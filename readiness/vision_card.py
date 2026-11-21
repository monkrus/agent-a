#!/usr/bin/env python3
"""Generate an X/Twitter card image for the AI Agent Vision Report promo."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 675  # 16:9 for X cards

# Colors from the nina gashi report
BG = "#f5f0ea"
WARM = "#c9a087"
WARM_DEEP = "#8b6c5c"
COLD = "#64748b"
COLD_LIGHT = "#94a3b8"
TEXT = "#1a1a1a"
MUTED = "#6b7280"
GREEN = "#166534"
YELLOW = "#92400e"
RED = "#991b1b"
DIVIDER = "#d9d2c9"
WHITE = "#ffffff"

def _font(size, bold=False):
    """Try system fonts, fall back to default."""
    names = (
        ["arialbd.ttf", "Arial Bold.ttf"] if bold
        else ["arial.ttf", "Arial.ttf"]
    )
    for name in names:
        for d in [
            "C:/Windows/Fonts",
            "/usr/share/fonts/truetype",
            "/System/Library/Fonts",
        ]:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def generate(out_path="vision_card.png"):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Subtle gradient overlay (warm left, cold right)
    for x in range(W):
        r = int(245 - (x / W) * 10)
        g = int(240 - (x / W) * 8)
        b = int(234 - (x / W) * 5)
        for y in range(H):
            draw.point((x, y), fill=(r, g, b))

    # Eyebrow
    font_mono_sm = _font(16)
    eyebrow = "AI  AGENT  VISION  REPORT"
    draw.text((80, 60), eyebrow, fill=COLD_LIGHT, font=font_mono_sm)

    # Main title
    font_title = _font(52, bold=True)
    font_title_light = _font(52)
    draw.text((80, 110), "We tested", fill=TEXT, font=font_title_light)
    draw.text((80, 170), "5 AI platforms.", fill=WARM, font=font_title)
    draw.text((80, 240), "Here's what they see.", fill=TEXT, font=font_title_light)

    # Subtitle
    font_sub = _font(20)
    draw.text((80, 320), "Same question. Five platforms. Very different results.", fill=MUTED, font=font_sub)

    # Platform result pills
    platforms = [
        ("ChatGPT", "17/17", GREEN),
        ("Perplexity", "17/17", GREEN),
        ("Gemini", "16/17", YELLOW),
        ("Copilot", "13/17", YELLOW),
        ("AI Overview", "4/4*", GREEN),
    ]

    font_pill = _font(17, bold=True)
    font_pill_name = _font(16)
    pill_y = 390
    pill_x = 80

    for name, score, color in platforms:
        # Pill background
        pw = 190
        ph = 70
        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pw, pill_y + ph],
            radius=12, fill=WHITE, outline=DIVIDER
        )
        # Dot
        dot_color = {"#166534": "#4ade80", "#92400e": "#fbbf24", "#991b1b": "#f87171"}[color]
        draw.ellipse([pill_x + 15, pill_y + 16, pill_x + 27, pill_y + 28], fill=dot_color)
        # Platform name
        draw.text((pill_x + 35, pill_y + 13), name, fill=TEXT, font=font_pill_name)
        # Score
        draw.text((pill_x + 35, pill_y + 38), score, fill=color, font=font_pill)
        # Label
        font_tiny = _font(11)
        draw.text((pill_x + 85, pill_y + 42), "prices found", fill=MUTED, font=font_tiny)

        pill_x += pw + 14

    # Bottom bar
    draw.rectangle([0, H - 60, W, H], fill=WARM_DEEP)
    font_bottom = _font(16, bold=True)
    font_bottom_light = _font(15)
    draw.text((80, H - 42), "agent-a.up.railway.app", fill="#e8d5c4", font=font_bottom)
    draw.text((W - 380, H - 42), "Custom report for every prospect we approach", fill="#e8d5c4", font=font_bottom_light)

    # "*limited to 4 categories" note
    font_note = _font(12)
    draw.text((80, 475), "* AI Overview tested on 4 service categories only", fill=COLD_LIGHT, font=font_note)

    img.save(out_path, "PNG", quality=95)
    print(f"Saved {out_path} ({W}x{H})")
    return out_path


if __name__ == "__main__":
    generate()
