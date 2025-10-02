import os
import json
import random
import logging
import asyncio
import tempfile
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.error import Forbidden, BadRequest, RetryAfter
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------------- Пути к файлам ----------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)  # Создаём папку data, если нет

USERS_FILE = DATA_DIR / "users.json"
GOALS_FILE = DATA_DIR / "fotinia_goals.json"
MORNING_FILE = DATA_DIR / "fotinia_morning_phrases.json"
EVENING_FILE = DATA_DIR / "fotinia_evening_phrases.json"
DAY_FILE = DATA_DIR / "fotinia_day_phrases.json"
PHRASES_FILE = DATA_DIR / "fotinia_phrases.json"
CHALLENGES_FILE = DATA_DIR / "challenges.json"
RULES_FILE = DATA_DIR / "universe_laws.json"

# ---------------- Конфигурация ----------------
if "BOT_TOKEN" not in os.environ or "ADMIN_CHAT_ID" not in os.environ:
    raise ValueError("❌ BOT_TOKEN или ADMIN_CHAT_ID не заданы")
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])  # <- сюда вставляем свой Telegram ID

# ---------------- Логирование ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Кнопки и клавиатуры ----------------
BTN_MOTIVATE    = "💪 Мотивируй меня"
BTN_RANDOM_GOAL = "🎯 Случайная цель"
BTN_CHALLENGE   = "⚔️ Челлендж дня"
BTN_RULES       = "📜 Правила Вселенной"

BTN_SHOW_USERS  = "📂 Смотреть users.json"
BTN_STATS       = "📊 Статистика пользователей"

MAIN_KEYBOARD = [
    [BTN_MOTIVATE, BTN_RANDOM_GOAL],
    [BTN_CHALLENGE, BTN_RULES]
]

ADMIN_BUTTONS = [
    [BTN_SHOW_USERS, BTN_STATS]
]

# Клавиатура для обычных пользователей
MAIN_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

# Клавиатура для владельца и админов
OWNER_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD + ADMIN_BUTTONS, resize_keyboard=True)

# ---------------- Утилиты ----------------
def load_json(filepath: Path) -> list | dict:
    if not filepath.exists():
        logger.warning(f"⚠️ Файл {filepath} не найден.")
        return [] if filepath in [PHRASES_FILE, MORNING_FILE, EVENING_FILE, DAY_FILE, GOALS_FILE, CHALLENGES_FILE, RULES_FILE] else {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if filepath in [PHRASES_FILE, MORNING_FILE, EVENING_FILE, DAY_FILE, GOALS_FILE, CHALLENGES_FILE, RULES_FILE]:
                if isinstance(data, dict):
                    return list(data.values())
                return data if isinstance(data, list) else []
            return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка декодирования JSON в {filepath}: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Не удалось прочитать файл {filepath}: {e}")
        return []

def load_users() -> dict:
    return load_json(USERS_FILE) or {}

def save_users(users_data: dict) -> None:
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            json.dump(users_data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        shutil.move(tmp_path, USERS_FILE)
        logger.info(f"💾 Сохранено {len(users_data)} пользователей")
    except Exception as e:
        logger.error(f"❌ Не удалось сохранить {USERS_FILE}: {e}")

def get_user_timezone(users_data: dict, chat_id: int) -> ZoneInfo:
    tz_name = users_data.get(str(chat_id), {}).get("timezone", "Europe/Kyiv")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"⚠️ Таймзона '{tz_name}' неверна для {chat_id}, используется Europe/Kyiv")
        return ZoneInfo("Europe/Kyiv")

def get_user_name(users_data: dict, chat_id: int, default="друг") -> str:
    return users_data.get(str(chat_id), {}).get("name", default)

def is_demo_expired(users_data: dict, chat_id: int) -> bool:
    user = users_data.get(str(chat_id))
    if not user:
        return True
    demo_exp = user.get("demo_expiration")
    if demo_exp is None:  # Владелец или подписка — не expired
        return False
    try:
        expiration = datetime.fromisoformat(demo_exp)
        user_tz = get_user_timezone(users_data, chat_id)
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=user_tz)
        return datetime.now(user_tz) > expiration
    except Exception as e:
        logger.warning(f"Ошибка при проверке demo_expiration для {chat_id}: {e}")
        return True

