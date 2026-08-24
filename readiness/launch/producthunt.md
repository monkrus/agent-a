# Product Hunt Launch — Agent Readiness Scanner

## Tagline (60 chars max)
Find out if AI shopping agents can buy from your store

## Description (260 chars max)
Free scanner that checks if ChatGPT, Gemini, and AI shopping agents can read, extract, and buy from your product pages. 40 checks across 6 categories: data, extraction, interaction, security, resilience, protocol discovery. Paste a URL, get a score in 30 seconds.

## Maker Comment (first comment on the post)

Hey PH! I built this because I kept hearing the same thing from Shopify merchants: "How do I know if AI agents can find my products?"

The answer was always: you don't, until you lose the sale.

AI shopping agents (ChatGPT, Gemini, Perplexity) are reading product pages right now. But most stores fail invisibly: JS-only prices that agents can't see, missing structured data, policies agents can't parse, checkout flows they can't navigate.

This scanner runs 40 checks across 6 categories:
- **Read**: Can agents find your page and parse the data?
- **Extract**: Do they get the right price, availability, product name?
- **Act**: Can they add to cart and reach checkout?
- **Safe**: Is your page protected from prompt injection and UGC manipulation?
- **Resilient**: Does it hold up under agent traffic across multiple AI crawlers?
- **Protocol-ready**: Does it speak MCP, A2A, OAuth, and other agent protocols?

We actually send a real AI agent to your page multiple times and grade its accuracy. Not just static analysis.

Free scan gives you the score + headline findings. Paid report ($49) adds evidence, sample agent responses, and copy-paste code fixes.

Built with Claude, deployed on Render. Would love feedback on what checks to add next.

## Topics/Categories
- Developer Tools
- E-Commerce
- Artificial Intelligence
- Shopify
- SaaS

## Thumbnail / Logo direction
Dark background, score circle (like a Lighthouse score), "40 checks / 6 categories" text. Use the OG image style already in the app.

## Gallery screenshots needed
1. Landing page with scan form
2. Live scan streaming results
3. Final score with revenue impact
4. Full report with check details and fix recipes
5. Shareable results page with OG image

## Launch day checklist
- [ ] Deploy to production (Render)
- [ ] Set real Stripe price ($49)
- [ ] Test full flow: scan -> results -> checkout -> email
- [ ] Submit PH listing (schedule for Tuesday 12:01 AM PT)
- [ ] Post maker comment immediately after launch
- [ ] Share on Twitter/LinkedIn with scan result screenshots
- [ ] Have 3-5 example scan results ready to share (from leaderboard brands)
- [ ] Monitor PH comments and reply within 15 min
