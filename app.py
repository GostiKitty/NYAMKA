import os
import sys
import asyncio
import contextlib
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from loguru import logger

# ── ENV ────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

# ── Logging: minimal buffers, console only ─────────────────────────────────
logger.remove()  # remove default handler
logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "WARNING"))

# ── AIROGRAM BOOTSTRAP (v3.11) ────────────────────────────────────────────
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ── OPTIONAL UI: currency rates button ────────────────────────────────────
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📈 Курс валют")]],
    resize_keyboard=True
)

@router.message(F.text == "/start")
async def cmd_start__nyamka(m: Message):
    await m.answer("Привет! Я бот NYAMKA 🐾", reply_markup=main_kb)

@router.message(F.text == "📈 Курс валют")
async def currency_rates__nyamka(m: Message):
    try:
        r = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        data = r.json()
        usd = float(data["Valute"]["USD"]["Value"])
        cny = float(data["Valute"]["CNY"]["Value"])
        text = f"💵 1 USD = {usd:.2f} ₽\\n🇨🇳 1 CNY = {cny:.2f} ₽"
    except Exception as e:
        logger.error(f"Currency fetch error: {e}")
        text = "Не удалось получить курс валют 😔"
    await m.answer(text)

# ── BEGIN: imported handlers from notebook ────────────────────────────────

# # 1) Установка зависимостей
# !pip install -q --upgrade aiogram==3.4.1 openai>=1.40.0 python-dotenv>=1.0.1 requests>=2.31.0 PyYAML>=6.0.1 nest_asyncio>=1.6.0 tzdata>=2024.1
# print("✅ Готово")

# Ячейка 1 — ставим зависимости
#               openai==1.46.0 deta==1.2.0


import os
from aiohttp import web


# Ячейка 2 — ввод секретов скрыто (точками) и загрузка в окружение процесса
import os


# В Deta Space ключ не нужен, но для локального теста можно указать:
# DETA_PROJECT_KEY from env

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

OWM_API_KEY = os.getenv("OWM_API_KEY", "")

# Локальный путь к БД нам не нужен (Deta Base), оставим для совместимости:
os.environ["DB_PATH"] = "db.sqlite3"

print("✅ Секреты приняты (не сохранялись на диск).")


# Ячейка 3 — создаём структуру проекта и адаптер БД на Deta Base
from pathlib import Path

Path("lovebot").mkdir(exist_ok=True)

db_code = r'''
# lovebot/db_deta.py — простая обёртка над Deta Base
import os, time
from deta import Deta

def _deta():
    key = os.getenv("DETA_PROJECT_KEY")  # в Deta Space можно оставить пустым
    return Deta(key) if key else Deta()

deta = _deta()
prefs  = deta.Base("prefs")
moods  = deta.Base("moods")
chat   = deta.Base("chatlog")
qans   = deta.Base("qanswers")

def _fetch_all(base, query=None, limit=1000):
    query = query or {}
    res = base.fetch(query, limit=limit)
    items = list(res.items)
    while res.last:
        res = base.fetch(query, last=res.last, limit=limit)
        items.extend(res.items)
    return items

# ---------- PREFERENCES ----------
def get_prefs(uid: int):
    key = str(uid)
    it = prefs.get(key)
    if not it:
        it = {"key": key, "user_id": uid, "city": "Moscow", "partner_city": "Zibo", "units": "metric", "petname": "зайчик"}
        prefs.put(it)
    return it

def set_prefs(uid: int, **kwargs):
    it = get_prefs(uid)
    for k, v in kwargs.items():
        if v is not None:
            it[k] = v
    prefs.put(it)
    return it

def list_user_ids():
    items = _fetch_all(prefs, {})
    out = []
    for it in items:
        try:
            out.append(int(it.get("key") or it.get("user_id")))
        except Exception:
            pass
    return list(sorted(set(out)))

# ---------- MOODS ----------
def set_mood(uid: int, day: str, rating: int, note: str = ""):
    key = f"{uid}:{day}"
    item = {"key": key, "user_id": uid, "day": day, "rating": int(rating), "note": note or "", "ts": int(time.time())}
    moods.put(item)
    return item

def get_mood(uid: int, day: str):
    return moods.get(f"{uid}:{day}")

def week_moods(uid: int, days: list[str]):
    out = []
    for d in days:
        it = moods.get(f"{uid}:{d}")
        if it:
            out.append(it)
    return out

# ---------- CHAT LOG ----------
def log_chat(uid: int, role: str, content: str):
    chat.put({"user_id": uid, "role": role, "content": content, "ts": int(time.time())})

def fetch_chat(uid: int, limit: int = 100):
    items = _fetch_all(chat, {"user_id": uid}, limit=limit)
    items.sort(key=lambda x: x.get("ts", 0))
    return items[-limit:]

# ---------- Q&A ----------
def save_answer(uid: int, category: str, question: str, answer: str):
    qans.put({"user_id": uid, "category": category, "question": question, "answer": answer, "ts": int(time.time())})

def fetch_answers(uid: int, since_ts: int | None = None, limit: int = 100):
    items = _fetch_all(qans, {"user_id": uid}, limit=limit)
    if since_ts:
        items = [i for i in items if i.get("ts", 0) >= since_ts]
    items.sort(key=lambda x: x.get("ts", 0))
    return items[-limit:]
'''

(Path("lovebot/db_deta.py")).write_text(db_code, encoding="utf-8")
print("✅ db_deta.py создан")


# 3) Санити-чек: бот, OpenAI, OpenWeather
# removed nest_asyncio for server env
from dotenv import load_dotenv
# removed nest_asyncio.apply()
load_dotenv("lovebot/.env")

from aiogram import Bot
import asyncio

# BOT_TOKEN from env
# OPENAI_API_KEY from env
# OWM_API_KEY from env

print("🔹 BOT_TOKEN:", bool(BOT_TOKEN))
print("🔹 OPENAI_API_KEY:", bool(OPENAI_API_KEY))
print("🔹 OWM_API_KEY:", bool(OWM_API_KEY))

async def tg_check():
    if not BOT_TOKEN: 
        print("⛔ Нет BOT_TOKEN"); 
        return
    b = Bot(BOT_TOKEN)
    me = await b.get_me()
    print("✅ Бот найден:", me.username)
    await b.session.close()


# OpenAI — мини-пинг
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        cli = OpenAI(api_key=OPENAI_API_KEY)
        r = cli.chat.completions.create(
            model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            messages=[{"role":"user","content":"Скажи «ок»"}],
            max_tokens=5,
        )
        print("✅ OpenAI ответ:", r.choices[0].message.content)
    except Exception as e:
        print("⛔ OpenAI ошибка:", e)

# Погода
if OWM_API_KEY:
    try:
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                         params={"q":"Moscow,RU","appid":OWM_API_KEY,"units":"metric","lang":"ru"},
                         timeout=6)
        print("🌦 OpenWeather статус:", r.status_code, r.json().get("weather",[{}])[0].get("description"))
    except Exception as e:
        print("⛔ OpenWeather ошибка:", e)


# Ячейка 3 — патч main.py под DB_PATH + минималистичное меню (только эмодзи)
from pathlib import Path
import re

p = Path("lovebot/main.py")
assert p.exists(), "Не нашла lovebot/main.py — сначала сгенерируй/вставь свой основной файл бота."

s = p.read_text(encoding="utf-8")



# Ячейка 4 — lovebot/llm.py
llm_code = r'''
import os
from openai import OpenAI

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
_temp  = float(os.getenv("LLM_TEMP", "0.8"))

_client = None
def _client_ok():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client

def reply(hist: list[dict], system: str | None = None) -> str:
    """hist = [{"role":"user"/"assistant","content":"..."}, ...]"""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(hist)
    r = _client_ok().chat.completions.create(model=MODEL, messages=msgs, temperature=_temp)
    return (r.choices[0].message.content or "").strip()
'''
from pathlib import Path
Path("lovebot/llm.py").write_text(llm_code, encoding="utf-8")
print("✅ llm.py создан")


# Ячейка 4 — создаём webhook.py
from pathlib import Path

WEBHOOK = r'''# webhook.py — веб-сервер для aiogram v3 (Replit)
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lovebot import main as lm

bot = lm.bot
dp = lm.dp

WEBHOOK_PATH = "/tg"
PUBLIC_URL = os.getenv("PUBLIC_URL")  # https://<project>.<user>.repl.co
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-secret")
PORT = int(os.getenv("PORT", "8080"))

async def on_startup(app: web.Application):
    try:
        await lm._set_commands()
    except Exception:
        pass
    try:
        lm.SCHED = AsyncIOScheduler()
        lm.SCHED.start()
        lm._schedule_all_users()
    except Exception:
        pass
    await bot.delete_webhook(drop_pending_updates=True)
    if PUBLIC_URL:
        await bot.set_webhook(url=PUBLIC_URL + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET)
    else:
        print("⚠️ PUBLIC_URL не задан — добавь его в Secrets на Replit.")

async def on_shutdown(app: web.Application):
    try:
        await bot.delete_webhook()
    except Exception:
        pass

async def health(_):
    return web.Response(text="ok")

app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

SimpleRequestHandler(dp, bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

app.router.add_get("/", health)

    # removed run_app
'''
Path("webhook.py").write_text(WEBHOOK, encoding="utf-8")
print("✅ webhook.py создан")


