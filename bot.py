import os
import json
import urllib.request
import threading
import time
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
    BIZ_LIST = "\n".join([f"{b[1]} = {b[0]}" for b in BUSINESSES])
    prompt = f"""Foydalanuvchi: "{text}"\nBiznes kodini toping:\n{BIZ_LIST}\nFaqat kod yozing."""
    try:
        body = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST")
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

def send_msg(chat_id, text, bc_id=None):
    data = {"chat_id": chat_id, "text": text}
    if bc_id:
        data["business_connection_id"] = bc_id
    tg("sendMessage", data)

def followup(chat_id, biz_name, bc_id):
    """Send follow-up after 5 minutes"""
    time.sleep(300)
    msg = (
        f"Hurmatli mijoz, siz {biz_name} uchun AI agentni ko'rib chiqdingizmi?\n\n"
        f"Ko'pchilik biznes egalari birinchi marta ko'rib: \"Bu menga kerak emas\" deb o'ylashadi. "
        f"Lekin raqamlar boshqacha gapiradi:\n\n"
        f"✅ 24/7 ishlaydi — siz uxlaganda ham mijozlarga javob beradi\n"
        f"✅ 1 agent = 2-3 menejer ishi\n"
        f"✅ Birinchi oydan o'zini qoplaydi\n\n"
        f"Hozir bepul konsultatsiya oling — 15 daqiqa vaqtingizni olamiz, biznesingizga qanday mos kelishini aniq ko'rsatamiz."
    )
    send_msg(chat_id, msg, bc_id)

def send_link(chat_id, biz_key, biz_name, bc_id=None):
    link = DEMO_URL + "?b=" + biz_key
    send_msg(chat_id, f"{biz_name} uchun AI agent demosi:\n\n{link}", bc_id)
    # Schedule follow-up in background
    t = threading.Thread(target=followup, args=(chat_id, biz_name, bc_id), daemon=True)
    t.start()

def is_from_site(text):
    """Check if message came from site demo button"""
    return "uchun AI agent demosini ko'rishni xohlayman" in text

def handle(update):
    if "business_connection" in update:
        print("Business connected:", update["business_connection"])
        return

    if "business_message" in update:
        msg = update["business_message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        bc_id = msg.get("business_connection_id")

        if not text:
            return

        # Only respond to messages from site
        if not is_from_site(text):
            return

        biz_key = detect_business(text)
        if biz_key:
            biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
            send_link(chat_id, biz_key, biz_name, bc_id)
        return

    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()

        if text.startswith("/start"):
            send_msg(chat_id, "Bot ishlayapti!")
            return

        # Only respond if from site
        if not is_from_site(text):
            return

        biz_key = detect_business(text)
        if biz_key:
            biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")
            send_link(chat_id, biz_key, biz_name)

    elif "callback_query" in update:
        cb = update["callback_query"]
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})

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
        me = tg("getMe", {})
        info = f"Bot: @{me.get('result',{}).get('username','?')}\n"
        info += f"can_connect_to_business: {me.get('result',{}).get('can_connect_to_business', False)}\n"
        self.wfile.write(info.encode())

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
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
    print("Bot running on port", port)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
