import asyncio
import time
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SimpleCache:
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
    
    async def delete(self, key: str):
        if key in self._cache:
            del self._cache[key]
    
    async def clear(self):
        self._cache.clear()
    
    async def start_cleanup_task(self, interval: int = 60):
        if self._cleanup_task and not self._cleanup_task.done():
            return
        
        async def cleanup():
            while True:
                try:
                    await asyncio.sleep(interval)
                    current_time = time.time()
                    expired_keys = [
                        key for key, (_, expiry) in self._cache.items()
                        if current_time > expiry
                    ]
                    for key in expired_keys:
                        del self._cache[key]
                    if expired_keys:
                        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in cache cleanup: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup())
    
    def get_stats(self) -> Dict[str, Any]:
        current_time = time.time()
        valid_entries = sum(1 for _, expiry in self._cache.values() if current_time <= expiry)
        expired_entries = len(self._cache) - valid_entries
        
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "hit_rate": 0.0
        }
