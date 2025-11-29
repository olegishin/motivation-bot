# 04 - bot/keyboards.py
# Reply и Inline клавиатуры

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import Dict, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote 

# ✅ ИСПРАВЛЕНО: Абсолютные импорты для надежности
from bot.localization import t, Lang
from bot.config import settings
from bot.utils import is_admin, is_demo_expired, get_cooldown_days, get_max_demo_cycles

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
        KeyboardButton(text=t('btn_settings', lang))
    )
    return builder.as_markup(resize_keyboard=True)


def get_admin_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    """Клавиатура Админа (с кнопками Статистики и Юзеров)"""
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
        KeyboardButton(text=t('btn_settings', lang)),
        KeyboardButton(text=t('btn_stats', lang)),
        # ✅ Кнопка "Юзеры" (Показать users.json)
        KeyboardButton(text=t('btn_show_users', lang)) 
    )
    builder.row(KeyboardButton(text=t('btn_profile', lang)))
    
    # Сетка кнопок: 2, 2, 3, 1
    builder.adjust(2, 2, 3, 1) 
    return builder.as_markup(resize_keyboard=True)


def get_settings_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    """
    Клавиатура настроек (Выбор языка).
    """
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🇺🇦 Українська"),
        KeyboardButton(text="🇬🇧 English"),
        KeyboardButton(text="🇷🇺 Русский")
    )
    builder.row(KeyboardButton(text=t('btn_back', lang)))
    return builder.as_markup(resize_keyboard=True)


def get_payment_keyboard(lang: Lang, is_test_user: bool = False, show_new_demo: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура оплаты / продления.
    """
    kb = InlineKeyboardBuilder()

    if show_new_demo:
        kb.button(text=t('btn_want_demo', lang), callback_data="activate_demo")

    if is_test_user:
        kb.button(text="💳 Test Pay", callback_data="test_payment_success")
    else:
        # Здесь можно поставить ссылку на оплату
        kb.button(text=t('btn_pay_premium', lang), url="https://t.me/Oleg_K")
        
    kb.adjust(1)
    return kb.as_markup()


def get_cooldown_keyboard(lang: Lang, is_test_user: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для режима ожидания (Inline)"""
    kb = InlineKeyboardBuilder()
    if is_test_user:
        kb.button(text="⚡ Skip Wait (Test)", callback_data="activate_demo")
    
    kb.button(text=t('btn_profile', lang), callback_data="nav_profile")
    return kb.as_markup()


def get_reply_keyboard_for_user(chat_id: int, lang: Lang, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    """Главная функция выбора клавиатуры"""
    if is_admin(chat_id):
        return get_admin_keyboard(lang)

    if user_data.get("is_paid"):
        return get_main_keyboard(lang)

    # Логика демо оставлена как у тебя была
    return get_main_keyboard(lang)


# -------------------------------------------------
# 2. Inline-клавиатуры (в сообщениях)
# -------------------------------------------------
def get_lang_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка при /start."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Українська 🇺🇦", callback_data="set_lang_ua_new")
    builder.button(text="English 🇬🇧", callback_data="set_lang_en_new")
    builder.button(text="Русский 🇷🇺", callback_data="set_lang_ru_new")
    builder.adjust(1)
    return builder.as_markup()


def get_broadcast_keyboard(lang: Lang, quote_text: str | None = None, category: str = "affirmation", user_name: str = "Друг") -> InlineKeyboardMarkup:
    """
    Генерирует инлайн-клавиатуру для контента.
    🔥 ИСПРАВЛЕНО: Убран длинный дублирующийся текст при шаринге.
    """
    builder = InlineKeyboardBuilder()
    
    # Лайки
    builder.button(text="👍", callback_data="reaction:like")
    builder.button(text="👎", callback_data="reaction:dislike")
    
    # Кнопка Поделиться (кроме категорий челлендж/мотивация/ритм, если не нужно)
    # Но в твоем случае ты хочешь делиться мотивацией, поэтому оставляем логику:
    # Исключаем только если это технически невозможно, но для текста всегда можно.
    excluded_categories = ["challenge"] # Челленджи обычно динамические, их сложно шарить текстом, но можно
    
    if category not in excluded_categories:
        if quote_text:
            # ✅ ИСПРАВЛЕНО: Краткий и четкий текст без "цветка" и дублей
            share_msg = (
                f"Посмотри, какое сообщение сегодня прислал мне мой бот:\n\n"
                f"«{quote_text}»\n\n"
                "Попробуй и ты, это интересно :-)\n"
                "@FotiniaBot"
            )
        else:
            share_msg = (
                "Посмотри, какой бот мне помогает двигаться к цели!\n"
                "Попробуй и ты, это интересно :-)\n"
                "@FotiniaBot"
            )

        share_url = f"https://t.me/share/url?url={quote('https://t.me/FotiniaBot')}&text={quote(share_msg)}"
        
        # Берем текст кнопки из переводов или ставим дефолтный
        btn_text = t('btn_share', lang)
        if btn_text == 'btn_share': btn_text = "Поделиться ✨"
            
        builder.button(text=btn_text, url=share_url)
        
        # 2 кнопки в ряд (лайки), 1 снизу (поделиться)
        builder.adjust(2, 1)
    else:
        # Только лайки
        builder.adjust(2)
    
    return builder.as_markup()

# Для совместимости (если где-то еще вызывается)
def get_main_menu_kb(lang: Lang) -> ReplyKeyboardMarkup:
    return get_main_keyboard(lang)