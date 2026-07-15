#!/usr/bin/env python3
"""
generate_post_assets.py — Generate all post assets from tier scan results.

Outputs to leaderboard/post-assets/:
  - leaderboard.md — ranked markdown table
  - leaderboard.png — 1600x900 horizontal bar chart
  - findings.md — computed facts only (no editorializing)
  - <domain>_scorecard.png — OG scorecard PNGs for top 3 brands
"""
from __future__ import annotations

import datetime
import json
import pathlib
import statistics
from urllib.parse import urlparse

SCANS_DIR = pathlib.Path(__file__).resolve().parent.parent / "readiness" / ".scans"
OUT_DIR = pathlib.Path(__file__).resolve().parent / "post-assets"

# The 18 tier domains
TIER_DOMAINS = {
    "gymshark.com", "everlane.com", "untuckit.com", "skims.com",
    "kyliecosmetics.com", "fentybeauty.com", "sundayriley.com", "olaplex.com",
    "harrys.com", "dollarshaveclub.com", "casper.com", "tuftandneedle.com",
    "purple.com", "framebridge.com", "awaytravel.com", "warbyparker.com",
    "liquid-iv.com", "aloyoga.com",
}

# Category info for same-category gap analysis
BRAND_CATEGORIES = {
    "gymshark.com": "apparel",
    "everlane.com": "apparel",
    "untuckit.com": "apparel",
    "skims.com": "apparel",
    "kyliecosmetics.com": "beauty",
    "fentybeauty.com": "beauty",
    "sundayriley.com": "beauty",
    "olaplex.com": "beauty",
    "harrys.com": "grooming",
    "dollarshaveclub.com": "grooming",
    "casper.com": "home goods",
    "tuftandneedle.com": "home goods",
    "purple.com": "home goods",
    "framebridge.com": "home goods",
    "awaytravel.com": "accessories",
    "warbyparker.com": "eyewear",
    "liquid-iv.com": "supplements/wellness",
    "aloyoga.com": "apparel/activewear",
}

LAYER_MAP_TYPE = {"shopper": "Extraction", "browser": "Interaction"}
CAT_LAYER_MAP = {
    "security": "Security",
    "agent-interaction": "Interaction",
    "variant-interaction": "Interaction",
}
LAYER_ORDER = ["Data", "Extraction", "Interaction", "Security"]

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}


def _domain(url):
    h = urlparse(url).hostname or url
    if h.startswith("www."):
        h = h[4:]
    if h.startswith("us."):
        h = h[3:]
    return h


def _layer_for_check(r):
    cat = r.get("category", "")
    ctype = r.get("type", "")
    return LAYER_MAP_TYPE.get(ctype, CAT_LAYER_MAP.get(cat, "Data"))


def _layer_scores(results):
    layers = {}
    for r in results:
        layer = _layer_for_check(r)
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        if layer not in layers:
            layers[layer] = {"num": 0.0, "den": 0.0}
        layers[layer]["num"] += w * pf
        layers[layer]["den"] += w
    return {k: round(v["num"] / v["den"] * 100, 1) if v["den"] else 0
            for k, v in layers.items()}


def _weakest_layer(results):
    ls = _layer_scores(results)
    if not ls:
        return "Unknown"
    worst = min(ls, key=ls.get)
    if ls[worst] >= 100.0:
        return "—"
    return worst


def _top_fail_title(results):
    fails = [r for r in results if r.get("verdict") == "FAIL"]
    fails.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
    return fails[0].get("title", "") if fails else "—"


def _scan_date_stamp(tier):
    """Extract 'Scanned <Month> <Year>' from scan timestamps."""
    timestamps = []
    for s in tier.values():
        ts = s.get("meta", {}).get("timestamp", "")
        if ts:
            timestamps.append(ts)
    if not timestamps:
        return "Scanned date unknown"
    # Use the latest timestamp
    latest = max(timestamps)
    try:
        dt = datetime.datetime.fromisoformat(latest)
        return f"Scanned {dt.strftime('%B %Y')}"
    except ValueError:
        return "Scanned date unknown"


