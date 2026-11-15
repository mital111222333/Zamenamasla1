"""Работа без интернета: замена из очереди телефона приходит на сервер позже.
Она должна: попасть в тот же аккаунт, где её вносили; получить дату и время
внесения (а не отправки); не задвоиться при повторной отправке."""
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
    head = db.create_shop("off_head", "Pass12345!", shop_name="Off Head")
    hid = head["id"]
    db.create_shop_employee(hid, "off_emp", "Pass12345!", full_name="Usta")
    return {"db": db, "webapp": webapp, "hid": hid}


def _login(env, employee=False):
    db, webapp = env["db"], env["webapp"]
    shop = db.get_shop(env["hid"])
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"] = env["hid"], "shop"
        if employee:
            full = db.get_active_employee("off_emp", env["hid"])
            s["username"], s["is_employee"] = "off_emp", True
            s["pwf"] = webapp._pw_fingerprint(full.get("password_hash"))
        else:
            s["username"], s["is_employee"] = shop["username"], False
            s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def _payload(plate, token, **kw):
    p = {"plate": plate, "owner_name": "Ali", "mileage": 100000, "next_mileage": 108000,
         "interval_value": 3, "interval_unit": "months", "cash_amount": 200000, "token": token,
         "items": [{"key": "fluid_0", "name": "Масло", "brand": "X 5W30", "unit_price": 50000, "qty": 4,
                    "total": 200000}]}
    p.update(kw)
    return p


def _rows(db, hid, plate):
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT oc.* FROM oil_changes oc JOIN cars c ON c.id=oc.car_id WHERE c.shop_id=? AND c.plate_number=?",
            (hid, plate)).fetchall()]


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(off_[a-z_]+)\b", src))
    keys |= {"off_err_owner"}
    assert len(keys) > 15
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_panel_marked_for_phone_copy(env):
    r = _login(env).get("/")
    assert r.status_code == 200 and r.headers.get("X-OB-Panel") == "1"
    html = r.get_data(as_text=True)
    assert 'id="obPill"' in html and "ob_outbox_" in html


def test_offline_entry_gets_entry_time_and_no_duplicate(env):
    db, hid = env["db"], env["hid"]
    c = _login(env)
    owner = f"{hid}_off_head"
    when = (datetime.now() - timedelta(days=1)).replace(hour=18, minute=5, second=0, microsecond=0)
    p = _payload("01O111OO", "tok-off-1", offline_owner=owner, offline_at=when.strftime("%Y-%m-%d %H:%M:%S"))
    r = c.post("/api/add", json=p).get_json()
    assert r["ok"] and not r.get("duplicate")
    again = c.post("/api/add", json=p).get_json()
    assert again["ok"] and again["duplicate"]
    rows = _rows(db, hid, "01O111OO")
    assert len(rows) == 1
    row = rows[0]
    assert row["change_date"] == when.strftime("%Y-%m-%d")
    assert str(row["created_at"]).startswith(when.strftime("%Y-%m-%d 18:05"))
    assert row["offline_saved"] == 1
    # напоминание считается от дня замены, а не от дня отправки
    from dateutil.relativedelta import relativedelta
    assert row["next_change_date"] == (when + relativedelta(months=3)).strftime("%Y-%m-%d")
    # деньги — во вчерашней кассе
    dc = c.get("/api/day_close?day=" + when.strftime("%Y-%m-%d")).get_json()
    assert dc["totals"]["cash"] >= 200000


def test_wrong_account_is_refused(env):
    db, hid = env["db"], env["hid"]
    c = _login(env)
    r = c.post("/api/add", json=_payload("01O222OO", "tok-off-2", offline_owner="999_other",
                                         offline_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    assert r.status_code == 409 and r.get_json()["wrong_owner"]
    assert _rows(db, hid, "01O222OO") == []
    # сотрудник той же точки — другой аккаунт (своя касса)
    e = _login(env, employee=True)
    assert e.post("/api/add", json=_payload("01O222OO", "tok-off-3", offline_owner=f"{hid}_off_head")).status_code == 409
    assert e.post("/api/add", json=_payload("01O222OO", "tok-off-3", offline_owner=f"{hid}_off_emp")).get_json()["ok"]


def test_bad_phone_clock_is_ignored(env):
    db, hid = env["db"], env["hid"]
    c = _login(env)
    owner = f"{hid}_off_head"
    today = datetime.now().strftime("%Y-%m-%d")
    for plate, at in (("01O333OO", (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")),
                      ("01O444OO", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")),
                      ("01O555OO", "kecha")):
        assert c.post("/api/add", json=_payload(plate, "t-" + plate, offline_owner=owner, offline_at=at)).get_json()["ok"]
        assert _rows(db, hid, plate)[0]["change_date"] == today


def test_parse_offline_at():
    import database as db
    now = datetime(2026, 11, 15, 12, 0, 0)
    assert db.parse_offline_at("2026-11-14 09:30:00", now) == datetime(2026, 11, 14, 9, 30)
    assert db.parse_offline_at("2026-11-15T12:05:00", now) == now  # чуть впереди — не позже «сейчас»
    assert db.parse_offline_at("2026-11-01 09:30:00", now) is None
    assert db.parse_offline_at("", now) is None


def test_service_worker_keeps_panel_copy():
    import os
    sw = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "sw.js"),
              encoding="utf-8").read()
    assert "X-OB-Panel" in sw and "PANEL_CACHE" in sw and "/logout" in sw
