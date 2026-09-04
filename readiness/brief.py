#!/usr/bin/env python3
"""
brief.py — one-page, self-contained HTML brief for a single scan run.

Renders a compact, visually designed summary of one `results.json` payload:
score dial, layer bars, verdict grid, top findings, revenue box. Every number
comes straight from the payload — nothing is invented here (repo rule 6) and
nothing is diagnosed beyond what the check's own `detail` string says
(repo rule 5).

Pure stdlib. Pillow (for an optional PNG hero image, via og_image.generate)
is imported lazily and the brief degrades gracefully if it isn't installed,
matching the pattern already used for Playwright in fetch.py.

Usage:
  python -m readiness.brief path/to/results.json [--out path/to/brief.html] [--teaser]

Library usage:
  from readiness import brief
  html = brief.render(payload, mode="full")
  brief.write(payload, pathlib.Path("brief.html"))
"""
from __future__ import annotations

import argparse
import base64
import html as _html
import pathlib
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og_image  # noqa: E402

# ---- design tokens (copied from readiness/static/style.css :root) ----------
BG = "#0a0a0f"
SURFACE = "#141419"
BORDER = "#23232d"
TEXT = "#e4e4e7"
MUTED = "#8b8b96"
ACCENT = "#6366f1"
GREEN = "#22c55e"
YELLOW = "#eab308"
RED = "#ef4444"

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}

LAYER_ORDER = ["data", "extraction", "interaction", "security"]
LAYER_LABELS = {
    "data": "Data",
    "extraction": "Extraction",
    "interaction": "Interaction",
    "security": "Security & Trust",
}

ALL_CHECK_IDS_HINT = 40  # informational only — never used to compute anything


def _esc(value) -> str:
    return _html.escape(str(value), quote=True)


def _score_color(score) -> str:
    """Hex color for a 0-100 score, same thresholds as og_image._score_color."""
    if score is None:
        return MUTED
    if score >= 80:
        return GREEN
    if score >= 50:
        return YELLOW
    return RED


def _verdict_color(verdict: str) -> str:
    return {"PASS": GREEN, "FAIL": RED, "UNKNOWN": MUTED}.get(verdict, MUTED)


def _domain(target: str) -> str:
    parsed = urlparse(target)
    d = parsed.hostname or target
    if d and d.startswith("www."):
        d = d[4:]
    return d or target


def _hero_data_uri(payload: dict) -> str | None:
    """Best-effort PNG hero via og_image.generate(). None if Pillow is unavailable
    or generation fails for any reason — the HTML/CSS score dial is the fallback
    and always renders regardless of this."""
    try:
        png_bytes = og_image.generate(payload)
    except Exception:
        return None
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _score_dial_svg(score, margin) -> str:
    """CSS/SVG score dial — no external dependency, always renders."""
    color = _score_color(score)
    score_str = "N/A" if score is None else str(score)
    pct = 0 if score is None else max(0.0, min(100.0, float(score)))
    # Circumference for r=52 circle: 2*pi*52 ≈ 326.7
    r = 52
    circumference = 2 * 3.14159265 * r
    dash = circumference * pct / 100
    margin_str = f" ± {_esc(margin)}" if margin is not None else ""
    return f"""
    <div class="score-dial">
      <svg width="130" height="130" viewBox="0 0 130 130">
        <circle cx="65" cy="65" r="{r}" fill="none" stroke="{BORDER}" stroke-width="10"/>
        <circle cx="65" cy="65" r="{r}" fill="none" stroke="{color}" stroke-width="10"
                stroke-dasharray="{dash:.1f} {circumference:.1f}"
                stroke-linecap="round" transform="rotate(-90 65 65)"/>
        <text x="65" y="60" text-anchor="middle" font-size="30" font-weight="700"
              fill="{color}" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">{_esc(score_str)}</text>
        <text x="65" y="82" text-anchor="middle" font-size="12" fill="{MUTED}"
              font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">/ 100{margin_str}</text>
      </svg>
    </div>"""


def _layer_bars_html(results: list[dict]) -> str:
    scores = og_image.layer_scores(results)
    rows = []
    for layer in LAYER_ORDER:
        if layer not in scores:
            continue
        pct = scores[layer]
        color = _score_color(pct)
        label = LAYER_LABELS.get(layer, layer.title())
        rows.append(f"""
        <div class="layer-row">
          <span class="layer-label">{_esc(label)}</span>
          <div class="layer-track"><div class="layer-fill" style="width:{pct}%;background:{color}"></div></div>
          <span class="layer-pct">{pct}%</span>
        </div>""")
    return "\n".join(rows)


