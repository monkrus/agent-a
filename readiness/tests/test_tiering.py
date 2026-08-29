"""Tests for free/paid tiering — the money boundary.

The hard requirement: no free-tier request may ever construct or call
the Anthropic shopper. These tests regression-lock that boundary.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


# ---- resolve_tier -----------------------------------------------------------

class TestResolveTier:
    def test_none_is_free(self):
        from app import resolve_tier
        assert resolve_tier(None) == "free"

    def test_unpaid_id_is_free(self):
        from app import resolve_tier
        assert resolve_tier("nonexistent1234") == "free"

    def test_paid_id_is_paid(self):
        """Mock _payment_completed to return True."""
        from unittest.mock import patch
        from app import resolve_tier
        with patch("app._payment_completed", return_value=True):
            assert resolve_tier("paid_scan_123") == "paid"


# ---- checks_for_tier -------------------------------------------------------

class TestChecksForTier:
    SAMPLE_CHECKS = [
        {"id": "RDY-001", "type": "static", "detect": "jsonld_product"},
        {"id": "RDY-002", "type": "static", "detect": "price_in_html"},
        {"id": "RDY-006", "type": "shopper", "task": "extract price"},
        {"id": "RDY-007", "type": "shopper", "task": "extract availability"},
        {"id": "RDY-017", "type": "browser", "detect": "add_to_cart_flow"},
    ]

    def test_free_has_no_shopper_checks(self):
        from app import checks_for_tier
        free = checks_for_tier("free", self.SAMPLE_CHECKS)
        shopper = [c for c in free if c.get("type") == "shopper"]
        assert len(shopper) == 0

    def test_free_has_no_browser_checks(self):
        from app import checks_for_tier
        free = checks_for_tier("free", self.SAMPLE_CHECKS)
        browser = [c for c in free if c.get("type") == "browser"]
        assert len(browser) == 0

    def test_free_has_only_static(self):
        from app import checks_for_tier
        free = checks_for_tier("free", self.SAMPLE_CHECKS)
        assert all(c.get("type") == "static" for c in free)
        assert len(free) == 2

    def test_paid_has_all_checks(self):
        from app import checks_for_tier
        paid = checks_for_tier("paid", self.SAMPLE_CHECKS)
        assert len(paid) == 5


# ---- Integration: free scan never constructs shopper -------------------------

class TestFreeScanNoShopper:
    def test_free_scan_never_calls_anthropic(self):
        """Monkeypatch the anthropic shopper to raise if constructed;
        assert a free _run_scan completes without ever constructing it."""
        from unittest.mock import patch, MagicMock
        import app

        # Create a fake page so fetch isn't called
        fake_page = {
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

        # Patch ask_batch to explode if called
        def _boom(*args, **kwargs):
            raise AssertionError("Shopper was called during a free scan!")

        with patch.object(app, "ask_batch", side_effect=_boom):
            # Should complete without error — shopper is never reached
            scan_id = app._run_scan(
                "https://example.com/products/test",
                n=5,
                pre_fetched_page=fake_page,
                tier="free",
            )
            assert scan_id  # got a scan_id back

    def test_paid_scan_includes_shopper(self):
        """With tier='paid', shopper checks should be present in the check list."""
        from app import checks_for_tier, _load_checks
        _, _, checks = _load_checks()
        paid = checks_for_tier("paid", checks)
        shopper = [c for c in paid if c.get("type") == "shopper"]
        assert len(shopper) > 0, "Paid tier must include shopper checks"
