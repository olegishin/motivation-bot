# 04 - bot/keyboards.py
# Поддержка ✅ на кнопках и классическая логика цитирования
# Исправленная версия: поддержка галочек ✅ и аргумента user_name
# Поддержка ✅ на кнопках и логика WebApp профиля
# (ФИНАЛЬНАЯ ВЕРСИЯ: Ссылка на оплату берется из конфига)
# Поддержка ✅ на кнопках и классическая логика цитирования
# ФИНАЛЬНАЯ ВЕРСИЯ: Исправлен порядок текста в кнопке "Поделиться" (Призыв первым)
# ПОЛНАЯ СВЕРКА: Сохранены WebApp, логика админа и поддержка галочек реакций
# Поддержка ✅ на кнопках и классическая логика цитирования
# ФИНАЛЬНАЯ ВЕРСИЯ: Исправлен порядок текста в кнопке "Поделиться" (2026-01-14)
# FIX: Внедрена обрезка цитаты до 300 знаков для гарантированной работы кнопки
# Поддержка ✅ на кнопках и классическая логика цитирования
# ФИНАЛЬНАЯ ВЕРСИЯ: Исправлен порядок текста в кнопке "Поделиться" (2026-01-14)
# FIX: Улучшена работа кнопки "Поделиться" (удален лишний url= параметр, оставлен только text=)
# ПОЛНАЯ СВЕРКА: Сохранены WebApp, логика админа и поддержка галочек реакций
# Поддержка ✅ на кнопках и классическая логика цитирования
# ФИНАЛЬНАЯ ВЕРСИЯ: Исправлен порядок текста в кнопке "Поделиться" (2026-01-14)
# ПОЛНАЯ СВЕРКА: Сохранены WebApp, логика админа, поддержка ✅ и аргумент user_name
# ФАЙЛ ВЫДАН ЦЕЛИКОМ ДЛЯ ЗАМЕНЫ
# Поддержка ✅ на кнопках и классическая логика цитирования
# ФИНАЛЬНАЯ ВЕРСИЯ: Исправлен порядок текста в кнопке "Поделиться" (2026-01-14)
# ПОЛНАЯ СВЕРКА: Сохранены WebApp, логика админа, поддержка ✅ и аргумент user_name
# FIX: Восстановлена корректная проверка ADMIN_CHAT_ID
# 04 - bot/keyboards.py
# Поддержка ✅ на кнопках и классическая логика цитирования
# Исправленная версия: поддержка галочек ✅ и аргумента user_name
# Поддержка ✅ на кнопках и логика WebApp профиля
# (ФИНАЛЬНАЯ ВЕРСИЯ: Ссылка на оплату берется из конфига)
# 04 - bot/keyboards.py
# Поддержка ✅ на кнопках и классическая логика цитирования
# Исправленная версия: поддержка галочек ✅ и аргумента user_name
# Поддержка ✅ на кнопках и логика WebApp профиля
# (ФИНАЛЬНАЯ ВЕРСИЯ: Ссылка на оплату берется из конфига)
# FIX: Меню теперь всегда развернуто (is_persistent=True во всех Reply-клавиатурах)
# 04 - bot/keyboards.py
# ULTIMATE VERSION: Fixed persistent menu + Share logic + Admin Fix
# ПОЛНАЯ СВЕРКА: Меню теперь всегда развернуто (is_persistent=True)

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import Dict, Any, Optional
from urllib.parse import quote

from bot.localization import t, Lang
from bot.config import settings

# ====================== REPLY КЛАВИАТУРЫ ======================

def get_main_keyboard(lang: Lang, user_id: int) -> ReplyKeyboardMarkup:
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
        KeyboardButton(
            text=t('btn_profile', lang), 
            web_app=WebAppInfo(url=f"{settings.BASE_URL}/profile/{user_id}")
        ),
        KeyboardButton(text=t('btn_settings', lang))
    )
    builder.adjust(2, 2, 2)
    # is_persistent=True — меню не сворачивается
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

