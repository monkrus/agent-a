#!/usr/bin/env python3
"""
og_image.py — Generate OG images (1200x630) for shareable scan results.

Dark background, clean type, score + domain + category bars.
Matches the app's aesthetic: --bg: #0a0a0f, --accent: #6366f1.

Uses Pillow (PIL). Falls back gracefully if not installed.
"""
from __future__ import annotations

import io
import pathlib
from typing import Optional

SCANS_DIR = pathlib.Path(__file__).resolve().parent / ".scans"


def _get_font(size):
    """Get a font, falling back to default if custom fonts unavailable."""
    from PIL import ImageFont
    # Try common system fonts
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf",
                 "C:/Windows/Fonts/segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _get_bold_font(size):
    from PIL import ImageFont
    for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf",
                 "C:/Windows/Fonts/segoeuib.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return _get_font(size)


def _score_color(score):
    """Return RGB color based on score."""
    if score is None:
        return (139, 139, 150)
    if score >= 80:
        return (34, 197, 94)   # green
    if score >= 50:
        return (234, 179, 8)   # yellow
    return (239, 68, 68)       # red


def _category_scores(results):
    """Compute per-category pass fractions from scan results."""
    cats = {}
    for r in results:
        cat = r.get("category", "other")
        pf = r.get("pass_fraction")
        if pf is None:
            continue
        w = r.get("weight", 0) or 0
        if cat not in cats:
            cats[cat] = {"num": 0.0, "den": 0.0}
        cats[cat]["num"] += w * pf
        cats[cat]["den"] += w
    return {cat: round(v["num"] / v["den"] * 100, 1) if v["den"] else 0
            for cat, v in cats.items()}


# Friendly names for categories
CAT_LABELS = {
    "structured-data": "Structured Data",
    "price-legibility": "Price in HTML",
    "agent-access": "Agent Access",
    "policy-text": "Policy Text",
    "llms-txt": "llms.txt",
    "llms-txt-quality": "llms.txt Quality",
    "jsonld-quality": "JSON-LD Quality",
    "js-render": "JS Rendering",
    "price-extraction": "Price Extraction",
    "availability-extraction": "Availability",
    "identity-extraction": "Product ID",
    "policy-extraction": "Return Policy",
    "shipping-extraction": "Shipping",
    "agent-interaction": "Add to Cart",
    "variant-interaction": "Variant Select",
    "security": "Security",
    "browser-cart": "Cart Flow",
}

LAYER_LABELS = {
    "data": "Data",
    "extraction": "Extraction",
    "interaction": "Interaction",
    "security": "Security",
}


def _layer_scores(results):
    """Compute per-layer (data/extraction/interaction/security) scores."""
    # Map categories to layers
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
    return {layer: round(v["num"] / v["den"] * 100, 1) if v["den"] else 0
            for layer, v in layers.items()}


