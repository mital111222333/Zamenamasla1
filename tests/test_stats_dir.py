"""Вкладки «Шиномонтаж» и «Запчасти» в «Статистике»: выручка направления,
сравнение периодов, топ, клиенты, склад. Прибыль и закупка — не филиалу и
не сотруднику; выключенное направление не отдаётся."""
import json
import re
from datetime import datetime, timedelta

import pytest

import i18n


@pytest.fixture(scope="module")
def env():
    import database as db
    db.init_db()
    import webapp
    webapp.app.config["TESTING"] = True
    head = db.create_shop("sd_head", "Pass12345!", shop_name="SD Head")
    hid = head["id"] if isinstance(head, dict) else head
    db.set_shop_warehouse_enabled(hid, True)
    db.set_shop_dir_enabled(hid, "tire", True)
    db.set_shop_dir_enabled(hid, "part", True)
    db.create_shop_employee(hid, "sd_emp", "Pass12345!", full_name="Usta")
    plain = db.create_shop("sd_plain", "Pass12345!", shop_name="SD Plain")
    pid = plain["id"] if isinstance(plain, dict) else plain
    br = db.create_branch_shop(hid, "sd_branch", "Pass12345!", shop_name="SD Branch")
    bid = (br["id"] if isinstance(br, dict) else br) if br else None
    part = db.create_product(hid, "other", "Kolodka", "pc", 170000, 120000, 2, dir="part")
    idle = db.create_product(hid, "other", "Amortizator", "pc", 400000, 300000, 4, dir="part")
    today = datetime.now().date()
    with db.get_conn() as conn:
        for n in range(6):
            conn.execute("INSERT INTO clients (shop_id, full_name, link_token) VALUES (?, ?, ?)", (hid, f"S{n}", f"sdtok{n}"))
            cl = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("INSERT INTO cars (shop_id, plate_number, client_id) VALUES (?, ?, ?)", (hid, f"01S{n:03d}SS", cl))
            car = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            items = [{"key": "fluid_0", "name": "Масло", "brand": "Oil 5W30", "qty": 4, "total": 200000}]
            if n == 0:
                # был на шиномонтаже 3 месяца назад — постоянный
                conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json) VALUES (?, ?, 50000, ?)",
                             (car, (today - timedelta(days=100)).strftime("%Y-%m-%d"),
                              json.dumps([{"key": "tire_svc", "name": "Balansirovka", "qty": 1, "total": 50000, "dir": "tire"}])))
            if n < 2:
                items.append({"key": "tire_svc", "name": "Balansirovka", "qty": 4, "unit_price": 25000, "total": 100000, "dir": "tire"})
            if n == 2:
                items.append({"key": "other_stock", "name": "Kolodka", "product_id": part["id"], "qty": 1,
                              "unit_price": 170000, "total": 170000, "cost_price": 120000, "dir": "part"})
            cost = sum(i["total"] for i in items)
            conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json) VALUES (?, ?, ?, ?)",
                         (car, today.strftime("%Y-%m-%d"), cost, json.dumps(items)))
        conn.commit()
    db.add_walkin(hid, "day_svc", [{"key": "tire_svc", "name": "Podkachka", "qty": 1, "unit_price": 30000,
                                    "total": 30000, "dir": "tire"}], cash_amount=30000)
    return {"db": db, "webapp": webapp, "hid": hid, "pid": pid, "bid": bid, "part": part, "idle": idle}


def _login(env, sid=None, employee=False, role="shop"):
    db, webapp = env["db"], env["webapp"]
    sid = sid or env["hid"]
    shop = db.get_shop(sid)
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"] = sid, role
        if employee:
            full = db.get_active_employee("sd_emp", sid)
            s["username"], s["is_employee"] = "sd_emp", True
            s["pwf"] = webapp._pw_fingerprint(full.get("password_hash"))
        else:
            s["username"], s["is_employee"] = shop["username"], False
            s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(sd_[a-z_0-9]+)\b", src))
    assert len(keys) > 25
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_tire_numbers(env):
    c = _login(env)
    d = c.get("/api/stats/dir?dir=tire").get_json()
    assert d["ok"] and d["with_profit"] is True
    m = d["periods"]["today"]
    # 2 визита по 100 000 + мелкие услуги 30 000
    assert m["total"] == 230000 and m["visits"] == 3
    assert m["profit"] == 230000  # у услуг нет закупки
    assert d["day_svc"]["days"] == 1 and d["day_svc"]["total"] == 30000
    assert d["clients"]["cars"] == 2 and d["clients"]["returning"] == 1 and d["clients"]["new"] == 1
    assert d["clients"]["oil_visits"] == 6 and d["clients"]["cross"] == 2
    names = [t["name"] for t in d["top"]]
    assert names[0] == "Balansirovka"
    assert d["daily"][-1]["total"] == 230000 and len(d["daily"]) == 30


def test_part_profit_and_stock(env):
    c = _login(env)
    d = c.get("/api/stats/dir?dir=part").get_json()
    m = d["periods"]["today"]
    assert m["total"] == 170000 and m["profit"] == 50000
    st = d["stock"]
    assert st["items"] == 2 and st["value"] == 2 * 120000 + 4 * 300000
    assert [x["name"] for x in st["low"]] == ["Kolodka"]
    assert st["idle_count"] == 1 and st["idle_value"] == 1200000


def test_share_of_business(env):
    c = _login(env)
    d = c.get("/api/stats/dir?dir=part").get_json()
    total = 6 * 200000 + 2 * 100000 + 170000 + 30000
    assert d["share_month"] == round(170000 / total * 100)


def test_employee_blocked_and_disabled_dir(env):
    c = _login(env, employee=True)
    r = c.get("/api/stats/dir?dir=tire")
    assert r.status_code in (302, 401, 403)
    c2 = _login(env, sid=env["pid"])
    assert c2.get("/api/stats/dir?dir=tire").status_code == 400
    assert _login(env).get("/api/stats/dir?dir=oil").status_code == 400


def test_branch_gets_no_profit(env):
    db = env["db"]
    if not env["bid"]:
        pytest.skip("нет create_branch")
    c = _login(env, sid=env["bid"], role="shop")
    d = c.get("/api/stats/dir?dir=tire").get_json()
    assert d["ok"] and d["with_profit"] is False
    blob = json.dumps(d)
    assert '"profit"' not in blob and '"value"' not in blob and "idle_value" not in blob


def test_panel_has_tabs_only_when_enabled(env):
    html = _login(env).get("/").get_data(as_text=True)
    assert 'id="sdTabs"' in html and "sdTab('tire')" in html and "sdTab('part')" in html
    html2 = _login(env, sid=env["pid"]).get("/").get_data(as_text=True)
    assert 'id="sdTabs"' not in html2 and 'id="stMainPane"' in html2
