"""
Mijoz agentini (masalan, Express) sun'iy dialoglarda sinash — mijozlarga hech narsa yuborilmaydi.
  * "mijoz" — Haiku turli personajlarda yozadi (lotin/kirill/rus, xatolar bilan, ovozli xabar matni bilan);
  * agent — haqiqiy bot mantig'i (generate_reply), model Haiku;
  * "tekshiruvchi" — Haiku har bir javobni baholaydi: imlo xatolari (noto'g'ri -> to'g'ri), mantiq, faktlar.
Natija: GET /eval/agent (matn) + Telegram'ga qisqa hisobot. Buyruq (admin chat): /agenttest express 300
"""
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

core = None
MODEL = "claude-haiku-5-5"
LAST = {"status": "idle", "text": "Тест агента ещё не запускался. Telegram: /agenttest express 300", "started": 0}

SCRIPTS = [("uz_lat", 50), ("uz_cyr", 30), ("ru", 20)]
SCENARIOS = [
    "у тебя НЕТ сертификата автошколы, хочешь получить права с нуля, спрашиваешь цену и сроки",
    "у тебя ЕСТЬ сертификат, на занятия ходил редко, всё забыл; хочешь быстро подготовиться к экзамену",
    "у тебя ЕСТЬ сертификат, ходил регулярно; хочешь самый быстрый курс",
    "спрашиваешь только цены («нархлари қанча», «прайс»), потом говоришь, что дорого",
    "спрашиваешь, где филиалы, какой ближе к Чиланзару, и какие смены есть",
    "спрашиваешь, какие документы нужны для категории B, и нужна ли медсправка",
    "тебе 17 лет, спрашиваешь, можно ли учиться и когда сдавать",
    "ты уже ученик школы: не можешь войти в приложение, забыл пароль, бот не находит номер",
    "ты ученик: доступ закрыт из-за долга, спрашиваешь, как открыть",
    "хочешь бесплатный пробный урок, потом даёшь имя и номер телефона",
    "хочешь записаться с другом, спрашиваешь про скидку",
    "сравниваешь Express 7 и Express 10, спрашиваешь разницу и что такое «ilova bilan»",
    "говоришь «подумаю», потом «нет времени»; в итоге отказываешься",
    "пишешь голосовыми: твои сообщения — расшифровка речи с ошибками распознавания, без знаков препинания",
    "ребёнок балуется: пишешь бессмыслицу, смайлы, «салом салом», «ты кто»",
    "просишь живого администратора и номер телефона школы",
    "спрашиваешь про возврат денег и заморозку курса",
    "уже сдал теорию, нужен только автодром (вождение), спрашиваешь цену и где",
]
STYLES = ["пишешь очень коротко, 1–5 слов, без заглавных букв", "пишешь с опечатками и разговорными сокращениями",
          "пишешь вежливо и подробно", "смешиваешь узбекский и русский", "пишешь несколькими короткими сообщениями подряд"]

CLIENT_SYS = """Ты играешь КЛИЕНТА, который пишет в Telegram/Instagram автошколе Express School (Ташкент). Это тест бота.
Язык и алфавит: {script_desc}.
Твоя ситуация: {scenario}.
Стиль: {style}.
Пиши как реальный человек из Узбекистана, НЕ как бот: коротко, иногда с ошибками. Не повторяйся.
Верни ТОЛЬКО JSON: {{"messages": ["сообщение клиента", ...], "done": false}}
- 1–2 сообщения за ход. "done": true — когда ты получил ответ, записался, отказался или разговор естественно закончился.
- Если ситуация «голосовые» — каждое сообщение начинай с «🎙 » (это расшифровка речи)."""
SCRIPT_DESC = {"uz_lat": "узбекский ЛАТИНИЦЕЙ (как пишут в Узбекистане, апострофы можно пропускать)",
               "uz_cyr": "узбекский КИРИЛЛИЦЕЙ",
               "ru": "русский"}

JUDGE_SYS = """Ты — строгий проверяющий ответов ИИ-администратора автошколы Express School. Выше — его база знаний и правила.
Тебе дают последние сообщения клиента и ОТВЕТ бота. Оцени ТОЛЬКО ответ бота.
ВАЖНО: если клиент пишет кириллицей — ответ узбекской КИРИЛЛИЦЕЙ правильный, это НЕ ошибка; не предлагай переписать его латиницей.
Не добавляй в spelling пары, где «правильно» совпадает с написанным или где ты просто хвалишь.
Найди:
1) ОРФОГРАФИЯ узбекского (латиница или кириллица): неправильные слова, русизмы, кальки, неверные апострофы (o', g'),
   неверная кириллица (ў, қ, ғ, ҳ), смешение алфавитов. Для каждой ошибки — пара [как написал бот, как правильно].
2) ПРОБЛЕМЫ: не ответил на вопрос; неверный факт/цена (сверяй с базой); повторное приветствие посреди диалога;
   больше одного вопроса; не тот язык/алфавит; канцелярит или неестественная фраза; пропустил логику продажи
   (сертификат → посещаемость → тариф); навязчиво просит номер; слишком длинно/сухо.
Верни ТОЛЬКО JSON: {"spelling": [["неправильно", "правильно"]], "issues": ["коротко, по-русски"], "score": 1-5}
score: 5 — как идеальный живой администратор, 1 — плохо. Не придумывай ошибок, если их нет."""


