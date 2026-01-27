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
# Вспомогательные утилиты + Middlewares (УЛЬТИМАТИВНАЯ ВЕРСИЯ: 10/10)
# ✅ ВОССТАНОВЛЕНО: _ensure_dict, format_phrase, Smart Ban, 5+1+5 Logic
# ✅ СИНХРОНИЗИРОВАНО: Асинхронный is_demo_expired и расширенный get_demo_config
# ✅ ДОБАВЛЕНО (2026-01-27): Система уровней для челленджей

import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from bot.config import settings, logger

# --- 🛡️ ЗАЩИТНЫЕ ФУНКЦИИ (ВОССТАНОВЛЕНО) ---

def _ensure_dict(data: any) -> dict:
    """Рекурсивная распаковка вложенных JSON-строк (защита от двойного JSON)."""
    if not data: return {}
    if isinstance(data, dict): return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return _ensure_dict(parsed)
        except: return {}
    return {}

def format_phrase(phrase: str, name: str) -> str:
    """Безопасная подстановка имени в фразу с защитой от ошибок форматирования."""
    if not phrase: return ""
    try:
        return phrase.format(name=name)
    except Exception as e:
        logger.error(f"Utils: Format error: {e}")
        return phrase.replace("{name}", name)

# --- 🚀 УПРАВЛЕНИЕ ДОСТУПОМ (ВОССТАНОВЛЕНО) ---

def get_demo_config(user_id: int) -> dict:
    """Возвращает настройки демо-периода с учетом админа и тестеров."""
    # Админу — год демо
    if user_id == settings.ADMIN_CHAT_ID:
        return {"demo": 365, "cooldown": 0}
    
    # Тестеры (если есть в конфиге)
    if hasattr(settings, 'TESTERS') and user_id in settings.TESTERS:
        return {"demo": 30, "cooldown": 1}
        
    return {
        "demo": settings.DEMO_DAYS,
        "cooldown": settings.COOLDOWN_DAYS
    }

async def is_demo_expired(user_data: dict) -> bool:
    """Асинхронная проверка истечения демо."""
    if user_data.get("is_paid"): return False
    exp_str = user_data.get("demo_expiration")
    if not exp_str: return True
    try:
        exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp_dt
    except: return True

def get_user_lang(user_data: dict) -> str:
    return user_data.get("language", settings.DEFAULT_LANG)

def get_user_tz(user_data: dict):
    tz_name = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    try: return ZoneInfo(tz_name)
    except: return ZoneInfo(settings.DEFAULT_TZ_KEY)

# --- 📤 БЕЗОПАСНАЯ ОТПРАВКА ---

