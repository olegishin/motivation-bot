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

# ---------------- Загрузка .env ----------------
from dotenv import load_dotenv
load_dotenv("token_id.env")  # <- здесь указываешь свой файл .env

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
# Для локального запуска можно использовать python-dotenv и .env файл
# from dotenv import load_dotenv
# load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))

if not BOT_TOKEN or not OWNER_CHAT_ID:
    raise ValueError("❌ BOT_TOKEN или ADMIN_CHAT_ID не заданы в переменных окружения")

# ---------------- Логирование ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Кнопки и клавиатуры ----------------
BTN_MOTIVATE = "💪 Мотивируй меня"
BTN_RANDOM_GOAL = "🎯 Случайная цель"
BTN_CHALLENGE = "⚔️ Челлендж дня"
BTN_RULES = "📜 Правила Вселенной"

BTN_SHOW_USERS = "📂 Смотреть users.json"
BTN_STATS = "📊 Статистика пользователей"

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
        return [] if 'phrases' in str(filepath) or 'goals' in str(filepath) or 'challenges' in str(filepath) or 'laws' in str(filepath) else {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка декодирования JSON в {filepath}: {e}")
        return [] if 'phrases' in str(filepath) or 'goals' in str(filepath) or 'challenges' in str(filepath) or 'laws' in str(filepath) else {}
    except Exception as e:
        logger.error(f"❌ Не удалось прочитать файл {filepath}: {e}")
        return [] if 'phrases' in str(filepath) or 'goals' in str(filepath) or 'challenges' in str(filepath) or 'laws' in str(filepath) else {}

def load_users() -> dict:
    return load_json(USERS_FILE) or {}

def save_users(users_data: dict) -> None:
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=DATA_DIR) as tmp:
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
    if demo_exp is None:
        return False
    try:
        expiration = datetime.fromisoformat(demo_exp)
        user_tz = get_user_timezone(users_data, chat_id)
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
        users_data = app.bot_data.get("users", {})
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
        delay = e.retry_after
        logger.warning(f"⏳ Превышен лимит Telegram, ждём {delay} сек...")
        await asyncio.sleep(delay)
        return await safe_send(app, chat_id, text, **kwargs) # Повторная попытка
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

    is_admin = (chat_id_int == OWNER_CHAT_ID) or (user_record and user_record.get("is_admin", False))

    is_new_user = not user_record
    if is_new_user:
        tz = ZoneInfo("Europe/Kyiv")
        expiration = (datetime.now(tz) + timedelta(days=3)).isoformat() if chat_id_int != OWNER_CHAT_ID else None
        users_data[chat_id_str] = {
            "name": name,
            "timezone": str(tz),
            "demo_expiration": expiration,
            "active": True,
            "is_admin": is_admin
        }
        logger.info(f"➕ Создан новый пользователь: {name} ({chat_id_int})")
    else:
        users_data[chat_id_str]["active"] = True
        logger.info(f"🔄 Пользователь {name} ({chat_id_int}) вернулся")

    if chat_id_int != OWNER_CHAT_ID:
        if is_demo_expired(users_data, chat_id_int):
            if not user_record or not user_record.get("grace_period_end") or is_grace_period_expired(users_data, chat_id_int):
                users_data[chat_id_str]["active"] = False
                users_data[chat_id_str]["grace_period_end"] = (datetime.now(get_user_timezone(users_data, chat_id_int)) + timedelta(days=4)).isoformat()
                save_users(users_data)
                context.bot_data["users"] = users_data
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Да, хочу!", callback_data="extend_demo")]])
                await update.message.reply_text("❌ Демо-период закончился. Спасибо за тестирование! Хотите продлить доступ и получить полную поддержку?", reply_markup=keyboard)
                return

    save_users(users_data)
    context.bot_data["users"] = users_data

    if is_new_user and chat_id_int != OWNER_CHAT_ID:
        await safe_send(context.application, OWNER_CHAT_ID, f"👤 Новый пользователь: {name} (ID: {chat_id_int})")

    keyboard = OWNER_MARKUP if is_admin else MAIN_MARKUP
    
    # 💡 ИСПРАВЛЕНИЕ №2: Проверка на None перед форматированием даты
    demo_exp = users_data[chat_id_str].get("demo_expiration")
    expiration_date = datetime.fromisoformat(demo_exp).strftime("%d.%m.%Y %H:%M") if demo_exp else "бессрочно"
    
    text = (
        f"Привет, {name}! Я — Фотиния, твой помощник по привычкам и мотивации.\n"
        f"Твой доступ активен до: {expiration_date}.\n\n"
        "Ты будешь получать мотивационные сообщения утром, днём и вечером.\n"
        "А это меню всегда перед тобой. Выбирай любое действие 👇"
    )
    await update.message.reply_text(text, reply_markup=keyboard)

