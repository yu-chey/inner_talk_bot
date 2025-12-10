import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

API_TOKEN = os.getenv("TELEGRAM_API_TOKEN", "8533182077:AAE_9xUNRI7AZTQJ2ztuMRFcb3D-Zsnw19Q")
BASE_API_URL = " http://0.0.0.0:8000"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def fetch_user_stats(username: str) -> dict:
    url = f"{BASE_API_URL}/stats/{username}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                logging.warning(f"API returned 404 for user {username}")
                return {"error": "Пользователь не найден или проблема с API."}
            else:
                error_data = await response.json()
                logging.error(f"API request failed with status {response.status}: {error_data}")
                return {"error": f"Ошибка сервера: {response.status}. {error_data.get('error', '')}"}


@dp.message(Command("stats"))
async def handle_stats_command(message: types.Message):
    args = message.text.split()

    if len(args) < 2:
        await message.reply("Пожалуйста, укажите имя пользователя.\nПример: `/stats username`")
        return

    username = args[1]

    await message.answer(f"Запрашиваю статистику для пользователя {username}...")

    stats_data = await fetch_user_stats(username)

    if "error" in stats_data:
        await message.answer(f"❌ **Ошибка при получении статистики:**\n{stats_data['error']}", parse_mode="Markdown")
        return
    try:
        response_text = f"📈 Статистика для {stats_data['username']}. Сообщения (user_text): {stats_data['total_user_texts']}"

        await message.answer(response_text, parse_mode="Markdown")

    except KeyError as e:
        logging.error(f"Неверная структура данных от API: Missing key {e}")
        await message.answer("❌ Ошибка: Получен неверный формат данных от сервера.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")