import asyncio
import logging
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from google.genai import types

from src import config
from src.presentation import keyboards, photos
from src.utils.portrait_utils import sanitize_portrait_text, update_portrait_caption_animation

logger = logging.getLogger(__name__)
router = Router()

ERROR_MESSAGES = [
    "Ошибка генерации портрета. Попробуйте позже.",
    "К сожалению, в базе данных не найдено достаточно сообщений для анализа.",
    "Произошла критическая ошибка в системе. Ваш лимит не был исчерпан. Попробуйте, пожалуйста, снова."
]


async def _generate_portrait_async(user_id, users_collection, generate_content_sync_func, gemini_client,
                                   openai_client=None, generate_openai_func=None, alert_func=None, bot=None):
    portrait_prompt_template = (
        "ТЫ — профессиональный аналитик, специализирующийся на формировании психологического портрета и стиля общения на основе текстовых данных. Твоя задача — проанализировать представленный ниже текст, который является диалогами пользователя.\n\n"
        "ТВОЙ АНАЛИЗ ДОЛЖЕН СОДЕРЖАТЬ СЛЕДУЮЩИЕ РАЗДЕЛЫ:\n"
        "1.  ОБЩИЙ ЭМОЦИОНАЛЬНЫЙ ФОН: Какие преобладающие эмоции прослеживаются в сообщениях (тревога, неуверенность, стремление к контролю, оптимизм и т.д.)?\n"
        "2.  ПАТТЕРНЫ МЫШЛЕНИЯ И РЕАКЦИЙ: Какие повторяющиеся темы, установки, когнитивные искажения (например, \"все или ничего\", катастрофизация, сверхобобщение) или защитные механизмы можно отметить?\n"
        "3.  СТИЛЬ ОБЩЕНИЯ: Насколько сообщения детальные, эмоционально окрашенные, структурированные, склонны ли к самокопанию или, наоборот, поверхностны?\n"
        "4.  КЛЮЧЕВЫЕ ПОТРЕБНОСТИ/ЦЕННОСТИ: Какие фундаментальные потребности или ценности (например, безопасность, признание, самореализация, отношения) являются наиболее актуальными для этого человека.\n"
        "5.  СОВЕТ ОТ ИИ-ПСИХОЛОГА: Дай одну поддерживающую, фокусирующуюся на сильных сторонах и конструктивную рекомендацию.\n\n"
        "ФОРМАТИРОВАНИЕ:\n"
        "* Оформи ответ в виде связного, профессионального текста с нормальной детализацией. НЕ ограничивай длину специально — она будет показана постранично.\n"
        "* Пиши ЧИСТЫМ ТЕКСТОМ без Markdown/разметки (не используй **жирный**, списки с маркерами, кавычки форматирования и т.п.).\n"
        "* Отвечай исключительно на РУССКОМ языке.\n"
        "* Запрещены любые заглушки/примеры вроде 'example text', 'пример текста', 'template', '[...]'. Пиши только фактический анализ.\n"
        "* НИ ПРИ КАКИХ УСЛОВИЯХ НЕ ОТВЕЧАЙ ФРАЗАМИ ТИПА \"Я НЕ СПЕЦИАЛИСТ\" ИЛИ \"ОБРАТИТЕСЬ К ПРОФЕССИОНАЛУ\". Твоя роль — дать анализ.\n\n"
        "ИСТОРИЯ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ:\n---\n{dialog_text}\n---"
    )

    user_messages_cursor = users_collection.find(
        {"user_id": user_id, "type": "user_message"},
        {"text": 1, "username": 1, "_id": 0}
    ).sort("timestamp", 1).limit(500)

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

    portrait_contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=summary_prompt)]
        )
    ]

    portrait_result = ERROR_MESSAGES[0]

    if openai_client and generate_openai_func:
        for model in ("gpt-5.2", "gpt-5.1"):
            try:
                text = await generate_openai_func(openai_client, model, summary_prompt, None)
                if text and isinstance(text, str) and len(text.strip()) > 0:
                    return text
            except Exception as e:
                logger.warning(f"OpenAI model '{model}' failed: {e}")
                continue
    else:
        if alert_func and bot:
            try:
                await alert_func(bot, "Портрет недоступен: отсутствует OPENAI_API_KEY или клиент OpenAI не инициализирован.", key="portrait_no_openai")
            except Exception:
                pass

    if alert_func and bot:
        try:
            await alert_func(bot, f"Сбой генерации портрета у пользователя {user_id}: обе модели OpenAI (gpt-5.2/5.1) не ответили.", key="portrait_failed")
        except Exception:
            pass
    return portrait_result


