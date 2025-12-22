import logging
import asyncio
import time
from datetime import datetime, timezone
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from src import config
from src.presentation.prompts import SYSTEM_PROMPT_TEXT
from src.presentation import keyboards, photos, texts
from src import states
from google.genai import types
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router()

_GEMINI_BACKOFF_UNTIL: float | None = None

def _gemini_backoff_seconds() -> int:
    try:
        return int(getattr(config, "GEMINI_BACKOFF_SEC", 300))
    except Exception:
        return 300

def _is_gemini_in_backoff() -> bool:
    global _GEMINI_BACKOFF_UNTIL
    if _GEMINI_BACKOFF_UNTIL is None:
        return False
    now = time.time()
    if now < _GEMINI_BACKOFF_UNTIL:
        return True
    _GEMINI_BACKOFF_UNTIL = None
    return False

def _set_gemini_backoff(seconds: int | None = None) -> None:
    global _GEMINI_BACKOFF_UNTIL
    ttl = seconds if seconds is not None else _gemini_backoff_seconds()
    _GEMINI_BACKOFF_UNTIL = time.time() + max(1, int(ttl))

def _clear_gemini_backoff() -> None:
    global _GEMINI_BACKOFF_UNTIL
    _GEMINI_BACKOFF_UNTIL = None

