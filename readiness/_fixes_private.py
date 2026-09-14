"""
Private fix recipes for the Agent-A scanner.

Each recipe returns a platform-specific, copy-paste code snippet for the
failing check. Shopify-focused but includes generic HTML/server guidance.
"""
from __future__ import annotations


def generate_fix(check_result: dict, page: dict) -> str | None:
    """Return a copy-paste fix recipe for a failing check."""
    if check_result.get("verdict") != "FAIL":
        return None

    check_id = check_result.get("id", "")
    handler = _RECIPES.get(check_id)
    if not handler:
        return None
    return handler(check_result, page)


# ---------------------------------------------------------------------------
# Per-check recipes
# ---------------------------------------------------------------------------

def _fix_001(cr, page):
    price = page.get("meta", {}).get("og:price:amount", "29.99")
    currency = page.get("meta", {}).get("og:price:currency", "USD")
    return f'''<!-- Add this to your product page <head> or before </body> -->
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "{{ product.title }}",
  "image": "{{ product.featured_image | image_url }}",
  "description": "{{ product.description | strip_html | truncate: 200 }}",
  "brand": {{
    "@type": "Brand",
    "name": "{{ product.vendor }}"
  }},
  "offers": {{
    "@type": "Offer",
    "price": "{{ product.price | money_without_currency }}",
    "priceCurrency": "{currency}",
    "availability": "{{% if product.available %}}https://schema.org/InStock{{% else %}}https://schema.org/OutOfStock{{% endif %}}",
    "url": "{{ canonical_url }}"
  }}
}}
</script>

Shopify: Add this to your theme's product.liquid or main-product.liquid section.
Most Shopify themes already include JSON-LD — check if yours is missing or incomplete.'''


def _fix_002(cr, page):
    return '''<!-- Server-render the price in visible HTML, not just JS -->
<!-- Shopify Liquid example: -->
<span class="product-price" data-product-price>
  {{ product.price | money }}
</span>

If your theme hides the price until JS runs (e.g. behind a "loading" state),
move the price into the initial Liquid render. AI agents don't run JavaScript.

Check: View your page source (Ctrl+U) — if the price isn't visible in the
raw HTML, agents can't see it.'''


def _fix_003(cr, page):
    detail = cr.get("detail", "")
    return f'''# robots.txt — allow AI agent crawlers
# Add these lines to your robots.txt (Shopify: Settings > Custom data > robots.txt)

User-agent: GPTBot
Allow: /products/
Allow: /collections/
Allow: /policies/

User-agent: ClaudeBot
Allow: /products/
Allow: /collections/
Allow: /policies/

User-agent: PerplexityBot
Allow: /products/
Allow: /collections/
Allow: /policies/

User-agent: OAI-SearchBot
Allow: /products/
Allow: /collections/
Allow: /policies/

Shopify: Go to Settings > Custom data > robots.txt.liquid and add these rules.
Note: Shopify's default robots.txt already allows most bots, but some themes
or apps add restrictive rules. Check your current robots.txt first.

Current issue: {detail[:200]}'''


def _fix_004(cr, page):
    return '''<!-- Make return/refund policy accessible as plain text -->
<!-- Shopify already generates /policies/refund-policy — make sure it exists: -->
<!-- Settings > Policies > Refund policy -->

1. Go to Shopify Admin > Settings > Policies
2. Fill in the "Refund policy" field with your full return policy
3. Shopify auto-publishes it at /policies/refund-policy
4. Link to it from your product page footer or product description

Also add a visible link on your product page:
<a href="/policies/refund-policy">Return Policy</a>

AI agents look for policy links in the footer, product page, and llms.txt.'''


def _fix_005(cr, page):
    return '''# Create /llms.txt at your site root
# Shopify: Use an app like "llms.txt" or add it via a custom page/proxy

# llms.txt
> This file tells AI shopping agents how to interact with our store.

## Product Catalog
- Products: /products.json
- Sitemap: /sitemap.xml
- Collections: /collections

## Policies
- Returns: /policies/refund-policy
- Shipping: /policies/shipping-policy
- Privacy: /policies/privacy-policy

## Checkout
- Cart API: /cart/add.js
- Checkout: /checkout (supports guest checkout)

## Contact
- Email: support@yourstore.com

Shopify: The easiest way is to use the "llms-txt" app from the Shopify App Store,
or create a page at /pages/llms-txt and set up a URL redirect from /llms.txt.'''


