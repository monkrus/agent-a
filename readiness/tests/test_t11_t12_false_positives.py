"""Regression tests for T11 and T12 — false positives found scanning li-vy.com
(Nov 2026).

T11: RDY-031 reported "ACCESS BLOCKED" because the scan's own request burst
     tripped a site-wide 429. Spaced-out manual probes returned 200 for
     GPTBot/ClaudeBot/PerplexityBot while a normal browser UA got 429.
T12: RDY-033 reported a stock contradiction because availability was read
     from the first variant only (XS, sold out) while other sizes were in stock.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import fetch
import scorers
from shopper import _jsonld_availability


def _probe_result(status, challenge=False, words=800):
    return {"status": status, "readable_words": words, "challenge": challenge,
            "inconclusive": status is None}


class _FakeProber:
    """Stands in for fetch._probe_single_ua with a scripted status sequence
    per UA string. Each call pops the next status for that UA."""

    def __init__(self, script):
        self.script = {ua: list(statuses) for ua, statuses in script.items()}
        self.calls = []

    def __call__(self, url, ua, timeout):
        self.calls.append(ua)
        seq = self.script[ua]
        status = seq.pop(0) if len(seq) > 1 else seq[0]
        return _probe_result(status)


def _ua(name):
    return dict(fetch._AGENT_UAS)[name]


def _run_probe(monkeypatch, script):
    prober = _FakeProber(script)
    monkeypatch.setattr(fetch, "_probe_single_ua", prober)
    monkeypatch.setattr(fetch, "_RATE_LIMIT_BACKOFF_S", 0)
    return fetch._probe_as_agent("https://example.com/products/x", 5), prober


def _page(detail):
    return {"agent_probe_status": detail["status"], "agent_probe_detail": detail}


# ---- T11 -------------------------------------------------------------------

class TestT11RateLimitControl:
    def test_transient_sitewide_429_recovers_after_backoff(self, monkeypatch):
        """li-vy.com case: everyone 429 during burst, agents 200 after backoff."""
        script = {ua: [429, 200] for _, ua in fetch._AGENT_UAS}
        script[fetch._BROWSER_UA] = [429]
        detail, _ = _run_probe(monkeypatch, script)
        assert detail["blocked_uas"] == []
        assert set(detail["allowed_uas"]) == {n for n, _ in fetch._AGENT_UAS}
        assert detail["status"] == 200
        v, _ = scorers.static_rate_limiting(_page(detail))
        assert v == "PASS"

    def test_persistent_sitewide_429_is_unknown_not_fail(self, monkeypatch):
        script = {ua: [429] for _, ua in fetch._AGENT_UAS}
        script[fetch._BROWSER_UA] = [429]
        detail, _ = _run_probe(monkeypatch, script)
        assert detail["blocked_uas"] == []
        assert detail["indiscriminate_429"]
        v, d = scorers.static_rate_limiting(_page(detail))
        assert v == "UNKNOWN"  # UNKNOWN does not trip the access gate
        assert "normal browser" in d

    def test_agent_specific_429_still_fails(self, monkeypatch):
        """Browser gets 200 while agents get 429 → real agent rate-limiting."""
        script = {ua: [429] for _, ua in fetch._AGENT_UAS}
        script[fetch._BROWSER_UA] = [200]
        detail, prober = _run_probe(monkeypatch, script)
        assert set(detail["blocked_uas"]) == {n for n, _ in fetch._AGENT_UAS}
        assert detail["control_status"] == 200
        v, _ = scorers.static_rate_limiting(_page(detail))
        assert v == "FAIL"

    def test_403_never_triggers_control_probe(self, monkeypatch):
        script = {ua: [403] for _, ua in fetch._AGENT_UAS}
        script[fetch._BROWSER_UA] = [200]
        detail, prober = _run_probe(monkeypatch, script)
        assert fetch._BROWSER_UA not in prober.calls
        v, _ = scorers.static_rate_limiting(_page(detail))
        assert v == "FAIL"

    def test_indiscriminate_gptbot_but_other_ua_403_fails(self, monkeypatch):
        script = {ua: [429] for _, ua in fetch._AGENT_UAS}
        script[_ua("ClaudeBot")] = [403]
        script[fetch._BROWSER_UA] = [429]
        detail, _ = _run_probe(monkeypatch, script)
        assert detail["blocked_uas"] == ["ClaudeBot"]
        v, _ = scorers.static_rate_limiting(_page(detail))
        assert v == "FAIL"


# ---- T12 -------------------------------------------------------------------

# Shape copied from li-vy.com ProductGroup JSON-LD (Nov 22 2026):
# 5 sizes, first 3 OutOfStock, last 2 InStock.
_LIVY_GROUP = {
    "@type": "ProductGroup",
    "name": "BRIEF ADORN BLACK",
    "offers": {
        "@type": "AggregateOffer", "lowPrice": "85.0", "highPrice": "85.0",
        "offers": [
            {"@type": "Offer", "sku": "652068305002", "price": "85.0",
             "availability": "http://schema.org/OutOfStock"},
            {"@type": "Offer", "sku": "652068305003", "price": "85.0",
             "availability": "http://schema.org/OutOfStock"},
            {"@type": "Offer", "sku": "652068305004", "price": "85.0",
             "availability": "http://schema.org/OutOfStock"},
            {"@type": "Offer", "sku": "652068305005", "price": "85.0",
             "availability": "http://schema.org/InStock"},
            {"@type": "Offer", "sku": "652068305006", "price": "85.0",
             "availability": "http://schema.org/InStock"},
        ],
    },
    "hasVariant": [
        {"@type": "Product", "sku": "652068305002",
         "offers": {"@type": "Offer", "price": "85.0",
                    "availability": "http://schema.org/OutOfStock"}},
        {"@type": "Product", "sku": "652068305005",
         "offers": {"@type": "Offer", "price": "85.0",
                    "availability": "http://schema.org/InStock"}},
    ],
}

_LIVY_HTML = (
    "<html><body><h1>BRIEF ADORN BLACK</h1><p>$85.00</p>"
    '<button>XS<span class="sr-only">Variant sold out or unavailable</span></button>'
    '<button>S<span class="sr-only">Variant sold out or unavailable</span></button>'
    '<button>M<span class="sr-only">Variant sold out or unavailable</span></button>'
    "<button>L</button><button>XL</button>"
    "<button>Add to cart</button></body></html>"
)


class TestT12PartialStock:
    def test_any_variant_in_stock_means_in_stock(self):
        assert _jsonld_availability({"jsonld": [_LIVY_GROUP]}) == "in_stock"

    def test_all_variants_oos_means_out_of_stock(self):
        group = {"@type": "ProductGroup", "offers": {
            "@type": "AggregateOffer", "offers": [
                {"availability": "https://schema.org/OutOfStock"},
                {"availability": "https://schema.org/SoldOut"}]}}
        assert _jsonld_availability({"jsonld": [group]}) == "out_of_stock"

    def test_product_with_offer_list_later_in_stock(self):
        prod = {"@type": "Product", "offers": [
            {"availability": "https://schema.org/OutOfStock"},
            {"availability": "https://schema.org/InStock"}]}
        assert _jsonld_availability({"jsonld": [prod]}) == "in_stock"

    def test_livy_page_passes_rdy033(self):
        page = {"jsonld": [_LIVY_GROUP], "html": _LIVY_HTML, "text": ""}
        v, d = scorers.static_contradictory_availability(page)
        assert v == "PASS", d

    def test_truly_oos_product_with_atc_still_fails(self):
        prod = {"@type": "Product", "offers": {
            "availability": "https://schema.org/OutOfStock"}}
        page = {"jsonld": [prod], "html": "<p>Add to cart</p>", "text": ""}
        v, _ = scorers.static_contradictory_availability(page)
        assert v == "FAIL"


# ---- T13 -------------------------------------------------------------------

class TestT13NameWordOrder:
    """li-vy.com: JSON-LD name "BRIEF ADORN BLACK", Shopify title (and the
    agent's answer 10/10) "ADORN BLACK BRIEF" — same product, reordered."""

    _check = {"id": "RDY-008", "type": "shopper", "grade": "correctness",
              "ground_truth": "product_name", "severity_if_fail": "medium"}

    def _grade(self, answers):
        page = {"jsonld": [_LIVY_GROUP], "html": "", "text": ""}
        return scorers.grade_shopper(self._check, page, answers)

    def test_reordered_name_matches(self):
        v = self._grade(["ADORN BLACK BRIEF"] * 10)
        assert v["verdict"] == "PASS", v

    def test_different_product_still_fails(self):
        v = self._grade(["WIRE BRA ADORN BLACK"] * 10)
        assert v["verdict"] == "FAIL", v


class TestT11RetryAfter:
    """li-vy.com sent Retry-After: 60; a fixed 15s backoff retried too early."""

    def _run(self, monkeypatch, retry_after):
        slept = []
        monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))

        def prober(url, ua, timeout):
            r = _probe_result(429)
            r["retry_after"] = retry_after if ua == fetch._BROWSER_UA else None
            return r
        monkeypatch.setattr(fetch, "_probe_single_ua", prober)
        fetch._probe_as_agent("https://example.com/products/x", 5)
        return slept

    def test_honors_retry_after(self, monkeypatch):
        assert self._run(monkeypatch, 60) == [60]

    def test_caps_long_retry_after(self, monkeypatch):
        assert self._run(monkeypatch, 3600) == [fetch._RATE_LIMIT_BACKOFF_MAX_S]

    def test_default_without_header(self, monkeypatch):
        assert self._run(monkeypatch, None) == [fetch._RATE_LIMIT_BACKOFF_S]
