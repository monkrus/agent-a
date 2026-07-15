# Findings — Computed Facts (Scanned July 2026)

## Score distribution
- Brands scanned: 17 of 18 (gymshark.com skipped: page returned no visible content to our fetch method)
- Min: 56.0
- Max: 95.0
- Median: 77.0
- Mean: 76.1
- Std dev: 10.5
- Brands scoring 80+: 8
- Brands scoring below 60: 1

## Most-failed check across brands
- **Page content is accessible without JavaScript** (RDY-013): FAIL on 12/17 brands
  Brands: awaytravel.com, liquid-iv.com, olaplex.com, untuckit.com, skims.com, dollarshaveclub.com, warbyparker.com, harrys.com, purple.com, kyliecosmetics.com, aloyoga.com, casper.com
- **Variant selectors (size/color) use semantic HTML** (RDY-015): FAIL on 11/17 brands
  Brands: liquid-iv.com, olaplex.com, untuckit.com, skims.com, fentybeauty.com, warbyparker.com, harrys.com, framebridge.com, purple.com, aloyoga.com, casper.com
- **JSON-LD Product markup is complete and well-formed** (RDY-012): FAIL on 8/17 brands
  Brands: tuftandneedle.com, dollarshaveclub.com, framebridge.com, everlane.com, purple.com, kyliecosmetics.com, aloyoga.com, casper.com
- **Agent can complete Add-to-Cart flow** (RDY-017): FAIL on 8/17 brands
  Brands: olaplex.com, untuckit.com, sundayriley.com, dollarshaveclub.com, warbyparker.com, framebridge.com, everlane.com, kyliecosmetics.com
- **Agent determines stock availability** (RDY-007): FAIL on 6/17 brands
  Brands: skims.com, fentybeauty.com, sundayriley.com, everlane.com, kyliecosmetics.com, casper.com

## Checks all brands passed
- Agent gives a consistent return window (RDY-009)
- No hidden prompt injection in page content (RDY-016)

## Checks all brands failed
- None — no check failed on every brand

## Biggest score gap within same category
- **apparel**: untuckit.com (84.0) vs everlane.com (70.0) — gap: 14.0 pts
- **beauty**: olaplex.com (84.0) vs kyliecosmetics.com (66.0) — gap: 18.0 pts
- **grooming**: dollarshaveclub.com (77.0) vs harrys.com (72.0) — gap: 5.0 pts
- **home goods**: tuftandneedle.com (90.0) vs casper.com (56.0) — gap: 34.0 pts
- **Biggest gap**: 34.0 pts — home goods: tuftandneedle.com (90.0) vs casper.com (56.0)

## Per-layer averages across all brands
- **Data**: avg 76.6%, range 37.5%–100.0%
- **Extraction**: avg 81.7%, range 45.2%–100.0%
- **Interaction**: avg 59.5%, range 18.8%–100.0%
- **Security**: avg 100.0%, range 100.0%–100.0%

## Per-brand top weakness
- **awaytravel.com** (95.0/100): weakest layer = Data, top fail = Page content is accessible without JavaScript
- **tuftandneedle.com** (90.0/100): weakest layer = Extraction, top fail = JSON-LD Product markup is complete and well-formed
- **liquid-iv.com** (85.4/100): weakest layer = Interaction, top fail = Page content is accessible without JavaScript
- **olaplex.com** (84.0/100): weakest layer = Interaction, top fail = Page content is accessible without JavaScript
- **untuckit.com** (84.0/100): weakest layer = Interaction, top fail = Page content is accessible without JavaScript
- **skims.com** (81.2/100): weakest layer = Interaction, top fail = Page content is accessible without JavaScript
- **fentybeauty.com** (81.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **sundayriley.com** (81.0/100): weakest layer = Interaction, top fail = Return / refund policy reachable as text
- **dollarshaveclub.com** (77.0/100): weakest layer = Interaction, top fail = JSON-LD Product markup is complete and well-formed
- **warbyparker.com** (74.0/100): weakest layer = Interaction, top fail = Agents are not blocked by robots.txt
- **harrys.com** (72.0/100): weakest layer = Data, top fail = Return / refund policy reachable as text
- **framebridge.com** (70.2/100): weakest layer = Interaction, top fail = Product structured data present with price + availability
- **everlane.com** (70.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **purple.com** (67.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **kyliecosmetics.com** (66.0/100): weakest layer = Interaction, top fail = Return / refund policy reachable as text
- **aloyoga.com** (60.7/100): weakest layer = Data, top fail = Product structured data present with price + availability
- **casper.com** (56.0/100): weakest layer = Extraction, top fail = Price appears in server-rendered HTML (not JS-only)