def load_tier_scans():
    """Load scans filtered to tier domains only, deduplicate by domain."""
    tier = {}
    for f in sorted(SCANS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, PermissionError, OSError):
            continue
        target = data.get("meta", {}).get("target", "")
        domain = _domain(target)
        if domain not in TIER_DOMAINS:
            continue
        if data.get("readiness_score") is None:
            continue
        ts = data.get("meta", {}).get("timestamp", "")
        if domain not in tier or ts > tier[domain].get("meta", {}).get("timestamp", ""):
            tier[domain] = data
    return tier


# ---- 1. RANKED MARKDOWN TABLE ----

def generate_markdown(tier):
    date_stamp = _scan_date_stamp(tier)
    entries = []
    for domain, s in tier.items():
        score = s.get("readiness_score", 0)
        results = s.get("results", [])
        weakness = _weakest_layer(results)
        entries.append({"domain": domain, "score": score, "weakness": weakness})
    entries.sort(key=lambda e: e["score"], reverse=True)

    lines = [
        "# AI Agent Readiness — 18 DTC Brand Leaderboard",
        "",
        f"{date_stamp}. {len(entries)} brands scanned with SHOPPER=anthropic (real Claude extraction).",
        "gymshark.com excluded: product page returned no visible content to our fetch method (JS-only rendering).",
        "",
        "| Rank | Brand | Score | Weakest Layer |",
        "|------|-------|-------|---------------|",
    ]
    for i, e in enumerate(entries, 1):
        lines.append(f"| {i} | {e['domain']} | {e['score']}/100 | {e['weakness']} |")

    return "\n".join(lines) + "\n"


# ---- 2. LEADERBOARD PNG (1600x900) ----