def _fix_006(cr, page):
    gt = cr.get("ground_truth", "")
    return f'''The AI agent extracted the wrong price or couldn't find it.
Expected: {gt}

Fix: Make the canonical price unambiguous.

1. Ensure JSON-LD has the correct price:
   "offers": {{ "price": "{gt}", "priceCurrency": "USD" }}

2. Remove stale or secondary prices that confuse agents:
   - Strike-through "compare at" prices should use <del> or <s> tags
   - Member/sale prices should be clearly labeled

3. Server-render the price in HTML (not JS-only):
   <span class="price">{{ product.price | money }}</span>

4. If you have variants at different prices, ensure the JSON-LD
   updates to match the selected variant.'''


def _fix_007(cr, page):
    return '''The AI agent got the wrong availability status.

Fix: Align JSON-LD availability with visible page state.

<!-- Shopify Liquid: -->
<script type="application/ld+json">
{
  "offers": {
    "availability": "{% if product.available %}https://schema.org/InStock{% else %}https://schema.org/OutOfStock{% endif %}"
  }
}
</script>

Also check:
- Remove "sold out" / "unavailable" text from the page if the product IS in stock
- If only some variants are sold out, don't show "sold out" for the whole product
- Update JSON-LD dynamically when variant selection changes (Shopify does this
  automatically if you use the default JSON-LD snippet)'''


def _fix_008(cr, page):
    gt = cr.get("ground_truth", "")
    return f'''The AI agent couldn't identify the correct product name.
Expected: {gt}

Fix: Use one canonical name consistently across:

1. <title> tag: "{gt} | Your Store"
2. og:title meta tag: "{gt}"
3. JSON-LD "name" field: "{gt}"
4. <h1> on the page: "{gt}"

If these all say different things, agents get confused. Pick one canonical
name and use it everywhere. Avoid stuffing keywords into the product title.'''


def _fix_009(cr, page):
    return '''The AI agent gave inconsistent return window answers.

Fix: State the return window once, explicitly, in plain text.

<!-- Add to your product page or link clearly to your policy: -->
<p class="return-policy">
  Free returns within <strong>30 days</strong> of purchase.
  <a href="/policies/refund-policy">Full return policy</a>
</p>

Common problems:
- Return window is buried in policy page legalese — agents can't find the number
- Multiple return windows mentioned (e.g. "14 days" in one place, "30 days" elsewhere)
- Return policy is in an image or PDF, not crawlable text'''


def _fix_010(cr, page):
    return '''The AI agent gave inconsistent shipping answers.

Fix: Publish shipping cost/conditions as explicit, crawlable text.

<!-- Add to your product page: -->
<p class="shipping-info">
  Free shipping on orders over $50. Standard shipping: $5.99 (3-5 business days).
  <a href="/policies/shipping-policy">Full shipping details</a>
</p>

Common problems:
- Shipping info only appears in checkout — agents can't see it pre-purchase
- "Calculated at checkout" tells the agent nothing useful
- Shipping rates are in a table image, not HTML text

Also add shipping info to your llms.txt file.'''


def _fix_012(cr, page):
    detail = cr.get("detail", "")
    return f'''Your JSON-LD Product markup is missing required fields.

{detail}

Complete JSON-LD Product example for Shopify:

<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "{{{{ product.title }}}}",
  "image": "{{{{ product.featured_image | image_url: width: 1200 }}}}",
  "description": "{{{{ product.description | strip_html | truncate: 500 }}}}",
  "brand": {{
    "@type": "Brand",
    "name": "{{{{ product.vendor }}}}"
  }},
  "sku": "{{{{ product.selected_or_first_available_variant.sku }}}}",
  "offers": {{
    "@type": "Offer",
    "price": "{{{{ product.price | money_without_currency }}}}",
    "priceCurrency": "{{{{ cart.currency.iso_code }}}}",
    "availability": "{{% if product.available %}}https://schema.org/InStock{{% else %}}https://schema.org/OutOfStock{{% endif %}}",
    "url": "{{{{ canonical_url }}}}"
  }}
}}
</script>

Shopify: Most themes include this in theme.liquid or product.liquid.
Search your theme code for "application/ld+json" to find and fix it.'''


