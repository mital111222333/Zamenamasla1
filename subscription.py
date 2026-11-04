"""Подписка платформы: страница «Подписка», курс доллара для «Безлимита»,
оплата по чеку, автооплата через Hamyon, решения администратора по оплатам
и раздел «Доходы» в админке.

Маршруты регистрируются на общем app из webapp.py при импорте этого файла
(webapp.py импортирует его в самом конце). Нужные остальной программе
функции (sub_decide и др.) webapp.py берёт отсюда обратно."""
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime

import requests
from flask import Response, g, jsonify, render_template_string, request

import database as db
import i18n
from webapp import (
    ADMIN_TELEGRAM_ID, BOT_TOKEN, PUBLIC_URL, _fmt_day, _fmt_sum, _is_sub_owner,
    _send_telegram_message, _tg_api, admin_required, app, logger, login_required,
    sub_exempt,
)
from registration import _ref_sync


# ---------- Курс доллара для тарифа «Безлимит» ----------
# Берём официальный курс ЦБ Узбекистана (обновляем раз в 6 часов). Если сайт
# ЦБ недоступен — последний сохранённый курс. Админ может задать свой курс
# (usd_rate_manual) — тогда используется он.
_CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
_cbu_cache = {"rate": None, "at": 0.0, "tried": 0.0}


def _cbu_usd_rate():
    now = time.time()
    if _cbu_cache["rate"] and now - _cbu_cache["at"] < 6 * 3600:
        return _cbu_cache["rate"]
    if now - _cbu_cache["tried"] > 600:
        _cbu_cache["tried"] = now
        try:
            r = requests.get(_CBU_URL, timeout=6)
            data = r.json()
            row = data[0] if isinstance(data, list) and data else data
            rate = float(str(row.get("Rate")).replace(",", "."))
            if 1000 < rate < 100000:
                _cbu_cache.update(rate=rate, at=now)
                db.set_raw_setting("cbu_usd_rate", rate)
                db.set_raw_setting("cbu_usd_date", row.get("Date") or "")
                return rate
        except Exception as e:
            logger.warning(f"Курс ЦБ не получен: {e}")
    if not _cbu_cache["rate"]:
        try:
            saved = float(db.get_raw_setting("cbu_usd_rate") or 0)
            if saved > 0:
                _cbu_cache.update(rate=saved, at=now - 5.5 * 3600)  # попробуем обновить через 30 мин
        except (TypeError, ValueError):
            pass
    return _cbu_cache["rate"]


def sub_usd_rate():
    """(курс, откуда): свой курс админа или курс ЦБ."""
    manual = int(db.get_platform_settings().get("usd_rate_manual") or 0)
    if manual > 0:
        return float(manual), "manual"
    rate = _cbu_usd_rate()
    return (rate, "cbu") if rate else (None, None)


def _sub_quote(head_id: int) -> dict:
    return db.sub_quote(head_id, usd_rate=sub_usd_rate()[0])


def _sub_ro_ctx():
    """Карточка «Режим просмотра» на месте формы «Замена» (None — всё работает)."""
    st = getattr(g, "sub", None) or {}
    if not st.get("readonly"):
        return None
    T = g.T
    owner = _is_sub_owner()
    ctx = {"owner": owner, "title": T["ro_title_trial"] if st.get("trial") else T["ro_title"],
           "text": T["ro_text"] if owner else T["ro_text_staff"], "offer": ""}
    if owner and st.get("trial"):
        try:
            q = db.sub_quote(st["head_id"])
            if q.get("first_disc") and q.get("first_amount"):
                nb = lambda n: _fmt_sum(n).replace(" ", "\u00a0")  # число не разрывается на две строки
                ctx["offer"] = T["ro_offer"].format(d=q["first_disc"], sum=nb(q["first_amount"]), full=nb(q["monthly"]))
        except Exception as e:
            logger.warning(f"Не удалось посчитать скидку первого месяца: {e}")
    return ctx


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
    elif p["kind"] == "lifetime":
        what = "♾ Безлимит — разовая оплата навсегда"
    else:
        disc = f" (−{p['discount']}%)" if p.get("discount") else ""
        what = f"Продление {p['months']} мес{disc}"
        if p["kind"] == "both":
            what += " + новые филиалы"
    lines = [
        (f"💳 Автооплата №{p['id']}" if p.get("method") == "hamyon" else f"🧾 Оплата подписки №{p['id']}"),
        f"Точка: {name} (@{head.get('username', '')})",
        f"Сеть: {net}",
        f"Что: {what}",
        f"Сумма: {_fmt_sum(p.get('amount'))} сум",
    ]
    if p.get("new_until"):
        lines.append(f"Продлится до: {_fmt_day(p['new_until'])}")
    return "\n".join(lines)




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
        elif p["kind"] == "lifetime":
            text = i18n.t("sub_bot_lifetime", lang)
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
    if approve:
        _ref_sync(p["shop_id"])
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

    q = _sub_quote(g.shop_id)
    settings = q["settings"]
    n = st.get("days_left")
    if st["lifetime"]:
        chip = ("blue", "∞")
    elif st["expired"]:
        chip = ("bad", T["sub_status_readonly"])
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
    # новая точка без курса: годовой срок и «Безлимит» дают обучение в подарок
    try:
        gift = bool(db.course_access(g.shop_id)["locked"])
    except Exception:
        gift = False
    options = []
    for o in q["options"]:
        hero = o["months"] == db.COURSE_GIFT_MONTHS
        full = (q["monthly"] or 0) * o["months"]
        extra = q["branch_part"]["amount"] if q["branch_part"] else 0
        options.append({
            "months": o["months"], "label": T[f"sub_m{o['months']}"], "discount": o["discount"],
            "amount_txt": _fmt_sum(o["amount"]), "until_txt": _fmt_day(o["new_until"]),
            "sub_txt": _sub_option_text(T, o, q["branch_part"]),
            "best": hero, "first": bool(o.get("first")), "hero": hero,
            "full_txt": _fmt_sum(full + extra) if hero and o["discount"] and full + extra > o["amount"] else "",
            "per_month_txt": _fmt_sum(int(round((o["amount"] - extra) / o["months"] / 100.0)) * 100) if o["months"] else "",
            "monthly_txt": _fmt_sum(q["monthly"]) if q.get("monthly") else "",
            "saving_txt": _fmt_sum(o["saving"]) if hero and o.get("saving") else "",
            "months_free": (str(round(o["saving"] / q["monthly"], 1)).replace(".", ",")
                            if hero and o.get("saving") and q.get("monthly") else ""),
            "save_txt": (T["sub_hero_save"].format(sum=_fmt_sum(o["saving"]),
                                                   n=str(round(o["saving"] / q["monthly"], 1)).replace(".", ","))
                         if hero and o.get("saving") and q.get("monthly") else ""),
        })
    # годовой — первым, крупной карточкой; остальные по возрастанию
    options.sort(key=lambda o: (not o["hero"], o["months"]))
    first_txt = ""
    if q.get("first_disc") and q.get("first_amount"):
        first_txt = T["sub_first_text"].format(sum=_fmt_sum(q["first_amount"]), full=_fmt_sum(q["monthly"]))
    checked = 12 if gift else (1 if first_txt else 12)
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
        method = (T["sub_method_cash"] if p.get("method") == "cash"
                  else T["sub_method_auto"] if p.get("method") == "hamyon" else T["sub_method_card"])
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
        expired_title=T["trial_expired_title"] if st.get("trial") else T["sub_expired_title"],
        expired_txt=(T["trial_expired_text"] if st.get("trial") else T["sub_expired_text"]).format(
            date=_fmt_day(st.get("paid_until"))),
        first_disc=q.get("first_disc") or 0, first_txt=first_txt, checked=checked, gift=gift,
        year_disc=next((o["discount"] for o in q["options"] if o["months"] == db.COURSE_GIFT_MONTHS), 0),
        lt_warn=(T["sub_lt_warn"].format(date=_fmt_day(st["paid_until"]))
                 if q.get("lifetime") and not st.get("trial") and st.get("days_left") is not None
                 and st["days_left"] >= 1 else ""),
        lt=q.get("lifetime"), lt_amount_txt=_fmt_sum(q["lifetime"]["amount"]) if q.get("lifetime") else "",
        lt_sub=(T["sub_lt_sub"].format(rate=_fmt_sum(round(q["lifetime"]["rate"])))
                + (" · " + T["sub_lt_branches"].format(n=q["lifetime"]["branches"], usd=q["lifetime"]["usd_branch"])
                   if q["lifetime"]["branches"] else "")) if q.get("lifetime") else "",
        auto=hamyon_enabled(),
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
    q = _sub_quote(g.shop_id)
    if q["state"]["lifetime"]:
        return jsonify({"ok": False, "error": "lifetime"}), 400
    if not q["settings"].get("card_number"):
        return jsonify({"ok": False, "error": T["sub_no_card"]}), 400
    choice = (request.form.get("choice") or "").strip()
    pending_ids = [b["id"] for b in q["pending_branches"]]
    if choice == "lifetime":
        if not q.get("lifetime"):
            return jsonify({"ok": False, "error": "выберите срок"}), 400
        kind, months, amount, discount, new_until = "lifetime", None, q["lifetime"]["amount"], 0, None
    elif choice == "branches":
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


