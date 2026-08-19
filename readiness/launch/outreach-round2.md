# Cold Outreach Round 2 — Plan

## Target list
41 verified Shopify DTC stores from `targets/candidates.csv`
All uncontacted as of Aug 2026.

## Categories
- Apparel (7): Cuts, Cuyana, MeUndies, Tentree, Pura Vida, Chubbies, ThirdLove
- Beauty (6): Tatcha, Function of Beauty, DedCool, Native, ColourPop, Summer Fridays
- Home (4): Schoolhouse, Boll & Branch, Burrow, Bearaby
- Supplements (7): Moon Juice, Magic Spoon, Transparent Labs, Ghost, Vital Proteins, Goli, AG1
- Outdoor (6): Big Agnes, Snow Peak, Rumpl, Cotopaxi, Outdoor Voices, MiiR
- Pet (4): Gunner Kennels, Ruffwear, Zesty Paws, Wild One
- Footwear (7): Greats, Koio, Rothy's, Birdies, Thursday Boots, Nisolo, Atoms

## Approach
1. Run mock scans on all 41 (free, instant, $0)
2. Generate personalized outreach emails from scan findings
3. Send via personal Gmail — not bulk, not automated
4. Follow up once after 5 days if no reply

## Command to batch scan
```bash
# From repo root
SHOPPER=mock python -m readiness.batch targets/candidates.csv
```
This generates scan results + outreach emails in outreach/ directory.

## Email template (already in outreach.py)
Short human email (~65 words) referencing specific findings.
Separate detailed scan report as attachment or link to /r/<scan_id>.

## Priority order (highest value first)
1. **AG1, Vital Proteins, Magic Spoon** — high traffic supplements, likely high agent traffic
2. **Rothy's, Thursday Boots** — already tested interaction with Manifest collab
3. **Tatcha, ColourPop, Summer Fridays** — beauty = high search/recommendation volume
4. **Cotopaxi, Outdoor Voices** — strong DTC brands, likely sophisticated e-comm teams
5. Everyone else

## Success metrics
- 10% reply rate = 4 conversations
- 2% conversion to paid scan = 1 paying customer
- 1 case study from the batch = portfolio value
