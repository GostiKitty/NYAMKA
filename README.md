# NYAMKA — Memory-optimized Koyeb package

- Single-file `app.py` with your notebook handlers (long polling)
- Minimal logging to reduce memory (set `LOG_LEVEL` env if needed)
- Slim Docker image, pip cache disabled
- Healthcheck at `/`

## Deploy
1) Put files in repo root.
2) Koyeb: Builder = Dockerfile, path = `Dockerfile`.
3) Set env: BOT_TOKEN (required), LOG_LEVEL (optional). Others only if handlers use them.
4) Redeploy. If only `app.py` changed → Skip build; if `requirements.txt` changed → Trigger build.

## Memory tips
- Keep `requirements.txt` short.
- Heavy libs (openai, deta) are optional — remove if not used.
- Avoid storing large data in globals; load on demand.
- Logging kept at WARNING by default; increase only for debugging.