# 4) Пишем lovebot/llm.py
from pathlib import Path
Path("lovebot").mkdir(exist_ok=True)

LLM_CODE = r'''
import os
from openai import OpenAI

MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_KEY = os.getenv("OPENAI_API_KEY")
BASE    = os.getenv("OPENAI_BASE_URL")  # опционально
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
RETRIES = int(os.getenv("LLM_RETRIES", "1"))

_client = None
def _client_ok():
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("OPENAI_API_KEY is empty")
        _client = OpenAI(api_key=API_KEY, base_url=BASE) if BASE else OpenAI(api_key=API_KEY)
        # client-level timeout/retries
        _client._settings["timeout"] = TIMEOUT
        _client._settings["max_retries"] = RETRIES
    return _client

SYSTEM = (
    "Ты — внимательная, тёплая партнёрша. Пиши по-русски, конкретно и по делу. "
    "Всегда PG-21 (с явной эротики и порно). "
    "Мат всегда "
    "Эмодзи по умолчанию не используй; только если очень уместно — максимум один. "
)

def _context(ctx: dict) -> str:
    pet = ctx.get("petname", "зайчик")
    msk = ctx.get("msk", "")
    sha = ctx.get("sha", "")
    left = ctx.get("days_left", "")
    tgt = ctx.get("target", "")
    return (
        f"Контекст: Москва {msk}, Zibo {sha}. До июля 2026: {left} дней (цель: {tgt}). "
        f"Обращайся к собеседнику как «{pet}». Если вопрос неполный — задай один короткий уточняющий вопрос."
    )

def reply_as_girlfriend(history, ctx):
    client = _client_ok()
    messages = [
        {"role":"system","content":SYSTEM},
        {"role":"system","content":_context(ctx)},
    ]
    for h in history:
        role = h.get("role","user")
        content = (h.get("content") or "").strip()
        if not content: 
            continue
        if role not in ("user","assistant","system"):
            role = "user"
        messages.append({"role":role, "content":content})

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=220,
    )
    txt = (resp.choices[0].message.content or "").strip()
    return txt or "..."
'''
Path("lovebot/llm.py").write_text(LLM_CODE, encoding="utf-8")
print("✅ llm.py записан")


# Ячейка 5 — lovebot/main.py
from pathlib import Path
main_code = r'''
# -*- coding: utf-8 -*-
import os, asyncio, random, requests
from datetime import date, datetime, timedelta

# aiogram imports adjusted by main app
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db_deta import (
    get_prefs, set_prefs, list_user_ids,
    set_mood, get_mood, week_moods,
    log_chat, fetch_chat,
    save_answer, fetch_answers,
)
from .llm import reply as llm_reply

# BOT_TOKEN from env
# bot = Bot(...)  # replaced by main app bot
# dp = Dispatcher(...)  # replaced by main app dp
# ---------- ВОПРОСЫ ----------
QUESTIONS = {
    "light": [
        "Какой момент недели тебе запомнился больше всего и почему?",
        "Что тебя порадовало сегодня?",
        "Какая мелочь сделала твой день лучше?",
    ],
    "deep": [
        "О чём тебе сейчас труднее всего говорить вслух?",
        "Когда ты чувствуешь себя по-настоящему в безопасности?",
        "Что ты хотел(а) бы чаще получать от меня в поддержке?",
    ],
    "flirt": [
        "Какая привычка у меня тебя больше всего заводит?",
        "Где бы ты хотел(а) поцеловать меня прямо сейчас?",
        "Что ты хотел(а) бы попробовать вместе, только вдвоём?",
    ],
}

Q_WAIT: dict[int, dict] = {}   # ожидание ответа на вопрос дня {uid: {"cat":..,"q":..}}

# ---------- КНОПКИ-МЕНЮ (ТОЛЬКО ЭМОДЗИ) ----------
def menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💙", callback_data="mood")
    kb.button(text="💌", callback_data="q")
    kb.button(text="🕒", callback_data="time")
    kb.button(text="🌊", callback_data="weather")
    kb.button(text="📅", callback_data="week")
    kb.adjust(5)
    return kb.as_markup()

def today_panel(uid: int):
    pref = get_prefs(uid)
    msk = datetime.utcnow() + timedelta(hours=3)
    sha = datetime.utcnow() + timedelta(hours=8)   # Шанхай/Цзыбо UTC+8
    return (
        f"⏱ Москва: <b>{msk:%H:%M}</b>  •  Цзыбо/Шанхай: <b>{sha:%H:%M}</b>\n"
        f"🏙 Москва: {pref.get('city','Moscow')}  •  Партнёр: {pref.get('partner_city','Zibo')}"
    )

# ---------- /start /menu ----------
@router.message(Command("start"))
async def start_cmd(m: types.Message):
    uid = m.from_user.id
    get_prefs(uid)  # инициализируем
    await m.answer(today_panel(uid), reply_markup=menu_kb())

@router.message(Command("menu"))
async def menu_cmd(m: types.Message):
    await m.answer(today_panel(m.from_user.id), reply_markup=menu_kb())

# ---------- НАСТРОЕНИЕ ----------
@router.callback_query(F.data == "mood")
async def cb_mood(c: types.CallbackQuery):
    uid = c.from_user.id
    day = date.today().isoformat()
    old = get_mood(uid, day)
    msg = "Оцени день от 1 до 10:"
    if old:
        msg += f" (сейчас {old.get('rating')}/10)"
    await c.message.answer(msg)
    await c.answer()

@router.message(F.text.regexp(r"^\s*[1-9]|10\s*$"))
async def set_mood_msg(m: types.Message):
    uid = m.from_user.id
    rating = int((m.text or "0").strip())
    rating = max(1, min(10, rating))
    day = date.today().isoformat()
    set_mood(uid, day, rating)
    await m.answer(f"💙 Сохранила: {rating}/10")

# ---------- ВОПРОСЫ ----------
def _q_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="😌 легкие", callback_data="qcat:light")
    kb.button(text="🫶 глубже", callback_data="qcat:deep")
    kb.button(text="🔥 флирт",  callback_data="qcat:flirt")
    kb.button(text="Ещё вопрос", callback_data="qnext")
    kb.adjust(3,1)
    return kb.as_markup()

@router.callback_query(F.data == "q")
async def cb_q(c: types.CallbackQuery):
    await c.message.answer("Выбери тему вопроса:", reply_markup=_q_kb())
    await c.answer()

@router.callback_query(F.data.startswith("qcat:"))
async def cb_qcat(c: types.CallbackQuery):
    uid = c.from_user.id
    cat = c.data.split(":")[1]
    q = random.choice(QUESTIONS.get(cat, QUESTIONS["light"]))
    Q_WAIT[uid] = {"cat": cat, "q": q}
    await c.message.answer("Вопрос:\n" + q + "\n\n(пришли один ответ — я его сохраню)")
    await c.answer()

@router.callback_query(F.data == "qnext")
async def cb_qnext(c: types.CallbackQuery):
    uid = c.from_user.id
    cat = Q_WAIT.get(uid, {}).get("cat", "light")
    q = random.choice(QUESTIONS.get(cat, QUESTIONS["light"]))
    Q_WAIT[uid] = {"cat": cat, "q": q}
    await c.message.answer("Вопрос:\n" + q + "\n\n(пришли один ответ — я его сохраню)")
    await c.answer()

@router.message(F.text & ~F.text.startswith("/") & ~F.via_bot)
async def dialog(m: types.Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()

    # Если ждём ответ на вопрос — сохраняем
    if uid in Q_WAIT:
        pack = Q_WAIT.pop(uid)
        save_answer(uid, pack.get("cat","light"), pack.get("q",""), txt)
        await m.answer("💾 Ответ сохранила. Хочешь ещё — жми «Ещё вопрос».")
        return

    # Иначе — обычный диалог через ИИ
    pref = get_prefs(uid)
    system = (
        "Ты заботливая, немного флиртовая партнерша. Короткие тёплые ответы, без шаблонов и повторов. "
        f"Обращайся по имени-ласковому: «{pref.get('petname','зайчик')}». "
        "Допускается лёгкая неформальность и редкая обсценная лексика, если это уместно и не токсично."
    )
    hist = [{"role":"user","content": txt}]
    log_chat(uid, "user", txt)
    try:
        out = llm_reply(hist, system=system)
    except Exception:
        out = "Сорян, у меня затык с нейросетью. Напиши ещё раз, ок?"
    log_chat(uid, "assistant", out)
    await m.answer(out)

# ---------- ПОГОДА И ВРЕМЯ ----------
def _owm(city: str, appid: str, units="metric", lang="ru"):
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": appid, "units": units, "lang": lang},
            timeout=10
        )
        if r.status_code != 200:
            return f"{city}: ошибка ({r.status_code})"
        j = r.json()
        desc = j.get("weather",[{}])[0].get("description","")
        t = j.get("main",{}).get("temp","?")
        return f"{city}: {desc}, {t}°"
    except Exception as e:
        return f"{city}: ошибка {e}"

@router.callback_query(F.data == "weather")
async def cb_weather(c: types.CallbackQuery):
    uid = c.from_user.id
    pref = get_prefs(uid)
    appid = os.getenv("OWM_API_KEY","")
    if not appid:
        await c.message.answer("Погода: не настроен ключ OWM.")
    else:
        a = _owm(pref.get("city","Moscow"), appid, units=pref.get("units","metric"))
        b = _owm(pref.get("partner_city","Zibo"), appid, units=pref.get("units","metric"))
        await c.message.answer("Погода сейчас:\n" + a + "\n" + b)
    await c.answer()

@router.callback_query(F.data == "time")
async def cb_time(c: types.CallbackQuery):
    msk = datetime.utcnow() + timedelta(hours=3)
    sha = datetime.utcnow() + timedelta(hours=8)
    await c.message.answer(f"⏱ Москва: <b>{msk:%H:%M}</b>\n⏱ Цзыбо/Шанхай: <b>{sha:%H:%M}</b>")
    await c.answer()

# ---------- НЕДЕЛЬНЫЙ ДАЙДЖЕСТ ----------
@router.callback_query(F.data == "week")
async def cb_week(c: types.CallbackQuery):
    uid = c.from_user.id
    days = [(date.today()-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    ms = week_moods(uid, days)
    line = []
    nums = []
    for d in days:
        one = next((x for x in ms if x["day"]==d), None)
        if one:
            nums.append(int(one.get("rating",0)))
            line.append(str(one.get("rating")))
        else:
            line.append("·")
    avg = (sum(nums)/len(nums)) if nums else 0.0

    # кусочек чата и Q&A для ИИ
    ch = fetch_chat(uid, limit=80)
    qa = fetch_answers(uid, since_ts=int((datetime.now()-timedelta(days=7)).timestamp()), limit=20)

    parts = []
    if qa:
        t = "\n".join([f"[{x.get('category')}] {x.get('question')}\n ↳ {x.get('answer')}" for x in qa[-6:]])
        parts.append("Ответы на вопросы:\n"+t)
    if ch:
        t = "\n".join([f"{x.get('role')[:1].upper()}: {(x.get('content') or '')[:200]}" for x in ch[-10:]])
        parts.append("Фрагменты чата:\n"+t)

    req = (
        f"Шкала настроения за 7 дней: {' '.join(line)}, среднее: {avg:.1f}/10. "
        "Собери короткий тёплый дайджест: 2−3 ноты недели, что порадовало/поддержало, где было напряжение, "
        "и 2 шага на следующую неделю."
    )
    body = f"💙 Настроение: {' '.join(line)} (ср. {avg:.1f}/10)"
    try:
        txt = llm_reply([{"role":"user","content": req + "\n\n" + "\n\n".join(parts)}])
        body += "\n\n" + txt
    except Exception:
        body += "\n\n(ИИ сейчас недоступен — сводка базовая)"
    await c.message.answer(body)
    await c.answer()

# ---------- ХЕЛПЕР: команды в меню Telegram (очистим)
async def _set_commands():
    try:
        await bot.set_my_commands([])  # пустой список — ничего не показываем
    except Exception:
        pass

# ---------- MAIN для локального запуска (НЕ используется в Space)
async def main():
    await _set_commands()
    print("Polling is not intended for Deta Space. Use server.py (webhook).")
    await router.start_polling(bot)

    import asyncio
'''
Path("lovebot/main.py").write_text(main_code, encoding="utf-8")
print("✅ main.py создан")