def generate(scan_data: dict, output_path: Optional[str] = None, date_stamp: str = "") -> bytes:
    """Generate a 1200x630 OG image PNG. Returns bytes."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise ImportError("Pillow is required for OG image generation: pip install Pillow")

    W, H = 1200, 630
    BG = (10, 10, 15)
    SURFACE = (20, 20, 25)
    BORDER = (35, 35, 45)
    TEXT = (228, 228, 231)
    MUTED = (139, 139, 150)
    ACCENT = (99, 102, 241)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_big = _get_bold_font(72)
    font_med = _get_bold_font(28)
    font_sm = _get_font(22)
    font_xs = _get_font(18)
    font_label = _get_bold_font(16)

    score = scan_data.get("readiness_score")
    domain = scan_data.get("meta", {}).get("target", "")
    # Extract just the domain
    from urllib.parse import urlparse
    parsed = urlparse(domain)
    domain_display = parsed.hostname or domain
    if domain_display and domain_display.startswith("www."):
        domain_display = domain_display[4:]

    results = scan_data.get("results", [])

    # --- Score circle area (left side) ---
    cx, cy = 240, 260
    r = 110
    # Draw circle outline
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BORDER, width=4)
    # Draw score arc
    sc = _score_color(score)
    if score is not None:
        arc_angle = int(score / 100 * 360)
        draw.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + arc_angle,
                 fill=sc, width=6)

    # Score text centered in circle
    score_text = str(int(score)) if score is not None else "N/A"
    bbox = draw.textbbox((0, 0), score_text, font=font_big)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2 - 10), score_text, fill=sc, font=font_big)
    # "/100" below
    bbox2 = draw.textbbox((0, 0), "/ 100", font=font_sm)
    tw2 = bbox2[2] - bbox2[0]
    draw.text((cx - tw2 // 2, cy + th // 2 + 5), "/ 100", fill=MUTED, font=font_sm)

    # --- Domain + branding (top) ---
    draw.text((60, 40), domain_display, fill=TEXT, font=font_med)
    draw.text((60, 80), "AI Agent Readiness Score", fill=MUTED, font=font_sm)

    # --- Category bars (right side) ---
    bar_x = 460
    bar_w = 640
    bar_h = 32
    bar_gap = 14
    bar_y_start = 150

    layer_scores = _layer_scores(results)
    layer_order = ["data", "extraction", "interaction", "security"]

    for i, layer in enumerate(layer_order):
        if layer not in layer_scores:
            continue
        ls = layer_scores[layer]
        y = bar_y_start + i * (bar_h + bar_gap + 20)

        label = LAYER_LABELS.get(layer, layer.title())
        pct_text = f"{int(ls)}%"

        # Label
        draw.text((bar_x, y), label, fill=TEXT, font=font_label)
        draw.text((bar_x + bar_w - 50, y), pct_text, fill=MUTED, font=font_label)

        # Bar background
        by = y + 22
        draw.rounded_rectangle([bar_x, by, bar_x + bar_w, by + bar_h],
                               radius=4, fill=SURFACE, outline=BORDER)
        # Bar fill
        fill_w = max(4, int(bar_w * ls / 100))
        color = _score_color(ls)
        draw.rounded_rectangle([bar_x, by, bar_x + fill_w, by + bar_h],
                               radius=4, fill=color)

    # --- Top finding (bottom area) ---
    findings = [r for r in results if r.get("verdict") == "FAIL"]
    if findings:
        worst = findings[0]
        finding_text = f"Top finding: {worst.get('title', '')}"
        if len(finding_text) > 80:
            finding_text = finding_text[:77] + "..."
        draw.text((60, 480), finding_text, fill=MUTED, font=font_xs)

    # --- Footer ---
    draw.line([(60, 560), (W - 60, 560)], fill=BORDER, width=1)
    footer_left = f"agent-a  |  agent-accessibility scanner  |  {date_stamp}" if date_stamp else "agent-a  |  agent-accessibility scanner"
    draw.text((60, 575), footer_left, fill=MUTED, font=font_xs)
    draw.text((W - 260, 575), "Scan your store free", fill=ACCENT, font=font_xs)

    # Save
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    data = buf.read()

    if output_path:
        pathlib.Path(output_path).write_bytes(data)

    return data


def generate_for_scan(scan_id: str) -> bytes:
    """Load a scan from .scans/ and generate its OG image."""
    import json
    scan_path = SCANS_DIR / f"{scan_id}.json"
    if not scan_path.exists():
        raise FileNotFoundError(f"Scan {scan_id} not found")
    scan_data = json.loads(scan_path.read_text())
    og_path = SCANS_DIR / f"{scan_id}_og.png"
    return generate(scan_data, str(og_path))


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) < 2:
        print("Usage: python og_image.py <scan_id_or_json_path>")
        sys.exit(1)
    arg = sys.argv[1]
    if arg.endswith(".json"):
        data = json.loads(pathlib.Path(arg).read_text())
        generate(data, "og_preview.png")
        print("Wrote og_preview.png")
    else:
        generate_for_scan(arg)
        print(f"Wrote .scans/{arg}_og.png")
