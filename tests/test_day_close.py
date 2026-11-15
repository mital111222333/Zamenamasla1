"""«Закрытие дня»: сверка денег в кассе с программой + чек в Telegram.
Должно быть в кассе = размен + наличные замен + погашения долгов
− расходы/поставщики, если их брали из кассы."""
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
    sent = []
    webapp._send_telegram_message = lambda chat, text: sent.append((chat, text)) or True
    head = db.create_shop("dc_head", "Pass12345!", shop_name="Head DC", notify_telegram_id="111")
    hid = head["id"] if isinstance(head, dict) else head
    with db.get_conn() as conn:
        conn.execute("INSERT INTO clients (shop_id, full_name, link_token) VALUES (?, 'Ali', 'dctok1')", (hid,))
        cl = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO cars (shop_id, plate_number, client_id) VALUES (?, '01A777AA', ?)", (hid, cl))
        car = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, cash_amount, card_amount) "
                     "VALUES (?, ?, 500000, 300000, 200000)", (car, today))
        conn.execute("INSERT INTO expense_entries (shop_id, category, name, amount, expense_date) "
                     "VALUES (?, 'other', 'чай', 20000, ?)", (hid, today))
        conn.commit()
    emp = db.create_shop_employee(hid, "dc_emp", "Pass12345!", full_name="Mastер Bek")
    return {"db": db, "webapp": webapp, "hid": hid, "sent": sent, "today": today, "emp": emp}


def _login(env, employee=False):
    db, webapp = env["db"], env["webapp"]
    shop = db.get_shop(env["hid"])
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"] = env["hid"], "shop"
        if employee:
            e = next(x for x in db.list_shop_employees(env["hid"]) if x["username"] == "dc_emp")
            full = db.get_active_employee("dc_emp", env["hid"])
            s["username"], s["is_employee"] = "dc_emp", True
            s["pwf"] = webapp._pw_fingerprint(full.get("password_hash"))
            assert e
        else:
            s["username"], s["is_employee"] = shop["username"], False
            s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(dc_[a-z_]+|tab_dayclose)\b", src))
    import webapp
    keys |= set(re.findall(r'g\.T\["(dc_[a-z_]+)"\]', open(webapp.__file__, encoding="utf-8").read()))
    assert len(keys) > 30
    missing = [k for k in sorted(keys) if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_expected_formula(env):
    db = env["db"]
    s = db.day_close_summary(env["hid"], env["today"])
    assert s["totals"]["cash"] == 300000 and s["totals"]["card"] == 200000
    assert s["expected"] == 300000 - 20000          # расходы по умолчанию из кассы
    t = s["totals"]
    assert db.day_close_expected(t, 50000, False, False) == 350000


def test_owner_sees_numbers_and_closes(env):
    c = _login(env)
    d = c.get("/api/day_close").get_json()
    assert d["ok"] and not d["blind"] and d["expected"] == 280000 and "profit" in d
    # неверная «видел на экране» сумма — просим обновить, ничего не сохраняем
    r = c.post("/api/day_close", json={"counted": 280000, "expected_seen": 1})
    assert r.status_code == 409 and env["db"].get_day_closing(env["hid"], env["today"]) is None
    r = c.post("/api/day_close", json={"counted": 270000, "expected_seen": 280000, "note": "сдача",
                                       "expenses_from_cash": True})
    j = r.get_json()
    assert j["ok"] and j["closing"]["diff"] == -10000 and j["sent"]
    chat, text = env["sent"][-1]
    assert chat == "111" and "Недостача: 10 000" in text and "сдача" in text
    # закрыть заново = исправление той же записи
    j = c.post("/api/day_close", json={"counted": 280000, "expected_seen": 280000}).get_json()
    assert j["reclosed"] and j["closing"]["diff"] == 0 and j["closing"]["times_closed"] == 2
    assert "✅" in env["sent"][-1][1]


def test_employee_closes_blind(env):
    db = env["db"]
    yday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    c = _login(env, employee=True)
    d = c.get("/api/day_close?day=" + yday).get_json()
    assert d["ok"] and d["blind"] and "expected" not in d and "totals" not in d
    j = c.post("/api/day_close", json={"day": yday, "counted": 5000}).get_json()
    assert j["ok"] and j["blind"] and "closing" not in j
    row = db.get_day_closing(env["hid"], yday)
    assert row["by_employee"] == 1 and row["counted"] == 5000
    assert "(сотрудник)" in env["sent"][-1][1]
    # день, закрытый владельцем, сотрудник перезаписать не может
    r = c.post("/api/day_close", json={"counted": 1})
    assert r.status_code == 409
    assert db.get_day_closing(env["hid"], env["today"])["counted"] == 280000


def test_old_or_future_day_rejected(env):
    c = _login(env)
    old = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    fut = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert c.post("/api/day_close", json={"day": old, "counted": 1}).status_code == 400
    assert c.post("/api/day_close", json={"day": fut, "counted": 1}).status_code == 400


def test_branch_receipt_has_no_profit_but_head_gets_it():
    import digest
    c = {"day": "2026-11-15", "services": 3, "revenue": 900000, "cash": 900000, "card": 0, "debt_out": 0,
         "repaid": 0, "expenses": 0, "expenses_from_cash": 1, "suppliers": 0, "suppliers_from_cash": 0,
         "float_start": 0, "expected": 900000, "counted": 900000, "diff": 0, "note": None,
         "closed_by": None, "by_employee": 0, "times_closed": 1, "updated_at": "2026-11-15 19:40:00"}
    shop = {"shop_name": "Filial"}
    assert "Прибыль" not in digest.render_day_close(shop, c, "ru", profit=None)
    t = digest.render_day_close(shop, c, "uz", profit=300000, branch_name="Filial")
    assert "Foyda: 300 000" in t and "Filial" in t


def test_page_renders_with_section(env):
    c = _login(env)
    html = c.get("/").get_data(as_text=True)
    assert 'id="view-dayclose"' in html and 'data-tab="dayclose"' in html and "function dcOpen" in html