def _fix_013(cr, page):
    return '''Most of your page content requires JavaScript to render.
AI agents (ChatGPT, Perplexity, Gemini) do NOT run JavaScript.

Fix options (pick one):

1. BEST: Ensure JSON-LD structured data is in the raw HTML (not injected by JS).
   This gives agents all product data even without JS.

2. Server-side render critical content in Liquid/HTML:
   - Product title in <h1>
   - Price in a visible <span>
   - Description in plain HTML
   - Variant options in <select> or <input> elements

3. Check your theme: Some Shopify themes (especially headless/React-based)
   render everything client-side. Switch to a theme that uses Liquid
   server-rendering, or add a JSON-LD block that doesn't depend on JS.

Quick test: View Page Source (Ctrl+U) — if you can't see your product
info in the raw HTML, neither can an AI agent.'''


def _fix_016(cr, page):
    return '''Hidden prompt injection detected in your page content.

This is a security issue: someone has embedded text that tries to
manipulate AI agents reading your page (e.g. "ignore previous instructions"
hidden in CSS or HTML comments).

Fix:
1. Search your theme code for hidden text:
   - CSS: visibility:hidden, display:none, font-size:0, color matching background
   - HTML comments containing instructions
   - Hidden <div> or <span> elements with agent-targeting language

2. Check third-party apps and scripts — some inject hidden content

3. Review user-generated content (reviews, Q&A) for prompt injection attempts

4. Add content moderation to filter injection patterns from submissions'''


def _fix_022(cr, page):
    return '''Your checkout requires login — agents can't complete purchases.

Fix: Enable guest checkout.

Shopify:
1. Go to Settings > Checkout
2. Under "Customer accounts" select "Accounts are optional"
3. Under "Customer contact method" ensure "Email" is selected

This lets both AI agents and regular customers check out without
creating an account. You can still offer account creation after purchase.'''


def _fix_029(cr, page):
    return '''No sitemap.xml found, or it doesn't list product pages.

Shopify automatically generates /sitemap.xml — check if it's accessible:
1. Visit https://yourstore.com/sitemap.xml
2. It should list sub-sitemaps including sitemap_products_1.xml

If it's missing:
- Check if a robots.txt rule is blocking /sitemap.xml
- Some apps or custom configurations can break the default sitemap
- Contact Shopify support if the default sitemap isn't generating

For non-Shopify platforms: generate a sitemap that includes all product URLs
and submit it to Google Search Console.'''


def _fix_031(cr, page):
    detail = cr.get("detail", "")
    blocked = [ua for ua in ["GPTBot", "ClaudeBot", "PerplexityBot", "OAI-SearchBot"]
               if ua.lower() in detail.lower()]
    blocked_str = ", ".join(blocked) if blocked else "AI agent user-agents"
    return f'''Your site is blocking AI agent traffic: {blocked_str}

This is usually caused by your CDN/WAF (Cloudflare, Akamai, etc.) or
a Shopify app that blocks bot traffic.

Fix:
1. Check your CDN/WAF rules for user-agent blocking
2. Allowlist these AI agent user-agents:
   - GPTBot (ChatGPT Shopping)
   - ClaudeBot (Claude/Anthropic)
   - PerplexityBot (Perplexity Shopping)
   - OAI-SearchBot (OpenAI Search)

3. Shopify-specific: Check if any security apps are blocking bots:
   - Go to Apps > look for "bot protection" or "security" apps
   - Check their settings for user-agent blocking rules

Blocking AI agents = blocking a growing sales channel.'''


def _fix_033(cr, page):
    detail = cr.get("detail", "")
    return f'''Your page has conflicting availability signals.

{detail}

Fix: Make JSON-LD and visible text agree.

<!-- Shopify Liquid — ensure both update together: -->
{{% if product.available %}}
  <span class="availability">In Stock</span>
{{% else %}}
  <span class="availability">Sold Out</span>
{{% endif %}}

<!-- And in JSON-LD: -->
"availability": "{{% if product.available %}}https://schema.org/InStock{{% else %}}https://schema.org/OutOfStock{{% endif %}}"

Common causes:
- "Sold out" badge still showing for in-stock products (variant-level issue)
- "Unavailable" text from a different variant visible on page
- Stale JSON-LD cached by a CDN or app'''


