# 07 - bot/scheduler.py
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ЧИСТАЯ ВЕРСИЯ)
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ БЕЗОПАСНАЯ ВЕРСИЯ)
# Планировщик фоновых задач APScheduler (МАРКЕТИНГОВАЯ ВЕРСИЯ)
# Планировщик фоновых задач (Маркетинг + Фикс имен)
# Планировщик: Окно отправки 2 мин, фолбек имени "друг", приоритет админов.
# Планировщик фоновых задач: исправлены дубли и логика маркетинга
# Планировщик фоновых задач: реализация логики 5+1+5 (и спец-интервалов)
# bot/scheduler.py — Финальная версия с фиксом импорта
# Планировщик фоновых задач (Финальная версия с защитой "тихого часа" и маркетингом)
# Планировщик фоновых задач (Версия: Фикс имен + Защита "тихого часа")
# Планировщик фоновых задач (Полная версия с исправлением дублей)

# 07 - bot/scheduler.py
import asyncio
import shutil
import random
from datetime import datetime, timezone, timedelta
from typing import List, Any

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import logger, settings
from bot.localization import t, DEFAULT_LANG
from bot.database import db 
from bot.utils import get_user_tz, get_user_lang, check_demo_status, safe_send

scheduler = AsyncIOScheduler(timezone="UTC")

def safe_choice(items: List[Any]) -> Any | None:
    if not items: return None
    return random.choice(items)

# ✅ ВОЗВРАЩЕНО: Функция теста, которую ищет bot/commands.py
async def test_broadcast_job(bot: Bot, static_data: dict, chat_id: int):
    """Мгновенный тест рассылки."""
    from bot.keyboards import get_broadcast_keyboard
    data = static_data.get("morning_phrases", {})
    phrases = data.get("ru", [])
    if phrases:
        phrase = random.choice(phrases).format(name="Тестер")
        kb = get_broadcast_keyboard("ru", quote_text=phrase)
        await safe_send(bot, chat_id, f"🧪 <b>Тест:</b>\n\n{phrase}", reply_markup=kb)

# --- ОСНОВНЫЕ ЗАДАЧИ ---

