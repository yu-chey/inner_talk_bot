import asyncio
import sys
import logging
from logging.handlers import RotatingFileHandler
import time
from typing import Optional
import motor.motor_asyncio
from src import config
from src.application.handlers import router as handler_router
from src.application.callbacks import (
    menu_router,
    session_router,
    test_router,
    portrait_router,
    admin_router,
    onboarding_router,
    profile_router
)
from src.infrastructure.cache import SimpleCache
from src.infrastructure.database import Database
from src.infrastructure.circuit_breaker import CircuitBreaker
from src.infrastructure.health import HealthChecker

from google import genai
from google.genai import types

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)
root_logger.addHandler(RotatingFileHandler("app.log", maxBytes=5_000_000, backupCount=3, encoding='utf-8'))
root_logger.addHandler(logging.StreamHandler(sys.stdout))

logger = logging.getLogger(__name__)

gemini_client = None
openai_client = None
mongo_client = None
db = None
users_collection = None

DEFAULT_TEMPERATURE = 0.8
_ALERT_THROTTLE: dict[str, float] = {}
_ALERT_THROTTLE_WINDOW_SEC = 60.0

def generate_content_sync(client, model_name, contents, system_instruction=None):
    """Синхронный вызов Gemini (оставлен для совместимости, без ретраев)."""
    config_params = {
        "temperature": DEFAULT_TEMPERATURE
    }

    if system_instruction:
        config_params['system_instruction'] = system_instruction

    config_obj = types.GenerateContentConfig(**config_params) if config_params else None

    return client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config_obj
    )


def count_tokens_sync(client, model_name, contents):
    return client.models.count_tokens(
        model=model_name,
        contents=contents
    )


async def _run_with_timeout(func, *args, timeout: float):
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(loop.run_in_executor(None, func, *args), timeout=timeout)


async def generate_content_async_with_retry(client,
                                            model_name,
                                            contents,
                                            system_instruction: Optional[str] = None,
                                            *,
                                            timeout: float = 20.0,
                                            retries: int = 3,
                                            backoff_base: float = 1.0,
                                            circuit_breaker=None):
    if circuit_breaker:
        try:
            return await circuit_breaker.call(
                _generate_with_retry_internal,
                client, model_name, contents, system_instruction,
                timeout, retries, backoff_base
            )
        except Exception as e:
            from src.infrastructure.circuit_breaker import CircuitBreakerOpenError
            if isinstance(e, CircuitBreakerOpenError):
                raise RuntimeError("AI service temporarily unavailable (circuit breaker open)")
            raise
    
    return await _generate_with_retry_internal(
        client, model_name, contents, system_instruction,
        timeout, retries, backoff_base
    )


async def _generate_with_retry_internal(client, model_name, contents, system_instruction,
                                        timeout, retries, backoff_base):
    attempt = 0
    last_err = None
    max_retries = min(retries, 2)
    while attempt < max_retries:
        try:
            return await _run_with_timeout(
                generate_content_sync,
                client,
                model_name,
                contents,
                system_instruction,
                timeout=min(timeout, 10.0)
            )
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = any(code in msg for code in ["429", " 5", "timeout", "temporar", "unavailable", "reset", "connection", "rate"])
            client_err = any(code in msg for code in [" 4", "bad request", "unauthorized", "forbidden"]) and "429" not in msg

            attempt += 1
            if client_err or attempt >= max_retries:
                break
            sleep_for = min(backoff_base * (2 ** (attempt - 1)), 2.0)
            await asyncio.sleep(sleep_for)
    raise last_err if last_err else RuntimeError("Gemini call failed without explicit error")


