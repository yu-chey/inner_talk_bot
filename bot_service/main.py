import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from google import genai
import motor.motor_asyncio

from . import config
from . import db_manager
from . import handlers

bot = Bot(token=config.TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(handlers.dp)

gemini_client = None

def generate_content_sync(client, model_name, contents):
    """Синхронно вызывает Gemini API в отдельном потоке."""
    return client.models.generate_content(
        model=model_name,
        contents=contents
    )


async def main():
    global gemini_client

    gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

    try:
        motor_client = motor.motor_asyncio.AsyncIOMotorClient(
            config.MONGODB_URI
        )

        db_manager.db = motor_client.get_database(config.DB_NAME)

        logging.info("Успешно подключен к MongoDB Atlas.")
    except Exception as e:
        logging.critical(f"Ошибка подключения к MongoDB: {e}")
        exit(1)

    dp.workflow_data.update({
        "gemini_client": gemini_client,
        "generate_content_sync_func": generate_content_sync,
    })

    logging.info("INNER_TALK_BOT запущен и готов к работе.")
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске бота: {e}")