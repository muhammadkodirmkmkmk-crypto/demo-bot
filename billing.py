"""
CRM: to'lovlar (sotuv bo'yicha oldindan to'lov / qoldiq / qarzlar), AI-agent obunalari, kassa, veb-kirish (sessiya).
Ma'lumotlar: chat["payments"] — mijoz to'lovlari; "crm:subs" — obunalar; "crm:sessions" — veb sessiyalar.
"""
import json
import time
import secrets
import hashlib
from datetime import datetime, timedelta

core = None
_SUBS = {"loaded": False, "items": []}
_SESS = {"loaded": False, "items": {}}
LOGIN_TOKENS = {}          # bir martalik havola tokeni -> amal qilish muddati
SESSION_DAYS = 30
SUB_STATUSES = {"active": "Активна", "paused": "Пауза", "cancelled": "Отменена"}
PAY_METHODS = {"cash": "Наличные", "card": "Карта", "transfer": "Перечисление", "click": "Click/Payme", "other": "Другое"}


def init(bot_module):
    global core
    core = bot_module


def _id(prefix=""):
    return prefix + hashlib.sha1(f"{time.time()}{secrets.token_hex(4)}".encode()).hexdigest()[:10]


def now_tz():
    return datetime.now(core.TZ)


def day_str(ts):
    return datetime.fromtimestamp(ts, core.TZ).strftime("%Y-%m-%d")

# --------------------------------------------------------------------------
# Veb-kirish: bot bergan bir martalik havola -> 30 kunlik sessiya (cookie)
# --------------------------------------------------------------------------
def _sessions():
    if not _SESS["loaded"]:
        _SESS["loaded"] = True
        _SESS["items"] = core.db_get("crm:sessions") or {}
    return _SESS["items"]


def new_login_token():
    t = secrets.token_urlsafe(24)
    LOGIN_TOKENS[t] = time.time() + 600
    for k, exp in list(LOGIN_TOKENS.items()):
        if exp < time.time():
            LOGIN_TOKENS.pop(k, None)
    return t


def login(token):
    """Havola tokeni to'g'ri bo'lsa — yangi sessiya qaytaradi (bir marta ishlaydi)"""
    exp = LOGIN_TOKENS.pop(token or "", 0)
    if exp < time.time():
        return None
    sid = secrets.token_urlsafe(32)
    with core.LOCK:
        s = _sessions()
        s[hashlib.sha256(sid.encode()).hexdigest()] = time.time() + SESSION_DAYS * 86400
        for k, e in list(s.items()):
            if e < time.time():
                s.pop(k, None)
        snap = dict(s)
    core.db_put("crm:sessions", snap)
    return sid


def logout(sid):
    with core.LOCK:
        _sessions().pop(hashlib.sha256((sid or "").encode()).hexdigest(), None)
        snap = dict(_sessions())
    core.db_put("crm:sessions", snap)


