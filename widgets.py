"""Интерактивные сообщения Telegram (Bot API 10.4, «виджеты»): напоминание о
замене масла приходит в чат живой карточкой — полоса срока и кнопки
«Записаться», «Уже заменил», «Через неделю» прямо внутри сообщения.

Как это устроено:
- sendWidget присылает HTML-карточку; её состояние (chat_data, до 1 КБ) задаёт
  только бот;
- нажатие в карточке приходит боту как update «widget_query», бот отвечает
  answerWidgetQuery и меняет карточку через editMessageWidgetData.
Внутри карточки нет интернета (fetch запрещён), поэтому всё, что она
показывает, лежит в chat_data, а тексты — в самом HTML на языке клиента.

Если Telegram не принял виджет (старый клиент, ограничение API) — бот сам
отправляет обычное текстовое напоминание с кнопками, как раньше."""
import json
import logging
import zlib

import requests

import i18n

logger = logging.getLogger(__name__)

HTML_MAX = 32768          # байт HTML
HTML_ZMAX = 4096          # байт после сжатия zlib -9
DATA_MAX = 1024           # байт chat_data

_HTML = """<style>
*{box-sizing:border-box;margin:0}
body{font:14px -apple-system,system-ui,sans-serif;color:#fff;background:transparent}
.c{border-radius:18px;padding:14px;background:linear-gradient(140deg,#2A6CF5,#0B2F8A)}
.r{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.m{font-size:12px;opacity:.8}.p{font-size:19px;font-weight:800;letter-spacing:.5px;margin-top:2px}
.w{font-weight:800;font-size:13px}.w i{font-style:normal;opacity:.6}
.l{display:flex;justify-content:space-between;font-size:12px;margin:14px 0 6px}.l b{font-size:14px}
.b{height:8px;border-radius:8px;background:rgba(255,255,255,.22);overflow:hidden}
.b u{display:block;height:100%;border-radius:8px;background:linear-gradient(90deg,#4ADE80,#FACC15 70%,#FB923C)}
.b u.x{background:linear-gradient(90deg,#FB923C,#F43F5E)}
.i{font-size:12px;opacity:.85;margin-top:8px;line-height:1.45}
.k{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:12px}
button{border:0;border-radius:12px;padding:10px 4px;font-weight:700;font-size:13px;font-family:inherit;color:#0B2F8A;background:#fff;cursor:pointer}
button.g{background:rgba(255,255,255,.16);color:#fff}button.f{grid-column:1/3}
.s{margin-top:12px;border-radius:12px;padding:10px;background:rgba(255,255,255,.16);font-weight:700;text-align:center}
</style><div class="c" id="a"></div><script>
var T=__T__,W=window.TelegramWidget,a=document.getElementById('a'),busy=0;
function D(){try{return JSON.parse(W&&W.chatData||'{}')}catch(e){return{}}}
function n(x){return String(Math.round(x)).replace(/(\\d)(?=(\\d{3})+$)/g,'$1 ')}
function e(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML}
function go(k){if(busy||!W)return;var d=D();busy=1;draw();W.request(k+':'+d.id+':'+(d.k||'o')+(d.demo?':d':'')).then(function(){busy=0},function(){busy=0;draw()})}
function draw(){var d=D(),r=d.r==null?null:d.r,due=r!=null&&r>=1,pc=r==null?0:Math.max(4,Math.min(100,Math.round(r*100)));
var big=due?T.now:(d.kl!=null?n(d.kl)+' '+T.km:(d.dl!=null?d.dl+' '+T.d:'—'));
var h='<div class="r"><div><div class="m">'+e(d.md||'')+'</div><div class="p">'+e(d.pl||'')+'</div></div><div class="w">Oil<i>Book</i></div></div>';
h+='<div class="l"><span>'+T.until+'</span><b>'+big+'</b></div><div class="b"><u class="'+(due?'x':'')+'" style="width:'+pc+'%"></u></div>';
var inf=[];if(d.ld)inf.push(T.last+': '+e(d.ld)+(d.lk?' · '+n(d.lk)+' '+T.km:''));if(d.oil)inf.push(T.oil+': '+e(d.oil));if(d.sh)inf.push('📍 '+e(d.sh));
if(inf.length)h+='<div class="i">'+inf.join('<br>')+'</div>';
if(d.st)h+='<div class="s">'+(T['s_'+d.st]||'').replace('{shop}',e(d.sh||''))+'</div>';
else if(busy)h+='<div class="s">…</div>';
else h+='<div class="k"><button class="f" data-k="book">📅 '+T.book+'</button><button class="g" data-k="changed">✅ '+T.changed+'</button><button class="g" data-k="snooze">⏰ '+T.snooze+'</button></div>';
a.innerHTML=h;var bs=a.querySelectorAll('button');for(var i=0;i<bs.length;i++)bs[i].addEventListener('click',function(){go(this.getAttribute('data-k'))})}
if(W&&W.onEvent)W.onEvent('chatDataChanged',draw);draw();
</script>"""

