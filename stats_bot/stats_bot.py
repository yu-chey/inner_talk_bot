import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.markdown import hbold, hcode
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("STATS_BOT_TOKEN")
BASE_API_URL = "https://innertalkbot-production.up.railway.app"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


async def fetch_api_data(route: str) -> dict:
    """
    Отправляет GET-запрос на API-сервер по указанному маршруту.
    """
    url = f"{BASE_API_URL}{route}"
    logging.info(f"Fetching from: {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                # Читаем JSON в любом случае, чтобы получить detail в случае ошибки
                data = await response.json()

                if response.status == 200:
                    return {"success": True, "data": data}
                else:
                    error_detail = data.get('detail', data.get('error', 'Неизвестная ошибка API.'))
                    return {"success": False, "error": f"Ошибка сервера ({response.status}): {error_detail}"}
    except aiohttp.ClientConnectorError:
        return {"success": False, "error": "Не удалось подключиться к API. Сервер недоступен."}
    except Exception as e:
        logging.error(f"General error during API fetch: {e}")
        return {"success": False, "error": f"Произошла непредвиденная ошибка: {e}"}


# --------------------------------------------------------------------------
# 3. Обработчик: /user_stats <username>
# --------------------------------------------------------------------------

@dp.message(Command("user_stats"))
async def handle_user_stats(message: types.Message):
    args = message.text.split()

    if len(args) < 2:
        await message.reply("Пожалуйста, укажите имя пользователя.\nПример: /user_stats vasya_pupkin")
        return

    username = args[1].lstrip('@')
    await message.answer(f"Запрашиваю статистику для {hbold(username)}...", parse_mode="HTML")

    # Формируем маршрут для API
    route = f"/stats/user/{username}"
    result = await fetch_api_data(route)

    if not result["success"]:
        await message.answer(f"❌ {result['error']}")
        return

    data = result["data"]

    # Форматирование ответа
    response_text = f"""
📈 {hbold('Статистика пользователя')} {hcode(data['username'])}:

🔹 **Сообщения (user_text):** {hbold(data['total_user_texts'])}
🔹 **Заметки (note):** {hbold(data['total_notes'])}

📝 {hbold('Последние 3 заметки')}:
"""
    if data.get('last_notes_summary'):
        notes_list = '\n'.join([f"  • {text[:50]}..." for text in data['last_notes_summary']])
        response_text += hcode(notes_list)
    else:
        response_text += "  (Нет недавних заметок)"

    await message.answer(response_text, parse_mode="HTML")


# --------------------------------------------------------------------------
# 4. Обработчик: /total_stats
# --------------------------------------------------------------------------

@dp.message(Command("total_stats"))
async def handle_total_stats(message: types.Message):
    await message.answer("Запрашиваю общую статистику...", parse_mode="HTML")

    route = "/stats/total"
    result = await fetch_api_data(route)

    if not result["success"]:
        await message.answer(f"❌ {result['error']}")
        return

    data = result["data"]

    response_text = f"""
📊 {hbold('Общая Статистика')}:

🔹 **Всего уникальных пользователей:** {hbold(data['unique_username_count'])}
"""
    await message.answer(response_text, parse_mode="HTML")


# --------------------------------------------------------------------------
# 5. Обработчик: /all_users
# --------------------------------------------------------------------------

@dp.message(Command("all_users"))
async def handle_all_users(message: types.Message):
    await message.answer("Запрашиваю список всех пользователей. Это может занять некоторое время...", parse_mode="HTML")

    route = "/stats/users"
    result = await fetch_api_data(route)

    if not result["success"]:
        await message.answer(f"❌ {result['error']}")
        return

    data = result["data"]
    users = data.get('users', [])
    count = data.get('count', 0)

    if not users:
        await message.answer(f"✅ Пользователи не найдены. Всего: {hbold(0)}")
        return

    # Форматирование списка: отправляем только часть списка для удобства
    list_preview = '\n'.join(users[:15])  # Показываем только первые 15 пользователей

    response_text = f"""
👤 {hbold('Список пользователей')} ({hbold(count)} всего):

{hcode(list_preview)}
... и еще {count - 15} пользователей.
"""
    await message.answer(response_text, parse_mode="HTML")


# --------------------------------------------------------------------------
# 6. Запуск Бота
# --------------------------------------------------------------------------

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")