# 5) Полная перезапись lovebot/main.py: /style, /nick, /week (муд+Q&A), ритуалы, реакции, заметка к настроению,
# погода, конвертер, меню, ошибки, тест ИИ, диалог с ИИ и безопасный shutdown.
from pathlib import Path

MAIN_CODE = r'''# -*- coding: utf-8 -*-
import os, re, asyncio, sqlite3, logging, random, traceback
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# aiogram imports adjusted by main app
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.enums import ChatAction

from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ---------- БАЗА НАСТРОЕК ----------
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
load_dotenv("lovebot/.env")

# BOT_TOKEN from env
OPENAI_KEY  = os.getenv("OPENAI_API_KEY")
# OWM_API_KEY from env
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
LLM_RETRIES = int(os.getenv("LLM_RETRIES", "1"))
TARGET_DATE = date(2026, 7, 1)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

THEME = {
    "bar":     "💙" + "━"*24,
    "title":   "🔷",
    "bullet":  "🔹",
    "ok":      "✅",
    "warn":    "⚠️",
    "weather": "🌊",
    "time":    "🕒",
}
def frame(title: str, body: str) -> str:
    return f"{THEME['bar']}\n{THEME['title']} {title}\n{body}\n{THEME['bar']}"

# ---------- LLM ----------
USE_LLM = bool(OPENAI_KEY)
LLM_IMPORT_ERROR = ""
try:
    from llm import reply_as_girlfriend
except Exception as e:
    reply_as_girlfriend = None
    LLM_IMPORT_ERROR = str(e)
    USE_LLM = False

# ---------- TELEGRAM ----------
# bot = Bot(...)  # replaced by main app bot
# dp = Dispatcher(...)  # replaced by main app dp
# ---------- ГЛОБАЛЬНОЕ СОСТОЯНИЕ ----------
AWAIT_MOOD_NOTE = set()   # ждём заметку к настроению
Q_LAST_CAT = {}           # последняя категория вопроса
Q_WAIT = {}               # ожидаем ответ на заданный вопрос
LAST_LLM_ERROR = ""
LAST_RUNTIME_ERROR = ""
SCHED = None  # AsyncIOScheduler будет создан в main()

# ---------- БД ----------
db = sqlite3.connect("db.sqlite3")
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, tz TEXT DEFAULT 'Europe/Moscow', petname TEXT DEFAULT 'зайчик', cooldown REAL DEFAULT 0)")
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
cur.execute("CREATE TABLE IF NOT EXISTS chatlog (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")
cur.execute("CREATE TABLE IF NOT EXISTS moods (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, day TEXT, rating INTEGER, note TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS qanswers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, category TEXT, question TEXT, answer TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")
db.commit()

def ensure_prefs(uid: int):
    cur.execute("SELECT 1 FROM prefs WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO prefs(user_id) VALUES(?)", (uid,))
        db.commit()

def get_user(uid: int):
    cur.execute("SELECT user_id,tz,petname,cooldown FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id) VALUES(?)", (uid,))
        db.commit()
        row = (uid, "Europe/Moscow", "зайчик", 0.0)
    ensure_prefs(uid)
    return row

def get_prefs(uid: int) -> dict:
    ensure_prefs(uid)
    cur.execute("SELECT city,partner_city,units,flirt_auto,profanity,style_mode,ritual_morning,ritual_night,r_morning_hour,r_night_hour FROM prefs WHERE user_id=?", (uid,))
    c, pc, u, fl, pr, sm, rm, rn, mh, nh = cur.fetchone()
    return {"city":c,"partner_city":pc,"units":u,"flirt_auto":int(fl),"profanity":int(pr),"style_mode":sm,
            "ritual_morning":int(rm),"ritual_night":int(rn),"r_morning_hour":int(mh),"r_night_hour":int(nh)}

def add_chat(uid: int, role: str, content: str):
    cur.execute("INSERT INTO chatlog(user_id,role,content) VALUES(?,?,?)", (uid, role, content))
    db.commit()

# ---------- UI ----------
def today_panel() -> str:
    try:
        msk = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m %H:%M")
        sha = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%d.%m %H:%M")
    except Exception:
        now = datetime.now().strftime("%d.%m %H:%M"); msk = sha = now
    left = (TARGET_DATE - date.today()).days
    cnt = "🎉 Июль 2026 уже наступил!" if left <= 0 else f"{THEME['bullet']} До июля 2026: {left} дн. (до {TARGET_DATE.strftime('%d.%m.%Y')})"
    body = f"{THEME['bullet']} Москва: {msk}\n{THEME['bullet']} Zibo/Шанхай: {sha}\n\n{cnt}"
    return frame("Сегодня", body)

def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔷 Сегодня", callback_data="today")],
        [InlineKeyboardButton(text="💙 Настроение", callback_data="mood")],
        [InlineKeyboardButton(text="💙 Вопрос дня", callback_data="q")],
        [InlineKeyboardButton(text=f"{THEME['time']} Конвертер", callback_data="when")],
        [InlineKeyboardButton(text=f"{THEME['weather']} Погода", callback_data="weather")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ])

async def typing(m: types.Message, seconds: float = 0.3):
    try:
        await bot.send_chat_action(m.chat.id, ChatAction.TYPING)
        await asyncio.sleep(seconds)
    except Exception:
        pass

# ---------- ПОГОДА ----------
def fetch_weather(city: str, units: str) -> str:
    if not OWM_API_KEY:
        return "Нет ключа OpenWeather (OWM_API_KEY)"
    try:
        import requests
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                         params={"q":city,"appid":OWM_API_KEY,"units":units,"lang":"ru"}, timeout=8)
        j = r.json()
        if r.status_code != 200:
            return f"{city}: ошибка ({j.get('message','unknown')})"
        t = round(j["main"]["temp"])
        desc = j["weather"][0]["description"]
        feels = round(j["main"].get("feels_like", t))
        return f"{city}: {t}°, {desc}; ощущ. {feels}°"
    except Exception as e:
        return f"{city}: не удалось ({e})"

# ---------- КОНВЕРТЕР ВРЕМЕНИ ----------
ALIASES = {"msk":"Europe/Moscow","moscow":"Europe/Moscow","ru":"Europe/Moscow",
           "cn":"Asia/Shanghai","sh":"Asia/Shanghai","shanghai":"Asia/Shanghai","zibo":"Asia/Shanghai"}

def parse_when(s: str):
    parts = (s or "").strip().split()
    if not parts: raise ValueError("нужно /when 19:30 msk")
    t = parts[0]
    if not re.match(r"^\d{1,2}:\d{2}$", t): raise ValueError("время должно быть hh:mm")
    zone = parts[1] if len(parts) > 1 else "msk"
    tz = ALIASES.get(zone.lower(), zone)
    hh, mm = map(int, t.split(":")); return hh, mm, tz

def when_convert(hh: int, mm: int, src_tz: str) -> str:
    dt = datetime.now(ZoneInfo(src_tz)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    msk = dt.astimezone(ZoneInfo("Europe/Moscow"))
    sha = dt.astimezone(ZoneInfo("Asia/Shanghai"))
    def label(d):
        today = datetime.now(d.tzinfo).date()
        if d.date()==today: suf="сегодня"
        elif d.date()==today+timedelta(days=1): suf="завтра"
        else: suf=d.strftime("%a")
        return d.strftime("%d.%m %H:%M")+" ("+suf+")"
    body = f"{THEME['bullet']} Москва: {label(msk)}\n{THEME['bullet']} Zibo/Шанхай: {label(sha)}"
    return frame("Конвертер времени", body)

# ---------- НАСТРОЕНИЕ ----------
def mood_kb():
    r1=[InlineKeyboardButton(text=str(i), callback_data=f"mrate:{i}") for i in range(1,6)]
    r2=[InlineKeyboardButton(text=str(i), callback_data=f"mrate:{i}") for i in range(6,11)]
    return InlineKeyboardMarkup(inline_keyboard=[r1,r2,[InlineKeyboardButton(text="📝 Заметка",callback_data="mnote")]])

@router.message(Command("mood"))
async def mood_cmd(m: types.Message):
    await m.answer(frame("Настроение", "Оцени день 1–10"), reply_markup=mood_kb())

@router.callback_query(F.data=="mood")
async def cb_mood(c: types.CallbackQuery):
    await c.message.answer(frame("Настроение", "Оцени день 1–10"), reply_markup=mood_kb()); await c.answer()

@router.callback_query(F.data.startswith("mrate:"))
async def cb_mrate(c: types.CallbackQuery):
    uid=c.from_user.id; rating=int(c.data.split(":")[1]); day=date.today().isoformat()
    cur.execute("DELETE FROM moods WHERE user_id=? AND day=?", (uid,day))
    cur.execute("INSERT INTO moods(user_id,day,rating,note) VALUES(?,?,?,?)", (uid,day,rating,""))
    db.commit()
    await c.message.answer(f"{THEME['ok']} Сохранила: {rating}/10"); await c.answer()

@router.callback_query(F.data=="mnote")
async def cb_mnote(c: types.CallbackQuery):
    AWAIT_MOOD_NOTE.add(c.from_user.id)
    await c.message.answer("Пришли одну короткую заметку."); await c.answer()

@router.message(Command("moodweek"))
async def moodweek(m: types.Message):
    uid=m.from_user.id
    days=[(date.today()-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    cur.execute("SELECT day,rating FROM moods WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY day",(uid,days[0],days[-1]))
    rows=dict(cur.fetchall()); line=[str(rows.get(d,"·")) for d in days]
    vals=[rows[d] for d in days if d in rows]; avg=(sum(vals)/len(vals)) if vals else 0.0
    body=" ".join(line); 
    if vals: body+=f"\nсреднее: {avg:.1f}/10"
    await m.answer(frame("Настроение — 7 дней", body))

# ---------- ВОПРОСЫ ДЛЯ БЛИЗОСТИ ----------
QUESTIONS={
    "light":[
        "Что из мелочей делает тебя счастливее всего?","Какой момент недели хочешь сохранить?",
        "Когда ты чувствуешь себя в безопасности рядом со мной?","Что тебя сегодня приятно удивило?",
        "Какая песня сейчас у тебя на репите — почему?","Какую маленькую победу ты отметил(а) на неделе?",
        "Есть ли запах/вкус, который сразу поднимает настроение?","Какая забота от меня была бы особенно приятной завтра?",
        "Как ты заряжаешься, если устал(а)?","О чём хочешь поговорить без спешки?"
    ],
    "deep":[
        "Чему тебя научила самая сложная ошибка?","Какие слова поддержки работают на тебе лучше всего?",
        "О чём тебе трудно просить — даже меня?","Какая ценность тебе особенно важна в отношениях?",
        "Когда ты в последний раз реально собой гордился(ась)?","Что тебя больше всего успокаивает в тяжёлые дни?",
        "Как ты понимаешь, что тебя услышали по-настоящему?","О каком своём качестве ты бы хотел(а) заботиться больше?",
        "Как я могу лучше заботиться о тебе на следующей неделе?","Что помогло бы нам ссориться реже и мириться мягче?"
    ],
    "future":[
        "Как видишь наш идеальный совместный выходной?","Какую традицию нам бы ввести?","Три маленьких мечты на год — какие?",
        "Какой мини-проект мы могли бы сделать вдвоём за месяц?","Каким ты хочешь помнить это лето?",
        "Куда сбежать на 48 часов, если завтра можно всё?","Чему нам стоит научиться вместе?",
        "Как мы отметим день, когда снова увидимся?","Какое «микроприключение» устроим на этой неделе?",
        "Какой приятный сюрприз я могу сделать тебе в обычный день?"
    ]
}
def q_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Лёгкие", callback_data="qcat:light"),
         InlineKeyboardButton(text="Глубже", callback_data="qcat:deep"),
         InlineKeyboardButton(text="О будущем", callback_data="qcat:future")],
        [InlineKeyboardButton(text="Ещё вопрос", callback_data="qnext")]
    ])

@router.message(Command("q"))
async def q_cmd(m: types.Message):
    await m.answer(frame("Вопросы", "Выбери категорию"), reply_markup=q_menu())

@router.callback_query(F.data=="q")
async def cb_q(c: types.CallbackQuery):
    await c.message.answer(frame("Вопросы", "Выбери категорию"), reply_markup=q_menu()); await c.answer()

@router.callback_query(F.data.startswith("qcat:"))
async def cb_qcat(c: types.CallbackQuery):
    uid=c.from_user.id; cat=c.data.split(":")[1]; Q_LAST_CAT[uid]=cat
    q=random.choice(QUESTIONS.get(cat, QUESTIONS["light"]))
    Q_WAIT[uid]={"cat":cat,"q":q}
    text="Вопрос:\n"+q+"\n\n(пришли один ответ — я его сохраню 💙)"
    await c.message.answer(text); await c.answer()

@router.callback_query(F.data=="qnext")
async def cb_qnext(c: types.CallbackQuery):
    uid=c.from_user.id; cat=Q_LAST_CAT.get(uid,"light")
    q=random.choice(QUESTIONS.get(cat, QUESTIONS["light"]))
    Q_WAIT[uid]={"cat":cat,"q":q}
    text="Вопрос:\n"+q+"\n\n(пришли один ответ — я его сохраню 💙)"
    await c.message.answer(text); await c.answer()

@router.message(Command("q_history"))
async def q_hist(m: types.Message):
    uid=m.from_user.id
    cur.execute("SELECT category,question,answer,ts FROM qanswers WHERE user_id=? ORDER BY id DESC LIMIT 5",(uid,))
    rows=cur.fetchall()
    if not rows: return await m.answer(frame("Ответы на вопросы","Пока пусто. Выбери категорию в /q и ответь на любой вопрос."))
    lines=[]
    for cat,q,a,ts in rows:
        q=(q or "").strip().replace("\n"," "); a=(a or "").strip().replace("\n"," ")
        if len(q)>120: q=q[:120]+"…"; 
        if len(a)>160: a=a[:160]+"…"
        lines.append(f"• [{cat}] {q}\n  ↳ {a}")
    await m.answer(frame("Ответы на вопросы (последние)","\n".join(lines)))

# ---------- СТИЛЬ / ОБРАЩЕНИЯ ----------
PETNAMES_POOL=['зайчик','котик','солнышко','любимый','малыш','милый','рыбка','лисёнок','звёздочка','котёнок','сладкий']
PET_LAST={}
def pick_petname(uid:int, style_mode:str, fixed:str)->str:
    if style_mode in ("auto","random"):
        opts=PETNAMES_POOL; last=PET_LAST.get(uid); cand=[p for p in opts if p!=last] or opts
        choice=random.choice(cand); PET_LAST[uid]=choice; return choice
    return fixed or "зайчик"

def style_kb(p:dict):
    prof_map={0:"off",1:"soft",2:"spicy"}
    rows=[
        [InlineKeyboardButton(text=f"Мат: {prof_map.get(int(p.get('profanity',0)),0)}", callback_data="sty:prof")],
        [InlineKeyboardButton(text=f"Флирт: {'on' if int(p.get('flirt_auto',1)) else 'off'}", callback_data="sty:flirt")],
        [InlineKeyboardButton(text=f"Обращения: {p.get('style_mode','auto')}", callback_data="sty:addr")],
    ]; return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(Command("style"))
async def style_cmd(m: types.Message):
    p=get_prefs(m.from_user.id); body="Переключай мат, флирт и режим обращений. В fixed использую ник из /nick."
    await m.answer(frame("Стиль диалога", body), reply_markup=style_kb(p))

@router.callback_query(F.data.startswith("sty:"))
async def cb_style(c: types.CallbackQuery):
    uid=c.from_user.id; p=get_prefs(uid); action=c.data.split(":")[1]
    if action=="prof":
        prof=(int(p.get("profanity",0))+1)%3; cur.execute("UPDATE prefs SET profanity=? WHERE user_id=?", (prof,uid))
    elif action=="flirt":
        fl=0 if int(p.get("flirt_auto",1)) else 1; cur.execute("UPDATE prefs SET flirt_auto=? WHERE user_id=?", (fl,uid))
    elif action=="addr":
        mode=p.get("style_mode","auto"); mode="fixed" if mode=="auto" else "auto"
        cur.execute("UPDATE prefs SET style_mode=? WHERE user_id=?", (mode,uid))
    db.commit(); p=get_prefs(uid)
    try: await c.message.edit_reply_markup(reply_markup=style_kb(p))
    except Exception: pass
    await c.answer("Обновлено")

@router.message(Command("nick"))
async def nick_cmd(m: types.Message):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer("Пример: /nick котик  (работает, когда в /style выбран режим: fixed)")
    nick=parts[1].strip()
    if len(nick)>24: return await m.answer("Слишком длинное обращение.")
    cur.execute("UPDATE users SET petname=? WHERE user_id=?", (nick, m.from_user.id)); db.commit()
    await m.answer(f"Ок, буду использовать «{nick}», если выбран режим «fixed».")

# ---------- ПОГОДА / КОНВЕРТЕР КОМАНДЫ ----------
@router.message(Command("weather"))
async def weather_cmd(m: types.Message):
    pf=get_prefs(m.from_user.id)
    txt=f"{THEME['weather']} Погода сейчас:\n"+fetch_weather(pf["city"], pf["units"])+"\n"+fetch_weather(pf["partner_city"]+",CN", pf["units"])
    await m.answer(frame("Погода", txt))

@router.callback_query(F.data=="weather")
async def cb_weather(c: types.CallbackQuery):
    pf=get_prefs(c.from_user.id)
    txt=f"{THEME['weather']} Погода сейчас:\n"+fetch_weather(pf["city"], pf["units"])+"\n"+fetch_weather(pf["partner_city"]+",CN", pf["units"])
    await c.message.answer(frame("Погода", txt)); await c.answer()

@router.message(Command("when"))
async def when_cmd(m: types.Message):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer("Пример: /when 19:30 msk  |  /when 20:00 Asia/Shanghai")
    try:
        hh,mm,tz=parse_when(parts[1]); await m.answer(when_convert(hh,mm,tz))
    except Exception as e:
        await m.answer(f"{THEME['warn']} {e}")

@router.callback_query(F.data=="when")
async def cb_when(c: types.CallbackQuery):
    await c.message.answer("Напиши так: /when 19:30 msk — скажу время в Москве и Zibo"); await c.answer()

@router.callback_query(F.data=="settings")
async def cb_settings(c: types.CallbackQuery):
    p=get_prefs(c.from_user.id)
    body=f"Город: {p['city']} | Партнёр: {p['partner_city']} | ед.: {p['units']}\nАвто-флирт: {'on' if p['flirt_auto'] else 'off'} | Мат: {('off','soft','spicy')[p['profanity']]}"
    await c.message.answer(frame("Настройки", body)); await c.answer()

# ---------- РЕАКЦИИ ----------
def _pick_reaction(text:str):
    t=(text or "").lower()
    if any(w in t for w in ["спасибо","благодар","love","люблю","ты лучший","умница"]): return "💙"
    if any(w in t for w in ["ура","класс","супер","круто","молодец","готово"]): return "👍"
    if any(w in t for w in ["тяжело","плохо","устал","груст","печал","болит","стресс"]): return "🤗"
    if any(w in t for w in ["ахах","ха-ха","смешно","ржу","лул"]): return "😄"
    return None

async def _try_react(chat_id:int, message_id:int, emoji:str):
    try:
        try:
            from aiogram.types.reaction_type_emoji import ReactionTypeEmoji
        except Exception:
            from aiogram.types import ReactionTypeEmoji
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=[ReactionTypeEmoji(emoji=emoji)], is_big=False)
        return True
    except Exception:
        try: await bot.send_message(chat_id, emoji, reply_to_message_id=message_id)
        except Exception: pass
        return False

# ---------- РИТУАЛЫ ----------
async def _send_ritual(uid:int, kind:str):
    msg = f"{THEME['bullet']} Как спалось? Начнём день бережно. Маленькая цель на сегодня?" if kind=="morning" \
          else f"{THEME['bullet']} Выдыхай понемногу. Я рядом. Добрых снов."
    await bot.send_message(uid, frame("Доброе утро" if kind=="morning" else "Спокойной ночи", msg))

def _schedule_user(uid:int):
    global SCHED
    if SCHED is None: return
    p=get_prefs(uid); tz=get_user(uid)[1] or "Europe/Moscow"
    # утро
    try: SCHED.remove_job(f"rit_m_{uid}")
    except Exception: pass
    if int(p.get("ritual_morning",0)):
        h=int(p.get("r_morning_hour",9))
        SCHED.add_job(_send_ritual, CronTrigger(hour=h, minute=0, timezone=ZoneInfo(tz)),
                      args=[uid,"morning"], id=f"rit_m_{uid}", replace_existing=True)
    # ночь
    try: SCHED.remove_job(f"rit_n_{uid}")
    except Exception: pass
    if int(p.get("ritual_night",0)):
        h=int(p.get("r_night_hour",22))
        SCHED.add_job(_send_ritual, CronTrigger(hour=h, minute=0, timezone=ZoneInfo(tz)),
                      args=[uid,"night"], id=f"rit_n_{uid}", replace_existing=True)

def _schedule_all_users():
    cur.execute("SELECT user_id FROM users")
    for (uid,) in cur.fetchall(): _schedule_user(uid)

def ritual_kb(p:dict):
    rows=[
        [InlineKeyboardButton(text=f"Утро: {'on' if int(p.get('ritual_morning',0)) else 'off'}", callback_data="rit:mor"),
         InlineKeyboardButton(text=f"Час: {int(p.get('r_morning_hour',9)):02d}:00", callback_data="rit:mh")],
        [InlineKeyboardButton(text=f"Ночь: {'on' if int(p.get('ritual_night',0)) else 'off'}", callback_data="rit:nit"),
         InlineKeyboardButton(text=f"Час: {int(p.get('r_night_hour',22)):02d}:00", callback_data="rit:nh")],
        [InlineKeyboardButton(text="Таймзона /tz", callback_data="rit:tz")]
    ]; return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(Command("ritual"))
async def ritual_cmd(m: types.Message):
    p=get_prefs(m.from_user.id); body="Ежедневные сообщения. Меняй on/off и часы. Таймзону см. /tz"
    await m.answer(frame("Ритуалы", body), reply_markup=ritual_kb(p))

@router.callback_query(F.data.startswith("rit:"))
async def rit_cb(c: types.CallbackQuery):
    uid=c.from_user.id; act=c.data.split(":")[1]; p=get_prefs(uid)
    if act=="mor":
        val=0 if int(p.get("ritual_morning",0)) else 1; cur.execute("UPDATE prefs SET ritual_morning=? WHERE user_id=?", (val,uid))
    elif act=="nit":
        val=0 if int(p.get("ritual_night",0)) else 1; cur.execute("UPDATE prefs SET ritual_night=? WHERE user_id=?", (val,uid))
    elif act=="mh":
        h=(int(p.get("r_morning_hour",9))+1)%24; cur.execute("UPDATE prefs SET r_morning_hour=? WHERE user_id=?", (h,uid))
    elif act=="nh":
        h=(int(p.get("r_night_hour",22))+1)%24; cur.execute("UPDATE prefs SET r_night_hour=? WHERE user_id=?", (h,uid))
    elif act=="tz":
        await c.message.answer("Команда: /tz Europe/Moscow  |  Примеры: Europe/Moscow, Asia/Shanghai"); await c.answer(); return
    db.commit(); _schedule_user(uid); p=get_prefs(uid)
    try: await c.message.edit_reply_markup(reply_markup=ritual_kb(p))
    except Exception: pass
    await c.answer("Обновлено")

@router.message(Command("tz"))
async def tz_cmd(m: types.Message):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer("Пример: /tz Europe/Moscow  |  Asia/Shanghai")
    tz=parts[1].strip()
    try: _=ZoneInfo(tz)
    except Exception: return await m.answer("Не знаю такую таймзону. Пример: Europe/Moscow")
    cur.execute("UPDATE users SET tz=? WHERE user_id=?", (tz, m.from_user.id)); db.commit()
    _schedule_user(m.from_user.id); await m.answer(f"{THEME['ok']} Таймзона сохранена: {tz}")

# ---------- /WEEK — ДАЙДЖЕСТ (муд недели + Q&A) ----------
def _collect_week_data(uid:int):
    days=[(date.today()-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    cur.execute("SELECT day,rating,note FROM moods WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY day",(uid,days[0],days[-1]))
    moods_raw=cur.fetchall(); moods={d:(r,n) for d,r,n in moods_raw}
    cur.execute("SELECT role, content, ts FROM chatlog WHERE user_id=? ORDER BY id DESC LIMIT 80",(uid,))
    chat=list(reversed(cur.fetchall()))
    start_dt=(datetime.now()-timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("SELECT category,question,answer,ts FROM qanswers WHERE user_id=? AND ts>=? ORDER BY id",(uid,start_dt))
    qa=cur.fetchall(); return days, moods, chat, qa

@router.message(Command("week"))
async def week_cmd(m: types.Message):
    uid=m.from_user.id
    days, moods, chat, qa=_collect_week_data(uid)
    nums=[]; notes=[]
    for d in days:
        if d in moods:
            nums.append(moods[d][0])
            if moods[d][1]: notes.append(f"{d[-2:]}: {moods[d][1]}")
        else:
            nums.append(None)
    mood_line=" ".join([str(n) if isinstance(n,int) else "·" for n in nums])
    vals=[n for n in nums if isinstance(n,int)]
    avg=(sum(vals)/len(vals)) if vals else 0.0
    best=max(vals) if vals else None; worst=min(vals) if vals else None

    chat_lines=[]; 
    for r,c,ts in chat:
        c=(c or "").strip().replace("\\n"," ")
        if len(c)>220: c=c[:220]+"…"
        chat_lines.append(f"{r[:1].upper()}: {c}")
    chat_txt="\\n".join(chat_lines)

    qa_lines=[]
    for cat,q,a,ts in qa[-6:]:
        q=(q or "").strip().replace("\\n"," ")
        a=(a or "").strip().replace("\\n"," ")
        if len(q)>120: q=q[:120]+"…"
        if len(a)>160: a=a[:160]+"…"
        qa_lines.append(f"[{cat}] {q}\\n ↳ {a}")
    qa_txt="\\n".join(qa_lines)

    if USE_LLM and reply_as_girlfriend is not None:
        try:
            req=("Собери тёплый недельный дайджест: 1) 2–3 главные ноты недели, "
                 "2) что порадовало/поддержало, 3) где было напряжение, 4) 2 шага на следующую неделю. "
                 f"Шкала настроения: {mood_line}, среднее: {avg:.1f}/10; лучший: {best}; худший: {worst}. "
                 "Учитывай ответы на вопросы (если есть) и кратко сошлись на них.")
            pieces=[]; 
            if qa_txt: pieces.append("Ответы на вопросы:\\n"+qa_txt)
            if chat_txt: pieces.append("Фрагменты чата:\\n"+chat_txt)
            hist=[{"role":"user","content": req + "\\n\\n" + "\\n\\n".join(pieces)}]
            text=await ask_llm(hist, {"petname": get_user(uid)[2]})
            body=f"{THEME['bullet']} Настроение: {mood_line} (ср. {avg:.1f}/10; лучш: {best or '-'}; худш: {worst or '-'})"
            if notes: body+="\n"+THEME['bullet']+" Заметки: "+"; ".join(notes[:3])
            if qa: body+=f"\n{THEME['bullet']} Ответов на вопросы за неделю: {len(qa)}"
            body+="\n\n"+text
            return await m.answer(frame("Недельный дайджест", body))
        except Exception:
            pass

    body=f"{THEME['bullet']} Настроение: {mood_line}"
    if vals: body+=f" (ср. {avg:.1f}/10; лучш: {best or '-'}; худш: {worst or '-'})"
    if qa: body+=f"\n{THEME['bullet']} Ответов на вопросы за неделю: {len(qa)}"
    if notes: body+="\n"+THEME['bullet']+" Заметки: "+"; ".join(notes[:3])
    body+="\n\n(ИИ недоступен — базовая сводка)"
    await m.answer(frame("Недельный дайджест", body))

# ---------- СЛУЖЕБНЫЕ ----------
@router.message(Command("ping"))
async def ping_cmd(m: types.Message): await m.answer("pong")

@router.message(Command("errors"))
async def errors_cmd(m: types.Message):
    body=f"LLM import error:\n{LLM_IMPORT_ERROR or '-'}\n\nLast LLM error:\n{LAST_LLM_ERROR or '-'}\n\nLast runtime error:\n{LAST_RUNTIME_ERROR or '-'}"
    await m.answer(frame("Ошибки", body))

@router.message(Command("test_ai"))
async def test_ai(m: types.Message):
    try:
        if not USE_LLM or reply_as_girlfriend is None:
            return await m.answer("ИИ недоступен: проверь OPENAI_API_KEY / llm.py")
        txt=reply_as_girlfriend([{"role":"user","content":"Скажи «ок»"}], {})
        await m.answer(frame("Тест ИИ", f"Ответ: {txt}"))
    except Exception:
        global LAST_LLM_ERROR
        LAST_LLM_ERROR=traceback.format_exc()
        await m.answer("Тест провалился. Смотри /errors")

@router.message(Command("debug"))
async def debug_cmd(m: types.Message):
    info=[
        f"USE_LLM: {USE_LLM}",
        f"OPENAI_API_KEY set: {bool(OPENAI_KEY)}",
        f"OWM_API_KEY set: {bool(OWM_API_KEY)}",
        f"LLM import error: {LLM_IMPORT_ERROR or '-'}",
        f"Last LLM error: {LAST_LLM_ERROR or '-'}",
        f"Last runtime error: {LAST_RUNTIME_ERROR or '-'}",
    ]
    await m.answer("\n".join(info))

# ---------- ПОМОЩНИК ДЛЯ LLM ----------
async def ask_llm(hist, ctx, timeout: float | None = None, tries: int | None = None):
    global LAST_LLM_ERROR
    timeout = timeout or LLM_TIMEOUT
    tries = (tries if tries is not None else (LLM_RETRIES + 1))
    last_err = None
    for i in range(max(1, tries)):
        try:
            return await asyncio.wait_for(asyncio.to_thread(reply_as_girlfriend, hist, ctx), timeout=timeout)
        except asyncio.TimeoutError as e:
            last_err = e; LAST_LLM_ERROR = f"timeout after {timeout}s (try {i+1}/{tries})"
        except Exception as e:
            last_err = e; LAST_LLM_ERROR = f"{type(e).__name__}: {e}"; break
    raise last_err

# ---------- ДИАЛОГ (ИИ + ожидания) ----------
@router.message(F.text & ~F.text.startswith("/") & ~F.via_bot)
async def dialog(m: types.Message):
    global LAST_RUNTIME_ERROR
    try:
        uid=m.from_user.id; txt=(m.text or "").strip()

        # 1) заметка к настроению
        if uid in AWAIT_MOOD_NOTE:
            day=date.today().isoformat()
            cur.execute("UPDATE moods SET note=? WHERE user_id=? AND day=?", (txt, uid, day)); db.commit()
            AWAIT_MOOD_NOTE.discard(uid)
            await m.answer(f"{THEME['ok']} Заметку сохранила."); return

        # 2) ответ на вопрос дня
        if uid in Q_WAIT:
            pack=Q_WAIT.pop(uid)
            cur.execute("INSERT INTO qanswers(user_id, category, question, answer) VALUES(?,?,?,?)",
                        (uid, pack.get('cat','light'), pack.get('q',''), txt)); db.commit()
            await m.answer(f"{THEME['ok']} Ответ сохранила. Хочешь ещё — /q или кнопка «Ещё вопрос»."); return

        # 3) обычный диалог — ИИ
        add_chat(uid,"user",txt)
        if not USE_LLM or reply_as_girlfriend is None:
            return await m.answer("ИИ недоступен: проверь OPENAI_API_KEY / llm.py (см. /errors)")

        await typing(m,0.4)
        pf=get_prefs(uid)
        ctx={
            "petname": pick_petname(uid, pf["style_mode"], get_user(uid)[2]),
            "msk": datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m %H:%M"),
            "sha": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%d.%m %H:%M"),
            "days_left": (TARGET_DATE - date.today()).days,
            "target": TARGET_DATE.strftime("%d.%m.%Y"),
            "flirt": bool(pf.get("flirt_auto",1)),
            "profanity": ('off','soft','spicy')[min(max(int(pf.get('profanity',0)),0),2)]
        }
        hist=[{"role":"user","content":txt}]
        answer=await ask_llm(hist, ctx)
        answer=(answer or "").strip() or "Не смогла сформулировать ответ — попробуем иначе?"
        add_chat(uid,"assistant",answer); await m.answer(answer)

        # 4) иногда добавим реакцию
        try:
            if random.random()<0.2:
                emo=_pick_reaction(txt)
                if emo: await _try_react(m.chat.id, m.message_id, emo)
        except Exception: pass

    except Exception:
        LAST_RUNTIME_ERROR=traceback.format_exc()
        try: await m.answer("Проблема на моей стороне. Посмотри /errors и напиши ещё раз.")
        except Exception: pass

# ---------- СТАРТ / МЕНЮ ----------
@router.message(Command("start"))
async def start_cmd(m: types.Message):
    uid=m.from_user.id; get_user(uid); ensure_prefs(uid)
    hint=f"{THEME['bullet']} Дайджест: /week  •  Ритуалы: /ritual  •  Стиль: /style"
    await m.answer(today_panel()+"\n"+hint, reply_markup=menu_kb())

@router.message(Command("menu"))
async def menu_cmd(m: types.Message):
    hint=f"{THEME['bullet']} Дайджест: /week  •  Ритуалы: /ritual  •  Стиль: /style"
    await m.answer(today_panel()+"\n"+hint, reply_markup=menu_kb())

# ---------- ТОЧКА ВХОДА ----------
async def _set_commands():
    cmds=[
        BotCommand(command="start", description="Старт/меню"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="mood", description="Оценить настроение"),
        BotCommand(command="moodweek", description="График за 7 дней"),
        BotCommand(command="q", description="Вопросы для близости"),
        BotCommand(command="q_history", description="Мои ответы на вопросы"),
        BotCommand(command="when", description="Конвертер времени"),
        BotCommand(command="weather", description="Погода в двух городах"),
        BotCommand(command="style", description="Стиль: мат/флирт/обращения"),
        BotCommand(command="nick", description="Задать обращение"),
        BotCommand(command="ritual", description="Ритуалы: утро/ночь"),
        BotCommand(command="tz", description="Таймзона"),
        BotCommand(command="week", description="Недельный дайджест"),
        BotCommand(command="test_ai", description="Проверка ИИ"),
        BotCommand(command="errors", description="Последние ошибки"),
        BotCommand(command="debug", description="Диагностика"),
        BotCommand(command="ping", description="Пинг"),
    ]
    try: await bot.set_my_commands(cmds)
    except Exception: pass

async def main():
    global SCHED
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        SCHED=AsyncIOScheduler(); SCHED.start(); _schedule_all_users()
    except Exception:
        SCHED=None
    await _set_commands()
    try:
        await router.start_polling(bot)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        try: await bot.session.close()
        except Exception: pass

if __name__=="__main__":
    import asyncio
'''

