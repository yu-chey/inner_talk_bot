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
from . import states
from . import config
from .handlers import _save_to_db_async
from . import tests_data

logger = logging.getLogger(__name__)


def _sanitize_portrait_text(text: str) -> str:
    """Очищает результат портрета от Markdown и шаблонных вставок.

    - удаляет **, __, *, _, `, #
    - заменяет маркеры списков на «- »
    - удаляет фразы-заглушки вроде "example text", "пример текста", "template"
    - нормализует подряд идущие пустые строки до максимум двух
    """
    if not isinstance(text, str):
        return ""
    s = text
    for m in ("**", "__", "*", "_", "`"):
        s = s.replace(m, "")
    s = "\n".join(line.lstrip("# ") for line in s.splitlines())
    s = s.replace("•", "- ").replace("–", "-")
    lowers = ["example text", "template", "placeholder", "пример текста", "пример", "заглушка"]
    for token in lowers:
        s = s.replace(token, "")
        s = s.replace(token.title(), "")
        s = s.replace(token.upper(), "")
    lines = [ln.rstrip() for ln in s.splitlines()]
    cleaned = []
    empty_streak = 0
    for ln in lines:
        if ln.strip() == "":
            empty_streak += 1
            if empty_streak <= 2:
                cleaned.append("")
        else:
            empty_streak = 0
            cleaned.append(ln)
    s = "\n".join(cleaned).strip()
    return s

router = Router()

ERROR_MESSAGES = [
    "Ошибка генерации портрета. Попробуйте позже.",
    "К сожалению, в базе данных не найдено достаточно сообщений для анализа.",
    "Произошла критическая ошибка в системе. Ваш лимит не был исчерпан. Попробуйте, пожалуйста, снова."
]

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    caption_text = texts.MAIN_MENU_CAPTION
    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=caption_text
    )
    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.main_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.main_menu
        )
    await callback.answer()


async def update_portrait_caption_animation(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "👂 Внимательно слушаю вашу историю...",
        "🧠 Сканирую ключевые слова и эмоции...",
        "📊 Ищу повторяющиеся паттерны...",
        "🔬 Анализирую когнитивные искажения...",
        "⚖️ Взвешиваю потребности и ценности...",
        "💡 Формулирую финальный совет..."
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
                        caption=text_frame
                    )
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e):
                        return

                await asyncio.sleep(delay)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in update_portrait_caption_animation: {e}")


@router.callback_query(F.data == "onb_next_1", StateFilter(states.OnboardingStates.step1))
async def onboarding_next_1(callback: CallbackQuery, state: FSMContext):
    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=texts.ONBOARDING_STEP2
    )
    try:
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.onboarding_step2)
    except TelegramBadRequest:
        await callback.message.edit_caption(caption=texts.ONBOARDING_STEP2, reply_markup=keyboards.onboarding_step2)
    await state.set_state(states.OnboardingStates.step2)
    await callback.answer()


def _likert_options() -> list[tuple[str, str]]:
    return [("1", "test_answer:1"), ("2", "test_answer:2"), ("3", "test_answer:3"), ("4", "test_answer:4"), ("5", "test_answer:5")]


def _mbti_options() -> list[tuple[str, str]]:
    return [("A", "test_answer:A"), ("B", "test_answer:B")]


async def _edit_prev_remove_end(bot, chat_id: int, message_id: int, q) -> None:
    try:
        if q.qtype == "likert":
            kb = keyboards.question_keyboard(_likert_options(), show_end=False)
        elif q.qtype == "mbti_ab":
            kb = keyboards.question_keyboard(_mbti_options(), show_end=False)
        else:
            kb = None
        if kb:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.debug(f"edit prev remove end failed: {e}")
    except Exception as e:
        logger.debug(f"edit prev remove end failed: {e}")


async def _send_question(callback: CallbackQuery, state: FSMContext, *, first: bool = False) -> None:
    data = await state.get_data()
    test_id: str = data.get("test_id")
    version: str = data.get("version")
    idx: int = data.get("current_index", 0)
    questions = tests_data.TESTS[test_id]["versions"][version]
    total = len(questions)
    q = questions[idx]

    prev_msg_id = data.get("last_question_message_id")
    if not first and prev_msg_id:
        await _edit_prev_remove_end(callback.message.bot, callback.message.chat.id, prev_msg_id, q=questions[idx-1])

    if q.qtype == "likert":
        options = _likert_options()
        hint = f"\n\n{texts.TESTS_LIKERT_HINT}"
    else:
        options = _mbti_options()
        hint = ""
    kb = keyboards.question_keyboard(options, show_end=True)

    sent = await callback.message.answer(f"Вопрос {idx+1}/{total}:\n{q.text}{hint}", reply_markup=kb)
    await state.update_data(last_question_message_id=sent.message_id)


