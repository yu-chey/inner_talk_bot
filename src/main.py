import asyncio
import sys
import logging
import motor.motor_asyncio
from src import config
from src.handlers import router as handler_router
from src.callbacks import router as callback_router

from google import genai
from google.genai import types

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

gemini_client = None
mongo_client = None
db = None
users_collection = None


def generate_content_sync(client, model_name, contents, system_instruction=None):
    """Синхронно вызывает Gemini API в отдельном потоке с системным промптом."""
    config_params = {}
    if system_instruction:
        config_params['system_instruction'] = system_instruction

    config_obj = types.GenerateContentConfig(**config_params) if config_params else None

    return client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config_obj
    )


def count_tokens_sync(client, model_name, contents):
    return client.models.count_tokens(
        model=model_name,
        contents=contents
    )

async def main():
    global gemini_client, mongo_client, db, users_collection

    gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI)
    db = mongo_client[config.DB_NAME]
    users_collection = db[config.USERS_COLLECTION]

    dp = Dispatcher()

    dp.include_routers(handler_router, callback_router)

    bot = Bot(token=config.TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=None))

    logger.info("Приложение успешно запущено.")

    dp.workflow_data.update({
        "gemini_client": gemini_client,
        "generate_content_sync_func": generate_content_sync,
        "count_tokens_sync_func": count_tokens_sync,
        "users_collection": users_collection,
        "config": config,
        "bot": bot,
    })

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        mongo_client.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске бота: {e}")