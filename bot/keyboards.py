# 3 - bot/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import Dict, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import urllib.parse
from localization import t, Lang
from config import settings, DEFAULT_TZ


# -------------------------------------------------
# 1. Reply-клавиатуры (под чатом)
# -------------------------------------------------
def get_main_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    """Обычная клавиатура (Демо или Premium)"""
    builder = ReplyKeyboardBuilder()

    # 1 ряд: Мотивация + Ритм
    builder.row(
        KeyboardButton(text=t('btn_motivate', lang)),
        KeyboardButton(text=t('btn_rhythm', lang))
    )
    # 2 ряд: Челлендж + Правила
    builder.row(
        KeyboardButton(text=t('btn_challenge', lang)),
        KeyboardButton(text=t('btn_rules', lang))
    )
    # 3 ряд: Профиль + Настройки
    builder.row(
        KeyboardButton(text=t('btn_profile', lang)),
        KeyboardButton(text=t('btn_settings', lang))  # Настройки
    )
    return builder.as_markup(resize_keyboard=True)


def get_admin_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    """Клавиатура Админа"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=t('btn_motivate', lang)),
        KeyboardButton(text=t('btn_rhythm', lang))
    )
    builder.row(
        KeyboardButton(text=t('btn_challenge', lang)),
        KeyboardButton(text=t('btn_rules', lang))
    )
    builder.row(
        KeyboardButton(text=t('btn_settings', lang)),  # Вместо users.json
        KeyboardButton(text=t('btn_stats', lang))
    )
    builder.row(KeyboardButton(text=t('btn_profile', lang)))
    return builder.as_markup(resize_keyboard=True)


def get_settings_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    """Клавиатура настроек (Выбор языка)"""
    builder = ReplyKeyboardBuilder()
    # Кнопки смены языка
    builder.row(
        KeyboardButton(text="Українська"),
        KeyboardButton(text="English"),
        KeyboardButton(text="Русский")
    )
    # Кнопка Назад
    builder.row(KeyboardButton(text=t('btn_back', lang)))
    return builder.as_markup(resize_keyboard=True)


def get_payment_keyboard(lang: Lang, is_test_user: bool = False, show_new_demo: bool = False) -> ReplyKeyboardMarkup:
    """Клавиатура, когда демо истек, но кулдаун прошел."""
    builder = ReplyKeyboardBuilder()

    if is_test_user:
        builder.button(text=t('btn_pay_api_test_premium', lang))
    else:
        builder.button(text=t('btn_pay_premium', lang))

    if show_new_demo:
        builder.button(text=t('btn_want_demo', lang))

    builder.adjust(2 if show_new_demo else 1)
    return builder.as_markup(resize_keyboard=True)


def get_cooldown_keyboard(lang: Lang, is_test_user: bool = False) -> ReplyKeyboardMarkup:
    """Клавиатура, когда демо истек И идет кулдаун."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=t('btn_motivate', lang)),
        KeyboardButton(text=t('btn_rhythm', lang))
    )
    builder.row(
        KeyboardButton(text=t('btn_challenge', lang)),
        KeyboardButton(text=t('btn_rules', lang))
    )
    builder.row(KeyboardButton(text=t('btn_profile', lang)))

    if is_test_user:
        builder.row(KeyboardButton(text=t('btn_pay_api_test_premium', lang)))
    else:
        builder.row(KeyboardButton(text=t('btn_pay_premium', lang)))

    return builder.as_markup(resize_keyboard=True)


def get_reply_keyboard_for_user(chat_id: int, lang: Lang, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    """
    Главная функция, определяющая, какую Reply-клавиатуру показать пользователю.
    """
    from utils import is_admin, is_demo_expired, get_cooldown_days, get_max_demo_cycles

    if is_admin(chat_id):
        return get_admin_keyboard(lang)

    if user_data.get("is_paid"):
        return get_main_keyboard(lang)

    is_test_user = chat_id in settings.TESTER_USER_IDS

    if is_demo_expired(user_data):
        demo_count = user_data.get("demo_count", 1)

        if user_data.get("status") == "awaiting_renewal":
            return get_cooldown_keyboard(lang, is_test_user)

        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            exp_dt = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))

            cooldown_days = get_cooldown_days(chat_id)
            max_cycles = get_max_demo_cycles(chat_id)
            next_demo_dt = exp_dt + timedelta(days=cooldown_days)

            if now_utc >= next_demo_dt:
                show_demo_button = (demo_count < max_cycles)
                return get_payment_keyboard(lang, is_test_user, show_new_demo=show_demo_button)
            else:
                return get_payment_keyboard(lang, is_test_user, show_new_demo=False)

        except Exception:
            max_cycles = get_max_demo_cycles(chat_id)
            return get_payment_keyboard(lang, is_test_user, show_new_demo=(demo_count < max_cycles))

    # Если демо активно
    return get_main_keyboard(lang)


# -------------------------------------------------
# 2. Inline-клавиатуры (в сообщениях)
# -------------------------------------------------
def get_lang_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка при /start."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Українська", callback_data="set_lang_ua_new")
    builder.button(text="English", callback_data="set_lang_en_new")
    builder.button(text="Русский", callback_data="set_lang_ru_new")
    builder.adjust(1)
    return builder.as_markup()


def get_broadcast_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    """Клавиатура для рассылок (Лайк/Дизлайк/Поделиться)."""
    bot_link = f"https://t.me/{settings.BOT_USERNAME}"
    share_text = t('share_text_template', lang, bot_username=settings.BOT_USERNAME)
    encoded_text = urllib.parse.quote_plus(share_text)
    share_url = f"https://t.me/share/url?url={bot_link}&text={encoded_text}"
    builder = InlineKeyboardBuilder()
    builder.button(text="Like", callback_data="reaction:like")
    builder.button(text="Dislike", callback_data="reaction:dislike")
    builder.button(text=t('btn_share', lang), url=share_url)
    builder.adjust(3)
    return builder.as_markup()


# -------------------------------------------------
# Добавленная функция, которую импортирует button_handlers.py
# -------------------------------------------------
def get_main_menu_kb(lang: Lang) -> ReplyKeyboardMarkup:
    """
    Основная клавиатура меню (аналог get_main_keyboard).
    Импортируется в button_handlers.py как `get_main_menu_kb`.
    """
    return get_main_keyboard(lang)