# bot/scheduler.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

from config import logger, settings
# Импорт t и Lang
from localization import t, Lang 
from database import db
# Все эти функции должны быть в utils.py
from utils import is_time_for_user, get_current_user_dt, is_premium_active, get_user_tz, is_demo_expired
# ✅ КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Импортируем модуль целиком, чтобы избежать ошибок циклического импорта
import content_handlers 

# --- Константы ---
scheduler = AsyncIOScheduler()
BROADCAST_INTERVAL_MINUTES = 60 * 6 # 6 часов
BROADCAST_JOB_ID = "daily_broadcast"
DEFAULT_LANG = settings.DEFAULT_LANG # Берем из настроек

# --- Кеш пользователей для планировщика ---
# Этот кэш будет содержать только user_id, is_paid, timezone и language
USERS_CACHE: Dict[int, Dict[str, Any]] = {} 
STATIC_CONTENT: Dict[str, Any] = {}


# =====================================================
# 1. СТАРТ и ОБНОВЛЕНИЕ ПЛАНИРОВЩИКА
# =====================================================

async def update_user_cache_and_jobs(bot: Bot):
    """Обновляет кэш пользователей из БД и обновляет расписание."""
    global USERS_CACHE, STATIC_CONTENT
    
    # 1. Обновляем кэш из БД (берем только нужные поля)
    all_users_data = await db.get_all_users()
    
    # Конвертируем ключи из str в int и фильтруем поля
    new_cache = {}
    for user_id_str, data in all_users_data.items():
        user_id = int(user_id_str)
        
        # Получаем данные, необходимые для шедулера
        new_cache[user_id] = {
            'language': data.get('language', DEFAULT_LANG),
            'timezone': data.get('timezone', settings.DEFAULT_TZ_KEY),
            'is_paid': data.get('is_paid', 0),
            'demo_expiration': data.get('demo_expiration'),
            'is_active': data.get('is_active', 1),
            'first_name': data.get('first_name', 'друг')
        }
        
    USERS_CACHE = new_cache
    logger.info(f"✅ Scheduler user cache updated: {len(USERS_CACHE)} users.")

    # 2. Перезапускаем основное задание рассылки
    if scheduler.running:
        try:
            scheduler.remove_job(BROADCAST_JOB_ID)
            logger.info(f"☑️ Removed old broadcast job: {BROADCAST_JOB_ID}")
        except JobLookupError:
            pass # Если задания не было, это нормально
            
    # Добавляем задание рассылки, которое будет запускаться каждые X минут
    scheduler.add_job(
        run_broadcast,
        IntervalTrigger(minutes=BROADCAST_INTERVAL_MINUTES),
        id=BROADCAST_JOB_ID,
        name="Main Broadcast Job",
        args=[bot]
    )
    logger.info(f"🚀 Main broadcast job added: every {BROADCAST_INTERVAL_MINUTES} minutes.")

async def setup_jobs_and_cache(bot: Bot, users_db_cache: Dict[str, Any], static_data: Dict[str, Any]):
    """Первоначальная настройка планировщика и кэша."""
    global STATIC_CONTENT
    
    # 1. Загружаем статический контент
    STATIC_CONTENT = static_data
    
    # 2. Обновляем кэш пользователей и настраиваем job
    await update_user_cache_and_jobs(bot)

    # 3. Запускаем планировщик, если он еще не запущен
    if not scheduler.running:
        scheduler.start()
        logger.info("▶️ APScheduler started.")


# =====================================================
# 2. ЗАДАНИЕ НА РАССЫЛКУ
# =====================================================

async def run_broadcast(bot: Bot):
    """
    Основное задание, которое запускается периодически и отправляет
    контент соответствующим пользователям.
    """
    logger.info("🔄 Running main broadcast job...")

    users_to_update_list = list(USERS_CACHE.keys())
    
    # Разделяем пользователей на чанки, чтобы избежать таймаутов
    chunk_size = 50 
    for i in range(0, len(users_to_update_list), chunk_size):
        chunk = users_to_update_list[i:i + chunk_size]
        
        tasks = [
            send_content_to_single_user(bot, user_id)
            for user_id in chunk
        ]
        
        await asyncio.gather(*tasks)
        await asyncio.sleep(2) # Задержка между чанками для соблюдения лимитов Telegram

    logger.info("✅ Main broadcast job finished.")


async def send_content_to_single_user(bot: Bot, user_id: int):
    """Отправляет один тип контента, если время подходит."""
    user_data = USERS_CACHE.get(user_id)

    if not user_data or not user_data.get('is_active'):
        # Пропускаем неактивных или несуществующих пользователей
        return

    # 1. Проверка демо-статуса
    # is_premium_active берется из utils
    is_active_premium = is_premium_active(user_data)
    if not is_active_premium and is_demo_expired(user_data):
        # Если демо истекло, но пользователь не Premium, рассылку не отправляем
        return 

    # 2. Проверка времени
    timezone_key = user_data.get('timezone', settings.DEFAULT_TZ_KEY)
    user_tz = get_user_tz(user_data)
    current_dt = get_current_user_dt(user_tz)
    
    # Получаем категорию, для которой пришло время (morning, ritm, evening)
    category = is_time_for_user(user_id, current_dt, user_tz)

    if category:
        try:
            # Получаем контент (теперь вызываем через модуль content_handlers)
            content, category_title = content_handlers.get_random_content_for_user(
                user_id,
                user_data.get('language', DEFAULT_LANG),
                category,
                STATIC_CONTENT
            )
            
            if content:
                # Отправляем сообщение
                await bot.send_message(
                    chat_id=user_id,
                    text=f"<b>{category_title}</b>\n\n{content}",
                    parse_mode="HTML" # Добавлено для безопасности
                    # reply_markup=get_inline_feedback_keyboard(category) 
                )
                
                # Обновляем статистику активности (опционально, можно вынести в миддлварь)
                await db.update_user(user_id, last_active=datetime.now().isoformat())
                logger.info(f"🚀 Sent '{category}' to user {user_id} ({current_dt.strftime('%H:%M')} in {timezone_key})")

        except Exception as e:
            logger.error(f"❌ Error sending {category} to user {user_id}: {e}")