# NYAMKA Bot for Koyeb

## Features
- Telegram bot on aiogram v3 + aiohttp
- Webhook ready for Koyeb
- Healthcheck at `/`
- Menu with "📈 Курс валют" → shows RUB→USD, RUB→CNY rates from Central Bank of Russia

## Files
- app.py — main application
- requirements.txt — dependencies
- Dockerfile — build instructions
- .env.example — env vars template

## How to Deploy
1. Push these files to your GitHub repo.
2. Create service on Koyeb with Builder type = Dockerfile, path = `Dockerfile`.
3. Set Environment variables:
   - BOT_TOKEN
   - OPENAI_API_KEY (optional)
   - OWM_API_KEY (optional)
   - DETA_PROJECT_KEY (optional)
   - WEBHOOK_BASE = your public URL from Koyeb
   - WEBHOOK_SECRET_PATH = any secret string
4. Deploy 🚀

## Local run
```bash
pip install -r requirements.txt
export $(cat .env | xargs)
python app.py
```
