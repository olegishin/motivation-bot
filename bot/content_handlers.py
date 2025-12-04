# 08 - bot/content_handlers.py
# Логика отправки контента (функции, которые вызывает button_handlers)

import random
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.enums import ParseMode

from bot.config import settings, logger
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import (
    get_main_keyboard, get_broadcast_keyboard, 
    get_payment_keyboard
)
from bot.utils import safe_send, get_user_tz

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def notify_admins(bot: Bot, text: str):
    """Отправляет уведомление админу (используя ADMIN_CHAT_ID)."""
    admin_id = settings.ADMIN_CHAT_ID
    if admin_id:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")
            pass

# --- ЛОГИКА СТАРТА ---
async def handle_start_command(message: Message, static_data: dict, user_data: dict, lang: Lang, is_new_user: bool = False):
    user_id = message.from_user.id
    bot = message.bot
    name = message.from_user.first_name
    
    if is_new_user:
        # 🔥 ИСПРАВЛЕНИЕ: Используем REGULAR_DEMO_DAYS
        days = getattr(settings, 'REGULAR_DEMO_DAYS', 30) 
        expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=days)).isoformat()
        
        await db.update_user(user_id, status="active_demo", active=True, demo_count=1, demo_expiration=expiration, language=lang)
        user_data.update({"status": "active_demo", "active": True, "demo_count": 1, "demo_expiration": expiration, "language": lang})

        # ✅ ИСПОЛЬЗУЕМ welcome_new для НОВЫХ пользователей
        welcome_text = t('welcome_new', lang, name=name, demo_days=days) 
        kb = get_main_keyboard(lang)
        await message.answer(welcome_text, reply_markup=kb, parse_mode="HTML")
        
        await notify_admins(bot, f"🆕 <b>Новый пользователь!</b>\n👤 {name} (ID: <code>{user_id}</code>)\n🌍 Язык: {lang}")
    else:
        status_text = t('status_premium', lang) if user_data.get("is_paid") else t('status_demo', lang)
        days_left_str = "∞"
        
        if not user_data.get("is_paid"):
            exp = user_data.get("demo_expiration")
            if exp:
                dt_exp = datetime.fromisoformat(exp)
                now = datetime.now(ZoneInfo("UTC"))
                days_left = (dt_exp - now).days
                days_left_str = str(max(0, days_left))
                # Обновляем status_text для демо-периода
                status_text = f"{t('status_demo', lang)} ({days_left_str} дн.)" 
            else:
                days_left_str = "0"
                status_text = f"{t('status_demo', lang)} (0 дн.)" 
        
        # ✅ ИСПОЛЬЗУЕМ welcome_return для ВЕРНУВШИХСЯ пользователей
        welcome_text = t('welcome_return', lang, name=name, status_text=status_text)
        
        kb = get_main_keyboard(lang)
        await message.answer(welcome_text, reply_markup=kb, parse_mode="HTML")
        
        if user_id != settings.ADMIN_CHAT_ID: 
             await notify_admins(bot, f"👋 <b>Пользователь вернулся:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

# --- ОТПРАВКА ИЗ СПИСКА (Мотивация, Ритм) ---
async def send_from_list(message: Message, static_data: dict, user_data: dict, lang: Lang, list_key: str, title_key: str):
    """Универсальная функция отправки цитаты из списка."""
    content_data = static_data.get(list_key, {})
    
    if isinstance(content_data, dict):
        phrases = content_data.get(lang, content_data.get("ru", []))
    elif isinstance(content_data, list):
        phrases = content_data
    else:
        phrases = []

    if not phrases:
        await message.answer(t('list_empty', lang, title=t(title_key, lang)))
        return

    phrase_raw = random.choice(phrases)
    
    if isinstance(phrase_raw, dict):
        phrase = phrase_raw.get("text") or phrase_raw.get("content") or str(phrase_raw)
    else:
        phrase = str(phrase_raw)

    try:
        phrase = phrase.format(name=user_data.get("name", "друг"))
    except Exception:
        pass

    kb = get_broadcast_keyboard(lang, quote_text=phrase, category=list_key, user_name=user_data.get("name", "друг"))
    
    await message.answer(phrase, reply_markup=kb, parse_mode="HTML")

# --- ОТПРАВКА ПРАВИЛ ---
async def send_rules(message: Message, static_data: dict, user_data: dict, lang: Lang):
    user_tz = get_user_tz(user_data)
    today_iso = datetime.now(user_tz).date().isoformat()
    
    if user_data.get("last_rules_date") != today_iso:
        await db.update_user(message.from_user.id, last_rules_date=today_iso, rules_shown_count=0, rules_indices_today=json.dumps([]))
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

    available_indices = [i for i in range(len(rules_list)) if i not in shown_indices]
    
    if not available_indices:
        available_indices = range(len(rules_list))

    idx = random.choice(available_indices)
    rule_text = rules_list[idx]
    
    new_shown = shown_indices + [idx]
    await db.update_user(
        message.from_user.id, 
        rules_shown_count=shown_count + 1, 
        rules_indices_today=json.dumps(new_shown)
    )
    user_data["rules_shown_count"] = shown_count + 1
    user_data["rules_indices_today"] = new_shown

    header = t('title_rules_daily', lang, title=t('title_rules', lang), count=shown_count + 1, limit=settings.RULES_PER_DAY_LIMIT)
    text = f"{header}\n\n{rule_text}"
    
    kb = get_broadcast_keyboard(lang, quote_text=rule_text, category="rules")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- ПРОФИЛЬ ---
async def send_profile(message: Message, user_data: dict, lang: Lang):
    status = t('status_premium', lang) if user_data.get("is_paid") else t('status_demo', lang)
    
    text = (
        f"{t('profile_title', lang)}\n\n"
        f"{t('profile_name', lang)}: <b>{user_data.get('name')}</b>\n"
        f"{t('profile_status', lang)}: <b>{status}</b>\n\n"
        f"{t('profile_challenges_accepted', lang)}: <b>{len(user_data.get('challenges', []))}</b>\n"
        f"{t('profile_challenge_streak', lang)}: <b>{user_data.get('challenge_streak', 0)}</b> 🔥\n\n"
        f"{t('profile_likes', lang)}: <b>{user_data.get('stats_likes', 0)}</b>\n"
        f"{t('profile_dislikes', lang)}: <b>{user_data.get('stats_dislikes', 0)}</b>"
    )
    await message.answer(text, parse_mode="HTML")

# --- ОПЛАТА И ДЕМО ---
async def send_payment_instructions(message: Message, user_data: dict, lang: Lang):
    kb = get_payment_keyboard(lang, is_test_user=(message.from_user.id == settings.ADMIN_CHAT_ID))
    await message.answer(t('pay_instructions', lang, name=message.from_user.first_name), reply_markup=kb, parse_mode="Markdown")

async def activate_new_demo(message: Message, user_data: dict, lang: Lang):
    days = settings.REGULAR_DEMO_DAYS
    expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=days)).isoformat()
    await db.update_user(message.from_user.id, status="active_demo", active=True, demo_expiration=expiration)
    user_data.update({"status": "active_demo", "active": True, "demo_expiration": expiration})
    
    await message.answer(t('welcome_renewed_demo', lang, name=message.from_user.first_name, demo_days=days), reply_markup=get_main_keyboard(lang))

async def handle_expired_demo(message: Message, user_data: dict, lang: Lang):
    await message.answer(t('demo_expired_final', lang, name=message.from_user.first_name), reply_markup=get_payment_keyboard(lang))