Path("lovebot").mkdir(exist_ok=True)
Path("lovebot/main.py").write_text(MAIN_CODE, encoding="utf-8")
print("✅ main.py записан — готово к запуску")


# ПАТЧ: реакции — поддержка старых aiogram, настройка процента и кнопка теста
from pathlib import Path, re

p = Path("lovebot/main.py")
s = p.read_text(encoding="utf-8")

# 0) Добавим колонку prefs.reactions_pct (если отсутствует)
if "reactions_pct" not in s:
    s = s.replace(
        'cur.execute("CREATE TABLE IF NOT EXISTS qanswers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, category TEXT, question TEXT, answer TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")\n'
        "db.commit()",
        'cur.execute("CREATE TABLE IF NOT EXISTS qanswers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, category TEXT, question TEXT, answer TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")\n'
        "db.commit()\n"
        "try:\n"
        "    cur.execute(\"ALTER TABLE prefs ADD COLUMN reactions_pct INTEGER DEFAULT 20\")\n"
        "except Exception:\n"
        "    pass\n"
        "db.commit()",
        1
    )

# 1) Хелпер для чтения процента реакций (не трогаем существующий get_prefs)
if "def get_react_pct(" not in s:
    anchor = re.search(r"def get_prefs\(uid: int\) -> dict:[\s\S]*?return \{[\s\S]*?\}\n", s)
    ins = anchor.end() if anchor else 0
    s = s[:ins] + r'''

def get_react_pct(uid: int) -> int:
    """Читаем prefs.reactions_pct; если нет колонки — 20% по умолчанию."""
    try:
        cur.execute("SELECT reactions_pct FROM prefs WHERE user_id=?", (uid,))
        row = cur.fetchone()
        return max(0, min(100, int(row[0] if row and row[0] is not None else 20)))
    except Exception:
        return 20
''' + s[ins:]

