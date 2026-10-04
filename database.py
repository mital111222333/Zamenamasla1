"""
База данных системы учёта замены масла — мультитенантная версия.

Каждая точка замены масла (shop) — отдельный аккаунт с логином/паролем.
Все клиенты, машины, история и рассылки помечены shop_id и физически не
пересекаются между точками: КАЖДЫЙ запрос ниже, читающий или пишущий
клиентские данные, фильтруется по shop_id — это единственная гарантия
изоляции (не интерфейс, а сама база).

Роли:
- 'admin' — платформенный администратор: создаёт/включает/выключает точки,
  не видит клиентских данных ни одной точки.
- 'shop'  — обычная точка замены масла: видит и редактирует только свои
  данные.
"""

import os
import time as _time

# Серверы (Render, Railway) живут по UTC, а точки — по Ташкенту (UTC+5). Без
# этого с 00:00 до 05:00 «сегодня» на сервере было бы ещё вчера: записи и
# статистика «Сегодня/неделя» уезжали бы на предыдущий день. Переопределить
# можно переменной окружения TZ.
os.environ.setdefault("TZ", "Asia/Tashkent")
try:
    _time.tzset()
except AttributeError:  # Windows — tzset нет; для локального запуска не критично
    pass

import json
import math
import sqlite3
import threading
import functools
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from contextlib import contextmanager
from dateutil.relativedelta import relativedelta
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken

DB_PATH = os.environ.get("DB_PATH", "oil_bot.db")

# Пароли точек хранятся ДВАЖДЫ: как необратимый хэш (для проверки входа —
# это правильный, безопасный способ) и отдельно в обратимо зашифрованном виде
# (чтобы ты, как платформенный админ, мог посмотреть пароль в /admin, если
# точка его забудет). Ключ шифрования выводится из SECRET_KEY — той же
# переменной окружения, что уже используется для входа на сайт, отдельно
# задавать ничего не нужно.
_fernet_key = base64.urlsafe_b64encode(
    hashlib.sha256((os.environ.get("SECRET_KEY") or "insecure-dev-key").encode()).digest()
)
_cipher = Fernet(_fernet_key)


def _encrypt_password(password: str) -> str:
    return _cipher.encrypt(password.encode()).decode()


def _decrypt_password(token: str):
    if not token:
        return None
    try:
        return _cipher.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None

MAX_FOLLOWUP_REMINDERS = 6
FOLLOWUP_INTERVAL_DAYS = 14

# Аккаунт-бутстрап при самом первом запуске (создаётся один раз, если таблица
# shops ещё пуста) — чтобы не потерять уже работавшую точку при обновлении.
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "admin")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
BOOTSTRAP_SHOP_USERNAME = os.environ.get("SITE_USERNAME", "shop1")
BOOTSTRAP_SHOP_PASSWORD = os.environ.get("SITE_PASSWORD", "")
BOOTSTRAP_SHOP_NAME = os.environ.get("SHOP_NAME", "Пункт замены масла")
BOOTSTRAP_SHOP_PHONE = os.environ.get("SHOP_PHONE", "")
BOOTSTRAP_SHOP_ADDRESS = os.environ.get("SHOP_ADDRESS", "")
BOOTSTRAP_SHOP_HOURS = os.environ.get("SHOP_HOURS", "")
BOOTSTRAP_SHOP_LAT = os.environ.get("SHOP_LAT", "")
BOOTSTRAP_SHOP_LON = os.environ.get("SHOP_LON", "")
BOOTSTRAP_NOTIFY_TELEGRAM_ID = os.environ.get("ADMIN_TELEGRAM_ID", "")