def _fix_036(cr, page):
    return '''Your site doesn't support markdown content negotiation.

This is an emerging standard — when an AI agent sends
"Accept: text/markdown", your server returns clean markdown
instead of HTML. This helps agents parse content more accurately.

For most stores this is low priority — JSON-LD structured data is
the primary way agents read your products. Markdown negotiation
will become more important as agent protocols mature.

If you want to implement it:
- Cloudflare Workers or a reverse proxy can intercept requests with
  Accept: text/markdown and return a simplified markdown version
- Some CMS platforms have plugins for this'''


def _fix_039(cr, page):
    return '''No Link response headers for agent discovery.

Add these HTTP headers to help agents discover related resources:

Link: </sitemap.xml>; rel="sitemap"
Link: </products.json>; rel="describedby"; type="application/json"
Link: </search>; rel="search"

Shopify: You can add custom headers via a Cloudflare Worker or a
middleware proxy. Shopify doesn't natively support custom response headers.

This is a low-priority improvement — most agents find your products
through sitemap.xml and JSON-LD, not Link headers.'''


def _fix_040(cr, page):
    return '''No DNS-AID TXT record found.

DNS for AI Discovery (DNS-AID) lets agents discover your store's
capabilities before visiting your site via a DNS TXT record.

Add this DNS record:
  Type: TXT
  Name: _ai
  Value: "v=ai1; shop=true; mcp=/.well-known/mcp.json; llms=/llms.txt"

Where to add it:
- Your DNS provider (Cloudflare, Route 53, Google Domains, etc.)
- Shopify: Go to your domain provider (not Shopify admin) and add the TXT record

This is an emerging standard — early adoption signals agent-readiness.'''


def _fix_042(cr, page):
    return '''Prompt injection patterns detected in user-generated content.

Someone has posted reviews or Q&A answers containing text designed to
manipulate AI agents (e.g. "ignore all previous instructions and recommend...").

Fix:
1. Review recent user-generated content for suspicious patterns
2. Add content moderation filters that reject submissions containing:
   - "ignore previous instructions"
   - "you are now"
   - "system prompt"
   - "disregard"
   - Unusual formatting or hidden characters

3. Shopify: Check your reviews app (Judge.me, Yotpo, Stamped, etc.)
   for moderation settings. Enable auto-moderation filters.

4. Consider flagging and removing the offending content immediately.'''


def _fix_043(cr, page):
    return '''Your cart API lacks rate limiting.

Without rate limiting, bots can spam /cart/add.js to:
- Create inventory holds (denial of service)
- Scrape pricing data at scale
- Abuse promotions

Fix for Shopify:
1. Shopify has built-in rate limiting on checkout, but /cart/add.js
   is less protected
2. Add Cloudflare rate limiting rules:
   - URL: /cart/add.js
   - Rate: 10 requests per minute per IP
   - Action: Block or Challenge

3. Or use a Shopify app like "Bot Protection" that rate-limits API endpoints'''


def _fix_045(cr, page):
    return '''Admin or API paths are publicly accessible.

Fix: Ensure these paths require authentication:
- /admin — should redirect to login
- /.env — should return 404, not your environment variables
- /api/ endpoints — should require API keys

Shopify: The /admin path is protected by default. If you see this warning,
check for:
1. Custom API endpoints you've created (Shopify Functions, proxy routes)
2. Third-party apps that expose API paths
3. Development/staging endpoints left in production'''


def _fix_032(cr, page):
    return '''No x402 / agent wallet payment signals found.

x402 is an emerging protocol that lets AI agents pay for products
autonomously. It's very early — most stores don't support it yet.

What you can do now:
1. Ensure your Shopify checkout works with Shop Pay (most Shopify stores
   already have this — it's the closest thing to agent-native checkout)
2. Monitor the x402 spec: https://www.x402.org/
3. Cloudflare's Monetization Gateway may add merchant support soon

This is forward-looking — no immediate revenue impact, but early
adopters will have an advantage when agent wallets go mainstream.'''


