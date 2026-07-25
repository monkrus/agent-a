"""Tests for shopper.py — mock answers and grading logic."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from shopper import _mock_answer, _jsonld_price, _jsonld_availability
import scorers


def _page(**kw):
    defaults = {"html": "", "text": "", "jsonld": [], "meta": {},
                "url": "https://example.com/products/test", "title": "Test Product"}
    defaults.update(kw)
    return defaults


def _product_page():
    return _page(
        text="Amazing Widget - $29.99 - In Stock",
        jsonld=[{
            "@type": "Product", "name": "Amazing Widget",
            "offers": {"price": "29.99", "priceCurrency": "USD",
                       "availability": "https://schema.org/InStock"}
        }],
        title="Amazing Widget"
    )


# ---- mock answer behavior ---------------------------------------------------

class TestMockAnswer:
    def test_price_extraction_returns_string(self):
        page = _product_page()
        ans = _mock_answer(page, "What is the price?")
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_availability_returns_valid(self):
        page = _product_page()
        ans = _mock_answer(page, "Is the main product in stock? Reply with only: in_stock, out_of_stock, or unknown.")
        assert ans in ("in_stock", "out_of_stock", "unknown")

    def test_product_name_returns_string(self):
        page = _product_page()
        ans = _mock_answer(page, "What is the exact name of the main product?")
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_return_window(self):
        page = _product_page()
        ans = _mock_answer(page, "How many days does the customer have to return this item?")
        assert isinstance(ans, str)

    def test_shipping(self):
        page = _product_page()
        ans = _mock_answer(page, "What does shipping cost for this product?")
        assert isinstance(ans, str)


# ---- grading ----------------------------------------------------------------

class TestGradeShopper:
    def test_correctness_all_correct(self):
        check = {"grade": "correctness", "ground_truth": "price",
                 "severity_if_fail": "critical"}
        page = _product_page()
        answers = ["29.99", "$29.99", "29.99", "29.99", "29.99"]
        r = scorers.grade_shopper(check, page, answers)
        assert r["verdict"] == "PASS"
        assert r["pass_fraction"] == 1.0

    def test_correctness_partial(self):
        check = {"grade": "correctness", "ground_truth": "price",
                 "severity_if_fail": "critical"}
        page = _product_page()
        answers = ["29.99", "39.99", "29.99", "unknown", "29.99"]
        r = scorers.grade_shopper(check, page, answers)
        assert r["verdict"] == "FAIL"  # critical needs 100%
        assert r["pass_fraction"] == 0.6

    def test_correctness_no_ground_truth(self):
        check = {"grade": "correctness", "ground_truth": "price",
                 "severity_if_fail": "medium"}
        page = _page()  # no jsonld
        answers = ["29.99"] * 5
        r = scorers.grade_shopper(check, page, answers)
        assert r["verdict"] == "UNKNOWN"

    def test_consistency_all_agree(self):
        check = {"grade": "consistency", "severity_if_fail": "medium"}
        page = _product_page()
        answers = ["30 days", "30 days", "30 days", "30 days", "30 days"]
        r = scorers.grade_shopper(check, page, answers)
        assert r["verdict"] == "PASS"
        assert r["pass_fraction"] == 1.0

    def test_consistency_disagreement(self):
        check = {"grade": "consistency", "severity_if_fail": "high"}
        page = _product_page()
        answers = ["30 days", "14 days", "30 days", "not stated", "14 days"]
        r = scorers.grade_shopper(check, page, answers)
        # 2/5 = 0.4, below 0.95 threshold for high severity
        assert r["verdict"] == "FAIL"

    def test_error_answers_excluded(self):
        check = {"grade": "correctness", "ground_truth": "price",
                 "severity_if_fail": "critical"}
        page = _product_page()
        answers = ["29.99", "__error__: timeout", "29.99", "__error__: bad", "29.99"]
        r = scorers.grade_shopper(check, page, answers)
        # 3/3 valid answers correct = 100%
        assert r["verdict"] == "PASS"
        assert r["n"] == 3

    def test_all_errors_returns_unknown(self):
        check = {"grade": "correctness", "ground_truth": "price",
                 "severity_if_fail": "critical"}
        page = _product_page()
        answers = ["__error__: x"] * 5
        r = scorers.grade_shopper(check, page, answers)
        assert r["verdict"] == "UNKNOWN"

    def test_empty_answers(self):
        check = {"grade": "consistency", "severity_if_fail": "medium"}
        page = _product_page()
        r = scorers.grade_shopper(check, page, [])
        assert r["verdict"] == "UNKNOWN"


# ---- severity thresholds ----------------------------------------------------

class TestRateVerdict:
    def test_critical_needs_100(self):
        assert scorers._rate_verdict(0.99, {"severity_if_fail": "critical"}) == "FAIL"
        assert scorers._rate_verdict(1.0, {"severity_if_fail": "critical"}) == "PASS"

    def test_high_needs_95(self):
        assert scorers._rate_verdict(0.94, {"severity_if_fail": "high"}) == "FAIL"
        assert scorers._rate_verdict(0.95, {"severity_if_fail": "high"}) == "PASS"

    def test_medium_needs_90(self):
        assert scorers._rate_verdict(0.89, {"severity_if_fail": "medium"}) == "FAIL"
        assert scorers._rate_verdict(0.90, {"severity_if_fail": "medium"}) == "PASS"

    def test_low_needs_80(self):
        assert scorers._rate_verdict(0.79, {"severity_if_fail": "low"}) == "FAIL"
        assert scorers._rate_verdict(0.80, {"severity_if_fail": "low"}) == "PASS"

    def test_none_is_unknown(self):
        assert scorers._rate_verdict(None, {"severity_if_fail": "medium"}) == "UNKNOWN"
