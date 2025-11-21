#!/usr/bin/env python3
"""
🚀 FOTINIA BOT v10.16.1 (Auto-TZ, Admin Grant & JobQueue Backups)

✅ ФУНКЦИОНАЛ: Полная админка, /pay, сложная логика челленджей, локализация (RU/UA/EN).
✅ АРХИТЕКТУРА: FastAPI, JSON+Lock, 2 Job Schedulers, современная работа со временем.

✅ НОВОЕ v10.16: Бэкапы users.json теперь запускаются через JobQueue (каждые 6 часов).
✅ НОВОЕ v10.15: Добавлена админ-команда /grant [ID] для выдачи Premium.
✅ НОВОЕ v10.15: Автоматическое определение часового пояса при регистрации.
✅ НОВОЕ v10.15: Убрана кнопка "⚙️ Настройки" (команда /timezone оставлена).

🐞 ИСПРАВЛЕНИЕ v10.16.1 (CRITICAL): Исправлен 'TypeError' (multiple values for 'parse_mode')
    при регистрации нового пользователя (в handle_callback_query).
🐞 ИСПРАВЛЕНИЕ v10.16.1: Исправлена передача 'context' в 'get_user_lang'
    внутри handle_callback_query.
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
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Dict
from contextlib import asynccontextmanager

# Webhook и FastAPI
from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Application
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
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

# --- v10.11: Конфигурация Симулятора ---
# ID пользователя @fotinia_admin для симуляции 2+1+2
SIMULATOR_USER_IDS = {6112492697}
# ------------------------------------

DEFAULT_LANG = "ru"
DEFAULT_TZ_KEY = "Europe/Kiev" # ⭐️ v10.15: Стало ключом по умолчанию
DEFAULT_TZ = ZoneInfo(DEFAULT_TZ_KEY)

REGULAR_DEMO_DAYS = 5
REGULAR_COOLDOWN_DAYS = 1
TESTER_DEMO_DAYS = 1
TESTER_COOLDOWN_DAYS = 1

RULES_PER_DAY_LIMIT = 3
MAX_DEMO_CYCLES = 2

BOT_USERNAME = "FotiniaBot"

logger.info("🤖 Bot starting...")
logger.info(f"🔑 ADMIN_CHAT_ID configured as: {ADMIN_CHAT_ID}")
logger.info(f"🧪 TESTER_USER_IDS configured as: {TESTER_USER_IDS}")
logger.info(f"🎮 SIMULATOR_USER_IDS configured as: {SIMULATOR_USER_IDS}")

# --- 📍 ПУТИ К ФАЙЛАМ ---
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))

# --- 📄 НАЗВАНИЯ ФАЙЛОВ ---
USERS_FILE = DATA_DIR / "users.json"

# --- ⭐️ FIX v10.14: НОВАЯ ФУНКЦИЯ ЗАГРУЗКИ С "ЛЕЧЕНИЕМ" ---
def load_users_with_fix():
    """
    Загружает данные пользователей из файла.
    ВКЛЮЧАЕТ ОБХОДНОЙ МАНЕВР для исправления поврежденной структуры v10.12.
    """
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info(f"Файл '{USERS_FILE}' не найден. Будет создан новый.")
        return {}
    except json.JSONDecodeError:
        logger.warning(f"Файл '{USERS_FILE}' пуст или содержит невалидный JSON. Будет создан новый.")
        return {}
    except Exception as e:
        logger.error(f"Неожиданная ошибка при чтении {USERS_FILE}: {e}")
        return {}

    # --- НАЧАЛО ОБХОДНОГО МАНЕВРА ---
    
    # Проверяем, имеет ли файл поврежденную структуру (от v10.12)
    # т.е. содержит ключи 'users', 'rules' и т.д. на верхнем уровне
    if isinstance(data, dict) and 'users' in data and ('rules' in data or 'motivations' in data):
        
        logger.warning(f"ОБНАРУЖЕНА ПОВРЕЖДЕННАЯ СТРУКТУРА '{USERS_FILE}'. Применяется авто-исправление...")
        
        # 1. Извлекаем правильные данные (то, что лежит ВНУТРИ 'users')
        correct_data = data.get('users', {})
        
        if not isinstance(correct_data, dict):
            logger.error("Критическая ошибка: 'users' внутри файла - не словарь. Сбрасываю к пустым данным.")
            correct_data = {}

        # 2. (ВАЖНО) Перезаписываем файл ТОЛЬКО правильными данными
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(correct_data, f, indent=4, ensure_ascii=False)
            logger.info(f"Файл '{USERS_FILE}' УСПЕШНО ИСПРАВЛЕН (перезаписан).")
        except IOError as e:
            logger.error(f"НЕ УДАЛОСЬ перезаписать '{USERS_FILE}': {e}.")
        
        # 3. Возвращаем боту уже исправленные данные
        return correct_data
    
    # --- КОНЕЦ ОБХОДНОГО МАНЕВРА ---

    if not isinstance(data, dict):
         logger.warning(f"ПРЕДУПРЕЖДЕНИЕ: {USERS_FILE} содержит не словарь. Сбрасываю к пустому словарю.")
         return {}
             
    logger.info(f"Успешно загружены данные из {USERS_FILE}.")
    return data # Возвращаем данные как есть
# --- ⭐️ КОНЕЦ ФИКСА v10.14 ---

# --- ⭐️ v10.15: НОВЫЙ ХЕЛПЕР ДЛЯ АВТО-TZ ---
def get_tz_from_lang(lang_code: str | None) -> str:
    """Автоматически определяет TZ по языку. По умолчанию - Киев."""
    if not lang_code:
        return DEFAULT_TZ_KEY
    
    lang_code = lang_code.lower()
    
    if lang_code.startswith('ru'):
        return "Europe/Moscow"
    if lang_code.startswith('ua'):
        return "Europe/Kiev"
    if lang_code.startswith('pl'):
        return "Europe/Warsaw"
    if lang_code.startswith('de'):
        return "Europe/Berlin"
    
    # Для 'en' и всех остальных - Киев по умолчанию
    return DEFAULT_TZ_KEY
# --- ⭐️ КОНЕЦ v10.15 ---

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
        "welcome_renewed_demo": "🌟 {name}, с возвращением! У Вас новый демо-период на {demo_days} дней. Все функции возобновлены. Достигнутые ранее уровни сброшены. В добрый путь! 👇",
        
        # --- ⭐️ v10.15: TIMEZONE И GRANT ПЕРЕВОДЫ ---
        "welcome_timezone_note": "\n\nP.S. Ваш часовой пояс был автоматически установлен: <code>{default_tz}</code>. Если он неверный, используйте команду /timezone, чтобы его изменить.",
        # "btn_settings": "⚙️ Настройки", # Убрано
        "timezone_command_text": "⚙️ <b>Настройка часового пояса</b>\n\nВаш текущий пояс: <code>{user_tz}</code>\n\nЧтобы изменить его, <b>отправьте свой часовой пояс</b> в формате IANA (TZ Database).\n\nНапример:\n<code>Europe/Berlin</code>\n<code>Europe/Warsaw</code>\n<code>America/New_York</code>\n<code>Asia/Tbilisi</code>\n\nОтправьте /cancel для отмены.",
        "timezone_set_success": "✅ Часовой пояс обновлен на <code>{new_tz}</code>.",
        "timezone_set_error": "⚠️ Ошибка. <code>{error_text}</code> - это невалидный часовой пояс. Попробуйте еще раз (например, <code>Europe/Kiev</code>) или нажмите /cancel.",
        "timezone_cancel": "✅ Настройка отменена. Ваш часовой пояс остался: <code>{user_tz}</code>.",
        "cmd_cancel": "Отмена",
        "admin_grant_success": "✅ Premium-доступ успешно выдан пользователю {name} (ID: {user_id}).",
        "admin_grant_fail_id": "⚠️ Ошибка. Пользователь с ID <code>{user_id}</code> не найден.",
        "admin_grant_fail_already_paid": "⚠️ Пользователь {name} (ID: {user_id}) уже имеет Premium-доступ.",
        "admin_grant_usage": "⚠️ Неверный формат. Используйте: <code>/grant [ID_пользователя]</code>",
        "user_grant_notification": "🎉 <b>Доступ активирован!</b>\n\nАдминистратор активировал ваш Premium-доступ. Поздравляем!\n\nНажмите /start, чтобы обновить клавиатуру.",
        # --- ⭐️ КОНЕЦ v10.15 ---
        
        "demo_expiring_soon_h": "🔒 {name}, ваш демо-доступ истекает менее чем через {hours} час(а). Не забудьте активировать подписку, чтобы не терять прогресс!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Ваш демо-доступ закончился.</b>\n\nДо возобновления демо-периода осталось **{hours} ч. {minutes} мин.**\n\nВы также можете активировать Premium-доступ прямо сейчас, нажав кнопку '👑 Хочу Premium'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Ваш демо-доступ закончился.</b>\n\nВы можете активировать **еще один** пробный период ({demo_days} дня) или получить постоянный Premium-доступ.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Ваши пробные периоды закончились.</b>\n\nДля возобновления доступа, пожалуйста, активируйте Premium-подписку. 👇",
        "demo_awaiting_renewal": "Понял. Ваш демо-период возобновится через **{hours} ч. {minutes} мин.**\n\nВ режиме ожидания рассылки отключены, но вы можете активировать Premium в любой момент.",
        "pay_info": "💳 Для получения полного доступа, пожалуйста, свяжитесь с администратором.",
        "pay_instructions": "✅ {name}, добро пожаловать в Premium! Я буду Вашей поддержкой в течение 30 дней. За это время Вы получите 120 сообщений (это ~2 грн за сообщение).\n\nДля активации, пожалуйста, переведите **245 грн** на эту Банку Monobank:\n\n`https://send.monobank.ua/jar/ao8c487LS`\n\n**ВАЖНО:** После оплаты, пожалуйста, пришлите скриншот чека нашему менеджеру: **@fotinia_admin**. Он увидит его и активирует ваш доступ вручную.",
        "pay_api_success_test": "✅ {name}, добро пожаловать в Premium! (Тест API)\nЯ буду Вашей поддержкой в течение 30 дней. За это время Вы получите 120 сообщений (это ~2 грн за сообщение). Нажмите /start.",
        "share_text_template": "Посмотри, какой бот мне помогает двигаться к цели! @{bot_username}",
        "reaction_received": "Благодарю за твою реакцию, {name}!",
        "profile_title": "👤 <b>Ваш профиль:</b>",
        "profile_name": "📛 Имя",
        "profile_challenges_accepted": "⚔️ Принято челленджей",
        "profile_challenges_completed": "✅ Выполнено",
        "profile_challenge_streak": "🔥 Серия выполнений",
        "profile_status": "💰 Статус",
        "profile_likes": "👍 Лайки",
        "profile_dislikes": "👎 Дизлайки",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Демо",
        "list_empty": "⚠️ Список для '{title}' пуст.",
        "list_error_format": "⚠️ Ошибка форматирования текста для '{title}'. Отсутствует ключ: {e}",
        "list_error_index": "⚠️ Произошла ошибка при выборе элемента из списка '{title}'. Список может быть пуст.",
        "list_error_unexpected": "⚠️ Произошла непредвиденная ошибка при отправке '{title}'.",
        "list_error_data": "⚠️ Ошибка данных для '{title}'. Обратитесь к администратору.",
        "challenge_already_issued": "⏳ Вы уже приняли челленддж на сегодня.",
        "challenge_pending_acceptance": "🔥 У вас уже есть активный челлендж. Примите его или нажмите 'Новый' в сообщении выше.",
        "challenge_accepted_msg": "💪 <b>Челлендж принят:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Отлично! Челлендж выполнен!",
        "challenge_completed_edit_err": "⚠️ Не удалось отредактировать сообщение о выполнении.",
        "challenge_new_day": "⚔️ <b>Челлендж дня:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Ошибка при выборе челленджа. Список может быть пустым.",
        "challenge_button_error": "⚠️ Произошла ошибка при формировании кнопок челленджа.",
        "challenge_unexpected_error": "⚠️ Произошла непредвиденная ошибка при отправке челленджа.",
        "challenge_accept_error": "⚠️ Произошла ошибка при принятии челленджа. Попробуйте запросить челлендж заново.",
        "challenge_streak_3_level_1": "🔥🔥🔥 {name}, ты молодец! Выполнено 3 челленджа подряд, и достигнут 1 уровень. Продолжай в том же темпе, и тебя ждет награда!",
        "unknown_command": "❓ Неизвестная команда. Пожалуйста, используйте кнопки.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "Файл users.json ещё не создан или пуст.",
        "reload_confirm": "✅ Кэш и задачи планировщика обновлены!",
        "start_required": "Похоже, мы ещё не знакомы. Пожалуйста, нажмите /start, чтобы начать.",
        "admin_new_user": "🎉 Новый пользователь: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Показать статистику",
        "admin_bot_started": "🤖 Бот успешно запущен (v10.16.1 - Auto-TZ, Grant & Backup)",
        "admin_bot_stopping": "⏳ Бот останавливается...",
        "lang_choose": "Выберите язык: 👇",
        "lang_chosen": "✅ Язык установлен на Русский.",
        "btn_motivate": "💪 Мотивируй меня", "btn_rhythm": "🎵 Ритм дня",
        "btn_challenge": "⚔️ Челлендж дня", "btn_rules": "📜 Правила Вселенной",
        "btn_profile": "👤 Профиль",
        "btn_share": "💌 Поделиться",
        "btn_show_users": "📂 Смотреть users.json", "btn_stats": "📊 Статистика",
        "btn_reload_data": "🔄 Обновить",
        "btn_pay_premium": "👑 Хочу Premium",
        "btn_pay_api_test_premium": "👑 Premium (API Тест)",
        "btn_want_demo": "🔄 Хочу демо",
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
        "welcome_renewed_demo": "🌟 {name}, з поверненням! У Вас новий демо-період на {demo_days} днів. Всі функції відновлено. Досягнуті раніше рівні скинуті. В добру путь! 👇",
        
        # --- ⭐️ v10.15: TIMEZONE И GRANT ПЕРЕВОДЫ ---
        "welcome_timezone_note": "\n\nP.S. Ваш часовий пояс було автоматично встановлено: <code>{default_tz}</code>. Якщо він невірний, використовуйте команду /timezone, щоб його змінити.",
        # "btn_settings": "⚙️ Налаштування", # Убрано
        "timezone_command_text": "⚙️ <b>Налаштування часового поясу</b>\n\nВаш поточний пояс: <code>{user_tz}</code>\n\nЩоб змінити його, <b>надішліть свій часовий пояс</b> у форматі IANA (TZ Database).\n\nНаприклад:\n<code>Europe/Berlin</code>\n<code>Europe/Warsaw</code>\n<code>America/New_York</code>\n<code>Asia/Tbilisi</code>\n\nНадішліть /cancel для скасування.",
        "timezone_set_success": "✅ Часовий пояс оновлено на <code>{new_tz}</code>.",
        "timezone_set_error": "⚠️ Помилка. <code>{error_text}</code> - це невалідний часовий пояс. Спробуйте ще раз (наприклад, <code>Europe/Kiev</code>) або натисніть /cancel.",
        "timezone_cancel": "✅ Налаштування скасовано. Ваш часовий пояс залишився: <code>{user_tz}</code>.",
        "cmd_cancel": "Скасувати",
        "admin_grant_success": "✅ Premium-доступ успішно видано користувачу {name} (ID: {user_id}).",
        "admin_grant_fail_id": "⚠️ Помилка. Користувача з ID <code>{user_id}</code> не знайдено.",
        "admin_grant_fail_already_paid": "⚠️ Користувач {name} (ID: {user_id}) вже має Premium-доступ.",
        "admin_grant_usage": "⚠️ Невірний формат. Використовуйте: <code>/grant [ID_користувача]</code>",
        "user_grant_notification": "🎉 <b>Доступ активовано!</b>\n\nАдміністратор активував ваш Premium-доступ. Вітаємо!\n\nНатисніть /start, щоб оновити клавіатуру.",
        # --- ⭐️ КОНЕЦ v10.15 ---
        
        "demo_expiring_soon_h": "🔒 {name}, ваш демо-доступ закінчується менш ніж за {hours} год. Не забудьте активувати підписку, щоб не втрачати прогрес!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Ваш демо-доступ закінчився.</b>\n\nДо возобновления демо-периода осталось **{hours} год {minutes} хв.**\n\nАбо ви можете активувати Premium-доступ прямо зараз, натиснувши кнопку 'Оплатити'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Ваш демо-доступ закінчився.</b>\n\nВи можете активувати **ще один** пробний період ({demo_days} дні) або отримати постійний Premium-доступ.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Ваші пробні періоди закінчилися.</b>\n\nДля відновлення доступу, будь ласка, активуйте Premium-підписку. 👇",
        "demo_awaiting_renewal": "Зрозумів. Ваш демо-період відновиться через **{hours} год {minutes} хв.**\n\nВ режимі очікування розсилки відключені, але ви можете активувати Premium у будь-який момент.",
        "pay_info": "💳 Для отримання повного доступу, будь ласка, зв'яжіться з адміністратором.",
        "pay_instructions": "✅ {name}, ласкаво просимо до Premium! Я буду Вашою підтримкою протягом 30 днів. За цей час Ви отримаєте 120 повідомлень (це ~2 грн за повідомлення).\n\nДля активації, будь ласка, перекажіть **245 грн** на цю Банку Monobank:\n\n`https://send.monobank.ua/jar/ao8c487LS`\n\n**ВАЖЛИВО:** Після оплати, будь ласка, надішліть скріншот чека нашому менеджеру: **@fotinia_admin**. Він побачить його та активує ваш доступ вручную.",
        "pay_api_success_test": "✅ {name}, ласкаво просимо до Premium! (Тест API)\nЯ буду Вашою підтримкою протягом 30 днів. За цей час Ви отримаєте 120 повідомлень (це ~2 грн за повідомлення). Натисніть /start.",
        "share_text_template": "Подивись, який бот мені допомагає рухатися до мети! @{bot_username}",
        "reaction_received": "Дякую за твою реакцію, {name}!",
        "profile_title": "👤 <b>Ваш профіль:</b>",
        "profile_name": "📛 Ім'я",
        "profile_challenges_accepted": "⚔️ Прийнято челенджів",
        "profile_challenges_completed": "✅ Виконано",
        "profile_challenge_streak": "🔥 Серія виконань",
        "profile_status": "💰 Статус",
        "profile_likes": "👍 Лайки",
        "profile_dislikes": "👎 Дизлайки",
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
        "challenge_streak_3_level_1": "🔥🔥🔥 {name}, ти молодець! Виконано 3 челенджі поспіль, і досягнуто 1 рівень. Продовжуй в тому ж темпі, і на тебе чекає нагорода!",
        "unknown_command": "❓ Невідома команда. Будь ласка, використовуйте кнопки.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "Файл users.json ще не створений або порожній.",
        "reload_confirm": "✅ Кеш та завдання планувальника оновлено!",
        "start_required": "Схоже, ми ще не знайомі. Будь ласка, натисніть /start, щоб почати.",
        "admin_new_user": "🎉 Новий користувач: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Показати статистику",
        "admin_bot_started": "🤖 Бот успішно запущен (v10.16.1 - Auto-TZ, Grant & Backup)",
        "admin_bot_stopping": "⏳ Бот зупиняється...",
        "lang_choose": "Оберіть мову: 👇",
        "lang_chosen": "✅ Мову встановлено на Українську.",
        "btn_motivate": "💪 Мотивуй мене", "btn_rhythm": "🎵 Ритм дня",
        "btn_challenge": "⚔️ Челендж дня", "btn_rules": "📜 Правила Всесвіту",
        "btn_profile": "👤 Профіль",
        "btn_share": "💌 Поділитися з другом",
        "btn_show_users": "📂 Дивитися users.json", "btn_stats": "📊 Статистика",
        "btn_reload_data": "🔄 Оновити",
        "btn_pay_premium": "👑 Хочу Premium",
        "btn_pay_api_test_premium": "👑 Premium (API Тест)",
        "btn_want_demo": "🔄 Хочу демо",
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
        "welcome_renewed_demo": "🌟 {name}, welcome back! You have a new demo period for {demo_days} days. All functions are restored. Previously achieved levels are reset. Good luck! 👇",
        
        # --- ⭐️ v10.15: TIMEZONE И GRANT ПЕРЕВОДЫ ---
        "welcome_timezone_note": "\n\nP.S. Your timezone was automatically set to <code>{default_tz}</code>. If this is incorrect, please use the /timezone command to change it.",
        # "btn_settings": "⚙️ Settings", # Убрано
        "timezone_command_text": "⚙️ <b>Timezone Settings</b>\n\nYour current timezone: <code>{user_tz}</code>\n\nTo change it, <b>please send your timezone</b> in IANA (TZ Database) format.\n\nExamples:\n<code>Europe/Berlin</code>\n<code>Europe/Warsaw</code>\n<code>America/New_York</code>\n<code>Asia/Tbilisi</code>\n\nSend /cancel to exit.",
        "timezone_set_success": "✅ Timezone updated to <code>{new_tz}</code>.",
        "timezone_set_error": "⚠️ Error. <code>{error_text}</code> is not a valid timezone. Please try again (e.g., <code>Europe/London</code>) or send /cancel.",
        "timezone_cancel": "✅ Setup cancelled. Your timezone remains: <code>{user_tz}</code>.",
        "cmd_cancel": "Cancel",
        "admin_grant_success": "✅ Premium access successfully granted to {name} (ID: {user_id}).",
        "admin_grant_fail_id": "⚠️ Error. User with ID <code>{user_id}</code> not found.",
        "admin_grant_fail_already_paid": "⚠️ User {name} (ID: {user_id}) already has Premium access.",
        "admin_grant_usage": "⚠️ Invalid format. Use: <code>/grant [USER_ID]</code>",
        "user_grant_notification": "🎉 <b>Access Activated!</b>\n\nThe administrator has activated your Premium access. Congratulations!\n\nPlease press /start to refresh your keyboard.",
        # --- ⭐️ КОНЕЦ v10.15 ---
        
        "demo_expiring_soon_h": "🔒 {name}, your demo access expires in less than {hours} hour(s). Don't forget to activate your subscription to keep your progress!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Your demo access has expired.</b>\n\nYou can reactivate a new demo period in **{hours}h {minutes}m**.\n\nOr you can activate Premium access right now by pressing 'Pay'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Your demo access has expired.</b>\n\nYou can activate **one more** trial period ({demo_days} days) or get permanent Premium access.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Your trial periods have ended.</b>\n\nTo resume access, please activate your Premium subscription. 👇",
        "demo_awaiting_renewal": "Got it. Your demo period will resume in **{hours}h {minutes}m**.\n\nBroadcasts are disabled in standby mode, but you can activate Premium at any time.",
        "pay_info": "💳 For full access, please contact the administrator.",
        "pay_instructions": "✅ {name}, welcome to Premium! I will be your support for 30 days. During this time, you will receive 120 messages (that's ~2 UAH per message).\n\nTo activate, please transfer **245 UAH** to this Monobank 'Banka' (jar):\n\n`https://send.monobank.ua/jar/ao8c487LS`\n\n**IMPORTANT:** After payment, please send a screenshot of the receipt to our manager: **@fotinia_admin**. They will see it and activate your access manually.",
        "pay_api_success_test": "✅ {name}, welcome to Premium! (API Test)\nI will be your support for 30 days. During this time, you will receive 120 messages (that's ~2 UAH per message). Press /start.",
        "share_text_template": "Check out this bot that's helping me reach my goals! @{bot_username}",
        "reaction_received": "Thank you for your reaction, {name}!",
        "profile_title": "👤 <b>Your Profile:</b>",
        "profile_name": "📛 Name",
        "profile_challenges_accepted": "⚔️ Challenges Accepted",
        "profile_challenges_completed": "✅ Completed",
        "profile_challenge_streak": "🔥 Completion Streak",
        "profile_status": "💰 Status",
        "profile_likes": "👍 Likes",
        "profile_dislikes": "👎 Dislikes",
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
        "challenge_streak_3_level_1": "🔥🔥🔥 {name}, you're amazing! 3 challenges completed in a row, and Level 1 achieved. Keep up the pace, and a reward awaits you!",
        "unknown_command": "❓ Unknown command. Please use the buttons.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "The users.json file has not been created or is empty.",
        "reload_confirm": "✅ Cache and scheduler tasks have been updated!",
        "start_required": "It seems we haven't met. Please press /start to begin.",
        "admin_new_user": "🎉 New user: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Show Statistics",
        "admin_bot_started": "🤖 Bot successfully launched (v10.16.1 - Auto-TZ, Grant & Backup)",
        "admin_bot_stopping": "⏳ Bot is stopping...",
        "lang_choose": "Select language: 👇",
        "lang_chosen": "✅ Language set to English.",
        "btn_motivate": "💪 Motivate me", "btn_rhythm": "🎵 Rhythm of the Day",
        "btn_challenge": "⚔️ Challenge of the Day", "btn_rules": "📜 Rules of the Universe",
        "btn_profile": "👤 Profile",
        "btn_share": "💌 Share",
        "btn_show_users": "📂 View users.json", "btn_stats": "📊 Statistics",
        "btn_reload_data": "🔄 Reload",
        "btn_pay_premium": "👑 Want Premium",
        "btn_pay_api_test_premium": "👑 Premium (API Test)",
        "btn_want_demo": "🔄 Want Demo",
        "btn_challenge_accept": "✅ Accept", "btn_challenge_new": "🎲 New",
        "btn_challenge_complete": "✅ Done",
        "title_motivation": "💪", "title_rhythm": "🎶 Rhythm of theDay:", "title_rules": "📜 Rules of the Universe",
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

# --- 🐞 НОВЫЕ ХЕЛПЕРЫ v10.11 ---
def get_demo_days(chat_id: int) -> int:
    """Возвращает длительность демо-периода в днях в зависимости от роли."""
    if chat_id in SIMULATOR_USER_IDS:
        return 2  # 2 дня для симулятора
    if chat_id in TESTER_USER_IDS:
        return TESTER_DEMO_DAYS  # 1 день для тестера
    return REGULAR_DEMO_DAYS  # 5 дней для обычных

def get_cooldown_days(chat_id: int) -> int:
    """Возвращает длительность кулдауна в днях в зависимости от роли."""
    if chat_id in SIMULATOR_USER_IDS:
        return 1  # 1 день для симулятора
    if chat_id in TESTER_USER_IDS:
        return TESTER_COOLDOWN_DAYS  # 1 день для тестера
    return REGULAR_COOLDOWN_DAYS  # 1 день для обычных

def get_max_demo_cycles(chat_id: int) -> int:
    """Возвращает кол-во демо-циклов в зависимости от роли."""
    if chat_id in SIMULATOR_USER_IDS:
        return 2  # 2 цикла для симулятора
    if chat_id in TESTER_USER_IDS:
        return 999  # 999 циклов для тестера (почти бесконечно)
    return MAX_DEMO_CYCLES  # 2 цикла для обычных
# --- ---------------------- ---

# --- ⌨️ КНОПКИ (з урахуванням локалізації) ---
def get_btn_text(key: str, lang: str = DEFAULT_LANG) -> str:
    return translations.get(lang, translations[DEFAULT_LANG]).get(f"btn_{key}", f"BTN_{key.upper()}")

BTN_MOTIVATE = "btn_motivate"
BTN_RHYTHM = "btn_rhythm"
BTN_CHALLENGE = "btn_challenge"
BTN_RULES = "btn_rules"
BTN_PROFILE = "btn_profile"
# BTN_SETTINGS = "btn_settings" # ⭐️ v10.15: Убрано
BTN_SHOW_USERS = "btn_show_users"
BTN_STATS = "btn_stats"
BTN_RELOAD_DATA = "btn_reload_data"
BTN_PAY_PREMIUM = "btn_pay_premium"
BTN_PAY_API_TEST_PREMIUM = "btn_pay_api_test_premium"
BTN_WANT_DEMO = "btn_want_demo"

def get_main_keyboard(lang: str = DEFAULT_LANG) -> ReplyKeyboardMarkup:
    layout = [
        [get_btn_text('motivate', lang), get_btn_text('rhythm', lang)],
        [get_btn_text('challenge', lang), get_btn_text('rules', lang)],
        [get_btn_text('profile', lang)] # ⭐️ v10.15: Убрана кнопка
    ]
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

def get_admin_keyboard(lang: str = DEFAULT_LANG) -> ReplyKeyboardMarkup:
    layout = [
        [get_btn_text('motivate', lang), get_btn_text('rhythm', lang)],
        [get_btn_text('challenge', lang), get_btn_text('rules', lang)],
        [get_btn_text('show_users', lang), get_btn_text('stats', lang)],
        [get_btn_text('profile', lang)] # ⭐️ v10.15: Убрана кнопка
    ]
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

def get_payment_keyboard(lang: str = DEFAULT_LANG, is_test_user: bool = False, show_new_demo: bool = False) -> ReplyKeyboardMarkup:
    buttons = []
    if is_test_user:
        buttons.append(get_btn_text('pay_api_test_premium', lang))
    else:
        buttons.append(get_btn_text('pay_premium', lang))
    
    if show_new_demo:
        buttons.append(get_btn_text('want_demo', lang))
        
    return ReplyKeyboardMarkup([buttons], resize_keyboard=True)

def get_cooldown_keyboard(lang: str = DEFAULT_LANG, is_test_user: bool = False) -> ReplyKeyboardMarkup:
    layout = [
        [get_btn_text('motivate', lang), get_btn_text('rhythm', lang)],
        [get_btn_text('challenge', lang), get_btn_text('rules', lang)],
        [get_btn_text('profile', lang)] # ⭐️ v10.15: Убрана кнопка
    ]
    
    if is_test_user:
        layout.append([get_btn_text('pay_api_test_premium', lang)])
    else:
        layout.append([get_btn_text('pay_premium', lang)])
        
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

def get_reply_keyboard_for_user(chat_id: int, lang: str, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    """Определяет, какую клавиатуру показать пользователю."""
    if is_admin(chat_id):
        return get_admin_keyboard(lang)
    
    if user_data.get("is_paid"):
        return get_main_keyboard(lang)
    
    is_test_user = chat_id in TESTER_USER_IDS
    
    if is_demo_expired(user_data):
        demo_count = user_data.get("demo_count", 1)
        
        if user_data.get("status") == "awaiting_renewal":
            return get_cooldown_keyboard(lang, is_test_user)
        
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            exp_dt = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
            
            # 🐞 v10.11: Используем хелперы
            cooldown_days = get_cooldown_days(chat_id)
            max_cycles = get_max_demo_cycles(chat_id)
            next_demo_dt = exp_dt + timedelta(days=cooldown_days)
            
            if now_utc >= next_demo_dt:
                show_demo_button = (demo_count < max_cycles)
                return get_payment_keyboard(lang, is_test_user, show_new_demo=show_demo_button)
            else:
                show_demo_button = (demo_count < max_cycles)
                return get_payment_keyboard(lang, is_test_user, show_new_demo=show_demo_button)
                
        except Exception:
            max_cycles = get_max_demo_cycles(chat_id)
            return get_payment_keyboard(lang, is_test_user, show_new_demo=(demo_count < max_cycles))
    
    return get_main_keyboard(lang)

USERS_FILE_LOCK = asyncio.Lock()
RULES_LOCK = asyncio.Lock()

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

# --- ⭐️ ИСПРАВЛЕНИЕ v10.16.1 ⭐️ ---
def get_user_lang(context_or_app: Any, chat_id: int) -> str:
    """
    Получает язык пользователя. 
    Принимает 'context' (из хендлера) или 'application' (из lifespan).
    """
    bot_data = {}
    if hasattr(context_or_app, 'bot_data'):
        # Это объект 'application'
        bot_data = context_or_app.bot_data
    elif hasattr(context_or_app, 'application') and hasattr(context_or_app.application, 'bot_data'):
        # Это объект 'context'
        bot_data = context_or_app.application.bot_data
    else:
        logger.error(f"get_user_lang: не удалось найти bot_data в {type(context_or_app)}")
        return DEFAULT_LANG

    user_data = bot_data.get("users", {}).get(str(chat_id), {})
    return user_data.get("language", DEFAULT_LANG)
# --- ⭐️ КОНЕЦ ИСПРАВЛЕНИЯ v10.16.1 ⭐️ ---


# --- ⭐️ НОВАЯ ФУНКЦИЯ БЭКАПА (v10.16) ⭐️ ---
def backup():
    """Создает бэкап users.json в папке /app/data/backups"""
    # Пути определяются из переменных окружения, которые уже есть
    DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
    USERS_FILE = DATA_DIR / "users.json"
    BACKUP_DIR = DATA_DIR / "backups" # <-- Бэкапы будут лежать ВНУТРИ /app/data
    
    logger.info(f"[Backup Service] Запускаю проверку бэкапа для {USERS_FILE}...")
    
    if not USERS_FILE.exists():
        logger.warning(f"[Backup Service] Файл {USERS_FILE} не найден. Бэкап пропущен.")
        return
        
    if USERS_FILE.stat().st_size < 10:
         logger.warning(f"[Backup Service] Файл {USERS_FILE} слишком мал (< 10 байт). Бэкап пропущен.")
         return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = BACKUP_DIR / f"users_{timestamp}.json"
    
    try:
        # Папка /app/data/backups будет создана автоматически
        BACKUP_DIR.mkdir(exist_ok=True) 
        shutil.copy(USERS_FILE, backup_path)
        logger.info(f"[Backup Service] ✅ Бэкап успешно создан: {backup_path}")
    except Exception as e:
        logger.error(f"[Backup Service] ❌ НЕ УДАЛОСЬ создать бэкап: {e}")
# --- ⭐️ КОНЕЦ НОВОЙ ФУНКЦИИ ⭐️ ---

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

def get_broadcast_keyboard(context: ContextTypes.DEFAULT_TYPE, lang: str) -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру с реакциями и кнопкой 'Поделиться'."""
    bot_username = context.bot.username or BOT_USERNAME
    share_text = get_text('share_text_template', lang=lang, bot_username=bot_username)
    bot_link = f"https://t.me/{bot_username}"
    encoded_text = urllib.parse.quote_plus(share_text)
    share_url = f"https://t.me/share/url?url={bot_link}&text={encoded_text}"
    
    keyboard = [
        [
            InlineKeyboardButton("👍", callback_data="reaction:like"),
            InlineKeyboardButton("👎", callback_data="reaction:dislike"),
            InlineKeyboardButton(get_text('btn_share', lang=lang), url=share_url)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

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
            
            try:
                # 🐞 v10.13: Проверяем ID-ключ на число
                chat_id = int(chat_id_str)
            except ValueError:
                logger.warning(f"Skipping non-int key '{chat_id_str}' in broadcast job.")
                continue
                
            # 🐞 v10.11: Админ и тестеры получают рассылку всегда,
            # даже если is_demo_expired() (что не должно случиться для них в /stats)
            is_special_user = chat_id in TESTER_USER_IDS or is_admin(chat_id)
            
            if not user_data.get("active"):
                continue
                
            if is_demo_expired(user_data) and not user_data.get("is_paid") and not is_special_user:
                logger.debug(f"Skipping broadcast for {chat_id_str}, demo expired.")
                continue
            
            try:
                # ⭐️ v10.15: Используем часовой пояс пользователя (который он мог изменить)
                user_tz_key = user_data.get("timezone", DEFAULT_TZ_KEY)
                user_tz = ZoneInfo(user_tz_key)
                user_lang = user_data.get("language", DEFAULT_LANG)
                
                lang_specific_phrases = phrases_by_lang.get(user_lang, phrases_by_lang.get(DEFAULT_LANG, []))
                
                if not lang_specific_phrases:
                    continue

                if now_utc.astimezone(user_tz).hour == hour:
                    logger.debug(f"Sending '{key}' to user {chat_id_str} at their local {hour}:00 (TZ: {user_tz_key})")
                    phrase = random.choice(lang_specific_phrases).format(name=user_data.get("name", "друг"))
                    reaction_keyboard = get_broadcast_keyboard(context, user_lang)
                    tasks.append(safe_send(context, chat_id, phrase, reply_markup=reaction_keyboard))
                    
            except ZoneInfoNotFoundError:
                logger.warning(f"Invalid timezone '{user_tz_key}' for user {chat_id_str}. Defaulting to Kiev for this check.")
                user_data["timezone"] = DEFAULT_TZ_KEY # Исправляем невалидный TZ
                if now_utc.astimezone(DEFAULT_TZ).hour == hour:
                    phrase = random.choice(lang_specific_phrases).format(name=user_data.get("name", "друг"))
                    reaction_keyboard = get_broadcast_keyboard(context, user_lang)
                    tasks.append(safe_send(context, chat_id, phrase, reply_markup=reaction_keyboard))
            except Exception as e: 
                logger.error(f"Ошибка в планировщике (broadcast) для {chat_id_str}: {e}")
    
    if tasks:
        results = await asyncio.gather(*tasks)
        if (sent_count := sum(1 for res in results if res)) > 0:
            logger.info(f"📢 Рассылка (broadcast) завершена. Отправлено {sent_count} сообщений.")

async def check_demo_expiry_job(context: ContextTypes.DEFAULT_TYPE):
    """Раз в час проверяет, не истекает ли у кого-то демо, и шлет уведомление."""
    logger.debug("Running check_demo_expiry_job...")
    now_utc = datetime.now(ZoneInfo("UTC"))
    users_data = context.application.bot_data.get("users", {})
    users_to_save = False
    
    for chat_id_str, user_data in users_data.items():
        try:
            # 🐞 v10.13: Проверяем ID-ключ на число
            chat_id = int(chat_id_str)
        except ValueError:
            logger.warning(f"Skipping non-int key '{chat_id_str}' in demo expiry job.")
            continue
        
        # 🐞 v10.11: Игнорируем Админа и Тестеров в этой проверке
        if chat_id == ADMIN_CHAT_ID or chat_id in TESTER_USER_IDS:
            continue
            
        if user_data.get("is_paid") or not user_data.get("active") or user_data.get("sent_expiry_warning"):
            continue
            
        demo_exp_str = user_data.get("demo_expiration")
        if not demo_exp_str:
            continue
            
        try:
            exp_dt = datetime.fromisoformat(demo_exp_str).replace(tzinfo=ZoneInfo("UTC"))
            time_left = exp_dt - now_utc
            
            # 🐞 v10.11: Используем хелпер (хотя для симулятора будет 24ч)
            is_simulator = chat_id in SIMULATOR_USER_IDS
            warning_hours = 24 # Стандарт - 24 часа
            
            # Для симулятора (2 дня демо) и обычных (5 дней демо) 24 часа - ок.
            # Если бы у симулятора было 1-дневное демо, нужна была бы другая логика.
                
            if timedelta(hours=0) < time_left <= timedelta(hours=warning_hours):
                logger.info(f"Demo expiring soon for user {chat_id} (Simulator: {is_simulator}). Sending warning.")
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
    
    # 🐞 v10.11: Тестеры всегда проходят флоу "нового" пользователя,
    # чтобы они могли легко менять язык и сбрасывать демо
    if is_new_user or is_test_user:
        logger.info(f"Поток нового пользователя для {chat_id} (Новый: {is_new_user}, Тестер: {is_test_user})")
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
            # 🐞 v10.11: Используем хелперы
            cooldown_days = get_cooldown_days(chat_id)
            demo_days = get_demo_days(chat_id)
            max_cycles = get_max_demo_cycles(chat_id)
            
            try:
                demo_exp_date = datetime.fromisoformat(user_entry.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
                next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
                
                if now_utc < next_demo_dt:
                    time_left = next_demo_dt - now_utc
                    hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                    minutes_left, _ = divmod(remainder, 60)
                    logger.info(f"Демо для {chat_id} еще на паузе. Осталось: {hours_left}ч {minutes_left}м")
                    await safe_send(context, chat_id, 
                                    get_text('demo_expired_cooldown', lang=user_lang, name=user_name, hours=hours_left, minutes=minutes_left),
                                    reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=True))
                
                else:
                    if demo_count < max_cycles:
                        logger.info(f"Кулдаун для {chat_id} прошел. Предлагаем 2-е демо (счетчик: {demo_count}).")
                        await safe_send(context, chat_id, 
                                        get_text('demo_expired_choice', lang=user_lang, name=user_name, demo_days=demo_days),
                                        reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=True))
                    else:
                        logger.info(f"Демо-циклы ({demo_count}) для {chat_id} закончились. Только оплата.")
                        await safe_send(context, chat_id, 
                                        get_text('demo_expired_final', lang=user_lang, name=user_name),
                                        reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=False))
            except (ValueError, TypeError):
                logger.error(f"Ошибка парсинга demo_expiration для {chat_id}. Показываем опцию оплаты.")
                await safe_send(context, chat_id, 
                                get_text('demo_expired_choice', lang=user_lang, name=user_name, demo_days=demo_days), 
                                reply_markup=get_payment_keyboard(lang=user_lang, is_test_user=is_test_user, show_new_demo=(demo_count < max_cycles)))
        
        else:
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

