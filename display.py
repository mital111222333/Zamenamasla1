"""Табло у входа и сканер номеров для каждой точки (по её anpr_token):
приём номера от ANPR-камеры или телефона, состояние табло, страница табло
для телевизора, страница сканера с обычной камеры и архив «агента» для
камеры на компьютере.

Маршруты регистрируются на общем app из webapp.py при импорте этого файла
(webapp.py импортирует его в самом конце). Кто сейчас на табло
(_display_states) хранится в webapp.py: его меняет и форма замены."""
import json
import os
import re
import time

from flask import g, jsonify, render_template_string, request, send_file

import database as db
import i18n
from webapp import (
    DISPLAY_SHOW_SECONDS, PLATE_DECODE_JS, _display_lock, _display_states, app,
    employee_blocked, login_required,
)


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

    plate = db.normalize_plate(str(plate))[:20]
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

    health = db.car_health(history)
    rec = db.service_recommendation(history, health=health)
    T = i18n.get_texts(shop.get("language") or "ru")

    def pct(ratio):
        return max(0, min(150, round(ratio * 100)))

    # шкалы «Состояние машины»: масло + то, что эта точка уже меняла (и совет,
    # даже если его здесь не меняли) — без «нет данных» по остальному
    bars = []
    if health["oil"] is not None:
        bars.append({"name": T.get("fluid_0"), "pct": pct(health["oil"])})
    extra = sorted(((k, r) for k, (r, here) in health["items"].items() if here or k == rec),
                   key=lambda kr: -kr[1])[:4]
    bars += [{"name": T.get(k) or k, "pct": pct(r)} for k, r in extra]
    last = history[0] if history else {}
    return jsonify({
        "active": True, "found": True, "plate": state["plate"],
        # табло видят все в зале ожидания — только имя, без фамилии
        "owner_name": ((car["owner_name"] or "").split() or [""])[0],
        "car": " ".join(x for x in (car.get("car_brand"), car.get("car_model")) if x),
        "est_km": health["est_km"] or last.get("mileage"),
        "health": bars,
        # прошлая замена — без цен
        "last": db.last_service_summary(history),
        "rec_item": T.get(rec) if rec else None,
        "offer_pct": int(shop.get("offer_pct") or 0) if rec else 0,
    })


@app.route("/api/arrival")
@login_required
def api_arrival():
    """Карточка мастера в панели: последняя машина, которую узнал сканер или
    камера у въезда этой точки (за последние 10 минут), — кто это и что
    предложить. Панель спрашивает раз в несколько секунд с after=<прошлое at>."""
    try:
        after = float(request.args.get("after") or 0)
    except ValueError:
        after = 0.0
    with _display_lock:
        state = _display_states.get(g.shop_id)
    if not state or not state.get("plate") or state["shown_at"] <= after or time.time() - state["shown_at"] > 600:
        return jsonify({"ok": True, "arrival": None})
    car, history = db.get_car_history(g.shop_id, state["plate"])
    rec = db.service_recommendation(history) if car else None
    shop = db.get_shop(g.shop_id) or {}
    return jsonify({"ok": True, "arrival": {
        "at": state["shown_at"], "plate": state["plate"], "found": bool(car),
        "owner_name": car["owner_name"] if car else None,
        "rec_item": g.T.get(rec) if rec else None,
        "offer_pct": int(shop.get("offer_pct") or 0) if rec else 0,
    }})


