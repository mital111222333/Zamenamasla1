"""Редизайн в стиле Apple и исправления расчётов, найденные по пути."""
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
    sh = db.create_shop("apple_head", "Pass12345!", shop_name="Apple")
    sid = sh["id"] if isinstance(sh, dict) else sh
    return {"db": db, "webapp": webapp, "sid": sid}


def _car(db, sid, plate):
    with db.get_conn() as conn:
        conn.execute("INSERT INTO clients (shop_id, full_name, link_token) VALUES (?, 'C', ?)", (sid, "tok" + plate))
        cl = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO cars (shop_id, plate_number, client_id) VALUES (?, ?, ?)", (sid, plate, cl))
        car = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    return car


def _visit(db, car, day, cost, created, service_type=None):
    with db.get_conn() as conn:
        conn.execute("INSERT INTO oil_changes (car_id, change_date, cost, created_at, service_type) VALUES (?, ?, ?, ?, ?)",
                     (car, day, cost, created, service_type))
        conn.commit()


def _login(env):
    db, webapp = env["db"], env["webapp"]
    shop = db.get_shop(env["sid"])
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"], s["username"], s["is_employee"] = shop["id"], "shop", shop["username"], False
        s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_panel_has_apple_theme_and_grouped_more_sheet(env):
    html = _login(env).get("/").get_data(as_text=True)
    assert "/ui/apple.css?v=" in html and "/ui/apple.js?v=" in html
    assert "d.classList.add('ap')" in html  # тема ставится до отрисовки
    # «Ещё» на телефоне — группами, как «Настройки» iPhone
    sheet = html[html.index('id="moreSheet"'):html.index('<div class="container">')]
    assert sheet.count('class="more-group"') >= 5
    assert 'class="mi-ic' in sheet and 'class="more-gh"' in sheet


def test_apple_assets_served(env):
    c = env["webapp"].app.test_client()
    css = c.get("/ui/apple.css").get_data(as_text=True)
    assert "html.ap" in css and "#007AFF" in css.upper()
    # авто-слой: заглавные и курсив убраны, серые Tailwind → серые Apple
    assert "text-transform:none" in css and "#f2f2f7" in css.lower()
    assert c.get("/ui/apple.js").status_code == 200


def test_group_titles_in_both_languages():
    for k in ("nav_grp_work", "nav_grp_business", "nav_grp_clients", "nav_grp_team", "nav_grp_help", "nav_grp_app"):
        assert i18n.RU.get(k) and i18n.UZ.get(k), k


def test_slate_grays_are_not_mistaken_for_blue():
    import apple_theme as ap
    assert ap.map_decl("color", "#64748B") == "#6e6e73"
    assert ap.map_decl("color", "#0F52BA") == "#007aff"
    assert ap.map_decl("background", "#F1F5F9") == "#f2f2f7"
    assert ap.map_decl("text-transform", "uppercase", ".x", "type") == "none"
    assert ap.map_decl("text-transform", "uppercase", "#plate", "type") is None  # госномер — заглавными


def test_avg_check_ignores_used_oil_sales(env):
    db = env["db"]
    sid = env["sid"]
    car = _car(db, sid, "01A001AA")
    day = "2026-03-10"
    _visit(db, car, day, 100000, day + " 09:00:00")
    _visit(db, car, day, 200000, day + " 10:00:00")
    _visit(db, car, day, 600000, day + " 11:00:00", service_type="used_oil")  # продали отработку
    r = db.get_revenue_range(sid, day, day)
    assert r["total"] == 900000            # выручка — вся
    assert r["paid_count"] == 2
    assert r["avg"] == 150000              # раньше было 450 000


def test_week_comparison_cuts_last_day_at_current_time(env):
    db = env["db"]
    sid = db.create_shop("apple_cmp", "Pass12345!", shop_name="Cmp")["id"]
    car = _car(db, sid, "01A002AA")
    now = datetime.now()
    if now.hour == 23 and now.minute >= 58:
        pytest.skip("слишком близко к полуночи")
    prev = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    _visit(db, car, prev, 100000, prev + " 00:00:01")      # до этого времени неделю назад — считается
    _visit(db, car, prev, 900000, prev + " 23:59:59")      # позже текущего времени — не считается
    cmp = db.get_revenue_comparison(sid)["week"]
    assert cmp["previous"] == 100000


def test_login_error_text_is_not_html(env):
    html = env["webapp"].app.test_client().get("/login").get_data(as_text=True)
    assert "msg.innerHTML = `<div class=\"error\">${data.error}" not in html
    assert re.search(r"d\.textContent = text", html)