def init_db():
    with get_conn() as conn:
        # WAL: чтение (статистика, списки) больше не блокирует запись и наоборот
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'shop',
            shop_name TEXT,
            phone TEXT,
            address TEXT,
            hours TEXT,
            lat REAL,
            lon REAL,
            anpr_token TEXT UNIQUE,
            notify_telegram_id TEXT,
            language TEXT DEFAULT 'ru',
            password_plain TEXT,
            sms_enabled INTEGER DEFAULT 0,
            eskiz_email TEXT,
            eskiz_password TEXT,
            warehouse_enabled INTEGER DEFAULT 0,
            client_group TEXT,
            parent_shop_id INTEGER,
            usd_rate REAL,
            card_number TEXT,
            owner_link_token TEXT UNIQUE,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL DEFAULT 1,
            telegram_id INTEGER,
            phone TEXT,
            full_name TEXT,
            link_token TEXT UNIQUE NOT NULL,
            linked_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (shop_id, telegram_id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL DEFAULT 1,
            plate_number TEXT NOT NULL,
            client_id INTEGER NOT NULL,
            car_brand TEXT,
            car_model TEXT,
            passport_token TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id),
            UNIQUE (shop_id, plate_number)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS oil_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            change_date TEXT NOT NULL,
            mileage INTEGER,
            service_type TEXT DEFAULT 'Замена масла',
            oil_brand TEXT,
            filter_changed INTEGER DEFAULT 0,
            cost INTEGER,
            cash_amount INTEGER,
            card_amount INTEGER,
            interval_months INTEGER,
            interval_unit TEXT DEFAULT 'months',
            next_mileage INTEGER,
            items_json TEXT,
            next_change_date TEXT,
            notes TEXT,
            reminder_count INTEGER DEFAULT 0,
            last_reminder_date TEXT,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (car_id) REFERENCES cars(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL DEFAULT 1,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            total_sent INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS shop_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_plain TEXT,
            full_name TEXT,
            role TEXT NOT NULL DEFAULT 'employee',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS installment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            car_id INTEGER NOT NULL,
            oil_change_id INTEGER,
            total_amount INTEGER NOT NULL,
            paid_amount INTEGER NOT NULL DEFAULT 0,
            installment_amount INTEGER NOT NULL,
            interval_days INTEGER NOT NULL,
            next_due_date TEXT NOT NULL,
            last_reminder_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (car_id) REFERENCES cars(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS installment_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            paid_date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (plan_id) REFERENCES installment_plans(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            name TEXT,
            amount INTEGER NOT NULL,
            day_of_month INTEGER NOT NULL,
            next_due_date TEXT NOT NULL,
            last_reminder_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS expense_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            recurring_expense_id INTEGER,
            category TEXT NOT NULL,
            name TEXT,
            amount INTEGER NOT NULL,
            expense_date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # --- индексы на часто используемые поля — чтобы поиск оставался
        # быстрым по мере роста числа точек, клиентов и записей. Безопасно
        # выполнять при каждом запуске (IF NOT EXISTS) и на уже существующих
        # базах — данные не трогаются, только ускоряется поиск. ---
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_shop ON clients(shop_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cars_shop ON cars(shop_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cars_plate_only ON cars(plate_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cars_client ON cars(client_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_oil_changes_car ON oil_changes(car_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_oil_changes_car_date ON oil_changes(car_id, change_date, id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_oil_changes_status_next ON oil_changes(status, next_change_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_broadcasts_shop ON broadcasts(shop_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_shop_users_shop ON shop_users(shop_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_installment_plans_shop ON installment_plans(shop_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_installment_plans_due ON installment_plans(status, next_due_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_installment_payments_plan ON installment_payments(plan_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reset_codes_shop ON password_reset_codes(shop_id, used, expires_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_recurring_expenses_shop ON recurring_expenses(shop_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_recurring_expenses_due ON recurring_expenses(status, next_due_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_expense_entries_shop ON expense_entries(shop_id, expense_date)")

        conn.commit()
        _migrate(conn)
        _migrate_subscription(conn)
        _migrate_name_aliases(conn)
        _bootstrap_accounts(conn)


def _migrate(conn):
    """Аккуратно доводит уже существующую (более старую) базу до текущей
    схемы, ничего не удаляя. Безопасно вызывать многократно."""

    # --- восстановление после возможного сбоя посреди прошлой миграции cars
    # (например, процесс перезапустился ровно между RENAME и DROP) ---
    leftover = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cars_old'"
    ).fetchone()
    if leftover:
        cars_count = conn.execute("SELECT COUNT(*) as c FROM cars").fetchone()["c"]
        old_count = conn.execute("SELECT COUNT(*) as c FROM cars_old").fetchone()["c"]
        if cars_count == 0 and old_count > 0:
            conn.execute("DROP TABLE cars")
            conn.execute("ALTER TABLE cars_old RENAME TO cars")
        else:
            conn.execute("DROP TABLE cars_old")

    # --- shops: добавляем language, если его ещё нет (старые точки получают 'ru') ---
    shop_cols = {row["name"] for row in conn.execute("PRAGMA table_info(shops)").fetchall()}
    if "language" not in shop_cols:
        conn.execute("ALTER TABLE shops ADD COLUMN language TEXT DEFAULT 'ru'")
    shop_cols.add("language")

    new_shop_cols = {
        "password_plain": "TEXT",
        "sms_enabled": "INTEGER DEFAULT 0",
        "eskiz_email": "TEXT",
        "eskiz_password": "TEXT",
        "warehouse_enabled": "INTEGER DEFAULT 0",
        "client_group": "TEXT",
        "parent_shop_id": "INTEGER",
        "usd_rate": "REAL",
        "card_number": "TEXT",
        "owner_link_token": "TEXT",
    }
    for col, ddl in new_shop_cols.items():
        if col not in shop_cols:
            conn.execute(f"ALTER TABLE shops ADD COLUMN {col} {ddl}")

    # --- у каждой точки должен быть токен для самостоятельной привязки
    # владельца к боту (взамен ручного ввода Telegram ID платформенным
    # админом) — генерируем недостающие, безопасно на каждом запуске
    rows_needing_token = conn.execute("SELECT id FROM shops WHERE owner_link_token IS NULL").fetchall()
    for row in rows_needing_token:
        conn.execute(
            "UPDATE shops SET owner_link_token=? WHERE id=?",
            (secrets.token_urlsafe(12), row["id"])
        )

    # --- склад: товары точки и история пополнений ---
    conn.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'l',
        stock_qty REAL NOT NULL DEFAULT 0,
        sell_price INTEGER,
        purchase_price INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS stock_restocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        shop_id INTEGER NOT NULL,
        quantity REAL NOT NULL,
        purchase_price INTEGER,
        restock_date TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS stock_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_shop_id INTEGER NOT NULL,
        from_shop_id INTEGER NOT NULL,
        to_shop_id INTEGER NOT NULL,
        from_product_id INTEGER NOT NULL,
        to_product_id INTEGER NOT NULL,
        quantity REAL NOT NULL,
        transfer_date TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS stock_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        old_qty REAL NOT NULL,
        new_qty REAL NOT NULL,
        reason TEXT,
        adjust_date TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_adjustments_shop ON stock_adjustments(shop_id)")
    tr_cols = [r[1] for r in conn.execute("PRAGMA table_info(stock_transfers)").fetchall()]
    if "batch" not in tr_cols:
        conn.execute("ALTER TABLE stock_transfers ADD COLUMN batch TEXT")

    # --- коды восстановления пароля: счётчик неверных попыток ---
    rc_cols = {r[1] for r in conn.execute("PRAGMA table_info(password_reset_codes)").fetchall()}
    if "attempts" not in rc_cols:
        conn.execute("ALTER TABLE password_reset_codes ADD COLUMN attempts INTEGER DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_transfers_from ON stock_transfers(from_shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_transfers_to ON stock_transfers(to_shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_shop ON products(shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_shop_category ON products(shop_id, category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_restocks_shop ON stock_restocks(shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_restocks_product ON stock_restocks(product_id)")

    # --- поставщики и заказы поставщику ---
    conn.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        phone TEXT,
        telegram TEXT,
        contact TEXT,
        delivery_days TEXT,
        note TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS supplier_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        supplier_id INTEGER,
        number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        note TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        sent_at TEXT,
        received_at TEXT,
        done_at TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS supplier_order_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'l',
        qty_ordered REAL NOT NULL DEFAULT 0,
        qty_received REAL,
        purchase_price INTEGER,
        alloc_json TEXT,
        dist_json TEXT
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_shop ON suppliers(shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_supplier_orders_shop ON supplier_orders(shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_supplier_order_lines_order ON supplier_order_lines(order_id)")
    pr_cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "supplier_id" not in pr_cols:
        conn.execute("ALTER TABLE products ADD COLUMN supplier_id INTEGER")
    sup_cols = {r[1] for r in conn.execute("PRAGMA table_info(suppliers)").fetchall()}
    if "tg_chat_id" not in sup_cols:
        conn.execute("ALTER TABLE suppliers ADD COLUMN tg_chat_id TEXT")
    if "link_token" not in sup_cols:
        conn.execute("ALTER TABLE suppliers ADD COLUMN link_token TEXT")
    if "pay_days" not in sup_cols:
        conn.execute("ALTER TABLE suppliers ADD COLUMN pay_days INTEGER")
    if "debt_reminded_at" not in sup_cols:
        conn.execute("ALTER TABLE suppliers ADD COLUMN debt_reminded_at TEXT")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS supplier_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        supplier_id INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'payment',
        amount INTEGER NOT NULL,
        pay_date TEXT NOT NULL,
        note TEXT,
        order_id INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_supplier_payments_sup ON supplier_payments(supplier_id)")
    # --- расчёты с поставщиком: курс доллара фиксируется в каждой операции,
    # чтобы эквивалент в $ через годы оставался тем, что был в день операции ---
    sp_cols = {r[1] for r in conn.execute("PRAGMA table_info(supplier_payments)").fetchall()}
    if "usd_rate" not in sp_cols:
        conn.execute("ALTER TABLE supplier_payments ADD COLUMN usd_rate REAL")
        # старые записи (до этой версии) — курс точки на момент обновления
        conn.execute("""UPDATE supplier_payments SET usd_rate =
                        (SELECT usd_rate FROM shops WHERE shops.id = supplier_payments.shop_id)
                        WHERE usd_rate IS NULL""")
    for col, ddl in (("currency", "TEXT DEFAULT 'UZS'"), ("amount_usd_cents", "INTEGER"), ("method", "TEXT"),
                     ("status", "TEXT DEFAULT 'active'"), ("cancel_reason", "TEXT"), ("cancelled_at", "TEXT"),
                     ("client_token", "TEXT")):
        if col not in sp_cols:
            conn.execute(f"ALTER TABLE supplier_payments ADD COLUMN {col} {ddl}")
    conn.execute("UPDATE supplier_payments SET status='active' WHERE status IS NULL")
    conn.execute("UPDATE supplier_payments SET currency='UZS' WHERE currency IS NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_payments_token "
                 "ON supplier_payments(shop_id, client_token) WHERE client_token IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_supplier_payments_shop_date ON supplier_payments(shop_id, supplier_id, pay_date)")
    so_cols = {r[1] for r in conn.execute("PRAGMA table_info(supplier_orders)").fetchall()}
    if "usd_rate" not in so_cols:
        conn.execute("ALTER TABLE supplier_orders ADD COLUMN usd_rate REAL")
        conn.execute("""UPDATE supplier_orders SET usd_rate =
                        (SELECT usd_rate FROM shops WHERE shops.id = supplier_orders.shop_id)
                        WHERE usd_rate IS NULL AND status IN ('received', 'done')""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_supplier_orders_sup ON supplier_orders(shop_id, supplier_id)")
    sup_cols2 = {r[1] for r in conn.execute("PRAGMA table_info(suppliers)").fetchall()}
    if "archived_at" not in sup_cols2:
        conn.execute("ALTER TABLE suppliers ADD COLUMN archived_at TEXT")
    rs_cols = {r[1] for r in conn.execute("PRAGMA table_info(stock_restocks)").fetchall()}
    if "order_id" not in rs_cols:
        conn.execute("ALTER TABLE stock_restocks ADD COLUMN order_id INTEGER")

    # --- oil_changes: добавляем недостающие колонки (из более ранних версий) ---
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(oil_changes)").fetchall()}
    to_add = {
        "service_type": "TEXT DEFAULT 'Замена масла'",
        "filter_changed": "INTEGER DEFAULT 0",
        "cost": "INTEGER",
        "reminder_count": "INTEGER DEFAULT 0",
        "last_reminder_date": "TEXT",
        "interval_unit": "TEXT DEFAULT 'months'",
        "next_mileage": "INTEGER",
        "items_json": "TEXT",
        "cash_amount": "INTEGER",
        "card_amount": "INTEGER",
    }
    for col, ddl in to_add.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE oil_changes ADD COLUMN {col} {ddl}")
    if "reminder_sent" in cols and "reminder_count" not in cols:
        conn.execute("UPDATE oil_changes SET reminder_count=reminder_sent WHERE reminder_count=0")
    if "cash_amount" not in cols:
        # старые записи (до появления разбивки нал/карта) считаем полностью
        # наличными — это было единственным способом оплаты на тот момент
        conn.execute("UPDATE oil_changes SET cash_amount=cost, card_amount=0 WHERE cost IS NOT NULL AND cash_amount IS NULL")

    # --- пароли больше нигде не хранятся в расшифровываемом виде (раньше
    # шифровались обратимо, чтобы платформенный админ мог их посмотреть).
    # Чистим то, что уже успело сохраниться раньше — идемпотентно, безопасно
    # выполнять на каждом запуске.
    conn.execute("UPDATE shops SET password_plain=NULL WHERE password_plain IS NOT NULL")
    conn.execute("UPDATE shop_users SET password_plain=NULL WHERE password_plain IS NOT NULL")

    # --- clients: старая схема имела UNIQUE(telegram_id) без учёта shop_id.
    # Это ломается, если один и тот же человек — клиент ДВУХ РАЗНЫХ,
    # независимых точек на этой платформе (обычное дело): второй раз
    # привязать тот же Telegram-аккаунт стало бы невозможно (ошибка базы).
    # Пересоздаём с UNIQUE(shop_id, telegram_id) — один и тот же Telegram
    # может быть привязан к разным точкам по отдельности, но не дважды
    # внутри одной точки. linked_at нужен, чтобы понимать, к какой точке
    # клиент привязывался последней (это и показывается по кнопкам бота).
    client_cols = {row["name"] for row in conn.execute("PRAGMA table_info(clients)").fetchall()}
    if "shop_id" not in client_cols:
        conn.execute("ALTER TABLE clients ADD COLUMN shop_id INTEGER NOT NULL DEFAULT 1")
        client_cols.add("shop_id")

    if "linked_at" not in client_cols:
        conn.execute("ALTER TABLE clients RENAME TO clients_old")
        conn.execute("""
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL DEFAULT 1,
            telegram_id INTEGER,
            phone TEXT,
            full_name TEXT,
            link_token TEXT UNIQUE NOT NULL,
            linked_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (shop_id, telegram_id)
        )
        """)
        old_client_cols = {row["name"] for row in conn.execute("PRAGMA table_info(clients_old)").fetchall()}
        common = [c for c in ["id", "shop_id", "telegram_id", "phone", "full_name", "link_token", "created_at"]
                  if c in old_client_cols]
        conn.execute(f"INSERT INTO clients ({', '.join(common)}) SELECT {', '.join(common)} FROM clients_old")
        # У кого telegram_id уже был проставлен раньше — считаем, что он и был "последней" привязкой
        conn.execute("UPDATE clients SET linked_at=created_at WHERE telegram_id IS NOT NULL")
        conn.execute("DROP TABLE clients_old")

    bc_cols = {row["name"] for row in conn.execute("PRAGMA table_info(broadcasts)").fetchall()}
    if "shop_id" not in bc_cols:
        conn.execute("ALTER TABLE broadcasts ADD COLUMN shop_id INTEGER NOT NULL DEFAULT 1")

    # --- cars: старая схема имела UNIQUE(plate_number) без shop_id — номер
    # мог принадлежать только одной точке во всей системе, что для
    # мультитенантности неверно (у двух разных точек может быть клиент с
    # одинаковым госномером). Пересоздаём таблицу с UNIQUE(shop_id, plate_number),
    # если ещё не сделано.
    car_cols = {row["name"] for row in conn.execute("PRAGMA table_info(cars)").fetchall()}
    if "shop_id" not in car_cols:
        conn.execute("ALTER TABLE cars RENAME TO cars_old")
        conn.execute("""
        CREATE TABLE cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL DEFAULT 1,
            plate_number TEXT NOT NULL,
            client_id INTEGER NOT NULL,
            car_brand TEXT,
            car_model TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id),
            UNIQUE (shop_id, plate_number)
        )
        """)
        old_cols = {row["name"] for row in conn.execute("PRAGMA table_info(cars_old)").fetchall()}
        common = [c for c in ["id", "plate_number", "client_id", "car_brand", "car_model", "created_at"] if c in old_cols]
        conn.execute(f"INSERT INTO cars (shop_id, {', '.join(common)}) SELECT 1, {', '.join(common)} FROM cars_old")
        conn.execute("DROP TABLE cars_old")

    # --- у каждой машины должен быть токен для публичной ссылки на
    # сервисный паспорт — проверяем заново (не по возможно устаревшему
    # car_cols выше, если только что была полная пересборка таблицы)
    car_cols_now = {row["name"] for row in conn.execute("PRAGMA table_info(cars)").fetchall()}
    if "passport_token" not in car_cols_now:
        conn.execute("ALTER TABLE cars ADD COLUMN passport_token TEXT")
    rows_needing_passport_token = conn.execute("SELECT id FROM cars WHERE passport_token IS NULL").fetchall()
    for row in rows_needing_passport_token:
        conn.execute("UPDATE cars SET passport_token=? WHERE id=?", (secrets.token_urlsafe(16), row["id"]))

    conn.commit()


def _bootstrap_accounts(conn):
    """При самом первом запуске (таблица shops ещё пуста) создаёт платформенного
    админа и точку №1 — так, чтобы уже работавшая (до мультитенантности) точка
    не потеряла доступ и продолжила использовать старые переменные окружения
    (SITE_USERNAME/SITE_PASSWORD/SHOP_NAME и т.д.) как логин своей точки."""
    existing = conn.execute("SELECT COUNT(*) as c FROM shops").fetchone()["c"]
    if existing > 0:
        return

    # ВАЖНО: точка №1 создаётся ПЕРВОЙ, чтобы получить id=1 — именно на
    # shop_id=1 миграция выше переносит все данные, созданные до перехода
    # на мультитенантность. Если поменять порядок местами, старые данные
    # окажутся привязаны не к той точке.
    shop_password = BOOTSTRAP_SHOP_PASSWORD or secrets.token_urlsafe(9)
    admin_password = BOOTSTRAP_ADMIN_PASSWORD or secrets.token_urlsafe(9)

    try:
        conn.execute("""
            INSERT INTO shops (username, password_hash, password_plain, role, shop_name, phone, address, hours, lat, lon,
                                anpr_token, notify_telegram_id, is_active)
            VALUES (?, ?, NULL, 'shop', ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            BOOTSTRAP_SHOP_USERNAME, generate_password_hash(shop_password),
            BOOTSTRAP_SHOP_NAME, BOOTSTRAP_SHOP_PHONE or None, BOOTSTRAP_SHOP_ADDRESS or None, BOOTSTRAP_SHOP_HOURS or None,
            float(BOOTSTRAP_SHOP_LAT) if BOOTSTRAP_SHOP_LAT else None,
            float(BOOTSTRAP_SHOP_LON) if BOOTSTRAP_SHOP_LON else None,
            secrets.token_urlsafe(8), BOOTSTRAP_NOTIFY_TELEGRAM_ID or None,
        ))
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(f"ВНИМАНИЕ: не удалось создать точку №1 (логин уже занят?): {e}")

    try:
        conn.execute(
            "INSERT INTO shops (username, password_hash, password_plain, role, shop_name, is_active) "
            "VALUES (?, ?, NULL, 'admin', 'Платформа', 1)",
            (BOOTSTRAP_ADMIN_USERNAME, generate_password_hash(admin_password))
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(f"ВНИМАНИЕ: не удалось создать платформенного админа (логин совпадает с логином точки №1? "
              f"PLATFORM_ADMIN_USERNAME и SITE_USERNAME должны различаться): {e}")

    if not BOOTSTRAP_ADMIN_PASSWORD or not BOOTSTRAP_SHOP_PASSWORD:
        # Печатаем в лог Railway один раз — если пароли не заданы явно через
        # переменные окружения, иначе их будет неоткуда узнать.
        print("=" * 60)
        print("СОЗДАНЫ ПЕРВЫЕ АККАУНТЫ (сохраните эти данные!):")
        if not BOOTSTRAP_ADMIN_PASSWORD:
            print(f"  Платформенный админ: {BOOTSTRAP_ADMIN_USERNAME} / {admin_password}")
        if not BOOTSTRAP_SHOP_PASSWORD:
            print(f"  Точка №1:            {BOOTSTRAP_SHOP_USERNAME} / {shop_password}")
        print("=" * 60)


def make_compressed_backup(tag: str):
    """Снимок базы через backup API SQLite (безопасно во время работы) и
    сжатие gzip — копия становится в 4–6 раз меньше, поэтому в лимит
    Telegram (50 МБ на файл) база влезает намного дольше. Возвращает
    (путь_к_снимку, путь_к_сжатому_файлу); удалить оба — забота вызывающего."""
    import gzip
    import shutil
    raw = f"/tmp/oilbot_backup_{tag}.db"
    gz = raw + ".gz"
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(raw)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    with open(raw, "rb") as fi, gzip.open(gz, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo, 1024 * 1024)
    return raw, gz


# Один общий замок на все ЗАПИСИ в базу. Бот и веб-панель работают в одном
# процессе (разными потоками), поэтому замок надёжно выстраивает в очередь
# одновременные «прочитал — проверил — записал» с разных телефонов: без него
# два одновременных удаления одной записи возвращали товар на склад дважды,
# два платежа по долгу затирали друг друга, а склад мог уйти в минус.
# RLock — можно вызывать одну защищённую функцию из другой.
WRITE_LOCK = threading.RLock()


def _serialized(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with WRITE_LOCK:
            return fn(*args, **kwargs)
    return wrapped


@contextmanager
def get_conn():
    # timeout/busy_timeout: если база на мгновение занята (резервная копия,
    # фоновая задача бота) — подождать до 30 с, а не сразу падать с ошибкой
    # «database is locked», как это было под нагрузкой.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
    finally:
        conn.close()


def normalize_plate(plate: str) -> str:
    return plate.strip().upper().replace(" ", "")


def generate_token() -> str:
    return secrets.token_urlsafe(6)


# ---------- Аккаунты точек (shops) ----------

@_serialized
def create_shop(username: str, password: str, shop_name: str = None, phone: str = None,
                 address: str = None, hours: str = None, lat: float = None, lon: float = None,
                 notify_telegram_id: str = None, role: str = "shop", client_group: str = None) -> dict:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO shops (username, password_hash, password_plain, role, shop_name, phone, address, hours, lat, lon,
                                anpr_token, notify_telegram_id, is_active, client_group, owner_link_token)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (username, generate_password_hash(password), role, shop_name,
              phone, address, hours, lat, lon, secrets.token_urlsafe(8), notify_telegram_id, client_group or None,
              secrets.token_urlsafe(12)))
        conn.commit()
        return get_shop(cur.lastrowid)


@_serialized
def set_shop_client_group(shop_id: int, client_group: str):
    """Платформенный админ объединяет точку с остальными филиалами того же
    клиента — просто текстовая метка, по которой /admin группирует список.
    Пустая строка снимает группировку (точка снова отдельная)."""
    with get_conn() as conn:
        conn.execute("UPDATE shops SET client_group=? WHERE id=?", (client_group or None, shop_id))
        conn.commit()


@_serialized
def set_shop_usd_rate(shop_id: int, rate):
    """Владелец точки (или главный аккаунт) сам выставляет свой курс доллара
    — используется только для перевода при вводе цены закупки в $, ничего
    не пересчитывает задним числом для уже сохранённых товаров."""
    with get_conn() as conn:
        conn.execute("UPDATE shops SET usd_rate=? WHERE id=?", (rate, shop_id))
        conn.commit()


@_serialized
def reset_shop_password(shop_id: int, new_password: str):
    """Сбрасывает пароль точки — обновляет только хэш (для входа). Пароль
    нигде не сохраняется в расшифровываемом виде: платформенный админ видит
    новый пароль один раз, сразу после сброса, в ответе на само действие —
    а не хранящимся где-либо для повторного просмотра."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE shops SET password_hash=?, password_plain=NULL WHERE id=?",
            (generate_password_hash(new_password), shop_id)
        )
        conn.commit()


@_serialized
def set_shop_notify_telegram_id(shop_id: int, notify_telegram_id):
    """Привязывает (или меняет) Telegram ID точки для уведомлений и
    восстановления пароля. Пустое значение снимает привязку."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE shops SET notify_telegram_id=? WHERE id=?",
            (notify_telegram_id or None, shop_id)
        )
        conn.commit()


def find_shop_by_username(username: str):
    """Точка (владелец или филиал) по логину, без проверки пароля — для
    восстановления доступа. Сотрудники и платформенные админы сюда не входят."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM shops WHERE username=? AND role IN ('shop', 'branch')", (username,)
        ).fetchone()
        return dict(row) if row else None


@_serialized
def link_shop_owner_by_token(telegram_id: int, token: str):
    """Владелец точки (или филиала) сам привязывает свой Telegram, перейдя
    по персональной ссылке — вместо того чтобы платформенный админ вручную
    вписывал ID. Раз владелец сам переходит по ссылке и пишет боту, Telegram
    после этого разрешает боту писать ему первым (это и была причина, по
    которой 'ручной' ID часто не срабатывал). Возвращает точку при успехе,
    None — если токен не найден."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM shops WHERE owner_link_token=?", (token,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE shops SET notify_telegram_id=? WHERE id=?", (str(telegram_id), row["id"]))
        conn.commit()
        return get_shop(row["id"])


@_serialized
def create_password_reset_code(shop_id: int) -> str:
    """Генерирует 6-значный код для восстановления пароля через Telegram,
    действует 10 минут. Прошлые неиспользованные коды этой точки становятся
    недействительными — чтобы старый запрос нельзя было использовать после
    того, как запросили новый код."""
    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("UPDATE password_reset_codes SET used=1 WHERE shop_id=? AND used=0", (shop_id,))
        conn.execute(
            "INSERT INTO password_reset_codes (shop_id, code, expires_at) VALUES (?, ?, ?)",
            (shop_id, code, expires_at)
        )
        conn.commit()
    return code


@_serialized
def reset_password_with_code(username: str, code: str, new_password: str) -> bool:
    """Проверяет код восстановления (не просрочен, не использован, совпадает)
    и, если всё верно, меняет пароль точки. Возвращает True при успехе,
    False — если логин, код или срок не подошли (без уточнения, что именно,
    чтобы не подсказывать посторонним, какие логины существуют)."""
    shop = find_shop_by_username(username)
    if not shop:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM password_reset_codes WHERE shop_id=? AND code=? AND used=0 AND expires_at >= ? "
            "ORDER BY id DESC LIMIT 1",
            (shop["id"], code, now)
        ).fetchone()
        if not row:
            # неверный код — считаем попытку; после 5 ошибок все коды точки
            # сгорают и нужно запрашивать новый (защита от подбора 6 цифр)
            latest = conn.execute(
                "SELECT id, attempts FROM password_reset_codes WHERE shop_id=? AND used=0 "
                "ORDER BY id DESC LIMIT 1", (shop["id"],)
            ).fetchone()
            if latest:
                if (latest["attempts"] or 0) + 1 >= 5:
                    conn.execute("UPDATE password_reset_codes SET used=1 WHERE shop_id=? AND used=0", (shop["id"],))
                else:
                    conn.execute("UPDATE password_reset_codes SET attempts=COALESCE(attempts,0)+1 WHERE id=?",
                                 (latest["id"],))
                conn.commit()
            return False
        conn.execute("UPDATE password_reset_codes SET used=1 WHERE id=?", (row["id"],))
        conn.execute(
            "UPDATE shops SET password_hash=?, password_plain=NULL WHERE id=?",
            (generate_password_hash(new_password), shop["id"])
        )
        conn.commit()
    return True


def authenticate_shop(username: str, password: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shops WHERE username=?", (username,)).fetchone()
        if not row or not row["is_active"]:
            return None
        if not check_password_hash(row["password_hash"], password):
            return None
        return dict(row)


def authenticate_shop_employee(username: str, password: str):
    """Логин сотрудника (ограниченный доступ) — своя таблица shop_users,
    не путать с владельцем точки в shops."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shop_users WHERE username=?", (username,)).fetchone()
        if not row or not row["is_active"]:
            return None
        if not check_password_hash(row["password_hash"], password):
            return None
        return dict(row)


@_serialized
def create_shop_employee(shop_id: int, username: str, password: str = None, full_name: str = None):
    """Платформенный админ создаёт логин сотрудника для точки — ограниченный
    доступ (без прибыли, цен закупки, статистики, экспорта). Пароль
    возвращается один раз в ответе — нигде не сохраняется в расшифровываемом виде."""
    if not password:
        password = secrets.token_urlsafe(9)
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO shop_users (shop_id, username, password_hash, password_plain, full_name, role) "
                "VALUES (?, ?, ?, NULL, ?, 'employee')",
                (shop_id, username, generate_password_hash(password), full_name)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return None
        return {"username": username, "password": password}


def get_active_employee(username: str, shop_id: int):
    """Логин сотрудника, только если он ещё существует, включён и относится
    к этой точке — проверяется при КАЖДОМ запросе, чтобы удалённый
    сотрудник сразу терял доступ, а не через месяц, когда истечёт вход."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, shop_id, is_active, password_hash FROM shop_users WHERE username=? AND shop_id=?",
            (username, shop_id)
        ).fetchone()
        return dict(row) if row and row["is_active"] else None


def list_shop_employees(shop_id: int):
    """Список сотрудников точки — без пароля: он нигде не хранится в
    расшифровываемом виде, только виден один раз сразу после создания/сброса."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, is_active, created_at FROM shop_users "
            "WHERE shop_id=? ORDER BY created_at DESC", (shop_id,)
        ).fetchall()
        return [dict(r) for r in rows]


@_serialized
def delete_shop_employee(employee_id: int, shop_id: int) -> bool:
    """Удаляет логин сотрудника — только если он реально принадлежит этой точке."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM shop_users WHERE id=? AND shop_id=?", (employee_id, shop_id))
        conn.commit()
        return cur.rowcount > 0


@_serialized
def reset_shop_employee_password(employee_id: int, shop_id: int):
    new_password = secrets.token_urlsafe(9)
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE shop_users SET password_hash=?, password_plain=NULL WHERE id=? AND shop_id=?",
            (generate_password_hash(new_password), employee_id, shop_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return new_password


def get_shop(shop_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
        return dict(row) if row else None


def get_shop_by_anpr_token(token: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shops WHERE anpr_token=?", (token,)).fetchone()
        return dict(row) if row else None


def list_shops():
    """Все точки (без платформенных админов) + число их клиентов — для админ-панели.
    Пароль нигде не хранится в расшифровываемом виде — только виден один раз
    сразу после создания или сброса, в ответе на само действие."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM clients WHERE shop_id = s.id) as client_count
            FROM shops s WHERE s.role='shop' ORDER BY s.created_at DESC
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            del d["password_hash"]  # хэш не нужен на клиенте, чтобы не путать с настоящим паролем
            del d["password_plain"]
            result.append(d)
        return result


@_serialized
def set_shop_active(shop_id: int, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE shops SET is_active=? WHERE id=?", (1 if active else 0, shop_id))
        conn.commit()


@_serialized
def set_shop_language(shop_id: int, language: str):
    if language not in ("ru", "uz"):
        language = "ru"
    with get_conn() as conn:
        conn.execute("UPDATE shops SET language=? WHERE id=?", (language, shop_id))
        conn.commit()


@_serialized
def set_shop_sms_enabled(shop_id: int, enabled: bool):
    """Платформенный админ включает/выключает саму ВОЗМОЖНОСТЬ SMS для точки.
    Даже при включении SMS не заработают, пока точка сама не впишет свои
    данные Eskiz в своих настройках — это её собственный договор/аккаунт."""
    with get_conn() as conn:
        conn.execute("UPDATE shops SET sms_enabled=? WHERE id=?", (1 if enabled else 0, shop_id))
        conn.commit()


@_serialized
def set_shop_eskiz_credentials(shop_id: int, email: str, password: str):
    """Точка сама вписывает свои логин/пароль от своего аккаунта Eskiz.uz.
    Пароль от Eskiz хранится так же, обратимо зашифрованным — он нужен боту,
    чтобы самому логиниться в Eskiz и получать токен для отправки SMS."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE shops SET eskiz_email=?, eskiz_password=? WHERE id=?",
            (email or None, _encrypt_password(password) if password else None, shop_id)
        )
        conn.commit()


def get_shop_eskiz_credentials(shop_id: int):
    """Возвращает (email, пароль_в_открытом_виде) для отправки SMS, или (None, None)."""
    shop = get_shop(shop_id)
    if not shop or not shop.get("eskiz_email") or not shop.get("eskiz_password"):
        return None, None
    return shop["eskiz_email"], _decrypt_password(shop["eskiz_password"])


@_serialized
def set_shop_warehouse_enabled(shop_id: int, enabled: bool):
    """Платформенный админ включает/выключает вкладку «Склад» для точки."""
    with get_conn() as conn:
        conn.execute("UPDATE shops SET warehouse_enabled=? WHERE id=?", (1 if enabled else 0, shop_id))
        conn.commit()


# ============ СКЛАД: товары и остатки ============

@_serialized
def create_product(shop_id: int, category: str, name: str, unit: str = "l",
                    sell_price=None, purchase_price=None, initial_stock: float = 0) -> dict:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO products (shop_id, category, name, unit, stock_qty, sell_price, purchase_price, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (shop_id, category, name, unit, initial_stock, sell_price, purchase_price))
        conn.commit()
        return get_product(cur.lastrowid, shop_id)


def get_product(product_id: int, shop_id: int, active_only: bool = True):
    """Только если товар принадлежит указанной точке — проверка прав.
    По умолчанию не находит «удалённые» (is_active=0) товары — на них больше
    нельзя ссылаться в новых/редактируемых записях о замене, даже если их id
    ещё где-то передаётся. Уже сохранённые старые записи это не затрагивает —
    там название/марка уже сохранены как обычный текст в items_json."""
    query = "SELECT * FROM products WHERE id=? AND shop_id=?"
    params = [product_id, shop_id]
    if active_only:
        query += " AND is_active=1"
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def list_products(shop_id: int, category: str = None, active_only: bool = True):
    query = "SELECT * FROM products WHERE shop_id=?"
    params = [shop_id]
    if category:
        query += " AND category=?"
        params.append(category)
    if active_only:
        query += " AND is_active=1"
    query += " ORDER BY category, name"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


@_serialized
def update_product(product_id: int, shop_id: int, name=None, sell_price=None, purchase_price=None,
                   clear_purchase_price=False):
    """Меняет название и цены товара. Возвращает (ok, error).
    Важно: прошлые продажи НЕ пересчитываются — в каждой записи о замене
    уже сохранена цена закупки на момент продажи (cost_price), поэтому
    прибыль за прошлые дни остаётся честной. Новые цены действуют с этого
    момента. Тип и единицу измерения не меняем — иначе поехала бы вся
    статистика по литрам/штукам."""
    existing = get_product(product_id, shop_id)
    if not existing:
        return False, "not_found"
    fields = {}
    if name is not None:
        name = " ".join(name.split())
        if not name:
            return False, "empty_name"
        key = (existing["category"], name.upper())
        for p in list_products(shop_id):
            if p["id"] != product_id and (p["category"], " ".join((p["name"] or "").upper().split())) == key:
                return False, "duplicate"
        fields["name"] = name
    if sell_price is not None:
        if sell_price < 0:
            return False, "bad_price"
        fields["sell_price"] = sell_price
    if purchase_price is not None:
        if purchase_price < 0:
            return False, "bad_price"
        fields["purchase_price"] = purchase_price
    elif clear_purchase_price:
        fields["purchase_price"] = None
    if not fields:
        return True, None
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE products SET {set_clause} WHERE id=?", (*fields.values(), product_id))
        conn.commit()
    if existing.get("purchase_price") is None and fields.get("purchase_price") is not None:
        backfill_cost_price(shop_id, product_id, fields["purchase_price"])
    return True, None


@_serialized
def set_stock_count(product_id: int, shop_id: int, new_qty: float, reason: str = None):
    """Корректировка остатка по факту (после пересчёта на складе). Не молча
    перезаписывает число, а пишет запись в историю движения: было → стало,
    кто бы ни поменял — всегда видно, откуда взялась разница."""
    existing = get_product(product_id, shop_id)
    if not existing:
        return False, "not_found"
    if new_qty is None or new_qty < 0:
        return False, "bad_qty"
    old_qty = existing["stock_qty"] or 0
    if abs(old_qty - new_qty) < 1e-9:
        return True, None
    with get_conn() as conn:
        conn.execute("UPDATE products SET stock_qty=? WHERE id=?", (new_qty, product_id))
        conn.execute("""
            INSERT INTO stock_adjustments (shop_id, product_id, old_qty, new_qty, reason, adjust_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (shop_id, product_id, old_qty, new_qty, (reason or "").strip()[:200] or None,
              datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
    return True, None


@_serialized
def delete_product(product_id: int, shop_id: int):
    """«Удаление» товара — мягкое (is_active=0), чтобы старые записи о заменах,
    которые уже на него ссылались, не потеряли название/историю."""
    existing = get_product(product_id, shop_id)
    if not existing:
        return False
    with get_conn() as conn:
        conn.execute("UPDATE products SET is_active=0 WHERE id=?", (product_id,))
        conn.commit()
    return True


@_serialized
def restock_product(product_id: int, shop_id: int, quantity: float, purchase_price=None, restock_date: str = None):
    """Пополнение склада — увеличивает остаток и пишет запись в историю
    пополнений (дата, количество, цена закупки на тот момент). Если указана
    цена закупки — обновляет её и в самой карточке товара (для будущих продаж)."""
    existing = get_product(product_id, shop_id)
    if not existing:
        return False
    if not restock_date:
        restock_date = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id=?", (quantity, product_id))
        if purchase_price is not None:
            conn.execute("UPDATE products SET purchase_price=? WHERE id=?", (purchase_price, product_id))
        conn.execute("""
            INSERT INTO stock_restocks (product_id, shop_id, quantity, purchase_price, restock_date)
            VALUES (?, ?, ?, ?, ?)
        """, (product_id, shop_id, quantity, purchase_price, restock_date))
        conn.commit()
    if existing.get("purchase_price") is None and purchase_price is not None:
        backfill_cost_price(shop_id, product_id, purchase_price)
    return True


def get_restock_history(shop_id: int, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT r.*, p.name as product_name, p.category, p.unit, o.number as order_number
            FROM stock_restocks r JOIN products p ON p.id = r.product_id
            LEFT JOIN supplier_orders o ON o.id = r.order_id
            WHERE r.shop_id=? ORDER BY r.restock_date DESC, r.id DESC LIMIT ?
        """, (shop_id, limit)).fetchall()
        return [dict(r) for r in rows]


@_serialized
def adjust_stock(product_id: int, delta: float):
    """Внутренняя функция — сдвигает остаток товара на delta (может быть
    отрицательным при продаже или положительным при отмене/удалении записи,
    которая его расходовала). Не проверяет принадлежность точке — вызывается
    только изнутри add/update/delete_oil_change, где принадлежность уже
    проверена на уровне самой записи о замене."""
    with get_conn() as conn:
        conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (delta, product_id))
        conn.commit()


def username_taken(username: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM shops WHERE username=?", (username,)).fetchone() is not None


@_serialized
def update_shop_identity(shop_id: int, shop_name: str, username: str) -> bool:
    """Меняет название точки и логин — то, что нельзя было поправить после
    создания. Уникальность логина проверяется на уровне вызывающего кода
    (webapp.py), здесь — только само обновление."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE shops SET shop_name=?, username=? WHERE id=?",
            (shop_name, username, shop_id)
        )
        conn.commit()
        return cur.rowcount > 0


# ---------- Клиенты ----------

@_serialized
def get_or_create_client(shop_id: int, owner_name: str, phone: str = None):
    """Находит клиента ЭТОЙ ЖЕ точки по телефону (если указан) или создаёт
    нового с новым персональным токеном для ссылки/QR."""
    phone = (phone or "").strip() or None
    with get_conn() as conn:
        if phone:
            existing = conn.execute(
                "SELECT * FROM clients WHERE shop_id=? AND phone=?", (shop_id, phone)
            ).fetchone()
            if existing:
                if owner_name:
                    conn.execute("UPDATE clients SET full_name=? WHERE id=?", (owner_name, existing["id"]))
                    conn.commit()
                return dict(existing)

        token = generate_token()
        cur = conn.execute(
            "INSERT INTO clients (shop_id, phone, full_name, link_token) VALUES (?, ?, ?, ?)",
            (shop_id, phone, owner_name, token)
        )
        conn.commit()
        return {"id": cur.lastrowid, "shop_id": shop_id, "telegram_id": None, "phone": phone,
                "full_name": owner_name, "link_token": token}


def get_client_by_token(token: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clients WHERE link_token=?", (token,)).fetchone()
        return dict(row) if row else None


@_serialized
def link_client_by_token(telegram_id: int, token: str, tg_full_name: str = None):
    """Привязывает Telegram-аккаунт клиента к его записи по персональному токену.
    Токен уникален глобально, поэтому сам определяет нужную точку (shop_id
    берётся из записи клиента) — участнику не нужно ничего дополнительно указывать.
    Один и тот же человек может быть отдельно привязан сразу к нескольким
    независимым точкам (это разные строки clients) — see get_client_by_telegram_id."""
    with get_conn() as conn:
        client = conn.execute("SELECT * FROM clients WHERE link_token=?", (token,)).fetchone()
        if not client:
            return None
        full_name = client["full_name"] or tg_full_name
        try:
            conn.execute(
                "UPDATE clients SET telegram_id=?, full_name=?, linked_at=datetime('now') WHERE id=?",
                (telegram_id, full_name, client["id"])
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # этот Telegram уже привязан к другой карточке клиента этой же точки
            # (две машины записаны на разные телефоны) — вторую привязку не
            # делаем, но и бот не должен падать: возвращаем уже привязанную
            conn.rollback()
            row = conn.execute("SELECT * FROM clients WHERE shop_id=? AND telegram_id=?",
                               (client["shop_id"], telegram_id)).fetchone()
            return dict(row) if row else None
        return get_client_by_token(token)


def get_client_by_telegram_id(telegram_id: int):
    """Если этот Telegram-аккаунт привязан сразу к нескольким точкам (клиент —
    общий покупатель нескольких независимых точек на этой платформе),
    возвращает запись САМОЙ НЕДАВНО привязанной точки — её и показывают
    кнопки бота «Моя история» / «О пункте»."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM clients WHERE telegram_id=? ORDER BY linked_at DESC, id DESC LIMIT 1",
            (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def get_client_cars(client_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cars WHERE client_id=?", (client_id,)).fetchall()
        return [dict(r) for r in rows]


def get_client_full_history(telegram_id: int):
    """Вся история по всем машинам клиента (для просмотра в боте самим клиентом).
    Строго в рамках ОДНОЙ (самой недавно привязанной) точки — see
    get_client_by_telegram_id — чтобы у клиента, привязанного сразу к
    нескольким независимым точкам, машины разных точек не перемешивались
    в одном списке."""
    client = get_client_by_telegram_id(telegram_id)
    if not client:
        return []
    with get_conn() as conn:
        cars = conn.execute("SELECT * FROM cars WHERE client_id=?", (client["id"],)).fetchall()
        result = []
        for car in cars:
            history = conn.execute(
                "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date DESC, id DESC",
                (car["id"],)
            ).fetchall()
            result.append({"car": dict(car), "history": [dict(h) for h in history]})
        return result


# ---------- Машины (всегда со shop_id — это и есть изоляция) ----------

def find_car(shop_id: int, plate_number: str):
    plate_number = normalize_plate(plate_number)
    with get_conn() as conn:
        car = conn.execute(
            "SELECT * FROM cars WHERE shop_id=? AND plate_number=?", (shop_id, plate_number)
        ).fetchone()
        return dict(car) if car else None


@_serialized
def update_car_and_client(shop_id: int, plate: str, new_plate: str, owner_name: str, owner_phone: str,
                           car_brand: str, car_model: str):
    """Редактирование данных клиента и машины целиком — имя, телефон,
    госномер, марка/модель. Возвращает True при успехе; False, если машина
    не найдена у этой точки, или новый госномер уже занят другой машиной
    этой же точки."""
    car = find_car(shop_id, plate)
    if not car:
        return False
    new_plate = normalize_plate(new_plate)
    if new_plate != car["plate_number"]:
        clash = find_car(shop_id, new_plate)
        if clash:
            return False
    with get_conn() as conn:
        conn.execute(
            "UPDATE clients SET full_name=?, phone=? WHERE id=?",
            (owner_name, owner_phone, car["client_id"])
        )
        conn.execute(
            "UPDATE cars SET plate_number=?, car_brand=?, car_model=? WHERE id=? AND shop_id=?",
            (new_plate, car_brand, car_model, car["id"], shop_id)
        )
        conn.commit()
    return True


@_serialized
def change_car_owner(shop_id: int, plate: str, owner_name: str, owner_phone: str = None) -> dict:
    """Машину продали: переводит её на нового владельца. История обслуживания
    остаётся у машины (она нужна и новому владельцу), а прежний владелец
    остаётся в базе со своими другими машинами и своим Telegram — напоминания
    по этой машине ему больше не приходят.
    Возвращает {"ok": True} или {"ok": False, "error": код}:
    not_found — машины нет у этой точки; same_owner — указан телефон
    нынешнего владельца; has_debt — у машины непогашенный долг прежнего
    владельца (напоминания о нём ушли бы новому — сначала закрыть долг)."""
    car = find_car(shop_id, plate)
    if not car:
        return {"ok": False, "error": "not_found"}
    owner_phone = (owner_phone or "").strip() or None
    with get_conn() as conn:
        old = conn.execute("SELECT phone FROM clients WHERE id=?", (car["client_id"],)).fetchone()
        debt = conn.execute(
            "SELECT 1 FROM installment_plans WHERE car_id=? AND shop_id=? AND status='active'",
            (car["id"], shop_id)
        ).fetchone()
    if owner_phone and old and (old["phone"] or "").strip() == owner_phone:
        return {"ok": False, "error": "same_owner"}
    if debt:
        return {"ok": False, "error": "has_debt"}
    client = get_or_create_client(shop_id, owner_name, owner_phone)
    with get_conn() as conn:
        conn.execute("UPDATE cars SET client_id=? WHERE id=? AND shop_id=?", (client["id"], car["id"], shop_id))
        # счётчик напоминаний начинаем заново — новому владельцу ещё ничего не слали
        conn.execute("UPDATE oil_changes SET reminder_count=0, last_reminder_date=NULL "
                     "WHERE car_id=? AND status='active'", (car["id"],))
        conn.commit()
    return {"ok": True}


@_serialized
def delete_car_completely(shop_id: int, plate: str) -> bool:
    """Полностью удаляет машину этой точки: саму машину, всю её историю
    замен, и связанные с ней планы рассрочки вместе с платежами по ним.
    Клиент (владелец) не удаляется — у него может быть другая машина."""
    car = find_car(shop_id, plate)
    if not car:
        return False
    with get_conn() as conn:
        plan_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM installment_plans WHERE car_id=? AND shop_id=?", (car["id"], shop_id)
        ).fetchall()]
        for pid in plan_ids:
            conn.execute("DELETE FROM installment_payments WHERE plan_id=?", (pid,))
        conn.execute("DELETE FROM installment_plans WHERE car_id=? AND shop_id=?", (car["id"], shop_id))
        conn.execute("DELETE FROM oil_changes WHERE car_id=?", (car["id"],))
        conn.execute("DELETE FROM cars WHERE id=? AND shop_id=?", (car["id"], shop_id))
        conn.commit()
    return True


@_serialized
def create_or_update_car(shop_id: int, plate_number: str, client_id: int, car_brand: str = None, car_model: str = None):
    plate_number = normalize_plate(plate_number)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM cars WHERE shop_id=? AND plate_number=?", (shop_id, plate_number)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE cars SET car_brand=COALESCE(?, car_brand), car_model=COALESCE(?, car_model) WHERE id=?",
                (car_brand, car_model, existing["id"])
            )
            conn.commit()
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO cars (shop_id, plate_number, client_id, car_brand, car_model, passport_token) VALUES (?, ?, ?, ?, ?, ?)",
                (shop_id, plate_number, client_id, car_brand, car_model, secrets.token_urlsafe(16))
            )
            conn.commit()
            return cur.lastrowid


def get_car_history(shop_id: int, plate_number: str):
    plate_number = normalize_plate(plate_number)
    with get_conn() as conn:
        row = conn.execute("""
            SELECT c.*, cl.full_name as owner_name, cl.phone as owner_phone,
                   cl.link_token, cl.telegram_id
            FROM cars c JOIN clients cl ON cl.id = c.client_id
            WHERE c.shop_id=? AND c.plate_number=?
        """, (shop_id, plate_number)).fetchone()
        if not row:
            return None, []
        history = conn.execute(
            "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date DESC, id DESC",
            (row["id"],)
        ).fetchall()
        return dict(row), [dict(h) for h in history]


def get_cross_network_history(plate: str, exclude_shop_id: int):
    """История этой машины на ДРУГИХ точках платформы (не текущей) — по
    госномеру, между вообще всеми точками, независимо от владельца.
    Сознательно БЕЗ цены — только дата, пробег, что делали: стоимость
    услуги остаётся внутренним делом каждой отдельной точки, а факт и
    состав обслуживания — общая история самой машины. Доступно
    автоматически всем ролям точки (владелец/филиал/сотрудник), явного
    согласия клиента не требуется — решение принято осознанно, риск
    минимален, раз не передаются ни телефон, ни деньги."""
    plate = normalize_plate(plate)
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.shop_name, oc.change_date, oc.mileage, oc.service_type, oc.items_json, oc.notes
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN shops s ON s.id = c.shop_id
            WHERE c.plate_number = ? AND c.shop_id != ?
            ORDER BY oc.change_date DESC, oc.id DESC
        """, (plate, exclude_shop_id)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # в items_json чужой точки лежат её цены продажи и закупки — наружу
        # отдаём только ЧТО делали (позиция, марка, количество), без денег
        if d.get("items_json"):
            try:
                items = json.loads(d["items_json"]) or []
                d["items_json"] = json.dumps([
                    {k: it.get(k) for k in ("key", "name", "brand", "qty", "unit") if it.get(k) is not None}
                    for it in items
                ], ensure_ascii=False)
            except (TypeError, ValueError):
                d["items_json"] = None
        out.append(d)
    return out


def get_car_by_passport_token(token: str):
    """Машина по токену сервисного паспорта — для публичной страницы, без
    входа в систему. Специально НЕ отдаёт телефон владельца и внутренние
    ID — это публичная ссылка, её может открыть кто угодно (например,
    покупатель машины), только то, что нужно для подтверждения истории
    обслуживания."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT c.plate_number, c.car_brand, c.car_model, c.passport_token,
                   cl.full_name as owner_name, s.shop_name, s.id as shop_id, c.id as car_id
            FROM cars c
            JOIN clients cl ON cl.id = c.client_id
            JOIN shops s ON s.id = c.shop_id
            WHERE c.passport_token=?
        """, (token,)).fetchone()
        if not row:
            return None, []
        history = conn.execute(
            "SELECT change_date, mileage, service_type, cost, items_json, notes FROM oil_changes "
            "WHERE car_id=? ORDER BY change_date DESC, id DESC",
            (row["car_id"],)
        ).fetchall()
        return dict(row), [dict(h) for h in history]


def get_last_service(car_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date DESC, id DESC LIMIT 1",
            (car_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_cars_overview(shop_id: int):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                c.id as car_id, c.plate_number, c.car_brand, c.car_model,
                cl.full_name as owner_name, cl.phone as owner_phone,
                cl.link_token, cl.telegram_id, cl.id as client_id,
                oc.change_date, oc.mileage, oc.service_type, oc.oil_brand,
                oc.next_change_date, oc.next_mileage, oc.cost
            FROM cars c JOIN clients cl ON cl.id = c.client_id
            LEFT JOIN oil_changes oc ON oc.id = (
                SELECT id FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1)
            WHERE c.shop_id=?
            ORDER BY c.created_at DESC
        """, (shop_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------- Замены масла / обслуживание ----------

@_serialized
def add_oil_change(car_id: int, mileage, service_type: str, oil_brand: str, filter_changed: bool,
                    cost, interval_value: int, interval_unit: str = "months", notes: str = "",
                    next_mileage=None, items=None, cash_amount=None, card_amount=None):
    """items (необязательно) — детализированный список позиций вида
    [{"name": "Моторное масло", "brand": "MITANOL", "unit_price": 45000, "qty": 4, "total": 180000}, ...]
    Если передан — стоимость и итоговое описание считаются по нему, а service_type/oil_brand/cost
    выше игнорируются (оставлены для обратной совместимости со старым простым способом внесения,
    которым по-прежнему пользуется бот в Telegram).
    cash_amount/card_amount — разбивка оплаты (сколько наличными, сколько картой). Если не переданы —
    вся сумма считается наличными (обратная совместимость со старыми вызовами и ботом)."""
    change_date = datetime.now().strftime("%Y-%m-%d")
    if interval_value:
        if interval_unit == "days":
            next_date = (datetime.now() + timedelta(days=interval_value)).strftime("%Y-%m-%d")
        else:
            next_date = (datetime.now() + relativedelta(months=interval_value)).strftime("%Y-%m-%d")
    else:
        next_date = None

    items_json = None
    stock_moves = []  # (product_id, qty) — списываются ниже в ОДНОЙ транзакции с самой записью
    if items:
        with get_conn() as _conn:
            car_row = _conn.execute("SELECT shop_id FROM cars WHERE id=?", (car_id,)).fetchone()
        item_shop_id = car_row["shop_id"] if car_row else None
        for item in items:
            pid = item.get("product_id")
            if pid and item_shop_id:
                product = get_product(pid, item_shop_id)
                if product:
                    # цена закупки — всегда со склада на момент продажи, не из запроса
                    item["cost_price"] = product.get("purchase_price")
                    stock_moves.append((pid, item.get("qty") or 0))
                else:
                    item["product_id"] = None  # товар не принадлежит этой точке — не связываем со складом
            elif pid:
                item["product_id"] = None
        items_json = json.dumps(items, ensure_ascii=False)
        cost = round(sum(i.get("total", 0) for i in items))
        names = [i["name"] for i in items]
        service_type = ", ".join(names) if names else "Обслуживание"
        motor_oil = next((i for i in items if i.get("key") == "fluid_0"), None)
        oil_brand = motor_oil["brand"] if motor_oil and motor_oil.get("brand") else None
        filter_changed = any((i.get("key") or "").startswith("filter_") for i in items)

    if cash_amount is None and card_amount is None:
        cash_amount, card_amount = cost, 0
    else:
        cash_amount = cash_amount or 0
        card_amount = card_amount or 0

    with get_conn() as conn:
        # всё ниже — одна транзакция: либо сохранится и запись, и списание
        # со склада, либо ничего (раньше склад списывался отдельно и при сбое
        # сохранения записи товар «пропадал»)
        for pid, qty in stock_moves:
            conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (qty, pid))
        conn.execute("UPDATE oil_changes SET status='done' WHERE car_id=? AND status='active'", (car_id,))
        cur = conn.execute("""
            INSERT INTO oil_changes
                (car_id, change_date, mileage, service_type, oil_brand, filter_changed, cost,
                 cash_amount, card_amount, interval_months, interval_unit, next_change_date,
                 next_mileage, items_json, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (car_id, change_date, mileage, service_type, oil_brand, int(bool(filter_changed)), cost,
              cash_amount, card_amount, interval_value, interval_unit, next_date, next_mileage, items_json, notes))
        conn.commit()
        return cur.lastrowid, next_date


def get_oil_change_for_shop(oc_id: int, shop_id: int):
    """Запись обслуживания, только если она принадлежит указанной точке —
    проверка прав перед редактированием/удалением."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT oc.* FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            WHERE oc.id=? AND c.shop_id=?
        """, (oc_id, shop_id)).fetchone()
        return dict(row) if row else None


@_serialized
def update_oil_change(oc_id: int, shop_id: int, change_date=None, mileage=None, next_mileage=None,
                       cost=None, interval_value=None, interval_unit=None, notes=None, items=None,
                       cash_amount=None, card_amount=None):
    """Редактирует уже сохранённую запись. Если передан НЕПУСТОЙ items — полностью
    пересчитывает стоимость, детализацию (жидкости/фильтры) и итоговое
    описание по нему (так же, как при создании новой записи); cost, которое
    также могло быть передано отдельно, в этом случае игнорируется — сумма
    считается по позициям. Пустой список ([]) или None в items трактуются
    ОДИНАКОВО — «позиции не трогать» (чтобы безобидное редактирование, скажем,
    только next_mileage у старой «простой» записи без позиций не стирало ей
    случайно стоимость и марку масла). Возвращает True, если запись найдена и
    принадлежит точке — иначе False (ничего не меняет)."""
    existing = get_oil_change_for_shop(oc_id, shop_id)
    if not existing:
        return False

    fields = {}
    if change_date is not None:
        fields["change_date"] = change_date
    if mileage is not None:
        fields["mileage"] = mileage
    if next_mileage is not None:
        fields["next_mileage"] = next_mileage
    if notes is not None:
        fields["notes"] = notes

    if items:
        # Склад: сначала возвращаем то, что было списано старыми позициями
        # (если товар всё ещё существует и принадлежит этой точке), потом
        # списываем заново по новым позициям — так редактирование количества
        # или замена бренда правильно отражается на остатках, а не задваивает
        # списание.
        old_items = json.loads(existing["items_json"]) if existing.get("items_json") else []
        for old_item in old_items:
            pid = old_item.get("product_id")
            if pid and get_product(pid, shop_id, active_only=False):
                adjust_stock(pid, -(old_item.get("qty") or 0))
        # цена закупки уже проданного товара не должна меняться задним числом:
        # если позиция была в записи раньше — оставляем её прежний cost_price,
        # текущую цену склада берём только для новых позиций
        old_cost = {o.get("product_id"): o.get("cost_price") for o in old_items
                    if o.get("product_id") and "cost_price" in o}
        for item in items:
            pid = item.get("product_id")
            if pid:
                product = get_product(pid, shop_id)
                if product:
                    item["cost_price"] = old_cost[pid] if pid in old_cost else product.get("purchase_price")
                    adjust_stock(pid, item.get("qty") or 0)
                else:
                    item["product_id"] = None

        fields["items_json"] = json.dumps(items, ensure_ascii=False)
        fields["cost"] = round(sum(i.get("total", 0) for i in items))
        names = [i["name"] for i in items]
        fields["service_type"] = ", ".join(names) if names else "Обслуживание"
        motor_oil = next((i for i in items if i.get("key") == "fluid_0"), None)
        fields["oil_brand"] = motor_oil["brand"] if motor_oil and motor_oil.get("brand") else None
        fields["filter_changed"] = int(any((i.get("key") or "").startswith("filter_") for i in items))
    elif cost is not None:
        fields["cost"] = cost

    if cash_amount is not None:
        fields["cash_amount"] = cash_amount
    if card_amount is not None:
        fields["card_amount"] = card_amount

    if interval_value is not None or interval_unit is not None:
        final_value = interval_value if interval_value is not None else existing["interval_months"]
        final_unit = interval_unit if interval_unit is not None else existing["interval_unit"]
        base_date_str = fields.get("change_date", existing["change_date"])
        base_date = datetime.strptime(base_date_str, "%Y-%m-%d")
        if final_value:
            if final_unit == "days":
                next_date = (base_date + timedelta(days=final_value)).strftime("%Y-%m-%d")
            else:
                next_date = (base_date + relativedelta(months=final_value)).strftime("%Y-%m-%d")
        else:
            next_date = None
        fields["interval_months"] = final_value
        fields["interval_unit"] = final_unit
        fields["next_change_date"] = next_date

    if not fields:
        return True

    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE oil_changes SET {set_clause} WHERE id=?", (*fields.values(), oc_id))
        conn.commit()
    return True


@_serialized
def delete_oil_change(oc_id: int, shop_id: int):
    """Удаляет запись (только если она принадлежит указанной точке). Товары,
    списанные со склада этой записью, возвращаются обратно на остаток. Если
    удалённая запись была 'active' (текущей) — делает активной следующую по
    свежести оставшуюся запись той же машины, чтобы напоминания продолжали
    работать корректно. Возвращает True, если запись была найдена и удалена."""
    existing = get_oil_change_for_shop(oc_id, shop_id)
    if not existing:
        return False

    returns = []
    if existing.get("items_json"):
        for item in json.loads(existing["items_json"]):
            pid = item.get("product_id")
            if pid and get_product(pid, shop_id, active_only=False):
                returns.append((pid, item.get("qty") or 0))

    with get_conn() as conn:
        cur = conn.execute("DELETE FROM oil_changes WHERE id=?", (oc_id,))
        if cur.rowcount == 0:
            return False  # уже удалена (например, нажали «удалить» с двух телефонов)
        for pid, qty in returns:
            conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id=?", (qty, pid))
        if existing["status"] == "active":
            next_row = conn.execute(
                "SELECT id FROM oil_changes WHERE car_id=? ORDER BY change_date DESC, id DESC LIMIT 1",
                (existing["car_id"],)
            ).fetchone()
            if next_row:
                conn.execute("UPDATE oil_changes SET status='active' WHERE id=?", (next_row["id"],))
        conn.commit()
    return True


@_serialized
def create_installment_plan(shop_id: int, car_id: int, total_amount: int, installment_amount: int,
                             interval_days: int, oil_change_id: int = None):
    """Оформляет остаток суммы в рассрочку — первый платёж ожидается через
    interval_days от сегодня. Возвращает созданный план."""
    next_due = (datetime.now() + timedelta(days=interval_days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO installment_plans
                (shop_id, car_id, oil_change_id, total_amount, paid_amount, installment_amount,
                 interval_days, next_due_date, status)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, 'active')
        """, (shop_id, car_id, oil_change_id, total_amount, installment_amount, interval_days, next_due))
        conn.commit()
        return get_installment_plan(cur.lastrowid, shop_id)


def get_installment_plan(plan_id: int, shop_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM installment_plans WHERE id=? AND shop_id=?", (plan_id, shop_id)).fetchone()
        return dict(row) if row else None


def get_active_debts(shop_id: int):
    """Все непогашенные долги этой точки — с именем клиента, машиной и
    остатком, для вкладки 'Долги'. Просроченные (next_due_date в прошлом)
    помечаются отдельным полем is_overdue."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT ip.*, c.plate_number, c.car_brand, c.car_model,
                   cl.full_name as owner_name, cl.phone as owner_phone, cl.telegram_id
            FROM installment_plans ip
            JOIN cars c ON c.id = ip.car_id
            JOIN clients cl ON cl.id = c.client_id
            WHERE ip.shop_id=? AND ip.status='active'
            ORDER BY ip.next_due_date ASC
        """, (shop_id,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["remaining"] = d["total_amount"] - d["paid_amount"]
            d["is_overdue"] = d["next_due_date"] < today
            result.append(d)
        return result


def get_debt_summary(shop_id: int) -> dict:
    """Краткая сводка по долгам для dashboard — сколько всего должны и
    сколько просрочено, без деталей по каждому клиенту отдельно."""
    debts = get_active_debts(shop_id)
    return {
        "total_remaining": sum(d["remaining"] for d in debts),
        "count": len(debts),
        "overdue_count": sum(1 for d in debts if d["is_overdue"]),
    }


def get_daily_revenue(shop_id: int, days: int = 30):
    """Выручка по дням за последние `days` дней — для графика динамики на
    dashboard. Дни без единой продажи всё равно включены в список с total=0,
    чтобы график не 'перепрыгивал' через пропуски."""
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.change_date as date, COALESCE(SUM(oc.cost), 0) as total
            FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.cost IS NOT NULL AND oc.change_date >= ?
            GROUP BY oc.change_date
        """, (shop_id, start_date)).fetchall()
    by_date = {r["date"]: r["total"] for r in rows}
    result = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        result.append({"date": d, "total": by_date.get(d, 0)})
    return result


def get_daily_revenue_range(shop_id: int, date_from: str, date_to: str):
    """Выручка по дням за произвольный период (включительно с обеих сторон)
    — для графика динамики, что на dashboard (30 дней), что при выборе
    своих дат. Дни без единой продажи всё равно включены в список с
    total=0, чтобы график не 'перепрыгивал' через пропуски."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.change_date as date, COALESCE(SUM(oc.cost), 0) as total, COUNT(*) as cnt
            FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.cost IS NOT NULL AND oc.change_date >= ? AND oc.change_date <= ?
            GROUP BY oc.change_date
        """, (shop_id, date_from, date_to)).fetchall()
    by_date = {r["date"]: r["total"] for r in rows}
    count_by_date = {r["date"]: r["cnt"] for r in rows}
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    result = []
    d = start
    while d <= end:
        d_str = d.strftime("%Y-%m-%d")
        result.append({"date": d_str, "total": by_date.get(d_str, 0), "count": count_by_date.get(d_str, 0)})
        d += timedelta(days=1)
    return result


def get_daily_revenue(shop_id: int, days: int = 30):
    """Выручка по дням за последние `days` дней — обёртка над
    get_daily_revenue_range с датами, посчитанными от сегодня."""
    date_from = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    return get_daily_revenue_range(shop_id, date_from, date_to)


def get_top_products_by_qty_range(shop_id: int, date_from: str, date_to: str, limit: int = 5):
    """Топ проданных товаров за произвольный период, по количеству (литры
    или штуки в зависимости от товара) — что берут чаще всего. Считается по
    items_json каждой записи, так как это единственное место, где хранится
    детализация по позициям."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.items_json FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.change_date >= ? AND oc.change_date <= ? AND oc.items_json IS NOT NULL
        """, (shop_id, date_from, date_to)).fetchall()
    totals = {}
    for r in rows:
        try:
            items = json.loads(r["items_json"])
        except (TypeError, ValueError):
            continue
        for item in items:
            name = item.get("name")
            if not name:
                continue
            qty = item.get("qty") or 0
            totals[name] = totals.get(name, 0) + qty
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"name": name, "qty": round(qty, 2)} for name, qty in ranked]


def get_top_products_by_qty(shop_id: int, days: int = 30, limit: int = 5):
    """Топ проданных товаров за последние `days` дней — обёртка над
    get_top_products_by_qty_range с датами, посчитанными от сегодня."""
    date_from = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    return get_top_products_by_qty_range(shop_id, date_from, date_to, limit=limit)


def get_top_brands_for_category_range(shop_id: int, category_name: str, date_from: str, date_to: str, limit: int = 10):
    """Топ-10 брендов ВНУТРИ одной категории за произвольный период —
    основа, используется и для dashboard (30 дней), и для выбора своих дат."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.items_json FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.change_date >= ? AND oc.change_date <= ? AND oc.items_json IS NOT NULL
        """, (shop_id, date_from, date_to)).fetchall()
    totals = {}
    for r in rows:
        try:
            items = json.loads(r["items_json"])
        except (TypeError, ValueError):
            continue
        for item in items:
            if item.get("name") != category_name:
                continue
            brand = item.get("brand") or "без марки"
            qty = item.get("qty") or 0
            totals[brand] = totals.get(brand, 0) + qty
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"name": brand, "qty": round(qty, 2)} for brand, qty in ranked]


BRAND_CATEGORY_ORDER = ["fluid_0", "fluid_1", "fluid_2", "fluid_3", "fluid_4",
                        "filter_0", "filter_1", "filter_2", "filter_3", "other"]
_FLUID_KEYS = {"fluid_0", "fluid_1", "fluid_2", "fluid_3", "fluid_4"}


def _item_category_key(item: dict, name_to_key: dict):
    """Ключ категории позиции. У новых записей он лежит в item['key'];
    у старых его нет — тогда узнаём категорию по названию (на русском или
    узбекском, в зависимости от языка, на котором сохраняли)."""
    key = item.get("key")
    if key in ("other", "other_stock"):
        return "other"
    if key in BRAND_CATEGORY_ORDER:
        return key
    name = (item.get("name") or "").strip()
    if name in name_to_key:
        return name_to_key[name]
    return "other"


def get_brand_breakdown(shop_id, date_from: str, date_to: str, limit: int = 10) -> dict:
    """Какие бренды продаются: по каждой категории (моторное масло, АКПП,
    антифриз, фильтры...) — топ-N брендов по объёму (литры/штуки) + всё
    остальное одной строкой «Остальные». Для «Прочего» бренда нет, поэтому
    там группируем по названию товара и ранжируем по выручке.
    Написание бренда нормализуем: «Mitanol», «MITANOL » и «mitanol» — один бренд."""
    import i18n
    # можно передать одну точку или список (для сводки по сети филиалов)
    shop_ids = list(shop_id) if isinstance(shop_id, (list, tuple)) else [shop_id]
    name_to_key = {}
    for lang_texts in i18n.TEXTS.values():
        for k in BRAND_CATEGORY_ORDER:
            if k in lang_texts:
                name_to_key[lang_texts[k]] = k
    other_prefixes = tuple(f"{t.get('other_prefix', '')}:" for t in i18n.TEXTS.values())

    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT oc.id, oc.items_json FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id IN ({",".join("?" * len(shop_ids))})
              AND oc.change_date >= ? AND oc.change_date <= ? AND oc.items_json IS NOT NULL
        """, (*shop_ids, date_from, date_to)).fetchall()

    # cats[key][norm] = {"qty", "sum", "visits": set, "spellings": {написание: сколько раз}}
    cats = {}
    for r in rows:
        try:
            items = json.loads(r["items_json"])
        except (TypeError, ValueError):
            continue
        for item in items or []:
            cat = _item_category_key(item, name_to_key)
            if cat == "other":
                label = (item.get("name") or "").strip()
                for pref in other_prefixes:
                    if label.startswith(pref):
                        label = label[len(pref):].strip()
                        break
            else:
                label = (item.get("brand") or "").strip()
            label = " ".join(label.split())
            norm = label.upper()
            b = cats.setdefault(cat, {}).setdefault(norm, {"qty": 0, "sum": 0, "visits": set(), "spellings": {}})
            b["qty"] += item.get("qty") or 0
            b["sum"] += item.get("total") or 0
            b["visits"].add(r["id"])
            if label:
                b["spellings"][label] = b["spellings"].get(label, 0) + 1

    result = []
    for cat in BRAND_CATEGORY_ORDER:
        brands = cats.get(cat)
        if not brands:
            continue
        metric = "sum" if cat == "other" else "qty"
        ranked = sorted(brands.items(), key=lambda kv: kv[1][metric], reverse=True)
        total_qty = sum(b["qty"] for b in brands.values())
        total_sum = sum(b["sum"] for b in brands.values())
        total_metric = total_sum if metric == "sum" else total_qty

        def share(v):
            return round(v / total_metric * 100, 1) if total_metric else 0

        top = []
        for norm, b in ranked[:limit]:
            display = max(b["spellings"].items(), key=lambda kv: kv[1])[0] if b["spellings"] else ""
            top.append({
                "name": display, "no_brand": not norm,
                "qty": round(b["qty"], 2), "sum": round(b["sum"]), "visits": len(b["visits"]),
                "share": share(b[metric]),
            })
        rest = ranked[limit:]
        others = None
        if rest:
            o_qty = sum(b["qty"] for _, b in rest)
            o_sum = sum(b["sum"] for _, b in rest)
            others = {"count": len(rest), "qty": round(o_qty, 2), "sum": round(o_sum),
                      "share": share(o_sum if metric == "sum" else o_qty)}
        result.append({
            "key": cat,
            "unit": "l" if cat in _FLUID_KEYS else ("pc" if cat.startswith("filter_") else ""),
            "metric": metric,
            "total_qty": round(total_qty, 2), "total_sum": round(total_sum),
            "brand_count": len(brands),
            "top": top, "others": others,
        })
    return {"categories": result}


def get_top_brands_for_category(shop_id: int, category_name: str, days: int = 30, limit: int = 10):
    """Топ-10 брендов ВНУТРИ одной категории (например, внутри 'Моторное
    масло' — какие марки берут чаще: MITANOL 5W-30, MATTEX и т.д.). Раскрытие
    по клику на категорию в dashboard, а не отдельный плоский список."""
    date_from = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    return get_top_brands_for_category_range(shop_id, category_name, date_from, date_to, limit=limit)


def get_low_stock_products(shop_id: int, threshold: float = 50):
    """Все товары, чей остаток меньше `threshold` (по умолчанию 50 — что в
    литрах, что в штуках), а не только 3-5 самых малых — чтобы не пропустить
    никого, кто реально заканчивается. Отсортировано по возрастанию остатка,
    чтобы самое срочное было сверху."""
    products = list_products(shop_id)
    low = [p for p in products if p["stock_qty"] < threshold]
    return sorted(low, key=lambda p: p["stock_qty"])


@_serialized
def log_installment_payment(plan_id: int, shop_id: int, amount: int, paid_date: str = None):
    """Отмечает поступивший платёж по долгу — увеличивает paid_amount,
    сдвигает следующую дату на interval_days вперёд, и закрывает план,
    если долг полностью погашен. Возвращает обновлённый план или None,
    если план не найден (или принадлежит другой точке)."""
    plan = get_installment_plan(plan_id, shop_id)
    if not plan:
        return None
    paid_date = paid_date or datetime.now().strftime("%Y-%m-%d")
    new_paid = plan["paid_amount"] + amount
    new_status = "completed" if new_paid >= plan["total_amount"] else "active"
    next_due = (datetime.strptime(plan["next_due_date"], "%Y-%m-%d") + timedelta(days=plan["interval_days"])).strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO installment_payments (plan_id, amount, paid_date) VALUES (?, ?, ?)",
            (plan_id, amount, paid_date)
        )
        conn.execute(
            "UPDATE installment_plans SET paid_amount=paid_amount+?, next_due_date=?, status=? WHERE id=? AND shop_id=?",
            (amount, next_due, new_status, plan_id, shop_id)
        )
        conn.commit()
    return get_installment_plan(plan_id, shop_id)


def get_installment_payments(plan_id: int, shop_id: int):
    """История платежей по конкретному плану — только если план
    принадлежит указанной точке."""
    if not get_installment_plan(plan_id, shop_id):
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM installment_payments WHERE plan_id=? ORDER BY paid_date DESC, id DESC", (plan_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_due_installment_reminders():
    """Для фонового задания бота — все активные планы по ВСЕМ точкам, чей
    следующий платёж наступил или просрочен, и сегодня ещё не напоминали.
    Возвращает данные клиента/владельца точки, нужные для отправки
    напоминания в Telegram."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT ip.*, c.plate_number, cl.full_name as owner_name, cl.telegram_id,
                   s.notify_telegram_id, s.shop_name, s.language
            FROM installment_plans ip
            JOIN cars c ON c.id = ip.car_id
            JOIN clients cl ON cl.id = c.client_id
            JOIN shops s ON s.id = ip.shop_id
            WHERE ip.status='active' AND ip.next_due_date <= ?
              AND (ip.last_reminder_date IS NULL OR ip.last_reminder_date != ?)
        """, (today, today)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["remaining"] = d["total_amount"] - d["paid_amount"]
            d["is_overdue"] = d["next_due_date"] < today
            result.append(d)
        return result


@_serialized
def mark_installment_reminded(plan_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE installment_plans SET last_reminder_date=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d"), plan_id)
        )
        conn.commit()


EXPENSE_PRESET_CATEGORIES = ["Аренда", "Коммунальные услуги", "Зарплата", "Реклама", "Транспорт", "Прочее"]


def _compute_expense_due_date(day_of_month: int, from_date: datetime = None) -> str:
    """Ближайшая дата с этим числом месяца, начиная с from_date (или
    сегодня) — если число уже прошло в этом месяце, берём следующий."""
    base = from_date or datetime.now()
    day_of_month = max(1, min(28, day_of_month))
    candidate = base.replace(day=day_of_month, hour=0, minute=0, second=0, microsecond=0)
    if candidate.date() < base.date():
        if base.month == 12:
            candidate = candidate.replace(year=base.year + 1, month=1)
        else:
            candidate = candidate.replace(month=base.month + 1)
    return candidate.strftime("%Y-%m-%d")


@_serialized
def create_recurring_expense(shop_id: int, category: str, name: str, amount: int, day_of_month: int):
    """Повторяющийся расход (аренда, зарплата и т.п.) — раз в месяц, в
    указанное число, с напоминанием через бота. Возвращает созданную запись."""
    next_due = _compute_expense_due_date(day_of_month)
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO recurring_expenses (shop_id, category, name, amount, day_of_month, next_due_date, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
        """, (shop_id, category, name, amount, max(1, min(28, day_of_month)), next_due))
        conn.commit()
        return get_recurring_expense(cur.lastrowid, shop_id)


def get_recurring_expense(expense_id: int, shop_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM recurring_expenses WHERE id=? AND shop_id=?", (expense_id, shop_id)
        ).fetchone()
        return dict(row) if row else None


def get_recurring_expenses(shop_id: int):
    """Все активные повторяющиеся расходы точки — для управления (пауза,
    удаление) и чтобы видеть, что запланировано."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM recurring_expenses WHERE shop_id=? AND status='active' ORDER BY day_of_month",
            (shop_id,)
        ).fetchall()
        return [dict(r) for r in rows]


@_serialized
def delete_recurring_expense(expense_id: int, shop_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM recurring_expenses WHERE id=? AND shop_id=?", (expense_id, shop_id))
        conn.commit()
        return cur.rowcount > 0


@_serialized
def log_expense(shop_id: int, category: str, name: str, amount: int, expense_date: str = None,
                 recurring_expense_id: int = None):
    """Записывает фактически понесённый расход — разовый или как отметку
    оплаты повторяющегося (тогда recurring_expense_id сдвигает следующую
    дату на месяц вперёд от текущей, а не от сегодня — чтобы ранняя или
    поздняя оплата не сбивала график)."""
    expense_date = expense_date or datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO expense_entries (shop_id, recurring_expense_id, category, name, amount, expense_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (shop_id, recurring_expense_id, category, name, amount, expense_date))
        if recurring_expense_id:
            plan = get_recurring_expense(recurring_expense_id, shop_id)
            if plan:
                next_due = datetime.strptime(plan["next_due_date"], "%Y-%m-%d")
                if next_due.month == 12:
                    next_due = next_due.replace(year=next_due.year + 1, month=1, day=plan["day_of_month"])
                else:
                    next_due = next_due.replace(month=next_due.month + 1, day=plan["day_of_month"])
                conn.execute(
                    "UPDATE recurring_expenses SET next_due_date=? WHERE id=?",
                    (next_due.strftime("%Y-%m-%d"), recurring_expense_id)
                )
        conn.commit()


def get_expenses(shop_id: int, date_from: str, date_to: str):
    """Журнал фактических расходов за период (включительно с обеих сторон)."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM expense_entries WHERE shop_id=? AND expense_date >= ? AND expense_date <= ?
            ORDER BY expense_date DESC, id DESC
        """, (shop_id, date_from, date_to)).fetchall()
        return [dict(r) for r in rows]


def get_expense_entry(entry_id: int, shop_id: int):
    """Одна запись журнала расходов — только если она принадлежит этой точке."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM expense_entries WHERE id=? AND shop_id=?", (entry_id, shop_id)
        ).fetchone()
        return dict(row) if row else None


@_serialized
def update_expense_entry(entry_id: int, shop_id: int, category: str, name: str, amount: int, expense_date: str) -> bool:
    """Редактирует уже внесённую запись расхода — сумму, категорию, название,
    дату. Не трогает связь с повторяющимся расходом (recurring_expense_id),
    если она была — только сами данные записи."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE expense_entries SET category=?, name=?, amount=?, expense_date=? WHERE id=? AND shop_id=?",
            (category, name, amount, expense_date, entry_id, shop_id)
        )
        conn.commit()
        return cur.rowcount > 0


@_serialized
def delete_expense_entry(entry_id: int, shop_id: int) -> bool:
    """Удаляет запись из журнала — только если она принадлежит этой точке.
    Если запись была отметкой оплаты повторяющегося расхода, сам
    повторяющийся расход и его график остаются нетронутыми — удаляется
    только эта одна запись из журнала."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM expense_entries WHERE id=? AND shop_id=?", (entry_id, shop_id))
        conn.commit()
        return cur.rowcount > 0


def get_expense_summary(shop_id: int, days: int = 30) -> dict:
    """Сумма расходов за последние `days` дней — итого и разбивка по
    категориям, для dashboard."""
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, amount FROM expense_entries WHERE shop_id=? AND expense_date >= ?",
            (shop_id, start_date)
        ).fetchall()
    by_category = {}
    total = 0
    for r in rows:
        by_category[r["category"]] = by_category.get(r["category"], 0) + r["amount"]
        total += r["amount"]
    breakdown = sorted(
        [{"category": k, "amount": v} for k, v in by_category.items()],
        key=lambda x: x["amount"], reverse=True
    )
    return {"total": total, "breakdown": breakdown}


def get_due_recurring_expenses():
    """Для фонового задания бота — все активные повторяющиеся расходы по
    ВСЕМ точкам, чей срок наступил или просрочен, и сегодня ещё не
    напоминали. Напоминание уходит владельцу (клиент тут ни при чём —
    расходы точки его не касаются)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT re.*, s.notify_telegram_id, s.shop_name, s.language
            FROM recurring_expenses re JOIN shops s ON s.id = re.shop_id
            WHERE re.status='active' AND re.next_due_date <= ?
              AND (re.last_reminder_date IS NULL OR re.last_reminder_date != ?)
        """, (today, today)).fetchall()
        return [dict(r) for r in rows]


@_serialized
def mark_expense_reminded(expense_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE recurring_expenses SET last_reminder_date=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d"), expense_id)
        )
        conn.commit()


def get_net_profit_30d(shop_id: int) -> dict:
    """Прибыль по марже на масле минус прочие расходы (аренда, зарплата и
    т.п.) за последние 30 дней — 'настоящая' прибыль точки целиком, не
    только по продаже масла."""
    start_date = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    br = get_profit_breakdown(shop_id, start_date, today)
    expenses = get_expense_summary(shop_id, days=30)
    return {
        "oil_profit": br["goods_profit"],
        "services": br["services"],
        "unpriced": br["unpriced"],
        "expenses_total": expenses["total"],
        "net_profit": br["profit"] - expenses["total"],
    }


def get_due_reminders():
    """Напоминания по ВСЕМ точкам разом (каждая запись несёт свой shop_id и
    название точки — фоновая задача одна на весь бот, но данные каждой
    записи принадлежат только её собственной точке). Возвращает клиентов и
    с Telegram, и без — какой канал использовать (Telegram/SMS/ничего),
    решает вызывающий код в боте."""
    today = datetime.now().strftime("%Y-%m-%d")
    followup_cutoff = (datetime.now() - timedelta(days=FOLLOWUP_INTERVAL_DAYS)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.*, c.plate_number, c.shop_id, cl.full_name as owner_name, cl.telegram_id,
                   cl.phone as owner_phone, s.shop_name, s.notify_telegram_id, s.language,
                   s.sms_enabled, s.eskiz_email, s.eskiz_password
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN clients cl ON cl.id = c.client_id
            JOIN shops s ON s.id = c.shop_id
            WHERE oc.status='active' AND oc.next_change_date IS NOT NULL AND (
                (oc.reminder_count = 0 AND oc.next_change_date <= ?)
                OR
                (oc.reminder_count > 0 AND oc.reminder_count < ? AND oc.last_reminder_date <= ?)
            )
        """, (today, MAX_FOLLOWUP_REMINDERS, followup_cutoff)).fetchall()
        return [dict(r) for r in rows]


@_serialized
def mark_reminder_sent(oil_change_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "UPDATE oil_changes SET reminder_count = reminder_count + 1, last_reminder_date=? WHERE id=?",
            (today, oil_change_id)
        )
        conn.commit()


@_serialized
def mark_booked(oil_change_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='booked' WHERE id=?", (oil_change_id,))
        conn.commit()


@_serialized
def mark_already_changed_elsewhere(oil_change_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='changed_elsewhere' WHERE id=?", (oil_change_id,))
        conn.commit()


def get_oil_change_with_context(oil_change_id: int):
    """Запись замены + госномер + владелец + данные точки (чтобы уведомить
    именно ту точку, которой принадлежит запись, о брони клиента)."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT oc.*, c.plate_number, c.shop_id, cl.full_name as owner_name, cl.phone as owner_phone,
                   cl.telegram_id as client_telegram_id, s.shop_name, s.notify_telegram_id, s.language
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN clients cl ON cl.id = c.client_id
            JOIN shops s ON s.id = c.shop_id
            WHERE oc.id=?
        """, (oil_change_id,)).fetchone()
        return dict(row) if row else None


# ---------- Рассылки ----------

def get_all_linked_clients(shop_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, telegram_id, full_name FROM clients WHERE shop_id=? AND telegram_id IS NOT NULL",
            (shop_id,)
        ).fetchall()
        return [dict(r) for r in rows]


@_serialized
def create_broadcast(shop_id: int, message: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO broadcasts (shop_id, message, status) VALUES (?, ?, 'pending')", (shop_id, message)
        )
        conn.commit()
        return cur.lastrowid


def get_pending_broadcast():
    """Одна старейшая необработанная рассылка (с любой точки) — фоновая
    задача обрабатывает их по очереди, каждую строго в рамках её shop_id."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM broadcasts WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None


@_serialized
def mark_broadcast_sending(broadcast_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE broadcasts SET status='sending' WHERE id=?", (broadcast_id,))
        conn.commit()


@_serialized
def mark_broadcast_done(broadcast_id: int, sent: int, failed: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE broadcasts SET status='done', total_sent=?, total_failed=?, finished_at=datetime('now') WHERE id=?",
            (sent, failed, broadcast_id)
        )
        conn.commit()


def get_recent_broadcasts(shop_id: int, limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM broadcasts WHERE shop_id=? ORDER BY id DESC LIMIT ?", (shop_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- Экспорт/бэкап (для кнопки «скачать базу» у точки) ----------

def _avg_check(total: int, paid_count: int) -> int:
    """Средний чек = выручка / число ПЛАТНЫХ визитов. Визиты с ценой 0
    (бесплатная проверка, гарантия) не учитываются — иначе они занижали бы
    средний чек, хотя денег не приносили."""
    return round(total / paid_count) if paid_count else 0


def _with_avg(d: dict) -> dict:
    d["avg"] = _avg_check(d["total"], d.get("paid_count", 0))
    return d


def _client_split(conn, shop_id: int, date_from: str, date_to: str) -> dict:
    """Сколько РАЗНЫХ клиентов приезжало за период и кто из них новый.
    Новый = его самый первый визит в эту точку (по любой из его машин)
    попадает внутрь периода. Повторный = он уже бывал здесь раньше.
    Считаются все визиты, даже без цены: тут важен сам человек, а не деньги."""
    row = conn.execute("""
        SELECT COUNT(*) as total,
               COALESCE(SUM(CASE WHEN first_ever >= ? THEN 1 ELSE 0 END), 0) as new_cnt
        FROM (
            SELECT c.client_id, MIN(oc.change_date) as first_ever
            FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id = ?
            GROUP BY c.client_id
            HAVING SUM(CASE WHEN oc.change_date >= ? AND oc.change_date <= ? THEN 1 ELSE 0 END) > 0
        )
    """, (date_from, shop_id, date_from, date_to)).fetchone()
    total = row["total"] or 0
    new = row["new_cnt"] or 0
    return {"total": total, "new": new, "returning": total - new}


def _sum_client_splits(parts) -> dict:
    """Для сети филиалов: клиенты у каждой точки свои, поэтому просто складываем."""
    out = {"total": 0, "new": 0, "returning": 0}
    for p in parts:
        for k in out:
            out[k] += p[k]
    return out


def get_revenue_stats(shop_id: int) -> dict:
    """Выручка и число услуг за сегодня/вчера/эту неделю (с понедельника)/этот
    месяц/этот год — для точки. Считается по дате самой услуги (change_date),
    а не по дате следующей замены."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    year_start = now.strftime("%Y-01-01")

    with get_conn() as conn:
        def agg(date_filter, param):
            row = conn.execute(f"""
                SELECT COALESCE(SUM(oc.cost), 0) as total, COUNT(*) as cnt,
                       COALESCE(SUM(oc.cash_amount), 0) as cash, COALESCE(SUM(oc.card_amount), 0) as card,
                       SUM(CASE WHEN oc.cost > 0 THEN 1 ELSE 0 END) as paid_cnt
                FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
                WHERE c.shop_id=? AND oc.cost IS NOT NULL AND {date_filter}
            """, (shop_id, param)).fetchone()
            return _with_avg({"total": row["total"], "count": row["cnt"], "cash": row["cash"], "card": row["card"],
                              "paid_count": row["paid_cnt"] or 0})

        result = {
            "today": agg("oc.change_date = ?", today),
            "yesterday": agg("oc.change_date = ?", yesterday),
            "week": agg("oc.change_date >= ?", week_start),
            "month": agg("oc.change_date >= ?", month_start),
            "year": agg("oc.change_date >= ?", year_start),
        }
        far_future = "9999-12-31"
        for key, (d_from, d_to) in {
            "today": (today, today),
            "yesterday": (yesterday, yesterday),
            "week": (week_start, far_future),
            "month": (month_start, far_future),
            "year": (year_start, far_future),
        }.items():
            result[key]["clients"] = _client_split(conn, shop_id, d_from, d_to)
        return result


def _pct_change(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _pack_comparison(cur_total, cur_paid, prev_total, prev_paid) -> dict:
    cur_avg = _avg_check(cur_total, cur_paid)
    prev_avg = _avg_check(prev_total, prev_paid)
    return {"current": cur_total, "previous": prev_total, "pct": _pct_change(cur_total, prev_total),
            "paid_current": cur_paid, "paid_previous": prev_paid,
            "avg_current": cur_avg, "avg_previous": prev_avg,
            # если в текущем периоде ещё нет платных визитов — сравнивать нечего
            "avg_pct": _pct_change(cur_avg, prev_avg) if cur_avg else None}


def get_revenue_comparison(shop_id: int) -> dict:
    """Сравнение текущей недели/месяца/года с ПРЕДЫДУЩИМ аналогичным
    периодом — честно, "яблоки к яблокам": раз текущий месяц ещё не
    закончился (например, сегодня 27-е число), сравниваем не с целым
    прошлым месяцем (он был бы больше просто потому что в нём больше дней
    прошло), а с тем же числом дней прошлого месяца — с 1-го по 27-е.
    Так же для недели и года. Возвращает разницу в процентах (None, если
    в прошлом периоде было 0 — делить не на что)."""
    now = datetime.now()

    def total_for(date_from: str, date_to: str):
        """Возвращает (выручка, средний чек) за диапазон."""
        with get_conn() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(oc.cost), 0) as total,
                       SUM(CASE WHEN oc.cost > 0 THEN 1 ELSE 0 END) as paid_cnt
                FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
                WHERE c.shop_id=? AND oc.cost IS NOT NULL AND oc.change_date >= ? AND oc.change_date <= ?
            """, (shop_id, date_from, date_to)).fetchone()
            return row["total"], row["paid_cnt"] or 0

    def pct_change(current: int, previous: int):
        if not previous:
            return None
        return round((current - previous) / previous * 100, 1)

    today_str = now.strftime("%Y-%m-%d")

    # неделя (с понедельника по сегодня) vs та же часть прошлой недели
    week_start = now - timedelta(days=now.weekday())
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = prev_week_start + timedelta(days=now.weekday())
    week_cur = total_for(week_start.strftime("%Y-%m-%d"), today_str)
    week_prev = total_for(prev_week_start.strftime("%Y-%m-%d"), prev_week_end.strftime("%Y-%m-%d"))

    # месяц (с 1-го по сегодняшнее число) vs то же число дней прошлого месяца
    month_start = now.replace(day=1)
    prev_month_end_date = month_start - timedelta(days=1)  # последний день прошлого месяца
    prev_month_start = prev_month_end_date.replace(day=1)
    prev_month_day = min(now.day, prev_month_end_date.day)
    prev_month_end = prev_month_start.replace(day=prev_month_day)
    month_cur = total_for(month_start.strftime("%Y-%m-%d"), today_str)
    month_prev = total_for(prev_month_start.strftime("%Y-%m-%d"), prev_month_end.strftime("%Y-%m-%d"))

    # год (с 1 января по сегодня) vs тот же период прошлого года
    year_start = now.replace(month=1, day=1)
    try:
        prev_year_end = now.replace(year=now.year - 1)
    except ValueError:
        prev_year_end = now.replace(year=now.year - 1, day=28)  # 29 февраля в невисокосном
    prev_year_start = year_start.replace(year=year_start.year - 1)
    year_cur = total_for(year_start.strftime("%Y-%m-%d"), today_str)
    year_prev = total_for(prev_year_start.strftime("%Y-%m-%d"), prev_year_end.strftime("%Y-%m-%d"))

    def pack(cur, prev):
        (cur_total, cur_paid), (prev_total, prev_paid) = cur, prev
        return _pack_comparison(cur_total, cur_paid, prev_total, prev_paid)

    return {
        "week": pack(week_cur, week_prev),
        "month": pack(month_cur, month_prev),
        "year": pack(year_cur, year_prev),
    }


def get_revenue_range(shop_id: int, date_from: str, date_to: str) -> dict:
    """Выручка и число услуг за произвольный период (включительно с обеих
    сторон), например для выбора дат через календарь на сайте."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(oc.cost), 0) as total, COUNT(*) as cnt,
                   COALESCE(SUM(oc.cash_amount), 0) as cash, COALESCE(SUM(oc.card_amount), 0) as card,
                   SUM(CASE WHEN oc.cost > 0 THEN 1 ELSE 0 END) as paid_cnt
            FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.cost IS NOT NULL
              AND oc.change_date >= ? AND oc.change_date <= ?
        """, (shop_id, date_from, date_to)).fetchone()
        result = _with_avg({"total": row["total"], "count": row["cnt"], "cash": row["cash"], "card": row["card"],
                            "paid_count": row["paid_cnt"] or 0})
        result["clients"] = _client_split(conn, shop_id, date_from, date_to)
        return result


def get_profit_breakdown(shop_id: int, date_from: str, date_to: str) -> dict:
    """Из чего складывается прибыль за период:
    • goods_profit — товары со склада: цена продажи − цена закупки на момент
      продажи (cost_price в записи);
    • services — работа и «Прочее» (мойка и т.п.): себестоимости товара у
      них нет, поэтому вся сумма — доход (зарплату мастеров вычитают расходы);
    • unpriced — выручка, по которой прибыль посчитать нельзя: товар со
      склада без цены закупки или масло/фильтр, вписанные вручную не со
      склада, и старые записи без разбивки. В прибыль НЕ входит — показываем
      отдельно, чтобы было видно, что прибыль неполная и что исправить.
    profit = goods_profit + services."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.items_json, oc.cost FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.change_date >= ? AND oc.change_date <= ?
        """, (shop_id, date_from, date_to)).fetchall()
    goods = services = unpriced = 0
    for row in rows:
        items = None
        if row["items_json"]:
            try:
                items = json.loads(row["items_json"])
            except (ValueError, TypeError):
                items = None
        if not items:
            unpriced += row["cost"] or 0
            continue
        for item in items:
            total = item.get("total") or 0
            if item.get("cost_price") is not None and item.get("qty") is not None:
                goods += total - item["qty"] * item["cost_price"]
            elif item.get("product_id") or str(item.get("key") or "").startswith(("fluid_", "filter_")):
                unpriced += total
            else:
                services += total
    goods, services, unpriced = round(goods), round(services), round(unpriced)
    return {"goods_profit": goods, "services": services, "unpriced": unpriced, "profit": goods + services}


def _compute_profit_for_range(shop_id: int, date_from: str, date_to: str) -> int:
    """Прибыль за период = прибыль по товарам со склада + работа/услуги
    (подробно — см. get_profit_breakdown)."""
    return get_profit_breakdown(shop_id, date_from, date_to)["profit"]


def get_profit_range(shop_id: int, date_from: str, date_to: str) -> int:
    return _compute_profit_for_range(shop_id, date_from, date_to)


def get_profit_stats(shop_id: int) -> dict:
    """Прибыль за сегодня/вчера/эту неделю/этот месяц/этот год — по той же
    логике периодов, что и get_revenue_stats."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    year_start = now.strftime("%Y-01-01")
    far_past = "2000-01-01"
    return {
        "today": _compute_profit_for_range(shop_id, today, today),
        "yesterday": _compute_profit_for_range(shop_id, yesterday, yesterday),
        "week": _compute_profit_for_range(shop_id, week_start, today),
        "month": _compute_profit_for_range(shop_id, month_start, today),
        "year": _compute_profit_for_range(shop_id, year_start, today),
    }


@_serialized
def create_branch_shop(parent_shop_id: int, username: str, password: str, shop_name: str = None,
                        phone: str = None, address: str = None, hours: str = None,
                        lat: float = None, lon: float = None, notify_telegram_id: str = None) -> dict:
    """Создаёт филиал — обычная точка (свой склад, своя база клиентов), но
    с role='branch' и привязкой к главному аккаунту (parent_shop_id).
    Права филиала (без прибыли, без цены закупки) применяются в webapp.py
    по этому role, а не отдельным полем — так же, как role='admin'.
    Принимает те же поля, что и обычная точка (телефон, адрес, часы работы,
    локация, Telegram для уведомлений) — филиал настраивается так же
    полноценно, как любая другая точка."""
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO shops (username, password_hash, password_plain, role, shop_name, phone, address, hours, lat, lon,
                                anpr_token, notify_telegram_id, is_active, parent_shop_id, owner_link_token)
            VALUES (?, ?, NULL, 'branch', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (username, generate_password_hash(password), shop_name,
              phone, address, hours, lat, lon, secrets.token_urlsafe(8), notify_telegram_id,
              parent_shop_id, secrets.token_urlsafe(12)))
        conn.commit()
        return get_shop(cur.lastrowid)


def get_branches(parent_shop_id: int):
    """Все филиалы главного аккаунта + число их клиентов — для его собственной
    панели и для админки. Пароль нигде не хранится в расшифровываемом виде."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM clients WHERE shop_id = s.id) as client_count
            FROM shops s WHERE s.parent_shop_id = ? ORDER BY s.created_at
        """, (parent_shop_id,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            del d["password_hash"]
            del d["password_plain"]
            result.append(d)
        return result


def is_branch_of(shop_id: int, parent_shop_id: int) -> bool:
    """Проверка владения: действительно ли эта точка — филиал именно этого
    главного аккаунта (защита от того, чтобы один владелец лез в чужие
    филиалы, подставив чужой shop_id)."""
    shop = get_shop(shop_id)
    return bool(shop and shop.get("parent_shop_id") == parent_shop_id)


def get_aggregated_revenue_stats(parent_shop_id: int) -> dict:
    """Выручка главного аккаунта, сложенная со всеми его филиалами — по тем
    же периодам, что и обычная статистика."""
    shop_ids = [parent_shop_id] + [b["id"] for b in get_branches(parent_shop_id)]
    combined = {p: {"total": 0, "count": 0, "cash": 0, "card": 0, "paid_count": 0}
                for p in ("today", "yesterday", "week", "month", "year")}
    client_parts = {p: [] for p in combined}
    for sid in shop_ids:
        stats = get_revenue_stats(sid)
        for period in combined:
            for k in ("total", "count", "cash", "card", "paid_count"):
                combined[period][k] += stats[period][k]
            client_parts[period].append(stats[period]["clients"])
    for period in combined:
        combined[period]["clients"] = _sum_client_splits(client_parts[period])
    # средний чек сети считаем из сумм, а не как среднее средних филиалов —
    # иначе маленький филиал весил бы столько же, сколько большой
    for period in combined:
        _with_avg(combined[period])
    return combined


def get_aggregated_profit_stats(parent_shop_id: int) -> dict:
    """Прибыль главного аккаунта, сложенная со всеми его филиалами."""
    shop_ids = [parent_shop_id] + [b["id"] for b in get_branches(parent_shop_id)]
    combined = {"today": 0, "yesterday": 0, "week": 0, "month": 0, "year": 0}
    for sid in shop_ids:
        stats = get_profit_stats(sid)
        for period in combined:
            combined[period] += stats[period]
    return combined


def get_branch_breakdown_stats(parent_shop_id: int):
    """Выручка и прибыль отдельно по каждому филиалу (и самому главному
    аккаунту) — кто сколько продал, а не только общая сумма."""
    parent = get_shop(parent_shop_id)
    branches = get_branches(parent_shop_id)
    rows = []
    for shop in [parent] + branches:
        if not shop:
            continue
        rows.append({
            "shop_id": shop["id"],
            "shop_name": shop.get("shop_name") or shop["username"],
            "is_head": shop["id"] == parent_shop_id,
            "revenue": get_revenue_stats(shop["id"]),
            "profit": get_profit_stats(shop["id"]),
        })
    return rows


def get_aggregated_revenue_range(parent_shop_id: int, date_from: str, date_to: str) -> dict:
    """Выручка за произвольный период, сложенная по главному аккаунту и всем
    его филиалам вместе."""
    shop_ids = [parent_shop_id] + [b["id"] for b in get_branches(parent_shop_id)]
    total, count, cash, card, paid = 0, 0, 0, 0, 0
    client_parts = []
    for sid in shop_ids:
        r = get_revenue_range(sid, date_from, date_to)
        total += r["total"]
        count += r["count"]
        cash += r["cash"]
        card += r["card"]
        paid += r["paid_count"]
        client_parts.append(r["clients"])
    result = _with_avg({"total": total, "count": count, "cash": cash, "card": card, "paid_count": paid})
    result["clients"] = _sum_client_splits(client_parts)
    return result


def get_aggregated_profit_range(parent_shop_id: int, date_from: str, date_to: str) -> int:
    """Прибыль за произвольный период, сложенная по главному аккаунту и всем
    его филиалам вместе."""
    shop_ids = [parent_shop_id] + [b["id"] for b in get_branches(parent_shop_id)]
    return sum(get_profit_range(sid, date_from, date_to) for sid in shop_ids)


def get_branch_breakdown_range(parent_shop_id: int, date_from: str, date_to: str):
    """Разбивка по каждому филиалу (и самому главному) за произвольный
    период — та же идея, что get_branch_breakdown_stats, но не только
    "сегодня", а любой выбранный диапазон дат."""
    parent = get_shop(parent_shop_id)
    branches = get_branches(parent_shop_id)
    rows = []
    for shop in [parent] + branches:
        if not shop:
            continue
        rows.append({
            "shop_id": shop["id"],
            "shop_name": shop.get("shop_name") or shop["username"],
            "is_head": shop["id"] == parent_shop_id,
            "revenue": get_revenue_range(shop["id"], date_from, date_to),
            "profit": get_profit_range(shop["id"], date_from, date_to),
        })
    return rows


def get_branch_warehouse_summary(parent_shop_id: int):
    """По каждому филиалу — сколько товаров на складе, у скольких из них
    ещё не проставлена цена закупки, и общая стоимость остатка по цене
    закупки (товары без цены в неё просто не входят — их стоимость пока
    неизвестна). Чтобы видеть это одним взглядом, не заходя по очереди в
    склад каждого филиала."""
    branches = get_branches(parent_shop_id)
    result = []
    for b in branches:
        products = list_products(b["id"])
        missing = sum(1 for p in products if p.get("purchase_price") is None)
        stock_value = sum(
            p["stock_qty"] * p["purchase_price"]
            for p in products if p.get("purchase_price") is not None
        )
        result.append({
            "id": b["id"],
            "shop_name": b.get("shop_name") or b["username"],
            "product_count": len(products),
            "missing_price_count": missing,
            "stock_value": stock_value,
        })
    return result


@_serialized
def backfill_cost_price(shop_id: int, product_id: int, purchase_price) -> int:
    """Цена закупки появилась у товара, у которого её НЕ было (филиал сам
    завёл товар, главный вписал цену позже). Проставляем её в прошлые
    продажи этого товара, где цены закупки не было, — иначе эти продажи
    навсегда выпали бы из прибыли. Продажи, где цена уже была, не трогаем:
    это не переписывание истории, а заполнение пропуска."""
    if purchase_price is None:
        return 0
    changed = 0
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.id, oc.items_json FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.items_json LIKE ?
        """, (shop_id, f'%"product_id": {int(product_id)}%')).fetchall()
        for r in rows:
            try:
                items = json.loads(r["items_json"]) or []
            except (ValueError, TypeError):
                continue
            touched = False
            for it in items:
                if it.get("product_id") == product_id and it.get("cost_price") is None:
                    it["cost_price"] = purchase_price
                    touched = True
                    changed += 1
            if touched:
                conn.execute("UPDATE oil_changes SET items_json=? WHERE id=?",
                             (json.dumps(items, ensure_ascii=False), r["id"]))
        conn.commit()
    return changed


@_serialized
def set_product_purchase_price(product_id: int, shop_id: int, purchase_price):
    """Главный аккаунт вписывает цену закупки товара своего филиала — сам
    филиал этого не делает (см. create_product/restock_product ниже, где
    покупная цена от филиала игнорируется)."""
    before = get_product(product_id, shop_id, active_only=False)
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE products SET purchase_price=? WHERE id=? AND shop_id=?",
            (purchase_price, product_id, shop_id)
        )
        conn.commit()
        ok = cur.rowcount > 0
    if ok and before and before.get("purchase_price") is None and purchase_price is not None:
        backfill_cost_price(shop_id, product_id, purchase_price)
    return ok


def get_full_history_flat(shop_id: int):
    """Полная история всех замен точки одним плоским списком (по строке на
    каждую услугу, с данными машины/клиента в той же строке) — для выгрузки
    в Excel. Отсортировано от новых к старым."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.change_date, c.plate_number, cl.full_name as owner_name, cl.phone as owner_phone,
                   c.car_brand, c.car_model, oc.mileage, oc.next_mileage, oc.service_type,
                   oc.oil_brand, oc.cost, oc.next_change_date, oc.notes
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN clients cl ON cl.id = c.client_id
            WHERE c.shop_id = ?
            ORDER BY oc.change_date DESC, oc.id DESC
        """, (shop_id,)).fetchall()
        return [dict(r) for r in rows]


def export_shop_data(shop_id: int) -> dict:
    """Полный дамп ВСЕХ данных одной точки — клиенты, машины (с полной
    историей внутри) и рассылки. Используется для скачивания резервной копии
    или переноса точки на другой сервер."""
    with get_conn() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
        clients = conn.execute("SELECT * FROM clients WHERE shop_id=?", (shop_id,)).fetchall()
        cars = conn.execute("SELECT * FROM cars WHERE shop_id=?", (shop_id,)).fetchall()
        cars_out = []
        for car in cars:
            history = conn.execute(
                "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date", (car["id"],)
            ).fetchall()
            car_dict = dict(car)
            car_dict["oil_changes"] = [dict(h) for h in history]
            cars_out.append(car_dict)
        broadcasts = conn.execute("SELECT * FROM broadcasts WHERE shop_id=? ORDER BY id", (shop_id,)).fetchall()

        return {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "shop": {k: v for k, v in dict(shop).items()
                      if k not in ("password_hash", "password_plain", "eskiz_password")} if shop else None,
            "clients": [dict(c) for c in clients],
            "cars": cars_out,
            "broadcasts": [dict(b) for b in broadcasts],
        }



# ---------- Сеть филиалов: полная картина для главного аккаунта ----------

def network_shops(parent_shop_id: int):
    """Главный аккаунт + его филиалы: [{id, name, is_head}] — для кнопок выбора."""
    parent = get_shop(parent_shop_id)
    out = []
    for shop in [parent] + get_branches(parent_shop_id):
        if shop:
            out.append({"id": shop["id"], "name": shop.get("shop_name") or shop["username"],
                        "is_head": shop["id"] == parent_shop_id})
    return out


def _sum_revenue_period(parts) -> dict:
    out = {"total": 0, "count": 0, "cash": 0, "card": 0, "paid_count": 0}
    for p in parts:
        for k in out:
            out[k] += p.get(k) or 0
    _with_avg(out)
    out["clients"] = _sum_client_splits([p["clients"] for p in parts])
    return out


def get_network_overview(shop_ids) -> dict:
    """Всё то же, что главный видит по своей точке, но для выбранного набора
    точек (вся сеть или один филиал): карточки периодов со сравнением,
    чистая прибыль за 30 дней, выручка по дням, долги, заканчивающиеся товары."""
    periods = ("today", "week", "month", "year")
    rev = [get_revenue_stats(sid) for sid in shop_ids]
    cmp_parts = [get_revenue_comparison(sid) for sid in shop_ids]
    prof = [get_profit_stats(sid) for sid in shop_ids]

    stats = {p: _sum_revenue_period([r[p] for r in rev]) for p in periods}
    comparison = {}
    for p in ("week", "month", "year"):
        comparison[p] = _pack_comparison(
            sum(c[p]["current"] for c in cmp_parts), sum(c[p]["paid_current"] for c in cmp_parts),
            sum(c[p]["previous"] for c in cmp_parts), sum(c[p]["paid_previous"] for c in cmp_parts))
    profit = {p: sum(x[p] for x in prof) for p in periods}

    net = {"oil_profit": 0, "services": 0, "unpriced": 0, "expenses_total": 0, "net_profit": 0}
    for sid in shop_ids:
        n = get_net_profit_30d(sid)
        for k in net:
            net[k] += n[k]

    daily = None
    for sid in shop_ids:
        d = get_daily_revenue(sid, days=30)
        if daily is None:
            daily = d
        else:
            for a, b in zip(daily, d):
                a["total"] += b["total"]
                a["count"] += b["count"]

    debt = {"total_remaining": 0, "count": 0, "overdue_count": 0}
    low_stock = []
    for sid in shop_ids:
        ds = get_debt_summary(sid)
        for k in debt:
            debt[k] += ds[k]
        shop = get_shop(sid)
        shop_name = (shop or {}).get("shop_name") or (shop or {}).get("username")
        if shop and shop.get("warehouse_enabled"):
            for p in get_low_stock_products(sid):
                low_stock.append({"name": p["name"], "stock_qty": p["stock_qty"], "unit": p["unit"],
                                  "shop_name": shop_name})
    low_stock.sort(key=lambda p: p["stock_qty"])

    return {"stats": stats, "comparison": comparison, "profit": profit, "net_profit": net,
            "daily_revenue": daily or [], "debt_summary": debt, "low_stock": low_stock}


def get_network_compare(parent_shop_id: int, period: str) -> dict:
    """Сравнение филиалов между собой за неделю/месяц/год (с начала периода
    по сегодня): выручка и её изменение, услуги, средний чек, клиенты,
    прибыль, расходы и чистая прибыль по каждой точке."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    starts = {
        "week": (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d"),
        "month": now.strftime("%Y-%m-01"),
        "year": now.strftime("%Y-01-01"),
    }
    if period not in starts:
        period = "month"
    date_from = starts[period]
    rows = []
    for shop in network_shops(parent_shop_id):
        sid = shop["id"]
        r = get_revenue_range(sid, date_from, today)
        cmp = get_revenue_comparison(sid)[period]
        pb = get_profit_breakdown(sid, date_from, today)
        profit = pb["profit"]
        expenses = sum(e["amount"] for e in get_expenses(sid, date_from, today))
        rows.append({
            **shop,
            "total": r["total"], "count": r["count"], "avg": r["avg"], "paid_count": r["paid_count"],
            "clients": r["clients"], "pct": cmp["pct"],
            "profit": profit, "goods_profit": pb["goods_profit"], "services": pb["services"],
            "unpriced": pb["unpriced"], "expenses": expenses, "net_profit": profit - expenses,
        })
    rows.sort(key=lambda x: x["total"], reverse=True)
    return {"period": period, "date_from": date_from, "date_to": today, "rows": rows}



# ---------- Склад: сводка, прогноз, склады сети, перемещения ----------

WH_LOW_THRESHOLD = 50       # как в get_low_stock_products: меньше 50 л/шт — «мало», если продаж ещё нет
WH_LOW_DAYS = 7             # если по скорости продаж хватит меньше чем на неделю — «заканчивается»
WH_COVER_DAYS = 30          # список закупки: сколько нужно, чтобы хватило на месяц
WH_DEAD_DAYS = 30           # «не продавался» — ни одной продажи за 30 дней


def get_product_sales(shop_id: int, days: int = 30) -> dict:
    """Сколько каждого товара склада продано за последние `days` дней
    (по записям о заменах, где товар выбран из склада) и дата последней продажи."""
    since = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.change_date, oc.items_json FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.change_date >= ? AND oc.items_json IS NOT NULL
        """, (shop_id, since)).fetchall()
    out = {}
    for r in rows:
        try:
            items = json.loads(r["items_json"]) or []
        except (TypeError, ValueError):
            continue
        for item in items:
            pid = item.get("product_id")
            if not pid:
                continue
            e = out.setdefault(pid, {"qty": 0, "last_sale": None})
            e["qty"] += item.get("qty") or 0
            if not e["last_sale"] or r["change_date"] > e["last_sale"]:
                e["last_sale"] = r["change_date"]
    return out


def get_warehouse_overview(shop_id: int, days: int = 30) -> dict:
    """Товары склада с прогнозом («хватит на N дней», сколько заказать) и
    сводка: стоимость остатка, возможная наценка, сколько заканчивается и
    сколько лежит без продаж. Прогноз честный: если продаж за 30 дней не было,
    дни не считаем, а пишем «нет продаж»."""
    products = list_products(shop_id)
    sales = get_product_sales(shop_id, days)
    old_enough = (datetime.now() - timedelta(days=WH_DEAD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    items = []
    summary = {"product_count": len(products), "stock_value": 0, "retail_value": 0,
               "potential_margin": 0, "missing_price_count": 0,
               "low_count": 0, "out_count": 0, "dead_count": 0, "dead_value": 0, "reorder_count": 0}
    for p in products:
        sold = round(sales.get(p["id"], {}).get("qty", 0), 2)
        per_day = sold / days if sold else 0
        stock = p["stock_qty"] or 0
        days_left = round(stock / per_day) if per_day and stock > 0 else (0 if per_day and stock <= 0 else None)
        need = per_day * WH_COVER_DAYS
        reorder = max(0, math.ceil(need - stock)) if per_day else 0
        if stock <= 0:
            status = "out"
        elif per_day and days_left is not None and days_left < WH_LOW_DAYS:
            status = "low"
        elif not per_day and stock < WH_LOW_THRESHOLD and (p.get("created_at") or "") < old_enough:
            status = "low"
        else:
            status = "ok"
        dead = stock > 0 and not sold and (p.get("created_at") or "") < old_enough
        buy, sell = p.get("purchase_price"), p.get("sell_price")
        margin_pct = round((sell - buy) / buy * 100) if buy and sell else None
        items.append({**p, "sold_30d": sold, "per_day": round(per_day, 2), "days_left": days_left,
                      "reorder_qty": reorder, "status": status, "dead": dead,
                      "last_sale": sales.get(p["id"], {}).get("last_sale"), "margin_pct": margin_pct})
        if buy is None:
            summary["missing_price_count"] += 1
        if stock > 0:
            if buy is not None:
                summary["stock_value"] += stock * buy
            if sell:
                summary["retail_value"] += stock * sell
            if buy is not None and sell:
                summary["potential_margin"] += stock * (sell - buy)
        if status == "low":
            summary["low_count"] += 1
        if status == "out":
            summary["out_count"] += 1
        if dead:
            summary["dead_count"] += 1
            if buy is not None:
                summary["dead_value"] += stock * buy
        if reorder > 0:
            summary["reorder_count"] += 1
    for k in ("stock_value", "retail_value", "potential_margin", "dead_value"):
        summary[k] = round(summary[k])
    return {"products": items, "summary": summary}


def _norm_product_key(p) -> tuple:
    return (p["category"], " ".join((p["name"] or "").upper().split()))


def get_network_stock_matrix(parent_shop_id: int) -> dict:
    """Остатки всех складов сети в одной таблице: строка — товар (одинаковое
    название и тип считаются одним товаром), колонка — точка."""
    shops = [s for s in network_shops(parent_shop_id)
             if (get_shop(s["id"]) or {}).get("warehouse_enabled")]
    rows = {}
    for shop in shops:
        ov = get_warehouse_overview(shop["id"])
        for p in ov["products"]:
            key = _norm_product_key(p)
            row = rows.setdefault(key, {"category": p["category"], "name": p["name"], "unit": p["unit"], "cells": {}})
            row["cells"][str(shop["id"])] = {"product_id": p["id"], "qty": p["stock_qty"], "status": p["status"],
                                             "days_left": p["days_left"]}
    out = sorted(rows.values(), key=lambda r: (r["category"], r["name"].upper()))
    return {"shops": shops, "rows": out}


def _in_network(parent_shop_id: int, shop_id: int) -> bool:
    return shop_id == parent_shop_id or is_branch_of(shop_id, parent_shop_id)


@_serialized
def transfer_stock(parent_shop_id: int, from_shop_id: int, product_id: int, to_shop_id: int,
                   quantity: float) -> dict:
    """Перемещение товара между складами сети (главный ↔ филиал, филиал ↔ филиал).
    На складе-получателе ищем такой же товар (тот же тип и название); если его
    нет — заводим с теми же ценами. Списание и зачисление — одной транзакцией,
    чтобы остатки никогда не разъехались."""
    if from_shop_id == to_shop_id:
        return {"ok": False, "error": "same_shop"}
    if not (_in_network(parent_shop_id, from_shop_id) and _in_network(parent_shop_id, to_shop_id)):
        return {"ok": False, "error": "not_your_shop"}
    if not quantity or quantity <= 0:
        return {"ok": False, "error": "bad_qty"}
    src = get_product(product_id, from_shop_id)
    if not src:
        return {"ok": False, "error": "no_product"}
    if quantity > (src["stock_qty"] or 0):
        return {"ok": False, "error": "not_enough", "available": src["stock_qty"]}
    key = _norm_product_key(src)
    dst = next((p for p in list_products(to_shop_id) if _norm_product_key(p) == key), None)
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        if not dst:
            cur = conn.execute("""
                INSERT INTO products (shop_id, category, name, unit, stock_qty, sell_price, purchase_price, is_active)
                VALUES (?, ?, ?, ?, 0, ?, ?, 1)
            """, (to_shop_id, src["category"], src["name"], src["unit"], src["sell_price"], src["purchase_price"]))
            dst_id = cur.lastrowid
        else:
            dst_id = dst["id"]
            # как при пополнении: цена закупки товара = цена последней пришедшей
            # партии, а партия от главного приходит со своей ценой закупки
            if src.get("purchase_price") is not None:
                conn.execute("UPDATE products SET purchase_price=? WHERE id=?", (src["purchase_price"], dst_id))
        conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (quantity, src["id"]))
        conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id=?", (quantity, dst_id))
        conn.execute("""
            INSERT INTO stock_transfers (parent_shop_id, from_shop_id, to_shop_id, from_product_id, to_product_id, quantity, transfer_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (parent_shop_id, from_shop_id, to_shop_id, src["id"], dst_id, quantity, today))
        conn.commit()
    if dst and dst.get("purchase_price") is None and src.get("purchase_price") is not None:
        backfill_cost_price(to_shop_id, dst_id, src["purchase_price"])
    return {"ok": True, "to_product_id": dst_id}


def get_stock_movements(shop_id: int, limit: int = 60) -> list:
    """История движения склада точки: пополнения + перемещения (пришло/ушло)."""
    out = []
    for r in get_restock_history(shop_id, limit):
        out.append({"type": "restock", "date": r["restock_date"], "product_name": r["product_name"],
                    "unit": r["unit"], "quantity": r["quantity"], "purchase_price": r.get("purchase_price"),
                    "order_number": r.get("order_number"),
                    "sort": (r["restock_date"], r["created_at"] or "")})
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT t.*, p.name as product_name, p.unit,
                   sf.shop_name as from_name, sf.username as from_user,
                   st.shop_name as to_name, st.username as to_user
            FROM stock_transfers t
            JOIN products p ON p.id = CASE WHEN t.from_shop_id=? THEN t.from_product_id ELSE t.to_product_id END
            LEFT JOIN shops sf ON sf.id = t.from_shop_id
            LEFT JOIN shops st ON st.id = t.to_shop_id
            WHERE t.from_shop_id=? OR t.to_shop_id=?
            ORDER BY t.transfer_date DESC, t.id DESC LIMIT ?
        """, (shop_id, shop_id, shop_id, limit)).fetchall()
    for r in rows:
        outgoing = r["from_shop_id"] == shop_id
        out.append({"type": "transfer_out" if outgoing else "transfer_in", "date": r["transfer_date"],
                    "product_name": r["product_name"], "unit": r["unit"], "quantity": r["quantity"],
                    "other_shop": ((r["to_name"] or r["to_user"]) if outgoing else (r["from_name"] or r["from_user"])) or "—",
                    "batch": r["batch"] if "batch" in r.keys() else None,
                    "sort": (r["transfer_date"], r["created_at"] or "")})
    with get_conn() as conn:
        adj = conn.execute("""
            SELECT a.*, p.name as product_name, p.unit FROM stock_adjustments a
            JOIN products p ON p.id = a.product_id
            WHERE a.shop_id=? ORDER BY a.id DESC LIMIT ?
        """, (shop_id, limit)).fetchall()
    for r in adj:
        out.append({"type": "adjust", "date": r["adjust_date"], "product_name": r["product_name"],
                    "unit": r["unit"], "quantity": abs(r["new_qty"] - r["old_qty"]),
                    "delta": r["new_qty"] - r["old_qty"], "old_qty": r["old_qty"], "new_qty": r["new_qty"],
                    "reason": r["reason"], "sort": (r["adjust_date"], r["created_at"] or "")})
    out.sort(key=lambda x: x["sort"], reverse=True)
    for x in out:
        x.pop("sort", None)
    return out[:limit]



# ---------- Управление филиалами (изменение и удаление) ----------

@_serialized
def update_branch_details(branch_id: int, shop_name: str, username: str, phone=None, address=None,
                          hours=None, lat=None, lon=None, notify_telegram_id=None) -> bool:
    """Меняет всё, что задаётся при создании филиала: название, логин,
    телефон, адрес, часы, локацию, Telegram для уведомлений."""
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE shops SET shop_name=?, username=?, phone=?, address=?, hours=?, lat=?, lon=?, notify_telegram_id=?
            WHERE id=? AND role='branch'
        """, (shop_name, username, phone, address, hours, lat, lon, notify_telegram_id, branch_id))
        conn.commit()
        return cur.rowcount > 0


def branch_data_counts(branch_id: int) -> dict:
    """Что пропадёт вместе с филиалом — показываем перед удалением."""
    with get_conn() as conn:
        one = lambda q: conn.execute(q, (branch_id,)).fetchone()[0]
        return {
            "clients": one("SELECT COUNT(*) FROM clients WHERE shop_id=?"),
            "cars": one("SELECT COUNT(*) FROM cars WHERE shop_id=?"),
            "services": one("SELECT COUNT(*) FROM oil_changes oc JOIN cars c ON c.id = oc.car_id WHERE c.shop_id=?"),
            "products": one("SELECT COUNT(*) FROM products WHERE shop_id=? AND is_active=1"),
            "debts": one("SELECT COUNT(*) FROM installment_plans WHERE shop_id=?"),
            "employees": one("SELECT COUNT(*) FROM shop_users WHERE shop_id=?"),
        }


@_serialized
def delete_branch_with_data(branch_id: int) -> bool:
    """Полностью удаляет филиал и все его данные одной транзакцией: либо
    удаляется всё, либо (при любой ошибке) ничего. Перемещения товара между
    складами остаются в истории других точек."""
    shop = get_shop(branch_id)
    if not shop or shop.get("role") != "branch":
        return False
    with get_conn() as conn:
        try:
            car_ids = "SELECT id FROM cars WHERE shop_id=?"
            conn.execute(f"DELETE FROM installment_payments WHERE plan_id IN (SELECT id FROM installment_plans WHERE shop_id=?)", (branch_id,))
            conn.execute("DELETE FROM installment_plans WHERE shop_id=?", (branch_id,))
            conn.execute(f"DELETE FROM oil_changes WHERE car_id IN ({car_ids})", (branch_id,))
            conn.execute("DELETE FROM cars WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM clients WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM stock_restocks WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM stock_adjustments WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM products WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM expense_entries WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM recurring_expenses WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM broadcasts WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM shop_users WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM password_reset_codes WHERE shop_id=?", (branch_id,))
            conn.execute("DELETE FROM shops WHERE id=? AND role='branch'", (branch_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return True



# ---------- Массовые операции склада: каталог, накладная, план отправки, импорт ----------

def _norm_key(category: str, name: str) -> tuple:
    return (category, " ".join((name or "").upper().split()))


@_serialized
def copy_catalog_to_branch(parent_shop_id: int, branch_id: int, categories=None) -> dict:
    """Все товары главного (или только выбранные типы) появляются на складе
    филиала с остатком 0 и теми же ценами. Товар физически не двигается.
    Уже существующие у филиала товары (тот же тип + название) пропускаем."""
    if not is_branch_of(branch_id, parent_shop_id):
        return {"ok": False, "error": "not_your_shop"}
    have = {_norm_key(p["category"], p["name"]) for p in list_products(branch_id)}
    created = skipped = 0
    with get_conn() as conn:
        for p in list_products(parent_shop_id):
            if categories and p["category"] not in categories:
                continue
            key = _norm_key(p["category"], p["name"])
            if key in have:
                skipped += 1
                continue
            conn.execute("""
                INSERT INTO products (shop_id, category, name, unit, stock_qty, sell_price, purchase_price, is_active)
                VALUES (?, ?, ?, ?, 0, ?, ?, 1)
            """, (branch_id, p["category"], p["name"], p["unit"], p["sell_price"], p["purchase_price"]))
            have.add(key)
            created += 1
        conn.commit()
    return {"ok": True, "created": created, "skipped": skipped}


def get_ship_plan(parent_shop_id: int, from_shop_id: int, to_shop_id: int) -> dict:
    """Для окна «Отправить товары»: все товары склада-отправителя с остатком,
    сколько такого товара у получателя, скорость его продаж там и сколько
    предложить отправить, чтобы получателю хватило ~на месяц (не больше,
    чем есть у отправителя)."""
    if not (_in_network(parent_shop_id, from_shop_id) and _in_network(parent_shop_id, to_shop_id)):
        return {"ok": False, "error": "not_your_shop"}
    dst = {_norm_key(p["category"], p["name"]): p for p in get_warehouse_overview(to_shop_id)["products"]}
    rows = []
    for p in list_products(from_shop_id):
        d = dst.get(_norm_key(p["category"], p["name"]))
        need = 0
        if d:
            need = d["reorder_qty"] or 0
            if not need and d["status"] == "out" and not d["per_day"]:
                need = 0
        suggested = min(need, max(0, p["stock_qty"] or 0))
        rows.append({
            "id": p["id"], "name": p["name"], "category": p["category"], "unit": p["unit"],
            "stock": p["stock_qty"] or 0, "sell_price": p["sell_price"],
            "to_qty": d["stock_qty"] if d else None, "to_per_day": d["per_day"] if d else 0,
            "to_status": d["status"] if d else None, "suggested": suggested,
        })
    rows.sort(key=lambda r: (-r["suggested"], r["category"], r["name"].upper()))
    return {"ok": True, "rows": rows}


@_serialized
def bulk_transfer(parent_shop_id: int, from_shop_id: int, to_shop_id: int, lines: list) -> dict:
    """Накладная: много товаров одним действием и ОДНОЙ транзакцией — либо
    уходит всё, либо (если чего-то не хватает) ничего, с понятным списком
    проблем. Каждая строка пишется в историю с общим номером накладной."""
    if from_shop_id == to_shop_id:
        return {"ok": False, "error": "same_shop"}
    if not (_in_network(parent_shop_id, from_shop_id) and _in_network(parent_shop_id, to_shop_id)):
        return {"ok": False, "error": "not_your_shop"}
    qty_by_pid = {}
    for ln in lines or []:
        try:
            pid, q = int(ln["product_id"]), float(ln["quantity"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "bad_request"}
        if q > 0:
            qty_by_pid[pid] = qty_by_pid.get(pid, 0) + q
    if not qty_by_pid:
        return {"ok": False, "error": "empty"}
    src_products = {p["id"]: p for p in list_products(from_shop_id)}
    problems = []
    for pid, q in qty_by_pid.items():
        p = src_products.get(pid)
        if not p:
            problems.append({"product_id": pid, "error": "no_product"})
        elif q > (p["stock_qty"] or 0) + 1e-9:
            problems.append({"product_id": pid, "name": p["name"], "error": "not_enough", "available": p["stock_qty"]})
    if problems:
        return {"ok": False, "error": "problems", "problems": problems}

    today = datetime.now().strftime("%Y-%m-%d")
    batch = datetime.now().strftime("%y%m%d-%H%M%S")
    with get_conn() as conn:
        try:
            backfills = _transfer_lines(conn, parent_shop_id, from_shop_id, to_shop_id,
                                        qty_by_pid, src_products, today, batch)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    for dst_id, price in backfills:
        backfill_cost_price(to_shop_id, dst_id, price)
    return {"ok": True, "batch": batch, "lines": len(qty_by_pid)}


def _transfer_lines(conn, parent_shop_id: int, from_shop_id: int, to_shop_id: int,
                    qty_by_pid: dict, src_products: dict, today: str, batch: str) -> list:
    """Внутри уже открытой транзакции: переносит товары {product_id: qty} со
    склада from на склад to (на получателе товар ищется по типу+названию или
    заводится). Остатки отправителя должны быть проверены заранее. Возвращает
    список (товар получателя, цена) для дозаполнения прошлых продаж."""
    dst_rows = conn.execute("SELECT * FROM products WHERE shop_id=? AND is_active=1", (to_shop_id,)).fetchall()
    dst_by_key = {_norm_key(r["category"], r["name"]): dict(r) for r in dst_rows}
    backfills = []
    for pid, q in qty_by_pid.items():
        src = src_products[pid]
        key = _norm_key(src["category"], src["name"])
        dst = dst_by_key.get(key)
        if not dst:
            cur = conn.execute("""
                INSERT INTO products (shop_id, category, name, unit, stock_qty, sell_price, purchase_price, is_active)
                VALUES (?, ?, ?, ?, 0, ?, ?, 1)
            """, (to_shop_id, src["category"], src["name"], src["unit"], src["sell_price"], src["purchase_price"]))
            dst = {"id": cur.lastrowid, "purchase_price": src["purchase_price"], "_new": True}
            dst_by_key[key] = dst
        else:
            if dst.get("purchase_price") is None and src.get("purchase_price") is not None and not dst.get("_new"):
                backfills.append((dst["id"], src["purchase_price"]))
            if src.get("purchase_price") is not None:
                conn.execute("UPDATE products SET purchase_price=? WHERE id=?", (src["purchase_price"], dst["id"]))
                dst["purchase_price"] = src["purchase_price"]
        conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (q, pid))
        conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id=?", (q, dst["id"]))
        conn.execute("""
            INSERT INTO stock_transfers (parent_shop_id, from_shop_id, to_shop_id, from_product_id, to_product_id, quantity, transfer_date, batch)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (parent_shop_id, from_shop_id, to_shop_id, pid, dst["id"], q, today, batch))
    return backfills


# --- импорт склада из Excel ---

IMPORT_UNITS = {"л": "l", "l": "l", "литр": "l", "litr": "l", "шт": "pc", "pc": "pc", "dona": "pc", "штук": "pc"}


def parse_import_rows(raw_rows: list, category_names: dict) -> list:
    """Проверяет строки из Excel: тип (по названию на русском/узбекском или
    по ключу), название, единица, цены, количество. Ничего не пишет — только
    возвращает, что будет сделано с каждой строкой, для предпросмотра."""
    out = []
    for i, r in enumerate(raw_rows, start=2):
        cat_raw = str(r.get("category") or "").strip()
        name = " ".join(str(r.get("name") or "").split())
        if not cat_raw and not name:
            continue
        row = {"row": i, "category_raw": cat_raw, "name": name, "errors": []}
        cat = category_names.get(cat_raw.lower())
        if not cat:
            row["errors"].append("type")
        if not name:
            row["errors"].append("name")
        unit_raw = str(r.get("unit") or "").strip().lower().rstrip(".")
        unit = IMPORT_UNITS.get(unit_raw) if unit_raw else (("l" if cat.startswith("fluid_") else "pc") if cat else None)
        if unit_raw and not unit:
            row["errors"].append("unit")

        def num(v, field, integer=True):
            if v in (None, ""):
                return None
            try:
                x = float(str(v).replace(" ", "").replace(",", "."))
                if x < 0:
                    raise ValueError
                return int(round(x)) if integer else x
            except ValueError:
                row["errors"].append(field)
                return None
        row.update({"category": cat, "unit": unit,
                    "sell_price": num(r.get("sell_price"), "sell_price"),
                    "purchase_price": num(r.get("purchase_price"), "purchase_price"),
                    "quantity": num(r.get("quantity"), "quantity", integer=False) or 0})
        out.append(row)
    return out


@_serialized
def apply_import(shop_id: int, rows: list, allow_purchase: bool) -> dict:
    """Новые товары — создаются с остатком из файла. Уже существующие (тот
    же тип + название) — количество приходит как пополнение (с ценой
    закупки партии, если она есть), цена продажи обновляется, если указана."""
    existing = {_norm_key(p["category"], p["name"]): p for p in list_products(shop_id)}
    created = restocked = updated = 0
    today = datetime.now().strftime("%Y-%m-%d")
    backfills = []
    with get_conn() as conn:
        try:
            for r in rows:
                if r.get("errors"):
                    continue
                buy = r.get("purchase_price") if allow_purchase else None
                key = _norm_key(r["category"], r["name"])
                p = existing.get(key)
                if not p:
                    cur = conn.execute("""
                        INSERT INTO products (shop_id, category, name, unit, stock_qty, sell_price, purchase_price, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (shop_id, r["category"], r["name"], r["unit"], r["quantity"] or 0, r.get("sell_price"), buy))
                    existing[key] = {"id": cur.lastrowid, "purchase_price": buy, "category": r["category"], "name": r["name"]}
                    if r["quantity"]:
                        conn.execute("""
                            INSERT INTO stock_restocks (product_id, shop_id, quantity, purchase_price, restock_date)
                            VALUES (?, ?, ?, ?, ?)
                        """, (cur.lastrowid, shop_id, r["quantity"], buy, today))
                    created += 1
                    continue
                if r.get("sell_price") is not None and r["sell_price"] != p.get("sell_price"):
                    conn.execute("UPDATE products SET sell_price=? WHERE id=?", (r["sell_price"], p["id"]))
                    updated += 1
                if buy is not None:
                    if p.get("purchase_price") is None:
                        backfills.append((p["id"], buy))
                    conn.execute("UPDATE products SET purchase_price=? WHERE id=?", (buy, p["id"]))
                if r["quantity"]:
                    conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id=?", (r["quantity"], p["id"]))
                    conn.execute("""
                        INSERT INTO stock_restocks (product_id, shop_id, quantity, purchase_price, restock_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (p["id"], shop_id, r["quantity"], buy, today))
                    restocked += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    for pid, price in backfills:
        backfill_cost_price(shop_id, pid, price)
    return {"ok": True, "created": created, "restocked": restocked, "updated": updated}


# ---------- Поставщики и заказы поставщику ----------
# Заказывает только главная (или самостоятельная) точка. Заказ проходит путь
# черновик → отправлен → получен (товар лёг на склад главной с ценами закупки)
# → раздан (по филиалам, перемещениями). У самостоятельной точки «получен»
# сразу становится последним шагом. Поставщик необязателен: заказ без
# поставщика — это просто список покупок (например, поездка на рынок).

ORDER_OPEN_STATUSES = ("draft", "sent")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_text(v, limit=200):
    v = " ".join(str(v or "").split())
    return v[:limit] or None


def list_suppliers(shop_id: int, archived: bool = False) -> list:
    """Поставщики точки с долгом. archived=True — поставщики из архива
    (удалённые): их история не пропадает, их можно вернуть."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM products p
                         WHERE p.shop_id=s.shop_id AND p.supplier_id=s.id AND p.is_active=1) AS product_count
            FROM suppliers s WHERE s.shop_id=? AND s.is_active=? ORDER BY s.name COLLATE NOCASE
        """, (shop_id, 0 if archived else 1)).fetchall()
        out = [dict(r) for r in rows]
        for sup in out:
            entries = _supplier_charges(conn, shop_id, sup["id"])
            d = supplier_debt(shop_id, sup["id"], sup.get("pay_days"), entries)
            sup["balance"], sup["overdue"] = d["balance"], d["overdue"]
            sup["next_due"], sup["oldest_overdue"] = d["next_due"], d["oldest_overdue"]
        return out


def get_supplier(shop_id: int, supplier_id: int, include_archived: bool = False):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM suppliers WHERE id=? AND shop_id=?" + ("" if include_archived else " AND is_active=1"),
                           (supplier_id, shop_id)).fetchone()
        return dict(row) if row else None


def shop_usd_rate(shop_id: int):
    """Курс доллара точки (как на «Складе»); у филиала без своего — курс главной."""
    with get_conn() as conn:
        r = conn.execute("SELECT usd_rate, parent_shop_id FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not r:
            return None
        if r["usd_rate"]:
            return r["usd_rate"]
        if r["parent_shop_id"]:
            p = conn.execute("SELECT usd_rate FROM shops WHERE id=?", (r["parent_shop_id"],)).fetchone()
            return p["usd_rate"] if p and p["usd_rate"] else None
        return None


def _supplier_fields(data: dict) -> dict:
    tg = _clean_text(data.get("telegram"), 64)
    if tg:
        tg = tg.replace("https://", "").replace("http://", "").replace("t.me/", "").lstrip("@").strip("/")
    try:
        pay_days = int(float(data.get("pay_days"))) if data.get("pay_days") not in (None, "") else None
    except (TypeError, ValueError):
        pay_days = None
    if pay_days is not None and not (0 <= pay_days <= 365):
        pay_days = None
    return {"name": _clean_text(data.get("name"), 80), "phone": _clean_text(data.get("phone"), 40),
            "telegram": tg or None, "contact": _clean_text(data.get("contact"), 80),
            "delivery_days": _clean_text(data.get("delivery_days"), 80), "note": _clean_text(data.get("note"), 300),
            "pay_days": pay_days}


@_serialized
def save_supplier(shop_id: int, data: dict, supplier_id: int = None):
    """Создать (supplier_id=None) или изменить поставщика. Возвращает (ok, error, id)."""
    f = _supplier_fields(data)
    if not f["name"]:
        return False, "empty_name", None
    for s in list_suppliers(shop_id):
        if s["id"] != supplier_id and s["name"].upper() == f["name"].upper():
            return False, "duplicate", None
    with get_conn() as conn:
        if supplier_id:
            cur = conn.execute("""
                UPDATE suppliers SET name=?, phone=?, telegram=?, contact=?, delivery_days=?, note=?, pay_days=?
                WHERE id=? AND shop_id=? AND is_active=1
            """, (*f.values(), supplier_id, shop_id))
            if cur.rowcount == 0:
                return False, "not_found", None
        else:
            cur = conn.execute("""
                INSERT INTO suppliers (shop_id, name, phone, telegram, contact, delivery_days, note, pay_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (shop_id, *f.values()))
            supplier_id = cur.lastrowid
        conn.commit()
    return True, None, supplier_id


@_serialized
def supplier_link_token(shop_id: int, supplier_id: int):
    """Персональная ссылка для поставщика: он один раз нажимает «Start» в
    боте, и дальше заказы приходят ему от бота автоматически (Telegram не
    даёт боту писать человеку первым, пока тот сам не начал чат)."""
    with get_conn() as conn:
        row = conn.execute("SELECT link_token FROM suppliers WHERE id=? AND shop_id=? AND is_active=1",
                           (supplier_id, shop_id)).fetchone()
        if not row:
            return None
        if row["link_token"]:
            return row["link_token"]
        token = secrets.token_urlsafe(12)
        conn.execute("UPDATE suppliers SET link_token=? WHERE id=?", (token, supplier_id))
        conn.commit()
        return token


@_serialized
def link_supplier_by_token(telegram_id, token: str):
    """Поставщик перешёл по ссылке и нажал Start — запоминаем его чат."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM suppliers WHERE link_token=? AND is_active=1", (token,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE suppliers SET tg_chat_id=? WHERE id=?", (str(telegram_id), row["id"]))
        conn.commit()
        sup = dict(row)
    sup["tg_chat_id"] = str(telegram_id)
    shop = get_shop(sup["shop_id"]) or {}
    sup["shop_name"] = shop.get("shop_name") or shop.get("username")
    sup["language"] = shop.get("language") or "ru"
    return sup


@_serialized
def unlink_supplier_telegram(shop_id: int, supplier_id: int) -> bool:
    """Отвязать чат и выдать новую ссылку (старая перестаёт работать)."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE suppliers SET tg_chat_id=NULL, link_token=NULL WHERE id=? AND shop_id=?",
                           (supplier_id, shop_id))
        conn.commit()
        return cur.rowcount > 0


@_serialized
def delete_supplier(shop_id: int, supplier_id: int) -> bool:
    """«Удалить» = убрать в архив. Заказы, оплаты и история цен остаются
    навсегда; поставщика можно вернуть из архива."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE suppliers SET is_active=0, archived_at=? WHERE id=? AND shop_id=? AND is_active=1",
                           (_now_str(), supplier_id, shop_id))
        conn.execute("UPDATE products SET supplier_id=NULL WHERE shop_id=? AND supplier_id=?", (shop_id, supplier_id))
        conn.commit()
        return cur.rowcount > 0


@_serialized
def restore_supplier(shop_id: int, supplier_id: int) -> dict:
    sup = get_supplier(shop_id, supplier_id, include_archived=True)
    if not sup or sup["is_active"]:
        return {"ok": False, "error": "not_found"}
    for s in list_suppliers(shop_id):
        if s["name"].upper() == sup["name"].upper():
            return {"ok": False, "error": "duplicate"}
    with get_conn() as conn:
        conn.execute("UPDATE suppliers SET is_active=1, archived_at=NULL WHERE id=? AND shop_id=?", (supplier_id, shop_id))
        conn.commit()
    return {"ok": True}


@_serialized
def assign_supplier_products(shop_id: int, supplier_id, product_ids: list) -> dict:
    """Набор товаров поставщика: отмеченные товары получают этого поставщика,
    снятые с отметки (были у него) — остаются без поставщика."""
    if not get_supplier(shop_id, supplier_id):
        return {"ok": False, "error": "not_found"}
    ids = set()
    for x in product_ids or []:
        try:
            ids.add(int(x))
        except (TypeError, ValueError):
            pass
    own = {p["id"] for p in list_products(shop_id)}
    ids &= own
    with get_conn() as conn:
        conn.execute("UPDATE products SET supplier_id=NULL WHERE shop_id=? AND supplier_id=?", (shop_id, supplier_id))
        for pid in ids:
            conn.execute("UPDATE products SET supplier_id=? WHERE id=? AND shop_id=?", (supplier_id, pid, shop_id))
        conn.commit()
    return {"ok": True, "count": len(ids)}


def order_network(shop_id: int) -> list:
    """Точки, на которые распределяется заказ: сама точка + филиалы со складом."""
    out = []
    for s in network_shops(shop_id):
        if s["is_head"] or (get_shop(s["id"]) or {}).get("warehouse_enabled"):
            out.append(s)
    return out


def suggest_order(shop_id: int, supplier_id=None) -> dict:
    """Черновик заказа: товары поставщика (или без поставщика) и сколько
    заказать — потребность самой точки + потребность её филиалов (по тем же
    правилам, что «Список закупки»: чтобы хватило примерно на месяц)."""
    shops = order_network(shop_id)
    head = {p["id"]: p for p in get_warehouse_overview(shop_id)["products"]}
    branch_maps = {}
    for s in shops:
        if not s["is_head"]:
            branch_maps[s["id"]] = {_norm_key(p["category"], p["name"]): p
                                    for p in get_warehouse_overview(s["id"])["products"]}
    lines = []
    for p in head.values():
        if (p.get("supplier_id") or None) != (supplier_id or None):
            continue
        alloc = {}
        if p["reorder_qty"] > 0:
            alloc[str(shop_id)] = p["reorder_qty"]
        key = _norm_key(p["category"], p["name"])
        for bid, bmap in branch_maps.items():
            bp = bmap.get(key)
            if bp and bp["reorder_qty"] > 0:
                alloc[str(bid)] = bp["reorder_qty"]
        total = sum(alloc.values())
        lines.append({"product_id": p["id"], "name": p["name"], "unit": p["unit"], "category": p["category"],
                      "purchase_price": p.get("purchase_price"), "stock_qty": p["stock_qty"],
                      "qty": total, "alloc": alloc})
    # сначала то, что пора заказать; остальные товары поставщика — ниже, с нулём
    lines.sort(key=lambda l: (l["qty"] <= 0, l["category"], l["name"].upper()))
    return {"ok": True, "lines": lines, "shops": shops}


def _clean_alloc(alloc, allowed_ids: set) -> dict:
    out = {}
    if isinstance(alloc, dict):
        for k, v in alloc.items():
            try:
                sid, q = int(k), float(v)
            except (TypeError, ValueError):
                continue
            if sid in allowed_ids and q > 0:
                out[str(sid)] = round(q, 3)
    return out


def _parse_order_lines(shop_id: int, lines: list):
    """Проверка строк заказа от клиента: товар своей точки, количество > 0.
    Возвращает (rows, error)."""
    products = {p["id"]: p for p in list_products(shop_id)}
    allowed = {s["id"] for s in order_network(shop_id)}
    rows, seen = [], set()
    for ln in lines or []:
        try:
            pid, q = int(ln["product_id"]), float(ln["qty"])
        except (KeyError, TypeError, ValueError):
            return None, "bad_request"
        if q <= 0 or pid in seen:
            continue
        p = products.get(pid)
        if not p:
            return None, "no_product"
        seen.add(pid)
        rows.append({"product_id": pid, "name": p["name"], "unit": p["unit"], "qty": round(q, 3),
                     "alloc": _clean_alloc(ln.get("alloc"), allowed)})
    if not rows:
        return None, "empty"
    return rows, None


@_serialized
def save_order(shop_id: int, supplier_id, lines: list, note=None, order_id: int = None) -> dict:
    """Создать новый черновик или переписать строки черновика."""
    if supplier_id and not get_supplier(shop_id, supplier_id):
        return {"ok": False, "error": "no_supplier"}
    rows, err = _parse_order_lines(shop_id, lines)
    if err:
        return {"ok": False, "error": err}
    with get_conn() as conn:
        try:
            if order_id:
                o = conn.execute("SELECT * FROM supplier_orders WHERE id=? AND shop_id=?", (order_id, shop_id)).fetchone()
                if not o:
                    return {"ok": False, "error": "not_found"}
                if o["status"] != "draft":
                    return {"ok": False, "error": "bad_status"}
                conn.execute("UPDATE supplier_orders SET supplier_id=?, note=? WHERE id=?",
                             (supplier_id or None, _clean_text(note, 300), order_id))
                conn.execute("DELETE FROM supplier_order_lines WHERE order_id=?", (order_id,))
            else:
                num = conn.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM supplier_orders WHERE shop_id=?",
                                   (shop_id,)).fetchone()[0]
                cur = conn.execute("""
                    INSERT INTO supplier_orders (shop_id, supplier_id, number, status, note, created_at)
                    VALUES (?, ?, ?, 'draft', ?, ?)
                """, (shop_id, supplier_id or None, num, _clean_text(note, 300), _now_str()))
                order_id = cur.lastrowid
            for r in rows:
                conn.execute("""
                    INSERT INTO supplier_order_lines (order_id, product_id, name, unit, qty_ordered, alloc_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (order_id, r["product_id"], r["name"], r["unit"], r["qty"],
                      json.dumps(r["alloc"]) if r["alloc"] else None))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"ok": True, "id": order_id}


def _order_row(conn, shop_id: int, order_id: int):
    row = conn.execute("SELECT * FROM supplier_orders WHERE id=? AND shop_id=?", (order_id, shop_id)).fetchone()
    return dict(row) if row else None


def get_order(shop_id: int, order_id: int):
    with get_conn() as conn:
        o = _order_row(conn, shop_id, order_id)
        if not o:
            return None
        sup = conn.execute("SELECT * FROM suppliers WHERE id=?", (o["supplier_id"],)).fetchone() if o["supplier_id"] else None
        lines = [dict(r) for r in conn.execute(
            "SELECT * FROM supplier_order_lines WHERE order_id=? ORDER BY id", (order_id,)).fetchall()]
    products = {p["id"]: p for p in list_products(shop_id, active_only=False)}
    for ln in lines:
        p = products.get(ln["product_id"]) or {}
        ln["alloc"] = json.loads(ln.pop("alloc_json") or "{}")
        ln["dist"] = json.loads(ln.pop("dist_json") or "{}")
        ln["category"] = p.get("category")
        ln["current_price"] = p.get("purchase_price")
        ln["stock_qty"] = p.get("stock_qty") if p.get("is_active") else None
    o["supplier"] = dict(sup) if sup else None
    o["lines"] = lines
    o["shops"] = order_network(shop_id)
    return o


def count_orders(shop_id: int) -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM supplier_orders WHERE shop_id=?", (shop_id,)).fetchone()[0]


def list_orders(shop_id: int, limit: int = 40, offset: int = 0) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT o.*, s.name AS supplier_name,
                   (SELECT COUNT(*) FROM supplier_order_lines l WHERE l.order_id=o.id) AS line_count,
                   (SELECT COALESCE(SUM(l.qty_ordered), 0) FROM supplier_order_lines l WHERE l.order_id=o.id) AS qty_total,
                   (SELECT COALESCE(SUM(COALESCE(l.qty_received, 0) * COALESCE(l.purchase_price, 0)), 0)
                      FROM supplier_order_lines l WHERE l.order_id=o.id) AS received_sum
            FROM supplier_orders o LEFT JOIN suppliers s ON s.id = o.supplier_id
            WHERE o.shop_id=?
            ORDER BY CASE o.status WHEN 'draft' THEN 0 WHEN 'sent' THEN 1 WHEN 'received' THEN 2 ELSE 3 END,
                     o.id DESC
            LIMIT ? OFFSET ?
        """, (shop_id, limit, offset)).fetchall()
        return [dict(r) for r in rows]


@_serialized
def mark_order_sent(shop_id: int, order_id: int) -> dict:
    with get_conn() as conn:
        o = _order_row(conn, shop_id, order_id)
        if not o:
            return {"ok": False, "error": "not_found"}
        if o["status"] == "sent":
            return {"ok": True}
        if o["status"] != "draft":
            return {"ok": False, "error": "bad_status"}
        conn.execute("UPDATE supplier_orders SET status='sent', sent_at=? WHERE id=?", (_now_str(), order_id))
        conn.commit()
    return {"ok": True}


@_serialized
def cancel_order(shop_id: int, order_id: int) -> dict:
    """Черновик удаляется совсем, отправленный заказ — помечается отменённым."""
    with get_conn() as conn:
        o = _order_row(conn, shop_id, order_id)
        if not o:
            return {"ok": False, "error": "not_found"}
        if o["status"] == "draft":
            conn.execute("DELETE FROM supplier_order_lines WHERE order_id=?", (order_id,))
            conn.execute("DELETE FROM supplier_orders WHERE id=?", (order_id,))
        elif o["status"] == "sent":
            conn.execute("UPDATE supplier_orders SET status='cancelled', done_at=? WHERE id=?", (_now_str(), order_id))
        else:
            return {"ok": False, "error": "bad_status"}
        conn.commit()
    return {"ok": True}


@_serialized
def receive_order(shop_id: int, order_id: int, lines: list) -> dict:
    """Приёмка: сколько пришло на самом деле и по какой цене. Всё одной
    транзакцией: остатки склада, история пополнений (с номером заказа), цена
    закупки товара. Если в заказе была доля филиалов — дальше шаг «раздать»."""
    by_line = {}
    for ln in lines or []:
        try:
            lid = int(ln["line_id"])
            q = float(ln.get("qty_received") or 0)
            price = ln.get("purchase_price")
            price = int(round(float(price))) if price not in (None, "") else None
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "bad_request"}
        if q < 0 or (price is not None and price < 0):
            return {"ok": False, "error": "bad_request"}
        by_line[lid] = (q, price)
    today = datetime.now().strftime("%Y-%m-%d")
    rate_now = shop_usd_rate(shop_id)  # курс дня приёмки — для эквивалента в $ навсегда
    backfills = []
    has_branch_share = False
    with get_conn() as conn:
        try:
            o = _order_row(conn, shop_id, order_id)
            if not o:
                return {"ok": False, "error": "not_found"}
            if o["status"] not in ORDER_OPEN_STATUSES:
                return {"ok": False, "error": "bad_status"}
            order_lines = conn.execute("SELECT * FROM supplier_order_lines WHERE order_id=?", (order_id,)).fetchall()
            if not any(by_line.get(l["id"], (0, None))[0] > 0 for l in order_lines):
                return {"ok": False, "error": "empty"}
            for l in order_lines:
                q, price = by_line.get(l["id"], (0, None))
                conn.execute("UPDATE supplier_order_lines SET qty_received=?, purchase_price=? WHERE id=?",
                             (q, price, l["id"]))
                if q <= 0:
                    continue
                p = conn.execute("SELECT * FROM products WHERE id=? AND shop_id=? AND is_active=1",
                                 (l["product_id"], shop_id)).fetchone()
                if not p:
                    conn.rollback()
                    return {"ok": False, "error": "no_product", "name": l["name"]}
                conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id=?", (q, p["id"]))
                if price is not None:
                    if p["purchase_price"] is None:
                        backfills.append((p["id"], price))
                    conn.execute("UPDATE products SET purchase_price=? WHERE id=?", (price, p["id"]))
                conn.execute("""
                    INSERT INTO stock_restocks (product_id, shop_id, quantity, purchase_price, restock_date, order_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (p["id"], shop_id, q, price, today, order_id))
                alloc = json.loads(l["alloc_json"] or "{}")
                if any(k != str(shop_id) and v > 0 for k, v in alloc.items()):
                    has_branch_share = True
            branches = [s for s in order_network(shop_id) if not s["is_head"]]
            status = "received" if (has_branch_share and branches) else "done"
            conn.execute("UPDATE supplier_orders SET status=?, received_at=?, done_at=?, usd_rate=? WHERE id=?",
                         (status, _now_str(), _now_str() if status == "done" else None, rate_now, order_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    for pid, price in backfills:
        backfill_cost_price(shop_id, pid, price)
    return {"ok": True, "status": status}


@_serialized
def distribute_order(shop_id: int, order_id: int, lines: list) -> dict:
    """Раздать полученный товар по филиалам: перемещения со склада главной на
    склады филиалов (как накладная), все филиалы — одной транзакцией. Пустое
    распределение = «оставить всё на своём складе»."""
    branch_ids = {s["id"] for s in order_network(shop_id) if not s["is_head"]}
    with get_conn() as conn:
        o = _order_row(conn, shop_id, order_id)
        if not o:
            return {"ok": False, "error": "not_found"}
        if o["status"] != "received":
            return {"ok": False, "error": "bad_status"}
        order_lines = {l["id"]: dict(l) for l in conn.execute(
            "SELECT * FROM supplier_order_lines WHERE order_id=?", (order_id,)).fetchall()}
    per_branch = {}       # branch_id -> {product_id: qty}
    dist_by_line = {}
    for ln in lines or []:
        try:
            lid = int(ln["line_id"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "bad_request"}
        l = order_lines.get(lid)
        if not l:
            return {"ok": False, "error": "bad_request"}
        alloc = _clean_alloc(ln.get("alloc"), branch_ids)
        if sum(alloc.values()) > (l["qty_received"] or 0) + 1e-9:
            return {"ok": False, "error": "too_much", "name": l["name"]}
        dist_by_line[lid] = alloc
        for k, q in alloc.items():
            per_branch.setdefault(int(k), {})
            per_branch[int(k)][l["product_id"]] = per_branch[int(k)].get(l["product_id"], 0) + q
    src_products = {p["id"]: p for p in list_products(shop_id)}
    need = {}
    for m in per_branch.values():
        for pid, q in m.items():
            need[pid] = need.get(pid, 0) + q
    problems = []
    for pid, q in need.items():
        p = src_products.get(pid)
        if not p:
            problems.append({"product_id": pid, "error": "no_product"})
        elif q > (p["stock_qty"] or 0) + 1e-9:
            problems.append({"product_id": pid, "name": p["name"], "error": "not_enough", "available": p["stock_qty"]})
    if problems:
        return {"ok": False, "error": "problems", "problems": problems}
    today = datetime.now().strftime("%Y-%m-%d")
    batch = f"Z{o['number']}-" + datetime.now().strftime("%y%m%d")
    backfills = []
    with get_conn() as conn:
        try:
            for bid, qty_by_pid in per_branch.items():
                for dst_id, price in _transfer_lines(conn, shop_id, shop_id, bid, qty_by_pid, src_products, today, batch):
                    backfills.append((bid, dst_id, price))
            for lid, alloc in dist_by_line.items():
                conn.execute("UPDATE supplier_order_lines SET dist_json=? WHERE id=?",
                             (json.dumps(alloc) if alloc else None, lid))
            conn.execute("UPDATE supplier_orders SET status='done', done_at=? WHERE id=?", (_now_str(), order_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    for bid, dst_id, price in backfills:
        backfill_cost_price(bid, dst_id, price)
    return {"ok": True, "batch": batch if per_branch else None, "branches": len(per_branch)}


@_serialized
def set_product_supplier(shop_id: int, product_id: int, supplier_id) -> bool:
    """Закрепить один товар за поставщиком (None — снять)."""
    if supplier_id and not get_supplier(shop_id, supplier_id):
        return False
    with get_conn() as conn:
        cur = conn.execute("UPDATE products SET supplier_id=? WHERE id=? AND shop_id=? AND is_active=1",
                           (supplier_id or None, product_id, shop_id))
        conn.commit()
        return cur.rowcount > 0


# ---------- Долг поставщику и история цен закупки ----------
# Долг = сумма принятых заказов поставщика (пришло × цена закупки) + долги,
# внесённые вручную (например, старый долг до начала работы в OilBook) −
# оплаты. Оплаты гасят самые старые долги первыми; если у поставщика задан
# срок оплаты (дней), видно, что уже просрочено.

def _usd(amount, rate):
    """Эквивалент в $ по курсу операции (None — курс в тот день не был задан)."""
    return round(amount / rate, 2) if amount and rate else (0 if not amount else None)


def _supplier_charges(conn, shop_id: int, supplier_id: int) -> list:
    """Все операции с поставщиком за всё время: принятые заказы (+долг),
    долги вручную (+) и оплаты (−). Отменённые оплаты тоже здесь (status
    'cancelled') — в долг они не входят, но в истории видны."""
    rows = conn.execute("""
        SELECT o.id, o.number, o.received_at, o.usd_rate,
               COALESCE(SUM(COALESCE(l.qty_received, 0) * COALESCE(l.purchase_price, 0)), 0) AS amount,
               SUM(CASE WHEN COALESCE(l.qty_received, 0) > 0 AND l.purchase_price IS NULL THEN 1 ELSE 0 END) AS unpriced,
               SUM(CASE WHEN COALESCE(l.qty_received, 0) > 0 THEN 1 ELSE 0 END) AS positions
        FROM supplier_orders o JOIN supplier_order_lines l ON l.order_id = o.id
        WHERE o.shop_id=? AND o.supplier_id=? AND o.status IN ('received', 'done')
        GROUP BY o.id
    """, (shop_id, supplier_id)).fetchall()
    out = [{"type": "order", "id": r["id"], "number": r["number"], "date": (r["received_at"] or "")[:10],
            "created_at": r["received_at"], "amount": int(round(r["amount"] or 0)), "unpriced": r["unpriced"] or 0,
            "positions": r["positions"] or 0, "usd_rate": r["usd_rate"], "status": "active"} for r in rows]
    for r in conn.execute("SELECT * FROM supplier_payments WHERE shop_id=? AND supplier_id=?",
                          (shop_id, supplier_id)).fetchall():
        out.append({"type": r["kind"], "id": r["id"], "date": r["pay_date"], "amount": r["amount"],
                    "note": r["note"], "order_id": r["order_id"], "created_at": r["created_at"],
                    "usd_rate": r["usd_rate"], "currency": r["currency"] or "UZS",
                    "amount_usd": (r["amount_usd_cents"] / 100) if r["amount_usd_cents"] is not None else None,
                    "method": r["method"], "status": r["status"] or "active",
                    "cancel_reason": r["cancel_reason"], "cancelled_at": r["cancelled_at"]})
    for e in out:
        # введено в $ — показываем ровно введённую сумму, иначе пересчёт по курсу дня
        e["usd"] = e.get("amount_usd") if e.get("amount_usd") is not None else _usd(e["amount"], e.get("usd_rate"))
    return out


def _live(entries):
    return [e for e in entries if e.get("status", "active") != "cancelled"]


def supplier_debt(shop_id: int, supplier_id: int, pay_days=None, entries=None) -> dict:
    if entries is None:
        with get_conn() as conn:
            entries = _supplier_charges(conn, shop_id, supplier_id)
    entries = _live(entries)
    charges = sorted([e for e in entries if e["type"] in ("order", "charge") and e["amount"] > 0],
                     key=lambda e: (e["date"], e["id"]))
    paid = sum(e["amount"] for e in entries if e["type"] == "payment")
    charged = sum(e["amount"] for e in charges)
    today = datetime.now().date()
    # оплата «сразу при приёмке» гасит именно свой заказ, остальные оплаты —
    # самые старые долги первыми
    rest_of = {(c["type"], c["id"]): c["amount"] for c in charges}
    left = 0
    for e in entries:
        if e["type"] != "payment":
            continue
        key = ("order", e.get("order_id"))
        if e.get("order_id") and key in rest_of:
            cover = min(rest_of[key], e["amount"])
            rest_of[key] -= cover
            left += e["amount"] - cover
        else:
            left += e["amount"]
    overdue = 0
    next_due = None
    oldest_overdue = None
    for c in charges:
        amount = rest_of[(c["type"], c["id"])]
        cover = min(left, amount)
        left -= cover
        rest = amount - cover
        if rest <= 0 or pay_days is None:
            continue
        try:
            due = datetime.strptime(c["date"], "%Y-%m-%d").date() + timedelta(days=int(pay_days))
        except ValueError:
            continue
        if due < today:
            overdue += rest
            oldest_overdue = oldest_overdue or due.isoformat()
        elif next_due is None or due.isoformat() < next_due["date"]:
            next_due = {"date": due.isoformat(), "amount": rest}
    return {"charged": charged, "paid": paid, "balance": charged - paid, "overdue": overdue,
            "oldest_overdue": oldest_overdue, "next_due": next_due,
            "unpriced_orders": sum(1 for e in entries if e["type"] == "order" and e.get("unpriced"))}


def _period_totals(entries) -> dict:
    """Итоги за период: сколько взяли товара и сколько оплатили — в сумах и в $
    по курсу каждой операции."""
    t = {"bought": 0, "bought_usd": 0.0, "paid": 0, "paid_usd": 0.0, "no_rate": 0}
    for e in _live(entries):
        k = "paid" if e["type"] == "payment" else "bought"
        t[k] += e["amount"]
        if e.get("usd") is None:
            t["no_rate"] += 1
        else:
            t[k + "_usd"] += e["usd"]
    t["bought_usd"] = round(t["bought_usd"], 2)
    t["paid_usd"] = round(t["paid_usd"], 2)
    return t


def supplier_price_history(shop_id: int, supplier_id: int) -> list:
    """Цены закупки товаров у поставщика по принятым заказам: как менялась
    цена и на сколько процентов по сравнению с прошлой и с первой. Вся
    история, без обрезки."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT l.product_id, l.name, l.unit, l.purchase_price, l.qty_received, o.number, o.received_at, o.usd_rate
            FROM supplier_order_lines l JOIN supplier_orders o ON o.id = l.order_id
            WHERE o.shop_id=? AND o.supplier_id=? AND o.status IN ('received', 'done')
              AND l.purchase_price IS NOT NULL AND COALESCE(l.qty_received, 0) > 0
            ORDER BY o.received_at, o.id
        """, (shop_id, supplier_id)).fetchall()
    by = {}
    for r in rows:
        e = by.setdefault(r["product_id"], {"product_id": r["product_id"], "name": r["name"], "unit": r["unit"], "history": []})
        e["name"] = r["name"]
        e["history"].append({"date": (r["received_at"] or "")[:10], "price": r["purchase_price"],
                             "qty": r["qty_received"], "number": r["number"],
                             "usd": _usd(r["purchase_price"], r["usd_rate"])})
    out = []
    for e in by.values():
        h = e["history"]
        last = h[-1]["price"]
        prev = next((x["price"] for x in reversed(h[:-1]) if x["price"] != last), None)
        first = h[0]["price"]
        e.update({"last": last, "last_usd": h[-1]["usd"], "last_date": h[-1]["date"], "prev": prev,
                  "change_pct": round((last - prev) / prev * 100, 1) if prev else None,
                  "since_first_pct": round((last - first) / first * 100, 1) if first and len(h) > 2 and first not in (last, prev) else None,
                  "_sort": (h[-1]["date"], h[-1]["number"])})
        e["history"] = list(reversed(h))
        out.append(e)
    out.sort(key=lambda e: e.pop("_sort"), reverse=True)
    return out


def _entry_sort_key(e):
    return (e["date"] or "", e.get("created_at") or "", e["id"])


def supplier_card(shop_id: int, supplier_id: int, year=None, offset: int = 0, limit: int = 100):
    """Карточка поставщика. Долг считается по ВСЕЙ истории; список операций —
    за выбранный год (или за все годы) порциями по limit, чтобы и через 10
    лет всё открывалось быстро и ничего не терялось."""
    sup = get_supplier(shop_id, supplier_id, include_archived=True)
    if not sup:
        return None
    with get_conn() as conn:
        entries = _supplier_charges(conn, shop_id, supplier_id)
        orders = conn.execute("""
            SELECT COUNT(*) AS n, MAX(created_at) AS last FROM supplier_orders
            WHERE shop_id=? AND supplier_id=? AND status != 'cancelled'
        """, (shop_id, supplier_id)).fetchone()
    debt = supplier_debt(shop_id, supplier_id, sup.get("pay_days"), entries)
    years = sorted({e["date"][:4] for e in entries if e.get("date")}, reverse=True)
    year = str(year) if year and str(year) in years else None
    chosen = [e for e in entries if not year or (e.get("date") or "").startswith(year)]
    ops = sorted(chosen, key=_entry_sort_key, reverse=True)
    offset = max(0, int(offset or 0))
    return {"supplier": sup, "debt": debt, "entries": ops[offset:offset + limit], "total_entries": len(ops),
            "offset": offset, "years": years, "year": year, "period": _period_totals(chosen),
            "all_time": _period_totals(entries), "prices": supplier_price_history(shop_id, supplier_id),
            "order_count": orders["n"], "last_order": orders["last"]}


def supplier_statement(shop_id: int, supplier_id: int, date_from: str = None, date_to: str = None):
    """Акт сверки: долг на начало периода, все операции периода с остатком
    после каждой и долг на конец. Отменённые оплаты не входят."""
    sup = get_supplier(shop_id, supplier_id, include_archived=True)
    if not sup:
        return None
    with get_conn() as conn:
        entries = _live(_supplier_charges(conn, shop_id, supplier_id))
    entries.sort(key=_entry_sort_key)
    sign = lambda e: -e["amount"] if e["type"] == "payment" else e["amount"]
    opening = sum(sign(e) for e in entries if date_from and e["date"] < date_from)
    rows, bal = [], opening
    for e in entries:
        if (date_from and e["date"] < date_from) or (date_to and e["date"] > date_to):
            continue
        bal += sign(e)
        rows.append({**e, "balance": bal})
    return {"supplier": sup, "opening": opening, "closing": bal, "rows": rows,
            "date_from": date_from, "date_to": date_to}


def supplier_totals(suppliers: list) -> dict:
    return {"owe": sum(s["balance"] for s in suppliers if s["balance"] > 0),
            "overpaid": sum(-s["balance"] for s in suppliers if s["balance"] < 0),
            "overdue": sum(s["overdue"] for s in suppliers),
            "overdue_count": sum(1 for s in suppliers if s["overdue"] > 0)}


PAY_METHODS = ("cash", "card", "transfer")
MAX_MONEY = 10 ** 13


@_serialized
def add_supplier_payment(shop_id: int, supplier_id: int, kind: str, amount=None, pay_date=None, note=None,
                         order_id=None, currency: str = "UZS", amount_usd=None, rate=None, method=None,
                         client_token=None) -> dict:
    """Оплата поставщику или долг вручную. Долг всегда ведётся в сумах; если
    сумма введена в долларах — переводим по указанному курсу и сохраняем
    и сумы, и доллары, и курс. Курс по умолчанию — курс точки (как на складе).
    client_token защищает от двойной записи при повторной отправке."""
    if kind not in ("payment", "charge"):
        return {"ok": False, "error": "bad_request"}
    if not get_supplier(shop_id, supplier_id):
        return {"ok": False, "error": "not_found"}
    currency = "USD" if str(currency or "").upper() == "USD" else "UZS"
    try:
        rate = float(rate) if rate not in (None, "") else None
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_rate"}
    if rate is not None and not (0 < rate < 1_000_000):
        return {"ok": False, "error": "bad_rate"}
    cents = None
    try:
        if currency == "USD":
            usd = float(amount_usd)
            if not rate:
                return {"ok": False, "error": "bad_rate"}
            cents = int(round(usd * 100))
            amount = int(round(cents * rate / 100))
            if cents <= 0:
                return {"ok": False, "error": "bad_amount"}
        else:
            amount = int(round(float(amount)))
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_amount"}
    if amount <= 0 or amount >= MAX_MONEY:
        return {"ok": False, "error": "bad_amount"}
    if rate is None:
        rate = shop_usd_rate(shop_id)
    method = method if method in PAY_METHODS else None
    pay_date = (pay_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    try:
        d = datetime.strptime(pay_date, "%Y-%m-%d").date()
    except ValueError:
        return {"ok": False, "error": "bad_date"}
    if d.year < 2000 or d > datetime.now().date() + timedelta(days=1):
        return {"ok": False, "error": "bad_date"}
    token = _clean_text(client_token, 64)
    with get_conn() as conn:
        if token:
            dup = conn.execute("SELECT id FROM supplier_payments WHERE shop_id=? AND client_token=?",
                               (shop_id, token)).fetchone()
            if dup:
                return {"ok": True, "id": dup["id"], "duplicate": True}
        try:
            cur = conn.execute("""
                INSERT INTO supplier_payments (shop_id, supplier_id, kind, amount, pay_date, note, order_id,
                                               currency, amount_usd_cents, usd_rate, method, status, client_token, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """, (shop_id, supplier_id, kind, amount, pay_date, _clean_text(note, 200), order_id,
                  currency, cents, rate, method, token, _now_str()))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            dup = conn.execute("SELECT id FROM supplier_payments WHERE shop_id=? AND client_token=?",
                               (shop_id, token)).fetchone()
            if dup:
                return {"ok": True, "id": dup["id"], "duplicate": True}
            raise
    return {"ok": True, "id": cur.lastrowid, "amount": amount}


@_serialized
def cancel_supplier_payment(shop_id: int, supplier_id: int, payment_id: int, reason=None) -> bool:
    """Оплату/долг не стираем: помечаем «отменено» с причиной — запись
    остаётся в истории зачёркнутой и больше не влияет на долг."""
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE supplier_payments SET status='cancelled', cancel_reason=?, cancelled_at=?
            WHERE id=? AND shop_id=? AND supplier_id=? AND COALESCE(status, 'active') != 'cancelled'
        """, (_clean_text(reason, 200), _now_str(), payment_id, shop_id, supplier_id))
        conn.commit()
        return cur.rowcount > 0


def order_amount(shop_id: int, order_id: int) -> int:
    with get_conn() as conn:
        r = conn.execute("""
            SELECT COALESCE(SUM(COALESCE(l.qty_received, 0) * COALESCE(l.purchase_price, 0)), 0)
            FROM supplier_order_lines l JOIN supplier_orders o ON o.id = l.order_id
            WHERE o.id=? AND o.shop_id=?
        """, (order_id, shop_id)).fetchone()
        return int(round(r[0] or 0))


def get_overdue_supplier_debts() -> list:
    """Для бота: поставщики с просроченным долгом, о которых владельцу ещё
    не напоминали последние 3 дня."""
    since = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, sh.notify_telegram_id, sh.language, sh.shop_name, sh.username
            FROM suppliers s JOIN shops sh ON sh.id = s.shop_id
            WHERE s.is_active=1 AND s.pay_days IS NOT NULL AND sh.notify_telegram_id IS NOT NULL
              AND sh.notify_telegram_id != '' AND (s.debt_reminded_at IS NULL OR s.debt_reminded_at < ?)
        """, (since,)).fetchall()
    out = []
    for r in rows:
        d = supplier_debt(r["shop_id"], r["id"], r["pay_days"])
        if d["overdue"] > 0:
            out.append({**dict(r), "debt": d})
    return out


@_serialized
def mark_supplier_debt_reminded(supplier_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE suppliers SET debt_reminded_at=? WHERE id=?", (_now_str(), supplier_id))
        conn.commit()



# ======================================================================
# ПОДПИСКА ПЛАТФОРМЫ
# ======================================================================
# Платит главная точка (role='shop') за всю сеть: 199 000 за главную +
# 99 000 за каждый включённый филиал в месяц (цены и скидки — в настройках
# админки). Дата «оплачено до» хранится у главной; филиалы и сотрудники
# живут по ней. Последний оплаченный день работает весь, на следующий день
# вход блокируется (без льготного периода). Данные при этом не трогаются.
#   paid_until   — последний оплаченный день (YYYY-MM-DD); NULL = дата ещё не
#                  задана админом → точка работает как раньше (так все уже
#                  существующие точки не отключатся в день обновления)
#   license_type — 'sub' (подписка) или 'lifetime' (куплено разово, ∞)
#   branch_pending — у филиала: создан, но ещё не оплачен → не работает
# Новый филиал оплачивается за оставшиеся до общей даты дни со скидкой
# последнего оплаченного срока; у бессрочной сети — 100 $ разово (отмечает админ).

SUB_TERMS = (1, 3, 6, 12)
SUB_DEFAULTS = {
    "price_main": 199000,
    "price_branch": 99000,
    "disc_1": 0, "disc_3": 5, "disc_6": 15, "disc_12": 30,
    "card_number": "",
    "card_holder": "",
    "support_contact": "",
}
_SUB_INT_KEYS = ("price_main", "price_branch", "disc_1", "disc_3", "disc_6", "disc_12")
# Чеки на сервере НЕ хранятся: файл сразу уходит администратору в Telegram,
# в базе остаётся только его file_id (по нему админка показывает чек).


def _migrate_subscription(conn):
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(shops)").fetchall()}
    for col, ddl in {
        "paid_until": "TEXT",
        "license_type": "TEXT DEFAULT 'sub'",
        "branch_pending": "INTEGER DEFAULT 0",
        "last_period_months": "INTEGER",
        "sub_notice": "TEXT",
        "custom_price": "INTEGER",
    }.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE shops ADD COLUMN {col} {ddl}")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sub_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        months INTEGER,
        discount INTEGER DEFAULT 0,
        amount INTEGER,
        branch_count INTEGER DEFAULT 0,
        branch_ids TEXT,
        method TEXT DEFAULT 'card',
        status TEXT DEFAULT 'pending',
        receipt_file TEXT,
        receipt_mime TEXT,
        tg_message_id INTEGER,
        tg_file_id TEXT,
        new_until TEXT,
        note TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        decided_at TEXT
    )
    """)
    pay_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sub_payments)").fetchall()}
    if "tg_file_id" not in pay_cols:
        conn.execute("ALTER TABLE sub_payments ADD COLUMN tg_file_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_payments_shop ON sub_payments(shop_id, status)")
    # раньше каждое включение «∞» добавляло новую запись о продаже (и выключение
    # её не убирало) — оставляем по одной действующей на бессрочную точку
    for sh in conn.execute("SELECT id, COALESCE(license_type, 'sub') AS lt FROM shops WHERE role='shop'").fetchall():
        rows = conn.execute("SELECT id FROM sub_payments WHERE shop_id=? AND kind='lifetime' AND status='confirmed' "
                            "ORDER BY id DESC", (sh["id"],)).fetchall()
        extra = rows[1:] if sh["lt"] == "lifetime" else rows
        for r in extra:
            conn.execute("UPDATE sub_payments SET status='cancelled' WHERE id=?", (r["id"],))
    conn.execute("""
    CREATE TABLE IF NOT EXISTS platform_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.commit()


def get_platform_settings() -> dict:
    out = dict(SUB_DEFAULTS)
    with get_conn() as conn:
        for r in conn.execute("SELECT key, value FROM platform_settings").fetchall():
            k, v = r["key"], r["value"]
            if k not in SUB_DEFAULTS:
                continue
            if k in _SUB_INT_KEYS:
                try:
                    out[k] = int(float(v))
                except (TypeError, ValueError):
                    pass
            else:
                out[k] = v or ""
    return out


@_serialized
def set_platform_settings(values: dict):
    with get_conn() as conn:
        for k, v in values.items():
            if k not in SUB_DEFAULTS:
                continue
            if k in _SUB_INT_KEYS:
                v = str(max(0, int(float(v))))
            else:
                v = str(v or "").strip()
            conn.execute("INSERT INTO platform_settings(key, value) VALUES(?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        conn.commit()


def _round_k(x) -> int:
    """Округление суммы до тысячи сумов."""
    return int(float(x) / 1000.0 + 0.5) * 1000


def _parse_day(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _today():
    return datetime.now().date()


def sub_head(shop: dict):
    """Главная точка, которая платит за эту (для филиала — его главная)."""
    if shop and shop.get("role") == "branch" and shop.get("parent_shop_id"):
        return get_shop(shop["parent_shop_id"]) or shop
    return shop


def subscription_state(shop: dict) -> dict:
    """Можно ли этой точке работать прямо сейчас — для входа и баннера."""
    head = sub_head(shop) or {}
    lifetime = (head.get("license_type") or "sub") == "lifetime"
    until = _parse_day(head.get("paid_until"))
    today = _today()
    days_left = (until - today).days if until else None
    expired = bool(not lifetime and until and today > until)
    pending = bool(shop and shop.get("role") == "branch" and shop.get("branch_pending"))
    reason = "expired" if expired else ("branch_pending" if pending else None)
    return {
        "head_id": head.get("id"),
        "lifetime": lifetime,
        "paid_until": until.strftime("%Y-%m-%d") if until else None,
        "days_left": days_left,
        "expired": expired,
        "blocked": bool(reason),
        "reason": reason,
    }


def _sub_discount(settings: dict, months) -> int:
    try:
        return int(settings.get(f"disc_{int(months)}", 0) or 0)
    except (TypeError, ValueError):
        return 0


def head_main_price(head: dict, settings: dict) -> int:
    """Цена главной точки в месяц: индивидуальная (если админ задал) или общая."""
    cp = head.get("custom_price") if head else None
    return int(cp) if cp else settings["price_main"]


def sub_quote(head_id: int) -> dict:
    """Всё, что нужно экрану «Подписка»: статус, цена сети в месяц, варианты
    сроков с суммами и, если есть, оплата новых филиалов."""
    head = get_shop(head_id)
    settings = get_platform_settings()
    branches = [b for b in get_branches(head_id) if b.get("is_active")]
    pending = [b for b in branches if b.get("branch_pending")]
    n = len(branches)
    custom = bool(head.get("custom_price"))
    monthly = head_main_price(head, settings) + settings["price_branch"] * n
    state = subscription_state(head)
    today = _today()
    until = _parse_day(head.get("paid_until"))
    active_period = bool(until and until >= today)

    branch_part = None
    if pending and not state["lifetime"] and active_period:
        days = max(1, (until - today).days)
        disc = 0 if custom else _sub_discount(settings, head.get("last_period_months") or 1)
        amount = _round_k(settings["price_branch"] * len(pending) * days / 30.0 * (100 - disc) / 100.0)
        branch_part = {"amount": amount, "days": days, "discount": disc,
                       "until": until.strftime("%Y-%m-%d")}

    base = until if active_period else today
    options = []
    for m in SUB_TERMS:
        # индивидуальная цена — уже особые условия, скидки за срок к ней не применяются
        disc = 0 if custom else _sub_discount(settings, m)
        full = monthly * m
        amount = _round_k(full * (100 - disc) / 100.0)
        if branch_part:
            amount += branch_part["amount"]
            full += branch_part["amount"]
        options.append({
            "months": m, "discount": disc, "amount": amount,
            "per_month": int(round(amount / m / 100.0)) * 100,
            "saving": max(0, full - amount),
            "new_until": (base + relativedelta(months=m)).strftime("%Y-%m-%d"),
        })
    return {
        "head_id": head_id,
        "state": state,
        "settings": settings,
        "branch_count": n,
        "monthly": monthly,
        "custom_price": head.get("custom_price"),
        "pending_branches": [{"id": b["id"], "name": b.get("shop_name") or b["username"]} for b in pending],
        "branch_part": branch_part,
        "options": options,
    }


def get_pending_sub_payment(head_id: int):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM sub_payments WHERE shop_id=? AND status='pending' "
                         "ORDER BY id DESC LIMIT 1", (head_id,)).fetchone()
        return dict(r) if r else None


def get_sub_payment(payment_id: int):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM sub_payments WHERE id=?", (payment_id,)).fetchone()
        return dict(r) if r else None


def list_sub_payments(head_id: int = None, status: str = None, limit: int = 50) -> list:
    q = ("SELECT p.*, s.shop_name, s.username FROM sub_payments p "
         "LEFT JOIN shops s ON s.id = p.shop_id WHERE 1=1")
    args = []
    if head_id:
        q += " AND p.shop_id=?"
        args.append(head_id)
    if status:
        q += " AND p.status=?"
        args.append(status)
    q += " ORDER BY p.id DESC LIMIT ?"
    args.append(int(limit))
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]


@_serialized
def create_sub_payment(head_id: int, kind: str, months, amount: int, discount: int,
                       branch_ids: list, branch_count: int, new_until: str = None) -> int:
    """Заявка на оплату по чеку (статус 'sending' — пока чек не дошёл до
    Telegram администратора; после этого — 'pending', см. sub_payment_sent)."""
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO sub_payments (shop_id, kind, months, discount, amount, branch_count, branch_ids,
                                      method, status, new_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'card', 'sending', ?)
        """, (head_id, kind, months, discount, amount, branch_count, json.dumps(branch_ids or []), new_until))
        conn.commit()
        return cur.lastrowid


@_serialized
def sub_payment_sent(payment_id: int, message_id, file_id: str, mime: str):
    """Чек дошёл до Telegram: заявка становится «на проверке», а прежняя
    непроверенная заявка этой точки заменяется (человек мог ошибиться и
    отправить чек ещё раз)."""
    with get_conn() as conn:
        row = conn.execute("SELECT shop_id FROM sub_payments WHERE id=?", (payment_id,)).fetchone()
        if not row:
            return
        conn.execute("UPDATE sub_payments SET status='replaced', decided_at=datetime('now','localtime') "
                     "WHERE shop_id=? AND status='pending' AND id!=?", (row["shop_id"], payment_id))
        conn.execute("UPDATE sub_payments SET status='pending', tg_message_id=?, tg_file_id=?, receipt_mime=? "
                     "WHERE id=?", (message_id, file_id, mime, payment_id))
        conn.commit()


@_serialized
def sub_payment_failed(payment_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE sub_payments SET status='failed', decided_at=datetime('now','localtime') WHERE id=?",
                     (payment_id,))
        conn.commit()


def _extend_head(conn, head_id: int, months: int, from_day):
    """Продлевает сеть на months от from_day или от текущей даты оплаты, если
    она позже (оплаченные заранее дни не пропадают). Возвращает новую дату."""
    row = conn.execute("SELECT paid_until FROM shops WHERE id=?", (head_id,)).fetchone()
    until = _parse_day(row["paid_until"]) if row else None
    base = until if (until and until >= from_day) else from_day
    new_until = (base + relativedelta(months=int(months))).strftime("%Y-%m-%d")
    conn.execute("UPDATE shops SET paid_until=?, last_period_months=?, sub_notice=NULL WHERE id=?",
                 (new_until, int(months), head_id))
    return new_until


def _clear_branch_pending(conn, head_id: int, branch_ids):
    if branch_ids is None:
        conn.execute("UPDATE shops SET branch_pending=0 WHERE parent_shop_id=?", (head_id,))
        return
    for bid in branch_ids:
        conn.execute("UPDATE shops SET branch_pending=0 WHERE id=? AND parent_shop_id=?", (int(bid), head_id))


@_serialized
def confirm_sub_payment(payment_id: int):
    """Подтверждение чека. Возвращает обновлённую заявку или None, если её
    уже обработали (повторное нажатие, вторая кнопка и т.п.)."""
    with get_conn() as conn:
        p = conn.execute("SELECT * FROM sub_payments WHERE id=?", (payment_id,)).fetchone()
        if not p or p["status"] != "pending":
            return None
        p = dict(p)
        try:
            branch_ids = json.loads(p.get("branch_ids") or "[]")
        except ValueError:
            branch_ids = []
        new_until = None
        created = _parse_day(p.get("created_at")) or _today()
        if p["kind"] in ("extend", "both") and p.get("months"):
            new_until = _extend_head(conn, p["shop_id"], p["months"], created)
        if p["kind"] in ("branches", "both", "extend"):
            _clear_branch_pending(conn, p["shop_id"], branch_ids)
        if new_until is None:
            row = conn.execute("SELECT paid_until FROM shops WHERE id=?", (p["shop_id"],)).fetchone()
            new_until = row["paid_until"] if row else None
        conn.execute("UPDATE sub_payments SET status='confirmed', new_until=?, "
                     "decided_at=datetime('now','localtime') WHERE id=?", (new_until, payment_id))
        conn.commit()
        p.update(status="confirmed", new_until=new_until)
        return p


@_serialized
def reject_sub_payment(payment_id: int):
    with get_conn() as conn:
        p = conn.execute("SELECT * FROM sub_payments WHERE id=?", (payment_id,)).fetchone()
        if not p or p["status"] != "pending":
            return None
        conn.execute("UPDATE sub_payments SET status='rejected', decided_at=datetime('now','localtime') "
                     "WHERE id=?", (payment_id,))
        conn.commit()
        d = dict(p)
        d["status"] = "rejected"
        return d


@_serialized
def admin_extend_subscription(head_id: int, months: int, amount=None) -> str:
    """Оплата наличными — админ продлевает вручную (с записью в историю)."""
    with get_conn() as conn:
        new_until = _extend_head(conn, head_id, months, _today())
        _clear_branch_pending(conn, head_id, None)
        conn.execute("""
            INSERT INTO sub_payments (shop_id, kind, months, amount, method, status, new_until, decided_at)
            VALUES (?, 'extend', ?, ?, 'cash', 'confirmed', ?, datetime('now','localtime'))
        """, (head_id, int(months), amount, new_until))
        conn.commit()
        return new_until


@_serialized
def admin_set_paid_until(head_id: int, day: str = None):
    d = _parse_day(day) if day else None
    with get_conn() as conn:
        conn.execute("UPDATE shops SET paid_until=?, sub_notice=NULL WHERE id=?",
                     (d.strftime("%Y-%m-%d") if d else None, head_id))
        conn.commit()


@_serialized
def admin_set_lifetime(head_id: int, on: bool, amount=None):
    """Разовая покупка (∞). Сумму в сумах вписывает админ — она идёт в
    статистику доходов. Снятие ∞ отменяет запись о продаже."""
    with get_conn() as conn:
        conn.execute("UPDATE shops SET license_type=? WHERE id=?", ("lifetime" if on else "sub", head_id))
        conn.execute("UPDATE sub_payments SET status='cancelled' WHERE shop_id=? AND kind='lifetime' "
                     "AND status='confirmed'", (head_id,))
        if on:
            conn.execute("""
                INSERT INTO sub_payments (shop_id, kind, amount, method, status, note, decided_at)
                VALUES (?, 'lifetime', ?, 'cash', 'confirmed', 'разовая покупка', datetime('now','localtime'))
            """, (head_id, amount))
        conn.commit()


@_serialized
def admin_set_custom_price(head_id: int, price=None):
    with get_conn() as conn:
        conn.execute("UPDATE shops SET custom_price=? WHERE id=? AND role='shop'",
                     (int(price) if price else None, head_id))
        conn.commit()


@_serialized
def admin_set_payment_amount(payment_id: int, amount) -> bool:
    """Исправить сумму оплаты, внесённой вручную (наличные, разовая покупка)."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE sub_payments SET amount=? WHERE id=? AND status='confirmed' AND method='cash'",
                           (int(amount) if amount else None, payment_id))
        conn.commit()
        return cur.rowcount > 0


@_serialized
def admin_cancel_payment(payment_id: int) -> bool:
    """Убрать ошибочную запись об оплате из статистики (дату оплаты не
    трогает — её админ при необходимости правит кнопкой «Дата»)."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE sub_payments SET status='cancelled' WHERE id=? AND status='confirmed'", (payment_id,))
        conn.commit()
        return cur.rowcount > 0


@_serialized
def set_branch_pending(branch_id: int, pending: bool):
    with get_conn() as conn:
        conn.execute("UPDATE shops SET branch_pending=? WHERE id=? AND role='branch'", (1 if pending else 0, branch_id))
        conn.commit()


@_serialized
def admin_mark_branch_paid(branch_id: int, amount=None) -> bool:
    """Филиал оплачен вручную (наличные или разово у бессрочной сети);
    сумму в сумах вписывает админ."""
    with get_conn() as conn:
        b = conn.execute("SELECT id, parent_shop_id FROM shops WHERE id=? AND role='branch'", (branch_id,)).fetchone()
        if not b:
            return False
        conn.execute("UPDATE shops SET branch_pending=0 WHERE id=?", (branch_id,))
        conn.execute("""
            INSERT INTO sub_payments (shop_id, kind, amount, branch_count, branch_ids, method, status, note, decided_at)
            VALUES (?, 'branches', ?, 1, ?, 'cash', 'confirmed', 'филиал оплачен вручную', datetime('now','localtime'))
        """, (b["parent_shop_id"], int(amount) if amount else None, json.dumps([branch_id])))
        conn.commit()
        return True


def new_branch_needs_payment(head: dict) -> bool:
    """Нужно ли новому филиалу ждать оплаты: да — у бессрочной сети (100 $
    разово) и у сети на подписке с заданной датой. Если дата ещё не задана
    (старый клиент), филиал работает сразу, как и раньше."""
    if not head:
        return False
    if (head.get("license_type") or "sub") == "lifetime":
        return True
    return bool(head.get("paid_until"))


def get_due_sub_notices() -> list:
    """Для бота: кому из владельцев пора напомнить (за 5, 3, 1 день) или
    сообщить о блокировке. Каждое событие отправляется один раз."""
    today = _today()
    out = []
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM shops WHERE role='shop' AND is_active=1 AND paid_until IS NOT NULL
              AND COALESCE(license_type, 'sub') != 'lifetime'
        """).fetchall()
    for r in rows:
        r = dict(r)
        until = _parse_day(r.get("paid_until"))
        if not until:
            continue
        left = (until - today).days
        if left in (5, 3, 1):
            code = f"d{left}"
        elif left < 0:
            code = "blocked"
        else:
            continue
        key = f"{r['paid_until']}:{code}"
        if r.get("sub_notice") == key:
            continue
        if code == "blocked" and left < -3:
            continue  # о старых блокировках не пишем повторно (например, после восстановления базы)
        out.append({"shop": r, "code": code, "days_left": left, "key": key})
    return out


@_serialized
def mark_sub_notice(head_id: int, key: str):
    with get_conn() as conn:
        conn.execute("UPDATE shops SET sub_notice=? WHERE id=?", (key, head_id))
        conn.commit()


def get_income_stats() -> dict:
    """Для вкладки «Доходы» в админке: сколько точек на подписке, сколько
    денег приходит, кто скоро платит, кто не продлил."""
    today = _today()
    settings = get_platform_settings()
    with get_conn() as conn:
        heads = [dict(r) for r in conn.execute(
            "SELECT * FROM shops WHERE role='shop' ORDER BY shop_name COLLATE NOCASE").fetchall()]
        branches = [dict(r) for r in conn.execute(
            "SELECT id, parent_shop_id, is_active FROM shops WHERE role='branch'").fetchall()]
        pays = [dict(r) for r in conn.execute("""
            SELECT p.*, s.shop_name, s.username FROM sub_payments p LEFT JOIN shops s ON s.id = p.shop_id
            WHERE p.status IN ('confirmed', 'pending') ORDER BY COALESCE(p.decided_at, p.created_at) DESC, p.id DESC
        """).fetchall()]
    br_count = {}
    for b in branches:
        if b["is_active"]:
            br_count[b["parent_shop_id"]] = br_count.get(b["parent_shop_id"], 0) + 1

    counts = {"total": 0, "paying": 0, "lifetime": 0, "unset": 0, "blocked": 0, "soon": 0, "off": 0}
    mrr = 0
    expected, blocked = [], []
    for h in heads:
        counts["total"] += 1
        if not h.get("is_active"):
            counts["off"] += 1
            continue
        monthly = head_main_price(h, settings) + settings["price_branch"] * br_count.get(h["id"], 0)
        name = h.get("shop_name") or h["username"]
        if (h.get("license_type") or "sub") == "lifetime":
            counts["lifetime"] += 1
            continue
        until = _parse_day(h.get("paid_until"))
        if not until:
            counts["unset"] += 1
            continue
        left = (until - today).days
        if left < 0:
            counts["blocked"] += 1
            blocked.append({"id": h["id"], "name": name, "paid_until": until.strftime("%Y-%m-%d"),
                            "days": -left, "monthly": monthly})
            continue
        counts["paying"] += 1
        mrr += monthly
        if left <= 5:
            counts["soon"] += 1
        if left <= 30:
            expected.append({"id": h["id"], "name": name, "paid_until": until.strftime("%Y-%m-%d"),
                             "days": left, "monthly": monthly})
    expected.sort(key=lambda x: x["days"])
    blocked.sort(key=lambda x: x["days"])

    # деньги по месяцам (последние 12): «получено» — в месяц оплаты;
    # «в пересчёте» — оплата за N месяцев делится поровну на эти месяцы
    months = []
    d = today.replace(day=1)
    for i in range(11, -1, -1):
        months.append((d - relativedelta(months=i)).strftime("%Y-%m"))
    received = {m: 0 for m in months}
    spread = {m: 0 for m in months}
    terms = {1: 0, 3: 0, 6: 0, 12: 0}
    lifetime_sales = lifetime_sum = 0
    branch_cash = branch_cash_sum = 0
    pending_sum, pending_n = 0, 0
    journal = []
    for p in pays:
        if p["status"] == "pending":
            pending_sum += int(p.get("amount") or 0)
            pending_n += 1
            continue
        if p["kind"] == "lifetime":
            lifetime_sales += 1
            lifetime_sum += int(p.get("amount") or 0)
        if p["kind"] == "branches" and p.get("method") == "cash":
            branch_cash += 1
            branch_cash_sum += int(p.get("amount") or 0)
        amount = int(p.get("amount") or 0)
        day = (p.get("decided_at") or p.get("created_at") or "")[:10]
        ym = day[:7]
        if ym in received:
            received[ym] += amount
        if p["kind"] in ("extend", "both") and p.get("months"):
            if int(p["months"]) in terms:
                terms[int(p["months"])] += 1
            start = _parse_day(day)
            if start and amount:
                m = int(p["months"])
                part = amount / m
                for k in range(m):
                    key = (start.replace(day=1) + relativedelta(months=k)).strftime("%Y-%m")
                    if key in spread:
                        spread[key] += part
        elif ym in spread:
            spread[ym] += amount
        if len(journal) < 15:
            journal.append({"id": p["id"], "date": day, "name": p.get("shop_name") or p.get("username") or "—",
                            "kind": p["kind"], "months": p.get("months"), "amount": amount or None,
                            "method": p.get("method") or "card"})
    this_m = months[-1]
    prev_m = months[-2]
    return {
        "counts": counts,
        "mrr": mrr,
        "arr": mrr * 12,
        "this_month": received[this_m],
        "prev_month": received[prev_m],
        "year_total": sum(received.values()),
        "expected_30": sum(x["monthly"] for x in expected),
        "expected": expected,
        "blocked": blocked,
        "months": months,
        "received": [received[m] for m in months],
        "spread": [int(round(spread[m])) for m in months],
        "terms": terms,
        "lifetime_sales": lifetime_sales,
        "lifetime_sum": lifetime_sum,
        "branch_cash": branch_cash,
        "branch_cash_sum": branch_cash_sum,
        "pending": {"count": pending_n, "sum": pending_sum},
        "journal": journal,
        "price_main": settings["price_main"],
        "price_branch": settings["price_branch"],
    }


# ---------- Админка: карта точек с аналитикой ----------

def get_map_points(days: int = 30) -> dict:
    """Все точки и филиалы платформы для карты в админке: координаты,
    статус и короткая аналитика — за последние `days` дней (замены,
    выручка, средний чек, разные клиенты), изменение выручки к таким же
    предыдущим `days` дням, дата последней замены и замены сегодня.
    Один запрос на все точки — карта открывается быстро даже при сотнях точек."""
    days = max(1, min(int(days or 30), 365))
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    cur_from = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    prev_from = (now - timedelta(days=2 * days - 1)).strftime("%Y-%m-%d")
    prev_to = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        shops = conn.execute("""
            SELECT s.id, s.shop_name, s.username, s.role, s.parent_shop_id, s.client_group,
                   s.address, s.phone, s.hours, s.lat, s.lon, s.is_active,
                   p.shop_name AS parent_name, p.username AS parent_username,
                   (SELECT COUNT(*) FROM shops b WHERE b.parent_shop_id = s.id AND b.role='branch') AS branch_count,
                   (SELECT COUNT(*) FROM clients WHERE shop_id = s.id) AS client_count
            FROM shops s LEFT JOIN shops p ON p.id = s.parent_shop_id
            WHERE s.role IN ('shop', 'branch')
        """).fetchall()
        stats = conn.execute("""
            SELECT c.shop_id,
                   SUM(CASE WHEN oc.change_date >= :cf AND oc.change_date <= :t THEN 1 ELSE 0 END) AS cnt,
                   SUM(CASE WHEN oc.change_date >= :cf AND oc.change_date <= :t THEN COALESCE(oc.cost, 0) ELSE 0 END) AS total,
                   SUM(CASE WHEN oc.change_date >= :cf AND oc.change_date <= :t AND oc.cost > 0 THEN 1 ELSE 0 END) AS paid_cnt,
                   COUNT(DISTINCT CASE WHEN oc.change_date >= :cf AND oc.change_date <= :t THEN c.client_id END) AS clients,
                   SUM(CASE WHEN oc.change_date >= :pf AND oc.change_date <= :pt THEN COALESCE(oc.cost, 0) ELSE 0 END) AS prev_total,
                   SUM(CASE WHEN oc.change_date = :t THEN 1 ELSE 0 END) AS today_cnt,
                   MAX(CASE WHEN oc.change_date <= :t THEN oc.change_date END) AS last_date
            FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            GROUP BY c.shop_id
        """, {"cf": cur_from, "t": today, "pf": prev_from, "pt": prev_to}).fetchall()
    by_shop = {r["shop_id"]: dict(r) for r in stats}
    points = []
    for s in shops:
        d = dict(s)
        st = by_shop.get(d["id"], {})
        total = st.get("total") or 0
        paid = st.get("paid_cnt") or 0
        prev = st.get("prev_total") or 0
        last = st.get("last_date")
        days_idle = None
        if last:
            try:
                days_idle = (now.date() - datetime.strptime(last[:10], "%Y-%m-%d").date()).days
            except ValueError:
                days_idle = None
        if d["role"] == "branch":
            kind = "branch"
        elif d["branch_count"]:
            kind = "main"
        else:
            kind = "single"
        d.update({
            "kind": kind,
            "is_active": bool(d["is_active"]),
            "count": st.get("cnt") or 0,
            "total": total,
            "avg": round(total / paid) if paid else 0,
            "clients": st.get("clients") or 0,
            "pct": round((total - prev) / prev * 100, 1) if prev else None,
            "today": st.get("today_cnt") or 0,
            "last_date": last,
            "days_idle": days_idle,
        })
        points.append(d)
    return {"days": days, "date_from": cur_from, "date_to": today, "points": points}


@_serialized
def set_shop_location(shop_id: int, lat, lon) -> bool:
    """Ставит (или убирает, если None) координаты точки или филиала — из
    карты в админке. Пользователей-админов не трогает."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE shops SET lat=?, lon=? WHERE id=? AND role IN ('shop', 'branch')",
            (lat, lon, shop_id))
        conn.commit()
        return cur.rowcount > 0


# ---------- Админка: аналитика продаж, чистка названий, проверка цен ----------
#
# Данные точек НЕ меняются. Названия товаров, как их вписала точка,
# пропускаются через «автоочистку» (регистр, кириллица → латиница, похожие
# буквы, вязкость 5-30 → 5W30, лишние слова «масло», «4л»…) и через словарь
# соответствий name_aliases, который заполняет админ на экране
# «Сопоставление». Словарь можно исправить в любой момент — аналитика
# сразу пересчитается, в том числе за прошлое.

import re as _re
from difflib import SequenceMatcher as _SM


def _migrate_name_aliases(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS name_aliases (
        raw_key TEXT PRIMARY KEY,
        brand TEXT,
        product TEXT,
        status TEXT NOT NULL DEFAULT 'ok',
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.commit()


# Бренды MITAL — подсвечиваются в аналитике и считаются в «доле MITAL».
# Чтобы добавить бренд, впиши его ЗАГЛАВНЫМИ буквами так же, как в KNOWN_BRANDS.
MITAL_BRANDS = {"MITANOL", "LIMAN OIL", "MATTEX", "DELPIN", "ECO FILTER", "MITAL"}

# Известные бренды: правильное имя → другие написания (уже после перевода в
# латиницу). Похожие с опечатками («MITONOL», «LUKOYL») находятся сами.
KNOWN_BRANDS = {
    "MITANOL": ["MITANOL", "MITANOIL"],
    "LIMAN OIL": ["LIMAN OIL", "LIMAN"],
    "MATTEX": ["MATTEX", "MATEX"],
    "DELPIN": ["DELPIN", "DELFIN"],
    "ECO FILTER": ["ECO FILTER", "ECOFILTER", "EKO FILTER", "EKOFILTER", "EKO FILTR", "ECO FILTR"],
    "MITAL": ["MITAL"],
    "LUKOIL": ["LUKOIL", "LUKOYL"],
    "SHELL": ["SHELL", "SHEL"],
    "MOBIL": ["MOBIL", "MOBIL 1", "MOBIL1"],
    "CASTROL": ["CASTROL", "KASTROL"],
    "TOTAL": ["TOTAL", "TOTALENERGIES", "TOTAL ENERGIES"],
    "MOTUL": ["MOTUL"],
    "AVANTOL": ["AVANTOL"],
    "ZIC": ["ZIC", "ZIK"],
    "KIXX": ["KIXX", "KIKS", "KIX"],
    "ROSNEFT": ["ROSNEFT", "ROSNEFT'"],
    "G-ENERGY": ["G ENERGY", "GENERGY", "DJI ENERJI"],
    "GAZPROMNEFT": ["GAZPROMNEFT", "GAZPROM"],
    "LIQUI MOLY": ["LIQUI MOLY", "LIQUIMOLY", "LIKVI MOLI", "LIKVIMOLI"],
    "MANNOL": ["MANNOL", "MANOL"],
    "ENEOS": ["ENEOS"],
    "IDEMITSU": ["IDEMITSU", "IDEMITSY"],
    "PETRONAS": ["PETRONAS"],
    "VALVOLINE": ["VALVOLINE"],
    "ELF": ["ELF"],
    "SINTEC": ["SINTEC", "SINTEK"],
    "HI-GEAR": ["HI GEAR", "HIGEAR"],
    "S-OIL": ["S OIL", "SOIL", "S OIL SEVEN", "S SEVEN", "SOIL SEVEN"],
    "ADDINOL": ["ADDINOL"],
    "XADO": ["XADO", "HADO"],
    "FELIX": ["FELIX", "FELIKS"],
    "SIBIRSKIY": ["SIBIRSKIY", "SIBIRSKI"],
    "MANN": ["MANN", "MANN FILTER", "MAN FILTER"],
    "MAHLE": ["MAHLE"],
    "BOSCH": ["BOSCH", "BOSH"],
    "SAKURA": ["SAKURA"],
    "VIC": ["VIC"],
    "FILTRON": ["FILTRON"],
    "TOYOTA": ["TOYOTA"],
    "HYUNDAI": ["HYUNDAI", "HUNDAI", "XYUNDAY"],
    "GM": ["GM", "GENERAL MOTORS"],
    "CHEVROLET": ["CHEVROLET", "SHEVROLE"],
    "UZAUTO": ["UZAUTO"],
}

# Слова, которые не являются брендом/товаром — убираются из названия.
_NOISE = {"MASLO", "MOY", "MOYI", "MOTORNOE", "MOTORNOYE", "KANISTRA", "BUTYLKA", "LITR", "LITRA", "LITROV",
          "L", "LT", "LTR", "SHT", "SHTUK", "ORIGINAL", "ORIG", "NOVYY", "NOVIY", "ZAMENA", "FILTR", "FILTRI",
          "FILTER", "FILTERS", "MASLYANYY", "MASLYANIY", "VOZDUSHNYY", "SALONNYY", "TOPLIVNYY", "ANTIFRIZ",
          "TORMOZNAYA", "ZHIDKOST", "JIDKOST", "OIL"}
# Обозначения классов и типов — не бренды (для поиска бренда пропускаются).
_GRADES = {"API", "SAE", "ACEA", "ILSAC", "SL", "SM", "SN", "SP", "SJ", "CF", "CI", "CK", "CH", "SG", "GL",
           "ATF", "DEXRON", "DEX", "MULTI", "SYNT", "SINT", "SYNTHETIC", "SINTETIKA", "SINTETIK",
           "POLUSINTETIKA", "POLUSINTETIK", "SEMI", "MINERAL", "MINERALKA", "FULLY", "FULL", "ULTRA",
           "SUPER", "EXTRA", "PREMIUM", "PRO", "PLUS", "LONG", "LIFE", "G11", "G12", "G13", "DOT", "DOT4",
           "DOT3", "ECO", "KRASNIY", "KRASNYY", "KRASNYI", "ZELENYY", "ZELENIY", "ZELENYI", "SINIY", "SINIIY",
           "ROZOVYY", "QIZIL", "YASHIL", "KOK", "RED", "GREEN", "BLUE", "PINK", "YELLOW"}

_HOMOGLYPH = str.maketrans({"А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
                            "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y", "І": "I"})
_TRANSLIT = {"А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ж": "J", "З": "Z", "И": "I",
             "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S",
             "Т": "T", "У": "U", "Ф": "F", "Х": "H", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SH", "Ъ": "",
             "Ы": "I", "Ь": "", "Э": "E", "Ю": "YU", "Я": "YA", "Ў": "O", "Қ": "K", "Ғ": "G", "Ҳ": "H",
             "І": "I"}
_CYR = _re.compile(r"[А-ЯЁЎҚҒҲІ]")
_LAT = _re.compile(r"[A-Z]")

_ALIAS_MAP = {}
for _canon, _als in KNOWN_BRANDS.items():
    for _a in _als + [_canon]:
        _ALIAS_MAP[" ".join(_a.replace("-", " ").split())] = _canon


def _translit_token(tok: str) -> str:
    if not _CYR.search(tok):
        return tok
    if _LAT.search(tok) or any(ch.isdigit() for ch in tok):
        # слово набрано латиницей, но с «похожими» русскими буквами (MITANОL)
        tok = tok.translate(_HOMOGLYPH)
        if not _CYR.search(tok):
            return tok
    return "".join(_TRANSLIT.get(ch, ch) for ch in tok)


def _clean_tokens(label: str, keep_noise: bool = False) -> list:
    """«масло Митанол 5-30 SL 4л» → ['MITANOL', '5W30', 'SL'].
    keep_noise=True — оставить слова вроде FILTER/OIL: они нужны, чтобы
    узнать бренды «ECO FILTER», «LIMAN OIL»."""
    s = (label or "").upper().replace("Ё", "Е")
    s = _re.sub(r"(?<![A-ZА-Я0-9])(\d+(?:[.,]\d+)?)\s*(?:L|Л|LT|LTR|ЛИТР[А-Я]*|LITR[A-Z]*)(?![A-ZА-Я])", " ", s)
    s = _re.sub(r"\b(0|5|10|15|20|25)\s*[WВV]\s*[-/]?\s*(8|16|20|30|40|50|60)\b", r"\1W\2", s)
    s = _re.sub(r"\b(0|5|10|15|20|25)\s*[-/]\s*(20|30|40|50|60)\b", r"\1W\2", s)
    s = _re.sub(r"[^0-9A-ZА-ЯЁЎҚҒҲІ]+", " ", s)
    out = []
    for tok in s.split():
        tok = _translit_token(tok)
        tok = _re.sub(r"(?<=[A-Z])0(?=[A-Z])", "O", tok)  # MITAN0L → MITANOL
        if not tok or (tok in _NOISE and not keep_noise):
            continue
        out.append(tok)
    return out


def _known_brand_map():
    """Словарь написаний брендов: встроенный + бренды, подтверждённые админом."""
    m = dict(_ALIAS_MAP)
    with get_conn() as conn:
        for r in conn.execute("SELECT DISTINCT brand FROM name_aliases WHERE status='ok' AND brand IS NOT NULL AND brand != ''"):
            b = " ".join(r["brand"].upper().replace("-", " ").split())
            m.setdefault(b, r["brand"].upper())
    return m


def _is_candidate(tok: str) -> bool:
    return len(tok) >= 2 and tok.isalpha() and tok not in _GRADES and tok not in _NOISE


def _detect_brand(tokens: list, bmap: dict):
    """Ищет бренд в словах названия. Возвращает (бренд, сколько слов он занял,
    позиция, уверенность 0..1, статус): exact — точно; auto — опечатка,
    исправлено автоматически; suggest — похоже, нужна проверка; unknown."""
    if not tokens:
        return "", 0, 0, 1.0, "nobrand"
    for i in range(len(tokens)):
        for n in (3, 2, 1):
            if i + n <= len(tokens):
                cand = " ".join(tokens[i:i + n])
                if cand in bmap:
                    return bmap[cand], n, i, 1.0, "exact"
                glued = "".join(tokens[i:i + n])
                if n > 1 and glued in bmap:
                    return bmap[glued], n, i, 1.0, "exact"
    best = (0.0, "", 0, 0)
    keys = [k for k in bmap if len(k.replace(" ", "")) >= 4]
    for i in range(len(tokens)):
        for n in (2, 1):
            if i + n > len(tokens) or not all(_is_candidate(t) for t in tokens[i:i + n]):
                continue
            cand = " ".join(tokens[i:i + n])
            if len(cand.replace(" ", "")) < 4:
                continue
            for k in keys:
                r = _SM(None, cand, k).ratio()
                if r > best[0]:
                    best = (r, bmap[k], n, i)
    if best[0] >= 0.85 and best[1][:1] == tokens[best[3]][:1]:
        return best[1], best[2], best[3], round(best[0], 2), "auto"
    first = next((i for i, t in enumerate(tokens) if _is_candidate(t)), None)
    if best[0] >= 0.72:
        return best[1], best[2], best[3], round(best[0], 2), "suggest"
    if first is None:
        return "", 0, 0, 1.0, "nobrand"
    return tokens[first], 1, first, 0.0, "unknown"


def _resolve_name(label: str, bmap: dict, aliases: dict, cache: dict) -> dict:
    """Что на самом деле продано: бренд, товар (для показа) и ключ товара
    (одинаковый для «MITANOL SL 5W30» и «Митанол 5-30 SL»)."""
    if label in cache:
        return cache[label]
    full = _clean_tokens(label, keep_noise=True)
    tokens = [t for t in full if t not in _NOISE]
    raw_key = " ".join(tokens)
    al = aliases.get(raw_key)
    if al:
        if al["status"] == "nobrand":
            res = {"raw": raw_key, "brand": "", "product": al.get("product") or raw_key,
                   "status": "mapped", "sug": None, "conf": 1.0}
        else:
            brand = (al.get("brand") or "").upper()
            product = al.get("product") or " ".join([brand] + [t for t in tokens if t not in brand.split()])
            res = {"raw": raw_key, "brand": brand, "product": product.strip(), "status": "mapped",
                   "sug": None, "conf": 1.0}
    else:
        brand, n, pos, conf, status = _detect_brand(full, bmap)
        rest = [t for t in (full[:pos] + full[pos + n:] if n else full) if t not in _NOISE]
        if status in ("exact", "auto"):
            product = " ".join([brand] + rest)
            res = {"raw": raw_key, "brand": brand, "product": product, "status": status, "sug": None, "conf": conf}
        elif status == "suggest":
            res = {"raw": raw_key, "brand": full[pos] if full else "", "product": raw_key, "status": status,
                   "sug": {"brand": brand, "product": " ".join([brand] + rest)}, "conf": conf}
        else:
            res = {"raw": raw_key, "brand": brand, "product": raw_key, "status": status, "sug": None, "conf": conf}
    ptoks = _clean_tokens(res["product"])
    btoks = res["brand"].replace("-", " ").split()
    res["pkey"] = " ".join(btoks + sorted(t for t in ptoks if t not in btoks)) or raw_key
    cache[label] = res
    return res


def _load_aliases() -> dict:
    with get_conn() as conn:
        return {r["raw_key"]: dict(r) for r in conn.execute("SELECT * FROM name_aliases").fetchall()}


def _scan_lines(date_from: str, date_to: str) -> list:
    """Все проданные товары за период по всем точкам — по одной строке на
    позицию, с распознанным брендом/товаром. Работа и услуги («Прочее» без
    товара со склада) пропускаются."""
    import i18n
    name_to_key = {}
    for lang_texts in i18n.TEXTS.values():
        for k in BRAND_CATEGORY_ORDER:
            if k in lang_texts:
                name_to_key[lang_texts[k]] = k
    other_prefixes = tuple(f"{t.get('other_prefix', '')}:" for t in i18n.TEXTS.values())
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.id, oc.change_date, c.shop_id, oc.items_json FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE oc.change_date >= ? AND oc.change_date <= ? AND oc.items_json IS NOT NULL
        """, (date_from, date_to)).fetchall()
    bmap = _known_brand_map()
    aliases = _load_aliases()
    cache = {}
    lines = []
    for r in rows:
        try:
            items = json.loads(r["items_json"]) or []
        except (TypeError, ValueError):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cat = _item_category_key(item, name_to_key)
            pid = item.get("product_id")
            if cat == "other":
                if not pid:
                    continue
                label = (item.get("name") or "").strip()
                for pref in other_prefixes:
                    if label.startswith(pref):
                        label = label[len(pref):].strip()
                        break
            else:
                label = (item.get("brand") or "").strip()
            label = " ".join(label.split())
            try:
                qty = float(item.get("qty") or 0)
                total = float(item.get("total") or 0)
            except (TypeError, ValueError):
                continue
            if qty <= 0 and total <= 0:
                continue
            cp = item.get("cost_price")
            try:
                cp = float(cp) if cp is not None else None
            except (TypeError, ValueError):
                cp = None
            res = _resolve_name(label, bmap, aliases, cache)
            lines.append({"id": r["id"], "date": r["change_date"], "s": r["shop_id"], "c": cat, "label": label,
                          "qty": qty, "total": total, "cp": cp if cp and cp > 0 else None,
                          "stock": bool(pid), "res": res})
    return lines


def _median(vals):
    vals = sorted(vals)
    n = len(vals)
    if not n:
        return None
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


PRICE_HIGH = 2.0   # цена дороже обычной по сети в 2+ раза — подозрительно
PRICE_LOW = 0.5    # дешевле обычной в 2+ раза — подозрительно


def _price_check(lines: list):
    """Помечает строки с подозрительной ценой продажи или закупки: сильно
    отличается от обычной (медианной) цены этого же товара по сети, или
    закупка дороже продажи в 1,5 раза (цена за коробку вместо штуки)."""
    sale_by, cost_by = {}, {}
    for ln in lines:
        k = (ln["c"], ln["res"]["pkey"])
        if ln["qty"] > 0 and ln["total"] > 0:
            sale_by.setdefault(k, []).append(ln["total"] / ln["qty"])
        if ln["cp"]:
            cost_by.setdefault(k, []).append(ln["cp"])
    med_s = {k: _median(v) for k, v in sale_by.items() if len(v) >= 3}
    med_c = {k: _median(v) for k, v in cost_by.items() if len(v) >= 3}
    for ln in lines:
        k = (ln["c"], ln["res"]["pkey"])
        ln["sale_bad"] = False
        ln["cost_bad"] = False
        ln["med_sale"] = med_s.get(k)
        ln["med_cost"] = med_c.get(k)
        up = ln["total"] / ln["qty"] if ln["qty"] > 0 and ln["total"] > 0 else None
        ln["unit"] = up
        if up is None:
            ln["sale_bad"] = True
        elif ln["med_sale"] and (up > ln["med_sale"] * PRICE_HIGH or up < ln["med_sale"] * PRICE_LOW):
            ln["sale_bad"] = True
        if ln["cp"]:
            if up and (ln["cp"] > up * 1.5 or up > ln["cp"] * 6):
                ln["cost_bad"] = True
            elif ln["med_cost"] and (ln["cp"] > ln["med_cost"] * PRICE_HIGH or ln["cp"] < ln["med_cost"] * PRICE_LOW):
                ln["cost_bad"] = True


def _period_from(days: int):
    now = datetime.now()
    return (now - timedelta(days=days - 1)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def get_admin_analytics(days: int = 30) -> dict:
    """Что продают точки: по точке, категории и товару — количество, сумма,
    цена и закупка за единицу (без подозрительных цен), сколько продаж ещё
    не распознано (нужно «Сопоставление») и качество данных точки."""
    days = max(1, min(int(days or 30), 730))
    date_from, today = _period_from(days)
    with get_conn() as conn:
        shops = conn.execute("""
            SELECT s.id, s.shop_name, s.username, s.role, s.parent_shop_id, s.client_group, s.is_active,
                   p.shop_name AS parent_name,
                   (SELECT COUNT(*) FROM shops b WHERE b.parent_shop_id = s.id AND b.role='branch') AS branch_count
            FROM shops s LEFT JOIN shops p ON p.id = s.parent_shop_id
            WHERE s.role IN ('shop', 'branch')
            ORDER BY s.shop_name
        """).fetchall()
    lines = _scan_lines(date_from, today)
    _price_check(lines)
    agg, quality = {}, {}
    for ln in lines:
        res = ln["res"]
        q = quality.setdefault(ln["s"], {"lines": 0, "stock": 0, "cost": 0})
        q["lines"] += 1
        if ln["stock"]:
            q["stock"] += 1
        if ln["cp"]:
            q["cost"] += 1
        a = agg.setdefault((ln["s"], ln["c"], res["pkey"]), {
            "q": 0.0, "t": 0.0, "pq": 0.0, "pt": 0.0, "cq": 0.0, "cs": 0.0, "ct": 0.0,
            "n": 0, "bad": 0, "ut": 0.0, "sp": {}, "brand": res["brand"]})
        a["q"] += ln["qty"]
        a["t"] += ln["total"]
        a["n"] += 1
        a["sp"][res["product"]] = a["sp"].get(res["product"], 0) + 1
        if res["status"] in ("suggest", "unknown"):
            a["ut"] += ln["total"]
        if ln["sale_bad"]:
            a["bad"] += 1
        else:
            a["pq"] += ln["qty"]
            a["pt"] += ln["total"]
            if ln["cp"] and not ln["cost_bad"]:
                a["cq"] += ln["qty"]
                a["cs"] += ln["qty"] * ln["cp"]
                a["ct"] += ln["total"]
        if ln["cp"] and ln["cost_bad"] and not ln["sale_bad"]:
            a["bad"] += 1
    out_rows = []
    for (sid, cat, pkey), a in agg.items():
        display = max(a["sp"].items(), key=lambda kv: kv[1])[0] if a["sp"] else ""
        brand = a["brand"]
        out_rows.append({
            "s": sid, "c": cat, "k": pkey, "p": display, "b": brand,
            "m": 1 if brand in MITAL_BRANDS else 0,
            "q": round(a["q"], 2), "t": round(a["t"]), "pq": round(a["pq"], 2), "pt": round(a["pt"]),
            "cq": round(a["cq"], 2), "cs": round(a["cs"]), "ct": round(a["ct"]),
            "n": a["n"], "bad": a["bad"], "ut": round(a["ut"]),
        })
    points = []
    for s in shops:
        d = dict(s)
        d["kind"] = "branch" if d["role"] == "branch" else ("main" if d["branch_count"] else "single")
        d["is_active"] = bool(d["is_active"])
        d["quality"] = quality.get(d["id"], {"lines": 0, "stock": 0, "cost": 0})
        points.append(d)
    import i18n
    ru = i18n.TEXTS.get("ru", {})
    cats = [{"key": k, "label": ru.get(k, k), "unit": "л" if k in _FLUID_KEYS else "шт"} for k in BRAND_CATEGORY_ORDER]
    return {"days": days, "date_from": date_from, "date_to": today,
            "points": points, "categories": cats, "rows": out_rows,
            "mital_brands": sorted(MITAL_BRANDS)}


def get_name_review(days: int = 365) -> dict:
    """Экран «Сопоставление»: названия, которые не распознаны уверенно (с
    подсказкой, если она есть), исправленные автоматически (для проверки) и
    уже подтверждённые админом. Сортировка — по сумме продаж: сначала то,
    что сильнее всего влияет на цифры."""
    date_from, today = _period_from(days)
    lines = _scan_lines(date_from, today)
    groups = {}
    for ln in lines:
        res = ln["res"]
        if res["status"] in ("exact", "nobrand") or not res["raw"]:
            continue
        g = groups.setdefault(res["raw"], {
            "raw": res["raw"], "status": res["status"], "brand": res["brand"], "product": res["product"],
            "sug": res["sug"], "conf": res["conf"], "sum": 0, "lines": 0, "shops": set(), "cats": set(),
            "spellings": {}, "first": ln["date"], "last": ln["date"]})
        g["sum"] += ln["total"]
        g["lines"] += 1
        g["shops"].add(ln["s"])
        g["cats"].add(ln["c"])
        if ln["label"]:
            g["spellings"][ln["label"]] = g["spellings"].get(ln["label"], 0) + 1
        g["first"] = min(g["first"], ln["date"])
        g["last"] = max(g["last"], ln["date"])
    total_sum = sum(ln["total"] for ln in lines) or 0
    out = {"review": [], "auto": [], "mapped": []}
    for g in groups.values():
        g["shops"] = len(g["shops"])
        g["cats"] = sorted(g["cats"])
        g["spellings"] = [k for k, _ in sorted(g["spellings"].items(), key=lambda kv: -kv[1])[:4]]
        g["sum"] = round(g["sum"])
        bucket = "review" if g["status"] in ("suggest", "unknown") else ("auto" if g["status"] == "auto" else "mapped")
        out[bucket].append(g)
    for k in out:
        out[k].sort(key=lambda g: -g["sum"])
    aliases = _load_aliases()
    for g in out["mapped"]:
        a = aliases.get(g["raw"]) or {}
        g["alias_status"] = a.get("status")
    # подтверждённые, которых за период не было в продажах — тоже показываем, чтобы можно было отменить
    seen = {g["raw"] for g in out["mapped"]}
    for raw, a in aliases.items():
        if raw not in seen:
            out["mapped"].append({"raw": raw, "brand": a.get("brand") or "", "product": a.get("product") or "",
                                  "status": "mapped", "alias_status": a.get("status"), "sum": 0, "lines": 0,
                                  "shops": 0, "cats": [], "spellings": [], "first": None, "last": None})
    unresolved = sum(g["sum"] for g in out["review"])
    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    brands = sorted(set(KNOWN_BRANDS) | {(a.get("brand") or "").upper() for a in aliases.values() if a.get("brand")})
    return {"days": days, "total_sum": round(total_sum), "unresolved_sum": round(unresolved),
            "unresolved_pct": round(unresolved / total_sum * 100, 1) if total_sum else 0,
            "new_this_week": sum(1 for g in out["review"] if g["first"] and g["first"] >= week_ago),
            "brands": [b for b in brands if b], "mital_brands": sorted(MITAL_BRANDS), **out}


def get_price_problems(days: int = 90, limit: int = 150) -> list:
    """Подозрительные цены: продажа или закупка сильно отличается от обычной
    цены этого товара по сети, или закупка выше продажи (цена за коробку)."""
    date_from, today = _period_from(days)
    lines = _scan_lines(date_from, today)
    _price_check(lines)
    out = []
    for ln in lines:
        if not (ln["sale_bad"] or ln["cost_bad"]):
            continue
        if ln["sale_bad"]:
            kind = "sale"
            val, med = ln["unit"], ln["med_sale"]
        else:
            kind = "cost"
            val, med = ln["cp"], ln["med_cost"] or ln["unit"]
        dev = (val / med) if val and med else 0
        out.append({"id": ln["id"], "date": ln["date"], "s": ln["s"], "c": ln["c"],
                    "label": ln["label"], "product": ln["res"]["product"], "qty": ln["qty"],
                    "total": round(ln["total"]), "unit": round(ln["unit"]) if ln["unit"] else None,
                    "cost": round(ln["cp"]) if ln["cp"] else None,
                    "med_sale": round(ln["med_sale"]) if ln["med_sale"] else None,
                    "med_cost": round(ln["med_cost"]) if ln["med_cost"] else None,
                    "kind": kind, "dev": round(dev, 2) if dev else None})
    out.sort(key=lambda x: -abs(math.log(x["dev"])) if x["dev"] else 0)
    return out[:limit]


@_serialized
def save_name_aliases(items: list) -> int:
    """Подтверждение админом: «это название = такой-то бренд/товар»
    (status='ok') или «это не бренд» (status='nobrand'). Данные точек не меняются."""
    n = 0
    with get_conn() as conn:
        for it in items:
            raw = " ".join(str(it.get("raw") or "").split())
            if not raw:
                continue
            status = "nobrand" if it.get("status") == "nobrand" else "ok"
            brand = " ".join(str(it.get("brand") or "").upper().split())[:60] or None
            product = " ".join(str(it.get("product") or "").split())[:120] or None
            if status == "ok" and not brand:
                continue
            conn.execute("""
                INSERT INTO name_aliases(raw_key, brand, product, status, updated_at) VALUES(?, ?, ?, ?, datetime('now'))
                ON CONFLICT(raw_key) DO UPDATE SET brand=excluded.brand, product=excluded.product,
                    status=excluded.status, updated_at=excluded.updated_at
            """, (raw, brand if status == "ok" else None, product, status))
            n += 1
        conn.commit()
    return n


@_serialized
def delete_name_alias(raw_key: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM name_aliases WHERE raw_key=?", (raw_key,))
        conn.commit()
        return cur.rowcount > 0


def get_name_review_summary() -> dict:
    """Для еженедельного сообщения админу в Telegram."""
    r = get_name_review(365)
    try:
        prob = len(get_price_problems(30, 1000))
    except Exception:
        prob = 0
    return {"count": len(r["review"]), "new": r["new_this_week"], "sum": r["unresolved_sum"],
            "pct": r["unresolved_pct"], "price_problems": prob}


def get_admin_shop_snapshot(shop_id: int, days: int = 30):
    """Копия того, что видит сама точка: статистика брендов (масла, фильтры…)
    за период и её склад с ценами закупки и продажи. Для окна на карте в админке."""
    import i18n
    shop = get_shop(shop_id)
    if not shop or shop.get("role") not in ("shop", "branch"):
        return None
    days = max(1, min(int(days or 30), 730))
    date_from, today = _period_from(days)
    ru = i18n.TEXTS.get("ru", {})
    brands = get_brand_breakdown(shop_id, date_from, today, limit=10)
    for c in brands["categories"]:
        c["label"] = ru.get(c["key"], c["key"])
    wh = get_warehouse_overview(shop_id)
    products = []
    for p in wh["products"]:
        products.append({
            "id": p["id"], "name": p["name"], "category": p["category"],
            "category_label": ru.get(p["category"], "Прочее") if p["category"] != "other" else "Прочее",
            "unit": p["unit"], "stock": p["stock_qty"], "buy": p.get("purchase_price"),
            "sell": p.get("sell_price"), "margin_pct": p.get("margin_pct"), "sold_30d": p.get("sold_30d"),
            "status": p.get("status"), "last_sale": p.get("last_sale"),
        })
    parent = get_shop(shop["parent_shop_id"]) if shop.get("parent_shop_id") else None
    return {
        "shop": {"id": shop["id"], "name": shop.get("shop_name") or shop["username"], "username": shop["username"],
                 "role": shop["role"], "parent_name": (parent or {}).get("shop_name"),
                 "warehouse_enabled": bool(shop.get("warehouse_enabled")), "address": shop.get("address")},
        "days": days, "date_from": date_from, "date_to": today,
        "revenue": get_revenue_range(shop_id, date_from, today),
        "brands": brands["categories"],
        "warehouse": {"products": products, "summary": wh["summary"]},
        "suppliers": _admin_suppliers_snapshot(shop_id, date_from, today),
    }


def _admin_suppliers_snapshot(shop_id: int, date_from: str, date_to: str) -> dict:
    """Поставщики точки для окна на карте: контакты, долг и просрочка, сколько
    взяли товара за период и всего, последние цены закупки по товарам."""
    sups = list_suppliers(shop_id)
    out = []
    with get_conn() as conn:
        for s in sups:
            entries = _live(_supplier_charges(conn, shop_id, s["id"]))
            in_period = [e for e in entries if date_from <= (e.get("date") or "") <= date_to]
            per = _period_totals(in_period)
            allt = _period_totals(entries)
            last_order = max((e["date"] for e in entries if e["type"] == "order" and e.get("date")), default=None)
            last_pay = max((e["date"] for e in entries if e["type"] == "payment" and e.get("date")), default=None)
            prods = [r["name"] for r in conn.execute(
                "SELECT name FROM products WHERE shop_id=? AND supplier_id=? AND is_active=1 ORDER BY name COLLATE NOCASE",
                (shop_id, s["id"])).fetchall()]
            prices = []
            for p in supplier_price_history(shop_id, s["id"])[:40]:
                prices.append({"name": p["name"], "unit": p["unit"], "last": p["last"], "last_date": p["last_date"],
                               "change_pct": p["change_pct"], "since_first_pct": p["since_first_pct"],
                               "times": len(p["history"])})
            out.append({
                "id": s["id"], "name": s["name"], "phone": s.get("phone"), "telegram": s.get("telegram"),
                "contact": s.get("contact"), "delivery_days": s.get("delivery_days"), "pay_days": s.get("pay_days"),
                "note": s.get("note"), "balance": s["balance"], "overdue": s["overdue"],
                "next_due": s.get("next_due"), "oldest_overdue": s.get("oldest_overdue"),
                "bought_period": per["bought"], "paid_period": per["paid"],
                "bought_all": allt["bought"], "paid_all": allt["paid"],
                "last_order": last_order, "last_payment": last_pay,
                "order_count": sum(1 for e in entries if e["type"] == "order"),
                "products": prods, "prices": prices,
            })
        no_sup = conn.execute(
            "SELECT COUNT(*) FROM products WHERE shop_id=? AND is_active=1 AND supplier_id IS NULL", (shop_id,)).fetchone()[0]
    out.sort(key=lambda x: (-x["bought_period"], -x["bought_all"], x["name"].lower()))
    return {"list": out, "no_supplier_products": no_sup,
            "owe": sum(x["balance"] for x in out if x["balance"] > 0),
            "overdue": sum(x["overdue"] for x in out),
            "bought_period": sum(x["bought_period"] for x in out)}
