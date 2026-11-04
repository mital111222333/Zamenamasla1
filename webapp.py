"""
Веб-панель системы учёта замены масла — мультитенантная версия.

- /login — вход по логину/паролю (для точки замены масла ИЛИ платформенного
  администратора). Никакого доступа без входа.
- Точка (role='shop') видит и редактирует ТОЛЬКО свои данные — во всех
  запросах ниже используется g.shop_id из сессии, и все обращения к БД идут
  с этим shop_id. Это и есть изоляция данных между точками.
- Админ (role='admin') управляет списком точек на /admin — создаёт новые,
  включает/выключает — но не видит клиентских данных ни одной из них.
"""

import os
import re
import time
import json
import secrets
import logging
import urllib.parse
import threading
import requests
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from flask import Flask, request, jsonify, render_template_string, Response, session, redirect, url_for, g, send_file, make_response

import database as db
import backup_store
import i18n
import help_content
import glass_theme

logger = logging.getLogger(__name__)

app = Flask(__name__)


_GZIP_TYPES = ("text/html", "application/json", "text/css", "application/javascript",
               "text/javascript", "text/plain", "application/manifest+json", "image/svg+xml")


@app.after_request
def _no_stale_cache(resp):
    """Данные не кешируем в браузере: иначе при возврате в приложение/кнопке
    «назад» телефон показывает старые цифры. Статика (иконки, шрифты)
    кешируется как обычно.

    Слабый интернет:
    - страница приложения (~600 КБ) получает «отпечаток» (ETag): телефон
      хранит её у себя, но каждый раз сверяется с сервером — если ничего не
      поменялось, сервер отвечает коротким «не изменилось» (304) вместо
      повторной загрузки всей страницы;
    - текст (страницы, данные) отдаётся сжатым (gzip) — в 4–5 раз меньше."""
    path = request.path or ""
    is_html = resp.mimetype == "text/html"
    if is_html and path == "/" and request.method == "GET" and resp.status_code == 200 and not resp.direct_passthrough:
        resp.headers["Cache-Control"] = "private, no-cache"
        try:
            resp.add_etag()
            resp.make_conditional(request)
        except Exception:
            resp.headers["Cache-Control"] = "no-store, max-age=0"
    elif path.startswith("/api/") or is_html:
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    elif path in ("/static/manifest.json", "/sw.js"):
        # по manifest телефон рисует заставку при запуске — всегда свежий
        resp.headers["Cache-Control"] = "no-cache"
    try:
        _gzip_response(resp)
    except Exception as e:  # сжатие — только ускорение, ответ уйдёт и без него
        logger.warning(f"gzip: {e}")
    return resp


def _gzip_response(resp):
    if resp.direct_passthrough or resp.is_streamed or resp.status_code in (204, 206, 304) or resp.status_code < 200:
        return
    if resp.mimetype not in _GZIP_TYPES or "Content-Encoding" in resp.headers:
        return
    if "gzip" not in (request.headers.get("Accept-Encoding") or "").lower():
        return
    data = resp.get_data()
    if len(data) < 1024:
        return
    import gzip
    comp = gzip.compress(data, compresslevel=6)
    if len(comp) >= len(data):
        return
    resp.set_data(comp)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(comp))
    resp.vary.add("Accept-Encoding")
    etag = resp.headers.get("ETag")
    if etag and not etag.startswith("W/"):
        resp.headers["ETag"] = "W/" + etag  # сжатый вариант — «слабый» отпечаток


