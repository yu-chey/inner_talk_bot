import asyncio
import logging
from datetime import datetime, timezone
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
import config
from google.genai import types
from states import SessionStates
from aiogram.types import Message
from keyboards import main_menu, end_session_menu
from texts import MAIN_MENU_CAPTION
from aiogram.enums import ParseMode, ChatAction
from photos import main_photo

logger = logging.getLogger(__name__)

router = Router()

async def _save_user_profile_async(collection, user_id, username, first_name):
    """Фоновое сохранение или обновление профиля пользователя в MongoDB."""
    try:
        await collection.update_one(
            {"user_id": user_id, "type": "user_profile"},
            {"$set": {
                "username": username,
                "first_name": first_name,
                "last_active": datetime.now(timezone.utc)
            }},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения/обновления профиля пользователя: {e}")

async def _save_to_db_async(collection, data):
    """Фоновое сохранение данных в MongoDB."""
    try:
        await collection.insert_one(data)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных в MongoDB в фоновом режиме: {e}")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, users_collection) -> None:
    await state.set_state(SessionStates.idle)

    user = message.from_user
    asyncio.create_task(_save_user_profile_async(
        users_collection,
        user.id,
        user.username,
        user.first_name
    ))

    caption_text = MAIN_MENU_CAPTION
    await message.answer_photo(
        photo=main_photo,
        caption=caption_text,
        reply_markup=main_menu,
        parse_mode=ParseMode.MARKDOWN)


async def update_thinking_message(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "**🔍 Анализирую** ваш диалог...",
        "**🧠 Синтезирую** информацию...",
        "**💬 Формулирую** ответ...",
        "**⚙️ Вычисляю** оптимальный совет..."
    ]
    delay = 1.0

    try:
        while not stop_event.is_set():
            for text_frame in animation_texts:
                if stop_event.is_set():
                    break

                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text_frame,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e):
                        return

                await asyncio.sleep(delay)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in update_thinking_message: {e}")

@router.message(StateFilter(SessionStates.in_session))
async def echo_handler(message: Message, state: FSMContext, generate_content_sync_func, users_collection, bot,
                       gemini_client, count_tokens_sync_func) -> None:
    user_text = message.text
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username

    if not user_text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return

    current_data = await state.get_data()
    history = current_data.get("current_dialog", [])
    last_ai_message_id = current_data.get('last_ai_message_id')

    if last_ai_message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=last_ai_message_id,
                reply_markup=None
            )
        except TelegramBadRequest:
            pass

    is_summary_present = (
            len(history) > 0 and
            history[0].get('content', '').startswith("ПРЕДЫДУЩИЙ КОНСПЕКТ СЕССИИ:")
    )
    summary_content_dict = history[0] if is_summary_present else None

    dialog_messages_only = history[1:] if is_summary_present else history.copy()

    user_message_content_dict = {"role": "user", "content": user_text}
    dialog_messages_only.append(user_message_content_dict)

    final_system_prompt = config.SYSTEM_PROMPT_TEXT
    if is_summary_present and summary_content_dict:
        final_system_prompt = f"{summary_content_dict['content']}\n\n{config.SYSTEM_PROMPT_TEXT}"
        logger.info("Конспект добавлен в системную инструкцию для Gemini.")

    new_contents_gemini = [
        types.Content(
            role=item['role'],
            parts=[types.Part(text=item['content'])]
        )
        for item in dialog_messages_only
    ]

    loop = asyncio.get_event_loop()
    total_token_count = 0

    try:
        token_response = await loop.run_in_executor(
            None,
            count_tokens_sync_func,
            gemini_client,
            'gemini-2.5-flash',
            new_contents_gemini,
        )
        total_token_count = token_response.total_tokens
    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        pass

    if total_token_count >= config.MAX_TOKENS_PER_SESSION:
        await message.answer(
            f"🕰️ **Лимит сессии:** Общий объем диалога ({total_token_count} токенов) "
            f"достиг максимума (~{config.MAX_TOKENS_PER_SESSION} токенов). \n"
            f"Для завершения и сохранения конспекта, пожалуйста, нажмите **'Закончить сессию'**.",
            reply_markup=end_session_menu,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    thinking_message = await message.answer("...")

    stop_event = asyncio.Event()
    animation_task = asyncio.create_task(
        update_thinking_message(
            bot,
            chat_id,
            thinking_message.message_id,
            stop_event
        )
    )

    ai_response = "Извините, произошла ошибка на стороне ИИ. Попробуйте закончить сессию и начать новую."

    try:
        ai_response_obj = await loop.run_in_executor(
            None,
            generate_content_sync_func,
            gemini_client,
            'gemini-2.5-flash',
            new_contents_gemini,
            final_system_prompt
        )
        ai_response = ai_response_obj.text
    except Exception as e:
        logger.error(f"Gemini API call error: {e}")

    stop_event.set()

    try:
        await animation_task
    except asyncio.CancelledError:
        pass

    final_message = thinking_message

    try:
        await thinking_message.edit_text(
            text=ai_response,
            reply_markup=end_session_menu,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.warning(f"Failed to edit thinking message: {e}")
        final_message = await message.answer(
            ai_response,
            reply_markup=end_session_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    current_time = datetime.now(timezone.utc)

    asyncio.create_task(_save_to_db_async(users_collection, {
        "user_id": user_id,
        "type": "user_message",
        "text": user_text,
        "timestamp": current_time,
        "username": username,
    }))

    asyncio.create_task(_save_to_db_async(users_collection, {
        "user_id": user_id,
        "type": "model_response",
        "text": ai_response,
        "timestamp": current_time,
    }))

    dialog_messages_only.append({"role": "model", "content": ai_response})

    history_to_save = dialog_messages_only

    if is_summary_present and summary_content_dict:
        history_to_save.insert(0, summary_content_dict)
        logger.info("Конспект возвращен в историю для FSMContext (индекс 0).")

    real_user_message_count = current_data.get("real_user_message_count", 0) + 1

    await state.update_data(
        current_dialog=history_to_save,
        last_ai_message_id=final_message.message_id,
        real_user_message_count=real_user_message_count
    )