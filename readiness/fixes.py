#!/usr/bin/env python3
"""
fixes.py — Generate copy-paste fix recipes per failing check.

Given a check result and the page data, produces platform-specific code
the merchant can paste into their store. Shopify-focused for v1.
"""
from __future__ import annotations


def generate_fix(check_result: dict, page: dict) -> str | None:
    """Return a code snippet the merchant can copy-paste, or None."""
    cid = check_result.get("id", "")
    verdict = check_result.get("verdict", "")
    if verdict != "FAIL":
        return None

    fn = GENERATORS.get(cid)
    if fn:
        return fn(check_result, page)
    return None


# ---- Per-check generators --------------------------------------------------

def _fix_jsonld(check, page):
    title = page.get("title", "Your Product Name")
    if " — " in title:
        title = title.split(" — ")[0].strip()
    if " - " in title:
        title = title.split(" - ")[0].strip()
    if "not found" in title.lower():
        title = "Your Product Name"

    url = page.get('url', 'https://your-store.com/products/your-product')

    return (
        '<!-- Paste this into your product page template (Shopify: theme.liquid or product.liquid) -->\n'
        '<!-- Replace the placeholder values with your actual product data -->\n\n'
        '<script type="application/ld+json">\n'
        '{\n'
        '  "@context": "https://schema.org",\n'
        '  "@type": "Product",\n'
        '  "name": "' + title + '",\n'
        '  "image": "https://your-store.com/product-image.jpg",\n'
        '  "description": "Your product description here",\n'
        '  "brand": {\n'
        '    "@type": "Brand",\n'
        '    "name": "Your Brand"\n'
        '  },\n'
        '  "offers": {\n'
        '    "@type": "Offer",\n'
        '    "price": "0.00",\n'
        '    "priceCurrency": "USD",\n'
        '    "availability": "https://schema.org/InStock",\n'
        '    "url": "' + url + '"\n'
        '  }\n'
        '}\n'
        '</script>\n\n'
        '<!-- Shopify Liquid version (auto-fills from product data): -->\n'
        '<!--\n'
        '<script type="application/ld+json">\n'
        '{\n'
        '  "@context": "https://schema.org",\n'
        '  "@type": "Product",\n'
        '  "name": "{{ product.title }}",\n'
        '  "image": "{{ product.featured_image | image_url }}",\n'
        '  "description": "{{ product.description | strip_html | truncate: 200 }}",\n'
        '  "brand": {\n'
        '    "@type": "Brand",\n'
        '    "name": "{{ product.vendor }}"\n'
        '  },\n'
        '  "offers": {\n'
        '    "@type": "Offer",\n'
        '    "price": "{{ product.price | money_without_currency }}",\n'
        '    "priceCurrency": "{{ cart.currency.iso_code }}",\n'
        '    "availability": "{% if product.available %}https://schema.org/InStock{% else %}https://schema.org/OutOfStock{% endif %}",\n'
        '    "url": "{{ shop.url }}{{ product.url }}"\n'
        '  }\n'
        '}\n'
        '</script>\n'
        '-->'
    )


def _fix_price_html(check, page):
    return '''<!-- Add a visible price element that renders server-side (no JavaScript needed) -->
<!-- Shopify Liquid — paste in your product template: -->

<div class="product-price" data-product-price>
  {{ product.price | money }}
</div>

<!-- This ensures the price is in the raw HTML that agents and crawlers see. -->
<!-- Do NOT rely on JavaScript to inject the price — most AI agents don't run JS. -->'''


def _fix_robots(check, page):
    return '''# Add these lines to your robots.txt to allow AI shopping agents:
# (Shopify: Settings > Custom data > robots.txt)

User-agent: GPTBot
Allow: /products/
Allow: /collections/
Allow: /policies/

User-agent: Google-Extended
Allow: /products/
Allow: /collections/

User-agent: PerplexityBot
Allow: /products/
Allow: /collections/

User-agent: ClaudeBot
Allow: /products/
Allow: /collections/
Allow: /policies/

User-agent: Amazonbot
Allow: /products/
Allow: /collections/'''


