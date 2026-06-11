# Proposal & Statement of Work — Agent Failure Audit

**Client:** {{CLIENT}} · **Prepared by:** Sergei · **Date:** {{DATE}}
**Valid for:** 14 days

## What you get

A structured QA audit of {{AGENT NAME}} against a six-category failure
protocol (task completion, trajectory, boundary/policy, injection/tool-surface,
degradation, drift exposure), performed by a QA engineer with 15 years of
testing experience and hands-on production agent development (LangChain,
multi-agent orchestration, MCP).

**Deliverable:** a written report containing every confirmed failure with
severity rating, step-by-step reproduction, observed vs. expected behavior,
and a suggested fix — plus a 30-minute walkthrough call.

{{IF TIER 2:}} **Plus:** a regression eval suite built in your stack
({{promptfoo/DeepEval/LangSmith/other}}), covering all critical and high
findings and all drift-exposed behaviors, runnable in your CI, documented for
your team, owned by you.

## Scope
- Agent/version: {{...}}
- Environment: {{staging endpoint / exported traces}}
- In scope: {{packs/areas}}
- Out of scope: {{e.g. load testing, model fine-tuning, infra security pentest}}

## Price & timeline
- **Fixed price: ${{X}}**, 50% on signing, 50% on delivery.
- Timeline: {{5/10}} working days from access being confirmed working.
- Access required by client: {{list from intake}} — timeline starts when
  access is verified, not when signed.

## Terms (short form)
- Findings and report are confidential to {{CLIENT}}.
- Methodology, scenario designs, and tooling remain the consultant's property;
  anonymized aggregate learnings may inform future work.
- Consultant may reference the engagement as "{{anonymized descriptor}}" in
  marketing unless client opts out in writing.
- No production-affecting actions without written approval per action.
- Not a security penetration test or compliance certification; no warranty
  that all defects are found.

Signature: _____________  Date: _______
