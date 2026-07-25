# Stuck on the Bra Size

## How an AI Shopping Agent Failed at Every Stage of the Shopping Journey — and What It Means for E-Commerce

We pointed an AI shopping agent at a $54 bra on SKIMS.com and asked it to do what a customer would: find the product, add it to cart, and check out.

It failed at almost every stage.

It couldn't find the bra through site search — the search button was hidden behind JavaScript that the agent couldn't activate. It couldn't navigate from the homepage — SKIMS uses HeadlessUI popover menus that produce opaque selectors the agent couldn't parse. When we put it directly on the product page, it clicked "Band Size: 32" three times in a row, never found the cup size selector, and gave up. It couldn't find related products to compare — the "How It Compares" section uses `div` containers without clickable links.

One thing worked: the checkout path. Once past the variant selector, the agent reached the checkout page in two steps.

This is what a 60/100 agent readiness score looks like across the full shopping journey.

---

### The journey

We ran a 21-check agent readiness scan against `skims.com/products/fits-everybody-t-shirt-bra-onyx` using real Claude extraction with 5 runs per check. The scanner now tests the complete AI shopping journey — from search to checkout:

```
Search ──→ Navigate ──→ Read ──→ Extract ──→ Compare ──→ Add to Cart ──→ Checkout
  FAIL       FAIL       PASS      MIXED       FAIL        FAIL           PASS
```

**Search (can agents find the product?)** — FAIL. The agent started on the SKIMS homepage and looked for the search bar. SKIMS has a search button with `aria-label="Search"`, but it's a hidden `<button>` element — it resolves to an invisible element that Playwright can't click. The agent spent all 10 allowed steps trying different selectors to activate search. None worked.

**Navigation (can agents browse to the product?)** — FAIL. Starting from the homepage, the agent correctly identified the "Bras" category in the navigation menu and clicked it. But SKIMS uses HeadlessUI popovers with dynamic IDs (like `#headlessui-popover-button-:r12:`) that change between page loads. The agent clicked into the dropdown but couldn't reliably select "T-Shirt Bras" — it fell back to clicking generic `a` selectors and got stuck in a loop.

**Data (how readable is the page?)** — SKIMS does well here. Product JSON-LD is present and complete with price, availability, brand, and images. Price appears in server-rendered HTML. No agent user-agents are blocked in robots.txt. Score: strong.

**Extraction (can agents get the right answers?)** — This is where cracks appear. We asked Claude to extract the product price five times. Ground truth from the JSON-LD: $54.00. The agent returned $54 once and $37.80 four times. The $37.80 is a sale or member price visible somewhere on the page. When a page shows two prices, agents guess wrong 80% of the time. Availability was worse: the agent said "unknown" on all five runs, even though JSON-LD declares the item in stock. The availability signal exists in structured data but isn't surfaced in the page text the agent reads.

**Comparison (can agents compare products?)** — FAIL. The agent scrolled down and found the "How It Compares" section with related bras. But the related product cards use `div` containers without proper `<a>` link wrappers — the agent tried to click product images but the selectors resolved to hidden elements. It couldn't navigate to a second product for comparison.

**Interaction (can agents complete a purchase?)** — Mostly failed. The browser agent got stuck on variant selection. SKIMS uses a two-step size picker for bras: band size first, then cup size. The band size buttons are aria-labeled, so the agent found them. The cup size options either render dynamically after band selection or use a non-standard widget the agent couldn't parse. Three clicks on the same button. Zero progress.

**Checkout (can agents reach checkout?)** — PASS. This was the one bright spot. On one attempt, the agent managed to select band size 34 and the checkout was auto-verified — SKIMS's cart-to-checkout flow uses clear links and standard Shopify checkout. The path works when the agent can get past variant selection.

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
| JS render ratio | PASS |
| Product name extracted | 5/5 PASS |
| Return window consistent | 5/5 PASS |
| **Checkout reachable** | **PASS** |
| Price extracted correctly | 1/5 FAIL |
| Availability determined | 0/5 FAIL |
| Shipping answer consistent | 3/5 FAIL |
| Browser Add-to-Cart flow | 0/2 FAIL |
| Variant selectors semantic | FAIL |
| **Search discovery** | **FAIL** |
| **Homepage navigation** | **FAIL** |
| **Product comparison** | **FAIL** |
| llms.txt present | FAIL |
| llms.txt complete | FAIL |

