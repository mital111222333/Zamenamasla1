# -*- coding: utf-8 -*-
"""Справка OilBook — статьи для раздела «Справка» / «Yordam».

Как устроено:
- SECTIONS — разделы справки (порядок = порядок на экране);
- ARTICLES — статьи. У каждой: раздел, роли, условие (склад / SMS), вкладка
  для кнопки «Открыть», заголовок и текст на RU и UZ;
- роли: M — главная точка с филиалами, S — самостоятельная точка,
  B — филиал, E — сотрудник;
- внутри текста можно писать [[MS]]...[[/]] — этот кусок увидят только
  указанные роли (здесь — главная и самостоятельная точки).

Текст статей — обычный HTML (p, ol, ul, b, div.hp-tip, div.hp-warn).
Чтобы добавить статью: допишите словарь в ARTICLES — больше ничего менять не нужно.
"""
import re

SECTIONS = [
    ("start", "fa-rocket", "С чего начать", "Nimadan boshlash"),
    ("service", "fa-car", "Замены и клиенты", "Almashtirish va mijozlar"),
    ("money", "fa-hand-holding-dollar", "Долги и расходы", "Qarzlar va xarajatlar"),
    ("reach", "fa-bullhorn", "Напоминания и рассылка", "Eslatmalar va xabarnoma"),
    ("warehouse", "fa-boxes-stacked", "Склад", "Ombor"),
    ("network", "fa-sitemap", "Сеть филиалов", "Filiallar tarmog'i"),
    ("suppliers", "fa-truck-field", "Поставщики и заказы", "Yetkazib beruvchilar va buyurtmalar"),
    ("stats", "fa-chart-column", "Статистика и прибыль", "Statistika va foyda"),
    ("team", "fa-user-gear", "Сотрудники и настройки", "Xodimlar va sozlamalar"),
    ("faq", "fa-circle-question", "Частые вопросы", "Ko'p beriladigan savollar"),
]

ROLE_NAMES = {
    "ru": {"M": "главная точка", "S": "точка", "B": "филиал", "E": "сотрудник"},
    "uz": {"M": "bosh nuqta", "S": "nuqta", "B": "filial", "E": "xodim"},
}

ALL = "MSBE"
OWNERS = "MS"
NOT_EMP = "MSB"

