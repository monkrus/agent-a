# Quickstart — run your first audit

## 0. Setup (once)
```bash
pip install -r requirements.txt        # pyyaml, anthropic, requests
```

## 1. Smoke test (no credentials — proves the pipeline)
```bash
cd runners
ADAPTER=mock python run_scenarios.py \
  --packs universal,mcp-tools,voice-agents,support-agents \
  --out /tmp/audit/run1 --n 10 --model mock --temperature 1.0 \
  --scenarios-root ../scenarios
python triage.py /tmp/audit/run1/results.json
```
You should see pass rates like `UNI-003 6/10` and a findings.md. That's the loop.

## 2. Point at a REAL agent
Pick ONE adapter via the ADAPTER env var.

**A Claude-based agent (fastest):**
```bash
export ADAPTER=anthropic
export ANTHROPIC_API_KEY=sk-...
export TARGET_MODEL=claude-sonnet-4-6
export TARGET_SYSTEM_PROMPT="$(cat path/to/the/agents/system_prompt.txt)"
cd runners && python run_scenarios.py --packs universal,mcp-tools \
  --out clients/<name>/run1 --n 10 \
  --model "$TARGET_MODEL" --temperature 0 --scenarios-root ../scenarios
```

**Any agent with an HTTP endpoint:**
```bash
export ADAPTER=http
export TARGET_URL=https://your-agent/chat
export TARGET_INPUT_FIELD=message      # JSON field the agent reads
export TARGET_OUTPUT_FIELD=response    # JSON field the reply is in
export TARGET_AUTH="Bearer ..."        # optional
cd runners && python run_scenarios.py --packs universal --out clients/<name>/run1 --n 10 \
  --model your-agent --temperature 0 --scenarios-root ../scenarios
```

## 3. Triage -> report
```bash
python triage.py clients/<name>/run1/results.json   # writes findings.md
```
- Complete the 8 MANUAL scenarios by hand (tool mocking, multi-turn, etc.).
- For automated FAILs, confirm the pass rate, write repro steps.
- A critical-severity scenario below 100% is a critical finding (see methodology.md).
- Fill reports/templates/audit-report.md from findings.md. Deliver PDF + walkthrough.

## Recommended first target: YOUR OWN agent
Audit a ListingIQ component or your own bot first. Full access, no NDA, no
reputation risk, and it becomes your first case study.

## What's automated vs. manual
- Automated (run x N, get pass rate): ambiguity, override/authority refusal,
  injection-via-canary (MCP/VOX/SUP), refund erosion, cross-account leak.
- Manual (you set up): tool-failure mocking, permission inventory, audio/
  transcription cases, multi-turn pressure, unsolvable-handoff.