async def share_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    bot_username = context.bot.username or BOT_USERNAME
    # 🐞 FIX: Такой строки перевода ('share_message') нет, используем 'share_text_template'
    share_text = get_text('share_text_template', lang=lang, bot_username=bot_username)
    
    await safe_send(context, chat_id, share_text)

# --- ⭐️ v10.15: КОМАНДЫ TIMEZONE И GRANT ---
async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup = None):
    """(v10.15) Начинает процесс смены часового пояса."""
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    user_data = context.application.bot_data.get("users", {}).get(str(chat_id))
    
    if not user_data:
        await update.message.reply_text(get_text('start_required', lang=lang))
        return
        
    # Устанавливаем статус, чтобы main_message_handler мог поймать следующий ответ
    user_data["status"] = "awaiting_timezone"
    await save_users(context, context.application.bot_data["users"])
    
    current_tz = user_data.get("timezone", DEFAULT_TZ_KEY)
    
    # Отправляем инструкцию
    await update.message.reply_text(
        get_text('timezone_command_text', lang=lang, user_tz=current_tz),
        parse_mode=ParseMode.HTML
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(v10.15) Отменяет текущее действие, например, ввод часового пояса."""
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    user_data = context.application.bot_data.get("users", {}).get(str(chat_id))
    
    if not user_data:
        return
        
    current_tz = user_data.get("timezone", DEFAULT_TZ_KEY)
    
    if user_data.get("status") == "awaiting_timezone":
        # Сбрасываем статус (неважно, какой он был до этого, /start все равно вернет нужную клаву)
        user_data["status"] = "active_demo" 
        await save_users(context, context.application.bot_data["users"])
        markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
        
        await update.message.reply_text(
            get_text('timezone_cancel', lang=lang, user_tz=current_tz),
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(v10.15) Админ-команда для выдачи Premium-доступа."""
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id) # Язык админа
    
    if not is_admin(chat_id):
        logger.warning(f"НЕ-АДМИН {chat_id} попытался использовать /grant")
        return

    if not context.args:
        await safe_send(context, chat_id, get_text('admin_grant_usage', lang=lang))
        return

    try:
        target_id_str = context.args[0]
        target_id_int = int(target_id_str)
    except (ValueError, IndexError):
        await safe_send(context, chat_id, get_text('admin_grant_usage', lang=lang))
        return

    users_data = context.application.bot_data["users"]
    target_user_data = users_data.get(target_id_str)

    if not target_user_data:
        await safe_send(context, chat_id, get_text('admin_grant_fail_id', lang=lang, user_id=target_id_str))
        return
    
    if target_user_data.get("is_paid"):
        await safe_send(context, chat_id, get_text('admin_grant_fail_already_paid', lang=lang, name=target_user_data.get('name', ''), user_id=target_id_str))
        return
    
    # Активируем Premium
    target_user_data["is_paid"] = True
    target_user_data["status"] = "active_paid" # Меняем статус
    target_user_data["active"] = True # На всякий случай, если был неактивен
    await save_users(context, users_data)
    
    # 1. Уведомляем админа
    await safe_send(context, chat_id, get_text('admin_grant_success', lang=lang, name=target_user_data.get('name', ''), user_id=target_id_str))
    
    # 2. Уведомляем пользователя
    target_lang = target_user_data.get("language", DEFAULT_LANG)
    await safe_send(context, target_id_int, get_text('user_grant_notification', lang=target_lang))
    
    logger.info(f"Админ {chat_id} выдал Premium пользователю {target_id_str}")
