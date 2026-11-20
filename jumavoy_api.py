"""Вход для JUMAVOY — личного ИИ-ассистента владельца платформы в Telegram.

JUMAVOY (Supabase Edge Function «ai-bot» в репозитории MitalCRM) спрашивает
здесь то же, что владелец видит в /admin, и выполняет небольшой список
действий. Что важно:

- Доступ только по секретному токену JUMAVOY_TOKEN (переменная Railway,
  не короче 32 символов). Нет токена — адресов /api/jumavoy/* как будто нет (404).
  Неверный токен — запись в журнал безопасности.
- Данные — ровно уровня админки: подписки, оплаты, заявки, общая аналитика.
  Клиентов, машин, замен и выручки точек здесь нет — так обещано в
  соглашении с клиентами (см. tests/test_privacy_admin.py), и поля точки
  отдаются по белому списку.
- Действия — только из списка SHOP_ACTIONS + оплата и заявка. Подтверждение
  кнопкой «✅» спрашивает сам JUMAVOY до вызова; здесь каждое действие пишется
  в журнал безопасности с пометкой JUMAVOY. Удаления, пароли и восстановление
  базы сюда не входят.
"""
import hmac
import os
from datetime import date, datetime

from flask import jsonify, request

import database as db
import security
from registration import reg_decide
from subscription import _admin_sub_summary, _ref_sync, sub_decide
from webapp import _client_ip, _send_telegram_message, app

TOKEN_MIN_LEN = 32

# Поля точки, которые получает JUMAVOY (белый список, а не «всё, кроме»:
# новое поле в shops само сюда не попадёт)
SHOP_FIELDS = ("id", "username", "shop_name", "name", "phone", "address", "client_group", "is_active",
               "created_at", "paid_until", "license_type", "custom_price", "trial", "self_registered",
               "branches", "branches_pending", "monthly", "paid_total", "paid_count", "last_paid",
               "first_paid", "pending", "days_left", "status", "has_tg")
FLAG_FIELDS = ("sms_enabled", "warehouse_enabled", "store_enabled", "tire_enabled", "parts_enabled")
REG_FIELDS = ("id", "shop_name", "owner_name", "city", "phone", "address", "username", "language",
              "tg_username", "tg_name", "status", "created_at", "decided_at")
PAY_FIELDS = ("id", "shop_id", "amount", "months", "kind", "method", "status", "created_at", "decided_at",
              "new_until", "pay_day")
EVENT_FIELDS = ("id", "kind", "severity", "ip", "username", "path", "created_at", "at")
STATUS_RU = {"trial": "пробный период", "paying": "оплачено", "soon": "скоро заканчивается",
             "grace": "просрочено (льготные дни)", "blocked": "заблокирована за неоплату",
             "lifetime": "пожизненная лицензия", "unset": "срок не задан", "off": "отключена"}


def _token():
    t = os.environ.get("JUMAVOY_TOKEN", "").strip()
    return t if len(t) >= TOKEN_MIN_LEN else ""


@app.before_request
def _jumavoy_auth():
    if not request.path.startswith("/api/jumavoy/"):
        return None
    want = _token()
    if not want:
        return jsonify({"ok": False, "error": "not found"}), 404
    got = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(got.encode(), want.encode()):
        security.log_event("jumavoy_bad_token", security.HIGH, ip=_client_ip(), path=request.path)
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


def _pick(row: dict, fields) -> dict:
    return {k: row.get(k) for k in fields if k in row}


def _shop_row(h: dict) -> dict:
    out = _pick(h, SHOP_FIELDS)
    out["status_ru"] = STATUS_RU.get(h.get("status"), h.get("status"))
    return out


def _payment_row(p: dict) -> dict:
    out = _pick(p, PAY_FIELDS)
    shop = db.get_shop(p.get("shop_id")) if p.get("shop_id") else None
    if shop:
        out["shop_name"] = shop.get("shop_name") or shop.get("username")
    out["has_receipt"] = bool(p.get("tg_file_id") or p.get("has_receipt"))
    return out


def _all_heads():
    return db.list_income_shops(status="all", sort="until", page=1, per=10000)


def _find_shop(shop_id=None, q=""):
    """Точка по id или по названию/логину. Возвращает (точка, варианты при неоднозначности)."""
    rows = _all_heads()["rows"]
    if shop_id not in (None, ""):
        try:
            sid = int(shop_id)
        except (TypeError, ValueError):
            return None, []
        return next((h for h in rows if h["id"] == sid), None), []
    q = (q or "").strip().lower()
    if not q:
        return None, []
    exact = [h for h in rows if q in ((h.get("name") or "").lower(), (h.get("username") or "").lower())]
    if len(exact) == 1:
        return exact[0], []
    found = exact or [h for h in rows if q in (h.get("name") or "").lower() or q in (h.get("username") or "").lower()]
    if len(found) == 1:
        return found[0], []
    return None, [{"id": h["id"], "name": h["name"], "username": h["username"]} for h in found[:10]]


