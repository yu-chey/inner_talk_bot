import motor.motor_asyncio
import logging

from server import config

logger = logging.getLogger(__name__)

mongo_client = None
db = None
users_data_collection = None


def init_db_for_stats():
    global mongo_client, db, users_data_collection
    try:
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI)
        db = mongo_client[config.DB_NAME]
        users_data_collection = db[config.USERS_COLLECTION]
        logger.info("Успешное подключение к MongoDB для API статистики.")
    except Exception as e:
        logger.critical(f"Критическая ошибка подключения MongoDB для API: {e}")

async def get_total_stats():
    if users_data_collection is None:
        return {"error": "Database not initialized"}, 500

    try:
        collection = users_data_collection

        unique_username_count = await collection.distinct("username")

        return {
            "unique_username_count": len(unique_username_count),
        }, 200
    except Exception as e:
        logger.error(f"Ошибка при получении общей статистики: {e}")
        return {"error": str(e)}, 500


async def get_user_stats(username: str):
    if users_data_collection is None:
        logger.error("База данных не инициализирована: users_data_collection is None")
        return {"error": "Database not initialized"}, 500

    try:
        collection = users_data_collection
        clean_username = username.strip()

        user_text_messages = await collection.count_documents({
            "username": clean_username,
            "type": "user_message"
        })

        return {
            "username": clean_username,
            "total_user_texts": user_text_messages,
        }, 200

    except Exception as e:
        logger.error(f"Ошибка при получении статистики пользователя {username}: {e}")
        return {"error": f"An internal error occurred: {str(e)}"}, 500


async def get_all_users():
    if users_data_collection is None:
        return {"error": "Database not initialized"}, 500

    try:
        unique_usernames = await users_data_collection.distinct("username")

        return {
            "users": unique_usernames,
            "count": len(unique_usernames)
        }, 200

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        return {"error": str(e)}, 500