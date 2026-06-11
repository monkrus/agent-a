#!/usr/bin/env python3
"""
Scenario runner for the Agent Failure Audit.

Key methodology (see playbook/methodology.md):
  - Each AUTOMATED scenario runs N times; we report a PASS RATE, never a single
    binary verdict, because the agent is non-deterministic.
  - MANUAL scenarios (automated: false) are NOT executed here — they require
    human setup (tool mocking, multi-turn, audio). The runner emits a checklist
    stub for them so they're never silently dropped.
  - Reproducibility metadata is recorded for the whole run.

Wire call_agent() per engagement (in clients/<name>/runner.py, importing this).

Usage:
    python run_scenarios.py --packs universal,mcp-tools --out clients/acme/run1 --n 10
"""
import argparse
import json
import pathlib
import datetime
import hashlib
import yaml  # pip install pyyaml


def load_packs(pack_names, scenarios_root):
    scenarios = []
    for name in pack_names:
        for path in (scenarios_root / name).rglob("*.yaml"):
            data = yaml.safe_load(path.read_text())
            for s in data.get("scenarios", []):
                s["_pack"] = data.get("pack", name)
                s["_version"] = data.get("version", "unversioned")
                scenarios.append(s)
    return scenarios


try:
    from adapters import call_agent  # active adapter (mock by default)
except Exception:
    def call_agent(scenario):
        raise NotImplementedError(
            "No adapter wired. Set runners/adapters.py call_agent, or copy it to "
            "clients/<name>/runner.py and point it at the target agent.")


def run_meta(model, temperature, system_prompt, tools, n):
    return {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "temperature": temperature,
        "system_prompt_sha256": (
            hashlib.sha256(system_prompt.encode()).hexdigest()[:16]
            if system_prompt else None
        ),
        "tools": tools,
        "n_runs": n,
    }


def run(scenarios, out_dir, n, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    automated, manual = [], []

    for s in scenarios:
        base = {
            "id": s["id"], "category": s.get("category"), "title": s.get("title"),
            "pack": s["_pack"], "version": s["_version"],
            "expect": s.get("expect"), "fail_if": s.get("fail_if"),
            "severity_if_fail": s.get("severity_if_fail"),
        }
        if s.get("automated", False) is False:
            manual.append({**base, "input_setup": s.get("setup") or s.get("input"),
                           "mode": "MANUAL", "instructions": s.get("setup"),
                           "observed": None, "attempts": None, "verdict": "PENDING"})
            continue

        runs = []
        for _ in range(n):
            try:
                r = call_agent(s)
                runs.append(r)
            except NotImplementedError:
                runs.append({"transcript": None, "programmatic_verdict": None,
                             "_error": "call_agent not wired"})
        pv = [r.get("programmatic_verdict") for r in runs if r.get("programmatic_verdict")]
        pass_n = sum(1 for v in pv if v == "PASS")
        automated.append({
            **base, "mode": "AUTOMATED", "n": n, "runs": runs,
            "programmatic_pass_rate": (f"{pass_n}/{len(pv)}" if pv else None),
            "verdict": "PENDING",   # final human/judge verdict + pass rate
            "pass_rate": None,      # fill: e.g. "7/10"
            "finding": None,
        })

    payload = {"run_meta": meta, "automated": automated, "manual": manual}
    (out_dir / "results.json").write_text(json.dumps(payload, indent=2))
    print(f"staged: {len(automated)} automated (x{n} runs each), "
          f"{len(manual)} manual -> {out_dir/'results.json'}")
    print("Next: complete manual scenarios, then triage.py for findings.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--n", type=int, default=10, help="runs per automated scenario")
    ap.add_argument("--scenarios-root", default="scenarios", type=pathlib.Path)
    ap.add_argument("--model", default="UNSET")
    ap.add_argument("--temperature", default="UNSET")
    args = ap.parse_args()
    packs = [p.strip() for p in args.packs.split(",")]
    scenarios = load_packs(packs, args.scenarios_root)
    meta = run_meta(args.model, args.temperature, "", [], args.n)
    run(scenarios, args.out, args.n, meta)


if __name__ == "__main__":
    main()
