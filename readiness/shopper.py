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

def _types_lower(obj):
    """Return set of lowercased @type values for a JSON-LD object."""
    t = obj.get("@type", "")
    return {str(x).lower() for x in (t if isinstance(t, list) else [t])}


def _extract_offer(obj):
    """Extract the first Offer dict from an object's 'offers' field."""
    off = obj.get("offers")
    if isinstance(off, list):
        off = off[0] if off else None
    return off if isinstance(off, dict) else None


def _flatten_jsonld(objects):
    """Yield all JSON-LD objects, unwrapping @graph containers and arrays."""
    for obj in objects:
        if isinstance(obj, list):
            yield from _flatten_jsonld(obj)
            continue
        if not isinstance(obj, dict):
            continue
        yield obj
        # Recurse into @graph
        graph = obj.get("@graph")
        if isinstance(graph, list):
            yield from _flatten_jsonld(graph)


def _jsonld_offers(page: dict):
    """Find a Product (or ProductGroup) and its first Offer.

    Handles:
    - top-level @type: "Product"
    - @type given as array (e.g. ["Product", "Thing"])
    - ProductGroup with hasVariant[] of Product (uses group-level
      fields + first variant's offers)
    - @graph containers holding either of the above
    """
    objects = list(_flatten_jsonld(page.get("jsonld", [])))

    # Pass 1: look for a direct Product
    for obj in objects:
        if "product" in _types_lower(obj):
            return obj, _extract_offer(obj)

    # Pass 2: look for ProductGroup with hasVariant
    for obj in objects:
        if "productgroup" in _types_lower(obj):
            variants = obj.get("hasVariant", [])
            if not isinstance(variants, list):
                variants = [variants]
            for v in variants:
                if isinstance(v, dict) and "product" in _types_lower(v):
                    # Merge: group-level fields + variant offers
                    merged = dict(obj)  # shallow copy of group
                    merged.pop("hasVariant", None)
                    merged["@type"] = "Product"
                    # Variant-level offers override
                    off = _extract_offer(v)
                    if off:
                        merged["offers"] = v.get("offers")
                    return merged, off
            # ProductGroup without typed variants — use its own offers
            return obj, _extract_offer(obj)

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


# ---- batched shopper (all tasks in one call) --------------------------------

def _mock_batch(page: dict, tasks: dict[str, str]) -> dict[str, str]:
    """Mock batch: just call individual mock for each task."""
    return {cid: _mock_answer(page, task) for cid, task in tasks.items()}


def _anthropic_batch(page: dict, tasks: dict[str, str]) -> dict[str, str]:
    """Real batch: all extraction tasks in a single API call."""
    import anthropic
    import json as _json
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("SHOPPER_MODEL", "claude-sonnet-4-6")

    # Build combined prompt
    task_lines = []
    for cid, task in tasks.items():
        task_lines.append(f'  "{cid}": "{task}"')
    tasks_block = "{\n" + ",\n".join(task_lines) + "\n}"

    sys_prompt = (
        "You are an AI shopping agent extracting facts from a product page. "
        "Use ONLY the page content provided. If the page does not clearly state "
        "the answer, say 'unknown'. You will receive multiple extraction tasks. "
        "Answer each one with a short value. Return a JSON object mapping each "
        "task ID to your answer string. No explanation, just the JSON."
    )

    user_msg = (
        f"{_page_blob(page)}\n\n"
        f"TASKS (answer each with a short value):\n{tasks_block}\n\n"
        f"Reply with ONLY a JSON object like: {{\"RDY-006\": \"29.99\", \"RDY-007\": \"in_stock\", ...}}"
    )

    msg = client.messages.create(
        model=model, max_tokens=300, system=sys_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    # Parse JSON response
    try:
        result = _json.loads(raw)
        if isinstance(result, dict):
            return {cid: str(result.get(cid, "unknown")) for cid in tasks}
    except _json.JSONDecodeError:
        # Try to extract JSON from response
        m = re.search(r"\{[^{}]*\}", raw, re.S)
        if m:
            try:
                result = _json.loads(m.group())
                if isinstance(result, dict):
                    return {cid: str(result.get(cid, "unknown")) for cid in tasks}
            except _json.JSONDecodeError:
                pass

    # Fallback: return unknown for all
    return {cid: "unknown" for cid in tasks}


_BATCH_BACKENDS = {"mock": _mock_batch, "anthropic": _anthropic_batch}


def ask_batch(page: dict, tasks: dict[str, str]) -> dict[str, str]:
    """Ask all shopper tasks in a single API call. Returns {check_id: answer}."""
    backend = _BATCH_BACKENDS.get(os.environ.get("SHOPPER", "mock"), _mock_batch)
    try:
        return backend(page, tasks)
    except Exception as e:
        return {cid: f"__error__: {e}" for cid in tasks}
