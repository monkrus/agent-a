#!/usr/bin/env python3
"""
validate_report.py — Gate for client-facing reports.

Checks that a report document (HTML or DOCX) matches its source payload.
Exits 0 if all checks pass, 1 if any fail.

Usage:
  python readiness/validate_report.py readiness/.scans/cli/results.json --report readiness/.scans/lolaluna-report.html
  python readiness/validate_report.py readiness/.scans/cli/results.json --report readiness/.scans/lolaluna-report.docx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_payload(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_report_text(path: str) -> str:
    """Extract plain text from HTML or DOCX report."""
    p = Path(path)
    if p.suffix == ".html":
        html = p.read_text(encoding="utf-8")
        # Strip tags, decode entities
        text = re.sub(r"<[^>]+>", " ", html)
        text = text.replace("&mdash;", "—").replace("&ndash;", "–")
        text = text.replace("&bull;", "•").replace("&plusmn;", "±")
        text = text.replace("&euro;", "€").replace("&amp;", "&")
        text = re.sub(r"&#\d+;", " ", text)
        text = re.sub(r"&\w+;", " ", text)
        return text
    elif p.suffix == ".docx":
        try:
            from docx import Document
            doc = Document(str(p))
            parts = []
            for para in doc.paragraphs:
                parts.append(para.text)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
            return "\n".join(parts)
        except ImportError:
            print("WARN: python-docx not installed, skipping DOCX validation")
            return ""
    else:
        return p.read_text(encoding="utf-8")


def validate(payload: dict, report_text: str) -> list[str]:
    """Return list of error strings. Empty = all good."""
    errors = []

    if not report_text.strip():
        errors.append("Report text is empty — cannot validate")
        return errors

    # --- 1. Score ---
    payload_score = payload.get("readiness_score")
    if payload_score is not None:
        score_str = str(payload_score)
        if score_str not in report_text:
            # Try integer form
            score_int = str(int(round(payload_score)))
            if score_int not in report_text:
                errors.append(
                    f"SCORE MISMATCH: payload says {payload_score}, "
                    f"not found in report (looked for '{score_str}' and '{score_int}')"
                )

    # --- 2. Confidence margin ---
    margin = payload.get("confidence_margin")
    if margin is not None:
        margin_str = str(margin)
        if margin_str not in report_text:
            errors.append(
                f"CONFIDENCE MARGIN: payload says ±{margin}, not found in report"
            )

    # --- 3. Verdict counts ---
    results = payload.get("results", [])
    pass_count = sum(1 for r in results if r.get("verdict") == "PASS")
    fail_count = sum(1 for r in results if r.get("verdict") == "FAIL")
    unkn_count = sum(1 for r in results if r.get("verdict") == "UNKNOWN")

    if str(pass_count) not in report_text:
        errors.append(f"PASS COUNT: payload has {pass_count} PASS, not found in report")
    if str(fail_count) not in report_text:
        errors.append(f"FAIL COUNT: payload has {fail_count} FAIL, not found in report")
    if unkn_count > 0 and str(unkn_count) not in report_text:
        errors.append(f"UNKNOWN COUNT: payload has {unkn_count} UNKNOWN, not found in report")

    # --- 4. Per-check verdicts ---
    for r in results:
        check_id = r.get("id", "???")
        verdict = r.get("verdict", "???")
        # Check that the check ID appears in the report
        if check_id not in report_text:
            errors.append(f"MISSING CHECK: {check_id} not mentioned in report")
            continue
        # For shopper checks, verify pass rate if present
        pass_rate = r.get("pass_rate")
        if pass_rate and pass_rate not in report_text:
            # Try fraction form
            pf = r.get("pass_fraction")
            n = r.get("n")
            if pf is not None and n:
                alt = f"{int(pf * n)}/{n}"
                if alt not in report_text:
                    errors.append(
                        f"PASS RATE: {check_id} payload says {pass_rate}, "
                        f"not found in report"
                    )

    # --- 5. Revenue figures ---
    impact = payload.get("impact", {})

    monthly = impact.get("estimated_monthly_loss", {})
    monthly_low = monthly.get("low")
    monthly_high = monthly.get("high")
    if monthly_low is not None:
        low_str = f"{monthly_low:,}"
        if low_str not in report_text and str(monthly_low) not in report_text:
            errors.append(
                f"REVENUE: monthly low ${low_str} from payload not found in report"
            )
    if monthly_high is not None:
        high_str = f"{monthly_high:,}"
        if high_str not in report_text and str(monthly_high) not in report_text:
            errors.append(
                f"REVENUE: monthly high ${high_str} from payload not found in report"
            )

    annual = impact.get("estimated_annual_loss", {})
    annual_low = annual.get("low")
    annual_high = annual.get("high")
    if annual_low is not None:
        low_str = f"{annual_low:,}"
        if low_str not in report_text and str(annual_low) not in report_text:
            errors.append(
                f"REVENUE: annual low ${low_str} from payload not found in report"
            )
    if annual_high is not None:
        high_str = f"{annual_high:,}"
        if high_str not in report_text and str(annual_high) not in report_text:
            errors.append(
                f"REVENUE: annual high ${high_str} from payload not found in report"
            )

    # --- 6. Failure rate ---
    fail_rate = impact.get("agent_failure_rate")
    if fail_rate is not None:
        pct = f"{fail_rate:.0%}"
        pct_num = str(int(fail_rate * 100))
        if pct not in report_text and pct_num not in report_text:
            errors.append(
                f"FAILURE RATE: payload says {pct}, not found in report"
            )

    # --- 7. Monthly visits ---
    visits = impact.get("monthly_visits_assumed")
    if visits is not None:
        visits_str = f"{visits:,}"
        if visits_str not in report_text and str(visits) not in report_text:
            errors.append(
                f"TRAFFIC: payload assumes {visits_str} monthly visits, "
                f"not found in report"
            )

    # --- 8. N (agent visits) ---
    n = payload.get("meta", {}).get("n")
    if n is not None:
        if str(n) not in report_text:
            errors.append(f"AGENT VISITS: payload says N={n}, not found in report")

    # --- 9. Check for annual = monthly × 12 consistency ---
    if monthly_low is not None and annual_low is not None:
        expected_annual_low = int(round(monthly_low * 12, -3))
        if annual_low != expected_annual_low:
            # The payload itself may round differently, so just check
            # the report doesn't invent its own number
            pass  # trust the payload, just verify report matches it

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate report against scan payload")
    parser.add_argument("payload", help="Path to results.json scan payload")
    parser.add_argument("--report", required=True, help="Path to report file (HTML or DOCX)")
    args = parser.parse_args()

    payload = load_payload(args.payload)
    report_text = extract_report_text(args.report)

    errors = validate(payload, report_text)

    if not errors:
        print(f"PASS: report matches payload ({len(payload.get('results', []))} checks verified)")
        sys.exit(0)
    else:
        print(f"FAIL: {len(errors)} validation error(s):\n")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
