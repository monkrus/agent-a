# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

This repo has **two tracks**:

1. **Agent Failure Audit** (original) — `playbook/`, `scenarios/`, `runners/`,
   `reports/`. A human QA engineer audits a client's LLM agent for failure
   modes, delivers a written report and optional eval suite.

2. **Agent-Accessibility Scanner** (primary, revenue-generating) — `readiness/`.
   A self-serve tool that scans any product page URL and tells a merchant how
   well AI shopping agents can read, extract from, interact with, and stay safe
   on their page. Sold as free score + paid full report via Stripe.

**This repo is the kitchen, not the menu.** Clients see the report, not the
source code, check library, or methodology.

## Critical rules — do not violate

1. **Never commit client data.** Everything under `clients/` (except
   `clients/_template/`) is gitignored and must stay that way.
2. **Never expose the check library or scoring logic to a client deliverable.**
   The report is self-contained. Do not paste check YAML, scorer internals,
   or prompt injection patterns into anything destined for a client.
3. **No secrets in the repo.** API keys, client endpoints, Stripe keys, etc.
   live in `.env` (gitignored) or per-client local files, never in tracked code.
4. **Scan results stay local.** `readiness/.scans/` is gitignored. Never commit
   scan output.

## Product principles — the scanner

These guide every feature decision:

1. **Focus on the merchant's product page.** The scanner answers one question:
   "Am I losing sales because AI agents can't buy from my store?" Everything
   we build serves that question.
2. **Don't try to be everything.** We are not a security tool, not an SEO tool,
   not a bot management platform. We are a readiness scanner for the AI
   shopping era, focused on what the merchant controls: their product pages.
3. **Show, don't tell.** Run a real agent N times, report pass rates, show
   sample answers. A page that returns the right price 3/5 times is a finding
   nobody else catches.
4. **Copy-paste fixes win deals.** Platform-specific code the merchant can
   paste is worth more than a paragraph of advice.
5. **Ship what sells today.** Don't build for hypothetical future markets.
   Double down on what works: agent simulation accuracy, fix quality, rendered
   DOM support.
6. **UNKNOWN is first-class.** Never silently treat an inconclusive result as
   PASS. Disclose it — if we can't verify it, neither can a shopping agent.

## Scanner architecture (readiness/)

```
readiness/
  scan.py              CLI entry point
  app.py               Flask web frontend (port 5000)
  fetch.py             Page fetcher (requests + optional Playwright for rendered DOM)
  shopper.py           Simulated shopping agent (mock or anthropic backend)
  scorers.py           Static probes + shopper grading (16 checks)
  intel.py             Agent intelligence: platform, chat agents, commerce protocols
  fixes.py             Copy-paste fix recipe generator per failing check
  checks/
    shopify-v1.yaml    Check pack (16 checks, weights sum to 100)
  templates/           Flask HTML templates
  .scans/              Scan results (gitignored)
```

## The four check layers

Every check maps to one layer of agent readiness:

1. **Data** — can agents read the page? (JSON-LD, price in HTML, llms.txt, robots.txt)
2. **Extraction** — can agents extract correctly? (shopper simulation, N runs, pass rates)
3. **Interaction** — can agents act on the page? (Add-to-Cart semantics, variant selectors)
4. **Security** — is the page safe from agent manipulation? (prompt injection scan)

## Check IDs and conventions

- Check IDs (RDY-NNN) are stable and never reused — scan results reference them.
- Severity: `critical` / `high` / `medium` / `low` (rubric in playbook/protocol.md).
- Weights in the YAML must sum to 100.
- Every new check needs: scorer in `scorers.py`, entry in YAML, fix in `fixes.py`.

## Env vars (readiness scanner)

- `SHOPPER` — `mock` (default, offline) or `anthropic` (real Claude extraction)
- `SHOPPER_MODEL` — model for extraction (default: `claude-sonnet-4-6`)
- `ANTHROPIC_API_KEY` — required if SHOPPER=anthropic
- `RENDER` — `playwright` enables headless browser fetch (optional, degrades gracefully)
- `SCAN_N` — shopper runs per check (default: 5 web, 10 CLI)
- `STRIPE_SECRET_KEY` / `STRIPE_PRICE_ID` — for paid report checkout

## Common tasks

- **Run a scan (CLI):** `SHOPPER=mock python readiness/scan.py --checks readiness/checks/shopify-v1.yaml --target <url> --n 5`
- **Run the web app:** `cd readiness && flask run` (or `python app.py`)
- **Add a check:** add scorer in `scorers.py`, entry in `shopify-v1.yaml` (rebalance weights to 100), fix in `fixes.py`
- **Enable rendered DOM:** `pip install playwright && playwright install chromium`, then set `RENDER=playwright`

## Layout (legacy audit track)

```
playbook/protocol.md   Six-category failure taxonomy.
scenarios/             Reusable test packs (YAML).
runners/               Scenario runner + adapters + graders.
reports/templates/     Client deliverable skeleton.
clients/               One folder per engagement (GITIGNORED).
```

## When in doubt

If a request would (a) commit client/scan data, (b) leak check logic or
injection patterns into a client deliverable, or (c) put secrets in tracked
files — stop and flag it. Everything else, proceed.
