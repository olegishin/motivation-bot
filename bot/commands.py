# 10 - bot/commands.py
# Системные и админ-команды (Исправлено: синхронизация и тесты)
# Системные и админ-команды
# ✅ ИСПРАВЛЕНО (2026-01-16): Логика /start — создание пользователя сразу (Ошибка #3)
# Системные и админ-команды
# ✅ ИСПРАВЛЕНО (2026-01-17): Ошибка #9 — Демо cooldown логика (автоматический перезапуск)

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
from bot.utils import safe_send, get_user_lang, check_demo_status, get_demo_config
from bot.scheduler import setup_jobs_and_cache, test_broadcast_job
from bot.user_loader import load_static_data

router = Router()

class TimezoneStates(StatesGroup):
    awaiting_timezone = State()

# --- ОТСЛЕЖИВАНИЕ БЛОКИРОВКИ БОТА ---

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, bot: Bot):
    """Отслеживание, когда пользователь блокирует бота."""
    user_id = event.chat.id
    name = event.from_user.first_name
    await db.update_user(user_id, active=False)
    logger.info(f"⛔ User {user_id} blocked the bot.")
    await notify_admins(bot, f"⛔ <b>Пользователь заблокировал бота:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, bot: Bot):
    """Отслеживание, когда пользователь разблокирует бота."""
    user_id = event.chat.id
    await db.update_user(user_id, active=True)
    logger.info(f"✅ User {user_id} unblocked the bot.")

# --- START & PAY ---

@router.message(CommandStart())
async def start_command(message: Message, bot: Bot, static_data: dict, users_db: dict):
    """
    ✅ ИСПРАВЛЕНО (2026-01-16): 
    - Логика /start создает пользователя (Ошибка #3)
    - НОВОЕ: Проверка автоматического перезапуска демо (Ошибка #9)
    
    ЛОГИКА ДЕМО (5+1+5):
    1. День 1-5: demo_count=1, статус="active_demo"
    2. День 6: demo_count=1, статус="cooldown" (1 день тишины)
    3. День 7: АВТОМАТИЧЕСКИЙ перезапуск → demo_count=2, статус="active_demo"
    4. День 7-11: demo_count=2, статус="active_demo"
    5. День 12: ФИНАЛ демо, отправляем на Premium или повторный цикл
    
    СЦЕНАРИЙ 1: Новый пользователь (впервые)
    - Создаем пользователя с language=DEFAULT_LANG
    - Показываем меню выбора языка
    
    СЦЕНАРИЙ 2: Вернувшийся пользователь (cooldown)
    - Проверяем: истек ли cooldown?
    - Если да → автоматически перезапускаем демо
    - Если нет → показываем сообщение с оставшимся временем
    
    СЦЕНАРИЙ 3: Вернувшийся пользователь (активный)
    - Показываем приветствие с текущим языком
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
        logger.info(f"Commands: New user {user_id}, creating with default language {settings.DEFAULT_LANG}")
        
        config = get_demo_config(user_id)
        demo_expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=config["demo"])).isoformat()
        
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
        
        logger.info(f"Commands: User {user_id} created successfully in DB")
        
        user_data = await db.get_user(user_id)
        if user_data:
            users_db[user_id_str] = user_data
            logger.debug(f"Commands: Updated users_db cache for new user {user_id}")
        
        logger.info(f"Commands: Showing language selection for new user {user_id}")
        await message.answer(
            t('lang_choose_first', settings.DEFAULT_LANG), 
            reply_markup=get_lang_keyboard()
        )
        return

    # 3️⃣ ВЕРНУВШИЙСЯ ПОЛЬЗОВАТЕЛЬ
    logger.info(f"Commands: Returning user {user_id}")
    lang = get_user_lang(user_data)
    users_db[user_id_str] = user_data
    
    # ✅ ИСПРАВЛЕНИЕ ОШИБКИ #9: Проверка автоматического перезапуска демо
    # Логика: если cooldown закончился → автоматически перезапускаем второй демо
    if user_data.get("status") == "cooldown":
        logger.info(f"Commands: User {user_id} is in cooldown, checking if should restart demo...")
        
        exp_str = user_data.get("demo_expiration")
        if exp_str:
            try:
                # Парсим дату истечения в UTC
                exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=ZoneInfo("UTC"))
                
                now_utc = datetime.now(ZoneInfo("UTC"))
                config = get_demo_config(user_id)
                
                # Дата когда cooldown заканчивается = exp_dt + cooldown_days
                cooldown_end = exp_dt + timedelta(days=config["cooldown"])
                
                # 🎯 КЛЮЧЕВАЯ ПРОВЕРКА: Прошло ли время cooldown?
                if now_utc >= cooldown_end:
                    # ✅ АВТОМАТИЧЕСКИЙ ПЕРЕЗАПУСК
                    logger.info(f"Commands: Cooldown ended for user {user_id}, restarting demo (demo_count: 1 → 2)")
                    
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
                    
                    # Получаем свежие данные
                    user_data = await db.get_user(user_id)
                    users_db[user_id_str] = user_data
                    
                    # Уведомляем пользователя
                    await safe_send(
                        bot,
                        user_id,
                        t("demo_restarted_info", lang, name=user_data.get("name", ""))
                    )
                    
                    logger.info(f"Commands: Demo restarted for user {user_id}")
                    
                    # Показываем обычное приветствие
                    await handle_start_command(
                        message=message,
                        static_data=static_data,
                        user_data=user_data,
                        lang=lang,
                        is_new_user=False
                    )
                    return
                else:
                    # ⏳ Cooldown ЕЩЕ НЕ закончился
                    remaining = cooldown_end - now_utc
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int((remaining.total_seconds() % 3600) // 60)
                    
                    logger.info(f"Commands: User {user_id} cooldown still active for {hours}h {minutes}m")
                    
                    await message.answer(
                        t('demo_expired_cooldown', lang, name=user_data.get('name', ''), hours=hours, minutes=minutes),
                        reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data)
                    )
                    return
                    
            except Exception as e:
                logger.error(f"Commands: Error checking cooldown for user {user_id}: {e}", exc_info=True)
                # Фолбек: показываем приветствие
                pass

    # 4️⃣ ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ (активный демо или Premium)
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

# --- LANGUAGE & TIMEZONE ---

@router.message(Command("language"))
async def language_command(message: Message, lang: Lang = "ru"):
    """Команда для изменения языка."""
    await message.answer(t('lang_choose', lang), reply_markup=get_lang_keyboard())

@router.message(Command("timezone"))
async def timezone_command(message: Message, state: FSMContext, user_data: dict, lang: Lang = "ru"):
    """Команда для настройки часового пояса."""
    await state.set_state(TimezoneStates.awaiting_timezone)
    current_tz = user_data.get("timezone", settings.DEFAULT_TZ_KEY)
    await message.answer(
        t('timezone_command_text', lang, user_tz=current_tz), 
        parse_mode="HTML"
    )

@router.message(TimezoneStates.awaiting_timezone)
async def handle_new_timezone(message: Message, state: FSMContext, user_data: dict, lang: Lang = "ru"):
    """Обработка ввода нового часового пояса."""
    new_tz_key = message.text.strip()
    user_id = message.from_user.id
    try:
        ZoneInfo(new_tz_key)
        await db.update_user(user_id, timezone=new_tz_key)
        await state.clear()
        user_data["timezone"] = new_tz_key  
        markup = get_reply_keyboard_for_user(user_id, lang, user_data)
        await message.answer(
            t('timezone_set_success', lang, new_tz=new_tz_key), 
            parse_mode="HTML", 
            reply_markup=markup
        )
        logger.info(f"Commands: User {user_id} changed timezone to {new_tz_key}")
    except ZoneInfoNotFoundError:
        await message.answer(
            t('timezone_set_error', lang, error_text=new_tz_key), 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Commands: Error setting timezone for user {user_id}: {e}")

# --- ADMIN COMMANDS ---

@router.message(Command("broadcast_test"))
async def broadcast_test_command(message: Message, bot: Bot, static_data: dict, is_admin: bool = False):
    """Админ-команда: тестовая рассылка."""
    if not is_admin:
        logger.warning(f"Commands: Non-admin user {message.from_user.id} tried /broadcast_test")
        return
    
    logger.info(f"Commands: Admin {message.from_user.id} running broadcast test")
    
    user_data = await db.get_user(message.from_user.id)
    lang = get_user_lang(user_data)
    
    await message.answer("🧪 <b>Запуск тестовой рассылки...</b>", parse_mode="HTML")
    await test_broadcast_job(bot, static_data, message.from_user.id, lang)
    await message.answer("✅ <b>Тестовая рассылка завершена.</b>", parse_mode="HTML")

@router.message(Command("grant"))
async def grant_command(message: Message, bot: Bot, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    """Админ-команда: выдать Premium доступ пользователю."""
    if not is_admin:
        logger.warning(f"Commands: Non-admin user {message.from_user.id} tried /grant")
        return
    
    try:
        target_id_str = message.text.split()[1]
        target_id_int = int(target_id_str)
        
        target_user_data = await db.get_user(target_id_int)
        if not target_user_data: 
            await message.answer(t('admin_grant_fail_id', lang, user_id=target_id_str))
            logger.warning(f"Commands: Admin {message.from_user.id} tried to grant to non-existent user {target_id_int}")
            return
        
        await db.update_user(target_id_int, is_paid=True, active=True, status="active_paid")
        users_db[target_id_str] = await db.get_user(target_id_int)
        
        await message.answer(
            t('admin_grant_success', lang, name=target_user_data.get('name', ''), user_id=target_id_str)
        )
        
        await safe_send(bot, target_id_int, t('user_grant_notification', get_user_lang(target_user_data)))
        logger.info(f"Commands: Admin {message.from_user.id} granted Premium to user {target_id_int}")
        
    except (IndexError, ValueError):
        await message.answer(t('admin_grant_usage', lang))
    except Exception as e:
        logger.error(f"Commands: Error in grant_command: {e}")
        await message.answer(t('admin_grant_usage', lang))

async def send_stats_report(message: Message, users_db: dict, lang: Lang):
    """Отправить подробный отчет статистики."""
    all_users = await db.get_all_users()
    users_db.clear()
    users_db.update(all_users)

    total = 0
    active = 0
    active_first = 0
    active_repeat = 0
    inactive = 0
    inactive_demo_expired = 0
    inactive_blocked = 0
    
    for user_id_str, u in users_db.items():
        if not isinstance(u, dict):
            continue
        
        total += 1
        
        if u.get("active") in [True, 1, "1"]:
            active += 1
            if u.get("demo_count", 1) > 1:
                active_repeat += 1
            else:
                active_first += 1
        else:
            inactive += 1
            if check_demo_status(u):
                inactive_demo_expired += 1
            else:
                inactive_blocked += 1
    
    stats_text = (
        f"👥 <b>{t('profile_status_total', lang)}:</b> {total}\n\n"
        f"✅ <b>{t('profile_status_active', lang)}:</b> {active}\n"
        f"  - <i>{t('profile_status_first_time', lang)}:</i> {active_first}\n"
        f"  - <i>{t('profile_status_repeat', lang)}:</i> {active_repeat}\n\n"
        f"❌ <b>{t('profile_status_inactive', lang)}:</b> {inactive}\n"
        f"  - <i>{t('profile_status_demo_expired', lang)}:</i> {inactive_demo_expired}\n"
        f"  - <i>{t('profile_status_blocked', lang)}:</i> {inactive_blocked}"
    )
    await message.answer(stats_text, parse_mode="HTML")
    logger.info(f"Commands: Stats report sent. Total users: {total}")

@router.message(Command("stats"))
async def stats_command(message: Message, users_db: dict, is_admin: bool = False, lang: Lang = "ru"):
    """Админ-команда: показать статистику."""
    if not is_admin:
        logger.warning(f"Commands: Non-admin user {message.from_user.id} tried /stats")
        return
    
    logger.info(f"Commands: Admin {message.from_user.id} requested statistics")
    await send_stats_report(message, users_db, lang)

@router.message(Command("show_users"))
async def show_users_command(message: Message, users_db: dict, is_admin: bool = False):
    """Админ-команда: показать JSON dump пользователей."""
    if not is_admin:
        logger.warning(f"Commands: Non-admin user {message.from_user.id} tried /show_users")
        return
    
    data_str = json.dumps(users_db, default=str, indent=2, ensure_ascii=False)
    file = BufferedInputFile(data_str.encode("utf-8"), filename="users.json")
    await message.answer_document(file, caption="📂 Users Database Dump")
    logger.info(f"Commands: Admin {message.from_user.id} dumped users database")

@router.message(Command("reload"))
async def reload_command(message: Message, bot: Bot, users_db: dict, static_data: dict, is_admin: bool = False, lang: Lang = "ru"):
    """Админ-команда: перезагрузить кэш и планировщик."""
    if not is_admin:
        logger.warning(f"Commands: Non-admin user {message.from_user.id} tried /reload")
        return
    
    logger.warning(f"Commands: Admin {message.from_user.id} requested RELOAD DATA")
    
    new_static_data = await load_static_data()
    static_data.clear()
    static_data.update(new_static_data)
    
    new_users_db = await db.get_all_users()
    users_db.clear()
    users_db.update(new_users_db)
    
    await setup_jobs_and_cache(bot, users_db, static_data)
    
    await message.answer(t('reload_confirm', lang))
    logger.info(f"Commands: Reload completed successfully")