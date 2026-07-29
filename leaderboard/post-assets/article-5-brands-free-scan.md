# We Scanned 5 Premium DTC Brands in 50 Seconds for $0. None of Them Are Ready for AI Shopping Agents.

---

We built a free, static-only scanner -- 18 checks, no API calls, just HTML analysis. Then we pointed it at five brands that obsess over customer experience: Glossier, Allbirds, Gymshark, Drunk Elephant, and Brooklinen.

Every scan finished in under 10 seconds. Total cost: zero.

**The scores:**

| Brand | Score | What breaks |
|-------|-------|-------------|
| Glossier | 83.7 | JSON-LD says "InStock" instead of the schema.org URL. One string. |
| Allbirds | 79.1 | Size picker is a JS widget. No cart API. Agents can't buy shoes. |
| Brooklinen | 79.1 | Same story -- JS swatches for sheet sizes, cart API disabled. |
| Drunk Elephant | 76.0 | No llms.txt, no cart API, no related products section. |
| Gymshark | 74.7 | No llms.txt, no cart API, no search form, JS-only size picker. |

**The pattern is identical across all five: agents can read the page but can't buy from it.**

Every brand has clean structured data. Prices are server-rendered. No prompt injection. Robots.txt is open. The data layer works. But the moment an agent tries to do something -- pick a size, add to cart, search for another product -- it hits a wall of custom JavaScript that has no semantic meaning.

Gymshark is the most striking. Three million monthly visits, Gen Z audience (the demographic most likely to use AI shopping agents), and their homepage has no search form an agent can find. The size picker is invisible to non-browser clients. The cart API returns nothing. An agent trying to buy a $30 t-shirt would fail at every interaction step.

**The revenue math is uncomfortable.** If 5-15% of traffic is AI-referred (Gartner's 2027 projection), and these agents convert at 2-4% when they work, these five brands are collectively leaving $82,000 to $491,000 per month on the table. Not because their products are bad or their pages are ugly -- because their size pickers use `<div>` instead of `<select>`.

**The fix is boring.** Semantic HTML. A 20-line llms.txt file. Re-enabling the Shopify cart API that was on by default. The brands scoring highest in our 17-brand leaderboard (Kylie Cosmetics: 100, Framebridge: 96) aren't doing anything exotic. They're just using `<select>` elements and standard forms.

The gap between "a beautiful page" and "a page agents can shop" is about a day of developer time. The question is which brands close it first.

---

*Scanned July 2026 with [agent-a](https://github.com/monkrus/agent-a). 18 static checks, $0 cost. Scanner is open source.*
