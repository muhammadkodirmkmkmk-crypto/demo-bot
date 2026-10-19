"""
Rahbar rejimi: admin chatida ИИ-продавец — bu sizning sotuvchingiz.
 - Siz unga yozasiz (matn yoki ovoz): u nima bo'layotganini aytadi, savollarga javob beradi.
 - Ko'rsatma bersangiz ("narx so'rasa avval biznesini so'ra") — qoida sifatida saqlaydi va barcha suhbatlarda bajaradi,
   nimasi o'zgarganini yozib beradi.
 - Lid kartochkasiga javob (reply) — shu mijoz konteksti bilan tuzatish.
 - /test — o'zingiz mijoz sifatida sinab ko'rish rejimi.
"""
import json
import time
import hashlib
from datetime import datetime

core = None
MAX_RULES = 40
_S = {"loaded": False, "rules": [], "hist": [], "rmap": {}, "test": False, "notify": "all", "digest_day": "", "voice": "",
      "voice_id": "", "voice_name": "", "prev_voice": None, "voice_list": []}
KEYS = ("rules", "hist", "rmap", "test", "notify", "digest_day", "voice", "voice_id", "voice_name", "prev_voice", "voice_list")
VOICE_MODES = {"lively": (0.5, "🙂 Живой (Stability 0.5) — эмоционально, как в обычных роликах"),
               "calm": (0.75, "🧘 Спокойный (Stability 0.75) — ровно и уверенно")}
VOICE_SAMPLE = {"uz": "Assalomu alaykum, Aziz aka, xabaringiz uchun katta rahmat. Sayt qaysi biznes uchun kerakligini aytsangiz, "
                      "sizga eng mos variantni tanlab beraman. AI agent esa Instagram'da va Telegram'da mijozlarga 24/7 javob beradi.",
                "ru": "Здравствуйте, Азиз, спасибо, что написали. Расскажите, для какого бизнеса нужен сайт, "
                      "и я подберу самый подходящий вариант. Цену написал вам ниже сообщением."}

BOSS_PROMPT = """Ты — ИИ-продавец компании AI Business UZ. Сейчас ты пишешь не клиенту, а своему руководителю (владельцу компании) в Telegram.
Ты его сотрудник: докладываешь по делу, коротко и честно, по-русски, без воды и без markdown-заголовков. Можно короткие списки через «•».

Что ты умеешь:
1. Отчитываться: что происходит, кто писал, кто горячий, кому звонить, что хотят клиенты — по данным ниже. Не выдумывай цифры и клиентов, которых нет в данных.
2. Принимать указания, как продавать. Если руководитель говорит, как отвечать клиентам, что предлагать, чего не делать, как исправить ответ —
   сформулируй это как чёткое правило для себя (одно предложение, в повелительном наклонении, на русском) и добавь в add_rules.
   Если указание меняет или отменяет существующее правило — укажи его номер в remove_rules (и при необходимости добавь новую формулировку).
   Не добавляй правило, если это просто вопрос или разговор.
3. Если руководитель ответил на карточку клиента — он говорит именно про этот диалог (контекст ниже). Объясни, что ты понял, и сделай правило, чтобы так было во всех похожих случаях.
4. После изменения правил кратко скажи, как теперь будешь вести себя с клиентами (1–2 предложения, на примере).
5. Правила не могут менять цены из базы, разрешать обман клиентов, давление или спам — такое вежливо откажись добавлять и объясни почему.

Ответ — строго один JSON-объект:
{"reply": "текст руководителю", "add_rules": ["..."], "remove_rules": [номера]}"""


def init(bot_module):
    global core
    core = bot_module


def _load():
    if _S["loaded"]:
        return
    _S["loaded"] = True
    saved = core.db_get("boss:state") or {}
    for k in KEYS:
        if k in saved:
            _S[k] = saved[k]
    if _S["voice"] in VOICE_MODES:
        core.STT.TTS_STABILITY = VOICE_MODES[_S["voice"]][0]
    if _S["voice_id"] and not core.STT.TTS_VOICE_ID:
        core.STT._VOICE_CACHE["resolved"] = _S["voice_id"]


