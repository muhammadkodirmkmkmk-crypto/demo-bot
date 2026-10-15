"""
AI Business UZ — sotuvchi AI agent (Telegram Business).

* 24/7 mijozlarga o'zbek yoki rus tilida javob beradi (mijoz qaysi tilda yozsa).
* Xizmatlar va narxlar haqida batafsil gapiradi, dialogni sotuvgacha olib boradi.
* Mijoz javob bermay qolsa — 24 soatlik oyna ichida 3 marta muloyim "dojim" xabari.
* Mijoz telefon / rozilik bersa — egasiga (biznes akkaunt egasiga) lid haqida xabar.
* Ega chatga o'zi yozsa — bot shu chatda HUMAN_PAUSE_HOURS soat jim turadi.
* Saytdagi "demo" tugmasidan kelgan xabarlarga avvalgidek demo havola yuboriladi.

Faqat standart kutubxona ishlatiladi.
"""
import os
import re
import json
import time
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEMO_URL = os.environ.get("DEMO_URL", "https://sayt-production-f9ed.up.railway.app/demo")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
DETECT_MODEL = os.environ.get("DETECT_MODEL", "claude-haiku-4-5-20251001")
# Lid haqida xabar qayerga ketadi (bo'sh bo'lsa — biznes akkaunt egasiga)
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
# Bot javob beradimi (o'chirish uchun AI_REPLIES=0)
AI_REPLIES = os.environ.get("AI_REPLIES", "1") != "0"
HUMAN_PAUSE_HOURS = float(os.environ.get("HUMAN_PAUSE_HOURS", "12"))
# Dojim xabarlari: oxirgi mijoz xabaridan necha daqiqa keyin
FOLLOWUP_MINUTES = [int(x) for x in os.environ.get("FOLLOWUP_MINUTES", "20,180,1260").split(",") if x.strip()]
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
TZ = timezone(timedelta(hours=5))  # Toshkent
QUIET_FROM, QUIET_TO = 23, 9      # tunda dojim yubormaymiz
TG_WINDOW = 23.5 * 3600            # Telegram: biznes bot faqat 24 soat ichida faol chatga yozadi
MAX_HISTORY = 40

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

# --------------------------------------------------------------------------
# Bilim bazasi va sotuv qoidalari
# --------------------------------------------------------------------------
KNOWLEDGE = """
KOMPANIYA: AI Business UZ (businessai.uz), Toshkent. IT va AI yechimlar agentligi.
22+ biznes biz bilan ishlaydi: ishlab chiqarish zavodlari, klinikalar, o'quv markazlari va boshqalar.
Aloqa: Telegram @businessaiuz, telefon +998 93 890 02 02, sayt https://businessai.uz
Konsultatsiya BEPUL. Har bir xizmatga 24/7 texnik yordam kiradi.

XIZMATLAR VA NARXLAR (boshlang'ich narxlar, aniq summa konsultatsiyada kelishiladi):
1) Saytlar (animatsion, tez, mobilga moslangan, konversiyaga yo'naltirilgan):
   - Bir sahifali landing — $290 dan (odatda bir necha kunda tayyor)
   - O'rta murakkablikdagi sayt — $590 dan
   - Korporativ murakkab sayt — $1090 dan
2) CRM tizim — $990 dan. Noldan, aynan mijozning savdo jarayoniga moslab: mijozlar va bitimlar bazasi,
   voronka va vazifalar, Telegram / AI integratsiya. Shablon emas, ortiqcha litsenziya to'lovlari yo'q.
3) ERP tizim — $1990 dan. Ombor, moliya, ishlab chiqarish, xodimlar, real vaqt hisobotlari — yagona tizimda.
4) Mobil ilova (iOS va Android) — $4490 dan. UX/UI dizayn, backend va admin panel, App Store / Google Play'ga joylash.
5) AI agent (xodim o'rniga ishlaydi): Telegram, Instagram va saytda mijozlarga 24/7 javob beradi,
   buyurtma oladi, yozib qo'yadi, lidlarni saralaydi, biznesning bilim bazasi asosida o'qitiladi, CRM bilan integratsiya.
   - Telegram uchun AI agent obunasi — $99/oy: biz yaratamiz, boshqaramiz, yangilaymiz, oylik hisobot, istalgan vaqt bekor qilish.
   - To'liq xarid — $1490 bir marta: agent, kod va sozlamalar mijozning mulki; keyin faqat AI model (API) va server xarajati.
   - Siz hozir aynan shunday AI agent bilan gaplashyapsiz — bu eng yaxshi jonli demo.

ISH JARAYONI: 1) Murojaat (bepul konsultatsiya) 2) Tahlil — jarayonlarni o'rganamiz 3) Yaratish — kelishilgan muddatda
4) Joriy qilish, kuzatish va doimiy yaxshilash.
Muddatlar va aniq narx loyiha hajmiga bog'liq — konsultatsiyada aytiladi.
"""

