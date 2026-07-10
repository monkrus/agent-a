#!/usr/bin/env python3
"""
Verify candidate DTC Shopify stores for outreach campaign.
Checks: homepage live, product page exists, Shopify detection, product count estimate, contact path.
"""
import csv
import json
import re
import sys
import time
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
TIMEOUT = 15

# Already contacted — exclude
EXCLUDE = {
    "allbirds.com", "caraway.com", "carawayhome.com", "ridgewallet.com",
    "ourplace.com", "fellowproducts.com", "rhone.com", "lovevery.com",
    "hexclad.com", "ruggable.com", "ritual.com", "brooklinen.com",
    "glossier.com", "parachutehome.com", "drinkolipop.com", "mejuri.com",
    "bombas.com",
}

CANDIDATES = [
    # (domain, category, source)
    # Apparel (8 max)
    ("cutsclothing.com", "apparel", "fudge.ai best Shopify stores 2026"),
    ("vuoriclothing.com", "apparel", "fudge.ai best Shopify stores 2026"),
    ("cuyana.com", "apparel", "fudge.ai best Shopify stores 2026"),
    ("meundies.com", "apparel", "fudge.ai best Shopify stores 2026"),
    ("tentree.com", "apparel", "omnisend top Shopify stores"),
    ("puravidabracelets.com", "apparel", "omnisend top Shopify stores"),
    ("chubbiesshorts.com", "apparel", "DTC brands list"),
    ("marine-layer.com", "apparel", "DTC fashion brands list"),

    # Beauty (8 max)
    ("tatcha.com", "beauty", "fudge.ai best Shopify stores 2026"),
    ("functionofbeauty.com", "beauty", "fudge.ai best Shopify stores 2026"),
    ("dedcool.com", "beauty", "fudge.ai best Shopify stores 2026"),
    ("nativecos.com", "beauty", "fudge.ai best Shopify stores 2026"),
    ("colourpop.com", "beauty", "omnisend top Shopify stores"),
    ("hismile.com", "beauty", "omnisend top Shopify stores"),
    ("kopfragnance.com", "beauty", "DTC beauty brands"),
    ("summerfridays.com", "beauty", "DTC beauty brands list"),

    # Home goods (8 max)
    ("schoolhouse.com", "home goods", "fudge.ai best Shopify stores 2026"),
    ("bollandbranch.com", "home goods", "fudge.ai best Shopify stores 2026"),
    ("burrow.com", "home goods", "DTC home goods list"),
    ("bearaby.com", "home goods", "DTC home goods brands"),
    ("brookliving.com", "home goods", "DTC home brands"),
    ("greats.com", "footwear", "DTC footwear brands"),
    ("koio.co", "footwear", "DTC footwear brands"),
    ("thirdlove.com", "apparel", "DTC brands list"),

    # Supplements/wellness (8 max)
    ("moonjuice.com", "supplements/wellness", "fudge.ai best Shopify stores 2026"),
    ("magicspoon.com", "supplements/wellness", "fudge.ai best Shopify stores 2026"),
    ("transparentlabs.com", "supplements/wellness", "craftberry supplement stores"),
    ("ghostlifestyle.com", "supplements/wellness", "craftberry supplement stores"),
    ("vitalproteins.com", "supplements/wellness", "craftberry supplement stores"),
    ("goli.com", "supplements/wellness", "skailama wellness brands"),
    ("drinkag1.com", "supplements/wellness", "fudge.ai best Shopify stores 2026"),
    ("absolutecollagen.com", "supplements/wellness", "omnisend top Shopify stores"),

    # Outdoor gear (8 max)
    ("bigagnes.com", "outdoor gear", "suttoncommerce hiking stores 2026"),
    ("snowpeak.com", "outdoor gear", "outdoor Shopify brands"),
    ("rumpl.com", "outdoor gear", "DTC outdoor brands"),
    ("cotopaxi.com", "outdoor gear", "DTC outdoor brands"),
    ("outdoorvoices.com", "outdoor gear", "DTC activewear/outdoor brands"),
    ("miir.com", "outdoor gear", "DTC outdoor brands"),

    # Pet (6)
    ("gunnerkennels.com", "pet", "omnisend pet stores 2026"),
    ("ruffwear.com", "pet", "omnisend pet stores 2026"),
    ("zestypaws.com", "pet", "omnisend pet stores 2026"),
    ("barkshop.com", "pet", "DTC pet brands"),
    ("wildone.com", "pet", "DTC pet brands"),
    ("fableforpets.com", "pet", "omnisend pet stores 2026"),

    # Footwear (6)
    ("rothys.com", "footwear", "DTC footwear list"),
    ("birdies.com", "footwear", "DTC footwear list"),
    ("thursdayboots.com", "footwear", "DTC footwear brands"),
    ("vivobarefoot.com", "footwear", "DTC footwear brands"),
    ("nisolo.com", "footwear", "DTC footwear brands"),
    ("atoms.com", "footwear", "fudge.ai best Shopify stores 2026"),
]