async def count_tokens_async_with_retry(client,
                                        model_name,
                                        contents,
                                        *,
                                        timeout: float = 10.0,
                                        retries: int = 3,
                                        backoff_base: float = 1.0,
                                        circuit_breaker=None):
    if circuit_breaker:
        try:
            return await circuit_breaker.call(
                _count_tokens_internal,
                client, model_name, contents, timeout, retries, backoff_base
            )
        except Exception as e:
            from src.infrastructure.circuit_breaker import CircuitBreakerOpenError
            if isinstance(e, CircuitBreakerOpenError):
                raise RuntimeError("AI service temporarily unavailable (circuit breaker open)")
            raise
    
    return await _count_tokens_internal(client, model_name, contents, timeout, retries, backoff_base)


async def _count_tokens_internal(client, model_name, contents, timeout, retries, backoff_base):
    attempt = 0
    last_err = None
    while attempt < retries:
        try:
            return await _run_with_timeout(
                count_tokens_sync,
                client,
                model_name,
                contents,
                timeout=timeout
            )
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = any(code in msg for code in ["429", " 5", "timeout", "temporar", "unavailable", "reset", "connection", "rate"])
            client_err = any(code in msg for code in [" 4", "bad request", "unauthorized", "forbidden"]) and "429" not in msg
            attempt += 1
            if client_err or attempt >= retries:
                break
            sleep_for = backoff_base * (2 ** (attempt - 1))
            await asyncio.sleep(sleep_for)
    raise last_err if last_err else RuntimeError("Gemini count_tokens failed without explicit error")


async def generate_openai_chat_async(client: "AsyncOpenAI", model: str, prompt: str, system_instruction: Optional[str] = None,
                                     *, timeout: float = 30.0, retries: int = 2, backoff_base: float = 1.0) -> str:
    if client is None:
        raise RuntimeError("OpenAI client is not initialized")
    sys_msg = system_instruction or ""
    attempt = 0
    last_err = None
    use_responses_api = (
        model.startswith("gpt-5")
        or model.startswith("gpt-4.1")
    )
    while attempt <= retries:
        try:
            if use_responses_api:
                full_input = f"{sys_msg}\n\n{prompt}" if sys_msg else prompt
                resp = await asyncio.wait_for(
                    client.responses.create(
                        model=model,
                        input=full_input,
                    ),
                    timeout=timeout
                )
                text = getattr(resp, "output_text", None)
                if not text:
                    try:
                        parts = resp.output[0].content if hasattr(resp, "output") else []
                        text = "".join(getattr(p, "text", "") for p in parts)
                    except Exception:
                        text = ""
                return text or ""
            else:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=DEFAULT_TEMPERATURE,
                    ),
                    timeout=timeout
                )
                return resp.choices[0].message.content if resp and resp.choices else ""
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = any(x in msg for x in ["429", "timeout", "temporar", "unavailable", "reset", "connection", "rate", " 5"]) and "forbidden" not in msg
            if not transient or attempt >= retries:
                break
            attempt += 1
            await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))
    raise last_err if last_err else RuntimeError("OpenAI generation failed without explicit error")


async def send_alert(bot: Bot, text: str, *, key: str | None = None) -> None:
    now = time.time()
    k = key or (text[:40] if text else "generic")
    last = _ALERT_THROTTLE.get(k, 0.0)
    if now - last < _ALERT_THROTTLE_WINDOW_SEC:
        return
    _ALERT_THROTTLE[k] = now
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, f"⚠️ Alert: {text}")
        except Exception as e:
            logger.warning(f"Не удалось отправить Alert {admin_id}: {e}")


async def _verify_openai_models(bot: Bot, client: "AsyncOpenAI"):
    if client is None:
        return
    try:
        models = await client.models.list()
        available = set()
        try:
            for m in getattr(models, "data", []) or []:
                mid = getattr(m, "id", None)
                if isinstance(mid, str):
                    available.add(mid)
        except Exception:
            pass
        required = {
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5-mini",
            "gpt-5-chat-latest",
            "gpt-4.1",
            "gpt-4.1-mini",
        }
        missing = sorted(list(required - available))
        if missing:
            miss_str = ", ".join(missing)
            logger.warning(f"Отсутствуют модели OpenAI: {miss_str}")
            await send_alert(bot, f"Отсутствуют модели OpenAI: {miss_str}. Проверьте доступ в аккаунте.", key="openai_models_missing")
        else:
            logger.info("Все требуемые модели OpenAI доступны.")
    except Exception as e:
        logger.warning(f"Не удалось проверить список моделей OpenAI: {e}")