# ---------- Подписка: автооплата через Hamyon API ----------
# Как это работает: точка выбирает срок → мы создаём платёж в Hamyon →
# показываем номер карты и ТОЧНУЮ сумму → человек переводит любым своим
# приложением (Payme, Click, Uzum, банк) → Hamyon видит поступление на карту
# и присылает нам callback (status=paid) → срок продлевается сам.
# В настройках Hamyon (бот @HamyonAPIBot → «Do'kon» → «Hamyon API»):
#   COMPLETE_URL = https://<ваш сайт>/api/hamyon/complete
#   PREPARE_URL  — можно оставить пустым.
# В Render → Environment: HAMYON_SHOP_ID и HAMYON_SHOP_KEY (из @HamyonAPIBot).

HAMYON_BASE = (os.environ.get("HAMYON_BASE_URL") or "https://hamyon-api.uz").rstrip("/")
HAMYON_SHOP_ID = (os.environ.get("HAMYON_SHOP_ID") or "").strip()
HAMYON_SHOP_KEY = (os.environ.get("HAMYON_SHOP_KEY") or "").strip()
_AUTO_TTL = 5 * 60          # сколько Hamyon ждёт перевод
_AUTO_GIVE_UP = 8 * 60      # после этого считаем, что перевода нет (если callback потерялся)
_auto_polls = {}            # payment_id → когда в последний раз спрашивали Hamyon о статусе


def hamyon_enabled() -> bool:
    return bool(HAMYON_SHOP_ID and HAMYON_SHOP_KEY)


def _hy_pick(d, *keys):
    """Достаёт поле из ответа Hamyon: и сверху, и из вложенных data/result/payment."""
    if not isinstance(d, dict):
        return None
    pools = [d] + [d[k] for k in ("data", "result", "payment") if isinstance(d.get(k), dict)]
    for pool in pools:
        for k in keys:
            v = pool.get(k)
            if v not in (None, ""):
                return v
    return None


def _hy_json(resp):
    try:
        d = resp.json()
        return d if isinstance(d, dict) else {"data": d}
    except ValueError:
        return None


def _hy_request(method: str, path: str, payload: dict) -> dict:
    """Запрос к Hamyon. Формат тела в их документации не указан, поэтому
    сначала шлём обычную форму, а если сервер её не понял — JSON."""
    url = HAMYON_BASE + path
    last = {}
    for mode in ("form", "json"):
        try:
            if method == "GET":
                r = requests.get(url, params=payload, timeout=20)
            elif mode == "form":
                r = requests.post(url, data=payload, timeout=20)
            else:
                r = requests.post(url, json=payload, timeout=20)
        except Exception as e:
            logger.warning(f"Hamyon {path}: нет связи — {e}")
            last = {"error": "network"}
            continue
        d = _hy_json(r)
        if d is None:
            logger.warning(f"Hamyon {path}: HTTP {r.status_code} — {r.text[:300]}")
            last = {"error": f"HTTP {r.status_code}"}
            if method == "GET":
                break
            continue
        if method == "POST" and mode == "form" and r.status_code in (400, 415, 422) \
                and not _hy_pick(d, "payment_id"):
            last = d
            continue
        return d
    return last


def _hy_error(d) -> str:
    v = _hy_pick(d, "error", "message", "detail", "msg")
    return str(v) if v and not isinstance(v, bool) else ""


def hamyon_create(amount: int, order_id: str):
    """Создаёт платёж. Если такая сумма у кого-то уже ждёт оплаты (Hamyon
    различает платежи по сумме), добавляем 1–3 сума. Возвращает
    (payment_id, карта, точная сумма) или (None, текст ошибки, None)."""
    err = ""
    for extra in range(0, 4):
        amt = int(amount) + extra
        d = _hy_request("POST", "/payment/create", {
            "shop_id": HAMYON_SHOP_ID, "shop_key": HAMYON_SHOP_KEY,
            "amount": amt, "order_id": order_id})
        pid = _hy_pick(d, "payment_id")
        if pid is None and (_hy_pick(d, "status") in ("ok", "success", True, "pending", "prepare")):
            pid = _hy_pick(d, "id")
        if pid is not None:
            card = _hy_pick(d, "card", "card_number", "cardNumber", "card_num", "pan") or ""
            real = _hy_pick(d, "amount")
            try:
                real = int(float(real)) if real is not None else amt
            except (TypeError, ValueError):
                real = amt
            return str(pid), str(card), real
        err = _hy_error(d) or "error"
        logger.warning(f"Hamyon create {order_id} на {amt}: {d}")
        if err in ("network",) or err.startswith("HTTP 5"):
            break
    return None, err, None