ARTICLES = [

# ======================================================================
# С ЧЕГО НАЧАТЬ
# ======================================================================
dict(id="roles_m", sec="start", roles="M",
ru=("Что вы можете как главная точка", """
<p>Вы — владелец сети. Вам видно всё по своей точке и по всем филиалам.</p>
<ul>
<li><b>Своя точка:</b> замены, база клиентов, долги, расходы, склад, поставщики, статистика с прибылью.</li>
<li><b>Филиалы:</b> вкладка «Все филиалы» в «Статистике» (сравнение выручки и прибыли) и вкладки «Склады филиалов» и «Сеть и перемещения» на «Складе».</li>
<li><b>Команда:</b> свои сотрудники во вкладке «Сотрудники».</li>
<li><b>Подписка:</b> оплачиваете вы — за всю сеть сразу.</li>
</ul>
<div class="hp-tip">Филиал не видит прибыль, закупочные цены и наценку — только выручку. Это сделано специально, чтобы цены закупки знали только вы.</div>
"""),
uz=("Bosh nuqta sifatida nimalar qila olasiz", """
<p>Siz tarmoq egasisiz. O'z nuqtangiz va barcha filiallar bo'yicha hammasini ko'rasiz.</p>
<ul>
<li><b>O'z nuqtangiz:</b> almashtirishlar, mijozlar bazasi, qarzlar, xarajatlar, ombor, yetkazib beruvchilar, foyda bilan statistika.</li>
<li><b>Filiallar:</b> «Statistika»dagi «Barcha filiallar» (tushum va foydani solishtirish), «Ombor»dagi «Filial omborlari» va «Tarmoq va ko'chirish».</li>
<li><b>Jamoa:</b> «Xodimlar» bo'limida o'z xodimlaringiz.</li>
<li><b>Obuna:</b> butun tarmoq uchun siz to'laysiz.</li>
</ul>
<div class="hp-tip">Filial foyda, xarid narxlari va ustamani ko'rmaydi — faqat tushumni ko'radi. Bu ataylab qilingan: xarid narxlarini faqat siz bilasiz.</div>
""")),

dict(id="roles_s", sec="start", roles="S",
ru=("Что умеет OilBook", """
<p>OilBook ведёт учёт вашего пункта замены масла:</p>
<ul>
<li>каждая замена записывается за 1–2 минуты, клиент и его машина запоминаются;</li>
<li>клиент сам получает в Telegram напоминание, когда пора на следующую замену;</li>
<li>долги и рассрочки считаются сами, просроченные видны красной цифрой;</li>
<li>склад списывается автоматически, программа подсказывает, что пора заказать;</li>
<li>статистика показывает выручку, средний чек, новых и постоянных клиентов и прибыль.</li>
</ul>
<div class="hp-tip">Начните с трёх шагов: установите приложение на телефон, привяжите Telegram точки и внесите первую замену. Статьи об этом — ниже.</div>
"""),
uz=("OilBook nimalar qila oladi", """
<p>OilBook moy almashtirish shoxobchangiz hisobini yuritadi:</p>
<ul>
<li>har bir almashtirish 1–2 daqiqada yoziladi, mijoz va uning mashinasi eslab qolinadi;</li>
<li>keyingi almashtirish vaqti kelganda mijozga Telegramda eslatma boradi;</li>
<li>qarz va bo'lib to'lashlar o'zi hisoblanadi, muddati o'tganlari qizil raqam bilan ko'rinadi;</li>
<li>ombordan mahsulot avtomatik chiqariladi, nimani buyurtma qilish kerakligi aytib turiladi;</li>
<li>statistika tushum, o'rtacha chek, yangi va doimiy mijozlar hamda foydani ko'rsatadi.</li>
</ul>
<div class="hp-tip">Uch qadamdan boshlang: ilovani telefonga o'rnating, nuqtaning Telegramini bog'lang va birinchi almashtirishni kiriting. Bular haqida maqolalar quyida.</div>
""")),

dict(id="roles_b", sec="start", roles="B",
ru=("Что вы можете как филиал", """
<p>Филиал — это полноценная точка сети: своя база клиентов, свой склад, свои сотрудники и расходы.</p>
<ul>
<li>Вы вносите замены, ведёте долги, склад и расходы, видите свою статистику: выручку, средний чек, клиентов.</li>
<li><b>Вы не видите</b> прибыль, цены закупки, наценку и стоимость склада. Их видит только главная точка.</li>
<li>Товар можно получать от главной точки — он сам появится на вашем складе.</li>
<li>Подписку оплачивает главная точка.</li>
</ul>
<p>В шапке под названием написано «OilBook · филиал» — так вы всегда знаете, где находитесь.</p>
"""),
uz=("Filial sifatida nimalar qila olasiz", """
<p>Filial — tarmoqning to'laqonli nuqtasi: o'z mijozlar bazasi, o'z ombori, o'z xodimlari va xarajatlari bor.</p>
<ul>
<li>Almashtirishlarni kiritasiz, qarzlar, ombor va xarajatlarni yuritasiz, o'z statistikangizni ko'rasiz: tushum, o'rtacha chek, mijozlar.</li>
<li><b>Ko'rmaysiz:</b> foyda, xarid narxlari, ustama va ombor qiymati. Ularni faqat bosh nuqta ko'radi.</li>
<li>Mahsulotni bosh nuqtadan olishingiz mumkin — u omboringizda o'zi paydo bo'ladi.</li>
<li>Obunani bosh nuqta to'laydi.</li>
</ul>
<p>Yuqorida nom ostida «OilBook · filial» deb yozilgan — shunda qayerda ekaningizni doim bilasiz.</p>
""")),

dict(id="roles_e", sec="start", roles="E",
ru=("Что вы можете как сотрудник", """
<p>Вы работаете в OilBook под своим логином. Вам доступно:</p>
<ul>
<li><b>Замена</b> — внести замену масла клиенту;</li>
<li><b>База</b> — найти клиента и посмотреть историю его машины;</li>
<li><b>Долги</b> — принять платёж от должника;</li>
<li><b>Рассылка</b> — отправить клиентам акцию;</li>
<li><b>Обучение</b> — курс для мастера.</li>
</ul>
<p>Статистику, прибыль, расходы, склад и экспорт видит только владелец точки.</p>
<div class="hp-tip">Когда выбираете масло и фильтр из списка склада, товар сам списывается со склада. Поэтому старайтесь выбирать из списка, а не писать вручную.</div>
"""),
uz=("Xodim sifatida nimalar qila olasiz", """
<p>Siz OilBook'da o'z loginingiz bilan ishlaysiz. Sizga ochiq:</p>
<ul>
<li><b>Almashtirish</b> — mijozga moy almashtirishni kiritish;</li>
<li><b>Baza</b> — mijozni topish va mashinasi tarixini ko'rish;</li>
<li><b>Qarzlar</b> — qarzdordan to'lov qabul qilish;</li>
<li><b>Xabarnoma</b> — mijozlarga aksiya yuborish;</li>
<li><b>Ta'lim</b> — usta uchun kurs.</li>
</ul>
<p>Statistika, foyda, xarajatlar, ombor va eksportni faqat nuqta egasi ko'radi.</p>
<div class="hp-tip">Moy va filtrni ombor ro'yxatidan tanlasangiz, mahsulot ombordan o'zi chiqariladi. Shuning uchun qo'lda yozmasdan, ro'yxatdan tanlashga harakat qiling.</div>
""")),

dict(id="install", sec="start", roles=ALL,
kw="установить приложение иконка главный экран телефон pwa o'rnatish ilova",
ru=("Установить OilBook на телефон как приложение", """
<p>OilBook работает в браузере, но его можно поставить на телефон как обычное приложение — с синей каплей на главном экране.</p>
<p><b>Android (Chrome):</b></p>
<ol class="hp-steps">
<li>Откройте сайт OilBook в Chrome и войдите.</li>
<li>Нажмите ⋮ (три точки) справа вверху.</li>
<li>Выберите «Установить приложение» или «Добавить на главный экран».</li>
</ol>
<p><b>iPhone (Safari):</b></p>
<ol class="hp-steps">
<li>Откройте сайт OilBook в Safari и войдите.</li>
<li>Нажмите кнопку «Поделиться» (квадрат со стрелкой вверх).</li>
<li>Выберите «На экран „Домой“».</li>
</ol>
<div class="hp-tip">Если адрес сайта поменялся — удалите старую иконку и установите приложение заново с нового адреса.</div>
"""),
uz=("OilBook'ni telefonga ilova qilib o'rnatish", """
<p>OilBook brauzerda ishlaydi, lekin uni telefonga oddiy ilova kabi o'rnatish mumkin — bosh ekranda ko'k tomchi belgisi bilan.</p>
<p><b>Android (Chrome):</b></p>
<ol class="hp-steps">
<li>OilBook saytini Chrome'da oching va kiring.</li>
<li>Yuqori o'ngdagi ⋮ (uch nuqta) tugmasini bosing.</li>
<li>«Ilovani o'rnatish» yoki «Bosh ekranga qo'shish»ni tanlang.</li>
</ol>
<p><b>iPhone (Safari):</b></p>
<ol class="hp-steps">
<li>OilBook saytini Safari'da oching va kiring.</li>
<li>«Ulashish» tugmasini bosing (yuqoriga strelkali kvadrat).</li>
<li>«Bosh ekranga» bandini tanlang.</li>
</ol>
<div class="hp-tip">Agar sayt manzili o'zgarsa — eski belgini o'chirib, ilovani yangi manzildan qayta o'rnating.</div>
""")),

dict(id="nav", sec="start", roles=ALL,
kw="меню навигация ещё нижняя панель язык выйти menyu til chiqish",
ru=("Как устроено меню. Язык и выход", """
<p><b>На телефоне</b> внизу экрана — панель с главными разделами. Красная круглая кнопка посередине — «Замена». Всё остальное — в кнопке «Ещё»: там же смена языка и «Выйти».</p>
<p><b>На компьютере и планшете</b> все разделы — в меню слева, язык и выход — внизу меню.</p>
<p>Красная цифра на «Долгах» (или на «Ещё») — сколько должников просрочили платёж.</p>
<p>Язык переключается кнопкой <b>UZ / RU</b> в шапке или «O'zbekcha» в меню. Язык запоминается для вашей точки.</p>
"""),
uz=("Menyu qanday tuzilgan. Til va chiqish", """
<p><b>Telefonda</b> ekran pastida asosiy bo'limlar paneli bor. O'rtadagi qizil dumaloq tugma — «Almashtirish». Qolgan hammasi «Yana» tugmasida: tilni almashtirish va «Chiqish» ham o'sha yerda.</p>
<p><b>Kompyuter va planshetda</b> barcha bo'limlar chap menyuda, til va chiqish — menyu pastida.</p>
<p>«Qarzlar» (yoki «Yana») ustidagi qizil raqam — to'lov muddatini o'tkazib yuborgan qarzdorlar soni.</p>
<p>Til yuqoridagi <b>UZ / RU</b> tugmasi yoki menyudagi «Русский» orqali almashtiriladi. Til nuqtangiz uchun eslab qolinadi.</p>
""")),

dict(id="telegram_owner", sec="start", roles=NOT_EMP,
kw="телеграм привязать уведомления бот резервная копия telegram bog'lash bildirishnoma",
ru=("Привязать Telegram точки", """
<p>Telegram точки нужен, чтобы:</p>
<ul>
<li>получать напоминания о долгах клиентов, которые не привязаны к боту;</li>
<li>получать напоминания о повторяющихся расходах (аренда и т.п.);</li>
[[MS]]<li>получать уведомления о подписке и долгах поставщикам;</li>[[/]]
<li>восстановить пароль, если забыли;</li>
<li>вносить замены и искать машины прямо из Telegram: команды <b>/add</b> и <b>/find</b>.</li>
</ul>
<p>Если вы регистрировались сами — Telegram уже привязан. Если точку создавал администратор — попросите у него ссылку для привязки, откройте её и нажмите «Start». Бот ответит «Telegram привязан к точке…».</p>
"""),
uz=("Nuqtaning Telegramini bog'lash", """
<p>Nuqtaning Telegrami quyidagilar uchun kerak:</p>
<ul>
<li>botga bog'lanmagan mijozlarning qarzlari haqida eslatma olish;</li>
<li>takrorlanuvchi xarajatlar (ijara va h.k.) haqida eslatma olish;</li>
[[MS]]<li>obuna va yetkazib beruvchilarga qarz haqida xabar olish;</li>[[/]]
<li>parolni unutsangiz, uni tiklash;</li>
<li>almashtirishni kiritish va mashinani to'g'ridan-to'g'ri Telegramdan qidirish: <b>/add</b> va <b>/find</b> buyruqlari.</li>
</ul>
<p>Agar o'zingiz ro'yxatdan o'tgan bo'lsangiz — Telegram allaqachon bog'langan. Agar nuqtani administrator yaratgan bo'lsa — undan bog'lash havolasini so'rang, uni oching va «Start»ni bosing. Bot «Telegram nuqtaga bog'landi…» deb javob beradi.</p>
""")),

dict(id="password", sec="start", roles=NOT_EMP,
kw="забыл пароль восстановить код parol unutdim tiklash",
ru=("Забыли пароль", """
<ol class="hp-steps">
<li>На странице входа нажмите «Забыли пароль?».</li>
<li>Введите логин и нажмите «Отправить код».</li>
<li>Код придёт в Telegram, привязанный к точке. Он действует 10 минут.</li>
<li>Введите код и новый пароль — готово.</li>
</ol>
<div class="hp-warn">Если Telegram к точке не привязан, код прийти не может. Тогда пароль сбрасывает администратор платформы.</div>
"""),
uz=("Parolni unutdingizmi", """
<ol class="hp-steps">
<li>Kirish sahifasida «Parolni unutdingizmi?»ni bosing.</li>
<li>Loginni kiriting va «Kodni yuborish»ni bosing.</li>
<li>Kod nuqtaga bog'langan Telegramga keladi. U 10 daqiqa amal qiladi.</li>
<li>Kodni va yangi parolni kiriting — tayyor.</li>
</ol>
<div class="hp-warn">Agar nuqtaga Telegram bog'lanmagan bo'lsa, kod kela olmaydi. Unda parolni platforma administratori tiklaydi.</div>
""")),

dict(id="password_e", sec="start", roles="E",
kw="забыл пароль parol unutdim",
ru=("Забыли пароль", """
<p>Сотрудник не восстанавливает пароль сам. Попросите владельца точки: он откроет «Сотрудники», нажмёт «Новый пароль» у вашего имени и передаст вам новый пароль.</p>
"""),
uz=("Parolni unutdingizmi", """
<p>Xodim parolni o'zi tiklamaydi. Nuqta egasidan so'rang: u «Xodimlar» bo'limini ochadi, ismingiz yonidagi «Yangi parol»ni bosadi va sizga yangi parolni beradi.</p>
""")),

# ======================================================================
# ЗАМЕНЫ И КЛИЕНТЫ
# ======================================================================
dict(id="add_service", sec="service", roles=ALL, go="add",
kw="внести замену масло фильтр сохранить пробег almashtirish kiritish moy filtr",
ru=("Как внести замену — по шагам", """
<p>Нажмите красную кнопку «Замена». Форма идёт сверху вниз:</p>
<ol class="hp-steps">
<li><b>Госномер.</b> Впишите номер или нажмите 📷 и наведите камеру на номер. Если машина уже есть в базе — появится карточка «Клиент узнан», а имя, телефон и марка заполнятся сами.</li>
<li><b>Имя и телефон владельца.</b> Телефон нужен, чтобы отправить клиенту ссылку в WhatsApp и связать несколько его машин.</li>
<li><b>Марка и модель</b> машины.</li>
<li><b>Пробег.</b> «Сейчас» — что на одометре. «Замена при» — на каком пробеге следующая замена. Кнопки +5 тыс. и +8 тыс. посчитают сами, «Свой…» — запомнит ваш интервал.</li>
<li><b>«В день» (необязательно)</b> — сколько клиент ездит в день. Тогда OilBook посчитает примерную дату следующей замены.</li>
<li><b>«Через сколько напомнить?»</b> — через сколько месяцев или дней клиент получит напоминание.</li>
<li><b>Товары и работа.</b> Найдите товар в «Быстром поиске» (например, <i>mit 5w30</i>) или выберите масло, фильтры и жидкости из списков. Работу и услуги без товара (мойка, замена свечей) впишите в «Другое».</li>
<li><b>Оплата:</b> наличными, картой, «Нал + карта» или «В долг».</li>
<li>Проверьте «Итого» и нажмите <b>«Сохранить»</b>.</li>
</ol>
<div class="hp-tip">Выбирайте товар из списка склада, а не пишите вручную. Тогда он сам спишется со склада[[MSB]], попадёт в прогноз «на сколько дней хватит»[[/]][[MS]] и войдёт в прибыль[[/]].</div>
<p>Если клиент привязан к боту, сразу после сохранения ему в Telegram придёт чек замены.</p>
"""),
uz=("Almashtirishni qanday kiritish — qadamma-qadam", """
<p>Qizil «Almashtirish» tugmasini bosing. Forma yuqoridan pastga to'ldiriladi:</p>
<ol class="hp-steps">
<li><b>Davlat raqami.</b> Raqamni yozing yoki 📷 ni bosib, kamerani raqamga qarating. Mashina bazada bo'lsa — «Mijoz tanildi» kartochkasi chiqadi, ism, telefon va marka o'zi to'ladi.</li>
<li><b>Egasining ismi va telefoni.</b> Telefon mijozga WhatsApp orqali havola yuborish va uning bir nechta mashinasini bog'lash uchun kerak.</li>
<li>Mashinaning <b>markasi va modeli</b>.</li>
<li><b>Probeg.</b> «Hozir» — odometrdagi raqam. «Almashtirish» — keyingi almashtirish qaysi probegda. +5 ming va +8 ming tugmalari o'zi hisoblaydi, «Boshqa…» — sizning intervalingizni eslab qoladi.</li>
<li><b>«Kuniga» (ixtiyoriy)</b> — mijoz kuniga qancha yuradi. Shunda OilBook keyingi almashtirishning taxminiy sanasini hisoblaydi.</li>
<li><b>«Necha vaqtdan keyin eslatish kerak?»</b> — mijozga necha oy yoki kundan keyin eslatma borishi.</li>
<li><b>Tovarlar va ish.</b> Mahsulotni «Tez qidirish»da toping (masalan, <i>mit 5w30</i>) yoki moy, filtr va suyuqliklarni ro'yxatdan tanlang. Mahsulotsiz ish va xizmatlarni (yuvish, sham almashtirish) «Boshqa»ga yozing.</li>
<li><b>To'lov:</b> naqd, karta bilan, «Naqd + karta» yoki «Qarzga».</li>
<li>«Jami»ni tekshiring va <b>«Saqlash»</b>ni bosing.</li>
</ol>
<div class="hp-tip">Mahsulotni qo'lda yozmang, ombor ro'yxatidan tanlang. Shunda u ombordan o'zi chiqariladi[[MSB]], «necha kunga yetadi» prognoziga tushadi[[/]][[MS]] va foydaga qo'shiladi[[/]].</div>
<p>Mijoz botga bog'langan bo'lsa, saqlangan zahoti unga Telegramda almashtirish cheki boradi.</p>
""")),

dict(id="scanner", sec="service", roles=ALL, go="add",
kw="камера сканер номер распознать фото фонарик kamera skaner raqam",
ru=("Сканировать госномер камерой", """
<ol class="hp-steps">
<li>В форме замены нажмите 📷 рядом с полем «Госномер».</li>
<li>Разрешите доступ к камере, если телефон спросит.</li>
<li>Наведите камеру так, чтобы номер занял всю рамку. Темно — включите «Фонарик».</li>
<li>OilBook покажет результат:
<ul>
<li><b>«ЕСТЬ В БАЗЕ»</b> — нажмите «Это он», данные клиента подставятся;</li>
<li><b>«ВОЗМОЖНО ЭТО»</b> — похожий номер из базы, проверьте;</li>
<li><b>«НОВЫЙ КЛИЕНТ»</b> — номера в базе нет, заполните остальное.</li>
</ul></li>
</ol>
<div class="hp-tip">Номер распознаётся прямо на телефоне. Фото никуда не отправляется и не сохраняется. В первый раз распознавание загружается несколько секунд.</div>
<p>Если камера не открывается — откройте OilBook в Chrome (Android) или Safari (iPhone) и разрешите камеру для сайта в настройках браузера.</p>
"""),
uz=("Davlat raqamini kamera bilan skanerlash", """
<ol class="hp-steps">
<li>Almashtirish formasida «Davlat raqami» yonidagi 📷 ni bosing.</li>
<li>Telefon so'rasa, kameraga ruxsat bering.</li>
<li>Kamerani raqam butun ramkani egallaydigan qilib qarating. Qorong'i bo'lsa — «Chiroq»ni yoqing.</li>
<li>OilBook natijani ko'rsatadi:
<ul>
<li><b>«BAZADA BOR»</b> — «Ha, shu»ni bosing, mijoz ma'lumotlari qo'yiladi;</li>
<li><b>«BALKI BU»</b> — bazadagi o'xshash raqam, tekshiring;</li>
<li><b>«YANGI MIJOZ»</b> — raqam bazada yo'q, qolganini to'ldiring.</li>
</ul></li>
</ol>
<div class="hp-tip">Raqam telefonning o'zida aniqlanadi. Rasm hech qayerga yuborilmaydi va saqlanmaydi. Birinchi marta aniqlash tizimi bir necha soniya yuklanadi.</div>
<p>Kamera ochilmasa — OilBook'ni Chrome (Android) yoki Safari (iPhone) da oching va brauzer sozlamalarida saytga kamera ruxsatini bering.</p>
""")),

dict(id="repeat", sec="service", roles=ALL, go="add",
kw="повторить прошлую замену постоянный клиент takrorlash doimiy mijoz",
ru=("Постоянный клиент: повторить прошлую замену", """
<p>Когда номер уже есть в базе, появляется карточка «Клиент узнан»: последний визит, пробег тогда и плановая замена. Если клиент перебрал пробег, вы это сразу увидите.</p>
<p>Зелёная кнопка <b>«Повторить прошлую замену»</b> заполнит масло, фильтры, литры и работы как в прошлый раз. Цены берутся текущие, со склада. Останется вписать пробег и сохранить.</p>
<div class="hp-tip">Если какого-то товара из прошлой замены уже нет на складе, строка останется пустой с подсказкой — выберите замену вручную.</div>
"""),
uz=("Doimiy mijoz: o'tgan almashtirishni takrorlash", """
<p>Raqam bazada bo'lsa, «Mijoz tanildi» kartochkasi chiqadi: oxirgi tashrif, o'shandagi probeg va rejadagi almashtirish. Mijoz probegdan oshib ketgan bo'lsa, buni darhol ko'rasiz.</p>
<p>Yashil <b>«O'tgan almashtirishni takrorlash»</b> tugmasi moy, filtr, litr va ishlarni o'tgan safargidek to'ldiradi. Narxlar hozirgi, ombordagi narxlar bo'ladi. Faqat probegni yozib saqlash qoladi.</p>
<div class="hp-tip">O'tgan almashtirishdagi biror mahsulot omborda qolmagan bo'lsa, qator bo'sh qoladi va maslahat chiqadi — o'rniga boshqasini qo'lda tanlang.</div>
""")),

dict(id="new_owner", sec="service", roles=ALL,
kw="машину продали новый владелец сменить владельца sotildi yangi egasi",
ru=("Машину продали — новый владелец", """
<ol class="hp-steps">
<li>Введите госномер — появится карточка «Клиент узнан».</li>
<li>Нажмите «Новый владелец (машину продали)».</li>
<li>Впишите имя и телефон нового владельца и сохраните замену.</li>
</ol>
<p>История машины сохранится, а напоминания будут приходить уже новому владельцу. Прежний владелец останется в базе со своими другими машинами.</p>
<div class="hp-warn">Если за машиной остался долг прежнего владельца, сначала закройте его в «Долгах».</div>
"""),
uz=("Mashina sotildi — yangi egasi", """
<ol class="hp-steps">
<li>Davlat raqamini kiriting — «Mijoz tanildi» kartochkasi chiqadi.</li>
<li>«Yangi egasi (mashina sotilgan)»ni bosing.</li>
<li>Yangi egasining ismi va telefonini yozing va almashtirishni saqlang.</li>
</ol>
<p>Mashina tarixi saqlanadi, eslatmalar esa endi yangi egasiga boradi. Oldingi egasi boshqa mashinalari bilan bazada qoladi.</p>
<div class="hp-warn">Mashinada oldingi egasining qarzi qolgan bo'lsa, avval uni «Qarzlar»da yoping.</div>
""")),

dict(id="base", sec="service", roles=ALL, go="table",
kw="база клиентов поиск история машина найти baza qidirish tarix",
ru=("База клиентов: найти машину и историю", """
<ul>
<li>В «Базе» ищите по госномеру или имени — список сужается, пока вы печатаете.</li>
<li>Сверху видно, сколько всего клиентов и машин. Внизу списка — «Показать ещё».</li>
<li>Нажмите «подробнее» в строке — откроется вся история замен этой машины: что меняли, пробег, сумма, заметки.</li>
<li>Если машина обслуживалась в других точках вашей сети, там же будет блок «История на других точках сети» — что и когда делали, без цен.</li>
</ul>
"""),
uz=("Mijozlar bazasi: mashina va tarixni topish", """
<ul>
<li>«Baza»da davlat raqami yoki ism bo'yicha qidiring — yozganingiz sari ro'yxat qisqarib boradi.</li>
<li>Yuqorida jami mijozlar va mashinalar soni ko'rinadi. Ro'yxat pastida — «Yana ko'rsatish».</li>
<li>Qatordagi «batafsil»ni bosing — shu mashinaning butun almashtirish tarixi ochiladi: nima almashtirilgan, probeg, summa, izohlar.</li>
<li>Mashina tarmog'ingizning boshqa nuqtalarida xizmat ko'rgan bo'lsa, o'sha yerda «Tarmoqdagi boshqa nuqtalardagi tarix» bloki bo'ladi — nima va qachon qilingani, narxlarsiz.</li>
</ul>
""")),

dict(id="fix_entry", sec="service", roles=ALL, go="table",
kw="ошибка исправить изменить удалить запись цена неправильно xato tuzatish o'chirish",
ru=("Исправить или удалить запись о замене", """
<ol class="hp-steps">
<li>Откройте «Базу» и найдите машину.</li>
<li>Откройте её историю («подробнее»).</li>
<li>У нужной записи нажмите «✏️ Изменить» — поправьте цену, пробег, товары — и сохраните. Или «🗑️ Удалить», если запись внесли по ошибке.</li>
</ol>
<p>Имя, телефон, марку и модель машины меняют кнопкой «✏️ Изменить данные» в карточке клиента.</p>
<div class="hp-warn">«🗑️ Удалить машину» стирает машину вместе со всей историей и долгами. Отменить это нельзя.</div>
"""),
uz=("Almashtirish yozuvini tuzatish yoki o'chirish", """
<ol class="hp-steps">
<li>«Baza»ni oching va mashinani toping.</li>
<li>Uning tarixini oching («batafsil»).</li>
<li>Kerakli yozuvda «✏️ O'zgartirish»ni bosing — narx, probeg, mahsulotlarni tuzating va saqlang. Yoki yozuv xato kiritilgan bo'lsa «🗑️ O'chirish».</li>
</ol>
<p>Mashinaning ismi, telefoni, markasi va modeli mijoz kartochkasidagi «✏️ Ma'lumotlarni o'zgartirish» tugmasi bilan o'zgartiriladi.</p>
<div class="hp-warn">«🗑️ Avtomobilni o'chirish» mashinani butun tarixi va qarzlari bilan birga o'chiradi. Buni qaytarib bo'lmaydi.</div>
""")),

dict(id="passport", sec="service", roles=ALL,
kw="сервисный паспорт ссылка история машины pdf servis pasporti",
ru=("Сервисный паспорт машины", """
<p>Сервисный паспорт — страница со всей историей обслуживания машины. Её удобно отправить клиенту или покупателю машины.</p>
<ol class="hp-steps">
<li>Введите госномер в форме замены — появится карточка «Клиент узнан».</li>
<li>Нажмите «Сервисный паспорт» — ссылка скопируется.</li>
<li>Вставьте её в Telegram или WhatsApp клиенту. Со страницы паспорта можно скачать PDF.</li>
</ol>
"""),
uz=("Mashinaning servis pasporti", """
<p>Servis pasporti — mashinaning butun xizmat tarixi yozilgan sahifa. Uni mijozga yoki mashina xaridoriga yuborish qulay.</p>
<ol class="hp-steps">
<li>Almashtirish formasida davlat raqamini kiriting — «Mijoz tanildi» kartochkasi chiqadi.</li>
<li>«Servis pasporti»ni bosing — havola nusxalanadi.</li>
<li>Uni mijozga Telegram yoki WhatsApp'da yuboring. Pasport sahifasidan PDF yuklab olish mumkin.</li>
</ol>
""")),

# ======================================================================
# ДОЛГИ И РАСХОДЫ
# ======================================================================
dict(id="debt_add", sec="money", roles=ALL, go="add",
kw="долг рассрочка в долг нет денег qarz bo'lib to'lash",
ru=("Замена в долг или в рассрочку", """
<ol class="hp-steps">
<li>Заполните замену как обычно.</li>
<li>В «Оплате» выберите <b>«В долг»</b>.</li>
<li>Если клиент часть оплатил сразу — впишите эту сумму в «Наличными» и/или «Картой». Остаток станет долгом.</li>
<li>Укажите <b>«Платёж (сум)»</b> — сколько клиент платит за раз, и <b>«Каждые (дней)»</b> — как часто.</li>
<li>Сохраните.</li>
</ol>
<p>Когда подойдёт срок, клиенту придёт напоминание в Telegram. Если клиент к боту не привязан — напоминание придёт вам, чтобы вы позвонили сами.</p>
"""),
uz=("Qarzga yoki bo'lib to'lashga almashtirish", """
<ol class="hp-steps">
<li>Almashtirishni odatdagidek to'ldiring.</li>
<li>«To'lov»da <b>«Qarzga»</b>ni tanlang.</li>
<li>Mijoz bir qismini darhol to'lagan bo'lsa — shu summani «Naqd» va/yoki «Karta bilan»ga yozing. Qolgani qarz bo'ladi.</li>
<li><b>«To'lov (so'm)»</b> — mijoz bir martada qancha to'lashi va <b>«Har (kun)»</b> — qanchalik tez-tez to'lashini kiriting.</li>
<li>Saqlang.</li>
</ol>
<p>Muddat kelganda mijozga Telegramda eslatma boradi. Mijoz botga bog'lanmagan bo'lsa — eslatma sizga keladi, o'zingiz qo'ng'iroq qilasiz.</p>
""")),

dict(id="debt_pay", sec="money", roles=ALL, go="debts",
kw="принять платёж долг оплатил должник просрочено qarz to'lov qabul qilish",
ru=("Принять платёж по долгу", """
<ol class="hp-steps">
<li>Откройте «Долги». Просроченные долги отмечены красным.</li>
<li>У нужного клиента впишите сумму, которую он принёс.</li>
<li>Нажмите «Оплатить».</li>
</ol>
<p>Остаток долга и дата следующего платежа пересчитаются сами. Когда долг погашен полностью, клиент исчезает из списка.</p>
"""),
uz=("Qarz bo'yicha to'lov qabul qilish", """
<ol class="hp-steps">
<li>«Qarzlar»ni oching. Muddati o'tgan qarzlar qizil bilan belgilangan.</li>
<li>Kerakli mijoz qatorida u olib kelgan summani yozing.</li>
<li>«To'lash»ni bosing.</li>
</ol>
<p>Qarz qoldig'i va keyingi to'lov sanasi o'zi qayta hisoblanadi. Qarz to'liq yopilganda mijoz ro'yxatdan chiqadi.</p>
""")),

dict(id="expenses", sec="money", roles=NOT_EMP, go="expenses",
kw="расходы аренда зарплата свет повторяющиеся журнал xarajat ijara",
ru=("Расходы: разовые и повторяющиеся", """
<p><b>Разовый расход</b> (реклама, ремонт, инструмент):</p>
<ol class="hp-steps">
<li>«Расходы» → «Добавить расход».</li>
<li>Выберите категорию или «+ Своя категория», впишите сумму и дату.</li>
<li>Нажмите «Добавить расход».</li>
</ol>
<p><b>Повторяющийся расход</b> (аренда, интернет, зарплата): в блоке «Повторяющиеся расходы» укажите название, сумму и число месяца. В этот день бот напомнит в Telegram, а вы нажмёте «Отметить оплаченным» — расход попадёт в журнал.</p>
<p>Все расходы видны в «Журнале расходов». Ошибочную запись можно удалить.</p>
[[MS]]<div class="hp-tip">Расходы вычитаются из прибыли: «Чистая прибыль» в статистике = прибыль с товаров + работа и услуги − расходы.</div>[[/]]
"""),
uz=("Xarajatlar: bir martalik va takrorlanuvchi", """
<p><b>Bir martalik xarajat</b> (reklama, ta'mir, asbob):</p>
<ol class="hp-steps">
<li>«Xarajatlar» → «Xarajat qo'shish».</li>
<li>Toifani yoki «+ O'z toifam»ni tanlang, summa va sanani yozing.</li>
<li>«Xarajat qo'shish»ni bosing.</li>
</ol>
<p><b>Takrorlanuvchi xarajat</b> (ijara, internet, maosh): «Takrorlanuvchi xarajatlar» blokida nomi, summasi va oyning sanasini kiriting. O'sha kuni bot Telegramda eslatadi, siz «To'langan deb belgilash»ni bosasiz — xarajat jurnalga tushadi.</p>
<p>Barcha xarajatlar «Xarajatlar jurnali»da ko'rinadi. Xato yozuvni o'chirish mumkin.</p>
[[MS]]<div class="hp-tip">Xarajatlar foydadan ayiriladi: statistikadagi «Sof foyda» = mahsulotlar foydasi + ish va xizmatlar − xarajatlar.</div>[[/]]
""")),

# ======================================================================
# НАПОМИНАНИЯ И РАССЫЛКА
# ======================================================================
dict(id="client_bot", sec="reach", roles=ALL, go="table",
kw="напоминание клиенту привязать бот ссылка qr whatsapp eslatma mijoz bog'lash havola",
ru=("Привязать клиента к боту — чтобы приходили напоминания", """
<p>Напоминание о замене приходит клиенту в Telegram, только если он один раз привязался к боту.</p>
<ol class="hp-steps">
<li>В «Базе» у клиента без бота нажмите «показать ссылку».</li>
<li>Покажите клиенту QR-код, чтобы он навёл камеру, или нажмите «Отправить в WhatsApp» / «Отправить в Telegram».</li>
<li>Клиент открывает ссылку и нажимает «Start» — всё, он привязан. В строке появится отметка «привязан».</li>
</ol>
<p>Что получает клиент:</p>
<ul>
<li>чек после каждой замены;</li>
<li>напоминание, когда подходит срок, с кнопками «✅ Уже поменял» и «📅 Записаться»;</li>
<li>повторное напоминание, если клиент не ответил;</li>
<li>напоминания о платежах по рассрочке.</li>
</ul>
<div class="hp-tip">Лучше привязывать клиента прямо на месте, пока он ждёт машину. Это занимает 20 секунд.</div>
"""),
uz=("Mijozni botga bog'lash — eslatmalar kelishi uchun", """
<p>Almashtirish haqidagi eslatma mijozga Telegramda faqat u bir marta botga bog'langan bo'lsa keladi.</p>
<ol class="hp-steps">
<li>«Baza»da botga bog'lanmagan mijoz qatorida «havolani ko'rsatish»ni bosing.</li>
<li>Mijozga QR-kodni ko'rsating, u kamerasini qaratadi. Yoki «WhatsApp orqali yuborish» / «Telegram orqali yuborish»ni bosing.</li>
<li>Mijoz havolani ochib, «Start»ni bosadi — tamom, u bog'landi. Qatorda «bog'langan» belgisi paydo bo'ladi.</li>
</ol>
<p>Mijoz nimalarni oladi:</p>
<ul>
<li>har bir almashtirishdan keyin chek;</li>
<li>muddat kelganda «✅ Allaqachon almashtirdim» va «📅 Yozilish» tugmalari bilan eslatma;</li>
<li>javob bermasa — takroriy eslatma;</li>
<li>bo'lib to'lash bo'yicha to'lov eslatmalari.</li>
</ul>
<div class="hp-tip">Mijozni joyida, mashinasini kutib turganida bog'lagan ma'qul. Bu 20 soniya oladi.</div>
""")),

dict(id="broadcast", sec="reach", roles=ALL, go="broadcast",
kw="рассылка акция скидка объявление отправить всем xabarnoma aksiya chegirma",
ru=("Рассылка акций клиентам", """
<ol class="hp-steps">
<li>Откройте «Рассылку».</li>
<li>Напишите текст, например: «Скидка 15% на масла MITANOL до конца месяца!».</li>
<li>Под полем видно, сколько клиентов получат сообщение — это те, кто привязан к боту.</li>
<li>Нажмите «📢 Отправить всем привязанным клиентам» и подтвердите.</li>
</ol>
<p>Сообщения уходят в течение примерно 15 секунд. Ниже показаны последние рассылки: сколько доставлено и сколько не удалось.</p>
<div class="hp-warn">Не отправляйте рассылки слишком часто — клиенты могут остановить бота, и тогда перестанут получать и напоминания о замене.</div>
"""),
uz=("Mijozlarga aksiya yuborish", """
<ol class="hp-steps">
<li>«Xabarnoma»ni oching.</li>
<li>Matnni yozing, masalan: «Oy oxirigacha MITANOL moylariga 15% chegirma!».</li>
<li>Maydon ostida xabarni nechta mijoz olishi ko'rinadi — bular botga bog'langanlar.</li>
<li>«📢 Barcha bog'langan mijozlarga yuborish»ni bosing va tasdiqlang.</li>
</ol>
<p>Xabarlar taxminan 15 soniya ichida jo'natiladi. Pastda oxirgi xabarnomalar ko'rsatiladi: qanchasi yetkazildi va qanchasi yetmadi.</p>
<div class="hp-warn">Xabarnomani juda tez-tez yubormang — mijozlar botni to'xtatib qo'yishi mumkin, shunda almashtirish eslatmalari ham bormay qoladi.</div>
""")),

dict(id="sms", sec="reach", roles=NOT_EMP, need="sms", go="sms",
kw="смс eskiz напоминание без телеграма sms",
ru=("SMS-напоминания через Eskiz", """
<p>SMS нужны для клиентов без Telegram. Они отправляются через ваш собственный аккаунт Eskiz.uz, поэтому договор с Eskiz вы оформляете сами, на своё юрлицо.</p>
<ol class="hp-steps">
<li>Зарегистрируйтесь на eskiz.uz и оформите договор.</li>
<li>Откройте вкладку «SMS» в OilBook.</li>
<li>Впишите email и пароль от аккаунта Eskiz и сохраните.</li>
</ol>
<p>После этого клиенты без Telegram будут получать напоминание о замене по SMS. Оплата SMS — по тарифу Eskiz, с вашего баланса там.</p>
"""),
uz=("Eskiz orqali SMS eslatmalar", """
<p>SMS Telegrami yo'q mijozlar uchun kerak. Ular o'zingizning Eskiz.uz akkauntingiz orqali yuboriladi, shuning uchun Eskiz bilan shartnomani o'zingiz, o'z yuridik shaxsingizga tuzasiz.</p>
<ol class="hp-steps">
<li>eskiz.uz saytida ro'yxatdan o'ting va shartnoma tuzing.</li>
<li>OilBook'da «SMS» bo'limini oching.</li>
<li>Eskiz akkauntining email va parolini yozing va saqlang.</li>
</ol>
<p>Shundan keyin Telegrami yo'q mijozlarga almashtirish eslatmasi SMS orqali boradi. SMS uchun to'lov Eskiz tarifi bo'yicha, u yerdagi balansingizdan.</p>
""")),

# ======================================================================
# СКЛАД
# ======================================================================
dict(id="wh_basics", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="склад как работает остаток списание товар ombor qoldiq",
ru=("Как работает склад", """
<p>На складе хранится каждый товар: тип (моторное масло, фильтр…), название, единица (литр или штука), цена продажи[[MS]], цена закупки[[/]] и остаток.</p>
<ul>
<li>Когда в замене вы выбираете товар из списка склада, остаток уменьшается сам.</li>
<li>Когда товар приходит — делаете «Пополнить», остаток растёт.</li>
<li>Если пересчитали товар и цифра не сходится — исправляете остаток через ✏️ с причиной.</li>
</ul>
<p>Вверху «Мой склад» — сводка[[MS]]: стоимость остатка по закупке, наценка, если продать всё[[/]], сколько товаров заканчивается и сколько лежит без продаж 30 дней. Блок «Требует внимания» показывает, что нужно заказать в первую очередь.</p>
<p>На карточке товара есть прогноз: «~2 л/день · хватит на 9 дн. · заказать 40». Он считается по заменам, где товар выбран со склада.</p>
"""),
uz=("Ombor qanday ishlaydi", """
<p>Omborda har bir mahsulot saqlanadi: turi (motor moyi, filtr…), nomi, o'lchov birligi (litr yoki dona), sotuv narxi[[MS]], xarid narxi[[/]] va qoldiq.</p>
<ul>
<li>Almashtirishda mahsulotni ombor ro'yxatidan tanlasangiz, qoldiq o'zi kamayadi.</li>
<li>Mahsulot kelganda — «To'ldirish» qilasiz, qoldiq oshadi.</li>
<li>Sanab chiqib, raqam to'g'ri kelmasa — qoldiqni ✏️ orqali sababini yozib tuzatasiz.</li>
</ul>
<p>«Mening omborim» tepasida — umumiy ko'rinish[[MS]]: qoldiqning xarid narxidagi qiymati, hammasi sotilsa ustama[[/]], nechta mahsulot tugayapti va nechtasi 30 kun sotilmay yotibdi. «E'tibor talab qiladi» bloki birinchi navbatda nimani buyurtma qilish kerakligini ko'rsatadi.</p>
<p>Mahsulot kartochkasida prognoz bor: «~2 l/kun · 9 kunga yetadi · buyurtma: 40». U mahsulot ombordan tanlangan almashtirishlar bo'yicha hisoblanadi.</p>
""")),

dict(id="wh_add", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="добавить товар новый товар цена закупки продажи mahsulot qo'shish narx",
ru=("Добавить товар на склад", """
<ol class="hp-steps">
<li>«Склад» → «Мой склад» → кнопка «+ Товар».</li>
<li>Выберите тип. Для того, чего нет в списке (свечи, лампы, присадки), выберите «Прочее» и впишите своё название.</li>
<li>Впишите название с маркой и вязкостью, например <i>MITANOL 5W-30 SP</i>.</li>
<li>Выберите единицу: литры для масла на разлив, штуки для фильтров и канистр.</li>
<li>Укажите цену продажи[[MS]] и цену закупки[[/]] за единицу, начальный остаток — и добавьте.</li>
</ol>
[[MS]]<div class="hp-warn">Цена закупки — за ту же единицу, что и продажа. Если масло продаётся литрами, пишите цену закупки за литр, а не за канистру. Иначе прибыль посчитается неправильно.</div>[[/]]
<div class="hp-tip">Если задан курс доллара, цены можно вписывать в $ — они переведутся в сумы.</div>
"""),
uz=("Omborga mahsulot qo'shish", """
<ol class="hp-steps">
<li>«Ombor» → «Mening omborim» → «+ Mahsulot» tugmasi.</li>
<li>Turini tanlang. Ro'yxatda yo'q narsalar uchun (sham, lampa, prisadka) «Boshqa»ni tanlab, o'z nomingizni yozing.</li>
<li>Nomini marka va qovushqoqligi bilan yozing, masalan <i>MITANOL 5W-30 SP</i>.</li>
<li>O'lchov birligini tanlang: quyma moy uchun litr, filtr va kanistrlar uchun dona.</li>
<li>Bir birlik uchun sotuv narxi[[MS]] va xarid narxini[[/]], boshlang'ich qoldiqni kiriting va qo'shing.</li>
</ol>
[[MS]]<div class="hp-warn">Xarid narxi sotuvdagi birlik uchun yoziladi. Moy litrlab sotilsa, xarid narxini kanistr emas, litr uchun yozing. Aks holda foyda noto'g'ri hisoblanadi.</div>[[/]]
<div class="hp-tip">Dollar kursi kiritilgan bo'lsa, narxlarni $ da yozish mumkin — ular so'mga o'giriladi.</div>
""")),

dict(id="wh_restock", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="пополнить приход товар привезли to'ldirish keldi",
ru=("Пополнить склад (приход товара)", """
<ol class="hp-steps">
<li>На складе найдите товар (поиск или фильтр по типу).</li>
<li>На его карточке нажмите «Пополнить».</li>
<li>Впишите, сколько пришло, и дату — нажмите «Пополнить».</li>
</ol>
<p>Приход сохраняется в «Движении товара».[[MS]] Если товар приходит от поставщика по заказу, удобнее принимать его через «Поставщики» — тогда сразу запишутся цены закупки и долг поставщику.[[/]]</p>
"""),
uz=("Omborni to'ldirish (mahsulot kirimi)", """
<ol class="hp-steps">
<li>Omborda mahsulotni toping (qidiruv yoki tur bo'yicha filtr).</li>
<li>Uning kartochkasida «To'ldirish»ni bosing.</li>
<li>Qancha kelganini va sanani yozing — «To'ldirish»ni bosing.</li>
</ol>
<p>Kirim «Mahsulot harakati»da saqlanadi.[[MS]] Mahsulot yetkazib beruvchidan buyurtma bo'yicha kelsa, uni «Yetkazib beruvchilar» orqali qabul qilish qulayroq — shunda xarid narxlari va yetkazib beruvchiga qarz birdaniga yoziladi.[[/]]</p>
""")),

dict(id="wh_edit", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="изменить товар цена пересчёт остаток корректировка ошибся mahsulot o'zgartirish qoldiq",
ru=("Изменить товар, цену или остаток", """
<p>На карточке товара нажмите ✏️. Можно изменить:</p>
<ul>
<li><b>название</b> — в старых записях останется прежнее;</li>
<li><b>цену продажи</b>[[MS]] и <b>цену закупки</b>[[/]] — новые цены действуют для следующих продаж;</li>
<li><b>фактический остаток</b> — только после пересчёта. Впишите причину («пересчёт», «брак», «пролили») — изменение попадёт в историю как «корректировка».</li>
</ul>
<p>Тип и единицу изменить нельзя. Если ошиблись в них — заведите товар заново.</p>
[[MS]]<div class="hp-tip">Если у товара раньше не было цены закупки и вы её впервые вписали, она сама проставится во все прошлые продажи этого товара — и они войдут в прибыль. Замена одной цены на другую прошлые продажи не меняет.</div>[[/]]
"""),
uz=("Mahsulot, narx yoki qoldiqni o'zgartirish", """
<p>Mahsulot kartochkasida ✏️ ni bosing. O'zgartirish mumkin:</p>
<ul>
<li><b>nomi</b> — eski yozuvlarda avvalgisi qoladi;</li>
<li><b>sotuv narxi</b>[[MS]] va <b>xarid narxi</b>[[/]] — yangi narxlar keyingi sotuvlardan amal qiladi;</li>
<li><b>haqiqiy qoldiq</b> — faqat sanab chiqqandan keyin. Sababini yozing («sanoq», «brak», «to'kilib ketdi») — o'zgarish tarixga «tuzatish» bo'lib tushadi.</li>
</ul>
<p>Tur va o'lchov birligini o'zgartirib bo'lmaydi. Ularda xato qilsangiz — mahsulotni qaytadan kiriting.</p>
[[MS]]<div class="hp-tip">Agar mahsulotning avval xarid narxi bo'lmagan bo'lsa va siz uni birinchi marta yozsangiz, u shu mahsulotning barcha o'tgan sotuvlariga o'zi qo'yiladi — va ular foydaga qo'shiladi. Bir narxni boshqasiga almashtirish o'tgan sotuvlarni o'zgartirmaydi.</div>[[/]]
""")),

dict(id="wh_purchase", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="список закупки что заказать заказ telegram xarid ro'yxati buyurtma",
ru=("Список закупки: что заказать", """
<p>Кнопка «Список закупки» на складе собирает, сколько товара заказать, чтобы хватило примерно на месяц. Считается по продажам за последние 30 дней.</p>
<ol class="hp-steps">
<li>Откройте «Список закупки».</li>
<li>Отметьте нужные товары и поправьте количество.</li>
<li>Нажмите «Отправить в Telegram» или «Скопировать» и вставьте в чат с поставщиком[[B]] или с главной точкой[[/]].</li>
</ol>
[[MS]]<p>Если вы работаете с поставщиками в OilBook, нажмите «Оформить заказ поставщику» — список превратится в заказ во вкладке «Поставщики».</p>[[/]]
"""),
uz=("Xarid ro'yxati: nimani buyurtma qilish", """
<p>Ombordagi «Xarid ro'yxati» tugmasi taxminan bir oyga yetadigan qilib qancha mahsulot buyurtma qilish kerakligini yig'adi. So'nggi 30 kunlik sotuvlar bo'yicha hisoblanadi.</p>
<ol class="hp-steps">
<li>«Xarid ro'yxati»ni oching.</li>
<li>Kerakli mahsulotlarni belgilang va miqdorini to'g'rilang.</li>
<li>«Telegramga yuborish» yoki «Nusxalash»ni bosing va yetkazib beruvchi[[B]] yoki bosh nuqta[[/]] bilan chatga qo'ying.</li>
</ol>
[[MS]]<p>Yetkazib beruvchilar bilan OilBook'da ishlasangiz, «Yetkazib beruvchiga buyurtma berish»ni bosing — ro'yxat «Yetkazib beruvchilar» bo'limida buyurtmaga aylanadi.</p>[[/]]
""")),

dict(id="wh_excel", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="excel импорт загрузить прайс шаблон много товаров excel yuklash shablon",
ru=("Загрузить много товаров из Excel", """
<ol class="hp-steps">
<li>На складе откройте «Загрузить склад из Excel» и скачайте «Шаблон».</li>
<li>Заполните его: одна строка — один товар. Тип выбирается из выпадающего списка. Можно взять свой прайс, если колонки называются похоже.</li>
<li>Загрузите файл. OilBook покажет предпросмотр: новые товары, пополнения и строки с ошибками.</li>
<li>Нажмите «Загрузить».</li>
</ol>
<p>Если товар уже есть на складе, количество добавится как пополнение. Строки с ошибками пропускаются — исправьте их в Excel и загрузите файл ещё раз.</p>
[[B]]<p>У филиала колонка «Цена закупки» не учитывается — её вносит главная точка.</p>[[/]]
"""),
uz=("Ko'p mahsulotni Excel'dan yuklash", """
<ol class="hp-steps">
<li>Omborda «Omborni Excel'dan yuklash»ni oching va «Shablon»ni yuklab oling.</li>
<li>Uni to'ldiring: bir qator — bitta mahsulot. Tur ochiladigan ro'yxatdan tanlanadi. Ustunlar nomi o'xshash bo'lsa, o'z prayslistingizni ham olish mumkin.</li>
<li>Faylni yuklang. OilBook oldindan ko'rsatadi: yangi mahsulotlar, to'ldirishlar va xato qatorlar.</li>
<li>«Yuklash»ni bosing.</li>
</ol>
<p>Mahsulot omborda bo'lsa, miqdori to'ldirish sifatida qo'shiladi. Xato qatorlar o'tkazib yuboriladi — ularni Excel'da tuzatib, faylni qayta yuklang.</p>
[[B]]<p>Filialda «Xarid narxi» ustuni hisobga olinmaydi — uni bosh nuqta kiritadi.</p>[[/]]
""")),

dict(id="wh_usd", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="курс доллара доллар $ dollar kursi",
ru=("Курс доллара", """
<p>Если вы закупаете товар в долларах, задайте курс на «Складе» в блоке «Курс доллара». Тогда цены можно вводить в $, а OilBook переведёт их в сумы.</p>
<ul>
<li>Курс действует с момента сохранения. На уже добавленные товары он не влияет.</li>
<li>Тот же курс используется в «Расходах»[[MS]] и в расчётах с поставщиками[[/]].</li>
</ul>
[[B]]<p>Если свой курс не задан, филиал берёт курс главной точки — это написано под полем. Можно задать свой. Чтобы снова брать курс главной точки, очистите поле и сохраните.</p>[[/]]
"""),
uz=("Dollar kursi", """
<p>Mahsulotni dollarda xarid qilsangiz, «Ombor»dagi «Dollar kursi» blokida kursni kiriting. Shunda narxlarni $ da yozish mumkin, OilBook ularni so'mga o'giradi.</p>
<ul>
<li>Kurs saqlangan paytdan amal qiladi. Avval qo'shilgan mahsulotlarga ta'sir qilmaydi.</li>
<li>Shu kurs «Xarajatlar»da[[MS]] va yetkazib beruvchilar bilan hisob-kitobda[[/]] ishlatiladi.</li>
</ul>
[[B]]<p>O'z kursingiz kiritilmagan bo'lsa, filial bosh nuqtaning kursini oladi — bu maydon ostida yozilgan. O'zingiznikini kiritishingiz mumkin. Yana bosh nuqta kursini olish uchun maydonni tozalab saqlang.</p>[[/]]
""")),

dict(id="wh_moves", sec="warehouse", roles=NOT_EMP, need="warehouse", go="warehouse",
kw="движение товара история пополнений перемещения куда делся mahsulot harakati tarix",
ru=("Движение товара: куда делся товар", """
<p>«Движение товара» на складе — журнал всех изменений остатка, кроме продаж: пополнения, перемещения между точками и корректировки после пересчёта (с причиной).</p>
<p>Продажи видны в истории замен в «Базе»[[MSB]] и в прогнозе на карточке товара[[/]].</p>
"""),
uz=("Mahsulot harakati: mahsulot qayerga ketdi", """
<p>Ombordagi «Mahsulot harakati» — sotuvdan tashqari qoldiqning barcha o'zgarishlari jurnali: to'ldirishlar, nuqtalar orasidagi ko'chirishlar va sanoqdan keyingi tuzatishlar (sababi bilan).</p>
<p>Sotuvlar «Baza»dagi almashtirishlar tarixida[[MSB]] va mahsulot kartochkasidagi prognozda[[/]] ko'rinadi.</p>
""")),

# ======================================================================
# СЕТЬ ФИЛИАЛОВ
# ======================================================================
dict(id="net_branch_wh", sec="network", roles="M", need="warehouse", go="warehouse",
kw="склады филиалов цена закупки филиала пополнить филиал filial omborlari",
ru=("Склады филиалов", """
<p>«Склад» → «Склады филиалов». Сверху — плитки филиалов: сколько товаров и у скольких нет цены закупки.</p>
<ol class="hp-steps">
<li>Нажмите на филиал — откроется его склад так же подробно, как ваш.</li>
<li>Здесь вы можете пополнить товар филиала, изменить его через ✏️ (в том числе цену закупки) и переместить товар.</li>
</ol>
<div class="hp-warn">Филиал сам цену закупки не видит и не вводит. Пока вы её не укажете, его продажи этого товара не войдут в прибыль. Такие товары помечены «Без цены закупки».</div>
"""),
uz=("Filial omborlari", """
<p>«Ombor» → «Filial omborlari». Tepada — filiallar plitkalari: nechta mahsulot va nechtasida xarid narxi yo'q.</p>
<ol class="hp-steps">
<li>Filialni bosing — uning ombori siznikidek batafsil ochiladi.</li>
<li>Bu yerda filial mahsulotini to'ldirishingiz, ✏️ orqali o'zgartirishingiz (xarid narxini ham) va ko'chirishingiz mumkin.</li>
</ol>
<div class="hp-warn">Filial xarid narxini o'zi ko'rmaydi va kiritmaydi. Siz uni kiritmaguningizcha, filialning shu mahsulot bo'yicha sotuvlari foydaga qo'shilmaydi. Bunday mahsulotlar «Xarid narxi yo'q» deb belgilangan.</div>
""")),

dict(id="net_transfer", sec="network", roles="M", need="warehouse", go="warehouse",
kw="переместить отправить товары накладная филиалу сеть ko'chirish yuborish",
ru=("Отправить товар в филиал", """
<p>«Склад» → «Сеть и перемещения». Там таблица остатков всех точек: строки — товары, столбцы — точки. Мало — подсвечено, ноль — выделен.</p>
<p><b>Один товар:</b> нажмите на ячейку в таблице или «Переместить товар» → откуда, куда, сколько → «Переместить».</p>
<p><b>Много товаров сразу (накладная):</b></p>
<ol class="hp-steps">
<li>Нажмите «Отправить товары» и выберите филиал.</li>
<li>Впишите количество у нужных товаров — или нажмите «Заполнить по потребности», и OilBook сам подставит, чего филиалу не хватает.</li>
<li>Нажмите «Отправить». Всё уходит одной накладной: либо всё, либо ничего.</li>
</ol>
<p>Цена закупки уходит вместе с товаром, поэтому продажи филиала сразу считаются в прибыли.</p>
"""),
uz=("Filialga mahsulot yuborish", """
<p>«Ombor» → «Tarmoq va ko'chirish». U yerda barcha nuqtalar qoldiqlari jadvali: qatorlar — mahsulotlar, ustunlar — nuqtalar. Kami belgilangan, nol ajratib ko'rsatilgan.</p>
<p><b>Bitta mahsulot:</b> jadvaldagi katakni yoki «Mahsulotni ko'chirish»ni bosing → qayerdan, qayerga, qancha → «Ko'chirish».</p>
<p><b>Ko'p mahsulot birdaniga (nakladnoy):</b></p>
<ol class="hp-steps">
<li>«Mahsulot yuborish»ni bosing va filialni tanlang.</li>
<li>Kerakli mahsulotlar miqdorini yozing — yoki «Ehtiyojga qarab to'ldirish»ni bosing, OilBook filialga nima yetishmasligini o'zi qo'yadi.</li>
<li>«Yuborish»ni bosing. Hammasi bitta nakladnoy bilan ketadi: yo hammasi, yo hech narsa.</li>
</ol>
<p>Xarid narxi mahsulot bilan birga ketadi, shuning uchun filial sotuvlari darhol foydada hisoblanadi.</p>
""")),

dict(id="net_catalog", sec="network", roles="M", need="warehouse", go="warehouse",
kw="скопировать каталог новый филиал товары katalog nusxalash",
ru=("Скопировать каталог в новый филиал", """
<p>Чтобы не вводить товары нового филиала вручную:</p>
<ol class="hp-steps">
<li>«Сеть и перемещения» → «Скопировать каталог в филиал».</li>
<li>Выберите филиал и типы товаров.</li>
<li>Нажмите «Скопировать».</li>
</ol>
<p>Ваши товары появятся у филиала с остатком 0 и вашими ценами. Сам товар не перемещается. То, что у филиала уже есть, пропускается.</p>
"""),
uz=("Yangi filialga katalogni nusxalash", """
<p>Yangi filial mahsulotlarini qo'lda kiritmaslik uchun:</p>
<ol class="hp-steps">
<li>«Tarmoq va ko'chirish» → «Katalogni filialga nusxalash».</li>
<li>Filial va mahsulot turlarini tanlang.</li>
<li>«Nusxalash»ni bosing.</li>
</ol>
<p>Mahsulotlaringiz filialda 0 qoldiq va sizning narxlaringiz bilan paydo bo'ladi. Mahsulotning o'zi ko'chirilmaydi. Filialda bor narsalar o'tkazib yuboriladi.</p>
""")),

dict(id="net_stats", sec="network", roles="M", go="stats",
kw="все филиалы сравнение статистика сети filiallarni solishtirish",
ru=("Статистика всех филиалов", """
<p>«Статистика» → «Все филиалы».</p>
<ul>
<li><b>Сравнение филиалов</b> — таблица за неделю, месяц или год: выручка, изменение к прошлому периоду, услуги, средний чек, клиенты, прибыль, расходы, чистая прибыль и итог по сети. Лучший результат в колонке — зелёным.</li>
<li>⚠️ рядом с прибылью — у точки есть продажи без цены закупки, они не вошли в прибыль.</li>
<li>Нажмите на филиал в таблице или на графике — ниже откроется его «Подробная статистика», такая же, как у вашей точки. Можно выбрать и «Вся сеть».</li>
</ul>
"""),
uz=("Barcha filiallar statistikasi", """
<p>«Statistika» → «Barcha filiallar».</p>
<ul>
<li><b>Filiallarni solishtirish</b> — hafta, oy yoki yil uchun jadval: tushum, o'tgan davrga nisbatan o'zgarish, xizmatlar, o'rtacha chek, mijozlar, foyda, xarajatlar, sof foyda va tarmoq bo'yicha jami. Ustundagi eng yaxshi natija — yashil.</li>
<li>Foyda yonidagi ⚠️ — nuqtada xarid narxisiz sotuvlar bor, ular foydaga kirmagan.</li>
<li>Jadvalda yoki grafikda filialni bosing — pastda uning «Batafsil statistika»si ochiladi, xuddi nuqtangiznikidek. «Butun tarmoq»ni ham tanlash mumkin.</li>
</ul>
""")),

dict(id="branch_receive", sec="network", roles="B", need="warehouse", go="warehouse",
kw="получить товар от главной точки перемещение bosh nuqtadan mahsulot olish",
ru=("Как получить товар от главной точки", """
<p>Главная точка отправляет вам товар из своей панели. Он сам появляется на вашем складе — ничего нажимать не нужно. В «Движении товара» будет запись «перемещение из …».</p>
<p>Чтобы главная точка знала, что вам нужно, откройте «Список закупки», отметьте товары и нажмите «Отправить в Telegram» или «Скопировать».</p>
<p>Если товар привезли не от главной точки, сделайте «Пополнить» на карточке товара.</p>
"""),
uz=("Bosh nuqtadan mahsulotni qanday olish", """
<p>Bosh nuqta sizga mahsulotni o'z panelidan yuboradi. U omboringizda o'zi paydo bo'ladi — hech narsa bosish shart emas. «Mahsulot harakati»da «keldi: …» yozuvi bo'ladi.</p>
<p>Bosh nuqta sizga nima kerakligini bilishi uchun «Xarid ro'yxati»ni oching, mahsulotlarni belgilang va «Telegramga yuborish» yoki «Nusxalash»ni bosing.</p>
<p>Mahsulot bosh nuqtadan emas, boshqa joydan kelsa, mahsulot kartochkasida «To'ldirish» qiling.</p>
""")),

# ======================================================================
# ПОСТАВЩИКИ И ЗАКАЗЫ
# ======================================================================
dict(id="sup_add", sec="suppliers", roles=OWNERS, need="warehouse", go="suppliers",
kw="поставщик добавить контакты товары поставщика telegram yetkazib beruvchi qo'shish",
ru=("Добавить поставщика", """
<ol class="hp-steps">
<li>Откройте «Поставщики» и в меню «⋯» выберите «Добавить поставщика».</li>
<li>Впишите название, телефон для WhatsApp, Telegram, контакт менеджера, дни доставки и <b>срок оплаты в днях</b> — по нему OilBook поймёт, когда долг просрочен.</li>
<li>Сохраните, затем нажмите «Товары» и отметьте товары, которые берёте у этого поставщика. Тогда заказ будет собираться по поставщику.</li>
</ol>
<p><b>Заказы через бота.</b> В карточке поставщика нажмите «Отправить ссылку поставщику». Он один раз нажмёт «Start» в боте — и дальше ваши заказы будут уходить ему в Telegram одной кнопкой.</p>
<p>Поставщика, с которым больше не работаете, уберите в архив. Вся история (заказы, оплаты, цены) сохранится, его можно вернуть из «Архива поставщиков».</p>
"""),
uz=("Yetkazib beruvchi qo'shish", """
<ol class="hp-steps">
<li>«Yetkazib beruvchilar»ni oching va «⋯» menyusida «Yetkazib beruvchi qo'shish»ni tanlang.</li>
<li>Nomi, WhatsApp uchun telefon, Telegram, menejer kontakti, yetkazish kunlari va <b>kunlarda to'lov muddatini</b> yozing — shu bo'yicha OilBook qarz qachon muddati o'tganini biladi.</li>
<li>Saqlang, keyin «Mahsulotlar»ni bosib, shu yetkazib beruvchidan oladigan mahsulotlarni belgilang. Shunda buyurtma yetkazib beruvchi bo'yicha yig'iladi.</li>
</ol>
<p><b>Bot orqali buyurtmalar.</b> Yetkazib beruvchi kartochkasida «Havolani yetkazib beruvchiga yuborish»ni bosing. U botda bir marta «Start»ni bosadi — keyin buyurtmalaringiz unga Telegramda bitta tugma bilan boradi.</p>
<p>Endi ishlamaydigan yetkazib beruvchini arxivga oling. Butun tarix (buyurtmalar, to'lovlar, narxlar) saqlanadi, uni «Yetkazib beruvchilar arxivi»dan qaytarish mumkin.</p>
""")),

dict(id="sup_order", sec="suppliers", roles=OWNERS, need="warehouse", go="suppliers",
kw="заказ поставщику принять товар приёмка черновик отправить buyurtma qabul qilish",
ru=("Заказ поставщику: от черновика до склада", """
<ol class="hp-steps">
<li><b>Новый заказ.</b> Нажмите «+ новый заказ» и выберите поставщика. Список соберётся сам — по тому, что заканчивается у вас[[M]] и в филиалах[[/]], чтобы хватило примерно на месяц. Количество можно поправить, товары — добавить. Нового товара ещё нет на складе? Выберите «Новый товар (ещё нет на складе)».</li>
<li><b>Отправить.</b> «Отправить поставщику» → через бота, или скопировать текст для Telegram и WhatsApp. Поставщик видит только товары и количество, без ваших цен[[M]] и без разбивки по филиалам[[/]]. Заказ получает статус «Отправлен».</li>
<li><b>Принять.</b> Когда товар привезли, нажмите «Принять товар». Отметьте, сколько пришло на самом деле, и цену закупки за единицу. Если заплатили сразу — отметьте «Оплачено сразу». Нажмите «Принять на склад».</li>
[[M]]<li><b>Раздать.</b> OilBook предложит, сколько отправить каждому филиалу. Нажмите «Раздать по филиалам» или «Оставить всё у себя». Цена закупки уйдёт вместе с товаром.</li>[[/]]
</ol>
<p>Если товар привезли без заказа — создайте заказ и сразу нажмите «Уже привезли — принять».</p>
<div class="hp-warn">Указывайте цену закупки при приёмке. Без неё продажи этого товара не войдут в прибыль, а сумма не попадёт в долг поставщику.</div>
"""),
uz=("Yetkazib beruvchiga buyurtma: qoralamadan omborgacha", """
<ol class="hp-steps">
<li><b>Yangi buyurtma.</b> «+ yangi buyurtma»ni bosing va yetkazib beruvchini tanlang. Ro'yxat o'zi yig'iladi — sizda[[M]] va filiallarda[[/]] tugayotgan narsalar bo'yicha, taxminan bir oyga yetadigan qilib. Miqdorni tuzatish, mahsulot qo'shish mumkin. Yangi mahsulot hali omborda yo'qmi? «Yangi mahsulot (omborda hali yo'q)»ni tanlang.</li>
<li><b>Yuborish.</b> «Yetkazib beruvchiga yuborish» → bot orqali yoki Telegram va WhatsApp uchun matnni nusxalab. Yetkazib beruvchi faqat mahsulot va miqdorni ko'radi, narxlaringizni[[M]] va filiallar bo'yicha taqsimotni[[/]] ko'rmaydi. Buyurtma «Yuborilgan» holatiga o'tadi.</li>
<li><b>Qabul qilish.</b> Mahsulot kelganda «Mahsulotni qabul qilish»ni bosing. Haqiqatda qancha kelganini va bir birlik uchun xarid narxini belgilang. Darhol to'lagan bo'lsangiz — «Darhol to'langan»ni belgilang. «Omborga qabul qilish»ni bosing.</li>
[[M]]<li><b>Tarqatish.</b> OilBook har bir filialga qancha yuborishni taklif qiladi. «Filiallarga tarqatish» yoki «Hammasini o'zimda qoldirish»ni bosing. Xarid narxi mahsulot bilan birga ketadi.</li>[[/]]
</ol>
<p>Mahsulot buyurtmasiz keltirilsa — buyurtma yarating va darhol «Allaqachon keltirildi — qabul qilish»ni bosing.</p>
<div class="hp-warn">Qabul qilishda xarid narxini yozing. Usiz shu mahsulot sotuvlari foydaga kirmaydi, summa esa yetkazib beruvchiga qarzga tushmaydi.</div>
""")),

dict(id="sup_debt", sec="suppliers", roles=OWNERS, need="warehouse", go="suppliers",
kw="долг поставщику оплата акт сверки история цен просрочка qarz to'lov dalolatnoma",
ru=("Расчёты с поставщиком: долг, оплаты, акт сверки", """
<p>Каждый принятый заказ увеличивает долг поставщику, каждая оплата — уменьшает. Вверху «Поставщиков» видно, сколько вы должны всем и сколько из этого просрочено.</p>
<ul>
<li><b>Оплатить:</b> в карточке поставщика нажмите «Оплатить», впишите сумму в сумах или в $, способ (наличные, карта, перечисление) и дату. Курс дня запоминается — старые суммы в $ не меняются.</li>
<li><b>Старый долг:</b> «Долг вручную» — если долг был ещё до OilBook.</li>
<li><b>Ошиблись:</b> отмените запись. Она останется в истории зачёркнутой и не будет влиять на долг.</li>
<li><b>Акт сверки:</b> выберите период и нажмите «Скачать акт сверки (Excel)» — долг на начало, все приходы и оплаты, долг на конец. Можно отправить поставщику.</li>
<li><b>История цен закупки:</b> как менялись цены у этого поставщика.</li>
</ul>
<p>Когда долг просрочен, бот напомнит вам в Telegram.</p>
"""),
uz=("Yetkazib beruvchi bilan hisob-kitob: qarz, to'lovlar, dalolatnoma", """
<p>Har bir qabul qilingan buyurtma yetkazib beruvchiga qarzni oshiradi, har bir to'lov — kamaytiradi. «Yetkazib beruvchilar» tepasida hammaga qancha qarzdorligingiz va uning qanchasi muddati o'tgani ko'rinadi.</p>
<ul>
<li><b>To'lash:</b> yetkazib beruvchi kartochkasida «To'lash»ni bosing, summani so'm yoki $ da, usulini (naqd, karta, o'tkazma) va sanani yozing. Kun kursi eslab qolinadi — eski $ summalar o'zgarmaydi.</li>
<li><b>Eski qarz:</b> «Qo'lda qarz» — agar qarz OilBook'gacha bo'lgan bo'lsa.</li>
<li><b>Xato qildingizmi:</b> yozuvni bekor qiling. U tarixda chizilgan holda qoladi va qarzga ta'sir qilmaydi.</li>
<li><b>Solishtirish dalolatnomasi:</b> davrni tanlab «Dalolatnomani yuklab olish (Excel)»ni bosing — boshidagi qarz, barcha kirim va to'lovlar, oxiridagi qarz. Yetkazib beruvchiga yuborish mumkin.</li>
<li><b>Xarid narxlari tarixi:</b> shu yetkazib beruvchida narxlar qanday o'zgargan.</li>
</ul>
<p>Qarz muddati o'tganda bot sizga Telegramda eslatadi.</p>
""")),

# ======================================================================
# СТАТИСТИКА И ПРИБЫЛЬ
# ======================================================================
dict(id="stats", sec="stats", roles=NOT_EMP, go="stats",
kw="статистика выручка средний чек клиенты новые повторные период statistika tushum o'rtacha chek",
ru=("Как читать статистику", """
<ul>
<li><b>Сегодня</b> — выручка и визиты за день.</li>
<li><b>Неделя, месяц, год</b> — услуги, средний чек, клиенты (новые и повторные), оплата наличными и картой[[MS]], прибыль[[/]]. Процент — сравнение с таким же отрезком прошлого периода.</li>
<li><b>Средний чек</b> = выручка ÷ платные визиты. Визиты с ценой 0 не считаются.</li>
<li><b>Новые клиенты</b> пришли к вам впервые, <b>повторные</b> — уже бывали.</li>
<li><b>Выручка за 30 дней</b> — столбики по дням. Красный — лучший день, пунктир — среднее за рабочий день.</li>
<li><b>Бренды: что продаётся лучше всего</b> — топ-10 брендов в каждой категории за 30 дней, 3 месяца или год.</li>
<li><b>Произвольный период</b> — любые даты «с» и «по».</li>
</ul>
[[B]]<div class="hp-tip">Прибыль и закупочные цены филиалу не показываются — их видит главная точка.</div>[[/]]
"""),
uz=("Statistikani qanday o'qish", """
<ul>
<li><b>Bugun</b> — kunlik tushum va tashriflar.</li>
<li><b>Hafta, oy, yil</b> — xizmatlar, o'rtacha chek, mijozlar (yangi va takroriy), naqd va karta bilan to'lov[[MS]], foyda[[/]]. Foiz — o'tgan davrning xuddi shunday qismi bilan solishtirish.</li>
<li><b>O'rtacha chek</b> = tushum ÷ pullik tashriflar. Narxi 0 bo'lgan tashriflar hisoblanmaydi.</li>
<li><b>Yangi mijozlar</b> sizga birinchi marta kelgan, <b>takroriylar</b> — avval kelganlar.</li>
<li><b>30 kunlik tushum</b> — kunlar bo'yicha ustunlar. Qizil — eng yaxshi kun, punktir — ish kuni uchun o'rtacha.</li>
<li><b>Brendlar: nima ko'proq sotilmoqda</b> — har bir toifada 30 kun, 3 oy yoki yil bo'yicha top-10 brend.</li>
<li><b>Ixtiyoriy davr</b> — istalgan «dan» va «gacha» sanalar.</li>
</ul>
[[B]]<div class="hp-tip">Foyda va xarid narxlari filialga ko'rsatilmaydi — ularni bosh nuqta ko'radi.</div>[[/]]
""")),

dict(id="profit", sec="stats", roles=OWNERS, go="stats",
kw="прибыль как считается чистая прибыль наценка foyda qanday hisoblanadi sof foyda",
ru=("Как считается прибыль", """
<p>Прибыль состоит из двух частей:</p>
<ul>
<li><b>Прибыль по товарам</b> — по каждому товару со склада: цена продажи − цена закупки. Цена закупки запоминается в момент продажи, поэтому потом её изменение прошлую прибыль не трогает.</li>
<li><b>Работа и услуги</b> — всё, что вписано в «Другое» без товара (мойка, замена свечей и т.п.), идёт в прибыль целиком.</li>
</ul>
<p><b>Чистая прибыль</b> = прибыль по товарам + работа и услуги − расходы.</p>
<div class="hp-warn">Жёлтая плашка «Продажи на … не вошли в прибыль» значит, что часть выручки нельзя посчитать: у товара нет цены закупки, или масло и фильтр вписаны вручную, а не выбраны со склада. Впишите цену закупки на складе[[M]] (у филиала — в «Складах филиалов»)[[/]], и эти продажи сами добавятся в прибыль.</div>
"""),
uz=("Foyda qanday hisoblanadi", """
<p>Foyda ikki qismdan iborat:</p>
<ul>
<li><b>Mahsulotlar foydasi</b> — ombordagi har bir mahsulot bo'yicha: sotuv narxi − xarid narxi. Xarid narxi sotuv paytida eslab qolinadi, shuning uchun keyin uni o'zgartirish o'tgan foydaga ta'sir qilmaydi.</li>
<li><b>Ish va xizmatlar</b> — «Boshqa»ga mahsulotsiz yozilgan hamma narsa (yuvish, sham almashtirish va h.k.) foydaga to'liq kiradi.</li>
</ul>
<p><b>Sof foyda</b> = mahsulotlar foydasi + ish va xizmatlar − xarajatlar.</p>
<div class="hp-warn">«…sotuvlar foydaga kirmadi» degan sariq yozuv tushumning bir qismini hisoblab bo'lmasligini bildiradi: mahsulotning xarid narxi yo'q yoki moy va filtr ombordan tanlanmay, qo'lda yozilgan. Omborda xarid narxini yozing[[M]] (filialniki — «Filial omborlari»da)[[/]], shunda bu sotuvlar foydaga o'zi qo'shiladi.</div>
""")),

# ======================================================================
# СОТРУДНИКИ И НАСТРОЙКИ
# ======================================================================
dict(id="staff", sec="team", roles=NOT_EMP, go="staff",
kw="сотрудник мастер добавить логин пароль выключить xodim usta qo'shish",
ru=("Сотрудники: добавить мастера", """
<ol class="hp-steps">
<li>Откройте «Сотрудники».</li>
<li>Впишите имя и логин (латинские буквы, цифры и _). Пароль можно не вписывать — он придумается сам.</li>
<li>Нажмите «+ Добавить сотрудника».</li>
<li>Нажмите «Скопировать» и отправьте сотруднику адрес, логин и пароль. <b>Пароль показывается только один раз.</b></li>
</ol>
<p>Сотрудник может вносить замены, смотреть базу и долги, делать рассылку. Прибыль, закупочные цены, расходы, склад, статистику и экспорт он не видит.</p>
<ul>
<li><b>Новый пароль</b> — если сотрудник забыл пароль. Старый перестанет работать.</li>
<li><b>Выключить</b> — сотрудник сразу теряет доступ, потом можно включить снова.</li>
<li><b>Удалить</b> — навсегда. Записи, которые он вносил, останутся.</li>
</ul>
"""),
uz=("Xodimlar: usta qo'shish", """
<ol class="hp-steps">
<li>«Xodimlar»ni oching.</li>
<li>Ism va loginni yozing (lotin harflari, raqamlar va _). Parolni yozmasangiz ham bo'ladi — u o'zi o'ylab topiladi.</li>
<li>«+ Xodim qo'shish»ni bosing.</li>
<li>«Nusxalash»ni bosing va xodimga manzil, login va parolni yuboring. <b>Parol faqat bir marta ko'rsatiladi.</b></li>
</ol>
<p>Xodim almashtirishlarni kirita oladi, baza va qarzlarni ko'radi, xabarnoma yuboradi. Foyda, xarid narxlari, xarajatlar, ombor, statistika va eksportni ko'rmaydi.</p>
<ul>
<li><b>Yangi parol</b> — xodim parolni unutsa. Eskisi ishlamay qoladi.</li>
<li><b>O'chirish</b> — xodim darhol kira olmaydi, keyin yana yoqish mumkin.</li>
<li><b>O'chirib tashlash</b> — butunlay. U kiritgan yozuvlar qoladi.</li>
</ul>
""")),

dict(id="export", sec="team", roles=NOT_EMP, go="export",
kw="экспорт excel резервная копия скачать базу eksport zaxira nusxa",
ru=("Экспорт: Excel и резервная копия", """
<ul>
<li><b>«📊 Скачать в Excel»</b> — таблица со всей историей замен. Удобно смотреть, печатать, отправлять бухгалтеру.</li>
<li><b>«⬇️ Скачать резервную копию»</b> — вся база вашей точки одним файлом: клиенты, машины, история. На всякий случай или для переноса.</li>
</ul>
<p>Кроме того, вся платформа каждую ночь сама сохраняет резервную копию у администратора.</p>
"""),
uz=("Eksport: Excel va zaxira nusxa", """
<ul>
<li><b>«📊 Excelga yuklab olish»</b> — barcha almashtirishlar tarixi bilan jadval. Ko'rish, chop etish, buxgalterga yuborish uchun qulay.</li>
<li><b>«⬇️ Zaxira nusxani yuklab olish»</b> — nuqtangizning butun bazasi bitta faylda: mijozlar, mashinalar, tarix. Har ehtimolga qarshi yoki ko'chirish uchun.</li>
</ul>
<p>Bundan tashqari, butun platforma har kecha administratorda zaxira nusxani o'zi saqlaydi.</p>
""")),

dict(id="subscription", sec="team", roles=OWNERS,
kw="подписка оплата продлить чек пробный период блокировка obuna to'lov uzaytirish chek",
ru=("Подписка: как продлить", """
<ol class="hp-steps">
<li>Откройте «Подписка» в меню.</li>
<li>Выберите срок: 1, 3, 6 или 12 месяцев. Чем дольше срок, тем больше скидка. Сумма — за всю сеть сразу.</li>
<li>Переведите сумму на карту, указанную на странице (номер можно скопировать).</li>
<li>Сделайте скриншот перевода, нажмите «Выбрать скриншот чека» и «Отправить чек».</li>
<li>После проверки подписка продлится сама, а вам придёт уведомление в Telegram.</li>
</ol>
<ul>
<li>Оплата заранее добавляется к текущей дате — оплаченные дни не пропадают.</li>
<li>За несколько дней до конца сверху появится напоминание, и бот напишет в Telegram.</li>
<li>Если срок закончился, вход приостанавливается. <b>Данные не удаляются</b> — после оплаты всё заработает сразу.</li>
<li>Новая точка получает 14 дней бесплатно.</li>
[[M]]<li>Новый филиал начинает работать после оплаты — его можно оплатить отдельно или вместе с продлением всей сети.</li>[[/]]
</ul>
"""),
uz=("Obuna: qanday uzaytirish", """
<ol class="hp-steps">
<li>Menyuda «Obuna»ni oching.</li>
<li>Muddatni tanlang: 1, 3, 6 yoki 12 oy. Muddat qancha uzun bo'lsa, chegirma shuncha katta. Summa — butun tarmoq uchun.</li>
<li>Summani sahifada ko'rsatilgan kartaga o'tkazing (raqamni nusxalash mumkin).</li>
<li>O'tkazma skrinshotini oling, «Chek skrinshotini tanlash» va «Chekni yuborish»ni bosing.</li>
<li>Tekshiruvdan keyin obuna o'zi uzayadi va sizga Telegramda xabar keladi.</li>
</ol>
<ul>
<li>Oldindan to'lov joriy sanaga qo'shiladi — to'langan kunlar yo'qolmaydi.</li>
<li>Tugashiga bir necha kun qolganda tepada eslatma chiqadi va bot Telegramda yozadi.</li>
<li>Muddat tugasa, kirish to'xtatiladi. <b>Ma'lumotlar o'chirilmaydi</b> — to'lovdan keyin hammasi darhol ishlaydi.</li>
<li>Yangi nuqta 14 kun bepul oladi.</li>
[[M]]<li>Yangi filial to'lovdan keyin ishlay boshlaydi — uni alohida yoki butun tarmoqni uzaytirish bilan birga to'lash mumkin.</li>[[/]]
</ul>
""")),

dict(id="course", sec="team", roles=ALL,
kw="обучение курс модули учиться ta'lim kurs modul",
ru=("Обучение: курс для пункта замены масла", """
<p>Во вкладке «Обучение» — курс из модулей: как зарабатывает пункт, масла и фильтры, технология замены, работа с клиентом, допродажи[[MSB]], база клиентов, склад, деньги точки, команда и реклама[[/]].</p>
<p>[[E]]Сотруднику доступны первые 7 модулей. [[/]]Пройденные модули отмечаются галочкой, прогресс сохраняется. Сейчас курс на узбекском языке.</p>
"""),
uz=("Ta'lim: moy almashtirish shoxobchasi uchun kurs", """
<p>«Ta'lim» bo'limida modullardan iborat kurs bor: shoxobcha qanday daromad qiladi, moy va filtrlar, almashtirish texnologiyasi, mijoz bilan ishlash, qo'shimcha sotish[[MSB]], mijozlar bazasi, ombor, shoxobcha pullari, jamoa va reklama[[/]].</p>
<p>[[E]]Xodimga dastlabki 7 ta modul ochiq. [[/]]O'tilgan modullar belgilanadi, natija saqlanadi.</p>
""")),

# ======================================================================
# ЧАСТЫЕ ВОПРОСЫ
# ======================================================================
dict(id="faq_noprofit", sec="faq", roles="BE",
kw="не вижу прибыль закупку статистику склад foyda ko'rinmaydi",
ru=("Почему я не вижу прибыль и цены закупки?", """
<p>Так задумано. Прибыль, цены закупки и наценку видит только владелец [[B]]главной [[/]]точки.[[E]] Сотруднику также не видны статистика, склад, расходы и экспорт.[[/]] Ничего не сломалось.</p>
"""),
uz=("Nega foyda va xarid narxlarini ko'rmayapman?", """
<p>Bu ataylab shunday qilingan. Foyda, xarid narxlari va ustamani faqat [[B]]bosh [[/]]nuqta egasi ko'radi.[[E]] Xodimga statistika, ombor, xarajatlar va eksport ham ko'rinmaydi.[[/]] Hech narsa buzilmagan.</p>
""")),

dict(id="faq_wrong_buy", sec="faq", roles=OWNERS, need="warehouse",
kw="ошибся цена закупки коробка канистра огромная прибыль минус xarid narxi xato",
ru=("Прибыль странная: огромная или в минусе", """
<p>Чаще всего цена закупки введена не за ту единицу — например, за коробку фильтров или канистру, а продаётся поштучно или литрами.</p>
<ol class="hp-steps">
<li>Откройте «Склад» и найдите товар. Подсказка «продажа ниже закупки» показывает такие товары.</li>
<li>Нажмите ✏️ и впишите цену закупки за одну единицу (1 литр или 1 штуку).</li>
</ol>
[[M]]<p>Товары филиала исправляются в «Склады филиалов».</p>[[/]]
<p>Если ошибка в цене продажи в конкретной замене — исправьте эту запись в «Базе» (✏️ Изменить).</p>
"""),
uz=("Foyda g'alati: juda katta yoki minusda", """
<p>Ko'pincha xarid narxi noto'g'ri birlik uchun kiritilgan bo'ladi — masalan, bir quti filtr yoki kanistr uchun, sotuv esa dona yoki litrda.</p>
<ol class="hp-steps">
<li>«Ombor»ni oching va mahsulotni toping. «Sotuv xariddan past» belgisi shunday mahsulotlarni ko'rsatadi.</li>
<li>✏️ ni bosing va bitta birlik (1 litr yoki 1 dona) uchun xarid narxini yozing.</li>
</ol>
[[M]]<p>Filial mahsulotlari «Filial omborlari»da tuzatiladi.</p>[[/]]
<p>Xato aniq bir almashtirishdagi sotuv narxida bo'lsa — o'sha yozuvni «Baza»da tuzating (✏️ O'zgartirish).</p>
""")),

dict(id="faq_reminders", sec="faq", roles=ALL,
kw="клиенту не приходят напоминания бот не пришло eslatma kelmayapti",
ru=("Клиенту не приходят напоминания", """
<ul>
<li><b>Клиент не привязан к боту.</b> В «Базе» у него нет отметки «привязан». Отправьте ему ссылку (статья «Привязать клиента к боту»).</li>
<li><b>Клиент остановил или заблокировал бота.</b> Попросите открыть ссылку ещё раз и нажать «Start».</li>
<li><b>Срок ещё не подошёл.</b> Напоминание приходит по «Через сколько напомнить?» из последней замены.</li>
</ul>
"""),
uz=("Mijozga eslatmalar kelmayapti", """
<ul>
<li><b>Mijoz botga bog'lanmagan.</b> «Baza»da unda «bog'langan» belgisi yo'q. Unga havola yuboring («Mijozni botga bog'lash» maqolasi).</li>
<li><b>Mijoz botni to'xtatgan yoki bloklagan.</b> Havolani qayta ochib, «Start»ni bosishini so'rang.</li>
<li><b>Muddat hali kelmagan.</b> Eslatma oxirgi almashtirishdagi «Necha vaqtdan keyin eslatish kerak?» bo'yicha keladi.</li>
</ul>
""")),

dict(id="faq_network", sec="faq", roles=ALL,
kw="нет интернета не сохранилось дубль ошибка сети связь internet yo'q saqlanmadi",
ru=("Нет интернета или «неизвестно, сохранилось ли»", """
<p>Если связь пропала в момент сохранения, OilBook напишет: «Связь прервалась — неизвестно, сохранилось ли».</p>
<p>Просто нажмите ту же кнопку ещё раз, ничего не меняя. <b>Дубля не будет</b> — OilBook узнает повторное нажатие.</p>
<p>Сверху появляется полоска «Нет интернета», пока связи нет, и «Связь восстановлена», когда она вернулась.</p>
"""),
uz=("Internet yo'q yoki «saqlandimi, noma'lum»", """
<p>Saqlash paytida aloqa uzilsa, OilBook «Aloqa uzildi — saqlangani noma'lum» deb yozadi.</p>
<p>Hech narsani o'zgartirmasdan, o'sha tugmani yana bir marta bosing. <b>Ikki marta yozilmaydi</b> — OilBook takroriy bosishni taniydi.</p>
<p>Aloqa yo'q paytda tepada «Internet yo'q» chizig'i chiqadi, aloqa tiklanganda — «Aloqa tiklandi».</p>
""")),

dict(id="faq_stale", sec="faq", roles=ALL,
kw="старые данные не обновляется зависло белый экран eski ma'lumot yangilanmayapti",
ru=("Показываются старые данные или пустой экран", """
<ol class="hp-steps">
<li>Переключитесь на другой раздел и обратно — данные загрузятся заново.</li>
<li>Закройте приложение полностью (смахните из списка открытых) и откройте снова.</li>
<li>Не помогло — удалите иконку OilBook и установите приложение заново. Данные хранятся на сервере, ничего не пропадёт.</li>
</ol>
"""),
uz=("Eski ma'lumotlar yoki bo'sh ekran ko'rinyapti", """
<ol class="hp-steps">
<li>Boshqa bo'limga o'tib, qayting — ma'lumotlar qayta yuklanadi.</li>
<li>Ilovani butunlay yoping (ochiq ilovalar ro'yxatidan suring) va qayta oching.</li>
<li>Yordam bermasa — OilBook belgisini o'chirib, ilovani qayta o'rnating. Ma'lumotlar serverda saqlanadi, hech narsa yo'qolmaydi.</li>
</ol>
""")),

dict(id="faq_blocked", sec="faq", roles="BE",
kw="доступ приостановлен подписка закончилась не могу войти kirish to'xtatildi obuna tugadi",
ru=("«Доступ приостановлен» или «подписка заканчивается»", """
<p>Подписку оплачивает владелец главной точки. Если видите предупреждение о подписке — сообщите ему. Данные не удаляются: после оплаты всё сразу заработает.</p>
"""),
uz=("«Kirish to'xtatildi» yoki «obuna tugayapti»", """
<p>Obunani bosh nuqta egasi to'laydi. Obuna haqida ogohlantirish ko'rsangiz — unga xabar bering. Ma'lumotlar o'chirilmaydi: to'lovdan keyin hammasi darhol ishlaydi.</p>
""")),

dict(id="faq_branch", sec="faq", roles="M",
kw="добавить филиал удалить филиал открыть точку filial qo'shish o'chirish",
ru=("Как открыть или закрыть филиал", """
<p>Филиалы создаёт администратор платформы — напишите ему название, адрес и телефон нового филиала. После оплаты филиал заработает, и вы скопируете в него каталог товаров («Сеть и перемещения»).</p>
<p>Закрытый филиал лучше <b>выключить</b>, а не удалять: история и статистика сохранятся.</p>
"""),
uz=("Filialni qanday ochish yoki yopish", """
<p>Filiallarni platforma administratori yaratadi — unga yangi filialning nomi, manzili va telefonini yozing. To'lovdan keyin filial ishlay boshlaydi va siz unga mahsulotlar katalogini nusxalaysiz («Tarmoq va ko'chirish»).</p>
<p>Yopilgan filialni o'chirib tashlamasdan, <b>o'chirib qo'ygan</b> ma'qul: tarix va statistika saqlanadi.</p>
""")),

]


