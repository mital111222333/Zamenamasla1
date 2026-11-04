"""Ежедневная сводка владельцу точки в Telegram: утром (8:00) — что было
вчера и что сделать сегодня, вечером (22:00) — итог дня и советы.

Без ИИ: все цифры считает database.py (те же расчёты, что в «Статистике»),
а советы выбираются по правилам ниже — не больше трёх, самые важные первыми.
Язык — язык точки (ru / uz). Отправляет bot.py."""
from datetime import date, datetime, timedelta

import database as db

MAX_TIPS = 3
QUIET_DAYS = 30          # точку без замен за столько дней не беспокоим
DUE_SHOW = 5             # сколько номеров машин показать в утреннем списке

TEXT = {
    "ru": {
        "weekdays": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
        "currency": "сум",
        "owner": "владелец",
        "eve_title": "🌙 Итоги дня — {shop} · {date}",
        "eve_none": "Сегодня замен не было.",
        "eve_counts": "Замен: {count} · Выручка: {revenue} сум",
        "eve_cash": "Наличные {sum}",
        "eve_card": "Карта {sum}",
        "eve_debt_out": "В долг {sum}",
        "eve_profit": "Прибыль: {profit} сум",
        "eve_clients": "Клиенты: новых {new}, вернулись {ret}",
        "eve_cmp_up": "К тому же дню прошлой недели: ▲ +{pct}%",
        "eve_cmp_down": "К тому же дню прошлой недели: ▼ −{pct}%",
        "eve_cmp_same": "К тому же дню прошлой недели: на том же уровне",
        "eve_staff": "Кто работал: {list}",
        "eve_staff_item": "{name} — {count}",
        "eve_expenses": "Расходы за день: {sum} сум",
        "eve_repaid": "Погасили долгов: {sum} сум",
        "tips_title": "💡 Советы:",
        "morning_title": "☀️ Доброе утро! {shop} · {wd}, {date}",
        "m_yesterday": "Вчера: замен {count}, выручка {revenue} сум",
        "m_yesterday_profit": ", прибыль {profit} сум",
        "m_yesterday_none": "Вчера замен не было.",
        "m_due": "🚗 Сегодня пора на замену: {n} {cars}",
        "m_due_late": "🕐 Не приехали за последнюю неделю: {n} {cars}",
        "m_due_more": "…и ещё {n}",
        "m_stock_low": "📦 Заканчивается: {list}",
        "m_stock_item": "{name} (≈{days} дн.)",
        "m_stock_out": "📦 Нет в наличии: {n} {items} — проверьте заказ",
        "m_debts": "💰 Просрочены долги: {n} на {sum} сум",
        "m_task": "🎯 Задача на сегодня: {text}",
        "cars": ("машина", "машины", "машин"),
        "items": ("товар", "товара", "товаров"),
        "off_btn": "🔕 Не присылать сводки",
        "off_done": "Сводки отключены. Включить снова: /svodka",
        "on_done": "Сводки включены: каждый день в 8:00 и 22:00.",
        "on_none": "Не нашёл вашу точку. Уведомления точки должны приходить в этот чат.",
        # советы
        "t_no_changes_due": "Сегодня ждали {n} {cars}, но замен не было. Завтра с утра позвоните этим клиентам — список придёт в 8:00.",
        "t_drop": "Выручка на {pct}% ниже, чем неделю назад в тот же день. Посмотрите, все ли клиенты получили напоминание, и позвоните тем, кто просрочил замену.",
        "t_up": "Отличный день: выручка на {pct}% выше, чем неделю назад. Отметьте мастеров — хорошую работу стоит замечать.",
        "t_oil_filter": "За неделю масляный фильтр поставили только в {pct}% замен масла. Предлагайте фильтр каждому клиенту: это безопасность двигателя и выше средний чек.",
        "t_air_filter": "Воздушный фильтр за месяц — лишь в {pct}% замен. Проверяйте его каждую вторую замену и показывайте клиенту, если он грязный.",
        "t_debt_share": "{pct}% сегодняшней выручки ушло в долг. Записывайте дату платежа — бот сам напомнит клиенту.",
        "t_no_new": "За неделю ни одного нового клиента. Дайте довольным клиентам визитку или ссылку «Пригласи друга», отметьте точку на картах.",
        "t_unpriced": "У части товаров не указана цена закупки, поэтому прибыль неполная. Заполните цены в «Склад» — так будет видно, на чём вы зарабатываете.",
        "t_dead": "{n} {items} лежат без продаж больше 2 месяцев (≈{sum} сум). Сделайте на них скидку или предлагайте первыми.",
        "t_staff_gap": "У {top} {top_n} замен, у {low} — {low_n}. Проверьте, равномерно ли распределена работа.",
        "task_call": "позвонить клиентам, у которых сегодня замена — так они приедут к вам, а не к соседу.",
        "task_order": "заказать товары, которые заканчиваются, пока клиенты не ушли без покупки.",
        "task_debts": "напомнить должникам об оплате — вежливо, в Telegram или по телефону.",
        "tip_pool": [
            "Встречайте клиента по имени — в карточке машины оно есть. Это мелочь, которую запоминают.",
            "Показывайте клиенту старый фильтр и щуп с маслом: так он видит, за что платит, и больше доверяет.",
            "Спросите 3 довольных клиентов, можно ли оставить отзыв на картах. Отзывы приводят новых клиентов.",
            "Проверьте цены на 5 самых ходовых масел у соседей. Иногда разница в 5 000 сум решает выбор клиента.",
            "Наклейка с датой и пробегом следующей замены на стекле — бесплатная реклама и повод вернуться к вам.",
            "Чистое рабочее место и форма мастеров повышают доверие сильнее любой скидки.",
            "Поговорите с каждым мастером 5 минут в неделю: что мешает работать быстрее и что можно улучшить.",
            "Держите на складе масло для самых частых машин вашего района: если товара нет, клиент уходит к соседу.",
            "Предложите постоянным клиентам набор «масло + все фильтры» с небольшой скидкой — это выгоднее, чем ждать.",
            "Записывайте телефон каждого клиента: без него не придёт напоминание, и клиент может не вернуться.",
            "Раз в месяц смотрите «Статистику»: какие дни слабые — туда ставьте акции.",
            "Честная цена без скрытых доплат — главная причина, по которой клиенты возвращаются годами.",
        ],
    },
    "uz": {
        "weekdays": ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"],
        "currency": "so'm",
        "owner": "egasi",
        "eve_title": "🌙 Kun yakuni — {shop} · {date}",
        "eve_none": "Bugun almashtirish bo'lmadi.",
        "eve_counts": "Almashtirishlar: {count} · Tushum: {revenue} so'm",
        "eve_cash": "Naqd {sum}",
        "eve_card": "Karta {sum}",
        "eve_debt_out": "Qarzga {sum}",
        "eve_profit": "Foyda: {profit} so'm",
        "eve_clients": "Mijozlar: yangi {new}, qaytganlar {ret}",
        "eve_cmp_up": "O'tgan {wd}ga nisbatan: ▲ +{pct}%",
        "eve_cmp_down": "O'tgan {wd}ga nisbatan: ▼ −{pct}%",
        "eve_cmp_same": "O'tgan {wd}ga nisbatan: shu darajada",
        "eve_staff": "Kim ishladi: {list}",
        "eve_staff_item": "{name} — {count}",
        "eve_expenses": "Kunlik xarajatlar: {sum} so'm",
        "eve_repaid": "Qarz to'landi: {sum} so'm",
        "tips_title": "💡 Maslahatlar:",
        "morning_title": "☀️ Xayrli tong! {shop} · {wd}, {date}",
        "m_yesterday": "Kecha: {count} ta almashtirish, {revenue} so'm",
        "m_yesterday_profit": ", foyda {profit} so'm",
        "m_yesterday_none": "Kecha almashtirish bo'lmadi.",
        "m_due": "🚗 Bugun almashtirish vaqti: {n} {cars}",
        "m_due_late": "🕐 O'tgan haftada kelmaganlar: {n} {cars}",
        "m_due_more": "…yana {n} ta",
        "m_stock_low": "📦 Tugayapti: {list}",
        "m_stock_item": "{name} (≈{days} kun)",
        "m_stock_out": "📦 Omborda yo'q: {n} {items} — buyurtmani tekshiring",
        "m_debts": "💰 Muddati o'tgan qarzlar: {n} ta, {sum} so'm",
        "m_task": "🎯 Bugungi vazifa: {text}",
        "cars": ("ta mashina", "ta mashina", "ta mashina"),
        "items": ("ta tovar", "ta tovar", "ta tovar"),
        "off_btn": "🔕 Hisobot yubormang",
        "off_done": "Hisobotlar o'chirildi. Qayta yoqish: /svodka",
        "on_done": "Hisobotlar yoqildi: har kuni 8:00 va 22:00 da.",
        "on_none": "Nuqtangiz topilmadi. Nuqta xabarnomalari shu chatga kelishi kerak.",
        "t_no_changes_due": "Bugun {n} {cars} kutilgan edi, lekin almashtirish bo'lmadi. Ertalab shu mijozlarga qo'ng'iroq qiling — ro'yxat 8:00 da keladi.",
        "t_drop": "Tushum o'tgan {wd}dan {pct}% kam. Hamma mijozlarga eslatma borganini tekshiring va almashtirish muddati o'tganlarga qo'ng'iroq qiling.",
        "t_up": "Ajoyib kun: tushum o'tgan {wd}dan {pct}% ko'p. Ustalarni rag'batlantiring — yaxshi ishni e'tiborsiz qoldirmang.",
        "t_oil_filter": "Hafta davomida moy filtri moy almashtirishlarning faqat {pct}% ida qo'yildi. Har bir mijozga filtr taklif qiling: bu dvigatel xavfsizligi va o'rtacha chek oshadi.",
        "t_air_filter": "Oy davomida havo filtri almashtirishlarning atigi {pct}% ida. Uni har ikkinchi almashtirishda tekshiring va iflos bo'lsa mijozga ko'rsating.",
        "t_debt_share": "Bugungi tushumning {pct}% qarzga ketdi. To'lov sanasini yozib qo'ying — bot mijozga o'zi eslatadi.",
        "t_no_new": "Hafta davomida birorta yangi mijoz yo'q. Mamnun mijozlarga vizitka yoki «Do'stni taklif qiling» havolasini bering, nuqtani xaritalarda belgilang.",
        "t_unpriced": "Ba'zi tovarlarning kirim narxi ko'rsatilmagan, shuning uchun foyda to'liq emas. «Ombor»da narxlarni to'ldiring — nimadan pul topayotganingiz ko'rinadi.",
        "t_dead": "{n} {items} 2 oydan ortiq sotilmay yotibdi (≈{sum} so'm). Ularga chegirma qiling yoki birinchi bo'lib taklif qiling.",
        "t_staff_gap": "{top}da {top_n} ta almashtirish, {low}da — {low_n} ta. Ish teng taqsimlanganini tekshiring.",
        "task_call": "bugun almashtirish vaqti kelgan mijozlarga qo'ng'iroq qilish — shunda ular qo'shningizga emas, sizga keladi.",
        "task_order": "tugayotgan tovarlarga buyurtma berish, mijozlar xaridsiz ketib qolmasin.",
        "task_debts": "qarzdorlarga to'lovni eslatish — xushmuomalalik bilan, Telegramda yoki telefonda.",
        "tip_pool": [
            "Mijozni ismi bilan kutib oling — ismi mashina kartochkasida bor. Bu kichik narsa, lekin esda qoladi.",
            "Mijozga eski filtr va moy shchupini ko'rsating: u nimaga pul to'layotganini ko'radi va ko'proq ishonadi.",
            "3 ta mamnun mijozdan xaritalarda sharh qoldirishni so'rang. Sharhlar yangi mijozlarni olib keladi.",
            "Eng ko'p sotiladigan 5 ta moy narxini qo'shnilarda tekshiring. Ba'zan 5 000 so'm farq mijoz tanlovini hal qiladi.",
            "Oynaga keyingi almashtirish sanasi va probegi yozilgan stiker — bepul reklama va sizga qaytishga sabab.",
            "Toza ish joyi va ustalarning formasi har qanday chegirmadan ko'ra ko'proq ishonch uyg'otadi.",
            "Har bir usta bilan haftasiga 5 daqiqa gaplashing: tezroq ishlashga nima xalaqit beradi, nimani yaxshilash mumkin.",
            "Omborda hududingizdagi eng ko'p uchraydigan mashinalar uchun moy saqlang: tovar bo'lmasa, mijoz qo'shniga ketadi.",
            "Doimiy mijozlarga kichik chegirma bilan «moy + barcha filtrlar» to'plamini taklif qiling.",
            "Har bir mijozning telefonini yozib oling: usiz eslatma bormaydi va mijoz qaytmasligi mumkin.",
            "Oyiga bir marta «Statistika»ni ko'ring: qaysi kunlar sust — o'sha kunlarga aksiya qo'ying.",
            "Yashirin qo'shimcha to'lovlarsiz halol narx — mijozlar yillab qaytishining asosiy sababi.",
        ],
    },
}


