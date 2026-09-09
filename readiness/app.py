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
import scorers             # noqa: E402
import yaml                # noqa: E402
import emailer             # noqa: E402
from shopper import ask, ask_batch  # noqa: E402

app = Flask(__name__)

# ---- Reverse proxy (Railway, Render, etc.) -----------------------------------
# Tell Flask it's behind HTTPS so session cookies, redirects, and url_for work.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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

# ---- Session cookie security ------------------------------------------------
app.config["SESSION_COOKIE_SECURE"] = True      # HTTPS only
app.config["SESSION_COOKIE_HTTPONLY"] = True     # no JS access
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # sent on top-level navigations (Stripe redirect)

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
    conn.execute("""CREATE TABLE IF NOT EXISTS counters (
        key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)""")
    conn.execute("""INSERT OR IGNORE INTO counters (key, value) VALUES ('total_scans', 0)""")
    conn.commit()
    conn.close()


def _increment_scan_count():
    """Increment the total scan counter. Returns the new count."""
    conn = _sqlite3.connect(str(_STORE_PATH), timeout=5)
    try:
        conn.execute("UPDATE counters SET value = value + 1 WHERE key = 'total_scans'")
        conn.commit()
        row = conn.execute("SELECT value FROM counters WHERE key = 'total_scans'").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _get_scan_count() -> int:
    conn = _sqlite3.connect(str(_STORE_PATH), timeout=5)
    try:
        row = conn.execute("SELECT value FROM counters WHERE key = 'total_scans'").fetchone()
        return row[0] if row else 0
    finally:
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