# ... (остальные хэндлеры без изменений, они выглядят хорошо)
async def handle_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Оплата пока не реализована. Скоро!")

async def handle_motivation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.")
        return

    phrases = load_json(PHRASES_FILE)
    if not phrases:
        await update.message.reply_text("⚠️ Список мотиваций пуст.")
        return

    user_name = update.effective_user.first_name
    phrase = random.choice(phrases).format(name=user_name)
    await update.message.reply_text(f"💬 {phrase}", parse_mode="HTML")


async def handle_random_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.")
        return

    goals = load_json(GOALS_FILE)
    if not goals:
        await update.message.reply_text("⚠️ Список целей пуст.")
        return

    user_name = update.effective_user.first_name
    goal = random.choice(goals).format(name=user_name)
    await update.message.reply_text(f"🎯 <b>{goal}</b>", parse_mode="HTML")


# ---------------- Хэндлер Челленджа ----------------
async def handle_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})

    # Проверка доступа
    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.")
        return

    # Загрузка списка челленджей
    challenges = load_json(CHALLENGES_FILE)
    if not challenges:
        await update.message.reply_text("⚠️ Список челленджей пуст.")
        return

    user_name = update.effective_user.first_name
    challenge = random.choice(challenges).format(name=user_name)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"accept_challenge:{challenge}"),
            InlineKeyboardButton("🎲 Новый", callback_data="new_challenge")
        ]
    ])

    await update.message.reply_text(
        f"🔥 <b>{challenge}</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ---------------- Обработка callback'ов ----------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Продление демо
    if query.data == "extend_demo":
        await query.edit_message_text(
            "💳 Для продления доступа, пожалуйста, свяжитесь с администратором (пока что)."
        )
        return

    # Принятие челленджа
    if query.data.startswith("accept_challenge:"):
        challenge_text = query.data.split(":", 1)[1]
        await query.edit_message_text(
            f"💪 Ты принял челлендж:\n\n🔥 <b>{challenge_text}</b>",
            parse_mode="HTML"
        )

    # Новый челлендж
    elif query.data == "new_challenge":
        challenges = load_json(CHALLENGES_FILE)
        if not challenges:
            await query.edit_message_text("⚠️ Список челленджей пуст.")
            return

        user_name = query.from_user.first_name
        new_challenge = random.choice(challenges).format(name=user_name)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept_challenge:{new_challenge}"),
                InlineKeyboardButton("🎲 Новый", callback_data="new_challenge")
            ]
        ])
        await query.edit_message_text(
            f"🔥 <b>{new_challenge}</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )


async def handle_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data = context.bot_data.get("users", {})
    if not users_data.get(str(chat_id), {}).get("active", True) or is_grace_period_expired(users_data, chat_id):
        await update.message.reply_text("❌ Доступ ограничен.")
        return

    rules = load_json(RULES_FILE)
    if not rules:
        await update.message.reply_text("⚠️ Список правил пуст.")
        return

    user_name = update.effective_user.first_name
    rule = random.choice(rules).format(name=user_name)
    await update.message.reply_text(f"📜 <b>{rule}</b>", parse_mode="HTML")


async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Неизвестная команда. Пожалуйста, используй кнопки.")


async def show_users_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID: return
    try:
        if not USERS_FILE.exists():
            await update.message.reply_text("Файл users.json еще не создан.")
            return
        await update.message.reply_document(document=open(USERS_FILE, "rb"))
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке файла: {e}")

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID: return
    users = load_users()
    total = len(users)
    active = sum(1 for u in users.values() if u.get("active"))
    await update.message.reply_text(f"👥 Всего: {total}\n✅ Активных: {active}\n❌ Неактивных: {total - active}")

# ... (и так далее для всех хэндлеров)

# ---------------- Планировщик ----------------
async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    filename = job.data["filename"]
    log_message = job.data["log_message"]

    users_data = context.bot_data.get("users", {})
    user_info = users_data.get(str(chat_id), {})

    if not user_info.get("active") or is_demo_expired(users_data, chat_id) or is_grace_period_expired(users_data, chat_id):
        logger.info(f"⏩ Пропуск рассылки '{log_message}' для неактивного пользователя {chat_id}")
        return

    phrases = load_json(BASE_DIR / filename)
    if not phrases:
        logger.warning(f"⚠️ Файл {filename} пуст, рассылка для {chat_id} отменена.")
        return

    name = user_info.get("name", "друг")
    phrase = random.choice(phrases).format(name=name)

    if await safe_send(context.application, chat_id, phrase):
        logger.info(f"✅ {log_message} для {chat_id}")
    else:
        logger.warning(f"⚠️ Не удалось отправить {log_message} для {chat_id}")

async def check_demo_reminders(context: ContextTypes.DEFAULT_TYPE):
    users_data = context.bot_data.get("users", {})
    utc_now = datetime.now(ZoneInfo("UTC"))
    for chat_id_str, user in users_data.items():
        if user.get("demo_expiration"):
            try:
                chat_id = int(chat_id_str)
                demo_end = datetime.fromisoformat(user["demo_expiration"])
                time_left = demo_end - utc_now
                if timedelta(days=0) < time_left <= timedelta(days=1):
                    await safe_send(context.application, chat_id, "⏰ Напоминание: ваш тестовый доступ к боту закончится через 24 часа.")
            except (ValueError, TypeError):
                continue


# ---------------- Main / запуск ----------------
from pathlib import Path
from datetime import time
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

async def post_init(app: Application):
    logger.info("📦 Инициализация post_init...")

    # Загружаем пользователей
    users_data = load_users()
    app.bot_data["users"] = users_data
    logger.info(f"👥 Загружено пользователей: {len(users_data)}")

    # Очищаем старые задачи, чтобы не было дублей
    for job in app.job_queue.jobs():
        job.schedule_removal()
    logger.info("🧹 Старые задачи планировщика очищены.")

    # Расписание рассылок
    schedules = [
        {"hour": 8, "minute": 0, "filename": "fotinia_morning_phrases.json", "log": "🌅 Утро"},
        {"hour": 12, "minute": 0, "filename": "fotinia_phrases.json", "log": "🎲 Случайная"},
        {"hour": 15, "minute": 0, "filename": "fotinia_day_phrases.json", "log": "☀️ День"},
        {"hour": 18, "minute": 0, "filename": "fotinia_evening_phrases.json", "log": "🌙 Вечер"},
    ]

    total_jobs = 0
    for chat_id_str, user in users_data.items():
        try:
            tz = ZoneInfo(user.get("timezone", "Europe/Kyiv"))
        except Exception as e:
            logger.warning(f"⚠️ Ошибка с таймзоной пользователя {chat_id_str}: {e}, используем Europe/Kyiv")
            tz = ZoneInfo("Europe/Kyiv")

        for job_info in schedules:
            json_path = DATA_DIR / job_info["filename"]
            if not json_path.exists():
                logger.warning(f"⚠️ Файл {json_path} не найден, рассылка пропущена")
                continue

            try:
                app.job_queue.run_daily(
                    send_scheduled_message,
                    time=time(hour=job_info["hour"], minute=job_info["minute"], tzinfo=tz),
                    chat_id=int(chat_id_str),
                    data={"filename": str(json_path), "log_message": job_info["log"]},
                    name=f"{job_info['log']}_{chat_id_str}"
                )
                total_jobs += 1
            except Exception as e:
                logger.error(f"❌ Ошибка при добавлении job для {chat_id_str}: {e}")

    # Ежедневная проверка демо-настроек
    try:
        app.job_queue.run_daily(
            check_demo_reminders,
            time=time(hour=10, minute=0, tzinfo=ZoneInfo("UTC"))
        )
    except Exception as e:
        logger.error(f"❌ Не удалось добавить job check_demo_reminders: {e}")

    logger.info(f"📅 Запланировано {total_jobs} рассылок и 1 ежедневная проверка напоминаний.")

    # Уведомление владельца
    try:
        await app.bot.send_message(chat_id=OWNER_CHAT_ID, text="✅ Бот успешно запущен/перезапущен!")
    except Exception as e:
        logger.error(f"❌ Не удалось уведомить владельца: {e}")


#-------------------Запуск------------------------
def register_handlers(app):
    # Команды
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("pay", handle_pay))

    # Кнопки
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_MOTIVATE)}$"), handle_motivation))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_RANDOM_GOAL)}$"), handle_random_goal))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_CHALLENGE)}$"), handle_challenge))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_RULES)}$"), handle_rules))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_SHOW_USERS)}$"), show_users_file))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_STATS)}$"), user_stats))

    # Колбэки и неизвестный текст
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_text))


def run_polling():
    logger.warning("Запуск в режиме polling (локально)")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    register_handlers(app)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


async def run_webhook():
    logger.info("Запуск в режиме webhook (Fly.io)")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    register_handlers(app)

    APP_NAME = os.getenv("FLY_APP_NAME")
    PORT = int(os.getenv("PORT", 8443))
    webhook_url = f"https://{APP_NAME}.fly.dev/{BOT_TOKEN}"

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=webhook_url,
        allowed_updates=Update.ALL_TYPES
    )

# ---------------- Точка входа ----------------
if __name__ == "__main__":
    if os.getenv("FLY_APP_NAME"):
        asyncio.run(run_webhook())
    else:
        run_polling()