import datetime
from .config import CHAT_COLLECTION, HISTORY_LIMIT, BAN_COLLECTION

db = None

async def save_message(user_id: int, role: str, text: str):
    if db is not None:
        await db[CHAT_COLLECTION].insert_one({
            "user_id": user_id,
            "role": role,
            "text": text,
            "timestamp": datetime.datetime.now()
        })

async def ban_user(user_id: int, full_name: str):
    if db is not None:
        await db[BAN_COLLECTION].insert_one({
            "user_id": user_id,
            "full_name": full_name,
            "timestamp": datetime.datetime.now()
        })

async def get_banned_users():
    if db is None:
        return []

    banned_users = db[BAN_COLLECTION]

    return banned_users


async def get_chat_history(user_id: int):
    if db is None:
        return []

    system_msg = await db[CHAT_COLLECTION].find_one(
        {"user_id": user_id, "role": "system_prompt"}
    )

    cursor = db[CHAT_COLLECTION].find(
        {"user_id": user_id, "role": {"$ne": "system_prompt"}}
    ).sort("timestamp", -1).limit(HISTORY_LIMIT)

    dialog_history_reversed = await cursor.to_list(length=HISTORY_LIMIT)
    dialog_history = dialog_history_reversed[::-1]

    full_history = []
    if system_msg:
        full_history.append(system_msg)

    full_history.extend(dialog_history)

    return full_history


async def clear_chat_history(user_id: int):
    if db is not None:
        result = await db[CHAT_COLLECTION].delete_many({
            "user_id": user_id,
            "role": {"$ne": "system_prompt"}
        })
        return result.deleted_count
    return 0

# реализовал, но нигде не применяется
async def unban_user(user_id: int):
    if db is not None:
        await db[BAN_COLLECTION].delete_one({
            "user_id": user_id
        })