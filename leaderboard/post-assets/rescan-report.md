# Parser Fix Rescan Report — July 2026

## Executive summary

The `_jsonld_offers` parser fix (commit 718599b) correctly resolves ProductGroup/hasVariant
JSON-LD structures used by SKIMS, Warby Parker, UNTUCKit, Purple, and Tuft & Needle.
Combined with 34 bug fixes (commits d59a361, 9db1002, 7948147), the median readiness
score across 18 scanned brands improved from 74.6 to 82.7 (+8.1 points).

## Brands directly improved by parser fix

| Brand | Old | New | Delta | JSON-LD pattern |
|-------|-----|-----|-------|-----------------|
| skims.com | 51.2 | 81.4 | +30.2 | ProductGroup + 35 hasVariant Products |
| warbyparker.com | 51.2 | 77.7 | +26.5 | ProductGroup |
| untuckit.com | 63.1 | 85.1 | +22.0 | ProductGroup |
| purple.com | 60.7 | 75.9 | +15.2 | ProductGroup |
| tuftandneedle.com | 76.2 | 87.8 | +11.6 | ProductGroup |

## Brands excluded from rescan

| Brand | Reason |
|-------|--------|
| gymshark.com | JS-only page, no server-rendered content |
| everlane.com | Product URL returned HTTP 404 |
| kyliecosmetics.com | Product URL returned HTTP 404 |

## Regression test summary

```
readiness/tests/test_parser.py — 6 tests, 6 passed, 0 failed

  PASS  test_skims_productgroup     (ProductGroup + 35 hasVariant)
  PASS  test_graph_container        (@graph wrapping Product)
  PASS  test_type_as_array          (@type as ["Product", "Thing"])
  PASS  test_offers_as_array        (offers as list)
  PASS  test_no_product             (graceful None on missing Product)
  PASS  test_empty_jsonld           (empty/missing jsonld)
```

Fixture: `readiness/tests/fixtures/skims-productgroup.json` (31KB, real SKIMS JSON-LD)

## Scanner changes since last scan

| Commit | Description |
|--------|-------------|
| 718599b | Parser fix: ProductGroup, hasVariant, @graph, @type arrays |
| d59a361 | 27 bug fixes: security, logic, robustness, accuracy |
| 9db1002 | Browser check tightening, DEV_MODE guard, cart verification |
| 7948147 | Web app: confidence band, impact estimates, rate limiting, deps |

## Files in this deliverable

```
leaderboard/post-assets/
  rescan-diff.md          — old vs new diff table
  rescan-report.md        — this file
  evidence-skims.md       — SKIMS detailed evidence + all check results
  evidence-olaplex.md     — Olaplex evidence
  evidence-kyliecosmetics.md — Kylie evidence (pre-404, historical)
readiness/tests/
  test_parser.py          — 6 regression tests
  fixtures/
    skims-productgroup.json — real SKIMS JSON-LD (31KB)
```
