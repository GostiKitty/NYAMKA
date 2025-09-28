# Telegram LoveBot (Koyeb-ready)

Minimal, memory-friendly version that preserves the notebook behaviour:
- /start, /menu
- /mood (numeric 1..10 + note), weekly digest /week
- /q and /q_history (light/deep)
- /when (time converter Moscow ↔ Shanghai/Zibo)
- /weather (two cities, via OWM_API_KEY)
- health-check on `/` for Koyeb

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill BOT_TOKEN and optional keys
python app.py
```

## Deploy on Koyeb
- Builder: Dockerfile
- Port: 8080 (auto-detected)
- Mount: none
- Add env vars: BOT_TOKEN (required), OWM_API_KEY (optional), OPENAI_* (optional)


## Webhook mode (recommended on Koyeb free)
Set env vars:
- USE_WEBHOOK=1
- PUBLIC_URL=https://<your-app>.koyeb.app
- TG_SECRET=<any random string>

Telegram will call `https://<PUBLIC_URL>/tg/<TG_SECRET>`.
