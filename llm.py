
"""
Опциональный модуль для ответов ИИ с поддержкой персонального "характера".
Если OPENAI_API_KEY не задан, функции не используются.
Сделано минимально, чтобы не увеличивать потребление памяти.
"""
import os
from functools import lru_cache
from openai import OpenAI

MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_KEY = os.getenv("OPENAI_API_KEY")
BASE    = os.getenv("OPENAI_BASE_URL")
TEMP    = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
MAXTOK  = int(os.getenv("OPENAI_MAX_TOKENS", "220"))

@lru_cache(maxsize=1)
def _load_persona() -> str:
    # 1) ENV wins
    p = os.getenv("PERSONA_PROMPT")
    if p and p.strip():
        return p.strip()
    # 2) persona.txt near app
    for path in ("./persona.txt", "/mnt/data/persona.txt"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    # 3) Fallback: empty (персона не меняется наружу)
    return ""

_client = None
def client():
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("OPENAI_API_KEY is empty")
        _client = OpenAI(api_key=API_KEY, base_url=BASE) if BASE else OpenAI(api_key=API_KEY)
    return _client

def short_reply(prompt: str) -> str:
    persona = _load_persona()
    messages = []
    if persona:
        messages.append({"role": "system", "content": persona})
    messages.append({"role": "user", "content": prompt})
    c = client()
    r = c.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMP,
        max_tokens=MAXTOK
    )
    return (r.choices[0].message.content or "").strip()