@router.callback_query(F.data == "tests_menu")
async def tests_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(states.TestStates.disclaimer)
    await callback.message.edit_caption(caption=texts.TESTS_DISCLAIMER, reply_markup=keyboards.tests_disclaimer_keyboard())
    await callback.answer()


@router.callback_query(F.data == "tests_consent", StateFilter(states.TestStates.disclaimer))
async def tests_consent(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(states.TestStates.picking_test)
    await callback.message.edit_caption(caption=texts.TESTS_INTRO, reply_markup=keyboards.tests_pick_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("test_pick:"), StateFilter(states.TestStates.picking_test))
async def test_pick(callback: CallbackQuery, state: FSMContext) -> None:
    test_id = callback.data.split(":", 1)[1]
    if test_id not in tests_data.TESTS:
        await callback.answer("Неизвестный тест", show_alert=True)
        return
    await state.update_data(test_id=test_id)
    await state.set_state(states.TestStates.picking_length)
    await callback.message.edit_caption(caption=f"Тест: {tests_data.TESTS[test_id]['title']}\nВыберите версию:", reply_markup=keyboards.tests_length_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("test_len:"), StateFilter(states.TestStates.picking_length))
async def test_len(callback: CallbackQuery, state: FSMContext) -> None:
    version = callback.data.split(":", 1)[1]
    data = await state.get_data()
    test_id = data.get("test_id")
    if not test_id or test_id not in tests_data.TESTS:
        await callback.answer("Ошибка выбора теста", show_alert=True)
        return
    if version not in tests_data.TESTS[test_id]["versions"]:
        await callback.answer("Неизвестная версия", show_alert=True)
        return
    await state.update_data(version=version, current_index=0, answers=[], last_question_message_id=None, test_started_at=datetime.now(timezone.utc))
    await state.set_state(states.TestStates.in_test)
    # Первый вопрос отправляем новым сообщением (не меняем медиа)
    await _send_question(callback, state, first=True)
    await callback.answer()


@router.callback_query(F.data.startswith("test_answer:"), StateFilter(states.TestStates.in_test))
async def test_answer(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    test_id: str = data.get("test_id")
    version: str = data.get("version")
    idx: int = data.get("current_index", 0)
    answers: list = data.get("answers", [])
    questions = tests_data.TESTS[test_id]["versions"][version]

    answers.append(val)
    idx += 1
    await state.update_data(answers=answers, current_index=idx)

    if idx >= len(questions):
        result = tests_data.compute_result(test_id, version, answers)
        record = {
            "user_id": callback.from_user.id,
            "type": "test_result",
            "test_id": test_id,
            "test_title": tests_data.TESTS[test_id]["title"],
            "version": version,
            "started_at": data.get("test_started_at"),
            "finished_at": datetime.now(timezone.utc),
            "answers": answers,
            "result": result,
        }
        try:
            await users_collection.insert_one(record)
        except Exception as e:
            logger.error(f"MongoDB error saving test result: {e}")

        verdict_text = result.get("verdict", "Результаты обработаны.")
        await callback.message.answer(
            f"✅ Тест завершён!\n\n{verdict_text}",
            reply_markup=keyboards.back_to_menu_keyboard
        )
        await state.clear()
        await callback.answer()
        return

    await _send_question(callback, state)
    await callback.answer()


@router.callback_query(F.data == "end_test", StateFilter(states.TestStates.in_test))
async def end_test(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    caption_text = texts.MAIN_MENU_CAPTION
    try:
        new_media = InputMediaPhoto(
            media=photos.main_photo,
            caption=caption_text
        )
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.main_menu)
    except TelegramBadRequest:
        try:
            await callback.message.edit_caption(caption=caption_text, reply_markup=keyboards.main_menu)
        except TelegramBadRequest:
            await callback.message.answer_photo(photo=photos.main_photo, caption=caption_text, reply_markup=keyboards.main_menu)
    await callback.answer("Тест завершён. Данные не сохранены.")


@router.callback_query(F.data == "onb_next_2", StateFilter(states.OnboardingStates.step2))
async def onboarding_next_2(callback: CallbackQuery, state: FSMContext):
    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=texts.ONBOARDING_STEP3
    )
    try:
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.onboarding_step3)
    except TelegramBadRequest:
        await callback.message.edit_caption(caption=texts.ONBOARDING_STEP3, reply_markup=keyboards.onboarding_step3)
    await state.set_state(states.OnboardingStates.step3)
    await callback.answer()


