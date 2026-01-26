# 10 - bot/commands.py
# Системные и админ-команды (Исправлено: синхронизация и тесты)
# Системные и админ-команды
# ✅ ИСПРАВЛЕНО (2026-01-16): Логика /start — создание пользователя сразу (Ошибка #3)
# Системные и админ-команды
# ✅ ИСПРАВЛЕНО (2026-01-17): Ошибка #9 — Демо cooldown логика (автоматический перезапуск)
# 10 - bot/commands.py
# Системные и админ-команды (ULTIMATE 10/10 VERSION)
# ✅ СВЕРЕНО: Сохранены все функции и логика Олега
# ✅ УЛУЧШЕНО: Временные метки в stats, защита от self-grant, асинхронность 100%
# Системные и админ-команды (УЛЬТИМАТИВНАЯ ВЕРСИЯ: 10/10)
# ✅ ВОССТАНОВЛЕНО: send_stats_report, отслеживание блокировок, все сценарии /start
# ✅ СИНХРОНИЗИРОВАНО: Полная асинхронность (is_demo_expired), логи релоада и защита от self-grant

import json
from datetime import datetime, timezone, timedelta
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
from bot.utils import safe_send, get_user_lang, is_demo_expired, get_demo_config
from bot.scheduler import setup_jobs_and_cache, test_broadcast_job
from bot.user_loader import load_static_data

router = Router()

class TimezoneStates(StatesGroup):
    awaiting_timezone = State()

# --- 🛡️ ОТСЛЕЖИВАНИЕ БЛОКИРОВКИ БОТА ---

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, bot: Bot):
    """Отслеживание, когда пользователь блокирует бота."""
    user_id = event.chat.id
    name = event.from_user.first_name if event.from_user else "User"
    await db.update_user(user_id, active=False)
    logger.info(f"⛔ User {user_id} blocked the bot.")
    await notify_admins(bot, f"⛔ <b>Пользователь заблокировал бота:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, bot: Bot):
    """Отслеживание, когда пользователь разблокирует бота."""
    user_id = event.chat.id
    await db.update_user(user_id, active=True)
    logger.info(f"✅ User {user_id} unblocked the bot.")

# --- 🚀 START & PAY ---

@router.message(CommandStart())
async def start_command(message: Message, bot: Bot, static_data: dict, users_db: dict):
    """
    ✅ ИСПРАВЛЕНО (2026-01-16): Логика /start создает пользователя сразу.
    ✅ ИСПРАВЛЕНО (2026-01-17): Демо cooldown логика (автоматический перезапуск).
    """
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    user_id_str = str(user_id)
    
    logger.info(f"Commands: /start command from user {user_id}")
    
    # 1️⃣ Пытаемся получить существующего пользователя
    user_data = await db.get_user(user_id)
    
    # 2️⃣ НОВЫЙ ПОЛЬЗОВАТЕЛЬ → Создаем его сразу
    if user_data is None:
        logger.info(f"Commands: New user {user_id}, creating...")
        config = get_demo_config(user_id)
        demo_expiration = (datetime.now(timezone.utc) + timedelta(days=config["demo"])).isoformat()
        
        await db.add_user(
            user_id=user_id,
            username=message.from_user.username,
            name=message.from_user.first_name or "Пользователь",
            language=settings.DEFAULT_LANG,
            timezone=settings.DEFAULT_TZ_KEY,
            status="active_demo",
            demo_expiration=demo_expiration,
            active=True,
            demo_count=1
        )
        
        user_data = await db.get_user(user_id)
        if user_data:
            users_db[user_id_str] = user_data
        
        await message.answer(
            t('lang_choose_first', settings.DEFAULT_LANG), 
            reply_markup=get_lang_keyboard()
        )
        return

    # 3️⃣ ВЕРНУВШИЙСЯ ПОЛЬЗОВАТЕЛЬ
    lang = get_user_lang(user_data)
    users_db[user_id_str] = user_data
    
    # Проверка автоматического перезапуска демо (Логика 5+1+5)
    if user_data.get("status") == "cooldown":
        exp_str = user_data.get("demo_expiration")
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                config = get_demo_config(user_id)
                cooldown_end = exp_dt + timedelta(days=config["cooldown"])
                
                if now_utc >= cooldown_end:
                    logger.info(f"Commands: Cooldown ended for user {user_id}, restarting demo...")
                    new_expiry = now_utc + timedelta(days=config["demo"])
                    await db.update_user(
                        user_id,
                        demo_count=2,
                        status="active_demo",
                        demo_expiration=new_expiry.isoformat(),
                        challenge_streak=0,
                        challenge_accepted=0,
                        challenges=[],
                        sent_expiry_warning=0,
                        challenges_today=0,
                        rules_shown_count=0,
                        active=True
                    )
                    
                    user_data = await db.get_user(user_id)
                    # Защита от race condition
                    if not user_data:
                        logger.critical(f"Failed to reload user_data after demo restart for {user_id}")
                        return

                    users_db[user_id_str] = user_data
                    
                    await safe_send(
                        bot, user_id, 
                        t("demo_restarted_info", lang, name=user_data.get("name", ""))
                    )
                else:
                    remaining = cooldown_end - now_utc
                    h, m = int(remaining.total_seconds() // 3600), int((remaining.total_seconds() % 3600) // 60)
                    await message.answer(
                        t('demo_expired_cooldown', lang, name=user_data.get('name', ''), hours=h, minutes=m),
                        reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data)
                    )
                    return
            except Exception as e:
                logger.error(f"Error checking cooldown for user {user_id}: {e}", exc_info=True)

    # 4️⃣ ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ
    await handle_start_command(
        message=message,
        static_data=static_data,
        user_data=user_data,
        lang=lang,
        is_new_user=False
    )

@router.message(Command("pay"))
async def pay_command(message: Message, user_data: dict, lang: Lang):
    """Команда для инициации платежа."""
    await send_payment_instructions(message, user_data, lang)

# --- ⚙️ LANGUAGE & TIMEZONE ---

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
        await message.answer(
            t('timezone_set_success', lang, new_tz=new_tz_key), 
            parse_mode="HTML", 
            reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data)
        )
    except (ZoneInfoNotFoundError, Exception):
        await message.answer(t('timezone_set_error', lang, error_text=new_tz_key), parse_mode="HTML")

