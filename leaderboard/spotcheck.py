#!/usr/bin/env python3
"""
spotcheck.py — Independent spot-check of leaderboard brands.

Uses plain requests (NOT the scanner pipeline) to fetch raw HTML
and extract evidence for/against each scanner finding.
"""
import re
import html
import requests
import pathlib
import textwrap

OUT_DIR = pathlib.Path(__file__).resolve().parent / "post-assets"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 20

BRANDS = {
    "skims": "https://skims.com/products/everyday-cotton-ultimate-teardrop-push-up-bra-sienna-heather",
    "olaplex": "https://olaplex.com/products/the-pro-healthy-hair-discovery-set",
    "kyliecosmetics": "https://kyliecosmetics.com/products/compact-mirror",
    "awaytravel": "https://awaytravel.com/products/celebration-bundle",
}


def strip_tags_visible(raw_html):
    """Extract visible text from HTML, stripping scripts/styles/tags."""
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # Remove all tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def count_script_bytes(raw_html):
    """Count bytes inside <script> tags."""
    scripts = re.findall(r'<script[^>]*>.*?</script>', raw_html, flags=re.DOTALL | re.IGNORECASE)
    return sum(len(s.encode('utf-8', errors='replace')) for s in scripts), len(scripts)


def find_jsonld(raw_html):
    """Find all application/ld+json blocks with surrounding context."""
    matches = []
    lines = raw_html.splitlines()
    for i, line in enumerate(lines):
        if 'application/ld+json' in line.lower():
            start = max(0, i - 1)
            # Find the closing </script> tag
            end = i + 1
            for j in range(i, min(len(lines), i + 100)):
                if '</script>' in lines[j].lower() and j > i:
                    end = j + 1
                    break
                elif j == i and '</script>' in lines[j].lower():
                    # Same line
                    end = j + 1
                    break
            end = min(end + 1, len(lines))
            context = lines[start:end]
            matches.append((i + 1, context))
    return matches


def find_head_block(raw_html, max_lines=60):
    """Extract the <head> block."""
    m = re.search(r'<head[^>]*>(.*?)</head>', raw_html, flags=re.DOTALL | re.IGNORECASE)
    if m:
        head = m.group(0)
        head_lines = head.splitlines()
        if len(head_lines) > max_lines:
            return head_lines[:max_lines] + [f"... ({len(head_lines) - max_lines} more lines)"]
        return head_lines
    return ["<head> block not found"]


def grep_patterns(raw_html, patterns, context_lines=2):
    """Search for patterns in HTML, return matches with context."""
    lines = raw_html.splitlines()
    results = []
    for pat_name, pat in patterns:
        found = []
        for i, line in enumerate(lines):
            if re.search(pat, line, re.IGNORECASE):
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                ctx = [(j + 1, lines[j]) for j in range(start, end)]
                found.append(ctx)
        results.append((pat_name, found))
    return results


