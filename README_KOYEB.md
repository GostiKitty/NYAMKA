# Koyeb Scaffold for Telegram Bot (aiogram + aiohttp)

## What this fixes
Your Koyeb build failed because there was no `Dockerfile`. This scaffold adds:
- `Dockerfile` for Koyeb to build the container
- `app.py` webhook server (listens on `$PORT`) with healthcheck `/`
- `requirements.txt`
- optional `Procfile` (Koyeb prefers Dockerfile; this is just a fallback)
- `.env.example`

## How to use in your Jupyter-only workflow
1) Open `app.py` and paste your handlers where indicated (keep `create_app()`).
2) If your current bot is only in a notebook, you can copy functions/handlers into `app.py`.
3) Update `requirements.txt` with any extra libraries you use.
4) Commit these files to your repo and push. Koyeb will now find the Dockerfile and build.
5) On Koyeb, set env vars:
   - `TELEGRAM_BOT_TOKEN`: your bot token
   - `WEBHOOK_BASE`: your public app URL (e.g., `https://<app>.koyeb.app`)
   - `WEBHOOK_SECRET_PATH`: random path that matches `app.py` (default `telegram`)
6) Deploy. On startup, the app sets the webhook to `WEBHOOK_BASE/WEBHOOK_SECRET_PATH`.

### Testing locally
```bash
pip install -r requirements.txt
export $(cat .env | xargs)  # if you've created .env
python app.py  # starts aiohttp on http://127.0.0.1:8080/
```

## Notes
- If you previously used long polling, Koyeb prefers a web process. This server uses webhooks.
- Keep logs clean; use `loguru` already wired.
- If you need `/setwebhook` manually, you can call `await bot.set_webhook(...)` similarly.
