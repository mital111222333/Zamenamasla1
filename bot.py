"""
Телеграм-бот + веб-панель для учёта клиентов пункта замены масла.

Два режима:
1. ХОЗЯИН ПУНКТА (админ, ADMIN_TELEGRAM_ID) — вносит машину/замену через
   пошаговую "форму" в чате ИЛИ через веб-панель, ищет машину по госномеру,
   видит всю историю. На каждого нового клиента бот и сайт выдают
   персональную ссылку/QR (плюс кнопку "Отправить в WhatsApp").
2. АВТОВЛАДЕЛЕЦ (клиент) — переходит по персональной ссылке, жмёт /start —
   и сразу привязан, без ввода телефона. Дальше — меню с историей своих
   машин и информацией о пункте, плюс напоминания о замене масла: первое —
   когда подошёл срок, дальше — раз в 2 недели, пока не отметит "уже поменял"
   или не запишется (максимум несколько напоминаний, чтобы не спамить).

Веб-панель поднимается в том же процессе (см. webapp.py).
"""

import os
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, filters, CallbackQueryHandler
)

import database as db
import webapp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")
ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))  # Telegram ID хозяина пункта
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")  # username бота без @, нужен для персональных ссылок

# Информация о пункте замены масла — показывается клиенту по кнопке "О пункте"
SHOP_NAME = os.environ.get("SHOP_NAME", "Пункт замены масла")
SHOP_PHONE = os.environ.get("SHOP_PHONE", "")
SHOP_ADDRESS = os.environ.get("SHOP_ADDRESS", "")
SHOP_HOURS = os.environ.get("SHOP_HOURS", "")
SHOP_LAT = os.environ.get("SHOP_LAT", "")
SHOP_LON = os.environ.get("SHOP_LON", "")

DEFAULT_INTERVAL_MONTHS = 3
SERVICE_TYPES = ["Замена масла", "Замена масла + фильтр", "Полное ТО", "Другое"]

CLIENT_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("🕒 Моя история"), KeyboardButton("ℹ️ О пункте")]],
    resize_keyboard=True
)

# Состояния диалогов админа
(
    ADMIN_PLATE, ADMIN_OWNER_NAME, ADMIN_OWNER_PHONE, ADMIN_CAR_BRAND_MODEL,
    ADMIN_MILEAGE, ADMIN_SERVICE_TYPE, ADMIN_OIL_BRAND, ADMIN_FILTER, ADMIN_COST,
    ADMIN_INTERVAL, ADMIN_NOTES, SEARCH_PLATE,
) = range(12)


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_TELEGRAM_ID


def client_link(token: str) -> str:
    if not BOT_USERNAME:
        return "(ссылка недоступна — не задан BOT_USERNAME)"
    return f"https://t.me/{BOT_USERNAME}?start={token}"


