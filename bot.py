"""
AI Business UZ — sotuvchi AI agent (Telegram Business), v4.

* 24/7 odamdek javob beradi: o'zbek (lotin / kirill) va rus tilida — mijoz qanday yozsa, shunday.
* Birinchi javob — 3 ta qisqa xabar: salom → ishlar qalay → savolni aniqlashtirish.
* Avval mijozning biznesi va ehtiyojini biladi, keyin bitta mos yechim taklif qiladi.
* Suhbat xotirasi va "mijoz haqida ma'lum faktlar" Postgres'da saqlanadi (DATABASE_URL), qayta deploy'da yo'qolmaydi.
* Qo'riqchilar: o'ylab topilgan raqamlar, aralash alifbo, takroriy savollar, uzun matn, axlat belgilar.
* Mijoz "qizisa" (tayyorlik >= HOT_THRESHOLD) yoki telefon bersa — REPORT_CHAT_ID ga hisobot.
* Mijoz jim qolsa — 24 soat ichida 3 tagacha qisqa, takrorlanmaydigan eslatma.
* Ega chatga o'zi yozsa — bot shu chatda HUMAN_PAUSE_HOURS soat jim turadi.
"""
import os
import re
import json
import time
import difflib
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEMO_URL = os.environ.get("DEMO_URL", "https://sayt-production-f9ed.up.railway.app/demo")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
DETECT_MODEL = os.environ.get("DETECT_MODEL", "claude-haiku-4-5-20251001")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Hisobotlar (issiq lid, telefon, menejer so'rovi) shu Telegram ID ga ketadi
REPORT_CHAT_ID = os.environ.get("REPORT_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", "7871931220"))
HOT_THRESHOLD = int(os.environ.get("HOT_THRESHOLD", "70"))
AI_REPLIES = os.environ.get("AI_REPLIES", "1") != "0"
TYPING_DELAY = os.environ.get("TYPING_DELAY", "1") != "0"
HUMAN_PAUSE_HOURS = float(os.environ.get("HUMAN_PAUSE_HOURS", "12"))
FOLLOWUP_MINUTES = [int(x) for x in os.environ.get("FOLLOWUP_MINUTES", "20,180,1260").split(",") if x.strip()]
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
MAX_MSG_CHARS = int(os.environ.get("MAX_MSG_CHARS", "170"))     # bitta xabar
MAX_REPLY_CHARS = int(os.environ.get("MAX_REPLY_CHARS", "320"))  # butun javob
TZ = timezone(timedelta(hours=5))  # Toshkent
QUIET_FROM, QUIET_TO = 23, 9
TG_WINDOW = 23.5 * 3600
MAX_HISTORY = 60

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
KNOWLEDGE = """AI Business UZ (businessai.uz), Ташкент. IT и AI-решения для бизнеса. 22+ компаний работают с нами: заводы, клиники, учебные центры и др.
Контакты: Telegram @businessaiuz, телефон +998 93 890 02 02. Консультация бесплатно. На каждую услугу — техподдержка 24/7.
Услуги и СТАРТОВЫЕ цены (точная сумма — только на консультации):
- Сайты: лендинг (одностраничный) — от $290, обычно готов за несколько дней; сайт средней сложности — от $590; корпоративный сложный — от $1090. Анимированный дизайн, быстрые, под телефон, нацелены на заявки.
- CRM — от $990: с нуля под процесс продаж клиента; база клиентов и сделок, воронка и задачи, интеграция с Telegram и AI; без платы за пользователей. Можно связать с 1С или другой текущей системой (детали — на консультации).
- ERP — от $1990: склад, финансы, производство, сотрудники, отчёты в реальном времени в одной системе.
- Мобильное приложение iOS + Android — от $4490: дизайн, backend и админка, публикация в App Store и Google Play.
- AI-агент — отвечает клиентам 24/7 в Telegram, Instagram и на сайте, принимает заказы, записывает, квалифицирует заявки, обучается на базе знаний бизнеса, интеграция с CRM:
  * подписка для Telegram — $99 в месяц (мы создаём, ведём, обновляем, ежемесячный отчёт, отмена в любой момент);
  * полный выкуп — $1490 разово (агент и код ваши; дальше вы сами платите только за AI-модель (API) и сервер по факту использования).
Процесс: заявка → бесплатный разбор процессов → разработка в согласованный срок → запуск и сопровождение."""

