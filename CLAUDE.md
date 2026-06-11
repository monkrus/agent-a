# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

This is the **internal protocol, scenario library, and tooling** behind a
paid service: the Agent Failure Audit. A human QA engineer audits a client's
LLM agent for failure modes, delivers a written report (and optionally a
regression eval suite the client keeps), and bills a fixed price per engagement.

**This repo is the kitchen, not the menu.** The product sold to clients is the
*report* and *eval suite* — never this repo, this methodology, or the scenario
library. Treat everything here as proprietary.

## Critical rules — do not violate

1. **Never commit client data.** Everything under `clients/` (except
   `clients/_template/`) is gitignored and must stay that way. Client traces,
   findings, and reports never enter git history. If asked to commit and a
   `clients/<name>/` path is involved, refuse and explain.
2. **Never expose the scenario library or protocol to a client deliverable.**
   The report (`reports/templates/audit-report.md`) is self-contained and
   describes methodology only at a high level. Do not paste scenario YAML,
   scenario IDs from the shared packs, or `playbook/protocol.md` content into
   anything destined for a client. Client-facing = report.md only.
3. **`call_agent()` in `runners/run_scenarios.py` is wired per engagement.**
   It is intentionally `NotImplementedError` in the committed version. When
   adapting it for a client, do that work inside `clients/<name>/` (e.g. a local
   `runner.py` that imports the generic loader), not by editing the shared
   runner. Keep the committed runner client-agnostic.
4. **No secrets in the repo.** API keys, client endpoints, wallet keys, etc.
   live in `.env` (gitignored) or per-client local files, never in tracked code.

## Layout

```
playbook/protocol.md   The six-category failure taxonomy. The core IP. Changes slowly.
playbook/engagement.md How to run an engagement end to end (create if absent).
scenarios/             Reusable test packs (YAML). Versioned by quarter.
  universal/           Apply to every agent.
  voice-agents/        Voice/desktop agent specific.
  support-agents/      Support agent specific.
  mcp-tools/           MCP / tool-surface (injection, scope creep). Highest-value pack.
runners/run_scenarios.py  Thin glue: load packs -> call agent -> stage for triage.
reports/templates/     Client deliverable skeleton.
clients/               One folder per engagement. GITIGNORED.
```

## The six failure categories (shorthand)

When generating or reviewing scenarios, every scenario maps to exactly one:
`task-completion`, `trajectory`, `boundary`, `injection`, `degradation`,
`drift`. Full definitions in `playbook/protocol.md` — read it before writing
scenarios.

## Common tasks & how to do them

- **Add a scenario:** append to the right pack YAML. Every scenario needs:
  `id` (PACK-NNN), `category` (one of the six), `title`, `input` and/or `setup`,
  `expect`, `fail_if`, `severity_if_fail` (critical/high/medium/low). Match the
  format already in `scenarios/universal/core.yaml`.
- **Start an engagement:** `cp -r clients/_template clients/<name>`. Work there.
- **Run scenarios:** `python runners/run_scenarios.py --packs <list> --out clients/<name>/run1`
  (after wiring `call_agent` for that client). Requires `pyyaml`.
- **Generalize a finding back into the library:** when a real engagement
  surfaces a novel failure, abstract it (strip client specifics) and add it to
  the appropriate shared pack. This feedback loop is the point of the repo —
  prompt the user to do it after each engagement if it hasn't happened.
- **Bump protocol version:** scenarios carry `version: 2026Q<n>`; tag the repo
  per quarter so re-audits can cite the exact protocol version applied.

## Conventions

- Scenario IDs are stable and never reused — findings reference them across
  versions, so renumbering breaks traceability.
- Severity uses the rubric in `playbook/protocol.md`; don't invent new levels.
- Keep the committed runner generic; client adaptation stays in `clients/`.
- New agent-type packs go under `scenarios/<type>/` and follow the same YAML shape.

## When in doubt

If a request would (a) commit client data, (b) leak the protocol/scenarios into
a client deliverable, or (c) put secrets in tracked files — stop and flag it.
Everything else, proceed.

## Testing infrastructure (added)

- `runners/adapters.py` — `call_agent` implementations. Select via `ADAPTER`
  env: `mock` (default, no creds), `anthropic`, `http`. Engagement work =
  pointing one of these at the target, usually in `clients/<name>/runner.py`.
- `runners/graders.py` — programmatic PASS/FAIL for objective conditions. The
  `canary` pattern automates injection tests: scenario carries a `canary` token,
  adapter plants an instruction to emit it, grader fails the run if it appears.
  Add objective graders here rather than relying on manual triage.
- `QUICKSTART.md` — the run procedure. Smoke test with ADAPTER=mock first.
- Methodology: every automated scenario runs N times -> report a PASS RATE, not
  a binary. Critical scenario below 100% = critical finding.
- When adding a scenario: set `automated: true` only if the adapter can run it
  from `input` (+ optional `canary`) alone; otherwise `automated: false`.
