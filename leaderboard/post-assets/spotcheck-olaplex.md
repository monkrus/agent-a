# Independent Spot-Check — olaplex.com (90.4/100)

**URL:** `https://olaplex.com/products/the-pro-healthy-hair-discovery-set`
**Method:** Plain `requests.get()` with Chrome User-Agent (no JS execution)
**Code path:** Completely independent of scanner's fetch.py / scorers.py

---

No disagreements found.

---

## 1. Fetch Summary
- HTTP status: **200**
- Total HTML size: **1,393,908 bytes**
- Script tags: **132** (981,953 bytes, **70.4%** of page)
- Visible text (tags/scripts stripped): **435 lines**
- Visible text includes: product title, promo banners, nav, footer — substantial content

## 2. JSON-LD (application/ld+json)

**Found 2 JSON-LD blocks:**

Block 0: `@type: "Product"`
```
name: "THE HEALTHY HAIR DISCOVERY SET"
offers: present (with price)
```

Block 1: `@type: "FAQPage"`

JSON-LD Product is present and complete. Scanner correctly passed RDY-001 and RDY-012
(JSON-LD quality) for this brand.

## 3. Visible Text (first 15 lines after stripping tags/scripts)

```
The Healthy Hair Discovery Set for Shinier, Healthier Hair - OLAPLEX Inc.
Close
Skip to content
This is an auto-rotating announcements carousel...
Free Summer Travel Set with a $100+ order.  Code: SHINE
Free Shipping on $50+.  Shop Now
New here? Get 15% off your first order.  Sign Up Now
Free complimentary sample with any order.
Update country/region
United States (English)
```

435 visible text lines — substantial nav + promo text.
Scanner reported 70.5% scripts / 1.4% visible text — independent confirms 70.4% scripts.
Note: the scanner's RDY-013 check compared server HTML to Playwright-rendered DOM and found
1,091 more chars in the rendered version. The independent fetch confirms high script ratio
but also shows 435 lines of visible text — the check's "little content" framing is about
product-specific content missing from server HTML, not total text.

## 4. Semantic Variant Selectors

- `<select>`: **4 matches** — all are **locale/market selectors** (`name='market_selector'`),
  NOT product variant selectors
- `input type=radio`: 0 matches
- `<fieldset>`: 0 matches

```html
<select name='market_selector' id='select_sections--...FooterForm-header_locale_code'>
  <option value='en-US'>English</option>
  ...
</select>
```

**Zero product variant selectors.** The 4 `<select>` elements are all locale pickers.
Scanner correctly identified non-semantic variant UI (RDY-015 FAIL).

## 5. Return/Refund Policy Links
- Policy links present in footer nav
- Scanner passed the return policy check (RDY-004) for this brand

## 6. Add-to-Cart Markup
- ATC forms and buttons present in HTML (Shopify standard)
- Scanner passed the ATC checks (RDY-014, RDY-017) for this brand

---

## Agree/Disagree Summary

| Scanner Finding | Independent Result | Verdict |
|---|---|---|
| JS-rendered, 70.5% scripts (RDY-013) | 70.4% scripts, 132 script tags | **AGREE** |
| Non-semantic variant selectors (RDY-015) | 4 `<select>` = locale pickers only, zero variant selectors | **AGREE** |
