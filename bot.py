import os
import json
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEMO_URL = os.environ.get("DEMO_URL", "https://sayt-production-f9ed.up.railway.app/demo")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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
    ("Boshqa soha",       "boshqa"),
]

BIZ_LIST = "\n".join([f"{b[1]} = {b[0]}" for b in BUSINESSES])

def tg(method, data):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print("TG error:", e)
        return {}

def detect_business(text):
    prompt = f"""Foydalanuvchi quyidagi xabarni yozdi: "{text}"

Quyidagi biznes turlaridan mosini toping va FAQAT kodni yozing:

{BIZ_LIST}

Agar aniqlab bo'lmasa "boshqa" yozing. Faqat kod, boshqa hech narsa."""
    try:
        body = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", ANTHROPIC_KEY)
        req.add_header("anthropic-version", "2023-06-01")
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read())
            code = res["content"][0]["text"].strip().lower()
            valid = [b[1] for b in BUSINESSES]
            return code if code in valid else None
    except Exception as e:
        print("Claude error:", e)
        return None

def send_menu(chat_id, business_connection_id=None):
    keyboard = []
    for i in range(0, len(BUSINESSES), 2):
        row = [{"text": BUSINESSES[i][0], "callback_data": "biz:" + BUSINESSES[i][1]}]
        if i + 1 < len(BUSINESSES):
            row.append({"text": BUSINESSES[i+1][0], "callback_data": "biz:" + BUSINESSES[i+1][1]})
        keyboard.append(row)
    data = {
        "chat_id": chat_id,
        "text": "Biznesingiz turini tanlang:",
        "reply_markup": {"inline_keyboard": keyboard}
    }
    if business_connection_id:
        data["business_connection_id"] = business_connection_id
    tg("sendMessage", data)

def send_link(chat_id, biz_key, biz_name, business_connection_id=None):
    link = DEMO_URL + "?b=" + biz_key
    data = {
        "chat_id": chat_id,
        "text": biz_name + " uchun AI agent demosi:\n\n" + link
    }
    if business_connection_id:
        data["business_connection_id"] = business_connection_id
    tg("sendMessage", data)

def handle(update):
    # Handle business_connection (when user connects bot to TG Business)
    if "business_connection" in update:
        bc = update["business_connection"]
        print("Business connection:", bc)
        return

    # Handle business messages (messages in owner's personal chats)
    if "business_message" in update:
        msg = update["business_message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        bc_id = msg.get("business_connection_id", None)

        if not text:
            return

        tg("sendChatAction", {"chat_id": chat_id, "action": "typing",
                               "business_connection_id": bc_id} if bc_id else {"chat_id": chat_id, "action": "typing"})

        biz_key = detect_business(text)
        if biz_key:
            biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
            send_link(chat_id, biz_key, biz_name, bc_id)
        else:
            send_menu(chat_id, bc_id)
        return

    # Handle regular bot messages
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()

        if not text:
            return

        if text.startswith("/start"):
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": "Assalomu alaykum! Biznesingiz haqida yozing yoki quyidan tanlang:"
            })
            send_menu(chat_id)
            return

        tg("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        biz_key = detect_business(text)
        if biz_key:
            biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
            send_link(chat_id, biz_key, biz_name)
        else:
            tg("sendMessage", {"chat_id": chat_id, "text": "Biznesingiz turini aniqlay olmadim. Quyidan tanlang:"})
            send_menu(chat_id)

    elif "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        msg_id = cb["message"]["message_id"]
        data = cb.get("data", "")
        if data.startswith("biz:"):
            biz_key = data[4:]
            biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
            tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
            tg("editMessageText", {"chat_id": chat_id, "message_id": msg_id, "text": "Tanlandi: " + biz_name})
            send_link(chat_id, biz_key, biz_name)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            update = json.loads(body)
            handle(update)
        except Exception as e:
            print("Error:", e)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot running!")

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    if WEBHOOK_URL:
        # Set webhook with business allowed updates
        result = tg("setWebhook", {
            "url": WEBHOOK_URL,
            "allowed_updates": [
                "message",
                "callback_query",
                "business_connection",
                "business_message",
                "edited_business_message",
                "deleted_business_messages"
            ]
        })
        print("Webhook:", result)
    print("Bot running on port", port)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
