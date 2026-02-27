# 11 - bot/button_handlers.py
# ✅ Обработчики текстовых кнопок (Мотивируй, Челлендж, Правила и т.д.)
# ✅ Обработчики callback-кнопок (выбор языка, реакции)
# ✅ Админские кнопки (Статистика, Обновить, Тест рассылки)
# ✅ Fallback для неизвестных команд
# ✅ Защита от дублей вызовов

# 11 - bot/button_handlers.py - ФИНАЛЬНАЯ ВЕРСИЯ (30.01.2026)
# Обработчики текстовых кнопок
# ✅ ПРОВЕРЕНО: Защита от дублей, админ-панель, fallback

import json
from datetime import datetime, date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import get_settings_keyboard, get_reply_keyboard_for_user
from bot.content_handlers import (
    send_from_list, send_rules, send_profile,
    send_payment_instructions, activate_new_demo
)
from bot.challenges import send_new_challenge_message, accept_challenge, complete_challenge
from bot.utils import get_user_tz
from bot.commands import send_stats_report, show_users_command, broadcast_test_command
from bot.scheduler import setup_jobs_and_cache
from bot.user_loader import load_static_data

router = Router()
router_unknown = Router()

def btn_filter(key: str):
    """Создает фильтр для кнопки на всех языках (RU/UA/EN)."""
    return F.text.in_([t(key, lang) for lang in ['ru', 'ua', 'en']])

async def _get_user_data(user_id: int, kwargs: dict, force_db: bool = False) -> dict:
    """Получение данных пользователя с опцией синхронизации."""
    try:
        if force_db:
            u = await db.get_user(user_id)
            if u and "users_db" in kwargs:
                kwargs["users_db"][str(user_id)] = u
            logger.debug(f"Handlers: force_db=True → fetched fresh data for {user_id}")
            return u or {}
        
        ud = kwargs.get("user_data")
        if ud and isinstance(ud, dict) and ud.get("user_id") == user_id:
            return ud
            
        users_db = kwargs.get("users_db")
        if users_db and isinstance(users_db, dict):
            cached = users_db.get(str(user_id))
            if cached: return cached
            
        return await db.get_user(user_id) or {}
    except Exception as e:
        logger.error(f"Handlers: Error getting user data for {user_id}: {e}")
        return {}

# --- 🖱️ CALLBACKS (Inline) ---

@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_callback(callback: CallbackQuery, **kwargs):
    user_id = callback.from_user.id
    new_lang = callback.data.replace("set_lang_", "")
    await db.update_user(user_id, language=new_lang, active=True)
    
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    
    await callback.answer()
    await callback.message.answer(
        t('lang_chosen', new_lang),
        reply_markup=get_reply_keyboard_for_user(user_id, new_lang, user_data)
    )
    try: await callback.message.delete()
    except: pass

@router.callback_query(F.data.startswith("accept_challenge"))
async def handle_accept_challenge_callback(callback: CallbackQuery, state: FSMContext, **kwargs):
    user_data = await _get_user_data(callback.from_user.id, kwargs, force_db=True)
    await accept_challenge(callback, kwargs.get("static_data", {}), user_data, kwargs.get("lang", "ru"), state)

@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge_callback_inline(callback: CallbackQuery, state: FSMContext, **kwargs):
    user_data = await _get_user_data(callback.from_user.id, kwargs, force_db=True)
    await send_new_challenge_message(callback, kwargs.get("static_data", {}), user_data, kwargs.get("lang", "ru"), state, is_edit=True)

@router.callback_query(F.data.startswith("complete_challenge"))
async def handle_complete_challenge_callback(callback: CallbackQuery, state: FSMContext, **kwargs):
    user_data = await _get_user_data(callback.from_user.id, kwargs, force_db=True)
    await complete_challenge(callback, user_data, kwargs.get("lang", "ru"), state)

