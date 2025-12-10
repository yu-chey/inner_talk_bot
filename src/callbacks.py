import asyncio
import logging
from datetime import datetime, timedelta, timezone
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from google.genai import types
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from keyboards import main_menu, about_us_menu, end_session_menu, back_to_menu_keyboard, support_menu
from photos import main_photo, about_us_photo, portrait_photo
from texts import MAIN_MENU_CAPTION, ABOUT_US_CAPTION, SUPPORT_CAPTION
from aiogram.enums import ParseMode

import config
from states import SessionStates

logger = logging.getLogger(__name__)

router = Router()

ERROR_MESSAGES = [
    "Ошибка генерации портрета. Попробуйте позже.",
    "К сожалению, в базе данных не найдено достаточно сообщений для анализа.",
    "Произошла критическая ошибка в системе. Ваш лимит не был исчерпан. Попробуйте, пожалуйста, снова."
]


async def update_portrait_caption_animation(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "**👂 Внимательно слушаю** вашу историю...",
        "**🧠 Сканирую** ключевые слова и эмоции...",
        "**📊 Ищу** повторяющиеся **паттерны**...",
        "**🔬 Анализирую** когнитивные искажения...",
        "**⚖️ Взвешиваю** потребности и ценности...",
        "**💡 Формулирую** финальный совет..."
    ]
    delay = 1.2

    try:
        while not stop_event.is_set():
            for text_frame in animation_texts:
                if stop_event.is_set():
                    break

                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=text_frame,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e):
                        return

                await asyncio.sleep(delay)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in update_portrait_caption_animation: {e}")


async def _generate_portrait_async(user_id, users_collection, generate_content_sync_func, gemini_client):
    portrait_prompt_template = (
        "ТЫ — профессиональный аналитик, специализирующийся на формировании психологического портрета и стиля общения на основе текстовых данных. Твоя задача — проанализировать представленный ниже текст, который является диалогами пользователя.\n\n"
        "ТВОЙ АНАЛИЗ ДОЛЖЕН СОДЕРЖАТЬ СЛЕДУЮЩИЕ РАЗДЕЛЫ:\n"
        "1.  **Общий Эмоциональный Фон:** Какие преобладающие эмоции прослеживаются в сообщениях (тревога, неуверенность, стремление к контролю, оптимизм и т.д.)?\n"
        "2.  **Паттерны Мышления и Реакций:** Какие повторяющиеся темы, установки, когнитивные искажения (например, \"все или ничего\", катастрофизация, сверхобобщение) или защитные механизмы можно отметить?\n"
        "3.  **Стиль Общения:** Насколько сообщения детальные, эмоционально окрашенные, структурированные, склонны ли к самокопанию или, наоборот, поверхностны?\n"
        "4.  **Ключевые Потребности/Ценности:** Какие фундаментальные потребности или ценности (например, безопасность, признание, самореализация, отношения) являются наиболее актуальными для этого человека.\n"
        "5.  **Совет от ИИ-Психолога:** Дай одну поддерживающую, фокусирующуюся на сильных сторонах и конструктивную рекомендацию.\n\n"
        "ФОРМАТИРОВАНИЕ:\n"
        "* Оформи ответ в виде связного, профессионального текста объемом **не более 120 слов** (для гарантии, что текст поместится в лимит Telegram).\n"
        "* Используй **жирный шрифт** для заголовков разделов.\n"
        "* Отвечай исключительно на РУССКОМ языке.\n"
        "* **НИ ПРИ КАКИХ УСЛОВИЯХ НЕ ОТВЕЧАЙ ФРАЗАМИ ТИПА \"Я НЕ СПЕЦИАЛИСТ\" ИЛИ \"ОБРАТИТЕСЬ К ПРОФЕССИОНАЛУ\".** Твоя роль — дать анализ.\n\n"
        "ИСТОРИЯ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ:\n---\n{dialog_text}\n---"
    )

    user_messages_cursor = users_collection.find(
        {"user_id": user_id, "type": "user_message"}
    ).sort("timestamp", 1)

    user_dialogs = []
    async for doc in user_messages_cursor:
        text = doc.get('text', '')
        username = doc.get('username')

        if username:
            user_dialogs.append(f"@{username}: {text}")
        else:
            user_dialogs.append(text)

    if not user_dialogs:
        return ERROR_MESSAGES[1]

    filtered_dialogs = [msg for msg in user_dialogs if msg.strip()]
    dialog_text = "\n".join([f"- {msg}" for msg in filtered_dialogs])
    summary_prompt = portrait_prompt_template.format(dialog_text=dialog_text)

    loop = asyncio.get_event_loop()
    portrait_contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=summary_prompt)]
        )
    ]

    portrait_result = ERROR_MESSAGES[0]

    try:
        portrait_response = await loop.run_in_executor(
            None,
            generate_content_sync_func,
            gemini_client,
            'gemini-2.5-flash',
            portrait_contents
        )
        portrait_result = portrait_response.text
    except Exception as e:
        logger.error(f"Gemini error during portrait generation: {e}")

    return portrait_result


