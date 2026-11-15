"""«Мой гараж» (вариант «Кошелёк»), живое напоминание и новый паспорт авто:
паспорт собирает историю по госномеру со всех точек, «записаться» из
мини-приложения работает только для своей машины, «через неделю» не
увеличивает счётчик напоминаний."""
import hashlib
import hmac
import json
import sqlite3
import time
import urllib.parse
from datetime import datetime, timedelta

import pytest

import database as db

OIL = {"key": "fluid_0", "name": "Моторное масло", "brand": "MITANOL 5W-30", "unit_price": 80000, "qty": 4,
       "total": 320000, "cost_price": 60000}
TG_OWNER = 777000111
TG_OTHER = 777000222


def _q(sql, *a):
    with sqlite3.connect(db.DB_PATH) as c:
        c.row_factory = sqlite3.Row
        r = c.execute(sql, a)
        c.commit()
        return [dict(x) for x in r.fetchall()]


def _shop(name):
    db.create_shop("u_" + name, "pass12345", name)
    return _q("SELECT id FROM shops WHERE username=?", "u_" + name)[0]["id"]


def _car(shop_id, plate, tg=None):
    cl = db.get_or_create_client(shop_id, "Жасур", "+998901112233")
    cl = cl["id"] if isinstance(cl, dict) else cl
    if tg:
        _q("UPDATE clients SET telegram_id=? WHERE id=?", tg, cl)
    car = db.create_or_update_car(shop_id, plate, cl, "Chevrolet", "Cobalt")
    return car["id"] if isinstance(car, dict) else car


def _last(car_id):
    return _q("SELECT * FROM oil_changes WHERE car_id=? ORDER BY id DESC LIMIT 1", car_id)[0]


@pytest.fixture(scope="module")
def world():
    db.init_db()
    a, b = _shop("Garage A"), _shop("Garage B")
    car_a = _car(a, "01G777AA", TG_OWNER)
    db.add_oil_change(car_a, 70000, "", "", True, 0, 3, items=[OIL], next_mileage=78000)
    old = _last(car_a)
    d0 = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    _q("UPDATE oil_changes SET change_date=?, next_change_date=? WHERE id=?",
       d0, (datetime.now() - timedelta(days=110)).strftime("%Y-%m-%d"), old["id"])
    car_b = _car(b, "01G777AA")          # та же машина в другой точке
    db.add_oil_change(car_b, 77500, "", "", True, 0, 3, items=[OIL], next_mileage=85500)
    token = _q("SELECT passport_token FROM cars WHERE id=?", car_a)[0]["passport_token"]
    return {"a": a, "b": b, "car_a": car_a, "car_b": car_b, "token": token}


def test_passport_has_history_from_all_shops_with_prices(world):
    car, history, stats = db.passport_full(world["token"])
    assert car["plate_number"] == "01G777AA"
    assert {h["shop_name"] for h in history} == {"Garage A", "Garage B"}
    assert stats["count"] == 2 and stats["km_ok"] is True and stats["last_km"] == 77500
    assert stats["on_time"] == 100                       # 77 500 ≤ 78 000 км
    flat = json.dumps(history, ensure_ascii=False)
    assert "320000" in flat                              # что платил владелец — видно
    assert "cost_price" not in flat and "60000" not in flat   # закупка точки — никогда


def test_passport_page_renders_full_plate_and_prices(world):
    import webapp
    c = webapp.app.test_client()
    r = c.get(f"/passport/{world['token']}")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "01G777AA" in body and "320 000" in body and "Garage B" in body
    r = c.get(f"/passport/{world['token']}?lang=uz")
    assert "Servis pasporti" in r.get_data(as_text=True)
    assert c.get("/passport/nope").status_code == 404


def test_reminder_card_and_snooze(world):
    last = _last(world["car_b"])
    today = datetime.now().strftime("%Y-%m-%d")
    d90 = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    _q("UPDATE oil_changes SET change_date=?, next_change_date=? WHERE id=?", d90, today, last["id"])
    item = next(x for x in db.get_due_reminders() if x["id"] == last["id"])
    assert item["car_brand"] == "Chevrolet"
    card = db.reminder_card(item)
    assert card["ratio"] is not None and card["ratio"] >= 1
    assert "MITANOL" in card["oil"] and "4" in card["oil"]
    db.mark_reminder_sent(last["id"])
    db.snooze_reminder(last["id"], "o", days=7)
    row = _last(world["car_b"])
    assert row["reminder_count"] == 1                    # счётчик не вырос
    assert not [x for x in db.get_due_reminders() if x["id"] == last["id"]]
    # через неделю — снова в списке
    shifted = (datetime.now() - timedelta(days=db.FOLLOWUP_INTERVAL_DAYS)).strftime("%Y-%m-%d")
    _q("UPDATE oil_changes SET last_reminder_date=? WHERE id=?", shifted, last["id"])
    assert [x for x in db.get_due_reminders() if x["id"] == last["id"]]


