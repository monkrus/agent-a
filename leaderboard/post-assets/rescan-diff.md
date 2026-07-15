# Rescan Diff: Old Parser vs Fixed Parser + Bug Fixes (July 2026)

Rescan date: 2026-07-14
Scanner version: post bug-fix batch (commits d59a361, 9db1002, 7948147)
Mode: SHOPPER=mock, N=10 runs per check, browser checks skipped (no Playwright)

## What changed in the scanner

1. **Parser fix** (718599b): `_jsonld_offers` now handles ProductGroup/hasVariant,
   @graph containers, @type arrays. Previously only matched top-level `@type: "Product"`.
2. **Scoring fixes** (d59a361+): float epsilon comparison, empty-answers guard,
   browser early-exit logic, fetch error handling, impact smoothing, and 24 other fixes.

## Diff Table (sorted by delta desc)

```
Brand                   Old    New   Delta  Parser fix?
----------------------  -----  -----  -----  --------------------------------
skims.com                51.2   81.4  +30.2  YES — ProductGroup w/ 35 variants
warbyparker.com          51.2   77.7  +26.5  YES — ProductGroup
untuckit.com             63.1   85.1  +22.0  YES — ProductGroup
purple.com               60.7   75.9  +15.2  YES — ProductGroup
tuftandneedle.com        76.2   87.8  +11.6  YES — ProductGroup
thursdayboots.com        72.3   84.1  +11.8  no (other check variance)
casper.com               56.0   63.9   +7.9  no (JS render check improved)
fentybeauty.com          81.0   88.5   +7.5  no (mock variance)
dollarshaveclub.com      77.0   82.5   +5.5  no (JS render check improved)
bearaby.com              91.0   95.1   +4.1  no (mock variance)
sundayriley.com          79.0   82.9   +3.9  no (mock variance)
olaplex.com              90.4   92.4   +2.0  no (JS render check improved)
cutsclothing.com         77.3   79.1   +1.8  no (JS render check improved)
harrys.com               73.0   73.4   +0.4  stable
framebridge.com          71.3   71.5   +0.2  stable
liquid-iv.com            85.4   83.5   -1.9  mock variance
awaytravel.com          100.0   92.2   -7.8  mock variance (was 100 before)
aloyoga.com              51.0   42.2   -8.8  mock variance (still JS-heavy)
```

## Medians

- Old median: 74.6
- New median: 82.7 (+8.1)

## Summary

- **5 brands directly improved by parser fix** (ProductGroup): SKIMS, Warby Parker, UNTUCKit, Purple, Tuft & Needle
- **8 brands improved by other fixes** (JS render ratio, mock variance)
- **2 brands stable** (harrys, framebridge)
- **3 brands declined** (mock variance, not parser-related)

## Notes

- Gymshark, Everlane, Kylie Cosmetics excluded (URLs returned 404 or JS-only blank page)
- Browser check (RDY-017) skipped in rescan — scored as UNKNOWN, excluded from totals
- Shopper check variance (RDY-009, RDY-010) is expected with SHOPPER=mock
- Old scores from pre-fix scans stored in `.scans/_old_scores.json`
