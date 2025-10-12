import os
import json
import random
import logging
import asyncio
import tempfile
import shutil
import re
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, time
import pytz
from collections import defaultdict
from typing import Dict, List, Optional, Any

# Добавляем новые импорты
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Импорты Telegram и FastAPI
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import Forbidden, BadRequest, RetryAfter
from fastapi import FastAPI, Request
import uvicorn

# Локальный запуск
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

# Блок: Настройка логирования
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Блок: Загрузка секретов и проверка
load_dotenv("token_id.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
SPECIAL_USER_ID = 290711961

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан в переменных окружения!")
try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
except (TypeError, ValueError):
    raise ValueError("❌ ADMIN_CHAT_ID должен быть числом")

# Блок: Определение путей к файлам
BASE_DIR = Path(__file__).parent
DATA_DIR = Path("/data")  # Для Fly, локально можно использовать S:\fotinia_bot\data
DATA_DIR.mkdir(exist_ok=True)
logger.info(f"📁 DATA_DIR: {DATA_DIR.resolve()}")

USERS_FILE = DATA_DIR / "users.json"
CHALLENGES_FILE = DATA_DIR / "challenges.json"  # Челлендж дня
RULES_FILE = DATA_DIR / "universe_laws.json"   # Правила вселенной
MOTIVATIONS_FILE = DATA_DIR / "fotinia_motivations.json"  # Мотивируй меня
RITM_FILE = DATA_DIR / "fotinia_ritm.json"     # Ритм дня
MORNING_FILE = DATA_DIR / "fotinia_morning_phrases.json"  # Утренняя рассылка 8:00
GOALS_FILE = DATA_DIR / "fotinia_goals.json"   # Случайная рассылка 12:00
DAY_FILE = DATA_DIR / "fotinia_day_phrases.json"  # Дневная рассылка 15:00
EVENING_FILE = DATA_DIR / "fotinia_evening_phrases.json"  # Вечерняя рассылка 18:00

# Блок: Кнопки и клавиатуры
BTN_MOTIVATE = "💪 Мотивируй меня"
BTN_RHYTHM = "🎵 Ритм дня"
BTN_CHALLENGE = "⚔️ Челлендж дня"
BTN_RULES = "📜 Правила Вселенной"
BTN_SHOW_USERS = "📂 Смотреть users.json"
BTN_STATS = "📊 Статистика пользователей"
BTN_EXTEND_DEMO = "🔄 Продлить демо"

MAIN_KEYBOARD = [[BTN_MOTIVATE, BTN_RHYTHM], [BTN_CHALLENGE, BTN_RULES]]
EXPIRED_DEMO_KEYBOARD = [[BTN_EXTEND_DEMO]]
ADMIN_BUTTONS = [[BTN_SHOW_USERS, BTN_STATS]]
MAIN_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
EXPIRED_DEMO_MARKUP = ReplyKeyboardMarkup(EXPIRED_DEMO_KEYBOARD, resize_keyboard=True)
OWNER_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD + ADMIN_BUTTONS, resize_keyboard=True)

# Блок: Утилиты
def load_json(filepath: Path) -> List | Dict:
    """Загружает JSON-файл с обработкой ошибок."""
    if not filepath.exists():
        logger.warning(f"⚠️ Файл {filepath} не найден.")
        return [] if any(key in str(filepath) for key in ["challenges", "universe_laws", "fotinia_motivations", "fotinia_ritm", "fotinia_morning_phrases", "fotinia_goals", "fotinia_day_phrases", "fotinia_evening_phrases"]) else {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"✅ Загружен {filepath}: {len(data) if isinstance(data, list) else 'dict'} элементов")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка декодирования {filepath}: {e}")
        return [] if any(key in str(filepath) for key in ["challenges", "universe_laws", "fotinia_motivations", "fotinia_ritm", "fotinia_morning_phrases", "fotinia_goals", "fotinia_day_phrases", "fotinia_evening_phrases"]) else {}
    except Exception as e:
        logger.error(f"❌ Ошибка чтения {filepath}: {e}")
        return [] if any(key in str(filepath) for key in ["challenges", "universe_laws", "fotinia_motivations", "fotinia_ritm", "fotinia_morning_phrases", "fotinia_goals", "fotinia_day_phrases", "fotinia_evening_phrases"]) else {}

