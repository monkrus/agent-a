"""Agency billing: signup credit, idempotent credit fulfilment, Stripe webhook."""
import hashlib
import hmac
import json
import pathlib
import sqlite3
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import app as appmod  # noqa: E402

WHSEC = "whsec_test_secret"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the app at a throwaway sqlite store."""
    monkeypatch.setattr(appmod, "_STORE_PATH", tmp_path / "store.db")
    appmod._init_store()
    appmod.app.config["TESTING"] = True
    return tmp_path / "store.db"


def _credits(store, agency_id):
    conn = sqlite3.connect(str(store))
    try:
        return conn.execute("SELECT credits FROM agencies WHERE id = ?",
                            (agency_id,)).fetchone()[0]
    finally:
        conn.close()


def _purchases(store):
    conn = sqlite3.connect(str(store))
    try:
        return conn.execute("SELECT COUNT(*) FROM agency_purchases").fetchone()[0]
    finally:
        conn.close()


def _register(client, email, ip="1.2.3.4"):
    return client.post("/agency/register",
                       data={"name": "Acme", "email": email, "password": "password123"},
                       environ_base={"REMOTE_ADDR": ip})


def _make_agency(store, credits=0):
    conn = sqlite3.connect(str(store))
    try:
        cur = conn.execute("INSERT INTO agencies (name, email, password_hash, api_key, "
                           "credits, created_at) VALUES ('A', 'a@x.com', 'h', 'k', ?, 0)",
                           (credits,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _signed(payload: str, secret: str = WHSEC) -> str:
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def _event(agency_id, pack="pack_10", session_id="cs_test_1", status="paid",
           etype="checkout.session.completed"):
    return json.dumps({
        "id": "evt_1", "object": "event", "type": etype,
        "data": {"object": {"id": session_id, "object": "checkout.session",
                            "payment_status": status,
                            "metadata": {"agency_id": str(agency_id), "pack": pack}}},
    })


class TestSignupCredit:
    def test_signup_grants_one_credit(self, store):
        client = appmod.app.test_client()
        _register(client, "first@agency.com")
        conn = sqlite3.connect(str(store))
        row = conn.execute("SELECT credits FROM agencies WHERE email='first@agency.com'").fetchone()
        conn.close()
        assert row[0] == 1

    def test_second_signup_same_ip_gets_no_credit(self, store):
        _register(appmod.app.test_client(), "one@agency.com", ip="9.9.9.9")
        _register(appmod.app.test_client(), "two@agency.com", ip="9.9.9.9")
        conn = sqlite3.connect(str(store))
        rows = dict(conn.execute("SELECT email, credits FROM agencies").fetchall())
        conn.close()
        assert rows == {"one@agency.com": 1, "two@agency.com": 0}

    def test_signup_marker_survives_rate_limit_prune(self, store):
        _register(appmod.app.test_client(), "one@agency.com", ip="8.8.8.8")
        # Age the marker past the 10-minute scan-limit prune window
        conn = sqlite3.connect(str(store))
        conn.execute("UPDATE rate_limits SET last_scan = last_scan - 3600")
        conn.commit()
        conn.close()
        appmod._check_rate_limit("5.5.5.5")  # triggers prune
        assert appmod._signup_credit_allowed("8.8.8.8") is False

    def test_register_page_mentions_free_scan(self, store):
        html = appmod.app.test_client().get("/agency/register").get_data(as_text=True)
        assert "first full scan is free" in html


class TestFulfilment:
    def test_adds_credits_once(self, store):
        aid = _make_agency(store)
        assert appmod._fulfill_credit_purchase(aid, "pack_10", "cs_a") is True
        assert appmod._fulfill_credit_purchase(aid, "pack_10", "cs_a") is False
        assert _credits(store, aid) == 10
        assert _purchases(store) == 1

    def test_unknown_pack_rejected(self, store):
        aid = _make_agency(store)
        assert appmod._fulfill_credit_purchase(aid, "pack_bogus", "cs_b") is False
        assert _credits(store, aid) == 0

    def test_missing_agency_records_nothing(self, store):
        assert appmod._fulfill_credit_purchase(999, "pack_10", "cs_c") is False
        assert _purchases(store) == 0


class TestWebhook:
    def test_unconfigured_returns_503(self, store, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        r = appmod.app.test_client().post("/stripe/webhook", data="{}")
        assert r.status_code == 503

    def test_bad_signature_rejected(self, store, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        aid = _make_agency(store)
        payload = _event(aid)
        r = appmod.app.test_client().post(
            "/stripe/webhook", data=payload,
            headers={"Stripe-Signature": _signed(payload, "whsec_wrong")})
        assert r.status_code == 400
        assert _credits(store, aid) == 0

    def test_valid_event_grants_credits_and_replay_is_noop(self, store, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        aid = _make_agency(store)
        payload = _event(aid, pack="pack_25")
        client = appmod.app.test_client()
        for _ in range(2):
            r = client.post("/stripe/webhook", data=payload,
                            headers={"Stripe-Signature": _signed(payload)})
            assert r.status_code == 200
        assert _credits(store, aid) == 25
        assert _purchases(store) == 1

    def test_unpaid_session_grants_nothing(self, store, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        aid = _make_agency(store)
        payload = _event(aid, status="unpaid")
        r = appmod.app.test_client().post("/stripe/webhook", data=payload,
                                          headers={"Stripe-Signature": _signed(payload)})
        assert r.status_code == 200
        assert _credits(store, aid) == 0

    def test_webhook_then_redirect_does_not_double_credit(self, store, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        aid = _make_agency(store)
        payload = _event(aid, session_id="cs_race")
        client = appmod.app.test_client()
        client.post("/stripe/webhook", data=payload,
                    headers={"Stripe-Signature": _signed(payload)})

        class _Meta(dict):
            def to_dict(self):
                return dict(self)

        class _CS:
            payment_status = "paid"
            metadata = _Meta(agency_id=str(aid), pack="pack_10")

        with client.session_transaction() as s:
            s["agency_id"] = aid
        with patch("stripe.checkout.Session.retrieve", return_value=_CS()):
            client.get("/agency/payment-success?session_id=cs_race")
        assert _credits(store, aid) == 10
        assert _purchases(store) == 1


def test_paid_scans_default_to_ten_runs(monkeypatch):
    monkeypatch.delenv("PAID_SCAN_N", raising=False)
    monkeypatch.setenv("SCAN_N", "5")
    assert appmod._paid_scan_n() == 10
