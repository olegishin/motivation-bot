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
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ПРОДАКШН ВЕРСИЯ)
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ВЕРСИЯ - FORCE FIX)
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ВЕРСИЯ с асинхронной базой и безопасными фолбеками)
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ВЕРСИЯ: Фикс тестов и мультиязычности)
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ВЕРСИЯ: Фикс Smart Ban в рассылках)
# Планировщик фоновых задач APScheduler (ФИНАЛЬНАЯ ПРОДАКШН ВЕРСИЯ)
# (MERGED: Anti-freeze loop + Smart Ban + Backups)
# ФИНАЛЬНАЯ ПРОДАКШЕН-ВЕРСИЯ (10/10)
# Каждый час проверяем локальное время ВСЕХ пользователей
# MERGED: Smart Ban + Anti-freeze + Backups + Демо 5+1+5 + Пакетная отправка + Логирование метрик
# Планировщик фоновых задач APScheduler
# ✅ ИСПРАВЛЕНО (2026-01-16):
#    - Безопасная обработка типов (Ошибка #7)
#    - Try-catch вокруг каждого пользователя
#    - Валидация TZ с фолбеком
#    - Подробное логирование ошибок
#    - Метрики успешности рассылок
# Планировщик фоновых задач APScheduler
# ✅ ИСПРАВЛЕНО (2026-01-16):
#    - Безопасная обработка типов (Ошибка #7)
#    - Try-catch вокруг каждого пользователя
#    - Валидация TZ с фолбеком
#    - Подробное логирование ошибок
#    - Метрики успешности рассылок
# ✅ ИСПРАВЛЕНО (2026-01-23):
#    - Напоминание в 16:00 о невыполненном челлендже
#    - Напоминание через 1 час после принятия челленджа
#    - Бэкап 1 раз в сутки в 3:05 UTC
# 07 - bot/scheduler.py
# Планировщик фоновых задач APScheduler
# ✅ ИСПРАВЛЕНО (2026-01-16):
#    - Безопасная обработка типов (Ошибка #7)
#    - Try-catch вокруг каждого пользователя
#    - Валидация TZ с фолбеком
#    - Подробное логирование ошибок
#    - Метрики успешности рассылок
# ✅ ИСПРАВЛЕНО (2026-01-26):
#    - Напоминание в 16:00 о невыполненном челлендже (через localization.py)
#    - Напоминание через 1 час после принятия челленджа (через localization.py)
#    - Бэкап 1 раз в сутки в 3:05 UTC
#    - Асинхронная проверка демо (is_demo_expired)

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

from bot.config import logger, settings
from bot.localization import t, DEFAULT_LANG
from bot.database import db
from bot.utils import get_user_tz, get_user_lang, is_demo_expired, safe_send

scheduler = AsyncIOScheduler(timezone="UTC")

# --- 🛡️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def safe_choice(items: List[Any]) -> Any | None:
    """Безопасный выбор случайного элемента из списка."""
    if not items:
        return None
    return random.choice(items)

def _safe_get_text(phrase_raw: Any) -> str | None:
    """
    ✅ ИСПРАВЛЕНО (Ошибка #7): Безопасное извлечение текста из фразы.
    """
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
        else:
            logger.debug(f"Unexpected phrase type: {type(phrase_raw)}")
            return None
    except Exception as e:
        logger.error(f"Error extracting text from phrase: {e}")
        return None

def _safe_format_text(text: str, user_name: str) -> str:
    """
    ✅ ИСПРАВЛЕНО (Ошибка #7): Безопасное форматирование текста с именем.
    """
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
    """
    ✅ ИСПРАВЛЕНО (Ошибка #7): Безопасное получение часового пояса.
    """
    try:
        return get_user_tz(user_data)
    except Exception as e:
        logger.warning(f"Error getting user timezone, using default: {e}")
        return get_user_tz({})

# --- 🧪 ТЕСТОВАЯ РАССЫЛКА ---

