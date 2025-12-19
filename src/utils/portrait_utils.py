import asyncio
import logging

logger = logging.getLogger(__name__)


def sanitize_portrait_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    s = text
    for m in ("**", "__", "*", "_", "`"):
        s = s.replace(m, "")
    s = "\n".join(line.lstrip("- ") for line in s.splitlines())
    s = s.replace("•", "- ").replace("–", "-")
    lowers = ["example text", "template", "placeholder", "пример текста", "пример", "заглушка"]
    for token in lowers:
        s = s.replace(token, "")
        s = s.replace(token.title(), "")
        s = s.replace(token.upper(), "")
    lines = [ln.rstrip() for ln in s.splitlines()]
    cleaned = []
    empty_streak = 0
    for ln in lines:
        if ln.strip() == "":
            empty_streak += 1
            if empty_streak <= 2:
                cleaned.append("")
        else:
            empty_streak = 0
            cleaned.append(ln)
    s = "\n".join(cleaned).strip()
    return s


async def update_portrait_caption_animation(bot, chat_id: int, message_id: int, stop_event: asyncio.Event):
    animation_texts = [
        "👂 Внимательно слушаю вашу историю...",
        "🧠 Сканирую ключевые слова и эмоции...",
        "📊 Ищу повторяющиеся паттерны...",
        "🔬 Анализирую когнитивные искажения...",
        "⚖️ Взвешиваю потребности и ценности...",
        "💡 Формулирую финальный совет..."
    ]
    delay = 1.2

    try:
        while not stop_event.is_set():
            for text_frame in animation_texts:
                if stop_event.is_set():
                    break

                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=text_frame
                    )
                except Exception as e:
                    if "message is not modified" not in str(e).lower():
                        return

                await asyncio.sleep(delay)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in update_portrait_caption_animation: {e}")

