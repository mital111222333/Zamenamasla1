"""«Машина готова» и живая очередь: доска мастера, ссылка клиента, табло."""
import re

import pytest

import i18n


@pytest.fixture(scope="module")
def env():
    import database as db
    db.init_db()
    import webapp
    import queue_routes
    webapp.app.config["TESTING"] = True
    sent = []
    queue_routes._tg_bg = lambda chat, text: sent.append((chat, text))
    sh = db.create_shop("q_head", "Pass12345!", shop_name="Q Shop")
    sid = sh["id"] if isinstance(sh, dict) else sh
    other = db.create_shop("q_other", "Pass12345!", shop_name="Other")
    oid = other["id"] if isinstance(other, dict) else other
    with db.get_conn() as conn:
        conn.execute("INSERT INTO clients (shop_id, full_name, phone, telegram_id, link_token) "
                     "VALUES (?, 'Ali Valiyev', '+998901112233', 555, 'qtok1')", (sid,))
        cl = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO cars (shop_id, plate_number, client_id, car_brand, car_model) "
                     "VALUES (?, '01A111AA', ?, 'Chevrolet', 'Cobalt')", (sid, cl))
        conn.commit()
    db.create_shop_employee(sid, "q_emp", "Pass12345!", full_name="Usta")
    return {"db": db, "webapp": webapp, "sid": sid, "oid": oid, "sent": sent}


def _login(env, employee=False, shop_key="sid"):
    db, webapp = env["db"], env["webapp"]
    sid = env[shop_key]
    shop = db.get_shop(sid)
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"] = sid, "shop"
        if employee:
            full = db.get_active_employee("q_emp", sid)
            s["username"], s["is_employee"] = "q_emp", True
            s["pwf"] = webapp._pw_fingerprint(full.get("password_hash"))
        else:
            s["username"], s["is_employee"] = shop["username"], False
            s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def test_texts_exist_in_both_languages():
    import panel_template
    import display
    import queue_routes
    src = open(panel_template.__file__, encoding="utf-8").read() + open(display.__file__, encoding="utf-8").read() \
        + open(queue_routes.__file__, encoding="utf-8").read()
    keys = set(re.findall(r"\bT\.(q_[a-z_]+|tab_queue)\b", src)) | set(re.findall(r'T\["(q_[a-z_]+)"\]', src))
    assert len(keys) > 30
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_queue_flow_with_telegram_client(env):
    c = _login(env)
    r = c.post("/api/queue", json={"plate": "01a 111 aa", "what": "Масло"}).get_json()
    assert r["ok"]
    it = r["item"]
    assert it["plate"] == "01A111AA" and it["owner_name"] == "Ali Valiyev" and it["car_label"] == "Chevrolet Cobalt"
    assert it["position"] == 1 and it["has_tg"] and r["item"]["tg_sent"]
    assert "telegram_id" not in it and "token" not in it
    assert env["sent"][-1][0] == 555 and "/q/" in env["sent"][-1][1]
    # повтор того же номера — та же запись, второе сообщение не уходит
    n = len(env["sent"])
    assert c.post("/api/queue", json={"plate": "01A111AA"}).get_json()["item"]["duplicate"]
    assert len(env["sent"]) == n

    c.post("/api/queue", json={"plate": "40B222BB"})
    items = c.get("/api/queue").get_json()["items"]
    assert [(i["plate"], i.get("position")) for i in items] == [("01A111AA", 1), ("40B222BB", 2)]

    assert c.post(f"/api/queue/{it['id']}", json={"status": "work"}).get_json()["ok"]
    done = c.post(f"/api/queue/{it['id']}", json={"status": "done"}).get_json()["item"]
    assert done["tg_sent"] and "готова" in env["sent"][-1][1]
    # второе «Готово» — сообщение не повторяется
    n = len(env["sent"])
    assert not c.post(f"/api/queue/{it['id']}", json={"status": "done"}).get_json()["item"]["tg_sent"]
    assert len(env["sent"]) == n


def test_client_page_shows_only_own_car(env):
    db = env["db"]
    c = _login(env)
    it = c.post("/api/queue", json={"plate": "10C333CC"}).get_json()["item"]
    token = it["link"].rsplit("/", 1)[1]
    anon = env["webapp"].app.test_client()
    page = anon.get(f"/q/{token}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "10C333CC" in html and "Q Shop" in html
    assert "40B222BB" not in html and "Ali" not in html
    st = anon.get(f"/api/q/{token}").get_json()
    assert st["ok"] and st["status"] == "wait" and st["position"] >= 1 and "shop_id" not in st
    assert anon.get("/q/nope-token").status_code == 404
    db.queue_set_status(env["sid"], it["id"], "done")
    assert anon.get(f"/api/q/{token}").get_json()["status"] == "done"


def test_display_queue_has_plates_only(env):
    db = env["db"]
    shop = db.get_shop(env["sid"])
    anon = env["webapp"].app.test_client()
    d = anon.get(f"/api/display_queue/{shop['anpr_token']}").get_json()
    assert d["items"] and set(d["items"][0]) == {"plate", "status", "position", "eta_min"}
    assert anon.get("/api/display_queue/wrong").get_json() == {"items": []}
    html = anon.get(f"/display/{shop['anpr_token']}").get_data(as_text=True)
    assert "/api/display_queue/" in html


def test_other_shop_cannot_touch_queue(env):
    c = _login(env)
    qid = c.get("/api/queue").get_json()["items"][0]["id"]
    o = _login(env, shop_key="oid")
    assert o.get("/api/queue").get_json()["items"] == []
    assert o.post(f"/api/queue/{qid}", json={"status": "gone"}).status_code == 404
    assert o.delete(f"/api/queue/{qid}").status_code == 404


def test_employee_uses_queue_without_display_link(env):
    e = _login(env, employee=True)
    r = e.post("/api/queue", json={"plate": "01E555EE"}).get_json()
    assert r["ok"]
    lst = e.get("/api/queue").get_json()
    assert "display_url" not in lst
    assert "display_url" in _login(env).get("/api/queue").get_json()
    assert e.delete(f"/api/queue/{r['item']['id']}").get_json()["ok"]


def test_bad_input(env):
    c = _login(env)
    assert c.post("/api/queue", json={"plate": "  "}).status_code == 400
    qid = c.get("/api/queue").get_json()["items"][0]["id"]
    assert c.post(f"/api/queue/{qid}", json={"status": "hacked"}).status_code == 400


def test_eta_uses_parallel_lanes():
    import database as db
    rows = [{"id": 1, "status": "work", "started_at": None}, {"id": 2, "status": "work", "started_at": None},
            {"id": 3, "status": "wait"}, {"id": 4, "status": "wait"}, {"id": 5, "status": "wait"}]
    db._queue_positions(rows, 20)
    assert [r.get("position") for r in rows[2:]] == [1, 2, 3]
    # два мастера: первые двое ждущих — через ~40, третий — через ~60
    assert [r["eta_min"] for r in rows[2:]] == [40, 40, 60]
