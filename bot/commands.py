# 12 - bot/commands.py
# 12 - bot/commands.py - ФИНАЛЬНАЯ ВЕРСИЯ (30.01.2026)
# Системные и админ-команды
# ✅ ПРОВЕРЕНО: Логика 3+1+3, статистика, все команды

import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.types import Message, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import get_lang_keyboard, get_reply_keyboard_for_user
from bot.content_handlers import handle_start_command, send_payment_instructions, notify_admins
from bot.utils import safe_send, get_user_lang, is_demo_expired
from bot.scheduler import setup_jobs_and_cache
from bot.user_loader import load_static_data

router = Router()

class TimezoneStates(StatesGroup):
    awaiting_timezone = State()

# --- 🛡️ ОТСЛЕЖИВАНИЕ БЛОКИРОВКИ БОТА ---

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, bot: Bot):
    user_id = event.chat.id
    name = event.from_user.first_name if event.from_user else "User"
    await db.update_user(user_id, active=False)
    logger.info(f"⛔ User {user_id} blocked the bot.")
    await notify_admins(bot, f"⛔ <b>Пользователь заблокировал бота:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, bot: Bot):
    user_id = event.chat.id
    await db.update_user(user_id, active=True)
    logger.info(f"✅ User {user_id} unblocked the bot.")

# --- 🚀 START & PAY ---

@router.message(CommandStart())
async def start_command(message: Message, bot: Bot, static_data: dict, users_db: dict):
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    user_id_str = str(user_id)
    user_data = await db.get_user(user_id)
    
    # 1️⃣ НОВЫЙ ПОЛЬЗОВАТЕЛЬ (Формула 3+1+3)
    if user_data is None:
        logger.info(f"Commands: New user {user_id}, creating (3 days demo)...")
        # Ставим 3 дня демо по умолчанию
        demo_expiration = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        
        await db.add_user(
            user_id=user_id,
            username=message.from_user.username,
            name=message.from_user.first_name or "Пользователь",
            language=None, # Оставляем пустым для обязательного выбора
            timezone=settings.DEFAULT_TZ_KEY,
            status="active_demo",
            demo_expiration=demo_expiration,
            active=True,
            demo_count=1
        )
        await message.answer("Выберите язык / Choose language:", reply_markup=get_lang_keyboard())
        return

    # 2️⃣ ПРОВЕРКА ЯЗЫКА (Если пользователь есть, но язык не выбрал)
    lang = user_data.get("language")
    if not lang:
        return await message.answer("Пожалуйста, выберите язык:", reply_markup=get_lang_keyboard())

    # 3️⃣ ВЕРНУВШИЙСЯ ПОЛЬЗОВАТЕЛЬ (Логика кулдауна 1 день)
    users_db[user_id_str] = user_data
    
    if user_data.get("status") == "cooldown":
        exp_str = user_data.get("demo_expiration")
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                # Кулдаун всегда 1 день по новой формуле
                cooldown_end = exp_dt + timedelta(days=1)
                
                if now_utc >= cooldown_end:
                    logger.info(f"Commands: Cooldown ended for {user_id}, starting Demo 2 (3 days)...")
                    new_expiry = now_utc + timedelta(days=3)
                    await db.update_user(
                        user_id, demo_count=2, status="active_demo", demo_expiration=new_expiry.isoformat(),
                        challenge_streak=0, challenge_accepted=0, challenges=[],
                        sent_expiry_warning=0, active=True
                    )
                    user_data = await db.get_user(user_id)
                    users_db[user_id_str] = user_data
                    await safe_send(bot, user_id, t("demo_restarted_info", lang, name=user_data.get("name", "")))
                else:
                    remaining = cooldown_end - now_utc
                    h, m = int(remaining.total_seconds() // 3600), int((remaining.total_seconds() % 3600) // 60)
                    await message.answer(
                        t('demo_expired_cooldown', lang, name=user_data.get('name', ''), hours=h, minutes=m),
                        reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data)
                    )
                    return
            except Exception as e:
                logger.error(f"Error checking cooldown: {e}")

    await handle_start_command(message=message, static_data=static_data, user_data=user_data, lang=lang, is_new_user=False)

@router.message(Command("pay"))
async def pay_command(message: Message, user_data: dict, lang: Lang):
    await send_payment_instructions(message, user_data, lang)

# --- ⚙️ SETTINGS ---

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
            t('timezone_set_success', lang, new_tz=new_tz_key), parse_mode="HTML", 
            reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data)
        )
    except (ZoneInfoNotFoundError, Exception):
        await message.answer(t('timezone_set_error', lang, error_text=new_tz_key), parse_mode="HTML")