# ======================================================================
# СПРАВКА ДЛЯ АДМИНИСТРАТОРА ПЛАТФОРМЫ (только RU — админка на русском)
# ======================================================================
ADMIN_SECTIONS = [
    ("a_start", "fa-compass", "Общее"),
    ("a_shops", "fa-store", "Точки, филиалы, сотрудники"),
    ("a_money", "fa-sack-dollar", "Подписка и доходы"),
    ("a_data", "fa-chart-pie", "Карта и аналитика"),
    ("a_safe", "fa-shield-halved", "Копии и восстановление"),
    ("a_tech", "fa-server", "Техническое"),
]

ADMIN_ARTICLES = [
dict(id="a_overview", sec="a_start", kw="админка вкладки роли",
ru=("Как устроена админ-панель", """
<p>Админ-панель открывается после входа под логином администратора. Вверху четыре вкладки:</p>
<ul>
<li><b>Точки</b> — заявки на регистрацию, добавление точки, подписка, резервная копия, восстановление и список всех точек.</li>
<li><b>Доходы</b> — оплаты подписки по месяцам, кто скоро продлевает, кто не продлил.</li>
<li><b>Карта</b> — все точки на карте и рейтинг по выручке или заменам.</li>
<li><b>Аналитика</b> — что и по каким ценам продают точки, доля MITAL.</li>
</ul>
<p><b>Кто есть кто:</b></p>
<ul>
<li><b>Самостоятельная точка</b> — создаётся через «Добавить новую точку» или регистрируется сама. Видит свою прибыль и закупку.</li>
<li><b>Главная точка</b> — самостоятельная точка, у которой есть филиалы. Видит прибыль всей сети.</li>
<li><b>Филиал</b> — создаётся только в карточке главной: плитка «Филиалы» → «+ Добавить филиал». Не видит прибыль и закупочные цены.</li>
<li><b>Сотрудник</b> — логин внутри точки. Только замены, база, долги, рассылка.</li>
</ul>
<div class="hp-warn">Точка, созданная через «Добавить новую точку» с той же группой, — это <b>не филиал</b>, а отдельная самостоятельная точка. Группа только ставит точки рядом в списке.</div>
""")),

dict(id="a_reg", sec="a_shops", kw="заявка регистрация одобрить отклонить register",
ru=("Заявки на регистрацию", """
<p>Владельцы точек могут зарегистрироваться сами по ссылке, которая указана внизу раздела «Заявки на регистрацию». Они заполняют форму и подтверждают телефон и локацию через Telegram-бота.</p>
<ol class="hp-steps">
<li>Откройте «Заявки на регистрацию».</li>
<li>Сверьте телефон из формы с телефоном, подтверждённым в Telegram, проверьте название и адрес.</li>
<li>Нажмите «✅ Одобрить (14 дней)» — точка получит пробный период и логин в Telegram. Или «❌ Отклонить».</li>
</ol>
"""),),

dict(id="a_add", sec="a_shops", kw="добавить точку создать логин пароль локация",
ru=("Добавить точку вручную", """
<ol class="hp-steps">
<li>«Добавить новую точку» → название, группа (необязательно), логин, пароль (пусто — сгенерируется), телефон, Telegram ID, адрес, локация.</li>
<li>Локация: в Google Картах нажмите и удерживайте на месте точки — внизу появятся два числа через запятую, вставьте их целиком.</li>
<li>Нажмите «Создать точку». <b>Пароль показывается один раз</b> — сразу сохраните и передайте владельцу.</li>
<li>Плитка «Ссылка» в карточке точки копирует ссылку для привязки Telegram владельца. Отправьте её владельцу, он нажмёт «Start».</li>
</ol>
"""),),

dict(id="a_card", sec="a_shops", kw="карточка точки выключить sms склад пароль ссылка тест",
ru=("Карточка точки", """
<ul>
<li><b>● активна / ○ выключена</b> — выключенная точка не может войти, данные сохраняются.</li>
<li><b>SMS</b> и <b>Склад</b> — переключатели функций для точки.</li>
<li><b>🏷 группа</b> — ставит точки одного владельца рядом в списке.</li>
<li><b>Филиалы</b> — список филиалов и добавление нового.</li>
<li><b>Сотрудники</b> — логины сотрудников этой точки.</li>
<li><b>Изменить</b> — название и логин.</li>
<li><b>Пароль</b> — сделать новый пароль (старый перестанет работать).</li>
<li><b>Ссылка</b> — ссылка для привязки Telegram владельца.</li>
<li><b>Тест TG</b> — отправить пробное сообщение в Telegram точки.</li>
<li><b>Telegram ID вручную</b> — если владелец не может пройти по ссылке.</li>
</ul>
<p>Фильтры над списком: Все, Активные, Выключенные, Без Telegram, Должники. Поиск — по названию, логину или телефону.</p>
"""),),

dict(id="a_branch", sec="a_shops", kw="филиал добавить изменить удалить ждёт оплаты",
ru=("Филиалы: добавить, изменить, удалить", """
<p><b>Добавить:</b> карточка главной точки → «Филиалы» → «+ Добавить филиал» → название, логин, пароль, телефон, адрес, локация.</p>
<ul>
<li>Новый филиал у платной точки получает отметку «⏳ ждёт оплаты» и не работает, пока его не оплатят. Если оплата пришла не через чек — нажмите «✅ отметить оплату».</li>
<li>У каждого филиала свои кнопки: активен/выключен, SMS, Склад, ✏️ изменить (название, логин, телефон, адрес, часы, локация, Telegram), «сбросить» пароль.</li>
<li><b>🗑 удалить:</b> OilBook покажет, что удалится, попросит ввести название филиала, сам отправит копию базы в Telegram и удалит всё одной операцией. Без копии удаление не выполняется.</li>
</ul>
<div class="hp-tip">Закрытый филиал лучше выключить, а не удалять — история и статистика сети сохранятся.</div>
"""),),

dict(id="a_emp", sec="a_shops", kw="сотрудник логин сбросить пароль",
ru=("Сотрудники точки", """
<p>Владелец добавляет сотрудников сам, во вкладке «Сотрудники» своей панели. Из админки это тоже можно сделать: плитка «Сотрудники» → логин → «+ добавить». Пароль показывается один раз.</p>
<p>Там же: выключить/включить, сбросить пароль, удалить. Записи, которые сотрудник вносил, остаются.</p>
"""),),

dict(id="a_sub", sec="a_money", kw="подписка чек подтвердить реквизиты цены скидки продлить бессрочная",
ru=("Подписка: чеки, цены, продление", """
<p><b>Чеки.</b> Когда точка оплачивает, чек приходит вам в Telegram и появляется в «Подписка: чеки и реквизиты» и в карточке точки. Откройте чек, сверьте сумму и нажмите «✅ Подтвердить» или «❌ Отклонить». Точка получит уведомление.</p>
<p><b>Настройки:</b> номер карты и имя на карте (их видят точки на странице оплаты), контакт поддержки, цена в месяц за главную точку и за каждый филиал, скидки за 1/3/6/12 месяцев.</p>
<p><b>В карточке точки:</b></p>
<ul>
<li><b>+1 мес / +3 / +6 / +12</b> — продлить вручную (например, оплатили наличными);</li>
<li><b>📅 Дата</b> — поставить точную дату «оплачено до»;</li>
<li><b>💲 Цена</b> — особая цена для этой точки;</li>
<li><b>∞ Разовая покупка</b> — бессрочная лицензия, платить каждый месяц не нужно.</li>
</ul>
<div class="hp-warn">Точки «без даты» работают как раньше. Как только поставите дату, подписка начнёт действовать. Блокировка — на следующий день после даты, без льготных дней. Данные при блокировке не удаляются.</div>
"""),),

dict(id="a_income", sec="a_money", kw="доходы оплаты по месяцам не продлили",
ru=("Вкладка «Доходы»", """
<ul>
<li>оплаты по месяцам и подписки в пересчёте на месяц;</li>
<li>какой срок выбирают точки;</li>
<li>кто продлевает в ближайшие 30 дней — сколько ожидается денег;</li>
<li>кто не продлил — сколько вы теряете в месяц;</li>
<li>последние оплаты.</li>
</ul>
<p>Точки с истекающей подпиской стоит обзвонить заранее.</p>
"""),),

dict(id="a_map", sec="a_data", kw="карта рейтинг молчат локация",
ru=("Карта", """
<ul>
<li>Все точки на карте. Размер круга — выручка за период, толстая обводка — главная точка.</li>
<li>Рейтинг за 7 дней, 30 дней или год — по выручке или по заменам.</li>
<li>«Молчат больше 14 дней» — точки, которые перестали вносить замены. Им стоит позвонить.</li>
<li>«Нет на карте» — точки без локации. Нажмите «Указать» и кликните на карте или «Я сейчас здесь», если вы на точке.</li>
</ul>
"""),),

dict(id="a_analytics", sec="a_data", kw="аналитика бренды цены доля mital сопоставление названий проблемные цены",
ru=("Аналитика продаж", """
<ul>
<li><b>Вся сеть / одна точка:</b> бренды, топ товаров, средняя наценка, доля MITAL по сумме.</li>
<li><b>Цены по точкам</b> — нажмите на товар в топе, и увидите, кто по какой цене продаёт.</li>
<li><b>Возможности для продаж</b> — что точки берут у других поставщиков: кому предложить продукцию MITAL.</li>
<li><b>Сопоставление названий</b> — точки пишут бренды по-разному. Укажите правильный бренд («✏️ Указать бренд») или отметьте «Не бренд», чтобы аналитика была точной.</li>
<li><b>Проблемные цены</b> — подозрительно низкие или высокие цены, похожие на ошибку ввода. Их исправляют в «Базе» самой точки.</li>
</ul>
"""),),

dict(id="a_backup", sec="a_safe", kw="резервная копия backup каждую ночь myid",
ru=("Резервная копия", """
<p>Копия всей базы приходит вам в Telegram каждую ночь.</p>
<ul>
<li>Чтобы получить копию прямо сейчас — «Резервная копия» → «Отправить сейчас».</li>
<li>Копия не приходит? Напишите боту <b>/myid</b> и сверьте число с переменной <b>ADMIN_TELEGRAM_ID</b> в Render → Environment.</li>
</ul>
<div class="hp-tip">Перед любыми крупными изменениями (обновление кода, удаление филиала, переезд) сделайте «Отправить сейчас».</div>
"""),),

dict(id="a_restore", sec="a_safe", kw="восстановить базу заменить копия",
ru=("Восстановить базу из копии", """
<div class="hp-warn">Это заменяет <b>все</b> данные платформы содержимым файла. Всё, что добавили после даты копии, пропадёт. Делайте только при настоящей необходимости.</div>
<ol class="hp-steps">
<li>Откройте «Восстановить базу из копии» (красная рамка).</li>
<li>Выберите файл копии (.db или .gz) из Telegram.</li>
<li>Впишите слово <b>ЗАМЕНИТЬ</b> и нажмите «Восстановить из этого файла».</li>
</ol>
<p>Перед заменой OilBook сам отправит вам копию текущего состояния — если восстановление окажется ошибкой, можно вернуть всё обратно.</p>
"""),),

dict(id="a_deploy", sec="a_tech", kw="github render обновить код залить файлы переменные",
ru=("Обновление кода и хостинг", """
<ul>
<li><b>Код</b> — на GitHub (Zamenamasla1). Новые файлы заливаются через «Add file → Upload files»: .py — в корень, manifest.json и sw.js — в папку <b>static</b>.</li>
<li><b>Хостинг</b> — Render. После каждой загрузки на GitHub сайт пересобирается сам за 2–3 минуты.</li>
<li><b>База</b> — на постоянном диске Render (<code>/var/data</code>).</li>
<li><b>Переменные</b> — Render → Environment. <b>SECRET_KEY менять нельзя</b>: им зашифрованы пароли SMS.</li>
<li>Если пароль администратора потерян — его сбрасывают через Render Shell.</li>
</ul>
"""),),
]


