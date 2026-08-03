# Most DTC Brands Don't Know AI Shopping Agents Exist. Their Product Pages Prove It.

---

*Data from 21 DTC brand scans, July 2026. [agent-a](https://github.com/monkrus/agent-a), open-source scanner.*

---

We keep talking about whether e-commerce sites are "ready" for AI shopping agents. But after scanning 21 Shopify brands, the more honest question is: **do they even know agents are coming?**

The data says no.

**Only 7 out of 21 brands have an llms.txt file.** This is a simple text file at the site root that tells AI agents what the site is and how to navigate it. It takes 15 minutes to create. A third of brands have one. The rest offer agents zero guidance — show up and figure it out yourself.

**MeUndies actively blocks AI agents.** Their WAF returns 403 to bot-like user-agents. They're not failing to accommodate agents — they're refusing them at the door. This is a $50-75M brand choosing to be invisible to every AI shopping assistant on the market.

**ThirdLove deployed AI personalization but has no structured data for AI agents.** They partnered with Bloomreach in 2025 to use Loomi AI across their customer experience. They understand AI. But their product page ships no JSON-LD with price and availability — the one thing an AI shopping agent needs to read the page. They're investing in AI for their customers while blocking AI that brings customers.

**9 out of 21 brands use variant selectors that agents can't parse.** Size pickers built with `<div>` elements. Color swatches that are invisible to anything that doesn't execute JavaScript. Two-step selectors where clicking one option reveals another with no programmatic signal. These aren't bugs — they're design choices made without agents in mind, because nobody was thinking about agents.

**Zero brands have been caught injecting prompts to manipulate agents.** RDY-016 (prompt injection) passed across all 21 scans. This sounds like good news until you realize what it means: nobody is trying to manipulate agents because nobody thinks agents are visiting. The day brands start worrying about what agents tell shoppers is the day they'll start caring about agent readiness. That day hasn't arrived.

## The awareness gap in one stat

The average agent-readiness score across our 21 brands is **74.3**. But that average hides a split:

- **Data layer** (can agents read the page?): ~80% pass rate
- **Interaction layer** (can agents buy from the page?): ~15% pass rate

Most brands accidentally got the data layer right — JSON-LD and server-rendered prices were built for SEO, not agents. The interaction layer, which requires intentional agent accommodation, is where scores collapse. Nobody built their Add-to-Cart flow thinking "will a Claude agent be able to click this?"

## What awareness looks like

It looks boring. It looks like a 20-line llms.txt file. A `<select>` element instead of a custom JavaScript swatch picker. A JSON-LD block that matches the price humans see. A WAF rule that doesn't 403 GPTBot.

None of this is hard. All of it requires knowing that AI agents exist, that they're trying to shop your site right now, and that they fail silently — no error page, no abandoned cart metric, no customer complaint. The agent just leaves and tries the next brand.

The brands that figure this out first won't build anything new. They'll just stop blocking the traffic that's already there.

---

*21 brands scanned with [agent-a](https://github.com/monkrus/agent-a). 26 checks across data, extraction, interaction, and security. Open source at [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a). Built by [Sergei Stadnik](https://github.com/monkrus).*
