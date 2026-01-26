# 10 - bot/callbacks.py
# Полная версия: Исправлено создание пользователя и синхронизация языка/данных
# Обработчики Inline-кнопок Aiogram (Язык, Реакции, Челленджи)
# ✅ ИСПРАВЛЕНО (2026-01-16): 
#    - Убран параметр is_new_user (Ошибка #2)
#    - Исправлен full_name → name (Ошибка #1)
#    - Логирование для отладки
# ✅ ИСПРАВЛЕНО (2026-01-20):
#    - Повторное нажатие на реакцию → ТОЛЬКО всплывающее окно (show_alert=True)
#    - Убрано текстовое сообщение query.message.reply() при повторе
# ✅ ИСПРАВЛЕНО (2026-01-23): 
#    - Кнопки не пропадают после выбора языка
#    - Админские кнопки показываются сразу для админа

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
    **kwargs 
):
    """
    ✅ ИСПРАВЛЕНО (2026-01-16):
    - Убран параметр is_new_user (его нет в middleware)
    - Определяем новый пользователь через user_data.get("language")
    - Исправлен full_name → name (из database.py)
    
    ✅ ИСПРАВЛЕНО (2026-01-23):
    - Кнопки не пропадают после выбора языка
    - Админские кнопки показываются сразу для админа
    """
    
    if not query.message: 
        await query.answer("Ошибка: сообщение не найдено.")
        return
        
    parts = query.data.split("_")
    lang_code = parts[-1] 
    
    if lang_code not in ("ru", "ua", "en"): 
        return
    
    lang: Lang = lang_code  # type: ignore
    chat_id = query.from_user.id
    
    # 🛡️ Определяем новый ли пользователь (нет language → новый)
    # НО: С исправленной commands.py, пользователь УЖЕ должен быть в БД!
    is_new_user = not user_data.get("language")
    
    # 1️⃣ Обновляем язык в базе данных
    if is_new_user:
        # ✅ ИСПРАВЛЕНО: используем name вместо full_name
        # На самом деле, с новой commands.py это НЕ должно вызываться (пользователь уже создан)
        # Но на случай edge case, обновляем вместо создания
        await db.update_user(
            chat_id,
            language=lang,
            name=query.from_user.first_name or "Пользователь"
        )
        logger.info(f"Callbacks: New user {chat_id} set language to {lang}")
    else:
        # Вернувшийся пользователь просто обновляет язык
        await db.update_user(chat_id, language=lang)
        logger.info(f"Callbacks: User {chat_id} switched language to {lang}")
    
    # 2️⃣ КРИТИЧЕСКИ ВАЖНО: Получаем ПОЛНОСТЬЮ обновленные данные из БД
    # Это гарантирует, что лимиты и язык синхронизированы
    fresh_data = await db.get_user(chat_id)
    if fresh_data:
        user_data.update(fresh_data)
        logger.debug(f"Callbacks: Updated user_data for {chat_id}, language={fresh_data.get('language')}")
        
        # Также обновляем в кэше, если он передан через middleware
        if "users_db" in kwargs:
            kwargs["users_db"][str(chat_id)] = fresh_data
            logger.debug(f"Callbacks: Updated users_db cache for {chat_id}")

    await query.answer(t('lang_chosen', lang))
    
    # 3️⃣ 🔥 ИСПРАВЛЕНИЕ №1: НЕ УДАЛЯЕМ СООБЩЕНИЕ, а редактируем его текст
    try: 
        await query.message.edit_text(
            t('lang_chosen', lang),
            reply_markup=None  # Убираем только inline-кнопки выбора языка
        )
    except TelegramBadRequest: 
        # Если редактировать не получилось, продолжаем
        pass 
    
    # 4️⃣ 🔥 ИСПРАВЛЕНИЕ №2: СРАЗУ показываем правильные reply-кнопки
    markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
    
    if is_new_user: 
        logger.info(f"Callbacks: Showing welcome message for new user {chat_id}")
        await handle_start_command(
            message=query.message, 
            static_data=static_data, 
            user_data=user_data, 
            lang=lang, 
            is_new_user=True
        )
    else: 
        logger.info(f"Callbacks: Updating keyboard for user {chat_id}")
        # Отправляем новое сообщение с правильной клавиатурой
        await bot.send_message(
            chat_id, 
            t('lang_chosen', lang), 
            reply_markup=markup
        )


