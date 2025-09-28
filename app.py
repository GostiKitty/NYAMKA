
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

# Webhook config
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "0") == "1"
PUBLIC_URL = os.getenv("PUBLIC_URL")  # e.g., https://your-app.koyeb.app
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
    # 1) explicit DB_PATH
    if DB_ENV_PATH:
        try:
            os.makedirs(os.path.dirname(DB_ENV_PATH) or ".", exist_ok=True)
            return sqlite3.connect(DB_ENV_PATH)
        except Exception as e:
            print("[DB] Failed to open DB_PATH:", DB_ENV_PATH, e)
    # 2) /tmp/db.sqlite3
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        p = os.path.join(DB_DIR, "db.sqlite3")
        return sqlite3.connect(p)
    except Exception as e:
        print("[DB] Failed to open /tmp:", e)
    # 3) in-memory fallback (non-persistent)
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

def get_user(uid: int):
    cur.execute("SELECT user_id,tz,petname FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Europe/Moscow", "зайчик")
    return row

def set_user(uid: int, **kw):
    u = dict(zip(["user_id", "tz", "petname"], get_user(uid)))
    u.update({k: v for k, v in kw.items() if v is not None})
    cur.execute(
        "REPLACE INTO users(user_id,tz,petname) VALUES(?,?,?)",
        (uid, u["tz"], u["petname"]),
    )
    db.commit()

def get_prefs(uid: int):
    cur.execute("SELECT user_id,city,partner_city,units FROM prefs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO prefs(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Moscow", "Zibo", "metric")
    return row

def set_prefs(uid: int, **kw):
    uid0, city, partner, units = get_prefs(uid)
    city = kw.get("city", city)
    partner = kw.get("partner_city", partner)
    units = kw.get("units", units)
    cur.execute(
        "REPLACE INTO prefs(user_id,city,partner_city,units) VALUES(?,?,?,?)",
        (uid, city, partner, units),
    )
    db.commit()

# ── UTIL ───────────────────────────────────────────────────────────────────
def frame(title: str, body: str) -> str:
    return f"<b>{title}</b>\n{body}"

def today_panel(uid: int) -> str:
    _, tz, _ = get_user(uid)
    msk = datetime.utcnow() + timedelta(hours=3)
    sh = datetime.utcnow() + timedelta(hours=8)
    _, city, partner, _ = get_prefs(uid)
    return (
        f"⏱ Москва: <b>{msk:%H:%M}</b>  •  Цзыбо/Шанхай: <b>{sh:%H:%M}</b>\n"
        f"🏙 Москва: {city}  •  Партнёр: {partner}"
    )

# ── QUESTIONS ──────────────────────────────────────────────────────────────
QUEST_LIGHT = [
    "Что сегодня сделало тебя счастливее на 1%?",
    "О чём ты мечтаешь в ближайшие 3 месяца?",
    "Какая песня — твой сегодняшний саундтрек и почему?",
]
QUEST_DEEP = [
    "Какое убеждение из детства ты пересматриваешь сейчас?",
    "Чего ты боишься потерять больше всего и почему?",
    "Что для тебя означает забота в отношениях?",
]
QUESTIONS = {"light": QUEST_LIGHT, "deep": QUEST_DEEP}

# ── COMMANDS ───────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    uid = m.from_user.id
    get_user(uid)
    get_prefs(uid)
    await m.answer(frame("Привет!", "Я рядом. Выбирай в /menu что нужно."))

@dp.message(Command("menu"))
async def cmd_menu(m: types.Message):
    await m.answer(today_panel(m.from_user.id))

AWAIT_MOOD = set()

@dp.message(Command("mood"))
async def cmd_mood(m: types.Message):
    AWAIT_MOOD.add(m.from_user.id)
    await m.answer("Пришли оценку настроения 1–10 и заметку. Пример: <code>7 много дел</code>")

