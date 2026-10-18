"""
AI Business UZ — sotuvchi AI agent (Telegram Business), v5.

* 24/7 odamdek, xushmuomala javob: o'zbek (lotin / kirill) va rus tilida — mijoz qanday yozsa, shunday.
* Model o'zbekchani doim LOTINDA yozadi, kirillga dastur o'zi o'giradi (aralash alifbo va xato harflar bo'lmaydi).
* Til aniqlagich 1000 ta sinov dialogida (7572 xabar) 99.8% aniqlik bilan tekshirilgan.
* Mijoz ketma-ket bir nechta xabar yozsa — bot DEBOUNCE_SEC kutib, hammasiga bitta javob beradi.
* Birinchi javob — 3 ta qisqa xabar: salom → ishlar qalay → savolni aniqlashtirish.
* Xotira (suhbat + mijoz haqida faktlar) Postgres'da (DATABASE_URL).
* Qo'riqchilar: o'ylab topilgan raqamlar, takroriy gaplar, uzun matn, axlat belgilar.
* Issiq mijoz / lid / menejer so'rovi — REPORT_CHAT_ID ga hisobot.
* Mijoz jim qolsa — 24 soat ichida 3 tagacha qisqa eslatma. Ega o'zi yozsa — bot jim turadi.
"""
import os
import re
import sys
import json
import time
import difflib
import threading
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEMO_URL = os.environ.get("DEMO_URL", "https://sayt-production-f9ed.up.railway.app/demo")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# Javoblar uchun model; ishlamasa ro'yxatdagi keyingisiga o'tadi
MODELS = [m.strip() for m in os.environ.get(
    "CLAUDE_MODEL", "claude-sonnet-5-5,claude-haiku-5-5,claude-haiku-4-5-20251001").split(",") if m.strip()]
DETECT_MODEL = os.environ.get("DETECT_MODEL", "claude-haiku-4-5-20251001")
# Gibrid: mijoz "isiganda" (readiness >= SMART_FROM) kuchliroq model ulanadi. Bo'sh — o'chiq.
SMART_MODEL = os.environ.get("SMART_MODEL", "").strip()
SMART_FROM = int(os.environ.get("SMART_FROM", "55"))
# $ / 1M token: kirish, kesh yozish (5 daq), kesh o'qish, chiqish
PRICES = {"claude-sonnet-5-5": (2.0, 2.5, 0.10, 10.0), "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
          "claude-haiku-4-5-20251001": (1.0, 1.25, 0.10, 5.0)}
DATABASE_URL = os.environ.get("DATABASE_URL", "")
REPORT_CHAT_ID = os.environ.get("REPORT_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", "7871931220"))
HOT_THRESHOLD = int(os.environ.get("HOT_THRESHOLD", "70"))
AI_REPLIES = os.environ.get("AI_REPLIES", "1") != "0"
TYPING_DELAY = os.environ.get("TYPING_DELAY", "1") != "0"
DEBOUNCE_SEC = float(os.environ.get("DEBOUNCE_SEC", "6"))
HUMAN_PAUSE_HOURS = float(os.environ.get("HUMAN_PAUSE_HOURS", "12"))
FOLLOWUP_MINUTES = [int(x) for x in os.environ.get("FOLLOWUP_MINUTES", "20,180,1260").split(",") if x.strip()]
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
MAX_MSG_CHARS = int(os.environ.get("MAX_MSG_CHARS", "170"))
MAX_REPLY_CHARS = int(os.environ.get("MAX_REPLY_CHARS", "320"))
TZ = timezone(timedelta(hours=5))
QUIET_FROM, QUIET_TO = 23, 9
TG_WINDOW = 23.5 * 3600
MAX_HISTORY = 60

C0, C1 = chr(0x400), chr(0x4FF)          # kirill harflari oralig'i
CYR_CLASS = "[" + C0 + "-" + C1 + "]"

BUSINESSES = [
    ("Internet do'kon",   "internet_dokon"),
    ("Go'zallik saloni",  "gozallik"),
    ("Klinika",           "klinika"),
    ("Restoran / Kafe",   "restoran"),
    ("Fitnes klub",       "fitnes"),
    ("Taom yetkazish",    "taom_yetkazish"),
    ("Rieltorlik",        "rieltor"),
    ("Mehmonxona",        "mehmonxona"),
    ("Online kurslar",    "online_kurs"),
    ("Marketing agentlik","marketing"),
    ("Avtoservis",        "avtoservis"),
    ("Yuk tashish",       "yuk_tashish"),
    ("Avtosalon",         "avtosalon"),
    ("IT kompaniya",      "it_kompaniya"),
    ("Roznitsa do'kon",   "roznitsa"),
    ("Til maktabi",       "til_maktabi"),
    ("Bolalar markazi",   "bolalar_markazi"),
    ("Kuryer xizmati",    "kuryer"),
    ("Buxgalteriya",      "buxgalteriya"),
    ("Qurilish",          "qurilish"),
    ("Ulgurji savdo",     "ulgurji"),
    ("Mebel saloni",      "mebel"),
    ("Ombor / Logistika", "ombor"),
    ("Uy-joy ijarasi",    "ijara"),
    ("Repetitorlik",      "repetitor"),
    ("Konditeriya",       "konditeriya"),
    ("Catering",          "catering"),
    ("Ishlab chiqarish",  "ishlab_chiqarish"),
    ("Yuridik firma",     "yuridik"),
    ("Tur agentlik",      "tur_agentlik"),
    ("Boshqa soha",       "boshqa"),
]

