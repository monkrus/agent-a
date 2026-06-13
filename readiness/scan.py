#!/usr/bin/env python3
"""
scan.py — readiness runner. The scanner equivalent of run_scenarios.py.

  1. Load a check pack (YAML).
  2. Fetch the target page once (fetch.py).
  3. STATIC checks: run the deterministic probe.
     SHOPPER checks: ask the simulated shopper N times, grade the answers.
  4. Compute a weighted readiness score (0-100) over checks that produced a
     verdict; UNKNOWN checks are excluded from the score and disclosed.
  5. Write results.json and print a free-tier summary (score + headline only) —
     the full per-check report is the paid deliverable (see report_template.md).

Usage:
  SHOPPER=mock python scan.py --checks checks/shopify-v1.yaml \
      --target sample_page.html --n 10 --out /tmp/scan1
  SHOPPER=anthropic ANTHROPIC_API_KEY=sk-... python scan.py \
      --checks checks/shopify-v1.yaml --target https://store.example/products/x --n 10
"""
from __future__ import annotations
import argparse
import datetime
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch as fetchmod          # noqa: E402
import scorers                    # noqa: E402
from shopper import ask           # noqa: E402

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}


def load_checks(path):
    data = yaml.safe_load(pathlib.Path(path).read_text())
    return data.get("pack", "pack"), data.get("version", "unversioned"), data.get("checks", [])


def scan(checks, page, n):
    results = []
    for c in checks:
        base = {k: c.get(k) for k in
                ("id", "type", "category", "title", "weight", "severity_if_fail", "fix")}
        if c.get("type") == "static":
            r = scorers.run_static(c, page)
            results.append({**base, **r})
        else:
            answers = [ask(page, c["task"]) for _ in range(n)]
            g = scorers.grade_shopper(c, page, answers)
            results.append({**base, **g, "sample_answers": answers[:5]})
    return results


def score(results):
    """Weighted readiness score over checks with a numeric pass_fraction."""
    num = den = 0.0
    for r in results:
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        num += w * pf
        den += w
    return round(100 * num / den, 1) if den else None


def headline(results):
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
        return "No failures found, but some checks were inconclusive — see full report."
    return "Page reads cleanly to shopping agents across all checks."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checks", required=True)
    ap.add_argument("--target", required=True, help="URL or local .html file")
    ap.add_argument("--n", type=int, default=10, help="shopper runs per check")
    ap.add_argument("--out", default="/tmp/readiness", type=pathlib.Path)
    args = ap.parse_args()

    pack, version, checks = load_checks(args.checks)
    page = fetchmod.fetch(args.target)
    results = scan(checks, page, args.n)
    results.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
    s = score(results)

    args.out.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "target": args.target, "pack": pack, "version": version,
            "n": args.n, "shopper": __import__("os").environ.get("SHOPPER", "mock"),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "page_status": page.get("status"),
        },
        "readiness_score": s,
        "headline": headline(results),
        "results": results,
    }
    (args.out / "results.json").write_text(json.dumps(payload, indent=2))

    # ---- free-tier console summary (score + headline only) ----
    print(f"\n  AGENT READINESS SCORE: {s}/100" if s is not None else "\n  SCORE: n/a")
    print(f"  {payload['headline']}")
    counts = {}
    for r in results:
        counts[r.get("verdict")] = counts.get(r.get("verdict"), 0) + 1
    print(f"  checks: {counts}")
    print(f"  full per-check report -> {args.out/'results.json'} (paid deliverable)\n")


if __name__ == "__main__":
    main()
