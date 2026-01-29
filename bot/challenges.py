# 09 - bot/challenges.py
# 09 - bot/challenges.py - 27.01.2026
# bot/challenges.py — УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс лимитов и синхронизация БД
# ✅ СВЕРЕНО ПОСТРОЧНО: Сохранена вся логика Олега
# ✅ ДОБАВЛЕНО (Этап 2): Сброс стрика при пропуске дня (Duolingo Style)
# ✅ ДОБАВЛЕНО (2026-01-27): Уведомление о сбросе стрика при пропуске дня
# 09 - bot/challenges.py - ПОЛНАЯ ВЕРСИЯ (28.01.2026)
# ✅ ИСПРАВЛЕНО: Четкие состояния (none/active/completed)
# ✅ ИСПРАВЛЕНО: Кнопки "Выполнено" и "Новый" для активного состояния
# ✅ ИСПРАВЛЕНО: Защита от дублей и проверка часовых поясов
# 09 - bot/challenges.py
# ✅ ULTIMATE VERSION (28.01.2026)
# ✅ СИНХРОНИЗИРОВАНО: Полная локализация (t) + Аудит (1.b, 1.c, 1.d)
# ✅ СОХРАНЕНО: Логика сброса стриков, Idempotency Guard, часовые пояса

import random
import json
from datetime import datetime, date, timedelta
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send, get_user_tz, get_level_info, send_level_up_message
from bot.keyboards import get_challenge_complete_button

def _ensure_list(data: any) -> list:
    """Безопасное преобразование в список."""
    if isinstance(data, list): return data
    if isinstance(data, str):
        try: return json.loads(data)
        except: return []
    return []

def _get_challenge_state(user_data: dict) -> tuple[str, dict | None, int | None]:
    """Определяет состояние челленджа пользователя."""
    if user_data.get("challenge_accepted", 0) or user_data.get("challenges_today", 0) > 0:
        challenges = _ensure_list(user_data.get("challenges", []))
        if challenges:
            last_challenge = challenges[-1]
            challenge_index = len(challenges) - 1
            
            user_tz = get_user_tz(user_data)
            now_local = datetime.now(user_tz)
            today_str = now_local.date().isoformat()
            
            challenge_date = last_challenge.get("date")
            if not challenge_date and last_challenge.get("accepted"):
                try:
                    acc_dt = datetime.fromisoformat(last_challenge["accepted"].replace('Z', '+00:00'))
                    challenge_date = acc_dt.astimezone(user_tz).date().isoformat()
                except:
                    challenge_date = today_str
            
            if challenge_date != today_str:
                return "none", None, None
            
            if last_challenge.get("completed"):
                return "completed", last_challenge, challenge_index
            
            if user_data.get("challenge_accepted", 0):
                return "active", last_challenge, challenge_index

    return "none", None, None