SYSTEM_PROMPT = """Sen — AI Business UZ kompaniyasining Telegramdagi sotuv menejerisan (AI agent).
Mijozlar @businessaiuz akkauntiga yozadi, sen kompaniya nomidan javob berasan.

TIL: mijoz qaysi tilda yozsa (o'zbek lotin / o'zbek kirill / rus), aynan shu tilda javob ber.
Aralash bo'lsa — mijozning oxirgi xabari tilida.

USLUB — ENG MUHIM QOIDA: oddiy odam Telegramda qanday yozsa, shunday yoz.
- Salomlashish faqat suhbat boshida, har xabarda emas.
- Juda qisqa: 1-2 jumla, ko'pi bilan ~25 so'z. Uzun tushuntirish, ro'yxat, "✅" punktlar, sarlavhalar YO'Q.
- Savolga to'g'ridan-to'g'ri javob ber. Narx so'rasa — narxni ayt va bitta qisqa savol ber. Hamma narsani birdaniga aytma.
- "Qisqa qilib", "Juda yaxshi savol", "Albatta!" kabi robotcha iboralar ishlatma. Reklama matnidek yozma.
- Jonli so'zlashuv tili: "Assalomu alaykum", "Ha, bor", "Tushundim", "Здравствуйте", "Да, конечно", "Понял".
- Emoji — juda kam (ko'pi bilan bitta, ko'pincha umuman yo'q). Markdown (**, ##) ishlatma.
- Har qanday savolga (hatto mavzudan tashqari bo'lsa ham) odamdek tabiiy javob ber, keyin kerak bo'lsa yumshoq qilib xizmatlarga qayt.
- Fikr ikki qismdan iborat bo'lsa, ularni bo'sh qator bilan ajrat — ular alohida xabar bo'lib ketadi (ko'pi bilan 2 qism).

MISOLLAR (uslub uchun):
Mijoz: "Salom, CRM qancha turadi?"
Sen: "Assalomu alaykum! CRM $990 dan boshlanadi, aniq narx jarayonlaringizga bog'liq. Qanday biznesingiz bor?"
Mijoz: "Сколько стоит бот?"
Sen: "Здравствуйте! Telegram-бот с ИИ — $99 в месяц, либо выкуп за $1490. Для какого бизнеса нужен?"
Mijoz: "Qayerdasizlar?"
Sen: "Toshkentdamiz. Lekin hammasini onlayn ham qilsa bo'ladi — sizga qaysi biri qulay?"
Mijoz: "Бот это или человек?"
Sen: "Я ИИ-ассистент AI Business 🙂 Если нужно, подключу живого менеджера."

MAQSAD — dialogni natijaga olib borish:
1. Salomlash, mijozning biznesi va muammosini bil (qanday biznes, hozir nima qiyin, nimani xohlaydi).
2. Ehtiyojga mos xizmatni tavsiya qil, narx va foydasini aniq tushuntir (pul/vaqt tejash, yo'qotilgan mijozlar).
3. E'tirozlarga ishonchli javob ber (qimmat → foyda va $99/oy obuna variantini ko'rsat; "keyinroq" → bepul konsultatsiya
   hech narsaga majburlamasligini ayt; "ishonmayman" → 22+ mijoz, 24/7 yordam, hozir u bilan gaplashayotgan agentning o'zi demo).
4. Har doim aniq keyingi qadamni taklif qil: bepul konsultatsiya (qo'ng'iroq yoki uchrashuv) uchun
   ism va telefon raqamini so'ra, qulay vaqtni kelish.
5. Telefon raqami / aniq rozilik olganingdan keyin — minnatdorchilik bildir va menejer tez orada bog'lanishini ayt.

QAT'IY QOIDALAR:
- Faqat quyidagi bilim bazasidagi faktlar va narxlarni ishlat. O'ylab topilgan chegirma, aksiya, kafolat, keys,
  muddat yoki raqam aytma. Bilmasang — "aniq javobni menejerimiz konsultatsiyada beradi" de.
- Yolg'on shoshilinchlik yaratma, bosim qilma. Mijoz aniq rad etsa — hurmat bilan xayrlash.
- Mavzudan tashqari savollarga qisqa javob berib, suhbatni xizmatlarga qaytar.
- Agar mijoz "siz botmisiz?" desa — rost ayt: ha, AI agentman, kerak bo'lsa jonli menejerga ulayman.
- Agar mijoz jonli odam bilan gaplashmoqchi bo'lsa, shikoyat qilsa yoki murakkab texnik savol bersa — menejer ulanishini ayt va [[HANDOFF]] qo'sh.

XIZMAT BELGILARI (javobning OXIRIDA, alohida qatorda; mijoz ularni ko'rmaydi):
- Mijoz telefon raqamini bersa yoki konsultatsiya/xaridga aniq rozi bo'lsa:
  [[LEAD|ism|telefon|qiziqqan xizmat|biznesi va kelishuv haqida 1 jumla]]  (noma'lum maydonga - yoz)
- Mijoz aniq rad etsa yoki yozmaslikni so'rasa: [[STOP]]
- Jonli menejer kerak bo'lsa: [[HANDOFF]]

BILIM BAZASI:
""" + KNOWLEDGE

