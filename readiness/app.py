#!/usr/bin/env python3
"""
app.py — free-score web frontend for the readiness scanner.

The ListingIQ-style funnel:
  1. Merchant enters a product page URL.
  2. Engine scans it (N runs, weighted score).
  3. Free tier: score + headline + check-level pass/fail (no details).
  4. Paid tier: full per-check breakdown, evidence, fixes — unlocked via Stripe.

Run:
  pip install -r requirements.txt
  FLASK_APP=app.py flask run          # dev
  SHOPPER=mock flask run              # offline / demo mode

Env vars:
  SHOPPER          mock | anthropic  (default: mock)
  ANTHROPIC_API_KEY  required if SHOPPER=anthropic
  STRIPE_SECRET_KEY  required for paid checkout
  STRIPE_PRICE_ID    the Stripe Price object for a single report
  FLASK_SECRET_KEY   session signing (defaults to random per-restart in dev)
  SCAN_N             shopper runs per check (default: 5 for web, 10 for CLI)
  SMTP_HOST          SMTP server (default: smtp.gmail.com)
  SMTP_PORT          SMTP port (default: 587)
  SMTP_USER          SMTP username / login email
  SMTP_PASS          SMTP password or app password
  FROM_EMAIL         sender address (defaults to SMTP_USER)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets
import sys

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

from flask import (Flask, Response, abort, redirect, render_template, request,
                   session, url_for)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch as fetchmod   # noqa: E402
import fixes as fixesmod   # noqa: E402
import impact as impactmod # noqa: E402
import intel as intelmod   # noqa: E402
import yaml                # noqa: E402
import emailer             # noqa: E402
from pipeline import run_pipeline, run_pipeline_sync, gate_info, layer_for_check  # noqa: E402

app = Flask(__name__)

# ---- Secret key check -------------------------------------------------------
_flask_env = os.environ.get("FLASK_ENV", "production")
_flask_secret = os.environ.get("FLASK_SECRET_KEY", "")
_is_testing = "pytest" in sys.modules or os.environ.get("TESTING", "") == "1"
if not _flask_secret and _flask_env != "development" and not _is_testing:
    # Allow app to start in debug mode without FLASK_SECRET_KEY
    if not os.environ.get("FLASK_DEBUG", "0") == "1":
        raise RuntimeError(
            "FLASK_SECRET_KEY is not set. Set it in .env or environment, "
            "or set FLASK_ENV=development for local dev."
        )
app.secret_key = _flask_secret or secrets.token_hex(32)

CHECKS_PATH = pathlib.Path(__file__).resolve().parent / "checks" / "shopify-v1.yaml"
SCANS_DIR = pathlib.Path(__file__).resolve().parent / ".scans"
SCANS_DIR.mkdir(exist_ok=True)

# ---- Persistent mount detection --------------------------------------------
import logging as _logging
_logger = _logging.getLogger("agent-a")


def _detect_persistent_mount():
    """Check whether .scans/ is on a persistent volume mount."""
    # Railway volumes are mounted over the app directory — check if the
    # .scans dir is on a different device from the app root
    import stat
    try:
        scans_stat = os.stat(str(SCANS_DIR))
        app_stat = os.stat(str(pathlib.Path(__file__).resolve().parent))
        # Different device ID → likely a mounted volume
        if scans_stat.st_dev != app_stat.st_dev:
            return True
        # Presence of a Railway volume marker file
        if (SCANS_DIR / ".railway-volume").exists():
            return True
        # Fallback: env var override
        if os.environ.get("SCANS_PERSISTENT", "").lower() in ("1", "true"):
            return True
    except Exception:
        pass
    return False


_persistent = _detect_persistent_mount()
_scan_count = len(list(SCANS_DIR.glob("*.json")))
_logger.warning(
    "Scans dir: %s | persistent mount: %s | existing scans: %d",
    SCANS_DIR, "YES" if _persistent else "NO (ephemeral — will be lost on redeploy)",
    _scan_count,
)

# ---- Shared sqlite store for rate limits + stats cache ----------------------
# Works across gunicorn workers (file-level locking via sqlite WAL mode)
import time as _time
import sqlite3 as _sqlite3

_STORE_PATH = SCANS_DIR / "_app_store.db"

def _init_store():
    conn = _sqlite3.connect(str(_STORE_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS rate_limits (
        ip TEXT PRIMARY KEY, last_scan REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS stats_cache (
        key TEXT PRIMARY KEY, value TEXT, ts REAL)""")
    conn.commit()
    conn.close()