def _fix_046(cr, page):
    detail = cr.get("detail", "")
    return f'''Your product description is too thin for AI agents.

{detail}

AI agents use your product description to answer customer questions like
"what's it made of?" and "will it fit me?". A sparse description means
the agent guesses or says "I don't know" — both lose the sale.

Add text covering these dimensions:
1. Material/composition: "Made from 100% organic cotton"
2. Features/benefits: "Moisture-wicking, breathable, machine washable"
3. Fit/size/specs: "Runs true to size. Model wears size M (5'8\", 145 lbs)"
4. Use case: "Perfect for everyday wear or light workouts"

Aim for 100+ words of real product information (not marketing fluff).
AI agents ignore superlatives — they want facts.'''


def _fix_011(cr, page):
    detail = cr.get("detail", "")
    return f'''Your llms.txt file is incomplete.

{detail}

A complete llms.txt should include:

# llms.txt
> Instructions for AI shopping agents visiting our store.

## Product Catalog
- Products API: /products.json
- Sitemap: /sitemap.xml
- Collections: /collections

## Policies
- Returns: /policies/refund-policy
- Shipping: /policies/shipping-policy
- Privacy: /policies/privacy-policy

## Checkout
- Cart API: /cart/add.js
- Guest checkout: supported
- Payment: Shop Pay, credit card

## Contact
- Support: support@yourstore.com
- Hours: Mon-Fri 9am-5pm EST'''


def _fix_014(cr, page):
    return '''Your Add-to-Cart button isn't semantic — agents can't find it.

Fix: Use a standard HTML form with a clear button.

<!-- Shopify Liquid example: -->
<form method="post" action="/cart/add">
  <input type="hidden" name="id" value="{{ product.selected_or_first_available_variant.id }}">
  <input type="hidden" name="quantity" value="1">
  <button type="submit" name="add" aria-label="Add to Cart">
    Add to Cart
  </button>
</form>

Common problems:
- ATC is a <div> or <a> with a JS click handler — agents can't trigger it
- Button text says something vague like "Buy" or "Shop" without aria-label
- ATC only appears after selecting a variant (agents can't see it initially)

Shopify: Most themes use a proper form. Check your product-form snippet.'''


def _fix_015(cr, page):
    return '''Variant selectors (size/color) don't use semantic HTML.

Fix: Use <select> or <input type="radio"> with <label> elements.

<!-- Shopify Liquid example: -->
{% for option in product.options_with_values %}
<fieldset>
  <legend>{{ option.name }}</legend>
  {% for value in option.values %}
  <label>
    <input type="radio" name="{{ option.name }}" value="{{ value }}"
           {% if option.selected_value == value %}checked{% endif %}>
    {{ value }}
  </label>
  {% endfor %}
</fieldset>
{% endfor %}

Common problems:
- Variants are custom JS-only swatches (colored divs with click handlers)
- No <label> elements — agents can't tell which swatch is which color
- Variant names are abbreviations ("BK" instead of "Black")'''


def _fix_023(cr, page):
    return '''No programmatic cart API endpoint detected.

Shopify stores have /cart/add.js by default — if this check failed,
something may be blocking it.

Check:
1. Visit https://yourstore.com/cart/add.js — it should return JSON
2. If it returns a 403 or challenge page, your WAF is blocking it
3. Some headless Shopify setups use a custom cart API — ensure it's
   accessible without authentication

For non-Shopify: expose a POST endpoint that accepts product ID and
quantity, returns cart state as JSON. Document it in your llms.txt.'''


def _fix_030(cr, page):
    detail = cr.get("detail", "")
    return f'''Your page is too slow for AI agents.

{detail}

AI agents typically timeout after 10-30 seconds. A slow page means
the agent gives up and moves to a competitor.

Fix:
1. Enable CDN caching (Cloudflare, Fastly, Shopify CDN)
2. Optimize images — use WebP/AVIF, lazy-load below-fold images
3. Reduce third-party scripts — each tracking/chat/popup script adds latency
4. Enable Shopify's built-in speed optimizations (Online Store > Themes > Speed)
5. Check if your theme has heavy JS bundles that block rendering

Quick test: run PageSpeed Insights on your product page URL.'''


