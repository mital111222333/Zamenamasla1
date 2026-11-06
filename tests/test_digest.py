"""Ежедневная сводка владельцу: собирается на языке точки, с цифрами дня и
советами; точку, которая давно не работает, не беспокоим."""
import sqlite3
from datetime import datetime, timedelta

import pytest

import database as db
import digest


@pytest.fixture(scope="module")
def shop():
    db.init_db()
    # своя точка: другие тесты пишут замены «сегодня» в общую тестовую точку
    sid = db.create_shop("digest_test_shop", "secret123", shop_name="Test Oil")["id"]
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE shops SET notify_telegram_id='111', shop_name='Test Oil', paid_until=NULL, "
                  "license_type='sub', trial=0 WHERE id=?", (sid,))
        c.commit()
    oil = [{"key": "fluid_0", "name": "Моторное масло", "brand": "MITASU 5W-30", "unit_price": 75000,
            "qty": 4, "total": 300000}]

    def visit(plate, name, cost, days_ago=0, next_in_days=None):
        cid = db.get_or_create_client(sid, name, None)
        cid = cid["id"] if isinstance(cid, dict) else cid
        car = db.create_or_update_car(sid, plate, cid, "Chevrolet", "Cobalt")
        car = car["id"] if isinstance(car, dict) else car
        db.add_oil_change(car, 50000, "Замена масла", "MITASU", False, cost, 3, items=oil,
                          cash_amount=cost, card_amount=0)
        day = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        with sqlite3.connect(db.DB_PATH) as c:
            oc = c.execute("SELECT MAX(id) FROM oil_changes WHERE car_id=?", (car,)).fetchone()[0]
            c.execute("UPDATE oil_changes SET change_date=? WHERE id=?", (day, oc))
            if next_in_days is not None:
                nd = (datetime.now() + timedelta(days=next_in_days)).strftime("%Y-%m-%d")
                c.execute("UPDATE oil_changes SET next_change_date=? WHERE id=?", (nd, oc))
            c.commit()

    visit("01A111AA", "Алишер", 300000)
    visit("01A222BB", "Бекзод", 300000)
    for i in range(4):
        visit(f"01B33{i}CC", f"Клиент {i}", 300000, days_ago=7)
    visit("01C444DD", "Жасур", 280000, days_ago=90, next_in_days=0)   # сегодня пора на замену
    return db.get_shop(sid)


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_evening_digest(shop, lang):
    s = dict(shop, language=lang)
    text = digest.build(s, "evening")
    assert text and "Test Oil" in text
    assert "600 000" in text                        # выручка за день: 2 × 300 000
    assert "▼ −50%" in text                         # к тому же дню прошлой недели (1 200 000)
    assert ("Советы" in text) if lang == "ru" else ("Maslahatlar" in text)
    print("\n" + text)


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_morning_digest(shop, lang):
    s = dict(shop, language=lang)
    text = digest.build(s, "morning")
    assert text and "01C444DD" in text              # машина, которой сегодня пора на замену
    assert ("Задача на сегодня" in text) if lang == "ru" else ("Bugungi vazifa" in text)
    print("\n" + text)


def test_quiet_shop_gets_nothing(shop):
    later = datetime.now() + timedelta(days=digest.QUIET_DAYS + 2)
    assert digest.build(shop, "evening", now=later) is None


def test_digest_off_toggle(shop):
    assert any(s["id"] == shop["id"] for s in db.digest_shops())
    db.set_digest_off(shop["id"], True)
    assert not any(s["id"] == shop["id"] for s in db.digest_shops())
    db.set_digest_off(shop["id"], False)
    assert any(s["id"] == shop["id"] for s in db.digest_shops())