# --- 👑 ADMIN ---

@router.message(Command("broadcast_test"))
async def broadcast_test_command(message: Message, bot: Bot, static_data: dict, is_admin: bool = False):
    if not is_admin: return
    user_data = await db.get_user(message.from_user.id)
    lang = get_user_lang(user_data)
    
    await message.answer("🧪 <b>Тест рассылки (Режим 3+1+3)...</b>", parse_mode="HTML")
    # Отправляем только УТРО админу
    await message.answer(f"☀️ <b>Утреннее (Preview):</b>\n\n{t('broadcast_morning', lang)}", parse_mode="HTML")
    
    # Остальное — в логи сервера (fly.io logs)
    logger.info(f"--- ADMIN TEST BROADCAST ---")
    logger.info(f"DAY: {t('broadcast_day', lang)[:50]}...")
    logger.info(f"NIGHT: {t('broadcast_night', lang)[:50]}...")
    logger.info(f"--- TEST END ---")
    
    await message.answer("✅ Тест завершен. Остальные типы сообщений выведены в логи сервера.")

@router.message(Command("grant"))
async def grant_command(message: Message, bot: Bot, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    if not is_admin: return
    try:
        args = message.text.split()
        if len(args) < 2: raise ValueError
        target_id_int = int(args[1])
        
        target_user = await db.get_user(target_id_int)
        if not target_user: 
            await message.answer(f"❌ Пользователь {target_id_int} не найден.")
            return
        
        await db.update_user(target_id_int, is_paid=True, active=True, status="active_paid")
        users_db[str(target_id_int)] = await db.get_user(target_id_int)
        
        await message.answer(f"✅ Доступ Premium выдан: {target_user.get('name')} (ID: {target_id_int})")
        await safe_send(bot, target_id_int, t('user_grant_notification', get_user_lang(target_user)))
    except:
        await message.answer("Использование: <code>/grant [USER_ID]</code>")

@router.message(Command("stats"))
async def stats_cmd_handler(message: Message, is_admin: bool = False):
    if not is_admin: return
    await send_stats_report(message, {}, "ru")

@router.message(Command("delete_user"))
async def delete_user_command(message: Message, is_admin: bool = False):
    """Специальная команда для тестов: удаляет юзера полностью."""
    if not is_admin: return
    try:
        target_id = int(message.text.split()[1])
        await db.delete_user(target_id)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> полностью удален для повторного теста.")
    except:
        await message.answer("Использование: <code>/delete_user [USER_ID]</code>")

@router.message(Command("reload"))
async def reload_command(message: Message, bot: Bot, users_db: dict, static_data: dict, is_admin: bool = False):
    if not is_admin: return
    static_data.update(await load_static_data())
    users_db.update(await db.get_all_users())
    await setup_jobs_and_cache(bot, users_db, static_data)
    await message.answer("🔄 Система успешно перезагружена.")

# --- 📊 ФУНКЦИИ СТАТИСТИКИ (Вызываются из button_handlers) ---

async def send_stats_report(message: Message, users_db: dict, lang: Lang = "ru"):
    """Функция для кнопки 'Статистика'"""
    total = await db.get_total_users_count()
    active_7d = await db.get_active_users_count(days=7)
    report = (
        f"📊 <b>Статистика (3+1+3):</b>\n\n"
        f"👥 Всего: <code>{total}</code>\n"
        f"✅ Активны (7д): <code>{active_7d}</code>\n"
    )
    await message.answer(report, parse_mode="HTML")

async def show_users_command(message: Message, users_db: dict, is_admin: bool = False):
    """Функция для кнопки 'Показать юзеров'"""
    if not is_admin: return
    await send_stats_report(message, users_db)  # Пока делаем упрощенно через статы