_init_store()

SCAN_RATE_LIMIT = int(os.environ.get("SCAN_RATE_LIMIT", "30"))  # seconds between scans per IP


def _check_rate_limit(client_ip: str) -> int | None:
    """Check rate limit. Returns seconds to wait, or None if OK."""
    now = _time.time()
    conn = _sqlite3.connect(str(_STORE_PATH), timeout=5)
    try:
        row = conn.execute("SELECT last_scan FROM rate_limits WHERE ip = ?",
                           (client_ip,)).fetchone()
        if row and now - row[0] < SCAN_RATE_LIMIT:
            return int(SCAN_RATE_LIMIT - (now - row[0])) + 1
        conn.execute("""INSERT INTO rate_limits (ip, last_scan) VALUES (?, ?)
                        ON CONFLICT(ip) DO UPDATE SET last_scan = ?""",
                     (client_ip, now, now))
        # Prune old entries
        conn.execute("DELETE FROM rate_limits WHERE last_scan < ?", (now - 600,))
        conn.commit()
        return None
    finally:
        conn.close()


SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}


# ---- Tier resolution (free vs paid) -----------------------------------------

def _payment_completed(scan_id: str) -> bool:
    """Check if a scan_id has a completed Stripe payment recorded."""
    # Payment state is stored in Flask session by /payment-success
    # For server-side checks outside request context, check scan metadata
    scan_path = SCANS_DIR / f"{scan_id}.json"
    if scan_path.exists():
        try:
            data = json.loads(scan_path.read_text())
            return data.get("meta", {}).get("paid", False)
        except Exception:
            pass
    return False


def resolve_tier(scan_id: str | None) -> str:
    """'paid' iff scan_id maps to a completed Stripe payment; else 'free'.
    Never trust a client-supplied tier field — derive it server-side."""
    if scan_id and _payment_completed(scan_id):
        return "paid"
    return "free"


def checks_for_tier(tier: str, checks: list[dict]) -> list[dict]:
    """Free tier = static checks only. Paid = all checks."""
    if tier == "free":
        return [c for c in checks if c.get("type") == "static"]
    return checks


def _load_checks():
    data = yaml.safe_load(CHECKS_PATH.read_text())
    return data.get("pack", "pack"), data.get("version", ""), data.get("checks", [])


# ---- Live stats from stored scans ------------------------------------------
STATS_CACHE_TTL = 300  # recompute every 5 minutes


