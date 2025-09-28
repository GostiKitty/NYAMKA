import os
import asyncio
import json
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from loguru import logger

# ── ENV ────────────────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
DETA_PROJECT_KEY = os.environ.get("DETA_PROJECT_KEY", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")          # https://<app>.koyeb.app
SECRET_PATH  = os.environ.get("WEBHOOK_SECRET_PATH", "telegram").strip("/")  # <— ВАЖНО: убираем / с краёв
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

@router.message(F.text == "/setwebhook")
async def set_webhook_cmd(m: Message):
    if not WEBHOOK_BASE:
        await m.answer("WEBHOOK_BASE не задан в переменных окружения Koyeb.")
        return
    url = f"{WEBHOOK_BASE}/{SECRET_PATH}"
    try:
        await bot.set_webhook(url, drop_pending_updates=True, request_timeout=20)
        await m.answer(f"✅ Webhook обновлён:\n{url}")
    except Exception as e:
        await m.answer(f"❌ Ошибка при установке вебхука:\n<code>{e}</code>")

@router.message(F.text == "/webhookinfo")
async def webhook_info_cmd(m: Message):
    info = await bot.get_webhook_info()
    await m.answer(
        "<b>WebhookInfo</b>\n<code>" + json.dumps(info.model_dump(), ensure_ascii=False, indent=2) + "</code>"
    )

@router.message()
async def echo(m: Message):
    from_user = f"{m.from_user.id} @{m.from_user.username}" if m.from_user else "unknown"
    logger.info(f"✅ update: text from {from_user}: {m.text!r}")
    await m.answer("Я тебя понял: " + (m.text or ""))

# ── WEBHOOK STARTUP (safe with retries + диагностика) ─────────────────────────
async def _set_webhook_safe():
    logger.info(f"BOOT: WEBHOOK_BASE={WEBHOOK_BASE!r}, SECRET_PATH={SECRET_PATH!r}")
    if not WEBHOOK_BASE:
        logger.warning("WEBHOOK_BASE not set — skipping webhook setup")
        return

    url = f"{WEBHOOK_BASE}/{SECRET_PATH}"
    for attempt in range(1, 4):
        try:
            await bot.set_webhook(url, drop_pending_updates=True, request_timeout=20)
            logger.info(f"✅ Webhook set: {url}")
            return
        except Exception as e:
            logger.warning(f"Webhook attempt {attempt}/3 failed: {e}")
            await asyncio.sleep(2)
    logger.error("❌ Webhook not set after retries. Running without webhook.")

    # Логируем текущее состояние у Телеги
    try:
        info = await bot.get_webhook_info()
        logger.warning("Telegram getWebhookInfo: " + json.dumps(info.model_dump(), ensure_ascii=False))
    except Exception as e:
        logger.warning(f"getWebhookInfo failed: {e}")

# ── AIOHTTP APP ───────────────────────────────────────────────────────────────
async def on_startup(app: web.Application):
    await _set_webhook_safe()

async def on_cleanup(app: web.Application):
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Healthcheck
    async def ping(request):
        return web.json_response({"ok": True, "status": "alive"})
    app.router.add_get("/", ping)

    # GET-диагностика webhook-пути (POST приходит от Telegram)
    async def secret_get(request):
        return web.json_response({"ok": True, "webhook_path": f"/{SECRET_PATH}"})
    app.router.add_get(f"/{SECRET_PATH}", secret_get)

    # Webhook endpoint (POST от Telegram)
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=f"/{SECRET_PATH}")

    setup_application(app, dp, bot=bot)
    return app

# ── ENTRYPOINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
