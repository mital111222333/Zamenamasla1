"""«Анализ бизнеса» в статистике: план, сравнение 30 дней, вязкость, клиенты,
загрузка по дням, без закупки и без служебных записей #SALE."""
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
    sh = db.create_shop("an_head", "Pass12345!", shop_name="An")
    sid = sh["id"] if isinstance(sh, dict) else sh
    today = datetime.now().date()
    with db.get_conn() as conn:
        for n in range(12):
            conn.execute("INSERT INTO clients (shop_id, full_name, link_token) VALUES (?, ?, ?)", (sid, f"C{n}", f"antok{n}"))
            cl = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("INSERT INTO cars (shop_id, plate_number, client_id) VALUES (?, ?, ?)", (sid, f"01A{n:03d}AA", cl))
            car = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if n < 6:  # бывали раньше — постоянные
                conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json) VALUES (?, ?, 100000, '[]')",
                             (car, (today - timedelta(days=200)).strftime("%Y-%m-%d")))
            items = [{"key": "fluid_0", "name": "Масло", "brand": "MITANOL 5W-30" if n % 3 else "Liman 10w40", "qty": 4, "total": 200000}]
            if n % 2:
                items.append({"key": "filter_0", "name": "Фильтр", "unit_price": 30000, "qty": 1, "total": 30000})
            conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json, created_at) VALUES (?, ?, ?, ?, ?)",
                         (car, (today - timedelta(days=n % 5)).strftime("%Y-%m-%d"), 230000, json.dumps(items),
                          (today - timedelta(days=n % 5)).strftime("%Y-%m-%d") + " 10:15:00"))
        conn.commit()
    return {"db": db, "webapp": webapp, "sid": sid}


def _login(env):
    db, webapp = env["db"], env["webapp"]
    shop = db.get_shop(env["sid"])
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"], s["username"], s["is_employee"] = env["sid"], "shop", shop["username"], False
        s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(an_[a-z_]+)\b", src))
    assert len(keys) > 30
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_analytics_numbers(env):
    db = env["db"]
    sid = env["sid"]
    car = db.get_walkin_car(sid)
    with db.get_conn() as conn:  # продажа без машины — деньги есть, визита нет
        conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json) VALUES (?, ?, 500000, '[]')",
                     (car, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
    d = _login(env).get("/api/stats/analytics").get_json()
    assert d["ok"]
    assert d["clients"]["unique"] == 12 and d["clients"]["returning"] == 6 and d["clients"]["new"] == 6
    assert d["liters"] == 48
    names = {v["name"]: v["liters"] for v in d["viscosity"]}
    assert names == {"5W-30": 32, "10W-40": 16}
    assert d["filter"] == {"oil_visits": 12, "no_filter": 6, "avg_price": 30000}
    assert d["sum30"] == 12 * 230000 + 500000
    assert sum(d["week"]) == 12
    assert sum(d["hours"].values()) == 12
    assert len(d["daily"]) == 30
    assert "cost_price" not in json.dumps(d) and "purchase" not in json.dumps(d)


def test_month_plan(env):
    c = _login(env)
    assert c.post("/api/stats/plan", json={"amount": 75000000}).get_json()["ok"]
    p = c.get("/api/stats/analytics").get_json()["plan"]
    assert p["amount"] == 75000000 and p["forecast"] >= p["per_day"] and p["need_per_day"] > 0
    assert c.post("/api/stats/plan", json={"amount": -5}).status_code == 400
    c.post("/api/stats/plan", json={"amount": 0})
    assert c.get("/api/stats/analytics").get_json()["plan"]["amount"] is None


def test_new_visits_get_time(env):
    db = env["db"]
    car = db.get_walkin_car(env["sid"])
    oc_id, _ = db.add_oil_change(car, None, None, None, False, 1000, 0)
    with db.get_conn() as conn:
        assert conn.execute("SELECT created_at FROM oil_changes WHERE id=?", (oc_id,)).fetchone()[0]
