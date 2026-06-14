#!/usr/bin/env python3
"""
intel.py — Agent Intelligence module.

Detects what AI agents interact with a store and how, giving the merchant
proof that we understand their agent ecosystem. This is the credibility
section of the report: "here's who's already hitting your store."

Detects:
  - Shopping/AI agent access rules (robots.txt per-agent analysis)
  - llms.txt / agent guidance content and protocols (UCP, Shop skill, MCP)
  - Support/chat agents running on the page (Gorgias, Zendesk, Intercom, etc.)
  - Agent commerce protocols (UCP endpoint, Shop Pay agent checkout)
  - Platform detection (Shopify, WooCommerce, etc.)
  - Structured data exposed to agents
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urljoin


# ---- Agent user-agents we look for in robots.txt --------------------------
KNOWN_AGENTS = {
    "gptbot": {"name": "GPTBot (OpenAI)", "type": "shopping/search", "org": "OpenAI"},
    "oai-searchbot": {"name": "OAI-SearchBot", "type": "search", "org": "OpenAI"},
    "chatgpt-user": {"name": "ChatGPT-User", "type": "shopping", "org": "OpenAI"},
    "google-extended": {"name": "Google-Extended", "type": "AI training", "org": "Google"},
    "googleother": {"name": "GoogleOther", "type": "AI/search", "org": "Google"},
    "perplexitybot": {"name": "PerplexityBot", "type": "search", "org": "Perplexity"},
    "claudebot": {"name": "ClaudeBot", "type": "AI training", "org": "Anthropic"},
    "anthropic-ai": {"name": "Anthropic-AI", "type": "AI training", "org": "Anthropic"},
    "ccbot": {"name": "CCBot", "type": "AI training", "org": "Common Crawl"},
    "bytespider": {"name": "Bytespider", "type": "AI training", "org": "ByteDance"},
    "cohere-ai": {"name": "Cohere-AI", "type": "AI training", "org": "Cohere"},
    "meta-externalagent": {"name": "Meta-ExternalAgent", "type": "AI", "org": "Meta"},
    "facebookbot": {"name": "FacebookBot", "type": "social/AI", "org": "Meta"},
    "amazonbot": {"name": "Amazonbot", "type": "shopping/search", "org": "Amazon"},
    "applebot-extended": {"name": "Applebot-Extended", "type": "AI", "org": "Apple"},
}

# ---- Chat / support agent widgets detectable from script URLs ---------------
CHAT_AGENTS = {
    "gorgias": {"name": "Gorgias", "type": "support agent", "desc": "AI-powered e-commerce support"},
    "zendesk": {"name": "Zendesk", "type": "support agent", "desc": "Customer service platform"},
    "intercom": {"name": "Intercom", "type": "support agent", "desc": "AI customer messaging"},
    "drift": {"name": "Drift", "type": "sales agent", "desc": "Conversational AI for sales"},
    "tidio": {"name": "Tidio", "type": "chatbot", "desc": "AI chatbot for e-commerce"},
    "crisp": {"name": "Crisp", "type": "chatbot", "desc": "Customer messaging platform"},
    "livechat": {"name": "LiveChat", "type": "support agent", "desc": "Live chat + AI"},
    "freshchat": {"name": "Freshchat", "type": "support agent", "desc": "Freshworks messaging"},
    "gladly": {"name": "Gladly", "type": "support agent", "desc": "People-centered customer service"},
    "kustomer": {"name": "Kustomer", "type": "support agent", "desc": "AI customer service CRM"},
    "ada": {"name": "Ada", "type": "AI agent", "desc": "AI-first customer service automation"},
    "forethought": {"name": "Forethought", "type": "AI agent", "desc": "Generative AI for support"},
    "dixa": {"name": "Dixa", "type": "support agent", "desc": "Conversational customer service"},
    "re:amaze": {"name": "Re:amaze", "type": "support agent", "desc": "Helpdesk for e-commerce"},
    "reamaze": {"name": "Re:amaze", "type": "support agent", "desc": "Helpdesk for e-commerce"},
    "shopify-inbox": {"name": "Shopify Inbox", "type": "support agent", "desc": "Shopify native chat"},
}


def analyze(page: dict, llms_txt_content: str | None = None) -> dict:
    """Run all detections on a fetched page. Returns intel dict."""
    intel = {
        "platform": _detect_platform(page),
        "agent_access": _analyze_robots(page),
        "llms_txt": _analyze_llms_txt(page, llms_txt_content),
        "chat_agents": _detect_chat_agents(page),
        "structured_data": _analyze_structured_data(page),
        "agent_commerce": _detect_agent_commerce(page, llms_txt_content),
        "meta_directives": _analyze_meta_robots(page),
    }
    intel["summary"] = _build_summary(intel)
    return intel


def _detect_platform(page: dict) -> dict | None:
    html = (page.get("html", "") or "").lower()
    if "shopify" in html or "cdn.shopify.com" in html or "myshopify.com" in html:
        return {"name": "Shopify", "detail": "Shopify-powered storefront"}
    if "woocommerce" in html or "wp-content" in html:
        return {"name": "WooCommerce", "detail": "WordPress + WooCommerce"}
    if "bigcommerce" in html:
        return {"name": "BigCommerce", "detail": "BigCommerce storefront"}
    if "squarespace" in html:
        return {"name": "Squarespace", "detail": "Squarespace commerce"}
    if "magento" in html or "mage" in html:
        return {"name": "Magento", "detail": "Magento / Adobe Commerce"}
    return None


def _analyze_robots(page: dict) -> list[dict]:
    robots = page.get("robots") or ""
    if not robots:
        return []

    results = []
    # Split by User-agent blocks
    blocks = re.split(r"(?im)^user-agent:\s*", robots)
    for blk in blocks:
        if not blk.strip():
            continue
        lines = blk.strip().split("\n")
        ua_line = lines[0].strip().lower()

        for key, info in KNOWN_AGENTS.items():
            if key in ua_line or ua_line == key:
                rules = [l.strip() for l in lines[1:] if l.strip() and not l.strip().startswith("#")]
                blocked = any(re.match(r"(?i)disallow:\s*/\s*$", r) for r in rules)
                allowed_all = any(re.match(r"(?i)allow:\s*/\s*$", r) for r in rules)
                status = "blocked" if blocked else ("allowed" if allowed_all else "partial")
                results.append({
                    **info,
                    "ua": ua_line,
                    "status": status,
                    "rules": rules[:5],
                })
                break

    # Check wildcard rules for context
    for blk in blocks:
        if blk.strip().split("\n")[0].strip() == "*":
            rules = [l.strip() for l in blk.strip().split("\n")[1:] if l.strip() and not l.strip().startswith("#")]
            wildcard_blocked = any(re.match(r"(?i)disallow:\s*/\s*$", r) for r in rules)
            if wildcard_blocked:
                results.append({
                    "name": "All bots (wildcard)", "type": "all", "org": "—",
                    "ua": "*", "status": "blocked", "rules": rules[:5],
                })
            break

    return results


def _analyze_llms_txt(page: dict, content: str | None) -> dict:
    present = page.get("llms_txt", False)
    result = {"present": present, "protocols": [], "features": []}
    if not content:
        return result

    cl = content.lower()
    if "ucp" in cl or "universal commerce protocol" in cl:
        result["protocols"].append("UCP (Universal Commerce Protocol)")
    if "shop.app/skill" in cl or "shop skill" in cl:
        result["protocols"].append("Shop Skill (Shopify agent checkout)")
    if "mcp" in cl or "model context protocol" in cl:
        result["protocols"].append("MCP (Model Context Protocol)")
    if "acp" in cl or "agent commerce protocol" in cl:
        result["protocols"].append("ACP (Agent Commerce Protocol)")

    if "search_catalog" in cl or "product search" in cl:
        result["features"].append("Catalog search for agents")
    if "create_cart" in cl or "add to cart" in cl:
        result["features"].append("Agent cart creation")
    if "create_checkout" in cl or "checkout" in cl:
        result["features"].append("Agent checkout flow")
    if "/products/" in cl and ".json" in cl:
        result["features"].append("JSON product API")
    if "sitemap" in cl:
        result["features"].append("Sitemap exposed")
    if "refund" in cl or "return" in cl:
        result["features"].append("Policy links for agents")

    return result


def _detect_chat_agents(page: dict) -> list[dict]:
    html = (page.get("html", "") or "").lower()
    scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html, re.I)
    script_text = " ".join(scripts).lower()
    found = []

    for key, info in CHAT_AGENTS.items():
        if key in html or key in script_text:
            found.append(info)

    return found


def _analyze_structured_data(page: dict) -> dict:
    jsonld = page.get("jsonld", [])
    if not jsonld:
        return {"present": False, "types": []}

    types = []
    for obj in jsonld:
        if isinstance(obj, dict):
            t = obj.get("@type", "Unknown")
            if isinstance(t, list):
                types.extend(t)
            else:
                types.append(t)

    return {"present": True, "types": list(set(types)), "count": len(jsonld)}


def _detect_agent_commerce(page: dict, llms_txt_content: str | None) -> list[dict]:
    protocols = []
    html = (page.get("html", "") or "").lower()

    # Check for UCP endpoint
    if "/.well-known/ucp" in html or (llms_txt_content and "/.well-known/ucp" in llms_txt_content):
        protocols.append({
            "protocol": "UCP",
            "name": "Universal Commerce Protocol",
            "status": "active",
            "detail": "Agent checkout via UCP endpoint",
        })

    # Check for Shop Pay / Shop Skill
    if "shop-js" in html or "shop.app" in html or "shopify-pay" in html:
        protocols.append({
            "protocol": "Shop Pay",
            "name": "Shopify Shop Pay",
            "status": "active",
            "detail": "Shop Pay agent checkout available",
        })

    if llms_txt_content and "shop.app/skill" in llms_txt_content.lower():
        protocols.append({
            "protocol": "Shop Skill",
            "name": "Shop Skill for Agents",
            "status": "recommended",
            "detail": "Store recommends agents install Shop Skill for purchasing",
        })

    return protocols


def _analyze_meta_robots(page: dict) -> dict:
    meta = page.get("meta", {})
    robots_meta = meta.get("robots", "")
    result = {"tag": robots_meta or None}
    if robots_meta:
        rl = robots_meta.lower()
        result["noindex"] = "noindex" in rl
        result["nofollow"] = "nofollow" in rl
    else:
        result["noindex"] = False
        result["nofollow"] = False
    return result


def _build_summary(intel: dict) -> list[str]:
    points = []

    p = intel.get("platform")
    if p:
        points.append(f"Platform: {p['name']}")

    access = intel.get("agent_access", [])
    blocked = [a for a in access if a["status"] == "blocked"]
    allowed = [a for a in access if a["status"] == "allowed"]
    if blocked:
        names = ", ".join(a["name"] for a in blocked[:3])
        points.append(f"Blocks {len(blocked)} AI agent(s) in robots.txt: {names}")
    if allowed:
        names = ", ".join(a["name"] for a in allowed[:3])
        points.append(f"Explicitly allows {len(allowed)} AI agent(s): {names}")
    if not blocked and not allowed and access:
        points.append("No AI agents specifically blocked or allowed in robots.txt")

    llms = intel.get("llms_txt", {})
    if llms.get("present"):
        protos = llms.get("protocols", [])
        if protos:
            points.append(f"llms.txt present with agent protocols: {', '.join(protos)}")
        else:
            points.append("llms.txt present (basic agent guidance)")

    commerce = intel.get("agent_commerce", [])
    if commerce:
        names = ", ".join(c["protocol"] for c in commerce)
        points.append(f"Agent commerce enabled: {names}")

    chat = intel.get("chat_agents", [])
    if chat:
        names = ", ".join(c["name"] for c in chat)
        points.append(f"Support/chat agent(s) detected: {names}")

    sd = intel.get("structured_data", {})
    if sd.get("present"):
        points.append(f"Structured data: {', '.join(sd['types'])}")
    else:
        points.append("No structured data (JSON-LD) found — agents have no machine-readable product info")

    meta = intel.get("meta_directives", {})
    if meta.get("noindex"):
        points.append("Page has noindex directive — search agents will skip this page")

    return points
