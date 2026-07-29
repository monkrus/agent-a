# SKIMS vs ThirdLove: We Sent an AI Agent to Buy a Bra From Both. Neither Let It.

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a). 23 checks across data, extraction, interaction, and security. Real Claude extraction (10 runs per check) and real Playwright browser agent.*

---

Two of the biggest DTC bra brands. Both on Shopify. Both selling the same core product — a T-shirt bra that requires band size and cup size selection. We sent an AI shopping agent to each.

**ThirdLove: 78.5 / 100. SKIMS: 70.1 / 100. Neither agent could buy a bra.**

The reasons are completely different — and that's what makes this interesting.

## The scorecard

| Check | ThirdLove | SKIMS | What it tests |
|-------|-----------|-------|---------------|
| JSON-LD structured data | FAIL | PASS | Can agents read product data? |
| Price in HTML | PASS | PASS | Can agents find the price without JS? |
| robots.txt | PASS | PASS | Are agents allowed on the page? |
| Return policy | PASS | PASS | Can agents find the return window? |
| llms.txt present | PASS | FAIL | Does the site guide AI agents? |
| llms.txt quality | PASS | FAIL | Is the guidance complete? |
| Price extraction | PASS | PASS | Does the agent get the price right? |
| Availability extraction | UNKNOWN | PASS | Can the agent read stock status? |
| Product name extraction | PASS | PASS | Does the agent identify the product? |
| Return window consistency | PASS | PASS | Same answer every time? |
| Shipping consistency | FAIL | PASS | Same shipping answer every time? |
| JSON-LD completeness | FAIL | PASS | All fields agents need? |
| JS render ratio | PASS | PASS | Data available without a browser? |
| ATC button semantics | PASS | PASS | Is Add-to-Cart a real button? |
| Variant selectors | PASS | FAIL | Semantic HTML for size/color? |
| Prompt injection | PASS | PASS | No hidden manipulation? |
| **ATC browser flow** | **FAIL** | **FAIL** | **Can an agent actually add to cart?** |
| Site search | PASS | FAIL | Can the agent search for the product? |
| Checkout reachable | PASS | PASS | Can the agent reach checkout? |
| Homepage navigation | PASS | FAIL | Can the agent browse from homepage? |
| Product comparison | FAIL | FAIL | Can the agent find related products? |
| Guest checkout | UNKNOWN | UNKNOWN | Is there a login wall? |
| Cart API | PASS | FAIL | Can headless agents add to cart programmatically? |

ThirdLove passes 16 checks. SKIMS passes 14. But the one check that matters most — can an agent actually buy the product — fails for both.

## ThirdLove's strengths are infrastructure

ThirdLove did something unusual for a DTC brand: they invested in the plumbing.

**They have an llms.txt file.** When an AI agent visits thirdlove.com/llms.txt, it gets a structured guide to the site — product categories, sizing info, policies. SKIMS returns a 404. Most Shopify stores return a 404. ThirdLove is ahead of the curve.

**Their variant selectors are semantic HTML.** Size and color options use standard `<select>` elements that any agent can parse. SKIMS uses HeadlessUI popover components with randomly generated IDs that change every page load — 64 HeadlessUI references, 10 popovers, zero `<select>` elements.

**Their cart API works.** ThirdLove's `/cart/add.js` endpoint responds. A headless agent can add a product to cart with a single POST request, no browser required. SKIMS returns HTTP 410 Gone — the endpoint is deliberately disabled.

**Site search works.** Our agent found the search bar, typed "t-shirt bra," and located the product in results. On SKIMS, the search icon click timed out — it's behind a JavaScript overlay that the agent couldn't open.

**Homepage navigation works.** The agent started at thirdlove.com, browsed through navigation menus, found the bras category, and reached the product. On SKIMS, the agent got to the Push-Up Bras collection but couldn't navigate to the specific product.

## SKIMS's strength is data

SKIMS wins on one thing, but it's a big thing: structured data.

**Their JSON-LD is flawless.** Complete `schema.org/Product` markup with price, availability, currency, brand, images, and variant information. Every field an agent needs for product comparison is there.

ThirdLove's JSON-LD has price but **no availability field**. This is a critical failure — it means agents can tell you the bra costs $72 but can't tell you whether it's in stock. Two checks fail because of this single missing field (RDY-001 and RDY-012).

It also means our availability extraction check (RDY-007) returns UNKNOWN — there's no ground truth to grade against, which is itself a finding. A shopper asking "is this bra in stock?" gets no reliable answer.

## The Add-to-Cart problem: same outcome, different causes

Here's where both brands fail — and the failure is instructive because the root cause is completely different.

