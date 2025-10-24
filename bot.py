#!/usr/bin/env python3
"""
🚀 FOTINIA BOT v8.9 (ADVANCED DEMO CYCLE)
✅ ФУНКЦИОНАЛ: Полная админка, /pay, сложная логика челленджей, локализация (RU/UA/EN).
✅ АРХИТЕКТУРА: FastAPI, JSON+Lock, 2 Job Schedulers, современная работа со временем.
🐞 ИСПРАВЛЕНИЕ: Новая демо-логика: 3+1+3 дня (обычные) и 1+1+1 день (тестеры).
                 Кнопки доступны всегда. Добавлены уведомления об окончании демо.
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
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Any, Dict
from contextlib import asynccontextmanager

# Webhook и FastAPI
from fastapi import FastAPI, Request

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
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
TESTER_USER_IDS = {290711961, 6104624108} 
DEFAULT_LANG = "ru" 
DEFAULT_TZ = ZoneInfo("Europe/Kiev")

# ✅ НОВЫЕ ПАРАМЕТРЫ ДЕМО-ЦИКЛА
REGULAR_DEMO_DAYS = 3
REGULAR_COOLDOWN_DAYS = 1
TESTER_DEMO_DAYS = 1
TESTER_COOLDOWN_DAYS = 1
RULES_PER_DAY_LIMIT = 3
MAX_DEMO_CYCLES = 2 # Сколько всего демо-периодов (1-й и 2-й)

logger.info("🤖 Bot starting...")
logger.info(f"🔑 ADMIN_CHAT_ID configured as: {ADMIN_CHAT_ID}")
logger.info(f"🧪 TESTER_USER_IDS configured as: {TESTER_USER_IDS}")

# --- 📍 ПУТИ К ФАЙЛАМ ---
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))

# --- 📄 НАЗВАНИЯ ФАЙЛОВ ---
USERS_FILE = DATA_DIR / "users.json"
FILE_MAPPING = {
    "rules": "universe_laws.json",
    "motivations": "fotinia_motivations.json", "ritm": "fotinia_ritm.json",
    "morning_phrases": "fotinia_morning_phrases.json", "goals": "fotinia_goals.json",
    "day_phrases": "fotinia_day_phrases.json", "evening_phrases": "fotinia_evening_phrases.json"
}

# --- 🌐 ЛОКАЛИЗАЦИЯ ---
COMMON_LANG_CHOOSE_FIRST = "Вітаю! Будь ласка, оберіть мову: 👇\n\nEnglish: Please select a language: 👇\n\nЗдравствуйте! Пожалуйста, выберите язык: 👇"

translations = {
    "ru": {
        "lang_choose_first": COMMON_LANG_CHOOSE_FIRST,
        "welcome": "🌟 Привет, {name}! Я Фотиния, твой бот-помощник по саморазвитию.\n\nЯ буду присылать тебе сообщения 4 раза в день, чтобы помочь держать фокус. У тебя есть ознакомительный период ({demo_days} дня), чтобы попробовать все функции. Начнем! 👇",
        "welcome_return": "🌟 С возвращением, {name}! Рад снова тебя видеть. Твой {status_text} доступ активен. Используй кнопки ниже 👇",
        "demo_expiring_soon_h": "🔒 {name}, ваш демо-доступ истекает менее чем через {hours} час(а). Не забудьте активировать подписку, чтобы не терять прогресс!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Ваш демо-доступ закончился.</b>\n\nДо возобновления демо-периода осталось **{hours} ч. {minutes} мин.**\n\nИли вы можете активировать Premium-доступ прямо сейчас, нажав кнопку 'Оплатить'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Ваш демо-доступ закончился.</b>\n\nВы можете активировать **еще один** пробный период ({demo_days} дня) или получить постоянный Premium-доступ.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Ваши пробные периоды закончились.</b>\n\nДля возобновления доступа, пожалуйста, активируйте Premium-подписку. 👇",
        "pay_info": "💳 Для получения полного доступа, пожалуйста, свяжитесь с администратором.",
        "pay_instructions": "Для активации, пожалуйста, переведите **1 грн** (тестовая сумма) на эту карту Monobank:\n\n`https://send.monobank.ua/2f4hvev7yR`\n\n**ВАЖНО:** После оплаты, пожалуйста, пришлите скриншот чека **в этот чат**. Админ увидит его и активирует ваш доступ вручную.",
        "pay_api_success_test": "✅ Симуляция API-оплаты прошла! Ваш 'Premium' доступ активирован. Нажмите /start.",
        "profile_title": "👤 <b>Ваш профиль:</b>",
        "profile_name": "📛 Имя",
        "profile_challenges_accepted": "⚔️ Принято челленджей",
        "profile_challenges_completed": "✅ Выполнено",
        "profile_challenge_streak": "🔥 Серия выполнений",
        "profile_status": "💰 Статус",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Демо",
        "list_empty": "⚠️ Список для '{title}' пуст.",
        "list_error_format": "⚠️ Ошибка форматирования текста для '{title}'. Отсутствует ключ: {e}",
        "list_error_index": "⚠️ Произошла ошибка при выборе элемента из списка '{title}'. Список может быть пуст.",
        "list_error_unexpected": "⚠️ Произошла непредвиденная ошибка при отправке '{title}'.",
        "list_error_data": "⚠️ Ошибка данных для '{title}'. Обратитесь к администратору.",
        "challenge_already_issued": "⏳ Вы уже приняли челлендж на сегодня.",
        "challenge_pending_acceptance": "🔥 У вас уже есть активный челлендж. Примите его или нажмите 'Новый' в сообщении выше.",
        "challenge_accepted_msg": "💪 <b>Челлендж принят:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Отлично! Челлендж выполнен!",
        "challenge_completed_edit_err": "⚠️ Не удалось отредактировать сообщение о выполнении.",
        "challenge_new_day": "⚔️ <b>Челлендж дня:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Ошибка при выборе челленджа. Список может быть пуст.",
        "challenge_button_error": "⚠️ Произошла ошибка при формировании кнопок челленджа.",
        "challenge_unexpected_error": "⚠️ Произошла непредвиденная ошибка при отправке челленджа.",
        "challenge_accept_error": "⚠️ Произошла ошибка при принятии челленджа. Попробуйте запросить челлендж заново.",
        "challenge_streak_3": "🔥🔥🔥 {name}, ты выполнил(а) 3 челленджа подряд! Невероятный результат! Продолжай в том же духе, ты способен(на) на многое!",
        "unknown_command": "❓ Неизвестная команда. Пожалуйста, используйте кнопки.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "Файл users.json ещё не создан или пуст.",
        "reload_confirm": "✅ Кэш и задачи планировщика обновлены!",
        "start_required": "Похоже, мы ещё не знакомы. Пожалуйста, нажмите /start, чтобы начать.",
        "admin_new_user": "🎉 Новый пользователь: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Показать статистику",
        "admin_bot_started": "🤖 Бот успешно запущен (v8.9 Advanced Demo Cycle)",
        "admin_bot_stopping": "⏳ Бот останавливается...",
        "lang_choose": "Выберите язык: 👇",
        "lang_chosen": "✅ Язык установлен на Русский.",
        "btn_motivate": "💪 Мотивируй меня", "btn_rhythm": "🎵 Ритм дня",
        "btn_challenge": "⚔️ Челлендж дня", "btn_rules": "📜 Правила Вселенной",
        "btn_profile": "👤 Профиль",
        "btn_show_users": "📂 Смотреть users.json", "btn_stats": "📊 Статистика",
        "btn_reload_data": "🔄 Обновить",
        "btn_pay_real": "💳 Активировать подписку",
        "btn_pay_api_test": "💳 Оплатить (API Тест)",
        "btn_new_demo": "🔄 Активировать демо",
        "btn_challenge_accept": "✅ Принять", "btn_challenge_new": "🎲 Новый",
        "btn_challenge_complete": "✅ Выполнено",
        "title_motivation": "💪", "title_rhythm": "🎶 Ритм дня:", "title_rules": "📜 Правила Вселенной",
        "title_rules_daily": "📜 <b>{title} ({count}/{limit}):</b>",
        "rules_limit_reached": "На сегодня это все законы. Новые ты узнаешь завтра! 🌙",
        "profile_status_total": "Всего",
        "profile_status_active": "Активных",
        "profile_status_first_time": "Первый раз",
        "profile_status_repeat": "Повторно",
        "profile_status_inactive": "Неактивных",
        "profile_status_demo_expired": "Закончилось демо",
        "profile_status_blocked": "Заблокировали",
    },
    "ua": {
        "lang_choose_first": COMMON_LANG_CHOOSE_FIRST,
        "welcome": "🌟 Привіт, {name}! Я бот Фотінія, твій особистий помічник із саморозвитку.\n\nЯ буду надсилати тобі повідомлення 4 рази на день, щоб допомогти тримати фокус. У тебе є ознайомчий період ({demo_days} дні), щоб спробувати всі функції. Почнемо! 👇",
        "welcome_return": "🌟 З поверненням, {name}! Радий знову тебе бачити. Твій {status_text} доступ активний. Використовуй кнопки нижче 👇",
        "demo_expiring_soon_h": "🔒 {name}, ваш демо-доступ закінчується менш ніж за {hours} год. Не забудьте активувати підписку, щоб не втрачати прогрес!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Ваш демо-доступ закінчився.</b>\n\nМожливість активувати новий демо-період з'явиться через **{hours} год {minutes} хв.**\n\nАбо ви можете активувати Premium-доступ прямо зараз, натиснувши кнопку 'Оплатити'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Ваш демо-доступ закінчився.</b>\n\nВи можете активувати **ще один** пробний період ({demo_days} дні) або отримати постійний Premium-доступ.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Ваші пробні періоди закінчилися.</b>\n\nДля відновлення доступу, будь ласка, активуйте Premium-підписку. 👇",
        "pay_info": "💳 Для отримання повного доступу, будь ласка, зв'яжіться з адміністратором.",
        "pay_instructions": "Для активації, будь ласка, перекажіть **1 грн** (тестова сума) на цю картку Monobank:\n\n`https://send.monobank.ua/2f4hvev7yR`\n\n**ВАЖЛИВО:** Після оплати, будь ласка, надішліть скріншот чека **в цей чат**. Адмін побачить його та активує ваш доступ вручну.",
        "pay_api_success_test": "✅ Симуляція API-оплати пройшла! Ваш 'Premium' доступ активовано. Натисніть /start.",
        "profile_title": "👤 <b>Ваш профіль:</b>",
        "profile_name": "📛 Ім'я",
        "profile_challenges_accepted": "⚔️ Прийнято челенджів",
        "profile_challenges_completed": "✅ Виконано",
        "profile_challenge_streak": "🔥 Серія виконань",
        "profile_status": "💰 Статус",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Демо",
        "list_empty": "⚠️ Список для '{title}' порожній.",
        "list_error_format": "⚠️ Помилка форматування тексту для '{title}'. Відсутній ключ: {e}",
        "list_error_index": "⚠️ Сталася помилка під час вибору елемента зі списку '{title}'. Список може бути порожнім.",
        "list_error_unexpected": "⚠️ Сталася непередбачена помилка під час надсилання '{title}'.",
        "list_error_data": "⚠️ Помилка даних для '{title}'. Зверніться до адміністратора.",
        "challenge_already_issued": "⏳ Ви вже отримали челендж на сьогодні.",
        "challenge_pending_acceptance": "🔥 У вас вже є активний челендж. Прийміть його або натисніть 'Новий' у повідомленні вище.",
        "challenge_accepted_msg": "💪 <b>Челендж прийнято:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Чудово! Челендж виконано!",
        "challenge_completed_edit_err": "⚠️ Не вдалося відредагувати повідомлення про виконання.",
        "challenge_new_day": "⚔️ <b>Челендж дня:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Помилка під час вибору челенджу. Список може бути порожнім.",
        "challenge_button_error": "⚠️ Сталася помилка під час формування кнопок челенджу.",
        "challenge_unexpected_error": "⚠️ Сталася непередбачена помилка під час надсилання челенджу.",
        "challenge_accept_error": "⚠️ Сталася помилка під час прийняття челенджу. Спробуйте запросити челендж знову.",
        "challenge_streak_3": "🔥🔥🔥 {name}, ти виконав(ла) 3 челенджі поспіль! Неймовірний результат! Продовжуй так само, ти здатен(на) на багато що!",
        "unknown_command": "❓ Невідома команда. Будь ласка, використовуйте кнопки.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "Файл users.json ще не створений або порожній.",
        "reload_confirm": "✅ Кеш та завдання планувальника оновлено!",
        "start_required": "Схоже, ми ще не знайомі. Будь ласка, натисніть /start, щоб почати.",
        "admin_new_user": "🎉 Новий користувач: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Показати статистику",
        "admin_bot_started": "🤖 Бот успішно запущений (v8.9 Advanced Demo Cycle)",
        "admin_bot_stopping": "⏳ Бот зупиняється...",
        "lang_choose": "Оберіть мову: 👇",
        "lang_chosen": "✅ Мову встановлено на Українську.",
        "btn_motivate": "💪 Мотивуй мене", "btn_rhythm": "🎵 Ритм дня",
        "btn_challenge": "⚔️ Челендж дня", "btn_rules": "📜 Правила Всесвіту",
        "btn_profile": "👤 Профіль",
        "btn_show_users": "📂 Дивитися users.json", "btn_stats": "📊 Статистика",
        "btn_reload_data": "🔄 Оновити",
        "btn_pay_real": "💳 Активувати підписку",
        "btn_pay_api_test": "💳 Оплатити (API Тест)",
        "btn_new_demo": "🔄 Активувати демо",
        "btn_challenge_accept": "✅ Прийняти", "btn_challenge_new": "🎲 Новий",
        "btn_challenge_complete": "✅ Виконано",
        "title_motivation": "💪", "title_rhythm": "🎶 Ритм дня:", "title_rules": "📜 Правила Всесвіту",
        "title_rules_daily": "📜 <b>{title} ({count}/{limit}):</b>",
        "rules_limit_reached": "На сьогодні це всі закони. Нові ти дізнаєшся завтра! 🌙",
        "profile_status_total": "Всього",
        "profile_status_active": "Активних",
        "profile_status_first_time": "Перший раз",
        "profile_status_repeat": "Повторно",
        "profile_status_inactive": "Неактивних",
        "profile_status_demo_expired": "Закінчилося демо",
        "profile_status_blocked": "Заблокували",
    },
    "en": {
        "lang_choose_first": COMMON_LANG_CHOOSE_FIRST,
        "welcome": "🌟 Hello, {name}! I am Fotinia Bot, your personal self-development assistant.\n\nI will send you messages 4 times a day to help you stay focused. You have a trial period ({demo_days} days) to try all features. Let's start! 👇",
        "welcome_return": "🌟 Welcome back, {name}! Glad to see you again. Your {status_text} access is active. Use the buttons below 👇",
        "demo_expiring_soon_h": "🔒 {name}, your demo access expires in less than {hours} hour(s). Don't forget to activate your subscription to keep your progress!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Your demo access has expired.</b>\n\nYou can reactivate a new demo period in **{hours}h {minutes}m**.\n\nOr you can activate Premium access right now by pressing 'Pay'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Your demo access has expired.</b>\n\nYou can activate **one more** trial period ({demo_days} days) or get permanent Premium access.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Your trial periods have ended.</b>\n\nTo resume access, please activate your Premium subscription. 👇",
        "pay_info": "💳 For full access, please contact the administrator.",
        "pay_instructions": "To activate, please transfer **1 UAH** (test amount) to this Monobank card:\n\n`https://send.monobank.ua/2f4hvev7yR`\n\n**IMPORTANT:** After payment, please send a screenshot of the receipt **to this chat**. The admin will see it and activate your access manually.",
        "pay_api_success_test": "✅ API Simulation successful! Your 'Premium' access is activated. Press /start.",
        "profile_title": "👤 <b>Your Profile:</b>",
        "profile_name": "📛 Name",
        "profile_challenges_accepted": "⚔️ Challenges Accepted",
        "profile_challenges_completed": "✅ Completed",
        "profile_challenge_streak": "🔥 Completion Streak",
        "profile_status": "💰 Status",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Demo",
        "list_empty": "⚠️ The list for '{title}' is empty.",
        "list_error_format": "⚠️ Error formatting text for '{title}'. Missing key: {e}",
        "list_error_index": "⚠️ An error occurred while selecting an item from the list '{title}'. The list may be empty.",
        "list_error_unexpected": "⚠️ An unexpected error occurred while sending '{title}'.",
        "list_error_data": "⚠️ Data error for '{title}'. Please contact the administrator.",
        "challenge_already_issued": "⏳ You have already received a challenge for today.",
        "challenge_pending_acceptance": "🔥 You already have an active challenge. Accept it or press 'New' in the message above.",
        "challenge_accepted_msg": "💪 <b>Challenge accepted:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Excellent! Challenge completed!",
        "challenge_completed_edit_err": "⚠️ Failed to edit the completion message.",
        "challenge_new_day": "⚔️ <b>Challenge of the day:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Error choosing challenge. The list may be empty.",
        "challenge_button_error": "⚠️ An error occurred while generating challenge buttons.",
        "challenge_unexpected_error": "⚠️ An unexpected error occurred while sending the challenge.",
        "challenge_accept_error": "⚠️ An error occurred while accepting the challenge. Please request a new challenge.",
        "challenge_streak_3": "🔥🔥🔥 {name}, you have completed 3 challenges in a row! Incredible result! Keep it up, you are capable of great things!",
        "unknown_command": "❓ Unknown command. Please use the buttons.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "The users.json file has not been created or is empty.",
        "reload_confirm": "✅ Cache and scheduler tasks have been updated!",
        "start_required": "It seems we haven't met. Please press /start to begin.",
        "admin_new_user": "🎉 New user: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Show Statistics",
        "admin_bot_started": "🤖 Bot successfully launched (v8.9 Advanced Demo Cycle)",
        "admin_bot_stopping": "⏳ Bot is stopping...",
        "lang_choose": "Select language: 👇",
        "lang_chosen": "✅ Language set to English.",
        "btn_motivate": "💪 Motivate me", "btn_rhythm": "🎵 Rhythm of the Day",
        "btn_challenge": "⚔️ Challenge of the Day", "btn_rules": "📜 Rules of the Universe",
        "btn_profile": "👤 Profile",
        "btn_show_users": "📂 View users.json", "btn_stats": "📊 Statistics",
        "btn_reload_data": "🔄 Reload",
        "btn_pay_real": "💳 Activate Subscription",
        "btn_pay_api_test": "💳 Pay (API Test)",
        "btn_new_demo": "🔄 Activate Demo",
        "btn_challenge_accept": "✅ Accept", "btn_challenge_new": "🎲 New",
        "btn_challenge_complete": "✅ Done",
        "title_motivation": "💪", "title_rhythm": "🎶 Rhythm of the Day:", "title_rules": "📜 Rules of the Universe",
        "title_rules_daily": "📜 <b>{title} ({count}/{limit}):</b>",
        "rules_limit_reached": "That's all the laws for today. You will learn new ones tomorrow! 🌙",
        "profile_status_total": "Total",
        "profile_status_active": "Active",
        "profile_status_first_time": "First time",
        "profile_status_repeat": "Repeat",
        "profile_status_inactive": "Inactive",
        "profile_status_demo_expired": "Demo expired",
        "profile_status_blocked": "Blocked",
    }
}


# --- ⌨️ КНОПКИ (з урахуванням локалізації) ---
def get_btn_text(key: str, lang: str = DEFAULT_LANG) -> str:
    return translations.get(lang, translations[DEFAULT_LANG]).get(f"btn_{key}", f"BTN_{key.upper()}")

BTN_MOTIVATE = "btn_motivate"
BTN_RHYTHM = "btn_rhythm"
BTN_CHALLENGE = "btn_challenge"
BTN_RULES = "btn_rules"
BTN_PROFILE = "btn_profile"
BTN_SHOW_USERS = "btn_show_users"
BTN_STATS = "btn_stats"
BTN_RELOAD_DATA = "btn_reload_data"
BTN_PAY_REAL = "btn_pay_real"
BTN_PAY_API_TEST = "btn_pay_api_test" 
BTN_NEW_DEMO = "btn_new_demo"

def get_main_keyboard(lang: str = DEFAULT_LANG) -> ReplyKeyboardMarkup:
    layout = [
        [get_btn_text('motivate', lang), get_btn_text('rhythm', lang)],
        [get_btn_text('challenge', lang), get_btn_text('rules', lang)],
        [get_btn_text('profile', lang)]
    ]
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

def get_admin_keyboard(lang: str = DEFAULT_LANG) -> ReplyKeyboardMarkup:
    layout = [
        [get_btn_text('motivate', lang), get_btn_text('rhythm', lang)],
        [get_btn_text('challenge', lang), get_btn_text('rules', lang)],
        [get_btn_text('show_users', lang), get_btn_text('stats', lang)]
    ]
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

# ✅ ИЗМЕНЕНО: Клавиатура для выбора оплаты/демо
def get_payment_keyboard(lang: str = DEFAULT_LANG, is_test_user: bool = False, show_new_demo: bool = False) -> ReplyKeyboardMarkup:
    buttons = []
    if is_test_user:
        buttons.append(get_btn_text('pay_api_test', lang))
    else:
        buttons.append(get_btn_text('pay_real', lang))
    
    if show_new_demo:
        buttons.append(get_btn_text('new_demo', lang))
        
    return ReplyKeyboardMarkup([buttons], resize_keyboard=True)

def get_reply_keyboard_for_user(chat_id: int, lang: str, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    """Определяет, какую клавиатуру показать пользователю."""
    if is_admin(chat_id):
        return get_admin_keyboard(lang)
    
    if user_data.get("is_paid"):
        return get_main_keyboard(lang)
    
    is_test_user = chat_id in TESTER_USER_IDS

    if is_demo_expired(user_data):
        demo_count = user_data.get("demo_count", 1)
        
        # Проверяем, прошел ли кулдаун
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            exp_dt = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
            cooldown_days = TESTER_COOLDOWN_DAYS if is_test_user else REGULAR_COOLDOWN_DAYS
            next_demo_dt = exp_dt + timedelta(days=cooldown_days)
            
            if now_utc >= next_demo_dt:
                # Кулдаун прошел. Показываем выбор, если это был 1-й демо
                show_demo_button = (demo_count < MAX_DEMO_CYCLES)
                return get_payment_keyboard(lang, is_test_user, show_new_demo=show_demo_button)
            else:
                # Еще в кулдауне, показываем только кнопку оплаты
                return get_payment_keyboard(lang, is_test_user, show_new_demo=False)
        except Exception:
             # Ошибка парсинга даты, на всякий случай даем выбор
             return get_payment_keyboard(lang, is_test_user, show_new_demo=(demo_count < MAX_DEMO_CYCLES))
    
    # Если мы здесь, значит, демо активно
    # (Тестеры с активным демо видят обычную клавиатуру)
    return get_main_keyboard(lang)


USERS_FILE_LOCK = asyncio.Lock()

# ----------------- РАБОТА С ДАННЫМИ -----------------
def load_json_data(filepath: Path, default_factory=list) -> Any:
    if not filepath.exists():
        logger.warning(f"Файл {filepath.name} не найден. Используется значение по умолчанию.")
        return default_factory()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            logger.debug(f"Reading {filepath.name}: Content starts with '{content[:100]}...' (Total size: {len(content)})")
            if not content or content.strip() in ('[]', '{}'):
                logger.warning(f"Файл {filepath.name} пуст или содержит только '[]'/'{{}}'. Используется значение по умолчанию.")
                return default_factory()
            return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Ошибка чтения или парсинга {filepath.name}: {e}. Используется значение по умолчанию.")
        return default_factory()

def load_all_challenges_into_cache(app: Application):
    """Загружает челленджи из всех файлов challenges*.json в папке данных."""
    challenges = {} 
    challenge_files = list(DATA_DIR.glob("challenges*.json"))
    logger.info(f"Найдено {len(challenge_files)} файлов с челленджами: {[p.name for p in challenge_files]}")
    
    for p in challenge_files:
        data = load_json_data(p, default_factory={}) 
        if not isinstance(data, dict):
            logger.error(f" -> Ошибка: Файл {p.name} содержит не словарь, а {type(data).__name__}. Пропущено.")
            continue
            
        for lang, items in data.items():
            if lang not in challenges:
                challenges[lang] = []
            if isinstance(items, list):
                challenges[lang].extend(items)
                logger.info(f" -> Загружено {len(items)} челленджей для языка '{lang}' из {p.name}")
            else:
                logger.warning(f" -> Ошибка: 'items' для языка '{lang}' в файле {p.name} - не список.")
                
    app.bot_data["challenges"] = challenges
    total_count = sum(len(v) for v in challenges.values())
    logger.info(f"✅ Всего загружено челленджей: {total_count} (в {len(challenges)} языках)")


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
    logger.info(f"Синхронизация файлов в persistent-директории '{DATA_DIR}'...")
    DATA_DIR.mkdir(exist_ok=True)

    source_data_dir = Path(__file__).parent / "data_initial"
    if not source_data_dir.exists():
        logger.warning(f"⚠️ Папка 'data_initial' не найдена. Невозможно скопировать исходные данные.")
        all_expected_files = list(FILE_MAPPING.values()) + ["challenges.json", USERS_FILE.name]
        for filename in all_expected_files:
             filepath = DATA_DIR / filename
             if not filepath.exists():
                  default_content = {} if filename == USERS_FILE.name else []
                  with open(filepath, "w", encoding="utf-8") as f: json.dump(default_content, f)
                  logger.warning(f"  -> ⚠️ Создан пустой файл '{filename}'.")
        return

    copied_count = 0
    for filename in os.listdir(source_data_dir):
        source_path = source_data_dir / filename
        dest_path = DATA_DIR / filename

        if not source_path.is_file(): continue

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                source_content = f.read().strip()
                logger.debug(f"Source {filename} content: {source_content[:50]}{'...' if len(source_content) > 50 else ''} (Size: {source_path.stat().st_size} bytes)")
        except Exception as e:
            logger.error(f"Не удалось прочитать исходный файл {source_path}: {e}")
            continue

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

                if dest_size < 10 and filename != USERS_FILE.name :
                    should_copy = True
                    reason = "пустой"
                elif source_mtime > dest_mtime and filename != USERS_FILE.name:
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

    if not USERS_FILE.exists():
        with open(USERS_FILE, "w", encoding="utf-8") as f: json.dump({}, f)
        logger.warning(f"  -> ⚠️ Файл '{USERS_FILE.name}' не найден, создан пустой.")

    logger.info(f"✅ Синхронизация завершена. Скопировано/обновлено файлов: {copied_count}.")


# ----------------- УТИЛИТЫ -----------------
def get_user_lang(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    user_data = context.application.bot_data.get("users", {}).get(str(chat_id), {})
    return user_data.get("language", DEFAULT_LANG)

def get_text(key: str, context: ContextTypes.DEFAULT_TYPE | None = None, chat_id: int | None = None, lang: str | None = None, **kwargs) -> str:
    effective_lang = lang
    if not effective_lang and context and chat_id:
        effective_lang = get_user_lang(context, chat_id)
    if not effective_lang:
        effective_lang = DEFAULT_LANG
    lang_dict = translations.get(effective_lang, translations[DEFAULT_LANG])
    text = lang_dict.get(key, key)
    try:
        if 'name' not in kwargs and '{name}' in text:
             kwargs['name'] = ''
        if key == 'admin_new_user' and 'user_id' not in kwargs:
            kwargs['user_id'] = 'N/A'
        return text.format(**kwargs)
    except KeyError as e:
        logger.error(f"Missing key '{e}' during formatting text for key '{key}' in lang '{effective_lang}'")
        return text

def strip_html_tags(text: str) -> str: return re.sub('<[^<]+?>', '', text)
def is_admin(chat_id: int) -> bool: return chat_id == ADMIN_CHAT_ID

def is_demo_expired(user_data: dict) -> bool:
    if not user_data: return True
    if user_data.get("is_paid"): return False
    
    demo_exp = user_data.get("demo_expiration")
    if not demo_exp: return False
    try:
        expiration_dt = datetime.fromisoformat(demo_exp).replace(tzinfo=ZoneInfo("UTC"))
        return datetime.now(ZoneInfo("UTC")) > expiration_dt
    except (ValueError, TypeError): return True

async def safe_send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs):
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, **kwargs)
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
    """Отправляет 4 рассылки в день (утром, цели, днем, вечером)."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    users_data = context.application.bot_data.get("users", {})
    schedules = [(8, "morning_phrases"), (12, "goals"), (15, "day_phrases"), (18, "evening_phrases")]
    tasks = []
    
    logger.debug(f"Running centralized_broadcast_job at {now_utc.isoformat()}")
    
    for hour, key in schedules:
        data = context.application.bot_data.get(key, {})
        phrases_by_lang = data if isinstance(data, dict) else {DEFAULT_LANG: data if isinstance(data, list) else []}

        for chat_id_str, user_data in users_data.items():
            # Рассылки уходят только активным (не заблокировал) И (платным ИЛИ демо не истек)
            if not user_data.get("active") or (not user_data.get("is_paid") and is_demo_expired(user_data)):
                 if is_demo_expired(user_data):
                      logger.debug(f"Skipping broadcast for {chat_id_str}, demo expired.")
                 continue
            
            try:
                user_tz = ZoneInfo(user_data.get("timezone", DEFAULT_TZ.key))
                user_lang = user_data.get("language", DEFAULT_LANG)
                
                lang_specific_phrases = phrases_by_lang.get(user_lang, phrases_by_lang.get(DEFAULT_LANG, []))
                
                if not lang_specific_phrases:
                     if hour == 8: # Логируем только 1 раз в день, чтобы не спамить
                        logger.warning(f"Нет фраз для языка '{user_lang}' в рассылке '{key}'.")
                     continue

                if now_utc.astimezone(user_tz).hour == hour:
                    logger.debug(f"Sending '{key}' to user {chat_id_str} at their local {hour}:00")
                    phrase = random.choice(lang_specific_phrases).format(name=user_data.get("name", "друг"))
                    tasks.append(safe_send(context, int(chat_id_str), phrase))
            except Exception as e: logger.error(f"Ошибка в планировщике (broadcast) для {chat_id_str}: {e}")
    
    if tasks:
        results = await asyncio.gather(*tasks)
        if (sent_count := sum(1 for res in results if res)) > 0:
            logger.info(f"📢 Рассылка (broadcast) завершена. Отправлено {sent_count} сообщений.")