def load_users() -> Dict:
    """Загружает данные пользователей."""
    return load_json(USERS_FILE) or {}

def save_users(users_data: Dict) -> None:
    """Сохраняет данные пользователей с использованием временного файла."""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=DATA_DIR) as tmp:
            json.dump(users_data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        shutil.move(tmp_path, USERS_FILE)
        logger.info(f"💾 Сохранено {len(users_data)} пользователей")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения {USERS_FILE}: {e}")

def get_user_timezone(users_data: Dict, chat_id: int) -> pytz.BaseTzInfo:
    """Получает таймзону пользователя с резервом на Europe/Kiev."""
    tz_name = users_data.get(str(chat_id), {}).get("timezone", "Europe/Kiev")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        logger.warning(f"⚠️ Неверная таймзона '{tz_name}' для {chat_id}, используется Europe/Kiev")
        return pytz.timezone("Europe/Kiev")

def get_user_name(users_data: Dict, chat_id: int, default="друг") -> str:
    """Получает имя пользователя с резервным значением."""
    return users_data.get(str(chat_id), {}).get("name", default)

def is_demo_expired(users_data: Dict, chat_id: int) -> bool:
    """Проверяет истечение демо-периода."""
    if chat_id == SPECIAL_USER_ID:
        return False
    user = users_data.get(str(chat_id))
    if not user:
        return True
    demo_exp = user.get("demo_expiration")
    if demo_exp is None:
        return False
    try:
        expiration = datetime.fromisoformat(demo_exp).replace(tzinfo=pytz.UTC)
        return datetime.now(pytz.UTC) > expiration
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки demo_expiration для {chat_id}: {e}")
        return True

def is_grace_period_expired(users_data: Dict, chat_id: int) -> bool:
    """Проверяет истечение периода милости."""
    if chat_id == SPECIAL_USER_ID:
        return False
    user = users_data.get(str(chat_id))
    if not user or "grace_period_end" not in user:
        return False
    try:
        grace_end = datetime.fromisoformat(user["grace_period_end"]).replace(tzinfo=pytz.UTC)
        return datetime.now(pytz.UTC) > grace_end
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки grace_period_end для {chat_id}: {e}")
        return True

def safe_format(text: str, **kwargs) -> str:
    """Форматирует текст с безопасной обработкой."""
    def default_format(k): return kwargs.get(k, "{" + k + "}")
    return text.format_map(defaultdict(str, **kwargs))

def make_callback_challenge(text: str) -> str:
    """Создаёт уникальный callback ID для челленджа."""
    clean_text = re.sub(r'[^\x00-\x7F]+', '', text)[:40]
    hash_suffix = hashlib.md5(text.encode("utf-8")).hexdigest()[:6]
    callback = f"{clean_text}_{hash_suffix}"
    return callback[:60] if len(callback.encode("utf-8")) > 64 else callback

# Блок: Обработчики
async def post_init(application: Application) -> None:
    """Инициализация бота при запуске."""
    logger.info("✅ Бот готов к запуску")
    users_data = load_users()
    application.bot_data["users"] = users_data
    logger.info(f"👥 Загружено {len(users_data)} пользователей")

    # Кэширование JSON-файлов
    for key, file in [
        ("challenges", CHALLENGES_FILE),
        ("rules", RULES_FILE),
        ("motivations", MOTIVATIONS_FILE),
        ("rhythm", RITM_FILE),
        ("morning_phrases", MORNING_FILE),
        ("goals", GOALS_FILE),
        ("day_phrases", DAY_FILE),
        ("evening_phrases", EVENING_FILE)
    ]:
        application.bot_data[key] = load_json(file)
    logger.info("📚 Кэшированы файлы: "
                f"challenges={len(application.bot_data['challenges'])}, "
                f"rules={len(application.bot_data['rules'])}, "
                f"motivations={len(application.bot_data['motivations'])}, "
                f"rhythm={len(application.bot_data['rhythm'])}, "
                f"morning_phrases={len(application.bot_data['morning_phrases'])}, "
                f"goals={len(application.bot_data['goals'])}, "
                f"day_phrases={len(application.bot_data['day_phrases'])}, "
                f"evening_phrases={len(application.bot_data['evening_phrases'])}")

    # Очистка старых задач
    for job in application.job_queue.jobs():
        job.schedule_removal()
    logger.info("🧹 Очищены старые задачи планировщика")

    # Планирование рассылок
    schedules = [
        {"hour": 8, "minute": 0, "file": MORNING_FILE, "log": "🌅 Утро", "key": "morning_phrases"},
        {"hour": 12, "minute": 0, "file": GOALS_FILE, "log": "🎲 Случайная", "key": "goals"},
        {"hour": 15, "minute": 0, "file": DAY_FILE, "log": "☀️ День", "key": "day_phrases"},
        {"hour": 18, "minute": 0, "file": EVENING_FILE, "log": "🌙 Вечер", "key": "evening_phrases"},
    ]
    total_jobs = 0
    for chat_id_str, user in users_data.items():
        try:
            tz = pytz.timezone(user.get("timezone", "Europe/Kiev"))
        except Exception as e:
            logger.warning(f"⚠️ Ошибка таймзоны для {chat_id_str}: {e}, используется Europe/Kiev")
            tz = pytz.timezone("Europe/Kiev")
        for job in schedules:
            if not job["file"].exists():
                logger.warning(f"⚠️ Файл {job['file']} не найден, пропуск")
                continue
            application.job_queue.run_daily(
                send_scheduled_message,
                time=time(hour=job["hour"], minute=job["minute"], tzinfo=tz),
                chat_id=int(chat_id_str),
                data={"cache_key": job["key"], "log": job["log"]},
                name=f"{job['log']}_{chat_id_str}"
            )
            total_jobs += 1
    application.job_queue.run_daily(check_demo_reminders, time=time(hour=10, minute=0, tzinfo=pytz.UTC))
    logger.info(f"📅 Запланировано {total_jobs} рассылок и 1 проверка напоминаний")

    if not await safe_send(application, ADMIN_CHAT_ID, "✅ Бот запущен/перезапущен"):
        logger.warning(f"⚠️ Не удалось уведомить {ADMIN_CHAT_ID}")

async def safe_send(application: Application, chat_id: int, text: str, **kwargs) -> bool:
    """Безопасная отправка сообщения с обработкой ошибок."""
    try:
        await application.bot.send_message(chat_id, text, **kwargs)
        return True
    except Forbidden:
        logger.warning(f"⛔ Бот заблокирован {chat_id}")
        users_data = application.bot_data.get("users", {})
        if str(chat_id) in users_data:
            users_data[str(chat_id)]["active"] = False
            save_users(users_data)
        return False
    except BadRequest as e:
        msg = str(e).lower()
        if "chat not found" in msg or "user not found" in msg:
            logger.warning(f"❌ Чат {chat_id} не найден")
        else:
            logger.warning(f"⚠️ BadRequest для {chat_id}: {e}")
        return False
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await safe_send(application, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"⚠️ Ошибка отправки {chat_id}: {e}")
        return False

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /start."""
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name or "друг"
    users_data = context.bot_data.get("users", {})
    user = users_data.get(str(chat_id))

    is_admin = chat_id == ADMIN_CHAT_ID or (user and user.get("is_admin", False))
    is_special = chat_id == SPECIAL_USER_ID
    is_new = not user or is_special
    logger.info(f"📥 /start от {name} ({chat_id}), is_admin: {is_admin}")

    should_welcome = True
    if is_new:
        expiration = None if is_admin else (datetime.now(pytz.UTC) + timedelta(days=3)).isoformat()
        users_data[str(chat_id)] = {
            "name": name, "timezone": "Europe/Kiev", "demo_expiration": expiration,
            "active": True, "is_admin": is_admin, "last_welcome": datetime.now(pytz.UTC).isoformat(),
            "demo_count": 0 if is_admin or is_special else 1, "next_demo_available": None,
            "last_challenge_date": None, "challenge_accepted": None, "last_rhythm_date": None,
            "current_challenge": None
        }
        logger.info(f"➕ Новый пользователь: {name} ({chat_id})")
        if not is_admin and not is_special:
            await safe_send(context.application, ADMIN_CHAT_ID, f"👤 Новый: {name} (ID: {chat_id})")
    else:
        users_data[str(chat_id)]["active"] = True
        for key in ["last_challenge_date", "challenge_accepted", "last_rhythm_date", "current_challenge"]:
            if key not in users_data[str(chat_id)]:
                users_data[str(chat_id)][key] = None
        logger.info(f"🔄 Пользователь {name} ({chat_id}) вернулся")
        if user.get("last_welcome"):
            last_welcome = datetime.fromisoformat(user["last_welcome"]).replace(tzinfo=pytz.UTC)
            if datetime.now(pytz.UTC) - last_welcome < timedelta(minutes=10):
                should_welcome = False

    if not is_admin and not is_special and is_demo_expired(users_data, chat_id):
        demo_count = users_data[str(chat_id)].get("demo_count", 1)
        next_demo = users_data[str(chat_id)].get("next_demo_available")
        if demo_count >= 2:
            if not next_demo:
                users_data[str(chat_id)]["next_demo_available"] = (datetime.now(pytz.UTC) + timedelta(days=1)).isoformat()
                await update.message.reply_text(
                    "⏳ Второй демо-период истёк. Доступ через 24 часа.", reply_markup=EXPIRED_DEMO_MARKUP
                )
                save_users(users_data)
                return
            next_time = datetime.fromisoformat(next_demo).replace(tzinfo=pytz.UTC)
            if datetime.now(pytz.UTC) < next_time:
                time_left = next_time - datetime.now(pytz.UTC)
                hours, minutes = int(time_left.total_seconds() // 3600), int((time_left.total_seconds() % 3600) // 60)
                await update.message.reply_text(
                    f"⏳ Доступ через {hours} ч {minutes} мин.", reply_markup=EXPIRED_DEMO_MARKUP
                )
                return
            users_data[str(chat_id)]["active"] = False
            save_users(users_data)
            await update.message.reply_text(
                "❌ Два демо-периода исчерпаны. Свяжитесь с админом.", reply_markup=EXPIRED_DEMO_MARKUP
            )
            return
        if next_demo:
            next_time = datetime.fromisoformat(next_demo).replace(tzinfo=pytz.UTC)
            if datetime.now(pytz.UTC) < next_time:
                time_left = next_time - datetime.now(pytz.UTC)
                hours, minutes = int(time_left.total_seconds() // 3600), int((time_left.total_seconds() % 3600) // 60)
                await update.message.reply_text(
                    f"⏳ Доступ через {hours} ч {minutes} мин.", reply_markup=EXPIRED_DEMO_MARKUP
                )
                return
        users_data[str(chat_id)]["demo_expiration"] = (datetime.now(pytz.UTC) + timedelta(days=3)).isoformat()
        users_data[str(chat_id)]["demo_count"] = 2
        users_data[str(chat_id)]["next_demo_available"] = None
        users_data[str(chat_id)]["active"] = True
        logger.info(f"🔄 Второй демо-период для {chat_id}")

    if chat_id == ADMIN_CHAT_ID:
        users_data[str(chat_id)]["is_admin"] = True
        users_data[str(chat_id)]["demo_count"] = 0
        users_data[str(chat_id)]["next_demo_available"] = None

    save_users(users_data)
    context.bot_data["users"] = users_data

    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    if should_welcome:
        demo_count = users_data[str(chat_id)].get("demo_count", 1)
        demo_exp = users_data[str(chat_id)].get("demo_expiration")
        user_tz = get_user_timezone(users_data, chat_id)
        exp_date = "бессрочно" if is_admin else datetime.fromisoformat(demo_exp).astimezone(user_tz).strftime("%d.%m.%Y %H:%M")
        text = (
            f"Добрый день, {name}! Я рада снова приветствовать тебя и продолжать мотивировать тебя в движении к твоим целям.\n"
            f"Демо-период — 3 дня (до {exp_date}). Что будет происходить, ты уже знаешь )"
        ) if demo_count == 2 and not is_special else (
            f"Привет, {name}! Я — Фотиния, твой помощник по привычкам и мотивации.\n"
            f"Твой доступ к демо-версии бота активен до: {exp_date}.\n\n"
            "Ты будешь получать мотивационные сообщения утром, днём и вечером.\n"
            "А это меню всегда перед тобой. Выбирай любое действие 👇"
        )
        await update.message.reply_text(text, reply_markup=keyboard)
        logger.info(f"📤 Приветствие отправлено для {chat_id}")
        users_data[str(chat_id)]["last_welcome"] = datetime.now(pytz.UTC).isoformat()
        save_users(users_data)
    else:
        await update.message.reply_text("Меню на месте 👇", reply_markup=keyboard)

async def handle_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /pay."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 /pay от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    await update.message.reply_text("💳 Оплата пока не реализована. Скоро!", reply_markup=keyboard)

async def handle_motivation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка мотивации пользователя."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос мотивации от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP

    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.", reply_markup=keyboard)
        return

    motivations = context.bot_data.get("motivations", [])
    if not motivations:
        await update.message.reply_text("⚠️ Мотивации отсутствуют.", reply_markup=keyboard)
        return

    user_name = update.effective_user.first_name or "друг"
    phrase = safe_format(random.choice(motivations), name=user_name)
    await update.message.reply_text(f"💡 <b>{phrase}</b>", parse_mode="HTML", reply_markup=keyboard)
    logger.info(f"💬 Мотивация отправлена для {chat_id}: {phrase}")

async def handle_rhythm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ритма дня с дневным лимитом."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос ритма от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP

    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.", reply_markup=keyboard)
        return

    user = users_data.get(str(chat_id), {})
    user_tz = get_user_timezone(users_data, chat_id)
    current_date = datetime.now(user_tz).date().isoformat()
    if user.get("last_rhythm_date") == current_date:
        await update.message.reply_text("⏳ Ритм уже получен сегодня.", reply_markup=keyboard)
        logger.info(f"⏳ Ритм для {chat_id} уже выдан")
        return

    rhythms = context.bot_data.get("rhythm", [])
    if not rhythms:
        await update.message.reply_text("⚠️ Ритмы отсутствуют.", reply_markup=keyboard)
        logger.warning(f"⚠️ Нет ритмов для {chat_id}")
        return

    user_name = update.effective_user.first_name or "друг"
    rhythm = safe_format(random.choice(rhythms), name=user_name)
    await update.message.reply_text(f"🎶 <b>{rhythm}</b>", parse_mode="HTML", reply_markup=keyboard)
    logger.info(f"🎶 Ритм отправлен для {chat_id}: {rhythm}")

    users_data[str(chat_id)]["last_rhythm_date"] = current_date
    save_users(users_data)

async def handle_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка челленджа с инлайн-ответами."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос челленджа от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP

    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.", reply_markup=keyboard)
        return

    user = users_data.get(str(chat_id), {})
    user_tz = get_user_timezone(users_data, chat_id)
    current_date = datetime.now(user_tz).date().isoformat()
    if user.get("last_challenge_date") == current_date:
        if user.get("challenge_accepted") is True:
            await update.message.reply_text("⏳ Челлендж уже выполнен.", reply_markup=keyboard)
            logger.info(f"⏳ Челлендж для {chat_id} использован")
            return
        if user.get("challenge_accepted") is False:
            await update.message.reply_text("🔥 Примите текущий челлендж!", reply_markup=keyboard)
            logger.info(f"🔥 Челлендж для {chat_id} ожидает принятия")
            return

    challenges = context.bot_data.get("challenges", [])
    if not challenges:
        await update.message.reply_text("⚠️ Челленджи отсутствуют.", reply_markup=keyboard)
        logger.warning(f"⚠️ Нет челленджей для {chat_id}")
        return

    user_name = update.effective_user.first_name or "друг"
    challenge = safe_format(random.choice(challenges), name=user_name)
    logger.info(f"🔥 Челлендж для {chat_id}: {challenge}")

    callback_id = make_callback_challenge(challenge)
    users_data[str(chat_id)]["current_challenge"] = challenge
    save_users(users_data)

    inline_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Принять", callback_data=f"accept:{callback_id}"),
                                           InlineKeyboardButton("🎲 Новый", callback_data="new")]])

    try:
        await update.message.reply_text(f"🔥 <b>{challenge}</b>", parse_mode="HTML", reply_markup=inline_keyboard)
        await update.message.reply_text("📲 Меню доступно 👇", reply_markup=keyboard)
        logger.info(f"📤 Челлендж отправлен для {chat_id}")
    except BadRequest as e:
        logger.error(f"❌ Ошибка челленджа для {chat_id}: {e}")
        await safe_send(context.application, ADMIN_CHAT_ID, f"⚠️ Ошибка: {e} для {chat_id}")
        await update.message.reply_text("⚠️ Ошибка отправки. Попробуйте позже.", reply_markup=keyboard)

    users_data[str(chat_id)]["last_challenge_date"] = current_date
    users_data[str(chat_id)]["challenge_accepted"] = False
    save_users(users_data)

async def handle_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка правил вселенной."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос правил от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP

    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.", reply_markup=keyboard)
        return

    rules = context.bot_data.get("rules", [])
    if not rules:
        rules = load_json(RULES_FILE)
        context.bot_data["rules"] = rules
        logger.info(f"🔄 Правила загружены: {len(rules)} элементов")

    if not rules:
        await update.message.reply_text("⚠️ Правила отсутствуют.", reply_markup=keyboard)
        return

    user_name = update.effective_user.first_name or "друг"
    rule = safe_format(random.choice(rules), name=user_name)
    await update.message.reply_text(f"📜 <b>{rule}</b>", parse_mode="HTML", reply_markup=keyboard)
    logger.info(f"📜 Правило отправлено для {chat_id}: {rule}")

async def handle_extend_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка продления демо-доступа."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос продления демо от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else EXPIRED_DEMO_MARKUP
    await update.message.reply_text("💳 Свяжитесь с админом для продления.", reply_markup=keyboard)

async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка неизвестных текстовых сообщений."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Неизвестный текст от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    await update.message.reply_text("❓ Используйте кнопки.", reply_markup=keyboard)

async def show_users_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показ файла users.json (только для админа)."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос users.json от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    if not is_admin:
        await update.message.reply_text("❌ Доступ только для админа.", reply_markup=keyboard)
        return
    try:
        if not USERS_FILE.exists():
            await update.message.reply_text("📂 Файл users.json не создан.", reply_markup=keyboard)
            return
        await update.message.reply_document(document=open(USERS_FILE, "rb"))
        await update.message.reply_text("📂 Файл users.json отправлен.", reply_markup=keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки: {e}", reply_markup=keyboard)

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображение статистики пользователей (только для админа)."""
    chat_id = update.effective_chat.id
    logger.info(f"📥 Запрос статистики от {chat_id}")
    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    if not is_admin:
        await update.message.reply_text("❌ Доступ только для админа.", reply_markup=keyboard)
        return
    users = {k: v for k, v in load_users().items() if int(k) != SPECIAL_USER_ID}
    total = len(users)
    active = sum(1 for u in users.values() if u.get("active", False))
    active_first = sum(1 for u in users.values() if u.get("active", False) and u.get("demo_count", 1) == 1)
    active_repeat = sum(1 for u in users.values() if u.get("active", False) and u.get("demo_count", 1) == 2)
    inactive = total - active
    inactive_expired = sum(1 for k, u in users.items() if not u.get("active", False) and is_demo_expired(users, int(k)))
    inactive_blocked = inactive - inactive_expired
    await update.message.reply_text(
        f"👥 Всего: {total}\n"
        f"✅ Активных: {active}\n"
        f"   Из них:\n"
        f"   - Первый вход: {active_first}\n"
        f"   - Повторный вход: {active_repeat}\n"
        f"❌ Неактивных: {inactive}\n"
        f"   Из них:\n"
        f"   - Закончился демо-период: {inactive_expired}\n"
        f"   - Заблокировали и вышли: {inactive_blocked}",
        reply_markup=keyboard
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка инлайн-кнопок."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    logger.info(f"📥 Callback от {chat_id}: {query.data}")

    users_data = context.bot_data.get("users", {})
    is_admin = chat_id == ADMIN_CHAT_ID or users_data.get(str(chat_id), {}).get("is_admin", False)
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP

    if query.data.startswith("accept:"):
        callback_id = query.data.split(":", 1)[1]
        current = users_data.get(str(chat_id), {}).get("current_challenge", "Челлендж не найден")
        users_data[str(chat_id)]["challenge_accepted"] = True
        save_users(users_data)
        try:
            await query.edit_message_text(f"💪 Челлендж принят:\n🔥 <b>{current}</b>", parse_mode="HTML")
            await query.message.reply_text("📲 Меню доступно 👇", reply_markup=keyboard)
        except BadRequest as e:
            logger.error(f"❌ Ошибка принятия для {chat_id}: {e}")
            await safe_send(context.application, ADMIN_CHAT_ID, f"⚠️ Ошибка: {e} для {chat_id}")
            await query.message.reply_text("⚠️ Ошибка принятия.", reply_markup=keyboard)
        return

    elif query.data == "new":
        user = users_data.get(str(chat_id), {})
        if user.get("challenge_accepted") is True:
            await query.edit_message_text("⏳ Челлендж уже выполнен.")
            await query.message.reply_text("📲 Меню доступно 👇", reply_markup=keyboard)
            return
        challenges = context.bot_data.get("challenges", [])
        if not challenges:
            await query.edit_message_text("⚠️ Челленджи отсутствуют.")
            await query.message.reply_text("📲 Меню доступно 👇", reply_markup=keyboard)
            return
        user_name = query.from_user.first_name or "друг"
        new_challenge = safe_format(random.choice(challenges), name=user_name)
        callback_id = make_callback_challenge(new_challenge)
        users_data[str(chat_id)]["current_challenge"] = new_challenge
        save_users(users_data)

        inline_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Принять", callback_data=f"accept:{callback_id}"),
                                               InlineKeyboardButton("🎲 Новый", callback_data="new")]])
        try:
            await query.edit_message_text(f"🔥 <b>{new_challenge}</b>", parse_mode="HTML", reply_markup=inline_keyboard)
            await query.message.reply_text("📲 Меню доступно 👇", reply_markup=keyboard)
        except BadRequest as e:
            logger.error(f"❌ Ошибка нового челленджа для {chat_id}: {e}")
            await safe_send(context.application, ADMIN_CHAT_ID, f"⚠️ Ошибка: {e} для {chat_id}")
            await query.message.reply_text("⚠️ Ошибка отправки.", reply_markup=keyboard)
        users_data[str(chat_id)]["last_challenge_date"] = datetime.now(get_user_timezone(users_data, chat_id)).date().isoformat()
        users_data[str(chat_id)]["challenge_accepted"] = False
        save_users(users_data)

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка запланированных сообщений."""
    job = context.job
    chat_id = job.chat_id
    cache_key = job.data["cache_key"]
    log = job.data["log"]
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_demo_expired(users_data, chat_id) or is_grace_period_expired(users_data, chat_id):
        logger.info(f"⏩ Пропуск {log} для {chat_id}")
        return
    phrases = context.bot_data.get(cache_key, [])
    if not phrases:
        logger.warning(f"⚠️ Пустой список {cache_key} для {chat_id}")
        return
    name = users_data.get(str(chat_id), {}).get("name", "друг")
    if await safe_send(context.application, chat_id, safe_format(random.choice(phrases), name=name)):
        logger.info(f"✅ {log} для {chat_id}")
    else:
        logger.warning(f"⚠️ Ошибка {log} для {chat_id}")

async def check_demo_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка напоминаний о демо-периоде."""
    users_data = context.bot_data.get("users", {})
    now = datetime.now(pytz.UTC)
    for chat_id_str, user in users_data.items():
        if int(chat_id_str) == SPECIAL_USER_ID:
            continue
        if user.get("demo_expiration"):
            try:
                chat_id = int(chat_id_str)
                demo_end = datetime.fromisoformat(user["demo_expiration"]).replace(tzinfo=pytz.UTC)
                if timedelta(days=0) < demo_end - now <= timedelta(days=1):
                    await safe_send(context.application, chat_id, "⏰ Демо заканчивается через 24 часа.")
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Ошибка проверки для {chat_id_str}: {e}")

