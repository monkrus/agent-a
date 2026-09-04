#!/usr/bin/env python3
"""
scorers.py — readiness-track graders.

Two families, mirroring the audit track's programmatic-vs-judge split:

  STATIC probes  -> deterministic PASS / FAIL / UNKNOWN on the fetched page.
  SHOPPER grades -> aggregate N agent answers into a pass rate:
       correctness: fraction of runs matching ground truth from the page.
       consistency: modal-answer agreement across runs (no ground truth needed);
                    low self-agreement means the page reads ambiguously to agents.

UNKNOWN is a first-class result (e.g. can't derive ground truth, or JS-only
page). It is disclosed in the report, never silently treated as PASS — same
discipline as the audit track's coverage section.
"""
from __future__ import annotations
import re
from collections import Counter
from html.parser import HTMLParser as _HTMLParser


class _ScriptStripper(_HTMLParser):
    """Strip <script> (and optionally <style>) tag content using stdlib parser."""
    def __init__(self, strip_styles=False):
        super().__init__()
        self._parts = []
        self._skip = False
        self._skip_tags = {'script'}
        if strip_styles:
            self._skip_tags.add('style')
    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        elif not self._skip:
            self._parts.append(self.get_starttag_text() or '')
    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False
        elif not self._skip:
            self._parts.append(f'</{tag}>')
    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)
    def handle_entityref(self, name):
        if not self._skip:
            self._parts.append(f'&{name};')
    def handle_charref(self, name):
        if not self._skip:
            self._parts.append(f'&#{name};')
    def get_result(self):
        return ''.join(self._parts)


def _strip_scripts(html_str):
    """Remove <script> tag content from HTML using stdlib parser."""
    s = _ScriptStripper()
    s.feed(html_str)
    return s.get_result()


class _ScriptCollector(_HTMLParser):
    """Collect content inside <script> tags."""
    def __init__(self):
        super().__init__()
        self.scripts = []
        self._in_script = False
        self._current = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self._in_script = True
            self._current = []
    def handle_endtag(self, tag):
        if tag == 'script' and self._in_script:
            self._in_script = False
            self.scripts.append(''.join(self._current))
    def handle_data(self, data):
        if self._in_script:
            self._current.append(data)


def _script_sizes(html_str):
    """Return (total_script_bytes, script_count) using stdlib parser."""
    c = _ScriptCollector()
    c.feed(html_str)
    return sum(len(s) for s in c.scripts), len(c.scripts)

from shopper import _jsonld_offers, _jsonld_price, _jsonld_availability

POLICY_WORDS = ("return", "refund", "exchange")
AGENT_UAS = ("gptbot", "oai-searchbot", "google-extended", "perplexitybot",
             "claudebot", "anthropic-ai", "ccbot")


# ---- STATIC probes (detect name -> verdict) --------------------------------
def static_jsonld_product(page):
    obj, off = _jsonld_offers(page)
    if not obj:
        return "FAIL", "No schema.org/Product JSON-LD found."
    if not off or off.get("price") is None:
        return "FAIL", "Product JSON-LD present but offers.price missing."
    if not off.get("availability"):
        return "FAIL", "Product JSON-LD has price but no availability."
    return "PASS", "Product JSON-LD with price and availability present."


def static_price_in_html(page):
    html = page.get("html", "") or ""
    # Strip script bodies AND HTML tags (including attributes like
    # <meta itemprop="price" content="$59">) so only truly visible
    # text-node prices count as server-rendered.
    no_scripts = _strip_scripts(html)
    visible = re.sub(r"<[^>]{1,500}>", " ", no_scripts)
    matches = re.findall(r"[$£€]\s?(\d[\d,]*\.?\d*)", visible)
    if not matches:
        if _jsonld_price(page) is not None:
            return "FAIL", "Price only in structured data, not in visible server HTML."
        return "FAIL", "No price string in server HTML (likely JS-rendered only)."

    # If we know the product price from JSON-LD, check it specifically appears
    # in visible HTML — avoids false PASS from "$5 shipping" on a $200 product
    gt_price = _jsonld_price(page)
    if gt_price is not None:
        for m in matches:
            try:
                v = float(m.replace(",", ""))
                if abs(v - gt_price) < 0.01:
                    return "PASS", f"Product price ${gt_price:.2f} found in visible server HTML."
            except ValueError:
                continue
        return "FAIL", (f"Currency strings found in HTML but none match product price "
                        f"${gt_price:.2f} — visible price may be JS-rendered.")

    return "PASS", "Currency-formatted price present in server HTML."


def static_robots_allows_agents(page):
    robots = page.get("robots")
    if robots is None:
        return "UNKNOWN", "robots.txt not fetched (local file or unreachable)."

    blocked = []
    catalog_blocked = []

    # Parse robots.txt into per-UA stanzas
    blocks = re.split(r"(?im)^\s*user-agent:", robots)
    wildcard_disallows = []

    for blk in blocks:
        head = blk.strip().lower()
        ua = head.split("\n", 1)[0].strip()
        # Extract all Disallow directives in this stanza
        disallows = re.findall(r"(?im)^\s*disallow:\s*(.+)", blk)
        disallows = [d.strip() for d in disallows]

        is_agent_ua = any(a in ua for a in AGENT_UAS)
        is_wildcard = ua == "*"

        if is_wildcard:
            wildcard_disallows = disallows

        if is_agent_ua or is_wildcard:
            for d in disallows:
                if d == "/":
                    label = ua if is_agent_ua else "* (all crawlers)"
                    if label not in blocked:
                        blocked.append(label)
                elif d.rstrip("/") in ("/products", "/collections", "/catalog"):
                    label = ua if is_agent_ua else "* (all crawlers)"
                    if label not in catalog_blocked:
                        catalog_blocked.append(label)

    # Agent-specific stanzas that re-allow override the wildcard block
    # (a more-specific Allow: / for an agent UA cancels a wildcard Disallow: /)
    for blk in blocks:
        head = blk.strip().lower()
        ua = head.split("\n", 1)[0].strip()
        if any(a in ua for a in AGENT_UAS):
            allows = re.findall(r"(?im)^\s*allow:\s*(.+)", blk)
            allows = [a.strip() for a in allows]
            if "/" in allows:
                # This agent is explicitly re-allowed — remove wildcard block
                blocked = [b for b in blocked if b != "* (all crawlers)"]

    if blocked:
        return "FAIL", f"robots.txt blocks agent user-agents: {', '.join(blocked)}."
    if catalog_blocked:
        return "FAIL", f"robots.txt blocks product catalog paths for: {', '.join(catalog_blocked)}."
    return "PASS", "No agent user-agents fully disallowed in robots.txt."


def static_policy_text_present(page):
    text = (page.get("text", "") or "").lower()
    links = " ".join(a for _, a in page.get("links", [])).lower()
    hrefs = " ".join(h for h, _ in page.get("links", [])).lower()
    if any(w in text for w in POLICY_WORDS) or any(w in links for w in POLICY_WORDS) \
            or "return" in hrefs or "refund" in hrefs:
        return "PASS", "Return/refund policy referenced in text or links."
    return "FAIL", "No discoverable return/refund policy text or link."


def static_llms_txt_present(page):
    v = page.get("llms_txt")
    if v is None:
        return "UNKNOWN", "llms.txt not probed (local file mode)."
    return ("PASS", "llms.txt present.") if v else ("FAIL", "No llms.txt at site root.")


