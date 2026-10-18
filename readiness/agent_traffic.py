"""AI agent traffic analyzer — parse access logs and classify agent visits."""

import os
import re
import yaml
from collections import defaultdict
from pathlib import Path

_YAML_PATH = Path(__file__).parent / "agent_uas.yaml"
_agents = None


def _load_agents():
    global _agents
    if _agents is not None:
        return _agents
    with open(_YAML_PATH) as f:
        data = yaml.safe_load(f)
    _agents = data.get("agents", [])
    return _agents


def classify_ua(ua_string):
    """Classify a user-agent string. Returns agent dict or None."""
    if not ua_string:
        return None
    ua_lower = ua_string.lower()
    for agent in _load_agents():
        if agent["pattern"] in ua_lower:
            return agent
    return None


# Common log format patterns
# Combined: 127.0.0.1 - - [10/Oct/2026:13:55:36 -0700] "GET /products/foo HTTP/1.1" 200 2326 "-" "Mozilla/5.0 ..."
# Cloudflare JSON: {"ClientRequestURI":"/products/foo","ClientRequestUserAgent":"GPTBot/1.0",...}
# Simple TSV: /products/foo\tGPTBot/1.0\t200

_COMBINED_RE = re.compile(
    r'^(\S+)\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)\s+\S+"\s+(\d+)\s+\S+\s+"[^"]*"\s+"([^"]*)"'
)

_CLOUDFLARE_KEYS = {"ClientRequestURI", "ClientRequestUserAgent", "EdgeResponseStatus"}


def _parse_line_combined(line):
    """Parse Apache/Nginx combined log format."""
    m = _COMBINED_RE.match(line)
    if not m:
        return None
    return {
        "ip": m.group(1),
        "timestamp": m.group(2),
        "method": m.group(3),
        "path": m.group(4),
        "status": int(m.group(5)),
        "ua": m.group(6),
    }


def _parse_line_json(line):
    """Parse Cloudflare-style JSON log line."""
    import json as _json
    try:
        obj = _json.loads(line)
    except (ValueError, TypeError):
        return None
    # Cloudflare format
    if "ClientRequestUserAgent" in obj:
        return {
            "path": obj.get("ClientRequestURI", ""),
            "ua": obj.get("ClientRequestUserAgent", ""),
            "status": obj.get("EdgeResponseStatus", 0),
            "ip": obj.get("ClientIP", ""),
            "timestamp": obj.get("EdgeStartTimestamp", ""),
            "method": obj.get("ClientRequestMethod", "GET"),
        }
    # Generic JSON with ua/path fields
    if "ua" in obj or "user_agent" in obj:
        return {
            "path": obj.get("path", obj.get("url", "")),
            "ua": obj.get("ua", obj.get("user_agent", "")),
            "status": obj.get("status", obj.get("status_code", 0)),
            "ip": obj.get("ip", ""),
            "timestamp": obj.get("timestamp", obj.get("time", "")),
            "method": obj.get("method", "GET"),
        }
    return None


def parse_logs(log_text):
    """Parse access log text (combined, JSON, or TSV). Returns list of request dicts."""
    lines = log_text.strip().splitlines()
    if not lines:
        return []

    # Auto-detect format from first non-empty line
    first = lines[0].strip()
    if first.startswith("{"):
        parser = _parse_line_json
    else:
        parser = _parse_line_combined

    requests = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parsed = parser(line)
        if parsed:
            requests.append(parsed)
    return requests


def analyze(log_text):
    """Analyze access logs for AI agent traffic.

    Returns:
        {
            "total_requests": int,
            "agent_requests": int,
            "agents": {
                "GPTBot": {
                    "vendor": "OpenAI",
                    "type": "crawler",
                    "requests": int,
                    "unique_paths": int,
                    "product_pages": int,
                    "top_paths": [("/products/foo", count), ...],
                    "status_codes": {200: count, 403: count, ...},
                },
                ...
            },
            "timeline": [{"date": "2026-10-01", "agent_hits": int}, ...],
            "product_pages_visited": int,
            "blocked_requests": int,  # 403/429 to agents
        }
    """
    requests = parse_logs(log_text)
    total = len(requests)

    agents = defaultdict(lambda: {
        "requests": 0,
        "paths": defaultdict(int),
        "status_codes": defaultdict(int),
        "vendor": "",
        "type": "",
    })

    agent_count = 0
    product_pages = set()
    blocked = 0
    timeline = defaultdict(int)

    for req in requests:
        agent = classify_ua(req.get("ua", ""))
        if not agent:
            continue

        agent_count += 1
        name = agent["name"]
        agents[name]["requests"] += 1
        agents[name]["vendor"] = agent["vendor"]
        agents[name]["type"] = agent["type"]

        path = req.get("path", "")
        agents[name]["paths"][path] += 1

        status = req.get("status", 0)
        agents[name]["status_codes"][status] += 1

        if status in (403, 429):
            blocked += 1

        if "/products/" in path or "/collections/" in path:
            product_pages.add(path)

        # Timeline — extract date
        ts = req.get("timestamp", "")
        if ts:
            # Try to extract YYYY-MM-DD or DD/Mon/YYYY
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', ts)
            if date_match:
                timeline[date_match.group(1)] += 1
            else:
                date_match = re.search(r'(\d{2}/\w+/\d{4})', ts)
                if date_match:
                    timeline[date_match.group(1)] += 1

    # Build result
    result = {
        "total_requests": total,
        "agent_requests": agent_count,
        "agents": {},
        "product_pages_visited": len(product_pages),
        "blocked_requests": blocked,
        "timeline": sorted([{"date": d, "agent_hits": c} for d, c in timeline.items()],
                           key=lambda x: x["date"]),
    }

    for name, data in sorted(agents.items(), key=lambda x: -x[1]["requests"]):
        top_paths = sorted(data["paths"].items(), key=lambda x: -x[1])[:10]
        result["agents"][name] = {
            "vendor": data["vendor"],
            "type": data["type"],
            "requests": data["requests"],
            "unique_paths": len(data["paths"]),
            "product_pages": sum(1 for p in data["paths"] if "/products/" in p or "/collections/" in p),
            "top_paths": top_paths,
            "status_codes": dict(data["status_codes"]),
        }

    return result
