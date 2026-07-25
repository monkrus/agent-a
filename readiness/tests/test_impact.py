"""Tests for impact.py — revenue impact estimation."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from impact import estimate, _extract_price, _categorize_failures, _compound_failure_rate


def _result(verdict="PASS", category="structured-data", severity="medium",
            pass_fraction=1.0, weight=5, **kw):
    r = {"verdict": verdict, "category": category, "severity_if_fail": severity,
         "pass_fraction": pass_fraction, "weight": weight, "title": "Test check"}
    r.update(kw)
    return r


# ---- price extraction -------------------------------------------------------

class TestExtractPrice:
    def test_from_ground_truth(self):
        results = [_result(category="price-extraction", ground_truth=29.99)]
        assert _extract_price(results) == 29.99

    def test_from_sample_answers(self):
        results = [_result(category="price-extraction",
                           sample_answers=["49.99", "49.99"])]
        assert _extract_price(results) == 49.99

    def test_returns_none_if_missing(self):
        results = [_result(category="structured-data")]
        assert _extract_price(results) is None


# ---- failure categorization -------------------------------------------------

class TestCategorizeFailures:
    def test_discovery_failure(self):
        results = [_result(verdict="FAIL", category="structured-data",
                           severity="critical", pass_fraction=0.0)]
        cats = _categorize_failures(results)
        assert "discovery" in cats

    def test_accuracy_failure(self):
        results = [_result(verdict="FAIL", category="price-extraction",
                           severity="critical", pass_fraction=0.6)]
        cats = _categorize_failures(results)
        assert "accuracy" in cats

    def test_interaction_failure(self):
        results = [_result(verdict="FAIL", category="agent-interaction",
                           severity="high", pass_fraction=0.0)]
        cats = _categorize_failures(results)
        assert "interaction" in cats

    def test_passing_results_ignored(self):
        results = [_result(verdict="PASS")]
        cats = _categorize_failures(results)
        assert len(cats) == 0


# ---- compound failure rate --------------------------------------------------

class TestCompoundFailureRate:
    def test_no_failures(self):
        assert _compound_failure_rate({}) == 0.0

    def test_single_failure(self):
        impact = {"discovery": {"label": "x", "severity": "critical",
                                "issues": [{"title": "t", "severity": "critical",
                                            "impact_weight": 1.0}]}}
        rate = _compound_failure_rate(impact)
        assert 0 < rate <= 1.0

    def test_more_failures_higher_rate(self):
        single = {"discovery": {"label": "x", "severity": "critical",
                                "issues": [{"title": "t", "severity": "critical",
                                            "impact_weight": 1.0}]}}
        multi = {
            "discovery": single["discovery"],
            "accuracy": {"label": "y", "severity": "high",
                         "issues": [{"title": "t2", "severity": "high",
                                     "impact_weight": 0.7}]}
        }
        assert _compound_failure_rate(multi) > _compound_failure_rate(single)


# ---- full estimate ----------------------------------------------------------

class TestEstimate:
    def test_basic_structure(self):
        results = [
            _result(verdict="FAIL", category="price-extraction",
                    severity="critical", pass_fraction=0.6,
                    ground_truth=29.99),
        ]
        est = estimate(results)
        assert "estimated_monthly_loss" in est
        assert "estimated_annual_loss" in est
        assert est["estimated_monthly_loss"]["low"] >= 0
        assert est["estimated_monthly_loss"]["high"] >= est["estimated_monthly_loss"]["low"]
        assert est["estimated_annual_loss"]["high"] > 0

    def test_all_passing_low_impact(self):
        results = [_result(verdict="PASS", pass_fraction=1.0)]
        est = estimate(results)
        assert est["agent_failure_rate"] == 0.0
        assert est["estimated_monthly_loss"]["low"] == 0

    def test_uses_provided_price(self):
        results = [_result(verdict="FAIL", category="structured-data",
                           severity="critical", pass_fraction=0.0)]
        est = estimate(results, product_price=100.0)
        assert est["product_price"] == 100.0
