#!/usr/bin/env python3
"""
🚀 FOTINIA BOT v6.3 (DEBUG SYNC)
✅ ФУНКЦИОНАЛ: Полная админка, /pay, сложная логика челленджей, статистика.
✅ АРХИТЕКТУРА: FastAPI, JSON+Lock, 1 Job Scheduler, современная работа со временем.
🐞 ИСПРАВЛЕНИЕ: Добавлено детальное логирование в setup_initial_files для
                 проверки содержимого исходных файлов перед копированием.
"""
import os
import json
import random
import logging
import asyncio
import tempfile
import shutil
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any
from contextlib import asynccontextmanager

# Webhook и FastAPI
from fastapi import FastAPI, Request

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import Forbidden, BadRequest, RetryAfter

# ----------------- КОНФИГУРАЦИЯ -----------------
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(handler)
logger.propagate = False
logger.setLevel(logging.DEBUG)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SPECIAL_USER_ID = 290711961
DEFAULT_TZ = ZoneInfo("Europe/Kiev")

logger.info("🤖 Bot starting...")
logger.info(f"🔑 ADMIN_CHAT_ID configured as: {ADMIN_CHAT_ID}")

# --- 📍 ПУТИ К ФАЙЛАМ ---
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))

# --- 📄 НАЗВАНИЯ ФАЙЛОВ ---
USERS_FILE = DATA_DIR / "users.json"
FILE_MAPPING = {
    "challenges": "challenges.json", "rules": "universe_laws.json",
    "motivations": "fotinia_motivations.json", "ritm": "fotinia_ritm.json",
    "morning_phrases": "fotinia_morning_phrases.json", "goals": "fotinia_goals.json",
    "day_phrases": "fotinia_day_phrases.json", "evening_phrases": "fotinia_evening_phrases.json"
}

# --- ⌨️ КНОПКИ ---
BTN_MOTIVATE, BTN_RHYTHM = "💪 Мотивируй меня", "🎵 Ритм дня"
BTN_CHALLENGE, BTN_RULES = "⚔️ Челлендж дня", "📜 Правила Вселенной"
BTN_PROFILE = "👤 Профиль"
BTN_SHOW_USERS, BTN_STATS = "📂 Смотреть users.json", "📊 Статистика пользователей"
BTN_RELOAD_DATA, BTN_EXTEND_DEMO = "🔄 Обновить", "🔄 Продлить демо"

USER_KEYBOARD_LAYOUT = [
    [BTN_MOTIVATE, BTN_RHYTHM],
    [BTN_CHALLENGE, BTN_RULES],
    [BTN_PROFILE]
]

ADMIN_KEYBOARD_LAYOUT = [
    [BTN_MOTIVATE, BTN_RHYTHM],
    [BTN_CHALLENGE, BTN_RULES],
    [BTN_SHOW_USERS, BTN_STATS, BTN_RELOAD_DATA]
]

MAIN_MARKUP = ReplyKeyboardMarkup(USER_KEYBOARD_LAYOUT, resize_keyboard=True)
OWNER_MARKUP = ReplyKeyboardMarkup(ADMIN_KEYBOARD_LAYOUT, resize_keyboard=True)
EXPIRED_DEMO_MARKUP = ReplyKeyboardMarkup([[BTN_EXTEND_DEMO]], resize_keyboard=True)

USERS_FILE_LOCK = asyncio.Lock()

# ----------------- РАБОТА С ДАННЫМИ -----------------
def load_json_data(filepath: Path, default_factory=list) -> Any:
    if not filepath.exists(): return default_factory()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            if not content or content.strip() in ('[]', '{}'):
                logger.warning(f"Файл {filepath.name} пуст или содержит только '[]'/'{{}}'. Используется значение по умолчанию.")
                return default_factory()
            return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Ошибка чтения или парсинга {filepath.name}: {e}. Используется значение по умолчанию.")
        return default_factory()

def save_users_sync(users_data: dict) -> None:
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=DATA_DIR) as tmp:
            json.dump(users_data, tmp, ensure_ascii=False, indent=2)
        shutil.move(tmp.name, USERS_FILE)
    except Exception as e: logger.error(f"❌ Ошибка сохранения users.json: {e}")

async def save_users(context: ContextTypes.DEFAULT_TYPE, users_data: dict) -> None:
    async with USERS_FILE_LOCK:
        context.application.bot_data["users"] = users_data.copy()
        await asyncio.get_running_loop().run_in_executor(None, save_users_sync, users_data)