# ======================================================================
# Сборка справки под роль
# ======================================================================
_ROLE_BLOCK = re.compile(r"\[\[([MSBE]+)\]\](.*?)\[\[/\]\]", re.S)


def _for_role(html: str, role: str) -> str:
    return _ROLE_BLOCK.sub(lambda m: m.group(2) if role in m.group(1) else "", html).strip()


def detect_role(is_employee: bool, is_branch: bool, has_branches: bool) -> str:
    if is_employee:
        return "E"
    if is_branch:
        return "B"
    return "M" if has_branches else "S"


def build(lang: str, role: str, warehouse: bool = False, sms: bool = False):
    """Разделы справки для роли: [{key, icon, title, articles: [{id, title, body, go, kw}]}]."""
    lang = "uz" if lang == "uz" else "ru"
    flags = {"warehouse": warehouse, "sms": sms}
    out = []
    for key, icon, ru_t, uz_t in SECTIONS:
        arts = []
        for a in ARTICLES:
            if a["sec"] != key or role not in a["roles"]:
                continue
            if a.get("need") and not flags.get(a["need"]):
                continue
            title, body = a.get(lang) or a["ru"]
            arts.append({
                "id": a["id"], "title": _for_role(title, role), "body": _for_role(body, role),
                "go": a.get("go") or "", "kw": a.get("kw", ""),
            })
        if arts:
            out.append({"key": key, "icon": icon, "title": uz_t if lang == "uz" else ru_t, "articles": arts})
    return out


def build_admin():
    out = []
    for key, icon, title in ADMIN_SECTIONS:
        arts = [{"id": a["id"], "title": a["ru"][0], "body": a["ru"][1].strip(), "go": "", "kw": a.get("kw", "")}
                for a in ADMIN_ARTICLES if a["sec"] == key]
        if arts:
            out.append({"key": key, "icon": icon, "title": title, "articles": arts})
    return out


def role_name(lang: str, role: str) -> str:
    return ROLE_NAMES["uz" if lang == "uz" else "ru"].get(role, "")