**Final score: 59.6/100** with a confidence margin of +/- 5.5 points (21 checks, 11 pass, 10 fail).

### Why this matters

SKIMS is not a small brand with a broken Shopify theme. This is a company with a $4B valuation, a world-class engineering team, and a site that works flawlessly for human shoppers. The bra size picker is actually well-designed — it's intuitive, responsive, and accessible in the traditional sense (screen readers can navigate it).

But AI shopping agents are not screen readers. They don't execute JavaScript the same way. They can't infer that clicking "32" should reveal a second row of cup size buttons. They see a flat list of interactive elements, a screenshot, and they try to reason about what to do next. When the cup sizes don't appear in their element inventory, they're stuck.

The journey-level failures reveal something deeper: it's not just single pages that break — the entire flow is fragile. An agent can't even *find* this bra through search or site navigation. The search icon is invisible to automation. The nav menus use dynamic IDs. The related products section isn't linked. At every step, the human-optimized UI is an agent-hostile one.

### The $37.80 problem

The price extraction failure is arguably more damaging than the cart failure. An agent that can't add to cart simply doesn't convert — the customer has to do it manually. But an agent that reports the wrong price actively misleads the customer.

SKIMS shows $54.00 as the regular price and $37.80 as a promotional or member price. The JSON-LD lists $54.00. Four out of five times, Claude extracted $37.80 from the page text instead. This happens because the discounted price is visually prominent — styled larger, colored differently, positioned near the product title. The agent reads the raw text without visual hierarchy and picks whichever price it encounters first or most often.

If an AI shopping agent tells a customer this bra costs $37.80, and the customer gets to checkout and sees $54.00, that's a broken experience. It's worse than not showing a price at all.

### What would fix it

Five changes would move this product from 60 to 85+:

**1. Make search accessible.** The search button exists but is hidden to headless browsers. Ensure the search icon or input is a visible, clickable element — not gated behind JavaScript visibility toggling. A `<a href="/search">` fallback link works.

**2. Use stable navigation selectors.** HeadlessUI popovers generate dynamic IDs that change per session. Add `data-testid` attributes to nav menu items so agents can reliably find "Bras > T-Shirt Bras" regardless of the internal component state.

**3. Surface availability in page text.** The JSON-LD says `InStock` but the page text never says "In Stock" anywhere the agent can read. Adding a visible availability badge eliminates 5 points of failure.

**4. Disambiguate the price.** When the page shows multiple prices, mark the canonical price with structured data *and* make it the most prominent in raw text extraction. Use `<meta>` tags or a clearly labeled "Regular price: $54" string. Agents need one unambiguous answer.

**5. Use semantic variant selectors — or provide a fallback.** The custom JS size picker works beautifully for humans but is opaque to agents. A hidden `<select>` element with band and cup options, even if not displayed to human users, would give agents a machine-readable way to choose a variant. Alternatively, exposing a direct add-to-cart API endpoint (which Shopify already provides via `/cart/add.js`) and documenting it in `llms.txt` would let agents bypass the UI entirely.

### The bigger picture

We've now scanned 17 major DTC brands with real Claude extraction (N=10 runs per check). The average agent readiness score is 79/100. Seven brands scored above 80, but the scores mask real fragility — a single product with a sale price or a complex variant picker can drop a brand's score by 20 points. One brand hit 100, another landed at 47.

The gap isn't in data — most Shopify stores have decent JSON-LD. It's not in security — none of the 17 brands had prompt injection issues. The gap is in the journey: search bars hidden behind JavaScript, navigation menus with dynamic IDs, dual prices that confuse extraction, variant selectors that block interaction, and related products that aren't linked. Pages are *readable* but not *reliably extractable*. Forms are *present* but not *agent-navigable*. And the path between pages is invisible.

As AI shopping agents move from novelty to real purchase channel — Gartner projects 5-15% of e-commerce traffic will be agent-referred by end of 2027 — this gap becomes revenue at risk. For SKIMS, we estimate $6,800 to $40,900 per month in lost agent-driven conversions at current traffic levels.

The bra size picker that stumped our agent isn't the whole story anymore. The agent can't even *get to* the product page. That's not a bug — it's a preview of the friction every online store will face when their next customer isn't a person with a mouse — it's a program with a prompt.

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a), an open-source agent-accessibility scanner. 21 checks across the full shopping journey. Real Claude extraction, 5 runs per check. Scan your store free at agent-a.com.*
