"""Аудит, круг 2: рассылки, удаление филиала, дата платежа по долгу."""
import os
import re
import sqlite3

import pytest

import database as db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def head_id():
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as c:
        return c.execute("SELECT id FROM shops WHERE role='shop' ORDER BY id LIMIT 1").fetchone()[0]


def test_broadcast_one_in_queue_and_daily_limit(head_id):
    assert db.broadcast_allowed(head_id)
    b1 = db.create_broadcast(head_id, "акция")
    assert not db.broadcast_allowed(head_id)  # прежняя ещё в очереди
    db.mark_broadcast_done(b1, 1, 0)
    for _ in range(db.BROADCAST_PER_DAY - 1):
        assert db.broadcast_allowed(head_id)
        db.mark_broadcast_done(db.create_broadcast(head_id, "ещё"), 1, 0)
    assert not db.broadcast_allowed(head_id)  # лимит за сутки


def test_branch_delete_removes_all_branch_rows(head_id):
    br = db.create_branch_shop(head_id, "branch_audit2", "secret123", shop_name="Филиал")
    bid = br["id"] if isinstance(br, dict) and "id" in br else br["shop"]["id"]
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("INSERT INTO suppliers (shop_id, name) VALUES (?, 'Поставщик')", (bid,))
        c.execute("INSERT INTO usd_rate_history (shop_id, rate, set_at) VALUES (?, 12500, '2026-01-01')", (bid,))
        c.commit()
    db.log_action(bid, "branch_audit2", False, "delete_car", {"plate": "01A123BC"})
    assert db.delete_branch_with_data(bid)
    with sqlite3.connect(db.DB_PATH) as c:
        tables = [t for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        left = {}
        for t in tables:
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
            if "shop_id" in cols:
                n = c.execute(f"SELECT COUNT(*) FROM {t} WHERE shop_id=?", (bid,)).fetchone()[0]
                if n and t not in ("sub_payments", "registration_requests"):
                    left[t] = n
    assert left == {}, f"после удаления филиала остались данные: {left}"


GUARDS = {
    "webapp.py": [
        r"@employee_blocked\s+def api_broadcast_create", r"db\.broadcast_allowed\(",
        r"escapeHtml\(b\.message", r"paid_day > today or g\.is_employee",
    ],
    "bot.py": [r"except Forbidden:\s+# клиент остановил бота"],
}


@pytest.mark.parametrize("fname,pattern", [(f, p) for f, ps in GUARDS.items() for p in ps])
def test_audit2_guards_present(fname, pattern):
    src = open(os.path.join(ROOT, fname), encoding="utf-8").read()
    assert re.search(pattern, src), f"{fname}: пропала защита /{pattern}/"
