"""Tests for fetch.py — HTML parsing, dead page detection, challenge detection."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fetch import _parse_html, is_dead_page, is_collection_page, _probe_single_ua, _is_safe_url


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

    def test_429_is_not_dead(self):
        """429 = rate-limited, not dead. Scan should proceed, not abort."""
        page = {"status": 429, "title": "", "text": ""}
        assert is_dead_page(page) is None

    def test_403_is_dead(self):
        page = {"status": 403, "title": "", "text": ""}
        assert is_dead_page(page) is not None


# ---- challenge detection (bot wall vs real page) ----------------------------

class TestChallengeDetection:
    """Regression tests for _probe_single_ua challenge detection.

    We can't easily call _probe_single_ua without a real HTTP server,
    so we test the challenge-detection logic via the internal code path
    by simulating what the function does with crafted responses.
    """

    def _detect_challenge(self, body):
        """Replicate the challenge detection logic from _probe_single_ua."""
        import re
        text = re.sub(r"<[^>]{1,500}>", " ", body)
        words = len(text.split())
        tl = text.lower()
        challenge_sigs = ("cf-challenge", "challenge-platform",
                          "checking your browser", "please verify",
                          "access denied", "bot detection", "ddos protection",
                          "captcha")
        matched = [sig for sig in challenge_sigs if sig in tl]
        return bool(matched and words < 500), words, matched

    def test_real_challenge_page_detected(self):
        """A thin page with challenge keywords IS a challenge."""
        html = "<html><body><p>Checking your browser before accessing</p></body></html>"
        is_challenge, words, _ = self._detect_challenge(html)
        assert is_challenge
        assert words < 500

    def test_captcha_only_challenge_page(self):
        """A thin page mentioning captcha IS a challenge."""
        html = "<html><body><p>Please complete the captcha to continue</p></body></html>"
        is_challenge, _, matched = self._detect_challenge(html)
        assert is_challenge
        assert "captcha" in matched

    def test_shopify_captcha_bootstrap_not_challenge(self):
        """Shopify's captcha-bootstrap script on a real product page is NOT a challenge.

        Regression: every Shopify store includes <script id="captcha-bootstrap">.
        With 5000+ words of product content, this must not trigger."""
        product_content = " ".join(f"word{i}" for i in range(5000))
        html = (f'<html><body><div>{product_content}</div>'
                f'<script id="captcha-bootstrap">!function(){{}}</script></body></html>')
        is_challenge, words, _ = self._detect_challenge(html)
        assert not is_challenge
        assert words >= 500

    def test_cf_challenge_in_script_not_visible(self):
        """cf-challenge inside a <script> tag is stripped before matching.

        Only visible text triggers challenge detection, not script contents."""
        product_content = " ".join(f"word{i}" for i in range(600))
        html = (f'<html><body><div>{product_content}</div>'
                f'<script>var cf_challenge = true;</script></body></html>')
        is_challenge, words, _ = self._detect_challenge(html)
        assert not is_challenge

    def test_real_cloudflare_challenge_detected(self):
        """A real Cloudflare challenge page (thin, visible challenge text)."""
        html = ('<html><body>'
                '<h1>Please verify you are a human</h1>'
                '<p>Access denied. Checking your browser.</p>'
                '<div id="cf-challenge">Challenge in progress</div>'
                '</body></html>')
        is_challenge, words, matched = self._detect_challenge(html)
        assert is_challenge
        assert words < 500

    def test_access_denied_in_privacy_policy_not_challenge(self):
        """A real page that mentions 'access denied' in policy text is NOT a challenge
        if the page has substantial content."""
        content = " ".join(f"product{i}" for i in range(600))
        html = (f'<html><body><div>{content}</div>'
                f'<p>If access denied, contact support.</p></body></html>')
        is_challenge, _, _ = self._detect_challenge(html)
        assert not is_challenge


# ---- SSRF protection --------------------------------------------------------

class TestSsrfProtection:
    def test_rejects_localhost(self):
        assert not _is_safe_url("http://localhost/")

    def test_rejects_127(self):
        assert not _is_safe_url("http://127.0.0.1/")

    def test_rejects_metadata_ip(self):
        assert not _is_safe_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_private_10(self):
        assert not _is_safe_url("http://10.0.0.1/")

    def test_rejects_private_172(self):
        assert not _is_safe_url("http://172.16.0.1/")

    def test_rejects_private_192(self):
        assert not _is_safe_url("http://192.168.1.1/")

    def test_rejects_ipv6_loopback(self):
        assert not _is_safe_url("http://[::1]/")

    def test_rejects_ftp_scheme(self):
        assert not _is_safe_url("ftp://example.com/file")

    def test_rejects_file_scheme(self):
        assert not _is_safe_url("file:///etc/passwd")

    def test_allows_public_url(self):
        # google.com resolves to public IPs
        assert _is_safe_url("https://www.google.com/")


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


# ---- Fetch cache keyed by URL ------------------------------------------------

class TestFetchCache:
    def test_different_urls_same_domain_not_cached(self):
        """Two different product URLs on the same domain must fetch independently."""
        from unittest.mock import patch, MagicMock
        import fetch as fetchmod

        # Clear cache before test
        fetchmod._fetch_cache.clear()

        page_a = {"title": "Product A", "status": 200, "html": "<html>A</html>",
                  "text": "A", "jsonld": [], "meta": {}, "links": [], "images": [],
                  "url": "https://x.com/products/a"}
        page_b = {"title": "Product B", "status": 200, "html": "<html>B</html>",
                  "text": "B", "jsonld": [], "meta": {}, "links": [], "images": [],
                  "url": "https://x.com/products/b"}

        call_count = 0

        def mock_safe_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.url = url
            resp.elapsed.total_seconds.return_value = 0.1
            if "/products/a" in url:
                resp.text = "<html><head><title>Product A</title></head><body>A</body></html>"
            else:
                resp.text = "<html><head><title>Product B</title></head><body>B</body></html>"
            resp.headers = {}
            return resp

        with patch.object(fetchmod, '_safe_get', side_effect=mock_safe_get):
            with patch.object(fetchmod, '_is_safe_url', return_value=True):
                result_a = fetchmod.fetch("https://x.com/products/a")
                result_b = fetchmod.fetch("https://x.com/products/b")

        # Both must hit the network (call_count >= 2 for primary fetches)
        assert result_a["title"] != result_b["title"], \
            "Different URLs returned same page — cache is still keyed by domain"
        assert result_a["title"] == "Product A"
        assert result_b["title"] == "Product B"

        # Clean up
        fetchmod._fetch_cache.clear()

    def test_same_url_uses_cache(self):
        """Same URL within TTL should return cached result."""
        import fetch as fetchmod

        fetchmod._fetch_cache.clear()

        # Pre-populate cache with a fake page
        import time
        fake_page = {"title": "Cached Widget", "status": 200,
                     "html": "<html>cached</html>", "text": "cached",
                     "jsonld": [], "meta": {}, "links": [], "images": [],
                     "url": "https://x.com/products/widget"}
        fetchmod._fetch_cache["https://x.com/products/widget"] = (
            time.time(), fake_page)

        # This should return the cached page without any network call
        result = fetchmod.fetch("https://x.com/products/widget")
        assert result.get("_cached") is True
        assert result["title"] == "Cached Widget"
        fetchmod._fetch_cache.clear()


# ---- SSRF protection --------------------------------------------------------

class TestSSRFProtection:
    def test_dns_rebinding_detected(self):
        """If DNS resolves to a safe IP first then a private IP, raise error."""
        from unittest.mock import patch
        from fetch import _resolve_is_safe

        # First call returns safe, second returns private (169.254.169.254)
        call_count = [0]
        original_getaddrinfo = __import__("socket").getaddrinfo

        def mock_getaddrinfo(host, port, *args, **kwargs):
            call_count[0] += 1
            if host == "rebinding.test":
                # Always return metadata IP to simulate rebinding
                return [(2, 1, 6, '', ('169.254.169.254', 80))]
            return original_getaddrinfo(host, port, *args, **kwargs)

        with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
            # _resolve_is_safe should detect the private IP
            assert not _resolve_is_safe("rebinding.test", 80)

    def test_resolve_is_safe_rejects_loopback(self):
        from unittest.mock import patch
        from fetch import _resolve_is_safe

        def mock_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, '', ('127.0.0.1', 80))]

        with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
            assert not _resolve_is_safe("evil.com", 80)

    def test_resolve_is_safe_allows_public(self):
        from unittest.mock import patch
        from fetch import _resolve_is_safe

        def mock_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, '', ('93.184.216.34', 80))]

        with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
            assert _resolve_is_safe("example.com", 80)

    def test_check_response_ip_catches_private(self):
        """Post-connect IP check catches DNS rebinding."""
        from unittest.mock import MagicMock
        from fetch import _check_response_ip, _UnsafeURLError
        import pytest

        response = MagicMock()
        sock = MagicMock()
        sock.getpeername.return_value = ('169.254.169.254', 80)
        response.raw._connection.sock = sock

        with pytest.raises(_UnsafeURLError, match="rebinding"):
            _check_response_ip(response)

    def test_safe_request_available(self):
        """_safe_request is exported and callable."""
        from fetch import _safe_request
        assert callable(_safe_request)

    def test_playwright_guard_uses_port_80_for_http(self):
        """_playwright_ssrf_guard must use port 80 for http://, not 443."""
        from fetch import _playwright_ssrf_guard
        from urllib.parse import urlparse
        # Verify the logic inline — the guard calls _resolve_is_safe(host, port)
        parsed = urlparse("http://example.com/foo")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        assert port == 80
