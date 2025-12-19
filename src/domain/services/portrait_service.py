from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
import logging

from src import config
from src.presentation import keyboards, photos
from src.utils.portrait_utils import sanitize_portrait_text, update_portrait_caption_animation
import asyncio

logger = logging.getLogger(__name__)


class PortraitService:
    
    def __init__(self, users_collection, cache=None):
        self.collection = users_collection
        self.cache = cache
    
    async def check_cooldown(self, user_id: int) -> Dict:
        current_time = datetime.now(timezone.utc)
        
        user_doc = await self.collection.find_one(
            {"user_id": user_id, "type": "user_profile"}
        )
        
        last_portrait_timestamp = None
        if user_doc and isinstance(user_doc.get("last_portrait_timestamp"), datetime):
            last_portrait_timestamp = user_doc.get("last_portrait_timestamp")
            if last_portrait_timestamp.tzinfo is None:
                last_portrait_timestamp = last_portrait_timestamp.replace(tzinfo=timezone.utc)
        
        if not last_portrait_timestamp:
            return {"on_cooldown": False, "portrait": None, "time_left": None}
        
        cooldown_end_time = last_portrait_timestamp + timedelta(hours=config.PORTRAIT_COOLDOWN_HOURS)
        
        if current_time < cooldown_end_time:
            time_left = cooldown_end_time - current_time
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            
            last_portrait_doc = await self.collection.find_one(
                {"user_id": user_id, "type": "portrait"},
                sort=[("generated_at", -1)]
            )
            
            portrait_text = None
            generated_at = None
            if last_portrait_doc and last_portrait_doc.get("portrait_text"):
                portrait_text = last_portrait_doc.get("portrait_text")
                generated_at = last_portrait_doc.get("generated_at")
            
            return {
                "on_cooldown": True,
                "portrait": portrait_text,
                "generated_at": generated_at,
                "time_left": {"hours": hours, "minutes": minutes}
            }
        
        return {"on_cooldown": False, "portrait": None, "time_left": None}
    
    async def show_last_portrait(self, callback: CallbackQuery, portrait_text: str, 
                                time_left: Dict, generated_at: Optional[datetime], state):
        cooldown_info = (
            f"⚠️ Психологический портрет можно создавать не чаще, чем раз в {config.PORTRAIT_COOLDOWN_HOURS} часа.\n"
            f"Повторная попытка будет доступна через {time_left['hours']} ч. {time_left['minutes']} мин.\n\n"
        )
        
        if generated_at:
            date_str = generated_at.strftime("%d.%m.%Y в %H:%M")
            cooldown_info += f"📅 Последний портрет был сгенерирован {date_str} (UTC)\n\n"
        
        cooldown_info += "---\n\n"
        header = "Ваш Психологический Портрет: 🧠\n\n"
        full_text = f"{cooldown_info}{header}{portrait_text}"
        
        pages = self._split_into_pages(full_text)
        total_pages = max(1, len(pages))
        current_page = 1
        
        await state.update_data(
            portrait_pages=pages,
            portrait_page_idx=current_page,
            portrait_message_id=callback.message.message_id
        )
        
        new_media = InputMediaPhoto(
            media=photos.portrait_photo,
            caption=pages[0] if pages else full_text
        )
        
        try:
            await callback.message.edit_media(
                media=new_media,
                reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
            )
        except TelegramBadRequest:
            try:
                await callback.message.edit_caption(
                    caption=pages[0] if pages else full_text,
                    reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
                )
            except TelegramBadRequest:
                await callback.message.answer_photo(
                    photo=photos.portrait_photo,
                    caption=pages[0] if pages else full_text,
                    reply_markup=keyboards.portrait_pagination_keyboard(current_page, total_pages)
                )
    
    def _split_into_pages(self, text: str, max_len: int = 1000) -> List[str]:
        pages = []
        text_left = text
        while text_left:
            chunk = text_left[:max_len]
            if len(text_left) > max_len:
                last_nl = chunk.rfind("\n")
                last_space = chunk.rfind(" ")
                cut_at = max(last_nl, last_space)
                if cut_at > 200:
                    chunk = chunk[:cut_at]
            pages.append(chunk)
            text_left = text_left[len(chunk):]
        return pages
    
    async def save_portrait(self, user_id: int, portrait_text: str):
        try:
            await self.collection.insert_one({
                "user_id": user_id,
                "type": "portrait",
                "portrait_text": portrait_text,
                "generated_at": datetime.now(timezone.utc)
            })
            
            await self.collection.update_one(
                {"user_id": user_id, "type": "user_profile"},
                {"$set": {"last_portrait_timestamp": datetime.now(timezone.utc)}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving portrait: {e}")
            raise

