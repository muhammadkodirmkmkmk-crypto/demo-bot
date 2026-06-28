import os
import json
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEMO_URL = os.environ.get("DEMO_URL", "https://sayt-production-f9ed.up.railway.app/demo")

BUSINESSES = [
    ("Internet do'kon",      "internet_dokon"),
    ("Go'zallik saloni",     "gozallik"),
    ("Klinika",              "klinika"),
    ("Restoran / Kafe",      "restoran"),
    ("Fitnes klub",          "fitnes"),
    ("Taom yetkazish",       "taom_yetkazish"),
    ("Rieltorlik",           "rieltor"),
    ("Mehmonxona",           "mehmonxona"),
    ("Online kurslar",       "online_kurs"),
    ("Marketing agentlik",   "marketing"),
    ("Avtoservis",           "avtoservis"),
    ("Yuk tashish",          "yuk_tashish"),
    ("Avtosalon",            "avtosalon"),
    ("IT kompaniya",         "it_kompaniya"),
    ("Roznitsa do'kon",      "roznitsa"),
    ("Til maktabi",          "til_maktabi"),
    ("Bolalar markazi",      "bolalar_markazi"),
    ("Kuryer xizmati",       "kuryer"),
    ("Buxgalteriya",         "buxgalteriya"),
    ("Qurilish",             "qurilish"),
    ("Ulgurji savdo",        "ulgurji"),
    ("Mebel saloni",         "mebel"),
    ("Ombor / Logistika",    "ombor"),
    ("Uy-joy ijarasi",       "ijara"),
    ("Repetitorlik",         "repetitor"),
    ("Konditeriya",          "konditeriya"),
    ("Catering",             "catering"),
    ("Ishlab chiqarish",     "ishlab_chiqarish"),
    ("Yuridik firma",        "yuridik"),
    ("Boshqa soha",          "boshqa"),
]

def tg(method, data):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"TG error: {e}")
        return {}

def send_business_menu(chat_id):
    # Build inline keyboard 2 columns
    keyboard = []
    for i in range(0, len(BUSINESSES), 2):
        row = []
        row.append({"text": BUSINESSES[i][0], "callback_data": "biz:" + BUSINESSES[i][1]})
        if i + 1 < len(BUSINESSES):
            row.append({"text": BUSINESSES[i+1][0], "callback_data": "biz:" + BUSINESSES[i+1][1]})
        keyboard.append(row)

    tg("sendMessage", {
        "chat_id": chat_id,
        "text": "Biznesingiz turini tanlang 👇",
        "reply_markup": {"inline_keyboard": keyboard}
    })

def send_demo_link(chat_id, biz_key, biz_name):
    link = f"{DEMO_URL}?b={biz_key}"
    tg("sendMessage", {
        "chat_id": chat_id,
        "text": f"✅ *{biz_name}* uchun AI agent demosi tayyor!\n\n👇 Quyidagi havolani bosing:\n{link}\n\n_Demo bilan tanishib chiqing. Savollar bo'lsa yozing!_",
        "parse_mode": "Markdown"
    })

def handle_update(update):
    # Handle /start or any message
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        if text.startswith("/start") or text.lower() in ["salom", "hello", "demo", "/demo"]:
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": "Assalomu alaykum! 👋\n\nSizning biznesingiz uchun *AI agent demosini* ko'rmoqchimisiz?\n\nQuyidan biznesingiz turini tanlang:",
                "parse_mode": "Markdown"
            })
            send_business_menu(chat_id)
        else:
            send_business_menu(chat_id)

    # Handle button click
    elif "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        data = cb.get("data", "")
        msg_id = cb["message"]["message_id"]

        if data.startswith("biz:"):
            biz_key = data[4:]
            biz_name = next((b[0] for b in BUSINESSES if b[1] == biz_key), "Biznes")

            # Answer callback
            tg("answerCallbackQuery", {"callback_query_id": cb["id"]})

            # Edit original message
            tg("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": f"✅ Tanlandi: *{biz_name}*",
                "parse_mode": "Markdown"
            })

            # Send demo link
            send_demo_link(chat_id, biz_key, biz_name)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            update = json.loads(body)
            handle_update(update)
        except Exception as e:
            print(f"Error: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Demo bot is running!")

    def log_message(self, format, *args):
        pass

def set_webhook(port):
    # Webhook will be set via Railway URL
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        result = tg("setWebhook", {"url": webhook_url})
        print(f"Webhook set: {result}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    set_webhook(port)
    print(f"Bot server running on port {port}")
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