def setup_initial_files():
    """
    Умная синхронизация с отладкой: копирует файлы из data_initial в data, если:
    1. Файла в data нет.
    2. Файл в data_initial новее.
    3. Файл в data существует, но пустой (< 10 байт).
    Добавлено логирование содержимого исходных файлов.
    """
    logger.info(f"Синхронизация файлов в persistent-директории '{DATA_DIR}'...")
    DATA_DIR.mkdir(exist_ok=True)
    
    source_data_dir = Path(__file__).parent / "data_initial"
    if not source_data_dir.exists():
        logger.warning(f"⚠️ Папка 'data_initial' не найдена. Невозможно скопировать исходные данные.")
        # Создаем пустые файлы на всякий случай, чтобы бот не падал
        for filename in FILE_MAPPING.values():
             filepath = DATA_DIR / filename
             if not filepath.exists():
                  with open(filepath, "w", encoding="utf-8") as f: json.dump([], f)
                  logger.warning(f"  -> ⚠️ Создан пустой файл '{filename}'.")
        # users.json
        if not USERS_FILE.exists():
             with open(USERS_FILE, "w", encoding="utf-8") as f: json.dump({}, f)
             logger.warning(f"  -> ⚠️ Файл '{USERS_FILE.name}' не найден, создан пустой.")
        return

    copied_count = 0
    for filename in os.listdir(source_data_dir):
        source_path = source_data_dir / filename
        dest_path = DATA_DIR / filename
        
        # Пропускаем, если это не файл
        if not source_path.is_file():
            continue

        # ✅ Добавлено логирование содержимого исходного файла
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                source_content = f.read().strip()
                logger.debug(f"Source {filename} content: {source_content[:50]}{'...' if len(source_content) > 50 else ''} (Size: {source_path.stat().st_size} bytes)")
        except Exception as e:
            logger.error(f"Не удалось прочитать исходный файл {source_path}: {e}")
            continue # Пропускаем этот файл, если не можем прочитать

        should_copy = False
        reason = "нет"
        if not dest_path.exists():
            should_copy = True
            reason = "не существует"
        else:
            try:
                dest_size = dest_path.stat().st_size
                source_mtime = source_path.stat().st_mtime
                dest_mtime = dest_path.stat().st_mtime
                logger.debug(f"Comparing {filename}: Dest size={dest_size}, Source mtime={source_mtime}, Dest mtime={dest_mtime}")

                if dest_size < 10:
                    should_copy = True
                    reason = "пустой"
                elif source_mtime > dest_mtime:
                    should_copy = True
                    reason = "новее"
            except OSError as e:
                logger.error(f"Не удалось получить информацию о файле {dest_path}: {e}")
                should_copy = True
                reason = "ошибка доступа"

        if should_copy:
            try:
                shutil.copy2(source_path, dest_path)
                logger.info(f"  -> ✅ Файл '{filename}' скопирован/обновлен (причина: {reason}).")
                copied_count += 1
            except Exception as e:
                logger.error(f"  -> ❌ Не удалось скопировать '{filename}': {e}")

    # Отдельно убедимся, что users.json существует
    if not USERS_FILE.exists():
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        logger.warning(f"  -> ⚠️ Файл '{USERS_FILE.name}' не найден, создан пустой.")
        
    logger.info(f"✅ Синхронизация завершена. Скопировано/обновлено файлов: {copied_count}.")


# ... (остальной код остается без изменений) ...

# ----------------- УТИЛИТЫ -----------------
def strip_html_tags(text: str) -> str: return re.sub('<[^<]+?>', '', text)
def is_admin(chat_id: int) -> bool: return chat_id == ADMIN_CHAT_ID

def is_demo_expired(user_data: dict) -> bool:
    if not user_data: return True
    if user_data.get("is_paid") or user_data.get("id") == SPECIAL_USER_ID: return False
    demo_exp = user_data.get("demo_expiration")
    if not demo_exp: return False
    try:
        expiration_dt = datetime.fromisoformat(demo_exp).replace(tzinfo=ZoneInfo("UTC"))
        return datetime.now(ZoneInfo("UTC")) > expiration_dt
    except (ValueError, TypeError): return True

async def safe_send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs):
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', **kwargs)
        return True
    except Forbidden:
        users_data = context.application.bot_data.setdefault("users", {})
        if str(chat_id) in users_data and users_data[str(chat_id)].get("active", True):
            users_data[str(chat_id)]["active"] = False
            await save_users(context, users_data)
        return False
    except RetryAfter as e:
        logger.warning(f"Flood control: Wating {e.retry_after} seconds for chat {chat_id}")
        await asyncio.sleep(e.retry_after)
        return await safe_send(context, chat_id, text, **kwargs)
    except BadRequest as e:
        logger.warning(f"Ошибка отправки сообщения в чат {chat_id}: {e}")
        return False

