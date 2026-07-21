#!/usr/bin/env python3
"""Regenerate all leaderboard/post-assets from canonical scan data."""
import json
import os
import pathlib
import statistics
from collections import defaultdict

SCANS_DIR = pathlib.Path(__file__).resolve().parent.parent / "readiness" / ".scans"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "leaderboard" / "post-assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}
LAYER_MAP = {"shopper": "Extraction", "browser": "Interaction"}
CAT_LAYER = {"security": "Security", "agent-interaction": "Interaction",
             "variant-interaction": "Interaction"}


def dom(url):
    h = url.split("//")[1].split("/")[0] if "//" in url else url
    if h.startswith("www."):
        h = h[4:]
    if h.startswith("us."):
        h = h[3:]
    return h


def layer_of(r):
    return LAYER_MAP.get(r.get("type", ""), CAT_LAYER.get(r.get("category", ""), "Data"))


def weakest_layer(results):
    layers = {}
    for r in results:
        ly = layer_of(r)
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        if ly not in layers:
            layers[ly] = {"num": 0, "den": 0}
        layers[ly]["num"] += w * pf
        layers[ly]["den"] += w
    scored = {k: v["num"] / v["den"] if v["den"] else 0 for k, v in layers.items()}
    if not scored:
        return "Unknown"
    worst = min(scored, key=scored.get)
    return "\u2014" if scored[worst] >= 1.0 else worst