@app.after_request
def _security_headers(resp):
    """Базовые заголовки безопасности. Встраивать сайт во фрейм можно только
    ему самому и Telegram (панель открывается как Telegram Mini App, а в
    веб-версии Telegram это фрейм) — чужой сайт не сможет «накрыть» кнопки
    панели своими (clickjacking). Скрипты CSP не ограничиваем: в страницах
    много встроенного JS."""
    resp.headers.setdefault("Content-Security-Policy",
                            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    # ссылки паспорта и табло содержат токен — не отдаём полный адрес чужим сайтам
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.is_secure:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp


# Камера ANPR шлёт номера со своего устройства, а не из браузера — её не проверяем
# (там защита — секретный токен в адресе).
_CSRF_EXEMPT_PREFIXES = ("/api/anpr/", "/api/hamyon/")


# Общий предел MAX_CONTENT_LENGTH (300 МБ) нужен только восстановлению базы.
# Остальным адресам хватает 20 МБ (чек, Excel, фото) — иначе любой вошедший
# (а регистрация открыта) мог бы слать огромные запросы и забивать память
# единственного процесса, где работают и сайт, и бот.
UPLOAD_LIMIT_BYTES = 20 * 1024 * 1024
_BIG_UPLOAD_PATHS = ("/api/admin/restore_backup",)


@app.before_request
def _limit_request_size():
    n = request.content_length
    if n and n > UPLOAD_LIMIT_BYTES and request.path not in _BIG_UPLOAD_PATHS:
        return jsonify({"ok": False, "error": "файл слишком большой"}), 413
    return None


@app.before_request
def _csrf_origin_check():
    """Защита от CSRF: изменяющий запрос (POST/PUT/DELETE) принимаем, только
    если браузер прислал его с нашего же сайта. Иначе чужая страница могла
    бы от имени вошедшего владельца что-то удалить или изменить. Сравниваем
    только домен (без http/https — за прокси схема может отличаться)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if request.path.startswith(_CSRF_EXEMPT_PREFIXES):
        return None
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return None  # не браузер (или очень старый) — у таких нет чужих cookie
    source_host = urllib.parse.urlparse(source).netloc.lower()
    allowed = {(request.host or "").lower()}
    public_host = urllib.parse.urlparse(os.environ.get("PUBLIC_URL", "")).netloc.lower()
    if public_host:
        allowed.add(public_host)
    if source_host and source_host in allowed:
        return None
    logger.warning(f"CSRF: отклонён {request.method} {request.path} с источника {source_host or source!r}")
    return jsonify({"ok": False, "error": "запрос с чужого сайта отклонён"}), 403

# ---------- Защита от дублей при плохом интернете ----------
# Приложение отправляет каждое изменение (замена, оплата, склад…) с ключом
# X-Request-Id. Если связь оборвалась уже ПОСЛЕ того, как сервер всё
# сохранил, человек нажимает ещё раз — запрос приходит с тем же ключом, и
# сервер возвращает прежний ответ, а не создаёт вторую запись/списание.
_IDEM_LOCK = threading.Lock()
_IDEM = {}
_IDEM_TTL = 15 * 60
_IDEM_LAST_CLEAN = [0.0]


def _idem_key():
    rid = request.headers.get("X-Request-Id") or ""
    if not rid or len(rid) > 100 or request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if not request.path.startswith("/api/"):
        return None
    return (session.get("role"), session.get("shop_id"), session.get("username"),
            request.method, request.path, rid)


@app.before_request
def _idem_before():
    key = _idem_key()
    if key is None:
        return None
    now = time.time()
    with _IDEM_LOCK:
        if now - _IDEM_LAST_CLEAN[0] > 60:
            _IDEM_LAST_CLEAN[0] = now
            for k in [k for k, v in _IDEM.items() if now - v["ts"] > _IDEM_TTL and v["ev"].is_set()]:
                _IDEM.pop(k, None)
        ent = _IDEM.get(key)
        if ent is None:
            _IDEM[key] = {"ev": threading.Event(), "resp": None, "ts": now}
            g._idem_key = key
            return None
    # тот же запрос уже был — ждём, пока первый закончится, и отдаём его ответ
    ent["ev"].wait(90)
    if ent["resp"] is None:
        return jsonify({"ok": False, "error": "запрос ещё выполняется — подождите и обновите страницу"}), 409
    body, status, mimetype = ent["resp"]
    resp = Response(body, status=status, mimetype=mimetype)
    resp.headers["X-Idempotent-Replay"] = "1"
    return resp


_USD_COST_KEYS = ("purchase_usd_cents", "purchase_currency")


def _strip_usd_cost(obj):
    if isinstance(obj, dict):
        for k in _USD_COST_KEYS:
            obj.pop(k, None)
        for v in obj.values():
            _strip_usd_cost(v)
    elif isinstance(obj, list):
        for v in obj:
            _strip_usd_cost(v)
    return obj


@app.after_request
def _hide_usd_cost(resp):
    """Филиал и сотрудник не видят закупку — значит и закупку в $ тоже: из
    любого JSON-ответа для них убираем долларовую цену закупки товара."""
    if not (getattr(g, "is_branch", False) or getattr(g, "is_employee", False)):
        return resp
    if resp.mimetype != "application/json" or resp.direct_passthrough:
        return resp
    body = resp.get_data()
    if b"purchase_usd_cents" not in body and b"purchase_currency" not in body:
        return resp
    try:
        data = _strip_usd_cost(json.loads(body))
    except ValueError:
        return resp
    resp.set_data(json.dumps(data, ensure_ascii=False))
    return resp


@app.after_request
def _idem_after(resp):
    key = getattr(g, "_idem_key", None)
    if key is None:
        return resp
    g._idem_key = None
    with _IDEM_LOCK:
        ent = _IDEM.get(key)
    if ent is None:
        return resp
    if resp.status_code < 500 and resp.mimetype == "application/json" and not resp.direct_passthrough:
        ent["resp"] = (resp.get_data(), resp.status_code, resp.mimetype)
        ent["ts"] = time.time()
    else:
        with _IDEM_LOCK:
            _IDEM.pop(key, None)  # ошибка сервера/файл — повтор выполнится заново
    ent["ev"].set()
    return resp


@app.teardown_request
def _idem_teardown(exc):
    key = getattr(g, "_idem_key", None)
    if key is None:
        return
    with _IDEM_LOCK:
        ent = _IDEM.pop(key, None)
    if ent is not None:
        ent["ev"].set()


if not os.environ.get("SECRET_KEY") or len(os.environ.get("SECRET_KEY", "")) < 32:
    # без постоянного ключа: все сессии сбрасываются при каждом перезапуске,
    # а пароль Eskiz в базе шифруется общеизвестным ключом (см. database.py)
    logger.critical("SECRET_KEY не задан или короче 32 символов — задайте длинный случайный "
                    "SECRET_KEY в переменных окружения хостинга")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # самый большой законный файл — резервная копия базы
# SameSite=None (только на https): иначе в веб-версии Telegram, где панель
# открыта во фрейме, браузер не отправит cookie входа и войти будет нельзя.
# От подделки запросов чужими сайтами защищает проверка Origin (_csrf_origin_check).
_COOKIE_SECURE = os.environ.get("PUBLIC_URL", "").startswith("https://")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="None" if _COOKIE_SECURE else "Lax",
                  SESSION_COOKIE_SECURE=_COOKIE_SECURE)

PUBLIC_URL = os.environ.get("PUBLIC_URL", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
app.jinja_env.globals["tg_bot_username"] = BOT_USERNAME.lstrip("@")
ADMIN_TELEGRAM_ID = os.environ.get("ADMIN_TELEGRAM_ID", "")


def _send_telegram_document(chat_id, file_path, filename, caption=""):
    """Отправка файла (например, резервной копии базы) напрямую через HTTP
    API Telegram, без участия асинхронного бот-процесса. Возвращает
    (успех, сообщение) — сообщение объясняет причину, если не получилось,
    чтобы её можно было сразу показать в интерфейсе, а не только в логах
    сервера, которые обычному пользователю недоступны."""
    if not BOT_TOKEN:
        return False, "BOT_TOKEN не задан на сервере"
    if not chat_id:
        return False, "ADMIN_TELEGRAM_ID не задан на сервере — некому отправлять"
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (filename, f)},
                timeout=300,  # часть копии до 45 МБ на медленном канале
            )
        if resp.ok:
            return True, None
        return False, f"Telegram отклонил файл: HTTP {resp.status_code} — {resp.text[:300]}"
    except Exception as e:
        return False, f"Не удалось отправить файл: {e}"


def _create_and_send_backup(chat_id, caption_note=""):
    """Строит резервную копию базы (через безопасный backup API SQLite —
    не ломается, даже если в этот момент кто-то пишет в базу) и
    отправляет её файлом в Telegram. Общая логика для ночной автоматической
    отправки и для кнопки 'отправить сейчас' в админке — чтобы не
    дублировать её в двух местах."""
    import sqlite3
    today_str = datetime.now().strftime("%Y-%m-%d")
    backup_path, gz_path = db.make_compressed_backup(f"manual_{today_str}")
    parts, extra = [], []
    try:
        size_mb = os.path.getsize(gz_path) / 1024 / 1024
        # шифруем паролем (если задан) — в копии телефоны клиентов всех точек
        path, name, enc = backup_store.prepare(gz_path, f"oilbot_backup_{today_str}.db.gz")
        if path != gz_path:
            extra.append(path)
        lock = "🔒 зашифрована" if enc else "⚠️ без шифрования — задайте BACKUP_PASSWORD"
        # больше лимита Telegram — шлём частями (иначе копия не дошла бы вовсе)
        parts = db.split_backup(path)
        for i, part in enumerate(parts, 1):
            caption = (f"📦 Резервная копия базы данных за {today_str} ({size_mb:.1f} МБ, сжатая, "
                       f"{lock}){caption_note}")
            if len(parts) > 1:
                caption += f"\nЧасть {i} из {len(parts)} — для восстановления выберите все части сразу"
            ok, err = _send_telegram_document(
                chat_id, part, name if len(parts) == 1 else f"{name}.part{i:02d}", caption=caption)
            if not ok:
                return False, err, size_mb
        # вторая копия — в Google Диск (если настроен); старше 30 дней удаляются там сами
        gd_ok, gd_err = backup_store.to_gdrive(path, name)
        if gd_ok is False:
            _send_telegram_message(chat_id, f"⚠️ Копия НЕ загружена в Google Диск: {gd_err}")
        return True, None, size_mb
    finally:
        for pth in {backup_path, gz_path, *parts, *extra}:
            if os.path.exists(pth):
                os.remove(pth)


def _validate_sqlite_backup(file_path):
    """Проверяет, что загруженный файл — действительно база данных этой
    платформы (SQLite с нужными таблицами), а не случайный или чужой файл,
    прежде чем позволить им заменить текущую живую базу."""
    import sqlite3
    required_tables = {"shops", "clients", "cars", "oil_changes"}
    try:
        conn = sqlite3.connect(file_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
    except Exception as e:
        return False, f"Это не похоже на файл базы данных: {e}"
    missing = required_tables - tables
    if missing:
        return False, f"В файле нет нужных таблиц ({', '.join(sorted(missing))}) — это не резервная копия этой платформы"
    return True, None


RESTORE_MAX_BYTES = 1024 * 1024 * 1024  # 1 ГБ распакованной базы


def _restore_from_backup(uploaded_bytes, notify_chat_id=None):
    """Заменяет текущую базу данных на загруженную резервную копию —
    атомарно (через os.replace, чтобы не оставить базу в 'наполовину
    заменённой' при сбое посередине). Временный файл кладём В ТУ ЖЕ папку,
    что и текущая база (а не просто /tmp) — иначе на Railway, где база
    лежит на отдельном постоянном диске (Volume), atomic-замена между
    разными дисками может не сработать. Перед заменой отправляет ТЕКУЩУЮ
    базу владельцу как safety-копию — чтобы даже ошибочное восстановление
    можно было откатить."""
    same_dir_tmp = os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), ".restore_upload.db")
    if backup_store.is_encrypted(uploaded_bytes):
        # зашифрованная копия (.enc) — сначала расшифровываем паролем с сервера
        try:
            uploaded_bytes = backup_store.decrypt_bytes(uploaded_bytes, backup_store.backup_password())
        except ValueError as e:
            return False, f"Не удалось расшифровать копию: {e}"
    if uploaded_bytes[:2] == b"\x1f\x8b":
        # сжатая копия (.db.gz) — распаковываем, но не больше RESTORE_MAX_BYTES:
        # маленький «gz-бомба» файл иначе раздулся бы в памяти до гигабайт
        import zlib
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            uploaded_bytes = d.decompress(uploaded_bytes, RESTORE_MAX_BYTES)
            if d.unconsumed_tail:
                return False, f"Распакованный файл больше {RESTORE_MAX_BYTES // (1024 * 1024)} МБ — это не похоже на копию базы"
        except Exception as e:
            return False, f"Не удалось распаковать файл: {e}"
    with open(same_dir_tmp, "wb") as f:
        f.write(uploaded_bytes)
    valid, err = _validate_sqlite_backup(same_dir_tmp)
    if not valid:
        os.remove(same_dir_tmp)
        return False, err
    if notify_chat_id:
        _create_and_send_backup(notify_chat_id)  # снимок ТЕКУЩЕГО состояния перед заменой, для отката
    # Копируем содержимое в ЖИВУЮ базу штатным механизмом SQLite (backup API),
    # а не подменой файла: база работает в режиме WAL (рядом файлы -wal/-shm),
    # и подмена одного файла могла бы смешать старый журнал с новой базой.
    # Под общим замком — чтобы в этот момент никто ничего не записал.
    import sqlite3
    with db.WRITE_LOCK:
        src = sqlite3.connect(same_dir_tmp)
        dst = sqlite3.connect(db.DB_PATH, timeout=60)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    os.remove(same_dir_tmp)
    # копия могла быть сделана старой версией программы — докатываем схему
    # (новые таблицы/колонки создаются, существующие данные не трогаются)
    try:
        db.init_db()
    except Exception as e:
        print(f"init_db после восстановления: {e}")
    return True, None


DISPLAY_SHOW_SECONDS = int(os.environ.get("DISPLAY_SHOW_SECONDS", "45"))


def _tg_api(method: str, data: dict = None, files: dict = None):
    if not BOT_TOKEN:
        return None
    try:
        resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                             data=data, files=files, timeout=30)
        if not resp.ok:
            logger.warning(f"Telegram {method}: HTTP {resp.status_code} — {resp.text[:300]}")
            return None
        return resp.json().get("result")
    except Exception as e:
        logger.error(f"Telegram {method} не выполнен: {e}")
        return None


def _send_telegram_message(chat_id, text) -> bool:
    """Отправка сообщения напрямую через HTTP API Telegram — синхронно, без
    участия основного бот-процесса (веб-панель работает в отдельном потоке
    того же процесса, но без доступа к его асинхронному event loop).
    Частая причина отказа: получатель ни разу не писал этому боту — Telegram
    не разрешает боту писать первым, даже если chat_id указан верно."""
    if not BOT_TOKEN:
        logger.warning("Telegram-сообщение не отправлено: BOT_TOKEN не задан")
        return False
    if not chat_id:
        logger.warning("Telegram-сообщение не отправлено: chat_id не указан")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if not resp.ok:
            logger.warning(f"Telegram отклонил сообщение для chat_id={chat_id}: "
                            f"HTTP {resp.status_code} — {resp.text[:300]}")
        return resp.ok
    except Exception as e:
        logger.error(f"Не удалось отправить Telegram-сообщение для chat_id={chat_id}: {e}")
        return False

# Состояние табло — отдельно для каждой точки (по shop_id), чтобы камера
# одной точки не могла подсветить экран другой.
_display_lock = threading.Lock()
_display_states = {}

# Марки и их модели — для кнопок-подсказок под полем «Модель» (самые
# частые в Узбекистане — первыми). Названия марок не менять: они уже
# сохранены у машин в базе.
CAR_MODELS = {
    "Chevrolet": ["Cobalt", "Nexia 3", "Gentra", "Spark", "Damas", "Labo", "Lacetti", "Malibu", "Malibu 2",
                  "Tracker", "Onix", "Captiva", "Equinox", "Monza", "Tahoe", "Traverse", "Trailblazer",
                  "Aveo", "Cruze", "Orlando", "Epica"],
    "Daewoo": ["Nexia", "Nexia 2", "Matiz", "Lacetti", "Damas", "Labo", "Tico", "Espero", "Gentra"],
    "Ravon": ["R2", "R3", "R4", "Gentra", "Nexia R3", "Matiz"],
    "BYD": ["Song Plus", "Chazor", "Han", "Tang", "Seal", "Song L", "Qin Plus", "Destroyer 05", "Seagull",
            "Dolphin", "Atto 3", "Yuan Plus", "Leopard 5"],
    "Kia": ["K5", "Sportage", "Rio", "Cerato", "K3", "Seltos", "Sorento", "Carnival", "K8", "Optima",
            "Picanto", "Soul", "Sonet", "Mohave"],
    "Hyundai": ["Elantra", "Sonata", "Tucson", "Santa Fe", "Accent", "Solaris", "Creta", "Palisade", "Kona",
                "Grandeur", "Ioniq 5", "Starex", "Porter"],
    "Toyota": ["Camry", "Corolla", "RAV4", "Land Cruiser Prado", "Land Cruiser 200", "Land Cruiser 300",
               "Hilux", "Fortuner", "Highlander", "C-HR", "Yaris", "Avalon", "Sequoia", "Tundra"],
    "Lexus": ["LX 570", "LX 600", "RX", "ES", "NX", "GX", "LS"],
    "Chery": ["Tiggo 2 Pro", "Tiggo 4 Pro", "Tiggo 7 Pro", "Tiggo 8 Pro", "Arrizo 5", "Arrizo 6 Pro", "Arrizo 8",
              "Omoda C5", "Jaecoo J7", "Exeed TXL", "Exeed LX"],
    "Haval": ["Jolion", "H6", "Dargo", "M6", "H9"],
    "Geely": ["Monjaro", "Tugella", "Coolray", "Atlas", "Emgrand", "Okavango", "Geometry C"],
    "Changan": ["CS35 Plus", "CS55 Plus", "CS75 Plus", "UNI-K", "UNI-V", "Eado", "Alsvin"],
    "Jetour": ["Dashing", "X70 Plus", "X90 Plus", "T2"],
    "Li Auto": ["L6", "L7", "L8", "L9"],
    "Zeekr": ["001", "007", "7X", "X"],
    "Leapmotor": ["C10", "C11", "C16"],
    "Hongqi": ["H5", "H9", "HS5", "E-HS9"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
    "Mercedes-Benz": ["C-Class", "E-Class", "S-Class", "GLA", "GLC", "GLE", "GLS", "G-Class", "ML", "CLS",
                      "Sprinter", "Vito", "Actros"],
    "BMW": ["3 Series", "5 Series", "7 Series", "X1", "X3", "X5", "X6", "X7", "M5"],
    "Audi": ["A4", "A6", "A8", "Q3", "Q5", "Q7", "Q8", "e-tron"],
    "Volkswagen": ["Polo", "Jetta", "Passat", "Golf", "Tiguan", "Touareg", "Teramont", "ID.4", "ID.6",
                   "Caddy", "Transporter"],
    "Skoda": ["Rapid", "Octavia", "Superb", "Kodiaq", "Karoq"],
    "Porsche": ["Cayenne", "Macan", "Panamera", "911", "Taycan"],
    "Land Rover": ["Range Rover", "Range Rover Sport", "Velar", "Evoque", "Discovery", "Defender"],
    "Nissan": ["X-Trail", "Qashqai", "Almera", "Teana", "Patrol", "Juke", "Murano", "Pathfinder", "Sunny"],
    "Honda": ["Civic", "Accord", "CR-V", "HR-V", "Fit", "Odyssey", "Pilot"],
    "Mazda": ["3", "6", "CX-5", "CX-30", "CX-9"],
    "Mitsubishi": ["Lancer", "Outlander", "Pajero", "Pajero Sport", "ASX", "L200"],
    "Subaru": ["Forester", "Outback", "XV", "Impreza"],
    "Suzuki": ["Swift", "Vitara", "Jimny", "SX4"],
    "Ford": ["Focus", "Fusion", "Mondeo", "Explorer", "Escape", "Ranger", "Mustang", "Transit"],
    "Isuzu": ["NPR", "NQR", "NMR", "ELF", "D-Max"],
    "JAC": ["J7", "JS4", "S3", "T6", "N35", "N56", "N80", "N120"],
    "Lada (ВАЗ)": ["Vesta", "Granta", "Largus", "Priora", "Kalina", "Niva", "Niva Travel", "XRAY",
                   "2107", "2109", "2110", "2114"],
    "Datsun": ["on-DO", "mi-DO"],
    "ГАЗ": ["Газель Next", "Газель Бизнес", "ГАЗон Next", "ГАЗ-53", "ГАЗ-3307"],
    "УАЗ": ["Patriot", "Hunter", "Буханка", "Profi"],
    "КамАЗ": ["5320", "65115", "5490", "K5"],
    "MAN": ["TGS", "TGX", "CLA"],
    "Sinotruk": ["HOWO", "A7", "T7H", "Sitrak C7H"],
    "Shacman": ["F3000", "X3000"],
    "Foton": ["Aumark", "Auman"],
    "Iveco": ["Daily", "Stralis", "Trakker"],
}
CAR_BRANDS = list(CAR_MODELS) + ["Другое"]
SERVICE_TYPES = ["Замена масла", "Замена масла + фильтр", "Полное ТО", "Другое"]


def _pw_fingerprint(password_hash) -> str:
    """Короткий отпечаток текущего пароля (хвост его хэша — сам пароль из
    него не восстановить). Хранится в сессии при входе; сменили пароль —
    отпечаток перестаёт совпадать, и все старые входы закрываются."""
    return (password_hash or "")[-16:]


def _session_password_ok(current_fp) -> bool:
    saved = session.get("pwf")
    if saved is None:
        # вход сделан до этого обновления — запоминаем текущий отпечаток,
        # чтобы не выкидывать всех разом при выкатке
        session["pwf"] = current_fp
        return True
    return saved == current_fp


def _auth_fail():
    """Нет входа (истёк, пароль сменили, точку выключили). Запросы данных из
    приложения получают понятный ответ 401 — приложение само покажет
    «войдите заново» и откроет страницу входа. Раньше они получали HTML
    страницы входа, и разделы молча оставались пустыми. Обычный переход
    по ссылке (скачать Excel и т.п.) по-прежнему ведёт на страницу входа."""
    if request.path.startswith("/api/") and "text/html" not in (request.headers.get("Accept") or ""):
        return jsonify({"ok": False, "error": "session", "login": True}), 401
    return redirect(url_for("login_page"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") not in ("shop", "branch") or not session.get("shop_id"):
            return _auth_fail()
        shop = db.get_shop(session["shop_id"])
        if not shop or not shop["is_active"]:
            session.clear()
            return _auth_fail()
        if session.get("is_employee"):
            emp = db.get_active_employee(session.get("username") or "", session["shop_id"])
            if not emp:
                # сотрудника удалили/отключили — доступ закрывается сразу
                session.clear()
                return _auth_fail()
            cur_pwf = _pw_fingerprint(emp.get("password_hash"))
        else:
            cur_pwf = _pw_fingerprint(shop.get("password_hash"))
        if not _session_password_ok(cur_pwf):
            # пароль сменили — все, кто вошёл со старым паролем, выходят
            session.clear()
            return _auth_fail()
        g.shop_id = session["shop_id"]
        g.lang = shop.get("language") or "ru"
        g.T = i18n.get_texts(g.lang)
        g.is_employee = bool(session.get("is_employee"))
        # кто из сотрудников работает — его наличные копятся в его «кассе»
        g.employee_id = emp["id"] if g.is_employee else None
        g.is_branch = shop.get("role") == "branch"
        g.parent_shop_id = shop.get("parent_shop_id")
        # подписка: не оплачено (или новый филиал ещё не оплачен) — вся
        # панель закрыта, открыта только страница «Подписка» (там оплата)
        g.sub = db.subscription_state(shop)
        if g.sub["blocked"] and not getattr(view, "_sub_exempt", False):
            if request.path.startswith("/api/") and "text/html" not in (request.headers.get("Accept") or ""):
                return jsonify({"ok": False, "error": "subscription", "subscription": True}), 402
            return redirect("/subscription")
        # срок закончился — режим «только просмотр»: читать можно всё,
        # а любые изменения (добавить, изменить, удалить) — после оплаты
        if (g.sub.get("readonly") and request.method not in ("GET", "HEAD", "OPTIONS")
                and not getattr(view, "_sub_exempt", False) and not getattr(view, "_ro_ok", False)):
            resp = jsonify({"ok": False, "error": g.T["ro_error"], "readonly": True})
            resp.status_code = 402
            resp.headers["X-OilBook-Readonly"] = "1"
            return resp
        return view(*args, **kwargs)
    return wrapped


def readonly_ok(view):
    """Действие, которое не меняет данные точки (язык, отметка урока) —
    работает и в режиме «только просмотр». Ставить сразу ПОД @login_required."""
    view._ro_ok = True
    return view


def sub_exempt(view):
    """Разрешает разделу работать и при неоплаченной подписке (страница
    оплаты, отправка чека). Ставить сразу ПОД @login_required."""
    view._sub_exempt = True
    return view


def employee_blocked(view):
    """Закрывает API-эндпоинт для логина сотрудника (прибыль, цены закупки,
    экспорт, управление складом) — даже если кто-то обратится к нему напрямую,
    в обход интерфейса. Ставить ПОСЛЕ @login_required."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "is_employee", False):
            return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
        return view(*args, **kwargs)
    return wrapped


def profit_blocked(view):
    """Закрывает прибыль и от сотрудника, и от филиала — прибыль по филиалам
    видит только их главный аккаунт (в сложенном виде, см. агрегированную
    статистику). Остальное (статистика по выручке, экспорт, рассылка, SMS)
    филиалу по-прежнему доступно, поэтому это отдельный декоратор, а не
    расширение employee_blocked."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "is_employee", False) or getattr(g, "is_branch", False):
            return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
        return view(*args, **kwargs)
    return wrapped



def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            return _auth_fail()
        admin = db.get_shop(session.get("shop_id")) if session.get("shop_id") else None
        if not admin or admin.get("role") != "admin" or not _session_password_ok(_pw_fingerprint(admin.get("password_hash"))):
            session.clear()
            return _auth_fail()
        return view(*args, **kwargs)
    return wrapped


def _client_link(token):
    if not token or not BOT_USERNAME:
        return None
    return f"https://t.me/{BOT_USERNAME}?start={token}"


LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ T.app_title }}</title>
<link rel="manifest" href="/static/manifest.json?v=2">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@700;800&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@700;800&display=swap"></noscript>
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="OilBook">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
</script>
<style>
  * { box-sizing: border-box; }
  body {
    margin:0; background:#0f1115; color:#f2f2f2; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    height:100vh; display:flex; align-items:center; justify-content:center;
  }
  .box { background:#1a1d24; border:1px solid #2a2e37; border-radius:14px; padding:28px; width:90%; max-width:340px; }
  h1 { font-size:20px; margin:0 0 20px; text-align:center; }
  body { flex-direction:column; min-height:100vh; height:auto; padding:28px 16px; box-sizing:border-box; }
  .login-brand { display:flex; flex-direction:column; align-items:center; gap:10px; margin:0 0 22px; }
  .login-brand .drop { width:58px; height:58px; border-radius:18px; background:#0B1B3A; display:flex; align-items:center; justify-content:center; box-shadow:0 10px 30px rgba(14,165,233,.25); transform:rotate(-8deg); }
  .login-brand .drop svg { transform:rotate(8deg); }
  .login-brand .wordmark { font-family:'Sora', -apple-system, sans-serif; font-weight:800; font-size:38px; letter-spacing:-1px; line-height:1; }
  .login-brand .wm-oil { background:linear-gradient(135deg, #38BDF8 0%, #3B82F6 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .login-brand .wm-book { color:#fff; }
  .login-brand .tagline { font-size:12.5px; color:#8b93a3; letter-spacing:.3px; }
  label { display:block; font-size:13px; color:#9a9a9a; margin-bottom:4px; }
  input { width:100%; padding:11px; border-radius:8px; border:1px solid #2a2e37; background:#11141a; color:#fff; font-size:15px; margin-bottom:14px; }
  button { width:100%; padding:12px; border:none; border-radius:10px; background:#3a86ff; color:#fff; font-size:16px; font-weight:600; cursor:pointer; }
  .error { background:#3a1e1e; color:#dc6f6f; padding:10px; border-radius:8px; margin-bottom:14px; font-size:14px; }
  .ok-msg { background:#1e3a24; color:#6fdc86; padding:10px; border-radius:8px; margin-bottom:14px; font-size:14px; }
  .lang-link { display:block; text-align:center; margin-top:14px; color:#9a9a9a; font-size:12px; text-decoration:none; }
  .forgot-link { display:block; text-align:center; margin-top:12px; color:#3a86ff; font-size:13px; background:none; border:none; cursor:pointer; padding:0; }
  .hint { font-size:12px; color:#7a7a7a; margin:-8px 0 14px; }
  .reg-link { display:block; text-align:center; margin-top:16px; padding:11px; border:1px solid #2a2e37; border-radius:10px; color:#e6e6e6; font-size:14px; text-decoration:none; }
  .app-link { display:block; text-align:center; margin-top:16px; padding:10px 18px; border-radius:22px; background:rgba(56,189,248,.10); border:1px solid rgba(56,189,248,.30); color:#7DD3FC; font-size:14px; font-weight:600; text-decoration:none; }
  @media (display-mode: standalone) { .app-link { display:none; } }
  .video-link { display:flex; align-items:center; justify-content:center; gap:10px; margin-top:10px; padding:10px 18px; border-radius:22px; background:rgba(255,0,51,.10); border:1px solid rgba(255,0,51,.35); color:#FF8A9B; font-size:14px; font-weight:600; text-decoration:none; }
  .video-link i { font-style:normal; width:22px; height:16px; border-radius:5px; background:#FF0033; color:#fff; font-size:9px; display:flex; align-items:center; justify-content:center; }
  .video-link:hover { background:rgba(255,0,51,.16); }
</style>
</head>
<body>
  <div class="login-brand">
    <div class="drop"><svg width="26" height="30" viewBox="0 0 26 30" aria-hidden="true"><path d="M13 1C13 1 2 13.5 2 19.5A11 11 0 0 0 24 19.5C24 13.5 13 1 13 1Z" fill="#0EA5E9"/><ellipse cx="8.5" cy="19" rx="2.2" ry="3.6" fill="#BAE6FD" opacity=".85"/></svg></div>
    <div class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></div>
    <div class="tagline">{{ T.app_tagline }}</div>
  </div>
  <form class="box" method="POST" id="loginForm">
    <h1>{{ T.login_title }}</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <input type="hidden" name="_lang" value="{{ lang }}">
    <label>{{ T.login_username }}</label>
    <input name="username" autofocus required>
    <label>{{ T.login_password }}</label>
    <input name="password" type="password" required>
    <button type="submit">{{ T.login_button }}</button>
    <button type="button" class="forgot-link" onclick="showForgot()">{{ T.forgot_password_link }}</button>
    <a class="reg-link" href="/register?lang={{ lang }}">{{ T.reg_link_login }}</a>
    <a class="lang-link" href="/login?lang={{ other_lang }}">{{ T.lang_switch }}</a>
  </form>
  <a class="app-link" href="/app?lang={{ lang }}">{{ T.inst_login_link }}</a>
  <a class="video-link" href="https://youtu.be/4p436_6TxIM" target="_blank" rel="noopener"><i>▶</i>{{ T.login_video_link }}</a>

  <div class="box" id="forgotBox" style="display:none;">
    <h1>🔑 {{ T.forgot_title }}</h1>
    <div id="forgotMsg"></div>
    <div id="forgotStep1">
      <label>{{ T.login_username }}</label>
      <input id="forgot_username" autofocus>
      <p class="hint">{{ T.forgot_hint }}</p>
      <button type="button" onclick="requestResetCode()">{{ T.forgot_send_code }}</button>
    </div>
    <div id="forgotStep2" style="display:none;">
      <label>{{ T.forgot_code_label }}</label>
      <input id="forgot_code" inputmode="numeric" maxlength="6">
      <label>{{ T.forgot_new_password }}</label>
      <input id="forgot_new_password" type="password">
      <button type="button" onclick="confirmResetCode()">{{ T.forgot_save_btn }}</button>
    </div>
    <button type="button" class="forgot-link" onclick="hideForgot()">{{ T.forgot_back }}</button>
  </div>

  <script>
    function showForgot() {
      document.getElementById('loginForm').style.display = 'none';
      document.getElementById('forgotBox').style.display = 'block';
    }
    function hideForgot() {
      document.getElementById('forgotBox').style.display = 'none';
      document.getElementById('loginForm').style.display = 'block';
      document.getElementById('forgotStep1').style.display = 'block';
      document.getElementById('forgotStep2').style.display = 'none';
      document.getElementById('forgotMsg').innerHTML = '';
    }
    async function requestResetCode() {
      const username = document.getElementById('forgot_username').value.trim();
      const msg = document.getElementById('forgotMsg');
      if (!username) return;
      const res = await fetch('/api/forgot_password/request', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username})
      });
      const data = await res.json();
      if (data.ok) {
        msg.innerHTML = `<div class="ok-msg">{{ T.forgot_code_sent }}</div>`;
        document.getElementById('forgotStep1').style.display = 'none';
        document.getElementById('forgotStep2').style.display = 'block';
      } else {
        msg.innerHTML = `<div class="error">${data.error}</div>`;
      }
    }
    async function confirmResetCode() {
      const username = document.getElementById('forgot_username').value.trim();
      const code = document.getElementById('forgot_code').value.trim();
      const new_password = document.getElementById('forgot_new_password').value;
      const msg = document.getElementById('forgotMsg');
      const res = await fetch('/api/forgot_password/confirm', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, code, new_password})
      });
      const data = await res.json();
      if (data.ok) {
        msg.innerHTML = `<div class="ok-msg">{{ T.forgot_success }}</div>`;
        setTimeout(() => { window.location.href = '/login'; }, 1800);
      } else {
        msg.innerHTML = `<div class="error">${data.error}</div>`;
      }
    }
  </script>
</body>
</html>
"""


# Города и страница самостоятельной регистрации — в registration.py.


PASSPORT_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Сервисный паспорт — {{ car.plate_number }}</title>
<style>
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#F1F4F9; color:#1A1D24; }
  .wrap { max-width:640px; margin:0 auto; padding:20px 16px 40px; }
  .stripe { height:6px; background:linear-gradient(90deg, #1D4ED8 33%, #E10600 33%, #E10600 66%, #38BDF8 66%); }
  .head { text-align:center; padding:24px 0 18px; }
  .head .badge { display:inline-block; background:#1D4ED8; color:#fff; font-size:11px; font-weight:700; letter-spacing:1px; text-transform:uppercase; padding:4px 12px; border-radius:20px; margin-bottom:10px; }
  .head h1 { font-size:26px; margin:6px 0 2px; font-family:'Courier New',monospace; letter-spacing:1px; }
  .head .sub { color:#6B7280; font-size:14px; }
  .card { background:#fff; border:1px solid #E5E9F0; border-radius:16px; padding:18px; margin-bottom:14px; }
  .card .label { font-size:11px; color:#8A93A6; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }
  .card .value { font-size:16px; font-weight:600; }
  .owner-row { display:flex; justify-content:space-between; gap:12px; }
  .owner-row > div { flex:1; }
  .hist-title { font-size:15px; font-weight:700; margin:22px 0 10px; }
  .entry { background:#fff; border:1px solid #E5E9F0; border-radius:14px; padding:14px; margin-bottom:10px; }
  .entry .top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  .entry .date { font-weight:700; font-size:14.5px; }
  .entry .mileage { color:#6B7280; font-size:12.5px; margin-top:2px; }
  .entry .cost { font-weight:700; color:#1D4ED8; font-family:'Courier New',monospace; white-space:nowrap; }
  .entry .items { margin-top:8px; padding-top:8px; border-top:1px dashed #E5E9F0; font-size:13px; color:#4B5563; }
  .entry .items div { display:flex; justify-content:space-between; padding:2px 0; }
  .empty { text-align:center; color:#8A93A6; padding:30px 0; }
  .footer { text-align:center; color:#9AA3B2; font-size:12px; margin-top:26px; line-height:1.6; }
  .footer b { color:#4B5563; }
</style>
</head>
<body>
  <div class="stripe"></div>
  <div class="wrap">
    <div class="head">
      <span class="badge">✓ Сервисный паспорт</span>
      <h1>{{ car.plate_number }}</h1>
      <div class="sub">{{ car.car_brand or '' }} {{ car.car_model or '' }}</div>
    </div>

    <div class="card">
      <div class="owner-row">
        <div>
          <div class="label">Владелец</div>
          <div class="value">{{ car.owner_name or '—' }}</div>
        </div>
        <div>
          <div class="label">Обслуживается в</div>
          <div class="value">{{ car.shop_name or '—' }}</div>
        </div>
      </div>
    </div>

    <div class="hist-title">История обслуживания ({{ history|length }})</div>
    {% if history %}
      {% for h in history %}
      <div class="entry">
        <div class="top">
          <div>
            <div class="date">{{ h.service_type or 'Замена масла' }}</div>
            <div class="mileage">{{ h.change_date }}{% if h.mileage %} · {{ "{:,}".format(h.mileage).replace(',', ' ') }} км{% endif %}</div>
          </div>
          {% if h.cost %}<div class="cost">{{ "{:,}".format(h.cost).replace(',', ' ') }} сум</div>{% endif %}
        </div>
        {% if h.items_list %}
        <div class="items">
          {% for it in h.items_list %}
          <div><span>{{ it.name }}{% if it.brand %} ({{ it.brand }}){% endif %}{% if it.qty and it.qty != 1 %} — {{ it.qty }} л{% endif %}</span><span>{{ "{:,}".format(it.total|int).replace(',', ' ') }}</span></div>
          {% endfor %}
          {% if h.discount_amount %}<div style="color:#B3241C;"><span>Скидка</span><span>−{{ "{:,}".format(h.discount_amount|int).replace(',', ' ') }}</span></div>{% endif %}
        </div>
        {% endif %}
      </div>
      {% endfor %}
    {% else %}
      <div class="empty">Записей пока нет.</div>
    {% endif %}

    <div class="footer">
      Подтверждённая история обслуживания.<br>
      Данные предоставлены точкой <b>{{ car.shop_name or '' }}</b> через платформу учёта замены масла.
    </div>
  </div>
</body>
</html>
"""


@app.route("/passport/<token>")
def public_passport(token):
    """Публичная страница сервисного паспорта машины — без входа в систему.
    Можно показать покупателю при продаже авто как подтверждение истории
    обслуживания."""
    car, history = db.get_car_by_passport_token(token)
    if not car:
        return "Паспорт не найден", 404
    for h in history:
        h["items_list"] = None
        if h.get("items_json"):
            try:
                h["items_list"] = json.loads(h["items_json"])
            except (TypeError, ValueError):
                pass
    return render_template_string(PASSPORT_PAGE, car=car, history=history)


def _register_pdf_fonts():
    """Регистрирует шрифт с поддержкой кириллицы для reportlab — встроен
    прямо в проект (fonts/), чтобы PDF одинаково работал что локально, что
    на любом хостинге, независимо от того, какие шрифты есть на сервере."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "DejaVuSans" in pdfmetrics.getRegisteredFontNames():
        return
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(base_dir, "fonts", "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf")))


def _generate_passport_pdf(car, history, output_path):
    """Строит PDF сервисного паспорта — та же информация, что на публичной
    странице, но в виде файла, который можно скачать и переслать."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle

    _register_pdf_fonts()
    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    styles = {
        "title": ParagraphStyle("title", fontName="DejaVuSans-Bold", fontSize=20, leading=26, spaceAfter=8),
        "sub": ParagraphStyle("sub", fontName="DejaVuSans", fontSize=12, textColor=colors.HexColor("#6B7280"), spaceAfter=14),
        "label": ParagraphStyle("label", fontName="DejaVuSans", fontSize=9, textColor=colors.HexColor("#8A93A6")),
        "value": ParagraphStyle("value", fontName="DejaVuSans-Bold", fontSize=12, spaceAfter=10),
        "hist_title": ParagraphStyle("hist_title", fontName="DejaVuSans-Bold", fontSize=13, spaceBefore=10, spaceAfter=8),
        "cell": ParagraphStyle("cell", fontName="DejaVuSans", fontSize=9, leading=12),
        "cell_bold": ParagraphStyle("cell_bold", fontName="DejaVuSans-Bold", fontSize=9, leading=12),
        "footer": ParagraphStyle("footer", fontName="DejaVuSans", fontSize=8, textColor=colors.HexColor("#9AA3B2"), spaceBefore=16),
    }
    story = [
        Paragraph(f"✓ Сервисный паспорт — {car['plate_number']}", styles["title"]),
        Paragraph(f"{car.get('car_brand') or ''} {car.get('car_model') or ''}".strip() or "—", styles["sub"]),
        Paragraph("ВЛАДЕЛЕЦ", styles["label"]),
        Paragraph(car.get("owner_name") or "—", styles["value"]),
        Paragraph("ОБСЛУЖИВАЕТСЯ В", styles["label"]),
        Paragraph(car.get("shop_name") or "—", styles["value"]),
        Paragraph(f"История обслуживания ({len(history)})", styles["hist_title"]),
    ]
    if history:
        rows = [[Paragraph("Дата", styles["cell_bold"]), Paragraph("Пробег", styles["cell_bold"]),
                 Paragraph("Услуга / состав", styles["cell_bold"]), Paragraph("Стоимость", styles["cell_bold"])]]
        for h in history:
            desc = h.get("service_type") or "Замена масла"
            if h.get("items_json"):
                try:
                    items = json.loads(h["items_json"])
                    desc += "<br/>" + "<br/>".join(
                        f"• {it.get('name', '')}" + (f" ({it['brand']})" if it.get("brand") else "")
                        for it in items
                    )
                    if h.get("discount_amount"):
                        desc += "<br/>• Скидка −" + f"{int(h['discount_amount']):,}".replace(",", " ") + " сум"
                except (TypeError, ValueError):
                    pass
            mileage = f"{h['mileage']:,}".replace(",", " ") + " км" if h.get("mileage") else "—"
            cost = f"{h['cost']:,}".replace(",", " ") + " сум" if h.get("cost") else "—"
            rows.append([
                Paragraph(h["change_date"], styles["cell"]),
                Paragraph(mileage, styles["cell"]),
                Paragraph(desc, styles["cell"]),
                Paragraph(cost, styles["cell"]),
            ])
        table = Table(rows, colWidths=[24 * mm, 24 * mm, 82 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F4F9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E9F0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Записей пока нет.", styles["cell"]))
    story.append(Paragraph(
        f"Подтверждённая история обслуживания. Данные предоставлены точкой «{car.get('shop_name') or ''}» "
        f"через платформу учёта замены масла.", styles["footer"]
    ))
    doc.build(story)


@app.route("/passport/<token>/pdf")
def public_passport_pdf(token):
    """Скачивание сервисного паспорта в виде PDF — та же публичная ссылка,
    без входа в систему."""
    car, history = db.get_car_by_passport_token(token)
    if not car:
        return "Паспорт не найден", 404
    import tempfile
    fd, output_path = tempfile.mkstemp(prefix="passport_", suffix=".pdf")
    os.close(fd)
    # номер может быть на кириллице (А123ВС77), а в filename="..." допустим
    # только ASCII — иначе сервер падал с ошибкой 500. Настоящее имя — в filename*
    filename = f"passport_{car['plate_number']}.pdf"
    try:
        _generate_passport_pdf(car, history, output_path)
        with open(output_path, "rb") as f:
            body = f.read()
        return Response(
            body,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"inline; filename=\"passport.pdf\"; "
                                            f"filename*=UTF-8''{urllib.parse.quote(filename)}"}
        )
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


@app.route("/sw.js")
def service_worker():
    """Service worker обязательно отдаётся с корня (не из /static/), иначе
    его область действия (scope) ограничится только папкой /static/ и он
    не сможет ничего перехватывать на реальных страницах приложения."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sw.js"), encoding="utf-8") as f:
        response = Response(f.read(), mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


# Сканер госномера: файлы распознавания (движок ONNX + модель) лежат в
# static/ocr/. Распознавание идёт на телефоне — сервер только один раз
# отдаёт эти файлы, дальше телефон берёт их из своего кэша. Фото номера
# на сервер не отправляются. Файлы сжимаем gzip один раз и держим в памяти
# (≈ 4,5 МБ вместо 13 МБ трафика на телефон).
_OCR_FILES = {
    "ort.wasm.min.js": "text/javascript",
    "ort-wasm-simd-threaded.mjs": "text/javascript",
    "ort-wasm-simd-threaded.wasm": "application/wasm",
    "plate_ocr_uz.onnx": "application/octet-stream",  # дообучена на номерах UZ / RU / KZ / KG / TJ
    # «искатель»: находит номер в любом месте кадра. Имя с размером входа —
    # файлы кэшируются «навсегда», новая версия модели = новое имя файла
    "plate_det_s256.onnx": "application/octet-stream",
}
_ocr_gz_cache = {}
_ocr_gz_lock = threading.Lock()


@app.route("/ocr/v1/<name>")
def ocr_file(name):
    import gzip
    mime = _OCR_FILES.get(name)
    if not mime:
        return Response(status=404)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "ocr", name)
    if not os.path.exists(path):
        return Response(status=404)
    if "gzip" in (request.headers.get("Accept-Encoding") or ""):
        with _ocr_gz_lock:
            body = _ocr_gz_cache.get(name)
            if body is None:
                with open(path, "rb") as f:
                    body = gzip.compress(f.read(), 6)
                _ocr_gz_cache[name] = body
        resp = Response(body, mimetype=mime)
        resp.headers["Content-Encoding"] = "gzip"
    else:
        with open(path, "rb") as f:
            resp = Response(f.read(), mimetype=mime)
    resp.headers["Vary"] = "Accept-Encoding"
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


# Защита от подбора пароля: не больше 10 неверных попыток за 15 минут для
# одной пары «адрес + логин». Хранится в памяти процесса (после перезапуска
# сервера счётчик обнуляется — это нормально).
_login_fail_lock = threading.Lock()
_login_fails = {}
LOGIN_MAX_FAILS = 10
LOGIN_WINDOW_SEC = 15 * 60


def _client_ip():
    # Render дописывает настоящий адрес клиента В КОНЕЦ X-Forwarded-For;
    # первые значения присылает сам клиент и может подделать (раньше так
    # можно было обойти ограничение на подбор пароля, меняя заголовок)
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[-1].strip() if fwd else request.remote_addr) or "?"


LOGIN_MAX_FAILS_PER_USER = 30  # с любых адресов вместе — на случай перебора с разных IP


def _login_blocked(key) -> bool:
    now = time.time()
    user_key = ("*", key[1])
    with _login_fail_lock:
        fails = [t for t in _login_fails.get(key, []) if now - t < LOGIN_WINDOW_SEC]
        _login_fails[key] = fails
        user_fails = [t for t in _login_fails.get(user_key, []) if now - t < LOGIN_WINDOW_SEC]
        _login_fails[user_key] = user_fails
        return len(fails) >= LOGIN_MAX_FAILS or len(user_fails) >= LOGIN_MAX_FAILS_PER_USER


def _login_failed(key):
    now = time.time()
    with _login_fail_lock:
        if len(_login_fails) > 5000:
            # чистим только устаревшее (раньше очищалось всё — счётчики
            # можно было «сбросить», засыпав сервер попытками)
            for k in [k for k, v in _login_fails.items() if not v or now - v[-1] > LOGIN_WINDOW_SEC]:
                _login_fails.pop(k, None)
        _login_fails.setdefault(key, []).append(now)
        _login_fails.setdefault(("*", key[1]), []).append(now)


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    lang = request.form.get("_lang") or request.args.get("lang")
    if lang not in ("ru", "uz"):
        lang = "ru"
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        fail_key = (_client_ip(), username.lower())
        if _login_blocked(fail_key):
            T = i18n.get_texts(lang)
            return render_template_string(LOGIN_PAGE, error=i18n.t("login_too_many", lang), T=T, lang=lang,
                                          other_lang="uz" if lang == "ru" else "ru"), 429
        shop = db.authenticate_shop(username, password)
        if shop:
            session.clear()
            session["shop_id"] = shop["id"]
            session["role"] = shop["role"]
            session["username"] = shop["username"]
            session["shop_name"] = shop.get("shop_name") or shop["username"]
            session["is_employee"] = False
            session["pwf"] = _pw_fingerprint(shop.get("password_hash"))
            session.permanent = True
            return redirect(url_for("admin_page") if shop["role"] == "admin" else url_for("index"))
        employee = db.authenticate_shop_employee(username, password)
        if employee:
            parent_shop = db.get_shop(employee["shop_id"])
            session.clear()
            session["shop_id"] = employee["shop_id"]
            session["role"] = "shop"
            session["username"] = employee["username"]
            session["shop_name"] = (parent_shop.get("shop_name") or "") if parent_shop else ""
            session["is_employee"] = True
            session["pwf"] = _pw_fingerprint(employee.get("password_hash"))
            session.permanent = True
            return redirect(url_for("index"))
        _login_failed(fail_key)
        error = i18n.t("login_error", lang)
    T = i18n.get_texts(lang)
    return render_template_string(LOGIN_PAGE, error=error, T=T, lang=lang, other_lang="uz" if lang == "ru" else "ru")


# Лимит на отправку кодов восстановления: без него можно было заспамить
# Telegram владельца кодами и каждым новым запросом сжигать его настоящий код.
_reset_req_lock = threading.Lock()
_reset_req_hits = {}
RESET_REQ_WINDOW_SEC = 10 * 60
RESET_REQ_MAX_PER_IP = 10
RESET_REQ_MAX_PER_USER = 3


def _reset_request_limited(ip, username) -> bool:
    now = time.time()
    keys = (("ip", ip, RESET_REQ_MAX_PER_IP), ("user", username.lower(), RESET_REQ_MAX_PER_USER))
    with _reset_req_lock:
        if len(_reset_req_hits) > 5000:
            for k in [k for k, v in _reset_req_hits.items() if not v or now - v[-1] > RESET_REQ_WINDOW_SEC]:
                _reset_req_hits.pop(k, None)
        for kind, value, limit in keys:
            hits = [t for t in _reset_req_hits.get((kind, value), []) if now - t < RESET_REQ_WINDOW_SEC]
            _reset_req_hits[(kind, value)] = hits
            if len(hits) >= limit:
                return True
        for kind, value, _ in keys:
            _reset_req_hits[(kind, value)].append(now)
    return False


@app.route("/api/forgot_password/request", methods=["POST"])
def api_forgot_password_request():
    """Первый шаг восстановления пароля — отправляет 6-значный код в
    привязанный Telegram точки. Несуществующий логин и логин без Telegram
    получают ОДИНАКОВЫЙ ответ — чтобы по ответам нельзя было выяснить,
    какие логины есть на платформе."""
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username") or "").strip()[:64]
    if not username:
        return jsonify({"ok": False, "error": "укажите логин"}), 400
    if _reset_request_limited(_client_ip(), username):
        return jsonify({"ok": False, "error": "слишком много запросов — подождите 10 минут и попробуйте снова"}), 429
    no_code = jsonify({"ok": False, "error": "не удалось отправить код: проверьте логин. Если к точке не привязан "
                                              "Telegram — обратитесь к администратору платформы для сброса пароля"})
    shop = db.find_shop_by_username(username)
    if not shop or not shop.get("notify_telegram_id"):
        return no_code, 400
    code = db.create_password_reset_code(shop["id"])
    lang = shop.get("language") or "ru"
    text = i18n.t("password_reset_code_message", lang, code=code)
    sent = _send_telegram_message(shop["notify_telegram_id"], text)
    if not sent:
        return jsonify({"ok": False, "error": "не удалось отправить код в Telegram, попробуйте позже или обратитесь к администратору"}), 500
    return jsonify({"ok": True})


@app.route("/api/forgot_password/confirm", methods=["POST"])
def api_forgot_password_confirm():
    """Второй шаг — проверяет код и, если верный, задаёт новый пароль."""
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    code = (data.get("code") or "").strip()
    new_password = data.get("new_password") or ""
    if not username or not code or len(new_password) < 6:
        return jsonify({"ok": False, "error": "заполните все поля (пароль — минимум 6 символов)"}), 400
    ok = db.reset_password_with_code(username, code, new_password)
    if not ok:
        return jsonify({"ok": False, "error": "неверный или просроченный код"}), 400
    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------- Страница «Скачать приложение» (/app) ----------
# Открыта без входа: ссылку можно дать любому (сотруднику, новой точке).
# Сама определяет телефон и браузер:
#   Android + Chrome  → кнопка «Установить» (системное окно Chrome);
#   iPhone            → инструкция для Safari («Поделиться» → «На экран Домой»);
#   внутри Telegram   → просьба открыть в Chrome/Safari (оттуда установить нельзя);
#   компьютер         → QR-код, чтобы открыть страницу на телефоне;
#   уже установлено   → кнопка «Открыть OilBook».
APP_PAGE = """
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{{ T.inst_title }}</title>
<meta name="description" content="{{ T.inst_lead }}">
<link rel="manifest" href="/static/manifest.json?v=2">
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="OilBook">
<meta property="og:title" content="{{ T.inst_title }}">
<meta property="og:description" content="{{ T.inst_lead }}">
<meta property="og:image" content="{{ page_origin }}/static/icons/icon-512.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@700;800&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
</script>
<style>
  * { box-sizing:border-box; }
  html, body { margin:0; }
  body { background:#F1F5F9; color:#0F172A; font-family:-apple-system, 'Segoe UI', Roboto, sans-serif; -webkit-font-smoothing:antialiased; }
  .hero { background:linear-gradient(160deg, #0A2540 0%, #0B1B3A 60%, #10305E 100%); color:#fff; padding:calc(22px + env(safe-area-inset-top, 0px)) 16px 64px; text-align:center; position:relative; overflow:hidden; }
  .hero::after { content:''; position:absolute; width:340px; height:340px; border-radius:50%; background:radial-gradient(circle, rgba(56,189,248,.22), rgba(56,189,248,0) 70%); top:-120px; right:-120px; }
  .top { display:flex; justify-content:space-between; align-items:center; max-width:520px; margin:0 auto 22px; position:relative; z-index:1; }
  .wordmark { font-family:'Sora', -apple-system, sans-serif; font-weight:800; font-size:22px; letter-spacing:-.6px; }
  .wm-oil { background:linear-gradient(135deg, #38BDF8 0%, #3B82F6 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .wm-book { color:#fff; }
  .lang { color:#B9CBEA; font-size:13px; text-decoration:none; border:1px solid rgba(255,255,255,.18); padding:6px 12px; border-radius:20px; }
  .app-icon { width:96px; height:96px; border-radius:24px; display:block; margin:0 auto 16px; box-shadow:0 14px 36px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.08); position:relative; z-index:1; }
  .hero h1 { font-family:'Sora', -apple-system, sans-serif; font-size:26px; margin:0 0 8px; letter-spacing:-.5px; position:relative; z-index:1; }
  .hero p { margin:0 auto; max-width:360px; color:#B9CBEA; font-size:15px; line-height:1.45; position:relative; z-index:1; }
  .chips { display:flex; justify-content:center; gap:8px; margin-top:14px; position:relative; z-index:1; flex-wrap:wrap; }
  .chip { font-size:12.5px; color:#E2E8F0; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12); border-radius:20px; padding:5px 11px; display:inline-flex; align-items:center; gap:6px; }
  .chip svg { width:14px; height:14px; }

  .wrap { max-width:520px; margin:-40px auto 0; padding:0 16px calc(28px + env(safe-area-inset-bottom, 0px)); position:relative; z-index:2; }
  .card { background:#fff; border-radius:20px; padding:18px 16px; margin-bottom:12px; box-shadow:0 6px 24px rgba(15,23,42,.08); }
  .card h2 { font-size:17px; margin:0 0 12px; }
  .btn { display:flex; align-items:center; justify-content:center; gap:10px; width:100%; border:none; border-radius:14px; padding:15px 16px; font-size:16px; font-weight:700; cursor:pointer; text-decoration:none; font-family:inherit; }
  .btn svg { width:20px; height:20px; flex:none; }
  .btn-main { background:#E63946; color:#fff; box-shadow:0 8px 20px rgba(230,57,70,.30); }
  .btn-blue { background:#2563EB; color:#fff; }
  .btn-ghost { background:#F1F5F9; color:#0F172A; margin-top:8px; }
  .state { display:none; }
  .state.on { display:block; }
  .note { font-size:14px; color:#475569; line-height:1.5; margin:0 0 12px; }
  .ok { display:flex; gap:12px; align-items:center; }
  .ok .tick { width:40px; height:40px; border-radius:50%; background:#DCFCE7; color:#16A34A; display:flex; align-items:center; justify-content:center; flex:none; }
  .ok .tick svg { width:22px; height:22px; }
  .ok b { font-size:15px; }
  .warn { border-left:4px solid #F59E0B; }

  .tabs { display:flex; background:#F1F5F9; border-radius:12px; padding:4px; margin-bottom:14px; }
  .tab { flex:1; border:none; background:none; padding:9px 6px; border-radius:9px; font-size:14px; font-weight:700; color:#64748B; cursor:pointer; font-family:inherit; display:flex; align-items:center; justify-content:center; gap:6px; }
  .tab svg { width:16px; height:16px; }
  .tab.on { background:#fff; color:#0F172A; box-shadow:0 1px 4px rgba(15,23,42,.10); }
  .steps { list-style:none; margin:0; padding:0; display:none; }
  .steps.on { display:block; }
  .steps li { display:flex; gap:12px; align-items:flex-start; padding:10px 0; border-bottom:1px dashed #E2E8F0; font-size:14.5px; line-height:1.45; }
  .steps li:last-child { border-bottom:none; }
  .num { width:28px; height:28px; border-radius:50%; background:#0A2540; color:#fff; font-weight:800; font-size:14px; display:flex; align-items:center; justify-content:center; flex:none; }
  .steps .pic { margin-left:auto; flex:none; width:40px; height:40px; border-radius:10px; background:#F1F5F9; display:flex; align-items:center; justify-content:center; color:#334155; }
  .steps .pic svg { width:22px; height:22px; }
  .result { display:flex; gap:12px; align-items:center; background:#EFF6FF; border-radius:14px; padding:12px; margin-top:12px; font-size:14px; color:#1E3A8A; line-height:1.4; }
  .result img { width:44px; height:44px; border-radius:11px; flex:none; }

  .qr { display:flex; gap:16px; align-items:center; }
  .qr img { width:132px; height:132px; border-radius:12px; border:1px solid #E2E8F0; padding:6px; background:#fff; flex:none; }
  .qr p { margin:0; font-size:14px; color:#475569; line-height:1.5; }
  .qr .url { display:block; margin-top:8px; font-weight:700; color:#0F172A; word-break:break-all; }

  details { border-bottom:1px solid #F1F5F9; padding:12px 0; }
  details:last-child { border-bottom:none; padding-bottom:0; }
  summary { font-weight:700; font-size:14.5px; cursor:pointer; list-style:none; display:flex; justify-content:space-between; gap:10px; }
  summary::-webkit-details-marker { display:none; }
  summary::after { content:'+'; color:#94A3B8; font-size:18px; line-height:1; }
  details[open] summary::after { content:'−'; }
  details p { margin:8px 0 0; font-size:14px; color:#475569; line-height:1.5; }
  .foot { text-align:center; margin-top:16px; }
  .foot a { color:#2563EB; font-weight:600; font-size:14px; text-decoration:none; }
  .toast { position:fixed; left:50%; bottom:calc(24px + env(safe-area-inset-bottom, 0px)); transform:translateX(-50%) translateY(20px); background:#0F172A; color:#fff; padding:11px 16px; border-radius:12px; font-size:14px; opacity:0; transition:.2s; pointer-events:none; z-index:10; }
  .toast.on { opacity:1; transform:translateX(-50%) translateY(0); }
  @media (min-width: 700px) { .hero { padding-bottom:72px; } .hero h1 { font-size:30px; } }
</style>
</head>
<body>
<div class="hero">
  <div class="top">
    <span class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span>
    <a class="lang" href="/app?lang={{ other_lang }}">{{ T.lang_switch_short }}</a>
  </div>
  <img class="app-icon" src="/static/icons/icon-192.png" alt="OilBook">
  <h1>{{ T.inst_title }}</h1>
  <p>{{ T.inst_lead }}</p>
  <div class="chips">
    <span class="chip"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.6 9.48l1.84-3.18a.38.38 0 0 0-.66-.38l-1.86 3.22A11.4 11.4 0 0 0 12 8.1c-1.77 0-3.43.39-4.92 1.04L5.22 5.92a.38.38 0 0 0-.66.38L6.4 9.48A10.8 10.8 0 0 0 1 18h22a10.8 10.8 0 0 0-5.4-8.52zM7 15.25a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5zm10 0a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5z"/></svg>Android</span>
    <span class="chip"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.37 12.6c-.02-2.3 1.88-3.4 1.96-3.46a4.2 4.2 0 0 0-3.32-1.8c-1.4-.14-2.75.83-3.46.83-.72 0-1.82-.81-3-.79a4.43 4.43 0 0 0-3.74 2.28c-1.6 2.77-.41 6.86 1.14 9.1.76 1.1 1.66 2.33 2.85 2.29 1.14-.05 1.58-.74 2.96-.74 1.38 0 1.77.74 2.98.71 1.23-.02 2-1.11 2.75-2.22a9.6 9.6 0 0 0 1.25-2.57 3.97 3.97 0 0 1-2.37-3.63zM14.1 5.86A3.98 3.98 0 0 0 15.04 3a4.06 4.06 0 0 0-2.63 1.36 3.8 3.8 0 0 0-.96 2.76 3.36 3.36 0 0 0 2.65-1.26z"/></svg>iPhone</span>
    <span class="chip">{{ T.inst_chip_free }}</span>
  </div>
</div>

<div class="wrap">
  <!-- уже установлено -->
  <div class="card state" id="stInstalled">
    <div class="ok"><span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span><b>{{ T.inst_installed }}</b></div>
    <a class="btn btn-blue" href="/" style="margin-top:14px;">{{ T.inst_open }}</a>
  </div>

  <!-- Android Chrome: системная кнопка установки -->
  <div class="card state" id="stPrompt">
    <button class="btn btn-main" id="installBtn" type="button">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M6.5 10L12 15.5 17.5 10M4 20h16"/></svg>
      <span>{{ T.inst_btn }}</span>
    </button>
  </div>

  <!-- только что установили -->
  <div class="card state" id="stDone">
    <div class="ok"><span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span><b>{{ T.inst_done }}</b></div>
  </div>

  <!-- открыто внутри Telegram и т.п. -->
  <div class="card warn state" id="stInApp">
    <h2>{{ T.inst_inapp_title }}</h2>
    <p class="note" id="inAppText"></p>
    <a class="btn btn-blue" id="openChromeBtn" href="#">{{ T.inst_open_chrome }}</a>
    <button class="btn btn-ghost" type="button" onclick="copyLink()">{{ T.inst_copy }}</button>
  </div>

  <!-- компьютер: QR-код -->
  <div class="card state" id="stDesktop">
    <h2>{{ T.inst_qr_title }}</h2>
    <div class="qr">
      <img src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&margin=0&data={{ page_url|urlencode }}" alt="QR">
      <p>{{ T.inst_qr_text }}<span class="url">{{ page_url_short }}</span></p>
    </div>
  </div>

  <div class="card" id="howCard">
    <h2>{{ T.inst_how }}</h2>
    <div class="tabs">
      <button class="tab" type="button" data-os="android" onclick="pickOs('android')"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.6 9.48l1.84-3.18a.38.38 0 0 0-.66-.38l-1.86 3.22A11.4 11.4 0 0 0 12 8.1c-1.77 0-3.43.39-4.92 1.04L5.22 5.92a.38.38 0 0 0-.66.38L6.4 9.48A10.8 10.8 0 0 0 1 18h22a10.8 10.8 0 0 0-5.4-8.52zM7 15.25a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5zm10 0a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5z"/></svg>Android</button>
      <button class="tab" type="button" data-os="ios" onclick="pickOs('ios')"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.37 12.6c-.02-2.3 1.88-3.4 1.96-3.46a4.2 4.2 0 0 0-3.32-1.8c-1.4-.14-2.75.83-3.46.83-.72 0-1.82-.81-3-.79a4.43 4.43 0 0 0-3.74 2.28c-1.6 2.77-.41 6.86 1.14 9.1.76 1.1 1.66 2.33 2.85 2.29 1.14-.05 1.58-.74 2.96-.74 1.38 0 1.77.74 2.98.71 1.23-.02 2-1.11 2.75-2.22a9.6 9.6 0 0 0 1.25-2.57 3.97 3.97 0 0 1-2.37-3.63zM14.1 5.86A3.98 3.98 0 0 0 15.04 3a4.06 4.06 0 0 0-2.63 1.36 3.8 3.8 0 0 0-.96 2.76 3.36 3.36 0 0 0 2.65-1.26z"/></svg>iPhone</button>
    </div>
    <ol class="steps" id="steps-android">
      <li><span class="num">1</span><span>{{ T.inst_a1|safe }}</span><span class="pic"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#EA4335"/><path d="M12 2a10 10 0 0 1 8.66 5H12a5 5 0 0 0-4.33 2.5L3.34 7A10 10 0 0 1 12 2z" fill="#EA4335"/><path d="M20.66 7A10 10 0 0 1 12 22l4.33-7.5A5 5 0 0 0 17 12a5 5 0 0 0-.67-2.5z" fill="#FBBC05"/><path d="M12 22A10 10 0 0 1 3.34 7l4.33 7.5A5 5 0 0 0 12 17a5 5 0 0 0 4.33-2.5z" fill="#34A853"/><circle cx="12" cy="12" r="4" fill="#4285F4" stroke="#fff" stroke-width="1.6"/></svg></span></li>
      <li><span class="num">2</span><span>{{ T.inst_a2|safe }}</span><span class="pic"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="2.2"/><circle cx="12" cy="12" r="2.2"/><circle cx="12" cy="19" r="2.2"/></svg></span></li>
      <li><span class="num">3</span><span>{{ T.inst_a3|safe }}</span><span class="pic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2.5" width="12" height="19" rx="2.5"/><path d="M12 7.5v7M9 11.5l3 3 3-3"/></svg></span></li>
    </ol>
    <ol class="steps" id="steps-ios">
      <li><span class="num">1</span><span>{{ T.inst_i1|safe }}</span><span class="pic"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#1E90FF"/><circle cx="12" cy="12" r="8.4" fill="none" stroke="#fff" stroke-width=".8" stroke-dasharray="1 2"/><path d="M15.8 8.2l-5.2 2.4-2.4 5.2 5.2-2.4z" fill="#fff"/><path d="M15.8 8.2l-2.4 5.2-2.8-2.8z" fill="#FF3B30"/></svg></span></li>
      <li><span class="num">2</span><span>{{ T.inst_i2|safe }}</span><span class="pic"><svg viewBox="0 0 24 24" fill="none" stroke="#1E90FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9H6.5A1.5 1.5 0 0 0 5 10.5v9A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 17.5 9H16"/><path d="M12 14V2.5M8.5 6L12 2.5 15.5 6"/></svg></span></li>
      <li><span class="num">3</span><span>{{ T.inst_i3|safe }}</span><span class="pic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M12 8v8M8 12h8"/></svg></span></li>
    </ol>
    <div class="result"><img src="/static/icons/icon-192.png" alt=""><span>{{ T.inst_result }}</span></div>
  </div>

  <div class="card">
    <button class="btn btn-ghost" type="button" style="margin-top:0;" onclick="shareLink()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 3.5L10.5 14.5M21.5 3.5l-7 18-4-7-7-4z"/></svg>
      <span>{{ T.inst_share }}</span>
    </button>
  </div>

  <div class="card">
    <details><summary>{{ T.inst_faq1_q }}</summary><p>{{ T.inst_faq1_a }}</p></details>
    <details><summary>{{ T.inst_faq2_q }}</summary><p>{{ T.inst_faq2_a }}</p></details>
  </div>

  <div class="foot"><a href="/login?lang={{ lang }}">{{ T.inst_login }} →</a></div>
</div>
<div class="toast" id="toast"></div>

<script>
  const L = {{ js_texts|tojson }};
  const PAGE_URL = {{ page_url|tojson }};
  const ua = navigator.userAgent || '';
  const isIOS = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroid = ua.indexOf('Android') !== -1;
  const isMobile = isIOS || isAndroid;
  const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  // встроенные браузеры (Telegram, Instagram, Facebook, WebView) — из них установить нельзя
  const inApp = ['Telegram', 'FBAN', 'FBAV', 'Instagram', '; wv)'].some(s => ua.indexOf(s) !== -1);
  // на iPhone ставится только из Safari
  const iosOther = isIOS && ['CriOS', 'FxiOS', 'EdgiOS', 'OPiOS', 'YaBrowser', 'GSA'].some(s => ua.indexOf(s) !== -1);

  function show(id) {
    ['stInstalled', 'stPrompt', 'stDone', 'stInApp', 'stDesktop'].forEach(x => document.getElementById(x).classList.toggle('on', x === id));
  }
  function pickOs(os) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.os === os));
    document.getElementById('steps-android').classList.toggle('on', os === 'android');
    document.getElementById('steps-ios').classList.toggle('on', os === 'ios');
  }
  function toast(text) {
    const el = document.getElementById('toast');
    el.textContent = text;
    el.classList.add('on');
    setTimeout(() => el.classList.remove('on'), 2200);
  }
  async function copyLink() {
    try { await navigator.clipboard.writeText(PAGE_URL); toast(L.copied); }
    catch (e) { window.prompt(L.copy, PAGE_URL); }
  }
  async function shareLink() {
    if (navigator.share) {
      try { await navigator.share({ title: L.title, text: L.share_text, url: PAGE_URL }); return; }
      catch (e) { if (e && e.name === 'AbortError') return; }
    }
    copyLink();
  }

  pickOs(isIOS ? 'ios' : 'android');

  if (standalone) {
    show('stInstalled');
  } else if (inApp || iosOther) {
    document.getElementById('inAppText').textContent = isIOS ? L.inapp_ios : L.inapp_android;
    const chrome = document.getElementById('openChromeBtn');
    if (isAndroid) {
      const u = new URL(PAGE_URL);
      chrome.href = 'intent://' + u.host + u.pathname + u.search + '#Intent;scheme=https;package=com.android.chrome;end';
    } else {
      chrome.style.display = 'none';
    }
    show('stInApp');
  } else if (!isMobile) {
    show('stDesktop');
  }

  // Android Chrome сам предлагает установку — показываем большую кнопку
  let deferred = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferred = e;
    if (!standalone && !inApp) show('stPrompt');
  });
  document.getElementById('installBtn').addEventListener('click', async () => {
    if (!deferred) return;
    deferred.prompt();
    try {
      const choice = await deferred.userChoice;
      if (choice && choice.outcome === 'accepted') show('stDone');
    } catch (e) {}
    deferred = null;
  });
  window.addEventListener('appinstalled', () => show('stDone'));
</script>
</body>
</html>
"""


# Политика конфиденциальности: публичная страница (нужна по закону о
# персональных данных и для подключения Google Диска к резервным копиям).
PRIVACY_TEXT = {
    "ru": ("Политика конфиденциальности OilBook", [
        ("Кто мы", "OilBook — сервис учёта для пунктов замены масла: клиенты, автомобили, замены, склад, напоминания."),
        ("Какие данные храним", "Данные точки (название, адрес, телефон, логин), данные клиентов точки, которые вносит сама точка (гос. номер, телефон, имя, пробег, история обслуживания), и Telegram ID клиентов, подписавшихся на напоминания."),
        ("Зачем", "Только для работы сервиса: учёт обслуживания, статистика точки и напоминания клиентам о следующей замене. Мы не продаём и не передаём данные третьим лицам для рекламы."),
        ("Кто видит данные", "Каждая точка видит только свои данные. Доступ администратора сервиса используется только для поддержки и восстановления."),
        ("Резервные копии", "Ежедневные копии базы шифруются паролем (AES-256) и хранятся в Telegram и Google Диске владельца сервиса не дольше 30 дней. Приложение имеет доступ только к созданным им файлам на Диске."),
        ("Ваши права", "Точка может изменить или удалить данные клиента в панели. Клиент может отписаться от напоминаний в боте или попросить точку удалить его данные."),
        ("Контакты", "Вопросы о данных: напишите в Telegram-бот OilBook или администратору сервиса."),
    ]),
    "uz": ("OilBook maxfiylik siyosati", [
        ("Biz kimmiz", "OilBook — moy almashtirish shoxobchalari uchun hisob xizmati: mijozlar, avtomobillar, almashtirishlar, ombor, eslatmalar."),
        ("Qanday ma'lumotlar saqlanadi", "Shoxobcha ma'lumotlari (nomi, manzili, telefoni, logini), shoxobcha o'zi kiritgan mijozlar ma'lumotlari (davlat raqami, telefon, ism, probeg, xizmat tarixi) va eslatmalarga obuna bo'lgan mijozlarning Telegram ID raqami."),
        ("Nima uchun", "Faqat xizmat ishlashi uchun: xizmat hisobi, shoxobcha statistikasi va mijozlarga keyingi almashtirish haqida eslatma. Ma'lumotlar reklama uchun sotilmaydi va uchinchi shaxslarga berilmaydi."),
        ("Ma'lumotlarni kim ko'radi", "Har bir shoxobcha faqat o'z ma'lumotlarini ko'radi. Xizmat administratori kirishidan faqat yordam va tiklash uchun foydalaniladi."),
        ("Zaxira nusxalar", "Bazaning kunlik nusxalari parol bilan shifrlanadi (AES-256) va xizmat egasining Telegram va Google Diskida 30 kundan ko'p saqlanmaydi. Ilova Diskda faqat o'zi yaratgan fayllarga kira oladi."),
        ("Sizning huquqlaringiz", "Shoxobcha panelda mijoz ma'lumotlarini o'zgartirishi yoki o'chirishi mumkin. Mijoz botda eslatmalardan voz kechishi yoki shoxobchadan ma'lumotlarini o'chirishni so'rashi mumkin."),
        ("Aloqa", "Ma'lumotlar bo'yicha savollar: OilBook Telegram-botiga yoki xizmat administratoriga yozing."),
    ]),
}

PRIVACY_PAGE = """<!doctype html>
<html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
body{margin:0;background:#f5f6f8;color:#1d2330;font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 48px}
h1{font-size:26px;line-height:1.25;margin:0 0 8px}
h2{font-size:18px;margin:24px 0 4px}
p{margin:0}
.lang{margin-bottom:20px;font-size:14px}.lang a{color:#2563eb}
</style></head><body><main>
<div class="lang"><a href="?lang=ru">Русский</a> · <a href="?lang=uz">O'zbekcha</a></div>
<h1>{{ title }}</h1>
{% for h, p in sections %}<h2>{{ h }}</h2><p>{{ p }}</p>{% endfor %}
</main></body></html>"""


@app.route("/privacy")
def privacy_page():
    lang = request.args.get("lang")
    if lang not in ("ru", "uz"):
        lang = "ru"
    title, sections = PRIVACY_TEXT[lang]
    return render_template_string(PRIVACY_PAGE, lang=lang, title=title, sections=sections)


@app.route("/app")
@app.route("/install")
def app_install_page():
    """Публичная страница установки приложения (без входа)."""
    lang = request.args.get("lang")
    if lang not in ("ru", "uz"):
        al = (request.headers.get("Accept-Language") or "").lower()
        lang = "uz" if al.startswith("uz") else "ru"
    T = i18n.get_texts(lang)
    origin = (PUBLIC_URL or request.host_url).rstrip("/")
    page_url = f"{origin}/app" + ("?lang=uz" if lang == "uz" else "")
    js_texts = {
        "title": T["inst_title"], "copied": T["inst_copied"], "copy": T["inst_copy"],
        "inapp_ios": T["inst_inapp_ios"], "inapp_android": T["inst_inapp_android"],
        "share_text": T["inst_share_text"],
    }
    return render_template_string(
        APP_PAGE, T=T, lang=lang, other_lang="uz" if lang == "ru" else "ru",
        page_url=page_url, page_url_short=page_url.split("://", 1)[-1],
        page_origin=origin, js_texts=js_texts,
    )


# ---------- Справка (раздел «Справка» / «Yordam») ----------
# Общие куски для панели точки и для /admin/help. Статьи — в help_content.py.
from panel_template import HELP_CSS  # noqa: E402  (сам текст — в panel_template.py)

from panel_template import HELP_VIEW  # noqa: E402  (сам текст — в panel_template.py)

from panel_template import HELP_JS  # noqa: E402  (сам текст — в panel_template.py)

from panel_template import PAGE  # noqa: E402  (сам текст — в panel_template.py)

from panel_template import MODAL_AND_SCRIPT  # noqa: E402  (сам текст — в panel_template.py)

from panel_template import NET_GUARD_JS  # noqa: E402  (сам текст — в panel_template.py)

_SW_SNIPPET = "<script>\nif ('serviceWorker' in navigator) {"



# Сканер госномера камерой телефона (распознавание прямо в браузере)
from panel_template import PLATE_DECODE_JS  # noqa: E402  (сам текст — в panel_template.py)


from panel_template import PLATE_SCAN_HTML  # noqa: E402  (сам текст — в panel_template.py)

PAGE = PAGE + MODAL_AND_SCRIPT
PAGE = PAGE.replace("</body>", HELP_JS + "</body>", 1)
from panel_template import VIN_SCAN_HTML  # noqa: E402  (сам текст — в panel_template.py)

_ps_i = PAGE.rfind("</body>")
PLATE_SCAN_HTML = PLATE_SCAN_HTML.replace("/*__PLATE_DECODE_JS__*/", PLATE_DECODE_JS)
PAGE = PAGE[:_ps_i] + PLATE_SCAN_HTML + VIN_SCAN_HTML + PAGE[_ps_i:]
assert PAGE.count(_SW_SNIPPET) == 1
PAGE = PAGE.replace(_SW_SNIPPET, NET_GUARD_JS + _SW_SNIPPET, 1)


@app.route("/")
@login_required
def index():
    import json as _json
    shop = db.get_shop(g.shop_id)
    _has_staff = (not g.is_employee) and bool(db.list_shop_employees(g.shop_id))
    return render_template_string(
        PAGE, brands=CAR_BRANDS, car_models=CAR_MODELS, service_types=SERVICE_TYPES,
        shop_name=session.get("shop_name") or "Замена масла",
        T=g.T, lang=g.lang, t_json=_json.dumps(g.T, ensure_ascii=False), bot_username=BOT_USERNAME,
        sms_enabled=bool(shop.get("sms_enabled")) if shop else False,
        eskiz_email=(shop.get("eskiz_email") or "") if shop else "",
        warehouse_enabled=bool(shop.get("warehouse_enabled")) if shop else False,
        store_enabled=_store_on(shop),
        is_employee=g.is_employee,
        has_staff=_has_staff,
        team_on=g.is_employee or _has_staff or ((not g.is_branch) and bool(db.get_branches(g.shop_id))),
        my_employee_id=g.employee_id or 0,
        is_branch=g.is_branch,
        usd_rate=_effective_usd_rate(shop),
        usd_rate_own=shop.get("usd_rate") if shop else None,
        usd_rate_head=_head_usd_rate(shop),
        draft_owner=f"{g.shop_id}_{session.get('username') or ''}",
        sub_banner=_sub_banner(shop),
        sub_ro=_sub_ro_ctx(),
        is_sub_owner=_is_sub_owner(),
        **_help_context(shop),
    )


def _support_contact():
    """Контакт поддержки из настроек подписки: текст и ссылка (Telegram / телефон)."""
    try:
        c = (db.get_platform_settings().get("support_contact") or "").strip()
    except Exception:
        return "", ""
    if not c:
        return "", ""
    if c.startswith("@") and len(c) > 1:
        return c, "https://t.me/" + c[1:]
    if c.startswith("https://") or c.startswith("http://"):
        return c, c
    digits = re.sub(r"[^0-9+]", "", c)
    return c, ("tel:" + digits if len(digits) >= 7 else "")


def _help_context(shop) -> dict:
    """Справка под роль: главная (есть филиалы), самостоятельная, филиал, сотрудник."""
    has_branches = False
    if not g.is_employee and not g.is_branch:
        try:
            has_branches = bool(db.get_branches(g.shop_id))
        except Exception:
            has_branches = False
    role = help_content.detect_role(g.is_employee, g.is_branch, has_branches)
    support, support_url = _support_contact()
    return dict(
        help_sections=help_content.build(
            g.lang, role,
            warehouse=bool(shop.get("warehouse_enabled")) if shop else False,
            sms=bool(shop.get("sms_enabled")) if shop else False),
        help_role=help_content.role_name(g.lang, role),
        help_support=support, help_support_url=support_url,
    )


# ---------- Обучение: курс для пунктов замены масла ----------
# Уроки — готовые страницы в папке course/ (только для вошедших в панель).
# Сотрудник (мастер) видит модули 1–7, владелец точки и филиал — все 12.
COURSE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "course")
COURSE_MODULES = [
    (1, "Moy almashtirish shoxobchasi qanday daromad qiladi", 40),
    (2, "Moy: qovushqoqlik, standartlar, tanlash", 50),
    (3, "Filtrlar va texnik suyuqliklar", 45),
    (4, "Mashinaga moy va filtr tanlash", 45),
    (5, "Moy almashtirish texnologiyasi", 45),
    (6, "Mijozni kutib olish va kuzatib qo\u02bbyish", 40),
    (7, "Majburlamasdan qo\u02bbshimcha sotish", 40),
    (8, "Mijozlar bazasi va qayta tashriflar", 45),
    (9, "Ombor va xaridlar", 45),
    (10, "Shoxobcha pullari", 50),
    (11, "Jamoa: ustalarni yollash va rivojlantirish", 45),
    (12, "Shoxobchani reklama qilish", 45),
]
COURSE_EMPLOYEE_MAX = 7
# Бонус-урок (доступен всем, вне основной карты): электромобили и гибриды.
COURSE_BONUS = (13, "Elektromobil reduktorlari uchun moylar", 195)
COURSE_BONUS_FILE = "bonus-ev.html"


def _course_max() -> int:
    return COURSE_EMPLOYEE_MAX if g.is_employee else len(COURSE_MODULES)


COURSE_FREE_MODULES = 1  # сколько первых модулей открыты всем (для пробы)


def _course_locked() -> bool:
    """Курс (кроме первых модулей) закрыт: новая точка ещё не получила его в
    подарок с годовой подпиской или «Безлимитом». Считается раз на запрос."""
    if not hasattr(g, "_course_locked"):
        try:
            g._course_locked = bool(db.course_access(g.shop_id)["locked"])
        except Exception:
            g._course_locked = False
    return g._course_locked


def _course_allowed(n: int) -> bool:
    if _course_locked():
        return 1 <= n <= min(COURSE_FREE_MODULES, _course_max())
    return 1 <= n <= _course_max() or n == COURSE_BONUS[0]


# Дизайн «Dala» (DESIGN.md): уроки написаны в старой сине-голубой палитре.
# Перекрашиваем их на лету (жёсткие цвета в CSS/SVG) и снижаем жирность
# шрифта; остальное делает общий static/course/dala.css.
_DALA_COLORS = {
    "#1463E6": "#8052FF", "#1F8BEA": "#8052FF", "#1FB5F2": "#A98BFF", "#0A2A5E": "#34343E",
    "#15A35B": "#2FBF9F", "#F2A20C": "#FFB829", "#E5484D": "#FF6B6B", "#9DB4D6": "#55555F",
    "#0A2350": "#FFFFFF", "#6B7F9E": "#9A9A9A", "#3E5479": "#BDBDBD", "#E8F0FC": "#FFFFFF",
    "#B9C9E2": "#BDBDBD", "#8CA0C0": "#9A9A9A", "#22396A": "#2A2A32", "#16305F": "#18181E",
    "#11234A": "#0C0C10", "#0A1730": "#000000", "#E3EEFD": "#18181E", "#D9E4F2": "#2A2A32",
    "#EEF4FB": "#000000",
}
_DALA_COLOR_RE = re.compile("|".join(_DALA_COLORS), re.I)
_DALA_WEIGHT = {"900": "400", "800": "500", "700": "500"}
_DALA_WEIGHT_RE = re.compile(r"font-weight:\s*(900|800|700)")
_DALA_HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600&display=swap">'
              '<link rel="stylesheet" href="/static/course/dala.css?v=2">')
_DALA_SCRIPT = '<script src="/static/course/dala-fx.js?v=5" defer></script>'


def _dala_lesson(html: str) -> str:
    html = _DALA_COLOR_RE.sub(lambda m: _DALA_COLORS[m.group(0).upper()], html)
    html = _DALA_WEIGHT_RE.sub(lambda m: "font-weight:" + _DALA_WEIGHT[m.group(1)], html)
    html = html.replace("<body>", '<body class="ob-les">', 1)
    return html


def _course_user_key() -> str:
    if g.is_employee:
        return "emp:" + (session.get("username") or "")
    return "owner"


_COURSE_HOOK = """<script>
(function () {
  var M = %d, MAX = %d, L = %s;
  function post(ev, score) {
    try {
      fetch('/api/course/progress', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module: M, event: ev, score: score }) });
    } catch (e) {}
  }
  post('open');
  try {
    var orig = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) {
      orig.apply(this, arguments);
      try { if (String(k).slice(-5) === '-quiz') post('quiz', parseInt(v, 10)); } catch (e) {}
    };
  } catch (e) {}
  function fix() {
    var bar = document.querySelector('.bar-in');
    if (bar && !document.getElementById('obBack')) {
      var a = document.createElement('a');
      a.id = 'obBack'; a.href = '/?tab=course';
      a.textContent = '\u2190 ' + L.back;
      a.setAttribute('style', 'margin-left:auto;flex:none;font-weight:800;font-size:14px;color:#fff;background:#1463E6;text-decoration:none;border-radius:10px;padding:8px 12px');
      bar.appendChild(a);
    }
    var brand = document.querySelector('.bar .brand');
    if (brand) brand.setAttribute('href', '/?tab=course');
    var next = document.querySelector('.done-card a.btn');
    if (next) {
      if (M < MAX) { next.href = '/course/' + (M + 1); next.textContent = L.next + ' \u2192'; }
      else { next.href = '/?tab=course'; next.textContent = L.map; }
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fix); else fix();
})();
</script>"""

# Бонус-урок — самостоятельное мини-приложение со своим тестом: результат
# итогового теста (из его localStorage) пересчитываем в баллы из 10.
_COURSE_BONUS_HOOK = """<script>
(function () {
  var M = %d, L10 = %s, KEY = 'ev-oil-course-uz-v1', sent = null;
  function report() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY) || '{}'), done = s.done || {};
      var fin = (window.L || []).filter(function (l) { return l.final; })[0];
      if (!fin || done[fin.id] == null) return;
      var score = Math.round(done[fin.id] * 10 / fin.quiz.length);
      if (score === sent) return;
      sent = score;
      fetch('/api/course/progress', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module: M, event: 'quiz', score: score }) });
    } catch (e) {}
  }
  try {
    fetch('/api/course/progress', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ module: M, event: 'open' }) });
    var orig = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) { orig.apply(this, arguments); if (k === KEY) report(); };
  } catch (e) {}
  function fix() {
    var bar = document.querySelector('.topbar-in');
    if (bar && !document.getElementById('obBackEv')) {
      var a = document.createElement('a');
      a.id = 'obBackEv'; a.href = '/?tab=course'; a.textContent = '\\u2190 ' + L10.back;
      var menu = document.getElementById('menuBtn');
      bar.insertBefore(a, menu || null);
    }
    report();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fix); else fix();
})();
</script>"""


def _inject(html: str, head: str, tail: str) -> str:
    i = html.find("</head>")
    html = html[:i] + head + html[i:] if i != -1 else head + html
    i = html.rfind("</body>")
    return html[:i] + tail + html[i:] if i != -1 else html + tail


@app.route("/course/<int:n>")
@login_required
def course_page(n):
    if not _course_allowed(n):
        return redirect("/?tab=course")
    bonus = n == COURSE_BONUS[0]
    path = os.path.join(COURSE_DIR, COURSE_BONUS_FILE if bonus else "modul-%d.html" % n)
    if not os.path.isfile(path):
        return redirect("/?tab=course")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    if bonus:
        hook = _COURSE_BONUS_HOOK % (n, json.dumps({"back": g.T["tab_course"]}))
    else:
        html = _dala_lesson(html)
        labels = json.dumps({"back": g.T["tab_course"], "next": g.T["course_next"], "map": g.T["course_to_map"]})
        hook = _COURSE_HOOK % (n, _course_max(), labels)
    html = _inject(html, _DALA_HEAD, _DALA_SCRIPT + hook)
    return Response(html, mimetype="text/html")


@app.route("/api/course")
@login_required
def api_course():
    prog = db.course_progress(g.shop_id, _course_user_key())
    mods = []
    for n, title, mins in COURSE_MODULES[:_course_max()]:
        p = prog.get(n) or {}
        mods.append({"n": n, "title": title, "mins": mins, "opened": bool(p.get("opened")),
                     "best": p.get("best"), "passed": bool(p.get("passed")), "locked": not _course_allowed(n)})
    n, title, mins = COURSE_BONUS
    p = prog.get(n) or {}
    bonus = {"n": n, "title": title, "mins": mins, "opened": bool(p.get("opened")),
             "best": p.get("best"), "passed": bool(p.get("passed")), "locked": not _course_allowed(n)}
    # закрыт — показываем, как открыть: владелец — кнопкой на подписку,
    # филиал и сотрудник — подсказкой (платит владелец главной точки)
    gate = {"locked": _course_locked(), "owner": _is_sub_owner(), "months": db.COURSE_GIFT_MONTHS}
    return jsonify({"ok": True, "modules": mods, "bonus": bonus, "gate": gate})


@app.route("/api/course/progress", methods=["POST"])
@login_required
@readonly_ok
def api_course_progress():
    data = request.get_json(silent=True) or {}
    try:
        n = int(data.get("module"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "module"}), 400
    if not _course_allowed(n):
        return jsonify({"ok": False, "error": "module"}), 403
    event = data.get("event")
    score = None
    if event == "quiz":
        try:
            score = int(data.get("score"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "score"}), 400
        if score < 0 or score > 10:
            return jsonify({"ok": False, "error": "score"}), 400
    elif event != "open":
        return jsonify({"ok": False, "error": "event"}), 400
    db.course_mark(g.shop_id, _course_user_key(), n, event, score)
    return jsonify({"ok": True})


@app.route("/api/set_language", methods=["POST"])
@login_required
@readonly_ok
def api_set_language():
    data = request.get_json(force=True)
    lang = data.get("language")
    if lang not in ("ru", "uz"):
        return jsonify({"ok": False, "error": "invalid language"}), 400
    db.set_shop_language(g.shop_id, lang)
    return jsonify({"ok": True})


def _head_usd_rate(shop):
    """Курс доллара главной точки — для филиала, если он не задал свой."""
    if shop and shop.get("role") == "branch" and shop.get("parent_shop_id"):
        parent = db.get_shop(shop["parent_shop_id"])
        return parent.get("usd_rate") if parent else None
    return None


def _effective_usd_rate(shop):
    """Единый курс сети: у филиала действует курс главной точки (свой — только
    если у главной курс ещё не задан)."""
    if not shop:
        return None
    return _head_usd_rate(shop) or shop.get("usd_rate")


def _usd_head_id():
    """Чей курс меняем: главная/самостоятельная точка — свой; филиал не меняет."""
    return None if g.is_branch or g.is_employee else g.shop_id


@app.route("/api/usd_rate", methods=["GET"])
@login_required
@employee_blocked
def api_get_usd_rate():
    """Раздел «Курс доллара»: текущий курс сети и история изменений."""
    shop = db.get_shop(g.shop_id)
    hist = db.get_usd_rate_history(g.shop_id)
    if g.is_branch:
        for h in hist:
            h.pop("reval_amount", None)
            h.pop("usd_products", None)
    return jsonify({"ok": True, "rate": _effective_usd_rate(shop), "can_edit": _usd_head_id() is not None,
                    "history": hist})


@app.route("/api/usd_rate", methods=["POST"])
@login_required
@employee_blocked
def api_set_usd_rate():
    """Новый курс доллара — для всей сети (главная + филиалы). Задаёт только
    главная или самостоятельная точка. Долларовые товары переоцениваются,
    в ответе — предложения поднять цены продажи."""
    head = _usd_head_id()
    if head is None:
        return jsonify({"ok": False, "error": "курс задаёт главная точка"}), 403
    data = request.get_json(force=True) or {}
    try:
        rate = float(data.get("rate"))
        if not (0 < rate < 1_000_000):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "укажите положительное число"}), 400
    res = db.set_network_usd_rate(head, rate)
    res.update({"ok": True, "effective": rate, "history": db.get_usd_rate_history(head)})
    return jsonify(res)


@app.route("/api/usd_rate/apply_prices", methods=["POST"])
@login_required
@profit_blocked
def api_usd_apply_prices():
    data = request.get_json(force=True) or {}
    n = db.apply_price_suggestions(g.shop_id, data.get("items") or [])
    return jsonify({"ok": True, "updated": n})


@app.route("/api/usd_rate/setup", methods=["GET"])
@login_required
@profit_blocked
def api_usd_setup_get():
    res = db.usd_setup_products(g.shop_id)
    res.update({"ok": True, "rate": _effective_usd_rate(db.get_shop(g.shop_id))})
    return jsonify(res)


@app.route("/api/usd_rate/setup", methods=["POST"])
@login_required
@profit_blocked
def api_usd_setup_save():
    """Разметка товаров: какие закупаются в $ и по какому курсу их вводили."""
    data = request.get_json(force=True) or {}
    try:
        entered = float(data.get("entered_rate"))
        if not (0 < entered < 1_000_000):
            raise ValueError()
        ids = [int(x) for x in data.get("product_ids") or []]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "укажите курс, по которому вводили товары"}), 400
    res = db.mark_usd_products(g.shop_id, ids, entered)
    res["ok"] = True
    return jsonify(res)




# ---- Подбор масла по модели машины ----
# Справочник лежит в car_specs.py (сгенерирован из Excel-справочника).
# Поиск по тексту модели: «Cobalt», «кобальт», «Nexia 3», «R4»… Марка из
# списка только помогает при равенстве. Отдаём 1 основной вариант и до 3
# альтернатив (например «Nexia» → Nexia 1/2, а Nexia 3 — кнопкой).
from car_specs import CAR_SPECS as _CAR_SPECS


def _spec_norm(s):
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-яўқғҳ]+", " ", s).strip()


def _spec_phrases(spec):
    out = set()
    for a in (spec.get("aliases") or "").split(","):
        if _spec_norm(a):
            out.add(_spec_norm(a))
    for part in re.split(r"[/()]", spec.get("model") or ""):
        if len(_spec_norm(part)) >= 3:
            out.add(_spec_norm(part))
    return out


_SPEC_INDEX = [(sp, _spec_phrases(sp)) for sp in _CAR_SPECS]
_SPEC_PUBLIC = ("id", "brand", "model", "engine", "oil_vol", "liters", "approval", "visc",
                "visc_list", "visc_hot", "trans", "trans_spec", "brake", "coolant", "approx")


def match_car_specs(brand, model, limit=4):
    q = _spec_norm(model)
    if len(q) < 2:
        return []
    qc = q.replace(" ", "")
    qt = set(q.split())
    b = _spec_norm(brand)
    if b == "ravon":
        b = "chevrolet"
    found = []
    for sp, phrases in _SPEC_INDEX:
        best, best_pc = 0, ""
        for p in phrases:
            pc = p.replace(" ", "")
            if len(pc) <= 3:
                sc = 100 if (p in qt or pc == qc) else 0
            elif pc == qc:
                sc = 100
            elif pc in qc:
                sc = 60 + len(pc)
            elif len(qc) >= 3 and qc in pc:
                sc = 30 + len(qc)
            else:
                sc = 0
            if sc > best:
                best, best_pc = sc, pc
        if best:
            sb = _spec_norm(sp.get("brand"))
            if b and b not in ("другое",) and (sb.startswith(b) or b.startswith(sb)):
                best += 5
            found.append((best, best_pc, sp))
    if not found:
        return []
    # «nexia» внутри «nexia3»: если найдено более длинное совпадение,
    # короткое (другой модели) не предлагаем
    full = [f for f in found if f[0] >= 60]
    found = [f for f in found if not (f[0] >= 60 and any(
        o is not f and o[0] >= 60 and f[1] != o[1] and f[1] in o[1] for o in full))]
    found.sort(key=lambda f: -f[0])
    return [{k: f[2].get(k) for k in _SPEC_PUBLIC} for f in found[:limit]]


# ---- VIN: расшифровка без платных сервисов ----
# 1) производитель — по первым 3 знакам (WMI, таблица ниже);
# 2) модель — из опыта всех точек OilBook (db.vin_models: мастер один раз
#    выбрал модель для такого начала VIN — дальше она подставляется сама);
# 3) если не знаем — бесплатный справочник NHTSA (vPIC), он хорошо знает
#    машины американского/корейского/японского рынка, для узбекских Chevrolet
#    обычно молчит — тогда мастер выбирает модель кнопкой, и мы её запоминаем.
_VIN_WMI = {
    "XWB": "Chevrolet", "KL1": "Chevrolet", "KL3": "Chevrolet", "KL4": "Chevrolet", "KL7": "Chevrolet",
    "KL8": "Chevrolet", "KLA": "Daewoo", "KLY": "Daewoo", "1G1": "Chevrolet", "1GN": "Chevrolet",
    "1GC": "Chevrolet", "3G1": "Chevrolet", "3GN": "Chevrolet", "X9L": "Chevrolet",
    "KMH": "Hyundai", "KMF": "Hyundai", "KMJ": "Hyundai", "KM8": "Hyundai", "5NP": "Hyundai", "5NM": "Hyundai",
    "KNA": "Kia", "KNB": "Kia", "KNC": "Kia", "KND": "Kia", "KNE": "Kia", "U5Y": "Kia", "U6Y": "Kia",
    "5XY": "Kia", "5XX": "Kia",
    "JTD": "Toyota", "JTE": "Toyota", "JTF": "Toyota", "JTK": "Toyota", "JTM": "Toyota", "JTN": "Toyota",
    "JT1": "Toyota", "JT2": "Toyota", "JT3": "Toyota", "SB1": "Toyota", "NMT": "Toyota", "4T1": "Toyota",
    "4T3": "Toyota", "5TD": "Toyota", "5TF": "Toyota", "MR0": "Toyota", "AHT": "Toyota",
    "JTH": "Lexus", "JTJ": "Lexus", "2T2": "Lexus",
    "JN1": "Nissan", "JN8": "Nissan", "SJN": "Nissan", "VSK": "Nissan", "1N4": "Nissan", "3N1": "Nissan",
    "5N1": "Nissan", "JHM": "Honda", "JHL": "Honda", "SHH": "Honda", "SHS": "Honda", "1HG": "Honda",
    "2HG": "Honda", "5J6": "Honda", "19X": "Honda",
    "WDB": "Mercedes-Benz", "WDD": "Mercedes-Benz", "WDC": "Mercedes-Benz", "WDF": "Mercedes-Benz",
    "W1K": "Mercedes-Benz", "W1N": "Mercedes-Benz", "W1V": "Mercedes-Benz",
    "WBA": "BMW", "WBS": "BMW", "WBX": "BMW", "WBY": "BMW", "5UX": "BMW", "5YM": "BMW",
    "WAU": "Audi", "WA1": "Audi", "TRU": "Audi", "WUA": "Audi",
    "WVW": "Volkswagen", "WVG": "Volkswagen", "WV1": "Volkswagen", "WV2": "Volkswagen", "3VW": "Volkswagen",
    "1VW": "Volkswagen", "XW8": "Volkswagen", "TMB": "Skoda", "WP0": "Porsche", "WP1": "Porsche",
    "XTA": "Lada (ВАЗ)", "XTT": "УАЗ", "X96": "ГАЗ", "XTC": "КамАЗ",
    "JAA": "Isuzu", "JAL": "Isuzu", "JM1": "Mazda", "JMZ": "Mazda", "JA3": "Mitsubishi", "JA4": "Mitsubishi",
    "JMB": "Mitsubishi", "WF0": "Ford", "NM0": "Ford", "1FA": "Ford", "1FM": "Ford", "1FT": "Ford",
    "LVV": "Chery", "LGW": "Haval", "L6T": "Geely", "LS5": "Changan", "LS4": "Changan", "LGX": "BYD",
    "LC0": "BYD", "LZZ": "Sinotruk", "LZG": "Shacman", "LFW": "FAW", "WMA": "MAN", "YV2": "Volvo",
    "YS2": "Scania", "XLR": "DAF", "ZCF": "Iveco",
}
# коды производителей нужны и сканеру на телефоне (выбор варианта VIN)
PAGE = PAGE.replace("__VIN_WMI__", json.dumps(sorted(_VIN_WMI)), 1)
# тема «Тёмное стекло»: стили строятся из уже собранной страницы (все вкладки
# и окна), отдаются отдельным файлом /ui/glass.css с версией в адресе
GLASS = glass_theme.Theme(PAGE)
PAGE = GLASS.install(PAGE)


def _glass_asset(body, mimetype):
    resp = Response(body, mimetype=mimetype)
    # адрес меняется при каждом изменении темы (?v=...) — можно хранить долго
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.route("/ui/glass.css")
def glass_css():
    return _glass_asset(GLASS.css, "text/css")


@app.route("/ui/glass.js")
def glass_js():
    return _glass_asset(GLASS.js, "application/javascript")
_VIN_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"
_VIN_TRANSLIT = {**{c: i + 1 for i, c in enumerate("ABCDEFGH")}, **{c: i + 1 for i, c in enumerate("JKLMN")},
                 "P": 7, "R": 9, **{c: i + 2 for i, c in enumerate("STUVWXYZ")}}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
_vpic_cache = {}


def _vin_check_ok(vin):
    total = sum((int(c) if c.isdigit() else _VIN_TRANSLIT.get(c, 0)) * w for c, w in zip(vin, _VIN_WEIGHTS))
    r = total % 11
    return vin[8] == ("X" if r == 10 else str(r))


def _vin_year(vin):
    i = _VIN_YEAR_CODES.find(vin[9])
    if i < 0:
        return None
    now = datetime.now().year
    years = [y for y in (1980 + i, 2010 + i) if y <= now + 1]
    return max(years) if years else None


def _vin_vpic(vin):
    if vin in _vpic_cache:
        return _vpic_cache[vin]
    res = None
    try:
        r = requests.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json", timeout=4)
        row = (r.json().get("Results") or [{}])[0]
        make, model = (row.get("Make") or "").strip(), (row.get("Model") or "").strip()
        if model:
            res = {"brand": make.title(), "model": model}
    except Exception:
        res = None
    if len(_vpic_cache) > 2000:
        _vpic_cache.clear()
    _vpic_cache[vin] = res
    return res


_BRAND_WORDS = ("kia", "hyundai", "toyota", "lexus", "ravon", "chevrolet", "daewoo", "skoda", "volkswagen",
                "lada", "mercedes-benz", "bmw", "audi", "porsche", "byd", "chery", "haval", "geely", "isuzu", "gaz", "uaz")


def _vin_model_choices(brand_lower):
    """Короткие названия моделей марки из справочника — для кнопок выбора."""
    out = []
    for sp in _CAR_SPECS:
        sb = (sp.get("brand") or "").lower()
        bw = (brand_lower.split() or [""])[0]
        if (sb != brand_lower and not (brand_lower == "chevrolet" and sb == "daewoo")
                and bw + " " not in (sp.get("model") or "").lower()):
            continue
        same = sb == brand_lower or (brand_lower == "chevrolet" and sb == "daewoo")
        own = (bw, sb.split()[0] if (sb and same) else "")
        for part in re.sub(r"\s*\(.*?\)", "", sp.get("model") or "").split(" / "):
            name = part.strip()
            low = name.lower()
            pref = next((w for w in own if w and low.startswith(w + " ")), None)
            if pref:
                name = name[len(pref) + 1:].strip()
            elif any(low.startswith(w + " ") for w in _BRAND_WORDS):
                continue
            name = re.sub(r"\s+1$", "", name)
            if len(name) < 2 or name.isdigit() or name in out:
                continue
            out.append(name)
    return out[:18]


def decode_vin(vin, shop_id=None):
    v = db.normalize_vin(vin)
    if not v:
        return {"ok": False}
    brand = _VIN_WMI.get(v[:3])
    out = {"ok": True, "vin": v, "brand": brand, "year": _vin_year(v), "check_ok": _vin_check_ok(v),
           "model": None, "model_source": None}
    learned = db.vin_lookup_model(v)
    if learned:
        out["model"], out["model_source"] = learned["model"], "learned"
        out["brand"] = out["brand"] or learned.get("brand")
    elif v[0] in "12345JKW":
        vp = _vin_vpic(v)
        if vp:
            out["model"], out["model_source"] = vp["model"], "vpic"
            out["brand"] = out["brand"] or vp["brand"]
    if shop_id:
        out["car"] = db.find_car_by_vin(shop_id, v)
    out["brand_in_list"] = out["brand"] in CAR_BRANDS
    q = " ".join(x for x in [out["model"]] if x)
    out["specs"] = match_car_specs(out["brand"] or "", q) if q else []
    # модели из справочника этой марки — кнопки «выберите модель»
    if not out["model"] and out["brand"]:
        b = out["brand"].lower()
        out["choices"] = _vin_model_choices(b)
    return out


@app.route("/api/top_models")
@login_required
def api_top_models():
    return jsonify({"models": db.top_car_models(g.shop_id)})


@app.route("/api/vin/decode")
@login_required
def api_vin_decode():
    return jsonify(decode_vin(request.args.get("vin", ""), g.shop_id))


@app.route("/api/car_specs")
@login_required
def api_car_specs():
    return jsonify({"matches": match_car_specs(request.args.get("brand", ""), request.args.get("model", ""))})


@app.route("/api/cars")
@login_required
def api_cars():
    """Список машин для «Базы» и подсказок госномера. Отдаём только поля,
    которые нужны экрану (раньше шло всё подряд — 1,4 МБ на 2 500 машин).
    Версия списка (X-Data-Version) — если у телефона уже есть такая же
    версия (?v=…), отвечаем 204 без данных: при повторном открытии «Базы»
    ничего заново не скачивается, пока в базе ничего не поменялось."""
    import hashlib
    cars = db.get_all_cars_overview(g.shop_id)
    slim = [{
        "plate_number": c["plate_number"], "car_brand": c["car_brand"], "car_model": c["car_model"],
        "owner_name": c["owner_name"], "owner_phone": c["owner_phone"], "client_id": c["client_id"],
        "link_token": c["link_token"], "telegram_id": 1 if c["telegram_id"] else 0,
        "change_date": c["change_date"], "next_change_date": c["next_change_date"], "cost": c["cost"],
    } for c in cars]
    body = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    version = hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]
    if request.args.get("v") == version:
        resp = Response(status=204)
    else:
        resp = Response(body, mimetype="application/json")
    resp.headers["X-Data-Version"] = version
    return resp


def _strip_cost_price(history):
    """Убирает cost_price (цена закупки, снятая со склада на момент продажи) из
    items_json перед отправкой сотруднику — иначе цена закупки была бы видна
    через сырой ответ сервера, даже если интерфейс её не показывает."""
    import json as _json
    for row in history:
        if not row.get("items_json"):
            continue
        try:
            items = _json.loads(row["items_json"])
        except (ValueError, TypeError):
            continue
        for item in items:
            item.pop("cost_price", None)
        row["items_json"] = _json.dumps(items, ensure_ascii=False)
    return history


@app.route("/api/history/<plate>")
@login_required
def api_history(plate):
    car, history = db.get_car_history(g.shop_id, plate)
    if g.is_employee or g.is_branch:
        history = _strip_cost_price(history)
    cross_history = db.get_cross_network_history(plate, g.shop_id)
    return jsonify({"car": car, "history": history, "cross_history": cross_history})


@app.route("/api/passport/send_tg/<plate>", methods=["POST"])
@login_required
def api_passport_send_tg(plate):
    """Отправить клиенту ссылку на сервисный паспорт машины через бота.
    Только машины своей точки; клиент должен быть подключён к боту."""
    car, _history = db.get_car_history(g.shop_id, plate)
    if not car:
        return jsonify({"ok": False, "error": g.T.get("kc_passport_tg_failed", "kc_passport_tg_failed")}), 404
    if not car.get("telegram_id"):
        return jsonify({"ok": False, "error": g.T.get("kc_passport_tg_no_client", "kc_passport_tg_no_client")}), 400
    if not car.get("passport_token"):
        return jsonify({"ok": False, "error": g.T.get("kc_passport_no_token", "kc_passport_no_token")}), 400
    origin = (PUBLIC_URL or request.host_url).rstrip("/")
    link = f"{origin}/passport/{car['passport_token']}"
    shop = db.get_shop(g.shop_id) or {}
    lang = "uz" if (shop.get("language") == "uz") else "ru"
    shop_name = shop.get("shop_name") or "OilBook"
    car_line = " ".join(x for x in [car.get("car_brand"), car.get("car_model")] if x)
    if lang == "uz":
        text = (f"🛡 Avtomobilingiz servis pasporti\n"
                f"{car['plate_number']}{(' · ' + car_line) if car_line else ''}\n\n"
                f"Barcha almashtirishlar tarixi «{shop_name}»da. Havolani ochib ko'ring yoki PDF yuklab oling.")
        btn = "Pasportni ochish"
    else:
        text = (f"🛡 Сервисный паспорт вашей машины\n"
                f"{car['plate_number']}{(' · ' + car_line) if car_line else ''}\n\n"
                f"Вся история замен в «{shop_name}». Откройте ссылку или скачайте PDF.")
        btn = "Открыть паспорт"
    if not BOT_TOKEN:
        return jsonify({"ok": False, "error": g.T.get("kc_passport_tg_failed", "kc_passport_tg_failed")}), 500
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": car["telegram_id"], "text": text,
                  "reply_markup": {"inline_keyboard": [[{"text": btn, "url": link}]]}},
            timeout=10,
        )
        ok = resp.ok
        if not ok:
            logger.warning(f"Паспорт не отправлен chat_id={car['telegram_id']}: HTTP {resp.status_code} — {resp.text[:300]}")
    except Exception as e:
        logger.error(f"Паспорт не отправлен: {e}")
        ok = False
    if not ok:
        return jsonify({"ok": False, "error": g.T.get("kc_passport_tg_failed", "kc_passport_tg_failed")}), 502
    return jsonify({"ok": True})


