"""Route-level regression tests: /scan and /scan-stream must agree.

Before the pipeline.py refactor, /scan-stream ran its own hand-rolled
copy of the scan logic that grouped static checks through a hardcoded
ID map and silently dropped every check outside it (RDY-032..RDY-045).
The same URL scored 80.0 through /scan-stream and 74.1 through /scan.
These tests drive both routes against an identical mocked page fetch
and assert they now produce the same result set and the same score.
"""
import json
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("SHOPPER", "mock")


def _fake_page(**overrides):
    page = {
        "url": "https://example.com/products/widget",
        "status": 200,
        "html": "<div>Widget $29.99</div>",
        "text": ("Widget is a great product, in stock and ready to ship. " * 4),
        "title": "Widget — Example Store",
        "jsonld": [{"@type": "Product", "name": "Widget",
                    "offers": {"price": "29.99",
                               "availability": "https://schema.org/InStock"}}],
        "meta": {}, "links": [], "llms_txt": None, "llms_txt_content": None,
        "robots": "User-agent: *\nAllow: /\n",
        "cart_api": True,
        "checkout_probe": {"status": 200, "html": "<form>Email: <input></form>",
                           "final_url": "https://example.com/checkout",
                           "location": None, "redirect_reason": None},
        "checkout_html": "<form>Email: <input></form>",
        "homepage_html": '<form action="/search"><input type="search"></form>',
        "sitemap_xml": "<urlset><url><loc>https://example.com/products/widget</loc></url></urlset>",
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


def _setup(monkeypatch, tmp_path, page, stub_browser=False):
    import app as appmod
    import fetch as fetchmod

    monkeypatch.setattr(appmod, "SCANS_DIR", tmp_path)
    monkeypatch.setattr(appmod, "_check_rate_limit", lambda ip: None)
    monkeypatch.setattr(fetchmod, "fetch", lambda url, **kw: dict(page))
    if stub_browser:
        # scorers.run_browser drives a real (Playwright/requests) probe
        # against page["url"] regardless of the mocked fetch — stub it so
        # paid-tier tests don't make live network calls to example.com.
        import scorers as scorersmod

        def _fast_browser(check, page):
            return {"verdict": "PASS", "detail": "stubbed for test", "pass_fraction": 1.0}

        monkeypatch.setattr(scorersmod, "run_browser", _fast_browser)
    return appmod


class TestScanRouteParity:
    def test_scan_and_scan_stream_agree_on_score_and_results(self, monkeypatch, tmp_path):
        appmod = _setup(monkeypatch, tmp_path, _fake_page())
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        assert resp.status_code == 302
        scan_id_a = resp.headers["Location"].rsplit("/", 1)[-1]
        data_a = json.loads((tmp_path / f"{scan_id_a}.json").read_text())

        resp2 = client.get(f"/scan-stream?url={url}")
        body = resp2.get_data(as_text=True)
        events = [json.loads(l[6:]) for l in body.split("\n\n") if l.startswith("data: ")]
        done = [e for e in events if e["type"] == "done"][0]
        data_b = json.loads((tmp_path / f"{done['scan_id']}.json").read_text())

        assert data_a["readiness_score"] == data_b["readiness_score"]
        assert {r["id"] for r in data_a["results"]} == {r["id"] for r in data_b["results"]}

    def test_scan_stream_runs_all_free_tier_checks(self, monkeypatch, tmp_path):
        appmod = _setup(monkeypatch, tmp_path, _fake_page())
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.get(f"/scan-stream?url={url}")
        body = resp.get_data(as_text=True)
        events = [json.loads(l[6:]) for l in body.split("\n\n") if l.startswith("data: ")]
        check_events = [e for e in events if e["type"] == "check"]
        done = [e for e in events if e["type"] == "done"][0]

        from app import checks_for_tier, _load_checks
        _, _, all_checks = _load_checks()
        free_checks = checks_for_tier("free", all_checks)

        assert {e["id"] for e in check_events} == {c["id"] for c in free_checks}
        assert done["total_checks"] == len(free_checks)
        assert check_events[-1]["progress"] == f"{len(free_checks)}/{len(free_checks)}"

    def test_scan_stream_forwards_discovery_layer(self, monkeypatch, tmp_path):
        """RDY-029/030/034-041 used to have no layer in the streamed log
        and never appeared. They must now show up under a real layer."""
        appmod = _setup(monkeypatch, tmp_path, _fake_page())
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.get(f"/scan-stream?url={url}")
        body = resp.get_data(as_text=True)
        events = [json.loads(l[6:]) for l in body.split("\n\n") if l.startswith("data: ")]
        layer_events = [e["layer"] for e in events if e["type"] == "layer"]
        assert "discovery" in layer_events

    def test_gated_scan_stores_same_result_count_as_unblocked(self, monkeypatch, tmp_path):
        """Blocked and unblocked scans must score over the same
        denominator — both must persist a result for every check."""
        blocked_page = _fake_page(
            robots="User-agent: GPTBot\nDisallow: /\n",
            agent_probe_detail={"readable_words": 500, "challenge": False,
                                "blocked_uas": ["GPTBot"], "allowed_uas": []},
        )
        appmod = _setup(monkeypatch, tmp_path, blocked_page)
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.get(f"/scan-stream?url={url}")
        body = resp.get_data(as_text=True)
        events = [json.loads(l[6:]) for l in body.split("\n\n") if l.startswith("data: ")]
        done = [e for e in events if e["type"] == "done"][0]
        data = json.loads((tmp_path / f"{done['scan_id']}.json").read_text())

        from app import checks_for_tier, _load_checks
        _, _, all_checks = _load_checks()
        free_checks = checks_for_tier("free", all_checks)

        assert len(data["results"]) == len(free_checks)
        assert data["gate"]["gate_cause"] == "robots"


class TestResultsPageTruthfulness:
    def test_no_agent_visits_claim_when_no_shopper_ran(self, monkeypatch, tmp_path):
        appmod = _setup(monkeypatch, tmp_path, _fake_page())
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"
        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        scan_id = resp.headers["Location"].rsplit("/", 1)[-1]

        r = client.get(f"/results/{scan_id}")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "AI agent visits simulated" not in html

    def test_blocked_page_has_one_check_count_not_two(self, monkeypatch, tmp_path):
        blocked_page = _fake_page(
            robots="User-agent: GPTBot\nDisallow: /\n",
            agent_probe_detail={"readable_words": 500, "challenge": False,
                                "blocked_uas": ["GPTBot"], "allowed_uas": []},
        )
        appmod = _setup(monkeypatch, tmp_path, blocked_page)
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"
        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        scan_id = resp.headers["Location"].rsplit("/", 1)[-1]

        r = client.get(f"/results/{scan_id}")
        html = r.get_data(as_text=True)
        assert "Cloudflare" not in html
        assert "Akamai" not in html

    def test_robots_blocked_page_cites_robots_not_cdn(self, monkeypatch, tmp_path):
        blocked_page = _fake_page(
            robots="User-agent: GPTBot\nDisallow: /\n",
            agent_probe_detail={"readable_words": 500, "challenge": False,
                                "blocked_uas": [], "allowed_uas": ["GPTBot"]},
        )
        appmod = _setup(monkeypatch, tmp_path, blocked_page)
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"
        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        scan_id = resp.headers["Location"].rsplit("/", 1)[-1]

        data = json.loads((tmp_path / f"{scan_id}.json").read_text())
        assert data["gate"]["gate_cause"] == "robots"

        r = client.get(f"/results/{scan_id}")
        html = r.get_data(as_text=True)
        assert "robots.txt" in html
        assert "Cloudflare" not in html and "Akamai" not in html


class TestPaidUnlock:
    """Paying $49 must actually re-run the scan with shopper + browser
    checks, not just flip a session flag over the same free payload."""

    def test_dev_mode_checkout_reruns_with_full_pack(self, monkeypatch, tmp_path):
        appmod = _setup(monkeypatch, tmp_path, _fake_page(), stub_browser=True)
        monkeypatch.setenv("DEV_MODE", "true")
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        scan_id = resp.headers["Location"].rsplit("/", 1)[-1]
        before = json.loads((tmp_path / f"{scan_id}.json").read_text())
        assert before["meta"]["tier"] == "free"
        assert len(before["results"]) < 40

        r = client.post(f"/checkout/{scan_id}", data={})
        assert r.status_code == 302

        after = json.loads((tmp_path / f"{scan_id}.json").read_text())
        assert after["meta"]["tier"] == "paid"
        assert after["meta"]["paid"] is True
        assert len(after["results"]) == 40

    def test_unlock_is_idempotent(self, monkeypatch, tmp_path):
        """A page refresh or repeated payment webhook after unlock must
        not re-run (and re-spend on) the paid scan."""
        appmod = _setup(monkeypatch, tmp_path, _fake_page(), stub_browser=True)
        monkeypatch.setenv("DEV_MODE", "true")
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        scan_id = resp.headers["Location"].rsplit("/", 1)[-1]
        client.post(f"/checkout/{scan_id}", data={})
        first = json.loads((tmp_path / f"{scan_id}.json").read_text())

        result = appmod._unlock_paid_scan(scan_id)
        assert result["meta"]["timestamp"] == first["meta"]["timestamp"]

    def test_results_page_reflects_persistent_paid_state_without_session(self, monkeypatch, tmp_path):
        """meta.paid (written to disk) must unlock the report even without
        the session cookie that set it — the whole point of writing it."""
        appmod = _setup(monkeypatch, tmp_path, _fake_page(), stub_browser=True)
        monkeypatch.setenv("DEV_MODE", "true")
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
        client = appmod.app.test_client()
        url = "https://example.com/products/widget"

        resp = client.post("/scan", data={"url": url}, follow_redirects=False)
        scan_id = resp.headers["Location"].rsplit("/", 1)[-1]
        client.post(f"/checkout/{scan_id}", data={})

        # Fresh client == fresh session, no paid_<scan_id> cookie.
        fresh_client = appmod.app.test_client()
        r = fresh_client.get(f"/results/{scan_id}")
        assert r.status_code == 200
        assert "Deep Agent Audit — Full Results" in r.get_data(as_text=True)