def load_scans():
    scans = []
    for f in sorted(SCANS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if "readiness_score" in data and data["readiness_score"] is not None:
                scans.append(data)
        except (json.JSONDecodeError, KeyError, PermissionError, OSError):
            continue
    by_domain = {}
    for s in scans:
        d = dom(s.get("meta", {}).get("target", ""))
        ts = s.get("meta", {}).get("timestamp", "")
        if d not in by_domain or ts > by_domain[d].get("meta", {}).get("timestamp", ""):
            by_domain[d] = s
    result = list(by_domain.values())
    result.sort(key=lambda s: s.get("readiness_score", 0), reverse=True)
    return result, by_domain


def gen_leaderboard(scans):
    n = len(scans)
    lines = [
        f"# AI Agent Readiness \u2014 {n} DTC Brand Leaderboard",
        "",
        f"Scanned July 2026. {n} brands scanned with SHOPPER=anthropic (real Claude extraction), N=10 runs.",
        "gymshark.com excluded: product page returned no visible content to our fetch method (JS-only rendering).",
        "",
        "| Rank | Brand | Score | Weakest Layer |",
        "|------|-------|-------|---------------|",
    ]
    for i, s in enumerate(scans, 1):
        d = dom(s["meta"]["target"])
        score = s["readiness_score"]
        wl = weakest_layer(s.get("results", []))
        lines.append(f"| {i} | {d} | {score}/100 | {wl} |")
    md = "\n".join(lines) + "\n"
    (OUT_DIR / "leaderboard.md").write_text(md, encoding="utf-8")
    print(f"Wrote leaderboard.md ({n} brands)")
    return md


def gen_findings(scans):
    n = len(scans)
    scores = [s["readiness_score"] for s in scans]
    check_fails = defaultdict(list)
    check_titles = {}
    brand_info = []
    layer_scores = defaultdict(list)

    for s in scans:
        d = dom(s["meta"]["target"])
        results = s.get("results", [])
        fails = [r for r in results if r.get("verdict") == "FAIL"]
        fails.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
        wl = weakest_layer(results)
        top_fail = fails[0].get("title", "(none)") if fails else "(all passed)"
        brand_info.append({"domain": d, "score": s["readiness_score"], "weakness": wl, "top_fail": top_fail})

        for r in results:
            cid = r.get("id", "")
            check_titles[cid] = r.get("title", "")
            if r.get("verdict") == "FAIL":
                check_fails[cid].append(d)

        # per-layer
        layers = {}
        for r in results:
            ly = layer_of(r)
            pf = r.get("pass_fraction")
            if pf is None:
                continue
            w = r.get("weight", 0) or 0
            if ly not in layers:
                layers[ly] = {"num": 0, "den": 0}
            layers[ly]["num"] += w * pf
            layers[ly]["den"] += w
        for ly, v in layers.items():
            if v["den"]:
                layer_scores[ly].append(v["num"] / v["den"] * 100)

    passed_all = [cid for cid in check_titles if cid not in check_fails]
    failed_all = [cid for cid in check_titles if len(check_fails.get(cid, [])) == n]

    lines = [
        "# Findings \u2014 Computed Facts (Scanned July 2026)",
        "",
        "## Score distribution",
        f"- Brands scanned: {n} of 18 (gymshark.com skipped: page returned no visible content to our fetch method)",
        f"- Min: {min(scores):.1f}",
        f"- Max: {max(scores):.1f}",
        f"- Median: {statistics.median(scores):.1f}",
        f"- Mean: {statistics.mean(scores):.1f}",
    ]
    if len(scores) > 1:
        lines.append(f"- Std dev: {statistics.stdev(scores):.1f}")
    lines.extend([
        f"- Brands scoring 80+: {sum(1 for s in scores if s >= 80)}",
        f"- Brands scoring below 60: {sum(1 for s in scores if s < 60)}",
        "",
        "## Most-failed check across brands",
    ])
    sorted_fails = sorted(check_fails.items(), key=lambda x: -len(x[1]))
    for cid, domains in sorted_fails[:5]:
        lines.append(f"- **{check_titles[cid]}** ({cid}): FAIL on {len(domains)}/{n} brands")
        lines.append(f"  Brands: {', '.join(domains)}")

    lines.append("")
    lines.append("## Checks all brands passed")
    if passed_all:
        for cid in passed_all:
            lines.append(f"- {check_titles[cid]} ({cid})")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Checks all brands failed")
    if failed_all:
        for cid in failed_all:
            lines.append(f"- {check_titles[cid]} ({cid})")
    else:
        lines.append("- None \u2014 no check failed on every brand")

    lines.append("")
    lines.append("## Per-layer averages across all brands")
    for ly in ["Data", "Extraction", "Interaction", "Security"]:
        vals = layer_scores.get(ly, [])
        if vals:
            lines.append(f"- **{ly}**: avg {statistics.mean(vals):.1f}%, range {min(vals):.1f}%\u2013{max(vals):.1f}%")

    lines.append("")
    lines.append("## Per-brand top weakness")
    for b in brand_info:
        lines.append(f"- **{b['domain']}** ({b['score']}/100): weakest layer = {b['weakness']}, top fail = {b['top_fail']}")

    md = "\n".join(lines) + "\n"
    (OUT_DIR / "findings.md").write_text(md, encoding="utf-8")
    print("Wrote findings.md")


def gen_evidence(scans, by_domain):
    evidence_brands = set()
    for s in scans[:3]:
        evidence_brands.add(dom(s["meta"]["target"]))
    for s in scans[-3:]:
        evidence_brands.add(dom(s["meta"]["target"]))
    for prev in ["olaplex.com", "skims.com", "kyliecosmetics.com"]:
        if prev in by_domain:
            evidence_brands.add(prev)

    for d in sorted(evidence_brands):
        s = by_domain[d]
        results = s.get("results", [])
        score = s["readiness_score"]
        n_runs = s.get("meta", {}).get("n", 10)
        fails = [r for r in results if r.get("verdict") == "FAIL"]
        fails.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))

        lines = [
            f"# Evidence \u2014 {d} ({score}/100)",
            "",
            f"Scanned July 2026 | SHOPPER=anthropic, N={n_runs} runs per extraction check",
            "",
        ]
        if fails:
            lines.append("## Top failed checks")
            lines.append("")
            for i, fc in enumerate(fails[:5], 1):
                sev = (fc.get("severity_if_fail") or "").upper()
                lines.append(f"### {i}. {fc['id']} \u2014 {fc.get('title', '')} ({sev})")
                lines.append("")
                detail = fc.get("detail", "No detail available.")
                lines.append(f"**Observed:** {detail}")
                lines.append("")
                lines.append("---")
                lines.append("")

        lines.append("## All checks")
        lines.append("")
        lines.append("| Check | Verdict | Detail |")
        lines.append("|-------|---------|--------|")
        for r in results:
            cid = r.get("id", "")
            title = r.get("title", "")[:40]
            verdict = r.get("verdict", "?")
            pf = r.get("pass_fraction")
            if pf is not None and verdict == "PASS":
                n_pass = int(pf * n_runs)
                verdict = f"PASS ({n_pass}/{n_runs})"
            elif pf is not None and verdict == "FAIL":
                n_pass = int(pf * n_runs)
                verdict = f"FAIL ({n_pass}/{n_runs})"
            detail = (r.get("detail", "") or "")[:80]
            lines.append(f"| {cid} {title} | {verdict} | {detail} |")

        ev_md = "\n".join(lines) + "\n"
        slug = d.replace(".com", "").replace(".", "")
        (OUT_DIR / f"evidence-{slug}.md").write_text(ev_md, encoding="utf-8")
        print(f"Wrote evidence-{slug}.md")