def get_admin_keyboard(lang: Lang, user_id: int) -> ReplyKeyboardMarkup:
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
        KeyboardButton(text=t('btn_show_users', lang))
    )
    builder.row(
        KeyboardButton(text=t('btn_reload_data', lang)),
        KeyboardButton(text=t('btn_test_broadcast', lang)),
        KeyboardButton(
            text=t('btn_profile', lang), 
            web_app=WebAppInfo(url=f"{settings.BASE_URL}/profile/{user_id}")
        )
    )
    builder.adjust(2, 2, 3, 3)
    # is_persistent=True — меню не сворачивается
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

def get_settings_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🇺🇦 Українська"),
        KeyboardButton(text="🇬🇧 English"),
        KeyboardButton(text="🇷🇺 Русский")
    )
    builder.row(KeyboardButton(text=t('btn_back', lang)))
    builder.adjust(3, 1)
    # is_persistent=True — меню не сворачивается
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

def get_reply_keyboard_for_user(chat_id: int, lang: Lang, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    if int(chat_id) == int(settings.ADMIN_CHAT_ID):
        return get_admin_keyboard(lang, chat_id)

    from bot.utils import check_demo_status
    is_paid = user_data.get("is_paid", False)
    is_expired = check_demo_status(user_data) 

    if is_expired and not is_paid:
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(
            text=t('btn_profile', lang),
            web_app=WebAppInfo(url=f"{settings.BASE_URL}/profile/{chat_id}")
        ))
        builder.row(KeyboardButton(text=t('btn_settings', lang)))
        builder.row(KeyboardButton(text=t('btn_pay_premium', lang)))
        builder.adjust(1, 1, 1)
        # is_persistent=True — меню не сворачивается
        return builder.as_markup(resize_keyboard=True, is_persistent=True)

    return get_main_keyboard(lang, chat_id)

# ====================== INLINE КЛАВИАТУРЫ ======================

def get_lang_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська UA", callback_data="set_lang_ua")
    builder.button(text="🇬🇧 English EN", callback_data="set_lang_en")
    builder.button(text="🇷🇺 Русский RU", callback_data="set_lang_ru")
    builder.adjust(1)
    return builder.as_markup()

def get_broadcast_keyboard(lang: Lang, quote_text: Optional[str] = None, category: str = "default", current_reaction: Optional[str] = None, user_name: Optional[str] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    like_text = "👍 ✅" if current_reaction == "like" else "👍"
    dislike_text = "👎 ✅" if current_reaction == "dislike" else "👎"

    builder.button(text=like_text, callback_data=f"reaction:like:{category}")
    builder.button(text=dislike_text, callback_data=f"reaction:dislike:{category}")

    if category != "challenge" and quote_text:
        # Безопасная обрезка для Share
        safe_quote = quote_text[:250] + "..." if len(quote_text) > 250 else quote_text
        share_msg = t('share_text_with_quote', lang, quote=safe_quote, bot_username=settings.BOT_USERNAME, name=user_name or "")
        share_url = f"https://t.me/share/url?url=https://t.me/{settings.BOT_USERNAME}&text={quote(share_msg)}"
        
        builder.button(text=t('btn_share', lang), url=share_url)
        builder.adjust(2, 1)
    else:
        builder.adjust(2)
    return builder.as_markup()

def get_challenge_buttons(lang: Lang, challenge_id: Optional[int] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if challenge_id is not None:
        builder.button(text=t("btn_challenge_accept", lang), callback_data=f"accept_challenge:{challenge_id}")
    builder.button(text=t("btn_challenge_new", lang), callback_data="new_challenge")
    builder.adjust(1)
    return builder.as_markup()

def get_challenge_complete_button(lang: Lang, challenge_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_challenge_complete", lang), callback_data=f"complete_challenge:{challenge_id}")
    return builder.as_markup()

def get_payment_keyboard(lang: Lang, is_test_user: bool = False, show_new_demo: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if show_new_demo:
        kb.button(text=t('btn_want_demo', lang), callback_data="activate_demo")
    
    kb.button(text=t('btn_pay_premium', lang), url=settings.PAYMENT_LINK) 
    
    if is_test_user:
        kb.button(text="Test Pay", callback_data="test_payment_success")
    kb.adjust(1)
    return kb.as_markup()