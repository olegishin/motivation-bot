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
            logger.error(f"Utils: Ошибка распаковки JSON: {e}. Data: {data[:100]}")
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
    if user_id == 290711961:
        return {"demo": 3, "cooldown": 1}
    if user_id in settings.TESTER_USER_IDS:
        return {"demo": settings.TESTER_DEMO_DAYS, "cooldown": settings.TESTER_COOLDOWN_DAYS}
    return {"demo": settings.REGULAR_DEMO_DAYS, "cooldown": settings.REGULAR_COOLDOWN_DAYS}

def check_demo_status(user_data: Any) -> bool:
    """
    Возвращает True, если демо ИСТЕКЛО (или в кулдауне).
    Возвращает False, если доступ разрешен.
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
        logger.error(f"Utils: Ошибка в check_demo_status для {user_id}: {e}")
        return True

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    """Безопасная отправка сообщения с обработкой блокировки бота."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as e:
        logger.error(f"safe_send error for {chat_id}: {e}")
        if "bot was blocked" in str(e).lower():
            await db.update_user(chat_id, active=0)
        return False

# --- 🛡️ MIDDLEWARE ---

class AccessMiddleware(BaseMiddleware):
    """
    ✅ ИСПРАВЛЕНО (2026-01-16): Убрана автоматическая регистрация (Ошибка #4)
    
    Теперь middleware ТОЛЬКО:
    1. Получает пользователя из БД (создание происходит в /start)
    2. Проверяет Smart Ban (тайм-ауты)
    3. Проверяет демо-статус
    4. Определяет язык и права доступа
    
    ЛОГИКА ЖИЗНЕННОГО ЦИКЛА ПОЛЬЗОВАТЕЛЯ:
    - Новый пользователь нажимает /start → создается в commands.py
    - Middleware находит его в БД → работает с проверками
    - Никогда больше автоматическое создание!
    """
    
    async def __call__(self, handler, event, data):
        from bot.keyboards import get_reply_keyboard_for_user
        
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)
        
        chat_id = user.id
        logger.debug(f"Middleware: Processing event from user {chat_id}")

        # 1️⃣ ПОЛУЧАЕМ пользователя из БД
        user_data = await db.get_user(chat_id)
        
        # 2️⃣ ✅ ИСПРАВЛЕНО: Если пользователя нет — НЕ создаем его!
        # Пользователь должен был быть создан в /start
        if not user_data:
            logger.warning(f"Middleware: User {chat_id} not found in DB (should have been created in /start)")
            # Просто пропускаем, пусть обработчик сам разбирается
            # Скорее всего это будет перенаправлено на /start
            return await handler(event, data)

        logger.debug(f"Middleware: User {chat_id} found in DB")

        # 3️⃣ ПРОВЕРКА SMART BAN (временный бан на 24 часа)
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
                    
                    logger.warning(f"Middleware: User {chat_id} is banned until {unban_at}")
                    
                    if isinstance(event, Message):
                        await safe_send(data["bot"], chat_id, ban_msg)
                    elif isinstance(event, CallbackQuery):
                        await event.answer(ban_msg, show_alert=True)
                    return 
                else:
                    # Таймаут истек, разбанить пользователя
                    logger.info(f"Middleware: Unbanning user {chat_id} (timeout expired)")
                    await db.update_user(chat_id, active=True)
                    user_data["active"] = True
            except Exception as e:
                logger.error(f"Middleware: Smart Ban parse error for {chat_id}: {e}")
                return

        # 4️⃣ ПОДГОТОВКА ДАННЫХ для обработчиков
        user_data = _ensure_dict(user_data)
        lang = get_user_lang(user_data)
        
        data.update({
            "user_data": user_data,
            "lang": lang,
            "is_admin": (chat_id == settings.ADMIN_CHAT_ID),
            "is_paid": user_data.get("is_paid", False)
        })

        logger.debug(f"Middleware: User {chat_id} lang={lang}, is_paid={data['is_paid']}, is_admin={data['is_admin']}")

        # 5️⃣ ПРЕМИУМ и АДМИН — полный доступ
        if data["is_paid"] or data["is_admin"]:
            logger.debug(f"Middleware: User {chat_id} has full access (paid or admin)")
            return await handler(event, data)

        # 6️⃣ ПРОВЕРКА ДЕМО-СТАТУСА (логика 5+1+5)
        now = datetime.now(timezone.utc)
        expiry_str = user_data.get("demo_expiration")
        expiry_date = datetime.fromisoformat(expiry_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) if expiry_str else now
        demo_count = int(user_data.get("demo_count", 1))
        config = get_demo_config(chat_id)

        logger.debug(f"Middleware: User {chat_id} demo_count={demo_count}, expiry={expiry_str}")

        # 7️⃣ ПРОВЕРКА: Нужно ли запустить второй демо (после 5+1 дней)?
        if demo_count == 1 and now > (expiry_date + timedelta(days=config["cooldown"])):
            logger.info(f"Middleware: Restarting demo for user {chat_id} (demo_count: 1 → 2)")
            
            new_expiry = now + timedelta(days=config["demo"])
            await db.update_user(
                chat_id, 
                demo_count=2, 
                demo_expiration=new_expiry.isoformat(),
                challenge_streak=0, 
                challenge_accepted=0, 
                challenges=[], 
                sent_expiry_warning=0, 
                challenges_today=0, 
                rules_shown_count=0
            )
            await safe_send(
                data["bot"], 
                chat_id, 
                t("demo_restarted_info", lang, name=user_data.get("name", ""))
            )
            user_data = await db.get_user(chat_id)
            data["user_data"] = _ensure_dict(user_data)
            data["lang"] = get_user_lang(user_data)

        # 8️⃣ ПРОВЕРКА: Демо истек?
        if check_demo_status(user_data):
            logger.info(f"Middleware: User {chat_id} demo has expired")
            
            text = getattr(event, "text", "")
            
            # Разрешаем только определенные кнопки (профиль, оплата, настройки, назад)
            allowed_btns = [
                t("btn_pay_premium", lang), 
                t("btn_profile", lang), 
                t("btn_settings", lang), 
                t("btn_back", lang),
                "⚙️ Settings", "👤 Profile", 
                "⚙️ Настройки", "👤 Профіль", "⚙️ Налаштування", "👤 Профіль", 
                "↩️ Назад", "↩️ Back"
            ]
            
            # Разрешаем команды (/start, /language, /timezone) и разрешенные кнопки
            if isinstance(event, CallbackQuery) or (text and (text.startswith("/") or text in allowed_btns)):
                logger.debug(f"Middleware: User {chat_id} allowed to use command/button despite expired demo")
                return await handler(event, data)

            # Иначе показываем сообщение о демо
            if demo_count == 1 and now <= (expiry_date + timedelta(days=config["cooldown"])):
                # В режиме "тишины" (cooldown)
                remaining = (expiry_date + timedelta(days=config["cooldown"])) - now
                hours_left = max(1, int(remaining.total_seconds() // 3600))
                msg = t("demo_cooldown_msg", lang, name=user_data.get("name", ""), hours=hours_left)
            else:
                # Демо полностью истек
                msg = t("demo_expired_final", lang, name=user_data.get("name", ""))

            logger.info(f"Middleware: Showing demo expired message to user {chat_id}")
            
            if isinstance(event, Message):
                await safe_send(
                    data["bot"], 
                    chat_id, 
                    msg, 
                    reply_markup=get_reply_keyboard_for_user(chat_id, lang, user_data)
                )
            return

        logger.debug(f"Middleware: User {chat_id} has active demo access")
        return await handler(event, data)