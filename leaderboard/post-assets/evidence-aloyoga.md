# Evidence — aloyoga.com (38.0/100)

Scanned July 2026 | SHOPPER=anthropic, N=10 runs per extraction check

## Top failed checks

### 1. RDY-001 — Product structured data present with price + availability (CRITICAL)

**Observed:** No schema.org/Product JSON-LD found.

---

### 2. RDY-002 — Price appears in server-rendered HTML (not JS-only) (CRITICAL)

**Observed:** No price string in server HTML (likely JS-rendered only).

---

### 3. RDY-006 — Agent extracts the correct product price (CRITICAL)

**Observed:** 0/10 runs matched ground truth (42.0).

---

### 4. RDY-012 — JSON-LD Product markup is complete and well-formed (HIGH)

**Observed:** No schema.org/Product JSON-LD to validate.

---

### 5. RDY-013 — Agents can access key product data without JavaScript (HIGH)

**Observed:** High JS dependency with no structured data fallback. Script: 73.9% of page, visible text: 0.8% of page. Rendered DOM has 10066 more chars of text — JS hides content from text-mode agents.

---

## All checks

| Check | Verdict | Detail |
|-------|---------|--------|
| RDY-001 Product structured data present with pri | FAIL (0/10) | No schema.org/Product JSON-LD found. |
| RDY-002 Price appears in server-rendered HTML (n | FAIL (0/10) | No price string in server HTML (likely JS-rendered only). |
| RDY-016 No hidden prompt injection in page conte | PASS (10/10) | No prompt injection patterns detected in page content. |
| RDY-006 Agent extracts the correct product price | FAIL (0/10) | 0/10 runs matched ground truth (42.0). |
| RDY-003 Agents are not blocked by robots.txt | PASS (10/10) | No agent user-agents fully disallowed in robots.txt. |
| RDY-004 Return / refund policy reachable as text | PASS (10/10) | Return/refund policy referenced in text or links. |
| RDY-012 JSON-LD Product markup is complete and w | FAIL (0/10) | No schema.org/Product JSON-LD to validate. |
| RDY-013 Agents can access key product data witho | FAIL (0/10) | High JS dependency with no structured data fallback. Script: 73.9% of page, visi |
| RDY-014 Add-to-Cart is a semantic, identifiable  | PASS (10/10) | Buy/cart button with semantic attributes found. |
| RDY-017 Agent can complete Add-to-Cart flow | FAIL (0/10) | Agent failed to add product to cart after 0 steps (0/2 attempts succeeded). Reas |
| RDY-007 Agent determines stock availability | FAIL (0/10) | 0/10 runs matched ground truth (in_stock). |
| RDY-010 Agent gives a consistent shipping answer | PASS (10/10) | agent agreed with itself 10/10 (modal: 'error: error code: 401 - {'type': 'error |
| RDY-011 llms.txt content is complete and well-st | PASS (10/10) | llms.txt has product paths, policy links, and sitemap. |
| RDY-015 Variant selectors (size/color) use seman | FAIL (0/10) | Variant UI detected but uses non-semantic JS widgets — agents can't select sizes |
| RDY-008 Agent identifies the correct product | FAIL (0/10) | 0/10 runs matched ground truth (Superfood Multivitamin - 60 Pack | ALO). |
| RDY-009 Agent gives a consistent return window | PASS (10/10) | agent agreed with itself 10/10 (modal: 'error: error code: 401 - {'type': 'error |
| RDY-005 llms.txt / agent guidance present | PASS (10/10) | llms.txt present. |