@app.route("/api/entry_presets")
@login_required
def api_entry_presets():
    """Готовые наборы для формы замены — частые сочетания масла и фильтров
    этой точки для выбранной модели (только позиции и цены продажи)."""
    model = (request.args.get("model") or "").strip()[:60]
    try:
        sets = db.get_popular_item_sets(g.shop_id, model)
    except Exception:
        sets = []
    return jsonify({"sets": sets})


def _employee_record_guard(rec):
    """Сотрудник правит и удаляет только СВОИ записи и только за сегодня —
    иначе запись «за наличные» можно было бы убрать или уменьшить задним
    числом. Владелец и филиал — без ограничений."""
    if not g.is_employee:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    if rec.get("employee_id") == g.employee_id and str(rec.get("change_date") or "")[:10] == today:
        return None
    return jsonify({"ok": False, "error": g.T["emp_only_own_today"]}), 403


def _log_action(action, details):
    """Журнал для владельца (удаления и правки денег). Сбой журнала не должен
    ломать само действие — только пишем в лог сервера."""
    try:
        db.log_action(g.shop_id, session.get("username"), g.is_employee, action, details)
    except Exception as e:
        logger.error(f"Журнал действий не записан ({action}): {e}")


def _money(rec):
    return {"cost": rec.get("cost"), "cash": rec.get("cash_amount"), "card": rec.get("card_amount")}


