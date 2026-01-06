# 10 - bot/callbacks.py
# Полная версия: Исправлено создание пользователя при выборе языка

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db 
from bot.content_handlers import handle_start_command 
from bot.challenges import accept_challenge, send_new_challenge_message, complete_challenge
from bot.keyboards import get_reply_keyboard_for_user
from bot.commands import send_stats_report 

router = Router()

# --- 🌍 ВЫБОР ЯЗЫКА ---
@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_select(
    query: CallbackQuery, 
    bot: Bot, 
    static_data: dict, 
    user_data: dict, 
    is_new_user: bool, 
    **kwargs 
):
    if not query.message: 
        await query.answer("Ошибка: сообщение не найдено.")
        return
        
    parts = query.data.split("_")
    lang_code = parts[-1] 
    
    if lang_code not in ("ru", "ua", "en"): 
        return
    
    lang: Lang = lang_code # type: ignore
    chat_id = query.from_user.id
    
    if is_new_user:
        await db.add_user(
            user_id=chat_id,
            username=query.from_user.username,
            full_name=query.from_user.first_name,
            language=lang
        )
        # Получаем полные данные из БД сразу
        new_data = await db.get_user(chat_id)
        user_data.update(new_data)
    else:
        await db.update_user(chat_id, language=lang)
        user_data["language"] = lang 
    
    await query.answer(t('lang_chosen', lang))
    
    try: 
        await query.message.edit_text(t('lang_chosen', lang), reply_markup=None) 
    except TelegramBadRequest: 
        pass 
    
    if is_new_user: 
        await handle_start_command(message=query.message, static_data=static_data, user_data=user_data, lang=lang, is_new_user=True)
    else: 
        markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
        await bot.send_message(chat_id, t('lang_chosen', lang), reply_markup=markup)


# --- 👍 РЕАКЦИИ (Лайки) ---
@router.callback_query(F.data.startswith("reaction:"))
async def handle_reaction(query: CallbackQuery, user_data: dict, lang: Lang, **kwargs):
    user_name = user_data.get("name") or query.from_user.first_name or "друг"
    parts = query.data.split(":")
    action = parts[1] 
    
    share_url = None
    share_text = t('btn_share', lang) 
    
    if query.message.reply_markup and query.message.reply_markup.inline_keyboard:
        for row in query.message.reply_markup.inline_keyboard:
            for button in row:
                if button.url and button.text == share_text: 
                    share_url = button.url
                    break
            if share_url: break

    if len(parts) > 2 and parts[2] == "done":
        await query.message.reply(t('reaction_already_accepted', lang, name=user_name))
        await query.answer() 
        return

    new_likes = user_data.get("stats_likes", 0)
    new_dislikes = user_data.get("stats_dislikes", 0)
    
    if action == "like": 
        new_likes += 1
    elif action == "dislike": 
        new_dislikes += 1
        
    await db.update_user(query.from_user.id, stats_likes=new_likes, stats_dislikes=new_dislikes)
    user_data["stats_likes"] = new_likes
    user_data["stats_dislikes"] = new_dislikes
    
    await query.message.reply(t('reaction_received', lang, name=user_name))
    await query.answer() 

    try:
        kb = InlineKeyboardBuilder()
        l_text = "👍 ✅" if action == "like" else "👍"
        d_text = "👎 ✅" if action == "dislike" else "👎"
        kb.button(text=l_text, callback_data="reaction:like:done")
        kb.button(text=d_text, callback_data="reaction:dislike:done")
        kb.adjust(2) 
        if share_url:
            kb.row(InlineKeyboardButton(text=share_text, url=share_url))
        await query.message.edit_reply_markup(reply_markup=kb.as_markup())
    except TelegramBadRequest: pass 
    except Exception as e: logger.error(f"Error locking reaction: {e}")

# --- ⚔️ ЧЕЛЛЕНДЖИ ---
@router.callback_query(F.data.startswith("accept_challenge_idx:"))
async def handle_accept_challenge_idx(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext, **kwargs):
    await accept_challenge(query, static_data, user_data, lang, state) 

@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext, **kwargs):
    await send_new_challenge_message(query, static_data, user_data, lang, state, is_edit=True) 

@router.callback_query(F.data.startswith("complete_challenge:"))
async def handle_complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext, **kwargs):
    await complete_challenge(query, user_data, lang, state)

# --- 🛠 АДМИН ---
@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats_callback(query: CallbackQuery, users_db: dict, is_admin: bool, lang: Lang, **kwargs):
    await query.answer()
    if not is_admin or not query.message: return
    await send_stats_report(query.message, users_db, lang)