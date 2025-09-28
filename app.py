import os
import re
import sqlite3
import asyncio
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

# ── ENV ────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

USE_WEBHOOK = os.getenv("USE_WEBHOOK", "1") == "1"
PUBLIC_URL = os.getenv("PUBLIC_URL")
WEBHOOK_SECRET = os.getenv("TG_SECRET", "hooksecret")
WEBHOOK_PATH = f"/tg/{WEBHOOK_SECRET}"

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
    petname TEXT DEFAULT 'зайчик'
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS prefs (
    user_id INTEGER PRIMARY KEY,
    city TEXT DEFAULT 'Moscow',
    partner_city TEXT DEFAULT 'Zibo',
    units TEXT DEFAULT 'metric'
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
db.commit()


# Upgrade DB schema to include extra prefs and helpers
def _ensure_columns():
    def has_col(table, name):
        cur.execute(f"PRAGMA table_info({table})")
        return any(r[1]==name for r in cur.fetchall())
    # users.cooldown
    if not has_col("users","cooldown"):
        try: cur.execute("ALTER TABLE users ADD COLUMN cooldown REAL DEFAULT 0")
        except Exception: pass
    # prefs extra columns
    for col, defv in [
        ("flirt_auto","INTEGER DEFAULT 1"),
        ("profanity","INTEGER DEFAULT 1"),
        ("style_mode","TEXT DEFAULT 'auto'"),
        ("ritual_morning","INTEGER DEFAULT 0"),
        ("ritual_night","INTEGER DEFAULT 0"),
        ("r_morning_hour","INTEGER DEFAULT 9"),
        ("r_night_hour","INTEGER DEFAULT 22"),
    ]:
        if not has_col("prefs", col):
            try: cur.execute(f"ALTER TABLE prefs ADD COLUMN {col} {defv}")
            except Exception: pass
    # chatlog
    cur.execute("""CREATE TABLE IF NOT EXISTS chatlog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    # rituals sent track
    cur.execute("""CREATE TABLE IF NOT EXISTS rituals_sent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        day TEXT,
        which TEXT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()

_ensure_columns()

def get_user(uid: int):
    cur.execute("SELECT user_id,tz,petname FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Europe/Moscow", "зайчик")
    return row

def get_prefs(uid: int):
    cur.execute("SELECT user_id,city,partner_city,units FROM prefs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO prefs(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Moscow", "Zibo", "metric")
    return row


# ── FX (RUB, CNY, USD) ─────────────────────────────────────────────────────
from aiohttp import ClientSession
import time

FX_CACHE = {"ts": 0, "data": {}}
FX_SYMBOLS = ["RUB","CNY","USD"]

async def _fetch_rates():
    # Cache for 10 minutes
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
                # derive other directions
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

def _fmt_amount(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".00","")

def _norm_ccy(s: str) -> str:
    s = s.strip().upper()
    aliases = {"YUAN":"CNY","RMB":"CNY","YUANS":"CNY","RUBLES":"RUB","RUR":"RUB","RUBLE":"RUB","DOLLAR":"USD","DOLLARS":"USD"}
    return aliases.get(s, s)

@dp.message(Command("fx"))
async def cmd_fx(m: types.Message):
    # /fx  — show snapshot
    # /fx 100 usd to rub — convert
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
    # /fx 150 usd rub
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

# ── BASIC HANDLERS ─────────────────────────────────────────────────────────


# ── STYLE / PREFS ───────────────────────────────────────────────────────────
@dp.message(Command("style"))
async def cmd_style(m: types.Message):
    uid = m.from_user.id
    parts = (m.text or "").split(maxsplit=1)
    if len(parts)<2:
        _, tz, pet = get_user(uid)
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

# ── Q&A ────────────────────────────────────────────────────────────────────
@dp.message(Command("qadd"))
async def cmd_qadd(m: types.Message):
    uid = m.from_user.id
    # /qadd <категория> вопрос = ответ
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
    # /q [cat] <поиск>
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

# ── MOOD WEEK ──────────────────────────────────────────────────────────────
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

# ── WEATHER (basic) ───────────────────────────────────────────────────────
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
        c = j.get("current", {})
        return c
    except Exception as e:
        print("[weather] err", e)
        return {}

@dp.message(Command("weather"))
async def cmd_weather(m: types.Message):
    uid = m.from_user.id
    pf = get_prefs_dict(uid)
    parts = (m.text or "").split(maxsplit=1)
    city = (parts[1].strip() if len(parts)>1 else pf["city"]) or pf["city"]
    lat, lon = await _geocode_city(city)
    if not lat: return await m.answer("Не смогла найти город.")
    cur_w = await _weather_by_coords(lat, lon)
    if not cur_w: return await m.answer("Нет данных по погоде.")
    t = cur_w.get("temperature_2m"); w = cur_w.get("wind_speed_10m"); code = cur_w.get("weather_code")
    await m.answer(f"Погода в {city}: {t}°C, ветер {w} м/с, код {code} (open-meteo).")

# ── RITUALS ────────────────────────────────────────────────────────────────
@dp.message(Command("ritual"))
async def cmd_ritual(m: types.Message):
    uid = m.from_user.id
    parts = (m.text or "").split()
    if len(parts)<2:
        pf = get_prefs_dict(uid)
        return await m.answer(f"morning: {pf['ritual_morning']}@{pf['r_morning_hour']} • night: {pf['ritual_night']}@{pf['r_night_hour']}")
    mode = parts[1].lower()
    if mode in ("morning","утро"):
        if len(parts)>=3 and parts[2].lower() in ("on","off"):
            v = 1 if parts[2].lower()=="on" else 0
            cur.execute("UPDATE prefs SET ritual_morning=? WHERE user_id=?", (v, uid))
            db.commit(); return await m.answer(f"Утренний ритуал: {v}")
        if len(parts)>=3 and parts[2].isdigit():
            h = max(0, min(23, int(parts[2])))
            cur.execute("UPDATE prefs SET r_morning_hour=? WHERE user_id=?", (h, uid)); db.commit()
            return await m.answer(f"Утренний час: {h}:00")
        return await m.answer("Примеры: /ritual morning on • /ritual morning 9")
    if mode in ("night","ночь"):
        if len(parts)>=3 and parts[2].lower() in ("on","off"):
            v = 1 if parts[2].lower()=="on" else 0
            cur.execute("UPDATE prefs SET ritual_night=? WHERE user_id=?", (v, uid))
            db.commit(); return await m.answer(f"Ночной ритуал: {v}")
        if len(parts)>=3 and parts[2].isdigit():
            h = max(0, min(23, int(parts[2])))
            cur.execute("UPDATE prefs SET r_night_hour=? WHERE user_id=?", (h, uid)); db.commit()
            return await m.answer(f"Ночной час: {h}:00")
        return await m.answer("Примеры: /ritual night on • /ritual night 22")
    await m.answer("Используй: /ritual morning on|off|<час>  • /ritual night on|off|<час>")

async def _ritual_loop():
    while True:
        try:
            # Check every 60s
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
                            _, _, pet = get_user(uid)
                            await bot.send_message(uid, f"Доброе утро, {pet} ☀️ Я рядом.")
                        except Exception as e:
                            print("[ritual send morning]", e)
                        cur.execute("INSERT INTO rituals_sent(user_id, day, which) VALUES(?,?,?)", (uid, day, "morning"))
                        db.commit()
                # Night
                if pf["ritual_night"] and now.hour==pf["r_night_hour"] and now.minute==0:
                    cur.execute("SELECT 1 FROM rituals_sent WHERE user_id=? AND day=? AND which='night'", (uid, day))
                    if not cur.fetchone():
                        try:
                            _, _, pet = get_user(uid)
                            await bot.send_message(uid, f"Спокойной ночи, {pet} 🌙 Обнимашки.")
                        except Exception as e:
                            print("[ritual send night]", e)
                        cur.execute("INSERT INTO rituals_sent(user_id, day, which) VALUES(?,?,?)", (uid, day, "night"))
                        db.commit()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print("[ritual loop]", e)

# ── CHATLOG export ─────────────────────────────────────────────────────────
@dp.message(Command("exportlog"))
async def cmd_exportlog(m: types.Message):
    uid = m.from_user.id
    cur.execute("SELECT role,content,ts FROM chatlog WHERE user_id=? ORDER BY id DESC LIMIT 100", (uid,))
    rows = cur.fetchall()
    if not rows:
        return await m.answer("Лог пуст.")
    rows = list(reversed(rows))
    lines = ["\n".join([f"[{r[2]}] {r[0]}: {r[1]}" for r in rows])]
    text = "\n".join(lines)
    # Telegram limit, so chunk
    for i in range(0, len(text), 3500):
        await m.answer("<code>"+text[i:i+3500]+"</code>")

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    uid = m.from_user.id
    get_user(uid); get_prefs(uid)
    await m.answer("Привет! Я рядом. Напиши /menu")

@dp.message(Command("menu"))
async def cmd_menu(m: types.Message):
    msk = datetime.utcnow() + timedelta(hours=3)
    sha = datetime.utcnow() + timedelta(hours=8)
    _, city, partner, _ = get_prefs(m.from_user.id)
    await m.answer(
        f"⏱ Москва: <b>{msk:%H:%M}</b> • Цзыбо/Шанхай: <b>{sha:%H:%M}</b>\n"
        f"🏙 Москва: {city} • Партнёр: {partner}"
    )

@dp.message(Command("ping"))
async def cmd_ping(m: types.Message):
    await m.answer("pong")

@dp.message(F.text)
async def echo(m: types.Message):
    print("[UPDATE] message from", m.from_user.id)
    await m.answer(m.text or "Пусто")


# ── WEEK & DEBUG ───────────────────────────────────────────────────────────
@dp.message(Command("week"))
async def cmd_week(m: types.Message):
    uid = m.from_user.id
    _, tz, _ = get_user(uid)
    now = _now_in_tz(tz)
    iso = now.isocalendar()
    # next 7 days
    days = []
    for d in range(7):
        dt = now.date() + timedelta(days=d)
        days.append(f"{dt} ({(now + timedelta(days=d)).strftime('%a')})")
    await m.answer(f"Сейчас неделя №{iso.week}\n" + "\n".join(days))

@dp.message(Command("debug"))
async def cmd_debug(m: types.Message):
    uid = m.from_user.id
    _, tz, pet = get_user(uid)
    pf = get_prefs_dict(uid)
    out = [
        f"tz={tz}, pet={pet}",
        f"prefs={pf}",
        f"USE_WEBHOOK={USE_WEBHOOK}, PUBLIC_URL={PUBLIC_URL}, PATH={WEBHOOK_PATH}"
    ]
    await m.answer("\n".join(out))

# ── STARTUP ────────────────────────────────────────────────────────────────
async def _set_commands():
    cmds = [
        BotCommand(command="start", description="Старт"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="ping", description="Проверка"),
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
        # Register POST webhook handler
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        print(f"[WEBHOOK] route registered at {WEBHOOK_PATH}")

    return app

if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)