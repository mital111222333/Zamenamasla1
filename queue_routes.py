"""«Машина готова» и живая очередь.

Мастер ставит машину в очередь (ждёт → в работе → готово → забрали).
Клиент получает ссылку /q/<токен>: своё место и примерное время, страница
обновляется сама. Когда мастер жмёт «Готово» — клиенту сообщение в Telegram
(если он подключён к боту), иначе мастер отправляет его в WhatsApp кнопкой.
На табло в зале — вся очередь, только номера (без имён и телефонов).

Маршруты регистрируются на общем app из webapp.py при импорте этого файла
(webapp.py импортирует его в самом конце)."""
import json
import threading

from flask import g, jsonify, render_template_string, request

import database as db
import i18n
from webapp import PUBLIC_URL, _send_telegram_message, app, login_required, logger

QUEUE_FIELDS = ("id", "plate", "what", "car_label", "owner_name", "owner_phone", "status",
                "position", "eta_min", "created_at", "started_at", "done_at")


def _origin():
    return (PUBLIC_URL or request.host_url).rstrip("/")


def _shop_texts(shop):
    return i18n.get_texts((shop or {}).get("language") or "ru")


def _q_out(r: dict) -> dict:
    out = {k: r.get(k) for k in QUEUE_FIELDS}
    out["has_tg"] = bool(r.get("telegram_id"))
    out["link"] = f"{_origin()}/q/{r['token']}"
    return out


def _q_text(kind: str, shop: dict, r: dict, link: str) -> str:
    T = _shop_texts(shop)
    name = shop.get("shop_name") or "OilBook"
    if kind == "ready":
        return T["q_msg_ready"].format(shop=name, plate=r["plate"])
    pos = r.get("position") or 1
    return T["q_msg_added"].format(shop=name, plate=r["plate"], pos=pos, min=r.get("eta_min") or "—", link=link)


def _tg_bg(chat_id, text):
    def run():
        try:
            _send_telegram_message(chat_id, text)
        except Exception as e:  # не критично: мастер может отправить в WhatsApp
            logger.warning(f"queue tg: {e}")
    threading.Thread(target=run, daemon=True).start()


def _with_position(shop_id: int, qid: int):
    return next((x for x in db.queue_list(shop_id) if x["id"] == qid), None) or db.queue_get(shop_id, qid)


@app.route("/api/queue")
@login_required
def api_queue_list():
    shop = db.get_shop(g.shop_id) or {}
    out = {"ok": True, "items": [_q_out(r) for r in db.queue_list(g.shop_id)],
           "avg_min": db.queue_avg_minutes(g.shop_id)}
    if not g.is_employee and shop.get("anpr_token"):
        out["display_url"] = f"{_origin()}/display/{shop['anpr_token']}"
    return jsonify(out)


@app.route("/api/queue", methods=["POST"])
@login_required
def api_queue_add():
    data = request.get_json(force=True) or {}
    try:
        r = db.queue_add(g.shop_id, data.get("plate"), data.get("what") or "", employee_id=g.employee_id)
    except ValueError:
        return jsonify({"ok": False, "error": g.T["q_err_plate"]}), 400
    r = _with_position(g.shop_id, r["id"]) if not r.get("duplicate") else {**r, "duplicate": True}
    out = _q_out(r)
    out["duplicate"] = bool(r.get("duplicate"))
    out["tg_sent"] = False
    if r.get("telegram_id") and not r.get("duplicate"):
        _tg_bg(r["telegram_id"], _q_text("added", db.get_shop(g.shop_id) or {}, r, out["link"]))
        out["tg_sent"] = True
    return jsonify({"ok": True, "item": out})


@app.route("/api/queue/<int:qid>", methods=["POST"])
@login_required
def api_queue_status(qid):
    data = request.get_json(force=True) or {}
    try:
        r = db.queue_set_status(g.shop_id, qid, data.get("status"))
    except ValueError:
        return jsonify({"ok": False, "error": "bad status"}), 400
    if not r:
        return jsonify({"ok": False, "error": "not found"}), 404
    out = _q_out(r)
    out["tg_sent"] = False
    if r.get("just_done") and r.get("telegram_id"):
        _tg_bg(r["telegram_id"], _q_text("ready", db.get_shop(g.shop_id) or {}, r, out["link"]))
        out["tg_sent"] = True
    return jsonify({"ok": True, "item": out})


@app.route("/api/queue/<int:qid>", methods=["DELETE"])
@login_required
def api_queue_delete(qid):
    if not db.queue_delete(g.shop_id, qid):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


# ---------- страница клиента ----------

def _client_state(token):
    st = db.queue_by_token(token)
    if not st:
        return None, None
    shop = db.get_shop(st["shop_id"]) or {}
    st.pop("shop_id", None)
    return st, shop


@app.route("/api/q/<token>")
def api_q_client(token):
    st, shop = _client_state(token)
    if not st:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True, **st})


@app.route("/q/<token>")
def q_client_page(token):
    st, shop = _client_state(token)
    lang = request.args.get("lang") if request.args.get("lang") in ("ru", "uz") else ((shop or {}).get("language") or "ru")
    T = i18n.get_texts(lang)
    if not st:
        return render_template_string(Q_PAGE, T=T, lang=lang, missing=True, token=token, shop={}, state_json="null"), 404
    return render_template_string(
        Q_PAGE, T=T, lang=lang, missing=False, token=token, tq={k: v for k, v in T.items() if k.startswith("q_page")},
        shop={"name": shop.get("shop_name") or "", "phone": shop.get("phone") or "", "address": shop.get("address") or ""},
        state_json=json.dumps(st, ensure_ascii=False),
    )


