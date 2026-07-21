# Evidence — harrys.com (55.0/100)

Scanned July 2026 | SHOPPER=anthropic, N=10 runs per extraction check

## Top failed checks

### 1. RDY-006 — Agent extracts the correct product price (CRITICAL)

**Observed:** 0/10 runs matched ground truth (19.0).

---

### 2. RDY-004 — Return / refund policy reachable as text (HIGH)

**Observed:** No discoverable return/refund policy text or link.

---

### 3. RDY-017 — Agent can complete Add-to-Cart flow (HIGH)

**Observed:** Agent failed to add product to cart after 0 steps (0/2 attempts succeeded). Reason: Browser error: Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}. Steps: 

---

### 4. RDY-007 — Agent determines stock availability (HIGH)

**Observed:** 0/10 runs matched ground truth (in_stock).

---

### 5. RDY-011 — llms.txt content is complete and well-structured (MEDIUM)

**Observed:** No llms.txt found — nothing to validate.

---

## All checks

| Check | Verdict | Detail |
|-------|---------|--------|
| RDY-001 Product structured data present with pri | PASS (10/10) | Product JSON-LD with price and availability present. |
| RDY-002 Price appears in server-rendered HTML (n | PASS (10/10) | Currency-formatted price present in server HTML. |
| RDY-016 No hidden prompt injection in page conte | PASS (10/10) | No prompt injection patterns detected in page content. |
| RDY-006 Agent extracts the correct product price | FAIL (0/10) | 0/10 runs matched ground truth (19.0). |
| RDY-003 Agents are not blocked by robots.txt | PASS (10/10) | No agent user-agents fully disallowed in robots.txt. |
| RDY-004 Return / refund policy reachable as text | FAIL (0/10) | No discoverable return/refund policy text or link. |
| RDY-012 JSON-LD Product markup is complete and w | PASS (10/10) | JSON-LD Product is complete: name, image, brand, price, currency, availability. |
| RDY-013 Agents can access key product data witho | PASS (10/10) | Structured data provides agent-readable content despite JS ratio. Script: 88.7%  |
| RDY-014 Add-to-Cart is a semantic, identifiable  | PASS (10/10) | Add-to-Cart form with semantic button found — agents can interact. |
| RDY-017 Agent can complete Add-to-Cart flow | FAIL (0/10) | Agent failed to add product to cart after 0 steps (0/2 attempts succeeded). Reas |
| RDY-007 Agent determines stock availability | FAIL (0/10) | 0/10 runs matched ground truth (in_stock). |
| RDY-010 Agent gives a consistent shipping answer | PASS (10/10) | agent agreed with itself 10/10 (modal: 'error: error code: 401 - {'type': 'error |
| RDY-011 llms.txt content is complete and well-st | FAIL (0/10) | No llms.txt found — nothing to validate. |
| RDY-015 Variant selectors (size/color) use seman | FAIL (0/10) | Variant UI detected but uses non-semantic JS widgets — agents can't select sizes |
| RDY-008 Agent identifies the correct product | FAIL (0/10) | 0/10 runs matched ground truth (Harry&#x27;s Original On the Go Bundle | Harry&# |
| RDY-009 Agent gives a consistent return window | PASS (10/10) | agent agreed with itself 10/10 (modal: 'error: error code: 401 - {'type': 'error |
| RDY-005 llms.txt / agent guidance present | FAIL (0/10) | No llms.txt at site root. |
