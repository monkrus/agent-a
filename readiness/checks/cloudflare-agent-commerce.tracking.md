# Cloudflare Agent Commerce — Spec Tracking for New Checks
# Created: 2026-08-13
# Status: WATCHING — specs not final, no checks to implement yet

## Context

Cloudflare announced (Aug 2026) two primitives for agentic commerce:
1. **Agent Identity** — stable web-addressable ID per agent, tied to a CF account
2. **Agent Wallet** — stablecoins, spending caps, merchant whitelisting, tx limits
3. **Monetization Gateway** — two-sided marketplace connecting agent wallets to merchant endpoints

Source: cloudflare.com/press/press-releases/2026/cloudflare-gives-ai-agents-an-identity-and-a-wallet/

## Candidate checks to add when specs ship

### CHECK 1: Agent identity verification endpoint
- **Layer**: Data (agent-access)
- **What to detect**: Does the site publish a `.well-known/agent-verification` or similar manifest that tells agents how to present identity?
- **Signal**: HTTP GET to `.well-known/` path, or `<meta>` tag, or response header (e.g., `CF-Agent-Auth: supported`)
- **Severity**: medium (early adopter advantage, not yet critical)
- **Watch for**: Cloudflare docs on "Monetization Gateway" merchant setup — the merchant-side config will reveal the discoverable format
- **Blocked on**: Cloudflare hasn't published the spec yet

### CHECK 2: Agent-compatible payment flow
- **Layer**: Interaction (agent-checkout)
- **What to detect**: Can an agent complete a purchase without a full browser session? Does the checkout accept programmatic payment (API-based, not form-fill)?
- **Signal**: Presence of checkout API endpoints, headless-compatible payment forms, or CF Monetization Gateway integration
- **Severity**: high (agents with wallets can't spend if checkout requires manual form-fill)
- **Existing coverage**: RDY-019 (checkout reachable), RDY-022 (guest checkout), RDY-023 (cart API) partially cover this. New check would test the payment step specifically.
- **Watch for**: CF wallet integration SDK/docs for merchants
- **Blocked on**: Wallet payment flow spec not public

### CHECK 3: Verified-agent access policy
- **Layer**: Data (agent-access)
- **What to detect**: Does the site distinguish between verified agents (with CF identity) and anonymous bots? Does robots.txt or a new manifest grant different access to authenticated agents?
- **Signal**: New robots.txt directives, `.well-known/agents.json`, or CF-specific headers
- **Severity**: medium
- **Existing coverage**: RDY-003 (robots.txt), RDY-031 (rate limiting) test anonymous access. New check would test whether verified agents get better access.
- **Watch for**: robots.txt extensions or new standards for agent auth
- **Blocked on**: No standard exists yet

### CHECK 4: Monetization Gateway integration
- **Layer**: Interaction
- **What to detect**: Is the site connected to Cloudflare's Monetization Gateway (or similar agent commerce gateway)?
- **Signal**: CF script tags, response headers, DNS records pointing to CF gateway
- **Severity**: low initially, rising as adoption grows
- **Watch for**: CF dashboard docs, merchant onboarding flow
- **Blocked on**: Gateway not yet generally available

## How to monitor

1. **Cloudflare blog** — watch for "Monetization Gateway" merchant docs
2. **Cloudflare developer docs** — new `.well-known/` paths or headers
3. **robots.txt proposals** — IETF or community proposals for agent auth in robots.txt
4. **Shopify changelog** — Shopify is likely an early CF partner; watch for native integration
5. **W3C / IETF** — any "agent identity" or "machine-readable commerce" drafts

## Integration opportunity: scanner as verified agent

When CF agent identity is live, the scanner itself should authenticate as a
verified agent when probing sites. Benefits:
- Reduces false positives on RDY-003/RDY-031 (sites that block anon bots but allow verified agents)
- Enables a new check: "does this site treat verified agents differently?"
- Adds credibility when sharing scan results with merchants

## Timeline estimate

- **Now**: Track specs, reference in outreach (positioning only)
- **When CF publishes merchant SDK**: Prototype CHECK 1 (identity endpoint detection)
- **When wallets go live**: Prototype CHECK 2 (payment flow compatibility)
- **When adoption hits ~10% of Shopify stores**: Promote checks to scored (weighted in YAML)
