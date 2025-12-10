from dotenv import load_dotenv
import os

def load_env():
    load_dotenv(override=True)

load_env()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME")

USERS_COLLECTION = os.getenv("USERS_COLLECTION", "users_data")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT") or os.getenv("API_PORT", 8000))