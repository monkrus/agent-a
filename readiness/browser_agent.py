#!/usr/bin/env python3
"""
browser_agent.py — LLM-driven browser interaction agent.

Phase 1: Add-to-Cart flow. Opens a product page in Playwright, uses Claude
to decide actions (click, select, scroll), and attempts to add the product
to cart. Returns a structured result with steps taken and success/failure.

Design:
  1. Open URL in headless Playwright.
  2. Extract interactive elements (buttons, selects, inputs, links).
  3. Take a screenshot.
  4. Send element inventory + screenshot to Claude: "what action next?"
  5. Claude returns a JSON action.
  6. Execute the action, repeat until done or max steps.
"""
from __future__ import annotations
import base64
import json
import os
import pathlib
import re

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

MAX_STEPS = 12
_JSON_RETRY_PROMPT = "Your previous response was not valid JSON. Reply with ONLY a JSON object, no explanation."


def _parse_action_json(raw: str) -> dict | None:
    """Try to extract a JSON action object from model output. Returns None on failure."""
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\{[^{}]*\}", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_elements(page) -> list[dict]:
    """Extract interactive elements from the page with selectors and text."""
    return page.evaluate("""() => {
        const els = [];
        const seen = new Set();

        function uid(tag, i) { return tag + '_' + i; }
        function txt(el) {
            return (el.innerText || el.textContent || '').trim().substring(0, 120);
        }
        function selector(el) {
            if (el.id) return '#' + CSS.escape(el.id);
            if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
            if (el.getAttribute('data-testid'))
                return '[data-testid="' + el.getAttribute('data-testid') + '"]';
            if (el.getAttribute('aria-label'))
                return '[aria-label="' + el.getAttribute('aria-label') + '"]';
            // fallback: nth-of-type
            const parent = el.parentElement;
            if (!parent) return el.tagName.toLowerCase();
            const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
            const idx = siblings.indexOf(el) + 1;
            return el.tagName.toLowerCase() + ':nth-of-type(' + idx + ')';
        }

        // Buttons
        document.querySelectorAll('button, input[type="submit"], [role="button"]').forEach((el, i) => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            const t = txt(el) || el.value || el.getAttribute('aria-label') || '';
            if (!t) return;
            const s = selector(el);
            if (seen.has(s)) return;
            seen.add(s);
            els.push({type: 'button', selector: s, text: t, visible: r.width > 0});
        });

        // Select dropdowns
        document.querySelectorAll('select').forEach((el, i) => {
            const s = selector(el);
            if (seen.has(s)) return;
            seen.add(s);
            const options = Array.from(el.options).map(o => ({
                value: o.value, text: o.text.trim(), selected: o.selected
            }));
            const label = el.getAttribute('aria-label')
                || (el.labels && el.labels[0] ? el.labels[0].textContent.trim() : '')
                || el.name || '';
            els.push({type: 'select', selector: s, label: label, options: options});
        });

        // Radio groups
        const radioGroups = {};
        document.querySelectorAll('input[type="radio"]').forEach(el => {
            const name = el.name || 'radio';
            if (!radioGroups[name]) radioGroups[name] = [];
            const label = el.labels && el.labels[0] ? el.labels[0].textContent.trim() : el.value;
            radioGroups[name].push({
                selector: selector(el), value: el.value, label: label, checked: el.checked
            });
        });
        for (const [name, radios] of Object.entries(radioGroups)) {
            els.push({type: 'radio_group', name: name, options: radios});
        }

        // Links with cart/checkout relevance
        document.querySelectorAll('a[href]').forEach(el => {
            const href = el.getAttribute('href') || '';
            const t = txt(el);
            if (/cart|checkout|bag|basket/i.test(href) || /cart|checkout|bag|view.cart/i.test(t)) {
                const s = selector(el);
                if (seen.has(s)) return;
                seen.add(s);
                els.push({type: 'link', selector: s, text: t, href: href});
            }
        });

        return els;
    }""")


