from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["innertalk_db"]  # имя базы
users_collection = db["users"]