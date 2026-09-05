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
<title>Вход — Замена масла</title>
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
</style>
</head>
<body>
  <form class="box" method="POST">
    <h1>🔧 Вход в панель</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <label>Логин</label>
    <input name="username" autofocus required>
    <label>Пароль</label>
    <input name="password" type="password" required>
    <button type="submit">Войти</button>
  </form>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
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
        error = "Неверный логин или пароль."
    return render_template_string(LOGIN_PAGE, error=error)


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
  .modal img { width:180px; height:180px; margin: 10px auto; display:block; border-radius:8px; background:#fff; }
  .modal .link-text { font-size:12px; word-break:break-all; color:var(--hint); background:#11141a; padding:8px; border-radius:8px; margin-bottom:10px; }
  .modal button { margin-top:8px; }
  .modal a.wa-btn { display:block; text-decoration:none; }
  .close-btn { background:transparent; border:none; color:var(--hint); font-size:14px; cursor:pointer; margin-top:6px; width:100%; padding:8px; }
  .history-toggle { background:transparent; border:none; color:var(--btn); font-size:12px; cursor:pointer; text-decoration:underline; padding:0; }
  .history-row td { background:#11141a; white-space:normal; }
  .history-entry { padding:6px 0; border-bottom:1px dashed var(--border); font-size:12px; }
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <h1>🔧 {{ shop_name }}</h1>
    <a class="logout" href="/logout">Выйти</a>
  </div>

  <div class="tabs">
    <div class="tab active" id="tab-add" onclick="showTab('add')">Внести замену</div>
    <div class="tab" id="tab-table" onclick="showTab('table')">База</div>
    <div class="tab" id="tab-broadcast" onclick="showTab('broadcast')">📢 Рассылка</div>
    <div class="tab" id="tab-export" onclick="showTab('export')">⬇️ Экспорт</div>
  </div>

  <div id="msg"></div>

  <div id="view-add" class="card">
    <div class="field">
      <label>Госномер</label>
      <input id="plate" placeholder="01A123BC">
    </div>
    <div class="field">
      <label>Имя владельца</label>
      <input id="owner_name" placeholder="Имя Фамилия">
    </div>
    <div class="field">
      <label>Телефон владельца</label>
      <input id="owner_phone" placeholder="+998 90 123 45 67">
      <div class="hint-text">Нужен, чтобы можно было в один клик отправить клиенту ссылку в WhatsApp, и чтобы связать несколько его машин в один аккаунт.</div>
    </div>
    <div class="row2">
      <div class="field">
        <label>Марка авто</label>
        <select id="car_brand">
          {% for b in brands %}<option value="{{b}}">{{b}}</option>{% endfor %}
        </select>
      </div>
      <div class="field">
        <label>Модель</label>
        <input id="car_model" placeholder="Cobalt, Nexia, Malibu...">
      </div>
    </div>
    <div class="field">
      <label>Пробег (км)</label>
      <input id="mileage" type="number" placeholder="45000">
    </div>
    <div class="field">
      <label>Тип услуги</label>
      <select id="service_type">
        {% for s in service_types %}<option value="{{s}}">{{s}}</option>{% endfor %}
      </select>
    </div>
    <div class="field">
      <label>Марка масла</label>
      <input id="oil_brand" placeholder="MITANOL 5W-30">
    </div>
    <div class="field checkbox-row">
      <input type="checkbox" id="filter_changed">
      <label style="margin:0;">Меняли фильтр</label>
    </div>
    <div class="row2">
      <div class="field">
        <label>Стоимость (сум)</label>
        <input id="cost" type="number" placeholder="150000">
      </div>
      <div class="field">
        <label>Через сколько месяцев следующая замена?</label>
        <input id="interval_months" type="number" placeholder="3" value="3">
      </div>
    </div>
    <div class="field">
      <label>Заметки</label>
      <textarea id="notes" rows="2" placeholder="Необязательно"></textarea>
    </div>
    <button class="submit" onclick="submitCar()">Сохранить</button>
  </div>

  <div id="view-table" style="display:none;">
    <input class="search" id="search" placeholder="Поиск по госномеру или имени..." oninput="renderTable()">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Госномер</th><th>Владелец</th><th>Телефон</th><th>Авто</th>
            <th>Посл. замена</th><th>Пробег</th><th>Услуга</th><th>Масло</th><th>След. замена</th><th>Клиент</th><th>История</th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
  </div>

  <div id="view-broadcast" class="card" style="display:none;">
    <div class="field">
      <label>Текст объявления/акции</label>
      <textarea id="broadcast_message" rows="5" placeholder="Например: 🎉 Скидка 15% на масла MITANOL до конца месяца! Успейте записаться."></textarea>
      <div class="hint-text" id="broadcastRecipients">Загрузка получателей...</div>
    </div>
    <button class="submit" onclick="sendBroadcast()">📢 Отправить всем привязанным клиентам</button>
    <div style="margin-top:18px;">
      <div class="hint-text" style="margin-bottom:8px;">Последние рассылки:</div>
      <div id="broadcastHistory"></div>
    </div>
  </div>

  <div id="view-export" class="card" style="display:none;">
    <p style="margin-top:0;">Скачайте полную копию базы вашей точки — все клиенты, машины и история обслуживания одним файлом (формат JSON).</p>
    <p class="hint-text">Пригодится для переноса на другой сервер или как резервная копия на всякий случай.</p>
    <button class="submit" onclick="window.location.href='/api/export'">⬇️ Скачать резервную копию</button>
  </div>
</div>
"""

MODAL_AND_SCRIPT = """
<div class="modal-overlay" id="linkModal">
  <div class="modal">
    <h3 id="modalPlate"></h3>
    <div class="hint-text">Отправьте ссылку клиенту или покажите QR — после перехода он автоматически привяжется к боту.</div>
    <img id="modalQr" alt="QR-код">
    <div class="link-text" id="modalLink"></div>
    <a class="wa-btn" id="modalTg" href="#" target="_blank"><button class="submit" type="button" style="background:#2AABEE;">✈️ Отправить в Telegram</button></a>
    <a class="wa-btn" id="modalWa" href="#" target="_blank"><button class="submit" type="button">📲 Отправить в WhatsApp</button></a>
    <button class="submit" onclick="copyLink()" style="background:#2a2e37;">Скопировать ссылку</button>
    <button class="close-btn" onclick="closeModal()">Закрыть</button>
  </div>
</div>

<script>
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

let carsCache = [];
let openHistoryRow = null;

function showTab(t) {
  document.getElementById('view-add').style.display = t === 'add' ? 'block' : 'none';
  document.getElementById('view-table').style.display = t === 'table' ? 'block' : 'none';
  document.getElementById('view-broadcast').style.display = t === 'broadcast' ? 'block' : 'none';
  document.getElementById('view-export').style.display = t === 'export' ? 'block' : 'none';
  document.getElementById('tab-add').classList.toggle('active', t === 'add');
  document.getElementById('tab-table').classList.toggle('active', t === 'table');
  document.getElementById('tab-broadcast').classList.toggle('active', t === 'broadcast');
  document.getElementById('tab-export').classList.toggle('active', t === 'export');
  if (t === 'table') loadCars();
  if (t === 'broadcast') loadBroadcastInfo();
}

async function loadBroadcastInfo() {
  const res = await fetch('/api/broadcast/recipients');
  const data = await res.json();
  document.getElementById('broadcastRecipients').textContent =
    `Получат сообщение: ${data.count} клиент(ов), привязавших бот.`;

  const res2 = await fetch('/api/broadcast/history');
  const items = await res2.json();
  document.getElementById('broadcastHistory').innerHTML = items.length ? items.map(b => `
    <div style="padding:8px 0;border-bottom:1px dashed var(--border);font-size:13px;">
      <div>${b.message.length > 80 ? b.message.slice(0,80) + '…' : b.message}</div>
      <div class="hint-text">${b.created_at} — статус: ${b.status}${b.status === 'done' ? `, доставлено ${b.total_sent}, не удалось ${b.total_failed}` : ''}</div>
    </div>
  `).join('') : '<div class="hint-text">Пока рассылок не было.</div>';
}

async function sendBroadcast() {
  const message = document.getElementById('broadcast_message').value.trim();
  if (!message) { showMsg('Введите текст объявления.', false); return; }
  if (!confirm('Отправить это сообщение всем привязанным клиентам?')) return;
  const res = await fetch('/api/broadcast', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Рассылка поставлена в очередь, отправится в течение примерно 15 секунд.', true);
    document.getElementById('broadcast_message').value = '';
    setTimeout(loadBroadcastInfo, 4000);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 6000);
}

async function submitCar() {
  const payload = {
    plate: document.getElementById('plate').value.trim(),
    owner_name: document.getElementById('owner_name').value.trim(),
    owner_phone: document.getElementById('owner_phone').value.trim(),
    car_brand: document.getElementById('car_brand').value,
    car_model: document.getElementById('car_model').value.trim(),
    mileage: document.getElementById('mileage').value,
    service_type: document.getElementById('service_type').value,
    oil_brand: document.getElementById('oil_brand').value.trim(),
    filter_changed: document.getElementById('filter_changed').checked,
    cost: document.getElementById('cost').value,
    interval_months: document.getElementById('interval_months').value,
    notes: document.getElementById('notes').value.trim(),
  };
  if (!payload.plate || !payload.owner_name || !payload.interval_months) {
    showMsg('Заполните хотя бы госномер, имя владельца и интервал в месяцах.', false);
    return;
  }
  const res = await fetch('/api/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(`✅ Сохранено. Следующая замена ориентировочно: ${data.next_date || '—'}.`, true);
    ['plate','owner_name','owner_phone','car_model','mileage','oil_brand','cost','notes'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('filter_changed').checked = false;
    document.getElementById('interval_months').value = 3;
    if (data.client_link) {
      openModal(payload.plate, data.client_link, payload.owner_phone);
    }
  } else {
    showMsg('Ошибка: ' + data.error, false);
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
      <td>${c.service_type || '—'}</td>
      <td>${c.oil_brand || '—'}</td>
      <td>${c.next_change_date || '—'}</td>
      <td>${c.telegram_id
          ? '<span class="badge linked">привязан</span>'
          : `<button class="badge unlinked" onclick='openModal(${JSON.stringify(c.plate_number)}, ${JSON.stringify(c.client_link || "")}, ${JSON.stringify(c.owner_phone || "")})'>показать ссылку</button>`}</td>
      <td><button class="history-toggle" onclick="toggleHistory('${c.plate_number}')">подробнее</button></td>
    </tr>
    <tr class="history-row" id="hist-${c.plate_number}" style="display:none;"><td colspan="11"><div id="hist-body-${c.plate_number}">Загрузка...</div></td></tr>
  `).join('');
}

async function toggleHistory(plate) {
  const row = document.getElementById('hist-' + plate);
  const isOpen = row.style.display !== 'none';
  if (openHistoryRow && openHistoryRow !== plate) {
    document.getElementById('hist-' + openHistoryRow).style.display = 'none';
  }
  if (isOpen) {
    row.style.display = 'none';
    openHistoryRow = null;
    return;
  }
  row.style.display = '';
  openHistoryRow = plate;
  const res = await fetch('/api/history/' + encodeURIComponent(plate));
  const history = await res.json();
  const body = document.getElementById('hist-body-' + plate);
  if (!history.length) {
    body.innerHTML = 'Пока нет записей.';
    return;
  }
  body.innerHTML = history.map(h => `
    <div class="history-entry">
      📅 ${h.change_date} — ${h.service_type || 'Замена масла'}${h.filter_changed ? ' + фильтр' : ''} |
      пробег: ${h.mileage || '—'} км | масло: ${h.oil_brand || '—'}
      ${h.cost ? ' | ' + h.cost.toLocaleString('ru-RU') + ' сум' : ''}
      | след.: ${h.next_change_date || '—'}
      ${h.notes ? ' | заметка: ' + h.notes : ''}
    </div>
  `).join('');
}

function openModal(plate, link, phone) {
  if (!link) { showMsg('BOT_USERNAME не задан на сервере — ссылку сформировать нельзя.', false); return; }
  document.getElementById('modalPlate').textContent = plate;
  document.getElementById('modalLink').textContent = link;
  document.getElementById('modalQr').src = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(link);
  const tgBtn = document.getElementById('modalTg');
  tgBtn.href = 'https://t.me/share/url?url=' + encodeURIComponent(link) + '&text=' + encodeURIComponent('Ваша персональная ссылка для напоминаний о замене масла:');
  const waBtn = document.getElementById('modalWa');
  if (phone) {
    let digits = phone.replace(/\\D/g, '');
    if (digits && !digits.startsWith('998') && digits.length <= 9) digits = '998' + digits;
    const text = encodeURIComponent('Здравствуйте! Вот ваша персональная ссылка для напоминаний о замене масла: ' + link);
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
  navigator.clipboard.writeText(text).then(() => showMsg('Ссылка скопирована', true));
}
</script>
</body>
</html>
"""

PAGE = PAGE + MODAL_AND_SCRIPT


@app.route("/")
@login_required
def index():
    return render_template_string(PAGE, brands=CAR_BRANDS, service_types=SERVICE_TYPES,
                                   shop_name=session.get("shop_name") or "Замена масла")


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
    _, history = db.get_car_history(g.shop_id, plate)
    return jsonify(history)


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
        service_type = data.get("service_type") or "Замена масла"
        oil_brand = data.get("oil_brand") or None
        filter_changed = bool(data.get("filter_changed"))
        cost = int(data["cost"]) if data.get("cost") else None
        interval_months = int(data["interval_months"])
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
            car_id, mileage, service_type, oil_brand, filter_changed, cost, interval_months, notes
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
    <table>
      <thead><tr><th>Название</th><th>Логин</th><th>Клиентов</th><th>Статус</th></tr></thead>
      <tbody id="shops-body"></tbody>
    </table>
  </div>
</div>

<script>
function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 8000);
}

async function loadShops() {
  const res = await fetch('/api/admin/shops');
  const shops = await res.json();
  document.getElementById('shops-body').innerHTML = shops.map(s => `
    <tr>
      <td>${s.shop_name || '—'}</td>
      <td>${s.username}</td>
      <td>${s.client_count}</td>
      <td><button class="badge ${s.is_active ? 'active' : 'inactive'}" onclick="toggleShop(${s.id}, ${s.is_active ? 0 : 1})">
        ${s.is_active ? 'активна' : 'выключена'}
      </button></td>
    </tr>
  `).join('');
}

async function toggleShop(id, makeActive) {
  await fetch(`/api/admin/shops/${id}/toggle`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({active: !!makeActive})
  });
  loadShops();
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
<title>Табло</title>
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
const SHOP_NAME = {{ shop_name|tojson }};
const ANPR_TOKEN = {{ anpr_token|tojson }};

function pad(n) { return n.toString().padStart(2, '0'); }
function renderIdle() {
  const now = new Date();
  const days = ['Якшанба','Душанба','Сешанба','Чоршанба','Пайшанба','Жума','Шанба'];
  document.getElementById('screen').innerHTML = `
    <div class="idle">
      <div class="shop">${SHOP_NAME || '🔧 Пункт замены масла'}</div>
      <div class="clock">${pad(now.getHours())}:${pad(now.getMinutes())}</div>
      <div class="date">${days[now.getDay()]}, ${pad(now.getDate())}.${pad(now.getMonth()+1)}.${now.getFullYear()}</div>
    </div>`;
}

function renderActive(d) {
  if (!d.found) {
    document.getElementById('screen').innerHTML = `
      <div class="active">
        <div class="greet">Хуш келибсиз! 👋</div>
        <div class="plate">${d.plate}</div>
        <div class="notfound">Сиз ҳали бизнинг мижозимиз эмассиз</div>
      </div>`;
    return;
  }
  const last = d.last_service_date
    ? `Сўнгги хизмат: ${d.last_service_date}${d.service_type ? ' — ' + d.service_type : ''}${d.oil_brand ? ' (' + d.oil_brand + ')' : ''}`
    : 'Хизмат тарихи топилмади';
  document.getElementById('screen').innerHTML = `
    <div class="active">
      <div class="greet">Ассалому алайкум, ҳурматли мижоз ${d.owner_name || ''}!</div>
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
    shop = db.get_shop_by_anpr_token(anpr_token)
    if not shop or not shop["is_active"]:
        return "Табло не найдено — проверьте ссылку.", 404
    return render_template_string(DISPLAY_PAGE, shop_name=shop.get("shop_name") or "", anpr_token=anpr_token)


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
