"""Regression tests for the Nov 2026 security + cost-leak review."""
import json
import pathlib
import re
import socket
import sqlite3
import sys
import threading
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import app as appmod  # noqa: E402
import emailer  # noqa: E402
import emotional_gap  # noqa: E402
import fetch as fetchmod  # noqa: E402

TEMPLATES = pathlib.Path(appmod.__file__).resolve().parent / "templates"
FREE, PAID, AGENCY = "aaaaaaaaaaa1", "aaaaaaaaaaa2", "aaaaaaaaaaa3"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "SCANS_DIR", tmp_path)
    monkeypatch.setattr(appmod, "_STORE_PATH", tmp_path / "store.db")
    monkeypatch.setitem(appmod._domain_index_cache, "ts", 0.0)
    monkeypatch.setitem(appmod._leaderboard_cache, "ts", 0.0)
    appmod._init_store()
    appmod.app.config["TESTING"] = True
    return tmp_path


def _scan(d, sid, ts, **meta):
    body = {"scan_id": sid, "readiness_score": 50.0, "headline": "h", "results": [],
            "meta": {"target": "https://client.example/products/x", "timestamp": ts, **meta}}
    (d / f"{sid}.json").write_text(json.dumps(body))


# ---- 1. paid/agency reports not discoverable -------------------------------------

def test_domain_lookup_never_returns_paid_or_agency_scans(env):
    _scan(env, PAID, "2026-11-03", paid=True, tier="paid")
    _scan(env, AGENCY, "2026-11-04", paid=True, agency_id=7)
    c = appmod.app.test_client()
    assert c.get("/api/compare?domain=client.example").get_json()["found"] is False
    assert c.get("/report/client.example").status_code == 404


def test_domain_lookup_still_finds_free_scans(env):
    _scan(env, FREE, "2026-11-01")
    _scan(env, AGENCY, "2026-11-04", paid=True, agency_id=7)
    j = appmod.app.test_client().get("/api/compare?domain=client.example").get_json()
    assert j["found"] is True and j["scan_id"] == FREE


def test_leaderboard_hides_paid_and_agency_scans(env, monkeypatch):
    import leaderboard as lb
    monkeypatch.setattr(lb, "SCANS_DIR", env)
    _scan(env, AGENCY, "2026-11-04", paid=True, agency_id=7)
    html = appmod.app.test_client().get("/leaderboard").get_data(as_text=True)
    assert "client.example" not in html and AGENCY not in html


# ---- 2. XSS: stream/leaderboard fields always escaped -----------------------------

@pytest.mark.parametrize("name", ["index.html", "processing.html"])
def test_stream_fields_escaped_before_innerhtml(name):
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    assert "function esc(" in src
    raw = re.findall(r"\+ d\.(message|label|title|headline|detail|id|scan_id|skipped)\b(?!\))", src)
    assert raw == [], f"unescaped stream fields in {name}: {raw}"


def test_leaderboard_domain_escaped():
    src = (TEMPLATES / "leaderboard.html").read_text(encoding="utf-8")
    assert "esc(e.domain)" in src and "+ e.domain +" not in src


def test_badge_svg_escapes_domain(env):
    _scan(env, FREE, "2026-11-01")
    data = json.loads((env / f"{FREE}.json").read_text())
    data["meta"]["target"] = "https://x<script>.example/p"
    (env / f"{FREE}.json").write_text(json.dumps(data))
    svg = appmod.app.test_client().get(f"/r/{FREE}/badge.svg").get_data(as_text=True)
    assert "<script>" not in svg


def test_email_html_escapes_page_text():
    html = emailer._build_html({"readiness_score": 1, "headline": "<b>x</b>", "meta": {"target": "t"},
                                "results": [{"id": "RDY-1", "verdict": "FAIL", "title": "<img src=x onerror=1>",
                                             "detail": "<script>a()</script>"}]})
    assert "<img src=x" not in html and "<script>a()" not in html


# ---- 3/4/6. paid-scan cost guards ------------------------------------------------

def test_rescan_of_a_rescan_refused(env):
    _scan(env, PAID, "2026-11-03", paid=True, free_scan_id=FREE, rescan_of=FREE)
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s[f"paid_verified_{FREE}"] = True
    assert c.post(f"/rescan/{PAID}").status_code == 403


