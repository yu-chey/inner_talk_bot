import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from google import genai

# TODO: optimize code

TOKEN = "8043619786:AAER8lyoOfhixIUbzO-pyPbYNPIfMRc46EI"
GEMINI_API_KEY = "AIzaSyAEn-QWnwLSF78K_DogH1cbk65EfzCqItc"

client = None

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(msg: Message):
    await msg.answer("# Привет! Я твой ИИ-психолог. Расскажи, что тебя беспокоит 😊")

@dp.message()
async def echo_handler(msg: Message):
    user_text = msg.text

    prompt = f"""
        Ты — эмпатичный, профессиональный и поддерживающий ИИ-психолог.

        Твоя задача — внимательно проанализировать проблему пользователя и предоставить поддерживающий, ободряющий, но в то же время конструктивный ответ.

        ### ОГРАНИЧЕНИЯ ФОРМАТИРОВАНИЯ:
        1.  НЕ ИСПОЛЬЗУЙ никакой разметки Markdown (звездочки *, нижние подчеркивания _, решетки #, и т.д.) и HTML.
        2.  Ответ должен быть ТОЛЬКО чистым, простым текстом без специальных символов форматирования.
        3.  Ответ должен быть лаконичным, но исчерпывающим, не превышая 5-7 предложений.
        4.  Используй эмодзи только для добавления теплоты и эмоциональной поддержки (например, 😊, 🙏, ✨).

        ### СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:
        {user_text}
        """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        ai_response = response.text
        await msg.answer(ai_response)

    except Exception as e:
        print(f"Gemini API Error: {e}")
        await msg.answer("Прости, у меня возникла техническая проблема. Попробуй позже.")


async def main():
    global client

    client = genai.Client(api_key=GEMINI_API_KEY)

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())