# ----------------- ⏰ ПЛАНИРОВЩИК -----------------
async def centralized_broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    now_utc = datetime.now(ZoneInfo("UTC"))
    users_data = context.application.bot_data.get("users", {})
    schedules = [(8, "morning_phrases"), (12, "goals"), (15, "day_phrases"), (18, "evening_phrases")]
    tasks = []
    
    if now_utc.minute > 5:
        return

    for hour, key in schedules:
        phrases = context.application.bot_data.get(key, [])
        if not phrases: continue
        for chat_id_str, user_data in users_data.items():
            if not user_data.get("active") or is_demo_expired(user_data): continue
            try:
                user_tz = ZoneInfo(user_data.get("timezone", DEFAULT_TZ.key))
                if now_utc.astimezone(user_tz).hour == hour:
                    phrase = random.choice(phrases).format(name=user_data.get("name", "друг"))
                    tasks.append(safe_send(context, int(chat_id_str), phrase))
            except Exception as e: logger.error(f"Ошибка в планировщике для {chat_id_str}: {e}")
    if tasks:
        results = await asyncio.gather(*tasks)
        if (sent_count := sum(1 for res in results if res)) > 0:
            logger.info(f"📢 Рассылка завершена. Отправлено {sent_count} сообщений.")

# ----------------- 🖥️ ХЕНДЛЕРЫ -----------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.application.bot_data.get("users", {})
    user_name = update.effective_user.first_name or "друг"
    user_id_str = str(chat_id)
    
    is_new_user = user_id_str not in users_data

    if is_new_user:
        users_data[user_id_str] = {
            "id": chat_id, "name": user_name, "active": True, "timezone": DEFAULT_TZ.key,
            "demo_expiration": (datetime.now(ZoneInfo("UTC")) + timedelta(days=7)).isoformat(),
            "demo_count": 1, "last_challenge_date": None, "challenge_accepted": None
        }
        logger.info(f"👤 Новый пользователь: {chat_id} ({user_name})")
        if chat_id != ADMIN_CHAT_ID:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Показать статистику", callback_data="admin_stats")]])
            await safe_send(context, ADMIN_CHAT_ID, f"🎉 Новый пользователь: {user_name} (ID: {chat_id})", reply_markup=keyboard)
    else:
        user_entry = users_data[user_id_str]
        user_entry["active"], user_entry["name"] = True, user_name
        if is_demo_expired(user_entry):
            user_entry["demo_count"] = user_entry.get("demo_count", 1) + 1
            user_entry["demo_expiration"] = (datetime.now(ZoneInfo("UTC")) + timedelta(days=7)).isoformat()
    
    await save_users(context, users_data)
    
    markup = OWNER_MARKUP if is_admin(chat_id) else MAIN_MARKUP
    await safe_send(context, chat_id, f"🌟 Привет, {user_name}! Я бот Фотиния, твой личный помощник по саморазвитию.", reply_markup=markup)

async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Для получения полного доступа, пожалуйста, свяжитесь с администратором.")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.application.bot_data["users"].get(str(update.effective_chat.id), {})
    challenges = user_data.get("challenges", [])
    completed = sum(1 for c in challenges if c.get("completed"))
    status = "⭐ Premium" if user_data.get('is_paid') else "🆓 Демо"
    text = (f"👤 <b>Ваш профиль:</b>\n\n"
            f"📛 Имя: {user_data.get('name', 'Неизвестно')}\n"
            f"⚔️ Принято челленджей: {len(challenges)}\n"
            f"✅ Выполнено: {completed}\n"
            f"💰 Статус: {status}")
    await update.message.reply_text(text, parse_mode="HTML")

async def send_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, title: str):
    item_list = context.application.bot_data.get(key, [])
    if not item_list:
        await safe_send(context, update.effective_chat.id, f"⚠️ Список для '{title}' пуст.")
        return
    user_name = context.application.bot_data["users"].get(str(update.effective_chat.id), {}).get("name", "друг")
    item = random.choice(item_list).format(name=user_name)
    await update.message.reply_text(f"<b>{title}</b>\n{item}", parse_mode="HTML")

async def send_motivation(u: Update, c: ContextTypes.DEFAULT_TYPE): await send_from_list(u, c, "motivations", "💪")
async def send_rhythm(u: Update, c: ContextTypes.DEFAULT_TYPE): await send_from_list(u, c, "ritm", "🎶 Ритм дня:")

