# 08 - bot/content_handlers.py
# Логика отправки контента (функции, которые вызывает button_handlers)
# Полная эталонная версия: Лимиты 5+1+5, Синхронизация кэша, Логика Демо
# Логика отправки контента (Фикс реакций: Цитирование + Галочки)
# Логика отправки контента (ФИНАЛЬНАЯ ВЕРСИЯ: Цитирование + Галочки + Умные уведомления)
# Логика отправки контента (ФИНАЛЬНАЯ ВЕРСИЯ: Большое окно уведомления show_alert=True)
# Логика отправки контента (ФИНАЛЬНАЯ ВЕРСИЯ: Фикс отображения лайков в профиле)
# Логика отправки контента (ФИНАЛЬНАЯ ВЕРСИЯ: Фикс импорта + Лайки в профиле)
# Логика отправки контента (ФИНАЛЬНЫЙ ФИКС: Гарантированное обновление лайков в БД)
# ФИНАЛЬНАЯ ВЕРСИЯ: Синхронизация полей статистики для WebApp Профиля
# ФИНАЛЬНАЯ ВЕРСИЯ: Исправлена ошибка базы данных (no such column)
# ФИНАЛЬНАЯ ВЕРСИЯ: Синхронизация полей статистики для WebApp Профиля
# Логика отправки контента (функции, которые вызывает button_handlers)
# Логика отправки контента (Ультимативная версия: Guard + Logs + Admin Notif)
# Логика отправки контента (функции, которые вызывает button_handlers)
# Ультимативная версия: Guard + Logs + Admin Notif + WebApp Sync
# Логика отправки контента (функции, которые вызывает button_handlers)
# Ультимативная версия: Guard + Logs + Admin Notif + WebApp Sync
# (ФИНАЛЬНАЯ ВЕРСИЯ: Текст оплаты берет данные из конфига)
# ГРУППА 2: ФИНАЛЬНАЯ ВЕРСИЯ (ULTIMATE 10/10)
# Динамические ключи статистики, DRY-рефакторинг, расширенное логирование
# ГРУППА 2: ФИНАЛЬНАЯ ВЕРСИЯ (ULTIMATE 10/10)
# ✅ ИСПРАВЛЕНО (2026-01-18): 
#    - Первая оценка: цитирование сообщения + статистика
#    - Повторная оценка: центральное окно alert (show_alert=True)
#    - Убрана избыточная всплывашка при первой оценке (только цитата)
#    - Сохранены: лимиты, синхронизация WebApp, логика Демо

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

from bot.config import settings, logger
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import (
    get_main_keyboard, get_broadcast_keyboard,
    get_payment_keyboard
)
from bot.utils import get_user_tz, get_demo_config

# --- 🛡️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def notify_admins(bot: Bot, text: str):
    """Отправляет уведомление администратору."""
    admin_id = settings.ADMIN_CHAT_ID
    if admin_id:
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Handlers: Admin notify failed: {e}")

# --- 🚀 ЛОГИКА СТАРТА ---

async def handle_start_command(message: Message, static_data: dict, user_data: dict, lang: Lang, is_new_user: bool = False):
    user_id = message.from_user.id
    bot = message.bot
    name = message.from_user.first_name

    if is_new_user:
        config = get_demo_config(user_id)
        days = config["demo"]
        expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=days)).isoformat()

        await db.update_user(
            user_id,
            status="active_demo",
            active=True,
            demo_count=1,
            demo_expiration=expiration,
            language=lang
        )

        welcome_text = t('welcome', lang, name=name, demo_days=days)
        kb = get_main_keyboard(lang, user_id=user_id)
        await message.answer(welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)

        await notify_admins(bot, f"🆕 <b>Новый пользователь!</b>\n👤 {name} (ID: <code>{user_id}</code>)\n🌍 Язык: {lang}")
    else:
        is_paid = user_data.get("is_paid", False)
        status_text = t('status_premium', lang) if is_paid else t('status_demo', lang)

        if not is_paid:
            exp = user_data.get("demo_expiration")
            if exp:
                try:
                    dt_exp = datetime.fromisoformat(exp.replace('Z', '+00:00'))
                    days_left = (dt_exp - datetime.now(ZoneInfo("UTC"))).days
                    status_text = f"{t('status_demo', lang)} ({max(0, days_left)} {t('profile_days_unit', lang)})"
                except Exception:
                    status_text = t('status_demo', lang)

        welcome_text = t('welcome_return', lang, name=name, status_text=status_text)
        kb = get_main_keyboard(lang, user_id=user_id)
        await message.answer(welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)

        if user_id != settings.ADMIN_CHAT_ID:
            await notify_admins(bot, f"👋 <b>Пользователь вернулся:</b>\n👤 {name} (ID: <code>{user_id}</code>)")

