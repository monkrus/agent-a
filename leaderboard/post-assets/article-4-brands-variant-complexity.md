# AI Shopping Agents Can't Buy Bras, Boots, or Underwear. We Scanned 4 DTC Brands to Prove It.

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a). 26 checks, real Claude extraction, 10 runs per check.*

---

## The thesis

The products most likely to be bought through AI agents are the ones people hate shopping for themselves — bras that require band-and-cup combinations, boots that need half-size precision, underwear you'd rather not browse in public. So we scanned four DTC brands that sell exactly these products.

None scored above 73. One was nearly invisible to agents.

| Brand | Category | Score | Top Issue |
|-------|----------|-------|-----------|
| Rothy's | Shoes  | 73.0 | Every browser flow fails |
| ThirdLove | Bras | 71.0 | No JSON-LD structured data |
| Thursday Boots | Boots | 65.0 | Price extraction 0/10 |
| MeUndies | Underwear | 25.6 | Blocks agents, no structured data |

**Mean: 58.7** — twenty points below our 17-brand benchmark of 79.4.

## What we found

**MeUndies is the least agent-ready brand we've ever scanned.** Score: 25.6. Fifteen checks failed. No JSON-LD. No server-rendered price. Returns 403 to agent user-agents. No semantic Add-to-Cart. Agents can't even identify the product name. A $50-75M brand that might as well not exist to AI shoppers.

**ThirdLove invested in AI but forgot the front door.** In 2025, ThirdLove partnered with Bloomreach to deploy AI personalization across their site. But their product page ships no JSON-LD with price and availability — the single most important signal for AI shopping agents. The irony: their variant selectors actually use semantic HTML (the check most intimates brands fail). They got the hard part right and missed the easy part. One JSON-LD block — 15 lines of code — would fix the critical failure.

**Thursday Boots has the data but agents read it wrong.** Complete JSON-LD, server-rendered prices, open robots.txt. But agents extract the wrong price 10 out of 10 times. The JSON-LD says one price; the page displays another. An agent telling a customer "these boots cost $149" might be off by $50.

**Rothy's is readable but not shoppable.** Every static check passes — JSON-LD, llms.txt, semantic selectors, cart API, sitemap, fast load time. Then every browser flow fails — ATC, checkout, search, navigation, comparison. Agents can read the price, confirm stock, extract the return policy. They just can't pick size 8 and add to cart.

## The pattern

Across all four brands, browser interaction checks had a **5% pass rate**. Static data checks passed at 72%.

These brands built complex, JavaScript-heavy size/fit selection interfaces that work beautifully for humans and defeat agents completely. The products that would benefit most from AI shopping are the ones most hostile to it.

## What would fix this

- **MeUndies (25.6 → ~70):** Add JSON-LD. Server-render the price. Remove the bot-blocking WAF rule. One day of work, score more than doubles.
- **ThirdLove (71.0 → ~85):** Add JSON-LD with price and availability. One code block.
- **Thursday Boots (65.0 → ~80):** Reconcile displayed price with JSON-LD price. Use `<select>` for sizes.
- **Rothy's (73.0 → ~90):** Data layer already works. Fix the ATC interaction flow.

Combined revenue at risk: **$47,000 to $289,000 per month.**

---

*Scanner: [agent-a](https://github.com/monkrus/agent-a) (open source). 26 checks — 16 static, 5 shopper (Claude Sonnet), 5 browser (Playwright). One product page per brand, July 31 2026. Built by [Sergei Stadnik](https://github.com/monkrus).*