def _verdict_strip_html(results: list[dict]) -> tuple[str, int, int, int]:
    pass_n = sum(1 for r in results if r.get("verdict") == "PASS")
    fail_n = sum(1 for r in results if r.get("verdict") == "FAIL")
    unk_n = sum(1 for r in results if r.get("verdict") == "UNKNOWN")
    html = f"""
    <div class="verdict-strip">
      <div class="verdict-cell"><span class="verdict-num" style="color:{GREEN}">{pass_n}</span><span class="verdict-label">PASS</span></div>
      <div class="verdict-cell"><span class="verdict-num" style="color:{RED}">{fail_n}</span><span class="verdict-label">FAIL</span></div>
      <div class="verdict-cell"><span class="verdict-num" style="color:{MUTED}">{unk_n}</span><span class="verdict-label">UNKNOWN</span></div>
    </div>"""
    return html, pass_n, fail_n, unk_n


def _check_grid_html(results: list[dict]) -> str:
    """Every check ID, with its verdict and pass_rate rendered as *visible text*
    (not just in a title= tooltip) so validate_report.py's substring checks find
    them. See CLAUDE.md rule 7 — this is the piece that has to stay validator-clean."""
    chips = []
    for r in results:
        cid = _esc(r.get("id", "???"))
        verdict = r.get("verdict", "UNKNOWN")
        color = _verdict_color(verdict)
        title = _esc(r.get("title", ""))
        detail = _esc(r.get("detail", ""))
        rate = r.get("pass_rate")
        rate_html = f' <span class="chip-rate">({_esc(rate)})</span>' if rate else ""
        chips.append(f"""
        <div class="chip" style="border-color:{color}" title="{title} — {detail}">
          <span class="chip-id">{cid}</span>
          <span class="chip-verdict" style="color:{color}">{_esc(verdict)}</span>{rate_html}
        </div>""")
    return "\n".join(chips)


def _top_findings_html(results: list[dict], limit: int) -> str:
    """FAIL/UNKNOWN checks, worst severity first. Gated checks (access blocked —
    they were skipped, not measured) are excluded from ranking so a blocked scan
    doesn't get presented as if 30+ checks had failed."""
    candidates = [r for r in results
                  if r.get("verdict") in ("FAIL", "UNKNOWN") and not r.get("gated")]
    candidates.sort(key=lambda r: SEV_RANK.get(r.get("severity_if_fail"), 4))
    rows = []
    for r in candidates[:limit]:
        cid = _esc(r.get("id", "???"))
        title = _esc(r.get("title", ""))
        sev = _esc(r.get("severity_if_fail") or "medium")
        verdict = r.get("verdict")
        color = _verdict_color(verdict)
        detail = _esc(r.get("detail", ""))
        rate = r.get("pass_rate")
        rate_html = f'<span class="finding-rate">{_esc(rate)}</span>' if rate else ""
        rows.append(f"""
        <div class="finding" style="border-left-color:{color}">
          <div class="finding-head">
            <span class="chip-id">{cid}</span>
            <span class="finding-title">{title}</span>
            <span class="sev sev-{sev}">{sev}</span>
            <span class="verdict-tag" style="color:{color}">{_esc(verdict)}</span>
            {rate_html}
          </div>
          <div class="finding-detail">{detail}</div>
        </div>""")
    if not rows:
        return '<p class="muted">No failing or inconclusive checks — page reads cleanly to agents.</p>'
    return "\n".join(rows)


def _roadmap_html(roadmap: list[dict]) -> str:
    if not roadmap:
        return ""
    rows = []
    for item in roadmap:
        sev = _esc(item.get("severity") or "medium")
        rows.append(f"""
        <div class="roadmap-row">
          <span class="sev sev-{sev}">{sev}</span>
          <span class="roadmap-fix">{_esc(item.get("fix", ""))}</span>
          <span class="roadmap-points">+{_esc(item.get("points"))} pts</span>
        </div>""")
    return f"""
    <div class="section">
      <h2>Score roadmap</h2>
      <p class="muted small">Points recoverable per fix (weight × failure depth), highest first.</p>
      {"".join(rows)}
    </div>"""


def _access_banner_html(gated_count: int) -> str:
    return f"""
    <div class="banner banner-gated">
      <strong>ACCESS BLOCKED</strong> — {gated_count} check(s) were skipped because
      agents can't reach the page. Fix access first; the checks below reflect only
      what could actually be measured.
    </div>"""