async def test_broadcast_job(bot: Bot, static_data: dict, chat_id: int, lang: str = "ru"):
    from bot.keyboards import get_broadcast_keyboard
    
    logger.info(f"Test broadcast: Starting for user {chat_id}, lang={lang}")
    
    try:
        data = static_data.get("morning_phrases", {})
        if isinstance(data, dict):
            phrases = data.get(lang, data.get(DEFAULT_LANG, []))
        else:
            phrases = []
        
        if not phrases:
            logger.warning(f"Test broadcast: No phrases found for language {lang}")
            await safe_send(bot, chat_id, f"❌ Ошибка теста: Фразы для {lang} не найдены.")
            return
        
        phrase_raw = safe_choice(phrases)
        text = _safe_get_text(phrase_raw)
        
        if not text:
            logger.warning(f"Test broadcast: Could not extract text from phrase")
            await safe_send(bot, chat_id, "❌ Ошибка теста: Не удалось извлечь текст фразы.")
            return
        
        phrase = _safe_format_text(text, "Тестер")
        kb = get_broadcast_keyboard(lang, quote_text=phrase, category="morning_phrases", user_name="Тестер")
        await safe_send(bot, chat_id, f"🧪 <b>Тест ({lang.upper()}):</b>\n\n{phrase}", reply_markup=kb)
        logger.info(f"Test broadcast: Sent successfully to {chat_id}")
        
    except Exception as e:
        logger.error(f"Test broadcast error for user {chat_id}: {e}", exc_info=True)

# --- 📢 ГЛАВНАЯ РАССЫЛКА ---

