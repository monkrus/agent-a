#!/usr/bin/env python3
"""
outreach.py — Generate outreach email drafts from scan results.

Takes a scan payload dict and generates a merchant-friendly email
using ONLY actual scan findings (no invented claims).
"""
from __future__ import annotations

from urllib.parse import urlparse


def _domain(url):
    h = urlparse(url).hostname or url
    return h[4:] if h.startswith("www.") else h


def _worst_finding_plain(results):
    """Pick the single most surprising finding, phrased for a merchant."""
    SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    fails = [r for r in results if r.get("verdict") == "FAIL"]
    if not fails:
        unknowns = [r for r in results if r.get("verdict") == "UNKNOWN"]
        if unknowns:
            return "several checks couldn't be verified — if our scanner can't find the data, neither can a shopping agent"
        return "all checks passed"
    fails.sort(key=lambda r: SEV.get(r.get("severity_if_fail", "medium"), 3))
    worst = fails[0]

    title = worst.get("title", "").lower()
    pr = worst.get("pass_rate", "")
    detail = worst.get("detail", "")

    # Build merchant-friendly description
    if "price" in title and "extract" in title and pr:
        parts = pr.split("/")
        if len(parts) == 2:
            correct, total = parts
            wrong = int(total) - int(correct)
            return f"in {wrong} of {total} test visits, AI agents read your price incorrectly or couldn't find it at all"
    if "structured data" in title or "json-ld" in title:
        return "your product pages have no structured data (JSON-LD), so AI shopping agents can't reliably read your prices or availability"
    if "price" in title and "html" in title:
        return "your price only appears after JavaScript runs — most AI agents don't run JavaScript and see no price at all"
    if "robots" in title:
        return "your robots.txt blocks AI shopping agents from reading your product pages entirely"
    if "availability" in title and pr and "/" in pr:
        parts = pr.split("/")
        if len(parts) == 2:
            return f"AI agents got your stock availability right only {parts[0]} of {parts[1]} times — inconsistent answers lose buyer confidence"
    if "cart" in title:
        return "AI agents couldn't find or click your Add to Cart button"
    if "llms" in title:
        return "your site has no llms.txt file, so AI agents have zero guidance on how to interact with your store"
    if "policy" in title:
        return "AI agents can't find your return policy, so they tell shoppers 'unknown' when asked"
    if "shipping" in title:
        return "AI agents give different shipping answers each time a customer asks"
    if "injection" in title:
        return "your pages contain text patterns that could hijack an AI agent's behavior"
    if "javascript" in title or "js" in title or "render" in title:
        return "your product page relies heavily on JavaScript — AI agents that don't run JS see almost no content"
    if "variant" in title:
        return "your size/color selectors use custom JS widgets that AI agents can't interact with"
    if "product" in title and "identif" in title:
        return "AI agents can't reliably identify what product this page sells"
    if "json-ld" in title and "complete" in title:
        return "your structured product data is incomplete — AI agents need all fields to compare products accurately"
    if pr and "/" in pr:
        parts = pr.split("/")
        if len(parts) == 2:
            return f"agents got '{worst.get('title', 'this check')}' right only {parts[0]} of {parts[1]} times"
    if detail and len(detail) < 100:
        return detail.rstrip(".")
    return worst.get("title", "a readiness issue was found")


def generate_email(scan_data: dict, permalink: str) -> str:
    """Generate outreach email markdown from scan data."""
    target = scan_data.get("meta", {}).get("target", "")
    domain = _domain(target)
    score = scan_data.get("readiness_score")
    results = scan_data.get("results", [])
    worst = _worst_finding_plain(results)

    score_str = str(int(score)) if score is not None else "N/A"

    email = f"""---
Subject: {domain} scored {score_str}/100 for AI shopping agents

Hi — I run an agent-readiness scanner that tests how reliably AI
shopping agents (the kind now built into ChatGPT, Perplexity, and
Claude) can read product pages. {domain} scored {score_str}/100.

The finding that matters most: {worst}.

Full free report: {permalink}

If AI-driven traffic matters to your roadmap, happy to walk through
the fixes — most take under a day.

— Sergei Stadnik | github.com/monkrus/agent-a
---"""
    return email