def _save():
    core.db_put("boss:state", {k: _S[k] for k in KEYS})


def is_admin_chat(chat_id):
    return str(chat_id) == str(core.REPORT_CHAT_ID)


def test_mode():
    _load()
    return bool(_S["test"])

# --------------------------------------------------------------------------
# Qoidalar (barcha suhbatlarga qo'shiladi)
# --------------------------------------------------------------------------
def rules():
    _load()
    return list(_S["rules"])


def rules_block(c):
    """Rahbar ko'rsatmalari — faqat o'zimizning (AI Business) suhbatlar uchun"""
    rs = rules()
    if not rs or core.IG.prompt_for(c) is not core.SYSTEM_PROMPT:
        return ""
    return ("\n\nУКАЗАНИЯ РУКОВОДИТЕЛЯ (выполняй обязательно; они важнее общих правил, но цены — только из базы):\n" +
            "\n".join(f"{i + 1}. {r['t']}" for i, r in enumerate(rs)))


def rules_text():
    rs = rules()
    if not rs:
        return "Указаний пока нет. Просто напишите мне, как продавать — я запомню."
    return "📋 Ваши указания (работают во всех диалогах):\n" + "\n".join(f"{i + 1}. {r['t']}" for i, r in enumerate(rs)) + \
        "\n\nУдалить: /rule_del номер"

# --------------------------------------------------------------------------
# Kartochka <-> mijoz (reply orqali tuzatish, tugmalar)
# --------------------------------------------------------------------------
def short_id(key):
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def key_by_short(sid):
    with core.LOCK:
        for k in core.STATE["chats"]:
            if short_id(k) == sid:
                return k
    return None


def remember_card(message_id, key):
    _load()
    _S["rmap"][str(message_id)] = key
    if len(_S["rmap"]) > 400:
        for k in list(_S["rmap"])[:100]:
            _S["rmap"].pop(k, None)
    _save()


def card_buttons(key):
    s = short_id(key)
    return {"inline_keyboard": [[{"text": "📞 Позвонил", "callback_data": "d:called:" + s},
                                 {"text": "✅ Купил", "callback_data": "d:won:" + s},
                                 {"text": "❌ Отказ", "callback_data": "d:lost:" + s}]]}


def current_voice():
    vid = core.STT.resolve_voice() if core.STT.ELEVEN_KEY else ""
    return vid, _S.get("voice_name") or core.STT.TTS_VOICE_NAME


def list_voices(chat_id, gender="male"):
    """ElevenLabs kutubxonasidan o'zbekcha ovozlar: namunasi + «Выбрать» tugmasi"""
    found = []
    for q in (f"/v1/shared-voices?page_size=10&language=uz&gender={gender}&sort=usage_character_count_1y",
              f"/v1/shared-voices?page_size=10&language=uz&gender={gender}",
              "/v1/shared-voices?page_size=10&search=uzbek"):
        found = [v for v in core.STT._api("GET", q).get("voices") or [] if v.get("voice_id")]
        if found:
            break
    if not found:
        core.send_msg(chat_id, "Не удалось получить голоса из библиотеки ElevenLabs. Проверьте ключ (нужно право на голоса).")
        return
    _S["voice_list"] = [{"id": v["voice_id"], "owner": v.get("public_owner_id", ""), "name": v.get("name", "")[:60],
                         "preview": v.get("preview_url", "")} for v in found[:8]]
    _save()
    vid, vname = current_voice()
    core.send_msg(chat_id, f"Сейчас голос: {vname}. Ниже {len(_S['voice_list'])} узбекских голосов "
                           f"({'мужские' if gender == 'male' else 'женские'}) — послушайте и нажмите «Выбрать».\n"
                           "После выбора пришлю пример с нашими фразами. Женские: /voices female")
    for i, v in enumerate(_S["voice_list"]):
        src = found[i]
        cap = f"{i + 1}. {v['name']}"
        desc = " · ".join(x for x in (src.get("accent"), src.get("age"), src.get("descriptive"), src.get("use_case")) if x)
        if desc:
            cap += f"\n{desc}"
        btn = {"inline_keyboard": [[{"text": "✅ Выбрать этот голос", "callback_data": f"vp:{i}"}]]}
        if v["preview"]:
            r = core.tg("sendAudio", {"chat_id": chat_id, "audio": v["preview"], "caption": cap[:1000],
                                      "title": v["name"], "reply_markup": btn})
            if r.get("ok"):
                continue
        core.tg("sendMessage", {"chat_id": chat_id, "text": cap + "\n(без примера)", "reply_markup": btn})


