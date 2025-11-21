# 11 - bot/callbacks.py

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

from config import logger, settings, SPECIAL_USER_IDS
from localization import t, Lang
from database import db 
from content_handlers import handle_start_command
from challenges import accept_challenge, send_new_challenge_message, complete_challenge
from keyboards import get_main_keyboard, get_reply_keyboard_for_user
from utils import get_user_lang, is_demo_expired
from commands import send_stats_report

router = Router()

@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_select(
    query: CallbackQuery, 
    bot: Bot, 
    static_data: dict, 
    user_data: dict, 
    is_new_user: bool,
    data: dict 
):
    if not query.message:
        await query.answer("Ошибка: не могу найти сообщение.", show_alert=True)
        return

    lang_code = query.data.split("_")[2]
    if lang_code not in ("ru", "ua", "en"): return
        
    lang: Lang = lang_code # type: ignore
    chat_id = query.from_user.id
    
    await query.answer(t('lang_chosen', lang))
    try:
        await query.message.edit_text(t('lang_chosen', lang), reply_markup=None)
    except TelegramBadRequest: pass 
    
    if is_new_user:
        await handle_start_command(message=query.message, static_data=static_data, user_data=user_data, lang=lang, is_new_user=True)
    else:
        await db.update_user(chat_id, language=lang)
        user_data["language"] = lang
        markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
        await bot.send_message(chat_id, t('lang_chosen', lang), reply_markup=markup)


@router.callback_query(F.data.startswith("reaction:"))
async def handle_reaction(query: CallbackQuery, user_data: dict, lang: Lang):
    # Сразу отвечаем телеграму, чтобы кнопка перестала крутиться
    await query.answer() 
    
    # 1. Получаем ID сообщения и Имя
    msg_id = query.message.message_id
    name = user_data.get("name", "друг") # Дефолтное обращение, если имя не указано

    # 2. Проверяем список сообщений, где уже голосовали
    # Получаем список из базы (или создаем новый, если его нет)
    reacted_list = user_data.get("reacted_messages", [])
    if not isinstance(reacted_list, list): # Защита от старых данных
        reacted_list = []
    
    if msg_id in reacted_list:
        # --- ЛОГИКА 2: Если уже нажимал ---
        if lang == 'ru':
            text = f"{name}, твоя оценка уже принята" # <--- ИЗМЕНЕНО
        elif lang == 'ua':
            text = f"{name}, ти вже зробив вибір, твою оцінку прийнято"
        else:
            text = f"{name}, you have already made a choice, your rating is accepted"
            
        # Отправляем как Reply (ответ на сообщение)
        await query.message.reply(text)
        return

    # 3. Если это первый раз — считаем голос
    reaction = query.data.split(":")[-1]
    logger.info(f"Reaction received from {query.from_user.id}: {reaction}")
    
    new_likes = user_data.get("stats_likes", 0)
    new_dislikes = user_data.get("stats_dislikes", 0)
    
    if reaction == "like": new_likes += 1
    elif reaction == "dislike": new_dislikes += 1
    
    # 4. Обновляем данные (добавляем ID сообщения в список "проголосованных")
    reacted_list.append(msg_id)
    
    # Ограничиваем историю (храним последние 50 голосов, чтобы база не раздувалась)
    if len(reacted_list) > 50:
        reacted_list.pop(0) # Удаляем самый старый

    await db.update_user(
        query.from_user.id, 
        stats_likes=new_likes, 
        stats_dislikes=new_dislikes,
        reacted_messages=reacted_list # Сохраняем обновленный список
    )
    
    # Обновляем кэш в памяти
    user_data["stats_likes"] = new_likes 
    user_data["stats_dislikes"] = new_dislikes
    user_data["reacted_messages"] = reacted_list

    # --- ЛОГИКА 1: Благодарность (Сообщением в чат) ---
    if lang == 'ru':
        thanks_text = "Благодарим за оценку"
    elif lang == 'ua':
        thanks_text = "Дякуємо за оцінку"
    else:
        thanks_text = "Thanks for your rating"

    # Отправляем как Reply (ответ на сообщение)
    await query.message.reply(thanks_text)


# --- 3. Хендлеры кнопок челленджа ---

@router.callback_query(F.data == "accept_current_challenge")
async def handle_accept_challenge(
    query: CallbackQuery, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext
):
    await query.answer()
    await accept_challenge(query, user_data, lang, state) 


@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge(
    query: CallbackQuery, 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext
):
    await query.answer()
    await send_new_challenge_message(query, static_data, user_data, lang, state, is_edit=True) 


@router.callback_query(F.data.startswith("complete_challenge:"))
async def handle_complete_challenge(
    query: CallbackQuery, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext
):
    await query.answer()
    await complete_challenge(query, user_data, lang, state)

# --- 4. Хендлеры кнопок Админа (статистика) ---
@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats_callback(query: CallbackQuery, users_db: dict, is_admin: bool, lang: Lang):
    await query.answer()
    if not is_admin or not query.message: return
    await send_stats_report(query.message, users_db, lang)