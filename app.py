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
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "1") == "1"
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

def get_prefs(uid: int):
    cur.execute("SELECT user_id,city,partner_city,units FROM prefs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO prefs(user_id) VALUES(?)", (uid,))
        db.commit()
        return (uid, "Moscow", "Zibo", "metric")
    return row

# ── BASIC HANDLERS ─────────────────────────────────────────────────────────
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
        # test handlers to verify path exists via browser/health checks
        async def hook_get(_):
            return web.Response(text="hook alive")
        app.router.add_get(WEBHOOK_PATH, hook_get)
        app.router.add_head(WEBHOOK_PATH, hook_get)
        app.router.add_options(WEBHOOK_PATH, hook_get)

        # webhook POST handler
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        print(f"[WEBHOOK] route registered at {WEBHOOK_PATH}")

    return app

if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)