# ✅ НОВЫЙ ПЛАНИРОВЩИК: Уведомления об окончании демо
async def check_demo_expiry_job(context: ContextTypes.DEFAULT_TYPE):
    """Раз в час проверяет, не истекает ли у кого-то демо, и шлет уведомление."""
    logger.debug("Running check_demo_expiry_job...")
    now_utc = datetime.now(ZoneInfo("UTC"))
    users_data = context.application.bot_data.get("users", {})
    users_to_save = False
    
    for chat_id_str, user_data in users_data.items():
        chat_id = int(chat_id_str)
        # Пропускаем, если уже оплатил, неактивен, или уже отправляли
        if user_data.get("is_paid") or not user_data.get("active") or user_data.get("sent_expiry_warning"):
            continue
            
        demo_exp_str = user_data.get("demo_expiration")
        if not demo_exp_str:
            continue
            
        try:
            exp_dt = datetime.fromisoformat(demo_exp_str).replace(tzinfo=ZoneInfo("UTC"))
            time_left = exp_dt - now_utc
            
            is_test_user = (chat_id in TESTER_USER_IDS)
            warning_hours = 2 if is_test_user else 24
            
            if timedelta(hours=0) < time_left <= timedelta(hours=warning_hours):
                logger.info(f"Demo expiring soon for user {chat_id} (Tester: {is_test_user}). Sending warning.")
                lang = user_data.get("language", DEFAULT_LANG)
                await safe_send(context, chat_id, get_text('demo_expiring_soon_h', lang=lang, name=user_data.get("name", "друг"), hours=warning_hours))
                
                user_data["sent_expiry_warning"] = True
                users_to_save = True
                
        except Exception as e:
            logger.error(f"Ошибка в планировщике (expiry check) для {chat_id}: {e}")

    if users_to_save:
        await save_users(context, users_data)
    logger.debug("check_demo_expiry_job finished.")


