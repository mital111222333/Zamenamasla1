"""Самостоятельная регистрация точки (/register → подтверждение в боте →
решение администратора) и реферальная программа «Пригласи друга» (/r/<код>,
раздел «Пригласи друга», бонусы в админке).

Маршруты регистрируются на общем app из webapp.py при импорте этого файла
(webapp.py импортирует его в самом конце). reg_decide и reg_notify_admin
вызывает bot.py через webapp, _ref_sync — subscription.py."""
import json
import re
from urllib.parse import quote

from flask import g, jsonify, make_response, redirect, render_template_string, request

import database as db
import i18n
from webapp import (
    ADMIN_TELEGRAM_ID, BOT_TOKEN, BOT_USERNAME, PUBLIC_URL, _client_ip, _client_link,
    _fmt_day, _fmt_sum, _is_sub_owner, _send_telegram_message, _tg_api, admin_required,
    app, logger, login_required, sub_exempt,
)


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
<link rel="manifest" href="/static/manifest.json?v=2">
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
  .refnote { background:#2a2410; border:1px solid #6b5a1c; color:#f5dc8a; border-radius:10px; padding:10px 12px; font-size:14px; margin:0 0 14px; line-height:1.45; }
  .refnote b { color:#fff; }
</style>
</head>
<body>
  <div class="brand"><div class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></div></div>

  <form class="box" id="regForm" novalidate onsubmit="submitReg(event)">
    {% if ref_name %}<div class="refnote">🎁 {{ T.reg_ref_from }} <b>{{ ref_name }}</b></div>{% endif %}
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


REFERRAL_PAGE = r"""<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0A2540">
<link rel="manifest" href="/static/manifest.json?v=2">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<title>{{ T.ref_title }} · OilBook</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@800&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
<style>
:root { --line:#E3E8F0; --text:#0B1F3A; --muted:#5B6B82; --blue:#1D6FE0; --blue-bg:#F0F6FF; --green:#0E6B3E; --green-bg:#E3F4EA;
  --gold:#F5B700; --mono:'IBM Plex Mono', ui-monospace, monospace; }
* { box-sizing:border-box; }
body { margin:0; background:#F3F5F9; color:var(--text); font-family:'Plus Jakarta Sans', system-ui, -apple-system, sans-serif; -webkit-tap-highlight-color:transparent; }
.wrap { max-width:520px; margin:0 auto; min-height:100vh; min-height:100dvh; display:flex; flex-direction:column; }
.top { position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:8px; padding:calc(6px + env(safe-area-inset-top, 0px)) 16px 6px; min-height:56px; background:#fff; border-bottom:1px solid var(--line); }
.back { width:44px; height:44px; margin-left:-12px; display:flex; align-items:center; justify-content:center; color:var(--text); text-decoration:none; font-size:20px; }
.ttl { font-size:18px; font-weight:700; }
.wm { margin-left:auto; font-family:Sora, sans-serif; font-weight:800; font-size:17px; }
.wm b { color:var(--blue); font-weight:800; }
.body { flex:1; padding:16px 16px calc(28px + env(safe-area-inset-bottom, 0px)); display:flex; flex-direction:column; gap:12px; }
.card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; }
.h { font-size:16px; font-weight:700; margin:0 0 8px; }
.muted { color:var(--muted); font-size:14px; }
.hero { position:relative; overflow:hidden; background:#0B1F3A; color:#fff; border-radius:16px; padding:18px 18px 20px; }
.hero:after { content:""; position:absolute; right:-40px; top:-40px; width:150px; height:150px; border-radius:50%; background:radial-gradient(circle, rgba(245,183,0,.35), rgba(245,183,0,0) 70%); }
.hero .pct { font-family:Sora, sans-serif; font-weight:800; font-size:52px; line-height:1; color:var(--gold); }
.hero .t1 { font-size:17px; font-weight:700; margin-top:8px; line-height:1.35; position:relative; }
.hero .t2 { font-size:14px; color:#B9C6DA; margin-top:6px; line-height:1.45; position:relative; }
.hero .gift { position:absolute; right:18px; top:18px; font-size:34px; color:var(--gold); }
.linkbox { display:flex; align-items:center; gap:8px; background:#F4F7FB; border:1.5px dashed #9AAAC2; border-radius:12px; padding:6px 6px 6px 12px; }
.linkbox .l { flex:1; min-width:0; font-family:var(--mono); font-size:14px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cp { width:44px; height:44px; border:0; border-radius:10px; background:#fff; color:var(--blue); font-size:18px; cursor:pointer; flex:none; border:1px solid var(--line); }
.btn { height:50px; border:0; border-radius:12px; background:var(--blue); color:#fff; font:700 15px 'Plus Jakarta Sans', system-ui, sans-serif; cursor:pointer; width:100%; display:flex; align-items:center; justify-content:center; gap:10px; text-decoration:none; }
.btn.tg { background:#229ED9; }
.btn.ghost { background:#fff; color:var(--text); border:1.5px solid #D5DDE8; }
.btn:disabled { opacity:.55; }
.btns { display:flex; flex-direction:column; gap:8px; margin-top:10px; }
.stats { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
.stat { background:#fff; border:1px solid var(--line); border-radius:14px; padding:12px 8px; text-align:center; }
.stat b { display:block; font-family:var(--mono); font-size:20px; font-weight:600; }
.stat span { font-size:12px; color:var(--muted); }
.money { display:flex; gap:10px; }
.money > div { flex:1; }
.money .v { font-family:var(--mono); font-size:20px; font-weight:600; margin-top:2px; }
.money .v.g { color:var(--green); }
.field { display:flex; gap:8px; margin-top:8px; }
.field input { flex:1; min-width:0; height:48px; border:1.5px solid #D5DDE8; border-radius:12px; padding:0 10px; font:600 16px var(--mono); letter-spacing:-.3px; color:var(--text); background:#fff; }
.field input:focus { outline:none; border-color:var(--blue); }
.field .btn { width:auto; padding:0 14px; height:48px; flex:none; }
.ok { color:var(--green); font-size:13px; font-weight:700; margin-top:6px; }
.err { color:#B3122F; font-size:13px; font-weight:700; margin-top:6px; }
.it { display:flex; align-items:center; gap:10px; padding:11px 0; border-top:1px solid #EEF1F6; }
.it:first-of-type { border-top:0; }
.it .ic { width:38px; height:38px; border-radius:10px; background:#EEF3FA; color:var(--blue); display:flex; align-items:center; justify-content:center; flex:none; }
.it .mid { flex:1; min-width:0; }
.it .nm { font-weight:700; font-size:15px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.it .sb { font-size:12.5px; color:var(--muted); margin-top:2px; }
.chip { font-size:12px; font-weight:700; padding:4px 9px; border-radius:999px; white-space:nowrap; flex:none; }
.chip.grey { background:#EEF1F6; color:#3E4F68; }
.chip.blue { background:var(--blue-bg); color:var(--blue); }
.chip.green { background:var(--green-bg); color:var(--green); }
.chip.dark { background:#0B1F3A; color:#fff; }
.empty { text-align:center; color:var(--muted); font-size:14px; padding:10px 0 4px; line-height:1.45; }
.steps { display:flex; flex-direction:column; gap:10px; }
.st { display:flex; gap:12px; align-items:flex-start; font-size:14px; line-height:1.45; color:#3E4F68; }
.st b { width:26px; height:26px; border-radius:50%; background:var(--gold); color:#0B1F3A; display:flex; align-items:center; justify-content:center; font-size:13px; flex:none; }
.small { font-size:12.5px; color:var(--muted); line-height:1.5; }
.hidden { display:none !important; }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <a class="back" href="/" aria-label="{{ T.sub_back }}"><i class="fa-solid fa-chevron-left"></i></a>
    <div class="ttl">{{ T.ref_title }}</div>
    <div class="wm"><b>Oil</b>Book</div>
  </div>
  <div class="body">
    <div class="hero">
      <i class="fa-solid fa-gift gift"></i>
      <div class="pct">{{ pct }}%</div>
      <div class="t1">{{ T.ref_hero_title }}</div>
      <div class="t2">{{ T.ref_hero_text }}</div>
    </div>

    <div class="card">
      <div class="h">{{ T.ref_your_link }}</div>
      <div class="linkbox">
        <span class="l" id="refLink">{{ link }}</span>
        <button class="cp" type="button" aria-label="{{ T.sub_copy }}" onclick="copyLink(this)"><i class="fa-regular fa-copy"></i></button>
      </div>
      <div class="btns">
        <a class="btn tg" href="{{ tg_share }}" target="_blank" rel="noopener"><i class="fa-brands fa-telegram"></i>{{ T.ref_share_tg }}</a>
        <button class="btn ghost hidden" id="shareBtn" type="button" onclick="shareOther()"><i class="fa-solid fa-share-nodes"></i>{{ T.ref_share_other }}</button>
      </div>
    </div>

    <div class="stats">
      <div class="stat"><b>{{ stats.invited }}</b><span>{{ T.ref_stat_invited }}</span></div>
      <div class="stat"><b>{{ stats.paying }}</b><span>{{ T.ref_stat_paying }}</span></div>
      <div class="stat"><b>{{ earned_txt }}</b><span>{{ T.ref_stat_earned }}</span></div>
    </div>

    <div class="card">
      <div class="money">
        <div><div class="muted">{{ T.ref_to_receive }}</div><div class="v g">{{ pending_txt }}</div></div>
        <div><div class="muted">{{ T.ref_paid_out }}</div><div class="v">{{ paid_txt }}</div></div>
      </div>
      <div class="muted" style="margin-top:12px; font-weight:600; color:var(--text);">{{ T.ref_card_label }}</div>
      <div class="field">
        <input id="card" inputmode="numeric" autocomplete="cc-number" maxlength="23" placeholder="8600 0000 0000 0000" value="{{ card }}">
        <button class="btn" id="cardBtn" type="button" onclick="saveCard()">{{ T.ref_card_save }}</button>
      </div>
      <div class="small" style="margin-top:6px;">{{ T.ref_card_hint }}</div>
      <div class="ok hidden" id="cardOk">{{ T.ref_card_saved }}</div>
      <div class="err hidden" id="cardErr"></div>
    </div>

    <div class="card">
      <div class="h">{{ T.ref_list_title }}</div>
      {% if items %}
        {% for it in items %}
        <div class="it">
          <div class="ic"><i class="fa-solid fa-store"></i></div>
          <div class="mid"><div class="nm">{{ it.name }}</div><div class="sb">{{ it.date }} · {{ it.sub }}</div></div>
          <span class="chip {{ it.chip[0] }}">{{ it.chip[1] }}</span>
        </div>
        {% endfor %}
      {% else %}
        <div class="empty">{{ T.ref_list_empty }}</div>
      {% endif %}
    </div>

    <div class="card">
      <div class="h">{{ T.ref_how_title }}</div>
      <div class="steps">
        <div class="st"><b>1</b><span>{{ T.ref_how_1 }}</span></div>
        <div class="st"><b>2</b><span>{{ T.ref_how_2 }}</span></div>
        <div class="st"><b>3</b><span>{{ T.ref_how_3.format(pct=pct) }}</span></div>
      </div>
      <div class="small" style="margin-top:12px;">{{ T.ref_rules }}</div>
    </div>
  </div>
</div>
<script>
(function () {
  const LINK = {{ link|tojson }};
  const SHARE_TEXT = {{ share_text|tojson }};
  const L = { saving: {{ T.ref_saving|tojson }}, save: {{ T.ref_card_save|tojson }}, err: {{ T.sub_err|tojson }}, copied: {{ T.sub_copied|tojson }} };
  const $ = id => document.getElementById(id);
  if (navigator.share) $('shareBtn').classList.remove('hidden');

  window.copyLink = function (btn) {
    const done = () => { const old = btn.innerHTML; btn.innerHTML = '<i class="fa-solid fa-check"></i>'; setTimeout(() => { btn.innerHTML = old; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(LINK).then(done, () => { prompt(L.copied, LINK); });
    } else { prompt(L.copied, LINK); }
  };

  window.shareOther = function () {
    navigator.share({ text: SHARE_TEXT }).catch(() => {});
  };

  $('card').addEventListener('input', function () {
    const d = this.value.replace(/[^0-9]/g, '').slice(0, 19);
    this.value = d.replace(/(.{4})/g, '$1 ').trim();
    $('cardOk').classList.add('hidden'); $('cardErr').classList.add('hidden');
  });

  let busy = false;
  window.saveCard = async function () {
    if (busy) return;
    busy = true;
    const btn = $('cardBtn');
    btn.disabled = true; btn.textContent = L.saving;
    try {
      const res = await fetch('/api/referral/card', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card: $('card').value }) });
      let data = {};
      try { data = await res.json(); } catch (e) {}
      if (res.status === 401) { location.href = '/login'; return; }
      if (res.ok && data.ok) { $('card').value = data.card || ''; $('cardOk').classList.remove('hidden'); }
      else { $('cardErr').textContent = data.error || L.err; $('cardErr').classList.remove('hidden'); }
    } catch (e) {
      $('cardErr').textContent = L.err; $('cardErr').classList.remove('hidden');
    } finally {
      busy = false; btn.disabled = false; btn.textContent = L.save;
    }
  };
})();
</script>
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


@app.route("/welcome")
def landing_page():
    """Рекламная страница OilBook (ссылка для Instagram): static/landing.html."""
    import os
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, "static"), "landing.html", max_age=0)


@app.route("/register")
def register_page():
    lang = _reg_lang()
    ref_code = (request.args.get("ref") or request.cookies.get(_REF_COOKIE) or "").strip()
    referrer = db.find_referrer_by_code(ref_code) if ref_code else None
    resp = make_response(render_template_string(
        REGISTER_PAGE, T=i18n.get_texts(lang), lang=lang, other_lang="uz" if lang == "ru" else "ru",
        cities=REG_CITIES[lang], bot_username=BOT_USERNAME or "OilBook",
        ref_name=(referrer.get("shop_name") or referrer.get("username")) if referrer else ""))
    if referrer and request.args.get("ref"):
        _set_ref_cookie(resp, referrer["ref_code"])
    return resp


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
    referrer = db.find_referrer_by_code(data.get("ref") or request.cookies.get(_REF_COOKIE))
    if referrer:
        db.set_registration_ref(req["id"], referrer["id"])
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
    ] + _reg_ref_line(req))


def _reg_map_link(req: dict) -> str:
    if req.get("lat") is None or req.get("lon") is None:
        return "—"
    link = f"https://maps.google.com/?q={req['lat']:.6f},{req['lon']:.6f}"
    return link if db.reg_location_in_uz(req["lat"], req["lon"]) else link + " ⚠️ вне Узбекистана"


def reg_notify_admin(req: dict, auto: bool = False):
    """Заявка подтверждена в боте — администратору платформы (с кнопками, либо
    просто уведомление, если точка подключается автоматически)."""
    if not ADMIN_TELEGRAM_ID:
        return None
    payload = {"chat_id": ADMIN_TELEGRAM_ID, "text": _reg_admin_text(req), "disable_web_page_preview": "true"}
    if not auto:
        payload["reply_markup"] = json.dumps({"inline_keyboard": [[
            {"text": f"✅ Одобрить ({db.trial_days()} дн. бесплатно)", "callback_data": f"reg:ok:{req['id']}"},
            {"text": "❌ Отклонить", "callback_data": f"reg:no:{req['id']}"},
        ]]})
    res = _tg_api("sendMessage", payload)
    if res and res.get("message_id"):
        db.set_registration_admin_msg(req["id"], res["message_id"])
        if req.get("lat") is not None and req.get("lon") is not None:
            # метка на карте прямо под заявкой — видно место без перехода по ссылке
            _tg_api("sendLocation", {"chat_id": ADMIN_TELEGRAM_ID, "latitude": req["lat"], "longitude": req["lon"],
                                     "reply_to_message_id": res["message_id"]})
    return res


def reg_decide(req_id: int, approve: bool, auto: bool = False) -> dict:
    """Единое решение по заявке — и из админки, и из кнопок в Telegram."""
    r = db.approve_registration(req_id) if approve else db.reject_registration(req_id)
    req = r.get("req")
    if not r["ok"]:
        return r
    shop = r.get("shop")
    if approve and shop and req.get("ref_shop_id"):
        try:
            if db.link_referred_shop(shop["id"], req["ref_shop_id"]):
                _ref_notify(req["ref_shop_id"], "ref_bot_joined", shop=req["shop_name"])
        except Exception as e:
            logger.error(f"Реферал: не удалось привязать точку {shop.get('id')}: {e}")
    if req.get("admin_msg_id") and ADMIN_TELEGRAM_ID:
        mark = (f"✅ {'Подключена автоматически' if auto else 'Одобрено'} — точка создана, "
                f"пробный период до {_fmt_day(shop.get('paid_until'))}"
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


# ---------- Реферальная программа «Пригласи друга» ----------
# Ссылка /r/<код> ставит cookie на REF_COOKIE_DAYS дней и ведёт на /register.
# Заявка запоминает пригласившего, одобренная точка — shops.referred_by.
# Первая подтверждённая оплата приглашённой точки → бонус REF_SHARE_PCT %
# (db.referral_sync). Выплачивает администратор вручную.

_REF_COOKIE = "ob_ref"


def _set_ref_cookie(resp, code):
    resp.set_cookie(_REF_COOKIE, code, max_age=db.REF_COOKIE_DAYS * 86400, samesite="Lax",
                    secure=request.is_secure, httponly=True)


def _ref_link(code) -> str:
    base = PUBLIC_URL.rstrip("/") if PUBLIC_URL else request.host_url.rstrip("/")
    return f"{base}/r/{code}"


def _reg_ref_line(req: dict) -> list:
    if not req.get("ref_shop_id"):
        return []
    ref = db.get_shop(req["ref_shop_id"]) or {}
    return [f"🎁 Пригласил: {ref.get('shop_name') or '—'} (@{ref.get('username') or '?'})"]


def _ref_notify(shop_id, key, **kw):
    shop = db.get_shop(shop_id) if shop_id else None
    if not shop or not shop.get("notify_telegram_id"):
        return
    try:
        _send_telegram_message(shop["notify_telegram_id"], i18n.t(key, shop.get("language") or "ru", **kw))
    except Exception as e:
        logger.error(f"Реферал: сообщение точке {shop_id} не отправлено: {e}")


def _ref_sync(referred_id):
    """Пересчитать бонус после изменения оплат; о новом бонусе — сообщение
    пригласившему и администратору (напоминание перевести деньги)."""
    if not referred_id:
        return
    try:
        r = db.referral_sync(int(referred_id))
    except Exception as e:
        logger.error(f"Реферал: пересчёт бонуса для точки {referred_id} не выполнен: {e}")
        return
    rw = r.get("reward")
    if not r.get("created") or not rw:
        return
    new = db.get_shop(rw["referred_id"]) or {}
    ref = db.get_shop(rw["referrer_id"]) or {}
    _ref_notify(rw["referrer_id"], "ref_bot_reward", shop=new.get("shop_name") or new.get("username") or "—",
                sum=_fmt_sum(rw["reward_amount"]))
    if ADMIN_TELEGRAM_ID:
        card = ref.get("ref_card") or "карта не указана"
        _send_telegram_message(ADMIN_TELEGRAM_ID, "\n".join([
            "🎁 Реферальный бонус к выплате",
            f"Кому: {ref.get('shop_name') or '—'} (@{ref.get('username') or '?'})",
            f"Карта: {card}",
            f"За точку: {new.get('shop_name') or '—'} (@{new.get('username') or '?'})",
            f"Оплата: {_fmt_sum(rw['base_amount'])} сум → бонус {db.ref_pct()}%: {_fmt_sum(rw['reward_amount'])} сум",
            "После перевода нажмите «Выплачено» в админке → Реферальная программа.",
        ]))


@app.route("/r/<code>")
def referral_entry(code):
    referrer = db.find_referrer_by_code(code)
    lang = request.args.get("lang")
    target = "/register" + ("?lang=uz" if lang == "uz" else "")
    resp = redirect(target)
    if referrer:
        _set_ref_cookie(resp, referrer["ref_code"])
    return resp


@app.route("/referral")
@login_required
@sub_exempt
def referral_page():
    if not _is_sub_owner():
        return redirect("/")
    T = g.T
    code = db.get_or_create_ref_code(g.shop_id)
    if not code:
        return redirect("/")
    shop = db.get_shop(g.shop_id) or {}
    data = db.my_referrals(g.shop_id)
    link = _ref_link(code)
    chips = {"request": ("grey", T["ref_st_request"]), "joined": ("blue", T["ref_st_joined"]),
             "paid": ("green", T["ref_st_paid"]), "paid_out": ("dark", T["ref_st_paid_out"])}
    items = []
    for it in data["items"]:
        chip = chips[it["status"]]
        if it["status"] == "paid":
            sub = T["ref_item_wait"].format(sum=_fmt_sum(it["reward"]))
        elif it["status"] == "paid_out":
            sub = T["ref_item_paid"].format(sum=_fmt_sum(it["reward"]), date=_fmt_day(it.get("paid_at")))
        elif it["status"] == "joined":
            sub = T["ref_item_joined"]
        else:
            sub = T["ref_item_request"]
        items.append({"name": it["name"], "date": _fmt_day(it["date"]), "chip": chip, "sub": sub})
    share_text = T["ref_share_text"].format(link=link)
    return render_template_string(
        REFERRAL_PAGE, T=T, lang=g.lang, link=link, code=code, pct=db.ref_pct(),
        share_text=share_text,
        tg_share="https://t.me/share/url?url=" + quote(link, safe="") + "&text=" + quote(
            T["ref_share_text_tg"], safe=""),
        stats=data, pending_txt=_fmt_sum(data["pending"]), paid_txt=_fmt_sum(data["paid_out"]),
        earned_txt=_fmt_sum(data["earned"]), items=items, card=shop.get("ref_card") or "")


@app.route("/api/referral/card", methods=["POST"])
@login_required
@sub_exempt
def api_referral_card():
    if not _is_sub_owner():
        return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
    raw = (request.get_json(force=True, silent=True) or {}).get("card") or ""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if digits and not (12 <= len(digits) <= 19):
        return jsonify({"ok": False, "error": g.T["ref_card_bad"]}), 400
    return jsonify({"ok": True, "card": db.set_ref_card(g.shop_id, digits) or ""})


@app.route("/api/admin/referrals")
@admin_required
def api_admin_referrals():
    return jsonify({"ok": True, **db.admin_referrals()})


@app.route("/api/admin/referrals/<int:reward_id>/paid", methods=["POST"])
@admin_required
def api_admin_referral_paid(reward_id):
    rw = db.admin_mark_reward_paid(reward_id)
    if not rw:
        return jsonify({"ok": False, "error": "бонус уже отмечен или не найден"}), 409
    new = db.get_shop(rw["referred_id"]) or {}
    _ref_notify(rw["referrer_id"], "ref_bot_paid", sum=_fmt_sum(rw["reward_amount"]),
                shop=new.get("shop_name") or new.get("username") or "—")
    return jsonify({"ok": True})


@app.route("/api/admin/shops/<int:shop_id>/referrer", methods=["POST"])
@admin_required
def api_admin_set_referrer(shop_id):
    raw = (request.get_json(force=True, silent=True) or {}).get("referrer_id")
    try:
        ref_id = int(raw) if raw not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "неверная точка"}), 400
    err = db.admin_set_referrer(shop_id, ref_id)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    _ref_sync(shop_id)
    return jsonify({"ok": True})
