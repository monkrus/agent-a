# Posts — August 2026: The Agency Pattern

---

## Medium Article

### Your Shopify Agency Might Be Blocking AI Shopping Agents Across Every Client Site

**Why I built this**

A few months ago I started watching how AI shopping agents — ChatGPT, Claude, Perplexity — actually interact with e-commerce sites. Not the demos. The real thing: an agent visiting a product page, trying to read the price, pick a size, add to cart, and check out.

They fail constantly. And nobody notices, because agents fail silently. No abandoned cart metric. No error page. No customer complaint. The agent just leaves and tries the next store.

I couldn't find a tool that tested this systematically, so I built one. agent-a is an open-source scanner that runs 26 checks across four layers of agent readiness:

1. **Data** — can agents find and read the page? (JSON-LD, server-rendered prices, robots.txt, llms.txt, sitemap)
2. **Extraction** — can agents extract correctly? (price, availability, product name, return policy, shipping — 10 runs each to measure consistency, not just one-shot accuracy)
3. **Interaction** — can agents act on the page? (Add-to-Cart flow, checkout, site search, navigation, variant selectors, cart API)
4. **Security** — is the page safe from agent manipulation? (hidden prompt injection detection)

Most people aren't thinking about this yet. Out of 28 brands I've scanned, zero had ever tested their site from an AI agent's perspective. The concept of "agent readiness" doesn't exist in their vocabulary — they optimize for Google, for mobile, for page speed. Not for the AI that's trying to buy their product.

**The agency pattern**

The most interesting finding wasn't about any single brand. It was about an agency.

I scanned 4 clients of the same Shopify Plus agency. All 4 returned 403 to AI agent user-agents.

Lunya (77.6/100), Kirna Zabête (73), Cara Cara (65.5), Kashwère (64.2). Four different brands, four different categories — sleepwear, luxury fashion, resort wear, home textiles. Same agency built all four sites. Same WAF configuration blocking ChatGPT, Claude, and Perplexity from visiting.

This isn't a coincidence. It's a setting — probably in Cloudflare or Shopify's CDN config — that the agency applied once and deployed everywhere. One checkbox is making four brands invisible to every AI shopping assistant on the market.

When a single brand blocks agents, it's their problem. When an agency does it, it's a portfolio-wide pattern. The top Shopify Plus agencies manage 20-50 client sites. If their default build template blocks AI agents, every client launches with the same blind spot.

**The numbers across 28 brands**

- Can agents READ the page? ~80% pass rate.
- Can agents BUY from the page? ~15% pass rate.
- Browser interaction checks (add-to-cart, search, checkout, navigation): 5% pass rate on fit-dependent products.
- 100% of brands pass prompt injection checks — nobody is trying to manipulate agents because nobody knows agents are visiting.

The gap between "readable" and "shoppable" is where revenue gets lost. Most brands got the data layer right accidentally — JSON-LD was built for SEO, not agents. The interaction layer, where purchase actually happens, was built for humans only.

**The fix is infrastructure, not code**

For individual brands, the fixes are boring: add a JSON-LD block, use `<select>` instead of custom JS swatches, reconcile displayed prices with structured data.

For agencies, the fix is even simpler: update the WAF allowlist in your deployment template. Whitelist GPTBot, ClaudeBot, PerplexityBot. One change, every client benefits, zero downside.

The agencies that add "AI agent readiness" to their build checklist will have a real differentiator. The ones that don't will keep launching sites that block the fastest-growing source of e-commerce traffic.

Scanner is open source: [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a)

*Built by [Sergei Stadnik](https://github.com/monkrus)*

---

## LinkedIn Post

Three months ago I noticed something: AI shopping agents — ChatGPT, Claude, Perplexity — fail constantly on e-commerce sites. They can't read prices, can't pick sizes, can't add to cart. And nobody notices because agents fail silently. No error page. No abandoned cart metric. They just leave.

I couldn't find a tool that tested this, so I built one.

agent-a runs 26 checks across 4 layers:
→ Data: can agents find and read the page?
→ Extraction: do they get the price and product right?
→ Interaction: can they pick a size and buy?
→ Security: is anyone trying to manipulate agents?

I've scanned 28 DTC brands. The finding I didn't expect: agency-level patterns.

I scanned 4 clients of the same Shopify Plus agency. All 4 block AI agents.

Lunya: 77.6/100
Kirna Zabête: 73/100
Cara Cara: 65.5/100
Kashwère: 64.2/100

Every site returns 403 to ChatGPT, Claude, and Perplexity. Same WAF config, deployed across the entire portfolio. One setting is making four brands invisible to AI shopping assistants.

When an agency does this, it's not one site — it's 20-50 client sites with the same blind spot baked into the build template.

The fix takes five minutes: whitelist GPTBot, ClaudeBot, PerplexityBot in the CDN config. But first someone has to notice — and right now, almost nobody is thinking about AI agent readiness. Zero of the 28 brands I've scanned had ever tested this.

Scanner is open source: github.com/monkrus/agent-a

Is your agency checking for this?

---

## X Post

3 months ago I noticed AI shopping agents fail silently on e-commerce sites. No error, no abandoned cart — they just leave. Nobody was testing for this.

So I built an open-source scanner. 26 checks across 4 layers: data, extraction, interaction, security.

28 brands scanned. The surprise: I found 4 clients of the same Shopify Plus agency — all 4 return 403 to AI agents. Same WAF config. One setting blocking ChatGPT, Claude, and Perplexity from every client site.

The fix is one allowlist update. But first someone has to notice.

github.com/monkrus/agent-a

---

## Reddit Post (r/shopify or r/ecommerce)
I built a scanner to test if AI shopping agents can actually buy from your store. 28 brands later, almost none are ready.

A few months ago I started watching how AI agents (ChatGPT, Claude, Perplexity) interact with Shopify stores. Not the hype — the actual experience. An agent visits your product page, tries to read the price, pick a size, add to cart, check out.

They fail. A lot. And you'd never know because there's no error, no abandoned cart metric, no bounce tracked. The agent just leaves and tries your competitor.

I couldn't find a tool that tested this from the agent's perspective, so I built one. It runs 26 checks across 4 layers:

1. **Data** — can agents find the page? (JSON-LD structured data, server-rendered prices, robots.txt, llms.txt, sitemap)
2. **Extraction** — can they read it correctly? (price, availability, product name, return policy, shipping — each tested 10 times for consistency)
3. **Interaction** — can they buy from it? (Add-to-Cart flow, checkout, search, navigation, variant selectors, cart API)
4. **Security** — is anyone injecting hidden prompts to manipulate agents?

**28 brands scanned. What I found:**

- ~80% pass rate on "can agents read the page"
- ~15% pass rate on "can agents buy from the page"
- Zero brands had ever tested their site from an agent's perspective
- The lowest score: 25.6/100 — a $50-75M brand that blocks agents at the WAF, has no structured data, and no server-rendered price. Completely invisible.

**The surprise: agency-level patterns.** I scanned 4 clients built by the same Shopify Plus agency. All 4 return 403 to AI agent user-agents. Same WAF configuration across the entire portfolio. One setting is blocking ChatGPT, Claude, and Perplexity from every site they built.

**If you want to check your own store:**

1. Does your site return 200 or 403 when accessed with a GPTBot user-agent?
2. Does your product page have JSON-LD structured data with price and availability?
3. Can a non-browser client find an Add-to-Cart button in your DOM?
4. Do your size/color pickers use `<select>` elements or custom JS widgets?

The scanner is open source: [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a)

Has anyone else started thinking about this, or is it completely off your radar?

### 