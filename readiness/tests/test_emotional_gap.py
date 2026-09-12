"""Tests for emotional_gap.py and image extraction in fetch.py."""
import sys
import pathlib
import os

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


# ---- fetch.py image extraction -----------------------------------------------

class TestImageExtraction:
    def test_og_image_extracted(self):
        from fetch import _parse_html
        html = '<meta property="og:image" content="https://example.com/hero.jpg"><p>Hello</p>'
        page = _parse_html(html, "https://example.com/product")
        assert "images" in page
        assert "https://example.com/hero.jpg" in page["images"]

    def test_img_tags_extracted(self):
        from fetch import _parse_html
        html = '<img src="https://cdn.example.com/a.jpg"><img src="/b.png"><p>Text</p>'
        page = _parse_html(html, "https://example.com/product")
        assert len(page["images"]) >= 2
        assert "https://cdn.example.com/a.jpg" in page["images"]
        # Relative URL should be made absolute
        assert any("b.png" in img for img in page["images"])

    def test_jsonld_image_extracted(self):
        from fetch import _parse_html
        html = '''<script type="application/ld+json">
        {"@type": "Product", "name": "Test", "image": "https://cdn.example.com/jsonld.jpg",
         "offers": {"price": "29.99"}}
        </script><p>Product</p>'''
        page = _parse_html(html, "https://example.com/product")
        assert "https://cdn.example.com/jsonld.jpg" in page["images"]

    def test_jsonld_image_array(self):
        from fetch import _parse_html
        html = '''<script type="application/ld+json">
        {"@type": "Product", "name": "Test",
         "image": ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg"],
         "offers": {"price": "29.99"}}
        </script>'''
        page = _parse_html(html, "https://example.com/product")
        assert "https://cdn.example.com/1.jpg" in page["images"]
        assert "https://cdn.example.com/2.jpg" in page["images"]

    def test_deduplication(self):
        from fetch import _parse_html
        html = '''<meta property="og:image" content="https://example.com/same.jpg">
        <img src="https://example.com/same.jpg"><p>Text</p>'''
        page = _parse_html(html, "https://example.com/product")
        count = page["images"].count("https://example.com/same.jpg")
        assert count == 1

    def test_max_five_images(self):
        from fetch import _parse_html
        imgs = "".join(f'<img src="https://example.com/{i}.jpg">' for i in range(10))
        page = _parse_html(f"<div>{imgs}</div>", "https://example.com/product")
        assert len(page["images"]) <= 5

    def test_data_uri_excluded(self):
        from fetch import _parse_html
        html = '<img src="data:image/png;base64,abc123"><img src="https://example.com/real.jpg">'
        page = _parse_html(html, "https://example.com/product")
        assert not any(img.startswith("data:") for img in page["images"])
        assert "https://example.com/real.jpg" in page["images"]

    def test_img_in_script_not_extracted(self):
        from fetch import _parse_html
        html = '<script><img src="https://example.com/fake.jpg"></script><p>Text</p>'
        page = _parse_html(html, "https://example.com/product")
        assert "https://example.com/fake.jpg" not in page["images"]

    def test_no_images_empty_list(self):
        from fetch import _parse_html
        page = _parse_html("<p>No images here</p>", "https://example.com/product")
        assert page["images"] == []

    def test_data_src_extracted(self):
        from fetch import _parse_html
        html = '<img data-src="https://cdn.example.com/lazy.jpg"><p>Text</p>'
        page = _parse_html(html, "https://example.com/product")
        assert "https://cdn.example.com/lazy.jpg" in page["images"]


# ---- emotional_gap.py --------------------------------------------------------

class TestCategoryDetection:
    def test_jsonld_category(self):
        from emotional_gap import _detect_category
        page = {"jsonld": [{"@type": "Product", "category": "Lingerie"}],
                "meta": {}, "title": "", "text": ""}
        cat, weight = _detect_category(page)
        assert cat == "lingerie"
        assert weight == 9

    def test_meta_category(self):
        from emotional_gap import _detect_category
        page = {"jsonld": [], "meta": {"product:category": "Electronics"},
                "title": "", "text": ""}
        cat, weight = _detect_category(page)
        assert cat == "electronics"
        assert weight == 3

    def test_text_fallback(self):
        from emotional_gap import _detect_category
        page = {"jsonld": [], "meta": {},
                "title": "Beautiful Swimwear Collection",
                "text": "Shop our latest swimwear designs"}
        cat, weight = _detect_category(page)
        assert cat == "swimwear"
        assert weight == 9

    def test_default_category(self):
        from emotional_gap import _detect_category
        page = {"jsonld": [], "meta": {}, "title": "Product", "text": "A thing"}
        cat, weight = _detect_category(page)
        assert cat == "general"
        assert weight == 5


class TestEmotionalGapNoImages:
    def test_no_images_returns_none(self):
        from emotional_gap import analyze_emotional_gap
        page = {"images": [], "jsonld": [], "meta": {}, "title": "", "text": ""}
        result = analyze_emotional_gap(page)
        assert result["gap_score"] is None
        assert "No product images" in result["detail"]


class TestMockFallback:
    """Ensure SHOPPER=mock uses keyword check, not vision API."""

    def test_mock_mode_uses_keywords(self):
        import scorers
        os.environ["SHOPPER"] = "mock"
        html = """<div>
            <p>Made from luxurious silk and French lace blend.</p>
            <p>Designed for everyday comfort with a flattering fit.</p>
            <p>True to size — see our size chart for measurements.</p>
            <p>This is a longer product description that provides enough detail
               for an AI shopping agent to understand what the product is about
               and recommend it to customers looking for quality items.</p>
        </div>"""
        page = {"html": html, "text": "", "jsonld": [], "meta": {},
                "links": [], "robots": None, "llms_txt": None,
                "llms_txt_content": None,
                "images": ["https://example.com/photo.jpg"]}
        v, d = scorers.static_copy_richness(page)
        assert v == "PASS"
        # Should mention dimensions (keyword check), not emotional gap
        assert "dimension" in d.lower() or "4" in d

    def test_mock_mode_no_images_still_works(self):
        import scorers
        os.environ["SHOPPER"] = "mock"
        html = "<h1>Black Bra</h1><span>$98.00</span>"
        page = {"html": html, "text": "", "jsonld": [], "meta": {},
                "links": [], "robots": None, "llms_txt": None,
                "llms_txt_content": None, "images": []}
        v, d = scorers.static_copy_richness(page)
        assert v == "FAIL"


class TestKeywordCopyRichness:
    """Direct tests for the keyword fallback (unchanged behavior)."""

    def test_pass_all_dimensions(self):
        import scorers
        html = """<div>
            <p>Made from luxurious silk and French lace blend.</p>
            <p>Designed for everyday comfort with a flattering fit.</p>
            <p>True to size — see our size chart for measurements.</p>
            <p>This is a longer product description that provides enough detail
               for an AI shopping agent to understand what the product is about
               and recommend it to customers looking for quality items.</p>
        </div>"""
        v, d = scorers._keyword_copy_richness(
            {"html": html, "text": "", "jsonld": [], "meta": {}, "links": []})
        assert v == "PASS"

    def test_fail_thin_copy(self):
        import scorers
        html = "<h1>Black Bra</h1><span>$98.00</span><button>Add to Cart</button>"
        v, d = scorers._keyword_copy_richness(
            {"html": html, "text": "", "jsonld": [], "meta": {}, "links": []})
        assert v == "FAIL"
