# bot/middlewares.py

from datetime import datetime
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from database import db
from zoneinfo import ZoneInfo # ✅ ДОБАВЛЕНО

class TrackActivityMiddleware(BaseMiddleware):
    """
    Мидлварь для отслеживания активности пользователя.
    Обновляет last_active при каждом действии.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        
        if user:
            # ✅ ИСПРАВЛЕНО: Используем UTC для консистентности
            now_utc = datetime.now(ZoneInfo("UTC")).isoformat() 
            
            # Пишем в базу, что юзер жив и активен прямо сейчас
            await db.update_user(
                user.id, 
                last_active=now_utc,
                is_active=True,
                username=user.username,
                first_name=user.first_name
            )
            
        return await handler(event, data)