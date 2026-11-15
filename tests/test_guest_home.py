"""Главный адрес сайта: новый человек видит рекламную страницу /welcome,
а пользователи OilBook по-прежнему попадают в панель или на вход."""
import pytest


@pytest.fixture(scope="module")
def app():
    import database as db
    db.init_db()
    import webapp
    webapp.app.config["TESTING"] = True
    return webapp.app


def _login(client, shop_id, role="shop"):
    import database as db
    import webapp
    shop = db.get_shop(shop_id)
    with client.session_transaction() as s:
        s["shop_id"] = shop_id
        s["role"] = role
        s["username"] = shop["username"]
        s["is_employee"] = False
        s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))


def _any_shop_id():
    import database as db
    with db.get_conn() as conn:
        row = conn.execute("SELECT id FROM shops WHERE role='shop' AND is_active=1 ORDER BY id LIMIT 1").fetchone()
    return row["id"]


def test_new_visitor_gets_welcome(app):
    r = app.test_client().get("/")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/welcome")


def test_referral_and_ad_params_survive(app):
    r = app.test_client().get("/?ref=ABC123&fbclid=x")
    assert r.headers["Location"].endswith("/welcome?ref=ABC123&fbclid=x")


def test_welcome_page_opens(app):
    r = app.test_client().get("/welcome")
    assert r.status_code == 200 and b'id="register"' in r.data


def test_logged_in_shop_gets_panel_and_is_remembered(app):
    import webapp
    c = app.test_client()
    _login(c, _any_shop_id())
    r = c.get("/")
    assert r.status_code == 200
    assert webapp.KNOWN_COOKIE + "=1" in "".join(r.headers.getlist("Set-Cookie"))
    # вход истёк — знакомый браузер идёт на страницу входа, а не на рекламу
    with c.session_transaction() as s:
        s.clear()
    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_api_still_answers_401_not_welcome(app):
    r = app.test_client().get("/api/cars")
    assert r.status_code in (302, 401, 403)
    assert "/welcome" not in (r.headers.get("Location") or "")


def test_app_and_telegram_entry_go_to_login(app):
    r = app.test_client().get("/tg")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    import json, os
    manifest = json.load(open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "manifest.json")))
    assert manifest["start_url"] == "/tg"
