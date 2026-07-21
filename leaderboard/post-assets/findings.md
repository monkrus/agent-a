# Findings — Computed Facts (Scanned July 2026)

## Score distribution
- Brands scanned: 17 of 18 (gymshark.com skipped: page returned no visible content to our fetch method)
- Min: 34.6
- Max: 71.0
- Median: 66.0
- Mean: 60.8
- Std dev: 10.2
- Brands scoring 80+: 0
- Brands scoring below 60: 5

## Most-failed check across brands
- **Agent can complete Add-to-Cart flow** (RDY-017): FAIL on 17/17 brands
  Brands: awaytravel.com, untuckit.com, framebridge.com, fentybeauty.com, dollarshaveclub.com, tuftandneedle.com, sundayriley.com, everlane.com, casper.com, liquid-iv.com, kyliecosmetics.com, skims.com, warbyparker.com, purple.com, harrys.com, aloyoga.com, olaplex.com
- **Agent identifies the correct product** (RDY-008): FAIL on 17/17 brands
  Brands: awaytravel.com, untuckit.com, framebridge.com, fentybeauty.com, dollarshaveclub.com, tuftandneedle.com, sundayriley.com, everlane.com, casper.com, liquid-iv.com, kyliecosmetics.com, skims.com, warbyparker.com, purple.com, harrys.com, aloyoga.com, olaplex.com
- **Agent extracts the correct product price** (RDY-006): FAIL on 15/17 brands
  Brands: awaytravel.com, untuckit.com, framebridge.com, fentybeauty.com, tuftandneedle.com, sundayriley.com, everlane.com, casper.com, liquid-iv.com, kyliecosmetics.com, skims.com, warbyparker.com, purple.com, harrys.com, aloyoga.com
- **Agent determines stock availability** (RDY-007): FAIL on 15/17 brands
  Brands: awaytravel.com, untuckit.com, framebridge.com, fentybeauty.com, tuftandneedle.com, sundayriley.com, everlane.com, casper.com, liquid-iv.com, kyliecosmetics.com, skims.com, warbyparker.com, purple.com, harrys.com, aloyoga.com
- **Variant selectors (size/color) use semantic HTML** (RDY-015): FAIL on 9/17 brands
  Brands: untuckit.com, framebridge.com, fentybeauty.com, liquid-iv.com, skims.com, warbyparker.com, purple.com, harrys.com, aloyoga.com

## Checks all brands passed
- No hidden prompt injection in page content (RDY-016)
- Agent gives a consistent shipping answer (RDY-010)
- Agent gives a consistent return window (RDY-009)

## Checks all brands failed
- Agent can complete Add-to-Cart flow (RDY-017)
- Agent identifies the correct product (RDY-008)

## Per-layer averages across all brands
- **Data**: avg 81.5%, range 27.1%–100.0%
- **Extraction**: avg 36.3%, range 32.3%–66.7%
- **Interaction**: avg 35.3%, range 0.0%–50.0%
- **Security**: avg 100.0%, range 100.0%–100.0%

## Per-brand top weakness
- **awaytravel.com** (71.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **untuckit.com** (68.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **framebridge.com** (68.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **fentybeauty.com** (68.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **dollarshaveclub.com** (66.7/100): weakest layer = Interaction, top fail = Product structured data present with price + availability
- **tuftandneedle.com** (66.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **sundayriley.com** (66.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **everlane.com** (66.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **casper.com** (66.0/100): weakest layer = Extraction, top fail = Agent extracts the correct product price
- **liquid-iv.com** (63.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **kyliecosmetics.com** (61.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **skims.com** (60.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **warbyparker.com** (58.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **purple.com** (58.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **harrys.com** (55.0/100): weakest layer = Interaction, top fail = Agent extracts the correct product price
- **aloyoga.com** (38.0/100): weakest layer = Interaction, top fail = Product structured data present with price + availability
- **olaplex.com** (34.6/100): weakest layer = Interaction, top fail = Product structured data present with price + availability