# 2) Обновим хелперы реакций: проверка поддержки и надёжный фоллбэк
if "def _react_supported(" not in s:
    s = s.replace(
        "async def _try_react(chat_id:int, message_id:int, emoji:str):",
        "def _react_supported() -> bool:\n"
        "    return hasattr(bot, 'set_message_reaction')\n\n"
        "async def _try_react(chat_id:int, message_id:int, emoji:str):"
    )

s = re.sub(
    r"async def _try_react\(chat_id:int, message_id:int, emoji:str\):[\s\S]*?return False",
    r"""async def _try_react(chat_id:int, message_id:int, emoji:str):
    # Если метод реакций недоступен в этой версии aiogram/Bot API — делаем ответ-эмодзи
    if not _react_supported():
        try:
            await bot.send_message(chat_id, emoji, reply_to_message_id=message_id)
        except Exception:
            pass
        return False
    try:
        try:
            from aiogram.types.reaction_type_emoji import ReactionTypeEmoji
        except Exception:
            from aiogram.types import ReactionTypeEmoji
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id,
                                       reaction=[ReactionTypeEmoji(emoji=emoji)], is_big=False)
        return True
    except Exception:
        # Фоллбэк — просто ответить эмодзи
        try:
            await bot.send_message(chat_id, emoji, reply_to_message_id=message_id)
        except Exception:
            pass
        return False""",
    s, count=1
)

