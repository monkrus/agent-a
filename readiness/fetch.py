#!/usr/bin/env python3
"""
fetch.py — the readiness scanner's "adapter".

In the agent-audit track an adapter speaks to an agent. Here it speaks to a
SITE: given a URL (or a local HTML file for offline tests), return a normalized
`page` dict that both the static probes and the simulated shopper consume.

    page = {
      "url", "status", "html", "text",        # raw + stripped text
      "jsonld": [ ...parsed objects... ],      # all application/ld+json blocks
      "meta": { "og:title", "product:price:amount", ... },
      "title",
      "llms_txt": bool, "robots": str|None,    # only populated for real URLs
    }

Network note: JS-only sites (price rendered client-side) will look "empty" to
this fetcher — which is the correct signal, since most agents/crawlers also do
not run JS. For JS-heavy targets, point `fetch_rendered` at a rendering backend
(ListingIQ already uses Apify; wire that in clients work, not here).
"""
from __future__ import annotations
import json
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin


# ---- Per-domain fetch cache (prevents rate-limit garbage on rapid rescans) ---
_fetch_cache: dict[str, tuple[float, dict]] = {}  # domain -> (timestamp, page)
CACHE_TTL = 120  # seconds


# ---- minimal HTML -> text + meta + jsonld --------------------------------
class _Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.jsonld_raw: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, anchor_text)
        self._in_script_ld = False
        self._skip_depth = 0
        self._cur_href = None
        self._cur_anchor: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip_depth += 1
            if tag == "script" and a.get("type", "").strip() == "application/ld+json":
                self._in_script_ld = True
                self._ld_buf = []
        elif tag == "meta":
            key = a.get("property") or a.get("name")
            if key and "content" in a:
                self.meta[key.lower()] = a["content"]
        elif tag == "a" and a.get("href"):
            self._cur_href = a["href"]
            self._cur_anchor = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            if self._in_script_ld:
                self.jsonld_raw.append("".join(self._ld_buf))
                self._in_script_ld = False
        elif tag == "a" and self._cur_href is not None:
            self.links.append((self._cur_href, " ".join(self._cur_anchor).strip()))
            self._cur_href = None
            self._cur_anchor = []

    def handle_data(self, data):
        if self._in_script_ld:
            self._ld_buf.append(data)
            return
        if self._skip_depth > 0:
            return
        s = data.strip()
        if s:
            self.text_parts.append(s)
            if self._cur_href is not None:
                self._cur_anchor.append(s)


def _parse_html(html: str, url: str = "") -> dict:
    p = _Extract()
    try:
        p.feed(html)
    except Exception:
        pass
    jsonld = []
    for raw in p.jsonld_raw:
        try:
            obj = json.loads(raw)
            jsonld.extend(obj if isinstance(obj, list) else [obj])
        except Exception:
            continue
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    return {
        "url": url,
        "html": html,
        "text": "\n".join(p.text_parts),
        "jsonld": jsonld,
        "meta": p.meta,
        "title": title or p.meta.get("og:title", ""),
        "links": p.links,
    }