# --- ⭐️ КОНЕЦ v10.15 ---

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    user_data = context.application.bot_data["users"].get(str(chat_id), {})
    
    completed_challenges = sum(1 for ch in user_data.get("challenges", []) if ch.get("completed"))
    
    status_key = 'status_premium' if user_data.get('is_paid') else 'status_demo'
    status_text = get_text(status_key, lang=lang)
    
    likes_count = user_data.get("stats_likes", 0)
    dislikes_count = user_data.get("stats_dislikes", 0)
    
    text = (f"{get_text('profile_title', lang=lang)}\n\n"
            f"{get_text('profile_name', lang=lang)}: {user_data.get('name', 'Неизвестно')}\n"
            f"{get_text('profile_status', lang=lang)}: {status_text}\n\n"
            f"<b>📊 Статистика:</b>\n"
            f"{get_text('profile_challenges_accepted', lang=lang)}: {len(user_data.get('challenges', []))}\n"
            f"{get_text('profile_challenges_completed', lang=lang)}: {completed_challenges}\n"
            f"{get_text('profile_challenge_streak', lang=lang)}: {user_data.get('challenge_streak', 0)} 🔥\n"
            f"{get_text('profile_likes', lang=lang)}: {likes_count}\n"
            f"{get_text('profile_dislikes', lang=lang)}: {dislikes_count}")
            
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
    
    async with RULES_LOCK:
        try:
            user_data = context.application.bot_data["users"].get(str(chat_id), {})
            # ⭐️ v10.15: Используем часовой пояс пользователя
            user_tz_key = user_data.get("timezone", DEFAULT_TZ_KEY)
            user_tz = ZoneInfo(user_tz_key)
            today_iso = datetime.now(user_tz).date().isoformat()
            
            last_rules_date = user_data.get("last_rules_date")
            rules_shown_count = user_data.get("rules_shown_count", 0)

            if last_rules_date != today_iso:
                logger.debug(f"New day for rules for user {chat_id}.")
                user_data["last_rules_date"] = today_iso
                user_data["rules_shown_count"] = 0
                rules_shown_count = 0

            if rules_shown_count >= RULES_PER_DAY_LIMIT:
                logger.debug(f"User {chat_id} already received {RULES_PER_DAY_LIMIT} rules today.")
                await safe_send(context, chat_id, get_text('rules_limit_reached', lang=lang), reply_markup=markup)
                return

            data = context.application.bot_data.get("rules", {})
            item_list = data.get(lang, data.get(DEFAULT_LANG, [])) if isinstance(data, dict) else data if isinstance(data, list) else []
            logger.debug(f"Attempting to send rule {rules_shown_count + 1}/{RULES_PER_DAY_LIMIT} for lang '{lang}'. Found {len(item_list)} items.")
            
            if not item_list:
                await safe_send(context, chat_id, get_text('list_empty', lang=lang, title=get_text('title_rules', lang=lang)), reply_markup=markup)
                return
            
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
            
            rules_shown_count += 1
            user_data["rules_shown_count"] = rules_shown_count
            shown_today_indices.append(rule_index)
            user_data["rules_indices_today"] = shown_today_indices
            
            if last_rules_date != today_iso: 
                user_data["rules_indices_today"] = [rule_index]
            
            await save_users(context, context.application.bot_data["users"])
            await safe_send(context, chat_id, text, reply_markup=markup)
        
        except ZoneInfoNotFoundError:
            logger.warning(f"Invalid timezone '{user_tz_key}' for user {chat_id} in send_rules. Defaulting to Kiev.")
            user_data["timezone"] = DEFAULT_TZ_KEY # Исправляем невалидный TZ
            await save_users(context, context.application.bot_data["users"])
            await safe_send(context, chat_id, get_text('list_error_unexpected', lang=lang, title=get_text('title_rules', lang=lang)), reply_markup=markup)
        except Exception as e:
            await safe_send(context, chat_id, get_text('list_error_unexpected', lang=lang, title=get_text('title_rules', lang=lang)), reply_markup=markup)
            logger.exception(f"Unexpected error in send_rules for key 'rules/{lang}':")

