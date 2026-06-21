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
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("BROWSER_AGENT_MODEL",
                           os.environ.get("SHOPPER_MODEL", "claude-sonnet-4-6"))

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

    msg = client.messages.create(
        model=model, max_tokens=200, system=sys_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    # Parse JSON from response (strip markdown fences and extra text)
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # Extract first JSON object if there's text after it
    m = re.search(r"\{[^{}]*\}", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
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
            for step_num in range(1, MAX_STEPS + 1):
                # After several failed clicks, force-clear all modals
                if consecutive_fails >= 3:
                    _force_clear_modals(page)
                    consecutive_fails = 0

                elements = _extract_elements(page)
                screenshot = _screenshot_b64(page)
                action = _ask_agent(elements, screenshot, goal, steps, step_num)

                act = action.get("action", "fail")
                step_record = {
                    "step": step_num,
                    "action": act,
                    "selector": action.get("selector", ""),
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
                            "step": step_num,
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
                return
        except Exception:
            continue


def _check_cart_api(page) -> bool:
    """Check Shopify /cart.json API for items in cart."""
    try:
        # Use synchronous XHR — more reliable than async fetch for cart state
        result = page.evaluate("""() => {
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/cart.json', false);
                xhr.setRequestHeader('Accept', 'application/json');
                xhr.send(null);
                if (xhr.status === 200) {
                    var cart = JSON.parse(xhr.responseText);
                    return cart.item_count > 0;
                }
            } catch(e) {}
            return false;
        }""")
        return result
    except Exception:
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
        for (const el of document.querySelectorAll('*')) {
            const style = getComputedStyle(el);
            if ((style.position === 'fixed' || style.position === 'absolute') &&
                parseInt(style.zIndex) > 100 &&
                el.offsetWidth > window.innerWidth * 0.5 &&
                el.offsetHeight > window.innerHeight * 0.3 &&
                el.tagName !== 'HEADER' && el.tagName !== 'NAV') {
                el.remove();
            }
        }
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
            # "Added to cart" confirmation message
            page.evaluate("""() => {
                const body = document.body.innerText.toLowerCase();
                return body.includes('added to cart') || body.includes('added to bag')
                    || body.includes('item added') || body.includes('added to your cart');
            }"""),
            # Shopify cart API check (works on any Shopify store)
            _check_cart_api(page),
        ]
        return any(indicators)
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python browser_agent.py <url>")
        sys.exit(1)
    result = run_add_to_cart(sys.argv[1])
    print(json.dumps(result, indent=2))
