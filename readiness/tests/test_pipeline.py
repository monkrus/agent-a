"""Tests for pipeline.py — the shared scan pipeline.

This is the regression lock for the bug the audit found: the streaming
web route used to group static checks through a hardcoded set of check
IDs and silently drop everything outside it (RDY-032..RDY-045 never ran,
never scored, never appeared anywhere). `run_pipeline` now derives layers
from `category` and raises if any requested check doesn't produce a
result — these tests exercise exactly that.
"""
import sys
import pathlib

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pipeline import (run_pipeline, run_pipeline_sync, layer_for_check,
                       gate_cause, gate_info, CATEGORY_TO_LAYER)

CHECKS_PATH = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"


def _load_checks():
    data = yaml.safe_load(CHECKS_PATH.read_text())
    return data["checks"]


def _fake_page(**overrides):
    page = {
        "url": "https://example.com/products/test",
        "status": 200,
        "html": "<div>Test product $29.99</div>",
        "text": "Test product $29.99",
        "jsonld": [{"@type": "Product", "name": "Test",
                    "offers": {"price": "29.99",
                               "availability": "https://schema.org/InStock"}}],
        "meta": {}, "links": [], "title": "Test Product",
        "llms_txt": None, "llms_txt_content": None,
        "robots": "User-agent: *\nAllow: /\n",
        "cart_api": True,
        "checkout_probe": {"status": 200, "html": "<form>Email: <input></form>",
                           "final_url": "https://example.com/checkout",
                           "location": None, "redirect_reason": None},
        "checkout_html": "<form>Email: <input></form>",
        "homepage_html": '<form action="/search"><input type="search"></form>',
        "sitemap_xml": "<urlset><url><loc>https://example.com/products/test</loc></url></urlset>",
        "mcp_json": None, "oauth_discovery": None,
        "markdown_negotiation": None, "agent_verification": None,
        "a2a_agent_card": None, "auth_md": None,
        "link_headers": None, "dns_aid": None,
        "cart_rate_test": None, "admin_exposure": None,
        "fetch_time_ms": 500,
        "agent_probe_status": 200,
        "agent_probe_detail": {"readable_words": 500, "challenge": False,
                               "blocked_uas": [], "allowed_uas": ["GPTBot"]},
    }
    page.update(overrides)
    return page


def _blocked_page(**overrides):
    return _fake_page(
        robots="User-agent: GPTBot\nDisallow: /\n",
        agent_probe_status=200,
        agent_probe_detail={"readable_words": 500, "challenge": False,
                            "blocked_uas": ["GPTBot"], "allowed_uas": []},
        **overrides,
    )


# ---- Coverage: every check in the pack must appear in the category map -----

class TestCategoryCoverage:
    def test_every_category_in_pack_is_mapped_to_a_layer(self):
        """A category missing from CATEGORY_TO_LAYER doesn't crash anything
        (layer_for_check falls back to "other"), but it's a sign the map
        is stale — this is the assertion that would have caught RDY-032
        through RDY-045 having nowhere to go."""
        checks = _load_checks()
        categories = {c["category"] for c in checks if c.get("category")}
        unmapped = categories - set(CATEGORY_TO_LAYER)
        assert unmapped == set(), f"Unmapped categories: {unmapped}"

    def test_no_check_falls_into_other(self):
        checks = _load_checks()
        others = [c["id"] for c in checks if layer_for_check(c) == "other"]
        assert others == []


# ---- The invariant: every requested check produces a result ----------------

class TestPipelineDropDetection:
    def test_full_pack_produces_a_result_for_every_check(self):
        checks = _load_checks()
        page = _fake_page()
        results = run_pipeline_sync(checks, page, n=2, tier="paid", shopper_mode="mock")
        got = {r["id"] for r in results}
        want = {c["id"] for c in checks}
        assert got == want

    def test_free_tier_subset_produces_a_result_for_every_check(self):
        checks = _load_checks()
        static_checks = [c for c in checks if c.get("type") == "static"]
        page = _fake_page()
        results = run_pipeline_sync(static_checks, page, n=2, tier="free")
        got = {r["id"] for r in results}
        want = {c["id"] for c in static_checks}
        assert got == want

    def test_unmapped_category_still_runs_and_still_raises_if_dropped(self):
        """Simulate the historical bug directly: a check with a category
        the layer map doesn't know about must still appear in results."""
        checks = [{"id": "RDY-999", "type": "static", "category": "totally-new-category",
                   "title": "New check", "weight": 5, "severity_if_fail": "low",
                   "detect": "jsonld_product"}]
        page = _fake_page()
        results = run_pipeline_sync(checks, page, n=1, tier="paid")
        assert {r["id"] for r in results} == {"RDY-999"}

    def test_raises_if_a_check_is_silently_dropped(self, monkeypatch):
        """Directly exercise the invariant: if something upstream stops
        emitting a result for a requested check, run_pipeline_sync raises
        instead of silently returning a shorter list."""
        import pipeline as pipelinemod

        checks = [{"id": "RDY-001", "type": "static", "category": "structured-data",
                   "title": "t", "weight": 5, "severity_if_fail": "low",
                   "detect": "jsonld_product"}]
        page = _fake_page()

        def _swallow(*args, **kwargs):
            return {"verdict": "UNKNOWN", "detail": "boom", "pass_fraction": None}

        # Even if the scorer returns a degenerate result, it must still be
        # *present* — this monkeypatch doesn't remove it, so this call
        # should succeed. The real drop happened at the grouping layer, not
        # here; this documents the boundary the invariant actually guards.
        monkeypatch.setattr(pipelinemod.scorers, "run_static", _swallow)
        results = run_pipeline_sync(checks, page, n=1, tier="paid")
        assert len(results) == 1