async def send_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules_list = context.application.bot_data.get("rules", [])
    if not rules_list: await safe_send(context, update.effective_chat.id, "⚠️ Список правил пуст."); return
    rules = "\n".join(f"• {r}" for r in rules_list)
    await update.message.reply_text(f"📜 <b>Правила Вселенной:</b>\n{rules}", parse_mode="HTML")

async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.application.bot_data["users"].get(str(update.effective_chat.id), {})
    user_tz = ZoneInfo(user_data.get("timezone", DEFAULT_TZ.key))
    today = datetime.now(user_tz).date().isoformat()
    if user_data.get("last_challenge_date") == today:
        await update.message.reply_text("⏳ Вы уже получили челлендж на сегодня.")
        return
    await send_new_challenge_message(update, context)

async def send_new_challenge_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_edit=False):
    chat_id = update.effective_chat.id
    challenge_list = context.application.bot_data.get('challenges', [])
    if not challenge_list: await safe_send(context, chat_id, "⚠️ Список челленджей пуст."); return
    challenge = random.choice(challenge_list)
    clean_challenge = strip_html_tags(challenge)[:40]
    keyboard = [[InlineKeyboardButton("✅ Принять", callback_data=f"accept_challenge:{clean_challenge}"),
                 InlineKeyboardButton("🎲 Новый", callback_data="new_challenge")]]
    text = f"⚔️ <b>Челлендж дня:</b>\n{challenge}"
    sender = update.callback_query.edit_message_text if is_edit else update.message.reply_text
    await sender(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    users_data = context.application.bot_data["users"]
    user_tz = ZoneInfo(users_data.get(str(chat_id), {}).get("timezone", DEFAULT_TZ.key))
    today = datetime.now(user_tz).date().isoformat()
    users_data[str(chat_id)]["last_challenge_date"] = today
    users_data[str(chat_id)]["challenge_accepted"] = False
    await save_users(context, users_data)

async def extend_demo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Для продления доступа, пожалуйста, свяжитесь с администратором.")

# --- Админские функции ---
async def show_users_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if USERS_FILE.exists() and USERS_FILE.stat().st_size > 2:
        with open(USERS_FILE, "rb") as f:
            await update.message.reply_document(document=f, caption="📂 users.json")
    else:
        await update.message.reply_text("Файл users.json ещё не создан или пуст.")

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_data = {k: v for k, v in context.application.bot_data["users"].items() if int(k) != SPECIAL_USER_ID}
    total = len(users_data)
    active = sum(1 for u in users_data.values() if u.get("active"))
    inactive = total - active
    active_first = sum(1 for u in users_data.values() if u.get("active") and u.get("demo_count", 1) == 1)
    active_repeat = sum(1 for u in users_data.values() if u.get("active") and u.get("demo_count", 1) > 1)
    inactive_demo_expired = sum(1 for u in users_data.values() if not u.get("active") and is_demo_expired(u))
    inactive_blocked = inactive - inactive_demo_expired
    stats_text = (f"👥 <b>Всего:</b> {total}\n\n✅ <b>Активных:</b> {active}\n"
                  f"   - <i>Первый раз:</i> {active_first}\n   - <i>Повторно:</i> {active_repeat}\n\n"
                  f"❌ <b>Неактивных:</b> {inactive}\n"
                  f"   - <i>Закончилось демо:</i> {inactive_demo_expired}\n   - <i>Заблокировали:</i> {inactive_blocked}")
    
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def reload_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setup_jobs_and_cache(context.application)
    await update.message.reply_text("✅ Кэш и задачи планировщика обновлены!")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id_str = str(query.from_user.id)
    
    logger.info(f"💬 Callback от {query.from_user.id}: {query.data}")

    users_data = context.application.bot_data["users"]
    data = query.data

    if data.startswith("accept_challenge:"):
        challenge_text = query.message.text.split(":\n", 1)[-1].strip()
        users_data[chat_id_str]["challenge_accepted"] = True
        challenges = users_data[chat_id_str].setdefault("challenges", [])
        challenges.append({"text": challenge_text, "accepted": datetime.now().isoformat(), "completed": None})
        await save_users(context, users_data)
        await query.edit_message_text(f"💪 <b>Челлендж принят:</b>\n\n<i>{challenge_text}</i>", parse_mode="HTML")
    elif data == "new_challenge":
        await send_new_challenge_message(update, context, is_edit=True)
    elif data == "admin_stats":
        if is_admin(query.from_user.id):
            mock_update = type('MockUpdate', (), {'message': query.message})
            mock_update.message.chat.id = query.from_user.id
            await user_stats(mock_update, context)

# --- ⭐️ ГЛАВНЫЙ ДИСПЕТЧЕР СООБЩЕНИЙ ⭐️ ---
async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    text, chat_id = update.message.text, update.effective_chat.id
    
    user_data = context.application.bot_data.get("users", {}).get(str(chat_id))
    if not user_data:
        await update.message.reply_text("Похоже, мы ещё не знакомы. Пожалуйста, нажмите /start, чтобы начать.")
        return

    is_user_admin = is_admin(chat_id)
    if is_demo_expired(user_data) and not is_user_admin:
        if text == BTN_EXTEND_DEMO:
             await extend_demo(update, context)
        else:
             await safe_send(context, chat_id, text=f"👋 {user_data.get('name', 'друг')}!\n🔒 <b>Ваш демо-доступ закончился.</b>", reply_markup=EXPIRED_DEMO_MARKUP)
        return
        
    all_handlers = {
        BTN_MOTIVATE: send_motivation, BTN_RHYTHM: send_rhythm, BTN_RULES: send_rules,
        BTN_CHALLENGE: challenge_command, BTN_PROFILE: profile_command,
        BTN_EXTEND_DEMO: extend_demo,
        BTN_STATS: user_stats, BTN_SHOW_USERS: show_users_file, BTN_RELOAD_DATA: reload_data
    }

    handler_to_call = all_handlers.get(text)

    if handler_to_call:
        admin_only_buttons = {BTN_STATS, BTN_SHOW_USERS, BTN_RELOAD_DATA}
        if text in admin_only_buttons and not is_user_admin:
            logger.warning(f"Пользователь {chat_id} попытался использовать админ-команду: {text}")
        else:
            await handler_to_call(update, context)
    else:
        markup = OWNER_MARKUP if is_user_admin else MAIN_MARKUP
        await update.message.reply_text("❓ Неизвестная команда. Пожалуйста, используйте кнопки.", reply_markup=markup)

# ----------------- 🚀 ЗАПУСК И НАСТРОЙКА -----------------
async def setup_jobs_and_cache(app: Application):
    try:
        app.bot_data["users"] = load_json_data(USERS_FILE, default_factory=dict)
        logger.info(f"👥 Загружено {len(app.bot_data['users'])} пользователей")
        
        for key, filename in FILE_MAPPING.items():
            filepath = DATA_DIR / filename
            data = load_json_data(filepath)
            app.bot_data[key] = data
            logger.info(f"  -> {filename}: {len(data)} записей")
            
        logger.info("📚 Кэш статических данных загружен")
        
        if app.job_queue:
            for job in app.job_queue.jobs():
                job.schedule_removal()
                logger.debug(f"Удалена job: {job}")
                
        first_run = datetime.now(DEFAULT_TZ) + timedelta(seconds=15)
        app.job_queue.run_repeating(centralized_broadcast_job, interval=timedelta(hours=1), first=first_run)
        logger.info("✅ Планировщик настроен!")
    except Exception as e:
        logger.error(f"❌ Ошибка в setup_jobs_and_cache: {e}")
        raise

application = ApplicationBuilder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("pay", pay_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))
application.add_handler(CallbackQueryHandler(handle_callback_query))

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        if not BOT_TOKEN:
            logger.critical("❌ BOT_TOKEN не задан! Бот не запустится.")
            yield; return
        if not ADMIN_CHAT_ID or ADMIN_CHAT_ID == 0:
            logger.critical("❌ ADMIN_CHAT_ID не задан! Бот не запустится.")
            yield; return

        setup_initial_files()
        await application.initialize()
        await setup_jobs_and_cache(application)
        await application.start()
        
        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL}/telegram/{BOT_TOKEN}"
            await application.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook установлен.")
        else:
            logger.info("⚠️ WEBHOOK_URL не задан — используется polling (локально).")
        
        await application.bot.send_message(ADMIN_CHAT_ID, "🤖 Бот успешно запущен (v6.3 Debug Sync)")
        logger.info("✅ Lifespan STARTED - Бот готов!")
    
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА в lifespan: {e}")
        logger.exception("Полный traceback:") # Log full traceback
        raise
        
    yield
    
    try:
        await application.stop()
        await application.shutdown()
        logger.info("✅ Lifespan STOPPED")
    except Exception as e:
        logger.error(f"❌ Ошибка при остановке: {e}")

app = FastAPI(lifespan=lifespan)

@app.post(f"/telegram/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    update = Update.de_json(await request.json(), application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def health_check(): return {"status": "fotinia-v6.3-debug-sync-ready"}

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск в режиме Polling")
        setup_initial_files()
        asyncio.run(setup_jobs_and_cache(application))
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Ошибка в polling: {e}")
        logger.exception("Полный traceback:")