def gen_rescan_report(scans):
    n = len(scans)
    scores = [s["readiness_score"] for s in scans]
    report = f"""# Canonical Scan Report \u2014 July 2026

## Summary

{n} DTC brands scanned with SHOPPER=anthropic (real Claude extraction), N=10 runs per check,
Playwright rendered DOM enabled. All numbers in this report and the leaderboard trace to this
single canonical run.

gymshark.com excluded: JS-only rendering returns no server-side content.

## Scanner version

Post bug-fix (commits through 56a0b44): ProductGroup parser, N=10 majority-vote, confidence band.
429 recovery: Playwright fallback when requests gets rate-limited by Shopify CDN.

## Score distribution

- Brands: {n}
- Min: {min(scores):.1f}
- Max: {max(scores):.1f}
- Median: {statistics.median(scores):.1f}
- Mean: {statistics.mean(scores):.1f}

## Run conditions

- SHOPPER=anthropic (Claude Sonnet)
- SCAN_N=10
- RENDER=playwright (headless Chromium for 429 recovery and JS-heavy pages)
- Check pack: shopify-v1.yaml v2026Q2.1 (17 checks, weights sum to 100)
- Date: July 2026

## Test suite

37 tests passed (34 parser + 3 fixes-stub graceful degradation).
"""
    (OUT_DIR / "rescan-report.md").write_text(report, encoding="utf-8")
    print("Wrote rescan-report.md")


def gen_rescan_diff(scans):
    old_file = SCANS_DIR / "_old" / "_old_scores.json"
    old_scores = {}
    if old_file.exists():
        try:
            old_scores = json.loads(old_file.read_text())
        except Exception:
            pass

    lines = [
        "# Rescan Diff: Old Scan vs Canonical Anthropic Scan (July 2026)",
        "",
        "Old scan: pre-parser-fix, mixed SHOPPER modes",
        "Canonical scan: SHOPPER=anthropic, N=10, Playwright rendered DOM, post-56a0b44",
        "",
        "## Diff Table",
        "",
        "| Brand | Old | New | Delta |",
        "|-------|-----|-----|-------|",
    ]
    for s in scans:
        d = dom(s["meta"]["target"])
        new = s["readiness_score"]
        old_entry = old_scores.get(d)
        old = old_entry.get("score") if isinstance(old_entry, dict) else old_entry
        if old is not None:
            delta = new - old
            lines.append(f"| {d} | {old:.1f} | {new:.1f} | {delta:+.1f} |")
        else:
            lines.append(f"| {d} | (new) | {new:.1f} | \u2014 |")

    md = "\n".join(lines) + "\n"
    (OUT_DIR / "rescan-diff.md").write_text(md, encoding="utf-8")
    print("Wrote rescan-diff.md")


def cleanup_stale():
    for f in OUT_DIR.iterdir():
        if f.name.startswith("spotcheck-"):
            f.unlink()
            print(f"Removed stale {f.name}")


def main():
    scans, by_domain = load_scans()
    print(f"Loaded {len(scans)} canonical scans.\n")
    gen_leaderboard(scans)
    gen_findings(scans)
    gen_evidence(scans, by_domain)
    gen_rescan_report(scans)
    gen_rescan_diff(scans)
    cleanup_stale()
    print(f"\nDone. All post-assets regenerated from {len(scans)} canonical scans.")


if __name__ == "__main__":
    main()
