#!/usr/bin/env python3
"""
scorers.py — readiness-track graders.

Two families, mirroring the audit track's programmatic-vs-judge split:

  STATIC probes  -> deterministic PASS / FAIL / UNKNOWN on the fetched page.
  SHOPPER grades -> aggregate N agent answers into a pass rate:
       correctness: fraction of runs matching ground truth from the page.
       consistency: modal-answer agreement across runs (no ground truth needed);
                    low self-agreement means the page reads ambiguously to agents.

UNKNOWN is a first-class result (e.g. can't derive ground truth, or JS-only
page). It is disclosed in the report, never silently treated as PASS — same
discipline as the audit track's coverage section.
"""
from __future__ import annotations
import re
from collections import Counter

from shopper import _jsonld_offers, _jsonld_price, _jsonld_availability

POLICY_WORDS = ("return", "refund", "exchange")
AGENT_UAS = ("gptbot", "oai-searchbot", "google-extended", "perplexitybot",
             "claudebot", "anthropic-ai", "ccbot")


# ---- STATIC probes (detect name -> verdict) --------------------------------
def static_jsonld_product(page):
    obj, off = _jsonld_offers(page)
    if not obj:
        return "FAIL", "No schema.org/Product JSON-LD found."
    if not off or off.get("price") is None:
        return "FAIL", "Product JSON-LD present but offers.price missing."
    if not off.get("availability"):
        return "FAIL", "Product JSON-LD has price but no availability."
    return "PASS", "Product JSON-LD with price and availability present."


def static_price_in_html(page):
    html = page.get("html", "") or ""
    # strip script bodies so a JS-embedded price doesn't count as server-rendered
    visible = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    if re.search(r"[$£€]\s?\d[\d,]*\.?\d*", visible):
        return "PASS", "Currency-formatted price present in server HTML."
    if _jsonld_price(page) is not None:
        return "FAIL", "Price only in structured data, not in visible server HTML."
    return "FAIL", "No price string in server HTML (likely JS-rendered only)."


def static_robots_allows_agents(page):
    robots = page.get("robots")
    if robots is None:
        return "UNKNOWN", "robots.txt not fetched (local file or unreachable)."
    blocked = []
    blocks = re.split(r"(?im)^\s*user-agent:", robots)
    for blk in blocks:
        head = blk.strip().lower()
        ua = head.split("\n", 1)[0].strip()
        if any(a in ua for a in AGENT_UAS) and re.search(r"(?im)^\s*disallow:\s*/\s*$", blk):
            blocked.append(ua)
    if blocked:
        return "FAIL", f"robots.txt blocks agent user-agents: {', '.join(blocked)}."
    return "PASS", "No agent user-agents fully disallowed in robots.txt."


def static_policy_text_present(page):
    text = (page.get("text", "") or "").lower()
    links = " ".join(a for _, a in page.get("links", [])).lower()
    hrefs = " ".join(h for h, _ in page.get("links", [])).lower()
    if any(w in text for w in POLICY_WORDS) or any(w in links for w in POLICY_WORDS) \
            or "return" in hrefs or "refund" in hrefs:
        return "PASS", "Return/refund policy referenced in text or links."
    return "FAIL", "No discoverable return/refund policy text or link."


def static_llms_txt_present(page):
    v = page.get("llms_txt")
    if v is None:
        return "UNKNOWN", "llms.txt not probed (local file mode)."
    return ("PASS", "llms.txt present.") if v else ("FAIL", "No llms.txt at site root.")


STATIC = {
    "jsonld_product": static_jsonld_product,
    "price_in_html": static_price_in_html,
    "robots_allows_agents": static_robots_allows_agents,
    "policy_text_present": static_policy_text_present,
    "llms_txt_present": static_llms_txt_present,
}


def run_static(check, page):
    fn = STATIC.get(check.get("detect"))
    if not fn:
        return {"verdict": "UNKNOWN", "detail": f"no probe '{check.get('detect')}'",
                "pass_fraction": None}
    verdict, detail = fn(page)
    return {"verdict": verdict, "detail": detail,
            "pass_fraction": {"PASS": 1.0, "FAIL": 0.0}.get(verdict)}


# ---- SHOPPER grading --------------------------------------------------------
def _norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _norm_num(s):
    m = re.search(r"\d[\d,]*\.?\d*", str(s))
    return float(m.group(0).replace(",", "")) if m else None


def _ground_truth(kind, page):
    if kind == "price":
        return _jsonld_price(page)
    if kind == "availability":
        return _jsonld_availability(page)
    if kind == "product_name":
        return page.get("title") or None
    return None


def grade_shopper(check, page, answers):
    """answers: list[str] of N agent responses -> grading dict."""
    n = len(answers)
    mode = check.get("grade", "consistency")

    if mode == "correctness":
        gt = _ground_truth(check.get("ground_truth"), page)
        if gt is None:
            return {"verdict": "UNKNOWN", "pass_fraction": None, "n": n,
                    "detail": f"no ground truth for '{check.get('ground_truth')}' "
                              f"(page doesn't expose it cleanly — itself a weakness)."}
        hits = 0
        for a in answers:
            if isinstance(gt, float):
                hits += (_norm_num(a) == gt)
            else:
                hits += (_norm(gt) in _norm(a) or _norm(a) in _norm(gt)) and _norm(a) not in ("", "unknown")
        frac = hits / n if n else None
        return {"verdict": _rate_verdict(frac, check), "pass_fraction": frac,
                "n": n, "pass_rate": f"{hits}/{n}", "ground_truth": gt,
                "detail": f"{hits}/{n} runs matched ground truth ({gt})."}

    # consistency
    counts = Counter(_norm(a) for a in answers)
    modal, modal_n = counts.most_common(1)[0]
    frac = modal_n / n if n else None
    return {"verdict": _rate_verdict(frac, check), "pass_fraction": frac, "n": n,
            "pass_rate": f"{modal_n}/{n}", "modal_answer": modal,
            "detail": f"agent agreed with itself {modal_n}/{n} (modal: '{modal}'); "
                      f"{len(counts)} distinct answers."}


# severity-keyed thresholds, same philosophy as audit methodology.md
THRESH = {"critical": 1.0, "high": 0.95, "medium": 0.90, "low": 0.80}


def _rate_verdict(frac, check):
    if frac is None:
        return "UNKNOWN"
    need = THRESH.get(check.get("severity_if_fail", "medium"), 0.90)
    return "PASS" if frac >= need else "FAIL"