def hamyon_status(ext_id: str) -> str:
    """Статус платежа у Hamyon: 'paid', 'cancel', 'pending'… или '' если не узнали."""
    d = _hy_request("GET", "/payment/status", {
        "payment_id": ext_id, "shop_id": HAMYON_SHOP_ID, "shop_key": HAMYON_SHOP_KEY})
    st = _hy_pick(d, "status", "state")
    return str(st).strip().lower() if st and not isinstance(st, bool) else ""


def hamyon_cancel(ext_id: str):
    try:
        _hy_request("POST", "/payment/cancel", {
            "payment_id": ext_id, "shop_id": HAMYON_SHOP_ID, "shop_key": HAMYON_SHOP_KEY})
    except Exception as e:
        logger.warning(f"Hamyon cancel {ext_id}: {e}")


def _hy_sign_ok(ext_id, amount, sign) -> bool:
    """sign = md5(shop_id + payment_id + amount + shop_key). Как именно Hamyon
    пишет сумму (50000 или 50000.00), в документации не сказано — проверяем
    все обычные варианты."""
    import hashlib
    if not sign or ext_id is None or amount is None:
        return False
    sign = str(sign).strip().lower()
    variants = {str(amount).strip()}
    try:
        f = float(amount)
        variants.update({str(int(f)), f"{f:.2f}", f"{f:.1f}", str(f)})
    except (TypeError, ValueError):
        pass
    for a in variants:
        raw = f"{HAMYON_SHOP_ID}{ext_id}{a}{HAMYON_SHOP_KEY}"
        if secrets.compare_digest(hashlib.md5(raw.encode("utf-8")).hexdigest(), sign):
            return True
    return False


def _auto_paid(p: dict):
    """Оплата засчитана: сообщения владельцу и администратору, реферальный бонус."""
    try:
        notify_sub_decision(p)
    except Exception as e:
        logger.error(f"Не удалось уведомить точку об автооплате {p.get('id')}: {e}")
    if ADMIN_TELEGRAM_ID:
        try:
            until = "навсегда (безлимит)" if p.get("kind") == "lifetime" else f"до {_fmt_day(p.get('new_until'))}"
            _send_telegram_message(ADMIN_TELEGRAM_ID, _sub_admin_caption(p) + f"\n\n✅ Оплачено автоматически — действует {until}")
        except Exception as e:
            logger.warning(f"Не удалось сообщить администратору об автооплате: {e}")
    try:
        _ref_sync(p["shop_id"])
    except Exception as e:
        logger.error(f"Реферальный бонус после автооплаты {p.get('id')}: {e}")


def _sub_pick(q: dict, choice: str):
    """Что оплачивается: (kind, months, amount, discount, new_until) или None."""
    if choice == "lifetime":
        lt = q.get("lifetime")
        return ("lifetime", None, lt["amount"], 0, None) if lt else None
    if choice == "branches":
        if not q["branch_part"]:
            return None
        bp = q["branch_part"]
        return "branches", None, bp["amount"], bp["discount"], bp["until"]
    opt = next((o for o in q["options"] if str(o["months"]) == choice), None)
    if not opt:
        return None
    kind = "both" if q["branch_part"] else "extend"
    return kind, opt["months"], opt["amount"], opt["discount"], opt["new_until"]


def _order_num(order_id):
    m = re.search(r"(\d+)", str(order_id or ""))
    return int(m.group(1)) if m else None


@app.route("/api/subscription/auto", methods=["POST"])
@login_required
@sub_exempt
def api_subscription_auto():
    T = g.T
    if not _is_sub_owner():
        return jsonify({"ok": False, "error": "недоступно для этого аккаунта"}), 403
    if not hamyon_enabled():
        return jsonify({"ok": False, "error": T["sub_auto_err"]}), 400
    q = _sub_quote(g.shop_id)
    if q["state"]["lifetime"]:
        return jsonify({"ok": False, "error": "lifetime"}), 400
    data = request.get_json(silent=True) or request.form
    picked = _sub_pick(q, str(data.get("choice") or "").strip())
    if not picked:
        return jsonify({"ok": False, "error": "выберите срок"}), 400
    kind, months, amount, discount, new_until = picked
    # прежняя неоплаченная автооплата этой точки больше не нужна
    for old in db.list_sub_payments(head_id=g.shop_id, limit=5):
        if old.get("method") == "hamyon" and old["status"] == "auto_wait" and old.get("ext_id"):
            hamyon_cancel(old["ext_id"])
    pid = db.create_auto_payment(g.shop_id, kind, months, amount, discount,
                                 [b["id"] for b in q["pending_branches"]], q["branch_count"], new_until)
    ext_id, card, real = hamyon_create(amount, f"OB{pid}")
    if not ext_id:
        db.cancel_auto_payment(pid, f"hamyon: {card}"[:200])
        return jsonify({"ok": False, "error": T["sub_auto_err"]}), 502
    db.auto_payment_started(pid, ext_id, real)
    card = card or (q["settings"].get("card_number") or "")
    return jsonify({"ok": True, "id": pid, "amount": real, "amount_txt": _fmt_sum(real),
                    "card": card, "holder": q["settings"].get("card_holder") or "", "ttl": _AUTO_TTL})


