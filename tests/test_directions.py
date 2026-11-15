"""Направления точки: масло / шиномонтаж / автозапчасти.
Направление позиции чека определяется само: у товара — от товара на складе,
у услуги шиномонтажа (tire_svc) — шиномонтаж. Статистика делит выручку
записи (уже со скидкой) между направлениями пропорционально позициям."""
import json
import re
from datetime import datetime

import pytest

import i18n


@pytest.fixture(scope="module")
def env():
    import database as db
    db.init_db()
    import webapp
    webapp.app.config["TESTING"] = True
    head = db.create_shop("dir_head", "Pass12345!", shop_name="Dir Head")
    hid = head["id"] if isinstance(head, dict) else head
    db.set_shop_warehouse_enabled(hid, True)
    db.set_shop_dir_enabled(hid, "tire", True)
    db.set_shop_dir_enabled(hid, "part", True)
    emp = db.create_shop_employee(hid, "dir_emp", "Pass12345!", full_name="Usta")
    return {"db": db, "webapp": webapp, "hid": hid, "emp": emp}


def _login(env, employee=False):
    db, webapp = env["db"], env["webapp"]
    shop = db.get_shop(env["hid"])
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"] = env["hid"], "shop"
        if employee:
            full = db.get_active_employee("dir_emp", env["hid"])
            s["username"], s["is_employee"] = "dir_emp", True
            s["pwf"] = webapp._pw_fingerprint(full.get("password_hash"))
        else:
            s["username"], s["is_employee"] = shop["username"], False
            s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(dir_[a-z]+|ds_[a-z_]+|ws_[a-z_]+|ts_[a-z_]+|st_dirs_[a-z_]+|cat_tire[a-z_]*|cat_parts|wh_cat_tires|wh_cat_parts|wh_dir_label)\b", src))
    assert len(keys) > 15
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_sanitize_keeps_only_known_dirs():
    import database as db
    out = db.sanitize_items([
        {"key": "tire_svc", "name": "Balans", "qty": 4, "unit_price": 15000, "total": 60000, "dir": "tire"},
        {"key": "other", "name": "X", "total": 1000, "dir": "<b>evil</b>"},
    ])
    assert out[0]["dir"] == "tire"
    assert "dir" not in out[1]
    assert db.item_dir({"key": "tire_svc"}) == "tire"
    assert db.item_dir({"key": "fluid_0"}) == "oil"


def test_product_dir_only_for_other_goods(env):
    db, hid = env["db"], env["hid"]
    t = db.create_product(hid, "other", "Shina 205/55 R16", "pc", 900000, 700000, 8, dir="tire")
    oil = db.create_product(hid, "fluid_0", "Mitanol 5W30", "l", 60000, 45000, 20, dir="tire")
    assert t["dir"] == "tire"
    assert oil["dir"] == ""  # у масла направления нет — это всегда масло
    assert db.set_product_dir(oil["id"], hid, "part") is False


def test_add_visit_stamps_dirs_and_splits_stats(env):
    db, hid = env["db"], env["hid"]
    c = _login(env)
    tire = db.create_product(hid, "other", "Shina R15", "pc", 500000, 400000, 10, dir="tire")
    part = db.create_product(hid, "other", "Kolodka", "pc", 170000, 120000, 5, dir="part")
    oil = db.create_product(hid, "fluid_0", "Oil 5W40", "l", 50000, 40000, 30)
    items = [
        {"key": "fluid_0", "name": "Масло", "brand": "Oil 5W40", "product_id": oil["id"], "unit_price": 50000, "qty": 4, "total": 200000},
        {"key": "tire_svc", "name": "Balansirovka", "unit_price": 25000, "qty": 4, "total": 100000, "dir": "tire"},
        {"key": "other_stock", "name": "Shina R15", "product_id": tire["id"], "unit_price": 500000, "qty": 1, "total": 500000, "dir": "part"},
        {"key": "other_stock", "name": "Kolodka", "product_id": part["id"], "unit_price": 170000, "qty": 1, "total": 170000},
    ]
    total = 970000
    r = c.post("/api/add", json={"plate": "01D555DD", "owner_name": "Bek", "items": items,
                                 "cash_amount": total, "mileage": 100000, "next_mileage": 108000})
    assert r.status_code == 200, r.get_data(as_text=True)
    with db.get_conn() as conn:
        row = conn.execute("SELECT oc.items_json FROM oil_changes oc JOIN cars c ON c.id=oc.car_id "
                           "WHERE c.shop_id=? ORDER BY oc.id DESC LIMIT 1", (hid,)).fetchone()
    saved = json.loads(row["items_json"])
    dirs = {it["name"]: db.item_dir(it) for it in saved}
    # браузер прислал dir=part для шины — сервер берёт направление со склада
    assert dirs == {"Масло": "oil", "Balansirovka": "tire", "Shina R15": "tire", "Kolodka": "part"}

    today = datetime.now().strftime("%Y-%m-%d")
    d = c.get(f"/api/stats/directions?from={today}&to={today}").get_json()
    assert d["ok"]
    assert d["dirs"]["oil"]["total"] == 200000
    assert d["dirs"]["tire"]["total"] == 600000
    assert d["dirs"]["part"]["total"] == 170000
    assert d["dirs"]["oil"]["qty"] == 4 and d["dirs"]["tire"]["qty"] == 5
    assert d["dirs"]["tire"]["visits"] == 1