def test_concurrent_refunds_grant_exactly_one_credit(env):
    conn = sqlite3.connect(str(env / "store.db"))
    conn.execute("INSERT INTO agencies (id, name, email, password_hash, api_key, credits, created_at) "
                 "VALUES (1, 'A', 'a@x', 'h', 'k', 0, 0)")
    conn.commit()
    conn.close()
    ts = [threading.Thread(target=appmod._refund_once, args=(PAID, 1)) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    conn = sqlite3.connect(str(env / "store.db"))
    assert conn.execute("SELECT credits FROM agencies WHERE id = 1").fetchone()[0] == 1
    conn.close()


def test_concurrent_run_claims_capped(env):
    wins = []
    lock = threading.Lock()

    def claim():
        ok, _ = appmod._claim_paid_run(PAID)
        with lock:
            wins.append(ok)
    ts = [threading.Thread(target=claim) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert wins.count(True) == appmod.MAX_PAID_RUNS


def test_send_report_refused_for_link_holder(env):
    _scan(env, PAID, "2026-11-03", paid=True, free_scan_id=FREE)
    r = appmod.app.test_client().post(f"/send-report/{PAID}", data={"email": "x@evil.example"})
    assert r.status_code == 403


def test_send_report_allowed_for_owning_agency(env):
    _scan(env, AGENCY, "2026-11-03", paid=True, agency_id=7)
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["agency_id"] = 7
    with patch.object(appmod.emailer, "_is_configured", return_value=False):
        r = c.post(f"/send-report/{AGENCY}", data={"email": "me@agency.example"})
    assert r.status_code != 403


# ---- 5/7. SSRF + DNS rebinding ---------------------------------------------------

@pytest.mark.parametrize("ip,unsafe", [("127.0.0.1", True), ("169.254.169.254", True),
                                       ("10.0.0.5", True), ("100.64.1.1", True),
                                       ("224.0.0.1", True), ("::ffff:127.0.0.1", True),
                                       ("0.0.0.0", True), ("8.8.8.8", False)])
def test_ip_classification(ip, unsafe):
    import ipaddress
    assert fetchmod._ip_unsafe(ipaddress.ip_address(ip)) is unsafe


def test_connect_guard_blocks_rebinding_at_connect_time():
    """Name resolves to loopback when requests connects: must be refused even
    though no _is_safe_url pre-check ran (as with any helper fetch)."""
    real = socket.getaddrinfo

    def rebinding(host, *a, **k):
        if host == "rebind.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        return real(host, *a, **k)
    with patch("socket.getaddrinfo", side_effect=rebinding):
        with pytest.raises(fetchmod._UnsafeURLError):
            requests.get("http://rebind.example/", timeout=3)


def test_image_fetch_cannot_reach_metadata_endpoint():
    with patch("socket.create_connection", side_effect=AssertionError("connected!")):
        assert emotional_gap._fetch_image_bytes("http://169.254.169.254/latest/meta-data/") is None


def test_body_is_capped():
    r = requests.Response()
    r.status_code = 200
    chunk = b"x" * 65536
    r.raw = None
    r.iter_content = lambda chunk_size=65536: iter([chunk] * 200)  # 12.5MB
    r.close = lambda: None
    fetchmod._read_capped(r, 10)
    assert len(r.content) == fetchmod.MAX_BODY_BYTES


# ---- 8. login hardening ----------------------------------------------------------

def _login(c, email, pw, token="tok"):
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    return c.post("/agency/login", data={"email": email, "password": pw, "csrf_token": token})


def test_login_without_csrf_token_rejected(env):
    r = appmod.app.test_client().post("/agency/login", data={"email": "a@x", "password": "p"})
    assert r.status_code == 400


def test_login_throttled_after_repeated_failures(env):
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(str(env / "store.db"))
    conn.execute("INSERT INTO agencies (name, email, password_hash, api_key, credits, created_at) "
                 "VALUES ('A', 'a@x.com', ?, 'k', 0, 0)", (generate_password_hash("rightpass1"),))
    conn.commit()
    conn.close()
    c = appmod.app.test_client()
    for _ in range(appmod.LOGIN_MAX_PER_EMAIL):
        _login(c, "a@x.com", "wrong")
    r = _login(c, "a@x.com", "rightpass1")
    assert r.status_code == 429


def test_logout_requires_post(env):
    assert appmod.app.test_client().get("/agency/logout").status_code == 405


# ---- 9. resource limits ----------------------------------------------------------

def test_oversized_request_body_rejected(env):
    big = "x" * (12 * 1024 * 1024)
    r = appmod.app.test_client().post("/api/agent-traffic", data=big,
                                      content_type="application/json")
    assert r.status_code == 413


def test_free_scan_refused_when_all_slots_busy(env, monkeypatch):
    monkeypatch.setattr(appmod, "_FREE_SCAN_SLOTS", threading.BoundedSemaphore(1))
    appmod._FREE_SCAN_SLOTS.acquire()
    try:
        body = appmod.app.test_client().get(
            "/scan-stream?url=https://shop.example/products/x").get_data(as_text=True)
    finally:
        appmod._FREE_SCAN_SLOTS.release()
    assert "try again in a minute" in body


# ---- low: headers, seed auth, admin token ----------------------------------------

def test_security_headers_present(env):
    r = appmod.app.test_client().get("/agency")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Referrer-Policy" in r.headers


def test_seed_rejects_session_signing_key(env, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-tok")
    r = appmod.app.test_client().post(
        "/api/seed-leaderboard", headers={"Authorization": f"Bearer {appmod._flask_secret}"})
    assert r.status_code == 403