# 3) /react — настройка процента и /react_test — принудительная проверка
if '@router.message(Command("react"))' not in s:
    block = r'''
@router.message(Command("react"))
async def react_cmd(m: types.Message):
    """
    /react           -> показать текущую вероятность
    /react 50        -> 50%
    /react off|0     -> выключить
    """
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        pct = get_react_pct(m.from_user.id)
        return await m.answer(f"Реакции: {pct}% (изменить: /react 0..100 или /react off)")
    arg = parts[1].strip().lower()
    if arg in ("off", "0"):
        pct = 0
    else:
        try:
            pct = int(arg)
        except Exception:
            return await m.answer("Нужно число 0..100 или 'off'. Пример: /react 35")
        pct = max(0, min(100, pct))
    # гарантируем наличие колонки
    try:
        cur.execute("ALTER TABLE prefs ADD COLUMN reactions_pct INTEGER DEFAULT 20")
    except Exception:
        pass
    cur.execute("UPDATE prefs SET reactions_pct=? WHERE user_id=?", (pct, m.from_user.id))
    db.commit()
    await m.answer(f"{THEME['ok']} Реакции теперь: {pct}%")

@router.message(Command("react_test"))
async def react_test_cmd(m: types.Message):
    """Принудительно проставить реакцию на ТВОЁ сообщение."""
    emo = _pick_reaction(m.text or "") or "💙"
    ok = await _try_react(m.chat.id, m.message_id, emo)
    await m.answer(("Поставила нативную реакцию." if ok else "Отправила эмодзи-ответ."))'''
    # вставим перед служебными командами
    anchor = re.search(r"\n# ---------- СЛУЖЕБНЫЕ", s) or re.search(r"\n# ---------- Служебные", s)
    pos = anchor.start() if anchor else len(s)
    s = s[:pos] + "\n" + block + "\n" + s[pos:]

