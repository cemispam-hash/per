"""Настройки бота, читаются из .env."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

MSK = ZoneInfo("Europe/Moscow")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "diyordestorebot").lstrip("@")

DB_PATH = os.getenv("DB_PATH") or str(BASE_DIR / "bot.sqlite3")
if not os.path.isabs(DB_PATH):
    DB_PATH = str(BASE_DIR / DB_PATH)

ADMIN_IDS = {
    int(chunk)
    for chunk in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",")
    if chunk.isdigit()
}

ORDER_TTL_MINUTES = int(os.getenv("ORDER_TTL_MINUTES", "15"))

SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/diyordestore_support")
NEWS_URL = os.getenv("NEWS_URL", "https://t.me/diyordestore")
MANUAL_URL = os.getenv("MANUAL_URL", "https://t.me/diyordestore")

PAYPALYCH_TOKEN = os.getenv("PAYPALYCH_TOKEN", "")
PAYPALYCH_SHOP_ID = os.getenv("PAYPALYCH_SHOP_ID", "")
PAYPALYCH_API = os.getenv("PAYPALYCH_API", "https://paypalych.com/api/v1")

MAX_QTY = 999


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
