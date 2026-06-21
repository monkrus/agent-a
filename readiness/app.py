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

from flask import (Flask, abort, redirect, render_template, request,
                   session, url_for)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch as fetchmod   # noqa: E402
import fixes as fixesmod   # noqa: E402
import intel as intelmod   # noqa: E402
import scorers             # noqa: E402
import yaml                # noqa: E402
from shopper import ask, ask_batch  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

CHECKS_PATH = pathlib.Path(__file__).resolve().parent / "checks" / "shopify-v1.yaml"
SCANS_DIR = pathlib.Path(__file__).resolve().parent / ".scans"
SCANS_DIR.mkdir(exist_ok=True)

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}


def _load_checks():
    data = yaml.safe_load(CHECKS_PATH.read_text())
    return data.get("pack", "pack"), data.get("version", ""), data.get("checks", [])


def _run_scan(target_url, n=None, pre_fetched_page=None):
    from concurrent.futures import ThreadPoolExecutor
    n = n or int(os.environ.get("SCAN_N", "5"))
    pack, version, checks = _load_checks()
    page = pre_fetched_page or fetchmod.fetch(target_url)

    def _base(c):
        return {k: c.get(k) for k in
                ("id", "type", "category", "title", "weight", "severity_if_fail", "fix")}

    static_checks = [c for c in checks if c.get("type") == "static"]
    browser_checks = [c for c in checks if c.get("type") == "browser"]
    shopper_checks = [c for c in checks if c.get("type") == "shopper"]

    results = []
    for c in static_checks:
        r = scorers.run_static(c, page)
        results.append({**_base(c), **r})
    for c in browser_checks:
        r = scorers.run_browser(c, page)
        results.append({**_base(c), **r})

    if shopper_checks:
        tasks = {c["id"]: c["task"] for c in shopper_checks}
        with ThreadPoolExecutor(max_workers=n) as pool:
            batch_results = list(pool.map(lambda _: ask_batch(page, tasks), range(n)))
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

    scan_id = hashlib.sha256(
        f"{target_url}:{datetime.datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    payload = {
        "scan_id": scan_id,
        "meta": {
            "target": target_url, "pack": pack, "version": version,
            "n": n, "shopper": os.environ.get("SHOPPER", "mock"),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "page_status": page.get("status"),
        },
        "readiness_score": readiness_score,
        "headline": _headline(results),
        "results": results,
        "intel": intelmod.analyze(page, page.get("llms_txt_content")),
    }
    (SCANS_DIR / f"{scan_id}.json").write_text(json.dumps(payload, indent=2))
    return scan_id


def _headline(results):
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
    path = SCANS_DIR / f"{scan_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ---- Routes ----------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan", methods=["POST"])
def scan():
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
        return render_template("index.html", error=(
            "That looks like a homepage or collection page. "
            "Please paste a specific product page URL instead — "
            "on your store, click on any product and copy the URL from your browser. "
            "It usually looks like: your-store.com/products/product-name"
        ))
    # Fetch page and check for 404 / soft-404 before running full scan
    try:
        pre_page = fetchmod.fetch(url)
    except Exception as e:
        return render_template("index.html", error=f"Could not fetch that URL: {e}")

    dead = fetchmod.is_dead_page(pre_page)
    if dead:
        return render_template("index.html", error=dead)

    try:
        scan_id = _run_scan(url, pre_fetched_page=pre_page)
    except Exception as e:
        return render_template("index.html", error=f"Could not scan that URL: {e}")
    return redirect(url_for("results", scan_id=scan_id))


@app.route("/results/<scan_id>")
def results(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)
    paid = session.get(f"paid_{scan_id}", False)
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    has_stripe = bool(stripe_key)
    return render_template("results.html", data=data, paid=paid,
                           has_stripe=has_stripe)


@app.route("/checkout/<scan_id>", methods=["POST"])
def checkout(scan_id):
    data = _load_scan(scan_id)
    if not data:
        abort(404)

    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    price_id = os.environ.get("STRIPE_PRICE_ID")
    if not stripe_key or not price_id:
        # No Stripe configured — unlock directly (dev/demo mode)
        session[f"paid_{scan_id}"] = True
        return redirect(url_for("results", scan_id=scan_id))

    import stripe
    stripe.api_key = stripe_key
    checkout_session = stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=request.host_url.rstrip("/") +
                     url_for("payment_success", scan_id=scan_id),
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
    session[f"paid_{scan_id}"] = True
    return redirect(url_for("results", scan_id=scan_id))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