FOLLOWUP_PROMPT = """Mijoz oxirgi xabaringga javob bermadi. Bu {n}-eslatma ({total} tadan).
Yuqoridagi suhbatni hisobga olib, mijozga BITTA juda qisqa (1 jumla, ~15 so'z) muloyim xabar yoz — xuddi jonli menejer
"suhbatni davom ettirish" uchun yozganidek. Mijozning tilida yoz.
{stage}
Takrorlanma, oldingi eslatmalardan farqli bo'lsin. Bosim, yolg'on shoshilinchlik va o'ylab topilgan aksiyalar yo'q.
Faqat xabar matnini yoz, hech qanday izoh va belgilarsiz."""

FOLLOWUP_STAGES = [
    "Bosqich: yengil eslatma — u to'xtagan joyga qaytib, oddiy savol bilan suhbatni davom ettir.",
    "Bosqich: qiymat — mijozning biznesiga mos aniq foydani (bilim bazasidagi faktlar asosida) eslatib, bepul konsultatsiyani taklif qil.",
    "Bosqich: oxirgi muloyim xabar — bu oxirgi eslatma ekanini bosimsiz ayt, qaror mijozda, xohlasa qachon bo'lsa ham yozishi mumkinligini va telefon +998 93 890 02 02 ni qoldir.",
]

# --------------------------------------------------------------------------
# Holat (state)
# --------------------------------------------------------------------------
LOCK = threading.RLock()
CHAT_LOCKS = {}
STATE = {"chats": {}, "owners": {}}


def load_state():
    global STATE
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            STATE = json.load(f)
        STATE.setdefault("chats", {})
        STATE.setdefault("owners", {})
    except FileNotFoundError:
        pass
    except Exception as e:
        print("State load error:", e)


def save_state():
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
            c = {"history": [], "last_client": 0, "followups": 0, "status": "active",
                 "paused_until": 0, "bc_id": None, "chat_id": None, "name": "", "lead_sent": False}
            STATE["chats"][key] = c
        return c


def chat_lock(key):
    with LOCK:
        if key not in CHAT_LOCKS:
            CHAT_LOCKS[key] = threading.Lock()
        return CHAT_LOCKS[key]

