# 7 - bot/challenges.py
# Обработка/логика челленджей

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
from aiogram.fsm.state import State, StatesGroup

# ✅ Импорты
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
    
    # --- 1. Получение списка ---
    challenge_list = static_data.get("challenges", {}).get(lang, [])
    if not challenge_list:
        challenge_list = static_data.get("challenges", {}).get("ru", [])
    
    if not challenge_list:
        logger.error(f"❌ Challenge list EMPTY for {chat_id}")
        await safe_send(event.bot, chat_id, "⚠️ Ошибка: Список челленджей пуст.")
        return

    try:
        challenge_raw = random.choice(challenge_list)
        
        # --- 2. Нормализация текста ---
        if isinstance(challenge_raw, dict):
            challenge_raw = challenge_raw.get("text") or challenge_raw.get("content") or str(challenge_raw)
        
        if not isinstance(challenge_raw, str):
            challenge_raw = str(challenge_raw)

        # --- 3. Форматирование ---
        user_name = user_data.get("name", "друг")
        try:
            formatted_challenge = challenge_raw.format(name=user_name)
        except Exception:
            formatted_challenge = challenge_raw

        # --- 4. Сохранение (В ПАМЯТЬ + В БАЗУ для надежности) ---
        await state.set_state(ChallengeStates.pending)
        await state.update_data(pending_challenge_text=formatted_challenge)
        
        # ✅ FIX: Сохраняем во временное поле в user_data, чтобы пережить рестарт
        # (Можно использовать поле data или отдельное, здесь пишем в data для простоты)
        user_data["pending_challenge_text"] = formatted_challenge
        # Обновляем JSON в базе, чтобы сохранить это поле
        await db.update_user(chat_id, pending_challenge_text=formatted_challenge)

        # --- 5. Клавиатура ---
        kb = InlineKeyboardBuilder()
        kb.button(text=t('btn_challenge_accept', lang), callback_data="accept_current_challenge")
        kb.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
        
        text = t('challenge_new_day', lang, challenge_text=formatted_challenge)
        
        # ✅ FIX: Ловим ошибку "Not Modified" вручную
        try:
            if is_edit and isinstance(event, CallbackQuery) and event.message:
                await event.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
            elif isinstance(event, Message):
                await event.answer(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        except Exception as e:
            # Если текст такой же, игнорируем ошибку
            if "message is not modified" in str(e).lower():
                if isinstance(event, CallbackQuery): await event.answer()
                return
            raise e # Если другая ошибка - пробрасываем дальше

        # --- 6. Метка даты ---
        user_tz = get_user_tz(user_data)
        today_iso = datetime.now(user_tz).date().isoformat()
        
        # Обновляем дату, но pending_text уже сохранен выше через update_user, 
        # поэтому здесь можно не дублировать, или обновить всё разом.
        await db.update_user(chat_id, last_challenge_date=today_iso, challenge_accepted=False)
        user_data["last_challenge_date"] = today_iso
        user_data["challenge_accepted"] = False

    except Exception as e:
        # Еще одна проверка на Not Modified на всякий случай
        if "message is not modified" in str(e).lower():
            return
            
        logger.exception(f"CRITICAL ERROR in send_challenge: {e}")
        await safe_send(event.bot, chat_id, f"⚠️ Error: {str(e)}")


async def accept_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    chat_id = query.from_user.id
    
    try:
        # --- 1. Попытка получить текст (Сначала память, потом база) ---
        fsm_data = await state.get_data()
        challenge_text = fsm_data.get("pending_challenge_text")
        
        # ✅ FIX: Если в памяти пусто (был рестарт), берем из базы
        if not challenge_text:
            challenge_text = user_data.get("pending_challenge_text")
        
        if not challenge_text:
            await query.answer("⚠️ Данные устарели. Нажмите 'Новый'!", show_alert=True)
            return

        # --- 2. Безопасное получение истории ---
        challenge_history = user_data.get("challenges", [])
        if isinstance(challenge_history, str):
            try: challenge_history = json.loads(challenge_history)
            except: challenge_history = []
        if not isinstance(challenge_history, list):
            challenge_history = []
            
        # --- 3. Добавление записи ---
        challenge_entry = {
            "text": challenge_text, 
            "accepted": datetime.now(ZoneInfo("UTC")).isoformat(), 
            "completed": None
        }
        challenge_history.append(challenge_entry)
        accepted_challenge_index = len(challenge_history) - 1
        
        # --- 4. Запись в БД ---
        history_json = json.dumps(challenge_history, ensure_ascii=False)
        
        # Убираем pending_challenge_text из базы (очистка)
        if "pending_challenge_text" in user_data:
            del user_data["pending_challenge_text"]
            
        # Обновляем базу: challenges + очистка pending
        # Примечание: update_user сохраняет переданные поля в JSON. 
        # Чтобы удалить поле, мы можем перезаписать весь JSON или просто оставить его (он не мешает).
        # Проще перезаписать.
        await db.update_user(chat_id, challenge_accepted=True, challenges=history_json, pending_challenge_text=None)
        
        user_data["challenge_accepted"] = True
        user_data["challenges"] = challenge_history
        
        await state.clear()
        
        # --- 5. Обновление сообщения ---
        kb = InlineKeyboardBuilder()
        kb.button(text=t('btn_challenge_complete', lang), callback_data=f"complete_challenge:{accepted_challenge_index}")
        
        try:
            await query.message.edit_text(t('challenge_accepted_msg', lang, challenge_text=challenge_text), reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        except Exception as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                logger.error(f"Error editing message on accept: {e}")
                
        await query.answer(t('challenge_accepted_msg', lang))
            
    except Exception as e:
        logger.exception(f"CRITICAL ERROR in accept_challenge: {e}")
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
        logger.exception(f"Error processing complete_challenge for {chat_id}: {e}")
        await query.answer("Error!", show_alert=True)
    finally:
        try: await query.answer()
        except: pass