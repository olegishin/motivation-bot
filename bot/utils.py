# 06 - bot/utils.py
# Утилиты и хелперы

import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Dict, Any, Literal

from aiogram import Bot
from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.exceptions import TelegramAPIError

from bot.config import logger, settings, SPECIAL_USER_IDS
from bot.localization import t, Lang
from bot.keyboards import get_payment_keyboard, get_cooldown_keyboard

# --- Константы ---
# 24 часа для проверки демо-периода
DEMO_COOLDOWN_HOURS = 24
# Количество циклов демо-периода
MAX_DEMO_CYCLES = 2
# Длительность одного демо-периода (в днях)
DEMO_DURATION_DAYS = 5
# Тестовый ID для API оплаты
TEST_USER_IDS = settings.TESTER_USER_IDS

# --- Функции ---

def get_user_tz(user_data: Dict[str, Any]) -> ZoneInfo:
    """Возвращает часовой пояс пользователя или дефолтный."""
    tz_key = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    try:
        return ZoneInfo(tz_key)
    except ZoneInfoNotFoundError:
        return ZoneInfo(settings.DEFAULT_TZ_KEY)

def get_user_lang(user_data: Dict[str, Any]) -> Lang:
    """Возвращает язык пользователя или дефолтный."""
    return user_data.get("language", settings.DEFAULT_LANG)

def get_max_demo_cycles() -> int:
    """Возвращает максимальное количество демо-циклов."""
    return MAX_DEMO_CYCLES

def get_cooldown_days() -> float:
    """Возвращает длительность кулдауна в днях."""
    return DEMO_COOLDOWN_HOURS / 24

# 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Приведение типов для безопасного сравнения
def is_admin(chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return str(chat_id) == str(settings.ADMIN_CHAT_ID)

def is_tester(chat_id: int) -> bool:
    """Проверяет, является ли пользователь тестером."""
    # Также проверяем на приведение типов
    return str(chat_id) in [str(uid) for uid in TEST_USER_IDS]

def is_demo_expired(user_data: Dict[str, Any]) -> Literal[False, "cooldown", "final"]:
    """Проверяет статус демо-доступа."""
    
    # 1. Если оплачено, демо не истекло
    if user_data.get("is_paid"):
        return False
        
    now_utc = datetime.now(ZoneInfo("UTC"))
    
    # 2. Если достигнут лимит циклов, это 'final'
    demo_count = user_data.get("demo_count", 0)
    if demo_count >= MAX_DEMO_CYCLES:
        return "final"
        
    # 3. Если есть дата истечения и она в будущем, демо активно
    exp_str = user_data.get("demo_expiration")
    if exp_str:
        try:
            exp_dt = datetime.fromisoformat(exp_str).replace(tzinfo=ZoneInfo("UTC"))
            if exp_dt > now_utc:
                return False
        except Exception:
            pass # Если формат даты неверный, переходим к кулдауну

    # 4. Проверяем кулдаун
    last_demo_end_str = user_data.get("last_demo_end")
    if last_demo_end_str:
        try:
            last_demo_end_dt = datetime.fromisoformat(last_demo_end_str).replace(tzinfo=ZoneInfo("UTC"))
            cooldown_end_dt = last_demo_end_dt + timedelta(hours=DEMO_COOLDOWN_HOURS)
            
            if cooldown_end_dt > now_utc:
                # В режиме кулдауна
                return "cooldown"
        except Exception:
            pass
            
    # 5. Если нет активного демо, нет кулдауна, но есть циклы < MAX_CYCLES, то демо истекло и доступно для активации
    return False # Если демо закончилось, но кулдауна нет, оно доступно для активации


async def safe_send(
    bot: Bot, 
    chat_id: int, 
    text: str, 
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML"
) -> bool:
    """Безопасная отправка сообщения с обработкой блокировки."""
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except TelegramAPIError as e:
        # 403 Forbidden: Бот заблокирован пользователем
        if 'bot was blocked by the user' in str(e) or 'user is deactivated' in str(e):
            from bot.database import db # Ленивый импорт для избежания циклической зависимости
            await db.update_user(chat_id, active=False)
            logger.warning(f"User {chat_id} blocked the bot (auto-set active=False).")
            return False
        elif 'chat not found' in str(e) or 'user not found' in str(e):
            logger.error(f"Chat/User {chat_id} not found: {e}")
            return False
        else:
            logger.error(f"Telegram API Error sending to {chat_id}: {e}")
            return False
    except Exception as e:
        logger.error(f"Unknown error sending to {chat_id}: {e}")
        return False