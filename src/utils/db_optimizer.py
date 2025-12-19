import asyncio
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


async def batch_find_one(
    collection,
    filters: List[Dict[str, Any]],
    projection: Optional[Dict] = None
) -> List[Optional[Dict]]:
    if not filters:
        return []
    
    async def find_one(filter_dict):
        try:
            return await collection.find_one(filter_dict, projection)
        except Exception as e:
            logger.error(f"Error in batch find_one: {e}")
            return None
    
    results = await asyncio.gather(*[find_one(f) for f in filters], return_exceptions=True)
    
    processed_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Exception in batch_find_one: {r}")
            processed_results.append(None)
        else:
            processed_results.append(r)
    
    return processed_results


async def batch_insert(
    collection,
    documents: List[Dict[str, Any]],
    ordered: bool = False
) -> int:
    if not documents:
        return 0
    
    try:
        result = await collection.insert_many(documents, ordered=ordered)
        return len(result.inserted_ids)
    except Exception as e:
        logger.error(f"Error in batch_insert: {e}")
        inserted = 0
        for doc in documents:
            try:
                await collection.insert_one(doc)
                inserted += 1
            except Exception:
                pass
        return inserted


async def batch_update(
    collection,
    updates: List[tuple[Dict[str, Any], Dict[str, Any]]],
    upsert: bool = False
) -> int:
    if not updates:
        return 0
    
    async def update_one(filter_dict, update_dict):
        try:
            result = await collection.update_one(filter_dict, update_dict, upsert=upsert)
            return result.modified_count
        except Exception as e:
            logger.error(f"Error in batch update_one: {e}")
            return 0
    
    results = await asyncio.gather(*[update_one(f, u) for f, u in updates], return_exceptions=True)
    
    total_modified = sum(r for r in results if isinstance(r, int))
    return total_modified

