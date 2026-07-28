---
Subject: SKIMS scored 87/100 for AI shopping agents — 3 fixes would get you to 95+

Hi --

I built an open-source scanner that tests how well AI shopping agents (ChatGPT, Perplexity, Claude) can shop on product pages. I ran a 17-check scan against the Everyday Cotton Ultimate Teardrop Push-Up Bra on skims.com.

SKIMS scored 87/100 — 6th out of 17 DTC brands.

Your data layer is strong: JSON-LD is complete, prices are server-rendered, agents extract the correct price and availability 100% of the time. But three issues hold the score back:

- **The band/cup size picker defeats agents.** Non-semantic JS widgets mean agents can't select a size. No `<select>`, no ARIA roles they can parse. They click the same button repeatedly and give up.
- **No llms.txt.** Agents have zero context for how to navigate or interact with SKIMS. A 20-line file at your site root fixes this.
- **Shipping answers are inconsistent.** Agents extract "free on orders $75+" 80% of the time but get confused by secondary references the other 20%.

Three targeted fixes — semantic variant selectors, llms.txt, and shipping text cleanup — would move the score to 95+. Most take under a day.

As AI shopping agents go from novelty to real purchase channel, these gaps become lost conversions. Happy to walk through the specifics if this is on your roadmap.

-- Sergei Stadnik
sergeigodev@gmail.com
github.com/monkrus/agent-a
---
