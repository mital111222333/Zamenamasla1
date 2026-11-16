"""«Статистика»: блок «Сегодня» (выручка по часам против вчера, из чего
выручка, мастера дня) и столбики карточки «Неделя / Месяц / Год»."""
import json
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
    sh = db.create_shop("pulse_head", "Pass12345!", shop_name="Pulse")
    sid = sh["id"] if isinstance(sh, dict) else sh
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    with db.get_conn() as conn:
        emp = []
        for name in ("Akmal", "Bekzod"):
            conn.execute("INSERT INTO shop_users (shop_id, username, password_hash, full_name) VALUES (?, ?, 'x', ?)",
                         (sid, "pu_" + name, name))
            emp.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute("INSERT INTO clients (shop_id, full_name, link_token) VALUES (?, 'C', 'pulsetok')", (sid,))
        cl = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO cars (shop_id, plate_number, client_id) VALUES (?, '01P001PP', ?)", (sid, cl))
        car = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        oil = [{"key": "fluid_0", "name": "Масло", "qty": 4, "total": 300000},
               {"key": "filter_0", "name": "Фильтр", "qty": 1, "total": 50000},
               {"key": "other", "name": "Работа", "qty": 1, "total": 50000}]
        rows = [
            (today, 360000, oil, "08:10:00", emp[0]),   # скидка 40 000 делится по позициям
            (today, 200000, [], "08:40:00", emp[1]),     # старая запись без позиций — масло
            (today, 100000, [{"key": "fluid_0", "total": 100000}], "08:50:00", emp[0]),
            (yday, 250000, oil, "08:05:00", None),
            (yday, 900000, oil, "23:59:00", None),       # вечер вчера — не «к этому часу»
        ]
        for day, cost, items, hm, eid in rows:
            conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, items_json, created_at, master_id) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (car, day, cost, json.dumps(items), f"{day} {hm}", eid))
        conn.commit()
    return {"db": db, "webapp": webapp, "sid": sid, "now": now}


def _login(env, sid=None, employee=False):
    db, webapp = env["db"], env["webapp"]
    shop = db.get_shop(sid or env["sid"])
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"], s["username"], s["is_employee"] = shop["id"], shop.get("role") or "shop", shop["username"], employee
        s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_texts_exist_in_both_languages():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.((?:dp_mix|dp|st_tab|st_wd|st_mon|st_best|st_by)_?[a-z_]*)\b", src))
    keys |= {f"dp_mix_{k}" for k in ("oil", "fluids", "filters", "work", "goods", "tire", "part", "used")}
    keys |= {f"st_tab_{k}" for k in ("week", "month", "year")}
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing
    for k in ("st_wd", "st_wd_full"):
        assert len(i18n.RU[k].split(",")) == 7 and len(i18n.UZ[k].split(",")) == 7
    for k in ("st_mon", "st_mon_full", "st_mon_gen"):
        assert len(i18n.RU[k].split(",")) == 12 and len(i18n.UZ[k].split(",")) == 12


def test_pulse_numbers(env):
    db = env["db"]
    now = env["now"].replace(hour=9, minute=0)
    p = db.stats_pulse(env["sid"], now=now)
    h = p["hours"]
    assert h["from"] == 8 and h["to"] >= 23  # вчерашняя запись в 23:59 расширяет ось
    assert h["today"][-1] == 660000 and h["today"][0] == 660000  # всё сегодня — в 8 часов
    assert h["yesterday"][-1] == 1150000
    assert p["yesterday_same_time"] == 250000  # только то, что было вчера до 9 часов
    mix = {m["k"]: m["v"] for m in p["mix"]}
    assert mix["oil"] == 270000 + 200000 + 100000
    assert mix["filters"] == 45000 and mix["work"] == 45000
    assert sum(mix.values()) == 660000
    ms = {m["name"]: m for m in p["masters"]}
    assert ms["Akmal"]["count"] == 2 and ms["Akmal"]["total"] == 460000
    assert ms["Bekzod"]["total"] == 200000
    s = p["series"]
    assert len(s["week"]["v"]) == 7 and len(s["year"]["v"]) == 12
    assert s["week"]["v"][s["week"]["cur"]] == 660000
    assert s["month"]["v"][s["month"]["cur"]] == 660000


def test_pulse_api_access(env):
    c = _login(env)
    d = c.get("/api/stats/pulse").get_json()
    assert d["ok"] and "series" in d
    txt = json.dumps(d)
    assert "cost_price" not in txt and "profit" not in txt
    # сотруднику статистика закрыта
    e = _login(env, employee=True)
    r = e.get("/api/stats/pulse")
    assert r.status_code in (302, 401, 403) or not (r.get_json() or {}).get("ok")


def test_period_card_replaces_three_cards():
    import panel_template
    src = open(panel_template.__file__, encoding="utf-8").read()
    assert "renderPeriodCard('stPeriodCard')" in src and "renderPeriodCard('netPeriodCard')" in src
    assert "ST_PERIODS().map(([key, label, note]) => renderStatCard" not in src
