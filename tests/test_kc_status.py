"""Карточка постоянного клиента: моторное масло и масло коробки показаны
отдельно (на каком пробеге и до какой даты менять), а в окне АКПП видна
плановая замена прошлого раза."""
import pytest

import i18n

KEYS = ["kc_st_last_visit", "kc_st_due_km", "kc_st_due_date", "kc_st_done", "kc_st_left", "kc_st_over",
        "kc_st_date_over", "kc_st_no_plan", "kc_st_never", "bot_booked_notify"]


@pytest.mark.parametrize("key", KEYS)
def test_texts_exist_in_both_languages(key):
    assert i18n.RU.get(key) and i18n.UZ.get(key), key


def test_panel_has_status_block_and_atf_hint():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    assert 'id="kcStatus"' in src and 'id="atfCompare"' in src
    assert "function kcBuildStatus" in src and "last.atf_next_mileage" in src


def test_booking_notice_uses_shop_language():
    text = i18n.t("bot_booked_notify", "uz", plate="60A123BA", owner="Aziz")
    assert "60A123BA" in text and "Aziz" in text and "Клиент" not in text


def test_atf_plan_survives_engine_oil_only_visit():
    """Плановый пробег коробки переносится в следующий визит, где меняли
    только моторное масло — карточка берёт его из последней записи."""
    import sqlite3
    import database as db
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as c:
        sid = c.execute("SELECT id FROM shops WHERE role='shop' ORDER BY id LIMIT 1").fetchone()[0]
    oil = {"key": "fluid_0", "name": "Моторное масло", "brand": "M", "unit_price": 80000, "qty": 4, "total": 320000}
    atf = {"key": "fluid_1", "name": "АКПП", "brand": "A", "unit_price": 90000, "qty": 4, "total": 360000}
    cl = db.get_or_create_client(sid, "Клиент АКПП", "+998907770011")
    car = db.create_or_update_car(sid, "01K555AT", cl["id"] if isinstance(cl, dict) else cl, "Chevrolet", "Cobalt")
    car = car["id"] if isinstance(car, dict) else car
    db.add_oil_change(car, 45000, "", "", False, 0, 3, next_mileage=53000, items=[oil, atf],
                      atf={"interval_value": 24, "next_mileage": 85000})
    db.add_oil_change(car, 53200, "", "", False, 0, 3, next_mileage=61200, items=[oil])
    _car, history = db.get_car_history(sid, "01K555AT")
    assert history[0]["mileage"] == 53200
    assert history[0]["atf_next_mileage"] == 85000 and history[0]["atf_next_date"]
    assert history[0]["next_mileage"] == 61200