def test_discount_is_shared_between_directions(env):
    db = env["db"]
    with db.get_conn() as conn:
        car = conn.execute("SELECT id FROM cars WHERE shop_id=? LIMIT 1", (env["hid"],)).fetchone()["id"]
        items = [{"key": "fluid_0", "name": "M", "total": 100000}, {"key": "tire_svc", "name": "T", "total": 100000, "dir": "tire"}]
        conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json) VALUES (?, '2020-01-05', 180000, ?)",
                     (car, json.dumps(items)))
        conn.commit()
    d = db.get_direction_range(env["hid"], "2020-01-01", "2020-01-31")
    assert d["oil"]["total"] == 90000 and d["tire"]["total"] == 90000


def test_employee_has_no_direction_stats(env):
    c = _login(env, employee=True)
    r = c.get("/api/stats/directions?from=2020-01-01&to=2020-01-31")
    assert r.status_code in (302, 403)


def test_branch_inherits_head_dirs(env):
    db = env["db"]
    assert db.shop_dirs({"tire_enabled": 0, "parts_enabled": 0, "parent_shop_id": env["hid"]}) == {"tire": True, "part": True}
    assert db.shop_dirs({"tire_enabled": 0, "parts_enabled": 0}) == {"tire": False, "part": False}


def test_page_shows_direction_tiles_only_when_enabled(env):
    db = env["db"]
    c = _login(env)
    html = c.get("/").get_data(as_text=True)
    assert '"tire": true' in html.replace("'", '"') or '"tire":true' in html
    assert 'id="dirCard"' in html
    db.set_shop_dir_enabled(env["hid"], "tire", False)
    db.set_shop_dir_enabled(env["hid"], "part", False)
    html = c.get("/").get_data(as_text=True)
    assert 'id="dirCard"' not in html
    db.set_shop_dir_enabled(env["hid"], "tire", True)
    db.set_shop_dir_enabled(env["hid"], "part", True)


def test_admin_toggle_requires_admin(env):
    c = _login(env)
    r = c.post(f"/api/admin/shops/{env['hid']}/toggle_dir", json={"dir": "tire", "enabled": False})
    assert r.status_code in (302, 401, 403)


# ---------- «Мелкие услуги за день» и «Продажа без машины» ----------

def _today():
    return datetime.now().strftime("%Y-%m-%d")


def test_day_services_go_to_revenue_cash_and_tire(env):
    db = env["db"]
    c = _login(env)
    before = db.get_revenue_range(env["hid"], _today(), _today())["total"]
    r = c.post("/api/walkin", json={"kind": "day_svc", "day": _today(), "token": "ds-1",
                                    "items": [{"key": "tire_svc", "name": "Podkachka", "total": 200000},
                                              {"key": "tire_svc", "name": "Bosim", "total": 0}]})
    assert r.get_json()["ok"], r.get_data(as_text=True)
    # повтор той же отправки (плохой интернет) — второй раз не пишется
    assert c.post("/api/walkin", json={"kind": "day_svc", "day": _today(), "token": "ds-1",
                                       "items": [{"key": "tire_svc", "name": "Podkachka", "total": 200000}]}).get_json()["duplicate"]
    rev = db.get_revenue_range(env["hid"], _today(), _today())
    assert rev["total"] == before + 200000
    d = db.get_direction_range(env["hid"], _today(), _today())
    assert d["tire"]["total"] >= 200000
    dc = c.get("/api/day_close").get_json()
    assert [x["total"] for x in dc["day_svc"]] == [200000]
    assert dc["totals"]["cash"] >= 200000


