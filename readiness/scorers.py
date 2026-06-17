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
    # strip script bodies so a JS-embedded price doesn't count as server-rendered
    visible = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    if re.search(r"[$£€]\s?\d[\d,]*\.?\d*", visible):
        return "PASS", "Currency-formatted price present in server HTML."
    if _jsonld_price(page) is not None:
        return "FAIL", "Price only in structured data, not in visible server HTML."
    return "FAIL", "No price string in server HTML (likely JS-rendered only)."


def static_robots_allows_agents(page):
    robots = page.get("robots")
    if robots is None:
        return "UNKNOWN", "robots.txt not fetched (local file or unreachable)."
    blocked = []
    blocks = re.split(r"(?im)^\s*user-agent:", robots)
    for blk in blocks:
        head = blk.strip().lower()
        ua = head.split("\n", 1)[0].strip()
        if any(a in ua for a in AGENT_UAS) and re.search(r"(?im)^\s*disallow:\s*/\s*$", blk):
            blocked.append(ua)
    if blocked:
        return "FAIL", f"robots.txt blocks agent user-agents: {', '.join(blocked)}."
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

    # Script content size
    scripts = _re.findall(r"<script[^>]*>.*?</script>", html, _re.I | _re.S)
    script_len = sum(len(s) for s in scripts)

    # Visible text vs total page
    text_len = len(text)
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

    # Heavy JS with very little text = bad for agents
    if script_ratio > 60 and text_ratio < 10:
        return "FAIL", f"Page is heavily JS-rendered — agents see very little content. {detail}"
    if script_ratio > 50 and text_ratio < 15:
        return "FAIL", f"High JS dependency — limited content without a browser. {detail}"
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

    # 1. Check HTML comments for injection
    comments = _re.findall(r"<!--(.*?)-->", html, _re.S | _re.I)
    for c in comments:
        if _re.search(pattern, c, _re.I):
            findings.append("HTML comment contains agent-hijacking text")
            break

    # 2. Check hidden elements (display:none, visibility:hidden, opacity:0, aria-hidden)
    hidden_blocks = _re.findall(
        r'<[^>]*(display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0'
        r'|font-size\s*:\s*0|height\s*:\s*0|width\s*:\s*0'
        r'|aria-hidden\s*=\s*["\']true["\'])[^>]*>(.*?)</[^>]+>',
        html, _re.I | _re.S)
    for _, content in hidden_blocks:
        if _re.search(pattern, content, _re.I):
            findings.append("Hidden element contains agent-hijacking text")
            break

    # 3. Check for invisible text via color tricks (white-on-white, 0px font)
    # Look for style with color:#fff or color:white on non-body elements
    stealth_blocks = _re.findall(
        r'<[^>]*(color\s*:\s*(?:white|#fff(?:fff)?|rgba?\(\s*255))[^>]*>(.*?)</[^>]+>',
        html, _re.I | _re.S)
    for _, content in stealth_blocks:
        if _re.search(pattern, content, _re.I):
            findings.append("Invisible text (color trick) contains agent-hijacking text")
            break

    # 4. Check all page text for injection patterns in obvious places
    text = (page.get("text", "") or "").lower()
    # Only flag visible text if it's clearly injected (not natural language)
    for p in INJECTION_PATTERNS[:6]:  # check the most dangerous patterns only
        if _re.search(p, text, _re.I):
            findings.append("Visible page text contains suspicious agent-override phrasing")
            break

    if not findings:
        return "PASS", "No prompt injection patterns detected in page content."
    return "FAIL", f"Potential prompt injection found: {'; '.join(findings)}."


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
}


def run_static(check, page):
    fn = STATIC.get(check.get("detect"))
    if not fn:
        return {"verdict": "UNKNOWN", "detail": f"no probe '{check.get('detect')}'",
                "pass_fraction": None}
    verdict, detail = fn(page)
    return {"verdict": verdict, "detail": detail,
            "pass_fraction": {"PASS": 1.0, "FAIL": 0.0}.get(verdict)}


# ---- SHOPPER grading --------------------------------------------------------
def _norm(s):
    t = re.sub(r"[*_`#>]+", "", str(s))   # strip markdown formatting
    return re.sub(r"\s+", " ", t).strip().lower()


def _norm_num(s):
    m = re.search(r"\d[\d,]*\.?\d*", str(s))
    return float(m.group(0).replace(",", "")) if m else None


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
        title = page.get("title") or None
        # If raw title looks broken, try rendered title
        if (not title or "not found" in title.lower()) and page.get("rendered_title"):
            title = page["rendered_title"]
        return title
    return None


def grade_shopper(check, page, answers):
    """answers: list[str] of N agent responses -> grading dict."""
    n = len(answers)
    mode = check.get("grade", "consistency")

    if mode == "correctness":
        gt = _ground_truth(check.get("ground_truth"), page)
        if gt is None:
            return {"verdict": "UNKNOWN", "pass_fraction": None, "n": n,
                    "detail": f"no ground truth for '{check.get('ground_truth')}' "
                              f"(page doesn't expose it cleanly — itself a weakness)."}
        hits = 0
        for a in answers:
            if isinstance(gt, float):
                hits += (_norm_num(a) == gt)
            else:
                hits += (_norm(gt) in _norm(a) or _norm(a) in _norm(gt)) and _norm(a) not in ("", "unknown")
        frac = hits / n if n else None
        return {"verdict": _rate_verdict(frac, check), "pass_fraction": frac,
                "n": n, "pass_rate": f"{hits}/{n}", "ground_truth": gt,
                "detail": f"{hits}/{n} runs matched ground truth ({gt})."}

    # consistency
    counts = Counter(_norm(a) for a in answers)
    modal, modal_n = counts.most_common(1)[0]
    frac = modal_n / n if n else None
    return {"verdict": _rate_verdict(frac, check), "pass_fraction": frac, "n": n,
            "pass_rate": f"{modal_n}/{n}", "modal_answer": modal,
            "detail": f"agent agreed with itself {modal_n}/{n} (modal: '{modal}'); "
                      f"{len(counts)} distinct answers."}


# severity-keyed thresholds, same philosophy as audit methodology.md
THRESH = {"critical": 1.0, "high": 0.95, "medium": 0.90, "low": 0.80}


def _rate_verdict(frac, check):
    if frac is None:
        return "UNKNOWN"
    need = THRESH.get(check.get("severity_if_fail", "medium"), 0.90)
    return "PASS" if frac >= need else "FAIL"