async def centralized_broadcast_job(bot: Bot, static_data: dict):
    """
    Основная задача рассылки контента по расписанию.
    """
    from bot.keyboards import get_broadcast_keyboard, get_payment_keyboard

    users_db = await db.get_all_users()
    now_utc = datetime.now(timezone.utc)
    
    schedules = [
        (8, "morning_phrases", "reminder_8"),
        (12, "goals", "reminder_12"),
        (15, "day_phrases", "reminder_15"),
        (18, "evening_phrases", "reminder_18"),
    ]
    tasks = []

    for hour, content_key, reminder_key in schedules:
        data = static_data.get(content_key, {})
        phrases_by_lang = data if isinstance(data, dict) else {DEFAULT_LANG: data if isinstance(data, list) else []}

        for chat_id_str, user_data in users_db.items():
            try:
                chat_id = int(chat_id_str)
                if not user_data.get("active"): continue

                user_tz = get_user_tz(user_data)
                user_lang = get_user_lang(user_data)
                user_dt_local = now_utc.astimezone(user_tz)
                
                # Проверка времени (строго в 00 минут часа)
                if user_dt_local.hour == hour and user_dt_local.minute == 0:
                    
                    is_paid = user_data.get("is_paid", False)
                    is_admin = (chat_id == settings.ADMIN_CHAT_ID)
                    user_name = user_data.get("name") or ""

                    # 1. ПРИОРИТЕТ: АДМИН ИЛИ ОПЛАЧЕНО -> Контент всегда
                    if is_admin or is_paid:
                        lang_specific_phrases = phrases_by_lang.get(user_lang, phrases_by_lang.get(DEFAULT_LANG, []))
                        phrase_raw = safe_choice(lang_specific_phrases)
                        if phrase_raw:
                            phrase = phrase_raw.format(name=user_name)
                            kb = get_broadcast_keyboard(user_lang, quote_text=phrase, category=content_key)
                            tasks.append(safe_send(bot, chat_id, phrase, reply_markup=kb))
                        continue

                    # 2. ПРОВЕРКА ЧЕРЕЗ UTILS (ДОСТУП ЗАКРЫТ)
                    if check_demo_status(user_data):
                        demo_count = user_data.get("demo_count", 1)
                        if demo_count >= 2:
                            reminder_text = t(reminder_key, user_lang, name=user_name)
                            kb = get_payment_keyboard(user_lang)
                            tasks.append(safe_send(bot, chat_id, reminder_text, reply_markup=kb))
                        continue

                    # 3. ДОСТУП ОТКРЫТ (ДЕМО)
                    lang_specific_phrases = phrases_by_lang.get(user_lang, phrases_by_lang.get(DEFAULT_LANG, []))
                    if not lang_specific_phrases: continue

                    phrase_raw = safe_choice(lang_specific_phrases)
                    if not phrase_raw: continue
                    
                    phrase = phrase_raw.format(name=user_name)
                    kb = get_broadcast_keyboard(user_lang, quote_text=phrase, category=content_key)
                    tasks.append(safe_send(bot, chat_id, phrase, reply_markup=kb))

            except Exception as e:
                logger.error(f"Error in broadcast loop for {chat_id_str}: {e}")

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def check_demo_expiry_job(bot: Bot):
    """Предупреждение за 24 часа до конца демо."""
    users_db = await db.get_all_users()
    now_utc = datetime.now(timezone.utc)
    for chat_id_str, user_data in users_db.items():
        try:
            chat_id = int(chat_id_str)
            if user_data.get("is_paid") or not user_data.get("active") or user_data.get("sent_expiry_warning"): continue
            
            demo_exp_str = user_data.get("demo_expiration")
            if not demo_exp_str: continue
            
            exp_dt = datetime.fromisoformat(demo_exp_str.replace('Z', '+00:00'))
            if timedelta(hours=0) < (exp_dt - now_utc) <= timedelta(hours=24):
                lang = get_user_lang(user_data)
                user_name = user_data.get("name") or ""
                
                from bot.keyboards import get_payment_keyboard
                await safe_send(bot, chat_id, t("demo_expiring_soon_h", lang=lang, name=user_name, hours=24), reply_markup=get_payment_keyboard(lang))
                await db.update_user(chat_id, sent_expiry_warning=True)
        except: continue

async def backup_job(bot: Bot):
    """Создает бэкап и отправляет ОДИН файл админу."""
    if not settings.DB_FILE.exists(): return
    BACKUP_DIR = settings.DATA_DIR / "backups"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_path = BACKUP_DIR / f"fotinia_{timestamp}.db"
    try:
        BACKUP_DIR.mkdir(exist_ok=True, parents=True)
        shutil.copy2(settings.DB_FILE, backup_path)
        
        await bot.send_document(
            chat_id=settings.ADMIN_CHAT_ID, 
            document=FSInputFile(backup_path), 
            caption=f"📦 <b>Daily DB Backup</b>\n📅 {timestamp}"
        )
        logger.info(f"Backup sent: {backup_path.name}")
    except Exception as e: 
        logger.error(f"Backup failed: {e}")

# --- НАСТРОЙКА ПЛАНИРОВЩИКА ---

async def setup_jobs_and_cache(bot: Bot, users_db: dict, static_data: dict):
    """Настройка задач с защитой от дублей (replace_existing=True)."""
    
    # 1. Рассылка контента (каждую минуту)
    scheduler.add_job(
        centralized_broadcast_job, 
        trigger="interval", 
        minutes=1, 
        id="centralized_broadcast_job", 
        kwargs={"bot": bot, "static_data": static_data},
        replace_existing=True
    )
    
    # 2. Проверка истечения демо (раз в час)
    scheduler.add_job(
        check_demo_expiry_job, 
        trigger="cron", 
        hour="*", 
        minute=2, 
        id="check_demo_expiry_job", 
        kwargs={"bot": bot},
        replace_existing=True
    )
    
    # 3. Бэкап базы — СТРОГО 1 РАЗ В СУТКИ (03:05 UTC)
    scheduler.add_job(
        backup_job, 
        trigger="cron", 
        hour=3, 
        minute=5, 
        id="backup_job", 
        kwargs={"bot": bot},
        replace_existing=True,
        misfire_grace_time=600
    )
    
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")
    else:
        logger.info("APScheduler jobs updated.")