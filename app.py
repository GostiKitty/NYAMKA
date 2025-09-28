import os
import asyncio
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, F
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

WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")   # e.g. https://<app>.koyeb.app
SECRET_PATH  = os.environ.get("WEBHOOK_SECRET_PATH", "telegram") # random secret path
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

# ── AIROGRAM BOOTSTRAP (v3.11) ────────────────────────────────────────────────
# parse_mode настраиваем через DefaultBotProperties (в 3.11 нельзя передавать прямо в Bot)
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ── KEYBOARDS ─────────────────────────────────────────────────────────────────
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Курс валют")],
    ],
    resize_keyboard=True
)

# ── HANDLERS ──────────────────────────────────────────────────────────────────
@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer(
        "Привет! Я бот NYAMKA 🐾\n"
        "Пробуй кнопки ниже или пиши сообщение — я отвечу.",
        reply_markup=main_kb
    )

@dp.message(F.text == "📈 Курс валют")
async def currency_rates(m: Message):
    """Показываем RUB→USD и RUB→CNY по данным ЦБ РФ."""
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

@dp.message(F.text == "/setwebhook")
async def set_webhook_cmd(m: Message):
    """Ручная установка вебхука из чата."""
    if not WEBHOOK_BASE:
        await m.answer("WEBHOOK_BASE не задан. Добавь переменную окружения на Koyeb.")
        return
    url = f"{WEBHOOK_BASE}/{SECRET_PATH}"
    try:
        await bot.set_webhook(url, drop_pending_updates=True)
        await m.answer(f"✅ Webhook обновлён:\n{url}")
    except Exception as e:
        await m.answer(f"❌ Ошибка при установке вебхука:\n<code>{e}</code>")

@dp.message()
async def echo(m: Message):
    """Простое эхо + лог входящих апдейтов, чтобы видеть их в консоли Koyeb."""
    from_user = f"{m.from_user.id} @{m.from_user.username}" if m.from_user else "unknown"
    logger.info(f"✅ update: text from {from_user}: {m.text!r}")
    await m.answer("Я тебя понял: " + (m.text or ""))

# ── WEBHOOK STARTUP (safe with retries) ───────────────────────────────────────
async def _set_webhook_safe():
    """Пытаемся поставить вебхук, но не падаем, если Телеграм временно недоступен."""
    if not WEBHOOK_BASE:
        logger.warning("WEBHOOK_BASE not set — skipping webhook setup")
        return
    url = f"{WEBHOOK_BASE}/{SECRET_PATH}"
    for attempt in range(1, 4):
        try:
            await bot.set_webhook(url, drop_pending_updates=True)
            logger.info(f"✅ Webhook set: {url}")
            return
        except Exception as e:
            logger.warning(f"Webhook attempt {attempt}/3 failed: {e}")
            await asyncio.sleep(2)
    logger.error("❌ Webhook not set after retries. Running without webhook.")

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

    # Debug GET на webhook-пути (POST приходит от Telegram, GET — для быстрой проверки в браузере)
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