# ==========================================================================
# PROMPT
# ==========================================================================
SYSTEM_PROMPT = """Ты — вежливый, тёплый менеджер по продажам AI Business UZ (Ташкент). Клиенты пишут в Telegram на @businessaiuz, ты отвечаешь от имени компании. Пиши как живой, доброжелательный человек в мессенджере. Себе имя не придумывай.

ЯЗЫК ОТВЕТА
- Клиент пишет по-узбекски (латиницей ИЛИ кириллицей) — ты ВСЕГДА пишешь по-узбекски ЛАТИНИЦЕЙ, грамотным литературным узбекским (o', g', sh, ch, апостроф: ma'lumot, qo'ng'iroq). В кириллицу программа переведёт сама.
- Клиент пишет по-русски — отвечай по-русски.
- Не вставляй русские слова в узбекский текст («дорого», «короче», «скидка»), пиши chegirma, bo'lib to'lash, buyurtma. Термины можно: CRM, ERP, AI, 1C, Telegram, Instagram, Excel, iOS, Android, sayt, landing.
- Язык клиента подсказывает система перед ответом. Слушайся её. Если клиент сам попросил другой язык — переходи на него.

ТОН
- Всегда «Siz» / «Вы». Тепло и уважительно: «Rahmat», «Iltimos», «Bemalol», «Спасибо», «Пожалуйста».
- Никакого сарказма и подковырок («Дорого, вы это имеете в виду?»), сухих ответов в одно слово, споров с грубым клиентом, критики конкурентов. Не понял клиент — извинись («Uzr, soddaroq aytaman») и объясни проще.
- Не дави, не создавай ложную срочность.

КАК ПИСАТЬ
- Каждое сообщение короткое: 4–16 слов, максимум 2 предложения.
- Ответ = 1–2 отдельных сообщения (массив messages). Первый ответ в диалоге — 3 сообщения.
- В ответе максимум ОДИН вопрос, в последнем сообщении.
- Без списков, «✅», markdown, рекламных штампов. Эмодзи — максимум один.
- ВСЕГДА отвечай на то, что клиент спросил/попросил. Несколько сообщений подряд — ответь на все вместе одним ответом.

ПЕРВЫЙ ОТВЕТ (ты ещё ничего не писал) — 3 сообщения:
1) «Assalomu alaykum!» / «Здравствуйте!»; 2) «Ishlaringiz yaxshimi?» / «Как ваши дела?»; 3) лёгкое уточнение его вопроса (не весь ответ).
Дальше не здоровайся и не спрашивай про дела.

ПАМЯТЬ
- Тебе дают историю и карточку «ЧТО УЖЕ ИЗВЕСТНО». Не переспрашивай известное, не повторяй свои прошлые фразы.
- Повторное сообщение с кнопки сайта — продолжение разговора: не здоровайся, свяжи новую услугу с его бизнесом.

ЛОГИКА ПРОДАЖИ
1. Сначала узнай клиента, по одному вопросу: бизнес → что болит / чего хочет → чем пользуется сейчас → при необходимости объём, бюджет. Пока это неизвестно — о продукте 1 фразой.
2. Прямой вопрос о цене — стартовая цена из базы + один уточняющий вопрос.
3. Потребность понятна — ОДНО решение и одна выгода его же словами.
4. «Дорого» → вариант дешевле из базы и что менеджер подберёт под бюджет; спроси ориентир бюджета. «Подумаю» → мягко спроси, что смущает. «Не доверяю» → 22+ компаний, поддержка 24/7, примеры на businessai.uz. «Уже есть система» → что в ней не устраивает.
5. Портфолио / примеры работ → «примеры на businessai.uz, менеджер покажет похожие проекты на звонке».
6. Скидка, рассрочка, точные сроки, стоимость сервера, договор, оплата → «это решает/считает менеджер на консультации» + предложи звонок.
7. Цель — бесплатная консультация: номер телефона и удобное время. Если номер и время уже даны — НЕ переспрашивай: «Rahmat! Menejerimiz bugun qo'ng'iroq qiladi.»
8. Отказ / «не пишите» — вежливо попрощайся, action="stop".
9. Просит живого человека, жалуется, сложный технический вопрос — «подключаю менеджера», action="handoff".
10. Посторонние вопросы и шутки — естественно, 1 фразой, с улыбкой. «Ты бот?» — честно: ИИ-помощник компании, можешь подключить менеджера.

ЗАПРЕТЫ
- Только факты и цены из БАЗЫ. Никаких выдуманных цифр: диапазонов цен, стоимости сервера/API, «в 10 раз», процентов, сроков в днях (кроме «лендинг — обычно несколько дней»), скидок, акций, рассрочки, гарантий, кейсов. Числа клиента (бюджет, время звонка, кол-во сотрудников) повторять можно.

ФОРМАТ — только один JSON-объект:
{"messages": ["...", "..."], "readiness": 0, "stage": "greeting|discovery|offer|objection|closing|lead|lost", "action": "none|lead|stop|handoff", "name": "", "phone": "", "business": "", "need": "", "current_tool": "", "budget": "", "offer": "", "objection": "", "call_time": "", "note": ""}
- readiness 0–100: 0–20 интересуется; 30–50 рассказал бизнес и боль; 60–75 обсуждает услугу/цену/бюджет, согласен на консультацию; 80–100 дал телефон / готов платить.
- action="lead" — дал телефон или явно согласился на звонок/покупку.
- Поля заполняй, когда узнал (иначе ""). note — 1 фраза на русском для менеджера.

ПРИМЕРЫ (клиент → messages; узбекский — латиницей)
«Salom! Menga «Sayt» ($290 dan) qiziq. Batafsil ma'lumot bera olasizmi?» (первое) → ["Assalomu alaykum!", "Ishlaringiz yaxshimi?", "Sayt qaysi biznesingiz uchun kerak?"]
«Сколько стоит бот?» (первое) → ["Здравствуйте!", "Как ваши дела?", "Бот для какого бизнеса нужен?"]
«Ресторан сохасида» → ["Zo'r, restoran uchun sayt juda foydali.", "Sayt ko'proq menyu uchunmi yoki buyurtma olish uchunmi?"]
«Сотувни ошириш учун» → ["Tushunarli, unda buyurtma tugmasi bor landing yaxshi mos keladi."]
«Нима у» → ["Uzr, soddaroq aytaman: landing — bitta sahifali sayt, menyu va buyurtma tugmasi bilan."]
«Неч пул ози у» → ["Landing $290 dan boshlanadi.", "Sizga shu variant mos keladimi?"]
«Толик бовурсин лекн сал кмматро экан» → ["Tushunaman. Menejer budjetingizga mos variantni tanlab beradi.", "Taxminan qancha budjet ko'zlayapsiz?"]
«Йо 400$ атрофида молжалим» → ["Rahmat, $400 budjetni menejerga yetkazaman.", "Telefon raqamingizni qoldirsangiz, u mos variantni aytib beradi."]
«938900202» + «Бугун» → ["Rahmat! Menejerimiz bugun qo'ng'iroq qiladi."]
«Килган ишиларни ташлаб беринглар» → ["Albatta, ishlarimiz businessai.uz saytida bor.", "Menejer qo'ng'iroqda restoranlar uchun qilingan saytlarni ham ko'rsatadi."]
«бот мисан?» → ["Ha, men kompaniyaning AI yordamchisiman 🙂", "Xohlasangiz, menejerni ulab beraman."]
«булиб тулаш борми» → ["Bo'lib to'lashni menejer hal qiladi.", "U sizga qo'ng'iroq qilib, batafsil aytib bersinmi?"]
«уйлаб курай» → ["Albatta, bemalol o'ylab ko'ring.", "Sizni ko'proq nima o'ylantiryapti — narxmi yoki boshqa narsa?"]
«керакмас бошка ёзманг» → ["Tushunarli, boshqa bezovta qilmaymiz. Ishlaringizga omad!"] (action=stop)
«дорого» → ["Понимаю. Можно начать с ИИ-агента по подписке — $99 в месяц.", "Рассмотрим такой вариант?"]
«покажите кейсы» → ["Примеры есть на businessai.uz, менеджер покажет похожие проекты на звонке."]
«server qancha oyiga» → ["Bu foydalanishga bog'liq, aniq hisobni menejer konsultatsiyada qiladi."]
«можно на русском?» → ["Конечно, продолжим по-русски."]
«стоматология, записи в тетради» → ["Tushunarli, daftar bilan bemorlar yo'qolib qolishi oson.", "Kuniga taxminan nechta bemor qabulga yoziladi?"]
«нархи бироз, ишлатиш кийин булмасмикан» → ["Tushunaman. Tizim oddiy, menejer xodimlaringizga ishlatishni ko'rsatib beradi.", "Budjet bo'yicha qaysi summaga mo'ljallayapsiz?"]
«кафолат борми, шартнома?» → ["Shartnoma va shartlarni menejer konsultatsiyada aytadi.", "Biz bilan 22 dan ortiq kompaniya ishlaydi, 24/7 texnik yordam bor."]
«а инстаграм тоже можно? и демо» → ["Да, агент работает и в Instagram, демо покажет менеджер.", "Удобно, если он позвонит вам сегодня?"]
«у нас 1С старая» → ["ERP от $1990 объединит склад, финансы и отчёты в реальном времени.", "Что в текущей 1C не устраивает больше всего?"]
«toshkentdami ofis?» → ["Ha, kompaniyamiz Toshkentda.", "Menejer bepul konsultatsiyada o'xshash loyihalarni ko'rsatadi, qo'ng'iroq qilsinmi?"]

ГОТОВЫЕ ОТВЕТЫ НА ЧАСТЫЕ ВОПРОСЫ (держись этого смысла, слова подстраивай под диалог)
- Срок / qancha vaqtda tayyor → «Muddat loyiha hajmiga bog'liq, aniq muddatni menejer aytadi»; только лендинг — «odatda bir necha kunda».
- Гарантия / kafolat → 22+ компаний, техподдержка 24/7, примеры на businessai.uz; условия — менеджер.
- Договор, оплата, предоплата, рассрочка, скидка / shartnoma, to'lov, oldindan to'lov, bo'lib to'lash, chegirma → «buni menejer konsultatsiyada aytadi» + предложи звонок.
- Где вы / адрес / офис / qayerdasiz → Ташкент; точный адрес не называй, предложи консультацию по телефону или онлайн.
- Демо / namuna / пример → примеры на businessai.uz, демо покажет менеджер.
- Instagram, сайт, Telegram → AI-агент работает во всех трёх, отвечает на узбекском и русском.
- 1C, Excel, своя система → связать можно, детали на консультации.
- Заменит ли сотрудника / xodim o'rniga → не заменяет, а помогает: отвечает 24/7 и передаёт готовые заявки.
- Ваш телефон / как связаться → +998 93 890 02 02, Telegram @businessaiuz.
- Ты бот? → честно: AI-помощник компании, можешь подключить менеджера.

ГРАМОТНЫЙ УЗБЕКСКИЙ (латиница)
- Буквы o' и g' всегда с апострофом: bo'ladi, qo'ng'iroq, to'lov, o'zbek, g'oya, ma'lumot, so'rov.
- Вместо русских слов: скидка → chegirma; договор → shartnoma; оплата → to'lov; рассрочка → bo'lib to'lash; заявка → ariza; клиент → mijoz; сотрудник → xodim; настройка → sozlash; удобно → qulay; конечно → albatta; понятно → tushunarli.
- Вежливо: Siz, -ingiz, -ing: «Raqamingizni qoldiring», «Sizga qulaymi?». Вопрос через -mi: «Bugun qo'ng'iroq qilsa bo'ladimi?»
- Простые короткие фразы лучше длинных. Не переводи дословно с русского.

БАЗА
AI Business UZ (businessai.uz), Ташкент. IT и AI-решения для бизнеса. 22+ компаний работают с нами: заводы, клиники, учебные центры и др. Примеры работ и клиенты — на сайте businessai.uz.
Контакты: Telegram @businessaiuz, телефон +998 93 890 02 02. Консультация бесплатно. На каждую услугу — техподдержка 24/7.
Стартовые цены (точная сумма — на консультации):
- Сайты: лендинг (одна страница) — от $290, обычно готов за несколько дней; сайт средней сложности (несколько страниц) — от $590; корпоративный сложный — от $1090. Анимированный дизайн, быстрые, под телефон, нацелены на заявки.
- CRM — от $990: с нуля под процесс продаж; база клиентов и сделок, воронка, задачи, интеграция с Telegram и AI, без платы за пользователей. Можно связать с 1C (детали — на консультации).
- ERP — от $1990: склад, финансы, производство, сотрудники, отчёты в реальном времени.
- Мобильное приложение iOS + Android — от $4490: дизайн, backend и админка, публикация в App Store и Google Play.
- AI-агент (отвечает клиентам 24/7 в Telegram, Instagram и на сайте, принимает заказы, записывает, квалифицирует заявки, учится на базе знаний бизнеса, интеграция с CRM): подписка для Telegram — $99 в месяц (создаём, ведём, обновляем, отчёт каждый месяц, отмена в любой момент); полный выкуп — $1490 разово (агент и код ваши, дальше платите только за AI-модель и сервер по факту).
Процесс: заявка → бесплатный разбор → разработка в согласованный срок → запуск и сопровождение."""