async def _save_summary_async(session_data, users_collection, generate_content_sync_func, gemini_client):
    user_id = session_data['user_id']
    full_dialog = session_data['full_dialog']
    real_user_message_count = session_data['real_user_message_count']

    dialog_for_summary = full_dialog[1:] if full_dialog and full_dialog[0].get('content', '').startswith(
        "ПРЕДЫДУЩИЙ КОНСПЕКТ СЕССИИ:") else full_dialog

    dialog_text = "\n".join([f"{item['role']}: {item['content']}" for item in dialog_for_summary])

    system_instruction = (
        "Ты — специалист по конспектированию. Твоя задача — извлечь ключевые темы, эмоции и проблемы, "
        "обсужденные в предоставленном диалоге. Ответ должен быть кратким (не более 150 слов), "
        "используй чистый текст без форматирования (без жирного, курсива, списков), так как он будет использован "
        "для восстановления контекста в следующей сессии."
    )

    dialog_contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=f"Вот диалог, который необходимо законспектировать:\n---\n{dialog_text}")]
        )
    ]

    loop = asyncio.get_event_loop()
    session_summary = "Конспект не был сгенерирован из-за ошибки."

    try:
        summary_response = await loop.run_in_executor(
            None,
            generate_content_sync_func,
            gemini_client,
            'gemini-2.5-flash',
            dialog_contents,
            system_instruction
        )
        session_summary = summary_response.text
        logger.info(
            f"Конспект для пользователя {user_id} успешно сгенерирован. Длина: {len(session_summary)} символов.")
    except Exception as e:
        logger.error(f"Gemini error during session summary: {e}")

    session_record = {
        "user_id": user_id,
        "date": datetime.now(timezone.utc),
        "summary": session_summary,
        "full_dialog_length": real_user_message_count,
        "type": "session_summary"
    }

    try:
        await users_collection.insert_one(session_record)
    except Exception as e:
        logger.error(f"MongoDB error during summary insertion: {e}")


async def _load_session_history(user_id, users_collection, state: FSMContext):
    initial_history = []

    try:
        last_summary_record = await users_collection.find_one(
            {"user_id": user_id, "type": "session_summary"},
            sort=[("date", -1)]
        )

        if last_summary_record and 'summary' in last_summary_record:
            last_summary = last_summary_record['summary']

            if last_summary and last_summary.strip():
                initial_history.append({
                    "role": "user",
                    "content": f"ПРЕДЫДУЩИЙ КОНСПЕКТ СЕССИИ: {last_summary}. Учти его в текущем диалоге."
                })

        await state.update_data(current_dialog=initial_history)

    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке конспекта для {user_id}: {e}")


