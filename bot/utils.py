# 05 - bot/utils.py
# Утилиты и Middleware

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Dict, Any, Callable, Awaitable, Optional
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, Update
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

# ✅ ИСПРАВЛЕНО: Импорты с префиксом bot.
from bot.config import logger, settings, DEFAULT_TZ, SPECIAL_USER_IDS
from bot.localization import t, Lang
from bot.database import db

# =====================================================
# 1. Вспомогательные функции
# =====================================================

def is_admin(chat_id: int) -> bool:
    return chat_id == settings.ADMIN_CHAT_ID

def is_demo_expired(user_data: dict) -> bool:
    if not user_data: return True
    if user_data.get("is_paid"): return False
    demo_exp = user_data.get("demo_expiration")
    if not demo_exp: return True 
    try:
        expiration_dt = datetime.fromisoformat(demo_exp).replace(tzinfo=ZoneInfo("UTC"))
        return datetime.now(ZoneInfo("UTC")) > expiration_dt
    except (ValueError, TypeError):
        return True

def get_user_lang(user_data: dict) -> Lang:
    lang_code = user_data.get("language", settings.DEFAULT_LANG)
    if lang_code not in ("ru", "ua", "en"):
        return settings.DEFAULT_LANG
    return lang_code # type: ignore

def get_user_tz(user_data: dict) -> ZoneInfo:
    user_tz_key = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    try:
        return ZoneInfo(user_tz_key)
    except ZoneInfoNotFoundError:
        return DEFAULT_TZ 

def get_tz_from_lang(lang_code: str | None) -> str:
    if not lang_code: return settings.DEFAULT_TZ_KEY
    lang_code = lang_code.lower()
    if lang_code.startswith('ru'): return "Europe/Moscow"
    if lang_code.startswith('ua'): return "Europe/Kiev"
    return settings.DEFAULT_TZ_KEY

# --- Хелперы для ролей ---
def get_demo_days(chat_id: int) -> int:
    if chat_id in settings.SIMULATOR_USER_IDS: return 2
    if chat_id in settings.TESTER_USER_IDS: return settings.TESTER_DEMO_DAYS
    return settings.REGULAR_DEMO_DAYS

def get_cooldown_days(chat_id: int) -> int:
    if chat_id in settings.SIMULATOR_USER_IDS: return 1
    if chat_id in settings.TESTER_USER_IDS: return settings.TESTER_COOLDOWN_DAYS
    return settings.REGULAR_COOLDOWN_DAYS

def get_max_demo_cycles(chat_id: int) -> int:
    if chat_id in settings.SIMULATOR_USER_IDS: return 2
    if chat_id in settings.TESTER_USER_IDS: return 999
    return settings.MAX_DEMO_CYCLES

# =====================================================
# 2. Безопасная отправка
# =====================================================

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    try:
        if "parse_mode" not in kwargs:
            kwargs["parse_mode"] = "HTML"
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return True
    except TelegramForbiddenError:
        logger.warning(f"Bot blocked by {chat_id}.")
        await db.update_user(chat_id, active=False) 
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await safe_send(bot, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Error sending to {chat_id}: {e}")
    return False


# =====================================================
# 3. Middleware
# =====================================================

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        
        user = None
        message = None
        
        if event.message:
            user = event.message.from_user
            message = event.message
        elif event.callback_query:
            user = event.callback_query.from_user
            message = event.callback_query.message

        if not user:
            return await handler(event, data)

        chat_id = user.id
        
        # 1. Достаем свежие данные из БД
        user_data = await db.get_user(chat_id)
        is_new_user = not bool(user_data)
        
        # 2. Если юзера нет в БД — создаем на лету (Чтобы кнопки работали у старых юзеров и админа)
        if is_new_user:
            lang_code = user.language_code if user.language_code in ["ru", "ua", "en"] else "ru"
            await db.add_user(
                user_id=chat_id,
                username=user.username,
                full_name=user.first_name, 
                language=lang_code,
                timezone=get_tz_from_lang(lang_code)
            )
            user_data = await db.get_user(chat_id)

        # 3. 🔥 Обновляем глобальный кэш (чтобы админ видел актуальную стату сразу)
        if "users_db" in data:
            data["users_db"][str(chat_id)] = user_data

        lang = get_user_lang(user_data)
        is_admin_flag = is_admin(chat_id)

        data.update({
            "user_data": user_data,
            "lang": lang,
            "is_admin": is_admin_flag,
            "is_new_user": is_new_user
        })

        # 4. Логика проверки доступа (Demo / Paid)
        if message and hasattr(message, 'text') and message.text:
            text = message.text

            # Если забанен
            if user_data.get("active") is False and not is_admin_flag:
                return

            # Админы, тестеры и платные проходят всегда
            if is_admin_flag or chat_id in SPECIAL_USER_IDS or user_data.get("is_paid", False):
                return await handler(event, data)

            allowed_cmds = ("/start", "/language", "/timezone", "/cancel", "/pay")
            allowed_btns = (
                t('btn_pay_premium', lang),
                t('btn_pay_api_test_premium', lang),
                t('btn_want_demo', lang),
                t('cmd_cancel', lang)
            )

            if any(text.startswith(cmd) for cmd in allowed_cmds) or text in allowed_btns:
                return await handler(event, data)

            if not is_demo_expired(user_data):
                return await handler(event, data)

            logger.info(f"Access denied for {chat_id} — demo expired")
            
            # ✅ ИСПРАВЛЕНО: Импорт ВНУТРИ функции, чтобы избежать циклической зависимости
            from bot.content_handlers import handle_expired_demo
            await handle_expired_demo(message, user_data, lang)
            return

        return await handler(event, data)