# ----------------- 🖥️ ХЕНДЛЕРЫ -----------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id_str = str(chat_id)
    users_data = context.application.bot_data.get("users", {})
    user_entry = users_data.get(user_id_str)
    now_utc = datetime.now(ZoneInfo("UTC"))

    is_test_user = (chat_id in TESTER_USER_IDS)
    is_new_user = (user_entry is None)
    
    if is_new_user:
        logger.info(f"Поток нового пользователя для {chat_id}")
        keyboard = [
            [InlineKeyboardButton("Українська 🇺🇦", callback_data="set_lang_ua_new")],
            [InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en_new")],
            [InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru_new")]
        ]
        await safe_send(context, chat_id, get_text('lang_choose_first', lang=DEFAULT_LANG), reply_markup=InlineKeyboardMarkup(keyboard))
    
    else:
        user_lang = user_entry.get("language", DEFAULT_LANG)
        user_name = user_entry.get("name", "друг")
        
        if is_demo_expired(user_entry) and not user_entry.get("is_paid"):
            logger.info(f"Демо истек для вернувшегося пользователя {chat_id}.")
            
            demo_count = user_entry.get("demo_count", 1)
            cooldown_days = TESTER_COOLDOWN_DAYS if is_test_user else REGULAR_COOLDOWN_DAYS
            demo_days = TESTER_DEMO_DAYS if is_test_user else DEMO_DAYS
            
            try:
                demo_exp_date = datetime.fromisoformat(user_entry.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
                next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
                
                if now_utc < next_demo_dt:
                    # ЕЩЕ В КУЛДАУНЕ
                    time_left = next_demo_dt - now_utc
                    hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                    minutes_left, _ = divmod(remainder, 60)
                    logger.info(f"Демо для {chat_id} еще на паузе. Осталось: {hours_left}ч {minutes_left}м")
                    await safe_send(context, chat_id, 
                                    get_text('demo_expired_cooldown', lang=user_lang, name=user_name, hours=hours_left, minutes=minutes_left),
                                    reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=False))
                
                else:
                    # КУЛДАУН ПРОШЕЛ
                    if demo_count < MAX_DEMO_CYCLES:
                        # Показываем выбор: "Оплатить" или "Новое демо"
                        logger.info(f"Кулдаун для {chat_id} прошел. Предлагаем 2-е демо (счетчик: {demo_count}).")
                        await safe_send(context, chat_id, 
                                        get_text('demo_expired_choice', lang=user_lang, name=user_name, demo_days=demo_days),
                                        reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=True))
                    else:
                        # Демо-циклы закончились
                        logger.info(f"Демо-циклы ({demo_count}) для {chat_id} закончились. Только оплата.")
                        await safe_send(context, chat_id, 
                                        get_text('demo_expired_final', lang=user_lang, name=user_name),
                                        reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=False))

            except (ValueError, TypeError):
                logger.error(f"Ошибка парсинга demo_expiration для {chat_id}. Показываем опцию оплаты.")
                await safe_send(context, chat_id, 
                                get_text('demo_expired_choice', lang=user_lang, name=user_name, demo_days=demo_days), 
                                reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=(demo_count < MAX_DEMO_CYCLES)))
        
        else:
            # Демо активно или есть Premium
            status_text_key = 'status_premium' if user_entry.get("is_paid") else 'status_demo'
            status_text = get_text(status_text_key, lang=user_lang)
            logger.debug(f"Вернувшийся пользователь {chat_id} с активным статусом: {status_text}.")
            markup = get_reply_keyboard_for_user(chat_id, user_lang, user_entry)
            await safe_send(context, chat_id, get_text('welcome_return', lang=user_lang, name=user_name, status_text=status_text), reply_markup=markup)


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context, update.effective_chat.id)
    await update.message.reply_text(get_text('pay_info', lang=lang))

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context, update.effective_chat.id)
    keyboard = [
        [InlineKeyboardButton("Українська 🇺🇦", callback_data="set_lang_ua")],
        [InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en")],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru")]
    ]
    await update.message.reply_text(get_text('lang_choose', lang=lang), reply_markup=InlineKeyboardMarkup(keyboard))

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    user_data = context.application.bot_data["users"].get(str(chat_id), {})
    
    completed_challenges = sum(1 for ch in user_data.get("challenges", []) if ch.get("completed"))
    
    status_key = 'status_premium' if user_data.get('is_paid') else 'status_demo'
    status_text = get_text(status_key, lang=lang)
    
    text = (f"{get_text('profile_title', lang=lang)}\n\n"
            f"{get_text('profile_name', lang=lang)}: {user_data.get('name', 'Неизвестно')}\n"
            f"{get_text('profile_challenges_accepted', lang=lang)}: {len(user_data.get('challenges', []))}\n"
            f"{get_text('profile_challenges_completed', lang=lang)}: {completed_challenges}\n"
            f"{get_text('profile_challenge_streak', lang=lang)}: {user_data.get('challenge_streak', 0)} 🔥\n"
            f"{get_text('profile_status', lang=lang)}: {status_text}")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def send_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, title_key: str, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    title = get_text(title_key, lang=lang)
    
    data = context.application.bot_data.get(key, {})
    item_list = data.get(lang, data.get(DEFAULT_LANG, [])) if isinstance(data, dict) else data if isinstance(data, list) else []

    logger.debug(f"Attempting to send item from list '{key}' for lang '{lang}'. Found {len(item_list)} items.")
    
    if not item_list:
        await safe_send(context, chat_id, get_text('list_empty', lang=lang, title=title), reply_markup=markup)
        return
        
    user_name = context.application.bot_data["users"].get(str(chat_id), {}).get("name", "друг")
    try:
        if not isinstance(item_list, list):
            logger.error(f"Data for key '{key}/{lang}' is not a list, but {type(item_list).__name__}.")
            await safe_send(context, chat_id, get_text('list_error_data', lang=lang, title=title), reply_markup=markup)
            return

        item = random.choice(item_list).format(name=user_name)
        await update.message.reply_text(f"<b>{title}</b>\n{item}", parse_mode=ParseMode.HTML, reply_markup=markup)
    except IndexError:
         await safe_send(context, chat_id, get_text('list_error_index', lang=lang, title=title), reply_markup=markup)
         logger.error(f"IndexError when choosing from list '{key}/{lang}'. List content: {item_list}")
    except KeyError as e:
         await safe_send(context, chat_id, get_text('list_error_format', lang=lang, title=title, e=e), reply_markup=markup)
         logger.error(f"KeyError when formatting item from list '{key}/{lang}'. Error: {e}. Item list: {item_list}")
    except Exception as e:
         await safe_send(context, chat_id, get_text('list_error_unexpected', lang=lang, title=title), reply_markup=markup)
         logger.exception(f"Unexpected error in send_from_list for key '{key}/{lang}':")

