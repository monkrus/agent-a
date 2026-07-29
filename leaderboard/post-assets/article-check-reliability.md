# Every Check We Run, How We Prove It, and Why You Can Verify It Yourself

---

We built an agent-readiness scanner. Before you trust the score, you should know exactly what each check does, what evidence it produces, and how you can verify every result without our tool.

This is the full transparency table. No black boxes.

---

## Static checks — deterministic, reproducible, zero AI

These checks parse your HTML. Same page, same result, every time. No model, no randomness, no interpretation. You can verify every one by viewing your page source.

| Check | What we test | Evidence | How you verify it yourself |
|-------|-------------|----------|---------------------------|
| **RDY-001** Product JSON-LD | Is there a `schema.org/Product` JSON-LD block with `offers.price` and `availability`? | We show the exact JSON-LD we found (or didn't find) | View source, Ctrl+F for `application/ld+json`, look for `"@type": "Product"` |
| **RDY-002** Price in HTML | Is a currency-formatted price in the server-rendered HTML? | We show the regex match and the price string | `curl -s <url> \| grep -oP '[$]\d+'` — if nothing comes back, agents without JS can't see your price |
| **RDY-003** robots.txt | Does robots.txt block GPTBot, PerplexityBot, Google-Extended, or OAI-SearchBot? | We show which user-agents are blocked and for which paths | Visit `yoursite.com/robots.txt` and read it |
| **RDY-004** Return policy | Is a return/refund policy linked and served as readable text? | We show whether a policy link was found and if it returned text | Click "Return Policy" on your site. If it's a PDF or image, agents can't read it |
| **RDY-005** llms.txt present | Does `yoursite.com/llms.txt` exist? | HTTP status code: 200 or 404 | Visit `yoursite.com/llms.txt` in your browser |
| **RDY-011** llms.txt quality | Does llms.txt contain product paths, policy links, sitemap, and valid URLs? | We list which sections are present and which are missing | Read your llms.txt — does it have product catalog paths, policy links, and a sitemap URL? |
| **RDY-012** JSON-LD quality | Does JSON-LD include name, image, brand, description, price, currency, and availability URL? | We list every missing field | Paste your JSON-LD into [Google's Rich Results Test](https://search.google.com/test/rich-results) |
| **RDY-013** JS render ratio | Can agents access product data without executing JavaScript? | We compare raw HTML content length vs. what we know is on the page. If structured data exists, we pass the page regardless of JS ratio | View source vs. rendered page — if the price only appears after JS runs, agents without a browser can't see it |
| **RDY-014** ATC semantics | Is there a `<form>` or `<button>` with cart/purchase semantics? | We show the matched element's tag, name, aria-label | View source, search for "add to cart" — is it a `<button>` in a `<form>`, or a `<div onclick>`? |
| **RDY-015** Variant selectors | Do size/color options use `<select>`, `<input type="radio">`, or labeled fieldsets? | We show which selector type was found (or that none was found) | Inspect element on your size picker — `<select>` and `<input>` are semantic, `<div class="swatch">` is not |
| **RDY-016** Prompt injection | Does the page contain hidden text designed to hijack AI agent behavior? | We show the exact pattern matched and where it was found (hidden element, HTML comment, invisible text) | View source, search for "ignore previous", "you are now", "disregard" in comments or hidden elements |
| **RDY-022** Guest checkout | Does checkout require login or account creation? | We check the checkout page for login walls | Go to checkout as a new visitor without logging in — can you proceed? |
| **RDY-023** Cart API | Does `/cart/add.js` respond? | HTTP status code from the endpoint | `curl -s yoursite.com/cart/add.js` — Shopify stores have this by default unless disabled |

**Reliability: 100%.** These are string matches, HTTP requests, and DOM queries. There is no model involved. Run them twice, get the same answer.

---

## Shopper extraction checks — real AI, measured statistically

These checks send your page content to Claude and ask it to extract a specific fact. We run each extraction **10 times** and measure two things:

- **Correctness:** Does the answer match ground truth (from your JSON-LD)?
- **Consistency:** Does the agent give the same answer every time?

We report the pass **rate**, not a binary pass/fail. If the agent gets the price right 7 out of 10 times, we report 70% — and that itself is a finding (your page is ambiguous to agents).

| Check | What we ask the AI | How we grade | Ground truth source | How you verify |
|-------|-------------------|-------------|-------------------|----------------|
| **RDY-006** Price extraction | "What is the price?" | Correctness — must match JSON-LD `offers.price` | Your own structured data | Compare what ChatGPT/Perplexity says your price is vs. what your JSON-LD declares |
| **RDY-007** Availability | "Is it in stock?" | Correctness — must match JSON-LD `offers.availability` | Your own structured data | Ask ChatGPT "Is [product] in stock?" and check against your site |
| **RDY-008** Product name | "What is the product name?" | Correctness — must match JSON-LD `name` or `<title>` | Your own structured data | Ask any AI agent to name the product and see if it matches your listing |
| **RDY-009** Return window | "How many days to return?" | Consistency — agent must agree with itself across 10 runs | No ground truth needed — we measure agreement | Ask the same question 5 times in ChatGPT. If you get different answers, your page is ambiguous |
| **RDY-010** Shipping cost | "What does shipping cost?" | Consistency — agent must give stable answers | No ground truth needed — we measure agreement | Same test: ask 5 times, see if the answer changes |

**Reliability: statistical.** Any single extraction run can vary — that's the nature of language models. That's exactly why we run 10 times. The pass *rate* is stable and reproducible. A page that scores 90% on price extraction will score 85-95% on the next scan, not 40%.

**Why this isn't AI slop:** We're not asking a model "is this page good?" and reporting its opinion. We're asking it a factual question with a known answer and checking whether it gets it right. The model is the test subject, not the judge. The grading is deterministic: extracted price matches JSON-LD price, or it doesn't.

---

## Browser agent checks — real browser, real clicks, video-level evidence

These checks launch a headless Chromium browser, navigate to your page, and let an AI agent decide what to click, type, and select — step by step. Each flow runs multiple times with majority-vote.

Every step is logged: what the agent saw, what it decided, what happened.

| Check | What the agent attempts | Max steps | Success criteria | How you verify |
|-------|------------------------|-----------|-----------------|----------------|
| **RDY-017** Add-to-Cart | Select a variant, click ATC, verify cart updated | 12 | Cart count > 0 or "Added to cart" confirmation detected, verified via Shopify `/cart.json` API | Add your own product to cart — did it take more than 3 clicks? |
| **RDY-018** Site search | From homepage: find search, type product name, find it in results | 10 | Landed on a search results page with product links | Use your site search. Is the search bar visible? Does it return the right product? |
| **RDY-019** Checkout reachable | After ATC: navigate to cart, click checkout, verify checkout form | 12 | Reached a page with `/checkout` URL or email/address input fields | Add to cart, go to checkout — how many steps? Any login walls? |
| **RDY-020** Homepage navigation | From homepage: use menus to find the product (no search) | 15 | Landed on the target product page URL | Can you find the product from your homepage using only menus in under 5 clicks? |
| **RDY-021** Product comparison | From product page: find related products, navigate to one | 10 | Landed on a different `/products/` URL | Scroll down — is there a "You may also like" section with clickable links? |

**Reliability: majority-vote.** Each flow runs multiple times. A flow passes if the majority of attempts succeed. This filters out one-off failures (slow page load, transient popup timing) and surfaces real, reproducible issues.

**Why this isn't AI slop:** The evidence is a step-by-step action log. "Step 1: clicked [aria-label='Band Size: 32']. Step 2: clicked [aria-label='Cup Size: B']. Step 3: clicked [aria-label='Add to Bag']. Step 4: clicked [aria-label='Add to Bag']. Step 5: clicked [aria-label='Add to Bag']. FAIL: stuck." That's not an opinion. That's a transcript. You can replay it.

---

## The three evidence tiers

| Tier | Checks | Evidence type | Reproducibility |
|------|--------|--------------|-----------------|
| **Deterministic** | 13 static checks | HTML parsing, HTTP requests, regex matches | 100% — same page, same result, always |
| **Statistical** | 5 shopper checks | N=10 extraction runs, correctness/consistency rates | ~95% stable — rates vary within a few percentage points |
| **Behavioral** | 5 browser checks | Step-by-step action logs from a real browser | Majority-vote across attempts — filters noise, surfaces real blocks |

Every check falls into one of these tiers. None of them ask a model "what do you think?" and report the answer. The static checks are math. The shopper checks use the AI as a test subject against known answers. The browser checks produce action logs you can read step by step.

---

## Why we open-sourced the scoring

The check definitions, weights, and scoring logic are public at [github.com/monkrus/agent-a](https://github.com/monkrus/agent-a). You can read every check's YAML definition, every scorer function, and every weight. The score is a weighted pass rate — `sum(weight * pass_rate) / sum(weights)` — not a proprietary algorithm.

We open-sourced it because a score you can't audit isn't a score. It's a sales pitch.

---

*Built by [Sergei Stadnik](https://github.com/monkrus). 23 checks, three evidence tiers, zero black boxes.*