def _t(lang):
    return TEXT.get(lang) or TEXT["ru"]


def money(n) -> str:
    return f"{int(round(n or 0)):,}".replace(",", " ")


def _plural(lang, n, forms):
    if lang != "ru":
        return forms[0]
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else (forms[1] if 2 <= n <= 4 else forms[2])


def _ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _pct(cur, prev):
    return round((cur - prev) / prev * 100) if prev else None


# ---------- цифры ----------

def collect_evening(shop: dict, day: date) -> dict:
    sid, d = shop["id"], _ymd(day)
    with db.get_conn() as conn:
        clients = db._client_split(conn, sid, d, d)
        clients_week = db._client_split(conn, sid, _ymd(day - timedelta(days=6)), d)
    return {
        "kind": "evening", "day": day,
        "t": db.get_day_details(sid, d)["totals"],
        "prev": db.get_day_details(sid, _ymd(day - timedelta(days=7)))["totals"],
        "profit": db.get_profit_breakdown(sid, d, d),
        "clients": clients, "clients_week": clients_week,
        "staff": db.digest_staff_day(sid, d),
        "due_today": db.digest_due(sid, d, d),
        "rates_week": db.digest_item_rates(sid, _ymd(day - timedelta(days=6)), d),
        "rates_month": db.digest_item_rates(sid, _ymd(day - timedelta(days=29)), d),
        "wh": db.get_warehouse_overview(sid) if shop.get("warehouse_enabled") else None,
    }


