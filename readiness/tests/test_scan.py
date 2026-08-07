"""Tests for scan.py — score computation, confidence band, headline."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from scan import score, confidence_band, headline, load_checks


def _result(verdict="PASS", weight=10, pass_fraction=1.0, severity="medium", **kw):
    r = {"verdict": verdict, "weight": weight, "pass_fraction": pass_fraction,
         "severity_if_fail": severity, "title": "Test check", "type": "static"}
    r.update(kw)
    return r


# ---- score ------------------------------------------------------------------

class TestScore:
    def test_all_pass(self):
        results = [_result(weight=50), _result(weight=50)]
        assert score(results) == 100.0

    def test_all_fail(self):
        results = [_result(verdict="FAIL", pass_fraction=0.0, weight=50),
                   _result(verdict="FAIL", pass_fraction=0.0, weight=50)]
        assert score(results) == 0.0

    def test_mixed(self):
        results = [_result(weight=50, pass_fraction=1.0),
                   _result(weight=50, pass_fraction=0.0)]
        assert score(results) == 50.0

    def test_unknown_excluded(self):
        results = [_result(weight=50, pass_fraction=1.0),
                   _result(verdict="UNKNOWN", weight=50, pass_fraction=None)]
        assert score(results) == 100.0

    def test_weighted(self):
        results = [_result(weight=80, pass_fraction=1.0),
                   _result(weight=20, pass_fraction=0.0)]
        assert score(results) == 80.0

    def test_empty_returns_none(self):
        assert score([]) is None

    def test_all_unknown_returns_none(self):
        results = [_result(verdict="UNKNOWN", pass_fraction=None)]
        assert score(results) is None


# ---- confidence band --------------------------------------------------------

class TestConfidenceBand:
    def test_static_only_zero_margin(self):
        results = [_result(type="static")]
        margin = confidence_band(results, n=10)
        assert margin == 0.0

    def test_shopper_has_margin(self):
        results = [_result(type="shopper", pass_fraction=0.8, weight=50)]
        margin = confidence_band(results, n=5)
        assert margin > 0

    def test_more_runs_tighter_band(self):
        r = [_result(type="shopper", pass_fraction=0.8, weight=50)]
        m5 = confidence_band(r, n=5)
        m20 = confidence_band(r, n=20)
        assert m20 < m5

    def test_none_when_no_scored_checks(self):
        results = [_result(verdict="UNKNOWN", pass_fraction=None)]
        assert confidence_band(results, n=5) is None


# ---- headline ---------------------------------------------------------------

class TestHeadline:
    def test_critical_failure(self):
        results = [_result(verdict="FAIL", severity="critical")]
        h = headline(results)
        assert "critical" in h.lower()

    def test_non_critical_failure(self):
        results = [_result(verdict="FAIL", severity="medium")]
        h = headline(results)
        assert "issue" in h.lower()

    def test_all_pass(self):
        results = [_result()]
        h = headline(results)
        assert "cleanly" in h.lower()

    def test_unknown_only(self):
        results = [_result(verdict="UNKNOWN")]
        h = headline(results)
        assert "inconclusive" in h.lower()


# ---- load_checks ------------------------------------------------------------

class TestLoadChecks:
    def test_loads_yaml(self):
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        pack, version, checks = load_checks(yaml_path)
        assert pack == "shopify-readiness"
        assert len(checks) == 26

    def test_weights_sum_to_100(self):
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        _, _, checks = load_checks(yaml_path)
        total = sum(c.get("weight", 0) for c in checks)
        assert total == 100

    def test_all_checks_have_required_fields(self):
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        _, _, checks = load_checks(yaml_path)
        for c in checks:
            assert "id" in c, f"Check missing id: {c}"
            assert "type" in c, f"Check {c['id']} missing type"
            assert "detect" in c or "task" in c, f"Check {c['id']} missing detect/task"
            assert "weight" in c, f"Check {c['id']} missing weight"
            assert "severity_if_fail" in c, f"Check {c['id']} missing severity_if_fail"

    def test_every_detect_has_scorer(self):
        """Every YAML detect key must map to a registered scorer function."""
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        _, _, checks = load_checks(yaml_path)
        from scorers import STATIC, BROWSER
        for c in checks:
            detect = c.get("detect")
            if detect is None:
                continue  # shopper checks use task, not detect
            ctype = c["type"]
            if ctype == "static":
                assert detect in STATIC, (
                    f"Check {c['id']} detect={detect!r} not wired in STATIC dict")
            elif ctype == "browser":
                assert detect in BROWSER, (
                    f"Check {c['id']} detect={detect!r} not wired in BROWSER dict")

    def test_no_duplicate_check_ids(self):
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        _, _, checks = load_checks(yaml_path)
        ids = [c["id"] for c in checks]
        assert len(ids) == len(set(ids)), f"Duplicate check IDs: {[i for i in ids if ids.count(i) > 1]}"