def fetch_page(url):
    """Fetch raw HTML, return (status, html, error)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.text, None
    except requests.RequestException as e:
        return None, None, str(e)


def check_bot_block(status, raw_html):
    """Check if the response looks like a bot-block/challenge page."""
    if status and status in (403, 429, 503):
        return True
    if raw_html and len(raw_html) < 5000:
        lower = raw_html.lower()
        if any(x in lower for x in ['captcha', 'challenge', 'verify you are human',
                                      'access denied', 'cloudflare', 'just a moment']):
            return True
    return False


def generate_spotcheck(brand, url):
    """Run independent spot-check for one brand. Returns markdown string."""
    lines = []
    lines.append(f"# Independent Spot-Check — {brand}")
    lines.append("")
    lines.append(f"**URL:** `{url}`")
    lines.append(f"**Method:** Plain `requests.get()` with Chrome User-Agent (no JS execution)")
    lines.append(f"**Code path:** Completely independent of scanner's fetch.py/scorers.py")
    lines.append("")

    status, raw_html, error = fetch_page(url)

    if error:
        lines.append(f"## FETCH ERROR")
        lines.append(f"```")
        lines.append(f"{error}")
        lines.append(f"```")
        lines.append("")
        lines.append("Cannot produce evidence — fetch failed.")
        return "\n".join(lines), []

    lines.append(f"## 1. Fetch Summary")
    lines.append(f"- HTTP status: **{status}**")

    blocked = check_bot_block(status, raw_html)
    if blocked:
        lines.append(f"- **BOT-BLOCKED**: Response appears to be a challenge/block page.")
        lines.append(f"- HTML size: {len(raw_html)} bytes")
        lines.append(f"- First 500 chars:")
        lines.append(f"```")
        lines.append(raw_html[:500])
        lines.append(f"```")
        lines.append("")
        lines.append("**A blocked fetch is NOT evidence for or against any finding.**")
        return "\n".join(lines), []

    html_bytes = len(raw_html.encode('utf-8', errors='replace'))
    script_bytes, script_count = count_script_bytes(raw_html)
    visible_lines = strip_tags_visible(raw_html)
    visible_text = "\n".join(visible_lines)
    visible_bytes = len(visible_text.encode('utf-8', errors='replace'))
    script_pct = round(100 * script_bytes / html_bytes, 1) if html_bytes else 0
    visible_pct = round(100 * visible_bytes / html_bytes, 1) if html_bytes else 0

    lines.append(f"- Total HTML size: **{html_bytes:,} bytes**")
    lines.append(f"- Script tags: **{script_count}** ({script_bytes:,} bytes, **{script_pct}%** of page)")
    lines.append(f"- Visible text (tags/scripts stripped): **{visible_bytes:,} bytes** ({visible_pct}% of page)")
    lines.append(f"- Visible text lines: **{len(visible_lines)}**")
    lines.append("")

    # --- Evidence extraction ---
    findings = []

    # JSON-LD check
    lines.append("## 2. JSON-LD (application/ld+json)")
    jsonld_matches = find_jsonld(raw_html)
    if jsonld_matches:
        lines.append(f"**Found {len(jsonld_matches)} JSON-LD block(s):**")
        for line_num, ctx in jsonld_matches:
            lines.append(f"")
            lines.append(f"Starting at line {line_num}:")
            lines.append("```html")
            for cl in ctx:
                # Truncate very long lines
                if len(cl) > 500:
                    lines.append(cl[:500] + "...")
                else:
                    lines.append(cl)
            lines.append("```")
        findings.append(("JSON-LD present", True, len(jsonld_matches)))
    else:
        lines.append("**Zero matches for `application/ld+json`.**")
        lines.append("")
        lines.append("First 40 lines of `<head>` block for manual inspection:")
        lines.append("```html")
        head = find_head_block(raw_html, max_lines=40)
        for hl in head:
            if len(hl) > 300:
                lines.append(hl[:300] + "...")
            else:
                lines.append(hl)
        lines.append("```")
        findings.append(("JSON-LD present", False, 0))
    lines.append("")

    # Visible text — first 30 lines
    lines.append("## 3. Visible Text (first 30 lines after stripping tags/scripts)")
    lines.append("```")
    for vl in visible_lines[:30]:
        lines.append(vl[:200])
    lines.append("```")
    if len(visible_lines) > 30:
        lines.append(f"... ({len(visible_lines) - 30} more lines)")
    lines.append("")

    substantive_lines = [l for l in visible_lines if len(l) > 30 and not l.startswith('{')]
    lines.append(f"**Substantive text lines (>30 chars, non-JSON):** {len(substantive_lines)}")
    lines.append("")

    # Semantic variant selectors
    lines.append("## 4. Semantic Variant Selectors")
    variant_patterns = [
        ("<select", r'<select[\s>]'),
        ("input type=radio", r'<input[^>]+type=["\']?radio'),
        ("size/color option", r'<option[^>]*>(.*?(size|color|small|medium|large|S|M|L|XL|XXL).*?)</option>'),
        ("fieldset (variants)", r'<fieldset'),
    ]
    variant_results = grep_patterns(raw_html, variant_patterns, context_lines=1)
    any_variant = False
    for pat_name, matches in variant_results:
        if matches:
            any_variant = True
            lines.append(f"**`{pat_name}`**: {len(matches)} match(es)")
            for ctx in matches[:3]:  # Show max 3
                lines.append("```html")
                for ln, content in ctx:
                    c = content if len(content) < 300 else content[:300] + "..."
                    lines.append(f"  L{ln}: {c}")
                lines.append("```")
        else:
            lines.append(f"**`{pat_name}`**: 0 matches")
    lines.append("")
    findings.append(("Semantic variant selectors", any_variant, sum(len(m) for _, m in variant_results)))

    # Return/refund policy links
    lines.append("## 5. Return/Refund Policy Links")
    policy_patterns = [
        ("return/refund in link text", r'>[^<]*(return|refund|exchange)[^<]*</a>'),
        ("return/refund in href", r'href="[^"]*(?:return|refund|exchange)[^"]*"'),
        ("policy link", r'href="[^"]*policy[^"]*"'),
    ]
    policy_results = grep_patterns(raw_html, policy_patterns, context_lines=1)
    any_policy = False
    for pat_name, matches in policy_results:
        if matches:
            any_policy = True
            lines.append(f"**`{pat_name}`**: {len(matches)} match(es)")
            for ctx in matches[:3]:
                lines.append("```html")
                for ln, content in ctx:
                    c = content if len(content) < 300 else content[:300] + "..."
                    lines.append(f"  L{ln}: {c}")
                lines.append("```")
        else:
            lines.append(f"**`{pat_name}`**: 0 matches")
    lines.append("")
    findings.append(("Return/refund policy link", any_policy, sum(len(m) for _, m in policy_results)))

    # Add-to-Cart markup
    lines.append("## 6. Add-to-Cart Markup")
    atc_patterns = [
        ("add-to-cart / Add to Cart", r'(?i)add[- _]?to[- _]?cart'),
        ("AddToCart", r'AddToCart'),
        ("add-to-bag / Add to Bag", r'(?i)add[- _]?to[- _]?bag'),
        ("form action /cart", r'<form[^>]*action="[^"]*cart[^"]*"'),
    ]
    atc_results = grep_patterns(raw_html, atc_patterns, context_lines=1)
    any_atc = False
    for pat_name, matches in atc_results:
        if matches:
            any_atc = True
            lines.append(f"**`{pat_name}`**: {len(matches)} match(es)")
            for ctx in matches[:5]:
                lines.append("```html")
                for ln, content in ctx:
                    c = content if len(content) < 300 else content[:300] + "..."
                    lines.append(f"  L{ln}: {c}")
                lines.append("```")
        else:
            lines.append(f"**`{pat_name}`**: 0 matches")
    lines.append("")
    findings.append(("Add-to-Cart markup", any_atc, sum(len(m) for _, m in atc_results)))

    return "\n".join(lines), findings


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for brand, url in BRANDS.items():
        print(f"Fetching {brand} ({url})...")
        md, findings = generate_spotcheck(brand, url)

        # Write spotcheck file
        out_path = OUT_DIR / f"spotcheck-{brand}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"  Wrote {out_path}")

        for name, present, count in findings:
            summary_rows.append((brand, name, present, count))

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for brand, name, present, count in summary_rows:
        status = f"FOUND ({count})" if present else "NOT FOUND"
        print(f"  {brand:20s} | {name:30s} | {status}")


if __name__ == "__main__":
    main()
