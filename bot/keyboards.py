# 8 - bot/keyboards.py
# Reply и Inline клавиатуры

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import Dict, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import urllib.parse

from localization import t, Lang
from config import settings
# ✅ ИСПРАВЛЕНО: from utils, а не from bot.utils
from utils import is_admin, is_demo_expired, get_cooldown_days, get_max_demo_cycles 

def get_main_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=t('btn_motivate', lang)), KeyboardButton(text=t('btn_rhythm', lang)))
    builder.row(KeyboardButton(text=t('btn_challenge', lang)), KeyboardButton(text=t('btn_rules', lang)))
    builder.row(KeyboardButton(text=t('btn_profile', lang)), KeyboardButton(text=t('btn_settings', lang)))
    return builder.as_markup(resize_keyboard=True)

def get_admin_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=t('btn_motivate', lang)), KeyboardButton(text=t('btn_rhythm', lang)))
    builder.row(KeyboardButton(text=t('btn_challenge', lang)), KeyboardButton(text=t('btn_rules', lang)))
    builder.row(KeyboardButton(text=t('btn_settings', lang)), KeyboardButton(text=t('btn_stats', lang)), KeyboardButton(text=t('btn_show_users', lang)))
    builder.row(KeyboardButton(text=t('btn_profile', lang)))
    builder.adjust(2, 2, 3, 1) 
    return builder.as_markup(resize_keyboard=True)

def get_settings_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🇺🇦 Українська"), KeyboardButton(text="🇬🇧 English"), KeyboardButton(text="🇷🇺 Русский"))
    builder.row(KeyboardButton(text=t('btn_back', lang)))
    return builder.as_markup(resize_keyboard=True)

def get_payment_keyboard(lang: Lang, is_test_user: bool = False, show_new_demo: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if is_test_user: builder.button(text=t('btn_pay_api_test_premium', lang))
    else: builder.button(text=t('btn_pay_premium', lang))
    if show_new_demo: builder.button(text=t('btn_want_demo', lang))
    builder.adjust(2 if show_new_demo else 1)
    return builder.as_markup(resize_keyboard=True)

def get_cooldown_keyboard(lang: Lang, is_test_user: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=t('btn_motivate', lang)), KeyboardButton(text=t('btn_rhythm', lang)))
    builder.row(KeyboardButton(text=t('btn_challenge', lang)), KeyboardButton(text=t('btn_rules', lang)))
    builder.row(KeyboardButton(text=t('btn_profile', lang)))
    if is_test_user: builder.row(KeyboardButton(text=t('btn_pay_api_test_premium', lang)))
    else: builder.row(KeyboardButton(text=t('btn_pay_premium', lang)))
    return builder.as_markup(resize_keyboard=True)

def get_reply_keyboard_for_user(chat_id: int, lang: Lang, user_data: Dict[str, Any]) -> ReplyKeyboardMarkup:
    if is_admin(chat_id): return get_admin_keyboard(lang)
    if user_data.get("is_paid"): return get_main_keyboard(lang)
    is_test_user = chat_id in settings.TESTER_USER_IDS

    if is_demo_expired(user_data) and user_data.get("status") != "new":
        demo_count = user_data.get("demo_count", 1)
        if user_data.get("status") == "awaiting_renewal": return get_cooldown_keyboard(lang, is_test_user)
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            exp_dt = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
            cooldown_days = get_cooldown_days(chat_id)
            next_demo_dt = exp_dt + timedelta(days=cooldown_days)
            if now_utc >= next_demo_dt:
                max_cycles = get_max_demo_cycles(chat_id)
                return get_payment_keyboard(lang, is_test_user, show_new_demo=(demo_count < max_cycles))
            else:
                return get_payment_keyboard(lang, is_test_user, show_new_demo=False)
        except Exception:
            max_cycles = get_max_demo_cycles(chat_id)
            return get_payment_keyboard(lang, is_test_user, show_new_demo=(demo_count < max_cycles))
    return get_main_keyboard(lang)

def get_lang_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Українська 🇺🇦", callback_data="set_lang_ua_new") 
    builder.button(text="English 🇬🇧", callback_data="set_lang_en_new")
    builder.button(text="Русский 🇷🇺", callback_data="set_lang_ru_new")
    builder.adjust(1)
    return builder.as_markup()

def get_broadcast_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    bot_link = f"https://t.me/{settings.BOT_USERNAME}"
    share_text = t('share_text_template', lang, bot_username=settings.BOT_USERNAME)
    encoded_text = urllib.parse.quote_plus(share_text)
    share_url = f"https://t.me/share/url?url={bot_link}&text={encoded_text}"
    builder = InlineKeyboardBuilder()
    builder.button(text="👍", callback_data="reaction:like")
    builder.button(text="👎", callback_data="reaction:dislike")
    builder.button(text=t('btn_share', lang), url=share_url)
    builder.adjust(2, 1) 
    return builder.as_markup()