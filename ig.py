"""
Instagram Direct kanali (rasmiy Meta API: "Instagram API with Instagram Login").

Bir nechta mijoz (tenant): har bir biznes o'z Instagram akkauntini /ig sahifasidagi tugma orqali ulaydi.
Mantiq (sotuv, xotira, til, qo'riqchilar, hisobotlar) — bot.py bilan bir xil.

Muhit o'zgaruvchilari:
  IG_APP_ID, IG_APP_SECRET   — Meta App Dashboard > Instagram > API setup with Instagram login
  IG_VERIFY_TOKEN            — webhook uchun istalgan maxfiy so'z (Meta'da ham shu yoziladi)
  PUBLIC_URL                 — https://demo-bot-production-61c7.up.railway.app
  OWN_IG_USERNAME            — o'zimizning akkaunt (AI Business prompti bilan javob beradi), default aibusiness_uz
"""
import os
import json
import time
import hmac
import html
import base64
import hashlib
import secrets
import threading
import urllib.request
import urllib.parse
import urllib.error

core = None   # bot.py moduli (init() orqali beriladi)

IG_APP_ID = os.environ.get("IG_APP_ID", "")
IG_APP_SECRET = os.environ.get("IG_APP_SECRET", "")
IG_VERIFY_TOKEN = os.environ.get("IG_VERIFY_TOKEN", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://demo-bot-production-61c7.up.railway.app").rstrip("/")
API_VER = os.environ.get("IG_API_VERSION", "v25.0")
OWN_IG_USERNAME = os.environ.get("OWN_IG_USERNAME", "aibusiness_uz").lstrip("@").lower()
SCOPES = "instagram_business_basic,instagram_business_manage_messages"

OUR_SENT = {}        # bot yuborgan xabarlar mid -> vaqt (echo'ni ajratish uchun)
PENDING = {}         # (mijoz, matn) -> vaqt: yuborilayotgan xabar (echo API javobidan oldin kelishi mumkin)
PENDING_AUDIO = {}   # mijoz -> vaqt: bot ovoz yuborayotgan payt
OAUTH_STATES = {}    # state -> vaqt
LOCK = threading.Lock()


def init(bot_module):
    global core
    core = bot_module
    core.STATE.setdefault("tenants", {})


def configured():
    return bool(IG_APP_ID and IG_APP_SECRET)

# --------------------------------------------------------------------------
# HTTP yordamchilar
# --------------------------------------------------------------------------
def http(method, url, params=None, data=None, json_body=None, token=None, timeout=20):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = None
    headers = {}
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        print("IG http error:", url.split("?")[0], e)
        return 0, {}


def graph(method, path, **kw):
    return http(method, f"https://graph.instagram.com/{API_VER}/{path.lstrip('/')}", **kw)

# --------------------------------------------------------------------------
# Tenantlar (ulangan Instagram akkauntlar)
# --------------------------------------------------------------------------
def tenants():
    return core.STATE.setdefault("tenants", {})


def save_tenant(t):
    tenants()[t["ig_id"]] = t
    if not core.db_put("tenant:" + t["ig_id"], t):
        core.save_file()


def find_tenant(ref):
    ref = str(ref).lstrip("@").lower()
    for t in tenants().values():
        if t["ig_id"] == ref or (t.get("username") or "").lower() == ref:
            return t
    return None


def is_own(t):
    return (t.get("username") or "").lower() == OWN_IG_USERNAME


TENANT_PROMPT = """Ты — вежливый, тёплый менеджер по продажам компании «{company}». Клиенты пишут в Instagram Direct, ты отвечаешь от имени компании. Пиши как живой, доброжелательный человек. Себе имя не придумывай.

ЯЗЫК ОТВЕТА
- Клиент пишет по-узбекски (латиницей ИЛИ кириллицей) — пиши по-узбекски ЛАТИНИЦЕЙ, грамотно (o', g', sh, ch). В кириллицу программа переведёт сама.
- Клиент пишет по-русски — по-русски. Русские слова в узбекский текст не вставляй.

ТОН И ФОРМАТ
- Всегда «Siz» / «Вы», тепло и уважительно. Без сарказма, давления и ложной срочности.
- Каждое сообщение 4–16 слов, 1–2 сообщения в ответе (первый ответ — 3: приветствие; как дела; лёгкое уточнение вопроса). Максимум один вопрос — в конце.
- Без списков, markdown, рекламных штампов. Отвечай на то, что клиент спросил.
- Не переспрашивай то, что уже известно, не повторяй свои фразы.

ПРОДАЖА
1. Узнай потребность клиента по одному вопросу, потом предложи одно подходящее решение из базы.
2. Цель — получить номер телефона и удобное время звонка (или оформить заказ, если так указано в базе). Если номер уже дан — поблагодари и подтверди.
3. Отказ — вежливо попрощайся (action="stop"). Просит человека или жалуется — action="handoff".
4. «Ты бот?» — честно: ИИ-помощник компании, можешь подключить менеджера.

ЗАПРЕТЫ
- Только факты и цены из БАЗЫ. Ничего не выдумывай: цены, скидки, сроки, гарантии. Не знаешь — «уточню у менеджера».

ФОРМАТ — только один JSON-объект:
{{"messages": ["...", "..."], "readiness": 0, "stage": "greeting|discovery|offer|objection|closing|lead|lost", "action": "none|lead|stop|handoff", "name": "", "phone": "", "business": "", "need": "", "current_tool": "", "budget": "", "offer": "", "objection": "", "call_time": "", "note": ""}}
- readiness 0–100 — готовность купить. action="lead" — дал телефон или согласился на покупку/звонок. note — 1 фраза на русском для менеджера.

БАЗА КОМПАНИИ
{kb}"""


def prompt_for(c):
    ag = c.get("agent") or (core.AGENTS.for_ig_tenant(c.get("tenant")) if c.get("channel") == "ig" else None)
    if ag and core.AGENTS.prompt(ag):
        return core.AGENTS.prompt(ag)
    if c.get("channel") == "ig":
        t = tenants().get(c.get("tenant") or "")
        if t and not is_own(t) and t.get("kb"):
            return TENANT_PROMPT.format(company=t.get("company") or t.get("username") or "", kb=t["kb"])
    return core.SYSTEM_PROMPT

# --------------------------------------------------------------------------
# Yuborish
# --------------------------------------------------------------------------
def send_parts(c, parts):
    t = tenants().get(c.get("tenant") or "")
    if not t or not t.get("token"):
        print("IG send skipped: no token for tenant", c.get("tenant"))
        return
    for p in parts:
        with LOCK:
            PENDING[(str(c["chat_id"]), norm(p[:900]))] = time.time()
        if core.TYPING_DELAY:
            graph("POST", "me/messages", json_body={"recipient": {"id": c["chat_id"]}, "sender_action": "typing_on"},
                  token=t["token"])
            time.sleep(min(0.8 + len(p) / 30.0, 5.0))
        st, res = graph("POST", "me/messages", json_body={"recipient": {"id": c["chat_id"]}, "message": {"text": p[:900]}},
                        token=t["token"])
        if st == 200 and res.get("message_id"):
            with LOCK:
                OUR_SENT[res["message_id"]] = time.time()
                if len(OUR_SENT) > 5000:
                    for k in sorted(OUR_SENT, key=OUR_SENT.get)[:1000]:
                        OUR_SENT.pop(k, None)
        else:
            print("IG send error:", st, json.dumps(res)[:300])

# --------------------------------------------------------------------------
# Webhook
# --------------------------------------------------------------------------
def send_voice(c, audio):
    """Ovozli javob: fayl serverimizda vaqtincha turadi, Instagram uni URL orqali oladi"""
    t = tenants().get(c.get("tenant") or "")
    if not t or not t.get("token"):
        return False
    mid_ = secrets.token_hex(12)
    now = time.time()
    with LOCK:
        for k in [k for k, v in core.MEDIA.items() if now - v[1] > 3600]:
            core.MEDIA.pop(k, None)
        core.MEDIA[mid_] = (audio, now)
        PENDING_AUDIO[str(c["chat_id"])] = now
    st, res = graph("POST", "me/messages", json_body={"recipient": {"id": c["chat_id"]}, "message": {
        "attachment": {"type": "audio", "payload": {"url": f"{PUBLIC_URL}/media/{mid_}.wav"}}}}, token=t["token"])
    if st == 200 and res.get("message_id"):
        with LOCK:
            OUR_SENT[res["message_id"]] = time.time()
        return True
    print("IG voice send error:", st, json.dumps(res)[:300])
    return False


def norm(t):
    return " ".join((t or "").split()).lower()


def variants(t):
    """Tarixdagi matn (lotin) va mijozga yuborilgan ko'rinishi (kirill) — ikkalasi"""
    out = {norm(t)}
    try:
        out.add(norm(core.render(t, "uz_cyr")))
    except Exception:
        pass
    return out


def is_our_echo(recipient, msg, ig_id):
    """Echo botning o'z xabarimi? mid, yuborilayotgan matn yoki yaqindagi bot javobi bo'yicha"""
    if msg.get("mid") in OUR_SENT:
        return True
    text = norm(msg.get("text"))
    if not text:
        kinds = [a.get("type") for a in msg.get("attachments", [])]
        return "audio" in kinds and time.time() - PENDING_AUDIO.get(str(recipient), 0) < 300
    now = time.time()
    with LOCK:
        for k in [k for k, ts in PENDING.items() if now - ts > 600]:
            PENDING.pop(k, None)
        if PENDING.pop((str(recipient), text), None) is not None:
            return True
    c = core.STATE["chats"].get(f"ig:{ig_id}:{recipient}")
    if c:
        for h in c["history"][-12:]:
            if h["r"] == "a" and not h.get("human") and now - h.get("ts", 0) < 900 and text in variants(h["t"]):
                return True
    return False


def repair_echo_pauses():
    """Eski xato: botning o'z xabari 'egasi javob berdi' deb olingan va chat to'xtatilgan — tuzatamiz"""
    fixed = 0
    for key, c in list(core.STATE["chats"].items()):
        if not key.startswith("ig:"):
            continue
        bot_texts = set()
        for h in c["history"]:
            if h["r"] == "a" and not h.get("human"):
                bot_texts |= variants(h["t"])
        bad = [h for h in c["history"] if h.get("human") and norm(h["t"]) in bot_texts]
        if bad:
            c["history"] = [h for h in c["history"] if h not in bad]
            if not any(h.get("human") for h in c["history"]):
                c["paused_until"] = 0
            core.save_chat(key)
            fixed += 1
    if fixed:
        print("IG: repaired echo pauses in", fixed, "chats")
    return fixed


def ig_voice_text(msg):
    """Instagram ovozli xabari -> matn"""
    for a in msg.get("attachments", []):
        if a.get("type") == "audio":
            url = (a.get("payload") or {}).get("url")
            core.CTX.ch = "ig"
            if url and core.STT.configured():
                t = core.STT.transcribe(core.STT.fetch(url), "voice.mp4", "audio/mp4")
                if t:
                    return core.STT.voice_note(t)
            return core.STT.VOICE_FALLBACK
    return ""


def valid_signature(body, header):
    if not IG_APP_SECRET:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(IG_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def profile_name(t, igsid):
    st, res = graph("GET", igsid, params={"fields": "name,username"}, token=t["token"])
    if st == 200:
        return res.get("name") or "", res.get("username") or ""
    return "", ""


def on_webhook(payload):
    if payload.get("object") != "instagram":
        return
    for entry in payload.get("entry", []):
        ig_id = str(entry.get("id"))
        t = tenants().get(ig_id)
        for ev in entry.get("messaging", []):
            msg = ev.get("message")
            if not msg or msg.get("is_deleted"):
                continue
            sender = str((ev.get("sender") or {}).get("id"))
            recipient = str((ev.get("recipient") or {}).get("id"))
            bc = "ig:" + ig_id
            if msg.get("is_echo"):
                if is_our_echo(recipient, msg, ig_id):
                    continue                         # botning o'z xabari
                if t is not None:                    # ega Instagram'dan o'zi javob berdi — bot jim turadi
                    core.on_owner_message(recipient, bc, msg.get("text") or "")
                continue
            if t is None or sender == ig_id:
                print("IG message for unknown tenant", ig_id)
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                kinds = [a.get("type") for a in msg.get("attachments", [])]
                if "audio" in kinds:
                    core.CTX.chat = core.chat_state(f"{bc}:{sender}")
                    text = ig_voice_text(msg)
                elif kinds:
                    text = "[клиент отправил вложение (" + ", ".join(k for k in kinds if k) + ") без подписи]"
                else:
                    continue
            key = f"{bc}:{sender}"
            c = core.chat_state(key)
            first_time = not c.get("channel")
            c["channel"] = "ig"
            c["tenant"] = ig_id
            c["report_chat"] = t.get("report_chat") or core.REPORT_CHAT_ID
            if first_time and t.get("token"):
                name, uname = profile_name(t, sender)
                sender_info = {"first_name": name, "username": uname}
            else:
                sender_info = {}
            key, stamp = core.record_client(sender, text, bc, sender_info)
            if not t.get("enabled", True):
                core.save_chat(key)
                continue
            if not is_own(t) and not t.get("kb"):
                core.save_chat(key)
                notify_admin(f"⚠️ Instagram @{t.get('username')}: пришло сообщение, но база знаний не заполнена — бот молчит.\n"
                             f"Заполните: /ig_kb {t['ig_id']} | Название компании\\nописание, услуги, цены")
                continue
            threading.Thread(target=core.respond, args=(key, stamp), daemon=True).start()


def notify_admin(text):
    if core.REPORT_CHAT_ID:
        core.send_msg(core.REPORT_CHAT_ID, text)

# --------------------------------------------------------------------------
# OAuth: Instagram akkauntni ulash
# --------------------------------------------------------------------------
def redirect_uri():
    return PUBLIC_URL + "/ig/callback"


def connect_url():
    state = secrets.token_urlsafe(16)
    with LOCK:
        OAUTH_STATES[state] = time.time()
    q = urllib.parse.urlencode({"client_id": IG_APP_ID, "redirect_uri": redirect_uri(), "response_type": "code",
                                "scope": SCOPES, "state": state, "enable_fb_login": "false", "force_reauth": "true"})
    return "https://www.instagram.com/oauth/authorize?" + q


def finish_oauth(code):
    code = code.split("#")[0]
    st, res = http("POST", "https://api.instagram.com/oauth/access_token", data={
        "client_id": IG_APP_ID, "client_secret": IG_APP_SECRET, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(), "code": code})
    if isinstance(res.get("data"), list) and res["data"]:
        res = res["data"][0]
    short = res.get("access_token")
    if not short:
        return None, "Не удалось получить токен: " + json.dumps(res)[:300]
    st, ll = http("GET", "https://graph.instagram.com/access_token",
                  params={"grant_type": "ig_exchange_token", "client_secret": IG_APP_SECRET, "access_token": short})
    token = ll.get("access_token") or short
    expires = time.time() + int(ll.get("expires_in") or 3600)
    st, me = graph("GET", "me", params={"fields": "user_id,username,name"}, token=token)
    ig_id = str(me.get("user_id") or me.get("id") or res.get("user_id") or "")
    if not ig_id:
        return None, "Не удалось получить профиль: " + json.dumps(me)[:300]
    st2, sub = graph("POST", "me/subscribed_apps", params={"subscribed_fields": "messages"}, token=token)
    old = tenants().get(ig_id, {})
    t = {"ig_id": ig_id, "username": me.get("username") or old.get("username", ""), "name": me.get("name", ""),
         "token": token, "token_ts": time.time(), "expires_at": expires,
         "kb": old.get("kb", ""), "company": old.get("company", ""),
         "report_chat": old.get("report_chat") or core.REPORT_CHAT_ID,
         "enabled": old.get("enabled", True), "subscribed": bool(sub.get("success")), "connected_at": time.time(),
         "app_user_id": str(res.get("user_id") or "")}
    save_tenant(t)
    notify_admin(f"✅ Instagram подключён: @{t['username']} (id {ig_id})\n"
                 f"Подписка на сообщения: {'да' if t['subscribed'] else 'НЕТ — ' + json.dumps(sub)[:200]}\n"
                 + ("Это наш аккаунт — бот уже отвечает." if is_own(t) else
                    f"Заполните базу знаний: /ig_kb {ig_id} | Название компании\\nуслуги, цены, адрес, график"))
    return t, None


def maintenance():
    """Tokenlarni yangilash (60 kunlik, kamida 24 soatlik bo'lishi kerak)"""
    try:
        repair_echo_pauses()
    except Exception as e:
        print("IG repair error:", e)
    now = time.time()
    for t in list(tenants().values()):
        if not t.get("token"):
            continue
        if now - t.get("token_ts", 0) > 86400 and t.get("expires_at", 0) - now < 20 * 86400:
            st, res = http("GET", "https://graph.instagram.com/refresh_access_token",
                           params={"grant_type": "ig_refresh_token", "access_token": t["token"]})
            if res.get("access_token"):
                t["token"] = res["access_token"]
                t["token_ts"] = now
                t["expires_at"] = now + int(res.get("expires_in") or 5184000)
                save_tenant(t)
            else:
                print("IG token refresh failed:", t.get("username"), json.dumps(res)[:200])
                if t.get("expires_at", 0) - now < 3 * 86400:
                    notify_admin(f"⚠️ Токен Instagram @{t.get('username')} скоро истечёт — переподключите: {PUBLIC_URL}/ig")

# --------------------------------------------------------------------------
# Meta callback'lari: deauthorize va ma'lumotni o'chirish
# --------------------------------------------------------------------------
def parse_signed_request(sr):
    try:
        sig, payload = sr.split(".", 1)
        pad = lambda s: s + "=" * (-len(s) % 4)
        data = json.loads(base64.urlsafe_b64decode(pad(payload)))
        expected = hmac.new(IG_APP_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(base64.urlsafe_b64decode(pad(sig)), expected):
            return None
        return data
    except Exception:
        return None


def delete_user_data(user_id):
    user_id = str(user_id)
    removed = 0
    for ig_id, t in list(tenants().items()):
        if ig_id == user_id or str(t.get("app_user_id", "")) == user_id:
            tenants().pop(ig_id, None)
            core.db_delete("tenant:" + ig_id)
            for k in [k for k in core.STATE["chats"] if k.startswith(f"ig:{ig_id}:")]:
                core.STATE["chats"].pop(k, None)
                core.db_delete("chat:" + k)
                removed += 1
    for k in [k for k in core.STATE["chats"] if k.startswith("ig:") and k.endswith(":" + user_id)]:
        core.STATE["chats"].pop(k, None)
        core.db_delete("chat:" + k)
        removed += 1
    core.save_file()
    return removed

# --------------------------------------------------------------------------
# Admin buyruqlari (Telegram, faqat REPORT_CHAT_ID dan)
# --------------------------------------------------------------------------
def admin_command(text):
    parts = text.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    if cmd in ("/ig", "/ig_list"):
        if not tenants():
            return f"Подключённых Instagram пока нет.\nСсылка для подключения: {PUBLIC_URL}/ig"
        lines = ["Instagram аккаунты:"]
        for t in tenants().values():
            days = int((t.get("expires_at", 0) - time.time()) / 86400)
            lines.append(f"• @{t.get('username')} (id {t['ig_id']}) — {'вкл' if t.get('enabled', True) else 'выкл'}, "
                         f"{'наш' if is_own(t) else ('база ✅' if t.get('kb') else 'база ❌')}, токен ещё {days} дн., "
                         f"отчёты → {t.get('report_chat')}")
        lines.append(f"\nСсылка для подключения клиента: {PUBLIC_URL}/ig")
        return "\n".join(lines)
    if cmd == "/ig_link":
        return f"Отправьте клиенту: {PUBLIC_URL}/ig"
    if cmd == "/ig_kb":
        head, _, kb = arg.partition("\n")
        ref, _, company = head.partition("|")
        t = find_tenant(ref.strip())
        if not t or not kb.strip():
            return "Формат:\n/ig_kb <id или @username> | Название компании\nописание, услуги, цены, адрес, график"
        t["company"] = company.strip() or t.get("company") or t.get("username")
        t["kb"] = kb.strip()[:6000]
        save_tenant(t)
        return f"База знаний для @{t.get('username')} сохранена ({len(t['kb'])} символов). Бот отвечает."
    if cmd == "/ig_report":
        ref, _, chat = arg.partition(" ")
        t = find_tenant(ref)
        if not t or not chat.strip():
            return "Формат: /ig_report <id или @username> <telegram chat id>"
        t["report_chat"] = chat.strip()
        save_tenant(t)
        return f"Отчёты по @{t.get('username')} → {t['report_chat']} (этот чат должен нажать /start у бота)."
    if cmd in ("/ig_on", "/ig_off"):
        t = find_tenant(arg)
        if not t:
            return "Формат: /ig_on <id или @username>"
        t["enabled"] = cmd == "/ig_on"
        save_tenant(t)
        return f"@{t.get('username')}: бот {'включён' if t['enabled'] else 'выключен'}."
    return None

# --------------------------------------------------------------------------
# HTTP sahifalar
# --------------------------------------------------------------------------
STYLE = """<style>:root{--bg:#f6f7fb;--fg:#111827;--mut:#5b6474;--card:#fff;--acc:#2f6bff;--line:#e5e7ef}
@media (prefers-color-scheme:dark){:root{--bg:#0f1220;--fg:#eef1f8;--mut:#a4adbf;--card:#171b2e;--acc:#6f97ff;--line:#2a3050}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 16px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px}
h1{font-size:28px;line-height:1.2;margin:0 0 12px}h2{font-size:19px;margin:28px 0 8px}p,li{color:var(--fg)}small,.mut{color:var(--mut)}
.btn{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;padding:14px 22px;border-radius:12px;font-weight:600}
a{color:var(--acc)}</style>"""

COMPANY = "AI Business UZ"
CONTACTS = "Telegram: @businessaiuz · Phone: +998 93 890 02 02 · Tashkent, Uzbekistan · https://businessai.uz"


def page(title, body):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title>{STYLE}</head><body><main><div class='card'>{body}</div>"
            f"<p class='mut' style='margin-top:16px'>{COMPANY} · {CONTACTS}</p></main></body></html>")


PRIVACY = f"""<h1>Privacy Policy</h1><p class='mut'>Last updated: October 18, 2026</p>
<p>{COMPANY} ("we") provides an AI sales assistant that answers customer messages on behalf of businesses in Instagram Direct and Telegram. This policy explains what data we process and why.</p>
<h2>Data we process</h2><ul>
<li><b>Business accounts that connect Instagram:</b> Instagram account ID, username, name, and an access token issued by Meta with the permissions <code>instagram_business_basic</code> and <code>instagram_business_manage_messages</code>.</li>
<li><b>People who message a connected business:</b> Instagram-scoped user ID, name/username (if available), and the text of messages in the conversation, plus details the person chooses to share (for example, a phone number to request a call back).</li></ul>
<h2>How we use data</h2><ul>
<li>To read incoming Direct messages and send replies on behalf of the connected business within Meta's 24-hour messaging window.</li>
<li>To remember the conversation context so replies are relevant.</li>
<li>To notify the business's staff about leads (for example, a customer asked for a call back).</li></ul>
<p>We do not sell data, do not use it for advertising, and do not share it with third parties except service providers needed to run the service (cloud hosting and an AI language-model provider that generates reply text). Data is not used to train AI models.</p>
<h2>Retention</h2><p>Conversation data is kept for up to 30 days of inactivity and then deleted. Access tokens are kept while the business keeps the account connected.</p>
<h2>Your choices and data deletion</h2><p>A business can disconnect at any time in Instagram settings (Settings → Apps and websites / Business integrations). Anyone can request deletion of their data — see <a href='{PUBLIC_URL}/data-deletion'>Data Deletion Instructions</a> — or contact us via Telegram @businessaiuz. We delete data within 30 days.</p>
<h2>Contact</h2><p>{CONTACTS}</p>
<hr><p class='mut'>Кратко на русском: мы обрабатываем только сообщения в Direct подключённых бизнес-аккаунтов, чтобы отвечать клиентам от имени бизнеса; данные не продаём и не передаём третьим лицам, удаляем по запросу.</p>"""

TERMS = f"""<h1>Terms of Service</h1><p class='mut'>Last updated: October 18, 2026</p>
<p>By connecting an Instagram professional account to {COMPANY}'s AI assistant, the business agrees that:</p><ul>
<li>The assistant replies to customer messages on its behalf using the information the business provides (products, prices, contacts).</li>
<li>The business is responsible for the accuracy of that information and for complying with Instagram's Terms of Use, Meta Platform Terms and applicable law. Spam, unsolicited messages and prohibited goods are not allowed.</li>
<li>The assistant only replies to people who message the business first and only within Meta's messaging window.</li>
<li>Customers can always ask for a human; the business's staff can take over any conversation.</li>
<li>The business can disconnect at any time; we may suspend accounts that violate these terms.</li></ul>
<p>Contact: {CONTACTS}</p>"""

DELETION = f"""<h1>Data Deletion Instructions</h1>
<p>To delete your data from {COMPANY}'s AI assistant:</p><ol>
<li>Business accounts: in Instagram go to Settings → Apps and websites (or Business integrations), find "{COMPANY}" and remove it. Meta will notify us and we will delete the account's token and conversation data.</li>
<li>Anyone (including people who messaged a business): send a request to Telegram @businessaiuz or call +998 93 890 02 02 with your Instagram username. We delete the data within 30 days and confirm.</li></ol>
<p class='mut'>Ma'lumotlaringizni o'chirish uchun Telegram @businessaiuz ga yozing. / Для удаления данных напишите в Telegram @businessaiuz.</p>"""


def landing():
    if not configured():
        return page("Connect Instagram", "<h1>Instagram подключение</h1><p>Сервис ещё настраивается (нет IG_APP_ID / IG_APP_SECRET).</p>")
    return page("Connect Instagram", f"""<h1>AI-ассистент для Instagram Direct</h1>
<p>Подключите Instagram бизнес-аккаунт — ИИ-ассистент {COMPANY} будет 24/7 отвечать клиентам в Direct на узбекском и русском, узнавать потребность и передавать вам горячие заявки.</p>
<p class='mut'>Нужен профессиональный аккаунт Instagram (Бизнес или Автор). В настройках Instagram включите «Разрешить доступ к сообщениям» для подключённых инструментов.</p>
<p style='margin:24px 0'><a class='btn' href='{PUBLIC_URL}/ig/connect'>Подключить Instagram</a></p>
<small>Нажимая кнопку, вы соглашаетесь с <a href='{PUBLIC_URL}/terms'>условиями</a> и <a href='{PUBLIC_URL}/privacy'>политикой конфиденциальности</a>.</small>""")


def respond_html(h, status, body, ctype="text/html; charset=utf-8", headers=None):
    data = body.encode() if isinstance(body, str) else body
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)


ROUTES_GET = ("/privacy", "/terms", "/data-deletion", "/deletion-status", "/ig")


def handle_get(h):
    """True qaytarsa — so'rov shu yerda bajarildi"""
    u = urllib.parse.urlparse(h.path)
    path, q = u.path.rstrip("/") or "/", urllib.parse.parse_qs(u.query)
    if not (path in ROUTES_GET or path.startswith("/ig/")):
        return False
    if path == "/privacy":
        respond_html(h, 200, page("Privacy Policy", PRIVACY))
    elif path == "/terms":
        respond_html(h, 200, page("Terms of Service", TERMS))
    elif path == "/data-deletion":
        respond_html(h, 200, page("Data Deletion", DELETION))
    elif path == "/deletion-status":
        code = html.escape((q.get("code") or [""])[0])
        respond_html(h, 200, page("Deletion status", f"<h1>Deletion request {code}</h1><p>Your data has been deleted.</p>"))
    elif path == "/ig":
        respond_html(h, 200, landing())
    elif path == "/ig/connect":
        if not configured():
            respond_html(h, 503, landing())
        else:
            respond_html(h, 302, "", headers={"Location": connect_url()})
    elif path == "/ig/callback":
        state = (q.get("state") or [""])[0]
        with LOCK:
            ok_state = OAUTH_STATES.pop(state, None) is not None
        if (q.get("error") or [""])[0]:
            respond_html(h, 200, page("Отменено", "<h1>Подключение отменено</h1><p>Вы можете попробовать снова.</p>"
                                      f"<p><a class='btn' href='{PUBLIC_URL}/ig'>Назад</a></p>"))
        elif not ok_state or not q.get("code"):
            respond_html(h, 400, page("Ошибка", f"<h1>Ссылка устарела</h1><p><a class='btn' href='{PUBLIC_URL}/ig'>Начать заново</a></p>"))
        else:
            t, err = finish_oauth(q["code"][0])
            if err:
                print("IG oauth error:", err)
                respond_html(h, 200, page("Ошибка", f"<h1>Не получилось подключить</h1><p class='mut'>{html.escape(err)}</p>"))
            else:
                respond_html(h, 200, page("Готово", f"<h1>Instagram @{html.escape(t['username'])} подключён ✅</h1>"
                                          "<p>Ассистент начнёт отвечать в Direct после настройки базы знаний вашей компании. "
                                          "Мы свяжемся с вами в ближайшее время.</p>"))
    elif path == "/ig/webhook":
        if (q.get("hub.mode") or [""])[0] == "subscribe" and IG_VERIFY_TOKEN and \
                (q.get("hub.verify_token") or [""])[0] == IG_VERIFY_TOKEN:
            respond_html(h, 200, (q.get("hub.challenge") or [""])[0], ctype="text/plain")
        else:
            respond_html(h, 403, "forbidden", ctype="text/plain")
    else:
        respond_html(h, 404, page("Not found", "<h1>404</h1>"))
    return True


def handle_post(h, body):
    path = urllib.parse.urlparse(h.path).path.rstrip("/")
    if not path.startswith("/ig/"):
        return False
    if path == "/ig/webhook":
        if not valid_signature(body, h.headers.get("X-Hub-Signature-256", "")):
            print("IG webhook: bad signature")
            respond_html(h, 403, "bad signature", ctype="text/plain")
            return True
        respond_html(h, 200, "EVENT_RECEIVED", ctype="text/plain")
        try:
            payload = json.loads(body or b"{}")
        except Exception:
            return True
        threading.Thread(target=_safe, args=(on_webhook, payload), daemon=True).start()
        return True
    form = urllib.parse.parse_qs(body.decode("utf-8", "ignore"))
    data = parse_signed_request((form.get("signed_request") or [""])[0])
    if path == "/ig/deauthorize":
        if data and data.get("user_id"):
            for t in tenants().values():
                if str(t.get("app_user_id", "")) == str(data["user_id"]) or t["ig_id"] == str(data["user_id"]):
                    t["enabled"] = False
                    t["token"] = ""
                    save_tenant(t)
                    notify_admin(f"Instagram @{t.get('username')} отключил приложение.")
        respond_html(h, 200, "{}", ctype="application/json")
    elif path == "/ig/data-deletion":
        code = secrets.token_hex(6)
        if data and data.get("user_id"):
            delete_user_data(data["user_id"])
        respond_html(h, 200, json.dumps({"url": f"{PUBLIC_URL}/deletion-status?code={code}", "confirmation_code": code}),
                     ctype="application/json")
    else:
        respond_html(h, 404, "not found", ctype="text/plain")
    return True


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception as e:
        print("IG error:", e)
