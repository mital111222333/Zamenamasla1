"""Наценка: продали дороже обычной цены склада — прибыль выше, «Наценки»
в статистике показывают разницу, склад списывает то же количество."""
import sqlite3
from datetime import datetime

import database as db


def test_markup_counts_in_profit_and_stats():
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as c:
        sid = c.execute("SELECT id FROM shops WHERE role='shop' ORDER BY id LIMIT 1").fetchone()[0]
        cur = c.execute("INSERT INTO products (shop_id, category, name, unit, stock_qty, sell_price, purchase_price, "
                        "is_active) VALUES (?, 'fluid_0', 'MARKUP TEST 5W-30', 'l', 20, 100000, 70000, 1)", (sid,))
        pid = cur.lastrowid
        c.commit()
    cl = db.get_or_create_client(sid, "Наценка", None)
    car = db.create_or_update_car(sid, "01M999MM", cl["id"] if isinstance(cl, dict) else cl, "Chevrolet", "Cobalt")
    car = car["id"] if isinstance(car, dict) else car
    # браузер прислал «обычную цену» 1 сум — сервер всё равно возьмёт её со склада
    item = {"key": "fluid_0", "name": "Моторное масло", "brand": "MARKUP TEST 5W-30", "product_id": pid,
            "unit_price": 120000, "qty": 4, "total": 480000, "list_price": 1}
    db.add_oil_change(car, 60000, "", "", False, 0, 3, items=[item])
    today = datetime.now().strftime("%Y-%m-%d")
    pb = db.get_profit_breakdown(sid, today, today)
    with sqlite3.connect(db.DB_PATH) as c:
        stock = c.execute("SELECT stock_qty FROM products WHERE id=?", (pid,)).fetchone()[0]
    assert stock == 16                                  # списали 4 л, как обычно
    assert pb["markups"] >= 80000                       # 4 л × (120 000 − 100 000)
    assert pb["goods_profit"] >= 200000                 # 4 л × (120 000 − 70 000)