async def _save_user_profile_async(collection, user_id, username, first_name, user_service=None):
    try:
        if user_service:
            await user_service.save_user_profile_async(user_id, username, first_name)
        else:
            await collection.update_one(
                {"user_id": user_id, "type": "user_profile"},
                {
                    "$set": {
                        "username": username,
                        "first_name": first_name,
                        "last_active": datetime.now(timezone.utc)
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения/обновления профиля пользователя: {e}")

async def _save_to_db_async(collection, data):
    try:
        await collection.insert_one(data)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных в MongoDB в фоновом режиме: {e}")


def _get_time_of_day() -> str:
    now = datetime.now(timezone.utc)
    hour = now.hour
    
    if 5 <= hour < 12:
        return "утро"
    elif 12 <= hour < 17:
        return "день"
    elif 17 <= hour < 22:
        return "вечер"
    else:
        return "ночь"


async def _load_user_context(users_collection, user_id: int) -> str:
    context_parts = []
    
    time_of_day = _get_time_of_day()
    time_emoji = {"утро": "🌅", "день": "☀️", "вечер": "🌆", "ночь": "🌙"}.get(time_of_day, "🕐")
    context_parts.append(f"{time_emoji} Сейчас {time_of_day} (по UTC).")
    
    try:
        test_results_cursor = users_collection.find(
            {"user_id": user_id, "type": "test_result"}
        ).sort("finished_at", -1).limit(5)
        
        test_results = []
        async for doc in test_results_cursor:
            test_title = doc.get("test_title", "Неизвестный тест")
            test_id = doc.get("test_id", "")
            result = doc.get("result", {})
            verdict = result.get("verdict", "")
            
            finished_at = doc.get("finished_at")
            date_str = ""
            if finished_at:
                if isinstance(finished_at, datetime):
                    date_str = finished_at.strftime("%d.%m.%Y")
                else:
                    try:
                        date_str = datetime.fromisoformat(str(finished_at)).strftime("%d.%m.%Y")
                    except:
                        pass
            
            date_prefix = f"[{date_str}] " if date_str else ""
            
            if result.get("type") == "mbti":
                code = result.get("code", "")
                description = result.get("description", "")
                if description:
                    short_desc = description[:200] + "..." if len(description) > 200 else description
                    test_results.append(f"- {date_prefix}{test_title}: тип личности {code}. {short_desc}")
                else:
                    test_results.append(f"- {date_prefix}{test_title}: тип личности {code}")
            elif result.get("type") == "likert_multi":
                if "emotional" in test_id:
                    averages = result.get("averages", {})
                    if averages:
                        stress = averages.get("stress", 0)
                        anxiety = averages.get("anxiety", 0)
                        burnout = averages.get("burnout", 0)
                        interpretation = []
                        if stress >= 4.0:
                            interpretation.append("высокий уровень стресса")
                        elif stress >= 3.0:
                            interpretation.append("умеренный стресс")
                        if anxiety >= 4.0:
                            interpretation.append("высокая тревожность")
                        elif anxiety >= 3.0:
                            interpretation.append("умеренная тревожность")
                        if burnout >= 4.0:
                            interpretation.append("высокий риск выгорания")
                        elif burnout >= 3.0:
                            interpretation.append("признаки выгорания")
                        
                        interp_text = f" ({', '.join(interpretation)})" if interpretation else ""
                        test_results.append(
                            f"- {date_prefix}{test_title}: "
                            f"стресс {stress:.1f}/5, тревожность {anxiety:.1f}/5, "
                            f"выгорание {burnout:.1f}/5{interp_text}"
                        )
                    else:
                        short_verdict = verdict[:200] + "..." if len(verdict) > 200 else verdict
                        test_results.append(f"- {date_prefix}{test_title}: {short_verdict}")
                elif "attachment" in test_id:
                    short_verdict = verdict[:200] + "..." if len(verdict) > 200 else verdict
                    test_results.append(f"- {date_prefix}{test_title}: {short_verdict}")
                elif "love" in test_id:
                    short_verdict = verdict[:200] + "..." if len(verdict) > 200 else verdict
                    test_results.append(f"- {date_prefix}{test_title}: {short_verdict}")
                else:
                    short_verdict = verdict[:200] + "..." if len(verdict) > 200 else verdict
                    test_results.append(f"- {date_prefix}{test_title}: {short_verdict}")
        
        if test_results:
            context_parts.append("\n📊 Результаты последних тестов пользователя (это психологические тесты, которые пользователь проходил ранее):")
            context_parts.extend(test_results[:3])
            context_parts.append("Используй эти результаты для понимания текущего состояния пользователя и его психологических особенностей.")
    except Exception as e:
        logger.error(f"Ошибка загрузки результатов тестов: {e}")
    
    try:
        progress_scores_cursor = users_collection.find(
            {"user_id": user_id, "type": "progress_score"}
        ).sort("timestamp", -1).limit(10)
        
        progress_scores = []
        score_values = []
        async for doc in progress_scores_cursor:
            score = doc.get("score", 0)
            timestamp = doc.get("timestamp")
            if timestamp:
                date_str = timestamp.strftime("%d.%m.%Y")
                progress_scores.append(f"{date_str}: {score}/10")
                score_values.append(score)
        
        if progress_scores:
            context_parts.append("\n📈 Последние оценки прогресса (дневник эмоций):")
            context_parts.append(", ".join(progress_scores[:5]))
            
            if len(score_values) >= 2:
                latest = score_values[0]
                previous = score_values[1]
                avg_recent = sum(score_values[:5]) / min(5, len(score_values))
                
                trend_info = []
                if latest > previous:
                    trend_info.append("тенденция к улучшению")
                elif latest < previous:
                    trend_info.append("тенденция к снижению")
                else:
                    trend_info.append("стабильное состояние")
                
                if avg_recent >= 7:
                    trend_info.append("в целом хорошее состояние")
                elif avg_recent <= 4:
                    trend_info.append("требуется поддержка")
                
                if trend_info:
                    context_parts.append(f"({', '.join(trend_info)}, среднее за последние оценки: {avg_recent:.1f}/10)")
            elif len(score_values) == 1:
                latest = score_values[0]
                if latest >= 7:
                    context_parts.append("(хорошее состояние)")
                elif latest <= 4:
                    context_parts.append("(требуется поддержка)")
    except Exception as e:
        logger.error(f"Ошибка загрузки оценок прогресса: {e}")
    
    if len(context_parts) > 1:
        return "\n".join(context_parts)
    return context_parts[0] if context_parts else ""


@router.message(Command("health"))
async def health_handler(message: Message, health_checker=None) -> None:
    if not health_checker:
        await message.answer("Health checker не инициализирован")
        return
    
    try:
        status = await health_checker.get_health_status()
        overall = status["overall"]
        services = status["services"]
        
        status_text = f"🏥 Статус сервисов: {overall.upper()}\n\n"
        status_text += f"📊 База данных: {services['database'].get('status', 'unknown')}\n"
        status_text += f"🤖 Gemini API: {services['gemini_api'].get('status', 'unknown')} ({services['gemini_api'].get('state', 'N/A')})\n"
        status_text += f"🧠 OpenAI API: {services['openai_api'].get('status', 'unknown')} ({services['openai_api'].get('state', 'N/A')})\n"
        
        if services['database'].get('error'):
            status_text += f"\n⚠️ Ошибка БД: {services['database']['error']}"
        
        await message.answer(status_text)
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        await message.answer(f"Ошибка при проверке здоровья: {e}")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, users_collection) -> None:
    await state.set_state(states.SessionStates.idle)

    user = message.from_user
    try:
        from src.domain.services.user_service import UserService
        cache = getattr(message.bot, '_cache', None) if hasattr(message, 'bot') else None
        user_service = UserService(users_collection, cache)
        asyncio.create_task(user_service.save_user_profile_async(
            user.id,
            user.username,
            user.first_name
        ))
    except Exception as e:
        logger.error(f"Error using UserService, fallback: {e}")
        asyncio.create_task(_save_user_profile_async(
            users_collection,
            user.id,
            user.username,
            user.first_name
        ))

    user_profile = await users_collection.find_one({"user_id": user.id, "type": "user_profile"})
    onboarding_completed = bool(user_profile.get("onboarding_completed")) if user_profile else False

    if not onboarding_completed:
        await state.set_state(states.OnboardingStates.step1)
        await message.answer_photo(
            photo=photos.main_photo,
            caption=texts.ONBOARDING_STEP1,
            reply_markup=keyboards.onboarding_step1
        )
        return

    caption_text = texts.MAIN_MENU_CAPTION
    await message.answer_photo(
        photo=photos.main_photo,
        caption=caption_text,
        reply_markup=keyboards.main_menu)


async def update_thinking_message(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "🔍 Анализирую ваш диалог...",
        "🧠 Синтезирую информацию...",
        "💬 Формулирую ответ...",
        "⚙️ Вычисляю оптимальный совет..."
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
                        text=text_frame
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
        "🚫 Ошибка: Я — текстовый ИИ‑психолог и могу обрабатывать только текстовые сообщения."
    )

@router.message(StateFilter(states.SessionStates.in_session))
async def echo_handler(message: Message, state: FSMContext, generate_content_sync_func, users_collection, bot,
                       gemini_client, count_tokens_sync_func, openai_client=None, generate_openai_func=None, alert_func=None) -> None:
    if not message or not message.from_user:
        logger.error("Invalid message object in echo_handler")
        return
    
    user_text = message.text or ""
    user_id = message.from_user.id
    chat_id = message.chat.id if message.chat else user_id
    username = message.from_user.username or ""

    if not user_text or not user_text.strip():
        try:
            await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
        return

    current_data = await state.get_data()
    ai_style = current_data.get("ai_style", "default")

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
    if not isinstance(history, list):
        history = []
    
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
        except Exception as e:
            logger.warning(f"Error editing message markup: {e}")

    is_summary_present = (
            len(history) > 0 and
            isinstance(history[0], dict) and
            history[0].get('content', '').startswith("ПРЕДЫДУЩИЙ КОНСПЕКТ СЕССИИ:")
    )
    summary_content_dict = history[0] if is_summary_present else None

    dialog_messages_only = history[1:] if is_summary_present else (history.copy() if history else [])

    user_message_content_dict = {"role": "user", "content": user_text}
    dialog_messages_only.append(user_message_content_dict)
    max_msgs = getattr(config, "MAX_DIALOG_MESSAGES", 20)
    if len(dialog_messages_only) > max_msgs:
        dialog_messages_only = dialog_messages_only[-max_msgs:]

    try:
        from src.domain.services.context_service import ContextService
        cache = getattr(bot, '_cache', None)
        context_service = ContextService(users_collection, cache)
        user_context = await context_service.load_user_context(user_id)
    except Exception as e:
        logger.error(f"Error loading context via service: {e}, falling back to old method")
        user_context = await _load_user_context(users_collection, user_id)
    
    context_section = ""
    if user_context:
        context_section = (
            f"\n\n### КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:\n{user_context}\n\n"
            "ВАЖНО: Используй эту информацию для более персонализированного ответа:\n"
            "- Если сейчас ночь, упомяни это естественно (например: 'Глубокая ночь, а мысли не отпускают?')\n"
            "- РЕЗУЛЬТАТЫ ТЕСТОВ: Это психологические тесты, которые пользователь проходил ранее. "
            "Если видишь высокий уровень стресса (≥4/5), тревожности (≥4/5) или выгорания (≥4/5) - будь более поддерживающим и эмпатичным. "
            "Если видишь тип личности MBTI - учитывай особенности этого типа в общении. "
            "Используй эту информацию естественно, не перечисляя явно, но учитывая в своих ответах.\n"
            "- ОЦЕНКИ ПРОГРЕССА: Это дневник эмоций пользователя (шкала 1-10). "
            "Если есть тенденция к улучшению - отметь это поддержкой; если к снижению - прояви больше эмпатии и предложи исследовать причины.\n"
            "- Не перечисляй все данные явно, но используй их для понимания состояния пользователя\n"
            "- Если видишь противоречия (например, высокий стресс по тесту, но хорошие оценки прогресса), мягко исследуй это в диалоге"
        )
    
    base_prompt_with_style = f"{SYSTEM_PROMPT_TEXT}{context_section}\n\n{style_modifier}"

    if is_summary_present and summary_content_dict:
        final_system_prompt = f"{summary_content_dict['content']}\n\n{base_prompt_with_style}"
        logger.info("Конспект, контекст пользователя и акцент добавлены в системную инструкцию.")
    else:
        final_system_prompt = base_prompt_with_style
        if user_context:
            logger.info(f"Используется акцент: {ai_style}, контекст пользователя загружен.")
        else:
            logger.info(f"Используется акцент: {ai_style}")

    new_contents_gemini = []
    try:
        for item in dialog_messages_only:
            if not item or not isinstance(item, dict):
                continue
            role = item.get('role', 'user')
            content = item.get('content', '')
            if content:
                new_contents_gemini.append(
                    types.Content(
                        role=role,
                        parts=[types.Part(text=str(content))]
                    )
                )
    except Exception as e:
        logger.error(f"Error creating Gemini contents: {e}")
    new_contents_gemini = [
        types.Content(
                role="user",
                parts=[types.Part(text=user_text)]
            )
        ]
    
    if not new_contents_gemini:
        logger.error("Empty contents for Gemini, using fallback")
        new_contents_gemini = [
            types.Content(
                role="user",
                parts=[types.Part(text=user_text)]
            )
    ]

    total_token_count = 0
    token_task = None

    if not gemini_client or not count_tokens_sync_func:
        logger.warning("Gemini client or count_tokens function not available, skipping token count")
    else:
        try:
                token_task = asyncio.create_task(
                    count_tokens_sync_func(
                gemini_client,
                'gemini-3-flash-preview',
                new_contents_gemini,
            )
                )
        except Exception as e:
            logger.error(f"Error starting token count: {e}")
        
        if token_task:
            try:
                token_response = await token_task
                if token_response and hasattr(token_response, 'total_tokens'):
                    total_token_count = token_response.total_tokens
            except Exception as e:
                logger.error(f"Error counting tokens: {e}")

    if total_token_count >= config.MAX_TOKENS_PER_SESSION:
        await message.answer(
            f"🕰️ Лимит сессии: общий объем диалога ({total_token_count} токенов) "
            f"достиг максимума (~{config.MAX_TOKENS_PER_SESSION} токенов).\n"
            f"Для завершения и сохранения конспекта нажмите 'Закончить сессию'.",
            reply_markup=keyboards.end_session_menu
        )
        if alert_func:
            try:
                asyncio.create_task(alert_func(bot, f"Пользователь {user_id} достиг лимита токенов сессии ({total_token_count}/{config.MAX_TOKENS_PER_SESSION}).", key="session_tokens_limit"))
            except Exception:
                pass
        return

    try:
        thinking_message = await message.answer("...")
    except Exception as e:
        logger.error(f"Error sending thinking message to user {user_id}: {e}")
        thinking_message = message
        stop_event = None
        animation_task = None
    else:
        stop_event = asyncio.Event()
        try:
            animation_task = asyncio.create_task(
            update_thinking_message(
                bot,
                chat_id,
                thinking_message.message_id,
                stop_event))   
        except Exception as e:
            logger.error(f"Error starting animation task: {e}")
            animation_task = None

    ai_response = "Извините, модель поставщика на данный момент перегружена. Попробуйте повторить последнее сообщение! Если ошибка повторяется, завершите сессию."

    def _is_resource_exhausted(err: Exception) -> bool:
        msg = str(err).lower()
        substrings = [
            "resource exhausted",
            "quota",
            "exceed",
            "rate",
            "insufficient",
            "limit",
            "429",
            "503",
            "502",
            "504",
            "service unavailable",
            "temporarily unavailable",
            "unavailable",
            "overloaded",
            "model is overloaded",
            "bad gateway",
            "gateway timeout",
            "deadline exceeded",
            "connection reset",
            "upstream",
            "retry later",
        ]
        return any(x in msg for x in substrings) and "forbidden" not in msg

    gemini_failed_exc: Exception | None = None

    async def _call_openai_fallback(reason: str | None = None):
        nonlocal ai_response
        if not openai_client or not generate_openai_func:
            logger.warning("OpenAI fallback requested but OpenAI client not available")
            return False
        
        if alert_func:
            try:
                msg = "Срабатывание фоллбэка: переключаемся на OpenAI"
                if reason:
                    msg += f" ({reason})"
                asyncio.create_task(alert_func(bot, f"{msg} (user {user_id}).", key="fallback_gemini_openai"))
            except Exception:
                pass
        
        for model in ("gpt-4.1", "gpt-5-chat-latest"):
            try:
                if not dialog_messages_only:
                    logger.warning("Empty dialog for OpenAI fallback")
                    break
                
                joined_dialog = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in dialog_messages_only])
                if not joined_dialog.strip():
                    logger.warning("Empty dialog text for OpenAI fallback")
                    break
                
                ai_text = await generate_openai_func(openai_client, model, joined_dialog, final_system_prompt)
                if ai_text and ai_text.strip():
                    ai_response = ai_text
                    logger.info(f"OpenAI fallback successful with model {model}")
                    return True
            except Exception as oe:
                logger.warning(f"OpenAI fallback '{model}' failed: {oe}")
        
        if alert_func:
            try:
                asyncio.create_task(alert_func(bot, f"Неудачный фоллбэка: ни одна из моделей OpenAI (4.1/5-chat-latest) не ответила (user {user_id}).", key="fallback_failed"))
            except Exception:
                pass
        return False

    gemini_circuit = getattr(bot, '_gemini_circuit', None) if hasattr(bot, '_gemini_circuit') else None
    gemini_available = True
    
    if gemini_circuit is not None:
        try:
            from src.infrastructure.circuit_breaker import CircuitState
            circuit_state = gemini_circuit.get_state()
            if circuit_state == CircuitState.OPEN:
                gemini_available = False
                logger.info(f"Gemini Circuit Breaker is OPEN, skipping Gemini call")
        except Exception as e:
            logger.warning(f"Error checking circuit breaker state: {e}")
    
    if not gemini_available or (openai_client and generate_openai_func and _is_gemini_in_backoff()):
        if openai_client and generate_openai_func:
            reason = "Circuit Breaker открыт" if not gemini_available else f"активен backoff Gemini, повторная попытка через ~{max(1, int((_GEMINI_BACKOFF_UNTIL - time.time()) if _GEMINI_BACKOFF_UNTIL else 0))}с"
            await _call_openai_fallback(reason=reason)
    else:
            gemini_available = True
    
    if gemini_available:
        try:
            if not gemini_client:
                raise RuntimeError("Gemini client not initialized")
            
            ai_response_obj = await generate_content_sync_func(
                gemini_client,
                'gemini-3-flash-preview',
                new_contents_gemini,
                final_system_prompt
            )
            
            if not ai_response_obj or not hasattr(ai_response_obj, 'text'):
                raise RuntimeError("Invalid response from Gemini API")
            
            ai_response = ai_response_obj.text
            if not ai_response or not ai_response.strip():
                raise RuntimeError("Empty response from Gemini API")
            
            _clear_gemini_backoff()
        except RuntimeError as e:
            if "circuit breaker open" in str(e).lower() or "temporarily unavailable" in str(e).lower():
                logger.warning(f"Gemini Circuit Breaker открыт, переключаемся на OpenAI")
                if openai_client and generate_openai_func:
                    await _call_openai_fallback(reason="Circuit Breaker открыт")
                else:
                    ai_response = "Извините, сервис временно недоступен. Попробуйте позже."
            else:
                raise
        except Exception as e:
            gemini_failed_exc = e
            logger.error(f"Gemini API call error: {e}")

            if openai_client and generate_openai_func and _is_resource_exhausted(e):
                _set_gemini_backoff()
                await _call_openai_fallback(reason="Gemini недоступен или исчерпан ресурс")

    if stop_event:
        stop_event.set()

    if animation_task:
        try:
            await animation_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in animation task: {e}")

    final_message = thinking_message

    if not ai_response or not ai_response.strip():
        ai_response = "Извините, не удалось получить ответ. Попробуйте позже."

    try:
        if thinking_message and thinking_message != message:
            await thinking_message.edit_text(
                text=ai_response,
                reply_markup=keyboards.end_session_menu
            )
        else:
            final_message = await message.answer(
                ai_response,
                reply_markup=keyboards.end_session_menu
            )
    except TelegramBadRequest as e:
        logger.warning(f"Failed to edit thinking message: {e}")
        try:
            final_message = await message.answer(
                ai_response,
                reply_markup=keyboards.end_session_menu
            )
        except Exception as e2:
            logger.error(f"Failed to send message to user {user_id}: {e2}")
            try:
                final_message = await message.answer(ai_response)
            except Exception as e3:
                logger.critical(f"Complete failure to send message to user {user_id}: {e3}")
                return

    current_time = datetime.now(timezone.utc)

    if users_collection is not None:
        try:
            asyncio.create_task(_save_to_db_async(users_collection, {
                "user_id": user_id,
                "type": "user_message",
                "text": user_text,
                "timestamp": current_time,
                "username": username,
            }))
        except Exception as e:
            logger.error(f"Error scheduling user message save: {e}")

        try:
            asyncio.create_task(_save_to_db_async(users_collection, {
                "user_id": user_id,
                "type": "model_response",
                "text": ai_response,
                "timestamp": current_time,
            }))
        except Exception as e:
            logger.error(f"Error scheduling AI response save: {e}")

    try:
        if ai_response:
            dialog_messages_only.append({"role": "model", "content": ai_response})
    
        if len(dialog_messages_only) > max_msgs:
            dialog_messages_only = dialog_messages_only[-max_msgs:]

            history_to_save = dialog_messages_only.copy() if dialog_messages_only else []

        if is_summary_present and summary_content_dict:
            history_to_save.insert(0, summary_content_dict)
            logger.info("Конспект возвращен в историю для FSMContext (индекс 0).")

        real_user_message_count = current_data.get("real_user_message_count", 0) + 1

        message_id = final_message.message_id if final_message and hasattr(final_message, 'message_id') else None
        await state.update_data(
            current_dialog=history_to_save,
                last_ai_message_id=message_id,
            real_user_message_count=real_user_message_count
        )
    except Exception as e:
        logger.error(f"Error updating state: {e}")

