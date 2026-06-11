# Engagement Runbook

End-to-end process for one audit engagement. Target: Tier 1 in 5 working days,
Tier 2 in 10.

## Phase 0 — Discovery (before quoting, ~30-60 min call + intake form)
- Send `playbook/intake.md` questions before or during the call.
- Goal: understand architecture, tool surface, and stakes well enough to (a)
  pick scenario packs, (b) estimate effort, (c) quote a fixed price.
- Red flags that change scope/price: no staging environment, no trace logging,
  multi-agent systems, voice (transcription adds a layer), >15 tools.
- Output: signed proposal/SOW (`reports/templates/proposal-sow.md`) + access list.

## Phase 1 — Setup (day 1)
- `cp -r clients/_template clients/<name>`; fill `engagement.md` (scope, access,
  NDA notes, contacts, milestone the client is shipping toward).
- Get access working: staging endpoint or trace export. Verify you can run one
  end-to-end request before doing anything else.
- Wire `call_agent()` in a local `clients/<name>/runner.py`.

## Phase 2 — Architecture read + scenario selection (day 1-2)
- Read their prompts, tool definitions, and 20-50 production/staging traces.
- Select applicable shared packs; write 10-20 client-specific scenarios in
  `clients/<name>/scenarios/` (these are where most critical findings come from).
- For MCP/tool agents: inventory every tool and its permission scope first
  (this alone often produces findings — see MCP-005).

## Phase 3 — Execution (day 2-4)
- Run packs: `python runners/run_scenarios.py --packs ... --out clients/<name>/run1`
- Triage: `python runners/triage.py clients/<name>/run1/results.json` to
  scaffold findings, then manually verdict each transcript.
- Manual exploratory pass: follow anything suspicious in traces beyond the
  scripted scenarios. Budget at least half a day — exploratory testing finds
  what scripts miss.
- Every FAIL gets a finding with reproduction steps. Re-run repro steps once
  to confirm they're deterministic enough to hand over.

## Phase 4 — Report (day 4-5)
- Fill `reports/templates/audit-report.md`. Executive summary written for a
  founder; findings written for an engineer.
- Drift-exposure section doubles as the Tier 2 pitch — list what isn't pinned.
- Deliver as PDF + a 30-min walkthrough call. The call is where the retainer
  conversation happens.

## Phase 5 — Close & compound (after delivery)
- Generalize novel failures back into shared packs (strip client specifics).
- Note actual hours vs. quote in `engagement.md` — calibrates the next quote.
- 2 weeks later: follow-up email asking what they fixed. Ask for testimonial
  / permission for anonymized case study ("B2B voice agent, 14 findings, 3
  critical"). Case studies are the sales engine.

## Tier 2 addendum (eval suite delivery)
- Build the suite in THEIR stack (promptfoo/DeepEval/LangSmith/pytest), in
  THEIR repo, covering: every critical/high finding + drift-exposed behaviors.
- Deliverable includes a README for their team: how to run, how to add cases,
  what each grader checks. The suite must run in their CI without you.
- Do not copy shared scenario YAML verbatim — re-express cases in their
  harness's format (rule 2 in CLAUDE.md).
