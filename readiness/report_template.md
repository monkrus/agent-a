# Agent Readiness Report — {{TARGET}}

**Prepared by:** Sergei · **Date:** {{DATE}} · **Pack:** {{PACK}} {{VERSION}}
**What this measures:** how well this page survives an AI shopping agent
(ChatGPT / Gemini / agent checkout) reading it to find price, availability,
identity, and policies. Scores reflect behavior across {{N}} runs, not single
observations.

---

## FREE TIER  (shown publicly / pre-purchase)

### Agent Readiness Score: {{SCORE}} / 100

> {{HEADLINE}}

| | |
|---|---|
| Critical failures | {{n_critical}} |
| Total checks failing | {{n_fail}} |
| Inconclusive (need access) | {{n_unknown}} |

*The full per-check breakdown, reproduction, and fixes are in the paid report.*

---

## PAID TIER  (full deliverable — do not expose above this line for free)

### Findings (ordered by severity)

> Each check is independently reproducible. Shopper checks report a pass RATE
> across {{N}} runs; a critical check below 100% is a critical finding.

#### {{CHECK-ID}} — {{title}} · **{{SEVERITY}}** · {{verdict}}
- **Type:** {{static | shopper}} | **Category:** {{category}}
- **Result:** {{pass_rate or detail}}
- **What it means:** {{plain-language consequence — e.g. "agents will quote the
  wrong price or skip your product"}}
- **Evidence:** {{static detail, or sample agent answers}}
- **Fix:** {{fix}}

_(repeat per check, criticals first)_

### Inconclusive checks
Checks that could not be decided without deeper access (e.g. robots.txt on a
local capture, JS-rendered content). Disclosed, never assumed safe.

- {{CHECK-ID}} — {{why}}

### What this scan did NOT cover
- Checkout-flow completion (agent add-to-cart → purchase) — separate engagement.
- Multi-variant / multi-currency pages.
- AP2 / ACP agent-checkout exposure — available as an add-on (you implemented
  AP2 end-to-end; this is the differentiated upsell).

### Next steps
1. Fix the {{n_critical}} critical issue(s) — these are the ones that lose the
   agent sale silently.
2. Re-scan to confirm (re-scans cite the same pack version for a clean delta).
3. Optional: roll readiness scanning across your full catalog (per-store / per-PM
   subscription) instead of a single page.

---

## Run conditions
Target {{TARGET}}, pack {{PACK}} {{VERSION}}, shopper backend {{SHOPPER}},
{{N}} runs per shopper check, scored {{DATE}}.
Score = weighted pass rate over checks that produced a verdict; inconclusive
checks excluded from the score and listed above.
