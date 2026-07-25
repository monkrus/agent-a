"""Tests for fetch.py — HTML parsing, dead page detection, collection detection."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fetch import _parse_html, is_dead_page, is_collection_page


# ---- HTML parsing -----------------------------------------------------------

class TestParseHtml:
    def test_extracts_title(self):
        html = "<html><head><title>My Product</title></head><body></body></html>"
        page = _parse_html(html, "https://example.com")
        assert page["title"] == "My Product"

    def test_extracts_text(self):
        html = "<html><body><h1>Widget</h1><p>Great product</p></body></html>"
        page = _parse_html(html)
        assert "Widget" in page["text"]
        assert "Great product" in page["text"]

    def test_strips_script_text(self):
        html = "<html><body><script>var x = 1;</script><p>Visible</p></body></html>"
        page = _parse_html(html)
        assert "var x" not in page["text"]
        assert "Visible" in page["text"]

    def test_extracts_jsonld(self):
        html = '''<html><head>
        <script type="application/ld+json">{"@type": "Product", "name": "Widget"}</script>
        </head></html>'''
        page = _parse_html(html)
        assert len(page["jsonld"]) == 1
        assert page["jsonld"][0]["@type"] == "Product"

    def test_extracts_meta(self):
        html = '<html><head><meta property="og:title" content="My Product"></head></html>'
        page = _parse_html(html)
        assert page["meta"].get("og:title") == "My Product"

    def test_extracts_links(self):
        html = '<html><body><a href="/products/x">Product X</a></body></html>'
        page = _parse_html(html)
        assert len(page["links"]) == 1
        assert page["links"][0] == ("/products/x", "Product X")

    def test_url_preserved(self):
        page = _parse_html("<html></html>", "https://example.com/p")
        assert page["url"] == "https://example.com/p"

    def test_malformed_html_doesnt_crash(self):
        html = "<html><body><div><p>unclosed<span>also unclosed"
        page = _parse_html(html)
        assert isinstance(page["text"], str)

    def test_multiple_jsonld_blocks(self):
        html = '''<html><head>
        <script type="application/ld+json">{"@type": "Organization"}</script>
        <script type="application/ld+json">{"@type": "Product", "name": "W"}</script>
        </head></html>'''
        page = _parse_html(html)
        assert len(page["jsonld"]) == 2


# ---- dead page detection ----------------------------------------------------

class TestIsDeadPage:
    def test_404_status(self):
        page = {"status": 404, "title": "", "text": ""}
        assert is_dead_page(page) is not None

    def test_500_status(self):
        page = {"status": 500, "title": "", "text": ""}
        assert is_dead_page(page) is not None

    def test_soft_404_title(self):
        page = {"status": 200, "title": "Page Not Found", "text": "Sorry, not found"}
        assert is_dead_page(page) is not None

    def test_empty_page(self):
        page = {"status": 200, "title": "Store", "text": "   "}
        assert is_dead_page(page) is not None

    def test_healthy_page(self):
        page = {"status": 200, "title": "Widget - Store",
                "text": "Widget description " * 20}
        assert is_dead_page(page) is None


# ---- collection page detection ----------------------------------------------

class TestIsCollectionPage:
    def test_collection_url_no_jsonld(self):
        page = {"url": "https://store.com/collections/all", "title": "All",
                "text": "", "jsonld": [], "links": [
                    ("/products/a", "A"), ("/products/b", "B")]}
        assert is_collection_page(page) is not None

    def test_product_page_with_jsonld(self):
        page = {"url": "https://store.com/products/widget", "title": "Widget",
                "text": "", "jsonld": [{"@type": "Product", "name": "W",
                                        "offers": {"price": "10"}}],
                "links": []}
        assert is_collection_page(page) is None

    def test_many_product_links_no_jsonld(self):
        links = [(f"/products/p{i}", f"Product {i}") for i in range(10)]
        page = {"url": "https://store.com/shop", "title": "Shop",
                "text": "", "jsonld": [], "links": links}
        assert is_collection_page(page) is not None