_TEXT_KEYS = {
    "until": "wg_until", "now": "wg_now", "km": "km_unit", "d": "wg_days", "last": "rem_card_last",
    "oil": "rem_card_oil", "book": "wg_book", "changed": "wg_changed", "snooze": "wg_snooze",
    "s_book": "wg_s_book", "s_changed": "wg_s_changed", "s_snooze": "wg_s_snooze",
}


def widget_html(lang: str) -> str:
    texts = {k: i18n.t(v, lang) for k, v in _TEXT_KEYS.items()}
    return _HTML.replace("__T__", json.dumps(texts, ensure_ascii=False))


def html_fits(lang: str) -> bool:
    raw = widget_html(lang).encode("utf-8")
    return len(raw) <= HTML_MAX and len(zlib.compress(raw, 9)) <= HTML_ZMAX


def _fmt_date(s):
    p = str(s or "")[:10].split("-")
    return f"{p[2]}.{p[1]}.{p[0]}" if len(p) == 3 else (s or None)


def reminder_data(item: dict, card: dict, kinds: str, demo: bool = False) -> dict:
    """chat_data карточки (держим в 1 КБ). id/k — какая запись и о чём
    напоминание: по ним бот выполняет нажатие, проверив, что жмёт сам клиент."""
    car = " ".join(x for x in (item.get("car_brand"), item.get("car_model")) if x)
    data = {
        "id": item.get("id"), "k": kinds, "pl": item.get("plate_number") or "", "md": car[:40],
        "r": round(card["ratio"], 3) if card.get("ratio") is not None else None,
        "kl": card.get("km_left"), "dl": card.get("days_left"),
        "ld": _fmt_date(card.get("last_date")), "lk": card.get("last_mileage"),
        "oil": (card.get("oil") or "")[:40] or None, "sh": (item.get("shop_name") or "")[:40] or None,
    }
    if demo:
        data["demo"] = 1
    data = {k: v for k, v in data.items() if v not in (None, "")}
    while len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > DATA_MAX and data.get("oil"):
        data.pop("oil")
    return data


def _call(token: str, method: str, payload: dict):
    """Прямой вызов Bot API (python-telegram-bot 21 ещё не знает этих методов).
    Возвращает (ok, result_or_description)."""
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=20)
        body = r.json()
    except Exception as e:  # сеть, не-JSON
        return False, str(e)
    if body.get("ok"):
        return True, body.get("result")
    return False, body.get("description") or f"HTTP {r.status_code}"


def send_reminder_widget(token: str, chat_id, lang: str, data: dict, caption: str, garage_url: str = None):
    """Отправить карточку-напоминание. С кнопкой «Мой гараж» под ней, если
    Telegram её примет; иначе — без неё. Возвращает (сообщение, None) или
    (None, причина отказа Telegram)."""
    payload = {
        "chat_id": chat_id, "html": widget_html(lang), "allow_queries": True,
        "chat_data": json.dumps(data, ensure_ascii=False), "caption": caption[:1024],
        "width": 360, "height": 300,
    }
    if garage_url:
        with_btn = dict(payload, reply_markup={"inline_keyboard": [[
            {"text": i18n.t("btn_open_garage", lang), "web_app": {"url": garage_url}}]]})
        ok, res = _call(token, "sendWidget", with_btn)
        if ok:
            return res, None
        logger.info(f"Виджет с кнопкой не принят ({res}) — пробуем без кнопки")
    ok, res = _call(token, "sendWidget", payload)
    if ok:
        return res, None
    logger.warning(f"Виджет-напоминание не отправлено: {res}")
    return None, res


def answer_query(token: str, query_id: str, text: str = None):
    payload = {"widget_query_id": query_id}
    if text:
        payload["data"] = text[:1000]
    return _call(token, "answerWidgetQuery", payload)


def set_state(token: str, chat_id, message_id, data: dict):
    return _call(token, "editMessageWidgetData", {
        "chat_id": chat_id, "message_id": message_id, "chat_data": json.dumps(data, ensure_ascii=False)})
