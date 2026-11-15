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
    keys = set(re.findall(r"\bT\.(dir_[a-z]+|ts_[a-z_]+|st_dirs_[a-z_]+|cat_tire[a-z_]*|cat_parts|wh_cat_tires|wh_cat_parts|wh_dir_label)\b", src))
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