@router.callback_query(F.data == "main_menu")
async def menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    current_data = await state.get_data()

    if current_data.get('portrait_loading') is True and current_data.get(
            'loading_message_id') == callback.message.message_id:
        await state.update_data(portrait_loading=False, loading_message_id=None)

    caption_text = MAIN_MENU_CAPTION

    try:
        new_media = InputMediaPhoto(
            media=main_photo,
            caption=caption_text,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.message.edit_media(
            media=new_media,
            reply_markup=main_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=main_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    await callback.answer()


@router.callback_query(F.data == "about_us")
async def about_us_handler(callback: CallbackQuery) -> None:
    caption_text = ABOUT_US_CAPTION
    new_media = InputMediaPhoto(
        media=about_us_photo,
        caption=caption_text,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=about_us_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=about_us_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    await callback.answer()


@router.callback_query(F.data == "start_session")
async def start_session_handler(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    user_id = callback.from_user.id
    current_time_utc = datetime.now(timezone.utc)
    today_utc = current_time_utc.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

    sessions_today_count = await users_collection.count_documents({
        "user_id": user_id,
        "type": "session_summary",
        "date": {"$gte": today_utc}
    })

    logger.info(f"User {user_id} attempts session. Count: {sessions_today_count}. Max: {config.MAX_SESSIONS_PER_DAY}")

    if sessions_today_count >= config.MAX_SESSIONS_PER_DAY:
        logger.warning(
            f"User {user_id} hit session limit. Count: {sessions_today_count}, Max: {config.MAX_SESSIONS_PER_DAY}")
        await callback.answer(
            f"⚠️ Вы достигли лимита в {config.MAX_SESSIONS_PER_DAY} сессий на сегодня. "
            f"Пожалуйста, попробуйте завтра.",
            show_alert=True
        )
        return

    await callback.answer()

    loading_caption = "⏳ **Готовлю рабочее пространство...**\nЗагружаю предыдущий контекст. Секунду..."

    try:
        loading_message = await callback.message.edit_caption(
            caption=loading_caption,
            reply_markup=None,
            parse_mode=ParseMode.MARKDOWN
        )
        loading_message_id = loading_message.message_id
    except TelegramBadRequest:
        loading_message = await callback.message.answer(loading_caption, reply_markup=None,
                                                        parse_mode=ParseMode.MARKDOWN)
        loading_message_id = loading_message.message_id

    await _load_session_history(
        user_id=callback.from_user.id,
        users_collection=users_collection,
        state=state
    )

    start_caption = (
        "🎉 **Сессия начата!** Я слушаю тебя. Помни, что сессия ограничена объемом **"
        f"~{config.MAX_TOKENS_PER_SESSION} токенов** для контроля расходов (это примерно 50-70 сообщений). \n"
        "Удачного вам диалога! 😊\n"
        "Помните, что я здесь для того, чтобы поддержать вас. "
        "Говорите свободно, я слушаю внимательно. "
        "Нажмите кнопку ниже, когда будете готовы закончить сессию."
    )

    try:
        await callback.message.edit_caption(
            caption=start_caption,
            reply_markup=end_session_menu,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest:
        await callback.message.answer(start_caption, reply_markup=end_session_menu, parse_mode=ParseMode.MARKDOWN)

    await state.set_state(SessionStates.in_session)
    await state.update_data(
        last_ai_message_id=callback.message.message_id,
        real_user_message_count=0
    )


@router.callback_query(F.data == "end_session", StateFilter(SessionStates.in_session))
async def end_session_handler(callback: CallbackQuery, state: FSMContext, users_collection, generate_content_sync_func,
                              gemini_client) -> None:
    data = await state.get_data()
    full_dialog = data.get('current_dialog', [])
    last_ai_message_id = data.get('last_ai_message_id')
    user_id = callback.from_user.id

    if last_ai_message_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=last_ai_message_id,
                reply_markup=None
            )
        except TelegramBadRequest:
            pass

    real_user_message_count = data.get('real_user_message_count', 0)

    if real_user_message_count < 1:
        try:
            await callback.message.answer(
                text="Сессия была слишком короткой (0 сообщений) и не была сохранена."
            )
        except TelegramBadRequest:
            pass

        await state.set_state(SessionStates.idle)
        await state.set_data({})

        caption_text = MAIN_MENU_CAPTION
        await callback.message.answer_photo(
            photo=main_photo,
            caption=caption_text,
            reply_markup=main_menu,
            parse_mode=ParseMode.MARKDOWN
        )

        await callback.answer()
        return

    processing_text = "📝 **Создаю конспект** и завершаю сессию..."
    processing_message = await callback.message.answer(text=processing_text, parse_mode=ParseMode.MARKDOWN)

    session_data = {
        "user_id": user_id,
        "full_dialog": full_dialog,
        "real_user_message_count": real_user_message_count
    }

    await _save_summary_async(
        session_data,
        users_collection,
        generate_content_sync_func,
        gemini_client
    )

    final_text = (
        f"✅ Сессия завершена! "
        f"Вы обменялись *{real_user_message_count}* сообщениями.\n"
        f"📝 Конспект сохранен."
    )

    try:
        await processing_message.edit_text(text=final_text, parse_mode=ParseMode.MARKDOWN)
    except TelegramBadRequest:
        await callback.message.answer(text=final_text, parse_mode=ParseMode.MARKDOWN)

    await state.set_state(SessionStates.idle)
    await state.set_data({})

    caption_text = MAIN_MENU_CAPTION

    await callback.message.answer_photo(
        photo=main_photo,
        caption=caption_text,
        reply_markup=main_menu,
        parse_mode=ParseMode.MARKDOWN
    )

    await callback.answer()


@router.callback_query(F.data == "get_profile")
async def get_profile_handler(callback: CallbackQuery) -> None:
    await callback.message.answer("Функция 'Профиль' в разработке. Скоро ИИ сделает ваш психологический портрет!")
    await callback.answer()


@router.callback_query(F.data == "get_portrait")
async def get_portrait_handler(callback: CallbackQuery, users_collection, generate_content_sync_func, gemini_client,
                               state: FSMContext, bot) -> None:
    user_id = callback.from_user.id
    current_time = datetime.now(timezone.utc)

    user_doc = await users_collection.find_one({"user_id": user_id, "type": "user_profile"})
    last_portrait_timestamp_from_db = user_doc.get("last_portrait_timestamp") if user_doc and isinstance(
        user_doc.get("last_portrait_timestamp"), datetime) else None

    last_portrait_timestamp = None
    if last_portrait_timestamp_from_db:
        last_portrait_timestamp = last_portrait_timestamp_from_db.replace(tzinfo=timezone.utc)

    if last_portrait_timestamp:
        cooldown_end_time = last_portrait_timestamp + timedelta(hours=config.PORTRAIT_COOLDOWN_HOURS)

        if current_time < cooldown_end_time:
            time_left = cooldown_end_time - current_time
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)

            await callback.answer(
                f"⚠️ Психологический портрет можно создавать не чаще, чем раз в {config.PORTRAIT_COOLDOWN_HOURS} часа. "
                f"Повторная попытка будет доступна через {hours} ч. {minutes} мин.",
                show_alert=True
            )
            return

    await callback.answer("Запускаю анализ... 🧠")

    initial_caption = "⏳ **Начинаю анализ...**"
    new_media = InputMediaPhoto(
        media=portrait_photo,
        caption=initial_caption,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        message_to_edit = await callback.message.edit_media(
            media=new_media,
            reply_markup=back_to_menu_keyboard
        )
    except TelegramBadRequest:
        message_to_edit = await callback.message.edit_caption(
            caption=initial_caption,
            reply_markup=back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    await state.update_data(
        portrait_loading=True,
        loading_message_id=message_to_edit.message_id
    )

    stop_event = asyncio.Event()

    animation_task = asyncio.create_task(
        update_portrait_caption_animation(
            bot,
            callback.message.chat.id,
            message_to_edit.message_id,
            stop_event
        )
    )

    generation_task = asyncio.create_task(
        _generate_portrait_async(
            user_id=callback.from_user.id,
            users_collection=users_collection,
            generate_content_sync_func=generate_content_sync_func,
            gemini_client=gemini_client
        )
    )

    portrait_result = ERROR_MESSAGES[2]

    try:
        portrait_result = await generation_task
    except Exception as e:
        logger.error(f"Critical error during portrait generation (main task): {e}")
    finally:
        stop_event.set()
        await asyncio.gather(animation_task, return_exceptions=True)

    is_successful_generation = not any(err in portrait_result for err in ERROR_MESSAGES)

    if is_successful_generation:
        await users_collection.update_one(
            {"user_id": user_id, "type": "user_profile"},
            {"$set": {"last_portrait_timestamp": current_time}},
            upsert=True
        )
        logger.info(f"User {user_id} successfully generated portrait. Cooldown applied.")
    else:
        logger.warning(f"User {user_id} failed to generate portrait: {portrait_result}. Cooldown skipped.")

    await state.update_data(portrait_loading=False, loading_message_id=None)

    caption_limit = 1000

    if is_successful_generation:
        header = "**Ваш Психологический Портрет: 🧠**\n\n"
    else:
        header = ""

    if len(portrait_result) > caption_limit - len(header):
        portrait_result = portrait_result[:caption_limit - len(header) - 5] + "..."

    final_caption = f"{header}{portrait_result}"

    try:
        await message_to_edit.edit_caption(
            caption=final_caption,
            reply_markup=back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit final caption after portrait generation: {e}")
        await callback.message.answer_photo(
            photo=portrait_photo,
            caption=final_caption,
            reply_markup=back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )


@router.callback_query(F.data == "call_support")
async def call_support_handler(callback: CallbackQuery) -> None:
    caption_text = SUPPORT_CAPTION

    new_media = InputMediaPhoto(
        media=main_photo,
        caption=caption_text,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=support_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=support_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    await callback.answer()