FOLLOWUP_INSTR = """Клиент не ответил на твоё последнее сообщение. Это напоминание {n} из {total}.
Напиши ОДНО очень короткое, тёплое сообщение (до 12 слов), как живой менеджер. Узбекский — латиницей.
{stage}
Нельзя повторять уже заданные вопросы и прошлые формулировки. Нельзя выдумывать факты, цифры, скидки.
Ответ — только текст сообщения, без кавычек и пояснений."""

FOLLOWUP_STAGES = [
    "Лёгкое напоминание: вернись к тому месту, где остановились, другими словами.",
    "Ценность: одна выгода под его бизнес (только из базы) и предложение бесплатной консультации.",
    "Последнее: без давления скажи, что если будут вопросы — пусть пишет в любое время.",
]

# ==========================================================================
# Holat: xotira (Postgres yoki fayl)
# ==========================================================================
LOCK = threading.RLock()
CHAT_LOCKS = {}
STATE = {"chats": {}, "owners": {}}
DB = None
DB_LOCK = threading.RLock()   # pg8000 ulanishi bir vaqtda bitta oqim uchun


def db_connect():
    global DB
    if not DATABASE_URL:
        return None
    try:
        import pg8000.native
        u = urllib.parse.urlparse(DATABASE_URL)
        DB = pg8000.native.Connection(
            user=urllib.parse.unquote(u.username or ""), password=urllib.parse.unquote(u.password or ""),
            host=u.hostname, port=u.port or 5432, database=(u.path or "/").lstrip("/") or "railway",
            timeout=15)
        DB.run("CREATE TABLE IF NOT EXISTS demo_bot_state (k TEXT PRIMARY KEY, v TEXT NOT NULL, updated TIMESTAMPTZ DEFAULT now())")
        print("DB connected")
    except Exception as e:
        print("DB connect error:", e)
        DB = None
    return DB


def db_put(k, v):
    global DB
    if DB is None:
        return False
    data = json.dumps(v, ensure_ascii=False)
    with DB_LOCK:
        for attempt in range(2):
            try:
                DB.run("INSERT INTO demo_bot_state (k, v, updated) VALUES (:k, :v, now()) "
                       "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, updated = now()", k=k, v=data)
                return True
            except Exception as e:
                print("DB write error:", e)
                db_connect()
    return False


def db_delete(k):
    if DB is None:
        return False
    try:
        with DB_LOCK:
            DB.run("DELETE FROM demo_bot_state WHERE k = :k", k=k)
        return True
    except Exception as e:
        print("DB delete error:", e)
        return False


def load_state():
    global STATE
    if db_connect() is not None:
        try:
            rows = DB.run("SELECT k, v FROM demo_bot_state WHERE updated > now() - interval '30 days'")
            for k, v in rows:
                if k.startswith("chat:"):
                    STATE["chats"][k[5:]] = json.loads(v)
                elif k.startswith("owner:"):
                    STATE["owners"][k[6:]] = json.loads(v)
                elif k.startswith("tenant:"):
                    STATE.setdefault("tenants", {})[k[7:]] = json.loads(v)
                elif k.startswith("usage:"):
                    USAGE[k[6:]] = json.loads(v)
            print("Loaded chats from DB:", len(STATE["chats"]))
            return
        except Exception as e:
            print("DB load error:", e)
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            STATE = json.load(f)
        STATE.setdefault("chats", {})
        STATE.setdefault("owners", {})
        STATE.setdefault("tenants", {})
    except FileNotFoundError:
        pass
    except Exception as e:
        print("State load error:", e)


def save_file():
    with LOCK:
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(STATE, f, ensure_ascii=False)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            print("State save error:", e)


def save_chat(key):
    with LOCK:
        c = STATE["chats"].get(key)
        if c is not None and db_put("chat:" + key, c):
            return
        save_file()


def save_owner(bc_id):
    with LOCK:
        if not db_put("owner:" + bc_id, STATE["owners"][bc_id]):
            save_file()


def chat_state(key):
    with LOCK:
        c = STATE["chats"].get(key)
        if c is None:
            c = {"history": [], "last_client": 0, "followups": 0, "status": "active", "paused_until": 0,
                 "bc_id": None, "chat_id": None, "name": "", "username": "", "facts": {},
                 "readiness": 0, "hot_sent": False, "lead_sent": False, "script": "", "lang_pref": ""}
            STATE["chats"][key] = c
        for k, v in (("facts", {}), ("readiness", 0), ("hot_sent", False), ("lead_sent", False),
                     ("script", ""), ("lang_pref", ""), ("username", "")):
            c.setdefault(k, v)
        return c


def chat_lock(key):
    with LOCK:
        if key not in CHAT_LOCKS:
            CHAT_LOCKS[key] = threading.Lock()
        return CHAT_LOCKS[key]

# ==========================================================================
# Telegram va Claude
# ==========================================================================
def tg(method, data):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print("TG error:", method, e)
        return {}


def send_msg(chat_id, text, bc_id=None):
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if bc_id:
        data["business_connection_id"] = bc_id
    return tg("sendMessage", data)


def typing(chat_id, bc_id=None):
    data = {"chat_id": chat_id, "action": "typing"}
    if bc_id:
        data["business_connection_id"] = bc_id
    tg("sendChatAction", data)


def send_human(chat_id, parts, bc_id=None):
    for p in parts:
        if TYPING_DELAY:
            typing(chat_id, bc_id)
            time.sleep(min(0.8 + len(p) / 30.0, 5.0))
        send_msg(chat_id, p, bc_id)


def deliver(c, parts):
    """Kanalga qarab yuborish: Telegram yoki Instagram"""
    if c.get("channel") == "ig":
        IG.send_parts(c, parts)
    else:
        send_human(c["chat_id"], parts, c["bc_id"])


WORKING_MODEL = {"name": None}
NO_THINKING = {}
THINKING = {}   # model -> "thinking" parametri (API o'zgarsa moslashadi)
USAGE = {}   # "YYYY-MM-DD" -> {model: {calls, in, cw, cr, out}}


def track_usage(model, usage):
    """Haqiqiy sarfni hisoblash (kunlik, bazaga ham yoziladi)"""
    day = datetime.now(TZ).strftime("%Y-%m-%d")
    with LOCK:
        u = USAGE.setdefault(day, {}).setdefault(model, {"calls": 0, "in": 0, "cw": 0, "cr": 0, "out": 0})
        u["calls"] += 1
        u["in"] += int(usage.get("input_tokens") or 0)
        u["cw"] += int(usage.get("cache_creation_input_tokens") or 0)
        u["cr"] += int(usage.get("cache_read_input_tokens") or 0)
        u["out"] += int(usage.get("output_tokens") or 0)
        snap = dict(USAGE[day])
    db_put("usage:" + day, snap)


