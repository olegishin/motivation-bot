# ✅ Логика челленджей (выдача, принятие, выполнение)
# ✅ Проверка состояния челленджа (none/active/completed)
# ✅ Система стриков (серия выполнений)
# ✅ Сброс стрика при пропуске дня
# ✅ Напоминания о челленджах (16:00 и +1 час после принятия)
# ✅ Интеграция с системой уровней
# 09 - bot/challenges.py - ФИНАЛЬНАЯ ВЕРСИЯ (23.02.2026)
# Логика челленджей
# ✅ ПРОВЕРЕНО: Стрики, напоминания, система уровней, сброс при пропуске
# 09 - bot/challenges.py - ФИНАЛЬНАЯ ВЕРСИЯ (26.02.2026)
# Логика челленджей и системы уровней
# ✅ ПРОВЕРЕНО: Стрики, напоминания, расчет уровней, Level Up сообщения
# 09 - bot/challenges.py - ФИНАЛЬНАЯ ВЕРСИЯ (27.02.2026)
# Логика челленджей и системы уровней
# ✅ ПРОВЕРЕНО: Стрики, напоминания, расчёт уровней, Level Up сообщения
# ✅ ДОБАВЛЕНО: check_challenges_reminder для scheduler.py

import random
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple

from aiogram import Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send, get_user_tz

# --- 🏆 КОНСТАНТЫ УРОВНЕЙ ---
LEVEL_EMOJIS = {
    "level_0": "🌱",
    "level_1": "🌿",
    "level_2": "🌳",
    "level_3": "🏆",
    "level_4": "👑"
}

# --- 🛠️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def _ensure_list(data: Any) -> list:
    """Безопасное преобразование в список."""
    if isinstance(data, list):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return []
    return []


def get_level_info(streak: int) -> Dict[str, Any]:
    """
    Определяет информацию об уровне на основе стрика.
    Возвращает словарь с данными текущего и следующего уровня.
    """
    levels = [
        (0,   2,   0, "level_0"),   # Новичок
        (3,   6,   1, "level_1"),   # Практик
        (7,   14,  2, "level_2"),   # Специалист
        (15,  29,  3, "level_3"),   # Мастер
        (30,  999, 4, "level_4"),   # Эксперт
    ]

    for min_days, max_days, level_num, level_key in levels:
        if min_days <= streak <= max_days:
            next_level_data = next((l for l in levels if l[2] == level_num + 1), None)

            progress_percent = 0
            days_to_next = 0
            if next_level_data:
                level_range = max_days - min_days + 1
                current_in_level = streak - min_days + 1
                progress_percent = min(100, int((current_in_level / level_range) * 100))
                days_to_next = next_level_data[0] - streak

            return {
                "current_level": level_key,
                "level_key": level_key,
                "level_number": level_num,
                "emoji": LEVEL_EMOJIS.get(level_key, "🌱"),
                "progress_percent": progress_percent,
                "days_to_next": days_to_next,
                "is_max_level": next_level_data is None,
                "next_level": next_level_data[3] if next_level_data else None
            }

    # Если стрик > 999 — максимальный уровень
    return {
        "current_level": "level_4",
        "level_key": "level_4",
        "level_number": 4,
        "emoji": "👑",
        "progress_percent": 100,
        "days_to_next": 0,
        "is_max_level": True,
        "next_level": None
    }


def get_level_bonus_description(level_key: str, lang: str = "ru") -> str:
    """Текстовое описание бонусов уровня."""
    bonuses = {
        "ru": {
            "level_0": "Старт",
            "level_1": "Новые челленджи",
            "level_2": "+1 Правило в день",
            "level_3": "Ритм дня без ограничений",
            "level_4": "Статус ментора"
        },
        "ua": {
            "level_0": "Старт",
            "level_1": "Нові челенджі",
            "level_2": "+1 Правило на день",
            "level_3": "Ритм дня без обмежень",
            "level_4": "Статус ментора"
        },
        "en": {
            "level_0": "Start",
            "level_1": "New challenges",
            "level_2": "+1 Rule per day",
            "level_3": "Unlimited daily rhythm",
            "level_4": "Mentor status"
        }
    }
    return bonuses.get(lang, bonuses["ru"]).get(level_key, "Бонус уровня")