def _scan_stats() -> dict:
    """Compute live stats from all stored scans. Cached for 5 minutes in sqlite."""
    now = _time.time()
    # Check sqlite cache first
    conn = _sqlite3.connect(str(_STORE_PATH), timeout=5)
    try:
        row = conn.execute("SELECT value, ts FROM stats_cache WHERE key = 'stats'").fetchone()
        if row and now - row[1] < STATS_CACHE_TTL:
            return json.loads(row[0])
    finally:
        conn.close()

    from urllib.parse import urlparse
    domains_seen: dict[str, bool] = {}  # domain -> has_critical_or_high_fail

    # Web scans
    for f in SCANS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            target = data.get("meta", {}).get("target", "")
            domain = urlparse(target).netloc
            if not domain:
                continue
            has_fail = any(
                r.get("verdict") == "FAIL" and r.get("severity_if_fail") in ("critical", "high")
                for r in data.get("results", [])
            )
            # If we've seen this domain before, keep the worst result
            if domain not in domains_seen:
                domains_seen[domain] = has_fail
            elif has_fail:
                domains_seen[domain] = True
        except (json.JSONDecodeError, OSError, PermissionError):
            continue

    # CLI scans
    cli_dir = SCANS_DIR / "cli"
    if cli_dir.is_dir():
        for f in cli_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                target = data.get("meta", {}).get("target", "")
                domain = urlparse(target).netloc
                if not domain:
                    continue
                has_fail = any(
                    r.get("verdict") == "FAIL" and r.get("severity_if_fail") in ("critical", "high")
                    for r in data.get("results", [])
                )
                if domain not in domains_seen:
                    domains_seen[domain] = has_fail
                elif has_fail:
                    domains_seen[domain] = True
            except (json.JSONDecodeError, OSError, PermissionError):
                continue

    total = len(domains_seen)
    failing = sum(1 for v in domains_seen.values() if v)
    pct = round(100 * failing / total) if total else 0

    stats = {"total_brands": total, "failing_pct": pct}
    conn = _sqlite3.connect(str(_STORE_PATH), timeout=5)
    try:
        conn.execute("""INSERT INTO stats_cache (key, value, ts) VALUES ('stats', ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = ?, ts = ?""",
                     (json.dumps(stats), now, json.dumps(stats), now))
        conn.commit()
    finally:
        conn.close()
    return stats


def _run_scan(target_url, n=None, pre_fetched_page=None, tier="free", scan_id=None):
    """Run a scan via the shared pipeline (pipeline.py) and write the payload.

    `scan_id`: reuse an existing scan_id instead of minting a new one. Used
    by the paid re-scan (see payment_success) so the paid results land under
    the same URL the merchant already has open/bookmarked.
    """
    import time as _time
    _t0 = _time.time()
    n = n or int(os.environ.get("SCAN_N", "5"))
    pack, version, checks = _load_checks()
    checks = checks_for_tier(tier, checks)
    page = pre_fetched_page or fetchmod.fetch(target_url)

    # SHOPPER env is the master switch the rest of the codebase (CLI,
    # batch.py) already respects — an explicit SHOPPER=mock must win even
    # for a paid scan (this is what keeps tests and staging environments
    # from making real, billed Anthropic calls just because tier="paid").
    # Only when SHOPPER isn't set do we pick a tier-based default, and even
    # then we degrade "anthropic" to "mock" rather than crash the checkout
    # flow if no API key is configured. meta.shopper below always records
    # which backend actually ran, never the aspirational one.
    shopper_mode = os.environ.get("SHOPPER")
    if not shopper_mode:
        shopper_mode = "anthropic" if tier == "paid" else "mock"
    if shopper_mode == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        shopper_mode = "mock"
    results = run_pipeline_sync(checks, page, n, tier=tier, shopper_mode=shopper_mode)

    results.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))

    # Generate fix recipes for failing checks
    for r in results:
        recipe = fixesmod.generate_fix(r, page)
        if recipe:
            r["fix_recipe"] = recipe

    num = den = 0.0
    for r in results:
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        num += w * pf
        den += w
    readiness_score = round(100 * num / den, 1) if den else None

    now = datetime.datetime.now()
    if not scan_id:
        scan_id = hashlib.sha256(
            f"{target_url}:{now.isoformat()}".encode()
        ).hexdigest()[:12]

    # Confidence band (same logic as scan.py CLI)
    from scan import confidence_band
    margin = confidence_band(results, n)

    impact_est = impactmod.estimate(results)

    _elapsed = round(_time.time() - _t0, 1)

    agent_runs = n if any(r.get("type") == "shopper" for r in results) else 0

    payload = {
        "scan_id": scan_id,
        "meta": {
            "target": target_url, "pack": pack, "version": version,
            "n": n, "shopper": shopper_mode,
            "tier": tier, "paid": tier == "paid",
            "agent_runs": agent_runs,
            "timestamp": now.isoformat(timespec="seconds"),
            "page_status": page.get("status"),
            "duration_seconds": _elapsed,
        },
        "readiness_score": readiness_score,
        "confidence_margin": margin,
        "headline": _headline(results),
        "results": results,
        "impact": impact_est,
        "intel": intelmod.analyze(page, page.get("llms_txt_content")),
        "gate": gate_info(results, page),
    }
    (SCANS_DIR / f"{scan_id}.json").write_text(json.dumps(payload, indent=2))
    return scan_id