# --------------------------------------------------------------------------
# Telegram va Claude
# --------------------------------------------------------------------------
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


TYPING_DELAY = os.environ.get("TYPING_DELAY", "1") != "0"


def send_human(chat_id, text, bc_id=None):
    """Odamdek yuborish: bo'sh qator bo'yicha 2 tagacha xabar, orasida 'yozmoqda...'"""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) > 2:
        parts = [parts[0], "\n\n".join(parts[1:])]
    for i, p in enumerate(parts):
        if TYPING_DELAY:
            typing(chat_id, bc_id)
            time.sleep(min(1.2 + len(p) / 35.0, 5.0))
        send_msg(chat_id, p, bc_id)


def claude(system, messages, max_tokens=600, model=None):
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
    """Claude uchun user/assistant navbatma-navbat bo'lishi kerak"""
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


TAG_RE = re.compile(r"\[\[(LEAD|STOP|HANDOFF)([^\]]*)\]\]")


def parse_tags(text):
    tags = []
    for m in TAG_RE.finditer(text):
        tags.append((m.group(1), [p.strip() for p in m.group(2).split("|")[1:]]))
    clean = TAG_RE.sub("", text).strip()
    clean = clean.replace("**", "")
    return clean, tags

# --------------------------------------------------------------------------
# Egaga xabar (lid / handoff)
# --------------------------------------------------------------------------
def notify_owner(c, title, fields=None):
    target = ADMIN_CHAT_ID or STATE["owners"].get(c.get("bc_id") or "", "")
    if not target:
        print("Owner notify skipped (no target):", title)
        return
    lines = [title, f"Mijoz: {c.get('name') or '-'} (chat {c.get('chat_id')})"]
    if c.get("username"):
        lines.append("Telegram: @" + c["username"])
    if fields:
        labels = ["Ism", "Telefon", "Xizmat", "Izoh"]
        for i, v in enumerate(fields[:4]):
            if v and v != "-":
                lines.append(f"{labels[i]}: {v}")
    last = [h["t"] for h in c["history"] if h["r"] == "u"][-3:]
    if last:
        lines.append("\nOxirgi xabarlar:\n- " + "\n- ".join(t[:300] for t in last))
    send_msg(target, "\n".join(lines))

# --------------------------------------------------------------------------
# Dialog
# --------------------------------------------------------------------------
def ai_reply(key):
    c = chat_state(key)
    msgs = build_messages(c["history"])
    if not msgs:
        return
    typing(c["chat_id"], c["bc_id"])
    raw = claude(SYSTEM_PROMPT, msgs, max_tokens=300)
    if not raw:
        return
    text, tags = parse_tags(raw)
    if text:
        send_human(c["chat_id"], text, c["bc_id"])
        with LOCK:
            c["history"].append({"r": "a", "t": text, "ts": time.time()})
    for name, fields in tags:
        if name == "LEAD":
            with LOCK:
                c["status"] = "lead"
            if not c.get("lead_sent"):
                c["lead_sent"] = True
                notify_owner(c, "🔥 Yangi lid / Новый лид", fields)
        elif name == "STOP":
            with LOCK:
                c["status"] = "stopped"
        elif name == "HANDOFF":
            with LOCK:
                c["status"] = "handoff"
            notify_owner(c, "🙋 Mijoz jonli menejerni so'radi / Клиент просит менеджера")


def on_client_message(chat_id, text, bc_id, sender):
    key = f"{bc_id or 'direct'}:{chat_id}"
    with chat_lock(key):
        c = chat_state(key)
        with LOCK:
            c["chat_id"] = chat_id
            c["bc_id"] = bc_id
            c["name"] = " ".join(x for x in [sender.get("first_name"), sender.get("last_name")] if x)
            c["username"] = sender.get("username", "")
            c["history"].append({"r": "u", "t": text, "ts": time.time()})
            c["history"] = c["history"][-MAX_HISTORY * 2:]
            c["last_client"] = time.time()
            c["followups"] = 0
            if c["status"] == "stopped":
                c["status"] = "active"   # mijoz o'zi qaytdi
        if c["paused_until"] > time.time():
            save_state()
            return

        if is_from_site(text):
            biz_key = detect_business(text)
            if biz_key:
                biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
                link = DEMO_URL + "?b=" + biz_key
                demo = f"{biz_name} uchun AI agent demosi:\n\n{link}"
                send_msg(chat_id, demo, bc_id)
                with LOCK:
                    c["history"].append({"r": "a", "t": demo, "ts": time.time()})
                save_state()
                return

        if AI_REPLIES and c["status"] != "handoff":
            ai_reply(key)
        save_state()


