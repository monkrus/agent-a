#!/usr/bin/env python3
"""
impact.py — Revenue impact estimator.

Takes scan results and estimates how much revenue a merchant may be losing
because AI agents can't read, extract from, or interact with their product pages.

The model uses conservative, citeable assumptions. We output a range (low–high)
and show our math so the merchant can plug in their own traffic numbers.

Key assumptions (2026):
  - AI-referred product page visits: 5–15% of total traffic (Gartner, Forrester)
  - Agent-assisted conversion rate: 2–4% (similar to organic search)
  - Each failing check category reduces agent effectiveness differently
"""
from __future__ import annotations


def estimate(results: list[dict], product_price: float | None = None,
             monthly_visits: int | None = None) -> dict:
    """
    Estimate monthly revenue impact from agent readiness failures.

    Args:
        results: scan results list from scan.py
        product_price: product price (from JSON-LD or agent extraction)
        monthly_visits: monthly product page visits (if known)

    Returns dict with low/high estimates and breakdown.
    """
    # -- Extract product price from results if not provided --
    if product_price is None:
        product_price = _extract_price(results)
    if product_price is None or product_price <= 0:
        product_price = 50.0  # conservative fallback

    # -- Estimate monthly visits if not provided --
    # Use tiered defaults based on product price as a rough proxy for brand size
    if monthly_visits is None:
        if product_price >= 150:
            monthly_visits = 100_000  # premium DTC
        elif product_price >= 50:
            monthly_visits = 200_000  # mid-market DTC
        else:
            monthly_visits = 300_000  # high-volume / lower AOV

    # -- AI traffic share (conservative range) --
    ai_share_low = 0.05   # 5%
    ai_share_high = 0.15  # 15%

    # -- Agent conversion rate (when agent works correctly) --
    conv_rate_low = 0.02   # 2%
    conv_rate_high = 0.04  # 4%

    # -- Calculate failure impact by category --
    failure_impact = _categorize_failures(results)

    # -- Overall agent failure rate --
    # Each category contributes to the probability an agent-assisted
    # session fails to convert
    agent_fail_rate = _compound_failure_rate(failure_impact)

    # -- Revenue calculation --
    ai_visits_low = monthly_visits * ai_share_low
    ai_visits_high = monthly_visits * ai_share_high

    # Revenue lost = visits × fail_rate × conversion_rate × AOV
    lost_low = ai_visits_low * agent_fail_rate * conv_rate_low * product_price
    lost_high = ai_visits_high * agent_fail_rate * conv_rate_high * product_price

    return {
        "product_price": product_price,
        "monthly_visits_assumed": monthly_visits,
        "ai_traffic_share": f"{ai_share_low:.0%}–{ai_share_high:.0%}",
        "agent_failure_rate": round(agent_fail_rate, 2),
        "failure_breakdown": failure_impact,
        "estimated_monthly_loss": {
            "low": int(round(lost_low, -2)),     # round to nearest $100
            "high": int(round(lost_high, -2)),
        },
        "estimated_annual_loss": {
            "low": int(round(lost_low * 12, -3)),   # round to nearest $1000
            "high": int(round(lost_high * 12, -3)),
        },
        "assumptions": [
            f"Product price: ${product_price:.2f}",
            f"Monthly product page visits: {monthly_visits:,} (assumed)",
            f"AI-referred traffic: {ai_share_low:.0%}–{ai_share_high:.0%} of visits",
            f"Agent conversion rate: {conv_rate_low:.0%}–{conv_rate_high:.0%} (when working)",
            "Sources: Gartner AI in Commerce 2026, Forrester Channel Mix",
        ],
    }


def _extract_price(results: list[dict]) -> float | None:
    """Pull product price from scan results."""
    for r in results:
        # Try ground truth first
        gt = r.get("ground_truth")
        if r.get("category") == "price-extraction" and isinstance(gt, (int, float)):
            return float(gt)
    # Try agent answers
    for r in results:
        if r.get("category") == "price-extraction":
            for ans in r.get("sample_answers", []):
                try:
                    v = float(str(ans).replace(",", "").replace("$", ""))
                    if 0 < v < 100_000:
                        return v
                except (ValueError, TypeError):
                    continue
    return None


