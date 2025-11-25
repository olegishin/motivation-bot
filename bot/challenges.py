# 7 - bot/challenges.py
# Обработка/логика челленджей

import random
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any

from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ✅ ИСПРАВЛЕНО: Импорты с префиксом bot.
from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send, get_user_tz

class ChallengeStates(StatesGroup):
    pending = State()

async def send_new_challenge_message(
    event: Message | CallbackQuery, 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext, 
    is_edit: bool = False
):
    chat_id = event.from_user.id
    challenge_list = static_data.get("challenges", {}).get(lang, [])
    
    if not challenge_list:
        logger.error(f"Challenge list empty for lang {lang}")
        return

    try:
        challenge_raw = random.choice(challenge_list)
        user_name = user_data.get("name", "друг")
        formatted_challenge = challenge_raw.format(name=user_name)
        
        await state.set_state(ChallengeStates.pending)
        await state.update_data(pending_challenge_text=formatted_challenge)

        kb = InlineKeyboardBuilder()
        kb.button(text=t('btn_challenge_accept', lang), callback_data="accept_current_challenge")
        kb.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
        text = t('challenge_new_day', lang, challenge_text=formatted_challenge)
        
        sent_message = None
        if is_edit and isinstance(event, CallbackQuery) and event.message:
            sent_message = await event.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        elif isinstance(event, Message):
            sent_message = await event.answer(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        
        if sent_message:
            await state.update_data(challenge_message_id=sent_message.message_id)

        user_tz = get_user_tz(user_data)
        today_iso = datetime.now(user_tz).date().isoformat()
        
        await db.update_user(chat_id, last_challenge_date=today_iso, challenge_accepted=False)
        user_data["last_challenge_date"] = today_iso
        user_data["challenge_accepted"] = False

    except Exception as e:
        logger.exception(f"Unexpected error sending challenge to {chat_id}:")

async def accept_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    chat_id = query.from_user.id
    fsm_data = await state.get_data()
    challenge_text = fsm_data.get("pending_challenge_text")
    message_id = fsm_data.get("challenge_message_id")

    if not query.message or not challenge_text or not message_id or message_id != query.message.message_id:
        await query.answer(t('challenge_accept_error', lang), show_alert=True)
        try: await query.message.edit_text(query.message.text, reply_markup=None, parse_mode=ParseMode.HTML)
        except TelegramBadRequest: pass
        return

    challenge_history = user_data.get("challenges", [])
    if isinstance(challenge_history, str):
        try: challenge_history = json.loads(challenge_history)
        except: challenge_history = []
        
    challenge_entry = {"text": challenge_text, "accepted": datetime.now(ZoneInfo("UTC")).isoformat(), "completed": None}
    challenge_history.append(challenge_entry)
    accepted_challenge_index = len(challenge_history) - 1
    
    await db.update_user(chat_id, challenge_accepted=True, challenges=json.dumps(challenge_history))
    user_data["challenge_accepted"] = True
    user_data["challenges"] = challenge_history
    
    await state.set_state(None)
    await state.update_data(challenge_message_id=message_id)

    kb = InlineKeyboardBuilder()
    kb.button(text=t('btn_challenge_complete', lang), callback_data=f"complete_challenge:{accepted_challenge_index}")
    
    try:
        await query.message.edit_text(t('challenge_accepted_msg', lang, challenge_text=challenge_text), reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    except TelegramBadRequest as e: logger.error(f"Failed to edit message {message_id}: {e}")
    finally: await query.answer(t('challenge_accepted_msg', lang))


async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    chat_id = query.from_user.id
    fsm_data = await state.get_data()
    message_id = fsm_data.get("challenge_message_id")

    if not query.message or not message_id or message_id != query.message.message_id:
        await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
        try: await query.message.edit_text(t('challenge_completed_edit_err', lang), reply_markup=None)
        except TelegramBadRequest: pass
        return
    
    try:
        challenge_index_to_complete = int(query.data.split(":")[-1])
        challenge_history = user_data.get("challenges", [])
        if isinstance(challenge_history, str): challenge_history = json.loads(challenge_history)
        
        if 0 <= challenge_index_to_complete < len(challenge_history):
            if challenge_history[challenge_index_to_complete].get("completed"):
                await query.answer(t('challenge_completed_msg', lang))
                return

            challenge_history[challenge_index_to_complete]["completed"] = datetime.now(ZoneInfo("UTC")).isoformat()
            current_streak = user_data.get("challenge_streak", 0) + 1
            
            await db.update_user(chat_id, challenge_streak=current_streak, challenges=json.dumps(challenge_history), challenge_accepted=False)
            user_data["challenge_streak"] = current_streak
            user_data["challenges"] = challenge_history

            await state.clear()
            original_text = query.message.text
            confirmation_text = t('challenge_completed_msg', lang)
            
            await query.message.edit_text(f"{original_text}\n\n<b>{confirmation_text}</b>", reply_markup=None, parse_mode=ParseMode.HTML)

            if current_streak == 3:
                await safe_send(query.bot, chat_id, t('challenge_streak_3_level_1', lang, name=user_data.get("name", "друг")))
        else:
            await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
    except Exception as e:
        logger.exception(f"Error processing complete_challenge for {chat_id}:")
        await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
    finally:
        await query.answer(t('challenge_completed_msg', lang))