def static_llms_txt_quality(page):
    content = page.get("llms_txt_content")
    if not content:
        if page.get("llms_txt") is None:
            return "UNKNOWN", "llms.txt not probed (local file mode)."
        return "FAIL", "No llms.txt found — nothing to validate."

    issues = []
    cl = content.lower()

    # Check for key sections a good llms.txt should have
    has_products = any(k in cl for k in ("/products", "/collections", "catalog", "product search"))
    has_policies = any(k in cl for k in ("/policies", "refund", "return", "shipping"))
    has_sitemap = "sitemap" in cl

    if not has_products:
        issues.append("no product/catalog paths")
    if not has_policies:
        issues.append("no policy links")
    if not has_sitemap:
        issues.append("no sitemap reference")

    # Check for broken-looking URLs (relative paths without a domain)
    import re as _re
    urls = _re.findall(r'https?://[^\s<>"\']+', content)
    if not urls:
        issues.append("no absolute URLs found")

    if not issues:
        return "PASS", "llms.txt has product paths, policy links, and sitemap."
    return "FAIL", f"llms.txt incomplete: {'; '.join(issues)}."


def static_jsonld_quality(page):
    obj, off = _jsonld_offers(page)
    if not obj:
        return "FAIL", "No schema.org/Product JSON-LD to validate."

    issues = []
    if not obj.get("name"):
        issues.append("missing product name")
    if not obj.get("image"):
        issues.append("missing product image")
    brand = obj.get("brand")
    if not brand or (isinstance(brand, dict) and not brand.get("name")):
        issues.append("missing brand")
    if not obj.get("description"):
        issues.append("missing description")

    if off:
        price = off.get("price")
        currency = off.get("priceCurrency")
        avail = off.get("availability", "")
        if price is None:
            issues.append("missing price")
        if not currency:
            issues.append("missing priceCurrency")
        if not avail:
            issues.append("missing availability")
        elif "schema.org" not in str(avail).lower():
            issues.append(f"availability not a schema.org URL: {avail}")
    else:
        issues.append("no offers block")

    if not issues:
        return "PASS", "JSON-LD Product is complete: name, image, brand, price, currency, availability."
    return "FAIL", f"JSON-LD Product incomplete: {'; '.join(issues)}."


def static_js_render_ratio(page):
    html = page.get("html", "") or ""
    text = page.get("text", "") or ""
    import re as _re

    # Total HTML length
    html_len = len(html)
    if html_len < 100:
        return "UNKNOWN", "Page too small to evaluate rendering ratio."

    # Script content size (exclude external scripts with src= and empty body)
    script_len, _ = _script_sizes(html)

    # Visible text vs total page (strip tags for non-script content)
    text_len = len(text)
    # More robust: measure text outside scripts
    non_script_html = _strip_scripts(html)
    non_script_text = _re.sub(r"<[^>]{1,500}>", " ", non_script_html)
    non_script_text_len = len(non_script_text.strip())

    script_ratio = round(script_len / html_len * 100, 1) if html_len else 0
    text_ratio = round(text_len / html_len * 100, 1) if html_len else 0

    detail = f"Script: {script_ratio}% of page, visible text: {text_ratio}% of page."

    # If rendered DOM available, show comparison
    rendered_text = page.get("rendered_text", "")
    if rendered_text:
        rendered_len = len(rendered_text)
        gap = rendered_len - text_len
        if gap > 200:
            detail += f" Rendered DOM has {gap} more chars of text — JS hides content from text-mode agents."

    # Evaluate JS render ratio on its own merits.
    # JSON-LD coverage is handled by RDY-001/RDY-012 — this check measures
    # whether the *visible page content* is server-rendered or JS-gated.
    if script_ratio > 60 and text_ratio < 8:
        return "FAIL", f"High JS dependency — most visible content requires JS execution. {detail}"
    if script_ratio > 50 and text_ratio < 5 and non_script_text_len < 500:
        return "FAIL", f"Page is heavily JS-rendered — agents see very little content. {detail}"
    return "PASS", f"Acceptable text-to-script ratio for agents. {detail}"


def static_cart_semantic(page):
    html = page.get("html", "") or ""
    import re as _re
    hl = html.lower()

    # Look for forms with cart-related actions
    has_cart_form = bool(_re.search(
        r'<form[^>]*(action=["\'][^"\']*cart[^"\']*["\']|id=["\'][^"\']*cart[^"\']*["\'])', hl))

    # Look for buttons with add-to-cart semantics
    has_cart_button = bool(_re.search(
        r'<(button|input)[^>]*(add.to.cart|addtocart|add-to-cart|data-action=["\']add)', hl))

    # Look for name/data-testid/aria-label on submit-like elements
    has_semantic_btn = bool(_re.search(
        r'<(button|input)[^>]*(name=["\']|data-testid=["\']|aria-label=["\'])[^>]*(submit|cart|buy|purchase)', hl))

    if has_cart_form and (has_cart_button or has_semantic_btn):
        return "PASS", "Add-to-Cart form with semantic button found — agents can interact."
    if has_cart_form or has_cart_button:
        return "PASS", "Add-to-Cart element found (form or button with cart semantics)."
    if has_semantic_btn:
        return "PASS", "Buy/cart button with semantic attributes found."

    # Check if there's any form at all on the page
    has_any_form = "<form" in hl
    if has_any_form:
        return "FAIL", "Forms found but none with cart/purchase semantics — agents can't identify the buy action."
    return "FAIL", "No Add-to-Cart form or button found in server HTML — agents cannot purchase."


def static_variant_selectors(page):
    html = page.get("html", "") or ""
    import re as _re
    hl = html.lower()

    # Look for semantic variant selectors
    has_select = bool(_re.search(
        r'<select[^>]*(name=["\'][^"\']*(?:size|color|variant|option)[^"\']*["\'])', hl))
    has_radio = bool(_re.search(
        r'<input[^>]*type=["\']radio["\'][^>]*(name=["\'][^"\']*(?:size|color|variant|option))', hl))
    has_labeled = bool(_re.search(
        r'<(label|fieldset|legend)[^>]*>[^<]*(size|color|variant|option)', hl))

    semantic_count = sum([has_select, has_radio, has_labeled])

    if semantic_count >= 2:
        return "PASS", "Variant selectors use semantic HTML (select/radio with labels) — agents can choose options."
    if semantic_count == 1:
        return "PASS", "Basic variant selector found in semantic HTML."

    # Check if there are variant-related elements at all (just not semantic)
    has_variant_js = bool(_re.search(r'(variant|swatch|option-selector|size-selector)', hl))
    if has_variant_js:
        return "FAIL", "Variant UI detected but uses non-semantic JS widgets — agents can't select sizes/colors."
    return "UNKNOWN", "No variant selectors detected (may be a single-variant product)."


