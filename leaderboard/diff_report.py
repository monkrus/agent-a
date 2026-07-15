#!/usr/bin/env python3
"""
diff_report.py — Compare old-parser vs new-parser scores.

Reads:
  - readiness/.scans/_old_scores.json (archived old scores)
  - readiness/.scans/*.json (new scans)

Outputs the diff table, flipped checks, median comparison, ranking changes.
"""
import json
import pathlib
import statistics
from urllib.parse import urlparse

SCANS_DIR = pathlib.Path(__file__).resolve().parent.parent / "readiness" / ".scans"
OLD_SCORES_FILE = SCANS_DIR / "_old_scores.json"

TIER_DOMAINS = {
    "gymshark.com", "everlane.com", "untuckit.com", "skims.com",
    "kyliecosmetics.com", "fentybeauty.com", "sundayriley.com", "olaplex.com",
    "harrys.com", "dollarshaveclub.com", "casper.com", "tuftandneedle.com",
    "purple.com", "framebridge.com", "awaytravel.com", "warbyparker.com",
    "liquid-iv.com", "aloyoga.com",
}

TEST_DOMAINS = {"bearaby.com", "cutsclothing.com", "thursdayboots.com"}


def _domain(url):
    h = urlparse(url).hostname or url
    if h.startswith("www."): h = h[4:]
    if h.startswith("us."): h = h[3:]
    return h


def load_new_scans():
    new = {}
    for f in sorted(SCANS_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text())
            target = data.get("meta", {}).get("target", "")
            domain = _domain(target)
            score = data.get("readiness_score")
            results = data.get("results", [])
            checks = {}
            for r in results:
                checks[r.get("id", "")] = r.get("verdict", "")
            ts = data.get("meta", {}).get("timestamp", "")
            if domain not in new or ts > new[domain].get("ts", ""):
                new[domain] = {"score": score, "checks": checks, "ts": ts}
        except:
            continue
    return new


def main():
    old = json.loads(OLD_SCORES_FILE.read_text())
    new = load_new_scans()

    all_domains = sorted(set(old.keys()) | set(new.keys()))
    tier_in_new = {d for d in new if d in TIER_DOMAINS and new[d]["score"] is not None}

    print("=" * 90)
    print("DIFF REPORT: Old Parser vs New Parser")
    print("=" * 90)
    print()

    # Full diff table
    print(f"{'Domain':30s} {'Old':>7s} {'New':>7s} {'Delta':>7s} {'Flipped Checks'}")
    print("-" * 90)

    product_group_gainers = []

    for domain in all_domains:
        old_score = old.get(domain, {}).get("score")
        new_entry = new.get(domain, {})
        new_score = new_entry.get("score")

        old_str = f"{old_score}" if old_score is not None else "N/A"
        new_str = f"{new_score}" if new_score is not None else "N/A"

        delta = ""
        if old_score is not None and new_score is not None:
            d = new_score - old_score
            delta = f"{d:+.1f}" if d != 0 else "0.0"

        # Find flipped checks
        old_checks = old.get(domain, {}).get("checks", {})
        new_checks = new_entry.get("checks", {})
        flipped = []
        for cid in sorted(set(old_checks.keys()) | set(new_checks.keys())):
            ov = old_checks.get(cid, "")
            nv = new_checks.get(cid, "")
            if ov != nv and ov and nv:
                flipped.append(f"{cid}: {ov}->{nv}")

        if d > 0 if (old_score is not None and new_score is not None) else False:
            # Check if RDY-001 or RDY-012 flipped — indicates ProductGroup fix
            rdy001_flipped = any("RDY-001" in f for f in flipped)
            rdy012_flipped = any("RDY-012" in f for f in flipped)
            if rdy001_flipped or rdy012_flipped:
                product_group_gainers.append(domain)

        flipped_str = "; ".join(flipped) if flipped else ""
        tier_marker = " [TIER]" if domain in TIER_DOMAINS else " [TEST]" if domain in TEST_DOMAINS else ""
        print(f"{domain + tier_marker:30s} {old_str:>7s} {new_str:>7s} {delta:>7s}  {flipped_str}")

    print()

    # Tier-only stats
    old_tier_scores = [old[d]["score"] for d in TIER_DOMAINS if d in old and old[d]["score"] is not None]
    new_tier_scores = [new[d]["score"] for d in TIER_DOMAINS if d in new and new[d]["score"] is not None]

    print("=" * 90)
    print("TIER STATISTICS")
    print("=" * 90)
    print(f"Old tier scans: {len(old_tier_scores)}")
    print(f"New tier scans: {len(new_tier_scores)}")
    if old_tier_scores:
        print(f"Old median: {statistics.median(old_tier_scores)}")
    if new_tier_scores:
        print(f"New median: {statistics.median(new_tier_scores)}")
    print()

    # Away confirmation
    away_old = old.get("awaytravel.com", {}).get("score")
    away_new = new.get("awaytravel.com", {}).get("score")
    print(f"AWAY CONFIRMATION: old={away_old}, new={away_new}")
    if away_new == 100.0:
        print("  awaytravel.com remains 100.0 ✓")
    else:
        print(f"  WARNING: awaytravel.com changed from {away_old} to {away_new}")
    print()

    # ProductGroup adoption
    print(f"PRODUCTGROUP ADOPTION:")
    print(f"  Brands that gained points from ProductGroup fix: {len(product_group_gainers)}")
    for d in product_group_gainers:
        old_s = old.get(d, {}).get("score", "N/A")
        new_s = new.get(d, {}).get("score", "N/A")
        print(f"    {d}: {old_s} -> {new_s}")
    print()

    # Ranking
    print("NEW TIER RANKING:")
    ranked = sorted(
        [(d, new[d]["score"]) for d in TIER_DOMAINS if d in new and new[d]["score"] is not None],
        key=lambda x: x[1], reverse=True
    )
    for i, (d, s) in enumerate(ranked, 1):
        old_s = old.get(d, {}).get("score")
        delta_str = f"({s - old_s:+.1f})" if old_s is not None else "(new)"
        print(f"  {i:2d}. {d:30s} {s:>6.1f} {delta_str}")


if __name__ == "__main__":
    main()