def _split_into_pages(text: str, max_len: int = 1000) -> list[str]:
    pages = []
    text_left = text
    while text_left:
        chunk = text_left[:max_len]
        if len(text_left) > max_len:
            last_nl = chunk.rfind("\n")
            last_space = chunk.rfind(" ")
            cut_at = max(last_nl, last_space)
            if cut_at > 200:
                chunk = chunk[:cut_at]
        pages.append(chunk)
        text_left = text_left[len(chunk):]
    return pages


@router.callback_query(F.data == "get_portrait")
async def get_portrait_handler(callback: CallbackQuery, users_collection, generate_content_sync_func, gemini_client,
                               state: FSMContext, bot, openai_client=None, generate_openai_func=None, alert_func=None) -> None:
    user_id = callback.from_user.id
    current_time = datetime.now(timezone.utc)

    data_now = await state.get_data()
    if data_now.get("portrait_loading"):
        await callback.answer("Анализ уже выполняется, пожалуйста подождите…", show_alert=False)
        return
    last_req = data_now.get("last_portrait_req_ts")
    if isinstance(last_req, datetime):
        if (current_time - last_req).total_seconds() < 10:
            await callback.answer("Не так быстро, пожалуйста 🙂", show_alert=False)
            return
    await state.update_data(last_portrait_req_ts=current_time)

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

            last_portrait_doc = await users_collection.find_one(
                {"user_id": user_id, "type": "portrait"},
                sort=[("generated_at", -1)]
            )
            
            if last_portrait_doc and last_portrait_doc.get("portrait_text"):
                portrait_text = last_portrait_doc.get("portrait_text", "")
                generated_at = last_portrait_doc.get("generated_at")
                
                cooldown_info = (
                    f"⚠️ Психологический портрет можно создавать не чаще, чем раз в {config.PORTRAIT_COOLDOWN_HOURS} часа.\n"
                    f"Повторная попытка будет доступна через {hours} ч. {minutes} мин.\n\n"
                )
                
                if generated_at:
                    date_str = generated_at.strftime("%d.%m.%Y в %H:%M")
                    cooldown_info += f"📅 Последний портрет был сгенерирован {date_str} (UTC)\n\n"
                
                cooldown_info += "---\n\n"
                header = "Ваш Психологический Портрет: 🧠\n\n"
                full_text = f"{cooldown_info}{header}{portrait_text}"
                
                pages = _split_into_pages(full_text)
                total_pages = max(1, len(pages))
                current_page = 1
                
                await state.update_data(
                    portrait_pages=pages,
                    portrait_page_idx=current_page,
                    portrait_message_id=callback.message.message_id
                )
                
                new_media = InputMediaPhoto(
                    media=photos.portrait_photo,
                    caption=pages[0] if pages else full_text
                )
                
                try:
                    await callback.message.edit_media(
                        media=new_media,
                        reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
                    )
                except TelegramBadRequest:
                    try:
                        await callback.message.edit_caption(
                            caption=pages[0] if pages else full_text,
                            reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
                        )
                    except TelegramBadRequest:
                        await callback.message.answer_photo(
                            photo=photos.portrait_photo,
                            caption=pages[0] if pages else full_text,
                            reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
                        )
            else:
                await callback.answer(
                    f"⚠️ Психологический портрет можно создавать не чаще, чем раз в {config.PORTRAIT_COOLDOWN_HOURS} часа. "
                    f"Повторная попытка будет доступна через {hours} ч. {minutes} мин.",
                    show_alert=True
                )
            
            await callback.answer()
            return

    alert_message = (
        "⚠️ Функция Анализа Личности доступна лишь 1 раз за 24 часа!\n"
        "Точность психологического портрета напрямую зависит от количества сообщений за все сессии 🌟."
    )

    await callback.answer(text=alert_message, show_alert=True)

    initial_caption = "⏳ Начинаю анализ..."
    new_media = InputMediaPhoto(
        media=photos.portrait_photo,
        caption=initial_caption
    )

    try:
        message_to_edit = await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.back_to_menu_keyboard
        )
    except TelegramBadRequest:
        message_to_edit = await callback.message.edit_caption(
            caption=initial_caption,
            reply_markup=keyboards.back_to_menu_keyboard
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
            gemini_client=gemini_client,
            openai_client=openai_client,
            generate_openai_func=generate_openai_func,
            alert_func=alert_func,
            bot=bot
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
        cleaned_portrait = sanitize_portrait_text(portrait_result)
        async def _save_portrait_data():
            try:
                await users_collection.insert_one({
                    "user_id": user_id,
                    "type": "portrait",
                    "portrait_text": cleaned_portrait,
                    "generated_at": current_time
                })
                await users_collection.update_one(
                    {"user_id": user_id, "type": "user_profile"},
                    {"$set": {"last_portrait_timestamp": current_time}},
                    upsert=True
                )
                logger.info(f"Portrait saved to DB for user {user_id}")
            except Exception as e:
                logger.error(f"Ошибка сохранения портрета в БД: {e}")
        
        asyncio.create_task(_save_portrait_data())
        logger.info(f"User {user_id} successfully generated portrait. Cooldown applied.")
    else:
        logger.warning(f"User {user_id} failed to generate portrait: {portrait_result}. Cooldown skipped.")

    await state.update_data(portrait_loading=False, loading_message_id=None)

    header = "Ваш Психологический Портрет: 🧠\n\n" if is_successful_generation else ""
    if is_successful_generation:
        last_portrait_doc = await users_collection.find_one(
            {"user_id": user_id, "type": "portrait"},
            sort=[("generated_at", -1)]
        )
        if last_portrait_doc and last_portrait_doc.get("portrait_text"):
            cleaned_portrait = last_portrait_doc.get("portrait_text")
        else:
            cleaned_portrait = sanitize_portrait_text(portrait_result)
    else:
        cleaned_portrait = portrait_result
    full_text = f"{header}{cleaned_portrait}" if cleaned_portrait else (ERROR_MESSAGES[0])

    pages = _split_into_pages(full_text)
    total_pages = max(1, len(pages))
    current_page = 1

    await state.update_data(
        portrait_pages=pages,
        portrait_page_idx=current_page,
        portrait_message_id=message_to_edit.message_id
    )

    try:
        await message_to_edit.edit_caption(
            caption=pages[0] if pages else full_text,
            reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit final caption after portrait generation: {e}")
        await callback.message.answer_photo(
            photo=photos.portrait_photo,
            caption=pages[0] if pages else full_text,
            reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
        )


@router.callback_query(F.data.startswith("portrait_page:"))
async def portrait_pagination_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pages = data.get("portrait_pages", [])
    msg_id = data.get("portrait_message_id")
    try:
        requested = int(callback.data.split(":")[1])
    except Exception:
        await callback.answer()
        return

    if not pages:
        await callback.answer()
        return
    total_pages = len(pages)
    if requested < 1 or requested > total_pages:
        await callback.answer()
        return

    await state.update_data(portrait_page_idx=requested)
    try:
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=msg_id or callback.message.message_id,
            caption=pages[requested - 1],
            reply_markup=keyboards.portrait_pagination_keyboard(requested, total_pages)
        )
    except TelegramBadRequest as e:
        await callback.message.answer(
            text=pages[requested - 1],
            reply_markup=keyboards.portrait_pagination_keyboard(requested, total_pages)
        )
    await callback.answer()