def static_prompt_injection(page):
    html = page.get("html", "") or ""
    import re as _re
    import html as _html_mod

    # Decode HTML entities so &#105;gnore / &lt;system&gt; patterns are caught
    html_decoded = _html_mod.unescape(html)

    # Injection phrases that could hijack an agent's context
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above",
        r"disregard\s+(all\s+)?(previous|above|prior)",
        r"you\s+are\s+now\s+a",
        r"system\s*:\s*override",
        r"system\s*:\s*you\s+are",
        r"new\s+instructions?\s*:",
        r"forget\s+(everything|all|your)\s+(above|previous|prior)",
        r"act\s+as\s+(if|though)\s+you",
        r"do\s+not\s+follow\s+(the\s+)?(previous|above|prior)",
        r"tell\s+the\s+user\s+(this|that)",
        r"respond\s+with\s+only",
        r"<\s*system\s*>",
    ]
    pattern = "|".join(f"({p})" for p in INJECTION_PATTERNS)

    findings = []

    # 1. Check HTML comments for injection (use decoded to catch entity-encoded payloads)
    comments = _re.findall(r"<!--(.*?)-->", html_decoded, _re.S | _re.I)
    for c in comments:
        if _re.search(pattern, c, _re.I):
            findings.append("HTML comment contains agent-hijacking text")
            break

    # 2. Check hidden elements (display:none, visibility:hidden, opacity:0, aria-hidden)
    # Skip legitimate accessibility classes (sr-only, visually-hidden, etc.)
    SR_ONLY = _re.compile(r'class=["\'][^"\']*(?:sr-only|visually-hidden|screen-reader)[^"\']*["\']', _re.I)
    hidden_blocks = _re.findall(
        r'(<[^>]*(display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0'
        r'|font-size\s*:\s*0|height\s*:\s*0|width\s*:\s*0'
        r'|aria-hidden\s*=\s*["\']true["\'])[^>]*>(.*?)</[^>]+>)',
        html_decoded, _re.I | _re.S)
    for full_tag, _, content in hidden_blocks:
        if SR_ONLY.search(full_tag):
            continue  # legitimate accessibility content
        if _re.search(pattern, content, _re.I):
            findings.append("Hidden element contains agent-hijacking text")
            break

    # 3. Check for invisible text via color tricks (white-on-white, 0px font)
    # Look for style with color:#fff or color:white on non-body elements
    stealth_blocks = _re.findall(
        r'<[^>]*(color\s*:\s*(?:white|#fff(?:fff)?|rgba?\(\s*255))[^>]*>(.*?)</[^>]+>',
        html_decoded, _re.I | _re.S)
    for _, content in stealth_blocks:
        if _re.search(pattern, content, _re.I):
            findings.append("Invisible text (color trick) contains agent-hijacking text")
            break

    # 4. Check all page text for injection patterns in obvious places
    text = (page.get("text", "") or "").lower()
    # Only flag visible text for unambiguous injection — patterns like
    # "you are now a" match marketing copy ("You are now a member of our
    # rewards club"), so require co-occurrence with instruction-target words.
    VISIBLE_SAFE = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above",
        r"disregard\s+(all\s+)?(previous|above|prior)",
        r"system\s*:\s*override",
        r"system\s*:\s*you\s+are",
    ]
    for p in VISIBLE_SAFE:
        if _re.search(p, text, _re.I):
            findings.append("Visible page text contains suspicious agent-override phrasing")
            break

    if not findings:
        return "PASS", "No prompt injection patterns detected in page content."
    return "FAIL", f"Potential prompt injection found: {'; '.join(findings)}."


def static_guest_checkout(page):
    probe = page.get("checkout_probe")
    checkout_html = page.get("checkout_html")
    if probe is None and checkout_html is None:
        return "UNKNOWN", "Checkout page not probed (local file mode)."

    # Handle redirect cases from the no-redirect probe
    if probe and probe.get("redirect_reason"):
        reason = probe["redirect_reason"]
        final = probe.get("final_url", "/checkout")
        if reason == "redirected_to_login":
            return "FAIL", f"/checkout redirected to {final} — login required before checkout. Agents cannot purchase without credentials."
        if reason == "redirected_to_cart":
            return "UNKNOWN", f"/checkout redirected to {final} — checkout not directly reachable without a cart session."

    if not checkout_html:
        return "UNKNOWN", "Checkout page returned no content."

    cl = checkout_html.lower()
    probed_url = probe.get("final_url", "/checkout") if probe else "/checkout"

    # Login wall indicators: page requires sign-in before showing checkout
    login_wall = any(phrase in cl for phrase in (
        "log in to checkout", "sign in to checkout", "login to checkout",
        "create an account to", "sign in to continue", "login to continue",
        "you must be logged in", "please log in", "please sign in",
        "account required",
    ))

    # Guest checkout indicators — require explicit guest affordances,
    # not weak signals like "email address" that appear on login pages too
    guest_ok = any(phrase in cl for phrase in (
        "guest checkout", "continue as guest", "checkout as guest",
        "without an account", "no account needed",
    ))

    # Login wall short-circuits — even if weak guest signals are present,
    # a login wall dominates unless there's an explicit guest option
    if login_wall and not guest_ok:
        return "FAIL", f"Page at {probed_url} requires login — no guest checkout option found. Agents cannot purchase without credentials."
    if guest_ok:
        return "PASS", f"Guest checkout available at {probed_url} — agents can purchase without an account."
    # Shopify default: checkout pages typically show email/shipping fields
    if "email" in cl and ("shipping" in cl or "address" in cl):
        return "PASS", f"Page at {probed_url} shows email and address fields (guest checkout likely available)."
    return "UNKNOWN", f"Could not determine guest checkout availability from {probed_url}."


def static_cart_api(page):
    cart_api = page.get("cart_api")
    if cart_api is None:
        return "UNKNOWN", "Cart API not probed (local file mode)."

    html = page.get("html", "") or ""
    hl = html.lower()

    # Check for /cart/add.js endpoint availability
    has_endpoint = cart_api

    # Also check if page references the cart API in its scripts
    has_cart_js_ref = any(path in hl for path in (
        "/cart/add.js", "/cart/add.json", "cart/add",
        "ajax_cart", "ajaxcart", "cart-api",
    ))

    if has_endpoint:
        return "PASS", "Cart API endpoint (/cart/add.js) responds — headless agents can add to cart programmatically."
    if has_cart_js_ref:
        return "PASS", "Cart API references found in page scripts (AJAX cart likely supported)."
    return "FAIL", "No cart API endpoint found — agents must interact with the DOM to add items to cart."


def static_search_accessible(page):
    """Proxy for RDY-018 browser check: can agents find site search?"""
    homepage = page.get("homepage_html")
    if homepage is None:
        return "UNKNOWN", "Homepage not fetched (local file mode)."
    if not homepage:
        return "FAIL", "Homepage not reachable — agents cannot discover site search."

    hl = homepage.lower()

    # Look for search form or input
    has_search_form = bool(re.search(
        r'<form[^>]*action=["\'][^"\']*search[^"\']*["\']', hl))
    has_search_input = bool(re.search(
        r'<input[^>]*type=["\']search["\']', hl))
    has_search_role = 'role="search"' in hl or "role='search'" in hl
    has_search_link = bool(re.search(r'href=["\'][^"\']*/search(/|\?|["\'])', hl))

    if has_search_form or has_search_input:
        return "PASS", "Site search form or input found on homepage — agents can search for products."
    if has_search_role:
        return "PASS", "Search landmark (role=search) found on homepage."
    if has_search_link:
        return "PASS", "Search page link found on homepage."
    return "FAIL", "No search form, search input, or search link found on homepage — agents cannot discover products via search."


def static_nav_accessible(page):
    """Proxy for RDY-020 browser check: can agents navigate from homepage?"""
    homepage = page.get("homepage_html")
    if homepage is None:
        return "UNKNOWN", "Homepage not fetched (local file mode)."
    if not homepage:
        return "FAIL", "Homepage not reachable — agents cannot navigate to products."

    hl = homepage.lower()

    # Check for nav element with product/collection links
    has_nav = "<nav" in hl
    product_links = len(re.findall(r'href=["\'][^"\']*/(products|collections)/[^"\']*["\']', hl))
    has_menu = bool(re.search(r'<(ul|ol)[^>]*class=["\'][^"\']*(?:menu|nav)[^"\']*["\']', hl))

    if has_nav and product_links >= 3:
        return "PASS", f"Navigation element with {product_links} product/collection links found — agents can browse."
    if product_links >= 5:
        return "PASS", f"{product_links} product/collection links found on homepage — agents can discover products."
    if has_nav and has_menu:
        return "PASS", "Navigation menu found on homepage — agents can browse categories."
    if product_links >= 1:
        return "PASS", f"{product_links} product link(s) found on homepage (limited but navigable)."
    return "FAIL", "No navigation with product or collection links found on homepage — agents cannot browse to products."


