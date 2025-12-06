import os
import logging
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REVISOR_API_KEY = os.getenv("REVISOR_API_KEY")
SYSTEM_PROMPT_TEXT = os.getenv("SYSTEM_PROMPT_TEMPLATE")
ANALYZE_PROMPT_TEXT = os.getenv("ANALYZE_PROMPT")
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME")

BAN_COLLECTION = "banned_users"
HISTORY_LIMIT = 20
CHAT_COLLECTION = "chats"

if not all([TOKEN, GEMINI_API_KEY, SYSTEM_PROMPT_TEXT, MONGODB_URI, DB_NAME, REVISOR_API_KEY, ANALYZE_PROMPT_TEXT]):
    logging.critical("ОШИБКА: Не удалось загрузить все необходимые ключи. Проверьте файл .env.")
    exit(1)
