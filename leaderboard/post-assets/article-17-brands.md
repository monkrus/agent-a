# We Scanned 17 DTC Brands for AI Shopping Agent Readiness. The Average Score Was 79.

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a), an open-source agent-accessibility scanner. 17 checks across data, extraction, interaction, and security. Real Claude extraction, 10 runs per check.*

---

## The experiment

AI shopping agents are here. ChatGPT, Perplexity, Claude — they browse product pages, extract prices, compare options, and attempt to add items to cart. But most e-commerce sites were built for human eyes and human clicks. We wanted to know: how ready are the biggest DTC Shopify brands for this shift?

We picked 17 well-known direct-to-consumer brands across fashion, beauty, home, and wellness. We ran each product page through [agent-a](https://github.com/monkrus/agent-a), an open-source scanner that tests 17 dimensions of agent readiness — from structured data and price extraction to Add-to-Cart flows and prompt injection defense. Every extraction check ran 10 times with real Claude to measure consistency, not just one-shot correctness.

## The leaderboard

| Rank | Brand | Score | Top Issue |
|------|-------|-------|-----------|
| 1 | Kylie Cosmetics | 100.0 | None |
| 2 | Framebridge | 96.2 | Shipping answer inconsistency |
| 3 | Away | 94.7 | Add-to-Cart flow |
| 4 | Liquid I.V. | 92.0 | llms.txt content incomplete |
| 5 | UNTUCKit | 89.0 | Add-to-Cart flow |
| 6 | SKIMS | 87.0 | Shipping answer inconsistency |
| 7 | Harry's | 85.0 | Return policy unreachable |
| 8 | Sunday Riley | 79.5 | Return policy unreachable |
| 9 | Warby Parker | 78.5 | Blocked by robots.txt |
| 10 | Tuft & Needle | 77.0 | Blocked by robots.txt |
| 11 | Fenty Beauty | 74.0 | Price extraction failure |
| 12 | Olaplex | 72.5 | Price extraction failure |
| 13 | Casper | 71.0 | Price extraction failure |
| 13 | Everlane | 71.0 | Price extraction failure |
| 15 | Purple | 69.6 | Price extraction failure |
| 16 | Dollar Shave Club | 66.1 | Missing JSON-LD structured data |
| 17 | Alo Yoga | 46.7 | Missing JSON-LD, no server-rendered price |

**Mean: 79.4 | Median: 78.5**

Only 4 brands scored above 90. Three scored below 70. The range — 46.7 to 100.0 — shows how much variance exists even among well-funded Shopify stores.

## The five findings that matter

### 1. Add-to-Cart is the hardest step for agents

The Add-to-Cart browser flow (RDY-017) had the lowest pass rate of any check: **23%** across brands where it could be tested. Ten out of 17 brands failed it outright. Agents can read your page, extract your price, identify your product — and then get stuck trying to actually buy it.

The culprit is almost always variant selectors. Custom JavaScript size pickers, color swatches built with `<div>` elements instead of `<select>`, two-step selectors where clicking one option reveals another — these patterns work for humans but are opaque to agents that navigate by DOM semantics.

### 2. Shipping is the question agents can't answer consistently

**RDY-010 (consistent shipping answer) failed for 47% of brands.** Even when agents could find shipping information, they disagreed with themselves across runs. A page might say "Free shipping on orders over $75" in one section and "Standard shipping: 5-7 business days, $5.99" in another. Humans reconcile these; agents pick one or the other randomly.

By contrast, return policy extraction (RDY-009) had a **100% pass rate** — every brand's return window was extracted consistently across all runs. The difference: return policies tend to be stated once, clearly, in a single location.

### 3. Price extraction fails when structured data conflicts with page content

Six brands failed price extraction (RDY-006). In every case, the root cause was the same: the price in JSON-LD didn't match what the page visually displayed. A product might list $1,599 in structured data but show "$999 sale price" prominently on the page. Agents extract the visible price; the ground truth is the structured data price. Neither is "wrong," but the inconsistency means agents report incorrect prices to shoppers.

Purple is the clearest example: 0/10 extraction runs matched the ground truth price of $1,599, because agents consistently extracted the promotional price shown on the page instead.

### 4. Variant selectors are the most common static failure

**9 out of 17 brands** use non-semantic JavaScript widgets for size and color selection (RDY-015, 47% pass rate). These custom components — built with `<div>`, `<span>`, or framework-specific elements — look right to humans but give agents nothing to grab onto. A `<select>` element with `<option>` children is instantly parseable. A `<div class="swatch-element" data-value="M">` requires site-specific interpretation.

### 5. Security is a non-issue (for now)

Prompt injection detection (RDY-016) passed for **100% of brands**. No hidden text attempting to manipulate agent behavior was found on any product page. This is good news, but worth monitoring as agent traffic grows and the incentive to manipulate agent responses increases.

## Three tiers of readiness

**Tier A (90+): Agent-ready.** Kylie Cosmetics, Framebridge, Away, Liquid I.V. These brands have clean structured data, consistent extraction, and minimal interaction barriers. An AI agent can read, understand, and (mostly) act on their product pages.

**Tier B (70–89): Readable but not shoppable.** UNTUCKit, SKIMS, Harry's, Sunday Riley, Warby Parker, Tuft & Needle, Fenty Beauty, Olaplex, Casper, Everlane. Agents can extract product information but hit walls when trying to complete purchase actions. The data layer works; the interaction layer doesn't.

**Tier C (below 70): Partially invisible.** Purple, Dollar Shave Club, Alo Yoga. These brands have structural data issues — missing JSON-LD, conflicting prices, JS-only rendering — that make even basic extraction unreliable. Alo Yoga scored lowest (46.7) because it ships no JSON-LD and renders prices entirely in client-side JavaScript, making the product invisible to agents that don't execute JS.

## What the best brands do differently

Kylie Cosmetics scored 100 — the only perfect score. What sets it apart isn't complexity; it's completeness. Its product page has:
- Complete JSON-LD with correct price and availability
- Server-rendered prices in HTML (no JS dependency)
- Semantic `<select>` elements for variants
- Clean robots.txt that doesn't block agents
- Consistent extraction across all 10 runs for every check

No single element is remarkable. The remarkable thing is that nothing is missing.

## What this means

The DTC brands that will capture AI-agent-driven commerce aren't necessarily building new technology. They're doing the basics completely: structured data that matches visible prices, semantic HTML for interactive elements, and consistent content that agents extract the same way every time.

The average score of 79.4 means most brands are readable to agents but not shoppable. The gap between "an agent can tell me the price" and "an agent can buy it for me" is where revenue will be won or lost as agent-referred traffic grows.

---

## Methodology

- **Scanner:** [agent-a](https://github.com/monkrus/agent-a) (open source)
- **Checks:** 17 checks across 4 layers — data (can agents find the page?), extraction (can they read it correctly?), interaction (can they act on it?), security (is it safe from manipulation?)
- **Extraction model:** Claude claude-sonnet-4-6, 10 runs per check
- **Scope:** One product page per brand (not full-site audit)
- **Date:** July 2026
- **Brands:** Selected from well-known Shopify-powered DTC brands across fashion, beauty, home, wellness, and personal care

Check definitions, weights, and scoring logic are open source at [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a).

---

*Built by [Sergei Stadnik](https://github.com/monkrus). Scan your store at agent-a.com.*
