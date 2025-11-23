# 10 bot/button_handlers.py
# Обработчики кнопок Aiogram (F.text)/ Обработчики CallbackQuery

from datetime import datetime, date

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

# ✅ ИСПРАВЛЕНО: прямые импорты
from config import logger, settings
from localization import t, Lang
from database import db
from keyboards import get_settings_keyboard, get_reply_keyboard_for_user
from content_handlers import (
    send_from_list, send_rules, send_profile,
    send_payment_instructions, activate_new_demo
)
from challenges import send_new_challenge_message
from utils import get_user_tz 
from commands import send_stats_report, show_users_command # ✅ Импорт 
from scheduler import setup_jobs_and_cache
from user_loader import load_static_data

router = Router()

@router.message(F.text.in_([t('btn_motivate', 'ru'), t('btn_motivate', 'ua'), t('btn_motivate', 'en')]))
async def handle_motivate_button(message: Message, static_data: dict, user_data: dict, lang: Lang):
    await send_from_list(message, static_data, user_data, lang, "motivations", "title_motivation")

@router.message(F.text.in_([t('btn_settings', 'ru'), t('btn_settings', 'ua'), t('btn_settings', 'en')]))
async def handle_settings_button(message: Message, lang: Lang):
    await message.answer(t('msg_choose_action', lang), reply_markup=get_settings_keyboard(lang))

async def set_language(message: Message, user_data: dict, lang: Lang, new_lang: Lang):
    if user_data.get("language") == new_lang:
        await message.answer(t('lang_chosen', new_lang), reply_markup=get_reply_keyboard_for_user(message.from_user.id, new_lang, user_data))
        return
    await db.update_user(message.from_user.id, language=new_lang)
    user_data["language"] = new_lang 
    await message.answer(t('lang_chosen', new_lang), reply_markup=get_reply_keyboard_for_user(message.from_user.id, new_lang, user_data))

@router.message(F.text == "🇺🇦 Українська")
async def handle_lang_ua(message: Message, user_data: dict, lang: Lang): await set_language(message, user_data, lang, "ua")
@router.message(F.text == "🇬🇧 English")
async def handle_lang_en(message: Message, user_data: dict, lang: Lang): await set_language(message, user_data, lang, "en")
@router.message(F.text == "🇷🇺 Русский")
async def handle_lang_ru(message: Message, user_data: dict, lang: Lang): await set_language(message, user_data, lang, "ru")

@router.message(F.text.in_([t('btn_back', 'ru'), t('btn_back', 'ua'), t('btn_back', 'en')]))
async def handle_back_button(message: Message, user_data: dict, lang: Lang):
    await message.answer(t('msg_welcome_back', lang), reply_markup=get_reply_keyboard_for_user(message.from_user.id, lang, user_data))

@router.message(F.text.in_([t('btn_rules', 'ru'), t('btn_rules', 'ua'), t('btn_rules', 'en')]))
async def handle_rules_button(message: Message, static_data: dict, user_data: dict, lang: Lang):
    await send_rules(message, static_data, user_data, lang)

@router.message(F.text.in_([t('btn_rhythm', 'ru'), t('btn_rhythm', 'ua'), t('btn_rhythm', 'en')]))
async def handle_rhythm_button(message: Message, static_data: dict, user_data: dict, lang: Lang):
    await send_from_list(message, static_data, user_data, lang, "ritm", "title_rhythm")

@router.message(F.text.in_([t('btn_challenge', 'ru'), t('btn_challenge', 'ua'), t('btn_challenge', 'en')]))
async def handle_challenge_button(message: Message, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    chat_id = message.from_user.id
    user_tz = get_user_tz(user_data); today = datetime.now(user_tz).date()
    last_challenge_date_str = user_data.get("last_challenge_date")
    if last_challenge_date_str:
        try:
            last_challenge_date = date.fromisoformat(last_challenge_date_str)
            if last_challenge_date == today:
                if user_data.get("challenge_accepted") is False: await message.answer(t('challenge_pending_acceptance', lang=lang)); return
                elif user_data.get("challenge_accepted") is True and chat_id not in settings.TESTER_USER_IDS: await message.answer(t('challenge_already_issued', lang=lang)); return
        except Exception: pass
    await send_new_challenge_message(message, static_data, user_data, lang, state, is_edit=False)

@router.message(F.text.in_([t('btn_profile', 'ru'), t('btn_profile', 'ua'), t('btn_profile', 'en')]))
async def handle_profile_button(message: Message, user_data: dict, lang: Lang):
    await send_profile(message, user_data, lang)

@router.message(F.text.in_([t('btn_stats', 'ru'), t('btn_stats', 'ua'), t('btn_stats', 'en')]))
async def handle_stats_button(message: Message, users_db: dict, is_admin: bool, lang: Lang):
    if not is_admin: await message.answer(t('unknown_command', lang)); return
    await send_stats_report(message, users_db, lang)

@router.message(F.text.in_([t('btn_pay_premium', 'ru'), t('btn_pay_premium', 'ua'), t('btn_pay_premium', 'en'), t('btn_pay_api_test_premium', 'ru'), t('btn_pay_api_test_premium', 'ua'), t('btn_pay_api_test_premium', 'en')]))
async def handle_pay_button(message: Message, user_data: dict, lang: Lang):
    await send_payment_instructions(message, user_data, lang)

@router.message(F.text.in_([t('btn_want_demo', 'ru'), t('btn_want_demo', 'ua'), t('btn_want_demo', 'en')]))
async def handle_want_demo_button(message: Message, user_data: dict, lang: Lang):
    await activate_new_demo(message, user_data, lang)

@router.message(F.text.in_([t('btn_reload_data', 'ru'), t('btn_reload_data', 'ua'), t('btn_reload_data', 'en')]))
async def handle_reload_data(message: Message, bot: Bot, users_db: dict, static_data: dict, is_admin: bool, lang: Lang):
    if not is_admin: return
    logger.info(f"Admin {message.from_user.id} triggered /reload (button).")
    new_static_data = await load_static_data(); static_data.clear(); static_data.update(new_static_data)
    new_users_db = await db.get_all_users(); users_db.clear(); users_db.update(new_users_db)
    await setup_jobs_and_cache(bot, users_db, static_data)
    await message.answer(t('reload_confirm', lang))

@router.message(F.text.in_([t('btn_show_users', 'ru'), t('btn_show_users', 'ua'), t('btn_show_users', 'en')]))
async def handle_show_users_button(message: Message, is_admin: bool, lang: Lang):
    if not is_admin: return
    await show_users_command(message, is_admin, lang)

@router.message(F.text)
async def handle_unknown_text(message: Message, lang: Lang, user_data: dict):
    logger.warning(f"Unknown command received from user {message.from_user.id}: {message.text}")
    markup = get_reply_keyboard_for_user(message.from_user.id, lang, user_data)
    await message.answer(t('unknown_command', lang), reply_markup=markup)