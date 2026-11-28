"""Тара на складе: «канистра 4 л × 100 шт» → 400 л. В форме склада
(добавить товар / пополнить) и в Excel-шаблоне литры считаются сами."""
import io
import re
import sqlite3

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


def _shop_id():
    import database as db
    with sqlite3.connect(db.DB_PATH) as c:
        return c.execute("SELECT id FROM shops WHERE role='shop' AND is_active=1 ORDER BY id LIMIT 1").fetchone()[0]


def _client(app):
    import database as db
    import webapp
    sid = _shop_id()
    shop = db.get_shop(sid)
    c = app.test_client()
    with c.session_transaction() as s:
        s["shop_id"], s["role"], s["username"], s["is_employee"] = sid, "shop", shop["username"], False
        s["pwf"] = webapp._pw_fingerprint(shop.get("password_hash"))
    return c


def _template(app, lang="ru"):
    from openpyxl import load_workbook
    import database as db
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE shops SET language=? WHERE id=?", (lang, _shop_id()))
    r = _client(app).get("/api/products/import_template")
    assert r.status_code == 200
    return load_workbook(io.BytesIO(r.data))


def test_texts_exist_in_both_languages():
    keys = set(re.findall(r"\bT\.(pk_[a-z_]+)\b", _src())) | {
        "imp_col_pack", "imp_col_packs", "imp_note_pack", "imp_note_packs", "imp_note_qty"}
    assert len(keys) > 8
    missing = [k for k in keys if not i18n.RU.get(k) or not i18n.UZ.get(k)]
    assert not missing, missing


def test_picker_is_wired_into_both_forms():
    src = _src()
    assert 'id="whnew_pk"' in src and 'id="restock_pk"' in src
    assert "packInit('whnew', 'wh_new_stock')" in src
    assert "packInit('restock', 'restock_qty')" in src
    assert "PACK_MAIN = [4, 5]" in src and "PACK_QUICK = [1, 20, 200, 208]" in src


def test_parse_counts_liters_from_canisters():
    import database as db
    import webapp
    rows = db.parse_import_rows([
        {"category": "fluid_0", "name": "A", "pack_size": 4, "packs": 100, "quantity": None},
        {"category": "fluid_0", "name": "B", "pack_size": "5", "packs": "100", "quantity": ""},
        {"category": "fluid_0", "name": "C", "pack_size": "20,5", "packs": 2},
        {"category": "fluid_0", "name": "D", "pack_size": 208, "packs": 2, "quantity": 416},
        {"category": "fluid_0", "name": "E", "quantity": 35},                  # без тары — как раньше
        {"category": "fluid_0", "name": "F", "pack_size": 4, "quantity": 12},  # тара без канистр
        {"category": "fluid_0", "name": "G", "pack_size": "abc", "packs": 3},
    ], webapp._import_category_names())
    q = {r["name"]: r for r in rows}
    assert q["A"]["quantity"] == 400 and q["A"]["packs"] == 100 and q["A"]["pack_size"] == 4
    assert q["B"]["quantity"] == 500
    assert q["C"]["quantity"] == 41
    assert q["D"]["quantity"] == 416
    assert q["E"]["quantity"] == 35 and "packs" not in q["E"]
    assert q["F"]["quantity"] == 12
    assert q["G"]["errors"] == ["quantity"]


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_template_has_canister_columns_and_formula(app, lang):
    import webapp
    T = i18n.TEXTS[lang]
    ws = _template(app, lang).worksheets[0]
    header = [ws.cell(row=1, column=i).value for i in range(1, ws.max_column + 1)]
    assert header[-3:] == [T["imp_col_pack"], T["imp_col_packs"], T["imp_col_qty"]]
    n = len(header)
    f = ws.cell(row=2, column=n).value
    assert f.startswith("=IF(") and "*" in f
    # при загрузке колонки узнаются по заголовкам: тара, канистры, количество
    hdr = [str(h).lower() for h in header]
    colmap = {}
    for field, hints in webapp.IMPORT_HEADER_HINTS.items():
        for idx, h in enumerate(hdr):
            if idx in colmap.values():
                continue
            if any(hint in h for hint in hints):
                colmap[field] = idx
                break
    assert colmap["category"] == 0 and colmap["name"] == 1
    assert colmap["pack_size"] == n - 3 and colmap["packs"] == n - 2 and colmap["quantity"] == n - 1


def test_filled_template_without_excel_recalc_still_counts(app):
    """Файл заполнили, но формулу никто не пересчитал (нет сохранённого
    значения) — сервер сам считает литры из тары и числа канистр."""
    import database as db
    import webapp
    wb = _template(app)
    ws = wb.worksheets[0]
    n = ws.max_column
    ws.cell(row=2, column=1, value="fluid_0")
    ws.cell(row=2, column=2, value="MITANOL TEST")
    ws.cell(row=2, column=n - 2, value=4)
    ws.cell(row=2, column=n - 1, value=100)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    raw, err = webapp._read_import_sheet(buf)
    assert err is None
    rows = db.parse_import_rows(raw, webapp._import_category_names())
    assert len(rows) == 1 and rows[0]["quantity"] == 400 and not rows[0]["errors"]
