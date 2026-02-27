# 10 - bot/callbacks.py
# ✅ Обработка Inline-кнопок (выбор языка, реакции, челленджи)
# ✅ Защита от несанкционированного доступа
# ✅ Логика первого запуска (выбор языка с полным приветствием)
# ✅ Обработка реакций (лайки/дизлайки) с защитой от дублей
# ✅ Кнопки челленджей (принять, новый, выполнить)

# 10 - bot/callbacks.py - ФИНАЛЬНАЯ ВЕРСИЯ (23.02.2026)
# Обработчики Inline-кнопок
# ✅ ПРОВЕРЕНО: Защита от дублей, логика 3+1+3, реакции

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db 
from bot.utils import get_demo_config
from bot.challenges import accept_challenge, send_new_challenge_message, complete_challenge
from bot.keyboards import get_reply_keyboard_for_user
from bot.commands import stats_command

router = Router()

# --- 🌍 ВЫБОР ЯЗЫКА (ИСПРАВЛЕННАЯ ВЕРСИЯ) ---

@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_select(query: CallbackQuery, bot: Bot, static_data: dict, user_data: dict, **kwargs):
    """Первичный выбор языка с полным приветствием для новых пользователей."""
    if not query.message: return
        
    lang_code = query.data.split("_")[-1]
    if lang_code not in ("ru", "ua", "en"): return
    
    lang: Lang = lang_code
    chat_id = query.from_user.id
    
    # Имя пользователя с fallback
    name = query.from_user.first_name or user_data.get("name") or "друг"
    
    # Определяем, новый ли это пользователь
    is_new_user = not user_data.get("language")
    
    logger.info(f"User {chat_id} selected language {lang} (new: {is_new_user})")
    
    # Обновляем язык в БД
    await db.update_user(chat_id, language=lang, name=name)
    
    # Получаем свежие данные
    fresh_data = await db.get_user(chat_id)
    if fresh_data:
        user_data.update(fresh_data)
        if "users_db" in kwargs:
            kwargs["users_db"][str(chat_id)] = fresh_data
    
    # 1. Убираем inline-кнопки выбора языка
    try:
        await query.message.edit_text(t('lang_chosen', lang), reply_markup=None)
    except TelegramBadRequest:
        pass
    
    # 2. Готовим клавиатуру
    markup = get_reply_keyboard_for_user(chat_id, lang, user_data)
    
    # 3. ДЛЯ НОВОГО ПОЛЬЗОВАТЕЛЯ - ПОЛНОЕ ПРИВЕТСТВИЕ
    if is_new_user:
        # Получаем настройки демо для этого пользователя
        config = get_demo_config(chat_id)
        demo_days = config["demo"]
        
        # Отправляем приветствие
        welcome_text = t('welcome', lang, name=name, demo_days=demo_days)
        await bot.send_message(
            chat_id,
            welcome_text,
            reply_markup=markup,
            parse_mode="HTML"
        )
        
        # Добавляем заметку о часовом поясе
        tz_note = t('welcome_timezone_note', lang, default_tz=settings.DEFAULT_TZ_KEY)
        await bot.send_message(chat_id, tz_note, parse_mode="HTML")
    
    # 4. ДЛЯ ВЕРНУВШЕГОСЯ - КОРОТКОЕ СООБЩЕНИЕ
    else:
        await bot.send_message(
            chat_id,
            f"{t('lang_chosen', lang)}\n\n{t('msg_welcome_back', lang)}",
            reply_markup=markup
        )
    
    # 5. Убираем "часики" с кнопки
    await query.answer()

# --- 👍 РЕАКЦИИ (Лайки / Дизлайки) ---

@router.callback_query(F.data.startswith("reaction:"))
async def handle_reaction(query: CallbackQuery, user_data: dict, lang: Lang):
    """Обработка оценки контента с проверкой на дубли и Cooldown."""
    
    # 🛡️ ПРОВЕРКА COOLDOWN (3+1+3)
    if user_data.get("status") == "cooldown":
        from datetime import datetime, timezone, timedelta
        exp_str = user_data.get("demo_expiration")
        try:
            exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
            cooldown_end = exp_dt + timedelta(days=1)
            rem = cooldown_end - datetime.now(timezone.utc)
            h, m = int(rem.total_seconds() // 3600), int((rem.total_seconds() % 3600) // 60)
            return await query.answer(t('btn_quiet_day_lock', lang, hours=h, minutes=m), show_alert=True)
        except:
            return await query.answer(t('btn_quiet_day_lock', lang, hours=0, minutes=0), show_alert=True)

    parts = query.data.split(":")
    action = parts[1]  # "like" или "dislike"

    # ✅ ЗАЩИТА ОТ ДУБЛЕЙ
    if len(parts) > 2 and parts[2] == "done":
        return await query.answer(t('reaction_already_accepted', lang, name=user_data.get("name", "")), show_alert=True)

    # Обновляем статистику в БД
    new_likes = user_data.get("stats_likes", 0) + (1 if action == "like" else 0)
    new_dislikes = user_data.get("stats_dislikes", 0) + (1 if action == "dislike" else 0)
    
    await db.update_user(query.from_user.id, stats_likes=new_likes, stats_dislikes=new_dislikes)
    user_data.update({"stats_likes": new_likes, "stats_dislikes": new_dislikes})

    await query.answer(t('reaction_received', lang, name=user_data.get("name", "")))
    
    # Обновляем кнопки в сообщении (ставим галочку)
    share_url = None
    if query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.url: share_url = btn.url

    kb = InlineKeyboardBuilder()
    kb.button(text="👍 ✅" if action == "like" else "👍", callback_data="reaction:like:done")
    kb.button(text="👎 ✅" if action == "dislike" else "👎", callback_data="reaction:dislike:done")
    if share_url:
        kb.row(InlineKeyboardButton(text=t('btn_share', lang), url=share_url))
    
    try:
        await query.message.edit_reply_markup(reply_markup=kb.as_markup())
    except TelegramBadRequest:
        pass

# --- ⚔️ ЧЕЛЛЕНДЖИ ---

@router.callback_query(F.data.startswith("accept_challenge"))
async def handle_accept_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    if user_data.get("status") == "cooldown":
        return await query.answer(t('btn_quiet_day_lock', lang), show_alert=True)
    await accept_challenge(query, static_data, user_data, lang, state)

@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge(query: CallbackQuery, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    if user_data.get("status") == "cooldown":
        return await query.answer(t('btn_quiet_day_lock', lang), show_alert=True)
    await send_new_challenge_message(query, static_data, user_data, lang, state, is_edit=True)

@router.callback_query(F.data.startswith("complete_challenge:"))
async def handle_complete_challenge(query: CallbackQuery, user_data: dict, lang: Lang, state: FSMContext):
    await complete_challenge(query, user_data, lang, state)

# --- 📊 АДМИН ПАНЕЛЬ (Inline) ---

@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats_callback(query: CallbackQuery, is_admin: bool, lang: Lang):
    if not is_admin:
        return await query.answer("Access Denied", show_alert=True)
    await query.answer()
    await stats_command(query.message, is_admin=True)