async def _finish_onboarding(callback: CallbackQuery, users_collection, state: FSMContext):
    user_id = callback.from_user.id
    try:
        await users_collection.update_one(
            {"user_id": user_id, "type": "user_profile"},
            {"$set": {"onboarding_completed": True}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Ошибка обновления статуса онбординга: {e}")

    await state.set_state(states.SessionStates.idle)
    caption_text = texts.MAIN_MENU_CAPTION
    new_media = InputMediaPhoto(media=photos.main_photo, caption=caption_text)
    try:
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.main_menu)
    except TelegramBadRequest:
        await callback.message.edit_caption(caption=caption_text, reply_markup=keyboards.main_menu)
    await callback.answer()


@router.callback_query(F.data == "onb_finish", StateFilter(states.OnboardingStates.step3))
async def onboarding_finish(callback: CallbackQuery, users_collection, state: FSMContext):
    await _finish_onboarding(callback, users_collection, state)


@router.callback_query(F.data == "onb_skip", StateFilter(states.OnboardingStates.step1, states.OnboardingStates.step2, states.OnboardingStates.step3))
async def onboarding_skip(callback: CallbackQuery, users_collection, state: FSMContext):
    await _finish_onboarding(callback, users_collection, state)

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
                    if "message is not modified" not in str(e):
                        return

                await asyncio.sleep(delay)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in update_stats_caption_animation: {e}")


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
                    logger.info(
                        f"Конспект (OpenAI {model}) сгенерирован для пользователя {user_id}. Длина: {len(session_summary)} символов.")
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
                'gemini-2.5-flash',
                dialog_contents,
                system_instruction
            )
            session_summary = summary_response.text
            logger.info(
                f"Конспект (Gemini) для пользователя {user_id} успешно сгенерирован. Длина: {len(session_summary)} символов.")
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
            caption=caption_text
        )
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.main_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.main_menu
        )

    await callback.answer()


