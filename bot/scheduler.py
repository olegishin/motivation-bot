# 07 - bot/scheduler.py
# ✅ APScheduler - планировщик задач
#✅ Центральная рассылка (03:00 UTC) с защитой от дублей
#✅ Маркетинговые дожимы (8, 12, 15, 18 часов по локальному времени)
#✅ Напоминания о челленджах (16:00 и +1 час)
#✅ Проверка истечения демо
#✅ Ежедневный бэкап базы данных (03:05 UTC)

# 07 - bot/scheduler.py - ФИНАЛЬНАЯ ВЕРСИЯ (30.01.2026)
# Планировщик задач (APScheduler)
# ✅ ПРОВЕРЕНО: Защита от дублей, маркетинг 3+1+3, бэкапы

import asyncio
import shutil
import random
import json
from datetime import datetime, timezone, timedelta
from typing import List, Any, Dict, Tuple
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import logger, settings
from bot.localization import t, DEFAULT_LANG
from bot.database import db
from bot.utils import get_user_tz, get_user_lang, is_demo_expired, safe_send
from bot.challenges import check_challenges_reminder

scheduler = AsyncIOScheduler(timezone="UTC")

# --- 🛡️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БЕЗОПАСНОСТИ ---

def safe_choice(items: List[Any]) -> Any | None:
    """Безопасный выбор случайного элемента из списка."""
    if not items:
        return None
    return random.choice(items)

def _safe_get_text(phrase_raw: Any) -> str | None:
    """Безопасное извлечение текста из фразы."""
    if not phrase_raw:
        return None
    try:
        if isinstance(phrase_raw, dict):
            text = phrase_raw.get("text")
            if isinstance(text, str) and text.strip():
                return text
            return None
        elif isinstance(phrase_raw, str) and phrase_raw.strip():
            return phrase_raw
        return None
    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        return None

def _safe_format_text(text: str, user_name: str) -> str:
    """Безопасное форматирование текста с именем."""
    if not user_name:
        return text.replace("{name}", "").strip()
    try:
        if "{name}" in text:
            return text.format(name=user_name)
        return text
    except Exception as e:
        logger.error(f"Error formatting text with name '{user_name}': {e}")
        return text.replace("{name}", "").strip()

def _safe_get_user_tz(user_data: Dict[str, Any]):
    """Безопасное получение часового пояса."""
    try:
        return get_user_tz(user_data)
    except Exception as e:
        logger.warning(f"Error getting user timezone, using default: {e}")
        return get_user_tz({})

# --- 📢 ГЛАВНАЯ РАССЫЛКА (КОНТЕНТ + МАРКЕТИНГ) ---

async def centralized_broadcast_job(bot: Bot, static_data: dict):
    """
    Ультимативная рассылка:
    1. 03:00 UTC - Утренний контент или Маркетинг 'Дня тишины'.
    2. 08, 12, 15, 18 Local - Дожим на оплату (если демо истекло).
    """
    from bot.keyboards import get_broadcast_keyboard
    
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.date().isoformat()
    MARKETING_HOURS = {8: "reminder_8", 12: "reminder_12", 15: "reminder_15", 18: "reminder_18"}
    
    try:
        users_db = await db.get_all_users()
    except Exception as e:
        logger.critical(f"Failed to load users: {e}")
        return

    sent_count = 0
    for chat_id_str, user_data in users_db.items():
        try:
            chat_id = int(chat_id_str)
            lang = get_user_lang(user_data)
            user_tz = _safe_get_user_tz(user_data)
            
            # Локальное время пользователя
            local_now = now_utc.astimezone(user_tz)
            local_hour = local_now.hour

            # 🛡️ ЗАЩИТА ОТ ДУБЛЕЙ (Проверка Часа)
            # Формат: "2026-01-30_08" - если уже слали в этот час, пропускаем
            last_ts = user_data.get("last_broadcast_date", "")
            if last_ts == f"{today_str}_{local_hour}":
                continue

            # 🛡️ SMART BAN (Если заблокировал или неактивен)
            if not user_data.get("active", True):
                continue

            is_expired = await is_demo_expired(user_data)
            is_paid = user_data.get("is_paid", False)

            # --- А) УТРЕННИЙ БЛОК (03:00 UTC) ---
            if now_utc.hour == 3:
                # Для активных - контент
                if not is_expired or is_paid:
                    data = static_data.get("morning_phrases", {})
                    phrases = data.get(lang, data.get(DEFAULT_LANG, []))
                    phrase_raw = safe_choice(phrases)
                    text = _safe_get_text(phrase_raw)
                    if text:
                        phrase = _safe_format_text(text, user_data.get("name") or "друг")
                        kb = get_broadcast_keyboard(lang, quote_text=phrase, category="morning_phrases", user_name=user_data.get("name") or "друг")
                        await safe_send(bot, chat_id, phrase, reply_markup=kb)
                
                # Для "Дня тишины" - маркетинговый призыв
                elif user_data.get("status") == "cooldown":
                    await safe_send(bot, chat_id, t('marketing_quiet_day', lang))

            # --- Б) МАРКЕТИНГОВЫЙ ДОЖИМ (8, 12, 15, 18 Local Time) ---
            elif local_hour in MARKETING_HOURS and is_expired and not is_paid:
                msg_key = MARKETING_HOURS[local_hour]
                # Шлем только если это не статус cooldown (в тишине не дожимаем лишний раз)
                if user_data.get("status") != "cooldown":
                    await safe_send(bot, chat_id, t(msg_key, lang, name=user_data.get("name") or "друг"))

            # Обновляем метку времени, чтобы не было дублей в рамках этого часа
            await db.update_user(chat_id, last_broadcast_date=f"{today_str}_{local_hour}")
            sent_count += 1
            await asyncio.sleep(0.05)  # Flood protection

        except Exception as e:
            logger.error(f"Error in broadcast loop for {chat_id_str}: {e}")

    if sent_count > 0:
        logger.info(f"📊 Broadcast: Sent {sent_count} messages.")