@app.route("/api/oil_change/<int:oc_id>", methods=["PUT"])
@login_required
def api_update_oil_change(oc_id):
    data = request.get_json(force=True)
    before = db.get_oil_change_for_shop(oc_id, g.shop_id)
    if not before:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    denied = _employee_record_guard(before)
    if denied:
        return denied
    try:
        ok = db.update_oil_change(
            oc_id, g.shop_id,
            mileage=int(data["mileage"]) if data.get("mileage") not in (None, "") else None,
            next_mileage=int(data["next_mileage"]) if data.get("next_mileage") not in (None, "") else None,
            cost=int(data["cost"]) if data.get("cost") not in (None, "") else None,
            interval_value=int(data["interval_value"]) if data.get("interval_value") not in (None, "") else None,
            interval_unit=data.get("interval_unit"),
            notes=data.get("notes"),
            items=data.get("items"),
            cash_amount=int(data["cash_amount"]) if data.get("cash_amount") not in (None, "") else None,
            card_amount=int(data["card_amount"]) if data.get("card_amount") not in (None, "") else None,
            discount=int(float(data["discount"])) if data.get("discount") not in (None, "") else None,
            discount_pct=data.get("discount_pct"),
        )
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not ok:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    after = db.get_oil_change_for_shop(oc_id, g.shop_id) or {}
    if _money(after) != _money(before):
        _log_action("edit_service", {"plate": before.get("plate_number"), "date": before.get("change_date"),
                                     "before": _money(before), "after": _money(after)})
    # «Мастер» меняет только владелец (сотрудник не может переписать замену на себя)
    if "master_id" in data and not g.is_employee:
        raw = data.get("master_id")
        try:
            if raw in (None, "", 0, "0"):
                rec = db.get_oil_change_for_shop(oc_id, g.shop_id) or {}
                db.set_oil_change_master(oc_id, g.shop_id, 0 if rec.get("employee_id") else None)
            elif db.is_shop_employee(g.shop_id, raw):
                db.set_oil_change_master(oc_id, g.shop_id, int(raw))
        except Exception as e:
            logger.warning(f"мастер замены не сохранён: {e}")
    return jsonify({"ok": True})


@app.route("/api/oil_change/<int:oc_id>", methods=["DELETE"])
@login_required
def api_delete_oil_change(oc_id):
    rec = db.get_oil_change_for_shop(oc_id, g.shop_id)
    if not rec:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    denied = _employee_record_guard(rec)
    if denied:
        return denied
    ok = db.delete_oil_change(oc_id, g.shop_id)
    if ok == "has_debt":
        return jsonify({"ok": False, "error": "has_debt"}), 400
    if not ok:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    _log_action("delete_service", {"plate": rec.get("plate_number"), "date": rec.get("change_date"),
                                   "service": rec.get("service_type"), **_money(rec)})
    return jsonify({"ok": True})


@app.route("/api/car/<plate>", methods=["PUT"])
@login_required
def api_update_car(plate):
    """Редактирование данных клиента и машины — имя, телефон, госномер,
    марка/модель. Доступно всем ролям (владелец, филиал, сотрудник),
    ограничено только собственной точкой."""
    data = request.get_json(force=True)
    new_plate = (data.get("plate") or "").strip()
    owner_name = (data.get("owner_name") or "").strip()
    owner_phone = (data.get("owner_phone") or "").strip()
    car_brand = data.get("car_brand") or None
    car_model = (data.get("car_model") or "").strip() or None
    if not new_plate or not owner_name:
        return jsonify({"ok": False, "error": "госномер и имя обязательны"}), 400
    with db.WRITE_LOCK:
        if data.get("new_owner"):
            # машину продали — переводим на нового владельца, история остаётся
            res = db.change_car_owner(g.shop_id, plate, owner_name, owner_phone)
            if not res["ok"]:
                return jsonify({"ok": False, "error": _owner_change_error(res["error"])}), 400
        ok = db.update_car_and_client(g.shop_id, plate, new_plate, owner_name, owner_phone, car_brand, car_model)
    if not ok:
        return jsonify({"ok": False, "error": "машина не найдена, или новый госномер уже занят другой машиной"}), 400
    return jsonify({"ok": True, "plate": db.normalize_plate(new_plate)})


def _owner_change_error(code):
    return {"has_debt": g.T["err_owner_has_debt"], "same_owner": g.T["err_owner_same"]}.get(code, "машина не найдена")


@app.route("/api/car/<plate>", methods=["DELETE"])
@login_required
@employee_blocked
def api_delete_car(plate):
    """Полное удаление машины — сама машина, вся её история, связанные
    долги. Клиент (владелец) остаётся, если у него есть другие машины.
    Только владелец/филиал: сотрудник не может стереть историю целиком."""
    ok = db.delete_car_completely(g.shop_id, plate)
    if not ok:
        return jsonify({"ok": False, "error": "машина не найдена"}), 404
    _log_action("delete_car", {"plate": db.normalize_plate(plate)})
    return jsonify({"ok": True})


@app.route("/api/action_log")
@login_required
@employee_blocked
def api_action_log():
    return jsonify({"ok": True, "log": db.list_action_log(g.shop_id)})


def _send_service_receipt(shop, plate, items, cash_amount, card_amount, next_date, discount=0):
    """Присылает клиенту чек в Telegram сразу после внесения замены — что
    залили, сколько стоило, когда следующая. Отдельно от напоминания о
    следующей замене (то приходит позже, ближе к сроку). Молча ничего не
    делает, если клиент не привязан к боту — это не должно мешать
    основному сохранению записи."""
    telegram_id = shop.get("_receipt_telegram_id")
    if not telegram_id:
        return
    total = sum((it.get("total") or 0) for it in (items or []))
    lang = shop.get("language") or "ru"
    lines = "\n".join(
        f"• {it.get('name', '')}"
        + (f" ({it['brand']})" if it.get("brand") else "")
        + (f" — {it['qty']} {i18n.t('liters_ph', lang)}" if it.get("qty") and it.get("qty") != 1 else "")
        + f": {int(it.get('total') or 0):,}".replace(",", " ")
        for it in (items or [])
    )
    if discount:
        total -= discount
        lines += "\n" + i18n.t("bot_receipt_discount", lang, amount=f"{int(discount):,}".replace(",", " "))
    text = i18n.t(
        "bot_service_receipt", lang,
        plate=plate, shop=shop.get("shop_name") or shop.get("username") or "",
        items=lines or "—", total=f"{total:,}".replace(",", " "),
        cash=f"{(cash_amount or 0):,}".replace(",", " "), card=f"{(card_amount or 0):,}".replace(",", " "),
        next_date=next_date or "—",
    )
    _send_telegram_message(telegram_id, text)