@router.callback_query(F.data == "about_us")
async def about_us_handler(callback: CallbackQuery) -> None:
    caption_text = texts.ABOUT_US_CAPTION
    new_media = InputMediaPhoto(
        media=photos.about_us_photo,
        caption=caption_text
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.about_us_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.about_us_menu
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
        loading_message = await callback.message.edit_media(
            media=new_media
        )
        loading_message_id = loading_message.message_id
    except TelegramBadRequest:
        loading_message = await callback.message.answer(loading_caption, reply_markup=None)
        loading_message_id = loading_message.message_id

    await _load_session_history(
        user_id=callback.from_user.id,
        users_collection=users_collection,
        state=state
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
        await callback.message.edit_media(
            media=new_media
        )
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


@router.callback_query(F.data == "get_profile")
async def get_profile_handler(callback: CallbackQuery) -> None:
    await callback.message.answer("Функция 'Профиль' в разработке. Скоро ИИ сделает ваш психологический портрет!")
    await callback.answer()


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

            await callback.answer(
                f"⚠️ Психологический портрет можно создавать не чаще, чем раз в {config.PORTRAIT_COOLDOWN_HOURS} часа. "
                f"Повторная попытка будет доступна через {hours} ч. {minutes} мин.",
                show_alert=True
            )
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
        await users_collection.update_one(
            {"user_id": user_id, "type": "user_profile"},
            {"$set": {"last_portrait_timestamp": current_time}},
            upsert=True
        )
        logger.info(f"User {user_id} successfully generated portrait. Cooldown applied.")
    else:
        logger.warning(f"User {user_id} failed to generate portrait: {portrait_result}. Cooldown skipped.")

    await state.update_data(portrait_loading=False, loading_message_id=None)

    header = "Ваш Психологический Портрет: 🧠\n\n" if is_successful_generation else ""
    cleaned_portrait = _sanitize_portrait_text(portrait_result) if is_successful_generation else portrait_result
    full_text = f"{header}{cleaned_portrait}" if cleaned_portrait else (ERROR_MESSAGES[0])

    max_page_len = 1000
    pages = []
    text_left = full_text
    while text_left:
        chunk = text_left[:max_page_len]
        if len(text_left) > max_page_len:
            last_nl = chunk.rfind("\n")
            last_space = chunk.rfind(" ")
            cut_at = max(last_nl, last_space)
            if cut_at > 200:
                chunk = chunk[:cut_at]
        pages.append(chunk)
        text_left = text_left[len(chunk):]

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


@router.callback_query(F.data == "call_support")
async def call_support_handler(callback: CallbackQuery) -> None:
    caption_text = texts.SUPPORT_CAPTION

    new_media = InputMediaPhoto(
        media=photos.support_photo,
        caption=caption_text
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.support_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.support_menu
        )

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
    try:
        await users_collection.update_one(
            {"user_id": callback.from_user.id, "type": "user_profile"},
            {"$unset": {"preferred_style": ""}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Ошибка сброса preferred_style: {e}")

    text = (
        "♻️ Акцент сброшен к стандартному режиму.\n\n"
        "Чтобы снова выбрать акцент, откройте '⚙️ Настройка акцента'."
    )
    try:
        await callback.message.edit_caption(caption=text, reply_markup=keyboards.back_to_menu_keyboard)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=keyboards.back_to_menu_keyboard)
    await callback.answer("Сброшено")


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

async def _admin_metrics(users_collection):
    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=1)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    async def count_distinct(query, field):
        pipeline = [
            {"$match": query},
            {"$group": {"_id": f"${field}"}},
            {"$count": "c"}
        ]
        res = await users_collection.aggregate(pipeline).to_list(length=1)
        return (res[0]["c"] if res else 0)

    total_users = await count_distinct({"type": "user_profile"}, "user_id")
    dau = await count_distinct({"type": "user_profile", "last_active": {"$gte": d1}}, "user_id")
    wau = await count_distinct({"type": "user_profile", "last_active": {"$gte": d7}}, "user_id")
    mau = await count_distinct({"type": "user_profile", "last_active": {"$gte": d30}}, "user_id")

    new_24h = await users_collection.count_documents({"type": "user_profile", "created_at": {"$gte": d1}})
    new_7d = await users_collection.count_documents({"type": "user_profile", "created_at": {"$gte": d7}})

    active_dialogs_24h = await count_distinct({"type": "user_message", "timestamp": {"$gte": d1}}, "user_id")

    avg_msgs = await get_average_messages_per_user(users_collection)

    pipeline_sessions = [
        {"$match": {"type": "session_summary", "timestamp": {"$gte": d7}}},
        {"$group": {"_id": None, "cnt": {"$sum": 1}, "avg_len": {"$avg": "$real_user_message_count"}}}
    ]
    sess = await users_collection.aggregate(pipeline_sessions).to_list(length=1)
    sessions_7d = int(sess[0]["cnt"]) if sess else 0
    avg_session_len = float(sess[0]["avg_len"]) if sess and sess[0]["avg_len"] is not None else 0.0

    portraits_7d = await users_collection.count_documents({"type": "user_profile", "last_portrait_timestamp": {"$gte": d7}})

    pipeline_avg7 = [
        {"$match": {"type": "progress_score", "timestamp": {"$gte": d7}}},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}}
    ]
    pipeline_prev7 = [
        {"$match": {"type": "progress_score", "timestamp": {"$lt": d7, "$gte": d7 - timedelta(days=7)}}},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}}
    ]
    a7 = await users_collection.aggregate(pipeline_avg7).to_list(length=1)
    p7 = await users_collection.aggregate(pipeline_prev7).to_list(length=1)
    avg_score_7d = float(a7[0]["avg"]) if a7 and a7[0]["avg"] is not None else 0.0
    prev_avg_score_7d = float(p7[0]["avg"]) if p7 and p7[0]["avg"] is not None else 0.0
    trend = 0.0
    if prev_avg_score_7d > 0:
        trend = (avg_score_7d - prev_avg_score_7d) / prev_avg_score_7d

    onboard_total = total_users if total_users > 0 else 1
    onboard_completed = await users_collection.count_documents({"type": "user_profile", "onboarding_completed": True})
    onboarding_conv = onboard_completed / onboard_total

    return {
        "total_users": total_users,
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "new_24h": new_24h,
        "new_7d": new_7d,
        "active_dialogs_24h": active_dialogs_24h,
        "avg_msgs": avg_msgs,
        "sessions_7d": sessions_7d,
        "avg_session_len": avg_session_len,
        "portraits_7d": portraits_7d,
        "avg_score_7d": avg_score_7d,
        "trend": trend,
        "onboarding_conv": onboarding_conv,
    }