def is_grace_period_expired(users_data: dict, chat_id: int) -> bool:
    user = users_data.get(str(chat_id))
    if not user or "grace_period_end" not in user:
        return False
    try:
        grace_end = datetime.fromisoformat(user["grace_period_end"])
        user_tz = get_user_timezone(users_data, chat_id)
        if grace_end.tzinfo is None:
            grace_end = grace_end.replace(tzinfo=user_tz)
        return datetime.now(user_tz) > grace_end
    except Exception as e:
        logger.warning(f"Ошибка при проверке grace_period_end для {chat_id}: {e}")
        return True

# ---------------- Безопасная отправка ----------------
async def safe_send(app, chat_id: int, text: str, **kwargs) -> bool:
    try:
        await app.bot.send_message(int(chat_id), text, **kwargs)
        return True
    except Forbidden:
        logger.warning(f"⛔ Бот заблокирован пользователем {chat_id}")
        return False
    except BadRequest as e:
        msg = str(e).lower()
        if "chat not found" in msg or "chat_not_found" in msg:
            logger.warning(f"❌ Чат {chat_id} не найден")
        else:
            logger.warning(f"⚠️ BadRequest для {chat_id}: {e}")
        return False
    except RetryAfter as e:
        delay = getattr(e, "retry_after", 5)
        logger.warning(f"⏳ Превышен лимит Telegram, ждём {delay} сек...")
        await asyncio.sleep(delay)
        try:
            await app.bot.send_message(int(chat_id), text, **kwargs)
            return True
        except RetryAfter:
            logger.error(f"❌ Повторная отправка в {chat_id} не удалась из-за лимита")
            return False
        except Exception as e2:
            logger.error(f"❌ Повторная отправка в {chat_id} не удалась: {e2}")
            return False
    except Exception as e:
        logger.error(f"⚠️ Ошибка отправки в {chat_id}: {e}")
        return False