# 4) В диалоге используем процент из prefs
s = re.sub(
    r"# 4\) иногда добавим реакцию[\s\S]*?except Exception: pass",
    r"""# 4) иногда добавим реакцию — по твоему проценту
        try:
            pct = get_react_pct(uid)
            if pct > 0:
                import random
                if random.randint(1,100) <= pct:
                    emo = _pick_reaction(txt)
                    if emo:
                        await _try_react(m.chat.id, m.message_id, emo)
        except Exception:
            pass""",
    s, count=1
)

# 5) Добавим команды в меню
s = s.replace(
    'BotCommand(command="debug", description="Диагностика"),',
    'BotCommand(command="debug", description="Диагностика"),\n'
    '        BotCommand(command="react", description="Вероятность реакций 0–100"),\n'
    '        BotCommand(command="react_test", description="Проверка реакции"),'
)

Path("lovebot/main.py").write_text(s, encoding="utf-8")
print("✅ Реакции: добавлены /react и /react_test, фоллбэк и процент в prefs")


# Ячейка 5 — requirements.txt и .gitignore
from pathlib import Path

Path("requirements.txt").write_text("""aiogram==3.11.0
python-dotenv==1.0.1
APScheduler==3.10.4
requests==2.32.3
openai==1.46.0
aiohttp==3.9.5
""", encoding="utf-8")