# --- 🎯 ЧЕЛЛЕНДЖИ (ЕЖЕЧАСНАЯ ПРОВЕРКА) ---

async def challenges_reminder_job(bot: Bot):
    """
    Вызывает логику из challenges.py.
    Сама определяет: 16:00 (принятие) или +1 час (выполнение).
    """
    users_db = await db.get_all_users()
    for chat_id_str, user_data in users_db.items():
        if not user_data.get("active", True):
            continue
        try:
            lang = get_user_lang(user_data)
            await check_challenges_reminder(bot, int(chat_id_str), user_data, lang)
        except Exception as e:
            logger.error(f"Error in challenge reminder: {e}")

# --- ⏰ СИСТЕМНЫЕ ЗАДАЧИ ---

async def check_demo_expiry_job(bot: Bot):
    """Предупреждение за 24 часа до конца демо."""
    users_db = await db.get_all_users()
    now_utc = datetime.now(timezone.utc)
    for chat_id_str, u in users_db.items():
        if u.get("is_paid") or u.get("sent_expiry_warning"):
            continue
        exp_str = u.get("demo_expiration")
        if exp_str:
            exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
            if timedelta(hours=0) < (exp_dt - now_utc) <= timedelta(hours=24):
                lang = get_user_lang(u)
                await safe_send(bot, int(chat_id_str), t("demo_expiry_warning", lang))
                await db.update_user(int(chat_id_str), sent_expiry_warning=True)

async def backup_job(bot: Bot):
    """Ежедневный бэкап базы в 03:05 UTC."""
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
            caption=f"📦 <b>Daily Backup</b>\n📅 {timestamp}"
        )
        # Очистка старых (30+ дней)
        limit = datetime.now(timezone.utc) - timedelta(days=30)
        for old in BACKUP_DIR.glob("fotinia_*.db"):
            if datetime.fromtimestamp(old.stat().st_mtime, tz=timezone.utc) < limit:
                old.unlink()
    except Exception as e:
        logger.error(f"Backup failed: {e}")

# --- 🔧 НАСТРОЙКА ПЛАНИРОВЩИКА ---

async def setup_jobs_and_cache(bot: Bot, users_db: dict, static_data: dict):
    """Инициализация APScheduler с новой логикой."""
    logger.info("⏰ Настройка планировщика (Ultimate Production)...")
    
    for job in scheduler.get_jobs():
        scheduler.remove_job(job.id)

    # 1. Центральная рассылка (Каждые 30 минут, чтобы точно ловить начало часа)
    # Защита внутри функции не даст отправить дважды.
    scheduler.add_job(
        centralized_broadcast_job,
        CronTrigger(minute="0,30"),
        args=[bot, static_data],
        id="main_broadcast_job"
    )

    # 2. Челленджи (Раз в 30 минут для 16:00 и напоминаний через час)
    scheduler.add_job(
        challenges_reminder_job,
        CronTrigger(minute="5,35"),
        args=[bot],
        id="challenge_reminder_job"
    )

    # 3. Демо-статус (Раз в 4 часа)
    scheduler.add_job(
        check_demo_expiry_job,
        CronTrigger(hour="0,4,8,12,16,20"),
        args=[bot],
        id="demo_status_job"
    )

    # 4. Бэкап (Раз в сутки в 03:05 UTC)
    scheduler.add_job(
        backup_job,
        CronTrigger(hour=3, minute=5),
        args=[bot],
        id="backup_system_job"
    )

    if not scheduler.running:
        scheduler.start()
        logger.info("✅ APScheduler запущен успешно.")
    else:
        logger.info("✅ APScheduler задачи обновлены.")