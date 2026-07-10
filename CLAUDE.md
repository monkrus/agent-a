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
2. **Never expose the check library or scoring logic to a client deliverable.**
   The report is self-contained. Do not paste check YAML, scorer internals,
   or prompt injection patterns into anything destined for a client.
3. **No secrets in the repo.** API keys, client endpoints, Stripe keys, etc.
   live in `.env` (gitignored) or per-client local files, never in tracked code.
4. **Scan results stay local.** `readiness/.scans/` is gitignored. Never commit
   scan output.

## Scanner architecture (readiness/)

```
readiness/
  scan.py              CLI entry point
  app.py               Flask web frontend (port 5000)
  fetch.py             Page fetcher (requests + optional Playwright for rendered DOM)
  shopper.py           Simulated shopping agent (mock or anthropic backend)
  scorers.py           Static probes + shopper grading
  intel.py             Agent intelligence: platform, chat agents, commerce protocols
  fixes.py             Copy-paste fix recipe generator per failing check
  batch.py             Batch scan CLI (python -m readiness.batch targets.txt)
  leaderboard.py       Leaderboard export (python -m readiness.leaderboard)
  og_image.py          OG image generator for shareable results
  checks/
    shopify-v1.yaml    Check pack (weights sum to 100)
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

## Common tasks

- **Run a scan (CLI):** `SHOPPER=mock python readiness/scan.py --checks readiness/checks/shopify-v1.yaml --target <url> --n 5`
- **Run the web app:** `cd readiness && python app.py`
- **Batch scan:** `python -m readiness.batch targets.txt`
- **Generate leaderboard:** `python -m readiness.leaderboard`
- **Add a check:** add scorer in `scorers.py`, entry in `shopify-v1.yaml` (rebalance weights to 100), fix in `fixes.py`
- **Enable rendered DOM:** `pip install playwright && playwright install chromium`, then set `RENDER=playwright`

## When in doubt

If a request would (a) commit client/scan data, (b) leak check logic or
injection patterns into a client deliverable, or (c) put secrets in tracked
files — stop and flag it. Everything else, proceed.
