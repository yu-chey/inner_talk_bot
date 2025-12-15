import asyncio
import logging
from datetime import datetime, timedelta, timezone
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from google.genai import types
from aiogram.types import CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, Message
from . import keyboards
from . import photos
from . import texts
from aiogram.enums import ParseMode
from . import states
from . import config
from .handlers import _save_to_db_async

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

async def update_stats_caption_animation(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "**📊 Собираю** все оценки прогресса...",
        "**🧠 Вычисляю** средний балл...",
        "**📈 Анализирую** тенденции за последний месяц...",
        "**💡 Формулирую** финальные выводы..."
    ]
    delay = 1.0

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
        logger.error(f"Error in update_stats_caption_animation: {e}")


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
        "* Оформи ответ в виде связного, профессионального текста объемом **не более 900 символов** (для гарантии, что текст поместится в лимит Telegram. ЭТО КРИТИЧЕСКИ ВАЖНО).\n"
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
    await state.set_state(states.SessionStates.idle)

    current_data = await state.get_data()

    if current_data.get('portrait_loading') is True and current_data.get(
            'loading_message_id') == callback.message.message_id:
        await state.update_data(portrait_loading=False, loading_message_id=None)

    caption_text = texts.MAIN_MENU_CAPTION

    try:
        new_media = InputMediaPhoto(
            media=photos.main_photo,
            caption=caption_text,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.main_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.main_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    await callback.answer()


@router.callback_query(F.data == "about_us")
async def about_us_handler(callback: CallbackQuery) -> None:
    caption_text = texts.ABOUT_US_CAPTION
    new_media = InputMediaPhoto(
        media=photos.about_us_photo,
        caption=caption_text,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.about_us_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.about_us_menu,
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

    new_media = InputMediaPhoto(
        media=photos.active_session_photo,
        caption=loading_caption,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        loading_message = await callback.message.edit_media(
            media=new_media
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

    new_media = InputMediaPhoto(
        media=photos.active_session_photo,
        caption=start_caption,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media
        )
    except TelegramBadRequest:
        await callback.message.answer(start_caption, reply_markup=keyboards.end_session_menu, parse_mode=ParseMode.MARKDOWN)

    await state.set_state(states.SessionStates.in_session)
    await state.update_data(
        last_ai_message_id=callback.message.message_id,
        real_user_message_count=0
    )


@router.callback_query(F.data == "end_session", StateFilter(states.SessionStates.in_session))
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

        await state.set_state(states.SessionStates.idle)
        await state.set_data({})

        caption_text = texts.MAIN_MENU_CAPTION
        await callback.message.answer_photo(
            photo=photos.main_photo,
            caption=caption_text,
            reply_markup=keyboards.main_menu,
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

    data = await state.get_data()
    saved_style = data.get("ai_style", "default")

    await state.set_state(states.SessionStates.idle)
    await state.set_data({"ai_style": saved_style})

    caption_text = texts.MAIN_MENU_CAPTION

    await callback.message.answer_photo(
        photo=photos.main_photo,
        caption=caption_text,
        reply_markup=keyboards.main_menu,
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
        media=photos.portrait_photo,
        caption=initial_caption,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        message_to_edit = await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.back_to_menu_keyboard
        )
    except TelegramBadRequest:
        message_to_edit = await callback.message.edit_caption(
            caption=initial_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
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

    caption_limit = 1020

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
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit final caption after portrait generation: {e}")
        await callback.message.answer_photo(
            photo=photos.portrait_photo,
            caption=final_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )


@router.callback_query(F.data == "call_support")
async def call_support_handler(callback: CallbackQuery) -> None:
    caption_text = texts.SUPPORT_CAPTION

    new_media = InputMediaPhoto(
        media=photos.support_photo,
        caption=caption_text,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.support_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.support_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    await callback.answer()


@router.callback_query(F.data == "start_progress_scale", StateFilter(states.SessionStates.idle, None))
async def start_progress_scale_handler(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    user_id = callback.from_user.id
    current_time = datetime.now(timezone.utc)

    last_score_doc = await users_collection.find_one(
        {"user_id": user_id, "type": "progress_score"},
        sort=[("timestamp", -1)]
    )

    if last_score_doc and 'timestamp' in last_score_doc:
        last_score_time = last_score_doc['timestamp'].replace(tzinfo=timezone.utc)

        cooldown_end_time = last_score_time + timedelta(hours=config.PROGRESS_SCORE_COOLDOWN_HOURS)

        if current_time < cooldown_end_time:
            time_left = cooldown_end_time - current_time
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)

            await callback.answer(
                f"⚠️ Вы можете оценить свое состояние не чаще, чем раз в {config.PROGRESS_SCORE_COOLDOWN_HOURS} часа. "
                f"Повторная попытка будет доступна через {hours} ч. {minutes} мин.",
                show_alert=True
            )
            return

    await state.set_state(states.MoodStates.waiting_for_score)

    caption_text = (
        "📈 **Шкала Прогресса**\n\n"
        "Как вы оцениваете свое текущее состояние или прогресс в решении проблемы?\n\n"
        "По шкале от 1 до 10 👨🏼‍⚕️"
    )

    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=caption_text,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.progress_scale_menu
        )
    except TelegramBadRequest as e:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.progress_scale_menu,
            parse_mode=ParseMode.MARKDOWN
        )
        logger.warning(f"Failed to edit media for scale, used edit_caption: {e}")

    await callback.answer("Выберите оценку...")


@router.callback_query(F.data.startswith("set_score:"))
async def set_score_handler(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    if await state.get_state() != states.MoodStates.waiting_for_score:
        await callback.answer("Ошибка: Опрос не был начат корректно.")
        return

    score = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    current_time = datetime.now(timezone.utc)

    asyncio.create_task(_save_to_db_async(users_collection, {
        "user_id": user_id,
        "type": "progress_score",
        "score": score,
        "timestamp": current_time,
    }))

    filled = "🟢" * score
    empty = "⚪" * (10 - score)
    progress_bar = f"{filled}{empty}"

    final_caption = (
        f"✅ **Отлично! Ваша оценка сохранена.**\n\n"
        f"Текущий прогресс: **{progress_bar}** ({score}/10)\n\n"
        "Чем чаще вы оцениваете прогресс, тем лучше видите свой путь. Нажмите кнопку, чтобы вернуться к основным функциям."
    )

    try:
        await callback.message.edit_caption(
            caption=final_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit caption after score: {e}")
        await callback.message.answer(
            text=final_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    await state.set_state(states.SessionStates.idle)

    await callback.answer()


@router.callback_query(F.data == "start_style_selection", StateFilter(states.SessionStates.idle, None))
async def start_style_selection_handler(callback: CallbackQuery, state: FSMContext) -> None:
    caption_text = (
        "⚙️ Настройка Акцента для Сессии\n\n"
        "Выберите, какой тип поддержки вам нужен прямо сейчас:\n\n"
        "**🤗 Эмпатия:** Больше поддержки, сочувствия и валидации чувств.\n"
        "**🛠️ Практика:** Больше конкретных шагов, задач и фокуса на решении.\n\n"
        "Этот акцент будет применен к вашей следующей сессии (кнопка 'Начать разговор')."
    )

    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=caption_text,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.style_selection_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.style_selection_menu,
            parse_mode=ParseMode.MARKDOWN
        )

    await callback.answer()


@router.callback_query(F.data.startswith("set_style:"))
async def style_selector_handler(callback: CallbackQuery, state: FSMContext) -> None:
    style_code = callback.data.split(":")[1]

    await state.update_data(ai_style=style_code)

    if style_code == 'empathy':
        style_text = "🤗 Эмпатия и Поддержка"
    elif style_code == 'action':
        style_text = "🛠️ Практика и Действие"
    else:
        style_text = "Стандартный режим SFBT"

    confirmation_text = (
        f"✅ **Акцент установлен!**\n\n"
        f"Текущий стиль: **{style_text}**\n\n"
        "Нажмите **'🎉 Начать разговор'**, чтобы начать сессию с этим акцентом."
    )

    try:
        await callback.message.edit_caption(
            caption=confirmation_text,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        await callback.message.answer(
            text=confirmation_text,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        logger.warning(f"Failed to edit message after style selection, sending new: {e}")

    await callback.answer()


async def _get_user_stats_async(user_id, users_collection):
    """Фоновый сбор всех данных и метрик статистики."""
    scores_cursor = users_collection.find(
        {"user_id": user_id, "type": "progress_score"}
    ).sort("timestamp", -1)

    all_scores = await scores_cursor.to_list(length=None)

    total_scores = len(all_scores)

    if total_scores == 0:
        return None, 0, 0, None, 0

    numeric_scores = [doc['score'] for doc in all_scores if 'score' in doc]
    latest_score = numeric_scores[0]
    average_score = sum(numeric_scores) / total_scores
    latest_timestamp = all_scores[0]['timestamp']

    trend_line = ""
    avg_latest_n = average_score
    if total_scores >= 2:
        last_n = min(5, total_scores)
        avg_latest_n = sum(numeric_scores[:last_n]) / last_n

    return numeric_scores, total_scores, average_score, latest_timestamp, avg_latest_n


@router.callback_query(F.data == "get_user_stats")
async def get_stats_handler(callback: CallbackQuery, users_collection, state: FSMContext, bot) -> None:
    user_id = callback.from_user.id

    await callback.answer()

    initial_caption = "⏳ **Начинаю сбор статистики...**"
    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=initial_caption,
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        message_to_edit = await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.back_to_menu_keyboard
        )
    except TelegramBadRequest:
        message_to_edit = await callback.message.edit_caption(
            caption=initial_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    stop_event = asyncio.Event()

    animation_task = asyncio.create_task(
        update_stats_caption_animation(
            bot,
            callback.message.chat.id,
            message_to_edit.message_id,
            stop_event
        )
    )

    generation_task = asyncio.create_task(
        _get_user_stats_async(
            user_id=user_id,
            users_collection=users_collection
        )
    )

    numeric_scores, total_scores, average_score, latest_timestamp, avg_latest_n = (None, 0, 0, None, 0)

    try:
        numeric_scores, total_scores, average_score, latest_timestamp, avg_latest_n = await generation_task
    except Exception as e:
        logger.error(f"Critical error during stats generation: {e}")
    finally:
        stop_event.set()
        await asyncio.gather(animation_task, return_exceptions=True)

    if total_scores == 0:
        final_caption = (
            "😔 **Статистика недоступна**\n\n"
            "Вы еще не оценили свой прогресс ни разу. Начните с **'📈 Шкала Прогресса'**!"
        )
    else:
        latest_score = numeric_scores[0]

        trend_line = "Для отслеживания тенденции нужна минимум 2 оценки."
        if total_scores >= 2 and average_score > 0:
            diff_percent = (avg_latest_n - average_score) / average_score
            last_n = min(5, total_scores)

            trend_status = ""
            trend_icon = "⚖️"

            if diff_percent > 0.05:
                trend_status = "заметно **улучшился**"
                trend_icon = "🚀"
            elif diff_percent < -0.05:
                trend_status = "**снизился**"
                trend_icon = "⬇️"
            else:
                trend_status = "стабилен"
                trend_icon = "⚖️"

            trend_line = f"Тенденция за последние {last_n} оценок: {trend_icon} Прогресс {trend_status}."

        final_caption = (
            "📊 **Ваша Персональная Статистика**\n\n"
            "---"
            "\n\n**✅ Оценки прогресса**"
            f"\n- **Всего оценок:** `{total_scores}`"
            f"\n- **Последняя оценка:** **{latest_score}/10** (от {latest_timestamp.strftime('%d.%m.%Y')})"
            f"\n- **Средняя оценка:** **{average_score:.2f}/10**"
            f"\n\n{trend_line}"
            f"\n\n---"
            f"\n\n**📝 Рекомендация:** Отмечайте, что изменилось между высоким и низким баллом, чтобы увидеть свои **точки роста**."
        )
    try:
        await message_to_edit.edit_caption(
            caption=final_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit final caption after stats generation: {e}")
        await callback.message.answer(
            final_caption,
            reply_markup=keyboards.back_to_menu_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

async def get_total_user_count(users_collection) -> int:
    pipeline = [
        {"$group": {"_id": "$user_id"}},
        {"$count": "unique_users_count"}
    ]

    cursor = users_collection.aggregate(pipeline)
    result = await cursor.to_list(length=1)

    if result:
        return result[0].get("unique_users_count", 0)
    else:
        return 0

async def get_total_user_messages(users_collection) -> int:
    return await users_collection.count_documents({"type": "user_message"})

async def get_distinct_users_who_sent_messages(users_collection):
    pipeline = [
        {"$match": {"type": "user_message"}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "distinct_users"}
    ]

    cursor = users_collection.aggregate(pipeline)
    result = await cursor.to_list(length=1)

    return result[0].get("distinct_users", 0) if result else 0

async def get_average_messages_per_user(users_collection):
    total_messages_task = asyncio.create_task(get_total_user_messages(users_collection))
    unique_users_task = asyncio.create_task(get_distinct_users_who_sent_messages(users_collection))

    total_messages, unique_users = await asyncio.gather(total_messages_task, unique_users_task)

    if unique_users == 0:
        avg = 0
    else:
        avg = total_messages / unique_users

    return {
        "average_messages_per_user": round(avg, 2),
        "total_messages": total_messages,
        "unique_users": unique_users
    }

@router.callback_query(F.data == "admin_panel", config.IsAdmin())
async def admin_panel(callback: CallbackQuery) -> None:
    text = (
        "👋 Добро пожаловать в Админ-панель!\n\n"
        "Вы находитесь в главном меню управления ботом."
        "Выберите действие ниже, чтобы начать работу с пользователями или системой.\n"
        "\n"
        "[Внимание] Все критические действия (рассылка, бан) запускаются "
        "через соответствующую кнопку."
    )

    await callback.message.edit_text(text=text, reply_markup=keyboards.admin_keyboard)

@router.callback_query(F.data == "admin_stats", config.IsAdmin())
async def admin_stats(callback: CallbackQuery, users_collection) -> None:
    unique_users = await get_total_user_count(users_collection=users_collection)
    average_messages_per_user = await get_average_messages_per_user(users_collection=users_collection)

    average = average_messages_per_user.get("average_messages_per_user")
    active_users = average_messages_per_user.get("unique_users")
    total_messages = average_messages_per_user.get("total_messages")

    stats = (
        "📊 Статистика InnerTalk\n"
        "\n"
        f"👥 Общий Охват: {unique_users:,} (Уникальных ID)\n"
        f"💬 Всего Сообщений: {total_messages:,}\n"
        "\n"
        f"🟢 Активные Пользователи: {active_users:,}\n"
        f"✨ Средняя Активность: {average:.2f} сообщений/пользователя\n"
    )

    await callback.message.edit_text(text=stats, reply_markup=keyboards.back_to_admin_panel)

async def send_single_message(bot, user_id: int, text: str, **kwargs):
    try:
        await bot.send_message(user_id, text, **kwargs)
        await asyncio.sleep(config.RATE_LIMIT_DELAY)
    except Exception as e:
        print(f"❌ Ошибка отправки {user_id}: {e}")


async def get_user_ids(users_collection) -> list[int]:
    projection = {"user_id": 1, "_id": 0}

    cursor = users_collection.find(projection)

    user_ids = []
    async for doc in cursor:
        user_ids.append(doc.get("user_id"))

    return user_ids


async def start_mass_mailing(bot, text: str, admin_id: int, users_collection):
    user_ids = await get_user_ids(users_collection)

    users_sent_count = 0

    for user_id in user_ids:
        asyncio.create_task(send_single_message(bot, user_id, text))
        users_sent_count += 1

    await bot.send_message(admin_id,
                           f"✅ Рассылка успешно инициирована для {users_sent_count} пользователей. "
                           f"Остаток процесса будет выполнен в фоновом режиме.", reply_markup=keyboards.back_to_admin_panel)


@router.callback_query(F.data == "admin_news", config.IsAdmin())
async def process_mailing_start(callback: CallbackQuery, state: FSMContext, users_collection):
    await callback.message.edit_text("Введите текст для рассылки (поддерживается Markdown):")
    await state.set_state(states.MailingStates.waiting_for_text)
    await callback.answer()


@router.message(states.MailingStates.waiting_for_text, F.text)
async def process_mailing_text(message: Message, state: FSMContext, users_collection):
    await state.update_data(mailing_text=message.text)

    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="mailing_confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="mailing_cancel")
        ]
    ])

    await message.answer(
        "Подтверждение:\n\n"
        f"{message.text}\n\n"
        "Вы уверены, что хотите запустить рассылку?",
        reply_markup=confirmation_keyboard
    )
    await state.set_state(states.MailingStates.waiting_for_confirmation)


@router.callback_query(F.data == "mailing_confirm", states.MailingStates.waiting_for_confirmation)
async def process_mailing_confirm(callback: CallbackQuery, state: FSMContext, users_collection):
    data = await state.get_data()
    mailing_text = data.get('mailing_text')
    admin_id = callback.from_user.id

    await state.clear()

    asyncio.create_task(start_mass_mailing(callback.bot, mailing_text, admin_id, users_collection))

    await callback.message.edit_text("✅ Рассылка запущена! Ждите отчета о завершении.")
    await callback.answer()


@router.callback_query(F.data == "mailing_cancel", states.MailingStates.waiting_for_confirmation)
async def process_mailing_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=keyboards.back_to_admin_panel)
    await callback.answer()