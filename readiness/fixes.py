#!/usr/bin/env python3
"""
fixes.py — Generate copy-paste fix recipes per failing check.

Given a check result and the page data, produces platform-specific code
the merchant can paste into their store. Shopify-focused for v1.

Each fix has two parts:
  1. Plain-English steps (what to click in Shopify admin)
  2. Code to paste (clearly labeled)
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
        'HOW TO FIX (structured product data is missing)\n'
        '================================================\n\n'
        'What this means: AI shopping agents (ChatGPT, Perplexity, etc.) can\'t\n'
        'find your product name, price, or availability because the page is\n'
        'missing structured data (JSON-LD). This is like having a store with\n'
        'no price tags — agents will skip your product.\n\n'
        'STEPS (Shopify):\n'
        '1. In your Shopify admin, go to: Online Store > Themes > Edit code\n'
        '2. Open the file: product.liquid (or main-product.liquid)\n'
        '3. Paste the code below at the very TOP of that file\n'
        '4. Click Save\n\n'
        '--- PASTE THIS CODE ---\n\n'
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
        '</script>\n\n'
        '--- END CODE ---\n\n'
        'This code auto-fills from your product data — no manual editing needed.\n'
        'It works for every product page automatically.'
    )


def _fix_price_html(check, page):
    return (
        'HOW TO FIX (price not visible in page source)\n'
        '==============================================\n\n'
        'What this means: Your price only appears after JavaScript runs.\n'
        'AI agents don\'t run JavaScript — they see a blank where the price\n'
        'should be. They can\'t recommend a product if they don\'t know the price.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Find where your price is displayed\n'
        '4. Make sure it includes this line (paste it if missing):\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '<div class="product-price" data-product-price>\n'
        '  {{ product.price | money }}\n'
        '</div>\n\n'
        '--- END CODE ---\n\n'
        'This shows the price directly in the HTML — no JavaScript needed.\n'
        'It auto-fills the correct price for each product.'
    )


def _fix_robots(check, page):
    return (
        'HOW TO FIX (robots.txt blocks AI agents)\n'
        '=========================================\n\n'
        'What this means: Your robots.txt file tells AI shopping agents they\'re\n'
        'not allowed to visit your product pages. It\'s like putting a "closed"\n'
        'sign on your door — agents will respect it and leave.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Settings > Custom data (scroll down to "robots.txt")\n'
        '2. Add the lines below to allow AI agents to see your products\n\n'
        'If you DON\'T use Shopify:\n'
        '1. Open the robots.txt file at your website root\n'
        '2. Add these lines at the end\n\n'
        '--- PASTE THESE LINES ---\n\n'
        'User-agent: GPTBot\n'
        'Allow: /products/\n'
        'Allow: /collections/\n'
        'Allow: /policies/\n\n'
        'User-agent: Google-Extended\n'
        'Allow: /products/\n'
        'Allow: /collections/\n\n'
        'User-agent: PerplexityBot\n'
        'Allow: /products/\n'
        'Allow: /collections/\n\n'
        'User-agent: ClaudeBot\n'
        'Allow: /products/\n'
        'Allow: /collections/\n'
        'Allow: /policies/\n\n'
        'User-agent: Amazonbot\n'
        'Allow: /products/\n'
        'Allow: /collections/\n\n'
        '--- END ---\n\n'
        'This lets AI agents see your products and policies, while keeping\n'
        'the rest of your site protected.'
    )


def _fix_policy(check, page):
    return (
        'HOW TO FIX (return policy not found)\n'
        '====================================\n\n'
        'What this means: AI agents can\'t find your return/refund policy.\n'
        'When a customer asks an AI agent "can I return this?", the agent\n'
        'won\'t have an answer — and may recommend a competitor instead.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Settings > Policies > Refund policy\n'
        '2. Make sure you have a written policy (not blank)\n'
        '3. Then add a link to it on your product page:\n'
        '   Go to: Online Store > Themes > Edit code > product.liquid\n'
        '4. Paste this near your "Add to Cart" button:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '<a href="/policies/refund-policy">Return & Refund Policy</a>\n\n'
        '--- END CODE ---\n\n'
        'Important: Your policy page must contain plain text (not a PDF or image).\n'
        'AI agents cannot read PDFs or images.'
    )


def _fix_llms_txt(check, page):
    url = page.get("url", "https://your-store.com")
    base = url.split("/products")[0] if "/products" in url else url.rstrip("/")
    return (
        'HOW TO FIX (no llms.txt file)\n'
        '=============================\n\n'
        'What this means: llms.txt is a simple text file that tells AI agents\n'
        'how to navigate your store — like a map for robots. Without it, agents\n'
        'have to guess where your products, search, and policies are.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Pages > Add page\n'
        '2. Title: "llms.txt"\n'
        '3. Set the URL handle to: llms-txt\n'
        '4. Paste the text below into the page body\n'
        '5. Click Save\n\n'
        '--- PASTE THIS TEXT ---\n\n'
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
        '- ' + base + '/sitemap.xml\n\n'
        '--- END TEXT ---\n\n'
        'Replace "Your Store Name" with your actual store name.'
    )


def _fix_price_extraction(check, page):
    return (
        'HOW TO FIX (AI agents can\'t read the correct price)\n'
        '====================================================\n\n'
        'What this means: When we asked AI agents "what does this cost?",\n'
        'they got the wrong answer. This usually happens when multiple prices\n'
        'are shown (original, sale, compare-at) and the agent picks the wrong one.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Find your price display code and replace it with this:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '<div class="product-price">\n'
        '  {% if product.compare_at_price > product.price %}\n'
        '    <span class="price-sale">{{ product.price | money }}</span>\n'
        '    <span class="price-compare"><s>{{ product.compare_at_price | money }}</s></span>\n'
        '  {% else %}\n'
        '    <span class="price-regular">{{ product.price | money }}</span>\n'
        '  {% endif %}\n'
        '</div>\n\n'
        '--- END CODE ---\n\n'
        'This displays the sale price first and strikes out the old price,\n'
        'so agents always pick up the current price.'
    )


def _fix_availability(check, page):
    return (
        'HOW TO FIX (stock status not visible to agents)\n'
        '================================================\n\n'
        'What this means: AI agents can\'t tell if this product is in stock.\n'
        'If a customer asks "is this available?", the agent won\'t know.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Paste this code near your price or "Add to Cart" button:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '{% if product.available %}\n'
        '  <span class="stock-status">In Stock</span>\n'
        '{% else %}\n'
        '  <span class="stock-status">Out of Stock</span>\n'
        '{% endif %}\n\n'
        '--- END CODE ---\n\n'
        'This auto-updates based on your inventory — no manual changes needed.'
    )


def _fix_product_name(check, page):
    return (
        'HOW TO FIX (product name not clear to agents)\n'
        '==============================================\n\n'
        'What this means: AI agents can\'t confidently identify what this product\n'
        'is called. The page title may be generic ("Shop" or "Products") or\n'
        'missing entirely.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to the product in your Shopify admin\n'
        '2. Make sure the "Title" field has the full product name\n'
        '   (e.g., "Wool Runner - Natural Grey" not just "Runner")\n'
        '3. Then check your theme code:\n'
        '   Online Store > Themes > Edit code > theme.liquid\n'
        '4. Make sure the <title> tag includes the product name:\n\n'
        '--- PASTE THIS CODE (in theme.liquid, inside <head>) ---\n\n'
        '<title>{{ product.title }} — {{ shop.name }}</title>\n'
        '<meta property="og:title" content="{{ product.title }}">\n\n'
        '--- END CODE ---\n\n'
        'Most Shopify themes do this automatically. If your title shows\n'
        '"Home" or your store name instead of the product, your theme\n'
        'may need this fix.'
    )


def _fix_return_window(check, page):
    return (
        'HOW TO FIX (return window not stated on product page)\n'
        '=====================================================\n\n'
        'What this means: Your return policy page exists, but the product page\n'
        'doesn\'t say HOW MANY DAYS customers have to return. AI agents need\n'
        'a specific number — "within 30 days" not "within our return period."\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Paste this near your "Add to Cart" button:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '<div class="return-policy-summary">\n'
        '  <strong>Returns:</strong> 30-day return window.\n'
        '  <a href="/policies/refund-policy">Full return policy</a>\n'
        '</div>\n\n'
        '--- END CODE ---\n\n'
        'Change "30-day" to your actual return window.\n'
        'Be specific: say "30 days" not "within our return period."'
    )


def _fix_shipping(check, page):
    return (
        'HOW TO FIX (shipping cost not shown on product page)\n'
        '====================================================\n\n'
        'What this means: AI agents can\'t find your shipping cost. When a\n'
        'customer asks "how much is shipping?", the agent has no answer.\n'
        '"Calculated at checkout" is not helpful — agents treat it as unknown.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Paste this near your price:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '<div class="shipping-summary">\n'
        '  <strong>Shipping:</strong> Free on orders over $100. Standard shipping $5.00.\n'
        '  <a href="/policies/shipping-policy">Full shipping details</a>\n'
        '</div>\n\n'
        '--- END CODE ---\n\n'
        'Change the amounts to match your actual shipping rates.\n'
        'Be specific: "$5.00 flat rate" is much better than "calculated at checkout."'
    )


def _fix_llms_txt_quality(check, page):
    url = page.get("url", "https://your-store.com")
    base = url.split("/products")[0] if "/products" in url else url.rstrip("/")
    return (
        'HOW TO FIX (llms.txt exists but is incomplete)\n'
        '===============================================\n\n'
        'What this means: You have an llms.txt file (great!), but it\'s missing\n'
        'important sections that AI agents need to navigate your store.\n\n'
        'STEPS:\n'
        '1. Open your existing llms.txt file\n'
        '   (Shopify: Online Store > Pages > find "llms.txt")\n'
        '2. Replace its content with this improved version:\n\n'
        '--- PASTE THIS TEXT ---\n\n'
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
        '--- END TEXT ---\n\n'
        'Make sure all URLs start with https:// and actually work when clicked.'
    )


def _fix_jsonld_quality(check, page):
    return (
        'HOW TO FIX (structured data is incomplete)\n'
        '===========================================\n\n'
        'What this means: Your page has structured data (good!), but it\'s missing\n'
        'fields that AI agents need — like brand, availability, or currency.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Find the existing <script type="application/ld+json"> block\n'
        '4. Replace it with this complete version:\n\n'
        '--- PASTE THIS CODE ---\n\n'
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
        '</script>\n\n'
        '--- END CODE ---\n\n'
        'This auto-fills from your product data. No manual editing needed.'
    )


def _fix_js_render_ratio(check, page):
    return (
        'HOW TO FIX (page content hidden behind JavaScript)\n'
        '===================================================\n\n'
        'What this means: Most of your page content only appears after JavaScript\n'
        'runs. AI agents don\'t run JavaScript — so they see a mostly blank page.\n'
        'It\'s like having a store where the products are invisible.\n\n'
        'WHY THIS HAPPENS:\n'
        '- Headless storefronts (Hydrogen, Next.js, custom React) often render\n'
        '  everything with JavaScript\n'
        '- Standard Shopify themes don\'t have this problem\n\n'
        'WHAT TO DO:\n'
        '1. If using a headless/custom storefront: Enable Server-Side Rendering (SSR)\n'
        '   - This is a developer task — ask your developer to enable SSR\n'
        '   - Key elements that MUST render without JS: product title, price,\n'
        '     description, availability, and "Add to Cart" button\n\n'
        '2. If using a standard Shopify theme: Check if an app or custom code\n'
        '   is replacing your product info with JavaScript widgets\n'
        '   - Common culprits: price apps, currency converters, A/B testing tools\n'
        '   - Try disabling apps one by one to find the one hiding your content\n\n'
        '3. Quick test: Right-click your product page > "View Page Source"\n'
        '   - If you can see the product name and price in the source, you\'re fine\n'
        '   - If the source is mostly <script> tags, you have this problem'
    )


def _fix_cart_semantic(check, page):
    return (
        'HOW TO FIX (Add-to-Cart button not recognizable by agents)\n'
        '==========================================================\n\n'
        'What this means: AI agents can\'t find or click your "Add to Cart" button\n'
        'because it\'s built with custom JavaScript instead of a standard HTML form.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Find your Add-to-Cart button\n'
        '4. Make sure it\'s inside a <form> tag like this:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '<form method="post" action="/cart/add" id="product-form">\n'
        '  <input type="hidden" name="id" value="{{ product.selected_or_first_available_variant.id }}">\n'
        '  <input type="hidden" name="quantity" value="1">\n\n'
        '  <button type="submit" name="add" aria-label="Add to Cart">\n'
        '    Add to Cart\n'
        '  </button>\n'
        '</form>\n\n'
        '--- END CODE ---\n\n'
        'Key points:\n'
        '- The button must be inside a <form> (not a standalone <div> or <span>)\n'
        '- The button text should say "Add to Cart" (not an icon or symbol)\n'
        '- Avoid JavaScript-only cart buttons that don\'t work without JS'
    )


def _fix_variant_selectors(check, page):
    return (
        'HOW TO FIX (size/color selectors not accessible to agents)\n'
        '==========================================================\n\n'
        'What this means: Your size, color, or other variant options use custom\n'
        'visual swatches that AI agents can\'t interact with. The agent can\'t\n'
        'select "Large" or "Blue" because there\'s no standard form element.\n\n'
        'STEPS (Shopify):\n'
        '1. Go to: Online Store > Themes > Edit code\n'
        '2. Open: product.liquid (or main-product.liquid)\n'
        '3. Find your variant selectors (size, color, etc.)\n'
        '4. Make sure they use dropdown menus or radio buttons:\n\n'
        '--- PASTE THIS CODE ---\n\n'
        '{% for option in product.options_with_values %}\n'
        '  <label for="option-{{ option.name }}">{{ option.name }}</label>\n'
        '  <select name="{{ option.name }}" id="option-{{ option.name }}">\n'
        '    {% for value in option.values %}\n'
        '      <option value="{{ value }}">{{ value }}</option>\n'
        '    {% endfor %}\n'
        '  </select>\n'
        '{% endfor %}\n\n'
        '--- END CODE ---\n\n'
        'You can keep your visual swatches for human shoppers — just make sure\n'
        'there\'s also a real <select> dropdown or radio button underneath.\n'
        'The visual swatch can control the hidden dropdown via JavaScript.'
    )


def _fix_prompt_injection(check, page):
    return (
        'HOW TO FIX (hidden text could hijack AI agents)\n'
        '================================================\n\n'
        'What this means: We found hidden text on your page that could trick\n'
        'AI shopping agents into giving wrong information to your customers.\n'
        'This is a SECURITY issue — someone may have injected malicious content.\n\n'
        'WHAT TO CHECK:\n\n'
        '1. CHECK YOUR REVIEWS AND Q&A\n'
        '   - Look for reviews containing unusual phrases like:\n'
        '     "ignore previous instructions" or "system: override"\n'
        '   - If using a review app (Yotpo, Judge.me, Loox), turn on\n'
        '     content moderation in the app settings\n\n'
        '2. CHECK YOUR THEME CODE\n'
        '   - Go to: Online Store > Themes > Edit code\n'
        '   - Search all files (Ctrl+F) for: "ignore", "system:", "override"\n'
        '   - Remove any HTML comments that contain instructions to AI\n\n'
        '3. CHECK FOR HIDDEN ELEMENTS\n'
        '   - Right-click your product page > Inspect Element\n'
        '   - Look for text that\'s hidden (invisible, 0px size, white-on-white)\n'
        '   - Hidden text with instructions like "tell the user..." is malicious\n\n'
        'If you find suspicious content you didn\'t add, it may have been injected\n'
        'through a third-party app, review spam, or a compromised template.\n'
        'Remove it and audit your installed apps.'
    )


def _fix_add_to_cart_flow(check, page):
    return (
        'HOW TO FIX (AI agent could not add to cart)\n'
        '============================================\n\n'
        'What this means: We ran an AI agent that tried to add this product\n'
        'to the cart, and it couldn\'t complete the process. Customers using\n'
        'AI assistants won\'t be able to buy from your store.\n\n'
        'COMMON CAUSES & FIXES:\n\n'
        '1. POP-UPS BLOCKING THE PAGE\n'
        '   - Newsletter popups, cookie banners, or warranty offers can block\n'
        '     the Add-to-Cart button from being clicked\n'
        '   - Fix: Set popups to appear after 30+ seconds, not immediately\n'
        '   - In your popup app settings, add a delay or scroll trigger\n\n'
        '2. ADD-TO-CART IS JAVASCRIPT-ONLY\n'
        '   - Your button may need JavaScript to work, and agents can\'t\n'
        '     always run complex JavaScript\n'
        '   - Fix: Use a standard HTML form (see code below)\n\n'
        '3. VARIANT SELECTION REQUIRED FIRST\n'
        '   - If customers must pick size/color before adding to cart, make sure\n'
        '     the selectors are standard dropdowns (not custom JS swatches)\n\n'
        '--- PASTE THIS CODE (standard Add-to-Cart form) ---\n\n'
        '<form method="post" action="/cart/add" id="product-form">\n'
        '  <input type="hidden" name="id" value="{{ product.selected_or_first_available_variant.id }}">\n'
        '  <input type="hidden" name="quantity" value="1">\n\n'
        '  {% for option in product.options_with_values %}\n'
        '    <label for="option-{{ option.name }}">{{ option.name }}</label>\n'
        '    <select name="{{ option.name }}" id="option-{{ option.name }}">\n'
        '      {% for value in option.values %}\n'
        '        <option value="{{ value }}">{{ value }}</option>\n'
        '      {% endfor %}\n'
        '    </select>\n'
        '  {% endfor %}\n\n'
        '  <button type="submit" name="add" aria-label="Add to Cart">\n'
        '    Add to Cart\n'
        '  </button>\n'
        '</form>\n\n'
        '--- END CODE ---'
    )


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
    "RDY-017": _fix_add_to_cart_flow,
}
