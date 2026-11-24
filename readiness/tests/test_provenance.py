"""T1: shopper provenance — each answer carries the page text the agent used,
and every quote is verified against what the agent was actually shown."""
import json
import pathlib
import sys
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import scorers  # noqa: E402
import shopper  # noqa: E402

TASKS = {"RDY-006": "What is the price?", "RDY-007": "Is it in stock?"}

# Shaped like the li-vy.com finding: visible labels swapped vs the real price.
LIVY_PAGE = {
    "url": "https://shop.example/products/adorn",
    "title": "ADORN BLACK BRIEF",
    "text": "ADORN BLACK BRIEF\nSale price $145.00 USD\nRegular price $86.00 USD\nAdd to cart",
    "jsonld": [{"@type": "Product", "name": "BRIEF ADORN BLACK",
                "offers": {"@type": "Offer", "price": "86.00",
                           "availability": "https://schema.org/InStock"}}],
}


# ---- parsing the model reply -------------------------------------------------

def test_parse_detailed_shape():
    raw = json.dumps({"RDY-006": {"answer": "145.00", "quote": "Sale price $145.00 USD"},
                      "RDY-007": {"answer": "in_stock", "quote": "Add to cart"}})
    out = shopper._parse_detailed(raw, TASKS)
    assert out["RDY-006"] == {"answer": "145.00", "evidence": "Sale price $145.00 USD"}
    assert out["RDY-007"]["answer"] == "in_stock"


def test_parse_legacy_flat_shape_has_empty_evidence():
    out = shopper._parse_detailed('{"RDY-006": "86.00", "RDY-007": "in_stock"}', TASKS)
    assert out["RDY-006"] == {"answer": "86.00", "evidence": ""}


def test_parse_json_wrapped_in_prose_or_fences():
    raw = 'Here you go:\n```json\n{"RDY-006": {"answer": "86", "quote": "$86.00"}}\n```'
    out = shopper._parse_detailed(raw, TASKS)
    assert out["RDY-006"]["evidence"] == "$86.00"
    assert out["RDY-007"] == {"answer": "unknown", "evidence": ""}  # missing key


def test_parse_garbage_is_unknown_not_crash():
    out = shopper._parse_detailed("sorry, I can't help", TASKS)
    assert all(v == {"answer": "unknown", "evidence": ""} for v in out.values())


def test_parse_caps_quote_length():
    raw = json.dumps({"RDY-006": {"answer": "1", "quote": "x" * 5000}})
    assert len(shopper._parse_detailed(raw, TASKS)["RDY-006"]["evidence"]) == 300


# ---- backends ------------------------------------------------------------------

def test_mock_detailed_returns_answer_and_evidence(monkeypatch):
    monkeypatch.setenv("SHOPPER", "mock")
    out = shopper.ask_batch_detailed(LIVY_PAGE, TASKS)
    assert set(out) == set(TASKS)
    for v in out.values():
        assert set(v) == {"answer", "evidence"}


def test_mock_evidence_is_real_page_line_or_empty():
    assert shopper._mock_evidence(LIVY_PAGE, "145.00") == "Sale price $145.00 USD"
    assert shopper._mock_evidence(LIVY_PAGE, "unknown") == ""
    assert shopper._mock_evidence(LIVY_PAGE, "999.99") == ""


def test_backend_exception_becomes_error_answers():
    with patch.dict(shopper._DETAILED_BACKENDS, {"mock": lambda p, t: 1 / 0}):
        out = shopper.ask_batch_detailed(LIVY_PAGE, TASKS, shopper="mock")
    assert all(v["answer"].startswith("__error__") and v["evidence"] == "" for v in out.values())


