# LinkedIn Post — Latest Findings (August 2026)

I've scanned 21 DTC brands to see how well AI shopping agents can read and buy from their sites.

The finding that keeps showing up: most stores don't know this is happening.

Here's what I mean.

---

MeUndies scored 25.6 out of 100. Lowest I've ever recorded. Their WAF returns 403 to AI agent user-agents. No structured data. No server-rendered price. An AI shopping agent visiting meundies.com can't see the product, can't read the price, and gets blocked if it tries.

This is a $50-75M brand that is invisible to every AI shopping assistant on the market.

ThirdLove scored 71/100. In 2025, they partnered with Bloomreach to deploy AI-powered personalization across their site. They understand AI. But their product pages ship no JSON-LD with price or availability — the one thing an AI shopping agent needs to read the page. They're investing in AI for their customers while blocking AI that brings customers.

Rothy's scored 73/100. Every data check passes — JSON-LD, llms.txt, semantic selectors, cart API. An agent can read the price, confirm stock, extract the return policy perfectly. Then it tries to pick size 8 and add to cart. Fails. Every browser interaction flow fails. Readable but not shoppable.

Thursday Boots scored 65/100. Agents extract the wrong price 10 out of 10 times. The structured data says one number, the page shows another.

---

Across all 21 brands, the pattern is the same:

→ Can agents READ the page? ~80% pass rate.
→ Can agents BUY from the page? ~15% pass rate.

Most brands accidentally got the data layer right — JSON-LD and server-rendered prices were built for SEO, not for agents. The interaction layer, which requires intentionally thinking about AI agents, is where everything breaks.

And here's the part nobody talks about: agents fail silently. There's no abandoned cart metric. No error page. No customer complaint. The agent just leaves and tries the next brand that works.

The brands that fix this aren't building anything exotic. They're adding a JSON-LD block. Using <select> instead of custom JavaScript swatches. Whitelisting GPTBot in their WAF. Boring changes. The kind that take a day and nobody writes a press release about.

But those are the brands that will capture the 5-15% of e-commerce traffic that Gartner projects will be AI-referred by 2027.

The scanner is open source: github.com/monkrus/agent-a

---

*What's your take — are you thinking about AI agent readiness, or is this not on your radar yet?*
