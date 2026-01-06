import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.types import Message, BufferedInputFile, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import get_lang_keyboard, get_reply_keyboard_for_user
from bot.content_handlers import handle_start_command, send_payment_instructions, notify_admins
from bot.utils import safe_send, get_user_lang, check_demo_status
from bot.scheduler import setup_jobs_and_cache, test_broadcast_job
from bot.user_loader import load_static_data

router = Router()

class TimezoneStates(StatesGroup):
    awaiting_timezone = State()

# --- ОТСЛЕЖИВАНИЕ БЛОКИРОВКИ БОТА ---

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, bot: Bot):
    user_id = event.chat.id
    name = event.from_user.first_name
    await db.update_user(user_id, active=False)
    logger.info(f"⛔ User {user_id} blocked the bot.")
    await notify_admins(bot, f"⛔ <b>Пользователь заблокировал бота:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, bot: Bot):
    user_id = event.chat.id
    await db.update_user(user_id, active=True)
    logger.info(f"✅ User {user_id} unblocked the bot.")

# --- START & PAY ---

@router.message(CommandStart())
async def start_command(message: Message, bot: Bot, static_data: dict, users_db: dict):
    if not message.from_user: return
    user_id = message.from_user.id
    user_id_str = str(user_id)
    user_data = await db.get_user(user_id)
    
    if user_data is None:
        await message.answer(t('lang_choose_first', settings.DEFAULT_LANG), reply_markup=get_lang_keyboard())
        return

    lang = get_user_lang(user_data)
    users_db[user_id_str] = user_data

    # ✅ ПРОВЕРКА НА ПАУЗУ (COOLDOWN) ПЕРЕД ПРИВЕТСТВИЕМ
    if user_data.get("status") == "cooldown":
        exp_str = user_data.get("demo_expiration")
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=ZoneInfo("UTC"))
                
                # Пауза 24 часа после окончания демо
                resume_dt = exp_dt + timedelta(hours=24)
                now = datetime.now(ZoneInfo("UTC"))
                diff = resume_dt - now
                
                if diff.total_seconds() > 0:
                    hours = int(diff.total_seconds() // 3600)
                    minutes = int((diff.total_seconds() % 3600) // 60)
                    await message.answer(
                        t('demo_expired_cooldown', lang, name=user_data.get('name', ''), hours=hours, minutes=minutes),
                        reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data)
                    )
                    return # Останавливаем, чтобы не писать "С возвращением"
            except Exception as e:
                logger.error(f"Error calculating cooldown in start: {e}")

    # Если не на паузе — обычное приветствие через handle_start_command
    await handle_start_command(message=message, static_data=static_data, user_data=user_data, lang=lang, is_new_user=False)

@router.message(Command("pay"))
async def pay_command(message: Message, user_data: dict, lang: Lang):
    await send_payment_instructions(message, user_data, lang)

# --- LANGUAGE & TIMEZONE ---

@router.message(Command("language"))
async def language_command(message: Message, lang: Lang = "ru"):
    await message.answer(t('lang_choose', lang), reply_markup=get_lang_keyboard())

@router.message(Command("timezone"))
async def timezone_command(message: Message, state: FSMContext, user_data: dict, lang: Lang = "ru"):
    await state.set_state(TimezoneStates.awaiting_timezone)
    current_tz = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    await message.answer(t('timezone_command_text', lang, user_tz=current_tz), parse_mode="HTML")

@router.message(TimezoneStates.awaiting_timezone)
async def handle_new_timezone(message: Message, state: FSMContext, user_data: dict, lang: Lang = "ru"):
    new_tz_key = message.text.strip()
    user_id = message.from_user.id
    try:
        ZoneInfo(new_tz_key)  
        await db.update_user(user_id, timezone=new_tz_key)
        await state.clear()
        user_data["timezone"] = new_tz_key  
        markup = get_reply_keyboard_for_user(user_id, lang, user_data)
        await message.answer(t('timezone_set_success', lang, new_tz=new_tz_key), parse_mode="HTML", reply_markup=markup)
    except ZoneInfoNotFoundError:
        await message.answer(t('timezone_set_error', lang, error_text=new_tz_key), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error setting timezone: {e}")

@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext, user_data: dict, lang: Lang = "ru"):
    current_state = await state.get_state()
    if current_state is None: return
    await state.clear()
    user_id = message.from_user.id
    current_tz = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    markup = get_reply_keyboard_for_user(user_id, lang, user_data)
    await message.answer(t('timezone_cancel', lang, user_tz=current_tz), parse_mode="HTML", reply_markup=markup)

# --- ADMIN COMMANDS ---

@router.message(Command("broadcast_test"))
async def broadcast_test_command(message: Message, bot: Bot, static_data: dict, is_admin: bool = False):
    if not is_admin: return
    await message.answer("🧪 <b>Запуск тестовой рассылки...</b>", parse_mode="HTML")
    await test_broadcast_job(bot, static_data, message.from_user.id)
    await message.answer("✅ <b>Тестовая рассылка завершена.</b>", parse_mode="HTML")

@router.message(Command("grant"))
async def grant_command(message: Message, bot: Bot, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    if not is_admin: return
    try:
        target_id_str = message.text.split()[1]
        target_id_int = int(target_id_str)
        target_user_data = await db.get_user(target_id_int)
        if not target_user_data: 
            await message.answer(t('admin_grant_fail_id', lang, user_id=target_id_str))
            return
        await db.update_user(target_id_int, is_paid=True, active=True, status="active_paid")
        users_db[target_id_str] = await db.get_user(target_id_int)
        await message.answer(t('admin_grant_success', lang, name=target_user_data.get('name', ''), user_id=target_id_str))
        await safe_send(bot, target_id_int, t('user_grant_notification', get_user_lang(target_user_data)))
    except Exception:
        await message.answer(t('admin_grant_usage', lang))

@router.message(Command("wipe"))
async def wipe_user_command(message: Message, users_db: dict, is_admin: bool = False):
    if not is_admin: return
    try:
        target_id_str = message.text.split()[1]
        target_id = int(target_id_str)
        await db.delete_user(target_id)
        users_db.pop(target_id_str, None)
        await message.answer(f"🗑️ Пользователь <code>{target_id}</code> удален.")
    except Exception:
        await message.answer("⚠️ Формат: <code>/wipe ID</code>", parse_mode="HTML")

async def send_stats_report(message: Message, users_db: dict, lang: Lang):
    total = 0; active = 0; active_first = 0; active_repeat = 0; inactive = 0; inactive_demo_expired = 0; inactive_blocked = 0
    for user_id_str, u in users_db.items():
        if not isinstance(u, dict): continue
        total += 1
        if u.get("active"):
            active += 1
            if u.get("demo_count", 1) > 1: active_repeat += 1
            else: active_first += 1
        else:
            inactive += 1
            if check_demo_status(u): inactive_demo_expired += 1
            else: inactive_blocked += 1
    
    stats_text = (f"👥 <b>{t('profile_status_total', lang)}:</b> {total}\n\n"
                  f"✅ <b>{t('profile_status_active', lang)}:</b> {active}\n"
                  f"  - <i>{t('profile_status_first_time', lang)}:</i> {active_first}\n"
                  f"  - <i>{t('profile_status_repeat', lang)}:</i> {active_repeat}\n\n"
                  f"❌ <b>{t('profile_status_inactive', lang)}:</b> {inactive}\n"
                  f"  - <i>{t('profile_status_demo_expired', lang)}:</i> {inactive_demo_expired}\n"
                  f"  - <i>{t('profile_status_blocked', lang)}:</i> {inactive_blocked}")
    await message.answer(stats_text, parse_mode="HTML")

@router.message(Command("stats"))
async def stats_command(message: Message, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    if is_admin: await send_stats_report(message, users_db, lang)

@router.message(Command("show_users"))
async def show_users_command(message: Message, users_db: dict, is_admin: bool = False):
    if not is_admin: return
    data_str = json.dumps(users_db, default=str, indent=2, ensure_ascii=False)
    file = BufferedInputFile(data_str.encode("utf-8"), filename="users.json")
    await message.answer_document(file, caption="📂 Users Database Dump")

@router.message(Command("reload"))
async def reload_command(message: Message, bot: Bot, users_db: dict, static_data: dict, is_admin: bool = False, lang: Lang = "ru"):
    if not is_admin: return
    new_static_data = await load_static_data()
    static_data.clear()
    static_data.update(new_static_data)
    new_users_db = await db.get_all_users()
    users_db.clear()
    users_db.update(new_users_db)
    await setup_jobs_and_cache(bot, users_db, static_data)
    await message.answer(t('reload_confirm', lang))