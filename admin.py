"""
Admin panel — Telegram Mini App (faqat REPORT_CHAT_ID uchun).
Ichida: xarajatlar (Claude, ElevenLabs, server) kanal bo'yicha, voronka, lidlar, sotuvlar.

Muhit o'zgaruvchilari (ixtiyoriy):
  ELEVEN_PLAN_USD       — ElevenLabs tarifi narxi, $/oy (default 22)
  ELEVEN_PLAN_CREDITS   — tarifdagi kreditlar (default 121000; API'dan aniq qiymat olinadi)
  STT_INCLUDED_HOURS    — tarifga kirgan ovoz tanish soatlari (default 100)
  SERVER_USD            — Railway, $/oy (default 5)
"""
import os
import json
import re
import time
import hmac
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

core = None
ELEVEN_PLAN_USD = float(os.environ.get("ELEVEN_PLAN_USD", "22"))
ELEVEN_PLAN_CREDITS = int(os.environ.get("ELEVEN_PLAN_CREDITS", "121000"))
STT_INCLUDED_HOURS = float(os.environ.get("STT_INCLUDED_HOURS", "6.1"))   # Creator: 6 soat 7 daqiqa
STT_EXTRA_PER_HOUR = float(os.environ.get("STT_EXTRA_PER_HOUR", "0.22"))
SERVER_USD = float(os.environ.get("SERVER_USD", "5"))
CHANNELS = ("tg", "ig")
CH_NAMES = {"tg": "Telegram", "ig": "Instagram", "manual": "Вручную", "test": "Ваши тесты", "eval": "Проверки /eval",
            "other": "Без канала"}
CRM_CH = ("tg", "ig", "manual")
PIPE = [("dialog", "Диалог с ботом"), ("new", "Новый лид"), ("work", "В работе"), ("offer", "Предложение"),
        ("pay", "Ждёт оплаты"), ("won", "Купил"), ("lost", "Отказ")]
EDIT_FIELDS = ("name", "phone", "business", "need", "budget", "call_time", "offer")
EXP_CATS = [("ads_ig", "Таргет Instagram", "ig"), ("ads_tg", "Реклама Telegram", "tg"), ("ads_other", "Другая реклама", ""),
            ("ai", "ИИ-сервисы (Claude, ChatGPT)", ""), ("server", "Сервер (Railway)", ""), ("voice", "Голос (ElevenLabs)", ""),
            ("services", "Другие сервисы", ""), ("people", "Зарплата / фриланс", ""), ("other", "Прочее", "")]
SEED_MONTHLY = [("ai", 224, "Claude"), ("ai", 5, "ChatGPT"), ("server", 35, "Railway"), ("voice", 22, "ElevenLabs")]
_EXP = {"loaded": False, "items": []}


def expenses():
    if not _EXP["loaded"]:
        _EXP["loaded"] = True
        _EXP["items"] = core.db_get("admin:expenses") or []
    return _EXP["items"]


def add_expense(d):
    cats = {c[0]: c for c in EXP_CATS}
    cat = d.get("cat") if d.get("cat") in cats else "other"
    try:
        amount = round(float(d.get("amount") or 0), 2)
        ts = float(d.get("ts") or time.time())
    except Exception:
        return False
    if amount <= 0:
        return False
    item = {"id": hashlib.sha1(f"{time.time()}{amount}{len(expenses())}".encode()).hexdigest()[:10], "rec": d.get("rec", ""), "ts": ts, "cat": cat, "ch": cats[cat][2], "amount": amount,
            "note": str(d.get("note") or "")[:300], "created": time.time()}
    with core.LOCK:
        expenses().append(item)
        items = list(_EXP["items"])
    core.db_put("admin:expenses", items)
    return True


_REC = {"loaded": False, "items": []}


def recurring():
    if not _REC["loaded"]:
        _REC["loaded"] = True
        _REC["items"] = core.db_get("admin:recurring") or []
    return _REC["items"]


_SEEDED = {}


def seed_monthly():
    """Bir marta: egasi aytgan oylik obunalar (Claude, ChatGPT, Railway, ElevenLabs) — keyin panelda o'zgartiriladi"""
    if _SEEDED.get("done"):
        return
    if core.db_get("admin:seeded") or any(r.get("freq") == "monthly" for r in recurring()):
        _SEEDED["done"] = True
        return
    _SEEDED["done"] = True
    first = datetime.now(core.TZ).strftime("%Y-%m-01")
    for cat, amount, note in SEED_MONTHLY:
        add_recurring({"cat": cat, "amount": amount, "note": note, "since": first, "freq": "monthly"})
    core.db_put("admin:seeded", True)


def add_recurring(d):
    """Takroriy xarajat: har kuni (target $15/kun) yoki har oy (Claude $224/oy) — avtomatik yoziladi"""
    cats = {c[0] for c in EXP_CATS}
    try:
        amount = round(float(d.get("amount") or 0), 2)
    except Exception:
        return False
    if amount <= 0:
        return False
    since = d.get("since") or datetime.now(core.TZ).strftime("%Y-%m-%d")
    rule = {"id": hashlib.sha1(f"r{time.time()}{amount}{d.get('note')}".encode()).hexdigest()[:10],
            "cat": d.get("cat") if d.get("cat") in cats else "ads_ig", "freq": "monthly" if d.get("freq") == "monthly" else "daily",
            "amount": amount, "note": str(d.get("note") or "")[:200], "since": since, "last": "", "active": True}
    with core.LOCK:
        recurring().append(rule)
    core.db_put("admin:recurring", recurring())
    apply_recurring()
    return True


def update_recurring(rid, d):
    with core.LOCK:
        for r in recurring():
            if r["id"] == str(rid):
                if d.get("amount"):
                    r["amount"] = round(float(d["amount"]), 2)
                if "note" in d:
                    r["note"] = str(d["note"] or "")[:200]
    core.db_put("admin:recurring", recurring())
    return True


def stop_recurring(rid):
    with core.LOCK:
        for r in recurring():
            if r["id"] == str(rid):
                r["active"] = False
    core.db_put("admin:recurring", recurring())
    return True


def apply_recurring():
    """Har bir faol qoida uchun yozilmagan kunlarni (bugungacha) xarajatga qo'shadi"""
    today = datetime.now(core.TZ).date()
    changed = False
    for r in list(recurring()):
        if not r.get("active"):
            continue
        monthly = r.get("freq") == "monthly"
        day = datetime.strptime(r["last"] or r["since"], "%Y-%m-%d").date()
        if r["last"]:
            day = datetime.strptime(core.BILL.add_months(r["last"], 1), "%Y-%m-%d").date() if monthly else day + timedelta(days=1)
        n = 0
        while day <= today and n < 400:
            ts = datetime(day.year, day.month, day.day, 12, tzinfo=core.TZ).timestamp()
            add_expense({"cat": r["cat"], "amount": r["amount"], "ts": ts,
                         "note": (r["note"] or "") + (" · ежемесячно" if monthly else " · ежедневно"), "rec": r["id"]})
            r["last"] = day.strftime("%Y-%m-%d")
            day = datetime.strptime(core.BILL.add_months(r["last"], 1), "%Y-%m-%d").date() if monthly else day + timedelta(days=1)
            n += 1
            changed = True
    if changed:
        core.db_put("admin:recurring", recurring())


def del_expense(eid):
    with core.LOCK:
        n = len(expenses())
        _EXP["items"] = [x for x in _EXP["items"] if x["id"] != str(eid)]
        items, ok = list(_EXP["items"]), len(_EXP["items"]) < n
    core.db_put("admin:expenses", items)
    return ok
_SUB = {"t": 0, "v": None}


def init(bot_module):
    global core
    core = bot_module

# --------------------------------------------------------------------------
# Kirish tekshiruvi (Telegram WebApp initData)
# --------------------------------------------------------------------------
def check_init(init_data):
    """initData imzosini tekshiradi; to'g'ri bo'lsa — foydalanuvchi id"""
    try:
        pairs = urllib.parse.parse_qsl(init_data or "", keep_blank_values=True)
        d = dict(pairs)
        got = d.pop("hash", "")
        if not got:
            return None
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        secret = hmac.new(b"WebAppData", core.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(d.get("auth_date") or 0) > 7 * 86400:
            return None
        return str((json.loads(d.get("user") or "{}")).get("id") or "")
    except Exception as e:
        print("Admin auth error:", e)
        return None


def role(h):
    """admin — hammasi; staff — faqat lidlar (alohida mijoz botida hisobot oluvchi xodim), moliya yo'q"""
    if core.BILL.session_ok(h):          # veb-CRM (kompyuterdan) — bot bergan havola orqali kirilgan
        return "admin"
    uid = check_init(h.headers.get("X-Init-Data", ""))
    if not uid:
        return None
    if uid == str(core.REPORT_CHAT_ID):
        return "admin"
    if core.AGENT_MODE and core.is_staff(uid):
        return "staff"
    return None


def is_admin(h):
    return role(h) == "admin"


STAFF_POST = ("/admin/api/deal", "/admin/api/remind", "/admin/api/client", "/admin/api/new", "/admin/api/bot", "/admin/api/history")


def staff_view(d):
    """Xodim uchun: faqat qo'ng'iroqlar va mijozlar, pul/xarajat maydonlarisiz"""
    crm = []
    for x in d["crm"]:
        x = {k: v for k, v in x.items() if k not in ("cost", "payments", "paid")}
        x["deal"] = {"status": (x.get("deal") or {}).get("status", "")}
        x["facts"] = {k: v for k, v in x["facts"].items() if k != "budget"}
        crm.append(x)
    calls = [{k: v for k, v in x.items() if k != "budget"} for x in d["calls"]]
    proc = {ch: {k: v for k, v in p.items() if k != "revenue"} for ch, p in d["proc"].items()}
    needs = {}
    for x in d["leads"]:
        n = (x["facts"].get("offer") or x["facts"].get("need") or "").strip()[:60]
        if n:
            needs[n] = needs.get(n, 0) + 1
    f = d["funnel"]
    return {"role": "staff", "period": d["period"], "generated": d["generated"], "calls": calls, "crm": crm,
            "pipe": d["pipe"], "ch_names": d["ch_names"], "company": core.AGENTS.name(core.AGENT_MODE) if core.AGENT_MODE else "",
            "funnel": f, "proc": proc, "funnel_steps": [("wrote", "Написали"), ("answered", "Бот ответил"), ("warm", "Заинтересовались"),
                                                        ("hot", "Горячие"), ("lead", "Оставили контакт"), ("won", "Записались")],
            "daily": [{k: v for k, v in x.items() if k != "cost"} for x in d["daily"]],
            "totals": {"dialogs": d["totals"]["dialogs"], "leads": d["totals"]["leads"], "won": d["totals"]["won"],
                       "hot": sum(f[c]["hot"] for c in f)},
            "needs": sorted(needs.items(), key=lambda x: -x[1])[:10], "ins": staff_insights(d["period"]),
            "crm": crm_stats(core.AGENT_MODE, d["period"]) if core.AGENT_MODE else None,
            "prev_label": {"today": "вчера", "yesterday": "позавчера"}.get(d["period"], "предыдущим таким же периодом"),
            "period_label": period_label(d["period"])}

# --------------------------------------------------------------------------
# Ma'lumot yig'ish
# --------------------------------------------------------------------------
def eleven_subscription():
    """ElevenLabs: haqiqiy sarflangan kreditlar (5 daqiqa kesh)"""
    if not core.STT.ELEVEN_KEY:
        return None
    if time.time() - _SUB["t"] < 300:
        return _SUB["v"]
    v = None
    try:
        req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription",
                                     headers={"xi-api-key": core.STT.ELEVEN_KEY})
        with urllib.request.urlopen(req, timeout=10) as r:
            s = json.loads(r.read())
        v = {"tier": s.get("tier"), "used": s.get("character_count"), "limit": s.get("character_limit"),
             "reset": s.get("next_character_count_reset_unix")}
    except Exception as e:
        print("ElevenLabs subscription error:", e)
    _SUB.update(t=time.time(), v=v)
    return v


PERIODS = [("today", "Сегодня"), ("yesterday", "Вчера"), ("7d", "7 дней"), ("30d", "30 дней"), ("month", "Этот месяц"),
           ("lastmonth", "Прошлый месяц"), ("quarter", "Квартал"), ("year", "Год"), ("all", "Всё время")]


