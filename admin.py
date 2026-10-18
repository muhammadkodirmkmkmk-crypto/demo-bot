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
import time
import hmac
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

core = None
ELEVEN_PLAN_USD = float(os.environ.get("ELEVEN_PLAN_USD", "22"))
ELEVEN_PLAN_CREDITS = int(os.environ.get("ELEVEN_PLAN_CREDITS", "121000"))
STT_INCLUDED_HOURS = float(os.environ.get("STT_INCLUDED_HOURS", "100"))
STT_EXTRA_PER_HOUR = float(os.environ.get("STT_EXTRA_PER_HOUR", "0.22"))
SERVER_USD = float(os.environ.get("SERVER_USD", "5"))
CHANNELS = ("tg", "ig")
CH_NAMES = {"tg": "Telegram", "ig": "Instagram", "test": "Ваши тесты", "eval": "Проверки /eval", "other": "Без канала"}
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


def is_admin(h):
    uid = check_init(h.headers.get("X-Init-Data", ""))
    return bool(uid) and uid == str(core.REPORT_CHAT_ID)

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


def period_range(period):
    now = datetime.now(core.TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start = today
    elif period == "7d":
        start = today - timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
    else:
        period, start = "30d", today - timedelta(days=29)
    days = []
    d = start
    while d <= today:
        days.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return period, start.timestamp(), days


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


def build(period="30d"):
    period, start, days = period_range(period)
    with core.LOCK:
        chats = json.loads(json.dumps(core.STATE["chats"]))
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
        if deal.get("status") == "won" and (deal.get("ts") or 0) >= start:
            revenue += float(deal.get("amount") or 0)
            proc[ch]["revenue"] += float(deal.get("amount") or 0)
            dd = datetime.fromtimestamp(deal["ts"], core.TZ).strftime("%Y-%m-%d")
            if dd in daily:
                daily[dd]["won"] += 1
        if first < start:
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
        lvl, label = stage_of(c)
        last_ts = max([h.get("ts") or 0 for h in hist] or [first])
        who = c.get("name") or "—"
        if c.get("username"):
            who += " @" + c["username"]
        leads.append({"key": key, "ch": ch, "who": who, "stage": label, "lvl": lvl,
                      "readiness": int(c.get("readiness") or 0), "last": last_ts, "first": first,
                      "facts": {k: v for k, v in (c.get("facts") or {}).items() if v},
                      "deal": deal, "status": c.get("status"),
                      "tail": [{"r": h["r"], "t": h["t"].replace(core.STT.VOICE_PREFIX, "🎙 ")[:300],
                                "v": bool(h.get("voice")), "f": bool(h.get("f"))} for h in hist[-8:]]})
    leads.sort(key=lambda x: (-x["lvl"], -x["last"]))

    # --- umumiy hisob
    tts_usd = sum(costs[c]["tts_usd"] for c in costs)
    stt_min = sum(costs[c]["stt_min"] for c in costs)
    months = max(1.0, len(days) / 30.0) if period != "today" else 1 / 30
    server = round(SERVER_USD * (len(days) / 30.0), 2)
    stt_extra = round(max(0.0, stt_min / 60 - STT_INCLUDED_HOURS * months) * STT_EXTRA_PER_HOUR, 2)
    total_dialogs = sum(proc[c]["dialogs"] for c in CHANNELS)
    total_leads = sum(funnel[c]["lead"] for c in CHANNELS)
    total_won = sum(funnel[c]["won"] for c in CHANNELS)
    spend = ai_total + tts_usd + stt_extra + server
    return {
        "period": period, "days": days, "generated": time.time(),
        "costs": costs, "ai_total": round(ai_total, 4), "tts_usd": round(tts_usd, 2), "stt_min": round(stt_min, 1),
        "stt_extra": stt_extra, "server": server, "spend": round(spend, 2),
        "eleven": {"sub": sub, "plan_usd": ELEVEN_PLAN_USD, "credits_limit": credits_limit,
                   "stt_included_h": STT_INCLUDED_HOURS},
        "funnel_steps": FUNNEL, "funnel": funnel, "proc": proc, "events": ev,
        "totals": {"dialogs": total_dialogs, "leads": total_leads, "won": total_won, "revenue": round(revenue, 2),
                   "per_dialog": round(spend / total_dialogs, 4) if total_dialogs else 0,
                   "per_lead": round(spend / total_leads, 2) if total_leads else 0,
                   "per_sale": round(spend / total_won, 2) if total_won else 0},
        "daily": [{"d": d, **daily[d], "cost": round(core.usage_cost(usage[d]) + sum(
            s.get("tts_chars", 0) for s in stats[d].values()) * usd_per_credit, 3)} for d in days],
        "business": sorted(biz.items(), key=lambda x: -x[1])[:8],
        "leads": leads[:150], "ch_names": CH_NAMES,
    }


def set_deal(key, status, amount=0):
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        if status == "open":
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
    title = {"today": "Сегодня", "7d": "7 дней", "30d": "30 дней", "month": "Этот месяц"}[d["period"]]
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


COMMANDS = [("panel", "📊 Панель: расходы, воронка, лиды"), ("stats", "Сводка за сегодня"),
            ("month", "Сводка за месяц"), ("leads", "Горячие клиенты и контакты"), ("cost", "Расход на ИИ"),
            ("eval", "Проверка качества ответов"), ("ig", "Instagram аккаунты")]


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
# HTTP
# --------------------------------------------------------------------------
def handle_get(h):
    path = urllib.parse.urlparse(h.path).path.rstrip("/")
    if path == "/admin":
        core.IG.respond_html(h, 200, PAGE, headers={"Cache-Control": "no-store"})
        return True
    if path == "/admin/api":
        if not is_admin(h):
            core.IG.respond_html(h, 403, '{"error":"forbidden"}', ctype="application/json")
            return True
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        data = build((q.get("period") or ["30d"])[0])
        core.IG.respond_html(h, 200, json.dumps(data, ensure_ascii=False), ctype="application/json; charset=utf-8",
                             headers={"Cache-Control": "no-store"})
        return True
    return False


def handle_post(h, body):
    path = urllib.parse.urlparse(h.path).path.rstrip("/")
    if path != "/admin/api/deal":
        return False
    if not is_admin(h):
        core.IG.respond_html(h, 403, '{"error":"forbidden"}', ctype="application/json")
        return True
    try:
        d = json.loads(body or b"{}")
        ok = d.get("status") in ("won", "lost", "open") and set_deal(str(d.get("key")), d["status"], d.get("amount"))
    except Exception:
        ok = False
    core.IG.respond_html(h, 200 if ok else 400, json.dumps({"ok": bool(ok)}), ctype="application/json")
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
header{position:sticky;top:0;z-index:5;background:var(--bg2);padding:10px 12px 6px}
.chips,.tabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}.chips::-webkit-scrollbar,.tabs::-webkit-scrollbar{display:none}
.chip{border:0;border-radius:16px;padding:6px 12px;background:var(--bg);color:var(--tx);font:inherit;font-size:13px;white-space:nowrap}
.chip.on{background:var(--ac);color:var(--act)}
.tabs{margin-top:8px}.tab{flex:1;border:0;background:none;color:var(--mut);font:inherit;font-weight:600;padding:6px 4px;border-bottom:2px solid transparent}
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
.lead{background:var(--bg);border-radius:14px;padding:10px 12px;margin:8px 0}.lead .top{display:flex;justify-content:space-between;gap:8px}
.badge{font-size:12px;padding:2px 8px;border-radius:10px;background:var(--bg2);white-space:nowrap}
.b6{background:#2e9e5b22;color:var(--ok)}.b5{background:#e69a2822;color:var(--warn)}.b4{background:#d9534f22;color:var(--bad)}.b-1{opacity:.6}
.det{display:none;margin-top:8px;font-size:13px}.lead.open .det{display:block}
.msg{margin:3px 0;padding:5px 8px;border-radius:10px;background:var(--bg2);max-width:92%}.msg.a{margin-left:auto;background:#2a7de11a}
.btns{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}.btns button,.btns input{font:inherit;font-size:13px;border-radius:10px;border:0;padding:7px 10px}
.btns input{width:90px;background:var(--bg2);color:var(--tx)}.won{background:var(--ok);color:#fff}.lost{background:var(--bg2);color:var(--tx)}
.filters{display:flex;gap:6px;margin-top:4px}.hidden{display:none}
#err{display:none;padding:30px 16px;text-align:center}
</style></head><body>
<header>
 <div class="chips" id="per"></div>
 <div class="tabs" id="tabs"></div>
</header>
<main id="app"><p class="mut" style="padding:20px">Загрузка…</p></main>
<div id="err"></div>
<script>
const tg=window.Telegram&&Telegram.WebApp; if(tg){tg.ready();tg.expand();}
const INIT=tg?tg.initData:"";
const PER=[["today","Сегодня"],["7d","7 дней"],["month","Месяц"],["30d","30 дней"]];
const TABS=[["ov","Обзор"],["fn","Воронка"],["cost","Расходы"],["leads","Лиды"]];
const COL={tg:"var(--tg)",ig:"var(--ig)"};
let st={per:"month",tab:"ov",data:null,lf:"hot"};
try{const s=JSON.parse(localStorage.getItem("adm")||"{}");Object.assign(st,{per:s.per||st.per,tab:s.tab||st.tab})}catch(e){}
const $=s=>document.querySelector(s);
const money=(v,d=2)=>"$"+Number(v||0).toFixed(d);
const pct=(a,b)=>b?Math.round(100*a/b)+"%":"—";
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const when=ts=>{if(!ts)return"";const d=new Date(ts*1000);return d.toLocaleDateString("ru",{day:"2-digit",month:"2-digit"})+" "+d.toLocaleTimeString("ru",{hour:"2-digit",minute:"2-digit"})};
function save(){try{localStorage.setItem("adm",JSON.stringify({per:st.per,tab:st.tab}))}catch(e){}}
function chips(){
 $("#per").innerHTML=PER.map(([k,n])=>`<button class="chip ${st.per==k?"on":""}" data-p="${k}">${n}</button>`).join("")+
  `<button class="chip" data-p="re">↻</button>`;
 $("#tabs").innerHTML=TABS.map(([k,n])=>`<button class="tab ${st.tab==k?"on":""}" data-t="${k}">${n}</button>`).join("");
}
document.addEventListener("click",e=>{
 const p=e.target.closest("[data-p]"),t=e.target.closest("[data-t]"),l=e.target.closest(".lead .top"),f=e.target.closest("[data-lf]"),dl=e.target.closest("[data-deal]");
 if(p){if(p.dataset.p!="re")st.per=p.dataset.p;save();load();}
 if(t){st.tab=t.dataset.t;save();chips();render();}
 if(f){st.lf=f.dataset.lf;render();}
 if(l){l.parentElement.classList.toggle("open");}
 if(dl){deal(dl.dataset.key,dl.dataset.deal,dl.closest(".lead").querySelector("input"));}
});
async function load(){
 chips();
 if(!INIT){fail("Откройте панель из Telegram: команда /panel в боте.");return;}
 try{
  const r=await fetch("/admin/api?period="+st.per,{headers:{"X-Init-Data":INIT}});
  if(r.status==403){fail("Доступ только для администратора.");return;}
  st.data=await r.json();render();
 }catch(e){fail("Не удалось загрузить данные: "+e)}
}
function fail(t){$("#app").innerHTML="";$("#err").style.display="block";$("#err").textContent=t}
async function deal(key,status,inp){
 const amount=inp&&inp.value?Number(inp.value):0;
 if(status=="won"&&!amount){inp&&inp.focus();if(tg)tg.HapticFeedback.notificationOccurred("warning");return;}
 const r=await fetch("/admin/api/deal",{method:"POST",headers:{"X-Init-Data":INIT,"Content-Type":"application/json"},body:JSON.stringify({key,status,amount})});
 if(r.ok){if(tg)tg.HapticFeedback.notificationOccurred("success");load();}
}
function render(){
 const d=st.data;if(!d)return;
 $("#app").innerHTML={ov,fn,cost,leads}[st.tab](d);
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
 ${d.business.length?`<div class="card"><h3>Кто пишет (бизнес)</h3><table>${d.business.map(([b,n])=>`<tr><td>${esc(b)}</td><td>${n}</td></tr>`).join("")}</table></div>`:""}`;
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
  <p class="mut">Голос считается по цене кредита вашего тарифа ElevenLabs ($${e.plan_usd} за ${Number(e.credits_limit).toLocaleString("ru")} кредитов). Распознавание входит в тариф (${e.stt_included_h} ч/мес), платно только сверх.</p></div>
 <div class="card"><h3>По каналам</h3><table><tr><th></th><th>ИИ</th><th>кредиты</th><th>голос $</th><th>мин STT</th></tr>${keys.map(row).join("")}</table>
  <p class="mut">«Ваши тесты» — ваши сообщения боту, «Без канала» — расходы до включения учёта.</p></div>
 ${s?`<div class="card"><h3>ElevenLabs сейчас</h3><div class="l" style="display:flex;justify-content:space-between;font-size:13px"><span>${esc(s.tier||"")}</span><span>${Number(s.used||0).toLocaleString("ru")} из ${Number(s.limit||0).toLocaleString("ru")}</span></div>
  <div class="bar" style="margin-top:6px"><i style="width:${used}%;background:${used>85?"var(--bad)":"var(--ac)"}"></i></div>
  <p class="mut">${s.reset?"Обновится "+new Date(s.reset*1000).toLocaleDateString("ru"):""}${used>85?" · кредиты заканчиваются — бот перейдёт на текст":""}</p></div>`:""}`;
}
function leads(d){
 const F=[["hot","Горячие+"],["all","Все"],["won","Купили"]];
 let L=d.leads;if(st.lf=="hot")L=L.filter(x=>x.lvl>=4);if(st.lf=="won")L=L.filter(x=>x.lvl==6);
 const items=L.map(x=>{const fx=Object.entries(x.facts).map(([k,v])=>`<div><span class="mut">${esc(k)}:</span> ${esc(v)}</div>`).join("");
  const tail=x.tail.map(m=>`<div class="msg ${m.r=="a"?"a":""}">${m.r=="a"?(m.v?"🤖🎙 ":m.f?"🔔 ":"🤖 "):""}${esc(m.t)}</div>`).join("");
  return `<div class="lead"><div class="top"><div><b>${esc(x.who)}</b><div class="mut"><span class="dot" style="background:${COL[x.ch]}"></span>${when(x.last)} · ${x.readiness}%</div></div>
   <span class="badge b${x.lvl}">${x.stage}${x.deal&&x.deal.status=="won"?" · $"+x.deal.amount:""}</span></div>
   <div class="det">${fx}<div style="margin-top:6px">${tail}</div>
   <div class="btns"><input type="number" inputmode="decimal" placeholder="сумма $">
   <button class="won" data-deal="won" data-key="${esc(x.key)}">✅ Купил</button>
   <button class="lost" data-deal="lost" data-key="${esc(x.key)}">❌ Отказ</button>
   ${x.deal&&x.deal.status?`<button class="lost" data-deal="open" data-key="${esc(x.key)}">↩︎ Сбросить</button>`:""}</div></div></div>`}).join("");
 return `<div class="chips filters">${F.map(([k,n])=>`<button class="chip ${st.lf==k?"on":""}" data-lf="${k}">${n}</button>`).join("")}</div>
 ${items||`<p class="mut" style="padding:16px 4px">Пока пусто за этот период.</p>`}
 <p class="mut">Нажмите на клиента, чтобы увидеть детали. Отметьте «Купил» с суммой — так считается выручка и конверсия в покупку.</p>`;
}
load();
</script></body></html>"""