def _auto_age(p) -> float:
    try:
        return (datetime.now() - datetime.strptime(str(p.get("created_at"))[:19], "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return 0


@app.route("/api/subscription/auto/<int:payment_id>")
@login_required
@sub_exempt
def api_subscription_auto_status(payment_id):
    if not _is_sub_owner():
        return jsonify({"ok": False}), 403
    p = db.get_sub_payment(payment_id)
    if not p or p["shop_id"] != g.shop_id or p.get("method") != "hamyon":
        return jsonify({"ok": False}), 404
    if p["status"] == "auto_wait" and p.get("ext_id"):
        age = _auto_age(p)
        # на случай, если callback от Hamyon до нас не дошёл — раз в 15 секунд
        # сами спрашиваем у них статус
        if age > 20 and time.time() - _auto_polls.get(payment_id, 0) > 15:
            _auto_polls[payment_id] = time.time()
            st = hamyon_status(p["ext_id"])
            if st in ("paid", "success", "completed"):
                done = db.confirm_auto_payment(payment_id)
                if done:
                    _auto_paid(done)
                p = db.get_sub_payment(payment_id)
            elif st in ("cancel", "cancelled", "canceled", "timeout", "expired"):
                db.cancel_auto_payment(payment_id, "timeout")
                p = db.get_sub_payment(payment_id)
        if p["status"] == "auto_wait" and age > _AUTO_GIVE_UP:
            db.cancel_auto_payment(payment_id, "timeout")
            p = db.get_sub_payment(payment_id)
    status = {"confirmed": "paid", "cancelled": "cancel"}.get(p["status"], "wait")
    return jsonify({"ok": True, "status": status, "until": _fmt_day(p.get("new_until")) if p.get("new_until") else ""})


@app.route("/api/subscription/auto/<int:payment_id>/cancel", methods=["POST"])
@login_required
@sub_exempt
def api_subscription_auto_cancel(payment_id):
    if not _is_sub_owner():
        return jsonify({"ok": False}), 403
    p = db.get_sub_payment(payment_id)
    if not p or p["shop_id"] != g.shop_id or p.get("method") != "hamyon":
        return jsonify({"ok": False}), 404
    if p["status"] == "auto_wait" and p.get("ext_id"):
        hamyon_cancel(p["ext_id"])
    db.cancel_auto_payment(payment_id, "user")
    return jsonify({"ok": True})


@app.route("/api/hamyon/complete", methods=["POST", "GET"])
@app.route("/api/hamyon/prepare", methods=["POST", "GET"])
def api_hamyon_callback():
    """Сюда Hamyon сообщает о платеже. Всегда отвечаем 200, иначе он будет
    повторять. Деньги засчитываем, только если подпись верная или сам Hamyon
    подтвердил статус по нашему ключу."""
    data = {}
    js = request.get_json(silent=True)
    if isinstance(js, dict):
        data.update(js)
    data.update(request.form.to_dict())
    data.update(request.args.to_dict())
    ext_id = _hy_pick(data, "payment_id")
    status = str(_hy_pick(data, "status") or "").strip().lower()
    amount = _hy_pick(data, "amount")
    sign = _hy_pick(data, "sign")
    order = _hy_pick(data, "order_id")
    logger.info(f"Hamyon callback {request.path}: payment_id={ext_id} order={order} status={status} amount={amount}")
    if not hamyon_enabled():
        return jsonify({"ok": True})
    p = db.get_auto_payment(ext_id=ext_id, order_id=None if ext_id else _order_num(order))
    if not p and order:
        cand = db.get_auto_payment(order_id=_order_num(order))
        # по номеру заказа ищем, только если у нас ещё нет номера Hamyon или он совпал
        if cand and (not cand.get("ext_id") or str(cand["ext_id"]) == str(ext_id)):
            p = cand
    if not p:
        return jsonify({"ok": True, "note": "unknown payment"})
    if request.path.endswith("/prepare") or status in ("prepare", "pending", "wait", "waiting"):
        return jsonify({"ok": True})
    ext = str(ext_id or p.get("ext_id") or "")
    verified = _hy_sign_ok(ext, amount, sign)
    if status in ("paid", "success", "completed"):
        if not verified:
            # Без верной подписи верим только статусу ЭТОГО ЖЕ платежа у Hamyon:
            # номер должен совпасть с тем, что Hamyon выдал нам при создании.
            # Иначе чужой оплаченный номер (или свой старый) можно было
            # «подставить» к другому заказу и продлить подписку без оплаты.
            own_ext = str(p.get("ext_id") or "")
            if own_ext and ext == own_ext and hamyon_status(own_ext) in ("paid", "success", "completed"):
                verified = True
                amount = None  # сумма в запросе не подписана — берём ожидаемую из нашей записи
        if not verified:
            logger.warning(f"Hamyon: подпись не сошлась, оплату {p['id']} не засчитываем ({data})")
            return jsonify({"ok": False, "error": "sign"})
        try:
            if amount is not None and int(float(amount)) < int(p.get("amount") or 0):
                logger.warning(f"Hamyon: сумма {amount} меньше ожидаемой {p.get('amount')} (оплата {p['id']})")
                if ADMIN_TELEGRAM_ID:
                    _send_telegram_message(ADMIN_TELEGRAM_ID, f"⚠️ Автооплата №{p['id']}: пришло {amount}, "
                                           f"ожидалось {_fmt_sum(p.get('amount'))} — проверьте вручную.")
                return jsonify({"ok": True})
        except (TypeError, ValueError):
            pass
        done = db.confirm_auto_payment(p["id"], amount)
        if done:
            _auto_paid(done)
        return jsonify({"ok": True})
    if status in ("cancel", "cancelled", "canceled", "timeout", "expired"):
        if verified or (ext and hamyon_status(ext) in ("cancel", "cancelled", "canceled", "timeout", "expired")):
            db.cancel_auto_payment(p["id"], str(_hy_pick(data, "reason") or "cancel")[:60])
    return jsonify({"ok": True})


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


# ---------- «Доходы»: обзор, точки, оплаты, массовые действия ----------

def _inc_int(name, default):
    try:
        return int(request.args.get(name) or default)
    except (TypeError, ValueError):
        return default


@app.route("/api/admin/income/overview")
@admin_required
def api_admin_income_overview():
    return jsonify({"ok": True, "data": db.get_income_overview(request.args.get("from"), request.args.get("to"))})


@app.route("/api/admin/income/shops")
@admin_required
def api_admin_income_shops():
    grp = request.args.get("group")
    data = db.list_income_shops(q=request.args.get("q", ""), status=request.args.get("status", "all"),
                                group=grp if grp is not None else None, sort=request.args.get("sort", "until"),
                                page=_inc_int("page", 1), per=_inc_int("per", 50))
    return jsonify({"ok": True, "data": data})


@app.route("/api/admin/income/payments")
@admin_required
def api_admin_income_payments():
    data = db.list_income_payments(request.args.get("from"), request.args.get("to"),
                                   method=request.args.get("method", ""), kind=request.args.get("kind", ""),
                                   status=request.args.get("status", "confirmed"), q=request.args.get("q", ""),
                                   page=_inc_int("page", 1), per=_inc_int("per", 100))
    return jsonify({"ok": True, "data": data})


@app.route("/api/admin/income/shop/<int:shop_id>")
@admin_required
def api_admin_income_shop(shop_id):
    d = db.get_income_shop(shop_id)
    if not d:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    q = db.sub_quote(shop_id)
    d["options"] = [{"months": o["months"], "amount": o["amount"], "discount": o["discount"]} for o in q["options"]]
    return jsonify({"ok": True, "data": d})


@app.route("/api/admin/income/record", methods=["POST"])
@admin_required
def api_admin_income_record():
    """Записать оплату вручную: точка, срок, сумма (можно своя), дата, способ."""
    data = request.get_json(force=True) or {}
    try:
        shop_id = int(data.get("shop_id"))
        months = int(data.get("months"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "выберите точку и срок"}), 400
    shop = db.get_shop(shop_id)
    if not shop or shop.get("role") != "shop":
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    if (shop.get("license_type") or "sub") == "lifetime":
        return jsonify({"ok": False, "error": "у точки бессрочная лицензия — продлевать не нужно"}), 400
    if months < 1 or months > 36:
        return jsonify({"ok": False, "error": "срок — от 1 до 36 месяцев"}), 400
    amount = _parse_admin_sum(data.get("amount"))
    if amount is False:
        return jsonify({"ok": False, "error": "сумма — только цифры"}), 400
    if amount is None:
        q = db.sub_quote(shop_id)
        amount = next((o["amount"] for o in q["options"] if o["months"] == months), None) \
            or db._round_k(q["monthly"] * months)
    day = None
    raw = (data.get("date") or "").strip()
    if raw:
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                day = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
        if not day:
            return jsonify({"ok": False, "error": "дата в формате ДД.ММ.ГГГГ"}), 400
    new_until = db.admin_record_payment(shop_id, months, amount, data.get("note"),
                                        data.get("method") or "cash", day)
    _ref_sync(shop_id)
    return jsonify({"ok": True, "paid_until": new_until, "amount": amount})


@app.route("/api/admin/income/days", methods=["POST"])
@admin_required
def api_admin_income_days():
    data = request.get_json(force=True) or {}
    try:
        shop_id = int(data.get("shop_id"))
        days = int(data.get("days"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "укажите число дней"}), 400
    if not days or abs(days) > 366:
        return jsonify({"ok": False, "error": "от 1 до 366 дней"}), 400
    new_until = db.admin_add_days(shop_id, days)
    if not new_until:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    return jsonify({"ok": True, "paid_until": new_until})


def _inc_send_messages(targets: list, text: str):
    sent = 0
    for t in targets:
        if not t.get("notify_telegram_id"):
            continue
        if _tg_api("sendMessage", {"chat_id": t["notify_telegram_id"], "text": text}):
            sent += 1
        time.sleep(0.06)  # Telegram: не больше ~30 сообщений в секунду
    if ADMIN_TELEGRAM_ID:
        _tg_api("sendMessage", {"chat_id": ADMIN_TELEGRAM_ID,
                                "text": f"📨 Рассылка из «Доходов»: доставлено {sent} из {len(targets)} точек."})


@app.route("/api/admin/income/bulk", methods=["POST"])
@admin_required
def api_admin_income_bulk():
    """Действие сразу для многих точек: продлить, подарить дни, цена, сообщение."""
    data = request.get_json(force=True) or {}
    try:
        ids = [int(x) for x in (data.get("ids") or [])]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "неверный список"}), 400
    ids = list(dict.fromkeys(ids))[:2000]
    if not ids:
        return jsonify({"ok": False, "error": "не выбрано ни одной точки"}), 400
    action = data.get("action")
    shops = {s["id"]: s for s in (db.get_shop(i) for i in ids) if s and s.get("role") == "shop"}
    done, skipped = 0, 0
    if action == "extend":
        try:
            months = int(data.get("months"))
        except (TypeError, ValueError):
            months = 0
        if months not in db.SUB_TERMS:
            return jsonify({"ok": False, "error": "неверный срок"}), 400
        for sid, s in shops.items():
            if (s.get("license_type") or "sub") == "lifetime" or not s.get("is_active"):
                skipped += 1
                continue
            q = db.sub_quote(sid)
            amount = next((o["amount"] for o in q["options"] if o["months"] == months), None)
            db.admin_extend_subscription(sid, months, amount)
            _ref_sync(sid)
            done += 1
    elif action == "days":
        try:
            days = int(data.get("days"))
        except (TypeError, ValueError):
            days = 0
        if not days or abs(days) > 366:
            return jsonify({"ok": False, "error": "от 1 до 366 дней"}), 400
        for sid, s in shops.items():
            if (s.get("license_type") or "sub") == "lifetime":
                skipped += 1
                continue
            db.admin_add_days(sid, days)
            done += 1
    elif action == "price":
        price = _parse_admin_sum(data.get("price"))
        if price is False:
            return jsonify({"ok": False, "error": "цена — только цифры"}), 400
        for sid in shops:
            db.admin_set_custom_price(sid, price)
            done += 1
    elif action == "message":
        text = (data.get("text") or "").strip()
        if len(text) < 2:
            return jsonify({"ok": False, "error": "напишите текст сообщения"}), 400
        targets = db.income_telegram_targets(list(shops))
        with_tg = [t for t in targets if t.get("notify_telegram_id")]
        threading.Thread(target=_inc_send_messages, args=(with_tg, text[:3500]), daemon=True).start()
        return jsonify({"ok": True, "done": len(with_tg), "skipped": len(targets) - len(with_tg), "queued": True})
    else:
        return jsonify({"ok": False, "error": "неизвестное действие"}), 400
    return jsonify({"ok": True, "done": done, "skipped": skipped + (len(ids) - len(shops))})


