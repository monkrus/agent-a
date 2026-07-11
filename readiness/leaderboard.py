#!/usr/bin/env python3
"""
leaderboard.py — Generate leaderboard from all stored scans.

Usage:
  python -m readiness.leaderboard

Output (saved to leaderboard/):
  - leaderboard.md — markdown table (rank, domain, score, top weakness)
  - leaderboard.png — 1600x900 chart
"""
from __future__ import annotations

import json
import pathlib
import sys

SCANS_DIR = pathlib.Path(__file__).resolve().parent / ".scans"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "leaderboard"

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}

LAYER_MAP = {
    "shopper": "Extraction",
    "browser": "Interaction",
}
CAT_LAYER = {
    "security": "Security",
    "agent-interaction": "Interaction",
    "variant-interaction": "Interaction",
}


def _domain(url):
    from urllib.parse import urlparse
    h = urlparse(url).hostname or url
    return h[4:] if h.startswith("www.") else h


def _top_weakness_category(results):
    """Find the weakest layer for this scan."""
    layers = {}
    for r in results:
        cat = r.get("category", "")
        ctype = r.get("type", "")
        layer = LAYER_MAP.get(ctype, CAT_LAYER.get(cat, "Data"))
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        if layer not in layers:
            layers[layer] = {"num": 0.0, "den": 0.0}
        layers[layer]["num"] += w * pf
        layers[layer]["den"] += w

    if not layers:
        return "Unknown"
    scored = {k: v["num"] / v["den"] if v["den"] else 0 for k, v in layers.items()}
    worst = min(scored, key=scored.get)
    if scored[worst] >= 1.0:
        return "—"
    return worst


def load_all_scans():
    """Load all scans, deduplicate by domain (keep latest)."""
    if not SCANS_DIR.exists():
        return []
    scans = []
    for f in sorted(SCANS_DIR.glob("*.json")):
        if f.name.endswith("_og.png"):
            continue
        try:
            data = json.loads(f.read_text())
            if "readiness_score" in data and data["readiness_score"] is not None:
                scans.append(data)
        except (json.JSONDecodeError, KeyError, PermissionError, OSError):
            continue

    # Deduplicate by domain, keep latest
    by_domain = {}
    for s in scans:
        domain = _domain(s.get("meta", {}).get("target", ""))
        ts = s.get("meta", {}).get("timestamp", "")
        if domain not in by_domain or ts > by_domain[domain].get("meta", {}).get("timestamp", ""):
            by_domain[domain] = s

    return list(by_domain.values())


def generate_markdown(scans):
    """Generate markdown leaderboard table."""
    entries = []
    for s in scans:
        domain = _domain(s.get("meta", {}).get("target", ""))
        score = s.get("readiness_score")
        results = s.get("results", [])
        weakness = _top_weakness_category(results)
        entries.append({"domain": domain, "score": score, "weakness": weakness})

    entries.sort(key=lambda e: e["score"] or 0, reverse=True)

    lines = ["# AI Agent Readiness Leaderboard", "",
             f"Generated from {len(entries)} scans.", "",
             "| Rank | Domain | Score | Top Weakness |",
             "|------|--------|-------|-------------|"]

    for i, e in enumerate(entries, 1):
        lines.append(f"| {i} | {e['domain']} | {e['score']}/100 | {e['weakness']} |")

    return "\n".join(lines) + "\n"


def generate_chart(scans, output_path):
    """Generate 1600x900 leaderboard chart PNG."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Warning: Pillow not installed, skipping chart generation")
        return False

    entries = []
    for s in scans:
        domain = _domain(s.get("meta", {}).get("target", ""))
        score = s.get("readiness_score", 0) or 0
        entries.append({"domain": domain, "score": score})
    entries.sort(key=lambda e: e["score"], reverse=True)

    W, H = 1600, 900
    BG = (10, 10, 15)
    SURFACE = (20, 20, 25)
    BORDER = (35, 35, 45)
    TEXT = (228, 228, 231)
    MUTED = (139, 139, 150)
    GREEN = (34, 197, 94)
    YELLOW = (234, 179, 8)
    RED = (239, 68, 68)
    ACCENT = (99, 102, 241)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Fonts
    def _font(size):
        for name in ("arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf",
                      "C:/Windows/Fonts/segoeuib.ttf",
                      "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _font_reg(size):
        for name in ("arial.ttf", "C:/Windows/Fonts/arial.ttf",
                      "C:/Windows/Fonts/segoeui.ttf",
                      "DejaVuSans.ttf"):
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
    draw.text((60, 35), "AI Agent Readiness Leaderboard", fill=TEXT, font=font_title)
    draw.text((60, 80), f"{len(entries)} Shopify stores scored  |  How well can AI agents shop here?",
              fill=MUTED, font=font_subtitle)

    # Bars
    margin_left = 60
    margin_right = 100
    bar_area_top = 130
    max_bars = min(len(entries), 25)
    bar_h = max(16, min(28, (H - bar_area_top - 80) // max_bars - 6))
    bar_gap = 4
    max_domain_w = 220
    bar_start_x = margin_left + max_domain_w + 20
    bar_max_w = W - bar_start_x - margin_right

    for i, e in enumerate(entries[:max_bars]):
        y = bar_area_top + i * (bar_h + bar_gap)
        domain = e["domain"]
        score = e["score"]

        # Truncate domain if too long
        if len(domain) > 28:
            domain = domain[:25] + "..."

        # Domain label
        draw.text((margin_left, y + 2), domain, fill=TEXT, font=font_domain)

        # Bar
        bar_w = max(4, int(bar_max_w * score / 100))
        if score >= 80:
            color = GREEN
        elif score >= 50:
            color = YELLOW
        else:
            color = RED

        draw.rounded_rectangle([bar_start_x, y, bar_start_x + bar_w, y + bar_h],
                               radius=3, fill=color)

        # Score label
        draw.text((bar_start_x + bar_w + 10, y + 2), f"{int(score)}",
                  fill=MUTED, font=font_score)

    # Footer
    draw.line([(60, H - 50), (W - 60, H - 50)], fill=BORDER, width=1)
    draw.text((60, H - 40), "agent-a  |  agent-accessibility scanner  |  Scan your store free",
              fill=MUTED, font=font_footer)

    img.save(output_path, format="PNG")
    return True


def main():
    scans = load_all_scans()
    if not scans:
        print("No scans found in .scans/ directory.")
        sys.exit(1)

    print(f"Found {len(scans)} unique domain scans.")

    OUT_DIR.mkdir(exist_ok=True)

    # Markdown
    md = generate_markdown(scans)
    md_path = OUT_DIR / "leaderboard.md"
    md_path.write_text(md)
    print(f"Wrote {md_path}")

    # Chart
    png_path = OUT_DIR / "leaderboard.png"
    if generate_chart(scans, str(png_path)):
        print(f"Wrote {png_path}")
    else:
        print("Chart skipped (install Pillow for PNG generation)")


if __name__ == "__main__":
    main()
