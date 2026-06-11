#!/usr/bin/env python3
"""
Triage helper: turns run results.json into a findings.md skeleton.

Reads the v2 structure {run_meta, automated[], manual[]}. Orders by severity,
shows pass-rate placeholders for automated scenarios and observed-behavior
placeholders for manual ones. You complete the verdict + finding for each FAIL.

Usage: python runners/triage.py clients/<name>/run1/results.json
"""
import json, pathlib, sys

SEV = {"critical":0,"high":1,"medium":2,"low":3,None:4}

AUTO = """### {id} — {title}  ·  **{sev}** if confirmed  ·  AUTOMATED (n={n})
- **Pass rate:** ____/{n}   <!-- fill from transcripts; programmatic: {pv} -->
- **Verdict:** PENDING   <!-- PASS only if rate meets threshold for severity -->
- **Category:** {cat}  | **Expect:** {expect}  | **Fail if:** {fail_if}
- **Observed:** <!-- summarize across runs; note flakiness -->
- **Reproduction:** 1. <!-- --> 
- **Suggested fix:** <!-- -->

"""
MANUAL = """### {id} — {title}  ·  **{sev}** if confirmed  ·  MANUAL
- **Setup performed:** {setup}
- **Attempts:** ____  | **Verdict:** PENDING
- **Category:** {cat}  | **Expect:** {expect}  | **Fail if:** {fail_if}
- **Observed:** <!-- what happened -->
- **Reproduction:** 1. <!-- -->
- **Suggested fix:** <!-- -->

"""

def main():
    if len(sys.argv)!=2: sys.exit("usage: triage.py path/to/results.json")
    p = pathlib.Path(sys.argv[1]); data = json.loads(p.read_text())
    auto = sorted(data.get("automated",[]), key=lambda r: SEV.get(r.get("severity_if_fail"),4))
    man  = sorted(data.get("manual",[]),    key=lambda r: SEV.get(r.get("severity_if_fail"),4))
    blocks = [AUTO.format(id=r["id"], title=r.get("title",""),
                sev=(r.get("severity_if_fail") or "n/a").upper(), n=r.get("n","?"),
                pv=r.get("programmatic_pass_rate") or "n/a", cat=r.get("category",""),
                expect=r.get("expect",""), fail_if=r.get("fail_if","")) for r in auto]
    blocks += [MANUAL.format(id=r["id"], title=r.get("title",""),
                sev=(r.get("severity_if_fail") or "n/a").upper(),
                setup=(r.get("instructions") or r.get("input_setup") or ""),
                cat=r.get("category",""), expect=r.get("expect",""),
                fail_if=r.get("fail_if","")) for r in man]
    out = p.parent/"findings.md"
    meta = data.get("run_meta",{})
    out.write_text(f"# Findings — triage of {p.name}\n\n"
        f"Run: model={meta.get('model')} temp={meta.get('temperature')} "
        f"n={meta.get('n_runs')} at {meta.get('timestamp')}\n\n"
        f"{len(auto)} automated + {len(man)} manual. Set pass rate + verdict per "
        f"block; a critical that isn't 100% is a critical finding.\n\n" + "".join(blocks))
    print(f"wrote {out} ({len(auto)} automated, {len(man)} manual)")

if __name__=="__main__": main()
