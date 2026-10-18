"""
Modellarni solishtirish: sinov dialoglari (eval_set.json) har bir model orqali o'tkaziladi.
Mijozga hech narsa yuborilmaydi. Natija: GET /eval/last (matn) va Telegram'ga qisqa hisobot.
Ishga tushirish (faqat admin chatdan): /eval [N] [model1,model2]
"""
import os
import re
import gzip
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

core = None
EVAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_set.json")
DEFAULT_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
LAST = {"status": "idle", "text": "Eval hali ishga tushirilmagan. Telegram: /eval 30", "started": 0}
RU_ONLY = re.compile("[ыэщъЫЭЩЪ]")


def init(bot_module):
    global core
    core = bot_module


def load_set():
    if os.path.exists(EVAL_FILE + ".gz"):
        with gzip.open(EVAL_FILE + ".gz", "rt", encoding="utf-8") as f:
            return json.load(f)
    with open(EVAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def short(m):
    return m.replace("claude-", "").replace("-20251001", "")


def check(out, script, history):
    """Avtomatik tekshiruv: muammolar ro'yxati"""
    probs = []
    if not out:
        return ["EMPTY"]
    text = " ".join(out)
    if script == "ru" and re.search(r"(?i)\b(rahmat|albatta|siz|menejer|qo'ng'iroq)\b", text):
        probs.append("LANG(uz in ru)")
    if script == "uz_lat" and re.search(core.CYR_CLASS, text):
        probs.append("LANG(cyr in lat)")
    if script.startswith("uz") and RU_ONLY.search(text):
        probs.append("LANG(ru letters)")
    if script == "uz_cyr" and re.search(r"[A-Za-z]{4,}", re.sub(r"(?i)businessai\.uz|@\w+|CRM|ERP|AI|Telegram|Instagram|Excel|iOS|Android|1C", "", text)):
        probs.append("LATIN(in cyr)")
    if any(len(m) > core.MAX_MSG_CHARS for m in out):
        probs.append("LONG")
    if sum(m.count("?") for m in out) > 1 and any(h["r"] == "a" for h in history):
        probs.append("2Q")
    nums = sorted({n for m in out for n in core.bad_numbers(m, history)})
    if nums:
        probs.append("NUM(" + ",".join(nums) + ")")
    return probs


def run_dialog(d, model):
    hist, facts, ready, rows = [], {}, 0, []
    for t in d["turns"]:
        if t["role"] == "client":
            for x in t["texts"]:
                hist.append({"r": "u", "t": x, "ts": 0})
            continue
        c = {"history": [dict(h) for h in hist], "facts": dict(facts), "readiness": ready, "script": "",
             "lang_pref": "", "status": "active", "chat_id": "eval"}
        script = core.client_script(c)
        t0 = time.time()
        try:
            r = core.generate_reply(c, script, model=model) or {}
        except Exception as e:
            r = {"messages": [], "error": str(e)}
        out = r.get("messages") or []
        for k in ("name", "phone", "business", "need", "current_tool", "budget", "offer", "objection", "call_time"):
            v = str(r.get(k) or "").strip()
            if v:
                facts[k] = v[:200]
        try:
            ready = max(0, min(100, int(r.get("readiness", ready))))
        except Exception:
            pass
        rows.append({"client": [h["t"] for h in hist if h["r"] == "u"][-3:], "ideal": t["messages"], "out": out,
                     "action": r.get("action"), "ready": ready, "script": script,
                     "probs": check(out, script, c["history"]), "ms": int((time.time() - t0) * 1000)})
        for x in t["messages"]:
            hist.append({"r": "a", "t": x, "ts": 0})
    return rows


def usage_snapshot():
    with core.LOCK:
        return json.loads(json.dumps(core.USAGE))


def usage_delta(before, after):
    out = {}
    for day, models in after.items():
        for m, u in models.items():
            b = before.get(day, {}).get(m, {})
            d = {k: u[k] - b.get(k, 0) for k in u}
            if d["calls"]:
                acc = out.setdefault(m, {"calls": 0, "in": 0, "cw": 0, "cr": 0, "out": 0})
                for k in acc:
                    acc[k] += d[k]
    return out


def run(n=30, models=None, notify=None):
    models = models or DEFAULT_MODELS
    data = load_set()[:n]
    LAST.update(status="running", started=time.time(), text=f"Ishlayapti: {len(data)} dialog x {len(models)} model...")
    before = usage_snapshot()
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {(m, i): ex.submit(run_dialog, d, m) for m in models for i, d in enumerate(data)}
        for (m, i), f in futs.items():
            try:
                results[(m, i)] = f.result()
            except Exception as e:
                results[(m, i)] = [{"client": [], "ideal": [], "out": [], "probs": ["ERROR " + str(e)[:80]],
                                    "ms": 0, "ready": 0, "action": "", "script": ""}]
    spent = usage_delta(before, usage_snapshot())
    lines, summary = [], []
    for m in models:
        rows = [r for i in range(len(data)) for r in results[(m, i)]]
        bad = [r for r in rows if r["probs"]]
        cnt = {}
        for r in bad:
            for p in r["probs"]:
                k = p.split("(")[0]
                cnt[k] = cnt.get(k, 0) + 1
        ms = sorted(r["ms"] for r in rows) or [0]
        cost = core.usage_cost({m: spent[m]}) if m in spent else 0.0
        per_reply = cost / max(1, len(rows))
        s = (f"{short(m)}: {len(rows)} ответов, без замечаний {len(rows) - len(bad)} "
             f"({100 * (len(rows) - len(bad)) // max(1, len(rows))}%), замечания {cnt}, "
             f"медиана {ms[len(ms) // 2] / 1000:.1f}с, потрачено ${cost:.3f} (${per_reply:.4f} за ответ)")
        summary.append(s)
    lines.append("ИТОГ\n" + "\n".join(summary) + "\n")
    for i, d in enumerate(data):
        lines.append(f"===== Диалог #{d['id']}")
        per_model = [results[(m, i)] for m in models]
        for j, row in enumerate(per_model[0]):
            lines.append("👤 " + " / ".join(row["client"])[-300:])
            lines.append("   эталон: " + " | ".join(row["ideal"]))
            for m, rr in zip(models, per_model):
                if j < len(rr):
                    r = rr[j]
                    flag = (" ⚠️" + ",".join(r["probs"])) if r["probs"] else ""
                    lines.append(f"   {short(m)}: " + " | ".join(r["out"]) + f"  [{r['ready']}% {r['action'] or ''}]{flag}")
    LAST.update(status="done", text="\n".join(lines))
    if notify:
        notify("🧪 Сравнение моделей готово (" + str(len(data)) + " диалогов)\n\n" + "\n".join(summary) +
               f"\n\nПодробно: {core.IG.PUBLIC_URL}/eval/last")
    return LAST["text"]


def start(arg, notify):
    if LAST["status"] == "running" and time.time() - LAST["started"] < 3600:
        return "Тест уже идёт, дождитесь отчёта."
    parts = (arg or "").split()
    n = int(parts[0]) if parts and parts[0].isdigit() else 30
    models = parts[1].split(",") if len(parts) > 1 else None
    threading.Thread(target=lambda: _safe(n, models, notify), daemon=True).start()
    return f"Запустил сравнение: {n} диалогов, модели {', '.join(models or DEFAULT_MODELS)}. Отчёт пришлю сюда (~5–10 мин)."


def _safe(n, models, notify):
    try:
        run(n, models, notify)
    except Exception as e:
        LAST.update(status="error", text="Ошибка теста: " + str(e))
        if notify:
            notify("⚠️ Ошибка теста: " + str(e)[:300])