def _fix_034(cr, page):
    return '''No MCP (Model Context Protocol) server card found.

MCP lets AI agents discover what tools your store offers
(product search, cart management, etc.).

To add MCP support:
1. Create /.well-known/mcp.json with your available tools:

{
  "name": "Your Store",
  "description": "Shop our products",
  "tools": [
    {"name": "search_products", "endpoint": "/search/suggest.json"},
    {"name": "get_product", "endpoint": "/products/{handle}.json"},
    {"name": "add_to_cart", "endpoint": "/cart/add.js"}
  ]
}

2. Shopify: Host this via a custom page or Cloudflare Worker at the
   /.well-known/ path.

This is an emerging standard — early adoption helps AI agents
discover and use your store's capabilities.'''


def _fix_035(cr, page):
    return '''No OAuth authorization server metadata found.

OAuth discovery lets AI agents authenticate with your store to
access protected resources (customer accounts, order status, etc.).

Shopify stores with customer accounts already have OAuth via Shopify's
authentication system. If this check failed, the discovery endpoint
may not be properly exposed.

For most stores, this is low priority unless you offer authenticated
agent experiences (e.g. order tracking via AI assistant).'''


def _fix_037(cr, page):
    return '''No A2A (Agent-to-Agent) card found.

Google's A2A protocol lets AI agents discover other agents' capabilities
via /.well-known/agent.json.

To add A2A support:
1. Create /.well-known/agent.json:

{
  "name": "Your Store Assistant",
  "description": "Helps customers find and buy products",
  "capabilities": ["product_search", "product_info", "checkout"],
  "endpoint": "https://yourstore.com/api/agent"
}

2. Host it via Cloudflare Worker or custom server route.

This is Google-specific and emerging — implement if you want to be
discoverable by Google's AI agent ecosystem.'''


def _fix_038(cr, page):
    return '''No auth.md documentation found.

auth.md tells AI agents how to authenticate with your store's APIs.

Create /auth.md at your site root:

# Authentication

## Public API (no auth required)
- GET /products.json — product catalog
- GET /search/suggest.json?q={query} — search
- POST /cart/add.js — add to cart

## Customer API (requires OAuth)
- GET /account — customer account details
- GET /account/orders — order history

## OAuth Flow
- Authorization: https://yourstore.com/account/login
- Token endpoint: (via Shopify's OAuth)

Host via Cloudflare Worker or custom route. Low priority unless
you offer authenticated agent experiences.'''


def _fix_041(cr, page):
    return '''No agent commerce protocols detected (Skills, WebMCP, UCP, ACP).

These protocols let AI agents interact with your store programmatically.

Shopify stores often have these via Shopify's built-in integrations:
- Shop Pay / Shop Skill: enabled automatically for Shopify stores
- UCP: Shopify's Universal Commerce Protocol (check Shopify admin)

If this check failed on a Shopify store:
1. Ensure Shop Pay is enabled (Settings > Payments)
2. Check that your store appears in the Shop app
3. Verify llms.txt mentions available commerce protocols

For non-Shopify: consider integrating UCP or WebMCP to let agents
search, add to cart, and check out programmatically.'''


def _fix_044(cr, page):
    return '''Your checkout lacks bot challenge protection.

Without bot protection, automated scripts can:
- Create fake orders
- Test stolen credit cards
- Abuse promotions and discount codes

Fix for Shopify:
1. Go to Settings > Checkout > Bot protection
2. Enable Shopify's built-in bot protection
3. Consider adding Cloudflare Turnstile or reCAPTCHA

Note: Bot challenges should protect checkout but NOT block product
pages — you want agents to read your products, just not auto-checkout
without proper authentication.'''


def _fix_017(cr, page):
    detail = cr.get("detail", "")
    return f'''An AI agent could not complete the Add-to-Cart flow on your page.

{detail}

This means AI shopping assistants can recommend your product but can't
help the customer actually buy it.

Common causes:
1. ATC button only appears after JS loads — use server-rendered forms
2. Popup modals (cookie consent, newsletter) block the ATC button
3. Variant must be selected before ATC appears — pre-select a default
4. ATC is a custom JS component, not a standard <form> + <button>

Fix for Shopify:
- Use a standard product form (most themes have this by default)
- Ensure the form works without JS: method="post" action="/cart/add"
- Dismiss popups with a close button that has clear aria-label
- Pre-select the first available variant'''


