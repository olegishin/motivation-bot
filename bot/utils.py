# 05 - bot/utils.py
# Исправленная версия: Разрешает нажатие кнопок новым пользователям
# Исправленная версия: Защита от JSON-строк + Логика Демо
# Исправленная версия: Защита от JSON-строк + Улучшенная логика Демо
# Исправленная версия: Защита от JSON + Допуск к кнопкам при истекшем демо
# Финальная версия (Логика 5+1+5)
# Финальная версия: Исправлены имена (БЕЗ "Друга") + Логика 5+1+5
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс синхронизации языка и лимитов
# Финальная версия: Асинхронная база + безопасные фолбеки имени
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Авто-регистрация новых юзеров + Логика 5+1+5
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс Бана + Логика 5+1+5 + Защита от JSON
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Smart Ban 24h + Логика 5+1+5 + Защита от JSON
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Smart Ban 24h (Мультиязычный) + Логика 5+1+5 + Защита от JSON
# ГРУППА 2: Логирование ошибок + сохранение всей Ультимативной логики (Smart Ban, 5+1+5, Middleware)
# FIX (2026-01-13): Исправлен язык сообщений в режиме "тишины" (cooldown)
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Smart Ban 24h + Логика 5+1+5 + Защита от JSON
# ПОЛНАЯ СВЕРКА: Сохранены Middleware, авто-регистрация и лимиты
# FIX (2026-01-14): Расширен список разрешенных кнопок в режиме тишины (RU/UA/EN)
# Утилиты, middleware и проверки демо
# ✅ ИСПРАВЛЕНО (2026-01-16):
#    - Убрана автоматическая регистрация в middleware (Ошибка #4)
#    - Логирование на каждом шаге
#    - Middleware теперь только получает пользователя, не создает его
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Smart Ban 24h + Логика 5+1+5 + Защита от JSON
# ✅ ИСПРАВЛЕНО (2026-01-26): 
#    - Функция is_demo_expired сделана асинхронной для совместимости с планировщиком
#    - Middleware обновлен для работы с асинхронными проверками
#    - Сохранена вся логика Smart Ban и Middleware из исходника

import json
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from bot.config import settings, logger
from bot.database import db
from bot.localization import t

# --- 🛡️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def _ensure_dict(data: Any) -> dict:
    """Безопасная распаковка JSON с глубокой проверкой на вложенные строки."""
    if isinstance(data, dict):
        return data
    if isinstance(data, str) and data.strip():
        try:
            curr = json.loads(data)
            while isinstance(curr, str):
                curr = json.loads(curr)
            return curr if isinstance(curr, dict) else {}
        except Exception as e:
            logger.error(f"Utils: Ошибка распаковки JSON: {e}")
            return {}
    return {}

def get_user_tz(user_data: Any) -> ZoneInfo:
    """Определяет часовой пояс пользователя."""
    user_data = _ensure_dict(user_data)
    tz_key = user_data.get("timezone")
    try:
        return ZoneInfo(tz_key) if tz_key else ZoneInfo(settings.DEFAULT_TZ_KEY)
    except Exception as e:
        logger.error(f"Utils: Ошибка ZoneInfo для {tz_key}: {e}")
        return ZoneInfo(settings.DEFAULT_TZ_KEY)

def get_user_lang(user_data: Any) -> str:
    """Определяет язык пользователя."""
    user_data = _ensure_dict(user_data)
    return user_data.get("language", settings.DEFAULT_LANG)

def format_phrase(phrase_raw: str, user_name: str | None) -> str:
    """Форматирует фразу, подставляя имя или убирая плейсхолдер."""
    if not user_name:
        return phrase_raw.replace("{name}", "").strip().replace("  ", " ")
    try:
        return phrase_raw.format(name=user_name)
    except Exception as e:
        logger.error(f"Utils: Ошибка форматирования фразы: {e}")
        return phrase_raw

# --- 🧠 ЛОГИКА ДЕМО (5+1+5) ---

def get_demo_config(user_id: int) -> dict:
    """Возвращает настройки демо-периода на основе ID пользователя."""
    if user_id == settings.ADMIN_CHAT_ID:
        return {"demo": 365, "cooldown": 0}
    if user_id in settings.TESTER_USER_IDS:
        return {"demo": settings.TESTER_DEMO_DAYS, "cooldown": settings.TESTER_COOLDOWN_DAYS}
    return {"demo": settings.REGULAR_DEMO_DAYS, "cooldown": settings.REGULAR_COOLDOWN_DAYS}