def static_related_products(page):
    """Proxy for RDY-021 browser check: can agents find related products?"""
    html = page.get("html", "") or ""
    hl = html.lower()

    # Look for related/recommended product sections
    related_section = bool(re.search(
        r'(you may also like|related products|customers also bought|'
        r'recommended for you|similar products|complete the look|'
        r'more from this collection|pairs well with|shop the look|'
        r'frequently bought together)', hl))

    # Count product links in the page (beyond the main product)
    product_slugs = re.findall(r'href=["\'][^"\']*/products/([^"\'/?#]+)', hl)
    distinct_products = len(set(product_slugs))

    if related_section and distinct_products >= 2:
        return "PASS", f"Related products section found with {distinct_products}+ product links — agents can compare."
    if related_section:
        return "PASS", "Related products section found on page."
    if distinct_products >= 3:
        return "PASS", f"{distinct_products} product links on page — agents can navigate to alternatives."
    return "FAIL", "No related products section or product links found — agents cannot compare alternatives."


def static_atc_flow_proxy(page):
    """Proxy for RDY-017 browser check: can agents likely complete ATC?
    Combines signals from semantic cart, variant selectors, and cart API."""
    html = page.get("html", "") or ""
    hl = html.lower()

    issues = []

    # Check ATC button
    has_cart_btn = bool(re.search(
        r'<(button|input)[^>]*(add.to.cart|addtocart|add-to-cart)', hl))
    has_cart_form = bool(re.search(
        r'<form[^>]*action=["\'][^"\']*cart[^"\']*["\']', hl))
    if not has_cart_btn and not has_cart_form:
        issues.append("no Add-to-Cart button or form found")

    # Check variant selectors
    has_select = bool(re.search(
        r'<select[^>]*name=["\'][^"\']*(?:size|color|variant|option)', hl))
    has_variant_js = bool(re.search(r'(variant|swatch|option-selector|size-selector)', hl))
    if has_variant_js and not has_select:
        issues.append("variant selectors use JS widgets instead of semantic HTML")

    # Check cart API
    cart_api = page.get("cart_api", False)
    cart_refs = any(p in hl for p in ("/cart/add.js", "/cart/add.json", "cart/add"))
    if not cart_api and not cart_refs:
        issues.append("no cart API endpoint available")

    if not issues:
        return "PASS", "Add-to-Cart flow looks agent-friendly: semantic button, proper selectors, cart API available."
    if len(issues) >= 2:
        return "FAIL", f"Add-to-Cart flow likely broken for agents: {'; '.join(issues)}."
    return "FAIL", f"Add-to-Cart flow has an issue: {issues[0]}."


def static_checkout_proxy(page):
    """Proxy for RDY-019 browser check: can agents reach checkout?"""
    probe = page.get("checkout_probe")
    checkout_html = page.get("checkout_html")
    cart_api = page.get("cart_api", False)

    if probe is None and checkout_html is None:
        return "UNKNOWN", "Checkout page not probed (local file mode)."

    html = page.get("html", "") or ""
    hl = html.lower()

    # Check if checkout link exists on the page
    has_checkout_link = bool(re.search(r'href=["\'][^"\']*checkout[^"\']*["\']', hl))
    has_cart_link = bool(re.search(r'href=["\'][^"\']*cart[^"\']*["\']', hl))

    # Handle redirect from probe
    if probe and probe.get("redirect_reason"):
        final = probe.get("final_url", "/checkout")
        reason = probe["redirect_reason"]
        if reason == "redirected_to_cart":
            if has_checkout_link:
                return "PASS", f"/checkout redirected to {final} (empty cart), but checkout link found on product page."
            return "UNKNOWN", f"/checkout redirected to {final} — checkout requires a cart session. Cart/checkout links: {'found' if has_cart_link else 'not found'}."
        if reason == "redirected_to_login":
            return "FAIL", f"/checkout redirected to {final} — login required before checkout."

    # Check if /checkout returns content
    checkout_reachable = bool(checkout_html and len(checkout_html) > 100)

    if checkout_reachable and (has_checkout_link or has_cart_link):
        return "PASS", "Checkout page is reachable and cart/checkout links found — agents can complete the purchase path."
    if checkout_reachable:
        return "PASS", "Checkout page is reachable at /checkout."
    if has_checkout_link:
        return "PASS", "Checkout link found on product page (checkout likely reachable after adding to cart)."
    if has_cart_link:
        return "UNKNOWN", "Cart link found but /checkout not reachable and no checkout link — agents may not complete the purchase path."
    return "FAIL", "No checkout or cart links found, and /checkout not reachable — agents cannot complete a purchase."


def static_sitemap_xml(page):
    """RDY-029: Does /sitemap.xml exist and list product URLs?"""
    content = page.get("sitemap_xml")
    if content is None:
        return "UNKNOWN", "Sitemap not probed (local file mode)."
    if not content:
        return "FAIL", "No sitemap.xml at site root — agents cannot discover product catalog."

    cl = content.lower()
    product_urls = len(re.findall(r"<loc>[^<]*/products/[^<]*</loc>", cl))
    has_urlset = "<urlset" in cl or "<sitemapindex" in cl

    if not has_urlset:
        return "FAIL", "sitemap.xml exists but is not valid XML (no <urlset> or <sitemapindex>)."
    if product_urls >= 1:
        return "PASS", f"sitemap.xml found with {product_urls} product URL(s) — agents can discover the catalog."
    # Sitemap index (links to sub-sitemaps) is also valid
    if "<sitemapindex" in cl:
        return "PASS", "sitemap.xml is a sitemap index — agents can follow sub-sitemaps to discover products."
    return "PASS", "sitemap.xml found (no direct product URLs, but site is discoverable)."


def static_page_load_time(page):
    """RDY-030: Does the page respond within a reasonable time for agents?"""
    ms = page.get("fetch_time_ms")
    if ms is None:
        return "UNKNOWN", "Page load time not measured (local file mode or 429 recovery)."

    if ms <= 2000:
        return "PASS", f"Page responded in {ms}ms — well within agent timeout thresholds."
    if ms <= 5000:
        return "PASS", f"Page responded in {ms}ms — acceptable but could be faster for agents."
    if ms <= 10000:
        return "FAIL", f"Page took {ms}ms to respond — agents with short timeouts may give up."
    return "FAIL", f"Page took {ms}ms to respond — most agents will timeout before loading this page."


def static_wallet_compatibility(page):
    """RDY-032: Does the site show x402 / Cloudflare agent-wallet readiness signals?

    x402 protocol: HTTP 402 + PAYMENT-REQUIRED/PAYMENT-SIGNATURE headers.
    MPP (Machine Payments Protocol) is backwards-compatible with x402.
    Cloudflare Monetization Gateway is the seller-side product.
    Cloudflare Wallets + cloudflare.pay are the buyer-side (agent) product.
    Status as of Aug 2026: waitlist / early access, not GA.
    """
    signals = []

    # .well-known/agent-verification endpoint (CF agent identity) — strongest signal
    agent_verify = page.get("agent_verification")
    if agent_verify:
        signals.append("agent-verification endpoint")

    # Strip <script> bodies before text matching — JS error constants like
    # var ERR="PAYMENT-REQUIRED" must not trigger a PASS
    raw_html = page.get("html", "") or ""
    visible_html = _strip_scripts(raw_html).lower()
    llms = (page.get("llms_txt_content") or "").lower()
    checkout_visible = _strip_scripts(page.get("checkout_html") or "").lower()
    combined = visible_html + " " + llms + " " + checkout_visible

    # x402 protocol references (HTTP 402 Payment Required for agents)
    if any(s in combined for s in ("x402", "402-receipt", "x402-hono")):
        signals.append("x402 protocol")

    # MPP (Machine Payments Protocol — backwards-compatible with x402)
    if "machine-payment" in combined or "mpp-payment" in combined:
        signals.append("MPP (Machine Payments Protocol)")

    # Cloudflare Monetization Gateway / agent commerce
    if any(s in combined for s in ("monetization-gateway", "cloudflare.pay",
                                    "cf-agent-auth", "cloudflare-agent")):
        signals.append("Cloudflare Monetization Gateway")

    if page.get("agent_probe_status") is None and not signals:
        return "UNKNOWN", "Site not probed (local file mode) — cannot check x402 signals."

    if signals:
        return "PASS", f"Agent wallet signals detected: {', '.join(signals)} — site supports x402/MPP agent payments."
    return "FAIL", "No x402, MPP, or agent-wallet signals found in page HTML, llms.txt, or checkout page."


