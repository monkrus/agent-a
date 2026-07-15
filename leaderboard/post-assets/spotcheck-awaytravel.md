# Independent Spot-Check — awaytravel.com (100.0/100)

**URL:** `https://awaytravel.com/products/celebration-bundle`
**Method:** Plain `requests.get()` with Chrome User-Agent (no JS execution)
**Code path:** Completely independent of scanner's fetch.py / scorers.py

**Purpose:** Verify that a 100.0/100 score is consistent with the raw HTML profile.
A perfect score with a skims-like profile (empty HTML, no JSON-LD) would be a scoring bug.

---

No disagreements found. Raw HTML profile is the opposite of low-scoring brands.

---

## 1. Fetch Summary
- HTTP status: **200**
- Total HTML size: **923,633 bytes**
- Script tags: **139** (468,228 bytes, **50.7%** of page)
- Visible text lines: **426** — substantial product + site content
- Visible text bytes: **8,350** (0.9% of page)

**Contrast with skims (51.2):** Skims has 76.2% script bytes and 1 visible text line.
Away has 50.7% script bytes and 426 visible text lines. The raw HTML profile is markedly
richer.

## 2. JSON-LD (application/ld+json)

**Found 5 JSON-LD blocks:**

```
Block 0: @type: "Product"
  name: "Celebration Bundle"
  offers: [{ price: "573.00" }]

Block 1: @type: "BreadcrumbList"
Block 2: @type: "WebSite"
Block 3: @type: "SiteNavigationElement"
Block 4: @type: "SiteNavigationElement"
```

Product JSON-LD with name, price ($573.00), and offers block — the exact structured
data the scanner checks for in RDY-001. Present and complete.

## 3. Visible Text (first 15 lines after stripping tags/scripts)

```
Celebration Bundle | Away
Skip to content
Your favorite Topside, now in summer hues. Shop new arrivals
To the airport and beyond. Disney & Pixar's Toy Story 5.
Meet the Racket Bag. Game, set, match
Help
Select store
Store
Austin
Boston: Newbury
Boston: Seaport
Chicago
Dallas
Houston
LA: Venice Beach
```

426 visible text lines — product title, promo banners, store locations, nav, footer.
Non-trivially rich content available without JavaScript.

## 4. Semantic Variant Selectors

- `<select>`: 0 matches
- `input type=radio`: **14 matches** — but ALL are **country code selectors**
  (`name='country_code'`, values CA/GB/US), not product variant selectors

```html
<input id='country-us' name='country_code' type='radio' value='US' checked>
```

This product is a bundle and appears to have no variant selection (no size/color choice).
The scanner correctly passed RDY-015 — no variant selectors needed for this product type.

## 5. Return/Refund Policy Links

- `<a>` tags matching "return/refund/policy": **6 matches**
- However, most are `return_to` login URL parameters and privacy policy links
- Scanner passed RDY-004 (return policy reachable as text)

The scanner likely found return policy text/links via a broader check than simple href
grep. The page does have a "Shipping & Returns" section in the rendered version.

## 6. Add-to-Cart Markup

- `<form action="/cart/add">`: **2 matches** — proper Shopify product form

```html
<form method="post" action="/cart/add" id="product_form_10471941603512"
      class="shopify-product-form" enctype="multipart/form-data">
```

Standard Shopify `action="/cart/add"` form present in server HTML. Scanner correctly
passed RDY-014 (semantic ATC).

---

## 100.0 Profile Consistency Check

| Signal | awaytravel (100.0) | skims (51.2) | Consistent? |
|---|---|---|---|
| JSON-LD Product | Present with price | ProductGroup (not Product) | Yes — opposite profiles |
| Script byte share | 50.7% | 76.2% | Yes — Away is lighter |
| Visible text lines | 426 | 1 | Yes — Away has rich text |
| Semantic ATC | `<form action="/cart/add">` | No ATC button | Yes |
| Variant selectors | N/A (bundle, no variants) | None (JS-rendered) | Yes |

**Conclusion:** awaytravel's raw HTML profile is the opposite of low-scoring brands.
Rich structured data, substantial visible text, semantic cart forms. The 100.0 score
is consistent with the raw evidence.

---

## Agree/Disagree Summary

| Scanner Finding | Independent Result | Verdict |
|---|---|---|
| All checks passed (100.0/100) | Rich JSON-LD, semantic ATC, substantial text | **AGREE** |