async def centralized_broadcast_job(bot: Bot, static_data: dict):
    from bot.keyboards import get_broadcast_keyboard, get_payment_keyboard
    
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("📢 Starting centralized broadcast job")
    logger.info("=" * 60)
    
    try:
        users_db = await db.get_all_users()
    except Exception as e:
        logger.critical(f"Failed to load users from DB: {e}")
        return
    
    now_utc = start_time
    SCHEDULE_MAP = {
        8:  ("morning_phrases", "reminder_8"),
        12: ("goals",           "reminder_12"),
        15: ("day_phrases",     "reminder_15"),
        18: ("evening_phrases", "reminder_18"),
    }
    
    tasks = []
    eligible_count = processed_count = sent_count = error_count = skipped_count = 0
    
    logger.debug(f"Processing {len(users_db)} users")
    
    for chat_id_str, user_data in users_db.items():
        processed_count += 1
        if processed_count % 200 == 0:
            await asyncio.sleep(0.2)
        elif processed_count % 50 == 0:
            await asyncio.sleep(0.05)
        
        try:
            chat_id = int(chat_id_str)
            active_val = user_data.get("active", True)
            if active_val in [False, 0, "0"]:
                skipped_count += 1
                continue
            
            if isinstance(active_val, str) and active_val not in ["1", "true", "True"]:
                try:
                    unban_at = datetime.fromisoformat(active_val.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                    if now_utc < unban_at:
                        skipped_count += 1
                        continue
                    else:
                        await db.update_user(chat_id, active=True)
                        user_data["active"] = True
                except Exception:
                    skipped_count += 1
                    continue
            
            user_tz = _safe_get_user_tz(user_data)
            try:
                local_now = now_utc.astimezone(user_tz)
                local_hour = local_now.hour
                local_minute = local_now.minute
            except Exception:
                skipped_count += 1
                continue
            
            if local_hour not in SCHEDULE_MAP or local_minute >= 5:
                continue
            
            eligible_count += 1
            content_key, reminder_key = SCHEDULE_MAP[local_hour]
            is_paid = user_data.get("is_paid", False)
            is_admin = (chat_id == settings.ADMIN_CHAT_ID)
            user_name = user_data.get("name") or "друг"
            user_lang = get_user_lang(user_data)
            
            # --- ПРОВЕРКА КОНТЕНТА (Премиум / Демо) ---
            demo_expired = await is_demo_expired(user_data)

            if is_admin or is_paid or not demo_expired:
                try:
                    data = static_data.get(content_key, {})
                    phrases = data.get(user_lang, data.get(DEFAULT_LANG, [])) if isinstance(data, dict) else []
                    
                    if not phrases:
                        skipped_count += 1
                        continue
                    
                    phrase_raw = safe_choice(phrases)
                    text = _safe_get_text(phrase_raw)
                    if not text:
                        skipped_count += 1
                        continue
                    
                    phrase = _safe_format_text(text, user_name)
                    kb = get_broadcast_keyboard(user_lang, quote_text=phrase, category=content_key, user_name=user_name)
                    tasks.append(safe_send(bot, chat_id, phrase, reply_markup=kb))
                    sent_count += 1
                except Exception:
                    error_count += 1
                continue

            # --- МАРКЕТИНГ (5+1+5) ---
            if demo_expired:
                try:
                    demo_count = int(user_data.get("demo_count", 1))
                    if demo_count >= 2:
                        reminder_text = t(reminder_key, user_lang, name=user_name)
                        kb = get_payment_keyboard(user_lang)
                        tasks.append(safe_send(bot, chat_id, reminder_text, reply_markup=kb))
                        sent_count += 1
                    else:
                        skipped_count += 1
                except Exception:
                    error_count += 1
                continue
            
        except Exception as e:
            logger.error(f"Scheduler error for {chat_id_str}: {e}")
            error_count += 1
    
    if tasks:
        for i in range(0, len(tasks), 30):
            batch = tasks[i:i+30]
            results = await asyncio.gather(*batch, return_exceptions=True)
            batch_errors = sum(1 for r in results if isinstance(r, Exception))
            if i + 30 < len(tasks):
                await asyncio.sleep(1)
    
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info(f"📊 BROADCAST: Sent {sent_count}/{eligible_count} in {duration:.2f} sec. Errors: {error_count}")
    logger.info("=" * 60)

# --- ⏰ ВСПОМОГАТЕЛЬНЫЕ ЗАДАЧИ ---

async def check_demo_expiry_job(bot: Bot):
    logger.debug("Check demo expiry: Starting")
    try:
        users_db = await db.get_all_users()
    except Exception: return
    
    now_utc = datetime.now(timezone.utc)
    tasks = []
    for chat_id_str, user_data in users_db.items():
        try:
            if user_data.get("is_paid") or not user_data.get("active") or user_data.get("sent_expiry_warning"):
                continue
            demo_exp_str = user_data.get("demo_expiration")
            if not demo_exp_str: continue
            
            exp_dt = datetime.fromisoformat(demo_exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
            if timedelta(hours=0) < (exp_dt - now_utc) <= timedelta(hours=24):
                lang = get_user_lang(user_data)
                from bot.keyboards import get_payment_keyboard
                tasks.append(safe_send(bot, int(chat_id_str), t("demo_expiring_soon_h", lang=lang, name=user_data.get("name", "друг"), hours=24), reply_markup=get_payment_keyboard(lang)))
                await db.update_user(int(chat_id_str), sent_expiry_warning=True)
        except Exception: continue
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)

async def backup_job(bot: Bot):
    logger.info("💾 Backup: Starting daily backup at 03:05 UTC...")
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
            caption=f"📦 <b>Daily Backup</b>\n📅 {timestamp}\n📊 Size: {backup_path.stat().st_size // 1024} KB"
        )
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        for old in BACKUP_DIR.glob("fotinia_*.db"):
            if datetime.fromtimestamp(old.stat().st_mtime, tz=timezone.utc) < thirty_days_ago:
                old.unlink()
    except Exception as e:
        logger.error(f"❌ Backup failed: {e}", exc_info=True)
        try: await bot.send_message(settings.ADMIN_CHAT_ID, f"❌ <b>Backup failed:</b>\n{str(e)[:200]}")
        except: pass

# --- 🎯 ЧЕЛЛЕНДЖИ (NEW LOGIC) ---