# ---------------- Хэндлеры ----------------
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_int = update.effective_chat.id
    chat_id_str = str(chat_id_int)
    name = update.effective_user.first_name or "друг"

    users_data = context.bot_data.get("users", {})
    user_record = users_data.get(chat_id_str)

    logger.info(f"DEBUG start: chat_id={chat_id_int}, owner={OWNER_CHAT_ID}, user_record={user_record is not None}")

    # Проверка на админство
    is_admin = False
    if chat_id_int == OWNER_CHAT_ID:
        is_admin = True
        logger.info(f"DEBUG: OWNER detected, is_admin=True")
    elif user_record:
        is_admin = user_record.get("is_admin", False)
        logger.info(f"DEBUG: from record, is_admin={is_admin}")

    # Если пользователь новый — создаём запись
    is_new_user = False
    if not user_record:
        tz = ZoneInfo("Europe/Kyiv")
        expiration = (datetime.now(tz) + timedelta(days=3)).isoformat() if chat_id_int != OWNER_CHAT_ID else None
        users_data[chat_id_str] = {
            "name": name,
            "timezone": str(tz),
            "demo_expiration": expiration,
            "active": True,
            "is_admin": is_admin  # OWNER автоматически admin
        }
        is_new_user = True
        logger.info(f"DEBUG: New user created, is_new={is_new_user}, is_admin={is_admin}")
    else:
        users_data[chat_id_str]["active"] = True
        logger.info(f"DEBUG: Existing user, active=True")

    # Проверка демо и грайс-периода
    if chat_id_int != OWNER_CHAT_ID:
        if is_demo_expired(users_data, chat_id_int):
            if not user_record.get("grace_period_end"):
                users_data[chat_id_str]["active"] = False
                users_data[chat_id_str]["grace_period_end"] = (datetime.now(tz) + timedelta(days=4)).isoformat()
                logger.info(f"⏳ Демо для {chat_id_int} истекло, начат грайс-период до {users_data[chat_id_str]['grace_period_end']}")
                save_users(users_data)
                context.bot_data["users"] = users_data
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Да", callback_data="extend_demo"),
                                                 InlineKeyboardButton("Нет", callback_data="no_extend")]])
                await update.message.reply_text("❌ Демо-период закончился. Спасибо за тестирование! Хотите продолжить?", reply_markup=keyboard)
                return
            elif is_grace_period_expired(users_data, chat_id_int):
                users_data[chat_id_str]["active"] = False
                logger.info(f"⏳ Грайс-период для {chat_id_int} истек, меню скрыто")
                save_users(users_data)
                context.bot_data["users"] = users_data
                await update.message.reply_text("❌ Грайс-период закончился. Меню недоступно.")
                return

    save_users(users_data)
    context.bot_data["users"] = users_data
    logger.info(f"DEBUG: Saved users, len={len(users_data)}")

    # Отправляем уведомление владельцу о новом пользователе
    if is_new_user and chat_id_int != OWNER_CHAT_ID:
        tz = users_data[chat_id_str]["timezone"]
        expiration = users_data[chat_id_str]["demo_expiration"]
        await safe_send(context.application, OWNER_CHAT_ID, f"👤 Новый пользователь: {name} (ID: {chat_id_int}), Тайм-зона: {tz}, Срок: {expiration}")
        logger.info(f"DEBUG: Notification sent to owner")

    # Выбираем клавиатуру
    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    logger.info(f"DEBUG: Keyboard={ 'OWNER' if is_admin else 'MAIN' }")

    # Приветственное сообщение
    expiration_date = datetime.fromisoformat(users_data[chat_id_str]["demo_expiration"]).strftime("%d.%m.%Y %H:%M") if users_data[chat_id_str]["demo_expiration"] else "бессрочно"
    text = (
        f"Привет, {name}! Я — Фотиния, твой помощник по привычкам и мотивации.\n"
        f"Твой тестовый период: 3 дня до {expiration_date}.\n"
        "Ты будешь получать мотивационные сообщения утром, днём и вечером.\n"
        "А это меню всегда перед тобой. Выбирай любое действие 👇"
    )
    logger.info(f"👤 Пользователь {chat_id_int} стартовал. Admin={is_admin}, Новый={is_new_user}")
    await update.message.reply_text(text, reply_markup=keyboard)