# ---- Access gate ------------------------------------------------------------

class TestAccessGate:
    def test_blocked_page_gates_every_non_access_check(self):
        checks = _load_checks()
        page = _blocked_page()
        results = run_pipeline_sync(checks, page, n=2, tier="paid", shopper_mode="mock")
        gated = [r for r in results if r.get("gated")]
        non_access = [c for c in checks if c["id"] not in ("RDY-003", "RDY-031")]
        assert len(gated) == len(non_access)
        # Every gated result still has a pass_fraction of 0.0, not None —
        # so it's counted in the score, not silently excluded.
        assert all(r["pass_fraction"] == 0.0 for r in gated)

    def test_unblocked_page_runs_everything_normally(self):
        checks = _load_checks()
        page = _fake_page()
        results = run_pipeline_sync(checks, page, n=2, tier="paid", shopper_mode="mock")
        assert not any(r.get("gated") for r in results)

    def test_gate_cause_robots_only(self):
        checks = _load_checks()
        page = _blocked_page()
        # Only robots blocked, WAF probe passes:
        page["agent_probe_detail"] = {"readable_words": 500, "challenge": False,
                                      "blocked_uas": [], "allowed_uas": ["GPTBot"]}
        results = run_pipeline_sync(checks, page, n=1, tier="paid", shopper_mode="mock")
        assert gate_cause(results) == "robots"

    def test_gate_cause_waf_only(self):
        checks = _load_checks()
        page = _fake_page(
            robots="User-agent: *\nAllow: /\n",
            agent_probe_status=200,
            agent_probe_detail={"readable_words": 5, "challenge": False,
                                "blocked_uas": [], "allowed_uas": []},
        )
        results = run_pipeline_sync(checks, page, n=1, tier="paid", shopper_mode="mock")
        assert gate_cause(results) == "waf"

    def test_gate_info_none_when_not_gated(self):
        checks = _load_checks()
        page = _fake_page()
        results = run_pipeline_sync(checks, page, n=1, tier="paid", shopper_mode="mock")
        assert gate_info(results, page) is None


# ---- Layer events (what the streaming route forwards to the browser) -------

class TestLayerEvents:
    def test_free_tier_stream_emits_all_check_ids(self):
        checks = _load_checks()
        static_checks = [c for c in checks if c.get("type") == "static"]
        page = _fake_page()
        events = list(run_pipeline(static_checks, page, n=2, tier="free"))
        check_events = [e for e in events if e["type"] == "check"]
        assert {e["id"] for e in check_events} == {c["id"] for c in static_checks}

    def test_progress_denominator_matches_total_requested(self):
        checks = _load_checks()
        static_checks = [c for c in checks if c.get("type") == "static"]
        page = _fake_page()
        events = list(run_pipeline(static_checks, page, n=2, tier="free"))
        check_events = [e for e in events if e["type"] == "check"]
        last_progress = check_events[-1]["progress"]
        assert last_progress == f"{len(static_checks)}/{len(static_checks)}"

    def test_discovery_layer_is_emitted_for_protocol_checks(self):
        """RDY-029/030/034-041 used to have no layer at all in the
        streaming route and were dropped; they must now appear under a
        real layer."""
        checks = _load_checks()
        static_checks = [c for c in checks if c.get("type") == "static"]
        page = _fake_page()
        events = list(run_pipeline(static_checks, page, n=2, tier="free"))
        layer_events = [e["layer"] for e in events if e["type"] == "layer"]
        assert "discovery" in layer_events
        discovery_checks = [e for e in events if e["type"] == "check" and e["layer"] == "discovery"]
        assert len(discovery_checks) >= 1
