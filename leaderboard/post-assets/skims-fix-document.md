# SKIMS Agent-Readiness Fix Document

**Score: 87/100 | 4 failures | Scanned July 2026**
Product: [Everyday Cotton Ultimate Teardrop Push-Up Bra](https://skims.com/products/everyday-cotton-ultimate-teardrop-push-up-bra-sienna-heather)

This document contains specific, implementable fixes for the four issues found in SKIMS's agent-readiness scan. Each fix includes the problem, what agents see, and the code to fix it.

---

## Fix 1: Replace HeadlessUI Popovers with Semantic Size Selectors

**Check:** RDY-015 (Variant selectors use semantic HTML)
**Severity:** Critical | **Weight:** 3/100 | **Impact:** Blocks Add-to-Cart flow entirely

### The problem

SKIMS uses HeadlessUI popover components for band and cup size selection. The page contains **64 HeadlessUI references**, **10 popover instances**, **13 swatch divs**, and **zero `<select>` elements**. There are no `role="listbox"` attributes anywhere on the page.

When an AI agent lands on this page, it sees something like:

```html
<!-- What SKIMS currently renders (simplified) -->
<div id="headlessui-popover-button-:r12:">
  <span>Band Size</span>
  <span>No selected Option</span>
</div>
<!-- Popover panel appears on click, but the ID changes every page load -->
<div id="headlessui-popover-panel-:r13:">
  <div class="swatch" data-value="32">32</div>
  <div class="swatch" data-value="34">34</div>
  <!-- ... -->
</div>
```

Agents can't work with this because:
- The popover IDs (`:r12:`, `:r13:`) are **randomly generated and change on every page load**
- There's no `role="listbox"` or `role="option"` to indicate these are selectable options
- The two-step interaction (click popover -> click swatch) has no semantic relationship between band and cup

### The fix

Add a semantic `<select>` fallback alongside the visual popover, or replace it entirely:

```html
<!-- Option A: Semantic selects (simplest, best for agents) -->
<form action="/cart/add" method="post">
  <input type="hidden" name="id" id="variant-id" value="">

  <label for="band-size">Band Size</label>
  <select id="band-size" name="properties[Band]" required
          aria-label="Band Size">
    <option value="">Select band size</option>
    <option value="30">30</option>
    <option value="32">32</option>
    <option value="34">34</option>
    <option value="36">36</option>
    <option value="38">38</option>
    <option value="40">40</option>
    <option value="42">42</option>
  </select>

  <label for="cup-size">Cup Size</label>
  <select id="cup-size" name="properties[Cup]" required
          aria-label="Cup Size">
    <option value="">Select cup size</option>
    <option value="A">A</option>
    <option value="B">B</option>
    <option value="C">C</option>
    <option value="D">D</option>
    <option value="DD">DD</option>
    <option value="F">F</option>
  </select>

  <button type="submit">Add to Cart</button>
</form>

<script>
  // Map band+cup to Shopify variant ID
  const variantMap = {
    "30 A": 49876543210, "30 B": 49876543211,
    "32 A": 49876543212, /* ... all 43 combinations */
  };

  document.querySelectorAll('#band-size, #cup-size').forEach(sel => {
    sel.addEventListener('change', () => {
      const band = document.getElementById('band-size').value;
      const cup = document.getElementById('cup-size').value;
      const key = `${band} ${cup}`;
      const variantId = variantMap[key];
      document.getElementById('variant-id').value = variantId || '';
    });
  });
</script>
```

```html
<!-- Option B: Keep visual popovers, add ARIA roles -->
<div role="listbox" aria-label="Band Size"
     id="band-size-selector">
  <div role="option" aria-selected="false" data-value="30">30</div>
  <div role="option" aria-selected="false" data-value="32">32</div>
  <div role="option" aria-selected="false" data-value="34">34</div>
  <!-- ... -->
</div>

<div role="listbox" aria-label="Cup Size"
     id="cup-size-selector">
  <div role="option" aria-selected="false" data-value="A">A</div>
  <div role="option" aria-selected="false" data-value="B">B</div>
  <!-- ... -->
</div>
```

**Estimated effort:** 2-4 hours for a Shopify theme developer.

---

## Fix 2: Add llms.txt

**Checks:** RDY-005 + RDY-011 (llms.txt present and well-structured)
**Severity:** Medium | **Combined weight:** 8/100

### The problem

No `llms.txt` file exists at `skims.com/llms.txt` (returns 404). AI agents have zero context for what SKIMS is, how the site is organized, or what actions are available.

### The fix

Create a file at `skims.com/llms.txt`:

```
# SKIMS
> Shop inclusive everyday essentials — underwear, loungewear, shapewear, swim.

SKIMS is a Shopify-powered store. Products are organized by category:
underwear, bras, shapewear, loungewear, swim, and accessories.

## Navigation
- Homepage: https://skims.com
- All Products: https://skims.com/collections/all
- Bras: https://skims.com/collections/bras
- Underwear: https://skims.com/collections/underwear
- Shapewear: https://skims.com/collections/shapewear
- Loungewear: https://skims.com/collections/loungewear

## Product pages
Each product page includes:
- JSON-LD structured data with price, availability, and variant info
- Band and cup size selection (bras) or S/M/L sizing (other categories)
- "Complete the Look" section with related products

## Sizing
Bra sizing uses two steps: band size (30-42) then cup size (A-F).
Other categories use XS, S, M, L, XL, 2X, 3X, 4X.

## Shipping
Free shipping on domestic (US) orders $75+.

## Returns
Free returns for SKIMS Rewards members.
Exchange or return within 30 days of delivery.

## For AI agents
- Product data is available in JSON-LD on every product page
- Use the JSON-LD hasVariant array to enumerate available sizes
- The recommended Add-to-Cart method is the product form on the page
- Contact: support@skims.com
```

On Shopify, deploy via a proxy route or a static hosting redirect. In `shopify.config.js` or the theme's `routes` section:

```json
{
  "proxy": {
    "/llms.txt": "https://cdn.skims.com/llms.txt"
  }
}
```

Or serve it as a static asset in the theme's `assets/` folder with a URL rewrite.

**Estimated effort:** 15 minutes to write, 30 minutes to deploy.

---

## Fix 3: Disambiguate Shipping Text

**Check:** RDY-010 (Consistent shipping answer)
**Severity:** High | **Weight:** 5/100 | **Pass rate:** 80% (8/10 runs agreed)

### The problem

The page contains shipping text in multiple languages/regions:
- English: `"Free Shipping on Domestic Orders $75+"`
- Australian: `"Free Shipping On Orders AUD185+"`

Both appear in the page source. Agents extract one or the other depending on which they encounter first, producing inconsistent answers across runs.

### The fix

Ensure only one canonical shipping statement is visible in the HTML for the user's locale. Wrap regional variants in locale-specific containers that aren't exposed to non-browser agents:

```html
<!-- Canonical shipping (always in HTML) -->
<p class="shipping-policy" data-shipping="canonical">
  Free shipping on US orders $75+
</p>

<!-- Regional variants (render only with JS based on geo-IP) -->
<template id="shipping-au">
  Free shipping on orders AUD185+
</template>

<script>
  if (userLocale === 'en-AU') {
    document.querySelector('.shipping-policy').textContent =
      document.getElementById('shipping-au').content.textContent;
  }
</script>
```

Using a `<template>` tag keeps the regional text out of the DOM that agents parse, while still being available for JavaScript-based localization.

**Estimated effort:** 1-2 hours.

---

## Fix 4: Re-enable Cart API Endpoint

**Check:** RDY-023 (Programmatic cart API available)
**Severity:** Medium | **Weight:** 3/100

### The problem

SKIMS's `/cart/add.js` endpoint returns **HTTP 410 Gone**. This is the standard Shopify AJAX cart API that headless agents use to add products to cart without DOM interaction. With it disabled, agents must navigate the visual UI to add items — a process that currently fails due to the HeadlessUI variant selectors.

### The fix

Re-enable the Shopify default `/cart/add.js` endpoint. On Shopify, this is typically active by default. It may have been disabled via a middleware proxy or a custom app.

Once enabled, a headless agent can add to cart with:

```bash
POST https://skims.com/cart/add.js
Content-Type: application/json

{
  "id": 49876543210,
  "quantity": 1
}
```

The variant ID comes from the JSON-LD `hasVariant` array already on the page — agents don't need the visual UI at all.

If re-enabling the full endpoint isn't desired, consider a read-only version that at least confirms the endpoint exists, so agents know programmatic carting is supported.

**Estimated effort:** 30 minutes (usually a config toggle or removing a proxy rule).

---

## Summary

| Fix | Checks | Weight | Effort | Score impact |
|-----|--------|--------|--------|-------------|
| Semantic size selectors | RDY-015, RDY-017 | 3+8 | 2-4 hours | +11 points |
| Add llms.txt | RDY-005, RDY-011 | 3+5 | 45 minutes | +8 points |
| Disambiguate shipping | RDY-010 | 5 | 1-2 hours | +1 point (80% -> 100%) |
| Re-enable cart API | RDY-023 | 3 | 30 minutes | +3 points |

**Total estimated effort:** ~1 day of developer time
**Projected score:** 87 -> 97+ / 100

---

*Generated by [agent-a](https://github.com/monkrus/agent-a), an open-source agent-accessibility scanner. Contact: sergeigodev@gmail.com*
