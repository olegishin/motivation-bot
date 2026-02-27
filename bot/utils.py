# 05 - bot/utils.py
# ✅ Вспомогательные функции (форматирование, защита от JSON-строк)
# ✅ Проверка демо-статуса (формула 3+1+3)
# ✅ Система уровней для челленджей
# ✅ AccessMiddleware (проверка доступа, Smart Ban 24h)
# ✅ Безопасная отправка сообщений

# 05 - bot/utils.py - ФИНАЛЬНАЯ ВЕРСИЯ (30.01.2026)
# Вспомогательные утилиты + Middlewares
# ✅ ПРОВЕРЕНО: Smart Ban 24h, Логика 3+1+3, Система уровней
# 05 - bot/utils.py - ФИНАЛЬНАЯ ВЕРСИЯ (26.02.2026)
# Системные утилиты и Middlewares
# ✅ ПРОВЕРЕНО: Очищено от бизнес-логики (уровни перенесены)

import asyncio
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Optional

from aiogram import Bot, BaseMiddleware
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from bot.config import settings, logger
from bot.localization import t, Lang

# --- 🛡️ ЗАЩИТНЫЕ ФУНКЦИИ ---

def _ensure_dict(data: Any) -> dict:
    """Рекурсивная распаковка вложенных JSON-строк."""
    if not data: return {}
    if isinstance(data, dict): return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return _ensure_dict(parsed)
        except: return {}
    return {}

def format_phrase(phrase: str, name: str) -> str:
    """Безопасная подстановка имени в тексты."""
    if not phrase: return ""
    try:
        return phrase.format(name=name)
    except Exception as e:
        logger.error(f"Utils: Format error: {e}")
        return phrase.replace("{name}", name)

# --- 🚀 УПРАВЛЕНИЕ ДОСТУПОМ ---

def get_demo_config(user_id: int) -> dict:
    """Настройки демо с учетом админа."""
    if int(user_id) == int(settings.ADMIN_CHAT_ID):
        return {"demo": 365, "cooldown": 0}
    return {
        "demo": settings.REGULAR_DEMO_DAYS,
        "cooldown": settings.REGULAR_COOLDOWN_DAYS
    }

async def is_demo_expired(user_data: dict) -> bool:
    """Асинхронная проверка истечения демо-периода."""
    if user_data.get("is_paid"): return False
    exp_str = user_data.get("demo_expiration")
    if not exp_str: return True
    try:
        exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp_dt
    except: return True

def get_user_lang(user_data: dict) -> Lang:
    """Определение языка пользователя."""
    lang = user_data.get("language", settings.DEFAULT_LANG)
    return lang if lang in ("ru", "ua", "en") else settings.DEFAULT_LANG

def get_user_tz(user_data: dict):
    """Получение объекта ZoneInfo для пользователя."""
    tz_name = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    try: return ZoneInfo(tz_name)
    except: return ZoneInfo(settings.DEFAULT_TZ_KEY)

# --- 📤 БЕЗОПАСНАЯ ОТПРАВКА ---

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    """Отправка сообщения с обработкой блокировок и Flood лимитов."""
    try:
        return await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, **kwargs)
    except TelegramForbiddenError:
        logger.warning(f"SafeSend: User {chat_id} blocked bot.")
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await safe_send(bot, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"SafeSend: Error to {chat_id}: {e}")
    return None

def get_progress_bar(percent: int, length: int = 10) -> str:
    """Визуальный прогресс-бар (0-100%)."""
    filled = max(0, min(length, percent // 10))
    return "🟩" * filled + "⬜" * (length - filled)

# --- 🧠 ACCESS MIDDLEWARE ---

class AccessMiddleware(BaseMiddleware):
    """
    Middleware для проверки статуса пользователя перед каждым хендлером.
    Инжектирует user_data, lang и admin-статус.
    """
    def __init__(self, users_db: dict, static_data: dict):
        self.users_db = users_db
        self.static_data = static_data
        super().__init__()

    async def __call__(self, handler, event: Message, data: dict):
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        from bot.database import db
        
        # Получаем свежие данные из БД
        user_data = await db.get_user(user_id)
        if not user_data:
            return await handler(event, data)

        # 1. SMART BAN (проверка блокировки на 24 часа)
        active_val = user_data.get("active")
        if isinstance(active_val, str) and len(active_val) > 5:
            try:
                ban_dt = datetime.fromisoformat(active_val.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < ban_dt:
                    h = int((ban_dt - datetime.now(timezone.utc)).total_seconds() // 3600)
                    lang = get_user_lang(user_data)
                    await event.answer(t("ban_timeout_msg", lang, h=h, m=0), parse_mode=ParseMode.HTML)
                    return
                else:
                    await db.update_user(user_id, active=1)
            except: pass

        # 2. DEMO LOGIC (авто-переход в cooldown)
        lang = get_user_lang(user_data)
        if await is_demo_expired(user_data) and not user_data.get("is_paid"):
            if user_data.get("status") != "cooldown":
                await db.update_user(user_id, status="cooldown", active=0)
                user_data["status"] = "cooldown"
                user_data["active"] = 0

        # 3. Инъекция данных в контекст хендлера
        data["user_data"] = user_data
        data["lang"] = lang
        data["is_admin"] = (int(user_id) == int(settings.ADMIN_CHAT_ID))
        data["static_data"] = self.static_data
        
        return await handler(event, data)