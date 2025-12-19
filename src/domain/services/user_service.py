from typing import Optional, Dict
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class UserService:
    
    def __init__(self, users_collection, cache=None):
        self.collection = users_collection
        self.cache = cache
    
    async def get_user_profile(self, user_id: int) -> Optional[Dict]:
        cache_key = f"user_profile:{user_id}"
        
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
        
        try:
            profile = await self.collection.find_one(
                {"user_id": user_id, "type": "user_profile"}
            )
            
            if self.cache and profile:
                await self.cache.set(cache_key, profile, ttl=300)
            
            return profile
        except Exception as e:
            logger.error(f"Error loading user profile: {e}")
            return None
    
    async def update_user_profile(self, user_id: int, update_data: Dict):
        try:
            await self.collection.update_one(
                {"user_id": user_id, "type": "user_profile"},
                {"$set": update_data},
                upsert=True
            )
            
            if self.cache:
                await self.cache.delete(f"user_profile:{user_id}")
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
            raise
    
    async def save_user_profile_async(self, user_id: int, username: Optional[str], 
                                     first_name: Optional[str]):
        try:
            await self.collection.update_one(
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
            
            if self.cache:
                await self.cache.delete(f"user_profile:{user_id}")
        except Exception as e:
            logger.error(f"Error saving user profile: {e}")

