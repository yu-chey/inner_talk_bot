import asyncio
import logging
from datetime import datetime, timezone
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from . import config
from . import keyboards
from . import photos
from . import texts
from . import states
from google.genai import types
from aiogram.types import Message
from aiogram.enums import ParseMode

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
    await state.set_state(states.SessionStates.idle)

    user = message.from_user
    asyncio.create_task(_save_user_profile_async(
        users_collection,
        user.id,
        user.username,
        user.first_name
    ))

    caption_text = texts.MAIN_MENU_CAPTION
    await message.answer_photo(
        photo=photos.main_photo,
        caption=caption_text,
        reply_markup=keyboards.main_menu,
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

@router.message(F.content_type != "text", StateFilter(states.SessionStates.in_session))
async def non_text_in_session_handler(message: Message) -> None:
    await message.answer(
        "🚫 **Ошибка:** Я — текстовый ИИ-психолог и могу обрабатывать **только текстовые сообщения**.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(StateFilter(states.SessionStates.in_session))
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
    ai_style = current_data.get("ai_style", "default")
    real_user_message_count = current_data.get("real_user_message_count", 0) + 1

    is_miracle_asked = current_data.get('miracle_question_asked', False)
    is_scaling_asked = current_data.get('scaling_question_asked', False)

    if real_user_message_count == 2 and not is_miracle_asked:
        logger.info(f"User {user_id} reached 2 messages. Initiating Miracle Question.")
        await state.update_data(initiate_miracle_question=True, miracle_question_asked=True)

    elif real_user_message_count == 5 and not is_miracle_asked and not is_scaling_asked:
        logger.info(f"User {user_id} reached 5 messages. Initiating Scaling Question.")
        await state.update_data(initiate_scaling_question=True, scaling_question_asked=True)

    else:
        if current_data.get('initiate_miracle_question'):
            await state.update_data(initiate_miracle_question=False)
        if current_data.get('initiate_scaling_question'):
            await state.update_data(initiate_scaling_question=False)

    style_modifier = ""
    if ai_style == "empathy":
        style_modifier = (
            "ТВОЙ ПРИОРИТЕТ: Сейчас ты должен быть максимально эмпатичным и поддерживающим. "
            "Фокусируйся на валидации чувств пользователя, покажи, что ты слышишь его боль. "
            "Уменьши количество прямых вопросов, увеличь количество фраз сочувствия."
        )
    elif ai_style == "action":
        style_modifier = (
            "ТВОЙ ПРИОРИТЕТ: Ты должен быть максимально практичным и ориентированным на действия. "
            "Избегай лишних фраз сочувствия. Сразу предлагай конкретные шаги, формулируй задачи "
            "и фокусируйся на плане действий. В выводах '3-2-1' делай упор на '1️⃣ Действие'."
        )

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

    updated_data = await state.get_data()

    miracle_prompt_modifier = ""
    if updated_data.get('initiate_miracle_question'):
        miracle_prompt_modifier = "FSMContext содержит ключ 'initiate_miracle_question'. Немедленно выполни УПРАЖНЕНИЕ: Вопрос о Чуде, строго по инструкции 5."

    scaling_prompt_modifier = ""
    if updated_data.get('initiate_scaling_question'):
        scaling_prompt_modifier = "FSMContext содержит ключ 'initiate_scaling_question'. Немедленно выполни УПРАЖНЕНИЕ: Шкала Компетентности, строго по инструкции 6."

    full_modifier = f"{style_modifier}\n\n{miracle_prompt_modifier}\n\n{scaling_prompt_modifier}"

    base_prompt_with_style = f"{config.SYSTEM_PROMPT_TEXT}\n\n{full_modifier}"

    if is_summary_present and summary_content_dict:
        final_system_prompt = f"{summary_content_dict['content']}\n\n{base_prompt_with_style}"
        logger.info("Конспект и Акцент добавлены в системную инструкцию для Gemini.")
    else:
        final_system_prompt = base_prompt_with_style
        logger.info(f"Используется Акцент: {ai_style}")

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
            reply_markup=keyboards.end_session_menu,
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
            reply_markup=keyboards.end_session_menu,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.warning(f"Failed to edit thinking message: {e}")
        final_message = await message.answer(
            ai_response,
            reply_markup=keyboards.end_session_menu,
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

@router.message(F.content_type != "text")
async def non_text_idle_handler(message: Message) -> None:
    print(message.photo[-1].file_id)