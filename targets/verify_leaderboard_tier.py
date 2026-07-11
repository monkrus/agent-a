#!/usr/bin/env python3
"""
Verify leaderboard-tier candidates: big-name DTC brands for public scoring.
"""
import csv
import json
import re
import time
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
TIMEOUT = 15

# ---- EXCLUSION LISTS ----
CONTACTED = {
    "allbirds.com", "carawayhome.com", "caraway.com", "ridgewallet.com",
    "ourplace.com", "fellowproducts.com", "rhone.com", "lovevery.com",
    "hexclad.com", "ruggable.com", "ritual.com", "brooklinen.com",
    "glossier.com", "parachutehome.com", "drinkolipop.com", "mejuri.com",
    "bombas.com",
}

OUTREACH = set()
try:
    with open("candidates.csv") as f:
        for row in csv.DictReader(f):
            OUTREACH.add(row["domain"].strip())
except FileNotFoundError:
    pass

ALL_EXCLUDED = CONTACTED | OUTREACH

# Some brands have known product URL patterns
KNOWN_PRODUCT_URLS = {
    "warbyparker.com": "https://www.warbyparker.com/eyeglasses/men/durand/whiskey-tortoise",
    "awaytravels.com": "https://www.awaytravels.com/shop/the-carry-on",  # Away luggage
    "away.com": "https://www.away.com/suitcases/carry-on/aluminum-edition",
    "theordinary.com": "https://theordinary.com/en-us/hyaluronic-acid-2-b5-hydrating-serum-100029.html",
    "article.com": "https://www.article.com/product/17144/sven-charme-tan-sofa",
    "saatva.com": "https://www.saatva.com/mattresses/saatva-classic",
    "purple.com": "https://purple.com/mattresses/purple-mattress",
    "dollarshaveclub.com": "https://www.dollarshaveclub.com/our-products/shave/razors/6-blade-razor",
    "huel.com": "https://huel.com/products/huel-powder",
    "manscaped.com": "https://www.manscaped.com/products/the-lawn-mower-5-0-ultra",
    "quip.com": "https://www.getquip.com/store/electric-toothbrush",
    "yeti.com": "https://www.yeti.com/drinkware/bottles/21071502547.html",
    "hydroflask.com": "https://www.hydroflask.com/32-oz-wide-mouth-2-0",
}

CANDIDATES = [
    # Apparel (4)
    ("gymshark.com", "apparel", "Category leader in fitness apparel, $500M+ revenue"),
    ("everlane.com", "apparel", "Radical transparency pioneer, household DTC name"),
    ("untuckit.com", "apparel", "Category-defining men's shirts, retail + DTC"),
    ("skims.com", "apparel", "Kim Kardashian shapewear brand, valued at $4B"),

    # Beauty (4)
    ("kyliecosmetics.com", "beauty", "Kylie Jenner brand, most recognized DTC cosmetics"),
    ("fentybeauty.com", "beauty", "Rihanna's beauty empire, inclusivity pioneer"),
    ("theordinary.com", "beauty", "DECIEM brand, disrupted skincare pricing, cult following"),
    ("harrys.com", "beauty", "Men's razors DTC, acquired for $1.4B"),

    # Home goods (4)
    ("casper.com", "home goods", "Mattress-in-a-box pioneer, IPO'd DTC brand"),
    ("tuftandneedle.com", "home goods", "Mattress DTC, merged with Serta Simmons"),
    ("purple.com", "home goods", "Purple mattress, public company, $500M+ revenue"),
    ("article.com", "home goods", "DTC furniture leader, known for mid-century modern"),

    # Supplements/wellness (4)
    ("huel.com", "supplements/wellness", "Meal replacement DTC, $100M+ revenue, global"),
    ("liquid-iv.com", "supplements/wellness", "Hydration brand, acquired by Unilever"),
    ("dollarshaveclub.com", "supplements/wellness", "Razors DTC pioneer, acquired by Unilever for $1B"),
    ("manscaped.com", "beauty", "Men's grooming DTC, strong brand, IPO'd"),

    # Eyewear/Accessories (2)
    ("warbyparker.com", "eyewear", "DTC poster child, IPO'd, redefined glasses shopping"),
    ("mvmt.com", "accessories", "Watches/sunglasses DTC, acquired by Movado"),

    # Outdoor (2)
    ("yeti.com", "outdoor gear", "Premium coolers/drinkware, $1.6B revenue, public company"),
    ("hydroflask.com", "outdoor gear", "Water bottle category leader, Helen of Troy brand"),

    # Extra picks in case of failures
    ("aloyoga.com", "apparel", "Luxury activewear, massive Instagram presence"),
    ("awaytravel.com", "home goods", "Luggage DTC leader, 'Away' brand"),
    ("quip.com", "beauty", "Electric toothbrush DTC, ubiquitous advertising"),
    ("forhims.com", "supplements/wellness", "Telehealth + wellness DTC, IPO'd"),
    ("framebridge.com", "home goods", "Custom framing DTC, disrupted framing industry"),
]


