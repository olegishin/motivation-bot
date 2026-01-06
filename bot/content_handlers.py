# 08 - bot/content_handlers.py
import random
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.enums import ParseMode

from bot.config import settings, logger
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import (
    get_main_keyboard, get_broadcast_keyboard, 
    get_payment_keyboard, get_reply_keyboard_for_user
)
from bot.utils import safe_send, get_user_tz

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def notify_admins(bot: Bot, text: str):
    admin_id = settings.ADMIN_CHAT_ID 
    if admin_id:
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

# --- ЛОГИКА СТАРТА ---
async def handle_start_command(message: Message, static_data: dict, user_data: dict, lang: Lang, is_new_user: bool = False):
    user_id = message.from_user.id
    bot = message.bot
    name = message.from_user.first_name
    
    if is_new_user:
        days = getattr(settings, 'REGULAR_DEMO_DAYS', 30) 
        expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=days)).isoformat()
        
        await db.update_user(user_id, status="active_demo", active=True, demo_count=1, demo_expiration=expiration, language=lang)
        user_data.update({"status": "active_demo", "active": True, "demo_count": 1, "demo_expiration": expiration, "language": lang})

        welcome_text = t('welcome', lang, name=name, demo_days=days) 
        kb = get_main_keyboard(lang, user_id=user_id)
        await message.answer(welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        
        await notify_admins(bot, f"🆕 <b>Новый пользователь!</b>\n👤 {name} (ID: <code>{user_id}</code>)\n🌍 Язык: {lang}")
    else:
        status_text = t('status_premium', lang) if user_data.get("is_paid") else t('status_demo', lang)
        
        if not user_data.get("is_paid"):
            exp = user_data.get("demo_expiration")
            if exp:
                dt_exp = datetime.fromisoformat(exp.replace('Z', '+00:00'))
                now = datetime.now(ZoneInfo("UTC"))
                days_left = (dt_exp - now).days
                status_text = f"{t('status_demo', lang)} ({max(0, days_left)} дн.)" 
            else:
                status_text = f"{t('status_demo', lang)} (0 дн.)" 
        
        welcome_text = t('welcome_return', lang, name=name, status_text=status_text)
        kb = get_main_keyboard(lang, user_id=user_id)
        await message.answer(welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        
        if user_id != settings.ADMIN_CHAT_ID: 
             await notify_admins(bot, f"👋 <b>Пользователь вернулся:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

# --- ОТПРАВКА ИЗ СПИСКА ---
async def send_from_list(message: Message, static_data: dict, user_data: dict, lang: Lang, list_key: str, title_key: str):
    content_data = static_data.get(list_key, {})
    if isinstance(content_data, dict):
        phrases = content_data.get(lang, content_data.get("ru", []))
    else:
        phrases = content_data if isinstance(content_data, list) else []

    if not phrases:
        await message.answer(t('list_empty', lang, title=t(title_key, lang)))
        return

    phrase_raw = random.choice(phrases)
    phrase = phrase_raw.get("text") or phrase_raw.get("content") or str(phrase_raw) if isinstance(phrase_raw, dict) else str(phrase_raw)

    user_name = user_data.get("name") or message.from_user.first_name
    try: phrase = phrase.format(name=user_name)
    except: pass

    kb = get_broadcast_keyboard(lang, quote_text=phrase, category=list_key, user_name=user_name)
    await message.answer(phrase, reply_markup=kb, parse_mode=ParseMode.HTML)

# --- ЛОГИКА РЕАКЦИЙ И ЧЕЛЛЕНДЖЕЙ ---

async def handle_reaction(callback: CallbackQuery, user_data: dict, lang: Lang):
    """Алиас для обработки реакций из колбэков."""
    data = callback.data
    if "like" in data:
        await handle_like(callback, user_data, lang)
    elif "dislike" in data:
        await handle_dislike(callback, user_data, lang)

async def handle_like(callback: CallbackQuery, user_data: dict, lang: Lang):
    likes = user_data.get("stats_likes", 0) + 1
    await db.update_user(callback.from_user.id, stats_likes=likes)
    user_data["stats_likes"] = likes
    await callback.answer(t('msg_like_thanks', lang))

async def handle_dislike(callback: CallbackQuery, user_data: dict, lang: Lang):
    dislikes = user_data.get("stats_dislikes", 0) + 1
    await db.update_user(callback.from_user.id, stats_dislikes=dislikes)
    user_data["stats_dislikes"] = dislikes
    await callback.answer(t('msg_dislike_thanks', lang))

async def handle_accept_challenge_idx(callback: CallbackQuery, user_data: dict, lang: Lang):
    """Обработка принятия конкретного челленджа."""
    await handle_accept_challenge(callback, user_data, lang)

async def handle_accept_challenge(callback: CallbackQuery, user_data: dict, lang: Lang):
    user_id = callback.from_user.id
    await db.update_user(user_id, challenge_accepted=True)
    user_data["challenge_accepted"] = True
    
    await callback.answer(t('challenge_accepted_toast', lang))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await callback.message.answer(t('challenge_accepted_msg', lang), parse_mode=ParseMode.HTML)

async def handle_new_challenge(callback: CallbackQuery, user_data: dict, lang: Lang):
    """Запрос нового челленджа."""
    # Логика может быть расширена, пока просто уведомляем
    await callback.answer("Генерирую новый челлендж...")
    # Здесь можно вызвать функцию отправки нового челленджа

# --- ОТПРАВКА ПРАВИЛ ---
async def send_rules(message: Message, static_data: dict, user_data: dict, lang: Lang):
    user_id = message.from_user.id
    user_tz = get_user_tz(user_data)
    today_iso = datetime.now(user_tz).date().isoformat()
    
    if user_data.get("last_rules_date") != today_iso:
        await db.update_user(user_id, last_rules_date=today_iso, rules_shown_count=0, rules_indices_today=json.dumps([]))
        user_data.update({"last_rules_date": today_iso, "rules_shown_count": 0, "rules_indices_today": []})

    shown_count = user_data.get("rules_shown_count", 0)
    if shown_count >= settings.RULES_PER_DAY_LIMIT:
        await message.answer(t('rules_limit_reached', lang))
        return

    rules_list = static_data.get("rules", {}).get(lang, [])
    if not rules_list:
        await message.answer(t('list_empty', lang, title="Rules"))
        return

    shown_indices = user_data.get("rules_indices_today") or []
    if isinstance(shown_indices, str):
        try: shown_indices = json.loads(shown_indices)
        except: shown_indices = []

    available_indices = [i for i in range(len(rules_list)) if i not in shown_indices] or list(range(len(rules_list)))
    idx = random.choice(available_indices)
    rule_text = rules_list[idx]
    
    new_shown = shown_indices + [idx]
    await db.update_user(user_id, rules_shown_count=shown_count + 1, rules_indices_today=json.dumps(new_shown))
    
    header = t('title_rules_daily', lang, title=t('title_rules', lang), count=shown_count + 1, limit=settings.RULES_PER_DAY_LIMIT)
    kb = get_broadcast_keyboard(lang, quote_text=rule_text, category="rules")
    await message.answer(f"{header}\n\n{rule_text}", reply_markup=kb, parse_mode=ParseMode.HTML)

# --- ПРОФИЛЬ ---
async def send_profile(message: Message, user_data: dict, lang: Lang):
    name = user_data.get('name') or message.from_user.first_name or "Пользователь"
    status = t('status_premium', lang) if user_data.get("is_paid") else t('status_demo', lang)
    
    challenges = user_data.get("challenges", [])
    accepted_count = len(challenges)
    completed_count = len([c for c in challenges if isinstance(c, dict) and c.get("completed")])
    
    streak = user_data.get("challenge_streak", 0)
    likes = user_data.get("stats_likes", 0)
    dislikes = user_data.get("stats_dislikes", 0)

    text = (
        f"👤 <b>{t('profile_title', lang)}</b>\n\n"
        f"📛 {t('profile_name', lang)}: <b>{name}</b>\n"
        f"💰 {t('profile_status', lang)}: <b>{status}</b>\n\n"
        f"⚔️ {t('profile_challenges_accepted', lang)}: <b>{accepted_count}</b>\n"
        f"✅ Выполнено челленджей: <b>{completed_count}</b>\n"
        f"🔥 {t('profile_challenge_streak', lang)}: <b>{streak}</b>\n\n"
        f"👍 {t('profile_likes', lang)}: <b>{likes}</b>\n"
        f"👎 {t('profile_dislikes', lang)}: <b>{dislikes}</b>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

# --- ОПЛАТА И ДЕМО ---
async def send_payment_instructions(message: Message, user_data: dict, lang: Lang):
    kb = get_payment_keyboard(lang, is_test_user=(message.from_user.id == settings.ADMIN_CHAT_ID))
    await message.answer(t('pay_instructions', lang, name=message.from_user.first_name), reply_markup=kb)

async def activate_new_demo(message: Message, user_data: dict, lang: Lang):
    user_id = message.from_user.id
    days = settings.REGULAR_DEMO_DAYS
    expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=days)).isoformat()
    await db.update_user(user_id, status="active_demo", active=True, demo_expiration=expiration)
    user_data.update({"status": "active_demo", "active": True, "demo_expiration": expiration})
    
    await message.answer(t('welcome_renewed_demo', lang, name=message.from_user.first_name, demo_days=days), 
                         reply_markup=get_main_keyboard(lang, user_id=user_id))

async def handle_expired_demo(message: Message, user_data: dict, lang: Lang):
    await message.answer(t('demo_expired_final', lang, name=message.from_user.first_name), 
                         reply_markup=get_payment_keyboard(lang))