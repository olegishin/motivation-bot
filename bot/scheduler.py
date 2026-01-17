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

import asyncio
import shutil
import random
from datetime import datetime, timezone, timedelta
from typing import List, Any, Dict, Tuple
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import logger, settings
from bot.localization import t, DEFAULT_LANG
from bot.database import db
from bot.utils import get_user_tz, get_user_lang, check_demo_status, safe_send

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
    
    Фраза может быть:
    - dict с ключом "text"
    - list (не может быть — ошибка в БД)
    - просто string
    - None или пусто
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
    Если форматирование упадет, возвращаем текст без имени.
    """
    if not user_name:
        return text.replace("{name}", "").strip()
    
    try:
        if "{name}" in text:
            return text.format(name=user_name)
        return text
    except Exception as e:
        logger.error(f"Error formatting text with name '{user_name}': {e}")
        # Возвращаем текст без имени как фолбек
        return text.replace("{name}", "").strip()

def _safe_get_user_tz(user_data: Dict[str, Any]):
    """
    ✅ ИСПРАВЛЕНО (Ошибка #7): Безопасное получение часового пояса.
    С полным фолбеком на DEFAULT_TZ при ошибке.
    """
    try:
        return get_user_tz(user_data)
    except Exception as e:
        logger.warning(f"Error getting user timezone, using default: {e}")
        return get_user_tz({})  # Вернет DEFAULT_TZ

# --- 🧪 ТЕСТОВАЯ РАССЫЛКА ---

async def test_broadcast_job(bot: Bot, static_data: dict, chat_id: int, lang: str = "ru"):
    """
    Тестовая рассылка (вызывается админом командой /broadcast_test).
    Используется для проверки, что рассылки работают.
    """
    from bot.keyboards import get_broadcast_keyboard
    
    logger.info(f"Test broadcast: Starting for user {chat_id}, lang={lang}")
    
    try:
        data = static_data.get("morning_phrases", {})
        
        # Получаем фразы для языка пользователя
        if isinstance(data, dict):
            phrases = data.get(lang, data.get(DEFAULT_LANG, []))
        else:
            phrases = []
        
        if not phrases:
            logger.warning(f"Test broadcast: No phrases found for language {lang}")
            await safe_send(bot, chat_id, f"❌ Ошибка теста: Фразы для {lang} не найдены.")
            return
        
        # Выбираем случайную фразу
        phrase_raw = safe_choice(phrases)
        text = _safe_get_text(phrase_raw)
        
        if not text:
            logger.warning(f"Test broadcast: Could not extract text from phrase")
            await safe_send(bot, chat_id, "❌ Ошибка теста: Не удалось извлечь текст фразы.")
            return
        
        # Форматируем с именем
        phrase = _safe_format_text(text, "Тестер")
        
        kb = get_broadcast_keyboard(lang, quote_text=phrase, category="morning_phrases", user_name="Тестер")
        await safe_send(bot, chat_id, f"🧪 <b>Тест ({lang.upper()}):</b>\n\n{phrase}", reply_markup=kb)
        logger.info(f"Test broadcast: Sent successfully to {chat_id}")
        
    except Exception as e:
        logger.error(f"Test broadcast error for user {chat_id}: {e}", exc_info=True)

# --- 📢 ГЛАВНАЯ РАССЫЛКА ---

async def centralized_broadcast_job(bot: Bot, static_data: dict):
    """
    ✅ ИСПРАВЛЕНО (Ошибка #7): Главная рассылка с полной защитой от ошибок.
    
    Логика:
    1. Для каждого часа (8, 12, 15, 18) проверяем локальное время пользователя
    2. Если совпадает — выбираем контент (контент, маркетинг или демо напоминание)
    3. Отправляем пакетами (защита от рейт-лимитов Telegram)
    4. Логируем метрики
    
    Защита от ошибок:
    - Try-catch вокруг каждого пользователя (один упадет → остальные продолжат)
    - Безопасная обработка типов данных
    - Валидация TZ с фолбеком
    - Anti-freeze loop (asyncio.sleep каждые N пользователей)
    """
    
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
    
    # Карта: какой ЛОКАЛЬНЫЙ час → какой контент и напоминание
    SCHEDULE_MAP = {
        8:  ("morning_phrases", "reminder_8"),
        12: ("goals",           "reminder_12"),
        15: ("day_phrases",     "reminder_15"),
        18: ("evening_phrases", "reminder_18"),
    }
    
    tasks = []
    eligible_count = 0      # Пользователи в часовом окне
    processed_count = 0     # Всех обработано
    sent_count = 0          # Успешно отправлено
    error_count = 0         # Ошибок
    skipped_count = 0       # Пропущено (бан, оплачено, истекло)
    
    logger.debug(f"Processing {len(users_db)} users")
    
    for chat_id_str, user_data in users_db.items():
        processed_count += 1
        
        # Anti-freeze: даем event loop время на обработку других задач
        if processed_count % 200 == 0:
            await asyncio.sleep(0.2)
        elif processed_count % 50 == 0:
            await asyncio.sleep(0.05)
        
        try:
            chat_id = int(chat_id_str)
            
            # 1️⃣ ПРОВЕРКА: Smart Ban (забаненный пользователь)
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
                        # Таймаут истек, разбанить
                        await db.update_user(chat_id, active=True)
                        user_data["active"] = True
                except Exception as e:
                    logger.warning(f"Scheduler: Error parsing ban timeout for {chat_id}: {e}")
                    skipped_count += 1
                    continue
            
            # 2️⃣ ПОЛУЧИТЬ: Локальное время пользователя
            user_tz = _safe_get_user_tz(user_data)
            try:
                local_now = now_utc.astimezone(user_tz)
                local_hour = local_now.hour
                local_minute = local_now.minute
            except Exception as e:
                logger.warning(f"Scheduler: Error calculating local time for {chat_id}: {e}")
                skipped_count += 1
                continue
            
            # 3️⃣ ПРОВЕРКА: Нужно ли отправлять сейчас?
            # Отправляем в первые 5 минут часа (окно 00:00-00:05, 08:00-08:05 и т.д.)
            if local_hour not in SCHEDULE_MAP or local_minute >= 5:
                # Не в часовом окне
                continue
            
            eligible_count += 1
            content_key, reminder_key = SCHEDULE_MAP[local_hour]
            
            is_paid = user_data.get("is_paid", False)
            is_admin = (chat_id == settings.ADMIN_CHAT_ID)
            user_name = user_data.get("name") or "друг"
            user_lang = get_user_lang(user_data)
            
            logger.debug(f"Scheduler: User {chat_id} eligible ({local_hour}:00 local), is_paid={is_paid}, lang={user_lang}")
            
            # 4️⃣ ВЫБРАТЬ КОНТЕНТ
            
            # ✅ ПРЕМИУМ и АДМИН — всегда контент
            if is_admin or is_paid:
                try:
                    data = static_data.get(content_key, {})
                    
                    if isinstance(data, dict):
                        phrases = data.get(user_lang, data.get(DEFAULT_LANG, []))
                    else:
                        phrases = []
                    
                    if not phrases:
                        logger.warning(f"Scheduler: No {content_key} for {user_lang}, skipping {chat_id}")
                        skipped_count += 1
                        continue
                    
                    phrase_raw = safe_choice(phrases)
                    text = _safe_get_text(phrase_raw)
                    
                    if not text:
                        logger.warning(f"Scheduler: Could not extract text for {chat_id}")
                        skipped_count += 1
                        continue
                    
                    phrase = _safe_format_text(text, user_name)
                    kb = get_broadcast_keyboard(user_lang, quote_text=phrase, category=content_key, user_name=user_name)
                    
                    tasks.append(safe_send(bot, chat_id, phrase, reply_markup=kb))
                    sent_count += 1
                    
                except Exception as e:
                    logger.error(f"Scheduler: Error preparing content for paid user {chat_id}: {e}")
                    error_count += 1
                
                continue
            
            # ✅ ДЕМО ИСТЕК → маркетинг (напоминание об оплате)
            if check_demo_status(user_data):
                try:
                    demo_count = int(user_data.get("demo_count", 1))
                    if demo_count >= 2:
                        # Демо полностью истек → напоминание о платеже
                        reminder_text = t(reminder_key, user_lang, name=user_name)
                        kb = get_payment_keyboard(user_lang)
                        tasks.append(safe_send(bot, chat_id, reminder_text, reply_markup=kb))
                        sent_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    logger.error(f"Scheduler: Error preparing marketing for {chat_id}: {e}")
                    error_count += 1
                
                continue
            
            # ✅ АКТИВНЫЙ ДЕМО → контент
            try:
                data = static_data.get(content_key, {})
                
                if isinstance(data, dict):
                    phrases = data.get(user_lang, data.get(DEFAULT_LANG, []))
                else:
                    phrases = []
                
                if not phrases:
                    logger.warning(f"Scheduler: No {content_key} for {user_lang}, skipping {chat_id}")
                    skipped_count += 1
                    continue
                
                phrase_raw = safe_choice(phrases)
                text = _safe_get_text(phrase_raw)
                
                if not text:
                    logger.warning(f"Scheduler: Could not extract text for {chat_id}")
                    skipped_count += 1
                    continue
                
                phrase = _safe_format_text(text, user_name)
                kb = get_broadcast_keyboard(user_lang, quote_text=phrase, category=content_key, user_name=user_name)
                
                tasks.append(safe_send(bot, chat_id, phrase, reply_markup=kb))
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Scheduler: Error preparing content for demo user {chat_id}: {e}")
                error_count += 1
        
        except Exception as e:
            logger.error(f"Scheduler: Unexpected error for user {chat_id_str}: {e}", exc_info=True)
            error_count += 1
    
    # 5️⃣ ОТПРАВКА ПАКЕТАМИ (защита от рейт-лимитов Telegram)
    logger.info(f"📦 Sending {len(tasks)} messages in batches...")
    
    if tasks:
        for i in range(0, len(tasks), 30):
            batch = tasks[i:i+30]
            results = await asyncio.gather(*batch, return_exceptions=True)
            
            # Считаем успешные отправки
            batch_errors = sum(1 for r in results if isinstance(r, Exception))
            logger.debug(f"  Batch {i//30 + 1}: {len(batch) - batch_errors}/{len(batch)} sent successfully")
            
            # Пауза между пакетами (защита от лимитов Telegram: 30 msg/sec)
            if i + 30 < len(tasks):
                await asyncio.sleep(1)
    
    # 6️⃣ ЛОГИРОВАНИЕ МЕТРИК
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    
    logger.info("=" * 60)
    logger.info("📊 BROADCAST METRICS:")
    logger.info(f"  ⏱️  Duration: {duration:.2f} sec")
    logger.info(f"  👥 Total users in DB: {len(users_db)}")
    logger.info(f"  🎯 Eligible (in time window): {eligible_count}")
    logger.info(f"  ✅ Sent successfully: {sent_count}")
    logger.info(f"  ⏭️  Skipped (banned/expired/etc): {skipped_count}")
    logger.info(f"  ❌ Errors: {error_count}")
    logger.info(f"  📈 Success rate: {(sent_count / eligible_count * 100):.1f}%" if eligible_count > 0 else "  📈 Success rate: N/A")
    logger.info("=" * 60)

# --- ⏰ ПРОВЕРКА ИСТЕЧЕНИЯ ДЕМО ---

async def check_demo_expiry_job(bot: Bot):
    """
    ✅ ИСПРАВЛЕНО (Ошибка #7): Проверка истечения демо с защитой от ошибок.
    Отправляет напоминание за 24 часа до конца демо.
    """
    
    logger.debug("Check demo expiry: Starting")
    
    try:
        users_db = await db.get_all_users()
    except Exception as e:
        logger.error(f"Check demo expiry: Failed to load users: {e}")
        return
    
    now_utc = datetime.now(timezone.utc)
    tasks = []
    checked_count = 0
    warned_count = 0
    
    for chat_id_str, user_data in users_db.items():
        try:
            chat_id = int(chat_id_str)
            checked_count += 1
            
            # Пропускаем: оплатил, неактивен, уже предупрежден
            if user_data.get("is_paid") or not user_data.get("active") or user_data.get("sent_expiry_warning"):
                continue
            
            # Получаем дату истечения демо
            demo_exp_str = user_data.get("demo_expiration")
            if not demo_exp_str:
                continue
            
            try:
                exp_dt = datetime.fromisoformat(demo_exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.warning(f"Check demo expiry: Invalid date format for {chat_id}: {e}")
                continue
            
            # Если демо кончается через 0-24 часа → предупреждаем
            time_until_expiry = exp_dt - now_utc
            if timedelta(hours=0) < time_until_expiry <= timedelta(hours=24):
                try:
                    lang = get_user_lang(user_data)
                    user_name = user_data.get("name") or "друг"
                    
                    from bot.keyboards import get_payment_keyboard
                    
                    tasks.append(
                        safe_send(
                            bot, 
                            chat_id, 
                            t("demo_expiring_soon_h", lang=lang, name=user_name, hours=24),
                            reply_markup=get_payment_keyboard(lang)
                        )
                    )
                    
                    # Отмечаем, что предупредили
                    await db.update_user(chat_id, sent_expiry_warning=True)
                    warned_count += 1
                    
                except Exception as e:
                    logger.error(f"Check demo expiry: Error for {chat_id}: {e}")
        
        except Exception as e:
            logger.error(f"Check demo expiry: Unexpected error for {chat_id_str}: {e}")
    
    # Отправляем все предупреждения
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info(f"✅ Check demo expiry: Checked {checked_count} users, warned {warned_count}")

# --- 💾 БЭКАП БАЗЫ ДАННЫХ ---

async def backup_job(bot: Bot):
    """
    Ежедневный бэкап БД (в 3:05 UTC).
    Отправляет файл админу и удаляет старые бэкапы (старше 30 дней).
    """
    
    logger.info("💾 Backup: Starting...")
    
    if not settings.DB_FILE.exists():
        logger.warning("Backup: DB file not found")
        return
    
    BACKUP_DIR = settings.DATA_DIR / "backups"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_path = BACKUP_DIR / f"fotinia_{timestamp}.db"
    
    try:
        # Создаем папку для бэкапов
        BACKUP_DIR.mkdir(exist_ok=True, parents=True)
        
        # Копируем БД
        shutil.copy2(settings.DB_FILE, backup_path)
        logger.info(f"✅ Backup: Database copied to {backup_path}")
        
        # Отправляем админу
        await bot.send_document(
            chat_id=settings.ADMIN_CHAT_ID, 
            document=FSInputFile(backup_path), 
            caption=f"📦 <b>Daily Backup</b>\n📅 {timestamp}"
        )
        logger.info(f"✅ Backup: Sent to admin")
        
        # Удаляем старые бэкапы (больше 30)
        backups = sorted(BACKUP_DIR.glob("fotinia_*.db"))
        if len(backups) > 30:
            for old in backups[:-30]:
                old.unlink()
            logger.info(f"🧹 Backup: Cleaned old backups (kept last 30)")
        
    except Exception as e:
        logger.error(f"❌ Backup failed: {e}", exc_info=True)

# --- 🔧 НАСТРОЙКА ПЛАНИРОВЩИКА ---

async def setup_jobs_and_cache(bot: Bot, users_db: dict, static_data: dict):
    """
    Регистрирует все задачи планировщика.
    
    Задачи:
    - centralized_broadcast_job: каждый час в 00 минут (рассылки)
    - check_demo_expiry_job: каждые 6 часов в 02 минуты (напоминания)
    - backup_job: ежедневно в 3:05 UTC (бэкап БД)
    """
    
    logger.info("⏰ Setting up scheduler jobs...")
    
    job_ids = ["centralized_broadcast_job", "check_demo_expiry_job", "backup_job"]
    
    # Удаляем старые задачи (если они были)
    for job_id in job_ids:
        try:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                logger.debug(f"  Removed old job: {job_id}")
        except Exception:
            pass

    # 1. Главная рассылка (каждый час)
    scheduler.add_job(
        centralized_broadcast_job, 
        trigger="cron", 
        hour="*", 
        minute=0, 
        id="centralized_broadcast_job",
        kwargs={"bot": bot, "static_data": static_data}, 
        replace_existing=True
    )
    logger.info("  ✅ centralized_broadcast_job: every hour at :00")

    # 2. Проверка истечения демо (каждые 6 часов)
    scheduler.add_job(
        check_demo_expiry_job, 
        trigger="cron", 
        hour="*/6", 
        minute=2, 
        id="check_demo_expiry_job",
        kwargs={"bot": bot}, 
        replace_existing=True
    )
    logger.info("  ✅ check_demo_expiry_job: every 6 hours at :02")

    # 3. Бэкап БД (ежедневно в 3:05 UTC)
    scheduler.add_job(
        backup_job, 
        trigger="cron", 
        hour=3, 
        minute=5, 
        id="backup_job",
        kwargs={"bot": bot}, 
        replace_existing=True, 
        misfire_grace_time=600,  # Если задача пропущена, запустить в течение 10 мин
        max_instances=1,         # Не запускать параллельные копии
        coalesce=True            # Если задача отстала, запустить только один раз
    )
    logger.info("  ✅ backup_job: daily at 03:05 UTC")

    # Запускаем планировщик, если он еще не работает
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ APScheduler started successfully")
    else:
        logger.info("✅ APScheduler jobs updated")