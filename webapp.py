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
from flask import Flask, request, jsonify, render_template_string, Response, session, redirect, url_for, g, send_file

import database as db
import i18n
import help_content

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.after_request
def _no_stale_cache(resp):
    """Данные и страницы не кешируем в браузере: иначе при возврате в
    приложение/кнопке «назад» телефон показывает старые цифры, пока не
    обновишь страницу вручную. Статика (иконки, шрифты) кешируется как обычно."""
    path = request.path or ""
    if path.startswith("/api/") or resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

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


app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # самый большой законный файл — резервная копия базы
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("PUBLIC_URL", "").startswith("https://"))

PUBLIC_URL = os.environ.get("PUBLIC_URL", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
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
                timeout=60,
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
    try:
        size_mb = os.path.getsize(gz_path) / 1024 / 1024
        ok, err = _send_telegram_document(
            chat_id, gz_path, f"oilbot_backup_{today_str}.db.gz",
            caption=f"📦 Резервная копия базы данных за {today_str} ({size_mb:.1f} МБ, сжатая){caption_note}",
        )
        return ok, err, size_mb
    finally:
        for pth in (backup_path, gz_path):
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
    if uploaded_bytes[:2] == b"\x1f\x8b":
        # сжатая копия (.db.gz) — распаковываем
        import gzip
        try:
            uploaded_bytes = gzip.decompress(uploaded_bytes)
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

CAR_BRANDS = [
    "Chevrolet", "Daewoo", "Ravon", "Kia", "Hyundai", "Toyota", "Lexus",
    "Nissan", "Isuzu", "BMW", "Mercedes-Benz", "Audi", "Volkswagen",
    "Lada (ВАЗ)", "Datsun", "Honda", "Mazda", "Ford", "Mitsubishi", "Другое",
]
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
        g.is_branch = shop.get("role") == "branch"
        g.parent_shop_id = shop.get("parent_shop_id")
        # подписка: не оплачено (или новый филиал ещё не оплачен) — вся
        # панель закрыта, открыта только страница «Подписка» (там оплата)
        g.sub = db.subscription_state(shop)
        if g.sub["blocked"] and not getattr(view, "_sub_exempt", False):
            if request.path.startswith("/api/") and "text/html" not in (request.headers.get("Accept") or ""):
                return jsonify({"ok": False, "error": "subscription", "subscription": True}), 402
            return redirect("/subscription")
        return view(*args, **kwargs)
    return wrapped


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
<link rel="manifest" href="/static/manifest.json">
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


REG_CITIES = {
    "ru": ["Андижан", "Асака", "Ханабад", "Шахрихан", "Фергана", "Маргилан", "Коканд", "Кувасай",
           "Наманган", "Чуст", "Чартак", "Ташкент"],
    "uz": ["Andijon", "Asaka", "Xonobod", "Shahrixon", "Farg'ona", "Marg'ilon", "Qo'qon", "Quvasoy",
           "Namangan", "Chust", "Chortoq", "Toshkent"],
}

REGISTER_PAGE = """
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ T.reg_title }} — OilBook</title>
<link rel="manifest" href="/static/manifest.json">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@700;800&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<style>
  * { box-sizing: border-box; }
  body { margin:0; background:#0f1115; color:#f2f2f2; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
         min-height:100vh; display:flex; flex-direction:column; align-items:center; padding:24px 14px 40px; }
  .brand { display:flex; align-items:center; gap:10px; margin:0 0 18px; }
  .brand .wordmark { font-family:'Sora', -apple-system, sans-serif; font-weight:800; font-size:30px; letter-spacing:-1px; line-height:1; }
  .wm-oil { background:linear-gradient(135deg, #38BDF8 0%, #3B82F6 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .wm-book { color:#fff; }
  .box { background:#1a1d24; border:1px solid #2a2e37; border-radius:14px; padding:22px 18px; width:100%; max-width:420px; }
  h1 { font-size:20px; margin:0 0 6px; }
  .step { font-size:12px; color:#3a86ff; font-weight:600; margin-bottom:6px; }
  .intro { font-size:14px; color:#a9b0bd; margin:0 0 16px; line-height:1.5; }
  label { display:block; font-size:14px; font-weight:600; color:#e6e6e6; margin:14px 0 5px; }
  input { width:100%; padding:11px; border-radius:8px; border:1px solid #2a2e37; background:#11141a; color:#fff; font-size:16px; }
  input:focus { outline:none; border-color:#3a86ff; }
  input.bad { border-color:#dc6f6f; }
  .hint { font-size:12.5px; color:#8b93a3; margin-top:5px; line-height:1.45; }
  .ferr { font-size:13px; color:#ff8a8a; margin-top:5px; display:none; }
  .ferr.on { display:block; }
  .row2 { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .row2 label { margin-top:14px; }
  button, .btn { display:block; width:100%; padding:13px; border:none; border-radius:10px; background:#3a86ff; color:#fff;
                 font-size:16px; font-weight:600; cursor:pointer; text-align:center; text-decoration:none; margin-top:18px; }
  button:disabled { opacity:.6; }
  .btn-tg { background:#229ED9; }
  .btn-ghost { background:transparent; border:1px solid #2a2e37; color:#cfd5df; }
  .error { background:#3a1e1e; color:#ff9a9a; padding:10px; border-radius:8px; margin-top:14px; font-size:14px; display:none; }
  .error.on { display:block; }
  ol { margin:10px 0 0; padding-left:20px; color:#cfd5df; font-size:14px; line-height:1.7; }
  .code { font-family: ui-monospace, Menlo, monospace; font-size:26px; letter-spacing:4px; text-align:center;
          background:#11141a; border:1px dashed #3a86ff; border-radius:10px; padding:10px; margin-top:8px; user-select:all; }
  .wait { display:flex; align-items:center; gap:10px; margin-top:16px; font-size:14px; color:#cfd5df; }
  .spin { width:18px; height:18px; border:2px solid #3a86ff; border-top-color:transparent; border-radius:50%; animation:sp 0.9s linear infinite; flex:none; }
  @keyframes sp { to { transform:rotate(360deg); } }
  .note { background:#16253f; color:#bcd4ff; border-radius:8px; padding:10px; font-size:13.5px; margin-top:14px; line-height:1.5; display:none; }
  .note.on { display:block; }
  .big { font-size:44px; text-align:center; margin:4px 0 8px; }
  .links { text-align:center; margin-top:16px; font-size:13px; }
  .links a { color:#8b93a3; text-decoration:none; display:block; margin-top:8px; }
  .links a.pri { color:#3a86ff; }
  .hp { position:absolute; left:-5000px; width:1px; height:1px; overflow:hidden; }
  .locrow { display:flex; gap:10px; align-items:flex-start; margin-top:16px; padding:12px; border:1px dashed #3a4456; border-radius:10px; background:#141821; }
  .locico { font-size:20px; line-height:1; margin-top:1px; }
  .loct { font-size:14px; font-weight:600; color:#e6e6e6; }
</style>
</head>
<body>
  <div class="brand"><div class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></div></div>

  <form class="box" id="regForm" novalidate onsubmit="submitReg(event)">
    <div class="step">{{ T.reg_step.format(n=1) }}</div>
    <h1>{{ T.reg_title }}</h1>
    <p class="intro">{{ T.reg_intro }}</p>

    <label for="f_shop_name">{{ T.reg_shop_name }}</label>
    <input id="f_shop_name" maxlength="80" placeholder="{{ T.reg_shop_name_ph }}" autocomplete="organization">
    <div class="hint">{{ T.reg_shop_name_hint }}</div>
    <div class="ferr" id="e_shop_name"></div>

    <label for="f_owner_name">{{ T.reg_owner_name }}</label>
    <input id="f_owner_name" maxlength="60" placeholder="{{ T.reg_owner_name_ph }}" autocomplete="name">
    <div class="hint">{{ T.reg_owner_name_hint }}</div>
    <div class="ferr" id="e_owner_name"></div>

    <label for="f_city">{{ T.reg_city }}</label>
    <input id="f_city" maxlength="40" list="cityList" placeholder="{{ T.reg_city_ph }}" autocomplete="off">
    <datalist id="cityList">{% for c in cities %}<option value="{{ c }}">{% endfor %}</datalist>
    <div class="hint">{{ T.reg_city_hint }}</div>
    <div class="ferr" id="e_city"></div>

    <label for="f_phone">{{ T.reg_phone }}</label>
    <input id="f_phone" type="tel" inputmode="tel" maxlength="20" placeholder="+998 90 123 45 67" autocomplete="tel">
    <div class="hint">{{ T.reg_phone_hint }}</div>
    <div class="ferr" id="e_phone"></div>

    <label for="f_address">{{ T.reg_address }}</label>
    <input id="f_address" maxlength="150" placeholder="{{ T.reg_address_ph }}" autocomplete="street-address">
    <div class="hint">{{ T.reg_address_hint }}</div>
    <div class="ferr" id="e_address"></div>

    <div class="locrow">
      <div class="locico">📍</div>
      <div><div class="loct">{{ T.reg_location }}</div><div class="hint" style="margin-top:3px;">{{ T.reg_location_hint }}</div></div>
    </div>

    <label for="f_username">{{ T.reg_username }}</label>
    <input id="f_username" maxlength="30" placeholder="{{ T.reg_username_ph }}" autocomplete="username"
           autocapitalize="none" autocorrect="off" spellcheck="false">
    <div class="hint">{{ T.reg_username_hint }}</div>
    <div class="ferr" id="e_username"></div>

    <label for="f_password">{{ T.reg_password }}</label>
    <input id="f_password" type="password" maxlength="100" autocomplete="new-password">
    <div class="hint">{{ T.reg_password_hint }}</div>
    <div class="ferr" id="e_password"></div>

    <label for="f_password2">{{ T.reg_password2 }}</label>
    <input id="f_password2" type="password" maxlength="100" autocomplete="new-password">
    <div class="ferr" id="e_password2"></div>

    <div class="hp" aria-hidden="true"><input id="f_website" tabindex="-1" autocomplete="off"></div>

    <div class="error" id="formErr"></div>
    <button type="submit" id="submitBtn">{{ T.reg_submit }}</button>
    <div class="links">
      <a class="pri" href="/login?lang={{ lang }}">{{ T.reg_back_login }}</a>
      <a href="/register?lang={{ other_lang }}">{{ T.lang_switch }}</a>
    </div>
  </form>

  <div class="box" id="tgBox" style="display:none;">
    <div class="step">{{ T.reg_step.format(n=2) }}</div>
    <h1>{{ T.reg_tg_title }}</h1>
    <p class="intro">{{ T.reg_tg_why }}</p>
    <ol>
      <li>{{ T.reg_tg_step1 }}</li>
      <li>{{ T.reg_tg_step2 }}</li>
      <li>{{ T.reg_tg_step3 }}</li>
      <li>{{ T.reg_tg_step4 }}</li>
    </ol>
    <a class="btn btn-tg" id="tgLink" href="#" target="_blank" rel="noopener">{{ T.reg_tg_btn }}</a>
    <div class="note" id="tgBound">{{ T.reg_tg_bound }}</div>
    <div class="note" id="tgPhoneOk">{{ T.reg_tg_phone_ok }}</div>
    <div class="wait"><div class="spin"></div><span>{{ T.reg_tg_wait }}</span></div>
    <p class="hint" style="margin-top:18px;">{{ T.reg_tg_fallback.format(bot=bot_username) }}</p>
    <div class="code" id="tgCode">—</div>
    <p class="hint">{{ T.reg_tg_expires }}</p>
  </div>

  <div class="box" id="doneBox" style="display:none;">
    <div class="big" id="doneIcon">✅</div>
    <h1 id="doneTitle" style="text-align:center;"></h1>
    <p class="intro" id="doneText" style="text-align:center;"></p>
    <a class="btn" id="doneBtn" href="/login?lang={{ lang }}" style="display:none;">{{ T.reg_approved_btn }}</a>
    <a class="btn btn-ghost" id="againBtn" href="/register?lang={{ lang }}" style="display:none;">{{ T.reg_again }}</a>
  </div>

<script>
const LANG = {{ lang|tojson }};
const TX = {
  sent_title: {{ T.reg_sent_title|tojson }}, sent_text: {{ T.reg_sent_text|tojson }},
  ok_title: {{ T.reg_approved_title|tojson }}, ok_text: {{ T.reg_approved_text|tojson }},
  no_title: {{ T.reg_rejected_title|tojson }}, no_text: {{ T.reg_rejected_text|tojson }},
  exp_title: {{ T.reg_expired_title|tojson }}, exp_text: {{ T.reg_expired_text|tojson }},
  e_shop_name: {{ T.reg_err_shop_name|tojson }}, e_owner_name: {{ T.reg_err_owner_name|tojson }},
  e_city: {{ T.reg_err_city|tojson }}, e_phone: {{ T.reg_err_phone|tojson }},
  e_address: {{ T.reg_err_address|tojson }}, e_username: {{ T.reg_err_username|tojson }},
  e_password: {{ T.reg_err_password|tojson }}, e_password2: {{ T.reg_err_password2|tojson }},
  e_network: {{ T.reg_err_network|tojson }}
};
const FIELDS = ['shop_name', 'owner_name', 'city', 'phone', 'address', 'username', 'password', 'password2'];
let regToken = null, pollTimer = null, sending = false;

function val(id) { return document.getElementById('f_' + id).value.trim(); }
function setErr(f, text) {
  const e = document.getElementById('e_' + f), inp = document.getElementById('f_' + f);
  if (!e) return;
  e.textContent = text || '';
  e.classList.toggle('on', !!text);
  if (inp) inp.classList.toggle('bad', !!text);
}
function phoneDigits(v) {
  let d = String(v || '').replace(/[^0-9]/g, '');
  if (d.length === 9) d = '998' + d;
  return d;
}
function checkForm() {
  const bad = {};
  const sn = val('shop_name');
  if (sn.length < 2 || sn.length > 80) bad.shop_name = TX.e_shop_name;
  if (val('owner_name').length < 2) bad.owner_name = TX.e_owner_name;
  if (val('city').length < 2) bad.city = TX.e_city;
  const pd = phoneDigits(val('phone'));
  if (pd.length !== 12 || pd.slice(0, 3) !== '998') bad.phone = TX.e_phone;
  if (val('address').length < 3) bad.address = TX.e_address;
  if (!/^[A-Za-z0-9_]{3,30}$/.test(val('username'))) bad.username = TX.e_username;
  const pw = document.getElementById('f_password').value;
  if (pw.length < 6) bad.password = TX.e_password;
  else if (pw !== document.getElementById('f_password2').value) bad.password2 = TX.e_password2;
  FIELDS.forEach(f => setErr(f, bad[f]));
  const first = FIELDS.find(f => bad[f]);
  if (first) document.getElementById('f_' + first).focus();
  return !first;
}
FIELDS.forEach(f => {
  const el = document.getElementById('f_' + f);
  el.addEventListener('input', () => setErr(f, ''));
  el.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter') return;
    const i = FIELDS.indexOf(f);
    if (i < FIELDS.length - 1) { ev.preventDefault(); document.getElementById('f_' + FIELDS[i + 1]).focus(); }
  });
});

async function submitReg(ev) {
  ev.preventDefault();
  if (sending) return;
  const err = document.getElementById('formErr');
  err.classList.remove('on');
  if (!checkForm()) return;
  sending = true;
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  const body = { lang: LANG, website: document.getElementById('f_website').value };
  FIELDS.forEach(f => { body[f] = f.indexOf('password') === 0 ? document.getElementById('f_' + f).value : val(f); });
  try {
    const res = await fetch('/api/register', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    if (!data.ok) {
      if (data.field) { setErr(data.field, data.error); document.getElementById('f_' + data.field).focus(); }
      else { err.textContent = data.error || TX.e_network; err.classList.add('on'); }
      return;
    }
    regToken = data.token;
    try { history.replaceState(null, '', '/register?lang=' + LANG + '&t=' + encodeURIComponent(regToken)); } catch (e) {}
    showStatus(data);
  } catch (e) {
    err.textContent = TX.e_network; err.classList.add('on');
  } finally {
    sending = false; btn.disabled = false;
  }
}

function show(id) {
  ['regForm', 'tgBox', 'doneBox'].forEach(b => { document.getElementById(b).style.display = b === id ? '' : 'none'; });
  window.scrollTo(0, 0);
}
function showDone(icon, title, text, loginBtn, againBtn) {
  document.getElementById('doneIcon').textContent = icon;
  document.getElementById('doneTitle').textContent = title;
  document.getElementById('doneText').textContent = text;
  document.getElementById('doneBtn').style.display = loginBtn ? '' : 'none';
  document.getElementById('againBtn').style.display = againBtn ? '' : 'none';
  show('doneBox');
}
function showStatus(d) {
  const st = d.status;
  if (st === 'new') {
    if (d.bot_link) document.getElementById('tgLink').href = d.bot_link;
    document.getElementById('tgCode').textContent = d.code || '—';
    document.getElementById('tgBound').classList.toggle('on', !!d.tg_bound && !d.phone_ok);
    document.getElementById('tgPhoneOk').classList.toggle('on', !!d.phone_ok);
    if (document.getElementById('tgBox').style.display === 'none') show('tgBox');
    startPoll();
    return;
  }
  stopPoll();
  if (st === 'pending') showDone('📨', TX.sent_title, TX.sent_text, false, false);
  else if (st === 'approved') showDone('🎉', TX.ok_title, TX.ok_text, true, false);
  else if (st === 'rejected') showDone('✖️', TX.no_title, TX.no_text, false, false);
  else showDone('⌛', TX.exp_title, TX.exp_text, false, true);
}
async function poll() {
  if (!regToken) return;
  try {
    const res = await fetch('/api/register/status?t=' + encodeURIComponent(regToken));
    const d = await res.json();
    if (d.ok) showStatus(d);
    else if (d.status) showStatus(d);
  } catch (e) {}
}
function startPoll() { if (!pollTimer) pollTimer = setInterval(poll, 3000); }
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
document.addEventListener('visibilitychange', () => { if (!document.hidden && regToken) poll(); });

(function init() {
  const t = new URLSearchParams(location.search).get('t');
  if (t) { regToken = t; poll(); }
})();
</script>
</body>
</html>
"""


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
    output_path = f"/tmp/passport_{token}.pdf"
    try:
        _generate_passport_pdf(car, history, output_path)
        return Response(
            open(output_path, "rb").read(),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"inline; filename=passport_{car['plate_number']}.pdf"}
        )
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


@app.route("/sw.js")
def service_worker():
    """Service worker обязательно отдаётся с корня (не из /static/), иначе
    его область действия (scope) ограничится только папкой /static/ и он
    не сможет ничего перехватывать на реальных страницах приложения."""
    response = Response(
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sw.js")).read(),
        mimetype="application/javascript",
    )
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
    "plate_ocr.onnx": "application/octet-stream",
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


@app.route("/api/forgot_password/request", methods=["POST"])
def api_forgot_password_request():
    """Первый шаг восстановления пароля — отправляет 6-значный код в
    привязанный Telegram точки. Если Telegram не привязан, честно говорит
    об этом (это не секретная информация — точка и так это знает),
    предлагая обратиться к администратору."""
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"ok": False, "error": "укажите логин"}), 400
    shop = db.find_shop_by_username(username)
    if not shop:
        return jsonify({"ok": False, "error": "точка с таким логином не найдена"}), 404
    if not shop.get("notify_telegram_id"):
        return jsonify({"ok": False, "error": "к этой точке не привязан Telegram — обратитесь к администратору платформы для сброса пароля", "no_telegram": True}), 400
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


# ---------- Справка (раздел «Справка» / «Yordam») ----------
# Общие куски для панели точки и для /admin/help. Статьи — в help_content.py.
HELP_CSS = """
  #view-help { max-width:760px; }
  .hp-head { background:var(--darkblue); color:#fff; border-radius:20px; padding:18px 16px 16px; margin-bottom:12px; }
  .hp-head h2 { margin:0; font-family:var(--font-display); font-size:24px; font-weight:700; letter-spacing:-.01em; }
  .hp-head .hp-for { font-size:13px; color:#B9CBEA; margin-top:3px; }
  .hp-search { position:relative; margin-top:14px; }
  .hp-search i { position:absolute; left:14px; top:50%; transform:translateY(-50%); color:#64748B; font-size:15px; pointer-events:none; }
  .hp-search input { width:100%; height:48px; border:0; border-radius:14px; padding:0 14px 0 40px; font-size:16px; font-family:inherit; background:#fff; color:var(--text); }
  .hp-search input:focus { outline:3px solid #7DB2FF; }
  .hp-chips { display:flex; gap:6px; overflow-x:auto; padding:2px 0 10px; scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .hp-chips::-webkit-scrollbar { display:none; }
  .hp-chip { flex:none; display:flex; align-items:center; gap:6px; height:36px; padding:0 12px; border-radius:18px; border:1px solid var(--border); background:#fff; color:var(--darkblue); font-size:13px; font-weight:600; font-family:inherit; cursor:pointer; }
  .hp-chip i { color:var(--blue); font-size:12px; }
  .hp-sec { margin-bottom:16px; scroll-margin-top:12px; }
  .hp-sec-h { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:700; color:#64748B; margin:0 4px 8px; }
  .hp-sec-h i { color:var(--blue); }
  .hp-list { background:#fff; border:1px solid var(--border); border-radius:16px; overflow:hidden; }
  details.hp-art + details.hp-art { border-top:1px solid #EEF2F7; }
  details.hp-art > summary { list-style:none; display:flex; align-items:center; gap:10px; padding:14px 16px; cursor:pointer; font-weight:600; font-size:15px; line-height:1.35; color:var(--darkblue); -webkit-tap-highlight-color:transparent; }
  details.hp-art > summary::-webkit-details-marker { display:none; }
  details.hp-art > summary span { flex:1; min-width:0; }
  details.hp-art > summary .fa-chevron-down { color:#94A3B8; font-size:12px; transition:transform .2s; }
  details.hp-art[open] > summary { color:var(--blue); }
  details.hp-art[open] > summary .fa-chevron-down { transform:rotate(180deg); }
  .hp-body { padding:0 16px 16px; font-size:14.5px; line-height:1.6; color:#334155; }
  .hp-body p { margin:0 0 10px; }
  .hp-body ul { margin:0 0 10px; padding-left:20px; }
  .hp-body li { margin-bottom:5px; }
  .hp-body b { color:var(--darkblue); }
  .hp-body ol.hp-steps { list-style:none; counter-reset:hps; margin:0 0 12px; padding:0; }
  .hp-body ol.hp-steps > li { counter-increment:hps; position:relative; padding:2px 0 0 36px; margin-bottom:10px; min-height:26px; }
  .hp-body ol.hp-steps > li::before { content:counter(hps); position:absolute; left:0; top:0; width:26px; height:26px; border-radius:8px; background:#E8F0FD; color:var(--blue); font-weight:700; font-size:13px; display:flex; align-items:center; justify-content:center; }
  .hp-body ol.hp-steps ul { margin-top:6px; }
  .hp-tip, .hp-warn { border-radius:12px; padding:10px 12px; margin:4px 0 12px; font-size:14px; }
  .hp-tip { background:#EEF5FF; color:#123E7C; }
  .hp-warn { background:#FFF6E0; color:#7A4A00; }
  .hp-tip b, .hp-warn b { color:inherit; }
  .hp-go { display:inline-flex; align-items:center; gap:6px; height:38px; padding:0 14px; border-radius:10px; border:1px solid #C9DBF7; background:#fff; color:var(--blue); font-weight:600; font-size:14px; font-family:inherit; cursor:pointer; }
  .hp-empty { background:#fff; border:1px solid var(--border); border-radius:16px; padding:18px 16px; color:#64748B; font-size:14px; }
  .hp-foot { text-align:center; color:#64748B; font-size:13px; padding:6px 0 18px; }
  .hp-foot a { color:var(--blue); font-weight:600; }
  .hp-hidden { display:none !important; }
"""

HELP_VIEW = """
  <div class="hp-head">
    <h2>{{ T.tab_help }}</h2>
    <div class="hp-for">{{ T.help_for }} {{ help_role }}</div>
    <div class="hp-search">
      <i class="fa-solid fa-magnifying-glass"></i>
      <input id="hpSearch" type="search" autocomplete="off" spellcheck="false" placeholder="{{ T.help_search_ph }}" oninput="helpSearch(this.value)">
    </div>
  </div>
  <div class="hp-chips" id="hpChips">
    {% for s in help_sections %}<button type="button" class="hp-chip" onclick="helpJump('{{ s.key }}')"><i class="fa-solid {{ s.icon }}"></i>{{ s.title }}</button>{% endfor %}
  </div>
  <div id="hpEmpty" class="hp-empty hp-hidden">{{ T.help_nothing }}</div>
  {% for s in help_sections %}
  <div class="hp-sec" id="hp-sec-{{ s.key }}">
    <div class="hp-sec-h"><i class="fa-solid {{ s.icon }}"></i>{{ s.title }}</div>
    <div class="hp-list">
      {% for a in s.articles %}
      <details class="hp-art" id="hp-{{ a.id }}" data-kw="{{ a.kw }}">
        <summary><span>{{ a.title }}</span><i class="fa-solid fa-chevron-down"></i></summary>
        <div class="hp-body">{{ a.body|safe }}
          {% if a.go %}<button type="button" class="hp-go" onclick="showTab('{{ a.go }}')">{{ T.help_open }} «{{ T['tab_' ~ a.go] }}» <i class="fa-solid fa-arrow-right"></i></button>{% endif %}
        </div>
      </details>
      {% endfor %}
    </div>
  </div>
  {% endfor %}
  {% if help_support %}<div class="hp-foot">{{ T.help_support }} {% if help_support_url %}<a href="{{ help_support_url }}" target="_blank" rel="noopener">{{ help_support }}</a>{% else %}<b>{{ help_support }}</b>{% endif %}</div>{% endif %}
"""

HELP_JS = """
<script>
function helpNorm(s) { return (s || '').toLowerCase().split('ё').join('е').split('ʻ').join("'").split('‘').join("'").split('’').join("'"); }
let HELP_INDEX = null;
function helpBuildIndex() {
  HELP_INDEX = [];
  document.querySelectorAll('#view-help details.hp-art').forEach(d => {
    HELP_INDEX.push({ el: d, text: helpNorm(d.textContent + ' ' + (d.dataset.kw || '')) });
  });
}
function helpSearch(q) {
  if (!HELP_INDEX) helpBuildIndex();
  const words = helpNorm(q).trim().split(' ').filter(w => w.length > 0);
  const active = words.length > 0 && helpNorm(q).trim().length >= 2;
  let found = 0;
  HELP_INDEX.forEach(it => {
    const ok = !active || words.every(w => it.text.indexOf(w) !== -1);
    it.el.classList.toggle('hp-hidden', !ok);
    if (ok) found++;
    if (active) it.el.open = ok && found <= 3;
  });
  document.querySelectorAll('#view-help .hp-sec').forEach(sec => {
    sec.classList.toggle('hp-hidden', !sec.querySelector('details.hp-art:not(.hp-hidden)'));
  });
  const chips = document.getElementById('hpChips');
  if (chips) chips.classList.toggle('hp-hidden', active);
  document.getElementById('hpEmpty').classList.toggle('hp-hidden', found > 0);
  if (!active) HELP_INDEX.forEach(it => { it.el.open = false; });
}
function helpJump(key) {
  const sec = document.getElementById('hp-sec-' + key);
  if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
</script>
"""

PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{{ shop_name }} — OilBook</title>
<link rel="manifest" href="/static/manifest.json">
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
<script>
// скрипт Telegram нужен, только если панель открыта внутри Telegram —
// в обычном приложении/браузере его не грузим (раньше он держал белый экран)
if (window.TelegramWebviewProxy || location.hash.indexOf('tgWebApp') !== -1) {
  const s = document.createElement('script');
  s.src = 'https://telegram.org/js/telegram-web-app.js';
  s.onload = () => { if (window.Telegram && Telegram.WebApp) { Telegram.WebApp.ready(); Telegram.WebApp.expand(); } };
  document.head.appendChild(s);
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&display=swap"></noscript>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"></noscript>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #F1F5F9);
    --text: var(--tg-theme-text-color, #1E293B);
    --hint: var(--tg-theme-hint-color, #94A3B8);
    --btn: var(--tg-theme-button-color, #E63946);
    --btn-text: var(--tg-theme-button-text-color, #FFFFFF);
    --blue: #0F52BA;
    --darkblue: #0A2540;
    --cyan: #00A8E8;
    --darkred: #9B111E;
    --carbon: #181E29;
    --card: #FFFFFF;
    --border: #E2E8F0;
    --field-bg: #F4F7FA;
    --ok: #059669;
    --ok-bg: #ECFDF5;
    --danger: #B3241C;
    --danger-bg: #FDECEA;
    --accent2: #0F52BA;
    --font-display: 'Space Grotesk', sans-serif;
    --font-body: 'Plus Jakarta Sans', -apple-system, sans-serif;
    --font-mono: 'IBM Plex Mono', monospace;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: var(--font-body); }
  .speedline {
    height:6px; width:100%;
    background: linear-gradient(90deg, var(--blue) 0%, var(--blue) 33%, #fff 33%, #fff 38%, var(--btn) 38%, var(--btn) 70%, #fff 70%, #fff 75%, var(--cyan) 75%, var(--cyan) 100%);
  }
  .container { padding: 12px; max-width: 960px; margin: 0 auto; }
  .topbar { display:flex; justify-content:space-between; align-items:center; margin: 14px 0 16px; }
  .logo-badge {
    display:inline-flex; align-items:center; justify-content:center; width:40px; height:40px;
    background:var(--darkblue); color:var(--cyan); border-radius:12px; transform:rotate(-8deg);
    box-shadow:0 4px 10px rgba(10,37,64,.25); font-size:16px; flex:none;
  }
  h1 { font-family: var(--font-display); font-weight:800; font-style:italic; letter-spacing:-0.3px; font-size: 22px; margin: 0; line-height:1.1; color:var(--darkblue); }
  h1 .accent { color:var(--btn); }
  .logo-sub { font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:var(--hint); }
  .brand-line { text-transform:none; letter-spacing:0; font-size:12px; display:flex; align-items:baseline; gap:4px; flex-wrap:wrap; margin-top:2px; }
  .brand-line .role-tag { font-size:11px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }
  .wordmark { font-family:'Sora', var(--font-display), sans-serif; font-style:normal; font-weight:800; font-size:17px; letter-spacing:-0.4px; line-height:1; white-space:nowrap; }
  .wordmark .wm-oil { background:linear-gradient(135deg, #0EA5E9 0%, #1D4ED8 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .wordmark .wm-book { color:#0B1B3A; }
  .logout { color: var(--btn); font-size: 12px; font-weight:700; text-decoration:none; background:var(--danger-bg); padding:6px 10px; border-radius:10px; }
  .lang-btn { background: #EFF6FF; border: 1px solid #BFDBFE; color: var(--blue); font-size: 12px; font-weight:700; padding: 6px 10px; border-radius: 10px; cursor: pointer; }
  .tabs { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; margin-bottom: 10px; }
  /* ---- навигация: телефон ---- */
  .container { padding-bottom: calc(96px + env(safe-area-inset-bottom, 0px)); }
  .topbar { margin: 10px 0 12px; gap:10px; }
  .topbar h1 { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .side-nav { display:none; }
  .role-tag { color:#B45309; }
  .bottom-bar { position:fixed; left:0; right:0; bottom:0; z-index:50; display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); background:rgba(255,255,255,0.97); border-top:1px solid var(--border); padding:6px 4px calc(6px + env(safe-area-inset-bottom, 0px)); box-shadow:0 -4px 16px rgba(15,23,42,0.06); }
  .bb-item { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:3px; min-height:50px; font-size:11px; font-weight:600; color:#64748B; cursor:pointer; -webkit-tap-highlight-color:transparent; user-select:none; }
  .bb-item i { font-size:19px; }
  .bb-item span { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bb-item.active { color:var(--blue); }
  .bb-item.active:not(.bb-add)::before { content:''; position:absolute; top:-6px; width:28px; height:3px; border-radius:2px; background:var(--blue); }
  .bb-plus { width:48px; height:48px; margin-top:-22px; border-radius:50%; background:var(--btn); color:#fff; display:flex; align-items:center; justify-content:center; box-shadow:0 6px 14px rgba(200,30,43,0.35); border:3px solid #fff; }
  .bb-plus i { font-size:20px; }
  .bb-add.active span { color:var(--btn); }
  .nav-badge { display:none; position:absolute; top:0; right:calc(50% - 22px); min-width:17px; height:17px; padding:0 4px; border-radius:9px; background:var(--btn); color:#fff; font-size:10px; font-weight:800; line-height:17px; text-align:center; }
  .nav-badge.show { display:block; }
  .more-backdrop { position:fixed; inset:0; background:rgba(15,23,42,0.35); z-index:60; opacity:0; pointer-events:none; transition:opacity .2s; }
  .more-backdrop.open { opacity:1; pointer-events:auto; }
  .more-sheet { position:fixed; left:0; right:0; bottom:0; z-index:61; background:#fff; border-radius:20px 20px 0 0; padding:8px 14px calc(14px + env(safe-area-inset-bottom, 0px)); transform:translateY(105%); transition:transform .25s ease; box-shadow:0 -10px 30px rgba(15,23,42,0.15); max-height:80vh; overflow-y:auto; }
  .more-sheet:not(.open) { visibility:hidden; transition:transform .25s ease, visibility 0s .25s; }
  .more-sheet.open { transform:translateY(0); visibility:visible; }
  .more-grab { width:40px; height:5px; border-radius:3px; background:#CBD5E1; margin:2px auto 10px; }
  .more-item { position:relative; display:flex; align-items:center; gap:14px; padding:14px 6px; border-bottom:1px solid #F1F5F9; font-size:15px; font-weight:600; color:var(--text); cursor:pointer; text-decoration:none; }
  .more-item i { width:22px; text-align:center; font-size:18px; color:#64748B; }
  .more-item.active, .more-item.active i { color:var(--blue); }
  .more-item.hidden-in-more { display:none; }
  .more-item .nav-badge { position:static; margin-left:auto; }
  .more-logout, .more-logout i { color:var(--btn); border-bottom:none; }
  /* ---- навигация: планшет и компьютер ---- */
  @media (min-width: 900px) {
    .bottom-bar, .more-sheet, .more-backdrop, .topbar { display:none !important; }
    .container { padding-bottom:24px; margin-left:240px; max-width:1100px; padding-left:24px; padding-right:24px; }
    .side-nav { display:flex; flex-direction:column; position:fixed; top:6px; left:0; bottom:0; width:232px; background:#fff; border-right:1px solid var(--border); padding:16px 12px; z-index:40; overflow-y:auto; }
    .side-brand { display:flex; align-items:center; gap:10px; padding:4px 6px 16px; border-bottom:1px solid #F1F5F9; margin-bottom:10px; }
    .side-shop { font-family:var(--font-display); font-weight:800; font-style:italic; font-size:18px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .side-list { display:flex; flex-direction:column; gap:2px; }
    .side-item { position:relative; display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:10px; font-size:14px; font-weight:600; color:#475569; cursor:pointer; }
    .side-item i { width:18px; text-align:center; color:#94A3B8; }
    .side-item:hover { background:#F8FAFC; }
    .side-item.active { background:#EFF6FF; color:var(--blue); }
    .side-item.active i { color:var(--blue); }
    .side-add { background:var(--danger-bg); color:var(--btn); margin-bottom:8px; }
    .side-add i { color:var(--btn); }
    .side-add.active { background:var(--btn); color:#fff; }
    .side-add.active i { color:#fff; }
    .side-item .nav-badge { position:static; margin-left:auto; }
    .side-foot { margin-top:auto; padding-top:14px; border-top:1px solid #F1F5F9; display:flex; flex-direction:column; gap:8px; }
    .side-foot .lang-btn, .side-foot .logout { text-align:center; padding:9px 10px; display:block; }
  }
  .subtabs { display:flex; gap:8px; margin-bottom:14px; }
  .subtab {
    flex:1; text-align:center; padding:10px; border-radius:10px; background:var(--field-bg);
    border:1.5px solid var(--border); cursor:pointer; font-weight:700; font-size:13px; color:var(--hint);
  }
  .subtab.active { background:var(--btn); color:#fff; border-color:var(--btn); }
  .tab {
    text-align:center; padding: 10px 4px; border-radius: 14px; background: var(--card);
    border:2px solid var(--border); cursor:pointer; font-weight:700; font-family: var(--font-display);
    font-size:11px; text-transform:uppercase; letter-spacing:0.2px; transition: all .15s ease;
    display:flex; flex-direction:column; align-items:center; gap:5px;
    box-shadow: 0 1px 3px rgba(20,20,25,.04);
  }
  .tab .tab-icon {
    width:30px; height:30px; border-radius:50%; background:var(--field-bg); color:var(--blue);
    display:flex; align-items:center; justify-content:center; font-size:13px; flex:none; transition: all .15s ease;
  }
  .tab#tab-add { border-color:var(--btn); }
  .tab#tab-add .tab-icon { background:var(--danger-bg); color:var(--btn); }
  .tab#tab-add span:last-child { color:var(--btn); }
  .tab.active { color: var(--btn); }
  .tab.active .tab-icon { background:var(--btn); color:#fff; transform:scale(1.08); }
  .wh-banner {
    width:100%; background:var(--carbon); border:2px solid #0d1117; border-radius:16px; padding:12px 16px;
    display:flex; align-items:center; justify-content:center; gap:12px; cursor:pointer; margin-bottom:12px;
    box-shadow:0 8px 20px rgba(0,0,0,.25);
  }
  .wh-banner .stripe-pair { display:flex; gap:4px; }
  .wh-banner .stripe-pair span { width:8px; height:26px; border-radius:2px; transform:skewX(-12deg); }
  .wh-banner .wh-label { font-family:var(--font-display); font-weight:800; font-style:italic; font-size:18px; color:#fff; text-transform:uppercase; letter-spacing:0.5px; }
  .card {
    background: #fff; border:2px solid #DBEAFE; border-radius: 22px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 10px 25px -5px rgba(15,82,186,.08); overflow:hidden;
  }
  .field { margin-bottom: 10px; }
  .row2 { display:flex; gap:10px; }
  .row2 .field { flex:1; }
  label { display:block; font-size: 12px; color: var(--hint); margin-bottom: 4px; text-transform:uppercase; letter-spacing:0.4px; }
  label i { color:var(--btn); margin-right:4px; width:12px; text-align:center; }
  input, select, textarea {
    width: 100%; padding: 10px; border-radius: 10px; border: 1.5px solid var(--border);
    background: var(--field-bg); color: var(--text); font-size: 15px; font-family: var(--font-body);
  }
  input:focus, select:focus, textarea:focus { outline:none; border-color: var(--btn); box-shadow:0 0 0 3px rgba(225,6,0,.12); }
  .card-header {
    background:linear-gradient(90deg, var(--blue), #1a6fd4); color:#fff; padding:14px 16px; border-radius:20px 20px 0 0; margin:-16px -16px 14px;
    display:flex; align-items:center; gap:10px;
  }
  .card-header .dot { width:9px; height:9px; border-radius:50%; background:var(--btn); flex:none; box-shadow:0 0 0 4px rgba(225,6,0,.25); animation: pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.4; } }
  .card-header h3 { margin:0; font-family:var(--font-display); font-weight:700; font-style:italic; font-size:17px; letter-spacing:0.3px; text-transform:uppercase; }
  .plate-wrap { position:relative; }
  .plate-chip {
    position:absolute; left:10px; top:50%; transform:translateY(-50%);
    font-size:11px; font-weight:700; color:var(--hint); background:var(--border); padding:2px 6px; border-radius:5px;
  }
  #plate { padding-left:44px; font-family:var(--font-mono); font-weight:600; letter-spacing:1px; text-transform:uppercase; }
  .plate-suggest {
    position:absolute; top:100%; left:0; right:0; margin-top:4px; background:var(--card);
    border:1.5px solid var(--border); border-radius:12px; box-shadow:0 8px 20px rgba(20,20,25,.12);
    z-index:20; overflow:hidden; max-height:240px; overflow-y:auto;
  }
  .plate-suggest .ps-item { padding:10px 14px; cursor:pointer; border-bottom:1px solid var(--border); }
  .plate-suggest .ps-item:last-child { border-bottom:none; }
  .plate-suggest .ps-item:active, .plate-suggest .ps-item:hover { background:var(--field-bg); }
  .plate-suggest .ps-plate { font-family:var(--font-mono); font-weight:700; font-size:14px; letter-spacing:0.5px; color:var(--text); }
  .plate-suggest .ps-owner { font-size:12px; color:var(--hint); margin-top:2px; }
  .checkbox-row { display:flex; align-items:center; gap:8px; }
  .checkbox-row input { width:auto; }
  .item-row { display:flex; gap:8px; align-items:center; margin-bottom:8px; }
  .item-row .item-name { flex:1.3; font-size:13px; color:var(--hint); min-width:0; }
  .item-row input { flex:1; padding:8px; font-size:13px; min-width:0; }
  .item-row select { flex:1.6; padding:8px; font-size:13px; min-width:0; }
  .other-stock-row { display:flex; gap:6px; align-items:center; margin-bottom:8px; }
  .other-stock-row select { flex:2; padding:8px; font-size:13px; min-width:0; }
  .other-stock-row input { flex:1; padding:8px; font-size:13px; min-width:0; }
  .other-stock-row button { flex:none; width:32px; height:32px; border-radius:8px; border:none; background:var(--danger-bg); color:var(--danger); font-size:14px; cursor:pointer; }
  .item-row .item-total { flex:0.9; font-size:12px; color:var(--hint); text-align:right; }
  .pick-search { margin:2px 0 14px; }
  .pick-search input { width:100%; }
  .pick-results { margin-top:6px; }
  .pick-item { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:10px 12px; border:1px solid var(--border); border-radius:10px; margin-bottom:6px; background:var(--field-bg); cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .pick-item:active { transform:scale(.99); border-color:var(--blue); }
  .pick-item .pi-main { min-width:0; }
  .pick-item .pi-name { font-size:14px; font-weight:600; color:var(--text); overflow-wrap:anywhere; }
  .pick-item .pi-sub { font-size:12px; color:var(--hint); margin-top:2px; }
  .pick-item .pi-sub .pi-out { color:var(--danger); font-weight:600; }
  .pick-item .pi-price { flex:none; font-size:13px; font-family:var(--font-mono); color:var(--blue); font-weight:600; text-align:right; }
  .pick-note { font-size:13px; color:var(--hint); padding:4px 2px; }
  .pick-note.ok { color:var(--ok); font-weight:600; }
  .pick-flash { animation:pickFlash 1.4s ease; border-radius:10px; }
  @keyframes pickFlash { 0% { background:rgba(15,82,186,.20); } 60% { background:rgba(15,82,186,.12); } 100% { background:transparent; } }
  button.submit {
    width: 100%; padding: 14px; border: none; border-radius: 14px;
    background: linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #312E81 100%); color:#fff; font-size: 15px; font-weight: 700; font-family: var(--font-display);
    letter-spacing:0.5px; text-transform:uppercase; cursor: pointer; margin-top: 6px;
    box-shadow: 0 8px 18px rgba(29,78,216,.30);
  }
  button.submit:active { transform:scale(.98); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color:#fff; font-weight: 700; position: sticky; top: 0; background: #1E293B; font-family: var(--font-body); letter-spacing:0.4px; font-size:10px; text-transform:uppercase; }
  .table-wrap { overflow-x: auto; border:1px solid var(--border); border-radius: 12px; }
  .badge { display:inline-block; padding: 3px 9px; border-radius: 20px; font-size: 11px; font-weight:600; cursor:pointer; border:none; text-transform:uppercase; letter-spacing:0.3px; }
  .badge.linked { background: var(--ok-bg); color: var(--ok); }
  .badge.unlinked { background: var(--danger-bg); color: var(--danger); }
  .search { margin-bottom: 10px; }
  .hint-text { color: var(--hint); font-size: 12px; margin-top: 6px; }
  .msg { padding: 12px; border-radius: 10px; margin-bottom: 10px; font-size: 14px; }
  .msg.ok { background:var(--ok-bg); color:var(--ok); }
  .msg.err { background:var(--danger-bg); color:var(--danger); }
  .modal-overlay { display:none; position:fixed; inset:0; background:rgba(20,20,25,.55); align-items:center; justify-content:center; z-index:50; }
  .modal-overlay.open { display:flex; }
  .modal { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:18px; max-width:320px; width:90%; text-align:center; box-shadow: 0 12px 34px rgba(20,20,25,.25); }
  .modal-wide { max-width:480px; max-height:85vh; overflow-y:auto; }
  .modal img { width:180px; height:180px; margin: 10px auto; display:block; border-radius:10px; background:#fff; }
  .modal .link-text { font-size:12px; word-break:break-all; color:var(--hint); background:var(--field-bg); padding:8px; border-radius:10px; margin-bottom:10px; }
  .modal button { margin-top:8px; }
  .modal a.wa-btn { display:block; text-decoration:none; }
  .close-btn { background:transparent; border:none; color:var(--hint); font-size:14px; cursor:pointer; margin-top:6px; width:100%; padding:8px; }
  .history-toggle { background:transparent; border:none; color:var(--btn); font-size:12px; cursor:pointer; text-decoration:underline; padding:0; }
  .history-entry { padding:6px 0; border-bottom:1px dashed var(--border); font-size:12px; }
  .stats-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:10px; }
  .stats-card {
    background:linear-gradient(135deg, #EFF6FF, #EEF2FF); border:1px solid #DBEAFE; border-radius:16px; padding:14px;
    text-align:center;
  }
  .stats-card .label { font-size:10px; color:#64748B; margin-bottom:4px; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; }
  .stats-card .amount { font-size:22px; font-weight:800; color:var(--blue); font-family: var(--font-display); }
  .stats-card .count { font-size:11px; color:var(--hint); margin-top:4px; }
  .known-client {
    margin-top:12px; background:var(--card); border:2px solid #BFDBFE; border-radius:18px;
    overflow:hidden; box-shadow: 0 6px 16px rgba(15,82,186,.08);
  }
  .cross-network-card {
    margin-top:12px; background:var(--card); border:1.5px solid #A7F3D0; border-radius:16px;
    padding:14px; box-shadow: 0 4px 12px rgba(5,150,105,.06);
  }
  .cross-network-card .cn-header {
    display:flex; align-items:center; gap:8px; color:#047857; font-weight:700; font-size:13.5px; margin-bottom:4px;
  }
  .cross-network-card .cn-hint { font-size:11.5px; color:var(--hint); margin-bottom:10px; }
  .cross-network-card .cn-entry {
    background:var(--field-bg); border-radius:10px; padding:10px 12px; margin-bottom:6px;
  }
  .cross-network-card .cn-entry:last-child { margin-bottom:0; }
  .cross-network-card .cn-entry-shop { font-size:13px; font-weight:700; color:var(--text); }
  .cross-network-card .cn-entry-date { font-size:11.5px; color:var(--hint); margin-top:1px; }
  .cross-network-card .kc-lv-items { margin-top:6px; padding-top:6px; border-top:1px dashed var(--border); }
  .cross-network-card .kc-lv-item { font-size:12px; color:var(--text); padding:1px 0; }
  .known-client .kc-header {
    background:linear-gradient(90deg, var(--blue), #1a6fd4); color:#fff; padding:12px 14px;
    display:flex; align-items:center; gap:8px;
  }
  .known-client .kc-header i { font-size:15px; }
  .known-client .kc-header span { font-family:var(--font-display); font-weight:700; font-style:italic; font-size:14px; text-transform:uppercase; letter-spacing:0.3px; }
  .known-client .kc-body { padding:16px; }
  .known-client .kc-person { display:flex; align-items:center; gap:14px; margin-bottom:16px; }
  .known-client .kc-avatar {
    width:58px; height:58px; border-radius:50%; background:var(--field-bg); color:var(--blue);
    display:flex; align-items:center; justify-content:center; font-family:var(--font-display);
    font-weight:700; font-size:22px; flex:none; border:2px solid #DBEAFE;
  }
  .known-client .kc-name { font-size:18px; font-weight:700; color:var(--text); line-height:1.25; }
  .known-client .kc-meta { font-size:13px; color:var(--hint); margin-top:3px; }
  .known-client .kc-history-label { font-size:11px; font-weight:700; color:var(--hint); text-transform:uppercase; letter-spacing:0.4px; margin-bottom:8px; }
  .known-client .kc-last-visit {
    background:var(--field-bg); border-radius:12px; padding:11px 13px; margin-bottom:14px;
  }
  .known-client .kc-last-visit .kc-lv-top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .known-client .kc-last-visit .kc-lv-service { font-size:14px; font-weight:700; color:var(--text); }
  .known-client .kc-last-visit .kc-lv-date { font-size:12px; color:var(--hint); margin-top:2px; }
  .known-client .kc-lv-mileage { font-size:12px; color:var(--blue); font-weight:600; margin-top:8px; }
  .mileage-compare { font-size:12.5px; margin-top:6px; padding:8px 10px; border-radius:8px; }
  .mileage-compare.over { background:#FEF2F2; color:#B3241C; font-weight:600; }
  .mileage-compare.ok { background:#F0FDF4; color:#15803D; }
  .known-client .kc-last-visit .kc-lv-cost { font-size:16px; font-weight:700; color:var(--blue); flex:none; }
  .known-client .kc-lv-items { margin-top:9px; padding-top:9px; border-top:1px dashed var(--border); }
  .kc-repeat { width:100%; margin-top:10px; padding:11px 12px; border:none; border-radius:12px; background:#16A34A; color:#fff; font-weight:800; font-size:14px; font-family:inherit; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; }
  .kc-repeat:active { transform:scale(.98); }
  .kc-new-owner { margin:8px 0 12px; padding:6px 0; border:none; background:none; color:var(--hint); font-size:12.5px; font-weight:600; font-family:inherit; cursor:pointer; display:inline-flex; align-items:center; gap:6px; text-decoration:underline; }
  .kc-new-owner-box { margin-bottom:12px; padding:12px; border-radius:12px; background:#FEF3C7; color:#78350F; font-size:13px; line-height:1.4; }
  .kc-new-owner-box b { display:block; font-size:14px; margin-bottom:4px; }
  .kc-new-owner-box button { margin-top:8px; padding:7px 12px; border:1px solid #D97706; border-radius:10px; background:#fff; color:#92400E; font-weight:700; font-size:12.5px; font-family:inherit; cursor:pointer; }
  .km-chips { display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }
  .dk-row { display:flex; align-items:center; gap:8px; }
  .dk-row input { flex:1; min-width:0; }
  .dk-unit { font-size:13px; color:var(--hint); white-space:nowrap; }
  #dkSuggest .km-chip { margin-top:6px; }
  .dk-hint { font-size:12.5px; color:#475569; margin-top:6px; line-height:1.45; }
  .dk-hint b { color:var(--blue); }
  .km-chip { border:1px solid var(--border); background:#fff; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; color:#475569; cursor:pointer; font-family:inherit; }
  .km-chip.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .add-form { max-width:760px; }
  .af-title { display:flex; align-items:center; gap:10px; font-family:var(--font-display); font-weight:700; font-style:italic; font-size:18px; text-transform:uppercase; letter-spacing:.3px; color:var(--darkblue, #0A2540); margin:2px 4px 10px; }
  .af-title .dot { width:9px; height:9px; border-radius:50%; background:var(--btn); flex:none; box-shadow:0 0 0 4px rgba(225,6,0,.18); }
  .af-sec { background:#fff; border:1px solid #E2E8F0; border-radius:18px; padding:14px; margin-bottom:12px; box-shadow:0 4px 14px -6px rgba(15,82,186,.10); }
  .af-h { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:800; color:#0F172A; text-transform:uppercase; letter-spacing:.5px; margin-bottom:12px; }
  .af-h i { width:28px; height:28px; border-radius:9px; background:#EFF6FF; color:var(--blue); display:inline-flex; align-items:center; justify-content:center; font-size:13px; }
  .af-sub { font-size:12px; color:var(--hint); text-transform:uppercase; letter-spacing:.4px; margin:12px 0 6px; }
  .mil-grid { display:grid; grid-template-columns:minmax(0,1fr) 22px minmax(0,1fr); gap:6px; align-items:end; }
  .mil-arrow { text-align:center; color:#94A3B8; padding-bottom:14px; font-size:13px; }
  .mil-l { font-size:12px; color:var(--hint); margin-bottom:5px; }
  .mil-f { position:relative; }
  .mil-f input { padding-right:62px; font-size:18px; font-weight:700; font-family:var(--font-mono); }
  .mil-f input::-webkit-outer-spin-button, .mil-f input::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
  .mil-f input[type=number] { -moz-appearance:textfield; }
  .mil-f span { position:absolute; right:12px; top:50%; transform:translateY(-50%); font-size:12px; color:var(--hint); pointer-events:none; }
  .mil-f.accent input { border-color:#93C5FD; background:#F8FBFF; }
  .km-seg { display:grid !important; grid-template-columns:repeat(auto-fit, minmax(64px, 1fr)); gap:4px; background:#EEF2F7; border-radius:12px; padding:4px; margin-top:10px; }
  .km-seg .km-chip { border:0; background:transparent; border-radius:9px; padding:9px 4px; font-size:13px; color:#475569; }
  .km-seg .km-chip.on { background:var(--blue); color:#fff; box-shadow:0 2px 6px rgba(15,82,186,.25); }
  .dk-hint:not(:empty) { background:#ECFDF5; color:#065F46; border-radius:10px; padding:9px 11px; font-size:13px; margin-top:8px; }
  .dk-hint b { color:#047857 !important; }
  .af-add { display:flex; flex-wrap:wrap; gap:6px; margin-top:4px; }
  .af-add:empty { display:none; }
  .af-add button { border:1.5px dashed #CBD5E1; background:#fff; color:#334155; border-radius:999px; padding:6px 11px; font-size:12.5px; font-weight:700; cursor:pointer; font-family:inherit; }
  .af-add button i { color:var(--blue); margin-right:3px; }
  .add-form .item-row { gap:5px; }
  .add-form .item-row .item-name { flex:1 !important; font-size:12.5px; line-height:1.2; }
  .add-form .item-row input { padding:8px 6px; }
  .add-form .item-row select { flex:1.5; padding:8px 4px; }
  .item-row .row-x { flex:none; width:26px; height:34px; border:0; background:transparent; color:#94A3B8; font-size:15px; cursor:pointer; border-radius:8px; }
  .item-row .row-x:hover { background:#F1F5F9; color:var(--btn); }
  .af-ghost { width:100%; padding:9px; border:1.5px dashed #CBD5E1; background:#fff; border-radius:12px; color:#334155; font-weight:700; font-size:13px; cursor:pointer; font-family:inherit; }
  .pay-seg { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:6px; }
  @media (min-width:480px) { .pay-seg { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .pay-seg button { border:1.5px solid var(--border); background:#fff; border-radius:12px; padding:10px 6px; font-size:13px; font-weight:700; color:#334155; cursor:pointer; font-family:inherit; }
  .pay-seg button.on { border-color:var(--blue); background:#EFF6FF; color:var(--blue); }
  .af-bar { position:sticky; bottom:calc(76px + env(safe-area-inset-bottom, 0px)); z-index:20; display:flex; align-items:center; gap:12px; background:#fff; border:1px solid #E2E8F0; border-radius:18px; padding:10px 10px 10px 16px; box-shadow:0 8px 24px rgba(15,23,42,.14); margin-top:4px; }
  @media (min-width:900px) { .af-bar { bottom:14px; } }
  .af-bar-total { flex:1; min-width:0; }
  .af-bar-total span { display:block; font-size:11px; color:var(--hint); text-transform:uppercase; letter-spacing:.4px; }
  .af-bar-total b { display:block; font-size:21px; font-weight:800; font-family:var(--font-mono); color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .af-save { flex:none; border:0; border-radius:14px; padding:13px 20px; background:linear-gradient(135deg, #E63946, #C1121F); color:#fff; font-size:15px; font-weight:800; font-family:var(--font-display); cursor:pointer; box-shadow:0 6px 14px rgba(230,57,70,.30); }
  .known-client .kc-lv-item {
    display:flex; justify-content:space-between; gap:8px; font-size:12.5px; color:var(--text);
    padding:3px 0;
  }
  .known-client .kc-lv-item span:last-child { color:var(--hint); flex:none; }
  .known-client .kc-action-btn {
    width:100%; padding:13px; border:none; border-radius:12px; background:linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #312E81 100%);
    color:#fff; font-size:15px; font-weight:700; font-family:var(--font-body); cursor:pointer;
    display:flex; align-items:center; justify-content:center; gap:8px; box-shadow:0 6px 14px rgba(29,78,216,.28);
  }
  .known-client .kc-action-hint { font-size:11.5px; color:var(--hint); text-align:center; margin-top:8px; }
  .car-card {
    background:var(--card); border:1.5px solid var(--border); border-radius:14px; padding:14px;
    margin-bottom:10px; cursor:pointer; transition:border-color .12s, box-shadow .12s;
  }
  .car-card:active { border-color:var(--blue); box-shadow:0 2px 10px rgba(15,82,186,.1); }
  .car-card .cc-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; gap:8px; }
  .car-card .cc-plate {
    font-family:var(--font-mono); font-weight:700; font-size:14.5px; letter-spacing:0.5px; color:var(--blue);
    background:var(--field-bg); padding:3px 9px; border-radius:7px; flex:none;
  }
  .car-card .cc-linkbtn { flex:none; }
  .car-card .cc-owner { font-size:15px; font-weight:700; color:var(--text); }
  .car-card .cc-meta { font-size:12.5px; color:var(--hint); margin-top:2px; }
  .car-card .cc-bottom {
    display:flex; justify-content:space-between; align-items:center; margin-top:10px;
    padding-top:10px; border-top:1px dashed var(--border);
  }
  .car-card .cc-cost { font-size:15px; font-weight:700; color:var(--blue); }
  .car-card .cc-cost-date { font-size:11px; color:var(--hint); font-weight:400; }
  .car-card .cc-next { font-size:11.5px; color:var(--hint); text-align:right; }
  .car-card .cc-chevron { color:var(--hint); font-size:13px; flex:none; }
  .debt-card { background:var(--card); border:1.5px solid var(--border); border-radius:14px; padding:14px; margin-bottom:10px; }
  .debt-card.overdue { border-color:#F87171; background:linear-gradient(135deg, #FFFFFF, #FEF2F2); }
  .debt-card .dc-top { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
  .debt-card .dc-owner { font-size:15px; font-weight:700; color:var(--text); }
  .debt-card .dc-meta { font-size:12.5px; color:var(--hint); margin-top:2px; }
  .debt-card .dc-remaining { font-size:18px; font-weight:700; color:var(--btn); font-family:var(--font-mono); text-align:right; }
  .debt-card .dc-due { font-size:11.5px; color:var(--hint); margin-top:2px; text-align:right; }
  .debt-card .dc-due.overdue-text { color:#B3241C; font-weight:700; }
  .debt-card .dc-pay-row { display:flex; gap:6px; margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); }
  .brand-chips { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; margin-bottom:12px; scrollbar-width:none; }
  .brand-chips::-webkit-scrollbar { display:none; }
  .brand-chip { flex:0 0 auto; border:1px solid var(--border); background:#fff; color:var(--text); border-radius:999px; padding:7px 12px; font-size:12.5px; font-weight:600; cursor:pointer; white-space:nowrap; }
  .brand-chip.active { background:var(--blue); border-color:var(--blue); color:#fff; }
  .brand-chip .bc-sub { font-weight:500; opacity:0.7; margin-left:4px; }
  .brand-period { display:inline-flex; background:#F1F5F9; border-radius:10px; padding:3px; margin-bottom:12px; }
  .brand-period button { border:none; background:transparent; padding:6px 12px; font-size:12.5px; font-weight:600; color:#64748B; border-radius:8px; cursor:pointer; }
  .brand-period button.active { background:#fff; color:var(--text); box-shadow:0 1px 2px rgba(15,23,42,0.12); }
  .brand-summary { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:14px; }
  .brand-summary div { background:#F8FAFC; border-radius:10px; padding:10px 8px; text-align:center; }
  .brand-summary b { display:block; font-size:16px; font-family:var(--font-display); color:var(--text); }
  .brand-summary span { font-size:11px; color:#64748B; }
  .brand-donut-wrap { position:relative; max-width:240px; margin:0 auto 16px; }
  .brand-row { padding:9px 0; border-bottom:1px solid #F1F5F9; }
  .brand-row:last-child { border-bottom:none; }
  .brand-row-top { display:flex; align-items:center; gap:8px; font-size:13.5px; }
  .brand-rank { width:22px; height:22px; border-radius:50%; color:#fff; font-size:11px; font-weight:700; display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
  .brand-name { flex:1; font-weight:600; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .brand-val { font-weight:700; color:var(--text); white-space:nowrap; }
  .brand-share { font-size:12px; color:#64748B; width:46px; text-align:right; }
  .brand-bar { height:6px; background:#F1F5F9; border-radius:3px; margin:6px 0 4px 30px; overflow:hidden; }
  .brand-bar i { display:block; height:100%; border-radius:3px; }
  .brand-meta { font-size:11.5px; color:#94A3B8; margin-left:30px; }
  .st-today { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px 16px; background:#fff; border:1px solid var(--border); border-radius:16px; padding:14px 18px; margin-bottom:12px; }
  .st-today-main { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  .st-today-label { font-size:13px; font-weight:600; color:#64748B; }
  .st-today-amount { font-size:24px; font-weight:800; font-family:var(--font-display); color:var(--text); }
  .st-today-amount small, .st-amount small { font-size:0.55em; font-weight:600; color:#64748B; margin-left:3px; }
  .st-today-chips { display:flex; gap:6px; flex-wrap:wrap; }
  .st-chip { background:#F1F5F9; border-radius:999px; padding:5px 11px; font-size:12.5px; color:#334155; }
  .st-chip b { color:var(--text); }
  .st-empty { font-size:13px; color:#94A3B8; }
  .st-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; }
  .st-card { background:#fff; border:1px solid var(--border); border-radius:16px; padding:16px 16px 12px; display:flex; flex-direction:column; }
  .st-card.orange { background:#FFFBF5; border-color:#FDBA74; }
  .st-label { font-size:13px; font-weight:600; color:#64748B; }
  .st-amount { font-size:26px; font-weight:800; font-family:var(--font-display); color:var(--blue); line-height:1.15; margin:4px 0 6px; }
  .st-card.orange .st-amount { color:#9A3412; }
  .st-badge { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:700; }
  .st-badge.up { background:#DCFCE7; color:#15803D; }
  .st-badge.down { background:#FEE2E2; color:#B91C1C; }
  .st-badge-note { font-size:11.5px; color:#94A3B8; margin-left:6px; }
  .st-badge-line { min-height:24px; margin-bottom:8px; }
  .st-row { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:8px 0; border-top:1px solid #F1F5F9; font-size:13px; color:#64748B; }
  .st-row b { color:var(--text); font-weight:700; white-space:nowrap; }
  .st-row .st-badge { padding:1px 7px; font-size:11px; margin-left:6px; }
  .st-block { padding:8px 0; border-top:1px solid #F1F5F9; font-size:13px; color:#64748B; }
  .st-block-head { display:flex; justify-content:space-between; margin-bottom:6px; }
  .st-block-head b { color:var(--text); }
  .st-split { display:flex; height:7px; border-radius:4px; overflow:hidden; background:#F1F5F9; }
  .st-split i { display:block; height:100%; }
  .st-legend { display:flex; justify-content:space-between; gap:8px; font-size:11.5px; margin-top:5px; }
  .st-legend span::before { content:''; display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; background:var(--dot); }
  .st-row.profit b { color:#15803D; }
  .rv-summary { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; margin-bottom:14px; }
  .rv-box { background:#F8FAFC; border-radius:12px; padding:10px 12px; }
  .rv-box b { display:block; font-size:17px; font-family:var(--font-display); color:var(--text); line-height:1.2; }
  .rv-box span { font-size:11.5px; color:#64748B; }
  .rv-box.best { background:#FEF2F2; }
  .rv-box.best b { color:#C81E2B; }
  .rv-chart-wrap { position:relative; height:240px; }
  .rv-legend { display:flex; gap:14px; flex-wrap:wrap; font-size:11.5px; color:#64748B; margin-top:8px; }
  .rv-legend i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:5px; vertical-align:-1px; }
  .net-cmp { width:100%; border-collapse:collapse; font-size:13px; min-width:640px; }
  .net-cmp th { text-align:right; font-size:11.5px; font-weight:600; color:#64748B; padding:8px 6px; border-bottom:1px solid var(--border); white-space:normal; line-height:1.25; vertical-align:bottom; background:none; text-transform:none; letter-spacing:0; }
  .net-cmp th:first-child, .net-cmp td:first-child { text-align:left; position:sticky; left:0; background:#fff; z-index:1; }
  .net-cmp tbody tr:hover td:first-child { background:#F8FAFC; }
  .net-cmp tbody tr.active td:first-child { background:#EFF6FF; }
  .net-cmp tfoot td:first-child { background:#F8FAFC; }
  .net-cmp td { text-align:right; padding:10px 6px; border-bottom:1px solid #F1F5F9; white-space:nowrap; color:var(--text); }
  .net-cmp tbody tr { cursor:pointer; }
  .net-cmp tbody tr:hover { background:#F8FAFC; }
  .net-cmp tbody tr.active { background:#EFF6FF; }
  .net-cmp .shop-cell { display:flex; align-items:center; gap:8px; font-weight:700; }
  .net-cmp .shop-cell small { font-weight:500; color:#94A3B8; }
  .net-cmp .best { color:#15803D; font-weight:800; }
  .net-cmp .neg { color:#B91C1C; font-weight:700; }
  .net-cmp tfoot td { font-weight:800; border-top:2px solid var(--border); border-bottom:none; background:#F8FAFC; }
  .net-cmp-chart-wrap { position:relative; margin-top:16px; }
  .net-detail-head { margin:22px 0 10px; }
  .net-detail-title { font-size:16px; font-weight:700; color:var(--text); margin-bottom:8px; }
  .modal-overlay { z-index:70 !important; }
  .modal-wide { max-height:88vh; }
  .wh-kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; }
  .wh-kpi { background:#F8FAFC; border-radius:12px; padding:10px 12px; }
  .wh-kpi b { display:block; font-size:18px; font-family:var(--font-display); color:var(--text); line-height:1.2; }
  .wh-kpi span { font-size:11.5px; color:#64748B; }
  .wh-kpi.good b { color:#15803D; }
  .wh-kpi.bad { background:#FEF2F2; }
  .wh-kpi.bad b { color:#B91C1C; }
  .wh-kpi.muted { background:#F1F5F9; }
  .wh-att-title { font-size:12px; font-weight:700; color:#64748B; margin:14px 0 4px; }
  .wh-att { display:flex; align-items:center; gap:10px; padding:9px 0; border-bottom:1px solid #F1F5F9; font-size:13px; }
  .wh-att:last-child { border-bottom:none; }
  .wh-att i.fa-solid { width:18px; text-align:center; }
  .wh-att .wa-main { flex:1; min-width:0; }
  .wh-att .wa-main b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text); }
  .wh-att .wa-main span { font-size:11.5px; color:#64748B; }
  .wh-toolbar { display:flex; gap:8px; margin-bottom:10px; }
  .wh-search { flex:1; display:flex; align-items:center; gap:8px; background:var(--field-bg); border:1px solid var(--border); border-radius:12px; padding:0 12px; }
  .wh-search i { color:#94A3B8; }
  .wh-search input { border:none !important; background:transparent !important; padding:10px 0 !important; margin:0 !important; box-shadow:none !important; outline:none; width:100%; font-size:14px; }
  .wh-tbtn { border:1px solid var(--border); background:#fff; color:var(--text); border-radius:12px; padding:9px 12px; font-size:13px; font-weight:700; cursor:pointer; white-space:nowrap; font-family:inherit; }
  .wh-tbtn-primary { background:var(--blue); border-color:var(--blue); color:#fff; }
  .wh-tbtn-wide { width:100%; margin-top:10px; }
  .wh-tbtn-sm { padding:6px 10px; font-size:12px; border-radius:10px; }
  .wh-tbtn-icon { padding:6px 9px; font-size:12px; border-radius:10px; color:#64748B; }
  .whc { border:1px solid var(--border); border-radius:14px; padding:12px; margin-top:8px; background:#fff; }
  .whc.st-out { border-color:#FCA5A5; background:#FFFBFB; }
  .whc.st-low { border-color:#FCD34D; }
  .whc-top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  .whc-name { min-width:0; }
  .whc-name b { display:block; font-size:14.5px; color:var(--text); overflow:hidden; text-overflow:ellipsis; }
  .whc-name span { font-size:11.5px; color:#94A3B8; }
  .whc-qty { font-family:var(--font-display); font-weight:800; font-size:18px; color:var(--text); white-space:nowrap; }
  .whc.st-out .whc-qty { color:#B91C1C; }
  .whc.st-low .whc-qty { color:#B45309; }
  .whc-bar { height:6px; border-radius:3px; background:#F1F5F9; margin:8px 0 6px; overflow:hidden; }
  .whc-bar i { display:block; height:100%; border-radius:3px; }
  .whc-info { font-size:12px; color:#64748B; }
  .whc-info .warn { color:#B91C1C; font-weight:700; }
  .whc-info .amber { color:#B45309; font-weight:700; }
  .whc-bottom { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-top:8px; flex-wrap:wrap; }
  .whc-price { font-size:12px; color:#475569; }
  .whc-price .mg { color:#15803D; font-weight:700; }
  .whc-actions { display:flex; gap:6px; margin-left:auto; }
  .ord-head-row { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:6px; }
  .sup-row, .ord-row { display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid #F1F5F9; }
  .sup-row:last-child, .ord-row:last-child { border-bottom:none; }
  .ord-row { cursor:pointer; }
  .sup-main { flex:1; min-width:0; cursor:pointer; }
  .sup-main b { display:block; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sup-main span { display:block; font-size:12px; color:#64748B; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ord-badge { font-size:11px; font-weight:700; padding:3px 9px; border-radius:999px; white-space:nowrap; }
  .ord-title { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .ord-title b { font-size:17px; }
  .ord-sub { font-size:12px; color:#64748B; margin-top:2px; }
  .ord-steps { display:flex; gap:4px; margin:10px 0 12px; }
  .ord-step { flex:1; text-align:center; font-size:11px; padding:5px 2px; border-radius:8px; background:#F1F5F9; color:#64748B; font-weight:600; }
  .ord-step.on { background:#DBEAFE; color:#0F52BA; }
  .ord-line { display:flex; align-items:center; gap:8px; padding:9px 0; border-bottom:1px solid #F1F5F9; font-size:13px; }
  .ord-line .pl-name, .ord-recv .pl-name, .ord-dist .pl-name { flex:1; min-width:0; }
  .ord-line .pl-name b, .ord-recv .pl-name b, .ord-dist .pl-name b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ord-line .pl-name span, .ord-recv .pl-name span, .ord-dist .pl-name span { font-size:11px; color:#64748B; }
  .ord-line input[type=number] { width:74px !important; padding:6px 8px !important; margin:0 !important; font-size:14px; }
  .ord-unit { font-size:12px; color:#64748B; min-width:18px; }
  .ord-x { border:none; background:none; color:#94A3B8; font-size:15px; cursor:pointer; padding:4px; }
  .ord-total { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:#475569; margin:12px 0; font-weight:600; }
  .ord-text { white-space:pre-wrap; background:#F8FAFC; border:1px solid var(--border); border-radius:12px; padding:12px; font-size:13px; font-family:inherit; margin:8px 0 12px; }
  .ord-recv, .ord-dist { padding:10px 0; border-bottom:1px solid #F1F5F9; }
  .ord-recv-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:6px; }
  .ord-recv-grid label { font-size:11px; color:#64748B; display:block; }
  .ord-recv-grid input { width:100% !important; margin:2px 0 0 !important; padding:7px 9px !important; }
  .ord-dist-row { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:13px; margin-top:6px; }
  .ord-dist-row input { width:84px !important; margin:0 !important; padding:6px 8px !important; }
  .ord-keep { font-size:12px; color:#15803D; margin-top:6px; font-weight:600; }
  .ord-keep.bad { color:#B91C1C; }
  .pl-group { font-size:12px; font-weight:700; color:#0F52BA; margin:12px 0 2px; }
  #orderModal select { width:100%; }
  .sup-tg { border:1px solid var(--border); border-radius:12px; padding:12px; margin:4px 0 12px; background:#F8FAFC; font-size:13px; }
  .sup-tg b { display:block; margin-bottom:4px; }
  .sup-tg .ok { color:#15803D; font-weight:700; }
  .sup-tg .no { color:#B45309; font-weight:700; }
  .sup-tg .wh-tbtn { margin:8px 6px 0 0; }
  .sup-bot { color:#15803D; font-weight:700; }
  .sc-actions { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 4px; }
  .sd-box { border:1px solid var(--border); border-radius:14px; padding:12px; margin-top:10px; background:#F8FAFC; }
  .sd-head { font-size:12px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.03em; margin-bottom:6px; }
  .sd-big { font-size:24px; font-weight:800; }
  .sd-big.bad { color:#B91C1C; }
  .sd-big.ok { color:#15803D; }
  .sd-cap { font-size:12px; color:#64748B; margin-bottom:6px; }
  .sd-note { font-size:13px; font-weight:600; margin:4px 0; color:#334155; }
  .sd-note.bad { color:#B91C1C; }
  .sd-note.warn { color:#B45309; }
  .pr-row { border-bottom:1px solid #F1F5F9; cursor:pointer; }
  .pr-badge { font-size:11px; font-weight:700; padding:2px 7px; border-radius:999px; white-space:nowrap; }
  .pr-badge.up { color:#B91C1C; background:#FEE2E2; }
  .pr-badge.down { color:#15803D; background:#DCFCE7; }
  .pr-hist { display:none; padding:0 0 8px; }
  .pr-row.open .pr-hist { display:block; }
  .pr-h { display:flex; justify-content:space-between; gap:8px; font-size:12px; color:#475569; padding:3px 0; }
  .sup-debt { font-weight:700; color:#B91C1C; }
  /* раздел «Поставщики» — вариант «Банк»: синий итог + список */
  .sp-top { display:flex; align-items:center; gap:8px; margin:2px 0 12px; }
  .sp-top h2 { flex:1; margin:0; font-family:var(--font-display); font-size:22px; font-weight:800; color:var(--darkblue); letter-spacing:-.01em; }
  .sp-pill { border:1px solid #BFDBFE; background:#EFF6FF; color:#0F52BA; border-radius:999px; padding:7px 12px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; white-space:nowrap; }
  .sp-pill.warn { background:#FEF3C7; border-color:#FDE68A; color:#92400E; }
  .sp-icon { width:38px; height:38px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#334155; font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center; }
  .sp-menu-wrap { position:relative; }
  .sp-menu { display:none; position:absolute; right:0; top:44px; z-index:30; background:#fff; border:1px solid var(--border); border-radius:14px; box-shadow:0 12px 30px rgba(15,23,42,.14); min-width:220px; padding:6px; }
  .sp-menu.open { display:block; }
  .sp-menu button { display:flex; align-items:center; gap:10px; width:100%; border:none; background:none; font:inherit; font-size:14px; font-weight:600; color:var(--text); padding:11px 12px; border-radius:10px; cursor:pointer; text-align:left; }
  .sp-menu button:hover { background:#F1F5F9; }
  .sp-menu button i { width:18px; color:#64748B; }
  .sp-hero { background:linear-gradient(135deg, #0A2540 0%, #0F52BA 100%); color:#fff; border-radius:20px; padding:18px 18px 16px; margin-bottom:14px; }
  .sp-hero .l { font-size:13px; color:#BFDBFE; font-weight:600; }
  .sp-hero .x { font-family:var(--font-display); font-size:32px; font-weight:800; line-height:1.15; margin:4px 0 2px; letter-spacing:-.01em; }
  .sp-hero .x small { font-size:16px; font-weight:700; color:#BFDBFE; margin-left:4px; }
  .sp-hero .u { font-size:13px; color:#BFDBFE; }
  .sp-bar { display:flex; height:8px; border-radius:4px; overflow:hidden; background:rgba(255,255,255,.22); margin-top:14px; }
  .sp-bar i { display:block; height:100%; }
  .sp-bar .o { background:#FCA5A5; } .sp-bar .k { background:#93C5FD; }
  .sp-leg { display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12px; color:#DBEAFE; margin-top:8px; }
  .sp-leg span::before { content:""; display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:0; }
  .sp-leg .o::before { background:#FCA5A5; } .sp-leg .k::before { background:#93C5FD; }
  .sp-hero.zero { background:linear-gradient(135deg, #065F46 0%, #059669 100%); }
  .sp-list { background:#fff; border:1px solid var(--border); border-radius:18px; padding:4px 14px; }
  .sp-row { display:flex; align-items:center; gap:12px; padding:12px 0; border-bottom:1px solid #F1F5F9; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .sp-row:last-child { border-bottom:none; }
  .sp-av { width:42px; height:42px; border-radius:13px; flex:none; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:14px; font-family:var(--font-display); }
  .sp-av.r { background:#FEE2E2; color:#B91C1C; } .sp-av.a { background:#FEF3C7; color:#92400E; }
  .sp-av.b { background:#DBEAFE; color:#1D4ED8; } .sp-av.g { background:#DCFCE7; color:#15803D; }
  .sp-mid { flex:1; min-width:0; }
  .sp-nm { font-weight:700; font-size:15px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sp-chip { display:inline-block; white-space:nowrap; font-size:11.5px; font-weight:700; padding:3px 9px; border-radius:999px; margin-top:4px; }
  .sp-chip.r { background:#FEE2E2; color:#B91C1C; } .sp-chip.a { background:#FEF3C7; color:#92400E; }
  .sp-chip.b { background:#DBEAFE; color:#1D4ED8; } .sp-chip.g { background:#DCFCE7; color:#15803D; } .sp-chip.n { background:#F1F5F9; color:#475569; }
  .sp-amt { text-align:right; flex:none; }
  .sp-amt b { display:block; font-family:var(--font-display); font-size:16px; font-weight:800; color:var(--text); white-space:nowrap; }
  .sp-amt span { font-size:12px; color:#64748B; white-space:nowrap; }
  .sp-pay { flex:none; border:none; background:#0F52BA; color:#fff; font:inherit; font-size:13px; font-weight:700; padding:9px 12px; border-radius:11px; cursor:pointer; }
  .sp-amt .sp-pay { display:inline-block; margin-top:6px; font-size:12px; padding:6px 12px; border-radius:999px; }
  .sp-pay:active, .sp-row:active { transform:scale(.98); }
  .sp-empty { text-align:center; padding:22px 8px; color:#64748B; font-size:14px; }
  .sp-empty .sp-pay { margin-top:12px; padding:11px 18px; }
  .sp-sec { display:flex; align-items:center; justify-content:space-between; margin:20px 2px 8px; }
  .sp-sec b { font-size:13px; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:.04em; }
  .sp-link { border:none; background:none; color:#0F52BA; font:inherit; font-size:13px; font-weight:700; cursor:pointer; padding:4px 0; }
  .sp-strip { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; }
  .sp-strip button { border:1px solid var(--border); background:#fff; border-radius:14px; padding:10px 6px; font:inherit; font-size:12px; font-weight:600; color:#64748B; cursor:pointer; }
  .sp-strip button b { display:block; font-family:var(--font-display); font-size:20px; font-weight:800; color:var(--text); }
  .sp-strip button.on { border-color:#0F52BA; color:#0F52BA; background:#EFF6FF; }
  .sp-strip button.new { background:#0F52BA; border-color:#0F52BA; color:#DBEAFE; }
  .sp-strip button.new b { color:#fff; }
  .sp-orders { background:#fff; border:1px solid var(--border); border-radius:18px; padding:2px 14px; margin-top:10px; }
  @media (min-width:900px) { .sp-hero .x { font-size:38px; } #view-suppliers { max-width:820px; } }
  /* карточка поставщика — шторка снизу, «Оплатить» всегда под рукой */
  .sp-sheet { position:relative; text-align:left; padding:0 !important; display:flex; flex-direction:column; overflow:hidden !important; max-width:560px !important; }
  .sp-sheet-body { overflow-y:auto; padding:8px 18px 18px; -webkit-overflow-scrolling:touch; }
  .sp-grab { width:42px; height:5px; border-radius:3px; background:#CBD5E1; margin:10px auto 2px; }
  .sp-x { position:absolute; top:10px; right:12px; width:34px; height:34px; border-radius:50%; border:none; background:#F1F5F9; color:#475569; font-size:16px; cursor:pointer; z-index:2; }
  .sp-foot { display:flex; gap:8px; padding:12px 18px calc(12px + env(safe-area-inset-bottom)); border-top:1px solid var(--border); background:#fff; }
  .sp-foot:empty { display:none; }
  .sp-foot .main { flex:1; border:none; background:#0F52BA; color:#fff; font:inherit; font-size:15px; font-weight:800; padding:14px; border-radius:14px; cursor:pointer; }
  .sp-foot .sec { border:1px solid var(--border); background:#fff; color:#334155; font:inherit; font-size:13px; font-weight:700; padding:0 14px; border-radius:14px; cursor:pointer; }
  @media (max-width:899px) {
    .modal-overlay.sp-sheet-ov { align-items:flex-end; }
    .sp-sheet { width:100% !important; max-width:100% !important; max-height:92vh !important; border-radius:22px 22px 0 0 !important; border:none !important; }
  }
  @media (min-width:900px) { .sp-grab { display:none; } .sp-sheet { max-height:88vh !important; } }
  .sp-head { display:flex; align-items:center; gap:12px; padding:6px 40px 4px 0; }
  .sp-head .sp-av { width:48px; height:48px; font-size:16px; }
  .sp-head .t { font-family:var(--font-display); font-size:19px; font-weight:800; color:var(--text); line-height:1.2; }
  .sp-head .c { font-size:12.5px; color:#64748B; margin-top:2px; }
  .sp-acts { display:flex; gap:6px; overflow-x:auto; margin:12px 0 4px; padding-bottom:2px; }
  .sp-acts button { flex:none; border:1px solid var(--border); background:#fff; border-radius:999px; padding:8px 13px; font:inherit; font-size:13px; font-weight:700; color:#334155; cursor:pointer; }
  .sp-acts button i { color:#0F52BA; margin-right:5px; }
  .sp-bal { border-radius:18px; padding:16px; margin-top:10px; background:#F8FAFC; border:1px solid var(--border); }
  .sp-bal.r { background:#FEF2F2; border-color:#FECACA; } .sp-bal.g { background:#F0FDF4; border-color:#BBF7D0; } .sp-bal.b { background:#EFF6FF; border-color:#BFDBFE; }
  .sp-bal .l { font-size:12.5px; font-weight:700; color:#64748B; }
  .sp-bal .x { font-family:var(--font-display); font-size:30px; font-weight:800; line-height:1.15; margin:2px 0; }
  .sp-bal.r .x { color:#B91C1C; } .sp-bal.g .x { color:#15803D; } .sp-bal.b .x { color:#1D4ED8; }
  .sp-bal .f { font-size:12.5px; color:#475569; }
  .sp-bal .chips { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; }
  .sp-bal .chips .sp-chip { margin-top:0; }
  .sp-det { border:1px solid var(--border); border-radius:16px; margin-top:12px; background:#fff; }
  .sp-det > summary { list-style:none; cursor:pointer; padding:14px; display:flex; align-items:center; justify-content:space-between; font-weight:800; font-size:14px; color:var(--text); }
  .sp-det > summary::-webkit-details-marker { display:none; }
  .sp-det > summary::after { content:"›"; font-size:20px; color:#94A3B8; transform:rotate(90deg); transition:transform .15s; }
  .sp-det[open] > summary::after { transform:rotate(-90deg); }
  .sp-det > summary span { font-weight:600; color:#64748B; font-size:12.5px; margin-left:auto; margin-right:10px; }
  .sp-det-in { padding:0 14px 12px; }
  .sp-form { border:2px solid #BFDBFE; background:#fff; border-radius:18px; padding:14px; margin-top:12px; }
  .sp-form-t { font-weight:800; font-size:15px; margin-bottom:2px; }
  .sp-form { scroll-margin-top:56px; }
  .sp-form-now { font-size:12.5px; color:#64748B; margin-bottom:6px; }
  #supCardBody .ord-x { color:#CBD5E1; background:none; }
  #supCardBody .ord-x:hover { color:#B91C1C; }
  .sp-seg { display:flex; gap:4px; background:#F1F5F9; border-radius:12px; padding:3px; margin:8px 0; }
  .sp-seg button { flex:1; border:none; background:transparent; padding:8px 6px; border-radius:9px; font:inherit; font-size:13px; font-weight:600; color:#64748B; cursor:pointer; }
  .sp-seg button.on { background:#fff; color:var(--text); box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .sp-chips { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 8px; }
  .sp-chips button { border:1px solid var(--border); background:#fff; border-radius:999px; padding:5px 12px; font:inherit; font-size:12px; font-weight:600; color:#475569; cursor:pointer; }
  .sp-chips button.on { background:#0F52BA; border-color:#0F52BA; color:#fff; }
  .sp-eq { background:#EFF6FF; color:#0F52BA; border-radius:10px; padding:8px 10px; font-size:13px; font-weight:600; margin-top:8px; }
  .sp-after { font-size:13px; margin-top:6px; color:#334155; }
  .sp-tot { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; margin:6px 0 10px; }
  .sp-tot div { background:#F8FAFC; border-radius:10px; padding:8px 10px; font-size:12px; color:#64748B; }
  .sp-tot b { display:block; font-size:14px; color:var(--text); }
  .ord-line.cancelled .pl-name b, .ord-line.cancelled > b { text-decoration:line-through; color:#94A3B8 !important; }
  .sp-sub { font-size:11px; color:#64748B; font-weight:600; text-align:right; }
  label.pl-row, label.ord-dist-row { text-transform:none; letter-spacing:normal; font-size:13px; color:var(--text); font-weight:400; margin:0; }
  label.pl-row .pl-name b, label.ord-dist-row span { color:var(--text); font-weight:600; }
  label.pl-row .pl-name span { text-transform:none; letter-spacing:normal; }
  .pl-row { display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid #F1F5F9; font-size:13px; }
  .pl-row .pl-name { flex:1; min-width:0; }
  .pl-row .pl-name b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pl-row .pl-name span { font-size:11px; color:#64748B; }
  .pl-row input[type=number] { width:78px !important; padding:6px 8px !important; margin:0 !important; font-size:13px; }
  .pl-row input[type=checkbox] { width:18px; height:18px; margin:0; }
  .whn-summary { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:6px; }
  .whn-shop { background:#F8FAFC; border-radius:12px; padding:9px 11px; font-size:12px; color:#64748B; }
  .whn-shop { cursor:pointer; border:1px solid transparent; }
  .whn-shop.active { border-color:var(--blue); background:#EFF6FF; }
  .whn-shop b { display:block; color:var(--text); font-size:13px; }
  .whn-shop .v { color:#9A3412; font-weight:700; font-size:14px; }
  .wh-mx { border-collapse:collapse; font-size:12.5px; width:100%; }
  .wh-mx th { font-size:11.5px; font-weight:700; color:#64748B; padding:8px 6px; border-bottom:1px solid var(--border); text-align:right; white-space:normal; background:#fff; text-transform:none; letter-spacing:0; }
  .wh-mx td { padding:8px 6px; border-bottom:1px solid #F1F5F9; text-align:right; white-space:nowrap; }
  .wh-mx th:first-child, .wh-mx td:first-child { text-align:left; position:sticky; left:0; background:#fff; z-index:1; white-space:normal; min-width:130px; }
  .wh-mx td:first-child span { display:block; font-size:11px; color:#94A3B8; }
  .wh-mx td.cell { cursor:pointer; }
  .wh-mx td.cell:hover { background:#F8FAFC; }
  .wh-mx .q-out { color:#B91C1C; font-weight:800; background:#FEF2F2; border-radius:6px; padding:2px 6px; }
  .wh-mx .q-low { color:#B45309; font-weight:800; background:#FEF3C7; border-radius:6px; padding:2px 6px; }
  .wh-mx .q-none { color:#CBD5E1; }
  .ship-modal { max-width:640px; }
  .net-actions { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:8px; margin:0 0 12px; }
  .ship-list { max-height:48vh; overflow-y:auto; border:1px solid var(--border); border-radius:12px; margin-top:6px; }
  .sh-row { display:flex; align-items:center; gap:8px; padding:9px 10px; border-bottom:1px solid #F1F5F9; }
  .sh-row:last-child { border-bottom:none; }
  .sh-row.sel { background:#EFF6FF; }
  .sh-name { flex:1; min-width:0; }
  .sh-name b { display:block; font-size:13.5px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sh-name span { font-size:11.5px; color:#64748B; }
  .sh-name .need { color:#B45309; font-weight:700; }
  .sh-row input { width:76px !important; padding:6px 8px !important; margin:0 !important; font-size:13px; text-align:right; }
  .sh-row input.over { border-color:#DC2626 !important; background:#FEF2F2 !important; }
  .sh-unit { font-size:12px; color:#64748B; width:22px; }
  .ship-foot { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:10px; flex-wrap:wrap; }
  .ship-foot span { font-size:13px; color:#475569; font-weight:600; }
  .imp-steps { display:flex; flex-direction:column; gap:6px; font-size:13px; color:#334155; background:#F8FAFC; border-radius:12px; padding:10px 12px; }
  .imp-sum { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin:8px 0; }
  .imp-sum div { background:#F8FAFC; border-radius:10px; padding:8px; text-align:center; font-size:11.5px; color:#64748B; }
  .imp-sum b { display:block; font-size:18px; color:var(--text); }
  .imp-table { width:100%; border-collapse:collapse; font-size:12px; }
  .imp-table td, .imp-table th { padding:6px; border-bottom:1px solid #F1F5F9; text-align:left; background:none; color:var(--text); text-transform:none; letter-spacing:0; font-size:12px; }
  .imp-tag { display:inline-block; font-size:10.5px; font-weight:700; padding:2px 6px; border-radius:6px; }
  .imp-tag.new { background:#DCFCE7; color:#15803D; }
  .imp-tag.upd { background:#DBEAFE; color:#1D4ED8; }
  .imp-tag.err { background:#FEE2E2; color:#B91C1C; }
  .dash-row {
    display:flex; justify-content:space-between; align-items:center; padding:8px 0;
    border-bottom:1px dashed var(--border); font-size:13.5px;
  }
  .dash-row:last-child { border-bottom:none; }
  .dash-row .dash-row-rank {
    display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px;
    background:var(--field-bg); border-radius:50%; font-size:11px; font-weight:700; color:var(--hint); margin-right:8px; flex:none;
  }
  .dash-row .dash-row-name { color:var(--text); font-weight:600; }
  .dash-row .dash-row-value { color:var(--blue); font-weight:700; flex:none; }
  .dash-row .dash-row-value.warn { color:#B3241C; }
  .dash-summary-grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; }
  .dash-summary-box { background:var(--field-bg); border-radius:12px; padding:12px; text-align:center; }
  .dash-summary-box .dsb-num { font-size:20px; font-weight:700; color:var(--text); font-family:var(--font-mono); }
  .dash-summary-box .dsb-num.warn { color:#B3241C; }
  .dash-summary-box .dsb-label { font-size:11px; color:var(--hint); margin-top:2px; }
  .dash-brands-panel { background:var(--field-bg); border-radius:10px; margin:4px 0 8px; padding:2px 8px; }
  .recur-exp-card {
    background:var(--field-bg); border-radius:12px; padding:12px; margin-bottom:8px;
  }
  .recur-exp-card.overdue { background:#FEF2F2; }
  .recur-exp-card .rec-top { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
  .recur-exp-card .rec-name { font-size:14px; font-weight:700; color:var(--text); }
  .recur-exp-card .rec-meta { font-size:11.5px; color:var(--hint); margin-top:2px; }
  .recur-exp-card .rec-amount { font-size:15px; font-weight:700; color:var(--blue); flex:none; }
  .recur-exp-card .rec-actions { display:flex; gap:6px; margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); }
  .journal-row { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px dashed var(--border); font-size:13px; }
  .journal-row:last-child { border-bottom:none; }
  .journal-row .jr-cat { font-weight:700; color:var(--text); }
  .journal-row .jr-meta { font-size:11.5px; color:var(--hint); margin-top:2px; }
  .journal-row .jr-amount { color:#B3241C; font-weight:700; flex:none; }
  .jr-icon-btn {
    background:none; border:none; cursor:pointer; font-size:13px; padding:4px; color:var(--hint); flex:none;
  }
  .jr-icon-btn:active { color:var(--blue); }
  .jr-edit-form { background:var(--field-bg); border-radius:10px; padding:12px; margin:2px 0 10px; }
  .kc-hist-list { margin-top:14px; }
  .kc-hist-entry { background:var(--field-bg); border-radius:12px; padding:12px 13px; margin-bottom:8px; }
  .kc-hist-entry .kc-he-top { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
  .kc-hist-entry .kc-he-service { font-size:14px; font-weight:700; color:var(--text); }
  .kc-hist-entry .kc-he-date { font-size:11.5px; color:var(--hint); margin-top:2px; }
  .kc-hist-entry .kc-he-cost { font-size:15px; font-weight:700; color:var(--blue); flex:none; white-space:nowrap; }
  .kc-hist-entry .kc-he-meta { font-size:12px; color:var(--hint); margin-top:6px; }
  .kc-hist-entry .kc-he-items { font-size:12px; color:var(--text); margin-top:6px; line-height:1.5; }
  .kc-hist-entry .kc-he-notes { font-size:12px; color:var(--hint); margin-top:6px; }
  .kc-hist-entry .kc-he-actions { margin-top:8px; padding-top:8px; border-top:1px dashed var(--border); }
  .sub-banner { display:flex; align-items:center; gap:10px; margin:0 0 12px; padding:12px 14px; border-radius:12px; background:#FEF0DC; color:#7A3A04; font-size:14px; font-weight:700; line-height:1.35; text-decoration:none; border:1.5px solid #F2C27D; }
  .sub-banner span { flex:1; }
  .sub-banner i { flex:none; }
  #view-staff label[for] { display:block; font-size:13px; font-weight:600; color:var(--text); margin:12px 0 4px; }
  .staff-err { display:none; color:#B3241C; font-size:13px; margin-top:4px; }
  .staff-err.on { display:block; }
  .staff-creds { margin-top:14px; padding:12px; border-radius:12px; background:#ECFDF5; border:1.5px solid #86EFAC; }
  .staff-creds-t { font-size:13px; font-weight:700; color:#166534; margin-bottom:8px; }
  .staff-creds-v { white-space:pre-line; font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:14px; color:#14532D; background:#fff; border-radius:8px; padding:10px; user-select:all; }
  .staff-copy { margin-top:8px; border:0; border-radius:8px; padding:8px 14px; background:#16A34A; color:#fff; font-weight:700; font-size:13px; cursor:pointer; }
  .staff-row { padding:10px 0; border-bottom:1px dashed var(--border); }
  .staff-row:last-child { border-bottom:0; }
  .staff-row.off .staff-who b { opacity:.55; }
  .staff-who { display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; font-size:14px; color:var(--text); }
  .staff-pill { font-size:11.5px; font-weight:700; padding:2px 8px; border-radius:999px; background:#E2E8F0; color:#475569; }
  .staff-pill.on { background:#DCFCE7; color:#166534; }
  .staff-btns { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .staff-btns button { border:1px solid var(--border); background:#F8FAFC; color:var(--text); border-radius:8px; padding:7px 10px; font-size:12.5px; font-weight:600; cursor:pointer; }
  .staff-btns button.del { color:#B3241C; border-color:#F5C2BE; background:#FDECEA; }

  /* ---------- Обучение: карта курса ---------- */
  .course-wrap { background:#0A2350; color:#fff; border-radius:22px; padding:18px 16px 22px; position:relative; overflow:hidden; }
  .course-sub { font-size:13px; font-weight:700; color:#9CC4FF; }
  .course-head { font-size:22px; font-weight:800; line-height:1.2; margin:4px 0 2px; }
  .course-note { font-size:12.5px; color:#C9D8F2; margin-top:6px; }
  .course-map { position:relative; margin:14px auto 0; max-width:520px; }
  .course-map svg.course-path { position:absolute; left:0; top:0; pointer-events:none; }
  .cnode { position:absolute; width:48px; height:48px; margin-left:-24px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:16px; text-decoration:none; border:0; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .cnode.done { background:#15A35B; color:#fff; }
  .cnode.open { background:#1E3F7A; color:#CFE0FF; }
  .cnode.cur { width:64px; height:64px; margin-left:-32px; background:#fff; color:#1463E6; box-shadow:0 0 0 6px #1FB5F2; font-size:22px; }
  .cnode .cscore { position:absolute; bottom:-18px; left:50%; transform:translateX(-50%); font-size:11px; font-weight:800; color:#7EE2AE; white-space:nowrap; }
  .ccard { position:absolute; width:140px; box-sizing:border-box; background:#fff; color:#0A2350; border-radius:14px; padding:10px 12px; box-shadow:0 8px 20px rgba(0,0,0,0.25); display:flex; flex-direction:column; gap:6px; }
  .ccard .cc-meta { font-size:11px; font-weight:800; color:#1463E6; }
  .ccard .cc-title { font-size:13.5px; font-weight:800; line-height:1.25; }
  .ccard a { display:block; background:#1463E6; color:#fff; text-decoration:none; text-align:center; border-radius:10px; padding:9px 0; font-weight:800; font-size:13px; }
  .course-list { margin:14px auto 0; max-width:520px; display:flex; flex-direction:column; gap:6px; }
  .course-row { display:flex; align-items:center; gap:10px; background:rgba(255,255,255,0.06); border-radius:12px; padding:10px 12px; color:#fff; text-decoration:none; font-size:14px; font-weight:600; }
  .course-row b { width:26px; height:26px; border-radius:8px; background:#1E3F7A; display:flex; align-items:center; justify-content:center; font-size:12px; flex:none; }
  .course-row.done b { background:#15A35B; }
  .course-row span.cr-t { flex:1; min-width:0; }
  .course-row span.cr-s { font-size:12px; font-weight:800; color:#7EE2AE; }
""" + HELP_CSS + """
</style>
</head>
<body>
<div class="speedline"></div>
<!-- Навигация: на телефоне — нижняя панель + шторка «Ещё», на широком экране — меню слева.
     Пункты бокового меню несут id="tab-..." (на них опирается showTab), нижняя панель и
     шторка помечены только data-tab — активный пункт подсвечивается везде сразу. -->
<aside class="side-nav">
  <div class="side-brand">
    <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
    <div style="min-width:0;">
      <div class="side-shop">{{ shop_name }}</div>
      <div class="logo-sub brand-line"><span class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span>{% if is_employee %} · <span class="role-tag">{{ T.role_employee }}</span>{% elif is_branch %} · <span class="role-tag">{{ T.role_branch }}</span>{% endif %}</div>
    </div>
  </div>
  <nav class="side-list">
    <div class="side-item side-add active" id="tab-add" data-tab="add" onclick="showTab('add')"><i class="fa-solid fa-plus"></i><span>{{ T.tab_add }}</span></div>
    <div class="side-item" id="tab-table" data-tab="table" onclick="showTab('table')"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
    {% if not is_employee %}<div class="side-item" id="tab-stats" data-tab="stats" onclick="showTab('stats')"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>{% endif %}
    {% if warehouse_enabled and not is_employee %}<div class="side-item" id="tab-warehouse" data-tab="warehouse" onclick="showTab('warehouse')"><i class="fa-solid fa-boxes-stacked"></i><span>{{ T.tab_warehouse }}</span></div>{% endif %}
    {% if warehouse_enabled and not is_employee and not is_branch %}<div class="side-item" id="tab-suppliers" data-tab="suppliers" onclick="showTab('suppliers')"><i class="fa-solid fa-truck-field"></i><span>{{ T.tab_suppliers }}</span><b class="nav-badge" data-badge="suppliers"></b></div>{% endif %}
    <div class="side-item" id="tab-debts" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
    {% if not is_employee %}<div class="side-item" id="tab-expenses" data-tab="expenses" onclick="showTab('expenses')"><i class="fa-solid fa-receipt"></i><span>{{ T.tab_expenses }}</span></div>{% endif %}
    <div class="side-item" id="tab-broadcast" data-tab="broadcast" onclick="showTab('broadcast')"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
    {% if sms_enabled %}<div class="side-item" id="tab-sms" data-tab="sms" onclick="showTab('sms')"><i class="fa-solid fa-comment-sms"></i><span>{{ T.tab_sms }}</span></div>{% endif %}
    <div class="side-item" id="tab-course" data-tab="course" onclick="showTab('course')"><i class="fa-solid fa-graduation-cap"></i><span>{{ T.tab_course }}</span></div>
    <div class="side-item" id="tab-help" data-tab="help" onclick="showTab('help')"><i class="fa-solid fa-circle-question"></i><span>{{ T.tab_help }}</span></div>
    {% if not is_employee %}<div class="side-item" id="tab-export" data-tab="export" onclick="showTab('export')"><i class="fa-solid fa-file-arrow-down"></i><span>{{ T.tab_export }}</span></div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-staff" data-tab="staff" onclick="showTab('staff')"><i class="fa-solid fa-user-group"></i><span>{{ T.tab_staff }}</span></div>{% endif %}
    {% if is_sub_owner %}<div class="side-item" onclick="location.href='/subscription'"><i class="fa-solid fa-credit-card"></i><span>{{ T.sub_menu }}</span></div>{% endif %}
  </nav>
  <div class="side-foot">
    <button class="lang-btn" onclick="switchLanguage()">{{ T.lang_switch }}</button>
    <a class="logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i> {{ T.logout }}</a>
  </div>
</aside>

{% set bar_slot2 = 'debts' if is_employee else 'stats' %}
{% set bar_slot4 = 'warehouse' if (warehouse_enabled and not is_employee) else ('broadcast' if is_employee else 'debts') %}
<nav class="bottom-bar" id="bottomBar">
  <div class="bb-item" data-tab="table" onclick="showTab('table')"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
  {% if bar_slot2 == 'stats' %}
  <div class="bb-item" data-tab="stats" onclick="showTab('stats')"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>
  {% else %}
  <div class="bb-item" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
  {% endif %}
  <div class="bb-item bb-add active" data-tab="add" onclick="showTab('add')"><div class="bb-plus"><i class="fa-solid fa-plus"></i></div><span>{{ T.nav_add_short }}</span></div>
  {% if bar_slot4 == 'warehouse' %}
  <div class="bb-item" data-tab="warehouse" onclick="showTab('warehouse')"><i class="fa-solid fa-boxes-stacked"></i><span>{{ T.tab_warehouse }}</span></div>
  {% elif bar_slot4 == 'debts' %}
  <div class="bb-item" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
  {% else %}
  <div class="bb-item" data-tab="broadcast" onclick="showTab('broadcast')"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
  {% endif %}
  <div class="bb-item" id="bbMore" onclick="openMore()"><i class="fa-solid fa-ellipsis"></i><span>{{ T.nav_more }}</span><b class="nav-badge" id="moreBadge"></b></div>
</nav>

<div class="more-backdrop" id="moreBackdrop" onclick="closeMore()"></div>
<div class="more-sheet" id="moreSheet" data-bar="table,{{ bar_slot2 }},add,{{ bar_slot4 }}">
  <div class="more-grab"></div>
  <div class="more-list">
      {% if warehouse_enabled and not is_employee and not is_branch %}<div class="more-item" data-tab="suppliers" onclick="showTab('suppliers'); closeMore();"><i class="fa-solid fa-truck-field"></i><span>{{ T.tab_suppliers }}</span><b class="nav-badge" data-badge="suppliers"></b></div>{% endif %}
      <div class="more-item" data-tab="table" data-more-slot="table" onclick="showTab('table'); closeMore();"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
      {% if not is_employee %}<div class="more-item" data-tab="stats" data-more-slot="stats" onclick="showTab('stats'); closeMore();"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>{% endif %}
      {% if warehouse_enabled and not is_employee %}<div class="more-item" data-tab="warehouse" data-more-slot="warehouse" onclick="showTab('warehouse'); closeMore();"><i class="fa-solid fa-boxes-stacked"></i><span>{{ T.tab_warehouse }}</span></div>{% endif %}
      <div class="more-item" data-tab="debts" data-more-slot="debts" onclick="showTab('debts'); closeMore();"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
      {% if not is_employee %}<div class="more-item" data-tab="expenses" data-more-slot="expenses" onclick="showTab('expenses'); closeMore();"><i class="fa-solid fa-receipt"></i><span>{{ T.tab_expenses }}</span></div>{% endif %}
      <div class="more-item" data-tab="broadcast" data-more-slot="broadcast" onclick="showTab('broadcast'); closeMore();"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
      {% if sms_enabled %}<div class="more-item" data-tab="sms" data-more-slot="sms" onclick="showTab('sms'); closeMore();"><i class="fa-solid fa-comment-sms"></i><span>{{ T.tab_sms }}</span></div>{% endif %}
      <div class="more-item" data-tab="course" data-more-slot="course" onclick="showTab('course'); closeMore();"><i class="fa-solid fa-graduation-cap"></i><span>{{ T.tab_course }}</span></div>
      <div class="more-item" data-tab="help" data-more-slot="help" onclick="showTab('help'); closeMore();"><i class="fa-solid fa-circle-question"></i><span>{{ T.tab_help }}</span></div>
      {% if not is_employee %}<div class="more-item" data-tab="export" data-more-slot="export" onclick="showTab('export'); closeMore();"><i class="fa-solid fa-file-arrow-down"></i><span>{{ T.tab_export }}</span></div>{% endif %}
      {% if not is_employee %}<div class="more-item" data-tab="staff" data-more-slot="staff" onclick="showTab('staff'); closeMore();"><i class="fa-solid fa-user-group"></i><span>{{ T.tab_staff }}</span></div>{% endif %}
      {% if is_sub_owner %}<a class="more-item" href="/subscription"><i class="fa-solid fa-credit-card"></i><span>{{ T.sub_menu }}</span></a>{% endif %}
      <div class="more-item" onclick="switchLanguage()"><i class="fa-solid fa-language"></i><span>{{ T.lang_switch }}</span></div>
      <a class="more-item more-logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i><span>{{ T.logout }}</span></a>
  </div>
</div>

<div class="container">
  <div class="topbar">
    <div style="display:flex; align-items:center; gap:10px; min-width:0;">
      <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
      <div style="min-width:0;">
        <h1>{{ shop_name }}</h1>
        <div class="logo-sub brand-line"><span class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span>{% if is_employee %} · <span class="role-tag">{{ T.role_employee }}</span>{% elif is_branch %} · <span class="role-tag">{{ T.role_branch }}</span>{% endif %}</div>
      </div>
    </div>
    <button class="lang-btn" onclick="switchLanguage()">{{ T.lang_switch_short }}</button>
  </div>

  {% if sub_banner %}{% if sub_banner.link %}<a class="sub-banner" href="/subscription"><i class="fa-solid fa-credit-card"></i><span>{{ sub_banner.text }}</span><i class="fa-solid fa-chevron-right"></i></a>{% else %}<div class="sub-banner"><i class="fa-solid fa-circle-info"></i><span>{{ sub_banner.text }}</span></div>{% endif %}{% endif %}
  <div id="msg"></div>

  <div id="view-add" class="add-form">
    <div class="af-title"><span class="dot"></span>{{ T.tab_add }}</div>

    <div class="af-sec">
      <div class="af-h"><i class="fa-solid fa-car"></i>{{ T.af_car }}</div>
      <div class="field">
        <label><i class="fa-solid fa-id-card"></i>{{ T.field_plate }}</label>
        <div class="plate-wrap">
          <span class="plate-chip">UZ</span>
          <input id="plate" placeholder="01A123BC" oninput="onPlateInput()" onblur="onPlateBlur()" autocomplete="off" autocapitalize="characters" spellcheck="false" enterkeyhint="next">
          <button type="button" class="ps-cam-btn" onclick="openPlateScanner()" title="{{ T.ps_btn_title }}" aria-label="{{ T.ps_btn_title }}"><i class="fa-solid fa-camera"></i></button>
          <div id="plateSuggest" class="plate-suggest" style="display:none;"></div>
        </div>
        <div id="knownClientPanel"></div>
      </div>
      <div class="field">
        <label><i class="fa-solid fa-user"></i>{{ T.field_owner_name }}</label>
        <input id="owner_name" placeholder="Имя Фамилия">
      </div>
      <div class="field">
        <label><i class="fa-solid fa-phone"></i>{{ T.field_owner_phone }}</label>
        <input id="owner_phone" type="tel" inputmode="tel" placeholder="+998 90 123 45 67" enterkeyhint="next">
        <div class="hint-text">{{ T.hint_owner_phone }}</div>
      </div>
      <div class="row2" style="margin-bottom:-10px;">
        <div class="field">
          <label><i class="fa-solid fa-car"></i>{{ T.field_car_brand }}</label>
          <select id="car_brand">
            {% for b in brands %}<option value="{{b}}">{{b}}</option>{% endfor %}
          </select>
        </div>
        <div class="field">
          <label><i class="fa-solid fa-car-side"></i>{{ T.field_car_model }}</label>
          <input id="car_model" placeholder="Cobalt, Nexia, Malibu...">
        </div>
      </div>
    </div>

    <div class="af-sec">
      <div class="af-h"><i class="fa-solid fa-gauge-high"></i>{{ T.af_mileage }}</div>
      <div class="mil-grid">
        <div>
          <div class="mil-l">{{ T.mil_now }}</div>
          <div class="mil-f"><input id="mileage" type="number" inputmode="numeric" placeholder="45000" oninput="checkMileageVsDue(); applyKmStep(); applyDailyKm()" enterkeyhint="next"><span>{{ T.km_short }}</span></div>
        </div>
        <div class="mil-arrow"><i class="fa-solid fa-arrow-right"></i></div>
        <div>
          <div class="mil-l">{{ T.mil_next }}</div>
          <div class="mil-f accent"><input id="next_mileage" type="number" inputmode="numeric" placeholder="55000" oninput="KM.manual = true; applyDailyKm()" enterkeyhint="next"><span>{{ T.km_short }}</span></div>
        </div>
      </div>
      <div id="mileageCompare"></div>
      <div class="km-chips km-seg" id="kmChips"></div>
      <div class="mil-l" style="margin-top:12px;">{{ T.daily_km_label }}</div>
      <div class="mil-f"><input id="daily_km" type="number" inputmode="numeric" placeholder="{{ T.daily_km_ph }}" oninput="DK.intervalManual = false; applyDailyKm()" enterkeyhint="next"><span>{{ T.km_per_day }}</span></div>
      <div id="dkSuggest"></div>
      <div id="dkHint" class="dk-hint"></div>
      <div class="mil-l" style="margin-top:12px;">{{ T.field_interval }}</div>
      <div style="display:flex; gap:8px;">
        <input id="interval_value" type="number" placeholder="3" value="3" style="flex:1;" oninput="DK.intervalManual = true; applyDailyKm()">
        <select id="interval_unit" style="flex:1;" onchange="DK.intervalManual = true; applyDailyKm()">
          <option value="months">{{ T.unit_months }}</option>
          <option value="days">{{ T.unit_days }}</option>
        </select>
      </div>
    </div>

    <div class="af-sec">
      <div class="af-h"><i class="fa-solid fa-oil-can"></i>{{ T.af_items }}</div>
      {% if warehouse_enabled %}
      <div class="field pick-search">
        <input id="pickSearch" type="search" placeholder="🔍 {{ T.pick_search_ph }}" aria-label="{{ T.pick_search_label }}" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search" oninput="renderPickResults('main')" onkeydown="onPickKey(event, 'main')">
        <div id="pickResults" class="pick-results"></div>
      </div>
      {% endif %}
      <div id="fluidsList"></div>
      <div id="filtersList"></div>
      <div class="af-add" id="itemAddChips"></div>
      <div class="af-sub">{{ T.section_other }}</div>
      <div class="row2">
        <div class="field">
          <input id="other_name" placeholder="{{ T.field_other_name_ph }}" aria-label="{{ T.field_other_name }}">
        </div>
        <div class="field" style="flex:0 0 38%;">
          <input id="other_price" type="number" placeholder="{{ T.field_price }}" aria-label="{{ T.field_price }}" oninput="updateTotal()">
        </div>
      </div>
      {% if warehouse_enabled %}
      <div class="af-sub">{{ T.wh_other_stock_title }}</div>
      <div id="otherStockRows"></div>
      <button type="button" class="af-ghost" onclick="addOtherStockRow('other')">{{ T.wh_add_row }}</button>
      {% endif %}
    </div>

    <div class="af-sec">
      <div class="af-h"><i class="fa-solid fa-wallet"></i>{{ T.af_payment }}</div>
      <div class="pay-seg" id="paySeg">
        <button type="button" data-m="cash" class="on" onclick="setPayMode('cash')"><i class="fa-solid fa-money-bill"></i> {{ T.payment_cash }}</button>
        <button type="button" data-m="card" onclick="setPayMode('card')"><i class="fa-solid fa-credit-card"></i> {{ T.payment_card }}</button>
        <button type="button" data-m="mix" onclick="setPayMode('mix')">{{ T.pay_mode_mix }}</button>
        <button type="button" data-m="debt" onclick="setPayMode('debt')">{{ T.pay_mode_debt }}</button>
      </div>
      <div id="payInputs" style="display:none; margin-top:10px;">
        <div class="row2">
          <div class="field">
            <label style="font-size:11px;"><i class="fa-solid fa-money-bill"></i> {{ T.payment_cash }}</label>
            <input id="pay_cash" type="number" placeholder="0" oninput="onPayCashInput()">
          </div>
          <div class="field">
            <label style="font-size:11px;"><i class="fa-solid fa-credit-card"></i> {{ T.payment_card }}</label>
            <input id="pay_card" type="number" placeholder="0" oninput="onPayCardInput()">
          </div>
        </div>
      </div>
      <div style="display:none;">
        <input type="checkbox" id="debt_enabled" onchange="toggleDebtSection()">
      </div>
      <div id="debtFields" style="display:none; margin-top:4px; padding:12px; background:var(--field-bg); border:1.5px dashed var(--border); border-radius:12px;">
        <div class="field">
          <label style="font-size:11px;">{{ T.debt_remaining_label }}</label>
          <div id="debtRemaining" style="font-size:18px; font-weight:700; color:var(--btn); font-family:var(--font-mono);">0</div>
        </div>
        <div class="row2" style="margin-bottom:-10px;">
          <div class="field">
            <label style="font-size:11px;">{{ T.debt_installment_amount }}</label>
            <input id="debt_installment_amount" type="number" placeholder="100000">
          </div>
          <div class="field">
            <label style="font-size:11px;">{{ T.debt_interval_days }}</label>
            <input id="debt_interval_days" type="number" placeholder="14">
          </div>
        </div>
      </div>
      <div class="af-sub" style="margin-top:14px;">{{ T.field_notes }}</div>
      <textarea id="notes" rows="2" placeholder="{{ T.notes_ph }}"></textarea>
    </div>

    <div class="af-bar">
      <div class="af-bar-total"><span>{{ T.field_total }}</span><b id="totalCost">0</b></div>
      <button class="af-save" onclick="submitCar()"><i class="fa-solid fa-check"></i> {{ T.btn_save }}</button>
    </div>
  </div>

  <div id="view-table" style="display:none;">
    <div id="baseClientCount" style="font-size:13px; color:var(--hint); margin-bottom:8px;"></div>
    <div style="position:relative;">
      <input class="search" id="search" type="search" name="oilbook_base_q" autocomplete="off" autocapitalize="off" spellcheck="false" data-lpignore="true" placeholder="{{ T.search_ph }}" oninput="onBaseSearch(); toggleSearchClearBtn();" style="padding-right:40px;">
      <button type="button" id="searchClearBtn" onclick="clearSearch()" style="display:none; position:absolute; right:10px; top:50%; transform:translateY(-50%); background:none; border:none; color:var(--hint); font-size:18px; cursor:pointer; padding:4px 6px;">✕</button>
    </div>
    <div id="clientCardPanel" style="display:none; margin-bottom:12px;"></div>
    <div id="table-body"></div>
  </div>

  <div id="view-debts" style="display:none;">
    <div id="debtsList"></div>
  </div>

  {% if not is_employee %}
  <div id="view-expenses" style="display:none;">
    {% if true %}
    <div class="card" id="usdRateCardExp" style="margin-bottom:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.usd_rate_title }}</label>
      <div class="row2">
        <div class="field">
          <label>{{ T.usd_rate_label }}</label>
          <input id="usd_rate_input_exp" type="number" step="0.01" placeholder="{{ '%g'|format(usd_rate_head) if usd_rate_head else 12700 }}" value="{{ '%g'|format(usd_rate_own) if usd_rate_own else '' }}">
        </div>
      </div>
      <button class="submit" onclick="saveUsdRate('usd_rate_input_exp', 'usdRateSaved_exp')">{{ T.usd_rate_save }}</button>
      <div id="usdRateSaved_exp" style="display:none; color:#1B8A5A; font-size:13px; margin-top:8px;">✓ {{ T.usd_rate_saved }}</div>
      <div class="hint-text usd-inherit-hint" style="display:none; margin-top:8px; color:#0F52BA;"></div>
    </div>
    {% endif %}

    <div class="card">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.expense_add_title }}</label>
      <div class="field">
        <label>{{ T.expense_category_label }}</label>
        <select id="exp_category" onchange="onExpenseCategoryChange('exp_category', 'exp_category_custom')"></select>
        <input id="exp_category_custom" placeholder="{{ T.expense_custom_category_ph }}" style="display:none; margin-top:6px;">
      </div>
      <div class="field">
        <label>{{ T.expense_name_label }}</label>
        <input id="exp_name" placeholder="{{ T.expense_name_ph }}">
      </div>
      <div class="row2">
        <div class="field">
          <label>{{ T.expense_amount_label }}</label>
          <input id="exp_amount" type="number" placeholder="100000" oninput="onSumFieldEdited('exp_amount', 'exp_amount_usd')">
        </div>
        <div class="field">
          <label>{{ T.usd_price_label }}</label>
          <input id="exp_amount_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('exp_amount_usd', 'exp_amount')">
        </div>
      </div>
      <button class="submit" onclick="submitExpense()">{{ T.expense_add_btn }}</button>
    </div>

    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.expense_recurring_title }}</label>
      <div id="recurringExpensesList"></div>
      <div style="margin-top:10px; padding-top:10px; border-top:1px dashed var(--border);">
        <div class="field">
          <label>{{ T.expense_category_label }}</label>
          <select id="rec_category" onchange="onExpenseCategoryChange('rec_category', 'rec_category_custom')"></select>
          <input id="rec_category_custom" placeholder="{{ T.expense_custom_category_ph }}" style="display:none; margin-top:6px;">
        </div>
        <div class="field">
          <label>{{ T.expense_name_label }}</label>
          <input id="rec_name" placeholder="{{ T.expense_recurring_name_ph }}">
        </div>
        <div class="row2">
          <div class="field">
            <label>{{ T.expense_amount_label }}</label>
            <input id="rec_amount" type="number" placeholder="2000000" oninput="onSumFieldEdited('rec_amount', 'rec_amount_usd')">
          </div>
          <div class="field">
            <label>{{ T.expense_day_of_month_label }}</label>
            <input id="rec_day" type="number" min="1" max="28" placeholder="5">
          </div>
        </div>
        <div class="field">
          <label>{{ T.usd_price_label }}</label>
          <input id="rec_amount_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('rec_amount_usd', 'rec_amount')">
        </div>
        <button class="submit" onclick="createRecurringExpense()">{{ T.expense_recurring_add_btn }}</button>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.expense_journal_title }}</label>
      <div id="expensesJournal">{{ T.stats_loading }}</div>
    </div>
  </div>
  {% endif %}

  <div id="view-broadcast" class="card" style="display:none;">
    <div class="field">
      <label>{{ T.broadcast_msg_label }}</label>
      <textarea id="broadcast_message" rows="5" placeholder="{{ T.broadcast_msg_ph }}"></textarea>
      <div class="hint-text" id="broadcastRecipients">{{ T.broadcast_loading_recipients }}</div>
    </div>
    <button class="submit" onclick="sendBroadcast()">{{ T.broadcast_send_btn }}</button>
    <div style="margin-top:18px;">
      <div class="hint-text" style="margin-bottom:8px;">{{ T.broadcast_history_title }}</div>
      <div id="broadcastHistory"></div>
    </div>
  </div>

  <div id="view-course" style="display:none;">
    <div class="course-wrap">
      <div class="course-sub">{{ T.course_sub }}</div>
      <div class="course-head" id="courseHead">&nbsp;</div>
      {% if lang != 'uz' %}<div class="course-note">{{ T.course_lang_note }}</div>{% endif %}
      <div class="course-map" id="courseMap"></div>
      <div class="course-list" id="courseList"></div>
    </div>
  </div>

  <div id="view-help" style="display:none;">
""" + HELP_VIEW + """
  </div>

  {% if not is_employee %}
  <div id="view-staff" style="display:none;">
    <div class="card">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:6px;">{{ T.staff_add_title }}</label>
      <div class="hint-text" style="margin-bottom:12px;">{{ T.staff_intro }}</div>
      <label for="staff_name">{{ T.staff_name }}</label>
      <input id="staff_name" maxlength="60" placeholder="{{ T.staff_name_ph }}" autocomplete="off">
      <div class="staff-err" id="staff_err_full_name"></div>
      <label for="staff_login">{{ T.staff_login }}</label>
      <input id="staff_login" maxlength="30" placeholder="{{ T.staff_login_ph }}" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false">
      <div class="hint-text">{{ T.staff_login_hint }}</div>
      <div class="staff-err" id="staff_err_username"></div>
      <label for="staff_pw">{{ T.staff_password }}</label>
      <input id="staff_pw" maxlength="100" autocomplete="new-password">
      <div class="hint-text">{{ T.staff_password_hint }}</div>
      <div class="staff-err" id="staff_err_password"></div>
      <button class="submit" onclick="createStaff()">{{ T.staff_add_btn }}</button>
      <div id="staffCreds"></div>
    </div>
    <div class="card" style="margin-top:16px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.staff_list_title }}</label>
      <div id="staffList">{{ T.stats_loading }}</div>
    </div>
  </div>

  <div id="view-export" class="card" style="display:none;">
    <p style="margin-top:0;">{{ T.export_p1 }}</p>
    <p class="hint-text">{{ T.export_p2 }}</p>
    <button class="submit" onclick="window.location.href='/api/export'">{{ T.export_btn }}</button>
    <button class="submit" style="background:#1a7a3d; margin-top:8px;" onclick="window.location.href='/api/export_excel'">{{ T.export_excel_btn }}</button>
    <p class="hint-text">{{ T.export_excel_hint }}</p>
  </div>

  <div id="view-stats" style="display:none;">
    <div class="subtabs">
      <div class="subtab active" id="substat-own" onclick="showStatsSubTab('own')">{{ T.stats_sub_own }}</div>
      <div class="subtab" id="substat-branches" onclick="showStatsSubTab('branches')" style="display:none;">{{ T.stats_sub_branches }}</div>
    </div>

    <div id="statsOwnView">
      <div id="statsGrid">{{ T.stats_loading }}</div>

      {% if not is_employee %}
      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.stats_brands_title }}</label>
        <div class="hint-text" style="margin-bottom:12px;">{{ T.stats_brands_hint }}</div>
        <div class="brand-period" id="brandPeriod"></div>
        <div class="brand-chips" id="brandCategoryChips"></div>
        <div id="brandBody">{{ T.stats_loading }}</div>
      </div>
      {% endif %}

      {% if not is_employee and not is_branch %}
      <div class="card" style="margin-top:16px; background:linear-gradient(135deg, #F0FDF4, #ECFDF5); border-color:#86EFAC;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_net_profit_title }}</label>
        <div id="dashNetProfit">{{ T.stats_loading }}</div>
      </div>
      {% endif %}

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_revenue_chart_title }}</label>
        <div id="revenueSummary" class="rv-summary"></div>
        <div class="rv-chart-wrap"><canvas id="revenueChart"></canvas></div>
      </div>

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_debt_summary_title }}</label>
        <div id="dashDebtSummary">{{ T.stats_loading }}</div>
      </div>

      {% if warehouse_enabled and not is_employee %}
      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_low_stock_title }}</label>
        <div id="dashLowStock">{{ T.stats_loading }}</div>
      </div>
      {% endif %}

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.stats_custom_title }}</label>
        <div id="statsPresets" style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;"></div>
        <div class="row2">
          <div class="field">
            <label>{{ T.stats_from }}</label>
            <input id="stats_from" type="date">
          </div>
          <div class="field">
            <label>{{ T.stats_to }}</label>
            <input id="stats_to" type="date">
          </div>
        </div>
        <button class="submit" onclick="applyStatsRange()">{{ T.stats_apply }}</button>
        <div id="statsRangeResult" style="margin-top:14px;"></div>
      </div>
    </div>

    <div id="statsBranchesView" style="display:none;">
      <div id="statsAggregated">
        <div class="card">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.net_compare_title }}</label>
          <div class="hint-text" style="margin-bottom:12px;">{{ T.net_compare_hint }}</div>
          <div class="brand-period" id="netComparePeriod"></div>
          <div id="netCompareBody">{{ T.stats_loading }}</div>
          <div class="net-cmp-chart-wrap" id="netCompareChartWrap"><canvas id="netCompareChart"></canvas></div>
        </div>

        <div class="net-detail-head" id="netDetailHead">
          <div class="net-detail-title">{{ T.net_detail_title }}</div>
          <div class="brand-chips" id="netScopeChips"></div>
        </div>
        <div id="netStatsGrid">{{ T.stats_loading }}</div>

        <div class="card" style="margin-top:16px; background:linear-gradient(135deg, #F0FDF4, #ECFDF5); border-color:#86EFAC;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_net_profit_title }}</label>
          <div id="netNetProfit">{{ T.stats_loading }}</div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_revenue_chart_title }}</label>
          <div id="netRevenueSummary" class="rv-summary"></div>
          <div class="rv-chart-wrap"><canvas id="netRevenueChart"></canvas></div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.stats_brands_title }}</label>
          <div class="hint-text" style="margin-bottom:12px;">{{ T.stats_brands_hint }}</div>
          <div class="brand-period" id="netBrandPeriod"></div>
          <div class="brand-chips" id="netBrandCategoryChips"></div>
          <div id="netBrandBody">{{ T.stats_loading }}</div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_debt_summary_title }}</label>
          <div id="netDebtSummary">{{ T.stats_loading }}</div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_low_stock_title }}</label>
          <div id="netLowStock">{{ T.stats_loading }}</div>
        </div>
      </div>

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.stats_custom_title }}</label>
        <div id="branchStatsPresets" style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;"></div>
        <div class="row2">
          <div class="field">
            <label>{{ T.stats_from }}</label>
            <input id="branch_stats_from" type="date">
          </div>
          <div class="field">
            <label>{{ T.stats_to }}</label>
            <input id="branch_stats_to" type="date">
          </div>
        </div>
        <button class="submit" onclick="applyBranchStatsRange()">{{ T.stats_apply }}</button>
        <div id="branchStatsRangeResult" style="margin-top:14px;"></div>
        <div id="branchChartWrap" style="margin-top:16px; display:none;">
          <canvas id="branchChart" height="220"></canvas>
        </div>
      </div>
    </div>
  </div>
  {% endif %}

  {% if sms_enabled %}
  <div id="view-sms" class="card" style="display:none;">
    <p style="margin-top:0;">{{ T.sms_intro }}</p>
    <div class="field">
      <label>{{ T.sms_email }}</label>
      <input id="eskiz_email" value="{{ eskiz_email }}" placeholder="you@example.com" autocomplete="off">
    </div>
    <div class="field">
      <label>{{ T.sms_password }}</label>
      <input id="eskiz_password" type="password" autocomplete="new-password" placeholder="{{ T.sms_password_ph }}">
      <div class="hint-text">{{ T.sms_password_hint }}</div>
    </div>
    <button class="submit" onclick="saveSmsSettings()">{{ T.btn_save }}</button>
  </div>
  {% endif %}

  {% if warehouse_enabled and not is_employee %}
  <div id="view-warehouse" style="display:none;">
    <div class="subtabs">
      <div class="subtab active" id="subwh-own" onclick="showWhSubTab('own')">{{ T.wh_sub_own }}</div>
      <div class="subtab" id="subwh-branches" onclick="showWhSubTab('branches')" style="display:none;">{{ T.wh_sub_branches }}</div>
      <div class="subtab" id="subwh-network" onclick="showWhSubTab('network')" style="display:none;">{{ T.wh_sub_network }}</div>
    </div>

    <div id="whOwnView">
      <div class="card" id="whSummaryCard">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_title }}</label>
        <div class="wh-kpis" id="whKpis">{{ T.stats_loading }}</div>
        <div id="whAttention"></div>
      </div>

      <div class="card" style="margin-top:14px;">
        <div class="wh-toolbar">
          <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="whSearch" placeholder="{{ T.whs_search }}" oninput="renderProductCards()" autocomplete="off"></div>
          <button class="wh-tbtn wh-tbtn-primary" onclick="openAddProductModal()"><i class="fa-solid fa-plus"></i> {{ T.whs_add_short }}</button>
          <button class="wh-tbtn" title="{{ T.imp_title }}" onclick="openImportModal()"><i class="fa-solid fa-file-excel" style="color:#15803D;"></i> Excel</button>
        </div>
        <div class="brand-chips" id="whCatChips"></div>
        <div id="whCards"></div>
        <button class="wh-tbtn wh-tbtn-wide" id="whPurchaseBtn" onclick="openPurchaseList()"><i class="fa-solid fa-clipboard-list"></i> <span>{{ T.whs_purchase_list }}</span></button>
      </div>

      <div class="card" style="margin-top:14px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_movements }}</label>
        <div id="restockHistory"></div>
      </div>

      {% if true %}
      <div class="card" id="usdRateCard" style="margin-top:14px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.usd_rate_title }}</label>
        <div class="row2">
          <div class="field">
            <label>{{ T.usd_rate_label }}</label>
            <input id="usd_rate_input" type="number" step="0.01" placeholder="{{ '%g'|format(usd_rate_head) if usd_rate_head else 12700 }}" value="{{ '%g'|format(usd_rate_own) if usd_rate_own else '' }}">
          </div>
        </div>
        <button class="submit" onclick="saveUsdRate()">{{ T.usd_rate_save }}</button>
        <div id="usdRateSaved" style="display:none; color:#1B8A5A; font-size:13px; margin-top:8px;">✓ {{ T.usd_rate_saved }}</div>
        <div class="hint-text usd-inherit-hint" style="display:none; margin-top:8px; color:#0F52BA;"></div>
        <p class="hint-text" style="margin-top:10px; margin-bottom:0;">{{ T.usd_rate_hint }}</p>
      </div>
      {% endif %}


    </div>

    <div id="whNetworkView" style="display:none;">
      <div class="card">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.whn_title }}</label>
        <div class="hint-text" style="margin-bottom:12px;">{{ T.whn_hint }}</div>
        <div class="net-actions">
          <button class="wh-tbtn wh-tbtn-primary" onclick="openShipModal()"><i class="fa-solid fa-truck"></i> {{ T.shp_title }}</button>
          <button class="wh-tbtn" onclick="openCatalogModal()"><i class="fa-solid fa-copy"></i> {{ T.cat_title }}</button>
          <button class="wh-tbtn" onclick="openTransferModal({})"><i class="fa-solid fa-right-left"></i> {{ T.whn_transfer_one }}</button>
        </div>
        <div id="whNetMatrix">{{ T.stats_loading }}</div>
      </div>
    </div>

    <div id="whBranchesView" style="display:none;">
      <div id="branchWarehouseSummary" class="whn-summary" style="margin-bottom:12px;"></div>
      <div id="whbDetail" style="display:none;">
        <div class="card">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_title }} — <span id="whbTitle"></span></label>
          <div class="wh-kpis" id="whbKpis"></div>
          <div id="whbAttention"></div>
        </div>
        <div class="card" style="margin-top:14px;">
          <div class="wh-toolbar">
            <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="whbSearch" placeholder="{{ T.whs_search }}" oninput="renderProductCards('br')" autocomplete="off"></div>
          </div>
          <div class="brand-chips" id="whbCatChips"></div>
          <div id="whbCards"></div>
          <button class="wh-tbtn wh-tbtn-wide" id="whbPurchaseBtn" onclick="openPurchaseList('br')"><i class="fa-solid fa-clipboard-list"></i> <span>{{ T.whs_purchase_list }}</span></button>
        </div>
        <div class="card" style="margin-top:14px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_movements }}</label>
          <div id="whbHistory"></div>
        </div>
      </div>

    </div>

  </div>

  {% if warehouse_enabled and not is_employee and not is_branch %}
  <div id="view-suppliers" style="display:none;">
    <div class="sp-top">
      <h2>{{ T.tab_suppliers }}</h2>
      <button class="sp-pill" id="spRatePill" onclick="openSupRate()"></button>
      <div class="sp-menu-wrap">
        <button class="sp-icon" onclick="toggleSupMenu(event)" aria-label="{{ T.nav_more }}"><i class="fa-solid fa-ellipsis"></i></button>
        <div class="sp-menu" id="spMenu">
          <button onclick="closeSupMenu(); openSupplierModal();"><i class="fa-solid fa-plus"></i>{{ T.sp_menu_add }}</button>
          <button onclick="closeSupMenu(); openNewOrder();"><i class="fa-solid fa-cart-plus"></i>{{ T.ord_new }}</button>
          <button onclick="closeSupMenu(); openSupRate();"><i class="fa-solid fa-dollar-sign"></i>{{ T.usd_rate_title }}</button>
          <button onclick="closeSupMenu(); openSupArchive();"><i class="fa-solid fa-box-archive"></i><span id="spMenuArchive">{{ T.sp_archive }}</span></button>
        </div>
      </div>
    </div>
    <div id="spHero"></div>
    <div class="sp-list" id="supList"><div class="sp-empty">{{ T.stats_loading }}</div></div>
    <div class="sp-sec"><b>{{ T.ord_list_title }}</b><button class="sp-link" id="ordToggle" onclick="toggleAllOrders()"></button></div>
    <div class="sp-strip" id="ordStrip"></div>
    <div class="sp-orders" id="ordWrap">
      <div id="ordList">{{ T.stats_loading }}</div>
      <button class="wh-tbtn wh-tbtn-wide" id="ordMoreBtn" style="display:none; margin:6px 0 10px;" onclick="loadMoreOrders()">{{ T.sp_show_more }}</button>
    </div>
  </div>
  {% endif %}

  <div id="whModals">
      <div class="modal-overlay" id="addProductModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.wh_add_product }}</h3>
          <div class="row2">
            <div class="field">
              <label>{{ T.wh_category }}</label>
              <select id="wh_new_category" onchange="onWhCategoryChanged()"></select>
            </div>
            <div class="field">
              <label>{{ T.wh_product_name }}</label>
              <input id="wh_new_name" placeholder="MITANOL 5W-30">
            </div>
          </div>
          <div class="field" id="wh_new_unit_row" style="display:none;">
            <label>{{ T.wh_unit }}</label>
            <select id="wh_new_unit">
              <option value="pc">{{ T.unit_pc }}</option>
              <option value="l">{{ T.unit_l }}</option>
            </select>
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.wh_sell_price }}</label>
              <input id="wh_new_sell_price" type="number" placeholder="45000" oninput="onSumFieldEdited('wh_new_sell_price', 'wh_new_sell_usd')">
            </div>
            <div class="field">
              <label>{{ T.usd_sell_label }}</label>
              <input id="wh_new_sell_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('wh_new_sell_usd', 'wh_new_sell_price')">
            </div>
          </div>
          <div class="row2" {% if is_branch %}style="display:none;"{% endif %}>
            <div class="field">
              <label>{{ T.wh_purchase_price }}</label>
              <input id="wh_new_purchase_price" type="number" placeholder="30000" oninput="onSumFieldEdited('wh_new_purchase_price', 'wh_new_purchase_usd')">
            </div>
            <div class="field">
              <label>{{ T.usd_buy_label }}</label>
              <input id="wh_new_purchase_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('wh_new_purchase_usd', 'wh_new_purchase_price')">
            </div>
          </div>
          <div class="field">
            <label>{{ T.wh_initial_stock }}</label>
            <input id="wh_new_stock" type="number" placeholder="0">
          </div>
          <button class="submit" onclick="createProduct()">{{ T.wh_add_btn }}</button>
          <button class="close-btn" onclick="closeWhModal('addProductModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="purchaseListModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.whs_purchase_list }}</h3>
          <div class="hint-text" style="margin-bottom:10px;">{{ T.whs_purchase_hint }}</div>
          <div id="purchaseListBody"></div>
          <button class="submit" onclick="sendPurchaseList('tg')" style="background:#2AABEE;"><i class="fa-brands fa-telegram"></i> {{ T.whs_send_tg }}</button>
          <button class="submit" onclick="sendPurchaseList('copy')" style="background:var(--border); color:var(--text);"><i class="fa-regular fa-copy"></i> {{ T.whs_copy }}</button>
          {% if not is_branch and not is_employee %}<button class="submit" id="plOrderBtn" onclick="purchaseToOrder()" style="background:#DBEAFE; color:#0F52BA; display:none;"><i class="fa-solid fa-truck-ramp-box"></i> {{ T.ord_from_purchase }}</button>{% endif %}
          <button class="close-btn" onclick="closeWhModal('purchaseListModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      {% if not is_branch and not is_employee %}
      <div class="modal-overlay" id="orderModal">
        <div class="modal modal-wide" style="text-align:left;">
          <div id="ordHead"></div>
          <div id="ordBody"></div>
          <button class="close-btn" onclick="closeWhModal('orderModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="supplierModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;" id="supModalTitle">{{ T.sup_add }}</h3>
          <div class="field">
            <label>{{ T.sup_name }}</label>
            <input id="sup_name" placeholder="MITAL" maxlength="80" autocomplete="off">
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.sup_phone }}</label>
              <input id="sup_phone" type="tel" inputmode="tel" placeholder="+998 90 123 45 67" maxlength="40">
            </div>
            <div class="field">
              <label>{{ T.sup_telegram }}</label>
              <input id="sup_telegram" placeholder="@username" maxlength="64" autocomplete="off" autocapitalize="off">
            </div>
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.sup_contact }}</label>
              <input id="sup_contact" maxlength="80">
            </div>
            <div class="field">
              <label>{{ T.sup_days }}</label>
              <input id="sup_delivery_days" placeholder="{{ T.sup_days_ph }}" maxlength="80">
            </div>
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.sup_pay_days }}</label>
              <input id="sup_pay_days" type="number" inputmode="numeric" min="0" max="365" placeholder="{{ T.sup_pay_days_ph }}">
            </div>
            <div class="field">
              <label>{{ T.sup_note }}</label>
              <input id="sup_note" maxlength="300">
            </div>
          </div>
          <div id="supTgBlock" class="sup-tg" style="display:none;"></div>
          <button class="submit" onclick="saveSupplier()">{{ T.sup_save }}</button>
          <button class="submit" id="supDeleteBtn" onclick="deleteSupplierBtn()" style="background:#FEE2E2; color:#B91C1C;">{{ T.sup_delete }}</button>
          <button class="close-btn" onclick="closeWhModal('supplierModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="supProductsModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.sup_assign_title }}: <span id="supProdTitle"></span></h3>
          <div class="hint-text" style="margin-bottom:10px;">{{ T.sup_assign_hint }}</div>
          <div class="wh-search" style="margin-bottom:8px;"><i class="fa-solid fa-magnifying-glass"></i><input id="supProdSearch" placeholder="{{ T.whs_search }}" oninput="renderSupProducts()" autocomplete="off"></div>
          <div style="display:flex; gap:8px; margin-bottom:6px;">
            <button class="wh-tbtn wh-tbtn-sm" onclick="supSelectVisible(true)">{{ T.sup_all }}</button>
            <button class="wh-tbtn wh-tbtn-sm" onclick="supSelectVisible(false)">{{ T.sup_none }}</button>
            <span class="hint-text" id="supProdCount" style="margin:auto 0 auto auto;"></span>
          </div>
          <div id="supProdList"></div>
          <button class="submit" onclick="saveSupplierProducts()">{{ T.sup_save }}</button>
          <button class="close-btn" onclick="closeWhModal('supProductsModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      {% endif %}
      {% if not is_branch and not is_employee %}
      <div class="modal-overlay sp-sheet-ov" id="supCardModal" onclick="if (event.target === this) closeWhModal('supCardModal')">
        <div class="modal modal-wide sp-sheet">
          <div class="sp-grab"></div>
          <button class="sp-x" onclick="closeWhModal('supCardModal')" aria-label="{{ T.modal_close }}"><i class="fa-solid fa-xmark"></i></button>
          <div class="sp-sheet-body" id="supCardScroll"><div id="supCardBody"></div></div>
          <div class="sp-foot" id="supCardFoot"></div>
        </div>
      </div>
      <div class="modal-overlay" id="supRateModal" onclick="if (event.target === this) closeWhModal('supRateModal')">
        <div class="modal" style="text-align:left; max-width:380px;">
          <h3 style="text-align:center; margin-top:0;">{{ T.usd_rate_title }}</h3>
          <div class="field">
            <label>{{ T.usd_rate_label }}</label>
            <input id="usd_rate_input_sup" type="number" inputmode="decimal" step="0.01" placeholder="12700" value="{{ '%g'|format(usd_rate_own) if usd_rate_own else '' }}">
          </div>
          <p class="hint-text" style="margin-top:0;">{{ T.sp_rate_hint }}</p>
          <button class="submit" onclick="saveSupRate()">{{ T.usd_rate_save }}</button>
          <div id="usdRateSaved_sup" style="display:none; color:#1B8A5A; font-size:13px; margin-top:8px; text-align:center;">✓ {{ T.usd_rate_saved }}</div>
          <button class="close-btn" onclick="closeWhModal('supRateModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="orderNewProductModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.onp_title }}</h3>
          <div class="hint-text" id="onp_hint" style="margin-bottom:10px;"></div>
          <div class="field">
            <label>{{ T.wh_category }}</label>
            <select id="onp_category" onchange="onOnpCategoryChanged()"></select>
          </div>
          <div class="field">
            <label>{{ T.wh_product_name }}</label>
            <input id="onp_name" placeholder="MITANOL 5W-30" autocomplete="off">
          </div>
          <div class="field" id="onp_unit_row" style="display:none;">
            <label>{{ T.wh_unit }}</label>
            <select id="onp_unit">
              <option value="pc">{{ T.unit_pc }}</option>
              <option value="l">{{ T.unit_l }}</option>
            </select>
          </div>
          <div class="field">
            <label>{{ T.onp_sell }}</label>
            <input id="onp_sell" type="number" inputmode="numeric" placeholder="45000">
          </div>
          <button class="submit" onclick="saveOrderNewProduct()">{{ T.onp_save }}</button>
          <button class="close-btn" onclick="closeWhModal('orderNewProductModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      {% endif %}
      <div class="modal-overlay" id="transferModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.whn_transfer }}</h3>
          <div class="row2">
            <div class="field">
              <label>{{ T.whn_from }}</label>
              <select id="tr_from" onchange="onTransferFromChanged()"></select>
            </div>
            <div class="field">
              <label>{{ T.whn_to }}</label>
              <select id="tr_to"></select>
            </div>
          </div>
          <div class="field">
            <label>{{ T.whn_product }}</label>
            <select id="tr_product" onchange="onTransferProductChanged()"></select>
            <div class="hint-text" id="tr_available"></div>
          </div>
          <div class="field">
            <label>{{ T.whn_qty }}</label>
            <input id="tr_qty" type="number" step="0.5" min="0">
          </div>
          <button class="submit" onclick="submitTransfer()">{{ T.whn_send }}</button>
          <button class="close-btn" onclick="closeWhModal('transferModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="editProductModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.whe_title }}</h3>
          <div class="hint-text" id="ep_category" style="text-align:center; margin:-6px 0 12px;"></div>
          <div class="field">
            <label>{{ T.wh_product_name }}</label>
            <input id="ep_name">
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.wh_sell_price }}</label>
              <input id="ep_sell" type="number" min="0" oninput="onSumFieldEdited('ep_sell', 'ep_sell_usd')">
            </div>
            <div class="field" id="ep_sell_usd_wrap">
              <label>{{ T.usd_sell_label }}</label>
              <input id="ep_sell_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('ep_sell_usd', 'ep_sell')">
            </div>
          </div>
          <div class="row2" id="ep_buy_wrap">
            <div class="field">
              <label>{{ T.wh_purchase_price }}</label>
              <input id="ep_buy" type="number" min="0" oninput="onSumFieldEdited('ep_buy', 'ep_buy_usd')">
            </div>
            <div class="field" id="ep_usd_wrap">
              <label>{{ T.usd_buy_label }}</label>
              <input id="ep_buy_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('ep_buy_usd', 'ep_buy')">
            </div>
          </div>
          <div class="hint-text" id="ep_price_hint" style="margin:-4px 0 10px;">{{ T.whe_price_hint }}</div>
          <div class="row2">
            <div class="field">
              <label>{{ T.whe_stock_label }} (<span id="ep_unit"></span>)</label>
              <input id="ep_stock" type="number" min="0" step="0.5" oninput="onEditStockChanged()">
            </div>
            <div class="field" id="ep_reason_wrap" style="display:none;">
              <label>{{ T.whe_reason_label }}</label>
              <input id="ep_reason" placeholder="{{ T.whe_reason_ph }}">
            </div>
          </div>
          <div class="hint-text" id="ep_stock_hint" style="margin:-4px 0 10px;">{{ T.whe_stock_hint }}</div>
          <button class="submit" onclick="submitEditProduct()">{{ T.whe_save }}</button>
          <button class="close-btn" onclick="closeWhModal('editProductModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="shipModal">
        <div class="modal modal-wide ship-modal" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.shp_title }}</h3>
          <div class="row2">
            <div class="field"><label>{{ T.whn_from }}</label><select id="shp_from" onchange="loadShipPlan()"></select></div>
            <div class="field"><label>{{ T.whn_to }}</label><select id="shp_to" onchange="loadShipPlan()"></select></div>
          </div>
          <div class="wh-toolbar" style="margin-bottom:8px;">
            <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="shp_search" placeholder="{{ T.whs_search }}" oninput="renderShipRows()" autocomplete="off"></div>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px;">
            <button class="wh-tbtn wh-tbtn-sm" onclick="shipAutofill()"><i class="fa-solid fa-wand-magic-sparkles"></i> {{ T.shp_autofill }}</button>
            <button class="wh-tbtn wh-tbtn-sm" onclick="shipClear()"><i class="fa-solid fa-eraser"></i> {{ T.shp_clear }}</button>
            <label class="wh-tbtn wh-tbtn-sm" style="display:inline-flex; align-items:center; gap:6px; margin:0; text-transform:none; letter-spacing:0; color:var(--text);"><input type="checkbox" id="shp_only_selected" onchange="renderShipRows()" style="width:auto; margin:0;"> {{ T.shp_only_selected }}</label>
          </div>
          <div class="brand-chips" id="shp_cats"></div>
          <div id="shp_list" class="ship-list">{{ T.stats_loading }}</div>
          <div class="ship-foot">
            <span id="shp_summary"></span>
            <button class="submit" style="width:auto; padding:10px 18px; margin:0;" onclick="submitShip()"><i class="fa-solid fa-truck"></i> {{ T.shp_send }}</button>
          </div>
          <button class="close-btn" onclick="closeWhModal('shipModal')">{{ T.modal_close }}</button>
        </div>
      </div>

      <div class="modal-overlay" id="catalogModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.cat_title }}</h3>
          <div class="hint-text" style="margin-bottom:12px;">{{ T.cat_hint }}</div>
          <div class="field"><label>{{ T.cat_branch }}</label><select id="cat_branch"></select></div>
          <label style="display:block; margin:6px 0;">{{ T.cat_types }}</label>
          <div id="cat_types" style="display:flex; flex-direction:column; gap:6px; margin-bottom:12px;"></div>
          <button class="submit" onclick="submitCatalog()"><i class="fa-solid fa-copy"></i> {{ T.cat_copy }}</button>
          <button class="close-btn" onclick="closeWhModal('catalogModal')">{{ T.modal_close }}</button>
        </div>
      </div>

      <div class="modal-overlay" id="importModal">
        <div class="modal modal-wide ship-modal" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.imp_title }}</h3>
          <div class="imp-steps">
            <div><b>1.</b> {{ T.imp_step1 }} <a class="wh-tbtn wh-tbtn-sm" href="/api/products/import_template" style="text-decoration:none; display:inline-block; margin-left:4px;"><i class="fa-solid fa-download"></i> {{ T.imp_template }}</a></div>
            <div><b>2.</b> {{ T.imp_step2 }}</div>
            <div><b>3.</b> {{ T.imp_step3 }}</div>
          </div>
          <input type="file" id="imp_file" accept=".xlsx" onchange="previewImport()" style="margin:10px 0;">
          <div id="imp_preview"></div>
          <button class="submit" id="imp_apply_btn" style="display:none;" onclick="applyImport()"></button>
          <button class="close-btn" onclick="closeWhModal('importModal')">{{ T.modal_close }}</button>
        </div>
      </div>
  </div>
  {% endif %}
</div>
"""

MODAL_AND_SCRIPT = """
<div class="modal-overlay" id="restockModal">
  <div class="modal" style="text-align:left;">
    <h3 style="text-align:center;" id="restockModalTitle">{{ T.wh_restock_title }}</h3>
    <div class="field">
      <label>{{ T.wh_restock_qty }}</label>
      <input id="restock_qty" type="number">
    </div>
    <div class="field" {% if is_branch %}style="display:none;"{% endif %}>
      <label>{{ T.wh_purchase_price }}</label>
      <input id="restock_price" type="number" oninput="onSumFieldEdited('restock_price', 'restock_price_usd')">
    </div>
    <div class="field" {% if is_branch %}style="display:none;"{% endif %}>
      <label>{{ T.usd_price_label }}</label>
      <input id="restock_price_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('restock_price_usd', 'restock_price')">
    </div>
    <div class="field">
      <label>{{ T.wh_restock_date }}</label>
      <input id="restock_date" type="date">
    </div>
    <button class="submit" onclick="submitRestock()">{{ T.wh_restock_btn }}</button>
    <button class="close-btn" onclick="closeRestockModal()">{{ T.modal_close }}</button>
  </div>
</div>

<div class="modal-overlay" id="linkModal">
  <div class="modal">
    <h3 id="modalPlate"></h3>
    <div class="hint-text">{{ T.modal_hint }}</div>
    <img id="modalQr" alt="QR">
    <div class="link-text" id="modalLink"></div>
    <a class="wa-btn" id="modalTg" href="#" target="_blank"><button class="submit" type="button" style="background:#2AABEE;">{{ T.modal_send_tg }}</button></a>
    <a class="wa-btn" id="modalWa" href="#" target="_blank"><button class="submit" type="button">{{ T.modal_send_wa }}</button></a>
    <button class="submit" onclick="copyLink()" style="background:var(--border);">{{ T.modal_copy }}</button>
    <button class="close-btn" onclick="closeModal()">{{ T.modal_close }}</button>
  </div>
</div>

<div class="modal-overlay" id="editModal">
  <div class="modal modal-wide" style="text-align:left;">
    <h3 style="text-align:center;" id="svcModalTitle">{{ T.entry_edit_title }}</h3>
    <div class="field">
      <label>{{ T.field_mileage }}</label>
      <input id="edit_mileage" type="number">
    </div>
    <div class="field">
      <label>{{ T.field_next_mileage }}</label>
      <input id="edit_next_mileage" type="number">
    </div>

    {% if warehouse_enabled %}
    <div class="field pick-search">
      <label>{{ T.pick_search_label }}</label>
      <input id="svcPickSearch" type="search" placeholder="{{ T.pick_search_ph }}" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search" oninput="renderPickResults('svc')" onkeydown="onPickKey(event, 'svc')">
      <div id="svcPickResults" class="pick-results"></div>
    </div>
    {% endif %}
    <div class="field">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_fluids }}</label>
    </div>
    <div id="svcFluidsList"></div>

    <div class="field" style="margin-top:10px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_filters }}</label>
    </div>
    <div id="svcFiltersList"></div>

    <div class="field" style="margin-top:10px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_other }}</label>
    </div>
    <div class="row2">
      <div class="field">
        <label>{{ T.field_other_name }}</label>
        <input id="svc_other_name" placeholder="{{ T.field_other_name_ph }}">
      </div>
      <div class="field">
        <label>{{ T.field_price }}</label>
        <input id="svc_other_price" type="number" placeholder="0" oninput="updateSvcTotal()">
      </div>
    </div>

    {% if warehouse_enabled %}
    <div class="field" style="margin-top:10px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.wh_other_stock_title }}</label>
    </div>
    <div id="svcOtherStockRows"></div>
    <button type="button" class="submit" style="padding:8px; background:var(--border);" onclick="addOtherStockRow('svcOther')">{{ T.wh_add_row }}</button>
    {% endif %}

    <div class="field" style="margin-top:10px; padding:12px; background:var(--field-bg); border-radius:10px;">
      <label style="font-size:15px;">{{ T.field_total }}</label>
      <div id="svcTotalCost" style="font-size:22px; font-weight:600; color:var(--btn); font-family:var(--font-mono);">0</div>
    </div>

    <div class="field" style="margin-top:10px;">
      <label>{{ T.payment_split_label }}</label>
      <div class="row2">
        <div class="field">
          <label style="font-size:11px;"><i class="fa-solid fa-money-bill"></i> {{ T.payment_cash }}</label>
          <input id="svc_pay_cash" type="number" placeholder="0" oninput="onSvcPayCashInput()">
        </div>
        <div class="field">
          <label style="font-size:11px;"><i class="fa-solid fa-credit-card"></i> {{ T.payment_card }}</label>
          <input id="svc_pay_card" type="number" placeholder="0" oninput="onSvcPayCardInput()">
        </div>
      </div>
    </div>

    <div class="field" style="margin-top:10px;">
      <label>{{ T.field_interval }}</label>
      <div style="display:flex; gap:8px;">
        <input id="edit_interval_value" type="number" style="flex:1;">
        <select id="edit_interval_unit" style="flex:1;">
          <option value="months">{{ T.unit_months }}</option>
          <option value="days">{{ T.unit_days }}</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label>{{ T.field_notes }}</label>
      <textarea id="edit_notes" rows="2"></textarea>
    </div>
    <button class="submit" onclick="saveEdit()">{{ T.btn_save }}</button>
    <button class="close-btn" onclick="closeEditModal()">{{ T.modal_close }}</button>
  </div>
</div>

<script>
const T = {{ t_json|safe }};
const LANG = {{ lang|tojson }};
const WAREHOUSE_ENABLED = {{ warehouse_enabled|tojson }};
const IS_BRANCH = {{ is_branch|tojson }};
let USD_RATE = {{ usd_rate|tojson }};
const HEAD_USD_RATE = {{ usd_rate_head|tojson }};  // у филиала: курс главной точки (если свой не задан)
const BOT_USERNAME = {{ bot_username|tojson }};
function clientLink(token) { return token && BOT_USERNAME ? 'https://t.me/' + BOT_USERNAME + '?start=' + token : ''; }
// Графики (Chart.js, ~70 КБ) нужны только в «Статистике» — грузим их не при
// старте, а когда раздел открыли (или тихо в фоне через несколько секунд).
// Когда библиотека пришла, а статистика уже на экране — перерисовываем её.
let CHART_LOADING = false;
function ensureChartJs() {
  if (typeof Chart !== 'undefined' || CHART_LOADING) return;
  CHART_LOADING = true;
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js';
  s.crossOrigin = 'anonymous';
  s.onload = () => { if (CURRENT_TAB === 'stats') refreshCurrentView(); };
  s.onerror = () => { CHART_LOADING = false; s.remove(); };
  document.head.appendChild(s);
}
window.addEventListener('load', () => {
  if (document.getElementById('view-stats')) setTimeout(ensureChartJs, 4000);
});

let carsCache = [];
let lastKnownNextMileage = null;

function checkMileageVsDue() {
  const el = document.getElementById('mileageCompare');
  if (!el) return;
  const entered = parseFloat(document.getElementById('mileage').value);
  if (!lastKnownNextMileage || isNaN(entered)) { el.innerHTML = ''; return; }
  const diff = entered - lastKnownNextMileage;
  if (diff > 0) {
    el.innerHTML = `<div class="mileage-compare over">⚠️ ${T.mileage_over_due} ${lastKnownNextMileage.toLocaleString('ru-RU')} ${T.km_short} — ${T.mileage_over_by} ${diff.toLocaleString('ru-RU')} ${T.km_short}</div>`;
  } else {
    el.innerHTML = `<div class="mileage-compare ok">${T.mileage_within_due} ${lastKnownNextMileage.toLocaleString('ru-RU')} ${T.km_short}</div>`;
  }
}

let openHistoryRow = null;
let historyDataCache = {};  // { plate: [entry, entry, ...] } — чтобы кнопки не тащили сырые данные записи (с заметками, апострофами и т.п.) прямо в HTML-атрибут onclick, а брали их отсюда по id

let CURRENT_TAB = 'add';
function showTab(t, keepScroll) {
  CURRENT_TAB = t;
  document.getElementById('view-add').style.display = t === 'add' ? 'block' : 'none';
  document.getElementById('view-table').style.display = t === 'table' ? 'block' : 'none';
  document.getElementById('view-debts').style.display = t === 'debts' ? 'block' : 'none';
  document.getElementById('view-broadcast').style.display = t === 'broadcast' ? 'block' : 'none';
  document.getElementById('tab-add').classList.toggle('active', t === 'add');
  document.getElementById('tab-table').classList.toggle('active', t === 'table');
  document.getElementById('tab-debts').classList.toggle('active', t === 'debts');
  document.getElementById('tab-broadcast').classList.toggle('active', t === 'broadcast');
  const exportView = document.getElementById('view-export');
  const exportTab = document.getElementById('tab-export');
  if (exportView) exportView.style.display = t === 'export' ? 'block' : 'none';
  if (exportTab) exportTab.classList.toggle('active', t === 'export');
  const statsView = document.getElementById('view-stats');
  const statsTab = document.getElementById('tab-stats');
  if (statsView) statsView.style.display = t === 'stats' ? 'block' : 'none';
  if (statsTab) statsTab.classList.toggle('active', t === 'stats');
  const smsView = document.getElementById('view-sms');
  const smsTab = document.getElementById('tab-sms');
  if (smsView) smsView.style.display = t === 'sms' ? 'block' : 'none';
  if (smsTab) smsTab.classList.toggle('active', t === 'sms');
  const whView = document.getElementById('view-warehouse');
  const whTab = document.getElementById('tab-warehouse');
  if (whView) whView.style.display = t === 'warehouse' ? 'block' : 'none';
  if (whTab) whTab.classList.toggle('active', t === 'warehouse');
  const supView = document.getElementById('view-suppliers');
  const supTab = document.getElementById('tab-suppliers');
  if (supView) supView.style.display = t === 'suppliers' ? 'block' : 'none';
  if (supTab) supTab.classList.toggle('active', t === 'suppliers');
  const expView = document.getElementById('view-expenses');
  const expTab = document.getElementById('tab-expenses');
  if (expView) expView.style.display = t === 'expenses' ? 'block' : 'none';
  if (expTab) expTab.classList.toggle('active', t === 'expenses');
  if (t === 'table') loadCars();
  if (t === 'debts') loadDebts();
  if (t === 'expenses') loadExpensesTab();
  if (t === 'broadcast') loadBroadcastInfo();
  document.querySelectorAll('[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === t));
  // пункт «Ещё» подсвечен, если открыт раздел, которого нет в нижней панели
  const sheet = document.getElementById('moreSheet');
  const bbMore = document.getElementById('bbMore');
  if (sheet && bbMore) bbMore.classList.toggle('active', !sheet.dataset.bar.split(',').includes(t));
  if (!keepScroll) window.scrollTo(0, 0);
  if (t === 'stats') { ensureChartJs(); loadStats(); }
  if (t === 'warehouse') loadWarehouse();
  if (t === 'suppliers') loadSuppliersTab();
  const courseView = document.getElementById('view-course');
  const courseTab = document.getElementById('tab-course');
  if (courseView) courseView.style.display = t === 'course' ? 'block' : 'none';
  if (courseTab) courseTab.classList.toggle('active', t === 'course');
  if (t === 'course') loadCourse();
  const staffView = document.getElementById('view-staff');
  const staffTab = document.getElementById('tab-staff');
  if (staffView) staffView.style.display = t === 'staff' ? 'block' : 'none';
  if (staffTab) staffTab.classList.toggle('active', t === 'staff');
  if (t === 'staff') loadStaff();
  const helpView = document.getElementById('view-help');
  const helpTab = document.getElementById('tab-help');
  if (helpView) helpView.style.display = t === 'help' ? 'block' : 'none';
  if (helpTab) helpTab.classList.toggle('active', t === 'help');
}

// ---------- Сотрудники: владелец точки сам ----------
let STAFF_SEQ = 0;
function staffFmt(s, vars) { return String(s).replace(/{([a-z_]+)}/g, (m, k) => (k in vars ? vars[k] : m)); }
function staffErr(field, text) {
  ['full_name', 'username', 'password'].forEach(f => {
    const el = document.getElementById('staff_err_' + f);
    if (el) { el.textContent = f === field ? (text || '') : ''; el.classList.toggle('on', f === field && !!text); }
  });
}
function staffShowCreds(title, login, password) {
  const text = staffFmt(T.staff_creds, { url: location.origin + '/login', login: login, password: password });
  const box = document.getElementById('staffCreds');
  box.innerHTML = `<div class="staff-creds"><div class="staff-creds-t">${escapeHtml(title)}</div>
    <div class="staff-creds-v" id="staffCredsText"></div>
    <button type="button" class="staff-copy" onclick="copyStaffCreds(this)">${escapeHtml(T.staff_copy)}</button></div>`;
  document.getElementById('staffCredsText').textContent = text;
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
async function copyStaffCreds(btn) {
  const text = document.getElementById('staffCredsText').textContent;
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta);
    ta.select(); try { document.execCommand('copy'); } catch (e2) {} ta.remove();
  }
  btn.textContent = T.staff_copied;
}
async function loadStaff() {
  const seq = ++STAFF_SEQ;
  let d;
  try { d = await (await fetch('/api/staff', { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (seq !== STAFF_SEQ || !d || !d.ok) return;
  const box = document.getElementById('staffList');
  if (!d.employees.length) { box.innerHTML = `<div class="hint-text">${escapeHtml(T.staff_empty)}</div>`; return; }
  box.innerHTML = d.employees.map(e => {
    const nm = escapeHtml(JSON.stringify(e.full_name || e.username));
    return `<div class="staff-row ${e.is_active ? '' : 'off'}">
      <div class="staff-who"><b>${escapeHtml(e.full_name || e.username)}</b>
        <span class="hint-text">@${escapeHtml(e.username)}</span>
        <span class="staff-pill ${e.is_active ? 'on' : ''}">${escapeHtml(e.is_active ? T.staff_active : T.staff_off)}</span></div>
      <div class="staff-btns">
        <button type="button" onclick="staffResetPw(${e.id}, ${nm}, ${escapeHtml(JSON.stringify(e.username))})"><i class="fa-solid fa-key"></i> ${escapeHtml(T.staff_btn_pw)}</button>
        <button type="button" onclick="staffToggle(${e.id}, ${e.is_active ? 0 : 1}, ${nm})">${e.is_active ? '<i class="fa-solid fa-pause"></i> ' + escapeHtml(T.staff_btn_off) : '<i class="fa-solid fa-play"></i> ' + escapeHtml(T.staff_btn_on)}</button>
        <button type="button" class="del" onclick="staffDelete(${e.id}, ${nm})"><i class="fa-solid fa-trash"></i> ${escapeHtml(T.staff_btn_del)}</button>
      </div></div>`;
  }).join('');
}
async function createStaff() {
  staffErr(null);
  const body = {
    full_name: document.getElementById('staff_name').value.trim(),
    username: document.getElementById('staff_login').value.trim(),
    password: document.getElementById('staff_pw').value,
  };
  if (body.full_name.length < 2) return staffErr('full_name', T.staff_err_name);
  if (!/^[A-Za-z0-9_]{3,30}$/.test(body.username)) return staffErr('username', T.staff_err_login);
  if (body.password && body.password.length < 6) return staffErr('password', T.staff_err_password);
  const res = await fetch('/api/staff', { method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  const d = await res.json();
  if (!d.ok) { if (d.field) staffErr(d.field, d.error); else alert(d.error || 'Error'); return; }
  ['staff_name', 'staff_login', 'staff_pw'].forEach(id => { document.getElementById(id).value = ''; });
  staffShowCreds(T.staff_created, d.username, d.password);
  loadStaff();
}
async function staffResetPw(id, name, login) {
  if (!confirm(staffFmt(T.staff_confirm_pw, { name: name }))) return;
  const d = await (await fetch(`/api/staff/${id}/reset_password`, { method: 'POST', credentials: 'same-origin' })).json();
  if (!d.ok) { alert(d.error); return; }
  staffShowCreds(T.staff_new_pw, login, d.password);
}
async function staffToggle(id, on, name) {
  if (!on && !confirm(staffFmt(T.staff_confirm_off, { name: name }))) return;
  const d = await (await fetch(`/api/staff/${id}/active`, { method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ active: !!on }) })).json();
  if (!d.ok) { alert(d.error); return; }
  loadStaff();
}
async function staffDelete(id, name) {
  if (!confirm(staffFmt(T.staff_confirm_del, { name: name }))) return;
  const d = await (await fetch(`/api/staff/${id}`, { method: 'DELETE', credentials: 'same-origin' })).json();
  if (!d.ok) { alert(d.error); return; }
  document.getElementById('staffCreds').innerHTML = '';
  loadStaff();
}

// ---------- Обучение: карта курса ----------
let COURSE_SEQ = 0;
async function loadCourse() {
  const seq = ++COURSE_SEQ;
  const map = document.getElementById('courseMap');
  const list = document.getElementById('courseList');
  if (!map) return;
  let d;
  try {
    const r = await fetch('/api/course', { credentials: 'same-origin' });
    d = await r.json();
  } catch (e) { return; }
  if (seq !== COURSE_SEQ || !d || !d.ok) return;
  const mods = d.modules;
  const done = mods.filter(m => m.passed).length;
  document.getElementById('courseHead').textContent = done === mods.length
    ? T.course_all_done
    : T.course_head.replace('{done}', done).replace('{left}', mods.length - done);
  let cur = mods.find(m => !m.passed);
  const W = map.clientWidth || 340;
  const ROW = 96, TOP = 40;
  const xs = [0.5, 0.78, 0.5, 0.22];
  const pts = mods.map((m, i) => ({ x: Math.round(W * xs[i % 4]), y: TOP + i * ROW }));
  const H = TOP + (mods.length - 1) * ROW + 70;
  map.style.height = H + 'px';
  let path = 'M' + pts[0].x + ' ' + pts[0].y;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], my = (a.y + b.y) / 2;
    path += ' C' + a.x + ' ' + my + ', ' + b.x + ' ' + my + ', ' + b.x + ' ' + b.y;
  }
  const curIdx = cur ? mods.indexOf(cur) : mods.length - 1;
  let donePath = 'M' + pts[0].x + ' ' + pts[0].y;
  for (let i = 1; i <= curIdx; i++) {
    const a = pts[i - 1], b = pts[i], my = (a.y + b.y) / 2;
    donePath += ' C' + a.x + ' ' + my + ', ' + b.x + ' ' + my + ', ' + b.x + ' ' + b.y;
  }
  let html = '<svg class="course-path" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true">'
    + '<path d="' + path + '" fill="none" stroke="#1E3F7A" stroke-width="12" stroke-linecap="round"/>'
    + (curIdx > 0 ? '<path d="' + donePath + '" fill="none" stroke="#1FB5F2" stroke-width="12" stroke-linecap="round"/>' : '')
    + '</svg>';
  mods.forEach((m, i) => {
    const p = pts[i];
    const isCur = cur && m.n === cur.n;
    const cls = isCur ? 'cur' : (m.passed ? 'done' : 'open');
    const sz = isCur ? 32 : 24;
    html += '<a class="cnode ' + cls + '" href="/course/' + m.n + '" style="left:' + p.x + 'px; top:' + (p.y - sz) + 'px" aria-label="' + escapeHtml(m.n + '. ' + m.title) + '">' + m.n
      + (m.passed && m.best != null ? '<span class="cscore">' + m.best + '/10</span>' : '') + '</a>';
  });
  if (cur) {
    const p = pts[curIdx];
    // карточка — на стороне, противоположной следующему кружку, чтобы его не закрывать
    const k = curIdx % 4;
    const toRight = (k === 2 || k === 3);
    const CW = Math.min(140, Math.round(W * 0.4));
    const left = toRight ? Math.min(p.x + 40, W - CW - 4) : Math.max(p.x - 40 - CW, 4);
    html += '<div class="ccard" style="left:' + left + 'px; top:' + (p.y - 40) + 'px; width:' + CW + 'px">'
      + '<span class="cc-meta">' + cur.n + ' · ' + cur.mins + ' ' + T.course_min + '</span>'
      + '<span class="cc-title">' + escapeHtml(cur.title) + '</span>'
      + '<a href="/course/' + cur.n + '">' + (cur.opened ? T.course_continue : T.course_start) + '</a></div>';
  }
  map.innerHTML = html;
  list.innerHTML = mods.map(m => '<a class="course-row' + (m.passed ? ' done' : '') + '" href="/course/' + m.n + '"><b>' + m.n + '</b><span class="cr-t">' + escapeHtml(m.title) + '</span>'
    + (m.best != null ? '<span class="cr-s">' + m.best + '/10</span>' : '') + '</a>').join('');
}

// Данные на экране не должны «застревать»: если приложение было свёрнуто
// дольше минуты или страница восстановлена из кеша браузера (кнопка «назад»,
// возврат в приложение), тихо перезагружаем открытый раздел — без прокрутки вверх.
function refreshCurrentView() {
  if (CURRENT_TAB === 'add') return;  // форму ввода не трогаем — там могут быть несохранённые данные
  showTab(CURRENT_TAB, true);
  const vis = id => { const el = document.getElementById(id); return el && el.style.display !== 'none'; };
  if (CURRENT_TAB === 'warehouse') {
    if (vis('whBranchesView') && WH.branchId) selectWhBranch(WH.branchId);
    if (vis('whNetworkView')) { WH.net = null; loadNetworkStock(); }
  }
  if (CURRENT_TAB === 'stats' && vis('statsBranchesView')) { loadNetworkCompare(); loadNetwork(); }
}
let HIDDEN_AT = 0;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { HIDDEN_AT = Date.now(); return; }
  if (HIDDEN_AT && Date.now() - HIDDEN_AT > 60 * 1000) refreshCurrentView();
  HIDDEN_AT = 0;
});
window.addEventListener('pageshow', e => { if (e.persisted) refreshCurrentView(); });
document.addEventListener('DOMContentLoaded', () => {
  if (new URLSearchParams(location.search).get('tab') === 'course') {
    showTab('course');
    history.replaceState(null, '', '/');
  }
  if (new URLSearchParams(location.search).get('tab') === 'help') {
    showTab('help');
    history.replaceState(null, '', '/');
  }
});

function openMore() {
  document.getElementById('moreSheet').classList.add('open');
  document.getElementById('moreBackdrop').classList.add('open');
}

function closeMore() {
  document.getElementById('moreSheet').classList.remove('open');
  document.getElementById('moreBackdrop').classList.remove('open');
}

(function setupMoreSheet() {
  // в шторке «Ещё» прячем то, что уже есть в нижней панели
  const sheet = document.getElementById('moreSheet');
  if (!sheet) return;
  const inBar = sheet.dataset.bar.split(',');
  sheet.querySelectorAll('[data-more-slot]').forEach(el => {
    if (inBar.includes(el.dataset.moreSlot)) el.classList.add('hidden-in-more');
  });
  // закрытие свайпом вниз
  let startY = null;
  sheet.addEventListener('touchstart', e => { startY = e.touches[0].clientY; }, { passive: true });
  sheet.addEventListener('touchend', e => {
    if (startY !== null && e.changedTouches[0].clientY - startY > 60) closeMore();
    startY = null;
  });
})();

async function refreshNavBadges() {
  // красная цифра — число просроченных долгов (видна на «Долгах» и на «Ещё»)
  try {
    const debts = await (await fetch('/api/debts')).json();
    const overdue = (debts || []).filter(d => d.is_overdue).length;
    document.querySelectorAll('[data-badge="debts"]').forEach(b => {
      b.textContent = overdue;
      b.classList.toggle('show', overdue > 0);
    });
    NAV_BADGES.debts = overdue;
    if (document.getElementById('tab-suppliers')) {
      const sd = await (await fetch('/api/suppliers')).json();
      if (sd && sd.ok) NAV_BADGES.suppliers = sd.totals.overdue_count;
    }
  } catch (e) {}
  renderNavBadges();
}
const NAV_BADGES = { debts: 0, suppliers: 0 };
function renderNavBadges() {
  // поставщики с просроченным долгом — красная цифра на «Поставщиках» и на «Ещё»
  document.querySelectorAll('[data-badge="suppliers"]').forEach(b => {
    b.textContent = NAV_BADGES.suppliers;
    b.classList.toggle('show', NAV_BADGES.suppliers > 0);
  });
  const sheet = document.getElementById('moreSheet');
  const moreBadge = document.getElementById('moreBadge');
  if (sheet && moreBadge) {
    const debtsInMore = !sheet.dataset.bar.split(',').includes('debts');
    const n = (debtsInMore ? NAV_BADGES.debts : 0) + NAV_BADGES.suppliers;
    moreBadge.textContent = n;
    moreBadge.classList.toggle('show', n > 0);
  }
}
refreshNavBadges();
setInterval(refreshNavBadges, 5 * 60 * 1000);

async function saveSmsSettings() {
  const emailEl = document.getElementById('eskiz_email');
  const passwordEl = document.getElementById('eskiz_password');
  if (!emailEl || !passwordEl) return;  // вкладка SMS не отрисована (выключена для этой точки)
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  const res = await fetch('/api/sms_settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email, password})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.sms_saved, true);
    document.getElementById('eskiz_password').value = '';
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

// ---- Склад ----
let productsCache = [];
let restockingProductId = null;

function renderWarehouseCategoryOptions() {
  const sel = document.getElementById('wh_new_category');
  if (!sel) return;
  const allKeys = FLUID_KEYS.concat(FILTER_KEYS);
  sel.innerHTML = allKeys.map(key => `<option value="${key}">${T[key]}</option>`).join('')
    + `<option value="other">${T.wh_category_other}</option>`;
}

function onWhCategoryChanged() {
  const sel = document.getElementById('wh_new_category');
  const unitRow = document.getElementById('wh_new_unit_row');
  if (unitRow) unitRow.style.display = sel.value === 'other' ? 'block' : 'none';
}

// ---- Склад: одна логика отрисовки для своего склада (ctx 'own', элементы wh*)
// и для склада выбранного филиала у главного (ctx 'br', элементы whb*).
const WH = { hasBranches: false, net: null, branchId: null, branches: [] };
const WHCTX = {
  own: { p: 'wh', products: [], summary: null, cat: 'all', showCost: !IS_BRANCH, shopId: null, name: '' },
  br:  { p: 'whb', products: [], summary: null, cat: 'all', showCost: true, shopId: null, name: '' },
};

async function loadWarehouse() {
  renderWarehouseCategoryOptions();
  let data = null;
  try { data = await (await fetch('/api/warehouse/overview')).json(); } catch (e) {}
  if (data && data.ok) {
    productsCache = data.products;
    WHCTX.own.summary = data.summary;
  } else {
    productsCache = await (await fetch('/api/products')).json();
    WHCTX.own.summary = null;
  }
  WHCTX.own.products = productsCache;
  WHCTX.own.name = ((document.querySelector('.side-shop') || {}).textContent || '').trim();
  renderWarehouseSummary('own');
  renderWhCategoryChips('own');
  renderProductCards('own');
  loadRestockHistory();
  // склад мог поменяться — обновляем списки «марка» в формах замены
  renderItemLists();
  renderSvcItemLists();

  if (!IS_BRANCH) {
    if (document.getElementById('supList')) loadSuppliers();
    try {
      const branches = await (await fetch('/api/my_branches')).json();
      const branchBtn = document.getElementById('subwh-branches');
      WH.hasBranches = branches.length > 0;
      WH.branches = branches;
      const netBtn = document.getElementById('subwh-network');
      if (netBtn) netBtn.style.display = branches.length ? '' : 'none';
      if (branches.length) {
        branchBtn.style.display = '';
        document.getElementById('branchWarehouseSummary').innerHTML = branches.map(b => `
          <div class="whn-shop ${WH.branchId === b.id ? 'active' : ''}" onclick="selectWhBranch(${b.id})">
            <b>${escapeHtml(b.shop_name || b.username)}</b>
            <div class="v">${fmtShort(b.stock_value)} ${T.currency}</div>
            ${T.branch_products_count} ${b.product_count}${b.missing_price_count > 0 ? ` · <span style="color:#B3241C;">⚠️ ${T.branch_missing_price} ${b.missing_price_count}</span>` : ''}
          </div>`).join('');
      } else {
        branchBtn.style.display = 'none';
      }
      renderProductCards('own');
    } catch (e) { /* не главный аккаунт — подвкладку не показываем */ }
  }
}

function whUnit(u) { return u === 'pc' ? T.unit_pc : T.unit_l; }
function whQty(q) { return (Math.round((q || 0) * 100) / 100).toLocaleString('ru-RU'); }
function whEl(key, suffix) { return document.getElementById(WHCTX[key].p + suffix); }

function renderWarehouseSummary(key) {
  const ctx = WHCTX[key];
  const kpis = whEl(key, 'Kpis');
  if (!kpis) return;
  const s = ctx.summary;
  if (!s) { kpis.innerHTML = ''; return; }
  const problems = (s.low_count || 0) + (s.out_count || 0);
  const boxes = [];
  if (ctx.showCost) {
    boxes.push(`<div class="wh-kpi"><b>${fmtShort(s.stock_value)}</b><span>${T.whs_kpi_value}</span></div>`);
    const neg = s.potential_margin < 0;
    boxes.push(`<div class="wh-kpi ${neg ? 'bad' : 'good'}"><b>${neg ? '' : '+'}${fmtShort(s.potential_margin)}</b><span>${neg ? T.whs_kpi_margin_neg : T.whs_kpi_margin}</span></div>`);
  } else {
    boxes.push(`<div class="wh-kpi"><b>${s.product_count}</b><span>${T.whs_kpi_products}</span></div>`);
    boxes.push(`<div class="wh-kpi"><b>${s.reorder_count}</b><span>${T.whs_kpi_reorder}</span></div>`);
  }
  boxes.push(`<div class="wh-kpi ${problems ? 'bad' : ''}"><b>${problems}</b><span>${T.whs_kpi_low}</span></div>`);
  boxes.push(`<div class="wh-kpi ${s.dead_count ? 'muted' : ''}"><b>${s.dead_count}</b><span>${T.whs_kpi_dead}</span></div>`);
  kpis.innerHTML = boxes.join('');

  const att = whEl(key, 'Attention');
  const list = ctx.products;
  const urgent = list.filter(p => p.status === 'out' || p.status === 'low')
    .sort((a, b) => (a.stock_qty || 0) - (b.stock_qty || 0)).slice(0, 6);
  const dead = list.filter(p => p.dead)
    .sort((a, b) => (b.stock_qty * (b.purchase_price || 0)) - (a.stock_qty * (a.purchase_price || 0))).slice(0, 4);
  const noPrice = ctx.showCost && key === 'br' ? list.filter(p => p.purchase_price == null) : [];
  let html = '';
  if (urgent.length) {
    html += `<div class="wh-att-title">${T.whs_att_urgent}</div>` + urgent.map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-triangle-exclamation" style="color:${p.status === 'out' ? '#DC2626' : '#D97706'};"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${whStatusText(p)}</span></div>
        <button class="wh-tbtn wh-tbtn-sm" onclick="openRestockModal(${p.id}, ${escapeHtml(JSON.stringify(p.name))}, ${ctx.shopId || 'null'})">+ ${T.wh_restock_action}</button>
      </div>`).join('');
  }
  if (noPrice.length) {
    html += `<div class="wh-att-title">${T.whb_att_no_price}</div>` + noPrice.slice(0, 6).map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-tag" style="color:#B3241C;"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${T.whb_no_price_hint}</span></div>
        <button class="wh-tbtn wh-tbtn-sm" onclick="openEditProductModal('br', ${p.id})">${T.whb_set_price}</button>
      </div>`).join('');
  }
  if (dead.length) {
    html += `<div class="wh-att-title">${T.whs_att_dead}</div>` + dead.map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-hourglass-half" style="color:#94A3B8;"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${whQty(p.stock_qty)} ${whUnit(p.unit)}${ctx.showCost && p.purchase_price ? ` · ${T.whs_frozen} ${fmtShort(p.stock_qty * p.purchase_price)} ${T.currency}` : ''}</span></div>
      </div>`).join('');
  }
  if (!html && list.length) html = `<div class="wh-att-title" style="color:#15803D;"><i class="fa-solid fa-circle-check"></i> ${T.whs_att_ok}</div>`;
  att.innerHTML = html;
}

function whStatusText(p) {
  const u = whUnit(p.unit);
  if (p.status === 'out') return `<span class="warn">${T.whs_out}</span>${p.per_day ? ` · ~${whQty(p.per_day)} ${u}${T.whs_per_day}` : ''}`;
  if (p.per_day) {
    const cls = p.status === 'low' ? 'warn' : (p.days_left < 14 ? 'amber' : '');
    let t = `~${whQty(p.per_day)} ${u}${T.whs_per_day} · <span class="${cls}">${T.whs_enough_for} ${p.days_left} ${T.whs_days}</span>`;
    if (p.reorder_qty > 0) t += ` · ${T.whs_order} ${whQty(p.reorder_qty)} ${u}`;
    return t;
  }
  if (p.dead) return T.whs_no_sales_30;
  if (p.status === 'low') return `<span class="amber">${T.whs_low_left}</span>`;
  return T.whs_no_sales_yet;
}

function renderWhCategoryChips(key) {
  const ctx = WHCTX[key];
  const el = whEl(key, 'CatChips');
  if (!el) return;
  const counts = {};
  ctx.products.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; });
  const order = FLUID_KEYS.concat(FILTER_KEYS, ['other']).filter(k => counts[k]);
  if (ctx.cat !== 'all' && !counts[ctx.cat]) ctx.cat = 'all';
  el.innerHTML = [`<div class="brand-chip ${ctx.cat === 'all' ? 'active' : ''}" onclick="setWhCat('${key}', 'all')">${T.whs_all}<span class="bc-sub">${ctx.products.length}</span></div>`]
    .concat(order.map(k => `<div class="brand-chip ${ctx.cat === k ? 'active' : ''}" onclick="setWhCat('${key}', '${k}')">${escapeHtml(k === 'other' ? T.wh_category_other : (T[k] || k))}<span class="bc-sub">${counts[k]}</span></div>`))
    .join('');
}

function setWhCat(key, k) {
  WHCTX[key].cat = k;
  renderWhCategoryChips(key);
  renderProductCards(key);
}

function renderProductCards(key) {
  key = key || 'own';
  const ctx = WHCTX[key];
  const box = whEl(key, 'Cards');
  if (!box) return;
  const q = ((whEl(key, 'Search') || {}).value || '').trim().toLowerCase();
  const rank = { out: 0, low: 1, ok: 2 };
  const all = ctx.products;
  const list = all
    .filter(p => ctx.cat === 'all' || p.category === ctx.cat)
    .filter(p => !q || p.name.toLowerCase().includes(q))
    .sort((a, b) => (rank[a.status] ?? 2) - (rank[b.status] ?? 2) || a.name.localeCompare(b.name));
  const maxStock = Math.max(1, ...all.map(p => p.stock_qty || 0));

  const btn = whEl(key, 'PurchaseBtn');
  if (btn) {
    const n = all.filter(p => p.reorder_qty > 0 || p.status === 'out').length;
    btn.querySelector('span').textContent = `${T.whs_purchase_list}${n ? ` (${n})` : ''}`;
  }

  if (!all.length) { box.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.wh_no_products}</div>`; return; }
  if (!list.length) { box.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.whs_nothing_found}</div>`; return; }

  const canTransfer = !IS_BRANCH && WH.hasBranches;
  box.innerHTML = list.map(p => {
    const st = p.status || 'ok';
    const width = (p.days_left !== null && p.days_left !== undefined)
      ? Math.min(100, Math.max(3, p.days_left / 60 * 100))
      : Math.min(100, Math.max(3, (p.stock_qty || 0) / maxStock * 100));
    const color = st === 'out' ? '#DC2626' : st === 'low' ? '#F59E0B' : (p.dead ? '#CBD5E1' : '#22C55E');
    const missingPrice = key === 'br' && p.purchase_price == null;
    const price = [
      p.sell_price ? `${fmtNum(p.sell_price)} ${T.currency}` : '',
      ctx.showCost && p.purchase_price ? `${T.whs_buy} ${fmtNum(p.purchase_price)}` : '',
      ctx.showCost && p.margin_pct !== null && p.margin_pct !== undefined
        ? (p.margin_pct < 0 ? `<span style="color:#B91C1C; font-weight:700;">⚠️ ${p.margin_pct}% ${T.whs_below_cost}</span>` : `<span class="mg">+${p.margin_pct}%</span>`) : '',
      missingPrice ? `<span style="color:#B3241C; font-weight:700;">⚠️ ${T.branch_missing_price.replace(':', '')}</span>` : '',
    ].filter(Boolean).join(' · ');
    const name = escapeHtml(JSON.stringify(p.name));
    const shopArg = ctx.shopId || 'null';
    const actions = [
      `<button class="wh-tbtn wh-tbtn-sm" onclick="openRestockModal(${p.id}, ${name}, ${shopArg})">+ ${T.wh_restock_action}</button>`,
      `<button class="wh-tbtn wh-tbtn-icon" title="${T.whe_title}" onclick="openEditProductModal('${key}', ${p.id})"><i class="fa-solid fa-pen"></i></button>`,
      canTransfer ? `<button class="wh-tbtn wh-tbtn-icon" title="${T.whn_transfer}" onclick="openTransferModal({fromShop: ${shopArg}, productId: ${p.id}})"><i class="fa-solid fa-right-left"></i></button>` : '',
      key === 'own' ? `<button class="wh-tbtn wh-tbtn-icon" title="${T.wh_delete_action}" onclick="deleteProduct(${p.id}, ${name})"><i class="fa-solid fa-trash-can"></i></button>` : '',
    ].join('');
    return `
      <div class="whc st-${st}">
        <div class="whc-top">
          <div class="whc-name"><b>${escapeHtml(p.name)}</b><span>${escapeHtml(p.category === 'other' ? T.wh_category_other : (T[p.category] || p.category))}</span></div>
          <div class="whc-qty">${whQty(p.stock_qty)} ${whUnit(p.unit)}</div>
        </div>
        <div class="whc-bar"><i style="width:${width}%; background:${color};"></i></div>
        <div class="whc-info">${whStatusText(p)}</div>
        <div class="whc-bottom">
          <span class="whc-price">${price || '—'}</span>
          <div class="whc-actions">${actions}</div>
        </div>
      </div>`;
  }).join('');
}

function openAddProductModal() {
  renderWarehouseCategoryOptions();
  if (WHCTX.own.cat !== 'all') document.getElementById('wh_new_category').value = WHCTX.own.cat;
  onWhCategoryChanged();
  document.getElementById('addProductModal').classList.add('open');
}

function closeWhModal(id) {
  document.getElementById(id).classList.remove('open');
}

// ---- список закупки ----
function openPurchaseList(key) {
  key = key || 'own';
  const ctx = WHCTX[key];
  let items = ctx.products
    .filter(p => p.reorder_qty > 0 || p.status === 'out')
    .sort((a, b) => (a.days_left ?? -1) - (b.days_left ?? -1));
  // свой склад и есть поставщики — группируем список по поставщикам
  const grouped = key === 'own' && !IS_BRANCH && SUP.list.length > 0;
  const supKey = p => p.supplier_id ? '0' + supName(p.supplier_id).toUpperCase() : '1';
  if (grouped) items = items.slice().sort((a, b) => supKey(a).localeCompare(supKey(b)));
  let lastSup = -1;
  const groupHead = p => {
    if (!grouped || (p.supplier_id || 0) === lastSup) return '';
    lastSup = p.supplier_id || 0;
    return `<div class="pl-group">${escapeHtml(supName(p.supplier_id))}</div>`;
  };
  const orderBtn = document.getElementById('plOrderBtn');
  if (orderBtn) orderBtn.style.display = key === 'own' ? '' : 'none';
  document.getElementById('purchaseListBody').innerHTML = items.length ? items.map(p => groupHead(p) + `
    <div class="pl-row">
      <input type="checkbox" id="pl_on_${p.id}" checked>
      <div class="pl-name"><b>${escapeHtml(p.name)}</b><span>${T.whs_now} ${whQty(p.stock_qty)} ${whUnit(p.unit)}${p.per_day ? ` · ~${whQty(p.per_day)}${T.whs_per_day}` : ''}</span></div>
      <input type="number" id="pl_qty_${p.id}" value="${p.reorder_qty || ''}" placeholder="${T.whn_qty}" min="0">
      <span style="font-size:12px; color:#64748B;">${whUnit(p.unit)}</span>
    </div>`).join('') : `<div class="hint-text" style="padding:10px 0;">${T.whs_purchase_empty}</div>`;
  WH.purchaseItems = items;
  WH.purchaseShopName = ctx.name;
  document.getElementById('purchaseListModal').classList.add('open');
}

function buildPurchaseText() {
  const lines = [];
  (WH.purchaseItems || []).forEach(p => {
    const on = document.getElementById('pl_on_' + p.id);
    const qty = parseFloat((document.getElementById('pl_qty_' + p.id) || {}).value);
    if (on && on.checked && qty > 0) lines.push(`${lines.length + 1}. ${p.name} — ${whQty(qty)} ${whUnit(p.unit)}`);
  });
  if (!lines.length) return '';
  return `${T.whs_order_title} — ${(WH.purchaseShopName || '').trim()} (${fmtDate(new Date())})\\n` + lines.join('\\n');
}

async function sendPurchaseList(mode) {
  const text = buildPurchaseText();
  if (!text) { showMsg(T.whs_purchase_pick, false); return; }
  if (mode === 'tg') {
    window.open('https://t.me/share/url?url=' + encodeURIComponent(' ') + '&text=' + encodeURIComponent(text), '_blank');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showMsg(T.whs_copied, true);
  } catch (e) {
    prompt(T.whs_copy, text);
  }
}

// ---- Поставщики и заказы поставщику (главная / самостоятельная точка) ----
// Путь заказа: черновик → отправлен → получен (товар лёг на склад с ценами
// закупки) → раздан по филиалам. Поставщик необязателен: заказ «Без
// поставщика» — это просто список покупок (например, поездка на рынок).
const SUP = { list: [], loaded: false, editId: null, assignId: null, checked: new Set() };
const ORD = { list: [], cur: null, mode: 'view', dist: null, distFor: null, limit: 40, total: 0, filter: 'active' };

async function ordFetch(url, method, body) {
  try {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return await (await fetch(url, opts)).json();
  } catch (e) { return { ok: false, error: 'network' }; }
}
function ordErr(d) {
  const code = (d && d.error) || '';
  let text = T['ord_err_' + code] || T['sup_err_' + code] || (T.msg_error + ' ' + code);
  if (code === 'problems' && d.problems) text = T.ord_err_not_enough + ': ' + d.problems.map(p => escapeHtml(p.name || '')).join(', ');
  else if (d && d.name) text += ': ' + escapeHtml(d.name);
  return text;
}
function ordDate(s) { return s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : ''; }
function supName(id) {
  const s = SUP.list.find(x => x.id === id);
  return s ? s.name : T.ord_no_supplier;
}
function whCatName(c) { return c === 'other' ? T.wh_category_other : (T[c] || c || ''); }

// ---- раздел «Поставщики» (главное меню) ----
// Долг ведётся в сумах; $ — справочно: в каждой операции сохранён курс того
// дня, а общий долг пересчитывается по текущему курсу (как на «Складе»).
function fmtUsd(x) {
  x = Number(x || 0);
  const v = Math.abs(x) >= 100 ? Math.round(x) : Math.round(x * 100) / 100;
  return '$' + v.toLocaleString('ru-RU');
}
function usdTail(sum) { return USD_RATE && sum ? ' · ≈ ' + fmtUsd(sum / USD_RATE) : ''; }
function supRateStr(r) { return r ? Number(r).toLocaleString('ru-RU') : ''; }

async function ensureOwnProducts() {
  // заказам нужны товары своего склада — подгружаем, если «Склад» ещё не открывали
  if (WHCTX.own.products && WHCTX.own.products.length) return;
  try {
    const d = await (await fetch('/api/warehouse/overview')).json();
    if (d && d.ok) { productsCache = d.products; WHCTX.own.products = d.products; WHCTX.own.summary = d.summary; }
  } catch (e) {}
}

async function loadSuppliersTab() {
  await ensureOwnProducts();
  await Promise.all([loadSuppliers(), loadOrders()]);
}
const loadOrdersTab = loadSuppliersTab;

async function loadSuppliers() {
  const d = await ordFetch('/api/suppliers');
  if (d.ok) {
    SUP.list = d.suppliers; SUP.loaded = true; SUP.botReady = !!d.bot_ready;
    SUP.totals = d.totals; SUP.archived = d.archived_count || 0;
    NAV_BADGES.suppliers = (d.totals && d.totals.overdue_count) || 0;
    renderNavBadges();
  }
  renderSuppliers();
}

function supInitials(name) {
  const w = String(name || '?').replace(/[«»"'()\\-]/g, ' ').trim().split(/\\s+/).filter(Boolean);
  return ((w[0] || '?')[0] + (w[1] ? w[1][0] : (w[0] || '').slice(1, 2))).toUpperCase();
}
function supDaysBetween(a, b) { return Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000); }
function supToday() { return fmtDate(new Date()); }
// цвет и подпись статуса: r — просрочка, a — скоро платить, b — долг без срока / переплата, g — долга нет
function supStatus(s, d) {
  const bal = d ? d.balance : s.balance, overdue = d ? d.overdue : s.overdue;
  const oldest = d ? d.oldest_overdue : s.oldest_overdue, next = d ? d.next_due : s.next_due;
  if (overdue > 0) {
    const n = oldest ? supDaysBetween(oldest, supToday()) : 0;
    return { c: 'r', t: n >= 60 ? T.sp_chip_overdue_months.replace('{n}', Math.floor(n / 30)) : n > 0 ? T.sp_chip_overdue_days.replace('{n}', n) : T.sp_st_overdue };
  }
  if (bal > 0 && next) {
    const n = supDaysBetween(supToday(), next.date);
    return { c: n <= 3 ? 'a' : 'b', t: n <= 0 ? T.sp_chip_today : T.sp_chip_due.replace('{date}', ordDate(next.date).slice(0, 5)).replace('{n}', n) };
  }
  if (bal > 0) return { c: 'b', t: T.sp_st_no_terms };
  if (bal < 0) return { c: 'b', t: T.sp_st_overpaid };
  return { c: 'g', t: T.sd_no_debt };
}
function supShort(n) { return fmtShort(Math.round(n || 0)); }

function renderSupRatePill() {
  const el = document.getElementById('spRatePill');
  if (!el) return;
  el.textContent = USD_RATE ? '$ ' + Number(USD_RATE).toLocaleString('ru-RU') : T.sp_rate_none;
  el.classList.toggle('warn', !USD_RATE);
}

function renderSuppliers() {
  const el = document.getElementById('supList');
  if (!el) return;
  renderSupRatePill();
  const t = SUP.totals || { owe: 0, overdue: 0, overpaid: 0, overdue_count: 0 };
  const owing = SUP.list.filter(s => s.balance > 0).length;
  const hero = document.getElementById('spHero');
  if (hero) {
    if (t.owe > 0) {
      const op = Math.min(100, Math.round(t.overdue / t.owe * 100));
      hero.innerHTML = `<div class="sp-hero">
        <div class="l">${T.sp_hero_title}</div>
        <div class="x">${supShort(t.owe)}<small>${T.currency}</small></div>
        <div class="u">${USD_RATE ? '≈ ' + fmtUsd(t.owe / USD_RATE) + ' · ' : ''}${T.sp_hero_sup.replace('{n}', owing)}${t.overpaid > 0 ? ' · ' + T.sp_st_overpaid + ' ' + supShort(t.overpaid) : ''}</div>
        <div class="sp-bar">${op ? `<i class="o" style="width:${op}%"></i>` : ''}<i class="k" style="width:${100 - op}%"></i></div>
        <div class="sp-leg">${t.overdue > 0 ? `<span class="o">${T.sp_leg_overdue} ${supShort(t.overdue)}</span>` : ''}<span class="k">${T.sp_leg_ok} ${supShort(t.owe - t.overdue)}</span></div>
      </div>`;
    } else {
      hero.innerHTML = `<div class="sp-hero zero"><div class="l">${T.sp_hero_title}</div><div class="x">0<small>${T.currency}</small></div>
        <div class="u">${SUP.list.length ? T.sp_hero_zero : T.sp_hero_empty}${t.overpaid > 0 ? ' · ' + T.sp_st_overpaid + ' ' + supShort(t.overpaid) : ''}</div></div>`;
    }
  }
  const list = SUP.list.slice().sort((a, b) => (b.overdue > 0) - (a.overdue > 0) || b.balance - a.balance || a.name.localeCompare(b.name));
  el.innerHTML = list.length ? list.map(s => {
    const st = supStatus(s);
    const amt = s.balance ? `<b>${supShort(Math.abs(s.balance))}</b><span>${USD_RATE ? '≈ ' + fmtUsd(Math.abs(s.balance) / USD_RATE) : T.currency}</span>` : `<b>0</b><span>${T.currency}</span>`;
    return `<div class="sp-row" onclick="openSupplierCard(${s.id})">
      <div class="sp-av ${st.c}">${escapeHtml(supInitials(s.name))}</div>
      <div class="sp-mid"><div class="sp-nm">${escapeHtml(s.name)}${s.tg_connected ? ' <i class="fa-brands fa-telegram" style="color:#229ED9; font-size:13px;"></i>' : ''}</div><span class="sp-chip ${st.c}">${st.t}</span></div>
      <div class="sp-amt">${amt}${s.balance > 0 ? `<br><button class="sp-pay" onclick="event.stopPropagation(); openSupplierCard(${s.id}, 'payment');">${T.sp_pay_btn}</button>` : ''}</div>
    </div>`;
  }).join('') : `<div class="sp-empty">${T.sup_empty}<br><button class="sp-pay" onclick="openSupplierModal()"><i class="fa-solid fa-plus"></i> ${T.sp_menu_add}</button></div>`;
  const ma = document.getElementById('spMenuArchive');
  if (ma) ma.textContent = T.sp_archive + (SUP.archived ? ` (${SUP.archived})` : '');
}

function toggleSupMenu(e) {
  e.stopPropagation();
  document.getElementById('spMenu').classList.toggle('open');
}
function closeSupMenu() { const m = document.getElementById('spMenu'); if (m) m.classList.remove('open'); }
document.addEventListener('click', e => { if (!e.target.closest || !e.target.closest('.sp-menu-wrap')) closeSupMenu(); });

function openSupRate() {
  const inp = document.getElementById('usd_rate_input_sup');
  document.getElementById('supRateModal').classList.add('open');
  setTimeout(() => { inp.focus(); inp.select && inp.select(); }, 50);
}
async function saveSupRate() {
  await saveUsdRate('usd_rate_input_sup', 'usdRateSaved_sup');
  renderSupRatePill();
  setTimeout(() => closeWhModal('supRateModal'), 700);
}

async function openSupArchive() {
  const m = document.getElementById('supCardModal');
  const body = document.getElementById('supCardBody');
  SUP.cardId = null;
  document.getElementById('supCardFoot').innerHTML = '';
  body.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.stats_loading}</div>`;
  m.classList.add('open');
  const d = await ordFetch('/api/suppliers?archived=1');
  if (!d.ok) { showMsg(ordErr(d), false); closeWhModal('supCardModal'); return; }
  body.innerHTML = `<div class="sp-head"><div class="t">${T.sp_archive}</div></div>
    <div class="hint-text" style="margin-bottom:8px;">${T.sp_archive_hint}</div>
    ${d.suppliers.length ? d.suppliers.map(s => `
      <div class="ord-line">
        <div class="pl-name" style="cursor:pointer;" onclick="openSupplierCard(${s.id})"><b>${escapeHtml(s.name)}</b>
          <span>${s.archived_at ? T.sp_archived_on + ' ' + ordDate(s.archived_at) : ''}${s.balance ? ' · ' + (s.balance > 0 ? T.sd_debt_short + ' ' : T.sp_st_overpaid + ' ') + fmtSum(Math.abs(s.balance)) : ''}</span></div>
        <button class="wh-tbtn wh-tbtn-sm" onclick="restoreSupplier(${s.id})">${T.sp_restore}</button>
      </div>`).join('') : `<div class="hint-text">${T.sp_archive_empty}</div>`}`;
}

async function restoreSupplier(id) {
  const d = await ordFetch(`/api/suppliers/${id}/restore`, 'POST');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.sp_restored, true);
  await loadSuppliers();
  openSupplierCard(id);
}

const SUP_FIELDS = ['name', 'phone', 'telegram', 'contact', 'delivery_days', 'note', 'pay_days'];

function openSupplierModal(id) {
  const s = id ? SUP.list.find(x => x.id === id) : null;
  SUP.editId = s ? s.id : null;
  document.getElementById('supModalTitle').textContent = s ? T.sup_edit : T.sup_add;
  SUP_FIELDS.forEach(k => { document.getElementById('sup_' + k).value = s && s[k] != null && s[k] !== '' ? (k === 'telegram' ? '@' + s[k] : s[k]) : ''; });
  document.getElementById('supDeleteBtn').style.display = s ? '' : 'none';
  renderSupTgBlock(s);
  document.getElementById('supplierModal').classList.add('open');
}

function renderSupTgBlock(s) {
  const el = document.getElementById('supTgBlock');
  if (!el) return;
  if (!s || !SUP.botReady) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.innerHTML = `<b>${T.sup_tg_title}</b>
    ${s.tg_connected ? `<span class="ok">✓ ${T.sup_tg_connected}</span>` : `<span class="no">${T.sup_tg_not_connected}</span><div class="hint-text" style="margin-top:4px;">${T.sup_tg_hint}</div>`}
    <div>
      ${s.tg_connected ? '' : `<button class="wh-tbtn wh-tbtn-primary" onclick="shareSupplierLink(${s.id}, 'tg')"><i class="fa-brands fa-telegram"></i> ${T.sup_tg_send_link}</button>`}
      ${s.tg_connected ? '' : `<button class="wh-tbtn" onclick="shareSupplierLink(${s.id}, 'copy')"><i class="fa-regular fa-copy"></i> ${T.sup_tg_copy_link}</button>`}
      ${s.tg_connected ? `<button class="wh-tbtn" onclick="unlinkSupplierTg(${s.id})">${T.sup_tg_unlink}</button>` : ''}
    </div>`;
}

async function shareSupplierLink(id, how) {
  const d = await ordFetch(`/api/suppliers/${id}/tg_link`);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  const s = SUP.list.find(x => x.id === id) || {};
  const shop = ((document.querySelector('.side-shop') || {}).textContent || '').trim();
  const text = T.sup_tg_invite.replace('{shop}', shop) + '\\n' + d.link;
  if (how === 'tg') {
    if (s.telegram) {
      try { await navigator.clipboard.writeText(text); } catch (e) {}
      window.open('https://t.me/' + encodeURIComponent(s.telegram) + '?text=' + encodeURIComponent(text), '_blank');
    } else {
      window.open('https://t.me/share/url?url=' + encodeURIComponent(d.link) + '&text=' + encodeURIComponent(T.sup_tg_invite.replace('{shop}', shop)), '_blank');
    }
    showMsg(T.sup_tg_after_send, true);
  } else {
    try { await navigator.clipboard.writeText(text); showMsg(T.whs_copied, true); } catch (e) { prompt(T.whs_copy, text); }
  }
}

async function unlinkSupplierTg(id) {
  if (!confirm(T.sup_tg_unlink_confirm)) return;
  const d = await ordFetch(`/api/suppliers/${id}/tg_unlink`, 'POST');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  await loadSuppliers();
  renderSupTgBlock(SUP.list.find(x => x.id === id));
}

async function saveSupplier() {
  const body = {};
  SUP_FIELDS.forEach(k => { body[k] = document.getElementById('sup_' + k).value; });
  if (!body.name.trim()) { showMsg(T.sup_err_empty_name, false); return; }
  const isNew = !SUP.editId;
  const d = await ordFetch(isNew ? '/api/suppliers' : '/api/suppliers/' + SUP.editId, isNew ? 'POST' : 'PUT', body);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  closeWhModal('supplierModal');
  showMsg(T.sup_saved, true);
  await loadSuppliers();
  if (!isNew && SUP.cardId === SUP.editId) { openSupplierCard(SUP.editId); return; }
  if (isNew && ordDraftOpen()) { ORD.cur.supplier_id = d.id; loadOrderSuggestion(); }
  // новому поставщику сразу предлагаем отметить его товары
  if (isNew && WHCTX.own.products.length) openSupProducts(d.id);
}

async function deleteSupplierBtn() {
  const cur = SUP.list.find(x => x.id === SUP.editId);
  const warn = cur && cur.balance ? '\\n\\n⚠️ ' + (cur.balance > 0 ? T.sp_archive_debt_warn : T.sp_archive_over_warn).replace('{sum}', fmtSum(Math.abs(cur.balance))) : '';
  if (!SUP.editId || !confirm(T.sup_delete_confirm + warn)) return;
  const d = await ordFetch('/api/suppliers/' + SUP.editId, 'DELETE');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  WHCTX.own.products.forEach(p => { if (p.supplier_id === SUP.editId) p.supplier_id = null; });
  closeWhModal('supplierModal');
  showMsg(T.sup_deleted, true);
  loadSuppliers();
}

function openSupProducts(id) {
  const s = SUP.list.find(x => x.id === id);
  if (!s) return;
  SUP.assignId = id;
  document.getElementById('supProdTitle').textContent = s.name;
  document.getElementById('supProdSearch').value = '';
  SUP.checked = new Set(WHCTX.own.products.filter(p => p.supplier_id === id).map(p => p.id));
  renderSupProducts();
  document.getElementById('supProductsModal').classList.add('open');
}

function supVisibleProducts() {
  const q = (document.getElementById('supProdSearch').value || '').trim().toLowerCase();
  return WHCTX.own.products
    .filter(p => !q || p.name.toLowerCase().includes(q))
    .sort((a, b) => (a.category || '').localeCompare(b.category || '') || a.name.localeCompare(b.name));
}

function renderSupProducts() {
  const list = supVisibleProducts();
  const el = document.getElementById('supProdList');
  if (!WHCTX.own.products.length) el.innerHTML = `<div class="hint-text" style="padding:10px 0;">${T.wh_no_products}</div>`;
  else if (!list.length) el.innerHTML = `<div class="hint-text" style="padding:10px 0;">${T.whs_nothing_found}</div>`;
  else el.innerHTML = list.map(p => {
    const other = p.supplier_id && p.supplier_id !== SUP.assignId ? ' · ' + T.sup_other_supplier.replace('{name}', escapeHtml(supName(p.supplier_id))) : '';
    return `
      <label class="pl-row" style="cursor:pointer;">
        <input type="checkbox" ${SUP.checked.has(p.id) ? 'checked' : ''} onchange="toggleSupProduct(${p.id}, this.checked)">
        <div class="pl-name"><b>${escapeHtml(p.name)}</b><span>${escapeHtml(whCatName(p.category))}${other}</span></div>
      </label>`;
  }).join('');
  document.getElementById('supProdCount').textContent = T.sup_selected.replace('{n}', SUP.checked.size);
}

function toggleSupProduct(id, on) {
  if (on) SUP.checked.add(id); else SUP.checked.delete(id);
  document.getElementById('supProdCount').textContent = T.sup_selected.replace('{n}', SUP.checked.size);
}

function supSelectVisible(on) {
  supVisibleProducts().forEach(p => { if (on) SUP.checked.add(p.id); else SUP.checked.delete(p.id); });
  renderSupProducts();
}

async function saveSupplierProducts() {
  const id = SUP.assignId;
  const d = await ordFetch(`/api/suppliers/${id}/products`, 'POST', { product_ids: Array.from(SUP.checked) });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  WHCTX.own.products.forEach(p => {
    if (SUP.checked.has(p.id)) p.supplier_id = id;
    else if (p.supplier_id === id) p.supplier_id = null;
  });
  closeWhModal('supProductsModal');
  showMsg(T.sup_assign_saved, true);
  loadSuppliers();
  if (ordDraftOpen() && ORD.cur.supplier_id === id) loadOrderSuggestion();
}

function ordDraftOpen() {
  const m = document.getElementById('orderModal');
  return !!(m && m.classList.contains('open') && ORD.cur && !ORD.cur.id && ORD.mode === 'edit');
}

// ---- список заказов ----
const ORD_ST_COLORS = { draft: ['#B45309', '#FEF3C7'], sent: ['#0F52BA', '#DBEAFE'], received: ['#7C3AED', '#EDE9FE'],
  done: ['#15803D', '#DCFCE7'], cancelled: ['#64748B', '#F1F5F9'] };
function ordBadge(st) {
  const c = ORD_ST_COLORS[st] || ORD_ST_COLORS.draft;
  return `<span class="ord-badge" style="color:${c[0]}; background:${c[1]};">${T['ord_st_' + st] || st}</span>`;
}

async function loadOrders() {
  const d = await ordFetch('/api/orders?limit=' + ORD.limit);
  if (d.ok) { ORD.list = d.orders; ORD.total = d.total || d.orders.length; }
  renderOrders();
}
function loadMoreOrders() { ORD.limit += 40; loadOrders(); }
const ORD_ACTIVE = ['draft', 'sent', 'received'];
function toggleAllOrders() { ORD.filter = ORD.filter === 'all' ? 'active' : 'all'; renderOrders(); }
function setOrderFilter(f) { ORD.filter = ORD.filter === f ? 'active' : f; renderOrders(); }

function renderOrders() {
  const el = document.getElementById('ordList');
  if (!el) return;
  const f = ORD.filter || 'active';
  const cnt = st => ORD.list.filter(o => st.includes(o.status)).length;
  const drafts = cnt(['draft']), transit = cnt(['sent', 'received']);
  const strip = document.getElementById('ordStrip');
  if (strip) strip.innerHTML = `
    <button class="${f === 'draft' ? 'on' : ''}" onclick="setOrderFilter('draft')"><b>${drafts}</b>${T.sp_ord_drafts}</button>
    <button class="${f === 'transit' ? 'on' : ''}" onclick="setOrderFilter('transit')"><b>${transit}</b>${T.sp_ord_transit}</button>
    <button class="new" onclick="openNewOrder()"><b>+</b>${T.sp_ord_new}</button>`;
  const tg = document.getElementById('ordToggle');
  if (tg) {
    tg.textContent = f === 'all' ? T.sp_ord_active : T.sp_ord_all.replace('{n}', ORD.total || ORD.list.length);
    tg.style.display = (ORD.total || ORD.list.length) ? '' : 'none';
  }
  const shown = ORD.list.filter(o => f === 'all' ? true : f === 'draft' ? o.status === 'draft'
    : f === 'transit' ? ['sent', 'received'].includes(o.status) : ORD_ACTIVE.includes(o.status));
  const more = document.getElementById('ordMoreBtn');
  if (more) more.style.display = f === 'all' && ORD.total > ORD.list.length ? '' : 'none';
  const wrap = document.getElementById('ordWrap');
  if (!shown.length) {
    el.innerHTML = `<div class="hint-text" style="padding:12px 0;">${ORD.list.length ? T.sp_ord_none_active : T.ord_empty}</div>`;
    if (wrap) wrap.style.display = ORD.list.length || f !== 'active' ? '' : 'none';
    return;
  }
  if (wrap) wrap.style.display = '';
  el.innerHTML = shown.map(o => `
    <div class="ord-row" onclick="openOrder(${o.id})" style="cursor:pointer;">
      <div class="sup-main"><b>${T.ord_title_n.replace('{n}', o.number)} · ${escapeHtml(o.supplier_name || T.ord_no_supplier)}</b>
        <span>${ordDate(o.created_at)} · ${o.line_count} ${T.ord_positions}${o.received_sum ? ' · ' + supShort(o.received_sum) + ' ' + T.currency : ''}</span></div>
      ${ordBadge(o.status)}
    </div>`).join('');
}

// ---- окно заказа ----
function ordHasBranches() { return !!(ORD.cur && ORD.cur.shops && ORD.cur.shops.length > 1); }
function ordShopName(id) { const s = ((ORD.cur && ORD.cur.shops) || []).find(x => x.id === +id); return s ? s.name : ''; }
function ordProduct(id) { return WHCTX.own.products.find(p => p.id === id); }

async function openNewOrder(supplierId) {
  if (!SUP.loaded) await loadSuppliers();
  if (supplierId === undefined) supplierId = SUP.list.length ? SUP.list[0].id : null;
  ORD.cur = { id: null, status: 'draft', supplier_id: supplierId || null, lines: [], shops: [] };
  ORD.mode = 'edit';
  document.getElementById('orderModal').classList.add('open');
  await loadOrderSuggestion();
}

async function loadOrderSuggestion() {
  const o = ORD.cur;
  document.getElementById('ordBody').innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.stats_loading}</div>`;
  const d = await ordFetch('/api/orders/suggest?supplier_id=' + (o.supplier_id || ''));
  if (ORD.cur !== o) return;  // окно уже переключили на другой заказ
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  o.shops = d.shops;
  o.lines = d.lines.filter(l => l.qty > 0);
  renderOrderModal();
}

function onOrderSupplierChanged(v) {
  if (v === '__new') {
    // поставщика можно завести прямо отсюда — после сохранения он выберется сам
    document.getElementById('ord_supplier').value = ORD.cur.supplier_id || '';
    openSupplierModal();
    return;
  }
  ORD.cur.supplier_id = v ? parseInt(v, 10) : null;
  loadOrderSuggestion();
}

async function openOrder(id, mode) {
  if (!SUP.loaded) await loadSuppliers();
  const d = await ordFetch('/api/orders/' + id);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  d.lines.forEach(l => { l.qty = l.qty_ordered; });
  ORD.cur = d;
  ORD.mode = mode || (d.status === 'draft' ? 'edit' : d.status === 'received' ? 'distribute' : 'view');
  document.getElementById('orderModal').classList.add('open');
  renderOrderModal();
}

function renderOrderModal() {
  const o = ORD.cur;
  const steps = ['draft', 'sent', 'received'].concat(ordHasBranches() ? ['done'] : []);
  const idx = { draft: 0, sent: 1, received: 2, done: steps.length - 1 }[o.status];
  const stepper = o.status === 'cancelled' ? '' : `<div class="ord-steps">${steps.map((st, i) =>
    `<div class="ord-step ${i <= idx ? 'on' : ''}">${i + 1} ${T['ord_step_' + st]}</div>`).join('')}</div>`;
  const dates = o.id ? [o.created_at ? `${T.ord_created} ${ordDate(o.created_at)}` : '', o.sent_at ? `${T.ord_sent_at} ${ordDate(o.sent_at)}` : '',
    o.received_at ? `${T.ord_received_at} ${ordDate(o.received_at)}` : ''].filter(Boolean).join(' · ') : '';
  const sup = o.supplier;
  const supLine = o.id ? `<div class="ord-sub">${escapeHtml(sup ? sup.name : T.ord_no_supplier)}${sup && sup.contact ? ' · ' + escapeHtml(sup.contact) : ''}${sup && sup.delivery_days ? ' · ' + escapeHtml(sup.delivery_days) : ''}</div>` : '';
  document.getElementById('ordHead').innerHTML = `
    <div class="ord-title"><b>${o.id ? T.ord_title_n.replace('{n}', o.number) : T.ord_new}</b>${o.id ? ordBadge(o.status) : ''}</div>
    ${supLine}${dates ? `<div class="ord-sub">${dates}</div>` : ''}${stepper}`;
  const render = { edit: renderOrderEdit, send: renderOrderSend, receive: renderOrderReceive, distribute: renderOrderDistribute }[ORD.mode] || renderOrderView;
  render();
}

function renderOrderEdit() {
  const o = ORD.cur;
  const supSel = o.id ? '' : `
    <div class="field"><label>${T.ord_supplier}</label>
      <select id="ord_supplier" onchange="onOrderSupplierChanged(this.value)">
        ${SUP.list.map(s => `<option value="${s.id}" ${o.supplier_id === s.id ? 'selected' : ''}>${escapeHtml(s.name)}</option>`).join('')}
        <option value="" ${!o.supplier_id ? 'selected' : ''}>${T.ord_no_supplier}</option>
        <option value="__new">+ ${T.sup_add}</option>
      </select>
      ${SUP.list.length ? '' : `<div class="hint-text" style="margin-top:6px;">${T.ord_no_suppliers_hint}</div>`}</div>`;
  const rows = o.lines.map((l, i) => {
    const parts = ordHasBranches() && l.alloc ? Object.entries(l.alloc).filter(e => e[1] > 0)
      .map(e => `${escapeHtml(ordShopName(e[0]))} ${whQty(e[1])}`).join(' · ') : '';
    const stock = l.stock_qty !== null && l.stock_qty !== undefined ? `${T.whs_now} ${whQty(l.stock_qty)} ${whUnit(l.unit)}` : '';
    return `
      <div class="ord-line">
        <div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${[stock, parts].filter(Boolean).join(' · ')}</span></div>
        <input type="number" inputmode="decimal" min="0" step="any" value="${l.qty || ''}" oninput="setOrderQty(${i}, this.value)">
        <span class="ord-unit">${whUnit(l.unit)}</span>
        <button class="ord-x" onclick="removeOrderLine(${i})" aria-label="${T.wh_delete_action}"><i class="fa-solid fa-xmark"></i></button>
      </div>`;
  }).join('');
  const inOrder = new Set(o.lines.map(l => l.product_id));
  const mine = p => (p.supplier_id || null) === (o.supplier_id || null);
  const free = WHCTX.own.products.filter(p => !inOrder.has(p.id));
  const opt = p => `<option value="${p.id}">${escapeHtml(p.name)} (${whQty(p.stock_qty)} ${whUnit(p.unit)})</option>`;
  const own = free.filter(mine), others = free.filter(p => !mine(p));
  const addSel = `
    <select id="ord_add" onchange="addOrderLine(this.value)" style="margin-top:10px;">
      <option value="">+ ${T.ord_add_product}</option>
      <option value="__new">✨ ${T.onp_option}</option>
      ${own.length ? `<optgroup label="${o.supplier_id ? T.ord_grp_supplier : T.ord_no_supplier}">${own.map(opt).join('')}</optgroup>` : ''}
      ${others.length ? `<optgroup label="${T.ord_grp_other}">${others.map(opt).join('')}</optgroup>` : ''}
    </select>`;
  const draft = !!o.id;
  document.getElementById('ordBody').innerHTML = `
    ${supSel}
    <div class="hint-text" style="margin-bottom:4px;">${o.lines.length ? T.ord_auto_hint : T.ord_no_lines}</div>
    ${rows}${addSel}
    <div class="ord-total" id="ordTotal"></div>
    <button class="submit" onclick="sendOrder()"><i class="fa-solid fa-paper-plane"></i> ${T.ord_send_btn}</button>
    <button class="submit" onclick="saveOrderDraft()" style="background:var(--border); color:var(--text);">${T.ord_save_draft}</button>
    <button class="submit" onclick="receiveFromDraft()" style="background:#DCFCE7; color:#15803D;"><i class="fa-solid fa-box-open"></i> ${T.ord_receive_now}</button>
    ${draft ? `<button class="submit" onclick="cancelOrderBtn()" style="background:#FEE2E2; color:#B91C1C;">${T.ord_delete_draft}</button>` : ''}`;
  updateOrderTotal();
}

function setOrderQty(i, v) { ORD.cur.lines[i].qty = Math.max(0, parseFloat(v) || 0); updateOrderTotal(); }
function removeOrderLine(i) { ORD.cur.lines.splice(i, 1); renderOrderEdit(); }

function addOrderLine(pid) {
  if (pid === '__new') { document.getElementById('ord_add').value = ''; openOrderNewProduct(); return; }
  const p = ordProduct(parseInt(pid, 10));
  if (!p) return;
  ORD.cur.lines.push({ product_id: p.id, name: p.name, unit: p.unit, stock_qty: p.stock_qty, qty: 0, alloc: {} });
  renderOrderEdit();
  const inputs = document.querySelectorAll('#ordBody .ord-line input');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

function updateOrderTotal() {
  const el = document.getElementById('ordTotal');
  if (!el) return;
  const lines = ORD.cur.lines.filter(l => l.qty > 0);
  let sum = 0;
  lines.forEach(l => { const p = ordProduct(l.product_id); if (p && p.purchase_price) sum += p.purchase_price * l.qty; });
  el.innerHTML = `<span>${lines.length} ${T.ord_positions}</span><span>${sum ? '≈ ' + fmtNum(Math.round(sum)) + ' ' + T.currency : ''}</span>`;
}

async function saveOrderLines(send) {
  const o = ORD.cur;
  const lines = o.lines.filter(l => l.qty > 0).map(l => ({ product_id: l.product_id, qty: l.qty, alloc: l.alloc || {} }));
  if (!lines.length) { showMsg(T.ord_err_empty, false); return null; }
  const d = await ordFetch(o.id ? '/api/orders/' + o.id : '/api/orders', o.id ? 'PUT' : 'POST',
    { supplier_id: o.supplier_id, lines, send: !!send });
  if (!d.ok) { showMsg(ordErr(d), false); return null; }
  return d.id;
}

async function saveOrderDraft() {
  const id = await saveOrderLines(false);
  if (!id) return;
  showMsg(T.ord_saved, true);
  closeWhModal('orderModal');
  loadOrders();
}

async function sendOrder() {
  // поставщик подключён к боту — заказ сразу уходит ему в Telegram
  const sup = SUP.list.find(x => x.id === ORD.cur.supplier_id);
  const viaBot = !!(sup && sup.tg_connected);
  const id = await saveOrderLines(!viaBot);
  if (!id) return;
  if (viaBot) {
    const d = await ordFetch(`/api/orders/${id}/send_tg`, 'POST');
    loadOrders();
    if (d.ok) { showMsg(T.ord_tg_sent, true); await openOrder(id, 'view'); return; }
    showMsg(ordErr(d), false);
    await openOrder(id, 'send');
    return;
  }
  loadOrders();
  await openOrder(id, 'send');
}

async function sendOrderBot() {
  const id = ORD.cur.id;
  const d = await ordFetch(`/api/orders/${id}/send_tg`, 'POST');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.ord_tg_sent, true);
  loadOrders();
  await openOrder(id, 'view');
}

async function receiveFromDraft() {
  const id = await saveOrderLines(false);
  if (!id) return;
  loadOrders();
  await openOrder(id, 'receive');
}

async function cancelOrderBtn() {
  const o = ORD.cur;
  if (!o.id) { closeWhModal('orderModal'); return; }
  if (!confirm(o.status === 'draft' ? T.ord_delete_confirm : T.ord_cancel_confirm)) return;
  const d = await ordFetch('/api/orders/' + o.id, 'DELETE');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  closeWhModal('orderModal');
  loadOrders();
}

// ---- отправка поставщику ----
function orderText() {
  const o = ORD.cur;
  const shop = o.shop || {};
  const lines = o.lines.filter(l => l.qty_ordered > 0)
    .map((l, i) => `${i + 1}. ${l.name} — ${whQty(l.qty_ordered)} ${whUnit(l.unit)}`);
  const tail = [shop.address ? `${T.ord_msg_address}: ${shop.address}` : '', shop.phone ? `${T.ord_msg_phone}: ${shop.phone}` : ''].filter(Boolean);
  return [`${T.ord_title_n.replace('{n}', o.number)} — ${shop.name || ''}`, ordDate(o.sent_at || o.created_at), '']
    .concat(lines, tail.length ? [''].concat(tail) : []).join('\\n');
}

function renderOrderSend() {
  const s = ORD.cur.supplier || {};
  const bot = s.tg_connected ? `<button class="submit" onclick="sendOrderBot()" style="background:#2AABEE;"><i class="fa-solid fa-robot"></i> ${T.ord_send_bot}</button>` : '';
  const invite = !s.tg_connected && s.id && SUP.botReady ? `
    <div class="sup-tg"><b>${T.sup_tg_title}</b><div class="hint-text">${T.ord_tg_connect_hint}</div>
      <button class="wh-tbtn wh-tbtn-primary" onclick="shareSupplierLink(${s.id}, 'tg')"><i class="fa-brands fa-telegram"></i> ${T.sup_tg_send_link}</button></div>` : '';
  document.getElementById('ordBody').innerHTML = `
    <div class="hint-text">${T.ord_send_hint}</div>
    <pre class="ord-text">${escapeHtml(orderText())}</pre>
    ${bot}
    <button class="submit" onclick="sendOrderVia('tg')" style="${s.tg_connected ? 'background:var(--border); color:var(--text);' : 'background:#2AABEE;'}"><i class="fa-brands fa-telegram"></i> ${T.whs_send_tg}${s.telegram ? ' · @' + escapeHtml(s.telegram) : ''}</button>
    ${s.phone ? `<button class="submit" onclick="sendOrderVia('wa')" style="background:#25D366;"><i class="fa-brands fa-whatsapp"></i> WhatsApp · ${escapeHtml(s.phone)}</button>` : ''}
    <button class="submit" onclick="sendOrderVia('copy')" style="background:var(--border); color:var(--text);"><i class="fa-regular fa-copy"></i> ${T.whs_copy}</button>
    <button class="submit" onclick="ORD.mode='view'; renderOrderModal();" style="background:#DBEAFE; color:#0F52BA;">${T.ord_done_btn}</button>
    ${invite}`;
}

async function sendOrderVia(ch) {
  const text = orderText();
  const s = ORD.cur.supplier || {};
  if (ch === 'wa') {
    window.open('https://wa.me/' + (s.phone || '').replace(/\\D/g, '') + '?text=' + encodeURIComponent(text), '_blank');
  } else if (ch === 'tg' && s.telegram) {
    // открываем чат поставщика с уже вписанным текстом (остаётся нажать «Отправить»);
    // на всякий случай текст ещё и копируется — если приложение его не подставит
    try { await navigator.clipboard.writeText(text); } catch (e) {}
    window.open('https://t.me/' + encodeURIComponent(s.telegram) + '?text=' + encodeURIComponent(text), '_blank');
    showMsg(T.ord_tg_pasted, true);
  } else if (ch === 'tg') {
    window.open('https://t.me/share/url?url=' + encodeURIComponent(' ') + '&text=' + encodeURIComponent(text), '_blank');
  } else {
    try { await navigator.clipboard.writeText(text); showMsg(T.whs_copied, true); } catch (e) { prompt(T.whs_copy, text); }
  }
}

// ---- просмотр (отправлен / завершён / отменён) ----
function renderOrderView() {
  const o = ORD.cur;
  const st = o.status;
  let total = 0;
  const rows = o.lines.map(l => {
    if (st !== 'done') {
      return `<div class="ord-line"><div class="pl-name"><b>${escapeHtml(l.name)}</b></div><b>${whQty(l.qty_ordered)} ${whUnit(l.unit)}</b></div>`;
    }
    const sum = (l.qty_received || 0) * (l.purchase_price || 0);
    total += sum;
    const dist = Object.entries(l.dist || {}).filter(e => e[1] > 0).map(e => `${escapeHtml(ordShopName(e[0]))} ${whQty(e[1])}`).join(', ');
    const info = [`${T.ord_ordered} ${whQty(l.qty_ordered)}`, `${T.ord_received} ${whQty(l.qty_received)} ${whUnit(l.unit)}`,
      l.purchase_price ? `${fmtNum(l.purchase_price)} ${T.currency}/${T.whs_per_unit}` : '', dist ? '→ ' + dist : ''].filter(Boolean).join(' · ');
    return `<div class="ord-line"><div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${info}</span></div><b style="white-space:nowrap;">${sum ? fmtNum(Math.round(sum)) : '—'}</b></div>`;
  }).join('');
  const buttons = st === 'sent' ? `
    <button class="submit" onclick="ORD.mode='receive'; renderOrderModal();"><i class="fa-solid fa-box-open"></i> ${T.ord_receive_btn}</button>
    <button class="submit" onclick="ORD.mode='send'; renderOrderModal();" style="background:var(--border); color:var(--text);"><i class="fa-solid fa-paper-plane"></i> ${T.ord_resend}</button>
    <button class="submit" onclick="cancelOrderBtn()" style="background:#FEE2E2; color:#B91C1C;">${T.ord_cancel_btn}</button>` : '';
  document.getElementById('ordBody').innerHTML = `${rows}
    ${st === 'done' && total ? `<div class="ord-total"><span>${T.ord_sum_total}</span><span>${fmtNum(Math.round(total))} ${T.currency}</span></div>` : '<div style="height:10px;"></div>'}
    ${buttons}`;
}

// ---- приёмка ----
function renderOrderReceive() {
  const o = ORD.cur;
  const rows = o.lines.map((l, i) => `
    <div class="ord-recv">
      <div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${T.ord_ordered} ${whQty(l.qty_ordered)} ${whUnit(l.unit)}</span></div>
      <div class="ord-recv-grid">
        <label>${T.ord_received}, ${whUnit(l.unit)}<input type="number" inputmode="decimal" min="0" step="any" id="ordr_q_${i}" value="${l.qty_ordered}" oninput="updateRecvTotal()"></label>
        <label>${T.ord_price_unit}<input type="number" inputmode="numeric" min="0" id="ordr_p_${i}" value="${l.current_price ?? ''}" oninput="updateRecvTotal()"></label>
      </div>
    </div>`).join('');
  document.getElementById('ordBody').innerHTML = `
    <div class="hint-text">${T.ord_receive_hint}</div>
    ${rows}
    <div class="ord-total" id="ordRecvTotal"></div>
    ${o.supplier_id ? `<label class="pl-row" style="cursor:pointer; border:none;"><input type="checkbox" id="ordr_paid"><div class="pl-name"><b>${T.ord_paid_now}</b><span>${T.ord_paid_now_hint}</span></div></label>` : ''}
    <button class="submit" onclick="submitReceive()"><i class="fa-solid fa-check"></i> ${T.ord_accept_btn}</button>
    <button class="submit" onclick="ORD.mode=ORD.cur.status==='draft'?'edit':'view'; renderOrderModal();" style="background:var(--border); color:var(--text);">${T.ord_back}</button>`;
  updateRecvTotal();
}

function readReceiveLines() {
  return ORD.cur.lines.map((l, i) => {
    const pv = document.getElementById('ordr_p_' + i).value;
    return { line_id: l.id, qty_received: Math.max(0, parseFloat(document.getElementById('ordr_q_' + i).value) || 0),
      purchase_price: pv === '' ? null : Math.max(0, Math.round(parseFloat(pv) || 0)) };
  });
}

function updateRecvTotal() {
  const el = document.getElementById('ordRecvTotal');
  if (!el) return;
  let sum = 0;
  readReceiveLines().forEach(r => { sum += r.qty_received * (r.purchase_price || 0); });
  el.innerHTML = `<span>${T.ord_sum_total}</span><span>${fmtNum(Math.round(sum))} ${T.currency}</span>`;
}

async function submitReceive() {
  const lines = readReceiveLines();
  if (!lines.some(r => r.qty_received > 0)) { showMsg(T.ord_err_empty, false); return; }
  if (lines.some(r => r.qty_received > 0 && r.purchase_price === null) && !confirm(T.ord_no_price_confirm)) return;
  const id = ORD.cur.id;
  const paidEl = document.getElementById('ordr_paid');
  const d = await ordFetch(`/api/orders/${id}/receive`, 'POST', { lines, paid_now: !!(paidEl && paidEl.checked) });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.ord_received_ok, true);
  ORD.distFor = null;
  loadWarehouse();
  loadOrders();
  loadSuppliers();
  await openOrder(id);
}

// ---- раздача по филиалам ----
function renderOrderDistribute() {
  const o = ORD.cur;
  const branches = o.shops.filter(s => !s.is_head);
  if (ORD.distFor !== o.id) {
    // по умолчанию — доли филиалов из заказа; если пришло меньше, филиалы
    // получают по очереди, сколько хватит
    ORD.dist = o.lines.map(l => {
      let rest = l.qty_received || 0;
      const a = {};
      branches.forEach(b => { const v = Math.min((l.alloc || {})[String(b.id)] || 0, rest); a[b.id] = v; rest -= v; });
      return a;
    });
    ORD.distFor = o.id;
  }
  const rows = o.lines.map((l, i) => (l.qty_received > 0) ? `
    <div class="ord-dist">
      <div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${T.ord_received} ${whQty(l.qty_received)} ${whUnit(l.unit)}</span></div>
      ${branches.map(b => `<label class="ord-dist-row"><span>${escapeHtml(b.name)}</span>
        <input type="number" inputmode="decimal" min="0" step="any" value="${ORD.dist[i][b.id] || ''}" placeholder="0" oninput="setDist(${i}, ${b.id}, this.value)"></label>`).join('')}
      <div class="ord-keep" id="ordKeep_${i}"></div>
    </div>` : '').join('');
  document.getElementById('ordBody').innerHTML = `
    <div class="hint-text">${T.ord_dist_hint}</div>
    ${rows}
    <div style="height:10px;"></div>
    <button class="submit" onclick="submitDistribute()"><i class="fa-solid fa-truck"></i> ${T.ord_dist_btn}</button>
    <button class="submit" onclick="keepAllOrder()" style="background:var(--border); color:var(--text);">${T.ord_keep_all}</button>`;
  o.lines.forEach((l, i) => updateKeep(i));
}

function updateKeep(i) {
  const el = document.getElementById('ordKeep_' + i);
  if (!el) return;
  const l = ORD.cur.lines[i];
  const keep = (l.qty_received || 0) - Object.values(ORD.dist[i]).reduce((a, b) => a + b, 0);
  el.textContent = keep < -1e-9 ? T.ord_err_too_much : `${T.ord_keep_head}: ${whQty(keep)} ${whUnit(l.unit)}`;
  el.classList.toggle('bad', keep < -1e-9);
}

function setDist(i, bid, v) { ORD.dist[i][bid] = Math.max(0, parseFloat(v) || 0); updateKeep(i); }

async function postDistribute(lines) {
  const id = ORD.cur.id;
  const d = await ordFetch(`/api/orders/${id}/distribute`, 'POST', { lines });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(d.branches ? T.ord_distributed_ok : T.ord_received_ok, true);
  loadWarehouse();
  loadOrders();
  await openOrder(id);
}

async function submitDistribute() {
  const o = ORD.cur;
  const lines = [];
  for (let i = 0; i < o.lines.length; i++) {
    const l = o.lines[i];
    const alloc = {};
    let sum = 0;
    Object.entries(ORD.dist[i] || {}).forEach(e => { if (e[1] > 0) { alloc[e[0]] = e[1]; sum += e[1]; } });
    if (sum > (l.qty_received || 0) + 1e-9) { showMsg(T.ord_err_too_much + ': ' + escapeHtml(l.name), false); return; }
    lines.push({ line_id: l.id, alloc });
  }
  if (!lines.some(x => Object.keys(x.alloc).length)) { keepAllOrder(); return; }
  await postDistribute(lines);
}

async function keepAllOrder() {
  if (!confirm(T.ord_keep_confirm)) return;
  await postDistribute([]);
}

// из «Списка закупки» — сразу в новый заказ поставщику
function purchaseToOrder() {
  const first = (WH.purchaseItems || []).find(p => p.supplier_id);
  closeWhModal('purchaseListModal');
  showTab('suppliers');
  openNewOrder(first ? first.supplier_id : null);
}

// ---- карточка поставщика: долг, оплаты, история цен ----
function fmtSum(n) { return fmtNum(Math.round(n || 0)) + ' ' + T.currency; }

async function openSupplierCard(id, then) {
  SUP.cardId = id;
  SUP.cardYear = null;
  SUP.pay = null;
  SUP.cardThen = then || null;  // 'payment' — сразу открыть форму оплаты
  const m = document.getElementById('supCardModal');
  document.getElementById('supCardFoot').innerHTML = '';
  document.getElementById('supCardBody').innerHTML = `<div class="hint-text" style="padding:24px 0; text-align:center;">${T.stats_loading}</div>`;
  m.classList.add('open');
  await reloadSupplierCard();
  if (SUP.cardThen && SUP.cardId === id && SUP.card && SUP.card.supplier.is_active) { const k = SUP.cardThen; SUP.cardThen = null; openSupPayForm(k); }
}

async function reloadSupplierCard(offset) {
  const id = SUP.cardId, year = SUP.cardYear;
  if (!id) return;
  const d = await ordFetch(`/api/suppliers/${id}/card?year=${year || ''}&offset=${offset || 0}`);
  if (SUP.cardId !== id || SUP.cardYear !== year) return;  // пока ждали ответ, открыли другое
  if (!d.ok) { showMsg(ordErr(d), false); closeWhModal('supCardModal'); return; }
  if (offset && SUP.card) { SUP.card.entries = SUP.card.entries.concat(d.entries); SUP.card.total_entries = d.total_entries; }
  else SUP.card = d;
  renderSupplierCard();
}

function supCardYear(y) {
  SUP.cardYear = y || null;
  reloadSupplierCard();
}

function supCardMore() { reloadSupplierCard(SUP.card.entries.length); }

const SUP_METHODS = ['cash', 'card', 'transfer'];
function supMethodName(m) { return SUP_METHODS.includes(m) ? T['sp_m_' + m] : ''; }

function supEntryLine(e) {
  const pay = e.type === 'payment';
  const off = e.status === 'cancelled';
  const title = e.type === 'order' ? T.ord_title_n.replace('{n}', e.number) : pay ? T.sd_payment : T.sd_charge;
  const click = e.type === 'order' ? `onclick="closeWhModal('supCardModal'); openOrder(${e.id});" style="cursor:pointer;"` : '';
  const act = SUP.card.supplier.is_active;
  const x = e.type !== 'order' && !off && act ? `<button class="ord-x" onclick="cancelSupPayment(${e.id})" aria-label="${T.sp_cancel}"><i class="fa-solid fa-xmark"></i></button>` : '';
  const meta = [ordDate(e.date), e.type === 'order' && e.positions ? e.positions + ' ' + T.ord_positions : '', supMethodName(e.method),
    e.note ? escapeHtml(e.note) : '', e.unpriced ? '⚠️ ' + T.sd_unpriced_short : '',
    off ? `<span style="color:#B91C1C;">${T.sp_cancelled}${e.cancel_reason ? ': ' + escapeHtml(e.cancel_reason) : ''}</span>` : ''].filter(Boolean).join(' · ');
  const usd = e.currency === 'USD' && e.amount_usd != null
    ? `${fmtUsd(e.amount_usd)} · ${T.sp_rate_short} ${supRateStr(e.usd_rate)}`
    : e.usd != null && e.amount ? `≈ ${fmtUsd(e.usd)} · ${T.sp_rate_short} ${supRateStr(e.usd_rate)}` : (e.amount ? T.sp_no_rate : '');
  return `<div class="ord-line ${off ? 'cancelled' : ''}" ${click}>
    <div class="pl-name"><b>${title}</b><span>${meta}</span></div>
    <div><b style="white-space:nowrap; display:block; text-align:right; color:${off ? '#94A3B8' : pay ? '#15803D' : '#B91C1C'};">${pay ? '−' : '+'}${fmtNum(e.amount)}</b><div class="sp-sub">${usd}</div></div>${x}
  </div>`;
}

function renderSupplierCard() {
  const c = SUP.card, s = c.supplier, d = c.debt;
  const act = !!s.is_active;
  const listed = SUP.list.find(x => x.id === s.id) || {};
  const st = supStatus(null, d);
  const contacts = [s.phone ? `<a href="tel:${escapeHtml(s.phone.replace(/[^0-9+]/g, ''))}" style="color:inherit;">${escapeHtml(s.phone)}</a>` : '',
    s.telegram ? `<a href="https://t.me/${escapeHtml(s.telegram)}" target="_blank" rel="noopener" style="color:inherit;">@${escapeHtml(s.telegram)}</a>` : '',
    s.contact ? escapeHtml(s.contact) : '', s.delivery_days ? escapeHtml(s.delivery_days) : '',
    s.tg_connected ? `<span class="sup-bot">✓ ${T.sup_tg_badge}</span>` : ''].filter(Boolean).join(' · ');
  const balCls = d.balance > 0 ? (d.overdue > 0 ? 'r' : 'b') : d.balance < 0 ? 'b' : 'g';
  const balLabel = d.balance > 0 ? T.sp_bal_owe : d.balance < 0 ? T.sd_overpaid : T.sd_no_debt;
  const abs = Math.abs(d.balance);
  const chips = [
    d.balance !== 0 || d.overdue ? `<span class="sp-chip ${st.c}">${st.t}</span>` : '',
    d.overdue > 0 && d.overdue < d.balance ? `<span class="sp-chip r">${T.sp_leg_overdue} ${supShort(d.overdue)}</span>` : '',
    d.next_due && d.overdue > 0 ? `<span class="sp-chip b">${T.sd_next_due.replace('{sum}', supShort(d.next_due.amount)).replace('{date}', ordDate(d.next_due.date))}</span>` : '',
    s.pay_days != null ? `<span class="sp-chip n">${T.sd_terms.replace('{n}', s.pay_days)}</span>` : '',
  ].filter(Boolean).join('');
  const notes = [
    s.pay_days == null && d.balance > 0 ? `<div class="hint-text" style="margin-top:8px;">${T.sd_no_terms}</div>` : '',
    d.unpriced_orders ? `<div class="sd-note warn" style="margin-top:8px;">${T.sd_unpriced}</div>` : '',
    !act ? `<div class="sd-note warn" style="margin-top:8px;">${T.sp_in_archive}</div>` : '',
  ].join('');
  const tt = c.period;
  const totals = `<div class="sp-tot" style="margin-top:12px;">
      <div>${T.sp_tot_bought}<b>${supShort(tt.bought)} ${T.currency}</b>${tt.bought ? '≈ ' + fmtUsd(tt.bought_usd) : ''}</div>
      <div>${T.sp_tot_paid}<b>${supShort(tt.paid)} ${T.currency}</b>${tt.paid ? '≈ ' + fmtUsd(tt.paid_usd) : ''}</div></div>
      ${tt.no_rate ? `<div class="hint-text">${T.sp_tot_no_rate.replace('{n}', tt.no_rate)}</div>` : ''}`;
  const yearChips = c.years.length > 1 ? `<div class="sp-chips"><button class="${!c.year ? 'on' : ''}" onclick="supCardYear(null)">${T.sp_all_years}</button>${c.years.map(y => `<button class="${c.year === y ? 'on' : ''}" onclick="supCardYear('${y}')">${y}</button>`).join('')}</div>` : '';
  const ops = c.entries.length ? c.entries.map(supEntryLine).join('') : `<div class="hint-text">${T.sd_no_ops}</div>`;
  const more = c.total_entries > c.entries.length ? `<button class="wh-tbtn wh-tbtn-wide" style="margin-top:8px;" onclick="supCardMore()">${T.sp_show_more} (${c.total_entries - c.entries.length})</button>` : '';
  const prices = c.prices.length ? c.prices.map(p => {
    const ch = p.change_pct;
    const badge = ch == null ? '' : `<span class="pr-badge ${ch > 0 ? 'up' : 'down'}">${ch > 0 ? '↑ +' : '↓ '}${ch}%</span>`;
    const hist = p.history.map(h => `<div class="pr-h"><span>${ordDate(h.date)} · №${h.number} · ${whQty(h.qty)} ${whUnit(p.unit)}</span><b>${fmtNum(h.price)}${h.usd != null ? ' · ' + fmtUsd(h.usd) : ''}</b></div>`).join('');
    return `<div class="pr-row" onclick="this.classList.toggle('open')">
      <div class="ord-line" style="border:none; padding:6px 0;">
        <div class="pl-name"><b>${escapeHtml(p.name)}</b><span>${ordDate(p.last_date)}${p.prev ? ' · ' + T.pr_was + ' ' + fmtNum(p.prev) : ''}${p.since_first_pct != null ? ' · ' + T.pr_since_first + ' ' + (p.since_first_pct > 0 ? '+' : '') + p.since_first_pct + '%' : ''}</span></div>
        <div style="text-align:right;"><b style="white-space:nowrap;">${fmtNum(p.last)}</b>${p.last_usd != null ? `<div class="sp-sub">${fmtUsd(p.last_usd)}</div>` : ''}<div>${badge}</div></div>
      </div>
      <div class="pr-hist">${hist}</div>
    </div>`;
  }).join('') : `<div class="hint-text">${T.pr_empty}</div>`;
  const yStart = c.year ? c.year + '-01-01' : (c.years.length ? c.years[c.years.length - 1] + '-01-01' : '');
  const yEnd = c.year && c.year !== String(new Date().getFullYear()) ? c.year + '-12-31' : fmtDate(new Date());
  const acts = act ? `<div class="sp-acts">
      <button onclick="closeWhModal('supCardModal'); openNewOrder(${s.id});"><i class="fa-solid fa-cart-plus"></i>${T.sup_order_btn}</button>
      <button onclick="closeWhModal('supCardModal'); openSupProducts(${s.id});"><i class="fa-solid fa-boxes-stacked"></i>${T.sup_assign_short}${listed.product_count ? ' · ' + listed.product_count : ''}</button>
      <button onclick="openSupPayForm('charge')"><i class="fa-solid fa-file-invoice"></i>${T.sp_charge_btn}</button>
      <button onclick="closeWhModal('supCardModal'); openSupplierModal(${s.id});"><i class="fa-solid fa-pen"></i>${T.sup_edit_short}</button>
    </div>` : '';
  document.getElementById('supCardBody').innerHTML = `
    <div class="sp-head"><div class="sp-av ${st.c}">${escapeHtml(supInitials(s.name))}</div>
      <div style="min-width:0;"><div class="t">${escapeHtml(s.name)}</div>${contacts ? `<div class="c">${contacts}</div>` : ''}</div></div>
    ${acts}
    <div class="sp-bal ${balCls}">
      <div class="l">${balLabel}</div>
      <div class="x">${abs ? supShort(abs) + ' ' + T.currency : '0'}</div>
      ${abs ? `<div class="f">${fmtSum(abs)}${USD_RATE ? ' · ≈ ' + fmtUsd(abs / USD_RATE) + ' ' + T.sp_by_rate + ' ' + supRateStr(USD_RATE) : ''}</div>` : ''}
      ${chips ? `<div class="chips">${chips}</div>` : ''}
      ${notes}
    </div>
    <div id="supPayForm" style="display:none;"></div>
    <details class="sp-det" open>
      <summary>${T.sd_ops}<span>${c.year ? T.sp_tot_year.replace('{y}', c.year) : T.sp_tot_all}</span></summary>
      <div class="sp-det-in">${yearChips}${totals}${ops}${more}</div>
    </details>
    <details class="sp-det">
      <summary>${T.pr_title}<span>${c.prices.length || ''}</span></summary>
      <div class="sp-det-in"><div class="hint-text" style="margin-bottom:4px;">${T.pr_hint}</div>${prices}</div>
    </details>
    <details class="sp-det">
      <summary>${T.ss_title}<span>Excel</span></summary>
      <div class="sp-det-in">
        <div class="hint-text" style="margin-bottom:6px;">${T.ss_hint}</div>
        <div class="ord-recv-grid">
          <label>${T.ss_from}<input type="date" id="ss_from" value="${yStart}"></label>
          <label>${T.ss_to}<input type="date" id="ss_to" value="${yEnd}"></label>
        </div>
        <button class="wh-tbtn wh-tbtn-wide" style="margin-top:8px;" onclick="downloadSupStatement()"><i class="fa-solid fa-file-excel"></i> ${T.ss_download}</button>
      </div>
    </details>`;
  renderSupCardFoot();
}

function renderSupCardFoot() {
  const foot = document.getElementById('supCardFoot');
  const c = SUP.card;
  if (!foot || !c) return;
  const s = c.supplier;
  if (!s.is_active) { foot.innerHTML = `<button class="main" onclick="restoreSupplier(${s.id})">${T.sp_restore}</button>`; return; }
  if (SUP.pay) {
    foot.innerHTML = `<button class="sec" onclick="closeSupPayForm()">${T.sp_cancel_form}</button>
      <button class="main" onclick="saveSupPayment('${SUP.pay.kind}')">${SUP.pay.kind === 'payment' ? T.sp_save_payment : T.sp_save_charge}</button>`;
    return;
  }
  foot.innerHTML = `<button class="main" onclick="openSupPayForm('payment')"><i class="fa-solid fa-money-bill-wave"></i> ${T.sp_pay_btn}</button>`;
}

function closeSupPayForm() {
  SUP.pay = null;
  const el = document.getElementById('supPayForm');
  if (el) { el.style.display = 'none'; el.innerHTML = ''; }
  renderSupCardFoot();
}

function downloadSupStatement() {
  const f = document.getElementById('ss_from').value, t = document.getElementById('ss_to').value;
  if (f && t && f > t) { showMsg(T.ss_err_period, false); return; }
  window.location.href = `/api/suppliers/${SUP.cardId}/statement.xlsx?from=${encodeURIComponent(f)}&to=${encodeURIComponent(t)}`;
}

function supNewToken() {
  try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (e) {}
  return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
}

function openSupPayForm(kind) {
  const el = document.getElementById('supPayForm');
  const d = SUP.card.debt;
  // один token на одну открытую форму: повторная отправка (плохая связь,
  // двойное нажатие) не создаст вторую оплату
  SUP.pay = { kind, cur: 'UZS', method: kind === 'payment' ? 'cash' : null, token: supNewToken() };
  el.style.display = '';
  el.className = 'sp-form';
  el.innerHTML = `
    <div class="sp-form-t">${kind === 'payment' ? T.sp_pay_title : T.sp_charge_title}</div>
    <div class="sp-form-now">${T.sp_debt_now}: <b>${d.balance < 0 ? T.sp_st_overpaid + ' ' : ''}${fmtSum(Math.abs(d.balance))}</b>${usdTail(Math.abs(d.balance))}</div>
    <div class="sp-seg">
      <button type="button" id="sp_cur_UZS" class="on" onclick="spSetCur('UZS')">${T.sp_cur_uzs}</button>
      <button type="button" id="sp_cur_USD" onclick="spSetCur('USD')">${T.sp_cur_usd}</button>
    </div>
    <div class="ord-recv-grid">
      <label><span id="sp_amount_lbl">${kind === 'payment' ? T.sd_pay_amount : T.sd_charge_amount}</span><input type="number" inputmode="decimal" min="0" step="any" id="sp_amount" oninput="spRecalc()" value="${kind === 'payment' && d.balance > 0 ? Math.round(d.balance) : ''}"></label>
      <label>${T.sp_rate_label}<input type="number" inputmode="decimal" min="0" step="any" id="sp_rate" oninput="spRecalc()" value="${USD_RATE || ''}" placeholder="12700"></label>
    </div>
    <div class="sp-eq" id="sp_eq"></div>
    ${kind === 'payment' ? `<div class="sp-chips" id="sp_methods">${SUP_METHODS.map(m => `<button type="button" class="${m === 'cash' ? 'on' : ''}" onclick="spSetMethod('${m}')" data-m="${m}">${T['sp_m_' + m]}</button>`).join('')}</div>` : ''}
    <div class="ord-recv-grid">
      <label>${T.sd_date}<input type="date" id="sp_date" value="${fmtDate(new Date())}" max="${fmtDate(new Date())}"></label>
      <label>${T.sd_note}<input id="sp_note" maxlength="200" placeholder="${kind === 'payment' ? T.sp_note_ph_pay : T.sd_note_ph_charge}"></label>
    </div>
    <div class="sp-after" id="sp_after"></div>`;
  spRecalc();
  renderSupCardFoot();
  el.scrollIntoView({ block: 'start', behavior: 'smooth' });
  setTimeout(() => { const a = document.getElementById('sp_amount'); if (a) a.focus({ preventScroll: true }); }, 250);
}

function spAmounts() {
  const v = parseFloat(document.getElementById('sp_amount').value);
  const rate = parseFloat(document.getElementById('sp_rate').value);
  const r = rate > 0 ? rate : null;
  if (!(v > 0)) return { sum: 0, usd: 0, rate: r };
  if (SUP.pay.cur === 'USD') return { sum: r ? Math.round(Math.round(v * 100) * r / 100) : 0, usd: Math.round(v * 100) / 100, rate: r };
  return { sum: Math.round(v), usd: r ? v / r : null, rate: r };
}

function spRecalc() {
  if (!SUP.pay) return;
  const a = spAmounts();
  const eq = document.getElementById('sp_eq');
  if (SUP.pay.cur === 'USD') eq.textContent = a.rate ? (a.usd ? `= ${fmtSum(a.sum)}` : T.sp_eq_hint_usd) : T.sp_err_rate;
  else eq.textContent = a.sum ? (a.rate ? `≈ ${fmtUsd(a.usd)}` : T.sp_no_rate_set) : T.sp_eq_hint_uzs;
  const after = document.getElementById('sp_after');
  const bal = SUP.card.debt.balance + (SUP.pay.kind === 'payment' ? -a.sum : a.sum);
  after.innerHTML = a.sum ? `${T.sp_debt_after}: <b style="color:${bal > 0 ? '#B91C1C' : '#15803D'};">${bal < 0 ? T.sp_st_overpaid + ' ' : ''}${fmtSum(Math.abs(bal))}</b>${usdTail(Math.abs(bal))}` : '';
}

function spSetCur(c) {
  if (!SUP.pay || SUP.pay.cur === c) return;
  const a = spAmounts();
  SUP.pay.cur = c;
  ['UZS', 'USD'].forEach(k => document.getElementById('sp_cur_' + k).classList.toggle('on', k === c));
  const inp = document.getElementById('sp_amount');
  // переводим уже введённую сумму в новую валюту, чтобы не набирать заново
  if (a.sum && a.rate) inp.value = c === 'USD' ? Math.round(a.sum / a.rate * 100) / 100 : a.sum;
  document.getElementById('sp_amount_lbl').textContent = c === 'USD'
    ? (SUP.pay.kind === 'payment' ? T.sp_pay_amount_usd : T.sp_charge_amount_usd)
    : (SUP.pay.kind === 'payment' ? T.sd_pay_amount : T.sd_charge_amount);
  spRecalc();
}

function spSetMethod(m) {
  SUP.pay.method = m;
  document.querySelectorAll('#sp_methods button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
}

async function saveSupPayment(kind) {
  const a = spAmounts();
  if (SUP.pay.cur === 'USD' && !a.rate) { showMsg(T.sp_err_rate, false); return; }
  if (!(a.sum > 0)) { showMsg(T.sd_err_amount, false); return; }
  const body = { kind, currency: SUP.pay.cur, rate: a.rate, method: SUP.pay.method, token: SUP.pay.token,
    date: document.getElementById('sp_date').value, note: document.getElementById('sp_note').value };
  if (SUP.pay.cur === 'USD') body.amount_usd = a.usd; else body.amount = a.sum;
  const d = await ordFetch(`/api/suppliers/${SUP.cardId}/payments`, 'POST', body);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  SUP.pay = null;
  showMsg(kind === 'payment' ? T.sd_payment_saved : T.sd_charge_saved, true);
  loadSuppliers();
  reloadSupplierCard();
}

async function cancelSupPayment(pid) {
  const reason = prompt(T.sp_cancel_prompt, '');
  if (reason === null) return;
  const d = await ordFetch(`/api/suppliers/${SUP.cardId}/payments/${pid}/cancel`, 'POST', { reason });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.sp_cancel_done, true);
  loadSuppliers();
  reloadSupplierCard();
}

// ---- новый товар прямо из заказа ----
function openOrderNewProduct() {
  renderWarehouseCategoryOptions();
  const src = document.getElementById('wh_new_category');
  const sel = document.getElementById('onp_category');
  sel.innerHTML = src ? src.innerHTML : '';
  ['onp_name', 'onp_sell'].forEach(id => { document.getElementById(id).value = ''; });
  onOnpCategoryChanged();
  const s = SUP.list.find(x => x.id === ORD.cur.supplier_id);
  document.getElementById('onp_hint').textContent = s ? T.onp_hint_sup.replace('{name}', s.name) : T.onp_hint;
  document.getElementById('orderNewProductModal').classList.add('open');
  document.getElementById('onp_name').focus();
}

function onOnpCategoryChanged() {
  document.getElementById('onp_unit_row').style.display = document.getElementById('onp_category').value === 'other' ? '' : 'none';
}

async function saveOrderNewProduct() {
  const category = document.getElementById('onp_category').value;
  const name = document.getElementById('onp_name').value.replace(/\\s+/g, ' ').trim();
  if (!category || !name) { showMsg(T.wh_fill_required, false); return; }
  // такой товар уже есть на складе — просто добавляем его в заказ
  const same = WHCTX.own.products.find(p => p.category === category && p.name.replace(/\\s+/g, ' ').trim().toUpperCase() === name.toUpperCase());
  let product = same;
  if (!same) {
    const d = await ordFetch('/api/products', 'POST', { category, name, unit: document.getElementById('onp_unit').value,
      sell_price: document.getElementById('onp_sell').value || null, initial_stock: 0, supplier_id: ORD.cur.supplier_id || null });
    if (!d.ok) { showMsg(ordErr(d), false); return; }
    product = d.product;
    WHCTX.own.products.push({ ...product, stock_qty: 0, reorder_qty: 0, status: 'out' });
    loadSuppliers();
  }
  closeWhModal('orderNewProductModal');
  if (!ORD.cur.lines.some(l => l.product_id === product.id)) {
    ORD.cur.lines.push({ product_id: product.id, name: product.name, unit: product.unit, stock_qty: product.stock_qty || 0, qty: 0, alloc: {} });
  }
  renderOrderEdit();
  const inputs = document.querySelectorAll('#ordBody .ord-line input');
  if (inputs.length) inputs[inputs.length - 1].focus();
  showMsg(same ? T.onp_exists : T.onp_created, true);
}

// ---- склад выбранного филиала (главный) ----
// ---- накладная: отправка многих товаров сразу ----
const SHIP = { rows: [], qty: {}, cat: 'all' };

async function openShipModal(toShopId) {
  if (!WH.net) await loadNetworkStock();
  if (!WH.net) return;
  const shops = WH.net.shops;
  const opt = s => `<option value="${s.id}">${escapeHtml(s.name)}${s.is_head ? ' (' + T.branch_head_label + ')' : ''}</option>`;
  const head = shops.find(s => s.is_head) || shops[0];
  document.getElementById('shp_from').innerHTML = shops.map(opt).join('');
  document.getElementById('shp_to').innerHTML = shops.map(opt).join('');
  document.getElementById('shp_from').value = head.id;
  const firstBranch = shops.find(s => !s.is_head);
  document.getElementById('shp_to').value = toShopId || (firstBranch ? firstBranch.id : head.id);
  document.getElementById('shp_search').value = '';
  document.getElementById('shp_only_selected').checked = false;
  SHIP.cat = 'all';
  document.getElementById('shipModal').classList.add('open');
  loadShipPlan();
}

async function loadShipPlan() {
  const from = document.getElementById('shp_from').value;
  const to = document.getElementById('shp_to').value;
  SHIP.qty = {};
  const list = document.getElementById('shp_list');
  if (from === to) { SHIP.rows = []; list.innerHTML = `<div class="hint-text" style="padding:12px;">${T.whn_err_same}</div>`; updateShipSummary(); return; }
  list.innerHTML = `<div class="hint-text" style="padding:12px;">${T.stats_loading}</div>`;
  let data;
  const seq = (SHIP.seq = (SHIP.seq || 0) + 1);
  try { data = await (await fetch(`/api/warehouse/ship_plan?from=${from}&to=${to}`)).json(); } catch (e) { return; }
  if (seq !== SHIP.seq) return;
  if (!data.ok) { list.innerHTML = `<div class="hint-text" style="padding:12px;">${escapeHtml(data.error || '')}</div>`; return; }
  SHIP.rows = data.rows;
  renderShipCats();
  renderShipRows();
}

function renderShipCats() {
  const counts = {};
  SHIP.rows.forEach(r => { counts[r.category] = (counts[r.category] || 0) + 1; });
  const order = FLUID_KEYS.concat(FILTER_KEYS, ['other']).filter(k => counts[k]);
  document.getElementById('shp_cats').innerHTML =
    [`<div class="brand-chip ${SHIP.cat === 'all' ? 'active' : ''}" onclick="SHIP.cat='all'; renderShipCats(); renderShipRows();">${T.whs_all}<span class="bc-sub">${SHIP.rows.length}</span></div>`]
      .concat(order.map(k => `<div class="brand-chip ${SHIP.cat === k ? 'active' : ''}" onclick="SHIP.cat='${k}'; renderShipCats(); renderShipRows();">${escapeHtml(k === 'other' ? T.wh_category_other : (T[k] || k))}<span class="bc-sub">${counts[k]}</span></div>`))
      .join('');
}

function renderShipRows() {
  const q = document.getElementById('shp_search').value.trim().toLowerCase();
  const onlySel = document.getElementById('shp_only_selected').checked;
  const toName = (document.getElementById('shp_to').selectedOptions[0] || {}).textContent || '';
  const rows = SHIP.rows.filter(r =>
    (SHIP.cat === 'all' || r.category === SHIP.cat) &&
    (!q || r.name.toLowerCase().includes(q)) &&
    (!onlySel || SHIP.qty[r.id] > 0));
  const list = document.getElementById('shp_list');
  if (!rows.length) { list.innerHTML = `<div class="hint-text" style="padding:12px;">${T.whs_nothing_found}</div>`; updateShipSummary(); return; }
  // рисуем не больше 300 строк за раз — поиск и фильтр помогают сузить
  list.innerHTML = rows.slice(0, 300).map(r => {
    const v = SHIP.qty[r.id] || '';
    const u = whUnit(r.unit);
    const there = r.to_qty === null ? T.shp_not_there : `${whQty(r.to_qty)} ${u}${r.to_per_day ? ` · ~${whQty(r.to_per_day)}${T.whs_per_day}` : ''}`;
    return `
      <div class="sh-row ${v > 0 ? 'sel' : ''}" id="shr_${r.id}">
        <div class="sh-name">
          <b>${escapeHtml(r.name)}</b>
          <span>${T.shp_have} ${whQty(r.stock)} ${u} · ${escapeHtml(toName.split(' (')[0])}: ${there}${r.suggested > 0 ? ` · <span class="need">${T.shp_need} ${whQty(r.suggested)}</span>` : ''}</span>
        </div>
        <input type="number" min="0" step="0.5" value="${v}" placeholder="0" oninput="onShipQty(${r.id}, this)" class="${v > r.stock ? 'over' : ''}">
        <span class="sh-unit">${u}</span>
      </div>`;
  }).join('') + (rows.length > 300 ? `<div class="hint-text" style="padding:10px;">${T.shp_more_rows.replace('{n}', rows.length - 300)}</div>` : '');
  updateShipSummary();
}

function onShipQty(id, input) {
  const v = parseFloat(input.value);
  const row = SHIP.rows.find(r => r.id === id);
  if (v > 0) SHIP.qty[id] = v; else delete SHIP.qty[id];
  input.classList.toggle('over', v > (row ? row.stock : 0));
  const el = document.getElementById('shr_' + id);
  if (el) el.classList.toggle('sel', v > 0);
  updateShipSummary();
}

function updateShipSummary() {
  const ids = Object.keys(SHIP.qty).filter(id => SHIP.qty[id] > 0);
  const over = SHIP.rows.filter(r => SHIP.qty[r.id] > r.stock).length;
  document.getElementById('shp_summary').innerHTML = `${T.shp_selected} ${ids.length}` + (over ? ` · <span style="color:#B91C1C;">${T.shp_over} ${over}</span>` : '');
}

function shipAutofill() {
  let n = 0;
  SHIP.rows.forEach(r => { if (r.suggested > 0) { SHIP.qty[r.id] = r.suggested; n++; } });
  renderShipRows();
  showMsg(n ? `${T.shp_autofilled} ${n}` : T.shp_nothing_needed, !!n);
}

function shipClear() {
  SHIP.qty = {};
  renderShipRows();
}

async function submitShip() {
  const from = document.getElementById('shp_from').value;
  const to = document.getElementById('shp_to').value;
  const lines = Object.keys(SHIP.qty).filter(id => SHIP.qty[id] > 0).map(id => ({ product_id: parseInt(id), quantity: SHIP.qty[id] }));
  if (!lines.length) { showMsg(T.shp_pick, false); return; }
  if (SHIP.rows.some(r => SHIP.qty[r.id] > r.stock)) { showMsg(T.shp_fix_over, false); return; }
  const toName = (document.getElementById('shp_to').selectedOptions[0] || {}).textContent || '';
  if (!confirm(`${T.shp_confirm} ${lines.length} → ${toName}?`)) return;
  const res = await fetch('/api/warehouse/bulk_transfer', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ from_shop_id: from, to_shop_id: to, lines })
  });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('shipModal');
    showMsg(`${T.shp_done} ${data.lines} (№ ${data.batch})`, true);
    WH.net = null;
    loadNetworkStock();
    loadWarehouse();
    if (WH.branchId) selectWhBranch(WH.branchId);
  } else if (data.error === 'problems') {
    const names = data.problems.map(p => `${p.name || '#' + p.product_id}${p.available !== undefined ? ` (${T.whn_available} ${whQty(p.available)})` : ''}`).join(', ');
    showMsg(`${T.whn_err_not_enough} ${names}`, false);
  } else {
    showMsg(T['whn_err_' + data.error] || data.error, false);
  }
}

// ---- скопировать каталог в филиал ----
function openCatalogModal(branchId) {
  const sel = document.getElementById('cat_branch');
  sel.innerHTML = WH.branches.map(b => `<option value="${b.id}">${escapeHtml(b.shop_name || b.username)}</option>`).join('');
  if (branchId) sel.value = branchId;
  const counts = {};
  WHCTX.own.products.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; });
  const order = FLUID_KEYS.concat(FILTER_KEYS, ['other']).filter(k => counts[k]);
  document.getElementById('cat_types').innerHTML = order.map(k => `
    <label style="display:flex; align-items:center; gap:8px; font-size:14px; text-transform:none; letter-spacing:0; color:var(--text); margin:0;">
      <input type="checkbox" class="cat-type" value="${k}" checked style="width:auto; margin:0;">
      ${escapeHtml(k === 'other' ? T.wh_category_other : (T[k] || k))} <span class="hint-text" style="margin:0;">(${counts[k]})</span>
    </label>`).join('') || `<div class="hint-text">${T.wh_no_products}</div>`;
  document.getElementById('catalogModal').classList.add('open');
}

async function submitCatalog() {
  const branchId = document.getElementById('cat_branch').value;
  const cats = Array.from(document.querySelectorAll('.cat-type:checked')).map(c => c.value);
  if (!cats.length) { showMsg(T.cat_pick, false); return; }
  const res = await fetch('/api/warehouse/copy_catalog', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ branch_id: branchId, categories: cats })
  });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('catalogModal');
    showMsg(`${T.cat_done} ${data.created}${data.skipped ? ` · ${T.cat_skipped} ${data.skipped}` : ''}`, true);
    WH.net = null;
    loadNetworkStock();
    loadWarehouse();
    if (WH.branchId) selectWhBranch(WH.branchId);
  } else {
    showMsg(T['whn_err_' + data.error] || data.error, false);
  }
}

// ---- загрузка склада из Excel ----
let IMPORT_ROWS = [];

function openImportModal() {
  document.getElementById('imp_file').value = '';
  document.getElementById('imp_preview').innerHTML = '';
  document.getElementById('imp_apply_btn').style.display = 'none';
  IMPORT_ROWS = [];
  document.getElementById('importModal').classList.add('open');
}

async function previewImport() {
  const f = document.getElementById('imp_file').files[0];
  const box = document.getElementById('imp_preview');
  const btn = document.getElementById('imp_apply_btn');
  btn.style.display = 'none';
  if (!f) return;
  box.innerHTML = `<div class="hint-text">${T.stats_loading}</div>`;
  const fd = new FormData();
  fd.append('file', f);
  let data;
  try { data = await (await fetch('/api/products/import_preview', { method: 'POST', body: fd })).json(); }
  catch (e) { box.innerHTML = `<div class="hint-text" style="color:#B91C1C;">${T.imp_err_bad_file}</div>`; return; }
  if (!data.ok) { box.innerHTML = `<div class="hint-text" style="color:#B91C1C;">${T['imp_err_' + data.error] || data.error}</div>`; return; }
  IMPORT_ROWS = data.rows;
  const errs = data.rows.filter(r => r.errors.length);
  const ok = data.rows.filter(r => !r.errors.length);
  const upd = ok.filter(r => r.exists).length;
  const errText = e => e.map(x => T['imp_bad_' + x] || x).join(', ');
  box.innerHTML = `
    <div class="imp-sum">
      <div><b style="color:#15803D;">${ok.length - upd}</b>${T.imp_new}</div>
      <div><b style="color:#1D4ED8;">${upd}</b>${T.imp_update}</div>
      <div><b style="color:#B91C1C;">${errs.length}</b>${T.imp_errors}</div>
    </div>
    ${errs.length ? `<div class="hint-text" style="color:#B91C1C; margin-bottom:6px;">${T.imp_errors_hint}</div>` : ''}
    <div style="max-height:36vh; overflow:auto; border:1px solid var(--border); border-radius:12px;">
      <table class="imp-table">
        <tbody>${data.rows.slice(0, 200).map(r => `
          <tr>
            <td style="color:#94A3B8;">${r.row}</td>
            <td><b>${escapeHtml(r.name || '—')}</b><br><span class="hint-text" style="margin:0;">${escapeHtml(r.category ? (r.category === 'other' ? T.wh_category_other : T[r.category]) : r.category_raw || '—')}</span></td>
            <td style="white-space:nowrap;">${r.quantity ? whQty(r.quantity) + ' ' + whUnit(r.unit) : '—'}</td>
            <td style="white-space:nowrap;">${r.sell_price != null ? fmtNum(r.sell_price) : '—'}${!IS_BRANCH && r.purchase_price != null ? `<br><span class="hint-text" style="margin:0;">${T.whs_buy} ${fmtNum(r.purchase_price)}</span>` : ''}</td>
            <td>${r.errors.length ? `<span class="imp-tag err">${errText(r.errors)}</span>` : (r.exists ? `<span class="imp-tag upd">${T.imp_tag_upd}</span>` : `<span class="imp-tag new">${T.imp_tag_new}</span>`)}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    ${data.rows.length > 200 ? `<div class="hint-text">${T.shp_more_rows.replace('{n}', data.rows.length - 200)}</div>` : ''}`;
  if (ok.length) {
    btn.style.display = '';
    btn.innerHTML = `<i class="fa-solid fa-file-import"></i> ${T.imp_apply} ${ok.length}`;
  }
}

async function applyImport() {
  const ok = IMPORT_ROWS.filter(r => !r.errors.length);
  if (!ok.length) return;
  const payload = ok.map(r => ({ category: r.category, name: r.name, unit: r.unit, sell_price: r.sell_price, purchase_price: r.purchase_price, quantity: r.quantity }));
  const btn = document.getElementById('imp_apply_btn');
  btn.disabled = true;
  const res = await fetch('/api/products/import_apply', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ rows: payload }) });
  const data = await res.json();
  btn.disabled = false;
  if (data.ok) {
    closeWhModal('importModal');
    showMsg(`${T.imp_done}: ${T.imp_new} ${data.created}, ${T.imp_restocked} ${data.restocked}${data.updated ? `, ${T.imp_prices} ${data.updated}` : ''}`, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + (data.error || ''), false);
  }
}

// ---- изменение товара ----
let editingProduct = null;  // { key, shopId, p }

function openEditProductModal(key, productId) {
  const ctx = WHCTX[key];
  const p = ctx.products.find(x => x.id === productId);
  if (!p) return;
  editingProduct = { key, shopId: ctx.shopId, p };
  const canBuy = key === 'br' || !IS_BRANCH;
  document.getElementById('ep_category').textContent = (p.category === 'other' ? T.wh_category_other : (T[p.category] || p.category)) + ' · ' + whUnit(p.unit);
  document.getElementById('ep_name').value = p.name;
  document.getElementById('ep_sell').value = p.sell_price ?? '';
  document.getElementById('ep_buy').value = canBuy ? (p.purchase_price ?? '') : '';
  document.getElementById('ep_buy_usd').value = '';
  document.getElementById('ep_sell_usd').value = '';
  document.getElementById('ep_sell_usd_wrap').style.display = USD_RATE ? '' : 'none';
  document.getElementById('ep_buy_wrap').style.display = canBuy ? '' : 'none';
  document.getElementById('ep_usd_wrap').style.display = canBuy && USD_RATE ? '' : 'none';
  document.getElementById('ep_price_hint').style.display = canBuy ? '' : 'none';
  document.getElementById('ep_unit').textContent = whUnit(p.unit);
  document.getElementById('ep_stock').value = Math.round((p.stock_qty || 0) * 100) / 100;
  document.getElementById('ep_reason').value = '';
  document.getElementById('ep_reason_wrap').style.display = 'none';
  document.getElementById('editProductModal').classList.add('open');
}

function onEditStockChanged() {
  if (!editingProduct) return;
  const v = parseFloat(document.getElementById('ep_stock').value);
  const changed = !isNaN(v) && Math.abs(v - (editingProduct.p.stock_qty || 0)) > 1e-9;
  document.getElementById('ep_reason_wrap').style.display = changed ? '' : 'none';
}

async function submitEditProduct() {
  if (!editingProduct) return;
  const { key, shopId, p } = editingProduct;
  const canBuy = key === 'br' || !IS_BRANCH;
  const name = document.getElementById('ep_name').value.trim();
  const sell = document.getElementById('ep_sell').value.trim();
  const buy = document.getElementById('ep_buy').value.trim();
  const stock = document.getElementById('ep_stock').value.trim();
  if (!name) { showMsg(T.whe_err_name, false); return; }
  if (stock === '' || parseFloat(stock) < 0) { showMsg(T.whe_err_stock, false); return; }
  // отправляем только то, что действительно изменили
  const payload = {};
  if (name !== p.name) payload.name = name;
  if (sell !== String(p.sell_price ?? '')) payload.sell_price = sell;
  if (canBuy && buy !== String(p.purchase_price ?? '')) payload.purchase_price = buy;
  if (Math.abs(parseFloat(stock) - (p.stock_qty || 0)) > 1e-9) {
    payload.stock_qty = stock;
    payload.stock_reason = document.getElementById('ep_reason').value.trim();
  }
  if (!Object.keys(payload).length) { closeWhModal('editProductModal'); return; }
  if (payload.name && !confirm(T.whe_rename_confirm)) return;
  const url = shopId ? `/api/branches/${shopId}/products/${p.id}` : `/api/products/${p.id}`;
  const res = await fetch(url, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('editProductModal');
    showMsg(T.whe_saved, true);
    if (shopId) { selectWhBranch(shopId); WH.net = null; }
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function selectWhBranch(branchId) {
  WH.branchId = branchId;
  const seq = (WH.brSeq = (WH.brSeq || 0) + 1);
  document.querySelectorAll('#branchWarehouseSummary .whn-shop').forEach((el, i) => {
    el.classList.toggle('active', WH.branches[i] && WH.branches[i].id === branchId);
  });
  document.querySelectorAll('#whbChips .brand-chip').forEach(el => {
    el.classList.toggle('active', el.dataset.id === String(branchId));
  });
  const wrap = document.getElementById('whbDetail');
  wrap.style.display = 'block';
  let data;
  try { data = await (await fetch(`/api/branches/${branchId}/warehouse`)).json(); } catch (e) { return; }
  if (seq !== WH.brSeq) return;  // пока грузилось, выбрали другой филиал
  if (!data.ok) { showMsg(T.msg_error + ' ' + data.error, false); return; }
  const ctx = WHCTX.br;
  ctx.shopId = branchId;
  ctx.products = data.products;
  ctx.summary = data.summary;
  ctx.name = data.name;
  document.getElementById('whbTitle').textContent = data.name;
  renderWarehouseSummary('br');
  renderWhCategoryChips('br');
  renderProductCards('br');
  renderMovements(document.getElementById('whbHistory'), data.movements, true);
}

function renderWhBranchChips() {
  const el = document.getElementById('whbChips');
  if (!el) return;
  el.innerHTML = WH.branches.map(b => `<div class="brand-chip ${WH.branchId === b.id ? 'active' : ''}" data-id="${b.id}" onclick="selectWhBranch(${b.id})">${escapeHtml(b.shop_name || b.username)}</div>`).join('');
}

async function editBranchPrice(productId, name, current) {
  const val = prompt(`${T.whb_set_price}: ${name}`, current ?? '');
  if (val === null) return;
  const res = await fetch(`/api/branches/${WHCTX.br.shopId}/products/${productId}/purchase_price`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ purchase_price: val.trim() })
  });
  const data = await res.json();
  if (data.ok) { showMsg(T.whb_price_saved, true); selectWhBranch(WHCTX.br.shopId); loadWarehouse(); }
  else showMsg(T.msg_error + ' ' + data.error, false);
}

// ---- склады сети (главный) ----
async function loadNetworkStock() {
  const box = document.getElementById('whNetMatrix');
  if (!box) return;
  let data;
  try { data = await (await fetch('/api/warehouse/network')).json(); } catch (e) { return; }
  if (!data.ok) return;
  WH.net = data;
  if (!data.rows.length) { box.innerHTML = `<div class="hint-text">${T.wh_no_products}</div>`; return; }
  const shops = data.shops;
  box.innerHTML = `
    <div class="table-wrap"><table class="wh-mx">
      <thead><tr><th>${T.whn_product}</th>${shops.map(s => `<th>${escapeHtml(s.name)}${s.is_head ? `<br><span style="font-weight:500; color:#94A3B8;">${T.branch_head_label}</span>` : ''}</th>`).join('')}</tr></thead>
      <tbody>${data.rows.map((r, i) => `
        <tr>
          <td>${escapeHtml(r.name)}<span>${escapeHtml(r.category === 'other' ? T.wh_category_other : (T[r.category] || r.category))}</span></td>
          ${shops.map(s => {
            const c = r.cells[String(s.id)];
            if (!c) return `<td class="cell" onclick="openTransferModal({row: ${i}, to: ${s.id}})"><span class="q-none">—</span></td>`;
            const cls = c.status === 'out' ? 'q-out' : c.status === 'low' ? 'q-low' : '';
            return `<td class="cell" onclick="openTransferModal({row: ${i}, to: ${s.id}})"><span class="${cls}">${whQty(c.qty)}</span></td>`;
          }).join('')}
        </tr>`).join('')}
      </tbody>
    </table></div>
    <div class="rv-legend">
      <span><i style="background:#FEE2E2; border:1px solid #FCA5A5;"></i>${T.whs_out}</span>
      <span><i style="background:#FEF3C7; border:1px solid #FCD34D;"></i>${T.whn_legend_low}</span>
      <span>${T.whn_legend_click}</span>
    </div>`;
}

async function openTransferModal(opts) {
  if (!WH.net) await loadNetworkStock();
  if (!WH.net) return;
  const shops = WH.net.shops;
  const opt = s => `<option value="${s.id}">${escapeHtml(s.name)}${s.is_head ? ' (' + T.branch_head_label + ')' : ''}</option>`;
  const fromSel = document.getElementById('tr_from');
  const toSel = document.getElementById('tr_to');
  fromSel.innerHTML = shops.map(opt).join('');
  toSel.innerHTML = shops.map(opt).join('');
  const head = shops.find(s => s.is_head) || shops[0];
  let fromId = head.id, productKey = null, toId = null;

  if (opts.productId) {
    fromId = opts.fromShop || head.id;
    const row = WH.net.rows.find(r => r.cells[String(fromId)] && r.cells[String(fromId)].product_id === opts.productId);
    if (row) productKey = WH.net.rows.indexOf(row);
  }
  if (opts.row !== undefined) {
    productKey = opts.row;
    toId = opts.to;
    // отправляем с той точки, где этого товара больше всего
    const cells = WH.net.rows[opts.row].cells;
    const best = shops.filter(s => s.id !== opts.to && cells[String(s.id)] && cells[String(s.id)].qty > 0)
      .sort((a, b) => cells[String(b.id)].qty - cells[String(a.id)].qty)[0];
    if (best) fromId = best.id;
  }
  fromSel.value = fromId;
  const firstOther = shops.find(s => s.id !== fromId);
  toSel.value = toId && toId !== fromId ? toId : (firstOther ? firstOther.id : fromId);
  onTransferFromChanged(productKey);
  document.getElementById('tr_qty').value = '';
  document.getElementById('transferModal').classList.add('open');
}

function onTransferFromChanged(preselectRow) {
  const fromId = document.getElementById('tr_from').value;
  const sel = document.getElementById('tr_product');
  const rows = WH.net.rows.map((r, i) => ({ r, i })).filter(x => x.r.cells[fromId] && x.r.cells[fromId].qty > 0);
  sel.innerHTML = rows.length
    ? rows.map(x => `<option value="${x.i}">${escapeHtml(x.r.name)} — ${whQty(x.r.cells[fromId].qty)} ${whUnit(x.r.unit)}</option>`).join('')
    : `<option value="">${T.whn_nothing_to_send}</option>`;
  if (preselectRow !== undefined && preselectRow !== null && rows.some(x => x.i === preselectRow)) sel.value = preselectRow;
  onTransferProductChanged();
}

function onTransferProductChanged() {
  const fromId = document.getElementById('tr_from').value;
  const idx = document.getElementById('tr_product').value;
  const el = document.getElementById('tr_available');
  if (idx === '') { el.textContent = ''; return; }
  const r = WH.net.rows[idx];
  el.textContent = `${T.whn_available} ${whQty(r.cells[fromId].qty)} ${whUnit(r.unit)}`;
}

async function submitTransfer() {
  const fromId = document.getElementById('tr_from').value;
  const toId = document.getElementById('tr_to').value;
  const idx = document.getElementById('tr_product').value;
  const qty = parseFloat(document.getElementById('tr_qty').value);
  if (idx === '' || !(qty > 0)) { showMsg(T.whn_err_fill, false); return; }
  if (fromId === toId) { showMsg(T.whn_err_same, false); return; }
  const r = WH.net.rows[idx];
  const res = await fetch('/api/warehouse/transfer', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ from_shop_id: fromId, to_shop_id: toId, product_id: r.cells[fromId].product_id, quantity: qty })
  });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('transferModal');
    showMsg(T.whn_done, true);
    WH.net = null;
    loadNetworkStock();
    loadWarehouse();
    if (WH.branchId) selectWhBranch(WH.branchId);
  } else {
    const msg = data.error === 'not_enough' ? `${T.whn_err_not_enough} ${whQty(data.available)}` : (T['whn_err_' + data.error] || data.error);
    showMsg(msg, false);
  }
}

function showWhSubTab(t) {
  ['own', 'branches', 'network'].forEach(k => {
    const view = document.getElementById({ own: 'whOwnView', branches: 'whBranchesView', network: 'whNetworkView' }[k]);
    if (view) view.style.display = t === k ? 'block' : 'none';
    const tab = document.getElementById('subwh-' + k);
    if (tab) tab.classList.toggle('active', t === k);
  });
  if (t === 'network') { WH.net = null; loadNetworkStock(); }
  if (t === 'branches') {
    if (!WH.branchId && WH.branches.length) selectWhBranch(WH.branches[0].id);
    else if (WH.branchId) selectWhBranch(WH.branchId);
  }
}

function onUsdFieldEdited(usdFieldId, sumFieldId) {
  const usdVal = parseFloat(document.getElementById(usdFieldId).value);
  const sumField = document.getElementById(sumFieldId);
  if (!USD_RATE || isNaN(usdVal)) return;
  sumField.value = Math.round(usdVal * USD_RATE);
}

function onSumFieldEdited(sumFieldId, usdFieldId) {
  // если сумма меняется вручную (не через пересчёт из $), поле $ больше не
  // соответствует новой сумме однозначно - просто очищаем его, чтобы не
  // вводить в заблуждение несоответствующим числом
  const usdField = document.getElementById(usdFieldId);
  if (usdField) usdField.value = '';
}

async function saveUsdRate(inputId, savedId) {
  inputId = inputId || 'usd_rate_input';
  savedId = savedId || 'usdRateSaved';
  const rateInput = document.getElementById(inputId);
  const rate = rateInput.value;
  const res = await fetch('/api/usd_rate', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({rate})
  });
  const data = await res.json();
  if (data.ok) {
    USD_RATE = data.effective ?? data.rate;
    renderUsdInheritHint(data.rate);
    // синхронизируем оба виджета курса, если на странице есть второй (Расходы)
    ['usd_rate_input', 'usd_rate_input_exp', 'usd_rate_input_sup'].forEach(id => {
      const el = document.getElementById(id);
      if (el && id !== inputId) el.value = data.rate ?? '';
    });
    if (SUP.loaded) { SUP.rate = USD_RATE; renderSuppliers(); }
    const saved = document.getElementById(savedId);
    saved.style.display = 'block';
    setTimeout(() => { saved.style.display = 'none'; }, 1500);
  } else {
    showMsg(T.usd_rate_error || data.error, false);
  }
}

function renderUsdInheritHint(ownRate) {
  // филиал без своего курса пересчитывает $ по курсу главной точки — пишем это явно
  document.querySelectorAll('.usd-inherit-hint').forEach(el => {
    if (IS_BRANCH && !ownRate && HEAD_USD_RATE) {
      el.innerHTML = `${T.usd_head_used} <b>${Number(HEAD_USD_RATE).toLocaleString('ru-RU')}</b>. ${T.usd_head_own}`;
      el.style.display = '';
    } else if (IS_BRANCH && !ownRate) {
      el.textContent = T.usd_none;
      el.style.display = '';
    } else {
      el.style.display = 'none';
    }
  });
}
renderUsdInheritHint({{ usd_rate_own|tojson }});

async function createProduct() {
  const catEl = document.getElementById('wh_new_category');
  const nameEl = document.getElementById('wh_new_name');
  if (!catEl || !nameEl) return;  // вкладка "Склад" не отрисована (выключена для этой точки)
  const category = catEl.value;
  const name = nameEl.value.trim();
  if (!category || !name) { showMsg(T.wh_fill_required, false); return; }
  const payload = {
    category, name,
    unit: document.getElementById('wh_new_unit').value,
    sell_price: document.getElementById('wh_new_sell_price').value || null,
    purchase_price: document.getElementById('wh_new_purchase_price').value || null,
    initial_stock: document.getElementById('wh_new_stock').value || 0,
  };
  const res = await fetch('/api/products', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.wh_product_added, true);
    ['wh_new_name','wh_new_sell_price','wh_new_purchase_price','wh_new_purchase_usd','wh_new_stock'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('wh_new_unit_row').style.display = 'none';
    closeWhModal('addProductModal');
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteProduct(id, name) {
  if (!confirm(T.wh_delete_confirm)) return;
  const res = await fetch('/api/products/' + id, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.wh_product_deleted, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

let restockingShopId = null;  // null — свой склад; id филиала — пополнение склада филиала главным

function openRestockModal(id, name, shopId) {
  restockingProductId = id;
  restockingShopId = shopId || null;
  document.getElementById('restockModalTitle').textContent = T.wh_restock_title + ': ' + name;
  document.getElementById('restock_qty').value = '';
  document.getElementById('restock_price').value = '';
  const restockUsd = document.getElementById('restock_price_usd');
  if (restockUsd) restockUsd.value = '';
  document.getElementById('restock_date').value = fmtDate(new Date());
  document.getElementById('restockModal').classList.add('open');
}

function closeRestockModal() {
  document.getElementById('restockModal').classList.remove('open');
}

async function submitRestock() {
  const payload = {
    quantity: document.getElementById('restock_qty').value,
    purchase_price: document.getElementById('restock_price').value || null,
    restock_date: document.getElementById('restock_date').value || null,
  };
  const url = restockingShopId
    ? `/api/branches/${restockingShopId}/products/${restockingProductId}/restock`
    : `/api/products/${restockingProductId}/restock`;
  const res = await fetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    closeRestockModal();
    showMsg(T.wh_restocked, true);
    if (restockingShopId) { selectWhBranch(restockingShopId); WH.net = null; loadNetworkStock(); }
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function loadRestockHistory() {
  const el = document.getElementById('restockHistory');
  if (!el) return;
  let moves = [];
  try { moves = await (await fetch('/api/warehouse/movements')).json(); } catch (e) {}
  renderMovements(el, moves, !IS_BRANCH);
}

function renderMovements(el, moves, showPrice) {
  if (!el) return;
  if (!moves || !moves.length) { el.innerHTML = `<div class="hint-text">${T.wh_no_restocks}</div>`; return; }
  const icon = { restock: ['fa-arrow-down', '#15803D'], transfer_in: ['fa-right-to-bracket', '#0F52BA'], transfer_out: ['fa-right-from-bracket', '#B45309'], adjust: ['fa-scale-balanced', '#7C3AED'] };
  el.innerHTML = moves.slice(0, 30).map(m => {
    const [ic, col] = icon[m.type] || icon.restock;
    const sign = m.type === 'transfer_out' || (m.type === 'adjust' && m.delta < 0) ? '−' : '+';
    const what = m.type === 'restock' ? T.whs_mv_restock + (m.order_number ? ' · ' + T.ord_title_n.replace('{n}', m.order_number) : '')
      : m.type === 'adjust' ? `${T.whe_mv_adjust}: ${whQty(m.old_qty)} → ${whQty(m.new_qty)}${m.reason ? ' · ' + escapeHtml(m.reason) : ''}`
      : (m.type === 'transfer_in' ? `${T.whs_mv_from} ${escapeHtml(m.other_shop || '')}` : `${T.whs_mv_to} ${escapeHtml(m.other_shop || '')}`) + (m.batch ? ` · ${T.shp_batch} ${escapeHtml(m.batch)}` : '');
    return `
    <div class="wh-att">
      <i class="fa-solid ${ic}" style="color:${col};"></i>
      <div class="wa-main"><b>${escapeHtml(m.product_name)}</b><span>${m.date} · ${what}${showPrice && m.purchase_price ? ` · ${fmtNum(m.purchase_price)} ${T.currency}/${T.whs_per_unit}` : ''}</span></div>
      <b style="color:${col}; white-space:nowrap;">${sign}${whQty(m.quantity)} ${whUnit(m.unit)}</b>
    </div>`;
  }).join('');
}


let revenueChartInstance = null;

function renderRevenueChart(dailyData) {
  revenueChartInstance = drawRevenueBars('revenueChart', 'revenueSummary', dailyData, revenueChartInstance);
}

function rvDateLabel(iso, withWeekday) {
  const [y, m, d] = iso.split('-').map(Number);
  const months = T.st_months.split(',');
  const wd = T.st_weekdays.split(',');  // с понедельника
  const dow = (new Date(y, m - 1, d).getDay() + 6) % 7;
  return (withWeekday ? wd[dow] + ', ' : '') + d + ' ' + months[m - 1];
}

function drawRevenueBars(canvasId, summaryId, dailyData, prevInstance) {
  // Столбик на каждый день. Лучший день подсвечен красным, пунктир — средняя
  // выручка за рабочий день (дни без продаж в среднее не входят).
  const canvas = document.getElementById(canvasId);
  if (prevInstance) prevInstance.destroy();
  dailyData = dailyData || [];
  const totals = dailyData.map(d => d.total || 0);
  const sum = totals.reduce((a, b) => a + b, 0);
  const workDays = totals.filter(v => v > 0).length;
  const avg = workDays ? Math.round(sum / workDays) : 0;
  const maxVal = Math.max(0, ...totals);
  const bestIdx = maxVal > 0 ? totals.indexOf(maxVal) : -1;
  const visits = dailyData.reduce((a, d) => a + (d.count || 0), 0);

  const summaryEl = document.getElementById(summaryId);
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="rv-box"><b>${fmtShort(sum)}</b><span>${T.rv_total} · ${visits} ${T.brands_visits}</span></div>
      <div class="rv-box"><b>${fmtShort(avg)}</b><span>${T.rv_avg_day}</span></div>
      <div class="rv-box"><b>${workDays} / ${dailyData.length}</b><span>${T.rv_work_days}</span></div>
      ${bestIdx >= 0 ? `<div class="rv-box best"><b>${fmtShort(maxVal)}</b><span>${T.rv_best_day}: ${rvDateLabel(dailyData[bestIdx].date, false)}</span></div>` : ''}
    `;
  }
  if (!canvas || typeof Chart === 'undefined') return null;

  // легенда под графиком (создаём один раз)
  const wrap = canvas.parentElement;
  let legend = wrap.nextElementSibling;
  if (!legend || !legend.classList.contains('rv-legend')) {
    legend = document.createElement('div');
    legend.className = 'rv-legend';
    wrap.after(legend);
  }
  legend.innerHTML = `
    <span><i style="background:#0F52BA;"></i>${T.rv_legend_day}</span>
    ${bestIdx >= 0 ? `<span><i style="background:#E63946;"></i>${T.rv_best_day}</span>` : ''}
    ${avg ? `<span><i style="background:repeating-linear-gradient(90deg,#F59E0B 0 4px,transparent 4px 7px); height:3px; vertical-align:3px;"></i>${T.rv_avg_short}: ${fmtShort(avg)}</span>` : ''}
  `;

  const colors = totals.map((v, i) => i === bestIdx ? '#E63946' : '#0F52BA');
  const avgLine = {
    id: 'avgLine',
    afterDatasetsDraw(chart) {
      if (!avg) return;
      const y = chart.scales.y.getPixelForValue(avg);
      const area = chart.chartArea;
      const ctx = chart.ctx;
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(area.left, y); ctx.lineTo(area.right, y); ctx.stroke();
      ctx.restore();
    }
  };

  const chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: dailyData.map(d => rvDateLabel(d.date, false)),
      datasets: [{
        data: totals,
        backgroundColor: colors,
        hoverBackgroundColor: totals.map((v, i) => i === bestIdx ? '#C81E2B' : '#0A3D8F'),
        borderRadius: 5, borderSkipped: false,
        maxBarThickness: 26, categoryPercentage: 0.8, barPercentage: 0.9,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false, padding: 10,
          callbacks: {
            title: items => rvDateLabel(dailyData[items[0].dataIndex].date, true),
            label: item => `${fmtNum(item.raw)} ${T.currency}`,
            afterLabel: item => {
              const d = dailyData[item.dataIndex];
              return d.count ? `${d.count} ${T.brands_visits}` : T.rv_no_sales;
            },
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { autoSkip: true, maxTicksLimit: 8, maxRotation: 0, color: '#94A3B8', font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          border: { display: false },
          grid: { color: '#F1F5F9' },
          ticks: { maxTicksLimit: 5, color: '#94A3B8', font: { size: 11 }, callback: v => fmtShort(v) },
        }
      }
    },
    plugins: [avgLine],
  });
  return chart;
}

async function toggleCategoryBrands(categoryName, idx) {
  const panel = document.getElementById('catBrands_' + idx);
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  document.querySelectorAll('.dash-brands-panel').forEach(el => { if (el !== panel) el.style.display = 'none'; });
  if (isOpen) { panel.style.display = 'none'; return; }
  panel.innerHTML = T.stats_loading;
  panel.style.display = 'block';
  const brands = await (await fetch('/api/dashboard/top_brands?category=' + encodeURIComponent(categoryName))).json();
  panel.innerHTML = brands.length ? brands.map((b, j) => `
    <div class="dash-row" style="padding-left:28px; font-size:12.5px;">
      <span class="dash-row-name">${j + 1}. ${escapeHtml(b.name)}</span>
      <span class="dash-row-value">${b.qty.toLocaleString('ru-RU')}</span>
    </div>
  `).join('') : `<div class="hint-text" style="padding-left:28px;">${T.dash_no_data}</div>`;
}

async function loadDashboard() {
  const res = await fetch('/api/dashboard');
  const data = await res.json();

  renderRevenueChart(data.daily_revenue);

  const netEl = document.getElementById('dashNetProfit');
  if (netEl && data.net_profit) netEl.innerHTML = renderNetProfitHtml(data.net_profit);
  const debtEl = document.getElementById('dashDebtSummary');
  if (debtEl) debtEl.innerHTML = renderDebtHtml(data.debt_summary);
  const lowEl = document.getElementById('dashLowStock');
  if (lowEl) lowEl.innerHTML = renderLowStockHtml(data.low_stock, false);
}

function renderNetProfitHtml(np) {
  // прибыль = товары со склада (продажа − закупка) + работа/услуги; минус расходы.
  // Продажи без цены закупки в прибыль не входят — показываем их отдельно.
  const isNegative = np.net_profit < 0;
  const services = np.services || 0;
  const unpriced = np.unpriced || 0;
  return `
    <div class="dash-summary-grid" style="grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px;">
      <div class="dash-summary-box">
        <div class="dsb-num" style="font-size:15px; white-space:nowrap;" title="${np.oil_profit.toLocaleString('ru-RU')} ${T.currency}">${fmtShort(np.oil_profit)}</div>
        <div class="dsb-label">${T.np_goods_label}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num" style="font-size:15px; white-space:nowrap;" title="${services.toLocaleString('ru-RU')} ${T.currency}">${fmtShort(services)}</div>
        <div class="dsb-label">${T.np_services_label}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num warn" style="font-size:15px; white-space:nowrap;" title="${np.expenses_total.toLocaleString('ru-RU')} ${T.currency}">−${fmtShort(np.expenses_total)}</div>
        <div class="dsb-label">${T.dash_expenses_label}</div>
      </div>
    </div>
    <div style="text-align:center; margin-top:12px; padding-top:12px; border-top:1px dashed #86EFAC;">
      <div style="font-size:24px; font-weight:700; font-family:var(--font-mono); color:${isNegative ? '#B3241C' : '#15803D'};">${np.net_profit.toLocaleString('ru-RU')} ${T.currency}</div>
      <div style="font-size:11px; color:var(--hint); margin-top:2px;">${T.dash_net_profit_label}</div>
    </div>
    ${unpriced > 0 ? `
    <div style="margin-top:12px; padding:10px 12px; background:#FFFBEB; border:1px solid #FCD34D; border-radius:12px; font-size:12.5px; color:#92400E;">
      ⚠️ ${T.np_unpriced_1} <b>${unpriced.toLocaleString('ru-RU')} ${T.currency}</b> ${T.np_unpriced_2}
    </div>` : ''}`;
}

function renderDebtHtml(ds) {
  return `
    <div class="dash-summary-grid">
      <div class="dash-summary-box">
        <div class="dsb-num">${ds.total_remaining.toLocaleString('ru-RU')} ${T.currency}</div>
        <div class="dsb-label">${T.dash_total_owed}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num ${ds.overdue_count > 0 ? 'warn' : ''}">${ds.overdue_count} / ${ds.count}</div>
        <div class="dsb-label">${T.dash_overdue_of_total}</div>
      </div>
    </div>`;
}

function renderLowStockHtml(list, withShop) {
  if (!list || !list.length) return `<div class="hint-text">${T.dash_no_data}</div>`;
  return list.map(p => `
    <div class="dash-row">
      <span class="dash-row-name">${escapeHtml(p.name)}${withShop && p.shop_name ? ` <span class="hint-text">· ${escapeHtml(p.shop_name)}</span>` : ''}</span>
      <span class="dash-row-value warn">${p.stock_qty} ${p.unit === 'pc' ? T.unit_pc : T.unit_l}</span>
    </div>`).join('');
}

const BRAND_COLORS = ['#0F52BA', '#E63946', '#F4A261', '#2A9D8F', '#8E44AD', '#E9C46A', '#1D3557', '#06B6D4', '#84CC16', '#EC4899'];
const BRAND_OTHERS_COLOR = '#CBD5E1';
// Карточка брендов — одна логика для своей точки (prefix 'brand') и для сети
// филиалов (prefix 'netBrand', scope = 'all' или id филиала).
const BRAND_W = {};
function bw(p) {
  if (!BRAND_W[p]) BRAND_W[p] = { data: null, cat: null, days: 30, chart: null, scope: '' };
  return BRAND_W[p];
}

function fmtNum(n) { return Number(n || 0).toLocaleString('ru-RU'); }

function brandUnitLabel(unit) {
  if (unit === 'l') return T.unit_l;
  if (unit === 'pc') return T.unit_pc;
  return '';
}

function renderBrandPeriod(p) {
  const el = document.getElementById(p + 'Period');
  if (!el) return;
  const opts = [[30, T.brands_period_30], [90, T.brands_period_90], [365, T.brands_period_365]];
  el.innerHTML = opts.map(([d, label]) =>
    `<button class="${d === bw(p).days ? 'active' : ''}" onclick="setBrandDays('${p}', ${d})">${label}</button>`
  ).join('');
}

function setBrandDays(p, d) {
  bw(p).days = d;
  loadBrandStats(p);
}

async function loadBrandStats(p) {
  p = p || 'brand';
  const body = document.getElementById(p + 'Body');
  if (!body) return;
  renderBrandPeriod(p);
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - (bw(p).days - 1));
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  try {
    var brandSeq = (bw(p).seq = (bw(p).seq || 0) + 1);
    const scopeQs = bw(p).scope ? `&scope=${bw(p).scope}` : '';
    const res = await fetch(`/api/stats/brands?from=${iso(from)}&to=${iso(to)}${scopeQs}`);
    const fresh = await res.json();
    if (brandSeq !== bw(p).seq) return;  // пока грузилось, сменили период или точку
    bw(p).data = fresh;
  } catch (e) { bw(p).data = null; }
  const cats = (bw(p).data && bw(p).data.categories) || [];
  const chips = document.getElementById(p + 'CategoryChips');
  if (!cats.length) {
    chips.innerHTML = '';
    body.innerHTML = `<div class="hint-text">${T.brands_empty}</div>`;
    if (bw(p).chart) { bw(p).chart.destroy(); bw(p).chart = null; }
    return;
  }
  if (!cats.some(c => c.key === bw(p).cat)) bw(p).cat = cats[0].key;
  chips.innerHTML = cats.map(c => {
    const sub = c.metric === 'sum' ? '' : `<span class="bc-sub">${fmtNum(c.total_qty)} ${brandUnitLabel(c.unit)}</span>`;
    return `<div class="brand-chip ${c.key === bw(p).cat ? 'active' : ''}" onclick="selectBrandCategory('${p}', '${c.key}')">${escapeHtml(T[c.key] || c.key)}${sub}</div>`;
  }).join('');
  renderBrandCategory(p);
}

function selectBrandCategory(p, key) {
  bw(p).cat = key;
  document.querySelectorAll(`#${p}CategoryChips .brand-chip`).forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick').indexOf(`'${key}'`) !== -1);
  });
  renderBrandCategory(p);
}

function renderBrandCategory(p) {
  const body = document.getElementById(p + 'Body');
  const c = ((bw(p).data && bw(p).data.categories) || []).find(x => x.key === bw(p).cat);
  if (!c) return;
  const unit = brandUnitLabel(c.unit);
  const bySum = c.metric === 'sum';
  const mainVal = x => bySum ? `${fmtNum(x.sum)} ${T.currency}` : `${fmtNum(x.qty)} ${unit}`;
  const brandLabel = b => b.no_brand ? T.brands_no_brand : escapeHtml(b.name);

  // полоски считаем относительно лидера (лидер = полная полоска), а % справа — доля от всего
  const leaderVal = c.top.length ? (bySum ? c.top[0].sum : c.top[0].qty) || 1 : 1;
  const barW = x => Math.max(Math.round((bySum ? x.sum : x.qty) / leaderVal * 100), 2);
  const rows = c.top.map((b, i) => `
    <div class="brand-row">
      <div class="brand-row-top">
        <span class="brand-rank" style="background:${BRAND_COLORS[i]};">${i + 1}</span>
        <span class="brand-name">${brandLabel(b)}${i === 0 && c.top.length > 1 ? ' 🏆' : ''}</span>
        <span class="brand-val">${mainVal(b)}</span>
        <span class="brand-share">${b.share}%</span>
      </div>
      <div class="brand-bar"><i style="width:${barW(b)}%; background:${BRAND_COLORS[i]};"></i></div>
      <div class="brand-meta">${bySum ? '' : `${fmtNum(b.sum)} ${T.currency} · `}${b.visits} ${T.brands_visits}</div>
    </div>
  `).join('');
  const othersRow = c.others ? `
    <div class="brand-row">
      <div class="brand-row-top">
        <span class="brand-rank" style="background:${BRAND_OTHERS_COLOR}; color:#475569;">…</span>
        <span class="brand-name" style="color:#64748B;">${T.brands_others} (${c.others.count})</span>
        <span class="brand-val" style="color:#64748B;">${mainVal(c.others)}</span>
        <span class="brand-share">${c.others.share}%</span>
      </div>
      <div class="brand-bar"><i style="width:${Math.min(barW(c.others), 100)}%; background:${BRAND_OTHERS_COLOR};"></i></div>
    </div>` : '';

  body.innerHTML = `
    <div class="brand-summary">
      <div><b>${bySum ? fmtNum(c.top.reduce((a, b) => a + b.visits, 0)) : fmtNum(c.total_qty) + ' ' + unit}</b><span>${bySum ? T.brands_visits : T.brands_total_sold}</span></div>
      <div><b>${fmtNum(c.total_sum)}</b><span>${T.brands_revenue}, ${T.currency}</span></div>
      <div><b>${c.brand_count}</b><span>${bySum ? T.brands_items : T.brands_count}</span></div>
    </div>
    <div class="brand-donut-wrap"><canvas id="${p}Donut"></canvas></div>
    ${rows}${othersRow}
  `;
  renderBrandDonut(p, c, bySum ? `${fmtNum(c.total_sum)}` : `${fmtNum(c.total_qty)}`, bySum ? T.currency : unit);
}

function renderBrandDonut(p, c, centerValue, centerUnit) {
  const canvas = document.getElementById(p + 'Donut');
  if (!canvas || typeof Chart === 'undefined') return;
  if (bw(p).chart) bw(p).chart.destroy();
  const bySum = c.metric === 'sum';
  const labels = c.top.map(b => b.no_brand ? T.brands_no_brand : b.name);
  const values = c.top.map(b => bySum ? b.sum : b.qty);
  const colors = c.top.map((_, i) => BRAND_COLORS[i]);
  if (c.others) {
    labels.push(`${T.brands_others} (${c.others.count})`);
    values.push(bySum ? c.others.sum : c.others.qty);
    colors.push(BRAND_OTHERS_COLOR);
  }
  const centerText = {
    id: 'centerText',
    afterDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !meta.data.length) return;
      const x = meta.data[0].x, y = meta.data[0].y;
      const ctx = chart.ctx;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#0F172A';
      ctx.font = "700 20px 'Space Grotesk', sans-serif";
      ctx.fillText(centerValue, x, y - 8);
      ctx.fillStyle = '#64748B';
      ctx.font = "500 12px sans-serif";
      ctx.fillText(centerUnit, x, y + 13);
      ctx.restore();
    }
  };
  bw(p).chart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: '#fff', borderWidth: 2, hoverOffset: 6 }] },
    options: {
      responsive: true, cutout: '64%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => {
              const total = values.reduce((a, b) => a + b, 0) || 1;
              const pct = Math.round(item.raw / total * 1000) / 10;
              return ` ${item.label}: ${fmtNum(item.raw)} ${centerUnit} (${pct}%)`;
            }
          }
        }
      }
    },
    plugins: [centerText],
  });
}

function fmtShort(n) {
  // компактно для второстепенных цифр: 19 496 586 -> 19,5 млн; 710 000 -> 710 тыс
  n = Number(n || 0);
  const abs = Math.abs(n);
  if (abs >= 1e6) return (Math.round(n / 1e5) / 10).toLocaleString('ru-RU') + ' ' + T.st_mln;
  if (abs >= 1e4) return Math.round(n / 1e3).toLocaleString('ru-RU') + ' ' + T.st_thousand;
  return n.toLocaleString('ru-RU');
}

function stBadge(pct, extraClass) {
  if (pct === null || pct === undefined) return '';
  const up = pct >= 0;
  return `<span class="st-badge ${up ? 'up' : 'down'} ${extraClass || ''}">${up ? '↑' : '↓'} ${up ? '+' : ''}${String(pct).replace('.', ',')}%</span>`;
}

function renderStatCard(o) {
  // o = { label, d: {total,count,avg,paid_count,cash,card,clients}, cmp, cmpNote, profit, orange }
  const d = o.d || {};
  const cmp = o.cmp || null;
  const cl = d.clients || { total: 0, new: 0, returning: 0 };
  const cash = d.cash || 0, card = d.card || 0, paySum = (cash + card) || 1;
  const clSum = cl.total || 1;
  const badgeLine = cmp && cmp.pct !== null && cmp.pct !== undefined
    ? `${stBadge(cmp.pct)}<span class="st-badge-note">${o.cmpNote || ''}</span>` : '';
  const empty = !d.count;
  return `
    <div class="st-card ${o.orange ? 'orange' : ''}">
      <div class="st-label">${o.label}</div>
      <div class="st-amount">${fmtNum(d.total)}<small>${T.currency}</small></div>
      <div class="st-badge-line">${badgeLine}</div>
      ${empty ? `<div class="st-empty">${T.st_no_visits}</div>` : `
      <div class="st-row"><span>${T.st_services}</span><b>${d.count}</b></div>
      ${d.paid_count ? `<div class="st-row"><span>${T.st_avg}</span><b>${fmtNum(d.avg)} ${T.currency}${cmp ? stBadge(cmp.avg_pct) : ''}</b></div>` : ''}
      ${cl.total ? `
      <div class="st-block">
        <div class="st-block-head"><span>${T.st_clients}</span><b>${cl.total}</b></div>
        <div class="st-split"><i style="width:${cl.new / clSum * 100}%; background:#3B82F6;"></i><i style="width:${cl.returning / clSum * 100}%; background:#14B8A6;"></i></div>
        <div class="st-legend"><span style="--dot:#3B82F6;">${cl.new} ${T.st_new}</span><span style="--dot:#14B8A6;">${cl.returning} ${T.st_returning}</span></div>
      </div>` : ''}
      ${(cash || card) ? `
      <div class="st-block">
        <div class="st-block-head"><span>${T.st_payment}</span></div>
        <div class="st-split"><i style="width:${cash / paySum * 100}%; background:#22C55E;"></i><i style="width:${card / paySum * 100}%; background:#6366F1;"></i></div>
        <div class="st-legend"><span style="--dot:#22C55E;">${T.st_cash} ${fmtShort(cash)}</span><span style="--dot:#6366F1;">${T.st_card} ${fmtShort(card)}</span></div>
      </div>` : ''}
      ${o.profit !== null && o.profit !== undefined ? `<div class="st-row profit"><span>${T.st_profit}</span><b>${fmtNum(o.profit)} ${T.currency}</b></div>` : ''}
      `}
    </div>`;
}

function renderTodayStrip(d, profit) {
  d = d || {};
  const cl = d.clients || {};
  const chips = d.count ? `
    <div class="st-today-chips">
      <span class="st-chip">${T.st_services}: <b>${d.count}</b></span>
      ${d.paid_count ? `<span class="st-chip">${T.st_avg}: <b>${fmtShort(d.avg)}</b></span>` : ''}
      ${cl.total ? `<span class="st-chip">${T.st_clients}: <b>${cl.total}</b> (${cl.new} ${T.st_new})</span>` : ''}
      ${profit !== null && profit !== undefined ? `<span class="st-chip" style="background:#DCFCE7;">${T.st_profit}: <b style="color:#15803D;">${fmtShort(profit)}</b></span>` : ''}
    </div>` : `<div class="st-empty">${T.st_today_empty}</div>`;
  return `
    <div class="st-today">
      <div class="st-today-main">
        <span class="st-today-label">${T.stats_today}</span>
        <span class="st-today-amount">${fmtNum(d.total)}<small>${T.currency}</small></span>
      </div>
      ${chips}
    </div>`;
}

const ST_PERIODS = () => [
  ['week', T.stats_week, T.st_vs_week],
  ['month', T.stats_month, T.st_vs_month],
  ['year', T.stats_year, T.st_vs_year],
];

const NET = { scope: 'all', period: 'month', shops: [], revChart: null, cmpChart: null };

function setNetScope(scope) {
  NET.scope = String(scope);
  loadNetwork();
  const head = document.getElementById('netDetailHead');
  if (head) head.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadNetwork() {
  const grid = document.getElementById('netStatsGrid');
  if (!grid) return;
  let data;
  try {
    var netSeq = (NET.seq = (NET.seq || 0) + 1);
    data = await (await fetch(`/api/network/overview?scope=${encodeURIComponent(NET.scope)}`)).json();
  } catch (e) { return; }
  if (netSeq !== NET.seq) return;  // пока грузилось, выбрали другую точку
  if (!data.ok) return;
  NET.shops = data.shops || [];
  const isAll = NET.scope === 'all';

  document.getElementById('netScopeChips').innerHTML =
    [`<div class="brand-chip ${isAll ? 'active' : ''}" onclick="setNetScope('all')">${T.net_all}<span class="bc-sub">${NET.shops.length}</span></div>`]
      .concat(NET.shops.map(sh => `<div class="brand-chip ${NET.scope === String(sh.id) ? 'active' : ''}" onclick="setNetScope('${sh.id}')">${escapeHtml(sh.name)}${sh.is_head ? `<span class="bc-sub">${T.branch_head_label}</span>` : ''}</div>`))
      .join('');

  grid.innerHTML =
    renderTodayStrip(data.stats.today, data.profit.today) +
    `<div class="st-grid">${ST_PERIODS().map(([key, label, note]) => renderStatCard({
      label, d: data.stats[key], cmp: data.comparison[key], cmpNote: note,
      profit: data.profit[key], orange: isAll,
    })).join('')}</div>`;

  document.getElementById('netNetProfit').innerHTML = renderNetProfitHtml(data.net_profit);
  NET.revChart = drawRevenueBars('netRevenueChart', 'netRevenueSummary', data.daily_revenue, NET.revChart);
  document.getElementById('netDebtSummary').innerHTML = renderDebtHtml(data.debt_summary);
  document.getElementById('netLowStock').innerHTML = renderLowStockHtml(data.low_stock, isAll);

  bw('netBrand').scope = NET.scope;
  loadBrandStats('netBrand');

  document.querySelectorAll('#netCompareBody tbody tr').forEach(tr => {
    tr.classList.toggle('active', tr.dataset.shop === NET.scope);
  });
}

function setNetComparePeriod(p) {
  NET.period = p;
  loadNetworkCompare();
}

async function loadNetworkCompare() {
  const body = document.getElementById('netCompareBody');
  if (!body) return;
  document.getElementById('netComparePeriod').innerHTML =
    [['week', T.stats_week], ['month', T.stats_month], ['year', T.stats_year]]
      .map(([k, label]) => `<button class="${k === NET.period ? 'active' : ''}" onclick="setNetComparePeriod('${k}')">${label}</button>`).join('');
  let data;
  try {
    var cmpSeq = (NET.cseq = (NET.cseq || 0) + 1);
    data = await (await fetch(`/api/network/compare?period=${NET.period}`)).json();
  } catch (e) { return; }
  if (cmpSeq !== NET.cseq) return;
  if (!data.ok) return;
  const rows = data.rows || [];
  if (!rows.length) { body.innerHTML = `<div class="hint-text">${T.dash_no_data}</div>`; return; }

  // лучший показатель в каждой колонке подсвечиваем зелёным
  const maxOf = f => Math.max(...rows.map(f));
  const best = {
    total: maxOf(r => r.total), count: maxOf(r => r.count), avg: maxOf(r => r.avg),
    clients: maxOf(r => r.clients.total), profit: maxOf(r => r.profit), net: maxOf(r => r.net_profit),
  };
  const many = rows.length > 1;
  const cls = (v, b) => (many && v > 0 && v === b) ? 'best' : '';
  const sum = f => rows.reduce((a, r) => a + f(r), 0);
  const totPaid = sum(r => r.paid_count);
  const tot = {
    total: sum(r => r.total), count: sum(r => r.count),
    clients: sum(r => r.clients.total), newc: sum(r => r.clients.new),
    profit: sum(r => r.profit), expenses: sum(r => r.expenses), net: sum(r => r.net_profit),
  };
  const totAvg = totPaid ? Math.round(tot.total / totPaid) : 0;

  body.innerHTML = `
    <div class="table-wrap"><table class="net-cmp">
      <thead><tr>
        <th>${T.net_col_shop}</th><th>${T.net_col_revenue}</th><th>${T.net_col_change}</th>
        <th>${T.net_col_services}</th><th>${T.net_col_avg}</th><th>${T.net_col_clients}</th>
        <th>${T.net_col_profit}</th><th>${T.net_col_expenses}</th><th>${T.net_col_net}</th>
      </tr></thead>
      <tbody>${rows.map((r, i) => `
        <tr data-shop="${r.id}" class="${NET.scope === String(r.id) ? 'active' : ''}" onclick="setNetScope('${r.id}')">
          <td><div class="shop-cell"><span class="brand-rank" style="background:${BRAND_COLORS[i % BRAND_COLORS.length]};">${i + 1}</span>${escapeHtml(r.name)}${r.is_head ? ` <small>${T.branch_head_label}</small>` : ''}${i === 0 && many && r.total > 0 ? ' 🏆' : ''}</div></td>
          <td class="${cls(r.total, best.total)}">${fmtNum(r.total)}</td>
          <td>${r.pct === null || r.pct === undefined ? '—' : stBadge(r.pct)}</td>
          <td class="${cls(r.count, best.count)}">${r.count}</td>
          <td class="${cls(r.avg, best.avg)}">${r.paid_count ? fmtNum(r.avg) : '—'}</td>
          <td class="${cls(r.clients.total, best.clients)}">${r.clients.total} <span class="hint-text">(${r.clients.new})</span></td>
          <td class="${cls(r.profit, best.profit)}">${r.unpriced > 0 ? `<span title="${T.np_row_unpriced} ${fmtNum(r.unpriced)} ${T.currency}" style="cursor:help;">⚠️</span> ` : ''}${fmtNum(r.profit)}</td>
          <td>${fmtNum(r.expenses)}</td>
          <td class="${r.net_profit < 0 ? 'neg' : cls(r.net_profit, best.net)}">${fmtNum(r.net_profit)}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td>${T.net_total_row}</td><td>${fmtNum(tot.total)}</td><td></td><td>${tot.count}</td>
        <td>${totPaid ? fmtNum(totAvg) : '—'}</td><td>${tot.clients} <span class="hint-text">(${tot.newc})</span></td>
        <td>${fmtNum(tot.profit)}</td><td>${fmtNum(tot.expenses)}</td>
        <td class="${tot.net < 0 ? 'neg' : ''}">${fmtNum(tot.net)}</td>
      </tr></tfoot>
    </table></div>
    <div class="hint-text" style="margin-top:6px;">${T.net_sum_note} ${T.currency}. ${T.net_clients_note}</div>`;

  // горизонтальные столбцы: выручка и чистая прибыль по каждой точке
  const wrap = document.getElementById('netCompareChartWrap');
  const canvas = document.getElementById('netCompareChart');
  if (!canvas || typeof Chart === 'undefined') return;
  wrap.style.height = (60 + rows.length * 56) + 'px';
  let legend = wrap.nextElementSibling;
  if (!legend || !legend.classList.contains('rv-legend')) {
    legend = document.createElement('div');
    legend.className = 'rv-legend';
    wrap.after(legend);
  }
  legend.innerHTML = `
    <span><i style="background:#0F52BA;"></i>${T.net_col_revenue}</span>
    <span><i style="background:#22C55E;"></i>${T.net_col_net}</span>
    <span><i style="background:#E63946;"></i>${T.net_loss}</span>`;
  if (NET.cmpChart) NET.cmpChart.destroy();
  NET.cmpChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.name),
      datasets: [
        { label: T.net_col_revenue, data: rows.map(r => r.total), backgroundColor: '#0F52BA', borderRadius: 5, maxBarThickness: 20 },
        { label: T.net_col_net, data: rows.map(r => r.net_profit), backgroundColor: rows.map(r => r.net_profit < 0 ? '#E63946' : '#22C55E'), borderRadius: 5, maxBarThickness: 20 },
      ]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: it => ` ${it.dataset.label}: ${fmtNum(it.raw)} ${T.currency}` } },
      },
      scales: {
        x: { beginAtZero: true, grid: { color: '#F1F5F9' }, border: { display: false }, ticks: { color: '#94A3B8', callback: v => fmtShort(v), maxTicksLimit: 5, maxRotation: 0 } },
        y: { grid: { display: false }, ticks: { color: '#0F172A', font: { weight: '600' } } },
      },
      onClick: (evt, els) => { if (els.length) setNetScope(String(rows[els[0].index].id)); },
    }
  });
}

async function loadStats() {
  loadDashboard();
  loadBrandStats();  // для сотрудника карточки нет — функция сама выйдет
  const res = await fetch('/api/stats');
  const s = await res.json();
  let profit = null;
  if (WAREHOUSE_ENABLED && !IS_BRANCH) {
    const pRes = await fetch('/api/profit_stats');
    profit = await pRes.json();
  }
  document.getElementById('statsGrid').innerHTML =
    renderTodayStrip(s.today, profit ? profit.today : null) +
    `<div class="st-grid">${ST_PERIODS().map(([key, label, note]) => renderStatCard({
      label, d: s[key], cmp: s.comparison && s.comparison[key], cmpNote: note,
      profit: profit ? profit[key] : null,
    })).join('')}</div>`;

  if (!IS_BRANCH) {
    try {
      const agg = await (await fetch('/api/aggregated_stats')).json();
      const branchBtn = document.getElementById('substat-branches');
      if (agg.has_branches) {
        branchBtn.style.display = '';
        // сама сводка грузится при открытии вкладки (см. showStatsSubTab)
        if (document.getElementById('statsBranchesView').style.display !== 'none') {
          loadNetworkCompare();
          loadNetwork();
        }
      } else {
        branchBtn.style.display = 'none';
      }
    } catch (e) { /* не главный аккаунт или ошибка - просто не показываем подвкладку */ }
  }
}

function showStatsSubTab(t) {
  document.getElementById('statsOwnView').style.display = t === 'own' ? 'block' : 'none';
  document.getElementById('statsBranchesView').style.display = t === 'branches' ? 'block' : 'none';
  document.getElementById('substat-own').classList.toggle('active', t === 'own');
  document.getElementById('substat-branches').classList.toggle('active', t === 'branches');
  if (t === 'branches') {
    loadNetworkCompare();
    loadNetwork();
  }
}

async function loadBranchProducts(branchId) {
  const panel = document.getElementById('branchProductsPanel');
  if (!branchId) { panel.innerHTML = ''; return; }
  const products = await (await fetch(`/api/branches/${branchId}/products`)).json();
  if (!products.length) { panel.innerHTML = `<div class="hint-text">${T.wh_no_products}</div>`; return; }
  panel.innerHTML = products.map(p => `
    <div style="padding:6px 0; border-bottom:1px dashed var(--border); font-size:13px;">
      <div>${escapeHtml(p.name)} <span class="hint-text">(${p.stock_qty} ${p.unit === 'pc' ? T.unit_pc : T.unit_l})</span></div>
      <div style="display:flex; align-items:center; gap:6px; margin-top:4px; flex-wrap:wrap;">
        <input id="branch_price_${branchId}_${p.id}" type="number" value="${p.purchase_price ?? ''}" placeholder="${T.wh_purchase_price}"
               style="width:100px; padding:5px 8px; font-size:12px; flex:none;"
               oninput="onSumFieldEdited('branch_price_${branchId}_${p.id}', 'branch_price_usd_${branchId}_${p.id}')">
        <input id="branch_price_usd_${branchId}_${p.id}" type="number" step="0.01" placeholder="$"
               style="width:80px; padding:5px 8px; font-size:12px; flex:none;"
               oninput="onUsdFieldEdited('branch_price_usd_${branchId}_${p.id}', 'branch_price_${branchId}_${p.id}')">
        <button class="badge active" style="flex:none;" onclick="setBranchPurchasePrice(${branchId}, ${p.id})">${T.branch_save_price}</button>
        <span id="branch_price_saved_${branchId}_${p.id}" style="display:none; color:#1B8A5A; font-size:15px; flex:none;">✓</span>
      </div>
    </div>
  `).join('');
}

async function setBranchPurchasePrice(branchId, productId) {
  const input = document.getElementById(`branch_price_${branchId}_${productId}`);
  await fetch(`/api/branches/${branchId}/products/${productId}/purchase_price`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({purchase_price: input.value})
  });
  const check = document.getElementById(`branch_price_saved_${branchId}_${productId}`);
  if (check) {
    check.style.display = 'inline';
    setTimeout(() => { check.style.display = 'none'; }, 1500);
  }
}

function fmtDate(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function setStatsRange(from, to) {
  document.getElementById('stats_from').value = fmtDate(from);
  document.getElementById('stats_to').value = fmtDate(to);
  applyStatsRange();
}

function renderStatsPresets() {
  const presetsEl = document.getElementById('statsPresets');
  if (!presetsEl) return;  // вкладка "Статистика" скрыта (например, для сотрудника)
  const today = new Date();
  const presets = [
    [T.stats_preset_today, () => setStatsRange(today, today)],
    [T.stats_preset_yesterday, () => {
      const y = new Date(today); y.setDate(y.getDate() - 1);
      setStatsRange(y, y);
    }],
    [T.stats_preset_7days, () => {
      const start = new Date(today); start.setDate(start.getDate() - 6);
      setStatsRange(start, today);
    }],
    [T.stats_preset_this_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      setStatsRange(start, today);
    }],
    [T.stats_preset_prev_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const end = new Date(today.getFullYear(), today.getMonth(), 0);
      setStatsRange(start, end);
    }],
  ];
  document.getElementById('statsPresets').innerHTML = presets.map(([label], i) =>
    `<button class="lang-btn" onclick="STATS_PRESETS[${i}]()">${label}</button>`
  ).join('');
  window.STATS_PRESETS = presets.map(p => p[1]);
  const from = document.getElementById('stats_from');
  const to = document.getElementById('stats_to');
  if (!from.value) from.value = fmtDate(today);
  if (!to.value) to.value = fmtDate(today);
}

let currentRangeFrom = null, currentRangeTo = null;

async function applyStatsRange() {
  const from = document.getElementById('stats_from').value;
  const to = document.getElementById('stats_to').value;
  if (!from || !to) return;
  currentRangeFrom = from; currentRangeTo = to;
  const res = await fetch(`/api/stats/range?from=${from}&to=${to}`);
  const data = await res.json();
  if (!data.ok) { document.getElementById('statsRangeResult').innerHTML = ''; return; }
  const hasProfit = data.profit !== undefined;
  document.getElementById('statsRangeResult').innerHTML = `
    ${renderStatCard({ label: `${T.stats_range_result} ${from} — ${to}`, d: data, profit: hasProfit ? data.profit : null })}
    ${hasProfit ? `
    <div class="stats-card" style="margin-top:10px; background:linear-gradient(135deg, #F0FDF4, #ECFDF5); border-color:#86EFAC;">
      ${renderNetProfitHtml({ oil_profit: data.goods_profit || 0, services: data.services || 0, unpriced: data.unpriced || 0, expenses_total: data.expenses || 0, net_profit: data.net_profit })}
    </div>
    ` : ''}
    <div class="stats-card" style="margin-top:10px;">
      <label style="font-size:14px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">${T.dash_revenue_chart_title}</label>
      <div id="rangeRevenueSummary" class="rv-summary"></div>
      <div class="rv-chart-wrap"><canvas id="rangeRevenueChart"></canvas></div>
    </div>
  `;
  renderRangeChart(data.daily_revenue);
}

let rangeChartInstance = null;
function renderRangeChart(dailyData) {
  rangeChartInstance = drawRevenueBars('rangeRevenueChart', 'rangeRevenueSummary', dailyData, rangeChartInstance);
}

async function toggleRangeCategoryBrands(categoryName, idx) {
  const panel = document.getElementById('rangeCatBrands_' + idx);
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  document.querySelectorAll('.dash-brands-panel').forEach(el => { if (el !== panel) el.style.display = 'none'; });
  if (isOpen) { panel.style.display = 'none'; return; }
  panel.innerHTML = T.stats_loading;
  panel.style.display = 'block';
  const url = `/api/dashboard/top_brands?category=${encodeURIComponent(categoryName)}&from=${currentRangeFrom}&to=${currentRangeTo}`;
  const brands = await (await fetch(url)).json();
  panel.innerHTML = brands.length ? brands.map((b, j) => `
    <div class="dash-row" style="padding-left:28px; font-size:12.5px;">
      <span class="dash-row-name">${j + 1}. ${escapeHtml(b.name)}</span>
      <span class="dash-row-value">${b.qty.toLocaleString('ru-RU')}</span>
    </div>
  `).join('') : `<div class="hint-text" style="padding-left:28px;">${T.dash_no_data}</div>`;
}

renderStatsPresets();

function renderBranchStatsPresets() {
  const presetsEl = document.getElementById('branchStatsPresets');
  if (!presetsEl) return;  // подвкладка "Все филиалы" скрыта (нет филиалов) или недоступна
  const today = new Date();
  const presets = [
    [T.stats_preset_today, () => setBranchStatsRange(today, today)],
    [T.stats_preset_yesterday, () => {
      const y = new Date(today); y.setDate(y.getDate() - 1);
      setBranchStatsRange(y, y);
    }],
    [T.stats_preset_7days, () => {
      const start = new Date(today); start.setDate(start.getDate() - 6);
      setBranchStatsRange(start, today);
    }],
    [T.stats_preset_this_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      setBranchStatsRange(start, today);
    }],
    [T.stats_preset_prev_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const end = new Date(today.getFullYear(), today.getMonth(), 0);
      setBranchStatsRange(start, end);
    }],
  ];
  presetsEl.innerHTML = presets.map(([label], i) =>
    `<button class="lang-btn" onclick="BRANCH_STATS_PRESETS[${i}]()">${label}</button>`
  ).join('');
  window.BRANCH_STATS_PRESETS = presets.map(p => p[1]);
  const from = document.getElementById('branch_stats_from');
  const to = document.getElementById('branch_stats_to');
  if (from && !from.value) from.value = fmtDate(today);
  if (to && !to.value) to.value = fmtDate(today);
}

function setBranchStatsRange(from, to) {
  document.getElementById('branch_stats_from').value = fmtDate(from);
  document.getElementById('branch_stats_to').value = fmtDate(to);
  applyBranchStatsRange();
}

async function applyBranchStatsRange() {
  const from = document.getElementById('branch_stats_from').value;
  const to = document.getElementById('branch_stats_to').value;
  if (!from || !to) return;
  const res = await fetch(`/api/aggregated_stats/range?from=${from}&to=${to}`);
  const data = await res.json();
  if (!data.ok) { document.getElementById('branchStatsRangeResult').innerHTML = ''; return; }

  const breakdown = data.breakdown || [];
  const breakdownRows = breakdown.map(r => `
    <tr>
      <td>${escapeHtml(r.shop_name)}${r.is_head ? ` <span class="hint-text">(${T.branch_head_label})</span>` : ''}</td>
      <td>${r.revenue.total.toLocaleString('ru-RU')} ${T.currency}</td>
      <td style="color:#1B8A5A;">${r.profit.toLocaleString('ru-RU')} ${T.currency}</td>
    </tr>
  `).join('');

  document.getElementById('branchStatsRangeResult').innerHTML = `
    <div style="margin-bottom:14px;">${renderStatCard({ label: `${T.stats_range_result} ${from} — ${to}`, d: data.revenue, profit: data.profit, orange: true })}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>${T.branch_col_label}</th><th>${T.stats_revenue_label}</th><th>${T.stats_profit_label}</th></tr></thead>
      <tbody>${breakdownRows}</tbody>
    </table></div>
  `;

  renderBranchChart(breakdown);
}

function renderBranchChart(breakdown) {
  const wrap = document.getElementById('branchChartWrap');
  if (!wrap) return;
  if (typeof Chart === 'undefined' || !breakdown.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  const canvas = document.getElementById('branchChart');
  if (window.branchChartInstance) { window.branchChartInstance.destroy(); }
  window.branchChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: breakdown.map(r => r.shop_name),
      datasets: [
        { label: T.stats_revenue_label, data: breakdown.map(r => r.revenue.total), backgroundColor: '#E63946' },
        { label: T.branch_chart_profit_label, data: breakdown.map(r => r.profit), backgroundColor: '#1B8A5A' },
      ]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } }
  });
}

renderBranchStatsPresets();

async function switchLanguage() {
  const newLang = LANG === 'ru' ? 'uz' : 'ru';
  await fetch('/api/set_language', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({language: newLang})
  });
  window.location.reload();
}

async function loadBroadcastInfo() {
  const res = await fetch('/api/broadcast/recipients');
  const data = await res.json();
  document.getElementById('broadcastRecipients').textContent =
    `${T.broadcast_recipients_text} ${data.count} ${T.broadcast_recipients_suffix}`;

  const res2 = await fetch('/api/broadcast/history');
  const items = await res2.json();
  document.getElementById('broadcastHistory').innerHTML = items.length ? items.map(b => `
    <div style="padding:8px 0;border-bottom:1px dashed var(--border);font-size:13px;">
      <div>${b.message.length > 80 ? b.message.slice(0,80) + '…' : b.message}</div>
      <div class="hint-text">${b.created_at} — ${T.broadcast_status_label} ${b.status}${b.status === 'done' ? `, ${T.broadcast_delivered} ${b.total_sent}, ${T.broadcast_failed} ${b.total_failed}` : ''}</div>
    </div>
  `).join('') : `<div class="hint-text">${T.broadcast_none_yet}</div>`;
}

async function sendBroadcast() {
  const message = document.getElementById('broadcast_message').value.trim();
  if (!message) { showMsg(T.broadcast_empty_msg, false); return; }
  if (!confirm(T.broadcast_confirm)) return;
  const res = await fetch('/api/broadcast', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.broadcast_queued, true);
    document.getElementById('broadcast_message').value = '';
    setTimeout(loadBroadcastInfo, 4000);
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 6000);
}

// ---- Жидкости и фильтры (детализация замены) ----
const FLUID_KEYS = ["fluid_0", "fluid_1", "fluid_2", "fluid_3", "fluid_4"];
const FILTER_KEYS = ["filter_0", "filter_1", "filter_2", "filter_3"];

// Общая логика для полей "марка" в форме внесения/редактирования замены —
// используется и в обычной форме "Внести замену", и в форме
// добавления/редактирования из истории (svcModal). Если для категории есть
// товары на складе — поле становится выпадающим списком с остатком и ценой,
// иначе (или если склад не включён точке) — обычное текстовое поле, как и
// раньше.
function productsForCategory(key) {
  return WAREHOUSE_ENABLED ? productsCache.filter(p => p.category === key) : [];
}

function brandFieldHtml(key, fieldId, onPickHandler) {
  const prods = productsForCategory(key);
  if (!prods.length) {
    return `<input id="${fieldId}" placeholder="${T.brand_ph}">`;
  }
  const options = ['<option value="">' + T.brand_ph + '</option>'].concat(
    prods.map(p => {
      const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
      const stockWarn = p.stock_qty < 0 ? ' ⚠️' : '';
      return `<option value="${p.id}" data-price="${p.sell_price || ''}" data-name="${escapeHtml(p.name)}">${escapeHtml(p.name)} (${p.stock_qty} ${unitLabel}${stockWarn})</option>`;
    })
  ).join('');
  return `<select id="${fieldId}" data-is-product="1" onchange="${onPickHandler}">${options}</select>`;
}

function readBrandField(fieldId) {
  const el = document.getElementById(fieldId);
  if (!el) return { brand: null, product_id: null };
  if (el.tagName === 'SELECT') {
    if (!el.value) return { brand: null, product_id: null };
    const opt = el.options[el.selectedIndex];
    return { brand: opt.dataset.name || null, product_id: parseInt(el.value) };
  }
  return { brand: el.value.trim() || null, product_id: null };
}

function selectOrPreserveBrand(brandEl, it) {
  // Подставляет сохранённую позицию в поле "марка" при открытии редактирования.
  // Если это обычное текстовое поле — просто вписываем текст, как раньше.
  // Если это выпадающий список (склад включён и в категории есть товары) —
  // пытаемся выбрать ТОТ ЖЕ товар. Но если товар с тех пор удалили со склада
  // (его больше нет среди опций) — список НЕ должен молча показывать пустое
  // поле: тогда добавляем в список одноразовую "историческую" опцию с
  // сохранённым названием, чтобы при обычном пересохранении (без изменения
  // этого поля) марка не терялась.
  if (brandEl.tagName === 'INPUT') {
    brandEl.value = it.brand || '';
    return;
  }
  if (brandEl.tagName !== 'SELECT') return;
  if (it.product_id && [...brandEl.options].some(o => o.value === String(it.product_id))) {
    brandEl.value = String(it.product_id);
  } else if (it.brand) {
    const phantom = document.createElement('option');
    phantom.value = it.product_id || ('legacy_' + Math.random().toString(36).slice(2));
    phantom.textContent = it.brand + ' (' + T.wh_product_unavailable + ')';
    phantom.dataset.name = it.brand;
    if (!it.product_id) phantom.dataset.legacy = '1';
    brandEl.appendChild(phantom);
    brandEl.value = phantom.value;
  }
}

// ---- "Прочие товары" — динамический список строк (как в чеке), для товаров
// со склада, которые не подходят ни под одну из фиксированных категорий
// (жидкости/фильтры). prefix: 'other' — основная форма "Внести замену",
// 'svcOther' — форма редактирования/добавления из истории. ----
let otherStockRows = [];
let otherStockSeq = 0;
let svcOtherStockRows = [];
let svcOtherStockSeq = 0;

function renderOneOtherStockRow(prefix, id) {
  const prods = productsForCategory('other');
  const updateFn = prefix === 'other' ? 'updateTotal' : 'updateSvcTotal';
  const options = ['<option value="">' + T.brand_ph + '</option>'].concat(
    prods.map(p => {
      const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
      const stockWarn = p.stock_qty < 0 ? ' ⚠️' : '';
      return `<option value="${p.id}" data-price="${p.sell_price || ''}" data-name="${escapeHtml(p.name)}">${escapeHtml(p.name)} (${p.stock_qty} ${unitLabel}${stockWarn})</option>`;
    })
  ).join('');
  return `
    <div class="other-stock-row" id="${prefix}_stockrow_${id}">
      <select id="${prefix}_stock_product_${id}" onchange="onOtherStockPicked('${prefix}', ${id})">${options}</select>
      <input id="${prefix}_stock_price_${id}" type="number" placeholder="${T.price_ph}" oninput="${updateFn}()">
      <input id="${prefix}_stock_qty_${id}" type="number" step="0.1" placeholder="${T.qty_ph}" oninput="${updateFn}()">
      <button type="button" onclick="removeOtherStockRow('${prefix}', ${id})">✕</button>
    </div>
  `;
}

function addOtherStockRow(prefix) {
  let id;
  if (prefix === 'other') { otherStockSeq++; id = otherStockSeq; otherStockRows.push(id); }
  else { svcOtherStockSeq++; id = svcOtherStockSeq; svcOtherStockRows.push(id); }
  const container = document.getElementById(prefix + 'StockRows');
  if (!container) return;
  // добавляем ТОЛЬКО новую строку в конец — не трогаем уже существующие,
  // чтобы не стереть то, что пользователь уже успел ввести в них
  container.insertAdjacentHTML('beforeend', renderOneOtherStockRow(prefix, id));
}

function removeOtherStockRow(prefix, id) {
  if (prefix === 'other') { otherStockRows = otherStockRows.filter(x => x !== id); }
  else { svcOtherStockRows = svcOtherStockRows.filter(x => x !== id); }
  // удаляем ТОЛЬКО конкретный элемент строки — соседние строки не трогаем
  const rowEl = document.getElementById(`${prefix}_stockrow_${id}`);
  if (rowEl) rowEl.remove();
  if (prefix === 'other') updateTotal(); else updateSvcTotal();
}

function renderOtherStockRows(prefix) {
  // Полная перерисовка С НУЛЯ — используется только при сбросе формы или
  // загрузке сохранённых позиций (когда в DOM ещё нет строк, которые можно
  // было бы случайно затереть). Для добавления/удаления ОДНОЙ строки к уже
  // заполненному списку используются addOtherStockRow/removeOtherStockRow —
  // они не перерисовывают соседние строки.
  const container = document.getElementById(prefix + 'StockRows');
  if (!container) return;
  const ids = prefix === 'other' ? otherStockRows : svcOtherStockRows;
  container.innerHTML = ids.map(id => renderOneOtherStockRow(prefix, id)).join('');
}

function onOtherStockPicked(prefix, id) {
  const el = document.getElementById(`${prefix}_stock_product_${id}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`${prefix}_stock_price_${id}`).value = opt.dataset.price;
  if (prefix === 'other') updateTotal(); else updateSvcTotal();
}

function collectOtherStockItems(prefix) {
  const ids = prefix === 'other' ? otherStockRows : svcOtherStockRows;
  const items = [];
  ids.forEach(id => {
    const selectEl = document.getElementById(`${prefix}_stock_product_${id}`);
    const priceEl = document.getElementById(`${prefix}_stock_price_${id}`);
    const qtyEl = document.getElementById(`${prefix}_stock_qty_${id}`);
    if (!selectEl || !priceEl || !qtyEl) return;
    const price = parseFloat(priceEl.value) || 0;
    const qty = parseFloat(qtyEl.value) || 0;
    if (price > 0 && qty > 0 && selectEl.value) {
      const opt = selectEl.options[selectEl.selectedIndex];
      items.push({
        key: 'other_stock', name: opt.dataset.name || '', brand: null, product_id: parseInt(selectEl.value),
        unit_price: price, qty, total: Math.round(price * qty),
      });
    }
  });
  return items;
}

function fillOtherStockRowsFrom(prefix, items) {
  // Восстанавливает СРАЗУ ВСЕ позиции "Прочее" при открытии редактирования.
  // Важно: сначала регистрируем id всех строк и рисуем их ОДНИМ вызовом
  // renderOtherStockRows — если рисовать по одной (вызывая render на каждую),
  // каждый следующий вызов полностью перерисовывает контейнер и стирает
  // выбор, уже сделанный в предыдущих строках.
  if (!items.length) return;
  const ids = items.map(() => {
    if (prefix === 'other') { otherStockSeq++; otherStockRows.push(otherStockSeq); return otherStockSeq; }
    svcOtherStockSeq++; svcOtherStockRows.push(svcOtherStockSeq); return svcOtherStockSeq;
  });
  renderOtherStockRows(prefix);
  items.forEach((it, i) => {
    const id = ids[i];
    const selectEl = document.getElementById(`${prefix}_stock_product_${id}`);
    if (selectEl) selectOrPreserveBrand(selectEl, { product_id: it.product_id, brand: it.name });
    document.getElementById(`${prefix}_stock_price_${id}`).value = it.unit_price ?? '';
    document.getElementById(`${prefix}_stock_qty_${id}`).value = it.qty ?? '';
  });
}

// ---- Быстрый поиск товара со склада при вводе замены ----
// Пишешь 2–3 кусочка названия в любом порядке ("mit 5w30 sp", "spark") —
// показываются подходящие товары; нажатие на товар ставит его в нужную
// строку формы (моторное масло, фильтр и т.д.) ровно так же, как выбор из
// выпадающего списка, и подставляет цену. Выпадающие списки остаются.
// ctx: 'main' — форма "Внести замену", 'svc' — окно добавления/редактирования.
const PICK_TR = {а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'j',з:'z',и:'i',й:'i',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'h',ц:'s',ч:'ch',ш:'sh',щ:'sh',ъ:'',ы:'i',ь:'',э:'e',ю:'yu',я:'ya',ў:'o',қ:'k',ғ:'g',ҳ:'h'};
const PICK = { main: [], svc: [] };

function pickNorm(s) {
  // регистр, дефисы, пробелы, точки не важны; кириллица = латиница; w = v
  return String(s || '').toLowerCase().split('').map(c => PICK_TR[c] ?? c).join('')
    .replace(/w/g, 'v').replace(/[^a-z0-9]/g, '');
}

function pickCatLabel(k) { return k === 'other' ? T.other : (T[k] || k); }

function pickEls(ctx) {
  return ctx === 'svc'
    ? { inp: document.getElementById('svcPickSearch'), box: document.getElementById('svcPickResults') }
    : { inp: document.getElementById('pickSearch'), box: document.getElementById('pickResults') };
}

function renderPickResults(ctx) {
  const { inp, box } = pickEls(ctx);
  if (!inp || !box) return;
  const words = inp.value.trim().split(' ').map(pickNorm).filter(Boolean);
  if (!words.length) { box.innerHTML = ''; PICK[ctx] = []; return; }
  const cats = FLUID_KEYS.concat(FILTER_KEYS, ['other']);
  const found = productsCache
    .filter(p => cats.includes(p.category))
    .map(p => {
      const n = pickNorm(p.name);
      const hay = n + '|' + pickNorm(pickCatLabel(p.category));
      if (!words.every(w => hay.includes(w))) return null;
      let score = 0;
      if (n.startsWith(words[0])) score -= 2;
      if (!(p.stock_qty > 0)) score += 5;
      return { p, score };
    })
    .filter(Boolean)
    .sort((a, b) => a.score - b.score || String(a.p.name).localeCompare(String(b.p.name)))
    .slice(0, 8)
    .map(x => x.p);
  PICK[ctx] = found;
  if (!found.length) { box.innerHTML = `<div class="pick-note">${T.pick_nothing}</div>`; return; }
  box.innerHTML = found.map(p => {
    const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
    const stock = p.stock_qty > 0
      ? `${p.stock_qty} ${unitLabel}`
      : `<span class="pi-out">${p.stock_qty} ${unitLabel} ⚠️</span>`;
    const price = p.sell_price ? fmtNum(p.sell_price) : '—';
    return `<div class="pick-item" role="button" tabindex="0" onclick="pickProduct('${ctx}', ${p.id})">
      <div class="pi-main"><div class="pi-name">${escapeHtml(p.name)}</div>
      <div class="pi-sub">${escapeHtml(pickCatLabel(p.category))} · ${stock}</div></div>
      <div class="pi-price">${price}</div></div>`;
  }).join('');
}

function onPickKey(e, ctx) {
  if (e.key !== 'Enter' || e.isComposing) return;
  e.preventDefault();
  e.stopPropagation();
  if (PICK[ctx] && PICK[ctx].length) pickProduct(ctx, PICK[ctx][0].id);
}

function pickProduct(ctx, id) {
  const p = productsCache.find(x => x.id === id);
  if (!p) return;
  const pre = ctx === 'svc' ? 'svc_' : '';
  const fi = FLUID_KEYS.indexOf(p.category);
  const ti = FILTER_KEYS.indexOf(p.category);
  let sel = null, focusEl = null;
  if (fi >= 0) {
    sel = document.getElementById(`${pre}fluid_brand_${fi}`);
    focusEl = document.getElementById(`${pre}fluid_liters_${fi}`);
  } else if (ti >= 0) {
    sel = document.getElementById(`${pre}filter_brand_${ti}`);
    focusEl = document.getElementById(`${pre}filter_price_${ti}`);
  } else {
    const prefix = ctx === 'svc' ? 'svcOther' : 'other';
    const rows = () => (prefix === 'other' ? otherStockRows : svcOtherStockRows);
    let rid = rows().find(r => {
      const s = document.getElementById(`${prefix}_stock_product_${r}`);
      return s && !s.value;
    });
    if (rid === undefined) { addOtherStockRow(prefix); rid = rows()[rows().length - 1]; }
    sel = document.getElementById(`${prefix}_stock_product_${rid}`);
    focusEl = document.getElementById(`${prefix}_stock_qty_${rid}`);
  }
  if (!sel || sel.tagName !== 'SELECT') return;
  sel.value = String(p.id);
  if (sel.value !== String(p.id)) return;
  sel.dispatchEvent(new Event('change'));

  const { inp, box } = pickEls(ctx);
  if (inp) inp.value = '';
  PICK[ctx] = [];
  if (box) {
    box.innerHTML = `<div class="pick-note ok">✓ ${escapeHtml(p.name)} → ${escapeHtml(pickCatLabel(p.category))}</div>`;
    setTimeout(() => { if (inp && !inp.value) box.innerHTML = ''; }, 3500);
  }
  const row = sel.closest('.item-row, .other-stock-row');
  if (row) {
    row.classList.remove('pick-flash');
    void row.offsetWidth;
    row.classList.add('pick-flash');
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  if (focusEl && !focusEl.value) setTimeout(() => focusEl.focus({ preventScroll: true }), 300);
}

function clearPick(ctx) {
  const { inp, box } = pickEls(ctx);
  if (inp) inp.value = '';
  if (box) box.innerHTML = '';
  PICK[ctx] = [];
}

function renderItemLists() {
  document.getElementById('fluidsList').innerHTML = FLUID_KEYS.map((key, i) => `
    <div class="item-row" id="row_${key}">
      <span class="item-name">${T[key]}</span>
      ${brandFieldHtml(key, `fluid_brand_${i}`, `onFluidProductPicked(${i})`)}
      <input id="fluid_price_${i}" type="number" placeholder="${T.price_per_liter_ph}" oninput="updateTotal()">
      <input id="fluid_liters_${i}" type="number" step="0.1" placeholder="${T.liters_ph}" oninput="updateTotal()">
      <button type="button" class="row-x" onclick="closeItemRow('${key}')" aria-label="${T.af_remove}">✕</button>
    </div>
  `).join('');
  document.getElementById('filtersList').innerHTML = FILTER_KEYS.map((key, i) => {
    const prods = productsForCategory(key);
    const brandField = prods.length ? brandFieldHtml(key, `filter_brand_${i}`, `onFilterProductPicked(${i})`) : '';
    return `
    <div class="item-row" id="row_${key}">
      <span class="item-name" style="flex:${prods.length ? '1.3' : '2.3'};">${T[key]}</span>
      ${brandField}
      <input id="filter_price_${i}" type="number" placeholder="${T.price_ph}" oninput="updateTotal()">
      <button type="button" class="row-x" onclick="closeItemRow('${key}')" aria-label="${T.af_remove}">✕</button>
    </div>
  `;
  }).join('');
  syncItemRows();
}

// Показываем только нужные строки товаров: по умолчанию моторное масло и
// масляный фильтр, остальные — кнопками «+ АКПП», «+ Антифриз»… Строка с
// заполненным значением видна всегда (после «Повторить прошлую», выбора из
// поиска по складу и т.п.). ✕ очищает строку и прячет её.
const ROW_DEFAULT = ['fluid_0', 'filter_0'];
let ROW_OPEN = new Set(ROW_DEFAULT);
function rowFieldIds(key) {
  const fi = FLUID_KEYS.indexOf(key), ti = FILTER_KEYS.indexOf(key);
  if (fi >= 0) return [`fluid_brand_${fi}`, `fluid_price_${fi}`, `fluid_liters_${fi}`];
  if (ti >= 0) return [`filter_brand_${ti}`, `filter_price_${ti}`];
  return [];
}
function rowHasValue(key) {
  return rowFieldIds(key).some(id => { const el = document.getElementById(id); return el && String(el.value || '').trim() !== ''; });
}
function syncItemRows() {
  const hidden = [];
  FLUID_KEYS.concat(FILTER_KEYS).forEach(key => {
    const row = document.getElementById('row_' + key);
    if (!row) return;
    if (rowHasValue(key)) ROW_OPEN.add(key);
    const vis = ROW_OPEN.has(key);
    row.style.display = vis ? '' : 'none';
    if (!vis) hidden.push(key);
  });
  const box = document.getElementById('itemAddChips');
  if (box) box.innerHTML = hidden.map(k => `<button type="button" onclick="openItemRow('${k}')"><i class="fa-solid fa-plus"></i>${T[k]}</button>`).join('');
}
function openItemRow(key) {
  ROW_OPEN.add(key);
  syncItemRows();
  const first = rowFieldIds(key).map(id => document.getElementById(id)).find(Boolean);
  if (first) setTimeout(() => first.focus(), 50);
}
function closeItemRow(key) {
  rowFieldIds(key).forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  ROW_OPEN.delete(key);
  updateTotal();
}

// Оплата одной кнопкой: наличные / карта / наличные + карта / в долг.
let PAY_MODE = 'cash';
function setPayMode(m) {
  PAY_MODE = m;
  document.querySelectorAll('#paySeg button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  const inputs = document.getElementById('payInputs');
  if (inputs) inputs.style.display = (m === 'mix' || m === 'debt') ? 'block' : 'none';
  const debt = document.getElementById('debt_enabled');
  if (m === 'debt') {
    if (debt && !debt.checked) { debt.checked = true; toggleDebtSection(); }
    paymentSplitTouched = true;
    document.getElementById('pay_cash').value = '';
    document.getElementById('pay_card').value = '';
    updateDebtRemaining();
    return;
  }
  if (debt && debt.checked) { debt.checked = false; toggleDebtSection(); }
  paymentSplitTouched = false;
  updateTotal();
}

function onFluidProductPicked(i) {
  const el = document.getElementById(`fluid_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`fluid_price_${i}`).value = opt.dataset.price;
  updateTotal();
}

function onFilterProductPicked(i) {
  const el = document.getElementById(`filter_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`filter_price_${i}`).value = opt.dataset.price;
  updateTotal();
}

function collectItems() {
  const items = [];
  FLUID_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`fluid_price_${i}`).value) || 0;
    const liters = parseFloat(document.getElementById(`fluid_liters_${i}`).value) || 0;
    if (price > 0 && liters > 0) {
      const { brand, product_id } = readBrandField(`fluid_brand_${i}`);
      items.push({
        key, name: T[key], brand, product_id,
        unit_price: price, qty: liters, total: Math.round(price * liters),
      });
    }
  });
  FILTER_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`filter_price_${i}`).value) || 0;
    if (price > 0) {
      const brandEl = document.getElementById(`filter_brand_${i}`);
      const { brand, product_id } = brandEl ? readBrandField(`filter_brand_${i}`) : { brand: null, product_id: null };
      items.push({key, name: T[key], brand, product_id, unit_price: price, qty: 1, total: Math.round(price)});
    }
  });
  const otherName = document.getElementById('other_name').value.trim();
  const otherPrice = parseFloat(document.getElementById('other_price').value) || 0;
  if (otherPrice > 0) {
    items.push({key: 'other', name: `${T.other_prefix}: ${otherName || T.other_unnamed}`, unit_price: otherPrice, qty: 1, total: Math.round(otherPrice)});
  }
  items.push(...collectOtherStockItems('other'));
  return items;
}

let paymentSplitTouched = false;

function updateTotal() {
  const total = collectItems().reduce((sum, i) => sum + i.total, 0);
  document.getElementById('totalCost').textContent = total.toLocaleString('ru-RU') + ' ' + T.currency;
  const payCash = document.getElementById('pay_cash');
  const payCard = document.getElementById('pay_card');
  if (payCash && payCard && !paymentSplitTouched) {
    if (typeof PAY_MODE !== 'undefined' && PAY_MODE === 'card') {
      payCash.value = '';
      payCard.value = total || '';
    } else {
      payCash.value = total || '';
      payCard.value = '';
    }
  }
  updateDebtRemaining();
  if (typeof syncItemRows === 'function') syncItemRows();
}

function onPayCashInput() {
  paymentSplitTouched = true;
  const debtEnabled = document.getElementById('debt_enabled').checked;
  if (!debtEnabled) {
    const total = collectItems().reduce((sum, i) => sum + i.total, 0);
    const cash = parseFloat(document.getElementById('pay_cash').value) || 0;
    document.getElementById('pay_card').value = Math.max(0, Math.round(total - cash));
  }
  updateDebtRemaining();
}

function onPayCardInput() {
  paymentSplitTouched = true;
  const debtEnabled = document.getElementById('debt_enabled').checked;
  if (!debtEnabled) {
    const total = collectItems().reduce((sum, i) => sum + i.total, 0);
    const card = parseFloat(document.getElementById('pay_card').value) || 0;
    document.getElementById('pay_cash').value = Math.max(0, Math.round(total - card));
  }
  updateDebtRemaining();
}

function updateDebtRemaining() {
  const debtEl = document.getElementById('debtRemaining');
  if (!debtEl) return;
  const total = collectItems().reduce((sum, i) => sum + i.total, 0);
  const cash = parseFloat(document.getElementById('pay_cash').value) || 0;
  const card = parseFloat(document.getElementById('pay_card').value) || 0;
  const remaining = Math.max(0, Math.round(total - cash - card));
  debtEl.textContent = remaining.toLocaleString('ru-RU') + ' ' + T.currency;
}

function toggleDebtSection() {
  const enabled = document.getElementById('debt_enabled').checked;
  document.getElementById('debtFields').style.display = enabled ? 'block' : 'none';
  if (!enabled) {
    // выключили - возвращаем обычное поведение (наличные/карта снова = вся сумма)
    paymentSplitTouched = false;
    updateTotal();
    document.getElementById('debt_installment_amount').value = '';
    document.getElementById('debt_interval_days').value = '';
  } else {
    updateDebtRemaining();
  }
}

// ---------- Быстрый ввод ----------
let LAST_VISIT_ITEMS = [];
// смена владельца машины (машину продали): KNOWN_OWNER — кто записан сейчас,
// NEW_OWNER — пользователь подтвердил, что вписывает нового владельца
let KNOWN_OWNER = null;
let NEW_OWNER = false;
let LAST_LOOKED_PLATE = '';  // номер, для которого карточка уже показана — не перерисовываем её зря

function startNewOwner() {
  NEW_OWNER = true;
  document.getElementById('owner_name').value = '';
  document.getElementById('owner_phone').value = '';
  const box = document.getElementById('kcPersonBox');
  if (box) box.innerHTML = `<div class="kc-new-owner-box"><b><i class="fa-solid fa-user-pen"></i> ${T.kc_new_owner_title}</b>${T.kc_new_owner_hint}<br><button type="button" onclick="lookupPlate(true)">${T.kc_new_owner_cancel}</button></div>`;
  const nameEl = document.getElementById('owner_name');
  nameEl.scrollIntoView({behavior: 'smooth', block: 'center'});
  setTimeout(() => nameEl.focus(), 300);
}

function repeatLastVisit() {
  // «Как в прошлый раз»: те же масло/фильтры/литры, цены — текущие со склада
  // (если товар есть на складе), иначе цена прошлого визита.
  const items = LAST_VISIT_ITEMS || [];
  if (!items.length) return;
  FLUID_KEYS.forEach((_, i) => {
    ['fluid_brand_', 'fluid_price_', 'fluid_liters_'].forEach(pfx => { const el = document.getElementById(pfx + i); if (el) el.value = ''; });
  });
  FILTER_KEYS.forEach((_, i) => {
    ['filter_brand_', 'filter_price_'].forEach(pfx => { const el = document.getElementById(pfx + i); if (el) el.value = ''; });
  });
  document.getElementById('other_name').value = '';
  document.getElementById('other_price').value = '';
  otherStockRows = [];
  renderOtherStockRows('other');

  const missing = [];
  const pickBrand = (el, it) => {
    if (!el) return null;
    if (el.tagName !== 'SELECT') { el.value = it.brand || ''; return null; }
    const opts = Array.from(el.options);
    let opt = it.product_id ? opts.find(o => o.value === String(it.product_id)) : null;
    if (!opt && it.brand) {
      const want = it.brand.trim().toUpperCase();
      opt = opts.find(o => (o.dataset.name || '').trim().toUpperCase() === want);
    }
    if (opt && opt.value) { el.value = opt.value; return opt; }
    if (it.brand) missing.push(it.brand);
    return null;
  };
  items.forEach(it => {
    const fi = FLUID_KEYS.indexOf(it.key);
    const fl = FILTER_KEYS.indexOf(it.key);
    // если марки больше нет на складе — строку не заполняем: иначе сохранилась
    // бы позиция без товара (не списалась бы со склада и выпала бы из прибыли)
    const isSelect = id => { const el = document.getElementById(id); return el && el.tagName === 'SELECT'; };
    if (fi >= 0) {
      const opt = pickBrand(document.getElementById(`fluid_brand_${fi}`), it);
      if (isSelect(`fluid_brand_${fi}`) && !opt) return;
      document.getElementById(`fluid_price_${fi}`).value = (opt && opt.dataset.price) || it.unit_price || '';
      document.getElementById(`fluid_liters_${fi}`).value = it.qty || '';
    } else if (fl >= 0) {
      const opt = pickBrand(document.getElementById(`filter_brand_${fl}`), it);
      if (isSelect(`filter_brand_${fl}`) && !opt) return;
      document.getElementById(`filter_price_${fl}`).value = (opt && opt.dataset.price) || it.unit_price || '';
    } else if (it.key === 'other') {
      document.getElementById('other_name').value = String(it.name || '').replace(/^[^:]+:\\s*/, '');
      document.getElementById('other_price').value = it.unit_price || it.total || '';
    }
  });
  const stockItems = items.filter(it => it.key === 'other_stock');
  if (stockItems.length) fillOtherStockRowsFrom('other', stockItems);
  paymentSplitTouched = false;
  updateTotal();
  if (missing.length) showMsg(`${T.kc_repeat_missing} ${missing.join(', ')}`, false);
  else showMsg(T.kc_repeat_done, true);
  const mileageEl = document.getElementById('mileage');
  if (mileageEl) { mileageEl.focus(); mileageEl.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}

// Следующая замена по пробегу: +5 тыс. / +8 тыс. / свой шаг. Выбор запоминается
// на этом телефоне. Если мастер сам поправил поле — больше его не перезаписываем.
const KM = { step: 0, custom: 0, manual: false };
try {
  KM.step = parseInt(localStorage.getItem('mb_km_step')) || 0;
  KM.custom = parseInt(localStorage.getItem('mb_km_custom')) || 0;
} catch (e) {}

function renderKmChips() {
  const el = document.getElementById('kmChips');
  if (!el) return;
  const opts = [5000, 8000];
  if (KM.custom && !opts.includes(KM.custom)) opts.push(KM.custom);
  el.innerHTML = opts.map(v => `<button type="button" class="km-chip ${KM.step === v ? 'on' : ''}" onclick="setKmStep(${v})">+${(v / 1000).toLocaleString('ru-RU')} ${T.km_thousand}</button>`).join('')
    + `<button type="button" class="km-chip" onclick="askKmStep()">${T.km_custom}</button>`;
}

function setKmStep(v, force) {
  KM.step = (KM.step === v && !force) ? 0 : v;
  try { localStorage.setItem('mb_km_step', KM.step); } catch (e) {}
  KM.manual = false;
  applyKmStep();
  renderKmChips();
}

function askKmStep() {
  const raw = prompt(T.km_prompt, KM.custom || 10000);
  if (raw === null) return;
  const v = parseInt(String(raw).replace(/\\D/g, ''));
  if (!(v > 0) || v > 100000) { showMsg(T.km_bad, false); return; }
  KM.custom = v;
  try { localStorage.setItem('mb_km_custom', v); } catch (e) {}
  setKmStep(v, true);
}

renderKmChips();

function applyKmStep() {
  if (!KM.step || KM.manual) return;
  const m = parseInt(document.getElementById('mileage').value);
  const next = document.getElementById('next_mileage');
  if (m > 0 && next) next.value = m + KM.step;
  applyDailyKm();
}

// Средний пробег в день → когда следующая замена. Пример: следующая замена
// через 5 000 км, машина проезжает 80 км в день → через 63 дня. Срок замены
// (поле «Интервал») выставляется сам в днях; если мастер поправил его вручную —
// больше не перезаписываем. Для знакомой машины пробег в день подставляется
// из прошлой замены или считается по прошлому визиту (пробег и дата).
const DK = { intervalManual: false, applied: false, last: null };

function dkDaysBetween(a, b) {
  const d1 = new Date(a + 'T00:00:00'), d2 = new Date(b + 'T00:00:00');
  return Math.round((d2 - d1) / 86400000);
}
function dkToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function dkFmtDate(d) {
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}
// пробег в день по прошлому визиту: (пробег сейчас − пробег тогда) / дни
function dkFromHistory() {
  const L = DK.last;
  const m = parseInt(document.getElementById('mileage').value);
  if (!L || !L.mileage || !L.date || !(m > L.mileage)) return null;
  const days = dkDaysBetween(String(L.date).slice(0, 10), dkToday());
  if (days < 7) return null;
  const v = Math.round((m - L.mileage) / days);
  return v >= 1 && v <= 2000 ? { km: v, days } : null;
}
function useDkSuggest(v) {
  document.getElementById('daily_km').value = v;
  DK.intervalManual = false;
  applyDailyKm();
}
function applyDailyKm() {
  const el = document.getElementById('daily_km');
  const hint = document.getElementById('dkHint');
  const sug = document.getElementById('dkSuggest');
  if (!el || !hint) return;
  const daily = parseInt(el.value);
  const s = dkFromHistory();
  sug.innerHTML = s && s.km !== daily
    ? `<button type="button" class="km-chip" onclick="useDkSuggest(${s.km})">${T.daily_km_hist} ~${s.km} ${T.km_per_day} · ${T.daily_km_use}</button>`
    : '';
  if (!(daily > 0)) {
    hint.textContent = '';
    if (DK.applied && !DK.intervalManual) {
      document.getElementById('interval_value').value = 3;
      document.getElementById('interval_unit').value = 'months';
    }
    DK.applied = false;
    return;
  }
  const m = parseInt(document.getElementById('mileage').value);
  const n = parseInt(document.getElementById('next_mileage').value);
  if (!(m > 0) || !(n > m)) { hint.textContent = T.daily_km_need; return; }
  const days = Math.min(730, Math.max(1, Math.round((n - m) / daily)));
  const d = new Date();
  d.setDate(d.getDate() + days);
  if (!DK.intervalManual) {
    document.getElementById('interval_value').value = days;
    document.getElementById('interval_unit').value = 'days';
    DK.applied = true;
  }
  hint.innerHTML = `${T.daily_km_next} <b>${dkFmtDate(d)}</b> — ${T.daily_km_in} ${days} ${T.daily_km_days} ` +
    `(${(n - m).toLocaleString('ru-RU')} ${T.km_short} ÷ ${daily} ${T.km_per_day})` +
    (DK.intervalManual ? `<br><span style="color:#B45309">${T.daily_km_manual}</span> <button type="button" class="km-chip" onclick="DK.intervalManual = false; applyDailyKm()">${T.daily_km_apply} ${days} ${T.daily_km_days}</button>` : '');
}
function resetDailyKm() {
  const el = document.getElementById('daily_km');
  if (el) el.value = '';
  DK.intervalManual = false;
  DK.applied = false;
  DK.last = null;
  const hint = document.getElementById('dkHint');
  if (hint) hint.textContent = '';
  const sug = document.getElementById('dkSuggest');
  if (sug) sug.innerHTML = '';
}

// Клавиатура телефона: цифровая для чисел, «Далее» переходит к следующему полю.
function tuneNumberInputs(root) {
  (root || document).querySelectorAll('input[type=number]:not([inputmode])').forEach(el => {
    const step = el.getAttribute('step') || '';
    el.setAttribute('inputmode', step.includes('.') ? 'decimal' : 'numeric');
  });
}
tuneNumberInputs();
new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) tuneNumberInputs(n); })))
  .observe(document.body, { childList: true, subtree: true });

document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.isComposing) return;
  const el = e.target;
  const form = document.getElementById('view-add');
  if (!form || !form.contains(el) || !['INPUT', 'SELECT'].includes(el.tagName) || el.type === 'checkbox') return;
  e.preventDefault();
  const fields = Array.from(form.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([disabled]), select:not([disabled]), textarea'))
    .filter(f => f.offsetParent !== null);
  const next = fields[fields.indexOf(el) + 1];
  if (next) next.focus(); else el.blur();
});

function resetItemInputs() {
  FLUID_KEYS.forEach((_, i) => {
    document.getElementById(`fluid_brand_${i}`).value = '';
    document.getElementById(`fluid_price_${i}`).value = '';
    document.getElementById(`fluid_liters_${i}`).value = '';
  });
  FILTER_KEYS.forEach((_, i) => {
    document.getElementById(`filter_price_${i}`).value = '';
    const fb = document.getElementById(`filter_brand_${i}`);
    if (fb) fb.value = '';
  });
  document.getElementById('other_name').value = '';
  document.getElementById('other_price').value = '';
  document.getElementById('knownClientPanel').innerHTML = '';
  otherStockRows = [];
  renderOtherStockRows('other');
  clearPick('main');
  ROW_OPEN = new Set(ROW_DEFAULT);
  updateTotal();
}

let plateSuggestLoading = false;

async function ensureCarsCacheLoaded() {
  if (carsCache.length || plateSuggestLoading) return;
  plateSuggestLoading = true;
  try {
    await fetchCars();
  } catch (e) { /* тихо — просто не будет подсказок в этот раз */ }
  plateSuggestLoading = false;
}

async function onPlateInput() {
  const plateEl = document.getElementById('plate');
  if (plateEl.value !== plateEl.value.toUpperCase()) {
    const pos = plateEl.selectionStart;
    plateEl.value = plateEl.value.toUpperCase();
    try { plateEl.setSelectionRange(pos, pos); } catch (e) {}
  }
  const val = plateEl.value.trim().toUpperCase();
  const dropdown = document.getElementById('plateSuggest');
  if (!val) { dropdown.style.display = 'none'; dropdown.innerHTML = ''; return; }
  await ensureCarsCacheLoaded();
  const matches = carsCache.filter(c => (c.plate_number || '').toUpperCase().includes(val)).slice(0, 8);
  if (!matches.length) { dropdown.style.display = 'none'; dropdown.innerHTML = ''; return; }
  dropdown.innerHTML = matches.map(c => `
    <div class="ps-item" onmousedown="selectPlateSuggestion(${escapeHtml(JSON.stringify(c.plate_number))})">
      <div class="ps-plate">${escapeHtml(c.plate_number)}</div>
      <div class="ps-owner">${escapeHtml(c.owner_name || '')}${c.car_brand ? ' · ' + escapeHtml(c.car_brand) + (c.car_model ? ' ' + escapeHtml(c.car_model) : '') : ''}</div>
    </div>
  `).join('');
  dropdown.style.display = '';
}

function selectPlateSuggestion(plate) {
  document.getElementById('plate').value = plate;
  document.getElementById('plateSuggest').style.display = 'none';
  lookupPlate();
}

function onPlateBlur() {
  setTimeout(() => {
    const dropdown = document.getElementById('plateSuggest');
    if (dropdown) dropdown.style.display = 'none';
  }, 150);
  lookupPlate();
}

async function lookupPlate(force) {
  const plate = document.getElementById('plate').value.trim();
  const panel = document.getElementById('knownClientPanel');
  // тот же номер — карточка уже на экране; не перерисовываем (иначе уход
  // курсора из поля номера сбрасывал бы, например, режим «новый владелец»)
  if (!force && plate && plate === LAST_LOOKED_PLATE) return;
  LAST_LOOKED_PLATE = plate;
  KNOWN_OWNER = null;
  NEW_OWNER = false;
  if (!plate) { panel.innerHTML = ''; lastKnownNextMileage = null; DK.last = null; applyDailyKm(); checkMileageVsDue(); return; }
  try {
    const res = await fetch('/api/history/' + encodeURIComponent(plate));
    const data = await res.json();

    const crossHtml = renderCrossNetworkHistory(data.cross_history);

    if (!data.car) {
      panel.innerHTML = crossHtml;
      lastKnownNextMileage = null;
      DK.last = null;
      applyDailyKm();
      checkMileageVsDue();
      return;
    }

    document.getElementById('owner_name').value = data.car.owner_name || '';
    document.getElementById('owner_phone').value = data.car.owner_phone || '';
    KNOWN_OWNER = {name: (data.car.owner_name || '').trim(), phone: (data.car.owner_phone || '').trim()};
    if (data.car.car_brand) document.getElementById('car_brand').value = data.car.car_brand;
    document.getElementById('car_model').value = data.car.car_model || '';

    const name = data.car.owner_name || T.kc_no_name;
    const initials = name.trim().split(/\\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
    const carLine = [data.car.car_brand, data.car.car_model].filter(Boolean).join(' ');
    const metaParts = [data.car.owner_phone, carLine].filter(Boolean);

    const last = data.history[0];
    const visitCount = data.history.length;
    lastKnownNextMileage = last ? last.next_mileage : null;
    DK.last = last ? { mileage: last.mileage, date: last.change_date, daily_km: last.daily_km } : null;
    const dkEl = document.getElementById('daily_km');
    if (dkEl && !dkEl.value) {
      const prevDaily = (data.history || []).find(h => h.daily_km);
      if (prevDaily) dkEl.value = prevDaily.daily_km;
    }
    applyDailyKm();
    let lastItemsHtml = '';
    LAST_VISIT_ITEMS = [];
    if (last && last.items_json) {
      try {
        const items = JSON.parse(last.items_json);
        LAST_VISIT_ITEMS = Array.isArray(items) ? items : [];
        lastItemsHtml = '<div class="kc-lv-items">' + items.map(it =>
          `<div class="kc-lv-item"><span>${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + it.qty + ' ' + T.liters_ph : ''}</span><span>${it.total.toLocaleString('ru-RU')} ${T.currency}</span></div>`
        ).join('') + '</div>';
      } catch (e) { /* старая запись без items_json — просто не показываем разбивку */ }
    }
    const mileageParts = [];
    if (last && last.mileage) mileageParts.push(`${T.kc_last_mileage} ${last.mileage.toLocaleString('ru-RU')} ${T.km_short}`);
    if (last && last.next_mileage) mileageParts.push(`${T.kc_due_mileage} ${last.next_mileage.toLocaleString('ru-RU')} ${T.km_short}`);
    const lastVisitHtml = last ? `
      <div class="kc-last-visit">
        <div class="kc-lv-top">
          <div>
            <div class="kc-lv-service">${escapeHtml(last.service_type || T.history_service_fallback)}</div>
            <div class="kc-lv-date">${last.change_date}${visitCount > 1 ? ` · ${T.kc_visits_total} ${visitCount}` : ''}</div>
          </div>
          <div class="kc-lv-cost">${last.cost ? last.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</div>
        </div>
        ${mileageParts.length ? `<div class="kc-lv-mileage">${mileageParts.join(' · ')}</div>` : ''}
        ${lastItemsHtml}
        ${LAST_VISIT_ITEMS.length ? `<button type="button" class="kc-repeat" onclick="repeatLastVisit()"><i class="fa-solid fa-rotate-right"></i> ${T.kc_repeat}</button>` : ''}
      </div>
    ` : `<div class="kc-last-visit"><span style="color:var(--hint); font-size:13px;">${T.kc_no_history}</span></div>`;

    panel.innerHTML = `
      <div class="known-client">
        <div class="kc-header"><i class="fa-solid fa-circle-check"></i><span>${T.kc_found_title}</span></div>
        <div class="kc-body">
          <div id="kcPersonBox">
            <div class="kc-person">
              <div class="kc-avatar">${escapeHtml(initials)}</div>
              <div>
                <div class="kc-name">${escapeHtml(name)}</div>
                <div class="kc-meta">${escapeHtml(metaParts.join(' · '))}</div>
              </div>
            </div>
            <button type="button" class="kc-new-owner" onclick="startNewOwner()"><i class="fa-solid fa-user-pen"></i>${T.kc_new_owner_btn}</button>
          </div>
          <div class="kc-history-label">${T.kc_history_label}</div>
          ${lastVisitHtml}
          <button type="button" class="kc-action-btn" onclick="focusNextEntry()"><i class="fa-solid fa-plus"></i>${T.kc_add_service_btn}</button>
          <div class="kc-action-hint">${T.kc_add_service_hint}</div>
        </div>
      </div>
    ` + crossHtml;
  } catch (e) {
    LAST_LOOKED_PLATE = '';
    panel.innerHTML = '';
    lastKnownNextMileage = null;
    checkMileageVsDue();
  }
}

function renderCrossNetworkHistory(crossHistory) {
  if (!crossHistory || !crossHistory.length) return '';
  const entries = crossHistory.map(h => {
    let itemsHtml = '';
    if (h.items_json) {
      try {
        const items = JSON.parse(h.items_json);
        itemsHtml = '<div class="kc-lv-items">' + items.map(it =>
          `<div class="kc-lv-item"><span>${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + it.qty + ' ' + T.liters_ph : ''}</span></div>`
        ).join('') + '</div>';
      } catch (e) {}
    }
    return `
      <div class="cn-entry">
        <div class="cn-entry-top">
          <div>
            <div class="cn-entry-shop">${escapeHtml(h.shop_name || '—')}</div>
            <div class="cn-entry-date">${h.change_date}${h.mileage ? ' · ' + h.mileage.toLocaleString('ru-RU') + ' ' + T.km_short : ''}</div>
          </div>
        </div>
        ${itemsHtml}
      </div>
    `;
  }).join('');
  return `
    <div class="cross-network-card">
      <div class="cn-header"><i class="fa-solid fa-globe"></i><span>${T.cn_history_title}</span></div>
      <div class="cn-hint">${T.cn_history_hint}</div>
      ${entries}
    </div>
  `;
}

function focusNextEntry() {
  const mileage = document.getElementById('mileage');
  mileage.scrollIntoView({ behavior: 'smooth', block: 'center' });
  mileage.focus();
}

async function initItemForms() {
  if (WAREHOUSE_ENABLED) {
    try {
      const res = await fetch('/api/products');
      productsCache = await res.json();
    } catch (e) { /* остаёмся с пустым каталогом — поля просто будут текстовыми */ }
  }
  renderItemLists();
  renderSvcItemLists();
}
initItemForms();

async function submitCar() {
  const items = collectItems();
  const payCashEl = document.getElementById('pay_cash');
  const payCardEl = document.getElementById('pay_card');
  const debtEnabled = document.getElementById('debt_enabled') && document.getElementById('debt_enabled').checked;
  const payload = {
    plate: document.getElementById('plate').value.trim(),
    owner_name: document.getElementById('owner_name').value.trim(),
    owner_phone: document.getElementById('owner_phone').value.trim(),
    car_brand: document.getElementById('car_brand').value,
    car_model: document.getElementById('car_model').value.trim(),
    mileage: document.getElementById('mileage').value,
    next_mileage: document.getElementById('next_mileage').value,
    items: items,
    interval_value: document.getElementById('interval_value').value,
    interval_unit: document.getElementById('interval_unit').value,
    daily_km: (document.getElementById('daily_km') || {}).value || '',
    notes: document.getElementById('notes').value.trim(),
    cash_amount: payCashEl ? payCashEl.value : null,
    card_amount: payCardEl ? payCardEl.value : null,
  };
  if (debtEnabled) {
    const total = items.reduce((sum, i) => sum + i.total, 0);
    const cash = parseFloat(payCashEl.value) || 0;
    const card = parseFloat(payCardEl.value) || 0;
    payload.debt_amount = Math.max(0, Math.round(total - cash - card));
    payload.installment_amount = document.getElementById('debt_installment_amount').value;
    payload.interval_days = document.getElementById('debt_interval_days').value;
    if (payload.debt_amount > 0 && (!payload.installment_amount || !payload.interval_days)) {
      showMsg(T.debt_fill_required, false);
      return;
    }
  }
  if (!payload.plate || !payload.owner_name || !payload.interval_value) {
    showMsg(T.msg_fill_required, false);
    return;
  }
  // имя/телефон известной машины изменили, но «Новый владелец» не нажали —
  // спрашиваем, иначе изменения молча терялись, а замена шла старому владельцу
  if (KNOWN_OWNER && !NEW_OWNER) {
    const nameChanged = payload.owner_name && payload.owner_name !== KNOWN_OWNER.name;
    const phoneChanged = payload.owner_phone && payload.owner_phone !== KNOWN_OWNER.phone;
    if ((nameChanged || phoneChanged) && confirm(T.kc_owner_changed_confirm)) NEW_OWNER = true;
  }
  payload.new_owner = NEW_OWNER;
  const res = await fetch('/api/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(`✅ ${T.msg_saved} ${data.next_date || '—'}.`, true);
    ['plate','owner_name','owner_phone','car_model','mileage','next_mileage','notes'].forEach(id => document.getElementById(id).value = '');
    KM.manual = false;
    KNOWN_OWNER = null;
    NEW_OWNER = false;
    LAST_LOOKED_PLATE = '';
    LAST_VISIT_ITEMS = [];
    resetItemInputs();
    document.getElementById('interval_value').value = 3;
    document.getElementById('interval_unit').value = 'months';
    paymentSplitTouched = false;
    resetDailyKm();
    setPayMode('cash');
    const payCash = document.getElementById('pay_cash');
    const payCard = document.getElementById('pay_card');
    if (payCash) payCash.value = '';
    if (payCard) payCard.value = '';
    const debtCheckbox = document.getElementById('debt_enabled');
    if (debtCheckbox) {
      debtCheckbox.checked = false;
      document.getElementById('debtFields').style.display = 'none';
      document.getElementById('debt_installment_amount').value = '';
      document.getElementById('debt_interval_days').value = '';
    }
    lastKnownNextMileage = null;
    document.getElementById('mileageCompare').innerHTML = '';
    document.getElementById('knownClientPanel').innerHTML = '';
    if (data.client_link) {
      openModal(payload.plate, data.client_link, payload.owner_phone);
    }
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

// «База»: сначала сразу показываем то, что уже есть на телефоне, потом
// тихо сверяемся с сервером — если ничего не поменялось, он отвечает
// пустым 204 и ничего не скачивается.
let CARS_VER = '';
let carsLoadSeq = 0;
function setCarsData(data, ver) {
  carsCache = data;
  CARS_VER = ver || '';
  CARS_CLIENTS = null;
}
async function fetchCars() {
  const seq = ++carsLoadSeq;
  const res = await fetch('/api/cars' + (CARS_VER && carsCache.length ? '?v=' + encodeURIComponent(CARS_VER) : ''));
  if (seq !== carsLoadSeq) return false;
  if (res.status === 204) return false;
  const data = await res.json();
  if (seq !== carsLoadSeq || !Array.isArray(data)) return false;
  setCarsData(data, res.headers.get('X-Data-Version'));
  return true;
}
async function loadCars() {
  if (carsCache.length) renderTable(true);
  else document.getElementById('table-body').innerHTML = `<div class="hint-text" style="text-align:center; padding:24px;">${T.history_loading}</div>`;
  if (await fetchCars()) renderTable(true);
}

async function loadDebts() {
  const debts = await (await fetch('/api/debts')).json();
  const list = document.getElementById('debtsList');
  if (!debts.length) { list.innerHTML = `<div class="hint-text" style="text-align:center; padding:24px;">${T.debts_empty}</div>`; return; }
  list.innerHTML = debts.map(d => `
    <div class="debt-card ${d.is_overdue ? 'overdue' : ''}">
      <div class="dc-top">
        <div>
          <div class="dc-owner">${escapeHtml(d.owner_name || T.kc_no_name)}</div>
          <div class="dc-meta">${escapeHtml(d.plate_number)}${d.owner_phone ? ' · ' + escapeHtml(d.owner_phone) : ''}</div>
        </div>
        <div>
          <div class="dc-remaining">${d.remaining.toLocaleString('ru-RU')} ${T.currency}</div>
          <div class="dc-due ${d.is_overdue ? 'overdue-text' : ''}">${d.is_overdue ? T.debt_overdue : T.debt_next_due} ${d.next_due_date}</div>
        </div>
      </div>
      <div class="dc-pay-row">
        <input id="debt_pay_${d.id}" type="number" placeholder="${T.debt_pay_placeholder}" style="flex:1;">
        <button class="badge active" style="flex:none;" onclick="payDebt(${d.id})">${T.debt_pay_btn}</button>
      </div>
    </div>
  `).join('');
}

async function payDebt(planId) {
  const input = document.getElementById(`debt_pay_${planId}`);
  const amount = input.value;
  if (!amount || parseFloat(amount) <= 0) { showMsg(T.debt_pay_invalid, false); return; }
  const res = await fetch(`/api/debts/${planId}/pay`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.debt_pay_success, true);
    loadDebts();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

let expenseCategoriesCache = [];

async function loadExpenseCategoryOptions(selectId) {
  if (!expenseCategoriesCache.length) {
    expenseCategoriesCache = await (await fetch('/api/expenses/categories')).json();
  }
  const select = document.getElementById(selectId);
  if (!select) return;
  select.innerHTML = expenseCategoriesCache.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('')
    + `<option value="__custom__">${T.expense_custom_category_option}</option>`;
}

function onExpenseCategoryChange(selectId, customInputId) {
  const select = document.getElementById(selectId);
  const customInput = document.getElementById(customInputId);
  const isCustom = select.value === '__custom__';
  customInput.style.display = isCustom ? 'block' : 'none';
  if (isCustom) customInput.focus();
}

function getSelectedCategory(selectId, customInputId) {
  const select = document.getElementById(selectId);
  if (select.value === '__custom__') {
    return document.getElementById(customInputId).value.trim();
  }
  return select.value;
}

async function loadExpensesTab() {
  await loadExpenseCategoryOptions('exp_category');
  await loadExpenseCategoryOptions('rec_category');
  loadRecurringExpenses();
  loadExpensesJournal();
}

async function submitExpense() {
  const category = getSelectedCategory('exp_category', 'exp_category_custom');
  const name = document.getElementById('exp_name').value.trim();
  const amount = document.getElementById('exp_amount').value;
  if (!category || !amount) { showMsg(T.msg_fill_required, false); return; }
  const res = await fetch('/api/expenses', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, name, amount}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_saved, true);
    document.getElementById('exp_name').value = '';
    document.getElementById('exp_amount').value = '';
    document.getElementById('exp_category_custom').value = '';
    document.getElementById('exp_amount_usd').value = '';
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function loadRecurringExpenses() {
  const list = await (await fetch('/api/recurring_expenses')).json();
  const el = document.getElementById('recurringExpensesList');
  if (!el) return;
  const today = new Date().toISOString().slice(0, 10);
  el.innerHTML = list.length ? list.map(r => `
    <div class="recur-exp-card ${r.next_due_date < today ? 'overdue' : ''}">
      <div class="rec-top">
        <div>
          <div class="rec-name">${escapeHtml(r.name || r.category)}</div>
          <div class="rec-meta">${escapeHtml(r.category)} · ${T.expense_next_due} ${r.next_due_date}</div>
        </div>
        <div class="rec-amount">${r.amount.toLocaleString('ru-RU')} ${T.currency}</div>
      </div>
      <div class="rec-actions">
        <button class="badge active" style="flex:1;" onclick="payRecurringExpense(${r.id})">${T.expense_mark_paid_btn}</button>
        <button class="badge inactive" style="flex:none;" onclick="deleteRecurringExpenseBtn(${r.id})">${T.entry_delete}</button>
      </div>
    </div>
  `).join('') : `<div class="hint-text">${T.expense_no_recurring}</div>`;
}

async function createRecurringExpense() {
  const category = getSelectedCategory('rec_category', 'rec_category_custom');
  const name = document.getElementById('rec_name').value.trim();
  const amount = document.getElementById('rec_amount').value;
  const day_of_month = document.getElementById('rec_day').value;
  if (!category || !amount || !day_of_month) { showMsg(T.msg_fill_required, false); return; }
  const res = await fetch('/api/recurring_expenses', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, name, amount, day_of_month}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_recurring_created, true);
    document.getElementById('rec_name').value = '';
    document.getElementById('rec_amount').value = '';
    document.getElementById('rec_day').value = '';
    document.getElementById('rec_category_custom').value = '';
    document.getElementById('rec_amount_usd').value = '';
    loadRecurringExpenses();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function payRecurringExpense(id) {
  const res = await fetch(`/api/recurring_expenses/${id}/pay`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_mark_paid_success, true);
    loadRecurringExpenses();
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteRecurringExpenseBtn(id) {
  if (!confirm(T.expense_delete_recurring_confirm)) return;
  const res = await fetch(`/api/recurring_expenses/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.entry_deleted, true);
    loadRecurringExpenses();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

let journalCache = [];

async function loadExpensesJournal() {
  journalCache = await (await fetch('/api/expenses')).json();
  const el = document.getElementById('expensesJournal');
  if (!el) return;
  el.innerHTML = journalCache.length ? journalCache.slice(0, 30).map(e => `
    <div>
      <div class="journal-row">
        <div>
          <div class="jr-cat">${escapeHtml(e.name || e.category)}</div>
          <div class="jr-meta">${escapeHtml(e.category)} · ${e.expense_date}</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <div class="jr-amount">−${e.amount.toLocaleString('ru-RU')} ${T.currency}</div>
          <button type="button" class="jr-icon-btn" onclick="toggleExpenseEditForm(${e.id})" title="${T.entry_edit}"><i class="fa-solid fa-pen"></i></button>
          <button type="button" class="jr-icon-btn" style="color:#B3241C;" onclick="deleteExpenseEntry(${e.id})" title="${T.entry_delete}"><i class="fa-solid fa-trash"></i></button>
        </div>
      </div>
      <div id="jredit-${e.id}" class="jr-edit-form" style="display:none;"></div>
    </div>
  `).join('') : `<div class="hint-text">${T.dash_no_data}</div>`;
}

async function toggleExpenseEditForm(id) {
  const panel = document.getElementById('jredit-' + id);
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  document.querySelectorAll('.jr-edit-form').forEach(el => { if (el !== panel) el.style.display = 'none'; });
  if (isOpen) { panel.style.display = 'none'; return; }
  const entry = journalCache.find(e => e.id === id);
  if (!entry) return;
  const catSelId = `jr_cat_${id}`, catCustomId = `jr_cat_custom_${id}`;
  await loadExpenseCategoryOptions(catSelId);
  const select = document.getElementById(catSelId);
  const isKnown = expenseCategoriesCache.includes(entry.category);
  panel.innerHTML = `
    <div class="field">
      <label>${T.expense_category_label}</label>
      <select id="${catSelId}" onchange="onExpenseCategoryChange('${catSelId}', '${catCustomId}')"></select>
      <input id="${catCustomId}" placeholder="${T.expense_custom_category_ph}" style="display:none; margin-top:6px;" value="${isKnown ? '' : escapeHtml(entry.category)}">
    </div>
    <div class="field">
      <label>${T.expense_name_label}</label>
      <input id="jr_name_${id}" value="${escapeHtml(entry.name || '')}">
    </div>
    <div class="row2">
      <div class="field">
        <label>${T.expense_amount_label}</label>
        <input id="jr_amount_${id}" type="number" value="${entry.amount}">
      </div>
      <div class="field">
        <label>${T.expense_date_label}</label>
        <input id="jr_date_${id}" type="date" value="${entry.expense_date}">
      </div>
    </div>
    <button class="submit" onclick="saveExpenseEdit(${id})">${T.btn_save}</button>
  `;
  await loadExpenseCategoryOptions(catSelId);
  const selectEl = document.getElementById(catSelId);
  if (isKnown) {
    selectEl.value = entry.category;
  } else {
    selectEl.value = '__custom__';
    onExpenseCategoryChange(catSelId, catCustomId);
  }
  panel.style.display = 'block';
}

async function saveExpenseEdit(id) {
  const category = getSelectedCategory(`jr_cat_${id}`, `jr_cat_custom_${id}`);
  const name = document.getElementById(`jr_name_${id}`).value.trim();
  const amount = document.getElementById(`jr_amount_${id}`).value;
  const expense_date = document.getElementById(`jr_date_${id}`).value;
  if (!category || !amount) { showMsg(T.msg_fill_required, false); return; }
  const res = await fetch(`/api/expenses/${id}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, name, amount, expense_date}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_saved, true);
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteExpenseEntry(id) {
  if (!confirm(T.expense_delete_entry_confirm)) return;
  const res = await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.entry_deleted, true);
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function toggleSearchClearBtn() {
  const btn = document.getElementById('searchClearBtn');
  if (!btn) return;
  btn.style.display = document.getElementById('search').value ? 'block' : 'none';
}

function clearSearch() {
  document.getElementById('search').value = '';
  toggleSearchClearBtn();
  BASE_SHOWN = BASE_PAGE;
  renderTable();
}

// Защита от автозаполнения: браузер (Chrome/Яндекс) иногда вставляет
// сохранённый логин (например «admin») в поле поиска базы. Принимаем
// только то, что человек сам набрал/вставил; остальное стираем.
function guardBaseSearchAutofill() {
  const s = document.getElementById('search');
  if (!s || s.dataset.afGuard) return;
  s.dataset.afGuard = '1';
  let typed = false;
  const mark = () => { typed = true; };
  s.addEventListener('beforeinput', mark);
  s.addEventListener('keydown', mark);
  s.addEventListener('paste', mark);
  s.addEventListener('input', (e) => {
    if (!typed && s.value) {
      e.stopImmediatePropagation();
      s.value = '';
      toggleSearchClearBtn();
      BASE_SHOWN = BASE_PAGE;
      renderTable();
    }
    typed = false;
  }, true);
  const wipe = () => {
    if (document.activeElement !== s && s.value && !typed) {
      s.value = '';
      toggleSearchClearBtn();
    }
  };
  setTimeout(wipe, 300);
  setTimeout(wipe, 1500);
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', guardBaseSearchAutofill);
} else {
  guardBaseSearchAutofill();
}

// Показываем по 50 карточек — раньше рисовались сразу все (2 500 карточек
// на каждую букву поиска), и на простом телефоне поиск «тормозил».
const BASE_PAGE = 50;
let BASE_SHOWN = BASE_PAGE;
let CARS_CLIENTS = null;
let baseSearchTimer = null;
function normSearch(v) { return String(v || '').toLowerCase().split(' ').join(''); }
function carSearchKey(c) {
  if (c._k === undefined) c._k = normSearch([c.plate_number, c.owner_name, c.owner_phone, c.car_brand, c.car_model].join(''));
  return c._k;
}
function onBaseSearch() {
  clearTimeout(baseSearchTimer);
  baseSearchTimer = setTimeout(() => { BASE_SHOWN = BASE_PAGE; renderTable(); }, 200);
}
function showMoreCars() {
  BASE_SHOWN += 100;
  renderTable(true);
}

function renderTable(keepPanel) {
  const q = normSearch(document.getElementById('search').value);
  if (!keepPanel && openHistoryRow !== null) {
    const panel = document.getElementById('clientCardPanel');
    panel.style.display = 'none';
    panel.innerHTML = '';
    openHistoryRow = null;
  }
  const countEl = document.getElementById('baseClientCount');
  if (CARS_CLIENTS === null) CARS_CLIENTS = new Set(carsCache.map(c => c.client_id)).size;
  const rows = q ? carsCache.filter(c => carSearchKey(c).includes(q)) : carsCache;
  if (countEl) {
    countEl.textContent = `${T.base_total_clients} ${CARS_CLIENTS} · ${T.base_total_cars} ${carsCache.length}` + (q ? ` · ${T.base_found} ${rows.length}` : '');
  }
  const shown = rows.length > BASE_SHOWN ? rows.slice(0, BASE_SHOWN) : rows;
  const more = rows.length - shown.length;
  document.getElementById('table-body').innerHTML = shown.length ? shown.map((c, i) => `
    <div class="car-card" onclick="toggleHistory(${escapeHtml(JSON.stringify(c.plate_number))})">
      <div class="cc-top">
        <span class="cc-plate">${escapeHtml(c.plate_number)}</span>
        ${c.telegram_id
            ? `<span class="badge linked cc-linkbtn">${T.badge_linked}</span>`
            : `<button class="badge unlinked cc-linkbtn" onclick="event.stopPropagation(); openModal(${escapeHtml(JSON.stringify(c.plate_number))}, ${escapeHtml(JSON.stringify(clientLink(c.link_token)))}, ${escapeHtml(JSON.stringify(c.owner_phone || ''))})">${T.badge_unlinked_btn}</button>`}
      </div>
      <div class="cc-owner">${escapeHtml(c.owner_name || T.kc_no_name)}</div>
      <div class="cc-meta">${escapeHtml([c.owner_phone, [c.car_brand, c.car_model].filter(Boolean).join(' ')].filter(Boolean).join(' · '))}</div>
      <div class="cc-bottom">
        <div>
          <div class="cc-cost">${c.cost ? c.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</div>
          <div class="cc-cost-date">${c.change_date || '—'}</div>
        </div>
        <div class="cc-next">${T.th_next_change}<br>${c.next_change_date || '—'}</div>
        <i class="fa-solid fa-chevron-right cc-chevron"></i>
      </div>
    </div>
  `).join('') + (more > 0 ? `<button type="button" class="base-more" onclick="showMoreCars()">${T.base_show_more} (${more})</button>` : '')
    : `<div class="hint-text" style="text-align:center; padding:20px;">${T.table_empty}</div>`;
}

async function toggleHistory(plate) {
  const panel = document.getElementById('clientCardPanel');
  if (openHistoryRow === plate) {
    panel.style.display = 'none';
    panel.innerHTML = '';
    openHistoryRow = null;
    return;
  }
  openHistoryRow = plate;
  panel.style.display = '';
  panel.innerHTML = T.history_loading;
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const res = await fetch('/api/history/' + encodeURIComponent(plate));
  const data = await res.json();
  // пока шёл ответ, могли открыть другого клиента — тогда этот ответ уже не нужен
  if (openHistoryRow !== plate) return;
  const history = data.history || [];
  historyDataCache[plate] = history;
  const body = panel;

  const car = data.car || {};
  const name = car.owner_name || T.kc_no_name;
  const initials = name.trim().split(/\\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
  const carLine = [car.car_brand, car.car_model].filter(Boolean).join(' ');
  const metaParts = [car.owner_phone, carLine].filter(Boolean);

  const entriesHtml = history.length ? history.map(h => {
    let itemsHtml = '';
    if (h.items_json) {
      try {
        const items = JSON.parse(h.items_json);
        itemsHtml = '<div class="kc-he-items">' + items.map(it =>
          `${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + it.qty + ' ' + T.liters_ph : ''}: ${it.total.toLocaleString('ru-RU')} ${T.currency}`
        ).join('<br>') + '</div>';
      } catch (e) { /* старая запись без items_json */ }
    }
    return `
    <div class="kc-hist-entry" id="hist-entry-${h.id}">
      <div class="kc-he-top">
        <div>
          <div class="kc-he-service">${escapeHtml(h.service_type || T.history_service_fallback)}</div>
          <div class="kc-he-date">${h.change_date} · ${T.history_mileage_label} ${h.mileage || '—'} км</div>
        </div>
        <div class="kc-he-cost">${h.cost ? h.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</div>
      </div>
      <div class="kc-he-meta">${T.history_next_mileage_label} ${h.next_mileage || '—'} км · ${T.history_next_label} ${h.next_change_date || '—'}</div>
      ${itemsHtml}
      ${h.notes ? `<div class="kc-he-notes">${T.history_notes_label} ${escapeHtml(h.notes)}</div>` : ''}
      <div class="kc-he-actions">
        <button class="history-toggle" onclick="openEditModalById(${h.id}, ${escapeHtml(JSON.stringify(plate))})">${T.entry_edit}</button>
        &nbsp;·&nbsp;
        <button class="history-toggle" style="color:#B3241C;" onclick="deleteEntry(${h.id}, ${escapeHtml(JSON.stringify(plate))})">${T.entry_delete}</button>
      </div>
    </div>
  `;
  }).join('') : `<div class="kc-hist-entry" style="color:var(--hint); text-align:center;">${T.history_empty}</div>`;

  body.innerHTML = `
    <div class="known-client">
      <div class="kc-header"><i class="fa-solid fa-user"></i><span>${T.kc_history_card_title}</span></div>
      <div class="kc-body">
        <div class="kc-person">
          <div class="kc-avatar">${escapeHtml(initials)}</div>
          <div>
            <div class="kc-name">${escapeHtml(name)}</div>
            <div class="kc-meta">${escapeHtml(metaParts.join(' · '))}</div>
          </div>
        </div>
        <button type="button" class="kc-action-btn" onclick="openAddServiceModal(${escapeHtml(JSON.stringify(plate))})"><i class="fa-solid fa-plus"></i>${T.kc_add_service_btn}</button>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button type="button" class="history-toggle" style="flex:1;" onclick="sharePassport(${escapeHtml(JSON.stringify(car.passport_token || ''))})"><i class="fa-solid fa-shield-halved"></i> ${T.kc_passport_btn}</button>
        </div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button type="button" class="history-toggle" style="flex:1;" onclick="toggleCarEditForm()">${T.kc_edit_car_btn}</button>
          <button type="button" class="history-toggle" style="flex:1; color:#B3241C;" onclick="deleteCarCompletely(${escapeHtml(JSON.stringify(plate))})">${T.kc_delete_car_btn}</button>
        </div>
        <div id="carEditForm" style="display:none; margin-top:10px; padding:12px; background:var(--field-bg); border-radius:10px;">
          <div class="field">
            <label style="font-size:11px;">${T.field_plate}</label>
            <input id="edit_car_plate" value="${escapeHtml(plate)}">
          </div>
          <div class="field">
            <label style="font-size:11px;">${T.field_owner_name}</label>
            <input id="edit_car_owner_name" value="${escapeHtml(name)}">
          </div>
          <div class="field">
            <label style="font-size:11px;">${T.field_owner_phone}</label>
            <input id="edit_car_owner_phone" value="${escapeHtml(car.owner_phone || '')}">
          </div>
          <div class="row2">
            <div class="field">
              <label style="font-size:11px;">${T.field_car_brand}</label>
              <input id="edit_car_brand" value="${escapeHtml(car.car_brand || '')}">
            </div>
            <div class="field">
              <label style="font-size:11px;">${T.field_car_model}</label>
              <input id="edit_car_model" value="${escapeHtml(car.car_model || '')}">
            </div>
          </div>
          <label style="display:flex; gap:8px; align-items:flex-start; font-size:12px; line-height:1.35; margin:2px 0 10px; color:var(--hint); cursor:pointer;">
            <input type="checkbox" id="edit_car_new_owner" style="width:auto; margin-top:2px; flex:none;">
            <span>${T.edit_new_owner_label}</span>
          </label>
          <button type="button" class="submit" onclick="saveCarEdit(${escapeHtml(JSON.stringify(plate))})">${T.btn_save}</button>
        </div>
        <div class="kc-hist-list">
          <div class="kc-history-label">${T.kc_full_history_label} (${history.length})</div>
          ${entriesHtml}
        </div>
      </div>
    </div>
  `;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function sharePassport(token) {
  if (!token) { showMsg(T.kc_passport_no_token, false); return; }
  const link = window.location.origin + '/passport/' + token;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(() => {
      showMsg(T.kc_passport_copied, true);
    }).catch(() => {});
  }
  window.open(link, '_blank');
}

function openModal(plate, link, phone) {
  if (!link) { showMsg(T.modal_no_bot_username, false); return; }
  document.getElementById('modalPlate').textContent = plate;
  document.getElementById('modalLink').textContent = link;
  document.getElementById('modalQr').src = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(link);
  const tgBtn = document.getElementById('modalTg');
  tgBtn.href = 'https://t.me/share/url?url=' + encodeURIComponent(link) + '&text=' + encodeURIComponent(T.share_text_tg);
  const waBtn = document.getElementById('modalWa');
  if (phone) {
    let digits = phone.replace(/\\D/g, '');
    if (digits && !digits.startsWith('998') && digits.length <= 9) digits = '998' + digits;
    const text = encodeURIComponent(T.share_text_wa + ' ' + link);
    waBtn.href = 'https://wa.me/' + digits + '?text=' + text;
    waBtn.style.display = 'block';
  } else {
    waBtn.style.display = 'none';
  }
  document.getElementById('linkModal').classList.add('open');
}

function closeModal() {
  document.getElementById('linkModal').classList.remove('open');
}

function copyLink() {
  const text = document.getElementById('modalLink').textContent;
  navigator.clipboard.writeText(text).then(() => showMsg(T.link_copied, true));
}

// ---- Единое модальное окно: и "изменить запись", и "внести новую замену уже известному клиенту" ----
let svcModal = { mode: null, id: null, plate: null };  // mode: 'edit' | 'add'

function renderSvcItemLists() {
  document.getElementById('svcFluidsList').innerHTML = FLUID_KEYS.map((key, i) => `
    <div class="item-row">
      <span class="item-name">${T[key]}</span>
      ${brandFieldHtml(key, `svc_fluid_brand_${i}`, `onSvcFluidProductPicked(${i})`)}
      <input id="svc_fluid_price_${i}" type="number" placeholder="${T.price_per_liter_ph}" oninput="updateSvcTotal()">
      <input id="svc_fluid_liters_${i}" type="number" step="0.1" placeholder="${T.liters_ph}" oninput="updateSvcTotal()">
    </div>
  `).join('');
  document.getElementById('svcFiltersList').innerHTML = FILTER_KEYS.map((key, i) => {
    const prods = productsForCategory(key);
    const brandField = prods.length ? brandFieldHtml(key, `svc_filter_brand_${i}`, `onSvcFilterProductPicked(${i})`) : '';
    return `
    <div class="item-row">
      <span class="item-name" style="flex:${prods.length ? '1.3' : '2.3'};">${T[key]}</span>
      ${brandField}
      <input id="svc_filter_price_${i}" type="number" placeholder="${T.price_ph}" oninput="updateSvcTotal()">
    </div>
  `;
  }).join('');
}

function onSvcFluidProductPicked(i) {
  const el = document.getElementById(`svc_fluid_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`svc_fluid_price_${i}`).value = opt.dataset.price;
  updateSvcTotal();
}

function onSvcFilterProductPicked(i) {
  const el = document.getElementById(`svc_filter_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`svc_filter_price_${i}`).value = opt.dataset.price;
  updateSvcTotal();
}

function collectSvcItems() {
  const items = [];
  FLUID_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`svc_fluid_price_${i}`).value) || 0;
    const liters = parseFloat(document.getElementById(`svc_fluid_liters_${i}`).value) || 0;
    if (price > 0 && liters > 0) {
      const { brand, product_id } = readBrandField(`svc_fluid_brand_${i}`);
      items.push({
        key, name: T[key], brand, product_id,
        unit_price: price, qty: liters, total: Math.round(price * liters),
      });
    }
  });
  FILTER_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`svc_filter_price_${i}`).value) || 0;
    if (price > 0) {
      const brandEl = document.getElementById(`svc_filter_brand_${i}`);
      const { brand, product_id } = brandEl ? readBrandField(`svc_filter_brand_${i}`) : { brand: null, product_id: null };
      items.push({key, name: T[key], brand, product_id, unit_price: price, qty: 1, total: Math.round(price)});
    }
  });
  const otherName = document.getElementById('svc_other_name').value.trim();
  const otherPrice = parseFloat(document.getElementById('svc_other_price').value) || 0;
  if (otherPrice > 0) {
    items.push({key: 'other', name: `${T.other_prefix}: ${otherName || T.other_unnamed}`, unit_price: otherPrice, qty: 1, total: Math.round(otherPrice)});
  }
  items.push(...collectOtherStockItems('svcOther'));
  return items;
}

let svcPaymentSplitTouched = false;

function updateSvcTotal() {
  const total = collectSvcItems().reduce((sum, i) => sum + i.total, 0);
  document.getElementById('svcTotalCost').textContent = total.toLocaleString('ru-RU') + ' ' + T.currency;
  const payCash = document.getElementById('svc_pay_cash');
  const payCard = document.getElementById('svc_pay_card');
  if (payCash && payCard && !svcPaymentSplitTouched) {
    payCash.value = total || '';
    payCard.value = '';
  }
}

function onSvcPayCashInput() {
  svcPaymentSplitTouched = true;
  const total = collectSvcItems().reduce((sum, i) => sum + i.total, 0);
  const cash = parseFloat(document.getElementById('svc_pay_cash').value) || 0;
  document.getElementById('svc_pay_card').value = Math.max(0, Math.round(total - cash));
}

function onSvcPayCardInput() {
  svcPaymentSplitTouched = true;
  const total = collectSvcItems().reduce((sum, i) => sum + i.total, 0);
  const card = parseFloat(document.getElementById('svc_pay_card').value) || 0;
  document.getElementById('svc_pay_cash').value = Math.max(0, Math.round(total - card));
}

function resetSvcItemInputs() {
  FLUID_KEYS.forEach((_, i) => {
    document.getElementById(`svc_fluid_brand_${i}`).value = '';
    document.getElementById(`svc_fluid_price_${i}`).value = '';
    document.getElementById(`svc_fluid_liters_${i}`).value = '';
  });
  FILTER_KEYS.forEach((_, i) => {
    document.getElementById(`svc_filter_price_${i}`).value = '';
    const brandEl = document.getElementById(`svc_filter_brand_${i}`);
    if (brandEl) brandEl.value = '';
  });
  document.getElementById('svc_other_name').value = '';
  document.getElementById('svc_other_price').value = '';
  svcOtherStockRows = [];
  renderOtherStockRows('svcOther');
  clearPick('svc');
  updateSvcTotal();
}

function fillSvcItemsFrom(items) {
  // подставляет уже сохранённые позиции в поля модалки (режим редактирования)
  const otherStockItems = [];
  (items || []).forEach(it => {
    if (!it.key) return;
    if (it.key === 'other') {
      const label = (it.name || '').replace(T.other_prefix + ': ', '');
      document.getElementById('svc_other_name').value = label === T.other_unnamed ? '' : label;
      document.getElementById('svc_other_price').value = it.total ?? '';
      return;
    }
    if (it.key === 'other_stock') {
      otherStockItems.push(it);
      return;
    }
    const fi = FLUID_KEYS.indexOf(it.key);
    if (fi !== -1) {
      const brandEl = document.getElementById(`svc_fluid_brand_${fi}`);
      selectOrPreserveBrand(brandEl, it);
      document.getElementById(`svc_fluid_price_${fi}`).value = it.unit_price ?? '';
      document.getElementById(`svc_fluid_liters_${fi}`).value = it.qty ?? '';
      return;
    }
    const filI = FILTER_KEYS.indexOf(it.key);
    if (filI !== -1) {
      const brandEl = document.getElementById(`svc_filter_brand_${filI}`);
      if (brandEl) selectOrPreserveBrand(brandEl, it);
      document.getElementById(`svc_filter_price_${filI}`).value = it.total ?? '';
    }
  });
  fillOtherStockRowsFrom('svcOther', otherStockItems);
}

function openEditModalById(id, plate) {
  const entry = (historyDataCache[plate] || []).find(h => h.id === id);
  if (!entry) { showMsg(T.msg_error + ' запись не найдена в кэше, обновите список', false); return; }
  openEditModal(plate, entry);
}

function openEditModal(plate, entry) {
  svcModal = { mode: 'edit', id: entry.id, plate };
  document.getElementById('svcModalTitle').textContent = T.entry_edit_title;
  document.getElementById('edit_mileage').value = entry.mileage ?? '';
  document.getElementById('edit_next_mileage').value = entry.next_mileage ?? '';
  document.getElementById('edit_interval_value').value = entry.interval_months ?? '';
  document.getElementById('edit_interval_unit').value = entry.interval_unit || 'months';
  document.getElementById('edit_notes').value = entry.notes || '';
  resetSvcItemInputs();
  if (entry.items_json) {
    try { fillSvcItemsFrom(JSON.parse(entry.items_json)); } catch (e) {}
  }
  updateSvcTotal();
  document.getElementById('svc_pay_cash').value = entry.cash_amount ?? entry.cost ?? '';
  document.getElementById('svc_pay_card').value = entry.card_amount ?? '';
  svcPaymentSplitTouched = true;  // это реальная сохранённая разбивка, не пересчитывать автоматически
  document.getElementById('editModal').classList.add('open');
}

function openAddServiceModal(plate) {
  svcModal = { mode: 'add', id: null, plate };
  document.getElementById('svcModalTitle').textContent = T.add_service_title;
  document.getElementById('edit_mileage').value = '';
  document.getElementById('edit_next_mileage').value = '';
  document.getElementById('edit_interval_value').value = 3;
  document.getElementById('edit_interval_unit').value = 'months';
  document.getElementById('edit_notes').value = '';
  svcPaymentSplitTouched = false;
  document.getElementById('svc_pay_cash').value = '';
  document.getElementById('svc_pay_card').value = '';
  resetSvcItemInputs();
  document.getElementById('editModal').classList.add('open');
}

function closeEditModal() {
  document.getElementById('editModal').classList.remove('open');
}

async function saveEdit() {
  const items = collectSvcItems();
  const mileage = document.getElementById('edit_mileage').value || null;
  const next_mileage = document.getElementById('edit_next_mileage').value || null;
  const interval_value = document.getElementById('edit_interval_value').value || null;
  const interval_unit = document.getElementById('edit_interval_unit').value;
  const notes = document.getElementById('edit_notes').value;
  const cash_amount = document.getElementById('svc_pay_cash').value || null;
  const card_amount = document.getElementById('svc_pay_card').value || null;

  let res;
  if (svcModal.mode === 'edit') {
    res = await fetch('/api/oil_change/' + svcModal.id, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ mileage, next_mileage, interval_value, interval_unit, notes, items, cash_amount, card_amount }),
    });
  } else {
    const carRow = carsCache.find(c => c.plate_number === svcModal.plate);
    res = await fetch('/api/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        plate: svcModal.plate, owner_name: carRow ? carRow.owner_name : '', mileage, next_mileage,
        interval_value, interval_unit, notes, items, cash_amount, card_amount,
      }),
    });
  }
  const data = await res.json();
  if (data.ok) {
    closeEditModal();
    showMsg(svcModal.mode === 'edit' ? T.entry_saved : T.service_added, true);
    openHistoryRow = null;  // чтобы toggleHistory ниже заново открыл панель со свежими данными, а не закрыл её
    toggleHistory(svcModal.plate);
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function toggleCarEditForm() {
  const form = document.getElementById('carEditForm');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function saveCarEdit(oldPlate) {
  const payload = {
    plate: document.getElementById('edit_car_plate').value.trim(),
    owner_name: document.getElementById('edit_car_owner_name').value.trim(),
    owner_phone: document.getElementById('edit_car_owner_phone').value.trim(),
    car_brand: document.getElementById('edit_car_brand').value.trim(),
    car_model: document.getElementById('edit_car_model').value.trim(),
    new_owner: !!(document.getElementById('edit_car_new_owner') && document.getElementById('edit_car_new_owner').checked),
  };
  if (!payload.plate || !payload.owner_name) {
    showMsg(T.msg_fill_required, false);
    return;
  }
  const res = await fetch('/api/car/' + encodeURIComponent(oldPlate), {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.kc_car_saved, true);
    openHistoryRow = null;
    toggleHistory(data.plate);
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteCarCompletely(plate) {
  if (!confirm(T.kc_delete_car_confirm.replace('{plate}', plate))) return;
  const res = await fetch('/api/car/' + encodeURIComponent(plate), { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.kc_car_deleted, true);
    document.getElementById('clientCardPanel').style.display = 'none';
    document.getElementById('clientCardPanel').innerHTML = '';
    openHistoryRow = null;
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteEntry(id, plate) {
  if (!confirm(T.entry_delete_confirm)) return;
  const res = await fetch('/api/oil_change/' + id, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.entry_deleted, true);
    openHistoryRow = null;
    toggleHistory(plate);
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

// Защита от двойного нажатия: пока действие выполняется (запрос на сервер),
// повторные нажатия той же кнопки игнорируются — иначе на медленном
// интернете можно случайно дважды внести замену, списать товар или оплату.
function guardOnce(names) {
  names.forEach(name => {
    const fn = window[name];
    if (typeof fn !== 'function' || fn.__guarded) return;
    let busy = false;
    const wrapped = async function (...args) {
      if (busy) return;
      busy = true;
      // нажатая кнопка тускнеет, пока ждём сервер — на слабом интернете
      // видно, что нажатие принято и запрос идёт
      const ev = window.event;
      const btn = ev && ev.currentTarget && ev.currentTarget.tagName === 'BUTTON' ? ev.currentTarget : null;
      const wasDisabled = btn ? btn.disabled : false;
      if (btn) { btn.disabled = true; btn.classList.add('net-busy'); }
      try { return await fn.apply(this, args); } finally {
        busy = false;
        if (btn) { btn.disabled = wasDisabled; btn.classList.remove('net-busy'); }
      }
    };
    wrapped.__guarded = true;
    window[name] = wrapped;
  });
}
guardOnce(['submitCar', 'saveEdit', 'saveCarEdit', 'deleteEntry', 'deleteCarCompletely',
  'payDebt', 'submitExpense', 'createRecurringExpense', 'payRecurringExpense', 'deleteRecurringExpenseBtn',
  'saveExpenseEdit', 'deleteExpenseEntry', 'sendBroadcast', 'saveSmsSettings', 'saveUsdRate',
  'createProduct', 'deleteProduct', 'submitRestock', 'submitEditProduct', 'submitTransfer', 'submitShip',
  'submitCatalog', 'applyImport', 'editBranchPrice',
  'saveSupplier', 'deleteSupplierBtn', 'saveSupplierProducts', 'saveOrderDraft', 'sendOrder', 'receiveFromDraft',
  'cancelOrderBtn', 'submitReceive', 'submitDistribute', 'keepAllOrder', 'sendOrderBot', 'unlinkSupplierTg', 'saveSupPayment', 'cancelSupPayment', 'restoreSupplier', 'saveOrderNewProduct',
  'createStaff', 'staffResetPw', 'staffToggle', 'staffDelete']);
</script>
</body>
</html>
"""

NET_GUARD_JS = """<style>
  #netBar { position: fixed; top: 0; left: 0; right: 0; height: 3px; z-index: 99999; pointer-events: none;
    background: linear-gradient(90deg, #0F52BA, #00A8E8, #0F52BA); background-size: 200% 100%;
    animation: netBarMove 1s linear infinite; display: none; }
  @keyframes netBarMove { from { background-position: 200% 0; } to { background-position: 0 0; } }
  #netOffline { position: fixed; top: 0; left: 0; right: 0; z-index: 99998; background: #B42318; color: #fff;
    text-align: center; font: 600 13px/1.2 system-ui, sans-serif; padding: 7px 10px calc(7px + env(safe-area-inset-top, 0px)); display: none; }
  #netToast { position: fixed; left: 0; right: 0; margin: 0 auto; width: fit-content; bottom: calc(86px + env(safe-area-inset-bottom, 0px));
    max-width: min(92vw, 460px); box-sizing: border-box; z-index: 99999; background: #1E293B; color: #fff; border-radius: 12px;
    padding: 12px 16px; font: 500 14px/1.35 system-ui, sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,.25); display: none; }
  #netToast.err { background: #B42318; }
  #netToast.ok { background: #1B8A5A; }
  button.net-busy { opacity: .55; cursor: wait !important; }
  .base-more { display: block; width: 100%; margin: 6px 0 14px; padding: 13px; border-radius: 12px; border: 1.5px dashed #94A3B8;
    background: transparent; color: #0F52BA; font-weight: 700; font-size: 14px; cursor: pointer; }
</style>
<script>
(function () {
  // Общий сетевой слой: таймаут, понятные сообщения при плохом интернете,
  // защита от дублей при повторном нажатии, реакция на истёкший вход.
  const NT = {
    offline: {{ T.net_offline|tojson }},
    timeout: {{ T.net_timeout|tojson }},
    unsure: {{ T.net_unsure|tojson }},
    server: {{ T.net_server|tojson }},
    session: {{ T.net_session|tojson }},
    bar: {{ T.net_offline_bar|tojson }},
    back: {{ T.net_back_online|tojson }}
  };
  const origFetch = window.fetch.bind(window);
  // ключ запроса хранится, только пока исход неизвестен (обрыв связи):
  // повторное нажатие с теми же данными уйдёт с тем же ключом, и сервер
  // вернёт прежний результат вместо второй записи
  const pendingKeys = {};
  let active = 0, barTimer = null, toastTimer = null, lastToast = '', lastToastAt = 0;

  function el(id, make) {
    let e = document.getElementById(id);
    if (!e && make && document.body) { e = document.createElement('div'); e.id = id; document.body.appendChild(e); }
    return e;
  }
  function setBusy(delta) {
    active = Math.max(0, active + delta);
    const bar = el('netBar', true);
    if (!bar) return;
    if (active > 0 && !barTimer && bar.style.display !== 'block') {
      barTimer = setTimeout(() => { barTimer = null; if (active > 0) bar.style.display = 'block'; }, 350);
    }
    if (active === 0) { if (barTimer) { clearTimeout(barTimer); barTimer = null; } bar.style.display = 'none'; }
  }
  function toast(text, kind, ms) {
    const now = Date.now();
    if (text === lastToast && now - lastToastAt < 4000) return;  // не дублировать одно и то же
    lastToast = text; lastToastAt = now;
    const t = el('netToast', true);
    if (!t) { alert(text); return; }
    t.className = kind || '';
    t.textContent = text;
    t.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.style.display = 'none'; }, ms || 6000);
  }
  window.netToast = toast;
  function rid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  }
  function netError(kind, msg, shown) {
    const e = new Error(msg); e.oilNet = kind; e.oilShown = !!shown; return e;
  }
  function jsonResponse(obj, status) {
    return new Response(JSON.stringify(obj), { status: status, headers: { 'Content-Type': 'application/json' } });
  }

  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const isApi = url.indexOf('/api/') === 0 || url.indexOf(location.origin + '/api/') === 0;
    if (!isApi) return origFetch(input, init);
    init = Object.assign({}, init || {});
    const method = (init.method || 'GET').toUpperCase();
    const write = method !== 'GET' && method !== 'HEAD';
    let key = null;
    if (write) {
      const headers = new Headers(init.headers || {});
      let id;
      if (typeof init.body === 'string' || init.body == null) {
        key = method + ' ' + url + ' ' + (init.body || '');
        id = pendingKeys[key] || rid();
        pendingKeys[key] = id;
      } else {
        id = rid();  // файл/форма — каждый раз новый запрос
      }
      headers.set('X-Request-Id', id);
      init.headers = headers;
    }
    const big = (typeof FormData !== 'undefined' && init.body instanceof FormData) || /backup|restore|import|export|statement/.test(url);
    const ms = big ? 180000 : (write ? 45000 : 30000);
    const ctrl = new AbortController();
    let timedOut = false, callerAborted = false;
    if (init.signal) {
      if (init.signal.aborted) { callerAborted = true; ctrl.abort(); }
      else init.signal.addEventListener('abort', () => { callerAborted = true; ctrl.abort(); });
    }
    init.signal = ctrl.signal;
    const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, ms);
    setBusy(1);
    let res;
    try {
      res = await origFetch(input, init);
    } catch (e) {
      if (callerAborted) throw e;
      const kind = timedOut ? 'timeout' : 'offline';
      if (write) {
        toast(NT.unsure, 'err', 9000);
        throw netError(kind, NT.unsure, true);
      }
      throw netError(kind, kind === 'timeout' ? NT.timeout : NT.offline, false);
    } finally {
      clearTimeout(timer);
      setBusy(-1);
    }
    if (key) delete pendingKeys[key];  // ответ получен — исход известен
    if (res.status === 401) {
      toast(NT.session, 'err', 4000);
      setTimeout(() => { location.href = '/login'; }, 1500);
      throw netError('session', NT.session, true);
    }
    if (res.status === 402) {
      // подписка закончилась, пока панель была открыта
      location.href = '/subscription';
      throw netError('session', NT.session, true);
    }
    const ct = res.headers.get('Content-Type') || '';
    if (!res.ok && ct.indexOf('json') === -1) {
      // сервер ответил не данными, а страницей ошибки
      if (write) return jsonResponse({ ok: false, error: NT.server + ' (' + res.status + ')' }, res.status);
      throw netError('server', NT.server, false);
    }
    return res;
  };

  window.addEventListener('unhandledrejection', (e) => {
    const r = e.reason;
    if (r && r.oilNet) {
      if (!r.oilShown) toast(r.message, 'err');
      e.preventDefault();
    }
  });

  function showOffline(on) {
    const b = el('netOffline', true);
    if (!b) return;
    b.textContent = NT.bar;
    b.style.display = on ? 'block' : 'none';
  }
  window.addEventListener('offline', () => showOffline(true));
  window.addEventListener('online', () => { showOffline(false); toast(NT.back, 'ok', 2500); });
  document.addEventListener('DOMContentLoaded', () => { if (navigator.onLine === false) showOffline(true); });
})();
</script>
"""

_SW_SNIPPET = "<script>\nif ('serviceWorker' in navigator) {"



# Сканер госномера камерой телефона (распознавание прямо в браузере)
PLATE_SCAN_HTML = r"""<style>
  .plate-wrap #plate { padding-right:58px; }
  .ps-cam-btn {
    position:absolute; right:5px; top:50%; transform:translateY(-50%); width:44px; height:36px; border:none; border-radius:10px;
    background:var(--btn); color:#fff; font-size:16px; display:flex; align-items:center; justify-content:center; cursor:pointer;
    box-shadow:0 3px 8px rgba(230,57,70,.35); padding:0;
  }
  .ps-cam-btn:active { transform:translateY(-50%) scale(.94); }
  #psOverlay { position:fixed; inset:0; z-index:9000; background:#0b0f16; display:none; overflow:hidden; touch-action:none; }
  #psOverlay.open { display:block; }
  #psVideo { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; background:#0b0f16; }
  #psFrame { position:absolute; left:50%; transform:translateX(-50%); border-radius:12px; box-shadow:0 0 0 200vmax rgba(0,0,0,.5); }
  #psFrame b { position:absolute; width:26px; height:26px; border:4px solid #22d3ee; }
  #psFrame .a { left:-2px; top:-2px; border-right:0; border-bottom:0; border-radius:12px 0 0 0; }
  #psFrame .b { right:-2px; top:-2px; border-left:0; border-bottom:0; border-radius:0 12px 0 0; }
  #psFrame .c { left:-2px; bottom:-2px; border-right:0; border-top:0; border-radius:0 0 0 12px; }
  #psFrame .d { right:-2px; bottom:-2px; border-left:0; border-top:0; border-radius:0 0 12px 0; }
  #psFrame .ps-line { position:absolute; left:8px; right:8px; top:50%; height:2px; background:#22d3ee; box-shadow:0 0 12px #22d3ee; animation:psLine 1.6s ease-in-out infinite; }
  @keyframes psLine { 0%,100% { top:15%; } 50% { top:85%; } }
  #psFrame.ps-hit b { border-color:#34d399; }
  .ps-top { position:absolute; top:0; left:0; right:0; padding:calc(14px + env(safe-area-inset-top, 0px)) 14px 14px; color:#fff; display:flex; justify-content:space-between; align-items:center; font-weight:700; font-size:15px; }
  .ps-ib { width:40px; height:40px; border-radius:50%; background:rgba(255,255,255,.16); color:#fff; border:none; display:flex; align-items:center; justify-content:center; font-size:17px; cursor:pointer; }
  .ps-ib.on { background:#facc15; color:#111; }
  .ps-ib[hidden] { visibility:hidden; display:flex; }
  #psHint { position:absolute; left:16px; right:16px; text-align:center; color:#fff; font-size:14px; font-weight:600; text-shadow:0 1px 3px rgba(0,0,0,.6); }
  #psStatus { position:absolute; left:16px; right:16px; text-align:center; }
  #psStatus span { display:inline-block; background:rgba(34,211,238,.18); color:#a5f3fc; border:1px solid rgba(34,211,238,.4); font-size:13px; padding:7px 14px; border-radius:20px; font-weight:600; max-width:100%; }
  #psStatus.err span { background:rgba(239,68,68,.2); color:#fecaca; border-color:rgba(239,68,68,.5); }
  .ps-bottom { position:absolute; left:0; right:0; bottom:calc(22px + env(safe-area-inset-bottom, 0px)); text-align:center; }
  .ps-manual { background:none; border:none; color:#fff; font-size:14px; text-decoration:underline; opacity:.85; cursor:pointer; padding:8px; font-family:inherit; }
  .ps-priv { color:#cbd5e1; font-size:12px; margin-top:8px; }
  #psSheet { position:absolute; left:0; right:0; bottom:0; background:var(--card, #fff); color:var(--text); border-radius:22px 22px 0 0; padding:14px 16px calc(20px + env(safe-area-inset-bottom, 0px)); box-shadow:0 -8px 24px rgba(0,0,0,.3); display:none; max-width:560px; margin:0 auto; }
  #psOverlay.result #psSheet { display:block; }
  #psOverlay.result #psVideo { filter:blur(4px) brightness(.6); }
  #psOverlay.result #psFrame, #psOverlay.result #psHint, #psOverlay.result #psStatus, #psOverlay.result .ps-bottom { display:none; }
  .ps-grab { width:40px; height:4px; border-radius:2px; background:#cbd5e1; margin:0 auto 12px; }
  .ps-lbl { font-size:11px; color:var(--hint); font-weight:700; text-transform:uppercase; letter-spacing:.5px; }
  .ps-plate-row { display:flex; align-items:center; gap:8px; margin:4px 0 12px; }
  .ps-plate { font-family:var(--font-mono); font-weight:700; font-size:24px; letter-spacing:1.5px; white-space:nowrap; }
  .ps-plate-input { font-family:var(--font-mono); font-weight:700; font-size:20px; letter-spacing:1px; text-transform:uppercase; flex:1; min-width:0; }
  .ps-edit { margin-left:auto; background:none; border:none; color:var(--blue); font-weight:700; font-size:13px; cursor:pointer; white-space:nowrap; font-family:inherit; }
  .ps-match { border-radius:14px; padding:11px 12px; display:flex; gap:10px; align-items:center; margin-bottom:12px; }
  .ps-match.ok { background:var(--ok-bg); border:1.5px solid #a7f3d0; }
  .ps-match.w { background:#FFFBEB; border:1.5px solid #fde68a; }
  .ps-match.n { background:var(--field-bg); border:1.5px solid var(--border); }
  .ps-av { width:40px; height:40px; border-radius:50%; background:var(--blue); color:#fff; font-weight:800; display:flex; align-items:center; justify-content:center; font-size:14px; flex:none; }
  .ps-match.w .ps-av { background:#B45309; }
  .ps-match.n .ps-av { background:#94A3B8; }
  .ps-tag { font-size:10.5px; font-weight:800; margin-bottom:3px; }
  .ps-match.ok .ps-tag { color:var(--ok); } .ps-match.w .ps-tag { color:#B45309; } .ps-match.n .ps-tag { color:var(--hint); }
  .ps-mt { font-size:14px; font-weight:700; }
  .ps-mt.mono { font-family:var(--font-mono); letter-spacing:1px; }
  .ps-ms { font-size:12px; color:#64748b; margin-top:2px; }
  .ps-alt { font-size:12.5px; color:#64748b; margin:-4px 0 12px; }
  .ps-alt b { font-family:var(--font-mono); color:var(--text); }
  .ps-btns { display:flex; gap:8px; }
  .ps-bt { flex:1; border-radius:12px; padding:13px; text-align:center; font-weight:800; font-size:14px; border:none; cursor:pointer; font-family:inherit; }
  .ps-bt.p { background:var(--btn); color:#fff; }
  .ps-bt.s { background:var(--field-bg); color:var(--text); border:1.5px solid var(--border); }
  .ps-lock { text-align:center; font-size:11px; color:var(--hint); margin-top:10px; }
</style>

<div id="psOverlay" role="dialog" aria-modal="true">
  <video id="psVideo" playsinline muted autoplay></video>
  <div id="psFrame"><b class="a"></b><b class="b"></b><b class="c"></b><b class="d"></b><div class="ps-line"></div></div>
  <div class="ps-top">
    <button type="button" class="ps-ib" onclick="closePlateScanner()" aria-label="close"><i class="fa-solid fa-xmark"></i></button>
    <div>{{ T.ps_title }}</div>
    <button type="button" class="ps-ib" id="psTorch" onclick="psToggleTorch()" hidden aria-label="{{ T.ps_torch }}"><i class="fa-solid fa-bolt"></i></button>
  </div>
  <div id="psHint">{{ T.ps_hint }}</div>
  <div id="psStatus"><span></span></div>
  <div class="ps-bottom">
    <button type="button" class="ps-manual" onclick="psManual()">{{ T.ps_manual }}</button>
    <div class="ps-priv"><i class="fa-solid fa-lock"></i> {{ T.ps_privacy }}</div>
  </div>
  <div id="psSheet"></div>
  <canvas id="psCanvas" width="128" height="64" style="display:none;"></canvas>
</div>

<script>
// ===== Сканер госномера =====
// Распознавание идёт прямо на телефоне (ONNX-модель в браузере): кадры с
// камеры никуда не отправляются и нигде не сохраняются, сервер только один
// раз отдаёт файлы модели (/ocr/v1/…), дальше они берутся из кэша.
// Формат узбекских номеров: 01 A 123 BC (физлица) и 01 123 ABC (юрлица).
const PS = { stream: null, track: null, session: null, loading: null, running: false, timer: null,
             hits: {}, startedAt: 0, result: null, torch: false, editing: false, gen: 0 };
const PS_ALPHA = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_';
const PS_FORMATS = ['DDLDDDLL', 'DDDDDLLL'];
const PS_REGIONS = ['01', '10', '20', '25', '30', '40', '50', '60', '70', '75', '80', '85', '90', '95'];
const PS_MIN_CONF = 0.55;     // кадр учитывается, если модель уверена хотя бы на столько
const PS_NEED_HITS = 2;       // сколько раз подряд должен прочитаться один и тот же номер
const PS_INSTANT_CONF = 0.97; // при такой уверенности хватает одного кадра
const PS_BASE_CONF = 0.5;     // для номера, который уже есть в базе, достаточно такой

function psLoadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error('load ' + src));
    document.head.appendChild(s);
  });
}

function psLoadModel() {
  if (PS.session) return Promise.resolve(PS.session);
  if (!PS.loading) {
    PS.loading = (async () => {
      if (!window.ort) await psLoadScript('/ocr/v1/ort.wasm.min.js');
      ort.env.wasm.wasmPaths = '/ocr/v1/';
      ort.env.wasm.numThreads = 1;
      const sess = await ort.InferenceSession.create('/ocr/v1/plate_ocr.onnx', { executionProviders: ['wasm'] });
      // «прогрев»: первый прогон всегда медленный — делаем его заранее
      try { await sess.run({ [sess.inputNames[0]]: new ort.Tensor('uint8', new Uint8Array(64 * 128 * 3), [1, 64, 128, 3]) }); } catch (e) {}
      PS.session = sess;
      return sess;
    })().catch(e => { PS.loading = null; throw e; });
  }
  return PS.loading;
}

function psSetStatus(text, isErr) {
  const st = document.getElementById('psStatus');
  st.classList.toggle('err', !!isErr);
  st.style.display = text ? '' : 'none';
  st.querySelector('span').textContent = text || '';
}

// рамка: ширина ~86% экрана (не больше 440px), пропорции как у номера с запасом
function psLayout() {
  const ov = document.getElementById('psOverlay');
  const W = ov.clientWidth, H = ov.clientHeight;
  const fw = Math.min(W * 0.86, 440), fh = Math.round(fw / 3.2);
  const top = Math.round(H * 0.42 - fh / 2);
  const fr = document.getElementById('psFrame');
  fr.style.width = Math.round(fw) + 'px'; fr.style.height = fh + 'px'; fr.style.top = top + 'px';
  document.getElementById('psHint').style.top = (top - 40) + 'px';
  document.getElementById('psStatus').style.top = (top + fh + 22) + 'px';
}

async function openPlateScanner() {
  const ov = document.getElementById('psOverlay');
  PS.gen++;
  PS.result = null; PS.editing = false; PS.hits = {};
  ov.classList.remove('result');
  ov.classList.add('open');
  document.body.style.overflow = 'hidden';
  document.getElementById('psFrame').classList.remove('ps-hit');
  document.getElementById('psHint').textContent = T.ps_hint;
  psLayout();
  ensureCarsCacheLoaded().then(psBuildPlateSet);
  psBuildPlateSet();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    psSetStatus(T.ps_no_camera, true);
    return;
  }
  psSetStatus(PS.session ? T.ps_scanning : T.ps_loading);
  const gen = PS.gen;
  const modelP = psLoadModel();
  try {
    await psStartCamera();
  } catch (e) {
    if (gen !== PS.gen) return;
    const denied = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
    psSetStatus(denied ? T.ps_denied : T.ps_no_camera, true);
    return;
  }
  try {
    await modelP;
  } catch (e) {
    if (gen !== PS.gen) return;
    psSetStatus(T.ps_load_fail, true);
    return;
  }
  if (gen !== PS.gen || !ov.classList.contains('open')) return;
  psSetStatus(T.ps_scanning);
  PS.running = true;
  PS.startedAt = Date.now();
  psTick(gen);
}

async function psStartCamera() {
  if (PS.stream) return;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    // без жёсткого разрешения: камера включается быстрее, а модели хватает
    // и обычного качества (номер всё равно ужимается до 128×64)
    video: { facingMode: { ideal: 'environment' } }
  });
  if (!document.getElementById('psOverlay').classList.contains('open')) {
    stream.getTracks().forEach(t => t.stop());
    return;
  }
  PS.stream = stream;
  PS.track = stream.getVideoTracks()[0] || null;
  const v = document.getElementById('psVideo');
  v.srcObject = stream;
  try { await v.play(); } catch (e) {}
  // фонарик — только если телефон умеет
  PS.torch = false;
  const tb = document.getElementById('psTorch');
  tb.classList.remove('on');
  let caps = {};
  try { caps = PS.track && PS.track.getCapabilities ? PS.track.getCapabilities() : {}; } catch (e) {}
  tb.hidden = !caps.torch;
}

function psBuildPlateSet() {
  PS.plateSet = new Set((carsCache || []).map(c => psNorm(c.plate_number)));
}

function psStopCamera() {
  PS.running = false;
  if (PS.timer) { clearTimeout(PS.timer); PS.timer = null; }
  if (PS.stream) PS.stream.getTracks().forEach(t => t.stop());
  PS.stream = null; PS.track = null;
  const v = document.getElementById('psVideo');
  if (v) v.srcObject = null;
}

async function psToggleTorch() {
  if (!PS.track) return;
  PS.torch = !PS.torch;
  try { await PS.track.applyConstraints({ advanced: [{ torch: PS.torch }] }); }
  catch (e) { PS.torch = false; }
  document.getElementById('psTorch').classList.toggle('on', PS.torch);
}

function closePlateScanner() {
  PS.gen++;
  psStopCamera();
  const ov = document.getElementById('psOverlay');
  ov.classList.remove('open', 'result');
  document.getElementById('psSheet').innerHTML = '';
  document.body.style.overflow = '';
}

function psManual() {
  closePlateScanner();
  const el = document.getElementById('plate');
  if (el) el.focus();
}

// часть кадра под рамкой → тензор 1×64×128×3 (uint8, RGB)
function psCropTensor(inset) {
  const v = document.getElementById('psVideo');
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return null;
  const ew = v.clientWidth, eh = v.clientHeight;
  const scale = Math.max(ew / vw, eh / vh);
  const offX = (vw * scale - ew) / 2, offY = (vh * scale - eh) / 2;
  const fr = document.getElementById('psFrame').getBoundingClientRect();
  const vr = v.getBoundingClientRect();
  let fx = fr.left - vr.left, fy = fr.top - vr.top, fw = fr.width, fh = fr.height;
  fx += fw * inset[0]; fw *= (1 - 2 * inset[0]);
  fy += fh * inset[1]; fh *= (1 - 2 * inset[1]);
  const sx = (fx + offX) / scale, sy = (fy + offY) / scale, sw = fw / scale, sh = fh / scale;
  const c = document.getElementById('psCanvas');
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(v, sx, sy, sw, sh, 0, 0, 128, 64);
  const px = ctx.getImageData(0, 0, 128, 64).data;
  const rgb = new Uint8Array(128 * 64 * 3);
  for (let i = 0, j = 0; i < px.length; i += 4, j += 3) { rgb[j] = px[i]; rgb[j + 1] = px[i + 1]; rgb[j + 2] = px[i + 2]; }
  return new ort.Tensor('uint8', rgb, [1, 64, 128, 3]);
}

// ответ модели: 10 позиций × 37 символов (вероятности). Подбираем лучший
// вариант, подходящий под узбекский формат номера.
function psDecode(probs) {
  const lp = (k, j) => Math.log(probs[k * 37 + j] + 1e-9);
  // код региона: 01, 10, 20 … 95 — остальные пары цифр сильно маловероятны
  let reg = null;
  for (let a = 0; a < 10; a++) for (let b = 0; b < 10; b++) {
    const code = String(a) + String(b);
    const sc = lp(0, a) + lp(1, b) - (PS_REGIONS.includes(code) ? 0 : 3);
    if (!reg || sc > reg.score) reg = { score: sc, code };
  }
  let best = null;
  for (const f of PS_FORMATS) {
    let score = reg.score, out = reg.code;
    for (let k = 2; k < 10; k++) {
      if (k >= f.length) { score += lp(k, 36); continue; }
      const lo = f[k] === 'D' ? 0 : 10, hi = f[k] === 'D' ? 10 : 36;
      let bj = lo;
      for (let j = lo + 1; j < hi; j++) if (probs[k * 37 + j] > probs[k * 37 + bj]) bj = j;
      score += lp(k, bj);
      out += PS_ALPHA[bj];
    }
    if (!best || score > best.score) best = { score, plate: out };
  }
  return { plate: best.plate, conf: Math.exp(best.score / 10) };
}

async function psRecognize() {
  const sess = PS.session;
  // по очереди: вся рамка / чуть плотнее (номер не всегда ровно на всю рамку) —
  // один прогон модели на кадр, чтобы кадры шли чаще
  PS.tickN = (PS.tickN || 0) + 1;
  const t = psCropTensor(PS.tickN % 2 ? [0, 0] : [0.06, 0.14]);
  if (!t) return null;
  const out = await sess.run({ [sess.inputNames[0]]: t });
  return psDecode(out[sess.outputNames[0]].data);
}

async function psTick(gen) {
  if (gen !== PS.gen || !PS.running) return;
  let r = null;
  try { r = await psRecognize(); } catch (e) { r = null; }
  if (gen !== PS.gen || !PS.running) return;
  if (r && r.conf >= PS_MIN_CONF) {
    PS.hits[r.plate] = (PS.hits[r.plate] || 0) + 1;
    document.getElementById('psFrame').classList.add('ps-hit');
    // номер уже есть в базе этой точки — хватает одного уверенного кадра
    const inBase = r.conf >= PS_BASE_CONF && PS.plateSet && PS.plateSet.has(r.plate);
    if (inBase || r.conf >= PS_INSTANT_CONF || PS.hits[r.plate] >= PS_NEED_HITS) {
      if (navigator.vibrate) { try { navigator.vibrate(60); } catch (e) {} }
      psShowResult(r.plate);
      return;
    }
  } else {
    document.getElementById('psFrame').classList.remove('ps-hit');
  }
  if (Date.now() - PS.startedAt > 8000) document.getElementById('psHint').textContent = T.ps_hint_slow;
  psNextFrame(gen);
}

// следующий кадр — сразу, как камера даст новый (без лишних пауз)
function psNextFrame(gen) {
  const v = document.getElementById('psVideo');
  if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(() => psTick(gen));
  else PS.timer = setTimeout(() => psTick(gen), 30);
}

// ---- результат ----
function psNorm(s) { return String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, ''); }
function psPretty(p) {
  p = psNorm(p);
  if (/^[0-9]{2}[A-Z][0-9]{3}[A-Z]{2}$/.test(p)) return p.slice(0, 2) + ' ' + p[2] + ' ' + p.slice(3, 6) + ' ' + p.slice(6);
  if (/^[0-9]{5}[A-Z]{3}$/.test(p)) return p.slice(0, 2) + ' ' + p.slice(2, 5) + ' ' + p.slice(5);
  return p;
}
function psDist(a, b) {
  if (Math.abs(a.length - b.length) > 1) return 9;
  const d = [];
  for (let i = 0; i <= a.length; i++) { d.push([i]); }
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}
function psFindCar(plate) {
  const p = psNorm(plate);
  if (!p) return { kind: 'none' };
  let near = null;
  for (const c of (carsCache || [])) {
    const cp = psNorm(c.plate_number);
    if (cp === p) return { kind: 'exact', car: c };
    if (!near && cp.length >= 6 && psDist(cp, p) === 1) near = c;
  }
  return near ? { kind: 'near', car: near } : { kind: 'none' };
}
function psInitials(name) {
  return String(name || '').trim().split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
}
function psDate(s) {
  const m = String(s || '').slice(0, 10).split('-');
  return m.length === 3 ? m[2] + '.' + m[1] + '.' + m[0] : '';
}
function psCarLine(c) {
  const parts = [[c.car_brand, c.car_model].filter(Boolean).join(' ')];
  const d = psDate(c.change_date);
  if (d) parts.push(T.ps_last + ' ' + d);
  return parts.filter(Boolean).join(' · ');
}

function psShowResult(plate) {
  psStopCamera();
  PS.result = psNorm(plate);
  PS.editing = false;
  document.getElementById('psOverlay').classList.add('result');
  psRenderSheet();
}

function psRenderSheet() {
  const sheet = document.getElementById('psSheet');
  const plate = PS.result;
  const m = psFindCar(plate);
  PS.match = m;
  const plateHtml = PS.editing
    ? `<input id="psPlateInput" class="ps-plate-input" value="${escapeHtml(plate)}" autocomplete="off" autocapitalize="characters" spellcheck="false" oninput="psOnEdit(this)">`
    : `<span class="ps-plate">${escapeHtml(psPretty(plate))}</span><button type="button" class="ps-edit" onclick="psStartEdit()"><i class="fa-solid fa-pen"></i> ${escapeHtml(T.ps_edit)}</button>`;
  sheet.innerHTML = `
    <div class="ps-grab"></div>
    <div class="ps-lbl">${escapeHtml(T.ps_recognized)}</div>
    <div class="ps-plate-row">${plateHtml}</div>
    <div id="psMatchBox">${psMatchHtml(m, plate)}</div>
    <div class="ps-lock"><i class="fa-solid fa-lock"></i> ${escapeHtml(T.ps_on_phone)}</div>`;
  if (PS.editing) {
    const inp = document.getElementById('psPlateInput');
    inp.focus();
    try { inp.setSelectionRange(inp.value.length, inp.value.length); } catch (e) {}
  }
}

function psMatchHtml(m, plate) {
  if (m.kind === 'exact') {
    const c = m.car;
    return `<div class="ps-match ok"><div class="ps-av">${escapeHtml(psInitials(c.owner_name))}</div><div style="min-width:0;">
        <div class="ps-tag"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(T.ps_in_base)}</div>
        <div class="ps-mt">${escapeHtml(c.owner_name || T.kc_no_name)}</div>
        <div class="ps-ms">${escapeHtml(psCarLine(c))}</div></div></div>
      <div class="ps-btns"><button type="button" class="ps-bt s" onclick="openPlateScanner()"><i class="fa-solid fa-rotate"></i> ${escapeHtml(T.ps_again)}</button>
        <button type="button" class="ps-bt p" onclick="psApply(PS.match.car.plate_number)">${escapeHtml(T.ps_use)}</button></div>`;
  }
  if (m.kind === 'near') {
    const c = m.car;
    return `<div class="ps-match w"><div class="ps-av">${escapeHtml(psInitials(c.owner_name))}</div><div style="min-width:0;">
        <div class="ps-tag"><i class="fa-solid fa-circle-question"></i> ${escapeHtml(T.ps_maybe)}</div>
        <div class="ps-mt mono">${escapeHtml(psPretty(c.plate_number))}</div>
        <div class="ps-ms">${escapeHtml([c.owner_name, [c.car_brand, c.car_model].filter(Boolean).join(' ')].filter(Boolean).join(' · '))}</div></div></div>
      <div class="ps-alt">${escapeHtml(T.ps_or_new)} <b>${escapeHtml(plate)}</b></div>
      <div class="ps-btns"><button type="button" class="ps-bt s" onclick="psApply(PS.result)">${escapeHtml(T.ps_new_btn)}</button>
        <button type="button" class="ps-bt p" onclick="psApply(PS.match.car.plate_number)">${escapeHtml(T.ps_its_him)}</button></div>`;
  }
  return `<div class="ps-match n"><div class="ps-av"><i class="fa-solid fa-plus"></i></div><div>
        <div class="ps-tag">${escapeHtml(T.ps_new)}</div>
        <div class="ps-ms">${escapeHtml(T.ps_new_hint)}</div></div></div>
      <div class="ps-btns"><button type="button" class="ps-bt s" onclick="openPlateScanner()"><i class="fa-solid fa-rotate"></i> ${escapeHtml(T.ps_again)}</button>
        <button type="button" class="ps-bt p" onclick="psApply(PS.result)">${escapeHtml(T.ps_use)}</button></div>`;
}

function psStartEdit() { PS.editing = true; psRenderSheet(); }
function psOnEdit(inp) {
  const v = psNorm(inp.value);
  if (inp.value !== v) inp.value = v;
  PS.result = v;
  PS.match = psFindCar(v);
  document.getElementById('psMatchBox').innerHTML = psMatchHtml(PS.match, v);
}

function psApply(plate) {
  const p = psNorm(plate);
  if (!p) return;
  closePlateScanner();
  const el = document.getElementById('plate');
  el.value = p;
  const dd = document.getElementById('plateSuggest');
  if (dd) { dd.style.display = 'none'; dd.innerHTML = ''; }
  lookupPlate(true);
}

// заранее, в фоне, загружаем распознавание — к нажатию 📷 оно уже готово
// (файлы берутся из кэша телефона, интернет тратится только первый раз)
window.addEventListener('load', () => {
  if (!document.getElementById('plate') || !navigator.mediaDevices) return;
  const go = () => psLoadModel().catch(() => {});
  setTimeout(() => (window.requestIdleCallback ? requestIdleCallback(go, { timeout: 4000 }) : go()), 2500);
});

window.addEventListener('resize', () => { if (document.getElementById('psOverlay').classList.contains('open')) psLayout(); });
document.addEventListener('visibilitychange', () => {
  // свернули приложение — камеру выключаем (батарея и приватность)
  if (document.hidden && PS.stream) closePlateScanner();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('psOverlay').classList.contains('open')) closePlateScanner();
});
</script>
"""

PAGE = PAGE + MODAL_AND_SCRIPT
PAGE = PAGE.replace("</body>", HELP_JS + "</body>", 1)
_ps_i = PAGE.rfind("</body>")
PAGE = PAGE[:_ps_i] + PLATE_SCAN_HTML + PAGE[_ps_i:]
assert PAGE.count(_SW_SNIPPET) == 1
PAGE = PAGE.replace(_SW_SNIPPET, NET_GUARD_JS + _SW_SNIPPET, 1)


@app.route("/")
@login_required
def index():
    import json as _json
    shop = db.get_shop(g.shop_id)
    return render_template_string(
        PAGE, brands=CAR_BRANDS, service_types=SERVICE_TYPES,
        shop_name=session.get("shop_name") or "Замена масла",
        T=g.T, lang=g.lang, t_json=_json.dumps(g.T, ensure_ascii=False), bot_username=BOT_USERNAME,
        sms_enabled=bool(shop.get("sms_enabled")) if shop else False,
        eskiz_email=(shop.get("eskiz_email") or "") if shop else "",
        warehouse_enabled=bool(shop.get("warehouse_enabled")) if shop else False,
        is_employee=g.is_employee,
        is_branch=g.is_branch,
        usd_rate=_effective_usd_rate(shop),
        usd_rate_own=shop.get("usd_rate") if shop else None,
        usd_rate_head=_head_usd_rate(shop),
        sub_banner=_sub_banner(shop),
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


def _course_max() -> int:
    return COURSE_EMPLOYEE_MAX if g.is_employee else len(COURSE_MODULES)


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


@app.route("/course/<int:n>")
@login_required
def course_page(n):
    if n < 1 or n > _course_max():
        return redirect("/?tab=course")
    path = os.path.join(COURSE_DIR, "modul-%d.html" % n)
    if not os.path.isfile(path):
        return redirect("/?tab=course")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    labels = json.dumps({"back": g.T["tab_course"], "next": g.T["course_next"], "map": g.T["course_to_map"]})
    hook = _COURSE_HOOK % (n, _course_max(), labels)
    i = html.rfind("</body>")
    html = html[:i] + hook + html[i:] if i != -1 else html + hook
    return Response(html, mimetype="text/html")


@app.route("/api/course")
@login_required
def api_course():
    prog = db.course_progress(g.shop_id, _course_user_key())
    mods = []
    for n, title, mins in COURSE_MODULES[:_course_max()]:
        p = prog.get(n) or {}
        mods.append({"n": n, "title": title, "mins": mins, "opened": bool(p.get("opened")),
                     "best": p.get("best"), "passed": bool(p.get("passed"))})
    return jsonify({"ok": True, "modules": mods})


@app.route("/api/course/progress", methods=["POST"])
@login_required
def api_course_progress():
    data = request.get_json(silent=True) or {}
    try:
        n = int(data.get("module"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "module"}), 400
    if n < 1 or n > _course_max():
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
    """Свой курс точки; у филиала без своего курса — курс главной точки."""
    if not shop:
        return None
    return shop.get("usd_rate") or _head_usd_rate(shop)


@app.route("/api/usd_rate", methods=["POST"])
@login_required
@employee_blocked
def api_set_usd_rate():
    """Курс доллара точки. Филиал тоже может задать свой (для цен продажи и
    расходов в $); пустое значение у филиала = снова брать курс главной точки."""
    data = request.get_json(force=True)
    try:
        rate = float(data.get("rate")) if data.get("rate") not in (None, "") else None
        if rate is not None and rate <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "укажите положительное число"}), 400
    db.set_shop_usd_rate(g.shop_id, rate)
    shop = db.get_shop(g.shop_id)
    return jsonify({"ok": True, "rate": rate, "effective": _effective_usd_rate(shop),
                    "head_rate": _head_usd_rate(shop)})




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


@app.route("/api/oil_change/<int:oc_id>", methods=["PUT"])
@login_required
def api_update_oil_change(oc_id):
    data = request.get_json(force=True)
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
        )
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not ok:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
    return jsonify({"ok": True})


@app.route("/api/oil_change/<int:oc_id>", methods=["DELETE"])
@login_required
def api_delete_oil_change(oc_id):
    ok = db.delete_oil_change(oc_id, g.shop_id)
    if not ok:
        return jsonify({"ok": False, "error": "запись не найдена"}), 404
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
def api_delete_car(plate):
    """Полное удаление машины — сама машина, вся её история, связанные
    долги. Клиент (владелец) остаётся, если у него есть другие машины."""
    ok = db.delete_car_completely(g.shop_id, plate)
    if not ok:
        return jsonify({"ok": False, "error": "машина не найдена"}), 404
    return jsonify({"ok": True})


def _send_service_receipt(shop, plate, items, cash_amount, card_amount, next_date):
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
        mileage = int(data["mileage"]) if data.get("mileage") else None
        next_mileage = int(data["next_mileage"]) if data.get("next_mileage") else None
        items = data.get("items") or []
        interval_value = int(data["interval_value"])
        interval_unit = data.get("interval_unit") or "months"
        if interval_unit not in ("days", "months"):
            interval_unit = "months"
        notes = data.get("notes") or ""
        cash_amount = int(data["cash_amount"]) if data.get("cash_amount") not in (None, "") else None
        card_amount = int(data["card_amount"]) if data.get("card_amount") not in (None, "") else None
        debt_amount = int(data["debt_amount"]) if data.get("debt_amount") not in (None, "") else 0
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
        with db.WRITE_LOCK:
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
                car_id = db.create_or_update_car(g.shop_id, plate, client_id, car_brand, car_model)
            else:
                client = db.get_or_create_client(g.shop_id, owner_name, owner_phone)
                client_id = client["id"]
                car_id = db.create_or_update_car(g.shop_id, plate, client_id, car_brand, car_model)

            oc_id, next_date = db.add_oil_change(
                car_id, mileage, None, None, False, None, interval_value, interval_unit, notes,
                next_mileage=next_mileage, items=items, cash_amount=cash_amount, card_amount=card_amount
            )
            if daily_km:
                try:
                    db.set_oil_change_daily_km(oc_id, daily_km)
                except Exception as e:  # не критично: замена уже сохранена
                    logger.warning(f"не удалось сохранить пробег в день: {e}")

            if debt_amount > 0:
                db.create_installment_plan(g.shop_id, car_id, debt_amount, installment_amount, interval_days, oil_change_id=oc_id)

        car_after, _ = db.get_car_history(g.shop_id, plate)
        link = None
        if car_after and not car_after["telegram_id"]:
            link = _client_link(car_after["link_token"])
        elif car_after and car_after["telegram_id"]:
            shop = db.get_shop(g.shop_id)
            if shop:
                shop["_receipt_telegram_id"] = car_after["telegram_id"]
                _send_service_receipt(shop, plate, items, cash_amount, card_amount, next_date)

        return jsonify({"ok": True, "next_date": next_date, "client_link": link})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/debts")
@login_required
def api_list_debts():
    return jsonify(db.get_active_debts(g.shop_id))


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
    plan = db.log_installment_payment(plan_id, g.shop_id, amount, data.get("paid_date"))
    if not plan:
        return jsonify({"ok": False, "error": "долг не найден"}), 404
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


@app.route("/api/broadcast", methods=["POST"])
@login_required
def api_broadcast_create():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "empty message"}), 400
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
        result["expenses"] = expenses
        result["net_profit"] = pb["profit"] - expenses
    return jsonify(result)


@app.route("/api/sms_settings", methods=["POST"])
@login_required
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


@app.route("/api/products")
@login_required
def api_list_products():
    products = db.list_products(g.shop_id)
    if g.is_employee or g.is_branch:
        for p in products:
            p.pop("purchase_price", None)
    return jsonify(products)


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
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    product = db.create_product(g.shop_id, category, name, unit, sell_price, purchase_price, initial_stock)
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
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "неверные данные"}), 400
    ok, err = db.update_product(product_id, shop_id, name=name, sell_price=sell_price,
                                purchase_price=purchase_price, clear_purchase_price=clear_purchase)
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
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
        if g.is_branch:
            purchase_price = None  # филиал не вписывает цену закупки при пополнении — только главный аккаунт
        restock_date = data.get("restock_date") or None
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    ok = db.restock_product(product_id, g.shop_id, quantity, purchase_price, restock_date)
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
        restock_date = data.get("restock_date") or None
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "неверные данные"}), 400
    ok = db.restock_product(product_id, branch_id, quantity, purchase_price, restock_date)
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
    wb = load_workbook(file_storage, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
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
    return jsonify(db.get_profit_stats(g.shop_id))


@app.route("/api/export")
@login_required
@employee_blocked
def api_export():
    import json
    data = db.export_shop_data(g.shop_id)
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

ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OilBook — админ-панель</title>
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&display=swap"></noscript>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"></noscript>
<style>
  :root {
    --bg:#F1F5F9; --text:#1E293B; --hint:#94A3B8; --btn:#E63946; --btn-text:#FFFFFF; --blue:#0F52BA; --darkblue:#0A2540; --cyan:#00A8E8;
    --card:#FFFFFF; --border:#E2E8F0; --field-bg:#F4F7FA; --ok:#059669; --ok-bg:#ECFDF5; --danger:#B3241C; --danger-bg:#FDECEA;
    --font-display:'Space Grotesk', sans-serif; --font-body:'Plus Jakarta Sans', -apple-system, sans-serif; --font-mono:'IBM Plex Mono', monospace;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: var(--font-body); }
  .speedline { height:6px; width:100%; background: linear-gradient(90deg, var(--blue) 0%, var(--blue) 33%, #fff 33%, #fff 38%, var(--btn) 38%, var(--btn) 70%, #fff 70%, #fff 75%, var(--cyan) 75%, var(--cyan) 100%); }
  .container { padding: 12px; max-width: 900px; margin: 0 auto; }
  .topbar { display:flex; justify-content:space-between; align-items:center; margin: 14px 0 16px; }
  .logo-badge {
    display:inline-flex; align-items:center; justify-content:center; width:40px; height:40px;
    background:var(--darkblue); color:var(--cyan); border-radius:12px; transform:rotate(-8deg);
    box-shadow:0 4px 10px rgba(10,37,64,.25); font-size:16px; flex:none;
  }
  h1 { font-family: var(--font-display); font-weight:800; font-style:italic; letter-spacing:-0.3px; font-size: 20px; margin: 0; line-height:1.1; color:var(--darkblue); }
  .logo-sub { font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:var(--hint); }
  .brand-line { text-transform:none; letter-spacing:0; font-size:12px; display:flex; align-items:baseline; gap:4px; flex-wrap:wrap; margin-top:2px; }
  .brand-line .role-tag { font-size:11px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }
  .wordmark { font-family:'Sora', var(--font-display), sans-serif; font-style:normal; font-weight:800; font-size:17px; letter-spacing:-0.4px; line-height:1; white-space:nowrap; }
  .wordmark .wm-oil { background:linear-gradient(135deg, #0EA5E9 0%, #1D4ED8 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .wordmark .wm-book { color:#0B1B3A; }
  .logout { color: var(--btn); font-size: 12px; font-weight:700; text-decoration:none; background:var(--danger-bg); padding:6px 10px; border-radius:10px; }
  .card { background: #fff; border:2px solid #DBEAFE; border-radius: 22px; padding: 16px; margin-bottom: 16px; box-shadow: 0 10px 25px -5px rgba(15,82,186,.08); }
  .field { margin-bottom: 10px; }
  .row2 { display:flex; gap:10px; }
  .row2 .field { flex:1; }
  label { display:block; font-size: 12px; color: var(--hint); margin-bottom: 4px; text-transform:uppercase; letter-spacing:0.4px; }
  input { width: 100%; padding: 10px; border-radius: 10px; border: 1.5px solid var(--border); background: var(--field-bg); color: var(--text); font-size: 15px; font-family: var(--font-body); }
  input:focus { outline:none; border-color: var(--blue); box-shadow:0 0 0 3px rgba(15,82,186,.12); }
  button.submit { width: 100%; padding: 14px; border: none; border-radius: 14px; background: linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #312E81 100%); color:#fff; font-size: 15px; font-weight: 700; font-family: var(--font-display); letter-spacing:0.5px; text-transform:uppercase; cursor: pointer; margin-top: 6px; box-shadow: 0 8px 18px rgba(29,78,216,.30); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color:#fff; background:#1E293B; font-weight: 700; font-size:10px; text-transform:uppercase; letter-spacing:0.4px; }
  .badge { display:inline-block; padding: 3px 9px; border-radius: 20px; font-size: 11px; font-weight:600; cursor:pointer; border:none; text-transform:uppercase; letter-spacing:0.3px; }
  .badge.active { background: var(--ok-bg); color: var(--ok); }
  .badge.inactive { background: var(--danger-bg); color: var(--danger); }
  .hint-text { color: var(--hint); font-size: 12px; margin-top: 6px; }
  .msg { padding: 12px; border-radius: 10px; margin-bottom: 10px; font-size: 14px; }
  .msg.ok { background:var(--ok-bg); color:var(--ok); }
  .msg.err { background:var(--danger-bg); color:var(--danger); }
  .new-creds { background:var(--field-bg); border:1px dashed var(--blue); border-radius:10px; padding:10px; font-size:13px; margin-top:10px; font-family: var(--font-mono); }
  .adm-stats { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin-bottom:14px; }
  .adm-stat { background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 12px; }
  .adm-stat b { display:block; font-family:var(--font-display); font-size:22px; color:var(--darkblue); line-height:1.1; }
  .adm-stat span { font-size:11.5px; color:#64748B; }
  details.adm-sec { background:#fff; border:1px solid var(--border); border-radius:16px; margin-bottom:10px; overflow:hidden; }
  details.adm-sec > summary { list-style:none; cursor:pointer; display:flex; align-items:center; gap:12px; padding:14px 16px; font-weight:700; font-size:15px; color:var(--text); -webkit-tap-highlight-color:transparent; }
  details.adm-sec > summary::-webkit-details-marker { display:none; }
  details.adm-sec > summary .ic { width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:15px; flex:none; }
  details.adm-sec > summary .sub { display:block; font-size:12px; font-weight:500; color:#64748B; margin-top:1px; }
  details.adm-sec > summary .chev { margin-left:auto; color:#94A3B8; transition:transform .2s; }
  details.adm-sec[open] > summary .chev { transform:rotate(180deg); }
  details.adm-sec[open] > summary { border-bottom:1px solid #F1F5F9; }
  details.adm-sec .sec-body { padding:14px 16px 16px; }
  details.adm-sec.danger { border-color:#FCA5A5; }
  .list-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:22px 0 10px; }
  .list-head h2 { font-family:var(--font-display); font-size:18px; margin:0; color:var(--darkblue); }
  .adm-filters { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0 12px; }
  .adm-filters button { border:1px solid var(--border); background:#fff; border-radius:999px; padding:6px 12px; font-size:12.5px; font-weight:600; color:#475569; cursor:pointer; font-family:inherit; }
  .adm-filters button.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .grp-title { font-weight:800; color:var(--blue); font-size:13px; margin:16px 2px 8px; }
  .shop-card { background:#fff; border:1px solid var(--border); border-radius:16px; padding:14px; margin-bottom:10px; }
  .shop-card.off { background:#FAFAFA; border-style:dashed; }
  .sc-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
  .sc-name { font-weight:800; font-size:16px; color:var(--text); }
  .sc-login { font-family:var(--font-mono); font-size:12.5px; color:#64748B; }
  .sc-meta { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:12.5px; color:#475569; margin:8px 0 10px; }
  .sc-meta .ok { color:#15803D; font-weight:700; }
  .sc-meta .no { color:#B3241C; font-weight:700; }
  .sc-row { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:6px; }
  .sc-row .lbl { font-size:11.5px; color:#94A3B8; margin-right:2px; }
  .sc-btn { border:1px solid var(--border); background:#fff; border-radius:10px; padding:6px 10px; font-size:12.5px; font-weight:600; color:#334155; cursor:pointer; font-family:inherit; }
  .sc-btn:hover { background:#F8FAFC; }
  .sc-panel { margin-top:10px; padding:12px; background:var(--field-bg); border-radius:12px; }
  .sc-edit input { font-size:13px; padding:7px 9px; margin-top:4px; }
  code { font-family:var(--font-mono); font-size:12px; background:#F1F5F9; padding:1px 5px; border-radius:5px; }
  .sc-toggles { display:flex; flex-wrap:wrap; align-items:center; gap:10px 18px; font-size:13px; font-weight:600; color:#334155; }
  .sw { position:relative; width:40px; height:23px; border-radius:12px; border:none; background:#CBD5E1; cursor:pointer; vertical-align:middle; margin-left:6px; padding:0; transition:background .15s; }
  .sw::after { content:''; position:absolute; top:3px; left:3px; width:17px; height:17px; border-radius:50%; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.2); transition:left .15s; }
  .sw.on { background:#16A34A; }
  .sw.on::after { left:20px; }
  .grp-chip { display:inline-flex; align-items:center; gap:4px; background:#F1F5F9; border-radius:999px; padding:0 4px 0 10px; font-size:12.5px; color:#475569; }
  .grp-chip input { border:none !important; background:transparent !important; box-shadow:none !important; padding:5px 6px !important; width:110px; font-size:12.5px; margin:0; }
  .sc-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin-top:12px; }
  .sc-tile { border:1px solid var(--border); background:#fff; border-radius:12px; padding:10px 4px 8px; text-align:center; font-size:12px; font-weight:600; color:#475569; cursor:pointer; font-family:inherit; }
  .sc-tile i { display:block; font-size:18px; color:var(--darkblue); margin-bottom:4px; }
  .sc-tile:hover { background:#F8FAFC; }
  .sc-tile.open { border-color:var(--blue); background:#EFF6FF; color:var(--blue); }
  .sc-tile.open i { color:var(--blue); }
  .sc-tile[disabled] { opacity:.4; cursor:default; }
  @media (max-width:560px) { .row2 { flex-direction:column; gap:0; } }
  .sc-sub { margin:10px 0; padding:10px 12px; border-radius:12px; background:#F8FAFC; border:1px solid var(--border); font-size:13px; }
  .sc-sub.bad { background:#FEF2F2; border-color:#FCA5A5; }
  .sc-sub.warn { background:#FFF7ED; border-color:#FDBA74; }
  .sc-sub-top { display:flex; flex-wrap:wrap; align-items:center; gap:6px 10px; }
  .sub-pill { font-size:12px; font-weight:700; padding:3px 9px; border-radius:999px; white-space:nowrap; }
  .sub-pill.ok { background:#DCFCE7; color:#166534; }
  .sub-pill.warn { background:#FFEDD5; color:#9A3412; }
  .sub-pill.bad { background:#B3241C; color:#fff; }
  .sub-pill.life { background:#0F52BA; color:#fff; }
  .sub-pill.unset { background:#E2E8F0; color:#334155; }
  .sc-sub-btns { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .sc-sub-btns button { border:1.5px solid #0F52BA; background:#fff; color:#0F52BA; border-radius:8px; padding:6px 10px; font-size:12.5px; font-weight:700; cursor:pointer; }
  .sc-sub-btns button.grey { border-color:#CBD5E1; color:#334155; }
  .sc-sub-chk { margin-top:8px; padding:8px 10px; border-radius:10px; background:#FEF3C7; display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
  .sc-sub-chk button { border:0; border-radius:8px; padding:6px 10px; font-weight:700; cursor:pointer; color:#fff; }
  .sc-sub-chk .ok { background:#16A34A; } .sc-sub-chk .no { background:#DC2626; }
  .pay-item { border:1px solid var(--border); border-radius:12px; padding:10px 12px; margin-bottom:8px; font-size:13px; }
  .pay-item .pay-cap { white-space:pre-line; }
  .pay-item .pay-act { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; white-space:normal; }
  .pay-item .pay-act button, .pay-item .pay-act a { border:0; border-radius:8px; padding:7px 12px; font-weight:700; cursor:pointer; color:#fff; text-decoration:none; font-size:13px; }
  .pay-act .ok { background:#16A34A; } .pay-act .no { background:#DC2626; } .pay-act a { background:#0F52BA; }
  .adm-tabs { display:flex; gap:6px; background:#E2E8F0; padding:4px; border-radius:12px; margin-bottom:14px; }
  .adm-tabs button { flex:1; height:42px; border:0; border-radius:9px; background:transparent; font-weight:700; font-size:14px; color:#475569; cursor:pointer; font-family:inherit; }
  .adm-tabs button.on { background:#fff; color:var(--blue); box-shadow:0 1px 3px rgba(15,23,42,.12); }
  .map-kpis { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; margin-bottom:10px; }
  @media (min-width:700px) { .map-kpis { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .map-kpi { background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 12px; }
  .map-kpi b { display:block; font-family:var(--font-display); font-size:20px; color:var(--darkblue); line-height:1.15; }
  .map-kpi span { font-size:11.5px; color:#64748B; }
  .map-bar { display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin-bottom:8px; }
  .map-seg { display:inline-flex; background:#E2E8F0; border-radius:10px; padding:3px; }
  .map-seg button { border:0; background:transparent; border-radius:8px; padding:6px 10px; font-size:12.5px; font-weight:700; color:#475569; cursor:pointer; font-family:inherit; }
  .map-seg button.on { background:#fff; color:var(--blue); box-shadow:0 1px 2px rgba(15,23,42,.12); }
  .map-bar select { border:1px solid var(--border); border-radius:10px; padding:7px 10px; font-size:12.5px; font-family:inherit; background:#fff; color:var(--text); }
  .map-bar label.chk { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; color:#475569; text-transform:none; letter-spacing:0; margin:0; cursor:pointer; }
  .map-bar label.chk input { width:auto; }
  .map-wrap { position:relative; border-radius:18px; overflow:hidden; border:2px solid #DBEAFE; background:#E5E7EB; }
  #admMapBox { height:62vh; min-height:340px; max-height:640px; width:100%; }
  #admMapBox.picking { cursor:crosshair; }
  .map-legend { display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color:#475569; margin:8px 2px 4px; }
  .map-legend i.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:-1px; }
  .map-pick { position:absolute; left:10px; right:10px; bottom:26px; z-index:1000; background:#0A2540; color:#fff; border-radius:14px; padding:10px 12px; font-size:13.5px; box-shadow:0 8px 20px rgba(0,0,0,.25); display:none; }
  .map-pick .pk-act { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
  .map-pick button { border:0; border-radius:9px; padding:8px 12px; font-weight:700; font-size:13px; cursor:pointer; font-family:inherit; }
  .map-pick .pk-geo { background:#00A8E8; color:#fff; } .map-pick .pk-cancel { background:#fff; color:#0A2540; }
  .map-pop { font-family:var(--font-body); min-width:220px; }
  .map-pop .mp-name { font-weight:800; font-size:15px; color:var(--darkblue); }
  .map-pop .mp-kind { font-size:11.5px; color:#64748B; margin:2px 0 6px; }
  .map-pop .mp-st { font-size:12.5px; font-weight:700; margin-bottom:6px; }
  .map-pop .mp-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin:6px 0; }
  .map-pop .mp-grid div { background:#F1F5F9; border-radius:8px; padding:6px 8px; font-size:11px; color:#64748B; }
  .map-pop .mp-grid b { display:block; font-size:14px; color:var(--darkblue); font-family:var(--font-display); }
  .map-pop .mp-addr { font-size:12px; color:#475569; margin:4px 0; }
  .map-pop .mp-snap { display:block; width:100%; margin-top:8px; border:0; border-radius:10px; padding:10px; background:#0F52BA; color:#fff; font-weight:800; font-size:13px; cursor:pointer; font-family:inherit; }
  .map-pop .mp-act { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
  .map-pop .mp-act button, .map-pop .mp-act a { border:0; border-radius:8px; padding:6px 9px; font-size:12px; font-weight:700; cursor:pointer; text-decoration:none; font-family:inherit; }
  .map-pop .mp-act .b1 { background:#0F52BA; color:#fff; } .map-pop .mp-act .b2 { background:#E2E8F0; color:#1E293B; }
  .map-list { background:#fff; border:1px solid var(--border); border-radius:16px; margin-top:12px; overflow:hidden; }
  .map-list h3 { margin:0; padding:12px 14px; font-size:14.5px; font-family:var(--font-display); color:var(--darkblue); border-bottom:1px solid #F1F5F9; }
  .map-row { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #F1F5F9; cursor:pointer; }
  .map-row:last-child { border-bottom:0; }
  .map-row .mr-n { font-weight:800; color:#94A3B8; width:20px; font-size:12px; flex:none; }
  .map-row .mr-dot { width:10px; height:10px; border-radius:50%; flex:none; }
  .map-row .mr-name { flex:1; min-width:0; font-size:13.5px; font-weight:700; }
  .map-row .mr-name small { display:block; font-weight:500; color:#64748B; font-size:11.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .map-row .mr-val { text-align:right; font-family:var(--font-mono); font-size:13px; font-weight:600; white-space:nowrap; }
  .map-row .mr-val small { display:block; font-size:11px; font-family:var(--font-body); }
  .map-row .mr-pin { border:0; background:#EFF6FF; color:var(--blue); border-radius:9px; padding:7px 10px; font-weight:700; font-size:12px; cursor:pointer; font-family:inherit; flex:none; }
  .leaflet-container { font-family:var(--font-body); }
  @media (max-width:440px) { .adm-tabs button { font-size:12.5px; } .adm-tabs button i { display:none; } }
  .ana-sel { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }
  .ana-sel select { flex:1; min-width:140px; border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-family:inherit; background:#fff; color:var(--text); }
  .ana-chips { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; margin-bottom:10px; -webkit-overflow-scrolling:touch; }
  .ana-chips button { flex:none; border:1px solid var(--border); background:#fff; border-radius:999px; padding:6px 12px; font-size:12.5px; font-weight:600; color:#475569; cursor:pointer; font-family:inherit; white-space:nowrap; }
  .ana-chips button.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .ana-card { background:#fff; border:1px solid var(--border); border-radius:16px; margin-bottom:12px; overflow:hidden; }
  .ana-card > h3 { margin:0; padding:12px 14px; font-size:14.5px; font-family:var(--font-display); color:var(--darkblue); border-bottom:1px solid #F1F5F9; display:flex; align-items:center; gap:8px; }
  .ana-card > h3 small { margin-left:auto; font-family:var(--font-body); font-weight:500; font-size:11.5px; color:#94A3B8; }
  .ana-card .ana-note { padding:8px 14px; font-size:12px; color:#64748B; background:#F8FAFC; border-bottom:1px solid #F1F5F9; }
  .ana-row { display:flex; align-items:center; gap:10px; padding:9px 14px; border-bottom:1px solid #F1F5F9; }
  .ana-row:last-child { border-bottom:0; }
  .ana-row.click { cursor:pointer; }
  .ana-row .ar-main { flex:1; min-width:0; }
  .ana-row .ar-name { font-size:13.5px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .ana-row .ar-sub { font-size:11.5px; color:#64748B; margin-top:1px; }
  .ana-row .ar-bar { height:6px; background:#F1F5F9; border-radius:3px; margin-top:5px; overflow:hidden; }
  .ana-row .ar-bar i { display:block; height:100%; background:#0F52BA; border-radius:3px; }
  .ana-row .ar-bar i.mital { background:#EAB308; }
  .ana-row .ar-val { text-align:right; font-family:var(--font-mono); font-size:13px; font-weight:600; white-space:nowrap; }
  .ana-row .ar-val small { display:block; font-family:var(--font-body); font-size:11px; color:#64748B; font-weight:500; }
  .mital-tag { display:inline-block; background:#FEF3C7; color:#B45309; border-radius:6px; padding:1px 6px; font-size:10px; font-weight:800; margin-left:5px; vertical-align:1px; letter-spacing:.3px; }
  .ana-tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .ana-tbl { width:100%; border-collapse:collapse; font-size:12.5px; }
  .ana-tbl .ar-sub { font-weight:500; color:#64748B; font-size:11px; margin-top:2px; }
  .ana-range { padding:4px 14px 10px; font-size:12px; color:#475569; line-height:1.6; }
  .ana-range b { font-family:var(--font-mono); color:var(--darkblue); }
  .ana-tbl th { background:#F8FAFC; color:#64748B; font-size:10px; text-transform:uppercase; letter-spacing:.2px; font-weight:700; text-align:right; padding:8px 6px; border-bottom:1px solid var(--border); }
  .ana-tbl th:first-child, .ana-tbl td:first-child { padding-left:14px; } .ana-tbl th:last-child, .ana-tbl td:last-child { padding-right:14px; }
  .ana-tbl th:first-child, .ana-tbl td:first-child { text-align:left; }
  .ana-tbl td { padding:8px 6px; border-bottom:1px solid #F1F5F9; text-align:right; font-family:var(--font-mono); white-space:nowrap; font-size:12px; }
  .ana-tbl td:first-child { font-family:var(--font-body); font-weight:700; white-space:normal; }
  .ana-tbl tr.click { cursor:pointer; }
  .ana-tbl tr.sum td { background:#F8FAFC; font-weight:700; }
  .ana-btn { border:0; background:#EFF6FF; color:var(--blue); border-radius:9px; padding:8px 12px; font-weight:700; font-size:12.5px; cursor:pointer; font-family:inherit; }
  .ana-dq { display:flex; gap:10px; align-items:center; flex-wrap:wrap; background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 12px; margin-bottom:12px; font-size:12.5px; color:#475569; }
  .ana-dq .dq-txt { flex:1; min-width:200px; line-height:1.5; }
  .ana-dq .dq-txt b { color:var(--darkblue); }
  .ana-dq .dq-act { display:flex; gap:6px; flex-wrap:wrap; }
  .nm-card { padding:12px 14px; }
  .nm-card .ar-sub, .ana-row .ar-sub { font-size:11.5px; color:#64748B; margin-top:2px; }
  .nm-spell { font-weight:800; font-size:14.5px; color:var(--darkblue); word-break:break-word; }
  .nm-spell small { display:block; font-weight:500; font-size:11.5px; color:#64748B; margin-top:2px; }
  .nm-sug { font-size:13px; margin-top:8px; color:#334155; }
  .nm-act { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
  .nm-act button { border:0; border-radius:9px; padding:8px 12px; font-weight:700; font-size:12.5px; cursor:pointer; font-family:inherit; background:#E2E8F0; color:#1E293B; }
  .nm-act button.ok { background:#16A34A; color:#fff; }
  .nm-act button.no { background:#FEE2E2; color:#B91C1C; }
  .nm-form { margin-top:10px; }
  .nm-form label { margin-top:6px; }
  .snap-ov { position:fixed; inset:0; z-index:5000; background:rgba(15,23,42,.55); display:none; }
  .snap-box { position:absolute; left:0; right:0; bottom:0; top:max(24px, env(safe-area-inset-top, 0px)); background:var(--bg); border-radius:20px 20px 0 0; overflow-y:auto; -webkit-overflow-scrolling:touch; }
  @media (min-width:900px) { .snap-box { left:50%; transform:translateX(-50%); width:760px; top:30px; bottom:30px; border-radius:20px; } }
  .snap-head { position:sticky; top:0; z-index:2; background:#0A2540; color:#fff; padding:14px 16px 12px; display:flex; gap:10px; align-items:flex-start; }
  .snap-head .sh-name { font-family:var(--font-display); font-weight:700; font-size:17px; line-height:1.2; }
  .snap-head .sh-sub { font-size:12px; color:#93C5FD; margin-top:3px; }
  .snap-head .sh-x { margin-left:auto; border:0; background:rgba(255,255,255,.12); color:#fff; width:36px; height:36px; border-radius:10px; font-size:18px; cursor:pointer; flex:none; }
  .snap-body { padding:12px 12px calc(24px + env(safe-area-inset-bottom, 0px)); }
  .snap-sec { font-family:var(--font-display); font-size:16px; color:var(--darkblue); margin:16px 2px 8px; display:flex; align-items:center; gap:8px; }
  .snap-wh-row { display:flex; gap:10px; align-items:center; padding:10px 14px; border-bottom:1px solid #F1F5F9; }
  .snap-wh-row:last-child { border-bottom:0; }
  .snap-wh-row .sw-main { flex:1; min-width:0; }
  .snap-wh-row .sw-name { font-weight:700; font-size:13.5px; }
  .snap-wh-row .sw-sub { font-size:11.5px; color:#64748B; margin-top:2px; }
  .snap-wh-row .sw-price { text-align:right; font-family:var(--font-mono); font-size:12.5px; white-space:nowrap; }
  .snap-wh-row .sw-price small { display:block; font-family:var(--font-body); font-size:11px; color:#64748B; }
  .snap-wh-row .sw-m { display:inline-block; margin-top:3px; padding:1px 7px; border-radius:7px; font-size:11.5px; font-weight:700; background:#ECFDF5; color:#047857; font-family:var(--font-body); }
  .snap-wh-row .sw-m.low { background:#FEF2F2; color:#B91C1C; }
  .snap-wh-row .sw-m.none { background:#F1F5F9; color:#94A3B8; }
  details.sup-card > summary { list-style:none; display:flex; align-items:center; gap:10px; padding:12px 14px; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  details.sup-card > summary::-webkit-details-marker { display:none; }
  details.sup-card > summary .ar-main { flex:1; min-width:0; }
  details.sup-card > summary .ar-name { font-size:14px; font-weight:800; color:var(--darkblue); }
  details.sup-card > summary .ar-sub { font-size:11.5px; color:#64748B; margin-top:2px; }
  details.sup-card > summary .ar-val { text-align:right; font-family:var(--font-mono); font-size:14px; font-weight:700; white-space:nowrap; }
  details.sup-card > summary .ar-val small { display:block; font-family:var(--font-body); font-size:11px; font-weight:500; color:#64748B; }
  details.sup-card .sup-chev { color:#94A3B8; transition:transform .2s; }
  details.sup-card[open] .sup-chev { transform:rotate(180deg); }
  details.sup-card[open] > summary { border-bottom:1px solid #F1F5F9; }
  .sup-contacts { display:flex; flex-wrap:wrap; gap:8px; padding:10px 14px 0; font-size:12.5px; }
  .sup-contacts > * { background:#EFF6FF; color:var(--blue); border-radius:8px; padding:5px 9px; text-decoration:none; font-weight:600; }
  .sup-h { padding:10px 14px 4px; font-size:11px; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:.4px; }
  .ana-cmp b.ana-bad, .ar-val small.ana-bad { color:#DC2626; } .ana-cmp b.ana-good, .ar-val small.ana-good { color:#16A34A; }
  .ana-good { color:#16A34A; } .ana-bad { color:#DC2626; } .ana-mute { color:#94A3B8; }
  .ana-brands { display:flex; flex-wrap:wrap; gap:5px; margin-top:5px; }
  .ana-brands span { background:#F1F5F9; border-radius:7px; padding:2px 7px; font-size:11.5px; color:#334155; }
  .ana-brands span.m { background:#FEF3C7; color:#B45309; font-weight:700; }
  .ana-cmp { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; padding:12px 14px; }
  @media (min-width:700px) { .ana-cmp { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .ana-cmp div { background:#F8FAFC; border-radius:10px; padding:8px 10px; font-size:11.5px; color:#64748B; }
  .ana-cmp b { display:block; font-family:var(--font-display); font-size:17px; color:var(--darkblue); }
  .inc-grid { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; margin-bottom:12px; }
  @media (min-width:900px) { .inc-grid { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .inc-kpi { background:#fff; border:1px solid var(--border); border-radius:14px; padding:12px 14px; }
  .inc-kpi .k-l { font-size:12px; color:var(--hint); font-weight:600; }
  .inc-kpi .k-v { font-family:var(--font-mono, monospace); font-size:20px; font-weight:700; color:var(--darkblue); margin:4px 0 2px; white-space:nowrap; }
  .inc-kpi .k-s { font-size:12px; color:var(--hint); }
  .inc-kpi.main { background:#0B1F3A; border-color:#0B1F3A; }
  .inc-kpi.main .k-l, .inc-kpi.main .k-s { color:#B9C6DA; } .inc-kpi.main .k-v { color:#fff; }
  .inc-card { background:#fff; border:1px solid var(--border); border-radius:14px; padding:14px; margin-bottom:12px; }
  .inc-card h3 { margin:0 0 10px; font-size:15px; display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
  .inc-seg { display:flex; background:#EEF2F7; border-radius:9px; padding:3px; gap:3px; }
  .inc-seg button { border:0; background:transparent; border-radius:7px; padding:6px 10px; font-size:12px; font-weight:700; color:#475569; cursor:pointer; font-family:inherit; }
  .inc-seg button.on { background:#fff; color:var(--blue); }
  .inc-bars { display:flex; align-items:flex-end; gap:4px; height:170px; padding-top:18px; }
  .inc-bar { flex:1; min-width:0; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; height:100%; }
  .inc-bar .b { width:100%; max-width:34px; background:#93C5FD; border-radius:6px 6px 2px 2px; min-height:2px; }
  .inc-bar.cur .b { background:#0F52BA; }
  .inc-bar .v { font-size:10px; color:#334155; font-weight:700; margin-bottom:3px; white-space:nowrap; }
  .inc-bar .m { font-size:10.5px; color:var(--hint); margin-top:4px; }
  @media (max-width:600px) { .inc-bar .v { display:none; } .inc-bar.cur .v, .inc-bar.mx .v { display:block; } }
  .inc-stack { display:flex; height:14px; border-radius:999px; overflow:hidden; background:#EEF2F7; margin-bottom:10px; }
  .inc-leg { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:6px 12px; font-size:13px; }
  .inc-leg span i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }
  .inc-term { display:flex; align-items:center; gap:8px; font-size:13px; margin:6px 0; }
  .inc-term .t-n { width:52px; font-weight:700; }
  .inc-term .t-bar { flex:1; height:10px; background:#EEF2F7; border-radius:999px; overflow:hidden; }
  .inc-term .t-bar div { height:100%; background:#0F52BA; border-radius:999px; }
  .inc-term .t-c { width:64px; text-align:right; color:var(--hint); }
  .inc-row { display:flex; justify-content:space-between; gap:10px; padding:9px 0; border-top:1px solid #EEF2F7; font-size:13px; }
  .inc-row:first-of-type { border-top:0; }
  .inc-row .r-s { font-size:12px; color:var(--hint); margin-top:2px; }
  .inc-row .r-v { font-family:var(--font-mono, monospace); font-weight:700; white-space:nowrap; }
  .inc-jact { display:flex; gap:6px; margin-top:6px; }
  .inc-jact button { border:1px solid #CBD5E1; background:#fff; border-radius:7px; padding:4px 8px; font-size:11.5px; font-weight:700; color:#334155; cursor:pointer; }
  .inc-alert { display:flex; align-items:center; gap:10px; background:#FEF3C7; border:1.5px solid #FCD34D; border-radius:12px; padding:10px 12px; margin-bottom:12px; font-size:13.5px; font-weight:600; cursor:pointer; }
</style>
</head>
<body>
<div class="speedline"></div>
<div class="container">
  <div class="topbar">
    <div style="display:flex; align-items:center; gap:10px;">
      <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
      <div>
        <h1 style="margin:0; line-height:1;"><span class="wordmark" style="font-size:28px;"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span></h1>
        <div class="logo-sub">Админ-панель платформы</div>
      </div>
    </div>
    <div style="display:flex; align-items:center; gap:14px;">
      <a class="logout" href="/admin/help"><i class="fa-solid fa-circle-question"></i> Справка</a>
      <a class="logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i> Выйти</a>
    </div>
  </div>

  <div id="msg"></div>

  <div class="adm-tabs" id="admTabs">
    <button class="on" data-t="main" onclick="admTab('main')"><i class="fa-solid fa-store"></i> Точки</button>
    <button data-t="income" onclick="admTab('income')"><i class="fa-solid fa-sack-dollar"></i> Доходы</button>
    <button data-t="map" onclick="admTab('map')"><i class="fa-solid fa-map-location-dot"></i> Карта</button>
    <button data-t="analytics" onclick="admTab('analytics')"><i class="fa-solid fa-chart-pie"></i> Аналитика</button>
  </div>
  <div id="admMain">

  <div class="adm-stats" id="admStats">
    <div class="adm-stat"><b>—</b><span>точек</span></div>
    <div class="adm-stat"><b>—</b><span>активных</span></div>
    <div class="adm-stat"><b>—</b><span>клиентов</span></div>
  </div>

  <details class="adm-sec" id="secReg">
    <summary>
      <span class="ic" style="background:#EFF6FF; color:#1D4ED8;"><i class="fa-solid fa-user-plus"></i></span>
      <span>Заявки на регистрацию<span class="sub" id="regSecSub">точки, которые зарегистрировались сами</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <div id="regPending"><div class="hint-text">Загружаю…</div></div>
      <div style="font-weight:700; font-size:13px; margin:14px 0 8px;">Последние решения</div>
      <div id="regDone"></div>
      <div class="hint-text" style="margin-top:10px;">Ссылка для владельцев точек: <b id="regLink"></b></div>
    </div>
  </details>

  <details class="adm-sec" id="secAdd">
    <summary>
      <span class="ic" style="background:#ECFDF5; color:#059669;"><i class="fa-solid fa-plus"></i></span>
      <span>Добавить новую точку<span class="sub">логин, телефон, адрес, локация</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <div class="field">
        <label>Название точки</label>
        <input id="new_shop_name" placeholder="Avto Servis Namangan">
      </div>
      <div class="field">
        <label>Группа (необяз.) — только чтобы точки одного владельца стояли рядом в списке</label>
        <input id="new_client_group" list="clientGroupsList" placeholder="например: Sinov01">
        <datalist id="clientGroupsList"></datalist>
      </div>
      <div class="row2">
        <div class="field">
          <label>Логин</label>
          <input id="new_username" placeholder="namangan_point">
        </div>
        <div class="field">
          <label>Пароль (пусто = сгенерировать)</label>
          <input id="new_password" placeholder="необязательно">
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label>Телефон точки</label>
          <input id="new_phone" placeholder="+998901112233">
        </div>
        <div class="field">
          <label>Telegram ID для уведомлений (необяз.)</label>
          <input id="new_notify_id" placeholder="123456789">
        </div>
      </div>
      <div class="field">
        <label>Адрес</label>
        <input id="new_address" placeholder="Наманган, ул. ...">
      </div>
      <div class="field">
        <label>Локация (необяз.) — широта и долгота из Google Карт через запятую</label>
        <input id="new_location" placeholder="40.782123, 72.344567">
        <div class="hint-text">Открой точку на Google Картах, нажми и удержи на месте — внизу появятся два числа через запятую, скопируй их сюда целиком.</div>
      </div>
      <div class="hint-text" style="margin:-2px 0 10px; color:#B45309;">⚠️ Это <b>самостоятельная</b> точка: она видит свою прибыль и закупочные цены. Если нужен <b>филиал</b> (без прибыли, с общим складом и статистикой у главного) — открой карточку главной точки → плитка «Филиалы» → «+ Добавить филиал».</div>
      <button class="submit" onclick="createShop()">Создать точку</button>
      <div id="newCreds"></div>
    </div>
  </details>

  <details class="adm-sec" id="secSub">
    <summary>
      <span class="ic" style="background:#FEF3C7; color:#B45309;"><i class="fa-solid fa-credit-card"></i></span>
      <span>Подписка: чеки и реквизиты<span class="sub" id="subSecSub">проверка оплат, карта, цены</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <div style="font-weight:700; font-size:13px; margin-bottom:8px;">Чеки на проверке</div>
      <div id="subPayments"><div class="hint-text">Загружаю…</div></div>
      <div style="font-weight:700; font-size:13px; margin:14px 0 8px;">Реквизиты для оплаты</div>
      <div class="row2">
        <div class="field"><label>Номер карты</label><input id="ss_card_number" inputmode="numeric" placeholder="5614 0000 0000 0000"></div>
        <div class="field"><label>Имя на карте</label><input id="ss_card_holder" placeholder="Имя Фамилия"></div>
      </div>
      <div class="field"><label>Контакт поддержки (Telegram или телефон, необяз.)</label><input id="ss_support_contact" placeholder="@username или +998..."></div>
      <div style="font-weight:700; font-size:13px; margin:6px 0 8px;">Цены в месяц (сум) и скидки за срок (%)</div>
      <div class="row2">
        <div class="field"><label>Главная точка</label><input id="ss_price_main" inputmode="numeric"></div>
        <div class="field"><label>Каждый филиал</label><input id="ss_price_branch" inputmode="numeric"></div>
      </div>
      <div class="row2">
        <div class="field"><label>1 мес, %</label><input id="ss_disc_1" inputmode="numeric"></div>
        <div class="field"><label>3 мес, %</label><input id="ss_disc_3" inputmode="numeric"></div>
        <div class="field"><label>6 мес, %</label><input id="ss_disc_6" inputmode="numeric"></div>
        <div class="field"><label>12 мес, %</label><input id="ss_disc_12" inputmode="numeric"></div>
      </div>
      <button class="submit" style="width:auto; padding:10px 20px;" onclick="saveSubSettings()">Сохранить</button>
      <div class="hint-text" style="margin-top:10px;">Точки без даты оплаты («без даты») работают как раньше — поставь им дату в карточке, и подписка начнёт действовать. Блокировка — на следующий день после даты, без льготы. Данные при блокировке не удаляются.</div>
    </div>
  </details>

  <details class="adm-sec" id="secBackup">
    <summary>
      <span class="ic" style="background:#EFF6FF; color:var(--blue);"><i class="fa-solid fa-box-archive"></i></span>
      <span>Резервная копия<span class="sub">приходит в Telegram каждую ночь</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <p class="hint-text" style="margin-top:0;">Если сомневаешься, что копия доходит, отправь её прямо сейчас. Если копии нет в чате с ботом, напиши боту <code>/myid</code> и сверь число с <code>ADMIN_TELEGRAM_ID</code> в настройках Render (Environment).</p>
      <button class="submit" style="width:auto; padding:10px 20px;" onclick="triggerBackupNow()"><i class="fa-solid fa-paper-plane"></i> Отправить сейчас</button>
      <div id="backupResult" style="margin-top:10px;"></div>
    </div>
  </details>

  <details class="adm-sec danger" id="secRestore">
    <summary>
      <span class="ic" style="background:#FEF2F2; color:#B3241C;"><i class="fa-solid fa-clock-rotate-left"></i></span>
      <span style="color:#B3241C;">Восстановить базу из копии<span class="sub">заменяет все данные — только при необходимости</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <p class="hint-text" style="margin-top:0;">
        <b>Внимание:</b> это заменит АБСОЛЮТНО ВСЕ текущие данные платформы (все точки, клиентов, историю) на содержимое загруженного файла.
        Всё, что было добавлено после даты этой копии, будет потеряно безвозвратно.<br>
        Перед заменой мы сами отправим тебе копию ТЕКУЩЕГО состояния — на случай, если восстановление окажется ошибкой.
      </p>
      <div class="field">
        <label>Файл резервной копии (.db)</label>
        <input type="file" id="restore_file" accept=".db,.gz">
      </div>
      <div class="field">
        <label>Чтобы подтвердить, впиши слово <code>ЗАМЕНИТЬ</code></label>
        <input id="restore_confirm" placeholder="ЗАМЕНИТЬ">
      </div>
      <button class="submit" style="width:auto; padding:10px 20px; background:linear-gradient(135deg, #DC2626, #991B1B);" onclick="triggerRestore()">Восстановить из этого файла</button>
      <div id="restoreResult" style="margin-top:10px;"></div>
    </div>
  </details>

  <div class="list-head">
    <h2>Все точки</h2>
  </div>
  <input id="shopSearch" type="search" name="oilbook_shop_q" autocomplete="off" spellcheck="false" placeholder="🔍 Поиск по названию, логину или телефону..." oninput="filterShops()">
  <div class="adm-filters" id="admFilters">
    <button class="on" data-f="all" onclick="setShopFilter('all')">Все</button>
    <button data-f="active" onclick="setShopFilter('active')">Активные</button>
    <button data-f="off" onclick="setShopFilter('off')">Выключенные</button>
    <button data-f="notg" onclick="setShopFilter('notg')">Без Telegram</button>
    <button data-f="debt" onclick="setShopFilter('debt')">Должники</button>
    <button data-f="soon" onclick="setShopFilter('soon')">Скоро истекает</button>
    <button data-f="check" onclick="setShopFilter('check')">Чек ждёт</button>
    <button data-f="life" onclick="setShopFilter('life')">∞ Бессрочные</button>
    <button data-f="unset" onclick="setShopFilter('unset')">Без даты</button>
    <button data-f="trial" onclick="setShopFilter('trial')">🎁 Пробные</button>
  </div>
  <div id="shops-body"></div>
  </div>
  <div id="admIncome" style="display:none;"><div class="hint-text">Загружаю…</div></div>
  <div id="admMap" style="display:none;">
    <div class="map-kpis" id="mapKpis"></div>
    <div class="map-bar">
      <div class="map-seg" id="mapDaysSeg">
        <button data-d="7" onclick="setMapDays(7)">7 дн</button>
        <button class="on" data-d="30" onclick="setMapDays(30)">30 дн</button>
        <button data-d="90" onclick="setMapDays(90)">3 мес</button>
      </div>
      <div class="map-seg" id="mapMetricSeg">
        <button class="on" data-m="count" onclick="setMapMetric('count')">Замены</button>
        <button data-m="total" onclick="setMapMetric('total')">Выручка</button>
      </div>
    </div>
    <div class="map-bar">
      <div class="map-seg" id="mapFilterSeg">
        <button class="on" data-f="all" onclick="setMapFilter('all')">Все</button>
        <button data-f="green" onclick="setMapFilter('green')">Работают</button>
        <button data-f="yellow" onclick="setMapFilter('yellow')">Реже</button>
        <button data-f="red" onclick="setMapFilter('red')">Молчат</button>
        <button data-f="off" onclick="setMapFilter('off')">Выкл.</button>
      </div>
      <select id="mapGroup" onchange="mapGroupSel=this.value; renderMap();"><option value="">Все сети</option></select>
      <label class="chk"><input type="checkbox" id="mapLinksChk" checked onchange="renderMap()"> Связи филиалов</label>
    </div>
    <div class="map-wrap">
      <div id="admMapBox"></div>
      <div class="map-pick" id="mapPick">
        <div id="mapPickText"></div>
        <div class="pk-act">
          <button class="pk-geo" onclick="mapPickHere()"><i class="fa-solid fa-location-crosshairs"></i> Я сейчас здесь</button>
          <button class="pk-cancel" onclick="mapPickCancel()">Отмена</button>
        </div>
      </div>
    </div>
    <div class="map-legend">
      <span><i class="dot" style="background:#16A34A"></i>замена за последние 3 дня</span>
      <span><i class="dot" style="background:#EAB308"></i>4–14 дней назад</span>
      <span><i class="dot" style="background:#DC2626"></i>больше 14 дней / не было</span>
      <span><i class="dot" style="background:#94A3B8"></i>выключена</span>
      <span>● размер круга — <b id="mapLegendMetric">замены</b> за период; толстая обводка — главная точка</span>
    </div>
    <div class="map-list" id="mapNoCoords" style="display:none;"></div>
    <div class="map-list" id="mapRating"></div>
  </div>
  <div id="admAna" style="display:none;">
    <div class="map-bar" id="anaDaysBar">
      <div class="map-seg" id="anaDaysSeg">
        <button class="on" data-d="30" onclick="setAnaDays(30)">30 дн</button>
        <button data-d="90" onclick="setAnaDays(90)">3 мес</button>
        <button data-d="365" onclick="setAnaDays(365)">Год</button>
      </div>
    </div>
    <div id="anaFilters">
    <div class="ana-sel">
      <select id="anaGroup" onchange="anaGroup=this.value; anaShop=0; renderAna();"></select>
      <select id="anaShopSel" onchange="anaShop=Number(this.value)||0; renderAna();"></select>
    </div>
    <div class="ana-chips" id="anaCats"></div>
    </div>
    <div id="anaBody"><div class="hint-text">Загружаю…</div></div>
  </div>
</div>
<div class="snap-ov" id="snapOv" onclick="if (event.target === this) closeSnapshot()">
  <div class="snap-box">
    <div class="snap-head">
      <div><div class="sh-name" id="snapName">—</div><div class="sh-sub" id="snapSub"></div></div>
      <button class="sh-x" onclick="closeSnapshot()" aria-label="Закрыть">✕</button>
    </div>
    <div class="snap-body" id="snapBody"></div>
  </div>
</div>

<script>
function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 8000);
}

function showMsgSticky(text) {
  // не исчезает сама - для одноразовых паролей, которые больше нигде не
  // будут показаны повторно, чтобы админ точно успел их скопировать
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ok" style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
    <span>${text}</span>
    <button type="button" onclick="this.closest('.msg').remove()" style="flex:none; background:none; border:none; color:inherit; font-size:18px; cursor:pointer; padding:0 4px;">×</button>
  </div>`;
  // #msg находится в самом верху страницы — если действие вызвано далеко
  // внизу (например, сброс пароля филиала в развёрнутой панели), человек
  // иначе может не увидеть, что пароль вообще появился
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

let allShopsCache = [];

const fmtSum = n => (n == null ? '—' : Number(n).toLocaleString('ru-RU'));
function fmtDay(s) {
  if (!s) return '—';
  const p = String(s).slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : s;
}

function renderSubBlock(s) {
  const u = s.sub;
  if (!u) return '';
  let pill, cls = '';
  if (u.lifetime) pill = '<span class="sub-pill life">∞ бессрочная</span>';
  else if (!u.paid_until) pill = '<span class="sub-pill unset">без даты — работает</span>';
  else if (u.trial && u.expired) { pill = `<span class="sub-pill bad">пробный закончился ${fmtDay(u.paid_until)}</span>`; cls = 'bad'; }
  else if (u.trial) { pill = `<span class="sub-pill warn">🎁 пробный · ${u.days_left === 0 ? 'последний день' : 'осталось ' + (u.days_left + 1) + ' дн.'}</span>`; }
  else if (u.expired) { pill = `<span class="sub-pill bad">заблокирована с ${fmtDay(addDays(u.paid_until, 1))}</span>`; cls = 'bad'; }
  else if (u.days_left <= 5) { pill = `<span class="sub-pill warn">${u.days_left === 0 ? 'сегодня последний день' : 'осталось ' + u.days_left + ' дн.'}</span>`; cls = 'warn'; }
  else pill = '<span class="sub-pill ok">оплачено</span>';
  const name = escapeHtml(JSON.stringify(s.shop_name || s.username));
  const chk = u.pending_payment ? `
    <div class="sc-sub-chk">🧾 Чек на проверке: <b>${fmtSum(u.pending_payment.amount)} сум</b>
      ${u.pending_payment.has_receipt ? `<a href="/api/admin/sub/receipt/${u.pending_payment.id}" target="_blank" rel="noopener">открыть чек</a>` : ''}
      <button class="ok" onclick="decideSub(${u.pending_payment.id}, 1)">✅ Подтвердить</button>
      <button class="no" onclick="decideSub(${u.pending_payment.id}, 0)">❌ Отклонить</button>
    </div>` : '';
  const br = u.pending_branches ? `<div style="margin-top:6px; color:#9A3412;">⏳ Филиалов ждут оплаты: <b>${u.pending_branches}</b> — открой «Филиалы»</div>` : '';
  const lp = u.lifetime_payment;
  const btns = u.lifetime ? `
      ${lp ? `<button onclick="editPayAmount(${lp.id}, ${lp.amount || 0})">✏️ Сумма покупки</button>` : ''}
      <button class="grey" onclick="subLifetime(${s.id}, 0, ${name})">Снять ∞ (вернуть подписку)</button>` : `
      <button onclick="subExtend(${s.id}, 1, ${name})">+1 мес</button>
      <button onclick="subExtend(${s.id}, 3, ${name})">+3</button>
      <button onclick="subExtend(${s.id}, 6, ${name})">+6</button>
      <button onclick="subExtend(${s.id}, 12, ${name})">+12</button>
      <button class="grey" onclick="subSetDate(${s.id}, ${escapeHtml(JSON.stringify(u.paid_until || ''))})">📅 Дата</button>
      <button class="grey" onclick="subPrice(${s.id}, ${u.custom_price || 0}, ${name})">💲 Цена</button>
      <button class="grey" onclick="subLifetime(${s.id}, 1, ${name})">∞ Разовая покупка</button>`;
  return `
    <div class="sc-sub ${cls}">
      <div class="sc-sub-top">${pill}
        ${!u.lifetime ? `${u.paid_until ? `<span>до <b>${fmtDay(u.paid_until)}</b></span>` : ''}<span>${fmtSum(u.monthly)} сум/мес${u.branch_count ? ' · ' + u.branch_count + ' фил.' : ''}</span>${u.custom_price ? `<span class="sub-pill unset">индив. цена ${fmtSum(u.custom_price)}</span>` : ''}`
          : `<span>${lp && lp.amount ? 'куплено за <b>' + fmtSum(lp.amount) + ' сум</b>' : '<span style="color:#B45309;">сумма покупки не указана</span>'}</span>`}
      </div>
      ${chk}${br}
      <div class="sc-sub-btns">${btns}</div>
    </div>`;
}


function regCard(r, withButtons) {
  const tgPh = r.tg_phone || '—';
  const same = r.tg_phone && r.phone && r.tg_phone.replace(/[^0-9]/g, '') === r.phone.replace(/[^0-9]/g, '');
  const tg = r.tg_username ? '@' + r.tg_username : 'без @username';
  const st = r.status === 'approved' ? '<span class="sub-pill ok">одобрена</span>'
           : r.status === 'rejected' ? '<span class="sub-pill unset">отклонена</span>' : '';
  const lines = [
    `<b>${escapeHtml(r.shop_name)}</b> ${st}`,
    `Владелец: ${escapeHtml(r.owner_name || '—')} · ${escapeHtml(r.city || '')}`,
    `Адрес: ${escapeHtml(r.address || '—')}`,
    `Телефон: ${escapeHtml(r.phone || '—')} · в Telegram: ${escapeHtml(tgPh)} ${r.tg_phone ? (same ? '✅' : '⚠️ отличается') : ''}`,
    `Telegram: ${escapeHtml(tg)} · ${escapeHtml(r.tg_name || '')}`,
    `Локация: ${r.lat != null && r.lon != null ? `<a href="https://maps.google.com/?q=${Number(r.lat).toFixed(6)},${Number(r.lon).toFixed(6)}" target="_blank" rel="noopener">📍 открыть на карте</a>` : '—'}`,
    `Логин: <b>${escapeHtml(r.username)}</b> · язык ${escapeHtml((r.language || 'ru').toUpperCase())}`,
  ];
  const when = withButtons ? `подтверждена ${escapeHtml(r.confirmed_at || r.created_at || '')}` : `решение ${escapeHtml(r.decided_at || '')}`;
  return `<div class="pay-item"><div class="pay-cap" style="white-space:normal; line-height:1.6;">${lines.join('<br>')}</div>
    <div class="hint-text" style="margin-top:4px;">№${r.id} · ${when}</div>
    ${withButtons ? `<div class="pay-act">
      <button class="ok" onclick="decideReg(${r.id}, 1)">✅ Одобрить (14 дней)</button>
      <button class="no" onclick="decideReg(${r.id}, 0)">❌ Отклонить</button></div>` : ''}
  </div>`;
}

async function loadRegs() {
  try {
    const res = await fetch('/api/admin/registrations');
    const d = await res.json();
    if (!d.ok) return;
    const pend = d.pending || [], done = d.done || [];
    document.getElementById('regPending').innerHTML = pend.length ? pend.map(r => regCard(r, true)).join('')
      : '<div class="hint-text">Новых заявок нет.</div>';
    document.getElementById('regDone').innerHTML = done.length ? done.map(r => regCard(r, false)).join('')
      : '<div class="hint-text">Пока пусто.</div>';
    document.getElementById('regSecSub').textContent = pend.length ? `ждут решения: ${pend.length}` : 'точки, которые зарегистрировались сами';
    document.getElementById('regLink').textContent = location.origin + '/register';
    const sec = document.getElementById('secReg');
    if (pend.length && !sec.dataset.autoOpened) { sec.open = true; sec.dataset.autoOpened = '1'; }
  } catch (e) {}
}

async function decideReg(id, ok) {
  if (!ok && !confirm('Отклонить заявку? Человеку придёт сообщение в Telegram.')) return;
  const res = await fetch(`/api/admin/registrations/${id}/${ok ? 'approve' : 'reject'}`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) showMsg(ok ? `✅ Точка создана, пробный период до ${fmtDay(data.paid_until)}` : 'Заявка отклонена', true);
  else showMsg('Ошибка: ' + data.error, false);
  loadRegs(); loadShops();
}

function addDays(day, n) {
  const d = new Date(String(day).slice(0, 10) + 'T00:00:00');
  d.setDate(d.getDate() + n);
  const z = x => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

async function subAction(shopId, body) {
  const res = await fetch(`/api/admin/shops/${shopId}/sub`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  return res.json();
}

async function subExtend(shopId, months, name) {
  if (!confirm(`Продлить «${name}» на ${months} мес. (оплата наличными)?`)) return;
  const data = await subAction(shopId, {action: 'extend', months});
  if (data.ok) { showMsg(`✅ Продлено до ${fmtDay(data.paid_until)}`, true); loadShops(); }
  else showMsg('Ошибка: ' + data.error, false);
}

async function subSetDate(shopId, current) {
  const v = prompt('Оплачено до (ДД.ММ.ГГГГ). Пусто — убрать дату (точка работает без подписки):', current ? fmtDay(current) : '');
  if (v === null) return;
  const data = await subAction(shopId, {action: 'set_until', date: v.trim()});
  if (data.ok) { showMsg(data.paid_until ? `✅ Дата: ${fmtDay(data.paid_until)}` : '✅ Дата убрана', true); loadShops(); }
  else showMsg('Ошибка: ' + data.error, false);
}

function askSum(text, current) {
  // null — нажали «Отмена»; '' — оставили пустым
  const v = prompt(text, current ? String(current) : '');
  if (v === null) return null;
  return v.replace(/[^0-9]/g, '');
}

async function subLifetime(shopId, on, name) {
  let amount = '';
  if (on) {
    amount = askSum(`«${name}» — разовая покупка (∞, без ежемесячной оплаты).\\nСумма, которую заплатили, в сумах (для статистики доходов):`, '');
    if (amount === null) return;
  } else if (!confirm(`Вернуть «${name}» на ежемесячную подписку? Запись о разовой покупке уберётся из статистики.`)) return;
  const data = await subAction(shopId, {action: 'lifetime', on: !!on, amount});
  if (data.ok) { showMsg('✅ Готово', true); loadShops(); } else showMsg('Ошибка: ' + data.error, false);
}

async function subPrice(shopId, current, name) {
  const v = askSum(`Индивидуальная цена главной точки «${name}», сум в месяц.\\nСкидки за срок к ней не применяются. Пусто — обычная цена.`, current || '');
  if (v === null) return;
  const data = await subAction(shopId, {action: 'price', price: v});
  if (data.ok) { showMsg(v ? `✅ Цена ${fmtSum(v)} сум/мес` : '✅ Обычная цена', true); loadShops(); }
  else showMsg('Ошибка: ' + data.error, false);
}

async function editPayAmount(paymentId, current) {
  const v = askSum('Сумма оплаты в сумах:', current || '');
  if (v === null) return;
  const res = await fetch(`/api/admin/sub/payments/${paymentId}/amount`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount: v})
  });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Сумма сохранена', true); loadShops(); if (INC) loadIncome(); }
  else showMsg('Ошибка: ' + data.error, false);
}

async function cancelPayment(paymentId) {
  if (!confirm('Убрать эту оплату из статистики? Дата «оплачено до» не изменится — если нужно, поправьте её кнопкой «📅 Дата».')) return;
  const res = await fetch(`/api/admin/sub/payments/${paymentId}/cancel`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Убрано', true); loadIncome(); loadShops(); } else showMsg('Ошибка: ' + data.error, false);
}

async function decideSub(paymentId, ok) {
  if (!ok && !confirm('Отклонить этот чек? Точке придёт сообщение, что чек не принят.')) return;
  const res = await fetch(`/api/admin/sub/payments/${paymentId}/${ok ? 'confirm' : 'reject'}`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) showMsg(ok ? `✅ Подтверждено — до ${fmtDay(data.new_until)}` : 'Чек отклонён', true);
  else showMsg('Ошибка: ' + data.error, false);
  loadShops(); loadSubPanel();
}

async function markBranchPaid(shopId, branchId, name) {
  const amount = askSum(`Филиал «${name}» оплачен — он сразу заработает.\\nСумма, которую заплатили, в сумах (для статистики):`, '');
  if (amount === null) return;
  const res = await fetch(`/api/admin/branches/${branchId}/sub_paid`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount})
  });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Филиал включён', true); loadBranches(shopId); }
  else showMsg('Ошибка: ' + data.error, false);
}

function admTab(t) {
  document.querySelectorAll('#admTabs button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  document.getElementById('admMain').style.display = t === 'main' ? '' : 'none';
  document.getElementById('admIncome').style.display = t === 'income' ? '' : 'none';
  document.getElementById('admMap').style.display = t === 'map' ? '' : 'none';
  document.getElementById('admAna').style.display = t === 'analytics' ? '' : 'none';
  if (t !== 'map' && typeof mapPickCancel === 'function' && mapPickId) mapPickCancel();
  try { history.replaceState(null, '', t === 'main' ? location.pathname : '#' + t); } catch (e) {}
  if (t === 'income') loadIncome();
  if (t === 'map') loadMap();
  if (t === 'analytics') loadAna();
  window.scrollTo(0, 0);
}

const MONTHS_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const MONTHS_FULL = ['январе', 'феврале', 'марте', 'апреле', 'мае', 'июне', 'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре'];
function fmtShort(n) {
  n = Number(n) || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace('.', ',').replace(',0', '') + ' млн';
  if (n >= 1000) return Math.round(n / 1000) + ' тыс';
  return String(n);
}
let INC = null, incMode = 'received';

async function loadIncome() {
  const box = document.getElementById('admIncome');
  try {
    const res = await fetch('/api/admin/income');
    const data = await res.json();
    if (!data.ok) { box.innerHTML = `<div class="msg err">${escapeHtml(data.error || 'Ошибка')}</div>`; return; }
    INC = data.stats;
    renderIncome();
  } catch (e) {
    box.innerHTML = '<div class="msg err">Не удалось загрузить — проверьте интернет</div>';
  }
}

function setIncMode(m) { incMode = m; renderIncome(); }

function openPendingChecks() {
  admTab('main');
  const sec = document.getElementById('secSub');
  sec.open = true;
  sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderIncome() {
  const d = INC;
  if (!d) return;
  const c = d.counts;
  const curM = Number(d.months[d.months.length - 1].slice(5)) - 1;
  const diff = d.this_month - d.prev_month;
  const kpis = `
    <div class="inc-grid">
      <div class="inc-kpi main"><div class="k-l">Подписки в месяц</div><div class="k-v">${fmtSum(d.mrr)}</div><div class="k-s">${c.paying} точек платят · ${fmtShort(d.arr)} в год</div></div>
      <div class="inc-kpi"><div class="k-l">Получено в ${MONTHS_FULL[curM]}</div><div class="k-v">${fmtSum(d.this_month)}</div><div class="k-s">прошлый месяц ${fmtShort(d.prev_month)}${d.prev_month || d.this_month ? (diff >= 0 ? ' · ▲ ' : ' · ▼ ') + fmtShort(Math.abs(diff)) : ''}</div></div>
      <div class="inc-kpi"><div class="k-l">За 12 месяцев</div><div class="k-v">${fmtSum(d.year_total)}</div><div class="k-s">деньгами, все оплаты</div></div>
      <div class="inc-kpi"><div class="k-l">Ожидается за 30 дней</div><div class="k-v">${fmtSum(d.expected_30)}</div><div class="k-s">${d.expected.length} точек продлевают</div></div>
    </div>`;
  const pend = d.pending.count ? `<div class="inc-alert" onclick="openPendingChecks()">🧾 <span style="flex:1;">Чеков на проверке: ${d.pending.count} на ${fmtSum(d.pending.sum)} сум</span><i class="fa-solid fa-chevron-right"></i></div>` : '';
  const series = incMode === 'received' ? d.received : d.spread;
  const max = Math.max(1, ...series);
  const bars = series.map((v, i) => {
    const m = Number(d.months[i].slice(5)) - 1;
    return `<div class="inc-bar ${i === series.length - 1 ? 'cur' : ''} ${v === max ? 'mx' : ''}" title="${MONTHS_RU[m]} ${d.months[i].slice(0, 4)}: ${fmtSum(v)} сум">
      <span class="v">${v ? fmtShort(v) : ''}</span><div class="b" style="height:${Math.round(v / max * 100)}%;"></div><span class="m">${MONTHS_RU[m]}</span></div>`;
  }).join('');
  const chart = `
    <div class="inc-card">
      <h3>Оплаты по месяцам
        <span class="inc-seg"><button class="${incMode === 'received' ? 'on' : ''}" onclick="setIncMode('received')">Получено</button><button class="${incMode === 'spread' ? 'on' : ''}" onclick="setIncMode('spread')">В пересчёте на месяц</button></span>
      </h3>
      <div class="inc-bars">${bars}</div>
      <div class="hint-text" style="margin-top:8px;">${incMode === 'received' ? 'Деньги в месяц, когда оплата подтверждена. Оплата за год даёт один высокий столбик.' : 'Оплата за N месяцев разложена поровну на эти месяцы — так видно реальный доход в месяц.'}</div>
    </div>`;
  const parts = [
    ['Платят', c.paying, '#16A34A'], ['∞ Бессрочные', c.lifetime, '#0F52BA'], ['Без даты', c.unset, '#94A3B8'],
    ['Заблокированы', c.blocked, '#DC2626'], ['Выключены', c.off, '#CBD5E1']];
  const totalPts = Math.max(1, parts.reduce((a, p) => a + p[1], 0));
  const pts = `
    <div class="inc-card">
      <h3>Точки <span class="hint-text" style="font-weight:600;">всего ${c.total}${c.soon ? ' · скоро истекает: ' + c.soon : ''}</span></h3>
      <div class="inc-stack">${parts.filter(p => p[1]).map(p => `<div style="width:${p[1] / totalPts * 100}%; background:${p[2]};"></div>`).join('')}</div>
      <div class="inc-leg">${parts.map(p => `<span><i style="background:${p[2]};"></i>${p[0]}: <b>${p[1]}</b></span>`).join('')}</div>
      <div class="hint-text" style="margin-top:10px;">Цена: главная ${fmtSum(d.price_main)} + филиал ${fmtSum(d.price_branch)} сум/мес</div>
      ${d.lifetime_sales || d.branch_cash ? `<div class="inc-row" style="margin-top:6px;"><div><b>Разовые продажи</b><div class="r-s">∞ точек: ${d.lifetime_sales}${d.branch_cash ? ' · филиалов вручную: ' + d.branch_cash : ''}</div></div><span class="r-v">${fmtSum(d.lifetime_sum + d.branch_cash_sum)}</span></div>` : ''}
    </div>`;
  const tTotal = Math.max(1, Object.values(d.terms).reduce((a, b) => a + b, 0));
  const terms = `
    <div class="inc-card">
      <h3>Какой срок выбирают</h3>
      ${[1, 3, 6, 12].map(m => `<div class="inc-term"><span class="t-n">${m} мес</span><span class="t-bar"><div style="width:${d.terms[m] / tTotal * 100}%;"></div></span><span class="t-c">${d.terms[m]} · ${Math.round(d.terms[m] / tTotal * 100)}%</span></div>`).join('')}
    </div>`;
  const exp = `
    <div class="inc-card">
      <h3>Продлевают в ближайшие 30 дней</h3>
      ${d.expected.length ? d.expected.map(x => `<div class="inc-row"><div><b>${escapeHtml(x.name)}</b><div class="r-s">до ${fmtDay(x.paid_until)} · ${x.days === 0 ? 'сегодня последний день' : 'через ' + x.days + ' дн.'}</div></div><span class="r-v">${fmtSum(x.monthly)}/мес</span></div>`).join('') : '<div class="hint-text">Никто — всё оплачено надолго вперёд.</div>'}
    </div>`;
  const blk = d.blocked.length ? `
    <div class="inc-card">
      <h3>Не продлили <span class="hint-text" style="font-weight:600;">теряем ${fmtSum(d.blocked.reduce((a, x) => a + x.monthly, 0))} сум/мес</span></h3>
      ${d.blocked.map(x => `<div class="inc-row"><div><b>${escapeHtml(x.name)}</b><div class="r-s">заблокирована ${x.days} дн. · было оплачено до ${fmtDay(x.paid_until)}</div></div><span class="r-v" style="color:#B3241C;">${fmtSum(x.monthly)}/мес</span></div>`).join('')}
    </div>` : '';
  const kindTxt = j => j.kind === 'lifetime' ? '∞ бессрочная' : j.kind === 'branches' ? 'новые филиалы' : `${j.months} мес${j.kind === 'both' ? ' + филиалы' : ''}`;
  const jr = `
    <div class="inc-card">
      <h3>Последние оплаты</h3>
      ${d.journal.length ? d.journal.map(j => `<div class="inc-row"><div><b>${escapeHtml(j.name)}</b><div class="r-s">${fmtDay(j.date)} · ${kindTxt(j)} · ${j.method === 'cash' ? 'наличные' : 'перевод'}</div>
        <div class="inc-jact">${j.method === 'cash' ? `<button onclick="editPayAmount(${j.id}, ${j.amount || 0})">✏️ сумма</button>` : ''}<button onclick="cancelPayment(${j.id})">🗑 убрать</button></div></div>
        <span class="r-v">${j.amount ? fmtSum(j.amount) : `<span style="color:#B45309; font-family:inherit; font-size:12px;">сумма не указана</span>`}</span></div>`).join('') : '<div class="hint-text">Оплат пока нет.</div>'}
    </div>`;
  document.getElementById('admIncome').innerHTML = kpis + pend + chart + pts + terms + exp + blk + jr;
}

async function loadSubPanel() {
  try {
    const [pr, sr] = await Promise.all([fetch('/api/admin/sub/payments?status=pending'), fetch('/api/admin/sub/settings')]);
    const pd = await pr.json(), sd = await sr.json();
    const box = document.getElementById('subPayments');
    const list = (pd.payments || []);
    box.innerHTML = list.length ? list.map(p => `
      <div class="pay-item"><div class="pay-cap">${escapeHtml(p.caption)}</div><div class="hint-text" style="margin-top:4px;">отправлен ${escapeHtml(p.created_at || '')}</div>
        <div class="pay-act">
          ${p.has_receipt ? `<a href="/api/admin/sub/receipt/${p.id}" target="_blank" rel="noopener">открыть чек</a>` : ''}
          <button class="ok" onclick="decideSub(${p.id}, 1)">✅ Подтвердить</button>
          <button class="no" onclick="decideSub(${p.id}, 0)">❌ Отклонить</button>
        </div>
      </div>`).join('') : '<div class="hint-text">Новых чеков нет.</div>';
    const sec = document.getElementById('secSub');
    document.getElementById('subSecSub').textContent = list.length ? `чеков на проверке: ${list.length}` : 'проверка оплат, карта, цены';
    if (list.length && !sec.dataset.autoOpened) { sec.open = true; sec.dataset.autoOpened = '1'; }
    const st = sd.settings || {};
    ['card_number', 'card_holder', 'support_contact', 'price_main', 'price_branch', 'disc_1', 'disc_3', 'disc_6', 'disc_12']
      .forEach(k => { const el = document.getElementById('ss_' + k); if (el && document.activeElement !== el) el.value = st[k] == null ? '' : st[k]; });
  } catch (e) {}
}

async function saveSubSettings() {
  const body = {};
  ['card_number', 'card_holder', 'support_contact'].forEach(k => body[k] = document.getElementById('ss_' + k).value.trim());
  for (const k of ['price_main', 'price_branch', 'disc_1', 'disc_3', 'disc_6', 'disc_12']) {
    const raw = document.getElementById('ss_' + k).value.replace(/[^0-9]/g, '');
    if (raw === '') { showMsg('Заполните все цены и скидки', false); return; }
    body[k] = Number(raw);
  }
  const res = await fetch('/api/admin/sub/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Сохранено', true); loadSubPanel(); loadShops(); } else showMsg('Ошибка: ' + data.error, false);
}

async function loadShops() {
  const res = await fetch('/api/admin/shops');
  allShopsCache = await res.json();

  // список известных групп — для автодополнения в форме создания новой точки
  const groupNames = [...new Set(allShopsCache.map(s => s.client_group).filter(Boolean))].sort();
  document.getElementById('clientGroupsList').innerHTML = groupNames.map(g => `<option value="${escapeHtml(g)}">`).join('');

  const st = document.getElementById('admStats');
  const active = allShopsCache.filter(s => s.is_active).length;
  const clients = allShopsCache.reduce((a, s) => a + (s.client_count || 0), 0);
  st.innerHTML = `
    <div class="adm-stat"><b>${allShopsCache.length}</b><span>точек</span></div>
    <div class="adm-stat"><b>${active}</b><span>активных</span></div>
    <div class="adm-stat"><b>${clients.toLocaleString('ru-RU')}</b><span>клиентов</span></div>`;
  filterShops();
}

let shopFilter = 'all';
function setShopFilter(f) {
  shopFilter = f;
  document.querySelectorAll('#admFilters button').forEach(b => b.classList.toggle('on', b.dataset.f === f));
  filterShops();
}

function filterShops() {
  const q = document.getElementById('shopSearch').value.trim().toLowerCase();
  const filtered = allShopsCache.filter(s =>
    (!q || (s.shop_name || '').toLowerCase().includes(q) ||
      (s.username || '').toLowerCase().includes(q) ||
      (s.phone || '').toLowerCase().includes(q)) &&
    (shopFilter === 'all' ||
      (shopFilter === 'active' && s.is_active) ||
      (shopFilter === 'off' && !s.is_active) ||
      (shopFilter === 'notg' && !s.notify_telegram_id) ||
      (shopFilter === 'debt' && s.sub && s.sub.expired) ||
      (shopFilter === 'soon' && s.sub && !s.sub.lifetime && s.sub.days_left !== null && s.sub.days_left >= 0 && s.sub.days_left <= 5) ||
      (shopFilter === 'check' && s.sub && s.sub.pending_payment) ||
      (shopFilter === 'life' && s.sub && s.sub.lifetime) ||
      (shopFilter === 'unset' && s.sub && !s.sub.lifetime && !s.sub.paid_until) ||
      (shopFilter === 'trial' && s.sub && s.sub.trial))
  );
  renderShopsTable(filtered);
}

function renderShopsTable(shops) {
  // карточки вместо широкой таблицы: на телефоне всё видно без прокрутки вбок.
  // id элементов прежние — на них опираются функции изменения/сотрудников/филиалов.
  const grouped = {};
  const standalone = [];
  shops.forEach(s => {
    if (s.client_group) (grouped[s.client_group] = grouped[s.client_group] || []).push(s);
    else standalone.push(s);
  });

  function renderShopCard(s) {
    const name = escapeHtml(JSON.stringify(s.username));
    const link = s.owner_link ? escapeHtml(JSON.stringify(s.owner_link)) : null;
    return `
    <div class="shop-card ${s.is_active ? '' : 'off'}">
      <div class="sc-head">
        <div style="min-width:0;">
          <div class="sc-name" id="name_view_${s.id}">${escapeHtml(s.shop_name || '—')}</div>
          <div class="sc-login">@<span id="username_view_${s.id}">${escapeHtml(s.username)}</span></div>
          <div class="sc-edit" id="name_edit_${s.id}" style="display:none;">
            <input id="name_input_${s.id}" value="${escapeHtml(s.shop_name || '')}" placeholder="Название">
          </div>
          <div class="sc-edit" id="username_edit_${s.id}" style="display:none;">
            <input id="username_input_${s.id}" value="${escapeHtml(s.username)}" placeholder="Логин">
            <button class="badge active" style="margin-top:6px; padding:6px 12px;" onclick="saveIdentity(${s.id})">💾 сохранить</button>
          </div>
        </div>
        <button class="badge ${s.is_active ? 'active' : 'inactive'}" style="flex:none;" onclick="toggleShop(${s.id}, ${s.is_active ? 0 : 1})">${s.is_active ? '● активна' : '○ выключена'}</button>
      </div>

      <div class="sc-meta">
        <span><i class="fa-solid fa-users"></i> ${s.client_count} клиентов</span>
        ${s.phone ? `<span><i class="fa-solid fa-phone"></i> ${escapeHtml(s.phone)}</span>` : ''}
        ${s.notify_telegram_id ? '<span class="ok"><i class="fa-brands fa-telegram"></i> Telegram</span>' : '<span class="no"><i class="fa-brands fa-telegram"></i> нет Telegram</span>'}
      </div>
      ${renderSubBlock(s)}

      <div class="sc-toggles">
        <span>SMS<button class="sw ${s.sms_enabled ? 'on' : ''}" title="${s.sms_enabled ? 'выключить' : 'включить'}" onclick="toggleSms(${s.id}, ${s.sms_enabled ? 0 : 1})"></button></span>
        <span>Склад<button class="sw ${s.warehouse_enabled ? 'on' : ''}" title="${s.warehouse_enabled ? 'выключить' : 'включить'}" onclick="toggleWarehouse(${s.id}, ${s.warehouse_enabled ? 0 : 1})"></button></span>
        <span class="grp-chip">🏷<input value="${escapeHtml(s.client_group || '')}" list="clientGroupsList" placeholder="без группы" onchange="setClientGroup(${s.id}, this.value)"></span>
      </div>

      <div class="sc-grid">
        <button class="sc-tile" id="tile-br-${s.id}" onclick="toggleBranches(${s.id}); this.classList.toggle('open')"><i class="fa-solid fa-building"></i>Филиалы</button>
        <button class="sc-tile" id="tile-emp-${s.id}" onclick="toggleEmployees(${s.id}); this.classList.toggle('open')"><i class="fa-solid fa-users"></i>Сотрудники</button>
        <button class="sc-tile" onclick="toggleIdentityEdit(${s.id}); this.classList.toggle('open')"><i class="fa-solid fa-pen"></i>Изменить</button>
        <button class="sc-tile" onclick="resetPassword(${s.id}, ${name})"><i class="fa-solid fa-key"></i>Пароль</button>
        <button class="sc-tile" ${link ? `onclick="copyOwnerLink(${link}, this)"` : 'disabled title="ссылки пока нет"'}><i class="fa-solid fa-link"></i>Ссылка</button>
        <button class="sc-tile" onclick="testNotifyTelegram(${s.id})"><i class="fa-solid fa-paper-plane"></i>Тест TG</button>
      </div>

      <details style="margin-top:10px;">
        <summary style="font-size:12px; color:var(--hint); cursor:pointer;">Telegram ID вручную</summary>
        <div style="display:flex; gap:6px; margin-top:6px;">
          <input id="notify_id_${s.id}" value="${escapeHtml(s.notify_telegram_id || '')}" placeholder="123456789" style="max-width:180px; font-size:13px; padding:7px 9px;">
          <button class="badge active" style="padding:6px 12px;" onclick="saveNotifyTelegram(${s.id})">сохранить</button>
        </div>
      </details>

      <div id="branch-row-${s.id}" style="display:none;"><div class="sc-panel" id="branch-panel-${s.id}">…</div></div>
      <div id="emp-row-${s.id}" style="display:none;"><div class="sc-panel" id="emp-panel-${s.id}">…</div></div>
    </div>`;
  }

  let html = '';
  Object.keys(grouped).sort().forEach(group => {
    html += `<div class="grp-title">🏷️ ${escapeHtml(group)} · ${grouped[group].length}</div>`;
    grouped[group].forEach(s => html += renderShopCard(s));
  });
  if (standalone.length && Object.keys(grouped).length) html += `<div class="grp-title" style="color:#64748B;">Без группы · ${standalone.length}</div>`;
  standalone.forEach(s => html += renderShopCard(s));

  document.getElementById('shops-body').innerHTML = html || `<div class="hint-text" style="padding:14px;">Ничего не найдено.</div>`;
}

async function setClientGroup(shopId, value) {
  await fetch(`/api/admin/shops/${shopId}/client_group`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({client_group: value.trim()})
  });
  loadShops();
}

async function toggleEmployees(shopId) {
  const row = document.getElementById(`emp-row-${shopId}`);
  const opening = row.style.display === 'none';
  row.style.display = opening ? '' : 'none';
  if (opening) await loadEmployees(shopId);
}

async function loadEmployees(shopId) {
  const panel = document.getElementById(`emp-panel-${shopId}`);
  const res = await fetch(`/api/admin/shops/${shopId}/employees`);
  const employees = await res.json();
  const list = employees.length ? employees.map(e => `
    <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px dashed var(--border); font-size:13px;">
      <span style="${e.is_active ? '' : 'opacity:.55;'}">${escapeHtml(e.full_name || e.username)} <span class="hint-text">(${escapeHtml(e.username)})</span>${e.is_active ? '' : ' <span class="hint-text">· выключен</span>'}</span>
      <span style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:flex-end;">
        <button class="badge" style="background:var(--border);color:var(--hint);" onclick="toggleEmployeeActive(${e.id}, ${shopId}, ${e.is_active ? 0 : 1})">${e.is_active ? 'выключить' : 'включить'}</button>
        <button class="badge" style="background:var(--border);color:var(--hint);" onclick="resetEmployeePassword(${e.id}, ${shopId}, ${escapeHtml(JSON.stringify(e.username))})">сбросить</button>
        <button class="badge inactive" onclick="deleteEmployee(${e.id}, ${shopId}, ${escapeHtml(JSON.stringify(e.username))})">удалить</button>
      </span>
    </div>
  `).join('') : `<div class="hint-text">Пока нет сотрудников у этой точки.</div>`;
  panel.innerHTML = `
    <div style="font-weight:700; font-size:13px; margin-bottom:8px;">Сотрудники точки (ограниченный доступ — без статистики, прибыли, экспорта, склада)</div>
    ${list}
    <div style="display:flex; gap:6px; margin-top:10px;">
      <input id="new-emp-username-${shopId}" placeholder="логин сотрудника" style="flex:1;">
      <button class="badge active" style="padding:6px 14px;" onclick="createEmployee(${shopId})">+ добавить</button>
    </div>
  `;
}

async function createEmployee(shopId) {
  const input = document.getElementById(`new-emp-username-${shopId}`);
  const username = input.value.trim();
  if (!username) return;
  const res = await fetch(`/api/admin/shops/${shopId}/employees`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username})
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Сотрудник «${username}» создан. Пароль (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
    loadEmployees(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function resetEmployeePassword(employeeId, shopId, username) {
  if (!confirm(`Сбросить пароль для сотрудника «${username}»?`)) return;
  const res = await fetch(`/api/admin/employees/${employeeId}/reset_password`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shop_id: shopId})
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Новый пароль для «${username}» (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
    loadEmployees(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function toggleEmployeeActive(employeeId, shopId, on) {
  const res = await fetch(`/api/admin/employees/${employeeId}/active`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shop_id: shopId, active: !!on})
  });
  const data = await res.json();
  if (data.ok) loadEmployees(shopId); else showMsg('Ошибка: ' + data.error, false);
}

async function deleteEmployee(employeeId, shopId, username) {
  if (!confirm(`Удалить сотрудника «${username}»? Он больше не сможет войти.`)) return;
  const res = await fetch(`/api/admin/employees/${employeeId}?shop_id=${shopId}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) { loadEmployees(shopId); } else { showMsg('Ошибка: ' + data.error, false); }
}

async function toggleBranches(shopId) {
  const row = document.getElementById(`branch-row-${shopId}`);
  const opening = row.style.display === 'none';
  row.style.display = opening ? '' : 'none';
  if (opening) await loadBranches(shopId);
}

async function loadBranches(shopId) {
  const panel = document.getElementById(`branch-panel-${shopId}`);
  const res = await fetch(`/api/admin/shops/${shopId}/branches`);
  const branches = await res.json();
  const list = branches.length ? branches.map(b => `
    <div style="padding:8px 0; border-bottom:1px dashed var(--border); font-size:13px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span>${escapeHtml(b.shop_name || b.username)} <span class="hint-text">(${b.username}, клиентов: ${b.client_count})</span></span>
        <span style="display:flex; align-items:center; gap:8px;">
          <span class="hint-text">🔒 скрыт</span>
          <button class="badge" style="background:var(--border);color:var(--hint);" onclick="resetPassword(${b.id}, ${escapeHtml(JSON.stringify(b.username))})">сбросить</button>
        </span>
      </div>
      <div id="branch-edit-${b.id}" style="display:none;"></div>
      <div style="display:flex; gap:6px; flex-wrap:wrap;">
        ${b.branch_pending ? `<span class="sub-pill warn" style="align-self:center;">⏳ ждёт оплаты</span><button class="badge active" onclick="markBranchPaid(${shopId}, ${b.id}, ${escapeHtml(JSON.stringify(b.shop_name || b.username))})">✅ отметить оплату</button>` : ''}
        <button class="badge ${b.is_active ? 'active' : 'inactive'}" onclick="toggleBranchField(${shopId}, ${b.id}, 'toggle', ${b.is_active ? 0 : 1})">${b.is_active ? 'активен' : 'выключен'}</button>
        <button class="badge ${b.sms_enabled ? 'active' : 'inactive'}" onclick="toggleBranchField(${shopId}, ${b.id}, 'toggle_sms', ${b.sms_enabled ? 0 : 1})">SMS: ${b.sms_enabled ? 'включён' : 'выключен'}</button>
        <button class="badge ${b.warehouse_enabled ? 'active' : 'inactive'}" onclick="toggleBranchField(${shopId}, ${b.id}, 'toggle_warehouse', ${b.warehouse_enabled ? 0 : 1})">Склад: ${b.warehouse_enabled ? 'включён' : 'выключен'}</button>
        <button class="badge" style="background:#EFF6FF; color:#0F52BA;" onclick='openBranchEdit(${shopId}, ${escapeHtml(JSON.stringify(b))})'>✏️ изменить</button>
        <button class="badge" style="background:#FEF2F2; color:#B3241C;" onclick="deleteBranch(${shopId}, ${b.id})">🗑 удалить</button>
      </div>
    </div>
  `).join('') : `<div class="hint-text">У этой точки пока нет филиалов.</div>`;
  panel.innerHTML = `
    <div style="font-weight:700; font-size:13px; margin-bottom:8px;">Филиалы (полноценные точки — свой склад, своя база, без цены закупки и без прибыли по отдельности)</div>
    ${list}
    <details style="margin-top:12px; padding-top:10px; border-top:1px solid var(--border);">
      <summary style="cursor:pointer; font-weight:700; color:#059669; font-size:13px; padding:4px 0;">+ Добавить филиал</summary>
      <div class="field" style="margin-top:8px;">
        <label>Название филиала</label>
        <input id="new-branch-name-${shopId}" placeholder="название филиала">
      </div>
      <div class="row2">
        <div class="field">
          <label>Логин</label>
          <input id="new-branch-username-${shopId}" placeholder="логин">
        </div>
        <div class="field">
          <label>Пароль (пусто = сгенерировать)</label>
          <input id="new-branch-password-${shopId}" placeholder="необязательно">
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label>Телефон филиала</label>
          <input id="new-branch-phone-${shopId}" placeholder="+998901112233">
        </div>
        <div class="field">
          <label>Telegram ID для уведомлений (необяз.)</label>
          <input id="new-branch-notify-${shopId}" placeholder="123456789">
        </div>
      </div>
      <div class="field">
        <label>Адрес</label>
        <input id="new-branch-address-${shopId}" placeholder="Наманган, ул. ...">
      </div>
      <div class="field">
        <label>Локация (необяз.) — широта и долгота из Google Карт через запятую</label>
        <input id="new-branch-location-${shopId}" placeholder="40.782123, 72.344567">
      </div>
      <button class="badge active" style="padding:6px 14px; margin-top:6px;" onclick="createBranch(${shopId})">+ добавить филиал</button>
    </details>
  `;
}

function openBranchEdit(shopId, b) {
  const box = document.getElementById(`branch-edit-${b.id}`);
  if (box.style.display !== 'none') { box.style.display = 'none'; return; }
  const v = x => escapeHtml(x == null ? '' : String(x));
  const loc = (b.lat != null && b.lon != null) ? `${b.lat}, ${b.lon}` : '';
  box.innerHTML = `
    <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:12px; padding:12px; margin:8px 0;">
      <div class="row2">
        <div class="field"><label>Название филиала</label><input id="be-name-${b.id}" value="${v(b.shop_name)}"></div>
        <div class="field"><label>Логин</label><input id="be-user-${b.id}" value="${v(b.username)}"></div>
      </div>
      <div class="row2">
        <div class="field"><label>Телефон</label><input id="be-phone-${b.id}" value="${v(b.phone)}" placeholder="+998901112233"></div>
        <div class="field"><label>Telegram ID для уведомлений</label><input id="be-notify-${b.id}" value="${v(b.notify_telegram_id)}"></div>
      </div>
      <div class="field"><label>Адрес</label><input id="be-address-${b.id}" value="${v(b.address)}"></div>
      <div class="row2">
        <div class="field"><label>Часы работы</label><input id="be-hours-${b.id}" value="${v(b.hours)}" placeholder="09:00–19:00"></div>
        <div class="field"><label>Локация (широта, долгота)</label><input id="be-loc-${b.id}" value="${v(loc)}" placeholder="40.782123, 72.344567"></div>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap;">
        <button class="badge active" style="padding:6px 14px;" onclick="saveBranchEdit(${shopId}, ${b.id})">💾 сохранить</button>
        <button class="badge" style="padding:6px 14px; background:var(--border); color:var(--hint);" onclick="document.getElementById('branch-edit-${b.id}').style.display='none'">отмена</button>
      </div>
      <div class="hint-text" style="margin-top:6px;">Пароль меняется кнопкой «сбросить».</div>
    </div>`;
  box.style.display = 'block';
}

async function saveBranchEdit(shopId, branchId) {
  const g = id => document.getElementById(`${id}-${branchId}`).value.trim();
  const payload = {
    shop_name: g('be-name'), username: g('be-user'), phone: g('be-phone'),
    notify_telegram_id: g('be-notify'), address: g('be-address'), hours: g('be-hours'),
  };
  if (!payload.shop_name || !payload.username) { showMsg('Укажите название и логин.', false); return; }
  const loc = g('be-loc');
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length !== 2 || isNaN(parseFloat(parts[0])) || isNaN(parseFloat(parts[1]))) {
      showMsg('Локация должна быть в формате: широта, долгота (два числа через запятую).', false);
      return;
    }
    payload.lat = parts[0]; payload.lon = parts[1];
  } else {
    payload.lat = ''; payload.lon = '';
  }
  const res = await fetch(`/api/admin/branches/${branchId}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Филиал сохранён', true);
    loadBranches(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function deleteBranch(shopId, branchId) {
  const pre = await (await fetch(`/api/admin/branches/${branchId}/delete_preview`)).json();
  if (!pre.ok) { showMsg('Ошибка: ' + pre.error, false); return; }
  const c = pre.counts;
  const warn = `Удалить филиал «${pre.name}» НАВСЕГДА?\n\n` +
    `Вместе с ним удалятся: клиентов — ${c.clients}, машин — ${c.cars}, записей о заменах — ${c.services}, ` +
    `товаров склада — ${c.products}, долгов — ${c.debts}, сотрудников — ${c.employees}.\n\n` +
    `Перед удалением вся база автоматически отправится резервной копией в Telegram.\n` +
    `Если нужно просто закрыть доступ и сохранить историю — нажмите «Отмена» и используйте кнопку «активен/выключен».`;
  if (!confirm(warn)) return;
  const typed = prompt(`Для подтверждения впишите название филиала точно так:\n${pre.name}`);
  if (typed === null) return;
  if (typed.trim() !== pre.name) { showMsg('Название не совпало — филиал не удалён.', false); return; }
  showMsg('⏳ Отправляю резервную копию и удаляю филиал…', true);
  const res = await fetch(`/api/admin/branches/${branchId}`, {
    method: 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ confirm_name: typed.trim() })
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`🗑 Филиал «${escapeHtml(pre.name)}» удалён. Резервная копия базы до удаления — в Telegram.`);
    loadBranches(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function createBranch(shopId) {
  const shopName = document.getElementById(`new-branch-name-${shopId}`).value.trim();
  const username = document.getElementById(`new-branch-username-${shopId}`).value.trim();
  if (!shopName || !username) { showMsg('Укажите название филиала и логин.', false); return; }
  const payload = {
    shop_name: shopName,
    username,
    password: document.getElementById(`new-branch-password-${shopId}`).value.trim(),
    phone: document.getElementById(`new-branch-phone-${shopId}`).value.trim(),
    notify_telegram_id: document.getElementById(`new-branch-notify-${shopId}`).value.trim(),
    address: document.getElementById(`new-branch-address-${shopId}`).value.trim(),
  };
  const loc = document.getElementById(`new-branch-location-${shopId}`).value.trim();
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length === 2 && !isNaN(parseFloat(parts[0])) && !isNaN(parseFloat(parts[1]))) {
      payload.lat = parts[0];
      payload.lon = parts[1];
    } else {
      showMsg('Локация должна быть в формате: широта, долгота (два числа через запятую).', false);
      return;
    }
  }
  const res = await fetch(`/api/admin/shops/${shopId}/branches`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Филиал «${shopName}» создан. Логин: <b>${username}</b>, пароль (больше не увидите — сохраните сейчас): <b>${data.password}</b>` +
      (data.sub_pending ? '<br>⏳ Филиал заработает после оплаты: владелец оплатит его в разделе «Подписка», или нажми «✅ отметить оплату» (наличные / 100 $ у бессрочной сети).' : ''));
    loadBranches(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function toggleWarehouse(id, makeEnabled) {
  await fetch(`/api/admin/shops/${id}/toggle_warehouse`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: !!makeEnabled})
  });
  loadShops();
}

async function toggleShop(id, makeActive) {
  await fetch(`/api/admin/shops/${id}/toggle`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({active: !!makeActive})
  });
  loadShops();
}

async function toggleBranchField(headShopId, branchId, endpoint, value) {
  const bodyKey = endpoint === 'toggle' ? 'active' : 'enabled';
  await fetch(`/api/admin/shops/${branchId}/${endpoint}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({[bodyKey]: !!value})
  });
  loadBranches(headShopId);
}

async function toggleSms(id, makeEnabled) {
  await fetch(`/api/admin/shops/${id}/toggle_sms`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: !!makeEnabled})
  });
  loadShops();
}

async function triggerBackupNow() {
  const btn = event.target;
  const resultEl = document.getElementById('backupResult');
  btn.disabled = true;
  btn.textContent = 'Отправляю...';
  resultEl.innerHTML = '';
  try {
    const res = await fetch('/api/admin/backup_now', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      const botLine = data.bot_username
        ? `Открой чат с ботом <b>@${data.bot_username}</b> в Telegram — <a href="https://t.me/${data.bot_username}" target="_blank" style="color:#0F52BA; font-weight:700;">нажми сюда, чтобы открыть сразу</a>.`
        : `Имя бота не настроено на сервере (BOT_USERNAME) — но сообщение реально ушло, просто не могу подсказать точный чат.`;
      resultEl.innerHTML = `<div class="msg ok">✅ Копия отправлена в Telegram (${data.size_mb} МБ). ${botLine}</div>`;
    } else {
      resultEl.innerHTML = `<div class="msg err">❌ Не отправилось: ${data.error}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="msg err">❌ Ошибка сети: ${e}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Отправить сейчас';
  }
}

async function triggerRestore() {
  const fileInput = document.getElementById('restore_file');
  const confirmInput = document.getElementById('restore_confirm');
  const resultEl = document.getElementById('restoreResult');
  const file = fileInput.files[0];
  if (!file) { resultEl.innerHTML = `<div class="msg err">Выбери файл резервной копии</div>`; return; }
  if (confirmInput.value.trim() !== 'ЗАМЕНИТЬ') {
    resultEl.innerHTML = `<div class="msg err">Впиши точно слово ЗАМЕНИТЬ, чтобы подтвердить</div>`;
    return;
  }
  if (!confirm(`Точно заменить ВСЮ текущую базу файлом «${file.name}»? Это необратимо без отдельной копии.`)) return;

  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Восстанавливаю...';
  resultEl.innerHTML = '';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('confirm', confirmInput.value.trim());
    const res = await fetch('/api/admin/restore_backup', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.ok) {
      resultEl.innerHTML = `<div class="msg ok">✅ База восстановлена. Копия прежнего состояния отправлена тебе в Telegram на всякий случай. Обнови страницу.</div>`;
      confirmInput.value = '';
      fileInput.value = '';
    } else {
      resultEl.innerHTML = `<div class="msg err">❌ Не удалось: ${data.error}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="msg err">❌ Ошибка сети: ${e}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Восстановить из этого файла';
  }
}

function toggleIdentityEdit(id) {
  const nameEdit = document.getElementById(`name_edit_${id}`);
  const usernameEdit = document.getElementById(`username_edit_${id}`);
  const isOpen = nameEdit.style.display !== 'none';
  nameEdit.style.display = isOpen ? 'none' : 'block';
  usernameEdit.style.display = isOpen ? 'none' : 'block';
}

async function saveIdentity(id) {
  const shop_name = document.getElementById(`name_input_${id}`).value.trim();
  const username = document.getElementById(`username_input_${id}`).value.trim();
  if (!shop_name || !username) { showMsg('Укажите и название, и логин.', false); return; }
  const res = await fetch(`/api/admin/shops/${id}/identity`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shop_name, username})
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById(`name_view_${id}`).textContent = data.shop_name;
    document.getElementById(`username_view_${id}`).textContent = data.username;
    toggleIdentityEdit(id);
    showMsg('✅ Название и логин обновлены', true);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function resetPassword(id, username) {
  if (!confirm(`Сбросить пароль для «${username}»? Старый пароль перестанет работать.`)) return;
  const res = await fetch(`/api/admin/shops/${id}/reset_password`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Новый пароль для «${username}» (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
    loadShops();
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

function copyOwnerLink(link, btn) {
  const done = () => {
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-check" style="color:#16A34A;"></i>скопировано';
    setTimeout(() => { btn.innerHTML = original; }, 1500);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(done).catch(() => {
      prompt('Скопируйте ссылку вручную:', link);
    });
  } else {
    prompt('Скопируйте ссылку вручную:', link);
  }
}

async function saveNotifyTelegram(id) {
  const notify_telegram_id = document.getElementById(`notify_id_${id}`).value.trim();
  const res = await fetch(`/api/admin/shops/${id}/notify_telegram`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({notify_telegram_id}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Telegram ID сохранён', true);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function testNotifyTelegram(id) {
  const res = await fetch(`/api/admin/shops/${id}/test_telegram`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Тестовое сообщение доставлено — связь работает', true);
  } else {
    showMsgSticky(`❌ Не удалось отправить: ${data.error}`);
  }
}

async function createShop() {
  const payload = {
    shop_name: document.getElementById('new_shop_name').value.trim(),
    client_group: document.getElementById('new_client_group').value.trim(),
    username: document.getElementById('new_username').value.trim(),
    password: document.getElementById('new_password').value.trim(),
    phone: document.getElementById('new_phone').value.trim(),
    notify_telegram_id: document.getElementById('new_notify_id').value.trim(),
    address: document.getElementById('new_address').value.trim(),
  };
  const loc = document.getElementById('new_location').value.trim();
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length === 2 && !isNaN(parseFloat(parts[0])) && !isNaN(parseFloat(parts[1]))) {
      payload.lat = parts[0];
      payload.lon = parts[1];
    } else {
      showMsg('Локация должна быть в формате: широта, долгота (два числа через запятую).', false);
      return;
    }
  }
  if (!payload.shop_name || !payload.username) {
    showMsg('Заполните хотя бы название точки и логин.', false);
    return;
  }
  const res = await fetch('/api/admin/shops', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('newCreds').innerHTML =
      `<div class="new-creds">✅ Точка создана. Логин: <b>${data.username}</b>, пароль: <b>${data.password}</b><br>
       Сохраните пароль сейчас — второй раз он нигде не показывается.</div>`;
    ['new_shop_name','new_client_group','new_username','new_password','new_phone','new_notify_id','new_address','new_location'].forEach(id => document.getElementById(id).value = '');
    loadShops();
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}


// Защита от двойного нажатия: пока действие выполняется (запрос на сервер),
// повторные нажатия той же кнопки игнорируются — иначе на медленном
// интернете можно случайно дважды внести замену, списать товар или оплату.
function guardOnce(names) {
  names.forEach(name => {
    const fn = window[name];
    if (typeof fn !== 'function' || fn.__guarded) return;
    let busy = false;
    const wrapped = async function (...args) {
      if (busy) return;
      busy = true;
      // нажатая кнопка тускнеет, пока ждём сервер — на слабом интернете
      // видно, что нажатие принято и запрос идёт
      const ev = window.event;
      const btn = ev && ev.currentTarget && ev.currentTarget.tagName === 'BUTTON' ? ev.currentTarget : null;
      const wasDisabled = btn ? btn.disabled : false;
      if (btn) { btn.disabled = true; btn.classList.add('net-busy'); }
      try { return await fn.apply(this, args); } finally {
        busy = false;
        if (btn) { btn.disabled = wasDisabled; btn.classList.remove('net-busy'); }
      }
    };
    wrapped.__guarded = true;
    window[name] = wrapped;
  });
}
guardOnce(['createShop', 'createBranch', 'createEmployee', 'toggleEmployeeActive', 'saveBranchEdit', 'deleteBranch',
  'deleteEmployee', 'resetPassword', 'resetEmployeePassword', 'saveIdentity', 'saveNotifyTelegram',
  'triggerBackupNow', 'triggerRestore', 'toggleShop', 'toggleSms', 'toggleWarehouse', 'toggleBranchField',
  'subExtend', 'subSetDate', 'subLifetime', 'decideSub', 'markBranchPaid', 'saveSubSettings',
  'subPrice', 'editPayAmount', 'cancelPayment', 'decideReg']);
loadShops();
loadSubPanel();
loadRegs();
setInterval(() => { if (!document.hidden) loadRegs(); }, 60000);
// ---------- Карта точек с аналитикой ----------
let MAP = null, MAPDATA = null, mapLayer = null, mapDays = 30, mapMetric = 'count', mapFilt = 'all', mapGroupSel = '';
let mapMarkers = {}, mapPickId = null, mapFitted = false, mapSaving = false, leafletPromise = null;
const MAP_COLORS = { green: '#16A34A', yellow: '#EAB308', red: '#DC2626', off: '#94A3B8' };

function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
    document.head.appendChild(css);
    const js = document.createElement('script');
    js.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
    js.onload = () => resolve();
    js.onerror = () => { leafletPromise = null; reject(new Error('leaflet')); };
    document.head.appendChild(js);
  });
  return leafletPromise;
}

function mapStatus(p) {
  if (!p.is_active) return 'off';
  if (p.days_idle === null || p.days_idle === undefined) return 'red';
  if (p.days_idle <= 3) return 'green';
  if (p.days_idle <= 14) return 'yellow';
  return 'red';
}
function mapIdleText(p) {
  if (!p.is_active) return 'Точка выключена';
  if (!p.last_date) return 'Замен ещё не было';
  if (p.days_idle === 0) return `Сегодня замен: ${p.today}`;
  if (p.days_idle === 1) return 'Последняя замена вчера';
  return `Последняя замена ${p.days_idle} дн. назад`;
}
function mapKindText(p) {
  if (p.kind === 'branch') return 'Филиал · ' + escapeHtml(p.parent_name || p.parent_username || '');
  if (p.kind === 'main') return `Главная точка · филиалов: ${p.branch_count}`;
  return 'Самостоятельная точка';
}
function mapPctHtml(pct) {
  if (pct === null || pct === undefined) return '<span style="color:#94A3B8">—</span>';
  const up = pct >= 0;
  return `<span style="color:${up ? '#16A34A' : '#DC2626'}">${up ? '▲' : '▼'} ${Math.abs(pct)}%</span>`;
}
function mapVisible() {
  if (!MAPDATA) return [];
  return MAPDATA.points.filter(p =>
    (!mapGroupSel || (p.client_group || '') === mapGroupSel) &&
    (mapFilt === 'all' || mapStatus(p) === mapFilt));
}

async function loadMap() {
  const kp = document.getElementById('mapKpis');
  if (!MAPDATA) kp.innerHTML = '<div class="hint-text">Загружаю карту…</div>';
  try {
    await loadLeaflet();
  } catch (e) {
    kp.innerHTML = '<div class="msg err">Не удалось загрузить карту — проверь интернет и открой вкладку ещё раз.</div>';
    return;
  }
  let data;
  try {
    const res = await fetch(`/api/admin/map?days=${mapDays}`);
    data = await res.json();
  } catch (e) {
    if (!MAPDATA) kp.innerHTML = '<div class="msg err">Не удалось получить данные точек.</div>';
    return;
  }
  if (!data || !data.points) return;
  MAPDATA = data;
  if (!MAP) {
    MAP = L.map('admMapBox', { zoomControl: true }).setView([40.8, 71.8], 8);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap'
    }).addTo(MAP);
    mapLayer = L.layerGroup().addTo(MAP);
    MAP.on('click', e => { if (mapPickId) mapSaveLocation(mapPickId, e.latlng.lat, e.latlng.lng); });
  }
  const groups = [...new Set(MAPDATA.points.map(p => p.client_group).filter(Boolean))].sort();
  const sel = document.getElementById('mapGroup');
  sel.innerHTML = '<option value="">Все сети</option>' + groups.map(g =>
    `<option value="${escapeHtml(g)}"${g === mapGroupSel ? ' selected' : ''}>${escapeHtml(g)}</option>`).join('');
  sel.style.display = groups.length ? '' : 'none';
  setTimeout(() => { MAP.invalidateSize(); renderMap(); }, 30);
}

function renderMap() {
  if (!MAP || !MAPDATA) return;
  const pts = mapVisible();
  const withXY = pts.filter(p => p.lat !== null && p.lon !== null);
  const noXY = pts.filter(p => p.lat === null || p.lon === null);
  const all = MAPDATA.points;
  const sum = (arr, k) => arr.reduce((a, p) => a + (Number(p[k]) || 0), 0);
  const per = MAPDATA.days === 7 ? '7 дней' : MAPDATA.days === 90 ? '3 месяца' : '30 дней';

  document.getElementById('mapKpis').innerHTML = `
    <div class="map-kpi"><b>${withXY.length} <small style="font-size:13px;color:#94A3B8">из ${all.length}</small></b><span>на карте</span></div>
    <div class="map-kpi"><b style="color:#16A34A">${all.filter(p => p.is_active && p.today > 0).length}</b><span>работали сегодня</span></div>
    <div class="map-kpi"><b style="color:#DC2626">${all.filter(p => mapStatus(p) === 'red').length}</b><span>молчат больше 14 дней</span></div>
    <div class="map-kpi"><b>${fmtShort(sum(pts, 'total'))}</b><span>${sum(pts, 'count').toLocaleString('ru-RU')} замен · ${per}</span></div>`;
  document.getElementById('mapLegendMetric').textContent = mapMetric === 'total' ? 'выручка' : 'замены';

  mapLayer.clearLayers();
  mapMarkers = {};
  const maxV = Math.max(1, ...withXY.map(p => Number(p[mapMetric]) || 0));
  if (document.getElementById('mapLinksChk').checked) {
    const byId = {};
    MAPDATA.points.forEach(p => { byId[p.id] = p; });
    withXY.forEach(p => {
      const par = p.kind === 'branch' ? byId[p.parent_shop_id] : null;
      if (par && par.lat !== null && par.lon !== null) {
        L.polyline([[par.lat, par.lon], [p.lat, p.lon]], { color: '#0F52BA', weight: 2, opacity: .55, dashArray: '6 6', interactive: false }).addTo(mapLayer);
      }
    });
  }
  withXY.slice().sort((a, b) => (Number(b[mapMetric]) || 0) - (Number(a[mapMetric]) || 0)).forEach(p => {
    const v = Number(p[mapMetric]) || 0;
    const st = mapStatus(p);
    const r = 7 + 22 * Math.sqrt(v / maxV);
    const m = L.circleMarker([p.lat, p.lon], {
      radius: r, color: p.kind === 'main' ? '#0A2540' : '#fff', weight: p.kind === 'main' ? 4 : 2,
      fillColor: MAP_COLORS[st], fillOpacity: .85
    }).addTo(mapLayer);
    m.bindPopup(() => mapPopupHtml(p), { maxWidth: 280 });
    m.bindTooltip(escapeHtml(p.shop_name || p.username), { direction: 'top', offset: [0, -r] });
    mapMarkers[p.id] = m;
  });
  if (!mapFitted && withXY.length) {
    mapFitted = true;
    if (withXY.length === 1) MAP.setView([withXY[0].lat, withXY[0].lon], 14);
    else MAP.fitBounds(withXY.map(p => [p.lat, p.lon]), { padding: [30, 30], maxZoom: 14 });
  }

  const nc = document.getElementById('mapNoCoords');
  if (noXY.length) {
    nc.style.display = '';
    nc.innerHTML = `<h3><i class="fa-solid fa-location-dot" style="color:#DC2626"></i> Нет на карте (${noXY.length})</h3>` +
      noXY.map(p => `<div class="map-row" style="cursor:default">
        <span class="mr-dot" style="background:${MAP_COLORS[mapStatus(p)]}"></span>
        <span class="mr-name">${escapeHtml(p.shop_name || p.username)}<small>${mapKindText(p)}</small></span>
        <button class="mr-pin" onclick="mapStartPick(${p.id})"><i class="fa-solid fa-map-pin"></i> Указать</button>
      </div>`).join('');
  } else {
    nc.style.display = 'none';
  }

  const ranked = pts.slice().sort((a, b) => (Number(b[mapMetric]) || 0) - (Number(a[mapMetric]) || 0));
  document.getElementById('mapRating').innerHTML = `<h3><i class="fa-solid fa-ranking-star" style="color:#EAB308"></i> Рейтинг за ${per} — по ${mapMetric === 'total' ? 'выручке' : 'заменам'}</h3>` +
    (ranked.length ? ranked.map((p, i) => `<div class="map-row" onclick="mapFocus(${p.id})">
        <span class="mr-n">${i + 1}</span>
        <span class="mr-dot" style="background:${MAP_COLORS[mapStatus(p)]}"></span>
        <span class="mr-name">${escapeHtml(p.shop_name || p.username)}<small>${mapKindText(p)} · ${mapIdleText(p)}</small></span>
        <span class="mr-val">${mapMetric === 'total' ? fmtShort(p.total) : p.count + ' зам.'}<small>${mapPctHtml(p.pct)}</small></span>
      </div>`).join('') : '<div class="hint-text" style="padding:12px 14px">Нет точек под этот фильтр.</div>');
}

function mapPopupHtml(p) {
  const st = mapStatus(p);
  const addr = [p.address, p.hours].filter(Boolean).map(escapeHtml).join(' · ');
  const per = MAPDATA.days === 7 ? '7 дн' : MAPDATA.days === 90 ? '3 мес' : '30 дн';
  return `<div class="map-pop">
    <div class="mp-name">${escapeHtml(p.shop_name || p.username)}</div>
    <div class="mp-kind">${mapKindText(p)}${p.client_group ? ' · ' + escapeHtml(p.client_group) : ''}</div>
    <div class="mp-st" style="color:${MAP_COLORS[st]}">● ${mapIdleText(p)}</div>
    <div class="mp-grid">
      <div><b>${p.count}</b>замен · ${per}</div>
      <div><b>${fmtShort(p.total)}</b>выручка ${mapPctHtml(p.pct)}</div>
      <div><b>${fmtShort(p.avg)}</b>средний чек</div>
      <div><b>${p.clients}</b>клиентов · всего ${p.client_count}</div>
    </div>
    ${addr ? `<div class="mp-addr"><i class="fa-solid fa-location-dot"></i> ${addr}</div>` : ''}
    ${p.phone ? `<div class="mp-addr"><i class="fa-solid fa-phone"></i> <a href="tel:${escapeHtml(p.phone)}">${escapeHtml(p.phone)}</a></div>` : ''}
    <button class="mp-snap" onclick="openSnapshot(${p.id})"><i class="fa-solid fa-oil-can"></i> Статистика, склад и поставщики</button>
    <div class="mp-act">
      <button class="b2" onclick="mapOpenCard(${p.id})">Карточка</button>
      <a class="b2" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lon}">Маршрут</a>
      <button class="b2" onclick="anaOpenFromMap(${p.id})">Аналитика</button>
      <button class="b2" onclick="mapStartPick(${p.id})">Переместить</button>
    </div>
  </div>`;
}

function setMapDays(d) {
  mapDays = d;
  document.querySelectorAll('#mapDaysSeg button').forEach(b => b.classList.toggle('on', Number(b.dataset.d) === d));
  loadMap();
}
function setMapMetric(m) {
  mapMetric = m;
  document.querySelectorAll('#mapMetricSeg button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  renderMap();
}
function setMapFilter(f) {
  mapFilt = f;
  document.querySelectorAll('#mapFilterSeg button').forEach(b => b.classList.toggle('on', b.dataset.f === f));
  renderMap();
}
function mapFocus(id) {
  const p = MAPDATA.points.find(x => x.id === id);
  if (!p) return;
  if (p.lat === null || p.lon === null) { mapStartPick(id); return; }
  document.querySelector('#admMap .map-wrap').scrollIntoView({ behavior: 'smooth', block: 'center' });
  MAP.setView([p.lat, p.lon], Math.max(MAP.getZoom(), 14));
  setTimeout(() => { if (mapMarkers[id]) mapMarkers[id].openPopup(); }, 350);
}
function mapOpenCard(id) {
  const p = MAPDATA.points.find(x => x.id === id);
  if (!p) return;
  admTab('main');
  setShopFilter('all');
  const search = document.getElementById('shopSearch');
  search.value = p.kind === 'branch' ? (p.parent_username || '') : (p.username || '');
  filterShops();
  setTimeout(() => search.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
}
function mapStartPick(id) {
  const p = MAPDATA.points.find(x => x.id === id);
  if (!p) return;
  if (MAP) MAP.closePopup();
  mapPickId = id;
  document.getElementById('mapPickText').innerHTML = `<i class="fa-solid fa-map-pin"></i> Нажми на карте, где находится <b>${escapeHtml(p.shop_name || p.username)}</b>. Можно приблизить карту пальцами.`;
  document.getElementById('mapPick').style.display = 'block';
  document.getElementById('admMapBox').classList.add('picking');
  document.querySelector('#admMap .map-wrap').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function mapPickCancel() {
  mapPickId = null;
  document.getElementById('mapPick').style.display = 'none';
  document.getElementById('admMapBox').classList.remove('picking');
}
function mapPickHere() {
  if (!mapPickId) return;
  if (!navigator.geolocation) { showMsg('Телефон не даёт определить местоположение.', false); return; }
  const id = mapPickId;
  navigator.geolocation.getCurrentPosition(
    pos => mapSaveLocation(id, pos.coords.latitude, pos.coords.longitude),
    () => showMsg('Не удалось определить местоположение — разреши доступ к геолокации или нажми место на карте.', false),
    { enableHighAccuracy: true, timeout: 15000 });
}
async function mapSaveLocation(id, lat, lon) {
  if (mapSaving) return;
  const p = MAPDATA.points.find(x => x.id === id);
  const name = p ? (p.shop_name || p.username) : '';
  if (!confirm(`Поставить «${name}» сюда?\\n${lat.toFixed(6)}, ${lon.toFixed(6)}`)) return;
  mapSaving = true;
  try {
    const res = await fetch(`/api/admin/shops/${id}/location`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat: lat, lon: lon })
    });
    const data = await res.json();
    if (!data.ok) { showMsg(data.error || 'Не удалось сохранить место.', false); return; }
    if (p) { p.lat = data.lat; p.lon = data.lon; }
    mapPickCancel();
    renderMap();
    MAP.setView([data.lat, data.lon], Math.max(MAP.getZoom(), 15));
    showMsg(`Точка «${escapeHtml(name)}» на карте.`, true);
  } catch (e) {
    showMsg('Не удалось сохранить место — проверь интернет.', false);
  } finally {
    mapSaving = false;
  }
}
// ---------- Аналитика продаж: бренды, доля MITAL, цены, возможности ----------
let ANA_CATLIST = [];
let anaView = 'main', NAMES = null, nmTab = 'review', nmEdit = null, nmSearch = '', PRICEPROB = null, ppShop = 0;
let ANA = null, anaDays = 30, anaGroup = '', anaShop = 0, anaCat = 'all', anaProduct = '', anaLoading = false;
const ANA_CATS = [
  ['all', 'Все товары'], ['fluid_0', 'Моторное'], ['fluid_1', 'АКПП/МКПП'], ['fluid_2', 'Антифриз'],
  ['fluid_3', 'Тормозная'], ['fluid_4', 'Редуктор'], ['filters', 'Фильтры'], ['other', 'Прочие товары']
];

async function loadAna() {
  if (anaLoading) return;
  anaLoading = true;
  if (!ANA) document.getElementById('anaBody').innerHTML = '<div class="hint-text">Загружаю…</div>';
  try {
    const res = await fetch(`/api/admin/analytics?days=${anaDays}`);
    const data = await res.json();
    if (data && data.rows) { ANA = data; ANA_CATLIST = data.categories || ANA_CATLIST; }
  } catch (e) {
    if (!ANA) document.getElementById('anaBody').innerHTML = '<div class="msg err">Не удалось получить данные — проверь интернет.</div>';
  } finally {
    anaLoading = false;
  }
  if (ANA) renderAna();
}
function setAnaDays(d) {
  anaDays = d;
  document.querySelectorAll('#anaDaysSeg button').forEach(b => b.classList.toggle('on', Number(b.dataset.d) === d));
  if (anaView === 'prices') { PRICEPROB = null; renderPriceProblems(); loadPriceProblems(); }
  loadAna();
}
function setAnaCat(c) { anaCat = c; anaProduct = ''; renderAna(); }
function anaPickShop(id) {
  anaShop = id || 0;
  renderAna();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function anaOpenFromMap(id) {
  anaView = 'main';
  document.getElementById('anaFilters').style.display = '';
  document.getElementById('anaDaysBar').style.display = '';
  admTab('analytics');
  anaShop = id;
  if (ANA) renderAna();
}
function anaPickProduct(key) {
  anaProduct = key;
  renderAna();
  const el = document.getElementById('anaPrices');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function anaKey(k) { return encodeURIComponent(k).replace(/'/g, '%27'); }
function anaCatOk(c) {
  return anaCat === 'all' || c === anaCat || (anaCat === 'filters' && String(c).indexOf('filter_') === 0);
}
function anaUnit(c) { return String(c).indexOf('fluid_') === 0 ? 'л' : 'шт'; }
function anaCatLabel(c) {
  const f = (ANA.categories || []).find(x => x.key === c);
  return f ? f.label : c;
}
function anaPoint(id) { return ANA.points.find(p => p.id === id); }
function anaPointName(p) { return p ? (p.shop_name || p.username) : '—'; }
function anaPointSub(p) {
  if (!p) return '';
  if (p.kind === 'branch') return 'филиал · ' + escapeHtml(p.parent_name || '');
  if (p.kind === 'main') return 'главная точка';
  return 'самостоятельная';
}
// точки в рамках выбранной сети (без учёта выбранной точки)
function anaGroupIds() {
  const ids = new Set();
  ANA.points.forEach(p => { if (!anaGroup || (p.client_group || '') === anaGroup) ids.add(p.id); });
  return ids;
}
function anaRows(withShop) {
  const ids = anaGroupIds();
  return ANA.rows.filter(r => ids.has(r.s) && anaCatOk(r.c) && (!withShop || !anaShop || r.s === anaShop));
}
function anaTotals(rows) {
  const t = { t: 0, m: 0, cs: 0, ct: 0, bad: 0, q: 0, ut: 0 };
  rows.forEach(r => { t.t += r.t; t.q += r.q; t.cs += r.cs; t.ct += r.ct; t.bad += r.bad; t.ut += r.ut || 0; if (r.m) t.m += r.t; });
  t.share = t.t ? Math.round(t.m / t.t * 100) : null;
  t.markup = t.cs ? Math.round((t.ct - t.cs) / t.cs * 100) : null;
  return t;
}
function anaQuality(ids) {
  let lines = 0, stock = 0, cost = 0;
  ANA.points.forEach(p => { if (ids.has(p.id)) { lines += p.quality.lines; stock += p.quality.stock; cost += p.quality.cost; } });
  return { lines, stock, cost, stockPct: lines ? Math.round(stock / lines * 100) : null, costPct: lines ? Math.round(cost / lines * 100) : null };
}
function anaPct(v) { return v === null || v === undefined ? '—' : v + '%'; }
function anaMoney(v) { return v === null || v === undefined || isNaN(v) ? '—' : Math.round(v).toLocaleString('ru-RU'); }
function anaQty(q, unit) {
  const n = Math.round(q * 10) / 10;
  return n.toLocaleString('ru-RU') + ' ' + unit;
}
// бренды: сумма, количество (если единица одна), доля
function anaBrands(rows) {
  const by = {};
  rows.forEach(r => {
    const k = r.b || '—';
    const b = by[k] = by[k] || { name: k === '—' ? 'без марки' : k, t: 0, q: 0, units: new Set(), m: r.m };
    b.t += r.t; b.q += r.q; b.units.add(anaUnit(r.c));
  });
  return Object.values(by).sort((a, b) => b.t - a.t);
}
// товары: агрегируем по категории + названию
function anaProducts(rows) {
  const by = {};
  rows.forEach(r => {
    const k = r.c + '|' + r.k;
    const p = by[k] = by[k] || { key: k, name: r.p || 'без названия', c: r.c, m: r.m, t: 0, q: 0, pt: 0, pq: 0, cs: 0, cq: 0, ct: 0, bad: 0, shops: new Set() };
    p.t += r.t; p.q += r.q; p.pt += r.pt; p.pq += r.pq; p.cs += r.cs; p.cq += r.cq; p.ct += r.ct; p.bad += r.bad; p.shops.add(r.s);
  });
  return Object.values(by).sort((a, b) => b.t - a.t);
}
function anaMarkupHtml(ct, cs) {
  if (!cs) return '<span class="ana-mute">—</span>';
  const v = Math.round((ct - cs) / cs * 100);
  return `<span class="${v < 10 ? 'ana-bad' : ''}">${v}%</span>`;
}

function renderAna() {
  if (anaView === 'names') { renderNames(); return; }
  if (anaView === 'prices') { renderPriceProblems(); return; }
  if (!ANA) return;
  document.getElementById('anaFilters').style.display = '';
  // фильтры: сеть, точка, категория
  const groups = [...new Set(ANA.points.map(p => p.client_group).filter(Boolean))].sort();
  const gSel = document.getElementById('anaGroup');
  gSel.innerHTML = '<option value="">Все сети</option>' + groups.map(g =>
    `<option value="${escapeHtml(g)}"${g === anaGroup ? ' selected' : ''}>${escapeHtml(g)}</option>`).join('');
  gSel.style.display = groups.length ? '' : 'none';
  const ids = anaGroupIds();
  if (anaShop && !ids.has(anaShop)) anaShop = 0;
  const sSel = document.getElementById('anaShopSel');
  sSel.innerHTML = `<option value="0">Все точки (${ids.size})</option>` + ANA.points.filter(p => ids.has(p.id)).map(p =>
    `<option value="${p.id}"${p.id === anaShop ? ' selected' : ''}>${escapeHtml(anaPointName(p))}${p.kind === 'branch' ? ' (филиал)' : ''}</option>`).join('');
  document.getElementById('anaCats').innerHTML = ANA_CATS.map(([k, l]) =>
    `<button class="${k === anaCat ? 'on' : ''}" onclick="setAnaCat('${k}')">${l}</button>`).join('');

  const rows = anaRows(true);
  const netRows = anaRows(false);
  const tot = anaTotals(rows);
  const netTot = anaTotals(netRows);
  const scopeIds = anaShop ? new Set([anaShop]) : ids;
  const ql = anaQuality(scopeIds);
  const netQl = anaQuality(ids);
  const per = anaDays === 365 ? 'год' : anaDays === 90 ? '3 месяца' : '30 дней';
  const vsNet = (v, n) => anaShop ? `<small style="display:block;font-size:11px;color:#94A3B8;font-weight:500">сеть: ${n}</small>` : '';
  let h = '';

  // ---- 1. ключевые цифры ----
  h += `<div class="map-kpis">
    <div class="map-kpi"><b>${fmtShort(tot.t)}</b><span>продажи товаров · ${per}</span></div>
    <div class="map-kpi"><b style="color:#B45309">${anaPct(tot.share)}</b><span>доля MITAL по сумме</span>${vsNet(tot.share, anaPct(netTot.share))}</div>
    <div class="map-kpi"><b>${anaPct(tot.markup)}</b><span>средняя наценка</span>${vsNet(tot.markup, anaPct(netTot.markup))}</div>
    <div class="map-kpi"><b style="color:${ql.stockPct !== null && ql.stockPct < 50 ? '#DC2626' : '#16A34A'}">${anaPct(ql.stockPct)}</b><span>позиций со склада</span>${vsNet(ql.stockPct, anaPct(netQl.stockPct))}</div>
  </div>`;
  if (!rows.length) {
    h += '<div class="ana-card"><div class="hint-text" style="padding:14px">За этот период и фильтр продаж товаров нет.</div></div>';
    document.getElementById('anaBody').innerHTML = h;
    return;
  }
  const utPct = tot.t ? Math.round(tot.ut / tot.t * 1000) / 10 : 0;
  h += `<div class="ana-dq">
    <div class="dq-txt"><b>Точность данных</b><br>
      ${utPct > 0 ? `<span class="${utPct >= 5 ? 'ana-bad' : ''}">Не распознано: ${utPct}% продаж (${fmtShort(tot.ut)})</span>` : '<span class="ana-good">Все названия распознаны ✓</span>'}
      · ${tot.bad ? `<span class="ana-bad">подозрительных цен: ${tot.bad}</span> — не входят в цены и наценку` : '<span class="ana-good">подозрительных цен нет</span>'}</div>
    <div class="dq-act"><button class="ana-btn" onclick="anaOpenView('names')"><i class="fa-solid fa-spell-check"></i> Сопоставление</button>
      <button class="ana-btn" onclick="anaOpenView('prices')"><i class="fa-solid fa-triangle-exclamation"></i> Проблемные цены</button></div>
  </div>`;

  // ---- 3. карточка выбранной точки ----
  if (anaShop) {
    const p = anaPoint(anaShop);
    const oilRows = ANA.rows.filter(r => r.s === anaShop && r.c === 'fluid_0');
    const netOil = ANA.rows.filter(r => ids.has(r.s) && r.c === 'fluid_0');
    const lp = rs => { const q = rs.reduce((a, r) => a + r.pq, 0); return q ? rs.reduce((a, r) => a + r.pt, 0) / q : null; };
    const cp = rs => { const q = rs.reduce((a, r) => a + r.cq, 0); return q ? rs.reduce((a, r) => a + r.cs, 0) / q : null; };
    h += `<div class="ana-card"><h3><i class="fa-solid fa-store" style="color:var(--blue)"></i> ${escapeHtml(anaPointName(p))}<small>${anaPointSub(p)}</small></h3>
      <div class="ana-cmp">
        <div><b>${anaMoney(lp(oilRows))}</b>моторное масло, сум/л · сеть ${anaMoney(lp(netOil))}</div>
        <div><b>${anaMoney(cp(oilRows))}</b>закупка масла, сум/л · сеть ${anaMoney(cp(netOil))}</div>
        <div><b>${anaPct(ql.costPct)}</b>позиций с ценой закупки · сеть ${anaPct(netQl.costPct)}</div>
        <div><b>${ql.lines}</b>проданных позиций за ${per}</div>
      </div>
      <div class="ana-note">${ql.stockPct !== null && ql.stockPct < 50 ? '⚠️ Больше половины масла и фильтров точка вписывает вручную, не со склада — наценка и закупка по ним неизвестны. Цифры точки пока неполные.' : 'Данные точки достаточно полные: большая часть товаров выбирается со склада.'}</div>
      <div style="padding:10px 14px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="ana-btn" onclick="anaPickShop(0)"><i class="fa-solid fa-arrow-left"></i> Вся сеть</button>
        <button class="ana-btn" onclick="openSnapshot(${anaShop})"><i class="fa-solid fa-oil-can"></i> Статистика и склад точки</button>
        <button class="ana-btn" onclick="admTab('map'); setTimeout(() => { if (MAPDATA) mapFocus(${anaShop}); }, 600);"><i class="fa-solid fa-map-location-dot"></i> На карте</button>
      </div></div>`;
  }

  // ---- 1. бренды ----
  const brands = anaBrands(rows);
  const top = brands.slice(0, 12);
  const rest = brands.slice(12);
  h += `<div class="ana-card"><h3><i class="fa-solid fa-tags" style="color:#EAB308"></i> Бренды — что продаётся<small>по сумме</small></h3>` +
    top.map(b => {
      const share = tot.t ? Math.round(b.t / tot.t * 1000) / 10 : 0;
      const qty = b.units.size === 1 ? anaQty(b.q, [...b.units][0]) : '';
      return `<div class="ana-row"><div class="ar-main">
        <div class="ar-name">${escapeHtml(b.name)}${b.m ? '<span class="mital-tag">MITAL</span>' : ''}</div>
        <div class="ar-bar"><i class="${b.m ? 'mital' : ''}" style="width:${Math.max(2, Math.min(100, share))}%"></i></div>
      </div><div class="ar-val">${fmtShort(b.t)}<small>${share}%${qty ? ' · ' + qty : ''}</small></div></div>`;
    }).join('') +
    (rest.length ? `<div class="ana-row"><div class="ar-main"><div class="ar-name ana-mute">Остальные (${rest.length})</div></div><div class="ar-val">${fmtShort(rest.reduce((a, b) => a + b.t, 0))}</div></div>` : '') +
    '</div>';

  // ---- 1. топ товаров ----
  const prods = anaProducts(rows);
  h += `<div class="ana-card"><h3><i class="fa-solid fa-ranking-star" style="color:var(--blue)"></i> Топ товаров<small>нажми — цены по точкам</small></h3>
    <div class="ana-tbl-wrap"><table class="ana-tbl"><tr><th>Товар</th><th>Цена</th><th>Закупка</th><th>Нац.</th></tr>` +
    prods.slice(0, 15).map(p => `<tr class="click" onclick="anaPickProduct('${anaKey(p.key)}')">
      <td>${escapeHtml(p.name)}${p.m ? '<span class="mital-tag">MITAL</span>' : ''}${p.bad ? ' ⚠️' : ''}<div class="ar-sub">${escapeHtml(anaCatLabel(p.c))} · ${anaQty(p.q, anaUnit(p.c))} · ${fmtShort(p.t)} сум</div></td>
      <td>${anaMoney(p.pq ? p.pt / p.pq : null)}</td>
      <td>${p.cq ? anaMoney(p.cs / p.cq) : '<span class="ana-mute">—</span>'}</td>
      <td>${anaMarkupHtml(p.ct, p.cs)}</td></tr>`).join('') +
    '</table></div></div>';

  // ---- 2. цены по точкам ----
  const netProds = anaProducts(netRows).filter(p => p.shops.size >= 1);
  if (!anaProduct || !netProds.find(p => anaKey(p.key) === anaProduct)) {
    const first = netProds.find(p => p.shops.size > 1) || netProds[0];
    anaProduct = first ? anaKey(first.key) : '';
  }
  const cur = netProds.find(p => anaKey(p.key) === anaProduct);
  if (cur) {
    const unit = anaUnit(cur.c);
    const pr = netRows.filter(r => r.c + '|' + r.k === cur.key).sort((a, b) => (b.pq ? b.pt / b.pq : 0) - (a.pq ? a.pt / a.pq : 0));
    const sales = pr.filter(r => r.pq > 0).map(r => r.pt / r.pq);
    const costs = pr.filter(r => r.cq > 0).map(r => r.cs / r.cq);
    const mn = a => a.length ? Math.min(...a) : null, mx = a => a.length ? Math.max(...a) : null;
    const minS = mn(sales), maxS = mx(sales), minC = mn(costs), maxC = mx(costs);
    const multi = pr.length > 1;
    h += `<div class="ana-card" id="anaPrices"><h3><i class="fa-solid fa-scale-balanced" style="color:#16A34A"></i> Цены по точкам</h3>
      <div style="padding:10px 14px 4px"><select style="width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 10px;font-size:13px;font-family:inherit;background:#fff" onchange="anaPickProduct(this.value)">` +
      netProds.slice(0, 200).map(p => `<option value="${anaKey(p.key)}"${anaKey(p.key) === anaProduct ? ' selected' : ''}>${escapeHtml(p.name)} — ${p.shops.size} точ.</option>`).join('') +
      `</select></div>
      <div class="ana-tbl-wrap"><table class="ana-tbl"><tr><th>Точка</th><th>Цена/${unit}</th><th>Закупка</th><th>Нац.</th></tr>` +
      pr.map(r => {
        const sp = r.pq ? r.pt / r.pq : null, cp = r.cq ? r.cs / r.cq : null;
        const p = anaPoint(r.s);
        const sCls = multi && sp === maxS ? 'ana-bad' : multi && sp === minS ? 'ana-good' : '';
        const cCls = multi && cp !== null && costs.length > 1 && cp === minC ? 'ana-good' : multi && cp !== null && costs.length > 1 && cp === maxC ? 'ana-bad' : '';
        return `<tr class="click${r.s === anaShop ? ' sum' : ''}" onclick="anaPickShop(${r.s})"><td>${escapeHtml(anaPointName(p))}${r.bad ? ' ⚠️' : ''}<div class="ar-sub">${anaPointSub(p)} · ${anaQty(r.q, unit)}</div></td>
          <td class="${sCls}">${anaMoney(sp)}</td>
          <td class="${cCls}">${cp === null ? '<span class="ana-mute">—</span>' : anaMoney(cp)}</td><td>${anaMarkupHtml(r.ct, r.cs)}</td></tr>`;
      }).join('') +
      ''+
      `</table></div>` +
      (multi ? `<div class="ana-range">Продажа за ${unit}: мин <b>${anaMoney(minS)}</b> · средн. <b>${anaMoney(cur.pq ? cur.pt / cur.pq : null)}</b> · макс <b>${anaMoney(maxS)}</b>` +
        (costs.length ? `<br>Закупка за ${unit}: мин <b>${anaMoney(minC)}</b> · средн. <b>${anaMoney(cur.cs / cur.cq)}</b> · макс <b>${anaMoney(maxC)}</b>` : '') +
        `<br>Всего продано: <b>${anaQty(cur.q, unit)}</b> · наценка по сети ${anaMarkupHtml(cur.ct, cur.cs)}</div>` : '') +
      `<div class="ana-note">Зелёный — самая низкая цена, красный — самая высокая. Нажми на точку, чтобы открыть её аналитику.</div></div>`;
  }

  // ---- 3. сравнение точек (только для всей сети) ----
  if (!anaShop) {
    const per_shop = {};
    netRows.forEach(r => { (per_shop[r.s] = per_shop[r.s] || []).push(r); });
    const list = ANA.points.filter(p => ids.has(p.id)).map(p => ({ p, t: anaTotals(per_shop[p.id] || []), q: p.quality }))
      .sort((a, b) => b.t.t - a.t.t);
    h += `<div class="ana-card"><h3><i class="fa-solid fa-store" style="color:var(--blue)"></i> Точки<small>нажми — аналитика точки</small></h3>
      <div class="ana-tbl-wrap"><table class="ana-tbl"><tr><th>Точка</th><th>Продажи</th><th>MITAL</th><th>Нац.</th><th>Склад</th></tr>` +
      list.map(x => {
        const sp = x.q.lines ? Math.round(x.q.stock / x.q.lines * 100) : null;
        return `<tr class="click" onclick="anaPickShop(${x.p.id})"><td>${escapeHtml(anaPointName(x.p))}<div class="ar-sub">${anaPointSub(x.p)}</div></td>
        <td>${fmtShort(x.t.t)}</td><td style="color:#B45309">${anaPct(x.t.share)}</td><td>${anaPct(x.t.markup)}</td>
        <td class="${sp !== null && sp < 50 ? 'ana-bad' : ''}">${anaPct(sp)}</td></tr>`;
      }).join('') + '</table></div><div class="ana-note">Нац. — средняя наценка. Склад — какая доля масла и фильтров выбрана со склада: чем выше, тем точнее цифры точки.</div></div>';
  }

  // ---- 4. возможности для продаж ----
  const opp = {};
  netRows.forEach(r => {
    if (anaShop && r.s !== anaShop) return;
    const o = opp[r.s] = opp[r.s] || { s: r.s, other: 0, mital: 0, brands: {} };
    if (r.m) o.mital += r.t; else o.other += r.t;
    const b = o.brands[r.b || 'без марки'] = o.brands[r.b || 'без марки'] || { name: r.b || 'без марки', t: 0, q: 0, units: new Set(), m: r.m };
    b.t += r.t; b.q += r.q; b.units.add(anaUnit(r.c));
  });
  const oppList = Object.values(opp).filter(o => o.other > 0).sort((a, b) => b.other - a.other);
  h += `<div class="ana-card"><h3><i class="fa-solid fa-bullseye" style="color:#DC2626"></i> Возможности для продаж<small>что точки берут у других</small></h3>
    <div class="ana-note">Сколько точка продала товаров других брендов — это объём, который можно предложить заменить. Жёлтым — бренды MITAL.</div>` +
    (oppList.length ? oppList.slice(0, 30).map(o => {
      const p = anaPoint(o.s);
      const all = o.other + o.mital;
      const share = all ? Math.round(o.mital / all * 100) : 0;
      const bs = Object.values(o.brands).sort((a, b) => b.t - a.t).slice(0, 6);
      return `<div class="ana-row click" onclick="anaPickShop(${o.s})"><div class="ar-main">
        <div class="ar-name">${escapeHtml(anaPointName(p))} <span class="ar-sub" style="display:inline">${anaPointSub(p)}</span></div>
        <div class="ana-brands">${bs.map(b => `<span class="${b.m ? 'm' : ''}">${escapeHtml(b.name)} ${b.units.size === 1 ? anaQty(b.q, [...b.units][0]) : fmtShort(b.t)}</span>`).join('')}</div>
        <div class="ar-bar"><i class="mital" style="width:${Math.max(share ? 2 : 0, share)}%"></i></div>
      </div><div class="ar-val ana-bad">${fmtShort(o.other)}<small>MITAL ${share}%</small></div></div>`;
    }).join('') : '<div class="hint-text" style="padding:12px 14px">Здесь все продажи — бренды MITAL. 👍</div>') +
    '</div>';

  document.getElementById('anaBody').innerHTML = h;
}
// ---------- Сопоставление названий и проблемные цены ----------
function anaOpenView(v) {
  anaView = v;
  nmEdit = null;
  document.getElementById('anaFilters').style.display = v === 'main' ? '' : 'none';
  document.getElementById('anaDaysBar').style.display = v === 'names' ? 'none' : '';
  if (v === 'names') { renderNames(); loadNames(); }
  else if (v === 'prices') { renderPriceProblems(); loadPriceProblems(); }
  else { if (ANA) renderAna(); loadAna(); }
  window.scrollTo(0, 0);
}
async function loadNames() {
  try {
    const res = await fetch('/api/admin/names?days=365');
    const data = await res.json();
    if (data && data.review) NAMES = data;
  } catch (e) {
    if (!NAMES) document.getElementById('anaBody').innerHTML = '<div class="msg err">Не удалось загрузить — проверь интернет.</div>';
    return;
  }
  if (anaView === 'names') renderNames();
}
function nmBack() { return `<button class="ana-btn" style="margin-bottom:10px" onclick="anaOpenView('main')"><i class="fa-solid fa-arrow-left"></i> Аналитика</button>`; }
function nmCats(cats) { return (cats || []).map(c => { const f = ANA_CATLIST.find(x => x.key === c); return f ? f.label : c; }).join(', '); }
function nmList() { return NAMES ? (NAMES[nmTab] || []) : []; }

function renderNames() {
  const box = document.getElementById('anaBody');
  if (!NAMES) { box.innerHTML = nmBack() + '<div class="hint-text">Загружаю…</div>'; return; }
  const N = NAMES;
  const sug = N.review.filter(g => g.sug);
  let h = nmBack();
  h += `<div class="ana-card"><h3><i class="fa-solid fa-spell-check" style="color:var(--blue)"></i> Сопоставление названий<small>за год</small></h3>
    <div class="ana-note">Точки вписывают названия по-разному («Митанол», «Mitonol 5-30»). Здесь ты один раз указываешь, что это за товар, — и аналитика всей сети, включая прошлое, сразу считается правильно. Данные самих точек не меняются.</div>
    <div class="ana-cmp">
      <div><b class="${N.unresolved_pct >= 5 ? 'ana-bad' : ''}">${N.unresolved_pct}%</b>продаж не распознано</div>
      <div><b>${fmtShort(N.unresolved_sum)}</b>сумма нераспознанных</div>
      <div><b>${N.review.length}</b>названий проверить</div>
      <div><b>${N.auto.length}</b>исправлено автоматически</div>
    </div></div>`;
  h += `<div class="ana-chips">
    <button class="${nmTab === 'review' ? 'on' : ''}" onclick="nmTab='review'; nmEdit=null; renderNames()">Проверить (${N.review.length})</button>
    <button class="${nmTab === 'auto' ? 'on' : ''}" onclick="nmTab='auto'; nmEdit=null; renderNames()">Исправлено авто (${N.auto.length})</button>
    <button class="${nmTab === 'mapped' ? 'on' : ''}" onclick="nmTab='mapped'; nmEdit=null; renderNames()">Подтверждено (${N.mapped.length})</button>
  </div>`;
  h += `<datalist id="nmBrands">${(N.brands || []).map(b => `<option value="${escapeHtml(b)}">`).join('')}</datalist>`;
  const list = nmList();
  if (nmTab === 'review' && sug.length > 1) {
    h += `<button class="ana-btn" style="margin-bottom:10px" onclick="nmAcceptAll()"><i class="fa-solid fa-check-double"></i> Принять все подсказки (${sug.length})</button>`;
  }
  if (nmTab === 'auto' && list.length > 1) {
    h += `<button class="ana-btn" style="margin-bottom:10px" onclick="nmConfirmAuto()"><i class="fa-solid fa-check-double"></i> Всё верно — подтвердить все (${list.length})</button>`;
  }
  if (nmTab === 'mapped') {
    h += `<input placeholder="🔍 Поиск" value="${escapeHtml(nmSearch)}" oninput="nmSearch=this.value; renderNamesList()" style="margin-bottom:10px">`;
  }
  h += '<div id="nmList"></div>';
  box.innerHTML = h;
  renderNamesList();
}

function renderNamesList() {
  const el = document.getElementById('nmList');
  if (!el) return;
  let list = nmList().map((g, i) => [g, i]);
  if (nmTab === 'mapped' && nmSearch.trim()) {
    const q = nmSearch.trim().toUpperCase();
    list = list.filter(([g]) => (g.raw + ' ' + (g.brand || '') + ' ' + (g.product || '')).toUpperCase().includes(q));
  }
  if (!list.length) {
    el.innerHTML = `<div class="ana-card"><div class="hint-text" style="padding:14px">${nmTab === 'review' ? 'Всё распознано — проверять нечего 👍' : 'Пусто.'}</div></div>`;
    return;
  }
  el.innerHTML = list.slice(0, 150).map(([g, i]) => nmCard(g, i)).join('') +
    (list.length > 150 ? `<div class="hint-text">Показаны первые 150 из ${list.length}.</div>` : '');
}

function nmCard(g, i) {
  const spell = (g.spellings && g.spellings.length) ? g.spellings : [g.raw];
  const meta = g.lines ? `${g.shops} точ. · ${g.lines} продаж · ${fmtShort(g.sum)} сум${g.cats.length ? ' · ' + escapeHtml(nmCats(g.cats)) : ''}` : 'в продажах за год не встречалось';
  let body = `<div class="nm-spell">${escapeHtml(spell[0])}${spell.length > 1 ? `<small>также: ${spell.slice(1).map(escapeHtml).join(' · ')}</small>` : ''}</div>
    <div class="ar-sub">${meta}</div>`;
  if (nmEdit === nmTab + i) {
    const b0 = g.sug ? g.sug.brand : (g.brand || '');
    const p0 = g.sug ? g.sug.product : (g.product || g.raw);
    body += `<div class="nm-form">
      <label>Бренд</label><input id="nmB" list="nmBrands" value="${escapeHtml(b0)}" placeholder="например, MITANOL" autocapitalize="characters">
      <label>Товар (как показывать в аналитике)</label><input id="nmP" value="${escapeHtml(p0)}" placeholder="например, MITANOL 5W-30 SL">
      <div class="nm-act"><button class="ok" onclick="nmSaveEdit('${nmTab}', ${i})">Сохранить</button>
        <button onclick="nmEdit=null; renderNamesList()">Отмена</button></div></div>`;
  } else if (nmTab === 'review') {
    if (g.sug) {
      body += `<div class="nm-sug">Похоже на: <b>${escapeHtml(g.sug.product)}</b>${(NAMES.mital_brands || []).includes(g.sug.brand) ? '<span class="mital-tag">MITAL</span>' : ''}</div>
        <div class="nm-act"><button class="ok" onclick="nmAccept(${i})">✓ Да, это оно</button>
          <button onclick="nmEdit='review${i}'; renderNamesList()">✏️ Другое</button>
          <button onclick="nmNoBrand('review', ${i})">Не бренд</button></div>`;
    } else {
      body += `<div class="nm-sug ana-mute">Бренд не найден в словаре</div>
        <div class="nm-act"><button class="ok" onclick="nmNewBrand(${i})">✓ Новый бренд «${escapeHtml(g.brand || '')}»</button>
          <button onclick="nmEdit='review${i}'; renderNamesList()">✏️ Указать бренд</button>
          <button onclick="nmNoBrand('review', ${i})">Не бренд</button></div>`;
    }
  } else if (nmTab === 'auto') {
    body += `<div class="nm-sug">Исправлено на: <b>${escapeHtml(g.product)}</b> <span class="ana-mute">(${Math.round((g.conf || 0) * 100)}%)</span></div>
      <div class="nm-act"><button class="ok" onclick="nmConfirmOne(${i})">✓ Верно</button>
        <button onclick="nmEdit='auto${i}'; renderNamesList()">✏️ Исправить</button></div>`;
  } else {
    body += `<div class="nm-sug">${g.alias_status === 'nobrand' ? '<b>Не бренд</b>' : `→ <b>${escapeHtml(g.product || g.brand)}</b> · бренд ${escapeHtml(g.brand || '')}`}</div>
      <div class="nm-act"><button onclick="nmEdit='mapped${i}'; renderNamesList()">✏️ Изменить</button>
        <button class="no" onclick="nmUndo(${i})">Отменить</button></div>`;
  }
  return `<div class="ana-card nm-card">${body}</div>`;
}

async function nmPost(items) {
  try {
    const res = await fetch('/api/admin/names', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) });
    const data = await res.json();
    if (!data.ok) { showMsg(data.error || 'Не удалось сохранить.', false); return false; }
    ANA = null;  // аналитика пересчитается при возврате
    nmEdit = null;
    await loadNames();
    return true;
  } catch (e) {
    showMsg('Не удалось сохранить — проверь интернет.', false);
    return false;
  }
}
function nmAccept(i) {
  const g = NAMES.review[i];
  if (g && g.sug) nmPost([{ raw: g.raw, brand: g.sug.brand, product: g.sug.product }]);
}
function nmNewBrand(i) {
  const g = NAMES.review[i];
  if (g && g.brand) nmPost([{ raw: g.raw, brand: g.brand, product: g.product }]);
}
function nmNoBrand(tab, i) {
  const g = NAMES[tab][i];
  if (g) nmPost([{ raw: g.raw, status: 'nobrand', product: g.raw }]);
}
function nmSaveEdit(tab, i) {
  const g = NAMES[tab][i];
  const brand = document.getElementById('nmB').value.trim();
  const product = document.getElementById('nmP').value.trim();
  if (!brand) { showMsg('Впиши бренд.', false); return; }
  nmPost([{ raw: g.raw, brand, product: product || brand }]);
}
function nmConfirmOne(i) {
  const g = NAMES.auto[i];
  if (g) nmPost([{ raw: g.raw, brand: g.brand, product: g.product }]);
}
function nmAcceptAll() {
  const items = NAMES.review.filter(g => g.sug).map(g => ({ raw: g.raw, brand: g.sug.brand, product: g.sug.product }));
  if (!items.length) return;
  if (!confirm(`Принять все подсказки (${items.length})? Сначала пролистай список — если какая-то подсказка неверная, исправь её отдельно.`)) return;
  nmPost(items);
}
function nmConfirmAuto() {
  const items = NAMES.auto.map(g => ({ raw: g.raw, brand: g.brand, product: g.product }));
  if (!items.length || !confirm(`Подтвердить все автоисправления (${items.length})?`)) return;
  nmPost(items);
}
async function nmUndo(i) {
  const g = NAMES.mapped[i];
  if (!g || !confirm(`Отменить сопоставление «${g.raw}»? Название снова будет распознаваться автоматически.`)) return;
  try {
    await fetch('/api/admin/names/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw: g.raw }) });
    ANA = null;
    await loadNames();
  } catch (e) {
    showMsg('Не удалось — проверь интернет.', false);
  }
}

async function loadPriceProblems() {
  try {
    const res = await fetch(`/api/admin/price_problems?days=${anaDays}`);
    const data = await res.json();
    if (Array.isArray(data)) PRICEPROB = data;
  } catch (e) {
    if (!PRICEPROB) document.getElementById('anaBody').innerHTML = '<div class="msg err">Не удалось загрузить — проверь интернет.</div>';
    return;
  }
  if (!ANA) await loadAna();
  if (anaView === 'prices') renderPriceProblems();
}
function renderPriceProblems() {
  const box = document.getElementById('anaBody');
  if (!PRICEPROB || !ANA) { box.innerHTML = nmBack() + '<div class="hint-text">Загружаю…</div>'; return; }
  const per = anaDays === 365 ? 'год' : anaDays === 90 ? '3 месяца' : '30 дней';
  const shops = [...new Set(PRICEPROB.map(x => x.s))];
  const list = PRICEPROB.filter(x => !ppShop || x.s === ppShop);
  let h = nmBack();
  h += `<div class="ana-card"><h3><i class="fa-solid fa-triangle-exclamation" style="color:#DC2626"></i> Проблемные цены<small>${per}</small></h3>
    <div class="ana-note">Цена продажи или закупки сильно отличается от обычной цены этого товара по сети (в 2 раза и больше), или закупка дороже продажи — чаще всего это цена за коробку/канистру вместо литра или штуки. Такие позиции не входят в средние цены и наценку. Исправить может только сама точка — в «Базе» или на складе (✏️).</div>
    <div style="padding:10px 14px"><select style="width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 10px;font-size:13px;font-family:inherit;background:#fff" onchange="ppShop=Number(this.value)||0; renderPriceProblems()">
      <option value="0">Все точки (${PRICEPROB.length})</option>
      ${shops.map(id => `<option value="${id}"${id === ppShop ? ' selected' : ''}>${escapeHtml(anaPointName(anaPoint(id)))} (${PRICEPROB.filter(x => x.s === id).length})</option>`).join('')}
    </select></div></div>`;
  if (!list.length) {
    h += '<div class="ana-card"><div class="hint-text" style="padding:14px">Подозрительных цен нет 👍</div></div>';
  } else {
    h += '<div class="ana-card">' + list.map(x => {
      const unit = anaUnit(x.c);
      const p = anaPoint(x.s);
      const what = x.kind === 'sale'
        ? `Продажа <b class="ana-bad">${anaMoney(x.unit)}</b> за ${unit}${x.med_sale ? ` — обычно ${anaMoney(x.med_sale)}` : ''}`
        : `Закупка <b class="ana-bad">${anaMoney(x.cost)}</b> за ${unit}${x.med_cost ? ` — обычно ${anaMoney(x.med_cost)}` : ` при продаже ${anaMoney(x.unit)}`}`;
      return `<div class="ana-row"><div class="ar-main">
        <div class="ar-name" style="white-space:normal">${escapeHtml(anaPointName(p))} · <span style="font-weight:600">${escapeHtml(x.label || x.product)}</span></div>
        <div class="ar-sub">${fmtDay(x.date)} · ${anaQty(x.qty, unit)} за ${anaMoney(x.total)} сум</div>
        <div style="font-size:12.5px;margin-top:3px">${what}</div>
      </div>${x.dev ? `<div class="ar-val ana-bad">×${x.dev >= 1 ? String(Math.round(x.dev * 10) / 10).replace('.', ',') : String(Math.round(1 / x.dev * 10) / 10).replace('.', ',') + '↓'}</div>` : ''}</div>`;
    }).join('') + '</div>';
  }
  box.innerHTML = h;
}
// ---------- Копия статистики брендов и склада одной точки ----------
let SNAP = null, snapId = 0, snapDays = 30, snapWh = 'oil', snapSeq = 0;
const SNAP_UNIT = { l: 'л', pc: 'шт', '': '' };

function openSnapshot(id) {
  snapId = id;
  SNAP = null;
  snapWh = 'oil';
  if (MAP) MAP.closePopup();
  const p = (MAPDATA && MAPDATA.points.find(x => x.id === id)) || (ANA && anaPoint(id));
  document.getElementById('snapName').textContent = p ? (p.shop_name || p.username) : '…';
  document.getElementById('snapSub').textContent = '';
  document.getElementById('snapOv').style.display = 'block';
  document.body.style.overflow = 'hidden';
  renderSnapshot();
  loadSnapshot();
}
function closeSnapshot() {
  document.getElementById('snapOv').style.display = 'none';
  document.body.style.overflow = '';
  snapSeq++;
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.getElementById('snapOv').style.display === 'block') closeSnapshot(); });

async function loadSnapshot() {
  const seq = ++snapSeq;
  try {
    const res = await fetch(`/api/admin/shops/${snapId}/snapshot?days=${snapDays}`);
    const data = await res.json();
    if (seq !== snapSeq) return;
    if (!data || !data.shop) {
      document.getElementById('snapBody').innerHTML = `<div class="msg err">${escapeHtml((data && data.error) || 'Не удалось загрузить.')}</div>`;
      return;
    }
    SNAP = data;
  } catch (e) {
    if (seq === snapSeq) document.getElementById('snapBody').innerHTML = '<div class="msg err">Не удалось загрузить — проверь интернет.</div>';
    return;
  }
  renderSnapshot();
}
function setSnapDays(d) { snapDays = d; renderSnapshot(); loadSnapshot(); }
function setSnapWh(w) { snapWh = w; renderSnapshot(); }

function renderSnapshot() {
  const body = document.getElementById('snapBody');
  const seg = `<div class="map-seg" style="margin-bottom:10px">
    ${[[30, '30 дней'], [90, '3 месяца'], [365, 'Год']].map(([d, l]) => `<button class="${d === snapDays ? 'on' : ''}" onclick="setSnapDays(${d})">${l}</button>`).join('')}
  </div>`;
  if (!SNAP) { body.innerHTML = seg + '<div class="hint-text">Загружаю…</div>'; return; }
  const S = SNAP;
  document.getElementById('snapName').textContent = S.shop.name;
  document.getElementById('snapSub').textContent = (S.shop.role === 'branch' ? 'Филиал' + (S.shop.parent_name ? ' · ' + S.shop.parent_name : '') : 'Точка') +
    (S.shop.address ? ' · ' + S.shop.address : '');
  const rv = S.revenue || {};
  let h = seg;
  h += `<div class="map-kpis">
    <div class="map-kpi"><b>${fmtShort(rv.total || 0)}</b><span>выручка</span></div>
    <div class="map-kpi"><b>${rv.count || 0}</b><span>замен и услуг</span></div>
    <div class="map-kpi"><b>${fmtShort(rv.avg || 0)}</b><span>средний чек</span></div>
    <div class="map-kpi"><b>${(rv.clients && rv.clients.total) || 0}</b><span>клиентов</span></div>
  </div>`;

  // --- бренды: копия экрана точки ---
  h += '<div class="snap-sec"><i class="fa-solid fa-oil-can" style="color:#EAB308"></i> Бренды: что продаётся</div>';
  if (!S.brands.length) {
    h += '<div class="ana-card"><div class="hint-text" style="padding:14px">За этот период продаж с указанием масла и фильтров нет.</div></div>';
  }
  S.brands.forEach(c => {
    const unit = SNAP_UNIT[c.unit] !== undefined ? SNAP_UNIT[c.unit] : '';
    const bySum = c.metric === 'sum';
    h += `<div class="ana-card"><h3>${escapeHtml(c.label)}<small>${bySum ? fmtShort(c.total_sum) + ' сум' : anaQty(c.total_qty, unit) + ' · ' + fmtShort(c.total_sum) + ' сум'}</small></h3>` +
      c.top.map(b => `<div class="ana-row"><div class="ar-main">
          <div class="ar-name">${b.no_brand ? '<span class="ana-mute">без марки</span>' : escapeHtml(b.name)}</div>
          <div class="ar-bar"><i style="width:${Math.max(2, Math.min(100, b.share))}%"></i></div>
        </div><div class="ar-val">${bySum ? fmtShort(b.sum) : anaQty(b.qty, unit)}<small>${b.share}% · ${b.visits} раз${bySum ? '' : ' · ' + fmtShort(b.sum)}</small></div></div>`).join('') +
      (c.others ? `<div class="ana-row"><div class="ar-main"><div class="ar-name ana-mute">Остальные (${c.others.count})</div></div>
        <div class="ar-val">${bySum ? fmtShort(c.others.sum) : anaQty(c.others.qty, unit)}<small>${c.others.share}%</small></div></div>` : '') +
      '</div>';
  });

  // --- склад: копия склада точки ---
  const all = S.warehouse.products || [];
  h += '<div class="snap-sec"><i class="fa-solid fa-warehouse" style="color:var(--blue)"></i> Склад</div>';
  if (!all.length) {
    h += `<div class="ana-card"><div class="hint-text" style="padding:14px">${S.shop.warehouse_enabled ? 'На складе точки пока нет товаров.' : 'Склад у этой точки выключен — товары не ведутся.'}</div></div>`;
    body.innerHTML = h + snapSuppliersHtml(S);
    return;
  }
  const isOil = p => String(p.category).indexOf('fluid_') === 0;
  const isFil = p => String(p.category).indexOf('filter_') === 0;
  const prods = all.filter(p => snapWh === 'all' || (snapWh === 'oil' && isOil(p)) || (snapWh === 'filter' && isFil(p)) || (snapWh === 'other' && !isOil(p) && !isFil(p)));
  h += `<div class="ana-chips">
    <button class="${snapWh === 'oil' ? 'on' : ''}" onclick="setSnapWh('oil')">Масла (${all.filter(isOil).length})</button>
    <button class="${snapWh === 'filter' ? 'on' : ''}" onclick="setSnapWh('filter')">Фильтры (${all.filter(isFil).length})</button>
    <button class="${snapWh === 'other' ? 'on' : ''}" onclick="setSnapWh('other')">Прочее (${all.filter(p => !isOil(p) && !isFil(p)).length})</button>
    <button class="${snapWh === 'all' ? 'on' : ''}" onclick="setSnapWh('all')">Всё (${all.length})</button>
  </div>`;
  let buyV = 0, sellV = 0, noBuy = 0;
  prods.forEach(p => {
    const st = Math.max(0, Number(p.stock) || 0);
    if (p.buy !== null && p.buy !== undefined) buyV += st * p.buy; else noBuy++;
    if (p.sell) sellV += st * p.sell;
  });
  h += `<div class="ana-cmp" style="padding:0 0 10px">
    <div><b>${fmtShort(buyV)}</b>остаток по закупке</div>
    <div><b>${fmtShort(sellV)}</b>если продать всё</div>
    <div><b>${fmtShort(sellV - buyV)}</b>возможная наценка</div>
    <div><b class="${noBuy ? 'ana-bad' : ''}">${noBuy}</b>без цены закупки</div>
  </div>`;
  const sorted = prods.slice().sort((a, b) => String(a.category).localeCompare(String(b.category)) || String(a.name).localeCompare(String(b.name)));
  h += '<div class="ana-card">' + (sorted.length ? sorted.map(p => {
    const unit = SNAP_UNIT[p.unit] !== undefined ? SNAP_UNIT[p.unit] : p.unit;
    const stCls = p.status === 'out' ? 'ana-bad' : p.status === 'low' ? 'ana-bad' : '';
    const m = p.margin_pct;
    const mHtml = m === null || m === undefined ? '<span class="sw-m none">наценка —</span>'
      : `<span class="sw-m ${m < 10 ? 'low' : ''}">+${m}%</span>`;
    return `<div class="snap-wh-row"><div class="sw-main">
        <div class="sw-name">${escapeHtml(p.name)}</div>
        <div class="sw-sub">${escapeHtml(p.category_label)} · <span class="${stCls}">остаток ${anaQty(Number(p.stock) || 0, unit)}</span>${p.sold_30d ? ` · продано за 30 дн ${anaQty(p.sold_30d, unit)}` : ''}</div>
      </div><div class="sw-price">${p.buy !== null && p.buy !== undefined ? anaMoney(p.buy) : '<span class="ana-bad">—</span>'} → ${p.sell ? anaMoney(p.sell) : '—'}
        <small>закупка → продажа, за ${unit}</small>${mHtml}</div></div>`;
  }).join('') : '<div class="hint-text" style="padding:14px">В этой группе товаров нет.</div>') + '</div>';
  body.innerHTML = h + snapSuppliersHtml(S);
}
function snapSuppliersHtml(S) {
  const SP = S.suppliers || { list: [] };
  const per = snapDays === 365 ? 'год' : snapDays === 90 ? '3 мес' : '30 дн';
  let h = '<div class="snap-sec"><i class="fa-solid fa-truck-field" style="color:#16A34A"></i> Поставщики</div>';
  if (!SP.list.length) {
    return h + `<div class="ana-card"><div class="hint-text" style="padding:14px">Точка не ведёт поставщиков в OilBook.${SP.no_supplier_products ? ` Товаров на складе без поставщика: ${SP.no_supplier_products}.` : ''}</div></div>`;
  }
  h += `<div class="ana-cmp" style="padding:0 0 10px">
    <div><b>${fmtShort(SP.owe)}</b>долг поставщикам</div>
    <div><b class="${SP.overdue ? 'ana-bad' : ''}">${fmtShort(SP.overdue)}</b>просрочено</div>
    <div><b>${fmtShort(SP.bought_period)}</b>взято товара · ${per}</div>
    <div><b>${SP.list.length}</b>поставщиков${SP.no_supplier_products ? ` · ${SP.no_supplier_products} товар. без поставщика` : ''}</div>
  </div>`;
  SP.list.forEach(s => {
    const bal = s.balance > 0
      ? `<span class="${s.overdue ? 'ana-bad' : ''}">${fmtShort(s.balance)}</span><small>${s.overdue ? 'просрочено ' + fmtShort(s.overdue) : 'долг'}</small>`
      : s.balance < 0 ? `<span class="ana-good">${fmtShort(-s.balance)}</span><small>переплата</small>` : `<span class="ana-mute">0</span><small>долга нет</small>`;
    const terms = [s.pay_days !== null && s.pay_days !== undefined ? `оплата через ${s.pay_days} дн` : '', s.delivery_days ? 'привоз: ' + escapeHtml(s.delivery_days) : '']
      .filter(Boolean).join(' · ');
    const contacts = [
      s.contact ? `<span><i class="fa-solid fa-user"></i> ${escapeHtml(s.contact)}</span>` : '',
      s.phone ? `<a href="tel:${escapeHtml(s.phone)}"><i class="fa-solid fa-phone"></i> ${escapeHtml(s.phone)}</a>` : '',
      s.telegram ? `<a target="_blank" rel="noopener" href="https://t.me/${encodeURIComponent(s.telegram)}"><i class="fa-brands fa-telegram"></i> @${escapeHtml(s.telegram)}</a>` : ''
    ].filter(Boolean).join('');
    const prices = (s.prices || []).map(p => {
      const unit = SNAP_UNIT[p.unit] !== undefined ? SNAP_UNIT[p.unit] : p.unit;
      const ch = p.change_pct === null || p.change_pct === undefined ? ''
        : `<small class="${p.change_pct > 0 ? 'ana-bad' : 'ana-good'}">${p.change_pct > 0 ? '▲' : '▼'} ${Math.abs(p.change_pct)}%</small>`;
      return `<div class="ana-row"><div class="ar-main"><div class="ar-name">${escapeHtml(p.name)}</div>
        <div class="ar-sub">последняя закупка ${fmtDay(p.last_date)} · закупок: ${p.times}</div></div>
        <div class="ar-val">${anaMoney(p.last)} <span style="font-size:11px;color:#64748B">/${unit}</span>${ch}</div></div>`;
    }).join('');
    const noHist = (s.products || []).filter(n => !(s.prices || []).some(p => p.name === n));
    h += `<details class="ana-card sup-card"><summary>
        <div class="ar-main"><div class="ar-name">${escapeHtml(s.name)}</div><div class="ar-sub">${terms || 'условия не указаны'}</div></div>
        <div class="ar-val">${bal}</div><i class="fa-solid fa-chevron-down sup-chev"></i>
      </summary>
      ${contacts ? `<div class="sup-contacts">${contacts}</div>` : ''}
      <div class="ana-cmp">
        <div><b>${fmtShort(s.bought_period)}</b>взято · ${per}</div>
        <div><b>${fmtShort(s.paid_period)}</b>оплачено · ${per}</div>
        <div><b>${fmtShort(s.bought_all)}</b>взято за всё время · ${s.order_count} заказ.</div>
        <div><b>${fmtShort(s.paid_all)}</b>оплачено за всё время</div>
      </div>
      <div class="ana-note">Последний заказ: ${fmtDay(s.last_order)} · последняя оплата: ${fmtDay(s.last_payment)}${s.next_due ? ` · следующий платёж до ${fmtDay(s.next_due.date)} — ${fmtShort(s.next_due.amount)}` : ''}${s.oldest_overdue ? ` · <span class="ana-bad">просрочка с ${fmtDay(s.oldest_overdue)}</span>` : ''}</div>
      ${prices ? '<div class="sup-h">Цены закупки у этого поставщика</div>' + prices : ''}
      ${noHist.length ? `<div class="sup-h">Товары поставщика без принятых заказов</div><div class="ana-brands" style="padding:0 14px 12px">${noHist.map(n => `<span>${escapeHtml(n)}</span>`).join('')}</div>` : ''}
      ${s.note ? `<div class="ana-note">📝 ${escapeHtml(s.note)}</div>` : ''}
    </details>`;
  });
  return h;
}
if (location.hash === '#income') admTab('income');
if (location.hash === '#analytics') admTab('analytics');
if (location.hash === '#map') admTab('map');
</script>
</body>
</html>
"""
assert ADMIN_PAGE.count(_SW_SNIPPET) == 1
ADMIN_PAGE = ADMIN_PAGE.replace(_SW_SNIPPET, NET_GUARD_JS + _SW_SNIPPET, 1)


@app.route("/admin")
@admin_required
def admin_page():
    return render_template_string(ADMIN_PAGE, T=i18n.get_texts("ru"))


ADMIN_HELP_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Справка администратора — OilBook</title>
<link rel="icon" href="/static/icons/icon-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
  :root { --bg:#F1F5F9; --text:#1E293B; --hint:#94A3B8; --blue:#0F52BA; --darkblue:#0A2540; --border:#E2E8F0;
          --font-display:'Space Grotesk', sans-serif; --font-body:'Plus Jakarta Sans', -apple-system, sans-serif; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:var(--font-body); }
  .wrap { max-width:760px; margin:0 auto; padding:14px 14px 30px; padding-top:calc(14px + env(safe-area-inset-top, 0px)); }
  .back { display:inline-flex; align-items:center; gap:8px; color:var(--blue); font-weight:600; text-decoration:none; font-size:14px; margin:2px 0 12px; }
""" + HELP_CSS + """
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/admin"><i class="fa-solid fa-arrow-left"></i> Назад в админ-панель</a>
  <div id="view-help">
""" + HELP_VIEW + """
  </div>
</div>
""" + HELP_JS + """
</body>
</html>
"""


@app.route("/admin/help")
@admin_required
def admin_help_page():
    T = dict(i18n.get_texts("ru"))
    T["tab_help"] = "Справка администратора"
    return render_template_string(
        ADMIN_HELP_PAGE, T=T, help_sections=help_content.build_admin(),
        help_role="администратор платформы", help_support="", help_support_url="")


@app.route("/api/admin/shops")
@admin_required
def api_admin_shops():
    shops = db.list_shops()
    for s in shops:
        s["owner_link"] = _client_link(f"owner_{s['owner_link_token']}") if s.get("owner_link_token") else None
        s["sub"] = _admin_sub_summary(s)
    return jsonify(shops)


@app.route("/api/admin/map")
@admin_required
def api_admin_map():
    """Карта точек: координаты, статус и аналитика за период (по умолчанию 30 дней)."""
    try:
        days = int(request.args.get("days") or 30)
    except ValueError:
        days = 30
    return jsonify(db.get_map_points(days))


@app.route("/api/admin/analytics")
@admin_required
def api_admin_analytics():
    """Аналитика продаж всех точек: товары, бренды, цены продажи и закупки."""
    try:
        days = int(request.args.get("days") or 30)
    except ValueError:
        days = 30
    return jsonify(db.get_admin_analytics(days))


def _int_arg(name, default):
    try:
        return max(1, min(int(request.args.get(name) or default), 730))
    except ValueError:
        return default


@app.route("/api/admin/names")
@admin_required
def api_admin_names():
    """«Сопоставление»: нераспознанные, исправленные автоматически и подтверждённые названия."""
    return jsonify(db.get_name_review(_int_arg("days", 365)))


@app.route("/api/admin/names", methods=["POST"])
@admin_required
def api_admin_names_save():
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "нечего сохранять"}), 400
    n = db.save_name_aliases(items[:500])
    return jsonify({"ok": True, "saved": n})


@app.route("/api/admin/names/delete", methods=["POST"])
@admin_required
def api_admin_names_delete():
    data = request.get_json(force=True) or {}
    ok = db.delete_name_alias(str(data.get("raw") or ""))
    return jsonify({"ok": ok})


@app.route("/api/admin/price_problems")
@admin_required
def api_admin_price_problems():
    """Подозрительные цены продажи/закупки за период."""
    return jsonify(db.get_price_problems(_int_arg("days", 90)))


@app.route("/api/admin/shops/<int:shop_id>/snapshot")
@admin_required
def api_admin_shop_snapshot(shop_id):
    """Копия статистики брендов и склада одной точки — для окна на карте."""
    data = db.get_admin_shop_snapshot(shop_id, _int_arg("days", 30))
    if not data:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    return jsonify(data)


@app.route("/api/admin/shops/<int:shop_id>/location", methods=["POST"])
@admin_required
def api_admin_set_location(shop_id):
    """Поставить точку/филиал на карту (или убрать с карты — пустые lat/lon)."""
    data = request.get_json(force=True) or {}
    lat, lon = data.get("lat"), data.get("lon")
    if lat in (None, "") and lon in (None, ""):
        lat = lon = None
    else:
        try:
            lat, lon = round(float(lat), 6), round(float(lon), 6)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "неверные координаты"}), 400
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return jsonify({"ok": False, "error": "координаты вне допустимого диапазона"}), 400
    if not db.set_shop_location(shop_id, lat, lon):
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    return jsonify({"ok": True, "lat": lat, "lon": lon})


@app.route("/api/admin/backup_now", methods=["POST"])
@admin_required
def api_admin_backup_now():
    """Ручной запуск резервной копии — чтобы проверить прямо сейчас, не
    дожидаясь ночной автоматической отправки, и сразу увидеть настоящую
    причину, если что-то не так (например, не задан ADMIN_TELEGRAM_ID)."""
    if not ADMIN_TELEGRAM_ID:
        return jsonify({"ok": False, "error": "ADMIN_TELEGRAM_ID не задан на сервере — некому отправлять резервную копию"}), 400
    ok, err, size_mb = _create_and_send_backup(ADMIN_TELEGRAM_ID)
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True, "size_mb": round(size_mb, 1), "bot_username": BOT_USERNAME or None})


@app.route("/api/admin/restore_backup", methods=["POST"])
@admin_required
def api_admin_restore_backup():
    """Восстановление базы из загруженного файла — заменяет ВСЕ текущие
    данные платформы. Требует точную фразу-подтверждение (не просто
    галочку в интерфейсе) — вторая линия защиты от случайного нажатия,
    раз действие необратимо без отдельной резервной копии."""
    if request.form.get("confirm") != "ЗАМЕНИТЬ":
        return jsonify({"ok": False, "error": "не подтверждено — введите точно 'ЗАМЕНИТЬ'"}), 400
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"ok": False, "error": "файл не выбран"}), 400
    ok, err = _restore_from_backup(uploaded.read(), notify_chat_id=ADMIN_TELEGRAM_ID or None)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/admin/shops", methods=["POST"])
@admin_required
def api_admin_create_shop():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    shop_name = (data.get("shop_name") or "").strip()
    if not username or not shop_name:
        return jsonify({"ok": False, "error": "укажите логин и название точки"}), 400
    if db.username_taken(username):
        return jsonify({"ok": False, "error": "такой логин уже занят"}), 400

    password = (data.get("password") or "").strip() or secrets.token_urlsafe(6)
    shop = db.create_shop(
        username, password, shop_name=shop_name,
        phone=data.get("phone") or None, address=data.get("address") or None,
        hours=data.get("hours") or None,
        lat=float(data["lat"]) if data.get("lat") else None,
        lon=float(data["lon"]) if data.get("lon") else None,
        notify_telegram_id=data.get("notify_telegram_id") or None,
        client_group=(data.get("client_group") or "").strip() or None,
    )
    return jsonify({"ok": True, "id": shop["id"], "username": username, "password": password})


@app.route("/api/admin/shops/<int:shop_id>/client_group", methods=["POST"])
@admin_required
def api_admin_set_client_group(shop_id):
    data = request.get_json(force=True)
    db.set_shop_client_group(shop_id, (data.get("client_group") or "").strip())
    return jsonify({"ok": True})


@app.route("/api/admin/shops/<int:shop_id>/toggle", methods=["POST"])
@admin_required
def api_admin_toggle_shop(shop_id):
    data = request.get_json(force=True)
    db.set_shop_active(shop_id, bool(data.get("active")))
    return jsonify({"ok": True})


@app.route("/api/admin/shops/<int:shop_id>/toggle_sms", methods=["POST"])
@admin_required
def api_admin_toggle_sms(shop_id):
    data = request.get_json(force=True)
    db.set_shop_sms_enabled(shop_id, bool(data.get("enabled")))
    return jsonify({"ok": True})


@app.route("/api/admin/shops/<int:shop_id>/toggle_warehouse", methods=["POST"])
@admin_required
def api_admin_toggle_warehouse(shop_id):
    data = request.get_json(force=True)
    db.set_shop_warehouse_enabled(shop_id, bool(data.get("enabled")))
    return jsonify({"ok": True})


@app.route("/api/admin/shops/<int:shop_id>/reset_password", methods=["POST"])
@admin_required
def api_admin_reset_password(shop_id):
    shop = db.get_shop(shop_id)
    if not shop:
        return jsonify({"ok": False, "error": "shop not found"}), 404
    new_password = secrets.token_urlsafe(6)
    db.reset_shop_password(shop_id, new_password)
    return jsonify({"ok": True, "password": new_password})


@app.route("/api/admin/shops/<int:shop_id>/identity", methods=["POST"])
@admin_required
def api_admin_update_identity(shop_id):
    """Меняет название точки и/или логин — единственное, что нельзя было
    поправить после создания точки."""
    shop = db.get_shop(shop_id)
    if not shop:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    data = request.get_json(force=True)
    shop_name = (data.get("shop_name") or "").strip()
    username = (data.get("username") or "").strip()
    if not shop_name or not username:
        return jsonify({"ok": False, "error": "укажите и название, и логин"}), 400
    if username != shop["username"] and db.username_taken(username):
        return jsonify({"ok": False, "error": "такой логин уже занят"}), 400
    db.update_shop_identity(shop_id, shop_name, username)
    return jsonify({"ok": True, "shop_name": shop_name, "username": username})


@app.route("/api/admin/shops/<int:shop_id>/notify_telegram", methods=["POST"])
@admin_required
def api_admin_set_notify_telegram(shop_id):
    shop = db.get_shop(shop_id)
    if not shop:
        return jsonify({"ok": False, "error": "shop not found"}), 404
    data = request.get_json(force=True)
    notify_id = (data.get("notify_telegram_id") or "").strip()
    db.set_shop_notify_telegram_id(shop_id, notify_id or None)
    return jsonify({"ok": True, "notify_telegram_id": notify_id or None})


@app.route("/api/admin/shops/<int:shop_id>/test_telegram", methods=["POST"])
@admin_required
def api_admin_test_telegram(shop_id):
    """Пробная отправка — сразу видно, реально ли бот может писать этому
    получателю (частая причина 'не приходит' — получатель ни разу не писал
    боту первым, Telegram такое запрещает)."""
    shop = db.get_shop(shop_id)
    if not shop:
        return jsonify({"ok": False, "error": "shop not found"}), 404
    notify_id = shop.get("notify_telegram_id")
    if not notify_id:
        return jsonify({"ok": False, "error": "у точки не указан Telegram ID"}), 400
    text = f"✅ Тестовое сообщение от платформы — если вы это видите, связь с точкой «{shop.get('shop_name') or shop['username']}» настроена верно."
    sent = _send_telegram_message(notify_id, text)
    if not sent:
        return jsonify({"ok": False, "error": "не удалось отправить — скорее всего, получатель ни разу не писал этому боту. Попросите его открыть бота в Telegram и нажать «Старт»"}), 400
    return jsonify({"ok": True})


@app.route("/api/admin/shops/<int:shop_id>/employees")
@admin_required
def api_admin_list_employees(shop_id):
    return jsonify(db.list_shop_employees(shop_id))


@app.route("/api/admin/shops/<int:shop_id>/employees", methods=["POST"])
@admin_required
def api_admin_create_employee(shop_id):
    shop = db.get_shop(shop_id)
    if not shop:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    full_name = (data.get("full_name") or "").strip() or None
    if not username:
        return jsonify({"ok": False, "error": "укажите логин"}), 400
    result = db.create_shop_employee(shop_id, username, full_name=full_name)
    if not result:
        return jsonify({"ok": False, "error": "такой логин уже занят"}), 400
    return jsonify({"ok": True, **result})


@app.route("/api/admin/shops/<int:shop_id>/branches")
@admin_required
def api_admin_list_branches(shop_id):
    return jsonify(db.get_branches(shop_id))


@app.route("/api/admin/shops/<int:shop_id>/branches", methods=["POST"])
@admin_required
def api_admin_create_branch(shop_id):
    parent = db.get_shop(shop_id)
    if not parent:
        return jsonify({"ok": False, "error": "главная точка не найдена"}), 404
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    shop_name = (data.get("shop_name") or "").strip()
    if not username or not shop_name:
        return jsonify({"ok": False, "error": "укажите логин и название филиала"}), 400
    if db.username_taken(username):
        return jsonify({"ok": False, "error": "такой логин уже занят"}), 400
    password = (data.get("password") or "").strip() or secrets.token_urlsafe(6)
    branch = db.create_branch_shop(
        shop_id, username, password, shop_name=shop_name,
        phone=data.get("phone") or None, address=data.get("address") or None,
        hours=data.get("hours") or None,
        lat=float(data["lat"]) if data.get("lat") else None,
        lon=float(data["lon"]) if data.get("lon") else None,
        notify_telegram_id=data.get("notify_telegram_id") or None,
    )
    db.set_shop_warehouse_enabled(branch["id"], True)  # филиалу склад нужен сразу, это весь смысл филиала
    pending = db.new_branch_needs_payment(parent)
    if pending:
        db.set_branch_pending(branch["id"], True)  # заработает после оплаты
    return jsonify({"ok": True, "id": branch["id"], "username": username, "password": password,
                    "sub_pending": pending})


def _admin_branch_or_404(branch_id):
    shop = db.get_shop(branch_id)
    if not shop or shop.get("role") != "branch":
        return None
    return shop


@app.route("/api/admin/branches/<int:branch_id>", methods=["POST"])
@admin_required
def api_admin_update_branch(branch_id):
    """Изменить филиал: название, логин, телефон, адрес, часы, локация, Telegram."""
    branch = _admin_branch_or_404(branch_id)
    if not branch:
        return jsonify({"ok": False, "error": "филиал не найден"}), 404
    data = request.get_json(force=True)
    shop_name = (data.get("shop_name") or "").strip()
    username = (data.get("username") or "").strip()
    if not shop_name or not username:
        return jsonify({"ok": False, "error": "укажите название и логин"}), 400
    if username != branch["username"] and db.username_taken(username):
        return jsonify({"ok": False, "error": "такой логин уже занят"}), 400
    try:
        lat = float(data["lat"]) if data.get("lat") not in (None, "") else None
        lon = float(data["lon"]) if data.get("lon") not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "неверная локация"}), 400
    db.update_branch_details(
        branch_id, shop_name, username,
        phone=(data.get("phone") or "").strip() or None,
        address=(data.get("address") or "").strip() or None,
        hours=(data.get("hours") or "").strip() or None,
        lat=lat, lon=lon,
        notify_telegram_id=(data.get("notify_telegram_id") or "").strip() or None,
    )
    return jsonify({"ok": True})


@app.route("/api/admin/branches/<int:branch_id>/delete_preview")
@admin_required
def api_admin_branch_delete_preview(branch_id):
    branch = _admin_branch_or_404(branch_id)
    if not branch:
        return jsonify({"ok": False, "error": "филиал не найден"}), 404
    return jsonify({"ok": True, "name": branch.get("shop_name") or branch["username"],
                    "counts": db.branch_data_counts(branch_id)})


@app.route("/api/admin/branches/<int:branch_id>", methods=["DELETE"])
@admin_required
def api_admin_delete_branch(branch_id):
    """Удаление филиала со всеми данными. Сначала — обязательная резервная
    копия всей базы в Telegram; если она не ушла, филиал НЕ удаляется."""
    branch = _admin_branch_or_404(branch_id)
    if not branch:
        return jsonify({"ok": False, "error": "филиал не найден"}), 404
    data = request.get_json(force=True) or {}
    name = branch.get("shop_name") or branch["username"]
    if (data.get("confirm_name") or "").strip() != name:
        return jsonify({"ok": False, "error": "название для подтверждения не совпадает"}), 400
    if not ADMIN_TELEGRAM_ID:
        return jsonify({"ok": False, "error": "ADMIN_TELEGRAM_ID не задан — без резервной копии удалять нельзя"}), 400
    ok, err, _ = _create_and_send_backup(ADMIN_TELEGRAM_ID, caption_note=f"\n⚠️ Перед удалением филиала «{name}»")
    if not ok:
        return jsonify({"ok": False, "error": f"резервная копия не отправилась ({err}) — филиал не удалён"}), 500
    db.delete_branch_with_data(branch_id)
    return jsonify({"ok": True})


@app.route("/api/admin/employees/<int:employee_id>/reset_password", methods=["POST"])
@admin_required
def api_admin_reset_employee_password(employee_id):
    shop_id = request.get_json(force=True).get("shop_id")
    new_password = db.reset_shop_employee_password(employee_id, shop_id)
    if not new_password:
        return jsonify({"ok": False, "error": "сотрудник не найден"}), 404
    return jsonify({"ok": True, "password": new_password})


@app.route("/api/admin/employees/<int:employee_id>", methods=["DELETE"])
@admin_required
def api_admin_delete_employee(employee_id):
    shop_id = request.get_json(force=True).get("shop_id") if request.data else None
    if not shop_id:
        shop_id = request.args.get("shop_id", type=int)
    ok = db.delete_shop_employee(employee_id, shop_id)
    if not ok:
        return jsonify({"ok": False, "error": "сотрудник не найден"}), 404
    return jsonify({"ok": True})


# ============ ТАБЛО (для ANPR-камеры + телевизора у входа, своё на каждую точку) ============

def _extract_plate_from_request():
    plate = request.args.get("plate")
    if plate:
        return plate
    if request.is_json:
        data = request.get_json(silent=True) or {}
        for key in ("plate", "plateNumber", "licensePlate", "carNumber", "car_number"):
            if data.get(key):
                return data[key]
    if request.form.get("plate"):
        return request.form.get("plate")
    for f in request.files.values():
        if (f.mimetype or "").endswith("xml") or (f.filename or "").endswith(".xml"):
            xml_text = f.read().decode("utf-8", errors="ignore")
            m = re.search(r"<(?:licensePlate|plateNumber)>([^<]+)</(?:licensePlate|plateNumber)>", xml_text)
            if m:
                return m.group(1)
    return None


@app.route("/api/anpr/<anpr_token>", methods=["GET", "POST"])
def api_anpr(anpr_token):
    """Сюда камера ОДНОЙ КОНКРЕТНОЙ точки присылает распознанный номер —
    токен в самом адресе однозначно определяет точку, так что табло разных
    точек никогда не пересекаются."""
    shop = db.get_shop_by_anpr_token(anpr_token)
    if not shop or not shop["is_active"]:
        return jsonify({"ok": False, "error": "invalid shop token"}), 403

    plate = _extract_plate_from_request()
    if not plate:
        return jsonify({"ok": False, "error": "no plate found in request"}), 400

    plate = db.normalize_plate(plate)
    with _display_lock:
        _display_states[shop["id"]] = {"plate": plate, "shown_at": time.time()}

    return jsonify({"ok": True, "plate": plate})


@app.route("/api/display_state/<anpr_token>")
def api_display_state(anpr_token):
    shop = db.get_shop_by_anpr_token(anpr_token)
    if not shop or not shop["is_active"]:
        return jsonify({"active": False})

    with _display_lock:
        state = _display_states.get(shop["id"], {"plate": None, "shown_at": 0})

    if not state["plate"] or (time.time() - state["shown_at"]) > DISPLAY_SHOW_SECONDS:
        return jsonify({"active": False})

    car, history = db.get_car_history(shop["id"], state["plate"])
    if not car:
        return jsonify({"active": True, "found": False, "plate": state["plate"]})

    last = history[0] if history else None
    return jsonify({
        "active": True, "found": True, "plate": state["plate"],
        "owner_name": car["owner_name"],
        "last_service_date": last["change_date"] if last else None,
        "oil_brand": last["oil_brand"] if last else None,
        "service_type": last["service_type"] if last else None,
    })


DISPLAY_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>{{ T.app_title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Teko:wght@500;600;700&family=Exo+2:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin:0; padding:0; }
  body {
    background: radial-gradient(circle at center, #1A0B0A 0%, #0A0A0B 100%);
    color: #F5F5F2; font-family: 'Exo 2', -apple-system, sans-serif;
    height: 100vh; display:flex; align-items:center; justify-content:center;
    overflow: hidden; text-align:center;
  }
  .idle .shop { font-family:'Teko', sans-serif; font-weight:600; font-size: 4.5vw; letter-spacing:1px; opacity:.9; text-transform:uppercase; }
  .idle .clock { font-family:'IBM Plex Mono', monospace; font-weight:600; font-size: 10vw; margin-top: 2vh; font-variant-numeric: tabular-nums; color:#E8352E; }
  .idle .date { font-size: 2.2vw; opacity:.6; margin-top:1vh; }
  .active { animation: fadein .4s ease; }
  .active .greet { font-family:'Teko', sans-serif; font-weight:600; font-size: 5vw; color:#3FBE7E; text-transform:uppercase; }
  .active .plate { font-family:'IBM Plex Mono', monospace; font-size: 6vw; font-weight:600; letter-spacing:4px; margin: 3vh 0; padding: 1vh 3vw;
    border: 4px solid #F5F5F2; border-radius: 6px; display:inline-block; }
  .active .info { font-size: 2.4vw; opacity:.85; line-height:1.7; margin-top:2vh; }
  .active .notfound { font-size: 3vw; opacity:.8; margin-top:3vh; }
  @keyframes fadein { from{opacity:0; transform:scale(.97);} to{opacity:1; transform:scale(1);} }
</style>
</head>
<body>
<div id="screen"></div>
<script>
const T = {{ t_json|safe }};
const SHOP_NAME = {{ shop_name|tojson }};
const ANPR_TOKEN = {{ anpr_token|tojson }};

function pad(n) { return n.toString().padStart(2, '0'); }
function renderIdle() {
  const now = new Date();
  const days = T.days_of_week;
  document.getElementById('screen').innerHTML = `
    <div class="idle">
      <div class="shop">${SHOP_NAME || '🔧 ' + T.app_title}</div>
      <div class="clock">${pad(now.getHours())}:${pad(now.getMinutes())}</div>
      <div class="date">${days[now.getDay()]}, ${pad(now.getDate())}.${pad(now.getMonth()+1)}.${now.getFullYear()}</div>
    </div>`;
}

function renderActive(d) {
  if (!d.found) {
    document.getElementById('screen').innerHTML = `
      <div class="active">
        <div class="greet">${T.display_welcome} 👋</div>
        <div class="plate">${d.plate}</div>
        <div class="notfound">${T.display_not_client_yet}</div>
      </div>`;
    return;
  }
  const last = d.last_service_date
    ? `${T.display_last_service} ${d.last_service_date}${d.service_type ? ' — ' + d.service_type : ''}${d.oil_brand ? ' (' + d.oil_brand + ')' : ''}`
    : T.display_no_history;
  document.getElementById('screen').innerHTML = `
    <div class="active">
      <div class="greet">${T.display_greeting} ${d.owner_name || ''}!</div>
      <div class="plate">${d.plate}</div>
      <div class="info">${last}</div>
    </div>`;
}

async function tick() {
  try {
    const res = await fetch('/api/display_state/' + ANPR_TOKEN);
    const d = await res.json();
    if (d.active) renderActive(d); else renderIdle();
  } catch (e) { renderIdle(); }
}

tick();
setInterval(tick, 2000);
</script>
</body>
</html>
"""


@app.route("/display/<anpr_token>")
def display_page(anpr_token):
    import json as _json
    shop = db.get_shop_by_anpr_token(anpr_token)
    if not shop or not shop["is_active"]:
        return "Табло не найдено — проверьте ссылку.", 404
    T = i18n.get_texts(shop.get("language") or "ru")
    return render_template_string(
        DISPLAY_PAGE, shop_name=shop.get("shop_name") or "", anpr_token=anpr_token,
        T=T, t_json=_json.dumps(T, ensure_ascii=False),
    )


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
    if st.get("trial") and n is not None and n >= 0:
        # пробный период — плашка видна все 14 дней, владельцу — со ссылкой на оплату
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


def _sub_admin_caption(p: dict) -> str:
    head = db.get_shop(p["shop_id"]) or {}
    name = head.get("shop_name") or head.get("username") or "—"
    n = int(p.get("branch_count") or 0)
    net = "только главная" if n == 0 else f"главная + {n} фил."
    if p["kind"] == "branches":
        try:
            ids = json.loads(p.get("branch_ids") or "[]")
        except ValueError:
            ids = []
        names = ", ".join((db.get_shop(i) or {}).get("shop_name") or str(i) for i in ids) or "—"
        what = f"Оплата новых филиалов: {names}"
    else:
        disc = f" (−{p['discount']}%)" if p.get("discount") else ""
        what = f"Продление {p['months']} мес{disc}"
        if p["kind"] == "both":
            what += " + новые филиалы"
    lines = [
        f"🧾 Оплата подписки №{p['id']}",
        f"Точка: {name} (@{head.get('username', '')})",
        f"Сеть: {net}",
        f"Что: {what}",
        f"Сумма: {_fmt_sum(p.get('amount'))} сум",
    ]
    if p.get("new_until"):
        lines.append(f"Продлится до: {_fmt_day(p['new_until'])}")
    return "\n".join(lines)


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


def _send_receipt_to_admin(p: dict, data_bytes: bytes, fname: str, mime: str):
    """Чек — администратору платформы в Telegram с кнопками ✅/❌. На сервере
    файл не сохраняется: хранится сам Telegram (бесплатно и бессрочно), в базе
    — только file_id. Возвращает (message_id, file_id) или None."""
    if not ADMIN_TELEGRAM_ID:
        return None
    markup = json.dumps({"inline_keyboard": [[
        {"text": "✅ Подтвердить", "callback_data": f"subpay:ok:{p['id']}"},
        {"text": "❌ Отклонить", "callback_data": f"subpay:no:{p['id']}"},
    ]]})
    caption = _sub_admin_caption(p)
    data = {"chat_id": ADMIN_TELEGRAM_ID, "caption": caption, "reply_markup": markup}
    result = None
    if mime in ("image/jpeg", "image/png", "image/webp"):
        result = _tg_api("sendPhoto", data, {"photo": (fname, data_bytes, mime)})
    if not result:
        result = _tg_api("sendDocument", data, {"document": (fname, data_bytes, mime or "application/octet-stream")})
    if not result or not result.get("message_id"):
        return None
    file_id = None
    if result.get("photo"):
        file_id = result["photo"][-1].get("file_id")  # самый крупный размер
    elif result.get("document"):
        file_id = result["document"].get("file_id")
    return result["message_id"], file_id


def _sub_owner_link() -> str:
    return (PUBLIC_URL.rstrip("/") + "/subscription") if PUBLIC_URL else "/subscription"


def notify_sub_decision(p: dict):
    """Сообщение владельцу точки о решении по чеку."""
    head = db.get_shop(p["shop_id"]) or {}
    chat = head.get("notify_telegram_id")
    if not chat:
        return
    lang = head.get("language") or "ru"
    if p["status"] == "confirmed":
        if p["kind"] == "branches":
            text = i18n.t("sub_bot_confirmed_br", lang)
        else:
            text = i18n.t("sub_bot_confirmed", lang, date=_fmt_day(p.get("new_until")))
    else:
        contact = db.get_platform_settings().get("support_contact") or ""
        text = i18n.t("sub_bot_rejected", lang, link=_sub_owner_link())
        if contact:
            text += "\n" + i18n.t("sub_support", lang, contact=contact)
    _send_telegram_message(chat, text)


def sub_decide(payment_id: int, approve: bool):
    """Единая точка решения по чеку — и из админки, и из кнопок в Telegram.
    Возвращает заявку после решения или None, если её уже обработали."""
    p = db.confirm_sub_payment(payment_id) if approve else db.reject_sub_payment(payment_id)
    if not p:
        return None
    if p.get("tg_message_id") and ADMIN_TELEGRAM_ID:
        mark = (f"✅ Подтверждено — действует до {_fmt_day(p.get('new_until'))}" if approve
                else "❌ Отклонено")
        _tg_api("editMessageCaption", {"chat_id": ADMIN_TELEGRAM_ID, "message_id": p["tg_message_id"],
                                       "caption": _sub_admin_caption(p) + "\n\n" + mark})
    try:
        notify_sub_decision(p)
    except Exception as e:
        logger.error(f"Не удалось уведомить точку о решении по чеку {payment_id}: {e}")
    return p


_SUB_ALLOWED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                    ".heic": "image/heic", ".heif": "image/heif", ".gif": "image/gif", ".pdf": "application/pdf"}
_SUB_MAX_FILE = 10 * 1024 * 1024


def _sub_option_text(T, o, branch_part) -> str:
    """Подпись под сроком: цена в месяц, экономия, доплата за новые филиалы."""
    extra = branch_part["amount"] if branch_part else 0
    parts = []
    if o["discount"] or extra:
        per_month = int(round((o["amount"] - extra) / o["months"] / 100.0)) * 100
        parts.append(T["sub_per_month"].format(sum=_fmt_sum(per_month)))
    else:
        parts.append(T["sub_no_discount"])
    if o["saving"]:
        parts.append(T["sub_saving"].format(sum=_fmt_sum(o["saving"])))
    if extra:
        parts.append(T["sub_plus_branches"].format(sum=_fmt_sum(extra)))
    return " · ".join(parts)


@app.route("/subscription")
@login_required
@sub_exempt
def subscription_page():
    shop = db.get_shop(g.shop_id)
    st = g.sub
    T = g.T
    ctx = {"T": T, "lang": g.lang, "st": st, "mode": "owner" if _is_sub_owner() else "staff",
           "paid_until_txt": _fmt_day(st.get("paid_until")) if st.get("paid_until") else T["sub_not_set"]}
    if ctx["mode"] == "staff":
        return render_template_string(SUB_PAGE, **ctx)

    q = db.sub_quote(g.shop_id)
    settings = q["settings"]
    n = st.get("days_left")
    if st["lifetime"]:
        chip = ("blue", "∞")
    elif st["expired"]:
        chip = ("bad", T["sub_status_blocked"])
    elif n is None:
        chip = ("warn", T["sub_not_set"])
    elif n == 0:
        chip = ("warn", T["sub_last_day"])
    elif n <= 5:
        chip = ("warn", T["sub_days_left"].format(n=n))
    else:
        chip = ("ok", T["sub_status_active"])
    net = (T["sub_network_main"].format(sum=_fmt_sum(q["monthly"])) if q["branch_count"] == 0
           else T["sub_network_br"].format(n=q["branch_count"], sum=_fmt_sum(q["monthly"])))
    options = []
    for o in q["options"]:
        options.append({
            "months": o["months"], "label": T[f"sub_m{o['months']}"], "discount": o["discount"],
            "amount_txt": _fmt_sum(o["amount"]), "until_txt": _fmt_day(o["new_until"]),
            "sub_txt": _sub_option_text(T, o, q["branch_part"]),
            "best": o["months"] == 12,
        })
    names = ", ".join(b["name"] for b in q["pending_branches"])
    branch_txt = None
    if q["branch_part"]:
        bp = q["branch_part"]
        branch_txt = T["sub_branches_text"].format(names=names, days=bp["days"], date=_fmt_day(bp["until"]))
        if bp["discount"]:
            branch_txt += T["sub_branches_disc"].format(d=bp["discount"])
    pending = db.get_pending_sub_payment(g.shop_id)
    pending_txt = None
    if pending:
        what = (T["sub_what_branches"] if pending["kind"] == "branches"
                else T["sub_what_extend"].format(m=pending["months"]))
        pending_txt = T["sub_pending_text"].format(what=what, sum=_fmt_sum(pending["amount"]),
                                                   date=_fmt_day(pending["created_at"]))
    history = []
    for p in db.list_sub_payments(head_id=g.shop_id, limit=12):
        if p["status"] not in ("confirmed", "rejected", "pending"):
            continue
        if p["kind"] == "lifetime":
            what = T["sub_lifetime_title"]
        elif p["kind"] == "branches":
            what = T["sub_what_branches"]
        else:
            what = T["sub_what_extend"].format(m=p["months"])
        left = f"{_fmt_day(p['created_at'])} · {what}"
        st_txt = {"confirmed": T["sub_st_confirmed"], "rejected": T["sub_st_rejected"],
                  "pending": T["sub_st_pending"]}[p["status"]]
        method = T["sub_method_cash"] if p.get("method") == "cash" else T["sub_method_card"]
        history.append({"left": left, "sub": f"{method} · {st_txt}",
                        "right": _fmt_sum(p["amount"]) if p.get("amount") else "",
                        "bad": p["status"] == "rejected"})
    ctx.update(
        q=q, chip=chip, net=net, options=options, branch_txt=branch_txt,
        branch_amount_txt=_fmt_sum(q["branch_part"]["amount"]) if q["branch_part"] else "",
        branch_until_txt=_fmt_day(q["branch_part"]["until"]) if q["branch_part"] else "",
        pending_txt=pending_txt, history=history,
        lifetime_branches=[T["sub_lifetime_branch"].format(name=b["name"]) for b in q["pending_branches"]]
        if st["lifetime"] else [],
        expired_txt=T["sub_expired_text"].format(date=_fmt_day(st.get("paid_until"))),
        card_number=settings.get("card_number") or "", card_holder=settings.get("card_holder") or "",
        support=T["sub_support"].format(contact=settings["support_contact"]) if settings.get("support_contact") else "",
    )
    return render_template_string(SUB_PAGE, **ctx)


@app.route("/api/subscription/pay", methods=["POST"])
@login_required
@sub_exempt
def api_subscription_pay():
    T = g.T
    if not _is_sub_owner():
        return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
    q = db.sub_quote(g.shop_id)
    if q["state"]["lifetime"]:
        return jsonify({"ok": False, "error": "lifetime"}), 400
    if not q["settings"].get("card_number"):
        return jsonify({"ok": False, "error": T["sub_no_card"]}), 400
    choice = (request.form.get("choice") or "").strip()
    pending_ids = [b["id"] for b in q["pending_branches"]]
    if choice == "branches":
        if not q["branch_part"]:
            return jsonify({"ok": False, "error": "нет филиалов для оплаты"}), 400
        kind, months, amount, discount, new_until = "branches", None, q["branch_part"]["amount"], \
            q["branch_part"]["discount"], q["branch_part"]["until"]
    else:
        opt = next((o for o in q["options"] if str(o["months"]) == choice), None)
        if not opt:
            return jsonify({"ok": False, "error": "выберите срок"}), 400
        kind = "both" if q["branch_part"] else "extend"
        months, amount, discount, new_until = opt["months"], opt["amount"], opt["discount"], opt["new_until"]
    f = request.files.get("receipt")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": T["sub_file_needed"]}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    mime = _SUB_ALLOWED_EXT.get(ext)
    if not mime and (f.mimetype or "").startswith("image/"):
        mime, ext = f.mimetype, ".jpg" if f.mimetype == "image/jpeg" else ".img"
    if not mime:
        return jsonify({"ok": False, "error": T["sub_file_type"]}), 400
    data = f.read(_SUB_MAX_FILE + 1)
    if len(data) > _SUB_MAX_FILE:
        return jsonify({"ok": False, "error": T["sub_file_big"]}), 400
    if not data:
        return jsonify({"ok": False, "error": T["sub_file_needed"]}), 400
    if not ADMIN_TELEGRAM_ID or not BOT_TOKEN:
        logger.error("Чек не принят: на сервере не заданы ADMIN_TELEGRAM_ID / BOT_TOKEN")
        return jsonify({"ok": False, "error": T["sub_err"]}), 503
    pid = db.create_sub_payment(g.shop_id, kind, months, amount, discount, pending_ids,
                                q["branch_count"], new_until)
    sent = None
    try:
        sent = _send_receipt_to_admin(db.get_sub_payment(pid), data, f"check_{pid}{ext}", mime)
    except Exception as e:
        logger.error(f"Не удалось отправить чек {pid} администратору: {e}")
    if not sent:
        db.sub_payment_failed(pid)  # чек не дошёл — человек просто отправит ещё раз
        return jsonify({"ok": False, "error": T["sub_err"]}), 502
    db.sub_payment_sent(pid, sent[0], sent[1], mime)
    return jsonify({"ok": True, "id": pid})


# ---------- Подписка: админка ----------

def _admin_sub_summary(shop: dict) -> dict:
    q = db.sub_quote(shop["id"])
    pend = db.get_pending_sub_payment(shop["id"])
    st = q["state"]
    life = None
    if st["lifetime"]:
        rows = [r for r in db.list_sub_payments(head_id=shop["id"], status="confirmed", limit=50) if r["kind"] == "lifetime"]
        if rows:
            life = {"id": rows[0]["id"], "amount": rows[0].get("amount")}
    return {
        "custom_price": q.get("custom_price"),
        "lifetime_payment": life,
        "lifetime": st["lifetime"], "paid_until": st["paid_until"], "days_left": st["days_left"],
        "trial": st.get("trial", False), "self_registered": bool(shop.get("self_registered")),
        "expired": st["expired"], "monthly": q["monthly"], "branch_count": q["branch_count"],
        "pending_branches": len(q["pending_branches"]),
        "pending_payment": {"id": pend["id"], "amount": pend["amount"], "kind": pend["kind"],
                            "months": pend["months"], "has_receipt": bool(pend.get("tg_file_id"))}
        if pend else None,
    }


def _parse_admin_sum(raw):
    """Сумма из формы админа: «1 270 000» → 1270000; пусто → None; мусор → False."""
    if raw is None:
        return None
    txt = re.sub(r"[\s\u00a0]", "", str(raw))
    if not txt:
        return None
    if not txt.isdigit():
        return False
    return int(txt) or None


@app.route("/api/admin/income")
@admin_required
def api_admin_income():
    return jsonify({"ok": True, "stats": db.get_income_stats()})


@app.route("/api/admin/sub/settings")
@admin_required
def api_admin_sub_settings():
    return jsonify({"ok": True, "settings": db.get_platform_settings()})


@app.route("/api/admin/sub/settings", methods=["POST"])
@admin_required
def api_admin_sub_settings_save():
    data = request.get_json(force=True) or {}
    try:
        db.set_platform_settings({k: v for k, v in data.items() if k in db.SUB_DEFAULTS})
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "проверьте числа"}), 400
    return jsonify({"ok": True, "settings": db.get_platform_settings()})


@app.route("/api/admin/sub/payments")
@admin_required
def api_admin_sub_payments():
    status = request.args.get("status") or None
    rows = db.list_sub_payments(status=status, limit=100)
    for r in rows:
        r["caption"] = _sub_admin_caption(r)
        r["has_receipt"] = bool(r.get("tg_file_id"))
        r.pop("tg_file_id", None)
    return jsonify({"ok": True, "payments": rows})


@app.route("/api/admin/sub/payments/<int:payment_id>/<action>", methods=["POST"])
@admin_required
def api_admin_sub_decide(payment_id, action):
    if action == "amount":
        amount = _parse_admin_sum((request.get_json(force=True) or {}).get("amount"))
        if amount is False:
            return jsonify({"ok": False, "error": "сумма — только цифры"}), 400
        if not db.admin_set_payment_amount(payment_id, amount):
            return jsonify({"ok": False, "error": "сумму можно менять только у оплат, внесённых вручную"}), 400
        return jsonify({"ok": True})
    if action == "cancel":
        if not db.admin_cancel_payment(payment_id):
            return jsonify({"ok": False, "error": "оплата не найдена"}), 404
        return jsonify({"ok": True})
    if action not in ("confirm", "reject"):
        return jsonify({"ok": False, "error": "неизвестное действие"}), 400
    p = sub_decide(payment_id, action == "confirm")
    if not p:
        return jsonify({"ok": False, "error": "этот чек уже обработан"}), 409
    return jsonify({"ok": True, "new_until": p.get("new_until")})


@app.route("/api/admin/sub/receipt/<int:payment_id>")
@admin_required
def api_admin_sub_receipt(payment_id):
    """Показывает чек, который лежит в Telegram (на сервере его нет)."""
    p = db.get_sub_payment(payment_id)
    if not p or not p.get("tg_file_id"):
        return "Чек не найден", 404
    info = _tg_api("getFile", {"file_id": p["tg_file_id"]})
    if not info or not info.get("file_path"):
        return "Не удалось получить чек из Telegram — откройте его в чате с ботом", 502
    try:
        resp = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{info['file_path']}", timeout=30)
    except Exception as e:
        logger.error(f"Чек {payment_id} не скачан из Telegram: {e}")
        return "Не удалось получить чек из Telegram — откройте его в чате с ботом", 502
    if not resp.ok:
        return "Не удалось получить чек из Telegram — откройте его в чате с ботом", 502
    mime = p.get("receipt_mime") or resp.headers.get("Content-Type") or "application/octet-stream"
    if info["file_path"].endswith(".jpg"):
        mime = "image/jpeg"  # Telegram пересжимает фото в JPEG
    return Response(resp.content, mimetype=mime, headers={"Cache-Control": "private, max-age=3600"})


@app.route("/api/admin/shops/<int:shop_id>/sub", methods=["POST"])
@admin_required
def api_admin_shop_sub(shop_id):
    shop = db.get_shop(shop_id)
    if not shop or shop.get("role") != "shop":
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    data = request.get_json(force=True) or {}
    action = data.get("action")
    if action == "extend":
        try:
            months = int(data.get("months"))
        except (TypeError, ValueError):
            months = 0
        if months not in db.SUB_TERMS:
            return jsonify({"ok": False, "error": "неверный срок"}), 400
        q = db.sub_quote(shop_id)
        amount = next((o["amount"] for o in q["options"] if o["months"] == months), None)
        new_until = db.admin_extend_subscription(shop_id, months, amount)
        return jsonify({"ok": True, "paid_until": new_until})
    if action == "set_until":
        raw = (data.get("date") or "").strip()
        day = None
        if raw:
            for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
                try:
                    day = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass
            if not day:
                return jsonify({"ok": False, "error": "дата в формате ДД.ММ.ГГГГ"}), 400
        db.admin_set_paid_until(shop_id, day)
        return jsonify({"ok": True, "paid_until": day})
    if action == "lifetime":
        amount = _parse_admin_sum(data.get("amount"))
        if amount is False:
            return jsonify({"ok": False, "error": "сумма — только цифры"}), 400
        db.admin_set_lifetime(shop_id, bool(data.get("on")), amount)
        return jsonify({"ok": True})
    if action == "price":
        price = _parse_admin_sum(data.get("price"))
        if price is False:
            return jsonify({"ok": False, "error": "цена — только цифры"}), 400
        db.admin_set_custom_price(shop_id, price)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "неизвестное действие"}), 400


@app.route("/api/admin/branches/<int:branch_id>/sub_paid", methods=["POST"])
@admin_required
def api_admin_branch_sub_paid(branch_id):
    amount = _parse_admin_sum((request.get_json(silent=True) or {}).get("amount"))
    if amount is False:
        return jsonify({"ok": False, "error": "сумма — только цифры"}), 400
    if not db.admin_mark_branch_paid(branch_id, amount):
        return jsonify({"ok": False, "error": "филиал не найден"}), 404
    return jsonify({"ok": True})


SUB_PAGE = r"""<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0A2540">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<title>{{ T.sub_title }} · OilBook</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@800&family=IBM+Plex+Mono:wght@500;600&display=swap">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous">
<style>
:root { --line:#E3E8F0; --text:#0B1F3A; --muted:#5B6B82; --blue:#1D6FE0; --blue-bg:#F0F6FF; --green:#0E6B3E; --green-bg:#E3F4EA;
  --warn:#8A4205; --warn-bg:#FEF0DC; --red:#B3122F; --red-bg:#FCE6EA; --mono:'IBM Plex Mono', ui-monospace, monospace; }
* { box-sizing:border-box; }
body { margin:0; background:#F3F5F9; color:var(--text); font-family:'Plus Jakarta Sans', system-ui, -apple-system, sans-serif; -webkit-tap-highlight-color:transparent; }
.wrap { max-width:520px; margin:0 auto; min-height:100vh; min-height:100dvh; display:flex; flex-direction:column; }
.top { position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:8px; padding:calc(6px + env(safe-area-inset-top, 0px)) 16px 6px; min-height:56px; background:#fff; border-bottom:1px solid var(--line); }
.back { width:44px; height:44px; margin-left:-12px; display:flex; align-items:center; justify-content:center; color:var(--text); text-decoration:none; border:0; background:none; font-size:20px; cursor:pointer; }
.ttl { font-size:18px; font-weight:700; }
.wm { margin-left:auto; font-family:Sora, sans-serif; font-weight:800; font-size:17px; }
.wm b { color:var(--blue); font-weight:800; }
.body { flex:1; padding:16px; display:flex; flex-direction:column; gap:12px; }
.card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; }
.row { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.muted { color:var(--muted); font-size:14px; }
.big { font-family:var(--mono); font-size:24px; font-weight:600; margin:4px 0 2px; }
.chip { font-size:13px; font-weight:700; padding:4px 10px; border-radius:999px; white-space:nowrap; }
.chip.warn { color:var(--warn); background:var(--warn-bg); }
.chip.ok { color:var(--green); background:var(--green-bg); }
.chip.bad { color:#fff; background:var(--red); }
.chip.blue { color:#fff; background:var(--blue); }
.h { font-size:16px; font-weight:700; margin:4px 0 0; }
.opt { position:relative; display:flex; align-items:center; gap:12px; background:#fff; border:2px solid var(--line); border-radius:14px; padding:12px 14px; cursor:pointer; }
.opt input { position:absolute; opacity:0; pointer-events:none; }
.radio { width:20px; height:20px; border-radius:50%; border:2px solid #B8C3D3; flex:none; background:#fff; }
.opt.sel { border-color:var(--blue); background:var(--blue-bg); }
.opt.sel .radio { border:6px solid var(--blue); }
.opt .mid { flex:1; display:flex; flex-direction:column; gap:2px; min-width:0; }
.opt .nm { display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:16px; font-weight:700; }
.disc { font-size:12px; font-weight:700; color:var(--green); background:var(--green-bg); padding:2px 8px; border-radius:999px; }
.best { font-size:12px; font-weight:700; color:#fff; background:var(--blue); padding:2px 8px; border-radius:999px; }
.opt .sub { font-size:13px; color:var(--muted); }
.opt .amt { font-family:var(--mono); font-size:16px; font-weight:600; white-space:nowrap; }
.note { font-size:13px; color:var(--muted); line-height:1.45; }
.foot { position:sticky; bottom:0; background:#fff; border-top:1px solid var(--line); padding:12px 16px calc(16px + env(safe-area-inset-bottom, 0px)); display:flex; flex-direction:column; gap:10px; }
.btn { height:52px; border:0; border-radius:12px; background:var(--blue); color:#fff; font:700 16px 'Plus Jakarta Sans', system-ui, sans-serif; cursor:pointer; width:100%; display:flex; align-items:center; justify-content:center; gap:10px; text-decoration:none; }
.btn:disabled { opacity:.55; cursor:wait; }
.btn.ghost { background:#fff; color:var(--text); border:1.5px solid #D5DDE8; height:48px; font-size:15px; }
.btn.line { background:#fff; color:var(--blue); border:1.5px solid var(--blue); height:48px; font-size:15px; }
.paycard { background:#0B1F3A; color:#fff; border-radius:14px; padding:16px; display:flex; flex-direction:column; gap:8px; }
.paycard .lbl { font-size:12px; color:#B9C6DA; }
.paycard .num { font-family:var(--mono); font-size:20px; font-weight:600; letter-spacing:.5px; }
.cp { width:44px; height:44px; border:0; border-radius:10px; background:rgba(255,255,255,.12); color:#fff; font-size:18px; cursor:pointer; flex:none; }
.cp.light { background:transparent; color:var(--blue); }
.center { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px; text-align:center; padding:24px 20px; }
.ico { width:88px; height:88px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:36px; }
.ico.grey { background:#E6EBF2; color:#3E4F68; }
.ico.green { background:var(--green-bg); color:var(--green); }
h1 { margin:0; font-size:26px; font-weight:800; }
.p { margin:0; font-size:16px; line-height:1.45; color:#3E4F68; }
.warnbox { background:#FFF8EC; border:2px solid #E08A1E; border-radius:14px; padding:14px 16px; display:flex; flex-direction:column; gap:8px; font-size:14px; line-height:1.45; color:#3E4F68; }
.warnbox b { color:var(--text); font-size:15px; }
.redbox { background:var(--red-bg); border-radius:14px; padding:14px 16px; color:#7A0C20; font-size:15px; line-height:1.45; }
.file { display:flex; align-items:center; gap:10px; border:1.5px dashed #9AAAC2; border-radius:12px; padding:14px; cursor:pointer; background:#fff; font-weight:700; color:var(--blue); min-height:52px; }
.file input { position:absolute; opacity:0; width:1px; height:1px; }
.file.has { border-style:solid; border-color:var(--green); color:var(--green); }
.hist .r { display:flex; justify-content:space-between; gap:8px; padding:10px 0; border-top:1px solid #EEF1F6; font-size:14px; }
.hist .r:first-of-type { border-top:0; }
.hist .r.bad { color:var(--red); }
.hist .r > span:last-child { white-space:nowrap; flex:none; }
.err { color:var(--red); font-size:14px; font-weight:700; }
.lo { display:block; text-align:center; padding:12px; color:var(--muted); text-decoration:none; font-size:15px; }
.hidden { display:none !important; }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    {% if not st.blocked %}<a class="back" href="/" aria-label="{{ T.sub_back }}"><i class="fa-solid fa-chevron-left"></i></a>{% endif %}
    <button class="back hidden" id="backStep" type="button" aria-label="{{ T.sub_back }}" onclick="showStep(1)"><i class="fa-solid fa-chevron-left"></i></button>
    <div class="ttl">{{ T.sub_title }}</div>
    <div class="wm"><b>Oil</b>Book</div>
  </div>

{% if mode == 'staff' %}
  {% if st.blocked %}
  <div class="center">
    <div class="ico grey"><i class="fa-solid fa-pause"></i></div>
    <h1>{{ T.sub_staff_title }}</h1>
    <p class="p">{% if st.reason == 'branch_pending' %}{{ T.sub_branch_pending_text }}{% else %}{{ T.sub_staff_text }}{% endif %}</p>
  </div>
  <div class="foot"><a class="btn ghost" href="/logout">{{ T.sub_logout }}</a></div>
  {% else %}
  <div class="body">
    <div class="card">
      {% if st.lifetime %}<b>{{ T.sub_lifetime_title }}</b>
      {% else %}<div class="muted">{{ T.sub_paid_until }}</div><div class="big">{{ paid_until_txt }}</div>{% endif %}
    </div>
  </div>
  {% endif %}
{% else %}
  <div class="body" id="step1">
    {% if st.expired %}<div class="redbox"><b>{{ T.sub_expired_title }}</b><br>{{ expired_txt }}</div>{% endif %}
    {% if pending_txt %}
    <div class="warnbox"><b><i class="fa-solid fa-hourglass-half"></i> {{ T.sub_pending_title }}</b><span>{{ pending_txt }}</span><span class="note">{{ T.sub_pending_hint }}</span></div>
    {% endif %}
    <div class="card">
      <div class="row"><span class="muted">{{ T.sub_paid_until }}</span><span class="chip {{ chip[0] }}">{{ chip[1] }}</span></div>
      {% if st.lifetime %}<div class="big" style="font-size:20px;">{{ T.sub_lifetime_title }}</div><div class="muted">{{ T.sub_lifetime_text }}</div>
      {% else %}<div class="big">{{ paid_until_txt }}</div><div class="muted">{{ net }}</div>{% endif %}
    </div>

    {% if st.lifetime %}
      {% for line in lifetime_branches %}<div class="warnbox"><span>{{ line }}</span></div>{% endfor %}
    {% else %}
      {% if branch_txt %}
      <div class="warnbox">
        <b><i class="fa-solid fa-building"></i> {{ T.sub_branches_title }}</b>
        <span>{{ branch_txt }}</span>
        <label class="opt" data-opt>
          <input type="radio" name="term" value="branches" data-amount="{{ branch_amount_txt }}" data-until="{{ branch_until_txt }}">
          <span class="radio"></span>
          <span class="mid"><span class="nm">{{ T.sub_only_branches }}</span></span>
          <span class="amt">{{ branch_amount_txt }}</span>
        </label>
      </div>
      {% endif %}
      <div class="h">{% if branch_txt %}{{ T.sub_or_extend }}{% else %}{{ T.sub_choose }}{% endif %}</div>
      {% for o in options %}
      <label class="opt" data-opt>
        <input type="radio" name="term" value="{{ o.months }}" data-amount="{{ o.amount_txt }}" data-until="{{ o.until_txt }}"{% if o.best %} checked{% endif %}>
        <span class="radio"></span>
        <span class="mid">
          <span class="nm">{{ o.label }}{% if o.discount %}<span class="disc">−{{ o.discount }}%</span>{% endif %}{% if o.best %}<span class="best">{{ T.sub_best }}</span>{% endif %}</span>
          <span class="sub">{{ o.sub_txt }}</span>
        </span>
        <span class="amt">{{ o.amount_txt }}</span>
      </label>
      {% endfor %}
      <div class="note">{% if branch_txt %}{{ T.sub_incl_branches_note }} {% endif %}{{ T.sub_note }}</div>
    {% endif %}

    {% if history %}
    <div class="card hist">
      <div class="h" style="margin:0 0 6px;">{{ T.sub_history }}</div>
      {% for h in history %}
      <div class="r{% if h.bad %} bad{% endif %}"><span>{{ h.left }}<br><span class="muted">{{ h.sub }}</span></span><span style="font-family:var(--mono);">{{ h.right }}</span></div>
      {% endfor %}
    </div>
    {% endif %}
    {% if support %}<div class="note" style="text-align:center;">{{ support }}</div>{% endif %}
    {% if st.blocked %}<a class="lo" href="/logout">{{ T.sub_logout }}</a>{% endif %}
  </div>

  {% if not st.lifetime %}
  <div class="foot" id="foot1">
    <div class="row muted"><span>{{ T.sub_new_date }}</span><span id="newDate" style="font-family:var(--mono); color:var(--text); font-weight:600;"></span></div>
    <button class="btn" id="payBtn" type="button" onclick="showStep(2)"></button>
  </div>

  <div class="body hidden" id="step2">
    <div class="opt sel" style="cursor:default;">
      <span class="mid"><span class="nm" id="s2What"></span><span class="sub" id="s2Until"></span></span>
      <span class="amt" id="s2Amount"></span>
    </div>
    {% if card_number %}
    <div class="h">{{ T.sub_step1 }}</div>
    <div class="paycard">
      <span class="lbl">{{ T.sub_card }}</span>
      <div class="row"><span class="num" id="cardNum">{{ card_number }}</span>
        <button class="cp" type="button" aria-label="{{ T.sub_copy }}" onclick="copyText(document.getElementById('cardNum').textContent, this)"><i class="fa-regular fa-copy"></i></button></div>
      {% if card_holder %}<span class="lbl" style="font-size:13px;">{{ card_holder }}</span>{% endif %}
    </div>
    <div class="card row" style="padding:6px 8px 6px 16px;">
      <span class="muted">{{ T.sub_amount }}</span>
      <span class="row" style="gap:4px;"><span id="s2Amount2" style="font-family:var(--mono); font-size:17px; font-weight:600;"></span>
        <button class="cp light" type="button" aria-label="{{ T.sub_copy }}" onclick="copyText(document.getElementById('s2Amount2').textContent, this)"><i class="fa-regular fa-copy"></i></button></span>
    </div>
    <div class="h">{{ T.sub_step2 }}</div>
    <div class="note" style="font-size:14px; color:#3E4F68;">{{ T.sub_step2_hint }}</div>
    <label class="file" id="fileBox">
      <input type="file" id="receipt" accept="image/*,application/pdf" onchange="onFile()">
      <i class="fa-solid fa-image"></i><span id="fileName">{{ T.sub_attach }}</span>
    </label>
    <div class="err hidden" id="payErr"></div>
    {% else %}
    <div class="redbox">{{ T.sub_no_card }}</div>
    {% endif %}
  </div>
  {% if card_number %}
  <div class="foot hidden" id="foot2">
    <button class="btn" id="sendBtn" type="button" onclick="sendReceipt()"><i class="fa-solid fa-paper-plane"></i><span>{{ T.sub_send }}</span></button>
  </div>
  {% endif %}

  <div class="center hidden" id="step3">
    <div class="ico green"><i class="fa-solid fa-check"></i></div>
    <h1>{{ T.sub_sent_title }}</h1>
    <p class="p">{{ T.sub_sent_text }}</p>
  </div>
  <div class="foot hidden" id="foot3">
    {% if st.blocked %}<a class="btn ghost" href="/logout">{{ T.sub_logout }}</a>
    {% else %}<a class="btn ghost" href="/">{{ T.sub_back_home }}</a>{% endif %}
  </div>

<script>
(function () {
  const PAY_TPL = {{ T.sub_pay_btn|tojson }};
  const L = { sending: {{ T.sub_sending|tojson }}, send: {{ T.sub_send|tojson }}, need: {{ T.sub_file_needed|tojson }},
    big: {{ T.sub_file_big|tojson }}, err: {{ T.sub_err|tojson }}, copied: {{ T.sub_copied|tojson }},
    attach: {{ T.sub_attach|tojson }}, until: {{ T.sub_new_date|tojson }}, branches: {{ T.sub_only_branches|tojson }} };
  const $ = id => document.getElementById(id);
  function current() { return document.querySelector('input[name=term]:checked'); }
  function refresh() {
    const r = current();
    document.querySelectorAll('[data-opt]').forEach(l => l.classList.toggle('sel', !!r && l.contains(r)));
    if (!r) { $('payBtn').disabled = true; $('payBtn').textContent = PAY_TPL.replace('{sum}', '—'); return; }
    $('payBtn').disabled = false;
    $('payBtn').textContent = PAY_TPL.replace('{sum}', r.dataset.amount);
    $('newDate').textContent = r.dataset.until;
  }
  document.querySelectorAll('input[name=term]').forEach(i => i.addEventListener('change', refresh));
  refresh();

  window.showStep = function (n) {
    const r = current();
    if (n === 2 && !r) return;
    $('step1').classList.toggle('hidden', n !== 1);
    $('foot1').classList.toggle('hidden', n !== 1);
    $('step2').classList.toggle('hidden', n !== 2);
    if ($('foot2')) $('foot2').classList.toggle('hidden', n !== 2);
    $('step3').classList.toggle('hidden', n !== 3);
    $('foot3').classList.toggle('hidden', n !== 3);
    $('backStep').classList.toggle('hidden', n !== 2);
    const homeBack = document.querySelector('a.back');
    if (homeBack) homeBack.classList.toggle('hidden', n === 2);
    if (n === 2) {
      const lbl = r.closest('label').querySelector('.nm');
      $('s2What').textContent = r.value === 'branches' ? L.branches : lbl.childNodes[0].textContent.trim();
      $('s2Until').textContent = L.until + ': ' + r.dataset.until;
      $('s2Amount').textContent = r.dataset.amount;
      if ($('s2Amount2')) $('s2Amount2').textContent = r.dataset.amount;
    }
    window.scrollTo(0, 0);
  };

  window.copyText = function (text, btn) {
    const plain = String(text).replace(/[^0-9]/g, '');
    const done = () => { const old = btn.innerHTML; btn.innerHTML = '<i class="fa-solid fa-check"></i>'; setTimeout(() => { btn.innerHTML = old; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(plain).then(done, () => { prompt(L.copied, plain); });
    } else { prompt(L.copied, plain); }
  };

  window.onFile = function () {
    const f = $('receipt').files[0];
    $('fileName').textContent = f ? f.name : L.attach;
    $('fileBox').classList.toggle('has', !!f);
    $('payErr').classList.add('hidden');
  };

  let busy = false;
  window.sendReceipt = async function () {
    if (busy) return;
    const err = $('payErr');
    const f = $('receipt').files[0];
    const r = current();
    if (!f) { err.textContent = L.need; err.classList.remove('hidden'); return; }
    if (f.size > 10 * 1024 * 1024) { err.textContent = L.big; err.classList.remove('hidden'); return; }
    busy = true;
    const btn = $('sendBtn');
    btn.disabled = true; btn.querySelector('span').textContent = L.sending;
    const fd = new FormData();
    fd.append('choice', r.value);
    fd.append('receipt', f);
    try {
      const res = await fetch('/api/subscription/pay', { method: 'POST', body: fd });
      let data = {};
      try { data = await res.json(); } catch (e) {}
      if (res.ok && data.ok) { showStep(3); return; }
      if (res.status === 401) { location.href = '/login'; return; }
      err.textContent = data.error || L.err; err.classList.remove('hidden');
    } catch (e) {
      err.textContent = L.err; err.classList.remove('hidden');
    } finally {
      busy = false; btn.disabled = false; btn.querySelector('span').textContent = L.send;
    }
  };
})();
</script>
  {% endif %}
{% endif %}
</div>
</body>
</html>
"""


# ---------- Самостоятельная регистрация точки ----------
# Форма /register → подтверждение Telegram и номера в боте (bot.py) →
# заявка администратору с кнопками ✅/❌ → точка с пробным периодом.

_REG_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


def _reg_lang():
    lang = request.args.get("lang") or ""
    return lang if lang in ("ru", "uz") else "ru"


@app.route("/register")
def register_page():
    lang = _reg_lang()
    return render_template_string(
        REGISTER_PAGE, T=i18n.get_texts(lang), lang=lang, other_lang="uz" if lang == "ru" else "ru",
        cities=REG_CITIES[lang], bot_username=BOT_USERNAME or "OilBook")


def _reg_status_payload(req: dict) -> dict:
    out = {"ok": True, "status": req["status"], "token": req["token"]}
    if req["status"] == "new":
        out["code"] = req["code"]
        out["bot_link"] = _client_link(f"reg_{req['code']}")
        out["tg_bound"] = bool(req.get("tg_id"))
        out["phone_ok"] = bool(req.get("tg_phone"))
    return out


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True, silent=True) or {}
    lang = data.get("lang") if data.get("lang") in ("ru", "uz") else "ru"
    T = i18n.get_texts(lang)

    def bad(field, key, code=400):
        return jsonify({"ok": False, "field": field, "error": T[key]}), code

    if not BOT_USERNAME or not BOT_TOKEN:
        return jsonify({"ok": False, "error": T["reg_err_unavailable"]}), 503
    if data.get("website"):  # невидимое поле — его заполняют только спам-боты
        return jsonify({"ok": False, "error": T["reg_err_network"]}), 400

    def s(k, n):
        return re.sub(r"\s+", " ", str(data.get(k) or "")).strip()[:n]

    shop_name, owner_name, city = s("shop_name", 80), s("owner_name", 60), s("city", 40)
    address, username = s("address", 150), s("username", 30)
    password, password2 = str(data.get("password") or ""), str(data.get("password2") or "")
    digits = "".join(ch for ch in str(data.get("phone") or "") if ch.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    if len(shop_name) < 2:
        return bad("shop_name", "reg_err_shop_name")
    if len(owner_name) < 2:
        return bad("owner_name", "reg_err_owner_name")
    if len(city) < 2:
        return bad("city", "reg_err_city")
    if len(digits) != 12 or not digits.startswith("998"):
        return bad("phone", "reg_err_phone")
    if len(address) < 3:
        return bad("address", "reg_err_address")
    if not _REG_USERNAME_RE.match(username):
        return bad("username", "reg_err_username")
    if len(password) < 6 or len(password) > 100:
        return bad("password", "reg_err_password")
    if password != password2:
        return bad("password2", "reg_err_password2")
    ip = _client_ip()
    if db.registrations_from_ip_today(ip) >= db.REG_MAX_PER_IP_DAY:
        return jsonify({"ok": False, "error": T["reg_err_limit"]}), 429
    if db.registration_login_taken(username):
        return bad("username", "reg_err_username_taken")
    phone = f"+{digits[:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    req = db.create_registration(shop_name, owner_name, city, phone, address, username, password, lang, ip)
    return jsonify(_reg_status_payload(req))


@app.route("/api/register/status")
def api_register_status():
    req = db.get_registration_by_token((request.args.get("t") or "").strip())
    if not req:
        return jsonify({"ok": False, "status": "expired"}), 404
    return jsonify(_reg_status_payload(req))


def _reg_admin_text(req: dict) -> str:
    tg = f"@{req['tg_username']}" if req.get("tg_username") else "без @username"
    same = ""
    if req.get("tg_phone") and req.get("phone"):
        same = (" ✅ совпадает" if db._phone_digits(req["tg_phone"]) == db._phone_digits(req["phone"])
                else " ⚠️ отличается от формы")
    return "\n".join([
        f"🆕 Заявка на регистрацию №{req['id']}",
        "",
        f"Точка: {req['shop_name']}",
        f"Владелец: {req.get('owner_name') or '—'}",
        f"Город: {req.get('city') or '—'}",
        f"Адрес: {req.get('address') or '—'}",
        f"Телефон в форме: {req.get('phone') or '—'}",
        f"Телефон Telegram: {req.get('tg_phone') or '—'}{same}",
        f"Telegram: {tg} · {req.get('tg_name') or ''} · ID {req.get('tg_id')}",
        f"Локация: {_reg_map_link(req)}",
        f"Логин: {req['username']}",
        f"Язык: {(req.get('language') or 'ru').upper()}",
    ])


def _reg_map_link(req: dict) -> str:
    if req.get("lat") is None or req.get("lon") is None:
        return "—"
    link = f"https://maps.google.com/?q={req['lat']:.6f},{req['lon']:.6f}"
    return link if db.reg_location_in_uz(req["lat"], req["lon"]) else link + " ⚠️ вне Узбекистана"


def reg_notify_admin(req: dict):
    """Заявка подтверждена в боте — администратору платформы с кнопками."""
    if not ADMIN_TELEGRAM_ID:
        return None
    markup = json.dumps({"inline_keyboard": [[
        {"text": f"✅ Одобрить ({db.REG_TRIAL_DAYS} дн. бесплатно)", "callback_data": f"reg:ok:{req['id']}"},
        {"text": "❌ Отклонить", "callback_data": f"reg:no:{req['id']}"},
    ]]})
    res = _tg_api("sendMessage", {"chat_id": ADMIN_TELEGRAM_ID, "text": _reg_admin_text(req), "reply_markup": markup,
                                  "disable_web_page_preview": "true"})
    if res and res.get("message_id"):
        db.set_registration_admin_msg(req["id"], res["message_id"])
        if req.get("lat") is not None and req.get("lon") is not None:
            # метка на карте прямо под заявкой — видно место без перехода по ссылке
            _tg_api("sendLocation", {"chat_id": ADMIN_TELEGRAM_ID, "latitude": req["lat"], "longitude": req["lon"],
                                     "reply_to_message_id": res["message_id"]})
    return res


def reg_decide(req_id: int, approve: bool) -> dict:
    """Единое решение по заявке — и из админки, и из кнопок в Telegram."""
    r = db.approve_registration(req_id) if approve else db.reject_registration(req_id)
    req = r.get("req")
    if not r["ok"]:
        return r
    shop = r.get("shop")
    if req.get("admin_msg_id") and ADMIN_TELEGRAM_ID:
        mark = (f"✅ Одобрено — точка создана, пробный период до {_fmt_day(shop.get('paid_until'))}"
                if approve else "❌ Отклонено")
        _tg_api("editMessageText", {"chat_id": ADMIN_TELEGRAM_ID, "message_id": req["admin_msg_id"],
                                    "text": _reg_admin_text(req) + "\n\n" + mark, "disable_web_page_preview": "true"})
    if req.get("tg_id"):
        lang = req.get("language") or "ru"
        if approve:
            link = (PUBLIC_URL.rstrip("/") + "/login") if PUBLIC_URL else "/login"
            if lang == "uz":
                link += "?lang=uz"
            text = i18n.t("reg_bot_approved", lang, shop=req["shop_name"], date=_fmt_day(shop.get("paid_until")),
                          login=req["username"], link=link)
        else:
            text = i18n.t("reg_bot_rejected", lang, shop=req["shop_name"])
        # убираем кнопку «Поделиться номером», если она ещё висит
        _tg_api("sendMessage", {"chat_id": req["tg_id"], "text": text,
                                "reply_markup": json.dumps({"remove_keyboard": True})})
    return r


@app.route("/api/admin/registrations")
@admin_required
def api_admin_registrations():
    return jsonify({"ok": True, **db.list_registrations()})


@app.route("/api/admin/registrations/<int:req_id>/<action>", methods=["POST"])
@admin_required
def api_admin_registration_decide(req_id, action):
    if action not in ("approve", "reject"):
        return jsonify({"ok": False, "error": "неизвестное действие"}), 400
    r = reg_decide(req_id, action == "approve")
    if not r["ok"]:
        err = {"done": "заявка уже обработана",
               "username_taken": "логин уже занят другой точкой — отклоните заявку"}.get(r.get("error"), "ошибка")
        return jsonify({"ok": False, "error": err}), 400
    out = {"ok": True}
    if r.get("shop"):
        out.update(shop_id=r["shop"]["id"], paid_until=r["shop"].get("paid_until"))
    return jsonify(out)


# ---------- Сотрудники: владелец точки управляет сам ----------
# Главная точка — своими, каждый филиал — своими (g.shop_id — сама точка).
# Сотрудник сюда не попадает (@employee_blocked). Админ платформы — через /api/admin.

_STAFF_LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


@app.route("/api/staff")
@login_required
@employee_blocked
def api_staff_list():
    return jsonify({"ok": True, "employees": db.list_shop_employees(g.shop_id)})


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
    if not db.delete_shop_employee(employee_id, g.shop_id):
        return jsonify({"ok": False, "error": g.T["staff_err_notfound"]}), 404
    return jsonify({"ok": True})


@app.route("/api/admin/employees/<int:employee_id>/active", methods=["POST"])
@admin_required
def api_admin_employee_active(employee_id):
    data = request.get_json(force=True, silent=True) or {}
    if not db.set_shop_employee_active(employee_id, data.get("shop_id"), bool(data.get("active"))):
        return jsonify({"ok": False, "error": "сотрудник не найден"}), 404
    return jsonify({"ok": True})


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


if __name__ == "__main__":
    run_webapp()
