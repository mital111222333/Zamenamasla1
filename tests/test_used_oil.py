"""Учёт отработки: слито считается само по заменам (× процент слива),
продажа — запись «без машины» kind used_oil, всегда наличными; деньги
попадают в кассу/«Закрыть день», выручку и прибыль, но не в число визитов
и средний чек. Сотрудник продаёт, но не видит итогов и не делает замер."""
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
    head = db.create_shop("uo_head", "Pass12345!", shop_name="UO Head")
    hid = head["id"] if isinstance(head, dict) else head
    br = db.create_branch_shop(hid, "uo_branch", "Pass12345!", shop_name="UO Filial")
    emp = db.create_shop_employee(hid, "uo_emp", "Pass12345!", full_name="Usta")
    return {"db": db, "webapp": webapp, "hid": hid, "bid": br["id"], "emp": emp}


def _login(env, employee=False, branch=False):
    db, webapp = env["db"], env["webapp"]
    sid = env["bid"] if branch else env["hid"]
    shop = db.get_shop(sid)
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"] = sid, "branch" if branch else "shop"
        if branch:
            s["parent_shop_id"] = env["hid"]
        if employee:
            full = db.get_active_employee("uo_emp", env["hid"])
            s["username"], s["is_employee"] = "uo_emp", True
            s["pwf"] = webapp._pw_fingerprint(full.get("password_hash"))
        else:
            s["username"], s["is_employee"] = shop["username"], False
            s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def _visit(c, plate, engine=4, gearbox=None):
    items = [{"key": "fluid_0", "name": "Масло", "brand": "X 5W30", "unit_price": 50000, "qty": engine,
              "total": 50000 * engine}]
    if gearbox:
        items.append({"key": "fluid_1", "name": "АКПП", "brand": "ATF", "unit_price": 60000, "qty": gearbox,
                      "total": 60000 * gearbox})
    total = sum(i["total"] for i in items)
    r = c.post("/api/add", json={"plate": plate, "owner_name": "Ali", "items": items, "cash_amount": total,
                                 "mileage": 100000, "next_mileage": 108000})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(uo_[a-z0-9_]+|tab_usedoil|dir_used)\b", src))
    assert len(keys) > 30
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_collected_sale_balance_and_stats(env):
    db = env["db"]
    c = _login(env)
    _visit(c, "01U111AA", engine=4)
    _visit(c, "01U222AA", engine=4, gearbox=6)
    d = c.get("/api/used_oil").get_json()
    assert d["ok"] and d["full"] and d["pct"] == 90
    assert d["today"]["collected"] == 12.6 and d["today"]["cars"] == 2   # (4 + 4 + 6) × 90%
    assert d["balance"] == 12.6
    before = c.get("/api/stats").get_json()

    r = c.post("/api/used_oil/sale", json={"liters": 2, "price": 6000, "token": "t1"}).get_json()
    assert r["ok"] and r["total"] == 12000
    dup = c.post("/api/used_oil/sale", json={"liters": 2, "price": 6000, "token": "t1"}).get_json()
    assert dup.get("duplicate")
    r = c.post("/api/used_oil/sale", json={"liters": "10,5", "price": 5500, "buyer": " Akmal  aka "}).get_json()
    assert not r.get("ok")  # «10,5» строкой с запятой браузер переводит сам; сервер ждёт число
    r = c.post("/api/used_oil/sale", json={"liters": 10.5, "price": 5500, "buyer": " Akmal  aka "}).get_json()
    assert r["ok"] and r["total"] == 57750

    d = c.get("/api/used_oil").get_json()
    assert d["today"]["sold"] == 12.5 and d["today"]["sum"] == 69750
    assert d["balance"] == 0.1
    assert d["walk_price"] == 6000
    assert d["buyers"][0]["name"] == "Akmal aka" and d["buyers"][0]["last_price"] == 5500
    m = d["periods"]["month"]
    assert m["sum"] == 69750 and m["avg_price"] == 5580 and m["per_car"] == 6.3

    # деньги — в выручке и кассе, но не в числе визитов
    after = c.get("/api/stats").get_json()
    assert after["today"]["total"] - before["today"]["total"] == 69750
    assert after["today"]["count"] == before["today"]["count"]
    today = datetime.now().strftime("%Y-%m-%d")
    dirs = c.get(f"/api/stats/directions?from={today}&to={today}").get_json()["dirs"]
    assert dirs["used"]["total"] == 69750 and dirs["used"]["qty"] == 12.5
    assert dirs["oil"]["total"] == before["today"]["total"]
    dc = c.get("/api/day_close").get_json()
    assert dc["used_oil"]["sum"] == 69750 and dc["used_oil"]["collected"] == 12.6
    assert dc["totals"]["count"] == 2
    assert db.get_profit_breakdown(env["hid"], today, today)["services"] >= 69750
    # в «Бренды» отработка не попадает
    import json as _json
    assert "Akmal" not in _json.dumps(c.get(f"/api/stats/brands?from={today}&to={today}").get_json() or {})