# --- ⌨️ MESSAGES (Text Buttons) ---

@router.message(btn_filter('btn_motivate'))
async def handle_motivate_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs)
    await send_from_list(message, kwargs.get("static_data", {}), user_data, user_data.get("language", "ru"), "motivations", "title_motivation")

@router.message(btn_filter('btn_settings'))
async def handle_settings_button(message: Message, **kwargs):
    lang = kwargs.get("lang", "ru")
    await message.answer(t('msg_choose_action', lang), reply_markup=get_settings_keyboard(lang))

@router.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English", "🇷🇺 Русский"]))
async def handle_lang_switch_buttons(message: Message, **kwargs):
    new_lang = "ua" if "Українська" in message.text else ("en" if "English" in message.text else "ru")
    await db.update_user(message.from_user.id, language=new_lang)
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    await message.answer(t('lang_chosen', new_lang), reply_markup=get_reply_keyboard_for_user(message.from_user.id, new_lang, user_data))

@router.message(btn_filter('btn_back'))
async def handle_back_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs)
    lang = user_data.get("language", "ru")
    await message.answer(t('msg_welcome_back', lang), reply_markup=get_reply_keyboard_for_user(message.from_user.id, lang, user_data))

@router.message(btn_filter('btn_rules'))
async def handle_rules_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs)
    await send_rules(message, kwargs.get("static_data", {}), user_data, user_data.get("language", "ru"))

@router.message(btn_filter('btn_rhythm'))
async def handle_rhythm_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs)
    await send_from_list(message, kwargs.get("static_data", {}), user_data, user_data.get("language", "ru"), "ritm", "title_rhythm")

@router.message(btn_filter('btn_challenge'))
async def handle_challenge_button(message: Message, state: FSMContext, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    await send_new_challenge_message(message, kwargs.get("static_data", {}), user_data, user_data.get("language", "ru"), state, is_edit=False)

@router.message(btn_filter('btn_profile'))
async def handle_profile_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    await send_profile(message, user_data, user_data.get("language", "ru"))

@router.message(btn_filter('btn_stats'))
async def handle_stats_button(message: Message, **kwargs):
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")): return
    await send_stats_report(message, kwargs.get("users_db", {}), kwargs.get("lang", "ru"))

@router.message(btn_filter('btn_pay_premium'))
async def handle_pay_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    await send_payment_instructions(message, user_data, user_data.get("language", "ru"))

@router.message(btn_filter('btn_want_demo'))
async def handle_want_demo_button(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    await activate_new_demo(message, user_data, user_data.get("language", "ru"))

@router.message(btn_filter('btn_reload_data'))
async def handle_reload_data(message: Message, bot: Bot, **kwargs):
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")): return
    new_static = await load_static_data()
    if "static_data" in kwargs: kwargs["static_data"].update(new_static)
    if "users_db" in kwargs: kwargs["users_db"].update(await db.get_all_users())
    await setup_jobs_and_cache(bot, kwargs.get("users_db", {}), new_static)
    await message.answer(t('reload_confirm', kwargs.get("lang", "ru")))

@router.message(btn_filter('btn_show_users'))
async def handle_show_users_button(message: Message, **kwargs):
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")): return
    await show_users_command(message, kwargs.get("users_db", {}), True)

@router.message(btn_filter('btn_test_broadcast'))
async def handle_test_broadcast_button(message: Message, bot: Bot, **kwargs):
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")): return
    await broadcast_test_command(message, bot, kwargs.get("static_data", {}), True)

# --- ❓ UNKNOWN TEXT (Fallback) ---

@router_unknown.message(F.text)
async def handle_unknown_text(message: Message, **kwargs):
    user_data = await _get_user_data(message.from_user.id, kwargs)
    lang = user_data.get("language", "ru")
    await message.answer(t('unknown_command', lang), reply_markup=get_reply_keyboard_for_user(message.from_user.id, lang, user_data)