def _screenshot_b64(page) -> str:
    """Take a screenshot and return as base64."""
    buf = page.screenshot(full_page=False, type="jpeg", quality=60)
    return base64.b64encode(buf).decode()


def _ask_agent(elements: list[dict], screenshot_b64: str, goal: str,
               history: list[dict], step: int) -> dict:
    """Ask Claude what action to take next."""
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Browser agent requires an API key.")
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("BROWSER_AGENT_MODEL", "claude-haiku-4-5-20251001")

    history_str = ""
    if history:
        history_str = "\n\nACTIONS TAKEN SO FAR:\n"
        for h in history:
            history_str += f"  Step {h['step']}: {h['action']} -> {h.get('result', 'ok')}\n"

    elements_str = json.dumps(elements, indent=2)[:4000]

    sys_prompt = (
        "You are an AI shopping agent interacting with a product page in a browser. "
        "Your goal is to add the main product to the cart. You can see a screenshot "
        "of the current page and a list of interactive elements.\n\n"
        "Reply with ONLY a JSON object (no markdown, no explanation) with these fields:\n"
        '  {"action": "click|select|scroll|done|fail",\n'
        '   "selector": "CSS selector from the element list",\n'
        '   "value": "for select: the option value to choose",\n'
        '   "reason": "brief explanation of why this action"}\n\n'
        "Actions:\n"
        "  click    - click a button or link (provide selector)\n"
        "  select   - choose an option from a dropdown (provide selector + value)\n"
        "  scroll   - scroll down to see more content (no selector needed)\n"
        "  done     - the product has been added to cart successfully\n"
        "  fail     - you cannot complete the goal (explain in reason)\n\n"
        "Rules:\n"
        "- If a variant (size/color) must be selected before adding to cart, select one first.\n"
        "- Prefer the default/first available variant if no specific one is needed.\n"
        "- After clicking Add to Cart, check if the cart updated (look for cart count, "
        "confirmation message, or cart drawer).\n"
        "- If you see a cart confirmation or the cart count changed, respond with 'done'.\n"
        "- Do not click 'Buy Now' or 'Checkout' — only 'Add to Cart'.\n"
        "- If the page has a popup/modal blocking the product, try to close it first.\n"
        "- Keep the 'reason' field under 80 characters."
    )

    user_content = [
        {"type": "text", "text": (
            f"GOAL: {goal}\n"
            f"STEP: {step}/{MAX_STEPS}\n"
            f"{history_str}\n\n"
            f"INTERACTIVE ELEMENTS ON PAGE:\n{elements_str}"
        )},
        {"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": screenshot_b64,
        }},
    ]

    messages = [{"role": "user", "content": user_content}]
    for _attempt in range(2):
        msg = client.messages.create(
            model=model, max_tokens=200, system=sys_prompt,
            messages=messages,
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        parsed = _parse_action_json(raw)
        if parsed is not None:
            return parsed
        # Retry: feed the bad response back and ask for JSON only
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": _JSON_RETRY_PROMPT})
    return {"action": "fail", "reason": f"Could not parse agent response: {raw[:200]}"}


def _execute_action(page, action: dict) -> str:
    """Execute an action on the page. Returns a result string."""
    act = action.get("action", "fail")
    selector = action.get("selector", "")
    value = action.get("value", "")

    if act == "click":
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=3000)
            try:
                el.click(timeout=3000)
            except Exception:
                # Fallback: force-click bypasses overlay/actionability checks
                el.click(force=True, timeout=3000)
            page.wait_for_timeout(1500)
            return "clicked"
        except Exception as e:
            return f"click failed: {e}"

    elif act == "select":
        try:
            page.select_option(selector, value=value, timeout=3000)
            page.wait_for_timeout(1000)
            return f"selected {value}"
        except Exception as e:
            return f"select failed: {e}"

    elif act == "scroll":
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(1000)
        return "scrolled"

    elif act in ("done", "fail"):
        return act

    return f"unknown action: {act}"


