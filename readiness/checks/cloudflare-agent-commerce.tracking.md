# Cloudflare Agent Commerce — Spec Tracking for New Checks
# Created: 2026-08-13
# Updated: 2026-08-18 — specs now public, RDY-032 implemented
# Status: PARTIALLY IMPLEMENTED — x402 signal check live (RDY-032), deeper checks pending GA

## Context

Cloudflare announced (Aug 4, 2026) three primitives for agentic commerce:
1. **Agent Identity** — stable web-addressable ID per agent via Web Bot Auth keypairs + cloudflare.pay handles
2. **Agent Wallet** — two-tier: Account Wallets (human-funded) → Virtual Wallets (per-agent, capped). Stablecoins (USDC) on Base, Ethereum, Polygon, Solana, etc.
3. **Monetization Gateway** — seller-side product: charge per-request for APIs, pages, MCP tools via x402/MPP

Sources:
- blog.cloudflare.com/wallets/
- blog.cloudflare.com/monetization-gateway/
- blog.cloudflare.com/x402/
- developers.cloudflare.com/agents/tools/payments/x402/
- developers.cloudflare.com/agents/tools/payments/mpp/

## Protocol specs (now public)

### x402 protocol (HTTP 402 Payment Required)
1. Client requests resource → server returns **HTTP 402** with `PAYMENT-REQUIRED` header (base64: price, token, network, merchant address)
2. Client signs payment → retries with `PAYMENT-SIGNATURE` header
3. Server verifies via facilitator (`POST /verify`, `POST /settle`) → returns resource + `PAYMENT-RESPONSE` header
4. Merchant never holds funds; facilitator processes on-chain settlement

### MPP (Machine Payments Protocol)
- Backwards-compatible with x402
- Extends to support Stripe cards + custom payment methods alongside stablecoins
- Supports charge, session, and subscription payment models
- Same HTTP 402 flow with payment challenges in auth headers

### Seller-side integration
- **Monetization Gateway**: configure rules via CF dashboard, API, or Terraform
- **x402-proxy Worker template**: sits in front of HTTP backend, handles payment verification
- **x402-hono middleware**: `paymentMiddleware("0xAddr", {"/premium": {price: "$0.10", network: "base-sepolia"}})`
- **Config**: `wrangler.jsonc` with `PAY_TO`, `NETWORK`, `PROTECTED_PATTERNS`

## Current status (Aug 2026)

| Component | Status |
|---|---|
| x402 protocol spec | Public, x402.org |
| x402 Foundation | Launched with Coinbase |
| Monetization Gateway | Waitlist / early access |
| Cloudflare Wallets | Announced, cloudflare.pay handles claimable, wallets not yet funded |
| Shopify integration | Not announced |

## Implemented checks

### RDY-032: x402 / agent wallet compatibility (LIVE)
- **Layer**: Interaction (agent-checkout)
- **Type**: static, weight 2, severity medium
- **Detects**: x402 references, PAYMENT-REQUIRED/PAYMENT-SIGNATURE headers, MPP signals, Monetization Gateway markers, cloudflare.pay, .well-known/agent-verification
- **Current reality**: ~0% of Shopify stores will pass (protocol is too new). Forward-looking signal.
- **Fetch probe**: .well-known/agent-verification added to fetch.py

## Candidate checks (pending GA adoption)

### CHECK 1: Agent identity verification endpoint
- **Layer**: Data (agent-access)
- **What to detect**: Does the site publish a `.well-known/agent-verification` or Web Bot Auth manifest?
- **Signal**: HTTP GET to `.well-known/agent-verification`, or CF-Agent-Auth header
- **Severity**: medium
- **Status**: Fetch probe added (returns JSON or None). Promote to scored check when adoption > 5%.

### CHECK 2: Verified-agent access policy
- **Layer**: Data (agent-access)
- **What to detect**: Does the site grant different access to verified agents vs anonymous bots?
- **Signal**: robots.txt extensions, `.well-known/agents.json`, or CF-specific headers
- **Severity**: medium
- **Existing coverage**: RDY-003 (robots.txt), RDY-031 (rate limiting) test anonymous access
- **Blocked on**: No standard for agent auth in robots.txt yet

### CHECK 3: Active Monetization Gateway integration
- **Layer**: Interaction
- **What to detect**: Is the site actively using Monetization Gateway (returning 402s with payment terms)?
- **Signal**: HTTP 402 responses to specific paths, x402 headers in responses
- **Severity**: low → medium as adoption grows
- **Note**: Would require an active probe (send request, check for 402) — more invasive than current static checks

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

- **Done**: RDY-032 x402 signal check + .well-known/agent-verification probe
- **When Monetization Gateway goes GA**: Promote CHECK 3 (active 402 probe)
- **When Shopify announces CF wallet integration**: Add Shopify-specific x402 check
- **When adoption hits ~10% of Shopify stores**: Increase RDY-032 weight, promote CHECK 1 + 2 to scored