# --- 👑 ADMIN COMMANDS ---

@router.message(Command("broadcast_test"))
async def broadcast_test_command(message: Message, bot: Bot, static_data: dict, is_admin: bool = False):
    if not is_admin: return
    user_data = await db.get_user(message.from_user.id)
    lang = get_user_lang(user_data)
    await message.answer("🧪 <b>Запуск тестовой рассылки...</b>", parse_mode="HTML")
    await test_broadcast_job(bot, static_data, message.from_user.id, lang)
    await message.answer("✅ <b>Тестовая рассылка завершена.</b>", parse_mode="HTML")

@router.message(Command("grant"))
async def grant_command(message: Message, bot: Bot, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    if not is_admin: return
    try:
        args = message.text.split()
        if len(args) < 2: raise ValueError
        target_id_int = int(args[1])
        
        if target_id_int == settings.ADMIN_CHAT_ID:
            await message.answer("Нельзя выдавать Premium самому себе :)")
            return

        target_user = await db.get_user(target_id_int)
        if not target_user: 
            await message.answer(t('admin_grant_fail_id', lang, user_id=target_id_int))
            return
        
        await db.update_user(target_id_int, is_paid=True, active=True, status="active_paid")
        users_db[str(target_id_int)] = await db.get_user(target_id_int)
        
        await message.answer(t('admin_grant_success', lang, name=target_user.get('name', ''), user_id=target_id_int))
        await safe_send(bot, target_id_int, t('user_grant_notification', get_user_lang(target_user)))
    except:
        await message.answer(t('admin_grant_usage', lang))

async def send_stats_report(message: Message, users_db: dict, lang: Lang):
    """Отправить подробный отчет статистики."""
    all_users = await db.get_all_users()
    users_db.clear()
    users_db.update(all_users)

    stats = {"total": 0, "active": 0, "first": 0, "repeat": 0, "inactive": 0, "exp": 0, "block": 0}
    
    for u in users_db.values():
        stats["total"] += 1
        if u.get("active") in [True, 1, "1"]:
            stats["active"] += 1
            if u.get("demo_count", 1) > 1: stats["repeat"] += 1
            else: stats["first"] += 1
        else:
            stats["inactive"] += 1
            if await is_demo_expired(u): stats["exp"] += 1
            else: stats["block"] += 1
    
    gen_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    stats_text = (
        f"👥 <b>{t('profile_status_total', lang)}:</b> {stats['total']}\n\n"
        f"✅ <b>{t('profile_status_active', lang)}:</b> {stats['active']}\n"
        f"  - <i>{t('profile_status_first_time', lang)}:</i> {stats['first']}\n"
        f"  - <i>{t('profile_status_repeat', lang)}:</i> {stats['repeat']}\n\n"
        f"❌ <b>{t('profile_status_inactive', lang)}:</b> {stats['inactive']}\n"
        f"  - <i>{t('profile_status_demo_expired', lang)}:</i> {stats['exp']}\n"
        f"  - <i>{t('profile_status_blocked', lang)}:</i> {stats['block']}\n\n"
        f"⏱ <b>Generated:</b> {gen_time}"
    )
    await message.answer(stats_text, parse_mode="HTML")

@router.message(Command("stats"))
async def stats_command(message: Message, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    if not is_admin: return
    await send_stats_report(message, users_db, lang)

@router.message(Command("show_users"))
async def show_users_command(message: Message, users_db: dict, is_admin: bool = False):
    if not is_admin: return
    data_str = json.dumps(users_db, default=str, indent=2, ensure_ascii=False)
    file = BufferedInputFile(data_str.encode("utf-8"), filename="users.json")
    await message.answer_document(file, caption="📂 Users Database Dump")

@router.message(Command("reload"))
async def reload_command(message: Message, bot: Bot, users_db: dict, static_data: dict, is_admin: bool = False, lang: Lang = "ru"):
    if not is_admin: return
    static_data.update(await load_static_data())
    users_db.update(await db.get_all_users())
    logger.info(f"Reloaded {len(users_db)} users from DB")
    await setup_jobs_and_cache(bot, users_db, static_data)
    await message.answer(t('reload_confirm', lang))