def check_domain(domain):
    """Check if a domain is live, on Shopify, and has a reachable product page."""
    result = {
        "domain": domain,
        "live": False,
        "shopify": False,
        "est_products": 0,
        "product_page_ok": False,
        "contact_path": "",
        "sample_product_url": "",
    }

    # 1. Check homepage
    try:
        r = requests.get(f"https://{domain}", headers=HEADERS, timeout=TIMEOUT,
                         allow_redirects=True)
        result["live"] = r.status_code == 200
        html = r.text[:50000]

        # Shopify detection
        if "cdn.shopify.com" in html or "Shopify.theme" in html or "shopify-section" in html:
            result["shopify"] = True
        if "myshopify.com" in r.url:
            result["shopify"] = True
    except Exception as e:
        print(f"  Homepage error: {e}")
        return result

    if not result["live"]:
        return result

    # 2. Try products.json for Shopify product count
    try:
        r2 = requests.get(f"https://{domain}/products.json?limit=250",
                          headers=HEADERS, timeout=TIMEOUT)
        if r2.status_code == 200:
            data = r2.json()
            products = data.get("products", [])
            result["est_products"] = len(products)
            result["shopify"] = True  # products.json confirms Shopify

            # Get a sample product URL
            if products:
                handle = products[0].get("handle", "")
                if handle:
                    result["sample_product_url"] = f"https://{domain}/products/{handle}"
    except Exception:
        pass

    # 3. If no sample product yet, try to find one from HTML
    if not result["sample_product_url"]:
        matches = re.findall(r'href="(/products/[^"?#]+)"', html)
        if matches:
            result["sample_product_url"] = f"https://{domain}{matches[0]}"

    # 4. Check sample product page
    if result["sample_product_url"]:
        try:
            r3 = requests.get(result["sample_product_url"], headers=HEADERS,
                              timeout=TIMEOUT)
            result["product_page_ok"] = r3.status_code == 200
        except Exception:
            pass

    # 5. Check for contact path
    try:
        for path in ("/pages/contact", "/pages/contact-us", "/contact"):
            r4 = requests.get(f"https://{domain}{path}", headers=HEADERS,
                              timeout=TIMEOUT, allow_redirects=True)
            if r4.status_code == 200 and len(r4.text) > 500:
                result["contact_path"] = f"contact page ({path})"
                break
        if not result["contact_path"]:
            # Check for email in footer
            emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', html[:100000])
            emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif'))]
            if emails:
                result["contact_path"] = f"email on site ({emails[0]})"
            else:
                result["contact_path"] = "website (no direct email found)"
    except Exception:
        result["contact_path"] = "website"

    return result


def main():
    today = "2026-07-10"
    verified = []
    skipped = []

    for domain, category, source in CANDIDATES:
        if domain in EXCLUDE:
            print(f"SKIP (already contacted): {domain}")
            skipped.append(domain)
            continue

        print(f"Checking {domain}...", end=" ", flush=True)
        info = check_domain(domain)

        if not info["live"]:
            print("DEAD")
            continue
        if not info["shopify"]:
            print(f"NOT SHOPIFY (live but no Shopify signals)")
            # Still include with platform noted
            info["platform"] = "non-Shopify"
        else:
            info["platform"] = "Shopify"

        if info["est_products"] < 5 and info["est_products"] > 0:
            print(f"TOO SMALL ({info['est_products']} products)")
            continue

        status = "OK" if info["product_page_ok"] else "no product page"
        print(f"{info['platform']} | ~{info['est_products']} products | {status}")

        verified.append({
            "domain": domain,
            "platform": info["platform"],
            "est_product_count": info["est_products"] if info["est_products"] > 0 else "unknown",
            "category": category,
            "contact_path": info["contact_path"],
            "source_of_discovery": source,
            "verified_date": today,
            "product_page_ok": info["product_page_ok"],
            "sample_product": info["sample_product_url"],
        })

        time.sleep(1)  # polite rate limiting

    # Write CSV
    csv_path = "candidates.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "domain", "platform", "est_product_count", "category",
            "contact_path", "source_of_discovery", "verified_date"
        ])
        writer.writeheader()
        for v in verified:
            writer.writerow({k: v[k] for k in writer.fieldnames})

    print(f"\n{'='*60}")
    print(f"Verified: {len(verified)} candidates")
    print(f"Written to: {csv_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
