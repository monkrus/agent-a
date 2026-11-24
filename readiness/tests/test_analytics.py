"""First-party page-view analytics and the admin stats page."""
import json
import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import app as appmod  # noqa: E402

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
SCAN_ID = "abc123def456"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Throwaway sqlite store + scans dir holding one free scan."""
    monkeypatch.setattr(appmod, "_STORE_PATH", tmp_path / "store.db")
    monkeypatch.setattr(appmod, "SCANS_DIR", tmp_path)
    appmod._init_store()
    appmod.app.config["TESTING"] = True
    scan = {
        "scan_id": SCAN_ID,
        "readiness_score": 61.5,
        "headline": "h",
        "meta": {"target": "https://www.example-store.com/products/x", "tier": "free", "n": 5},
        "results": [{"id": "RDY-001", "title": "JSON-LD", "verdict": "FAIL",
                     "severity_if_fail": "high", "weight": 5, "detail": "d",
                     "fix_recipe": "SECRET PAID RECIPE"}],
    }
    (tmp_path / f"{SCAN_ID}.json").write_text(json.dumps(scan), encoding="utf-8")
    return tmp_path / "store.db"


def _rows(store, sql):
    conn = sqlite3.connect(str(store))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


# ---- analytics -------------------------------------------------------------

def test_page_view_and_unique_visitor_recorded(store):
    c = appmod.app.test_client()
    for _ in range(3):
        assert c.get("/agency", headers=BROWSER).status_code == 200
    assert _rows(store, "SELECT path, referrer, views FROM page_views") == [("/agency", "", 3)]
    assert len(_rows(store, "SELECT 1 FROM daily_visitors")) == 1


def test_dynamic_paths_grouped_by_route(store):
    appmod.app.test_client().get(f"/results/{SCAN_ID}", headers=BROWSER)
    assert _rows(store, "SELECT path FROM page_views") == [("/results/<scan_id>",)]


def test_external_referrer_host_kept_internal_dropped(store):
    c = appmod.app.test_client()
    c.get("/agency", headers={**BROWSER, "Referer": "https://www.linkedin.com/feed/?x=1"})
    c.get("/agency", headers={**BROWSER, "Referer": "http://localhost/"})
    assert sorted(_rows(store, "SELECT referrer, views FROM page_views")) == [
        ("", 1), ("www.linkedin.com", 1)]


@pytest.mark.parametrize("ua", ["", "curl/8.4", "Mozilla/5.0 (compatible; GPTBot/1.1)",
                                "python-requests/2.32", "UptimeRobot/2.0"])
def test_bots_and_empty_ua_not_counted(store, ua):
    appmod.app.test_client().get("/agency", headers={"User-Agent": ua})
    assert _rows(store, "SELECT 1 FROM page_views") == []


def test_untracked_and_failed_requests_not_counted(store):
    c = appmod.app.test_client()
    c.get("/results/does-not-exist", headers=BROWSER)      # 404
    c.get(f"/r/{SCAN_ID}/badge.svg", headers=BROWSER)      # asset endpoint
    assert _rows(store, "SELECT 1 FROM page_views") == []


def test_no_ip_stored_anywhere(store):
    appmod.app.test_client().get("/agency", headers=BROWSER,
                                 environ_base={"REMOTE_ADDR": "203.0.113.77"})
    dump = repr(_rows(store, "SELECT * FROM page_views")) + repr(
        _rows(store, "SELECT * FROM daily_visitors"))
    assert "203.0.113.77" not in dump


def test_analytics_failure_never_breaks_page(store, monkeypatch):
    monkeypatch.setattr(appmod, "_STORE_PATH", store.parent / "missing-dir" / "x.db")
    assert appmod.app.test_client().get("/agency", headers=BROWSER).status_code == 200


# ---- admin stats -----------------------------------------------------------

def test_admin_stats_404_without_token_configured(store, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    c = appmod.app.test_client()
    assert c.get("/admin/stats").status_code == 404
    assert c.get("/admin/stats?token=").status_code == 404


def test_admin_stats_404_with_wrong_token(store, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "right-token")
    assert appmod.app.test_client().get("/admin/stats?token=wrong").status_code == 404


def test_admin_stats_shows_funnel(store, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "right-token")
    c = appmod.app.test_client()
    c.get("/agency", headers={**BROWSER, "Referer": "https://news.ycombinator.com/item"})
    first = c.get("/admin/stats?token=right-token")
    assert first.status_code == 302 and "token" not in first.headers["Location"]
    r = c.get(first.headers["Location"])
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    for expected in ("news.ycombinator.com", "/agency"):
        assert expected in html