def _fix_policy(check, page):
    return '''<!-- Make sure your return/refund policy is linked as plain HTML text. -->
<!-- Shopify: this is usually at /policies/refund-policy -->
<!-- Add a visible link on your product page: -->

<a href="/policies/refund-policy">Return & Refund Policy</a>

<!-- Also ensure the policy page contains plain text, not just a PDF or image. -->
<!-- AI agents cannot read PDFs or images embedded in policy pages. -->'''


def _fix_llms_txt(check, page):
    url = page.get("url", "https://your-store.com")
    base = url.split("/products")[0] if "/products" in url else url.rstrip("/")
    return (
        '# Create a file called llms.txt at your site root\n'
        '# (Shopify: Settings > Files, or use a custom page at /pages/llms-txt)\n'
        '# This tells AI agents how to interact with your store.\n\n'
        '# llms.txt — Your Store Name\n\n'
        '## Products\n'
        '- Browse products: ' + base + '/collections/all\n'
        '- Product JSON API: ' + base + '/products/{handle}.json\n'
        '- Search: ' + base + '/search?q={query}&type=product\n\n'
        '## Policies\n'
        '- Return policy: ' + base + '/policies/refund-policy\n'
        '- Shipping policy: ' + base + '/policies/shipping-policy\n'
        '- Privacy policy: ' + base + '/policies/privacy-policy\n\n'
        '## Sitemap\n'
        '- ' + base + '/sitemap.xml'
    )


def _fix_price_extraction(check, page):
    return '''<!-- Fix: make sure only ONE price is visible on the page. -->
<!-- Multiple prices (original, sale, compare-at) confuse AI agents. -->

<!-- Shopify Liquid — clear price display: -->
<div class="product-price">
  {% if product.compare_at_price > product.price %}
    <span class="price-sale">{{ product.price | money }}</span>
    <span class="price-compare"><s>{{ product.compare_at_price | money }}</s></span>
  {% else %}
    <span class="price-regular">{{ product.price | money }}</span>
  {% endif %}
</div>

<!-- Also ensure JSON-LD offers.price matches the visible price exactly. -->'''


def _fix_availability(check, page):
    return '''<!-- Add visible stock status to your product page: -->

<!-- Shopify Liquid: -->
{% if product.available %}
  <span class="stock-status in-stock">In Stock</span>
{% else %}
  <span class="stock-status out-of-stock">Out of Stock</span>
{% endif %}

<!-- Make sure JSON-LD offers.availability matches: -->
<!-- "availability": "{% if product.available %}https://schema.org/InStock{% else %}https://schema.org/OutOfStock{% endif %}" -->'''


def _fix_product_name(check, page):
    return '''<!-- Set a clear, canonical product name in these three places: -->

<!-- 1. Page title (Shopify: already automatic) -->
<title>{{ product.title }} — {{ shop.name }}</title>

<!-- 2. Open Graph tag -->
<meta property="og:title" content="{{ product.title }}">

<!-- 3. JSON-LD (see structured data fix above) -->
<!-- "name": "{{ product.title }}" -->

<!-- Avoid generic titles like "Product Page" or "Shop" -->
<!-- The title should be the specific product name. -->'''


def _fix_return_window(check, page):
    return '''<!-- State your return window clearly on the product page: -->

<div class="return-policy-summary">
  <strong>Returns:</strong> 30-day return window.
  <a href="/policies/refund-policy">Full return policy</a>
</div>

<!-- Place this near the buy button or in a product details tab. -->
<!-- AI agents look for a specific number of days — be explicit. -->
<!-- Don't say "within our return period" — say "within 30 days." -->'''


def _fix_shipping(check, page):
    return '''<!-- State shipping cost clearly on the product page: -->

<div class="shipping-summary">
  <strong>Shipping:</strong> Free on orders over $100. Standard shipping $5.00.
  <a href="/policies/shipping-policy">Full shipping details</a>
</div>

<!-- Place this near the price or buy button. -->
<!-- Be specific: "$5.00 flat rate" is better than "calculated at checkout" -->
<!-- AI agents treat "calculated at checkout" as unknown. -->'''