async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    logger.debug(f"Challenge command triggered by user {chat_id}")
    
    user_data = context.application.bot_data["users"].get(str(chat_id), {})
    # ⭐️ v10.15: Используем часовой пояс пользователя
    user_tz_key = user_data.get("timezone", DEFAULT_TZ_KEY)
    try:
        user_tz = ZoneInfo(user_tz_key)
    except ZoneInfoNotFoundError:
        logger.warning(f"Invalid timezone '{user_tz_key}' for user {chat_id} in challenge_command. Defaulting to Kiev.")
        user_tz = DEFAULT_TZ
        user_data["timezone"] = DEFAULT_TZ_KEY
    
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
                
                # 🐞 v10.11: Тестеры могут брать челлендж повторно
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
        user_data = users_data.get(str(chat_id), {})
        
        # ⭐️ v10.15: Используем часовой пояс пользователя
        user_tz_key = user_data.get("timezone", DEFAULT_TZ_KEY)
        try:
            user_tz = ZoneInfo(user_tz_key)
        except ZoneInfoNotFoundError:
            user_tz = DEFAULT_TZ
        
        today_iso = datetime.now(user_tz).date().isoformat()
        user_data["last_challenge_date"] = today_iso
        user_data["challenge_accepted"] = False
        users_data[str(chat_id)] = user_data # Убеждаемся, что user_data сохраняется
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
    user_name = context.application.bot_data["users"].get(str(chat_id), {}).get("name", "друг")
    logger.info(f"Sending P2P (Monobank) instructions to user {chat_id}.")
    await safe_send(context, chat_id, get_text('pay_instructions', lang=lang, name=user_name), 
                    disable_web_page_preview=True, reply_markup=markup)

