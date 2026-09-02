"""
Веб-панель для хозяина пункта замены масла.

Обычный сайт (открывается в браузере телефона или компьютера), показывает
базу машин в виде таблицы с подробной историей, форму добавления замены и
персональную ссылку/QR для привязки каждого клиента к боту — ссылка/QR
показываются автоматически сразу после сохранения новой записи.
"""

import os
import re
import time
import threading
from functools import wraps
from urllib.parse import quote
from flask import Flask, request, jsonify, render_template_string, Response

import database as db

app = Flask(__name__)

# Публичный адрес сайта (для отображения в /start у админа) — необязательно.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

# Username бота (без @) — нужен, чтобы строить персональные ссылки-приглашения.
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# Токен для вебхука от ANPR-камеры (см. /api/anpr) — необязателен, но
# рекомендуется, чтобы табло не могли "подделать" посторонние.
ANPR_WEBHOOK_TOKEN = os.environ.get("ANPR_WEBHOOK_TOKEN", "")

# Сколько секунд показывать приветствие на табло после срабатывания камеры,
# прежде чем вернуться к обычному экрану ожидания.
DISPLAY_SHOW_SECONDS = int(os.environ.get("DISPLAY_SHOW_SECONDS", "45"))

_display_lock = threading.Lock()
_display_state = {"plate": None, "shown_at": 0}

# Пароль на сайт. Если заданы SITE_USERNAME и SITE_PASSWORD — браузер спросит
# логин/пароль при входе (обычная HTTP-авторизация). Без них сайт открыт всем,
# у кого есть ссылка — так было в первой версии, но для каждой новой точки
# настоятельно рекомендуется задать эти переменные.
SITE_USERNAME = os.environ.get("SITE_USERNAME", "")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")


def require_site_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not SITE_USERNAME or not SITE_PASSWORD:
            return view(*args, **kwargs)  # авторизация не настроена — пропускаем
        auth = request.authorization
        if not auth or auth.username != SITE_USERNAME or auth.password != SITE_PASSWORD:
            return Response(
                "Требуется вход. Логин и пароль вам должен был сообщить администратор.",
                401, {"WWW-Authenticate": 'Basic realm="Oil Change Panel"'}
            )
        return view(*args, **kwargs)
    return wrapped


CAR_BRANDS = [
    "Chevrolet", "Daewoo", "Ravon", "Kia", "Hyundai", "Toyota", "Lexus",
    "Nissan", "Isuzu", "BMW", "Mercedes-Benz", "Audi", "Volkswagen",
    "Lada (ВАЗ)", "Datsun", "Honda", "Mazda", "Ford", "Mitsubishi", "Другое",
]

SERVICE_TYPES = ["Замена масла", "Замена масла + фильтр", "Полное ТО", "Другое"]

PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Замена масла — панель</title>
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
  h1 { font-size: 20px; margin: 8px 0 16px; }
  .tabs { display:flex; gap:8px; margin-bottom: 14px; }
  .tab { flex:1; text-align:center; padding: 10px; border-radius: 10px; background: var(--card); border:1px solid var(--border); cursor:pointer; font-weight:600; }
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
  <h1>🔧 Замена масла</h1>

  <div class="tabs">
    <div class="tab active" id="tab-add" onclick="showTab('add')">Внести замену</div>
    <div class="tab" id="tab-table" onclick="showTab('table')">База (таблица)</div>
    <div class="tab" id="tab-broadcast" onclick="showTab('broadcast')">📢 Рассылка</div>
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
      <div class="hint-text">Нужен, чтобы можно было в один клик отправить клиенту ссылку в WhatsApp.</div>
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
</div>

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
  document.getElementById('tab-add').classList.toggle('active', t === 'add');
  document.getElementById('tab-table').classList.toggle('active', t === 'table');
  document.getElementById('tab-broadcast').classList.toggle('active', t === 'broadcast');
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
    showMsg(`✅ Сохранено. Следующая замена ориентировочно: ${data.next_date}.`, true);
    ['plate','owner_name','owner_phone','car_model','mileage','oil_brand','cost','notes'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('filter_changed').checked = false;
    document.getElementById('interval_months').value = 3;
    // Ссылка появляется сразу же, без отдельного клика, если клиент новый и ещё не привязан
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
  // закрыть предыдущую открытую
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
      | след.: ${h.next_change_date}
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


def _client_link(token):
    if not token or not BOT_USERNAME:
        return None
    return f"https://t.me/{BOT_USERNAME}?start={token}"


@app.route("/")
@require_site_auth
def index():
    return render_template_string(PAGE, brands=CAR_BRANDS, service_types=SERVICE_TYPES)


@app.route("/api/cars")
@require_site_auth
def api_cars():
    cars = db.get_all_cars_overview()
    for c in cars:
        c["client_link"] = _client_link(c.get("link_token"))
    return jsonify(cars)


@app.route("/api/history/<plate>")
@require_site_auth
def api_history(plate):
    _, history = db.get_car_history(plate)
    return jsonify(history)


@app.route("/api/add", methods=["POST"])
@require_site_auth
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

        existing_car = db.find_car(plate)
        if existing_car:
            client_id = existing_car["client_id"]
            car_id = db.create_or_update_car(plate, client_id, car_brand, car_model)
        else:
            client = db.get_or_create_client(owner_name, owner_phone)
            client_id = client["id"]
            car_id = db.create_or_update_car(plate, client_id, car_brand, car_model)

        _, next_date = db.add_oil_change(
            car_id, mileage, service_type, oil_brand, filter_changed, cost, interval_months, notes
        )

        car_after, _ = db.get_car_history(plate)
        link = None
        if car_after and not car_after["telegram_id"]:
            link = _client_link(car_after["link_token"])

        return jsonify({"ok": True, "next_date": next_date, "client_link": link})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ============ Рассылки ============

@app.route("/api/broadcast/recipients")
@require_site_auth
def api_broadcast_recipients():
    return jsonify({"count": len(db.get_all_linked_clients())})


@app.route("/api/broadcast/history")
@require_site_auth
def api_broadcast_history():
    return jsonify(db.get_recent_broadcasts())


@app.route("/api/broadcast", methods=["POST"])
@require_site_auth
def api_broadcast_create():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "empty message"}), 400
    broadcast_id = db.create_broadcast(message)
    return jsonify({"ok": True, "id": broadcast_id})


# ============ ТАБЛО (для ANPR-камеры + телевизора у входа) ============

def _extract_plate_from_request():
    """Достаёт госномер из запроса камеры — поддерживает несколько частых
    форматов (query-параметр, JSON, form-поле, вложенный XML как у Hikvision).
    Если твоя камера шлёт данные иначе — пришли пример запроса, подстроим."""
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


@app.route("/api/anpr", methods=["GET", "POST"])
def api_anpr():
    """Сюда камера присылает распознанный номер. Настраивается в самой
    камере как адрес HTTP-уведомления (event notification URL)."""
    if ANPR_WEBHOOK_TOKEN and request.args.get("token") != ANPR_WEBHOOK_TOKEN:
        return jsonify({"ok": False, "error": "invalid token"}), 403

    plate = _extract_plate_from_request()
    if not plate:
        return jsonify({"ok": False, "error": "no plate found in request"}), 400

    plate = db.normalize_plate(plate)
    with _display_lock:
        _display_state["plate"] = plate
        _display_state["shown_at"] = time.time()

    return jsonify({"ok": True, "plate": plate})


@app.route("/api/display_state")
def api_display_state():
    with _display_lock:
        plate, shown_at = _display_state["plate"], _display_state["shown_at"]

    if not plate or (time.time() - shown_at) > DISPLAY_SHOW_SECONDS:
        return jsonify({"active": False})

    car, history = db.get_car_history(plate)
    if not car:
        return jsonify({"active": True, "found": False, "plate": plate})

    last = history[0] if history else None
    return jsonify({
        "active": True, "found": True, "plate": plate,
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
    const res = await fetch('/api/display_state');
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


@app.route("/display")
def display_page():
    return render_template_string(DISPLAY_PAGE, shop_name=os.environ.get("SHOP_NAME", ""))


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
