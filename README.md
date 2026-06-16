# agent-a — Agent-Accessibility Scanner

Scan any product page URL and find out how well AI shopping agents can read,
extract from, interact with, and stay safe on it.

AI agents (ChatGPT Shopping, Google Gemini, Perplexity, Amazon) are becoming
a major sales channel for e-commerce. But most product pages were built for
humans, not machines. This scanner tells merchants what's broken and gives
them copy-paste fixes.

## What it does

Paste a product page URL → get a readiness score (0–100) with per-check
results across four layers:

### Layer 1 — Can agents READ the page? (Data)
- Product structured data (JSON-LD) present and complete
- Price in server-rendered HTML (not JS-only)
- llms.txt / agent guidance present and well-structured
- robots.txt not blocking agent user-agents
- Return/refund policy reachable as text
- JS rendering ratio (how much content agents actually see)

### Layer 2 — Can agents EXTRACT correctly? (Simulation)
- Agent extracts the correct price (N runs, pass rate)
- Agent determines stock availability
- Agent identifies the correct product name
- Agent gives consistent return window
- Agent gives consistent shipping answer

### Layer 3 — Can agents ACT on the page? (Interaction)
- Add-to-Cart button is semantic and identifiable
- Variant selectors (size/color) use accessible HTML

### Layer 4 — Is the page SAFE? (Security)
- No hidden prompt injection in page content

### Intel section
- Platform detection (Shopify, WooCommerce, etc.)
- Chat/support agents detected (Gladly, Ada, Zendesk, etc.)
- Commerce protocols (UCP, Shop Pay, Shop Skill, MCP)
- llms.txt protocol and feature parsing
- Meta directive analysis (noindex detection)

## How it works

1. Fetches the product page (raw HTML + optional Playwright rendered DOM)
2. Runs 16 checks — 11 static probes + 5 shopper simulations
3. Shopper checks run N times (default 5) to report **pass rates**, not binary
4. Computes a weighted readiness score (0–100)
5. Generates platform-specific copy-paste fix recipes for every failure

## Quick start

```bash
# Install dependencies
pip install flask pyyaml requests python-dotenv anthropic

# Set up env
cp .env.example .env   # add your ANTHROPIC_API_KEY

# Run a scan (CLI, offline mock mode)
SHOPPER=mock python readiness/scan.py \
  --checks readiness/checks/shopify-v1.yaml \
  --target https://example.com/products/some-product \
  --n 5

# Run a scan (CLI, real AI extraction)
SHOPPER=anthropic python readiness/scan.py \
  --checks readiness/checks/shopify-v1.yaml \
  --target https://example.com/products/some-product \
  --n 10

# Run the web app
cd readiness && python app.py
# Open http://localhost:5000

# Enable rendered DOM (optional, for JS-heavy sites)
pip install playwright && playwright install chromium
RENDER=playwright SHOPPER=anthropic python readiness/scan.py ...
```

## Env vars

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPPER` | `mock` | `mock` (offline) or `anthropic` (real Claude extraction) |
| `SHOPPER_MODEL` | `claude-sonnet-4-6` | Model for shopper simulation |
| `ANTHROPIC_API_KEY` | — | Required if SHOPPER=anthropic |
| `RENDER` | — | Set to `playwright` for headless browser fetch |
| `SCAN_N` | 5 (web) / 10 (CLI) | Shopper runs per check |
| `STRIPE_SECRET_KEY` | — | For paid report checkout |
| `STRIPE_PRICE_ID` | — | Stripe Price object for single report |

## Repo layout

```
readiness/                 The scanner (primary product)
  scan.py                  CLI entry point
  app.py                   Flask web frontend
  fetch.py                 Page fetcher (requests + optional Playwright)
  shopper.py               Simulated shopping agent
  scorers.py               16 check probes + grading
  intel.py                 Agent intelligence module
  fixes.py                 Copy-paste fix recipe generator
  checks/shopify-v1.yaml   Check pack (16 checks, weights sum to 100)
  templates/               Web frontend templates
  .scans/                  Scan results (gitignored)

playbook/                  Agent audit methodology (legacy track)
scenarios/                 Reusable test scenario packs
runners/                   Scenario runner + adapters
reports/                   Report templates
clients/                   Per-engagement work (gitignored)
```

## Cost

- ~$0.15/scan with Claude Sonnet
- ~$0.03–0.05/scan with Claude Haiku
- Free with SHOPPER=mock (offline, deterministic-ish)

## Private repo

This is proprietary. Clients receive the scan report, not this codebase.
