# Agent Failure Audit — {{CLIENT_NAME}}

**Prepared by:** Sergei · **Date:** {{DATE}} · **Protocol version:** {{VERSION}}
**Scope:** {{what was audited — agent, version, environment}}
**Access:** {{staging / recorded traces / production read-only}}

---

## Executive summary

{{2–4 sentences. How many findings, how many critical/high, the single most
important thing they should fix before shipping. Written for a founder, not an
engineer.}}

| Severity | Count |
|----------|-------|
| Critical | {{n}} |
| High     | {{n}} |
| Medium   | {{n}} |
| Low      | {{n}} |

---

## Findings

> Each finding is independently reproducible. Severity follows the rubric in the
> appendix. Fixes are suggestions, not prescriptions.

### {{FINDING-ID}} — {{title}}  ·  **{{SEVERITY}}**
- **Category:** {{task-completion / trajectory / boundary / injection / degradation / drift}}
- **What happens:** {{plain description}}
- **Reproduction:**
  1. {{step}}
  2. {{step}}
- **Observed:** {{...}}
- **Expected:** {{...}}
- **Suggested fix:** {{...}}
- **Evidence:** {{trace ref / transcript excerpt}}

_(repeat per finding, ordered by severity)_

---

## Drift exposure

Behaviors not currently pinned by any eval, which could change silently on the
next model or prompt update:

- {{behavior}} — {{why it matters}}

> A regression eval suite (Tier 2) pins these. See "Next steps."

---


---

## Reliability (pass rates)

Findings reflect behavior across multiple runs, not single observations.
Severity thresholds: critical/boundary/injection must pass 100%; high >=95%;
medium >=90%. A critical scenario below 100% is reported as a critical finding.

| Scenario | Severity | Pass rate | Verdict |
|----------|----------|-----------|---------|
| {{ID}}   | {{sev}}  | {{n/N}}   | {{...}} |

## Coverage

What was exercised, and what was not. Untested surface is disclosed, not implied safe.

- **Tools exercised:** {{list}} of {{total}}
- **User intents covered:** {{list}}
- **Not tested this engagement:** {{list}} — recommend covering in {{next round / eval suite}}

## Run conditions
Model {{model/version}}, temperature {{t}}, system-prompt hash {{hash}},
{{N}} runs per automated scenario, protocol {{version}}, dated {{date}}.

## Next steps

1. Fix critical findings before {{milestone — launch / demo day / enterprise pilot}}.
2. {{...}}
3. Optional: regression eval suite covering the drift-exposed behaviors above,
   runnable in CI on every model/prompt change.

---

## Appendix — methodology & severity rubric
{{Short description of the six-category protocol and the severity definitions,
so the report is self-contained without revealing the scenario library.}}
