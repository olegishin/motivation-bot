import random
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import logger
from bot.localization import t, Lang
from bot.database import db
from bot.utils import safe_send
from bot.keyboards import get_challenge_complete_button

async def send_new_challenge_message(event: Message | CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext, is_edit: bool = False):
    chat_id = event.from_user.id
    today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    
    # Блокировка повторных запросов из МЕНЮ
    if not is_edit:
        if user_data.get("last_challenge_date") == today:
            if user_data.get("challenge_accepted"):
                return await safe_send(event.bot, chat_id, t('challenge_already_issued', lang, name=user_data.get("name", "Олег")))
            else:
                return await safe_send(event.bot, chat_id, t('challenge_pending_acceptance', lang, name=user_data.get("name", "Олег")))

    challenges = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    if not challenges: return await safe_send(event.bot, chat_id, "List empty")

    idx = random.randrange(len(challenges))
    item = challenges[idx]
    text_raw = str(item.get("text") if isinstance(item, dict) else item)
    
    # Имя
    name = user_data.get("name")
    if not name or name.lower() == "друг": name = event.from_user.first_name or "Олег"
    
    try: text = text_raw.format(name=name)
    except: text = text_raw

    kb = InlineKeyboardBuilder()
    kb.button(text=t('btn_challenge_accept', lang), callback_data=f"accept_challenge_idx:{idx}")
    kb.button(text=t('btn_challenge_new', lang), callback_data="new_challenge")

    msg_text = t('challenge_new_day', lang, challenge_text=text)

    if is_edit and isinstance(event, CallbackQuery):
        await event.message.edit_text(msg_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await db.update_user(chat_id, last_challenge_date=today)
        user_data["last_challenge_date"] = today
        await event.answer(msg_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)

async def accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    idx = int(query.data.split(":")[-1])
    challenges = static_data.get("challenges", {}).get(lang, []) or static_data.get("challenges", {}).get("ru", [])
    item = challenges[idx]
    text_raw = str(item.get("text") if isinstance(item, dict) else item)
    
    name = user_data.get("name")
    if not name or name.lower() == "друг": name = query.from_user.first_name or "Олег"
    text = text_raw.format(name=name)

    hist = user_data.get("challenges") or []
    hist.append({"text": text, "accepted": datetime.now(ZoneInfo("UTC")).isoformat(), "completed": None})
    
    await db.update_user(query.from_user.id, challenges=hist, challenge_accepted=1)
    user_data.update({"challenges": hist, "challenge_accepted": 1})

    # ШАГ 2: Меняем текст и ставим кнопку "Выполнено"
    await query.message.edit_text(
        t('challenge_accepted_msg', lang, challenge_text=text), 
        reply_markup=get_challenge_complete_button(lang, len(hist)-1), 
        parse_mode=ParseMode.HTML
    )

async def complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    idx = int(query.data.split(":")[-1])
    hist = user_data.get("challenges")
    if hist and idx < len(hist) and not hist[idx].get("completed"):
        hist[idx]["completed"] = datetime.now(ZoneInfo("UTC")).isoformat()
        streak = user_data.get("challenge_streak", 0) + 1
        
        await db.update_user(query.from_user.id, challenges=hist, challenge_streak=streak, challenge_accepted=0)
        user_data.update({"challenges": hist, "challenge_streak": streak, "challenge_accepted": 0})
        
        # ШАГ 3: Финальный текст без кнопок
        await query.message.edit_text(
            f"✅ {t('challenge_completed_msg', lang)}\n\n<i>{hist[idx]['text']}</i>", 
            reply_markup=None, 
            parse_mode=ParseMode.HTML
        )
    else:
        await query.answer("Уже выполнено")