def get_product_url(domain, html):
    """Find a representative product page URL."""
    # Check known URLs first
    if domain in KNOWN_PRODUCT_URLS:
        return KNOWN_PRODUCT_URLS[domain], "known"

    # Try products.json (Shopify)
    try:
        r = requests.get(f"https://{domain}/products.json?limit=10",
                         headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            products = r.json().get("products", [])
            for p in products:
                variants = p.get("variants", [])
                if variants and variants[0].get("available", True):
                    return f"https://{domain}/products/{p['handle']}", "Shopify"
            if products:
                return f"https://{domain}/products/{products[0]['handle']}", "Shopify"
    except Exception:
        pass

    # Find /products/ links
    matches = re.findall(r'href="(/products/[^"?#]+)"', html)
    product_links = [m for m in matches if "/collections/" not in m and len(m) > 12]
    if product_links:
        return f"https://{domain}{product_links[0]}", "likely Shopify"

    # Find /shop/ or /product/ links (non-Shopify patterns)
    for pat in [r'href="(/shop/[^"?#]+/[^"?#]+)"',
                r'href="(/product/[^"?#]+)"',
                r'href="(/p/[^"?#]+)"',
                r'href="(/store/[^"?#]+)"']:
        matches = re.findall(pat, html)
        if matches:
            return f"https://{domain}{matches[0]}", "non-Shopify"

    return None, "unknown"


def check_domain(domain):
    result = {
        "domain": domain, "live": False, "platform": "unknown",
        "product_url": "", "product_page_ok": False,
    }

    # Try with and without www
    for prefix in [f"https://{domain}", f"https://www.{domain}"]:
        try:
            r = requests.get(prefix, headers=HEADERS, timeout=TIMEOUT,
                             allow_redirects=True)
            if r.status_code == 200:
                result["live"] = True
                html = r.text[:80000]
                # Platform detection
                if "cdn.shopify.com" in html or "Shopify.theme" in html:
                    result["platform"] = "Shopify"
                elif "bigcommerce" in html.lower():
                    result["platform"] = "BigCommerce"
                elif "magento" in html.lower():
                    result["platform"] = "Magento"
                elif "woocommerce" in html.lower():
                    result["platform"] = "WooCommerce"
                else:
                    result["platform"] = "custom/other"
                break
        except Exception:
            continue

    if not result["live"]:
        return result

    product_url, hint = get_product_url(domain, html)
    if hint in ("Shopify", "likely Shopify"):
        result["platform"] = "Shopify"
    if product_url:
        result["product_url"] = product_url
        try:
            r2 = requests.get(product_url, headers=HEADERS, timeout=TIMEOUT,
                              allow_redirects=True)
            result["product_page_ok"] = r2.status_code == 200
        except Exception:
            pass

    return result


def main():
    print("=" * 60)
    print("LEADERBOARD TIER VERIFICATION")
    print("=" * 60)
    print(f"\nExclusion list: {len(ALL_EXCLUDED)} domains")
    print(f"  Contacted: {len(CONTACTED)}")
    print(f"  Outreach: {len(OUTREACH)}")

    verified = []
    overlaps = []
    failed = []
    TARGET = 18

    for domain, category, rationale in CANDIDATES:
        if len(verified) >= TARGET:
            break

        if domain in ALL_EXCLUDED:
            overlaps.append(domain)
            print(f"\n  OVERLAP — SKIP: {domain}")
            continue

        print(f"\n  Checking {domain}...", end=" ", flush=True)
        info = check_domain(domain)

        if not info["live"]:
            print("DEAD/UNREACHABLE")
            failed.append((domain, "unreachable"))
            continue

        if not info["product_url"]:
            print(f"LIVE ({info['platform']}) — no product page found")
            failed.append((domain, "no product page"))
            continue

        if not info["product_page_ok"]:
            print(f"LIVE ({info['platform']}) — product page returned error")
            failed.append((domain, "product page error"))
            continue

        print(f"{info['platform']} | OK")
        print(f"    -> {info['product_url']}")

        verified.append({
            "domain": domain,
            "platform": info["platform"],
            "category": category,
            "product_url": info["product_url"],
            "rationale": rationale,
        })

        time.sleep(1)

    # ---- RESULTS ----
    print(f"\n{'=' * 60}")
    print("OVERLAP CHECK (diff against outreach + contacted):")
    if overlaps:
        for d in overlaps:
            src = []
            if d in CONTACTED: src.append("contacted")
            if d in OUTREACH: src.append("outreach")
            print(f"  EXCLUDED: {d} ({', '.join(src)})")
    else:
        print("  CLEAN — zero overlaps")

    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for d, reason in failed:
            print(f"  {d}: {reason}")

    print(f"\nVERIFIED: {len(verified)} / target {TARGET}")
    print("=" * 60)

    # Category distribution
    cats = {}
    for v in verified:
        cats[v["category"]] = cats.get(v["category"], 0) + 1
    print("\nCategory distribution:")
    for c, n in sorted(cats.items()):
        print(f"  {c}: {n}")

    # Write files
    with open("leaderboard-tier.txt", "w") as f:
        for v in verified:
            f.write(f"{v['product_url']}\n")

    with open("leaderboard-rationale.md", "w") as f:
        f.write("# Leaderboard Tier — Brand Rationale\n\n")
        f.write(f"{len(verified)} big-name DTC brands for public industry analysis.\n")
        f.write("Zero overlap with outreach candidates or previously contacted brands.\n\n")
        cats_seen = {}
        for v in verified:
            cat = v["category"]
            cats_seen[cat] = cats_seen.get(cat, 0) + 1
            f.write(f"- **{v['domain']}** ({v['platform']}, {cat}) — {v['rationale']}\n")
        f.write(f"\n## Category distribution\n")
        for c, n in sorted(cats_seen.items()):
            f.write(f"- {c}: {n}\n")

    print(f"\nWritten: leaderboard-tier.txt, leaderboard-rationale.md")


if __name__ == "__main__":
    main()
