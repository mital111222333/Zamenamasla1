"""Аудит безопасности, круг 3: тесты-«атаки» на приложение.

Каждый тест изображает конкретную попытку взлома и проверяет, что она не
проходит: подбор пароля, вход без пароля, чужие данные, поддельный файл,
запрос с чужого сайта, заваливание запросами и т.д."""
import os
import re
import sqlite3
import time

import pytest

import database as db
import security

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD_PW = "Zx9-mountain-oil"


@pytest.fixture(scope="module")
def app():
    import webapp
    db.init_db()
    webapp.app.config["TESTING"] = True
    return webapp.app


@pytest.fixture(autouse=True)
def _fresh_limits():
    import webapp
    security.rate_reset()
    webapp._login_fails.clear()
    yield
    security.rate_reset()
    webapp._login_fails.clear()


def _shop(username):
    found = db.find_shop_by_username(username)
    if found:
        db.reset_shop_password(found["id"], GOOD_PW)
        return db.get_shop(found["id"])
    return db.create_shop(username, GOOD_PW, shop_name=username)


def _login(client, username, password=GOOD_PW):
    return client.post("/login", data={"username": username, "password": password})


def _events(kind):
    with sqlite3.connect(db.DB_PATH) as c:
        try:
            return c.execute("SELECT COUNT(*) FROM security_events WHERE kind=?", (kind,)).fetchone()[0]
        except sqlite3.OperationalError:
            return 0


# ---------- 1. Без входа закрыто всё, кроме публичных страниц ----------

PUBLIC = {
    "/", "/login", "/logout", "/app", "/install", "/m", "/privacy", "/register", "/referral", "/welcome",
    "/sw.js", "/ui/glass.css", "/ui/glass.js", "/static/<path:filename>", "/r/<code>", "/ocr/v1/<name>",
    "/passport/<token>", "/passport/<token>/pdf", "/display/<anpr_token>", "/scanner/<anpr_token>",
    "/api/display_state/<anpr_token>", "/api/anpr/<anpr_token>", "/api/hamyon/complete",
    "/api/hamyon/prepare", "/api/register", "/api/register/status", "/api/forgot_password/request",
    "/api/forgot_password/confirm", "/download/plate-agent.zip", "/course/<int:n>", "/tg",
    "/subscription", "/api/arrival", "/api/car_specs", "/api/vin/decode", "/oferta",
}


def test_anonymous_gets_no_data(app):
    c = app.test_client()
    opened = []
    for rule in app.url_map.iter_rules():
        if rule.rule in PUBLIC:
            continue
        url = re.sub(r"<int:[^>]+>", "1", rule.rule)
        url = re.sub(r"<[^>]+>", "x", url)
        for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            r = c.open(url, method=m, json={}, headers={"Accept": "application/json"})
            if r.status_code == 200:
                opened.append(f"{m} {rule.rule}")
    assert not opened, f"открыто без входа: {opened}"


# ---------- 2. Подбор пароля ----------

def test_password_bruteforce_is_blocked_and_logged(app):
    _shop("victim_shop")
    c = app.test_client()
    for _ in range(10):
        assert _login(c, "victim_shop", "wrong-pass").status_code == 200
    before = _events("login_locked")
    r = _login(c, "victim_shop", GOOD_PW)  # даже верный пароль — уже нет: адрес заблокирован
    assert r.status_code == 429
    assert _events("login_locked") == before + 1
    assert _events("login_failed") >= 10


def test_passwords_stored_only_as_hash(app):
    _shop("hash_shop")
    with sqlite3.connect(db.DB_PATH) as c:
        rows = c.execute("SELECT password_hash, password_plain FROM shops").fetchall()
    for h, plain in rows:
        assert h.startswith(("scrypt:", "pbkdf2:")), "пароль хранится не как стойкий хэш"
        assert GOOD_PW not in h and plain is None


@pytest.mark.parametrize("pw,login,problem", [
    ("short1", None, "short"), ("12345678", None, "common"), ("aaaaaaaaaa", None, "common"),
    ("myshop2026", "myshop2026", "same_as_login"), (GOOD_PW, "someone", None),
])
def test_password_policy(pw, login, problem):
    assert security.password_problem(pw, login) == problem