DISPLAY_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>{{ T.app_title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Teko:wght@500;600;700&family=Exo+2:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<style>
  * { box-sizing: border-box; margin:0; padding:0; }
  /* Светлая тема: голубой фон, тёмно-синий текст, белые плашки; украшения
     по углам меняются по сезону сами (зима ❄, весна ✿, лето ☀, осень 🍂) */
  body {
    background: #DCEBF7;
    color: #0C447C; font-family: 'Exo 2', -apple-system, sans-serif;
    height: 100vh; display:flex; align-items:center; justify-content:center;
    overflow: hidden; text-align:center;
  }
  .deco { position:fixed; font-size: 3.2vw; color:#85B7EB; line-height:1; pointer-events:none; }
  .deco.tl { top: 3vh; left: 2.5vw; } .deco.br { bottom: 3vh; right: 2.5vw; }
  .idle .shop { font-weight:700; font-size: 4vw; color:#0C447C; }
  .idle .clock { font-family:'IBM Plex Mono', monospace; font-weight:600; font-size: 10vw; margin-top: 2vh; font-variant-numeric: tabular-nums; color:#185FA5; }
  .idle .date { font-size: 2.2vw; color:#378ADD; margin-top:1vh; }
  .hc { width: 90vw; display:flex; flex-direction:column; align-items:center; gap: 2.6vh; animation: fadein .45s ease; }
  .hc .hello { font-weight:700; font-size: 4.6vw; line-height:1.1; color:#0C447C; }
  .hc .sub { font-size: 2.2vw; color:#185FA5; }
  .uzp { display:inline-flex; align-items:stretch; background:#fff; color:#111; border: .3vw solid #111;
    border-radius: .7vw; font-family:'IBM Plex Mono', monospace; font-weight:600; font-size: 3.6vw; letter-spacing: .3vw; line-height:1.25; }
  .uzp .rg { padding: .2vh 1.1vw; border-right: .3vw solid #111; }
  .uzp .rs { padding: .2vh 1.5vw; }
  .rec { background:#fff; border-radius: 1.2vw; padding: 1.6vh 2.4vw; font-size: 2.2vw; color:#0C447C; line-height:1.35; }
  .rec b { font-weight:700; }
  .rec .off { display:inline-block; margin-left: 1vw; background:#FAEEDA; color:#854F0B; border-radius: 2vw; padding: .3vh 1.2vw; font-weight:600; font-size: 1.9vw; }
  .cards { width:100%; display:grid; grid-template-columns: 1fr 1fr; gap: 2vw; text-align:left; }
  .card { background:#fff; border-radius: 1.4vw; padding: 2.6vh 2.2vw; }
  .card h3 { font-size: 1.6vw; font-weight:600; color:#378ADD; letter-spacing: .1vw; text-transform: uppercase; margin-bottom: 1.8vh; }
  .brow { margin-bottom: 1.8vh; }
  .brow:last-child { margin-bottom: 0; }
  .btop { display:flex; justify-content:space-between; font-size: 1.9vw; color:#0C447C; }
  .bar { height: 1.3vh; border-radius: .65vh; background:#E6F1FB; overflow:hidden; margin-top: .7vh; }
  .bar i { display:block; height:100%; border-radius: .65vh; }
  .last .when { font-size: 1.9vw; color:#185FA5; margin-bottom: 1.2vh; }
  .last .chip { display:inline-block; background:#E6F1FB; color:#0C447C; border-radius: .8vw; padding: .5vh 1vw; margin: .5vh .6vw .5vh 0; font-size: 1.8vw; }
  .welcome { animation: fadein .45s ease; display:flex; flex-direction:column; align-items:center; gap: 3vh; }
  .welcome .greet { font-weight:700; font-size: 5vw; color:#0C447C; }
  .welcome .notfound { background:#fff; border-radius: 1.2vw; padding: 1.6vh 2.4vw; font-size: 2.4vw; color:#185FA5; }
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
// номер приходит от камеры, имя/услуга — из базы: в HTML только экранированными
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
// перерисовываем экран, только когда данные поменялись — иначе анимация
// появления проигрывалась бы каждую секунду и экран «мигал»
let SCREEN_KEY = '';
function show(key, html) {
  if (key === SCREEN_KEY) return;
  SCREEN_KEY = key;
  document.getElementById('screen').innerHTML = html + decoHtml();
}
// украшения по углам — по сезону: зима ❄, весна ✿, лето ☀, осень 🍂
function decoHtml() {
  const m = new Date().getMonth();
  const d = m === 11 || m <= 1 ? ['❄ ❄', '❄'] : m <= 4 ? ['✿ ✿', '✿'] : m <= 7 ? ['☀', '☀'] : ['🍂', '🍂'];
  return `<div class="deco tl">${d[0]}</div><div class="deco br">${d[1]}</div>`;
}
function renderIdle() {
  const now = new Date();
  const days = T.days_of_week;
  const clock = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  show('idle' + clock, `
    <div class="idle">
      <div class="shop">${SHOP_NAME ? esc(SHOP_NAME) : '🔧 ' + T.app_title}</div>
      <div class="clock">${clock}</div>
      <div class="date">${days[now.getDay()]}, ${pad(now.getDate())}.${pad(now.getMonth()+1)}.${now.getFullYear()}</div>
    </div>`);
}

function greetWord() {
  const h = new Date().getHours();
  return h < 12 ? T.display_morning : (h < 18 ? T.display_day : T.display_evening);
}
// номер как настоящая табличка: код региона отдельно (у узбекских номеров)
function plateHtml(p) {
  p = String(p || '');
  let rg = null, rest = p;
  let m = p.match(/^([0-9]{2})([A-Z])([0-9]{3})([A-Z]{2})$/);
  if (m) { rg = m[1]; rest = m[2] + ' ' + m[3] + ' ' + m[4]; }
  else if ((m = p.match(/^([0-9]{2})([0-9]{3})([A-Z]{3})$/))) { rg = m[1]; rest = m[2] + ' ' + m[3]; }
  return `<div class="uzp">${rg ? `<span class="rg">${esc(rg)}</span>` : ''}<span class="rs">${esc(rest)}</span></div>`;
}
function fmtKm(n) { return Math.round(Number(n) || 0).toLocaleString('ru-RU'); }
function fmtDate(s) { s = String(s || ''); return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : s; }
function barHtml(b) {
  const p = Math.round(Number(b.pct) || 0);
  const color = p >= 100 ? '#E24B4A' : (p >= 80 ? '#BA7517' : '#1D9E75');
  const label = p >= 100 ? T.display_due : p + '%';
  return `<div class="brow"><div class="btop"><span>${esc(b.name)}</span><span style="color:${color}">${esc(label)}</span></div>
    <div class="bar"><i style="width:${Math.min(p, 100)}%; background:${color}"></i></div></div>`;
}
// прошлая замена — без цен: что меняли, марка, литры
function lastHtml(last) {
  if (!last || !last.items || !last.items.length) return '';
  const chips = last.items.map(it => {
    let t = esc(it.name);
    if (it.brand) t += ' · ' + esc(it.brand);
    if (String(it.key || '').startsWith('fluid') && it.qty) t += ' · ' + esc(it.qty) + ' ' + esc(T.display_l);
    return `<span class="chip">${t}</span>`;
  }).join('');
  const when = [fmtDate(last.date), last.mileage ? fmtKm(last.mileage) + ' ' + T.display_km : ''].filter(Boolean).join(' · ');
  return `<div class="card last"><h3>${esc(T.display_last_title)}</h3><div class="when">${esc(when)}</div>${chips}</div>`;
}

function renderActive(d) {
  if (!d.found) {
    show(JSON.stringify(d), `
      <div class="welcome">
        <div class="greet">${esc(T.display_welcome)} 👋</div>
        ${plateHtml(d.plate)}
        <div class="notfound">${esc(T.display_not_client_yet)}</div>
      </div>`);
    return;
  }
  // совет «пора менять …» и скидка точки — то, ради чего табло стоит у входа
  const rec = d.rec_item
    ? `<div class="rec">💡 ${esc(T.display_rec_due)} <b>${esc(d.rec_item)}</b>${d.offer_pct ? `<span class="off">${esc(T.display_rec_discount.replace('{pct}', d.offer_pct))}</span>` : ''}</div>`
    : '';
  const bars = (d.health || []).map(barHtml).join('');
  const health = bars ? `<div class="card"><h3>${esc(T.display_health_title)}</h3>${bars}</div>` : '';
  const last = lastHtml(d.last);
  const cards = health || last
    ? `<div class="cards" style="${health && last ? '' : 'grid-template-columns:1fr; max-width:60vw;'}">${health}${last}</div>`
    : `<div class="rec">${esc(T.display_no_history)}</div>`;
  const sub = [d.car, d.est_km ? T.display_now_km.replace('{km}', fmtKm(d.est_km)) : ''].filter(Boolean).join(' · ');
  show(JSON.stringify(d), `
    <div class="hc">
      <div class="hello">${esc(greetWord())}, ${esc(d.owner_name || '')}</div>
      ${sub ? `<div class="sub">${esc(sub)}</div>` : ''}
      ${plateHtml(d.plate)}
      ${rec}
      ${cards}
    </div>`);
}

async function tick() {
  try {
    const res = await fetch('/api/display_state/' + ANPR_TOKEN);
    const d = await res.json();
    if (d.active) renderActive(d); else renderIdle();
  } catch (e) { renderIdle(); }
}

tick();
setInterval(tick, 1000);  // раз в секунду: приветствие появляется почти сразу после распознавания
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


# ============ СКАНЕР НОМЕРОВ С ОБЫЧНОЙ КАМЕРЫ (замена дорогой ANPR-камере) ============
# Телефон или веб-камера у въезда открывает /scanner/<токен табло>: номер
# распознаётся прямо в браузере той же моделью, что и сканер в панели, и
# уходит на /api/anpr/<токен> — дальше всё как с настоящей ANPR-камерой.
# Модель читает уже вырезанный номер, поэтому владелец один раз обводит
# «зону номера» — место, где оказывается номер машины на месте остановки.
# Кадры никуда не отправляются, на сервер уходит только текст номера.

SCANNER_PAGE = """
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<meta name="robots" content="noindex">
<title>{{ T.scn_title }}</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  html, body { height:100%; background:#000; color:#F5F5F2; font-family:-apple-system, 'Segoe UI', Roboto, sans-serif; overflow:hidden; }
  #wrap { position:fixed; inset:0; touch-action:none; }
  video { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; background:#000; }
  #zone { position:absolute; border:3px solid #3FBE7E; border-radius:6px; box-shadow:0 0 0 9999px rgba(0,0,0,.35); pointer-events:none; }
  #zone.hit { border-color:#FFD23F; }
  #zone.edit { border-style:dashed; border-color:#00A8E8; }
  #hint { position:absolute; top:12px; left:12px; right:12px; padding:10px 14px; border-radius:10px; background:rgba(0,168,232,.92); color:#001018; font-size:14px; line-height:1.4; display:none; }
  #bar { position:absolute; left:0; right:0; bottom:0; padding:12px 16px calc(12px + env(safe-area-inset-bottom)); background:rgba(10,10,11,.85); display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
  #info { flex:1 1 220px; min-width:0; }
  #status { font-size:15px; line-height:1.4; }
  #status b { font-family:ui-monospace, Menlo, Consolas, monospace; font-size:18px; letter-spacing:2px; }
  #status.err { color:#FF8A80; }
  #live { font-size:13px; line-height:1.4; margin-top:2px; min-height:18px; }
  #live.good { color:#3FBE7E; }
  #live.weak { color:#FFB74D; }
  #live.none { color:#9AA3B2; }
  button, select { height:40px; padding:0 14px; border-radius:10px; border:1px solid #444; background:#1E1E22; color:#F5F5F2; font-size:14px; font-family:inherit; max-width:100%; }
  button.on { background:#00A8E8; border-color:#00A8E8; color:#001018; }
  #c { display:none; }
  #peekBox { flex:none; text-align:center; font-size:11px; color:#9AA3B2; }
  #peek { display:block; width:128px; height:64px; border:1px solid #444; border-radius:4px; background:#000; margin-top:2px; }
</style>
</head>
<body>
<div id="wrap">
  <video id="v" playsinline muted autoplay></video>
  <div id="zone"></div>
  <div id="hint">{{ T.scn_zone_hint }}</div>
  <div id="bar">
    <div id="peekBox">{{ T.scn_peek }}<canvas id="peek" width="128" height="64"></canvas></div>
    <div id="info"><div id="status">{{ T.scn_loading }}</div><div id="live"></div></div>
    <select id="cam" hidden aria-label="{{ T.scn_camera }}"></select>
    <button type="button" id="zoneBtn">{{ T.scn_zone_btn }}</button>
    <button type="button" id="fsBtn" aria-label="fullscreen">⛶</button>
  </div>
</div>
<canvas id="c" width="128" height="64"></canvas>
<canvas id="dc" width="256" height="256" style="display:none"></canvas>
<script>
const T = {{ t_json|safe }};
const TOKEN = {{ anpr_token|tojson }};
const ZONE_KEY = 'oilbook_scn_zone_' + TOKEN.slice(0, 8);
const CAM_KEY = 'oilbook_scn_cam_' + TOKEN.slice(0, 8);
// распознавание — как у сканера в панели (psDecode): модель читает вырезанный
// номер 128×64, ответ — 10 позиций × 37 символов
/*__PLATE_DECODE_JS__*/
const MIN_CONF = 0.6;      // кадр учитываем при такой уверенности
const NEED_HITS = 2;       // два одинаковых прочтения подряд — и номер на табло
const INSTANT_CONF = 0.95; // при такой уверенности хватает одного кадра
const HIT_WINDOW_MS = 2000; // прочтения должны идти подряд, без долгих пауз
const RESEND_MS = 90000;   // тот же номер повторно на табло не шлём полторы минуты
const FRAME_MS = 100;      // пауза между кадрами: ~6–10 кадров в секунду, телефон не перегревается

const S = { session: null, stream: null, zone: null, editing: false, hits: {}, lastHitAt: 0,
            lastSent: {}, tickN: 0, wake: null, lockIdx: 0, lockMiss: 0 };

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function status(html, err) {
  const el = document.getElementById('status');
  el.classList.toggle('err', !!err);
  el.innerHTML = html;
}
function pretty(p) { return platePretty(p); }

// ---- зона номера: хранится в долях кадра камеры, на этом устройстве ----
function loadZone() {
  try {
    const z = JSON.parse(localStorage.getItem(ZONE_KEY) || 'null');
    if (z && z.w > 0.02 && z.h > 0.01) return z;
  } catch (e) {}
  return { x: 0.3, y: 0.55, w: 0.4, h: 0.13 };
}
function saveZone(z) { try { localStorage.setItem(ZONE_KEY, JSON.stringify(z)); } catch (e) {} }
// видео вписано в экран с полями (object-fit: contain) — где именно кадр
function videoBox() {
  const v = document.getElementById('v');
  const vw = v.videoWidth || 16, vh = v.videoHeight || 9;
  const ew = v.clientWidth, eh = v.clientHeight;
  const sc = Math.min(ew / vw, eh / vh);
  return { x: (ew - vw * sc) / 2, y: (eh - vh * sc) / 2, w: vw * sc, h: vh * sc };
}
function drawZone() {
  const b = videoBox(), z = S.zone, el = document.getElementById('zone');
  el.style.left = (b.x + z.x * b.w) + 'px';
  el.style.top = (b.y + z.y * b.h) + 'px';
  el.style.width = (z.w * b.w) + 'px';
  el.style.height = (z.h * b.h) + 'px';
}
function setupZoneEditing() {
  const wrap = document.getElementById('wrap');
  let start = null;
  const pt = e => {
    const b = videoBox(), r = wrap.getBoundingClientRect();
    const cl = n => Math.min(1, Math.max(0, n));
    return { x: cl((e.clientX - r.left - b.x) / b.w), y: cl((e.clientY - r.top - b.y) / b.h) };
  };
  wrap.addEventListener('pointerdown', e => {
    if (!S.editing || e.target.closest('#bar')) return;
    start = pt(e);
    e.preventDefault();
  });
  wrap.addEventListener('pointermove', e => {
    if (!start) return;
    const p = pt(e);
    S.zone = { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.abs(p.x - start.x), h: Math.abs(p.y - start.y) };
    drawZone();
  });
  const end = () => {
    if (!start) return;
    start = null;
    if (S.zone.w > 0.02 && S.zone.h > 0.01) saveZone(S.zone);
    else { S.zone = loadZone(); drawZone(); }
  };
  wrap.addEventListener('pointerup', end);
  wrap.addEventListener('pointercancel', end);
  document.getElementById('zoneBtn').onclick = () => {
    S.editing = !S.editing;
    const btn = document.getElementById('zoneBtn');
    btn.classList.toggle('on', S.editing);
    btn.textContent = S.editing ? T.scn_zone_done : T.scn_zone_btn;
    document.getElementById('zone').classList.toggle('edit', S.editing);
    document.getElementById('hint').style.display = S.editing ? 'block' : 'none';
  };
}

// ---- камера ----
async function startCamera(deviceId) {
  if (S.stream) S.stream.getTracks().forEach(t => t.stop());
  S.stream = null;
  // для неподвижной камеры важно разрешение: номер в зоне должен быть крупным
  const size = { width: { ideal: 1920 }, height: { ideal: 1080 } };
  const video = deviceId ? Object.assign({ deviceId: { exact: deviceId } }, size)
                         : Object.assign({ facingMode: { ideal: 'environment' } }, size);
  S.stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: video });
  const v = document.getElementById('v');
  v.srcObject = S.stream;
  try { await v.play(); } catch (e) {}
  if (!v.videoWidth) await new Promise(r => v.addEventListener('loadedmetadata', r, { once: true }));
  drawZone();
}
async function fillCameras() {
  try {
    const list = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
    if (list.length < 2) return;
    const sel = document.getElementById('cam');
    sel.innerHTML = list.map((d, i) => `<option value="${esc(d.deviceId)}">${esc(d.label || (T.scn_camera + ' ' + (i + 1)))}</option>`).join('');
    const track = S.stream && S.stream.getVideoTracks()[0];
    const cur = track && track.getSettings ? track.getSettings().deviceId : null;
    if (cur) sel.value = cur;
    sel.hidden = false;
    sel.onchange = async () => {
      try {
        await startCamera(sel.value);
        try { localStorage.setItem(CAM_KEY, sel.value); } catch (e) {}
      } catch (e) { status(esc(T.scn_no_camera), true); }
    };
  } catch (e) {}
}
// экран телефона у въезда не должен гаснуть
async function keepAwake() {
  try { if ('wakeLock' in navigator) S.wake = await navigator.wakeLock.request('screen'); } catch (e) {}
}

// ---- распознавание ----
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error('load ' + src));
    document.head.appendChild(s);
  });
}
async function loadModel() {
  if (!window.ort) await loadScript('/ocr/v1/ort.wasm.min.js');
  ort.env.wasm.wasmPaths = '/ocr/v1/';
  ort.env.wasm.numThreads = 1;
  const sess = await ort.InferenceSession.create('/ocr/v1/plate_ocr_uz.onnx', { executionProviders: ['wasm'] });
  try { await sess.run({ [sess.inputNames[0]]: new ort.Tensor('uint8', new Uint8Array(64 * 128 * 3), [1, 64, 128, 3]) }); } catch (e) {}
  return sess;
}
// Окна поиска номера вокруг зоны. Геометрия — как у рамки сканера в панели
// (там номер читается за доли секунды): ширина рамки = ширина номера,
// высота = ширина / 3.2, то есть с запасом сверху и снизу. Зона задаёт только
// где номер и какой он ширины. Машина не всегда встаёт точно — поэтому, кроме
// основной рамки, по очереди пробуем рамки крупнее/мельче и со сдвигом.
const WIN_SCALES = [1, 1.3, 0.8];
const WIN_SHIFTS = [0, -0.25, 0.25];
const WIN_INSETS = [[0, 0], [0.06, 0.14]];
const LOCK_MISSES = 15;  // столько кадров подряд без номера — отпускаем «удачную» рамку
function searchWindows() {
  const v = document.getElementById('v');
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return [];
  const z = S.zone;
  const zw = z.w * vw, cx = (z.x + z.w / 2) * vw, cy = (z.y + z.h / 2) * vh;
  const list = [];
  for (const s of WIN_SCALES) for (const dx of WIN_SHIFTS) for (const ins of WIN_INSETS) {
    let w = zw * s, h = w / 3.2;
    let x = cx - w / 2 + dx * zw, y = cy - h / 2;
    x += w * ins[0]; w *= 1 - 2 * ins[0];
    y += h * ins[1]; h *= 1 - 2 * ins[1];
    // окно, вылезающее за кадр, прижимаем к краю (размер не меняем)
    x = Math.min(Math.max(0, x), Math.max(0, vw - w));
    y = Math.min(Math.max(0, y), Math.max(0, vh - h));
    list.push({ x: x, y: y, w: Math.min(w, vw), h: Math.min(h, vh) });
  }
  return list;  // [0] — основная рамка по центру зоны
}
function cropTensor(win) {
  const v = document.getElementById('v');
  if (!win || !v.videoWidth) return null;
  const ctx = document.getElementById('c').getContext('2d', { willReadFrequently: true });
  ctx.drawImage(v, win.x, win.y, win.w, win.h, 0, 0, 128, 64);
  const px = ctx.getImageData(0, 0, 128, 64).data;
  const rgb = new Uint8Array(128 * 64 * 3);
  for (let i = 0, j = 0; i < px.length; i += 4, j += 3) { rgb[j] = px[i]; rgb[j + 1] = px[i + 1]; rgb[j + 2] = px[i + 2]; }
  return new ort.Tensor('uint8', rgb, [1, 64, 128, 3]);
}
function decode(probs) { return plateDecode(probs); }
async function readWindow(win) {
  const t = cropTensor(win);
  if (!t) return null;
  const out = await S.session.run({ [S.session.inputNames[0]]: t });
  return decode(out[S.session.outputNames[0]].data);
}
// «Искатель» номера — та же маленькая YOLO-модель, что у сканера в панели:
// сама находит номер во всём кадре (в отдельном потоке), рамку рисовать не
// нужно. Если поток не запустился (очень старое устройство) — работает зона.
const DET = 256, DET_MIN = 0.4;
const DET_WORKER = `
let sess = null, S = 256;
self.onmessage = async (e) => {
  const m = e.data;
  if (m.type === 'init') {
    try {
      S = m.size;
      importScripts(m.base + 'ort.wasm.min.js');
      ort.env.wasm.wasmPaths = m.base;
      ort.env.wasm.numThreads = 1;
      sess = await ort.InferenceSession.create(m.base + 'plate_det_s256.onnx', { executionProviders: ['wasm'] });
      self.postMessage({ type: 'ready' });
    } catch (err) { self.postMessage({ type: 'fail' }); }
    return;
  }
  if (m.type === 'frame' && sess) {
    const px = new Uint8ClampedArray(m.buf), n = S * S, f = new Float32Array(3 * n);
    for (let i = 0, j = 0; j < n; i += 4, j++) { f[j] = px[i] / 255; f[n + j] = px[i + 1] / 255; f[2 * n + j] = px[i + 2] / 255; }
    let boxes = [];
    try {
      const out = await sess.run({ [sess.inputNames[0]]: new ort.Tensor('float32', f, [1, 3, S, S]) });
      const d = out[sess.outputNames[0]].data;
      for (let k = 0; k + 6 < d.length; k += 7) boxes.push([d[k + 1], d[k + 2], d[k + 3], d[k + 4], d[k + 6]]);
    } catch (x) { boxes = []; }
    self.postMessage({ type: 'boxes', id: m.id, boxes });
  }
};`;
function startDetector() {
  try {
    const w = new Worker(URL.createObjectURL(new Blob([DET_WORKER], { type: 'text/javascript' })));
    S.detWorker = w;
    w.onmessage = e => {
      const m = e.data;
      if (m.type === 'ready') {
        S.det = true;
        // рамка больше не нужна — номер находится сам
        document.getElementById('zone').style.display = 'none';
        document.getElementById('zoneBtn').hidden = true;
        detPump();
      } else if (m.type === 'fail') { S.det = false; }
      else if (m.type === 'boxes') { S.detBusy = false; if (S.detMap && m.id === S.detMap.id) onBoxes(m.boxes, S.detMap); setTimeout(detPump, 0); }
    };
    w.onerror = () => { S.det = false; };
    w.postMessage({ type: 'init', base: location.origin + '/ocr/v1/', size: DET });
  } catch (e) { S.det = false; }
}
function detPump() {
  if (!S.det || S.detBusy || !S.detWorker) return;
  const v = document.getElementById('v');
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) { setTimeout(detPump, 100); return; }
  const r = Math.min(DET / vw, DET / vh), nw = Math.round(vw * r), nh = Math.round(vh * r);
  const dx = Math.round((DET - nw) / 2), dy = Math.round((DET - nh) / 2);
  const c = document.getElementById('dc');
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = 'rgb(114,114,114)'; ctx.fillRect(0, 0, DET, DET);
  ctx.drawImage(v, 0, 0, vw, vh, dx, dy, nw, nh);
  const buf = ctx.getImageData(0, 0, DET, DET).data.buffer;
  S.detSeq = (S.detSeq || 0) + 1;
  S.detMap = { id: S.detSeq, r, dx, dy, vw, vh };
  S.detBusy = true;
  S.detWorker.postMessage({ type: 'frame', id: S.detSeq, buf }, [buf]);
}
// самый уверенный и крупный номер в кадре
function onBoxes(boxes, map) {
  let best = null, bestRank = 0;
  for (const bx of boxes) {
    if (bx[4] < DET_MIN) continue;
    const x1 = (bx[0] - map.dx) / map.r, y1 = (bx[1] - map.dy) / map.r;
    const x2 = (bx[2] - map.dx) / map.r, y2 = (bx[3] - map.dy) / map.r;
    const area = Math.max(0, x2 - x1) * Math.max(0, y2 - y1) / (map.vw * map.vh);
    const rank = bx[4] + Math.min(area * 4, 0.15);
    if (rank > bestRank && x2 - x1 >= 12 && y2 - y1 >= 5) { bestRank = rank; best = { x1, y1, x2, y2 }; }
  }
  if (best) { S.box = best; S.boxAt = Date.now(); }
}
// найденный номер с запасом вокруг → окно для модели чтения
function boxWindow(b, pad) {
  const v = document.getElementById('v');
  const w = b.x2 - b.x1, h = b.y2 - b.y1;
  const x = Math.max(0, b.x1 - w * pad[0]), y = Math.max(0, b.y1 - h * pad[1]);
  return { x: x, y: y, w: Math.min(v.videoWidth, b.x2 + w * pad[0]) - x, h: Math.min(v.videoHeight, b.y2 + h * pad[1]) - y };
}

// за кадр — две рамки: «удачная» (где номер читался в прошлый раз) и
// следующая по очереди; берём более уверенное прочтение. Если «искатель»
// только что нашёл номер — читаем прямо его место (два варианта запаса).
async function recognize() {
  if (S.det && S.box && Date.now() - (S.boxAt || 0) < 900) {
    S.tickN++;
    let best = null, bestWin = null;
    for (const pad of [[0.08, 0.2], [0.03, 0.1]]) {
      const win = boxWindow(S.box, pad);
      const r = win.w > 4 && win.h > 2 ? await readWindow(win) : null;
      if (r && (!best || r.conf > best.conf)) { best = r; bestWin = win; }
    }
    if (bestWin) peek(bestWin);
    return best;
  }
  if (S.det) return null;  // «искатель» работает, но номера в кадре нет
  const wins = searchWindows();
  if (!wins.length) return null;
  S.tickN++;
  const lock = S.lockIdx < wins.length ? S.lockIdx : 0;
  let rot = S.tickN % wins.length;
  if (rot === lock) rot = (rot + 1) % wins.length;
  let best = null, bestIdx = lock;
  for (const idx of [lock, rot]) {
    const r = await readWindow(wins[idx]);
    if (r && (!best || r.conf > best.conf)) { best = r; bestIdx = idx; }
  }
  if (best && best.conf >= MIN_CONF) { S.lockIdx = bestIdx; S.lockMiss = 0; }
  else if (++S.lockMiss > LOCK_MISSES) { S.lockIdx = 0; S.lockMiss = 0; }
  peek(wins[bestIdx]);
  return best;
}
// маленькое окошко «что видит модель» — сразу видно, попал ли номер в рамку
function peek(win) {
  const v = document.getElementById('v');
  const ctx = document.getElementById('peek').getContext('2d');
  try { ctx.drawImage(v, win.x, win.y, win.w, win.h, 0, 0, 128, 64); } catch (e) {}
}
async function send(plate) {
  const now = Date.now();
  if (S.lastSent[plate] && now - S.lastSent[plate] < RESEND_MS) return;
  S.lastSent[plate] = now;
  try {
    const r = await fetch('/api/anpr/' + encodeURIComponent(TOKEN), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plate: plate })
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = new Date();
    status(`${esc(T.scn_sent)} <b>${esc(pretty(plate))}</b> · ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`);
  } catch (e) {
    delete S.lastSent[plate];
    status(esc(T.scn_send_fail), true);
  }
}
// живая подсказка при настройке: что модель читает в рамке прямо сейчас и
// насколько уверенно — сразу видно, мешает рамка, расстояние или свет
const NOTHING_CONF = 0.2;
function showLive(r) {
  const el = document.getElementById('live');
  if (!r || r.conf < NOTHING_CONF) { el.className = 'none'; el.textContent = T.scn_nothing; return; }
  el.className = r.conf >= MIN_CONF ? 'good' : 'weak';
  el.textContent = T.scn_seeing + ' ' + pretty(r.plate) + ' · ' + Math.round(r.conf * 100) + '%';
}
async function tick() {
  if (S.editing) document.getElementById('live').textContent = '';
  if (!S.editing && S.session) {
    let r = null;
    try { r = await recognize(); } catch (e) { r = null; }
    const zone = document.getElementById('zone');
    const now = Date.now();
    showLive(r);
    if (now - S.lastHitAt > HIT_WINDOW_MS) S.hits = {};
    if (r && r.conf >= MIN_CONF) {
      S.lastHitAt = now;
      S.hits[r.plate] = (S.hits[r.plate] || 0) + 1;
      zone.classList.add('hit');
      if (S.hits[r.plate] >= NEED_HITS || r.conf >= INSTANT_CONF) { S.hits = {}; send(r.plate); }
    } else {
      zone.classList.remove('hit');
    }
  }
  setTimeout(tick, FRAME_MS);
}

(async function init() {
  S.zone = loadZone();
  setupZoneEditing();
  window.addEventListener('resize', drawZone);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') keepAwake(); });
  document.getElementById('fsBtn').onclick = () => {
    const d = document.documentElement;
    if (d.requestFullscreen) d.requestFullscreen().catch(() => {});
  };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { status(esc(T.scn_no_camera), true); return; }
  const modelP = loadModel();
  let savedCam = null;
  try { savedCam = localStorage.getItem(CAM_KEY); } catch (e) {}
  try {
    await startCamera(savedCam);
  } catch (e) {
    let err = e;
    if (savedCam) { try { await startCamera(null); err = null; } catch (e2) { err = e2; } }
    if (err) {
      const denied = err.name === 'NotAllowedError' || err.name === 'SecurityError';
      status(esc(denied ? T.scn_denied : T.scn_no_camera), true);
      return;
    }
  }
  fillCameras();
  keepAwake();
  try { S.session = await modelP; } catch (e) { status(esc(T.scn_load_fail), true); return; }
  startDetector();
  status(esc(T.scn_waiting));
  tick();
})();
</script>
</body>
</html>
"""


# Программа для IP-камеры (tools/plate_agent): отдаём архивом прямо из панели,
# чтобы владельцу не ходить на GitHub. .bat — всегда с CRLF, иначе Windows
# ломается на метках/goto, как бы файлы ни лежали на сервере.
PLATE_AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "plate_agent")
PLATE_AGENT_FILES = ("plate_agent.py", "requirements.txt", "install.bat", "setup.bat", "start.bat", "README.md")


@app.route("/download/plate-agent.zip")
@login_required
@employee_blocked
def download_plate_agent():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in PLATE_AGENT_FILES:
            with open(os.path.join(PLATE_AGENT_DIR, name), "rb") as f:
                data = f.read()
            if name.endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            zf.writestr("OilBook-camera/" + name, data)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="OilBook-camera.zip")


SCANNER_PAGE = SCANNER_PAGE.replace("/*__PLATE_DECODE_JS__*/", PLATE_DECODE_JS)


@app.route("/scanner/<anpr_token>")
def scanner_page(anpr_token):
    shop = db.get_shop_by_anpr_token(anpr_token)
    if not shop or not shop["is_active"]:
        return "Сканер не найден — проверьте ссылку.", 404
    lang = shop.get("language") or "ru"
    T = i18n.get_texts(lang)
    t_scn = {k: v for k, v in T.items() if k.startswith("scn_")}
    return render_template_string(SCANNER_PAGE, T=T, lang=lang, anpr_token=anpr_token,
                                  t_json=json.dumps(t_scn, ensure_ascii=False))
