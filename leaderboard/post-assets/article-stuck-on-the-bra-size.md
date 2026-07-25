# Stuck on the Bra Size

## How an AI Shopping Agent Burned 12 Steps Clicking the Same Button — and What It Means for E-Commerce

We pointed an AI shopping agent at a $54 bra on SKIMS.com and asked it to do one thing: add it to the cart.

It clicked "Band Size: 32" twelve times in a row. It never selected a cup size. It never reached the Add to Cart button. After exhausting all twelve allowed steps, it gave up.

The agent knew exactly what it needed to do. In its reasoning traces, it kept saying: "Band size 32 is already selected, need to select cup size next." But it couldn't find the cup size selector. SKIMS uses custom JavaScript widgets for variant selection — not standard `<select>` dropdowns or radio buttons. The agent could see the band size buttons (they have `aria-label` attributes), but the cup size UI was invisible to it.

This is what a 67/100 agent readiness score looks like in practice.

---

### The scan

We ran a full agent readiness scan against `skims.com/products/fits-everybody-t-shirt-bra-onyx` using real Claude extraction (not mocked) with 5 runs per check. The scanner tests four layers of agent accessibility:

**Data (how readable is the page?)** — SKIMS actually does well here. Product JSON-LD is present and complete with price, availability, brand, and images. Price appears in server-rendered HTML. No agent user-agents are blocked in robots.txt. Score: strong.

**Extraction (can agents get the right answers?)** — This is where cracks appear. We asked Claude to extract the product price five times. Ground truth from the JSON-LD: $54.00. The agent returned $54 twice and $37.80 three times. The $37.80 is a sale or member price visible somewhere on the page. When a page shows two prices, agents guess wrong 60% of the time. Availability was worse: the agent said "unknown" on all five runs, even though JSON-LD declares the item in stock. The availability signal exists in structured data but isn't surfaced in the page text the agent reads.

**Interaction (can agents complete a purchase?)** — Total failure. The browser agent loop — Playwright plus Claude vision deciding what to click — got stuck on variant selection. SKIMS uses a two-step size picker for bras: band size first, then cup size. The band size buttons are aria-labeled, so the agent found them. The cup size options either render dynamically after band selection or use a non-standard widget the agent couldn't parse. Twelve clicks on the same button. Zero progress.

**Security (is the page safe from manipulation?)** — Clean. No prompt injection patterns detected.

### The numbers

| Check | Result |
|-------|--------|
| Product JSON-LD present | PASS |
| Price in server HTML | PASS |
| JSON-LD complete | PASS |
| No prompt injection | PASS |
| robots.txt allows agents | PASS |
| Return policy reachable | PASS |
| ATC form is semantic | PASS |
| Product name extracted | 5/5 PASS |
| Return window consistent | 5/5 PASS |
| Price extracted correctly | 2/5 FAIL |
| Availability determined | 0/5 FAIL |
| Shipping answer consistent | 3/5 FAIL |
| Browser Add-to-Cart flow | 0/2 FAIL |
| Variant selectors semantic | FAIL |
| llms.txt present | FAIL |
| llms.txt complete | FAIL |

**Final score: 67.0/100** with a confidence margin of +/- 5.8 points.

### Why this matters

SKIMS is not a small brand with a broken Shopify theme. This is a company with a $4B valuation, a world-class engineering team, and a site that works flawlessly for human shoppers. The bra size picker is actually well-designed — it's intuitive, responsive, and accessible in the traditional sense (screen readers can navigate it).

But AI shopping agents are not screen readers. They don't execute JavaScript the same way. They can't infer that clicking "32" should reveal a second row of cup size buttons. They see a flat list of interactive elements, a screenshot, and they try to reason about what to do next. When the cup sizes don't appear in their element inventory, they're stuck.

This isn't a SKIMS problem. It's an industry problem. Across 17 DTC brands we scanned, the Add-to-Cart browser flow failed on every single one. The interaction layer averaged 35% across all brands. Even stores with perfect structured data and clean HTML couldn't get an agent through checkout.

### The $37.80 problem

The price extraction failure is arguably more damaging than the cart failure. An agent that can't add to cart simply doesn't convert — the customer has to do it manually. But an agent that reports the wrong price actively misleads the customer.

SKIMS shows $54.00 as the regular price and $37.80 as a promotional or member price. The JSON-LD lists $54.00. Three out of five times, Claude extracted $37.80 from the page text instead. This happens because the discounted price is visually prominent — styled larger, colored differently, positioned near the product title. The agent reads the raw text without visual hierarchy and picks whichever price it encounters first or most often.

If an AI shopping agent tells a customer this bra costs $37.80, and the customer gets to checkout and sees $54.00, that's a broken experience. It's worse than not showing a price at all.

### What would fix it

Three changes would move this product from 67 to 85+:

**1. Surface availability in page text.** The JSON-LD says `InStock` but the page text never says "In Stock" anywhere the agent can read. Adding a visible availability badge eliminates 6 points of failure.

**2. Disambiguate the price.** When the page shows multiple prices, mark the canonical price with structured data *and* make it the most prominent in raw text extraction. Use `<meta>` tags or a clearly labeled "Regular price: $54" string. Agents need one unambiguous answer.

**3. Use semantic variant selectors — or provide a fallback.** The custom JS size picker works beautifully for humans but is opaque to agents. A hidden `<select>` element with band and cup options, even if not displayed to human users, would give agents a machine-readable way to choose a variant. Alternatively, exposing a direct add-to-cart API endpoint (which Shopify already provides via `/cart/add.js`) and documenting it in `llms.txt` would let agents bypass the UI entirely.

### The bigger picture

We've now scanned 17 major DTC brands with real Claude extraction (N=10 runs per check). The average agent readiness score is 79/100. Seven brands scored above 80, but the scores mask real fragility — a single product with a sale price or a complex variant picker can drop a brand's score by 20 points. One brand hit 100, another landed at 47.

The gap isn't in data — most Shopify stores have decent JSON-LD. It's not in security — none of the 17 brands had prompt injection issues. The gap is in edge cases: dual prices that confuse extraction, variant selectors that block interaction, and policies buried in JavaScript. Pages are *readable* but not *reliably extractable*. Forms are *present* but not *agent-navigable*.

As AI shopping agents move from novelty to real purchase channel — Gartner projects 5-15% of e-commerce traffic will be agent-referred by end of 2027 — this gap becomes revenue at risk. For SKIMS, we estimate $6,300 to $37,900 per month in lost agent-driven conversions at current traffic levels.

The bra size picker that stumped our agent for twelve steps isn't a bug. It's a preview of the friction every online store will face when their next customer isn't a person with a mouse — it's a program with a prompt.

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a), an open-source agent-accessibility scanner. Real Claude extraction, 5 runs per check. Scan your store free at agent-a.com.*
