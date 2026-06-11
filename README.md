# Agent Failure Audit — Internal Protocol

Private repo. This is the methodology, scenario library, and tooling behind the
Agent Failure Audit service. **Never share this repo with clients** — clients
receive the report and (Tier 2) their own eval suite, not the protocol.

## Repo layout

```
playbook/            The audit methodology (the IP)
  protocol.md        Six-category failure taxonomy + per-category checklists
  engagement.md      How to run an engagement start-to-finish (timeline, access, comms)

scenarios/           Reusable test scenario libraries (YAML)
  universal/         Apply to every agent
  voice-agents/      Voice/desktop agent specific
  support-agents/    Customer support agent specific
  mcp-tools/         MCP / tool-surface specific (injection, scope creep)

runners/             Glue scripts to execute scenarios against a client agent
  run_scenarios.py   Generic runner: scenarios in → transcript + verdicts out

reports/
  templates/         Report skeleton (markdown → PDF via pandoc)

clients/             One folder per engagement (gitignored except .gitkeep)
  <client-name>/     Their scenario overrides, traces, findings, final report
```

## Engagement workflow (short version)

1. `cp -r clients/_template clients/<name>` — start engagement folder
2. Read their architecture, pick applicable scenario packs, write 10–20
   client-specific scenarios in `clients/<name>/scenarios/`
3. Run: `python runners/run_scenarios.py --target <their endpoint/harness> --packs universal,mcp-tools,clients/<name>`
4. Triage transcripts → findings.md (one entry per failure: repro steps, severity, fix)
5. Generate report from `reports/templates/audit-report.md`
6. **Feed back**: any novel failure mode discovered → generalize it → add to the
   shared scenario packs. This step is what makes the repo compound in value.

## Rules

- Client data never leaves `clients/` and `clients/` never leaves this machine
  unencrypted. Check NDA terms per engagement.
- Every scenario file has an `id`, so findings are traceable across versions.
- Scenario packs are versioned by git tag per quarter (v2026Q2, ...) so a
  re-audit can state exactly which protocol version was applied.
