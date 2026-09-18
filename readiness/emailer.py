#!/usr/bin/env python3
"""
emailer.py — Send scan reports via email.

Sends the full readiness report (score, per-check details, fix recipes)
as a formatted HTML email via SMTP.

Env vars:
  SMTP_HOST      SMTP server (default: smtp.gmail.com)
  SMTP_PORT      SMTP port (default: 587)
  SMTP_USER      SMTP username / email
  SMTP_PASS      SMTP password or app password
  FROM_EMAIL     Sender address (defaults to SMTP_USER)
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _is_configured() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def _score_color(score: float) -> str:
    if score >= 80:
        return "#22c55e"
    if score >= 50:
        return "#eab308"
    return "#ef4444"


def _verdict_color(verdict: str) -> str:
    return {"PASS": "#22c55e", "FAIL": "#ef4444", "UNKNOWN": "#6b7280"}.get(verdict, "#6b7280")


def _build_html(scan_data: dict, base_url: str = "") -> str:
    """Build an HTML email body from scan data."""
    score = scan_data.get("readiness_score", 0) or 0
    target = scan_data.get("meta", {}).get("target", "")
    headline = scan_data.get("headline", "")
    results = scan_data.get("results", [])
    n = scan_data.get("meta", {}).get("n", 5)
    timestamp = scan_data.get("meta", {}).get("timestamp", "")
    scan_id = scan_data.get("scan_id", "")
    rescan_promo = scan_data.get("meta", {}).get("rescan_promo_code", "")
    color = _score_color(score)
    report_url = f"{base_url}/results/{scan_id}" if base_url and scan_id else ""

    checks_html = ""
    for r in results:
        v = r.get("verdict", "")
        vc = _verdict_color(v)
        title = r.get("title", "")
        detail = r.get("detail", "")
        sev = r.get("severity_if_fail", "")
        fix_recipe = r.get("fix_recipe", "")

        check_html = f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">
            <span style="font-weight:600;color:#374151;">{r.get('id', '')}</span>
            <span style="color:#6b7280;margin-left:4px;">{title}</span>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">
            <span style="color:{vc};font-weight:600;">{v}</span>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;font-size:13px;">
            {sev}
          </td>
        </tr>"""

        if v == "FAIL" and detail:
            check_html += f"""
        <tr>
          <td colspan="3" style="padding:4px 12px 12px 32px;border-bottom:1px solid #e5e7eb;color:#6b7280;font-size:13px;">
            {detail}
          </td>
        </tr>"""

        if v == "FAIL" and fix_recipe:
            escaped = fix_recipe.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            check_html += f"""
        <tr>
          <td colspan="3" style="padding:4px 12px 16px 32px;border-bottom:2px solid #e5e7eb;">
            <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:12px;font-size:13px;">
              <div style="font-weight:600;color:#374151;margin-bottom:6px;">How to fix:</div>
              <pre style="white-space:pre-wrap;word-wrap:break-word;font-family:monospace;font-size:12px;color:#374151;margin:0;">{escaped}</pre>
            </div>
          </td>
        </tr>"""

        checks_html += check_html

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:20px;">
    <div style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

      <!-- Header -->
      <div style="background:#0f0f13;padding:32px;text-align:center;">
        <div style="font-size:48px;font-weight:700;color:{color};">{score:.0f}</div>
        <div style="color:#9ca3af;font-size:14px;margin-top:4px;">/ 100 Agent Readiness Score</div>
        <div style="color:#e5e7eb;font-size:14px;margin-top:12px;">{target}</div>
      </div>

      <!-- Headline -->
      <div style="padding:24px 32px;border-bottom:1px solid #e5e7eb;">
        <p style="margin:0;color:#374151;font-size:15px;">{headline}</p>
        <p style="margin:8px 0 0;color:#9ca3af;font-size:13px;">{n} AI agent visits simulated &middot; {timestamp}</p>
      </div>

      <!-- Check results -->
      <div style="padding:24px 32px;">
        <h2 style="margin:0 0 16px;font-size:18px;color:#111827;">Check Results</h2>
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="border-bottom:2px solid #e5e7eb;">
              <th style="padding:8px 12px;text-align:left;color:#6b7280;font-size:12px;text-transform:uppercase;">Check</th>
              <th style="padding:8px 12px;text-align:center;color:#6b7280;font-size:12px;text-transform:uppercase;">Result</th>
              <th style="padding:8px 12px;text-align:left;color:#6b7280;font-size:12px;text-transform:uppercase;">Severity</th>
            </tr>
          </thead>
          <tbody>
            {checks_html}
          </tbody>
        </table>
      </div>

      <!-- Report link + re-scan -->
      {"" if not report_url else f'''
      <div style="padding:24px 32px;background:#0f0f13;border-top:1px solid #e5e7eb;text-align:center;">
        <p style="margin:0 0 12px;color:#e5e7eb;font-size:14px;font-weight:600;">Your full report is always available at:</p>
        <a href="{report_url}" style="color:#60a5fa;font-size:14px;word-break:break-all;">{report_url}</a>
        <p style="margin:12px 0 0;color:#9ca3af;font-size:13px;">Bookmark this link. After you fix issues, come back and re-scan for free.</p>
      </div>
      '''}

      <!-- Promo code for free re-scan -->
      {"" if not rescan_promo else f'''
      <div style="padding:24px 32px;background:#0a1a0a;border-top:1px solid #22c55e;">
        <p style="margin:0 0 8px;color:#22c55e;font-size:14px;font-weight:600;">Scan another page — on us</p>
        <p style="margin:0 0 12px;color:#9ca3af;font-size:13px;">Use this one-time code at checkout to get a free Deep Agent Audit on a different product page:</p>
        <div style="text-align:center;margin:8px 0;">
          <span style="display:inline-block;padding:8px 16px;background:#1a1a2e;border-radius:6px;font-size:18px;font-weight:700;color:#facc15;letter-spacing:0.05em;">{rescan_promo}</span>
        </div>
      </div>
      '''}

      <!-- Footer -->
      <div style="padding:24px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;">
        <p style="margin:0;color:#6b7280;font-size:13px;">
          This report was generated by the agent-accessibility scanner.
          Questions? Reply to this email or contact sergeigodev@gmail.com
        </p>
      </div>
    </div>
  </div>
</body>
</html>"""


def send_report(to_email: str, scan_data: dict, subject: str | None = None,
                base_url: str = "") -> bool:
    """Send the full scan report to the given email. Returns True on success."""
    if not _is_configured():
        return False

    target = scan_data.get("meta", {}).get("target", "your page")
    score = scan_data.get("readiness_score", 0) or 0

    if not subject:
        subject = f"Agent Readiness Report: {score:.0f}/100 — {target}"

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    from_email = os.environ.get("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    html_body = _build_html(scan_data, base_url=base_url)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True
    except Exception:
        return False
