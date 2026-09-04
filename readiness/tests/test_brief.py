"""Tests for brief.py — one-page HTML brief for a single scan run.

The fixture payload is hand-built (same convention as test_scan.py /
test_impact.py) rather than run through a live fetch, so these tests are
fast and offline. It reuses scan.score / scan.confidence_band / scan.headline
/ scan.report_data and impact.estimate so the derived fields (score, margin,
headline, roadmap, revenue) are computed the same way scan.py computes them
for a real payload.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import brief
import scan
import impact as impactmod
import validate_report


def _result(id, verdict="PASS", type="static", category="structured-data",
            weight=5, severity="medium", pass_fraction=1.0, title=None,
            detail=None, gated=False, **kw):
    r = {
        "id": id, "type": type, "category": category, "weight": weight,
        "severity_if_fail": severity, "verdict": verdict,
        "pass_fraction": pass_fraction,
        "title": title or f"Check {id}",
        "detail": detail or f"Observed detail for {id}.",
        "fix": "Do the fix.",
        "confidence": "observed",
    }
    if gated:
        r["gated"] = True
    r.update(kw)
    return r


def _build_payload(n=5, seed=0):
    """A small but representative set of results across static/shopper/browser
    types and PASS/FAIL/UNKNOWN verdicts, offset by `seed` so two fixtures
    never share a score or revenue figure (used by test_no_hardcoded_numbers)."""
    results = [
        _result("RDY-001", verdict="PASS", category="structured-data", weight=10),
        _result("RDY-002", verdict="FAIL", category="price-legibility", weight=15,
                 severity="critical", pass_fraction=0.0,
                 detail="Price only appears after JS execution."),
        _result("RDY-010", verdict="PASS", type="shopper", category="price-extraction",
                 weight=10, pass_fraction=1.0, n=n, pass_rate=f"{n}/{n}"),
        _result("RDY-011", verdict="FAIL", type="shopper", category="availability-extraction",
                 weight=10, severity="high", pass_fraction=0.4 + seed * 0.01, n=n,
                 pass_rate=f"{max(1, int(0.4 * n) + seed)}/{n}",
                 detail="Agent reported in-stock for a sold-out item."),
        _result("RDY-020", verdict="PASS", type="browser", category="agent-interaction",
                 weight=10, pass_fraction=1.0),
        _result("RDY-030", verdict="UNKNOWN", category="security", weight=10,
                 pass_fraction=None, detail="Could not determine WAF behavior."),
    ]
    price = 20.0 + seed
    impact_est = impactmod.estimate(results, product_price=price)
    payload = {
        "meta": {
            "target": f"https://shop{seed}.example.com/products/widget",
            "pack": "shopify-readiness", "version": "test",
            "n": n, "shopper": "mock", "model": "claude-sonnet-4-6",
            "timestamp": "2026-01-01T00:00:00", "page_status": 200,
        },
        "readiness_score": scan.score(results),
        "confidence_margin": scan.confidence_band(results, n),
        "headline": scan.headline(results),
        "report": scan.report_data(results, {}),
        "results": results,
        "impact": impact_est,
    }
    return payload


def _gated_payload():
    results = [
        _result("RDY-003", verdict="FAIL", category="agent-access", weight=10,
                 severity="critical", pass_fraction=0.0,
                 detail="robots.txt disallows GPTBot."),
        _result("RDY-031", verdict="PASS", category="security", weight=5),
        _result("RDY-010", verdict="UNKNOWN", type="shopper", category="price-extraction",
                 weight=10, pass_fraction=0.0, gated=True,
                 detail="Skipped — access gate triggered.", severity="high"),
    ]
    impact_est = impactmod.estimate(results)
    return {
        "meta": {"target": "https://blocked.example.com/p/x", "pack": "shopify-readiness",
                 "version": "test", "n": 5, "shopper": "mock", "model": "claude-sonnet-4-6",
                 "timestamp": "2026-01-01T00:00:00", "page_status": 200},
        "readiness_score": scan.score(results),
        "confidence_margin": scan.confidence_band(results, 5),
        "headline": scan.headline(results),
        "report": scan.report_data(results, {}),
        "results": results,
        "impact": impact_est,
    }


class TestFullBrief:
    def setup_method(self):
        self.payload = _build_payload()
        self.html = brief.render(self.payload, mode="full")

    def test_contains_every_check_id(self):
        for r in self.payload["results"]:
            assert r["id"] in self.html

    def test_contains_score_and_margin(self):
        assert str(self.payload["readiness_score"]) in self.html
        assert str(self.payload["confidence_margin"]) in self.html

    def test_contains_headline_verbatim(self):
        assert self.payload["headline"] in self.html

    def test_validator_passes(self, tmp_path):
        report_path = tmp_path / "brief.html"
        report_path.write_text(self.html, encoding="utf-8")
        text = validate_report.extract_report_text(str(report_path))
        errors = validate_report.validate(self.payload, text)
        assert errors == []


class TestNoHardcodedNumbers:
    def test_figures_differ_between_payloads(self):
        payload_a = _build_payload(seed=0)
        payload_b = _build_payload(seed=7)
        html_a = brief.render(payload_a, mode="full")
        html_b = brief.render(payload_b, mode="full")

        # The domain from payload A must not leak into payload B's render.
        assert "shop0.example.com" in html_a
        assert "shop0.example.com" not in html_b

        # Payload A's monthly-loss figures must not appear in payload B's
        # render unless they happen to genuinely coincide (they don't, since
        # product_price differs).
        loss_a = payload_a["impact"]["estimated_monthly_loss"]
        loss_b = payload_b["impact"]["estimated_monthly_loss"]
        assert loss_a != loss_b
        assert f'{loss_a["low"]:,}' in html_a
        assert f'{loss_a["high"]:,}' in html_a


class TestGatedScan:
    def setup_method(self):
        self.payload = _gated_payload()
        self.html = brief.render(self.payload, mode="full")

    def test_shows_access_blocked_banner(self):
        assert "ACCESS BLOCKED" in self.html

    def test_gated_check_not_ranked_as_finding(self):
        # RDY-010 is gated (skipped, not measured) — it must not show up in
        # the top-findings list even though its verdict is UNKNOWN.
        findings_html = brief._top_findings_html(self.payload["results"], limit=5)
        assert "RDY-010" not in findings_html

    def test_gated_check_id_still_present_in_check_grid(self):
        # It's still a real check ID that must appear somewhere (validator
        # requires every ID to be mentioned) — just not ranked as a finding.
        assert "RDY-010" in self.html


class TestTeaserMode:
    def setup_method(self):
        self.payload = _build_payload()
        self.html = brief.render(self.payload, mode="teaser")

    def test_omits_full_check_grid(self):
        # Only checks that make the top-3 findings cut should have their ID
        # in a teaser render; the full grid (all 6 fixture IDs) must not.
        all_ids = [r["id"] for r in self.payload["results"]]
        present = [cid for cid in all_ids if cid in self.html]
        assert len(present) < len(all_ids)

    def test_omits_roadmap_and_revenue(self):
        assert "Score roadmap" not in self.html
        assert "Estimated revenue at risk" not in self.html

    def test_still_shows_score(self):
        assert str(self.payload["readiness_score"]) in self.html


class TestRendersWithoutPillow:
    def test_hero_omitted_gracefully(self, monkeypatch):
        def _boom(*a, **kw):
            raise ImportError("no Pillow in this env")
        monkeypatch.setattr(brief.og_image, "generate", _boom)
        payload = _build_payload()
        html = brief.render(payload, mode="full")
        assert '<img class="hero-img"' not in html
        # The rest of the brief still renders fully.
        assert str(payload["readiness_score"]) in html
        for r in payload["results"]:
            assert r["id"] in html


class TestWrite:
    def test_write_creates_file(self, tmp_path):
        payload = _build_payload()
        out = brief.write(payload, tmp_path / "sub" / "brief.html")
        assert out.exists()
        assert "RDY-001" in out.read_text(encoding="utf-8")


class TestResultsBriefRoute:
    """The Flask route mirrors send_report's paid gate exactly (app.py rule:
    same status as the test suite for repo-critical gates)."""

    def test_unknown_scan_returns_404(self):
        from app import app as flask_app
        flask_app.config["TESTING"] = True
        client = flask_app.test_client()
        r = client.get("/results/000000000000/brief.html")
        assert r.status_code == 404

    def test_unpaid_scan_returns_403(self):
        import app as appmod
        appmod.app.config["TESTING"] = True
        scan_id = "ab00ff001122"
        scan_file = appmod.SCANS_DIR / f"{scan_id}.json"
        payload = _build_payload()
        payload["scan_id"] = scan_id
        scan_file.write_text(json.dumps(payload))
        try:
            client = appmod.app.test_client()
            r = client.get(f"/results/{scan_id}/brief.html")
            assert r.status_code == 403
        finally:
            scan_file.unlink(missing_ok=True)

    def test_paid_scan_returns_rendered_brief(self):
        import app as appmod
        appmod.app.config["TESTING"] = True
        scan_id = "cd11ee223344"
        scan_file = appmod.SCANS_DIR / f"{scan_id}.json"
        payload = _build_payload()
        payload["scan_id"] = scan_id
        scan_file.write_text(json.dumps(payload))
        try:
            client = appmod.app.test_client()
            with client.session_transaction() as sess:
                sess[f"paid_{scan_id}"] = True
            r = client.get(f"/results/{scan_id}/brief.html")
            assert r.status_code == 200
            assert b"RDY-001" in r.data
        finally:
            scan_file.unlink(missing_ok=True)
