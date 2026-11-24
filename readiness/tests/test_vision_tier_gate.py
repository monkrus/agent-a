"""RDY-046 image analysis costs API money: paid scans only, never free scans."""
import pathlib
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import emotional_gap  # noqa: E402
import scorers  # noqa: E402

FAKE_GAP = {"gap_score": 20, "weighted_gap_score": 20, "missing_emotional_concepts": [],
            "covered_emotional_concepts": ["cozy"], "category": "apparel", "category_weight": 5}


def _page(tier=None):
    p = {"text": "A soft wool sweater. " * 30, "title": "Sweater",
         "images": ["https://cdn.example/a.jpg"], "jsonld": []}
    if tier:
        p["_tier"] = tier
    return p


@pytest.mark.parametrize("env", ["anthropic", "mock"])
def test_free_tier_never_calls_vision(monkeypatch, env):
    monkeypatch.setenv("SHOPPER", env)
    with patch.object(emotional_gap, "analyze_emotional_gap", return_value=FAKE_GAP) as gap:
        scorers.static_copy_richness(_page("free"))
    gap.assert_not_called()


@pytest.mark.parametrize("env", ["anthropic", "mock"])
def test_paid_tier_uses_vision_regardless_of_env(monkeypatch, env):
    monkeypatch.setenv("SHOPPER", env)
    with patch.object(emotional_gap, "analyze_emotional_gap", return_value=FAKE_GAP) as gap:
        scorers.static_copy_richness(_page("paid"))
    gap.assert_called_once()


@pytest.mark.parametrize("env,called", [("anthropic", True), ("mock", False)])
def test_no_tier_cli_follows_shopper_env(monkeypatch, env, called):
    monkeypatch.setenv("SHOPPER", env)
    with patch.object(emotional_gap, "analyze_emotional_gap", return_value=FAKE_GAP) as gap:
        scorers.static_copy_richness(_page())
    assert gap.called is called


def test_free_web_scan_end_to_end_makes_no_vision_call(monkeypatch):
    """Through app._run_scan with tier='free' and SHOPPER=anthropic in the env."""
    import app
    monkeypatch.setenv("SHOPPER", "anthropic")
    page = {"url": "https://example.com/products/x", "final_url": "https://example.com/products/x",
            "status": 200, "html": "<html></html>", "text": "Sweater. " * 100, "title": "Sweater",
            "jsonld": [], "meta": {}, "images": ["https://cdn.example/a.jpg"], "robots": "",
            "fetch_time_ms": 100, "agent_probe_status": 200,
            "agent_probe_detail": {"readable_words": 500, "challenge": False,
                                   "blocked_uas": [], "allowed_uas": ["GPTBot"]}}
    with patch.object(emotional_gap, "analyze_emotional_gap", return_value=FAKE_GAP) as gap:
        try:
            app._run_scan(page["url"], n=1, pre_fetched_page=page, tier="free")
        except Exception:
            pass  # other static checks may dislike the minimal page; we only care about vision
    gap.assert_not_called()
    assert page["_tier"] == "free"
