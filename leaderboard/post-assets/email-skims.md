---
Subject: SKIMS is the only intimates brand AI agents can actually shop — here's how to lock that in

Hi --

I'm a developer and a genuine SKIMS fan. I also build tools for AI commerce, and I ran into something I thought your team would want to know.

I built an open-source scanner (agent-a) that tests how well AI shopping agents -- ChatGPT, Perplexity, Claude -- can shop on product pages. I scanned 17 major DTC brands and then went deeper into the intimates category.

Here's what I found: I tried to scan ThirdLove, Savage X, CUUP, Knix, Negative, Lively, and Parade. Every single one blocked the request -- 403, 429, or redirect loops. Their pages are completely invisible to AI agents. No price, no product data, nothing.

SKIMS is the only intimates brand that actually serves the page. Your JSON-LD is complete, prices are server-rendered, and agents extract the correct price and availability 100% of the time. You scored 87/100 -- 6th out of 17 DTC brands overall.

Four things keep it from being near-perfect:

1. The band/cup size picker uses HeadlessUI popovers (64 instances, zero `<select>` elements). Agents can't select a size -- they click the same button repeatedly and give up.
2. No llms.txt file. Agents have zero context for how to navigate SKIMS. A 20-line file at your site root fixes this.
3. Shipping text appears in two locales (USD and AUD) in the same page source. Agents extract "free on $75+" 80% of the time but get confused by the AUD reference the other 20%.
4. /cart/add.js returns 410 Gone. The standard Shopify cart API is disabled, so agents can't add to cart programmatically.

I wrote up specific fixes with code for all four -- semantic `<select>` elements for the size picker, a ready-to-use llms.txt, a `<template>` pattern for the shipping text, and the cart API re-enable. About a day of dev work total, projected to move the score to 97+.

You're already ahead of every competitor in this category by a wide margin, simply because you serve the page. These fixes would make SKIMS the first intimates brand that AI agents can actually shop end-to-end -- before anyone else even shows up.

Happy to share the full fix document or walk through it with your engineering team.

-- Sergei Stadnik
sergeigodev@gmail.com
github.com/monkrus/agent-a
---
