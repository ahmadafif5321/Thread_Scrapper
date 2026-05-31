from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0")
HTTP_TIMEOUT_SECONDS = _float_env("HTTP_TIMEOUT_SECONDS", 25)
REQUEST_DELAY_SECONDS = _float_env("REQUEST_DELAY_SECONDS", 2)
FETCH_TIMEOUT_SECONDS = _float_env("FETCH_TIMEOUT_SECONDS", 90)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DB_PATH = os.getenv("DB_PATH", "data/threads_intel.sqlite3")
