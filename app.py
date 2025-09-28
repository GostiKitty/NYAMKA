import os
import asyncio
import json
import contextlib
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from loguru import logger

# ── ENV ────────────────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

# ── AIROGRAM BOOTSTRAP (v3.11) ────────────────────────────────────────────────
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ── KEYBOARD ──────────────────────────────────────────────────────────────────
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📈 Курс валют")]],
    resize_keyboard=True
)

# ── HANDLERS ──────────────────────────────────────────────────────────────────
@router.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer(
        "Привет! Я бот NYAMKA 🐾\nЖми кнопки или пиши сообщение.",
        reply_markup=main_kb
    )

@router.message(F.text == "📈 Курс валют")
async def currency_rates(m: Message):
    try:
        r = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        data = r.json()
        usd = float(data["Valute"]["USD"]["Value"])
        cny = float(data["Valute"]["CNY"]["Value"])
        text = f"💵 1 USD = {usd:.2f} ₽\n🇨🇳 1 CNY = {cny:.2f} ₽"
    except Exception as e:
        logger.error(f"Currency fetch error: {e}")
        text = "Не удалось получить курс валют 😔"
    await m.answer(text)

@router.message(F.text == "/mode")
async def mode_cmd(m: Message):
    await m.answer("Приём апдейтов: <b>long polling</b> ✅")

@router.message()
async def echo(m: Message):
    from_user = f"{m.from_user.id} @{m.from_user.username}" if m.from_user else "unknown"
    logger.info(f"✅ update: text from {from_user}: {m.text!r}")
    await m.answer("Я тебя понял: " + (m.text or ""))

# ── POLLING LAUNCH ────────────────────────────────────────────────────────────
async def start_polling_background():
    # Гарантированно выключаем (вдруг раньше стоял) вебхук — иначе polling не работает
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🧹 Webhook deleted (drop_pending_updates=True)")
    except Exception as e:
        logger.warning(f"delete_webhook failed: {e}")

    allowed = dp.resolve_used_update_types()
    logger.info(f"Starting long polling with allowed_updates={allowed}")
    await dp.start_polling(bot, allowed_updates=allowed)

# ── AIOHTTP APP (для healthcheck на Koyeb) ────────────────────────────────────
async def on_startup(app: web.Application):
    # Стартуем polling параллельно с веб-сервером
    app["polling_task"] = asyncio.create_task(start_polling_background())

async def on_cleanup(app: web.Application):
    task = app.get("polling_task")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Healthcheck + простая диагностика
    async def ping(request):
        return web.json_response({"ok": True, "status": "alive", "mode": "polling"})
    app.router.add_get("/", ping)

    async def diag(request):
        me = await bot.get_me()
        return web.json_response({"bot": me.model_dump(), "mode": "polling"})
    app.router.add_get("/diag", diag)

    return app

# ── ENTRYPOINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
