"""
База данных для системы учёта замены масла.
Хранит: клиентов (владельцев авто, привязанных к Telegram по персональному
токену), автомобили, полную историю замен по каждому авто.
"""

import sqlite3
import secrets
from datetime import datetime
from contextlib import contextmanager
from dateutil.relativedelta import relativedelta

DB_PATH = "oil_bot.db"


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

        # История замен масла — каждая запись отдельной строкой, ничего не
        # перезаписывается. Напоминание считается по месяцам от даты замены.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS oil_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            change_date TEXT NOT NULL,
            mileage INTEGER,
            oil_brand TEXT,
            interval_months INTEGER,
            next_change_date TEXT,
            notes TEXT,
            reminder_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (car_id) REFERENCES cars(id)
        )
        """)

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


def get_client_cars(client_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cars WHERE client_id=?", (client_id,)).fetchall()
        return [dict(r) for r in rows]


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


def get_last_oil_brand(car_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT oil_brand FROM oil_changes WHERE car_id=? ORDER BY change_date DESC LIMIT 1",
            (car_id,)
        ).fetchone()
        return row["oil_brand"] if row else None


def get_all_cars_overview():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                c.id as car_id, c.plate_number, c.car_brand, c.car_model,
                cl.full_name as owner_name, cl.phone as owner_phone,
                cl.link_token, cl.telegram_id, cl.id as client_id,
                (SELECT change_date FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as change_date,
                (SELECT mileage FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as mileage,
                (SELECT oil_brand FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as oil_brand,
                (SELECT next_change_date FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC LIMIT 1) as next_change_date
            FROM cars c JOIN clients cl ON cl.id = c.client_id
            ORDER BY c.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


# ---------- Замены масла ----------

def add_oil_change(car_id: int, mileage, oil_brand: str, interval_months: int, notes: str = ""):
    change_date = datetime.now().strftime("%Y-%m-%d")
    next_date = (datetime.now() + relativedelta(months=interval_months)).strftime("%Y-%m-%d")

    with get_conn() as conn:
        # закрываем предыдущие "active" записи этой машины
        conn.execute("UPDATE oil_changes SET status='done' WHERE car_id=? AND status='active'", (car_id,))
        cur = conn.execute("""
            INSERT INTO oil_changes (car_id, change_date, mileage, oil_brand, interval_months, next_change_date, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """, (car_id, change_date, mileage, oil_brand, interval_months, next_date, notes))
        conn.commit()
        return cur.lastrowid, next_date


def get_due_reminders():
    """Машины, которым пора напомнить (дата подошла, напоминание ещё не отправлено)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT oc.*, c.plate_number, cl.full_name as owner_name, cl.telegram_id
            FROM oil_changes oc
            JOIN cars c ON c.id = oc.car_id
            JOIN clients cl ON cl.id = c.client_id
            WHERE oc.status='active' AND oc.reminder_sent=0 AND oc.next_change_date <= ?
        """, (today,)).fetchall()
        return [dict(r) for r in rows]


def mark_reminder_sent(oil_change_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET reminder_sent=1 WHERE id=?", (oil_change_id,))
        conn.commit()


def mark_already_changed_elsewhere(oil_change_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='changed_elsewhere' WHERE id=?", (oil_change_id,))
        conn.commit()
