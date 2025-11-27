# 6 - bot/content_handlers.py
# - Логика контента и доступа. Обработчик статического контента и логики доступа

import random
import json
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any

# ✅ ДОБАВЛЕНО: Импорты для работы кнопок и колбэков
from aiogram.types import Message, CallbackQuery 
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

# --- Импорты ---
from bot.config import logger, settings, SPECIAL_USER_IDS
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import (
    get_reply_keyboard_for_user, get_payment_keyboard,
    get_main_keyboard, get_cooldown_keyboard,
    get_broadcast_keyboard 
)
from bot.utils import (
    get_demo_days, get_cooldown_days, get_max_demo_cycles,
    is_demo_expired, get_tz_from_lang, get_user_tz
)


# --- 1. Логика /start ---
async def handle_start_command(message: Message, static_data: dict, user_data: dict, lang: Lang, is_new_user: bool):
    chat_id = message.from_user.id
    user_name = message.from_user.first_name or "друг"
    
    if is_new_user:
        user_lang_code = user_data.get("language") 
        auto_tz_key = get_tz_from_lang(user_lang_code)
        demo_duration_days = get_demo_days(chat_id)
        demo_expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=demo_duration_days)).isoformat()

        await db.update_user(chat_id, demo_count=1, demo_expiration=demo_expiration, status="active_demo")
        
        user_data_from_db = await db.get_user(chat_id)
        if hasattr(message.bot, "dp"):
            dp = message.bot.dp
            if "users_db" in dp.data:
                dp.data["users_db"][str(chat_id)] = user_data_from_db
                user_data = user_data_from_db 

        logger.info(f"👤 New user {chat_id} activated demo. Lang: {lang}. Demo: {demo_duration_days} days.")
        
        if chat_id != settings.ADMIN_CHAT_ID:
            admin_data = await db.get_user(settings.ADMIN_CHAT_ID)
            admin_lang = admin_data.get("language", "ru") if admin_data else "ru"
            
            kb = InlineKeyboardBuilder().button(text=t('admin_stats_button', admin_lang), callback_data="admin_stats").as_markup()
            admin_text = t('admin_new_user', admin_lang, name=user_name, user_id=chat_id)
            try: await message.bot.send_message(settings.ADMIN_CHAT_ID, admin_text, reply_markup=kb)
            except Exception as e: logger.error(f"Failed to notify admin: {e}")

        markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
        welcome_text = t('welcome', lang, name=user_name, demo_days=demo_duration_days)
        welcome_text += t('welcome_timezone_note', lang, default_tz=auto_tz_key)
        
        await message.answer(welcome_text, reply_markup=markup, parse_mode="HTML")
        return

    if user_data.get("name") != user_name:
        await db.update_user(chat_id, name=user_name)
        user_data["name"] = user_name
        
    if is_demo_expired(user_data) and not user_data.get("is_paid") and chat_id not in SPECIAL_USER_IDS:
        await handle_expired_demo(message, user_data, lang)
        return

    status_text_key = 'status_premium' if user_data.get("is_paid") else 'status_demo'
    status_text = t(status_text_key, lang)
    markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
    await message.answer(t('welcome_return', lang, name=user_name, status_text=status_text), reply_markup=markup)

