import motor.motor_asyncio
from typing import Optional
import logging
import asyncio
from .retry import retry_async

logger = logging.getLogger(__name__)


class Database:
    
    def __init__(self, mongodb_uri: str, db_name: str):
        self.mongodb_uri = mongodb_uri
        self.db_name = db_name
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
    
    async def connect(self, max_retries: int = 5, retry_delay: float = 2.0):
        for attempt in range(max_retries):
            try:
                self.client = motor.motor_asyncio.AsyncIOMotorClient(
                    self.mongodb_uri,
                    maxPoolSize=50,
                    minPoolSize=5,
                    maxIdleTimeMS=45000,
                    retryWrites=True,
                    retryReads=True,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=60000,
                    waitQueueTimeoutMS=30000,
                    heartbeatFrequencyMS=10000
                )
                self.db = self.client[self.db_name]
                await self.client.admin.command('ping')
                logger.info("MongoDB connected with optimized connection pooling")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(f"MongoDB connection failed after {max_retries} attempts: {e}")
                    raise
    
    async def close(self):
        if self.client is not None:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    def get_collection(self, collection_name: str):
        if self.db is None:
            raise RuntimeError("Database not connected")
        return self.db[collection_name]
    
    async def ensure_indexes(self, collection_name: str):
        collection = self.get_collection(collection_name)
        try:
            await collection.create_index([("user_id", 1), ("type", 1), ("timestamp", -1)])
            await collection.create_index([("type", 1), ("timestamp", -1)])
            await collection.create_index([("user_id", 1), ("timestamp", -1)])
            await collection.create_index([("type", 1), ("user_id", 1)])
            await collection.create_index([("type", 1), ("last_active", -1)])
            await collection.create_index([("type", 1), ("created_at", -1)])
            await collection.create_index([("type", 1), ("last_portrait_timestamp", -1)])
            await collection.create_index([("user_id", 1), ("type", 1), ("generated_at", -1)])
            
            await collection.create_index([("user_id", 1), ("type", 1), ("date", -1)])
            await collection.create_index([("type", 1), ("date", -1)])
            
            await collection.create_index([("user_id", 1), ("type", 1), ("finished_at", -1)])
            await collection.create_index([("user_id", 1), ("type", 1), ("test_id", 1)])
            
            logger.info(f"Optimized indexes created for {collection_name}")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    async def find_one_with_retry(self, collection_name: str, filter_dict: dict, **kwargs):
        collection = self.get_collection(collection_name)
        return await retry_async(
            collection.find_one,
            filter_dict,
            max_retries=3,
            delay=0.1,
            exceptions=(Exception,),
            **kwargs
        )
    
    async def insert_one_with_retry(self, collection_name: str, document: dict):
        collection = self.get_collection(collection_name)
        return await retry_async(
            collection.insert_one,
            document,
            max_retries=3,
            delay=0.1,
            exceptions=(Exception,)
        )
    
    async def update_one_with_retry(self, collection_name: str, filter_dict: dict, update_dict: dict, **kwargs):
        collection = self.get_collection(collection_name)
        return await retry_async(
            collection.update_one,
            filter_dict,
            update_dict,
            max_retries=3,
            delay=0.1,
            exceptions=(Exception,),
            **kwargs
        )