def static_contradictory_availability(page):
    """Detect contradictory availability signals between JSON-LD and visible text."""
    jsonld_avail = _jsonld_availability(page)
    if jsonld_avail is None:
        return "UNKNOWN", "No JSON-LD availability found — cannot check for contradictions."

    text = (page.get("text", "") or "").lower()
    html = page.get("html", "") or ""
    # Strip script bodies so JS string literals don't count as visible text
    visible = _strip_scripts(html).lower()

    # Out-of-stock signals in visible text
    oos_phrases = ("out of stock", "sold out", "unavailable", "out stock")
    visible_oos = any(phrase in text for phrase in oos_phrases)

    # In-stock / purchasable signals in visible text
    in_stock_phrases = ("in stock", "add to cart", "add to bag", "buy now")
    visible_in_stock = any(phrase in text for phrase in in_stock_phrases)

    # Contradictory button state: both ATC and Sold Out text present in HTML
    has_atc_button = bool(re.search(
        r"add.to.cart|add.to.bag|buy.now", visible))
    has_soldout_button = bool(re.search(
        r"sold\s*out|out\s*of\s*stock", visible))
    contradictory_buttons = has_atc_button and has_soldout_button

    if jsonld_avail == "in_stock" and visible_oos:
        return "FAIL", (
            "JSON-LD says InStock but visible text contains out-of-stock language "
            f"(found: {next(p for p in oos_phrases if p in text)!r}). "
            "Agents may extract conflicting availability."
        )

    if jsonld_avail == "out_of_stock" and visible_in_stock:
        return "FAIL", (
            "JSON-LD says OutOfStock but visible text contains in-stock language "
            f"(found: {next(p for p in in_stock_phrases if p in text)!r}). "
            "Agents may extract conflicting availability."
        )

    if contradictory_buttons:
        return "FAIL", (
            "Page contains both Add-to-Cart and Sold Out text — "
            "agents may not determine the true availability."
        )

    return "PASS", (
        f"Availability signals are consistent (JSON-LD: {jsonld_avail.replace('_', ' ')}, "
        "no contradictory visible text)."
    )


def static_rate_limiting(page):
    """RDY-031: Does the site block or rate-limit agent-like traffic?

    T9: three-state — blocked / reachable-but-useless / accessible.
    T10: multi-UA — reports per-crawler access posture.
    """
    probe_status = page.get("agent_probe_status")
    if probe_status is None:
        return "UNKNOWN", "Agent probe not performed (local file mode)."

    detail = page.get("agent_probe_detail", {})
    challenge = detail.get("challenge", False)
    words = detail.get("readable_words", 0)
    ua_note = " (self-asserted UA, not verified vendor IP)"

    # T10: multi-UA summary
    blocked_uas = detail.get("blocked_uas", [])
    allowed_uas = detail.get("allowed_uas", [])
    ua_summary = ""
    if blocked_uas or allowed_uas:
        parts = []
        if blocked_uas:
            parts.append(f"blocked: {', '.join(blocked_uas)}")
        if allowed_uas:
            parts.append(f"allowed: {', '.join(allowed_uas)}")
        ua_summary = f" [{'; '.join(parts)}]"

    if probe_status == 200:
        if challenge:
            return "FAIL", f"Site responds 200 but serves a bot challenge page ({words} words){ua_note}.{ua_summary}"
        # T9: "200 but useless" — empty/near-empty body
        if words < 50:
            return "FAIL", (f"Site responds 200 but body has only {words} words — "
                            f"agents get an empty or stub page{ua_note}.{ua_summary}")
        # T10: partial blocking — some UAs allowed, some blocked
        if blocked_uas and allowed_uas:
            return "PASS", (f"Site allows some agent UAs but blocks others{ua_note}.{ua_summary}")
        return "PASS", f"Site responds 200 to agent UA strings — not blocking agent-like requests{ua_note}.{ua_summary}"
    if probe_status == 403:
        return "FAIL", f"Site returns 403 to GPTBot — likely blocking agent-like traffic{ua_note}.{ua_summary}"
    if probe_status == 429:
        return "FAIL", f"Site returns 429 to GPTBot — rate-limiting agent-like traffic{ua_note}.{ua_summary}"
    if 400 <= probe_status < 500:
        return "FAIL", f"Site returns {probe_status} to GPTBot — may be blocking agent-like traffic{ua_note}.{ua_summary}"
    if probe_status >= 500:
        return "UNKNOWN", f"Site returns {probe_status} to GPTBot — server error (may be transient).{ua_summary}"
    return "PASS", f"Site responds {probe_status} to agent UA strings{ua_note}.{ua_summary}"


# ---- PROTOCOL DISCOVERY probes -----------------------------------------------

def static_mcp_server_card(page):
    """RDY-034: MCP Server Card at /.well-known/mcp.json."""
    mcp = page.get("mcp_json")
    if mcp is None:
        return "UNKNOWN", "MCP endpoint not probed (local file mode)."
    if mcp:
        name = mcp.get("name", "unnamed")
        tools = len(mcp.get("tools", []))
        return "PASS", f"MCP server card found (name: {name}, {tools} tool(s)) — agents can discover available tools."
    return "FAIL", "No MCP server card at /.well-known/mcp.json — agents cannot discover tools via Model Context Protocol."


def static_oauth_discovery(page):
    """RDY-035: OAuth Authorization Server Discovery."""
    oauth = page.get("oauth_discovery")
    if oauth is None:
        return "UNKNOWN", "OAuth endpoint not probed (local file mode)."
    if oauth:
        issuer = oauth.get("issuer", "")
        detail = f" (issuer: {issuer})" if issuer else ""
        return "PASS", f"OAuth discovery endpoint found{detail} — agents can authenticate via standard OAuth flow."
    return "FAIL", "No OAuth discovery at /.well-known/oauth-authorization-server — agents cannot authenticate programmatically."


def static_markdown_negotiation(page):
    """RDY-036: Markdown content negotiation (Accept: text/markdown)."""
    md = page.get("markdown_negotiation")
    if md is None:
        return "UNKNOWN", "Markdown negotiation not probed (local file mode)."
    if md and md.get("supports_markdown"):
        return "PASS", "Site serves markdown when requested (Accept: text/markdown) — agents get clean, parseable content."
    return "FAIL", "Site does not support markdown content negotiation — agents must parse HTML instead of clean text."


def static_a2a_agent_card(page):
    """RDY-037: A2A Agent Card at /.well-known/agent.json (Google A2A protocol)."""
    a2a = page.get("a2a_agent_card")
    if a2a is None:
        return "UNKNOWN", "A2A endpoint not probed (local file mode)."
    if a2a:
        name = a2a.get("name", a2a.get("agent_name", ""))
        detail = f" (name: {name})" if name else ""
        return "PASS", f"A2A agent card found at /.well-known/agent.json{detail} — supports Google Agent-to-Agent protocol."
    return "FAIL", "No A2A agent card found at /.well-known/agent.json."


def static_auth_md(page):
    """RDY-038: Auth.md authentication documentation."""
    auth = page.get("auth_md")
    if auth is None:
        return "UNKNOWN", "Auth.md not probed (local file mode)."
    if auth:
        return "PASS", "auth.md found — agents have machine-readable authentication documentation."
    return "FAIL", "No auth.md at site root — agents have no authentication documentation."


def static_link_headers(page):
    """RDY-039: Link response headers for agent discovery."""
    lh = page.get("link_headers")
    if lh is None:
        return "UNKNOWN", "Link headers not probed (local file mode)."
    signals = []
    if lh.get("has_describedby"):
        signals.append("describedby")
    if lh.get("has_api_catalog"):
        signals.append("api-catalog")
    if lh.get("has_search"):
        signals.append("search")
    if signals:
        return "PASS", f"Link response headers found: rel={', '.join(signals)} — agents can discover related resources."
    return "FAIL", "No Link response headers for agent discovery (rel=describedby, api-catalog, search)."