def _headline(results):
    gated = [r for r in results if r.get("gated")]
    if gated:
        gate_sources = [r for r in results
                        if r.get("id") in ("RDY-031", "RDY-003") and r.get("verdict") == "FAIL"]
        reasons = []
        for r in gate_sources:
            if r.get("id") == "RDY-031":
                reasons.append("site blocks agent-like traffic")
            elif r.get("id") == "RDY-003":
                reasons.append("robots.txt blocks AI crawlers")
            else:
                reasons.append(r["title"])
        reason_str = "; ".join(reasons) if reasons else "access blocked"
        return (f"ACCESS BLOCKED — {reason_str}. "
                f"{len(gated)} checks skipped. Fix access first.")
    crits = [r for r in results
             if r.get("severity_if_fail") == "critical" and r.get("verdict") == "FAIL"]
    if crits:
        return f"{len(crits)} critical readiness failure(s): " + \
               "; ".join(r["title"] for r in crits[:2])
    fails = [r for r in results if r.get("verdict") == "FAIL"]
    if fails:
        return f"{len(fails)} issue(s) limiting agent readiness; top: {fails[0]['title']}."
    unknown = [r for r in results if r.get("verdict") == "UNKNOWN"]
    if unknown:
        return "No failures found, but some checks were inconclusive."
    return "Page reads cleanly to shopping agents across all checks."


def _load_scan(scan_id):
    import re as _re
    if not _re.fullmatch(r'[a-f0-9]{12}', scan_id):
        return None
    safe_name = os.path.basename(scan_id) + ".json"
    fpath = os.path.realpath(os.path.join(str(SCANS_DIR), safe_name))
    if not fpath.startswith(os.path.realpath(str(SCANS_DIR))):
        return None
    if not os.path.isfile(fpath):
        return None
    with open(fpath, 'r') as f:
        return json.load(f)


# ---- Routes ----------------------------------------------------------------

@app.route("/")
def index():
    stats = _scan_stats()
    return render_template("index.html", stats=stats)


def _index_error(error, status=200):
    """Render the homepage with an error message. index.html always
    references `stats.*` (the live "N% of stores fail" banner) — every
    error-path render_template("index.html", ...) call must pass stats
    too, or it 500s instead of showing the merchant the actual error."""
    return render_template("index.html", error=error, stats=_scan_stats()), status


@app.route("/scan", methods=["POST"])
def scan():
    # Rate limit: one scan per IP per SCAN_RATE_LIMIT seconds
    client_ip = request.remote_addr or "unknown"
    wait = _check_rate_limit(client_ip)
    if wait is not None:
        return _index_error(f"Please wait {wait} seconds before scanning again.", 429)

    url = request.form.get("url", "").strip()
    # Strip leading bullets, dashes, whitespace from copy-paste
    url = url.lstrip("-*•· \t")
    if not url:
        return redirect(url_for("index"))
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # Check if this looks like a product page
    from urllib.parse import urlparse
    path = urlparse(url).path.rstrip("/")
    if not path or path.count("/") < 2:
        return _index_error(
            "That looks like a homepage or collection page. "
            "Please paste a specific product page URL instead — "
            "on your store, click on any product and copy the URL from your browser. "
            "It usually looks like: your-store.com/products/product-name"
        )
    # Fetch page and check for 404 / soft-404 before running full scan
    try:
        pre_page = fetchmod.fetch(url)
    except fetchmod._UnsafeURLError:
        return _index_error("That URL points to a private or internal address and cannot be scanned.")
    except Exception as e:
        return _index_error(f"Could not fetch that URL: {e}")

    dead = fetchmod.is_dead_page(pre_page)
    if dead:
        return _index_error(dead)

    collection_warning = fetchmod.is_collection_page(pre_page)
    if collection_warning:
        return _index_error(collection_warning)

    try:
        scan_id = _run_scan(url, pre_fetched_page=pre_page)
    except Exception as e:
        return _index_error(f"Could not scan that URL: {e}")
    return redirect(url_for("results", scan_id=scan_id))