# --- 📜 ОТПРАВКА КОНТЕНТА ---

async def send_from_list(message: Message, static_data: dict, user_data: dict, lang: Lang, list_key: str, title_key: str):
    if getattr(message, f"_handled_{list_key}", False):
        return
    setattr(message, f"_handled_{list_key}", True)

    content_data = static_data.get(list_key, {})
    phrases = content_data.get(lang, content_data.get("ru", [])) if isinstance(content_data, dict) else content_data

    if not phrases or not isinstance(phrases, list):
        logger.error(f"Handlers: Content list {list_key} is empty/invalid for user {message.from_user.id}.")
        await message.answer(t('list_empty', lang, title=t(title_key, lang)))
        return

    phrase_raw = random.choice(phrases)
    phrase = str(phrase_raw.get("text") or phrase_raw.get("content") or phrase_raw) if isinstance(phrase_raw, dict) else str(phrase_raw)

    user_name = user_data.get("name") or message.from_user.first_name
    try:
        phrase = phrase.format(name=user_name)
    except Exception as e:
        logger.error(f"Format error in {list_key} for {message.from_user.id}: {e}")

    kb = get_broadcast_keyboard(lang, quote_text=phrase, category=list_key, user_name=user_name)
    await message.answer(phrase, reply_markup=kb, parse_mode=ParseMode.HTML)

# --- ❤️ ЛОГИКА РЕАКЦИЙ (ОБЩАЯ) ---

async def _handle_reaction(callback: CallbackQuery, user_data: dict, lang: Lang, reaction_type: str):
    """
    Универсальный обработчик реакций.
    - Первый раз: цитирование сообщения + запись в статистику.
    - Повторно: центральное всплывающее окно Alert (show_alert=True).
    """
    user_id = callback.from_user.id
    name = user_data.get("name") or callback.from_user.first_name or "Користувач"

    # 1. Проверка на повторную оценку (по наличию ✅ в кнопках)
    has_reaction = any(
        "✅" in btn.text 
        for row in (callback.message.reply_markup.inline_keyboard or []) 
        for btn in row
    )

    if has_reaction:
        # Повтор → Центральное окно (Alert)
        logger.debug(f"Reaction: User {user_id} tried duplicate reaction on {callback.message.message_id}")
        await callback.answer(
            t('reaction_already_accepted', lang, name=name),
            show_alert=True
        )
        return

    # 2. ПЕРВАЯ оценка → Запись в статистику БД
    stat_key = f"stats_{reaction_type}s"
    fresh_user = await db.get_user(user_id)
    new_val = (fresh_user.get(stat_key, 0) if fresh_user else 0) + 1
    await db.update_user(user_id, **{stat_key: new_val})
    logger.info(f"Reaction: {reaction_type} from {user_id} (+1 to {stat_key})")

    # 3. Обновление клавиатуры (добавляем ✅)
    category = callback.data.split(":")[-1] if ":" in callback.data else "default"
    new_kb = get_broadcast_keyboard(
        lang=lang, 
        quote_text=callback.message.text, 
        category=category, 
        current_reaction=reaction_type, 
        user_name=name
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=new_kb)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"Reaction ({reaction_type}) KB update error: {e}")

    # 4. Ответ сообщением с цитированием (Reply)
    await callback.message.reply(
        t('reaction_received', lang, name=name),
        parse_mode=ParseMode.HTML
    )

    # 5. Убираем "часики" (без текста, так как есть цитата в чате)
    await callback.answer()

async def handle_like(callback: CallbackQuery, user_data: dict, lang: Lang):
    await _handle_reaction(callback, user_data, lang, "like")

async def handle_dislike(callback: CallbackQuery, user_data: dict, lang: Lang):
    await _handle_reaction(callback, user_data, lang, "dislike")

# --- ⚖️ ПРАВИЛА ---