# ---------- табло в зале ----------

@app.route("/api/display_queue/<anpr_token>")
def api_display_queue(anpr_token):
    shop = db.get_shop_by_anpr_token(anpr_token)
    if not shop or not shop["is_active"]:
        return jsonify({"items": []})
    items = [{"plate": r["plate"], "status": r["status"], "position": r.get("position"), "eta_min": r.get("eta_min")}
             for r in db.queue_list(shop["id"])]
    return jsonify({"items": items})


Q_PAGE = """<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>{{ T.q_page_title }}{% if shop.name %} · {{ shop.name }}{% endif %}</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system, 'Segoe UI', Roboto, sans-serif; background:#EEF4FB; color:#0C2B4F; min-height:100vh;
         display:flex; justify-content:center; padding:20px 16px 40px; }
  .wrap { width:100%; max-width:420px; }
  .shop { text-align:center; font-weight:800; font-size:20px; margin:6px 0 2px; }
  .addr { text-align:center; font-size:13px; color:#4A6A8C; margin-bottom:16px; }
  .card { background:#fff; border-radius:22px; padding:22px 18px; text-align:center; box-shadow:0 6px 24px rgba(12,43,79,.08); }
  .plate { display:inline-block; font-family:ui-monospace, Menlo, monospace; font-weight:700; font-size:22px; letter-spacing:2px;
           border:2.5px solid #111; border-radius:8px; padding:4px 12px; background:#fff; color:#111; }
  .st { font-size:15px; color:#4A6A8C; margin-top:18px; }
  .big { font-size:64px; font-weight:800; line-height:1.05; margin:4px 0; color:#185FA5; }
  .big.small { font-size:30px; }
  .eta { font-size:17px; font-weight:600; }
  .what { font-size:14px; color:#4A6A8C; margin-top:10px; }
  .done .big { color:#0F8A5F; }
  .bar { height:8px; border-radius:4px; background:#E2ECF7; overflow:hidden; margin:18px 0 4px; }
  .bar i { display:block; height:100%; background:#378ADD; border-radius:4px; transition:width .6s; }
  .done .bar i { background:#1D9E75; }
  .note { font-size:12.5px; color:#6B86A3; text-align:center; margin-top:14px; line-height:1.45; }
  .call { display:block; text-align:center; margin-top:14px; padding:14px; border-radius:999px; background:#185FA5; color:#fff;
          font-weight:700; text-decoration:none; font-size:16px; }
  .lang { text-align:center; margin-top:16px; font-size:13px; }
  .lang a { color:#185FA5; margin:0 6px; }
  .brand { text-align:center; font-size:12px; color:#8AA3BD; margin-top:18px; }
</style>
</head>
<body>
<div class="wrap">
  {% if shop.name %}<div class="shop">{{ shop.name }}</div>{% endif %}
  {% if shop.address %}<div class="addr">{{ shop.address }}</div>{% endif %}
  <div class="card" id="card">
    {% if missing %}<div class="st">{{ T.q_page_missing }}</div>{% endif %}
  </div>
  <div class="note">{{ T.q_page_note }}</div>
  {% if shop.phone %}<a class="call" href="tel:{{ shop.phone }}">{{ T.q_page_call }}</a>{% endif %}
  <div class="lang"><a href="?lang=uz">O'zbekcha</a>·<a href="?lang=ru">Русский</a></div>
  <div class="brand">OilBook</div>
</div>
{% if not missing %}
<script>
const T = {{ tq|tojson }};
const TOKEN = {{ token|tojson }};
let S = {{ state_json|safe }};
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function render() {
  const card = document.getElementById('card');
  let main = '', pct = 10;
  if (S.status === 'wait') {
    main = `<div class="st">${esc(T.q_page_pos)}</div><div class="big">${S.position || 1}</div>`
      + (S.eta_min ? `<div class="eta">${esc(T.q_page_eta.replace('{min}', S.eta_min))}</div>` : '');
    pct = Math.max(8, 40 - (S.position || 1) * 8);
  } else if (S.status === 'work') {
    main = `<div class="st">${esc(T.q_page_now)}</div><div class="big small">${esc(T.q_page_work)}</div>`
      + (S.eta_min ? `<div class="eta">${esc(T.q_page_eta.replace('{min}', S.eta_min))}</div>` : '');
    pct = 70;
  } else if (S.status === 'done') {
    main = `<div class="big small">✅ ${esc(T.q_page_ready)}</div><div class="eta">${esc(T.q_page_ready_sub)}</div>`;
    pct = 100;
  } else {
    main = `<div class="big small">${esc(T.q_page_gone)}</div>`;
    pct = 100;
  }
  card.className = 'card' + (S.status === 'done' || S.status === 'gone' ? ' done' : '');
  card.innerHTML = `<div class="plate">${esc(S.plate)}</div>${main}<div class="bar"><i style="width:${pct}%"></i></div>`
    + (S.what ? `<div class="what">${esc(S.what)}</div>` : '');
  document.title = (S.status === 'done' ? '✅ ' : '') + T.q_page_title;
}
async function tick() {
  try {
    const r = await fetch('/api/q/' + encodeURIComponent(TOKEN), { cache: 'no-store' });
    if (r.ok) {
      const d = await r.json();
      const was = S.status;
      S = d;
      render();
      if (was !== 'done' && d.status === 'done' && navigator.vibrate) navigator.vibrate([200, 100, 200]);
    }
  } catch (e) {}
}
render();
setInterval(tick, 10000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
</script>
{% endif %}
</body>
</html>
"""