@app.route("/scan-stream")
def scan_stream():
    """SSE endpoint: streams check results one at a time as they complete.

    Drives the same `run_pipeline` generator used by the CLI and the
    non-streaming /scan route (see pipeline.py) — every event it yields is
    forwarded as an SSE message, so this route can no longer drop checks
    that the other entry points run.
    """
    # Rate limit: same per-IP limit as /scan
    client_ip = request.remote_addr or "unknown"
    wait = _check_rate_limit(client_ip)
    if wait is not None:
        return Response(
            "data: " + json.dumps({"type": "error",
                                   "message": f"Please wait {wait} seconds before scanning again."}) + "\n\n",
            content_type="text/event-stream", status=429)

    url = request.args.get("url", "").strip().lstrip("-*•· \t")
    if not url:
        return Response("data: " + json.dumps({"type": "error", "message": "No URL"}) + "\n\n",
                        content_type="text/event-stream")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    def generate():
        import time as t

        _t0 = t.time()
        n = int(os.environ.get("SCAN_N", "5"))

        yield "data: " + json.dumps({"type": "status", "message": "Fetching page..."}) + "\n\n"

        try:
            page = fetchmod.fetch(url)
        except fetchmod._UnsafeURLError:
            yield "data: " + json.dumps({"type": "error", "message": "That URL points to a private or internal address and cannot be scanned."}) + "\n\n"
            return
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "message": "Fetch failed. Check the URL and try again."}) + "\n\n"
            return

        dead = fetchmod.is_dead_page(page)
        if dead:
            yield "data: " + json.dumps({"type": "error", "message": dead}) + "\n\n"
            return

        # Same preflight the no-JS /scan route runs, so a collection/category
        # URL doesn't silently score as a broken product page here.
        collection_warning = fetchmod.is_collection_page(page)
        if collection_warning:
            yield "data: " + json.dumps({"type": "error", "message": collection_warning}) + "\n\n"
            return

        pack, version, checks = _load_checks()
        # Free tier: static checks only, no API spend
        tier = "free"  # scan-stream is always the free entry point
        checks = checks_for_tier(tier, checks)
        total_checks = len(checks)

        results = None
        for event in run_pipeline(checks, page, n, tier=tier):
            if event["type"] == "complete":
                results = event["results"]
                break
            if event["type"] == "layer":
                yield "data: " + json.dumps(event) + "\n\n"
            elif event["type"] == "check_running":
                yield "data: " + json.dumps(event) + "\n\n"
            elif event["type"] == "check":
                yield "data: " + json.dumps(event) + "\n\n"
            elif event["type"] == "gate_blocked":
                yield "data: " + json.dumps(event) + "\n\n"
            elif event["type"] == "gate_passed":
                yield "data: " + json.dumps(event) + "\n\n"

        # --- Final score ---
        results.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))

        for r in results:
            recipe = fixesmod.generate_fix(r, page)
            if recipe:
                r["fix_recipe"] = recipe

        num = den = 0.0
        for r in results:
            pf = r.get("pass_fraction")
            if pf is None:
                continue
            w = r.get("weight", 0) or 0
            num += w * pf
            den += w
        readiness_score = round(100 * num / den, 1) if den else None

        now = datetime.datetime.now()
        scan_id = hashlib.sha256(
            f"{url}:{now.isoformat()}".encode()
        ).hexdigest()[:12]

        from scan import confidence_band
        margin = confidence_band(results, n)
        impact_est = impactmod.estimate(results)
        _elapsed = round(t.time() - _t0, 1)

        # The free tier never runs shopper checks, so this is always 0 today
        # — kept as a real computation (not a hardcoded "n") so it stays
        # correct if the free tier ever changes.
        agent_runs = n if any(r.get("type") == "shopper" for r in results) else 0

        payload = {
            "scan_id": scan_id,
            "meta": {
                "target": url, "pack": pack, "version": version,
                "n": n, "shopper": "mock", "tier": tier, "paid": False,
                "agent_runs": agent_runs,
                "timestamp": now.isoformat(timespec="seconds"),
                "page_status": page.get("status"),
                "duration_seconds": _elapsed,
            },
            "readiness_score": readiness_score,
            "confidence_margin": margin,
            "headline": _headline(results),
            "results": results,
            "impact": impact_est,
            "intel": intelmod.analyze(page, page.get("llms_txt_content")),
            "gate": gate_info(results, page),
        }
        (SCANS_DIR / f"{scan_id}.json").write_text(json.dumps(payload, indent=2))

        yield "data: " + json.dumps({
            "type": "done",
            "score": readiness_score,
            "headline": payload["headline"],
            "scan_id": scan_id,
            "duration": _elapsed,
            "impact": impact_est.get("estimated_monthly_loss", {}),
            "blocked": bool(payload["gate"]),
            "total_checks": total_checks,
        }) + "\n\n"

    def safe_generate():
        try:
            yield from generate()
        except Exception:
            yield "data: " + json.dumps({"type": "error", "message": "Scan failed unexpectedly. Please try again."}) + "\n\n"

    return Response(safe_generate(), content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _unlock_paid_scan(scan_id: str) -> dict | None:
    """Re-run the scan with the paid tier's checks (shopper + browser) and
    overwrite the stored payload under the same scan_id.

    Before this, paying $49 only set a session flag — the report the
    merchant saw was still the free static-checks-only payload, re-labeled.
    This makes the purchase actually run what the paywall copy promises.

    Idempotent: if the stored payload already has meta.paid=True, this is
    a no-op, so a page refresh or a retried payment webhook can't spend
    the shopper/browser budget twice.
    """
    data = _load_scan(scan_id)
    if not data:
        return None
    if data.get("meta", {}).get("paid"):
        return data
    target_url = data.get("meta", {}).get("target", "")
    n = data.get("meta", {}).get("n") or int(os.environ.get("SCAN_N", "5"))
    try:
        _run_scan(target_url, n=n, tier="paid", scan_id=scan_id)
    except Exception:
        _logger.exception("Paid re-scan failed for scan_id=%s target=%s", scan_id, target_url)
        return _load_scan(scan_id)  # unchanged free payload; caller decides what to show
    return _load_scan(scan_id)


@app.route("/results/<scan_id>")
def results(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)
    # Persistent entitlement lives in the stored payload (meta.paid), not
    # just the session cookie — a cookie loss or a second device must not
    # re-lock a report that was already paid for. The session flag is kept
    # as a same-request-cycle signal (e.g. right after DEV_MODE unlock).
    paid = session.get(f"paid_{scan_id}", False) or bool(data.get("meta", {}).get("paid"))
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    has_stripe = bool(stripe_key)
    dev_mode = os.environ.get("DEV_MODE", "").lower() == "true"
    email_sent_to = session.get(f"email_{scan_id}")
    team_sent = session.pop(f"sent_{scan_id}", False)
    has_email = emailer._is_configured()
    access_blocked = any(r.get("gated") for r in data.get("results", []))
    return render_template("results.html", data=data, paid=paid,
                           has_stripe=has_stripe, dev_mode=dev_mode,
                           email_sent_to=email_sent_to, team_sent=team_sent,
                           has_email=has_email, access_blocked=access_blocked)


@app.route("/checkout/<scan_id>", methods=["POST"])
def checkout(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)

    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    price_id = os.environ.get("STRIPE_PRICE_ID")
    if not stripe_key or not price_id:
        # Only allow demo unlock if DEV_MODE is explicitly enabled
        if os.environ.get("DEV_MODE", "").lower() == "true":
            session[f"paid_{scan_id}"] = True
            _unlock_paid_scan(scan_id)
            return redirect(url_for("results", scan_id=scan_id))
        abort(503, description="Payment system is not configured.")

    import stripe
    stripe.api_key = stripe_key
    checkout_session = stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=request.host_url.rstrip("/") +
                     url_for("payment_success", scan_id=scan_id) +
                     "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=request.host_url.rstrip("/") +
                    url_for("results", scan_id=scan_id),
        metadata={"scan_id": scan_id},
    )
    return redirect(checkout_session.url, code=303)


