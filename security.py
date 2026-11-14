"""
Защита OilBook — общие инструменты (аудит безопасности, раунд 3).

- журнал подозрительных событий (таблица security_events + лог сервера +
  срочные события сразу в Telegram администратору платформы);
- ограничение частоты запросов (сколько раз за минуту с одного адреса);
- проверка надёжности пароля;
- проверка переменных окружения при запуске;
- определение типа загруженного файла по его содержимому (а не по имени).

Всё хранится в памяти процесса или в той же базе SQLite — внешние сервисы
(Redis и т.п.) не нужны.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger("security")

# ---------- Журнал подозрительных событий ----------

# Насколько событие важно: high — сразу сообщаем администратору в Telegram.
LOW, MEDIUM, HIGH = "low", "medium", "high"

EVENT_KEEP_DAYS = 90
_ALERT_EVERY_SEC = 60 * 60       # одно и то же срочное событие с одного адреса — не чаще раза в час
_alert_lock = threading.Lock()
_alert_last = {}
_table_ready = [False]
_notify = [None]                 # функция «написать администратору» — задаёт webapp


def set_notifier(fn):
    """fn(text) — отправка срочного сообщения администратору платформы."""
    _notify[0] = fn


def _ensure_table(conn):
    if _table_ready[0]:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            severity TEXT NOT NULL,
            ip TEXT,
            username TEXT,
            path TEXT,
            details TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_at ON security_events(created_at)")
    _table_ready[0] = True


def log_event(kind, severity=MEDIUM, ip=None, username=None, path=None, **details):
    """Записывает событие безопасности. Никогда не роняет основной запрос:
    если база недоступна — событие остаётся хотя бы в логе сервера.
    Пароли и коды сюда НЕ передавать."""
    username = (str(username)[:64] if username else None)
    info = json.dumps(details, ensure_ascii=False, default=str)[:1000] if details else None
    line = f"[SECURITY:{severity}] {kind} ip={ip} user={username} path={path} {info or ''}"
    if severity == HIGH:
        logger.warning(line)
    else:
        logger.info(line)
    try:
        import database as db
        with db.WRITE_LOCK, db.get_conn() as conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO security_events (created_at, kind, severity, ip, username, path, details) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kind, severity, ip, username,
                 (path or "")[:200] or None, info))
            # старое чистим изредка (примерно раз на 200 записей)
            if int(time.time() * 1000) % 200 == 0:
                cutoff = (datetime.now() - timedelta(days=EVENT_KEEP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("DELETE FROM security_events WHERE created_at < ?", (cutoff,))
            conn.commit()
    except Exception as e:  # журнал не должен ломать работу сайта
        logger.error(f"security_events: не записано: {e}")
    if severity == HIGH:
        _alert(kind, ip, username, path, details)


def _alert(kind, ip, username, path, details):
    fn = _notify[0]
    if not fn:
        return
    key = (kind, ip, username)
    now = time.time()
    with _alert_lock:
        if now - _alert_last.get(key, 0) < _ALERT_EVERY_SEC:
            return
        if len(_alert_last) > 5000:
            _alert_last.clear()
        _alert_last[key] = now
    text = (f"🛡 OilBook: подозрительная активность\n"
            f"Событие: {EVENT_TITLES.get(kind, kind)}\n"
            f"Адрес (IP): {ip or '?'}\n"
            + (f"Логин: {username}\n" if username else "")
            + (f"Страница: {path}\n" if path else "")
            + (f"Подробности: {json.dumps(details, ensure_ascii=False, default=str)[:400]}\n" if details else "")
            + "Если это были не вы — смените пароль в /admin.")
    try:
        threading.Thread(target=fn, args=(text,), daemon=True).start()
    except Exception as e:
        logger.error(f"security alert не отправлен: {e}")


EVENT_TITLES = {
    "login_failed": "неверный пароль при входе",
    "login_locked": "вход заблокирован: слишком много неверных паролей (похоже на подбор)",
    "admin_login": "вход в платформенную админку",
    "admin_session_expired": "сессия админки истекла",
    "reset_code_failed": "неверный код восстановления пароля",
    "reset_code_bruteforce": "подбор кода восстановления пароля",
    "password_reset": "пароль изменён через код из Telegram",
    "csrf_blocked": "запрос с чужого сайта отклонён (CSRF)",
    "rate_limited": "слишком частые запросы с одного адреса",
    "upload_rejected": "загружен файл недопустимого типа",
    "payment_bad_sign": "уведомление об оплате с неверной подписью",
    "payment_amount_low": "оплата меньше ожидаемой суммы",
}


def recent_events(limit=200, severity=None):
    import database as db
    limit = max(1, min(int(limit or 200), 1000))
    with db.get_conn() as conn:
        _ensure_table(conn)
        if severity:
            rows = conn.execute("SELECT * FROM security_events WHERE severity=? ORDER BY id DESC LIMIT ?",
                                (severity, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["title"] = EVENT_TITLES.get(d["kind"], d["kind"])
        out.append(d)
    return out


# ---------- Ограничение частоты запросов ----------

_rl_lock = threading.Lock()
_rl_hits = {}
_rl_last_clean = [0.0]


def rate_hit(bucket, key, limit, window_sec) -> bool:
    """Учитывает запрос и говорит, превышен ли предел: True — запрос лишний
    (отвечаем 429). Окно «скользящее» по корзинам фиксированной длины."""
    now = time.time()
    slot = int(now // window_sec)
    k = (bucket, key, window_sec, slot)
    with _rl_lock:
        if now - _rl_last_clean[0] > 60:
            _rl_last_clean[0] = now
            for old in [x for x in _rl_hits if x[3] < int(now // x[2]) - 1]:
                _rl_hits.pop(old, None)
        n = _rl_hits.get(k, 0) + 1
        _rl_hits[k] = n
        prev = _rl_hits.get((bucket, key, window_sec, slot - 1), 0)
    # учитываем часть предыдущего окна — так нельзя удвоить предел на стыке окон
    frac = 1 - (now % window_sec) / window_sec
    return n + prev * frac > limit


def rate_reset():
    """Для тестов."""
    with _rl_lock:
        _rl_hits.clear()


# (префикс адреса, корзина, предел, окно в секундах) — первое совпадение.
# Пределы с большим запасом: обычный человек и табло (опрос раз в секунду)
# их не достигают, а перебор токенов/паролей и «заваливание» запросами — да.
RATE_RULES = (
    ("/login", "login", 30, 60),
    ("/api/forgot_password/", "forgot", 20, 60),
    ("/api/register", "register", 60, 60),
    ("/api/hamyon/", "hamyon", 120, 60),
    ("/api/anpr/", "anpr", 240, 60),
    ("/api/display_state/", "display", 400, 60),
    ("/passport/", "passport", 60, 60),
    ("/display/", "pages", 60, 60),
    ("/scanner/", "pages", 60, 60),
    ("/r/", "pages", 60, 60),
)
GLOBAL_RATE = (1500, 60)  # любой адрес сайта: не больше 1500 запросов в минуту с одного IP


def rate_rule_for(path):
    for prefix, bucket, limit, window in RATE_RULES:
        if path.startswith(prefix):
            return bucket, limit, window
    return None


# ---------- Пароли ----------

PASSWORD_MIN = 8
PASSWORD_MAX = 100
_COMMON = {
    "12345678", "123456789", "1234567890", "123123123", "11111111", "00000000", "12341234",
    "87654321", "password", "password1", "qwertyui", "qwerty123", "qwerty12", "1q2w3e4r",
    "1qaz2wsx", "abcd1234", "iloveyou", "admin123", "administrator", "oilbook1", "oilbook123",
    "parol123", "parolparol", "uzbekistan", "tashkent", "11223344", "12121212", "q1w2e3r4",
    "zxcvbnm1", "asdfghjk", "88888888", "99999999", "55555555", "77777777", "qwertyuiop",
}


def password_problem(password, username=None):
    """None — пароль годится; иначе короткий код причины:
    'short' / 'long' / 'common' / 'same_as_login'."""
    password = password or ""
    if len(password) < PASSWORD_MIN:
        return "short"
    if len(password) > PASSWORD_MAX:
        return "long"
    low = password.lower()
    if low in _COMMON or len(set(low)) <= 2:
        return "common"
    if username and low == str(username).strip().lower():
        return "same_as_login"
    return None


# ---------- Загруженные файлы: тип по содержимому ----------

def sniff_upload(data: bytes):
    """Тип файла по первым байтам (имя и тип, присланные браузером, можно
    подделать). Возвращает (mime, расширение) или (None, None). SVG, HTML и
    всё прочее, в чём может прятаться скрипт, — не принимаем."""
    head = data[:16] if data else b""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if head.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"):
        return "image/heic", ".heic"
    return None, None


SAFE_INLINE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif",
                    "application/pdf"}


# ---------- Переменные окружения ----------

def check_env(environ=None):
    """Проверяет настройки сервера. Возвращает список (уровень, текст);
    уровень 'critical' — серьёзная дыра, 'warning' — стоит исправить."""
    env = os.environ if environ is None else environ
    out = []

    def crit(msg):
        out.append(("critical", msg))

    def warn(msg):
        out.append(("warning", msg))

    sk = env.get("SECRET_KEY", "")
    if not sk:
        crit("SECRET_KEY не задан: входы слетают при каждом перезапуске, а пароль SMS (Eskiz) "
             "в базе шифруется общеизвестным ключом")
    elif len(sk) < 32:
        crit("SECRET_KEY короче 32 символов — подделать вход проще. Задайте длинную случайную строку")
    elif sk.lower() in ("secret", "changeme", "любая_длинная_случайная_строка") or len(set(sk)) < 8:
        crit("SECRET_KEY похож на пример из инструкции — задайте свой случайный")
    if not env.get("BOT_TOKEN"):
        warn("BOT_TOKEN не задан — бот, коды восстановления и уведомления не работают")
    pub = env.get("PUBLIC_URL", "")
    if not pub:
        warn("PUBLIC_URL не задан — cookie входа без флага Secure, нет перенаправления на https")
    elif not pub.startswith("https://"):
        crit("PUBLIC_URL не начинается с https:// — пароли и данные идут по сети открытым текстом")
    if not env.get("ADMIN_TELEGRAM_ID"):
        warn("ADMIN_TELEGRAM_ID не задан — некому слать предупреждения о подозрительной активности и копии базы")
    if not env.get("BACKUP_PASSWORD"):
        warn("BACKUP_PASSWORD не задан — резервные копии базы (телефоны клиентов) уходят без шифрования")
    elif len(env.get("BACKUP_PASSWORD", "")) < 12:
        warn("BACKUP_PASSWORD короче 12 символов — копию проще расшифровать подбором")
    pap = env.get("PLATFORM_ADMIN_PASSWORD", "")
    if pap and password_problem(pap, env.get("PLATFORM_ADMIN_USERNAME") or "admin"):
        crit("PLATFORM_ADMIN_PASSWORD слишком простой (нужно 8+ символов, не из списка частых)")
    if env.get("FLASK_DEBUG") in ("1", "true", "True") or env.get("FLASK_ENV") == "development":
        crit("Включён режим отладки Flask (FLASK_DEBUG/FLASK_ENV) — на рабочем сервере его нужно выключить")
    if env.get("HAMYON_SHOP_ID") and not env.get("HAMYON_SHOP_KEY"):
        crit("HAMYON_SHOP_ID задан без HAMYON_SHOP_KEY — подпись оплат проверить нечем")
    return out


def log_env_report(environ=None):
    problems = check_env(environ)
    if not problems:
        logger.info("Проверка окружения: всё в порядке")
    for level, msg in problems:
        (logger.critical if level == "critical" else logger.warning)(f"Проверка окружения: {msg}")
    return problems