async def check_pending_challenges_job(bot: Bot):
    """Напоминание в 16:00 о невыполненном челлендже."""
    logger.info("🎯 Check pending challenges (16:00 local)...")
    try:
        users_db = await db.get_all_users()
    except Exception: return
    
    now_utc = datetime.now(timezone.utc)
    tasks = []
    for chat_id_str, user_data in users_db.items():
        try:
            chat_id = int(chat_id_str)
            if not user_data.get("active", True): continue
            if not user_data.get("is_paid", False) and await is_demo_expired(user_data): continue
            
            user_tz = _safe_get_user_tz(user_data)
            local_now = now_utc.astimezone(user_tz)
            if local_now.hour != 16 or local_now.minute >= 5: continue
            
            if user_data.get("last_challenge_date") == local_now.date().isoformat() and user_data.get("challenge_accepted"):
                challenges = user_data.get("challenges", [])
                if isinstance(challenges, str): challenges = json.loads(challenges)
                
                for ch in challenges:
                    if isinstance(ch, dict):
                        acc = ch.get("accepted", "")
                        if acc.startswith(local_now.date().isoformat()) and not ch.get("completed"):
                            lang = get_user_lang(user_data)
                            preview = ch.get("text", "")
                            preview = preview[:100] + "..." if len(preview) > 100 else preview
                            
                            # ✅ ИСПОЛЬЗУЕМ ЛОКАЛИЗАЦИЮ
                            reminder_text = t("challenge_pending_reminder_16", lang=lang, name=user_data.get("name", "друг"), challenge=preview)
                            tasks.append(safe_send(bot, chat_id, reminder_text, parse_mode="HTML"))
                            break
        except Exception: continue
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)

async def check_recently_accepted_challenges_job(bot: Bot):
    """Напоминание через 1 час после принятия."""
    logger.debug("⏱️ Check recently accepted challenges...")
    try:
        users_db = await db.get_all_users()
    except Exception: return
    
    now_utc = datetime.now(timezone.utc)
    tasks = []
    for chat_id_str, user_data in users_db.items():
        try:
            chat_id = int(chat_id_str)
            if not user_data.get("active", True): continue
            if not user_data.get("is_paid", False) and await is_demo_expired(user_data): continue
            
            challenges = user_data.get("challenges", [])
            if isinstance(challenges, str): challenges = json.loads(challenges)
            
            updated = False
            for ch in challenges:
                if isinstance(ch, dict) and ch.get("accepted") and not ch.get("completed") and not ch.get("reminder_sent"):
                    try:
                        acc_dt = datetime.fromisoformat(ch["accepted"].replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                        hours = (now_utc - acc_dt).total_seconds() / 3600
                        if 1 <= hours < 1.5:
                            lang = get_user_lang(user_data)
                            preview = ch.get("text", "")
                            preview = preview[:100] + "..." if len(preview) > 100 else preview
                            
                            # ✅ ИСПОЛЬЗУЕМ ЛОКАЛИЗАЦИЮ
                            reminder_text = t("challenge_hour_reminder", lang=lang, name=user_data.get("name", "друг"), challenge=preview)
                            tasks.append(safe_send(bot, chat_id, reminder_text, parse_mode="HTML"))
                            ch["reminder_sent"] = True
                            updated = True
                    except Exception: continue
            if updated:
                await db.update_user(chat_id, challenges=json.dumps(challenges, ensure_ascii=False))
        except Exception: continue
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)

# --- 🔧 НАСТРОЙКА ПЛАНИРОВЩИКА ---

async def setup_jobs_and_cache(bot: Bot, users_db: dict, static_data: dict):
    logger.info("⏰ Setting up scheduler jobs...")
    job_ids = ["centralized_broadcast_job", "check_demo_expiry_job", "backup_job", "check_pending_challenges_job", "check_recently_accepted_challenges_job"]
    
    for job_id in job_ids:
        try:
            if scheduler.get_job(job_id): scheduler.remove_job(job_id)
        except Exception: pass

    scheduler.add_job(centralized_broadcast_job, trigger="cron", hour="*", minute=0, id="centralized_broadcast_job", kwargs={"bot": bot, "static_data": static_data}, replace_existing=True)
    scheduler.add_job(check_demo_expiry_job, trigger="cron", hour="*/6", minute=2, id="check_demo_expiry_job", kwargs={"bot": bot}, replace_existing=True)
    scheduler.add_job(backup_job, trigger="cron", hour=3, minute=5, id="backup_job", kwargs={"bot": bot}, replace_existing=True, misfire_grace_time=600, max_instances=1, coalesce=True)
    scheduler.add_job(check_pending_challenges_job, trigger="cron", hour="*", minute=0, id="check_pending_challenges_job", kwargs={"bot": bot}, replace_existing=True)
    scheduler.add_job(check_recently_accepted_challenges_job, trigger="cron", minute="*/30", id="check_recently_accepted_challenges_job", kwargs={"bot": bot}, replace_existing=True)
    
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ APScheduler started successfully")
    else:
        logger.info("✅ APScheduler jobs updated")