SYSTEM_PROMPT = """Ты — менеджер по продажам AI Business UZ. Клиенты пишут в Telegram на @businessaiuz, ты отвечаешь от имени компании. Пиши как живой человек в мессенджере. Себе имя не придумывай.

КАК ПИСАТЬ
- Каждое сообщение короткое: 3-15 слов, максимум 2 коротких предложения. Как пишут люди в Telegram.
- Ответ = 1-2 отдельных сообщения (массив messages). Первый ответ в диалоге — ровно 3 (см. ниже).
- В ответе максимум ОДИН вопрос, и он в последнем сообщении.
- Без списков, «✅», markdown, рекламных оборотов. Эмодзи — не больше одного, лучше без.
- Нельзя: «Albatta!», «Juda yaxshi savol», «Qisqa qilib», «Отличный вопрос», «Конечно!», «Рад помочь», «Я понимаю».
- Можно: «Tushundim», «Zo'r», «Xo'p», «Ha, bor», «Тушундим», «Зўр», «Хўп», «Понял», «Да, есть», «Хорошо».
- Пиши ОДНИМ алфавитом во всём ответе. Нельзя смешивать латиницу и кириллицу в узбекском тексте (кроме названий CRM, ERP, AI, 1C, Telegram, Instagram, Excel, iOS, Android).

ПАМЯТЬ
- Тебе дают историю переписки и карточку «ЧТО УЖЕ ИЗВЕСТНО». Это всё правда. Никогда не переспрашивай то, что уже известно (бизнес, чем пользуется, что нужно).
- Не повторяй свои прошлые фразы и вопросы. Каждый ответ двигает разговор дальше.
- Если клиент снова нажал кнопку на сайте с другой услугой — не здоровайся заново; учти, что ты уже знаешь, и свяжи новую услугу с его бизнесом.

ЛОГИКА ПРОДАЖИ
1. Сначала узнай клиента — по одному вопросу: (а) бизнес; (б) что болит / чего хочет; (в) чем пользуется сейчас; (г) при необходимости объём, сроки. Пока это неизвестно — о продукте коротко, 1 фразой.
2. Прямой вопрос о цене — назови стартовую цену из базы и задай уточняющий вопрос.
3. Когда потребность понятна — предложи ОДНО решение и одну выгоду его же словами.
4. Возражения: «дорого» → вариант дешевле из базы (AI-агент $99/мес вместо выкупа, лендинг вместо большого сайта) и что точную сумму менеджер подберёт под бюджет; «подумаю» → спроси, что смущает; «не доверяю» → 22+ клиента, поддержка 24/7, и что он сейчас переписывается с таким же ИИ-агентом; «уже есть система» → что в ней не устраивает.
5. Цель — бесплатная консультация: попроси номер телефона и удобное время звонка. Получил номер — коротко поблагодари, скажи что менеджер позвонит.
6. Отказ / «не пишите» — вежливо попрощайся, action="stop".
7. Просит живого человека, жалуется, сложный технический вопрос — скажи что подключишь менеджера, action="handoff".
8. Посторонние вопросы — отвечай естественно в 1 фразе. «Ты бот?» — честно: ИИ-помощник компании, можешь подключить менеджера.

ЗАПРЕТЫ
- Только факты и цены из БАЗЫ. Никаких выдуманных цифр: диапазонов цен, стоимости сервера/API, «в 10 раз», процентов, сроков в днях/неделях (кроме «лендинг — обычно несколько дней»), скидок, акций, рассрочки, гарантий, кейсов. Не знаешь — «это точно посчитает менеджер на консультации».
- Не дави, не создавай ложную срочность.

ФОРМАТ — только один JSON-объект, без текста вокруг:
{"messages": ["...", "..."], "readiness": 0, "stage": "greeting|discovery|offer|objection|closing|lead|lost", "action": "none|lead|stop|handoff", "name": "", "phone": "", "business": "", "need": "", "current_tool": "", "offer": "", "objection": "", "note": ""}
- readiness (0-100) — готовность купить: 0-20 интересуется; 30-50 рассказал бизнес и боль; 60-75 обсуждает конкретную услугу/цену/сроки, спрашивает «как начать», согласен на консультацию; 80-100 дал телефон / готов платить / просит договор.
- action="lead" — дал телефон или явно согласился на звонок/покупку.
- name, phone, business, need, current_tool, offer, objection — заполняй, когда узнал/изменилось (иначе ""). offer — что ты предложил.
- note — 1 короткая фраза на русском: что сейчас происходит в диалоге (для менеджера).

ПРИМЕРЫ (стиль)
Клиент (первое сообщение): «Salom! Menga «CRM tizim» ($990 dan) qiziq. Batafsil ma'lumot bera olasizmi?»
messages: ["Assalomu alaykum!", "Ishlaringiz yaxshimi?", "CRM qaysi biznesingiz uchun kerak?"]
Клиент: «макарон бизнеси» → ["Тушундим, макарон ишлаб чиқарасизми ёки сотасизми?"]
Клиент: «блакнот ишлатамиз» (бизнес уже известен) → ["Хўп, демак ҳамма мижоз дафтарда.", "Энг кўп қаерда қийналасиз — буюртмаларни йўқотишдами ёки қарзларни кузатишдами?"]
Клиент: «1c» → ["Tushundim, 1C bor.", "1C'da nima yetishmayapti — mijozlar bilan ishlashmi?"]
Клиент: «Сколько стоит бот?» (первое сообщение) → ["Здравствуйте!", "Как ваши дела?", "Бот для какого бизнеса нужен?"]
Клиент: «дорого» → ["Понимаю. Можно начать с ИИ-агента по подписке — $99 в месяц.", "Попробуем на нём?"]
Клиент: «ты бот?» → ["Да, я ИИ-помощник AI Business 🙂", "Если удобнее — подключу живого менеджера."]
Клиент: «+998901234567» → ["Rahmat! Menejerimiz tez orada qo'ng'iroq qiladi.", "Qaysi vaqt qulay?"]

БАЗА
""" + KNOWLEDGE

