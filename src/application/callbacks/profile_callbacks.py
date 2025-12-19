import asyncio
import logging
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest

from src import states, config
from src.presentation import keyboards, photos, texts
from src.application.handlers import _save_to_db_async

logger = logging.getLogger(__name__)
router = Router()


async def update_stats_caption_animation(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "📊 Собираю все оценки прогресса...",
        "🧠 Вычисляю средний балл...",
        "📈 Анализирую тенденции за последний месяц...",
        "💡 Формулирую финальные выводы..."
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
                        caption=text_frame
                    )
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e).lower():
                        return
                await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in update_stats_caption_animation: {e}")


async def _get_user_stats_async(user_id, users_collection):
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

    avg_latest_n = average_score
    if total_scores >= 2:
        last_n = min(5, total_scores)
        avg_latest_n = sum(numeric_scores[:last_n]) / last_n

    return numeric_scores, total_scores, average_score, latest_timestamp, avg_latest_n


@router.callback_query(F.data == "get_profile")
async def get_profile_handler(callback: CallbackQuery) -> None:
    await callback.message.answer("Функция 'Профиль' в разработке. Скоро ИИ сделает ваш психологический портрет!")
    await callback.answer()


@router.callback_query(F.data == "start_progress_scale", StateFilter(states.SessionStates.idle, None, states.OnboardingStates.step3))
async def start_progress_scale_handler(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    user_id = callback.from_user.id
    current_time = datetime.now(timezone.utc)
    try:
        cur_state = await state.get_state()
        if cur_state == states.OnboardingStates.step3:
            await state.update_data(onboarding_back_to_step3=True)
        else:
            await state.update_data(onboarding_back_to_step3=False)
    except Exception:
        pass

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
        "📈 Шкала прогресса\n\n"
        "Как вы оцениваете свое текущее состояние или прогресс в решении проблемы?\n\n"
        "По шкале от 1 до 10 👨🏼‍⚕️"
    )

    new_media = InputMediaPhoto(
        media=photos.progress_scale_photo,
        caption=caption_text
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.progress_scale_menu
        )
    except TelegramBadRequest as e:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.progress_scale_menu
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

    try:
        asyncio.create_task(_save_to_db_async(users_collection, {
            "user_id": user_id,
            "type": "progress_score",
            "score": score,
            "timestamp": current_time,
        }))
    except Exception as e:
        logger.error(f"Error scheduling score save: {e}")

    filled = "🟢" * score
    empty = "⚪" * (10 - score)
    progress_bar = f"{filled}{empty}"

    final_caption = (
        f"✅ Отлично! Ваша оценка сохранена.\n\n"
        f"Текущий прогресс: {progress_bar} ({score}/10)\n\n"
        "Чем чаще вы оцениваете прогресс, тем лучше видите свой путь. Нажмите кнопку, чтобы вернуться к основным функциям."
    )

    data = await state.get_data()
    if data.get("onboarding_back_to_step3"):
        try:
            await callback.message.edit_caption(
                caption=texts.ONBOARDING_STEP3,
                reply_markup=keyboards.onboarding_step3
            )
        except TelegramBadRequest as e:
            logger.warning(f"Failed to return to onboarding step3 after score: {e}")
            await callback.message.answer(texts.ONBOARDING_STEP3, reply_markup=keyboards.onboarding_step3)
        await state.set_state(states.OnboardingStates.step3)
        await state.update_data(onboarding_back_to_step3=False)
        await callback.answer("Ваша оценка сохранена!")
    else:
        try:
            await callback.message.edit_caption(
                caption=final_caption,
                reply_markup=keyboards.back_to_menu_keyboard
            )
        except TelegramBadRequest as e:
            logger.error(f"Failed to edit caption after score: {e}")
            await callback.message.answer(
                text=final_caption,
                reply_markup=keyboards.back_to_menu_keyboard
            )
        await state.set_state(states.SessionStates.idle)
        await callback.answer("Ваша оценка сохранена!")


@router.callback_query(F.data == "start_style_selection", StateFilter(states.SessionStates.idle, None, states.OnboardingStates.step3))
async def start_style_selection_handler(callback: CallbackQuery, state: FSMContext) -> None:
    caption_text = (
        "⚙️ Настройка акцента для сессии\n\n"
        "Выберите, какой тип поддержки вам нужен прямо сейчас:\n\n"
        "🤗 Эмпатия: Больше поддержки, сочувствия и валидации чувств.\n"
        "🛠️ Практика: Больше конкретных шагов, задач и фокуса на решении.\n\n"
        "Этот акцент будет применен к вашей следующей сессии (кнопка 'Начать разговор')."
    )

    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=caption_text
    )

    try:
        cur_state = await state.get_state()
        if cur_state == states.OnboardingStates.step3:
            await state.update_data(onboarding_back_to_step3=True)
        else:
            await state.update_data(onboarding_back_to_step3=False)
    except Exception:
        pass

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.style_selection_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.style_selection_menu
        )

    await callback.answer("Выберите акцент...")


