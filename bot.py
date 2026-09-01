"""
Телеграм-бот + веб-панель для учёта клиентов пункта замены масла.

Два режима:
1. ХОЗЯИН ПУНКТА (админ, ADMIN_TELEGRAM_ID) — вносит машину/замену через
   пошаговую "форму" в чате ИЛИ через веб-панель (открывается по ссылке на
   сайт), ищет машину по госномеру, видит всю историю и последнюю марку масла.
   На каждого нового клиента бот выдаёт персональную ссылку/QR — её нужно
   отправить или показать клиенту, чтобы он привязался к системе.
2. АВТОВЛАДЕЛЕЦ (клиент) — переходит по персональной ссылке от хозяина пункта,
   жмёт /start — и сразу привязан, без ввода телефона. Дальше получает
   напоминания о замене масла (по умолчанию раз в 3 месяца от даты замены)
   с кнопками "Уже поменял" / "Записаться".

Веб-панель поднимается в том же процессе (см. webapp.py), так что для
хостинга достаточно одного процесса/дино.
"""

import os
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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

DEFAULT_INTERVAL_MONTHS = 3

# Состояния диалогов админа
(
    ADMIN_PLATE, ADMIN_OWNER_NAME, ADMIN_OWNER_PHONE, ADMIN_CAR_BRAND_MODEL,
    ADMIN_MILEAGE, ADMIN_OIL_BRAND, ADMIN_INTERVAL, ADMIN_NOTES,
    SEARCH_PLATE,
) = range(9)


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_TELEGRAM_ID


def client_link(token: str) -> str:
    if not BOT_USERNAME:
        return "(ссылка недоступна — не задан BOT_USERNAME)"
    return f"https://t.me/{BOT_USERNAME}?start={token}"


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
                f"Здравствуйте, {client['full_name'] or user.first_name}!\n\n"
                f"Вы привязаны к пункту замены масла. Авто: {plates}.\n"
                "Когда подойдёт время замены — пришлю напоминание."
            )
            return ConversationHandler.END

    await update.message.reply_text(
        "Здравствуйте! Чтобы получать напоминания о замене масла, попросите "
        "на пункте замены персональную ссылку или QR-код — просто перейдите по ней, "
        "и вы будете автоматически привязаны."
    )
    return ConversationHandler.END


async def reminder_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, oil_change_id = query.data.split(":")
    oil_change_id = int(oil_change_id)

    if action == "changed":
        db.mark_already_changed_elsewhere(oil_change_id)
        await query.edit_message_text("Спасибо! Отметили, что замена уже произведена. Хорошей дороги! 🚗")
    elif action == "book":
        db.mark_reminder_sent(oil_change_id)
        await query.edit_message_text(
            "Отлично! Приезжайте на пункт замены масла, вас уже ждут. "
            "Если нужно уточнить время — свяжитесь с нами напрямую."
        )


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
        last_brand = db.get_last_oil_brand(existing["id"])
        hint = f"\n💡 В прошлый раз заливали: {last_brand}" if last_brand else ""
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
    await update.message.reply_text("Какое масло залили (марка)?")
    return ADMIN_OIL_BRAND


async def add_oil_brand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["oil_brand"] = update.message.text.strip()
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
        client_id = d["client_id"]
    else:
        client = db.get_or_create_client(d["owner_name"], d.get("owner_phone"))
        client_id = client["id"]
        car_id = db.create_or_update_car(d["plate"], client_id, car_model=d.get("car_model"))

    _, next_date = db.add_oil_change(car_id, d.get("mileage"), d["oil_brand"], d["interval_months"], notes)

    car_after, _ = db.get_car_history(d["plate"])
    link_line = ""
    if car_after and not car_after["telegram_id"]:
        link_line = f"\n\n🔗 Персональная ссылка для клиента (отправьте или сделайте QR):\n{client_link(car_after['link_token'])}"

    await update.message.reply_text(
        f"✅ Запись сохранена!\n\n"
        f"Госномер: {d['plate']}\n"
        f"Масло: {d['oil_brand']}\n"
        f"Следующая замена ориентировочно: {next_date}"
        f"{link_line}"
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
        "📋 История замен:\n"
    )
    if not history:
        text += "Пока нет записей."
    else:
        for h in history:
            text += f"• {h['change_date']} — {h['mileage'] or '—'} км, масло: {h['oil_brand']}, след. замена: {h['next_change_date']}"
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


# ============ ПЛАНИРОВЩИК НАПОМИНАНИЙ ============

async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    due = db.get_due_reminders()
    for item in due:
        if not item["telegram_id"]:
            continue  # владелец ещё не привязал Telegram — пропускаем, отправим когда привяжется
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Уже поменял", callback_data=f"changed:{item['id']}"),
                InlineKeyboardButton("📅 Записаться", callback_data=f"book:{item['id']}"),
            ]
        ])
        try:
            await context.bot.send_message(
                chat_id=item["telegram_id"],
                text=(
                    f"🔧 Напоминание о замене масла\n\n"
                    f"Автомобиль: {item['plate_number']}\n"
                    f"Похоже, подошло время замены масла.\n\n"
                    f"Хотите записаться на пункт замены?"
                ),
                reply_markup=keyboard,
            )
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
            ADMIN_OIL_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_oil_brand)],
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
    app.add_handler(CallbackQueryHandler(reminder_button_callback))

    job_queue = app.job_queue
    job_queue.run_repeating(check_and_send_reminders, interval=6 * 3600, first=10)

    logger.info("Бот и веб-панель запущены...")
    app.run_polling()


if __name__ == "__main__":
    main()