def run_add_to_cart(url: str, timeout: int = 30) -> dict:
    """
    Attempt to add the main product to cart on the given URL.

    Returns:
        {
            "success": bool,
            "steps": [{"step": int, "action": str, "selector": str, "reason": str, "result": str}],
            "total_steps": int,
            "final_reason": str,
            "cart_verified": bool,
        }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "steps": [],
                "total_steps": 0, "final_reason": "Playwright not installed",
                "cart_verified": False}

    steps = []
    goal = "Add the main product on this page to the shopping cart."

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36",
            )
            page = ctx.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Close common popups (cookie banners, email captures)
            _dismiss_popups(page)

            consecutive_fails = 0
            last_selector = None
            repeat_count = 0
            for step_num in range(1, MAX_STEPS + 1):
                # After several failed clicks, force-clear all modals
                if consecutive_fails >= 3:
                    _force_clear_modals(page)
                    consecutive_fails = 0

                elements = _extract_elements(page)
                screenshot = _screenshot_b64(page)
                action = _ask_agent(elements, screenshot, goal, steps, step_num)

                act = action.get("action", "fail")
                selector = action.get("selector", "")

                # Detect stuck loop: same selector clicked 2+ times in a row
                if act == "click" and selector and selector == last_selector:
                    repeat_count += 1
                    if repeat_count >= 2:
                        steps.append({
                            "step": step_num,
                            "action": "fail",
                            "selector": selector,
                            "value": "",
                            "reason": f"Stuck: clicked '{selector}' {repeat_count + 1} times with no progress",
                            "result": "fail",
                        })
                        break
                else:
                    repeat_count = 0
                last_selector = selector if act == "click" else last_selector

                step_record = {
                    "step": step_num,
                    "action": act,
                    "selector": selector,
                    "value": action.get("value", ""),
                    "reason": action.get("reason", ""),
                }

                if act in ("done", "fail"):
                    step_record["result"] = act
                    steps.append(step_record)
                    break

                result = _execute_action(page, action)
                step_record["result"] = result
                steps.append(step_record)

                # Auto-detect cart success after click actions
                if act == "click" and "failed" not in result:
                    consecutive_fails = 0
                    if _verify_cart(page):
                        steps.append({
                            "step": step_num + 1,
                            "action": "done",
                            "selector": "",
                            "value": "",
                            "reason": "Cart verified automatically after click",
                            "result": "done",
                        })
                        break

                if "failed" in result:
                    consecutive_fails += 1
                    _dismiss_popups(page)
                    continue
                else:
                    consecutive_fails = 0

            # Verify cart state
            cart_verified = _verify_cart(page)

            success = any(s["action"] == "done" for s in steps)
            final_reason = steps[-1].get("reason", "") if steps else "no steps taken"

            browser.close()

            return {
                "success": success,
                "steps": steps,
                "total_steps": len(steps),
                "final_reason": final_reason,
                "cart_verified": cart_verified,
            }

    except Exception as e:
        return {
            "success": False,
            "steps": steps,
            "total_steps": len(steps),
            "final_reason": f"Browser error: {e}",
            "cart_verified": False,
        }


def _dismiss_popups(page):
    """Try to close common popup/modal overlays."""
    # First, try to remove known overlay elements via JS (fastest)
    page.evaluate("""() => {
        // Remove common marketing overlays by ID/class
        const overlaySelectors = [
            '#attentive_overlay', '.attentive-overlay',
            '#klaviyo-popup', '.klaviyo-popup',
            '.alia-overlay', '[id^="alia-root"]',
            '.privy-popup', '#privy-popup',
            '.omnisend-form-container',
        ];
        for (const sel of overlaySelectors) {
            document.querySelectorAll(sel).forEach(el => el.remove());
        }
        // Also remove any full-screen overlays blocking pointer events
        document.querySelectorAll('[role="dialog"][aria-modal="true"]').forEach(el => {
            el.remove();
        });
    }""")
    page.wait_for_timeout(500)

    # Then try clicking close buttons
    popup_selectors = [
        '[aria-label="Close"]',
        '[aria-label="close"]',
        'button.close',
        '.modal-close',
        '.popup-close',
        '[data-action="close"]',
        'button:has-text("No thanks")',
        'button:has-text("Close")',
        'button:has-text("✕")',
        'button:has-text("×")',
    ]
    for sel in popup_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                loc.click(timeout=1000)
                page.wait_for_timeout(500)
        except Exception:
            continue


def _check_cart_api(page) -> bool:
    """Check Shopify /cart.json API for items in cart."""
    try:
        response = page.request.get("/cart.json")
        if response.ok:
            cart = response.json()
            return cart.get("item_count", 0) > 0
    except Exception:
        pass
    return False


def _force_clear_modals(page):
    """Nuclear option: remove all overlays, modals, and fixed-position blockers."""
    page.evaluate("""() => {
        // Remove all dialog/modal elements
        document.querySelectorAll(
            '[role="dialog"], [aria-modal="true"], .modal, .popup, '
            + '.overlay, [class*="modal"], [class*="popup"], [class*="overlay"], '
            + '[id*="modal"], [id*="popup"], [id*="overlay"]'
        ).forEach(el => el.remove());
        // Remove fixed/absolute positioned overlays that cover the viewport
        const toRemove = [];
        for (const el of document.querySelectorAll('*')) {
            if (!el.isConnected) continue;
            try {
                const style = getComputedStyle(el);
                if ((style.position === 'fixed' || style.position === 'absolute') &&
                    parseInt(style.zIndex) > 100 &&
                    el.offsetWidth > window.innerWidth * 0.5 &&
                    el.offsetHeight > window.innerHeight * 0.3 &&
                    el.tagName !== 'HEADER' && el.tagName !== 'NAV') {
                    toRemove.push(el);
                }
            } catch(e) {}
        }
        toRemove.forEach(el => el.remove());
        // Clear body-level pointer-event blockers (e.g., Mulberry warranty overlays)
        document.body.style.pointerEvents = 'auto';
        document.body.style.overflow = 'auto';
        document.documentElement.style.pointerEvents = 'auto';
        document.documentElement.style.overflow = 'auto';
    }""")
    page.wait_for_timeout(500)


def _verify_cart(page) -> bool:
    """Check if the cart has items after the add-to-cart flow."""
    try:
        # Check common cart indicators
        indicators = [
            # Cart count badge showing > 0
            page.evaluate("""() => {
                const els = document.querySelectorAll(
                    '[data-cart-count], .cart-count, .cart-count-bubble, '
                    + '#cart-count, .header-cart-count, .cart-item-count');
                for (const el of els) {
                    const n = parseInt(el.textContent);
                    if (n > 0) return true;
                }
                return false;
            }"""),
            # Cart drawer/modal is open with items
            page.evaluate("""() => {
                const cartEls = document.querySelectorAll(
                    '.cart-drawer, .mini-cart, .cart-modal, [data-cart-items]');
                for (const el of cartEls) {
                    if (el.offsetHeight > 0 && el.textContent.length > 20) return true;
                }
                return false;
            }"""),
            # "Added to cart" confirmation in notification/transient elements
            page.evaluate("""() => {
                const sels = '[aria-live], [role="alert"], [role="status"], '
                    + '.cart-notification, .cart-popup, .notification, '
                    + '[class*="notification"], [class*="cart-confirm"], '
                    + '[class*="added-to-cart"], [data-cart-notification]';
                for (const el of document.querySelectorAll(sels)) {
                    const t = el.innerText.toLowerCase();
                    if (t.includes('added to cart') || t.includes('added to bag')
                        || t.includes('item added') || t.includes('added to your cart')) {
                        return true;
                    }
                }
                return false;
            }"""),
            # Shopify cart API check (works on any Shopify store)
            _check_cart_api(page),
        ]
        return any(indicators)
    except Exception:
        return False


# ==========================================================================
# Phase 2: Journey flows — search, checkout, navigation, comparison
# ==========================================================================

FLOW_MAX_STEPS = 15

FLOW_ACTIONS = (
    "Actions:\n"
    "  click  - click a button or link (selector required)\n"
    "  type   - fill text into an input field (selector + value required)\n"
    "  press  - press a keyboard key like Enter (value = key name)\n"
    "  select - choose a dropdown option (selector + value required)\n"
    "  scroll - scroll down to see more content\n"
    "  done   - goal achieved\n"
    "  fail   - cannot complete (explain in reason)\n\n"
    'Reply with ONLY a JSON object:\n'
    '{"action": "...", "selector": "...", "value": "...", "reason": "brief"}\n'
)


def _product_name_from_url(url: str) -> str:
    """Extract a human-readable product name from a URL slug."""
    from urllib.parse import urlparse
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    name = slug.replace("-", " ").replace("_", " ")
    for sfx in (".html", ".htm"):
        if name.endswith(sfx):
            name = name[:-len(sfx)]
    return name.strip()


def _homepage_url(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _extract_all_elements(page) -> list[dict]:
    """Extract all interactive elements including nav, search, forms."""
    return page.evaluate("""() => {
        const els = [];
        const seen = new Set();
        function txt(el) {
            return (el.innerText || el.textContent || '').trim().substring(0, 120);
        }
        function selector(el) {
            if (el.id) return '#' + CSS.escape(el.id);
            if (el.name && el.tagName !== 'A')
                return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
            if (el.getAttribute('data-testid'))
                return '[data-testid="' + el.getAttribute('data-testid') + '"]';
            if (el.getAttribute('aria-label'))
                return '[aria-label="' + el.getAttribute('aria-label') + '"]';
            const parent = el.parentElement;
            if (!parent) return el.tagName.toLowerCase();
            const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
            const idx = siblings.indexOf(el) + 1;
            return el.tagName.toLowerCase() + ':nth-of-type(' + idx + ')';
        }
        function add(obj) { if (!seen.has(obj.selector)) { seen.add(obj.selector); els.push(obj); } }

        // Buttons
        document.querySelectorAll('button, input[type="submit"], [role="button"]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            const t = txt(el) || el.value || el.getAttribute('aria-label') || '';
            if (t) add({type: 'button', selector: selector(el), text: t});
        });
        // Text/search inputs
        document.querySelectorAll(
            'input[type="text"], input[type="search"], input[type="email"], '
            + 'input[type="tel"], input:not([type]), textarea'
        ).forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            add({type: 'input', selector: selector(el),
                 label: el.getAttribute('aria-label') || el.placeholder || el.name || ''});
        });
        // Select dropdowns
        document.querySelectorAll('select').forEach(el => {
            const s = selector(el);
            const options = Array.from(el.options).slice(0, 10).map(o => ({value: o.value, text: o.text.trim()}));
            const label = el.getAttribute('aria-label') || (el.labels && el.labels[0] ? el.labels[0].textContent.trim() : '') || el.name || '';
            add({type: 'select', selector: s, label: label, options: options});
        });
        // Navigation links
        document.querySelectorAll('nav a[href], header a[href]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            const t = txt(el);
            if (t && t.length >= 2) add({type: 'nav_link', selector: selector(el), text: t, href: el.getAttribute('href')});
        });
        // Product links
        document.querySelectorAll('a[href*="/products/"], a[href*="/product/"]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            add({type: 'product_link', selector: selector(el), text: (txt(el) || '').substring(0, 80), href: el.getAttribute('href')});
        });
        // Cart/checkout links
        document.querySelectorAll('a[href]').forEach(el => {
            const href = el.getAttribute('href') || '';
            const t = txt(el);
            if (/cart|checkout|bag|basket/i.test(href) || /cart|checkout|bag|view.cart/i.test(t))
                add({type: 'link', selector: selector(el), text: t, href: href});
        });
        return els.slice(0, 60);
    }""")


def _execute_flow_action(page, action: dict) -> str:
    """Execute a flow action — extended with type and press."""
    act = action.get("action", "fail")
    selector = action.get("selector", "")
    value = action.get("value", "")

    if act == "click":
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=3000)
            try:
                el.click(timeout=3000)
            except Exception:
                el.click(force=True, timeout=3000)
            page.wait_for_timeout(1500)
            return "clicked"
        except Exception as e:
            return f"click failed: {e}"
    elif act == "type":
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=3000)
            el.fill(value, timeout=3000)
            page.wait_for_timeout(500)
            return f"typed '{value}'"
        except Exception as e:
            return f"type failed: {e}"
    elif act == "press":
        try:
            page.keyboard.press(value or "Enter")
            page.wait_for_timeout(1500)
            return f"pressed {value or 'Enter'}"
        except Exception as e:
            return f"press failed: {e}"
    elif act == "select":
        try:
            page.select_option(selector, value=value, timeout=3000)
            page.wait_for_timeout(1000)
            return f"selected {value}"
        except Exception as e:
            return f"select failed: {e}"
    elif act == "scroll":
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(1000)
        return "scrolled"
    elif act in ("done", "fail"):
        return act
    return f"unknown action: {act}"


def _ask_flow_agent(elements, screenshot_b64, goal, history, step,
                    system_prompt, max_steps=FLOW_MAX_STEPS) -> dict:
    """Ask Claude what action to take for a flow."""
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for browser flows.")
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("BROWSER_AGENT_MODEL", "claude-haiku-4-5-20251001")

    history_str = ""
    if history:
        history_str = "\nACTIONS SO FAR:\n"
        for h in history:
            history_str += (f"  Step {h['step']}: {h['action']}"
                           f"({h.get('selector','')[:30]}) -> {h.get('result','')}\n")

    elements_str = json.dumps(elements, indent=2)[:5000]
    user_content = [
        {"type": "text", "text": (
            f"GOAL: {goal}\nSTEP: {step}/{max_steps}\n"
            f"{history_str}\n\nINTERACTIVE ELEMENTS:\n{elements_str}")},
        {"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": screenshot_b64}},
    ]
    messages = [{"role": "user", "content": user_content}]
    for _attempt in range(2):
        msg = client.messages.create(
            model=model, max_tokens=200, system=system_prompt,
            messages=messages,
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        parsed = _parse_action_json(raw)
        if parsed is not None:
            return parsed
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": _JSON_RETRY_PROMPT})
    return {"action": "fail", "reason": f"Could not parse: {raw[:200]}"}


def _run_flow(start_url: str, goal: str, system_prompt: str,
              verify_fn=None, max_steps: int = FLOW_MAX_STEPS,
              timeout: int = 30) -> dict:
    """Generic browser flow runner."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "steps": [], "total_steps": 0,
                "final_reason": "Playwright not installed", "cart_verified": False}

    steps = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            )
            pg = ctx.new_page()
            pg.goto(start_url, timeout=timeout * 1000, wait_until="domcontentloaded")
            pg.wait_for_timeout(3000)
            _dismiss_popups(pg)

            last_selector = None
            repeat_count = 0
            consecutive_fails = 0

            for step_num in range(1, max_steps + 1):
                if consecutive_fails >= 3:
                    _force_clear_modals(pg)
                    consecutive_fails = 0

                elements = _extract_all_elements(pg)
                screenshot = _screenshot_b64(pg)
                action = _ask_flow_agent(elements, screenshot, goal, steps,
                                         step_num, system_prompt, max_steps)
                act = action.get("action", "fail")
                selector = action.get("selector", "")

                # Stuck loop detection
                if act == "click" and selector and selector == last_selector:
                    repeat_count += 1
                    if repeat_count >= 2:
                        steps.append({"step": step_num, "action": "fail",
                                      "selector": selector, "value": "",
                                      "reason": f"Stuck: repeated '{selector}' {repeat_count + 1} times",
                                      "result": "fail"})
                        break
                else:
                    repeat_count = 0
                last_selector = selector if act == "click" else last_selector

                step_record = {"step": step_num, "action": act, "selector": selector,
                               "value": action.get("value", ""),
                               "reason": action.get("reason", "")}

                if act in ("done", "fail"):
                    step_record["result"] = act
                    steps.append(step_record)
                    break

                result = _execute_flow_action(pg, action)
                step_record["result"] = result
                steps.append(step_record)

                if "failed" in result:
                    consecutive_fails += 1
                    _dismiss_popups(pg)
                else:
                    consecutive_fails = 0

                # Auto-verify after successful action
                if verify_fn and "failed" not in result and verify_fn(pg):
                    steps.append({"step": step_num + 1, "action": "done",
                                  "selector": "", "value": "",
                                  "reason": "Goal verified automatically",
                                  "result": "done"})
                    break

            verified = verify_fn(pg) if verify_fn else False
            success = any(s["action"] == "done" for s in steps)
            final_reason = steps[-1].get("reason", "") if steps else "no steps taken"
            browser.close()

            return {"success": success, "steps": steps,
                    "total_steps": len(steps), "final_reason": final_reason,
                    "cart_verified": verified}

    except Exception as e:
        return {"success": False, "steps": steps,
                "total_steps": len(steps), "final_reason": f"Browser error: {e}",
                "cart_verified": False}


