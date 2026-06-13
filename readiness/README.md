# readiness/ — Agent-Accessibility Scanner

A second track in this repo. The audit track tests **an agent** for failure
modes. This track inverts the system-under-test: it scores **a website** on how
well it survives an AI shopping agent reading it (price, availability, identity,
policies). Same architecture and methodology — different direction of fire.

The audit track stays intact as-is. This is additive.

## Why this exists
Shopping/booking agents (ChatGPT, Gemini, agent checkout via ACP/AP2) are a
real and growing source of traffic. When an agent visits a store it either reads
the page cleanly or silently moves on. Most sites fail invisibly: JS-only
prices, missing structured data, policies buried in PDFs, agents blocked in
robots.txt. Merchants already buy SEO audits; this is the same budget line,
new column ("GEO / agent readiness"). Distribution model = ListingIQ: free
score, paid full report.

## What carries over from the audit track (and what doesn't)
- **Carries over:** the pack/runner/grader/report shape; the core methodology —
  run N times, report a pass RATE not a binary, critical-below-100% = critical
  finding; UNKNOWN disclosed, never assumed safe.
- **Does NOT carry over:** the six agent-failure categories, the agent adapters,
  every agent scenario pack. Those are agent-specific. This track re-implements
  the *shape*, not the content.

## Layout
```
checks/shopify-v1.yaml   The check pack (static + shopper). Versioned like scenarios.
fetch.py                 Adapter: URL or local .html -> normalized page dict.
shopper.py               Simulated shopping agent. SHOPPER=mock|anthropic.
scorers.py               Static probes + shopper grading (correctness | consistency).
scan.py                  CLI runner: fetch once -> run checks -> weighted score 0-100.
app.py                   Flask web app: URL in -> free score -> paid full report (Stripe).
templates/               Jinja2 templates for the web frontend.
static/style.css         Minimal dark-theme stylesheet.
report_template.md       Report skeleton (free-score block + paid full report).
sample_page.html         Offline fixture (deliberately agent-hostile).
requirements.txt         Python dependencies.
.scans/                  Per-scan result JSON (gitignored, like clients/).
```

## Run it

### CLI (single scan, offline smoke test)
```bash
cd readiness
SHOPPER=mock python scan.py --checks checks/shopify-v1.yaml \
    --target sample_page.html --n 10 --out /tmp/scan1
```

### CLI against a real page
```bash
export SHOPPER=anthropic
export ANTHROPIC_API_KEY=sk-...
python scan.py --checks checks/shopify-v1.yaml \
    --target https://store.example/products/the-thing --n 10 --out /tmp/scan1
```

### Web app (the product surface)
```bash
pip install -r requirements.txt
SHOPPER=mock python app.py                    # demo mode, no creds needed
# then open http://localhost:5000
```

For production with Stripe:
```bash
export SHOPPER=anthropic
export ANTHROPIC_API_KEY=sk-...
export STRIPE_SECRET_KEY=sk_live_...
export STRIPE_PRICE_ID=price_...              # one-time $49 price object
export FLASK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

Without `STRIPE_SECRET_KEY`, the "Unlock" button auto-unlocks the report (demo mode).

## Check types
- **static** — deterministic probe of the page (JSON-LD, price-in-HTML,
  robots, policy text, llms.txt). No LLM. Exact.
- **shopper** — the simulated agent gets an extraction task, run N times:
  - `grade: correctness` — answers must match ground truth derived from the page
    (e.g. JSON-LD price). If the page exposes no ground truth, that's UNKNOWN —
    itself a weakness.
  - `grade: consistency` — no ground truth; measures whether the agent agrees
    with *itself* across runs. Disagreement = the page reads ambiguously to
    agents.

## Scoring
Weighted pass rate over checks that produced a verdict (weights in the pack sum
to 100). Shopper pass thresholds are severity-keyed (critical 100%, high 95%,
medium 90%) — same rubric as the audit methodology.

## Validate before expanding (do this first)
Run v1 against ~20 real Shopify / direct-booking pages before adding a single
new check. The distribution of FAILs across real sites tells you which checks
merchants will pay to fix — that ranking, not guesswork, decides what the paid
report leads with and which checks to build next. The public free-score page
(the ListingIQ-style funnel) comes *after* the engine produces useful scores on
real pages, not before.

## Known limitations (be honest in the report)
- No JS rendering: JS-only content reads as absent. That's correct for most
  agents/crawlers, but for JS-heavy targets wire a rendering backend (Apify,
  already used by ListingIQ) into `fetch.py` per engagement.
- `robots`/`llms.txt` only probed for real URLs, not local fixtures.
- Ground-truth derivation is best-effort from structured data; a page with no
  structured data yields more UNKNOWNs (which is, again, a finding).
