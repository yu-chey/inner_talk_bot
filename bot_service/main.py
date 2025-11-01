import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
import logging
import os
from dotenv import load_dotenv

from google import genai

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- КОНФИГУРАЦИЯ ---
load_dotenv() # Загружаем переменные окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # Секретные ключи из .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
SYSTEM_PROMPT_TEMPLATE = os.getenv("SYSTEM_PROMPT_TEMPLATE")

client = None


if not all([TOKEN, GEMINI_API_KEY]):
    logging.critical("ОШИБКА: Не удалось загрузить TELEGRAM_BOT_TOKEN или GEMINI_API_KEY из окружения/файла .env.")
    exit(1)


bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def generate_content_sync(client, model_name, contents):
    """Синхронно вызывает Gemini API."""
    return client.models.generate_content(
        model=model_name, 
        contents=contents
    )


@dp.message(Command("start"))
async def start_handler(msg: Message):
    await msg.answer("# Привет! Я твой ИИ-психолог. Расскажи, что тебя беспокоит 😊")

@dp.message()
async def echo_handler(msg: Message):
    user_text = msg.text
    prompt = SYSTEM_PROMPT_TEMPLATE.format(user_text=user_text)

    try:
        response = await asyncio.to_thread(
            generate_content_sync,
            client,
            "gemini-2.5-flash",
            prompt
        )
        ai_response = response.text
        await msg.answer(ai_response)

    except Exception as e:
        logging.error(f"Gemini API Error for user {msg.from_user.id}: {e}")
        await msg.answer("Прости, у меня возникла техническая проблема. Попробуй позже.")


async def main():
    global client
    
    # Инициализация клиента Gemini
    client = genai.Client(api_key=GEMINI_API_KEY)

    logging.info("INNER_TALK_BOT запущен и готов к работе.")
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске бота: {e}")