def _revenue_box_html(impact: dict) -> str:
    if not impact:
        return ""
    monthly = impact.get("estimated_monthly_loss", {})
    annual = impact.get("estimated_annual_loss", {})
    m_low, m_high = monthly.get("low"), monthly.get("high")
    a_low, a_high = annual.get("low"), annual.get("high")
    fail_rate = impact.get("agent_failure_rate")
    visits = impact.get("monthly_visits_assumed")
    derivation = impact.get("derivation", {})
    assumptions = impact.get("assumptions", [])
    assumptions_html = "".join(f"<li>{_esc(a)}</li>" for a in assumptions)
    fail_pct = f"{fail_rate:.0%}" if fail_rate is not None else "N/A"
    return f"""
    <div class="section revenue-box">
      <h2>Estimated revenue at risk <span class="muted small">(estimate — not measured)</span></h2>
      <div class="revenue-figures">
        <div><span class="revenue-label">Monthly</span><span class="revenue-value">${m_low:,} – ${m_high:,}</span></div>
        <div><span class="revenue-label">Annual</span><span class="revenue-value">${a_low:,} – ${a_high:,}</span></div>
      </div>
      <p class="small">Agent failure rate: <strong>{fail_pct}</strong> ·
         assumes <strong>{visits:,}</strong> monthly product-page visits.</p>
      <p class="small muted">{_esc(derivation.get("formula", ""))}</p>
      <ul class="small muted assumptions">{assumptions_html}</ul>
    </div>"""


_CSS = f"""
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      background: {BG}; color: {TEXT}; line-height: 1.5; padding: 24px;
    }}
    .brief {{ max-width: 820px; margin: 0 auto; }}
    .header {{ display: flex; justify-content: space-between; align-items: flex-start;
               border-bottom: 1px solid {BORDER}; padding-bottom: 16px; margin-bottom: 20px; }}
    .header h1 {{ font-size: 1.4rem; }}
    .header .meta {{ color: {MUTED}; font-size: 0.82rem; margin-top: 4px; }}
    .hero-img {{ width: 100%; max-width: 600px; border-radius: 8px; border: 1px solid {BORDER};
                 margin-bottom: 20px; display: block; }}
    .score-row {{ display: flex; align-items: center; gap: 24px; margin-bottom: 20px; }}
    .headline {{ font-size: 1rem; color: {TEXT}; }}
    .section {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
                padding: 16px 18px; margin-bottom: 16px; }}
    .section h2 {{ font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.04em;
                   color: {MUTED}; margin-bottom: 10px; }}
    .banner {{ padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 0.9rem; }}
    .banner-gated {{ background: rgba(239,68,68,0.12); border: 1px solid {RED}; color: {TEXT}; }}
    .layer-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
    .layer-label {{ width: 130px; font-size: 0.85rem; }}
    .layer-track {{ flex: 1; height: 10px; background: {BG}; border-radius: 5px; overflow: hidden; }}
    .layer-fill {{ height: 100%; border-radius: 5px; }}
    .layer-pct {{ width: 44px; text-align: right; font-size: 0.82rem; color: {MUTED}; }}
    .verdict-strip {{ display: flex; gap: 28px; }}
    .verdict-cell {{ text-align: center; }}
    .verdict-num {{ display: block; font-size: 1.6rem; font-weight: 700; }}
    .verdict-label {{ font-size: 0.72rem; color: {MUTED}; letter-spacing: 0.05em; }}
    .check-grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .chip {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
             font-size: 0.72rem; display: flex; align-items: center; gap: 4px;
             background: {BG}; }}
    .chip-id {{ color: {MUTED}; }}
    .chip-rate {{ color: {MUTED}; }}
    .finding {{ border-left: 3px solid {BORDER}; padding: 8px 12px; margin-bottom: 10px; }}
    .finding-head {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 0.85rem; }}
    .finding-title {{ font-weight: 600; }}
    .finding-detail {{ font-size: 0.8rem; color: {MUTED}; margin-top: 4px; }}
    .finding-rate {{ color: {MUTED}; font-size: 0.78rem; }}
    .sev {{ font-size: 0.68rem; text-transform: uppercase; padding: 1px 6px; border-radius: 4px; }}
    .sev-critical {{ background: rgba(239,68,68,0.18); color: {RED}; }}
    .sev-high {{ background: rgba(249,115,22,0.18); color: #f97316; }}
    .sev-medium {{ background: rgba(234,179,8,0.18); color: {YELLOW}; }}
    .sev-low {{ background: rgba(139,139,150,0.18); color: {MUTED}; }}
    .roadmap-row {{ display: flex; align-items: center; gap: 10px; padding: 6px 0;
                    border-top: 1px solid {BORDER}; font-size: 0.85rem; }}
    .roadmap-row:first-of-type {{ border-top: none; }}
    .roadmap-fix {{ flex: 1; }}
    .roadmap-points {{ color: {ACCENT}; font-weight: 600; font-size: 0.8rem; }}
    .revenue-box h2 {{ display: flex; justify-content: space-between; }}
    .revenue-figures {{ display: flex; gap: 32px; margin: 8px 0; }}
    .revenue-label {{ display: block; font-size: 0.72rem; color: {MUTED}; }}
    .revenue-value {{ font-size: 1.1rem; font-weight: 700; }}
    .assumptions {{ margin: 6px 0 0 18px; }}
    .muted {{ color: {MUTED}; }}
    .small {{ font-size: 0.78rem; }}
    .footer {{ color: {MUTED}; font-size: 0.72rem; text-align: center; margin-top: 20px;
               border-top: 1px solid {BORDER}; padding-top: 12px; }}
    @media print {{
      body {{ background: white; color: black; padding: 0; }}
      .section {{ background: white; border: 1px solid #ccc; }}
      .chip {{ background: white; }}
    }}
"""