@dp.message(F.text & (F.from_user.id.func(lambda uid: uid in AWAIT_MOOD)))
async def mood_value(m: types.Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    mobj = re.match(r"^\s*(\d{1,2})(?:\s+(.*))?$", txt)
    if not mobj:
        await m.answer("Нужно число 1–10. Пример: <code>8 выспалась</code>")
        return
    score = max(1, min(10, int(mobj.group(1))))
    note = (mobj.group(2) or "").strip()
    cur.execute(
        "INSERT INTO moods(user_id,day,score,note) VALUES(?,?,?,?)",
        (uid, date.today().isoformat(), score, note),
    )
    db.commit()
    AWAIT_MOOD.discard(uid)
    await m.answer(f"Записала: {score}/10" + (f" — {note}" if note else ""))

@dp.message(Command("q"))
async def cmd_q(m: types.Message):
    cat = (m.text or "").split(maxsplit=1)
    cat = (cat[1] if len(cat) > 1 else "light").lower()
    if cat not in QUESTIONS:
        cat = "light"
    q = QUESTIONS[cat][datetime.utcnow().microsecond % len(QUESTIONS[cat])]
    await m.answer(frame(f"Вопрос ({cat})", q + "\n\nПришли один ответ — я его сохраню 💙"))
    # mark waiting
    m.bot["q_wait"] = m.bot.get("q_wait", {})
    m.bot["q_wait"][m.from_user.id] = {"cat": cat, "q": q}

@dp.message(F.text)
async def text_router(m: types.Message):
    print("[UPDATE] webhook message from", m.from_user.id)
    # question answer?
    qw = m.bot.get("q_wait", {}).get(m.from_user.id)
    if qw:
        cur.execute(
            "INSERT INTO qanswers(user_id,category,question,answer) VALUES(?,?,?,?)",
            (m.from_user.id, qw["cat"], qw["q"], m.text),
        )
        db.commit()
        m.bot["q_wait"].pop(m.from_user.id, None)
        await m.answer("Сохранила 💙")
        return
    # echo fallback
    if m.text:
        await m.answer(m.text)

@dp.message(Command("q_history"))
async def cmd_q_hist(m: types.Message):
    cur.execute(
        "SELECT category,question,answer,ts FROM qanswers WHERE user_id=? ORDER BY id DESC LIMIT 5",
        (m.from_user.id,),
    )
    rows = cur.fetchall()
    if not rows:
        await m.answer(frame("Ответы", "Пока пусто. Используй /q"))
        return
    lines = []
    for cat, q, a, ts in rows:
        q = (q or "").replace("\n", " ")
        a = (a or "").replace("\n", " ")
        if len(q) > 120:
            q = q[:120] + "…"
        if len(a) > 160:
            a = a[:160] + "…"
        lines.append(f"• [{cat}] {q}\n  ↳ {a}")
    await m.answer(frame("Ответы (последние)", "\n".join(lines)))

@dp.message(Command("when"))
async def cmd_when(m: types.Message):
    args = (m.text or "").split(maxsplit=1)
    if len(args) < 2:
        await m.answer("пример: /when 19:45 msk")
        return
    try:
        hhmm, zone = args[1].split() if " " in args[1] else (args[1], "msk")
        if not re.match(r"^\d{1,2}:\d{2}$", hhmm):
            await m.answer("время должно быть hh:mm")
            return
        hh, mm = map(int, hhmm.split(":"))
        aliases = {
            "msk": "Europe/Moscow",
            "ru": "Europe/Moscow",
            "cn": "Asia/Shanghai",
            "sh": "Asia/Shanghai",
            "zibo": "Asia/Shanghai",
        }
        src = aliases.get(zone.lower(), "Europe/Moscow")
        dt = datetime.now(ZoneInfo(src)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        msk = dt.astimezone(ZoneInfo("Europe/Moscow"))
        sha = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        def label(d):
            today = datetime.now(d.tzinfo).date()
            if d.date() == today:
                return "сегодня"
            if d.date() == today + timedelta(days=1):
                return "завтра"
            return d.strftime("%a")
        text = f"Москва: {msk:%H:%M} ({label(msk)}), Цзыбо/Шанхай: {sha:%H:%M} ({label(sha)})"
        await m.answer(frame("Конвертер времени", text))
    except Exception as e:
        await m.answer(str(e))

@dp.message(Command("weather"))
async def cmd_weather(m: types.Message):
    key = os.getenv("OWM_API_KEY", "")
    if not key:
        await m.answer("Погода не настроена (OWM_API_KEY).")
        return
    import requests
    _, city, partner, units = get_prefs(m.from_user.id)
    def _owm(city: str):
        try:
            r = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": key, "units": units, "lang": "ru"},
                timeout=8,
            )
            j = r.json()
            if r.status_code != 200:
                return f"{city}: ошибка ({j.get('message', 'unknown')})"
            desc = j.get("weather", [{}])[0].get("description", "")
            t = round(j.get("main", {}).get("temp", 0))
            return f"{city}: {desc}, {t}°"
        except Exception as e:
            return f"{city}: ошибка {e}"
    a = _owm(city); b = _owm(partner)
    await m.answer("Погода сейчас:\n" + a + "\n" + b)

@dp.message(Command("week"))
async def cmd_week(m: types.Message):
    uid = m.from_user.id
    day7 = (date.today() - timedelta(days=6)).isoformat()
    cur.execute("SELECT score FROM moods WHERE user_id=? AND day>=? ORDER BY day", (uid, day7))
    vals = [r[0] for r in cur.fetchall()]
    if vals:
        avg = sum(vals) / len(vals)
        best = max(vals)
        worst = min(vals)
        body = f"Настроение за 7 дней: {len(vals)} записей, ср. {avg:.1f}/10; лучш: {best}; худш: {worst}."
    else:
        body = "Нет записей за неделю. Используй /mood"
    cur.execute(
        "SELECT COUNT(*) FROM qanswers WHERE user_id=? AND ts>=datetime('now','-7 day')",
        (uid,),
    )
    qn = cur.fetchone()[0]
    if qn:
        body += f" Ответов на вопросы: {qn}."
    await m.answer(frame("Недельный дайджест", body))

@dp.message(Command("debug"))
async def cmd_debug(m: types.Message):
    _, tz, pet = get_user(m.from_user.id)
    _, city, partner, units = get_prefs(m.from_user.id)
    await m.answer(frame("Профиль", f"tz={tz}, petname={pet}\ncity={city}, partner={partner}, units={units}"))

@dp.message(Command("ping"))
async def cmd_ping(m: types.Message):
    await m.answer("pong")

@dp.message(Command("setwebhook"))
async def cmd_setwebhook(m: types.Message):
    if not USE_WEBHOOK:
        await m.answer("USE_WEBHOOK=0 — polling режим.")
        return
    if not PUBLIC_URL:
        await m.answer("PUBLIC_URL не задан.")
        return
    await bot.set_webhook(url=PUBLIC_URL + WEBHOOK_PATH, drop_pending_updates=True, secret_token=WEBHOOK_SECRET)
    await m.answer("webhook обновлён")

# ── STARTUP ────────────────────────────────────────────────────────────────
async def _set_commands():
    cmds = [
        BotCommand(command="start", description="Старт/меню"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="mood", description="Оценить настроение"),
        BotCommand(command="q", description="Вопрос (light/deep)"),
        BotCommand(command="q_history", description="Мои ответы"),
        BotCommand(command="when", description="Конвертер времени"),
        BotCommand(command="weather", description="Погода в двух городах"),
        BotCommand(command="week", description="Недельный дайджест"),
        BotCommand(command="debug", description="Диагностика"),
        BotCommand(command="ping", description="Проверка связи"),
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

async def on_cleanup(app: web.Application):
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
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

    return app

if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