async def handle_expired_demo(message: Message, user_data: dict, lang: Lang):
    """Логика обработки просроченного демо-доступа."""
    chat_id = message.from_user.id
    user_name = user_data.get("name", "друг")
    is_test_user = chat_id in settings.TESTER_USER_IDS
    demo_count = user_data.get("demo_count", 1)
    
    cooldown_days = get_cooldown_days(chat_id)
    demo_days = get_demo_days(chat_id)
    max_cycles = get_max_demo_cycles(chat_id)
    
    demo_exp_str = user_data.get("demo_expiration")
    
    try:
        if demo_exp_str:
            demo_exp_date = datetime.fromisoformat(demo_exp_str).replace(tzinfo=ZoneInfo("UTC"))
            next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
            now_utc = datetime.now(ZoneInfo("UTC"))

            if now_utc < next_demo_dt:
                # Режим кулдауна
                time_left = next_demo_dt - now_utc
                hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes_left, _ = divmod(remainder, 60)
                
                if user_data.get("status") == "awaiting_renewal":
                    markup = get_cooldown_keyboard(lang, is_test_user)
                    text = t('demo_awaiting_renewal', lang, name=user_name, hours=hours_left, minutes=minutes_left)
                else:
                    markup = get_payment_keyboard(lang, is_test_user, show_new_demo=False)
                    text = t('demo_expired_cooldown', lang, name=user_name, hours=hours_left, minutes=minutes_left)
                await message.answer(text, reply_markup=markup, parse_mode="HTML")
                return 
        
        if demo_count < max_cycles:
            markup = get_payment_keyboard(lang, is_test_user, show_new_demo=True)
            text = t('demo_expired_choice', lang, name=user_name, demo_days=demo_days)
            await message.answer(text, reply_markup=markup)
        else:
            markup = get_payment_keyboard(lang, is_test_user, show_new_demo=False)
            text = t('demo_expired_final', lang, name=user_name)
            await message.answer(text, reply_markup=markup)
            
    except (ValueError, TypeError) as e:
        logger.error(f"Error checking demo date for {chat_id}: {e}")
        markup = get_payment_keyboard(lang, is_test_user, show_new_demo=(demo_count < max_cycles))
        await message.answer(t('demo_expired_choice', lang, name=user_name, demo_days=demo_days), reply_markup=markup)


# --- 2. Логика отправки контента и Пагинации ---