def _fix_llms_txt_quality(check, page):
    url = page.get("url", "https://your-store.com")
    base = url.split("/products")[0] if "/products" in url else url.rstrip("/")
    return (
        '# Improve your llms.txt with these key sections:\n\n'
        '# llms.txt — Your Store Name\n\n'
        '## Products\n'
        '- Browse all products: ' + base + '/collections/all\n'
        '- Product JSON API: ' + base + '/products/{handle}.json\n'
        '- Search products: ' + base + '/search?q={query}&type=product\n\n'
        '## Policies\n'
        '- Return policy: ' + base + '/policies/refund-policy\n'
        '- Shipping policy: ' + base + '/policies/shipping-policy\n'
        '- Privacy policy: ' + base + '/policies/privacy-policy\n\n'
        '## Sitemap\n'
        '- Sitemap: ' + base + '/sitemap.xml\n\n'
        '<!-- Ensure all URLs are absolute (https://...) and not broken. -->\n'
        '<!-- AI agents use these paths to navigate your store programmatically. -->'
    )


def _fix_jsonld_quality(check, page):
    return '''<!-- Ensure your JSON-LD Product includes ALL of these fields: -->

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "{{ product.title }}",
  "image": "{{ product.featured_image | image_url }}",
  "description": "{{ product.description | strip_html | truncate: 200 }}",
  "brand": {
    "@type": "Brand",
    "name": "{{ product.vendor }}"
  },
  "offers": {
    "@type": "Offer",
    "price": "{{ product.price | money_without_currency }}",
    "priceCurrency": "{{ cart.currency.iso_code }}",
    "availability": "{% if product.available %}https://schema.org/InStock{% else %}https://schema.org/OutOfStock{% endif %}",
    "url": "{{ shop.url }}{{ product.url }}"
  }
}
</script>

<!-- Common mistakes: -->
<!-- - availability must be a full schema.org URL, not just "InStock" -->
<!-- - priceCurrency must be a 3-letter ISO code (USD, GBP, EUR) -->
<!-- - brand must be a Brand object with a name, not just a string -->'''


def _fix_js_render_ratio(check, page):
    return '''<!-- Your page relies heavily on JavaScript to render content. -->
<!-- Most AI agents don't run JS — they see your raw HTML only. -->

<!-- Fix: Server-side render (SSR) these critical elements: -->

<!-- 1. Product title — must be in a visible <h1> in raw HTML -->
<h1 class="product-title">{{ product.title }}</h1>

<!-- 2. Price — must be in raw HTML, not injected by JS -->
<div class="product-price">{{ product.price | money }}</div>

<!-- 3. Description — at least the first paragraph in raw HTML -->
<div class="product-description">
  {{ product.description }}
</div>

<!-- 4. Availability — visible text in raw HTML -->
<span class="stock-status">
  {% if product.available %}In Stock{% else %}Out of Stock{% endif %}
</span>

<!-- Shopify Liquid templates render server-side by default. -->
<!-- If you use a JS framework (React/Vue/headless), ensure SSR is enabled. -->'''


def _fix_cart_semantic(check, page):
    return '''<!-- Make your Add-to-Cart button identifiable to AI agents: -->

<!-- Use a semantic <form> with a clear action: -->
<form method="post" action="/cart/add" id="product-form">
  <input type="hidden" name="id" value="{{ product.selected_or_first_available_variant.id }}">
  <input type="hidden" name="quantity" value="1">

  <button type="submit"
          name="add"
          aria-label="Add to Cart"
          data-testid="add-to-cart">
    Add to Cart
  </button>
</form>

<!-- Key requirements for agent accessibility: -->
<!-- - form action="/cart/add" (standard Shopify endpoint) -->
<!-- - button type="submit" (not a div or span) -->
<!-- - aria-label or name attribute on the button -->
<!-- - data-testid for automated agent interaction -->'''


