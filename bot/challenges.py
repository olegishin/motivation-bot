# 09 - bot/challenges.py
# Обработка/логика челленджей (Stateless version - Индексный метод)

import random
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List

from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

# ✅ Импорты
from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send, get_user_tz

async def send_new_challenge_message(
    event: Message | CallbackQuery, 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext, 
    is_edit: bool = False
):
    """
    Отправляет новое случайное задание.
    Индекс задания зашивается в кнопку 'accept_challenge_idx:<index>'.
    """
    chat_id = event.from_user.id
    
    # --- 1. Получение списка ---
    challenge_list = static_data.get("challenges", {}).get(lang, [])
    if not challenge_list:
        challenge_list = static_data.get("challenges", {}).get("ru", [])
    
    if not challenge_list:
        logger.error(f"❌ Challenge list EMPTY for {chat_id}")
        await safe_send(event.bot, chat_id, "⚠️ Ошибка: Список челленджей пуст.")
        return

    try:
        # Выбираем случайный ИНДЕКС
        total_challenges = len(challenge_list)
        random_index = random.randrange(total_challenges)
        challenge_raw = challenge_list[random_index]
        
        # --- 2. Нормализация текста ---
        if isinstance(challenge_raw, dict):
            challenge_raw = challenge_raw.get("text") or challenge_raw.get("content") or str(challenge_raw)
        else:
            challenge_raw = str(challenge_raw)

        # --- 3. Форматирование ---
        user_name = user_data.get("name", "друг")
        try:
            formatted_challenge = challenge_raw.format(name=user_name)
        except Exception:
            formatted_challenge = challenge_raw

        # --- 4. Клавиатура (Ставим ИНДЕКС в callback_data) ---
        kb = InlineKeyboardBuilder()
        # Кнопка теперь содержит ID задания: accept_challenge_idx:123
        kb.button(text=t('btn_challenge_accept', lang), callback_data=f"accept_challenge_idx:{random_index}")
        kb.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
        
        text = t('challenge_new_day', lang, challenge_text=formatted_challenge)
        
        # --- 5. Отправка / Редактирование ---
        try:
            if is_edit and isinstance(event, CallbackQuery) and event.message:
                await event.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
            elif isinstance(event, Message):
                await event.answer(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        except Exception as e:
            # Игнорируем "message is not modified", если рандом выбрал то же самое
            if "message is not modified" in str(e).lower():
                if isinstance(event, CallbackQuery): await event.answer()
                return
            raise e

        # --- 6. Метка даты (чтобы знать, что пользователь активен сегодня) ---
        user_tz = get_user_tz(user_data)
        today_iso = datetime.now(user_tz).date().isoformat()
        
        if user_data.get("last_challenge_date") != today_iso:
            await db.update_user(chat_id, last_challenge_date=today_iso, challenge_accepted=False)
            user_data["last_challenge_date"] = today_iso
            user_data["challenge_accepted"] = False

    except Exception as e:
        logger.exception(f"Error in send_new_challenge: {e}")
        await safe_send(event.bot, chat_id, f"⚠️ Error: {str(e)}")


async def accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    """
    Принимает челлендж по индексу из callback_data.
    Не зависит от памяти бота.
    """
    chat_id = query.from_user.id
    
    try:
        # data format: accept_challenge_idx:123
        parts = query.data.split(":")
        if len(parts) < 2:
            await query.answer("Error code", show_alert=True)
            return
            
        challenge_index = int(parts[1])
        
        # --- 1. Достаем текст из STATIC DATA по индексу ---
        # Нам не нужно помнить текст, мы берем его снова из файла по номеру
        challenge_list = static_data.get("challenges", {}).get(lang, [])
        if not challenge_list:
            challenge_list = static_data.get("challenges", {}).get("ru", [])
            
        if challenge_index < 0 or challenge_index >= len(challenge_list):
            await query.answer("⚠️ Задание не найдено (список изменился). Нажмите 'Новый'.", show_alert=True)
            return
            
        challenge_raw = challenge_list[challenge_index]
        
        # Нормализация
        if isinstance(challenge_raw, dict):
            challenge_text_raw = challenge_raw.get("text") or str(challenge_raw)
        else:
            challenge_text_raw = str(challenge_raw)
            
        # Форматирование
        user_name = user_data.get("name", "друг")
        try:
            challenge_text = challenge_text_raw.format(name=user_name)
        except:
            challenge_text = challenge_text_raw

        # --- 2. Сохраняем в историю пользователя ---
        challenge_history = user_data.get("challenges", [])
        if isinstance(challenge_history, str):
            try: challenge_history = json.loads(challenge_history)
            except: challenge_history = []
        if not isinstance(challenge_history, list):
            challenge_history = []
            
        challenge_entry = {
            "text": challenge_text, 
            "accepted": datetime.now(ZoneInfo("UTC")).isoformat(), 
            "completed": None
        }
        challenge_history.append(challenge_entry)
        accepted_challenge_index = len(challenge_history) - 1
        
        history_json = json.dumps(challenge_history, ensure_ascii=False)
        await db.update_user(chat_id, challenge_accepted=True, challenges=history_json)
        
        user_data["challenge_accepted"] = True
        user_data["challenges"] = challenge_history
        
        # --- 3. Обновляем сообщение (ставим кнопку "Выполнено") ---
        kb = InlineKeyboardBuilder()
        kb.button(text=t('btn_challenge_complete', lang), callback_data=f"complete_challenge:{accepted_challenge_index}")
        
        try:
            await query.message.edit_text(t('challenge_accepted_msg', lang, challenge_text=challenge_text), reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        except Exception:
            pass # Если сообщение не изменилось - не страшно
                
        await query.answer(t('challenge_accepted_msg', lang))
            
    except Exception as e:
        logger.exception(f"Error in accept_challenge: {e}")
        await query.answer("Error!", show_alert=True)


async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    chat_id = query.from_user.id
    try:
        challenge_index_to_complete = int(query.data.split(":")[-1])
        
        challenge_history = user_data.get("challenges", [])
        if isinstance(challenge_history, str): 
            try: challenge_history = json.loads(challenge_history)
            except: challenge_history = []
        if not isinstance(challenge_history, list):
            challenge_history = []
        
        if 0 <= challenge_index_to_complete < len(challenge_history):
            if challenge_history[challenge_index_to_complete].get("completed"):
                await query.answer(t('challenge_completed_msg', lang))
                return

            challenge_history[challenge_index_to_complete]["completed"] = datetime.now(ZoneInfo("UTC")).isoformat()
            current_streak = user_data.get("challenge_streak", 0) + 1
            
            history_json = json.dumps(challenge_history, ensure_ascii=False)
            await db.update_user(chat_id, challenge_streak=current_streak, challenges=history_json, challenge_accepted=False)
            
            user_data["challenge_streak"] = current_streak
            user_data["challenges"] = challenge_history

            await state.clear()
            
            original_text = query.message.text
            confirmation_text = t('challenge_completed_msg', lang)
            
            try:
                await query.message.edit_text(f"{original_text}\n\n<b>{confirmation_text}</b>", reply_markup=None, parse_mode=ParseMode.HTML)
            except Exception:
                pass

            if current_streak == 3:
                await safe_send(query.bot, chat_id, t('challenge_streak_3_level_1', lang, name=user_data.get("name", "друг")))
        else:
            await query.answer(t('challenge_completed_edit_err', lang), show_alert=True)
            
    except Exception as e:
        logger.exception(f"Error in complete_challenge: {e}")
        await query.answer("Error!", show_alert=True)