def test_reminder_text_has_card():
    import bot
    item = {"plate_number": "01G777AA", "car_brand": "Chevrolet", "car_model": "Cobalt",
            "change_date": (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
            "next_change_date": datetime.now().strftime("%Y-%m-%d"), "mileage": 77500,
            "items_json": json.dumps([OIL])}
    text = bot.reminder_card_text(item, "ru")
    assert "Chevrolet Cobalt · 01G777AA" in text and "▰" in text and "77 500" in text


def _init_data(tg_id):
    import webapp
    user = json.dumps({"id": tg_id, "first_name": "Test"})
    data = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", webapp.BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(data)


def test_miniapp_book_only_own_car(world, monkeypatch):
    import webapp
    sent = []
    monkeypatch.setattr(webapp, "_send_telegram_message", lambda chat, text: sent.append(text) or True)
    _q("UPDATE shops SET notify_telegram_id='5550001' WHERE id=?", world["a"])
    c = webapp.app.test_client()
    r = c.post("/api/m/book", json={"plate": "01G777AA"}, headers={"X-Telegram-Init-Data": _init_data(TG_OTHER)})
    assert r.status_code == 404 and not sent
    r = c.post("/api/m/book", json={"plate": "01g 777 aa"}, headers={"X-Telegram-Init-Data": _init_data(TG_OWNER)})
    assert r.status_code == 200 and r.get_json()["shop"] == "Garage A"
    assert _last(world["car_a"])["status"] == "booked" and sent and "01G777AA" in sent[0]
    assert c.post("/api/m/book", json={"plate": "01G777AA"}).status_code == 401


def test_miniapp_page_and_garage(world):
    import webapp
    c = webapp.app.test_client()
    page = c.get("/m?car=01G777AA").get_data(as_text=True)
    assert "wallet" in page and "Mening garajim" in page
    g = c.get("/api/m/garage", headers={"X-Telegram-Init-Data": _init_data(TG_OWNER)}).get_json()
    assert g["ok"] and g["cars"][0]["plate"] == "01G777AA"


def test_widget_html_fits_limits():
    import widgets
    assert widgets.html_fits("ru") and widgets.html_fits("uz")


def test_widget_query_reaches_handler(world, monkeypatch):
    """PTB 21 не знает widget_query — он должен лежать в api_kwargs, а
    нажатие «через неделю» — выполняться только для своего клиента."""
    import asyncio
    from telegram import Bot, Update
    import bot
    import widgets
    calls = []
    monkeypatch.setattr(widgets, "_call", lambda token, method, payload: calls.append((method, payload)) or (True, {}))
    oc = _last(world["car_a"])
    raw = {"update_id": 1, "widget_query": {"id": "q1", "from": {"id": TG_OTHER}, "chat": {"id": TG_OTHER},
                                             "message_id": 5, "data": f"snooze:{oc['id']}:o", "type": {"type": "data"}}}
    upd = Update.de_json(raw, Bot("123456:TEST"))
    assert upd.api_kwargs["widget_query"]["id"] == "q1"
    asyncio.run(bot.widget_query_handler(upd, None))
    assert [m for m, _ in calls] == ["answerWidgetQuery"]          # чужой — только ответ
    calls.clear()
    raw["widget_query"]["from"]["id"] = TG_OWNER
    raw["widget_query"]["chat"]["id"] = TG_OWNER
    before = _last(world["car_a"])["reminder_count"]
    asyncio.run(bot.widget_query_handler(Update.de_json(raw, Bot("123456:TEST")), None))
    assert [m for m, _ in calls] == ["answerWidgetQuery", "editMessageWidgetData"]
    assert json.loads(calls[1][1]["chat_data"])["st"] == "snooze"
    after = _last(world["car_a"])
    assert after["last_reminder_date"] and after["reminder_count"] >= max(1, before or 0)