def pick_voice(chat_id, idx):
    try:
        v = _S["voice_list"][idx]
    except Exception:
        core.send_msg(chat_id, "Список устарел — откройте заново: /voices")
        return
    old_id, old_name = current_voice()
    added = core.STT._api("POST", f"/v1/voices/add/{v['owner']}/{v['id']}", {"new_name": v["name"]}) if v["owner"] else {}
    new_id = added.get("voice_id") or v["id"]
    set_voice(new_id, v["name"], (old_id, old_name))
    core.tg("sendMessage", {"chat_id": chat_id, "text": f"🎙 Голос бота теперь: {v['name']}. Вот как он звучит с нашими фразами 👇",
                            "reply_markup": {"inline_keyboard": [[{"text": f"↩︎ Вернуть {old_name}"[:60], "callback_data": "vb"}]]}})
    send_voice_sample(chat_id)


def set_voice(vid, name, prev=None):
    if prev is not None:
        _S["prev_voice"] = list(prev)
    _S["voice_id"], _S["voice_name"] = vid, name
    core.STT._VOICE_CACHE["resolved"] = vid
    _save()


def send_voice_sample(chat_id):
    for lang in ("uz", "ru"):
        audio = core.STT.tts(core.voice_text(VOICE_SAMPLE[lang], "uz_lat" if lang == "uz" else "ru"), lang)
        if audio:
            core.tg_send_voice(chat_id, audio)
        else:
            core.send_msg(chat_id, "Не удалось озвучить пример (проверьте ключ ElevenLabs).")
            break


def on_callback(cq):
    """Kartochkadagi tugmalar"""
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if data.startswith("v:") and is_admin_chat(chat_id):
        core.tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Меняю голос…"})
        command(chat_id, "/voice " + data[2:])
        return True
    if data.startswith("r:") and is_admin_chat(chat_id):
        _, how, sid = (data.split(":", 2) + ["", ""])[:3]
        key = key_by_short(sid)
        if key:
            ts = snooze(key, how)
            core.tg("answerCallbackQuery", {"callback_query_id": cq["id"],
                                            "text": "⏰ Напомню " + datetime.fromtimestamp(ts, core.TZ).strftime("%d.%m %H:%M")})
        return True
    if data.startswith("vp:") and is_admin_chat(chat_id):
        _load()
        core.tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Ставлю голос…"})
        pick_voice(chat_id, int(data[3:]) if data[3:].isdigit() else -1)
        return True
    if data == "vb" and is_admin_chat(chat_id):
        _load()
        core.tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Возвращаю…"})
        if _S.get("prev_voice"):
            vid, name = _S["prev_voice"]
            set_voice(vid, name, current_voice())
            core.send_msg(chat_id, f"↩︎ Вернул голос: {name}")
            send_voice_sample(chat_id)
        return True
    if not data.startswith("d:"):
        return False
    _, action, sid = (data.split(":", 2) + ["", ""])[:3]
    key = key_by_short(sid)
    if not key:
        core.tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Клиент не найден"})
        return True
    c = core.chat_state(key)
    if str(chat_id) != str(core.report_target(c)) and not is_admin_chat(chat_id):
        core.tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Нет доступа"})
        return True
    core.ADMIN.set_deal(key, action, 0)
    label = {"called": "📞 Отмечено: позвонили", "won": "✅ Отмечено: купил. Ответьте на карточку суммой, например 590",
             "lost": "❌ Отмечено: отказ"}.get(action, "Готово")
    core.tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": label[:190]})
    mark = {"called": "📞 Позвонили", "won": "✅ Купил", "lost": "❌ Отказ"}.get(action, "")
    if msg.get("message_id") and mark:
        core.tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg["message_id"],
                                           "reply_markup": {"inline_keyboard": [[{"text": mark + " · изменить", "callback_data": "x"}]] +
                                                            card_buttons(key)["inline_keyboard"]}})
    return True