def test_day_services_never_take_products_or_odd_days(env):
    db = env["db"]
    c = _login(env)
    prod = db.create_product(env["hid"], "other", "Vent", "pc", 5000, 2000, 10, dir="tire")
    r = c.post("/api/walkin", json={"kind": "day_svc", "day": _today(), "items": [
        {"key": "other_stock", "name": "Vent", "product_id": prod["id"], "qty": 5, "total": 25000}]})
    assert r.get_json()["ok"]
    assert db.get_product(prod["id"], env["hid"])["stock_qty"] == 10  # со склада ничего не ушло
    assert c.post("/api/walkin", json={"kind": "day_svc", "day": "2001-01-01",
                                       "items": [{"name": "X", "total": 1000}]}).status_code == 400
    assert c.post("/api/walkin", json={"kind": "day_svc", "day": _today(), "items": []}).status_code == 400


def test_counter_sale_takes_stock_and_stays_out_of_base(env):
    db = env["db"]
    c = _login(env)
    prod = db.create_product(env["hid"], "other", "Kolodka zad", "pc", 150000, 100000, 4, dir="part")
    r = c.post("/api/walkin", json={"kind": "sale", "cash_amount": 100000, "card_amount": 200000, "items": [
        {"key": "other_stock", "name": "Kolodka zad", "product_id": prod["id"], "unit_price": 150000, "qty": 2, "total": 300000}]})
    j = r.get_json()
    assert j["ok"] and j["total"] == 300000
    assert db.get_product(prod["id"], env["hid"])["stock_qty"] == 2
    rec = db.get_oil_change_for_shop(j["id"], env["hid"])
    assert rec["service_type"] == "sale" and rec["card_amount"] == 200000 and rec["cash_amount"] == 100000
    assert db.get_profit_breakdown(env["hid"], _today(), _today())["goods_profit"] >= 100000
    plates = [x["plate_number"] for x in db.get_all_cars_overview(env["hid"])]
    assert db.WALKIN_PLATE not in plates
    day = db.get_day_details(env["hid"], _today())
    sale = next(s for s in day["services"] if s["id"] == j["id"])
    assert sale["walkin"] == "sale" and sale["plate"] == "" and sale["owner_name"] is None


def test_walkin_needs_enabled_directions(env):
    db = env["db"]
    db.set_shop_dir_enabled(env["hid"], "tire", False)
    db.set_shop_dir_enabled(env["hid"], "part", False)
    try:
        c = _login(env)
        assert c.post("/api/walkin", json={"kind": "day_svc", "day": _today(),
                                           "items": [{"name": "X", "total": 1000}]}).status_code == 403
        assert c.post("/api/walkin", json={"kind": "sale", "items": [{"name": "X", "total": 1000}]}).status_code == 403
        assert 'id="view-sale"' not in c.get("/").get_data(as_text=True)
    finally:
        db.set_shop_dir_enabled(env["hid"], "tire", True)
        db.set_shop_dir_enabled(env["hid"], "part", True)


def test_employee_day_services_go_to_his_cash(env):
    db = env["db"]
    c = _login(env, employee=True)
    r = c.post("/api/walkin", json={"kind": "day_svc", "day": _today(), "items": [{"name": "Podkachka", "total": 30000}]})
    j = r.get_json()
    assert j["ok"]
    emp_id = db.get_active_employee("dir_emp", env["hid"])["id"]
    assert db.get_oil_change_for_shop(j["id"], env["hid"])["employee_id"] == emp_id
    mine = c.get("/api/day_close").get_json()["day_svc"]
    assert [x["total"] for x in mine] == [30000]  # чужие суммы сотрудник не видит