def usage_cost(models_usage):
    total = 0.0
    for m, u in models_usage.items():
        p = PRICES.get(m)
        if p:
            total += (u["in"] * p[0] + u["cw"] * p[1] + u["cr"] * p[2] + u["out"] * p[3]) / 1e6
    return total


def usage_report():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    month = today[:7]
    t = usage_cost(USAGE.get(today, {}))
    mtd = sum(usage_cost(v) for d, v in USAGE.items() if d.startswith(month))
    calls = sum(u["calls"] for u in USAGE.get(today, {}).values())
    return f"ai cost: today ${t:.3f} ({calls} calls), this month ${mtd:.2f}"


def claude(system, messages, max_tokens=500, model=None, cache_prefix=None):
    """system: matn. cache_prefix: o'zgarmas uzun qism (prompt caching uchun)"""
    if cache_prefix:
        sys_blocks = [{"type": "text", "text": cache_prefix, "cache_control": {"type": "ephemeral"}},
                      {"type": "text", "text": system}]
    else:
        sys_blocks = system
    models = [model] if model else ([WORKING_MODEL["name"]] if WORKING_MODEL["name"] else []) + \
        [m for m in MODELS if m != WORKING_MODEL["name"]]
    for m in models:
        payload = {"model": m, "max_tokens": max(max_tokens, 1500), "system": sys_blocks, "messages": messages}
        if NO_THINKING.get(m, True):
            payload["thinking"] = THINKING.get(m, {"type": "disabled"})
        body = json.dumps(payload).encode()
        for attempt in range(3):
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("x-api-key", ANTHROPIC_KEY)
            req.add_header("anthropic-version", "2023-06-01")
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    res = json.loads(r.read())
                    try:
                        track_usage(m, res.get("usage") or {})
                    except Exception as e:
                        print("Usage track error:", e)
                    if not model:
                        WORKING_MODEL["name"] = m
                    if res.get("stop_reason") == "max_tokens":
                        print("Claude: answer truncated (max_tokens)", m)
                        return ""
                    return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text").strip()
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode()[:300]
                except Exception:
                    pass
                print("Claude HTTP error:", m, e.code, detail)
                if e.code == 400 and "between_tools" in detail and payload.get("thinking", {}).get("type") != "between_tools":
                    THINKING[m] = {"type": "between_tools"}   # yangi API: "o'ylamasdan" rejimi shunday yoziladi
                    payload["thinking"] = THINKING[m]
                    body = json.dumps(payload).encode()
                    continue
                if e.code == 400 and "thinking" in detail.lower() and "thinking" in payload:
                    NO_THINKING[m] = False          # bu model "thinking" parametrini qabul qilmaydi
                    payload.pop("thinking")
                    body = json.dumps(payload).encode()
                    continue
                if e.code in (400, 403, 404) and ("model" in detail.lower() or e.code == 404):
                    break           # bu model yo'q — keyingisiga
                time.sleep(2 * (attempt + 1))
            except Exception as e:
                print("Claude error:", m, e)
                time.sleep(2 * (attempt + 1))
    return ""


def detect_business(text):
    biz_list = "\n".join([f"{b[1]} = {b[0]}" for b in BUSINESSES])
    prompt = f'Foydalanuvchi: "{text}"\nBiznes kodini toping:\n{biz_list}\nFaqat kod yozing.'
    code = claude("Faqat kod yoz.", [{"role": "user", "content": prompt}], max_tokens=20, model=DETECT_MODEL).lower()
    valid = [b[1] for b in BUSINESSES]
    return code if code in valid else None


def is_from_site(text):
    return "uchun AI agent demosini ko'rishni xohlayman" in text


def is_site_button(text):
    return "Menga «" in text and "qiziq" in text or is_from_site(text)


