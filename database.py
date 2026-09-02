"""
База данных для системы учёта замены масла.
Хранит: клиентов (владельцев авто, привязанных к Telegram по персональному
токену), автомобили, подробную историю замен/обслуживания по каждому авто.
"""

import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from contextlib import contextmanager
from dateutil.relativedelta import relativedelta

# Если задана переменная окружения DB_PATH (например, путь на подключённый
# Railway Volume, /data/oil_bot.db) — база хранится там и переживает
# передеплои. Без неё — в рабочей папке контейнера (может стираться при
# пересоздании контейнера, см. README).
DB_PATH = os.environ.get("DB_PATH", "oil_bot.db")

MAX_FOLLOWUP_REMINDERS = 6      # сколько повторных напоминаний слать всего
FOLLOWUP_INTERVAL_DAYS = 14     # раз в сколько дней слать повторное напоминание


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        # Клиенты (владельцы авто). link_token — персональный код для ссылки/QR,
        # по которому клиент привязывается к боту без ввода телефона вручную.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            phone TEXT,
            full_name TEXT,
            link_token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # Автомобили, привязка к клиенту по client_id (у одного клиента может
        # быть несколько машин под одной привязкой к боту)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL,
            car_brand TEXT,
            car_model TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
        """)

        # Подробная история замен/обслуживания — каждая запись отдельной
        # строкой, ничего не перезаписывается.
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
            interval_months INTEGER,
            next_change_date TEXT,
            notes TEXT,
            reminder_count INTEGER DEFAULT 0,
            last_reminder_date TEXT,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (car_id) REFERENCES cars(id)
        )
        """)

        # Рассылки (акции/объявления всем привязанным клиентам)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            total_sent INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT
        )
        """)

        conn.commit()
        _migrate(conn)


def _migrate(conn):
    """Добавляет новые колонки в уже существующую базу (если апгрейд со старой версии)."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(oil_changes)").fetchall()}
    to_add = {
        "service_type": "TEXT DEFAULT 'Замена масла'",
        "filter_changed": "INTEGER DEFAULT 0",
        "cost": "INTEGER",
        "reminder_count": "INTEGER DEFAULT 0",
        "last_reminder_date": "TEXT",
    }
    for col, ddl in to_add.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE oil_changes ADD COLUMN {col} {ddl}")
    # Переносим старое поле reminder_sent (0/1), если оно есть, в reminder_count
    if "reminder_sent" in cols and "reminder_count" in to_add:
        conn.execute("UPDATE oil_changes SET reminder_count=reminder_sent WHERE reminder_count=0")
    conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def normalize_plate(plate: str) -> str:
    return plate.strip().upper().replace(" ", "")


def generate_token() -> str:
    return secrets.token_urlsafe(6)


# ---------- Клиенты ----------

def get_or_create_client(owner_name: str, phone: str = None):
    """Находит клиента по телефону (если указан) или создаёт нового с новым
    персональным токеном для ссылки/QR."""
    phone = (phone or "").strip() or None
    with get_conn() as conn:
        if phone:
            existing = conn.execute("SELECT * FROM clients WHERE phone=?", (phone,)).fetchone()
            if existing:
                if owner_name:
                    conn.execute("UPDATE clients SET full_name=? WHERE id=?", (owner_name, existing["id"]))
                    conn.commit()
                return dict(existing)

        token = generate_token()
        cur = conn.execute(
            "INSERT INTO clients (phone, full_name, link_token) VALUES (?, ?, ?)",
            (phone, owner_name, token)
        )
        conn.commit()
        return {"id": cur.lastrowid, "telegram_id": None, "phone": phone, "full_name": owner_name, "link_token": token}


def get_client_by_token(token: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clients WHERE link_token=?", (token,)).fetchone()
        return dict(row) if row else None


def link_client_by_token(telegram_id: int, token: str, tg_full_name: str = None):
    """Привязывает Telegram-аккаунт клиента к его записи по персональному токену
    из ссылки/QR. Возвращает запись клиента или None, если токен неверный."""
    with get_conn() as conn:
        client = conn.execute("SELECT * FROM clients WHERE link_token=?", (token,)).fetchone()
        if not client:
            return None
        full_name = client["full_name"] or tg_full_name
        conn.execute(
            "UPDATE clients SET telegram_id=?, full_name=? WHERE id=?",
            (telegram_id, full_name, client["id"])
        )
        conn.commit()
        return get_client_by_token(token)


def get_client_by_telegram_id(telegram_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clients WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row) if row else None


def get_client_cars(client_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cars WHERE client_id=?", (client_id,)).fetchall()
        return [dict(r) for r in rows]


def get_client_full_history(telegram_id: int):
    """Вся история по всем машинам клиента (для просмотра в боте самим клиентом)."""
    with get_conn() as conn:
        cars = conn.execute("""
            SELECT c.* FROM cars c JOIN clients cl ON cl.id=c.client_id
            WHERE cl.telegram_id=?
        """, (telegram_id,)).fetchall()
        result = []
        for car in cars:
            history = conn.execute(
                "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date DESC",
                (car["id"],)
            ).fetchall()
            result.append({"car": dict(car), "history": [dict(h) for h in history]})
        return result


# ---------- Машины ----------

def find_car(plate_number: str):
    plate_number = normalize_plate(plate_number)
    with get_conn() as conn:
        car = conn.execute("SELECT * FROM cars WHERE plate_number=?", (plate_number,)).fetchone()
        return dict(car) if car else None


def create_or_update_car(plate_number: str, client_id: int, car_brand: str = None, car_model: str = None):
    plate_number = normalize_plate(plate_number)
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM cars WHERE plate_number=?", (plate_number,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE cars SET car_brand=COALESCE(?, car_brand), car_model=COALESCE(?, car_model) WHERE plate_number=?",
                (car_brand, car_model, plate_number)
            )
            conn.commit()
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO cars (plate_number, client_id, car_brand, car_model) VALUES (?, ?, ?, ?)",
                (plate_number, client_id, car_brand, car_model)
            )
            conn.commit()
            return cur.lastrowid