async def reload_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перезагрузка всех данных из файлов."""
    context.bot_data["users"] = load_users()
    for key, file in [
        ("challenges", CHALLENGES_FILE),
        ("rules", RULES_FILE),
        ("motivations", MOTIVATIONS_FILE),
        ("rhythm", RITM_FILE),
        ("morning_phrases", MORNING_FILE),
        ("goals", GOALS_FILE),
        ("day_phrases", DAY_FILE),
        ("evening_phrases", EVENING_FILE)
    ]:
        context.bot_data[key] = load_json(file)
    await update.message.reply_text("🔄 Данные перезагружены.")

# Блок: Настройка FastAPI и бота
from fastapi import FastAPI
from contextlib import asynccontextmanager

async def setup_bot() -> Application:
    """Инициализация Telegram-бота."""
    logger.info("🔧 Настройка Telegram-бота...")
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("pay", handle_pay))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_MOTIVATE}$"), handle_motivation))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_RHYTHM}$"), handle_rhythm))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_CHALLENGE}$"), handle_challenge))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_RULES}$"), handle_rules))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_EXTEND_DEMO}$"), handle_extend_demo))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_SHOW_USERS}$"), show_users_file))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_STATS}$"), user_stats))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_text))

    logger.info("✅ Обработчики добавлены")
    return application

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения."""
    logger.info("🚀 Инициализация...")
    app.state.ptb_app = await setup_bot()
    logger.info("🤖 Бот готов")
    yield
    logger.info("🛑 Остановка...")
    await app.state.ptb_app.shutdown()
    await app.state.ptb_app.stop()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook/{token}")
async def process_update(request: Request, token: str) -> Dict[str, bool]:
    """Обработка вебхука."""
    if token != BOT_TOKEN.split(':')[0]:
        logger.error(f"❌ Неверный токен: {token}")
        return {"ok": False}
    app = request.app.state.ptb_app
    update_data = await request.json()
    update = Update.de_json(update_data, app.bot)
    await app.process_update(update)
    return {"ok": True}

@app.get("/health")
async def health_check() -> dict:
    """Проверка состояния."""
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