def render(payload: dict, *, mode: str = "full", scan_ref: str = "") -> str:
    """Render a self-contained HTML brief for one scan payload.

    mode="full"   — full brief: header, score, layers, verdicts, check grid,
                     top 5 findings, roadmap, revenue box. This is the mode
                     validate_report.py is run against (every check ID must
                     appear, so the check grid is required for the gate).
    mode="teaser" — header, score, layers, verdicts, top 3 findings only.
                     No check grid, no roadmap. For non-paying visitors.
    """
    meta = payload.get("meta", {})
    results = payload.get("results", [])
    report = payload.get("report", {})
    impact = payload.get("impact", {})

    domain = _domain(meta.get("target", ""))
    gated_results = [r for r in results if r.get("gated")]

    hero_uri = _hero_data_uri(payload) if mode == "full" else None
    hero_html = f'<img class="hero-img" src="{hero_uri}" alt="Score summary graphic">' if hero_uri else ""

    verdict_html, pass_n, fail_n, unk_n = _verdict_strip_html(results)
    finding_limit = 3 if mode == "teaser" else 5
    findings_html = _top_findings_html(results, finding_limit)

    sections = [hero_html]

    sections.append(f"""
    <div class="header">
      <div>
        <h1>{_esc(domain)}</h1>
        <div class="meta">
          {_esc(meta.get("pack", ""))} {_esc(meta.get("version", ""))} ·
          scanned {_esc(meta.get("timestamp", ""))} ·
          shopper: {_esc(meta.get("shopper", ""))} ({_esc(meta.get("model", ""))}) ·
          N = {_esc(meta.get("n", ""))} agent visits per check
        </div>
      </div>
    </div>""")

    if gated_results:
        sections.append(_access_banner_html(len(gated_results)))

    sections.append(f"""
    <div class="score-row">
      {_score_dial_svg(payload.get("readiness_score"), payload.get("confidence_margin"))}
      <div>
        <div class="headline">{_esc(payload.get("headline", ""))}</div>
      </div>
    </div>""")

    sections.append(f"""
    <div class="section">
      <h2>Readiness by layer</h2>
      {_layer_bars_html(results)}
    </div>""")

    sections.append(f"""
    <div class="section">
      <h2>Checks — {pass_n} pass / {fail_n} fail / {unk_n} unknown</h2>
      {verdict_html}
    </div>""")

    if mode == "full":
        sections.append(f"""
        <div class="section">
          <h2>All checks ({len(results)})</h2>
          <div class="check-grid">
            {_check_grid_html(results)}
          </div>
        </div>""")

    sections.append(f"""
    <div class="section">
      <h2>Top findings</h2>
      {findings_html}
    </div>""")

    if mode == "full":
        sections.append(_roadmap_html(report.get("score_roadmap", [])))
        sections.append(_revenue_box_html(impact))

    ref = _esc(scan_ref or meta.get("target", ""))
    sections.append(f"""
    <div class="footer">
      agent-a · agent-accessibility scanner · brief for {ref} ·
      figures copied verbatim from results.json
    </div>""")

    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agent Readiness Brief — {_esc(domain)}</title>
  <style>{_CSS}</style>
</head>
<body>
  <div class="brief">
    {body}
  </div>
</body>
</html>"""


def write(payload: dict, out_path: pathlib.Path, *, mode: str = "full",
          scan_ref: str = "") -> pathlib.Path:
    """Render and write the brief to out_path. Returns out_path."""
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(payload, mode=mode, scan_ref=scan_ref), encoding="utf-8")
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("payload", help="Path to a results.json scan payload")
    ap.add_argument("--out", default=None, help="Output HTML path (default: <payload dir>/brief.html)")
    ap.add_argument("--teaser", action="store_true", help="Render the teaser (non-paid) mode")
    args = ap.parse_args()

    import json
    payload_path = pathlib.Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    out = pathlib.Path(args.out) if args.out else payload_path.parent / "brief.html"
    mode = "teaser" if args.teaser else "full"
    write(payload, out, mode=mode, scan_ref=str(payload_path))
    print(f"brief -> {out}")


if __name__ == "__main__":
    main()