@app.route("/payment-success/<scan_id>")
def payment_success(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)
    # Verify payment via Stripe checkout session before unlocking
    stripe_session_id = request.args.get("session_id", "")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    buyer_email = None
    if stripe_key and stripe_session_id:
        try:
            import stripe
            stripe.api_key = stripe_key
            cs = stripe.checkout.Session.retrieve(stripe_session_id)
            if cs.payment_status == "paid" and cs.metadata.get("scan_id") == scan_id:
                session[f"paid_{scan_id}"] = True
                buyer_email = cs.customer_details.email if cs.customer_details else None
        except Exception:
            pass  # fall through — don't unlock without verified payment
    elif os.environ.get("DEV_MODE", "").lower() == "true":
        session[f"paid_{scan_id}"] = True

    if session.get(f"paid_{scan_id}"):
        data = _unlock_paid_scan(scan_id) or data

    # Auto-send report to buyer's email
    if buyer_email and session.get(f"paid_{scan_id}"):
        emailer.send_report(buyer_email, data)
        session[f"email_{scan_id}"] = buyer_email

    return redirect(url_for("results", scan_id=scan_id))


@app.route("/send-report/<scan_id>", methods=["POST"])
def send_report(scan_id):
    """Send the full report to an additional email (e.g. developer)."""
    data = _load_scan(scan_id)
    if not data:
        abort(404)
    # Same persistent-entitlement check as /results: don't require the
    # buyer to still have the session cookie that unlocked this scan.
    if not (session.get(f"paid_{scan_id}") or data.get("meta", {}).get("paid")):
        abort(403)
    to_email = request.form.get("email", "").strip()
    if not to_email or "@" not in to_email:
        return redirect(url_for("results", scan_id=scan_id))
    target = data.get("meta", {}).get("target", "")
    emailer.send_report(to_email, data,
                        subject=f"Agent Readiness Report for {target} (shared with you)")
    session[f"sent_{scan_id}"] = True
    return redirect(url_for("results", scan_id=scan_id))


