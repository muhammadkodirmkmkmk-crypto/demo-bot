import os
import json
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEMO_URL = os.environ.get("DEMO_URL", "https://sayt-production-f9ed.up.railway.app/demo")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

BUSINESSES = [
    ("Internet do'kon",      "internet_dokon"),
    ("Go'zallik saloni",     "gozallik"),
    ("Klinika",               "klinika"),
    ("Restoran / Kafe",       "restoran"),
    ("Fitnes klub",           "fitnes"),
    ("Taom yetkazish",        "taom_yetkazish"),
    ("Rieltorlik",            "rieltor"),
    ("Mehmonxona",            "mehmonxona"),
    ("Online kurslar",        "online_kurs"),
    ("Marketing agentlik",    "marketing"),
    ("Avtoservis",            "avtoservis"),
    ("Yuk tashish",           "yuk_tashish"),
    ("Avtosalon",             "avtosalon"),
    ("IT kompaniya",          "it_kompaniya"),
    ("Roznitsa do'kon",      "roznitsa"),
    ("Til maktabi",           "til_maktabi"),
    ("Bolalar markazi",       "bolalar_markazi"),
    ("Kuryer xizmati",        "kuryer"),
    ("Buxgalteriya",          "buxgalteriya"),
    ("Qurilish",              "qurilish"),
    ("Ulgurji savdo",         "ulgurji"),
    ("Mebel saloni",          "mebel"),
    ("Ombor / Logistika",     "ombor"),
    ("Uy-joy ijarasi",        "ijara"),
    ("Repetitorlik",          "repetitor"),
    ("Konditeriya",           "konditeriya"),
    ("Catering",              "catering"),
    ("Ishlab chiqarish",      "ishlab_chiqarish"),
    ("Yuridik firma",         "yuridik"),
    ("Boshqa soha",           "boshqa"),
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

def send_menu(chat_id):
    keyboard = []
    for i in range(0, len(BUSINESSES), 2):
        row = []
        row.append({"text": BUSINESSES[i][0], "callback_data": "biz:" + BUSINESSES[i][1]})
        if i + 1 < len(BUSINESSES):
            row.append({"text": BUSINESSES[i+1][0], "callback_data": "biz:" + BUSINESSES[i+1][1]})
        keyboard.append(row)
    tg("sendMessage", {
        "chat_id": chat_id,
        "text": "Biznesingiz turini tanlang:",
        "reply_markup": {"inline_keyboard": keyboard}
    })

def send_link(chat_id, biz_key, biz_name):
    link = DEMO_URL + "?b=" + biz_key
    tg("sendMessage", {
        "chat_id": chat_id,
        "text": "Demo tayyor! " + biz_name + " uchun AI agentni sinab koring:\n\n" + link,
    })

def handle(update):
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        tg("sendMessage", {
            "chat_id": chat_id,
            "text": "Assalomu alaykum! Biznesingiz turini tanlang:"
        })
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
            tg("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": "Tanlandi: " + biz_name
            })
            send_link(chat_id, biz_key, biz_name)

webhook_set = False

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
        global webhook_set
        if not webhook_set and WEBHOOK_URL:
            result = tg("setWebhook", {"url": WEBHOOK_URL})
            print("Webhook set:", result)
            webhook_set = True
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    if WEBHOOK_URL:
        result = tg("setWebhook", {"url": WEBHOOK_URL})
        print("Webhook set on startup:", result)
    print("Bot running on port", port)
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