# --------------------------------------------------------------------------
# Rahbar bilan suhbat
# --------------------------------------------------------------------------
def lead_context(key):
    c = core.STATE["chats"].get(key)
    if not c:
        return ""
    f = c.get("facts") or {}
    lines = [f"Клиент: {c.get('name') or '-'} ({core.ADMIN.CH_NAMES.get(core.chat_channel(c), '')}), готовность {c.get('readiness', 0)}%"]
    lines += [f"{k}: {v}" for k, v in f.items() if v]
    lines.append("Последние сообщения диалога:")
    for h in c.get("history", [])[-12:]:
        who = "Клиент" if h["r"] == "u" else ("Менеджер" if h.get("human") else "Ты")
        lines.append(f"{who}: {h['t'].replace(core.STT.VOICE_PREFIX, '(голосовое) ')[:300]}")
    return "\n".join(lines)


def data_context():
    try:
        d = core.ADMIN.build("today")
        week = core.ADMIN.build("7d")
    except Exception as e:
        return "Данные недоступны: " + str(e)
    t, w = d["totals"], week["totals"]
    lines = [f"Сегодня: диалогов {t['dialogs']}, контактов {t['leads']}, покупок {t['won']}, расход ${d['spend']:.2f}.",
             f"За 7 дней: диалогов {w['dialogs']}, контактов {w['leads']}, покупок {w['won']}, выручка ${w['revenue']:.0f}."]
    calls = [x for x in week["calls"] if x["todo"]][:8]
    if calls:
        lines.append("Нужно позвонить:")
        lines += [f"• {x['who']} {x['phone']} — {x['want'][:120]}" for x in calls]
    hot = [x for x in week["leads"] if x["lvl"] in (3, 4)][:8]
    if hot:
        lines.append("Тёплые/горячие без контакта:")
        lines += [f"• {x['who']} ({x['readiness']}%) — {(x['facts'].get('need') or x['facts'].get('business') or '')[:100]}" for x in hot]
    return "\n".join(lines)


