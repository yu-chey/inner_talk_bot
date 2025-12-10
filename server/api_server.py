from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
import logging

from . import db_stats
from . import config

logger = logging.getLogger(__name__)


class TotalStats(BaseModel):
    unique_username_count: int = Field(description="Общее число уникальных пользователей по username.")


class UserStats(BaseModel):
    username: str
    total_user_texts: int = Field(description="Количество сообщений с type='user_text' от этого пользователя.")

    class Config:
        from_attributes = True


app = FastAPI(
    title="InnerTalk Statistics API",
    description="API для мониторинга и выгрузки статистики пользователей InnerTalk Bot."
)


@app.on_event("startup")
async def startup_event():
    """Инициализация DB при запуске сервера."""
    db_stats.init_db_for_stats()
    if db_stats.users_data_collection is None:
        logger.error("API не смог подключиться к MongoDB.")


@app.on_event("shutdown")
def shutdown_event():
    """Закрытие соединения с DB при остановке сервера."""
    if db_stats.mongo_client:
        db_stats.mongo_client.close()
        logger.info("Соединение с MongoDB закрыто.")


@app.get("/stats/total", response_model=TotalStats)
async def get_total_stats_data():
    """Получает общие статистические данные."""
    stats, status_code = await db_stats.get_total_stats()

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=stats.get("error", "Failed to retrieve stats."))

    return stats


@app.get("/stats/user/{username}", response_model=UserStats)
async def get_user_data(username: str):
    clean_username = username.lstrip('@')

    stats, status_code = await db_stats.get_user_stats(clean_username)

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=stats.get("error", "Database error."))


    return stats

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT
    )