def whatsapp_share_url(phone: str, link: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits and not digits.startswith("998") and len(digits) <= 9:
        digits = "998" + digits
    text = f"Здравствуйте! Вот ваша персональная ссылка для напоминаний о замене масла: {link}"
    from urllib.parse import quote
    return f"https://wa.me/{digits}?text={quote(text)}"


def telegram_share_url(link: str) -> str:
    """Открывает у админа встроенное окно 'Переслать' в Telegram, где он сам
    выбирает получателя (например, клиента из своих контактов/чатов) и
    отправляет готовое сообщение со ссылкой в один клик."""
    from urllib.parse import quote
    text = "Ваша персональная ссылка для напоминаний о замене масла:"
    return f"https://t.me/share/url?url={quote(link)}&text={quote(text)}"


# ============ КЛИЕНТ (автовладелец) ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_admin(update):
        panel_note = f"\n🌐 Веб-панель: {webapp.PUBLIC_URL}" if webapp.PUBLIC_URL else ""
        await update.message.reply_text(
            "Здравствуйте! Это админ-панель пункта замены масла.\n\n"
            "/add — внести новую замену масла\n"
            "/find — найти машину по госномеру и посмотреть историю"
            f"{panel_note}"
        )
        return ConversationHandler.END

    token = context.args[0] if context.args else None
    if token:
        client = db.link_client_by_token(user.id, token, tg_full_name=user.full_name)
        if client:
            cars = db.get_client_cars(client["id"])
            plates = ", ".join(c["plate_number"] for c in cars) or "—"
            await update.message.reply_text(
                f"Здравствуйте, {client['full_name'] or user.first_name}! 👋\n\n"
                f"Вы привязаны к {SHOP_NAME}. Ваше авто: {plates}.\n"
                "Когда подойдёт время замены масла — пришлю напоминание.",
                reply_markup=CLIENT_MENU,
            )
            return ConversationHandler.END

    existing = db.get_client_by_telegram_id(user.id)
    if existing:
        await update.message.reply_text("С возвращением! 👋", reply_markup=CLIENT_MENU)
        return ConversationHandler.END

    await update.message.reply_text(
        "Здравствуйте! Чтобы получать напоминания о замене масла, попросите "
        "на пункте замены персональную ссылку или QR-код — просто перейдите по ней, "
        "и вы будете автоматически привязаны."
    )
    return ConversationHandler.END


async def client_history_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        return
    user = update.effective_user
    data = db.get_client_full_history(user.id)
    if not data:
        await update.message.reply_text("Пока нет ни одной машины, привязанной к вам.")
        return

    for item in data:
        car = item["car"]
        text = f"🚗 {car['plate_number']} — {(car['car_brand'] or '')} {(car['car_model'] or '')}\n\n"
        if not item["history"]:
            text += "Пока нет записей об обслуживании."
        else:
            for h in item["history"]:
                filt = " + фильтр" if h["filter_changed"] else ""
                cost = f", {h['cost']:,} сум".replace(",", " ") if h.get("cost") else ""
                text += (
                    f"📅 {h['change_date']} — {h['service_type']}{filt}\n"
                    f"   Масло: {h['oil_brand'] or '—'}, пробег: {h['mileage'] or '—'} км{cost}\n"
                    f"   Следующая замена: {h['next_change_date']}\n"
                )
                if h["notes"]:
                    text += f"   Заметка: {h['notes']}\n"
                text += "\n"
        await update.message.reply_text(text)


async def shop_info_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        return
    lines = [f"ℹ️ {SHOP_NAME}"]
    if SHOP_ADDRESS:
        lines.append(f"📍 Адрес: {SHOP_ADDRESS}")
    if SHOP_PHONE:
        lines.append(f"📞 Телефон: {SHOP_PHONE}")
    if SHOP_HOURS:
        lines.append(f"🕒 Часы работы: {SHOP_HOURS}")
    await update.message.reply_text("\n".join(lines))
    if SHOP_LAT and SHOP_LON:
        try:
            await update.message.reply_location(latitude=float(SHOP_LAT), longitude=float(SHOP_LON))
        except ValueError:
            pass


async def reminder_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, oil_change_id = query.data.split(":")
    oil_change_id = int(oil_change_id)

    if action == "changed":
        db.mark_already_changed_elsewhere(oil_change_id)
        await query.edit_message_text("Спасибо! Отметили, что замена уже произведена. Хорошей дороги! 🚗")
    elif action == "book":
        db.mark_booked(oil_change_id)
        await query.edit_message_text(
            f"Отлично! Ждём вас на {SHOP_NAME}. "
            "Если нужно уточнить время — свяжитесь с нами напрямую."
        )
        if ADMIN_TELEGRAM_ID:
            ctx = db.get_oil_change_with_context(oil_change_id)
            if ctx:
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_TELEGRAM_ID,
                        text=(
                            f"📅 Клиент записался на замену масла!\n\n"
                            f"Авто: {ctx['plate_number']}\n"
                            f"Владелец: {ctx['owner_name']}"
                            + (f"\nТелефон: {ctx['owner_phone']}" if ctx['owner_phone'] else "")
                        ),
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить админа о брони: {e}")


# ============ АДМИН: внесение новой замены (форма пошагово) ============

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    await update.message.reply_text("Введите госномер автомобиля:")
    return ADMIN_PLATE


async def add_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = db.normalize_plate(update.message.text)
    context.user_data["plate"] = plate

    existing = db.find_car(plate)
    if existing:
        context.user_data["existing_car_id"] = existing["id"]
        context.user_data["client_id"] = existing["client_id"]
        last = db.get_last_service(existing["id"])
        hint = f"\n💡 В прошлый раз: {last['service_type']}, масло {last['oil_brand']}" if last else ""
        await update.message.reply_text(
            f"Машина уже есть в базе.{hint}\n\nВведите текущий пробег (км), можно \"-\" если неизвестен:"
        )
        return ADMIN_MILEAGE

    await update.message.reply_text("Новая машина. Введите имя владельца:")
    return ADMIN_OWNER_NAME


async def add_owner_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["owner_name"] = update.message.text.strip()
    await update.message.reply_text("Телефон владельца (или \"-\", если не нужен):")
    return ADMIN_OWNER_PHONE


async def add_owner_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["owner_phone"] = None if phone == "-" else phone
    await update.message.reply_text("Марка и модель авто (например: Chevrolet Cobalt):")
    return ADMIN_CAR_BRAND_MODEL


async def add_car_brand_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["car_model"] = update.message.text.strip()
    await update.message.reply_text("Введите текущий пробег (км), можно \"-\" если неизвестен:")
    return ADMIN_MILEAGE


async def add_mileage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "-":
        context.user_data["mileage"] = None
    else:
        try:
            context.user_data["mileage"] = int(text.replace(" ", ""))
        except ValueError:
            await update.message.reply_text("Введите пробег числом, например: 45000 (или \"-\")")
            return ADMIN_MILEAGE
    types_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(SERVICE_TYPES))
    await update.message.reply_text(f"Тип услуги — напишите номер или текст:\n{types_list}")
    return ADMIN_SERVICE_TYPE


