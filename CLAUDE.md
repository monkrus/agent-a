# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

**Agent-Accessibility Scanner** — `readiness/`. A self-serve tool that scans
any product page URL and tells a merchant how well AI shopping agents can read,
extract from, interact with, and stay safe on their page.

Supporting code: `scenarios/` (reusable test packs), `runners/` (scenario
runner + adapters).

Business materials (playbook, report templates, client template) live in a
separate private repo (`agent-a-private/`).

## Critical rules — do not violate

1. **Never commit client data.** Everything under `clients/` is gitignored
   and must stay that way.
2. **Keep paid content in agent-a-private.** Fix recipes (the full
   `generate_fix` implementations), report templates, and client materials
   belong in the private repo. The public `fixes.py` is a stub that returns
   placeholders. Do not paste full fix recipes into the public repo.
3. **No secrets in the repo.** API keys, client endpoints, Stripe keys, etc.
   live in `.env` (gitignored) or per-client local files, never in tracked code.
4. **Scan results stay local.** `readiness/.scans/` is gitignored. Never commit
   scan output.

5. **Never assert a root cause you did not observe.** A FAIL verdict tells you
   *what* failed, never *why*. Before writing any causal explanation (in fix
   text, reports, commit messages, or comments), quote the specific evidence:
   the page substring, the log line, the payload field. If you don't have the
   evidence in front of you, write "cause not yet determined — candidates: X, Y"
   and list what would distinguish them. A plausible explanation stated
   confidently is worse than no explanation.
   *Origin: RDY-007 was blamed on JSON-LD when the page's visible "Out stock"
   text was the actual cause. The fix text was wrong in a client report.*
6. **Never type a number — copy it or compute it.** Every figure in any
   document (report, README, commit message, comment) must come from one of:
   (a) verbatim copy from tool/scan output visible in your context,
   (b) a calculation you show inline, or (c) an explicitly labeled estimate
   ("~", "assumed"). If you find yourself writing a number from memory of what
   it "should be," stop and re-read the source. Revenue figures in reports come
   only from `format_impact()` output — its "Derivation" block exists precisely
   so you can copy verbatim.
   *Origin: the Lola Luna docx stated 280,000 visits / 51% fail / $86K–$515K
   annual. The payload said 296,800 / 44% / $45K–$272K. Only one of four
   numbers was copied; three were invented.*
7. **Run the validator before calling any report final.**
   `python readiness/validate_report.py <payload.json> --report <report>` must
   exit 0. This is a gate, not a suggestion — same status as the test suite.
   If the validator flags a number, fix the report, never the payload.

**Intentionally public:** Check YAML (IDs, weights, descriptions), scoring
logic in `scorers.py`, prompt-injection detection patterns, and the scanner
framework code. These are portfolio-value open source.

## Scanner architecture (readiness/)

```
readiness/
  scan.py              CLI entry point
  app.py               Flask web frontend (port 5000)
  fetch.py             Page fetcher (requests + optional Playwright for rendered DOM)
  shopper.py           Simulated shopping agent (mock or anthropic backend)
  scorers.py           Static probes + shopper grading
  intel.py             Agent intelligence: platform, chat agents, commerce protocols
  fixes.py             Fix recipe stub (full recipes in agent-a-private)
  brief.py             One-page HTML brief for a single scan run (score dial,
                        layer bars, verdict grid, top findings, revenue box)
  batch.py             Batch scan CLI (python -m readiness.batch targets.txt)
  leaderboard.py       Leaderboard export (python -m readiness.leaderboard)
  og_image.py          OG image generator for shareable results
  validate_report.py   Report-vs-payload validator (gate for client reports)
  checks/
    shopify-v1.yaml    Check pack (weights sum to 100)
  templates/           Flask HTML templates
  .scans/              Scan results (gitignored)
```

## The six check categories

Every check maps to one category of agent readiness (40 checks total: 30 static + 5 shopper + 5 browser):

