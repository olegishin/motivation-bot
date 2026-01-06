# 11 - bot/button_handlers.py
import json
from datetime import datetime, date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import get_settings_keyboard, get_reply_keyboard_for_user
from bot.content_handlers import (
    send_from_list, send_rules, send_profile,
    send_payment_instructions, activate_new_demo,
    handle_like, handle_dislike, handle_accept_challenge
)
from bot.challenges import send_new_challenge_message
from bot.utils import get_user_tz
from bot.commands import send_stats_report, show_users_command, broadcast_test_command
from bot.scheduler import setup_jobs_and_cache
from bot.user_loader import load_static_data

router = Router()

def _ensure_dict(data: any) -> dict:
    if isinstance(data, dict): return data
    if isinstance(data, str):
        try: return json.loads(data)
        except: return {}
    return {}

def btn_filter(key: str):
    return F.text.in_([t(key, 'ru'), t(key, 'ua'), t(key, 'en')])

# --- ОБРАБОТКА CALLBACK (Inline кнопки) ---

# 1. Выбор языка
@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_callback(callback: CallbackQuery, **kwargs):
    user_data = _ensure_dict(kwargs.get("user_data") or kwargs.get("users_db") or {})
    new_lang = callback.data.replace("set_lang_", "")
    user_id = callback.from_user.id
    await db.update_user(user_id, language=new_lang, active=True)
    user_data["language"] = new_lang
    user_data["active"] = True
    await callback.answer()
    await callback.message.answer(t('lang_chosen', new_lang), reply_markup=get_reply_keyboard_for_user(user_id, new_lang, user_data))
    try: await callback.message.delete()
    except: pass

# 2. Лайки и реакции
@router.callback_query(F.data.in_(["like", "dislike"]) | F.data.startswith("handle_reaction"))
async def handle_reaction_callback(callback: CallbackQuery, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    if "dislike" in callback.data:
        await handle_dislike(callback, user_data, lang)
    else:
        await handle_like(callback, user_data, lang)

# 3. Принятие челленджа
@router.callback_query(F.data.in_(["accept_challenge"]) | F.data.startswith("handle_accept_challenge"))
async def handle_accept_challenge_callback(callback: CallbackQuery, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    await handle_accept_challenge(callback, user_data, lang)

# 4. Запрос нового челленджа через Inline
@router.callback_query(F.data.startswith("handle_new_challenge"))
async def handle_new_challenge_callback(callback: CallbackQuery, state: FSMContext, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    static_data = kwargs.get("static_data", {})
    await send_new_challenge_message(callback.message, static_data, user_data, lang, state, is_edit=False)

# --- ОСНОВНЫЕ КНОПКИ (Текстовые сообщения) ---

@router.message(btn_filter('btn_motivate'))
async def handle_motivate_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    static_data = kwargs.get("static_data", {})
    await send_from_list(message, static_data, user_data, lang, "motivations", "title_motivation")

@router.message(btn_filter('btn_settings'))
async def handle_settings_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    await message.answer(t('msg_choose_action', lang), reply_markup=get_settings_keyboard(lang))

@router.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English", "🇷🇺 Русский"]))
async def handle_lang_switch_buttons(message: Message, **kwargs):
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    user_id = message.from_user.id
    new_lang = "ua" if "Українська" in message.text else ("en" if "English" in message.text else "ru")
    await db.update_user(user_id, language=new_lang)
    user_data["language"] = new_lang
    await message.answer(t('lang_chosen', new_lang), reply_markup=get_reply_keyboard_for_user(user_id, new_lang, user_data))

@router.message(btn_filter('btn_back'))
async def handle_back_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    user_id = message.from_user.id
    await message.answer(t('msg_welcome_back', lang), reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data))

@router.message(btn_filter('btn_rules'))
async def handle_rules_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    static_data = kwargs.get("static_data", {})
    await send_rules(message, static_data, user_data, lang)

@router.message(btn_filter('btn_rhythm'))
async def handle_rhythm_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    static_data = kwargs.get("static_data", {})
    await send_from_list(message, static_data, user_data, lang, "ritm", "title_rhythm")

@router.message(btn_filter('btn_challenge'))
async def handle_challenge_button(message: Message, state: FSMContext, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    static_data = kwargs.get("static_data", {})
    
    user_tz = get_user_tz(user_data)
    today = datetime.now(user_tz).date()
    last_date_str = user_data.get("last_challenge_date")
    
    if last_date_str:
        try:
            last_date = date.fromisoformat(last_date_str)
            if last_date == today:
                if user_data.get("challenge_accepted") is False: 
                    await message.answer(t('challenge_pending_acceptance', lang=lang))
                    return
                elif user_data.get("challenge_accepted") is True: 
                    await message.answer(t('challenge_already_issued', lang=lang))
                    return
        except: pass

    await send_new_challenge_message(message, static_data, user_data, lang, state, is_edit=False)

@router.message(btn_filter('btn_profile'))
async def handle_profile_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    await send_profile(message, user_data, lang)

# --- АДМИН-КНОПКИ ---

@router.message(btn_filter('btn_stats'))
async def handle_stats_button(message: Message, **kwargs):
    if not kwargs.get("is_admin"): return
    await send_stats_report(message, kwargs.get("users_db", {}), kwargs.get("lang", "ru"))

@router.message(F.text.in_([t('btn_pay_premium', 'ru'), t('btn_pay_premium', 'ua'), t('btn_pay_premium', 'en')]))
async def handle_pay_button(message: Message, **kwargs):
    await send_payment_instructions(message, _ensure_dict(kwargs.get("user_data", {})), kwargs.get("lang", "ru"))

@router.message(btn_filter('btn_want_demo'))
async def handle_want_demo_button(message: Message, **kwargs):
    await activate_new_demo(message, _ensure_dict(kwargs.get("user_data", {})), kwargs.get("lang", "ru"))

@router.message(btn_filter('btn_reload_data'))
async def handle_reload_data(message: Message, bot: Bot, **kwargs):
    if not kwargs.get("is_admin"): return
    new_static_data = await load_static_data()
    if "static_data" in kwargs:
        kwargs["static_data"].clear()
        kwargs["static_data"].update(new_static_data)
    new_users_db = await db.get_all_users()
    if "users_db" in kwargs:
        kwargs["users_db"].clear()
        kwargs["users_db"].update(new_users_db)
    await setup_jobs_and_cache(bot, kwargs.get("users_db", {}), new_static_data)
    await message.answer(t('reload_confirm', kwargs.get("lang", "ru")))

@router.message(btn_filter('btn_show_users'))
async def handle_show_users_button(message: Message, **kwargs):
    if not kwargs.get("is_admin"): return
    await show_users_command(message, kwargs.get("users_db", {}), True)

@router.message(btn_filter('btn_test_broadcast'))
async def handle_test_broadcast_button(message: Message, bot: Bot, **kwargs):
    if not kwargs.get("is_admin"): return
    await broadcast_test_command(message, bot, kwargs.get("static_data", {}), True)

@router.message(F.text)
async def handle_unknown_text(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    user_data = _ensure_dict(kwargs.get("user_data", {}))
    user_id = message.from_user.id
    markup = get_reply_keyboard_for_user(user_id, lang, user_data)
    await message.answer(t('unknown_command', lang), reply_markup=markup)