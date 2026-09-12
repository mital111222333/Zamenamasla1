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
import secrets
import threading
from functools import wraps
from urllib.parse import quote
from flask import Flask, request, jsonify, render_template_string, Response, session, redirect, url_for, g

import database as db
import i18n

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

PUBLIC_URL = os.environ.get("PUBLIC_URL", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
DISPLAY_SHOW_SECONDS = int(os.environ.get("DISPLAY_SHOW_SECONDS", "45"))

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
        if session.get("role") != "shop" or not session.get("shop_id"):
            return redirect(url_for("login_page"))
        shop = db.get_shop(session["shop_id"])
        if not shop or not shop["is_active"]:
            session.clear()
            return redirect(url_for("login_page"))
        g.shop_id = session["shop_id"]
        g.lang = shop.get("language") or "ru"
        g.T = i18n.get_texts(g.lang)
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
  .lang-link { display:block; text-align:center; margin-top:14px; color:#9a9a9a; font-size:12px; text-decoration:none; }
</style>
</head>
<body>
  <form class="box" method="POST">
    <h1>🔧 {{ T.login_title }}</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <input type="hidden" name="_lang" value="{{ lang }}">
    <label>{{ T.login_username }}</label>
    <input name="username" autofocus required>
    <label>{{ T.login_password }}</label>
    <input name="password" type="password" required>
    <button type="submit">{{ T.login_button }}</button>
    <a class="lang-link" href="/login?lang={{ other_lang }}">{{ T.lang_switch }}</a>
  </form>
</body>
</html>
"""


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
            session.permanent = True
            return redirect(url_for("admin_page") if shop["role"] == "admin" else url_for("index"))
        error = i18n.t("login_error", lang)
    T = i18n.get_texts(lang)
    return render_template_string(LOGIN_PAGE, error=error, T=T, lang=lang, other_lang="uz" if lang == "ru" else "ru")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ shop_name }} — панель</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #0f1115);
    --text: var(--tg-theme-text-color, #f2f2f2);
    --hint: var(--tg-theme-hint-color, #9a9a9a);
    --btn: var(--tg-theme-button-color, #3a86ff);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --card: #1a1d24;
    --border: #2a2e37;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, Segoe UI, Roboto, sans-serif; }
  .container { padding: 12px; max-width: 960px; margin: 0 auto; }
  .topbar { display:flex; justify-content:space-between; align-items:center; margin: 8px 0 16px; }
  h1 { font-size: 20px; margin: 0; }
  .logout { color: var(--hint); font-size: 13px; text-decoration:none; }
  .lang-btn { background: var(--card); border: 1px solid var(--border); color: var(--text); font-size: 12px; padding: 6px 10px; border-radius: 8px; cursor: pointer; }
  .tabs { display:flex; gap:8px; margin-bottom: 14px; flex-wrap:wrap; }
  .tab { flex:1; min-width:100px; text-align:center; padding: 10px; border-radius: 10px; background: var(--card); border:1px solid var(--border); cursor:pointer; font-weight:600; }
  .tab.active { background: var(--btn); color: var(--btn-text); border-color: var(--btn); }
  .card { background: var(--card); border:1px solid var(--border); border-radius: 12px; padding: 14px; margin-bottom: 12px; }
  .field { margin-bottom: 10px; }
  .row2 { display:flex; gap:10px; }
  .row2 .field { flex:1; }
  label { display:block; font-size: 13px; color: var(--hint); margin-bottom: 4px; }
  input, select, textarea {
    width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border);
    background: #11141a; color: var(--text); font-size: 15px;
  }
  .checkbox-row { display:flex; align-items:center; gap:8px; }
  .checkbox-row input { width:auto; }
  .item-row { display:flex; gap:8px; align-items:center; margin-bottom:8px; }
  .item-row .item-name { flex:1.3; font-size:13px; color:var(--hint); }
  .item-row input { flex:1; padding:8px; font-size:13px; }
  .item-row .item-total { flex:0.9; font-size:12px; color:var(--hint); text-align:right; }
  button.submit {
    width: 100%; padding: 12px; border: none; border-radius: 10px;
    background: var(--btn); color: var(--btn-text); font-size: 16px; font-weight: 600;
    cursor: pointer; margin-top: 6px;
  }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color: var(--hint); font-weight: 600; position: sticky; top: 0; background: var(--bg); }
  .table-wrap { overflow-x: auto; border:1px solid var(--border); border-radius: 12px; }
  .badge { display:inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight:600; cursor:pointer; border:none; }
  .badge.linked { background: #1e3a2a; color: #6fdc9a; }
  .badge.unlinked { background: #3a1e1e; color: #dc6f6f; }
  .search { margin-bottom: 10px; }
  .hint-text { color: var(--hint); font-size: 12px; margin-top: 6px; }
  .msg { padding: 10px; border-radius: 8px; margin-bottom: 10px; font-size: 14px; }
  .msg.ok { background:#1e3a2a; color:#6fdc9a; }
  .msg.err { background:#3a1e1e; color:#dc6f6f; }
  .modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.6); align-items:center; justify-content:center; z-index:50; }
  .modal-overlay.open { display:flex; }
  .modal { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; max-width:320px; width:90%; text-align:center; }
  .modal-wide { max-width:480px; max-height:85vh; overflow-y:auto; }
  .modal img { width:180px; height:180px; margin: 10px auto; display:block; border-radius:8px; background:#fff; }
  .modal .link-text { font-size:12px; word-break:break-all; color:var(--hint); background:#11141a; padding:8px; border-radius:8px; margin-bottom:10px; }
  .modal button { margin-top:8px; }
  .modal a.wa-btn { display:block; text-decoration:none; }
  .close-btn { background:transparent; border:none; color:var(--hint); font-size:14px; cursor:pointer; margin-top:6px; width:100%; padding:8px; }
  .history-toggle { background:transparent; border:none; color:var(--btn); font-size:12px; cursor:pointer; text-decoration:underline; padding:0; }
  .history-row td { background:#11141a; white-space:normal; }
  .history-entry { padding:6px 0; border-bottom:1px dashed var(--border); font-size:12px; }
  .stats-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:12px; }
  .stats-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; }
  .stats-card .label { font-size:13px; color:var(--hint); margin-bottom:8px; }
  .stats-card .amount { font-size:20px; font-weight:700; color:var(--btn); }
  .stats-card .count { font-size:12px; color:var(--hint); margin-top:4px; }
  .known-client { margin-top:8px; padding:10px; background:#11141a; border:1px solid var(--btn); border-radius:10px; font-size:12px; }
  .known-client .kc-title { color:#6fdc9a; font-weight:600; margin-bottom:6px; }
  .known-client .kc-entry { padding:4px 0; border-bottom:1px dashed var(--border); }
  .known-client .kc-entry:last-child { border-bottom:none; }
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <h1>🔧 {{ shop_name }}</h1>
    <div style="display:flex; align-items:center; gap:14px;">
      <button class="lang-btn" onclick="switchLanguage()">{{ T.lang_switch }}</button>
      <a class="logout" href="/logout">{{ T.logout }}</a>
    </div>
  </div>

  <div class="tabs">
    <div class="tab active" id="tab-add" onclick="showTab('add')">{{ T.tab_add }}</div>
    <div class="tab" id="tab-table" onclick="showTab('table')">{{ T.tab_table }}</div>
    <div class="tab" id="tab-broadcast" onclick="showTab('broadcast')">{{ T.tab_broadcast }}</div>
    <div class="tab" id="tab-export" onclick="showTab('export')">{{ T.tab_export }}</div>
    <div class="tab" id="tab-stats" onclick="showTab('stats')">{{ T.tab_stats }}</div>
    {% if sms_enabled %}<div class="tab" id="tab-sms" onclick="showTab('sms')">{{ T.tab_sms }}</div>{% endif %}
    {% if warehouse_enabled %}<div class="tab" id="tab-warehouse" onclick="showTab('warehouse')">{{ T.tab_warehouse }}</div>{% endif %}
  </div>

  <div id="msg"></div>

  <div id="view-add" class="card">
    <div class="field">
      <label>{{ T.field_plate }}</label>
      <input id="plate" placeholder="01A123BC" onblur="lookupPlate()">
      <div id="knownClientPanel"></div>
    </div>
    <div class="field">
      <label>{{ T.field_owner_name }}</label>
      <input id="owner_name" placeholder="Имя Фамилия">
    </div>
    <div class="field">
      <label>{{ T.field_owner_phone }}</label>
      <input id="owner_phone" placeholder="+998 90 123 45 67">
      <div class="hint-text">{{ T.hint_owner_phone }}</div>
    </div>
    <div class="row2">
      <div class="field">
        <label>{{ T.field_car_brand }}</label>
        <select id="car_brand">
          {% for b in brands %}<option value="{{b}}">{{b}}</option>{% endfor %}
        </select>
      </div>
      <div class="field">
        <label>{{ T.field_car_model }}</label>
        <input id="car_model" placeholder="Cobalt, Nexia, Malibu...">
      </div>
    </div>
    <div class="row2">
      <div class="field">
        <label>{{ T.field_mileage }}</label>
        <input id="mileage" type="number" placeholder="45000">
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

    <div class="field" style="margin-top:14px; padding:12px; background:#11141a; border-radius:10px;">
      <label style="font-size:15px;">{{ T.field_total }}</label>
      <div id="totalCost" style="font-size:22px; font-weight:700; color:var(--btn);">0</div>
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
    <input class="search" id="search" placeholder="{{ T.search_ph }}" oninput="renderTable()">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{{ T.th_plate }}</th><th>{{ T.th_owner }}</th><th>{{ T.th_phone }}</th><th>{{ T.th_car }}</th>
            <th>{{ T.th_last_change }}</th><th>{{ T.th_mileage }}</th><th>{{ T.th_next_mileage }}</th><th>{{ T.th_service }}</th><th>{{ T.th_total }}</th><th>{{ T.th_next_change }}</th><th>{{ T.th_client }}</th><th>{{ T.th_history }}</th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
  </div>

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

  <div id="view-export" class="card" style="display:none;">
    <p style="margin-top:0;">{{ T.export_p1 }}</p>
    <p class="hint-text">{{ T.export_p2 }}</p>
    <button class="submit" onclick="window.location.href='/api/export'">{{ T.export_btn }}</button>
  </div>

  <div id="view-stats" style="display:none;">
    <div id="statsGrid" class="stats-grid">{{ T.stats_loading }}</div>

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

  {% if warehouse_enabled %}
  <div id="view-warehouse" style="display:none;">
    <div class="card">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.wh_add_product }}</label>
      <div class="row2">
        <div class="field">
          <label>{{ T.wh_category }}</label>
          <select id="wh_new_category"></select>
        </div>
        <div class="field">
          <label>{{ T.wh_product_name }}</label>
          <input id="wh_new_name" placeholder="MITANOL 5W-30">
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label>{{ T.wh_sell_price }}</label>
          <input id="wh_new_sell_price" type="number" placeholder="45000">
        </div>
        <div class="field">
          <label>{{ T.wh_purchase_price }}</label>
          <input id="wh_new_purchase_price" type="number" placeholder="30000">
        </div>
      </div>
      <div class="field">
        <label>{{ T.wh_initial_stock }}</label>
        <input id="wh_new_stock" type="number" placeholder="0">
      </div>
      <button class="submit" onclick="createProduct()">{{ T.wh_add_btn }}</button>
    </div>

    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.wh_products_title }}</label>
      <div class="table-wrap" style="overflow-x:auto;">
        <table>
          <thead><tr>
            <th>{{ T.wh_category }}</th><th>{{ T.wh_product_name }}</th><th>{{ T.wh_stock }}</th>
            <th>{{ T.wh_sell_price }}</th><th>{{ T.wh_purchase_price }}</th><th></th>
          </tr></thead>
          <tbody id="products-body"></tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.wh_restock_history }}</label>
      <div id="restockHistory"></div>
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
    <div class="field">
      <label>{{ T.wh_purchase_price }}</label>
      <input id="restock_price" type="number">
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
    <button class="submit" onclick="copyLink()" style="background:#2a2e37;">{{ T.modal_copy }}</button>
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

    <div class="field" style="margin-top:10px; padding:12px; background:#11141a; border-radius:10px;">
      <label style="font-size:15px;">{{ T.field_total }}</label>
      <div id="svcTotalCost" style="font-size:20px; font-weight:700; color:var(--btn);">0</div>
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
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

let carsCache = [];
let openHistoryRow = null;
let historyDataCache = {};  // { plate: [entry, entry, ...] } — чтобы кнопки не тащили сырые данные записи (с заметками, апострофами и т.п.) прямо в HTML-атрибут onclick, а брали их отсюда по id

function showTab(t) {
  document.getElementById('view-add').style.display = t === 'add' ? 'block' : 'none';
  document.getElementById('view-table').style.display = t === 'table' ? 'block' : 'none';
  document.getElementById('view-broadcast').style.display = t === 'broadcast' ? 'block' : 'none';
  document.getElementById('view-export').style.display = t === 'export' ? 'block' : 'none';
  document.getElementById('view-stats').style.display = t === 'stats' ? 'block' : 'none';
  document.getElementById('tab-add').classList.toggle('active', t === 'add');
  document.getElementById('tab-table').classList.toggle('active', t === 'table');
  document.getElementById('tab-broadcast').classList.toggle('active', t === 'broadcast');
  document.getElementById('tab-export').classList.toggle('active', t === 'export');
  document.getElementById('tab-stats').classList.toggle('active', t === 'stats');
  const smsView = document.getElementById('view-sms');
  const smsTab = document.getElementById('tab-sms');
  if (smsView) smsView.style.display = t === 'sms' ? 'block' : 'none';
  if (smsTab) smsTab.classList.toggle('active', t === 'sms');
  const whView = document.getElementById('view-warehouse');
  const whTab = document.getElementById('tab-warehouse');
  if (whView) whView.style.display = t === 'warehouse' ? 'block' : 'none';
  if (whTab) whTab.classList.toggle('active', t === 'warehouse');
  if (t === 'table') loadCars();
  if (t === 'broadcast') loadBroadcastInfo();
  if (t === 'stats') loadStats();
  if (t === 'warehouse') loadWarehouse();
}

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
  sel.innerHTML = allKeys.map(key => `<option value="${key}">${T[key]}</option>`).join('');
}

async function loadWarehouse() {
  renderWarehouseCategoryOptions();
  const res = await fetch('/api/products');
  productsCache = await res.json();
  renderProductsTable();
  loadRestockHistory();
  // склад мог поменяться (добавили/удалили/пополнили товар) — обновляем поля
  // "марка" в форме "Внести замену" и в форме редактирования/добавления из
  // истории, чтобы новый товар сразу стал доступен в списке, без
  // перезагрузки всей страницы
  renderItemLists();
  renderSvcItemLists();
}

function renderProductsTable() {
  const body = document.getElementById('products-body');
  if (!body) return;
  if (!productsCache.length) {
    body.innerHTML = `<tr><td colspan="6">${T.wh_no_products}</td></tr>`;
    return;
  }
  body.innerHTML = productsCache.map(p => {
    const isLow = p.stock_qty < 0;
    const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
    return `
    <tr>
      <td>${T[p.category] || p.category}</td>
      <td>${escapeHtml(p.name)}</td>
      <td style="${isLow ? 'color:#dc6f6f; font-weight:700;' : ''}">${isLow ? '⚠️ ' : ''}${p.stock_qty} ${unitLabel}</td>
      <td>${p.sell_price ? p.sell_price.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</td>
      <td>${p.purchase_price ? p.purchase_price.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</td>
      <td>
        <button class="history-toggle" onclick="openRestockModal(${p.id}, ${escapeHtml(JSON.stringify(p.name))})">${T.wh_restock_action}</button>
        &nbsp;·&nbsp;
        <button class="history-toggle" style="color:#dc6f6f;" onclick="deleteProduct(${p.id}, ${escapeHtml(JSON.stringify(p.name))})">${T.wh_delete_action}</button>
      </td>
    </tr>
  `;
  }).join('');
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
    ['wh_new_name','wh_new_sell_price','wh_new_purchase_price','wh_new_stock'].forEach(id => document.getElementById(id).value = '');
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

function openRestockModal(id, name) {
  restockingProductId = id;
  document.getElementById('restockModalTitle').textContent = T.wh_restock_title + ': ' + name;
  document.getElementById('restock_qty').value = '';
  document.getElementById('restock_price').value = '';
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
  const res = await fetch(`/api/products/${restockingProductId}/restock`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    closeRestockModal();
    showMsg(T.wh_restocked, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function loadRestockHistory() {
  const el = document.getElementById('restockHistory');
  if (!el) return;
  const res = await fetch('/api/restock_history');
  const history = await res.json();
  el.innerHTML = history.length ? history.map(r => `
    <div style="padding:8px 0;border-bottom:1px dashed var(--border);font-size:13px;">
      ${r.restock_date} — ${escapeHtml(r.product_name)}: +${r.quantity} ${r.unit === 'pc' ? T.unit_pc : T.unit_l}
      ${r.purchase_price ? ' (' + r.purchase_price.toLocaleString('ru-RU') + ' ' + T.currency + '/ед.)' : ''}
    </div>
  `).join('') : `<div class="hint-text">${T.wh_no_restocks}</div>`;
}


async function loadStats() {
  const res = await fetch('/api/stats');
  const s = await res.json();
  let profit = null;
  if (WAREHOUSE_ENABLED) {
    const pRes = await fetch('/api/profit_stats');
    profit = await pRes.json();
  }
  const periods = [
    ['today', T.stats_today], ['yesterday', T.stats_yesterday], ['week', T.stats_week],
    ['month', T.stats_month], ['year', T.stats_year],
  ];
  document.getElementById('statsGrid').innerHTML = periods.map(([key, label]) => `
    <div class="stats-card">
      <div class="label">${label}</div>
      <div class="amount">${s[key].total.toLocaleString('ru-RU')} ${T.currency}</div>
      <div class="count">${T.stats_services_count} ${s[key].count}</div>
      ${profit ? `<div class="count" style="color:#6fdc9a;">${T.stats_profit_label} ${profit[key].toLocaleString('ru-RU')} ${T.currency}</div>` : ''}
    </div>
  `).join('');
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

async function applyStatsRange() {
  const from = document.getElementById('stats_from').value;
  const to = document.getElementById('stats_to').value;
  if (!from || !to) return;
  const res = await fetch(`/api/stats/range?from=${from}&to=${to}`);
  const data = await res.json();
  if (!data.ok) { document.getElementById('statsRangeResult').innerHTML = ''; return; }
  document.getElementById('statsRangeResult').innerHTML = `
    <div class="stats-card">
      <div class="label">${T.stats_range_result} ${from} — ${to}</div>
      <div class="amount">${data.total.toLocaleString('ru-RU')} ${T.currency}</div>
      <div class="count">${T.stats_services_count} ${data.count}</div>
    </div>
  `;
}

renderStatsPresets();

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
  return items;
}

function updateTotal() {
  const total = collectItems().reduce((sum, i) => sum + i.total, 0);
  document.getElementById('totalCost').textContent = total.toLocaleString('ru-RU') + ' ' + T.currency;
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
  updateTotal();
}

async function lookupPlate() {
  const plate = document.getElementById('plate').value.trim();
  const panel = document.getElementById('knownClientPanel');
  if (!plate) { panel.innerHTML = ''; return; }
  try {
    const res = await fetch('/api/history/' + encodeURIComponent(plate));
    const data = await res.json();
    if (!data.car) { panel.innerHTML = ''; return; }

    document.getElementById('owner_name').value = data.car.owner_name || '';
    document.getElementById('owner_phone').value = data.car.owner_phone || '';
    if (data.car.car_brand) document.getElementById('car_brand').value = data.car.car_brand;
    document.getElementById('car_model').value = data.car.car_model || '';

    const shown = data.history.slice(0, 2);
    const historyHtml = shown.length ? shown.map(h => `
      <div class="kc-entry">📅 ${h.change_date} — ${h.service_type || T.history_service_fallback}${h.cost ? ', ' + h.cost.toLocaleString('ru-RU') + ' ' + T.currency : ''}</div>
    `).join('') : `<div class="kc-entry">${T.kc_no_history}</div>`;
    const moreHint = data.history.length > 2 ? `<div class="kc-entry" style="opacity:.7;">${T.kc_more_hint}</div>` : '';

    panel.innerHTML = `<div class="known-client"><div class="kc-title">${T.kc_found_title}</div>${historyHtml}${moreHint}</div>`;
  } catch (e) {
    panel.innerHTML = '';
  }
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
  };
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

function renderTable() {
  const q = (document.getElementById('search').value || '').toLowerCase();
  const rows = carsCache.filter(c =>
    (c.plate_number || '').toLowerCase().includes(q) || (c.owner_name || '').toLowerCase().includes(q)
  );
  document.getElementById('table-body').innerHTML = rows.map((c, i) => `
    <tr>
      <td><b>${c.plate_number}</b></td>
      <td>${c.owner_name || ''}</td>
      <td>${c.owner_phone || ''}</td>
      <td>${(c.car_brand || '')} ${(c.car_model || '')}</td>
      <td>${c.change_date || '—'}</td>
      <td>${c.mileage || '—'}</td>
      <td>${c.next_mileage || '—'}</td>
      <td>${c.service_type || '—'}</td>
      <td>${c.cost ? c.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</td>
      <td>${c.next_change_date || '—'}</td>
      <td>${c.telegram_id
          ? `<span class="badge linked">${T.badge_linked}</span>`
          : `<button class="badge unlinked" onclick="openModal(${escapeHtml(JSON.stringify(c.plate_number))}, ${escapeHtml(JSON.stringify(c.client_link || ''))}, ${escapeHtml(JSON.stringify(c.owner_phone || ''))})">${T.badge_unlinked_btn}</button>`}</td>
      <td><button class="history-toggle" onclick="toggleHistory('${c.plate_number}')">${T.history_more}</button></td>
    </tr>
    <tr class="history-row" id="hist-${c.plate_number}" style="display:none;"><td colspan="12"><div id="hist-body-${c.plate_number}">${T.history_loading}</div></td></tr>
  `).join('');
}

async function toggleHistory(plate) {
  const row = document.getElementById('hist-' + plate);
  if (!row) return;  // строки может не быть в DOM, если фильтр поиска её скрыл
  const isOpen = row.style.display !== 'none';
  if (openHistoryRow && openHistoryRow !== plate) {
    const prevRow = document.getElementById('hist-' + openHistoryRow);
    if (prevRow) prevRow.style.display = 'none';  // прошлая открытая строка могла исчезнуть при поиске
  }
  if (isOpen) {
    row.style.display = 'none';
    openHistoryRow = null;
    return;
  }
  row.style.display = '';
  openHistoryRow = plate;
  const res = await fetch('/api/history/' + encodeURIComponent(plate));
  const data = await res.json();
  const history = data.history || [];
  historyDataCache[plate] = history;
  const body = document.getElementById('hist-body-' + plate);
  const addBtnHtml = `<div style="margin-bottom:10px;"><button class="submit" style="padding:8px;" onclick="openAddServiceModal(${escapeHtml(JSON.stringify(plate))})">${T.add_service_btn}</button></div>`;
  if (!history.length) {
    body.innerHTML = addBtnHtml + T.history_empty;
    return;
  }
  body.innerHTML = addBtnHtml + history.map(h => {
    let itemsHtml = '';
    if (h.items_json) {
      try {
        const items = JSON.parse(h.items_json);
        itemsHtml = '<div style="margin:4px 0 4px 12px;">' + items.map(it =>
          `• ${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + it.qty + ' ' + T.liters_ph : ''}: ${it.total.toLocaleString('ru-RU')} ${T.currency}`
        ).join('<br>') + '</div>';
      } catch (e) { /* старая запись без items_json */ }
    }
    return `
    <div class="history-entry" id="hist-entry-${h.id}">
      📅 ${h.change_date} — ${escapeHtml(h.service_type || T.history_service_fallback)} |
      ${T.history_mileage_label} ${h.mileage || '—'} км | ${T.history_next_mileage_label} ${h.next_mileage || '—'} км
      ${h.cost ? ' | ' + T.history_total_label + ' ' + h.cost.toLocaleString('ru-RU') + ' ' + T.currency : ''}
      | ${T.history_next_label} ${h.next_change_date || '—'}
      ${itemsHtml}
      ${h.notes ? '<span style="color:var(--hint)">' + T.history_notes_label + ' ' + escapeHtml(h.notes) + '</span>' : ''}
      <div style="margin-top:6px;">
        <button class="history-toggle" onclick="openEditModalById(${h.id}, ${escapeHtml(JSON.stringify(plate))})">${T.entry_edit}</button>
        &nbsp;·&nbsp;
        <button class="history-toggle" style="color:#dc6f6f;" onclick="deleteEntry(${h.id}, ${escapeHtml(JSON.stringify(plate))})">${T.entry_delete}</button>
      </div>
    </div>
  `;
  }).join('');
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
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
  return items;
}

function updateSvcTotal() {
  const total = collectSvcItems().reduce((sum, i) => sum + i.total, 0);
  document.getElementById('svcTotalCost').textContent = total.toLocaleString('ru-RU') + ' ' + T.currency;
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
  updateSvcTotal();
}

function fillSvcItemsFrom(items) {
  // подставляет уже сохранённые позиции в поля модалки (режим редактирования)
  (items || []).forEach(it => {
    if (!it.key) return;
    if (it.key === 'other') {
      const label = (it.name || '').replace(T.other_prefix + ': ', '');
      document.getElementById('svc_other_name').value = label === T.other_unnamed ? '' : label;
      document.getElementById('svc_other_price').value = it.total ?? '';
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

  let res;
  if (svcModal.mode === 'edit') {
    res = await fetch('/api/oil_change/' + svcModal.id, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ mileage, next_mileage, interval_value, interval_unit, notes, items }),
    });
  } else {
    const carRow = carsCache.find(c => c.plate_number === svcModal.plate);
    res = await fetch('/api/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        plate: svcModal.plate, owner_name: carRow ? carRow.owner_name : '', mileage, next_mileage,
        interval_value, interval_unit, notes, items,
      }),
    });
  }
  const data = await res.json();
  if (data.ok) {
    closeEditModal();
    showMsg(svcModal.mode === 'edit' ? T.entry_saved : T.service_added, true);
    document.getElementById('hist-' + svcModal.plate).style.display = 'none';
    toggleHistory(svcModal.plate);
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
    document.getElementById('hist-' + plate).style.display = 'none';
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


@app.route("/api/cars")
@login_required
def api_cars():
    cars = db.get_all_cars_overview(g.shop_id)
    for c in cars:
        c["client_link"] = _client_link(c.get("link_token"))
    return jsonify(cars)


@app.route("/api/history/<plate>")
@login_required
def api_history(plate):
    car, history = db.get_car_history(g.shop_id, plate)
    return jsonify({"car": car, "history": history})


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

        existing_car = db.find_car(g.shop_id, plate)
        if existing_car:
            client_id = existing_car["client_id"]
            car_id = db.create_or_update_car(g.shop_id, plate, client_id, car_brand, car_model)
        else:
            client = db.get_or_create_client(g.shop_id, owner_name, owner_phone)
            client_id = client["id"]
            car_id = db.create_or_update_car(g.shop_id, plate, client_id, car_brand, car_model)

        _, next_date = db.add_oil_change(
            car_id, mileage, None, None, False, None, interval_value, interval_unit, notes,
            next_mileage=next_mileage, items=items
        )

        car_after, _ = db.get_car_history(g.shop_id, plate)
        link = None
        if car_after and not car_after["telegram_id"]:
            link = _client_link(car_after["link_token"])

        return jsonify({"ok": True, "next_date": next_date, "client_link": link})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


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
def api_stats():
    return jsonify(db.get_revenue_stats(g.shop_id))


@app.route("/api/stats/range")
@login_required
def api_stats_range():
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return jsonify({"ok": False, "error": "invalid date"}), 400
    result = db.get_revenue_range(g.shop_id, date_from, date_to)
    result["ok"] = True
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
    return jsonify(db.list_products(g.shop_id))


@app.route("/api/products", methods=["POST"])
@login_required
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
        unit = "pc" if category.startswith("filter_") else "l"
        sell_price = int(data["sell_price"]) if data.get("sell_price") not in (None, "") else None
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
        initial_stock = float(data["initial_stock"]) if data.get("initial_stock") not in (None, "") else 0
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    product = db.create_product(g.shop_id, category, name, unit, sell_price, purchase_price, initial_stock)
    return jsonify({"ok": True, "product": product})


@app.route("/api/products/<int:product_id>", methods=["PUT"])
@login_required
def api_update_product(product_id):
    data = request.get_json(force=True)
    try:
        ok = db.update_product(
            product_id, g.shop_id,
            name=data.get("name"),
            sell_price=int(data["sell_price"]) if data.get("sell_price") not in (None, "") else None,
            purchase_price=int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None,
        )
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
@login_required
def api_delete_product(product_id):
    ok = db.delete_product(product_id, g.shop_id)
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/products/<int:product_id>/restock", methods=["POST"])
@login_required
def api_restock_product(product_id):
    data = request.get_json(force=True)
    try:
        quantity = float(data["quantity"])
        purchase_price = int(data["purchase_price"]) if data.get("purchase_price") not in (None, "") else None
        restock_date = data.get("restock_date") or None
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    ok = db.restock_product(product_id, g.shop_id, quantity, purchase_price, restock_date)
    if not ok:
        return jsonify({"ok": False, "error": "товар не найден"}), 404
    return jsonify({"ok": True})


@app.route("/api/restock_history")
@login_required
def api_restock_history():
    return jsonify(db.get_restock_history(g.shop_id))


@app.route("/api/profit_stats")
@login_required
def api_profit_stats():
    return jsonify(db.get_profit_stats(g.shop_id))


@app.route("/api/export")
@login_required
def api_export():
    import json
    data = db.export_shop_data(g.shop_id)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"backup_shop_{g.shop_id}_{data['exported_at'][:10]}.json"
    return Response(
        body, mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ============ Админ-панель (платформа) ============

ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Админ-панель — точки</title>
<style>
  :root { --bg:#0f1115; --text:#f2f2f2; --hint:#9a9a9a; --btn:#3a86ff; --card:#1a1d24; --border:#2a2e37; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, Segoe UI, Roboto, sans-serif; }
  .container { padding: 12px; max-width: 900px; margin: 0 auto; }
  .topbar { display:flex; justify-content:space-between; align-items:center; margin: 8px 0 16px; }
  h1 { font-size: 20px; margin: 0; }
  .logout { color: var(--hint); font-size: 13px; text-decoration:none; }
  .card { background: var(--card); border:1px solid var(--border); border-radius: 12px; padding: 14px; margin-bottom: 16px; }
  .field { margin-bottom: 10px; }
  .row2 { display:flex; gap:10px; }
  .row2 .field { flex:1; }
  label { display:block; font-size: 13px; color: var(--hint); margin-bottom: 4px; }
  input { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border); background: #11141a; color: var(--text); font-size: 15px; }
  button.submit { width: 100%; padding: 12px; border: none; border-radius: 10px; background: var(--btn); color: #fff; font-size: 16px; font-weight: 600; cursor: pointer; margin-top: 6px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--hint); font-weight: 600; }
  .badge { display:inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight:600; cursor:pointer; border:none; }
  .badge.active { background: #1e3a2a; color: #6fdc9a; }
  .badge.inactive { background: #3a1e1e; color: #dc6f6f; }
  .hint-text { color: var(--hint); font-size: 12px; margin-top: 6px; }
  .msg { padding: 10px; border-radius: 8px; margin-bottom: 10px; font-size: 14px; }
  .msg.ok { background:#1e3a2a; color:#6fdc9a; }
  .msg.err { background:#3a1e1e; color:#dc6f6f; }
  .new-creds { background:#11141a; border:1px dashed var(--btn); border-radius:8px; padding:10px; font-size:13px; margin-top:10px; }
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <h1>🗂️ Точки замены масла</h1>
    <a class="logout" href="/logout">Выйти</a>
  </div>

  <div id="msg"></div>

  <div class="card">
    <h3 style="margin-top:0;">➕ Добавить новую точку</h3>
    <div class="field">
      <label>Название точки</label>
      <input id="new_shop_name" placeholder="MITAL Namangan">
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
      <label>Локация (необяз.) — вставь широту и долготу из Google Карт через запятую</label>
      <input id="new_location" placeholder="40.782123, 72.344567">
      <div class="hint-text">Открой точку на Google Картах, нажми и удержи на месте — внизу появятся два числа через запятую, скопируй их сюда целиком.</div>
    </div>
    <button class="submit" onclick="createShop()">Создать точку</button>
    <div id="newCreds"></div>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">Все точки</h3>
    <div class="table-wrap" style="overflow-x:auto;">
    <table>
      <thead><tr><th>Название</th><th>Логин</th><th>Пароль</th><th>Телефон</th><th>Клиентов</th><th>Статус</th><th>SMS</th><th>Склад</th></tr></thead>
      <tbody id="shops-body"></tbody>
    </table>
    </div>
  </div>
</div>

<script>
function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 8000);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function loadShops() {
  const res = await fetch('/api/admin/shops');
  const shops = await res.json();
  document.getElementById('shops-body').innerHTML = shops.map(s => `
    <tr>
      <td>${s.shop_name || '—'}</td>
      <td>${s.username}</td>
      <td>${s.password_plain
          ? `<span style="font-family:monospace;">${s.password_plain}</span>`
          : `<span class="hint-text">не сохранён</span>`}
          <br><button class="badge" style="background:#2a2e37;color:var(--hint);margin-top:4px;" onclick="resetPassword(${s.id}, ${escapeHtml(JSON.stringify(s.username))})">сбросить</button></td>
      <td>${s.phone || '—'}</td>
      <td>${s.client_count}</td>
      <td><button class="badge ${s.is_active ? 'active' : 'inactive'}" onclick="toggleShop(${s.id}, ${s.is_active ? 0 : 1})">
        ${s.is_active ? 'активна' : 'выключена'}
      </button></td>
      <td><button class="badge ${s.sms_enabled ? 'active' : 'inactive'}" onclick="toggleSms(${s.id}, ${s.sms_enabled ? 0 : 1})">
        ${s.sms_enabled ? 'включён' : 'выключен'}
      </button></td>
      <td><button class="badge ${s.warehouse_enabled ? 'active' : 'inactive'}" onclick="toggleWarehouse(${s.id}, ${s.warehouse_enabled ? 0 : 1})">
        ${s.warehouse_enabled ? 'включён' : 'выключен'}
      </button></td>
    </tr>
  `).join('');
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

async function toggleSms(id, makeEnabled) {
  await fetch(`/api/admin/shops/${id}/toggle_sms`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: !!makeEnabled})
  });
  loadShops();
}

async function resetPassword(id, username) {
  if (!confirm(`Сбросить пароль для «${username}»? Старый пароль перестанет работать.`)) return;
  const res = await fetch(`/api/admin/shops/${id}/reset_password`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsg(`✅ Новый пароль для «${username}»: <b>${data.password}</b> (он же теперь виден в таблице ниже)`, true);
    loadShops();
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function createShop() {
  const payload = {
    shop_name: document.getElementById('new_shop_name').value.trim(),
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
    ['new_shop_name','new_username','new_password','new_phone','new_notify_id','new_address','new_location'].forEach(id => document.getElementById(id).value = '');
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
    return jsonify(db.list_shops())


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
    )
    return jsonify({"ok": True, "id": shop["id"], "username": username, "password": password})


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
<style>
  * { box-sizing: border-box; margin:0; padding:0; }
  body {
    background: radial-gradient(circle at center, #10131a 0%, #05070b 100%);
    color: #fff; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    height: 100vh; display:flex; align-items:center; justify-content:center;
    overflow: hidden; text-align:center;
  }
  .idle .shop { font-size: 4vw; font-weight:700; letter-spacing:1px; opacity:.9; }
  .idle .clock { font-size: 10vw; font-weight:800; margin-top: 2vh; font-variant-numeric: tabular-nums; }
  .idle .date { font-size: 2.2vw; opacity:.6; margin-top:1vh; }
  .active { animation: fadein .4s ease; }
  .active .greet { font-size: 4.2vw; font-weight:800; color:#6fdc9a; }
  .active .plate { font-size: 6vw; font-weight:900; letter-spacing:4px; margin: 3vh 0; padding: 1vh 3vw;
    border: 4px solid #fff; border-radius: 16px; display:inline-block; }
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
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def run_webapp_in_thread():
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    run_webapp()