# --- 👍 РЕАКЦИИ (Лайки / Дизлайки) ---
@router.callback_query(F.data.startswith("reaction:"))
async def handle_reaction(query: CallbackQuery, user_data: dict, lang: Lang, **kwargs):
    """
    Обработка нажатия кнопок лайка/дизлайка.
    ✅ ИСПРАВЛЕНО (2026-01-20): Повторное нажатие → ТОЛЬКО всплывающее окно
    """
    
    user_name = user_data.get("name") or query.from_user.first_name or ""
    parts = query.data.split(":")
    action = parts[1]  # "like" или "dislike"
    
    # Пытаемся найти кнопку "Поделиться" в текущем сообщении
    share_url = None
    share_text = t('btn_share', lang) 
    
    if query.message.reply_markup and query.message.reply_markup.inline_keyboard:
        for row in query.message.reply_markup.inline_keyboard:
            for button in row:
                if button.url and button.text == share_text: 
                    share_url = button.url
                    break
            if share_url: 
                break

    # ✅ ИСПРАВЛЕНО: Если уже проголосовано → ТОЛЬКО всплывающее окно
    if len(parts) > 2 and parts[2] == "done":
        logger.debug(f"Callbacks: User {query.from_user.id} tried duplicate reaction")
        await query.answer(
            t('reaction_already_accepted', lang, name=user_name),
            show_alert=True  # ✅ Всплывающее окно на 2 секунды БЕЗ спама в чат
        )
        return  # ✅ Сразу выходим, НЕ отправляя текстовое сообщение

    # Получаем актуальную статистику из user_data
    new_likes = user_data.get("stats_likes", 0)
    new_dislikes = user_data.get("stats_dislikes", 0)
    
    # Увеличиваем счетчик соответствующей реакции
    if action == "like": 
        new_likes += 1
    elif action == "dislike": 
        new_dislikes += 1
    
    # Сохраняем в БД
    await db.update_user(
        query.from_user.id, 
        stats_likes=new_likes, 
        stats_dislikes=new_dislikes
    )
    
    # Обновляем локальные данные
    user_data["stats_likes"] = new_likes
    user_data["stats_dislikes"] = new_dislikes
    
    logger.info(f"Callbacks: User {query.from_user.id} reacted with {action}")
    
    # Отправляем благодарность с цитированием (только при ПЕРВОЙ оценке)
    await query.message.reply(t('reaction_received', lang, name=user_name))
    await query.answer()  # Убираем "часики"

    # Обновляем кнопки (добавляем галочку)
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
    except TelegramBadRequest: 
        pass  # Сообщение может быть удалено
    except Exception as e: 
        logger.error(f"Callbacks: Error updating reaction buttons: {e}")


# --- ⚔️ ЧЕЛЛЕНДЖИ ---
@router.callback_query(F.data.startswith("accept_challenge_idx:"))
async def handle_accept_challenge_idx(
    query: CallbackQuery, 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext, 
    **kwargs
):
    """Обработка нажатия кнопки 'Принять' челлендж."""
    await accept_challenge(query, static_data, user_data, lang, state)


@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge(
    query: CallbackQuery, 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext, 
    **kwargs
):
    """Обработка нажатия кнопки 'Новый' челлендж (переролл)."""
    # При реролле (🎲 Новый) обновляем с is_edit=True
    await send_new_challenge_message(query, static_data, user_data, lang, state, is_edit=True)


@router.callback_query(F.data.startswith("complete_challenge:"))
async def handle_complete_challenge(
    query: CallbackQuery, 
    user_data: dict, 
    lang: Lang, 
    state: FSMContext, 
    **kwargs
):
    """Обработка нажатия кнопки 'Выполнено' челлендж."""
    await complete_challenge(query, user_data, lang, state)


# --- 🛠 АДМИН ---
@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats_callback(
    query: CallbackQuery, 
    users_db: dict, 
    is_admin: bool, 
    lang: Lang, 
    **kwargs
):
    """Обработка запроса статистики от админа."""
    await query.answer()
    
    if not is_admin:
        logger.warning(f"Callbacks: Non-admin user {query.from_user.id} tried to access admin_stats")
        return
    
    if not query.message:
        return
    
    logger.info(f"Callbacks: Admin {query.from_user.id} requested statistics")
    await send_stats_report(query.message, users_db, lang)