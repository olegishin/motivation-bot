# 5 - bot/scheduler.py
# Планировщик фоновых задач APScheduler

import asyncio
import shutil
import os
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Any

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ✅ ИСПРАВЛЕНО: Безопасные импорты через bot.xxx
# Это гарантирует, что Python найдет файлы при запуске из корня
from bot.config import logger, settings, SPECIAL_USER_IDS
from bot.localization import t, DEFAULT_LANG
from bot.database import db 
from bot.keyboards import get_broadcast_keyboard 
from bot.utils import get_user_tz, get_user_lang, is_demo_expired, safe_send

DB_FILE = settings.DB_FILE 
ADMIN_CHAT_ID = settings.ADMIN_CHAT_ID
DATA_DIR = settings.DATA_DIR

scheduler = AsyncIOScheduler(timezone="UTC")


def safe_choice(items: List[Any]) -> Any | None:
    if not items:
        return None
    return random.choice(items)


def _is_user_active_for_broadcast(chat_id: int, user_data: dict) -> bool:
    if not user_data.get("active"):
        return False
    if chat_id in SPECIAL_USER_IDS:
        return True
    if user_data.get("is_paid"):
        return True
    if not is_demo_expired(user_data):
        return True
    if user_data.get("status") == "awaiting_renewal":
        return False
    return False


async def centralized_broadcast_job(bot: Bot, users_db: dict, static_data: dict):
    now_utc = datetime.now(ZoneInfo("UTC"))
    # ✅ УТРО В 8:00
    schedules = [
        (8, "morning_phrases"),
        (12, "goals"),
        (15, "day_phrases"),
        (18, "evening_phrases"),
    ]
    tasks = []

    logger.debug(f"Running broadcast_job for {len(users_db)} users (from cache).")

    for hour, key in schedules:
        data = static_data.get(key, {})
        phrases_by_lang = data if isinstance(data, dict) else {DEFAULT_LANG: data if isinstance(data, list) else []}

        for chat_id_str, user_data in users_db.items():
            try:
                chat_id = int(chat_id_str)
            except ValueError:
                continue

            if not _is_user_active_for_broadcast(chat_id, user_data):
                continue

            try:
                user_tz = get_user_tz(user_data)
                user_lang = get_user_lang(user_data)

                # Проверяем час по ЛОКАЛЬНОМУ времени пользователя
                if now_utc.astimezone(user_tz).hour == hour:
                    lang_specific_phrases = phrases_by_lang.get(user_lang, phrases_by_lang.get(DEFAULT_LANG, []))
                    if not lang_specific_phrases:
                        continue

                    phrase = (safe_choice(lang_specific_phrases) or "").format(
                        name=user_data.get("name", "друг")
                    )
                    # ✅ ИСПРАВЛЕНО: Передаем текст цитаты
                    reaction_keyboard = get_broadcast_keyboard(user_lang, quote_text=phrase)
                    tasks.append(safe_send(bot, chat_id, phrase, reply_markup=reaction_keyboard))
                    
            except Exception as e:
                logger.error(f"Error in broadcast loop for {chat_id_str}: {e}")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Считаем только успешные отправки (где результат True)
        sent_count = sum(1 for res in results if res is True)
        if sent_count > 0:
            logger.info(f"Broadcast done. Sent {sent_count} messages.")


async def check_demo_expiry_job(bot: Bot, users_db: dict):
    logger.debug("Running check_demo_expiry_job...")
    now_utc = datetime.now(ZoneInfo("UTC"))

    for chat_id_str, user_data in users_db.items():
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            continue

        if chat_id in SPECIAL_USER_IDS:
            continue
        if user_data.get("is_paid") or not user_data.get("active") or user_data.get("sent_expiry_warning"):
            continue

        demo_exp_str = user_data.get("demo_expiration")
        if not demo_exp_str:
            continue

        try:
            exp_dt = datetime.fromisoformat(demo_exp_str).replace(tzinfo=ZoneInfo("UTC"))
            time_left = exp_dt - now_utc
            warning_hours = 24

            if timedelta(hours=0) < time_left <= timedelta(hours=warning_hours):
                logger.info(f"Demo expiring soon for user {chat_id}.")
                lang = get_user_lang(user_data)
                await safe_send(
                    bot,
                    chat_id,
                    t("demo_expiring_soon_h", lang=lang, name=user_data.get("name", "друг"), hours=warning_hours),
                )
                await db.update_user(chat_id, sent_expiry_warning=True)
                user_data["sent_expiry_warning"] = True
        except Exception as e:
            logger.error(f"Error in expiry check for {chat_id}: {e}")


async def backup_job(bot: Bot):
    logger.info("[Backup Service] Starting DB backup...")
    if not DB_FILE.exists():
        logger.warning("[Backup Service] DB file not found, skipping backup.")
        return

    BACKUP_DIR = DATA_DIR / "backups"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"fotinia_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_filename

    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        shutil.copy2(DB_FILE, backup_path)
        logger.info(f"[Backup Service] DB backup created: {backup_path}")

        try:
            await bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=FSInputFile(backup_path),
                caption=f"📦 <b>DB Backup</b>\n📅 {timestamp}",
                parse_mode="HTML",
            )
        except Exception as e_tg:
            logger.error(f"[Backup Service] ⚠️ Failed to send to Telegram: {e_tg}")

        # Оставляем только последние 10 бэкапов
        all_backups = sorted(BACKUP_DIR.glob("fotinia_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_backup in all_backups[10:]:
            old_backup.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"[Backup Service] Backup failed: {e}")


async def setup_jobs_and_cache(bot: Bot, users_db: dict, static_data: dict):
    logger.info("Configuring APScheduler...")

    scheduler.remove_all_jobs()
    scheduler.add_job(centralized_broadcast_job, trigger="cron", hour="*", minute=0, kwargs={"bot": bot, "users_db": users_db, "static_data": static_data})
    scheduler.add_job(check_demo_expiry_job, trigger="cron", hour="*", minute=2, kwargs={"bot": bot, "users_db": users_db})
    scheduler.add_job(backup_job, trigger="cron", hour="*/6", minute=5, kwargs={"bot": bot})

    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")