async def handle_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заглушка для команды /pay"""
    await update.message.reply_text("💳 Оплата пока не реализована. Скоро!")

async def handle_motivation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен. Обратитесь к владельцу.")
        return
    try:
        phrases = load_json(PHRASES_FILE)
        if not phrases:
            await update.message.reply_text("⚠️ Список мотиваций пуст.")
            return
        phrase = random.choice(phrases)
        await update.message.reply_text(f"💬 Мотивация:\n<b>{phrase}</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка мотивации: {e}")
        await update.message.reply_text("⚠️ Не удалось загрузить мотивацию.")

async def handle_random_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен. Обратитесь к владельцу.")
        return
    try:
        goals = load_json(GOALS_FILE)
        if not goals:
            await update.message.reply_text("⚠️ Список целей пуст.")
            return
        goal = random.choice(goals)
        await update.message.reply_text(f"🎯 Случайная цель:\n<b>{goal}</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка цели: {e}")
        await update.message.reply_text("⚠️ Не удалось получить цель.")

async def handle_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен. Обратитесь к владельцу.")
        return
    try:
        challenges = load_json(CHALLENGES_FILE)
        if not challenges:
            await update.message.reply_text("⚠️ Список челленджей пуст.")
            return
        challenge = random.choice(challenges)
        await update.message.reply_text(f"🔥 Челлендж:\n<b>{challenge}</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка челленджа: {e}")
        await update.message.reply_text("⚠️ Не удалось загрузить челлендж.")

async def handle_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен. Обратитесь к владельцу.")
        return
    try:
        rules = load_json(RULES_FILE)
        if not rules:
            await update.message.reply_text("⚠️ Список правил пуст.")
            return
        rule = random.choice(rules)
        await update.message.reply_text(f"📜 Закон Вселенной:\n<b>{rule}</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка правил: {e}")
        await update.message.reply_text("⚠️ Не удалось загрузить правила.")

async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Я не понимаю этот текст. Попробуй выбрать кнопку.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    query = update.callback_query
    chat_id = query.from_user.id
    chat_id_str = str(chat_id)
    users_data = context.bot_data.get("users", {})
    user = users_data.get(chat_id_str)

    if query.data == "extend_demo":
        await query.message.edit_text("💳 Выберите тариф подписки:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1 месяц — 500 руб", callback_data="pay_1m"),
             InlineKeyboardButton("3 месяца — 1200 руб", callback_data="pay_3m")]
        ]))
    elif query.data == "no_extend":
        user["active"] = False
        user["grace_period_end"] = (datetime.now(ZoneInfo("UTC")) + timedelta(days=4)).isoformat()
        await query.message.edit_text("✅ Доступ к кнопкам сохраняется на 4 дня. Рассылка отключена.")
        save_users(users_data)
        context.bot_data["users"] = users_data
    elif query.data in ["pay_1m", "pay_3m"]:
        months = 1 if query.data == "pay_1m" else 3
        user["demo_expiration"] = None
        user["subscription_end"] = (datetime.now(ZoneInfo("UTC")) + timedelta(days=30 * months)).isoformat()
        user["active"] = True
        await query.message.edit_text(f"💳 Подписка на {months} мес. оформлена! (Заглушка, реализуйте платежи через Telegram Payments)")
        save_users(users_data)
        context.bot_data["users"] = users_data

async def show_users_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_data = context.bot_data.get("users", {})
    chat_id_str = str(update.effective_user.id)
    is_admin = users_data.get(chat_id_str, {}).get("is_admin", False)

    if update.effective_user.id != OWNER_CHAT_ID and not is_admin:
        return

    try:
        size = USERS_FILE.stat().st_size if USERS_FILE.exists() else 0
        if size > 4000:
            with open(USERS_FILE, "rb") as f:
                await update.message.reply_document(document=f)
            return
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = f.read()
        await update.message.reply_text(f"<code>{data}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при чтении файла: {e}")

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_data = context.bot_data.get("users", {})
    chat_id_str = str(update.effective_user.id)
    is_admin = users_data.get(chat_id_str, {}).get("is_admin", False)

    if update.effective_user.id != OWNER_CHAT_ID and not is_admin:
        return

    try:
        users = load_users()
        total = len(users)
        active = sum(1 for u in users.values() if u.get("active"))
        inactive = total - active
        await update.message.reply_text(
            f"👥 Всего: {total}\n👤 Активных: {active}\n😴 Неактивных: {inactive}"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при подсчёте: {e}")

async def handle_demo_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    chat_id_str = str(update.effective_chat.id)
    user = users.get(chat_id_str)
    if not user:
        await update.message.reply_text("Вы не зарегистрированы.")
        return
    await update.message.reply_text(f"Демо истекает: {user.get('demo_expiration', 'нет данных')}")

async def handle_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠 Debug-команда пока не реализована.")

# ---------------- Планировщик ----------------
async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.kwargs.get("chat_id") or (job.args[0] if job.args else None)
    data = job.kwargs.get("data", {})
    filename = data.get("filename")
    log_message = data.get("log_message", "Рассылка")

    if chat_id is None:
        logger.warning("Нет chat_id в задаче планировщика.")
        return

    if not filename:
        logger.warning(f"❌ Нет filename для рассылки в задаче {job}")
        return

    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_grace_period_expired(users_data, chat_id):
        logger.info(f"⏳ Доступ для {chat_id} ограничен, рассылка '{log_message}' отменена")
        return
    if is_demo_expired(users_data, chat_id):
        logger.info(f"⏳ Демо истекло для {chat_id}, рассылка '{log_message}' отменена")
        return

    file_path = BASE_DIR / filename
    if not file_path.exists():
        logger.warning(f"⚠️ Файл {file_path} не найден, рассылка пропущена")
        return

    phrases = load_json(file_path)
    if not phrases:
        logger.warning(f"⚠️ Фразы не загружены из {filename} для {chat_id}")
        return

    name = get_user_name(users_data, chat_id)
    phrase = random.choice(phrases)
    try:
        phrase = phrase.format(name=name)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка форматирования фразы для {chat_id}: {e}")
    success = await safe_send(context.application, chat_id, phrase)
    if success:
        logger.info(f"✅ {log_message} для {chat_id}")
    else:
        logger.warning(f"⚠️ Не удалось отправить {log_message} для {chat_id}")

async def check_demo_reminder(context: ContextTypes.DEFAULT_TYPE):
    users_data = context.bot_data.get("users", {})
    current_time = datetime.now(ZoneInfo("UTC"))
    for chat_id_str, user in users_data.items():
        chat_id = int(chat_id_str)
        if user.get("demo_expiration") and not is_demo_expired(users_data, chat_id):
            demo_end = datetime.fromisoformat(user["demo_expiration"])
            if (demo_end - current_time).days == 1:
                await safe_send(context.application, chat_id, "⏰ Завтра — последний день тестирования бота!")
            elif (demo_end - current_time).days == 2:
                await safe_send(context.application, chat_id, "⏰ Через 2 дня тестовый период закончится. Подумать о подписке?")
    save_users(users_data)
    context.bot_data["users"] = users_data

# ---------------- Broadcast для всех ----------------
async def send_broadcast(context: ContextTypes.DEFAULT_TYPE):
    users_data = context.bot_data.get("users", {})
    sent_count = 0
    for chat_id_str, user in users_data.items():
        chat_id = int(chat_id_str)
        if not user.get("active") or is_grace_period_expired(users_data, chat_id):
            continue
        logger.info(f"📢 Рассылка пользователю {chat_id}")
        if await safe_send(
            context.application,
            chat_id,
            "📢 Тестовая рассылка для всех пользователей"
        ):
            sent_count += 1
        await asyncio.sleep(0.05)  # Задержка для rate-limit
    logger.info(f"📢 Рассылка завершена: {sent_count} получателей")

# ---------------- Тестовые команды ----------------
async def handle_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая отправка мотивации одному пользователю (/test)"""
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active") or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен. Обратитесь к владельцу.")
        return
    if is_demo_expired(users_data, chat_id):
        await update.message.reply_text("❌ Демо истекло, тест отменён.")
        return
    
    filename = "fotinia_phrases.json"
    file_path = BASE_DIR / filename
    if not file_path.exists():
        await update.message.reply_text("⚠️ Файл фраз не найден.")
        return
    
    phrases = load_json(file_path)
    if not phrases:
        await update.message.reply_text("⚠️ Фразы не загружены.")
        return
    
    name = get_user_name(users_data, chat_id)
    phrase = random.choice(phrases)
    try:
        phrase = phrase.format(name=name)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка форматирования фразы для {chat_id}: {e}")
    
    success = await safe_send(context.application, chat_id, phrase)
    if success:
        await update.message.reply_text("✅ Тестовая мотивация отправлена!")
        logger.info(f"🧪 Тестовая рассылка вручную для {chat_id}")
    else:
        await update.message.reply_text("❌ Ошибка отправки теста.")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка тестового сообщения всем (/broadcast) — только для OWNER"""
    if update.effective_chat.id != OWNER_CHAT_ID:
        await update.message.reply_text("❌ Только владелец может рассылать всем.")
        return
    
    await update.message.reply_text("🚀 Запускаю тестовую рассылку всем...")
    await send_broadcast(context)
    await update.message.reply_text("✅ Рассылка завершена!")

# ---------------- Main / запуск ----------------
async def post_init(app: Application):
    logger.info("📦 Инициализация post_init...")

    # Отправка сообщения владельцу
    if not app.bot_data.get("post_init_done"):
        logger.info("📤 Пытаемся отправить сообщение владельцу при запуске...")
        try:
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text="✅ Бот успешно запущен и готов к работе")
            app.bot_data["post_init_done"] = True
            logger.info("📬 Сообщение владельцу успешно отправлено")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения владельцу: {e}")

    # Загрузка пользователей
    users_data = load_users()
    app.bot_data["users"] = users_data
    logger.info(f"👥 Загружено пользователей: {len(users_data)}")

    # Планирование рассылок и напоминаний
    total_jobs = 0
    for chat_id_str, user in users_data.items():
        chat_id = int(chat_id_str)
        tz = ZoneInfo(user.get("timezone", "Europe/Kyiv"))
        schedules = [
            {"hour": 7, "minute": 30, "filename": "fotinia_morning_phrases.json", "log": "🌅 Утренняя мотивация"},
            {"hour": 11, "minute": 0, "filename": "fotinia_phrases.json", "log": "🎲 Случайная мотивация"},
            {"hour": 14, "minute": 0, "filename": "fotinia_day_phrases.json", "log": "☀️ Дневная мотивация"},
            {"hour": 18, "minute": 0, "filename": "fotinia_evening_phrases.json", "log": "🌙 Вечерняя мотивация"},
        ]

        for job_info in schedules:
            file_path = BASE_DIR / job_info["filename"]
            if not file_path.exists():
                logger.warning(f"⚠️ Файл {file_path} не найден, рассылка пропущена")
                continue

            app.job_queue.run_daily(
                send_scheduled_message,
                time=time(hour=job_info["hour"], minute=job_info["minute"], tzinfo=tz),
                kwargs={"chat_id": chat_id, "data": {
                    "filename": job_info["filename"],
                    "log_message": job_info["log"]
                }}
            )
            total_jobs += 1

    # Планирование ежедневной проверки демо-напоминаний
    app.job_queue.run_daily(
        check_demo_reminder,
        time=time(hour=0, minute=0, tzinfo=ZoneInfo("UTC")),  # Полночь UTC
        data={}
    )

    logger.info(f"📅 Запланировано {total_jobs} ежедневных задач и 1 проверка демо")

if __name__ == "__main__":
    import os
    import asyncio

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    APP_NAME = os.getenv("FLY_APP_NAME")
    PORT = int(os.getenv("PORT", 8443))

    async def main():
        logger.info("🚀 Запуск Telegram-бота через webhook...")

        app = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .post_init(post_init)
            .build()
        )

        # ---------------- Хэндлеры команд и сообщений ----------------
        app.add_handler(CommandHandler("start", handle_start))
        app.add_handler(CommandHandler("pay", handle_pay))
        app.add_handler(CommandHandler("debug", handle_debug))
        app.add_handler(CommandHandler("demo_status", handle_demo_status))
        app.add_handler(CommandHandler("test", handle_test))
        app.add_handler(CommandHandler("broadcast", handle_broadcast))
        app.add_handler(CallbackQueryHandler(handle_callback))
        app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_MOTIVATE)}$"), handle_motivation))
        app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_RANDOM_GOAL)}$"), handle_random_goal))
        app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_CHALLENGE)}$"), handle_challenge))
        app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_RULES)}$"), handle_rules))
        app.add_handler(MessageHandler(filters.Regex(f"^{re.escape('📂 Смотреть users.json')}$"), show_users_file))
        app.add_handler(MessageHandler(filters.Regex(f"^{re.escape('📊 Статистика пользователей')}$"), user_stats))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_text))

        # ---------------- Настройка webhook ----------------
        logger.info("🌐 Удаляем старый webhook и сбрасываем pending updates...")
        await app.bot.delete_webhook(drop_pending_updates=True)

        webhook_url = f"https://{APP_NAME}.fly.dev/{BOT_TOKEN}"
        logger.info(f"🌐 Устанавливаем новый webhook: {webhook_url}")
        await app.bot.set_webhook(url=webhook_url)

        # ---------------- Запуск webhook-сервера ----------------
        logger.info(f"🟢 Webhook-сервер слушает на порту {PORT}")
        await app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=webhook_url
        )

    # Запуск напрямую без дополнительного event loop
    asyncio.run(main())