# ---- Flow 1: Search Discovery ----

def run_search_discovery(url: str, timeout: int = 30) -> dict:
    """Search for the product from the homepage using site search."""
    product_name = _product_name_from_url(url)
    homepage = _homepage_url(url)

    goal = f"Find the product '{product_name}' using the site's search function."
    system_prompt = (
        "You are an AI shopping agent. Find a product using site search.\n\n"
        "Steps:\n"
        "1. Find the search icon or search bar (magnifying glass, 'Search' text)\n"
        "2. Click to open search if it's behind an icon\n"
        "3. Type the product name into the search input\n"
        "4. Press Enter or click the search button\n"
        "5. Look for the product in search results\n"
        "6. When you see the product in results, respond with 'done'\n\n"
        "If the site has no search or the product doesn't appear, respond 'fail'.\n\n"
        + FLOW_ACTIONS
    )

    def verify(pg):
        return pg.evaluate("""() => {
            const url = window.location.href.toLowerCase();
            const isSearch = url.includes('/search') || url.includes('q=') || url.includes('query=');
            if (!isSearch) return false;
            const links = document.querySelectorAll('a[href*="/products/"], a[href*="/product/"]');
            return links.length >= 1;
        }""")

    return _run_flow(homepage, goal, system_prompt, verify_fn=verify,
                     max_steps=10, timeout=timeout)