def period_range(period):
    """Davr: tayyor (today/yesterday/7d/30d/month/lastmonth/quarter/year) yoki o'zingizniki «c:YYYY-MM-DD:YYYY-MM-DD»"""
    now = datetime.now(core.TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period = str(period or "30d")
    e = today
    if period == "today":
        start = today
    elif period == "yesterday":
        start = e = today - timedelta(days=1)
    elif period == "7d":
        start = today - timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
    elif period == "lastmonth":
        e = today.replace(day=1) - timedelta(days=1)
        start = e.replace(day=1)
    elif period == "quarter":
        start = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
    elif period == "year":
        start = today - timedelta(days=364)
    elif period == "all":
        start = today - timedelta(days=729)
    elif period.startswith("c:"):
        try:
            a, b = period[2:].split(":")[:2]
            start = datetime.strptime(a, "%Y-%m-%d").replace(tzinfo=core.TZ)
            e = datetime.strptime(b, "%Y-%m-%d").replace(tzinfo=core.TZ)
            if e < start:
                start, e = e, start
            e = min(e, today)
            start = max(min(start, e), e - timedelta(days=730))
            period = "c:" + start.strftime("%Y-%m-%d") + ":" + e.strftime("%Y-%m-%d")
        except Exception:
            period, start, e = "30d", today - timedelta(days=29), today
    else:
        period, start = "30d", today - timedelta(days=29)
    days = []
    d = start
    while d <= e:
        days.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return period, start.timestamp(), days


def period_end(days):
    return datetime.strptime(days[-1], "%Y-%m-%d").replace(tzinfo=core.TZ).timestamp() + 86400


def period_label(period):
    if str(period).startswith("c:"):
        a, b = period[2:].split(":")
        f = lambda x: x[8:10] + "." + x[5:7]
        return f(a) if a == b else f(a) + "–" + f(b)
    return dict(PERIODS).get(period, period)


def chat_first_ts(c):
    ts = c.get("first_ts")
    if ts:
        return ts
    u = [h.get("ts") or 0 for h in c.get("history", []) if h["r"] == "u"]
    return min(u) if u else 0


def stage_of(c):
    deal = (c.get("deal") or {}).get("status")
    if deal == "won":
        return 6, "Купил"
    if deal == "lost":
        return -1, "Отказ"
    if c.get("lead_sent"):
        return 5, "Оставил контакт"
    if c.get("hot_sent") or int(c.get("readiness") or 0) >= core.HOT_THRESHOLD:
        return 4, "Горячий"
    if int(c.get("readiness") or 0) >= 40:
        return 3, "Тёплый"
    if (c.get("facts") or {}).get("business"):
        return 2, "Рассказал о бизнесе"
    if any(h["r"] == "a" for h in c.get("history", [])):
        return 1, "В диалоге"
    return 0, "Написал"


FUNNEL = [("wrote", "Написали"), ("answered", "Бот ответил"), ("business", "Рассказали о бизнесе"), ("warm", "Тёплые (40%+)"), ("hot", "Горячие"),
          ("lead", "Оставили контакт"), ("won", "Купили")]


def funnel_flags(c):
    hist = c.get("history", [])
    n_u = sum(1 for h in hist if h["r"] == "u")
    r = int(c.get("readiness") or 0)
    won = (c.get("deal") or {}).get("status") == "won"
    lead = bool(c.get("lead_sent")) or won
    hot = lead or bool(c.get("hot_sent")) or r >= core.HOT_THRESHOLD
    warm = hot or r >= 40
    business = warm or bool((c.get("facts") or {}).get("business"))
    engaged = n_u >= 3 or lead
    answered = business or any(h["r"] == "a" for h in hist)
    return {"wrote": n_u > 0 or answered, "answered": answered, "engaged": engaged, "business": business,
            "warm": warm, "hot": hot, "lead": lead, "won": won}


REMOTE = {"t": 0, "chats": {}}
MAIN_DB_TABLE = "".join(ch for ch in os.environ.get("MAIN_DB_TABLE", "demo_bot_state") if ch.isalnum() or ch == "_")


def remote_ig_chats():
    """Alohida mijoz botida: shu agentning Instagram suhbatlari asosiy bot jadvalidan (faqat o'qish, 60 s kesh)"""
    if not core.AGENT_MODE or not MAIN_DB_TABLE or MAIN_DB_TABLE == core.DB_TABLE:
        return {}
    if time.time() - REMOTE["t"] < 60:
        return REMOTE["chats"]
    out, tid = {}, ""
    try:
        if core.db_connect() is not None:
            with core.DB_LOCK:
                rows = core.DB.run("SELECT v FROM " + MAIN_DB_TABLE + " WHERE k = 'agents'")
                tid = str(((json.loads(rows[0][0]) if rows else {}).get(core.AGENT_MODE) or {}).get("ig_tenant") or "")
                if tid:
                    rows = core.DB.run("SELECT k, v FROM " + MAIN_DB_TABLE + " WHERE k LIKE :p AND updated > now() - interval '365 days'",
                                       p="chat:ig:" + tid + ":%")
                    for k, v in rows:
                        c = json.loads(v)
                        c.update(channel="ig", tenant="", ro=True)
                        c.pop("agent", None)
                        out[k[5:]] = c
    except Exception as e:
        print("Remote IG chats error:", e)
        return REMOTE["chats"]
    if len(out) != len(REMOTE["chats"]) or not REMOTE["t"]:
        print(f"Remote IG chats: {len(out)} (table {MAIN_DB_TABLE}, tenant {tid or 'не привязан'})")
    REMOTE.update(t=time.time(), chats=out)
    return out


def build(period="30d"):
    period, start, days = period_range(period)
    with core.LOCK:
        chats = json.loads(json.dumps(core.STATE["chats"]))
    chats.update(json.loads(json.dumps(remote_ig_chats())))
    with core.LOCK:
        stats = json.loads(json.dumps({d: core.STATS.get(d, {}) for d in days}))
        usage = json.loads(json.dumps({d: core.USAGE.get(d, {}) for d in days}))

    # --- hodisalar (kanal bo'yicha)
    ev = {}
    for d in days:
        for ch, s in stats[d].items():
            acc = ev.setdefault(ch, {})
            for k, v in s.items():
                acc[k] = acc.get(k, 0) + v
    ai_total = sum(core.usage_cost(usage[d]) for d in days)
    ai_tracked = sum(s.get("ai_usd", 0) for s in ev.values())
    sub = eleven_subscription()
    credits_limit = (sub or {}).get("limit") or ELEVEN_PLAN_CREDITS
    usd_per_credit = ELEVEN_PLAN_USD / max(1, credits_limit)

    costs = {}
    for ch in list(CHANNELS) + ["test", "eval"]:
        s = ev.get(ch, {})
        tts = s.get("tts_chars", 0)
        costs[ch] = {"ai": round(s.get("ai_usd", 0), 4), "tts_chars": tts,
                     "tts_usd": round(tts * usd_per_credit, 3), "stt_min": round(s.get("stt_sec", 0) / 60, 1),
                     "ai_calls": s.get("ai_calls", 0)}
    costs["other"] = {"ai": round(max(0.0, ai_total - ai_tracked), 4), "tts_chars": 0, "tts_usd": 0, "stt_min": 0, "ai_calls": 0}

    # --- dialoglar, voronka, lidlar
    funnel = {ch: {k: 0 for k, _ in FUNNEL} for ch in CHANNELS}
    proc = {ch: {"dialogs": 0, "engaged": 0, "client_msgs": 0, "bot_msgs": 0, "voice_in": 0, "followups": 0, "revived": 0,
                 "silent": 0, "stopped": 0, "handoff": 0, "readiness_sum": 0, "revenue": 0.0, "won": 0}
            for ch in CHANNELS}
    biz = {}
    leads = []
    daily = {d: {"tg": 0, "ig": 0, "leads": 0, "won": 0} for d in days}
    revenue = 0.0
    for key, c in chats.items():
        ch = core.chat_channel(c)
        if ch not in CHANNELS:
            continue
        hist = c.get("history", [])
        first = chat_first_ts(c)
        deal = c.get("deal") or {}
        if deal.get("status") == "won" and start <= (deal.get("ts") or 0) < period_end(days):
            revenue += float(deal.get("amount") or 0)
            proc[ch]["revenue"] += float(deal.get("amount") or 0)
            dd = datetime.fromtimestamp(deal["ts"], core.TZ).strftime("%Y-%m-%d")
            if dd in daily:
                daily[dd]["won"] += 1
        if first < start or first >= period_end(days):
            continue
        fl = funnel_flags(c)
        for k in funnel[ch]:
            funnel[ch][k] += int(fl[k])
        p = proc[ch]
        p["dialogs"] += 1
        p["engaged"] += int(fl["engaged"])
        p["client_msgs"] += sum(1 for h in hist if h["r"] == "u")
        p["bot_msgs"] += sum(1 for h in hist if h["r"] == "a" and not h.get("human"))
        p["voice_in"] += sum(1 for h in hist if h["r"] == "u" and h["t"].startswith(core.STT.VOICE_PREFIX))
        p["followups"] += sum(1 for h in hist if h.get("f"))
        p["revived"] += int(any(h.get("f") and any(x["r"] == "u" for x in hist[i + 1:]) for i, h in enumerate(hist)))
        p["silent"] += int(bool(hist) and hist[-1]["r"] == "a" and c.get("followups", 0) >= len(core.FOLLOWUP_MINUTES))
        p["stopped"] += int(c.get("status") == "stopped")
        p["handoff"] += int(c.get("status") == "handoff")
        p["readiness_sum"] += int(c.get("readiness") or 0)
        p["won"] += int(fl["won"])
        b = ((c.get("facts") or {}).get("business") or "").strip().lower()[:40]
        if b:
            biz[b] = biz.get(b, 0) + 1
        fd = datetime.fromtimestamp(first, core.TZ).strftime("%Y-%m-%d")
        if fd in daily:
            daily[fd][ch] += 1
            daily[fd]["leads"] += int(fl["lead"])
        cc = c.get("cost") or {}
        ccost = {"ai": round(cc.get("ai_usd", 0), 4), "tts_chars": int(cc.get("tts_chars", 0)),
                 "tts_usd": round(cc.get("tts_chars", 0) * usd_per_credit, 4), "stt_sec": int(cc.get("stt_sec", 0))}
        ccost["total"] = round(ccost["ai"] + ccost["tts_usd"], 4)
        lvl, label = stage_of(c)
        last_ts = max([h.get("ts") or 0 for h in hist] or [first])
        who = c.get("name") or "—"
        if c.get("username"):
            who += " @" + c["username"]
        leads.append({"key": key, "ch": ch, "who": who, "stage": label, "lvl": lvl,
                      "readiness": int(c.get("readiness") or 0), "last": last_ts, "first": first,
                      "facts": {k: v for k, v in (c.get("facts") or {}).items() if v},
                      "deal": deal, "status": c.get("status"), "cost": ccost,
                      "tail": [{"r": h["r"], "t": h["t"].replace(core.STT.VOICE_PREFIX, "🎙 ")[:300],
                                "v": bool(h.get("voice")), "f": bool(h.get("f"))} for h in hist[-8:]]})
    leads.sort(key=lambda x: (-x["lvl"], -x["last"]))
    calls = call_list(chats)

    # --- umumiy hisob
    tts_usd = sum(costs[c]["tts_usd"] for c in costs)
    stt_min = sum(costs[c]["stt_min"] for c in costs)
    months = max(1.0, len(days) / 30.0) if period != "today" else 1 / 30
    server = round(SERVER_USD * (len(days) / 30.0), 2)
    stt_extra = round(max(0.0, stt_min / 60 - STT_INCLUDED_HOURS * months) * STT_EXTRA_PER_HOUR, 2)
    total_dialogs = sum(proc[c]["dialogs"] for c in CHANNELS)
    total_leads = sum(funnel[c]["lead"] for c in CHANNELS)
    total_won = sum(funnel[c]["won"] for c in CHANNELS)
    # --- qo'lda kiritilgan xarajatlar (reklama va b.)
    try:
        seed_monthly()
        apply_recurring()
    except Exception as e:
        print("Recurring error:", e)
    end_ts = datetime.strptime(days[-1], "%Y-%m-%d").replace(tzinfo=core.TZ).timestamp() + 86400
    with core.LOCK:
        exp = [dict(x) for x in expenses() if start <= x["ts"] < end_ts]
    exp.sort(key=lambda x: -x["ts"])
    manual = round(sum(x["amount"] for x in exp), 2)
    by_cat = {c[0]: round(sum(x["amount"] for x in exp if x["cat"] == c[0]), 2) for c in EXP_CATS}
    ads = {ch: round(sum(x["amount"] for x in exp if x["ch"] == ch and x["cat"].startswith("ads")), 2) for ch in CHANNELS}
    if by_cat.get("server"):
        server = 0.0                    # Railway kiritilgan — taxminiy ulush hisoblanmaydi
    voice_auto = 0.0 if by_cat.get("voice") else tts_usd + stt_extra
    spend_auto = ai_total + voice_auto + server
    spend = spend_auto + manual
    econ = {}
    for ch in CHANNELS:
        bot_usd = costs[ch]["ai"] + costs[ch]["tts_usd"]
        total = ads[ch] + bot_usd
        f = funnel[ch]
        rev = proc[ch]["revenue"]
        econ[ch] = {"ads": ads[ch], "bot": round(bot_usd, 2), "total": round(total, 2), "dialogs": proc[ch]["dialogs"],
                    "leads": f["lead"], "won": f["won"], "revenue": round(rev, 2),
                    "per_dialog": round(total / proc[ch]["dialogs"], 2) if proc[ch]["dialogs"] else 0,
                    "per_lead": round(total / f["lead"], 2) if f["lead"] else 0,
                    "per_sale": round(total / f["won"], 2) if f["won"] else 0,
                    "romi": round((rev - total) / total * 100) if total else None}
    return {
        "period": period, "days": days, "generated": time.time(),
        "costs": costs, "ai_total": round(ai_total, 4), "tts_usd": round(tts_usd, 2), "stt_min": round(stt_min, 1),
        "stt_extra": stt_extra, "server": server, "spend": round(spend, 2),
        "eleven": {"sub": sub, "plan_usd": ELEVEN_PLAN_USD, "credits_limit": credits_limit,
                   "stt_included_h": STT_INCLUDED_HOURS},
        "funnel_steps": FUNNEL, "funnel": funnel, "proc": proc, "events": ev,
        **core.BILL.data(chats, start, end_ts),
        "agent": {"dialogs": total_dialogs, "leads": total_leads, "hot": sum(funnel[c]["hot"] for c in CHANNELS),
                  "replies": sum(ev.get(c, {}).get("replies", 0) for c in CHANNELS),
                  "msgs_in": sum(ev.get(c, {}).get("msgs_in", 0) for c in CHANNELS),
                  "voice_out": sum(ev.get(c, {}).get("voice_out", 0) for c in CHANNELS),
                  "followups": sum(ev.get(c, {}).get("followups", 0) for c in CHANNELS),
                  "ai_usd": round(sum(costs[c]["ai"] for c in CHANNELS), 3), "voice_usd": round(sum(costs[c]["tts_usd"] for c in CHANNELS), 3),
                  "cost": round(sum(costs[c]["ai"] + costs[c]["tts_usd"] for c in CHANNELS), 3)},
        "rules": core.BOSS.rules(), "voice_mode": next((m for m, v in core.BOSS.VOICE_MODES.items()
                                                         if v[0] == core.STT.TTS_STABILITY), "calm"),
        "tenants": [{"ig_id": t["ig_id"], "username": t.get("username", ""), "enabled": t.get("enabled", True),
                     "company": t.get("company", ""), "kb": bool(t.get("kb"))} for t in core.IG.tenants().values()],
        "connect_url": core.IG.PUBLIC_URL + "/ig",
        "expenses": exp, "manual": manual, "recurring": [r for r in recurring() if r.get("active")], "by_cat": by_cat, "exp_cats": EXP_CATS, "econ": econ, "spend_auto": round(spend_auto, 2),
        "profit": round(revenue - spend, 2), "romi": round((revenue - spend) / spend * 100) if spend else None,
        "totals": {"dialogs": total_dialogs, "leads": total_leads, "won": total_won, "revenue": round(revenue, 2),
                   "per_dialog": round(spend / total_dialogs, 4) if total_dialogs else 0,
                   "per_lead": round(spend / total_leads, 2) if total_leads else 0,
                   "per_sale": round(spend / total_won, 2) if total_won else 0},
        "daily": [{"d": d, **daily[d], "cost": round(core.usage_cost(usage[d]) + sum(
            s.get("tts_chars", 0) for s in stats[d].values()) * usd_per_credit, 3)} for d in days],
        "business": sorted(biz.items(), key=lambda x: -x[1])[:8],
        "period_label": period_label(period), "periods": PERIODS,
        "leads": leads[:150], "ch_names": CH_NAMES, "calls": calls, "crm": crm_list(chats), "pipe": PIPE,
    }


def chat_link(c):
    if core.chat_channel(c) == "ig":
        return "https://instagram.com/" + c["username"] if c.get("username") else ""
    return "tg://user?id=" + str(c.get("chat_id")) if c.get("chat_id") else ""


def fmt_phone(p):
    """+998 90 441 76 34 ko'rinishi; tel: havola uchun raqamlar"""
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    if len(d) == 9:
        d = "998" + d
    if len(d) == 12 and d.startswith("998"):
        return "+" + d, f"+998 {d[3:5]} {d[5:8]} {d[8:10]} {d[10:12]}"
    return ("+" + d if d else ""), (p or "")


def call_list(chats):
    """Kimga qo'ng'iroq qilish kerak: telefon qoldirganlar (barcha vaqt)"""
    out = []
    for key, c in chats.items():
        if core.chat_channel(c) not in CRM_CH:
            continue
        f = c.get("facts") or {}
        phone = f.get("phone") or ""
        if not (phone or c.get("lead_sent")):
            continue
        deal = (c.get("deal") or {}).get("status")
        called = (c.get("call") or {}).get("status") == "done"
        rm = c.get("remind") or {}
        rm_active = bool(rm.get("ts")) and not rm.get("done")
        rm_due = rm_active and rm["ts"] <= time.time()
        tel, pretty = fmt_phone(phone)
        want = "; ".join(x for x in [f.get("need"), f.get("offer") and "предложено: " + f["offer"]] if x) or \
            f.get("note") or f.get("business") or "—"
        who = c.get("name") or "—"
        if c.get("username"):
            who += " @" + c["username"]
        out.append({"key": key, "ch": core.chat_channel(c), "who": who, "phone": pretty, "tel": tel, "want": want,
                    "remind_ts": rm.get("ts", 0) if rm_active else 0, "remind_text": rm.get("text", "") if rm_active else "",
                    "remind_due": rm_due,
                    "business": f.get("business", ""), "call_time": f.get("call_time", ""), "note": f.get("note", ""),
                    "budget": f.get("budget", ""), "objection": f.get("objection", ""),
                    "readiness": int(c.get("readiness") or 0), "ts": c.get("lead_ts") or chat_first_ts(c),
                    "called": called, "called_ts": (c.get("call") or {}).get("ts", 0), "deal": deal or "",
                    "todo": deal not in ("won", "lost") and (not called or rm_due), "link": chat_link(c), "ro": bool(c.get("ro"))})
    out.sort(key=lambda x: (not x["todo"], not x["remind_due"], -x["ts"]))
    return out[:100]


def pipe_stage(c):
    deal = (c.get("deal") or {}).get("status")
    if deal in ("won", "lost"):
        return deal
    if c.get("stage") in dict(PIPE):
        return c["stage"]
    if (c.get("call") or {}).get("status") == "done":
        return "work"
    f = c.get("facts") or {}
    if f.get("phone") or c.get("lead_sent") or c.get("hot_sent") or core.chat_channel(c) == "manual":
        return "new"
    return "dialog"


def crm_list(chats):
    """CRM: barcha mijozlar (davrdan qat'i nazar) — karta uchun to'liq ma'lumot"""
    out = []
    usd_per_credit = ELEVEN_PLAN_USD / max(1, ELEVEN_PLAN_CREDITS)
    for key, c in chats.items():
        ch = core.chat_channel(c)
        if ch not in CRM_CH:
            continue
        hist = c.get("history", [])
        if ch != "manual" and not any(h["r"] == "u" for h in hist):
            continue
        f = c.get("facts") or {}
        tel, pretty = fmt_phone(f.get("phone", ""))
        cc = c.get("cost") or {}
        rm = c.get("remind") or {}
        out.append({
            "key": key, "ch": ch, "name": c.get("name") or f.get("name") or "", "username": c.get("username", ""),
            "phone": pretty, "tel": tel, "facts": {k: f.get(k, "") for k in ("business", "need", "budget", "call_time", "offer",
                                                                             "objection", "note", "current_tool")},
            "stage": pipe_stage(c), "deal": c.get("deal") or {}, "readiness": int(c.get("readiness") or 0),
            "first": chat_first_ts(c) or c.get("created", 0), "last": max([h.get("ts") or 0 for h in hist] or [c.get("created", 0)]),
            "notes": (c.get("notes") or [])[-30:], "called": (c.get("call") or {}).get("status") == "done",
            "remind_ts": rm.get("ts", 0) if rm.get("ts") and not rm.get("done") else 0, "remind_text": rm.get("text", ""),
            "cost": round(cc.get("ai_usd", 0) + cc.get("tts_chars", 0) * usd_per_credit, 4), "link": chat_link(c),
            "paused": (c.get("paused_until") or 0) > time.time(), "status": c.get("status", ""), "bot_off": bool(c.get("bot_off")),
            "payments": c.get("payments", []), "paid": round(sum(p["amount"] for p in c.get("payments", [])), 2),
            "ro": bool(c.get("ro")),
            "tail": [{"r": h["r"], "t": h["t"].replace(core.STT.VOICE_PREFIX, "🎙 ")[:400], "v": bool(h.get("voice")),
                      "f": bool(h.get("f")), "h": bool(h.get("human"))} for h in hist[-14:]]})
    out.sort(key=lambda x: -x["last"])
    return out[:500]


def update_client(key, d):
    """Kartadan tahrirlash: maydonlar, bosqich, izoh"""
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        f = c.setdefault("facts", {})
        for k, v in (d.get("fields") or {}).items():
            if k in EDIT_FIELDS:
                v = str(v or "").strip()[:300]
                if k == "name":
                    c["name"] = v
                if v:
                    f[k] = v
                else:
                    f.pop(k, None)
        st = d.get("stage")
        if st in dict(PIPE):
            if st in ("won", "lost"):
                old = c.get("deal") or {}
                c["deal"] = {"status": st, "amount": float(d.get("amount") or old.get("amount") or 0), "ts": time.time()}
            else:
                c.pop("deal", None)
                c["stage"] = st
        note = str(d.get("note") or "").strip()
        if note:
            c.setdefault("notes", []).append({"t": note[:1000], "ts": time.time()})
    core.save_chat(key)
    return True


def new_client(d):
    """Qo'lda mijoz qo'shish (telefon orqali kelgan, tanish va h.k.)"""
    name = str(d.get("name") or "").strip()[:100]
    phone = str(d.get("phone") or "").strip()[:40]
    if not (name or phone):
        return None
    key = "manual:" + str(int(time.time() * 1000))
    c = core.chat_state(key)
    with core.LOCK:
        c.update(channel="manual", name=name, created=time.time(), first_ts=time.time(), lead_sent=bool(phone), status="manual")
        c["facts"].update({k: str(d.get(k) or "").strip()[:300] for k in ("phone", "business", "need", "budget") if d.get(k)})
        if d.get("note"):
            c["notes"] = [{"t": str(d["note"])[:1000], "ts": time.time()}]
    core.save_chat(key)
    return key


def export_csv():
    """Barcha mijozlar — CSV (Excel ochadi) admin chatiga fayl bo'lib keladi"""
    import csv
    import io
    with core.LOCK:
        chats = json.loads(json.dumps(core.STATE["chats"]))
    rows = crm_list(chats)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Имя", "Username", "Телефон", "Канал", "Этап", "Сумма $", "Бизнес", "Что хочет", "Бюджет", "Удобное время",
                "Готовность %", "Первое сообщение", "Последнее", "Заметки", "Расход $"])
    fmt = lambda ts: datetime.fromtimestamp(ts, core.TZ).strftime("%d.%m.%Y %H:%M") if ts else ""
    stages = dict(PIPE)
    for x in rows:
        f = x["facts"]
        w.writerow([x["name"], x["username"], x["phone"], CH_NAMES.get(x["ch"], x["ch"]), stages.get(x["stage"], ""),
                    x["deal"].get("amount", "") if x["stage"] == "won" else "", f["business"], f["need"], f["budget"],
                    f["call_time"], x["readiness"], fmt(x["first"]), fmt(x["last"]),
                    " | ".join(n["t"] for n in x["notes"]), x["cost"]])
    data = ("\ufeff" + buf.getvalue()).encode("utf-8")
    name = "clients_" + datetime.now(core.TZ).strftime("%Y-%m-%d") + ".csv"
    body, ctype = core.STT._multipart({"chat_id": str(core.REPORT_CHAT_ID), "caption": f"📤 Клиенты: {len(rows)}"},
                                      "document", name, data, "text/csv")
    req = urllib.request.Request("https://api.telegram.org/bot" + core.BOT_TOKEN + "/sendDocument", data=body,
                                 method="POST", headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print("Export error:", e)
        return False


def set_bot(key, on):
    """Shu mijoz uchun botni to'xtatish / yoqish (qo'lda boshqaruv)"""
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        if on:
            c["bot_off"] = False
            c["paused_until"] = 0
            if c.get("status") in ("handoff", "stopped"):
                c["status"] = "active"
        else:
            c["bot_off"] = True
            c["paused_until"] = time.time() + 10 * 365 * 86400
    core.save_chat(key)
    return True


def history(key):
    with core.LOCK:
        c = core.STATE["chats"].get(key) or REMOTE["chats"].get(key) or {}
        return [{"r": h["r"], "t": h["t"].replace(core.STT.VOICE_PREFIX, "🎙 "), "ts": h.get("ts", 0), "v": bool(h.get("voice")),
                 "f": bool(h.get("f")), "h": bool(h.get("human"))} for h in c.get("history", [])]


def set_remind(key, ts, text=""):
    """Qo'ng'iroq eslatmasi: aniq vaqt + izoh. ts=0 — o'chirish"""
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        if not ts:
            c.pop("remind", None)
        else:
            c["remind"] = {"ts": float(ts), "text": str(text or "")[:500], "sent": False, "done": False, "created": time.time()}
    core.save_chat(key)
    return True


def set_deal(key, status, amount=0):
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        if status == "called":
            c["call"] = {"status": "done", "ts": time.time()}
            rm = c.get("remind") or {}
            if rm.get("ts") and rm["ts"] <= time.time():
                rm["done"] = True                    # muddati kelgan eslatma bajarildi
        elif status == "uncall":
            c.pop("call", None)
        elif status == "open":
            c.pop("deal", None)
        else:
            c["deal"] = {"status": status, "amount": float(amount or 0), "ts": time.time()}
    core.save_chat(key)
    return True

# --------------------------------------------------------------------------
# Telegram: matnli hisobot, menyu
# --------------------------------------------------------------------------
def text_summary(period="today"):
    d = build(period)
    t = d["totals"]
    title = period_label(d["period"])
    lines = [f"📊 {title}", ""]
    for ch in CHANNELS:
        f = d["funnel"][ch]
        lines.append(f"{CH_NAMES[ch]}: диалогов {d['proc'][ch]['dialogs']}, горячих {f['hot']}, "
                     f"контактов {f['lead']}, покупок {f['won']}, ИИ ${d['costs'][ch]['ai']:.3f}, "
                     f"голос {d['costs'][ch]['tts_chars']} кред.")
    lines += ["", f"Всего: диалогов {t['dialogs']}, контактов {t['leads']}, покупок {t['won']}, выручка ${t['revenue']:.0f}",
              f"Расходы: ИИ ${d['ai_total']:.2f} · голос ≈${d['tts_usd']:.2f} · сервер ${d['server']:.2f} → ${d['spend']:.2f}"]
    if t["leads"]:
        lines.append(f"Цена контакта ≈ ${t['per_lead']:.2f}")
    sub = d["eleven"]["sub"]
    if sub and sub.get("limit"):
        lines.append(f"ElevenLabs: {sub['used']:,} из {sub['limit']:,} кредитов".replace(",", " "))
    return "\n".join(lines)


COURSE_RX = [("Express 7", r"(?i)express ?7|экспресс ?7|ekspress ?7|7 ?кун|7 ?kun|7 ?дней"),
             ("Express 10", r"(?i)express ?10|экспресс ?10|ekspress ?10|10 ?кун|10 ?kun|10 ?дней"),
             ("VIP", r"(?i)\bvip\b|вип"),
             ("Полный курс «B»", r"(?i)(\bb\b|«b»|\bб\b) ?(toifa|тоифа|категор|kurs|курс)|noldan|нолдан|с нуля|haydash|ҳайдаш|хайдаш|вожден|prava|права"),
             ("Individual / Premium", r"(?i)individual|индивидуал|premium|премиум")]
BRANCH_NAMES = ["Nest One", "Ойбек", "Чиланзар", "Максим Горький"]


def staff_insights(period="30d"):
    """Xodim paneli va kunlik hisobot uchun: pulsiz tahlil (soatlar, kunlar, kurslar, filiallar, til, oldingi davr bilan solishtirish)"""
    period, start, days = period_range(period)
    end = min(period_end(days), time.time())
    span = max(3600.0, end - start)
    p0 = start - span
    with core.LOCK:
        chats = json.loads(json.dumps(core.STATE["chats"]))
    chats.update(json.loads(json.dumps(remote_ig_chats())))
    hours = [0] * 24
    week = [0] * 7
    courses = {n: 0 for n, _ in COURSE_RX}
    branches = {n: 0 for n in BRANCH_NAMES}
    lang = {"uz_lat": 0, "uz_cyr": 0, "ru": 0}
    voice = 0
    prev = {"dialogs": 0, "leads": 0, "hot": 0}
    cur_new_leads = []
    bw = getattr(core.AGENTS, "BRANCH_WORDS", [])
    for key, c in chats.items():
        ch = core.chat_channel(c)
        if ch not in CHANNELS:
            continue
        first = chat_first_ts(c)
        hist = c.get("history", [])
        if p0 <= first < start:
            fl = funnel_flags(c)
            prev["dialogs"] += 1
            prev["leads"] += int(fl["lead"])
            prev["hot"] += int(fl["hot"])
        for h in hist:
            if h["r"] == "u" and start <= (h.get("ts") or 0) < end:
                hours[datetime.fromtimestamp(h["ts"], core.TZ).hour] += 1
                voice += int(h["t"].startswith(core.STT.VOICE_PREFIX))
        if first < start or first >= end:
            continue
        week[datetime.fromtimestamp(first, core.TZ).weekday()] += 1
        text = " ".join(h["t"] for h in hist if h["r"] == "u")
        for n, rx in COURSE_RX:
            courses[n] += int(bool(re.search(rx, text)))
        for n, rx in zip(BRANCH_NAMES, bw):
            branches[n] += int(bool(re.search("(?i)" + rx, text)))
        sc = c.get("script") or ""
        if sc in lang:
            lang[sc] += 1
        if c.get("lead_sent"):
            f = c.get("facts") or {}
            cur_new_leads.append({"who": c.get("name") or "Клиент", "ch": ch, "ts": first,
                                  "want": (f.get("offer") or f.get("need") or "")[:80]})
    peak = max(range(24), key=lambda i: hours[i]) if any(hours) else None
    return {"hours": hours, "week": week, "peak": peak, "voice": voice, "lang": lang, "prev": prev,
            "courses": sorted(courses.items(), key=lambda x: -x[1]), "branches": sorted(branches.items(), key=lambda x: -x[1]),
            "recent_leads": sorted(cur_new_leads, key=lambda x: -x["ts"])[:6]}


def text_staff_digest():
    """Mijoz (Express) uchun kunlik hisobot — tokenlar, server va AI xarajatlarisiz"""
    d = build("today")
    ins = staff_insights("today")
    t, f, pr = d["totals"], d["funnel"], ins["prev"]
    hot = sum(f[c]["hot"] for c in f)
    def delta(a, b):
        return "" if not b and not a else (" ↑" + str(a - b) if a > b else (" ↓" + str(b - a) if a < b else " ="))
    name = core.AGENTS.name(core.AGENT_MODE) if core.AGENT_MODE else "Итоги"
    lines = [f"📊 {name} — итоги дня {datetime.now(core.TZ).strftime('%d.%m')}", "",
             f"💬 Новых диалогов: {t['dialogs']}{delta(t['dialogs'], pr['dialogs'])}",
             f"   Telegram {d['proc']['tg']['dialogs']} · Instagram {d['proc']['ig']['dialogs']}",
             f"📞 Оставили номер: {t['leads']}{delta(t['leads'], pr['leads'])} · конверсия {round(100 * t['leads'] / t['dialogs']) if t['dialogs'] else 0}%",
             f"🔥 Горячих: {hot} · ✅ Записались: {t['won']}"]
    top_c = [f"{n} {v}" for n, v in ins["courses"] if v][:3]
    if top_c:
        lines.append("🎯 Спрашивали: " + ", ".join(top_c))
    top_b = [f"{n} {v}" for n, v in ins["branches"] if v][:3]
    if top_b:
        lines.append("📍 Филиалы: " + ", ".join(top_b))
    if ins["peak"] is not None:
        lines.append(f"⏰ Больше всего писали в {ins['peak']:02d}:00–{(ins['peak'] + 1) % 24:02d}:00")
    calls = [x for x in d["calls"] if x["todo"]]
    if calls:
        lines.append(f"\n📲 Позвонить ({len(calls)}):")
        lines += [f"• {x['who']} {x['phone']}" + (f" — {x['want'][:80]}" if x.get("want") else "") for x in calls[:10]]
    elif t["dialogs"]:
        lines.append("\n👍 Всем, кто оставил номер, уже позвонили.")
    lines.append("\n↑/↓ — по сравнению со вчера")
    return "\n".join(lines)


CRMSTATS = {}


def crm_hook(slug):
    """Mijoz agentining CRM havolasi (asosiy bot jadvalida). Alohida botda ham o'qiladi."""
    try:
        if core.AGENT_MODE and MAIN_DB_TABLE and MAIN_DB_TABLE != core.DB_TABLE:
            if core.db_connect() is None:
                return ""
            with core.DB_LOCK:
                rows = core.DB.run("SELECT v FROM " + MAIN_DB_TABLE + " WHERE k = :k", k="crmhook:" + slug)
            return ((json.loads(rows[0][0]) if rows else {}) or {}).get("url") or ""
        return (core.db_get("crmhook:" + slug) or {}).get("url") or ""
    except Exception as e:
        print("CRM hook read error:", e)
        return ""


def crm_stats(slug, period):
    """CRM'dagi lidlarni qayta ishlash tahlili (tezlik, dozvon, yozilish) — panel uchun, 60 s kesh"""
    key = (slug, period)
    hit = CRMSTATS.get(key)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    url = crm_hook(slug)
    out = None
    if url:
        try:
            p, start, days = period_range(period)
            frm = datetime.fromtimestamp(start, core.TZ).isoformat()
            to = datetime.fromtimestamp(period_end(days), core.TZ).isoformat()
            u = url.replace("/api/hook?", "/api/hook/stats?") + "&" + urllib.parse.urlencode({"from": frm, "to": to})
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "aib-bot"}), timeout=6) as r:
                out = json.loads(r.read().decode())
        except Exception as e:
            print("CRM stats error:", e)
    CRMSTATS[key] = (time.time(), out)
    return out