async def main():
    global gemini_client, mongo_client, db, users_collection, openai_client

    cache = SimpleCache()
    asyncio.create_task(cache.start_cleanup_task())
    
    gemini_circuit = CircuitBreaker(failure_threshold=3, timeout=30.0)
    openai_circuit = CircuitBreaker(failure_threshold=5, timeout=60.0)
    
    try:
        gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
        logger.info("Gemini client initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize Gemini client: {e}")
        logger.critical("Bot cannot start without Gemini API. Exiting...")
        sys.exit(1)
    
    if config.OPENAI_API_KEY and AsyncOpenAI is not None:
        try:
            openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.warning(f"Не удалось инициализировать OpenAI клиент: {e}")
            openai_client = None
    else:
        logger.info("OpenAI client not configured (optional)")

    try:
        database = Database(config.MONGODB_URI, config.DB_NAME)
        await database.connect()
        users_collection = database.get_collection(config.USERS_COLLECTION)
        asyncio.create_task(database.ensure_indexes(config.USERS_COLLECTION))
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        logger.critical("Bot cannot start without database. Exiting...")
        sys.exit(1)

    dp = Dispatcher()

    dp.include_routers(
        handler_router,
        menu_router,
        session_router,
        test_router,
        portrait_router,
        admin_router,
        onboarding_router,
        profile_router,
    )

    bot = Bot(token=config.TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=None))
    bot._cache = cache
    bot._gemini_circuit = gemini_circuit
    bot._openai_circuit = openai_circuit

    logger.info("Приложение успешно запущено с оптимизациями.")

    async def generate_with_circuit(client, model, contents, system_instruction=None, timeout=10.0, retries=2, backoff_base=0.5):
        return await generate_content_async_with_retry(
            client, model, contents, system_instruction,
            timeout=timeout, retries=retries, backoff_base=backoff_base,
            circuit_breaker=gemini_circuit
        )
    
    async def count_tokens_with_circuit(client, model, contents, timeout=10.0, retries=3, backoff_base=1.0):
        return await count_tokens_async_with_retry(
            client, model, contents,
            timeout=timeout, retries=retries, backoff_base=backoff_base,
            circuit_breaker=gemini_circuit
        )
    
    try:
        health_checker = HealthChecker(
            database=database,
            gemini_circuit=gemini_circuit,
            openai_circuit=openai_circuit
        )
        logger.info("Health checker initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize health checker: {e}")
        health_checker = None
    
    dp.workflow_data.update({
        "gemini_client": gemini_client,
        "gemini_circuit": gemini_circuit,
        "openai_circuit": openai_circuit,
        "generate_content_sync_func": generate_with_circuit,
        "count_tokens_sync_func": count_tokens_with_circuit,
        "openai_client": openai_client,
        "generate_openai_func": generate_openai_chat_async,
        "users_collection": users_collection,
        "database": database,
        "cache": cache,
        "config": config,
        "bot": bot,
        "alert_func": send_alert,
        "health_checker": health_checker,
    })

    try:
        if openai_client is not None:
            asyncio.create_task(_verify_openai_models(bot, openai_client))
        logger.info("Starting bot polling...")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error in bot main loop: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down...")
        try:
            if database:
                await database.close()
        except Exception as e:
            logger.error(f"Error closing database: {e}")
        
        try:
            if bot:
                await bot.session.close()
        except Exception as e:
            logger.error(f"Error closing bot session: {e}")
        
        try:
            if cache:
                await cache.clear()
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
        
        logger.info("Shutdown complete")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске бота: {e}")