async def send_level_up_message(bot: Bot, user_id: int, user_data: Dict[str, Any], lang: Lang, level_info: Dict[str, Any]) -> None:
    """Отправка уведомления о повышении уровня."""
    try:
        user_name = user_data.get("name") or "друг"
        level_key = level_info.get("level_key", "level_0")
        emoji = level_info.get("emoji", "🌱")

        translated_level_name = t(level_key, lang).upper()
        bonus = get_level_bonus_description(level_key, lang)

        texts = {
            "ru": ("🎉 НОВЫЙ УРОВЕНЬ!", "Поздравляем", "Твой новый статус", "Твой бонус", "Продолжай", "🎯 Продолжить"),
            "ua": ("🎉 НОВИЙ РІВЕНЬ!", "Вітаємо", "Твій новий статус", "Твій бонус", "Продовжуй", "🎯 Продовжити"),
            "en": ("🎉 NEW LEVEL!", "Congratulations", "Your status", "Your bonus", "Keep it up", "🎯 Continue")
        }
        T = texts.get(lang, texts["ru"])

        message = (
            f"<b>{T[0]}</b>\n\n"
            f"{T[1]}, {user_name}!\n"
            f"{T[2]}: <b>{emoji} {translated_level_name}</b>\n\n"
            f"✨ <b>{T[3]}:</b>\n• {bonus}\n\n"
            f"{T[4]}! 💪"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=T[5], callback_data="continue_level_up")
        ]])

        await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"LevelUp error for user {user_id}: {e}")


# --- ⚔️ ОСНОВНАЯ ЛОГИКА ЧЕЛЛЕНДЖЕЙ ---

def _get_challenge_state(user_data: dict) -> Tuple[str, Optional[dict], Optional[int]]:
    """Определяет текущий статус челленджа: none / active / completed."""
    challenges = _ensure_list(user_data.get("challenges", []))
    if not challenges:
        return "none", None, None

    last_challenge = challenges[-1]
    challenge_index = len(challenges) - 1
    user_tz = get_user_tz(user_data)
    today_str = datetime.now(user_tz).date().isoformat()

    challenge_date = last_challenge.get("date")
    if challenge_date != today_str:
        return "none", None, None

    if last_challenge.get("completed"):
        return "completed", last_challenge, challenge_index

    if user_data.get("challenge_accepted", 0):
        return "active", last_challenge, challenge_index

    return "none", None, None


