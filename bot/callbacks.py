# 12 - bot/callbacks.py
# Обработчики Inline-кнопок Aiogram.

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

# ✅ ИСПРАВЛЕНО: Импорты с префиксом bot.
from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db 
from bot.content_handlers import handle_start_command
from bot.challenges import accept_challenge, send_new_challenge_message, complete_challenge
from bot.keyboards import get_reply_keyboard_for_user
from bot.utils import get_user_lang
from bot.commands import send_stats_report 

router = Router()

@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_select(query: CallbackQuery, bot: Bot, static_data: dict, user_data: dict, is_new_user: bool, data: dict):
    if not query.message: 
        await query.answer("Ошибка: не могу найти сообщение.", show_alert=True)
        return
        
    lang_code = query.data.split("_")[2]
    if lang_code not in ("ru", "ua", "en"): return
    
    lang: Lang = lang_code # type: ignore
    chat_id = query.from_user.id
    
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


@router.callback_query(F.data.startswith("reaction:"))
async def handle_reaction(query: CallbackQuery, user_data: dict, lang: Lang):
    """
    Обработка лайков/дизлайков.
    Логика:
    1. Если кнопки уже нет или это повтор -> "Уже принята".
    2. Если ок -> Записываем в БД -> Пишем "Благодарю" -> Удаляем кнопки.
    """
    user_name = user_data.get("name", "друг")
    
    # 1. Защита от повторного нажатия (если клавиатура уже удалена или изменена)
    # Если сообщение не имеет reply_markup, значит реакция уже была обработана
    if not query.message.reply_markup:
        await query.answer(t('reaction_already_accepted', lang, name=user_name), show_alert=True)
        return

    reaction = query.data.split(":")[-1]
    
    # 2. Обновляем статистику
    new_likes = user_data.get("stats_likes", 0)
    new_dislikes = user_data.get("stats_dislikes", 0)
    
    if reaction == "like": 
        new_likes += 1
    elif reaction == "dislike": 
        new_dislikes += 1
        
    await db.update_user(query.from_user.id, stats_likes=new_likes, stats_dislikes=new_dislikes)
    user_data["stats_likes"] = new_likes
    user_data["stats_dislikes"] = new_dislikes
    
    # 3. Отвечаем всплывающим уведомлением
    await query.answer(t('reaction_received', lang, name=user_name))
    
    # 4. (Опционально) Пишем сообщение в чат, если нужно подтверждение текстом
    # Но обычно достаточно query.answer. Если нужно сообщение как раньше:
    # await query.message.answer(t('reaction_received', lang, name=user_name)) 

    # 5. Удаляем клавиатуру, чтобы нельзя было нажать второй раз
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        # Если кнопки уже удалены (гонка запросов), пишем "Уже принято"
        await query.answer(t('reaction_already_accepted', lang, name=user_name), show_alert=True)
    except Exception as e:
        logger.error(f"Error removing reaction keyboard: {e}")


@router.callback_query(F.data == "accept_current_challenge")
async def handle_accept_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    await query.answer()
    await accept_challenge(query, user_data, lang, state) 

@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    await query.answer()
    await send_new_challenge_message(query, static_data, user_data, lang, state, is_edit=True) 

@router.callback_query(F.data.startswith("complete_challenge:"))
async def handle_complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    await query.answer()
    await complete_challenge(query, user_data, lang, state)

@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats_callback(query: CallbackQuery, users_db: dict, is_admin: bool, lang: Lang):
    await query.answer()
    if not is_admin or not query.message: return
    await send_stats_report(query.message, users_db, lang)