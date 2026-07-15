# Independent Spot-Check — kyliecosmetics.com (66.0/100)

**URL:** `https://kyliecosmetics.com/products/compact-mirror`
**Method:** Plain `requests.get()` with Chrome User-Agent (no JS execution)
**Code path:** Completely independent of scanner's fetch.py / scorers.py

---

No disagreements found.

---

## 1. Fetch Summary
- HTTP status: **200**
- Total HTML size: **426,383 bytes**
- Script tags: high script ratio (consistent with scanner's 79.1%)
- Visible text lines: **76** — mostly nav, footer links, minimal product content

## 2. JSON-LD (application/ld+json)

**Found 1 JSON-LD block:**

```
@type: "Product"
name: "Compact Mirror"
description: NOT PRESENT (missing field)
```

Scanner finding: "JSON-LD Product incomplete: missing description" (RDY-012 FAIL).
Independent fetch confirms: JSON-LD Product block exists but `description` field is absent.

## 3. Visible Text (first 30 lines after stripping tags/scripts)

```
Compact Mirror - Kylie Cosmetics
Skip to content
free Travel Accessory with any $55+ order   shop now
Compact Mirror
on social
contact us
faq
shipping
order tracking
rewards
Gift Card Balance
Legal
privacy policy
terms
accessibility
cookie settings
cookie policy
(repeated footer block)
- Out of stock
Select an option
```

76 visible text lines total. Almost entirely nav links, footer, and legal links.
Product content is limited to title ("Compact Mirror"), "Out of stock", and "Select an option".
No price, no description in visible text.

## 4. Semantic Variant Selectors

Regex matched one `<input type="radio">` — but it's embedded in a Vue.js template,
not a standard form control. No `<select>`, `<option>`, or `<fieldset>` elements for
product variants found.

## 5. Return/Refund Policy Links (in HTML, scripts stripped)

**4 `<a>` tags found** — but ALL are `privacy-policy` and `cookie-policy`:

```html
<a href="/pages/privacy-policy">privacy policy</a>
<a href="/pages/cookie-policy">cookie policy</a>
<a href="/pages/privacy-policy">privacy policy</a>  (repeated in mobile nav)
<a href="/pages/cookie-policy">cookie policy</a>    (repeated in mobile nav)
```

**Zero** return/refund policy links. No `<a>` tag with "return", "refund", or "exchange"
in href or link text. Scanner correctly identified no return policy link (RDY-004 FAIL).

## 6. Add-to-Cart Markup (in HTML, scripts stripped)

- `<button>` with "add to cart/bag" text: **0 matches**
- `<form action="/cart">`: **0 matches**
- "add-to-cart" text in HTML (not scripts): **23 matches** — ALL in CSS class names

One key CSS match reveals the mechanism:
```css
.form__atc, .form__atc--main, .action--add-to-cart {
    display: none !important;
}
```

The ATC form element has class `.form__atc` but is **explicitly hidden with CSS**
(`display: none !important`). There is no visible or functional ATC button in the
server-rendered HTML. Scanner correctly identified no ATC form/button (RDY-014 FAIL).

---

## Agree/Disagree Summary

| Scanner Finding | Independent Result | Verdict |
|---|---|---|
| No return/refund policy link (RDY-004) | Zero return/refund `<a>` tags; only privacy/cookie | **AGREE** |
| JSON-LD incomplete: missing description (RDY-012) | Product JSON-LD present, `description` field absent | **AGREE** |
| JS-rendered, 79.1% scripts (RDY-013) | High script ratio confirmed, 76 visible text lines (nav/footer) | **AGREE** |
| No ATC form/button in served HTML (RDY-014) | Zero ATC buttons/forms; CSS explicitly hides `.form__atc` | **AGREE** |
| Browser ATC flow failed in 12 steps (RDY-017) | Consistent with no visible ATC button in server HTML | **AGREE** |