@app.route("/api/admin/income/export")
@admin_required
def api_admin_income_export():
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    pays = db.list_income_payments(request.args.get("from"), request.args.get("to"), status="all", per=500)
    rows = []
    page = 1
    while True:
        rows += pays["rows"]
        if page >= pays["pages"]:
            break
        page += 1
        pays = db.list_income_payments(request.args.get("from"), request.args.get("to"), status="all", page=page, per=500)
    shops = db.list_income_shops(per=200)
    all_shops = []
    for p in range(1, shops["pages"] + 1):
        all_shops += db.list_income_shops(page=p, per=200, sort="name")["rows"]
    wb = Workbook()
    head_font = Font(name="Arial", bold=True, color="FFFFFF")
    head_fill = PatternFill(start_color="0B1F3A", end_color="0B1F3A", fill_type="solid")

    def sheet(ws, headers, data, widths, money_cols):
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=i, value=h)
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"
        for r_i, vals in enumerate(data, 2):
            for c_i, v in enumerate(vals, 1):
                c = ws.cell(row=r_i, column=c_i, value=v)
                if c_i in money_cols and isinstance(v, (int, float)):
                    c.number_format = "#,##0"
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[chr(64 + i)].width = w

    kinds = {"extend": "продление", "both": "продление + филиалы", "branches": "филиалы", "lifetime": "бессрочная"}
    methods = {"cash": "наличные", "card": "перевод (чек)", "hamyon": "автооплата"}
    stats = {"confirmed": "оплачено", "pending": "на проверке", "rejected": "отклонён", "cancelled": "отменён"}
    ws = wb.active
    ws.title = "Оплаты"
    sheet(ws, ["Дата", "Точка", "Что оплачено", "Месяцев", "Сумма, сум", "Способ", "Статус", "Оплачено до", "Заметка"],
          [[r["day"], r["name"], kinds.get(r["kind"], r["kind"]), r.get("months"), r.get("amount"),
            methods.get(r.get("method") or "card", r.get("method")), stats.get(r["status"], r["status"]),
            r.get("new_until") or "", r.get("note") or ""] for r in rows],
          [12, 28, 20, 9, 14, 16, 13, 13, 30], {5})
    st_names = {"trial": "пробный", "paying": "платит", "soon": "скоро продление", "grace": "льготные дни",
                "blocked": "заблокирована", "lifetime": "бессрочная", "unset": "без даты", "off": "выключена"}
    ws2 = wb.create_sheet("Точки")
    sheet(ws2, ["Точка", "Логин", "Телефон", "Сеть", "Статус", "Оплачено до", "Филиалов", "В месяц, сум",
                "Своя цена", "Всего заплатила, сум", "Последняя оплата"],
          [[h["name"], h["username"], h.get("phone") or "", h.get("client_group") or "", st_names.get(h["status"], h["status"]),
            h.get("paid_until") or "", h["branches"], h["monthly"], h.get("custom_price") or "", h["paid_total"],
            h.get("last_paid") or ""] for h in all_shops],
          [28, 16, 16, 16, 16, 13, 9, 13, 11, 16, 14], {8, 9, 10})
    buf = io.BytesIO()
    wb.save(buf)
    fname = f"oilbook_dohody_{pays['from']}_{pays['to']}.xlsx"
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})


