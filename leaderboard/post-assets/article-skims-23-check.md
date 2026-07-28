# SKIMS Scores 87/100 for AI Shopping Agents — But the Bra Size Picker Still Breaks Them

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a), an open-source agent-accessibility scanner. 17 checks across data, extraction, interaction, and security layers. Real Claude extraction, 10 runs per check. Scan your store free at agent-a.com.*

---

## The score

SKIMS scored **87/100** in our agent-readiness scan of the [Everyday Cotton Ultimate Teardrop Push-Up Bra](https://skims.com/products/everyday-cotton-ultimate-teardrop-push-up-bra-sienna-heather). That puts it 6th out of 17 DTC brands we tested — above average (mean: 79.4), but with real gaps that cost conversions when AI agents try to shop.

## What works

SKIMS gets the data layer right. The product page ships complete JSON-LD with correct pricing and availability. Prices are server-rendered in HTML — no JavaScript dependency. Robots.txt doesn't block agents. Return policy text is accessible. Across 10 extraction runs, Claude correctly identified the product name (100%), price (100%), availability (100%), and return window (100%) every time.

**Security is clean.** No prompt injection found in page content.

## What breaks

Four checks failed — all in the interaction and content guidance layers:

**1. Variant selectors use non-semantic JavaScript widgets (RDY-015, critical)**
The two-step band-then-cup size picker works perfectly for humans but defeats AI agents. There are no `<select>` elements, no ARIA roles that map to standard controls. Agents click "32" and don't understand that cup options should appear. In past browser testing, our agent clicked the same button three times and gave up.

**2. No llms.txt agent guidance (RDY-005 + RDY-011)**
SKIMS has no `llms.txt` file at its site root. This file tells AI agents what the site is, how to navigate it, and what actions are supported. Without it, agents have zero context for how to interact with SKIMS beyond what they can infer from raw HTML.

**3. Shipping answers are inconsistent (RDY-010, 80% pass rate)**
Across 10 extraction runs, agents agreed with themselves 8 times (modal answer: "free on orders $75+") but gave 2 distinct answers. That 80% consistency falls below the 90% threshold. The page likely has multiple shipping references that confuse extraction.

## The ATC flow: unknown

The Add-to-Cart browser flow (RDY-017) returned UNKNOWN — the agent couldn't be tested in this scan run. Given the non-semantic variant selectors, this flow would likely struggle: an agent needs to select a band size, then a cup size, then click Add to Cart. Without semantic HTML controls, that sequence is fragile at best.

## What it would take to fix

Three targeted changes would push SKIMS past 95:

1. **Wrap variant selectors in semantic HTML.** Use `<select>` or `<fieldset>` with proper ARIA roles. Agents need to programmatically identify that "32" is a band size and "B" is a cup size.
2. **Add llms.txt.** A 20-line file at `skims.com/llms.txt` describing the site, product categories, and supported actions. Takes 15 minutes.
3. **Disambiguate shipping text.** Ensure one canonical shipping statement is prominent in the HTML. Remove or de-emphasize secondary references.

## Context: where SKIMS sits

| Rank | Brand | Score |
|------|-------|-------|
| 1 | Kylie Cosmetics | 100.0 |
| 2 | Framebridge | 96.2 |
| 3 | Away | 94.7 |
| 4 | Liquid I.V. | 92.0 |
| 5 | UNTUCKit | 89.0 |
| **6** | **SKIMS** | **87.0** |
| 7 | Harry's | 85.0 |
| 8 | Sunday Riley | 79.5 |
| 9 | Warby Parker | 78.5 |
| 10 | Tuft & Needle | 77.0 |
| 11 | Fenty Beauty | 74.0 |
| 12 | Olaplex | 72.5 |
| 13 | Casper | 71.0 |
| 13 | Everlane | 71.0 |
| 15 | Purple | 69.6 |
| 16 | Dollar Shave Club | 66.1 |
| 17 | Alo Yoga | 46.7 |

Mean: 79.4 | Median: 78.5

---

*Full methodology, check definitions, and scanner source at [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a). Data from a single-page scan — scores reflect the scanned product URL, not the entire site.*