def text_leads():
    d = build("30d")
    top = [x for x in d["leads"] if x["lvl"] >= 4][:10]
    if not top:
        return "Горячих клиентов и контактов за 30 дней пока нет."
    lines = ["🔥 Горячие и контакты (30 дней):"]
    for x in top:
        ph = x["facts"].get("phone", "")
        lines.append(f"• {x['who']} [{CH_NAMES[x['ch']]}] — {x['stage']}, {x['readiness']}%"
                     + (f", {ph}" if ph else "") + (f" — {x['facts'].get('business')}" if x['facts'].get('business') else ""))
    return "\n".join(lines)


def panel_url():
    return core.IG.PUBLIC_URL + "/admin"


def panel_button(chat_id):
    core.tg("sendMessage", {"chat_id": chat_id, "text": "Панель управления 👇",
                            "reply_markup": {"inline_keyboard": [[{"text": "📊 Открыть панель", "web_app": {"url": panel_url()}}]]}})


def staff_panel(chat_id):
    """Xodimga lidlar paneli: tugma + chatdagi 'Лиды' menyu tugmasi"""
    core.tg("setChatMenuButton", {"chat_id": int(chat_id), "menu_button": {"type": "web_app", "text": "Лиды",
                                                                           "web_app": {"url": panel_url()}}})
    core.tg("sendMessage", {"chat_id": chat_id, "text": "📋 Лиды и клиенты — в панели 👇 (также кнопка «Лиды» слева от поля ввода)",
                            "reply_markup": {"inline_keyboard": [[{"text": "📋 Открыть лиды", "web_app": {"url": panel_url()}}]]}})


COMMANDS = [("crm", "🖥 CRM: открыть на компьютере / в браузере"), ("agents", "🤖 Агенты клиентов и тест"), ("panel", "📊 Панель: звонки, расходы, воронка, лиды"), ("stats", "Сводка за сегодня"),
            ("leads", "Горячие клиенты и контакты"), ("rules", "Мои указания продавцу"),
            ("test", "Тест: написать боту как клиент"), ("digest", "Отчёт за день сейчас"),
            ("notify", "Уведомления: все диалоги / только горячие"),
            ("voice", "Голос бота: пример и стиль"), ("voices", "Сменить голос: узбекские голоса"), ("month", "Сводка за месяц"),
            ("cost", "Расход на ИИ"), ("eval", "Проверка качества ответов"), ("ig", "Instagram аккаунты")]


def setup_menu():
    """Faqat admin chatida: buyruqlar menyusi va 'Панель' tugmasi"""
    try:
        admin = int(core.REPORT_CHAT_ID)
    except Exception:
        return
    core.tg("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS],
                              "scope": {"type": "chat", "chat_id": admin}})
    core.tg("setChatMenuButton", {"chat_id": admin, "menu_button": {"type": "web_app", "text": "Панель",
                                                                     "web_app": {"url": panel_url()}}})


def command(chat_id, text):
    """Admin buyruqlari. True — bajarildi"""
    if str(chat_id) != str(core.REPORT_CHAT_ID):
        return False
    cmd = text.split()[0].split("@")[0].lower()
    if cmd == "/panel":
        panel_button(chat_id)
    elif cmd == "/crm":
        url = core.IG.PUBLIC_URL + "/crm/login?t=" + core.BILL.new_login_token()
        core.tg("sendMessage", {"chat_id": chat_id, "text": "🖥 Вход в CRM. Ссылка одноразовая и действует 10 минут, "
                                "после входа браузер запомнит вас на 30 дней.\n\nОткройте на компьютере или телефоне 👇",
                                "reply_markup": {"inline_keyboard": [[{"text": "Открыть CRM", "url": url}]]}})
    elif cmd == "/crm_pass":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            core.send_msg(chat_id, "Напишите так: /crm_pass ваш_пароль (минимум 4 символа)")
        elif core.BILL.set_password(parts[1]):
            core.send_msg(chat_id, "✅ Пароль для CRM установлен. Вход: " + core.IG.PUBLIC_URL + "/crm\n"
                                   "Удалите сообщение с паролем из этого чата.")
        else:
            core.send_msg(chat_id, "Пароль слишком короткий — минимум 4 символа.")
    elif cmd in ("/agents", "/agent_owner", "/agent_report", "/agent_ig"):
        core.send_msg(chat_id, core.AGENTS.admin_command(text))
    elif cmd == "/crm_hook":
        parts = text.split()
        if len(parts) < 3 or parts[1] not in core.AGENTS.agents():
            core.send_msg(chat_id, "Формат: /crm_hook <код агента> <ссылка из CRM → Доступы → Ключ для бота> (или off). "
                                   "Агенты: " + ", ".join(core.AGENTS.agents()))
        elif parts[2].lower() == "off":
            core.db_put("crmhook:" + parts[1], {"url": ""})
            CRMSTATS.clear()
            core.send_msg(chat_id, "CRM для " + parts[1] + " отключена.")
        elif not parts[2].startswith("https://") or "/api/hook" not in parts[2] or "key=" not in parts[2]:
            core.send_msg(chat_id, "Это не похоже на ссылку из CRM. Нужна ссылка вида https://…/api/hook?key=…")
        else:
            core.db_put("crmhook:" + parts[1], {"url": parts[2], "set": time.time()})
            CRMSTATS.clear()
            core.send_msg(chat_id, f"✅ CRM подключена к агенту {core.AGENTS.name(parts[1])}. "
                                   "Заявки (оставили номер) за последние 60 дней и все новые будут приходить туда в течение минуты.\n"
                                   "Удалите сообщение со ссылкой из этого чата — в ней ключ.")
    elif cmd == "/stats":
        core.send_msg(chat_id, text_summary("today"))
    elif cmd == "/month":
        core.send_msg(chat_id, text_summary("month"))
    elif cmd == "/leads":
        core.send_msg(chat_id, text_leads())
    else:
        return False
    return True

