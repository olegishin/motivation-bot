# 04 - bot/keyboards.py
# 04 - bot/keyboards.py - 26.01.2026
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
# ULTIMATE VERSION: Fixed persistent menu + Share logic + Admin Fix
# ✅ ИСПРАВЛЕНО (2026-01-18): 
#    - Гарантированное отображение админ-кнопок (ID casting)
#    - Поддержка ✅ на кнопках реакций
#    - Синхронизация callback_data для демо-периода
# ✅ ИСПРАВЛЕНО (2026-01-26):
#    - Исправлена функция is_demo_expired (вместо check_demo_status)
#    - Админские кнопки показываются всегда для админа

# 04 - bot/keyboards.py
# ✅ ВЫДАНО ЦЕЛИКОМ ДЛЯ ЗАМЕНЫ — ПОЛНАЯ СВЕРКА (28.01.2026)
# ✅ СИНХРОНИЗИРОВАНО: Логика 3+1+3 (Cooldown), Реферальная программа
# ✅ ИСПРАВЛЕНО: Меню всегда развернуто (is_persistent=True), Админ-фикс
# ✅ СОХРАНЕНО: WebApp Профиль, Поддержка ✅, Логика "Поделиться"

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
    """Основная клавиатура для активных пользователей."""
    builder = ReplyKeyboardBuilder()
    # 1 ряд: Основной контент
    builder.row(
        KeyboardButton(text=t('btn_motivate', lang)),
        KeyboardButton(text=t('btn_rhythm', lang))
    )
    # 2 ряд: Челленджи и правила
    builder.row(
        KeyboardButton(text=t('btn_challenge', lang)),
        KeyboardButton(text=t('btn_rules', lang))
    )
    # 3 ряд: Профиль (WebApp) и Рефералы (Новинка аудита)
    builder.row(
        KeyboardButton(
            text=t('btn_profile', lang), 
            web_app=WebAppInfo(url=f"{settings.BASE_URL}/profile/{user_id}")
        ),
        KeyboardButton(text=t('btn_share', lang)) # Кнопка приглашения/рефералки
    )
    # 4 ряд: Настройки
    builder.row(KeyboardButton(text=t('btn_settings', lang)))
    
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

def get_admin_keyboard(lang: Lang, user_id: int) -> ReplyKeyboardMarkup:
    """Клавиатура для администратора (полный фарш)."""
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
        KeyboardButton(text=t('btn_stats', lang)),
        KeyboardButton(text=t('btn_show_users', lang)),
        KeyboardButton(text=t('btn_reload_data', lang))
    )
    builder.row(
        KeyboardButton(
            text=t('btn_profile', lang), 
            web_app=WebAppInfo(url=f"{settings.BASE_URL}/profile/{user_id}")
        ),
        KeyboardButton(text=t('btn_test_broadcast', lang)),
        KeyboardButton(text=t('btn_settings', lang))
    )
    builder.adjust(2, 2, 3, 3)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

def get_settings_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    """Клавиатура выбора языка в настройках."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🇺🇦 Українська"),
        KeyboardButton(text="🇬🇧 English"),
        KeyboardButton(text="🇷🇺 Русский")
    )
    builder.row(KeyboardButton(text=t('btn_back', lang)))
    builder.adjust(3, 1)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

def get_reply_keyboard_for_user(chat_id: int, lang: Lang, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    """
    Определяет, какую клавиатуру выдать в зависимости от статуса 3+1+3.
    """
    # 1. Проверка на админа (Принудительное приведение типов)
    if int(chat_id) == int(settings.ADMIN_CHAT_ID):
        return get_admin_keyboard(lang, chat_id)

    is_paid = user_data.get("is_paid", False)
    status = user_data.get("status", "active_demo")

    # 2. Если пользователь в "Дне тишины" (Cooldown) или Демо истекло
    # Мы ограничиваем меню, оставляя только критические кнопки
    from datetime import datetime, timezone
    demo_expired = False
    if not is_paid:
        expiry_str = user_data.get("demo_expiration")
        if not expiry_str:
            demo_expired = True
        else:
            try:
                expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                demo_expired = datetime.now(timezone.utc) > expiry_date
            except:
                demo_expired = True

    if (demo_expired or status == "cooldown") and not is_paid:
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(
            text=t('btn_profile', lang),
            web_app=WebAppInfo(url=f"{settings.BASE_URL}/profile/{chat_id}")
        ))
        builder.row(KeyboardButton(text=t('btn_pay_premium', lang)))
        builder.row(KeyboardButton(text=t('btn_settings', lang)))
        builder.adjust(1, 1, 1)
        return builder.as_markup(resize_keyboard=True, is_persistent=True)

    # 3. Обычное меню для активных
    return get_main_keyboard(lang, chat_id)

# ====================== INLINE КЛАВИАТУРЫ ======================

def get_lang_keyboard() -> InlineKeyboardMarkup:
    """Выбор языка при первом старте."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська UA", callback_data="set_lang_ua")
    builder.button(text="🇬🇧 English EN", callback_data="set_lang_en")
    builder.button(text="🇷🇺 Русский RU", callback_data="set_lang_ru")
    builder.adjust(1)
    return builder.as_markup()

def get_broadcast_keyboard(
    lang: Lang, 
    quote_text: Optional[str] = None, 
    category: str = "default", 
    current_reaction: Optional[str] = None, 
    user_name: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Кнопки под сообщениями рассылки (Реакции + Поделиться)."""
    builder = InlineKeyboardBuilder()
    
    # Реакция Like
    like_txt = "👍 ✅" if current_reaction == "like" else "👍"
    like_cb = "reaction:like:done" if current_reaction == "like" else "reaction:like"
    
    # Реакция Dislike
    dis_txt = "👎 ✅" if current_reaction == "dislike" else "👎"
    dis_cb = "reaction:dislike:done" if current_reaction == "dislike" else "reaction:dislike"

    builder.button(text=like_txt, callback_data=like_cb)
    builder.button(text=dis_txt, callback_data=dis_cb)

    # Кнопка "Поделиться" (если есть текст)
    if quote_text:
        # Обрезаем для стабильности ссылки
        safe_quote = quote_text[:280] + "..." if len(quote_text) > 280 else quote_text
        # Формируем текст (Призыв первым согласно аудиту)
        share_msg = t('share_text_with_quote', lang, quote=safe_quote, bot_username=settings.BOT_USERNAME)
        share_url = f"https://t.me/share/url?text={quote(share_msg)}"
        builder.button(text=t('btn_share', lang), url=share_url)

    builder.adjust(2, 1)
    return builder.as_markup()

def get_challenge_buttons(lang: Lang, challenge_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Принятие или выбор нового челленджа."""
    builder = InlineKeyboardBuilder()
    if challenge_id is not None:
        builder.button(text=t("btn_challenge_accept", lang), callback_data=f"accept_challenge:{challenge_id}")
    builder.button(text=t("btn_challenge_new", lang), callback_data="new_challenge")
    builder.adjust(1)
    return builder.as_markup()

def get_challenge_complete_button(lang: Lang, challenge_id: int) -> InlineKeyboardMarkup:
    """Завершение челленджа."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_challenge_complete", lang), callback_data=f"complete_challenge:{challenge_id}")
    return builder.as_markup()

def get_payment_keyboard(lang: Lang, is_test_user: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура оплаты."""
    kb = InlineKeyboardBuilder()
    kb.button(text=t('btn_pay_premium', lang), url=settings.PAYMENT_LINK)
    if is_test_user:
        kb.button(text="💳 Test Pay (Success)", callback_data="test_payment_success")
    kb.adjust(1)
    return kb.as_markup()