async def send_rules(message: Message, static_data: dict, user_data: dict, lang: Lang):
    user_id = message.from_user.id
    if getattr(message, "_rules_handled", False): return
    message._rules_handled = True

    fresh_user = await db.get_user(user_id)
    if fresh_user: user_data.update(fresh_user)

    user_tz = get_user_tz(user_data)
    today = datetime.now(user_tz).date().isoformat()

    if user_data.get("last_rules_date") != today:
        await db.update_user(user_id, last_rules_date=today, rules_shown_count=0, rules_indices_today=[])
        user_data.update({"last_rules_date": today, "rules_shown_count": 0, "rules_indices_today": []})

    shown_count = int(user_data.get("rules_shown_count", 0))
    if shown_count >= settings.RULES_PER_DAY_LIMIT:
        await message.answer(t('rules_limit_reached', lang))
        return

    rules_list = static_data.get("rules", {}).get(lang) or static_data.get("rules", {}).get("ru", [])
    if not rules_list:
        await message.answer(t('list_empty', lang, title="Rules"))
        return

    shown_indices = user_data.get("rules_indices_today") or []
    available = [i for i in range(len(rules_list)) if i not in shown_indices] or list(range(len(rules_list)))

    idx = random.choice(available)
    rule_text = rules_list[idx]
    new_count, new_indices = shown_count + 1, shown_indices + [idx]

    await db.update_user(user_id, rules_shown_count=new_count, rules_indices_today=new_indices)
    user_data.update({"rules_shown_count": new_count, "rules_indices_today": new_indices})

    header = t('title_rules_daily', lang, title=t('title_rules', lang), count=new_count, limit=settings.RULES_PER_DAY_LIMIT)
    kb = get_broadcast_keyboard(lang, rule_text, "rules", user_name=user_data.get("name") or message.from_user.first_name)
    await message.answer(f"<b>{header}</b>\n\n{rule_text}", reply_markup=kb, parse_mode=ParseMode.HTML)

# --- 📊 ПРОФИЛЬ ---

async def send_profile(message: Message, user_data: dict, lang: Lang):
    fresh_user = await db.get_user(message.from_user.id)
    if fresh_user: user_data.update(fresh_user)

    challenges = user_data.get("challenges", [])
    completed_count = len([c for c in challenges if isinstance(c, dict) and c.get("completed")])
    
    text = (
        f"👤 <b>{t('profile_title', lang)}</b>\n\n"
        f"📛 {t('profile_name', lang)}: <b>{user_data.get('name') or message.from_user.first_name}</b>\n"
        f"💰 {t('profile_status', lang)}: <b>{t('status_premium', lang) if user_data.get('is_paid') else t('status_demo', lang)}</b>\n\n"
        f"⚔️ {t('profile_challenges_accepted', lang)}: <b>{len(challenges)}</b>\n"
        f"✅ {t('profile_challenges_completed', lang)}: <b>{completed_count}</b>\n"
        f"🔥 {t('profile_challenge_streak', lang)}: <b>{user_data.get('challenge_streak', 0)}</b>\n\n"
        f"👍 {t('profile_likes', lang)}: <b>{user_data.get('stats_likes', 0)}</b>\n"
        f"👎 {t('profile_dislikes', lang)}: <b>{user_data.get('stats_dislikes', 0)}</b>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

# --- 💳 ПЛАТЕЖИ ---

async def send_payment_instructions(message: Message, user_data: dict, lang: Lang):
    kb = get_payment_keyboard(lang, is_test_user=(message.from_user.id == settings.ADMIN_CHAT_ID))
    await message.answer(
        t('pay_instructions', lang, 
          name=message.from_user.first_name, amount=settings.PAYMENT_AMOUNT,
          currency=settings.PAYMENT_CURRENCY, link=settings.PAYMENT_LINK),
        reply_markup=kb
    )

async def activate_new_demo(message: Message, user_data: dict, lang: Lang):
    user_id = message.from_user.id
    config = get_demo_config(user_id)
    expiration = (datetime.now(ZoneInfo("UTC")) + timedelta(days=config["demo"])).isoformat()
    await db.update_user(user_id, status="active_demo", active=True, demo_expiration=expiration, demo_count=2)
    await notify_admins(message.bot, f"🔄 <b>Демо возобновлено!</b>\n👤 {message.from_user.first_name} (ID: <code>{user_id}</code>)")
    await message.answer(t('welcome_renewed_demo', lang, name=message.from_user.first_name, demo_days=config["demo"]), reply_markup=get_main_keyboard(lang, user_id=user_id))

async def handle_expired_demo(message: Message, user_data: dict, lang: Lang):
    await message.answer(t('demo_expired_final', lang, name=message.from_user.first_name), reply_markup=get_payment_keyboard(lang))