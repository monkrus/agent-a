# Evidence — kyliecosmetics.com (66.0/100)

Scanned July 2026 | SHOPPER=anthropic, N=5 runs per extraction check
Score unchanged from old scan (66.0 -> 66.0, delta 0.0)

## Top 3 failed checks

### 1. RDY-014 — Add-to-Cart is a semantic, identifiable action (CRITICAL)

**Observed:** No Add-to-Cart form or button found in server HTML. Independent spot-check
confirmed the ATC element is hidden via CSS: `.form__atc { display: none !important }`.
Agents cannot purchase from this page.

---

### 2. RDY-017 — Agent can complete Add-to-Cart flow (HIGH)

**Observed:** Our browser agent (headless Playwright + Claude vision) exhausted all 12 steps
without finding an Add-to-Cart button. The agent scrolled the entire page repeatedly but
the button is not rendered visually. Consistent with the CSS hiding confirmed in spot-check.

---

### 3. RDY-004 — Return/refund policy reachable as text (HIGH)

**Observed:** No discoverable return/refund policy text or link in the server-rendered HTML.
An agent asked "what is the return policy?" has no on-page content to reference.

---

### Additional failures

- **RDY-007** — Availability: 0/5 runs matched ground truth (in_stock). Agent cannot determine stock status.
- **RDY-012** — JSON-LD incomplete: missing `description` field.
- **RDY-013** — JS render ratio: 79.1% scripts by size. Minimal visible text in raw HTML.

## All checks

| Check | Verdict | Detail |
|-------|---------|--------|
| RDY-001 Product structured data | PASS | Product JSON-LD with price and availability |
| RDY-002 Price in server HTML | PASS | Currency-formatted price present |
| RDY-003 robots.txt | PASS | No agent user-agents blocked |
| RDY-004 Return policy | FAIL | No discoverable policy text or link |
| RDY-005 llms.txt present | PASS | llms.txt present |
| RDY-006 Price extraction | PASS (5/5) | All runs matched ground truth ($25.0) |
| RDY-007 Availability | FAIL (0/5) | 0/5 matched ground truth |
| RDY-008 Product name | PASS (5/5) | "Compact Mirror" |
| RDY-009 Return window | PASS (5/5) | Consistent: "not stated" |
| RDY-010 Shipping | PASS (5/5) | Consistent: "not stated" |
| RDY-011 llms.txt quality | PASS | Has product paths, policy links, sitemap |
| RDY-012 JSON-LD completeness | FAIL | Missing description field |
| RDY-013 JS render ratio | FAIL | 79.1% scripts by size |
| RDY-014 ATC semantic HTML | FAIL | No ATC form/button in server HTML (CSS hidden) |
| RDY-015 Variant selectors | PASS | Basic variant selector found in semantic HTML |
| RDY-016 Prompt injection | PASS | No injection patterns detected |
| RDY-017 ATC browser flow | FAIL | No ATC button visible to browser agent |