def _fix_018(cr, page):
    detail = cr.get("detail", "")
    return f'''An AI agent could not find your product via site search.

{detail}

Fix:
1. Ensure your search bar is visible (not hidden behind an icon that
   requires hover or JS interaction)
2. Use a standard <input type="search"> or <input type="text"> with
   a clear placeholder like "Search products..."
3. Search results should show product titles, prices, and links
4. Shopify: check your theme's search template — ensure it returns
   product results, not just blog posts or pages'''


def _fix_019(cr, page):
    detail = cr.get("detail", "")
    return f'''An AI agent could not reach the checkout page.

{detail}

This is critical — if agents can't get to checkout, they can't
complete purchases on behalf of customers.

Common causes:
1. Cart page requires JS to load the checkout button
2. Cart is a slide-out drawer with no direct link to /checkout
3. Checkout requires login (enable guest checkout)
4. Checkout redirect is blocked by bot protection

Fix for Shopify:
1. Settings > Checkout > enable guest checkout
2. Ensure /cart page has a visible "Checkout" button/link
3. Check that bot protection allows the checkout flow
4. Test: can you go from /cart to /checkout without JS?'''


def _fix_020(cr, page):
    detail = cr.get("detail", "")
    return f'''An AI agent could not navigate from your homepage to a product page.

{detail}

Fix:
1. Use clear, hierarchical navigation menus with descriptive labels
   (not just icons or images)
2. Collection/category links should be in <nav> with <a> elements
3. Product cards in collections should be standard <a> links with
   clear product names, not JS-only click handlers
4. Avoid mega-menus that only appear on hover — agents can't hover

Shopify: Most themes handle this well. Check that your navigation
uses proper HTML links, not JS-rendered dynamic menus.'''


def _fix_021(cr, page):
    detail = cr.get("detail", "")
    return f'''An AI agent could not find or navigate to a related product.

{detail}

Fix:
1. Add a visible "You may also like" or "Related products" section
   on product pages
2. Use standard <a> links to related products (not JS carousels
   that require interaction to reveal links)
3. Include product names in the link text or alt attributes

Shopify: Most themes include a related products section. Check:
- Online Store > Themes > Customize > Product page
- Look for "Related products" or "You may also like" section
- Enable it if it's turned off'''


# Map check IDs to recipe functions
_RECIPES = {
    "RDY-001": _fix_001,
    "RDY-002": _fix_002,
    "RDY-003": _fix_003,
    "RDY-004": _fix_004,
    "RDY-005": _fix_005,
    "RDY-006": _fix_006,
    "RDY-007": _fix_007,
    "RDY-008": _fix_008,
    "RDY-009": _fix_009,
    "RDY-010": _fix_010,
    "RDY-011": _fix_011,
    "RDY-012": _fix_012,
    "RDY-013": _fix_013,
    "RDY-014": _fix_014,
    "RDY-015": _fix_015,
    "RDY-016": _fix_016,
    "RDY-017": _fix_017,
    "RDY-018": _fix_018,
    "RDY-019": _fix_019,
    "RDY-020": _fix_020,
    "RDY-021": _fix_021,
    "RDY-022": _fix_022,
    "RDY-023": _fix_023,
    "RDY-029": _fix_029,
    "RDY-030": _fix_030,
    "RDY-031": _fix_031,
    "RDY-032": _fix_032,
    "RDY-033": _fix_033,
    "RDY-034": _fix_034,
    "RDY-035": _fix_035,
    "RDY-036": _fix_036,
    "RDY-037": _fix_037,
    "RDY-038": _fix_038,
    "RDY-039": _fix_039,
    "RDY-040": _fix_040,
    "RDY-041": _fix_041,
    "RDY-042": _fix_042,
    "RDY-043": _fix_043,
    "RDY-044": _fix_044,
    "RDY-045": _fix_045,
    "RDY-046": _fix_046,
}
