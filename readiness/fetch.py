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
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin


# ---- minimal HTML -> text + meta + jsonld --------------------------------
class _Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.jsonld_raw: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, anchor_text)
        self._in_script_ld = False
        self._in_skip = False
        self._cur_href = None
        self._cur_anchor: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._in_skip = True
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
            self._in_skip = False
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
        if self._in_skip:
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


def fetch(target: str, timeout: int = 30) -> dict:
    """Fetch a URL or read a local .html file -> normalized page dict."""
    if re.match(r"^https?://", target):
        import requests  # local import so offline/file mode needs no network dep
        headers = {"User-Agent": "agent-a-readiness-scanner/0.1 (+contact)"}
        r = requests.get(target, headers=headers, timeout=timeout)
        page = _parse_html(r.text, target)
        page["status"] = r.status_code
        origin = f"{urlparse(target).scheme}://{urlparse(target).netloc}"
        page["llms_txt"] = _probe_ok(urljoin(origin, "/llms.txt"), timeout)
        page["robots"] = _get_text(urljoin(origin, "/robots.txt"), timeout)
    else:
        with open(target, "r", encoding="utf-8") as f:
            html = f.read()
        page = _parse_html(html, target)
        page["status"] = 200
        page["llms_txt"] = None   # unknowable from a single local file
        page["robots"] = None
    return page


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


if __name__ == "__main__":
    page = fetch(sys.argv[1])
    print(json.dumps({k: (v if k not in ("html", "text") else f"<{len(v)} chars>")
                      for k, v in page.items()}, indent=2)[:2000])