@app.route("/api/add", methods=["POST"])
@login_required
def api_add():
    data = request.get_json(force=True)
    try:
        plate = data["plate"]
        owner_name = data["owner_name"]
        owner_phone = data.get("owner_phone") or None
        car_brand = data.get("car_brand") or None
        car_model = data.get("car_model") or None
        vin = db.normalize_vin(data.get("vin"))
        mileage = int(data["mileage"]) if data.get("mileage") else None
        next_mileage = int(data["next_mileage"]) if data.get("next_mileage") else None
        # проверяем позиции ДО того, как создадим клиента/машину — иначе при
        # ошибке в позициях остались бы пустые записи
        items = db.sanitize_items(data.get("items") or [])
        interval_value = int(data["interval_value"])
        interval_unit = data.get("interval_unit") or "months"
        if interval_unit not in ("days", "months"):
            interval_unit = "months"
        notes = data.get("notes") or ""
        cash_amount = int(data["cash_amount"]) if data.get("cash_amount") not in (None, "") else None
        card_amount = int(data["card_amount"]) if data.get("card_amount") not in (None, "") else None
        debt_amount = int(data["debt_amount"]) if data.get("debt_amount") not in (None, "") else 0
        discount = int(float(data["discount"])) if data.get("discount") not in (None, "") else 0
        discount_pct = data.get("discount_pct")
        installment_amount = int(data["installment_amount"]) if data.get("installment_amount") not in (None, "") else None
        interval_days = int(data["interval_days"]) if data.get("interval_days") not in (None, "") else None
        try:
            daily_km = int(float(data["daily_km"])) if data.get("daily_km") not in (None, "") else None
        except (TypeError, ValueError):
            daily_km = None
        if daily_km is not None and not (1 <= daily_km <= 2000):
            daily_km = None

        # проверка рассрочки — ДО сохранения: раньше запись и списание склада
        # уже происходили, а потом приходила ошибка, человек нажимал ещё раз —
        # и замена сохранялась дважды
        if debt_amount > 0 and (not installment_amount or not interval_days):
            return jsonify({"ok": False, "error": "укажите сумму платежа и период для рассрочки"}), 400

        # весь приём замены — под общим замком записи: два телефона одной точки,
        # одновременно вносящие одну и ту же новую машину, больше не получают
        # ошибку «UNIQUE constraint failed» и не плодят пустых клиентов
        add_token = str(data.get("token") or "")[:64] or None
        with db.WRITE_LOCK:
            # повторная отправка той же замены (ответ не дошёл по слабому
            # интернету, нажали ещё раз) — ничего не пишем, отвечаем «уже сохранено»
            prev = db.get_add_token_result(g.shop_id, add_token)
            if prev is not None:
                prev["ok"] = True
                prev["duplicate"] = True
                return jsonify(prev)
            existing_car = db.find_car(g.shop_id, plate)
            if existing_car and data.get("new_owner"):
                # машину продали: сначала переводим на нового владельца (если
                # нельзя — ничего не сохраняем и объясняем почему)
                res = db.change_car_owner(g.shop_id, plate, owner_name, owner_phone)
                if not res["ok"]:
                    return jsonify({"ok": False, "error": _owner_change_error(res["error"])}), 400
                existing_car = db.find_car(g.shop_id, plate)
            if existing_car:
                client_id = existing_car["client_id"]
                car_id = db.create_or_update_car(g.shop_id, plate, client_id, car_brand, car_model, vin=vin)
            else:
                client = db.get_or_create_client(g.shop_id, owner_name, owner_phone)
                client_id = client["id"]
                car_id = db.create_or_update_car(g.shop_id, plate, client_id, car_brand, car_model, vin=vin)

            oc_id, next_date = db.add_oil_change(
                car_id, mileage, None, None, False, None, interval_value, interval_unit, notes,
                next_mileage=next_mileage, items=items, cash_amount=cash_amount, card_amount=card_amount,
                allow_debt=debt_amount > 0, discount=discount, discount_pct=discount_pct,
                employee_id=g.employee_id, master_id=_master_arg(data.get("master_id"))
            )
            _saved_rec = db.get_oil_change_for_shop(oc_id, g.shop_id) or {}
            saved_discount = _saved_rec.get("discount_amount") or 0
            if debt_amount > 0:
                # сумму долга считает сервер: сумма замены − нал − карта (раньше
                # бралась из браузера и могла не совпасть с самой записью)
                _saved = db.get_oil_change_for_shop(oc_id, g.shop_id) or {}
                debt_amount = max(0, (_saved.get("cost") or 0) - (_saved.get("cash_amount") or 0)
                                  - (_saved.get("card_amount") or 0))
            if vin and car_model:
                try:
                    db.vin_learn(vin, car_brand, car_model)
                except Exception as e:
                    logger.warning(f"vin_learn: {e}")
            if daily_km:
                try:
                    db.set_oil_change_daily_km(oc_id, daily_km)
                except Exception as e:  # не критично: замена уже сохранена
                    logger.warning(f"не удалось сохранить пробег в день: {e}")

            if debt_amount > 0:
                db.create_installment_plan(g.shop_id, car_id, debt_amount, installment_amount, interval_days, oil_change_id=oc_id)

        # с этого места замена УЖЕ сохранена — что бы дальше ни случилось,
        # человеку нельзя показывать «ошибку» (он нажмёт ещё раз и будет дубль)
        link = None
        try:
            car_after, _ = db.get_car_history(g.shop_id, plate)
            if car_after and not car_after["telegram_id"]:
                link = _client_link(car_after["link_token"])
            elif car_after and car_after["telegram_id"]:
                shop = db.get_shop(g.shop_id)
                if shop:
                    shop["_receipt_telegram_id"] = car_after["telegram_id"]
                    # чек в Telegram — в фоне: не задерживаем ответ и не держим запрос
                    def _bg_receipt(shop=shop, plate=plate, items=items, cash=cash_amount, card=card_amount, nd=next_date, oc=oc_id, sid=g.shop_id, disc=saved_discount):
                        try:
                            # 12 с ждём: мастер может нажать «Отменить» на экране
                            # «Сохранено» — тогда чек клиенту не уходит
                            time.sleep(12)
                            if not db.get_oil_change_for_shop(oc, sid):
                                return
                            _send_service_receipt(shop, plate, items, cash, card, nd, disc)
                        except Exception as ex:
                            logger.warning(f"чек не отправлен: {ex}")
                    threading.Thread(target=_bg_receipt, daemon=True).start()
        except Exception as e:
            logger.warning(f"после сохранения замены: {e}")
        result = {"ok": True, "next_date": next_date, "client_link": link, "oc_id": oc_id}
        try:
            db.save_add_token_result(g.shop_id, add_token, result)
        except Exception as e:
            logger.warning(f"не удалось запомнить номер отправки: {e}")
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/debts")
@login_required
def api_list_debts():
    return jsonify(db.get_active_debts(g.shop_id))


@app.route("/api/debts/overview")
@login_required
def api_debts_overview():
    return jsonify(db.get_debts_overview(g.shop_id))


@app.route("/api/debts/closed")
@login_required
def api_debts_closed():
    return jsonify(db.get_closed_debts(g.shop_id))


@app.route("/api/dashboard")
@login_required
def api_dashboard():
    """Всё для dashboard одним запросом — график выручки за 30 дней, топ
    товаров по количеству, сводка по долгам, и товары с малым остатком.
    Склад и товары не относятся к филиалу/сотруднику без склада — тогда
    просто возвращаются пустыми, без ошибки."""
    result = {
        "daily_revenue": db.get_daily_revenue(g.shop_id, days=30),
        "top_products": db.get_top_products_by_qty(g.shop_id, days=30, limit=5),
        "debt_summary": db.get_debt_summary(g.shop_id),
        "low_stock": [],
        "net_profit": None,
    }
    # прибыль (и чистая прибыль) — только для самостоятельной точки или главного
    # аккаунта; филиал и сотрудник её не видят, как и в остальной статистике
    if not g.is_employee and not g.is_branch:
        result["net_profit"] = db.get_net_profit_30d(g.shop_id)
    shop = db.get_shop(g.shop_id)
    if shop and shop.get("warehouse_enabled") and not g.is_employee:
        low_stock = db.get_low_stock_products(g.shop_id)
        if g.is_branch:
            for p in low_stock:
                p.pop("purchase_price", None)
        result["low_stock"] = low_stock
    return jsonify(result)


@app.route("/api/dashboard/top_brands")
@login_required
def api_dashboard_top_brands():
    """Топ-10 брендов внутри одной категории — для раскрытия по клику на
    строку категории, что на dashboard (30 дней), что в произвольном
    периоде (если переданы from/to)."""
    category = request.args.get("category", "")
    if not category:
        return jsonify({"ok": False, "error": "укажите категорию"}), 400
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    if date_from and date_to:
        return jsonify(db.get_top_brands_for_category_range(g.shop_id, category, date_from, date_to, limit=10))
    return jsonify(db.get_top_brands_for_category(g.shop_id, category, days=30, limit=10))


@app.route("/api/expenses/categories")
@login_required
def api_expense_categories():
    return jsonify(db.EXPENSE_PRESET_CATEGORIES)


@app.route("/api/expenses")
@login_required
@employee_blocked
def api_list_expenses():
    """Журнал разовых расходов за период — сотруднику не показываем
    (финансовая информация точки, как и цена закупки)."""
    date_from = request.args.get("from") or "2000-01-01"
    date_to = request.args.get("to") or "2100-01-01"
    return jsonify(db.get_expenses(g.shop_id, date_from, date_to))


@app.route("/api/expenses", methods=["POST"])
@login_required
@employee_blocked
def api_log_expense():
    data = request.get_json(force=True)
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip() or None
    try:
        amount = int(data["amount"])
        if amount <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "укажите положительную сумму"}), 400
    if not category:
        return jsonify({"ok": False, "error": "укажите категорию"}), 400
    db.log_expense(g.shop_id, category, name, amount, data.get("expense_date"))
    return jsonify({"ok": True})


@app.route("/api/expenses/<int:entry_id>", methods=["PUT"])
@login_required
@employee_blocked
def api_update_expense(entry_id):
    data = request.get_json(force=True)
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip() or None
    try:
        amount = int(data["amount"])
        if amount <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "укажите положительную сумму"}), 400
    if not category:
        return jsonify({"ok": False, "error": "укажите категорию"}), 400
    from datetime import datetime as _dt
    expense_date = data.get("expense_date") or _dt.now().strftime("%Y-%m-%d")
    ok = db.update_expense_entry(entry_id, g.shop_id, category, name, amount, expense_date)
    if not ok:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    return jsonify({"ok": True})


@app.route("/api/expenses/<int:entry_id>", methods=["DELETE"])
@login_required
@employee_blocked
def api_delete_expense(entry_id):
    ok = db.delete_expense_entry(entry_id, g.shop_id)
    if not ok:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    return jsonify({"ok": True})


@app.route("/api/recurring_expenses")
@login_required
@employee_blocked
def api_list_recurring_expenses():
    return jsonify(db.get_recurring_expenses(g.shop_id))


@app.route("/api/recurring_expenses", methods=["POST"])
@login_required
@employee_blocked
def api_create_recurring_expense():
    data = request.get_json(force=True)
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip() or None
    try:
        amount = int(data["amount"])
        day_of_month = int(data["day_of_month"])
        if amount <= 0 or not (1 <= day_of_month <= 28):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "укажите сумму и число месяца (1-28)"}), 400
    if not category:
        return jsonify({"ok": False, "error": "укажите категорию"}), 400
    plan = db.create_recurring_expense(g.shop_id, category, name, amount, day_of_month)
    return jsonify({"ok": True, "expense": plan})


@app.route("/api/recurring_expenses/<int:expense_id>", methods=["DELETE"])
@login_required
@employee_blocked
def api_delete_recurring_expense(expense_id):
    ok = db.delete_recurring_expense(expense_id, g.shop_id)
    if not ok:
        return jsonify({"ok": False, "error": "не найдено"}), 404
    return jsonify({"ok": True})


@app.route("/api/recurring_expenses/<int:expense_id>/pay", methods=["POST"])
@login_required
@employee_blocked
def api_pay_recurring_expense(expense_id):
    plan = db.get_recurring_expense(expense_id, g.shop_id)
    if not plan:
        return jsonify({"ok": False, "error": "не найдено"}), 404
    db.log_expense(g.shop_id, plan["category"], plan["name"], plan["amount"], recurring_expense_id=expense_id)
    return jsonify({"ok": True})


@app.route("/api/debts/<int:plan_id>/pay", methods=["POST"])
@login_required
def api_pay_debt(plan_id):
    data = request.get_json(force=True)
    try:
        amount = int(data["amount"])
        if amount <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "укажите положительную сумму платежа"}), 400
    # дата платежа — настоящая и не в будущем; сотрудник вносит только сегодняшним
    # днём (иначе деньги «уезжают» в другой день статистики и кассы)
    today = datetime.now().date()
    try:
        paid_day = datetime.strptime(str(data.get("paid_date") or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        paid_day = today
    if paid_day > today or g.is_employee:
        paid_day = today
    plan = db.log_installment_payment(plan_id, g.shop_id, amount, paid_day.strftime("%Y-%m-%d"),
                                      employee_id=g.employee_id)
    if not plan:
        return jsonify({"ok": False, "error": "долг не найден"}), 404
    if plan.get("error") == "overpay":
        return jsonify({"ok": False, "error": "overpay", "remaining": plan["remaining"]}), 400
    if plan.get("error"):
        return jsonify({"ok": False, "error": "долг уже закрыт"}), 400
    return jsonify({"ok": True, "plan": plan})


@app.route("/api/debts/<int:plan_id>/payments/<int:payment_id>/cancel", methods=["POST"])
@login_required
@employee_blocked
def api_cancel_debt_payment(plan_id, payment_id):
    plan = db.cancel_installment_payment(plan_id, g.shop_id, payment_id)
    if not plan:
        return jsonify({"ok": False, "error": "долг не найден"}), 404
    if plan.get("error") == "written_off":
        return jsonify({"ok": False, "error": "долг списан — платежи по нему не отменяются"}), 400
    if plan.get("error"):
        return jsonify({"ok": False, "error": "платёж не найден или уже отменён"}), 404
    return jsonify({"ok": True, "plan": plan})


@app.route("/api/debts/<int:plan_id>/writeoff", methods=["POST"])
@login_required
@employee_blocked
def api_writeoff_debt(plan_id):
    data = request.get_json(silent=True) or {}
    plan = db.write_off_installment(plan_id, g.shop_id, data.get("reason"))
    if not plan:
        return jsonify({"ok": False, "error": "долг не найден"}), 404
    if plan.get("error"):
        return jsonify({"ok": False, "error": "долг уже закрыт"}), 400
    return jsonify({"ok": True, "plan": plan})


@app.route("/api/debts/<int:plan_id>/payments")
@login_required
def api_debt_payments(plan_id):
    return jsonify(db.get_installment_payments(plan_id, g.shop_id))


# ============ Рассылки ============

@app.route("/api/broadcast/recipients")
@login_required
def api_broadcast_recipients():
    return jsonify({"count": len(db.get_all_linked_clients(g.shop_id))})


@app.route("/api/broadcast/history")
@login_required
def api_broadcast_history():
    return jsonify(db.get_recent_broadcasts(g.shop_id))


BROADCAST_MAX_LEN = 3500   # у Telegram предел 4096 символов на сообщение


@app.route("/api/broadcast", methods=["POST"])
@login_required
@employee_blocked
def api_broadcast_create():
    data = request.get_json(force=True, silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "empty message"}), 400
    if len(message) > BROADCAST_MAX_LEN:
        return jsonify({"ok": False, "error": g.T["broadcast_too_long"].format(n=BROADCAST_MAX_LEN)}), 400
    # частые рассылки — клиенты блокируют бота, и Telegram может закрыть его
    # для всех точек сразу; поэтому не больше одной в очереди и N в сутки
    if not db.broadcast_allowed(g.shop_id):
        return jsonify({"ok": False, "error": g.T["broadcast_limit"].format(n=db.BROADCAST_PER_DAY)}), 429
    broadcast_id = db.create_broadcast(g.shop_id, message)
    return jsonify({"ok": True, "id": broadcast_id})


# ============ Экспорт / бэкап ============

@app.route("/api/stats")
@login_required
@employee_blocked
def api_stats():
    result = db.get_revenue_stats(g.shop_id)
    result["comparison"] = db.get_revenue_comparison(g.shop_id)
    return jsonify(result)


@app.route("/api/stats/day")
@login_required
@employee_blocked
def api_stats_day():
    """Подробно за день (по умолчанию — сегодня): машины и работы, оплаты,
    погашенные долги, расходы, оплаты поставщикам. Цен закупки в ответе нет."""
    day = (request.args.get("date") or "").strip()[:10] or datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "error": "неверная дата"}), 400
    result = db.get_day_details(g.shop_id, day)
    result["ok"] = True
    return jsonify(result)


@app.route("/api/aggregated_stats")
@login_required
@profit_blocked
def api_aggregated_stats():
    """Для главного аккаунта — сложенные выручка и прибыль по нему самому и
    всем его филиалам вместе, плюс разбивка кто сколько продал по отдельности.
    Для точки без филиалов просто вернёт её же собственные числа (сумма по
    пустому списку филиалов — это она сама)."""
    branches = db.get_branches(g.shop_id)
    return jsonify({
        "has_branches": len(branches) > 0,
        "branch_count": len(branches),
        "revenue": db.get_aggregated_revenue_stats(g.shop_id),
        "profit": db.get_aggregated_profit_stats(g.shop_id),
        "breakdown": db.get_branch_breakdown_stats(g.shop_id),
    })


@app.route("/api/aggregated_stats/range")
@login_required
@profit_blocked
def api_aggregated_stats_range():
    """То же самое, но за произвольный период — для календаря на вкладке
    'Все филиалы', как и у собственной статистики."""
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return jsonify({"ok": False, "error": "invalid date"}), 400
    return jsonify({
        "ok": True,
        "revenue": db.get_aggregated_revenue_range(g.shop_id, date_from, date_to),
        "profit": db.get_aggregated_profit_range(g.shop_id, date_from, date_to),
        "breakdown": db.get_branch_breakdown_range(g.shop_id, date_from, date_to),
    })


@app.route("/api/my_branches")
@login_required
@profit_blocked
def api_my_branches():
    """Список филиалов главного аккаунта со сводкой по складу — для панели
    управления ценами закупки. Филиалу самому это не нужно (заблокировано
    profit_blocked)."""
    branches = db.get_branches(g.shop_id)
    summary = {s["id"]: s for s in db.get_branch_warehouse_summary(g.shop_id)}
    result = []
    for b in branches:
        s = summary.get(b["id"], {"product_count": 0, "missing_price_count": 0, "stock_value": 0})
        result.append({
            "id": b["id"], "shop_name": b["shop_name"], "username": b["username"],
            "product_count": s["product_count"], "missing_price_count": s["missing_price_count"],
            "stock_value": s.get("stock_value", 0),
        })
    return jsonify(result)


@app.route("/api/branches/<int:branch_id>/products")
@login_required
@profit_blocked
def api_branch_products(branch_id):
    """Главный аккаунт смотрит склад конкретного своего филиала — с ценой
    закупки, которую сам филиал не видит. Проверяем, что это реально его
    филиал, а не чужая точка."""
    if not db.is_branch_of(branch_id, g.shop_id):
        return jsonify({"ok": False, "error": "это не ваш филиал"}), 403
    return jsonify(db.list_products(branch_id))


@app.route("/api/branches/<int:branch_id>/products/<int:product_id>/purchase_price", methods=["POST"])
@login_required
@profit_blocked
def api_set_branch_purchase_price(branch_id, product_id):
    if not db.is_branch_of(branch_id, g.shop_id):
        return jsonify({"ok": False, "error": "это не ваш филиал"}), 403
    data = request.get_json(force=True)
    try:
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "неверная цена"}), 400
    ok = db.set_product_purchase_price(product_id, branch_id, purchase_price)
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/stats/brands")
@login_required
@employee_blocked
def api_stats_brands():
    """Топ-10 брендов по каждой категории (масла, антифриз, фильтры...) за период."""
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return jsonify({"ok": False, "error": "invalid date"}), 400
    scope = request.args.get("scope", "")
    if scope:
        # сводка по сети — только главному аккаунту и только по своим филиалам
        if g.is_branch:
            return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
        shop_ids = _resolve_network_scope(scope)
        if not shop_ids:
            return jsonify({"ok": False, "error": "нет доступа к этой точке"}), 403
    else:
        shop_ids = [g.shop_id]
    result = db.get_brand_breakdown(shop_ids, date_from, date_to, limit=10)
    result["ok"] = True
    return jsonify(result)


def _resolve_network_scope(scope: str):
    """'all' — главный + все его филиалы; число — одна точка, но только если это
    сам главный или ЕГО филиал (чужой филиал подставить нельзя)."""
    if scope == "all":
        return [g.shop_id] + [b["id"] for b in db.get_branches(g.shop_id)]
    try:
        sid = int(scope)
    except (TypeError, ValueError):
        return None
    if sid == g.shop_id or db.is_branch_of(sid, g.shop_id):
        return [sid]
    return None


@app.route("/api/network/overview")
@login_required
@profit_blocked
def api_network_overview():
    """Полная картина по сети филиалов (или по одному филиалу) для главного."""
    shop_ids = _resolve_network_scope(request.args.get("scope", "all"))
    if not shop_ids:
        return jsonify({"ok": False, "error": "нет доступа к этой точке"}), 403
    result = db.get_network_overview(shop_ids)
    result["shops"] = db.network_shops(g.shop_id)
    result["ok"] = True
    return jsonify(result)


@app.route("/api/network/compare")
@login_required
@profit_blocked
def api_network_compare():
    """Сравнение филиалов между собой за неделю/месяц/год."""
    result = db.get_network_compare(g.shop_id, request.args.get("period", "month"))
    result["ok"] = True
    return jsonify(result)


@app.route("/api/stats/range")
@login_required
@employee_blocked
def api_stats_range():
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return jsonify({"ok": False, "error": "invalid date"}), 400
    result = db.get_revenue_range(g.shop_id, date_from, date_to)
    result["ok"] = True
    # график по дням разворачивает каждый день диапазона — при случайно
    # огромном периоде (например, опечатка в годе) это могло бы дать
    # десятки тысяч точек; сами суммы (revenue/top_products/прибыль) не
    # затронуты, они считаются агрегатно, а не по дням
    span_days = (datetime.strptime(date_to, "%Y-%m-%d") - datetime.strptime(date_from, "%Y-%m-%d")).days
    result["daily_revenue"] = db.get_daily_revenue_range(g.shop_id, date_from, date_to) if 0 <= span_days <= 730 else []
    result["top_products"] = db.get_top_products_by_qty_range(g.shop_id, date_from, date_to, limit=5)
    if not g.is_branch:
        pb = db.get_profit_breakdown(g.shop_id, date_from, date_to)
        expenses = sum(e["amount"] for e in db.get_expenses(g.shop_id, date_from, date_to))
        result["profit"] = pb["profit"]
        result["goods_profit"] = pb["goods_profit"]
        result["services"] = pb["services"]
        result["unpriced"] = pb["unpriced"]
        result["discounts"] = pb["discounts"]
        result["expenses"] = expenses
        result["net_profit"] = pb["profit"] - expenses
        usd = db.profit_usd_range(g.shop_id, date_from, date_to)
        result["profit_usd"] = usd["profit_usd"]
        result["net_profit_usd"] = usd["net_usd"]
    return jsonify(result)


@app.route("/api/sms_settings", methods=["POST"])
@login_required
@employee_blocked
def api_sms_settings():
    shop = db.get_shop(g.shop_id)
    if not shop or not shop.get("sms_enabled"):
        return jsonify({"ok": False, "error": "SMS не включены для вашей точки"}), 403
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not email:
        return jsonify({"ok": False, "error": "укажите email от Eskiz"}), 400
    if not password:
        # пароль не прислан -> оставляем прежний, меняем только email
        _, existing_password = db.get_shop_eskiz_credentials(g.shop_id)
        password = existing_password or ""
    if not password:
        return jsonify({"ok": False, "error": "укажите пароль от Eskiz"}), 400
    db.set_shop_eskiz_credentials(g.shop_id, email, password)
    return jsonify({"ok": True})


def _warehouse_required():
    shop = db.get_shop(g.shop_id)
    if not shop or not shop.get("warehouse_enabled"):
        return jsonify({"ok": False, "error": "Склад не включён для вашей точки"}), 403
    return None


def _store_on(shop) -> bool:
    """Включён ли «Склад магазина» (нужен и сам склад)."""
    return bool(shop and shop.get("warehouse_enabled") and shop.get("store_enabled"))


@app.route("/api/frequent_items")
@login_required
def api_frequent_items():
    """«Часто берут» по категориям для формы замены (только цены продажи)."""
    try:
        return jsonify(db.get_frequent_items(g.shop_id))
    except Exception as e:
        logger.warning(f"frequent_items: {e}")
        return jsonify({})


@app.route("/api/products")
@login_required
def api_list_products():
    products = db.list_products(g.shop_id)
    if g.is_employee or g.is_branch:
        for p in products:
            p.pop("purchase_price", None)
    if g.is_employee and _store_on(db.get_shop(g.shop_id)):
        # сотрудник работает только с магазином — основной склад ему не виден
        for p in products:
            p["stock_qty"] = p.get("shop_qty") or 0
    return jsonify(products)


# ---------- «Склад магазина» ----------
STORE_EMPLOYEE_FIELDS = ("id", "name", "category", "unit", "sell_price", "shop_qty", "per_day",
                         "store_days_left", "store_status")


@app.route("/api/store/overview")
@login_required
def api_store_overview():
    """Склад магазина. Хозяину — всё (включая остаток основного склада и
    подсказку, сколько перенести); сотруднику — только магазин."""
    shop = db.get_shop(g.shop_id)
    if not _store_on(shop):
        return jsonify({"ok": False, "error": "Склад магазина не включён"}), 403
    result = db.get_warehouse_overview(g.shop_id)
    s = result["summary"]
    summary = {"product_count": s["product_count"], "store_low_count": s["store_low_count"],
               "store_out_count": s["store_out_count"]}
    if g.is_employee:
        products = [{k: p.get(k) for k in STORE_EMPLOYEE_FIELDS} for p in result["products"]]
    else:
        summary["store_suggest_count"] = s["store_suggest_count"]
        products = result["products"]
        if g.is_branch:
            for p in products:
                p.pop("purchase_price", None)
                p.pop("margin_pct", None)
    return jsonify({"ok": True, "products": products, "summary": summary})


@app.route("/api/store/move", methods=["POST"])
@login_required
@employee_blocked
def api_store_move():
    """Перенос основной склад → магазин (back=true — обратно). Только хозяин."""
    if not _store_on(db.get_shop(g.shop_id)):
        return jsonify({"ok": False, "error": "Склад магазина не включён"}), 403
    data = request.get_json(force=True) or {}
    lines = [(l.get("product_id"), l.get("qty")) for l in (data.get("lines") or []) if isinstance(l, dict)]
    res = db.move_to_store(g.shop_id, lines, back=bool(data.get("back")))
    if res.get("ok"):
        return jsonify(res)
    err = res.get("error")
    msg = {"empty": g.T.get("st_err_empty", "empty"), "bad_qty": g.T.get("st_err_qty", "bad qty"),
           "not_found": g.T.get("st_err_not_found", "not found")}.get(err)
    if err == "not_enough":
        msg = g.T.get("st_err_not_enough", "{name}: {n}").replace("{name}", res.get("name") or "") \
            .replace("{n}", f"{res.get('available'):g}")
    return jsonify({"ok": False, "error": msg or err}), 400


@app.route("/api/store/count/<int:product_id>", methods=["POST"])
@login_required
@employee_blocked
def api_store_count(product_id):
    """Пересчёт магазина по факту (найдено/пропало). Только хозяин."""
    if not _store_on(db.get_shop(g.shop_id)):
        return jsonify({"ok": False, "error": "Склад магазина не включён"}), 403
    data = request.get_json(force=True) or {}
    try:
        qty = float(data.get("qty"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": PRODUCT_EDIT_ERRORS["bad_qty"]}), 400
    ok, err = db.set_store_count(product_id, g.shop_id, qty, data.get("reason"))
    if not ok:
        return jsonify({"ok": False, "error": PRODUCT_EDIT_ERRORS.get(err, err)}), (404 if err == "not_found" else 400)
    return jsonify({"ok": True})


@app.route("/api/products", methods=["POST"])
@login_required
@employee_blocked
def api_create_product():
    denied = _warehouse_required()
    if denied:
        return denied
    data = request.get_json(force=True)
    try:
        category = data["category"]
        name = data["name"].strip()
        if not name:
            return jsonify({"ok": False, "error": "укажите название товара"}), 400
        if category == "other":
            unit = "pc" if data.get("unit") == "pc" else "l"
        else:
            unit = "pc" if category.startswith("filter_") else "l"
        sell_price = int(data["sell_price"]) if data.get("sell_price") not in (None, "") else None
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
        if g.is_branch:
            purchase_price = None  # филиал не вписывает цену закупки — это делает только главный аккаунт
        initial_stock = float(data["initial_stock"]) if data.get("initial_stock") not in (None, "") else 0
        purchase_currency = "USD" if data.get("purchase_currency") == "USD" and not g.is_branch else None
        purchase_usd = float(data["purchase_usd"]) if purchase_currency and data.get("purchase_usd") not in (None, "") else None
        if purchase_usd is not None and purchase_usd < 0:
            raise ValueError("bad price")
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    product = db.create_product(g.shop_id, category, name, unit, sell_price, purchase_price, initial_stock,
                                purchase_currency=purchase_currency, purchase_usd=purchase_usd)
    # новинка, заведённая прямо из заказа поставщику, сразу закрепляется за ним
    if data.get("supplier_id") not in (None, "") and not g.is_branch:
        try:
            if db.set_product_supplier(g.shop_id, product["id"], int(data["supplier_id"])):
                product["supplier_id"] = int(data["supplier_id"])
        except (TypeError, ValueError):
            pass
    return jsonify({"ok": True, "product": product})


PRODUCT_EDIT_ERRORS = {
    "not_found": "товар не найден",
    "empty_name": "укажите название",
    "duplicate": "товар с таким названием и типом уже есть на складе",
    "bad_price": "цена не может быть отрицательной",
    "bad_qty": "остаток не может быть отрицательным",
}


def _apply_product_edit(shop_id: int, product_id: int, data: dict, allow_purchase: bool):
    """Общая логика изменения товара — для своего склада и для склада филиала
    (главным аккаунтом). Цена закупки меняется только если allow_purchase.
    Остаток — отдельной корректировкой с записью в историю."""
    def _int(v):
        return int(round(float(v))) if v not in (None, "") else None
    try:
        name = data.get("name")
        sell_price = _int(data.get("sell_price"))
        purchase_price = _int(data.get("purchase_price")) if allow_purchase else None
        clear_purchase = allow_purchase and "purchase_price" in data and data.get("purchase_price") in (None, "")
        stock_qty = float(data["stock_qty"]) if data.get("stock_qty") not in (None, "") else None
        currency = data.get("purchase_currency") if allow_purchase and data.get("purchase_currency") in ("USD", "UZS") else None
        purchase_usd = float(data["purchase_usd"]) if currency == "USD" and data.get("purchase_usd") not in (None, "") else None
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "неверные данные"}), 400
    ok, err = db.update_product(product_id, shop_id, name=name, sell_price=sell_price,
                                purchase_price=purchase_price, clear_purchase_price=clear_purchase,
                                purchase_currency=currency, purchase_usd=purchase_usd)
    if not ok:
        return jsonify({"ok": False, "error": PRODUCT_EDIT_ERRORS.get(err, err)}), (404 if err == "not_found" else 400)
    if stock_qty is not None:
        ok, err = db.set_stock_count(product_id, shop_id, stock_qty, data.get("stock_reason"))
        if not ok:
            return jsonify({"ok": False, "error": PRODUCT_EDIT_ERRORS.get(err, err)}), 400
    return jsonify({"ok": True})