# ---- Shareable public results (/r/<scan_id>) --------------------------------

SEV_RANK_SHARE = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}
LAYER_ORDER = ["data", "extraction", "interaction", "security", "discovery"]
LAYER_LABELS = {"data": "Data", "extraction": "Extraction",
                "interaction": "Interaction", "security": "Security",
                "discovery": "Protocol & Discovery"}


def _layer_scores(results):
    """Compute per-layer scores from results, using the same category->layer
    map as the scan pipeline (pipeline.layer_for_check) so the share page
    can't drift from what actually ran."""
    layers = {}
    counts = {}
    for r in results:
        layer = layer_for_check(r)
        if layer == "access":
            continue  # access-gate checks aren't shown as a share-page bar
        counts[layer] = counts.get(layer, 0) + 1
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        if layer not in layers:
            layers[layer] = {"num": 0.0, "den": 0.0}
        layers[layer]["num"] += w * pf
        layers[layer]["den"] += w
    scores = {lay: round(v["num"] / v["den"] * 100, 1) if v["den"] else 0
             for lay, v in layers.items()}
    return scores, counts


def _plain_finding(r):
    """Convert a check result into a plain-English one-liner for merchants."""
    v = r.get("verdict", "")
    title = r.get("title", "")
    detail = r.get("detail", "")
    pr = r.get("pass_rate", "")
    if v == "FAIL" and pr:
        return f"{title} — agent answered correctly in {pr} runs."
    if v == "UNKNOWN":
        return f"{title} — could not be verified (agents can't find this data either)."
    if detail and len(detail) < 120:
        return detail
    return title