def test_anthropic_prompt_asks_for_quotes_and_parses(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    reply = json.dumps({"RDY-006": {"answer": "145.00", "quote": "Sale price $145.00 USD"},
                        "RDY-007": {"answer": "in_stock", "quote": "Add to cart"}})

    class _Block:
        type = "text"
        text = reply

    class _Msgs:
        def create(self, **kw):
            _Msgs.kw = kw
            return type("M", (), {"content": [_Block()]})()

    fake = type("A", (), {"Anthropic": lambda **k: type("C", (), {"messages": _Msgs()})()})
    with patch.dict(sys.modules, {"anthropic": fake}):
        out = shopper._anthropic_batch_detailed(LIVY_PAGE, TASKS)
    assert out["RDY-006"]["evidence"] == "Sale price $145.00 USD"
    assert "exact text from the page" in _Msgs.kw["system"]
    assert "untrusted" in _Msgs.kw["system"]          # injection guard kept
    assert "Sale price $145.00" in _Msgs.kw["messages"][0]["content"]


# ---- verification + grouping ---------------------------------------------------

def _runs(*pairs):
    return [{"answer": a, "evidence": e} for a, e in pairs]


def test_livy_case_quote_verified_in_visible_text():
    runs = _runs(*[("145.00", "Sale price $145.00 USD")] * 10)
    ev = scorers.summarize_evidence(LIVY_PAGE, runs)
    assert ev["runs"] == 10 and ev["no_quote"] == 0
    g = ev["groups"][0]
    assert g["count"] == 10 and g["answers"] == ["145.00"]
    assert g["verified"] is True and g["sources"] == ["page_text"]


def test_quote_from_structured_data_labelled():
    ev = scorers.summarize_evidence(LIVY_PAGE, _runs(("86.00", '"price": "86.00"')))
    assert ev["groups"][0]["verified"] and ev["groups"][0]["sources"] == ["structured_data"]


def test_invented_quote_is_flagged_not_verified():
    ev = scorers.summarize_evidence(LIVY_PAGE, _runs(("19.99", "Now only $19.99!")))
    g = ev["groups"][0]
    assert g["verified"] is False and g["sources"] == []


def test_matching_ignores_case_whitespace_and_quote_marks():
    ev = scorers.summarize_evidence(LIVY_PAGE, _runs(("145", '"sale   PRICE $145.00 usd"')))
    assert ev["groups"][0]["verified"]


def test_groups_sorted_by_count_and_capped():
    runs = _runs(*([("145.00", "Sale price $145.00 USD")] * 6
                   + [("86.00", "Regular price $86.00 USD")] * 3
                   + [("86", "$86.00")] + [("x", "a1")] + [("y", "b2")]))
    ev = scorers.summarize_evidence(LIVY_PAGE, runs, max_groups=3)
    assert [g["count"] for g in ev["groups"]] == [6, 3, 1]
    assert ev["groups"][0]["quote"] == "Sale price $145.00 USD"


def test_no_quote_and_errors_counted_separately():
    runs = _runs(("unknown", ""), ("unknown", ""), ("__error__: boom", ""),
                 ("145.00", "Sale price $145.00 USD"))
    ev = scorers.summarize_evidence(LIVY_PAGE, runs)
    assert ev["no_quote"] == 2 and ev["runs"] == 3 and len(ev["groups"]) == 1


def test_same_quote_different_answers_collected():
    runs = _runs(("145", "Sale price $145.00 USD"), ("145.00", "Sale price $145.00 USD"))
    assert scorers.summarize_evidence(LIVY_PAGE, runs)["groups"][0]["answers"] == ["145", "145.00"]


# ---- report rendering ------------------------------------------------------------

def _render_fail(result):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import app as appmod
    with appmod.app.test_request_context():
        tpl = appmod.app.jinja_env.get_template("partials/check_fail.html")
        return tpl.render(r=result, paid=True, impact_texts={}, inconclusive_texts={})


def _fail_result(evidence):
    return {"id": "RDY-006", "title": "AI shopper reads the correct price", "verdict": "FAIL",
            "severity_if_fail": "critical", "detail": "0/10 runs matched ground truth (86.0).",
            "pass_rate": "0/10", "ground_truth": 86.0, "sample_answers": ["145.00"],
            "evidence": evidence}


def test_report_shows_verified_quote_and_source():
    ev = scorers.summarize_evidence(LIVY_PAGE, _runs(*[("145.00", "Sale price $145.00 USD")] * 10))
    html = _render_fail(_fail_result(ev))
    assert "What the agent read on your page" in html
    assert "Sale price $145.00 USD" in html
    assert "Used in 10 of 10 visits" in html
    assert "visible page text" in html
    assert "not found on the page" not in html


def test_report_flags_unverified_quote():
    ev = scorers.summarize_evidence(LIVY_PAGE, _runs(("19.99", "Now only $19.99!")))
    assert "not found on the page" in _render_fail(_fail_result(ev))


def test_report_escapes_quote_html():
    ev = scorers.summarize_evidence(LIVY_PAGE, _runs(("1", "<script>alert(1)</script>")))
    html = _render_fail(_fail_result(ev))
    assert "<script>alert(1)</script>" not in html


def test_old_scans_without_evidence_still_render():
    r = _fail_result(None)
    del r["evidence"]
    assert "What the agent read on your page" not in _render_fail(r)