async def send_motivation(u: Update, c: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup): await send_from_list(u, c, "motivations", "title_motivation", markup)
async def send_rhythm(u: Update, c: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup): await send_from_list(u, c, "ritm", "title_rhythm", markup)

async def send_rules(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    user_data = context.application.bot_data["users"].get(str(chat_id), {})
    user_tz = ZoneInfo(user_data.get("timezone", DEFAULT_TZ.key))
    today_iso = datetime.now(user_tz).date().isoformat()
    is_test_user = chat_id in TESTER_USER_IDS

    last_rules_date = user_data.get("last_rules_date")
    rules_shown_count = user_data.get("rules_shown_count", 0)

    if last_rules_date != today_iso:
        logger.debug(f"New day for rules for user {chat_id}.")
        user_data["last_rules_date"] = today_iso
        user_data["rules_shown_count"] = 0
        rules_shown_count = 0

    if rules_shown_count >= RULES_PER_DAY_LIMIT and not is_test_user:
        logger.debug(f"User {chat_id} already received {RULES_PER_DAY_LIMIT} rules today.")
        await safe_send(context, chat_id, get_text('rules_limit_reached', lang=lang), reply_markup=markup)
        return

    data = context.application.bot_data.get("rules", {})
    item_list = data.get(lang, data.get(DEFAULT_LANG, [])) if isinstance(data, dict) else data if isinstance(data, list) else []
    logger.debug(f"Attempting to send rule {rules_shown_count + 1}/{RULES_PER_DAY_LIMIT} for lang '{lang}'. Found {len(item_list)} items.")

    if not item_list:
        await safe_send(context, chat_id, get_text('list_empty', lang=lang, title=get_text('title_rules', lang=lang)), reply_markup=markup)
        return
    
    try:
        shown_today_indices = user_data.get("rules_indices_today", [])
        available_rules = [item for i, item in enumerate(item_list) if i not in shown_today_indices]
        
        if not available_rules:
            logger.warning(f"User {chat_id} has seen all rules, or list is smaller than limit. Resetting seen list.")
            available_rules = item_list
            shown_today_indices = []

        rule = random.choice(available_rules)
        rule_index = item_list.index(rule)
        
        title = get_text('title_rules', lang=lang)
        text = f"📜 <b>{get_text('title_rules_daily', lang=lang, title=title, count=rules_shown_count + 1, limit=RULES_PER_DAY_LIMIT)}</b>\n\n• {rule}"
        
        await safe_send(context, chat_id, text, reply_markup=markup)
        
        user_data["rules_shown_count"] = rules_shown_count + 1
        shown_today_indices.append(rule_index)
        user_data["rules_indices_today"] = shown_today_indices
        if last_rules_date != today_iso: 
            user_data["rules_indices_today"] = [rule_index]
        
        await save_users(context, context.application.bot_data["users"])

    except Exception as e:
         await safe_send(context, chat_id, get_text('list_error_unexpected', lang=lang, title=get_text('title_rules', lang=lang)), reply_markup=markup)
         logger.exception(f"Unexpected error in send_rules for key 'rules/{lang}':")


async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    logger.debug(f"Challenge command triggered by user {chat_id}")
    user_data = context.application.bot_data["users"].get(str(chat_id), {})
    user_tz = ZoneInfo(user_data.get("timezone", DEFAULT_TZ.key))
    today = datetime.now(user_tz).date()
    today_iso = today.isoformat()

    last_challenge_date_str = user_data.get("last_challenge_date")
    
    if last_challenge_date_str:
        try:
            last_challenge_date = date.fromisoformat(last_challenge_date_str)
            
            if last_challenge_date == today:
                challenge_accepted = user_data.get("challenge_accepted")
                
                if challenge_accepted is False:
                    logger.debug(f"User {chat_id} has a pending (un-accepted) challenge.")
                    await update.message.reply_text(get_text('challenge_pending_acceptance', lang=lang), reply_markup=markup)
                    return
                
                elif challenge_accepted is True and not (chat_id in TESTER_USER_IDS):
                    logger.debug(f"User {chat_id} already has an accepted challenge for today.")
                    await update.message.reply_text(get_text('challenge_already_issued', lang=lang), reply_markup=markup)
                    return
                
            elif last_challenge_date < today - timedelta(days=1):
                last_challenge_obj = next((ch for ch in reversed(user_data.get("challenges", [])) if date.fromisoformat(ch["accepted"].split("T")[0]) == last_challenge_date), None)
                if last_challenge_obj and not last_challenge_obj.get("completed"):
                     logger.info(f"Streak reset for {chat_id}: Previous challenge on {last_challenge_date_str} not completed.")
                     user_data["challenge_streak"] = 0
                     await save_users(context, context.application.bot_data["users"])

        except (ValueError, TypeError) as e:
             logger.error(f"Error parsing last_challenge_date '{last_challenge_date_str}' for user {chat_id}: {e}")

    logger.debug(f"Sending new challenge for user {chat_id}")
    await send_new_challenge_message(update, context, is_edit=False, markup=markup)


async def send_new_challenge_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_edit=False, markup: ReplyKeyboardMarkup = None):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    
    challenges_data = context.application.bot_data.get('challenges', {})
    challenge_list = challenges_data.get(lang, challenges_data.get(DEFAULT_LANG, []))
    
    logger.debug(f"Attempting to send challenge for lang '{lang}'. Found {len(challenge_list)} total challenges.")

    if not challenge_list:
        logger.error(f"Challenge list is empty for lang '{lang}'!")
        await safe_send(context, chat_id, get_text('list_empty', lang=lang, title=get_text('btn_challenge', lang=lang)), reply_markup=markup)
        return

    try:
        challenge_raw = random.choice(challenge_list)
        logger.debug(f"Selected challenge (raw): {challenge_raw}")

        user_name = context.application.bot_data["users"].get(str(chat_id), {}).get("name", "друг")
        formatted_challenge = challenge_raw.format(name=user_name)
        logger.debug(f"Formatted challenge: {formatted_challenge}")

        context.user_data['current_challenge_text'] = formatted_challenge
        logger.debug(f"Stored challenge text in user_data for {chat_id}")

        keyboard = [[
            InlineKeyboardButton(get_text('btn_challenge_accept', lang=lang), callback_data="accept_current_challenge"),
            InlineKeyboardButton(get_text('btn_challenge_new', lang=lang), callback_data="new_challenge")
        ]]

        text = get_text('challenge_new_day', lang=lang, challenge_text=formatted_challenge)
        sender = update.callback_query.edit_message_text if is_edit else update.message.reply_text

        sent_message = None
        if is_edit:
            sent_message = await sender(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            sent_message = await sender(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        
        message_id_to_store = None
        if not is_edit and sent_message:
             message_id_to_store = sent_message.message_id
        elif is_edit and update.callback_query:
             message_id_to_store = update.callback_query.message.message_id
             
        if message_id_to_store:
             context.user_data['challenge_message_id'] = message_id_to_store
             logger.debug(f"Stored/Updated challenge message ID {message_id_to_store} for user {chat_id}")

        users_data = context.application.bot_data["users"]
        user_tz = ZoneInfo(users_data.get(str(chat_id), {}).get("timezone", DEFAULT_TZ.key))
        today_iso = datetime.now(user_tz).date().isoformat()
        users_data[str(chat_id)]["last_challenge_date"] = today_iso
        users_data[str(chat_id)]["challenge_accepted"] = False
        await save_users(context, users_data)
        logger.debug(f"Challenge sent/edited successfully for {chat_id}")
    except IndexError:
         logger.error(f"IndexError when choosing challenge! List content: {challenge_list}")
         await safe_send(context, chat_id, get_text('challenge_choose_error', lang=lang), reply_markup=markup)
    except KeyError as e:
         logger.error(f"KeyError formatting challenge for {chat_id}. Lang: {lang}, Missing key: {e}. Raw challenge: '{challenge_raw}'")
         await safe_send(context, chat_id, get_text('list_error_format', lang=lang, title=get_text('btn_challenge', lang=lang), e=e), reply_markup=markup)
    except BadRequest as e:
         logger.error(f"BadRequest sending challenge to {chat_id}: {e}.")
         await safe_send(context, chat_id, get_text('challenge_button_error', lang=lang), reply_markup=markup)
    except Exception as e:
         logger.exception(f"Unexpected error sending challenge to {chat_id}:")
         await safe_send(context, chat_id, get_text('challenge_unexpected_error', lang=lang), reply_markup=markup)

# --- Новые функции для оплаты ---
async def handle_pay_real(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    """Отправляет обычному пользователю инструкции по P2P оплате."""
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    logger.info(f"Sending P2P (Monobank) instructions to user {chat_id}.")
    await safe_send(context, chat_id, get_text('pay_instructions', lang=lang), 
                    disable_web_page_preview=True, reply_markup=markup)

async def handle_pay_api_test(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    """Симулирует успешную API-оплату для тестового пользователя."""
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    users_data = context.application.bot_data.get("users", {})
    user_data = users_data.get(str(chat_id))

    if not user_data or chat_id not in TESTER_USER_IDS:
        logger.warning(f"Non-tester {chat_id} tried to use test payment.")
        return

    logger.info(f"Simulating API payment for test user {chat_id}.")
    user_data["is_paid"] = True
    user_data["demo_expiration"] = None
    await save_users(context, users_data)
    
    await safe_send(context, chat_id, get_text('pay_api_success_test', lang=lang), 
                    reply_markup=get_reply_keyboard_for_user(chat_id, lang, user_data))


# --- Админские функции ---
async def show_users_file(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    lang = get_user_lang(context, update.effective_chat.id)
    if USERS_FILE.exists() and USERS_FILE.stat().st_size > 2:
        with open(USERS_FILE, "rb") as f:
            await update.message.reply_document(document=f, caption=get_text('users_file_caption', lang=lang), reply_markup=markup)
    else:
        await update.message.reply_text(get_text('users_file_empty', lang=lang), reply_markup=markup)

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    users_data = {k: v for k, v in context.application.bot_data["users"].items()}
    total = len(users_data)
    active = sum(1 for u in users_data.values() if u.get("active"))
    inactive = total - active
    active_first = sum(1 for u in users_data.values() if u.get("active") and u.get("demo_count", 1) == 1)
    active_repeat = sum(1 for u in users_data.values() if u.get("active") and u.get("demo_count", 1) > 1)
    inactive_demo_expired = sum(1 for u in users_data.values() if not u.get("active") and is_demo_expired(u))
    inactive_blocked = inactive - inactive_demo_expired
    stats_text = (f"👥 <b>{get_text('profile_status_total', lang=lang)}:</b> {total}\n\n"
                  f"✅ <b>{get_text('profile_status_active', lang=lang)}:</b> {active}\n"
                  f"   - <i>{get_text('profile_status_first_time', lang=lang)}:</i> {active_first}\n"
                  f"   - <i>{get_text('profile_status_repeat', lang=lang)}:</i> {active_repeat}\n\n"
                  f"❌ <b>{get_text('profile_status_inactive', lang=lang)}:</b> {inactive}\n"
                  f"   - <i>{get_text('profile_status_demo_expired', lang=lang)}:</i> {inactive_demo_expired}\n"
                  f"   - <i>{get_text('profile_status_blocked', lang=lang)}:</i> {inactive_blocked}")

    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=markup)

# Скрытая команда
async def reload_data(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    lang = get_user_lang(context, update.effective_chat.id)
    logger.info(f"Admin {update.effective_chat.id} triggered reload_data.")
    await setup_jobs_and_cache(context.application)
    await update.message.reply_text(get_text('reload_confirm', lang=lang), reply_markup=markup)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    chat_id_str = str(chat_id)
    
    is_new_flow = query.data.endswith("_new")
    
    new_lang = None
    if query.data.startswith("set_lang_"):
        new_lang_code = query.data.split("_")[2]
        if new_lang_code in translations:
            new_lang = new_lang_code
            
    if not new_lang:
        new_lang = get_user_lang(context, chat_id)
    
    lang = new_lang

    logger.info(f"💬 Callback от {chat_id} (lang: {lang}): {query.data}")

    users_data = context.application.bot_data["users"]
    user_data = users_data.get(chat_id_str, {})
    data = query.data

    if data.startswith("set_lang_"):
        is_test_user = (chat_id in TESTER_USER_IDS)
        
        user_data["language"] = lang
        
        if is_new_flow:
            user_name = query.from_user.first_name or "друг"
            user_data["id"] = chat_id
            user_data["name"] = user_name
            user_data["active"] = True
            user_data["timezone"] = DEFAULT_TZ.key
            user_data["demo_count"] = user_data.get("demo_count", 0) + 1
            user_data["challenge_streak"] = 0
            user_data["challenges"] = []
            user_data["last_challenge_date"] = None
            user_data["last_rules_date"] = None
            user_data["rules_shown_count"] = 0 
            user_data["sent_expiry_warning"] = False
            user_data["is_paid"] = False # Сброс оплаты (для тестеров)

            demo_duration_days = 1 if is_test_user else DEMO_DAYS
            user_data["demo_expiration"] = (datetime.now(ZoneInfo("UTC")) + timedelta(days=demo_duration_days)).isoformat()
            
            logger.info(f"👤 Пользователь {chat_id} зарегистрирован/обновлен с языком {lang}. Демо: {demo_duration_days} дней.")

            if chat_id != ADMIN_CHAT_ID and not is_test_user and user_data["demo_count"] == 1:
                admin_lang = get_user_lang(context, ADMIN_CHAT_ID)
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(get_text('admin_stats_button', lang=admin_lang), callback_data="admin_stats")]])
                admin_notification_text = get_text('admin_new_user', lang=admin_lang, name=user_name, user_id=chat_id)
                try:
                    await context.application.bot.send_message(
                        ADMIN_CHAT_ID, admin_notification_text, reply_markup=keyboard
                    )
                    logger.info(f"Уведомление о новом пользователе {chat_id} отправлено админу.")
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление админу о новом пользователе {chat_id}: {e}")
        
        users_data[chat_id_str] = user_data
        await save_users(context, users_data)
        
        markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
        await query.edit_message_text(get_text('lang_chosen', lang=lang), reply_markup=None)
        
        if is_new_flow:
            await safe_send(context, chat_id, get_text('welcome', lang=lang, name=user_data.get("name"), demo_days=demo_duration_days), reply_markup=markup)
        else:
             await context.bot.send_message(chat_id, get_text('lang_chosen', lang=lang), reply_markup=markup)
        return

    elif data == "accept_current_challenge":
        challenge_text = context.user_data.get('current_challenge_text')
        message_id = context.user_data.get('challenge_message_id')
        if not challenge_text or not message_id:
             logger.error(f"No challenge text or message_id in user_data for {chat_id_str} on accept.")
             await query.edit_message_text(get_text('challenge_accept_error', lang=lang))
             return

        user_data["challenge_accepted"] = True
        challenge_history = user_data.setdefault("challenges", [])
        challenge_entry = {"text": challenge_text, "accepted": datetime.now(ZoneInfo("UTC")).isoformat(), "completed": None}
        challenge_history.append(challenge_entry)
        accepted_challenge_index = len(challenge_history) - 1
        
        await save_users(context, users_data)

        keyboard = [[InlineKeyboardButton(get_text('btn_challenge_complete', lang=lang), callback_data=f"complete_challenge:{accepted_challenge_index}")]]
        try:
             await context.bot.edit_message_text(
                 chat_id=chat_id, message_id=message_id,
                 text=get_text('challenge_accepted_msg', lang=lang, challenge_text=challenge_text),
                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
             )
             logger.debug(f"Challenge accepted message edited for {chat_id_str}")
        except BadRequest as e:
             logger.error(f"Failed to edit message {message_id} for {chat_id_str} on accept: {e}")
             await context.bot.send_message(
                 chat_id=chat_id, text=get_text('challenge_accepted_msg', lang=lang, challenge_text=challenge_text),
                 reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
             )
        context.user_data.pop('current_challenge_text', None)


    elif data.startswith("complete_challenge:"):
        message_id = context.user_data.get('challenge_message_id')
        if not message_id:
             logger.error(f"No challenge message_id in user_data for {chat_id_str} on complete.")
             try: await query.edit_message_text(get_text('challenge_completed_edit_err', lang=lang))
             except BadRequest: pass
             return
        
        try:
            challenge_index_to_complete = int(data.split(":")[-1])
            challenge_history = user_data.get("challenges", [])
            
            if 0 <= challenge_index_to_complete < len(challenge_history):
                if challenge_history[challenge_index_to_complete].get("completed"):
                     logger.warning(f"Challenge {challenge_index_to_complete} already completed by {chat_id_str}.")
                     try: await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
                     except BadRequest: pass
                     return

                challenge_history[challenge_index_to_complete]["completed"] = datetime.now(ZoneInfo("UTC")).isoformat()
                current_streak = user_data.get("challenge_streak", 0) + 1
                user_data["challenge_streak"] = current_streak
                await save_users(context, users_data)
                
                original_text = query.message.text if query.message else "Челлендж"
                confirmation_text = get_text('challenge_completed_msg', lang=lang)
                
                await context.bot.edit_message_text(
                     chat_id=chat_id, message_id=message_id,
                     text=f"{original_text}\n\n<b>{confirmation_text}</b>",
                     reply_markup=None, parse_mode=ParseMode.HTML
                 )
                logger.info(f"Challenge {challenge_index_to_complete} completed by user {chat_id_str}. New streak: {current_streak}")

                if current_streak >= 3:
                     await safe_send(context, chat_id, get_text('challenge_streak_3', lang=lang, name=user_data.get("name", "друг")))
                     user_data["challenge_streak"] = 0
                     await save_users(context, users_data)

            else:
                 logger.error(f"Invalid challenge index {challenge_index_to_complete} for user {chat_id_str}")
                 await query.edit_message_text(get_text('challenge_completed_edit_err', lang=lang))

        except (ValueError, IndexError) as e:
             logger.error(f"Error processing complete_challenge callback for {chat_id_str}: {e}. Data: {data}")
             await query.edit_message_text(get_text('challenge_completed_edit_err', lang=lang))
        except BadRequest as e:
             logger.error(f"Failed to edit message {message_id} for {chat_id_str} on complete: {e}")
             await context.bot.send_message(chat_id, get_text('challenge_completed_msg', lang=lang), parse_mode=ParseMode.HTML)
        finally:
             context.user_data.pop('challenge_message_id', None)


    elif data == "new_challenge":
        await send_new_challenge_message(update, context, is_edit=True)
    elif data == "admin_stats":
        if is_admin(chat_id):
            markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
            mock_update = type('obj', (object,), {
                'message': query.message, 
                'effective_chat': query.message.chat,
            })()
            mock_update.message.reply_text = query.message.reply_text
            await user_stats(mock_update, context, markup=markup)

# --- ⭐️ ГЛАВНЫЙ ДИСПЕТЧЕР СООБЩЕНИЙ ⭐️ ---
async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return

    text, chat_id = update.message.text, update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    logger.debug(f"Received message from {chat_id} (lang: {lang}): '{text}'")

    user_data = context.application.bot_data.get("users", {}).get(str(chat_id))
    if not user_data:
        logger.warning(f"User {chat_id} not found in bot_data. Asking to /start.")
        await update.message.reply_text(get_text('start_required', lang=DEFAULT_LANG))
        return

    is_user_admin = is_admin(chat_id)
    is_test_user = chat_id in TESTER_USER_IDS

    if is_demo_expired(user_data) and not is_user_admin and not user_data.get("is_paid"):
        logger.info(f"Demo expired for user {chat_id}. Checking cooldown...")
        
        markup = None
        demo_count = user_data.get("demo_count", 1)
        
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            demo_exp_date = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
            cooldown_days = TESTER_COOLDOWN_DAYS if is_test_user else REGULAR_COOLDOWN_DAYS
            next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
            
            if now_utc >= next_demo_dt:
                show_demo_button = (demo_count < MAX_DEMO_CYCLES)
                markup = get_payment_keyboard(lang=lang, is_test_user=is_test_user, show_new_demo=show_demo_button)
            else:
                markup = get_payment_keyboard(lang=lang, is_test_user=is_test_user, show_new_demo=False)
        except Exception:
             markup = get_payment_keyboard(lang=lang, is_test_user=is_test_user, show_new_demo=(demo_count < MAX_DEMO_CYCLES))
        
        # --- Обработка нажатий кнопок в состоянии "демо истек" ---
        if text == get_btn_text('pay_api_test', lang) and is_test_user:
            await handle_pay_api_test(update, context, markup=markup)
            return
        elif text == get_btn_text('pay_real', lang) and not is_test_user:
            await handle_pay_real(update, context, markup=markup)
            return
        elif text == get_btn_text('new_demo', lang):
            await start_command(update, context) # Перезапускаем /start для активации
            return

        # --- Отправка сообщения о состоянии, если нажата любая другая кнопка ---
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            demo_exp_date = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
            cooldown_days = TESTER_COOLDOWN_DAYS if is_test_user else REGULAR_COOLDOWN_DAYS
            next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
            
            if now_utc < next_demo_dt:
                time_left = next_demo_dt - now_utc
                hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes_left, _ = divmod(remainder, 60)
                await safe_send(context, chat_id, get_text('demo_expired_cooldown', lang=lang, name=user_data.get("name", "друг"), hours=hours_left, minutes=minutes_left), reply_markup=markup)
            else:
                if demo_count < MAX_DEMO_CYCLES:
                    demo_days = TESTER_DEMO_DAYS if is_test_user else REGULAR_DEMO_DAYS
                    await safe_send(context, chat_id, get_text('demo_expired_choice', lang=lang, name=user_data.get("name", "друг"), demo_days=demo_days), reply_markup=markup)
                else:
                    await safe_send(context, chat_id, get_text('demo_expired_final', lang=lang, name=user_data.get("name", "друг")), reply_markup=markup)
        
        except Exception:
             await safe_send(context, chat_id, get_text('demo_expired_final', lang=lang, name=user_data.get("name", "друг")), reply_markup=markup)
        return
    
    markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
    
    all_handlers = {
        get_btn_text('motivate', lang): send_motivation,
        get_btn_text('rhythm', lang): send_rhythm,
        get_btn_text('rules', lang): send_rules,
        get_btn_text('challenge', lang): challenge_command,
        get_btn_text('profile', lang): profile_command,
        get_btn_text('stats', lang): user_stats,
        get_btn_text('show_users', lang): show_users_file,
        get_btn_text('reload_data', lang): reload_data, # Скрытая команда
        get_btn_text('pay_api_test', lang): handle_pay_api_test, # Для тестера, если он нажмет ее ДО истечения демо
    }

    handler_to_call = all_handlers.get(text)

    if handler_to_call:
        admin_only_button_keys = {'stats', 'show_users', 'reload_data'}
        button_key_pressed = None
        for key, handler in all_handlers.items():
             if key == text and handler == handler_to_call:
                  button_key_pressed = next((k for k,v in translations[lang].items() if v == text and k.startswith("btn_")), None)
                  if button_key_pressed:
                       button_key_pressed = button_key_pressed.replace("btn_", "")
                  break

        is_admin_button = button_key_pressed in admin_only_button_keys

        if is_admin_button and not is_user_admin:
            logger.warning(f"User {chat_id} attempted to use admin command: {text}")
        else:
            logger.debug(f"Calling handler {handler_to_call.__name__} for user {chat_id}")
            await handler_to_call(update, context, markup=markup)
    else:
         logger.warning(f"Unknown command received from user {chat_id}: {text}")
         await update.message.reply_text(get_text('unknown_command', lang=lang), reply_markup=markup)


# ----------------- 🚀 ЗАПУСК И НАСТРОЙКА -----------------
async def setup_jobs_and_cache(app: Application):
    try:
        app.bot_data["users"] = load_json_data(USERS_FILE, default_factory=dict)
        logger.info(f"👥 Загружено {len(app.bot_data['users'])} пользователей")

        for key, filename in FILE_MAPPING.items():
            filepath = DATA_DIR / filename
            data = load_json_data(filepath)
            app.bot_data[key] = data
            size_info = len(data) if isinstance(data, (list, dict)) else 'N/A'
            logger.info(f"  -> {filename}: {size_info} записей/ключей (Type: {type(data).__name__})")

        load_all_challenges_into_cache(app)

        logger.info("📚 Кэш статических данных загружен")

        if app.job_queue:
            for job in app.job_queue.jobs():
                job.schedule_removal()
                logger.debug(f"Удалена job: {job}")

        now = datetime.now(DEFAULT_TZ)
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        # ✅ ИЗМЕНЕНО: 2 задачи в Job Queue
        app.job_queue.run_repeating(centralized_broadcast_job, interval=timedelta(hours=1), first=next_hour)
        logger.info(f"✅ Планировщик (broadcast) настроен! Первая рассылка в: {next_hour.isoformat()}")
        
        # Вторая задача - проверка истечения демо (запускается через 2 минуты, потом раз в час)
        app.job_queue.run_repeating(check_demo_expiry_job, interval=timedelta(hours=1), first=now + timedelta(minutes=2))
        logger.info(f"✅ Планировщик (demo expiry) настроен! Первая проверка в: {(now + timedelta(minutes=2)).isoformat()}")

    except Exception as e:
        logger.error(f"❌ Ошибка в setup_jobs_and_cache: {e}")
        logger.exception("Полный traceback для setup_jobs_and_cache:")
        raise

application = ApplicationBuilder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("pay", pay_command))
application.add_handler(CommandHandler("language", language_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))
application.add_handler(CallbackQueryHandler(handle_callback_query))

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_error = None
    try:
        if not BOT_TOKEN:
            startup_error = "BOT_TOKEN не задан!"
        elif not ADMIN_CHAT_ID or ADMIN_CHAT_ID == 0:
            startup_error = "ADMIN_CHAT_ID не задан!"
        
        if startup_error:
             logger.critical(f"❌ {startup_error} Бот не запустится.")
             yield; return

        logger.debug("Lifespan: Starting initialization...")
        setup_initial_files()
        await application.initialize()
        await setup_jobs_and_cache(application)
        await application.start()
        logger.debug("Lifespan: Application started.")

        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL}/telegram/{BOT_TOKEN}"
            await application.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook установлен.")
        else:
            logger.info("⚠️ WEBHOOK_URL не задан — используется polling (локально).")

        admin_lang = get_user_lang(application, ADMIN_CHAT_ID)
        await application.bot.send_message(ADMIN_CHAT_ID, get_text('admin_bot_started', lang=admin_lang))
        logger.info("✅ Lifespan STARTED - Бот готов!")

    except Exception as e:
        startup_error = e
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА в lifespan при запуске: {e}")
        logger.exception("Полный traceback:")

    yield

    logger.info("Lifespan: Stopping application...")
    try:
        if not startup_error:
             admin_lang = get_user_lang(application, ADMIN_CHAT_ID)
             await application.bot.send_message(ADMIN_CHAT_ID, get_text('admin_bot_stopping', lang=admin_lang))
        
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
async def health_check(): return {"status": "fotinia-v8.9-advanced-demo-cycle-ready"}

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск в режиме Polling")
        setup_initial_files()
        asyncio.run(setup_jobs_and_cache(application))
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Ошибка в polling: {e}")
        logger.exception("Полный traceback:")