def collect_morning(shop: dict, day: date) -> dict:
    sid, d = shop["id"], _ymd(day)
    yday = _ymd(day - timedelta(days=1))
    return {
        "kind": "morning", "day": day,
        "y": db.get_day_details(sid, yday)["totals"],
        "y_profit": db.get_profit_breakdown(sid, yday, yday),
        "due_today": db.digest_due(sid, d, d, limit=50),
        "due_late": db.digest_due(sid, _ymd(day - timedelta(days=7)), _ymd(day - timedelta(days=1)), limit=50),
        "debts": db.digest_debts(sid, d),
        "wh": db.get_warehouse_overview(sid) if shop.get("warehouse_enabled") else None,
    }


# ---------- советы по правилам ----------

def evening_tips(f: dict, lang: str) -> list:
    T, tips = _t(lang), []
    t, prev, wd = f["t"], f["prev"], T["weekdays"][f["day"].weekday()]
    if not t["count"] and f["due_today"]:
        n = len(f["due_today"])
        tips.append(T["t_no_changes_due"].format(n=n, cars=_plural(lang, n, T["cars"])))
    pct = _pct(t["revenue"], prev["revenue"])
    if pct is not None and pct <= -20 and t["count"]:
        tips.append(T["t_drop"].format(pct=-pct, wd=wd))
    rw = f["rates_week"]
    if rw["oil_visits"] >= 5 and rw["filter_0"] / rw["oil_visits"] < 0.7:
        tips.append(T["t_oil_filter"].format(pct=round(rw["filter_0"] / rw["oil_visits"] * 100)))
    rm = f["rates_month"]
    if rm["oil_visits"] >= 10 and rm["filter_1"] / rm["oil_visits"] < 0.15:
        tips.append(T["t_air_filter"].format(pct=round(rm["filter_1"] / rm["oil_visits"] * 100)))
    if t["revenue"] and t["debt_out"] / t["revenue"] > 0.3:
        tips.append(T["t_debt_share"].format(pct=round(t["debt_out"] / t["revenue"] * 100)))
    cw = f["clients_week"]
    if cw["total"] >= 5 and not cw["new"]:
        tips.append(T["t_no_new"])
    staff = [s for s in f["staff"] if s["name"]]
    if len(staff) >= 2 and staff[0]["count"] >= 6 and staff[0]["count"] >= 3 * max(staff[-1]["count"], 1):
        tips.append(T["t_staff_gap"].format(top=staff[0]["name"], top_n=staff[0]["count"],
                                            low=staff[-1]["name"], low_n=staff[-1]["count"]))
    if t["revenue"] and f["profit"]["unpriced"] > t["revenue"] * 0.3:
        tips.append(T["t_unpriced"])
    wh = f.get("wh")
    if wh and wh["summary"]["dead_count"]:
        n = wh["summary"]["dead_count"]
        tips.append(T["t_dead"].format(n=n, items=_plural(lang, n, T["items"]), sum=money(wh["summary"]["dead_value"])))
    if pct is not None and pct >= 20 and t["count"]:
        tips.append(T["t_up"].format(pct=pct, wd=wd))
    if len(tips) < MAX_TIPS:
        pool = T["tip_pool"]
        tips.append(pool[f["day"].timetuple().tm_yday % len(pool)])
    return tips[:MAX_TIPS]