def on_owner_message(chat_id, bc_id):
    """Ega chatga o'zi yozdi — bot jim turadi"""
    key = f"{bc_id}:{chat_id}"
    c = chat_state(key)
    with LOCK:
        c["chat_id"] = chat_id
        c["bc_id"] = bc_id
        c["paused_until"] = time.time() + HUMAN_PAUSE_HOURS * 3600
    save_state()


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
        save_state()
        return user["id"]
    return None

# --------------------------------------------------------------------------
# Dojim (follow-up) rejalashtiruvchisi
# --------------------------------------------------------------------------
def quiet_now(ts):
    h = datetime.fromtimestamp(ts, TZ).hour
    return h >= QUIET_FROM or h < QUIET_TO


def due_followup(c, now):
    if not AI_REPLIES or c["status"] != "active" or not c.get("chat_id"):
        return False
    if c["paused_until"] > now or c["followups"] >= len(FOLLOWUP_MINUTES):
        return False
    h = c["history"]
    if not h or h[-1]["r"] != "a":       # oxirgi so'z bizniki bo'lishi kerak
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
        msgs = build_messages(c["history"])
        msgs.append({"role": "user", "content": "[TIZIM] " + FOLLOWUP_PROMPT.format(n=n, total=total, stage=stage)})
        # ketma-ket user rollarini birlashtirish
        merged = []
        for m in msgs:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(m)
        text, _ = parse_tags(claude(SYSTEM_PROMPT, merged, max_tokens=300))
        with LOCK:
            c["followups"] = n
        if text:
            send_msg(c["chat_id"], text, c["bc_id"])
            with LOCK:
                c["history"].append({"r": "a", "t": text, "ts": time.time(), "f": n})
        save_state()


def scheduler():
    while True:
        try:
            now = time.time()
            with LOCK:
                keys = [k for k, c in STATE["chats"].items() if due_followup(c, now)]
            for k in keys:
                send_followup(k)
            # 7 kundan eski chatlarni tozalash
            with LOCK:
                old = [k for k, c in STATE["chats"].items() if now - max(c.get("last_client", 0), c.get("paused_until", 0)) > 7 * 86400]
                for k in old:
                    del STATE["chats"][k]
            if old:
                save_state()
        except Exception as e:
            print("Scheduler error:", e)
        time.sleep(60)

# --------------------------------------------------------------------------
# Update handler
# --------------------------------------------------------------------------
def handle(update):
    if "business_connection" in update:
        bc = update["business_connection"]
        print("Business connection:", bc.get("id"), "enabled:", bc.get("is_enabled"))
        if bc.get("id") and (bc.get("user") or {}).get("id"):
            with LOCK:
                STATE["owners"][bc["id"]] = bc["user"]["id"]
            save_state()
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
            on_owner_message(chat_id, bc_id)
            return
        if sender.get("is_bot"):
            return
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            if msg.get("voice") or msg.get("audio") or msg.get("video_note"):
                text = "[mijoz ovozli xabar yubordi — matnni o'qib bo'lmaydi; muloyim qilib matn bilan yozishini so'ra]"
            elif msg.get("photo") or msg.get("document") or msg.get("video"):
                text = "[mijoz fayl/rasm yubordi, izohsiz]"
            elif msg.get("contact"):
                ct = msg["contact"]
                text = f"[mijoz kontakt yubordi: {ct.get('first_name', '')} {ct.get('phone_number', '')}]"
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
            info += f"chats: {len(STATE['chats'])}\n"
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
    print("Bot running on port", port)
    ThreadingServer(("0.0.0.0", port), Handler).serve_forever()