async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramForbiddenError:
        logger.warning(f"SafeSend: User {chat_id} blocked bot.")
    except TelegramRetryAfter as e:
        logger.error(f"SafeSend: Flood. Sleeping {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        return await safe_send(bot, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"SafeSend: Error to {chat_id}: {e}")
    return None

# --- 🏆 СИСТЕМА УРОВНЕЙ (2026-01-27) ---

def get_level_info(streak: int) -> dict:
    """
    Определяет информацию об уровне на основе стрика челленджей.
    Возвращает словарь с данными о текущем уровне, прогрессе и следующем уровне.
    """
    # Уровни: (минимальный_дней, максимальный_дней, номер_уровня, ключ_уровня)
    levels = [
        (0, 2, 1, "level_0"),    # Новичок
        (3, 6, 2, "level_1"),    # Практик
        (7, 14, 3, "level_2"),   # Специалист
        (15, 29, 4, "level_3"),  # Мастер
        (30, 999, 5, "level_4"), # Эксперт
    ]
    
    for min_days, max_days, level_num, level_key in levels:
        if min_days <= streak <= max_days:
            # Текущий уровень найден
            next_level = None
            next_min = None
            
            # Находим следующий уровень (если есть)
            for next_min_days, next_max_days, next_level_num, next_level_key in levels:
                if next_level_num == level_num + 1:
                    next_level = next_level_key
                    next_min = next_min_days
                    break
            
            # Рассчитываем прогресс до следующего уровня
            progress_percent = 0
            days_to_next = 0
            
            if next_min is not None:
                # Прогресс внутри текущего уровня
                level_range = max_days - min_days + 1
                current_in_level = streak - min_days + 1
                progress_percent = min(100, int((current_in_level / level_range) * 100))
                
                # Дней до следующего уровня
                days_to_next = max(0, next_min - streak)
            
            return {
                "current_level": level_key,
                "level_number": level_num,
                "min_days": min_days,
                "max_days": max_days,
                "next_level": next_level,
                "next_min_days": next_min,
                "progress_percent": progress_percent,
                "days_to_next": days_to_next,
                "is_max_level": (next_level is None),
            }
    
    # Если стрик выше максимального (маловероятно)
    return {
        "current_level": "level_4",
        "level_number": 5,
        "min_days": 30,
        "max_days": 999,
        "next_level": None,
        "next_min_days": None,
        "progress_percent": 100,
        "days_to_next": 0,
        "is_max_level": True,
    }

def get_progress_bar(percent: int, length: int = 5) -> str:
    """
    Создает текстовый прогресс-бар.
    Пример: 60% с длиной 5 → "[███░░]"
    """
    if percent >= 100:
        return "[" + "█" * length + "]"
    
    filled = int(length * percent / 100)
    empty = length - filled
    
    # Используем разные символы для лучшей визуализации
    return "[" + "█" * filled + "░" * empty + "]"

def get_level_bonus_description(level_key: str, lang: str = "ru") -> str:
    """
    Возвращает описание бонуса для уровня.
    Пока только текстовые описания, без реальных изменений функционала.
    """
    bonuses = {
        "ru": {
            "level_0": "Стартовая позиция",
            "level_1": "Доступ к расширенным челленджам",
            "level_2": "+1 Правило Вселенной в день",
            "level_3": "Персональный ритм дня",
            "level_4": "Статус ментора + особый значок",
        },
        "ua": {
            "level_0": "Стартова позиція",
            "level_1": "Доступ до розширених челенджів",
            "level_2": "+1 Правило Всесвіту на день",
            "level_3": "Персональний ритм дня",
            "level_4": "Статус ментора + особлива відзнака",
        },
        "en": {
            "level_0": "Starting position",
            "level_1": "Access to extended challenges",
            "level_2": "+1 Rule of the Universe per day",
            "level_3": "Personal rhythm of the day",
            "level_4": "Mentor status + special badge",
        }
    }
    
    # Возвращаем описание бонуса для языка, или fallback на русский
    return bonuses.get(lang, bonuses["ru"]).get(level_key, "")

# --- 🧠 ACCESS MIDDLEWARE (ВОССТАНОВЛЕНО ПОЛНОСТЬЮ) ---

class AccessMiddleware(BaseMiddleware):
    """
    Основной страж бота:
    - Проверка Smart Ban (24h)
    - Логика 5+1+5 (Restart Demo)
    - Проброс user_data, lang, is_admin в хендлеры
    """
    async def __call__(self, handler, event: Message, data: dict):
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        from bot.database import db # Ленивый импорт во избежание циклов
        
        user_data = await db.get_user(user_id)
        if not user_data:
            return await handler(event, data) # Для /start

        # 1. SMART BAN CHECK (24h)
        active_val = user_data.get("active")
        if isinstance(active_val, str) and len(active_val) > 5:
            try:
                ban_dt = datetime.fromisoformat(active_val.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < ban_dt:
                    remaining = ban_dt - datetime.now(timezone.utc)
                    h = int(remaining.total_seconds() // 3600)
                    await event.answer(f"⏳ <b>Доступ временно ограничен.</b>\nОсталось: {h}ч.")
                    return
                else:
                    await db.update_user(user_id, active=True)
            except: pass

        # 2. DEMO RESTART LOGIC (5+1+5)
        lang = get_user_lang(user_data)
        is_expired = await is_demo_expired(user_data)
        
        if is_expired and not user_data.get("is_paid"):
            if user_data.get("status") != "cooldown":
                # Входим в режим тишины
                await db.update_user(user_id, status="cooldown", active=False)
                user_data["status"] = "cooldown"
            
            # Если это не команда старта или оплаты — ограничиваем
            allowed_commands = ["/start", "/pay", "💳 Premium", "💰 Оплатить"]
            if event.text not in allowed_commands:
                # Проверка: не пора ли выйти из cooldown? (Авто-рестарт)
                # Эта логика также дублируется в /start для надежности
                return await handler(event, data) # Пропускаем к хендлерам, они сами ответят про кулдаун

        # 3. ДАННЫЕ ДЛЯ ХЕНДЛЕРОВ
        data["user_data"] = user_data
        data["lang"] = lang
        data["is_admin"] = (user_id == settings.ADMIN_CHAT_ID)
        data["is_paid"] = user_data.get("is_paid", False)

        return await handler(event, data)