def static_dns_aid(page):
    """RDY-040: DNS for AI Discovery (DNS-AID) TXT records."""
    dns = page.get("dns_aid")
    if dns is None:
        return "UNKNOWN", "DNS-AID not probed (local file mode)."
    if dns.get("has_dns_aid"):
        return "PASS", "DNS-AID TXT record found at _ai subdomain — agents can discover site capabilities via DNS."
    return "FAIL", "No DNS-AID TXT record found at _ai subdomain."


def static_agent_skills(page):
    """RDY-041: Agent Skills / WebMCP discovery in HTML or llms.txt."""
    html = (page.get("html", "") or "").lower()
    llms = (page.get("llms_txt_content") or "").lower()
    combined = html + " " + llms

    signals = []
    if any(s in combined for s in ("agent-skill", "agentskill", "agent_skill")):
        signals.append("Agent Skills")
    if any(s in combined for s in ("webmcp", "web-mcp", "web_mcp")):
        signals.append("WebMCP")
    # UCP/ACP: require word boundaries — bare 3-char substrings match
    # ordinary words (e.g. "MacPherson" -> "acp", "UCPVC" -> "ucp")
    if re.search(r'\bucp\b', combined) or "unified-commerce-protocol" in combined:
        signals.append("UCP")
    if re.search(r'\bacp\b', combined) or "agent-commerce-protocol" in combined:
        signals.append("ACP")

    # Also check for .well-known/skills or similar
    mcp = page.get("mcp_json")
    if mcp and mcp.get("tools"):
        signals.append(f"MCP tools ({len(mcp['tools'])})")

    if page.get("agent_probe_status") is None and not signals:
        return "UNKNOWN", "Site not probed (local file mode)."

    if signals:
        return "PASS", f"Agent commerce protocols detected: {', '.join(signals)} — agents can interact via structured protocols."
    return "FAIL", "No agent skills, WebMCP, UCP, or ACP signals detected — agents have no structured commerce protocols."


# ---- SECURITY & TRUST probes -------------------------------------------------

def static_ugc_injection(page):
    """RDY-042: Prompt injection in user-generated content (reviews, Q&A)."""
    html = page.get("html", "") or ""
    import html as _html_mod
    html_decoded = _html_mod.unescape(html)
    hl = html_decoded.lower()

    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above",
        r"disregard\s+(all\s+)?(previous|above|prior)",
        r"you\s+are\s+now\s+a",
        r"system\s*:\s*override",
        r"new\s+instructions?\s*:",
        r"forget\s+(everything|all|your)",
    ]
    pattern = "|".join(f"({p})" for p in INJECTION_PATTERNS)

    # Identify UGC sections: reviews, comments, Q&A
    ugc_markers = [
        (r'class=["\'][^"\']*(?:review|comment|ugc|user-content|qa-|question|answer)[^"\']*["\']',
         "review/comment section"),
        (r'(?:customer\s+reviews|product\s+reviews|ratings?\s+and\s+reviews)',
         "reviews heading"),
        (r'data-(?:review|comment|testimonial)',
         "review data attributes"),
    ]

    ugc_found = False
    for marker_re, _ in ugc_markers:
        if re.search(marker_re, hl):
            ugc_found = True
            break

    if not ugc_found:
        # No UGC sections detected — not applicable
        return "PASS", "No user-generated content sections detected (reviews, Q&A) — no UGC injection risk."

    # Extract text from UGC sections (rough: everything after review markers)
    ugc_text = ""
    for marker_re, label in ugc_markers:
        m = re.search(marker_re, hl)
        if m:
            # Take up to 10000 chars after the marker
            start = m.start()
            ugc_text += hl[start:start + 10000] + " "

    if re.search(pattern, ugc_text, re.I):
        return "FAIL", "Prompt injection detected in user-generated content (reviews/comments) — agents reading this page may be hijacked."
    return "PASS", "User-generated content sections found but no prompt injection patterns detected."


def static_cart_rate_protection(page):
    """RDY-043: Does the cart API have rate limiting protection?"""
    cart_test = page.get("cart_rate_test")
    if cart_test is None:
        return "UNKNOWN", "Cart rate test not performed (local file mode)."
    if not cart_test.get("endpoint_exists"):
        return "UNKNOWN", "No cart API endpoint found — rate test not applicable."
    if cart_test.get("rate_limited"):
        return "PASS", "Cart API returned 429 during rapid requests — rate limiting is active."

    statuses = cart_test.get("statuses", [])
    # 422/400 = endpoint rejected the payload (invalid product ID), not "accepted"
    rejected = [s for s in statuses if s in (422, 400)]
    if rejected:
        return "UNKNOWN", (
            f"Cart API returned {rejected[0]} for test requests (invalid payload rejected). "
            "5 requests is not a meaningful rate-limit test."
        )

    if cart_test.get("all_accepted"):
        return "UNKNOWN", (
            "Cart API responded 200 to 5 rapid requests. "
            "This is too few requests to determine whether rate limiting is in place."
        )
    return "UNKNOWN", "Cart API responded to rapid requests with mixed results — inconclusive."


def static_checkout_bot_challenge(page):
    """RDY-044: Does checkout have bot detection/challenge?"""
    probe = page.get("checkout_probe")
    checkout_html = page.get("checkout_html")
    if probe is None and checkout_html is None:
        return "UNKNOWN", "Checkout page not probed (local file mode)."

    # Handle redirect — need to know if this is Shopify (item 2)
    if probe and probe.get("redirect_reason"):
        final = probe.get("final_url", "/checkout")
        reason = probe["redirect_reason"]
        platform = (page.get("_platform_name") or "").lower()
        # Shopify checkout is on a separate domain with built-in bot protection
        if reason == "redirected_to_cart" and platform == "shopify":
            return "UNKNOWN", (
                f"/checkout redirected to {final}. "
                "Shopify checkout is served on a separate domain with "
                "built-in bot protection; not probeable without a cart."
            )
        if reason == "redirected_to_cart":
            return "UNKNOWN", f"/checkout redirected to {final} — cannot probe bot challenge without a cart session."
        if reason == "redirected_to_login":
            return "UNKNOWN", f"/checkout redirected to login ({final}) — bot challenge check not applicable."

    if not checkout_html:
        return "UNKNOWN", "Checkout page returned no content."

    cl = checkout_html.lower()
    probed_url = probe.get("final_url", "/checkout") if probe else "/checkout"

    # Bot challenge signals
    challenge_signals = (
        "captcha", "recaptcha", "hcaptcha", "turnstile",
        "cf-challenge", "challenge-platform", "bot-detection",
        "g-recaptcha", "data-sitekey", "cf-turnstile",
        "arkose", "funcaptcha",
    )
    has_challenge = any(sig in cl for sig in challenge_signals)

    if has_challenge:
        detected = [sig for sig in challenge_signals if sig in cl]
        return "PASS", f"Checkout at {probed_url} has bot challenge protection ({detected[0]})."
    return "FAIL", f"No bot challenge (CAPTCHA, Turnstile) detected at {probed_url}."


def static_admin_exposure(page):
    """RDY-045: Are admin/staff/API paths exposed without authentication?"""
    admin = page.get("admin_exposure")
    if admin is None:
        return "UNKNOWN", "Admin paths not probed (local file mode)."
    exposed = admin.get("exposed_paths", [])
    if exposed:
        paths = ", ".join(e["path"] for e in exposed)
        return "FAIL", (
            f"Paths returned 200 with distinct content (not soft-404): {paths}. "
            f"Soft-404 baseline: HTTP {admin.get('baseline_status')}."
        )
    checked = admin.get("checked", 0)
    return "PASS", f"No admin or API paths exposed ({checked} paths checked, soft-404 baseline used)."


