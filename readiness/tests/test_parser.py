"""Regression tests for JSON-LD parser (_jsonld_offers).

Covers the cases that broke before the parser fix:
- ProductGroup with hasVariant[] (SKIMS)
- @graph containers
- @type as array (e.g. ["Product", "Thing"])
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from shopper import _jsonld_offers, _jsonld_price, _jsonld_availability


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def test_skims_productgroup():
    """SKIMS uses ProductGroup with 35 hasVariant Products."""
    jsonld = json.loads((FIXTURES / "skims-productgroup.json").read_text())
    page = {"jsonld": jsonld}
    obj, off = _jsonld_offers(page)

    assert obj is not None, "Parser should find a Product from ProductGroup"
    assert obj.get("@type") == "Product", f"Merged type should be Product, got {obj.get('@type')}"
    assert obj.get("name"), "Should have a product name"
    assert off is not None, "Should extract an Offer"
    assert off.get("price") is not None, "Offer should have a price"
    assert off.get("priceCurrency") == "USD"
    assert "schema.org" in str(off.get("availability", "")).lower()

    price = _jsonld_price(page)
    assert price == 64.0, f"SKIMS bra price should be 64.0, got {price}"

    avail = _jsonld_availability(page)
    assert avail == "in_stock", f"Should be in_stock, got {avail}"


def test_graph_container():
    """@graph wrapping a Product should be unwrapped."""
    page = {"jsonld": [{"@graph": [
        {"@type": "Organization", "name": "TestCo"},
        {"@type": "Product", "name": "Widget",
         "offers": {"@type": "Offer", "price": "19.99",
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock"}},
    ]}]}
    obj, off = _jsonld_offers(page)
    assert obj is not None
    assert obj["name"] == "Widget"
    assert _jsonld_price(page) == 19.99


def test_type_as_array():
    """@type given as ["Product", "Thing"] should still match."""
    page = {"jsonld": [
        {"@type": ["Product", "Thing"], "name": "Gadget",
         "offers": {"@type": "Offer", "price": "42.00",
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock"}},
    ]}
    obj, off = _jsonld_offers(page)
    assert obj is not None
    assert obj["name"] == "Gadget"
    assert _jsonld_price(page) == 42.0


def test_offers_as_array():
    """offers given as a list should use the first Offer."""
    page = {"jsonld": [
        {"@type": "Product", "name": "Multi",
         "offers": [
             {"@type": "Offer", "price": "29.99", "priceCurrency": "USD",
              "availability": "https://schema.org/InStock"},
             {"@type": "Offer", "price": "39.99", "priceCurrency": "USD"},
         ]},
    ]}
    obj, off = _jsonld_offers(page)
    assert off["price"] == "29.99"
    assert _jsonld_price(page) == 29.99


def test_no_product():
    """Pages with no Product/ProductGroup should return None."""
    page = {"jsonld": [{"@type": "Organization", "name": "Corp"}]}
    obj, off = _jsonld_offers(page)
    assert obj is None
    assert off is None


def test_empty_jsonld():
    """Empty or missing jsonld should not crash."""
    assert _jsonld_offers({"jsonld": []}) == (None, None)
    assert _jsonld_offers({}) == (None, None)


if __name__ == "__main__":
    tests = [f for f in dir() if f.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            globals()[t]()
            passed += 1
            print(f"  PASS  {t}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