@router.callback_query(F.data.startswith("set_style:"))
async def style_selector_handler(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    style_code = callback.data.split(":")[1]

    await state.update_data(ai_style=style_code)

    async def _save_style():
        try:
            if style_code == "default":
                await users_collection.update_one(
                    {"user_id": callback.from_user.id, "type": "user_profile"},
                    {"$unset": {"preferred_style": ""}},
                    upsert=True
                )
            else:
                await users_collection.update_one(
                    {"user_id": callback.from_user.id, "type": "user_profile"},
                    {"$set": {"preferred_style": style_code}},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Ошибка сохранения preferred_style: {e}")
    
    asyncio.create_task(_save_style())

    if style_code == 'empathy':
        style_text = "🤗 Эмпатия и Поддержка"
    elif style_code == 'action':
        style_text = "🛠️ Практика и Действие"
    else:
        style_text = "Стандартный режим SFBT"

    confirmation_text = (
        f"✅ Акцент установлен!\n\n"
        f"Текущий стиль: {style_text}\n\n"
        "Нажмите '🎉 Начать разговор', чтобы начать сессию с этим акцентом."
        if style_code != "default" else
        "♻️ Акцент сброшен к стандартному режиму.\n\nНажмите '🎉 Начать разговор', чтобы продолжить."
    )

    data = await state.get_data()
    if data.get("onboarding_back_to_step3"):
        try:
            await callback.message.edit_caption(
                caption=texts.ONBOARDING_STEP3,
                reply_markup=keyboards.onboarding_step3
            )
        except TelegramBadRequest as e:
            await callback.message.answer(
                text=texts.ONBOARDING_STEP3,
                reply_markup=keyboards.onboarding_step3
            )
            logger.warning(f"Failed to return to onboarding step3 after style selection: {e}")
        await state.set_state(states.OnboardingStates.step3)
        await state.update_data(onboarding_back_to_step3=False)
        await callback.answer("Акцент сохранён для следующей сессии!")
    else:
        try:
            await callback.message.edit_caption(
                caption=confirmation_text,
                reply_markup=keyboards.back_to_menu_keyboard
            )
        except TelegramBadRequest as e:
            await callback.message.answer(
                text=confirmation_text,
                reply_markup=keyboards.back_to_menu_keyboard
            )
            logger.warning(f"Failed to edit message after style selection, sending new: {e}")
        await callback.answer("Акцент сохранён!")


@router.callback_query(F.data == "reset_style")
async def reset_style_handler(callback: CallbackQuery, state: FSMContext, users_collection):
    await state.update_data(ai_style="default")
    async def _reset_style():
        try:
            await users_collection.update_one(
                {"user_id": callback.from_user.id, "type": "user_profile"},
                {"$unset": {"preferred_style": ""}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Ошибка сброса preferred_style: {e}")
    
    asyncio.create_task(_reset_style())

    text = (
        "♻️ Акцент сброшен к стандартному режиму.\n\n"
        "Чтобы снова выбрать акцент, откройте '⚙️ Настройка акцента'."
    )
    try:
        await callback.message.edit_caption(caption=text, reply_markup=keyboards.back_to_menu_keyboard)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=keyboards.back_to_menu_keyboard)
    await callback.answer("Сброшено")


@router.callback_query(F.data == "get_user_stats")
async def get_stats_handler(callback: CallbackQuery, users_collection, state: FSMContext, bot) -> None:
    user_id = callback.from_user.id

    await callback.answer("Собираем вашу статистику...")

    initial_caption = "⏳ Начинаю сбор статистики..."
    new_media = InputMediaPhoto(
        media=photos.stats_photo,
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
            "😔 Статистика недоступна\n\n"
            "Вы еще не оценили свой прогресс ни разу. Начните с '📈 Дневник эмоции'!"
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
                trend_status = "заметно улучшился"
                trend_icon = "🚀"
            elif diff_percent < -0.05:
                trend_status = "снизился"
                trend_icon = "⬇️"
            else:
                trend_status = "стабилен"
                trend_icon = "⚖️"

            trend_line = f"Тенденция за последние {last_n} оценок: {trend_icon} Прогресс {trend_status}."

        final_caption = (
            "📊 Ваша персональная статистика\n\n"
            "---"
            "\n\n✅ Оценки прогресса"
            f"\n- Всего оценок: {total_scores}"
            f"\n- Последняя оценка: {latest_score}/10 (от {latest_timestamp.strftime('%d.%m.%Y')})"
            f"\n- Средняя оценка: {average_score:.2f}/10"
            f"\n\n{trend_line}"
            f"\n\n---"
            f"\n\n📝 Рекомендация: отмечайте, что изменилось между высоким и низким баллом, чтобы увидеть свои точки роста."
        )
    try:
        await message_to_edit.edit_caption(
            caption=final_caption,
            reply_markup=keyboards.back_to_menu_keyboard
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit final caption after stats generation: {e}")
        await callback.message.answer(
            final_caption,
            reply_markup=keyboards.back_to_menu_keyboard
        )

