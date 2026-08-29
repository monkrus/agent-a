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
import ipaddress
import json
import os
import pathlib
import re
import socket
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin


# ---- SSRF protection --------------------------------------------------------
def _is_safe_url(url: str) -> bool:
    """Reject URLs targeting private/loopback/link-local/reserved IPs.

    Only http/https allowed. Resolves hostname via DNS and checks every
    returned IP against ipaddress safety predicates.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        return False
    for family, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


class _UnsafeURLError(ValueError):
    """Raised when a URL targets a private/internal host."""
    pass


def _safe_get(url, headers=None, timeout=30, max_redirects=5):
    """GET that re-runs _is_safe_url on every redirect hop."""
    import requests as _req
    current = url
    for _ in range(max_redirects):
        if not _is_safe_url(current):
            raise _UnsafeURLError(f"unsafe redirect target: {current}")
        r = _req.get(current, headers=headers, timeout=timeout,
                     allow_redirects=False)
        if r.is_redirect or r.is_permanent_redirect:
            loc = r.headers.get("Location", "")
            current = urljoin(current, loc)
            continue
        # Attach the final URL so callers can use r.url as before
        r.url = current
        return r
    raise _UnsafeURLError("too many redirects")


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
    m = re.search(r"<title[^>]{0,500}>([^<]{0,500})</title>", html, re.I)
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
    if not _is_safe_url(url):
        return None
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
        # SSRF guard: reject private/loopback/link-local/metadata IPs
        if not _is_safe_url(target):
            raise _UnsafeURLError(f"URL targets a private or reserved IP: {target}")
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
            r = _safe_get(target, headers=headers, timeout=timeout)
        except (requests.exceptions.RequestException, _UnsafeURLError) as e:
            return {"url": target, "status": 0, "html": "", "text": "",
                    "jsonld": [], "meta": {}, "title": "", "links": [],
                    "llms_txt": False, "llms_txt_content": None, "robots": None,
                    "cart_api": None, "checkout_html": None, "homepage_html": None,
                    "sitemap_xml": None, "mcp_json": None,
                    "oauth_discovery": None, "markdown_negotiation": None,
                    "agent_verification": None, "a2a_agent_card": None,
                    "auth_md": None, "link_headers": None, "dns_aid": None,
                    "cart_rate_test": None, "admin_exposure": None,
                    "fetch_time_ms": None,
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
                page["mcp_json"] = _get_json(urljoin(origin, "/.well-known/mcp.json"), timeout)
                page["oauth_discovery"] = _get_json(urljoin(origin, "/.well-known/oauth-authorization-server"), timeout)
                page["markdown_negotiation"] = _probe_markdown_negotiation(target, timeout)
                page["agent_verification"] = _get_json(urljoin(origin, "/.well-known/agent-verification"), timeout)
                page["a2a_agent_card"] = _get_json(urljoin(origin, "/.well-known/agent.json"), timeout)
                page["auth_md"] = _get_text(urljoin(origin, "/auth.md"), timeout)
                page["link_headers"] = _probe_link_headers(target, timeout)
                page["dns_aid"] = _probe_dns_aid(urlparse(final_url).netloc)
                page["cart_rate_test"] = _probe_cart_rate(urljoin(origin, "/cart/add.js"), timeout)
                page["admin_exposure"] = _probe_admin_paths(origin, timeout)
                page["fetch_time_ms"] = None  # not measurable after 429 recovery
                # Don't assume 429 on our scanner UA means agents are blocked —
                # run the real multi-UA probe (GPTBot, ClaudeBot, etc.)
                probe = _probe_as_agent(target, timeout)
                page["agent_probe_status"] = probe["status"]
                page["agent_probe_detail"] = probe
                page["_initial_429"] = True  # record that our scanner was rate-limited
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
        page["mcp_json"] = _get_json(urljoin(origin, "/.well-known/mcp.json"), timeout)
        page["oauth_discovery"] = _get_json(urljoin(origin, "/.well-known/oauth-authorization-server"), timeout)
        page["markdown_negotiation"] = _probe_markdown_negotiation(target, timeout)
        page["agent_verification"] = _get_json(urljoin(origin, "/.well-known/agent-verification"), timeout)
        page["a2a_agent_card"] = _get_json(urljoin(origin, "/.well-known/agent.json"), timeout)
        page["auth_md"] = _get_text(urljoin(origin, "/auth.md"), timeout)
        page["link_headers"] = _probe_link_headers(target, timeout)
        page["dns_aid"] = _probe_dns_aid(urlparse(final_url).netloc)
        page["cart_rate_test"] = _probe_cart_rate(urljoin(origin, "/cart/add.js"), timeout)
        page["admin_exposure"] = _probe_admin_paths(origin, timeout)
        page["fetch_time_ms"] = int(r.elapsed.total_seconds() * 1000)
        probe = _probe_as_agent(target, timeout)
        page["agent_probe_status"] = probe["status"]
        page["agent_probe_detail"] = probe

        # Rendered DOM: Playwright fetch for JS-heavy sites
        # Auto-enable if Playwright is installed and page looks JS-heavy,
        # or always when RENDER=playwright
        should_render = render
        if not should_render:
            # Auto-detect: if page is JS-heavy, try rendered fetch
            html_len = len(page.get("html", ""))
            if html_len > 100:
                import re as _re
                scripts = _re.findall(r"<script[^>]{0,500}>.*?</script>",
                                      page["html"], _re.I | _re.DOTALL)
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
        # Local file mode (CLI only, not web-facing)
        safe_name = os.path.basename(target)
        local_dir = os.path.realpath(os.path.dirname(target) or ".")
        fpath = os.path.realpath(os.path.join(local_dir, safe_name))
        if not fpath.startswith(local_dir):
            raise ValueError(f"Path traversal blocked: {target}")
        if not os.path.isfile(fpath):
            raise FileNotFoundError(f"Local file not found: {fpath}")
        _, ext = os.path.splitext(fpath)
        if ext not in (".html", ".htm", ".txt"):
            raise ValueError(f"Unsupported file type: {ext}")
        with open(fpath, "r", encoding="utf-8") as f:
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
        page["mcp_json"] = None
        page["oauth_discovery"] = None
        page["markdown_negotiation"] = None
        page["agent_verification"] = None
        page["a2a_agent_card"] = None
        page["auth_md"] = None
        page["link_headers"] = None
        page["dns_aid"] = None
        page["cart_rate_test"] = None
        page["admin_exposure"] = None
        page["fetch_time_ms"] = None
        page["agent_probe_status"] = None
    return page


def _probe_single_ua(url: str, ua: str, timeout: int) -> dict:
    """Probe the URL with a single bot UA, 2-of-3 vote to reduce flakiness.

    Returns a dict with:
      status: HTTP status code (majority vote) or None
      readable_words: word count of response body (0 = challenge/empty)
      challenge: True if response looks like a WAF/bot challenge page
      inconclusive: True if all attempts timed out or failed
    """
    result = {"status": None, "readable_words": 0, "challenge": False,
              "inconclusive": False}

    statuses = []
    last_response = None
    for _ in range(3):
        try:
            r = _safe_get(url, timeout=timeout,
                          headers={"User-Agent": ua})
            statuses.append(r.status_code)
            last_response = r
        except _UnsafeURLError:
            result["inconclusive"] = True
            return result
        except Exception:
            statuses.append(None)
        if len(statuses) >= 2 and statuses.count(statuses[0]) >= 2:
            break  # early exit on agreement

    # Majority vote: pick the most common status
    valid = [s for s in statuses if s is not None]
    if not valid:
        result["inconclusive"] = True
        return result

    from collections import Counter
    result["status"] = Counter(valid).most_common(1)[0][0]

    # Analyze response body for challenge signatures and readable content
    if last_response is not None:
        body = last_response.text or ""
        import re as _re
        # Strip tags for word count
        text = _re.sub(r"<[^>]{1,500}>", " ", body)
        words = len(text.split())
        result["readable_words"] = words

        # Detect common WAF/bot challenge pages
        # Match against visible text (tags stripped), not raw HTML — script
        # tags, attributes, and comments contain false-positive keywords
        # (e.g. Shopify's <script id="captcha-bootstrap"> on every store).
        tl = text.lower()
        challenge_sigs = ("cf-challenge", "challenge-platform",
                          "checking your browser", "please verify",
                          "access denied", "bot detection", "ddos protection",
                          "captcha")
        matched = [sig for sig in challenge_sigs if sig in tl]
        # Real challenge pages are thin (< 500 words of visible content).
        # A 5000-word product page mentioning "access denied" in its
        # privacy policy is not a challenge.
        if matched and words < 500:
            result["challenge"] = True
            result["challenge_sigs"] = matched

    return result


# The four AI crawler user-agents to probe
_AGENT_UAS = [
    ("GPTBot", "GPTBot/1.0"),
    ("ClaudeBot", "ClaudeBot/1.0"),
    ("PerplexityBot", "PerplexityBot/1.0"),
    ("OAI-SearchBot", "OAI-SearchBot/1.0"),
]


def _probe_as_agent(url: str, timeout: int) -> dict:
    """Probe the URL with multiple AI crawler UAs, 2-of-3 vote per UA.

    Probes four user-agents sequentially (to avoid triggering rate limits):
    GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot.

    Returns a dict with:
      status: HTTP status from GPTBot (backwards compat)
      readable_words: word count from GPTBot response
      challenge: True if GPTBot response looks like a WAF/bot challenge
      inconclusive: True if GPTBot probe was inconclusive
      note: 'self-asserted UA, not verified vendor IP'
      per_ua: dict mapping UA name to {status, readable_words, challenge}
      blocked_uas: list of UA names that got 403/429/challenge
      allowed_uas: list of UA names that got 200 without challenge
    """
    result = {"status": None, "readable_words": 0, "challenge": False,
              "inconclusive": False, "note": "self-asserted UA, not verified vendor IP",
              "per_ua": {}, "blocked_uas": [], "allowed_uas": []}
    try:
        import requests  # noqa: F401 — ensure requests is importable
    except ImportError:
        result["inconclusive"] = True
        return result

    blocked = []
    allowed = []

    for ua_name, ua_string in _AGENT_UAS:
        probe = _probe_single_ua(url, ua_string, timeout)
        result["per_ua"][ua_name] = {
            "status": probe["status"],
            "readable_words": probe["readable_words"],
            "challenge": probe["challenge"],
        }

        # Classify: blocked if 403, 429, or challenge detected
        status = probe["status"]
        if probe["challenge"] or status in (403, 429):
            blocked.append(ua_name)
        elif status == 200:
            allowed.append(ua_name)
        # Other statuses (None/inconclusive, 5xx, etc.) go in neither list

    result["blocked_uas"] = blocked
    result["allowed_uas"] = allowed

    # Backwards compat: top-level fields use GPTBot result
    gpt_probe = result["per_ua"].get("GPTBot", {})
    result["status"] = gpt_probe.get("status")
    result["readable_words"] = gpt_probe.get("readable_words", 0)
    result["challenge"] = gpt_probe.get("challenge", False)
    # inconclusive only if GPTBot itself was inconclusive
    if gpt_probe.get("status") is None:
        result["inconclusive"] = True

    return result


def _probe_ok(url: str, timeout: int) -> bool:
    try:
        return _safe_get(url, timeout=timeout).status_code == 200
    except Exception:
        return False


def _get_text(url: str, timeout: int):
    try:
        r = _safe_get(url, timeout=timeout)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def _probe_markdown_negotiation(url: str, timeout: int) -> dict | None:
    """Probe whether the server supports content negotiation for markdown."""
    try:
        r = _safe_get(url, timeout=timeout,
                      headers={"Accept": "text/markdown",
                               "User-Agent": "agent-a-readiness-scanner/0.1"})
        ct = r.headers.get("Content-Type", "")
        return {
            "status": r.status_code,
            "content_type": ct,
            "supports_markdown": "markdown" in ct.lower(),
            "body_length": len(r.text) if r.status_code == 200 else 0,
        }
    except Exception:
        return None


def _get_json(url: str, timeout: int) -> dict | None:
    """Fetch a URL and parse as JSON. Returns parsed dict or None."""
    try:
        r = _safe_get(url, timeout=timeout,
                      headers={"User-Agent": "agent-a-readiness-scanner/0.1"})
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _probe_link_headers(url: str, timeout: int) -> dict | None:
    """Check response headers for Link rel=describedby, rel=api-catalog, etc."""
    try:
        if not _is_safe_url(url):
            return None
        import requests
        r = requests.head(url, timeout=timeout, allow_redirects=False,
                          headers={"User-Agent": "agent-a-readiness-scanner/0.1"})
        link_header = r.headers.get("Link", "")
        return {
            "link_header": link_header or None,
            "has_describedby": "describedby" in link_header.lower(),
            "has_api_catalog": "api-catalog" in link_header.lower() or "api-description" in link_header.lower(),
            "has_search": 'rel="search"' in link_header.lower(),
        } if link_header else {"link_header": None, "has_describedby": False,
                                "has_api_catalog": False, "has_search": False}
    except Exception:
        return None


def _probe_dns_aid(domain: str) -> dict | None:
    """Check DNS TXT records for AI Discovery (DNS-AID) entries."""
    try:
        import subprocess
        result = subprocess.run(
            ["nslookup", "-type=TXT", f"_ai.{domain}"],
            capture_output=True, text=True, timeout=10)
        output = result.stdout + result.stderr
        has_aid = "_ai." in output and "text" in output.lower()
        return {"has_dns_aid": has_aid, "raw": output[:500] if has_aid else None}
    except Exception:
        return {"has_dns_aid": False, "raw": None}


def _probe_cart_rate(cart_url: str, timeout: int) -> dict | None:
    """Probe cart API endpoint multiple times rapidly to test rate limiting."""
    try:
        if not _is_safe_url(cart_url):
            return None
        import requests
        statuses = []
        for _ in range(5):
            try:
                r = requests.post(cart_url, timeout=timeout,
                                  allow_redirects=False,
                                  headers={"User-Agent": "agent-a-readiness-scanner/0.1",
                                           "Content-Type": "application/json"},
                                  json={"id": 0, "quantity": 1})
                statuses.append(r.status_code)
            except Exception:
                statuses.append(None)
        rate_limited = any(s == 429 for s in statuses if s)
        all_ok = all(s in (200, 422, 400) for s in statuses if s)  # 422/400 = invalid product, but endpoint responded
        return {
            "statuses": statuses,
            "rate_limited": rate_limited,
            "all_accepted": all_ok and not rate_limited,
            "endpoint_exists": any(s and s != 404 for s in statuses),
        }
    except Exception:
        return None


def _probe_admin_paths(origin: str, timeout: int) -> dict | None:
    """Check if admin/staff/API paths are exposed without auth."""
    try:
        if not _is_safe_url(origin + "/"):
            return None
        import requests
        paths = ["/admin", "/admin/api", "/staff", "/.env", "/api/products.json"]
        exposed = []
        for p in paths:
            try:
                r = requests.get(origin + p, timeout=timeout, allow_redirects=False,
                                 headers={"User-Agent": "agent-a-readiness-scanner/0.1"})
                # 200 with content = exposed; 301/302 to login = properly gated
                if r.status_code == 200 and len(r.text) > 200:
                    exposed.append({"path": p, "status": r.status_code})
            except Exception:
                continue
        return {"exposed_paths": exposed, "checked": len(paths)}
    except Exception:
        return None


def is_dead_page(page: dict) -> str | None:
    """Return an error message if the page is a 404 or soft-404, else None."""
    status = page.get("status")
    # 429 = rate-limited, not dead — let the scan proceed so RDY-031 can report it
    if status and status >= 400 and status != 429:
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
