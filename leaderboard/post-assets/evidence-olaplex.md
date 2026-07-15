# Evidence — olaplex.com (84.0/100)

Scanned July 2026 | SHOPPER=anthropic, N=5 runs per extraction check
Score changed from 90.4 to 84.0 (-6.4) — RDY-017 flipped PASS->FAIL

## Top 3 failed checks

### 1. RDY-013 — Page content is accessible without JavaScript (HIGH)

**Observed:** Server-rendered HTML is 70.5% `<script>` tags by size. Visible text content
is minimal. Product details are injected client-side. However, JSON-LD structured data is
complete, so extraction checks all pass despite the JS rendering gap.

---

### 2. RDY-017 — Agent can complete Add-to-Cart flow (HIGH)

**Observed:** Our browser agent (headless Playwright + Claude vision) failed to add product
to cart after 12 steps. The ATC button was identifiable (RDY-014 passes) but the click
action did not result in a confirmed cart state change. Likely cause: modal/overlay
interference or site-side JS blocking the interaction during this scan.

**Change from old scan:** This check previously passed. The flip is non-deterministic —
browser ATC flow depends on popup state, network timing, and site-side JS behavior.

---

### 3. RDY-015 — Variant selectors use semantic HTML (MEDIUM)

**Observed:** Variant selection UI is implemented as non-semantic JavaScript widgets rather
than standard `<select>` or `<input type="radio">` elements. Agents that attempt to select
variants programmatically (without a full browser) find no standard form controls.

---

## All checks

| Check | Verdict | Detail |
|-------|---------|--------|
| RDY-001 Product structured data | PASS | Product JSON-LD with price and availability |
| RDY-002 Price in server HTML | PASS | Currency-formatted price present |
| RDY-003 robots.txt | PASS | No agent user-agents blocked |
| RDY-004 Return policy | PASS | Return/refund policy referenced |
| RDY-005 llms.txt present | PASS | llms.txt present |
| RDY-006 Price extraction | PASS (5/5) | All runs matched ground truth ($18.0) |
| RDY-007 Availability | PASS (5/5) | All runs matched ground truth (in_stock) |
| RDY-008 Product name | PASS (5/5) | "The Healthy Hair Discovery Set" |
| RDY-009 Return window | PASS (5/5) | Consistent: "not stated" |
| RDY-010 Shipping | PASS (5/5) | Consistent: "free on $50+" |
| RDY-011 llms.txt quality | PASS | Has product paths, policy links, sitemap |
| RDY-012 JSON-LD completeness | PASS | Complete: name, image, brand, price, currency, availability |
| RDY-013 JS render ratio | FAIL | 70.5% scripts by size |
| RDY-014 ATC semantic HTML | PASS | Add-to-Cart form with semantic button found |
| RDY-015 Variant selectors | FAIL | Non-semantic JS widgets |
| RDY-016 Prompt injection | PASS | No injection patterns detected |
| RDY-017 ATC browser flow | FAIL | Failed after 12 steps |
