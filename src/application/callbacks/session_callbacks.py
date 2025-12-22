import asyncio
import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from google.genai import types

from src import states, config
from src.presentation import keyboards, photos, texts

logger = logging.getLogger(__name__)
router = Router()


async def _save_session_summary_async(collection, session_record):
    try:
        await collection.insert_one(session_record)
    except Exception as e:
        logger.error(f"MongoDB error during summary insertion: {e}")


async def _load_session_history(user_id, users_collection, state: FSMContext, cache=None):
    cache_key = f"session_history:{user_id}"
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached:
            await state.update_data(current_dialog=cached)
            return
    
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
        
        if cache is not None:
            await cache.set(cache_key, initial_history, ttl=600)
        
        await state.update_data(current_dialog=initial_history)
    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке конспекта для {user_id}: {e}")


async def _save_summary_async(session_data, users_collection, generate_content_sync_func, gemini_client,
                              openai_client=None, generate_openai_func=None, alert_func=None, bot=None):
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

    session_summary = "Конспект не был сгенерирован из-за ошибки."

    tried_openai = False
    if openai_client and generate_openai_func:
        tried_openai = True
        for model in ("gpt-4.1-mini", "gpt-5-mini"):
            try:
                joined_dialog = "\n".join([f"{item['role']}: {item['content']}" for item in dialog_for_summary])
                text = await generate_openai_func(openai_client, model, joined_dialog, system_instruction)
                if text and text.strip():
                    session_summary = text
                    logger.info(f"Конспект (OpenAI {model}) сгенерирован для пользователя {user_id}. Длина: {len(session_summary)} символов.")
                    break
            except Exception as e:
                logger.warning(f"OpenAI summary model '{model}' failed: {e}")
        else:
            if alert_func and bot:
                try:
                    await alert_func(bot, f"Сбой конспекта по OpenAI (4.1-mini/5-mini) для user {user_id}. Пробуем Gemini.", key="summary_openai_failed")
                except Exception:
                    pass

    if not tried_openai or (tried_openai and session_summary == "Конспект не был сгенерирован из-за ошибки."):
        try:
            summary_response = await generate_content_sync_func(
                gemini_client,
                'gemini-3-flash-preview',
                dialog_contents,
                system_instruction
            )
            session_summary = summary_response.text
            logger.info(f"Конспект (Gemini) для пользователя {user_id} успешно сгенерирован. Длина: {len(session_summary)} символов.")
        except Exception as e:
            logger.error(f"Gemini error during session summary: {e}")
            if alert_func and bot:
                try:
                    await alert_func(bot, f"Не удалось сгенерировать конспект ни OpenAI, ни Gemini для user {user_id}.", key="summary_all_failed")
                except Exception:
                    pass

    session_record = {
        "user_id": user_id,
        "date": datetime.now(timezone.utc),
        "summary": session_summary,
        "full_dialog_length": real_user_message_count,
        "type": "session_summary"
    }

    try:
        asyncio.create_task(_save_session_summary_async(users_collection, session_record))
    except Exception as e:
        logger.error(f"Error scheduling session summary save: {e}")


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
        logger.warning(f"User {user_id} hit session limit. Count: {sessions_today_count}, Max: {config.MAX_SESSIONS_PER_DAY}")
        await callback.answer(
            f"⚠️ Вы достигли лимита в {config.MAX_SESSIONS_PER_DAY} сессий на сегодня. "
            f"Пожалуйста, попробуйте завтра.",
            show_alert=True
        )
        return

    alert_message = (
        "️️⚠️ Вам доступны лишь 3 сессии в день.\n"
        "После диалога, не забывайте завершать сессию ❤️"
    )

    await callback.answer(text=alert_message, show_alert=True)

    loading_caption = "⏳ Готовлю рабочее пространство...\nЗагружаю предыдущий контекст. Секунду..."

    new_media = InputMediaPhoto(
        media=photos.active_session_photo,
        caption=loading_caption
    )

    try:
        loading_message = await callback.message.edit_media(media=new_media)
        loading_message_id = loading_message.message_id
    except TelegramBadRequest:
        loading_message = await callback.message.answer(loading_caption, reply_markup=None)
        loading_message_id = loading_message.message_id

    cache = getattr(callback.bot, '_cache', None) if hasattr(callback, 'bot') else None
    
    await _load_session_history(
        user_id=callback.from_user.id,
        users_collection=users_collection,
        state=state,
        cache=cache
    )

    try:
        data = await state.get_data()
        ai_style_present = data.get("ai_style")
        if not ai_style_present:
            profile = await users_collection.find_one({"user_id": callback.from_user.id, "type": "user_profile"})
            pref = None
            if profile:
                pref = profile.get("preferred_style")
            if pref in ("empathy", "action", "default"):
                await state.update_data(ai_style=pref)
            else:
                await state.update_data(ai_style="default")
    except Exception as e:
        logger.error(f"Не удалось загрузить preferred_style: {e}")

    start_caption = (
        "🎉 Сессия начата! Я слушаю тебя. Помни, что сессия ограничена объемом "
        f"~{config.MAX_TOKENS_PER_SESSION} токенов для контроля расходов. \n"
        "Этого хватит сполна даже на очень большие и затяжные диалоги! \n"
        "Удачного вам диалога! 😊\n"
        "Помните, что я здесь для того, чтобы поддержать вас. "
        "Говорите свободно, я слушаю внимательно. "
        "Нажмите кнопку ниже, когда будете готовы закончить сессию."
    )

    new_media = InputMediaPhoto(
        media=photos.active_session_photo,
        caption=start_caption
    )

    try:
        await callback.message.edit_media(media=new_media)
    except TelegramBadRequest:
        await callback.message.answer(start_caption, reply_markup=keyboards.end_session_menu)

    await state.set_state(states.SessionStates.in_session)
    await state.update_data(
        last_ai_message_id=callback.message.message_id,
        real_user_message_count=0
    )


@router.callback_query(F.data == "end_session", StateFilter(states.SessionStates.in_session))
async def end_session_handler(callback: CallbackQuery, state: FSMContext, users_collection, generate_content_sync_func,
                              gemini_client, openai_client=None, generate_openai_func=None, alert_func=None) -> None:
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
            reply_markup=keyboards.main_menu
        )

        await callback.answer()
        return

    processing_text = "📝 Создаю конспект и завершаю сессию..."
    processing_message = await callback.message.answer(text=processing_text)

    session_data = {
        "user_id": user_id,
        "full_dialog": full_dialog,
        "real_user_message_count": real_user_message_count
    }

    await _save_summary_async(
        session_data,
        users_collection,
        generate_content_sync_func,
        gemini_client,
        openai_client=openai_client,
        generate_openai_func=generate_openai_func,
        alert_func=alert_func,
        bot=callback.bot
    )

    final_text = (
        f"✅ Сессия завершена! "
        f"Вы обменялись {real_user_message_count} сообщениями.\n"
        f"📝 Конспект сохранен."
    )

    try:
        await processing_message.edit_text(text=final_text)
    except TelegramBadRequest:
        await callback.message.answer(text=final_text)

    data = await state.get_data()
    saved_style = data.get("ai_style", "default")

    await state.set_state(states.SessionStates.idle)
    await state.set_data({"ai_style": saved_style})

    caption_text = texts.MAIN_MENU_CAPTION

    await callback.message.answer_photo(
        photo=photos.main_photo,
        caption=caption_text,
        reply_markup=keyboards.main_menu
    )

    await callback.answer()