1. **Data** — can agents read and find the page? (JSON-LD, price in HTML, llms.txt, robots.txt, policy, JS ratio, sitemap, contradictory availability)
2. **Extraction** — can agents extract correctly? (shopper simulation, N runs, pass rates — price, availability, product name, return window, shipping)
3. **Interaction** — can agents act on the page? (ATC semantics, variant selectors, browser flows, checkout, guest checkout, cart API, x402 wallet)
4. **Security & Trust** — is the page safe from agent manipulation? (prompt injection, UGC injection, cart rate limiting, checkout bot challenge, admin exposure)
5. **Resilience** — does the page hold up under agent traffic? (page load time, multi-UA agent blocking)
6. **Protocol Discovery** — does the site advertise agent capabilities? (MCP, OAuth, markdown negotiation, A2A, Auth.md, Link headers, DNS-AID, Agent Skills/WebMCP/UCP/ACP)

## Check IDs and conventions

- Check IDs (RDY-NNN) are stable and never reused — scan results reference them.
- Severity: `critical` / `high` / `medium` / `low`.
- Weights in the YAML must sum to 100.
- Every new check needs: scorer in `scorers.py`, entry in YAML, fix in `fixes.py`.

## Env vars (readiness scanner)

- `SHOPPER` — `mock` (default, offline) or `anthropic` (real Claude extraction)
- `SHOPPER_MODEL` — model for extraction (default: `claude-sonnet-4-6`)
- `ANTHROPIC_API_KEY` — required if SHOPPER=anthropic
- `RENDER` — `playwright` enables headless browser fetch (optional, degrades gracefully)
- `SCAN_N` — shopper runs per check (default: 5 web, 10 CLI)
- `STRIPE_SECRET_KEY` / `STRIPE_PRICE_ID` — for paid report checkout
- `DEV_MODE` — set to `true` to enable demo unlock without Stripe (never in production)
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` — for emailing reports after purchase
- `FROM_EMAIL` — sender address (defaults to SMTP_USER)

## Common tasks

- **Run a scan (CLI):** `SHOPPER=mock python readiness/scan.py --checks readiness/checks/shopify-v1.yaml --target <url> --n 5`
- **Generate a brief for a run:** add `--brief` to the scan command above (writes `<out>/brief.html`), or `python -m readiness.brief <out>/results.json`. Gate it the same way as any client report: `python readiness/validate_report.py <out>/results.json --report <out>/brief.html`.
- **Run the web app:** `cd readiness && python app.py`
- **Batch scan:** `python -m readiness.batch targets.txt`
- **Generate leaderboard:** `python -m readiness.leaderboard`
- **Add a check:** add scorer in `scorers.py`, entry in `shopify-v1.yaml` (rebalance weights to 100), fix recipe in `agent-a-private/fixes.py`
- **Enable rendered DOM:** `pip install playwright && playwright install chromium`, then set `RENDER=playwright`

## Review discipline (when asked to check or double-check work)

A review that reads the document and nods is worthless — you share priors with
whoever wrote it, so what looks plausible to them looks plausible to you.
Reviews must be procedural:

- **Recompute every derived number.** Annual vs monthly×12, percentages vs
  their numerators, totals vs their parts. Use the bash tool and actually run
  the arithmetic; never eyeball it.
- **Diff against the source, not your memory.** If the document claims to
  reflect a scan, a page, or a file, open that artifact and compare
  claim-by-claim. If the source isn't available, say so explicitly and list
  which claims are therefore unchecked — do not silently treat them as fine.
- **Fetch independent evidence for causal claims.** For any "X happened
  because Y" statement, find the observation that supports Y. If the check
  data doesn't record which signal drove the result, the causal claim is
  unverifiable — flag it, don't confirm it.
- **Assume at least one error exists and hunt for it.** "Looks good" is not a
  finding. A completed review names either the errors found or the specific
  checks performed that came back clean.
- **End every review with a two-column list:** VERIFIED (with method) and
  NOT VERIFIED (with what it would take). Anything not in the first column
  belongs in the second — there is no third column.

## Report-writing pipeline (client-facing documents)

1. Generate scan payload via `scan.py` — this is the single source of truth.
2. Write prose around the payload. Quote numbers per rule 6. For every
   diagnosis, cite the evidence per rule 5; anything unobserved goes in an
   explicit "Not verified" section, never in fix text as fact.
3. Gate: `validate_report.py --report` exits 0.
4. Gate: the review discipline above, as a separate pass with fresh context
   (new session or subagent — do not review in the same context that wrote it).
5. Only then is the document deliverable.

## When in doubt

If a request would (a) commit client/scan data, (b) put full fix recipes
or report templates into the public repo, or (c) put secrets in tracked
files — stop and flag it. Everything else, proceed.
