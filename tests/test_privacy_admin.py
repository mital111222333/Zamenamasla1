"""Обещания из соглашения с клиентами (docs/foydalanish_shartlari_uz.md):
админ платформы не видит коммерческие данные точек, а оплата невозможна
без согласия с соглашением. Тесты следят, чтобы это не сломалось."""
import io
import os
import re
import sqlite3

import pytest

import database as db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "Zx9-mountain-oil"
BUSINESS_KEYS = {"count", "total", "avg", "clients", "pct", "today", "client_count", "revenue",
                 "purchase_price", "cs", "cq", "ct", "pt", "pq", "t", "s", "m", "points", "mital_brands"}


@pytest.fixture(scope="module")
def app():
    import webapp
    db.init_db()
    webapp.app.config["TESTING"] = True
    return webapp.app


@pytest.fixture(autouse=True)
def _limits():
    import security
    import webapp
    security.rate_reset()
    webapp._login_fails.clear()


def _admin_client(app):
    with sqlite3.connect(db.DB_PATH) as c:
        aid, name = c.execute("SELECT id, username FROM shops WHERE role='admin' LIMIT 1").fetchone()
    db.reset_shop_password(aid, PW)
    cl = app.test_client()
    assert cl.post("/login", data={"username": name, "password": PW}).status_code == 302
    return cl


def _shop(username):
    s = db.find_shop_by_username(username)
    if s:
        db.reset_shop_password(s["id"], PW)
        return db.get_shop(s["id"])
    return db.create_shop(username, PW, shop_name=username)


# ---------- админ не видит данные точек ----------

def test_map_has_no_business_numbers(app):
    _shop("priv_map_shop")
    data = _admin_client(app).get("/api/admin/map").get_json()
    assert data["points"]
    for p in data["points"]:
        leaked = BUSINESS_KEYS & set(p)
        assert not leaked, f"карта отдаёт данные точки: {leaked}"


def test_shop_list_hides_client_count_and_sms_account(app):
    _shop("priv_list_shop")
    shops = _admin_client(app).get("/api/admin/shops").get_json()
    for s in shops:
        for k in ("client_count", "eskiz_email", "eskiz_password", "password_hash"):
            assert k not in s


@pytest.mark.parametrize("path", ["/api/admin/shops/1/snapshot", "/api/admin/price_problems"])
def test_per_shop_views_removed(app, path):
    assert _admin_client(app).get(path).status_code == 404


def test_analytics_is_anonymous_and_needs_5_shops(app, monkeypatch):
    def line(shop, pkey, qty=4):
        return {"s": shop, "c": "fluid_0", "qty": qty, "total": 999999, "cp": 12345, "stock": True,
                "res": {"status": "exact", "pkey": pkey, "brand": "BRAND", "product": pkey}}
    lines = [line(i, "popular 5w30") for i in range(1, 6)] + [line(1, "rare oil"), line(2, "rare oil")]
    monkeypatch.setattr(db, "_scan_lines", lambda *_a, **_k: lines)
    data = _admin_client(app).get("/api/admin/analytics").get_json()
    names = [r["p"] for r in data["rows"]]
    assert "popular 5w30" in names, "товар 5+ точек должен быть в общей картине"
    assert "rare oil" not in names, "товар 2 точек выдаёт конкретные точки"
    for r in data["rows"]:
        assert not (BUSINESS_KEYS & set(r)), f"в аналитике цены/деньги/точки: {BUSINESS_KEYS & set(r)}"
    assert "points" not in data and "mital_brands" not in data
    assert "999999" not in str(data) and "12345" not in str(data)


def test_names_review_has_no_money(app):
    data = _admin_client(app).get("/api/admin/names").get_json()
    assert "unresolved_sum" not in data and "total_sum" not in data
    for key in ("review", "auto", "mapped"):
        for g in data.get(key) or []:
            assert "sum" not in g


def test_admin_ui_has_no_sales_targeting():
    src = open(os.path.join(ROOT, "admin_template.py"), encoding="utf-8").read()
    for bad in ("Возможности для продаж", "openSnapshot", "/snapshot", "price_problems", "Цены по точкам",
                "доля MITAL", "client_count"):
        assert bad not in src, f"в админке снова есть: {bad}"


# ---------- соглашение и согласие перед оплатой ----------

def test_oferta_version_matches_document():
    import oferta
    text = open(oferta.OFERTA_PATH, encoding="utf-8").read()
    m = re.search(r"\*\*Tahrir:\*\* ([\d.]+)", text)
    assert m and m.group(1) == oferta.OFERTA_VERSION, "OFERTA_VERSION и «Tahrir:» в документе разошлись"


def test_oferta_page_renders_safely(app):
    r = app.test_client().get("/oferta")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "OMONAT" in body and "<h2>" in body
    assert "To'lov sahifasidagi rozilik matni" not in body  # служебное приложение не показываем
    import oferta
    assert "<script>" not in oferta.md_to_html("<script>alert(1)</script> **x**")


def _pay_setup(app, monkeypatch, username):
    import subscription
    shop = _shop(username)
    db.set_platform_settings({"card_number": "5614000000000000"})
    monkeypatch.setattr(subscription, "ADMIN_TELEGRAM_ID", "1")
    monkeypatch.setattr(subscription, "BOT_TOKEN", "x")
    monkeypatch.setattr(subscription, "_send_receipt_to_admin", lambda *a, **k: (11, "file-id"))
    q = subscription._sub_quote(shop["id"])
    choice = str(q["options"][0]["months"])
    c = app.test_client()
    assert c.post("/login", data={"username": username, "password": PW}).status_code == 302
    return shop, c, choice


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def test_payment_without_agreement_is_refused(app, monkeypatch):
    _shop_, c, choice = _pay_setup(app, monkeypatch, "priv_pay_no")
    r = c.post("/api/subscription/pay", data={"choice": choice, "receipt": (io.BytesIO(JPEG), "chek.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json().get("oferta")
    r = c.post("/api/subscription/pay", data={"choice": choice, "agree": "1", "oferta_version": "0.1",
                                              "receipt": (io.BytesIO(JPEG), "chek.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 400, "согласие со старой редакцией не считается"


def test_payment_with_agreement_records_acceptance(app, monkeypatch):
    import oferta
    shop, c, choice = _pay_setup(app, monkeypatch, "priv_pay_yes")
    r = c.post("/api/subscription/pay", data={"choice": choice, "agree": "1", "oferta_version": oferta.OFERTA_VERSION,
                                              "receipt": (io.BytesIO(JPEG), "chek.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    acc = oferta.latest_acceptance(shop["id"])
    assert acc and acc["version"] == oferta.OFERTA_VERSION and acc["payment_id"] == r.get_json()["id"]
    assert acc["ip"]


def test_confirmed_payment_message_contains_promise(monkeypatch):
    import subscription
    shop = _shop("priv_msg_shop")
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE shops SET notify_telegram_id='777', language='uz' WHERE id=?", (shop["id"],))
        c.commit()
    sent = []
    monkeypatch.setattr(subscription, "_send_telegram_message", lambda chat, text: sent.append(text) or True)
    subscription.notify_sub_decision({"shop_id": shop["id"], "status": "confirmed", "kind": "extend",
                                      "new_until": "2027-01-01"})
    assert sent and "sotmaydi" in sent[0] and "Alloh" in sent[0]
