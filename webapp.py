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
from flask import Flask, request, jsonify, render_template_string, Response, session, redirect, url_for, g

import database as db
import i18n

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

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
    backup_path = f"/tmp/oilbot_backup_manual_{today_str}.db"
    try:
        src = sqlite3.connect(db.DB_PATH)
        dst = sqlite3.connect(backup_path)
        src.backup(dst)
        dst.close()
        src.close()
        size_mb = os.path.getsize(backup_path) / 1024 / 1024
        ok, err = _send_telegram_document(
            chat_id, backup_path, f"oilbot_backup_{today_str}.db",
            caption=f"📦 Резервная копия базы данных за {today_str} ({size_mb:.1f} МБ){caption_note}",
        )
        return ok, err, size_mb
    finally:
        if os.path.exists(backup_path):
            os.remove(backup_path)


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
    with open(same_dir_tmp, "wb") as f:
        f.write(uploaded_bytes)
    valid, err = _validate_sqlite_backup(same_dir_tmp)
    if not valid:
        os.remove(same_dir_tmp)
        return False, err
    if notify_chat_id:
        _create_and_send_backup(notify_chat_id)  # снимок ТЕКУЩЕГО состояния перед заменой, для отката
    os.replace(same_dir_tmp, db.DB_PATH)
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


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") not in ("shop", "branch") or not session.get("shop_id"):
            return redirect(url_for("login_page"))
        shop = db.get_shop(session["shop_id"])
        if not shop or not shop["is_active"]:
            session.clear()
            return redirect(url_for("login_page"))
        g.shop_id = session["shop_id"]
        g.lang = shop.get("language") or "ru"
        g.T = i18n.get_texts(g.lang)
        g.is_employee = bool(session.get("is_employee"))
        g.is_branch = shop.get("role") == "branch"
        g.parent_shop_id = shop.get("parent_shop_id")
        return view(*args, **kwargs)
    return wrapped


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
            return redirect(url_for("login_page"))
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
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="MoyBook">
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
  label { display:block; font-size:13px; color:#9a9a9a; margin-bottom:4px; }
  input { width:100%; padding:11px; border-radius:8px; border:1px solid #2a2e37; background:#11141a; color:#fff; font-size:15px; margin-bottom:14px; }
  button { width:100%; padding:12px; border:none; border-radius:10px; background:#3a86ff; color:#fff; font-size:16px; font-weight:600; cursor:pointer; }
  .error { background:#3a1e1e; color:#dc6f6f; padding:10px; border-radius:8px; margin-bottom:14px; font-size:14px; }
  .ok-msg { background:#1e3a24; color:#6fdc86; padding:10px; border-radius:8px; margin-bottom:14px; font-size:14px; }
  .lang-link { display:block; text-align:center; margin-top:14px; color:#9a9a9a; font-size:12px; text-decoration:none; }
  .forgot-link { display:block; text-align:center; margin-top:12px; color:#3a86ff; font-size:13px; background:none; border:none; cursor:pointer; padding:0; }
  .hint { font-size:12px; color:#7a7a7a; margin:-8px 0 14px; }
</style>
</head>
<body>
  <form class="box" method="POST" id="loginForm">
    <h1>🔧 {{ T.login_title }}</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <input type="hidden" name="_lang" value="{{ lang }}">
    <label>{{ T.login_username }}</label>
    <input name="username" autofocus required>
    <label>{{ T.login_password }}</label>
    <input name="password" type="password" required>
    <button type="submit">{{ T.login_button }}</button>
    <button type="button" class="forgot-link" onclick="showForgot()">{{ T.forgot_password_link }}</button>
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


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    lang = request.form.get("_lang") or request.args.get("lang")
    if lang not in ("ru", "uz"):
        lang = "ru"
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        shop = db.authenticate_shop(username, password)
        if shop:
            session.clear()
            session["shop_id"] = shop["id"]
            session["role"] = shop["role"]
            session["username"] = shop["username"]
            session["shop_name"] = shop.get("shop_name") or shop["username"]
            session["is_employee"] = False
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
            session.permanent = True
            return redirect(url_for("index"))
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


PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{{ shop_name }} — MoyBook</title>
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="MoyBook">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
</script>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
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
    background: rgba(255,255,255,.94); backdrop-filter: blur(10px); border:2px solid #DBEAFE; border-radius: 22px; padding: 16px; margin-bottom: 12px;
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
      <div class="logo-sub">MoyBook{% if is_employee %} · <span class="role-tag">{{ T.role_employee }}</span>{% elif is_branch %} · <span class="role-tag">{{ T.role_branch }}</span>{% endif %}</div>
    </div>
  </div>
  <nav class="side-list">
    <div class="side-item side-add active" id="tab-add" data-tab="add" onclick="showTab('add')"><i class="fa-solid fa-plus"></i><span>{{ T.tab_add }}</span></div>
    <div class="side-item" id="tab-table" data-tab="table" onclick="showTab('table')"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
    {% if not is_employee %}<div class="side-item" id="tab-stats" data-tab="stats" onclick="showTab('stats')"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>{% endif %}
    {% if warehouse_enabled and not is_employee %}<div class="side-item" id="tab-warehouse" data-tab="warehouse" onclick="showTab('warehouse')"><i class="fa-solid fa-boxes-stacked"></i><span>{{ T.tab_warehouse }}</span></div>{% endif %}
    <div class="side-item" id="tab-debts" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
    {% if not is_employee %}<div class="side-item" id="tab-expenses" data-tab="expenses" onclick="showTab('expenses')"><i class="fa-solid fa-receipt"></i><span>{{ T.tab_expenses }}</span></div>{% endif %}
    <div class="side-item" id="tab-broadcast" data-tab="broadcast" onclick="showTab('broadcast')"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
    {% if sms_enabled %}<div class="side-item" id="tab-sms" data-tab="sms" onclick="showTab('sms')"><i class="fa-solid fa-comment-sms"></i><span>{{ T.tab_sms }}</span></div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-export" data-tab="export" onclick="showTab('export')"><i class="fa-solid fa-file-arrow-down"></i><span>{{ T.tab_export }}</span></div>{% endif %}
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
      <div class="more-item" data-tab="table" data-more-slot="table" onclick="showTab('table'); closeMore();"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
      {% if not is_employee %}<div class="more-item" data-tab="stats" data-more-slot="stats" onclick="showTab('stats'); closeMore();"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>{% endif %}
      {% if warehouse_enabled and not is_employee %}<div class="more-item" data-tab="warehouse" data-more-slot="warehouse" onclick="showTab('warehouse'); closeMore();"><i class="fa-solid fa-boxes-stacked"></i><span>{{ T.tab_warehouse }}</span></div>{% endif %}
      <div class="more-item" data-tab="debts" data-more-slot="debts" onclick="showTab('debts'); closeMore();"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
      {% if not is_employee %}<div class="more-item" data-tab="expenses" data-more-slot="expenses" onclick="showTab('expenses'); closeMore();"><i class="fa-solid fa-receipt"></i><span>{{ T.tab_expenses }}</span></div>{% endif %}
      <div class="more-item" data-tab="broadcast" data-more-slot="broadcast" onclick="showTab('broadcast'); closeMore();"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
      {% if sms_enabled %}<div class="more-item" data-tab="sms" data-more-slot="sms" onclick="showTab('sms'); closeMore();"><i class="fa-solid fa-comment-sms"></i><span>{{ T.tab_sms }}</span></div>{% endif %}
      {% if not is_employee %}<div class="more-item" data-tab="export" data-more-slot="export" onclick="showTab('export'); closeMore();"><i class="fa-solid fa-file-arrow-down"></i><span>{{ T.tab_export }}</span></div>{% endif %}
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
        <div class="logo-sub">MoyBook{% if is_employee %} · <span class="role-tag">{{ T.role_employee }}</span>{% elif is_branch %} · <span class="role-tag">{{ T.role_branch }}</span>{% endif %}</div>
      </div>
    </div>
    <button class="lang-btn" onclick="switchLanguage()">{{ T.lang_switch_short }}</button>
  </div>

  <div id="msg"></div>

  <div id="view-add" class="card">
    <div class="card-header"><span class="dot"></span><h3>{{ T.tab_add }}</h3></div>
    <div class="field">
      <label><i class="fa-solid fa-id-card"></i>{{ T.field_plate }}</label>
      <div class="plate-wrap">
        <span class="plate-chip">UZ</span>
        <input id="plate" placeholder="01A123BC" oninput="onPlateInput()" onblur="onPlateBlur()" autocomplete="off">
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
      <input id="owner_phone" placeholder="+998 90 123 45 67">
      <div class="hint-text">{{ T.hint_owner_phone }}</div>
    </div>
    <div class="row2">
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
    <div class="row2">
      <div class="field">
        <label>{{ T.field_mileage }}</label>
        <input id="mileage" type="number" placeholder="45000" oninput="checkMileageVsDue()">
        <div id="mileageCompare"></div>
      </div>
      <div class="field">
        <label>{{ T.field_next_mileage }}</label>
        <input id="next_mileage" type="number" placeholder="55000">
      </div>
    </div>
    <div class="field">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_fluids }}</label>
    </div>
    <div id="fluidsList"></div>

    <div class="field" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_filters }}</label>
    </div>
    <div id="filtersList"></div>

    <div class="field" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_other }}</label>
    </div>
    <div class="row2">
      <div class="field">
        <label>{{ T.field_other_name }}</label>
        <input id="other_name" placeholder="{{ T.field_other_name_ph }}">
      </div>
      <div class="field">
        <label>{{ T.field_price }}</label>
        <input id="other_price" type="number" placeholder="0" oninput="updateTotal()">
      </div>
    </div>

    {% if warehouse_enabled %}
    <div class="field" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.wh_other_stock_title }}</label>
    </div>
    <div id="otherStockRows"></div>
    <button type="button" class="submit" style="padding:8px; background:var(--border);" onclick="addOtherStockRow('other')">{{ T.wh_add_row }}</button>
    {% endif %}

    <div class="field" style="margin-top:14px; padding:12px; background:var(--field-bg); border-radius:10px;">
      <label style="font-size:15px;">{{ T.field_total }}</label>
      <div id="totalCost" style="font-size:24px; font-weight:600; color:var(--btn); font-family:var(--font-mono);">0</div>
    </div>

    <div class="field" style="margin-top:14px;">
      <label>{{ T.payment_split_label }}</label>
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
      <div class="checkbox-row" style="margin-top:10px; cursor:pointer;" onclick="document.getElementById('debt_enabled').click()">
        <input type="checkbox" id="debt_enabled" onchange="toggleDebtSection()" onclick="event.stopPropagation()">
        <label style="margin:0; cursor:pointer;">{{ T.debt_enable_label }}</label>
      </div>
      <div id="debtFields" style="display:none; margin-top:10px; padding:12px; background:var(--card); border:1.5px dashed var(--border); border-radius:10px;">
        <div class="field">
          <label style="font-size:11px;">{{ T.debt_remaining_label }}</label>
          <div id="debtRemaining" style="font-size:18px; font-weight:700; color:var(--btn); font-family:var(--font-mono);">0</div>
        </div>
        <div class="row2">
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
    </div>

    <div class="field" style="margin-top:14px;">
      <label>{{ T.field_interval }}</label>
      <div style="display:flex; gap:8px;">
        <input id="interval_value" type="number" placeholder="3" value="3" style="flex:1;">
        <select id="interval_unit" style="flex:1;">
          <option value="months">{{ T.unit_months }}</option>
          <option value="days">{{ T.unit_days }}</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label>{{ T.field_notes }}</label>
      <textarea id="notes" rows="2" placeholder="{{ T.notes_ph }}"></textarea>
    </div>
    <button class="submit" onclick="submitCar()">{{ T.btn_save }}</button>
  </div>

  <div id="view-table" style="display:none;">
    <div id="baseClientCount" style="font-size:13px; color:var(--hint); margin-bottom:8px;"></div>
    <div style="position:relative;">
      <input class="search" id="search" placeholder="{{ T.search_ph }}" oninput="renderTable(); toggleSearchClearBtn();" style="padding-right:40px;">
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
    {% if not is_branch %}
    <div class="card" id="usdRateCardExp" style="margin-bottom:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.usd_rate_title }}</label>
      <div class="row2">
        <div class="field">
          <label>{{ T.usd_rate_label }}</label>
          <input id="usd_rate_input_exp" type="number" step="0.01" placeholder="12700" value="{{ usd_rate or '' }}">
        </div>
      </div>
      <button class="submit" onclick="saveUsdRate('usd_rate_input_exp', 'usdRateSaved_exp')">{{ T.usd_rate_save }}</button>
      <div id="usdRateSaved_exp" style="display:none; color:#1B8A5A; font-size:13px; margin-top:8px;">✓ {{ T.usd_rate_saved }}</div>
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

  {% if not is_employee %}
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
      <input id="eskiz_email" value="{{ eskiz_email }}" placeholder="you@example.com">
    </div>
    <div class="field">
      <label>{{ T.sms_password }}</label>
      <input id="eskiz_password" type="password" placeholder="{{ T.sms_password_ph }}">
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
        </div>
        <div class="brand-chips" id="whCatChips"></div>
        <div id="whCards"></div>
        <button class="wh-tbtn wh-tbtn-wide" id="whPurchaseBtn" onclick="openPurchaseList()"><i class="fa-solid fa-clipboard-list"></i> <span>{{ T.whs_purchase_list }}</span></button>
      </div>

      <div class="card" style="margin-top:14px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_movements }}</label>
        <div id="restockHistory"></div>
      </div>

      {% if not is_branch %}
      <div class="card" id="usdRateCard" style="margin-top:14px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.usd_rate_title }}</label>
        <div class="row2">
          <div class="field">
            <label>{{ T.usd_rate_label }}</label>
            <input id="usd_rate_input" type="number" step="0.01" placeholder="12700" value="{{ usd_rate or '' }}">
          </div>
        </div>
        <button class="submit" onclick="saveUsdRate()">{{ T.usd_rate_save }}</button>
        <div id="usdRateSaved" style="display:none; color:#1B8A5A; font-size:13px; margin-top:8px;">✓ {{ T.usd_rate_saved }}</div>
        <p class="hint-text" style="margin-top:10px; margin-bottom:0;">{{ T.usd_rate_hint }}</p>
      </div>
      {% endif %}


    </div>

    <div id="whNetworkView" style="display:none;">
      <div class="card">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.whn_title }}</label>
        <div class="hint-text" style="margin-bottom:12px;">{{ T.whn_hint }}</div>
        <button class="wh-tbtn wh-tbtn-primary wh-tbtn-wide" onclick="openTransferModal({})" style="margin:0 0 12px;"><i class="fa-solid fa-right-left"></i> {{ T.whn_transfer }}</button>
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
              <input id="wh_new_sell_price" type="number" placeholder="45000">
            </div>
            <div class="field" {% if is_branch %}style="display:none;"{% endif %}>
              <label>{{ T.wh_purchase_price }}</label>
              <input id="wh_new_purchase_price" type="number" placeholder="30000" oninput="onSumFieldEdited('wh_new_purchase_price', 'wh_new_purchase_usd')">
            </div>
          </div>
          <div class="field" {% if is_branch %}style="display:none;"{% endif %}>
            <label>{{ T.usd_price_label }}</label>
            <input id="wh_new_purchase_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('wh_new_purchase_usd', 'wh_new_purchase_price')">
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
          <button class="close-btn" onclick="closeWhModal('purchaseListModal')">{{ T.modal_close }}</button>
        </div>
      </div>
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
              <input id="ep_sell" type="number" min="0">
            </div>
            <div class="field" id="ep_buy_wrap">
              <label>{{ T.wh_purchase_price }}</label>
              <input id="ep_buy" type="number" min="0" oninput="onSumFieldEdited('ep_buy', 'ep_buy_usd')">
            </div>
          </div>
          <div class="field" id="ep_usd_wrap">
            <label>{{ T.usd_price_label }}</label>
            <input id="ep_buy_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('ep_buy_usd', 'ep_buy')">
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
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

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

