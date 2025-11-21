import logging
from typing import Dict, TypeVar
from config import settings

# Тип для языка
Lang = TypeVar("Lang", bound=str)

logger = logging.getLogger('FotiniaBot')

# --- Словарь с текстами ---
LOCALIZATION: Dict[str, Dict[Lang, str]] = {}

def load_localization():
    """Загружает локализацию."""
    global LOCALIZATION
    LOCALIZATION = {
        # --- Общие тексты ---
        "welcome_new": {
            "ru": "Привет, {name}! Я Fotinia, твой личный мотиватор.\n\nЯ подготовила для тебя бесплатный демо-период.",
            "ua": "Привіт, {name}! Я Fotinia, твій особистий мотиватор.\n\nЯ підготувала для тебе безкоштовний демо-період.",
            "en": "Hello, {name}! I am Fotinia, your personal motivator.\n\nI have prepared a free demo period for you.",
        },
        "greetings_back": {
            "ru": "С возвращением, {name}! Выбирай, что тебе нужно сейчас. 👇",
            "ua": "З поверненням, {name}! Обирай, що тобі потрібно зараз. 👇",
            "en": "Welcome back, {name}! Choose what you need right now. 👇",
        },
        "admin_bot_started": {
            "ru": "✅ Бот успешно запущен и вебхук установлен.",
            "ua": "✅ Бот успішно запущений і вебхук встановлено.",
            "en": "✅ Bot successfully started and webhook is set.",
        },
        "settings_menu_text": {
            "ru": "⚙️ <b>Настройки</b>\n\nВыберите, что хотите изменить:",
            "ua": "⚙️ <b>Налаштування</b>\n\nОберіть, що бажаєте змінити:",
            "en": "⚙️ <b>Settings</b>\n\nChoose what you want to change:",
        },
        "cancel_no_action": {
            "ru": "Отменять нечего. Возвращаемся в главное меню.",
            "ua": "Нічого скасовувати. Повертаємось до головного меню.",
            "en": "Nothing to cancel. Returning to the main menu.",
        },
        "cancel_success": {
            "ru": "Действие отменено. Возвращаемся в главное меню.",
            "ua": "Дію скасовано. Повертаємось до головного меню.",
            "en": "Action cancelled. Returning to the main menu.",
        },
        "stats_info_user": {
            "ru": "📊 Ваша статистика доступна в Профиле (👤 Профиль).",
            "ua": "📊 Ваша статистика доступна у Профілі (👤 Профіль).",
            "en": "📊 Your statistics are available in the Profile (👤 Profile).",
        },
        # --- Кнопки ---
        "cmd_cancel": {"ru": "❌ Отмена", "ua": "❌ Скасувати", "en": "❌ Cancel"},
        "btn_pay_premium": {"ru": "💎 Купить Premium", "ua": "💎 Купити Premium", "en": "💎 Buy Premium"},
        "btn_pay_api_test_premium": {"ru": "💳 Тест API Premium", "ua": "💳 Тест API Premium", "en": "💳 Test API Premium"},
        "btn_want_demo": {"ru": "Хочу еще демо", "ua": "Хочу ще демо", "en": "I want another demo"},
        "btn_settings": {"ru": "⚙️ Настройки", "ua": "⚙️ Налаштування", "en": "⚙️ Settings"},
    }
    logger.info("✅ Localization loaded.")

def t(key: str, lang: str = "ru", **kwargs) -> str:
    """Возвращает переведенный текст по ключу."""
    lang = lang.lower() if lang else "ru"
    if key in LOCALIZATION:
        text = LOCALIZATION[key].get(lang, LOCALIZATION[key].get("ru", key))
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return key

# Загружаем сразу при импорте
load_localization()