def _no_shop(variants):
    if variants:
        return jsonify({"ok": False, "error": "подходят несколько точек — уточните", "variants": variants}), 409
    return jsonify({"ok": False, "error": "точка не найдена"}), 404


def _int(name, default, lo=1, hi=730):
    try:
        return max(lo, min(int(request.args.get(name) or default), hi))
    except ValueError:
        return default


# ---------- чтение ----------

@app.route("/api/jumavoy/summary")
def jv_summary():
    """Короткая сводка для утреннего плана и вопроса «что в OilBook?»."""
    heads = _all_heads()
    rows = heads["rows"]
    today = date.today().isoformat()
    month = db.get_income_overview(today[:8] + "01", today)
    day = db.get_income_overview(today, today)
    soon = sorted([h for h in rows if h.get("days_left") is not None and 0 <= h["days_left"] <= 7
                   and h.get("status") not in ("lifetime", "off")], key=lambda h: h["days_left"])
    overdue = [h for h in rows if h.get("status") in ("grace", "blocked")]
    pend = db.list_sub_payments(status="pending", limit=50)
    regs = db.list_registrations().get("pending") or []
    high = [e for e in security.recent_events(200, "high")
            if str(e.get("created_at") or e.get("at") or "")[:10] == today]
    return jsonify({"ok": True, "date": today, "counts": heads["counts"], "status_ru": STATUS_RU,
                    "mrr": month.get("mrr"),
                    "month": {"from": month["from"], "to": month["to"], "received": month["received"],
                              "payments": month["payments"], "prev_received": month["prev_received"]},
                    "today": {"received": day["received"], "payments": day["payments"]},
                    "expiring_7d": [_shop_row(h) for h in soon],
                    "overdue": [_shop_row(h) for h in overdue],
                    "pending_payments": [_payment_row(p) for p in pend],
                    "pending_registrations": [_pick(r, REG_FIELDS) for r in regs],
                    "security_high_today": len(high)})


@app.route("/api/jumavoy/shops")
def jv_shops():
    data = db.list_income_shops(q=request.args.get("q", ""), status=request.args.get("status") or "all",
                                sort=request.args.get("sort", "until"), page=1, per=_int("limit", 200, 1, 1000))
    return jsonify({"ok": True, "total": data["total"], "counts": data["counts"], "status_ru": STATUS_RU,
                    "sum_monthly": data.get("sum_monthly"), "shops": [_shop_row(h) for h in data["rows"]]})


@app.route("/api/jumavoy/shop")
def jv_shop():
    head, variants = _find_shop(request.args.get("id"), request.args.get("q"))
    if not head:
        return _no_shop(variants)
    shop = db.get_shop(head["id"]) or {}
    inc = db.get_income_shop(head["id"]) or {}
    q = db.sub_quote(head["id"])
    return jsonify({"ok": True, "shop": _shop_row(head), "flags": _pick(shop, FLAG_FIELDS),
                    "telegram_connected": bool(shop.get("notify_telegram_id")),
                    "sub": _admin_sub_summary(shop),
                    "options": [{"months": o["months"], "amount": o["amount"], "discount": o["discount"]}
                                for o in q["options"]],
                    "payments": [_payment_row(p) for p in (inc.get("payments") or [])[:20]],
                    "branches": [{"id": b.get("id"), "name": b.get("shop_name") or b.get("name") or b.get("username"),
                                  "is_active": b.get("is_active")} for b in (inc.get("branches") or [])]})


@app.route("/api/jumavoy/payments")
def jv_payments():
    data = db.list_income_payments(request.args.get("from"), request.args.get("to"),
                                   status=request.args.get("status", "confirmed"), q=request.args.get("q", ""),
                                   page=1, per=_int("limit", 100, 1, 500))
    return jsonify({"ok": True, "total": data["total"], "sum": data["sum"],
                    "payments": [_payment_row(p) for p in data["rows"]]})


@app.route("/api/jumavoy/registrations")
def jv_registrations():
    r = db.list_registrations()
    return jsonify({"ok": True, "pending": [_pick(x, REG_FIELDS) for x in r.get("pending") or []],
                    "done": [_pick(x, REG_FIELDS) for x in r.get("done") or []]})


@app.route("/api/jumavoy/analytics")
def jv_analytics():
    """Та же общая аналитика, что во вкладке админки (без точек и денег точек)."""
    return jsonify({"ok": True, "data": db.get_admin_analytics(_int("days", 30))})


@app.route("/api/jumavoy/security")
def jv_security():
    sev = request.args.get("severity")
    sev = sev if sev in ("low", "medium", "high") else None
    events = security.recent_events(_int("limit", 30, 1, 200), sev)
    return jsonify({"ok": True, "events": [_pick(e, EVENT_FIELDS) for e in events]})


# ---------- действия ----------

def _on(data):
    v = data.get("on")
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "да")
    return bool(v)


