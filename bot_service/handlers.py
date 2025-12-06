import asyncio
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from google.genai.errors import APIError
from .config import SYSTEM_PROMPT_TEXT
from .db_manager import save_message, get_chat_history, clear_chat_history

dp = Router()


@dp.message(Command("start"))
async def start_handler(msg: Message):
    await clear_chat_history(msg.from_user.id)

    initial_bot_response = "Привет! Я твой ИИ-психолог. Расскажи, что тебя беспокоит 😊\n\nЧтобы начать разговор заново, используй команду /clear."

    await save_message(msg.from_user.id, "system_prompt", SYSTEM_PROMPT_TEXT)
    await save_message(msg.from_user.id, "model", initial_bot_response)

    await msg.answer(initial_bot_response)


@dp.message(Command("clear"))
async def clear_handler(msg: Message):
    deleted_count = await clear_chat_history(msg.from_user.id)
    await msg.answer(f"История чата очищена ({deleted_count} сообщений). Начнем новый разговор!")


@dp.message()
async def chat_handler(
        msg: Message,
        gemini_client: object,
        generate_content_sync_func: callable
):
    user_id = msg.from_user.id
    user_text = msg.text

    if not user_text:
        return

    await save_message(user_id, "user", user_text)

    full_history = await get_chat_history(user_id)

    final_contents = []

    messages_added_count = 0

    system_msg = next((m for m in full_history if m['role'] == 'system_prompt'), None)
    first_bot_response = next((m for m in full_history if m['role'] == 'model'), None)

    if system_msg and first_bot_response:
        final_contents.append({"role": "user", "parts": [{"text": system_msg["text"]}]})
        final_contents.append({"role": "model", "parts": [{"text": first_bot_response["text"]}]})

        messages_added_count = 2


    for i, message in enumerate(full_history):
        if i < messages_added_count:
            continue

        if message['role'] == 'system_prompt':
            continue

        if message['role'] == 'user' or message['role'] == 'model':
            final_contents.append({"role": message["role"], "parts": [{"text": message["text"]}]})

    thinking_message = await msg.answer("Думаю над ответом... ⏳")

    try:
        await msg.chat.do('typing')
        
        response = await asyncio.to_thread(
            generate_content_sync_func,
            gemini_client,
            "gemini-2.5-flash",
            final_contents
        )
        ai_response = response.text

        await save_message(user_id, "model", ai_response)

        await thinking_message.edit_text(ai_response)
        
        await msg.chat.do('cancel')

    except APIError as e:
        logging.error(f"Gemini API Error for user {user_id}: {e}")
        await msg.answer("Прости, у меня возникла проблема с ИИ. Попробуй позже.")
    except Exception as e:
        logging.error(f"General Error for user {user_id}: {e}")
        await msg.answer("Прости, у меня возникла техническая проблема. Попробуй позже.")
