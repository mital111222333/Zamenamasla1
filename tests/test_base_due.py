"""«База»: кому пора на замену — группы по сроку (масло и АКПП), отметки
обзвона текущего цикла, чужую машину отметить нельзя."""
import sqlite3
from datetime import datetime, timedelta

import pytest

import database as db

OIL = {"key": "fluid_0", "name": "Моторное масло", "brand": "M", "unit_price": 80000, "qty": 4, "total": 320000}
ATF = {"key": "fluid_1", "name": "АКПП", "brand": "A", "unit_price": 90000, "qty": 4, "total": 360000}


@pytest.fixture(scope="module")
def sid():
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as c:
        return c.execute("SELECT id FROM shops WHERE role='shop' ORDER BY id LIMIT 1").fetchone()[0]


def _visit(sid, plate, oil_in=None, atf_in=None):
    cl = db.get_or_create_client(sid, "Клиент " + plate, "+998901112233")
    car = db.create_or_update_car(sid, plate, cl["id"] if isinstance(cl, dict) else cl, "Chevrolet", "Nexia")
    car = car["id"] if isinstance(car, dict) else car
    items = [OIL] + ([ATF] if atf_in is not None else [])
    db.add_oil_change(car, 70000, "", "", False, 0, 3, items=items)
    day = lambda n: (datetime.now() + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    with sqlite3.connect(db.DB_PATH) as c:
        oc = c.execute("SELECT MAX(id) FROM oil_changes WHERE car_id=?", (car,)).fetchone()[0]
        c.execute("UPDATE oil_changes SET next_change_date=? WHERE id=?", (day(oil_in if oil_in is not None else 200), oc))
        if atf_in is not None:
            c.execute("UPDATE oil_changes SET atf_next_date=? WHERE id=?", (day(atf_in), oc))
        c.commit()
    return car


def test_groups_by_due_date(sid):
    cars = {
        "today": _visit(sid, "01D000AA", oil_in=0),
        "tomorrow": _visit(sid, "01D001AA", oil_in=1),
        "week": _visit(sid, "01D005AA", oil_in=5),
        "month": _visit(sid, "01D020AA", oil_in=20),
        "overdue": _visit(sid, "01D003BB", oil_in=-3),
        "atf": _visit(sid, "01D111CC", oil_in=120, atf_in=1),   # масло нескоро, АКПП завтра
    }
    d = db.base_due(sid)
    where = {e["car_id"]: g for g, rows in d["groups"].items() for e in rows}
    assert where[cars["today"]] == "today" and where[cars["tomorrow"]] == "tomorrow"
    assert where[cars["week"]] == "week" and where[cars["month"]] == "month"
    assert where[cars["overdue"]] == "overdue"
    atf_row = next(e for e in d["groups"]["tomorrow"] if e["car_id"] == cars["atf"])
    assert [k["kind"] for k in atf_row["kinds"]] == ["atf"]
    assert d["cars"] >= 6 and d["clients"] >= 1


def test_call_marks_current_cycle_only(sid):
    car = _visit(sid, "01D777AA", oil_in=0)
    assert db.log_call(sid, car, "no_answer")
    e = next(x for x in db.base_due(sid)["groups"]["today"] if x["car_id"] == car)
    assert e["call"]["result"] == "no_answer"
    assert not db.log_call(sid, car, "hacked")          # только известные результаты
    assert not db.log_call(sid + 999, car, "called")   # чужая точка — нельзя


def test_bot_reminder_once_a_day(sid):
    car = _visit(sid, "01D888AA", oil_in=0)
    assert not db.bot_reminded_today(sid, car)
    db.log_call(sid, car, "bot")
    assert db.bot_reminded_today(sid, car)


def _set_call_date(car, days_ago):
    when = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE call_log SET created_at=? WHERE id=(SELECT MAX(id) FROM call_log WHERE car_id=?)", (when, car))
        c.commit()


def test_no_answer_yesterday_goes_to_recall(sid):
    car = _visit(sid, "01D900AA", oil_in=-1)
    with sqlite3.connect(db.DB_PATH) as c:   # визит был давно, звонок — вчера
        c.execute("UPDATE oil_changes SET change_date=? WHERE car_id=?",
                  ((datetime.now() - timedelta(days=95)).strftime("%Y-%m-%d"), car))
        c.commit()
    db.log_call(sid, car, "no_answer")
    assert car not in [e["car_id"] for e in db.base_due(sid)["groups"]["recall"]]   # сегодняшний — ещё нет
    _set_call_date(car, 1)
    assert car in [e["car_id"] for e in db.base_due(sid)["groups"]["recall"]]


def test_booking_with_time_shows_in_tab_and_morning(sid):
    car = _visit(sid, "01D901AA", oil_in=0)
    today = datetime.now().strftime("%Y-%m-%d")
    assert not db.log_call(sid, car, "booked", booked_for="завтра")      # кривая дата — нет
    assert db.log_call(sid, car, "booked", booked_for=today + " 14:30")
    booked = db.base_due(sid)["groups"]["booked"]
    row = next(e for e in booked if e["car_id"] == car)
    assert row["call"]["booked_for"] == today + " 14:30"
    assert any(b["car_id"] == car and b["booked_for"].endswith("14:30") for b in db.bookings_on(sid, today))


def test_long_absent_cars_in_lost(sid):
    car = _visit(sid, "01D902AA", oil_in=-200)
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE oil_changes SET change_date=? WHERE car_id=?",
                  ((datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d"), car))
        c.commit()
    lost = db.base_due(sid)["groups"]["lost"]
    row = next(e for e in lost if e["car_id"] == car)
    assert row["days_since"] >= 299 and row["kinds"] == []


def test_calls_summary_for_evening(sid):
    car = _visit(sid, "01D903AA", oil_in=0)
    db.log_call(sid, car, "called")
    db.log_call(sid, car, "refused")
    s = db.calls_summary(sid, datetime.now().strftime("%Y-%m-%d"))
    assert s["calls"] >= 2 and s["refused"] >= 1
