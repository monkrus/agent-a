#!/usr/bin/env python3
"""
shopper.py — the simulated shopping agent.

Given a `page` (from fetch.py) and a `task` (from a shopper check), it returns
what an AI shopping agent would extract. This is the readiness-track equivalent
of `call_agent` in the audit track, and it follows the same mock-first pattern:

    SHOPPER=mock       (default) no creds; deterministic-ish, sometimes wrong,
                       so the pipeline runs offline and the scoring loop is real.
    SHOPPER=anthropic  real extraction via the API.

Return: the agent's answer as a short string.

Why it must run N times: extraction is non-deterministic. A page that yields the
right price 6/10 is a reliability finding, exactly like a 6/10 pass rate in the
audit methodology. The runner (scan.py) handles the N loop; this just answers
once.
"""
from __future__ import annotations
import os
import random
import re


def _page_blob(page: dict, limit: int = 6000) -> str:
    """Compact text the agent 'sees'. Mirrors what a text-mode agent gets."""
    parts = [f"URL: {page.get('url','')}", f"TITLE: {page.get('title','')}"]
    if page.get("jsonld"):
        parts.append("STRUCTURED_DATA: present")
    parts.append("PAGE TEXT:\n" + (page.get("text", "") or "")[:limit])
    return "\n".join(parts)


# ---- mock shopper (no creds) ------------------------------------------------
def _mock_answer(page: dict, task: str) -> str:
    """
    Fake but plausible extraction. Deliberately imperfect so pass rates aren't
    all 10/10 — proves the scoring distinguishes good pages from bad ones.
    Behavior keys off whether the page actually exposes the data.
    """
    text = (page.get("text", "") or "")
    has_price = bool(re.search(r"[$£€]\s?\d", text)) or _jsonld_price(page) is not None
    t = task.lower()

    if "price" in t:
        gt = _jsonld_price(page)
        visible = re.search(r"[$£€]\s?(\d[\d,]*\.?\d*)", text)
        if gt is not None and random.random() < (0.85 if has_price else 0.3):
            return str(gt)
        if visible and random.random() < 0.6:
            return visible.group(1).replace(",", "")
        return random.choice(["unknown", "29.99", "I couldn't find a price"])
    if "in stock" in t or "in_stock" in t:
        avail = _jsonld_availability(page)
        if avail and random.random() < 0.8:
            return avail
        return random.choice(["in_stock", "unknown", "out_of_stock"])
    if "name of the main product" in t:
        name = page.get("title") or "this product"
        return name if random.random() < 0.8 else "a product"
    if "return" in t:
        # ambiguous pages -> inconsistent answers across runs
        return random.choice(["30", "14", "30", "not stated"])
    if "shipping" in t:
        return random.choice(["Free shipping", "Calculated at checkout",
                              "Free shipping", "$5.99"])
    return "unknown"


# ---- real shopper -----------------------------------------------------------
def _anthropic_answer(page: dict, task: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("SHOPPER_MODEL", "claude-sonnet-4-6")
    sys_prompt = (
        "You are an AI shopping agent extracting facts from a product page. "
        "Use ONLY the page content provided. If the page does not clearly state "
        "the answer, say 'unknown'. Answer in the exact short format requested."
    )
    msg = client.messages.create(
        model=model, max_tokens=120, system=sys_prompt,
        messages=[{"role": "user",
                   "content": f"{_page_blob(page)}\n\nTASK: {task}"}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


# ---- jsonld helpers (also used by scorers for ground truth) -----------------
def _jsonld_offers(page: dict):
    for obj in page.get("jsonld", []):
        if not isinstance(obj, dict):
            continue
        types = obj.get("@type", "")
        types = types if isinstance(types, list) else [types]
        if any(str(x).lower() == "product" for x in types):
            off = obj.get("offers")
            if isinstance(off, list):
                off = off[0] if off else None
            return obj, (off if isinstance(off, dict) else None)
    return None, None


def _jsonld_price(page: dict):
    _, off = _jsonld_offers(page)
    if off and off.get("price") is not None:
        try:
            return float(str(off["price"]).replace(",", ""))
        except (TypeError, ValueError):
            return None
    amt = page.get("meta", {}).get("product:price:amount")
    if amt:
        try:
            return float(amt)
        except ValueError:
            return None
    return None


def _jsonld_availability(page: dict):
    _, off = _jsonld_offers(page)
    if off and off.get("availability"):
        v = str(off["availability"]).lower()
        if "instock" in v:
            return "in_stock"
        if "outofstock" in v or "soldout" in v:
            return "out_of_stock"
    return None


_BACKENDS = {"mock": _mock_answer, "anthropic": _anthropic_answer}


def ask(page: dict, task: str) -> str:
    backend = _BACKENDS.get(os.environ.get("SHOPPER", "mock"), _mock_answer)
    try:
        return backend(page, task)
    except Exception as e:
        return f"__error__: {e}"
