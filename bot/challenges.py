# 09 - bot/challenges.py
# bot/challenges.py — УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс лимитов и синхронизация БД

# 09 - bot/challenges.py
# bot/challenges.py — УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс лимитов и синхронизация БД
# ✅ СВЕРЕНО ПОСТРОЧНО: Сохранена вся логика Олега
# ✅ ДОБАВЛЕНО (Этап 2): Сброс стрика при пропуске дня (Duolingo Style)

import random
import json
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send, get_user_tz
from bot.keyboards import get_challenge_complete_button

def _ensure_list(data: any) -> list:
    if isinstance(data, list): return data
    if isinstance(data, str):
        try: return json.loads(data)
        except: return []
    return []

async def send_new_challenge_message(event: Message | CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext, is_edit: bool = False):
    chat_id = event.from_user.id
    
    # --- Idempotency Guard ---
    if not is_edit and getattr(event, "_challenge_handled", False):
        return
    setattr(event, "_challenge_handled", True)
    
    # СТРОГО: Получаем свежие данные напрямую из БД
    fresh_user = await db.get_user(chat_id)
    if not fresh_user:
        return

    # 1. ОПРЕДЕЛЯЕМ ДАТУ (по поясу юзера)
    user_tz = get_user_tz(fresh_user)
    now_local = datetime.now(user_tz)
    today_str = now_local.date().isoformat()
    last_challenge_date = str(fresh_user.get("last_challenge_date") or "")

    # 2. СБРОС ПРИ СМЕНЕ ДНЯ + ЛОГИКА СТРИКА (Duolingo Style)
    if last_challenge_date != today_str:
        upd_params = {
            "last_challenge_date": today_str,
            "challenges_today": 0,
            "challenge_accepted": 0
        }
        
        # Проверка на пропуск дня для сброса стрика
        if last_challenge_date:
            try:
                last_date = date.fromisoformat(last_challenge_date)
                today_date = now_local.date()
                if (today_date - last_date).days > 1:
                    logger.info(f"Streak: User {chat_id} missed a day. Streak reset.")
                    upd_params["challenge_streak"] = 0
            except: pass
            
        await db.update_user(chat_id, **upd_params)
        fresh_user = await db.get_user(chat_id) 

    # 3. ПРОВЕРКА: ЧЕЛЛЕНДЖ УЖЕ ПРИНЯТ?
    if fresh_user.get("challenge_accepted"):
        hist = _ensure_list(fresh_user.get("challenges", []))
        if hist:
            active_text = hist[-1].get("text", "Challenge")
            idx = len(hist) - 1
            text_msg = f"{t('challenge_already_issued', lang)}\n\n💪 <b>Текущий:</b>\n<i>{active_text}</i>"
            kb = get_challenge_complete_button(lang, idx)
            
            if isinstance(event, CallbackQuery):
                try: await event.message.edit_text(text_msg, reply_markup=kb, parse_mode=ParseMode.HTML)
                except: await safe_send(event.bot, chat_id, text_msg, reply_markup=kb)
            else:
                await safe_send(event.bot, chat_id, text_msg, reply_markup=kb)
            return

    # 4. ПРОВЕРКА ЛИМИТА (1 в день, кроме реролла)
    if not is_edit:
        attempts = int(fresh_user.get("challenges_today", 0))
        if attempts >= 1:
            msg = t('challenge_already_issued', lang)
            if isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)
            else:
                await safe_send(event.bot, chat_id, msg)
            return

    # 5. ГЕНЕРАЦИЯ
    challenges_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    if not challenges_list:
        return await safe_send(event.bot, chat_id, "⚠️ Challenges list is empty.")

    idx = random.randrange(len(challenges_list))
    item = challenges_list[idx]
    text_raw = str(item.get("text") if isinstance(item, dict) else item)
    
    name = fresh_user.get("name") or event.from_user.first_name or "Пользователь"
    try: final_text = text_raw.format(name=name)
    except: final_text = text_raw

    # 6. КЛАВИАТУРА
    builder = InlineKeyboardBuilder()
    builder.button(text=t('btn_challenge_accept', lang), callback_data=f"accept_challenge_idx:{idx}")
    builder.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")
    builder.adjust(1)
    
    msg_content = t('challenge_new_day', lang, challenge_text=final_text)

    # 7. ЗАПИСЬ В БАЗУ И ОТПРАВКА
    if is_edit and isinstance(event, CallbackQuery):
        await event.message.edit_text(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    else:
        new_attempts = int(fresh_user.get("challenges_today", 0)) + 1
        await db.update_user(chat_id, last_challenge_date=today_str, challenges_today=new_attempts)
        user_data.update({"last_challenge_date": today_str, "challenges_today": new_attempts})
        
        if isinstance(event, Message):
            await event.answer(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        else:
            await event.message.answer(msg_content, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

async def accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    try: idx = int(query.data.split(":")[-1])
    except: idx = 0
        
    fresh_user = await db.get_user(query.from_user.id)
    challenges_list = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    item = challenges_list[idx] if idx < len(challenges_list) else {"text": "Challenge"}
    text_raw = str(item.get("text") if isinstance(item, dict) else item)
    
    name = fresh_user.get("name") or query.from_user.first_name or "Пользователь"
    try: final_text = text_raw.format(name=name)
    except: final_text = text_raw

    hist = _ensure_list(fresh_user.get("challenges") or [])
    hist.append({
        "text": final_text, 
        "accepted": datetime.now(timezone.utc).isoformat(), 
        "completed": None
    })
    
    await db.update_user(query.from_user.id, challenges=hist, challenge_accepted=1)
    user_data.update({"challenges": hist, "challenge_accepted": 1})

    await query.message.edit_text(
        t('challenge_accepted_msg', lang, challenge_text=final_text),
        reply_markup=get_challenge_complete_button(lang, len(hist)-1),
        parse_mode=ParseMode.HTML
    )

async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    try: idx = int(query.data.split(":")[-1])
    except: return

    fresh_user = await db.get_user(query.from_user.id)
    hist = _ensure_list(fresh_user.get("challenges"))
    if hist and idx < len(hist) and not hist[idx].get("completed"):
        hist[idx]["completed"] = datetime.now(timezone.utc).isoformat()
        new_streak = int(fresh_user.get("challenge_streak", 0)) + 1
        
        await db.update_user(query.from_user.id, challenges=hist, challenge_streak=new_streak, challenge_accepted=0)
        user_data.update({"challenges": hist, "challenge_streak": new_streak, "challenge_accepted": 0})
        
        await query.message.edit_text(
            f"✅ {t('challenge_completed_msg', lang)}\n\n<i>{hist[idx]['text']}</i>",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )
    else:
        await query.answer(t('reaction_already_accepted', lang))