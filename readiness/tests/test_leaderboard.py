"""Tests for leaderboard.py's full-pack filtering.

Regression lock for the "free scan ranked against full scans" bug: a
16-check (bugged) or 30-check (fixed but still free-tier) web scan must
never be ranked or deduped against a 40-check full scan — the free tier
is structurally incapable of failing checks it never runs, so it would
rank artificially high.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from leaderboard import _is_full_pack_scan, load_all_scans, MIN_FULL_PACK_CHECKS


def _payload(n_results, tier=None, score=50.0, target="https://example.com/products/x"):
    results = [{"id": f"RDY-{i:03d}", "verdict": "PASS", "weight": 1,
                "pass_fraction": 1.0, "severity_if_fail": "medium"}
               for i in range(n_results)]
    meta = {"target": target, "timestamp": "2026-01-01T00:00:00"}
    if tier is not None:
        meta["tier"] = tier
    return {"readiness_score": score, "results": results, "meta": meta}


class TestIsFullPackScan:
    def test_paid_tier_is_full_pack(self):
        assert _is_full_pack_scan(_payload(40, tier="paid")) is True

    def test_free_tier_is_not_full_pack(self):
        assert _is_full_pack_scan(_payload(30, tier="free")) is False

    def test_free_tier_even_with_many_results_is_not_full_pack(self):
        # tier is authoritative when present, regardless of result count
        assert _is_full_pack_scan(_payload(40, tier="free")) is False

    def test_legacy_payload_without_tier_falls_back_to_count(self):
        assert _is_full_pack_scan(_payload(40, tier=None)) is True
        assert _is_full_pack_scan(_payload(16, tier=None)) is False

    def test_min_full_pack_checks_matches_pack_size(self):
        """Regression lock: this constant must track the real pack size,
        not a number typed from memory."""
        yaml_path = pathlib.Path(__file__).resolve().parent.parent / "checks" / "shopify-v1.yaml"
        import yaml
        data = yaml.safe_load(yaml_path.read_text())
        assert MIN_FULL_PACK_CHECKS == len(data["checks"])


class TestLoadAllScans:
    def test_free_scan_excluded_from_leaderboard(self, tmp_path, monkeypatch):
        import leaderboard
        monkeypatch.setattr(leaderboard, "SCANS_DIR", tmp_path)

        free = _payload(30, tier="free", target="https://free-store.example/products/a")
        paid = _payload(40, tier="paid", target="https://paid-store.example/products/b")
        (tmp_path / "free.json").write_text(json.dumps(free))
        (tmp_path / "paid.json").write_text(json.dumps(paid))

        scans = leaderboard.load_all_scans()
        domains = {s["meta"]["target"] for s in scans}
        assert "https://paid-store.example/products/b" in domains
        assert "https://free-store.example/products/a" not in domains

    def test_dedup_never_prefers_a_free_scan_over_a_full_one(self, tmp_path, monkeypatch):
        import leaderboard
        monkeypatch.setattr(leaderboard, "SCANS_DIR", tmp_path)

        # Same domain, free scan is *newer* than the paid one — the old
        # (pre-fix) dedup-by-timestamp logic would have kept the free scan.
        paid = _payload(40, tier="paid", score=40.0)
        paid["meta"]["timestamp"] = "2026-01-01T00:00:00"
        free = _payload(30, tier="free", score=90.0)
        free["meta"]["timestamp"] = "2026-02-01T00:00:00"
        (tmp_path / "paid.json").write_text(json.dumps(paid))
        (tmp_path / "free.json").write_text(json.dumps(free))

        scans = leaderboard.load_all_scans()
        assert len(scans) == 1
        assert scans[0]["readiness_score"] == 40.0
