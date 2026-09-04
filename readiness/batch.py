#!/usr/bin/env python3
"""
batch.py — Batch scan mode.

Usage:
  python -m readiness.batch targets.txt

Input: text file, one URL or domain per line (up to 25 targets).
Runs full N-run scans sequentially with polite rate limiting.
Resumable: skips already-scanned domains.

Output per domain:
  - Scan record in .scans/
  - /r/ permalink
  - Outreach email draft in outreach/<domain>.md

Summary: outreach/batch_summary.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import pathlib
import sys
import time

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fetch as fetchmod
import fixes as fixesmod
import intel as intelmod
from pipeline import run_pipeline_sync, gate_info
from scan import headline as scan_headline, confidence_band

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}
CHECKS_PATH = pathlib.Path(__file__).resolve().parent / "checks" / "shopify-v1.yaml"
SCANS_DIR = pathlib.Path(__file__).resolve().parent / ".scans"
OUTREACH_DIR = pathlib.Path(__file__).resolve().parent.parent / "outreach"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")


def _load_checks():
    import yaml
    data = yaml.safe_load(CHECKS_PATH.read_text())
    return data.get("pack", "pack"), data.get("version", ""), data.get("checks", [])


def _domain_from_url(url):
    from urllib.parse import urlparse
    h = urlparse(url).hostname or url
    return h[4:] if h.startswith("www.") else h


def _find_existing_scan(domain):
    """Check if we already have a scan for this domain."""
    if not SCANS_DIR.exists():
        return None
    for f in SCANS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            target = data.get("meta", {}).get("target", "")
            if _domain_from_url(target) == domain:
                return data
        except (json.JSONDecodeError, KeyError, PermissionError, OSError):
            continue
    return None


def _run_scan(target_url, n):
    """Run a full scan, return (scan_id, payload).

    Uses the shared pipeline (pipeline.py) — the same one the CLI and web
    routes use. Before this, batch.py had its own fourth copy of the
    fetch -> static -> browser -> shopper flow, and that copy never
    implemented the access gate at all: a blocked site would still get
    browser/shopper checks run against a challenge page. tier="paid" here
    just means "run every check type"; batch scans are always full scans.
    """
    import hashlib

    pack, version, checks = _load_checks()
    page = fetchmod.fetch(target_url)

    dead = fetchmod.is_dead_page(page)
    if dead:
        return None, {"error": dead, "meta": {"target": target_url}}

    results = run_pipeline_sync(checks, page, n, tier="paid")
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

    confidence_margin = confidence_band(results, n)
    headline = scan_headline(results)

    scan_id = hashlib.sha256(
        f"{target_url}:{datetime.datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    agent_runs = n if any(r.get("type") == "shopper" for r in results) else 0

    payload = {
        "scan_id": scan_id,
        "meta": {
            "target": target_url, "pack": pack, "version": version,
            "n": n, "shopper": os.environ.get("SHOPPER", "mock"),
            "tier": "paid", "paid": True,
            "agent_runs": agent_runs,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "page_status": page.get("status"),
        },
        "readiness_score": readiness_score,
        "confidence_margin": confidence_margin,
        "headline": headline,
        "results": results,
        "intel": intelmod.analyze(page, page.get("llms_txt_content")),
        "gate": gate_info(results, page),
    }

    SCANS_DIR.mkdir(exist_ok=True)
    (SCANS_DIR / f"{scan_id}.json").write_text(json.dumps(payload, indent=2))
    return scan_id, payload


def main():
    ap = argparse.ArgumentParser(description="Batch scan domains from a file")
    ap.add_argument("targets_file", help="Text file with one URL/domain per line")
    ap.add_argument("--n", type=int, default=int(os.environ.get("SCAN_N", "10")),
                    help="Shopper runs per check (default: 10)")
    ap.add_argument("--delay", type=int, default=5,
                    help="Seconds between scans (rate limiting, default: 5)")
    ap.add_argument("--base-url", default=BASE_URL,
                    help="Base URL for permalinks (default: from BASE_URL env or localhost:5000)")
    ap.add_argument("--no-outreach", action="store_true",
                    help="Skip outreach email generation (for leaderboard/public tier)")
    args = ap.parse_args()

    targets_path = pathlib.Path(args.targets_file)
    if not targets_path.exists():
        print(f"Error: {targets_path} not found")
        sys.exit(1)

    lines = [l.strip() for l in targets_path.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]

    if len(lines) > 25:
        print(f"Warning: {len(lines)} targets found, processing first 25")
        lines = lines[:25]

    OUTREACH_DIR.mkdir(exist_ok=True)

    # Import outreach generator
    from outreach import generate_email

    csv_rows = []
    total = len(lines)

    for i, line in enumerate(lines, 1):
        url = line.strip().lstrip("-*• \t")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        domain = _domain_from_url(url)
        print(f"\n[{i}/{total}] {domain}")

        # Check for existing scan (resumable)
        existing = _find_existing_scan(domain)
        if existing:
            scan_id = existing.get("scan_id", "unknown")
            print(f"  Already scanned (scan_id: {scan_id}), skipping...")
            payload = existing
        else:
            print(f"  Scanning {url}...")
            try:
                scan_id, payload = _run_scan(url, args.n)
            except Exception as e:
                print(f"  ERROR: {e}")
                csv_rows.append({
                    "domain": domain, "score": "ERROR",
                    "worst_finding": str(e), "permalink": ""
                })
                continue

            if scan_id is None:
                err = payload.get("error", "unknown error")
                print(f"  SKIPPED: {err}")
                csv_rows.append({
                    "domain": domain, "score": "SKIPPED",
                    "worst_finding": err, "permalink": ""
                })
                continue

        score = payload.get("readiness_score")
        results = payload.get("results", [])
        scan_id = payload.get("scan_id", "unknown")
        permalink = f"{args.base_url.rstrip('/')}/r/{scan_id}"

        # Worst finding for CSV
        fails = [r for r in results if r.get("verdict") == "FAIL"]
        fails.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
        worst = fails[0]["title"] if fails else "None"

        print(f"  Score: {score}/100 | Top issue: {worst}")
        print(f"  Permalink: {permalink}")

        # Generate outreach email (unless --no-outreach)
        if not args.no_outreach:
            email_md = generate_email(payload, permalink)
            outreach_path = OUTREACH_DIR / f"{domain}.md"
            outreach_path.write_text(email_md)
            print(f"  Outreach: {outreach_path}")
        else:
            print(f"  Outreach: skipped (--no-outreach)")

        csv_rows.append({
            "domain": domain, "score": score,
            "worst_finding": worst, "permalink": permalink
        })

        # Rate limiting (skip delay for cached scans)
        if not existing and i < total:
            print(f"  Waiting {args.delay}s...")
            time.sleep(args.delay)

    # Write summary CSV
    csv_path = OUTREACH_DIR / "batch_summary.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["domain", "score", "worst_finding", "permalink"])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n{'='*60}")
    print(f"Batch complete: {total} domains processed")
    print(f"Summary CSV: {csv_path}")
    print(f"Outreach drafts: {OUTREACH_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