def handle_text(chat_id, text, reply_to=None):
    """Admin yozdi. True — javob berildi (mijoz sifatida qayta ishlanmaydi)"""
    _load()
    if _S["test"]:
        return False
    key = _S["rmap"].get(str((reply_to or {}).get("message_id") or ""))
    # kartochkaga raqam bilan javob — sotuv summasi
    if key and text.strip().replace("$", "").replace(" ", "").isdigit():
        core.ADMIN.set_deal(key, "won", float(text.strip().replace("$", "").replace(" ", "")))
        core.send_msg(chat_id, f"✅ Записал продажу: ${text.strip().replace('$', '')}")
        return True
    ctx = "ДАННЫЕ CRM:\n" + data_context() + "\n\nТЕКУЩИЕ ПРАВИЛА:\n" + \
        ("\n".join(f"{i + 1}. {r['t']}" for i, r in enumerate(_S["rules"])) or "(нет)")
    if key:
        ctx += "\n\nРУКОВОДИТЕЛЬ ОТВЕТИЛ НА КАРТОЧКУ ЭТОГО КЛИЕНТА:\n" + lead_context(key)
    msgs = []
    for h in _S["hist"][-12:]:
        msgs.append({"role": h["r"], "content": h["t"]})
    msgs.append({"role": "user", "content": ctx + "\n\nСООБЩЕНИЕ РУКОВОДИТЕЛЯ:\n" + text})
    core.tg("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    core.CTX.ch, core.CTX.chat = "test", None
    raw = core.claude(BOSS_PROMPT, msgs, max_tokens=900)
    d = core.parse_json(raw)
    if not d or "reply" not in d:
        d = {"reply": raw.strip() or "Не получилось обработать, повторите, пожалуйста.", "add_rules": [], "remove_rules": []}
    removed, added = [], []
    for n in sorted({int(x) for x in d.get("remove_rules") or [] if str(x).isdigit()}, reverse=True):
        if 1 <= n <= len(_S["rules"]):
            removed.append(_S["rules"].pop(n - 1)["t"])
    for r in d.get("add_rules") or []:
        r = str(r).strip()
        if r and len(_S["rules"]) < MAX_RULES and r not in [x["t"] for x in _S["rules"]]:
            _S["rules"].append({"t": r[:400], "ts": time.time()})
            added.append(r[:400])
    reply = str(d.get("reply") or "").strip()
    if added or removed:
        reply += "\n\n✏️ Что изменилось в моей работе:"
        reply += "".join("\n− " + r for r in removed) + "".join("\n+ " + r for r in added)
        reply += f"\n\nВсего указаний: {len(_S['rules'])} · /rules"
    _S["hist"] = (_S["hist"] + [{"r": "user", "t": text[:1500]}, {"r": "assistant", "t": json.dumps(
        {"reply": reply[:1500]}, ensure_ascii=False)}])[-20:]
    _save()
    core.send_msg(chat_id, reply[:4000])
    return True


def command(chat_id, text):
    """/rules, /rule_del, /test, /notify, /digest. True — bajarildi"""
    if not is_admin_chat(chat_id):
        return False
    _load()
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    if cmd == "/rules":
        core.send_msg(chat_id, rules_text())
    elif cmd == "/rule_del":
        try:
            n = int(parts[1])
            r = _S["rules"].pop(n - 1)
            _save()
            core.send_msg(chat_id, f"Удалил указание {n}: «{r['t']}»\n\n" + rules_text())
        except Exception:
            core.send_msg(chat_id, "Формат: /rule_del 2")
    elif cmd == "/test":
        _S["test"] = not _S["test"]
        _save()
        core.send_msg(chat_id, "🧪 Режим теста включён: пишите мне как клиент, я отвечу как продавец. Выйти — /test"
                      if _S["test"] else "👔 Режим руководителя: пишите мне указания и вопросы, я докладываю. Тест — /test")
    elif cmd == "/notify":
        _S["notify"] = "hot" if _S["notify"] == "all" else "all"
        _save()
        core.send_msg(chat_id, "Уведомления: только горячие и контакты." if _S["notify"] == "hot"
                      else "Уведомления: о каждом новом диалоге + горячие и контакты.")
    elif cmd == "/digest":
        send_digest()
    elif cmd == "/voices":
        list_voices(chat_id, "female" if len(parts) > 1 and parts[1].lower().startswith(("f", "ж")) else "male")
    elif cmd == "/voice":
        mode = parts[1].lower() if len(parts) > 1 else ""
        if mode in VOICE_MODES:
            _S["voice"] = mode
            core.STT.TTS_STABILITY = VOICE_MODES[mode][0]
            _save()
        cur = next((m for m, v in VOICE_MODES.items() if v[0] == core.STT.TTS_STABILITY), "lively")
        core.tg("sendMessage", {"chat_id": chat_id, "text": "Голос бота сейчас: " + VOICE_MODES[cur][1] +
                                "\n\nНиже — пример, как он звучит. Сменить:",
                                "reply_markup": {"inline_keyboard": [[{"text": ("✅ " if m == cur else "") + m.capitalize(),
                                                                       "callback_data": "v:" + m} for m in VOICE_MODES]]}})
        send_voice_sample(chat_id)
    else:
        return False
    return True

# --------------------------------------------------------------------------
# Xabarnomalar
# --------------------------------------------------------------------------
def notify_new_dialog(c, text):
    _load()
    ch = core.chat_channel(c)
    if _S["notify"] != "all" or ch not in ("tg", "ig") or not core.REPORT_CHAT_ID:
        return
    if str(core.report_target(c)) != str(core.REPORT_CHAT_ID):
        return            # mijoz-biznesning suhbatlari — ularning o'z chatiga
    who = c.get("name") or "Клиент"
    if c.get("username"):
        who += " @" + c["username"]
    t = text.replace(core.STT.VOICE_PREFIX, "🎙 ")
    core.send_msg(core.REPORT_CHAT_ID, f"🆕 {core.ADMIN.CH_NAMES[ch]} · {who}: «{t[:160]}»")


def send_digest():
    d = core.ADMIN.build("today")
    calls = [x for x in d["calls"] if x["todo"]]
    lines = [core.ADMIN.text_summary("today")]
    if calls:
        lines.append("\n📞 Позвонить (" + str(len(calls)) + "):")
        lines += [f"• {x['who']} {x['phone']} — {x['want'][:100]}" for x in calls[:10]]
    if _S["rules"]:
        lines.append(f"\n📋 Работаю по {len(_S['rules'])} вашим указаниям · /rules")
    core.tg("sendMessage", {"chat_id": core.REPORT_CHAT_ID, "text": "\n".join(lines)[:4000],
                            "reply_markup": {"inline_keyboard": [[{"text": "📊 Панель", "web_app": {"url": core.ADMIN.panel_url()}}]]}})


def check_reminders():
    """Muddati kelgan qo'ng'iroq eslatmalari — admin'ga xabar (raqam + izoh + tugmalar)"""
    now = time.time()
    with core.LOCK:
        due = [(k, c) for k, c in core.STATE["chats"].items()
               if (c.get("remind") or {}).get("ts") and not c["remind"].get("sent") and not c["remind"].get("done")
               and c["remind"]["ts"] <= now]
    for key, c in due:
        f = c.get("facts") or {}
        tel, pretty = core.ADMIN.fmt_phone(f.get("phone", ""))
        who = c.get("name") or "Клиент"
        if c.get("username"):
            who += " @" + c["username"]
        want = f.get("need") or f.get("note") or f.get("business") or ""
        lines = [f"⏰ Напоминание: позвонить", f"👤 {who}"]
        if pretty:
            lines.append(f"📞 {pretty}")
        if c["remind"].get("text"):
            lines.append(f"💬 {c['remind']['text']}")
        if want:
            lines.append(f"🎯 {want[:160]}")
        s = short_id(key)
        kb = card_buttons(key)["inline_keyboard"] + [[{"text": "⏰ +1 час", "callback_data": "r:60:" + s},
                                                      {"text": "⏰ Завтра 10:00", "callback_data": "r:tm:" + s}]]
        res = core.tg("sendMessage", {"chat_id": core.REPORT_CHAT_ID, "text": "\n".join(lines), "reply_markup": {"inline_keyboard": kb}})
        mid = (res.get("result") or {}).get("message_id")
        if mid:
            remember_card(mid, key)
        with core.LOCK:
            c["remind"]["sent"] = True
        core.save_chat(key)


def snooze(key, how):
    from datetime import timedelta
    if how == "tm":
        t = datetime.now(core.TZ) + timedelta(days=1)
        ts = t.replace(hour=10, minute=0, second=0, microsecond=0).timestamp()
    else:
        ts = time.time() + int(how) * 60
    old = (core.STATE["chats"].get(key, {}).get("remind") or {}).get("text", "")
    core.ADMIN.set_remind(key, ts, old)
    return ts


def maybe_digest():
    """Har kuni 21:00 (Toshkent) — kunlik hisobot; eslatmalarni tekshirish (har daqiqa)"""
    try:
        check_reminders()
    except Exception as e:
        print("Reminders error:", e)
    _load()
    now = datetime.now(core.TZ)
    day = now.strftime("%Y-%m-%d")
    if now.hour >= 21 and _S["digest_day"] != day and core.REPORT_CHAT_ID:
        _S["digest_day"] = day
        _save()
        send_digest()