# ---------- тексты ----------

def render_evening(shop: dict, f: dict, lang: str) -> str:
    T, t = _t(lang), f["t"]
    wd = T["weekdays"][f["day"].weekday()]
    lines = [T["eve_title"].format(shop=shop.get("shop_name") or shop.get("username"), date=f["day"].strftime("%d.%m")), ""]
    if not t["count"]:
        lines.append(T["eve_none"])
    else:
        lines.append(T["eve_counts"].format(count=t["count"], revenue=money(t["revenue"])))
        pay = [T[k].format(sum=money(t[v])) for k, v in (("eve_cash", "cash"), ("eve_card", "card"),
                                                          ("eve_debt_out", "debt_out")) if t[v]]
        if pay:
            lines.append(" · ".join(pay))
        if f["profit"]["profit"] > 0:
            lines.append(T["eve_profit"].format(profit=money(f["profit"]["profit"])))
        c = f["clients"]
        lines.append(T["eve_clients"].format(new=c["new"], ret=c["returning"]))
        pct = _pct(t["revenue"], f["prev"]["revenue"])
        if pct is not None:
            key = "eve_cmp_up" if pct >= 3 else ("eve_cmp_down" if pct <= -3 else "eve_cmp_same")
            lines.append(T[key].format(pct=abs(pct), wd=wd))
        if f["staff"] and (len(f["staff"]) > 1 or f["staff"][0]["name"]):
            items = [T["eve_staff_item"].format(name=s["name"] or T["owner"], count=s["count"]) for s in f["staff"]]
            lines.append(T["eve_staff"].format(list=", ".join(items)))
    if t["repaid"]:
        lines.append(T["eve_repaid"].format(sum=money(t["repaid"])))
    if t["expenses"]:
        lines.append(T["eve_expenses"].format(sum=money(t["expenses"])))
    tips = evening_tips(f, lang)
    if tips:
        lines += ["", T["tips_title"]] + [f"{i}. {x}" for i, x in enumerate(tips, 1)]
    return "\n".join(lines)


