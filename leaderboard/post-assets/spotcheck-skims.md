# Independent Spot-Check — skims.com (51.2/100)

**URL:** `https://skims.com/products/everyday-cotton-ultimate-teardrop-push-up-bra-sienna-heather`
**Method:** Plain `requests.get()` with Chrome User-Agent (no JS execution)
**Code path:** Completely independent of scanner's fetch.py / scorers.py

---

## DISAGREEMENT FLAG

**Finding: "No schema.org/Product JSON-LD found" (RDY-001)**

Independent fetch found 3 JSON-LD script blocks. The third is `@type: "ProductGroup"`
containing **35 nested `@type: "Product"` objects** (one per size/color variant), each
with its own `Offer` and price ($64).

Structure:
```
ProductGroup (top-level JSON-LD block)
  └── hasVariant: [
        Product { name: "...30 A", offers: { price: 64 } },
        Product { name: "...30 B", offers: { price: 64 } },
        ... (35 total)
      ]
```

Confirmed via `curl | grep '@type' | sort | uniq -c`: 35 Product, 1 ProductGroup,
35 Offer.

Scanner code (`shopper.py:96`) iterates top-level JSON-LD blocks and checks
`@type == "product"` (case-insensitive). The top-level block is `ProductGroup`,
not `Product`. The 35 `Product` objects are nested inside `hasVariant`, which
the scanner never traverses.

This is a **scanner blind spot** — skims has rich product structured data (35 variants
with prices), but the scanner cannot see it because it doesn't recurse into
`ProductGroup.hasVariant`.

**Impact on score:** RDY-001 (weight 10, critical) and RDY-012 (weight 5, high) both
fail because neither recognizes `ProductGroup`. If both passed, skims' score would increase
by approximately 15 weighted points — from 51.2 to ~66.

**Your call whether to fix the scanner or annotate the finding before publication.**

---

## 1. Fetch Summary
- HTTP status: **200**
- Total HTML size: **1,188,118 bytes**
- Script tags: **30** (905,196 bytes, **76.2%** of page)
- Visible text (tags/scripts stripped): **4,878 bytes** (0.4% of page)
- Visible text lines: **1** (entire page content is one long line of nav + product title)

## 2. JSON-LD (application/ld+json)

**Found 3 JSON-LD script blocks:**

Block 0: `@type: "Organization"` — name "SKIMS", logo URL
Block 1: `@type: "BreadcrumbList"` — Home > Bras > Push-Up Bras > product
Block 2: `@type: "ProductGroup"` — contains 35 nested Product variants with prices

```
@type: "ProductGroup"
brand: { @type: "Brand", name: "SKIMS" }
description: "Our viral solution, reimagined in the softest, premium cotton..."
hasVariant: [
  { @type: "Product", name: "...30 A", offers: { @type: "Offer", price: 64 } },
  { @type: "Product", name: "...30 B", offers: { @type: "Offer", price: 64 } },
  ... (35 total variants, each with price)
]
```

Scanner only checks top-level `@type` — sees `ProductGroup`, not `Product`.
The 35 `Product` objects with prices are nested inside `hasVariant`.

## 3. Visible Text (first 30 lines after stripping tags/scripts)

```
EVERYDAY COTTON ULTIMATE TEARDROP PUSH-UP BRA | SIENNA HEATHER | SKIMS Skip to main
content SKIMS Logo Join SKIMS Rewards for Free Returns Free Shipping on Domestic Orders
$75+ Sign Up for Email & SMS
```

Entire visible text is a single run-on line: product title + nav links + promo text.
No price, no description, no variant options visible as text.

## 4. Semantic Variant Selectors

- `<select>`: 0 matches
- `input type=radio`: 0 matches
- `<option>` with size/color: 0 matches
- `<fieldset>`: 0 matches

**Zero semantic variant markup.** Variant selection (band size, cup size) is rendered
entirely by client-side JavaScript.

## 5. Return/Refund Policy Links (in HTML, scripts stripped)

- Return/refund `<a>` tags: **1 match** — `<a href="/pages/returns">` present in HTML
- Privacy/cookie policy links also present

A return policy link IS present in the served HTML.

## 6. Add-to-Cart Markup (in HTML, scripts stripped)

- `<button>` with ATC text: **0** (no button element with "add to cart/bag" text)
- `<form action="/cart">`: **5 matches** — Shopify cart forms present
- "add-to-cart" / "add-to-bag" text in HTML (not scripts): **13 matches** — appear in
  CSS class names and data attributes, not as visible button labels

The ATC forms exist as `<form action="/cart">` elements, but the interactive button
text and variant selection are rendered client-side.

---

## Agree/Disagree Summary

| Scanner Finding | Independent Result | Verdict |
|---|---|---|
| No schema.org/Product JSON-LD (RDY-001) | `ProductGroup` JSON-LD found (not `Product`) | **DISAGREE** — see flag above |
| JS-rendered, 76.3% scripts, 0.4% visible text (RDY-013) | 76.2% scripts, 0.4% visible, 1 text line | **AGREE** |
| No semantic variant selectors (RDY-015) | Zero select/radio/fieldset for variants | **AGREE** |
| ATC browser flow failed (RDY-017) | Cart forms present but buttons are JS-rendered | **AGREE** (consistent) |