def _fetch_rendered(url: str, timeout: int = 30) -> dict | None:
    """Fetch URL with Playwright headless browser. Returns parsed page or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="agent-a-readiness-scanner/0.1 (+contact)")
            pg = ctx.new_page()
            pg.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            # Wait for JS to render product content
            pg.wait_for_timeout(3000)
            html = pg.content()
            browser.close()
        return _parse_html(html, url)
    except Exception:
        return None


def fetch(target: str, timeout: int = 30) -> dict:
    """Fetch a URL or read a local .html file -> normalized page dict."""
    import os
    render = os.environ.get("RENDER", "").lower() == "playwright"

    if re.match(r"^https?://", target):
        # Check cache — prevent garbage results from rapid repeated scans
        domain = urlparse(target).netloc
        cached = _fetch_cache.get(domain)
        if cached:
            ts, cached_page = cached
            if time.time() - ts < CACHE_TTL:
                # Return cached page with updated URL
                page = dict(cached_page)
                page["url"] = target
                page["_cached"] = True
                return page
            else:
                del _fetch_cache[domain]
        import requests  # local import so offline/file mode needs no network dep
        headers = {"User-Agent": "agent-a-readiness-scanner/0.1 (+contact)"}
        try:
            r = requests.get(target, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            return {"url": target, "status": 0, "html": "", "text": "",
                    "jsonld": [], "meta": {}, "title": "", "links": [],
                    "llms_txt": False, "llms_txt_content": None, "robots": None,
                    "cart_api": None, "checkout_html": None, "homepage_html": None,
                    "sitemap_xml": None, "fetch_time_ms": None,
                    "agent_probe_status": None, "_fetch_error": str(e)}
        # If rate-limited (429), fall back to Playwright (real browser UA)
        if r.status_code == 429:
            rendered = _fetch_rendered(target, timeout)
            if rendered and rendered.get("html"):
                page = _parse_html(rendered["html"], target)
                page["status"] = 200
                page["rendered_html"] = rendered["html"]
                page["rendered_text"] = rendered["text"]
                page["rendered_title"] = rendered["title"]
                page["rendered_jsonld"] = rendered["jsonld"]
                page["rendered_links"] = rendered["links"]
                page["rendered_meta"] = rendered["meta"]
                page["_429_recovered"] = True
                final_url = target
                origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
                llms_txt = _get_text(urljoin(origin, "/llms.txt"), timeout)
                page["llms_txt"] = llms_txt is not None
                page["llms_txt_content"] = llms_txt
                page["robots"] = _get_text(urljoin(origin, "/robots.txt"), timeout)
                page["cart_api"] = _probe_ok(urljoin(origin, "/cart/add.js"), timeout)
                page["checkout_html"] = _get_text(urljoin(origin, "/checkout"), timeout)
                page["homepage_html"] = _get_text(origin + "/", timeout)
                page["sitemap_xml"] = _get_text(urljoin(origin, "/sitemap.xml"), timeout)
                page["fetch_time_ms"] = None  # not measurable after 429 recovery
                page["agent_probe_status"] = 429  # we already know it rate-limits
                return page

        page = _parse_html(r.text, target)
        page["status"] = r.status_code
        # Use final URL after redirects for origin (e.g. http->https)
        final_url = r.url
        origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
        llms_txt = _get_text(urljoin(origin, "/llms.txt"), timeout)
        page["llms_txt"] = llms_txt is not None
        page["llms_txt_content"] = llms_txt
        page["robots"] = _get_text(urljoin(origin, "/robots.txt"), timeout)
        page["cart_api"] = _probe_ok(urljoin(origin, "/cart/add.js"), timeout)
        page["checkout_html"] = _get_text(urljoin(origin, "/checkout"), timeout)
        page["homepage_html"] = _get_text(origin + "/", timeout)
        page["sitemap_xml"] = _get_text(urljoin(origin, "/sitemap.xml"), timeout)
        page["fetch_time_ms"] = int(r.elapsed.total_seconds() * 1000)
        page["agent_probe_status"] = _probe_as_agent(target, timeout)

        # Rendered DOM: Playwright fetch for JS-heavy sites
        # Auto-enable if Playwright is installed and page looks JS-heavy,
        # or always when RENDER=playwright
        should_render = render
        if not should_render:
            # Auto-detect: if page is JS-heavy, try rendered fetch
            html_len = len(page.get("html", ""))
            if html_len > 100:
                import re as _re
                scripts = _re.findall(r"<script[^>]*>.*?</script>",
                                      page["html"], _re.I | _re.S)
                script_len = sum(len(s) for s in scripts)
                if script_len / html_len > 0.50:
                    should_render = True
                    page["_auto_render"] = True
        if should_render:
            rendered = _fetch_rendered(target, timeout)
            if rendered:
                page["rendered_html"] = rendered["html"]
                page["rendered_text"] = rendered["text"]
                page["rendered_title"] = rendered["title"]
                page["rendered_jsonld"] = rendered["jsonld"]
                page["rendered_links"] = rendered["links"]
                page["rendered_meta"] = rendered["meta"]
        # Cache successful fetch for this domain
        if page.get("status") == 200:
            _fetch_cache[domain] = (time.time(), page)
    else:
        with open(target, "r", encoding="utf-8") as f:
            html = f.read()
        page = _parse_html(html, target)
        page["status"] = 200
        page["llms_txt"] = None   # unknowable from a single local file
        page["llms_txt_content"] = None
        page["robots"] = None
        page["cart_api"] = None
        page["checkout_html"] = None
        page["homepage_html"] = None
        page["sitemap_xml"] = None
        page["fetch_time_ms"] = None
        page["agent_probe_status"] = None
    return page


def _probe_as_agent(url: str, timeout: int) -> int | None:
    """Probe the URL with a bot-like user-agent and return the HTTP status."""
    try:
        import requests
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "GPTBot/1.0"})
        return r.status_code
    except Exception:
        return None


def _probe_ok(url: str, timeout: int) -> bool:
    try:
        import requests
        return requests.get(url, timeout=timeout).status_code == 200
    except Exception:
        return False


def _get_text(url: str, timeout: int):
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def is_dead_page(page: dict) -> str | None:
    """Return an error message if the page is a 404 or soft-404, else None."""
    status = page.get("status")
    if status and status >= 400:
        return f"HTTP {status} — this URL returned an error. Please check the URL and try again."

    title = (page.get("title") or "").lower()
    soft_404_signals = ["not found", "404", "page doesn't exist",
                        "page does not exist", "no longer available"]
    for signal in soft_404_signals:
        if signal in title:
            return (f"This page appears to be a 404 (title: \"{page.get('title')}\"). "
                    "The product may have been removed or the URL may be wrong. "
                    "Please try a different product URL.")

    # Almost-empty page body (< 50 chars of visible text) likely means dead page
    text = page.get("text", "")
    if len(text.strip()) < 50 and status == 200:
        return ("This page has almost no visible content — it may be a removed product "
                "or a JavaScript-only page that didn't load. Please check the URL.")

    return None


def is_collection_page(page: dict) -> str | None:
    """Return a warning if the page looks like a collection/category, not a PDP."""
    url = page.get("url", "")
    title = (page.get("title") or "").lower()

    # URL signals
    url_lower = url.lower()
    collection_paths = ("/collections/", "/categories/", "/category/",
                        "/collection/", "/shop/all", "/shop?")
    is_collection_url = any(p in url_lower for p in collection_paths)

    # Content signals: no Product JSON-LD but multiple product links
    from shopper import _jsonld_offers
    obj, _ = _jsonld_offers(page)
    has_product_jsonld = obj is not None

    product_links = sum(1 for href, _ in page.get("links", [])
                        if "/products/" in href.lower() or "/product/" in href.lower())

    if is_collection_url and not has_product_jsonld:
        return (f"This URL looks like a collection page, not a product page. "
                f"The scanner is designed for product pages (PDPs). "
                f"Try scanning a specific product URL instead "
                f"(e.g. one of the {product_links} product links found on this page)."
                if product_links > 1 else
                "This URL looks like a collection page, not a product page. "
                "The scanner is designed for product pages (PDPs). "
                "Try scanning a specific product URL instead.")

    if not has_product_jsonld and product_links >= 5:
        return (f"This page has no Product JSON-LD but links to {product_links} products — "
                f"it may be a category or listing page. The scanner works best on "
                f"individual product pages (PDPs).")

    return None


if __name__ == "__main__":
    page = fetch(sys.argv[1])
    print(json.dumps({k: (v if k not in ("html", "text") else f"<{len(v)} chars>")
                      for k, v in page.items()}, indent=2)[:2000])