def cookie_sid(h):
    for part in (h.headers.get("Cookie") or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "crm_s":
            return v
    return ""


def session_ok(h):
    sid = cookie_sid(h)
    if not sid:
        return False
    exp = _sessions().get(hashlib.sha256(sid.encode()).hexdigest(), 0)
    return exp > time.time()

# --------------------------------------------------------------------------
# Sotuv to'lovlari (mijoz kartasida)
# --------------------------------------------------------------------------
def add_payment(key, d):
    try:
        amount = round(float(d.get("amount") or 0), 2)
        ts = float(d.get("ts") or time.time())
    except Exception:
        return False
    if amount <= 0:
        return False
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        c.setdefault("payments", []).append({"id": _id("p"), "amount": amount, "ts": ts,
                                             "method": d.get("method") if d.get("method") in PAY_METHODS else "other",
                                             "note": str(d.get("note") or "")[:200]})
        deal = c.get("deal") or {}
        if deal.get("status") != "won":           # to'lov keldi — demak sotildi
            price = float(d.get("price") or deal.get("amount") or 0) or amount
            c["deal"] = {"status": "won", "amount": price, "ts": time.time()}
    core.save_chat(key)
    return True


def del_payment(key, pid):
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        n = len(c.get("payments", []))
        c["payments"] = [p for p in c.get("payments", []) if p["id"] != pid]
        ok = len(c["payments"]) < n
    core.save_chat(key)
    return ok


def set_price(key, price):
    with core.LOCK:
        c = core.STATE["chats"].get(key)
        if c is None:
            return False
        deal = c.get("deal") or {"status": "won", "ts": time.time()}
        deal["amount"] = round(float(price or 0), 2)
        c["deal"] = deal
    core.save_chat(key)
    return True

# --------------------------------------------------------------------------
# AI-agent obunalari ($99/oy va h.k.)
# --------------------------------------------------------------------------
def subs():
    if not _SUBS["loaded"]:
        _SUBS["loaded"] = True
        _SUBS["items"] = core.db_get("crm:subs") or []
    return _SUBS["items"]


def _save_subs():
    with core.LOCK:
        snap = json.loads(json.dumps(subs()))
    core.db_put("crm:subs", snap)


def add_months(day, n, anchor=0):
    """Oy qo'shish; anchor — obuna boshlangan kun (31-yanvar -> 28-fevral -> 31-mart)"""
    d = datetime.strptime(day, "%Y-%m-%d")
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return f"{y:04d}-{m:02d}-{min(anchor or d.day, last):02d}"


def sub_action(d):
    act = d.get("action")
    with core.LOCK:
        items = subs()
        if act == "add":
            start = d.get("start") or now_tz().strftime("%Y-%m-%d")
            s = {"id": _id("s"), "name": str(d.get("name") or "").strip()[:100], "phone": str(d.get("phone") or "")[:40],
                 "product": str(d.get("product") or "AI-агент")[:80], "price": round(float(d.get("price") or 99), 2),
                 "months": max(1, int(d.get("months") or 1)), "start": start,
                 "next_due": d.get("next_due") or start, "status": "active", "tenant": str(d.get("tenant") or ""),
                 "client_key": str(d.get("client_key") or ""), "note": str(d.get("note") or "")[:300],
                 "payments": [], "created": time.time()}
            if not s["name"]:
                return False
            items.append(s)
            if d.get("paid_now"):
                s["payments"].append({"id": _id("p"), "amount": s["price"], "ts": time.time(), "method": d.get("method", "other"),
                                      "period": s["next_due"]})
                s["next_due"] = add_months(s["next_due"], s["months"], int(s.get("start", "")[8:10] or 0))
        else:
            s = next((x for x in items if x["id"] == d.get("id")), None)
            if s is None:
                return False
            if act == "pay":                      # to'ladi: keyingi to'lov sanasi bir davrga suriladi
                amount = round(float(d.get("amount") or s["price"]), 2)
                s["payments"].append({"id": _id("p"), "amount": amount, "ts": float(d.get("ts") or time.time()),
                                      "method": d.get("method", "other"), "period": s["next_due"]})
                s["next_due"] = add_months(s["next_due"], s["months"], int(s.get("start", "")[8:10] or 0))
                if s["status"] != "active":
                    s["status"] = "active"
            elif act == "update":
                for k in ("name", "phone", "product", "note", "tenant", "next_due"):
                    if k in d:
                        s[k] = str(d[k] or "")[:300]
                for k in ("price",):
                    if k in d:
                        s[k] = round(float(d[k] or 0), 2)
                if "months" in d:
                    s["months"] = max(1, int(d["months"] or 1))
                if d.get("status") in SUB_STATUSES:
                    s["status"] = d["status"]
            elif act == "unpay":
                if s["payments"]:
                    p = s["payments"].pop()
                    s["next_due"] = p.get("period") or s["next_due"]
            elif act == "delete":
                items.remove(s)
            else:
                return False
    _save_subs()
    return True


def sub_view(s, today):
    overdue_days = 0
    if s["status"] == "active" and s["next_due"] < today:
        overdue_days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(s["next_due"], "%Y-%m-%d")).days
    due_in = (datetime.strptime(s["next_due"], "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days
    state = s["status"] if s["status"] != "active" else ("overdue" if overdue_days else ("soon" if due_in <= 3 else "ok"))
    return dict(s, overdue_days=overdue_days, due_in=due_in, state=state,
                paid_total=round(sum(p["amount"] for p in s["payments"]), 2),
                mrr=round(s["price"] / s["months"], 2) if s["status"] == "active" else 0)


def sub_reminders():
    """Har kuni: 3 kun qolgan va muddati o'tgan obunalar haqida admin'ga eslatma"""
    today = now_tz().strftime("%Y-%m-%d")
    out = []
    for s in subs():
        v = sub_view(s, today)
        if s["status"] != "active":
            continue
        if v["state"] == "overdue":
            out.append(f"🔴 {s['name']} — просрочка {v['overdue_days']} дн., ${s['price']:.0f} ({s['product']})")
        elif v["due_in"] in (0, 1, 3):
            out.append(f"🟡 {s['name']} — оплата {'сегодня' if v['due_in'] == 0 else 'через ' + str(v['due_in']) + ' дн.'}, "
                       f"${s['price']:.0f}")
    return out

# --------------------------------------------------------------------------
# Kassa, qarzlar — admin.build() uchun
# --------------------------------------------------------------------------
def data(chats, start, end):
    today = now_tz().strftime("%Y-%m-%d")
    pays, debts = [], []
    for key, c in chats.items():
        who = c.get("name") or (c.get("facts") or {}).get("name") or "Клиент"
        for p in c.get("payments", []):
            pays.append(dict(p, kind="deal", key=key, who=who))
        deal = c.get("deal") or {}
        if deal.get("status") == "won":
            paid = sum(p["amount"] for p in c.get("payments", []))
            price = float(deal.get("amount") or 0)
            if price - paid > 0.009:
                debts.append({"key": key, "who": who, "price": price, "paid": round(paid, 2), "left": round(price - paid, 2),
                              "since": deal.get("ts", 0)})
    sv = [sub_view(s, today) for s in subs()]
    for s in sv:
        for p in s["payments"]:
            pays.append(dict(p, kind="sub", sub=s["id"], who=s["name"], product=s["product"]))
    pays.sort(key=lambda x: -x["ts"])
    in_period = [p for p in pays if start <= p["ts"] < end]
    # oxirgi 6 oy kassasi: tushum va xarajat
    months = []
    t = now_tz().replace(day=1)
    for i in range(5, -1, -1):
        y, m = t.year, t.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y:04d}-{m:02d}")
    cash = {m: {"m": m, "in": 0.0, "out": 0.0} for m in months}
    for p in pays:
        m = day_str(p["ts"])[:7]
        if m in cash:
            cash[m]["in"] += p["amount"]
    for e in core.ADMIN.expenses():
        m = day_str(e["ts"])[:7]
        if m in cash:
            cash[m]["out"] += e["amount"]
    active = [s for s in sv if s["status"] == "active"]
    return {
        "payments": in_period[:300], "received": round(sum(p["amount"] for p in in_period), 2),
        "received_subs": round(sum(p["amount"] for p in in_period if p["kind"] == "sub"), 2),
        "debts": sorted(debts, key=lambda x: -x["left"]), "debt_total": round(sum(x["left"] for x in debts), 2),
        "subs": sorted(sv, key=lambda s: ({"overdue": 0, "soon": 1, "ok": 2}.get(s["state"], 3), s["next_due"])),
        "mrr": round(sum(s["mrr"] for s in active), 2), "subs_active": len(active),
        "subs_overdue": sum(1 for s in sv if s["state"] == "overdue"),
        "subs_overdue_sum": round(sum(s["price"] for s in sv if s["state"] == "overdue"), 2),
        "cash": [dict(cash[m], **{"in": round(cash[m]["in"], 2), "out": round(cash[m]["out"], 2)}) for m in months],
        "pay_methods": PAY_METHODS, "sub_statuses": SUB_STATUSES,
    }
