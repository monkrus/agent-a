#!/usr/bin/env python3
"""
pipeline.py — the one scan pipeline. Used by scan.py (CLI), app.py's
/scan and /scan-stream routes, and batch.py.

Why this file exists
---------------------
Before this module, the fetch -> access-gate -> static -> browser -> shopper
flow was implemented four separate times: scan.py::scan(), app.py::_run_scan,
the generate() closure inside app.py::scan_stream, and batch.py::_run_scan.
They drifted. The streaming route's copy grouped static checks through a
hardcoded set of check IDs (LAYER_CHECKS) and silently dropped every check
outside that set — RDY-032 through RDY-045 (14 of 30 free-tier checks,
16 of 66 weight points) never ran, never appeared in the payload, and were
never counted in the score. batch.py's copy never implemented the access
gate at all. Same bug, different shapes, because there was no single place
that had to stay correct.

`run_pipeline` is now that single place. It is a generator: it yields one
event per layer boundary and per completed check, and a final `complete`
event carrying the full result list. Callers that want live progress (the
SSE route) consume the events; callers that just want the end result
(`run_pipeline_sync`) drain the generator and keep the last event.

The categories in checks/shopify-v1.yaml are mapped to a *closed* set of
display/scoring layers (CATEGORY_TO_LAYER). A category that isn't in the
map still runs — it lands in an "other" layer that is rendered and scored
like every other layer — and `run_pipeline` raises if any check anywhere
was requested and didn't produce exactly one result. That assertion is the
one line that would have caught the original bug.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import scorers
from shopper import ask_batch

# RDY-031 (live WAF/challenge probe) and RDY-003 (robots.txt) are the
# access gate: if either fails, nothing downstream is worth running or
# scoring — an agent that can't reach the page can't do anything else.
ACCESS_GATE_IDS = {"RDY-031", "RDY-003"}

# category -> layer. Every category present in the check pack must be
# listed here. Anything not listed falls into "other", which still runs
# and still counts (see module docstring) — but it should not happen in
# practice, so treat a growing "other" bucket as a sign this map is stale.
CATEGORY_TO_LAYER = {
    "structured-data": "data",
    "price-legibility": "data",
    "rendering": "data",
    "policy-legibility": "data",
    "agent-access": "data",
    "price-extraction": "extraction",
    "availability-extraction": "extraction",
    "identity-extraction": "extraction",
    "policy-extraction": "extraction",
    "agent-interaction": "interaction",
    "agent-checkout": "interaction",
    "agent-search": "interaction",
    "agent-navigation": "interaction",
    "agent-comparison": "interaction",
    "security": "security",
    "agent-protocol": "discovery",
    "agent-discovery": "discovery",
    "agent-performance": "discovery",
}

LAYER_LABELS = {
    "access": "Layer 0: Access",
    "data": "Layer 1: Data",
    "extraction": "Layer 2: Extraction",
    "interaction": "Layer 3: Interaction",
    "security": "Layer 4: Security",
    "discovery": "Layer 5: Protocol & Discovery",
    "other": "Other checks",
}

# Display order for layers that run after the access gate.
LAYER_ORDER = ["data", "extraction", "interaction", "security", "discovery"]


def layer_for_check(check: dict) -> str:
    """Which display/scoring layer a check belongs to.

    RDY-031 and RDY-003 are always "access" regardless of category (they
    gate everything else). Every other check is placed by `category`.
    """
    if check.get("id") in ACCESS_GATE_IDS:
        return "access"
    return CATEGORY_TO_LAYER.get(check.get("category", ""), "other")


def _base(c):
    return {k: c.get(k) for k in
            ("id", "type", "category", "title", "weight", "severity_if_fail", "fix")}


def gate_cause(results: list[dict]) -> str | None:
    """'robots', 'waf', 'both', or None — which access-gate check(s) failed.

    Used to keep remediation copy honest: never blame a CDN/WAF for a
    robots.txt block, and never claim a vendor was identified unless the
    probe actually returned vendor evidence.
    """
    robots_failed = any(r.get("id") == "RDY-003" and r.get("verdict") == "FAIL"
                        for r in results)
    waf_failed = any(r.get("id") == "RDY-031" and r.get("verdict") == "FAIL"
                     for r in results)
    if robots_failed and waf_failed:
        return "both"
    if waf_failed:
        return "waf"
    if robots_failed:
        return "robots"
    return None


def gate_info(results: list[dict], page: dict) -> dict | None:
    """Structured access-gate summary for the payload, or None if not gated."""
    gated = [r for r in results if r.get("gated")]
    if not gated:
        return None
    probe_detail = page.get("agent_probe_detail") or {}
    return {
        "gate_cause": gate_cause(results),
        "blocked_uas": probe_detail.get("blocked_uas", []),
        "allowed_uas": probe_detail.get("allowed_uas", []),
        "gated_count": len(gated),
    }


def run_pipeline(checks: list[dict], page: dict, n: int, tier: str = "free",
                 shopper_mode: str | None = None, sample_limit: int | None = 3):
    """Generator: run the full scan pipeline against `checks`, yielding
    progress events. The last event is always {"type": "complete",
    "results": [...]}.

    Event shapes:
      {"type": "layer", "layer": id, "label": str}
      {"type": "check_running", "id", "title", "layer"}
      {"type": "check", "id", "title", "verdict", "detail", "layer", "progress"}
      {"type": "gate_blocked", "message", "skipped", "blocked_uas", "allowed_uas",
       "gate_cause"}
      {"type": "gate_passed", "message"}
      {"type": "complete", "results": [...]}

    `sample_limit` caps how many raw shopper answers are stored per check
    (the web UI only shows a preview; the CLI report keeps the full set via
    `sample_limit=None`).
    """
    # shopper_mode is passed straight through to ask_batch. Leaving it None
    # means "let ask_batch resolve it from the SHOPPER env var" — this is
    # what the CLI relies on; the web app passes it explicitly per tier.
    static_checks = [c for c in checks if c.get("type") == "static"]
    browser_checks = [c for c in checks if c.get("type") == "browser"]
    shopper_checks = [c for c in checks if c.get("type") == "shopper"]

    if tier == "free":
        assert not shopper_checks, "free tier must never carry shopper checks"
        assert not browser_checks, "free tier must never carry browser checks"

    results: list[dict] = []
    completed = 0
    total = len(checks)

    def _finish(c, r, layer):
        nonlocal completed
        result = {**_base(c), **r}
        results.append(result)
        completed += 1
        return {
            "type": "check", "id": c["id"], "title": c["title"],
            "verdict": result.get("verdict"), "detail": (result.get("detail") or "")[:120],
            "layer": layer, "progress": f"{completed}/{total}",
        }

    # --- Access gate ---
    access_checks = [c for c in static_checks if c.get("id") in ACCESS_GATE_IDS]
    other_static = [c for c in static_checks if c.get("id") not in ACCESS_GATE_IDS]

    if access_checks:
        yield {"type": "layer", "layer": "access", "label": LAYER_LABELS["access"]}
        for c in access_checks:
            r = scorers.run_static(c, page)
            yield _finish(c, r, "access")

    access_blocked = any(r.get("id") in ACCESS_GATE_IDS and r.get("verdict") == "FAIL"
                         for r in results)

    if access_blocked:
        gate_reasons = []
        for r in results:
            if r.get("id") in ACCESS_GATE_IDS and r.get("verdict") == "FAIL":
                if r["id"] == "RDY-031":
                    gate_reasons.append("site blocks agent-like traffic")
                elif r["id"] == "RDY-003":
                    gate_reasons.append("robots.txt blocks AI crawlers")
                else:
                    gate_reasons.append(r.get("title"))
        gate_reason = ("Skipped: site blocks agent access "
                       f"({'; '.join(gate_reasons)}). "
                       "Fix access first — nothing else matters until agents can reach the page.")
        probe_detail = page.get("agent_probe_detail") or {}
        remaining = other_static + browser_checks + shopper_checks
        yield {
            "type": "gate_blocked",
            "message": f"ACCESS BLOCKED — {'; '.join(gate_reasons)}",
            "skipped": len(remaining),
            "blocked_uas": probe_detail.get("blocked_uas", []),
            "allowed_uas": probe_detail.get("allowed_uas", []),
            "gate_cause": gate_cause(results),
        }
        for c in remaining:
            r = {"verdict": "FAIL", "detail": gate_reason,
                 "pass_fraction": 0.0, "gated": True}
            yield _finish(c, r, layer_for_check(c))
    else:
        yield {"type": "gate_passed", "message": "Access OK — continuing scan..."}

        remaining_by_layer: dict[str, list[dict]] = {}
        for c in other_static:
            remaining_by_layer.setdefault(layer_for_check(c), []).append(c)

        # Layer: data (static only)
        layer_checks = remaining_by_layer.pop("data", [])
        if layer_checks:
            yield {"type": "layer", "layer": "data", "label": LAYER_LABELS["data"]}
            for c in layer_checks:
                r = scorers.run_static(c, page)
                yield _finish(c, r, "data")

        # Layer: extraction (shopper checks + any static extraction checks,
        # e.g. RDY-033 which is a static probe in the extraction category)
        extraction_static = remaining_by_layer.pop("extraction", [])
        if shopper_checks or extraction_static:
            yield {"type": "layer", "layer": "extraction", "label": LAYER_LABELS["extraction"]}

        if shopper_checks:
            tasks = {c["id"]: c["task"] for c in shopper_checks}
            workers = min(n, 10)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                batch_results = list(pool.map(
                    lambda _: ask_batch(page, tasks, shopper=shopper_mode), range(n)))
            answers_by_check = {cid: [br[cid] for br in batch_results] for cid in tasks}
            for c in shopper_checks:
                answers = answers_by_check[c["id"]]
                g = scorers.grade_shopper(c, page, answers)
                stored_answers = answers if sample_limit is None else answers[:sample_limit]
                g = {**g, "sample_answers": stored_answers}
                yield _finish(c, g, "extraction")

        for c in extraction_static:
            r = scorers.run_static(c, page)
            yield _finish(c, r, "extraction")

        # Layer: interaction (static interaction checks + browser checks)
        interaction_static = remaining_by_layer.pop("interaction", [])
        if interaction_static or browser_checks:
            yield {"type": "layer", "layer": "interaction", "label": LAYER_LABELS["interaction"]}

            for c in interaction_static:
                r = scorers.run_static(c, page)
                yield _finish(c, r, "interaction")

            if browser_checks:
                for c in browser_checks:
                    yield {"type": "check_running", "id": c["id"], "title": c["title"],
                           "layer": "interaction"}
                with ThreadPoolExecutor(max_workers=len(browser_checks)) as pool:
                    future_to_check = {pool.submit(scorers.run_browser, c, page): c
                                       for c in browser_checks}
                    for future in as_completed(future_to_check):
                        c = future_to_check[future]
                        try:
                            r = future.result()
                        except Exception as exc:
                            r = {"verdict": "UNKNOWN",
                                 "detail": f"Browser check error: {exc}",
                                 "pass_fraction": None}
                        yield _finish(c, r, "interaction")

        # Layer: security (static)
        layer_checks = remaining_by_layer.pop("security", [])
        if layer_checks:
            yield {"type": "layer", "layer": "security", "label": LAYER_LABELS["security"]}
            for c in layer_checks:
                r = scorers.run_static(c, page)
                yield _finish(c, r, "security")

        # Layer: protocol & discovery (static) — RDY-029/030/034-041.
        # These used to have no layer at all and were dropped.
        layer_checks = remaining_by_layer.pop("discovery", [])
        if layer_checks:
            yield {"type": "layer", "layer": "discovery", "label": LAYER_LABELS["discovery"]}
            for c in layer_checks:
                r = scorers.run_static(c, page)
                yield _finish(c, r, "discovery")

        # Anything left is an unmapped category. It still runs — see the
        # module docstring for why this must never silently disappear.
        for layer, layer_checks in remaining_by_layer.items():
            yield {"type": "layer", "layer": layer,
                   "label": LAYER_LABELS.get(layer, "Other checks")}
            for c in layer_checks:
                r = scorers.run_static(c, page)
                yield _finish(c, r, layer)

    # Invariant: every requested check produced exactly one result. This is
    # the check that would have caught RDY-032..RDY-045 being dropped.
    got_ids = {r["id"] for r in results}
    want_ids = {c["id"] for c in checks}
    if got_ids != want_ids:
        missing = sorted(want_ids - got_ids)
        raise RuntimeError(f"pipeline dropped checks, no result produced for: {missing}")

    yield {"type": "complete", "results": results}


def run_pipeline_sync(checks: list[dict], page: dict, n: int, tier: str = "free",
                      shopper_mode: str | None = None,
                      sample_limit: int | None = 3) -> list[dict]:
    """Run the pipeline without caring about progress; return the final results."""
    results = None
    for event in run_pipeline(checks, page, n, tier=tier, shopper_mode=shopper_mode,
                              sample_limit=sample_limit):
        if event["type"] == "complete":
            results = event["results"]
    assert results is not None, "pipeline generator finished without a 'complete' event"
    return results
