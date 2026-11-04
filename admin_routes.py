"""Админ-панель платформы: страница /admin, справка, точки, филиалы,
сотрудники, резервные копии.

Маршруты регистрируются на общем app из webapp.py при импорте этого файла
(webapp.py импортирует его в самом конце, когда всё остальное уже готово).
Оплаты, доходы, заявки на регистрацию и рефералы пока остаются в webapp.py
рядом со своими разделами."""
import secrets

from flask import jsonify, render_template_string, request

import database as db
import help_content
import i18n
from subscription import _admin_sub_summary
from webapp import (
    ADMIN_PAGE, ADMIN_TELEGRAM_ID, BOT_USERNAME, HELP_CSS, HELP_JS, HELP_VIEW,
    _client_link, _create_and_send_backup, _restore_from_backup,
    _send_telegram_message, admin_required, app,
)


@app.route("/admin")
@admin_required
def admin_page():
    return render_template_string(ADMIN_PAGE, T=i18n.get_texts("ru"))


ADMIN_HELP_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Справка администратора — OilBook</title>
<link rel="icon" href="/static/icons/icon-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
<style>
  :root { --bg:#F1F5F9; --text:#1E293B; --hint:#94A3B8; --blue:#0F52BA; --darkblue:#0A2540; --border:#E2E8F0;
          --font-display:'Space Grotesk', sans-serif; --font-body:'Plus Jakarta Sans', -apple-system, sans-serif; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:var(--font-body); }
  .wrap { max-width:760px; margin:0 auto; padding:14px 14px 30px; padding-top:calc(14px + env(safe-area-inset-top, 0px)); }
  .back { display:inline-flex; align-items:center; gap:8px; color:var(--blue); font-weight:600; text-decoration:none; font-size:14px; margin:2px 0 12px; }
""" + HELP_CSS + """
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/admin"><i class="fa-solid fa-arrow-left"></i> Назад в админ-панель</a>
  <div id="view-help">
""" + HELP_VIEW + """
  </div>
</div>
""" + HELP_JS + """
</body>
</html>
"""


@app.route("/admin/help")
@admin_required
def admin_help_page():
    T = dict(i18n.get_texts("ru"))
    T["tab_help"] = "Справка администратора"
    return render_template_string(
        ADMIN_HELP_PAGE, T=T, help_sections=help_content.build_admin(),
        help_role="администратор платформы", help_support="", help_support_url="")


@app.route("/api/admin/shops")
@admin_required
def api_admin_shops():
    shops = db.list_shops()
    for s in shops:
        s["owner_link"] = _client_link(f"owner_{s['owner_link_token']}") if s.get("owner_link_token") else None
        s["sub"] = _admin_sub_summary(s)
    return jsonify(shops)


@app.route("/api/admin/map")
@admin_required
def api_admin_map():
    """Карта точек: координаты, статус и аналитика за период (по умолчанию 30 дней)."""
    try:
        days = int(request.args.get("days") or 30)
    except ValueError:
        days = 30
    return jsonify(db.get_map_points(days))


@app.route("/api/admin/analytics")
@admin_required
def api_admin_analytics():
    """Аналитика продаж всех точек: товары, бренды, цены продажи и закупки."""
    try:
        days = int(request.args.get("days") or 30)
    except ValueError:
        days = 30
    return jsonify(db.get_admin_analytics(days))


def _int_arg(name, default):
    try:
        return max(1, min(int(request.args.get(name) or default), 730))
    except ValueError:
        return default


@app.route("/api/admin/names")
@admin_required
def api_admin_names():
    """«Сопоставление»: нераспознанные, исправленные автоматически и подтверждённые названия."""
    return jsonify(db.get_name_review(_int_arg("days", 365)))


@app.route("/api/admin/names", methods=["POST"])
@admin_required
def api_admin_names_save():
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "нечего сохранять"}), 400
    n = db.save_name_aliases(items[:500])
    return jsonify({"ok": True, "saved": n})


@app.route("/api/admin/names/delete", methods=["POST"])
@admin_required
def api_admin_names_delete():
    data = request.get_json(force=True) or {}
    ok = db.delete_name_alias(str(data.get("raw") or ""))
    return jsonify({"ok": ok})


@app.route("/api/admin/price_problems")
@admin_required
def api_admin_price_problems():
    """Подозрительные цены продажи/закупки за период."""
    return jsonify(db.get_price_problems(_int_arg("days", 90)))


@app.route("/api/admin/shops/<int:shop_id>/snapshot")
@admin_required
def api_admin_shop_snapshot(shop_id):
    """Копия статистики брендов и склада одной точки — для окна на карте."""
    data = db.get_admin_shop_snapshot(shop_id, _int_arg("days", 30))
    if not data:
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    return jsonify(data)


@app.route("/api/admin/shops/<int:shop_id>/location", methods=["POST"])
@admin_required
def api_admin_set_location(shop_id):
    """Поставить точку/филиал на карту (или убрать с карты — пустые lat/lon)."""
    data = request.get_json(force=True) or {}
    lat, lon = data.get("lat"), data.get("lon")
    if lat in (None, "") and lon in (None, ""):
        lat = lon = None
    else:
        try:
            lat, lon = round(float(lat), 6), round(float(lon), 6)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "неверные координаты"}), 400
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return jsonify({"ok": False, "error": "координаты вне допустимого диапазона"}), 400
    if not db.set_shop_location(shop_id, lat, lon):
        return jsonify({"ok": False, "error": "точка не найдена"}), 404
    return jsonify({"ok": True, "lat": lat, "lon": lon})


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
    # большая копия приходит в Telegram частями (.part01, .part02…) — их
    # выбирают все разом, склеиваем по порядку имён
    files = sorted((f for f in request.files.getlist("file") if f and f.filename), key=lambda f: f.filename)
    if not files:
        return jsonify({"ok": False, "error": "файл не выбран"}), 400
    ok, err = _restore_from_backup(b"".join(f.read() for f in files), notify_chat_id=ADMIN_TELEGRAM_ID or None)
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


@app.route("/api/admin/shops/<int:shop_id>/toggle_store", methods=["POST"])
@admin_required
def api_admin_toggle_store(shop_id):
    """«Склад магазина»: основной склад + магазин в одном аккаунте."""
    data = request.get_json(force=True)
    enabled = bool(data.get("enabled"))
    if enabled:
        db.set_shop_warehouse_enabled(shop_id, True)  # без склада магазин не работает
    db.set_shop_store_enabled(shop_id, enabled)
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
    pending = db.new_branch_needs_payment(parent)
    if pending:
        db.set_branch_pending(branch["id"], True)  # заработает после оплаты
    return jsonify({"ok": True, "id": branch["id"], "username": username, "password": password,
                    "sub_pending": pending})


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
    if ok == "has_cash":
        return jsonify({"ok": False, "error": "у сотрудника в кассе есть несданные деньги — "
                                              "сначала владелец точки должен принять кассу"}), 400
    if not ok:
        return jsonify({"ok": False, "error": "сотрудник не найден"}), 404
    return jsonify({"ok": True})