@router.message(Command("admin"), config.IsAdmin())
async def start_admin(message: Message) -> None:
    text = (
        "👋 Добро пожаловать в Админ-панель!\n\n"
        "Вы находитесь в главном меню управления ботом."
        "Выберите действие ниже, чтобы начать работу с пользователями или системой.\n"
        "\n"
        "[Внимание] Все критические действия (рассылка, бан) запускаются "
        "через соответствующую кнопку."
    )

    await message.answer(text=text, reply_markup=keyboards.admin_keyboard)


@router.message(StateFilter(states.MailingStates.waiting_for_text), config.IsAdmin())
async def mailing_got_text(message: Message, state: FSMContext):
    text = message.text or ""
    await state.update_data(mailing_text=text, mailing_segment=None)

    preview = (
        "✉️ Предпросмотр рассылки\n\n"
        "Текст сообщения будет отправлен выбранному сегменту пользователей.\n\n"
        f"---\n{text}\n---\n\n"
        "Выберите сегмент получателей:"
    )
    await message.answer(preview, reply_markup=keyboards.mailing_segments_keyboard)


@router.message(StateFilter(states.MailingStates.waiting_for_confirmation), config.IsAdmin())
async def mailing_waiting_confirmation(message: Message):
    await message.answer("Используйте кнопки ниже для продолжения.")

@router.message(F.content_type != "text")
async def non_text_idle_handler(message: Message) -> None:
    if message.photo:
        print(message.photo[-1].file_id)
    else:
        print(f"Non-text content received: {message.content_type}")