# --------------------------------------------------------------------------
# ИИ-клиенты: har bir mijoz-agent bo'yicha alohida hisobot (dialoglar, AI, ElevenLabs, server)
# --------------------------------------------------------------------------
AIC_PERIODS = [("7d", "Неделя"), ("month", "Этот месяц"), ("quarter", "Квартал"), ("all", "Всё время")]
AIC_SERVER_DEFAULT = float(os.environ.get("AGENT_SERVER_USD", "5"))   # alohida bot (Railway servisi), $/oy


def aic_server():
    return core.db_get("aiclients:server") or {}


def set_aic_server(slug, usd):
    if not core.AGENTS.get(slug):
        return False
    v = aic_server()
    v[slug] = max(0.0, round(float(usd), 2))
    return core.db_put("aiclients:server", v)


def ai_clients(period="month"):
    today = datetime.now(core.TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "all":
        start, t1 = None, today.strftime("%Y-%m-%d")
    else:
        period, st0, dd = period_range(period)
        start, t1 = datetime.fromtimestamp(st0, core.TZ), dd[-1]
    t0 = start.strftime("%Y-%m-%d") if start else "0000"
    sub = eleven_subscription()
    usd_per_credit = ELEVEN_PLAN_USD / max(1, (sub or {}).get("limit") or ELEVEN_PLAN_CREDITS)
    with core.LOCK:
        stats = json.loads(json.dumps(core.STATS))
        chats = json.loads(json.dumps(list(core.STATE["chats"].values())))
    srv = aic_server()
    out = []
    for slug, a in core.AGENTS.agents().items():
        ch = "agent:" + slug
        days = {}
        blank = lambda: {"tg": 0, "ig": 0, "leads": 0, "ai": 0.0, "tts": 0, "stt": 0}
        for d, chs in stats.items():                     # shu botda (Instagram / Business) sarflangan
            x = chs.get(ch)
            if x:
                y = days.setdefault(d, blank())
                y["ai"] += x.get("ai_usd", 0)
                y["tts"] += x.get("tts_chars", 0)
                y["stt"] += x.get("stt_sec", 0)
        for c in chats:
            if core.chat_channel(c) != ch:
                continue
            first = chat_first_ts(c)
            if not first:
                continue
            y = days.setdefault(datetime.fromtimestamp(first, core.TZ).strftime("%Y-%m-%d"), blank())
            y["ig" if c.get("channel") == "ig" else "tg"] += 1
            y["leads"] += int(bool(c.get("lead_sent")))
        remote = core.db_get("agentstats:" + slug) or {}     # mijozning alohida boti (Telegram)
        for d, v in (remote.get("days") or {}).items():
            y = days.setdefault(d, blank())
            y["tg"] += int(v.get("dialogs", 0))
            y["leads"] += int(v.get("leads", 0))
            y["ai"] += float(v.get("ai", 0))
            y["tts"] += int(v.get("tts", 0))
            y["stt"] += int(v.get("stt", 0))
        if not days and not a.get("own_bot"):
            continue
        first_day = min(days) if days else t1
        d0 = max(t0, first_day)
        sel = {d: v for d, v in days.items() if d0 <= d <= t1}
        dd = datetime.strptime(d0, "%Y-%m-%d")
        span = []
        while dd.strftime("%Y-%m-%d") <= t1:
            span.append(dd.strftime("%Y-%m-%d"))
            dd += timedelta(days=1)
        n_days = len(span)
        server_m = float(srv.get(slug, AIC_SERVER_DEFAULT if a.get("own_bot") else 0))
        tot = {k: sum(v[k] for v in sel.values()) for k in ("tg", "ig", "leads", "ai", "tts", "stt")}
        tts_usd = tot["tts"] * usd_per_credit
        server = server_m * n_days / 30.0
        spend = tot["ai"] + tts_usd + server
        dialogs = tot["tg"] + tot["ig"]
        wk = [0] * 7
        for d, v in sel.items():
            wk[datetime.strptime(d, "%Y-%m-%d").weekday()] += v["tg"] + v["ig"]
        out.append({"slug": slug, "company": a.get("company") or slug, "crm": crm_stats(slug, period) if period != "all" else crm_stats(slug, "year"), "own_bot": bool(a.get("own_bot")),
                    "ig": bool(a.get("ig_tenant")), "since": first_day, "days": n_days,
                    "dialogs": dialogs, "tg": tot["tg"], "ig_dialogs": tot["ig"], "leads": tot["leads"],
                    "ai": round(tot["ai"], 3), "tts_chars": tot["tts"], "tts_usd": round(tts_usd, 3),
                    "stt_min": round(tot["stt"] / 60, 1), "server": round(server, 2), "server_m": server_m,
                    "spend": round(spend, 2), "per_dialog": round(spend / dialogs, 3) if dialogs else 0,
                    "per_lead": round(spend / tot["leads"], 2) if tot["leads"] else 0, "weekday": wk,
                    "updated": remote.get("updated", 0),
                    "daily": [{"d": d, "tg": (sel.get(d) or {}).get("tg", 0), "ig": (sel.get(d) or {}).get("ig", 0),
                               "cost": round((sel.get(d) or {}).get("ai", 0) + (sel.get(d) or {}).get("tts", 0) * usd_per_credit, 3)}
                              for d in span[-120:]]})
    out.sort(key=lambda x: -x["dialogs"])
    return {"period": period, "label": period_label(period) if period != "all" else "Всё время", "items": out}

# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def handle_get(h):
    path = urllib.parse.urlparse(h.path).path.rstrip("/")
    if path == "/crm" or path.startswith("/crm/"):
        return core.CRMWEB.handle_get(h)
    if path == "/admin":
        core.IG.respond_html(h, 200, PAGE, headers={"Cache-Control": "no-store"})
        return True
    if path == "/admin/api/aiclients":
        if role(h) != "admin" or core.AGENT_MODE:
            core.IG.respond_html(h, 403, '{"error":"forbidden"}', ctype="application/json")
            return True
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        core.IG.respond_html(h, 200, json.dumps(ai_clients((q.get("period") or ["month"])[0]), ensure_ascii=False),
                             ctype="application/json; charset=utf-8", headers={"Cache-Control": "no-store"})
        return True
    if path == "/admin/api":
        r = role(h)
        if not r:
            core.IG.respond_html(h, 403, '{"error":"forbidden"}', ctype="application/json")
            return True
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        data = build((q.get("period") or ["30d"])[0])
        data = staff_view(data) if (r == "staff" or core.AGENT_MODE) else dict(data, role="admin")
        core.IG.respond_html(h, 200, json.dumps(data, ensure_ascii=False), ctype="application/json; charset=utf-8",
                             headers={"Cache-Control": "no-store"})
        return True
    return False


def handle_post(h, body):
    path = urllib.parse.urlparse(h.path).path.rstrip("/")
    if path in ("/crm/code", "/crm/verify", "/crm/pass"):
        return core.CRMWEB.handle_post(h, body)
    if path not in ("/admin/api/deal", "/admin/api/remind", "/admin/api/client", "/admin/api/new", "/admin/api/export",
                    "/admin/api/expense", "/admin/api/bot", "/admin/api/history", "/admin/api/pay", "/admin/api/price",
                    "/admin/api/sub", "/admin/api/rule", "/admin/api/voice", "/admin/api/aicserver"):
        return False
    r = role(h)
    if not r or (r == "staff" and path not in STAFF_POST):
        core.IG.respond_html(h, 403, '{"error":"forbidden"}', ctype="application/json")
        return True
    try:
        d = json.loads(body or b"{}")
        if r == "staff":
            d.pop("amount", None)                # xodim summa kiritmaydi
            if isinstance(d.get("fields"), dict):
                d["fields"].pop("budget", None)
        if path == "/admin/api/remind":
            ok = set_remind(str(d.get("key")), float(d.get("ts") or 0), d.get("text", ""))
        elif path == "/admin/api/client":
            ok = update_client(str(d.get("key")), d)
        elif path == "/admin/api/new":
            ok = new_client(d)
        elif path == "/admin/api/export":
            ok = export_csv()
        elif path == "/admin/api/pay":
            ok = core.BILL.del_payment(str(d.get("key")), d["delete"]) if d.get("delete") else core.BILL.add_payment(str(d.get("key")), d)
        elif path == "/admin/api/price":
            ok = core.BILL.set_price(str(d.get("key")), d.get("price"))
        elif path == "/admin/api/sub":
            ok = core.BILL.sub_action(d)
        elif path == "/admin/api/rule":
            ok = core.BOSS.del_rule(int(d["delete"])) if d.get("delete") else core.BOSS.add_rule(str(d.get("text") or ""))
        elif path == "/admin/api/aicserver":
            ok = set_aic_server(str(d.get("slug")), d.get("usd") or 0)
        elif path == "/admin/api/voice":
            ok = core.BOSS.set_voice_mode(str(d.get("mode") or ""))
        elif path == "/admin/api/bot":
            ok = set_bot(str(d.get("key")), bool(d.get("on")))
        elif path == "/admin/api/history":
            core.IG.respond_html(h, 200, json.dumps({"ok": True, "items": history(str(d.get("key")))}, ensure_ascii=False),
                                 ctype="application/json; charset=utf-8")
            return True
        elif path == "/admin/api/expense":
            if d.get("delete"):
                ok = del_expense(d["delete"])
            elif d.get("stop"):
                ok = stop_recurring(d["stop"])
            elif d.get("daily") or d.get("freq") in ("daily", "monthly"):
                ok = add_recurring(dict(d, freq=d.get("freq") or "daily"))
            elif d.get("update_rec"):
                ok = update_recurring(d["update_rec"], d)
            else:
                ok = add_expense(d)
        else:
            ok = d.get("status") in ("won", "lost", "open", "called", "uncall") and set_deal(str(d.get("key")), d["status"], d.get("amount"))
    except Exception:
        ok = False
    core.IG.respond_html(h, 200 if ok else 400, json.dumps({"ok": bool(ok), **({"key": ok} if isinstance(ok, str) else {})}),
                         ctype="application/json")
    return True


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>AI Business — панель</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:var(--tg-theme-bg-color,#fff);--bg2:var(--tg-theme-secondary-bg-color,#f2f3f5);--tx:var(--tg-theme-text-color,#111);
--mut:var(--tg-theme-hint-color,#8a8f98);--ac:var(--tg-theme-button-color,#2a7de1);--act:var(--tg-theme-button-text-color,#fff);
--tg:#2a9fd8;--ig:#d6337a;--ok:#2e9e5b;--bad:#d9534f;--warn:#e69a28}
*{box-sizing:border-box}body{margin:0;background:var(--bg2);color:var(--tx);font:15px/1.4 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg2);
 padding:calc(10px + var(--tg-safe-area-inset-top,0px) + var(--tg-content-safe-area-inset-top,0px)) 12px 6px}
main{padding-bottom:calc(40px + var(--tg-safe-area-inset-bottom,0px)) !important}
.sheet{padding-bottom:calc(28px + var(--tg-safe-area-inset-bottom,0px)) !important}
@media(min-width:700px){main,header{max-width:920px;margin:0 auto}.kpis{grid-template-columns:repeat(3,1fr)}}
.chips,.tabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}.chips::-webkit-scrollbar,.tabs::-webkit-scrollbar{display:none}
.chip{border:0;border-radius:16px;padding:6px 12px;background:var(--bg);color:var(--tx);font:inherit;font-size:13px;white-space:nowrap}
.chip.on{background:var(--ac);color:var(--act)}
.tabs{margin-top:8px}.tab{flex:1 0 auto;white-space:nowrap;font-size:14px !important;border:0;background:none;color:var(--mut);font:inherit;font-weight:600;padding:6px 4px;border-bottom:2px solid transparent}
.tab.on{color:var(--tx);border-color:var(--ac)}
main{padding:4px 12px 40px}.card{background:var(--bg);border-radius:14px;padding:12px 14px;margin:10px 0}
h3{margin:0 0 8px;font-size:15px}.mut{color:var(--mut);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.kpi{background:var(--bg);border-radius:14px;padding:10px 12px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.kpi span{color:var(--mut);font-size:12px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{padding:6px 2px;text-align:right;font-size:13px}
td:first-child,th:first-child{text-align:left}th{color:var(--mut);font-weight:500}tr+tr td{border-top:1px solid var(--bg2)}
.tot td{font-weight:700}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
.fn{margin:6px 0}.fn .l{display:flex;justify-content:space-between;font-size:13px}.bar{height:8px;border-radius:4px;background:var(--bg2);overflow:hidden;display:flex}
.bar i{display:block;height:100%}
.chart{display:flex;align-items:flex-end;gap:2px;height:90px;margin-top:6px}.chart div{flex:1;display:flex;flex-direction:column-reverse;min-width:3px}
.chart i{display:block;width:100%}.axis{display:flex;justify-content:space-between;color:var(--mut);font-size:11px;margin-top:4px}
.lead{background:var(--bg);border-radius:14px;padding:10px 12px;margin:8px 0}.lead .top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.xbtn{border:0;background:var(--bg2);color:var(--tx);border-radius:50%;width:32px;height:32px;font-size:16px;flex:none}
.badge{font-size:12px;padding:2px 8px;border-radius:10px;background:var(--bg2);white-space:nowrap}
.b6{background:#2e9e5b22;color:var(--ok)}.b5{background:#e69a2822;color:var(--warn)}.b4{background:#d9534f22;color:var(--bad)}.b-1{opacity:.6}
.cst{background:var(--bg2);border-radius:10px;padding:6px 8px;margin-bottom:6px}.det{display:none;margin-top:8px;font-size:13px}.lead.open .det{display:block}
.msg{margin:3px 0;padding:5px 8px;border-radius:10px;background:var(--bg2);max-width:92%}.msg.a{margin-left:auto;background:#2a7de11a}
.btns{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}.btns button,.btns input{font:inherit;font-size:13px;border-radius:10px;border:0;padding:7px 10px}
.btns input{width:90px;background:var(--bg2);color:var(--tx)}.won{background:var(--ok);color:#fff}.lost{background:var(--bg2);color:var(--tx)}
.call{background:var(--bg);border-radius:14px;padding:10px 12px;margin:8px 0}.call.done{opacity:.6}
.call .top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.want{margin:6px 0 2px}
.tel{white-space:nowrap;text-decoration:none;background:var(--ok);color:#fff;border-radius:10px;padding:6px 10px;font-size:14px}
.lnk{text-decoration:none;font-size:13px;border-radius:10px;padding:7px 10px}
#modal{display:none;position:fixed;inset:0;z-index:20;background:rgba(0,0,0,.45);align-items:flex-end;justify-content:center}
.sheet{background:var(--bg);width:100%;max-width:520px;border-radius:18px 18px 0 0;padding:16px 16px 28px;max-height:90vh;overflow:auto}
.bignum{font-size:28px;font-weight:700;margin:6px 0;font-variant-numeric:tabular-nums;letter-spacing:.5px}
.bigbtn{display:block;width:100%;text-align:center;border:0;border-radius:12px;padding:13px;margin:6px 0;font:inherit;font-weight:600;
 background:var(--ok);color:#fff;text-decoration:none}.bigbtn.sec{background:var(--bg2);color:var(--tx)}
.sheet input[type=datetime-local],.sheet textarea{width:100%;font:inherit;border:0;border-radius:10px;padding:10px;background:var(--bg2);color:var(--tx);margin:4px 0}
.rem{margin:6px 0 0;padding:6px 8px;border-radius:10px;background:var(--bg2);font-size:13px}.rem.due{background:#e69a2833;color:var(--warn);font-weight:600}
button.tel{border:0;font:inherit}
.search{width:100%;font:inherit;border:0;border-radius:12px;padding:10px 12px;background:var(--bg);color:var(--tx)}
.small{font-size:13px;margin-top:3px}.fl{display:block;margin-top:10px;font-size:12px}
.fi{width:100%;font:inherit;border:0;border-radius:10px;padding:9px 10px;background:var(--bg2);color:var(--tx);margin-top:3px}
.chips.wrap{flex-wrap:wrap;overflow:visible}.chips.wrap .chip{background:var(--bg2)}.chips.wrap .chip.on{background:var(--ac);color:var(--act)}
tr.sub td{border-top:0;padding-top:0;color:var(--mut);font-size:12px;text-align:left}
select.fi{appearance:auto}
.botbar{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:10px;padding:8px 10px;border-radius:12px;background:#2e9e5b1a;font-size:13px}
.botbar.off{background:#d9534f1f}.botbar button{border:0;border-radius:10px;padding:7px 10px;font:inherit;font-size:13px;white-space:nowrap}
.note{background:var(--bg2);border-radius:10px;padding:6px 8px;margin:4px 0;font-size:13px}
.lead[data-open],.call[data-open]{cursor:pointer}
.st-new{background:#d9534f22;color:var(--bad)}.st-work{background:#2a7de122;color:var(--ac)}.st-offer,.st-pay{background:#e69a2822;color:var(--warn)}
.st-won{background:#2e9e5b22;color:var(--ok)}.st-lost{opacity:.6}
.cnt{display:inline-block;min-width:18px;padding:0 5px;border-radius:9px;background:var(--bad);color:#fff;font-size:11px;line-height:18px}
.filters{display:flex;gap:6px;margin-top:4px}.hidden{display:none}
#err{display:none;padding:30px 16px;text-align:center}
@media(min-width:700px){#per{flex-wrap:wrap}}
#per .chip.on{box-shadow:0 2px 8px #2a7de155}
.hero{border-radius:18px;padding:16px;margin:8px 0 10px;color:#fff;background:linear-gradient(135deg,#1f6fd6 0%,#7b3fe4 55%,#d6337a 100%);box-shadow:0 6px 20px #1f6fd633}
.hero h2{margin:0;font-size:19px}.hero .sub{opacity:.85;font-size:13px;margin-top:2px}
.hero .big{display:flex;gap:18px;margin-top:12px;flex-wrap:wrap}.hero .big div b{display:block;font-size:30px;line-height:1.1;font-variant-numeric:tabular-nums}
.hero .big div span{font-size:12px;opacity:.85}
.kc{border-radius:16px;padding:12px;position:relative;overflow:hidden;background:var(--bg)}
.kc b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.kc span{font-size:12px;color:var(--mut)}
.kc:before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:var(--c)}
.kc .ic{position:absolute;right:10px;top:10px;font-size:20px;opacity:.9}
.dl{font-size:12px;font-weight:600;margin-left:4px}.dl.up{color:var(--ok)}.dl.dn{color:var(--bad)}
.donut{width:118px;height:118px;border-radius:50%;flex:none;display:grid;place-items:center}
.donut>div{width:78px;height:78px;border-radius:50%;background:var(--bg);display:grid;place-items:center;text-align:center;font-size:12px;color:var(--mut)}
.donut>div b{display:block;font-size:20px;color:var(--tx)}
.split{display:flex;gap:16px;align-items:center}.leg div{display:flex;align-items:center;gap:6px;margin:6px 0;font-size:14px}.leg b{margin-left:auto;padding-left:10px}
.fnl{margin:8px 0}.fnl .l{display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px}
.fnl .t{height:26px;border-radius:8px;background:var(--bg2);overflow:hidden}.fnl .t i{display:flex;align-items:center;height:100%;border-radius:8px;color:#fff;font-size:12px;font-weight:600;padding-left:8px;white-space:nowrap}
.hrs{display:grid;grid-template-columns:repeat(24,1fr);gap:2px;margin-top:6px}.hrs i{height:30px;border-radius:4px}
.hax{display:flex;justify-content:space-between;color:var(--mut);font-size:10px;margin-top:3px}
.tagb{display:flex;align-items:center;gap:8px;margin:7px 0;font-size:14px}.tagb .n{width:46%;flex:none}.tagb .t{flex:1;height:10px;border-radius:5px;background:var(--bg2);overflow:hidden}
.tagb .t i{display:block;height:100%;border-radius:5px}.tagb b{width:28px;text-align:right}
.wl{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 0}.wl+.wl{border-top:1px solid var(--bg2)}
.pill{font-size:11px;padding:2px 7px;border-radius:8px;color:#fff}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:8px}@media(min-width:700px){.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}}
.stack{height:14px;border-radius:7px;overflow:hidden;display:flex;background:var(--bg2);margin:8px 0}.stack i{display:block;height:100%}
.cline{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:14px}.cline .sw{width:10px;height:10px;border-radius:3px;flex:none}.cline b{margin-left:auto}
.hero.cost{background:linear-gradient(135deg,#0f766e 0%,#1f6fd6 60%,#4338ca 100%)}

</style></head><body>
<header>
 <div class="chips" id="per"></div>
 <div class="tabs" id="tabs"></div>
</header>
<main id="app"><p class="mut" style="padding:20px">Загрузка…</p></main>
<div id="err"></div>
<div id="modal"></div>
<script>
const tg=window.Telegram&&Telegram.WebApp;
if(tg){tg.ready();tg.expand();
 try{if(tg.isVersionAtLeast&&tg.isVersionAtLeast("8.0")){tg.requestFullscreen();}}catch(e){}      // на весь экран (телефон и компьютер)
 try{tg.disableVerticalSwipes&&tg.disableVerticalSwipes();}catch(e){}                              // свайп вниз не закрывает панель
}
const INIT=tg?tg.initData:"";
const PER=[["today","Сегодня"],["yesterday","Вчера"],["7d","7 дней"],["30d","30 дней"],["month","Этот месяц"],["lastmonth","Прошлый месяц"],["quarter","Квартал"],["year","Год"],["all","Всё время"]];
const fmtD=x=>x.slice(8,10)+"."+x.slice(5,7)+"."+x.slice(2,4);
const perLabel=p=>{if(String(p).startsWith("c:")){const[a,b]=p.slice(2).split(":");return a==b?fmtD(a):fmtD(a)+" – "+fmtD(b)}const f=PER.find(x=>x[0]==p);return f?f[1]:p};
const isoD=t=>{const d=new Date(t);return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")};
function customPer(){
 const c=String(st.per).startsWith("c:")?st.per.slice(2).split(":"):[isoD(Date.now()-6*864e5),isoD(Date.now())];
 const q=(n,a,b)=>`<button class="chip" style="background:var(--bg2)" data-qr="${a}:${b}">${n}</button>`;
 const D=k=>isoD(Date.now()-k*864e5);
 modal(`<b style="font-size:17px">📅 Свой период</b><div class="mut">Выберите даты «с» и «по» — включительно.</div>
  <label class="fl">С</label><input id="pf" class="fi" type="date" value="${c[0]}" max="${isoD(Date.now())}">
  <label class="fl">По</label><input id="pt" class="fi" type="date" value="${c[1]}" max="${isoD(Date.now())}">
  <div class="chips wrap" style="margin-top:10px">${q("14 дней",D(13),D(0))}${q("60 дней",D(59),D(0))}${q("90 дней",D(89),D(0))}${q("Прошлая неделя",D(new Date().getDay()==0?13:new Date().getDay()+6),D(new Date().getDay()==0?7:new Date().getDay()))}</div>
  <button class="bigbtn" data-applyper>Показать</button><button class="bigbtn sec" data-close>Отмена</button>`);
}
let TABS=[["calls","Звонки"],["crm","Клиенты"],["fin","Финансы"],["ov","Обзор"],["fn","Воронка"],["cost","Бот"],["aic","ИИ-клиенты"]];
const STAFF=()=>st.data&&st.data.role=="staff";
const COL={tg:"var(--tg)",ig:"var(--ig)",manual:"#8a8f98"};
let st={per:"month",tab:"calls",data:null,lf:"hot",q:"",sf:"active",qfocus:false,ap:"month",aic:null};
try{const s=JSON.parse(localStorage.getItem("adm")||"{}");Object.assign(st,{per:s.per||st.per,tab:s.tab||st.tab})}catch(e){}
const $=s=>document.querySelector(s);
const money=(v,d=2)=>"$"+Number(v||0).toFixed(d);
const pct=(a,b)=>b?Math.round(100*a/b)+"%":"—";
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const when=ts=>{if(!ts)return"";const d=new Date(ts*1000);return d.toLocaleDateString("ru",{day:"2-digit",month:"2-digit"})+" "+d.toLocaleTimeString("ru",{hour:"2-digit",minute:"2-digit"})};
function save(){try{localStorage.setItem("adm",JSON.stringify({per:st.per,tab:st.tab}))}catch(e){}}
function chips(){
 const cu=String(st.per).startsWith("c:");
 $("#per").innerHTML=PER.map(([k,n])=>`<button class="chip ${st.per==k?"on":""}" data-p="${k}">${n}</button>`).join("")+
  `<button class="chip ${cu?"on":""}" data-custom>📅 ${cu?perLabel(st.per):"Свой период"}</button><button class="chip" data-p="re">↻</button>`;
 const on=$("#per .chip.on");if(on&&!st.perScrolled){st.perScrolled=1;on.scrollIntoView({inline:"center",block:"nearest"});}
 const todo=st.data?st.data.calls.filter(x=>x.todo).length:0;
 $("#tabs").innerHTML=TABS.map(([k,n])=>`<button class="tab ${st.tab==k?"on":""}" data-t="${k}">${n}${k=="calls"&&todo?` <span class="cnt">${todo}</span>`:""}</button>`).join("");
}
document.addEventListener("input",e=>{if(e.target.id=="q"){st.q=e.target.value;st.qfocus=true;render();}});
document.addEventListener("click",e=>{
 if(e.target.closest("[data-custom]")){customPer();return;}
 const qr=e.target.closest("[data-qr]");if(qr){const[a,b]=qr.dataset.qr.split(":");$("#pf").value=a;$("#pt").value=b;return;}
 if(e.target.closest("[data-applyper]")){const a=$("#pf").value,b=$("#pt").value;if(a&&b){st.per="c:"+(a<b?a+":"+b:b+":"+a);st.aic=null;closeModal();save();load();}return;}
 const p=e.target.closest("[data-p]"),t=e.target.closest("[data-t]"),l=e.target.closest(".lead .top"),f=e.target.closest("[data-lf]"),dl=e.target.closest("[data-deal]");
 if(p){if(p.dataset.p!="re")st.per=p.dataset.p;save();load();}
 if(t){st.tab=t.dataset.t;save();chips();render();}
 if(f){st.lf=f.dataset.lf;render();}
 if(l){l.parentElement.classList.toggle("open");}
 if(dl){const box=dl.closest(".lead,.call");deal(dl.dataset.key,dl.dataset.deal,box&&box.querySelector("input[type=number]"));closeModal();}
 const cb=e.target.closest("[data-call]");if(cb)openCall(cb.dataset.call);
 const rb=e.target.closest("[data-rem]");if(rb)openRemind(rb.dataset.rem);
 if(e.target.closest("[data-close]")||e.target.id=="modal")closeModal();
 const cp=e.target.closest("[data-copy]");if(cp){try{navigator.clipboard.writeText(cp.dataset.copy);cp.textContent="✓ Скопировано"}catch(_){}}
 const qs=e.target.closest("[data-quick]");if(qs){const dt=new Date(Date.now()+Number(qs.dataset.quick)*60000);if(qs.dataset.quick=="tm"){dt.setTime(Date.now()+864e5);dt.setHours(10,0,0,0)}
  const i=$("#rem-dt");if(i)i.value=localDT(dt);}
 const sv=e.target.closest("[data-saverem]");if(sv)saveRemind(sv.dataset.saverem,false);
 const oc=e.target.closest("[data-open]");if(oc&&!e.target.closest("button,a,input,textarea,select"))openClient(oc.dataset.open);
 const sf=e.target.closest("[data-sf]");if(sf){st.sf=sf.dataset.sf;render();}
 const sg=e.target.closest("[data-stage]");if(sg){$("#cl").dataset.stage=sg.dataset.stage;document.querySelectorAll("[data-stage]").forEach(b=>b.classList.toggle("on",b==sg));
  const a=$("#cl-amt");if(a)a.style.display=sg.dataset.stage=="won"?"block":"none";}
 const sc=e.target.closest("[data-saveclient]");if(sc)saveClient(sc.dataset.saveclient);
 if(e.target.closest("[data-newclient]"))openNew();
 if(e.target.closest("[data-createclient]"))createClient();
 if(e.target.closest("[data-export]"))exportCsv(e.target.closest("[data-export]"));
 if(e.target.closest("[data-addexp]"))addExp();
 const bb=e.target.closest("[data-bot]");if(bb)post("/admin/api/bot",{key:bb.dataset.bot,on:bb.dataset.on=="1"}).then(async r=>{if(r){await load();openClient(bb.dataset.bot);}});
 const hb=e.target.closest("[data-hist]");if(hb)showHist(hb.dataset.hist,hb);
 const sr=e.target.closest("[data-stoprec]");if(sr&&confirmStop(sr))post("/admin/api/expense",{stop:sr.dataset.stoprec}).then(r=>r&&load());
 const de=e.target.closest("[data-delexp]");if(de)post("/admin/api/expense",{delete:de.dataset.delexp}).then(r=>r&&load());
 const dr=e.target.closest("[data-delrem]");if(dr)saveRemind(dr.dataset.delrem,true);
 const ap=e.target.closest("[data-ap]");if(ap){st.ap=ap.dataset.ap;st.aic=null;render();}
 const as=e.target.closest("[data-aicsrv]");if(as)editSrv(as);
 const ss=e.target.closest("[data-savesrv]");if(ss)post("/admin/api/aicserver",{slug:ss.dataset.savesrv,usd:Number($("#srv-v").value||0)}).then(r=>{if(r){closeModal();st.aic=null;render();}});
});
const findCall=k=>st.data.calls.find(x=>x.key==k)||{};
const localDT=d=>{const z=n=>String(n).padStart(2,"0");return d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate())+"T"+z(d.getHours())+":"+z(d.getMinutes())};
function modal(html){$("#modal").innerHTML=`<div class="sheet">${html}</div>`;$("#modal").style.display="flex";}
function closeModal(){const m=$("#modal");if(m)m.style.display="none";}
function openCall(k){const x=findCall(k);
 modal(`<div class="mut">${esc(x.who)}</div><div class="bignum">${esc(x.phone)}</div>
  <div class="mut" style="margin-bottom:12px">🎯 ${esc(x.want)}${x.call_time?"<br>⏰ "+esc(x.call_time):""}</div>
  <a class="bigbtn" href="tel:${esc(x.tel)}">📞 Позвонить ${esc(x.phone)}</a>
  <button class="bigbtn sec" data-copy="${esc(x.tel)}">📋 Скопировать номер</button>
  <div class="mut" style="margin:14px 0 6px">После звонка:</div>
  <div class="btns"><button class="won" data-deal="called" data-key="${esc(k)}">✓ Позвонил</button>
  <button class="lost" data-rem="${esc(k)}">⏰ Напомнить позже</button><button class="lost" data-close>Закрыть</button></div>`);}
function openRemind(k){const x=findCall(k);const def=new Date(x.remind_ts?x.remind_ts*1000:Date.now()+3600e3);
 modal(`<b>⏰ Напоминание</b><div class="mut">${esc(x.who)} · ${esc(x.phone)}</div>
  <label class="mut" style="display:block;margin-top:10px">Когда</label><input id="rem-dt" type="datetime-local" value="${localDT(def)}">
  <div class="btns"><button class="lost" data-quick="60">+1 час</button><button class="lost" data-quick="180">+3 часа</button><button class="lost" data-quick="tm">Завтра 10:00</button></div>
  <label class="mut" style="display:block;margin-top:10px">Комментарий</label>
  <textarea id="rem-tx" rows="3" placeholder="Например: перезвонить после совещания, отправить КП">${esc(x.remind_text||"")}</textarea>
  <div class="btns"><button class="won" data-saverem="${esc(k)}">Сохранить</button>
  ${x.remind_ts?`<button class="lost" data-delrem="${esc(k)}">Удалить</button>`:""}<button class="lost" data-close>Отмена</button></div>
  <div class="mut" style="margin-top:8px">В указанное время бот пришлёт вам сообщение с номером и комментарием.</div>`);}
async function saveRemind(k,del){
 const v=$("#rem-dt")&&$("#rem-dt").value;const ts=del?0:(v?new Date(v).getTime()/1000:0);
 if(!del&&!ts){$("#rem-dt").focus();return;}
 if(!del&&ts<Date.now()/1000){if(tg)tg.HapticFeedback.notificationOccurred("warning");$("#rem-dt").focus();return;}
 const r=await fetch("/admin/api/remind",{method:"POST",headers:{"X-Init-Data":INIT,"Content-Type":"application/json"},
  body:JSON.stringify({key:k,ts,text:del?"":($("#rem-tx").value||"")})});
 if(r.ok){if(tg)tg.HapticFeedback.notificationOccurred("success");closeModal();load();}
}
async function load(){
 chips();
 if(!INIT){fail("Откройте панель из Telegram: команда /panel в боте.");return;}
 try{
  const r=await fetch("/admin/api?period="+st.per,{headers:{"X-Init-Data":INIT}});
  if(r.status==403){fail("Нет доступа. Откройте панель из бота, в чат которого приходят отчёты.");return;}
  st.data=await r.json();st.aic=null;if(st.data.period)st.per=st.data.period;
  if(STAFF()){TABS=[["eov","Обзор"],["calls","Звонки"],["crm","Клиенты"]];let sv=null;try{sv=localStorage.getItem("adm_x")}catch(e){}
   if(!sv){st.tab="eov";try{localStorage.setItem("adm_x","1")}catch(e){}}if(!["eov","calls","crm"].includes(st.tab))st.tab="eov";}
  render();
 }catch(e){fail("Не удалось загрузить данные: "+e)}
}
function fail(t){$("#app").innerHTML="";$("#err").style.display="block";$("#err").textContent=t}
async function deal(key,status,inp){
 const amount=inp&&inp.value?Number(inp.value):0;
 if(status=="won"&&!amount&&!STAFF()){inp&&inp.focus();if(tg)tg.HapticFeedback.notificationOccurred("warning");return;}
 const r=await fetch("/admin/api/deal",{method:"POST",headers:{"X-Init-Data":INIT,"Content-Type":"application/json"},body:JSON.stringify({key,status,amount})});
 if(r.ok){if(tg)tg.HapticFeedback.notificationOccurred("success");load();}
}
function render(){
 const d=st.data;if(!d)return;
 const V={calls,crm,fin:finance,ov,fn,cost,eov,aic};if(!V[st.tab])st.tab="calls";
 chips();$("#app").innerHTML=V[st.tab](d);
 const q=$("#q");if(q&&st.qfocus){q.focus();q.setSelectionRange(q.value.length,q.value.length);}
}
function aic(){
 if(!st.aic||st.aic.period!=st.per){loadAic();return `<p class="mut" style="padding:20px">Загрузка…</p>`;}
 const A=st.aic,W=["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];
 const chipsA="";
 if(!A.items.length)return chipsA+`<div class="card mut">Пока нет клиентов с ИИ-агентом.</div>`;
 const CA="#7b3fe4",CV="#e69a28",CS="#0f9d8f";
 const all=A.items.reduce((s,x)=>({spend:s.spend+x.spend,ai:s.ai+x.ai,tts:s.tts+x.tts_usd,srv:s.srv+x.server,d:s.d+x.dialogs,l:s.l+x.leads}),{spend:0,ai:0,tts:0,srv:0,d:0,l:0});
 const head=A.items.length>1?`<div class="hero cost"><h2>Все ИИ-клиенты</h2><div class="sub">${esc(A.label)} · ${A.items.length} клиентов</div>
  <div class="big"><div><b>${money(all.spend)}</b><span>расходы всего</span></div><div><b>${all.d}</b><span>диалогов</span></div><div><b>${all.l}</b><span>контактов</span></div></div></div>`:"";
 return chipsA+head+A.items.map(x=>{
  const mx=Math.max(1,...x.daily.map(y=>y.tg+y.ig)),mw=Math.max(1,...x.weekday),srvDay=x.server_m/30;
  const mc=Math.max(0.0001,...x.daily.map(y=>y.cost+srvDay));
  const bars=x.daily.map(y=>`<div title="${y.d}: Telegram ${y.tg}, Instagram ${y.ig}"><i style="height:${90*y.tg/mx}px;background:var(--tg);border-radius:0 0 3px 3px"></i><i style="height:${90*y.ig/mx}px;background:var(--ig);border-radius:3px 3px 0 0"></i></div>`).join("");
  const cbars=x.daily.map(y=>`<div title="${y.d}: ИИ+голос ${money(y.cost,3)} + сервер ${money(srvDay,2)}"><i style="height:${90*srvDay/mc}px;background:${CS}"></i><i style="height:${90*y.cost/mc}px;background:${CA};border-radius:3px 3px 0 0"></i></div>`).join("");
  const axis=x.daily.length?`<div class="axis"><span>${x.daily[0].d.slice(8)}.${x.daily[0].d.slice(5,7)}</span><span>${x.daily[x.daily.length-1].d.slice(8)}.${x.daily[x.daily.length-1].d.slice(5,7)}</span></div>`:"";
  const sp=Math.max(0.0001,x.spend),perDay=x.spend/Math.max(1,x.days);
  const share=(v,c,n,extra)=>`<div class="cline"><span class="sw" style="background:${c}"></span>${n}${extra?` <span class="mut">${extra}</span>`:""}<b>${money(v,v<1?3:2)} <span class="mut">${Math.round(100*v/sp)}%</span></b></div>`;
  const tgD=x.tg,igD=x.ig_dialogs,tot=Math.max(1,tgD+igD),deg=360*tgD/tot;
  return `<div class="hero cost"><h2>${esc(x.company)}</h2>
  <div class="sub">${esc(A.label)} · ${x.own_bot?"свой бот в Telegram":"через AI Business"}${x.ig?" · Instagram подключён":""} · ${x.days} дн.</div>
  <div class="big"><div><b>${money(x.spend)}</b><span>расходы за период</span></div><div><b>${money(perDay*30,0)}</b><span>прогноз в месяц</span></div><div><b>${x.dialogs?money(x.per_dialog,3):"—"}</b><span>цена диалога</span></div></div></div>
  <div class="kpis g4">
   <div class="kc" style="--c:var(--tg)"><span class="ic">💬</span><b>${x.dialogs}</b><span>диалогов</span></div>
   <div class="kc" style="--c:#2e9e5b"><span class="ic">📞</span><b>${x.leads}</b><span>контактов · ${pct(x.leads,x.dialogs)}</span></div>
   <div class="kc" style="--c:#e0582f"><span class="ic">🎯</span><b>${x.leads?money(x.per_lead):"—"}</b><span>цена контакта</span></div>
   <div class="kc" style="--c:${CA}"><span class="ic">📆</span><b>${money(perDay,2)}</b><span>в среднем в день</span></div></div>
  <div class="card"><h3>💸 Из чего расходы</h3>
   <div class="stack" style="height:18px"><i style="width:${100*x.ai/sp}%;background:${CA}"></i><i style="width:${100*x.tts_usd/sp}%;background:${CV}"></i><i style="width:${100*x.server/sp}%;background:${CS}"></i></div>
   ${share(x.ai,CA,"ИИ (Claude)","ответы бота")}
   ${share(x.tts_usd,CV,"Голос ElevenLabs",x.tts_chars.toLocaleString("ru")+" кред."+(x.stt_min?" · распознано "+x.stt_min+" мин":""))}
   ${share(x.server,CS,"Сервер Railway",money(x.server_m,0)+"/мес")}
   <div class="cline" style="border-top:1px solid var(--bg2);padding-top:8px;margin-top:8px"><b style="margin-left:0">Итого</b><b>${money(x.spend)}</b></div>
   <div class="btns"><button class="lost" data-aicsrv="${esc(x.slug)}" data-v="${x.server_m}">✏️ Сумма сервера в месяц</button></div>
   <p class="mut" style="margin:6px 0 0">ИИ и голос — по факту использования. Сервер — доля месячной суммы за дни периода.</p></div>
  ${crmCard(x.crm,true)}
  ${x.daily.length>1?`<div class="card"><h3>Расходы по дням</h3><div class="chart">${cbars}</div>${axis}
   <div class="leg" style="display:flex;gap:14px"><div><span class="dot" style="background:${CA}"></span>ИИ + голос</div><div><span class="dot" style="background:${CS}"></span>Сервер</div></div></div>`:""}
  <div class="card"><h3>Диалоги по платформам</h3><div class="split">
   <div class="donut" style="background:conic-gradient(var(--tg) 0 ${deg}deg,var(--ig) ${deg}deg 360deg${tgD+igD?"":",var(--bg2) 0 360deg"})"><div><b>${tgD+igD}</b>диалогов</div></div>
   <div class="leg" style="flex:1"><div><span class="dot" style="background:var(--tg)"></span>Telegram<b>${tgD}</b></div><div><span class="dot" style="background:var(--ig)"></span>Instagram<b>${igD}</b></div>
   <div class="mut" style="font-size:12px">На 1 диалог: ИИ ${x.dialogs?money(x.ai/x.dialogs,4):"—"} · голос ${x.dialogs?money(x.tts_usd/x.dialogs,4):"—"}</div></div></div></div>
  ${x.daily.length>1?`<div class="card"><h3>Новые диалоги по дням</h3><div class="chart">${bars}</div>${axis}</div>`:""}
  <div class="card"><h3>📅 По дням недели</h3>${W.map((n,i)=>`<div class="tagb"><span class="n" style="width:30px">${n}</span><span class="t"><i style="width:${100*x.weekday[i]/mw}%;background:linear-gradient(90deg,#2a7de1,#7b3fe4)"></i></span><b>${x.weekday[i]}</b></div>`).join("")}</div>`}).join("");
}
async function loadAic(){
 if(st.aicBusy)return;st.aicBusy=true;
 const want=st.per;try{const r=await fetch("/admin/api/aiclients?period="+encodeURIComponent(want),{headers:{"X-Init-Data":INIT}});if(r.ok){st.aic=await r.json();st.aic.period=want;}}catch(e){}
 st.aicBusy=false;if(st.tab=="aic")render();
}
function editSrv(b){
 modal(`<b>Сервер для ${esc(b.dataset.aicsrv)}</b><div class="mut">Сколько стоит в месяц ($), например Railway-сервис этого бота.</div>
  <input id="srv-v" class="fi" type="number" step="0.5" min="0" value="${esc(b.dataset.v)}">
  <div class="btns"><button class="won" data-savesrv="${esc(b.dataset.aicsrv)}">Сохранить</button><button class="lost" data-close>Отмена</button></div>`);
}
function chRow(name,col,vals){return `<tr><td><span class="dot" style="background:${col}"></span>${name}</td>${vals.map(v=>`<td>${v}</td>`).join("")}</tr>`}
function ov(d){
 const t=d.totals,f=d.funnel;
 const days=d.daily,mx=Math.max(1,...days.map(x=>x.tg+x.ig));
 const bars=days.map(x=>`<div title="${x.d}: ${x.tg+x.ig}"><i style="height:${90*x.tg/mx}px;background:var(--tg)"></i><i style="height:${90*x.ig/mx}px;background:var(--ig)"></i></div>`).join("");
 const p=d.proc;
 return `<div class="kpis">
  <div class="kpi"><b>${t.dialogs}</b><span>диалогов</span></div>
  <div class="kpi"><b>${t.leads}</b><span>оставили контакт · ${pct(t.leads,t.dialogs)}</span></div>
  <div class="kpi"><b>${t.won}</b><span>купили · ${pct(t.won,t.dialogs)}</span></div>
  <div class="kpi"><b>${money(t.revenue,0)}</b><span>выручка</span></div>
  <div class="kpi"><b>${money(d.spend)}</b><span>все расходы</span></div>
  <div class="kpi"><b>${t.leads?money(t.per_lead):"—"}</b><span>цена контакта</span></div>
 </div>
 <div class="card"><h3>Каналы</h3><table><tr><th></th><th>диалоги</th><th>горячие</th><th>контакты</th><th>покупки</th></tr>
  ${chRow("Telegram",COL.tg,[p.tg.dialogs,f.tg.hot,f.tg.lead,f.tg.won])}
  ${chRow("Instagram",COL.ig,[p.ig.dialogs,f.ig.hot,f.ig.lead,f.ig.won])}</table></div>
 ${days.length>1?`<div class="card"><h3>Новые диалоги по дням</h3><div class="chart">${bars}</div>
  <div class="axis"><span>${days[0].d.slice(5)}</span><span><span class="dot" style="background:var(--tg)"></span>Telegram <span class="dot" style="background:var(--ig);margin-left:6px"></span>Instagram</span><span>${days[days.length-1].d.slice(5)}</span></div></div>`:""}
 <div class="card"><h3>Сделки по этапам</h3><table>${d.pipe.map(([k,n])=>{const L=d.crm.filter(x=>x.stage==k);
   return `<tr><td>${n}</td><td>${L.length}</td><td>${k=="won"?money(L.reduce((s,x)=>s+Number(x.deal.amount||0),0),0):""}</td></tr>`}).join("")}</table></div>
 ${d.business.length?`<div class="card"><h3>Кто пишет (бизнес)</h3><table>${d.business.map(([b,n])=>`<tr><td>${esc(b)}</td><td>${n}</td></tr>`).join("")}</table></div>`:""}`;
}
function crmCard(c,admin){
 if(!c)return admin?`<div class="card"><h3>📞 Обработка заявок (CRM)</h3><p class="mut" style="margin:0">CRM не подключена. В CRM: «Доступы» → «Создать ключ» → отправьте боту команду /crm_hook.</p></div>`:"";
 const ft=c.first_touch||{},real=Math.max(1,c.real||0),pc=(a,b)=>b?Math.round(100*a/b)+"%":"—";
 const mm=m=>m==null?"—":m<1?"< 1 мин":m<60?Math.round(m)+" мин":m<1440?(m/60).toFixed(1).replace(".0","")+" ч":(m/1440).toFixed(1).replace(".0","")+" дн";
 const grade=ft.median_min==null?"":ft.median_min<=15?["#2e9e5b","отлично"]:ft.median_min<=60?["#e69a28","нормально"]:["#e0582f","медленно"];
 const CC={new:"#2a7de1",no_answer:"#e69a28",contacted:"#7b3fe4",thinking:"#d6337a",meeting:"#0f9d8f",won:"#2e9e5b",lost:"#8a94a6",spam:"#e0582f"};
 const mx=Math.max(1,...c.pipeline.map(([k])=>c.by_status[k]||0));
 const kc=(col,ic,v,l)=>`<div class="kc" style="--c:${col}"><span class="ic">${ic}</span><b>${v}</b><span>${l}</span></div>`;
 return `<div class="card"><h3>📞 Обработка заявок (CRM)</h3><p class="mut" style="margin:0 0 8px">Как менеджеры работают с заявками за период: скорость звонка, дозвон, записи.</p>
  <div class="kpis g4" style="margin:0">
   ${kc(grade?grade[0]:"#2a7de1","⚡",mm(ft.median_min),"до первого звонка"+(grade?` · <em style="font-style:normal;font-weight:700;color:${grade[0]}">${grade[1]}</em>`:""))}
   ${kc("#2e9e5b","⏱",pc(ft.in15,ft.n),"обработаны за 15 мин")}
   ${kc(c.untouched_1h?"#e0582f":"#8a94a6","🚨",c.untouched_1h,"ждут звонка > 1 часа")}
   ${kc(c.overdue?"#e69a28":"#8a94a6","⏰",c.overdue,"просрочено перезвонов")}
   ${kc("#7b3fe4","📲",pc(c.reached,c.real),"дозвонились")}
   ${kc("#0f9d8f","✅",c.won,"записались · "+pc(c.won,c.real))}</div>
  <div style="margin-top:10px">${c.pipeline.map(([k,n])=>`<div class="tagb"><span class="n">${esc(n)}</span><span class="t"><i style="width:${100*(c.by_status[k]||0)/mx}%;background:${CC[k]||"#2a7de1"}"></i></span><b>${c.by_status[k]||0}</b></div>`).join("")}</div>
  ${c.sources&&c.sources.length?`<table style="margin-top:8px"><tr><th>Откуда</th><th>заявок</th><th>дозвон</th><th>записались</th></tr>${c.sources.map(x=>`<tr><td>${esc(x.source)}</td><td>${x.n}</td><td>${pc(x.reached,x.n)}</td><td>${x.won}</td></tr>`).join("")}</table>`:""}
  ${c.revenue?`<p style="margin:8px 0 0">💰 Сумма оплат: <b>${Number(c.revenue).toLocaleString("ru")}</b></p>`:""}</div>`;
}
function eov(d){
 const t=d.totals,f=d.funnel,p=d.proc,days=d.daily,I=d.ins||{},pr=I.prev||{},per=d.period;
 const dl=(a,b)=>{if(b===undefined||(!a&&!b))return"";const x=a-b;return x>0?`<span class="dl up">▲${x}</span>`:x<0?`<span class="dl dn">▼${-x}</span>`:`<span class="dl">=</span>`};
 const waiting=d.calls.filter(x=>x.todo);
 const tgD=p.tg.dialogs,igD=p.ig.dialogs,tot=Math.max(1,tgD+igD),deg=360*tgD/tot;
 const conv=t.dialogs?Math.round(100*t.leads/t.dialogs):0;
 const PL=d.period_label||perLabel(per);
 const mx=Math.max(1,...days.map(x=>x.tg+x.ig)),mxl=Math.max(1,...days.map(x=>x.leads));
 const bars=days.map(x=>`<div title="${x.d}: Telegram ${x.tg}, Instagram ${x.ig}"><i style="height:${90*x.tg/mx}px;background:var(--tg);border-radius:0 0 3px 3px"></i><i style="height:${90*x.ig/mx}px;background:var(--ig);border-radius:3px 3px 0 0"></i></div>`).join("");
 const lbars=days.map(x=>`<div title="${x.d}: ${x.leads} заявок"><i style="height:${90*x.leads/mxl}px;background:linear-gradient(#34c77b,#2e9e5b);border-radius:3px"></i></div>`).join("");
 const axis=days.length?`<div class="axis"><span>${days[0].d.slice(8)}.${days[0].d.slice(5,7)}</span><span>${days[days.length-1].d.slice(8)}.${days[days.length-1].d.slice(5,7)}</span></div>`:"";
 const steps=d.funnel_steps,top=Math.max(1,f.tg.wrote+f.ig.wrote),FC=["#2a7de1","#3b8ff0","#7b3fe4","#e69a28","#e0582f","#2e9e5b"];
 const frows=steps.map(([k,n],i)=>{const s=f.tg[k]+f.ig[k],prev=i?f.tg[steps[i-1][0]]+f.ig[steps[i-1][0]]:s,w=Math.max(s?8:0,100*s/top);
  return `<div class="fnl"><div class="l"><span>${n}</span><span class="mut">${i&&prev?pct(s,prev)+" от пред. этапа":""}</span></div>
  <div class="t"><i style="width:${w}%;background:${FC[i%FC.length]}">${s}</i></div></div>`}).join("");
 const H=I.hours||[],mh=Math.max(1,...H);
 const hrs=H.map((v,i)=>`<i title="${String(i).padStart(2,"0")}:00 — ${v}" style="background:rgba(42,125,225,${v?0.15+0.85*v/mh:0.06})"></i>`).join("");
 const W=["Пн","Вт","Ср","Чт","Пт","Сб","Вс"],wk=I.week||[],mw=Math.max(1,...wk);
 const tag=(L,cols)=>{const m=Math.max(1,...L.map(x=>x[1]));return L.map(([n,v],i)=>`<div class="tagb"><span class="n">${esc(n)}</span><span class="t"><i style="width:${100*v/m}%;background:${cols[i%cols.length]}"></i></span><b>${v}</b></div>`).join("")};
 const C1=["#7b3fe4","#2a7de1","#e69a28","#2e9e5b","#d6337a"],C2=["#0f9d8f","#2a9fd8","#e0582f","#9b59b6"];
 const lg=I.lang||{},ln=Math.max(1,(lg.uz_lat||0)+(lg.uz_cyr||0)+(lg.ru||0));
 const kc=(c,ic,v,l,x)=>`<div class="kc" style="--c:${c}"><span class="ic">${ic}</span><b>${v}${x||""}</b><span>${l}</span></div>`;
 return `<div class="hero"><h2>${esc(d.company||"Отчёт")}</h2><div class="sub">📅 ${esc(PL)}${d.prev_label?" · ▲▼ — сравнение с "+d.prev_label:""}</div>
  <div class="big"><div><b>${t.dialogs}</b><span>новых диалогов</span></div><div><b>${t.leads}</b><span>оставили номер</span></div><div><b>${conv}%</b><span>конверсия</span></div></div></div>
 <div class="kpis g4">
  ${kc("#2a7de1","💬",t.dialogs,"новых диалогов",dl(t.dialogs,pr.dialogs))}
  ${kc("#2e9e5b","📞",t.leads,"оставили номер",dl(t.leads,pr.leads))}
  ${kc("#e0582f","🔥",t.hot,"горячих",dl(t.hot,pr.hot))}
  ${kc("#7b3fe4","✅",t.won,"записались")}
  ${kc("#e69a28","⏳",waiting.length,"ждут звонка")}
  ${kc("#d6337a","🎙",I.voice||0,"голосовых от клиентов")}</div>
 <div class="card"><h3>Откуда пишут</h3><div class="split">
  <div class="donut" style="background:conic-gradient(var(--tg) 0 ${deg}deg,var(--ig) ${deg}deg 360deg${tgD+igD?"":",var(--bg2) 0 360deg"})"><div><b>${tgD+igD}</b>диалогов</div></div>
  <div class="leg" style="flex:1">
   <div><span class="dot" style="background:var(--tg)"></span>Telegram<b>${tgD} · ${pct(tgD,tgD+igD)}</b></div>
   <div><span class="dot" style="background:var(--ig)"></span>Instagram<b>${igD} · ${pct(igD,tgD+igD)}</b></div>
   <div class="mut" style="font-size:12px">Номер оставили: Telegram ${f.tg.lead} (${pct(f.tg.lead,tgD)}) · Instagram ${f.ig.lead} (${pct(f.ig.lead,igD)})</div></div></div></div>
 ${days.length>1?`<div class="card"><h3>Новые диалоги по дням</h3><div class="chart">${bars}</div>${axis}
  <div class="leg" style="display:flex;gap:14px"><div><span class="dot" style="background:var(--tg)"></span>Telegram</div><div><span class="dot" style="background:var(--ig)"></span>Instagram</div></div></div>
 <div class="card"><h3>Заявки (оставили номер) по дням</h3><div class="chart">${lbars}</div>${axis}</div>`:""}
 <div class="card"><h3>Воронка</h3><p class="mut" style="margin:0 0 4px">Путь клиента от первого сообщения до записи.</p>${frows}</div>
 ${crmCard(d.crm,false)}
 ${waiting.length?`<div class="card"><h3>⏳ Ждут звонка <span class="cnt">${waiting.length}</span></h3>${waiting.slice(0,6).map(x=>`<div class="wl"><div><b>${esc(x.who)}</b> <span class="pill" style="background:${x.ch=="ig"?"var(--ig)":"var(--tg)"}">${x.ch=="ig"?"Instagram":"Telegram"}</span><div class="mut">${esc((x.want||"").slice(0,70))}</div></div>${x.tel&&!x.ro?`<a class="tel" href="tel:${esc(x.tel)}">📞</a>`:""}</div>`).join("")}
  ${waiting.length>6?`<p class="mut" style="margin:6px 0 0">Ещё ${waiting.length-6} — во вкладке «Звонки»</p>`:""}</div>`:""}
 <div class="g2 g-wrap" style="display:grid;gap:8px">
 ${(I.courses||[]).some(x=>x[1])?`<div class="card" style="margin:0"><h3>🎯 Какие курсы спрашивают</h3>${tag(I.courses.filter(x=>x[1]),C1)}</div>`:""}
 ${(I.branches||[]).some(x=>x[1])?`<div class="card" style="margin:0"><h3>📍 Какие филиалы</h3>${tag(I.branches.filter(x=>x[1]),C2)}</div>`:""}</div>
 <div class="card"><h3>⏰ Когда пишут клиенты</h3><div class="hrs">${hrs}</div><div class="hax"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>
  ${I.peak!=null&&I.peak!==undefined?`<p class="mut" style="margin:6px 0 0">Пик — ${String(I.peak).padStart(2,"0")}:00–${String((I.peak+1)%24).padStart(2,"0")}:00. Бот отвечает круглосуточно.</p>`:""}</div>
 <div class="card"><h3>📅 По дням недели</h3>${W.map((n,i)=>`<div class="tagb"><span class="n" style="width:30px">${n}</span><span class="t"><i style="width:${100*(wk[i]||0)/mw}%;background:linear-gradient(90deg,#2a7de1,#7b3fe4)"></i></span><b>${wk[i]||0}</b></div>`).join("")}</div>
 <div class="card"><h3>🗣 Язык клиентов</h3><div class="stack"><i style="width:${100*(lg.uz_lat||0)/ln}%;background:#2e9e5b"></i><i style="width:${100*(lg.uz_cyr||0)/ln}%;background:#0f9d8f"></i><i style="width:${100*(lg.ru||0)/ln}%;background:#2a7de1"></i></div>
  <div class="cline"><span class="sw" style="background:#2e9e5b"></span>Узбекский (латиница)<b>${lg.uz_lat||0}</b></div>
  <div class="cline"><span class="sw" style="background:#0f9d8f"></span>Узбекский (кириллица)<b>${lg.uz_cyr||0}</b></div>
  <div class="cline"><span class="sw" style="background:#2a7de1"></span>Русский<b>${lg.ru||0}</b></div></div>
 <div class="card"><h3>📈 Качество диалогов</h3><table>
  <tr><th></th><th>Telegram</th><th>Instagram</th></tr>
  <tr><td>Сообщений клиента на диалог</td><td>${tgD?(p.tg.client_msgs/tgD).toFixed(1):"—"}</td><td>${igD?(p.ig.client_msgs/igD).toFixed(1):"—"}</td></tr>
  <tr><td>Вовлеклись (3+ сообщений)</td><td>${pct(p.tg.engaged,tgD)}</td><td>${pct(p.ig.engaged,igD)}</td></tr>
  <tr><td>Вернулись после напоминания</td><td>${p.tg.revived}</td><td>${p.ig.revived}</td></tr>
  <tr><td>Передано менеджеру</td><td>${p.tg.handoff}</td><td>${p.ig.handoff}</td></tr></table></div>
 ${d.needs.length?`<div class="card"><h3>💡 Что хотят клиенты</h3>${tag(d.needs.slice(0,8),C1)}</div>`:""}`;
}
function fn(d){
 const steps=d.funnel_steps,f=d.funnel,top=Math.max(1,f.tg.wrote+f.ig.wrote);
 const rows=steps.map(([k,n],i)=>{const a=f.tg[k],b=f.ig[k],s=a+b,prev=i?f.tg[steps[i-1][0]]+f.ig[steps[i-1][0]]:s;
  return `<div class="fn"><div class="l"><span>${n}</span><span><b>${s}</b> <span class="mut">${i?pct(s,prev)+" от пред.":""}</span></span></div>
  <div class="bar"><i style="width:${100*a/top}%;background:var(--tg)"></i><i style="width:${100*b/top}%;background:var(--ig)"></i></div></div>`}).join("");
 const p=d.proc;const pr=(c)=>{const x=p[c];return[pct(x.engaged,x.dialogs),x.dialogs?(x.client_msgs/x.dialogs).toFixed(1):"—",x.dialogs?(x.bot_msgs/x.dialogs).toFixed(1):"—",
  pct(x.voice_in,x.client_msgs),x.followups,x.revived,x.silent,x.stopped,x.handoff,x.dialogs?Math.round(x.readiness_sum/x.dialogs)+"%":"—"]};
 const names=["Ответили 3+ раза","Сообщений клиента на диалог","Ответов бота на диалог","Доля голосовых","Дожимов отправлено","Вернулись после дожима","Замолчали совсем","Попросили не писать","Позвали менеджера","Средняя готовность"];
 const a=pr("tg"),b=pr("ig");
 return `<div class="card"><h3>Воронка</h3><p class="mut">Диалоги, начатые за период. Синий — Telegram, розовый — Instagram.</p>${rows}</div>
 <div class="card"><h3>Как идёт процесс</h3><table><tr><th></th><th>Telegram</th><th>Instagram</th></tr>
 ${names.map((n,i)=>`<tr><td>${n}</td><td>${a[i]}</td><td>${b[i]}</td></tr>`).join("")}</table></div>`;
}
function finance(d){
 const today=new Date();const z=n=>String(n).padStart(2,"0");const iso=today.getFullYear()+"-"+z(today.getMonth()+1)+"-"+z(today.getDate());
 const cn=Object.fromEntries(d.exp_cats.map(c=>[c[0],c[1]]));
 const er=ch=>{const x=d.econ[ch];return `<tr><td><span class="dot" style="background:${COL[ch]}"></span>${d.ch_names[ch]}</td><td>${money(x.ads,0)}</td><td>${money(x.bot,2)}</td>
   <td>${x.dialogs}</td><td>${x.leads}</td><td>${x.won}</td><td>${money(x.revenue,0)}</td></tr>
   <tr class="sub"><td colspan="7">диалог ${x.dialogs?money(x.per_dialog):"—"} · контакт ${x.leads?money(x.per_lead):"—"} · продажа ${x.won?money(x.per_sale):"—"} · ROMI ${x.romi===null?"—":x.romi+"%"}</td></tr>`};
 return `<div class="kpis">
  <div class="kpi"><b>${money(d.totals.revenue,0)}</b><span>выручка</span></div>
  <div class="kpi"><b>${money(d.spend,0)}</b><span>все расходы</span></div>
  <div class="kpi"><b style="color:${d.profit>=0?"var(--ok)":"var(--bad)"}">${money(d.profit,0)}</b><span>прибыль</span></div>
  <div class="kpi"><b>${d.romi===null?"—":d.romi+"%"}</b><span>ROMI</span></div></div>
 <div class="card"><h3>➕ Внести расход</h3>
  <div class="btns"><input class="fi" id="ex-date" type="date" value="${iso}" style="flex:1;min-width:130px">
  <select class="fi" id="ex-cat" style="flex:1;min-width:150px">${d.exp_cats.map(c=>`<option value="${c[0]}">${c[1]}</option>`).join("")}</select></div>
  <div class="btns"><input class="fi" id="ex-amt" type="number" inputmode="decimal" placeholder="Сумма $" style="flex:1">
  <input class="fi" id="ex-note" placeholder="Комментарий (кампания, за что)" style="flex:2"></div>
  <label class="mut" style="display:flex;gap:8px;align-items:center;margin-top:8px"><input type="checkbox" id="ex-daily"> Списывать эту сумму каждый день (например, дневной бюджет таргета)</label>
  <div class="btns"><button class="won" data-addexp>Добавить</button></div>
  <p class="mut">ИИ, голос и сервер считаются автоматически — вносите рекламу, подписки, зарплаты и прочее.</p></div>
 ${d.recurring.length?`<div class="card"><h3>🔁 Ежедневные расходы</h3><table>${d.recurring.map(r=>`<tr><td>${esc(cn[r.cat]||"")}${r.note?`<div class="mut">${esc(r.note)}</div>`:""}<div class="mut">с ${esc(r.since)}</div></td>
   <td>${money(r.amount,2)}/день</td><td><button class="lost" data-stoprec="${r.id}" style="border:0;border-radius:10px;padding:6px 10px">Стоп</button></td></tr>`).join("")}</table>
   <p class="mut">Добавляются в расходы автоматически каждый день.</p></div>`:""}
 <div class="card"><h3>Окупаемость по каналам</h3><table><tr><th></th><th>реклама</th><th>бот</th><th>диал.</th><th>конт.</th><th>прод.</th><th>выручка</th></tr>
  ${er("tg")}${er("ig")}</table><p class="mut">Цена = реклама канала + расходы бота на этот канал.</p></div>
 <div class="card"><h3>Куда уходят деньги</h3><table>
  <tr><td>ИИ, голос, сервер (авто)</td><td>${money(d.spend_auto,2)}</td><td>${d.spend?Math.round(100*d.spend_auto/d.spend):0}%</td></tr>
  ${d.exp_cats.filter(c=>d.by_cat[c[0]]).map(c=>`<tr><td>${c[1]}</td><td>${money(d.by_cat[c[0]],2)}</td><td>${Math.round(100*d.by_cat[c[0]]/d.spend)}%</td></tr>`).join("")}
  <tr class="tot"><td>Итого</td><td>${money(d.spend,2)}</td><td></td></tr></table>
  <div class="bar" style="margin-top:8px;height:10px">${[["auto",d.spend_auto,"#8a8f98"],...d.exp_cats.map((c,i)=>[c[0],d.by_cat[c[0]],["var(--ig)","var(--tg)","#7b61ff","var(--warn)","var(--ok)","#c0c4cc"][i]])]
   .filter(x=>x[1]).map(x=>`<i style="width:${100*x[1]/(d.spend||1)}%;background:${x[2]}"></i>`).join("")}</div></div>
 ${d.expenses.length?`<div class="card"><h3>Внесённые расходы</h3><table>${d.expenses.map(x=>`<tr><td>${new Date(x.ts*1000).toLocaleDateString("ru")}<div class="mut">${esc(cn[x.cat]||"")}${x.note?" · "+esc(x.note):""}</div></td>
   <td>${money(x.amount,2)}</td><td><button class="xbtn" data-delexp="${x.id}">✕</button></td></tr>`).join("")}</table></div>`:""}`;
}
function cost(d){
 const c=d.costs,e=d.eleven,s=e.sub;
 const row=(k)=>`<tr><td>${d.ch_names[k]}</td><td>${money(c[k].ai,3)}</td><td>${c[k].tts_chars.toLocaleString("ru")}</td><td>${money(c[k].tts_usd)}</td><td>${c[k].stt_min}</td></tr>`;
 const keys=["tg","ig","test","eval","other"].filter(k=>k=="tg"||k=="ig"||c[k].ai>0||c[k].tts_chars>0);
 const used=s&&s.limit?Math.min(100,100*s.used/s.limit):0;
 return `<div class="kpis">
  <div class="kpi"><b>${money(d.spend)}</b><span>итого за период</span></div>
  <div class="kpi"><b>${d.totals.dialogs?money(d.totals.per_dialog,3):"—"}</b><span>на один диалог</span></div>
 </div>
 <div class="card"><h3>По статьям</h3><table>
  <tr><td>ИИ (Claude)</td><td>${money(d.ai_total,3)}</td></tr>
  <tr><td>Голосовые ответы (ElevenLabs, эквивалент)</td><td>${money(d.tts_usd)}</td></tr>
  <tr><td>Распознавание голосовых · ${d.stt_min} мин</td><td>${money(d.stt_extra)}</td></tr>
  <tr><td>Сервер (Railway, доля)</td><td>${money(d.server)}</td></tr>
  <tr class="tot"><td>Итого</td><td>${money(d.spend)}</td></tr></table>
  <p class="mut">Голос считается по цене кредита вашего тарифа ElevenLabs ($${e.plan_usd} за ${Number(e.credits_limit).toLocaleString("ru")} кредитов). ~1 000 символов ≈ 1 минута речи. Распознавание: ${e.stt_included_h} ч/мес в тарифе, сверх — $0.22/ч.</p></div>
 <div class="card"><h3>По каналам</h3><table><tr><th></th><th>ИИ</th><th>кредиты</th><th>голос $</th><th>мин STT</th></tr>${keys.map(row).join("")}</table>
  <p class="mut">«Ваши тесты» — ваши сообщения боту, «Без канала» — расходы до включения учёта.</p></div>
 ${s?`<div class="card"><h3>ElevenLabs сейчас</h3><div class="l" style="display:flex;justify-content:space-between;font-size:13px"><span>${esc(s.tier||"")}</span><span>${Number(s.used||0).toLocaleString("ru")} из ${Number(s.limit||0).toLocaleString("ru")}</span></div>
  <div class="bar" style="margin-top:6px"><i style="width:${used}%;background:${used>85?"var(--bad)":"var(--ac)"}"></i></div>
  <p class="mut">${s.reset?"Обновится "+new Date(s.reset*1000).toLocaleDateString("ru"):""}${used>85?" · минуты заканчиваются — дальше ElevenLabs списывает по $0.18 за минуту":""}</p></div>`:""}`;
}
function calls(d){
 const todo=d.calls.filter(x=>x.todo),later=d.calls.filter(x=>!x.todo&&x.remind_ts).sort((a,b)=>a.remind_ts-b.remind_ts),
  done=d.calls.filter(x=>!x.todo&&!x.remind_ts).slice(0,15);
 const card=x=>`<div class="call ${x.todo?"":"done"}" data-open="${esc(x.key)}">
  <div class="top"><div><b>${esc(x.who)}</b><div class="mut"><span class="dot" style="background:${COL[x.ch]}"></span>${when(x.ts)} · ${x.readiness}%</div></div>
  ${x.phone?`<button class="tel" data-call="${esc(x.key)}">📞 Позвонить</button>`:`<span class="badge">без номера</span>`}</div>
  ${x.remind_ts?`<div class="rem ${x.remind_due?"due":""}">⏰ ${when(x.remind_ts)}${x.remind_text?" — "+esc(x.remind_text):""}</div>`:""}
  <div class="want">🎯 ${esc(x.want)}</div>
  ${x.business?`<div class="mut">🏢 ${esc(x.business)}</div>`:""}
  ${x.call_time||x.budget?`<div class="mut">${x.call_time?"⏰ "+esc(x.call_time):""}${x.call_time&&x.budget?" · ":""}${x.budget?"💰 "+esc(x.budget):""}</div>`:""}
  ${x.objection?`<div class="mut">⚠️ ${esc(x.objection)}</div>`:""}
  ${x.note&&x.note!=x.want?`<div class="mut">📝 ${esc(x.note)}</div>`:""}
  <div class="btns">${x.ro?`<span class="mut">Instagram · только просмотр</span>`:x.todo?`<button class="won" data-deal="called" data-key="${esc(x.key)}">✓ Позвонил</button>
   <button class="lost" data-rem="${esc(x.key)}">⏰ Напомнить</button>
   ${STAFF()?"":`<input type="number" inputmode="decimal" placeholder="сумма $">`}<button class="lost" data-deal="won" data-key="${esc(x.key)}">✅ Купил</button>
   <button class="lost" data-deal="lost" data-key="${esc(x.key)}">❌ Отказ</button>`:
   `<span class="mut">${x.deal=="won"?"✅ Купил":x.deal=="lost"?"❌ Отказ":"📞 Позвонили "+when(x.called_ts)}</span>
   ${x.deal?"":`<button class="lost" data-rem="${esc(x.key)}">⏰ ${x.remind_ts?"Изменить":"Напомнить"}</button>`}
   <button class="lost" data-deal="${x.deal?"open":"uncall"}" data-key="${esc(x.key)}">↩︎ Вернуть</button>`}
   ${x.link?`<a class="lost lnk" href="${esc(x.link)}">💬 Чат</a>`:""}</div></div>`;
 return `<div class="kpis"><div class="kpi"><b>${todo.length}</b><span>ждут звонка</span></div>
  <div class="kpi"><b>${d.calls.filter(x=>x.called).length}</b><span>уже позвонили</span></div></div>
  ${todo.length?todo.map(card).join(""):`<p class="mut" style="padding:16px 4px">Сейчас звонить некому — все обработаны 👍</p>`}
  ${later.length?`<h3 style="margin:16px 4px 4px">⏰ Запланировано</h3>${later.map(card).join("")}`:""}
  ${done.length?`<h3 style="margin:16px 4px 4px">Обработанные</h3>${done.map(card).join("")}`:""}`;
}
const findCl=k=>(st.data.crm||[]).find(x=>x.key==k)||{facts:{},notes:[],tail:[],deal:{}};
const stName=s=>(st.data.pipe.find(p=>p[0]==s)||["",s])[1];
function crm(d){
 const q=st.q.trim().toLowerCase();
 const SF=[["active","В работе"],["all","Все"],...d.pipe.map(p=>[p[0],p[1]])];
 let L=d.crm;
 if(st.sf=="active")L=L.filter(x=>!["won","lost","dialog"].includes(x.stage));else if(st.sf!="all")L=L.filter(x=>x.stage==st.sf);
 if(q)L=L.filter(x=>[x.name,x.username,x.phone,x.tel,x.facts.business,x.facts.need,...x.notes.map(n=>n.t)].join(" ").toLowerCase().includes(q));
 const cnt=s=>d.crm.filter(x=>s=="all"||(s=="active"?!["won","lost","dialog"].includes(x.stage):x.stage==s)).length;
 const sum=d.crm.filter(x=>x.stage=="won").reduce((s,x)=>s+Number(x.deal.amount||0),0);
 const rows=L.slice(0,200).map(x=>`<div class="lead" data-open="${esc(x.key)}"><div class="top"><div><b>${esc(x.name||"—")}${x.username?` <span class="mut">@${esc(x.username)}</span>`:""}</b>
   <div class="mut"><span class="dot" style="background:${COL[x.ch]}"></span>${x.phone?esc(x.phone)+" · ":""}${when(x.last)}</div>
   ${x.facts.need||x.facts.business?`<div class="small">🎯 ${esc((x.facts.business?x.facts.business+" — ":"")+(x.facts.need||""))}</div>`:""}
   ${x.remind_ts?`<div class="small">⏰ ${when(x.remind_ts)} ${esc(x.remind_text)}</div>`:""}${x.bot_off?`<div class="small" style="color:var(--bad)">⏸ бот остановлен</div>`:""}</div>
   <span class="badge st-${x.stage}">${stName(x.stage)}${x.stage=="won"&&x.deal.amount?" · $"+x.deal.amount:""}</span></div></div>`).join("");
 return `<input id="q" class="search" placeholder="🔍 Поиск: имя, телефон, бизнес, заметка" value="${esc(st.q)}">
 <div class="chips filters" style="margin-top:8px">${SF.map(([k,n])=>`<button class="chip ${st.sf==k?"on":""}" data-sf="${k}">${n} <span class="mut">${cnt(k)}</span></button>`).join("")}</div>
 <div class="btns" style="margin:8px 0"><button class="won" data-newclient>＋ Добавить клиента</button>${STAFF()?"":`<button class="lost" data-export>📤 Выгрузить в Excel</button>
 <span class="mut" style="align-self:center">Продажи: ${money(sum,0)}</span>`}</div>
 ${rows||`<p class="mut" style="padding:16px 4px">Никого не найдено.</p>`}
 ${L.length>200?`<p class="mut">Показаны первые 200 — уточните поиск.</p>`:""}`;
}
function openClient(k){const x=findCl(k);if(!x.key)return;const f=x.facts;
 if(x.ro){const tl=x.tail.map(m=>`<div class="msg ${m.r=="a"?"a":""}">${m.r=="a"?(m.h?"👤 ":m.v?"🤖🎙 ":m.f?"🔔 ":"🤖 "):""}${esc(m.t)}</div>`).join("");
  modal(`<div class="top" style="display:flex;justify-content:space-between;gap:8px"><div><b style="font-size:18px">${esc(x.name||"Клиент")}</b>
   <div class="mut"><span class="dot" style="background:${COL[x.ch]}"></span>Instagram${x.username?" · @"+esc(x.username):""} · с ${when(x.first)}</div></div><button class="xbtn" data-close>✕</button></div>
   ${x.tel?`<a class="bigbtn" href="tel:${esc(x.tel)}">📞 Позвонить ${esc(x.phone)}</a>`:""}
   <div class="small">Этап: ${stName(x.stage)} · готовность ${x.readiness}%</div>
   ${["need","offer","call_time","objection","note"].filter(i=>f[i]).map(i=>`<div class="small">${{need:"🎯",offer:"💼",call_time:"⏰",objection:"⚠️",note:"📝"}[i]} ${esc(f[i])}</div>`).join("")}
   <div class="mut fl" style="display:flex;justify-content:space-between;align-items:center">Переписка
   <button class="lost" data-hist="${esc(k)}" style="border:0;border-radius:10px;padding:5px 9px;font-size:12px">📜 Показать всю</button></div><div id="hist">${tl}</div>
   ${x.link?`<div class="btns"><a class="lost lnk" href="${esc(x.link)}">💬 Открыть в Instagram</a></div>`:""}
   <div class="mut" style="margin-top:8px">Диалог из Instagram — только просмотр. Ответить можно в Instagram Direct.</div>`);return;}
 const inp=(id,lab,v,ph)=>`<label class="mut fl">${lab}</label><input class="fi" id="cf-${id}" value="${esc(v||"")}" placeholder="${ph||""}">`;
 const tail=x.tail.map(m=>`<div class="msg ${m.r=="a"?"a":""}">${m.r=="a"?(m.h?"👤 ":m.v?"🤖🎙 ":m.f?"🔔 ":"🤖 "):""}${esc(m.t)}</div>`).join("");
 const notes=x.notes.slice().reverse().map(n=>`<div class="note"><span class="mut">${when(n.ts)}</span> ${esc(n.t)}</div>`).join("");
 modal(`<div id="cl" data-stage="${x.stage}"><div class="top" style="display:flex;justify-content:space-between;gap:8px">
   <div><b style="font-size:18px">${esc(x.name||"Клиент")}</b><div class="mut"><span class="dot" style="background:${COL[x.ch]}"></span>${st.data.ch_names[x.ch]}${x.username?" · @"+esc(x.username):""} · с ${when(x.first)}</div></div>
   <button class="xbtn" data-close>✕</button></div>
  ${x.tel?`<a class="bigbtn" href="tel:${esc(x.tel)}">📞 Позвонить ${esc(x.phone)}</a>`:""}
  ${x.ch!="manual"?`<div class="botbar ${x.bot_off?"off":""}">${x.bot_off?"⏸ Бот не отвечает этому клиенту":"🤖 Бот отвечает этому клиенту"}<button class="lost" data-bot="${esc(k)}" data-on="${x.bot_off?1:0}">${x.bot_off?"▶️ Включить бота":"⏸ Стоп бот"}</button></div>`:""}
  <div class="mut fl">Этап сделки</div><div class="chips wrap">${st.data.pipe.map(p=>`<button class="chip ${x.stage==p[0]?"on":""}" data-stage="${p[0]}">${p[1]}</button>`).join("")}</div>
  ${STAFF()?"":`<input class="fi" id="cl-amt" type="number" inputmode="decimal" placeholder="Сумма продажи $" value="${x.deal.amount||""}" style="display:${x.stage=="won"?"block":"none"}">`}
  ${inp("name","Имя",x.name)}${inp("phone","Телефон",x.phone||"","+998 ...")}${inp("business","Бизнес",f.business)}
  ${inp("need","Что хочет",f.need)}${inp("offer","Что предложили",f.offer)}${STAFF()?"":inp("budget","Бюджет",f.budget)}${inp("call_time","Удобное время",f.call_time)}
  ${f.objection?`<div class="small">⚠️ Возражение: ${esc(f.objection)}</div>`:""}${f.note?`<div class="small">📝 Итог бота: ${esc(f.note)}</div>`:""}
  <label class="mut fl">Новая заметка</label><textarea class="fi" id="cf-note" rows="2" placeholder="Что обсудили, договорённости…"></textarea>
  <div class="btns"><button class="won" data-saveclient="${esc(k)}">💾 Сохранить</button><button class="lost" data-rem="${esc(k)}">⏰ ${x.remind_ts?"Напоминание "+when(x.remind_ts):"Напомнить"}</button>
   ${x.link?`<a class="lost lnk" href="${esc(x.link)}">💬 Чат</a>`:""}</div>
  ${notes?`<div class="mut fl">Заметки</div>${notes}`:""}
  ${tail||x.ch!="manual"?`<div class="mut fl" style="display:flex;justify-content:space-between;align-items:center">Переписка
   <button class="lost" data-hist="${esc(k)}" style="border:0;border-radius:10px;padding:5px 9px;font-size:12px">📜 Показать всю</button></div><div id="hist">${tail}</div>`:""}
  <div class="mut" style="margin-top:8px">Готовность ${x.readiness}%${STAFF()?"":" · расход на клиента "+money(x.cost,3)}${x.paused?" · бот на паузе (отвечал менеджер)":""}</div></div>`);}
async function post(url,body){const r=await fetch(url,{method:"POST",headers:{"X-Init-Data":INIT,"Content-Type":"application/json"},body:JSON.stringify(body)});
 if(tg)tg.HapticFeedback.notificationOccurred(r.ok?"success":"error");return r.ok?r.json():null;}
async function saveClient(k){const fields={};["name","phone","business","need","offer","budget","call_time"].forEach(i=>{const e=$("#cf-"+i);if(e)fields[i]=e.value});
 const stage=$("#cl").dataset.stage;const amount=$("#cl-amt")?$("#cl-amt").value:0;
 if(stage=="won"&&!amount&&!STAFF()){$("#cl-amt").focus();return;}
 if(await post("/admin/api/client",{key:k,fields,stage,amount,note:$("#cf-note").value})){closeModal();load();}}
function openNew(){modal(`<b style="font-size:18px">＋ Новый клиент</b><div class="mut">Например, позвонил сам или пришёл по рекомендации</div>
 <label class="mut fl">Имя</label><input class="fi" id="nc-name"><label class="mut fl">Телефон</label><input class="fi" id="nc-phone" inputmode="tel" placeholder="+998 ...">
 <label class="mut fl">Бизнес</label><input class="fi" id="nc-business"><label class="mut fl">Что хочет</label><input class="fi" id="nc-need">
 <label class="mut fl">Бюджет</label><input class="fi" id="nc-budget"><label class="mut fl">Заметка</label><textarea class="fi" id="nc-note" rows="2"></textarea>
 <div class="btns"><button class="won" data-createclient>Добавить</button><button class="lost" data-close>Отмена</button></div>`);}
async function createClient(){const b={};["name","phone","business","need","budget","note"].forEach(i=>b[i]=$("#nc-"+i).value);
 if(!b.name&&!b.phone){$("#nc-name").focus();return;}
 const r=await post("/admin/api/new",b);if(r){closeModal();await load();if(r.key)openClient(r.key);}}
function confirmStop(b){if(b.dataset.sure)return true;b.dataset.sure=1;b.textContent="Точно?";return false;}
async function addExp(){const amt=Number($("#ex-amt").value);if(!(amt>0)){$("#ex-amt").focus();return;}
 const dv=$("#ex-date").value;const ts=dv?new Date(dv+"T12:00").getTime()/1000:Date.now()/1000;
 if(await post("/admin/api/expense",{ts,since:dv,daily:$("#ex-daily").checked,cat:$("#ex-cat").value,amount:amt,note:$("#ex-note").value}))load();}
async function showHist(k,btn){btn.textContent="⏳";const r=await post("/admin/api/history",{key:k});if(!r)return;
 $("#hist").innerHTML=r.items.map(m=>`<div class="msg ${m.r=="a"?"a":""}"><span class="mut" style="font-size:11px">${when(m.ts)}</span><br>${m.r=="a"?(m.h?"👤 ":m.v?"🤖🎙 ":m.f?"🔔 ":"🤖 "):""}${esc(m.t)}</div>`).join("")||"<p class='mut'>Пусто</p>";
 btn.textContent=r.items.length+" сообщений";}
async function exportCsv(btn){btn.textContent="⏳ Готовлю…";const r=await post("/admin/api/export",{});
 btn.textContent=r?"✓ Файл в чате с ботом":"Не получилось";}
function leads(d){
 const F=[["hot","Горячие+"],["all","Все"],["won","Купили"],["cost","Дорогие"]];
 let L=d.leads;if(st.lf=="hot")L=L.filter(x=>x.lvl>=4);if(st.lf=="won")L=L.filter(x=>x.lvl==6);
 if(st.lf=="cost")L=[...d.leads].sort((a,b)=>b.cost.total-a.cost.total);
 const sum=L.reduce((s,x)=>s+x.cost.total,0);
 const items=L.map(x=>{const fx=Object.entries(x.facts).map(([k,v])=>`<div><span class="mut">${esc(k)}:</span> ${esc(v)}</div>`).join("");
  const tail=x.tail.map(m=>`<div class="msg ${m.r=="a"?"a":""}">${m.r=="a"?(m.v?"🤖🎙 ":m.f?"🔔 ":"🤖 "):""}${esc(m.t)}</div>`).join("");
  return `<div class="lead"><div class="top"><div><b>${esc(x.who)}</b><div class="mut"><span class="dot" style="background:${COL[x.ch]}"></span>${when(x.last)} · ${x.readiness}% · <span style="white-space:nowrap">💸 ${money(x.cost.total,3)}</span></div></div>
   <span class="badge b${x.lvl}">${x.stage}${x.deal&&x.deal.status=="won"?" · $"+x.deal.amount:""}</span></div>
   <div class="det"><div class="cst"><b>Расход на клиента: ${money(x.cost.total,3)}</b><br>ИИ ${money(x.cost.ai,4)} · голос ${x.cost.tts_chars} кред. (≈${money(x.cost.tts_usd,3)}) · распознано ${x.cost.stt_sec} сек</div>${fx}<div style="margin-top:6px">${tail}</div>
   <div class="btns"><input type="number" inputmode="decimal" placeholder="сумма $">
   <button class="won" data-deal="won" data-key="${esc(x.key)}">✅ Купил</button>
   <button class="lost" data-deal="lost" data-key="${esc(x.key)}">❌ Отказ</button>
   ${x.deal&&x.deal.status?`<button class="lost" data-deal="open" data-key="${esc(x.key)}">↩︎ Сбросить</button>`:""}</div></div></div>`}).join("");
 return `<div class="chips filters">${F.map(([k,n])=>`<button class="chip ${st.lf==k?"on":""}" data-lf="${k}">${n}</button>`).join("")}</div>
 ${L.length?`<p class="mut" style="margin:8px 4px">${L.length} клиентов · расход ${money(sum,3)} · в среднем ${money(sum/L.length,4)} на клиента</p>`:""}
 ${items||`<p class="mut" style="padding:16px 4px">Пока пусто за этот период.</p>`}
 <p class="mut">Нажмите на клиента, чтобы увидеть детали. Отметьте «Купил» с суммой — так считается выручка и конверсия в покупку. Расход по клиенту считается с 19.10.</p>`;
}
load();
</script></body></html>"""
