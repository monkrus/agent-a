# Are you even aware that AI shopping agents are visiting your store right now?

I built an open-source scanner that checks how well product pages work for AI shopping agents (ChatGPT, Claude, Perplexity — the tools that browse sites, extract prices, and try to buy stuff on behalf of users).

I've scanned 21 Shopify DTC brands so far. The short version: most stores have no idea this is happening.

**Some things I found:**

- Only 7 out of 21 brands have an llms.txt file (a simple text file that tells AI agents how to navigate your site — takes 15 min to set up)
- One brand ($50-75M revenue) actively blocks AI agents at the WAF level — returns 403 to bot user-agents. Completely invisible to AI shoppers.
- Another brand spent money deploying AI-powered personalization on their site, but ships no structured data that AI shopping agents can actually read. They understand AI. They just don't know agents are trying to shop their pages.
- 9 out of 21 brands use JavaScript size/color pickers that agents can't interact with at all

**The split that surprised me:**

- Can agents READ the page? ~80% pass rate (mostly because JSON-LD was built for SEO)
- Can agents BUY from the page? ~15% pass rate

Most stores accidentally got the data layer right. The interaction layer — where revenue actually happens — is broken because nobody built their Add-to-Cart flow thinking "will an AI agent be able to click this?"

The worst part: agents fail silently. No abandoned cart. No error page. No customer complaint. They just leave and try the next store.

Scanner is open source if anyone wants to check their own site: [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a)

Curious — is anyone here actually thinking about this? Or is it not on your radar yet?
