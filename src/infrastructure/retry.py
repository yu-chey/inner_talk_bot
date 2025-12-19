import asyncio
import logging
from typing import Callable, TypeVar, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def retry_async(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    delay: float = 0.1,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    **kwargs
) -> T:
    attempt = 0
    last_exception = None
    
    while attempt < max_retries:
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            attempt += 1
            
            if attempt >= max_retries:
                logger.warning(f"Retry failed after {max_retries} attempts: {e}")
                raise
            
            wait_time = delay * (backoff ** (attempt - 1))
            logger.debug(f"Retry attempt {attempt}/{max_retries} after {wait_time:.2f}s: {e}")
            await asyncio.sleep(wait_time)
    
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry failed without exception")


def retry_db_operation(max_retries: int = 3):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                *args,
                max_retries=max_retries,
                delay=0.1,
                backoff=2.0,
                exceptions=(Exception,),
                **kwargs
            )
        return wrapper
    return decorator

