from dotenv import load_dotenv
import os

load_dotenv()  # загружает переменные из .env

MONGO_URI = os.getenv("MONGO_URI")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")