def test_register_rejects_weak_password(app):
    r = app.test_client().post("/api/register", json={
        "shop_name": "Test", "owner_name": "Ali", "city": "Andijon", "phone": "901112233",
        "address": "street 1", "username": "weakpw1", "password": "12345678", "password2": "12345678"})
    assert r.status_code in (400, 503)
    if r.status_code == 400:
        assert r.get_json().get("field") == "password"


# ---------- 3. Сброс пароля: срок и подбор кода ----------

def test_reset_code_expires(app):
    shop = _shop("reset_shop")
    code = db.create_password_reset_code(shop["id"])
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE password_reset_codes SET expires_at='2000-01-01 00:00:00' WHERE shop_id=?", (shop["id"],))
        c.commit()
    assert not db.reset_password_with_code("reset_shop", code, "New-strong-pass-1")


def test_reset_code_burns_after_5_wrong_tries(app):
    shop = _shop("reset_shop2")
    code = db.create_password_reset_code(shop["id"])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert not db.reset_password_with_code("reset_shop2", wrong, "New-strong-pass-1")
    assert not db.reset_password_with_code("reset_shop2", code, "New-strong-pass-1"), "код не сгорел после подбора"


def test_reset_confirm_rejects_weak_password(app):
    r = app.test_client().post("/api/forgot_password/confirm",
                               json={"username": "reset_shop", "code": "123456", "new_password": "123456"})
    assert r.status_code == 400


# ---------- 4. Админка ----------

def _admin(app):
    with sqlite3.connect(db.DB_PATH) as c:
        aid, name = c.execute("SELECT id, username FROM shops WHERE role='admin' LIMIT 1").fetchone()
    db.reset_shop_password(aid, GOOD_PW)
    return name


def test_admin_login_is_logged(app):
    name = _admin(app)
    before = _events("admin_login")
    c = app.test_client()
    assert _login(c, name).status_code == 302
    assert _events("admin_login") == before + 1
    assert c.get("/api/admin/security_events").status_code == 200


def test_admin_session_expires(app):
    name = _admin(app)
    c = app.test_client()
    _login(c, name)
    with c.session_transaction() as s:
        s["login_at"] = int(time.time()) - 13 * 3600
    assert c.get("/api/admin/shops", headers={"Accept": "application/json"}).status_code == 401


def test_shop_cannot_open_admin(app):
    _shop("plain_shop")
    c = app.test_client()
    _login(c, "plain_shop")
    for path in ("/api/admin/shops", "/api/admin/security_events", "/api/admin/sub/payments"):
        assert c.get(path, headers={"Accept": "application/json"}).status_code in (401, 302, 403)


# ---------- 5. Чужие данные (одна точка лезет в другую) ----------

def test_shop_cannot_touch_other_shops_product(app):
    a, b = _shop("tenant_a"), _shop("tenant_b")
    prod_b = db.create_product(b["id"], "oil", "Чужое масло", sell_price=100000)
    c = app.test_client()
    _login(c, "tenant_a")
    r = c.put(f"/api/products/{prod_b['id']}", json={"sell_price": 1})
    assert r.status_code in (400, 403, 404)
    r = c.delete(f"/api/products/{prod_b['id']}")
    assert r.status_code in (400, 403, 404)
    r = c.get(f"/api/branches/{b['id']}/products")
    assert r.status_code in (400, 403, 404)
    assert db.get_product(prod_b["id"], b["id"])["sell_price"] == 100000


# ---------- 6. Файлы ----------

SVG_XSS = b'<svg xmlns="http://www.w3.org/2000/svg"><script>fetch("/api/admin/shops")</script></svg>'


@pytest.mark.parametrize("data,ok", [
    (b"\xff\xd8\xff\xe0" + b"0" * 20, True), (b"\x89PNG\r\n\x1a\n" + b"0" * 8, True), (b"%PDF-1.7 ...", True),
    (SVG_XSS, False), (b"<html><script>alert(1)</script>", False), (b"MZ\x90\x00", False),
])
def test_upload_type_by_content(data, ok):
    assert (security.sniff_upload(data)[0] is not None) == ok