async def is_demo_expired(user_data: Any) -> bool:
    """
    ✅ АСИНХРОННАЯ ВЕРСИЯ (2026-01-23)
    Возвращает True, если демо ИСТЕКЛО (или в кулдауне).
    """
    user_data = _ensure_dict(user_data)
    if user_data.get("is_paid"):
        return False
    
    user_id = user_data.get("user_id")
    expiry_str = user_data.get("demo_expiration")
    
    if not expiry_str:
        return False 

    try:
        now = datetime.now(timezone.utc)
        expiry_date = datetime.fromisoformat(expiry_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
        demo_count = int(user_data.get("demo_count", 1))
        config = get_demo_config(user_id)

        if now <= expiry_date:
            return False 

        if demo_count == 1:
            cooldown_end = expiry_date + timedelta(days=config["cooldown"])
            return now <= cooldown_end 

        return True 
    except Exception as e:
        logger.error(f"Utils: Ошибка в is_demo_expired для {user_id}: {e}")
        return True

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    """Безопасная отправка сообщения с обработкой блокировки бота."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as e:
        if "bot was blocked" in str(e).lower():
            logger.warning(f"User {chat_id} blocked the bot. Marking as inactive.")
            await db.update_user(chat_id, active=0)
        else:
            logger.error(f"safe_send error for {chat_id}: {e}")
        return False

# --- 🛡️ MIDDLEWARE ---

class AccessMiddleware(BaseMiddleware):
    """
    Middleware для проверки прав доступа, банов и демо-статуса.
    """
    
    async def __call__(self, handler, event, data):
        from bot.keyboards import get_reply_keyboard_for_user
        
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)
        
        chat_id = user.id

        # 1️⃣ Получаем пользователя
        user_data = await db.get_user(chat_id)
        if not user_data:
            return await handler(event, data)

        # 2️⃣ ПРОВЕРКА SMART BAN
        active_val = user_data.get("active", True)
        if active_val not in [True, 1, "1", None]:
            try:
                unban_at = datetime.fromisoformat(str(active_val).replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if now < unban_at:
                    remaining = unban_at - now
                    h, m = int(remaining.total_seconds() // 3600), int((remaining.total_seconds() % 3600) // 60)
                    lang = get_user_lang(user_data)
                    ban_msg = t("ban_timeout_msg", lang, h=h, m=m)
                    
                    if isinstance(event, Message):
                        await safe_send(data["bot"], chat_id, ban_msg)
                    elif isinstance(event, CallbackQuery):
                        await event.answer(ban_msg, show_alert=True)
                    return 
                else:
                    await db.update_user(chat_id, active=True)
                    user_data["active"] = True
            except Exception as e:
                logger.error(f"Middleware: Smart Ban error: {e}")

        # 3️⃣ ПОДГОТОВКА ДАННЫХ
        user_data = _ensure_dict(user_data)
        lang = get_user_lang(user_data)
        data.update({
            "user_data": user_data,
            "lang": lang,
            "is_admin": (chat_id == settings.ADMIN_CHAT_ID),
            "is_paid": user_data.get("is_paid", False)
        })

        if data["is_paid"] or data["is_admin"]:
            return await handler(event, data)

        # 4️⃣ ПРОВЕРКА: Нужно ли запустить второй демо (5+1+5)?
        now = datetime.now(timezone.utc)
        expiry_str = user_data.get("demo_expiration")
        expiry_date = datetime.fromisoformat(expiry_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) if expiry_str else now
        demo_count = int(user_data.get("demo_count", 1))
        config = get_demo_config(chat_id)

        if demo_count == 1 and now > (expiry_date + timedelta(days=config["cooldown"])):
            new_expiry = now + timedelta(days=config["demo"])
            await db.update_user(
                chat_id, 
                demo_count=2, 
                demo_expiration=new_expiry.isoformat(),
                challenge_streak=0, 
                sent_expiry_warning=0
            )
            await safe_send(data["bot"], chat_id, t("demo_restarted_info", lang, name=user_data.get("name", "")))
            user_data = await db.get_user(chat_id)
            data["user_data"] = _ensure_dict(user_data)

        # 5️⃣ ПРОВЕРКА: Демо истек? (Используем await!)
        if await is_demo_expired(user_data):
            text = getattr(event, "text", "")
            allowed_btns = [
                t("btn_pay_premium", lang), t("btn_profile", lang), 
                t("btn_settings", lang), t("btn_back", lang)
            ]
            
            # Разрешаем команды и базовые кнопки
            if isinstance(event, CallbackQuery) or (text and (text.startswith("/") or text in allowed_btns)):
                return await handler(event, data)

            # Сообщение об окончании
            if demo_count == 1 and now <= (expiry_date + timedelta(days=config["cooldown"])):
                remaining = (expiry_date + timedelta(days=config["cooldown"])) - now
                hours_left = max(1, int(remaining.total_seconds() // 3600))
                msg = t("demo_cooldown_msg", lang, name=user_data.get("name", ""), hours=hours_left)
            else:
                msg = t("demo_expired_final", lang, name=user_data.get("name", ""))

            if isinstance(event, Message):
                await safe_send(data["bot"], chat_id, msg, reply_markup=get_reply_keyboard_for_user(chat_id, lang, user_data))
            return

        return await handler(event, data)