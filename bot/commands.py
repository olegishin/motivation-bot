# 9 - bot/commands.py
# Обработчики команд Aiogram

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import logger, settings, SPECIAL_USER_IDS
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import get_lang_keyboard, get_reply_keyboard_for_user
from bot.content_handlers import handle_start_command, send_payment_instructions
from bot.utils import safe_send, get_user_lang, is_demo_expired
from bot.scheduler import setup_jobs_and_cache
from bot.user_loader import load_static_data

router = Router()

class TimezoneStates(StatesGroup):
    awaiting_timezone = State()
    
# --- START & PAY ---

@router.message(CommandStart())
async def start_command(
    message: Message, 
    bot: Bot, 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    is_new_user: bool 
):
    if not message.from_user:
        return

    if is_new_user:
        await message.answer(t('lang_choose_first', settings.DEFAULT_LANG), reply_markup=get_lang_keyboard())
        return
    
    await handle_start_command(message, static_data, user_data, lang, is_new_user=False)

@router.message(Command("pay"))
async def pay_command(message: Message, user_data: dict, lang: Lang):
    await send_payment_instructions(message, user_data, lang)

# --- LANGUAGE & TIMEZONE ---

@router.message(Command("language"))
async def language_command(message: Message, lang: Lang):
    await message.answer(t('lang_choose', lang), reply_markup=get_lang_keyboard())

@router.message(Command("timezone"))
async def timezone_command(message: Message, state: FSMContext, user_data: dict, lang: Lang):
    await state.set_state(TimezoneStates.awaiting_timezone)
    current_tz = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    await message.answer(t('timezone_command_text', lang, user_tz=current_tz), parse_mode="HTML")

@router.message(TimezoneStates.awaiting_timezone)
async def handle_new_timezone(message: Message, state: FSMContext, user_data: dict, lang: Lang):
    new_tz_key = message.text.strip()
    try:
        ZoneInfo(new_tz_key) 
        await db.update_user(message.from_user.id, timezone=new_tz_key)
        await state.clear()
        
        user_data["timezone"] = new_tz_key 
        markup = get_reply_keyboard_for_user(message.from_user.id, lang, user_data)
        
        await message.answer(t('timezone_set_success', lang, new_tz=new_tz_key), parse_mode="HTML", reply_markup=markup)
    except ZoneInfoNotFoundError:
        await message.answer(t('timezone_set_error', lang, error_text=new_tz_key), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error setting timezone for {message.from_user.id}: {e}")
        await message.answer(t('timezone_set_error', lang, error_text=new_tz_key))


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext, user_data: dict, lang: Lang):
    current_state = await state.get_state()
    if current_state is None: return

    await state.clear()
    current_tz = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    markup = get_reply_keyboard_for_user(message.from_user.id, lang, user_data)
    await message.answer(t('timezone_cancel', lang, user_tz=current_tz), parse_mode="HTML", reply_markup=markup)

# --- ADMIN COMMANDS ---

@router.message(Command("grant"))
async def grant_command(message: Message, bot: Bot, users_db: dict, is_admin: bool, lang: Lang):
    if not is_admin: return

    try: target_id_str = message.text.split()[1]; target_id_int = int(target_id_str)
    except Exception: await message.answer(t('admin_grant_usage', lang)); return

    target_user_data = await db.get_user(target_id_int)
    if not target_user_data: await message.answer(t('admin_grant_fail_id', lang, user_id=target_id_str)); return
    if target_user_data.get("is_paid"): await message.answer(t('admin_grant_fail_already_paid', lang, name=target_user_data.get('name', ''), user_id=target_id_str)); return
    
    await db.update_user(target_id_int, is_paid=True, status="active_paid", active=True, demo_expiration=(datetime.now(ZoneInfo("UTC")) + timedelta(days=30)).isoformat())
    target_user_data['is_paid'] = True; target_user_data['status'] = 'active_paid'; users_db[target_id_str] = target_user_data 
    
    await message.answer(t('admin_grant_success', lang, name=target_user_data.get('name', ''), user_id=target_id_str))
    target_lang = get_user_lang(target_user_data)
    await safe_send(bot, target_id_int, t('user_grant_notification', target_lang))
    logger.info(f"Admin {message.from_user.id} granted Premium to {target_id_str}")

async def send_stats_report(message: Message, users_db: dict, lang: Lang):
    total = 0; active = 0; active_first = 0; active_repeat = 0; inactive = 0; inactive_demo_expired = 0; inactive_blocked = 0
    for user_id_str, u in users_db.items():
        if not isinstance(u, dict): continue
        try: user_id = int(user_id_str)
        except ValueError: continue
        total += 1
        is_special = user_id in SPECIAL_USER_IDS
        if is_special:
            active += 1
            if u.get("demo_count", 1) > 1: active_repeat += 1
            else: active_first += 1
            continue
        if u.get("active"):
            active += 1
            if u.get("demo_count", 1) > 1: active_repeat += 1
            else: active_first += 1
        else:
            inactive += 1
            if is_demo_expired(u): inactive_demo_expired += 1
            else: inactive_blocked += 1
    
    stats_text = (f"👥 <b>{t('profile_status_total', lang)}:</b> {total}\n\n"
                  f"✅ <b>{t('profile_status_active', lang)}:</b> {active}\n"
                  f"  - <i>{t('profile_status_first_time', lang)}:</i> {active_first}\n"
                  f"  - <i>{t('profile_status_repeat', lang)}:</i> {active_repeat}\n\n"
                  f"❌ <b>{t('profile_status_inactive', lang)}:</b> {inactive} (Обычные пользователи)\n"
                  f"  - <i>{t('profile_status_demo_expired', lang)}:</i> {inactive_demo_expired}\n"
                  f"  - <i>{t('profile_status_blocked', lang)}:</i> {inactive_blocked}")
    await message.answer(stats_text, parse_mode="HTML")

@router.message(Command("stats"))
async def stats_command(message: Message, users_db: dict, is_admin: bool, lang: Lang):
    if not is_admin: return
    await send_stats_report(message, users_db, lang)

@router.message(Command("show_users"))
async def show_users_command(message: Message, is_admin: bool, lang: Lang):
    if not is_admin: return
    if settings.USERS_FILE.exists() and settings.USERS_FILE.stat().st_size > 2:
        await message.answer_document(document=FSInputFile(settings.USERS_FILE), caption=t('users_file_caption', lang))
    else:
        await message.answer(t('users_file_empty', lang))

@router.message(Command("reload"))
async def reload_command(message: Message, bot: Bot, users_db: dict, static_data: dict, is_admin: bool, lang: Lang):
    if not is_admin: return
    logger.info(f"Admin {message.from_user.id} triggered /reload.")
    new_static_data = await load_static_data(); static_data.clear(); static_data.update(new_static_data)
    new_users_db = await db.get_all_users(); users_db.clear(); users_db.update(new_users_db)
    await setup_jobs_and_cache(bot, users_db, static_data)
    await message.answer(t('reload_confirm', lang))