def _run_scan(target_url, n=None, pre_fetched_page=None, tier="free"):
    from concurrent.futures import ThreadPoolExecutor
    import time as _time
    _t0 = _time.time()
    n = n or int(os.environ.get("SCAN_N", "5"))
    pack, version, checks = _load_checks()
    checks = checks_for_tier(tier, checks)
    page = pre_fetched_page or fetchmod.fetch(target_url)

    def _base(c):
        return {k: c.get(k) for k in
                ("id", "type", "category", "title", "weight", "severity_if_fail", "fix")}

    ACCESS_GATE_IDS = {"RDY-031", "RDY-003"}

    static_checks = [c for c in checks if c.get("type") == "static"]
    browser_checks = [c for c in checks if c.get("type") == "browser"]
    shopper_checks = [c for c in checks if c.get("type") == "shopper"]
    assert tier != "free" or not shopper_checks, "free tier must never carry shopper checks"
    assert tier != "free" or not browser_checks, "free tier must never carry browser checks"

    results = []
    for c in static_checks:
        r = scorers.run_static(c, page)
        results.append({**_base(c), **r})

    # Layer 0: access gate — if blocked, skip expensive checks
    access_blocked = any(r.get("id") in ACCESS_GATE_IDS and r.get("verdict") == "FAIL"
                         for r in results)

    if access_blocked:
        gate_failures = [r.get("title", r.get("id")) for r in results
                         if r.get("id") in ACCESS_GATE_IDS and r.get("verdict") == "FAIL"]
        gate_reason = ("Skipped: site blocks agent access "
                       f"({'; '.join(gate_failures)}). "
                       "Fix access first — nothing else matters until agents can reach the page.")
        for c in browser_checks + shopper_checks:
            results.append({**_base(c), "verdict": "FAIL", "detail": gate_reason,
                            "pass_fraction": 0.0, "gated": True})
    else:
        for c in browser_checks:
            r = scorers.run_browser(c, page)
            results.append({**_base(c), **r})

        if shopper_checks:
            shopper_mode = "anthropic" if tier == "paid" else "mock"
            tasks = {c["id"]: c["task"] for c in shopper_checks}
            with ThreadPoolExecutor(max_workers=n) as pool:
                batch_results = list(pool.map(
                    lambda _: ask_batch(page, tasks, shopper=shopper_mode), range(n)))
            answers_by_check = {cid: [br[cid] for br in batch_results] for cid in tasks}
            for c in shopper_checks:
                answers = answers_by_check[c["id"]]
                g = scorers.grade_shopper(c, page, answers)
                results.append({**_base(c), **g, "sample_answers": answers[:3]})

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
    scan_id = hashlib.sha256(
        f"{target_url}:{now.isoformat()}".encode()
    ).hexdigest()[:12]

    # Confidence band (same logic as scan.py CLI)
    from scan import confidence_band
    margin = confidence_band(results, n)

    impact_est = impactmod.estimate(results)

    _elapsed = round(_time.time() - _t0, 1)

    payload = {
        "scan_id": scan_id,
        "meta": {
            "target": target_url, "pack": pack, "version": version,
            "n": n, "shopper": "anthropic" if tier == "paid" else "mock",
            "tier": tier,
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
        "meta_price": page.get("meta", {}).get("og:price:amount")
                      or page.get("meta", {}).get("product:price:amount"),
        "meta_currency": page.get("meta", {}).get("og:price:currency")
                         or page.get("meta", {}).get("product:price:currency", "USD"),
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
    stats["total_scans"] = _get_scan_count()
    return render_template("index.html", stats=stats)


@app.route("/scan", methods=["POST"])
def scan():
    # Rate limit: one scan per IP per SCAN_RATE_LIMIT seconds
    client_ip = request.remote_addr or "unknown"
    wait = _check_rate_limit(client_ip)
    if wait is not None:
        return render_template("index.html",
                               error=f"Please wait {wait} seconds before scanning again."), 429

    url = request.form.get("url", "").strip()
    # Strip leading bullets, dashes, whitespace from copy-paste
    url = url.lstrip("-*•· \t")
    if not url:
        return redirect(url_for("index"))
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # Strip tracking/marketing params — keep only variant
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    _p = urlparse(url)
    if _p.query:
        _keep = {k: v for k, v in parse_qs(_p.query).items() if k == "variant"}
        url = urlunparse(_p._replace(query=urlencode(_keep, doseq=True)))
    if len(url) > 2000:
        return render_template("index.html", error="That URL is too long (max 2,000 characters). Please paste just the product page URL.")
    parsed = urlparse(url)
    if not parsed.hostname or "." not in parsed.hostname:
        return render_template("index.html", error="That doesn't look like a valid URL. Please paste a product page URL like: your-store.com/products/product-name")
    # Check if this looks like a product page
    path = parsed.path.rstrip("/")
    if not path or path.count("/") < 2:
        return render_template("index.html", error=(
            "That looks like a homepage or collection page. "
            "Please paste a specific product page URL instead — "
            "on your store, click on any product and copy the URL from your browser. "
            "It usually looks like: your-store.com/products/product-name"
        ))
    # Fetch page and check for 404 / soft-404 before running full scan
    try:
        pre_page = fetchmod.fetch(url)
    except fetchmod._UnsafeURLError:
        return render_template("index.html", error="That URL points to a private or internal address and cannot be scanned.")
    except Exception as e:
        return render_template("index.html", error=f"Could not fetch that URL: {e}")

    dead = fetchmod.is_dead_page(pre_page)
    if dead:
        return render_template("index.html", error=dead)

    collection_warning = fetchmod.is_collection_page(pre_page)
    if collection_warning:
        return render_template("index.html", error=collection_warning)

    try:
        scan_id = _run_scan(url, pre_fetched_page=pre_page)
        _increment_scan_count()
    except Exception as e:
        return render_template("index.html", error=f"Could not scan that URL: {e}")
    return redirect(url_for("results", scan_id=scan_id))


# ---- Layer-by-layer check ordering for streaming display ----
LAYER_CHECKS = {
    "access":      {"RDY-003", "RDY-031"},
    "data":        {"RDY-001", "RDY-002", "RDY-004", "RDY-005", "RDY-011",
                    "RDY-012", "RDY-013", "RDY-029", "RDY-030", "RDY-033"},
    "extraction":  {"RDY-006", "RDY-007", "RDY-008", "RDY-009", "RDY-010"},
    "interaction": {"RDY-014", "RDY-015", "RDY-017", "RDY-018", "RDY-019",
                    "RDY-020", "RDY-021", "RDY-022", "RDY-023", "RDY-032"},
    "security":    {"RDY-016", "RDY-042", "RDY-043", "RDY-044", "RDY-045"},
    "protocols":   {"RDY-034", "RDY-035", "RDY-036", "RDY-037", "RDY-038",
                    "RDY-039", "RDY-040", "RDY-041"},
}

def _check_layer(check_id):
    for layer, ids in LAYER_CHECKS.items():
        if check_id in ids:
            return layer
    return "other"


@app.route("/scan-stream")
def scan_stream():
    """SSE endpoint: streams check results one at a time as they complete."""
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
    # Strip tracking/marketing params — keep only variant
    from urllib.parse import urlparse as _urlp, parse_qs as _pqs, urlencode as _ue, urlunparse as _uu
    _pp = _urlp(url)
    if _pp.query:
        _keep = {k: v for k, v in _pqs(_pp.query).items() if k == "variant"}
        url = _uu(_pp._replace(query=_ue(_keep, doseq=True)))
    if len(url) > 2000:
        return Response("data: " + json.dumps({"type": "error", "message": "That URL is too long (max 2,000 characters). Please paste just the product page URL."}) + "\n\n",
                        content_type="text/event-stream")
    from urllib.parse import urlparse as _urlparse
    _parsed = _urlparse(url)
    if not _parsed.hostname or "." not in _parsed.hostname:
        return Response("data: " + json.dumps({"type": "error", "message": "That doesn't look like a valid URL. Please paste a product page URL like: your-store.com/products/product-name"}) + "\n\n",
                        content_type="text/event-stream")

    def generate():
        from concurrent.futures import ThreadPoolExecutor
        import time as t

        _t0 = t.time()
        n = int(os.environ.get("SCAN_N", "5"))
        ACCESS_GATE_IDS = {"RDY-031", "RDY-003"}

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

        pack, version, checks = _load_checks()
        # Free tier: static checks only, no API spend
        tier = "free"  # scan-stream is always the free entry point
        checks = checks_for_tier(tier, checks)

        def _base(c):
            return {k: c.get(k) for k in
                    ("id", "type", "category", "title", "weight", "severity_if_fail", "fix")}

        static_checks = [c for c in checks if c.get("type") == "static"]
        browser_checks = [c for c in checks if c.get("type") == "browser"]
        shopper_checks = [c for c in checks if c.get("type") == "shopper"]
        assert not shopper_checks, "free tier must never carry shopper checks"
        assert not browser_checks, "free tier must never carry browser checks"
        total_checks = len(checks)

        results = []
        completed = 0

        # --- Layer 0: Access ---
        yield "data: " + json.dumps({"type": "layer", "layer": "access", "label": "Layer 0: Access"}) + "\n\n"

        access_checks = [c for c in static_checks if c.get("id") in ACCESS_GATE_IDS]
        other_static = [c for c in static_checks if c.get("id") not in ACCESS_GATE_IDS]

        for c in access_checks:
            r = scorers.run_static(c, page)
            result = {**_base(c), **r}
            results.append(result)
            completed += 1
            yield "data: " + json.dumps({
                "type": "check", "id": c["id"], "title": c["title"],
                "verdict": r["verdict"], "detail": r.get("detail", "")[:120],
                "layer": "access", "progress": f"{completed}/{total_checks}",
            }) + "\n\n"

        # Check gate
        access_blocked = any(r.get("id") in ACCESS_GATE_IDS and r.get("verdict") == "FAIL"
                             for r in results)

        if access_blocked:
            gate_reasons = []
            for r in results:
                if r.get("id") in ACCESS_GATE_IDS and r.get("verdict") == "FAIL":
                    if r.get("id") == "RDY-031":
                        gate_reasons.append("site blocks agent-like traffic")
                    elif r.get("id") == "RDY-003":
                        gate_reasons.append("robots.txt blocks AI crawlers")
                    else:
                        gate_reasons.append(r.get("title"))
            gate_reason = ("Skipped: site blocks agent access "
                           f"({'; '.join(gate_reasons)}). "
                           "Fix access first.")
            # Gather per-crawler details for the blocked report
            probe_detail = page.get("agent_probe_detail", {})
            blocked_uas = probe_detail.get("blocked_uas", [])
            allowed_uas = probe_detail.get("allowed_uas", [])
            yield "data: " + json.dumps({
                "type": "gate_blocked",
                "message": f"ACCESS BLOCKED — {'; '.join(gate_reasons)}",
                "skipped": len(other_static) + len(browser_checks) + len(shopper_checks),
                "blocked_uas": blocked_uas,
                "allowed_uas": allowed_uas,
            }) + "\n\n"

            # Mark remaining checks as gated
            for c in other_static + browser_checks + shopper_checks:
                results.append({**_base(c), "verdict": "FAIL", "detail": gate_reason,
                                "pass_fraction": 0.0, "gated": True})
                completed += 1
        else:
            yield "data: " + json.dumps({
                "type": "gate_passed", "message": "Access OK — continuing scan..."
            }) + "\n\n"

            # --- Split static checks by layer ---
            LAYER_LABELS = {
                "data": "Layer 1: Data",
                "extraction": "Layer 2: Extraction",
                "interaction": "Layer 3: Interaction",
                "security": "Layer 4: Security",
                "protocols": "Layer 5: Protocol Discovery",
            }
            data_static = [c for c in other_static if _check_layer(c.get("id", "")) == "data"]
            interaction_static = [c for c in other_static if _check_layer(c.get("id", "")) == "interaction"]
            security_static = [c for c in other_static if _check_layer(c.get("id", "")) == "security"]
            protocol_static = [c for c in other_static if _check_layer(c.get("id", "")) == "protocols"]

            def _run_static_batch(label_key, checks_list):
                nonlocal completed
                if not checks_list:
                    return
                yield "data: " + json.dumps({
                    "type": "layer", "layer": label_key,
                    "label": LAYER_LABELS[label_key],
                }) + "\n\n"
                for c in checks_list:
                    r = scorers.run_static(c, page)
                    result = {**_base(c), **r}
                    results.append(result)
                    completed += 1
                    yield "data: " + json.dumps({
                        "type": "check", "id": c["id"], "title": c["title"],
                        "verdict": r["verdict"], "detail": r.get("detail", "")[:120],
                        "layer": label_key, "progress": f"{completed}/{total_checks}",
                    }) + "\n\n"

            # Layer 1: Data (static)
            yield from _run_static_batch("data", data_static)

            # Layer 2: Extraction (shopper checks)
            if shopper_checks:
                yield "data: " + json.dumps({
                    "type": "layer", "layer": "extraction",
                    "label": "Layer 2: Extraction",
                }) + "\n\n"

                tasks = {c["id"]: c["task"] for c in shopper_checks}
                with ThreadPoolExecutor(max_workers=n) as pool:
                    batch_results = list(pool.map(lambda _: ask_batch(page, tasks), range(n)))
                answers_by_check = {cid: [br[cid] for br in batch_results] for cid in tasks}

                for c in shopper_checks:
                    answers = answers_by_check[c["id"]]
                    g = scorers.grade_shopper(c, page, answers)
                    result = {**_base(c), **g, "sample_answers": answers[:3]}
                    results.append(result)
                    completed += 1
                    yield "data: " + json.dumps({
                        "type": "check", "id": c["id"], "title": c["title"],
                        "verdict": g["verdict"], "detail": g.get("detail", "")[:120],
                        "layer": "extraction", "progress": f"{completed}/{total_checks}",
                    }) + "\n\n"

            # Layer 3: Interaction (static + browser in parallel)
            has_interaction = interaction_static or browser_checks
            if has_interaction:
                from concurrent.futures import as_completed as _as_completed

                yield "data: " + json.dumps({
                    "type": "layer", "layer": "interaction",
                    "label": "Layer 3: Interaction",
                }) + "\n\n"

                # Static interaction checks first
                for c in interaction_static:
                    r = scorers.run_static(c, page)
                    result = {**_base(c), **r}
                    results.append(result)
                    completed += 1
                    yield "data: " + json.dumps({
                        "type": "check", "id": c["id"], "title": c["title"],
                        "verdict": r["verdict"], "detail": r.get("detail", "")[:120],
                        "layer": "interaction", "progress": f"{completed}/{total_checks}",
                    }) + "\n\n"

                # Browser interaction checks in parallel
                if browser_checks:
                    for c in browser_checks:
                        yield "data: " + json.dumps({
                            "type": "check_running", "id": c["id"], "title": c["title"],
                            "layer": "interaction",
                        }) + "\n\n"

                if browser_checks:
                    with ThreadPoolExecutor(max_workers=len(browser_checks)) as pool:
                        future_to_check = {
                            pool.submit(scorers.run_browser, c, page): c
                            for c in browser_checks
                        }
                        for future in _as_completed(future_to_check):
                            c = future_to_check[future]
                            try:
                                r = future.result()
                            except Exception as exc:
                                r = {"verdict": "UNKNOWN",
                                     "detail": f"Browser check error: {exc}",
                                     "pass_fraction": None}
                            result = {**_base(c), **r}
                            results.append(result)
                            completed += 1
                            yield "data: " + json.dumps({
                                "type": "check", "id": c["id"], "title": c["title"],
                                "verdict": r["verdict"], "detail": r.get("detail", "")[:120],
                                "layer": "interaction", "progress": f"{completed}/{total_checks}",
                            }) + "\n\n"

            # Layer 4: Security (static)
            yield from _run_static_batch("security", security_static)

            # Layer 5: Protocol Discovery (static)
            yield from _run_static_batch("protocols", protocol_static)

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

        payload = {
            "scan_id": scan_id,
            "meta": {
                "target": url, "pack": pack, "version": version,
                "n": n, "shopper": "mock", "tier": tier,
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
            "meta_price": page.get("meta", {}).get("og:price:amount")
                          or page.get("meta", {}).get("product:price:amount"),
            "meta_currency": page.get("meta", {}).get("og:price:currency")
                             or page.get("meta", {}).get("product:price:currency", "USD"),
        }
        (SCANS_DIR / f"{scan_id}.json").write_text(json.dumps(payload, indent=2))
        _increment_scan_count()

        yield "data: " + json.dumps({
            "type": "done",
            "score": readiness_score,
            "headline": payload["headline"],
            "scan_id": scan_id,
            "duration": _elapsed,
            "impact": impact_est.get("estimated_monthly_loss", {}),
        }) + "\n\n"

    def safe_generate():
        try:
            yield from generate()
        except Exception:
            yield "data: " + json.dumps({"type": "error", "message": "Scan failed unexpectedly. Please try again."}) + "\n\n"

    return Response(safe_generate(), content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _generate_jsonld_snippet(data: dict) -> str | None:
    """Generate a ready-to-paste JSON-LD snippet when RDY-001 fails."""
    results = data.get("results", [])
    rdy001 = next((r for r in results if r.get("id") == "RDY-001"), None)
    if not rdy001 or rdy001.get("verdict") != "FAIL":
        return None

    import re as _re
    target = data.get("meta", {}).get("target", "")
    intel = data.get("intel", {})

    # Extract product name from scan data
    name = "Your Product Name"
    for r in results:
        if r.get("id") == "RDY-008" and r.get("ground_truth"):
            name = r["ground_truth"]
            break
    if name == "Your Product Name":
        # Try to extract from URL slug — strip leading numeric IDs
        slug = target.rstrip("/").split("/")[-1].split("?")[0]
        if slug:
            clean = _re.sub(r'^\d+[-_]', '', slug)  # strip "3350692-" prefix
            name = clean.replace("-", " ").replace("_", " ").title()

    # Extract price from scan results
    price = "0.00"
    currency = "USD"
    # Check shopper ground truth first (paid tier)
    for r in results:
        if r.get("id") == "RDY-006" and r.get("ground_truth"):
            price = f"{r['ground_truth']:.2f}"
            break
    # Fall back to price found in HTML detail (free tier)
    if price == "0.00":
        for r in results:
            if r.get("id") == "RDY-002" and r.get("verdict") == "PASS":
                detail = r.get("detail", "")
                m = _re.search(r'\$(\d[\d,]*\.?\d*)', detail)
                if m:
                    price = m.group(1)
                    break
    # Fall back to og:price:amount from scan metadata
    if price == "0.00":
        meta_price = data.get("meta_price")
        if meta_price:
            price = f"{float(meta_price):.2f}"
            currency = data.get("meta_currency", currency)

    snippet = json.dumps({
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "url": target,
        "image": "https://your-store.com/path-to-product-image.jpg",
        "description": "Add your product description here.",
        "brand": {"@type": "Brand", "name": "Your Brand"},
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": currency,
            "availability": "https://schema.org/InStock",
            "url": target,
        }
    }, indent=2)
    return snippet


@app.route("/results/<scan_id>")
def results(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)
    paid = session.get(f"paid_{scan_id}", False)
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    has_stripe = bool(stripe_key)
    dev_mode = os.environ.get("DEV_MODE", "").lower() == "true"
    email_sent_to = session.get(f"email_{scan_id}")
    team_sent = session.pop(f"sent_{scan_id}", False)
    has_email = emailer._is_configured()
    access_blocked = any(r.get("gated") for r in data.get("results", []))
    # Generate JSON-LD snippet if RDY-001 failed
    jsonld_snippet = _generate_jsonld_snippet(data) if not paid else None
    # Load comparison if one exists
    comparison = session.get(f"compare_{scan_id}")
    return render_template("results.html", data=data, paid=paid,
                           has_stripe=has_stripe, dev_mode=dev_mode,
                           email_sent_to=email_sent_to, team_sent=team_sent,
                           has_email=has_email, access_blocked=access_blocked,
                           jsonld_snippet=jsonld_snippet, comparison=comparison)


@app.route("/compare/<scan_id>", methods=["POST"])
def compare(scan_id):
    """Run a free scan on a competitor URL and show side-by-side."""
    data = _load_scan(scan_id)
    if not data:
        abort(404)
    comp_url = request.form.get("competitor_url", "").strip().lstrip("-*•· \t")
    if not comp_url:
        return redirect(url_for("results", scan_id=scan_id))
    if not comp_url.startswith(("http://", "https://")):
        comp_url = "https://" + comp_url
    # Strip tracking params — keep only variant
    from urllib.parse import urlparse as _urlp2, parse_qs as _pqs2, urlencode as _ue2, urlunparse as _uu2
    _cp = _urlp2(comp_url)
    if _cp.query:
        _keep = {k: v for k, v in _pqs2(_cp.query).items() if k == "variant"}
        comp_url = _uu2(_cp._replace(query=_ue2(_keep, doseq=True)))

    try:
        comp_page = fetchmod.fetch(comp_url)
        dead = fetchmod.is_dead_page(comp_page)
        if dead:
            session[f"compare_{scan_id}"] = None
            return redirect(url_for("results", scan_id=scan_id))
        comp_scan_id = _run_scan(comp_url, pre_fetched_page=comp_page)
        _increment_scan_count()
        comp_data = _load_scan(comp_scan_id)
        comp_results = comp_data.get("results", [])
        your_results = data.get("results", [])
        # Build check-level comparison
        your_fails = {r["id"] for r in your_results if r.get("verdict") == "FAIL"}
        comp_fails = {r["id"] for r in comp_results if r.get("verdict") == "FAIL"}
        your_passes = {r["id"] for r in your_results if r.get("verdict") == "PASS"}
        comp_passes = {r["id"] for r in comp_results if r.get("verdict") == "PASS"}
        # Checks competitor fails that you pass
        comp_missing = [r["title"] for r in comp_results
                        if r["id"] in (comp_fails - your_fails) and r["id"] in your_passes]
        # Checks you both fail
        both_fail = [r["title"] for r in your_results
                     if r["id"] in (your_fails & comp_fails)]
        # Checks you fail that competitor passes
        you_behind = [r["title"] for r in your_results
                      if r["id"] in (your_fails - comp_fails) and r["id"] in comp_passes]
        session[f"compare_{scan_id}"] = {
            "score": comp_data.get("readiness_score"),
            "target": comp_url,
            "scan_id": comp_scan_id,
            "comp_missing": comp_missing[:5],
            "both_fail": both_fail[:5],
            "you_behind": you_behind[:5],
        }
    except Exception:
        session[f"compare_{scan_id}"] = None
    return redirect(url_for("results", scan_id=scan_id))


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
            return redirect(url_for("results", scan_id=scan_id))
        abort(503, description="Payment system is not configured.")

    import stripe
    stripe.api_key = stripe_key
    checkout_session = stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        allow_promotion_codes=True,
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
            _logger.info("Stripe session %s: payment_status=%s, metadata=%s",
                         stripe_session_id, cs.payment_status, cs.metadata)
            if cs.payment_status in ("paid", "no_payment_required") and cs.metadata.get("scan_id") == scan_id:
                session[f"paid_{scan_id}"] = True
                buyer_email = cs.customer_details.email if cs.customer_details else None
                _logger.info("Payment verified for scan %s — unlocked", scan_id)
            else:
                _logger.warning("Payment NOT verified for scan %s: status=%s, meta_scan_id=%s",
                                scan_id, cs.payment_status, cs.metadata.get("scan_id"))
        except Exception:
            _logger.exception("Stripe verification failed for scan %s", scan_id)
    elif os.environ.get("DEV_MODE", "").lower() == "true":
        session[f"paid_{scan_id}"] = True

    # Auto-send report to buyer's email
    if buyer_email and session.get(f"paid_{scan_id}"):
        emailer.send_report(buyer_email, data)
        session[f"email_{scan_id}"] = buyer_email

    return redirect(url_for("results", scan_id=scan_id))


@app.route("/send-report/<scan_id>", methods=["POST"])
def send_report(scan_id):
    """Send the full report to an additional email (e.g. developer)."""
    if not session.get(f"paid_{scan_id}"):
        abort(403)
    data = _load_scan(scan_id)
    if not data:
        abort(404)
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
LAYER_ORDER = ["data", "extraction", "interaction", "security"]
LAYER_LABELS = {"data": "Data", "extraction": "Extraction",
                "interaction": "Interaction", "security": "Security"}


def _layer_scores(results):
    """Compute per-layer scores from results."""
    CAT_TO_LAYER = {}
    for r in results:
        cat = r.get("category", "")
        ctype = r.get("type", "")
        if ctype == "shopper":
            CAT_TO_LAYER[cat] = "extraction"
        elif ctype == "browser":
            CAT_TO_LAYER[cat] = "interaction"
        elif cat in ("security",):
            CAT_TO_LAYER[cat] = "security"
        elif cat in ("agent-interaction", "variant-interaction"):
            CAT_TO_LAYER[cat] = "interaction"
        else:
            CAT_TO_LAYER[cat] = "data"
    layers = {}
    for r in results:
        cat = r.get("category", "")
        layer = CAT_TO_LAYER.get(cat, "data")
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        if layer not in layers:
            layers[layer] = {"num": 0.0, "den": 0.0}
        layers[layer]["num"] += w * pf
        layers[layer]["den"] += w
    return {lay: round(v["num"] / v["den"] * 100, 1) if v["den"] else 0
            for lay, v in layers.items()}


def _plain_finding(r):
    """Convert a check result into a plain-English one-liner for merchants."""
    v = r.get("verdict", "")
    title = r.get("title", "")
    detail = r.get("detail", "")
    pr = r.get("pass_rate", "")
    if v == "FAIL" and pr:
        return f"{title} — agents got this right only {pr} times."
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

    # Layer scores for bars
    ls = _layer_scores(results)
    layers = []
    for lay in LAYER_ORDER:
        if lay in ls:
            pct = ls[lay]
            grade = "good" if pct >= 80 else "ok" if pct >= 50 else "bad"
            layers.append({"label": LAYER_LABELS[lay], "pct": int(pct), "grade": grade})

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