# ---- Flow 2: Checkout Reachable ----

def run_checkout_reachable(url: str, timeout: int = 30) -> dict:
    """Add product to cart and verify checkout page is reachable."""
    goal = "Add the product to cart, then navigate to the checkout page."
    system_prompt = (
        "You are an AI shopping agent. Add the product to cart and reach checkout.\n\n"
        "Steps:\n"
        "1. Select a variant (size/color) if required\n"
        "2. Click 'Add to Cart'\n"
        "3. After adding, click the cart icon or 'View Cart' link\n"
        "4. On the cart page, click 'Checkout' or 'Proceed to Checkout'\n"
        "5. When you see the checkout form (email, shipping fields), respond 'done'\n\n"
        "DO NOT fill in any personal information or payment details.\n"
        "If a popup blocks the page, try to close it first.\n\n"
        + FLOW_ACTIONS
    )

    def verify(pg):
        return pg.evaluate("""() => {
            const url = window.location.href.toLowerCase();
            if (url.includes('/checkout') || url.includes('/checkouts/')) return true;
            const fields = document.querySelectorAll(
                'input[name*="email"], input[name*="address"], '
                + 'input[autocomplete="email"], input[autocomplete="shipping"],'
                + '[data-step="contact_information"]');
            return fields.length >= 1;
        }""")

    return _run_flow(url, goal, system_prompt, verify_fn=verify,
                     max_steps=12, timeout=timeout)


