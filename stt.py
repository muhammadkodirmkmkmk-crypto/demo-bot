"""
Ovozli xabarlarni matnga aylantirish (speech-to-text).

Muhit o'zgaruvchilari (bittasi yetarli):
  ELEVENLABS_API_KEY  — ElevenLabs Scribe (o'zbek tilini yaxshi taniydi), model: STT_MODEL (default scribe_v2)
  OPENAI_API_KEY      — OpenAI, model: STT_OPENAI_MODEL (default whisper-1)
"""
import os
import json
import uuid
import urllib.request
import urllib.error

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ELEVEN_MODELS = [m for m in [os.environ.get("STT_MODEL", "scribe_v2"), "scribe_v1"] if m]
OPENAI_MODEL = os.environ.get("STT_OPENAI_MODEL", "whisper-1")
MAX_BYTES = 20 * 1024 * 1024


def configured():
    return bool(ELEVEN_KEY or OPENAI_KEY)


def provider():
    return "elevenlabs" if ELEVEN_KEY else ("openai" if OPENAI_KEY else "none")


def fetch(url, timeout=30):
    """Fayl yuklab olish (Telegram file API yoki Instagram CDN)"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
            return data if len(data) <= MAX_BYTES else b""
    except Exception as e:
        print("STT fetch error:", str(url).split("?")[0], e)
        return b""


def _multipart(fields, file_field, filename, data, mime):
    boundary = "----stt" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    out.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode())
    out.append(data)
    out.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def _post(url, headers, fields, filename, data, mime, timeout=90):
    body, ctype = _multipart(fields, "file", filename, data, mime)
    req = urllib.request.Request(url, data=body, method="POST", headers=dict(headers, **{"Content-Type": ctype}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        print("STT request error:", e)
        return 0, {}


def transcribe(data, filename="voice.ogg", mime="audio/ogg"):
    """Ovozni matnga aylantiradi. Xato bo'lsa — bo'sh satr."""
    if not data:
        return ""
    if ELEVEN_KEY:
        for model in ELEVEN_MODELS:
            st, res = _post("https://api.elevenlabs.io/v1/speech-to-text", {"xi-api-key": ELEVEN_KEY},
                            {"model_id": model}, filename, data, mime)
            if st == 200 and (res.get("text") or "").strip():
                return res["text"].strip()
            print("STT elevenlabs error:", model, st, json.dumps(res)[:200])
            if st not in (400, 404, 422):
                break
    if OPENAI_KEY:
        st, res = _post("https://api.openai.com/v1/audio/transcriptions", {"Authorization": "Bearer " + OPENAI_KEY},
                        {"model": OPENAI_MODEL}, filename, data, mime)
        if st == 200 and (res.get("text") or "").strip():
            return res["text"].strip()
        print("STT openai error:", st, json.dumps(res)[:200])
    return ""


VOICE_PREFIX = "[голосовое сообщение, расшифровка] "
VOICE_FALLBACK = "[клиент отправил голосовое — прочитать нельзя; вежливо попроси написать текстом]"


def voice_note(text):
    """Model uchun belgi: bu ovozli xabarning matni"""
    return VOICE_PREFIX + text


# --------------------------------------------------------------------------
# Matn -> ovoz (javobni ovozli xabar qilib yuborish)
# --------------------------------------------------------------------------
VOICE_REPLIES = os.environ.get("VOICE_REPLIES", "1") != "0"
TTS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
TTS_MODEL = os.environ.get("TTS_MODEL", "eleven_v3")          # o'zbek tili faqat v3 da
TTS_FORMAT = os.environ.get("TTS_FORMAT", "mp3_44100_64")
_VOICE_CACHE = {"id": None}


def tts_enabled():
    return VOICE_REPLIES and bool(ELEVEN_KEY)


def _first_voice():
    """Sozlangan ovoz topilmasa — akkauntdagi birinchi ovoz"""
    if _VOICE_CACHE["id"]:
        return _VOICE_CACHE["id"]
    try:
        req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": ELEVEN_KEY})
        with urllib.request.urlopen(req, timeout=20) as r:
            voices = json.loads(r.read()).get("voices") or []
        if voices:
            _VOICE_CACHE["id"] = voices[0]["voice_id"]
    except Exception as e:
        print("TTS voices error:", e)
    return _VOICE_CACHE["id"]


def pcm_to_wav(pcm, rate=16000):
    """16-bit mono PCM -> WAV (Instagram mp3 ni qabul qilmaydi)"""
    import struct
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def _tts_call(text, voice, model, lang, fmt=None):
    body = {"text": text, "model_id": model}
    if lang and model != "eleven_multilingual_v2":
        body["language_code"] = lang
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format={fmt or TTS_FORMAT}",
        data=json.dumps(body).encode(), method="POST",
        headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return 200, r.read()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read()[:300].decode("utf-8", "ignore")
        except Exception:
            detail = ""
        print("TTS error:", model, voice, e.code, detail)
        return e.code, b""
    except Exception as e:
        print("TTS error:", e)
        return 0, b""


def tts(text, lang="uz", wav=False):
    """Matnni ovozga aylantiradi: mp3 (Telegram) yoki wav (Instagram). Xato bo'lsa — b''"""
    if not tts_enabled() or not text.strip():
        return b""
    fmt = "pcm_16000" if wav else None
    voice = TTS_VOICE
    st, audio = _tts_call(text, voice, TTS_MODEL, lang, fmt)
    if st in (400, 404) and not audio:
        alt = _first_voice()
        if alt and alt != voice:
            st, audio = _tts_call(text, alt, TTS_MODEL, lang, fmt)
    if not audio and lang == "ru":
        st, audio = _tts_call(text, _VOICE_CACHE["id"] or voice, "eleven_multilingual_v2", None, fmt)
    return pcm_to_wav(audio) if (wav and audio) else audio