@app.route("/api/products/<int:product_id>", methods=["PUT"])
@login_required
@employee_blocked
def api_update_product(product_id):
    """Изменить товар своего склада. Филиал меняет название, цену продажи и
    остаток; цену закупки — только главный или самостоятельная точка."""
    return _apply_product_edit(g.shop_id, product_id, request.get_json(force=True), allow_purchase=not g.is_branch)


@app.route("/api/branches/<int:branch_id>/products/<int:product_id>", methods=["PUT"])
@login_required
@profit_blocked
def api_update_branch_product(branch_id, product_id):
    """Главный аккаунт меняет товар на складе своего филиала (включая закупку)."""
    if not db.is_branch_of(branch_id, g.shop_id):
        return jsonify({"ok": False, "error": "это не ваш филиал"}), 403
    return _apply_product_edit(branch_id, product_id, request.get_json(force=True), allow_purchase=True)


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
@login_required
@employee_blocked
def api_delete_product(product_id):
    ok = db.delete_product(product_id, g.shop_id)
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/products/<int:product_id>/restock", methods=["POST"])
@login_required
@employee_blocked
def api_restock_product(product_id):
    data = request.get_json(force=True)
    try:
        quantity = float(data["quantity"])
        if not (quantity > 0 and quantity < 10 ** 7):
            return jsonify({"ok": False, "error": "количество должно быть больше нуля"}), 400
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
        purchase_usd = float(data["purchase_usd"]) if data.get("purchase_usd") not in (None, "") else None
        if g.is_branch:
            purchase_price = None  # филиал не вписывает цену закупки при пополнении — только главный аккаунт
            purchase_usd = None
        restock_date = data.get("restock_date") or None
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    ok = db.restock_product(product_id, g.shop_id, quantity, purchase_price, restock_date, purchase_usd=purchase_usd)
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/warehouse/overview")
@login_required
@employee_blocked
def api_warehouse_overview():
    """Склад своей точки: товары с прогнозом + сводка. Филиалу закупочные
    цены и всё, что из них считается (стоимость, наценка), не отдаём."""
    denied = _warehouse_required()
    if denied:
        return denied
    result = db.get_warehouse_overview(g.shop_id)
    if not g.is_branch:
        result["summary"]["usd_reval"] = db.last_usd_revaluation(g.shop_id)
        result["summary"]["usd_setup_done"] = db.usd_setup_products(g.shop_id)["done"]
    if g.is_branch:
        for p in result["products"]:
            p.pop("purchase_price", None)
            p.pop("margin_pct", None)
        for k in ("stock_value", "retail_value", "potential_margin", "dead_value", "missing_price_count"):
            result["summary"].pop(k, None)
    result["ok"] = True
    return jsonify(result)


@app.route("/api/warehouse/movements")
@login_required
@employee_blocked
def api_warehouse_movements():
    moves = db.get_stock_movements(g.shop_id)
    if g.is_branch:
        for m in moves:
            m.pop("purchase_price", None)
    return jsonify(moves)


@app.route("/api/branches/<int:branch_id>/warehouse")
@login_required
@profit_blocked
def api_branch_warehouse(branch_id):
    """Главный смотрит склад своего филиала так же подробно, как свой:
    сводка, прогноз, закупочные цены, движение товара."""
    if not db.is_branch_of(branch_id, g.shop_id):
        return jsonify({"ok": False, "error": "это не ваш филиал"}), 403
    result = db.get_warehouse_overview(branch_id)
    result["movements"] = db.get_stock_movements(branch_id)
    branch = db.get_shop(branch_id)
    result["name"] = branch.get("shop_name") or branch["username"]
    result["ok"] = True
    return jsonify(result)


@app.route("/api/branches/<int:branch_id>/products/<int:product_id>/restock", methods=["POST"])
@login_required
@profit_blocked
def api_branch_restock(branch_id, product_id):
    """Главный пополняет товар на складе своего филиала (с ценой закупки)."""
    if not db.is_branch_of(branch_id, g.shop_id):
        return jsonify({"ok": False, "error": "это не ваш филиал"}), 403
    data = request.get_json(force=True)
    try:
        quantity = float(data["quantity"])
        if quantity <= 0:
            raise ValueError
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
        purchase_usd = float(data["purchase_usd"]) if data.get("purchase_usd") not in (None, "") else None
        restock_date = data.get("restock_date") or None
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "неверные данные"}), 400
    ok = db.restock_product(product_id, branch_id, quantity, purchase_price, restock_date, purchase_usd=purchase_usd)
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/warehouse/copy_catalog", methods=["POST"])
@login_required
@profit_blocked
def api_copy_catalog():
    """Скопировать товары главного в филиал (остаток 0, те же цены)."""
    data = request.get_json(force=True)
    try:
        branch_id = int(data["branch_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad_request"}), 400
    cats = [c for c in (data.get("categories") or []) if isinstance(c, str)] or None
    result = db.copy_catalog_to_branch(g.shop_id, branch_id, cats)
    return jsonify(result), (200 if result.get("ok") else 403)