async def handle_pagination(query: CallbackQuery, static_data: dict, lang: Lang):
    """
    ✅ ДОБАВЛЕНО: Обработка листания списков (Мотивация, Ритмы и т.д.).
    Format callback_data: "page:category:index"
    """
    try:
        parts = query.data.split(":")
        # page:motivations:0
        category = parts[1]
        current_index = int(parts[2])

        # 1. Получаем список контента
        content_list = static_data.get(category, {}).get(lang, [])
        if not content_list:
            content_list = static_data.get(category, {}).get("ru", [])

        if not content_list:
            await query.answer("Список пуст / List empty", show_alert=True)
            return

        total_items = len(content_list)
        
        # Зацикливание
        if current_index < 0:
            current_index = total_items - 1
        elif current_index >= total_items:
            current_index = 0

        # 2. Получаем текст
        item = content_list[current_index]
        text_content = ""
        if isinstance(item, str):
            text_content = item
        elif isinstance(item, dict):
            text_content = item.get("text") or item.get("content") or str(item)
        
        # Добавляем счетчик страниц
        final_text = f"{text_content}\n\n📖 <i>{current_index + 1} / {total_items}</i>"

        # 3. Кнопки
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️", callback_data=f"page:{category}:{current_index - 1}")
        kb.button(text="➡️", callback_data=f"page:{category}:{current_index + 1}")
        # Можно добавить лайк, если нужно
        # kb.row()
        # kb.button(text="❤️", callback_data="reaction:like")
        
        # 4. Редактируем
        try:
            await query.message.edit_text(final_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        except TelegramBadRequest:
            await query.answer()
            
    except Exception as e:
        logger.error(f"Pagination error: {e}")
        await query.answer("Error parsing page", show_alert=True)


async def send_from_list(message: Message, static_data: dict, user_data: dict, lang: Lang, key: str, title_key: str):
    title = t(title_key, lang)
    data = static_data.get(key, {})
    item_list = data.get(lang, data.get(settings.DEFAULT_LANG, [])) 
    
    if not item_list:
        await message.answer(t('list_empty', lang, title=title))
        return
        
    user_name = user_data.get("name", "друг")
    try:
        # Если это первый элемент списка, отправляем его с кнопками пагинации
        # Но для "Случайной" фразы (фраза дня) лучше рандом.
        # Если мы хотим листать, то нужно отправлять с index=0 и кнопками.
        # В ТЗ было "Случайная фраза" для дня/утра, а списки (Мотивация) - листать.
        
        # Если это Мотивация или Ритмы (которые листаются):
        if key in ['motivations', 'ritm', 'universe_laws', 'goals']:
             # Отправляем первый элемент и кнопки пагинации
             item = item_list[0]
             text_content = item if isinstance(item, str) else item.get("text", str(item))
             final_text = f"{text_content}\n\n📖 <i>1 / {len(item_list)}</i>"
             
             kb = InlineKeyboardBuilder()
             kb.button(text="⬅️", callback_data=f"page:{key}:-1") # Сразу даем возможность пойти назад (в конец)
             kb.button(text="➡️", callback_data=f"page:{key}:1")
             
             await message.answer(final_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
             
        else:
            # Для фраз дня/утра/вечера - просто случайная цитата с лайками (как у тебя было)
            item = random.choice(item_list).format(name=user_name)
            reaction_keyboard = get_broadcast_keyboard(lang, quote_text=item)
            await message.answer(f"<b>{title}</b>\n{item}", parse_mode="HTML", reply_markup=reaction_keyboard)
            
    except Exception as e:
        logger.error(f"Error in send_from_list: {e}")
        await message.answer(t('list_error_unexpected', lang, title=title))

async def send_rules(message: Message, static_data: dict, user_data: dict, lang: Lang):
    chat_id = message.from_user.id
    user_tz = get_user_tz(user_data)
    today_iso = datetime.now(user_tz).date().isoformat()
    
    last_rules_date = user_data.get("last_rules_date")
    rules_shown_count = user_data.get("rules_shown_count", 0)
    shown_today_indices = user_data.get("rules_indices_today", [])
    if isinstance(shown_today_indices, str):
        try: shown_today_indices = json.loads(shown_today_indices)
        except: shown_today_indices = []

    if last_rules_date != today_iso:
        rules_shown_count = 0
        shown_today_indices = []

    if rules_shown_count >= settings.RULES_PER_DAY_LIMIT:
        await message.answer(t('rules_limit_reached', lang=lang))
        return

    data = static_data.get("rules", {})
    item_list = data.get(lang, data.get(settings.DEFAULT_LANG, []))
    
    if not item_list:
        await message.answer(t('list_empty', lang, title=t('title_rules', lang)))
        return
    
    available_rules = [item for i, item in enumerate(item_list) if i not in shown_today_indices]
    if not available_rules:
        available_rules = item_list 
        shown_today_indices = []
        
    rule = random.choice(available_rules)
    rule_index = item_list.index(rule)
    
    title = t('title_rules', lang)
    text = f"📜 <b>{t('title_rules_daily', lang, title=title, count=rules_shown_count + 1, limit=settings.RULES_PER_DAY_LIMIT)}</b>\n\n• {rule}"
    
    rules_shown_count += 1
    shown_today_indices.append(rule_index)
    
    await db.update_user(chat_id, last_rules_date=today_iso, rules_shown_count=rules_shown_count, rules_indices_today=json.dumps(shown_today_indices))
    user_data["last_rules_date"] = today_iso
    user_data["rules_shown_count"] = rules_shown_count
    user_data["rules_indices_today"] = shown_today_indices
    
    await message.answer(text, parse_mode="HTML")

async def send_profile(message: Message, user_data: dict, lang: Lang):
    challenges = user_data.get("challenges", [])
    if isinstance(challenges, str):
        try: challenges = json.loads(challenges)
        except: challenges = []
            
    completed_challenges = sum(1 for ch in challenges if isinstance(ch, dict) and ch.get("completed"))
    status_key = 'status_premium' if user_data.get('is_paid') else 'status_demo'
    status_text = t(status_key, lang=lang)
    
    text = (f"{t('profile_title', lang=lang)}\n\n"
            f"{t('profile_name', lang=lang)}: {user_data.get('name', 'Неизвестно')}\n"
            f"{t('profile_status', lang=lang)}: {status_text}\n\n"
            f"<b>📊 Статистика:</b>\n"
            f"{t('profile_challenges_accepted', lang=lang)}: {len(challenges)}\n"
            f"{t('profile_challenges_completed', lang=lang)}: {completed_challenges}\n"
            f"{t('profile_challenge_streak', lang=lang)}: {user_data.get('challenge_streak', 0)} 🔥\n"
            f"{t('profile_likes', lang=lang)}: {user_data.get('stats_likes', 0)}\n"
            f"{t('profile_dislikes', lang=lang)}: {user_data.get('stats_dislikes', 0)}")
    await message.answer(text, parse_mode="HTML")

async def send_payment_instructions(message: Message, user_data: dict, lang: Lang):
    user_name = user_data.get("name", "друг")
    await message.answer(t('pay_instructions', lang=lang, name=user_name), parse_mode="HTML", disable_web_page_preview=True)

async def activate_new_demo(message: Message, user_data: dict, lang: Lang):
    chat_id = message.from_user.id
    demo_duration_days = get_demo_days(chat_id)
    cooldown_days = get_cooldown_days(chat_id)
    max_cycles = get_max_demo_cycles(chat_id)
    demo_count = user_data.get("demo_count", 1)

    demo_exp_str = user_data.get("demo_expiration")
    
    try:
        if demo_exp_str:
            demo_exp_date = datetime.fromisoformat(demo_exp_str).replace(tzinfo=ZoneInfo("UTC"))
            next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
            now_utc = datetime.now(ZoneInfo("UTC"))
            
            if now_utc < next_demo_dt:
                await db.update_user(chat_id, status="awaiting_renewal")
                user_data["status"] = "awaiting_renewal" 
                from bot.keyboards import get_cooldown_keyboard
                markup = get_cooldown_keyboard(lang, chat_id in settings.TESTER_USER_IDS)
                time_left = next_demo_dt - now_utc
                hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes_left, _ = divmod(remainder, 60)
                
                await message.answer(t('demo_awaiting_renewal', lang, name=user_data.get("name", "друг"), hours=hours_left, minutes=minutes_left), reply_markup=markup)
                return
                
        if demo_count >= max_cycles:
            from bot.keyboards import get_payment_keyboard 
            markup = get_payment_keyboard(lang, chat_id in settings.TESTER_USER_IDS, show_new_demo=False)
            await message.answer(t('demo_expired_final', lang, name=user_data.get("name", "друг")), reply_markup=markup)
            return
            
    except Exception as e:
        logger.error(f"Error checking demo conditions for {chat_id}: {e}")
        if demo_count >= max_cycles:
            from bot.keyboards import get_payment_keyboard 
            markup = get_payment_keyboard(lang, chat_id in settings.TESTER_USER_IDS, show_new_demo=False)
            await message.answer(t('demo_expired_final', lang, name=user_data.get("name", "друг")), reply_markup=markup)
            return


    if demo_count >= max_cycles:
        from bot.keyboards import get_payment_keyboard 
        markup = get_payment_keyboard(lang, chat_id in settings.TESTER_USER_IDS, show_new_demo=False)
        await message.answer(t('demo_expired_final', lang, name=user_data.get("name", "друг")), reply_markup=markup)
        return

    logger.info(f"Activating new demo cycle ({demo_count + 1}) for user {chat_id}.")
    new_expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=demo_duration_days)).isoformat()
    new_data = {
        "demo_count": demo_count + 1, "demo_expiration": new_expiration,
        "challenge_streak": 0, "last_challenge_date": None, "last_rules_date": None,
        "rules_shown_count": 0, "sent_expiry_warning": False, "status": "active_demo"
    }
    await db.update_user(chat_id, **new_data)
    user_data.update(new_data)
    
    from bot.keyboards import get_main_keyboard
    new_markup = get_main_keyboard(lang)
    await message.answer(t('welcome_renewed_demo', lang, name=user_data.get("name", "друг"), demo_days=demo_duration_days), reply_markup=new_markup)