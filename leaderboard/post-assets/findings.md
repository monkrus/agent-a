# Findings — Computed Facts (Rescanned July 2026)

## Score distribution
- Brands scanned: 17
- Min: 46.7
- Max: 100.0
- Median: 78.5
- Mean: 79.4
- Std dev: 13.1
- Brands scoring 80+: 7
- Brands scoring below 60: 1

## Most-failed check across brands
- **Agent can complete Add-to-Cart flow** (RDY-017): FAIL on 10/17 brands
  Brands: awaytravel.com, casper.com, everlane.com, fentybeauty.com, olaplex.com, sundayriley.com, tuftandneedle.com, untuckit.com, warbyparker.com, purple.com
- **Variant selectors (size/color) use semantic HTML** (RDY-015): FAIL on 9/17 brands
  Brands: aloyoga.com, framebridge.com, harrys.com, liquid-iv.com, olaplex.com, purple.com, skims.com, untuckit.com, warbyparker.com
- **Agent gives a consistent shipping answer** (RDY-010): FAIL on 8/17 brands
  Brands: fentybeauty.com, framebridge.com, harrys.com, olaplex.com, skims.com, sundayriley.com, us.dollarshaveclub.com, warbyparker.com
- **Agent extracts the correct product price** (RDY-006): FAIL on 6/17 brands
  Brands: aloyoga.com, casper.com, everlane.com, fentybeauty.com, olaplex.com, purple.com
- **Agent determines stock availability** (RDY-007): FAIL on 6/17 brands
  Brands: aloyoga.com, casper.com, everlane.com, fentybeauty.com, olaplex.com, sundayriley.com
- **JSON-LD Product markup is complete and well-formed** (RDY-012): FAIL on 6/17 brands
  Brands: aloyoga.com, casper.com, everlane.com, purple.com, tuftandneedle.com, us.dollarshaveclub.com
- **llms.txt content is complete and well-structured** (RDY-011): FAIL on 5/17 brands
  Brands: harrys.com, liquid-iv.com, purple.com, skims.com, warbyparker.com

## Checks all brands passed
- No hidden prompt injection in page content (RDY-016)
- Add-to-Cart is a semantic, identifiable action (RDY-014)
- Agent gives a consistent return window (RDY-009)

## Key changes vs previous scan (broken API key)
- Old mean: 60.8 -> New mean: 79.4 (+18.6 points)
- Previous scan had broken ANTHROPIC_API_KEY: shopper error strings were scored as real answers
- Error-as-UNKNOWN fix now correctly excludes API failures from grading
- Browser agent loop detection prevents wasted steps (12 -> 3 max on same element)
- kyliecosmetics.com: 66 -> 100 (extraction was failing due to API errors, not page issues)
- olaplex.com: 34.6 -> 72.5 (same — API errors inflated failure count)
- aloyoga.com: 60 -> 46.7 (genuine failures now surfaced without error noise)