@app.route("/api/warehouse/ship_plan")
@login_required
@profit_blocked
def api_ship_plan():
    try:
        from_id, to_id = int(request.args["from"]), int(request.args["to"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad_request"}), 400
    result = db.get_ship_plan(g.shop_id, from_id, to_id)
    return jsonify(result), (200 if result.get("ok") else 403)


@app.route("/api/warehouse/bulk_transfer", methods=["POST"])
@login_required
@profit_blocked
def api_bulk_transfer():
    """Накладная: много товаров из одной точки сети в другую одним действием."""
    data = request.get_json(force=True)
    try:
        result = db.bulk_transfer(g.shop_id, int(data["from_shop_id"]), int(data["to_shop_id"]), data.get("lines") or [])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad_request"}), 400
    return jsonify(result), (200 if result.get("ok") else 400)


IMPORT_CATEGORY_KEYS = ["fluid_0", "fluid_1", "fluid_2", "fluid_3", "fluid_4",
                        "filter_0", "filter_1", "filter_2", "filter_3", "other"]


def _import_category_names() -> dict:
    """Название типа (как пишут люди, на русском или узбекском) → ключ."""
    names = {}
    for texts in i18n.TEXTS.values():
        for k in IMPORT_CATEGORY_KEYS[:-1]:
            if texts.get(k):
                names[texts[k].strip().lower()] = k
        other = (texts.get("wh_category_other") or "").replace("➕", "").strip().lower()
        if other:
            names[other] = "other"
            names[other.split("(")[0].strip()] = "other"
    for k in IMPORT_CATEGORY_KEYS:
        names[k] = k
    names.update({"прочее": "other", "другое": "other", "boshqa": "other"})
    return names


IMPORT_HEADER_HINTS = {
    "category": ("тип", "tur", "type", "категор"),
    "name": ("назв", "марк", "nom", "name", "tovar", "товар"),
    "unit": ("един", "birlik", "unit", "ед."),
    "sell_price": ("продаж", "sotish", "sell"),
    "purchase_price": ("закуп", "xarid", "purchase", "приход"),
    "quantity": ("колич", "остат", "miqdor", "qoldiq", "qty", "quantity"),
}


@app.route("/api/products/import_template")
@login_required
@employee_blocked
def api_import_template():
    """Шаблон Excel для загрузки склада: колонки, список типов в выпадающем
    меню и лист с примером. Филиалу колонку цены закупки не даём."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    T = g.T
    headers = [T["imp_col_type"], T["imp_col_name"], T["imp_col_unit"], T["imp_col_sell"]]
    if not g.is_branch:
        headers.append(T["imp_col_buy"])
    headers.append(T["imp_col_qty"])
    type_names = [T[k] for k in IMPORT_CATEGORY_KEYS[:-1]] + [T["imp_type_other"]]

    wb = Workbook()
    ws = wb.active
    ws.title = T["imp_sheet_goods"]
    fill = PatternFill(start_color="0F52BA", end_color="0F52BA", fill_type="solid")
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    widths = [22, 34, 10, 16, 16, 12]
    for i, w in enumerate(widths[:len(headers)], start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"

    lists = wb.create_sheet(T["imp_sheet_types"])
    for i, n in enumerate(type_names, start=1):
        lists.cell(row=i, column=1, value=n)
    lists.cell(row=1, column=3, value="л")
    lists.cell(row=2, column=3, value="шт")
    lists.column_dimensions["A"].width = 26
    dv = DataValidation(type="list", formula1=f"='{T['imp_sheet_types']}'!$A$1:$A${len(type_names)}", allow_blank=True)
    dv_unit = DataValidation(type="list", formula1=f"='{T['imp_sheet_types']}'!$C$1:$C$2", allow_blank=True)
    ws.add_data_validation(dv)
    ws.add_data_validation(dv_unit)
    dv.add("A2:A2000")
    dv_unit.add("C2:C2000")

    ex = wb.create_sheet(T["imp_sheet_example"])
    for i, h in enumerate(headers, start=1):
        ex.cell(row=1, column=i, value=h).font = Font(bold=True)
    sample = [[T["fluid_0"], "MITANOL 5W-30 SL", "л", 100000, 80000, 200],
              [T["filter_0"], "ECO FILTER Spark", "шт", 30000, 12000, 50],
              [T["imp_type_other"], "Освежитель воздуха", "шт", 10000, 5000, 20]]
    for r_i, row in enumerate(sample, start=2):
        if g.is_branch:
            row = row[:4] + row[5:]
        for c_i, v in enumerate(row, start=1):
            ex.cell(row=r_i, column=c_i, value=v)
    for i, w in enumerate(widths[:len(headers)], start=1):
        ex.column_dimensions[chr(64 + i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="oilbook_sklad_shablon.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _read_import_sheet(file_storage):
    """Читает первый лист Excel: колонки узнаём по заголовкам (на русском или
    узбекском), поэтому подойдёт и шаблон, и свой прайс с похожими колонками."""
    from openpyxl import load_workbook
    from itertools import islice
    wb = load_workbook(file_storage, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    # читаем не больше 5001 строки и 40 колонок: файл в пару МБ может
    # содержать миллионы сжатых строк, и list() по всему листу съел бы память
    rows = list(islice(ws.iter_rows(values_only=True, max_col=40), 5001))
    if not rows:
        return None, "empty"
    header = [str(h or "").strip().lower() for h in rows[0]]
    colmap = {}
    for field, hints in IMPORT_HEADER_HINTS.items():
        for idx, h in enumerate(header):
            if idx in colmap.values():
                continue
            if any(hint in h for hint in hints):
                colmap[field] = idx
                break
    if "name" not in colmap or "category" not in colmap:
        return None, "no_columns"
    raw = []
    for r in rows[1:5001]:
        raw.append({f: (r[i] if i < len(r) else None) for f, i in colmap.items()})
    return raw, None


@app.route("/api/products/import_preview", methods=["POST"])
@login_required
@employee_blocked
def api_import_preview():
    denied = _warehouse_required()
    if denied:
        return denied
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "no_file"}), 400
    try:
        raw, err = _read_import_sheet(f)
    except Exception:
        return jsonify({"ok": False, "error": "bad_file"}), 400
    if err:
        return jsonify({"ok": False, "error": err}), 400
    rows = db.parse_import_rows(raw, _import_category_names())
    existing = {(p["category"], " ".join(p["name"].upper().split())) for p in db.list_products(g.shop_id)}
    for r in rows:
        r["exists"] = bool(r.get("category")) and (r["category"], r["name"].upper()) in existing
        if g.is_branch:
            r["purchase_price"] = None
    return jsonify({"ok": True, "rows": rows})


@app.route("/api/products/import_apply", methods=["POST"])
@login_required
@employee_blocked
def api_import_apply():
    denied = _warehouse_required()
    if denied:
        return denied
    data = request.get_json(force=True)
    raw = data.get("rows") or []
    if not isinstance(raw, list) or len(raw) > 5000:
        return jsonify({"ok": False, "error": "bad_request"}), 400
    # всё проверяем заново на сервере — не доверяем тому, что прислал браузер
    rows = db.parse_import_rows(raw, _import_category_names())
    result = db.apply_import(g.shop_id, rows, allow_purchase=not g.is_branch)
    result["skipped_errors"] = sum(1 for r in rows if r["errors"])
    return jsonify(result)


@app.route("/api/warehouse/network")
@login_required
@profit_blocked
def api_warehouse_network():
    """Остатки всех складов сети — только для главного аккаунта."""
    result = db.get_network_stock_matrix(g.shop_id)
    result["ok"] = True
    return jsonify(result)


@app.route("/api/warehouse/transfer", methods=["POST"])
@login_required
@profit_blocked
def api_warehouse_transfer():
    """Перемещение товара между складами своей сети (делает только главный)."""
    data = request.get_json(force=True)
    try:
        result = db.transfer_stock(g.shop_id, int(data["from_shop_id"]), int(data["product_id"]),
                                   int(data["to_shop_id"]), float(data["quantity"]))
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "bad_request"}), 400
    return jsonify(result), (200 if result.get("ok") else 400)


@app.route("/api/restock_history")
@login_required
@employee_blocked
def api_restock_history():
    history = db.get_restock_history(g.shop_id)
    if g.is_branch:
        for r in history:
            r.pop("purchase_price", None)
    return jsonify(history)


# ---------- Поставщики и заказы поставщику (главная / самостоятельная точка) ----------

def _orders_allowed():
    """Заказы ведёт только главная или самостоятельная точка со складом:
    филиалу и сотруднику закрыто (profit_blocked), без склада — тоже."""
    return _warehouse_required()


@app.route("/api/suppliers")
@login_required
@profit_blocked
def api_list_suppliers():
    denied = _orders_allowed()
    if denied:
        return denied
    if request.args.get("archived"):
        return jsonify({"ok": True, "suppliers": [_public_supplier(x) for x in db.list_suppliers(g.shop_id, archived=True)]})
    sups = db.list_suppliers(g.shop_id)
    with db.get_conn() as conn:
        archived = conn.execute("SELECT COUNT(*) FROM suppliers WHERE shop_id=? AND is_active=0", (g.shop_id,)).fetchone()[0]
    return jsonify({"ok": True, "suppliers": [_public_supplier(x) for x in sups],
                    "totals": db.supplier_totals(sups), "archived_count": archived,
                    "usd_rate": db.shop_usd_rate(g.shop_id),
                    "bot_ready": bool(BOT_TOKEN and BOT_USERNAME)})


@app.route("/api/suppliers/<int:supplier_id>/restore", methods=["POST"])
@login_required
@profit_blocked
def api_restore_supplier(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    result = db.restore_supplier(g.shop_id, supplier_id)
    return jsonify(result), (200 if result.get("ok") else (404 if result.get("error") == "not_found" else 400))


def _public_supplier(sup):
    """Поставщик для интерфейса: вместо chat_id и токена — признак «бот
    подключён» и ссылка для подключения."""
    if not sup:
        return None
    sup = dict(sup)
    sup["tg_connected"] = bool(sup.pop("tg_chat_id", None))
    sup.pop("link_token", None)
    return sup


@app.route("/api/suppliers/<int:supplier_id>/tg_link")
@login_required
@profit_blocked
def api_supplier_tg_link(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    if not BOT_USERNAME:
        return jsonify({"ok": False, "error": "no_bot"}), 400
    token = db.supplier_link_token(g.shop_id, supplier_id)
    if not token:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "link": f"https://t.me/{BOT_USERNAME}?start=sup_{token}"})


@app.route("/api/suppliers/<int:supplier_id>/tg_unlink", methods=["POST"])
@login_required
@profit_blocked
def api_supplier_tg_unlink(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    if not db.unlink_supplier_telegram(g.shop_id, supplier_id):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True})


@app.route("/api/suppliers", methods=["POST"])
@app.route("/api/suppliers/<int:supplier_id>", methods=["PUT"])
@login_required
@profit_blocked
def api_save_supplier(supplier_id=None):
    denied = _orders_allowed()
    if denied:
        return denied
    ok, err, sid = db.save_supplier(g.shop_id, request.get_json(force=True) or {}, supplier_id)
    if not ok:
        return jsonify({"ok": False, "error": err}), (404 if err == "not_found" else 400)
    return jsonify({"ok": True, "id": sid})


@app.route("/api/suppliers/<int:supplier_id>", methods=["DELETE"])
@login_required
@profit_blocked
def api_delete_supplier(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    if not db.delete_supplier(g.shop_id, supplier_id):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True})


@app.route("/api/suppliers/<int:supplier_id>/products", methods=["POST"])
@login_required
@profit_blocked
def api_assign_supplier_products(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    data = request.get_json(force=True) or {}
    result = db.assign_supplier_products(g.shop_id, supplier_id, data.get("product_ids") or [])
    return jsonify(result), (200 if result.get("ok") else 404)


def _supplier_arg(raw):
    if raw in (None, "", "none", "null", "0", 0):
        return None
    return int(raw)


@app.route("/api/orders")
@login_required
@profit_blocked
def api_list_orders():
    denied = _orders_allowed()
    if denied:
        return denied
    try:
        limit = max(1, min(500, int(request.args.get("limit") or 40)))
    except ValueError:
        limit = 40
    return jsonify({"ok": True, "orders": db.list_orders(g.shop_id, limit), "total": db.count_orders(g.shop_id),
                    "has_branches": len(db.order_network(g.shop_id)) > 1})


@app.route("/api/orders/suggest")
@login_required
@profit_blocked
def api_suggest_order():
    denied = _orders_allowed()
    if denied:
        return denied
    try:
        supplier_id = _supplier_arg(request.args.get("supplier_id"))
    except ValueError:
        return jsonify({"ok": False, "error": "bad_request"}), 400
    if supplier_id and not db.get_supplier(g.shop_id, supplier_id):
        return jsonify({"ok": False, "error": "no_supplier"}), 404
    return jsonify(db.suggest_order(g.shop_id, supplier_id))


@app.route("/api/orders/<int:order_id>")
@login_required
@profit_blocked
def api_get_order(order_id):
    denied = _orders_allowed()
    if denied:
        return denied
    order = db.get_order(g.shop_id, order_id)
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404
    shop = db.get_shop(g.shop_id) or {}
    order["shop"] = {"name": shop.get("shop_name") or shop.get("username"),
                     "address": shop.get("address"), "phone": shop.get("phone")}
    order["supplier"] = _public_supplier(order.get("supplier"))
    order["ok"] = True
    return jsonify(order)


def _order_message(order, shop) -> str:
    """Текст заказа для поставщика (на языке точки): только товары и
    количество — без цен и без разбивки по филиалам."""
    T = i18n.get_texts(shop.get("language") or "ru")
    def q(x):
        x = round(float(x or 0), 2)
        return f"{x:g}".replace(".", ",")
    stamp = (order.get("sent_at") or order.get("created_at") or "")[:10]
    date = f"{stamp[8:10]}.{stamp[5:7]}.{stamp[0:4]}" if len(stamp) == 10 else ""
    lines = [f"📦 {T['ord_title_n'].replace('{n}', str(order['number']))} — {shop.get('shop_name') or shop.get('username')}", date, ""]
    n = 0
    for ln in order["lines"]:
        if (ln.get("qty_ordered") or 0) > 0:
            n += 1
            unit = T["unit_pc"] if ln["unit"] == "pc" else T["unit_l"]
            lines.append(f"{n}. {ln['name']} — {q(ln['qty_ordered'])} {unit}")
    tail = []
    if shop.get("address"):
        tail.append(f"{T['ord_msg_address']}: {shop['address']}")
    if shop.get("phone"):
        tail.append(f"{T['ord_msg_phone']}: {shop['phone']}")
    if tail:
        lines += [""] + tail
    return "\n".join(lines)


@app.route("/api/orders/<int:order_id>/send_tg", methods=["POST"])
@login_required
@profit_blocked
def api_order_send_tg(order_id):
    """Заказ уходит поставщику в Telegram от бота — если поставщик подключён
    (один раз нажал Start по своей ссылке). При успехе заказ = «отправлен»."""
    denied = _orders_allowed()
    if denied:
        return denied
    order = db.get_order(g.shop_id, order_id)
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if order["status"] not in ("draft", "sent"):
        return jsonify({"ok": False, "error": "bad_status"}), 400
    sup = order.get("supplier") or {}
    if not sup.get("tg_chat_id"):
        return jsonify({"ok": False, "error": "tg_not_connected"}), 400
    if not order.get("sent_at"):
        order["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not _send_telegram_message(sup["tg_chat_id"], _order_message(order, db.get_shop(g.shop_id) or {})):
        return jsonify({"ok": False, "error": "tg_failed"}), 502
    db.mark_order_sent(g.shop_id, order_id)
    return jsonify({"ok": True})


@app.route("/api/orders", methods=["POST"])
@app.route("/api/orders/<int:order_id>", methods=["PUT"])
@login_required
@profit_blocked
def api_save_order(order_id=None):
    denied = _orders_allowed()
    if denied:
        return denied
    data = request.get_json(force=True) or {}
    try:
        supplier_id = _supplier_arg(data.get("supplier_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad_request"}), 400
    result = db.save_order(g.shop_id, supplier_id, data.get("lines") or [], data.get("note"), order_id)
    if result.get("ok") and data.get("send"):
        db.mark_order_sent(g.shop_id, result["id"])
    return jsonify(result), (200 if result.get("ok") else 400)


def _order_action(fn, order_id, *args):
    denied = _orders_allowed()
    if denied:
        return denied
    result = fn(g.shop_id, order_id, *args)
    code = 200 if result.get("ok") else (404 if result.get("error") == "not_found" else 400)
    return jsonify(result), code


@app.route("/api/orders/<int:order_id>/sent", methods=["POST"])
@login_required
@profit_blocked
def api_order_sent(order_id):
    return _order_action(db.mark_order_sent, order_id)


@app.route("/api/orders/<int:order_id>", methods=["DELETE"])
@login_required
@profit_blocked
def api_cancel_order(order_id):
    return _order_action(db.cancel_order, order_id)


@app.route("/api/orders/<int:order_id>/receive", methods=["POST"])
@login_required
@profit_blocked
def api_receive_order(order_id):
    data = request.get_json(force=True) or {}
    resp, code = _order_action(db.receive_order, order_id, data.get("lines") or [])
    if code == 200 and data.get("paid_now"):
        # «Оплачено сразу» — долг по этому заказу сразу закрывается оплатой
        order = db.get_order(g.shop_id, order_id)
        amount = db.order_amount(g.shop_id, order_id)
        if order and order.get("supplier_id") and amount > 0:
            db.add_supplier_payment(g.shop_id, order["supplier_id"], "payment", amount,
                                    note=g.T["ord_title_n"].replace("{n}", str(order["number"])), order_id=order_id)
    return resp, code


@app.route("/api/suppliers/<int:supplier_id>/card")
@login_required
@profit_blocked
def api_supplier_card(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    try:
        offset = int(request.args.get("offset") or 0)
    except ValueError:
        offset = 0
    card = db.supplier_card(g.shop_id, supplier_id, request.args.get("year"), offset)
    if not card:
        return jsonify({"ok": False, "error": "not_found"}), 404
    card["supplier"] = _public_supplier(card["supplier"])
    card["usd_rate"] = db.shop_usd_rate(g.shop_id)
    card["ok"] = True
    return jsonify(card)


@app.route("/api/suppliers/<int:supplier_id>/payments", methods=["POST"])
@login_required
@profit_blocked
def api_supplier_payment(supplier_id):
    denied = _orders_allowed()
    if denied:
        return denied
    data = request.get_json(force=True) or {}
    result = db.add_supplier_payment(g.shop_id, supplier_id, data.get("kind") or "payment", data.get("amount"),
                                     data.get("date"), data.get("note"), currency=data.get("currency") or "UZS",
                                     amount_usd=data.get("amount_usd"), rate=data.get("rate"),
                                     method=data.get("method"), client_token=data.get("token"))
    return jsonify(result), (200 if result.get("ok") else (404 if result.get("error") == "not_found" else 400))


@app.route("/api/suppliers/<int:supplier_id>/payments/<int:payment_id>/cancel", methods=["POST"])
@app.route("/api/suppliers/<int:supplier_id>/payments/<int:payment_id>", methods=["DELETE"])
@login_required
@profit_blocked
def api_cancel_supplier_payment(supplier_id, payment_id):
    """Оплату не удаляем, а отменяем с причиной — запись остаётся в истории."""
    denied = _orders_allowed()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    if not db.cancel_supplier_payment(g.shop_id, supplier_id, payment_id, data.get("reason")):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True})


@app.route("/api/suppliers/<int:supplier_id>/statement.xlsx")
@login_required
@profit_blocked
def api_supplier_statement(supplier_id):
    """Акт сверки с поставщиком за период — Excel."""
    denied = _orders_allowed()
    if denied:
        return denied
    def _d(v):
        v = (v or "")[:10]
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            return None
    st = db.supplier_statement(g.shop_id, supplier_id, _d(request.args.get("from")), _d(request.args.get("to")))
    if not st:
        return jsonify({"ok": False, "error": "not_found"}), 404
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    T = g.T
    wb = Workbook()
    ws = wb.active
    ws.title = T["ss_sheet"]
    shop = db.get_shop(g.shop_id) or {}
    fmt_d = lambda d: f"{d[8:10]}.{d[5:7]}.{d[0:4]}" if d else ""
    period = f"{fmt_d(st['date_from']) or '…'} — {fmt_d(st['date_to']) or fmt_d(datetime.now().strftime('%Y-%m-%d'))}"
    ws.append([T["ss_title"]])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"{shop.get('shop_name') or shop.get('username') or ''} — {st['supplier']['name']}"])
    ws.append([f"{T['ss_period']}: {period}"])
    ws.append([])
    ws.append([T["ss_opening"], "", "", "", "", "", st["opening"]])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    head = [T["ss_date"], T["ss_op"], T["ss_debit"], T["ss_credit"], T["ss_rate"], T["ss_usd"], T["ss_balance"], T["ss_note"]]
    ws.append(head)
    hr = ws.max_row
    for c in range(1, len(head) + 1):
        ws.cell(hr, c).font = Font(bold=True, color="FFFFFF")
        ws.cell(hr, c).fill = PatternFill("solid", fgColor="0F52BA")
        ws.cell(hr, c).alignment = Alignment(wrap_text=True, vertical="center")
    methods = {"cash": T["sp_m_cash"], "card": T["sp_m_card"], "transfer": T["sp_m_transfer"]}
    for e in st["rows"]:
        if e["type"] == "order":
            op = T["ord_title_n"].replace("{n}", str(e["number"]))
        elif e["type"] == "payment":
            op = T["sd_payment"] + (f" ({methods[e['method']]})" if e.get("method") in methods else "")
        else:
            op = T["sd_charge"]
        pay = e["type"] == "payment"
        note = e.get("note") or ""
        if e.get("currency") == "USD" and e.get("amount_usd") is not None:
            note = (f"${e['amount_usd']:,.2f} " + note).strip()
        ws.append([fmt_d(e["date"]), op, None if pay else e["amount"], e["amount"] if pay else None,
                   e.get("usd_rate"), e.get("usd"), e["balance"], note])
    ws.append([])
    ws.append([T["ss_closing"], "", "", "", "", "", st["closing"]])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.cell(ws.max_row, 7).font = Font(bold=True)
    rate_now = db.shop_usd_rate(g.shop_id)
    if rate_now:
        ws.append([T["ss_closing_usd"].replace("{rate}", f"{rate_now:g}"), "", "", "", "", "", round(st["closing"] / rate_now, 2)])
    for row in ws.iter_rows(min_row=hr + 1):
        if len(row) >= 7 and row[2].value is not None or row[3].value is not None or row[6].value is not None:
            for idx in (2, 3, 6):
                row[idx].number_format = "#,##0"
            row[5].number_format = "#,##0.00"
            row[4].number_format = "#,##0.##"
    ws.cell(5, 7).number_format = "#,##0"
    for col, w in zip("ABCDEFGH", (12, 26, 16, 16, 10, 12, 16, 34)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe = "".join(ch for ch in st["supplier"]["name"] if ch.isalnum())[:30] or "supplier"
    return send_file(buf, as_attachment=True, download_name=f"akt_sverki_{safe}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/orders/<int:order_id>/distribute", methods=["POST"])
@login_required
@profit_blocked
def api_distribute_order(order_id):
    data = request.get_json(force=True) or {}
    return _order_action(db.distribute_order, order_id, data.get("lines") or [])


@app.route("/api/profit_stats")
@login_required
@profit_blocked
def api_profit_stats():
    res = db.get_profit_stats(g.shop_id)
    res["usd"] = db.profit_stats_usd(g.shop_id)
    return jsonify(res)


@app.route("/api/export")
@login_required
@employee_blocked
def api_export():
    import json
    data = db.export_shop_data(g.shop_id)
    if g.is_branch:
        # филиал не видит цену закупки — и в файле копии тоже
        for car in data.get("cars") or []:
            _strip_cost_price(car.get("oil_changes") or [])
    body = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"backup_shop_{g.shop_id}_{data['exported_at'][:10]}.json"
    return Response(
        body, mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.route("/api/export_excel")
@login_required
@employee_blocked
def api_export_excel():
    import io
    from datetime import datetime as _dt
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    rows = db.get_full_history_flat(g.shop_id)
    shop = db.get_shop(g.shop_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "История"

    headers = [
        "Дата", "Госномер", "Владелец", "Телефон", "Марка авто", "Модель",
        "Пробег, км", "Менять при, км", "Услуга", "Марка масла",
        "Итого, сум", "След. замена", "Заметки",
    ]
    header_font = Font(name="Arial", bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="3A5FCD", end_color="3A5FCD", fill_type="solid")
    for col_idx, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    body_font = Font(name="Arial", size=11)
    for row_idx, r in enumerate(rows, start=2):
        values = [
            r["change_date"], r["plate_number"], r["owner_name"] or "", r["owner_phone"] or "",
            r["car_brand"] or "", r["car_model"] or "", r["mileage"], r["next_mileage"],
            r["service_type"] or "", r["oil_brand"] or "", r["cost"], r["next_change_date"] or "",
            r["notes"] or "",
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = body_font
            if col_idx == 11 and value is not None:  # "Итого, сум"
                cell.number_format = "#,##0"

    widths = [12, 12, 20, 15, 14, 14, 12, 14, 22, 16, 13, 12, 24]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + col_idx)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    shop_name_part = (shop.get("shop_name") or "shop").replace(" ", "_") if shop else "shop"
    filename = f"{shop_name_part}_{_dt.now().strftime('%Y-%m-%d')}.xlsx"
    # Content-Disposition допускает только ASCII в filename="..." — название
    # точки почти всегда на кириллице, поэтому кодируем правильно (RFC 5987):
    # ASCII-заглушка для старых клиентов + filename*= с настоящим именем
    # в UTF-8 для всех современных браузеров.
    ascii_fallback = "history_export.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    return Response(
        buf.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}"
        }
    )


# ============ Админ-панель (платформа) ============

from admin_template import ADMIN_PAGE  # noqa: E402  (сам шаблон — в admin_template.py)
assert ADMIN_PAGE.count(_SW_SNIPPET) == 1
ADMIN_PAGE = ADMIN_PAGE.replace(_SW_SNIPPET, NET_GUARD_JS + _SW_SNIPPET, 1)

# ---------- Панель внутри Telegram (кнопка в боте → /tg) ----------
# Панель открывается как Telegram Mini App. Внутри Telegram: разворачиваем
# окно на весь экран, отключаем «закрытие свайпом вниз» (мешало листать),
# внешние ссылки открываем через Telegram, а файлы (Excel и т.п.) — скачать
# внутри Telegram нельзя, поэтому сервер присылает их в чат с ботом.
# Скрипт Telegram грузится только внутри Telegram — в браузере/приложении
# ничего не меняется. ВНИМАНИЕ: строка не raw — в JS без обратных слэшей.
TG_PANEL_JS = """<script>
(function () {
  var inTg = false;
  try {
    if (location.hash.indexOf('tgWebAppData') !== -1) sessionStorage.setItem('ob_tg', '1');
    inTg = !!(window.TelegramWebviewProxy || location.hash.indexOf('tgWebApp') !== -1 || sessionStorage.getItem('ob_tg') === '1');
  } catch (e) {}
  var DL_RE = /^[/](api[/]export(_excel)?|api[/]products[/]import_template|api[/]suppliers[/][0-9]+[/]statement[.]xlsx|api[/]admin[/]income[/]export|download[/]plate-agent[.]zip)$/;
  function tg() { var w = window.Telegram && window.Telegram.WebApp; return (w && w.initData) ? w : null; }
  window.obDownload = function (u) { if (!(tg() && route(u, false))) location.href = u; };
  if (!inTg) return;
  document.documentElement.classList.add('in-tg');
  var TXT = { wait: {{ T.tgdl_wait|tojson }}, sent: {{ T.tgdl_sent|tojson }}, fail: {{ T.tgdl_fail|tojson }} };

  function toast(text, ms) {
    var el = document.getElementById('obTgToast');
    if (!el) {
      el = document.createElement('div'); el.id = 'obTgToast';
      el.style.cssText = 'position:fixed;left:50%;bottom:calc(90px + env(safe-area-inset-bottom));transform:translateX(-50%);max-width:88%;background:#0A2540;color:#fff;padding:11px 16px;border-radius:12px;font:600 14px/1.35 -apple-system,Segoe UI,Roboto,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25);z-index:99999;text-align:center;transition:opacity .2s;';
      document.body.appendChild(el);
    }
    el.textContent = text; el.style.opacity = '1';
    clearTimeout(el._t); el._t = setTimeout(function () { el.style.opacity = '0'; }, ms || 3500);
  }
  var busy = false;
  function sendFile(path) {
    var w = tg();
    if (busy || !w) return;
    busy = true; toast(TXT.wait, 20000);
    fetch('/api/tg/send_file', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': w.initData },
      body: JSON.stringify({ path: path })
    }).then(function (r) { return r.json(); }).then(function (d) {
      var el = document.getElementById('obTgToast'); if (el) el.style.opacity = '0';
      var text = d.ok ? TXT.sent : (d.error || TXT.fail);
      try { w.HapticFeedback.notificationOccurred(d.ok ? 'success' : 'error'); } catch (e) {}
      try { w.showAlert(text); } catch (e) { toast(text, 6000); }
    }).catch(function () { toast(TXT.fail, 6000); }).then(function () { busy = false; });
  }
  // true — ссылку обработали сами (Telegram/файл в чат), false — пусть браузер
  function route(url, newWin) {
    var w = tg(); if (!w) return false;
    var a = document.createElement('a'); a.href = url;
    if (a.host === location.host) {
      if (DL_RE.test(a.pathname)) { sendFile(a.pathname + a.search); return true; }
      if (newWin) { w.openLink(a.href); return true; }
      return false;
    }
    if (a.hostname === 't.me' || a.hostname === 'telegram.me') { w.openTelegramLink(a.href); return true; }
    if (a.protocol === 'http:' || a.protocol === 'https:') { w.openLink(a.href); return true; }
    return false;  // tel:, mailto: и т.п. — как обычно
  }
  var origOpen = window.open;
  window.open = function (url) {
    try { if (url && route(String(url), true)) return null; } catch (e) {}
    return origOpen.apply(window, arguments);
  };
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var h = a.getAttribute('href') || '';
    if (!h || h.charAt(0) === '#' || h.indexOf('javascript:') === 0) return;
    try { if (route(a.href, a.target === '_blank')) { e.preventDefault(); e.stopPropagation(); } } catch (err) {}
  }, true);

  function setup() {
    var w = window.Telegram && window.Telegram.WebApp; if (!w) return;
    try { w.ready(); w.expand(); } catch (e) {}
    try { if (w.isVersionAtLeast('7.7')) w.disableVerticalSwipes(); } catch (e) {}
    try {
      var m = document.querySelector('meta[name=theme-color]');
      if (w.isVersionAtLeast('6.1')) {
        w.setHeaderColor(m ? m.content : '#0A2540');
        w.setBackgroundColor(getComputedStyle(document.body).backgroundColor || '#F1F5F9');
      }
    } catch (e) {}
  }
  if (window.Telegram && window.Telegram.WebApp) { setup(); return; }
  var s = document.createElement('script');
  s.src = 'https://telegram.org/js/telegram-web-app.js';
  s.onload = setup;
  document.head.appendChild(s);
})();
</script>
<style>html.in-tg .more-install, html.in-tg .tg-only-out { display:none !important; }
html.in-tg { color-scheme: light only; }</style>
"""
assert "\\" not in TG_PANEL_JS
assert PAGE.count("<!--__TG_PANEL_JS__-->") == 1
PAGE = PAGE.replace("<!--__TG_PANEL_JS__-->", TG_PANEL_JS, 1)
assert LOGIN_PAGE.count("</head>") == 1 and ADMIN_PAGE.count("</head>") == 1
LOGIN_PAGE = LOGIN_PAGE.replace("</head>", TG_PANEL_JS + "</head>", 1)
ADMIN_PAGE = ADMIN_PAGE.replace("</head>", TG_PANEL_JS + "</head>", 1)

# Заставка при запуске приложения с иконки (вариант 2: капля наполняется маслом).
# Показывается только в установленном приложении (standalone) и один раз за запуск:
# при переходах между страницами больше не появляется. Исчезает, когда страница
# загрузилась (но не раньше, чем капля наполнится), максимум через 10 секунд.
SPLASH_HTML = """
<script>
(function(){try{
  var sa=(window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||window.navigator.standalone===true;
  if(sa&&!sessionStorage.getItem('ob_splash')){sessionStorage.setItem('ob_splash','1');document.documentElement.classList.add('ob-sp');window.__obSpT=Date.now();}
}catch(e){}})();
</script>
<style>
#obSplash{display:none;position:fixed;inset:0;z-index:2147483000;background:#0A2540;transition:opacity .4s ease}
html.ob-sp #obSplash{display:block}
html.ob-sp body{overflow:hidden}
#obSplash.out{opacity:0;pointer-events:none}
#obSplash svg{position:absolute;left:50%;width:min(30.7vw,170px);height:auto;top:calc(50vh - min(17.05vw,94px));transform:translateX(-50%)}
#obSplash .obs-txt{position:absolute;left:0;right:0;text-align:center;top:calc(50vh + min(26.4vw,146px))}
#obSplash .obs-wm{font-family:'Sora',-apple-system,Segoe UI,Roboto,sans-serif;font-weight:800;font-size:34px;letter-spacing:-1px;opacity:0;animation:obsUp .5s 1.1s ease-out forwards}
#obSplash .obs-oil{color:#38BDF8}
#obSplash .obs-book{color:#fff}
#obSplash .obs-sub{font-size:13px;color:#8fa6c8;margin-top:8px;opacity:0;animation:obsUp .5s 1.4s ease-out forwards}
#obSplash .obs-lvl{transform:translateY(84px);animation:obsFill 1.6s .15s cubic-bezier(.35,.1,.3,1) forwards,obsBob 2.4s 1.75s ease-in-out infinite alternate}
#obSplash .obs-wave{animation:obsWave 1.1s linear infinite}
#obSplash .obs-wave2{animation:obsWave 1.7s linear infinite reverse}
@keyframes obsFill{from{transform:translateY(84px)}to{transform:translateY(10px)}}
@keyframes obsBob{from{transform:translateY(10px)}to{transform:translateY(17px)}}
@keyframes obsWave{to{transform:translateX(-60px)}}
@keyframes obsUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){ #obSplash *{animation-duration:.01s!important;animation-iteration-count:1!important}}
</style>
<div id="obSplash" aria-hidden="true">
  <svg viewBox="0 0 60 80">
    <defs><clipPath id="obsClip"><path d="M30 0C30 0 5 34 5 52a25 25 0 0050 0C55 34 30 0 30 0z"/></clipPath></defs>
    <path d="M30 0C30 0 5 34 5 52a25 25 0 0050 0C55 34 30 0 30 0z" fill="#00A8E8"/>
    <g clip-path="url(#obsClip)">
      <g class="obs-lvl">
        <path class="obs-wave2" d="M0 4q15-6 30 0t30 0 30 0 30 0V90H0z" fill="#FFD261" opacity=".6"/>
        <path class="obs-wave" d="M0 8q15-7 30 0t30 0 30 0 30 0V90H0z" fill="#F5B82E"/>
      </g>
    </g>
    <ellipse cx="20.9" cy="45.9" rx="5.5" ry="11" fill="#85D3F2"/>
  </svg>
  <div class="obs-txt">
    <div class="obs-wm"><span class="obs-oil">Oil</span><span class="obs-book">Book</span></div>
    <div class="obs-sub">{{ T.splash_loading }}</div>
  </div>
</div>
<script>
(function(){
  var el=document.getElementById('obSplash');
  if(!el||!document.documentElement.classList.contains('ob-sp'))return;
  var done=false;
  function hide(){
    if(done)return;done=true;
    el.classList.add('out');
    setTimeout(function(){document.documentElement.classList.remove('ob-sp');if(el.parentNode)el.parentNode.removeChild(el);},450);
  }
  function ready(){var left=1900-(Date.now()-(window.__obSpT||0));setTimeout(hide,left>0?left:0);}
  if(document.readyState==='complete')ready();else window.addEventListener('load',ready);
  setTimeout(hide,10000);
})();
</script>
"""


def _with_splash(page):
    assert page.count("<body>") >= 1
    return page.replace("<body>", "<body>" + SPLASH_HTML, 1)


LOGIN_PAGE = _with_splash(LOGIN_PAGE)
PAGE = _with_splash(PAGE)
ADMIN_PAGE = _with_splash(ADMIN_PAGE)


# Маршруты админ-панели (/admin, точки, филиалы, сотрудники, копии) —
# в admin_routes.py; он подключается в конце этого файла.


# Табло у входа, приём номеров от камеры и сканер номеров — в display.py.


# ======================================================================
# ПОДПИСКА: страница оплаты, приём чека, решения админа
# ======================================================================

def _fmt_sum(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _fmt_day(s) -> str:
    if not s:
        return "—"
    s = str(s)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return s


def _is_sub_owner() -> bool:
    """Платит только владелец главной точки (не филиал и не сотрудник)."""
    return not getattr(g, "is_employee", False) and not getattr(g, "is_branch", False)


def _sub_banner(shop):
    """Плашка над разделами панели: подписка скоро закончится / новый филиал
    ждёт оплаты. None — показывать нечего."""
    st = getattr(g, "sub", None) or db.subscription_state(shop)
    T = g.T
    owner = _is_sub_owner()
    n = st.get("days_left")
    if st.get("readonly"):
        if not owner:
            return {"text": T["ro_banner_staff"], "link": False, "ro": True}
        disc = db.first_month_offer(db.get_shop(st["head_id"]) or {}) if st.get("trial") else 0
        if st.get("trial") and disc:
            text = T["ro_banner_trial_owner"].format(d=disc)
        elif st.get("trial"):
            text = T["ro_banner_trial_plain"]
        else:
            text = T["ro_banner_owner"]
        return {"text": text, "link": True, "ro": True}
    if st.get("trial") and n is not None and n >= 0:
        # пробный период — плашка видна все дни пробного периода, владельцу — со ссылкой на оплату
        if owner:
            text = T["trial_banner_today"] if n == 0 else T["trial_banner_owner"].format(n=n + 1)
        else:
            text = T["trial_banner_staff_today"] if n == 0 else T["trial_banner_staff"].format(n=n + 1)
        return {"text": text, "link": owner}
    if not st.get("lifetime") and n is not None and 0 <= n <= 5:
        if owner:
            text = T["sub_banner_today"] if n == 0 else T["sub_banner_owner"].format(n=n)
        else:
            text = T["sub_banner_staff_today"] if n == 0 else T["sub_banner_staff"].format(n=n)
        return {"text": text, "link": owner}
    if owner:
        pending = [b for b in db.get_branches(g.shop_id) if b.get("is_active") and b.get("branch_pending")]
        if pending:
            names = ", ".join(b.get("shop_name") or b["username"] for b in pending)
            return {"text": T["sub_banner_branch_pending"].format(names=names), "link": True}
    return None


# Курс доллара, страница «Подписка», оплата по чеку и через Hamyon,
# решения админа по оплатам и «Доходы» — в subscription.py.


# Регистрация точек и реферальная программа «Пригласи друга» — в registration.py.


# ---------- Сотрудники: владелец точки управляет сам ----------
# Главная точка — своими, каждый филиал — своими (g.shop_id — сама точка).
# Сотрудник сюда не попадает (@employee_blocked). Админ платформы — через /api/admin.

_STAFF_LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


@app.route("/api/staff")
@login_required
@employee_blocked
def api_staff_list():
    emps = db.list_shop_employees(g.shop_id)
    try:
        bal = {c["employee_id"]: c["balance"] for c in db.list_staff_cash(g.shop_id)}
    except Exception as e:  # касса не должна ломать список сотрудников
        logger.warning(f"касса сотрудников: {e}")
        bal = {}
    for e in emps:
        e["cash_balance"] = bal.get(e["id"], 0)
    return jsonify({"ok": True, "employees": emps})


@app.route("/api/staff", methods=["POST"])
@login_required
@employee_blocked
def api_staff_create():
    data = request.get_json(force=True, silent=True) or {}
    T = g.T
    full_name = re.sub(r"\s+", " ", str(data.get("full_name") or "")).strip()[:60]
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if len(full_name) < 2:
        return jsonify({"ok": False, "field": "full_name", "error": T["staff_err_name"]}), 400
    if not _STAFF_LOGIN_RE.match(username):
        return jsonify({"ok": False, "field": "username", "error": T["staff_err_login"]}), 400
    if password and (len(password) < 6 or len(password) > 100):
        return jsonify({"ok": False, "field": "password", "error": T["staff_err_password"]}), 400
    result = db.create_shop_employee(g.shop_id, username, password=password or None, full_name=full_name)
    if not result:
        return jsonify({"ok": False, "field": "username", "error": T["staff_err_taken"]}), 400
    return jsonify({"ok": True, **result})


@app.route("/api/staff/<int:employee_id>/reset_password", methods=["POST"])
@login_required
@employee_blocked
def api_staff_reset_password(employee_id):
    new_password = db.reset_shop_employee_password(employee_id, g.shop_id)
    if not new_password:
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    return jsonify({"ok": True, "password": new_password})


@app.route("/api/staff/<int:employee_id>/active", methods=["POST"])
@login_required
@employee_blocked
def api_staff_set_active(employee_id):
    active = bool((request.get_json(force=True, silent=True) or {}).get("active"))
    if not db.set_shop_employee_active(employee_id, g.shop_id, active):
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    return jsonify({"ok": True, "active": active})


@app.route("/api/staff/<int:employee_id>", methods=["DELETE"])
@login_required
@employee_blocked
def api_staff_delete(employee_id):
    ok = db.delete_shop_employee(employee_id, g.shop_id)
    if ok == "has_cash":
        return jsonify({"ok": False, "error": g.T["cash_err_delete"]}), 400
    if not ok:
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    return jsonify({"ok": True})


# ---------- Касса сотрудника ----------
# Сотрудник видит только свою кассу; принимает кассу владелец точки
# (главная, самостоятельная или филиал — у своих сотрудников).

@app.route("/api/cash/my")
@login_required
def api_cash_my():
    if not g.is_employee or not g.employee_id:
        return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
    return jsonify({"ok": True,
                    "cash": db.get_employee_cash(g.shop_id, g.employee_id),
                    "entries": db.employee_cash_entries(g.shop_id, g.employee_id, limit=60),
                    "history": db.list_cash_handovers(g.shop_id, g.employee_id, limit=10)})


@app.route("/api/cash/staff")
@login_required
@employee_blocked
def api_cash_staff():
    return jsonify({"ok": True, "staff": db.list_staff_cash(g.shop_id)})


@app.route("/api/cash/staff/<int:employee_id>")
@login_required
@employee_blocked
def api_cash_staff_one(employee_id):
    if not any(e["id"] == employee_id for e in db.list_shop_employees(g.shop_id)):
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    return jsonify({"ok": True,
                    "cash": db.get_employee_cash(g.shop_id, employee_id),
                    "entries": db.employee_cash_entries(g.shop_id, employee_id, limit=100),
                    "history": db.list_cash_handovers(g.shop_id, employee_id, limit=30)})


@app.route("/api/cash/staff/<int:employee_id>/accept", methods=["POST"])
@login_required
@employee_blocked
def api_cash_accept(employee_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        expected = int(data.get("expected"))
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": g.T["cash_err_amount"]}), 400
    res = db.accept_cash_handover(g.shop_id, employee_id, expected, amount, data.get("note"))
    err = res.get("error")
    if err == "not_found":
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    if err == "changed":
        return jsonify({"ok": False, "error": "changed", "balance": res["balance"]}), 409
    if err == "empty":
        return jsonify({"ok": False, "error": g.T["cash_err_empty"]}), 400
    if err:
        return jsonify({"ok": False, "error": g.T["cash_err_amount"]}), 400
    return jsonify(res)


@app.route("/api/cash/handover/<int:handover_id>/cancel", methods=["POST"])
@login_required
@employee_blocked
def api_cash_cancel(handover_id):
    res = db.cancel_cash_handover(g.shop_id, handover_id)
    if res.get("error") == "not_last":
        return jsonify({"ok": False, "error": g.T["cash_err_not_last"]}), 400
    if res.get("error"):
        return jsonify({"ok": False, "error": g.T["cash_err_not_found"]}), 404
    return jsonify(res)


# ---------- Команда: рейтинг, зарплата, награды ----------
# Владелец точки — своих сотрудников; главная точка — ещё и сотрудников
# своих филиалов (параметр shop). Сотрудник видит рейтинг (очки и замены,
# без чужих денег) и только СВОЮ зарплату.

def _team_target_shop(raw):
    """Точка, с которой работает владелец: своя или филиал главной. None — нельзя."""
    if g.is_employee:
        return None
    try:
        sid = int(raw) if raw not in (None, "", "null") else g.shop_id
    except (TypeError, ValueError):
        return None
    if sid == g.shop_id:
        return sid
    if not g.is_branch and db.is_branch_of(sid, g.shop_id):
        return sid
    return None


def _team_period_arg(raw):
    """Месяц 'ГГГГ-ММ'; будущие месяцы не принимаем (там нечего считать и платить)."""
    p = str(raw or "") or db.team_current_period()
    if not db.team_period_bounds(p) or p > db.team_current_period():
        return None
    return p


def _team_shops_list():
    shop = db.get_shop(g.shop_id) or {}
    out = [{"id": g.shop_id, "name": shop.get("shop_name") or shop.get("username") or ""}]
    if not g.is_branch and not g.is_employee:
        out += [{"id": b["id"], "name": b.get("shop_name") or b.get("username") or ""}
                for b in db.get_branches(g.shop_id)]
    return out


@app.route("/api/team")
@login_required
def api_team():
    period = _team_period_arg(request.args.get("period"))
    if not period:
        return jsonify({"ok": False, "error": g.T["team_err"]}), 400
    if g.is_employee:
        if not g.employee_id:
            return jsonify({"ok": False, "error": "недоступно"}), 403
        res = db.team_overview(g.shop_id, period, with_money=False, only_employee=g.employee_id)
        res["my_badges"] = db.team_badges(g.shop_id, g.employee_id)
        return jsonify({"ok": True, **res})
    sid = _team_target_shop(request.args.get("shop"))
    if not sid:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    res = db.team_overview(sid, period, with_money=True)
    return jsonify({"ok": True, "shop_id": sid, "shops": _team_shops_list(), **res})


@app.route("/api/team/network")
@login_required
@employee_blocked
def api_team_network():
    if g.is_branch:
        return jsonify({"ok": False, "error": "только для главной точки"}), 403
    period = _team_period_arg(request.args.get("period"))
    if not period:
        return jsonify({"ok": False, "error": g.T["team_err"]}), 400
    res = db.team_network_board(g.shop_id, period)
    return jsonify({"ok": True, "shops": _team_shops_list(),
                    "points_rule": {"service": db.TEAM_PTS_SERVICE, "filter": db.TEAM_PTS_FILTER,
                                    "repeat": db.TEAM_PTS_REPEAT}, **res})


@app.route("/api/team/emp/<int:employee_id>")
@login_required
@employee_blocked
def api_team_emp(employee_id):
    sid = _team_target_shop(request.args.get("shop"))
    period = _team_period_arg(request.args.get("period"))
    if not sid or not period:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    ov = db.team_overview(sid, period, with_money=True)
    row = next((r for r in ov.get("board", []) if r["id"] == employee_id), None)
    emp = next((e for e in db.list_shop_employees_pay(sid, period) if e["id"] == employee_id), None)
    if not emp:
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    if not row:  # выключенный без замен в этом месяце — всё равно показываем
        ov2 = db.team_overview(sid, period, with_money=True, include_all=True)
        row = next((r for r in ov2.get("board", []) if r["id"] == employee_id), None)
    return jsonify({"ok": True, "row": row, "emp": emp, "settings": ov["settings"],
                    "ops": db.list_salary_ops(sid, employee_id), "badges": db.team_badges(sid, employee_id)})


def _num_or_none(v, cast=int, lo=0, hi=10 ** 10):
    if v in (None, ""):
        return None
    try:
        n = cast(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        raise ValueError
    if n < lo or n > hi:
        raise ValueError
    return n


@app.route("/api/team/emp/<int:employee_id>/pay_settings", methods=["POST"])
@login_required
@employee_blocked
def api_team_pay_settings(employee_id):
    data = request.get_json(force=True, silent=True) or {}
    sid = _team_target_shop(data.get("shop"))
    period = _team_period_arg(data.get("period"))
    if not sid or not period:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    try:
        fixed = _num_or_none(data.get("salary_fixed"))
        pg = _num_or_none(data.get("pct_goods"), float, 0, 100)
        pw = _num_or_none(data.get("pct_work"), float, 0, 100)
        plan = _num_or_none(data.get("plan_services"), int, 0, 100000)
        plan_bonus = _num_or_none(data.get("plan_bonus"))
    except ValueError:
        return jsonify({"ok": False, "error": g.T["team_err_values"]}), 400
    ok = db.save_employee_pay(sid, employee_id, data.get("position"), fixed,
                              round(pg, 2) if pg else None, round(pw, 2) if pw else None,
                              plan or None, plan_bonus or None, period=period)
    if not ok:
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    return jsonify({"ok": True})


@app.route("/api/team/settings", methods=["POST"])
@login_required
@employee_blocked
def api_team_settings():
    data = request.get_json(force=True, silent=True) or {}
    sid = _team_target_shop(data.get("shop"))
    period = _team_period_arg(data.get("period"))
    if not sid or not period:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    try:
        positions = {k: _num_or_none((data.get("positions") or {}).get(k)) or 0 for k in db.TEAM_POSITIONS}
        top_bonus = _num_or_none(data.get("top_bonus")) or 0
    except ValueError:
        return jsonify({"ok": False, "error": g.T["team_err_values"]}), 400
    return jsonify({"ok": True, "settings": db.save_team_settings(sid, positions, top_bonus, period=period)})


@app.route("/api/team/emp/<int:employee_id>/op", methods=["POST"])
@login_required
@employee_blocked
def api_team_op(employee_id):
    data = request.get_json(force=True, silent=True) or {}
    sid = _team_target_shop(data.get("shop"))
    period = _team_period_arg(data.get("period"))
    if not sid or not period:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": g.T["team_err_amount"]}), 400
    if abs(amount) > 10 ** 10:
        return jsonify({"ok": False, "error": g.T["team_err_amount"]}), 400
    kind = data.get("kind")
    emp = next((e for e in db.list_shop_employees(sid) if e["id"] == employee_id), None)
    if not emp:
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    label = g.T["team_exp_label"].format(name=emp.get("full_name") or emp.get("username"),
                                         period=period[5:7] + "." + period[:4])
    res = db.add_salary_op(sid, employee_id, period, kind, amount, data.get("note"),
                           expense_label=label)
    if res.get("error") == "not_found":
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    if res.get("error"):
        return jsonify({"ok": False, "error": g.T["team_err_amount"]}), 400
    return jsonify(res)


@app.route("/api/team/op/<int:op_id>/cancel", methods=["POST"])
@login_required
@employee_blocked
def api_team_op_cancel(op_id):
    data = request.get_json(force=True, silent=True) or {}
    sid = _team_target_shop(data.get("shop"))
    if not sid:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    res = db.cancel_salary_op(sid, op_id)
    if res.get("error"):
        return jsonify({"ok": False, "error": g.T["cash_err_not_found"]}), 404
    return jsonify(res)


@app.route("/api/team/masters")
@login_required
def api_team_masters():
    return jsonify({"ok": True, "masters": db.team_masters(g.shop_id)})


@app.route("/api/team/certificate")
@login_required
@employee_blocked
def api_team_certificate():
    sid = _team_target_shop(request.args.get("shop"))
    period = _team_period_arg(request.args.get("period"))
    if not sid or not period:
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    try:
        emp_id = int(request.args.get("emp"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    ov = db.team_overview(sid, period, with_money=False)
    row = next((r for r in ov.get("board", []) if r["id"] == emp_id), None)
    if not row or row.get("place") != 1:
        return jsonify({"ok": False, "error": g.T["team_cert_none"]}), 400
    shop = db.get_shop(sid) or {}
    pdf = _team_certificate_pdf(row, shop.get("shop_name") or shop.get("username") or "", period, g.T)
    fname = f"OilBook_{period}_{row['id']}.pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"', "Cache-Control": "no-store"})


def _team_certificate_pdf(row, shop_name, period, T) -> bytes:
    import io
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    _register_pdf_fonts()
    buf = io.BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(W, H))
    blue, dark, gold, grey = HexColor("#0F52BA"), HexColor("#0A2540"), HexColor("#D97706"), HexColor("#64748B")
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setStrokeColor(blue)
    c.setLineWidth(6)
    c.rect(22, 22, W - 44, H - 44, stroke=1, fill=0)
    c.setStrokeColor(gold)
    c.setLineWidth(1.5)
    c.rect(34, 34, W - 68, H - 68, stroke=1, fill=0)
    c.setFillColor(blue)
    c.setFont("DejaVuSans-Bold", 22)
    c.drawString(60, H - 80, "Oil")
    c.setFillColor(dark)
    c.drawString(60 + c.stringWidth("Oil", "DejaVuSans-Bold", 22), H - 80, "Book")
    c.setFillColor(grey)
    c.setFont("DejaVuSans", 11)
    c.drawRightString(W - 60, H - 78, shop_name[:60])
    c.setFillColor(dark)
    c.setFont("DejaVuSans-Bold", 46)
    c.drawCentredString(W / 2, H - 175, T["team_cert_title"])
    c.setFillColor(grey)
    c.setFont("DejaVuSans", 15)
    c.drawCentredString(W / 2, H - 210, T["team_cert_sub"])
    name = row["name"][:40]
    size = 40 if len(name) <= 22 else 30
    c.setFillColor(blue)
    c.setFont("DejaVuSans-Bold", size)
    c.drawCentredString(W / 2, H - 275, name)
    c.setStrokeColor(gold)
    c.setLineWidth(2)
    c.line(W / 2 - 170, H - 292, W / 2 + 170, H - 292)
    c.setFillColor(dark)
    c.setFont("DejaVuSans-Bold", 17)
    c.drawCentredString(W / 2, H - 330, T["team_cert_reason"])
    months = str(T["team_months"]).split(",")
    try:
        mname = months[int(period[5:7]) - 1] + " " + period[:4]
    except (ValueError, IndexError):
        mname = period
    c.setFont("DejaVuSans", 15)
    c.drawCentredString(W / 2, H - 358, mname)
    c.setFillColor(grey)
    c.setFont("DejaVuSans", 13)
    c.drawCentredString(W / 2, H - 386, T["team_cert_stats"].format(services=row["services"], points=row["points"]))
    # медаль
    cx, cy = W / 2, 108
    c.setFillColor(gold)
    c.circle(cx, cy, 34, stroke=0, fill=1)
    c.setFillColor(HexColor("#FDE68A"))
    c.circle(cx, cy, 26, stroke=0, fill=1)
    c.setFillColor(HexColor("#78350F"))
    c.setFont("DejaVuSans-Bold", 28)
    c.drawCentredString(cx, cy - 10, "1")
    c.setFillColor(grey)
    c.setFont("DejaVuSans", 10)
    c.drawString(60, 52, "oilbook.uz")
    c.drawRightString(W - 60, 52, datetime.now().strftime("%d.%m.%Y"))
    c.showPage()
    c.save()
    return buf.getvalue()


def _master_arg(raw):
    """«Мастер» из формы замены — только активный сотрудник этой же точки."""
    if raw in (None, "", 0, "0"):
        return None
    return int(raw) if db.is_shop_employee(g.shop_id, raw) else None


# ---------- «Моя точка»: контакты и локация для клиентов в боте ----------
# Главная точка правит себя и свои филиалы, филиал — только себя,
# сотрудник — ничего (employee_blocked).

def _shop_contacts(shop: dict) -> dict:
    return {"id": shop["id"], "name": shop.get("shop_name") or shop.get("username"),
            "is_branch": shop.get("role") == "branch",
            "phone": shop.get("phone") or "", "address": shop.get("address") or "",
            "hours": shop.get("hours") or "", "lat": shop.get("lat"), "lon": shop.get("lon"),
            # токен табло/сканера — только своей точке и её владельцу
            "anpr_token": shop.get("anpr_token") or "",
            "offer_pct": int(shop.get("offer_pct") or 0)}


def _can_edit_contacts(shop_id: int) -> bool:
    if shop_id == g.shop_id:
        return True
    return not g.is_branch and db.is_branch_of(shop_id, g.shop_id)


@app.route("/api/my_shop")
@login_required
@employee_blocked
def api_my_shop():
    shops = [db.get_shop(g.shop_id)]
    if not g.is_branch:
        shops += db.get_branches(g.shop_id)
    return jsonify({"ok": True, "shops": [_shop_contacts(s) for s in shops if s]})


@app.route("/api/my_shop/<int:shop_id>", methods=["POST"])
@login_required
@employee_blocked
def api_my_shop_save(shop_id):
    if not _can_edit_contacts(shop_id):
        return jsonify({"ok": False, "error": "это не ваша точка"}), 403
    data = request.get_json(force=True, silent=True) or {}

    def text(key, limit):
        return re.sub(r"\s+", " ", str(data.get(key) or "")).strip()[:limit] or None

    lat = lon = None
    if data.get("lat") not in (None, "") or data.get("lon") not in (None, ""):
        try:
            lat, lon = float(data.get("lat")), float(data.get("lon"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": g.T["myshop_bad_location"]}), 400
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            return jsonify({"ok": False, "error": g.T["myshop_bad_location"]}), 400
        lat, lon = round(lat, 6), round(lon, 6)
    try:
        offer_pct = int(data.get("offer_pct") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": g.T["myshop_bad_offer"]}), 400
    if not 0 <= offer_pct <= 50:
        return jsonify({"ok": False, "error": g.T["myshop_bad_offer"]}), 400
    ok = db.update_shop_contacts(shop_id, phone=text("phone", 40), address=text("address", 200),
                                 hours=text("hours", 80), lat=lat, lon=lon, offer_pct=offer_pct)
    if not ok:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    return jsonify({"ok": True, "shop": _shop_contacts(db.get_shop(shop_id))})


@app.route("/api/admin/employees/<int:employee_id>/active", methods=["POST"])
@admin_required
def api_admin_employee_active(employee_id):
    data = request.get_json(force=True, silent=True) or {}
    if not db.set_shop_employee_active(employee_id, data.get("shop_id"), bool(data.get("active"))):
        return jsonify({"ok": False, "error": "сотрудник не найден"}), 404
    return jsonify({"ok": True})


# ---------- Мини-приложение клиента в Telegram (/m) ----------
# Открывается кнопкой «OilBook» в боте. Логина нет: Telegram сам подписывает
# данные о пользователе (initData) ключом бота, сервер проверяет подпись —
# подделать чужой Telegram ID нельзя. Клиент видит только свои машины,
# историю и свои документы.

TG_INIT_MAX_AGE = 7 * 24 * 3600


def _tg_verify_init_data(raw: str):
    """Проверка подписи Telegram Mini App (core.telegram.org/bots/webapps).
    Возвращает словарь пользователя или None."""
    import hmac
    import hashlib
    if not raw or not BOT_TOKEN or len(raw) > 4096:
        return None
    data = dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
    received = data.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    try:
        if time.time() - int(data.get("auth_date", "0")) > TG_INIT_MAX_AGE:
            return None
        user = json.loads(data.get("user") or "{}")
        user["id"] = int(user["id"])
    except (ValueError, KeyError, TypeError):
        return None
    return user


def tg_client_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = _tg_verify_init_data(request.headers.get("X-Telegram-Init-Data") or "")
        if not user:
            return jsonify({"ok": False, "error": "tg_auth"}), 401
        g.tg_id = user["id"]
        return view(*args, **kwargs)
    return wrapped


# ---------- Панель в Telegram: вход по кнопке бота и файлы в чат ----------
@app.route("/tg")
def tg_panel_entry():
    """Сюда ведёт кнопка «Панель OilBook» в боте. Уже вошёл — сразу в панель,
    нет — на страницу входа (логин и пароль как на сайте)."""
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_page"))
    if role in ("shop", "branch") and session.get("shop_id"):
        return redirect(url_for("index"))
    lang = request.args.get("lang")
    return redirect(url_for("login_page", lang=lang if lang in ("ru", "uz") else None))


_TG_DL_PATH_RE = re.compile(r"^/(api/export(_excel)?|api/products/import_template|"
                            r"api/suppliers/\d+/statement\.xlsx|api/admin/income/export|"
                            r"download/plate-agent\.zip)(\?[^#]*)?$")
_TG_DL_MAX_BYTES = 45 * 1024 * 1024  # бот может отправить файл до 50 МБ


@app.route("/api/tg/send_file", methods=["POST"])
def api_tg_send_file():
    """Внутри Telegram файлы не скачиваются — получаем тот же файл, что дала
    бы кнопка «Скачать» (с теми же правами этого входа), и бот присылает его
    человеку в чат. Кому слать — берём из подписанных данных Telegram."""
    shop = db.get_shop(session["shop_id"]) if session.get("shop_id") else None
    lang = ((shop or {}).get("language") or "ru") if session.get("role") != "admin" else "ru"
    if session.get("role") not in ("shop", "branch", "admin"):
        return jsonify({"ok": False, "error": "session", "login": True}), 401
    user = _tg_verify_init_data(request.headers.get("X-Telegram-Init-Data") or "")
    if not user:
        return jsonify({"ok": False, "error": i18n.t("tgdl_no_tg", lang)}), 403
    path = str((request.get_json(silent=True) or {}).get("path") or "")
    if not _TG_DL_PATH_RE.match(path):
        return jsonify({"ok": False, "error": i18n.t("tgdl_fail", lang)}), 400
    try:
        cookie_name = app.config.get("SESSION_COOKIE_NAME") or "session"
        with app.test_client() as c:
            # тот же вход, что у человека: передаём его cookie сессии
            c.set_cookie(cookie_name, request.cookies.get(cookie_name, ""))
            r = c.get(path, headers={"Accept": "application/octet-stream"})
        disp = r.headers.get("Content-Disposition") or ""
        if r.status_code != 200 or "attachment" not in disp.lower():
            logger.warning(f"Файл для Telegram не получен: {path} → HTTP {r.status_code}")
            return jsonify({"ok": False, "error": i18n.t("tgdl_fail", lang)}), 400
        from werkzeug.http import parse_options_header
        fname = parse_options_header(disp)[1].get("filename") or "oilbook_file"
        data = r.get_data()
    except Exception as e:
        logger.error(f"Файл для Telegram: ошибка {path}: {e}")
        return jsonify({"ok": False, "error": i18n.t("tgdl_fail", lang)}), 500
    if len(data) > _TG_DL_MAX_BYTES:
        return jsonify({"ok": False, "error": i18n.t("tgdl_too_big", lang)}), 400
    sent = _tg_api("sendDocument", {"chat_id": user["id"], "caption": "OilBook · " + fname},
                   {"document": (fname, data, r.mimetype or "application/octet-stream")})
    if not sent:
        return jsonify({"ok": False, "error": i18n.t("tgdl_fail", lang)}), 502
    return jsonify({"ok": True})


def _miniapp_texts(lang):
    return {k[3:]: v for k, v in i18n.get_texts(lang).items() if k.startswith("ma_")}


@app.route("/m")
def miniapp_page():
    texts = {"ru": _miniapp_texts("ru"), "uz": _miniapp_texts("uz")}
    return render_template_string(MINIAPP_PAGE, ma_json=json.dumps(texts, ensure_ascii=False))


@app.route("/api/m/garage")
@tg_client_required
def api_miniapp_garage():
    garage = db.miniapp_garage(g.tg_id)
    garage["docs"] = db.list_client_documents(g.tg_id)
    garage["lang"] = db.client_lang_by_telegram(g.tg_id) if garage["cars"] else None
    garage["ok"] = True
    return jsonify(garage)


@app.route("/api/m/documents", methods=["POST"])
@app.route("/api/m/documents/<int:doc_id>", methods=["PUT"])
@tg_client_required
def api_miniapp_save_document(doc_id=None):
    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "bad_request"}), 400
    res = db.save_client_document(g.tg_id, data, doc_id, lang=data.get("lang"))
    if not res["ok"]:
        return jsonify(res), (404 if res["error"] == "not_found" else 400)
    res["docs"] = db.list_client_documents(g.tg_id)
    return jsonify(res)


@app.route("/api/m/documents/<int:doc_id>", methods=["DELETE"])
@tg_client_required
def api_miniapp_delete_document(doc_id):
    if not db.delete_client_document(g.tg_id, doc_id):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "docs": db.list_client_documents(g.tg_id)})


MINIAPP_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>OilBook</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-secondary-bg-color, #F1F5F9);
    --card: var(--tg-theme-bg-color, #FFFFFF);
    --text: var(--tg-theme-text-color, #0F172A);
    --hint: var(--tg-theme-hint-color, #64748B);
    --accent: var(--tg-theme-button-color, #0EA5E9);
    --accent-text: var(--tg-theme-button-text-color, #FFFFFF);
    --line: rgba(100, 116, 139, .18);
    --ok: #16A34A; --warn: #D97706; --bad: #DC2626;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 15px; }
  body { padding: 0 0 calc(76px + env(safe-area-inset-bottom)); min-height: 100vh; }
  .wrap { max-width: 560px; margin: 0 auto; padding: 14px 16px; }
  .top { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 14px; }
  .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .drop { width: 38px; height: 38px; border-radius: 12px; background: #0B1B3A; display: flex;
    align-items: center; justify-content: center; flex: none; }
  .wm { font-weight: 800; font-size: 20px; letter-spacing: -.4px; line-height: 1.1; }
  .wm .o { color: #38BDF8; }
  .shopline { font-size: 12.5px; color: var(--hint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .lang { border: 1px solid var(--line); background: var(--card); color: var(--text); border-radius: 999px;
    padding: 5px 11px; font-size: 12px; font-weight: 700; cursor: pointer; flex: none; }
  h2 { font-size: 17px; margin: 4px 0 10px; }
  .hint { color: var(--hint); font-size: 13px; line-height: 1.45; }
  .card { background: var(--card); border-radius: 16px; padding: 14px; margin-bottom: 12px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .06); }
  .car { cursor: pointer; }
  .car-h { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
  .plate { font-family: ui-monospace, Menlo, Consolas, monospace; font-weight: 800; font-size: 18px;
    letter-spacing: .5px; border: 2px solid var(--text); border-radius: 7px; padding: 1px 8px; }
  .model { color: var(--hint); font-size: 13.5px; text-align: right; }
  .bar { height: 10px; border-radius: 999px; background: var(--line); overflow: hidden; margin: 14px 0 8px; }
  .bar i { display: block; height: 100%; border-radius: 999px; }
  .left { font-weight: 700; font-size: 15px; }
  .left.ok { color: var(--ok); } .left.warn { color: var(--warn); } .left.bad { color: var(--bad); }
  .meta { display: flex; justify-content: space-between; gap: 8px; color: var(--hint); font-size: 12.5px; margin-top: 4px; }
  .btns { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  .btn { flex: 1 1 140px; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    border: none; border-radius: 12px; padding: 11px 12px; font-size: 14px; font-weight: 700; cursor: pointer;
    background: var(--accent); color: var(--accent-text); text-decoration: none; }
  .btn.ghost { background: transparent; color: var(--accent); border: 1.5px solid var(--accent); }
  .btn.danger { background: transparent; color: var(--bad); border: 1.5px solid var(--bad); }
  .back { background: none; border: none; color: var(--accent); font-size: 15px; font-weight: 600;
    padding: 0 0 10px; cursor: pointer; }
  .kv { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
  .kv:last-child { border-bottom: none; }
  .kv span { color: var(--hint); }
  .visit { border-left: 3px solid var(--accent); padding: 2px 0 2px 12px; margin: 12px 0; }
  .visit-h { display: flex; justify-content: space-between; gap: 8px; font-weight: 700; font-size: 14px; }
  .visit ul { margin: 6px 0 0; padding-left: 18px; font-size: 13.5px; }
  .visit .hint { font-size: 12.5px; }
  .doc { display: flex; align-items: center; gap: 12px; cursor: pointer; }
  .doc-ic { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
    font-size: 20px; flex: none; background: var(--bg); }
  .doc-b { flex: 1; min-width: 0; }
  .doc-t { font-weight: 700; font-size: 14.5px; }
  .doc-s { font-size: 12.5px; font-weight: 700; flex: none; text-align: right; }
  .doc-s.ok { color: var(--ok); } .doc-s.warn { color: var(--warn); } .doc-s.bad { color: var(--bad); }
  label.f { display: block; font-size: 12.5px; color: var(--hint); margin: 12px 0 6px; font-weight: 600; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { border: 1.5px solid var(--line); background: var(--card); color: var(--text); border-radius: 999px;
    padding: 7px 12px; font-size: 13px; cursor: pointer; }
  .chip.on { border-color: var(--accent); background: var(--accent); color: var(--accent-text); font-weight: 700; }
  input, select { width: 100%; padding: 11px 12px; border-radius: 12px; border: 1.5px solid var(--line);
    background: var(--card); color: var(--text); font-size: 15px; font-family: inherit; }
  .err { color: var(--bad); font-size: 13px; margin-top: 10px; min-height: 1em; }
  .empty { text-align: center; padding: 28px 18px; }
  .empty .big { font-size: 44px; }
  .nav { position: fixed; left: 0; right: 0; bottom: 0; display: flex; background: var(--card);
    border-top: 1px solid var(--line); padding: 6px 8px calc(6px + env(safe-area-inset-bottom)); z-index: 5; }
  .nav button { flex: 1; background: none; border: none; color: var(--hint); font-size: 11.5px; font-weight: 600;
    display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 6px 0; cursor: pointer; }
  .nav button b { font-size: 20px; line-height: 1; }
  .nav button.on { color: var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="drop"><svg width="18" height="21" viewBox="0 0 26 30" aria-hidden="true"><path d="M13 1C13 1 2 13.5 2 19.5A11 11 0 0 0 24 19.5C24 13.5 13 1 13 1Z" fill="#0EA5E9"/></svg></div>
      <div style="min-width:0;">
        <div class="wm"><span class="o">Oil</span>Book</div>
        <div class="shopline" id="shopLine"></div>
      </div>
    </div>
    <button class="lang" id="langBtn" onclick="toggleLang()">UZ</button>
  </div>
  <div id="view"></div>
</div>
<nav class="nav">
  <button id="nav-garage" class="on" onclick="go('garage')"><b>🚗</b><span id="navGarage"></span></button>
  <button id="nav-docs" onclick="go('docs')"><b>📄</b><span id="navDocs"></span></button>
</nav>
<script>
const TX = {{ ma_json|safe }};
const tg = window.Telegram && window.Telegram.WebApp;
const INIT = (tg && tg.initData) || new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || '';
const S = { tab: 'garage', data: null, car: null, doc: null, lang: 'ru' };
const KINDS = [['insurance', '🛡️'], ['inspection', '🔧'], ['gas', '🔥'], ['tint', '🕶️'], ['proxy', '📝'], ['other', '📄']];
const KIND_IC = Object.fromEntries(KINDS);

function savedLang() { try { return localStorage.getItem('ma_lang'); } catch (e) { return null; } }
(function initLang() {
  let l = savedLang();
  if (!l) {
    const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    l = u && /^uz/.test(u.language_code || '') ? 'uz' : 'ru';
  }
  S.lang = l === 'uz' ? 'uz' : 'ru';
})();
function T(k) { return (TX[S.lang] && TX[S.lang][k]) || TX.ru[k] || k; }
function toggleLang() {
  S.lang = S.lang === 'ru' ? 'uz' : 'ru';
  try { localStorage.setItem('ma_lang', S.lang); } catch (e) {}
  render();
}
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function num(n) { return Number(n || 0).toLocaleString('ru-RU'); }
function dt(s) { if (!s) return '—'; const p = String(s).slice(0, 10).split('-'); return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : s; }
function haptic() { try { tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged(); } catch (e) {} }

async function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({ 'X-Telegram-Init-Data': INIT, 'Content-Type': 'application/json' }, opts.headers || {});
  const res = await fetch(path, opts);
  let body = {};
  try { body = await res.json(); } catch (e) {}
  if (res.status === 401) throw new Error('auth');
  return body;
}

async function load() {
  document.getElementById('view').innerHTML = `<div class="empty hint">${T('loading')}</div>`;
  if (!INIT) { S.error = 'auth'; render(); return; }
  try {
    const d = await api('/api/m/garage');
    if (!d.ok) throw new Error('load');
    S.data = d; S.error = null;
    if (d.lang && !savedLang()) S.lang = d.lang;
  } catch (e) { S.error = e.message === 'auth' ? 'auth' : 'load'; }
  render();
}

function go(tab) { haptic(); S.tab = tab; S.car = null; S.doc = null; render(); window.scrollTo(0, 0); }

function setBack(on) {
  if (!tg || !tg.BackButton) return;
  if (on) tg.BackButton.show(); else tg.BackButton.hide();
}

function render() {
  document.getElementById('langBtn').textContent = S.lang === 'ru' ? 'UZ' : 'RU';
  document.getElementById('navGarage').textContent = T('tab_garage');
  document.getElementById('navDocs').textContent = T('tab_docs');
  document.getElementById('nav-garage').classList.toggle('on', S.tab === 'garage');
  document.getElementById('nav-docs').classList.toggle('on', S.tab === 'docs');
  const shop = S.data && S.data.shop;
  document.getElementById('shopLine').textContent = shop && shop.name ? `${T('your_shop')}: ${shop.name}` : '';
  const v = document.getElementById('view');
  if (S.error) {
    v.innerHTML = `<div class="card empty"><div class="big">🔒</div><p class="hint">${S.error === 'auth' ? T('open_from_bot') : T('load_error')}</p>
      ${S.error === 'auth' ? '' : `<button class="btn" onclick="load()">${T('retry')}</button>`}</div>`;
    setBack(false);
    return;
  }
  if (!S.data) return;
  if (S.tab === 'garage') v.innerHTML = S.car ? carView(S.car) : garageView();
  else v.innerHTML = S.doc ? docForm(S.doc) : docsView();
  setBack(!!(S.car || S.doc));
}

function forecast(c) {
  const r = c.oil_ratio;
  const due = (r != null && r >= 1) || (c.days_left != null && c.days_left <= 0) || (c.km_left != null && c.km_left <= 0);
  if (due) return { cls: 'bad', text: T('change_now'), pct: 100, color: 'var(--bad)' };
  const parts = [];
  if (c.km_left != null) parts.push(`≈ ${num(c.km_left)} ${T('km')}`);
  if (c.days_left != null) parts.push(`${c.days_left} ${T('days')}`);
  if (!parts.length) return { cls: '', text: T('no_forecast'), pct: 0, color: 'var(--line)' };
  const pct = Math.max(4, Math.min(100, Math.round((r || 0) * 100)));
  const cls = (r || 0) >= 0.8 ? 'warn' : 'ok';
  return { cls, text: `${parts.join(' · ')} ${T('until_change')}`, pct, color: cls === 'warn' ? 'var(--warn)' : 'var(--ok)' };
}

function garageView() {
  const d = S.data;
  if (!d.cars.length) {
    return `<div class="card empty"><div class="big">🚗</div><h2>${T('garage_empty_title')}</h2>
      <p class="hint">${T('garage_empty')}</p></div>
      <div class="card"><h2>📄 ${T('docs_title')}</h2><p class="hint">${T('docs_hint')}</p>
      <div class="btns"><button class="btn" onclick="go('docs')">${T('add_doc')}</button></div></div>`;
  }
  const hello = d.name ? `<p class="hint" style="margin:0 0 10px;">${T('hello')}, ${esc(d.name)}!</p>` : '';
  return hello + d.cars.map((c, i) => {
    const f = forecast(c);
    return `<div class="card car" onclick="openCar(${i})">
      <div class="car-h"><span class="plate">${esc(c.plate)}</span><span class="model">${esc([c.brand, c.model].filter(Boolean).join(' '))}</span></div>
      <div class="bar"><i style="width:${f.pct}%; background:${f.color};"></i></div>
      <div class="left ${f.cls}">${f.text}</div>
      <div class="meta"><span>${T('last_visit')}: ${dt(c.last_date)}</span><span>${esc((c.shop || {}).name || '')}</span></div>
    </div>`;
  }).join('');
}

function openCar(i) { haptic(); S.car = S.data.cars[i]; render(); window.scrollTo(0, 0); }

function unitText(u) { return u === 'l' ? ' ' + T('l') : (u === 'pc' ? ' ' + T('pc') : ''); }

function carView(c) {
  const f = forecast(c);
  const shop = c.shop || {};
  const phone = (shop.phone || '').replace(/[^0-9+]/g, '');
  const rows = [
    [T('next_change'), c.next_date ? dt(c.next_date) : '—'],
    c.next_mileage ? [T('mileage'), `${num(c.next_mileage)} ${T('km')}`] : null,
    c.est_km ? [T('est_mileage'), `${num(c.est_km)} ${T('km')}`] : null,
    [T('last_visit'), `${dt(c.last_date)}${c.last_mileage ? ' · ' + num(c.last_mileage) + ' ' + T('km') : ''}`],
  ].filter(Boolean);
  const visits = c.history.length ? c.history.map(h => {
    const items = (h.items || []).filter(i => i.name).map(i => {
      const qty = i.qty ? ` × ${String(i.qty).replace('.', ',')}${unitText(i.unit)}` : '';
      return `<li>${esc(i.name)}${i.brand && i.brand !== i.name ? ' — ' + esc(i.brand) : ''}${qty}</li>`;
    }).join('');
    return `<div class="visit">
      <div class="visit-h"><span>${dt(h.date)}</span><span>${h.cost ? num(h.cost) + ' ' + T('sum') : ''}</span></div>
      <div class="hint">${esc(h.shop || '')}${h.mileage ? ' · ' + num(h.mileage) + ' ' + T('km') : ''}</div>
      ${items ? `<ul>${items}</ul>` : `<div class="hint">${esc(h.service || '')}${h.oil ? ' — ' + esc(h.oil) : ''}${h.filter ? ', ' + T('filter') : ''}</div>`}
    </div>`;
  }).join('') : `<p class="hint">${T('no_history')}</p>`;
  return `<button class="back" onclick="closeView()">‹ ${T('back')}</button>
    <div class="card">
      <div class="car-h"><span class="plate">${esc(c.plate)}</span><span class="model">${esc([c.brand, c.model].filter(Boolean).join(' '))}</span></div>
      <div class="bar"><i style="width:${f.pct}%; background:${f.color};"></i></div>
      <div class="left ${f.cls}">${f.text}</div>
      <div style="margin-top:10px;">${rows.map(r => `<div class="kv"><span>${r[0]}</span><b>${r[1]}</b></div>`).join('')}</div>
      <div class="btns">
        ${c.passport ? `<button class="btn" onclick="sharePassport()">📤 ${T('share_passport')}</button>` : ''}
        ${c.passport ? `<button class="btn ghost" onclick="openPassport()">${T('open_passport')}</button>` : ''}
      </div>
    </div>
    ${shop.name ? `<div class="card">
      <div class="kv"><span>${T('your_shop')}</span><b>${esc(shop.name)}</b></div>
      ${shop.address ? `<div class="kv"><span>📍</span><b style="text-align:right;">${esc(shop.address)}</b></div>` : ''}
      ${shop.hours ? `<div class="kv"><span>🕘</span><b>${esc(shop.hours)}</b></div>` : ''}
      <div class="btns">
        ${phone ? `<a class="btn" href="tel:${esc(phone)}">📞 ${T('call_shop')}</a>` : ''}
        ${shop.lat && shop.lon ? `<button class="btn ghost" onclick="openRoute(${Number(shop.lat)}, ${Number(shop.lon)})">🧭 ${T('route')}</button>` : ''}
      </div>
    </div>` : ''}
    <div class="card"><h2>📘 ${T('service_book')}</h2>${visits}</div>`;
}

function passportUrl() { return `${location.origin}/passport/${encodeURIComponent(S.car.passport)}`; }
function openLink(url) { if (tg && tg.openLink) tg.openLink(url); else window.open(url, '_blank'); }
function openPassport() { openLink(passportUrl()); }
function openRoute(lat, lon) { openLink(`https://yandex.uz/maps/?rtext=~${lat},${lon}&rtt=auto`); }
function sharePassport() {
  const url = `https://t.me/share/url?url=${encodeURIComponent(passportUrl())}&text=${encodeURIComponent(T('share_text').replace('{plate}', S.car.plate))}`;
  if (tg && tg.openTelegramLink) tg.openTelegramLink(url); else window.open(url, '_blank');
}

function docStatus(d) {
  if (d.days_left < 0) return { cls: 'bad', text: `${T('expired')} ${-d.days_left} ${T('days')}` };
  if (d.days_left === 0) return { cls: 'bad', text: T('today') };
  if (d.days_left <= 30) return { cls: 'warn', text: `${T('left')} ${d.days_left} ${T('days')}` };
  return { cls: 'ok', text: T('until_date').replace('{date}', dt(d.expires_on)) };
}
function docName(d) { return d.kind === 'other' && d.title ? d.title : T('doc_' + d.kind); }

function docsView() {
  const docs = S.data.docs || [];
  const list = docs.length ? docs.map((d, i) => {
    const st = docStatus(d);
    return `<div class="card doc" onclick="editDoc(${i})">
      <div class="doc-ic">${KIND_IC[d.kind] || '📄'}</div>
      <div class="doc-b"><div class="doc-t">${esc(docName(d))}</div>
        <div class="hint">${d.plate ? esc(d.plate) + ' · ' : ''}${dt(d.expires_on)}</div></div>
      <div class="doc-s ${st.cls}">${st.text}</div>
    </div>`;
  }).join('') : `<div class="card empty"><div class="big">📄</div><p class="hint">${T('docs_empty')}</p></div>`;
  return `<h2>${T('docs_title')}</h2><p class="hint" style="margin-top:0;">${T('docs_hint')}</p>${list}
    <div class="btns"><button class="btn" onclick="editDoc(-1)">＋ ${T('add_doc')}</button></div>`;
}

function editDoc(i) {
  haptic();
  const plates = (S.data.cars || []).map(c => c.plate);
  S.doc = i >= 0 ? Object.assign({}, S.data.docs[i]) : { kind: 'insurance', title: '', plate: plates.length === 1 ? plates[0] : '', expires_on: '' };
  render(); window.scrollTo(0, 0);
}
function closeView() { S.car = null; S.doc = null; render(); window.scrollTo(0, 0); }
function keepForm() {
  const t = document.getElementById('docTitle'), p = document.getElementById('docPlate'), d = document.getElementById('docDate');
  if (t) S.doc.title = t.value;
  if (p) S.doc.plate = p.value;
  if (d) S.doc.expires_on = d.value;
}
function setKind(k) { keepForm(); S.doc.kind = k; render(); }

function docForm(d) {
  const plates = (S.data.cars || []).map(c => c.plate);
  if (d.plate && plates.indexOf(d.plate) < 0) plates.push(d.plate);
  return `<button class="back" onclick="closeView()">‹ ${T('back')}</button>
    <div class="card">
      <h2>${d.id ? esc(docName(d)) : T('add_doc')}</h2>
      <label class="f">${T('doc_kind')}</label>
      <div class="chips">${KINDS.map(([k, ic]) => `<button class="chip ${d.kind === k ? 'on' : ''}" onclick="setKind('${k}')">${ic} ${T('doc_' + k)}</button>`).join('')}</div>
      ${d.kind === 'other' ? `<label class="f">${T('doc_title')}</label><input id="docTitle" maxlength="60" placeholder="${T('doc_title_ph')}" value="${esc(d.title || '')}">` : ''}
      <label class="f">${T('doc_car')}</label>
      <select id="docPlate"><option value="">${T('doc_no_car')}</option>${plates.map(p => `<option ${p === d.plate ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select>
      <label class="f">${T('doc_date')}</label>
      <input id="docDate" type="date" value="${esc(d.expires_on || '')}">
      <div class="err" id="docErr"></div>
      <div class="btns">
        <button class="btn" id="docSave" onclick="saveDoc()">${T('save')}</button>
        ${d.id ? `<button class="btn danger" onclick="deleteDoc()">${T('delete')}</button>` : `<button class="btn ghost" onclick="closeView()">${T('cancel')}</button>`}
      </div>
    </div>`;
}

async function saveDoc() {
  keepForm();
  const d = S.doc;
  const body = { kind: d.kind, title: (d.title || '').trim(), plate: d.plate || '', expires_on: d.expires_on || '', lang: S.lang };
  const err = document.getElementById('docErr');
  if (!body.expires_on) { err.textContent = T('err_date'); return; }
  if (d.kind === 'other' && !body.title) { err.textContent = T('err_title'); return; }
  const btn = document.getElementById('docSave');
  btn.disabled = true;
  try {
    const r = await api(d.id ? `/api/m/documents/${d.id}` : '/api/m/documents', { method: d.id ? 'PUT' : 'POST', body: JSON.stringify(body) });
    if (!r.ok) { err.textContent = r.error === 'too_many' ? T('err_too_many') : (r.error === 'bad_date' ? T('err_date') : T('err_save')); btn.disabled = false; return; }
    S.data.docs = r.docs; S.doc = null;
    try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
    render();
  } catch (e) { err.textContent = e.message === 'auth' ? T('open_from_bot') : T('err_save'); btn.disabled = false; }
}

function deleteDoc() {
  const run = async ok => {
    if (!ok) return;
    try {
      const r = await api(`/api/m/documents/${S.doc.id}`, { method: 'DELETE' });
      if (r.ok) { S.data.docs = r.docs; S.doc = null; render(); }
    } catch (e) { document.getElementById('docErr').textContent = T('err_save'); }
  };
  if (tg && tg.showConfirm && tg.platform && tg.platform !== 'unknown') tg.showConfirm(T('delete_confirm'), run);
  else run(confirm(T('delete_confirm')));
}

if (tg) {
  try { tg.ready(); tg.expand(); } catch (e) {}
  if (tg.BackButton) tg.BackButton.onClick(closeView);
}
render();
load();
</script>
</body>
</html>
"""


def run_webapp():
    port = int(os.environ.get("PORT", 8000))
    db.init_db()
    try:
        # waitress — надёжный сервер для работы в интернете (встроенный
        # сервер Flask рассчитан только на разработку)
        from waitress import serve
        # перед сайтом стоит прокси Render: он сообщает настоящий адрес
        # клиента в X-Forwarded-For (последнее значение) и https в
        # X-Forwarded-Proto — без этих настроек waitress их отбрасывает
        serve(app, host="0.0.0.0", port=port, threads=16, channel_timeout=180,
              connection_limit=200, ident="OilBook",
              trusted_proxy="*", trusted_proxy_count=1,
              trusted_proxy_headers="x-forwarded-for x-forwarded-proto",
              clear_untrusted_proxy_headers=True)
    except ImportError:
        app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)


def run_webapp_in_thread():
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()
    return t


# Разделы, вынесенные в отдельные файлы: импортируются последними, когда
# всё, что они берут отсюда, уже определено.
import display  # noqa: E402,F401
import registration  # noqa: E402,F401
from registration import reg_decide, reg_notify_admin  # noqa: E402,F401  (их вызывает bot.py)
import subscription  # noqa: E402,F401
from subscription import (  # noqa: E402,F401  (нужны остальной программе и bot.py)
    _admin_sub_summary, _sub_owner_link, _sub_ro_ctx, notify_sub_decision, sub_decide,
)
import admin_routes  # noqa: E402,F401


if __name__ == "__main__":
    # запуск напрямую (python webapp.py): работаем с модулем webapp, на app
    # которого зарегистрированы и вынесенные маршруты
    import webapp
    webapp.run_webapp()