def test_check_pct_and_validation(env):
    c = _login(env)
    assert c.post("/api/used_oil/sale", json={"liters": 0, "price": 6000}).status_code == 400
    assert c.post("/api/used_oil/sale", json={"liters": 5, "price": -1}).status_code == 400
    r = c.post("/api/used_oil/check", json={"measured": 0}).get_json()
    assert r["ok"] and r["delta"] == -0.1
    d = c.get("/api/used_oil").get_json()
    assert d["balance"] == 0 and d["periods"]["month"]["shortage"] == 0.1
    assert c.post("/api/used_oil/pct", json={"pct": 30}).status_code == 400
    assert c.post("/api/used_oil/pct", json={"pct": 100}).get_json()["ok"]
    d = c.get("/api/used_oil").get_json()
    assert d["pct"] == 100 and d["today"]["collected"] == 14
    assert c.delete(f"/api/used_oil/check/{d['checks'][0]['id']}").get_json()["ok"]


def test_employee_sells_but_sees_no_totals(env):
    db = env["db"]
    e = _login(env, employee=True)
    d = e.get("/api/used_oil").get_json()
    assert d["ok"] and not d["full"]
    assert "periods" not in d and "history" not in d and d["today"]["sum"] is None
    r = e.post("/api/used_oil/sale", json={"liters": 1, "price": 6000}).get_json()
    assert r["ok"]
    d = e.get("/api/used_oil").get_json()
    assert len(d["my_sales"]) == 1 and d["my_sales"][0]["total"] == 6000
    emp_id = db.get_active_employee("uo_emp", env["hid"])["id"]
    assert db.get_employee_cash(env["hid"], emp_id)["balance"] >= 6000
    assert e.post("/api/used_oil/check", json={"measured": 5}).status_code in (302, 403)
    assert e.post("/api/used_oil/pct", json={"pct": 95}).status_code in (302, 403)
    dc = e.get("/api/day_close").get_json()
    assert set(dc["used_oil"]) == {"collected", "sold"}
    # сотрудник удаляет свою сегодняшнюю продажу
    assert e.delete(f"/api/oil_change/{d['my_sales'][0]['id']}").get_json()["ok"]


def test_branch_separate_and_head_sees_network(env):
    b = _login(env, branch=True)
    d = b.get("/api/used_oil").get_json()
    assert d["full"] and d["network"] is None and d["today"]["collected"] == 0
    assert b.post("/api/used_oil/sale", json={"liters": 50, "price": 6000, "buyer": "Bek"}).get_json()["ok"]
    h = _login(env).get("/api/used_oil").get_json()
    names = {n["name"]: n for n in h["network"]}
    assert names["UO Filial"]["month_sum"] == 300000
    assert all(x["buyer"] != "Bek" for x in h["history"])


def test_day_close_receipt_mentions_used_oil(env):
    import digest
    shop = env["db"].get_shop(env["hid"])
    c = {"day": datetime.now().strftime("%Y-%m-%d"), "services": 0, "revenue": 0, "cash": 0, "card": 0,
         "debt_out": 0, "repaid": 0, "expenses": 0, "expenses_from_cash": 1, "suppliers": 0,
         "suppliers_from_cash": 0, "float_start": 0, "expected": 0, "counted": 0, "diff": 0,
         "used_oil": {"collected": 96.4, "sold": 104, "sum": 624000}}
    t = digest.render_day_close(shop, c, "ru")
    assert "Отработка" in t and "96,4" in t and "624" in t
    assert "Otrabotka" in digest.render_day_close(shop, c, "uz")


def test_page_has_section(env):
    html = _login(env).get("/").get_data(as_text=True)
    assert 'id="view-usedoil"' in html and 'data-tab="usedoil"' in html