def generate_chart(tier, output_path, date_stamp=""):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Warning: Pillow not installed, skipping chart generation")
        return False

    entries = []
    for domain, s in tier.items():
        score = s.get("readiness_score", 0) or 0
        entries.append({"domain": domain, "score": score})
    entries.sort(key=lambda e: e["score"], reverse=True)

    W, H = 1600, 900
    BG = (10, 10, 15)
    BORDER = (35, 35, 45)
    TEXT = (228, 228, 231)
    MUTED = (139, 139, 150)
    GREEN = (34, 197, 94)
    YELLOW = (234, 179, 8)
    RED = (239, 68, 68)
    ACCENT = (99, 102, 241)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    def _font(size):
        for name in ("arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf",
                      "C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _font_reg(size):
        for name in ("arial.ttf", "C:/Windows/Fonts/arial.ttf",
                      "C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    font_title = _font(36)
    font_subtitle = _font_reg(20)
    font_domain = _font_reg(18)
    font_score = _font(18)
    font_footer = _font_reg(16)

    # Title
    draw.text((60, 35), "AI Agent Readiness — 18 DTC Brands", fill=TEXT, font=font_title)
    draw.text((60, 80), "How well can AI shopping agents buy from these stores?  |  Real Claude extraction, 5 runs per check",
              fill=MUTED, font=font_subtitle)

    # Bars
    margin_left = 60
    margin_right = 100
    bar_area_top = 130
    max_bars = len(entries)
    bar_h = max(16, min(30, (H - bar_area_top - 80) // max_bars - 6))
    bar_gap = 4
    max_domain_w = 230
    bar_start_x = margin_left + max_domain_w + 20
    bar_max_w = W - bar_start_x - margin_right

    for i, e in enumerate(entries[:max_bars]):
        y = bar_area_top + i * (bar_h + bar_gap)
        domain = e["domain"]
        score = e["score"]

        if len(domain) > 28:
            domain = domain[:25] + "..."

        draw.text((margin_left, y + 2), domain, fill=TEXT, font=font_domain)

        bar_w = max(4, int(bar_max_w * score / 100))
        if score >= 80:
            color = GREEN
        elif score >= 50:
            color = YELLOW
        else:
            color = RED

        draw.rounded_rectangle([bar_start_x, y, bar_start_x + bar_w, y + bar_h],
                               radius=3, fill=color)
        draw.text((bar_start_x + bar_w + 10, y + 2), f"{int(score)}",
                  fill=MUTED, font=font_score)

    # Footer
    draw.line([(60, H - 50), (W - 60, H - 50)], fill=BORDER, width=1)
    footer_left = f"agent-a  |  agent-accessibility scanner  |  {date_stamp}" if date_stamp else "agent-a  |  agent-accessibility scanner"
    draw.text((60, H - 40), footer_left, fill=MUTED, font=font_footer)

    img.save(output_path, format="PNG")
    return True


# ---- 3. FINDINGS.MD — Computed facts only ----

def generate_findings(tier):
    entries = []
    for domain, s in tier.items():
        score = s.get("readiness_score", 0) or 0
        results = s.get("results", [])
        entries.append({
            "domain": domain,
            "score": score,
            "results": results,
            "category": BRAND_CATEGORIES.get(domain, "unknown"),
        })
    entries.sort(key=lambda e: e["score"], reverse=True)
    scores = [e["score"] for e in entries]

    date_stamp = _scan_date_stamp(tier)
    lines = [f"# Findings — Computed Facts ({date_stamp})", ""]

    # Score distribution
    lines.append("## Score distribution")
    lines.append(f"- Brands scanned: {len(entries)} of 18 (gymshark.com skipped: page returned no visible content to our fetch method)")
    lines.append(f"- Min: {min(scores)}")
    lines.append(f"- Max: {max(scores)}")
    lines.append(f"- Median: {statistics.median(scores)}")
    lines.append(f"- Mean: {round(statistics.mean(scores), 1)}")
    lines.append(f"- Std dev: {round(statistics.stdev(scores), 1)}")
    above_80 = sum(1 for s in scores if s >= 80)
    below_60 = sum(1 for s in scores if s < 60)
    lines.append(f"- Brands scoring 80+: {above_80}")
    lines.append(f"- Brands scoring below 60: {below_60}")
    lines.append("")

    # Most-failed check across brands
    lines.append("## Most-failed check across brands")
    check_fails = {}  # check_id -> {title, count, brands}
    for e in entries:
        for r in e["results"]:
            if r.get("verdict") == "FAIL":
                cid = r.get("id", "")
                title = r.get("title", "")
                if cid not in check_fails:
                    check_fails[cid] = {"title": title, "count": 0, "brands": []}
                check_fails[cid]["count"] += 1
                check_fails[cid]["brands"].append(e["domain"])

    if check_fails:
        sorted_checks = sorted(check_fails.items(), key=lambda x: x[1]["count"], reverse=True)
        for cid, info in sorted_checks[:5]:
            brands_str = ", ".join(info["brands"])
            lines.append(f"- **{info['title']}** ({cid}): FAIL on {info['count']}/{len(entries)} brands")
            lines.append(f"  Brands: {brands_str}")
        lines.append("")

    # Checks that ALL brands passed
    lines.append("## Checks all brands passed")
    all_check_ids = set()
    for e in entries:
        for r in e["results"]:
            all_check_ids.add(r.get("id", ""))

    all_pass = []
    for cid in sorted(all_check_ids):
        if not cid:
            continue
        failed_any = cid in check_fails
        if not failed_any:
            # Find the title
            title = ""
            for e in entries:
                for r in e["results"]:
                    if r.get("id") == cid:
                        title = r.get("title", "")
                        break
                if title:
                    break
            all_pass.append(f"- {title} ({cid})")

    if all_pass:
        for line in all_pass:
            lines.append(line)
    else:
        lines.append("- None — every check had at least one failure")
    lines.append("")

    # Checks that ALL brands failed
    lines.append("## Checks all brands failed")
    all_fail = []
    for cid in sorted(all_check_ids):
        if not cid:
            continue
        if cid not in check_fails:
            continue
        if check_fails[cid]["count"] == len(entries):
            all_fail.append(f"- {check_fails[cid]['title']} ({cid})")
    if all_fail:
        for line in all_fail:
            lines.append(line)
    else:
        lines.append("- None — no check failed on every brand")
    lines.append("")

    # Biggest score gap between same-category brands
    lines.append("## Biggest score gap within same category")
    cat_scores = {}
    for e in entries:
        cat = e["category"]
        if cat not in cat_scores:
            cat_scores[cat] = []
        cat_scores[cat].append((e["domain"], e["score"]))

    biggest_gap = 0
    biggest_gap_info = ""
    for cat, brands in sorted(cat_scores.items()):
        if len(brands) < 2:
            continue
        brands.sort(key=lambda x: x[1], reverse=True)
        gap = brands[0][1] - brands[-1][1]
        lines.append(f"- **{cat}**: {brands[0][0]} ({brands[0][1]}) vs {brands[-1][0]} ({brands[-1][1]}) — gap: {round(gap, 1)} pts")
        if gap > biggest_gap:
            biggest_gap = gap
            biggest_gap_info = f"{cat}: {brands[0][0]} ({brands[0][1]}) vs {brands[-1][0]} ({brands[-1][1]})"

    if biggest_gap_info:
        lines.append(f"- **Biggest gap**: {round(biggest_gap, 1)} pts — {biggest_gap_info}")
    lines.append("")

    # Per-layer averages across all brands
    lines.append("## Per-layer averages across all brands")
    layer_totals = {}
    for e in entries:
        ls = _layer_scores(e["results"])
        for layer, pct in ls.items():
            if layer not in layer_totals:
                layer_totals[layer] = []
            layer_totals[layer].append(pct)
    for layer in LAYER_ORDER:
        if layer in layer_totals:
            vals = layer_totals[layer]
            avg = round(statistics.mean(vals), 1)
            low = min(vals)
            high = max(vals)
            lines.append(f"- **{layer}**: avg {avg}%, range {low}%–{high}%")
    lines.append("")

    # Per-brand top weakness one-liners
    lines.append("## Per-brand top weakness")
    for e in entries:
        weakness = _weakest_layer(e["results"])
        top_fail = _top_fail_title(e["results"])
        lines.append(f"- **{e['domain']}** ({e['score']}/100): weakest layer = {weakness}, top fail = {top_fail}")
    lines.append("")

    return "\n".join(lines)


# ---- 4. OG SCORECARD PNGs for top 3 ----

def generate_scorecard_png(scan_data, output_path, date_stamp=""):
    """Generate a 1200x630 OG scorecard PNG for a single brand."""
    # Reuse og_image.py logic
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "readiness"))
    import og_image
    og_image.generate(scan_data, str(output_path), date_stamp=date_stamp)


# ---- MAIN ----

def main():
    tier = load_tier_scans()
    date_stamp = _scan_date_stamp(tier)
    print(f"Loaded {len(tier)} tier scans (gymshark.com skipped: JS-only)")
    print(f"Date stamp: {date_stamp}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Ranked markdown table
    md = generate_markdown(tier)
    md_path = OUT_DIR / "leaderboard.md"
    md_path.write_text(md)
    print(f"Wrote {md_path}")

    # 2. Leaderboard PNG
    png_path = OUT_DIR / "leaderboard.png"
    if generate_chart(tier, str(png_path), date_stamp=date_stamp):
        print(f"Wrote {png_path}")

    # 3. Findings
    findings = generate_findings(tier)
    findings_path = OUT_DIR / "findings.md"
    findings_path.write_text(findings)
    print(f"Wrote {findings_path}")

    # 4. OG scorecard PNGs for top 3
    ranked = sorted(tier.items(), key=lambda kv: kv[1].get("readiness_score", 0), reverse=True)
    for domain, scan_data in ranked[:3]:
        safe_name = domain.replace(".", "-")
        png_path = OUT_DIR / f"{safe_name}_scorecard.png"
        generate_scorecard_png(scan_data, png_path, date_stamp=date_stamp)
        score = scan_data.get("readiness_score", 0)
        print(f"Wrote {png_path} (score: {score})")

    print(f"\nAll post assets written to {OUT_DIR}")


if __name__ == "__main__":
    main()