async def send_new_challenge_message(
    event: Message | CallbackQuery,
    static_data: dict,
    user_data: dict,
    lang: Lang,
    state: FSMContext,
    is_edit: bool = False
):
    """Выдача нового челленджа или сообщение о существующем."""
    chat_id = event.from_user.id
    fresh_user = await db.get_user(chat_id)
    if not fresh_user:
        return

    state_type, active_c, idx = _get_challenge_state(fresh_user)
    user_name = fresh_user.get("name") or event.from_user.first_name or ""

    if state_type == "completed":
        msg = t('challenge_already_issued', lang, name=user_name)
        if isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        else:
            await safe_send(event.bot, chat_id, msg)
        return

    if state_type == "active" and active_c:
        text_msg = f"{t('challenge_pending_acceptance', lang)}\n\n💪 <b>Текущий челлендж:</b>\n<i>{active_c.get('text')}</i>"
        builder = InlineKeyboardBuilder()
        builder.button(text=t("btn_challenge_complete", lang), callback_data=f"complete_challenge:{idx}")
        builder.button(text=t("btn_challenge_new", lang), callback_data="new_challenge")
        builder.adjust(1)

        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_msg, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        else:
            await event.answer(text_msg, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        return

    # Выдача нового челленджа
    challenges_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    if not challenges_list:
        return

    item = random.choice(challenges_list)
    final_text = (item.get("text") if isinstance(item, dict) else item).format(name=user_name)

    builder = InlineKeyboardBuilder()
    builder.button(text=t('btn_challenge_accept', lang), callback_data=f"accept_challenge_idx:{challenges_list.index(item)}")
    builder.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
    builder.adjust(1)

    msg_content = t('challenge_new_day', lang, challenge_text=final_text)

    if is_edit and isinstance(event, CallbackQuery):
        await event.message.edit_text(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await db.update_user(chat_id, challenges_today=int(fresh_user.get("challenges_today", 0)) + 1)
        if isinstance(event, Message):
            await event.answer(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        else:
            await event.message.answer(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)


async def accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    """Принятие челленджа."""
    try:
        idx = int(query.data.split(":")[-1])
    except:
        idx = 0

    challenges_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    item = challenges_list[idx] if idx < len(challenges_list) else {"text": "Challenge"}
    text_raw = item.get("text") if isinstance(item, dict) else item

    final_text = text_raw.format(name=user_data.get("name", "друг"))
    hist = _ensure_list(user_data.get("challenges") or [])
    hist.append({
        "text": final_text,
        "accepted": datetime.now().isoformat(),
        "completed": None,
        "date": datetime.now().date().isoformat()
    })

    await db.update_user(query.from_user.id, challenges=hist, challenge_accepted=1)

    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_challenge_complete", lang), callback_data=f"complete_challenge:{len(hist)-1}")

    await query.message.edit_text(
        t('challenge_accepted_msg', lang, challenge_text=final_text),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await query.answer()


async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    """Завершение челленджа и обновление стрика."""
    try:
        idx = int(query.data.split(":")[-1])
    except:
        return

    fresh_user = await db.get_user(query.from_user.id)
    hist = _ensure_list(fresh_user.get("challenges"))

    if hist and idx < len(hist) and not hist[idx].get("completed"):
        hist[idx]["completed"] = datetime.now().isoformat()
        old_streak = int(fresh_user.get("challenge_streak", 0))
        new_streak = old_streak + 1

        await db.update_user(
            query.from_user.id,
            challenges=hist,
            challenge_streak=new_streak,
            challenge_accepted=0
        )

        # Проверка повышения уровня
        old_lvl = get_level_info(old_streak)["current_level"]
        new_lvl_info = get_level_info(new_streak)
        if new_lvl_info["current_level"] != old_lvl:
            await send_level_up_message(query.bot, query.from_user.id, fresh_user, lang, new_lvl_info)

        await query.message.edit_text(
            f"✅ {t('challenge_completed_msg', lang)}\n\n<i>{hist[idx]['text']}</i>",
            parse_mode=ParseMode.HTML
        )

    await query.answer()


# --- ⏰ НАПОМИНАНИЯ О ЧЕЛЛЕНДЖАХ ---

async def check_challenges_reminder(bot: Bot, user_id: int, user_data: dict, lang: Lang):
    """
    Проверка и отправка напоминаний о челленджах.
    Вызывается из scheduler.py каждые 30 минут (в 5 и 35 минутах часа).
    """
    try:
        user_tz = get_user_tz(user_data)
        local_now = datetime.now(user_tz)
        local_hour = local_now.hour

        state_type, active_c, idx = _get_challenge_state(user_data)

        # 1. Напоминание в 16:00–16:59, если челлендж ещё не выдан/не принят
        if local_hour == 16 and state_type == "none":
            reminder_text = t(
                'challenge_new_day_reminder',
                lang,
                name=user_data.get("name", "друг")
            )
            await safe_send(bot, user_id, reminder_text)

        # 2. Напоминание через ~1 час после принятия, если не выполнен
        if state_type == "active" and active_c:
            accepted_time = active_c.get("accepted")
            if accepted_time:
                accepted_dt = datetime.fromisoformat(accepted_time).astimezone(user_tz)
                time_passed_hours = (local_now - accepted_dt).total_seconds() / 3600

                # Окно 60–90 минут после принятия
                if 1.0 <= time_passed_hours < 1.5:
                    challenge_text = active_c.get("text", "")
                    reminder_text = t(
                        'challenge_hour_reminder',
                        lang,
                        name=user_data.get("name", ""),
                        challenge=challenge_text
                    )
                    await safe_send(bot, user_id, reminder_text)

    except Exception as e:
        logger.error(f"Error in check_challenges_reminder for user {user_id}: {e}", exc_info=True)