function showTab(t) {
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
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  if (t === 'stats') loadStats();
  if (t === 'warehouse') loadWarehouse();
}

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
    const sheet = document.getElementById('moreSheet');
    const moreBadge = document.getElementById('moreBadge');
    if (sheet && moreBadge) {
      const debtsInMore = !sheet.dataset.bar.split(',').includes('debts');
      moreBadge.textContent = overdue;
      moreBadge.classList.toggle('show', debtsInMore && overdue > 0);
    }
  } catch (e) {}
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
  const items = ctx.products
    .filter(p => p.reorder_qty > 0 || p.status === 'out')
    .sort((a, b) => (a.days_left ?? -1) - (b.days_left ?? -1));
  document.getElementById('purchaseListBody').innerHTML = items.length ? items.map(p => `
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

// ---- склад выбранного филиала (главный) ----
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
  document.getElementById('ep_buy_wrap').style.display = canBuy ? '' : 'none';
  document.getElementById('ep_usd_wrap').style.display = canBuy && key === 'own' ? '' : 'none';
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
    USD_RATE = data.rate;
    // синхронизируем оба виджета курса, если на странице есть второй (Расходы)
    ['usd_rate_input', 'usd_rate_input_exp'].forEach(id => {
      const el = document.getElementById(id);
      if (el && id !== inputId) el.value = data.rate ?? '';
    });
    const saved = document.getElementById(savedId);
    saved.style.display = 'block';
    setTimeout(() => { saved.style.display = 'none'; }, 1500);
  } else {
    showMsg(T.usd_rate_error || data.error, false);
  }
}

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
    const what = m.type === 'restock' ? T.whs_mv_restock
      : m.type === 'adjust' ? `${T.whe_mv_adjust}: ${whQty(m.old_qty)} → ${whQty(m.new_qty)}${m.reason ? ' · ' + escapeHtml(m.reason) : ''}`
      : (m.type === 'transfer_in' ? `${T.whs_mv_from} ${escapeHtml(m.other_shop || '')}` : `${T.whs_mv_to} ${escapeHtml(m.other_shop || '')}`);
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
  const isNegative = np.net_profit < 0;
  return `
    <div class="dash-summary-grid">
      <div class="dash-summary-box">
        <div class="dsb-num">${np.oil_profit.toLocaleString('ru-RU')} ${T.currency}</div>
        <div class="dsb-label">${T.dash_oil_profit_label}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num warn">${np.expenses_total.toLocaleString('ru-RU')} ${T.currency}</div>
        <div class="dsb-label">${T.dash_expenses_label}</div>
      </div>
    </div>
    <div style="text-align:center; margin-top:12px; padding-top:12px; border-top:1px dashed #86EFAC;">
      <div style="font-size:24px; font-weight:700; font-family:var(--font-mono); color:${isNegative ? '#B3241C' : '#15803D'};">${np.net_profit.toLocaleString('ru-RU')} ${T.currency}</div>
      <div style="font-size:11px; color:var(--hint); margin-top:2px;">${T.dash_net_profit_label}</div>
    </div>`;
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
    const scopeQs = bw(p).scope ? `&scope=${bw(p).scope}` : '';
    const res = await fetch(`/api/stats/brands?from=${iso(from)}&to=${iso(to)}${scopeQs}`);
    bw(p).data = await res.json();
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
    data = await (await fetch(`/api/network/overview?scope=${encodeURIComponent(NET.scope)}`)).json();
  } catch (e) { return; }
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
    data = await (await fetch(`/api/network/compare?period=${NET.period}`)).json();
  } catch (e) { return; }
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
          <td class="${cls(r.profit, best.profit)}">${fmtNum(r.profit)}</td>
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
      <div class="dash-summary-grid">
        <div class="dash-summary-box">
          <div class="dsb-num">${data.profit.toLocaleString('ru-RU')} ${T.currency}</div>
          <div class="dsb-label">${T.dash_oil_profit_label}</div>
        </div>
        <div class="dash-summary-box">
          <div class="dsb-num warn">${data.expenses.toLocaleString('ru-RU')} ${T.currency}</div>
          <div class="dsb-label">${T.dash_expenses_label}</div>
        </div>
      </div>
      <div style="text-align:center; margin-top:12px; padding-top:12px; border-top:1px dashed #86EFAC;">
        <div style="font-size:22px; font-weight:700; font-family:var(--font-mono); color:${data.net_profit < 0 ? '#B3241C' : '#15803D'};">${data.net_profit.toLocaleString('ru-RU')} ${T.currency}</div>
        <div style="font-size:11px; color:var(--hint); margin-top:2px;">${T.dash_net_profit_label}</div>
      </div>
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

function renderItemLists() {
  document.getElementById('fluidsList').innerHTML = FLUID_KEYS.map((key, i) => `
    <div class="item-row">
      <span class="item-name">${T[key]}</span>
      ${brandFieldHtml(key, `fluid_brand_${i}`, `onFluidProductPicked(${i})`)}
      <input id="fluid_price_${i}" type="number" placeholder="${T.price_per_liter_ph}" oninput="updateTotal()">
      <input id="fluid_liters_${i}" type="number" step="0.1" placeholder="${T.liters_ph}" oninput="updateTotal()">
    </div>
  `).join('');
  document.getElementById('filtersList').innerHTML = FILTER_KEYS.map((key, i) => {
    const prods = productsForCategory(key);
    const brandField = prods.length ? brandFieldHtml(key, `filter_brand_${i}`, `onFilterProductPicked(${i})`) : '';
    return `
    <div class="item-row">
      <span class="item-name" style="flex:${prods.length ? '1.3' : '2.3'};">${T[key]}</span>
      ${brandField}
      <input id="filter_price_${i}" type="number" placeholder="${T.price_ph}" oninput="updateTotal()">
    </div>
  `;
  }).join('');
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
    payCash.value = total || '';
    payCard.value = '';
  }
  updateDebtRemaining();
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

function resetItemInputs() {
  FLUID_KEYS.forEach((_, i) => {
    document.getElementById(`fluid_brand_${i}`).value = '';
    document.getElementById(`fluid_price_${i}`).value = '';
    document.getElementById(`fluid_liters_${i}`).value = '';
  });
  FILTER_KEYS.forEach((_, i) => document.getElementById(`filter_price_${i}`).value = '');
  document.getElementById('other_name').value = '';
  document.getElementById('other_price').value = '';
  document.getElementById('knownClientPanel').innerHTML = '';
  otherStockRows = [];
  renderOtherStockRows('other');
  updateTotal();
}

let plateSuggestLoading = false;

async function ensureCarsCacheLoaded() {
  if (carsCache.length || plateSuggestLoading) return;
  plateSuggestLoading = true;
  try {
    const res = await fetch('/api/cars');
    carsCache = await res.json();
  } catch (e) { /* тихо — просто не будет подсказок в этот раз */ }
  plateSuggestLoading = false;
}

async function onPlateInput() {
  const val = document.getElementById('plate').value.trim().toUpperCase();
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

async function lookupPlate() {
  const plate = document.getElementById('plate').value.trim();
  const panel = document.getElementById('knownClientPanel');
  if (!plate) { panel.innerHTML = ''; lastKnownNextMileage = null; checkMileageVsDue(); return; }
  try {
    const res = await fetch('/api/history/' + encodeURIComponent(plate));
    const data = await res.json();

    const crossHtml = renderCrossNetworkHistory(data.cross_history);

    if (!data.car) {
      panel.innerHTML = crossHtml;
      lastKnownNextMileage = null;
      checkMileageVsDue();
      return;
    }

    document.getElementById('owner_name').value = data.car.owner_name || '';
    document.getElementById('owner_phone').value = data.car.owner_phone || '';
    if (data.car.car_brand) document.getElementById('car_brand').value = data.car.car_brand;
    document.getElementById('car_model').value = data.car.car_model || '';

    const name = data.car.owner_name || T.kc_no_name;
    const initials = name.trim().split(/\\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
    const carLine = [data.car.car_brand, data.car.car_model].filter(Boolean).join(' ');
    const metaParts = [data.car.owner_phone, carLine].filter(Boolean);

    const last = data.history[0];
    const visitCount = data.history.length;
    lastKnownNextMileage = last ? last.next_mileage : null;
    let lastItemsHtml = '';
    if (last && last.items_json) {
      try {
        const items = JSON.parse(last.items_json);
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
      </div>
    ` : `<div class="kc-last-visit"><span style="color:var(--hint); font-size:13px;">${T.kc_no_history}</span></div>`;

    panel.innerHTML = `
      <div class="known-client">
        <div class="kc-header"><i class="fa-solid fa-circle-check"></i><span>${T.kc_found_title}</span></div>
        <div class="kc-body">
          <div class="kc-person">
            <div class="kc-avatar">${escapeHtml(initials)}</div>
            <div>
              <div class="kc-name">${escapeHtml(name)}</div>
              <div class="kc-meta">${escapeHtml(metaParts.join(' · '))}</div>
            </div>
          </div>
          <div class="kc-history-label">${T.kc_history_label}</div>
          ${lastVisitHtml}
          <button type="button" class="kc-action-btn" onclick="focusNextEntry()"><i class="fa-solid fa-plus"></i>${T.kc_add_service_btn}</button>
          <div class="kc-action-hint">${T.kc_add_service_hint}</div>
        </div>
      </div>
    ` + crossHtml;
  } catch (e) {
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
  const res = await fetch('/api/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(`✅ ${T.msg_saved} ${data.next_date || '—'}.`, true);
    ['plate','owner_name','owner_phone','car_model','mileage','next_mileage','notes'].forEach(id => document.getElementById(id).value = '');
    resetItemInputs();
    document.getElementById('interval_value').value = 3;
    document.getElementById('interval_unit').value = 'months';
    paymentSplitTouched = false;
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

async function loadCars() {
  const res = await fetch('/api/cars');
  carsCache = await res.json();
  renderTable();
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
  renderTable();
}

function renderTable() {
  const q = (document.getElementById('search').value || '').toLowerCase();
  if (openHistoryRow !== null) {
    const panel = document.getElementById('clientCardPanel');
    panel.style.display = 'none';
    panel.innerHTML = '';
    openHistoryRow = null;
  }
  const countEl = document.getElementById('baseClientCount');
  if (countEl) {
    const uniqueClients = new Set(carsCache.map(c => c.client_id)).size;
    countEl.textContent = `${T.base_total_clients} ${uniqueClients} · ${T.base_total_cars} ${carsCache.length}`;
  }
  const rows = carsCache.filter(c =>
    (c.plate_number || '').toLowerCase().includes(q) || (c.owner_name || '').toLowerCase().includes(q)
  );
  document.getElementById('table-body').innerHTML = rows.length ? rows.map((c, i) => `
    <div class="car-card" onclick="toggleHistory(${escapeHtml(JSON.stringify(c.plate_number))})">
      <div class="cc-top">
        <span class="cc-plate">${escapeHtml(c.plate_number)}</span>
        ${c.telegram_id
            ? `<span class="badge linked cc-linkbtn">${T.badge_linked}</span>`
            : `<button class="badge unlinked cc-linkbtn" onclick="event.stopPropagation(); openModal(${escapeHtml(JSON.stringify(c.plate_number))}, ${escapeHtml(JSON.stringify(c.client_link || ''))}, ${escapeHtml(JSON.stringify(c.owner_phone || ''))})">${T.badge_unlinked_btn}</button>`}
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
  `).join('') : `<div class="hint-text" style="text-align:center; padding:20px;">${T.table_empty}</div>`;
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
</script>
</body>
</html>
"""

PAGE = PAGE + MODAL_AND_SCRIPT


@app.route("/")
@login_required
def index():
    import json as _json
    shop = db.get_shop(g.shop_id)
    return render_template_string(
        PAGE, brands=CAR_BRANDS, service_types=SERVICE_TYPES,
        shop_name=session.get("shop_name") or "Замена масла",
        T=g.T, lang=g.lang, t_json=_json.dumps(g.T, ensure_ascii=False),
        sms_enabled=bool(shop.get("sms_enabled")) if shop else False,
        eskiz_email=(shop.get("eskiz_email") or "") if shop else "",
        warehouse_enabled=bool(shop.get("warehouse_enabled")) if shop else False,
        is_employee=g.is_employee,
        is_branch=g.is_branch,
        usd_rate=shop.get("usd_rate") if shop else None,
    )


@app.route("/api/set_language", methods=["POST"])
@login_required
def api_set_language():
    data = request.get_json(force=True)
    lang = data.get("language")
    if lang not in ("ru", "uz"):
        return jsonify({"ok": False, "error": "invalid language"}), 400
    db.set_shop_language(g.shop_id, lang)
    return jsonify({"ok": True})


@app.route("/api/usd_rate", methods=["POST"])
@login_required
@profit_blocked
def api_set_usd_rate():
    """Владелец точки/главный аккаунт сам выставляет свой курс доллара —
    сотруднику и филиалу это не нужно (они не вписывают цену закупки)."""
    data = request.get_json(force=True)
    try:
        rate = float(data.get("rate")) if data.get("rate") not in (None, "") else None
        if rate is not None and rate <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "укажите положительное число"}), 400
    db.set_shop_usd_rate(g.shop_id, rate)
    return jsonify({"ok": True, "rate": rate})




@app.route("/api/cars")
@login_required
def api_cars():
    cars = db.get_all_cars_overview(g.shop_id)
    for c in cars:
        c["client_link"] = _client_link(c.get("link_token"))
    return jsonify(cars)


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
    ok = db.update_car_and_client(g.shop_id, plate, new_plate, owner_name, owner_phone, car_brand, car_model)
    if not ok:
        return jsonify({"ok": False, "error": "машина не найдена, или новый госномер уже занят другой машиной"}), 400
    return jsonify({"ok": True, "plate": db.normalize_plate(new_plate)})


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

        if debt_amount > 0:
            if not installment_amount or not interval_days:
                return jsonify({"ok": False, "error": "укажите сумму платежа и период для рассрочки"}), 400
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
        profit = db.get_profit_range(g.shop_id, date_from, date_to)
        expenses = sum(e["amount"] for e in db.get_expenses(g.shop_id, date_from, date_to))
        result["profit"] = profit
        result["expenses"] = expenses
        result["net_profit"] = profit - expenses
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
<title>MoyBook — админ-панель</title>
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
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
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
  .logout { color: var(--btn); font-size: 12px; font-weight:700; text-decoration:none; background:var(--danger-bg); padding:6px 10px; border-radius:10px; }
  .card { background: rgba(255,255,255,.94); backdrop-filter: blur(10px); border:2px solid #DBEAFE; border-radius: 22px; padding: 16px; margin-bottom: 16px; box-shadow: 0 10px 25px -5px rgba(15,82,186,.08); }
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
</style>
</head>
<body>
<div class="speedline"></div>
<div class="container">
  <div class="topbar">
    <div style="display:flex; align-items:center; gap:10px;">
      <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
      <div>
        <h1>MoyBook</h1>
        <div class="logo-sub">Админ-панель платформы</div>
      </div>
    </div>
    <a class="logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i> Выйти</a>
  </div>

  <div id="msg"></div>

  <div class="adm-stats" id="admStats">
    <div class="adm-stat"><b>—</b><span>точек</span></div>
    <div class="adm-stat"><b>—</b><span>активных</span></div>
    <div class="adm-stat"><b>—</b><span>клиентов</span></div>
  </div>

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
        <input type="file" id="restore_file" accept=".db">
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
  <input id="shopSearch" placeholder="🔍 Поиск по названию, логину или телефону..." oninput="filterShops()">
  <div class="adm-filters" id="admFilters">
    <button class="on" data-f="all" onclick="setShopFilter('all')">Все</button>
    <button data-f="active" onclick="setShopFilter('active')">Активные</button>
    <button data-f="off" onclick="setShopFilter('off')">Выключенные</button>
    <button data-f="notg" onclick="setShopFilter('notg')">Без Telegram</button>
  </div>
  <div id="shops-body"></div>
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
      (shopFilter === 'notg' && !s.notify_telegram_id))
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
      <span>${escapeHtml(e.full_name || e.username)} <span class="hint-text">(${e.username})</span></span>
      <span style="display:flex; align-items:center; gap:8px;">
        <span class="hint-text">🔒 скрыт</span>
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
    showMsgSticky(`✅ Филиал «${shopName}» создан. Логин: <b>${username}</b>, пароль (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
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

loadShops();
</script>
</body>
</html>
"""


@app.route("/admin")
@admin_required
def admin_page():
    return render_template_string(ADMIN_PAGE)


@app.route("/api/admin/shops")
@admin_required
def api_admin_shops():
    shops = db.list_shops()
    for s in shops:
        s["owner_link"] = _client_link(f"owner_{s['owner_link_token']}") if s.get("owner_link_token") else None
    return jsonify(shops)


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
    return jsonify({"ok": True, "id": branch["id"], "username": username, "password": password})


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


def run_webapp():
    port = int(os.environ.get("PORT", 8000))
    db.init_db()
    app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)


def run_webapp_in_thread():
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    run_webapp()