def init(bot_module):
    global core
    core = bot_module


def _json(raw):
    try:
        return core.parse_json(raw) or {}
    except Exception:
        return {}


def _persona(rnd):
    script = rnd.choices([s for s, _ in SCRIPTS], weights=[w for _, w in SCRIPTS])[0]
    return {"script": script, "scenario": rnd.choice(SCENARIOS), "style": rnd.choice(STYLES)}


def _client_turn(p, hist):
    sys = CLIENT_SYS.format(script_desc=SCRIPT_DESC[p["script"]], scenario=p["scenario"], style=p["style"])
    msgs = []
    for h in hist:                       # mijoz uchun rollar teskari: bot = "user", mijoz = "assistant"
        role = "assistant" if h["r"] == "u" else "user"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + h["t"]
        else:
            msgs.append({"role": role, "content": h["t"]})
    if not msgs or msgs[-1]["role"] == "assistant":
        msgs.append({"role": "user", "content": "(начни разговор)" if not msgs else "(продолжай)"})
    d = _json(core.claude(sys, msgs, max_tokens=300, model=MODEL))
    out = [str(x).strip() for x in (d.get("messages") or []) if str(x).strip()][:2]
    voice = "голосов" in p["scenario"]
    out = [(core.STT.VOICE_PREFIX + re.sub(r"^🎙\s*", "", x)) if voice else re.sub(r"^🎙\s*", "", x) for x in out]
    return out, bool(d.get("done"))


def _judge(slug, client_msgs, reply):
    user = ("КЛИЕНТ: " + " / ".join(client_msgs)[-600:] + "\n\nОТВЕТ БОТА:\n" + "\n".join(reply))
    d = _json(core.claude(JUDGE_SYS, [{"role": "user", "content": user}], max_tokens=600, model=MODEL,
                          cache_prefix=core.AGENTS.prompt(slug)))
    cyr = re.compile(r"[А-Яа-яЎўҚқҒғҲҳ]")
    sp = [x for x in (d.get("spelling") or []) if isinstance(x, list) and len(x) == 2 and str(x[0]).strip() != str(x[1]).strip()
          and not re.search(r"(?i)\(?(to'g'ri|тўғри|верно|ок|ok|правильно)\)?\s*$", str(x[1]))
          and not (cyr.search(str(x[0])) and not cyr.search(str(x[1])))]          # kirill -> lotin «tuzatish» — xato emas
    try:
        score = int(d.get("score") or 0)
    except Exception:
        score = 0
    return {"spelling": sp[:12], "issues": [str(x)[:200] for x in (d.get("issues") or [])][:6], "score": score}


def run_dialog(slug, seed, max_turns=6):
    rnd = random.Random(seed)
    p = _persona(rnd)
    c = {"history": [], "facts": {}, "readiness": 0, "script": "", "lang_pref": "", "status": "active",
         "chat_id": "eval", "agent": slug, "no_fallback": True}
    turns = []
    for _ in range(max_turns):
        cm, done = _client_turn(p, c["history"])
        if not cm:
            break
        for x in cm:
            c["history"].append({"r": "u", "t": x, "ts": time.time()})
        script = core.client_script(c)
        t0 = time.time()
        r = core.generate_reply(c, script, model=MODEL) or {}
        out = r.get("messages") or []
        if r.get("show"):
            show = r["show"] if isinstance(r["show"], list) else [r["show"]]
            out_full = out[:-1] + ["[блок: " + ", ".join(show) + "]"] + out[-1:] if out else out
        else:
            out_full = out
        voice_ok = None
        if core.client_used_voice(c):
            spoken, _ = core.split_written(out, r.get("voice"), script)
            voice_ok = bool(spoken)
        j = _judge(slug, cm, out) if out else {"spelling": [], "issues": ["ПУСТОЙ ОТВЕТ"], "score": 1}
        if voice_ok is False:
            j["issues"].append("ГОЛОС: ответ не озвучен")
        turns.append({"client": cm, "bot": out_full, "voice": r.get("voice") or "", "script": script,
                      "action": r.get("action") or "", "ms": int((time.time() - t0) * 1000), **j})
        for m in out:
            c["history"].append({"r": "a", "t": m, "ts": time.time()})
        for k in ("name", "phone", "need", "offer"):
            if r.get(k):
                c["facts"][k] = str(r[k])[:200]
        if done or r.get("action") in ("stop", "lead", "ignore"):
            break
    return {"persona": p, "turns": turns}