FOLLOWUP_INSTR = """Клиент не ответил на твоё последнее сообщение. Это напоминание {n} из {total}.
Напиши ОДНО очень короткое сообщение (до 12 слов) на языке и алфавите клиента, как живой менеджер.
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
    for attempt in range(2):
        try:
            DB.run("INSERT INTO demo_bot_state (k, v, updated) VALUES (:k, :v, now()) "
                   "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, updated = now()", k=k, v=json.dumps(v, ensure_ascii=False))
            return True
        except Exception as e:
            print("DB write error:", e)
            db_connect()
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
            print("Loaded chats from DB:", len(STATE["chats"]))
            return
        except Exception as e:
            print("DB load error:", e)
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            STATE = json.load(f)
        STATE.setdefault("chats", {})
        STATE.setdefault("owners", {})
    except FileNotFoundError:
        pass
    except Exception as e:
        print("State load error:", e)


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


def save_file():
    with LOCK:
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(STATE, f, ensure_ascii=False)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            print("State save error:", e)


def chat_state(key):
    with LOCK:
        c = STATE["chats"].get(key)
        if c is None:
            c = {"history": [], "last_client": 0, "followups": 0, "status": "active", "paused_until": 0,
                 "bc_id": None, "chat_id": None, "name": "", "username": "", "facts": {},
                 "readiness": 0, "hot_sent": False, "lead_sent": False, "script": ""}
            STATE["chats"][key] = c
        c.setdefault("facts", {})
        c.setdefault("readiness", 0)
        c.setdefault("hot_sent", False)
        c.setdefault("script", "")
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
    """Odamdek: har bir xabardan oldin 'yozmoqda...' va pauza"""
    for p in parts:
        if TYPING_DELAY:
            typing(chat_id, bc_id)
            time.sleep(min(0.8 + len(p) / 30.0, 5.0))
        send_msg(chat_id, p, bc_id)


def claude(system, messages, max_tokens=500, model=None):
    body = json.dumps({
        "model": model or CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }).encode()
    for attempt in range(3):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", ANTHROPIC_KEY)
        req.add_header("anthropic-version", "2023-06-01")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read())
                return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text").strip()
        except Exception as e:
            print("Claude error:", e)
            time.sleep(2 * (attempt + 1))
    return ""


def detect_business(text):
    biz_list = "\n".join([f"{b[1]} = {b[0]}" for b in BUSINESSES])
    prompt = f'Foydalanuvchi: "{text}"\nBiznes kodini toping:\n{biz_list}\nFaqat kod yozing.'
    code = claude("", [{"role": "user", "content": prompt}], max_tokens=20, model=DETECT_MODEL).lower()
    valid = [b[1] for b in BUSINESSES]
    return code if code in valid else None


def is_from_site(text):
    """Saytdagi demo tugmasidan kelgan xabar"""
    return "uchun AI agent demosini ko'rishni xohlayman" in text


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
# Til / alifbo
# ==========================================================================
KEEP_LATIN = {"crm", "erp", "ai", "api", "1c", "1с", "telegram", "instagram", "excel", "ios", "android", "app", "store",
              "google", "play", "whatsapp", "businessai", "uz", "it", "sms", "pdf", "online", "ok"}
UZ_CYR_LETTERS = set("ўқғҳЎҚҒҲ")
UZ_CYR_WORDS = re.compile(r"(?i)(?<![а-яёўқғҳ])(борми|йўқ|йук|керак|қанча|канча|нархи|салом|ассалому|рахмат|раҳмат|бизнес[иа]м?|қилиш|қилса|бўлади|булади|мумкинми|иложи|сизлар|сизларда|менга|нима|қандай|кандай|канака|бор|ха|хоп|хўп|яхши|кечирасиз|ишлатамиз|ишлаб|сотамиз|керакми|йўқми|қиламиз|биз|бизда|бизни|учун|билан|ҳам|хам|эмас|лекин|ва|ёки)(?![а-яёўқғҳ])")
UZ_SUFFIX = re.compile(r"(ми|лар|ларни|ларга|ларда|миз|сиз|ган|моқчи|мокчи|япти|ябди|ади|ини|нинг|дан|чи|имиз|ингиз|амиз|аймиз)$")
RU_SUFFIX = re.compile(r"(ость|ться|тся|ешь|ете|ого|ому|ыми|ией|ание|ение|ый|ий|ая|ое|ые|ует|ают|ить|ать)$")
RU_WORDS = re.compile(r"(?i)(?<![а-яё])(сколько|стоит|можно|нужно|нужен|нужна|здравствуйте|привет|спасибо|хочу|какой|какая|есть|цена|это|как|что|мне|у нас|мы|не|да|нет|для|или|вы|вас|пожалуйста)(?![а-яё])")


def classify_script(text):
    """'uz_cyr' | 'ru' | 'uz_lat' | '' (aniqlab bo'lmadi)"""
    words = re.findall(r"[A-Za-zʻ'’\x60]+|[\u0400-\u04ff]+", text)
    words = [w for w in words if w.lower().strip("'’\x60ʻ") not in KEEP_LATIN]
    cyr = sum(len(w) for w in words if re.match(r"[\u0400-\u04ff]", w))
    lat = sum(len(w) for w in words if re.match(r"[A-Za-z]", w))
    if cyr + lat < 3:
        return ""
    if cyr > lat:
        low = text.lower()
        cw = re.findall(r"[\u0400-\u04ff]+", low)
        uz_score = len(UZ_CYR_WORDS.findall(low)) + sum(1 for w in cw if UZ_SUFFIX.search(w))
        ru_score = len(RU_WORDS.findall(low)) + sum(1 for w in cw if RU_SUFFIX.search(w))
        if any(ch in UZ_CYR_LETTERS for ch in text) or uz_score > ru_score:
            return "uz_cyr"
        return "ru"
    return "uz_lat"


def client_script(c):
    """Oxirgi aniq yozilgan mijoz xabari bo'yicha"""
    for h in reversed(c["history"]):
        if h["r"] == "u" and not h["t"].startswith("["):
            s = classify_script(h["t"])
            if s:
                return s
    return c.get("script") or "uz_lat"


SCRIPT_HINT = {
    "uz_cyr": "АЛФАВИТ: клиент пишет по-узбекски КИРИЛЛИЦЕЙ. Весь ответ — по-узбекски кириллицей (ў, қ, ғ, ҳ). Ни одного узбекского слова латиницей.",
    "uz_lat": "АЛФАВИТ: клиент пишет по-узбекски ЛАТИНИЦЕЙ. Весь ответ — по-узбекски латиницей (o', g', sh, ch). Ни одного слова кириллицей.",
    "ru": "АЛФАВИТ: клиент пишет ПО-РУССКИ. Весь ответ — по-русски.",
}

L2C = [("o'", "ў"), ("g'", "ғ"), ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ye", "е"), ("e", "е"),
       ("a", "а"), ("b", "б"), ("d", "д"), ("f", "ф"), ("g", "г"), ("h", "ҳ"), ("i", "и"), ("j", "ж"), ("k", "к"),
       ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("q", "қ"), ("r", "р"), ("s", "с"), ("t", "т"),
       ("u", "у"), ("v", "в"), ("x", "х"), ("y", "й"), ("z", "з"), ("c", "с"), ("w", "в"), ("'", "ъ")]
C2L = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k",
       "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
       "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu",
       "я": "ya", "ё": "yo", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h", "е": "e"}


def _case(src, dst):
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def lat2cyr_word(w):
    lw = w.lower().replace("ʻ", "'").replace("’", "'").replace("\x60", "'")
    out, i = "", 0
    while i < len(lw):
        if i == 0 and lw[0] == "e":
            out += "э"; i += 1; continue
        for a, b in L2C:
            if lw.startswith(a, i):
                out += b; i += len(a); break
        else:
            out += lw[i]; i += 1
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


def fix_script(text, script):
    """Aralash alifboni tuzatish: uz_cyr da lotin so'zlarni kirillga, uz_lat da kirill so'zlarni lotinga"""
    if script == "uz_cyr":
        def rep(m):
            w = m.group(0)
            if w.lower().strip("'") in KEEP_LATIN or (w.isupper() and len(w) <= 5):
                return w
            return lat2cyr_word(w)
        return re.sub(r"(?<![@/\w.])[A-Za-z][A-Za-zʻ'’\x60]*", rep, text)
    if script == "uz_lat":
        return re.sub(r"[\u0400-\u04ff]+", lambda m: cyr2lat_word(m.group(0)), text)
    return text

# ==========================================================================
# Javobni tekshirish (qo'riqchilar)
# ==========================================================================
JUNK_RE = re.compile(r"[\u2e80-\u9fff\uac00-\ud7af\u3040-\u30ff\uff00-\uffef\u0600-\u06ff]")
ALLOWED_NUMS = {"290", "590", "1090", "990", "1990", "4490", "99", "1490", "24", "7", "22", "998", "93", "890", "02", "1"}
BANNED_PHRASES = re.compile(r"(?i)(albatta!|juda yaxshi savol|qisqa qilib|отличный вопрос|рад помочь|альбатта!)\s*")


def clean_text(t):
    t = JUNK_RE.sub("", t)
    t = t.replace("**", "").replace("__", "").replace("##", "")
    t = re.sub(r"^\s*[-•✅]\s*", "", t, flags=re.M)
    t = BANNED_PHRASES.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    return t


def bad_numbers(text, history):
    allowed = set(ALLOWED_NUMS)
    for h in history:
        if h["r"] == "u":
            allowed.update(re.findall(r"\d+", h["t"]))
    found = re.findall(r"\d+", re.sub(r"\+?998[\d\s\-()]{9,}", "", text))
    return [n for n in found if n not in allowed]


def norm(s):
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


def is_repeat(msg, history, thr=0.72):
    m = norm(msg)
    if len(m) < 12:
        return False
    for h in history:
        if h["r"] == "a" and difflib.SequenceMatcher(None, m, norm(h["t"])).ratio() >= thr:
            return True
    return False


def parse_json(raw):
    try:
        a, b = raw.index("{"), raw.rindex("}")
        return json.loads(raw[a:b + 1])
    except Exception:
        return None


def drop_sentences_with(text, nums):
    parts = re.split(r"(?<=[.!?])\s+", text)
    keep = [p for p in parts if not any(re.search(r"(?<!\d)" + n + r"(?!\d)", p) for n in nums)]
    return " ".join(keep).strip()


def facts_block(c):
    f = c.get("facts", {})
    labels = [("business", "Бизнес"), ("need", "Потребность"), ("current_tool", "Сейчас использует"),
              ("offer", "Ты уже предложил"), ("objection", "Возражение"), ("name", "Имя"), ("phone", "Телефон")]
    lines = [f"- {lab}: {f[k]}" for k, lab in labels if f.get(k)]
    asked = [h["t"] for h in c["history"] if h["r"] == "a" and "?" in h["t"]][-6:]
    out = "ЧТО УЖЕ ИЗВЕСТНО О КЛИЕНТЕ (не переспрашивай):\n" + ("\n".join(lines) if lines else "- пока ничего")
    out += f"\n- Готовность: {c.get('readiness', 0)}%"
    if asked:
        out += "\nТвои прошлые вопросы (НЕ повторяй их и их смысл):\n" + "\n".join("- " + q for q in asked)
    return out


def generate_reply(c, script):
    first = not any(h["r"] == "a" for h in c["history"])
    msgs = build_messages(c["history"])
    if not msgs:
        return None
    mode = ("ЭТО ПЕРВЫЙ ОТВЕТ В ДИАЛОГЕ: ровно 3 сообщения — приветствие; вопрос как дела; лёгкое уточнение его вопроса."
            if first else "Диалог уже идёт: НЕ здоровайся и не спрашивай про дела. 1-2 коротких сообщения.")
    system = SYSTEM_PROMPT + "\n\n" + SCRIPT_HINT[script] + "\n\n" + facts_block(c) + "\n\n" + mode
    data, feedback, best = None, "", None
    for attempt in range(2):
        convo = msgs if not feedback else msgs + [{"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                                                  {"role": "user", "content": "[СИСТЕМА] " + feedback}]
        if convo[-1]["role"] == "assistant":
            convo = convo[:-1]
        raw = claude(system, convo, max_tokens=500)
        if not raw:
            return None
        d = parse_json(raw)
        if d is None:
            d = {"messages": [p for p in re.split(r"\n\s*\n", raw) if p.strip()], "readiness": c.get("readiness", 0)}
        out = [clean_text(fix_script(str(m), script)) for m in (d.get("messages") or []) if str(m).strip()]
        out = [m for m in out if m]
        d["messages"] = out
        problems = []
        nums = sorted({n for m in out for n in bad_numbers(m, c["history"])})
        if nums:
            problems.append("Убери выдуманные числа " + ", ".join(nums) + " — их нет в базе.")
        reps = [m for m in out if is_repeat(m, c["history"])]
        if reps:
            problems.append("Ты повторяешь уже сказанное: «" + reps[0] + "». Скажи по-другому и двигай разговор дальше.")
        if sum(len(m) for m in out) > MAX_REPLY_CHARS or any(len(m) > MAX_MSG_CHARS for m in out):
            problems.append("Слишком длинно. Каждое сообщение до 15 слов, всего 1-2 сообщения.")
        if sum(m.count("?") for m in out) > (2 if first else 1):
            problems.append("Только один вопрос в ответе.")
        if first and len(out) < 2:
            problems.append("Первый ответ — 3 коротких сообщения: приветствие, как дела, уточнение.")
        if best is None or len(problems) < best[0]:
            best = (len(problems), d)
        data = d
        if not problems or attempt == 1:
            break
        feedback = " ".join(problems) + " Верни исправленный JSON."
    data = best[1]
    # oxirgi himoya
    out = data["messages"]
    nums = sorted({n for m in out for n in bad_numbers(m, c["history"])})
    if nums:
        out = [drop_sentences_with(m, nums) for m in out]
    out = [m for m in out if m and not is_repeat(m, c["history"], 0.9)]
    out = out[:3] if first else out[:2]
    data["messages"] = out
    return data


# ==========================================================================
# Hisobotlar
# ==========================================================================
def report_target(c):
    return REPORT_CHAT_ID or STATE["owners"].get(c.get("bc_id") or "", "")


def send_report(c, title):
    target = report_target(c)
    if not target:
        print("Report skipped (no target):", title)
        return
    f = c.get("facts", {})
    who = c.get("name") or "-"
    if c.get("username"):
        who += " (@" + c["username"] + ")"
    lines = [title, "",
             f"Клиент: {who}",
             f"Ссылка: tg://user?id={c.get('chat_id')}",
             f"Готовность купить: {c.get('readiness', 0)}%"]
    for k, lab in [("phone", "Телефон"), ("business", "Бизнес"), ("need", "Потребность"),
                   ("current_tool", "Сейчас использует"), ("offer", "Что предложили"),
                   ("objection", "Возражения"), ("note", "Как идёт диалог")]:
        if f.get(k):
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
    if TYPING_DELAY:
        typing(c["chat_id"], c["bc_id"])
    d = generate_reply(c, script)
    if not d:
        return
    out = d.get("messages") or []
    if out:
        send_human(c["chat_id"], out, c["bc_id"])
        with LOCK:
            for m in out:
                c["history"].append({"r": "a", "t": m, "ts": time.time()})
    with LOCK:
        for k in ("name", "phone", "business", "need", "current_tool", "offer", "objection", "note"):
            v = str(d.get(k) or "").strip()
            if v:
                c["facts"][k] = v[:200]
        try:
            c["readiness"] = max(0, min(100, int(d.get("readiness", c["readiness"]))))
        except Exception:
            pass
    action = str(d.get("action") or "none")
    has_phone = bool(c["facts"].get("phone")) or bool(re.search(r"\+?998[\d\s\-()]{9,}", " ".join(h["t"] for h in c["history"] if h["r"] == "u")))
    if (action == "lead" or has_phone) and not c.get("lead_sent"):
        c["lead_sent"] = True
        c["hot_sent"] = True
        c["status"] = "lead"
        send_report(c, "🔥 ЛИД: клиент оставил контакт / согласился")
    elif c["readiness"] >= HOT_THRESHOLD and not c.get("hot_sent"):
        c["hot_sent"] = True
        send_report(c, "🌶 ГОРЯЧИЙ КЛИЕНТ — пора подключаться")
    if action == "stop":
        c["status"] = "stopped"
    elif action == "handoff":
        c["status"] = "handoff"
        send_report(c, "🙋 Клиент просит живого менеджера")


def on_client_message(chat_id, text, bc_id, sender):
    key = f"{bc_id or 'direct'}:{chat_id}"
    with chat_lock(key):
        c = chat_state(key)
        with LOCK:
            c["chat_id"] = chat_id
            c["bc_id"] = bc_id
            nm = " ".join(x for x in [sender.get("first_name"), sender.get("last_name")] if x)
            if nm:
                c["name"] = nm
            if sender.get("username"):
                c["username"] = sender["username"]
            c["history"].append({"r": "u", "t": text, "ts": time.time()})
            c["history"] = c["history"][-MAX_HISTORY * 2:]
            c["last_client"] = time.time()
            c["followups"] = 0
            if c["status"] == "stopped":
                c["status"] = "active"
        if c["paused_until"] > time.time():
            save_chat(key)
            return

        if is_from_site(text) and not any(h["r"] == "a" for h in c["history"]):
            biz_key = detect_business(text)
            if biz_key:
                biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
                link = DEMO_URL + "?b=" + biz_key
                demo = f"{biz_name} uchun AI agent demosi:\n\n{link}"
                send_msg(chat_id, demo, bc_id)
                with LOCK:
                    c["history"].append({"r": "a", "t": demo, "ts": time.time()})
                    c["facts"].setdefault("business", biz_name)
                save_chat(key)
                return

        if AI_REPLIES and c["status"] != "handoff":
            ai_reply(key)
        save_chat(key)


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
        system = (SYSTEM_PROMPT + "\n\n" + SCRIPT_HINT[script] + "\n\n" + facts_block(c)
                  + "\n\n" + FOLLOWUP_INSTR.format(n=n, total=total, stage=stage))
        msgs = build_messages(c["history"])
        msgs.append({"role": "user", "content": "[СИСТЕМА] Напиши напоминание."})
        merged = []
        for m in msgs:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(m)
        text = ""
        for attempt in range(2):
            raw = claude(system, merged, max_tokens=150)
            d = parse_json(raw) if raw.strip().startswith("{") else None
            if d and d.get("messages"):
                raw = " ".join(str(x) for x in d["messages"])
            t = clean_text(fix_script(raw.strip().strip('"«»'), script))
            if t and not bad_numbers(t, c["history"]) and not is_repeat(t, c["history"], 0.6) and len(t) <= MAX_MSG_CHARS:
                text = t
                break
        with LOCK:
            c["followups"] = n
        if text:
            send_human(c["chat_id"], [text], c["bc_id"])
            with LOCK:
                c["history"].append({"r": "a", "t": text, "ts": time.time(), "f": n})
        save_chat(key)


def scheduler():
    while True:
        try:
            now = time.time()
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
                text = "[клиент отправил голосовое — прочитать нельзя; вежливо попроси написать текстом]"
            elif msg.get("photo") or msg.get("document") or msg.get("video"):
                text = "[клиент отправил файл/фото без подписи]"
            elif msg.get("contact"):
                ct = msg["contact"]
                text = f"Мой контакт: {ct.get('first_name', '')} {ct.get('phone_number', '')}"
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
        if chat.get("type") == "private" and text:
            on_client_message(chat_id, text, None, msg.get("from", {}))
        return

    if "callback_query" in update:
        tg("answerCallbackQuery", {"callback_query_id": update["callback_query"]["id"]})


class ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
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
        self.send_response(200)
        self.end_headers()
        me = tg("getMe", {})
        info = f"Bot: @{me.get('result', {}).get('username', '?')}\n"
        info += f"can_connect_to_business: {me.get('result', {}).get('can_connect_to_business', False)}\n"
        with LOCK:
            info += f"chats: {len(STATE['chats'])}\nmemory: {'postgres' if DB is not None else 'file'}\n"
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
    print("Bot running on port", port, "| memory:", "postgres" if DB is not None else "file")
    ThreadingServer(("0.0.0.0", port), Handler).serve_forever()
