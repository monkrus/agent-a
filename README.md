[![Agent Ready](https://img.shields.io/badge/Agent-Ready-22c55e?style=flat-square)](https://agent-a.up.railway.app)
[![Live Scanner](https://img.shields.io/badge/Live-Scanner-3b82f6?style=flat-square)](https://agent-a.up.railway.app)

# agent-a — AI shopping agent readiness scanner

Scan any product page URL and find out how well AI shopping agents can read,
extract from, interact with, and stay safe on it.

AI agents (ChatGPT Shopping, Google Gemini, Perplexity, Amazon Rufus) are becoming
a major sales channel for e-commerce. But most product pages were built for
humans, not machines. This scanner tells merchants what's broken and how to
fix it.

**Live at [agent-a.up.railway.app](https://agent-a.up.railway.app)**

## What it does

Paste a product page URL → get a readiness score (0-100) with per-check
results across six layers:

### Layer 0 — Access gate
- robots.txt not blocking agent user-agents
- Site does not block agent-like traffic (multi-UA: GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot)

### Layer 1 — Can agents READ the page? (Data)
- Product structured data (JSON-LD) present and complete
- Price in server-rendered HTML (not JS-only)
- llms.txt / agent guidance present and well-structured
- Return/refund policy reachable as text
- JS rendering ratio (how much content agents actually see)
- Product description richness (image-vs-text emotional gap analysis)
- Product image alt text (AI agents can't see images — they need descriptive alt text)
- Availability signal consistency (JSON-LD vs visible text)
- Sitemap.xml exists and lists products
- Page responds within agent timeout threshold

### Layer 2 — Can agents EXTRACT correctly? (AI Simulation)
- Agent extracts the correct price (N runs, pass rate)
- Agent determines stock availability
- Agent identifies the correct product name
- Agent gives consistent return window
- Agent gives consistent shipping answer

### Layer 3 — Can agents ACT on the page? (Interaction)
- Add-to-Cart button is semantic and identifiable
- Variant selectors (size/color) use accessible HTML
- Agent can complete Add-to-Cart flow (browser)
- Agent can find product via site search (browser)
- Agent can reach checkout (browser)
- Agent can navigate from homepage to product (browser)
- Agent can find related products (browser)
- Guest checkout available (no login wall)
- Programmatic cart API endpoint available
- x402 / agent wallet compatibility signals

### Layer 4 — Is the page SAFE? (Security & Trust)
- No hidden prompt injection in page content
- No prompt injection in user-generated content (reviews, Q&A)
- Cart API has rate limiting protection
- Checkout has bot challenge protection
- Admin and API paths are not exposed

### Layer 5 — Protocol Discovery
- MCP Server Card (/.well-known/mcp.json)
- OAuth Authorization Server discovery
- Markdown content negotiation (Accept: text/markdown)
- A2A Agent Card (Google protocol, /.well-known/agent.json)
- Auth.md authentication documentation
- Link response headers for agent discovery
- DNS for AI Discovery (DNS-AID) records
- Agent commerce protocols (Skills, WebMCP, UCP, ACP)

### Intel section
- Platform detection (Shopify, WooCommerce, etc.)
- Chat/support agents detected (Gorgias, Gladly, Ada, Zendesk, etc.)
- Commerce protocols (UCP, Shop Pay, Shop Skill, MCP)
- llms.txt protocol and feature parsing

## Two tiers

### Free scan (32 checks, $0)
- Readiness score (0-100)
- 32 structural checks: data, interaction, security, resilience, protocols
- Pass/fail/inconclusive per check with top issues listed
- One free fix recipe for the highest-priority failure
- Competitor head-to-head comparison
- Intel: platform, AI agents, commerce protocols detected
- Shareable results link with OG image
- No API cost, no account, instant

### Deep Agent Audit (42 checks, $49)
Everything in free, plus:
- **5 AI extraction checks** — Claude visits the page 5 times, extracts price, availability, product name, return window, shipping. Shows pass rate, ground truth, sample responses
- **5 browser agent flows** — AI agent tries to: add to cart, search, reach checkout, navigate from homepage, find related products
- **Revenue impact estimate** — monthly/annual dollar range (benchmark-based, not measured from your traffic)
- **Copy-paste fix recipes** for every failing check — Shopify Liquid, config steps, plain-language instructions
- **Full detail** on every check: result, what you're losing, how to fix
- **Save as PDF** — download a clean, print-ready report to share with your dev team
- **Free re-scan coupon** — every paid audit includes a one-time promo code for a free Deep Agent Audit on a different product page

**Safety:** checkout is blocked if browser checks are unavailable (Playwright not installed). Customers never pay for a degraded scan. If a site geo-blocks the scanner, all browser check failures are disclosed with an explanation.

## Features

- **Real-time streaming** — checks stream live as they complete, with layer-by-layer progress
- **Competitor comparison** — paste a competitor URL to see a head-to-head breakdown
- **Shareable results** — `/r/<scan_id>` public scorecard with OG image (1200x630 PNG)
- **Browser agent** — LLM-driven Playwright interaction loop with majority-vote (up to 3 attempts per flow)
- **Geo-block detection** — if all browser checks fail due to site access restrictions, the report explains why
- **Scan counter** — persistent scan count displayed on the homepage
- **Rate limiting** — configurable per-IP scan throttling

## How it works

1. Fetches the product page (raw HTML + optional Playwright rendered DOM)
2. Free tier runs 32 static structural checks (no API cost)
3. Paid tier re-scans with all 42 checks: static + AI shopper + browser flows
4. Shopper checks run N times (default 5) to report **pass rates**, not binary
5. Browser checks use majority-vote (2/3 or better to pass)
6. Computes a weighted readiness score (0-100)

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

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

# Enable browser checks (optional, for interaction flows)
pip install playwright && playwright install chromium
RENDER=playwright SHOPPER=anthropic python readiness/scan.py ...
```

## Env vars

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPPER` | `mock` | `mock` (offline) or `anthropic` (real Claude extraction) |
| `SHOPPER_MODEL` | `claude-sonnet-4-6` | Model for shopper simulation |
| `ANTHROPIC_API_KEY` | - | Required if SHOPPER=anthropic |
| `RENDER` | - | Set to `playwright` for headless browser fetch |
| `SCAN_N` | 5 (web) / 10 (CLI) | Shopper runs per check |
| `BROWSER_ATTEMPTS` | 3 | Browser flow attempts per check (0 to skip) |
| `BROWSER_AGENT_MODEL` | `claude-haiku-4-5-20251001` | Model for browser agent flows |
| `STRIPE_SECRET_KEY` | - | For paid report checkout |
| `STRIPE_PRICE_ID` | - | Stripe Price object for single report |
| `STRIPE_RESCAN_COUPON_ID` | - | Stripe coupon ID for free re-scan promo codes |
| `FLASK_SECRET_KEY` | - | Required in production |
| `SCAN_RATE_LIMIT` | 30 | Seconds between scans per IP |
| `DEV_MODE` | - | Set `true` for demo unlock without Stripe |

## Repo layout

```
readiness/                 The scanner (primary product)
  scan.py                  CLI entry point
  app.py                   Flask web frontend
  batch.py                 Batch scan CLI
  leaderboard.py           Leaderboard export
  fetch.py                 Page fetcher (requests + optional Playwright)
  shopper.py               Simulated shopping agent
  scorers.py               Check probes + grading
  intel.py                 Agent intelligence module
  browser_agent.py         LLM-driven Playwright interaction agent
  impact.py                Revenue-at-risk estimator
  emotional_gap.py         Image-vs-text emotional gap analysis
  emailer.py               Report email delivery
  fixes.py                 Fix recipe loader (loads private recipes via FIXES_MODULE)
  validate_report.py       Report-vs-payload validator
  og_image.py              OG image generator for shareable results
  checks/shopify-v1.yaml   Check pack (42 checks, weights sum to 100)
  templates/               Web frontend templates
  tests/                   Test suite (353+ tests)
  .scans/                  Scan results (gitignored)

scenarios/                 Reusable test scenario packs
runners/                   Scenario runner + adapters
```

## Cost per scan

- **Free scan** (SHOPPER=mock, static only): $0
- **Shopper-only** (SHOPPER=anthropic, no browser): ~$0.05/scan
- **Full scan with browser** (SHOPPER=anthropic + Playwright): ~$0.50-1.00/scan
- Browser vision calls are ~90% of the cost

## Deployment

Deployed on Railway with Nixpacks. See [DEPLOY.md](DEPLOY.md) for setup instructions.

- Gunicorn with 2 workers x 4 threads
- Playwright + Chromium installed at build time
- Persistent volume for scan storage (optional)
- Stripe checkout for paid reports

## Open-core model

The scanner framework, check definitions, scoring methodology, and fix
recipes are **open source** (this repo). Client deliverables and report
templates live in a separate private repository.

| Public (this repo)                | Private                            |
|-----------------------------------|------------------------------------|
| Scanner engine & CLI              | Report templates                   |
| Check pack (IDs, weights, YAML)   | Playbook & client templates        |
| Scoring & grading logic           | Client deliverables                |
| Web frontend                      | Outreach materials                 |
| Fix recipe loader (`fixes.py`)    | Fix recipes (`_fixes_private.py`)  |
| Prompt-injection detection        |                                    |
