
import os
import re
import sqlite3
import asyncio
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BotCommand, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

# Optional tiny LLM helper
try:
    from llm import short_reply as llm_short_reply
except Exception:
    llm_short_reply = None

# ── ENV ────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "1") == "1"
PUBLIC_URL = os.getenv("PUBLIC_URL")
WEBHOOK_SECRET = os.getenv("TG_SECRET", "hooksecret")
WEBHOOK_PATH = f"/tg/{WEBHOOK_SECRET}"

OWM_KEY = os.getenv("OWM_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ── DB ─────────────────────────────────────────────────────────────────────
DB_ENV_PATH = os.getenv("DB_PATH")
DB_DIR = os.getenv("DB_DIR", "/tmp")

def _open_db():
    if DB_ENV_PATH:
        try:
            os.makedirs(os.path.dirname(DB_ENV_PATH) or ".", exist_ok=True)
            return sqlite3.connect(DB_ENV_PATH)
        except Exception as e:
            print("[DB] Failed to open DB_PATH:", DB_ENV_PATH, e)
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        p = os.path.join(DB_DIR, "db.sqlite3")
        return sqlite3.connect(p)
    except Exception as e:
        print("[DB] Failed to open /tmp:", e)
    print("[DB] Falling back to in-memory DB")
    return sqlite3.connect(":memory:")

db = _open_db()
cur = db.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    tz TEXT DEFAULT 'Europe/Moscow',
    petname TEXT DEFAULT 'зайчик',
    cooldown REAL DEFAULT 0
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS prefs (
    user_id INTEGER PRIMARY KEY,
    city TEXT DEFAULT 'Moscow',
    partner_city TEXT DEFAULT 'Zibo',
    units TEXT DEFAULT 'metric',
    flirt_auto INTEGER DEFAULT 1,
    profanity INTEGER DEFAULT 1,
    style_mode TEXT DEFAULT 'auto',
    ritual_morning INTEGER DEFAULT 0,
    ritual_night INTEGER DEFAULT 0,
    r_morning_hour INTEGER DEFAULT 9,
    r_night_hour INTEGER DEFAULT 22
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS moods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day TEXT,
    score INTEGER,
    note TEXT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS qanswers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    question TEXT,
    answer TEXT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS chatlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS rituals_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day TEXT,
    which TEXT,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
)""")
db.commit()

# ── HELPERS ────────────────────────────────────────────────────────────────
def _now_in_tz(tz: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.utcnow()

def get_user(uid: int):
    cur.execute("SELECT user_id,tz,petname,cooldown FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Europe/Moscow", "зайчик", 0.0)
    return row

def get_prefs(uid: int):
    cur.execute("SELECT user_id,city,partner_city,units,flirt_auto,profanity,style_mode,ritual_morning,ritual_night,r_morning_hour,r_night_hour FROM prefs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO prefs(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Moscow", "Zibo", "metric", 1,1,"auto",0,0,9,22)
    return row

def get_prefs_dict(uid: int) -> dict:
    row = get_prefs(uid)
    return {
        "user_id": row[0],
        "city": row[1],
        "partner_city": row[2],
        "units": row[3],
        "flirt_auto": row[4],
        "profanity": row[5],
        "style_mode": row[6],
        "ritual_morning": row[7],
        "ritual_night": row[8],
        "r_morning_hour": row[9],
        "r_night_hour": row[10],
    }

def log_chat(uid: int, role: str, content: str):
    try:
        cur.execute("INSERT INTO chatlog(user_id, role, content) VALUES(?,?,?)", (uid, role, (content or "")[:4000]))
        db.commit()
    except Exception:
        pass

async def _ai_answer_with_ctx(uid: int, text: str) -> str:
    if llm_short_reply is None:
        return "Я сейчас без ключа ИИ, но уже не повторяю дословно: " + (text[:200] if text else "")
    try:
        cur.execute("SELECT role, content FROM chatlog WHERE user_id=? ORDER BY id DESC LIMIT 8", (uid,))
        rows = list(reversed(cur.fetchall()))
        convo = ""
        for r,c in rows[-6:]:
            who = "Ты" if r=="assistant" else "Я"
            convo += f"{who}: {c[-400:]}\n"
        prompt = f"{convo}\nЯ: {text}\nОтветь как обычно, учитывая контекст выше."
        return llm_short_reply(prompt)
    except Exception as e:
        return f"Не смогла позвать ИИ: {e}"

# Weather helpers
async def _geocode_city(city: str):
    url = f"https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&name={city}"
    try:
        async with ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                j = await r.json()
        res = (j.get("results") or [])[0]
        return res["latitude"], res["longitude"]
    except Exception as e:
        print("[geo] err", e)
        return None, None

async def _weather_by_coords(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m"
    try:
        async with ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                j = await r.json()
        return j.get("current", {})
    except Exception as e:
        print("[weather] err", e)
        return {}

async def _weather_by_city(city: str):
    if OWM_KEY:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_KEY}&units=metric&lang=ru"
        try:
            async with ClientSession() as s:
                async with s.get(url, timeout=10) as r:
                    j = await r.json()
            t = (j.get("main") or {}).get("temp")
            w = (j.get("wind") or {}).get("speed")
            if t is not None:
                return {"temperature_2m": t, "wind_speed_10m": w}
        except Exception as e:
            print("[owm] err", e)
    lat, lon = await _geocode_city(city)
    if not lat: return {}
    return await _weather_by_coords(lat, lon)

# FX helpers
FX_CACHE = {"ts": 0, "data": {}}
FX_SYMBOLS = ["RUB","CNY","USD"]

def _fmt_amount(x: float) -> str:
    try:
        return f"{x:,.2f}".replace(",", " ").replace(".00","")
    except Exception:
        return str(x)

def _norm_ccy(s: str) -> str:
    s = s.strip().upper()
    aliases = {"YUAN":"CNY","RMB":"CNY","YUANS":"CNY","RUBLES":"RUB","RUR":"RUB","RUBLE":"RUB","DOLLAR":"USD","DOLLARS":"USD"}
    return aliases.get(s, s)

async def _fetch_rates():
    # Cache 10 minutes
    if time.time() - FX_CACHE["ts"] < 600 and FX_CACHE["data"]:
        return FX_CACHE["data"]
    url = "https://api.exchangerate.host/latest?base=RUB&symbols=USD,CNY"
    try:
        async with ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                j = await r.json()
                rates = j.get("rates", {})
                data = {
                    "RUB": {"RUB": 1.0, "USD": rates.get("USD"), "CNY": rates.get("CNY")},
                }
                usd_rub = 1.0 / data["RUB"]["USD"] if data["RUB"]["USD"] else None
                cny_rub = 1.0 / data["RUB"]["CNY"] if data["RUB"]["CNY"] else None
                data["USD"] = {"USD":1.0, "RUB": usd_rub, "CNY": (cny_rub*data["RUB"]["USD"]) if (cny_rub and data["RUB"]["USD"]) else None}
                data["CNY"] = {"CNY":1.0, "RUB": cny_rub, "USD": (usd_rub/data['RUB']['CNY']) if (usd_rub and data['RUB']['CNY']) else None}
                FX_CACHE["ts"] = time.time()
                FX_CACHE["data"] = data
                return data
    except Exception as e:
        print("[FX] error:", e)
    return FX_CACHE["data"] or {}

# ── UI ─────────────────────────────────────────────────────────────────────
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💙 Настроение"), KeyboardButton(text="💌 Вопросы")],
            [KeyboardButton(text="🕒 Время"), KeyboardButton(text="🌊 Погода")],
            [KeyboardButton(text="💱 Курсы"), KeyboardButton(text="📅 Недельный дайджест")]
        ],
        resize_keyboard=True
    )

# ── BASIC HANDLERS ─────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    uid = m.from_user.id
    get_user(uid); get_prefs(uid)
    await m.answer("Привет! Я рядом. Жми кнопки в меню ниже. /help — список команд", reply_markup=main_keyboard())

@dp.message(Command("help"))
async def cmd_help(m: types.Message):
    await m.answer(
        "Навигация кнопками или командами:\n"
        "💙 /mood 7 заметка — настроение\n"
        "💌 /qadd <cat> вопрос = ответ • /q [cat] поиск • /q_history\n"
        "🕒 /menu — время для TZ/Москва/Шанхай\n"
        "🌊 /weather [город] — погода (OWM/Open-Meteo)\n"
        "💱 /fx [100 usd to rub] — курсы/конвертер\n"
        "📅 /digest — недельный дайджест\n"
        "/style • /flirt • /nsfw • /setpetname • /settz • /setcity • /setpartner"
    , reply_markup=main_keyboard())

@dp.message(Command("menu"))
async def cmd_menu(m: types.Message):
    uid = m.from_user.id
    _, tz, pet, _ = get_user(uid)
    pf = get_prefs_dict(uid)
    now_me = _now_in_tz(tz)
    msk = _now_in_tz("Europe/Moscow")
    sha = _now_in_tz("Asia/Shanghai")
    await m.answer(
        f"⏱ Твоё время ({tz}): <b>{now_me:%H:%M}</b>\n"
        f"🇷🇺 Москва: <b>{msk:%H:%M}</b> • 🇨🇳 Шанхай/Цзыбо: <b>{sha:%H:%M}</b>\n"
        f"🏙 Город: {pf['city']} • Партнёр: {pf['partner_city']}\n"
        f"Обращаться: {pet}",
        reply_markup=main_keyboard()
    )

@dp.message(Command("ping"))
async def cmd_ping(m: types.Message):
    await m.answer("pong")

@dp.message(Command("whoami"))
async def cmd_whoami(m: types.Message):
    uid = m.from_user.id
    _, tz, pet, _ = get_user(uid)
    pf = get_prefs_dict(uid)
    await m.answer(
        f"ID: <code>{uid}</code>\n"
        f"TZ: {tz}\n"
        f"Имя: {pet}\n"
        f"Город: {pf['city']}\n"
        f"Партнёр: {pf['partner_city']}\n"
        f"Единицы: {pf['units']}"
    , reply_markup=main_keyboard())

@dp.message(Command("setpetname"))
async def cmd_setpet(m: types.Message):
    name = (m.text or "").split(maxsplit=1)
    if len(name) < 2:
        return await m.answer("Напиши: /setpetname <имя>")
    cur.execute("INSERT INTO users(user_id,petname) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET petname=excluded.petname",
                (m.from_user.id, name[1].strip()))
    db.commit()
    await m.answer("Супер! Запомнила.", reply_markup=main_keyboard())

@dp.message(Command("settz"))
async def cmd_settz(m: types.Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Пример: /settz Europe/Amsterdam")
    tz = parts[1].strip()
    cur.execute("INSERT INTO users(user_id,tz) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET tz=excluded.tz",
                (m.from_user.id, tz))
    db.commit()
    await m.answer(f"Часовой пояс теперь {tz}", reply_markup=main_keyboard())

@dp.message(Command("setcity"))
async def cmd_setcity(m: types.Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Пример: /setcity Москва")
    city = parts[1].strip()
    uid = m.from_user.id
    cur.execute("INSERT INTO prefs(user_id,city) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET city=excluded.city",
                (uid, city))
    db.commit()
    await m.answer("Город обновлён.", reply_markup=main_keyboard())

@dp.message(Command("setpartner"))
async def cmd_setpartner(m: types.Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("Пример: /setpartner Цзыбо")
    p = parts[1].strip()
    uid = m.from_user.id
    cur.execute("INSERT INTO prefs(user_id,partner_city) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET partner_city=excluded.partner_city",
                (uid, p))
    db.commit()
    await m.answer("Город партнёра обновлён.", reply_markup=main_keyboard())

# ── STYLE / PREFS ───────────────────────────────────────────────────────────
@dp.message(Command("style"))
async def cmd_style(m: types.Message):
    uid = m.from_user.id
    parts = (m.text or "").split(maxsplit=1)
    if len(parts)<2:
        pf = get_prefs_dict(uid)
        return await m.answer(f"style_mode: <b>{pf['style_mode']}</b> • flirt_auto: {pf['flirt_auto']} • profanity: {pf['profanity']}")
    val = parts[1].strip().lower()
    allowed = {"auto","gentle","soft","strict","flirty"}
    if val not in allowed:
        return await m.answer("Варианты: auto, gentle/soft, strict, flirty")
    cur.execute("UPDATE prefs SET style_mode=? WHERE user_id=?", (val, uid))
    db.commit()
    await m.answer(f"Стиль теперь: <b>{val}</b>")

@dp.message(Command("flirt"))
async def cmd_flirt(m: types.Message):
    uid = m.from_user.id
    parts = (m.text or "").split(maxsplit=1)
    if len(parts)<2:
        pf = get_prefs_dict(uid)
        return await m.answer(f"flirt_auto = {pf['flirt_auto']} (используй: /flirt on|off)")
    v = 1 if parts[1].strip().lower() in ("on","1","true","да") else 0
    cur.execute("UPDATE prefs SET flirt_auto=? WHERE user_id=?", (v, uid))
    db.commit()
    await m.answer(f"Флирт авто: {v}")

@dp.message(Command("nsfw"))
async def cmd_nsfw(m: types.Message):
    uid = m.from_user.id
    parts = (m.text or "").split(maxsplit=1)
    if len(parts)<2:
        pf = get_prefs_dict(uid)
        return await m.answer(f"profanity = {pf['profanity']} (используй: /nsfw on|off)")
    v = 1 if parts[1].strip().lower() in ("on","1","true","да") else 0
    cur.execute("UPDATE prefs SET profanity=? WHERE user_id=?", (v, uid))
    db.commit()
    await m.answer(f"Профан слова: {v}")

# алиасы
@dp.message(Command("nick"))
async def cmd_nick(m: types.Message):
    m.text = m.text.replace("/nick", "/setpetname", 1)
    await cmd_setpet(m)

@dp.message(Command("tz"))
async def cmd_tz(m: types.Message):
    m.text = m.text.replace("/tz", "/settz", 1)
    await cmd_settz(m)

# ── MOOD ───────────────────────────────────────────────────────────────────
@dp.message(Command("mood"))
async def cmd_mood(m: types.Message):
    parts = (m.text or "").split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        return await m.answer("Пример: /mood 7 сегодня грустненько")
    score = int(parts[1])
    note = parts[2] if len(parts) > 2 else ""
    uid = m.from_user.id
    _, tz, _, _ = get_user(uid)
    day = _now_in_tz(tz).date().isoformat()
    cur.execute("INSERT INTO moods(user_id, day, score, note) VALUES(?,?,?,?)", (uid, day, score, note))
    db.commit()
    await m.answer(f"Сохранила настроение {score}/10 на {day}.")

@dp.message(Command("moodweek"))
async def cmd_moodweek(m: types.Message):
    uid = m.from_user.id
    cur.execute("SELECT day, AVG(score) FROM moods WHERE user_id=? GROUP BY day ORDER BY day DESC LIMIT 7", (uid,))
    rows = cur.fetchall()
    if not rows:
        return await m.answer("Нет данных за неделю.")
    rows = list(reversed(rows))
    bars = []
    for day, avg in rows:
        filled = "█" * int(round((avg or 0)/10*10))
        bars.append(f"{day}: {filled} {avg:.1f}/10")
    await m.answer("\n".join(bars))

# ── Q&A ────────────────────────────────────────────────────────────────────
@dp.message(Command("qadd"))
async def cmd_qadd(m: types.Message):
    uid = m.from_user.id
    text = (m.text or "")[5:].strip()
    if "=" not in text or not text:
        return await m.answer("Пример: /qadd thermo как считать Re? = Re = w*d/nu")
    try:
        left, answer = text.split("=",1)
        left = left.strip()
        answer = answer.strip()
        cat, question = left.split(None, 1)
    except Exception:
        return await m.answer("Нужно: /qadd <cat> <вопрос> = <ответ>")
    cur.execute("INSERT INTO qanswers(user_id, category, question, answer) VALUES(?,?,?,?)",
                (uid, cat.strip(), question.strip(), answer))
    db.commit()
    await m.answer("Сохранила.")

@dp.message(Command("q"))
async def cmd_q(m: types.Message):
    uid = m.from_user.id
    parts = (m.text or "").split(maxsplit=2)
    if len(parts)<2:
        return await m.answer("Пример: /q termo энтальпия")
    if len(parts)==2:
        cat = None; q = parts[1]
    else:
        cat = parts[1]; q = parts[2]
    if cat:
        cur.execute("SELECT question,answer FROM qanswers WHERE user_id=? AND category LIKE ? AND (question LIKE ? OR answer LIKE ?) ORDER BY ts DESC LIMIT 6",
                    (uid, f"%{cat}%", f"%{q}%", f"%{q}%"))
    else:
        cur.execute("SELECT question,answer FROM qanswers WHERE user_id=? AND (question LIKE ? OR answer LIKE ?) ORDER BY ts DESC LIMIT 6",
                    (uid, f"%{q}%", f"%{q}%"))
    rows = cur.fetchall()
    if not rows:
        return await m.answer("Ничего не нашла.")
    out = "\n".join([f"• <i>{r[0]}</i> — <b>{r[1]}</b>" for r in rows])
    await m.answer(out)

@dp.message(Command("q_history"))
async def cmd_q_history(m: types.Message):
    uid = m.from_user.id
    cur.execute("SELECT category,question,answer,ts FROM qanswers WHERE user_id=? ORDER BY ts DESC LIMIT 10", (uid,))
    rows = cur.fetchall()
    if not rows:
        return await m.answer("История пустая.")
    out = "\n".join([f"• [{r[0]}] {r[1]} — <b>{r[2]}</b> ({r[3]})" for r in rows])
    await m.answer(out)

# ── WEATHER ────────────────────────────────────────────────────────────────
@dp.message(Command("weather"))
async def cmd_weather(m: types.Message):
    uid = m.from_user.id
    pf = get_prefs_dict(uid)
    parts = (m.text or "").split(maxsplit=1)
    city = (parts[1].strip() if len(parts)>1 else pf["city"]) or pf["city"]
    cur_w = await _weather_by_city(city)
    if not cur_w: return await m.answer("Нет данных по погоде.")
    t = cur_w.get("temperature_2m"); w = cur_w.get("wind_speed_10m"); 
    await m.answer(f"Погода в {city}: {t}°C, ветер {w} м/с.")

# ── FX (RUB, CNY, USD) ─────────────────────────────────────────────────────
@dp.message(Command("fx"))
async def cmd_fx(m: types.Message):
    parts = (m.text or "").split()
    data = await _fetch_rates()
    if not data:
        return await m.answer("Пока не могу получить курсы. Попробуй позже.")
    if len(parts) < 2:
        rub_usd = data["RUB"]["USD"]; rub_cny = data["RUB"]["CNY"]
        usd_rub = data["USD"]["RUB"]; cny_rub = data["CNY"]["RUB"]
        return await m.answer(
            "Курсы (exchangerate.host):\n"
            f"1 USD ≈ <b>{_fmt_amount(usd_rub)} RUB</b>\n"
            f"1 CNY ≈ <b>{_fmt_amount(cny_rub)} RUB</b>\n"
            f"1 RUB ≈ {_fmt_amount(rub_usd)} USD • {_fmt_amount(rub_cny)} CNY"
        )
    # try parse conversion
    amt = None; src=None; dst=None
    try:
        for p in parts[1:]:
            if amt is None:
                try:
                    amt = float(p.replace(",",".").replace(" ",""))
                    continue
                except:
                    pass
            if src is None and p.lower() not in ("to","в","->"):
                src = _norm_ccy(p)
                continue
            if p.lower() in ("to","в","->"):
                continue
            if dst is None:
                dst = _norm_ccy(p)
        if amt is None or src not in FX_SYMBOLS or dst not in FX_SYMBOLS:
            raise ValueError
    except Exception:
        return await m.answer("Пример: /fx 100 usd to rub  • Доступные: RUB, CNY, USD")
    rate = data.get(src,{}).get(dst)
    if not rate:
        return await m.answer("Нет курса для этой пары.")
    val = amt * rate
    await m.answer(f"{_fmt_amount(amt)} {src} → <b>{_fmt_amount(val)} {dst}</b>")

# ── BUTTONS NAVIGATION ─────────────────────────────────────────────────────
@dp.message(F.text == "🕒 Время")
async def btn_time(m: types.Message):
    return await cmd_menu(m)

@dp.message(F.text == "💱 Курсы")
async def btn_fx(m: types.Message):
    m.text = "/fx"
    return await cmd_fx(m)

@dp.message(F.text == "🌊 Погода")
async def btn_weather(m: types.Message):
    uid = m.from_user.id
    pf = get_prefs_dict(uid)
    txts = []
    for city in list(dict.fromkeys([pf["city"], pf["partner_city"]])):
        if not city: 
            continue
        cur_w = await _weather_by_city(city)
        if cur_w:
            t = cur_w.get("temperature_2m"); w = cur_w.get("wind_speed_10m")
            txts.append(f"{city}: {t}°C, ветер {w} м/с")
        else:
            txts.append(f"{city}: нет данных")
    await m.answer("\n".join(txts) if txts else "Нет городов. Используй /setcity и /setpartner.")

@dp.message(F.text == "💙 Настроение")
async def btn_mood(m: types.Message):
    await m.answer("Оцени день от 1 до 10: отправь <code>/mood 7 комментарий</code>")

QUESTIONS = {
    "легкие": [
        "Что сегодня сделало тебя хоть каплю счастливее?",
        "Какая мелочь тебя вдохновляет в буднях?",
        "Какой запах ассоциируется с уютом?",
    ],
    "глубже": [
        "Какую черту в себе ты сейчас бережно развиваешь и почему?",
        "Что для тебя значит «быть услышанным»?",
        "В какой момент в последнее время ты собой гордилась и почему?",
    ],
    "флирт": [
        "Что тебя разоружает в человеке сильнее всего?",
        "Какое внимание тебе кажется самым тёплым?",
        "Назови три вещи, из-за которых ты теряешь голову 😉",
    ]
}

@dp.message(F.text == "💌 Вопросы")
async def btn_questions(m: types.Message):
    await m.answer("Выбери тему: легкие / глубже / флирт. Напиши ответ одним сообщением — я сохраню.")

_last_question_category = {}

@dp.message(F.text.lower().in_(["легкие","глубже","флирт"]))
async def pick_category(m: types.Message):
    cat = m.text.lower()
    q = QUESTIONS[cat][0]
    _last_question_category[m.from_user.id] = cat
    await m.answer(f"{q}\n\nНапиши ответ одним сообщением — сохраню в заметки.")

@dp.message(F.text & F.text.lower().not_in(["легкие","глубже","флирт"]) & ~F.text.startswith("/"))
async def capture_answer_after_question(m: types.Message):
    uid = m.from_user.id
    if uid in _last_question_category:
        cat = _last_question_category.pop(uid)
        cur.execute("INSERT INTO qanswers(user_id, category, question, answer) VALUES(?,?,?,?)",
                    (uid, cat, "user-flow", (m.text or '').strip()))
        db.commit()
        return await m.answer("Сохранила 💌. Посмотреть: /q "+cat)

# ── WEEKLY DIGEST ──────────────────────────────────────────────────────────
@dp.message(Command("digest"))
@dp.message(F.text == "📅 Недельный дайджест")
async def cmd_digest(m: types.Message):
    uid = m.from_user.id
    cur.execute("SELECT day, AVG(score) FROM moods WHERE user_id=? GROUP BY day ORDER BY day DESC LIMIT 7", (uid,))
    rows = cur.fetchall()
    rows = list(reversed(rows))
    if not rows:
        return await m.answer("Пока нет настроений за неделю. Поставь пару записей через /mood.")
    line = []
    summary_input = []
    for day, avg in rows:
        blocks = "▁▂▃▄▅▆▇"[int(min(6, max(0, round((avg or 0)/10*6))))]
        line.append(blocks)
        summary_input.append(f"{day}: {avg:.1f}/10")
    moodline = "".join(line)
    text_block = "\n".join(summary_input)
    try:
        ai = await _ai_answer_with_ctx(uid, f"Сводка настроения по дням:\n{text_block}\nСделай короткий человеческий обзор (2–3 предложения) и предложи 2–3 мягких шага на следующую неделю.")
    except Exception as e:
        ai = f"(не удалось получить обзор ИИ: {e})"
    await m.answer(f"Муд недели: {moodline}\n{text_block}\n\n{ai}")

# ── SMART TEXT HANDLER (не просто эхо) ─────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def smart_text(m: types.Message):
    txt = m.text or ""
    log_chat(m.from_user.id, 'user', txt)
    addressed = re.match(r"^(бот|ии|ai|hey|эй)[,\s]", txt.lower())
    if llm_short_reply or addressed:
        ans = await _ai_answer_with_ctx(m.from_user.id, txt)
        log_chat(m.from_user.id, 'assistant', ans)
        return await m.answer(ans)
    short = txt
    if len(short) > 140:
        short = short[:140] + "…"
    resp = f"Поняла тебя: “{short}”. Для ИИ-ответа введи /ask <вопрос>."
    log_chat(m.from_user.id, 'assistant', resp)
    await m.answer(resp)

# ── STARTUP ────────────────────────────────────────────────────────────────
async def _set_commands():
    cmds = [
        BotCommand(command="start", description="Старт"),
        BotCommand(command="help", description="Подсказка"),
        BotCommand(command="menu", description="Меню времени"),
        BotCommand(command="ping", description="Проверка"),
        BotCommand(command="mood", description="Настроение"),
        BotCommand(command="whoami", description="Профиль"),
        BotCommand(command="digest", description="Недельный дайджест"),
        BotCommand(command="fx", description="Курсы валют"),
    ]
    try:
        await bot.set_my_commands(cmds)
    except Exception:
        pass

async def start_background():
    await _set_commands()
    if USE_WEBHOOK:
        if not PUBLIC_URL:
            raise RuntimeError("PUBLIC_URL is required when USE_WEBHOOK=1")
        url = PUBLIC_URL + WEBHOOK_PATH
        print(f"[WEBHOOK] Setting webhook to {url}")
        await bot.set_webhook(url=url, drop_pending_updates=True, secret_token=WEBHOOK_SECRET)
    else:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass
        await dp.start_polling(bot)

async def _ritual_loop():
    while True:
        try:
            await asyncio.sleep(60)
            cur.execute("SELECT user_id,tz FROM users")
            for uid, tz in cur.fetchall():
                now = _now_in_tz(tz or "Europe/Moscow")
                day = now.date().isoformat()
                pf = get_prefs_dict(uid)
                # Morning
                if pf["ritual_morning"] and now.hour==pf["r_morning_hour"] and now.minute==0:
                    cur.execute("SELECT 1 FROM rituals_sent WHERE user_id=? AND day=? AND which='morning'", (uid, day))
                    if not cur.fetchone():
                        try:
                            _, _, pet, _ = get_user(uid)
                            await bot.send_message(uid, f"Доброе утро, {pet} ☀️ Я рядом.", reply_markup=main_keyboard())
                        except Exception as e:
                            print("[ritual send morning]", e)
                        cur.execute("INSERT INTO rituals_sent(user_id, day, which) VALUES(?,?,?)", (uid, day, "morning")); db.commit()
                # Night
                if pf["ritual_night"] and now.hour==pf["r_night_hour"] and now.minute==0:
                    cur.execute("SELECT 1 FROM rituals_sent WHERE user_id=? AND day=? AND which='night'", (uid, day))
                    if not cur.fetchone():
                        try:
                            _, _, pet, _ = get_user(uid)
                            await bot.send_message(uid, f"Спокойной ночи, {pet} 🌙 Обнимашки.", reply_markup=main_keyboard())
                        except Exception as e:
                            print("[ritual send night]", e)
                        cur.execute("INSERT INTO rituals_sent(user_id, day, which) VALUES(?,?,?)", (uid, day, "night")); db.commit()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print("[ritual loop]", e)

async def on_startup(app: web.Application):
    app["task"] = asyncio.create_task(start_background())
    app["scheduler"] = asyncio.create_task(_ritual_loop())

async def on_cleanup(app: web.Application):
    sched = app.get("scheduler")
    if sched:
        sched.cancel()
        try:
            await sched
        except Exception:
            pass
    task = app.get("task")
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    async def ping_handler(_):
        return web.json_response({"ok": True})

    app.router.add_get("/", ping_handler)

    if USE_WEBHOOK:
        async def hook_get(_):
            return web.Response(text="hook alive")
        app.router.add_get(WEBHOOK_PATH, hook_get)
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        print(f"[WEBHOOK] route registered at {WEBHOOK_PATH}")

    return app

if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
