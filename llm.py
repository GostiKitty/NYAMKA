
"""
Опциональный модуль для ответов ИИ. Если OPENAI_API_KEY не задан, функции не используются.
Сделано минимально, чтобы не увеличивать потребление памяти.
"""
import os
from openai import OpenAI

MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_KEY = os.getenv("OPENAI_API_KEY")
BASE    = os.getenv("OPENAI_BASE_URL")

_client = None
def client():
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("OPENAI_API_KEY is empty")
        _client = OpenAI(api_key=API_KEY, base_url=BASE) if BASE else OpenAI(api_key=API_KEY)
    return _client

def short_reply(prompt: str) -> str:
    c = client()
    r = c.chat.completions.create(model=MODEL, messages=[{"role":"user","content":prompt}], max_tokens=64)
    return r.choices[0].message.content.strip()
