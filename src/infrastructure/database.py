import motor.motor_asyncio
from typing import Optional
import logging
from .retry import retry_async

logger = logging.getLogger(__name__)


class Database:
    
    def __init__(self, mongodb_uri: str, db_name: str):
        self.mongodb_uri = mongodb_uri
        self.db_name = db_name
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
    
    async def connect(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            self.mongodb_uri,
            maxPoolSize=50,
            minPoolSize=10,
            maxIdleTimeMS=45000,
            retryWrites=True,
            retryReads=True,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
            waitQueueTimeoutMS=10000
        )
        self.db = self.client[self.db_name]
        logger.info("MongoDB connected with optimized connection pooling")
    
    async def close(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    def get_collection(self, collection_name: str):
        if not self.db:
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