@router.callback_query(F.data == "admin_stats", config.IsAdmin())
async def admin_stats(callback: CallbackQuery, users_collection) -> None:
    m = await _admin_metrics(users_collection)
    avg = m["avg_msgs"]["average_messages_per_user"]
    total_messages = m["avg_msgs"]["total_messages"]

    trend_icon = "⚖️"
    if m["trend"] > 0.05:
        trend_icon = "🚀"
    elif m["trend"] < -0.05:
        trend_icon = "⬇️"

    stats = (
        "📊 Статистика InnerTalk\n\n"
        f"👥 Пользователи: {m['total_users']:,}\n"
        f"➕ Новые: 24ч {m['new_24h']:,} • 7д {m['new_7d']:,}\n\n"
        f"🟢 Активность: DAU {m['dau']:,} • WAU {m['wau']:,} • MAU {m['mau']:,}\n"
        f"💬 Сообщений всего: {total_messages:,} • в среднем: {avg:.2f}/польз.\n"
        f"🗣️ Активные диалоги (24ч): {m['active_dialogs_24h']:,}\n\n"
        f"🧵 Сессии (7д): {m['sessions_7d']:,} • средняя длина: {m['avg_session_len']:.1f} сообщений\n"
        f"🧠 Портретов (7д): {m['portraits_7d']:,}\n"
        f"📈 Средний балл (7д): {m['avg_score_7d']:.2f} ({trend_icon} тренд)\n\n"
        f"🎯 Онбординг завершили: {m['onboarding_conv']*100:.1f}%\n"
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

    cursor = users_collection.find({}, projection)

    user_ids = []
    async for doc in cursor:
        user_id = doc.get("user_id")
        if isinstance(user_id, int):
            user_ids.append(user_id)

    return user_ids


async def start_mass_mailing(bot, text: str, admin_id: int, users_collection):
    user_ids = await get_user_ids(users_collection)

    users_sent_count = 0

    for user_id in user_ids:
        await send_single_message(bot, user_id, text)
        users_sent_count += 1

    await bot.send_message(admin_id,
                           f"✅ Рассылка успешно инициирована для {users_sent_count} пользователей."
                           f"Остаток процесса будет выполнен в фоновом режиме.", reply_markup=keyboards.back_to_admin_panel)


@router.callback_query(F.data == "admin_news", config.IsAdmin())
async def process_mailing_start(callback: CallbackQuery, state: FSMContext, users_collection):
    await callback.message.edit_text("Введите текст для рассылки:")
    await state.set_state(states.MailingStates.waiting_for_text)
    await callback.answer()


@router.callback_query(F.data.startswith("mail_seg:"), config.IsAdmin())
async def mailing_choose_segment(callback: CallbackQuery, state: FSMContext):
    seg = callback.data.split(":")[1]
    await state.update_data(mailing_segment=seg)
    data = await state.get_data()
    text = data.get("mailing_text", "")
    preview = (
        "✉️ Предпросмотр\n\n"
        f"Сегмент: {seg}\n\n"
        f"---\n{text}\n---\n\n"
        "Запустить рассылку?"
    )
    await state.set_state(states.MailingStates.waiting_for_confirmation)
    try:
        await callback.message.edit_text(preview, reply_markup=keyboards.mailing_confirm_keyboard)
    except TelegramBadRequest:
        await callback.message.answer(preview, reply_markup=keyboards.mailing_confirm_keyboard)
    await callback.answer()


@router.callback_query(F.data == "mail_change_segment", config.IsAdmin())
async def mailing_change_segment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.MailingStates.waiting_for_text)
    await callback.message.edit_text("Выберите сегмент получателей:", reply_markup=keyboards.mailing_segments_keyboard)
    await callback.answer()


@router.callback_query(F.data == "mail_cancel", config.IsAdmin())
async def mailing_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=keyboards.back_to_admin_panel)
    await callback.answer()


