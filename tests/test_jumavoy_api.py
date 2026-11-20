"""Вход для JUMAVOY (/api/jumavoy/*): только по токену, данные — уровня
админки без клиентских данных точек, действия — из короткого списка."""
import json

import pytest

import database as db

TOKEN = "jv-test-token-0123456789abcdefghijklmnop"
SECRET_KEYS = {"password_hash", "password_plain", "eskiz_email", "eskiz_password", "anpr_token",
               "owner_link_token", "client_count", "card_number", "notify_telegram_id"}


@pytest.fixture(scope="module")
def app():
    import webapp
    db.init_db()
    webapp.app.config["TESTING"] = True
    return webapp.app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    import security
    security.rate_reset()
    monkeypatch.setenv("JUMAVOY_TOKEN", TOKEN)


@pytest.fixture(scope="module")
def shop_id(app):
    s = db.find_shop_by_username("jv_motors") or db.create_shop("jv_motors", "Zx9-mountain-oil", "JV Motors",
                                                                 "+998901112233", "Andijon", "9-19")
    return s["id"]


def _get(app, path, token=TOKEN):
    return app.test_client().get(path, headers={"Authorization": f"Bearer {token}"} if token else {})


def _post(app, body, token=TOKEN):
    return app.test_client().post("/api/jumavoy/action", data=json.dumps(body), content_type="application/json",
                                  headers={"Authorization": f"Bearer {token}"})


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_off_without_token(app, monkeypatch):
    monkeypatch.setenv("JUMAVOY_TOKEN", "short")
    assert _get(app, "/api/jumavoy/summary").status_code == 404


def test_wrong_token_rejected_and_logged(app):
    import security
    assert _get(app, "/api/jumavoy/summary", token="nope").status_code == 401
    assert _get(app, "/api/jumavoy/summary", token=None).status_code == 401
    assert any(e["kind"] == "jumavoy_bad_token" for e in security.recent_events(20))


def test_summary_and_shops(app, shop_id):
    r = _get(app, "/api/jumavoy/summary")
    assert r.status_code == 200 and r.json["ok"], r.json
    for k in ("counts", "month", "today", "expiring_7d", "overdue", "pending_payments", "pending_registrations"):
        assert k in r.json
    shops = _get(app, "/api/jumavoy/shops").json["shops"]
    assert any(s["id"] == shop_id for s in shops)
    assert not SECRET_KEYS & set(_keys(shops))


def test_shop_card_has_no_secrets(app, shop_id):
    r = _get(app, "/api/jumavoy/shop?q=jv motors")
    assert r.status_code == 200, r.json
    assert r.json["shop"]["id"] == shop_id
    assert not SECRET_KEYS & set(_keys(r.json))
    assert _get(app, "/api/jumavoy/shop?q=no-such-shop-xyz").status_code == 404


def test_extend_and_set_until(app, shop_id):
    r = _post(app, {"action": "set_until", "shop_id": shop_id, "date": "2027-01-15"})
    assert r.status_code == 200 and r.json["paid_until"] == "2027-01-15", r.json
    r = _post(app, {"action": "extend", "shop_id": shop_id, "months": 1})
    assert r.status_code == 200 and r.json["paid_until"] > "2027-01-15", r.json
    assert _post(app, {"action": "extend", "shop_id": shop_id, "months": 5}).status_code == 400


def test_toggles_and_unknown_action(app, shop_id):
    assert _post(app, {"action": "sms", "shop_id": shop_id, "on": True}).status_code == 200
    assert db.get_shop(shop_id)["sms_enabled"] == 1
    assert _post(app, {"action": "sms", "shop_id": shop_id, "on": False}).status_code == 200
    assert db.get_shop(shop_id)["sms_enabled"] == 0
    r = _post(app, {"action": "delete", "shop_id": shop_id})
    assert r.status_code == 400 and "delete" not in r.json["actions"]
    assert _post(app, {"action": "active", "shop_id": 999999, "on": False}).status_code == 404


def test_price_and_log(app, shop_id):
    import security
    assert _post(app, {"action": "price", "shop_id": shop_id, "price": "150 000"}).status_code == 200
    assert db.get_shop(shop_id)["custom_price"] == 150000
    assert _post(app, {"action": "price", "shop_id": shop_id, "price": ""}).status_code == 200
    assert db.get_shop(shop_id)["custom_price"] is None
    assert any(e["kind"] == "jumavoy_action" for e in security.recent_events(20))


def test_message_needs_telegram(app, shop_id):
    r = _post(app, {"action": "message", "shop_id": shop_id, "text": "Salom"})
    assert r.status_code == 400 and "Telegram" in r.json["error"]


def test_analytics_and_registrations(app):
    assert _get(app, "/api/jumavoy/analytics").json["ok"]
    r = _get(app, "/api/jumavoy/registrations").json
    assert r["ok"] and "pending" in r
    assert _get(app, "/api/jumavoy/payments").json["ok"]
    assert _get(app, "/api/jumavoy/security").json["ok"]
