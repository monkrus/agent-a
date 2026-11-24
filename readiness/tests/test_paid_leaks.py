"""Cost-leak guards: one payment buys one paid scan; /rescan only for the payer."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import app as appmod  # noqa: E402

STUB = "aaaaaaaaaaaa"
FINAL = "bbbbbbbbbbbb"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "SCANS_DIR", tmp_path)
    monkeypatch.setattr(appmod, "_STORE_PATH", tmp_path / "store.db")
    appmod._init_store()
    appmod.app.config["TESTING"] = True

    def fetch_must_not_run(*a, **k):
        raise AssertionError("a paid scan started (page fetch) when it should not")
    monkeypatch.setattr(appmod.fetchmod, "fetch", fetch_must_not_run)
    return tmp_path


def _write(d, scan_id, meta, **extra):
    (d / f"{scan_id}.json").write_text(json.dumps({"scan_id": scan_id, "meta": meta, **extra}))


def _meta(d, scan_id):
    return json.loads((d / f"{scan_id}.json").read_text())["meta"]


def _stream(client):
    with client.session_transaction() as s:
        s[f"paid_verified_{STUB}"] = True
    return client.get(f"/paid-scan-stream/{STUB}").get_data(as_text=True)


# ---- one paid scan per payment -----------------------------------------------

def test_completed_scan_replays_result_without_rerunning(env):
    _write(env, STUB, {"target": "https://shop.example/p", "final_scan_id": FINAL})
    _write(env, FINAL, {"duration_seconds": 99}, readiness_score=71.5, headline="H")
    body = _stream(appmod.app.test_client())
    assert '"type": "done"' in body and FINAL in body and "71.5" in body


def test_reconnects_capped_at_max_runs(env):
    _write(env, STUB, {"target": "https://shop.example/p", "paid_runs": appmod.MAX_PAID_RUNS})
    body = _stream(appmod.app.test_client())
    assert "already attempted" in body
    assert _meta(env, STUB)["paid_runs"] == appmod.MAX_PAID_RUNS  # not incremented


def test_refunded_scan_cannot_run_again(env):
    _write(env, STUB, {"target": "https://shop.example/p", "refunded": True})
    assert "refunded" in _stream(appmod.app.test_client())


def test_each_attempt_is_counted(env, monkeypatch):
    _write(env, STUB, {"target": "https://shop.example/p", "paid_runs": 1})

    def fetch_fails(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(appmod.fetchmod, "fetch", fetch_fails)
    _stream(appmod.app.test_client())
    assert _meta(env, STUB)["paid_runs"] == 2


def test_stream_still_requires_payment_flag(env):
    _write(env, STUB, {"target": "https://shop.example/p"})
    r = appmod.app.test_client().get(f"/paid-scan-stream/{STUB}")
    assert r.status_code == 403


# ---- /rescan --------------------------------------------------------------------

def _paid_scan(env, **meta):
    _write(env, FINAL, {"target": "https://shop.example/p", "paid": True,
                        "free_scan_id": STUB, **meta})


def test_stranger_with_public_link_cannot_rescan(env):
    _paid_scan(env)
    assert appmod.app.test_client().post(f"/rescan/{FINAL}").status_code == 403


def test_agency_scan_cannot_use_free_rescan(env):
    _paid_scan(env, agency_id=1)
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s[f"paid_verified_{STUB}"] = True
    assert c.post(f"/rescan/{FINAL}").status_code == 403


def test_payer_can_rescan_once(env):
    _paid_scan(env)
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s[f"paid_verified_{STUB}"] = True
    r = c.post(f"/rescan/{FINAL}")
    assert r.status_code == 302 and f"/processing/{FINAL}" in r.headers["Location"]


def test_second_rescan_shows_existing_result(env):
    newer = "cccccccccccc"
    _paid_scan(env, final_scan_id=newer)
    _write(env, newer, {"target": "https://shop.example/p"})
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s[f"paid_verified_{STUB}"] = True
    r = c.post(f"/rescan/{FINAL}")
    assert r.status_code == 302 and f"/results/{newer}" in r.headers["Location"]
