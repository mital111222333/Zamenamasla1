"""«Все машины клиента»: в карточке видны другие машины владельца — свои и
с других точек OilBook (по телефону), срочные сверху, без денег и телефонов."""
import sqlite3
from datetime import datetime, timedelta

import pytest

import i18n

KEYS = ["kc_cars_title", "kc_cars_hint", "kc_cars_now", "kc_cars_other", "kc_cars_due",
        "kc_cars_soon", "kc_cars_none", "kc_cars_days"]


@pytest.mark.parametrize("key", KEYS)
def test_texts_exist_in_both_languages(key):
    assert i18n.RU.get(key) and i18n.UZ.get(key), key


def test_panel_renders_owner_cars():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    assert "function renderOwnerCars" in src and "renderOwnerCars(data.owner_cars)" in src
    assert "function pickOwnerCar" in src


def _shops():
    import database as db
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as c:
        ids = [r[0] for r in c.execute("SELECT id FROM shops WHERE role='shop' ORDER BY id LIMIT 2")]
    if len(ids) < 2:
        pytest.skip("нужны две точки в тестовой базе")
    return ids


def _car(db, shop, name, phone, plate, model, km, next_km, days_ago):
    cl = db.get_or_create_client(shop, name, phone)
    cl = cl["id"] if isinstance(cl, dict) else cl
    car = db.create_or_update_car(shop, plate, cl, "Chevrolet", model)
    car = car["id"] if isinstance(car, dict) else car
    db.add_oil_change(car, km, "", "", False, 0, 3, next_mileage=next_km)
    day = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE oil_changes SET change_date=?, next_change_date=? WHERE car_id=?",
                  (day, (datetime.now() + timedelta(days=90 - days_ago)).strftime("%Y-%m-%d"), car))
    return car


def test_owner_cars_own_and_other_shop_without_money():
    import database as db
    s1, s2 = _shops()
    phone = "+998935550123"
    _car(db, s1, "Равшан", phone, "01A777AA", "Cobalt", 80000, 85000, 5)
    _car(db, s1, "Равшан", phone, "01B123BA", "Nexia", 50000, 55000, 120)
    _car(db, s2, "Равшан", "93 555-01-23", "01K555KA", "Malibu", 20000, 30000, 10)
    cars = db.get_owner_cars(s1, "01A777AA")
    plates = [c["plate"] for c in cars]
    assert set(plates) == {"01A777AA", "01B123BA", "01K555KA"}
    assert sum(1 for c in cars if c["current"]) == 1
    other = next(c for c in cars if c["plate"] == "01K555KA")
    assert other["shop"] and next(c for c in cars if c["plate"] == "01B123BA")["shop"] is None
    # срочные — сверху: Nexia давно просрочена по сроку/пробегу, Malibu с запасом
    assert plates.index("01B123BA") < plates.index("01K555KA")
    for c in cars:
        assert not ({"cost", "phone", "owner_phone", "items_json", "cost_price"} & set(c))


def test_owner_cars_short_phone_does_not_match_other_shops():
    import database as db
    s1, s2 = _shops()
    _car(db, s1, "Без телефона", "123", "01X111XX", "Gentra", 1000, 6000, 1)
    _car(db, s2, "Другой", "123", "01Y222YY", "Spark", 1000, 6000, 1)
    assert [c["plate"] for c in db.get_owner_cars(s1, "01X111XX")] == ["01X111XX"]


def test_unknown_plate_gives_empty_list():
    import database as db
    s1, _ = _shops()
    assert db.get_owner_cars(s1, "00NOPE00") == []
