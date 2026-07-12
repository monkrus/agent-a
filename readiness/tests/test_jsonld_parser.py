"""
Regression tests for JSON-LD product extraction.

Covers every shape _jsonld_offers() must handle:
1. Top-level Product
2. ProductGroup with hasVariant[] of Product
3. @graph containers
4. Top-level arrays of JSON-LD blocks
5. @type given as an array
6. Negative: Organization/BreadcrumbList only
7. Real-world SKIMS fixture (ProductGroup pattern)
"""
import json
import pathlib
import sys

import pytest

# Ensure readiness/ is importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from shopper import _jsonld_offers, _jsonld_price, _jsonld_availability


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _page(jsonld):
    """Build a minimal page dict from JSON-LD objects."""
    return {"jsonld": jsonld, "meta": {}}


# 1. Top-level Product
FIXTURE_TOP_LEVEL_PRODUCT = _page([
    {"@type": "Product", "name": "Classic Widget",
     "image": "widget.jpg", "brand": {"@type": "Brand", "name": "Acme"},
     "description": "A widget",
     "offers": {"@type": "Offer", "price": "29.99",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock"}}
])

# 2. ProductGroup with hasVariant[]
FIXTURE_PRODUCT_GROUP = _page([
    {"@type": "Organization", "name": "Corp"},
    {"@type": "BreadcrumbList", "itemListElement": []},
    {"@type": "ProductGroup",
     "name": "Multi-Size Shirt",
     "brand": {"@type": "Brand", "name": "BrandCo"},
     "description": "A shirt in many sizes",
     "image": ["shirt-s.jpg", "shirt-m.jpg"],
     "hasVariant": [
         {"@type": "Product", "name": "Shirt S",
          "offers": {"@type": "Offer", "price": "40",
                     "priceCurrency": "USD",
                     "availability": "https://schema.org/InStock"}},
         {"@type": "Product", "name": "Shirt M",
          "offers": {"@type": "Offer", "price": "40",
                     "priceCurrency": "USD",
                     "availability": "https://schema.org/InStock"}},
     ]}
])

# 3. @graph container
FIXTURE_GRAPH = _page([
    {"@graph": [
        {"@type": "WebSite", "name": "Store"},
        {"@type": "Product", "name": "Graph Widget",
         "offers": {"price": "15.00", "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock"}},
    ]}
])

# 4. @type as array
FIXTURE_TYPE_ARRAY = _page([
    {"@type": ["Product", "IndividualProduct"],
     "name": "Typed Widget",
     "offers": {"price": "7.50"}}
])

# 5. Negative: no product at all
FIXTURE_NEGATIVE = _page([
    {"@type": "Organization", "name": "Corp"},
    {"@type": "BreadcrumbList", "itemListElement": []},
    {"@type": "WebSite", "name": "Store"},
])

# 6. ProductGroup without typed variants (group has its own offers)
FIXTURE_GROUP_OWN_OFFERS = _page([
    {"@type": "ProductGroup",
     "name": "Bundle",
     "offers": {"price": "99.00", "priceCurrency": "USD",
                "availability": "https://schema.org/InStock"}}
])

# 7. Real-world SKIMS fixture
FIXTURE_SKIMS = _page([
    {"@type": "Organization", "name": "SKIMS",
     "url": "https://skims.com/products/...",
     "logo": "https://cdn.shopify.com/..."},
    {"@type": "BreadcrumbList",
     "itemListElement": [
         {"@type": "ListItem", "position": 1, "name": "Home"},
         {"@type": "ListItem", "position": 2, "name": "Bras"},
         {"@type": "ListItem", "position": 3, "name": "Push-Up Bras"},
     ]},
    {"@type": "ProductGroup",
     "brand": {"@type": "Brand", "name": "SKIMS"},
     "description": "Our viral solution, reimagined in the softest, premium natural cotton.",
     "image": ["https://cdn.shopify.com/skims-bra-1.webp"],
     "name": "EVERYDAY COTTON ULTIMATE TEARDROP PUSH-UP BRA",
     "hasVariant": [
         {"@type": "Product",
          "name": "EVERYDAY COTTON ULTIMATE TEARDROP PUSH-UP BRA | SIENNA HEATHER | 30 A",
          "offers": {"@type": "Offer", "price": "64",
                     "priceCurrency": "USD",
                     "availability": "https://schema.org/InStock"}},
         {"@type": "Product",
          "name": "EVERYDAY COTTON ULTIMATE TEARDROP PUSH-UP BRA | SIENNA HEATHER | 32 B",
          "offers": {"@type": "Offer", "price": "64",
                     "priceCurrency": "USD",
                     "availability": "https://schema.org/InStock"}},
     ]}
])

# 8. Product inside a ProductGroup that also has a separate top-level Product
# (top-level Product should take priority)
FIXTURE_PRODUCT_PLUS_GROUP = _page([
    {"@type": "Product", "name": "Main Product",
     "offers": {"price": "50", "priceCurrency": "USD"}},
    {"@type": "ProductGroup", "name": "Group",
     "hasVariant": [
         {"@type": "Product", "name": "Variant A",
          "offers": {"price": "30"}}
     ]}
])

# 9. @graph containing a ProductGroup
FIXTURE_GRAPH_WITH_GROUP = _page([
    {"@graph": [
        {"@type": "WebSite", "name": "Store"},
        {"@type": "ProductGroup", "name": "Graphed Group",
         "description": "Desc", "image": "img.jpg",
         "brand": {"@type": "Brand", "name": "B"},
         "hasVariant": [
             {"@type": "Product", "name": "V1",
              "offers": {"price": "20", "priceCurrency": "USD",
                         "availability": "https://schema.org/InStock"}}
         ]}
    ]}
])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTopLevelProduct:
    def test_finds_product(self):
        obj, off = _jsonld_offers(FIXTURE_TOP_LEVEL_PRODUCT)
        assert obj is not None
        assert obj["name"] == "Classic Widget"

    def test_extracts_offer(self):
        _, off = _jsonld_offers(FIXTURE_TOP_LEVEL_PRODUCT)
        assert off is not None
        assert off["price"] == "29.99"

    def test_price(self):
        assert _jsonld_price(FIXTURE_TOP_LEVEL_PRODUCT) == 29.99

    def test_availability(self):
        assert _jsonld_availability(FIXTURE_TOP_LEVEL_PRODUCT) == "in_stock"


class TestProductGroup:
    def test_finds_product_group(self):
        obj, off = _jsonld_offers(FIXTURE_PRODUCT_GROUP)
        assert obj is not None

    def test_merges_group_fields(self):
        obj, _ = _jsonld_offers(FIXTURE_PRODUCT_GROUP)
        assert obj["name"] == "Multi-Size Shirt"
        assert obj["description"] == "A shirt in many sizes"
        assert obj["brand"]["name"] == "BrandCo"

    def test_uses_variant_offers(self):
        _, off = _jsonld_offers(FIXTURE_PRODUCT_GROUP)
        assert off is not None
        assert off["price"] == "40"

    def test_price(self):
        assert _jsonld_price(FIXTURE_PRODUCT_GROUP) == 40.0

    def test_availability(self):
        assert _jsonld_availability(FIXTURE_PRODUCT_GROUP) == "in_stock"

    def test_hasVariant_stripped(self):
        obj, _ = _jsonld_offers(FIXTURE_PRODUCT_GROUP)
        assert "hasVariant" not in obj

    def test_type_is_product(self):
        obj, _ = _jsonld_offers(FIXTURE_PRODUCT_GROUP)
        assert obj["@type"] == "Product"


class TestGraphContainer:
    def test_finds_product_in_graph(self):
        obj, off = _jsonld_offers(FIXTURE_GRAPH)
        assert obj is not None
        assert obj["name"] == "Graph Widget"

    def test_price(self):
        assert _jsonld_price(FIXTURE_GRAPH) == 15.0


class TestTypeArray:
    def test_finds_product_with_type_array(self):
        obj, off = _jsonld_offers(FIXTURE_TYPE_ARRAY)
        assert obj is not None
        assert obj["name"] == "Typed Widget"

    def test_price(self):
        assert _jsonld_price(FIXTURE_TYPE_ARRAY) == 7.5


class TestNegative:
    def test_no_product_returns_none(self):
        obj, off = _jsonld_offers(FIXTURE_NEGATIVE)
        assert obj is None
        assert off is None

    def test_price_is_none(self):
        assert _jsonld_price(FIXTURE_NEGATIVE) is None

    def test_availability_is_none(self):
        assert _jsonld_availability(FIXTURE_NEGATIVE) is None


class TestGroupOwnOffers:
    def test_group_with_own_offers(self):
        obj, off = _jsonld_offers(FIXTURE_GROUP_OWN_OFFERS)
        assert obj is not None
        assert off is not None
        assert off["price"] == "99.00"


class TestSkimsFixture:
    """Real-world SKIMS pattern: ProductGroup + hasVariant[] of Product."""
    def test_finds_product_data(self):
        obj, off = _jsonld_offers(FIXTURE_SKIMS)
        assert obj is not None

    def test_name_from_group(self):
        obj, _ = _jsonld_offers(FIXTURE_SKIMS)
        assert "PUSH-UP BRA" in obj["name"]

    def test_description_from_group(self):
        obj, _ = _jsonld_offers(FIXTURE_SKIMS)
        assert "viral solution" in obj["description"]

    def test_brand_from_group(self):
        obj, _ = _jsonld_offers(FIXTURE_SKIMS)
        assert obj["brand"]["name"] == "SKIMS"

    def test_price_from_variant(self):
        assert _jsonld_price(FIXTURE_SKIMS) == 64.0

    def test_availability_from_variant(self):
        assert _jsonld_availability(FIXTURE_SKIMS) == "in_stock"


class TestProductTakesPriorityOverGroup:
    def test_direct_product_wins(self):
        obj, _ = _jsonld_offers(FIXTURE_PRODUCT_PLUS_GROUP)
        assert obj["name"] == "Main Product"

    def test_price_from_direct(self):
        assert _jsonld_price(FIXTURE_PRODUCT_PLUS_GROUP) == 50.0


class TestGraphWithGroup:
    def test_finds_group_in_graph(self):
        obj, off = _jsonld_offers(FIXTURE_GRAPH_WITH_GROUP)
        assert obj is not None
        assert obj["name"] == "Graphed Group"
        assert off["price"] == "20"
