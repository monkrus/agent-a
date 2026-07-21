# Canonical Scan Report — July 2026

## Summary

17 DTC brands scanned with SHOPPER=anthropic (real Claude extraction), N=10 runs per check,
Playwright rendered DOM enabled. All numbers in this report and the leaderboard trace to this
single canonical run.

gymshark.com excluded: JS-only rendering returns no server-side content.

## Scanner version

Post bug-fix (commits through 56a0b44): ProductGroup parser, N=10 majority-vote, confidence band.
429 recovery: Playwright fallback when requests gets rate-limited by Shopify CDN.

## Score distribution

- Brands: 17
- Min: 34.6
- Max: 71.0
- Median: 66.0
- Mean: 60.8

## Run conditions

- SHOPPER=anthropic (Claude Sonnet)
- SCAN_N=10
- RENDER=playwright (headless Chromium for 429 recovery and JS-heavy pages)
- Check pack: shopify-v1.yaml v2026Q2.1 (17 checks, weights sum to 100)
- Date: July 2026

## Test suite

37 tests passed (34 parser + 3 fixes-stub graceful degradation).
