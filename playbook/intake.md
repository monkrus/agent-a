# Discovery Intake

Send before the scoping call, or walk through live. Answers drive pack
selection, effort estimate, and the fixed quote.

## The agent
1. What does the agent do, in one paragraph? Who uses it and what's the worst
   thing it could plausibly do wrong? (Their answer to the second half tells
   you where the critical-severity surface is.)
2. Single agent or multi-agent? Which model(s)/provider(s)? Any fallback model?
3. How do users interact: chat, voice, API, embedded UI?
4. What's the shipping milestone this audit is ahead of? (launch, demo day,
   enterprise pilot, SOC2 push)

## Tool surface
5. List every tool/function the agent can call, with a one-line description.
6. Which tools can write, delete, send, or spend? (money, email, data mutation)
7. Any MCP servers? Which, and are any third-party?
8. What external content does the agent ingest? (retrieved docs, web pages,
   email bodies, calendar events, file uploads) — every item here is an
   injection surface.

## Observability & access
9. Do you have trace logging? (LangSmith, Braintrust, custom, none)
10. Is there a staging environment I can hit without affecting production or
    real users? If not, can you export 50-100 representative traces?
11. Any existing evals/tests for agent behavior? What do they cover?

## Constraints
12. Anything contractually or ethically off-limits to test? (real customer
    data, third-party rate limits, production side effects)
13. NDA: yours, mine, or none needed?
14. Timeline pressure — hard date the report must land by?

## Internal scoring (do not send)
- Tools with write/spend scope: each one ≈ +0.5 day
- No staging env: +1 day (trace-only audits are slower)
- Voice layer: +1 day
- Multi-agent: +1-2 days
- Base Tier 1 = 4 days effort. Quote = effort x day-rate, rounded to the tier.
- If answers to Q5-Q8 reveal >15 tools or heavy third-party MCP use, quote
  Tier 2 from the start — Tier 1 won't fit.