def _domain_from_url(url):
    from urllib.parse import urlparse
    h = urlparse(url).hostname or url
    return h[4:] if h.startswith("www.") else h


@app.route("/r/<scan_id>")
def share(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)

    score = data.get("readiness_score")
    domain = _domain_from_url(data.get("meta", {}).get("target", ""))
    results = data.get("results", [])

    # Layer scores for bars. `counts` records how many checks actually ran
    # in each layer, so a bar can never read e.g. "Security 100%" when only
    # a fraction of the security checks in the pack were run — see CLAUDE.md
    # rule 6: a percentage without its denominator is a claim we can't back.
    ls, counts = _layer_scores(results)
    layers = []
    for lay in LAYER_ORDER:
        if lay in ls:
            pct = ls[lay]
            grade = "good" if pct >= 80 else "ok" if pct >= 50 else "bad"
            layers.append({"label": LAYER_LABELS[lay], "pct": int(pct), "grade": grade,
                           "n_checks": counts.get(lay, 0)})

    # Top 3 findings (FAIL/UNKNOWN, sorted by severity)
    findings_raw = [r for r in results if r.get("verdict") in ("FAIL", "UNKNOWN")]
    findings_raw.sort(key=lambda r: SEV_RANK_SHARE.get(r.get("severity_if_fail"), 4))
    findings = []
    for f in findings_raw[:3]:
        findings.append({**f, "plain_finding": _plain_finding(f)})

    # OG description: worst finding one-liner
    og_desc = findings[0]["plain_finding"] if findings else "All checks passed."

    # OG image URL
    og_image_url = request.host_url.rstrip("/") + url_for("share_og_image", scan_id=scan_id)
    canonical_url = request.host_url.rstrip("/") + url_for("share", scan_id=scan_id)

    return render_template("share.html",
                           data=data, score=score, domain=domain,
                           layers=layers, findings=findings,
                           og_description=og_desc, og_image_url=og_image_url,
                           canonical_url=canonical_url)


@app.route("/r/<scan_id>/og.png")
def share_og_image(scan_id):
    from flask import Response
    data = _load_scan(scan_id)
    if not data:
        abort(404)

    # Check cached OG image — scan_id already validated by _load_scan above
    import re as _re
    if not _re.fullmatch(r'[a-f0-9]{12}', scan_id):
        abort(400)
    safe_name = os.path.basename(scan_id) + "_og.png"
    scans_real = os.path.realpath(str(SCANS_DIR))
    og_fpath = os.path.realpath(os.path.join(scans_real, safe_name))
    if og_fpath.startswith(scans_real) and os.path.isfile(og_fpath):
        with open(og_fpath, 'rb') as f:
            return Response(f.read(), mimetype="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    try:
        import og_image
        png_bytes = og_image.generate(data, og_fpath)
        return Response(png_bytes, mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    except ImportError:
        abort(404, description="Pillow not installed for OG image generation.")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5000)
else:
    # Production guard: DEV_MODE must not be enabled outside debug mode
    if os.environ.get("DEV_MODE", "").lower() == "true" and not app.debug:
        import warnings
        warnings.warn(
            "DEV_MODE=true is set but app is not in debug mode. "
            "Demo unlock is active — unset DEV_MODE in production.",
            stacklevel=1,
        )