def test_receipt_upload_uses_content_sniffing():
    src = open(os.path.join(ROOT, "subscription.py"), encoding="utf-8").read()
    pay = src[src.index("def api_subscription_pay"):src.index("def api_subscription_auto")]
    assert "security.sniff_upload(data)" in pay
    assert 'startswith("image/")' not in pay, "снова принимаются любые image/* (в т.ч. SVG со скриптом)"
    view = src[src.index("def api_admin_sub_receipt"):]
    assert "SAFE_INLINE_MIME" in view and "sandbox" in view


def test_oversized_upload_rejected(app):
    r = app.test_client().post("/api/subscription/pay", data=b"0" * (21 * 1024 * 1024),
                               content_type="application/octet-stream")
    assert r.status_code == 413


# ---------- 7. CSRF, CORS, заголовки, HTTPS, отладка ----------

def test_cross_site_post_rejected_and_logged(app):
    _shop("csrf_shop")
    c = app.test_client()
    _login(c, "csrf_shop")
    before = _events("csrf_blocked")
    r = c.post("/api/products", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert _events("csrf_blocked") == before + 1


def test_no_cors_for_foreign_sites(app):
    c = app.test_client()
    for m in ("GET", "OPTIONS"):
        r = c.open("/api/cars", method=m, headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "POST"})
        assert "Access-Control-Allow-Origin" not in r.headers
        assert "Access-Control-Allow-Credentials" not in r.headers


def test_security_headers(app):
    r = app.test_client().get("/login")
    for h in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"):
        assert h in r.headers, h
    r = app.test_client().get("/login", base_url="https://oil.example")
    assert "Strict-Transport-Security" in r.headers


def test_http_redirects_to_https(app, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://oil.example")
    r = app.test_client().get("/login?lang=uz", base_url="http://oil.example")
    assert r.status_code == 301 and r.headers["Location"].startswith("https://oil.example/login")
    # камеры (часто умеют только http) и POST — не перенаправляем
    assert app.test_client().post("/api/anpr/x", base_url="http://oil.example").status_code != 301


def test_debug_mode_off(app):
    assert not app.debug
    src = open(os.path.join(ROOT, "webapp.py"), encoding="utf-8").read()
    assert "debug=True" not in src


# ---------- 8. Частота запросов ----------

def test_rate_limit_on_public_token_endpoint(app):
    c = app.test_client()
    codes = [c.get("/api/display_state/guess").status_code for _ in range(420)]
    assert 429 in codes, "перебор токенов табло не ограничен"
    assert codes[0] != 429


def test_rate_limit_on_login(app):
    c = app.test_client()
    codes = [c.get("/login").status_code for _ in range(40)]
    assert codes.count(429) > 0


# ---------- 9. Переменные окружения и секреты ----------

def test_env_check_flags_dangerous_settings():
    bad = dict(SECRET_KEY="short", PUBLIC_URL="http://oil.example", FLASK_DEBUG="1",
               PLATFORM_ADMIN_PASSWORD="12345678", HAMYON_SHOP_ID="1")
    msgs = " ".join(m for lvl, m in security.check_env(bad) if lvl == "critical")
    for word in ("SECRET_KEY", "https", "отладки", "PLATFORM_ADMIN_PASSWORD", "HAMYON_SHOP_KEY"):
        assert word in msgs, word
    good = dict(SECRET_KEY="k" * 10 + "0123456789abcdefghijklmnop", PUBLIC_URL="https://oil.example",
                BOT_TOKEN="1:x", ADMIN_TELEGRAM_ID="1", BACKUP_PASSWORD="long-backup-pass-123")
    assert [m for lvl, m in security.check_env(good) if lvl == "critical"] == []


def test_no_secrets_in_tracked_files():
    """В коде не должно быть настоящих токенов/ключей (только из окружения)."""
    pat = re.compile(r"\d{8,10}:AA[A-Za-z0-9_-]{30,}|sk_live_[0-9A-Za-z]{20,}|AKIA[0-9A-Z]{16}|"
                     r"ghp_[A-Za-z0-9]{36}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
    for name in os.listdir(ROOT):
        if name.endswith((".py", ".md", ".txt", ".json", ".html", ".yml")):
            with open(os.path.join(ROOT, name), encoding="utf-8", errors="ignore") as f:
                assert not pat.search(f.read()), f"похоже на секрет в {name}"