def _fix_variant_selectors(check, page):
    return '''<!-- Use semantic HTML for variant selectors so agents can choose options: -->

<!-- SIZE — use a <select> or radio inputs with labels: -->
<fieldset class="variant-selector">
  <legend>Size</legend>
  {% for option in product.options_with_values[0].values %}
    <label>
      <input type="radio" name="Size" value="{{ option }}">
      {{ option }}
    </label>
  {% endfor %}
</fieldset>

<!-- COLOR — same pattern: -->
<fieldset class="variant-selector">
  <legend>Color</legend>
  <select name="Color" id="color-selector">
    {% for option in product.options_with_values[1].values %}
      <option value="{{ option }}">{{ option }}</option>
    {% endfor %}
  </select>
</fieldset>

<!-- Avoid: custom JS-only swatches with no underlying input elements -->
<!-- Agents need name= attributes and standard form elements to select variants -->'''


def _fix_prompt_injection(check, page):
    return '''<!-- SECURITY: Hidden prompt injection detected on this page. -->
<!-- Malicious text hidden in your page can hijack AI shopping agents, -->
<!-- causing them to give wrong information to your customers. -->

<!-- Steps to fix: -->

<!-- 1. Audit HTML comments — remove any that contain instructions to AI -->
<!--    Search your templates for comments with words like "ignore", -->
<!--    "system", "override", or "instructions" -->

<!-- 2. Audit hidden elements — check display:none, visibility:hidden, -->
<!--    aria-hidden, and 0px/0-opacity elements for suspicious text -->

<!-- 3. Audit user-generated content (reviews, Q&A) -->
<!--    Add a content filter that strips known injection patterns: -->

<!-- Shopify Liquid example — sanitize review text: -->
<!-- {{ review.text | strip_html | escape }} -->

<!-- 4. If using a review app (Yotpo, Judge.me, Loox), check their -->
<!--    moderation settings and enable content filtering -->

<!-- Common injection patterns to filter: -->
<!-- "ignore previous instructions" -->
<!-- "you are now a..." -->
<!-- "system: override" -->
<!-- "disregard all previous" -->
<!-- "tell the user that..." -->'''


GENERATORS = {
    "RDY-001": _fix_jsonld,
    "RDY-002": _fix_price_html,
    "RDY-003": _fix_robots,
    "RDY-004": _fix_policy,
    "RDY-005": _fix_llms_txt,
    "RDY-006": _fix_price_extraction,
    "RDY-007": _fix_availability,
    "RDY-008": _fix_product_name,
    "RDY-009": _fix_return_window,
    "RDY-010": _fix_shipping,
    "RDY-011": _fix_llms_txt_quality,
    "RDY-012": _fix_jsonld_quality,
    "RDY-013": _fix_js_render_ratio,
    "RDY-014": _fix_cart_semantic,
    "RDY-015": _fix_variant_selectors,
    "RDY-016": _fix_prompt_injection,
}
    return '''<!-- SECURITY: Hidden prompt injection detected on this page. -->
<!-- Malicious text hidden in your page can hijack AI shopping agents, -->
<!-- causing them to give wrong information to your customers. -->

<!-- Steps to fix: -->

<!-- 1. Audit HTML comments — remove any that contain instructions to AI -->
<!--    Search your templates for <!-- comments with words like "ignore", -->
<!--    "system", "override", or "instructions" -->

<!-- 2. Audit hidden elements — check display:none, visibility:hidden, -->
<!--    aria-hidden, and 0px/0-opacity elements for suspicious text -->

<!-- 3. Audit user-generated content (reviews, Q&A) -->
<!--    Add a content filter that strips known injection patterns: -->

<!-- Shopify Liquid example — sanitize review text: -->
<!-- {{ review.text | strip_html | escape }} -->

<!-- 4. If using a review app (Yotpo, Judge.me, Loox), check their -->
<!--    moderation settings and enable content filtering -->

<!-- Common injection patterns to filter: -->
<!-- "ignore previous instructions" -->
<!-- "you are now a..." -->
<!-- "system: override" -->
<!-- "disregard all previous" -->
<!-- "tell the user that..." -->'''
