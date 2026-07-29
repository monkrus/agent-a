# The Free Scan Tells You What's Broken. The Paid Scan Proves What's Costing You Money.

---

We built two tiers of our agent-readiness scanner. One is free, instant, and runs on raw HTML. The other sends a real AI agent to your product page to try to buy something. Here's why both exist — and why the difference matters.

---

## The free scan: 18 checks, zero cost, 10 seconds

The free scan is a static analysis of your product page. No API calls, no browser automation, no AI model invocations. It fetches your HTML, reads the DOM, and runs 18 checks against it.

It answers the question: **does your page have the right structure for agents?**

- Is there JSON-LD structured data with price and availability?
- Can agents reach your page without being blocked by robots.txt?
- Is there an Add-to-Cart button with semantic HTML?
- Do your variant selectors use `<select>` elements or opaque JS widgets?
- Is there a cart API endpoint agents can call programmatically?
- Does your site have an llms.txt file telling agents where to find things?

For the five browser-agent flows (Add-to-Cart, search, checkout, navigation, product comparison), the free scan uses **static proxies** — it checks whether the right HTML elements exist and infers that agents can probably use them. "You have a search input on your homepage, so agents can probably search your site."

This is useful. It catches the most common failures — missing structured data, JS-only prices, non-semantic size pickers — and it catches them instantly, for free. When we scanned Glossier, Allbirds, Gymshark, Drunk Elephant, and Brooklinen with the free scan, every meaningful issue showed up: broken availability URLs, JS-only variant selectors, missing cart APIs. The free scan found all of it in under 10 seconds per brand.

**But "probably" isn't proof.**

## The paid scan: 23 checks, real AI agent, real evidence

The paid scan keeps all 13 core static checks and replaces the 5 static proxies with 5 real browser-agent flows. It also adds 5 shopper extraction checks. Total: 23 checks.

The difference is fundamental. The free scan looks at your page and says, "This should work." The paid scan sends an AI agent to your page and reports back: "Here's exactly what happened when I tried."

### What the paid scan adds

**5 browser-agent flows (20% of the score):**

An AI agent powered by Claude + Playwright actually visits your page and attempts each flow, multiple times:

| Flow | What the agent tries | Why it matters |
|------|---------------------|----------------|
| Add-to-Cart | Select a variant, click ATC, verify the cart updated | The money step. If this fails, agents can't buy. |
| Site search | Find the search bar, type a query, locate the product in results | How agents discover products they weren't linked to directly. |
| Checkout | After ATC, navigate to the checkout page | Proves the full purchase path is unblocked. |
| Homepage navigation | Start at the homepage, use menus to find the product | Simulates how agents browse without a direct link. |
| Product comparison | Find a related product and navigate to it | Agents comparison-shop. Can they find alternatives on your site? |

Each flow runs multiple times. We majority-vote the results. If the agent succeeds 3 out of 5 times, the flow passes. This filters out noise and surface real, reproducible failures.

**5 shopper extraction checks (26% of the score):**

A real Claude model reads your page and attempts to extract specific facts — price, availability, product name, return window, shipping cost. Each extraction runs 10 times. We grade on two dimensions:

- **Correctness:** Does the extracted price match your JSON-LD price? Does the availability reading match what the page declares?
- **Consistency:** Does the agent give the same answer every time? If it says "free shipping" on 6 runs and "$5.99 shipping" on 4 runs, your page is ambiguous to agents — and that's a readiness failure even if both answers are technically present on the page.

This catches problems the free scan can't see. A page might have perfect structured data (free scan passes) but display a conflicting sale price that confuses agents into extracting the wrong number (paid scan catches it). A size picker might use `<select>` elements (free scan passes) but have a popup that blocks the agent from reaching them (paid scan catches it).

## The numbers: how much more does the paid scan prove?

Here's the weight breakdown:

| Check type | Free scan | Paid scan |
|------------|-----------|-----------|
| Static HTML checks | 100 pts (100%) | 48 pts (48%) |
| Static proxy estimates | 29 pts (included above) | 0 pts (replaced) |
| Browser-agent flows | 0 pts | 20 pts (20%) |
| Shopper extraction | 0 pts | 26 pts (26%) |
| Additional static | 0 pts | 6 pts (6%) |

**46% of the paid scan score comes from actual AI agent behavior.** The free scan is 100% inference from HTML structure.

The free scan can tell you your ATC button looks right. The paid scan can tell you an agent clicked it, saw a popup asking to select a size, couldn't parse the swatch grid, and gave up on step 8.

## When the scores disagree — that's where the money is

We've seen brands score 80+ on the free scan and drop to 65 on the paid scan. The gap is always the same: the HTML structure looks correct, but agents can't actually use it.

Common reasons the paid scan catches failures the free scan misses:

- **Popups and modals** that block interaction (cookie consent, email capture, age gates)
- **Two-step variant selection** where picking a color reveals sizes in a dynamic panel
- **Conflicting price signals** — a sale price on the page vs. full price in JSON-LD
- **Search that requires JavaScript execution** to render results
- **Checkout that redirects through login walls** the agent can't bypass

These are the failures that cost money. An agent that can read your price but can't buy your product is a lost sale. The free scan tells you the foundation is there. The paid scan tells you whether the transaction actually works.

## The funnel: free scan to paid scan to fix

We designed the two tiers as a funnel, not a paywall:

**1. Free scan (you are here):** See your score, see which checks pass and fail. Understand the landscape. Takes 10 seconds, costs nothing. If you score 90+, your page is probably in good shape — the static proxies are reliable at the high end.

**2. Paid scan:** Get the real evidence. See exactly what an AI agent experiences on your page. Get per-check breakdowns with evidence, screenshots, and step-by-step flow traces. Know *why* the agent failed, not just *that* something looks off.

**3. Fix report:** Every failed check comes with a specific, copy-paste fix recipe. Not "improve your structured data" — actual code. The JSON-LD block you need. The `<select>` element that replaces your JS widget. The llms.txt file with your product catalog paths.

The free scan gets merchants in the door. The paid scan convinces them the problem is real — with evidence from an actual AI agent failing on their actual page. The fix report gives them the exact code to solve it.

## Why this matters now

Gartner projects 15-20% of e-commerce search will be agent-driven by 2028. Google's AI Overviews already pull from product pages. ChatGPT, Perplexity, and Claude are browsing and buying. The brands we've scanned are losing an estimated $2,000 to $50,000 per month in agent-referred revenue — not because their products are bad, but because their size pickers use `<div>` instead of `<select>`.

The free scan shows you the gap. The paid scan proves it with evidence. The fix report closes it.

Your competitors' pages are being read by AI agents right now. The question is whether those agents can buy.

---

## Try it

**Free scan:** [agent-a.com](https://agent-a.com) — paste a product URL, get your score in 10 seconds.

**Full scan:** Unlock the complete 23-check report with AI agent evidence, flow traces, and fix recipes.

**Open source:** Scanner framework, check definitions, and scoring logic at [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a).

---

*Built by [Sergei Stadnik](https://github.com/monkrus). Agent-readiness scanning for DTC e-commerce.*