async def _get_blacklisted_ids(users_collection) -> set[int]:
    cur = users_collection.find({"type": "blacklisted"}, {"user_id": 1, "_id": 0})
    res = set()
    async for d in cur:
        if isinstance(d.get("user_id"), int):
            res.add(d["user_id"])
    return res


async def _add_to_blacklist(users_collection, user_id: int):
    try:
        await users_collection.update_one(
            {"type": "blacklisted", "user_id": user_id},
            {"$set": {"type": "blacklisted", "user_id": user_id}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Не удалось добавить в blacklist {user_id}: {e}")


async def _segment_user_ids(users_collection, seg: str) -> list[int]:
    bl = await _get_blacklisted_ids(users_collection)
    ids: set[int] = set()
    now = datetime.now(timezone.utc)
    if seg == "all":
        cur = users_collection.find({"type": "user_profile"}, {"user_id": 1, "_id": 0})
        async for d in cur:
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)
    elif seg == "active7":
        since = now - timedelta(days=7)
        cur = users_collection.find({"type": "user_profile", "last_active": {"$gte": since}}, {"user_id": 1, "_id": 0})
        async for d in cur:
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)
    elif seg == "has_portrait":
        cur = users_collection.find({"type": "user_profile", "last_portrait_timestamp": {"$exists": True}}, {"user_id": 1, "_id": 0})
        async for d in cur:
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)
    elif seg == "scores3":
        pipeline = [
            {"$match": {"type": "progress_score"}},
            {"$group": {"_id": "$user_id", "cnt": {"$sum": 1}}},
            {"$match": {"cnt": {"$gte": 3}}},
            {"$project": {"user_id": "$_id", "_id": 0}}
        ]
        async for d in users_collection.aggregate(pipeline):
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)

    return [i for i in ids if i not in bl]


async def _send_with_retry(bot, user_id: int, text: str, *, retries: int = 3):
    delay = config.RATE_LIMIT_DELAY
    attempt = 0
    while attempt < retries:
        try:
            await bot.send_message(user_id, text)
            await asyncio.sleep(delay)
            return "ok"
        except Exception as e:
            s = str(e).lower()
            if "forbidden" in s or "blocked" in s or "403" in s:
                return "blocked"
            transient = any(x in s for x in ["429", "timeout", "temporar", "unavailable", "reset", "connection", "rate", "5"]) and "403" not in s
            attempt += 1
            if not transient or attempt >= retries:
                return f"err:{e}"
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))


async def start_mass_mailing(bot, text: str, admin_id: int, users_collection, seg: str):
    user_ids = await _segment_user_ids(users_collection, seg)
    total = len(user_ids)
    if total == 0:
        await bot.send_message(admin_id, "Нет пользователей в выбранном сегменте.", reply_markup=keyboards.back_to_admin_panel)
        return

    sem = asyncio.Semaphore(20)
    results = {"ok": 0, "blocked": 0, "errors": 0}

    async def worker(uid: int):
        async with sem:
            res = await _send_with_retry(bot, uid, text)
            if res == "ok":
                results["ok"] += 1
            elif res == "blocked":
                results["blocked"] += 1
                await _add_to_blacklist(users_collection, uid)
            else:
                results["errors"] += 1

    await asyncio.gather(*(worker(uid) for uid in user_ids))

    try:
        await users_collection.insert_one({
            "type": "mailing_log",
            "text": text,
            "segment": seg,
            "timestamp": datetime.now(timezone.utc),
            "total": total,
            **results
        })
    except Exception as e:
        logger.error(f"Не удалось сохранить лог рассылки: {e}")

    summary = (
        "✅ Рассылка завершена\n\n"
        f"Сегмент: {seg}\n"
        f"Всего: {total}\n"
        f"Доставлено: {results['ok']}\n"
        f"Заблокировали: {results['blocked']}\n"
        f"Ошибок: {results['errors']}\n"
    )
    await bot.send_message(admin_id, summary, reply_markup=keyboards.back_to_admin_panel)


@router.callback_query(F.data == "mail_send", config.IsAdmin())
async def mailing_send(callback: CallbackQuery, state: FSMContext, users_collection):
    data = await state.get_data()
    text = data.get("mailing_text", "")
    seg = data.get("mailing_segment", "all")
    await state.clear()
    asyncio.create_task(start_mass_mailing(callback.bot, text, callback.from_user.id, users_collection, seg))
    await callback.message.edit_text("🚀 Рассылка запущена. Итоги пришлю по завершении.")
    await callback.answer()