def report(slug, dialogs, spent_usd, secs):
    turns = [t for d in dialogs for t in d["turns"]]
    sp, iss = {}, {}
    for t in turns:
        for w, rgt in t["spelling"]:
            k = (str(w).strip(), str(rgt).strip())
            sp[k] = sp.get(k, 0) + 1
        for x in t["issues"]:
            k = re.sub(r"[«»\"'].*?[«»\"']", "…", x.lower())[:80]
            iss[k] = iss.get(k, 0) + 1
    scores = [t["score"] for t in turns if t["score"]]
    avg = sum(scores) / max(1, len(scores))
    bad = [t for t in turns if t["score"] and t["score"] <= 2]
    lines = [f"ТЕСТ АГЕНТА «{core.AGENTS.name(slug)}» · модель {MODEL}",
             f"Диалогов: {len(dialogs)}, ответов бота: {len(turns)}, средняя оценка {avg:.2f}/5, "
             f"плохих (≤2): {len(bad)}, с орфоошибками: {sum(1 for t in turns if t['spelling'])}",
             f"Время: {secs / 60:.0f} мин · потрачено ≈ ${spent_usd:.2f}", "",
             "ЧАСТЫЕ ОРФОГРАФИЧЕСКИЕ ОШИБКИ (раз · как писал → как правильно):"]
    lines += [f"{n} · {w} → {r}" for (w, r), n in sorted(sp.items(), key=lambda x: -x[1])[:150]]
    lines += ["", "ЧАСТЫЕ ПРОБЛЕМЫ (раз · что):"]
    lines += [f"{n} · {k}" for k, n in sorted(iss.items(), key=lambda x: -x[1])[:80]]
    lines += ["", "ХУДШИЕ ОТВЕТЫ:"]
    for t in sorted(bad, key=lambda x: x["score"])[:60]:
        lines.append(f"👤 {' / '.join(t['client'])[:300]}\n🤖 {' | '.join(t['bot'])[:700]}\n   ⚠️ {t['score']}/5: {'; '.join(t['issues'])}")
    lines += ["", "ВСЕ ДИАЛОГИ:"]
    for i, d in enumerate(dialogs):
        p = d["persona"]
        lines.append(f"===== #{i + 1} [{p['script']}] {p['scenario']} · {p['style']}")
        for t in d["turns"]:
            lines.append("👤 " + " / ".join(t["client"]))
            lines.append("🤖 " + " | ".join(t["bot"]) + (f"\n   🎙 {t['voice']}" if t["voice"] else ""))
            flags = [f"{t['score']}/5"] + [f"{w}→{r}" for w, r in t["spelling"]] + t["issues"]
            lines.append("   " + " · ".join(flags))
    return "\n".join(lines), avg, sp, iss


def run(slug, n, notify=None):
    from evalrun import usage_snapshot, usage_delta
    LAST.update(status="running", started=time.time(), text=f"Идёт тест: {n} диалогов…")
    before = usage_snapshot()
    t0 = time.time()
    dialogs = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(run_dialog, slug, 1000 + i) for i in range(n)]
        for k, f in enumerate(futs):
            try:
                dialogs.append(f.result())
            except Exception as e:
                dialogs.append({"persona": {"script": "?", "scenario": "ERROR " + repr(e)[:150], "style": ""}, "turns": []})
            if (k + 1) % 25 == 0:
                LAST["text"] = f"Идёт тест: готово {k + 1} из {n} диалогов…"
    spent = usage_delta(before, usage_snapshot())
    usd = core.usage_cost(spent) if spent else 0.0
    text, avg, sp, iss = report(slug, dialogs, usd, time.time() - t0)
    LAST.update(status="done", text=text)
    core.db_put("agenteval:last", {"status": "done", "text": text, "started": LAST["started"]})
    if notify:
        top = sorted(sp.items(), key=lambda x: -x[1])[:8]
        notify(f"🧪 Тест агента готов: {len(dialogs)} диалогов, средняя оценка {avg:.2f}/5, ≈ ${usd:.2f}\n"
               "Частые ошибки: " + ", ".join(f"{w}→{r}" for (w, r), _ in top) +
               f"\n\nПодробно: {core.IG.PUBLIC_URL}/eval/agent")
    return text


def start(arg, notify):
    if LAST["status"] == "running" and time.time() - LAST["started"] < 3 * 3600:
        return "Тест уже идёт, дождитесь отчёта."
    parts = (arg or "").split()
    slug = parts[0] if parts and not parts[0].isdigit() else "express"
    n = next((int(x) for x in parts if x.isdigit()), 300)
    if not core.AGENTS.get(slug):
        return f"Нет агента «{slug}». Агенты: {', '.join(core.AGENTS.agents())}"
    n = max(1, min(n, 500))

    def go():
        try:
            run(slug, n, notify)
        except Exception as e:
            LAST.update(status="error", text="Ошибка теста: " + str(e))
            if notify:
                notify("⚠️ Ошибка теста агента: " + str(e)[:300])
    threading.Thread(target=go, daemon=True).start()
    return (f"Запустил тест агента «{core.AGENTS.name(slug)}»: {n} диалогов, модель {MODEL} (клиент, бот и проверка). "
            f"Клиентам ничего не отправляется. Примерно 30–60 минут — отчёт пришлю сюда.")
