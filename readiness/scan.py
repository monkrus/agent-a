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

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch as fetchmod          # noqa: E402
import scorers                    # noqa: E402
import impact as impactmod        # noqa: E402
from shopper import ask, ask_batch  # noqa: E402

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}


def load_checks(path):
    data = yaml.safe_load(pathlib.Path(path).read_text())
    return data.get("pack", "pack"), data.get("version", "unversioned"), data.get("checks", [])


def scan(checks, page, n):
    from concurrent.futures import ThreadPoolExecutor

    static_checks = [c for c in checks if c.get("type") == "static"]
    browser_checks = [c for c in checks if c.get("type") == "browser"]
    shopper_checks = [c for c in checks if c.get("type") == "shopper"]

    def _base(c):
        return {k: c.get(k) for k in
                ("id", "type", "category", "title", "weight", "severity_if_fail", "fix")}

    # Static + browser checks (unchanged)
    results = []
    for c in static_checks:
        r = scorers.run_static(c, page)
        results.append({**_base(c), **r})
    for c in browser_checks:
        r = scorers.run_browser(c, page)
        results.append({**_base(c), **r})

    # Shopper checks: batched — all tasks in one API call per run
    if shopper_checks:
        tasks = {c["id"]: c["task"] for c in shopper_checks}
        # N batched calls in parallel (each call asks all shopper questions)
        with ThreadPoolExecutor(max_workers=n) as pool:
            batch_results = list(pool.map(lambda _: ask_batch(page, tasks), range(n)))
        # Transpose: {check_id: [answer_run1, answer_run2, ...]}
        answers_by_check = {cid: [br[cid] for br in batch_results] for cid in tasks}
        for c in shopper_checks:
            answers = answers_by_check[c["id"]]
            g = scorers.grade_shopper(c, page, answers)
            results.append({**_base(c), **g, "sample_answers": answers[:5]})

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


def confidence_band(results, n):
    """Estimate +/- confidence interval for the score.

    Sources of variance:
    - Shopper checks: N runs with stochastic LLM -> binomial uncertainty
    - Browser checks: non-deterministic (modal timing, popups)
    - Static checks: deterministic (zero variance)

    Returns (low, high) bounds as absolute score points, or None.
    Uses Wilson interval per shopper check, propagated through weights.
    """
    import math
    z = 1.96  # 95% CI

    den = 0.0
    variance_sum = 0.0
    for r in results:
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        den += w

        check_type = r.get("type", "static")
        if check_type == "shopper":
            # Binomial variance for pass_fraction with N observations
            p = pf
            se = math.sqrt(p * (1 - p) / n) if n > 0 else 0
            variance_sum += (w * se) ** 2
        elif check_type == "browser":
            # Browser with majority-vote (3 attempts): lower variance than single-shot
            browser_attempts = r.get("browser_attempts", 1)
            se = 0.3 / math.sqrt(max(browser_attempts, 1))
            variance_sum += (w * se) ** 2
        # static: variance = 0

    if den == 0:
        return None

    # Propagate: score = 100 * sum(w*pf) / sum(w)
    # SE(score) = 100 * sqrt(sum((w*se)^2)) / sum(w)
    score_se = 100 * math.sqrt(variance_sum) / den
    margin = round(z * score_se, 1)
    return margin