# ---- Flow 3: Homepage to Product Navigation ----

def run_homepage_to_product(url: str, timeout: int = 30) -> dict:
    """Navigate from homepage to the product via site menus."""
    product_name = _product_name_from_url(url)
    homepage = _homepage_url(url)
    slug = url.rstrip("/").split("/")[-1].lower()

    goal = (f"Navigate from the homepage to the product '{product_name}' "
            f"using site menus and categories. Do NOT use search.")
    system_prompt = (
        "You are an AI shopping agent. Navigate from the homepage to a product "
        "using only site menus and category pages. Do NOT use search.\n\n"
        "Steps:\n"
        "1. Look at the navigation menu for relevant categories\n"
        "2. Click through to the appropriate collection/category page\n"
        "3. Browse products on the collection page\n"
        "4. Click on the target product when you find it\n"
        "5. When you're on the product page, respond 'done'\n\n"
        "Try 'All Products' or 'Shop All' if you can't find the right category.\n\n"
        + FLOW_ACTIONS
    )

    def verify(pg):
        slug_safe = json.dumps(slug)
        return pg.evaluate(f"() => window.location.href.toLowerCase().includes({slug_safe})")

    return _run_flow(homepage, goal, system_prompt, verify_fn=verify,
                     max_steps=15, timeout=timeout)