STATIC = {
    "jsonld_product": static_jsonld_product,
    "price_in_html": static_price_in_html,
    "robots_allows_agents": static_robots_allows_agents,
    "policy_text_present": static_policy_text_present,
    "llms_txt_present": static_llms_txt_present,
    "llms_txt_quality": static_llms_txt_quality,
    "jsonld_quality": static_jsonld_quality,
    "js_render_ratio": static_js_render_ratio,
    "cart_semantic": static_cart_semantic,
    "variant_selectors": static_variant_selectors,
    "prompt_injection": static_prompt_injection,
    "guest_checkout": static_guest_checkout,
    "cart_api": static_cart_api,
    "search_accessible": static_search_accessible,
    "nav_accessible": static_nav_accessible,
    "related_products": static_related_products,
    "atc_flow_proxy": static_atc_flow_proxy,
    "checkout_proxy": static_checkout_proxy,
    "sitemap_xml": static_sitemap_xml,
    "page_load_time": static_page_load_time,
    "rate_limiting": static_rate_limiting,
    "wallet_compatibility": static_wallet_compatibility,
    "contradictory_availability": static_contradictory_availability,
    "mcp_server_card": static_mcp_server_card,
    "oauth_discovery": static_oauth_discovery,
    "markdown_negotiation": static_markdown_negotiation,
    "a2a_agent_card": static_a2a_agent_card,
    "auth_md": static_auth_md,
    "link_headers": static_link_headers,
    "dns_aid": static_dns_aid,
    "agent_skills": static_agent_skills,
    "ugc_injection": static_ugc_injection,
    "cart_rate_protection": static_cart_rate_protection,
    "checkout_bot_challenge": static_checkout_bot_challenge,
    "admin_exposure": static_admin_exposure,
}


BROWSER = {
    "add_to_cart_flow": "run_add_to_cart",
    "search_discovery": "run_search_discovery",
    "checkout_reachable": "run_checkout_reachable",
    "homepage_to_product": "run_homepage_to_product",
    "compare_products": "run_compare_products",
}


def run_browser(check, page):
    """Run a browser-agent check (e.g. Add-to-Cart flow).

    Uses majority-vote: runs the browser flow up to 3 times if the first
    attempt fails. PASS if at least 2/3 succeed (reduces non-deterministic
    flips from modals, timing, popups).
    """
    import os
    detect = check.get("detect")
    func_name = BROWSER.get(detect)
    if not func_name:
        return {"verdict": "UNKNOWN",
                "detail": f"No browser probe for detect={detect!r}.",
                "pass_fraction": None}
    url = page.get("url", "")
    if not url or not url.startswith("http"):
        return {"verdict": "UNKNOWN",
                "detail": "Browser checks require a live URL.",
                "pass_fraction": None}
    try:
        import browser_agent
        probe_fn = getattr(browser_agent, func_name)
    except (ImportError, AttributeError):
        return {"verdict": "UNKNOWN",
                "detail": "browser_agent module not available.",
                "pass_fraction": None}

    max_attempts = int(os.environ.get("BROWSER_ATTEMPTS", "3"))
    if max_attempts < 1:
        return {"verdict": "UNKNOWN", "detail": "BROWSER_ATTEMPTS set to 0.",
                "pass_fraction": None}
    successes = 0
    attempts = 0
    best_result = None
    majority_needed = (max_attempts + 1) // 2

    for attempt in range(max_attempts):
        result = probe_fn(url)
        attempts += 1
        if result.get("success"):
            successes += 1
            # Prefer a successful result for the detail output
            if best_result is None or not best_result.get("success"):
                best_result = result
            # Early exit: majority achieved
            if successes >= majority_needed:
                break
        else:
            if best_result is None:
                best_result = result
            # Early exit: majority failure certain
            failures = attempts - successes
            if failures > max_attempts - majority_needed:
                break

    if best_result is None:
        return {"verdict": "UNKNOWN", "detail": "Browser agent returned no results.",
                "pass_fraction": None}

    result = best_result
    pass_rate = successes / attempts

    steps_summary = "; ".join(
        f"step {s['step']}: {s['action']}({(s.get('selector') or '')[:40]}) -> {s.get('result','')}"
        for s in result.get("steps", [])
    )

    FLOW_LABELS = {
        "add_to_cart_flow": ("add product to cart", "Added to cart"),
        "search_discovery": ("find product via site search", "Found via search"),
        "checkout_reachable": ("reach the checkout page", "Reached checkout"),
        "homepage_to_product": ("navigate from homepage to product", "Navigated to product"),
        "compare_products": ("find and navigate to a related product", "Found related product"),
    }
    fail_label, pass_label = FLOW_LABELS.get(detect, ("complete the flow", "Flow completed"))

    if successes >= (max_attempts + 1) // 2:
        verified = result.get("cart_verified", False)
        detail = (f"{pass_label} in {result['total_steps']} steps "
                  f"({successes}/{attempts} attempts succeeded). "
                  f"Steps: {steps_summary}")
        if detect == "add_to_cart_flow":
            detail = (f"{pass_label} in {result['total_steps']} steps "
                      f"({successes}/{attempts} attempts succeeded). "
                      f"Cart verified: {'yes' if verified else 'not confirmed'}. "
                      f"Steps: {steps_summary}")
            if verified:
                return {"verdict": "PASS", "detail": detail, "pass_fraction": 1.0,
                        "browser_result": result, "browser_attempts": attempts,
                        "browser_successes": successes}
            return {"verdict": "UNKNOWN", "detail": detail, "pass_fraction": None,
                    "browser_result": result, "browser_attempts": attempts,
                    "browser_successes": successes, "cart_verified": False}
        return {"verdict": "PASS", "detail": detail, "pass_fraction": 1.0,
                "browser_result": result, "browser_attempts": attempts,
                "browser_successes": successes}

    detail = (f"Agent failed to {fail_label} after {result['total_steps']} steps "
              f"({successes}/{attempts} attempts). "
              f"Reason: {result.get('final_reason', 'unknown')}.")

    # Surface element-level diagnostics if available
    diag = result.get("diagnostics")
    if diag:
        diag_parts = []
        if diag.get("atc_state") == "disabled":
            diag_parts.append("ATC button is disabled (likely requires variant selection)")
        elif diag.get("atc_state") == "missing":
            diag_parts.append("No Add-to-Cart button found on page")
        for g in diag.get("gating", []):
            diag_parts.append(g)
        vs = diag.get("variant_selectors", [])
        custom_swatches = [v for v in vs if v.get("type") == "custom_swatch"]
        if custom_swatches:
            diag_parts.append(f"{len(custom_swatches)} custom JS swatch(es) "
                              f"instead of standard <select> elements")
        fragile = [v for v in vs if not v.get("has_stable_locator")]
        if fragile:
            diag_parts.append(f"{len(fragile)} variant selector(s) lack stable locators "
                              f"(no id/name/data-testid)")
        loc = diag.get("locator_summary", {})
        if loc.get("fragile", 0) > 0:
            total = loc.get("stable", 0) + loc.get("fragile", 0)
            pct = round(100 * loc["fragile"] / total) if total else 0
            diag_parts.append(f"{pct}% of interactive elements use fragile locators")
        if diag_parts:
            detail += " | DIAGNOSTICS: " + "; ".join(diag_parts)

    ret = {"verdict": "FAIL", "detail": detail, "pass_fraction": pass_rate,
           "browser_result": result, "browser_attempts": attempts,
           "browser_successes": successes}
    if diag:
        ret["diagnostics"] = diag
    return ret


