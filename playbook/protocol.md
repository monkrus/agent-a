# Agent Failure Audit Protocol

The audit walks six failure categories in order. Each has: what it is, why
metrics miss it, how to probe it, and what a finding looks like. Work top to
bottom — earlier categories surface context that sharpens later ones.

---

## 1. Task-completion failures
**The agent does the wrong thing confidently.** Misreads intent, picks the wrong
tool, satisfies the letter of the request while violating the goal.

Probe with a scenario matrix: `user persona × phrasing variant × ambiguity level`.
Take 3–4 core tasks the agent is supposed to do and generate ~5 phrasings each,
from crisp to deliberately ambiguous. The interesting failures live in the
ambiguous rows.

A finding here: "When the user says X (ambiguous between A and B), the agent
silently assumes A and proceeds without confirming. Repro: [steps]. Expected:
clarify or surface the assumption."

## 2. Trajectory failures
**Right answer, rotten path.** Loops, redundant tool calls, unrecoverable error
states, mid-chain factual corruption that survives to a plausible final answer.

You cannot see these from outputs — you must read traces. This is where being a
QA engineer who reads logs pays off; most founders have never opened their own
agent's trace. Look for: repeated near-identical tool calls, step N asserting a
fact contradicted by step N-2, error responses the agent "recovers" from by
fabricating.

## 3. Boundary & policy failures
**The agent does something it must never do.** Refunds it shouldn't issue, data
it shouldn't reveal, actions outside its mandate.

Probe with adversarial-user scenarios: social-engineering phrasings, authority
claims ("I'm the admin"), instruction-conflict ("ignore your previous
instructions and..."), and gradual escalation across a multi-turn conversation.
Severity here is almost always high — these are the failures that become incidents.

## 4. Injection & tool-surface failures  (MCP / tool-using agents)
**Hostile input rides in through data, not the user.** Malicious instructions in
retrieved documents, tool results that carry directives, scope escalation across
a tool chain, tool-poisoning.

This section alone justifies the fee for any MCP-based product. Probe: plant
instruction-bearing content in anything the agent ingests (a calendar event
title, a document it retrieves, a web page, an API response) and see if it
obeys. Test whether a tool granted for purpose A can be chained to accomplish
unauthorized purpose B. Check permission scope on every tool.

## 5. Degradation behavior
**What happens at the edges.** API timeouts, rate limits, malformed tool
responses, context overflow, model fallback to a weaker model.

Classic chaos testing, almost universally skipped by agent teams. Inject
failures at the harness boundary: return a 500 from a tool, a truncated JSON, a
timeout, an oversized payload. The question is never "does it work" — it's "does
it fail safely or fail silently."

## 6. Drift exposure
**Which behaviors are pinned vs. which would silently change on the next model
version.** Not a test you run once — it's an inventory.

For each critical behavior, ask: is there an eval that would catch it changing?
If not, it's drift-exposed. This category produces the Tier-2 upsell naturally —
the report lists drift-exposed behaviors, and the eval suite is what pins them.

---

## Severity rubric
- **Critical**: policy/boundary breach, data exposure, unauthorized action, or
  silent wrong-answer in a high-stakes task. Ship-blocker.
- **High**: reproducible wrong behavior in a common path; recoverable but
  user-visible.
- **Medium**: edge-case failure, degraded-mode misbehavior, inefficiency.
- **Low**: cosmetic, rare, or self-correcting.

Every finding needs: id, category, severity, **reproduction steps**, observed vs.
expected, suggested fix. The repro steps are the product — anyone can say "it
hallucinates"; you hand them a button to press.