def render_morning(shop: dict, f: dict, lang: str) -> str:
    T = _t(lang)
    lines = [T["morning_title"].format(shop=shop.get("shop_name") or shop.get("username"),
                                       wd=T["weekdays"][f["day"].weekday()], date=f["day"].strftime("%d.%m")), ""]
    y = f["y"]
    if y["count"]:
        s = T["m_yesterday"].format(count=y["count"], revenue=money(y["revenue"]))
        if f["y_profit"]["profit"] > 0:
            s += T["m_yesterday_profit"].format(profit=money(f["y_profit"]["profit"]))
        lines.append(s)
    else:
        lines.append(T["m_yesterday_none"])

    def due_block(key, rows):
        if not rows:
            return
        n = len(rows)
        lines.extend(["", T[key].format(n=n, cars=_plural(lang, n, T["cars"]))])
        for r in rows[:DUE_SHOW]:
            lines.append(f"• {r['plate']}" + (f" — {r['owner_name']}" if r.get("owner_name") else ""))
        if n > DUE_SHOW:
            lines.append(T["m_due_more"].format(n=n - DUE_SHOW))

    due_block("m_due", f["due_today"])
    due_block("m_due_late", f["due_late"])

    wh, task = f.get("wh"), None
    if wh:
        low = sorted([p for p in wh["products"] if p["status"] == "low" and p.get("days_left") is not None],
                     key=lambda p: p["days_left"])[:3]
        if low:
            lines.extend(["", T["m_stock_low"].format(list=", ".join(
                T["m_stock_item"].format(name=p["name"], days=p["days_left"]) for p in low))])
        out_n = wh["summary"]["out_count"]
        if out_n:
            lines.append(T["m_stock_out"].format(n=out_n, items=_plural(lang, out_n, T["items"])))
        if low or out_n:
            task = T["task_order"]
    d = f["debts"]
    if d["overdue_count"]:
        lines.extend(["", T["m_debts"].format(n=d["overdue_count"], sum=money(d["overdue_sum"]))])
        task = task or T["task_debts"]
    if f["due_today"] or f["due_late"]:
        task = T["task_call"]
    if not task:
        pool = T["tip_pool"]
        task = pool[(f["day"].timetuple().tm_yday + 5) % len(pool)]
    lines.extend(["", T["m_task"].format(text=task)])
    return "\n".join(lines)


def build(shop: dict, kind: str, now: datetime = None):
    """Текст сводки для точки или None, если слать нечего (точка давно не
    работает в OilBook или закрыта подпиской)."""
    now = now or datetime.now()
    st = db.subscription_state(shop)
    if st.get("blocked") or st.get("readonly"):
        return None
    last = db.digest_last_change(shop["id"])
    if not last or last < _ymd(now.date() - timedelta(days=QUIET_DAYS)):
        return None
    lang = shop.get("language") if shop.get("language") in TEXT else "ru"
    if kind == "morning":
        return render_morning(shop, collect_morning(shop, now.date()), lang)
    return render_evening(shop, collect_evening(shop, now.date()), lang)