def _categorize_failures(results: list[dict]) -> dict:
    """Map failures to business impact categories."""
    impacts = {}

    for r in results:
        if r.get("verdict") not in ("FAIL", "UNKNOWN"):
            continue

        cat = r.get("category", "")
        title = r.get("title", "")
        sev = r.get("severity_if_fail", "medium")
        frac = r.get("pass_fraction")

        # Discovery: can agents find and identify the product?
        if cat in ("structured-data", "agent-access", "rendering"):
            key = "discovery"
            label = "Agent can't find or identify the product"
        # Accuracy: does the agent get the facts right?
        elif cat in ("price-extraction", "price-legibility", "availability-extraction",
                      "identity-extraction"):
            key = "accuracy"
            label = "Agent gives wrong or missing information"
        # Interaction: can the agent help complete a purchase?
        elif cat in ("agent-interaction",):
            key = "interaction"
            label = "Agent can't help complete the purchase"
        # Policy: can the agent answer pre-purchase questions?
        elif cat in ("policy-extraction", "policy-legibility"):
            key = "confidence"
            label = "Agent can't answer pre-purchase questions"
        # Security
        elif cat == "security":
            key = "security"
            label = "Page vulnerable to agent manipulation"
        else:
            key = "other"
            label = "Other readiness issue"

        if key not in impacts:
            impacts[key] = {"label": label, "issues": [], "severity": sev}

        severity_weight = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}[sev]
        failure_depth = 1.0 - (frac if frac is not None else 0.0)

        impacts[key]["issues"].append({
            "title": title,
            "severity": sev,
            "impact_weight": round(severity_weight * failure_depth, 2),
        })
        # Upgrade category severity to worst issue
        if severity_weight > {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}[
                impacts[key]["severity"]]:
            impacts[key]["severity"] = sev

    return impacts


def _compound_failure_rate(failure_impact: dict) -> float:
    """
    Estimate the probability an agent-assisted session fails.

    Each impact category contributes independently — if discovery fails,
    accuracy doesn't matter. We model this as:
      P(fail) = 1 - product(1 - p_i) for each category

    Category weights reflect how much each impacts conversion:
      discovery: 0.40 (can't find product = total loss)
      accuracy:  0.30 (wrong info = failed checkout or lost trust)
      interaction: 0.15 (can't add to cart = no purchase)
      confidence: 0.10 (can't answer questions = abandoned)
      security: 0.05 (manipulation risk)
    """
    category_weights = {
        "discovery": 0.40,
        "accuracy": 0.30,
        "interaction": 0.15,
        "confidence": 0.10,
        "security": 0.05,
    }

    survival = 1.0
    for key, data in failure_impact.items():
        cw = category_weights.get(key, 0.05)
        # Max impact weight from issues in this category
        max_issue_weight = max(i["impact_weight"] for i in data["issues"]) if data["issues"] else 0
        # P(this category causes failure)
        p_fail = cw * max_issue_weight
        survival *= (1 - p_fail)

    return round(1 - survival, 3)


def format_impact(impact: dict) -> str:
    """Human-readable impact summary for reports."""
    lines = []
    low = impact["estimated_monthly_loss"]["low"]
    high = impact["estimated_monthly_loss"]["high"]
    annual_low = impact["estimated_annual_loss"]["low"]
    annual_high = impact["estimated_annual_loss"]["high"]

    lines.append(f"ESTIMATED REVENUE IMPACT")
    lines.append(f"{'=' * 50}")
    lines.append("")
    lines.append(f"Monthly:  ${low:,} – ${high:,}")
    lines.append(f"Annual:   ${annual_low:,} – ${annual_high:,}")
    lines.append("")
    lines.append(f"Agent failure rate: {impact['agent_failure_rate']:.0%}")
    lines.append("")

    lines.append("Failure breakdown:")
    for key, data in impact["failure_breakdown"].items():
        lines.append(f"  {data['label']} ({data['severity']})")
        for issue in data["issues"]:
            lines.append(f"    - {issue['title']}")

    lines.append("")
    lines.append("Assumptions (plug in your own numbers for a tighter estimate):")
    for a in impact["assumptions"]:
        lines.append(f"  - {a}")

    return "\n".join(lines)