async def handle_pay_api_test(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    """(Для Тестеров) Отправляет ИНСТРУКЦИЮ по P2P-оплате."""
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    user_name = context.application.bot_data["users"].get(str(chat_id), {}).get("name", "друг")
    
    if chat_id not in TESTER_USER_IDS:
        logger.warning(f"Non-tester {chat_id} tried to use test payment.")
        return
        
    logger.info(f"Sending P2P (Monobank) instructions to TESTER {chat_id}.")
    await safe_send(context, chat_id, get_text('pay_instructions', lang=lang, name=user_name), 
                    disable_web_page_preview=True, reply_markup=markup)

async def activate_new_demo(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    users_data = context.application.bot_data.get("users", {})
    user_data = users_data.get(str(chat_id))

    if not user_data:
        logger.warning(f"User {chat_id} trying to activate new demo, but not found.")
        return
        
    # 🐞 v10.11: Используем хелпер
    demo_duration_days = get_demo_days(chat_id)
    logger.info(f"Activating new demo cycle ({user_data.get('demo_count', 0) + 1}) for user {chat_id}.")
    
    user_data["demo_count"] = user_data.get("demo_count", 1) + 1
    user_data["demo_expiration"] = (datetime.now(ZoneInfo("UTC")) + timedelta(days=demo_duration_days)).isoformat()
    user_data["challenge_streak"] = 0
    # user_data["challenges"] = [] # НЕ сбрасываем историю
    user_data["last_challenge_date"] = None
    user_data["last_rules_date"] = None
    user_data["rules_shown_count"] = 0
    user_data["sent_expiry_warning"] = False
    user_data["status"] = "active_demo" # Обновляем статус
    
    await save_users(context, users_data)
    
    new_markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
    await safe_send(context, chat_id, 
                    get_text('welcome_renewed_demo', lang=lang, name=user_data.get("name", "друг"), demo_days=demo_duration_days), 
                    reply_markup=new_markup)

# --- Админские функции ---
async def show_users_file(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    lang = get_user_lang(context, update.effective_chat.id)
    if USERS_FILE.exists() and USERS_FILE.stat().st_size > 2:
        with open(USERS_FILE, "rb") as f:
            await update.message.reply_document(document=f, caption=get_text('users_file_caption', lang=lang), reply_markup=markup)
    else:
        await update.message.reply_text(get_text('users_file_empty', lang=lang), reply_markup=markup)

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    """
    🐞 v10.13: Статистика ПЕРЕПИСАНА + FIX
    1. Админ и Тестеры принудительно считаются "Активными".
    2. Добавлена защита от не-числовых КЛЮЧЕЙ в users.json (try...except ValueError).
    3. ⭐️ v10.14: Убеждаемся, что 'users_data' - это словарь (защита от "сломанного" файла,
       хотя 'load_users_with_fix' уже должен был это исправить).
    """
    chat_id = update.effective_chat.id
    lang = get_user_lang(context, chat_id)
    
    users_data = context.application.bot_data["users"]
    
    # --- ⭐️ v10.14: Дополнительная проверка ---
    if not isinstance(users_data, dict):
        logger.error(f"CRITICAL: users_data is {type(users_data)}, not dict. Cannot generate stats.")
        # Это может случиться, если 'load_users_with_fix' не сработал или был изменен
        await update.message.reply_text("Ошибка: Не удалось прочитать данные пользователей. Структура данных нарушена.", reply_markup=markup)
        return
        
    total = 0
    active = 0
    active_first = 0
    active_repeat = 0
    inactive = 0
    inactive_demo_expired = 0
    inactive_blocked = 0
    
    # "Специальные" пользователи, которых игнорируем в подсчетах неактивных
    special_users = TESTER_USER_IDS.union({ADMIN_CHAT_ID})

    for user_id_str, u in users_data.items():
        if not isinstance(u, dict):
            logger.warning(f"Skipping malformed user data for ID {user_id_str} in stats (not a dict).")
            continue
            
        try:
            # --- 🐞 НОВЫЙ FIX v10.13 ---
            user_id = int(user_id_str)
        except ValueError:
            logger.warning(f"Skipping malformed user ID key '{user_id_str}' in stats (not an int).")
            continue # Пропускаем ключ, если он не-числовой
            # --- --------------------- ---
            
        total += 1
        
        # --- Логика подсчета (v10.11) ---
        is_special = user_id in special_users
        
        if is_special:
            # Админ и Тестеры ВСЕГДА активны
            active += 1
            if u.get("demo_count", 1) > 1:
                active_repeat += 1
            else:
                active_first += 1
            continue
        
        # --- Логика для обычных пользователей ---
        if u.get("active"):
            active += 1
            if u.get("demo_count", 1) > 1:
                active_repeat += 1
            else:
                active_first += 1
        else:
            # Пользователь неактивен
            inactive += 1
            if is_demo_expired(u):
                inactive_demo_expired += 1
            else:
                # Считаем "заблокированным", если 'active'==False, но демо не истек
                inactive_blocked += 1
    
    stats_text = (f"👥 <b>{get_text('profile_status_total', lang=lang)}:</b> {total}\n\n"
                  f"✅ <b>{get_text('profile_status_active', lang=lang)}:</b> {active}\n"
                  f"  - <i>{get_text('profile_status_first_time', lang=lang)}:</i> {active_first}\n"
                  f"  - <i>{get_text('profile_status_repeat', lang=lang)}:</i> {active_repeat}\n\n"
                  f"❌ <b>{get_text('profile_status_inactive', lang=lang)}:</b> {inactive} (Только обычные пользователи)\n"
                  f"  - <i>{get_text('profile_status_demo_expired', lang=lang)}:</i> {inactive_demo_expired}\n"
                  f"  - <i>{get_text('profile_status_blocked', lang=lang)}:</i> {inactive_blocked}")

    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=markup)

# Скрытая команда
async def reload_data(update: Update, context: ContextTypes.DEFAULT_TYPE, markup: ReplyKeyboardMarkup):
    lang = get_user_lang(context, update.effective_chat.id)
    logger.info(f"Admin {update.effective_chat.id} triggered reload_data.")
    await setup_jobs_and_cache(context.application)
    await update.message.reply_text(get_text('reload_confirm', lang=lang), reply_markup=markup)

# --- ⭐️ ИСПРАВЛЕНИЕ 1 (Fix 1) - ЗАМЕНА ВСЕЙ ФУНКЦИИ ⭐️ ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    chat_id = query.from_user.id
    chat_id_str = str(chat_id)
    
    is_new_flow = query.data.endswith("_new")
    
    new_lang = None
    if query.data.startswith("set_lang_"):
        new_lang_code = query.data.split("_")[2]
        if new_lang_code in translations:
            new_lang = new_lang_code
            
    if not new_lang:
        # --- ИСПРАВЛЕНИЕ v10.16.1 ---
        # Убедимся, что context_or_app - это 'context'
        new_lang = get_user_lang(context, chat_id)
        # --- КОНЕЦ ИСПРАВЛЕНИЯ v10.16.1 ---
    
    lang = new_lang
    
    users_data = context.application.bot_data["users"]
    user_data = users_data.get(chat_id_str, {})
    
    if query.data.startswith("reaction:"):
        await query.answer() 
        reaction = query.data.split(":")[-1]
        logger.info(f"Reaction received from {chat_id}: {reaction}")
        
        if reaction == "like":
            user_data["stats_likes"] = user_data.get("stats_likes", 0) + 1
        elif reaction == "dislike":
            user_data["stats_dislikes"] = user_data.get("stats_dislikes", 0) + 1
        await save_users(context, users_data)
        
        await safe_send(context, chat_id, get_text('reaction_received', lang=lang, name=user_data.get("name", "друг")))
        return

    await query.answer()
    logger.info(f"💬 Callback от {chat_id} (lang: {lang}): {query.data}")
    
    data = query.data
    if data.startswith("set_lang_"):
        # 🐞 v10.11: Используем хелпер для определения дней
        demo_duration_days = get_demo_days(chat_id)
        
        user_data["language"] = lang
        
        if is_new_flow:
            user_name = query.from_user.first_name or "друг"
            user_lang_code = query.from_user.language_code
            
            # --- ⭐️ v10.15: АВТОМАТИЧЕСКАЯ УСТАНОВКА TIMEZONE ---
            auto_tz_key = get_tz_from_lang(user_lang_code)
            user_data["timezone"] = auto_tz_key
            # --- ⭐️ КОНЕЦ v10.15 ---
            
            user_data["id"] = chat_id
            user_data["name"] = user_name
            user_data["active"] = True
            user_data["demo_count"] = 1
            user_data["challenge_streak"] = 0
            user_data["challenges"] = []
            user_data["last_challenge_date"] = None
            user_data["last_rules_date"] = None
            user_data["rules_shown_count"] = 0 
            user_data["sent_expiry_warning"] = False
            user_data["is_paid"] = False 
            user_data["stats_likes"] = 0
            user_data["stats_dislikes"] = 0
            user_data["status"] = "active_demo" # ✅ НОВЫЙ СТАТУС
            user_data["demo_expiration"] = (datetime.now(ZoneInfo("UTC")) + timedelta(days=demo_duration_days)).isoformat()
            
            logger.info(f"👤 Пользователь {chat_id} зарегистрирован/обновлен с языком {lang}. Демо: {demo_duration_days} дней. Auto-TZ: {auto_tz_key} (based on {user_lang_code})")
            
            # 🐞 v10.11: Не шлем админу уведомление о Тестерах или Симуляторах
            is_test_user = chat_id in TESTER_USER_IDS
            is_simulator = chat_id in SIMULATOR_USER_IDS
            
            if chat_id != ADMIN_CHAT_ID and not is_test_user and not is_simulator and user_data["demo_count"] == 1:
                # --- ИСПРАВЛЕНИЕ v10.16.1 ---
                admin_lang = get_user_lang(context, ADMIN_CHAT_ID)
                # --- КОНЕЦ ИСПРАВЛЕНИЯ v10.16.1 ---
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
            # --- ⭐️ v10.15: Добавляем P.S. про АВТО-часовой пояс ---
            welcome_text = get_text('welcome', lang=lang, name=user_data.get("name"), demo_days=demo_duration_days)
            welcome_text += get_text('welcome_timezone_note', lang=lang, default_tz=user_data.get("timezone", DEFAULT_TZ_KEY))
            
            # --- ⭐️ ИСПРАВЛЕНИЕ 1 (Fix 1) - УБРАН 'parse_mode' ⭐️ ---
            # Эта строка вызывала TypeError, т.к. safe_send УЖЕ содержит parse_mode
            await safe_send(context, chat_id, welcome_text, reply_markup=markup)
            # --- ⭐️ КОНЕЦ ИСПРАВЛЕНИЯ 1 ⭐️ ---
            
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

                if current_streak == 3:
                    await safe_send(context, chat_id, get_text('challenge_streak_3_level_1', lang=lang, name=user_data.get("name", "друг")))
            
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

# --- ⭐️ v10.15: ГЛАВНЫЙ ДИСПЕТЧЕР (ПОЛНОСТЬЮ ЗАМЕНЕН) ⭐️ ---
async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text, chat_id = update.message.text, update.effective_chat.id
    chat_id_str = str(chat_id)
    
    users_data = context.application.bot_data.get("users", {})
    user_data = users_data.get(chat_id_str)
    
    if user_data:
        new_name = update.message.from_user.first_name or "друг"
        if user_data.get("name") != new_name:
            logger.info(f"Updating name for user {chat_id}: from '{user_data.get('name')}' to '{new_name}'")
            user_data["name"] = new_name
            await save_users(context, users_data) # <--- Здесь УЖЕ БЫЛ ПРАВИЛЬНЫЙ ФИКС (v10.13)
    
    lang = get_user_lang(context, chat_id)
    logger.debug(f"Received message from {chat_id} (lang: {lang}): '{text}'")
    
    if not user_data:
        logger.warning(f"User {chat_id} not found in bot_data. Asking to /start.")
        await update.message.reply_text(get_text('start_required', lang=DEFAULT_LANG))
        return

    # --- ⏰ НОВЫЙ БЛОК ДЛЯ TIMEZONE ⏰ ---
    if user_data.get("status") == "awaiting_timezone":
        
        # Проверяем на команду отмены
        if text.lower() == "/cancel" or text == get_text('cmd_cancel', lang=lang):
            user_data["status"] = "active_demo" # (или is_paid)
            await save_users(context, users_data)
            markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
            current_tz = user_data.get("timezone", DEFAULT_TZ_KEY)
            await update.message.reply_text(
                get_text('timezone_cancel', lang=lang, user_tz=current_tz),
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
            return

        try:
            # Пытаемся распознать часовой пояс
            new_tz = ZoneInfo(text)
            user_data["timezone"] = new_tz.key
            user_data["status"] = "active_demo" # (или is_paid)
            await save_users(context, users_data)
            
            markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
            await update.message.reply_text(
                get_text('timezone_set_success', lang=lang, new_tz=new_tz.key),
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
            logger.info(f"User {chat_id} changed timezone to {new_tz.key}")
            
        except ZoneInfoNotFoundError: # ⭐️ v10.15: Уточнили тип ошибки
            # Невалидный пояс
            logger.warning(f"User {chat_id} sent invalid timezone: '{text}'")
            await update.message.reply_text(
                get_text('timezone_set_error', lang=lang, error_text=text),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Unexpected error in timezone handler for {chat_id}: {e}")
            await update.message.reply_text(
                get_text('timezone_set_error', lang=lang, error_text=text),
                parse_mode=ParseMode.HTML
            )
        return # Важно, чтобы выйти из хендлера
    # --- ⏰ КОНЕЦ НОВОГО БЛОКА ⏰ ---
        
    is_user_admin = is_admin(chat_id)
    is_test_user = chat_id in TESTER_USER_IDS
    
    markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
    
    is_special_user = is_user_admin or is_test_user
    if is_demo_expired(user_data) and not user_data.get("is_paid") and not is_special_user:
        logger.info(f"Demo expired for user {chat_id}. Checking access...")
        
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            demo_exp_date = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
            
            cooldown_days = get_cooldown_days(chat_id)
            demo_days = get_demo_days(chat_id)
            max_cycles = get_max_demo_cycles(chat_id)
            
            next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
            demo_count = user_data.get("demo_count", 1)

            if text == get_btn_text('pay_api_test_premium', lang) and is_test_user:
                await handle_pay_api_test(update, context, markup=markup)
                return
            elif text == get_btn_text('pay_premium', lang) and not is_test_user:
                await handle_pay_real(update, context, markup=markup)
                return
            elif text == get_btn_text('want_demo', lang):
                if now_utc < next_demo_dt:
                    user_data["status"] = "awaiting_renewal"
                    await save_users(context, users_data) # <--- Здесь УЖЕ БЫЛ ПРАВИЛЬНЫЙ ФИКС (v10.13)
                    new_markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
                    time_left = next_demo_dt - now_utc
                    hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                    minutes_left, _ = divmod(remainder, 60)
                    await safe_send(context, chat_id, get_text('demo_awaiting_renewal', lang=lang, name=user_data.get("name", "друг"), hours=hours_left, minutes=minutes_left), reply_markup=new_markup)
                else:
                    await activate_new_demo(update, context, markup=markup)
                return
            
            if user_data.get("status") == "awaiting_renewal":
                time_left = next_demo_dt - now_utc
                hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes_left, _ = divmod(remainder, 60)
                await safe_send(context, chat_id, get_text('demo_awaiting_renewal', lang=lang, name=user_data.get("name", "друг"), hours=hours_left, minutes=minutes_left), reply_markup=markup)
            
            elif now_utc < next_demo_dt: 
                time_left = next_demo_dt - now_utc
                hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes_left, _ = divmod(remainder, 60)
                await safe_send(context, chat_id, get_text('demo_expired_cooldown', lang=lang, name=user_data.get("name", "друг"), hours=hours_left, minutes=minutes_left), reply_markup=markup)
            
            else: 
                if demo_count < max_cycles:
                    await safe_send(context, chat_id, get_text('demo_expired_choice', lang=lang, name=user_data.get("name", "друг"), demo_days=demo_days), reply_markup=markup)
                else:
                    await safe_send(context, chat_id, get_text('demo_expired_final', lang=lang, name=user_data.get("name", "друг")), reply_markup=markup)
        
        except Exception as e:
            logger.error(f"Критическая ошибка в demo_expired_handler: {e}")
            await safe_send(context, chat_id, get_text('demo_expired_final', lang=lang, name=user_data.get("name", "друг")), reply_markup=markup)
        return
    
    # --- Пользователь активен (демо/премиум/админ/тестер) ---
    all_handlers = {
        get_btn_text('motivate', lang): send_motivation,
        get_btn_text('rhythm', lang): send_rhythm,
        get_btn_text('rules', lang): send_rules,
        get_btn_text('challenge', lang): challenge_command,
        get_btn_text('profile', lang): profile_command,
        # get_btn_text('settings', lang): timezone_command, # <--- ⭐️ v10.15 Убрано
        get_btn_text('stats', lang): user_stats,
        get_btn_text('show_users', lang): show_users_file,
        get_btn_text('reload_data', lang): reload_data,
        get_btn_text('pay_api_test_premium', lang): handle_pay_api_test,
        get_btn_text('pay_premium', lang): handle_pay_real,
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

# --- ⭐️ ИСПРАВЛЕНИЕ 2 (Fix 2) - ЗАМЕНА ВСЕЙ ФУНКЦИИ ⭐️ ---
async def setup_jobs_and_cache(app: Application):
    """
    Загружает весь кэш (файлы JSON) в bot_data и настраивает 
    основные фоновые задачи (JobQueue).
    """
    try:
        # --- ⭐️ FIX v10.14: Вызываем функцию с "лечением" ---
        app.bot_data["users"] = load_users_with_fix()
        # --- ⭐️ КОНЕЦ ФИКСА v10.14 ---
        
        logger.info(f"👥 Загружено {len(app.bot_data['users'])} пользователей")

        # Загружаем остальные JSON-файлы в кэш
        for key, filename in FILE_MAPPING.items():
            filepath = DATA_DIR / filename
            data = load_json_data(filepath)
            app.bot_data[key] = data
            size_info = len(data) if isinstance(data, (list, dict)) else 'N/A'
            logger.info(f"  -> {filename}: {size_info} записей/ключей (Type: {type(data).__name__})")
            
        # Загружаем все челленджи
        load_all_challenges_into_cache(app)
        logger.info("📚 Кэш статических данных загружен")

        # Очищаем старые задачи, если они есть (важно для перезапуска)
        if app.job_queue:
            for job in app.job_queue.jobs():
                job.schedule_removal()
                logger.debug(f"Удалена job: {job}")

        # Настраиваем основные рассылки
        now = datetime.now(DEFAULT_TZ)
        # Запускаем в начале следующего часа
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        app.job_queue.run_repeating(centralized_broadcast_job, interval=timedelta(hours=1), first=next_hour)
        logger.info(f"✅ Планировщик (broadcast) настроен! Первая рассылка в: {next_hour.isoformat()}")
        
        # Настраиваем проверку истечения демо
        app.job_queue.run_repeating(check_demo_expiry_job, interval=timedelta(hours=1), first=now + timedelta(minutes=2))
        logger.info(f"✅ Планировщик (demo expiry) настроен! Первая проверка в: {(now + timedelta(minutes=2)).isoformat()}")
        
        # --- ⭐️ ИСПРАВЛЕНИЕ 2 (Fix 2) - ДОБАВЛЕН 'backup' ⭐️ ---
        app.job_queue.run_repeating(backup, interval=timedelta(hours=6), first=now + timedelta(minutes=5))
        logger.info(f"✅ Планировщик (Backup) настроен! Первый бэкап через 5 минут.")
        # --- ⭐️ КОНЕЦ ИСПРАВЛЕНИЯ 2 ⭐️ ---
        
    except Exception as e:
        logger.error(f"❌ Ошибка в setup_jobs_and_cache: {e}")
        logger.exception("Полный traceback для setup_jobs_and_cache:")
        raise
# --- ⭐️ КОНЕЦ ФУНКЦИИ 'setup_jobs_and_cache' ⭐️ ---


# --- Инициализация Application и добавление обработчиков ---
application = ApplicationBuilder().token(BOT_TOKEN).build()

# 1. Команды
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("pay", pay_command))
application.add_handler(CommandHandler("language", language_command))
application.add_handler(CommandHandler("share", share_command))

# --- ⭐️ FIX v10.15: Добавляем /grant, /timezone, /cancel ---
application.add_handler(CommandHandler("timezone", timezone_command))
application.add_handler(CommandHandler("cancel", cancel_command))
application.add_handler(CommandHandler("grant", grant_command))
# --- ⭐️ КОНЕЦ ФИКСА v10.15 ---

# 2. Обработчик всех текстовых сообщений (кнопки и ввод timezone)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))

# 3. Обработчик всех нажатий на инлайн-кнопки (реакции, челленджи)
application.add_handler(CallbackQueryHandler(handle_callback_query))


# --- Управление жизненным циклом FastAPI (Lifespan) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляет запуском и остановкой бота при старте/остановке веб-сервера.
    """
    startup_error = None
    try:
        # Проверки перед запуском
        if not BOT_TOKEN:
            startup_error = "BOT_TOKEN не задан!"
        elif not ADMIN_CHAT_ID or ADMIN_CHAT_ID == 0:
            startup_error = "ADMIN_CHAT_ID не задан!"
        
        if startup_error:
            logger.critical(f"❌ {startup_error} Бот не запустится.")
            yield; return # Завершаем, не запуская бота

        logger.debug("Lifespan: Starting initialization...")
        setup_initial_files()
        await application.initialize()
        await setup_jobs_and_cache(application) # <--- Вызов нашей функции с фиксом
        await application.start()
        logger.debug("Lifespan: Application started.")
        
        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL}/telegram/{BOT_TOKEN}"
            await application.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook установлен.")
        else:
            logger.info("⚠️ WEBHOOK_URL не задан — используется polling (локально).")

        # Уведомляем админа о старте
        admin_lang = get_user_lang(application, ADMIN_CHAT_ID)
        await application.bot.send_message(ADMIN_CHAT_ID, get_text('admin_bot_started', lang=admin_lang))
        logger.info("✅ Lifespan: Бот полностью запущен и готов к работе.")

        # --- Yield ---
        yield # <--- FastAPI (Uvicorn) будет работать здесь
        # --- Yield ---

    except Exception as e:
        # Эта ошибка произошла ВО ВРЕМЯ ЗАПУСКА
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ: {e}")
        logger.exception("Полный traceback ошибки запуска:")
        if ADMIN_CHAT_ID != 0:
            try:
                # Убедимся, что бот инициализирован для отправки
                if not application.bot:
                    await application.initialize()
                await application.bot.send_message(ADMIN_CHAT_ID, f"❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ: {e}")
            except Exception as e_admin:
                logger.error(f"Не удалось отправить админу сообщение об ошибке запуска: {e_admin}")
        
        # Все равно yield, чтобы FastAPI мог завершиться,
        # хотя бот, скорее всего, не будет работать
        yield

    finally:
        # --- Shutdown ---
        logger.info("⏳ Lifespan: Начинается остановка бота...")
        admin_lang = get_user_lang(application, ADMIN_CHAT_ID)
        
        try:
            if ADMIN_CHAT_ID != 0 and application.bot and application.is_running:
                    await application.bot.send_message(ADMIN_CHAT_ID, get_text('admin_bot_stopping', lang=admin_lang))
        except Exception as e:
            logger.error(f"Не удалось отправить админу сообщение об остановке: {e}")

        if application.job_queue:
            application.job_queue.stop()
            logger.info("Планировщик остановлен.")

        if application.is_running:
            await application.stop()
            logger.info("Application (polling/webhook) остановлен.")
        
        await application.shutdown()
        logger.info("Application (соединения) выключен.")
        logger.info("👋 Бот выключен.")

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "FotiniaBot v10.16.1 is alive"}

@app.post("/telegram/{token}")
async def webhook(request: Request, token: str):
    """
    Основной вебхук-энтрипоинт.
    """
    if token != BOT_TOKEN:
        logger.warning(f"Invalid token received: {token[:5]}...")
        return {"status": "error", "message": "Invalid token"}, 403

    try:
        update_data = await request.json()
        update = Update.de_json(update_data, application.bot)
        logger.debug(f"Webhook: Получен update {update.update_id}")

        # Передаем управление в python-telegram-bot
        await application.process_update(update)

        return {"status": "ok"}
    except json.JSONDecodeError:
        logger.error("Webhook: Не удалось декодировать JSON.")
        return {"status": "error", "message

logger.error("Webhook: Не удалось декодировать JSON.")
        return {"status": "error", "message": "Invalid JSON"}, 400
    except Exception as e:
        logger.error(f"Webhook: Ошибка обработки update: {e}")
        logger.exception("Полный traceback ошибки webhook:")
        return {"status": "error", "message": "Internal server error"}, 500

# --- Запуск (для локальной отладки) ---
if __name__ == "__main__":
    # Этот блок НЕ будет выполняться при запуске через Uvicorn/Gunicorn
    logger.info("Запуск в режиме polling (локальная отладка)...")
    
    # Настраиваем все вручную, так как lifespan не вызывается
    setup_initial_files()
    asyncio.run(application.initialize())
    asyncio.run(setup_jobs_and_cache(application))
    
    # Запускаем polling
    logger.info("...Начинаю polling...")
    application.run_polling()
    logger.info("...Polling завершен.")

"""
Конец файла
"""