async def add_service_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit() and 1 <= int(text) <= len(SERVICE_TYPES):
        context.user_data["service_type"] = SERVICE_TYPES[int(text) - 1]
    else:
        context.user_data["service_type"] = text
    await update.message.reply_text("Какое масло залили (марка)? Можно \"-\", если не меняли масло:")
    return ADMIN_OIL_BRAND


async def add_oil_brand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["oil_brand"] = None if text == "-" else text
    await update.message.reply_text("Меняли фильтр? (да/нет)")
    return ADMIN_FILTER


async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    context.user_data["filter_changed"] = text in ("да", "yes", "+", "ha", "ha", "х")
    await update.message.reply_text("Стоимость (сум)? Можно \"-\", если не нужно фиксировать:")
    return ADMIN_COST


async def add_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if text == "-":
        context.user_data["cost"] = None
    else:
        try:
            context.user_data["cost"] = int(text)
        except ValueError:
            await update.message.reply_text("Введите сумму числом, например: 150000 (или \"-\")")
            return ADMIN_COST
    await update.message.reply_text(
        f"Через сколько месяцев следующая замена? (например: {DEFAULT_INTERVAL_MONTHS})"
    )
    return ADMIN_INTERVAL


async def add_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["interval_months"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите число месяцев, например: 3")
        return ADMIN_INTERVAL
    await update.message.reply_text("Заметки (или напишите \"-\", если нет):")
    return ADMIN_NOTES


async def add_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notes = update.message.text.strip()
    if notes == "-":
        notes = ""
    d = context.user_data

    if "existing_car_id" in d:
        car_id = d["existing_car_id"]
    else:
        client = db.get_or_create_client(d["owner_name"], d.get("owner_phone"))
        car_id = db.create_or_update_car(d["plate"], client["id"], car_model=d.get("car_model"))

    _, next_date = db.add_oil_change(
        car_id, d.get("mileage"), d.get("service_type", "Замена масла"), d.get("oil_brand"),
        d.get("filter_changed", False), d.get("cost"), d["interval_months"], notes
    )

    car_after, _ = db.get_car_history(d["plate"])
    reply_markup = None
    link_line = ""
    if car_after and not car_after["telegram_id"]:
        link = client_link(car_after["link_token"])
        link_line = f"\n\n🔗 Персональная ссылка для клиента:\n{link}"
        buttons = [InlineKeyboardButton("✈️ Отправить в Telegram", url=telegram_share_url(link))]
        if car_after.get("owner_phone"):
            buttons.append(
                InlineKeyboardButton("📲 Отправить в WhatsApp", url=whatsapp_share_url(car_after["owner_phone"], link))
            )
        reply_markup = InlineKeyboardMarkup([buttons])

    await update.message.reply_text(
        f"✅ Запись сохранена!\n\n"
        f"Госномер: {d['plate']}\n"
        f"Услуга: {d.get('service_type', 'Замена масла')}\n"
        f"Следующая замена ориентировочно: {next_date}"
        f"{link_line}",
        reply_markup=reply_markup,
    )
    context.user_data.clear()
    return ConversationHandler.END


# ============ АДМИН: поиск по госномеру ============

async def find_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    await update.message.reply_text("Введите госномер для поиска:")
    return SEARCH_PLATE


async def find_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = update.message.text.strip()
    car, history = db.get_car_history(plate)

    if not car:
        await update.message.reply_text("Машина с таким номером не найдена.")
        return ConversationHandler.END

    linked = "✅ привязан к боту" if car["telegram_id"] else "⚠️ ещё не привязан"
    text = (
        f"🚗 {car['plate_number']} — {car['owner_name']}\n"
        f"Модель: {(car['car_brand'] or '')} {(car['car_model'] or '')}\n"
        f"Клиент: {linked}\n\n"
        "📋 Подробная история:\n"
    )
    if not history:
        text += "Пока нет записей."
    else:
        for h in history:
            filt = " + фильтр" if h["filter_changed"] else ""
            cost = f", {h['cost']:,} сум".replace(",", " ") if h.get("cost") else ""
            text += (
                f"• {h['change_date']} — {h['service_type']}{filt}, {h['mileage'] or '—'} км, "
                f"масло: {h['oil_brand'] or '—'}{cost}, след.: {h['next_change_date']}"
            )
            if h["notes"]:
                text += f" (заметка: {h['notes']})"
            text += "\n"

    if not car["telegram_id"]:
        text += f"\n🔗 Ссылка для привязки клиента:\n{client_link(car['link_token'])}"

    await update.message.reply_text(text)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


# ============ ПЛАНИРОВЩИК НАПОМИНАНИЙ (раз в 6 часов проверяет due) ============

async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    due = db.get_due_reminders()
    for item in due:
        is_followup = item["reminder_count"] > 0
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Уже поменял", callback_data=f"changed:{item['id']}"),
                InlineKeyboardButton("📅 Записаться", callback_data=f"book:{item['id']}"),
            ]
        ])
        if is_followup:
            text = (
                f"🔧 Напоминаем ещё раз про {item['plate_number']} 🚗\n\n"
                f"Масло пора менять — не откладывайте, это бережёт двигатель. "
                f"Заедете к нам на {SHOP_NAME}?"
            )
        else:
            text = (
                f"🔔 Время замены масла!\n\n"
                f"Ваш автомобиль {item['plate_number']} — подошёл срок очередной замены масла "
                f"({item.get('service_type') or 'Замена масла'}).\n\n"
                f"Хотите записаться на {SHOP_NAME}?"
            )
        try:
            await context.bot.send_message(chat_id=item["telegram_id"], text=text, reply_markup=keyboard)
            db.mark_reminder_sent(item["id"])
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание {item['id']}: {e}")


