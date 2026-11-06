"""Напоминания: у моторного масла и масла АКПП — свои сроки и пробег.
Визит без моторного масла не сбрасывает его напоминание; «уже поменял» по
одному не отменяет другое; два срока в один день — одно сообщение."""
import sqlite3
from datetime import datetime, timedelta

import pytest

import database as db

OIL = {"key": "fluid_0", "name": "Моторное масло", "brand": "MITANOL", "unit_price": 80000, "qty": 4, "total": 320000}
ATF = {"key": "fluid_1", "name": "АКПП", "brand": "ATF", "unit_price": 90000, "qty": 4, "total": 360000}
AIR = {"key": "filter_1", "name": "Воздушный фильтр", "brand": "AF", "unit_price": 50000, "qty": 1, "total": 50000}


def _car(plate):
    with sqlite3.connect(db.DB_PATH) as c:
        sid = c.execute("SELECT id FROM shops WHERE role='shop' ORDER BY id LIMIT 1").fetchone()[0]
    cl = db.get_or_create_client(sid, "Тест", None)
    cl = cl["id"] if isinstance(cl, dict) else cl
    car = db.create_or_update_car(sid, plate, cl, "Chevrolet", "Cobalt")
    return car["id"] if isinstance(car, dict) else car


def _last(car_id):
    with sqlite3.connect(db.DB_PATH) as c:
        c.row_factory = sqlite3.Row
        return dict(c.execute("SELECT * FROM oil_changes WHERE car_id=? ORDER BY id DESC LIMIT 1", (car_id,)).fetchone())


def _set(oc_id, **kw):
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE oil_changes SET " + ", ".join(f"{k}=?" for k in kw) + " WHERE id=?", (*kw.values(), oc_id))
        c.commit()


@pytest.fixture(scope="module", autouse=True)
def _db():
    db.init_db()


def test_oil_and_atf_get_own_dates_and_km():
    car = _car("01R001AA")
    db.add_oil_change(car, 100000, "", "", False, 0, 3, items=[OIL, ATF], next_mileage=105000,
                      atf={"interval_value": 6, "next_mileage": None})
    r = _last(car)
    in3 = (datetime.now() + timedelta(days=89)).strftime("%Y-%m-%d")
    in6 = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
    assert r["next_change_date"] >= in3 and r["next_mileage"] == 105000
    assert r["atf_next_date"] >= in6 and r["atf_next_mileage"] == 140000   # 100 000 + 40 000 по умолчанию


def test_visit_without_oil_keeps_oil_and_atf_reminders():
    car = _car("01R002AA")
    db.add_oil_change(car, 50000, "", "", False, 0, 3, items=[OIL, ATF], next_mileage=55000)
    first = _last(car)
    db.add_oil_change(car, 51000, "", "", False, 0, 3, items=[AIR])     # приехал только за фильтром
    second = _last(car)
    assert second["id"] != first["id"]
    assert second["next_change_date"] == first["next_change_date"] and second["next_mileage"] == 55000
    assert second["atf_next_date"] == first["atf_next_date"]


def test_both_due_same_day_is_one_reminder():
    car = _car("01R003AA")
    db.add_oil_change(car, 70000, "", "", False, 0, 3, items=[OIL, ATF])
    r = _last(car)
    today = datetime.now().strftime("%Y-%m-%d")
    _set(r["id"], next_change_date=today, atf_next_date=today)
    due = [x for x in db.get_due_reminders() if x["id"] == r["id"]]
    assert len(due) == 1 and due[0]["due_oil"] and due[0]["due_atf"]
    db.mark_reminder_sent(r["id"], oil=True, atf=True)
    after = _last(car)
    assert after["reminder_count"] == 1 and after["atf_reminder_count"] == 1
    assert not [x for x in db.get_due_reminders() if x["id"] == r["id"]]   # повтор — через 14 дней


def test_changed_elsewhere_for_oil_keeps_atf():
    car = _car("01R004AA")
    db.add_oil_change(car, 80000, "", "", False, 0, 3, items=[OIL, ATF])
    r = _last(car)
    today = datetime.now().strftime("%Y-%m-%d")
    _set(r["id"], next_change_date=today, atf_next_date=today)
    db.mark_already_changed_elsewhere(r["id"])               # «уже поменял» — про моторное масло
    due = [x for x in db.get_due_reminders() if x["id"] == r["id"]]
    assert len(due) == 1 and not due[0]["due_oil"] and due[0]["due_atf"]
    db.close_atf_reminder(r["id"])                           # «уже поменял» — про АКПП
    assert not [x for x in db.get_due_reminders() if x["id"] == r["id"]]


def test_old_visit_without_atf_keeps_old_behaviour():
    car = _car("01R005AA")
    db.add_oil_change(car, 90000, "", "", False, 0, 3, items=[OIL])
    r = _last(car)
    assert r["atf_next_date"] is None and r["next_change_date"]
