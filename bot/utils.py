# 05 - bot/utils.py
# Исправленная версия: Разрешает нажатие кнопок новым пользователям
# Исправленная версия: Защита от JSON-строк + Логика Демо
# Исправленная версия: Защита от JSON-строк + Улучшенная логика Демо
# Исправленная версия: Защита от JSON + Допуск к кнопкам при истекшем демо
# Финальная версия (Логика 5+1+5)
# Финальная версия: Исправлены имена (БЕЗ "Друга") + Логика 5+1+5

import logging
import json
from typing import Dict, Any, Union, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from bot.config import settings, logger
from bot.database import db
from bot.localization import t, Lang

# --- 🛡️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def _ensure_dict(data: Any) -> dict:
    if isinstance(data, dict): return data
    if isinstance(data, str):
        try:
            curr = data
            for _ in range(5):
                if isinstance(curr, dict): return curr
                curr = json.loads(curr)
            return curr if isinstance(curr, dict) else {}
        except: return {}
    return {}

def get_user_tz(user_data: Any) -> ZoneInfo:
    user_data = _ensure_dict(user_data)
    try:
        tz_key = user_data.get("timezone")
        if tz_key: return ZoneInfo(tz_key)
        return ZoneInfo(settings.DEFAULT_TZ_KEY)
    except: return ZoneInfo(settings.DEFAULT_TZ_KEY)

def get_user_lang(user_data: Any) -> str:
    user_data = _ensure_dict(user_data)
    return user_data.get("language", settings.DEFAULT_LANG)

# --- 🧠 ЛОГИКА 5+1+5 (МАТРЕШКА) ---

def get_demo_config(user_id: int) -> dict:
    """Возвращает настройки длительности в зависимости от ID."""
    if user_id == 290711961:
        return {"demo": 3, "cooldown": 1}
    if user_id in settings.TESTER_USER_IDS:
        return {"demo": settings.TESTER_DEMO_DAYS, "cooldown": settings.TESTER_COOLDOWN_DAYS}
    return {"demo": settings.REGULAR_DEMO_DAYS, "cooldown": settings.REGULAR_COOLDOWN_DAYS}

def check_demo_status(user_data: Any) -> bool:
    """
    False — доступ ОТКРЫТ (контент доступен).
    True — доступ ЗАКРЫТ (пауза или финал).
    """
    user_data = _ensure_dict(user_data)
    if user_data.get("is_paid"): return False
    
    user_id = user_data.get("user_id")
    expiry_str = user_data.get("demo_expiration")
    if not expiry_str: return True

    try:
        now = datetime.now(timezone.utc)
        expiry_date = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
        demo_count = user_data.get("demo_count", 1)
        config = get_demo_config(user_id)

        # 1. Если время еще не вышло — доступ есть
        if now <= expiry_date:
            return False

        # 2. Если время вышло и это был первый период (Демо 1)
        if demo_count == 1:
            cooldown_end = expiry_date + timedelta(days=config["cooldown"])
            if now <= cooldown_end:
                return True
            else:
                return False 
        
        # 3. Если demo_count >= 2 и время вышло — финал (True)
        return True
    except: 
        return True

async def is_demo_expired(user_data: Any) -> bool:
    return check_demo_status(user_data)

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as e:
        if 'bot was blocked' in str(e):
            await db.update_user(chat_id, active=False)
        return False

# --- 🛡️ MIDDLEWARE (КОНТРОЛЬ ДОСТУПА) ---

class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        from bot.keyboards import get_reply_keyboard_for_user
        
        user = getattr(event, 'from_user', None)
        if not user: return await handler(event, data)
        chat_id = user.id

        user_data = await db.get_user(chat_id)
        if not user_data:
            return await handler(event, data)

        user_data = _ensure_dict(user_data)
        lang = get_user_lang(user_data)
        # Динамически берем имя пользователя из базы
        user_name = user_data.get("name") or ""
        
        is_admin = (chat_id == settings.ADMIN_CHAT_ID)
        is_paid = user_data.get("is_paid", False)
        
        if is_paid or is_admin:
            data.update({"user_data": user_data, "lang": lang, "is_admin": is_admin, "is_paid": is_paid})
            return await handler(event, data)

        now = datetime.now(timezone.utc)
        expiry_str = user_data.get("demo_expiration")
        expiry_date = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc) if expiry_str else now
        demo_count = user_data.get("demo_count", 1)
        config = get_demo_config(chat_id)

        # 1. ПЕРЕХОД ИЗ ПАУЗЫ В ДЕМО 2
        if demo_count == 1 and now > (expiry_date + timedelta(days=config["cooldown"])):
            new_expiry = now + timedelta(days=config["demo"])
            
            await db.update_user(chat_id, 
                demo_count=2, 
                demo_expiration=new_expiry.isoformat(),
                challenge_streak=0,
                challenge_accepted=0,
                challenges=[],
                sent_expiry_warning=0
            )
            
            # ИСПРАВЛЕНО: передаем реальное имя
            await safe_send(data["bot"], chat_id, t("demo_restarted_info", lang, name=user_name))
            user_data = await db.get_user(chat_id)

        # 2. ПРОВЕРКА СТАТУСА ДОСТУПА
        is_expired = check_demo_status(user_data)
        
        if is_expired:
            allowed = [t('btn_pay_premium', lang), t('btn_profile', lang), t('btn_settings', lang)]
            text = getattr(event, 'text', '')
            
            if text.startswith('/') or text in allowed or isinstance(event, CallbackQuery):
                data.update({"user_data": user_data, "lang": lang, "is_admin": False, "is_paid": False})
                return await handler(event, data)

            # Сообщения о блокировке
            if demo_count == 1 and now <= (expiry_date + timedelta(days=config["cooldown"])):
                remaining = (expiry_date + timedelta(days=config["cooldown"])) - now
                hours_left = int(remaining.total_seconds() // 3600)
                # ИСПРАВЛЕНО: передаем имя
                msg = t("demo_cooldown_msg", lang, name=user_name, hours=max(1, hours_left))
            else:
                # ИСПРАВЛЕНО: передаем имя
                msg = t("demo_expired_final", lang, name=user_name)

            if isinstance(event, Message):
                await safe_send(data["bot"], chat_id, msg, reply_markup=get_reply_keyboard_for_user(chat_id, lang, user_data))
            return

        data.update({"user_data": user_data, "lang": lang, "is_admin": False, "is_paid": False})
        return await handler(event, data)