# Checks that use self-asserted UA, redirect proxies, or heuristic detection
# rather than direct observation of page content
_ESTIMATED_CHECKS = {
    "rate_limiting",         # self-asserted UA probe
    "checkout_proxy",        # redirect proxy for browser check
    "guest_checkout",        # probes /checkout (may redirect)
    "checkout_bot_challenge",# probes /checkout (may redirect)
    "cart_rate_protection",  # POST probe with 5 requests
    "admin_exposure",        # probes admin paths with soft-404 baseline
    "search_accessible",     # homepage HTML heuristic
    "nav_accessible",        # homepage HTML heuristic
    "related_products",      # regex heuristic for related sections
    "atc_flow_proxy",        # heuristic proxy for browser check
    "dns_aid",               # DNS TXT lookup
}


def check_confidence(detect: str) -> str:
    """Return 'estimated' or 'observed' based on check method."""
    return "estimated" if detect in _ESTIMATED_CHECKS else "observed"


def run_static(check, page):
    fn = STATIC.get(check.get("detect"))
    if not fn:
        return {"verdict": "UNKNOWN", "detail": f"no probe '{check.get('detect')}'",
                "pass_fraction": None, "confidence": "estimated"}
    verdict, detail = fn(page)
    confidence = check_confidence(check.get("detect", ""))
    return {"verdict": verdict, "detail": detail,
            "pass_fraction": {"PASS": 1.0, "FAIL": 0.0}.get(verdict),
            "confidence": confidence}


# ---- SHOPPER grading --------------------------------------------------------
def _norm(s):
    t = re.sub(r"[*_`#>]+", "", str(s))   # strip markdown formatting
    return re.sub(r"\s+", " ", t).strip().lower()


def _norm_num(s):
    m = re.search(r"\d[\d,]*\.?\d*", str(s))
    return float(m.group(0).replace(",", "")) if m else None


def _visible_prices(page) -> set[float]:
    """Extract all currency-formatted prices from visible page text."""
    text = (page.get("text", "") or "") + " " + (page.get("rendered_text", "") or "")
    matches = re.findall(r"[$£€]\s?(\d[\d,]*\.?\d*)", text)
    prices = set()
    for m in matches:
        try:
            v = float(m.replace(",", ""))
            if 0.01 < v < 100_000:
                prices.add(v)
        except ValueError:
            continue
    return prices


def _ground_truth(kind, page):
    """Extract ground truth, falling back to rendered DOM when available."""
    if kind == "price":
        gt = _jsonld_price(page)
        if gt is None and page.get("rendered_jsonld"):
            gt = _jsonld_price({"jsonld": page["rendered_jsonld"], "meta": page.get("rendered_meta", {})})
        return gt
    if kind == "availability":
        gt = _jsonld_availability(page)
        if gt is None and page.get("rendered_jsonld"):
            gt = _jsonld_availability({"jsonld": page["rendered_jsonld"]})
        return gt
    if kind == "product_name":
        # Prefer JSON-LD name (clean product name) over HTML title
        # (which often includes "Brand | Product | Category")
        obj, _ = _jsonld_offers(page)
        if obj and obj.get("name"):
            return obj["name"]
        # Fall back to rendered JSON-LD
        if page.get("rendered_jsonld"):
            obj2, _ = _jsonld_offers({"jsonld": page["rendered_jsonld"]})
            if obj2 and obj2.get("name"):
                return obj2["name"]
        # Last resort: HTML title
        title = page.get("title") or None
        if (not title or "not found" in title.lower()) and page.get("rendered_title"):
            title = page["rendered_title"]
        return title
    return None


def _is_error(answer: str) -> bool:
    """Check if an answer is an API error, not a real extraction."""
    return str(answer).startswith("__error__")


def grade_shopper(check, page, answers):
    """answers: list[str] of N agent responses -> grading dict."""
    n = len(answers)

    # Filter out API errors — they aren't real extraction results
    valid = [a for a in answers if not _is_error(a)]
    error_count = n - len(valid)
    if error_count > 0 and not valid:
        return {"verdict": "UNKNOWN", "pass_fraction": None, "n": n,
                "detail": f"All {n} shopper runs returned API errors — cannot grade."}
    if error_count > 0 and valid:
        n = len(valid)
        answers = valid

    mode = check.get("grade", "consistency")

    if mode == "correctness":
        gt = _ground_truth(check.get("ground_truth"), page)
        if gt is None:
            return {"verdict": "UNKNOWN", "pass_fraction": None, "n": n,
                    "detail": f"no ground truth for '{check.get('ground_truth')}' "
                              f"(page doesn't expose it cleanly — itself a weakness)."}

        # For price checks: accept alternate product prices (sale/member price)
        # but NOT arbitrary page prices like shipping ($5.99) or tax.
        # Only accept alternates within 20-150% of the GT price.
        alt_prices = set()
        if check.get("ground_truth") == "price" and isinstance(gt, float):
            for vp in _visible_prices(page):
                if vp == gt:
                    continue
                # Reject prices that are clearly not the product price
                # (shipping, small fees, unrelated numbers)
                if gt > 0 and 0.20 <= vp / gt <= 1.50:
                    alt_prices.add(vp)

        hits = 0
        alt_hits = 0
        for a in answers:
            if isinstance(gt, float):
                num = _norm_num(a)
                if num is not None and abs(num - gt) < 0.01:
                    hits += 1
                elif num is not None and any(abs(num - ap) < 0.01 for ap in alt_prices):
                    hits += 1
                    alt_hits += 1
            else:
                na, ng = _norm(a), _norm(gt)
                if na in ("", "unknown"):
                    pass  # not a hit
                elif na == ng:
                    hits += 1
                elif na in ng or ng in na:
                    # Substring match only counts if the shorter covers ≥50%
                    # of the longer — prevents "bikini" matching "Lola Luna Bikini Top Black"
                    shorter, longer = sorted([len(na), len(ng)])
                    if shorter / longer >= 0.5:
                        hits += 1
        frac = hits / n if n else None
        detail = f"{hits}/{n} runs matched ground truth ({gt})."
        if alt_hits:
            detail = f"{hits}/{n} runs returned a valid price ({hits - alt_hits} matched JSON-LD ${gt}, {alt_hits} matched a visible page price)."
        if error_count:
            detail += f" ({error_count} runs excluded due to API errors.)"
        return {"verdict": _rate_verdict(frac, check), "pass_fraction": frac,
                "n": n, "pass_rate": f"{hits}/{n}", "ground_truth": gt,
                "detail": detail}

    # consistency
    if not answers:
        return {"verdict": "UNKNOWN", "pass_fraction": None, "n": 0,
                "detail": "no shopper answers to grade (n=0 or all runs failed)."}
    counts = Counter(_norm(a) for a in answers)
    modal, modal_n = counts.most_common(1)[0]
    # A modal answer of "unknown"/empty means the agent extracted nothing —
    # that's not consistency, it's illegibility.
    if modal in ("", "unknown", "n/a", "none"):
        return {"verdict": "FAIL", "pass_fraction": 0.0, "n": n,
                "modal_answer": modal,
                "detail": f"Agent consistently returned '{modal}' — page is illegible to agents, not consistent."}
    frac = modal_n / n if n else None
    detail = (f"agent agreed with itself {modal_n}/{n} (modal: '{modal}'); "
              f"{len(counts)} distinct answers.")
    if error_count:
        detail += f" ({error_count} runs excluded due to API errors.)"
    return {"verdict": _rate_verdict(frac, check), "pass_fraction": frac, "n": n,
            "pass_rate": f"{modal_n}/{n}", "modal_answer": modal,
            "detail": detail}


# severity-keyed thresholds, same philosophy as audit methodology.md
THRESH = {"critical": 1.0, "high": 0.95, "medium": 0.90, "low": 0.80}


def _rate_verdict(frac, check):
    if frac is None:
        return "UNKNOWN"
    need = THRESH.get(check.get("severity_if_fail", "medium"), 0.90)
    return "PASS" if frac >= need else "FAIL"