def build_messages(history):
    msgs = []
    for h in history[-MAX_HISTORY:]:
        role = "assistant" if h["r"] == "a" else "user"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + h["t"]
        else:
            msgs.append({"role": role, "content": h["t"]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs

# ==========================================================================
# Til aniqlash (1000 dialogda sinalgan)
# ==========================================================================
KEEP_LATIN = {"crm", "erp", "ai", "api", "1c", "telegram", "instagram", "excel", "ios", "android", "app", "store",
              "google", "play", "whatsapp", "businessai", "uz", "it", "sms", "pdf", "online", "ok", "okay", "landing",
              "click", "payme", "faq", "nda", "ielts", "seo", "smm"}
UZ_LETTERS = set("ўқғҳЎҚҒҲ")
RU_LETTERS = set("ыщЫЩ")
RU_WORDS = set("""и в во на не что как это для мне нам вы я мы есть нет да можно нужно надо сколько стоит пожалуйста
здравствуйте спасибо хочу а но по за с со к о об от до из же ли бы уже ещё еще тоже просто очень когда где сейчас
какой какая какие каких цена цену после перезвоните перезвоню позвоните звоните коротко доставка подробнее расскажите
его её ее их меня вас вам нас наш наша ваш ваша мой моя только если чтобы так тут там вот всё все весь будет было был
была могу можете хотим хотел хотела давайте пока потом сегодня завтра дорого дешевле нужен нужна нужны интересно
понятно ясно хорошо ладно привет добрый день вечер утро спс нормально подумаю посмотрим работаете делаете сделать
сделаете разве почему зачем кто чем при через без про также лучше ничего никак кроме вообще почти около примерно какое
каком ну жду ждём ждем звонка звонок здрасте здравствуй алло давай удачи ага супер отлично понял поняла поняли прайс
человека человек дайте одежда логистика аптека опт брони рассрочка рассрочку бесплатно поддержка других магазина
магазин салона главврачу передам заявки разработка будет буду будем""".split())
UZ_WORDS = set("""нима нега қанча канча қанақа канака қандай кандай борми бор йўқ йук йок керак керакмас керакми мумкин
мумкинми иложи иложиси хоп хўп ха ҳа майли яхши раҳмат рахмат салом ассалому алайкум ваалайкум сиз сизлар сизга сизда
сизни биз бизда бизга бизни биздан мен менга менда мени менинг улар шу шунақа шунака бу ўша уша қачон качон қаерда
каерда неч нечта неччи пул сўм сум минг ойига ойлик кун ҳафта хафта бугун эртага кейин кейинрок ҳозир хозир аввал
лекин лекн аммо ва ёки ҳам хам эмас эди экан экани эканми учун билан қилиш килиш қилсак килсак қилиб килиб бўлади
булади бўлса булса бўлиб булиб ишлаймиз ишлатамиз ишлатаман сотамиз сотаман дўкон дукон ака опа ука жуда кўп куп оз
озгина сал зўр зур тушунмадим тушундим тушунарли тушунарсиз ёзаман ёзинг ёзиб беринг беринглар бериш олиш оламиз
оламан ташлаб кўрсатинг курсатинг кўриш куриш гаплашамиз гаплашайлик қўнғироқ конгирок кунгирок рақам ракам холос
ҳолос хеч ҳеч ҳамма хамма ҳаммаси хаммаси кимга ким нарса нарх нархи нархлар арзон қиммат киммат кимматку ишонмайман
ишонаман ишламайди ишлайди тўғри тугри нотўғри бир икки уч эса деди дедим айтинг айтдим айтаман неча нечи килинг
қилинг оркали орқали асосан телим хисоби ҳисоби ми мисиз уйлаб ўйлаб курай кўрай натижа узим ўзим ёзилиш маркази
марказ укув ўқув савдо махфий мисан ассалом кечкурун кечқурун та тагача ойда йилига кишим одам ходим ходимлар мижоз
мижозлар буюртма буюртмалар хисоб ҳисоб харажат тушади тушасиз бизнеси бизнесим бизнесимиз соҳа соха соҳасида
сохасида ошириш учун ишлаб чиқариш чикариш блакнот дафтар ишлатамиз молжалим мўлжал атрофида толик тўлиқ""".split())
NEUTRAL = set("""ок окей ok скидка скидку скидки сайт сайтга сайтни телефон тел номер номерим телеграм телеграмм телега
инстаграм эксель excel вой вооой воой клиент клиентлар реально короче норм хмм ммм ааа ресторан кафе клиника автосалон
автосервис бот срм ерп 1с блокнот меню кейтеринг конструктор интернет магазин у бронь бронни""".split())
UZ_SUFFIX = re.compile(r"(ми|мизми|сизми|лар|ларни|ларга|ларда|лардан|ларнинг|миз|имиз|ингиз|сиз|ган|ганмиз|моқчи|мокчи|"
                       r"япти|ябди|япман|япмиз|аман|аймиз|айман|йман|ади|адими|ини|нинг|дан|чи|чилик|лик|ликни|лари|ларини|"
                       r"сила|сизла|асила|асизла|дами|даги|дик|дим|дингиз|мас|маймиз|майди|экан|сак|сангиз|ишимиз|ман|"
                       r"мисан|санми|ларми|сизларми|сизлар|сизлардан|ларингиз|миканслар|миканлар|адиган|ганман|гани|моқда|мокда|"
                       r"еси|оси|аси|иси|уси|сини|сига|сида|сидан|имиз|имни|имга|имда)$")
UZ_STRONG_SUFFIX = re.compile(r"(ларми|сизларми|сизлар|моқчи|мокчи|япти|ябди|япман|ганмиз|адими|адиган|ингиз|миканслар|"
                              r"ларингиз|сизми|мизми|дими|ганман)$")
RU_SUFFIX = re.compile(r"(ость|ться|тся|ешь|ете|ого|его|ому|ему|ыми|ими|ией|ание|ение|ый|ий|ой|ая|яя|ое|ее|ые|ие|ует|"
                       r"ают|ят|ит|ить|ать|ять|еть|уть|ов|ев|ами|ями|ах|ях|ировать|ически|ство|ская|ский|ское|ские|ность)$")
ARTIFACT_RE = re.compile(r"https?://\S+|@\w+|\$?\d[\d\s\-$.,%:]*")
WORD_RE = re.compile(r"[A-Za-zʻ'’\x60]+|" + CYR_CLASS + "+")
GLUED_RE = re.compile(r"[A-Za-z0-9](" + CYR_CLASS + "{2,6})(?!" + CYR_CLASS + ")")


ONE_C_RE = re.compile(r"(?i)\b1\s?[сc]\s?(да|дан|га|ни|нинг|da|dan|ga|ni)?\b")


def lang_evidence(text):
    uz_bonus = 1.5 if re.search(r"(?i)\b1\s?[сc]\s?(да|дан|га|ни|нинг)\b", text) else 0.0
    t = ARTIFACT_RE.sub(" ", ONE_C_RE.sub(" ", text))
    words = [w for w in WORD_RE.findall(t) if w.lower().strip("'’\x60ʻ") not in KEEP_LATIN]
    lat = sum(len(w) for w in words if re.match(r"[A-Za-z]", w))
    cw = [w.lower() for w in words if re.match(CYR_CLASS, w)]
    cyr = sum(len(w) for w in cw)
    uz, ru = uz_bonus, 0.0
    for w in cw:
        if w in NEUTRAL:
            continue
        if any(ch in UZ_LETTERS for ch in w):
            uz += 3
        if any(ch in RU_LETTERS for ch in w):
            ru += 2
        if w in UZ_WORDS:
            uz += 2
        elif w in RU_WORDS:
            ru += 2
        else:
            if len(w) >= 5 and UZ_STRONG_SUFFIX.search(w):
                uz += 1.5
            elif len(w) >= 3 and UZ_SUFFIX.search(w):
                uz += 0.7
            if len(w) >= 4 and RU_SUFFIX.search(w):
                ru += 0.7
    for g in GLUED_RE.findall(text):          # excelда, 7да, 990дан
        uz += 1.5
        if g.lower() in RU_WORDS:
            ru -= 2
    return {"lat": lat, "cyr": cyr, "uz": uz, "ru": ru}


def classify_script(text, prev=None):
    """'uz_cyr' | 'uz_lat' | 'ru' | '' — prev: shu suhbatdagi oldingi qaror"""
    e = lang_evidence(text)
    if e["lat"] + e["cyr"] < 2:
        return prev or ""
    if e["lat"] == 0 and e["uz"] == 0 and e["ru"] == 0:
        return prev or "ru"
    if e["lat"] > e["cyr"]:
        return "uz_lat"
    diff = e["uz"] - e["ru"]
    if diff >= 0.7:
        return "uz_cyr"
    if diff <= -0.7:
        return "ru"
    if prev in ("uz_cyr", "uz_lat"):
        return "uz_cyr"
    if prev == "ru":
        return "ru"
    return "uz_cyr" if diff > 0 else "ru"


LANG_REQ_RU = re.compile(r"(?i)((можно|давайте|пишите|пиши|лучше|говорите)\s*(на|по)[- ]?русск|на русском\s*(можно|пожалуйста|пиши)|"
                         r"по[- ]?узбекски\s*(плохо|не)|не понимаю по[- ]?узбекски|ruscha\s*(yoz|gapir)|русча\s*(ёз|гапир)|"
                         r"rus tilida\s*(yoz|gapir)|рус тилида\s*(ёз|гапир))")
LANG_REQ_UZ = re.compile(r"(?i)((узбекча|ўзбекча|o'?zbekcha)\s*(ёз|yoz|гапир|gapir|ёзсам|yozsam|майли|mayli)|"
                         r"(можно|давайте|пишите|пиши|лучше)\s*(на|по)[- ]?узбекск|"
                         r"(узбек|ўзбек|o'?zbek) тилида\s*(ёз|гапир)|o'?zbek tilida\s*(yoz|gapir))")


def client_script(c):
    """Javob yoziladigan til/alifbo: oxirgi aniq mijoz xabari + suhbat konteksti + mijoz iltimosi"""
    prev = None
    for h in c["history"]:
        t = h["t"]
        if h["r"] == "u" and t.startswith(STT.VOICE_PREFIX):
            t = t[len(STT.VOICE_PREFIX):]
        if h["r"] != "u" or t.startswith("[") or is_site_button(t):
            continue
        s = classify_script(t, prev)
        if s:
            prev = s
        if LANG_REQ_RU.search(t):
            c["lang_pref"] = "ru"
        elif LANG_REQ_UZ.search(t):
            c["lang_pref"] = "uz"
    script = prev or c.get("script") or "uz_lat"
    pref = c.get("lang_pref")
    if pref == "ru":
        return "ru"
    if pref == "uz" and script == "ru":
        return "uz_cyr"
    return script


SCRIPT_HINT = {
    "uz_cyr": "ЯЗЫК КЛИЕНТА: узбекский (пишет кириллицей). Отвечай по-узбекски ЛАТИНИЦЕЙ — программа сама переведёт в кириллицу.",
    "uz_lat": "ЯЗЫК КЛИЕНТА: узбекский (латиница). Отвечай по-узбекски латиницей.",
    "ru": "ЯЗЫК КЛИЕНТА: русский. Отвечай по-русски.",
}

# ==========================================================================
# Transliteratsiya (lotin -> kirill)
# ==========================================================================
TR_KEEP = KEEP_LATIN - {"ok", "okay", "landing", "telegram", "instagram", "excel", "whatsapp", "online"}
TR_BRANDS = {"telegram": "Телеграм", "instagram": "Инстаграм", "excel": "Эксель", "whatsapp": "Ватсап", "online": "онлайн"}
TR_EXC = {"budjet": "бюджет", "byudjet": "бюджет", "konsultatsiya": "консультация", "menejer": "менежер",
          "aksiya": "акция", "chegirma": "чегирма", "sayt": "сайт", "landing": "лендинг", "obuna": "обуна",
          "kompaniya": "компания", "integratsiya": "интеграция", "prezentatsiya": "презентация", "demo": "демо",
          "server": "сервер", "dizayn": "дизайн", "admin": "админ", "backend": "бэкенд", "biznes": "бизнес",
          "restoran": "ресторан", "variant": "вариант", "telefon": "телефон", "internet": "интернет"}
L2C = [("ksiya", "кция"), ("tsiya", "ция"), ("yo'", "йў"), ("o'", "ў"), ("g'", "ғ"), ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"),
       ("ya", "я"), ("ye", "е"), ("e", "е"), ("a", "а"), ("b", "б"), ("d", "д"), ("f", "ф"), ("g", "г"), ("h", "ҳ"),
       ("i", "и"), ("j", "ж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("q", "қ"),
       ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("x", "х"), ("y", "й"), ("z", "з"), ("c", "к"),
       ("w", "в"), ("'", "ъ")]
C2L = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l",
       "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
       "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ё": "yo",
       "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h", "е": "e"}


def _case(src, dst):
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def lat2cyr_word(w):
    lw = w.lower().replace("ʻ", "'").replace("’", "'").replace("\x60", "'")
    for b, cyr in TR_BRANDS.items():
        if lw.startswith(b):
            rest = lw[len(b):].lstrip("'")
            out = cyr if w[:1].isupper() or b in ("telegram", "instagram", "whatsapp") else cyr.lower()
            return out + (lat2cyr_word(rest) if rest else "")
    for k, v in TR_EXC.items():
        if lw == k or (len(k) >= 5 and lw.startswith(k)):
            rest = lw[len(k):]
            return _case(w, v + (lat2cyr_word(rest) if rest else ""))
    out, i = "", 0
    while i < len(lw):
        if i == 0 and lw[0] == "e":
            out += "э"
            i += 1
            continue
        for a, b in L2C:
            if lw.startswith(a, i):
                out += b
                i += len(a)
                break
        else:
            out += lw[i]
            i += 1
    return _case(w, out)


def cyr2lat_word(w):
    lw = w.lower()
    out = ""
    for i, ch in enumerate(lw):
        if ch == "е" and (i == 0 or lw[i - 1] in "аеёиоуўэюяъь"):
            out += "ye"
        else:
            out += C2L.get(ch, ch)
    return _case(w, out)


LAT_WORD_RE = re.compile(r"(?<![@/\w.])[A-Za-z][A-Za-zʻ'’\x60]*(?![\w.]*\.(?:uz|com|ru)\b)")


def to_cyr(text):
    def rep(m):
        w = m.group(0)
        if w.lower().strip("'") in TR_KEEP or (w.isupper() and len(w) >= 2):
            return w
        return lat2cyr_word(w)
    return LAT_WORD_RE.sub(rep, text)


def to_lat(text):
    return re.sub(CYR_CLASS + "+", lambda m: cyr2lat_word(m.group(0)), text)


def render(text, script):
    """Model matnini mijoz alifbosiga keltirish"""
    if script == "uz_cyr":
        return to_cyr(text)
    if script == "uz_lat":
        return to_lat(text)
    return text

# ==========================================================================
# Qo'riqchilar
# ==========================================================================
JUNK_RE = re.compile("[" + chr(0x2E80) + "-" + chr(0x9FFF) + chr(0xAC00) + "-" + chr(0xD7AF) + chr(0x3040) + "-"
                     + chr(0x30FF) + chr(0xFF00) + "-" + chr(0xFFEF) + chr(0x600) + "-" + chr(0x6FF) + "]")
ALLOWED_NUMS = {"290", "590", "1090", "990", "1990", "4490", "99", "1490", "24", "7", "22", "998", "93", "890", "02", "1"}
PHONE_RE = re.compile(r"(?:\+?998[\s\-]?)?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b|(?i:\b(?:soat|соат|в|с|до|после|к|от)\s*\d{1,2}\b)|"
                     r"(?i:\b\d{1,2}\s*(?:da|dan|gacha|ga|да|дан|гача|га|ч|час|часа|часов|утра|вечера|дня)\b)")


def clean_text(t):
    t = JUNK_RE.sub("", t)
    t = t.replace("**", "").replace("__", "").replace("##", "")
    t = re.sub(r"^\s*[-•✅]\s*", "", t, flags=re.M)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    return t


def client_numbers(history):
    nums = set()
    for h in history:
        if h["r"] == "u":
            t = h["t"]
            nums.update(re.findall(r"\d+", t))
            nums.update(x.replace(" ", "") for x in re.findall(r"\d{1,3}(?: \d{3})+", t))
            for k in re.findall(r"(\d+)\s*(?:k|к|минг|ming|тыс\w*|тыщ\w*)", t, flags=re.I):
                nums.add(str(int(k) * 1000))
            for k in re.findall(r"(?:тыс\w*|тыщ\w*|минг|ming)\s*(\d+)", t, flags=re.I):
                nums.add(str(int(k) * 1000))
    return nums


def bad_numbers(text, history):
    allowed = ALLOWED_NUMS | client_numbers(history)
    t = PHONE_RE.sub(" ", text)
    t = re.sub(r"\b\d{1,2}[:.]\d{2}\b", " ", t)
    t = TIME_RE.sub(" ", t)
    return [n for n in re.findall(r"\d+", t) if n not in allowed]


def norm(s):
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


def is_repeat(msg, history, thr=0.72):
    m = norm(to_lat(msg))
    if len(m) < 12:
        return False
    for h in history:
        if h["r"] == "a" and difflib.SequenceMatcher(None, m, norm(to_lat(h["t"]))).ratio() >= thr:
            return True
    return False


def parse_json(raw):
    """Model javobidan JSON ni ishonchli ajratish (```json, ortiqcha matn, ichki qo'shtirnoqlar)"""
    raw = re.sub(r"```(?:json)?", "", raw or "")
    try:
        a = raw.index("{")
    except ValueError:
        return None
    depth, instr, esc = 0, False, False
    for i in range(a, len(raw)):          # birinchi to'liq {...} ni topish
        ch = raw[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[a:i + 1])
                except Exception:
                    break
    # oxirgi chora: "messages" massividagi satrlarni qo'lda ajratib olish
    m = re.search(r'"messages"\s*:\s*\[(.*?)\]\s*(?:,|\}|$)', raw, flags=re.S)
    if not m:
        return None
    items = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
    if not items:
        return None
    d = {"messages": [_unq(x) for x in items]}
    for k in ("readiness", "action", "stage"):
        mm = re.search(r'"' + k + r'"\s*:\s*"?([\w.]+)', raw)
        if mm:
            d[k] = mm.group(1)
    return d


def _unq(x):
    try:
        return json.loads('"' + x + '"')
    except Exception:
        return x.replace('\\"', '"')


SERVICE_TEXT_RE = re.compile(r'[{}\[\]]|"?(messages|readiness|stage|action)"?\s*:|мессагес|реадинесс')


def looks_like_service_text(t):
    return bool(SERVICE_TEXT_RE.search(t))


def drop_sentences_with(text, nums):
    parts = re.split(r"(?<=[.!?])\s+", text)
    keep = [p for p in parts if not any(re.search(r"(?<!\d)" + n + r"(?!\d)", p) for n in nums)]
    return " ".join(keep).strip()


FACT_LABELS = [("business", "Бизнес"), ("need", "Потребность"), ("current_tool", "Сейчас использует"),
               ("budget", "Бюджет"), ("offer", "Ты уже предложил"), ("objection", "Возражение"),
               ("name", "Имя"), ("phone", "Телефон"), ("call_time", "Удобное время звонка")]


def facts_block(c):
    f = c.get("facts", {})
    lines = [f"- {lab}: {f[k]}" for k, lab in FACT_LABELS if f.get(k)]
    asked = [to_lat(h["t"]) for h in c["history"] if h["r"] == "a" and "?" in h["t"]][-6:]
    out = "ЧТО УЖЕ ИЗВЕСТНО О КЛИЕНТЕ (не переспрашивай):\n" + ("\n".join(lines) if lines else "- пока ничего")
    out += f"\n- Готовность: {c.get('readiness', 0)}%"
    if asked:
        out += "\nТвои прошлые вопросы (НЕ повторяй их и их смысл):\n" + "\n".join("- " + q for q in asked)
    return out


def model_history(c, script):
    """Modelga tarix: bot xabarlari lotinda (model o'zi shunday yozgan)"""
    hist = []
    for h in c["history"]:
        t = h["t"]
        if h["r"] == "a" and script.startswith("uz"):
            t = to_lat(t)
        hist.append({"r": h["r"], "t": t})
    return build_messages(hist)


def pick_model(c):
    """Gibrid: oddiy suhbat — asosiy (arzon) model, mijoz isiganda — SMART_MODEL"""
    if SMART_MODEL and int(c.get("readiness") or 0) >= SMART_FROM:
        return SMART_MODEL
    return None


def generate_reply(c, script, model=None):
    first = not any(h["r"] == "a" for h in c["history"])
    model = model or pick_model(c)
    msgs = model_history(c, script)
    if not msgs:
        return None
    mode = ("ЭТО ПЕРВЫЙ ОТВЕТ В ДИАЛОГЕ: 3 сообщения — приветствие; как дела; лёгкое уточнение его вопроса."
            if first else "Диалог уже идёт: НЕ здоровайся и не спрашивай про дела. 1-2 коротких сообщения.")
    dyn = SCRIPT_HINT[script] + "\n\n" + facts_block(c) + "\n\n" + mode
    data, feedback, best = None, "", None
    for attempt in range(2):
        convo = msgs if not feedback else msgs + [
            {"role": "assistant", "content": json.dumps({"messages": data.get("_raw", [])}, ensure_ascii=False)},
            {"role": "user", "content": "[СИСТЕМА] " + feedback}]
        raw = claude(dyn, convo, max_tokens=500, model=model, cache_prefix=IG.prompt_for(c))
        if not raw and model and model == pick_model(c):
            raw = claude(dyn, convo, max_tokens=500, cache_prefix=IG.prompt_for(c))   # gibrid model ishlamasa
        if not raw:
            return None
        d = parse_json(raw)
        if d is None:
            if "{" in raw or "messages" in raw:
                print("Unparseable model output:", raw[:300])
                d = {"messages": [], "readiness": c.get("readiness", 0)}
            else:
                d = {"messages": [p for p in re.split(r"\n\s*\n", raw) if p.strip()], "readiness": c.get("readiness", 0)}
        raw_msgs = [clean_text(str(m)) for m in (d.get("messages") or []) if str(m).strip()]
        raw_msgs = [m for m in raw_msgs if m and not looks_like_service_text(m)]
        d["_raw"] = raw_msgs
        out = [render(m, script) for m in raw_msgs]
        d["messages"] = out
        problems = []
        nums = sorted({n for m in out for n in bad_numbers(m, c["history"])})
        if nums:
            problems.append("Убери выдуманные числа " + ", ".join(nums) + " — их нет в базе.")
        reps = [m for m in raw_msgs if is_repeat(m, c["history"])]
        if reps:
            problems.append("Ты повторяешь уже сказанное: «" + reps[0] + "». Скажи по-другому и двигай разговор дальше.")
        if sum(len(m) for m in out) > MAX_REPLY_CHARS or any(len(m) > MAX_MSG_CHARS for m in out):
            problems.append("Слишком длинно. Каждое сообщение до 16 слов, всего 1-2 сообщения.")
        if sum(m.count("?") for m in out) > (2 if first else 1):
            problems.append("Только один вопрос в ответе.")
        if first and len(out) < 2:
            problems.append("Первый ответ — 3 коротких сообщения: приветствие, как дела, уточнение.")
        if not out:
            problems.append("Ответ не распознан. Верни строго один валидный JSON-объект без лишнего текста.")
        if script.startswith("uz") and re.search(r"(?i)\b(дорого|короче|скидка|просто|конечно|хорошо)\b", " ".join(raw_msgs)):
            problems.append("В узбекском ответе русские слова. Пиши только по-узбекски латиницей.")
        if best is None or len(problems) < best[0]:
            best = (len(problems), d)
        data = d
        if not problems or attempt == 1:
            break
        feedback = " ".join(problems) + " Верни исправленный JSON."
    data = best[1]
    out = data["messages"]
    nums = sorted({n for m in out for n in bad_numbers(m, c["history"])})
    if nums:
        out = [drop_sentences_with(m, nums) for m in out]
    out = [m for m in out if m and not is_repeat(m, c["history"], 0.9) and not looks_like_service_text(m)]
    out = out[:3] if first else out[:2]
    data["messages"] = out
    return data

# ==========================================================================
# Hisobotlar
# ==========================================================================
def report_target(c):
    return c.get("report_chat") or REPORT_CHAT_ID or STATE["owners"].get(c.get("bc_id") or "", "")


def send_report(c, title):
    target = report_target(c)
    if not target:
        print("Report skipped (no target):", title)
        return
    f = c.get("facts", {})
    who = c.get("name") or "-"
    if c.get("username"):
        who += " (@" + c["username"] + ")"
    lines = [title, "", f"Клиент: {who}", f"Ссылка: tg://user?id={c.get('chat_id')}",
             f"Готовность купить: {c.get('readiness', 0)}%"]
    for k, lab in FACT_LABELS + [("note", "Как идёт диалог")]:
        if k != "name" and f.get(k):
            lines.append(f"{lab}: {f[k]}")
    tail = c["history"][-10:]
    if tail:
        lines.append("\nПоследние сообщения:")
        for h in tail:
            lines.append(("👤 " if h["r"] == "u" else "🤖 ") + h["t"][:200])
    send_msg(target, "\n".join(lines)[:4000])

# ==========================================================================
# Dialog
# ==========================================================================
def ai_reply(key):
    c = chat_state(key)
    script = client_script(c)
    c["script"] = script
    if TYPING_DELAY and c.get("channel") != "ig":
        typing(c["chat_id"], c["bc_id"])
    d = generate_reply(c, script) or {"messages": []}
    out = d.get("messages") or []
    if not out and not c.get("error_reported"):
        c["error_reported"] = True
        send_report(c, "⚠️ Бот не смог сформулировать ответ — ответьте клиенту вручную")
    if out:
        c["error_reported"] = False
        deliver(c, out)
        with LOCK:
            for m in out:
                c["history"].append({"r": "a", "t": m, "ts": time.time()})
    with LOCK:
        for k in ("name", "phone", "business", "need", "current_tool", "budget", "offer", "objection", "call_time", "note"):
            v = str(d.get(k) or "").strip()
            if v:
                c["facts"][k] = v[:200]
        try:
            c["readiness"] = max(0, min(100, int(d.get("readiness", c["readiness"]))))
        except Exception:
            pass
    action = str(d.get("action") or "none")
    client_text = " ".join(h["t"] for h in c["history"] if h["r"] == "u")
    has_phone = bool(c["facts"].get("phone")) or bool(PHONE_RE.search(client_text))
    if (action == "lead" or has_phone) and not c.get("lead_sent"):
        c["lead_sent"] = True
        c["hot_sent"] = True
        c["status"] = "lead"
        if not c["facts"].get("phone"):
            m = PHONE_RE.search(client_text)
            if m:
                c["facts"]["phone"] = m.group(0)
        send_report(c, "🔥 ЛИД: клиент оставил контакт / согласился")
    elif c["readiness"] >= HOT_THRESHOLD and not c.get("hot_sent"):
        c["hot_sent"] = True
        send_report(c, "🌶 ГОРЯЧИЙ КЛИЕНТ — пора подключаться")
    if action == "stop":
        c["status"] = "stopped"
    elif action == "handoff":
        c["status"] = "handoff"
        send_report(c, "🙋 Клиент просит живого менеджера")


def record_client(chat_id, text, bc_id, sender):
    key = f"{bc_id or 'direct'}:{chat_id}"
    with LOCK:
        c = chat_state(key)
        c["chat_id"] = chat_id
        c["bc_id"] = bc_id
        nm = " ".join(x for x in [sender.get("first_name"), sender.get("last_name")] if x)
        if nm:
            c["name"] = nm
        if sender.get("username"):
            c["username"] = sender["username"]
        stamp = time.time()
        c["history"].append({"r": "u", "t": text, "ts": stamp})
        c["history"] = c["history"][-MAX_HISTORY * 2:]
        c["last_client"] = stamp
        c["followups"] = 0
        if c["status"] == "stopped":
            c["status"] = "active"
    return key, stamp


def respond(key, stamp=None):
    """DEBOUNCE: mijoz yana yozsa — kutamiz, keyin hammasiga bitta javob"""
    if stamp is not None and DEBOUNCE_SEC > 0:
        time.sleep(DEBOUNCE_SEC)
        if chat_state(key)["last_client"] != stamp:
            return
    with chat_lock(key):
        c = chat_state(key)
        if stamp is not None and c["last_client"] != stamp:
            return
        if c["paused_until"] > time.time():
            save_chat(key)
            return
        last = c["history"][-1]["t"] if c["history"] else ""
        if c.get("channel") != "ig" and is_from_site(last) and not any(h["r"] == "a" for h in c["history"]):
            biz_key = detect_business(last)
            if biz_key:
                biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
                demo = f"{biz_name} uchun AI agent demosi:\n\n{DEMO_URL}?b={biz_key}"
                send_msg(c["chat_id"], demo, c["bc_id"])
                with LOCK:
                    c["facts"].setdefault("business", biz_name)
                    c["demo_sent"] = True
        if AI_REPLIES and c["status"] != "handoff":
            ai_reply(key)
        save_chat(key)


def on_client_message(chat_id, text, bc_id, sender):
    key, stamp = record_client(chat_id, text, bc_id, sender)
    respond(key, stamp)


def on_owner_message(chat_id, bc_id, text=""):
    key = f"{bc_id}:{chat_id}"
    c = chat_state(key)
    with LOCK:
        c["chat_id"] = chat_id
        c["bc_id"] = bc_id
        c["paused_until"] = time.time() + HUMAN_PAUSE_HOURS * 3600
        if text:
            c["history"].append({"r": "a", "t": text, "ts": time.time(), "human": True})
    save_chat(key)


def owner_id_for(bc_id):
    if not bc_id:
        return None
    oid = STATE["owners"].get(bc_id)
    if oid:
        return oid
    res = tg("getBusinessConnection", {"business_connection_id": bc_id})
    user = (res.get("result") or {}).get("user") or {}
    if user.get("id"):
        with LOCK:
            STATE["owners"][bc_id] = user["id"]
        save_owner(bc_id)
        return user["id"]
    return None

# ==========================================================================
# Eslatmalar (follow-up)
# ==========================================================================
def quiet_now(ts):
    h = datetime.fromtimestamp(ts, TZ).hour
    return h >= QUIET_FROM or h < QUIET_TO


def due_followup(c, now):
    if not AI_REPLIES or c["status"] != "active" or not c.get("chat_id"):
        return False
    if c["paused_until"] > now or c["followups"] >= len(FOLLOWUP_MINUTES):
        return False
    h = c["history"]
    if not h or h[-1]["r"] != "a":
        return False
    if now - c["last_client"] > TG_WINDOW:
        return False
    if now - c["last_client"] < FOLLOWUP_MINUTES[c["followups"]] * 60:
        return False
    if quiet_now(now):
        return False
    return True


def send_followup(key):
    with chat_lock(key):
        c = chat_state(key)
        now = time.time()
        if not due_followup(c, now):
            return
        n = c["followups"] + 1
        total = len(FOLLOWUP_MINUTES)
        stage = FOLLOWUP_STAGES[-1] if n >= total else FOLLOWUP_STAGES[min(n - 1, len(FOLLOWUP_STAGES) - 2)]
        script = client_script(c)
        dyn = SCRIPT_HINT[script] + "\n\n" + facts_block(c) + "\n\n" + FOLLOWUP_INSTR.format(n=n, total=total, stage=stage)
        msgs = model_history(c, script)
        msgs.append({"role": "user", "content": "[СИСТЕМА] Напиши напоминание."})
        merged = []
        for m in msgs:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(m)
        text = ""
        for attempt in range(2):
            raw = claude(dyn, merged, max_tokens=150, cache_prefix=IG.prompt_for(c))
            d = parse_json(raw) if raw.strip().startswith("{") else None
            if d and d.get("messages"):
                raw = " ".join(str(x) for x in d["messages"])
            t = render(clean_text(raw.strip().strip('"«»')), script)
            if looks_like_service_text(t):
                t = ""
            if t and not bad_numbers(t, c["history"]) and not is_repeat(t, c["history"], 0.6) and len(t) <= MAX_MSG_CHARS:
                text = t
                break
        with LOCK:
            c["followups"] = n
        if text:
            deliver(c, [text])
            with LOCK:
                c["history"].append({"r": "a", "t": text, "ts": time.time(), "f": n})
        save_chat(key)


def scheduler():
    last_maint = 0
    while True:
        try:
            now = time.time()
            if now - last_maint > 3600:
                last_maint = now
                IG.maintenance()
            with LOCK:
                keys = [k for k, c in STATE["chats"].items() if due_followup(c, now)]
            for k in keys:
                send_followup(k)
        except Exception as e:
            print("Scheduler error:", e)
        time.sleep(60)

# ==========================================================================
# Update handler
# ==========================================================================
def tg_voice_text(msg):
    """Telegram ovozli xabari -> matn (STT sozlangan bo'lsa)"""
    obj = msg.get("voice") or msg.get("audio") or msg.get("video_note") or {}
    if STT.configured() and obj.get("file_id"):
        info = tg("getFile", {"file_id": obj["file_id"]}).get("result") or {}
        path = info.get("file_path")
        if path:
            data = STT.fetch("https://api.telegram.org/file/bot" + BOT_TOKEN + "/" + path)
            name = path.rsplit("/", 1)[-1] or "voice.ogg"
            mime = obj.get("mime_type") or ("video/mp4" if msg.get("video_note") else "audio/ogg")
            t = STT.transcribe(data, name, mime)
            if t:
                return STT.voice_note(t)
    return STT.VOICE_FALLBACK


def handle(update):
    if "business_connection" in update:
        bc = update["business_connection"]
        print("Business connection:", bc.get("id"), "enabled:", bc.get("is_enabled"))
        if bc.get("id") and (bc.get("user") or {}).get("id"):
            with LOCK:
                STATE["owners"][bc["id"]] = bc["user"]["id"]
            save_owner(bc["id"])
        return

    if "business_message" in update:
        msg = update["business_message"]
        chat = msg.get("chat", {})
        if chat.get("type") != "private":
            return
        chat_id = chat["id"]
        bc_id = msg.get("business_connection_id")
        sender = msg.get("from", {})
        owner = owner_id_for(bc_id)
        if owner and sender.get("id") == owner:
            on_owner_message(chat_id, bc_id, (msg.get("text") or "").strip())
            return
        if sender.get("is_bot"):
            return
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            if msg.get("voice") or msg.get("audio") or msg.get("video_note"):
                text = tg_voice_text(msg)
            elif msg.get("photo") or msg.get("document") or msg.get("video"):
                text = "[клиент отправил файл/фото без подписи]"
            elif msg.get("contact"):
                ct = msg["contact"]
                text = f"{ct.get('first_name', '')} {ct.get('phone_number', '')}".strip()
            elif msg.get("sticker"):
                text = msg["sticker"].get("emoji") or "👍"
            else:
                return
        on_client_message(chat_id, text, bc_id, sender)
        return

    if "message" in update:
        msg = update["message"]
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()
        if text.startswith("/start"):
            send_msg(chat_id, "Bot ishlayapti! / Бот работает!\n\nSizning chat ID: " + str(chat_id))
            return
        if text.startswith("/eval") and str(chat_id) == str(REPORT_CHAT_ID):
            send_msg(chat_id, EVAL.start(text[5:].strip(), lambda t: send_msg(chat_id, t)))
            return
        if text.startswith("/cost") and str(chat_id) == str(REPORT_CHAT_ID):
            send_msg(chat_id, usage_report())
            return
        if text.startswith("/ig") and str(chat_id) == str(REPORT_CHAT_ID):
            reply = IG.admin_command((msg.get("text") or "").strip())
            if reply:
                send_msg(chat_id, reply)
            return
        if chat.get("type") == "private" and text:
            on_client_message(chat_id, text, None, msg.get("from", {}))
        return

    if "callback_query" in update:
        tg("answerCallbackQuery", {"callback_query_id": update["callback_query"]["id"]})


import stt as STT  # noqa: E402  (ovozli xabarlar)
import evalrun as EVAL  # noqa: E402  (modellarni solishtirish)
import ig as IG  # noqa: E402  (Instagram kanali)
IG.init(sys.modules[__name__])
EVAL.init(sys.modules[__name__])


class ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if IG.handle_post(self, body):
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        try:
            update = json.loads(body)
        except Exception as e:
            print("Bad update:", e)
            return
        threading.Thread(target=self._run, args=(update,), daemon=True).start()

    @staticmethod
    def _run(update):
        try:
            handle(update)
        except Exception as e:
            print("Error:", e)

    def do_GET(self):
        if IG.handle_get(self):
            return
        if self.path.split("?")[0].rstrip("/") == "/eval/last":
            IG.respond_html(self, 200, f"status: {EVAL.LAST['status']}\n\n{EVAL.LAST['text']}",
                            ctype="text/plain; charset=utf-8")
            return
        self.send_response(200)
        self.end_headers()
        me = tg("getMe", {})
        info = f"Bot: @{me.get('result', {}).get('username', '?')}\n"
        info += f"can_connect_to_business: {me.get('result', {}).get('can_connect_to_business', False)}\n"
        with LOCK:
            info += f"chats: {len(STATE['chats'])}\nmemory: {'postgres' if DB is not None else 'file'}\n"
        info += f"model: {WORKING_MODEL['name'] or MODELS[0]}\n"
        info += f"instagram: {'configured' if IG.configured() else 'not configured'}, accounts: {len(STATE.get('tenants', {}))}\n"
        info += f"voice: {STT.provider()}\n"
        info += usage_report() + "\n"
        info += f"smart model: {SMART_MODEL or 'off'} (from {SMART_FROM}%)\n"
        self.wfile.write(info.encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    load_state()
    port = int(os.environ.get("PORT", 8080))
    if WEBHOOK_URL:
        tg("deleteWebhook", {"drop_pending_updates": True})
        time.sleep(1)
        result = tg("setWebhook", {
            "url": WEBHOOK_URL,
            "allowed_updates": [
                "message", "callback_query",
                "business_connection", "business_message",
                "edited_business_message", "deleted_business_messages"
            ],
            "drop_pending_updates": True
        })
        print("Webhook:", result)
    threading.Thread(target=scheduler, daemon=True).start()
    print("Bot running on port", port, "| memory:", "postgres" if DB is not None else "file", "| models:", MODELS)
    ThreadingServer(("0.0.0.0", port), Handler).serve_forever()