def _act_extend(head, data):
    try:
        months = int(data.get("months"))
    except (TypeError, ValueError):
        months = 0
    if months not in db.SUB_TERMS:
        return {"ok": False, "error": f"срок — {', '.join(map(str, db.SUB_TERMS))} мес."}
    q = db.sub_quote(head["id"])
    amount = next((o["amount"] for o in q["options"] if o["months"] == months), None)
    new_until = db.admin_extend_subscription(head["id"], months, amount)
    _ref_sync(head["id"])
    return {"ok": True, "paid_until": new_until, "amount": amount}


def _act_set_until(head, data):
    raw = str(data.get("date") or "").strip()
    day = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            day = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            pass
    if not day:
        return {"ok": False, "error": "дата в формате ГГГГ-ММ-ДД"}
    db.admin_set_paid_until(head["id"], day)
    return {"ok": True, "paid_until": day}


def _act_active(head, data):
    db.set_shop_active(head["id"], _on(data))
    return {"ok": True, "is_active": _on(data)}


def _act_sms(head, data):
    db.set_shop_sms_enabled(head["id"], _on(data))
    return {"ok": True, "sms_enabled": _on(data)}


def _act_warehouse(head, data):
    db.set_shop_warehouse_enabled(head["id"], _on(data))
    return {"ok": True, "warehouse_enabled": _on(data)}


def _act_price(head, data):
    raw = data.get("price")
    if raw in (None, "", 0, "0"):
        price = None
    else:
        txt = "".join(ch for ch in str(raw) if not ch.isspace())
        if not txt.isdigit():
            return {"ok": False, "error": "цена — только цифры (пусто — обычная цена)"}
        price = int(txt) or None
    db.admin_set_custom_price(head["id"], price)
    return {"ok": True, "custom_price": price}


def _act_message(head, data):
    text = str(data.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "пустое сообщение"}
    shop = db.get_shop(head["id"]) or {}
    if not shop.get("notify_telegram_id"):
        return {"ok": False, "error": "у точки не подключён Telegram для уведомлений"}
    _send_telegram_message(shop["notify_telegram_id"], text[:3500])
    return {"ok": True, "sent": True}


SHOP_ACTIONS = {"extend": _act_extend, "set_until": _act_set_until, "active": _act_active, "sms": _act_sms,
                "warehouse": _act_warehouse, "price": _act_price, "message": _act_message}


def _int_field(data, key):
    try:
        return int(data.get(key))
    except (TypeError, ValueError):
        return None


@app.route("/api/jumavoy/action", methods=["POST"])
def jv_action():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "")
    if action == "payment":
        pid, decision = _int_field(data, "payment_id"), data.get("decision")
        if decision not in ("confirm", "reject") or not pid:
            return jsonify({"ok": False, "error": "нужны payment_id и decision: confirm / reject"}), 400
        p = sub_decide(pid, decision == "confirm")
        res = {"ok": True, "new_until": p.get("new_until")} if p else {"ok": False, "error": "этот чек уже обработан"}
        _log(action, None, data, res)
        return jsonify(res), (200 if res["ok"] else 409)
    if action == "registration":
        rid, decision = _int_field(data, "request_id"), data.get("decision")
        if decision not in ("approve", "reject") or not rid:
            return jsonify({"ok": False, "error": "нужны request_id и decision: approve / reject"}), 400
        r = reg_decide(rid, decision == "approve")
        if r.get("ok"):
            res = {"ok": True}
            if r.get("shop"):
                res.update(shop_id=r["shop"]["id"], paid_until=r["shop"].get("paid_until"))
        else:
            res = {"ok": False, "error": {"done": "заявка уже обработана",
                                          "username_taken": "логин уже занят другой точкой — отклоните заявку"
                                          }.get(r.get("error"), "ошибка")}
        _log(action, None, data, res)
        return jsonify(res), (200 if res["ok"] else 400)
    fn = SHOP_ACTIONS.get(action)
    if not fn:
        return jsonify({"ok": False, "error": "неизвестное действие",
                        "actions": sorted(SHOP_ACTIONS) + ["payment", "registration"]}), 400
    head, _ = _find_shop(data.get("shop_id"))
    if not head:
        return jsonify({"ok": False, "error": "точка не найдена (нужен shop_id)"}), 404
    res = fn(head, data)
    res.setdefault("shop", head.get("name"))
    _log(action, head["id"], data, res)
    return jsonify(res), (200 if res.get("ok") else 400)


def _log(action, shop_id, data, res):
    details = {k: v for k, v in data.items() if k in ("months", "date", "on", "price", "decision",
                                                     "payment_id", "request_id")}
    if action == "message":
        details["chars"] = len(str(data.get("text") or ""))
    security.log_event("jumavoy_action", security.LOW, ip=_client_ip(), username="JUMAVOY",
                       path=f"{action} shop={shop_id}", ok=bool(res.get("ok")), **details)