@app.route("/api/admin/sub/settings")
@admin_required
def api_admin_sub_settings():
    origin = (PUBLIC_URL or request.host_url).rstrip("/")
    rate, src = sub_usd_rate()
    st = db.get_platform_settings()
    return jsonify({"ok": True, "settings": st, "auto": hamyon_enabled(),
                    "complete_url": origin + "/api/hamyon/complete",
                    "usd_rate": rate, "usd_src": src,
                    "lt_example": db._round_k(st["lifetime_usd"] * rate) if rate else None})


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
        _ref_sync((db.get_sub_payment(payment_id) or {}).get("shop_id"))
        return jsonify({"ok": True})
    if action == "cancel":
        if not db.admin_cancel_payment(payment_id):
            return jsonify({"ok": False, "error": "оплата не найдена"}), 404
        _ref_sync((db.get_sub_payment(payment_id) or {}).get("shop_id"))
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
        _ref_sync(shop_id)
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
        _ref_sync(shop_id)
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
    _ref_sync((db.get_shop(branch_id) or {}).get("parent_shop_id"))
    return jsonify({"ok": True})


SUB_PAGE = r"""<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0A2540">
<link rel="manifest" href="/static/manifest.json?v=2">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<title>{{ T.sub_title }} · OilBook</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@800&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
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
.gift { display:flex; gap:12px; align-items:flex-start; background:#FFF6D6; border:1.5px solid #F5B700; border-radius:14px; padding:14px 16px; color:#5C4300; font-size:14px; line-height:1.45; }
.gift i { font-size:22px; color:#C98A00; margin-top:2px; }
.gift b { font-size:16px; color:#3D2C00; }
.ltc { font-size:12px; font-weight:700; color:#fff; background:#0B1F3A; padding:2px 8px; border-radius:999px; }
.opt.lt { border-color:#0B1F3A33; }
.opt.hero { display:block; padding:0; border-color:#9CC2F5; }
.opt.hero.sel { border-color:var(--blue); background:#fff; box-shadow:0 6px 18px -8px rgba(29,111,224,.45); }
.hero-in { display:flex; flex-direction:column; padding:12px 14px 6px; }
.hero-badge { align-self:flex-start; font-size:12px; font-weight:700; color:#fff; background:var(--blue); padding:3px 10px; border-radius:999px; margin-bottom:8px; }
.hero-top { display:flex; align-items:center; gap:12px; }
.hero-top .nm { flex:1; font-size:18px; font-weight:800; }
.hero-price { text-align:right; font-family:var(--mono); display:flex; flex-direction:column; }
.hero-price s { font-size:12.5px; color:var(--muted); }
.hero-price b { font-size:18px; font-weight:600; }
.hero-save { margin:10px 0 4px; background:var(--green-bg); color:var(--green); border-radius:10px; padding:8px 10px; font-size:13.5px; font-weight:700; }
.hero-ben { display:flex; gap:10px; align-items:flex-start; padding:9px 0; border-top:1px solid var(--line); font-size:14px; font-weight:600; }
.hero-ben:first-of-type { border-top:0; }
.hero-ben > i { width:20px; text-align:center; color:var(--blue); margin-top:2px; flex:none; }
.hero-ben.gf > i { color:#C27803; }
.hero-ben small { display:block; font-size:12.5px; font-weight:500; color:var(--muted); margin-top:2px; }
.hero-ben em { font-style:normal; font-size:11px; font-weight:800; color:#5C4300; background:#FFE58A; padding:1px 7px; border-radius:999px; margin-left:4px; white-space:nowrap; }
.hero-two { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; margin:10px 0 2px; }
.hb { border-radius:12px; padding:10px 11px; display:flex; flex-direction:column; min-width:0; }
.hb-save { background:var(--green-bg); color:var(--green); }
.hb-gift { background:#FFF4C2; color:#5C4300; }
.hb-h { font-size:10.5px; font-weight:800; letter-spacing:.05em; text-transform:uppercase; opacity:.85; }
.hb-v { font-size:16.5px; font-weight:800; line-height:1.2; margin-top:4px; }
.hb small { font-size:12px; font-weight:600; line-height:1.35; margin-top:5px; opacity:.9; }
.hero-inside { display:flex; flex-direction:column; gap:5px; border-top:1px solid var(--line); margin-top:10px; padding:9px 0 6px; }
.hero-inside span { display:flex; gap:9px; font-size:13.5px; font-weight:600; color:#33415C; line-height:1.35; }
.hero-inside i { color:#C27803; width:16px; text-align:center; margin-top:2px; flex:none; }
.nudge { border:1.5px dashed #E8B64A; background:#FFFBEB; color:#7A4E00; border-radius:12px; padding:9px 12px; font-size:13px; font-weight:600; margin-top:-2px; }
.nudge[hidden] { display:none; }
.lt-gifts { display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }
.lt-gifts span { font-size:11.5px; font-weight:700; color:#5C4300; background:#FFF4C2; padding:2px 8px; border-radius:999px; }
.ltw { font-size:13px; font-weight:600; color:var(--warn); margin-top:2px; line-height:1.35; }
.firstc { font-size:12px; font-weight:700; color:#5C4300; background:#FFE58A; padding:2px 8px; border-radius:999px; }
.howto { display:flex; gap:6px; flex-wrap:wrap; }
.howto span { font-size:12px; font-weight:700; color:#3E4F68; background:#EEF2F7; padding:4px 10px; border-radius:999px; }
.waitbox { display:flex; align-items:center; gap:12px; background:var(--blue-bg); border:1.5px solid #BCD3F5; border-radius:14px; padding:14px 16px; font-size:15px; font-weight:700; color:#0B3A7A; }
.spin { width:22px; height:22px; border-radius:50%; border:3px solid #BCD3F5; border-top-color:var(--blue); animation:spin 0.9s linear infinite; flex:none; }
@keyframes spin { to { transform:rotate(360deg); } }
.timer { margin-left:auto; font-family:var(--mono); font-size:16px; }
.linkbtn { background:none; border:0; color:var(--blue); font:700 15px 'Plus Jakarta Sans', system-ui, sans-serif; padding:12px; cursor:pointer; width:100%; }
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
    {% if st.readonly %}<div class="redbox">{{ T.ro_text_staff }}</div>{% endif %}
  </div>
  {% endif %}
{% else %}
  <div class="body" id="step1">
    {% if st.expired %}<div class="redbox"><b>{{ expired_title }}</b><br>{{ expired_txt }}</div>{% endif %}
    {% if first_txt %}<div class="gift"><i class="fa-solid fa-gift"></i><span>{% if gift %}<b>{{ T.sub_first_title_gift.format(d=first_disc, y=year_disc) }}</b><br>{{ T.sub_first_text_gift }}{% else %}<b>{{ T.sub_first_title.format(d=first_disc) }}</b><br>{{ first_txt }}{% endif %}</span></div>{% endif %}
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
      {% if o.hero %}
      <label class="opt hero" data-opt>
        <input type="radio" name="term" value="{{ o.months }}" data-amount="{{ o.amount_txt }}" data-until="{{ o.until_txt }}"{% if o.months == checked %} checked{% endif %}>
        <span class="hero-in">
          <span class="hero-badge"><i class="fa-solid fa-star"></i> {{ T.sub_best }}{% if o.discount %} · −{{ o.discount }}%{% endif %}</span>
          <span class="hero-top">
            <span class="radio"></span>
            <span class="nm">{{ o.label }}</span>
            <span class="hero-price">{% if o.full_txt %}<s>{{ o.full_txt }}</s>{% endif %}<b>{{ o.amount_txt }}</b></span>
          </span>
          {% if gift %}
          <span class="hero-two">
            <span class="hb hb-save"><span class="hb-h">{{ T.sub_gain1 }}</span><span class="hb-v">{% if o.saving_txt %}−{{ o.saving_txt }} {{ T.sub_sum }}{% else %}−{{ o.discount }}%{% endif %}</span>
              <small>{% if o.months_free %}{{ T.sub_gain1_free.format(n=o.months_free) }}<br>{% endif %}{% if o.monthly_txt and o.discount %}{{ T.sub_hero_month.format(sum=o.per_month_txt, full=o.monthly_txt) }}{% endif %}</small></span>
            <span class="hb hb-gift"><span class="hb-h">{{ T.sub_gain2 }}</span><span class="hb-v">{{ T.sub_gain2_v }}</span>
              <small>{{ T.sub_gain2_sub }}</small></span>
          </span>
          <span class="hero-inside">
            <span><i class="fa-solid fa-check"></i>{{ T.sub_in_1 }}</span>
            <span><i class="fa-solid fa-check"></i>{{ T.sub_in_2 }}</span>
            <span><i class="fa-solid fa-check"></i>{{ T.sub_in_3 }}</span>
            <span><i class="fa-solid fa-bolt"></i>{{ T.sub_in_4 }}</span>
          </span>
          {% else %}
          {% if o.save_txt %}<span class="hero-save"><i class="fa-solid fa-circle-check"></i> {{ o.save_txt }}</span>{% endif %}
          <span class="hero-ben"><i class="fa-solid fa-calendar-check"></i><span>{% if o.monthly_txt and o.discount %}{{ T.sub_hero_month.format(sum=o.per_month_txt, full=o.monthly_txt) }}{% else %}{{ o.sub_txt }}{% endif %}<small>{{ T.sub_hero_fixed }}</small></span></span>
          {% endif %}
        </span>
      </label>
      {% else %}
      <label class="opt" data-opt>
        <input type="radio" name="term" value="{{ o.months }}" data-amount="{{ o.amount_txt }}" data-until="{{ o.until_txt }}"{% if o.months == checked %} checked{% endif %}>
        <span class="radio"></span>
        <span class="mid">
          <span class="nm">{{ o.label }}{% if o.discount %}<span class="disc">−{{ o.discount }}%</span>{% endif %}{% if o.first %}<span class="firstc">🎁 {{ T.sub_first_chip }}</span>{% endif %}</span>
          <span class="sub">{{ o.sub_txt }}{% if gift %} · {{ T.sub_no_course }}{% endif %}</span>
        </span>
        <span class="amt">{{ o.amount_txt }}</span>
      </label>
      {% endif %}
      {% endfor %}
      {% if gift %}<div class="nudge" id="subNudge" hidden><i class="fa-solid fa-circle-info"></i> {{ T.sub_nudge.format(y=year_disc) }}</div>{% endif %}
      {% if lt %}
      <div class="h" style="margin-top:6px;">{{ T.sub_lt_or }}</div>
      <label class="opt lt" data-opt>
        <input type="radio" name="term" value="lifetime" data-amount="{{ lt_amount_txt }}" data-until="∞ {{ T.sub_lt_forever }}">
        <span class="radio"></span>
        <span class="mid">
          <span class="nm">{{ T.sub_lt_title }}<span class="ltc">♾ {{ lt.usd }} $</span></span>
          <span class="sub">{{ lt_sub }}</span>
          {% if gift %}<span class="lt-gifts"><span>+ {{ T.sub_gift_course }}</span><span>+ {{ T.sub_gift_ev }}</span><span>{{ T.sub_lt_never }}</span></span>{% endif %}
          {% if lt_warn %}<span class="ltw">⚠️ {{ lt_warn }}</span>{% endif %}
        </span>
        <span class="amt">{{ lt_amount_txt }}</span>
      </label>
      {% endif %}
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
    <button class="btn" id="payBtn" type="button" onclick="{% if auto %}startAuto(){% else %}showStep(2){% endif %}"></button>
    {% if auto %}<div class="note" style="text-align:center;">{{ T.sub_auto_how }}</div>{% endif %}
  </div>

  {% if auto %}
  <div class="body hidden" id="stepA">
    <div class="opt sel" style="cursor:default;">
      <span class="mid"><span class="nm" id="aWhat"></span><span class="sub" id="aUntil"></span></span>
    </div>
    <div class="h">{{ T.sub_auto_title }}</div>
    <div class="paycard">
      <span class="lbl">{{ T.sub_auto_amount }}</span>
      <div class="row"><span class="num" id="aAmount" style="font-size:26px;"></span>
        <button class="cp" type="button" aria-label="{{ T.sub_copy }}" onclick="copyText(document.getElementById('aAmount').textContent, this)"><i class="fa-regular fa-copy"></i></button></div>
      <span class="lbl" style="margin-top:6px;">{{ T.sub_auto_card }}</span>
      <div class="row"><span class="num" id="aCard"></span>
        <button class="cp" type="button" aria-label="{{ T.sub_copy }}" onclick="copyText(document.getElementById('aCard').textContent, this)"><i class="fa-regular fa-copy"></i></button></div>
      <span class="lbl" id="aHolder" style="font-size:13px;"></span>
    </div>
    <div class="howto"><span>Payme</span><span>Click</span><span>Uzum</span><span>{{ T.sub_auto_bank }}</span></div>
    <div class="note" style="font-size:14px; color:#3E4F68;">{{ T.sub_auto_hint }}</div>
    <div class="waitbox" id="aWait"><span class="spin"></span><span>{{ T.sub_auto_wait }}</span><span class="timer" id="aTimer">5:00</span></div>
    <div class="redbox hidden" id="aTimeout">{{ T.sub_auto_timeout }}</div>
    <div class="err hidden" id="aErr"></div>
    {% if card_number %}<button class="linkbtn" type="button" onclick="manualPay()">{{ T.sub_auto_manual }}</button>{% endif %}
  </div>
  <div class="foot hidden" id="footA">
    <button class="btn hidden" id="aRetry" type="button" onclick="startAuto()"><i class="fa-solid fa-rotate-right"></i><span>{{ T.sub_auto_retry }}</span></button>
    <button class="btn ghost" id="aCancel" type="button" onclick="cancelAuto()">{{ T.sub_auto_cancel }}</button>
  </div>
  <div class="center hidden" id="stepOK">
    <div class="ico green"><i class="fa-solid fa-check"></i></div>
    <h1>{{ T.sub_auto_ok_title }}</h1>
    <p class="p" id="okText"></p>
  </div>
  <div class="foot hidden" id="footOK"><a class="btn" href="/">{{ T.sub_auto_open }}</a></div>
  {% endif %}

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
    const giftOn = {{ 'true' if gift else 'false' }};
    const giftTerm = r.value === '12' || r.value === 'lifetime';
    $('payBtn').textContent = PAY_TPL.replace('{sum}', r.dataset.amount) + (giftOn && giftTerm ? ' · ' + {{ T.sub_pay_gift|tojson }} : '');
    $('newDate').textContent = r.dataset.until;
    // выбрали короткий срок — мягкая подсказка прямо под ним: год выгоднее и с подарком
    const nd = $('subNudge');
    if (nd) {
      const short = ['1', '3', '6'].indexOf(r.value) >= 0;
      nd.hidden = !short;
      if (short) { const lbl = r.closest('label'); if (lbl) lbl.insertAdjacentElement('afterend', nd); }
    }
  }
  document.querySelectorAll('input[name=term]').forEach(i => i.addEventListener('change', refresh));
  refresh();

  window.showStep = function (n) {
    const r = current();
    if (n === 2 && !r) return;
    ['stepA', 'footA', 'stepOK', 'footOK'].forEach(id => { if ($(id)) $(id).classList.add('hidden'); });
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

  // ---------- автооплата ----------
  const A = { starting: {{ T.sub_auto_starting|tojson }}, err: {{ T.sub_auto_err|tojson }},
    ok: {{ T.sub_auto_ok_text|tojson }} };
  let autoId = null, autoTimer = null, autoPoll = null, autoEnd = 0, autoBusy = false;
  function only(ids) {
    ['step1', 'foot1', 'step2', 'foot2', 'step3', 'foot3', 'stepA', 'footA', 'stepOK', 'footOK'].forEach(id => {
      if ($(id)) $(id).classList.toggle('hidden', ids.indexOf(id) === -1);
    });
    const homeBack = document.querySelector('a.back');
    if (homeBack) homeBack.classList.toggle('hidden', ids[0] !== 'step1');
    $('backStep').classList.add('hidden');
    window.scrollTo(0, 0);
  }
  function stopAuto() { clearInterval(autoTimer); clearTimeout(autoPoll); autoTimer = autoPoll = null; }
  function tick() {
    const left = Math.max(0, Math.round((autoEnd - Date.now()) / 1000));
    $('aTimer').textContent = Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
  }
  function showTimeout() {
    $('aWait').classList.add('hidden'); $('aTimeout').classList.remove('hidden');
    $('aRetry').classList.remove('hidden'); $('aCancel').textContent = {{ T.sub_back|tojson }};
  }
  async function poll() {
    if (!autoId) return;
    try {
      const res = await fetch('/api/subscription/auto/' + autoId, { cache: 'no-store' });
      const d = await res.json();
      if (d.ok && d.status === 'paid') {
        stopAuto(); autoId = null;
        $('okText').textContent = A.ok.replace('{date}', d.until || '');
        only(['stepOK', 'footOK']);
        return;
      }
      if (d.ok && d.status === 'cancel') { stopAuto(); showTimeout(); return; }
    } catch (e) {}
    if (Date.now() > autoEnd + 3 * 60 * 1000) { stopAuto(); showTimeout(); return; }
    autoPoll = setTimeout(poll, 4000);
  }
  window.startAuto = async function () {
    const r = current();
    if (!r || autoBusy) return;
    autoBusy = true; stopAuto();
    const btn = $('payBtn'); const old = btn.textContent;
    btn.disabled = true; btn.textContent = A.starting;
    if ($('aRetry')) { $('aRetry').disabled = true; }
    try {
      const res = await fetch('/api/subscription/auto', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ choice: r.value }) });
      let d = {};
      try { d = await res.json(); } catch (e) {}
      if (res.status === 401) { location.href = '/login'; return; }
      if (!res.ok || !d.ok) {
        if ($('step2') && $('receipt')) { manualPay(); $('payErr').textContent = d.error || A.err; $('payErr').classList.remove('hidden'); }
        else { alert(d.error || A.err); }
        return;
      }
      autoId = d.id;
      const lbl = r.closest('label').querySelector('.nm');
      $('aWhat').textContent = (r.value === 'branches' ? L.branches : lbl.childNodes[0].textContent.trim()) + ' · ' + r.dataset.amount;
      $('aUntil').textContent = L.until + ': ' + r.dataset.until;
      $('aAmount').textContent = d.amount_txt;
      $('aCard').textContent = String(d.card || '').replace(/[^0-9]/g, '').replace(/(.{4})/g, '$1 ').trim();
      $('aHolder').textContent = d.holder || '';
      $('aWait').classList.remove('hidden'); $('aTimeout').classList.add('hidden');
      $('aRetry').classList.add('hidden'); $('aCancel').textContent = {{ T.sub_auto_cancel|tojson }};
      autoEnd = Date.now() + (d.ttl || 300) * 1000;
      tick(); autoTimer = setInterval(tick, 1000);
      only(['stepA', 'footA']);
      autoPoll = setTimeout(poll, 4000);
    } catch (e) {
      alert(A.err);
    } finally {
      autoBusy = false; btn.disabled = false; btn.textContent = old;
      if ($('aRetry')) { $('aRetry').disabled = false; }
    }
  };
  window.cancelAuto = function () {
    const id = autoId; stopAuto(); autoId = null;
    if (id) fetch('/api/subscription/auto/' + id + '/cancel', { method: 'POST' }).catch(() => {});
    showStep(1);
  };
  window.manualPay = function () {
    const id = autoId; stopAuto(); autoId = null;
    if (id) fetch('/api/subscription/auto/' + id + '/cancel', { method: 'POST' }).catch(() => {});
    showStep(2);
  };
  document.addEventListener('visibilitychange', () => {
    // вернулись из приложения банка — сразу проверяем, дошли ли деньги
    if (!document.hidden && autoId) { clearTimeout(autoPoll); poll(); }
  });

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