async def send_new_challenge_message(event: Message | CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext, is_edit: bool = False):
    """Выдача челленджа с учетом аудита."""
    chat_id = event.from_user.id
    
    if not is_edit and getattr(event, "_challenge_handled", False):
        return
    setattr(event, "_challenge_handled", True)
    
    fresh_user = await db.get_user(chat_id)
    if not fresh_user: return

    challenge_state, active_challenge, challenge_index = _get_challenge_state(fresh_user)
    user_name = fresh_user.get("name") or event.from_user.first_name or ""
    
    # 1. Если челлендж ВЫПОЛНЕН сегодня
    if challenge_state == "completed":
        msg = t('challenge_already_issued', lang, name=user_name)
        if isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        else:
            await safe_send(event.bot, chat_id, msg)
        return
    
    # 2. Если челлендж АКТИВЕН (принят, но не выполнен)
    if challenge_state == "active" and active_challenge:
        challenge_text = active_challenge.get("text", "...")
        text_msg = f"{t('challenge_pending_acceptance', lang)}\n\n💪 <b>Текущий челлендж:</b>\n<i>{challenge_text}</i>"
        
        builder = InlineKeyboardBuilder()
        builder.button(text=t("btn_challenge_complete", lang), callback_data=f"complete_challenge:{challenge_index}")
        builder.button(text=t("btn_challenge_new", lang), callback_data="new_challenge")
        builder.adjust(1)
        
        if isinstance(event, CallbackQuery):
            try:
                await event.message.edit_text(text_msg, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
            except:
                await safe_send(event.bot, chat_id, text_msg, reply_markup=builder.as_markup())
        else:
            await event.answer(text_msg, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        return
    
    # 3. Выдача НОВОГО челленджа
    user_tz = get_user_tz(fresh_user)
    now_local = datetime.now(user_tz)
    today_str = now_local.date().isoformat()
    last_challenge_date = str(fresh_user.get("last_challenge_date") or "")

    if last_challenge_date != today_str:
        upd_params = {"last_challenge_date": today_str, "challenges_today": 0, "challenge_accepted": 0}
        if last_challenge_date:
            try:
                last_date = date.fromisoformat(last_challenge_date)
                if (now_local.date() - last_date).days > 1:
                    previous_streak = fresh_user.get("challenge_streak", 0)
                    upd_params["challenge_streak"] = 0
                    await db.update_user(chat_id, **upd_params)
                    streak_lost_msg = t('streak_lost_missed_day', lang, name=user_name, previous_streak=previous_streak)
                    await safe_send(event.bot, chat_id, streak_lost_msg, parse_mode=ParseMode.HTML)
                else:
                    await db.update_user(chat_id, **upd_params)
            except:
                await db.update_user(chat_id, **upd_params)
        else:
            await db.update_user(chat_id, **upd_params)
        fresh_user = await db.get_user(chat_id)

    if not is_edit and int(fresh_user.get("challenges_today", 0)) >= 1:
        msg = t('challenge_already_issued', lang, name=user_name)
        if isinstance(event, CallbackQuery): await event.answer(msg, show_alert=True)
        else: await safe_send(event.bot, chat_id, msg)
        return

    challenges_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    if not challenges_list: return await safe_send(event.bot, chat_id, "⚠️ Challenges list empty.")

    idx = random.randrange(len(challenges_list))
    item = challenges_list[idx]
    text_raw = str(item.get("text") if isinstance(item, dict) else item)
    final_text = text_raw.format(name=user_name)

    builder = InlineKeyboardBuilder()
    builder.button(text=t('btn_challenge_accept', lang), callback_data=f"accept_challenge_idx:{idx}")
    builder.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
    builder.adjust(1)
    
    msg_content = t('challenge_new_day', lang, challenge_text=final_text)

    if is_edit and isinstance(event, CallbackQuery):
        await event.message.edit_text(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    else:
        new_attempts = int(fresh_user.get("challenges_today", 0)) + 1
        await db.update_user(chat_id, last_challenge_date=today_str, challenges_today=new_attempts)
        if isinstance(event, Message): await event.answer(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        else: await event.message.answer(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

async def accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    """Принятие челленджа."""
    try: idx = int(query.data.split(":")[-1])
    except: idx = 0
        
    fresh_user = await db.get_user(query.from_user.id)
    challenges_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    item = challenges_list[idx] if idx < len(challenges_list) else {"text": "Challenge"}
    text_raw = str(item.get("text") if isinstance(item, dict) else item)
    
    name = fresh_user.get("name") or query.from_user.first_name or "Пользователь"
    final_text = text_raw.format(name=name)

    hist = _ensure_list(fresh_user.get("challenges") or [])
    hist.append({"text": final_text, "accepted": datetime.now().isoformat(), "completed": None, "date": datetime.now().date().isoformat()})
    
    await db.update_user(query.from_user.id, challenges=hist, challenge_accepted=1)
    await query.message.edit_text(t('challenge_accepted_msg', lang, challenge_text=final_text), 
                                reply_markup=get_challenge_complete_button(lang, len(hist)-1), parse_mode=ParseMode.HTML)
    await query.answer()

async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    """Завершение челленджа."""
    try: idx = int(query.data.split(":")[-1])
    except: return

    fresh_user = await db.get_user(query.from_user.id)
    hist = _ensure_list(fresh_user.get("challenges"))
    
    if hist and idx < len(hist) and not hist[idx].get("completed"):
        hist[idx]["completed"] = datetime.now().isoformat()
        new_streak = int(fresh_user.get("challenge_streak", 0)) + 1
        await db.update_user(query.from_user.id, challenges=hist, challenge_streak=new_streak, challenge_accepted=0)
        
        new_level_info = get_level_info(new_streak)
        if new_level_info["current_level"] != get_level_info(new_streak - 1)["current_level"]:
            await send_level_up_message(query.bot, query.from_user.id, fresh_user, lang, new_level_info)
        
        await query.message.edit_text(f"✅ {t('challenge_completed_msg', lang)}\n\n<i>{hist[idx]['text']}</i>", parse_mode=ParseMode.HTML)
    await query.answer()

# --- 🚀 НАПОМИНАНИЯ (Пункт 1.d аудита) ---

async def check_challenges_reminder(bot, user_id, user_data, lang):
    """Проверка и отправка напоминаний по челленджам."""
    state_type, active_c, _ = _get_challenge_state(user_data)
    name = user_data.get("name") or "друг"

    # i. Если челлендж не принят (16:00)
    if state_type == "none":
        await safe_send(bot, user_id, t('challenge_pending_reminder_16', lang, name=name))
        return

    # ii. Если челлендж открыт, но не выполнен (через час)
    if state_type == "active" and active_c:
        acc_time = datetime.fromisoformat(active_c["accepted"])
        if datetime.now() - acc_time > timedelta(hours=1):
            preview = active_c.get("text", "")[:100] + "..." if len(active_c.get("text", "")) > 100 else active_c.get("text", "")
            await safe_send(bot, user_id, t('challenge_hour_reminder', lang, name=name, challenge=preview))