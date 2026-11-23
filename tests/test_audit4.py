"""Аудит, круг 4: продажа без машины и отработка — не «замены» мастера
(Команда, значки, «Мастера сегодня», сводка в Telegram), плюс сверка
основных расчётов на одном сценарии."""
import sqlite3
from datetime import date, datetime

import pytest

import database as db

PW = "Audit4#Pass2026x"


@pytest.fixture(scope="module")
def env():
    db.init_db()
    import webapp
    webapp.app.config["TESTING"] = True
    head = db.create_shop("a4_head", PW, shop_name="A4 Head")
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE shops SET paid_until='2099-01-01', trial=0, warehouse_enabled=1 WHERE id=?", (head["id"],))
        c.commit()
    db.set_shop_dir_enabled(head["id"], "part", True)  # «Продажа без машины» — у точек с запчастями/шинами
    db.create_shop_employee(head["id"], "a4_emp", PW, full_name="Usta A4")

    def login(user):
        cl = webapp.app.test_client()
        r = cl.post("/login", data={"username": user, "password": PW})
        assert r.status_code in (302, 303)
        return cl
    owner, emp = login("a4_head"), login("a4_emp")
    p = owner.post("/api/products", json={"category": "motor_oil", "name": "A4 OIL", "sell_price": 50000,
                                          "purchase_price": 35000, "initial_stock": 100}).get_json()
    pid = (p.get("product") or p)["id"]
    emp_id = next(e["id"] for e in db.list_shop_employees(head["id"]) if e["username"] == "a4_emp")
    return {"head": head["id"], "owner": owner, "emp": emp, "pid": pid, "emp_id": emp_id}


def _oil(pid, qty, price=50000):
    return [{"key": "fluid_0", "name": "Моторное масло", "product_id": pid, "unit_price": price,
             "qty": qty, "total": int(price * qty)}]


def _board_row(env):
    board = env["owner"].get("/api/team").get_json()["board"]
    return next(r for r in board if r["id"] == env["emp_id"])


def test_walkin_and_used_oil_are_not_services_of_master(env):
    r = env["emp"].post("/api/add", json={"plate": "01A400AA", "owner_name": "Client", "items": _oil(env["pid"], 4),
                                          "cash_amount": 200000}).get_json()
    assert r["ok"]
    before = _board_row(env)
    assert before["services"] == 1
    for _ in range(2):
        assert env["emp"].post("/api/walkin", json={"kind": "sale", "items": _oil(env["pid"], 1),
                                                    "cash_amount": 50000}).get_json()["ok"]
    assert env["emp"].post("/api/used_oil/sale", json={"liters": 5, "price": 6000}).get_json()["ok"]
    after = _board_row(env)
    # раньше каждая продажа давала +1 замену и +15 очков («постоянный клиент» #SALE)
    assert after["services"] == before["services"]
    assert after["points"] == before["points"]
    # но продажа без машины — его продажа: деньги для % от товаров учитываются,
    # а отработка (доход точки) — нет
    assert after["salary"]["goods_money"] == before["salary"]["goods_money"] + 100000
    assert db.team_badges(env["head"], env["emp_id"])["total_services"] == 1


def test_pulse_masters_count_only_cars(env):
    p = env["owner"].get("/api/stats/pulse").get_json()
    m = next(x for x in p["masters"] if x["name"] == "Usta A4")
    assert m["count"] == 1               # «1 маш.», не 3
    assert m["total"] == 200000 + 100000  # продажи без машины — в выручке мастера


def test_digest_counts_cars_only(env):
    import digest
    shop = db.get_shop(env["head"])
    text = digest.build(shop, "evening", datetime.now().replace(hour=22))
    text = text if isinstance(text, str) else str(text)
    assert "Замен: 1 " in text or "Замен: 1\n" in text or "Замен: 1 ·" in text
    staff = db.digest_staff_day(env["head"], date.today().isoformat())
    assert [s["count"] for s in staff if s["name"] == "Usta A4"] == [1]


def test_core_money_reconciles(env):
    """Прибыль, выручка, нал/карта, склад на одном сценарии — сверка вручную."""
    t = date.today().isoformat()
    base = db.get_profit_breakdown(env["head"], t, t)
    rev0 = db.get_revenue_stats(env["head"])["today"]
    st0 = db.get_product(env["pid"], env["head"])["stock_qty"]
    items = _oil(env["pid"], 4) + [{"key": "labor", "name": "Работа", "unit_price": 20000, "qty": 1, "total": 20000}]
    r = env["owner"].post("/api/add", json={"plate": "01A401AA", "owner_name": "Vali", "items": items,
                                            "discount": 10000, "cash_amount": 100000,
                                            "card_amount": 110000}).get_json()
    assert r["ok"]
    after = db.get_profit_breakdown(env["head"], t, t)
    assert after["goods_profit"] - base["goods_profit"] == 4 * 15000
    assert after["services"] - base["services"] == 20000 - 10000
    rev = db.get_revenue_stats(env["head"])["today"]
    assert rev["total"] - rev0["total"] == 210000
    assert rev["cash"] - rev0["cash"] == 100000 and rev["card"] - rev0["card"] == 110000
    assert round(st0 - db.get_product(env["pid"], env["head"])["stock_qty"], 3) == 4
    # удаление возвращает товар и убирает деньги
    assert env["owner"].delete(f"/api/oil_change/{r['oc_id']}").get_json()["ok"]
    assert db.get_product(env["pid"], env["head"])["stock_qty"] == st0
    assert db.get_revenue_stats(env["head"])["today"]["total"] == rev0["total"]
