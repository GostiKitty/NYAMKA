import os
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
DETA_PROJECT_KEY = os.environ.get("DETA_PROJECT_KEY", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")
SECRET_PATH = os.environ.get("WEBHOOK_SECRET_PATH", "telegram")
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

from aiogram.client.default import DefaultBotProperties
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

dp = Dispatcher()

# ---------------------- Keyboards ----------------------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Курс валют")],
    ],
    resize_keyboard=True
)

# ---------------------- Handlers ----------------------
@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer("Привет! Я бот NYAMKA 🐾", reply_markup=main_kb)

@dp.message(F.text == "📈 Курс валют")
async def currency_rates(m: Message):
    try:
        r = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        data = r.json()
        usd = data["Valute"]["USD"]["Value"]
        cny = data["Valute"]["CNY"]["Value"]
        text = f"💵 1 USD = {usd:.2f} RUB\n🇨🇳 1 CNY = {cny:.2f} RUB"
    except Exception as e:
        logger.error(f"Currency fetch error: {e}")
        text = "Не удалось получить курс валют 😔"
    await m.answer(text)

@dp.message()
async def echo(m: Message):
    await m.answer("Я тебя понял: " + m.text)

# ---------------------- Webhook ----------------------
async def on_startup(app: web.Application):
    if WEBHOOK_BASE:
        url = f"{WEBHOOK_BASE}/{SECRET_PATH}"
        logger.info(f"Setting webhook: {url}")
        await bot.set_webhook(url, drop_pending_updates=True)
    else:
        logger.warning("WEBHOOK_BASE not set, webhook not configured")

async def on_cleanup(app: web.Application):
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    async def ping(request):
        return web.json_response({"ok": True, "status": "alive"})
    app.router.add_get("/", ping)

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=f"/{SECRET_PATH}")

    setup_application(app, dp, bot=bot)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
