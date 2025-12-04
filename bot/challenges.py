# 09 - bot/challenges.py

import random
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext

from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send, get_user_tz

async def send_new_challenge_message(event: Message | CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext, is_edit: bool = False):
    chat_id = event.from_user.id
    
    # 1. Берем список челленджей
    challenge_list = static_data.get("challenges", {}).get(lang, [])
    if not challenge_list:
        # Фолбэк на русский, если для языка нет
        challenge_list = static_data.get("challenges", {}).get("ru", [])
    
    if not challenge_list:
        await safe_send(event.bot, chat_id, "⚠️ Список заданий пока пуст.")
        return

    # 2. Случайный индекс
    random_index = random.randrange(len(challenge_list))
    challenge_raw = challenge_list[random_index]
    
    # 3. Достаем текст
    if isinstance(challenge_raw, dict):
        text_content = challenge_raw.get("text") or challenge_raw.get("content") or str(challenge_raw)
    else:
        text_content = str(challenge_raw)

    # 4. Форматируем имя
    try:
        text_content = text_content.format(name=user_data.get("name", "друг"))
    except: pass

    # 5. Кнопки (с индексом!)
    kb = InlineKeyboardBuilder()
    kb.button(text=t('btn_challenge_accept', lang), callback_data=f"accept_challenge_idx:{random_index}")
    kb.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
    
    msg_text = t('challenge_new_day', lang, challenge_text=text_content)
    
    # 6. Отправляем или редактируем
    if is_edit and isinstance(event, CallbackQuery):
        await event.message.edit_text(msg_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await event.answer(msg_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        
    # Записываем, что челлендж выдан (чтобы не спамить)
    # Но не блокируем кнопку "Новый", просто обновляем дату
    user_tz = get_user_tz(user_data)
    today_iso = datetime.now(user_tz).date().isoformat()
    if user_data.get("last_challenge_date") != today_iso:
        await db.update_user(chat_id, last_challenge_date=today_iso, challenge_accepted=False)
        user_data["last_challenge_date"] = today_iso
        user_data["challenge_accepted"] = False

async def accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    """Принятие челленджа по кнопке."""
    chat_id = query.from_user.id
    try:
        # Парсим индекс из "accept_challenge_idx:5"
        idx = int(query.data.split(":")[-1])
        
        # Снова достаем текст из базы (stateless)
        challenge_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
        if not challenge_list or idx >= len(challenge_list):
            await query.answer("⚠️ Ошибка: задание устарело. Нажми 'Новый'.", show_alert=True)
            return
            
        challenge_raw = challenge_list[idx]
        
        # 🔥 ФИКС ОШИБКИ: Получаем чистый текст
        if isinstance(challenge_raw, dict):
            text_content = challenge_raw.get("text") or str(challenge_raw)
        else:
            text_content = str(challenge_raw)
            
        try: text_content = text_content.format(name=user_data.get("name", "друг"))
        except: pass

        # Сохраняем в историю
        history = user_data.get("challenges", [])
        # 🔥 ФИКС ОШИБКИ: Десериализуем, если это строка (для совместимости с БД)
        if isinstance(history, str):
            try: history = json.loads(history)
            except: history = []
        
        new_entry = {
            "text": text_content,
            "accepted": datetime.now(ZoneInfo("UTC")).isoformat(),
            "completed": None
        }
        history.append(new_entry)
        
        # Сохраняем в БД
        json_history = json.dumps(history, ensure_ascii=False)
        await db.update_user(chat_id, challenges=json_history, challenge_accepted=True)
        user_data["challenges"] = history
        user_data["challenge_accepted"] = True
        
        # Меняем кнопку на "Выполнено"
        kb = InlineKeyboardBuilder()
        # Индекс в истории - это последний элемент (len - 1)
        hist_idx = len(history) - 1
        kb.button(text=t('btn_challenge_complete', lang), callback_data=f"complete_challenge:{hist_idx}")
        
        # ⚠️ ИСПРАВЛЕНА ОШИБКА 1: challenge_accepted_msg требует challenge_text
        await query.message.edit_text(
            t('challenge_accepted_msg', lang, challenge_text=text_content),
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await query.answer(t('challenge_accepted_msg', lang, challenge_text=""))
        
    except Exception as e:
        logger.error(f"Accept error: {e}")
        await query.answer("Error", show_alert=True)

async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    """Завершение челленджа."""
    chat_id = query.from_user.id
    try:
        hist_idx = int(query.data.split(":")[-1])
        
        history = user_data.get("challenges", [])
        # 🔥 ФИКС ОШИБКИ 2: Десериализуем, если это строка
        if isinstance(history, str):
            try: history = json.loads(history)
            except: history = []
        
        if hist_idx < len(history):
            # 🔥 ФИКС ОШИБКИ: Проверка, что элемент истории - словарь
            if isinstance(history[hist_idx], dict) and not history[hist_idx].get("completed"):
                history[hist_idx]["completed"] = datetime.now(ZoneInfo("UTC")).isoformat()
                streak = user_data.get("challenge_streak", 0) + 1
                
                await db.update_user(chat_id, challenges=json.dumps(history, ensure_ascii=False), challenge_streak=streak, challenge_accepted=False)
                user_data["challenges"] = history
                user_data["challenge_streak"] = streak
                user_data["challenge_accepted"] = False 
                
                orig_text = query.message.text
                final_text = f"{orig_text}\n\n✅ <b>{t('challenge_completed_msg', lang)}</b>"
                await query.message.edit_text(final_text, reply_markup=None, parse_mode=ParseMode.HTML)
                
                if streak % 3 == 0:
                     await safe_send(query.bot, chat_id, t('challenge_streak_3_level_1', lang, name=user_data.get("name")))
            else:
                await query.answer("Уже выполнено!")
        else:
            await query.answer("Ошибка индекса")
            
    except Exception as e:
        logger.error(f"Complete error: {e}")
        await query.answer("Error")