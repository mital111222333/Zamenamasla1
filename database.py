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
import json
import sqlite3
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

        conn.commit()
        _migrate(conn)
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
    }
    for col, ddl in new_shop_cols.items():
        if col not in shop_cols:
            conn.execute(f"ALTER TABLE shops ADD COLUMN {col} {ddl}")

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
    }
    for col, ddl in to_add.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE oil_changes ADD COLUMN {col} {ddl}")
    if "reminder_sent" in cols and "reminder_count" not in cols:
        conn.execute("UPDATE oil_changes SET reminder_count=reminder_sent WHERE reminder_count=0")

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
            VALUES (?, ?, ?, 'shop', ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            BOOTSTRAP_SHOP_USERNAME, generate_password_hash(shop_password), _encrypt_password(shop_password),
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
            "VALUES (?, ?, ?, 'admin', 'Платформа', 1)",
            (BOOTSTRAP_ADMIN_USERNAME, generate_password_hash(admin_password), _encrypt_password(admin_password))
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


# ---------- Аккаунты точек (shops) ----------

def create_shop(username: str, password: str, shop_name: str = None, phone: str = None,
                 address: str = None, hours: str = None, lat: float = None, lon: float = None,
                 notify_telegram_id: str = None, role: str = "shop") -> dict:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO shops (username, password_hash, password_plain, role, shop_name, phone, address, hours, lat, lon,
                                anpr_token, notify_telegram_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (username, generate_password_hash(password), _encrypt_password(password), role, shop_name,
              phone, address, hours, lat, lon, secrets.token_urlsafe(8), notify_telegram_id))
        conn.commit()
        return get_shop(cur.lastrowid)


def reset_shop_password(shop_id: int, new_password: str):
    """Сбрасывает пароль точки — обновляет и хэш (для входа), и зашифрованную
    копию (чтобы платформенный админ мог посмотреть новый пароль в /admin)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE shops SET password_hash=?, password_plain=? WHERE id=?",
            (generate_password_hash(new_password), _encrypt_password(new_password), shop_id)
        )
        conn.commit()


def authenticate_shop(username: str, password: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shops WHERE username=?", (username,)).fetchone()
        if not row or not row["is_active"]:
            return None
        if not check_password_hash(row["password_hash"], password):
            return None
        return dict(row)


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
    password_plain — расшифрованный пароль (чтобы платформенный админ мог его
    посмотреть, если точка забудет); может быть None для очень старых точек,
    заведённых до этой функции, или если SECRET_KEY менялся после создания."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM clients WHERE shop_id = s.id) as client_count
            FROM shops s WHERE s.role='shop' ORDER BY s.created_at DESC
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["password_plain"] = _decrypt_password(d.get("password_plain"))
            del d["password_hash"]  # хэш не нужен на клиенте, чтобы не путать с настоящим паролем
            result.append(d)
        return result


def set_shop_active(shop_id: int, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE shops SET is_active=? WHERE id=?", (1 if active else 0, shop_id))
        conn.commit()


def set_shop_language(shop_id: int, language: str):
    if language not in ("ru", "uz"):
        language = "ru"
    with get_conn() as conn:
        conn.execute("UPDATE shops SET language=? WHERE id=?", (language, shop_id))
        conn.commit()


def set_shop_sms_enabled(shop_id: int, enabled: bool):
    """Платформенный админ включает/выключает саму ВОЗМОЖНОСТЬ SMS для точки.
    Даже при включении SMS не заработают, пока точка сама не впишет свои
    данные Eskiz в своих настройках — это её собственный договор/аккаунт."""
    with get_conn() as conn:
        conn.execute("UPDATE shops SET sms_enabled=? WHERE id=?", (1 if enabled else 0, shop_id))
        conn.commit()


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


def username_taken(username: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM shops WHERE username=?", (username,)).fetchone() is not None


# ---------- Клиенты ----------

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
        conn.execute(
            "UPDATE clients SET telegram_id=?, full_name=?, linked_at=datetime('now') WHERE id=?",
            (telegram_id, full_name, client["id"])
        )
        conn.commit()
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
                "INSERT INTO cars (shop_id, plate_number, client_id, car_brand, car_model) VALUES (?, ?, ?, ?, ?)",
                (shop_id, plate_number, client_id, car_brand, car_model)
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
                (SELECT change_date FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as change_date,
                (SELECT mileage FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as mileage,
                (SELECT service_type FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as service_type,
                (SELECT oil_brand FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as oil_brand,
                (SELECT next_change_date FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as next_change_date,
                (SELECT next_mileage FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as next_mileage,
                (SELECT cost FROM oil_changes WHERE car_id=c.id ORDER BY change_date DESC, id DESC LIMIT 1) as cost
            FROM cars c JOIN clients cl ON cl.id = c.client_id
            WHERE c.shop_id=?
            ORDER BY c.created_at DESC
        """, (shop_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------- Замены масла / обслуживание ----------

def add_oil_change(car_id: int, mileage, service_type: str, oil_brand: str, filter_changed: bool,
                    cost, interval_value: int, interval_unit: str = "months", notes: str = "",
                    next_mileage=None, items=None):
    """items (необязательно) — детализированный список позиций вида
    [{"name": "Моторное масло", "brand": "MITANOL", "unit_price": 45000, "qty": 4, "total": 180000}, ...]
    Если передан — стоимость и итоговое описание считаются по нему, а service_type/oil_brand/cost
    выше игнорируются (оставлены для обратной совместимости со старым простым способом внесения,
    которым по-прежнему пользуется бот в Telegram)."""
    change_date = datetime.now().strftime("%Y-%m-%d")
    if interval_value:
        if interval_unit == "days":
            next_date = (datetime.now() + timedelta(days=interval_value)).strftime("%Y-%m-%d")
        else:
            next_date = (datetime.now() + relativedelta(months=interval_value)).strftime("%Y-%m-%d")
    else:
        next_date = None

    items_json = None
    if items:
        items_json = json.dumps(items, ensure_ascii=False)
        cost = round(sum(i.get("total", 0) for i in items))
        names = [i["name"] for i in items]
        service_type = ", ".join(names) if names else "Обслуживание"
        motor_oil = next((i for i in items if i.get("key") == "fluid_0"), None)
        oil_brand = motor_oil["brand"] if motor_oil and motor_oil.get("brand") else None
        filter_changed = any((i.get("key") or "").startswith("filter_") for i in items)

    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='done' WHERE car_id=? AND status='active'", (car_id,))
        cur = conn.execute("""
            INSERT INTO oil_changes
                (car_id, change_date, mileage, service_type, oil_brand, filter_changed, cost,
                 interval_months, interval_unit, next_change_date, next_mileage, items_json, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (car_id, change_date, mileage, service_type, oil_brand, int(bool(filter_changed)), cost,
              interval_value, interval_unit, next_date, next_mileage, items_json, notes))
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


def update_oil_change(oc_id: int, shop_id: int, change_date=None, mileage=None, next_mileage=None,
                       cost=None, interval_value=None, interval_unit=None, notes=None):
    """Редактирует базовые поля уже сохранённой записи (для исправления
    опечаток). Возвращает True, если запись найдена и принадлежит точке —
    иначе False (ничего не меняет), в том числе если это запись чужой точки."""
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
    if cost is not None:
        fields["cost"] = cost
    if notes is not None:
        fields["notes"] = notes

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


def delete_oil_change(oc_id: int, shop_id: int):
    """Удаляет запись (только если она принадлежит указанной точке). Если
    удалённая запись была 'active' (текущей) — делает активной следующую по
    свежести оставшуюся запись той же машины, чтобы напоминания продолжали
    работать корректно. Возвращает True, если запись была найдена и удалена."""
    existing = get_oil_change_for_shop(oc_id, shop_id)
    if not existing:
        return False

    with get_conn() as conn:
        conn.execute("DELETE FROM oil_changes WHERE id=?", (oc_id,))
        if existing["status"] == "active":
            next_row = conn.execute(
                "SELECT id FROM oil_changes WHERE car_id=? ORDER BY change_date DESC, id DESC LIMIT 1",
                (existing["car_id"],)
            ).fetchone()
            if next_row:
                conn.execute("UPDATE oil_changes SET status='active' WHERE id=?", (next_row["id"],))
        conn.commit()
    return True


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


def mark_reminder_sent(oil_change_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "UPDATE oil_changes SET reminder_count = reminder_count + 1, last_reminder_date=? WHERE id=?",
            (today, oil_change_id)
        )
        conn.commit()


def mark_booked(oil_change_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE oil_changes SET status='booked' WHERE id=?", (oil_change_id,))
        conn.commit()


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
                   s.shop_name, s.notify_telegram_id, s.language
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


def get_recent_broadcasts(shop_id: int, limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM broadcasts WHERE shop_id=? ORDER BY id DESC LIMIT ?", (shop_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- Экспорт/бэкап (для кнопки «скачать базу» у точки) ----------

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
                SELECT COALESCE(SUM(oc.cost), 0) as total, COUNT(*) as cnt
                FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
                WHERE c.shop_id=? AND oc.cost IS NOT NULL AND {date_filter}
            """, (shop_id, param)).fetchone()
            return {"total": row["total"], "count": row["cnt"]}

        return {
            "today": agg("oc.change_date = ?", today),
            "yesterday": agg("oc.change_date = ?", yesterday),
            "week": agg("oc.change_date >= ?", week_start),
            "month": agg("oc.change_date >= ?", month_start),
            "year": agg("oc.change_date >= ?", year_start),
        }


def get_revenue_range(shop_id: int, date_from: str, date_to: str) -> dict:
    """Выручка и число услуг за произвольный период (включительно с обеих
    сторон), например для выбора дат через календарь на сайте."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(oc.cost), 0) as total, COUNT(*) as cnt
            FROM oil_changes oc JOIN cars c ON c.id = oc.car_id
            WHERE c.shop_id=? AND oc.cost IS NOT NULL
              AND oc.change_date >= ? AND oc.change_date <= ?
        """, (shop_id, date_from, date_to)).fetchone()
        return {"total": row["total"], "count": row["cnt"]}


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
