# 7 - bot/challenges.py
# Обработак/логика челленджей

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

from config import logger
from localization import t, Lang
from database import db 
from bot.utils import safe_send, get_user_tz

# Состояния для FSM
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
    """Отправляет новое сообщение с челленджем."""
    chat_id = event.from_user.id
    challenge_list = static_data.get("challenges", {}).get(lang, [])
    
    if not challenge_list:
        logger.error(f"Challenge list empty for lang {lang}")
        return

    try:
        challenge_raw = random.choice(challenge_list)
        user_name = user_data.get("name", "друг")
        formatted_challenge = challenge_raw.format(name=user_name)
        
        # 1. Сохраняем в FSM для проверки при принятии/выполнении
        await state.set_state(ChallengeStates.pending)
        await state.update_data(
            pending_challenge_text=formatted_challenge
        )

        # 2. Формируем клавиатуру
        kb = InlineKeyboardBuilder()
        kb.button(text=t('btn_challenge_accept', lang), callback_data="accept_current_challenge")
        kb.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
        text = t('challenge_new_day', lang, challenge_text=formatted_challenge)
        
        # 3. Отправляем или редактируем
        sent_message = None
        if is_edit and isinstance(event, CallbackQuery) and event.message:
            sent_message = await event.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        elif isinstance(event, Message):
            sent_message = await event.answer(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        
        # 4. Сохраняем ID сообщения
        if sent_message:
            await state.update_data(challenge_message_id=sent_message.message_id)

        # 5. Обновляем статус в БД: челлендж выдан, но не принят
        user_tz = get_user_tz(user_data)
        today_iso = datetime.now(user_tz).date().isoformat()
        
        await db.update_user(
            chat_id,
            last_challenge_date=today_iso,
            challenge_accepted=False
        )
        user_data["last_challenge_date"] = today_iso
        user_data["challenge_accepted"] = False
        
        logger.debug(f"Challenge sent/edited for {chat_id}")

    except Exception as e:
        logger.exception(f"Unexpected error sending challenge to {chat_id}:")

async def accept_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    """Обрабатывает принятие челленджа."""
    chat_id = query.from_user.id
    
    fsm_data = await state.get_data()
    challenge_text = fsm_data.get("pending_challenge_text")
    message_id = fsm_data.get("challenge_message_id")

    if not query.message or not challenge_text or not message_id or message_id != query.message.message_id:
        logger.error(f"Challenge data mismatch for {chat_id} on accept.")
        await query.answer(t('challenge_accept_error', lang), show_alert=True)
        try:
            # Убираем кнопки, чтобы нельзя было повторно нажать
            await query.message.edit_text(query.message.text, reply_markup=None, parse_mode=ParseMode.HTML)
        except TelegramBadRequest: pass
        return

    # 1. Обновляем историю челленджей
    challenge_history = user_data.get("challenges", [])
    if isinstance(challenge_history, str):
        try: challenge_history = json.loads(challenge_history)
        except: challenge_history = []
        
    challenge_entry = {
        "text": challenge_text, 
        "accepted": datetime.now(ZoneInfo("UTC")).isoformat(), 
        "completed": None
    }
    challenge_history.append(challenge_entry)
    accepted_challenge_index = len(challenge_history) - 1
    
    # 2. Обновляем БД
    await db.update_user(
        chat_id,
        challenge_accepted=True,
        challenges=json.dumps(challenge_history) # Сохраняем как JSON строку
    )
    user_data["challenge_accepted"] = True
    user_data["challenges"] = challenge_history
    
    # 3. Очищаем FSM (чтобы избежать повторного принятия), но сохраняем ID для завершения
    await state.set_state(None)
    await state.update_data(challenge_message_id=message_id)

    # 4. Редактируем сообщение для завершения
    kb = InlineKeyboardBuilder()
    kb.button(text=t('btn_challenge_complete', lang), callback_data=f"complete_challenge:{accepted_challenge_index}")
    
    try:
        await query.message.edit_text(
            t('challenge_accepted_msg', lang, challenge_text=challenge_text),
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.HTML
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to edit message {message_id} for {chat_id} on accept: {e}")
    finally:
        await query.answer(t('challenge_accepted_msg', lang))


async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    """Обрабатывает завершение челленджа."""
    chat_id = query.from_user.id
    
    fsm_data = await state.get_data()
    message_id = fsm_data.get("challenge_message_id")

    if not query.message or not message_id or message_id != query.message.message_id:
        logger.error(f"No challenge message_id for {chat_id} on complete.")
        await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
        try:
            await query.message.edit_text(t('challenge_completed_edit_err', lang), reply_markup=None)
        except TelegramBadRequest: pass
        return
    
    try:
        challenge_index_to_complete = int(query.data.split(":")[-1])
        challenge_history = user_data.get("challenges", [])
        if isinstance(challenge_history, str):
            challenge_history = json.loads(challenge_history)
        
        if 0 <= challenge_index_to_complete < len(challenge_history):
            # Проверка на повторное выполнение
            if challenge_history[challenge_index_to_complete].get("completed"):
                await query.answer(t('challenge_completed_msg', lang))
                return

            challenge_history[challenge_index_to_complete]["completed"] = datetime.now(ZoneInfo("UTC")).isoformat()
            current_streak = user_data.get("challenge_streak", 0) + 1
            
            # Обновляем БД
            await db.update_user(
                chat_id,
                challenge_streak=current_streak,
                challenges=json.dumps(challenge_history), # Сохраняем как JSON строку
                challenge_accepted=False # Сбрасываем флаг, чтобы можно было взять новый на следующий день
            )
            user_data["challenge_streak"] = current_streak
            user_data["challenges"] = challenge_history

            # Очищаем FSM, так как задача выполнена
            await state.clear()
            
            original_text = query.message.text
            confirmation_text = t('challenge_completed_msg', lang)
            
            await query.message.edit_text(
                f"{original_text}\n\n<b>{confirmation_text}</b>",
                reply_markup=None,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Challenge {challenge_index_to_complete} completed by {chat_id}. New streak: {current_streak}")

            # Дополнительное сообщение за серию
            if current_streak == 3:
                await safe_send(query.bot, chat_id, t('challenge_streak_3_level_1', lang, name=user_data.get("name", "друг")))
        
        else:
            await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
            
    except Exception as e:
        logger.exception(f"Error processing complete_challenge for {chat_id}:")
        await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
    finally:
        await query.answer(t('challenge_completed_msg', lang))