Path(".gitignore").write_text(".env\ndb.sqlite3\n__pycache__/\n*.pyc\n*.log\n.env.*\n", encoding="utf-8")

print("✅ requirements.txt и .gitignore готовы")


# Ячейка 6 — server.py (aiohttp webhook)
server_code = r'''
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from lovebot import main as lm

bot = lm.bot
dp  = lm.dp

WEBHOOK_PATH  = "/tg"
PUBLIC_URL    = os.getenv("PUBLIC_URL", "")
WEBHOOK_SECRET= os.getenv("WEBHOOK_SECRET", "space-secret")
PORT          = int(os.getenv("PORT", "8080"))

async def on_startup(app: web.Application):
    await lm._set_commands()
    await bot.delete_webhook(drop_pending_updates=True)
    if PUBLIC_URL:
        await bot.set_webhook(url=PUBLIC_URL + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET)
    else:
        print("⚠️ PUBLIC_URL не задан — добавь его в переменные окружения.")

async def on_shutdown(app: web.Application):
    try:
        await bot.delete_webhook()
    except Exception:
        pass

async def health(_):
    return web.Response(text="ok")

app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

SimpleRequestHandler(dp, bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

app.router.add_get("/", health)

    # removed run_app
'''
Path("server.py").write_text(server_code, encoding="utf-8")
print("✅ server.py создан")


# # 7) Запуск бота (ячейка "висит" — это нормально; для остановки: квадрат Stop)
# import nest_asyncio, sys, os
# nest_asyncio.apply()

# sys.modules.pop("main", None)  # сбрасываем старый модуль, если был
# sys.path.insert(0, os.path.abspath("lovebot"))

# import main as love_main
# await love_main.main()


from pathlib import Path
import re

# 1) server.py — aiohttp-вебсервер для Telegram webhook (использует твой lovebot/main.py)
Path("server.py").write_text(r'''
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from lovebot import main as lm  # импортируем bot/dp

bot = lm.bot
dp  = lm.dp

WEBHOOK_PATH   = "/tg"
PUBLIC_URL     = os.getenv("PUBLIC_URL", "")               # позже задашь в Koyeb
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "koyeb-secret")
PORT           = int(os.getenv("PORT", "8080"))

async def on_startup(app: web.Application):
    # Почистим команды (чтобы в меню ТГ не торчали названия)
    try:
        await lm._set_commands()
    except Exception:
        pass
    await bot.delete_webhook(drop_pending_updates=True)
    if PUBLIC_URL:
        await bot.set_webhook(url=PUBLIC_URL + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET)
    else:
        print("⚠️ PUBLIC_URL не задан — добавь его в переменные окружения Koyeb и перезапусти сервис.")

async def on_shutdown(app: web.Application):
    try:
        await bot.delete_webhook()
    except Exception:
        pass

async def health(_):
    return web.Response(text="ok")

app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

SimpleRequestHandler(dp, bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)
app.router.add_get("/", health)

    # removed run_app
''', encoding="utf-8")

# 2) requirements.txt — пакеты
Path("requirements.txt").write_text("""aiogram==3.11.0
aiohttp==3.9.5
python-dotenv==1.0.1
APScheduler==3.10.4
requests==2.32.3
openai==1.46.0
tzdata==2024.1
""", encoding="utf-8")

# 3) .gitignore — чтобы мусор/секреты не попадали в репо
Path(".gitignore").write_text(".env\ndb.sqlite3\n__pycache__/\n*.pyc\n*.log\n.env.*\n", encoding="utf-8")

print("✅ server.py, requirements.txt, .gitignore готовы")


# Ячейка — патч lovebot/main.py под Koyeb: DB_PATH, __main__-guard и /backup
from pathlib import Path
import re, json

p = Path("lovebot/main.py")
assert p.exists(), "Не нашла lovebot/main.py — он должен быть у тебя уже создан."

s = p.read_text(encoding="utf-8")

# 1) DB_PATH вместо захардкоженного 'db.sqlite3'
if 'sqlite3.connect(os.getenv("DB_PATH"' not in s:
    # если нет import os — добавим
    if re.search(r'^\s*import os\b', s, flags=re.M) is None:
        s = s.replace("# -*- coding: utf-8 -*-", "# -*- coding: utf-8 -*-\nimport os")
    s = re.sub(
        r'sqlite3\.connect\(\s*[\'"]db\.sqlite3[\'"]\s*\)',
        'sqlite3.connect(os.getenv("DB_PATH", "db.sqlite3"))',
        s, count=1
    )

# 2) Guard, чтобы поллинг не стартовал при импорте (webhook-режим)
    s += r'''

    import asyncio
'''

# 3) /backup — экспорт данных пользователя в JSON (прикрепляется файлом)
if '@router.message(Command("backup"))' not in s:
    s += r'''

from aiogram.filters import Command
from aiogram import types
import io, json, sqlite3, os

@router.message(Command("backup"))
async def backup_cmd(m: types.Message):
    """Экспорт таблиц prefs/moods/chatlog/qanswers текущего пользователя."""
    uid = m.from_user.id
    try:
        db = sqlite3.connect(os.getenv("DB_PATH","db.sqlite3"))
        db.row_factory = sqlite3.Row
        cur = db.cursor()
        dump = {}
        for tbl in ("prefs","moods","chatlog","qanswers"):
            try:
                cur.execute(f"SELECT * FROM {tbl} WHERE user_id=?", (uid,))
                rows = [dict(r) for r in cur.fetchall()]
                dump[tbl] = rows
            except Exception:
                dump[tbl] = []
        db.close()

        # готовим буфер
        buf = io.BytesIO(json.dumps(dump, ensure_ascii=False, indent=2).encode("utf-8"))
        from aiogram.types import BufferedInputFile
        await m.answer_document(
            BufferedInputFile(buf.getvalue(), filename="backup.json"),
            caption="Резервная копия 📦"
        )
    except Exception as e:
        await m.answer(f"Не смогла сделать бэкап: {e}")
'''

p.write_text(s, encoding="utf-8")
print("✅ Готово: импорт исправлен, DB_PATH патчен, guard добавлен, /backup работает.")


from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")
SECRET_PATH = os.environ.get("WEBHOOK_SECRET_PATH", "telegram")
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

if not TOKEN:
    raise RuntimeError("No TELEGRAM_BOT_TOKEN provided")
# bot = Bot(...)  # replaced by main app bot
# dp = Dispatcher(...)  # replaced by main app dp
# --- тут оставляешь свои хендлеры как есть ---

async def on_startup(app: web.Application):
    if WEBHOOK_BASE:
        await bot.set_webhook(f"{WEBHOOK_BASE}/{SECRET_PATH}", drop_pending_updates=True)

async def on_cleanup(app: web.Application):
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
