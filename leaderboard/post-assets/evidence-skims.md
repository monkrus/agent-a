# Evidence — skims.com (81.4/100)

Scanned 2026-07-14 | SHOPPER=mock, N=10 runs per extraction check
**Post parser-fix rescan** — score changed from 51.2 to 81.4 (+30.2)

## Parser fix impact

The old parser only matched top-level `@type: "Product"`. SKIMS uses `@type: "ProductGroup"`
with `hasVariant[]` containing 35 nested Product objects (each with its own Offer). The fixed
parser correctly traverses ProductGroup -> hasVariant -> Product -> Offer, extracting price ($64)
and availability (InStock) from the first variant.

**Checks that flipped from parser fix:**
- RDY-001 (FAIL->PASS): ProductGroup now recognized as valid structured data
- RDY-012 (FAIL->PASS): JSON-LD completeness now passes (name, image, brand, price, currency, availability)

**Ground truth extracted by fixed parser:**
- Price: $64.00 (from first variant Offer)
- Availability: InStock (schema.org/InStock)
- Product name: EVERYDAY COTTON ULTIMATE TEARDROP PUSH-UP BRA
- Brand: SKIMS

## JSON-LD structure (what the parser sees)

```
jsonld[0]: @type=Organization (SKIMS corporate entity)
jsonld[1]: @type=BreadcrumbList
jsonld[2]: @type=ProductGroup
  ├── name: "EVERYDAY COTTON ULTIMATE TEARDROP PUSH-UP BRA"
  ├── brand: { @type: Brand, name: "SKIMS" }
  └── hasVariant: [35 Products]
       └── [0]: @type=Product
            └── offers: { price: 64, priceCurrency: USD,
                          availability: schema.org/InStock }
```

## Regression test

`readiness/tests/test_parser.py::test_skims_productgroup` — validates the parser
extracts price=$64.00, availability=in_stock, and product name from the saved
JSON-LD fixture (`readiness/tests/fixtures/skims-productgroup.json`, 31KB).

## All checks (rescan)

| Check | Verdict | Detail |
|-------|---------|--------|
| RDY-001 Product structured data | PASS | ProductGroup with hasVariant -> Product -> Offer correctly parsed |
| RDY-002 Price in server HTML | PASS | Currency-formatted price present |
| RDY-003 robots.txt | PASS | No agent user-agents blocked |
| RDY-004 Return policy | PASS | Return/refund policy referenced |
| RDY-005 llms.txt present | FAIL | No llms.txt at site root |
| RDY-006 Price extraction | FAIL | Mock shopper variance (mock mode) |
| RDY-007 Availability | FAIL | Mock shopper variance |
| RDY-008 Product name | PASS | Correctly identified |
| RDY-009 Return window | FAIL | Mock shopper inconsistency |
| RDY-010 Shipping | PASS | Consistent answer |
| RDY-011 llms.txt quality | FAIL | No llms.txt to validate |
| RDY-012 JSON-LD completeness | PASS | Complete: name, image, brand, price, currency, availability |
| RDY-013 JS render ratio | FAIL | ~76% scripts by size, but JSON-LD provides structured fallback |
| RDY-014 ATC semantic HTML | PASS | Add-to-Cart form with semantic button found |
| RDY-015 Variant selectors | FAIL | Non-semantic JS widgets |
| RDY-016 Prompt injection | PASS | No injection patterns detected |
| RDY-017 ATC browser flow | UNKNOWN | Browser check skipped in rescan |
