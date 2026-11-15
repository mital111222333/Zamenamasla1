"""Раздел «Цена»: быстро назвать клиенту цену товара и всей замены.
Экран работает на уже существующих данных и не показывает закупку."""
import re

import pytest

import i18n


@pytest.fixture(scope="module")
def app():
    import database as db
    db.init_db()
    import webapp
    webapp.app.config["TESTING"] = True
    return webapp.app


def _src():
    import panel_template
    return open(panel_template.__file__, encoding="utf-8").read()


def test_texts_exist_in_both_languages():
    keys = sorted(set(re.findall(r"\bT\.(pr_[a-z_]+|tab_price)\b", _src())))
    assert len(keys) > 20
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_section_is_wired_into_navigation():
    src = _src()
    assert 'id="view-price"' in src and 'id="tab-price"' in src
    assert """data-tab="price" onclick="showTab('price')\"""" in src
    assert "if (t === 'price') prOpen();" in src
    # кнопка стоит в нижней панели сразу после «Базы»
    bar = src[src.index('id="bottomBar"'):src.index('id="bbMore"')]
    assert bar.index('data-tab="table"') < bar.index('data-tab="price"') < bar.index('data-tab="add"')


def test_price_screen_never_shows_purchase_price():
    src = _src()
    js = src[src.index("// ===== «Цена»"):src.index("// «Готовые наборы»: частые сочетания")]
    assert "purchase" not in js and "cost_price" not in js


def test_page_renders_for_logged_in_shop(app):
    import sqlite3
    import database as db
    import webapp
    with sqlite3.connect(db.DB_PATH) as c:
        sid = c.execute("SELECT id FROM shops WHERE role='shop' AND is_active=1 ORDER BY id LIMIT 1").fetchone()[0]
    shop = db.get_shop(sid)
    c = app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"], s["username"], s["is_employee"] = sid, "shop", shop["username"], False
        s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    r = c.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="view-price"' in html and "function prOpen" in html