**SKIMS (RDY-017 failure):** The agent selected band size 32, selected cup size B, then clicked "Add to Bag" three times in a row. Nothing happened. The HeadlessUI popover didn't register the selection, so the ATC button was silently disabled. The agent got stuck in a loop clicking a button that wouldn't respond.

**ThirdLove (RDY-017 failure):** The agent scrolled to find the product form, then got stuck trying to close a persistent popup. It clicked `[aria-label="Close"]` three times — the popup kept coming back or a new one appeared. The agent never reached the ATC button at all.

Same result — zero successful purchases out of multiple attempts. But the fixes are completely different:

- SKIMS needs to replace HeadlessUI popovers with semantic `<select>` elements so the variant selection actually registers
- ThirdLove needs to tame their popup behavior so agents (and frustrated humans) can reach the product form

## The shipping problem both share

Both brands fail RDY-010 (consistent shipping answer), though ThirdLove's failure is milder.

ThirdLove's agent agreed with itself 8 out of 10 times — "free on orders $75+" — but gave a different answer on 2 runs. That's an 80% consistency rate. The likely cause: shipping text appears in multiple locations on the page with slight variations.

SKIMS had the same problem in our earlier 17-check scan — their page contained both US and Australian shipping text (`"Free Shipping on Domestic Orders $75+"` and `"Free Shipping On Orders AUD185+"`), and the agent picked one or the other randomly.

The fix is identical for both: ensure one canonical shipping statement is visible in the HTML. Use `<template>` tags or JS-only rendering for regional variants so agents parse the primary text.

## The related products gap

Neither brand lets an agent comparison-shop (RDY-021 fails for both).

ThirdLove technically has a "You may also like" section, but our agent scrolled to it, found it, and couldn't click through — the product links weren't resolving. SKIMS doesn't have a visible related products section at all.

This matters because AI shopping agents don't just buy — they compare. An agent asked "find me a comfortable T-shirt bra under $75" will navigate to ThirdLove, extract the price ($72), and then look for alternatives on the same site. If it can't find related products, it leaves to compare elsewhere.

## What each brand should fix first

**ThirdLove — fix the JSON-LD (30 minutes, +11 points):**

Add `availability` to the JSON-LD offers block. One field. That's it.

```json
"offers": {
  "@type": "Offer",
  "price": "72.00",
  "priceCurrency": "USD",
  "availability": "https://schema.org/InStock"
}
```

This fixes RDY-001 (critical) and RDY-012 (high), and unblocks RDY-007 availability extraction. Projected score: 78.5 -> 89+.

**SKIMS — fix the variant selectors (2-4 hours, +8 points):**

Replace HeadlessUI popovers with `<select>` elements for band and cup size. This unblocks the Add-to-Cart flow (RDY-017) and fixes RDY-015. Then add an llms.txt file (+7 points) and re-enable `/cart/add.js` (+3 points). Projected score: 70.1 -> 88+.

## The bigger picture

These two brands represent two opposite failure modes in agent readiness:

**ThirdLove built the infrastructure but forgot the data.** Semantic HTML, working cart API, llms.txt, searchable, navigable — but missing one field in their JSON-LD that makes the product invisible to stock-checking agents.

**SKIMS built the data but locked down the infrastructure.** Perfect structured data, flawless extraction — but HeadlessUI widgets, disabled cart API, no llms.txt, and a search overlay agents can't open.

The brand that fixes its weakness first will have one of the most agent-ready bra shopping experiences on Shopify. ThirdLove's fix is a 30-minute JSON-LD edit. SKIMS's fix is a 2-4 hour frontend refactor.

Both brands are leaving an estimated $5,800 - $67,400 per month in agent-referred revenue on the table. Not because their products are wrong — because their pages don't speak the language AI agents understand.

The irony is that between the two of them, they have all the pieces. ThirdLove's infrastructure plus SKIMS's structured data would score 95+.

---

## Methodology

- **Scanner:** [agent-a](https://github.com/monkrus/agent-a) (open source)
- **Checks:** 23 checks across 4 layers — data, extraction, interaction, security
- **Extraction model:** Claude Sonnet, 10 runs per check
- **Browser agent model:** Claude Haiku (action decisions) + Playwright
- **Products scanned:** [ThirdLove 24/7 Classic T-Shirt Bra](https://www.thirdlove.com/products/24-7-classic-t-shirt-bra-taupe) | [SKIMS Everyday Cotton Push-Up Bra](https://skims.com/products/everyday-cotton-ultimate-teardrop-push-up-bra-sienna-heather)
- **Date:** July 2026

---

*Built by [Sergei Stadnik](https://github.com/monkrus). Scan your store at agent-a.com.*
