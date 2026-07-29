We sent an AI shopping agent to buy a bra from SKIMS and ThirdLove.

It couldn't buy from either.

But the reasons are opposite — and that's the interesting part.

SKIMS: 70/100. ThirdLove: 78/100.

SKIMS has perfect structured data. Every field an agent needs — price, availability, variants — is there. But the size picker is a HeadlessUI popover with randomly generated IDs. The cart API returns 410 Gone. There's no llms.txt. The agent extracted the price correctly 10/10 times, then got stuck clicking "Add to Bag" in a loop because the variant selection never registered.

ThirdLove is the opposite. Semantic HTML selects for sizes. Working cart API. An llms.txt file that actually guides agents. Site search works. Navigation works. But their JSON-LD is missing one field: availability. The agent can tell you the bra costs $72 but not whether it's in stock. And a persistent popup blocked it from ever reaching the Add to Cart button.

Between the two of them, they have all the pieces. ThirdLove's infrastructure + SKIMS's data would score 95+.

ThirdLove's fix: add one field to their JSON-LD. Thirty minutes.
SKIMS's fix: replace popovers with select elements. Half a day.

Neither has done it yet.

23 checks. Real browser agent. Real extraction. Open-source scanner: github.com/monkrus/agent-a

#ecommerce #AI #DTC #Shopify #agentcommerce