def report_data(results, page):
    """Compute derived report data from scan results."""
    # Agent reliability percentages
    reliability = {}
    LABELS = {
        "price-extraction": "Price",
        "availability-extraction": "Availability",
        "identity-extraction": "Product name",
        "policy-extraction": "Policy info",
    }
    for r in results:
        cat = r.get("category", "")
        if cat in LABELS and r.get("type") == "shopper":
            pf = r.get("pass_fraction")
            reliability[LABELS[cat]] = f"{int(pf * 100)}%" if pf is not None else "N/A"

    # Browser vs agent comparison
    browser_vs_agent = {}
    feature_map = {
        "price-extraction": "Price",
        "price-legibility": "Price in HTML",
        "availability-extraction": "Availability",
        "identity-extraction": "Product name",
        "agent-interaction": "Add to cart",
    }
    has_rendered = bool(page.get("rendered_text"))
    for r in results:
        cat = r.get("category", "")
        if cat in feature_map:
            label = feature_map[cat]
            agent_ok = r.get("verdict") == "PASS"
            # Browser generally works for everything (it renders JS)
            browser_ok = True
            if label not in browser_vs_agent:
                browser_vs_agent[label] = {"browser": browser_ok, "agent": agent_ok}

    # AI visibility gap (rendered DOM delta)
    visibility_gap = None
    for r in results:
        if r.get("id") == "RDY-013" and "Rendered DOM has" in r.get("detail", ""):
            import re
            m = re.search(r"Rendered DOM has (\d+) more chars", r["detail"])
            if m:
                visibility_gap = int(m.group(1))

    # Score improvement roadmap
    roadmap = []
    for r in results:
        if r.get("verdict") == "FAIL" and r.get("weight"):
            pf = r.get("pass_fraction", 0) or 0
            potential_gain = r["weight"] * (1.0 - pf)
            roadmap.append({
                "fix": r.get("title", ""),
                "severity": r.get("severity_if_fail", "medium"),
                "points": round(potential_gain, 1),
            })
    roadmap.sort(key=lambda x: x["points"], reverse=True)

    # Severity breakdown
    severity = {"critical": [], "major": [], "minor": []}
    for r in results:
        if r.get("verdict") != "FAIL":
            continue
        sev = r.get("severity_if_fail", "medium")
        bucket = "critical" if sev == "critical" else "major" if sev in ("high",) else "minor"
        severity[bucket].append(r.get("title", ""))

    return {
        "agent_reliability": reliability,
        "browser_vs_agent": browser_vs_agent,
        "visibility_gap_chars": visibility_gap,
        "score_roadmap": roadmap[:5],
        "severity_breakdown": severity,
    }


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
    ap.add_argument("--compare", default=None,
                    help="Competitor URL to scan for side-by-side comparison")
    args = ap.parse_args()

    pack, version, checks = load_checks(args.checks)
    page = fetchmod.fetch(args.target)

    # Abort early on 404 / soft-404 pages
    dead = fetchmod.is_dead_page(page)
    if dead:
        print(f"\n  SCAN ABORTED: {dead}\n")
        sys.exit(1)

    results = scan(checks, page, args.n)
    results.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
    s = score(results)
    margin = confidence_band(results, args.n)

    args.out.mkdir(parents=True, exist_ok=True)
    impact_est = impactmod.estimate(results)
    rdata = report_data(results, page)
    payload = {
        "meta": {
            "target": args.target, "pack": pack, "version": version,
            "n": args.n, "shopper": __import__("os").environ.get("SHOPPER", "mock"),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "page_status": page.get("status"),
        },
        "readiness_score": s,
        "confidence_margin": margin,
        "headline": headline(results),
        "report": rdata,
        "results": results,
        "impact": impact_est,
    }

    # ---- competitor comparison (optional) ----
    if args.compare:
        comp_page = fetchmod.fetch(args.compare)
        comp_results = scan(checks, comp_page, args.n)
        comp_results.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
        comp_s = score(comp_results)
        payload["comparison"] = {
            "competitor_url": args.compare,
            "competitor_score": comp_s,
            "competitor_page_status": comp_page.get("status"),
            "delta": round(s - comp_s, 1) if s is not None and comp_s is not None else None,
            "competitor_results": comp_results,
        }

    (args.out / "results.json").write_text(json.dumps(payload, indent=2))

    # ---- free-tier console summary (score + headline only) ----
    print(f"\n  AGENT READINESS SCORE: {s}/100" if s is not None else "\n  SCORE: n/a")
    print(f"  {payload['headline']}")
    counts = {}
    for r in results:
        counts[r.get("verdict")] = counts.get(r.get("verdict"), 0) + 1
    print(f"  checks: {counts}")
    loss = impact_est["estimated_monthly_loss"]
    print(f"  est. monthly revenue at risk: ${loss['low']:,} - ${loss['high']:,}")
    if args.compare and "comparison" in payload:
        comp = payload["comparison"]
        delta = comp["delta"]
        arrow = "ahead" if delta and delta > 0 else "behind"
        print(f"  vs competitor: {comp['competitor_score']}/100 "
              f"(you are {abs(delta)} pts {arrow})" if delta else "")
    print(f"  full per-check report -> {args.out/'results.json'} (paid deliverable)\n")


if __name__ == "__main__":
    main()
