import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Update, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv
from loguru import logger

# Load .env if present (useful locally)
load_dotenv()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")  # e.g. https://your-app.koyeb.app
SECRET_PATH = os.environ.get("WEBHOOK_SECRET_PATH", "telegram")  # random path segment
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required.")

bot = Bot(TOKEN, parse_mode="HTML")
dp = Dispatcher()

# -------------------------- Handlers (put your logic here) --------------------------

@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer("Привет! Бот живёт на Koyeb 🚀. Напиши что-нибудь, и я повторю.")

@dp.message()
async def echo(m: Message):
    await m.answer(m.text)

# -------------------------- Webhook App --------------------------

async def on_startup(app: web.Application):
    # Set webhook if WEBHOOK_BASE is provided; otherwise just log a warning.
    if WEBHOOK_BASE:
        url = f"{WEBHOOK_BASE}/{SECRET_PATH}"
        logger.info(f"Setting webhook to: {url}")
        await bot.set_webhook(url, drop_pending_updates=True)
    else:
        logger.warning("WEBHOOK_BASE not provided — webhook is not set. "
                       "Ensure you set WEBHOOK_BASE env on Koyeb to your app URL.")

async def on_cleanup(app: web.Application):
    logger.info("Shutting down...")
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Healthcheck
    async def ping(request):
        return web.json_response({"ok": True, "service": "nyamka-bot", "status": "alive"})
    app.router.add_get("/", ping)

    # Telegram webhook endpoint
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=f"/{SECRET_PATH}")

    # Required for aiogram <-> aiohttp integration
    setup_application(app, dp, bot=bot)

    return app

if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