def main():
    db.init_db()
    webapp.run_webapp_in_thread()  # веб-панель поднимается в этом же процессе

    app = Application.builder().token(BOT_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            ADMIN_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plate)],
            ADMIN_OWNER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_owner_name)],
            ADMIN_OWNER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_owner_phone)],
            ADMIN_CAR_BRAND_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_car_brand_model)],
            ADMIN_MILEAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_mileage)],
            ADMIN_SERVICE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_service_type)],
            ADMIN_OIL_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_oil_brand)],
            ADMIN_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_filter)],
            ADMIN_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_cost)],
            ADMIN_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_interval)],
            ADMIN_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_notes)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    find_conv = ConversationHandler(
        entry_points=[CommandHandler("find", find_start)],
        states={
            SEARCH_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_result)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(add_conv)
    app.add_handler(find_conv)
    app.add_handler(MessageHandler(filters.Regex("^🕒 Моя история$"), client_history_button))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ О пункте$"), shop_info_button))
    app.add_handler(CallbackQueryHandler(reminder_button_callback))

    job_queue = app.job_queue
    job_queue.run_repeating(check_and_send_reminders, interval=6 * 3600, first=10)

    logger.info("Бот и веб-панель запущены...")
    app.run_polling()


if __name__ == "__main__":
    main()