# ---- Flow 4: Product Comparison ----

def run_compare_products(url: str, timeout: int = 30) -> dict:
    """Find and navigate to a related product for comparison."""
    original_slug = url.rstrip("/").split("/")[-1].lower()

    goal = "Find a related/recommended product on this page and navigate to it."
    system_prompt = (
        "You are an AI shopping agent comparing products.\n\n"
        "Steps:\n"
        "1. Scroll down to find 'You may also like', 'Related products', "
        "'Customers also bought', or similar sections\n"
        "2. Click on a related product link or image\n"
        "3. Verify you're on a different product page\n"
        "4. When on the related product page, respond 'done'\n\n"
        "If there are no related products, respond 'fail'.\n\n"
        + FLOW_ACTIONS
    )

    def verify(pg):
        orig_safe = json.dumps(original_slug)
        return pg.evaluate(f"""() => {{
            const url = window.location.href.toLowerCase();
            return (url.includes('/products/') || url.includes('/product/'))
                   && !url.includes({orig_safe});
        }}""")

    return _run_flow(url, goal, system_prompt, verify_fn=verify,
                     max_steps=10, timeout=timeout)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python browser_agent.py <url> [flow]")
        print("Flows: atc (default), search, checkout, navigate, compare")
        sys.exit(1)
    flow = sys.argv[2] if len(sys.argv) > 2 else "atc"
    flows = {
        "atc": run_add_to_cart,
        "search": run_search_discovery,
        "checkout": run_checkout_reachable,
        "navigate": run_homepage_to_product,
        "compare": run_compare_products,
    }
    fn = flows.get(flow, run_add_to_cart)
    result = fn(sys.argv[1])
    print(json.dumps(result, indent=2))