def get_car_history(plate_number: str):
    plate_number = normalize_plate(plate_number)
    with get_conn() as conn:
        row = conn.execute("""
            SELECT c.*, cl.full_name as owner_name, cl.phone as owner_phone,
                   cl.link_token, cl.telegram_id
            FROM cars c JOIN clients cl ON cl.id = c.client_id
            WHERE c.plate_number=?
        """, (plate_number,)).fetchone()
        if not row:
            return None, []
        history = conn.execute(
            "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date DESC",
            (row["id"],)
        ).fetchall()
        return dict(row), [dict(h) for h in history]


def get_last_service(car_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM oil_changes WHERE car_id=? ORDER BY change_date DESC LIMIT 1",
            (car_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_cars_overview():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                c.id as car_id, c.plate_number, c.car_brand, c.car_model,
                cl.full_name as owner_name, cl.phone as owner_phone,
                cl.link_token, cl.telegram_id, cl.id as client_id,
                (SELECT change_date FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as change_date,
                (SELECT mileage FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as mileage,
                (SELECT service_type FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as service_type,
                (SELECT oil_brand FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as oil_brand,
                (SELECT next_change_date FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as next_change_date
            FROM cars c JOIN clients cl ON cl.id = c.client_id
            ORDER BY c.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


# ---------- Замены масла / обслуживание ----------

def add_oil_change(car_id: int, mileage, service_type: str, oil_brand: str, filter_changed: bool,
                    cost, interval_months: int, notes: str = ""):
    change_date = datetime.now().strftime("%Y-%m-%d")
    next_date = (datetime.now() + relativedelta(months=interval_months)).strftime("%Y-%m-%d")

    with get_conn() as conn:
        # закрываем предыдущие "active" записи этой машины
        conn.execute("UPDATE oil_changes SET status='done' WHERE car_id=? AND status='active'", (car_id,))
        cur = conn.execute("""
            INSERT INTO oil_changes
                (car_id, change_date, mileage, service_type, oil_brand, filter_changed, cost,
                 interval_months, next_change_date, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (car_id, change_date, mileage, service_type, oil_brand, int(bool(filter_changed)), cost,
              interval_months, next_date, notes))
        conn.commit()
        return cur.lastrowid, next_date


def get_due_reminders():
    """Машины, которым пора напомнить: первое напоминание (дата подошла) или
    повторное (раз в FOLLOWUP_INTERVAL_DAYS дней, максимум MAX_FOLLOWUP_REMINDERS раз),
    только если клиент уже привязан к боту."""
    today = datetime.now().strftime("%Y-%m-%d")
    followup_cutoff = (datetime.now() - timedelta(days=FOLLOWUP_INTERVAL_DAYS)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.*, c.plate_number, cl.full_name as owner_name, cl.telegram_id
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN clients cl ON cl.id = c.client_id
            WHERE oc.status='active' AND cl.telegram_id IS NOT NULL AND (
                (oc.reminder_count = 0 AND oc.next_change_date <= ?)
                OR
                (oc.reminder_count > 0 AND oc.reminder_count < ? AND oc.last_reminder_date <= ?)
            )
        """, (today, MAX_FOLLOWUP_REMINDERS, followup_cutoff)).fetchall()
        return [dict(r) for r in rows]


def mark_reminder_sent(oil_change_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "UPDATE oil_changes SET reminder_count = reminder_count + 1, last_reminder_date=? WHERE id=?",
            (today, oil_change_id)
        )
        conn.commit()


def mark_booked(oil_change_id: int):
    """Клиент нажал «Записаться» — останавливаем повторные напоминания по этой записи."""
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='booked' WHERE id=?", (oil_change_id,))
        conn.commit()


def mark_already_changed_elsewhere(oil_change_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='changed_elsewhere' WHERE id=?", (oil_change_id,))
        conn.commit()


def get_oil_change_with_context(oil_change_id: int):
    """Запись замены + госномер + owner — используется, чтобы уведомить админа о брони."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT oc.*, c.plate_number, cl.full_name as owner_name, cl.phone as owner_phone
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN clients cl ON cl.id = c.client_id
            WHERE oc.id=?
        """, (oil_change_id,)).fetchone()
        return dict(row) if row else None


# ---------- Рассылки ----------

def get_all_linked_clients():
    """Клиенты, привязавшие Telegram (для рассылки объявлений/акций)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, telegram_id, full_name FROM clients WHERE telegram_id IS NOT NULL").fetchall()
        return [dict(r) for r in rows]


def create_broadcast(message: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO broadcasts (message, status) VALUES (?, 'pending')", (message,))
        conn.commit()
        return cur.lastrowid


def get_pending_broadcast():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM broadcasts WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None


def mark_broadcast_sending(broadcast_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE broadcasts SET status='sending' WHERE id=?", (broadcast_id,))
        conn.commit()


def mark_broadcast_done(broadcast_id: int, sent: int, failed: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE broadcasts SET status='done', total_sent=?, total_failed=?, finished_at=datetime('now') WHERE id=?",
            (sent, failed, broadcast_id)
        )
        conn.commit()


def get_recent_broadcasts(limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
