# 11 - bot/button_handlers.py
# Обработчики кнопок Aiogram (Исправленная версия: стабильное распознавание языков + force_db)
# Полная эталонная версия: Убит Double Trigger, изолирован Unknown Text, динамический фильтр
# Полная эталонная версия: Убит Double Trigger, изолирован Unknown Text
# Полная эталонная версия: Убит Double Trigger, изолирован Unknown Text, динамический фильтр
# ГРУППА 2: ФИНАЛЬНАЯ ВЕРСИЯ (ULTIMATE 10/10)
# Единообразие переменных, Полное логирование, Force DB для критических кнопок
# Обработчики кнопок Aiogram
# ✅ ИСПРАВЛЕНО (2026-01-16):
#    - force_db=True для критичных кнопок (синхронизация данных)
#    - Логирование для каждого события
#    - Безопасное получение user_data
# Обработчики кнопок Aiogram
# ✅ ИСПРАВЛЕНО (2026-01-18): Возвращены всплывающие уведомления (answerCallbackQuery)
# Построчная сверка: сохранена логика force_db, удален лишний функционал оплат.
# bot/button_handlers.py
# ГРУППА 2: ФИНАЛЬНАЯ ВЕРСИЯ (ULTIMATE 10/10)
# ✅ ИСПРАВЛЕНО (2026-01-18):
#    - Исправлено отображение АДМИН-КНОПОК (проверка is_admin)
#    - Возвращены всплывающие уведомления (answerCallbackQuery)
#    - Убраны лишние текстовые ответы на лайки
# ✅ ИСПРАВЛЕНО (2026-01-18): Добавлен callback.answer() для всплывающего окна реакций
# 11 - bot/button_handlers.py
# ГРУППА 2: ФИНАЛЬНАЯ ВЕРСИЯ (ULTIMATE 10/10)
# ✅ ИСПРАВЛЕНО (2026-01-18): 
#    - Унифицирован вызов реакций (все управление в content_handlers)
#    - Сохранен force_db и динамические фильтры
#    - Исправлен вызов клавиатур для админа (ID casting)

import json
from datetime import datetime, date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.config import logger, settings
from bot.localization import t, Lang
from bot.database import db
from bot.keyboards import get_settings_keyboard, get_reply_keyboard_for_user
from bot.content_handlers import (
    send_from_list, send_rules, send_profile,
    send_payment_instructions, activate_new_demo,
    handle_like, handle_dislike, _handle_reaction
)

# Импорт логики челленджей
from bot.challenges import send_new_challenge_message, accept_challenge, complete_challenge

from bot.utils import get_user_tz
from bot.commands import send_stats_report, show_users_command, broadcast_test_command
from bot.scheduler import setup_jobs_and_cache
from bot.user_loader import load_static_data

router = Router()
# Отдельный роутер для фолбека, чтобы он шел в самом конце pipeline
router_unknown = Router()

# ✅ Динамический фильтр по всем языкам
def btn_filter(key: str):
    """Создает фильтр для кнопки на всех языках (RU/UA/EN)."""
    return F.text.in_([t(key, lang) for lang in ['ru', 'ua', 'en']])

# --- 🛡️ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---

async def _get_user_data(user_id: int, kwargs: dict, force_db: bool = False) -> dict:
    """
    Получение данных пользователя с опцией синхронизации.
    """
    try:
        if force_db:
            u = await db.get_user(user_id)
            if u and "users_db" in kwargs:
                kwargs["users_db"][str(user_id)] = u
            logger.debug(f"Handlers: force_db=True for user {user_id}, got fresh data")
            return u or {}

        ud = kwargs.get("user_data")
        if ud and isinstance(ud, dict) and ud.get("user_id") == user_id:
            return ud
        
        users_db = kwargs.get("users_db")
        if users_db and isinstance(users_db, dict):
            cached = users_db.get(str(user_id)) or users_db.get(user_id)
            if cached:
                logger.debug(f"Handlers: Using cached user_data for {user_id}")
                return cached

        u = await db.get_user(user_id)
        return u or {}
        
    except Exception as e:
        logger.error(f"Handlers: Error getting user data for {user_id}: {e}")
        return {}

# --- 🖱️ ОБРАБОТКА CALLBACK (Inline кнопки) ---

@router.callback_query(F.data.startswith("set_lang_"))
async def handle_lang_callback(callback: CallbackQuery, **kwargs):
    """Смена языка (при выборе флага)."""
    user_id = callback.from_user.id
    new_lang = callback.data.replace("set_lang_", "")
    logger.info(f"Callback: User {user_id} switching language to {new_lang}")
    
    await db.update_user(user_id, language=new_lang, active=True)
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    
    await callback.answer()
    await callback.message.answer(
        t('lang_chosen', new_lang), 
        reply_markup=get_reply_keyboard_for_user(user_id, new_lang, user_data)
    )
    try: 
        await callback.message.delete()
    except Exception as e: 
        logger.debug(f"Callback: Could not delete lang message: {e}")

@router.callback_query(F.data.in_(["like", "dislike"]) | F.data.startswith("handle_reaction") | F.data.startswith("reaction:"))
async def handle_reaction_callback(callback: CallbackQuery, **kwargs):
    """
    Реакция на контент (лайк/дизлайк).
    ✅ ИСПРАВЛЕНО: Вся логика (цитата/alert) теперь внутри _handle_reaction.
    """
    lang = kwargs.get("lang", "ru")
    user_id = callback.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    
    reaction_type = "dislike" if "dislike" in callback.data else "like"
    
    # Вызываем единую логику из content_handlers
    await _handle_reaction(callback, user_data, lang, reaction_type)

@router.callback_query(F.data.startswith("accept_challenge"))
async def handle_accept_challenge_callback(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Принять челлендж (✅ КРИТИЧНО → force_db)."""
    user_id = callback.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    static_data = kwargs.get("static_data", {})
    logger.info(f"Handlers: User {user_id} accepting challenge (force_db=True)")
    await accept_challenge(callback, static_data, user_data, kwargs.get("lang", "ru"), state)

@router.callback_query(F.data == "new_challenge")
async def handle_new_challenge_callback_inline(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Новый челлендж (✅ КРИТИЧНО → force_db)."""
    user_id = callback.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    static_data = kwargs.get("static_data", {})
    logger.info(f"Handlers: User {user_id} requesting new challenge (force_db=True)")
    await send_new_challenge_message(callback, static_data, user_data, kwargs.get("lang", "ru"), state, is_edit=True)

@router.callback_query(F.data.startswith("complete_challenge"))
async def handle_complete_challenge_callback(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Выполнить челлендж (✅ КРИТИЧНО → force_db)."""
    user_id = callback.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    logger.info(f"Handlers: User {user_id} completing challenge (force_db=True)")
    await complete_challenge(callback, user_data, kwargs.get("lang", "ru"), state)

# --- ⌨️ ОСНОВНЫЕ КНОПКИ (Текстовые сообщения) ---

@router.message(btn_filter('btn_motivate'))
async def handle_motivate_button(message: Message, **kwargs):
    """Мотивирующая фраза."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    lang = user_data.get("language", "ru")
    static_data = kwargs.get("static_data", {})
    logger.debug(f"Handlers: User {user_id} requested motivation")
    await send_from_list(message, static_data, user_data, lang, "motivations", "title_motivation")

@router.message(btn_filter('btn_settings'))
async def handle_settings_button(message: Message, **kwargs):
    """Меню настроек."""
    user_id = message.from_user.id
    logger.info(f"Handlers: User {user_id} opened settings")
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    lang = user_data.get("language", "ru")
    await message.answer(t('msg_choose_action', lang), reply_markup=get_settings_keyboard(lang))

@router.message(F.text.in_(["🇺🇦 Українська", "🇬🇧 English", "🇷🇺 Русский"]))
async def handle_lang_switch_buttons(message: Message, **kwargs):
    """Переключение языка."""
    user_id = message.from_user.id
    new_lang = "ua" if "Українська" in message.text else ("en" if "English" in message.text else "ru")
    logger.info(f"Handlers: User {user_id} switched language to {new_lang}")
    await db.update_user(user_id, language=new_lang)
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    await message.answer(t('lang_chosen', new_lang), reply_markup=get_reply_keyboard_for_user(user_id, new_lang, user_data))

@router.message(btn_filter('btn_back'))
async def handle_back_button(message: Message, **kwargs):
    """Кнопка "Назад" в меню."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    lang = user_data.get("language", "ru")
    logger.debug(f"Handlers: User {user_id} going back to main menu")
    await message.answer(t('msg_welcome_back', lang), reply_markup=get_reply_keyboard_for_user(user_id, lang, user_data))

@router.message(btn_filter('btn_rules'))
async def handle_rules_button(message: Message, **kwargs):
    """Правила вселенной."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    lang = user_data.get("language", "ru")
    static_data = kwargs.get("static_data", {})
    logger.debug(f"Handlers: User {user_id} requested rules")
    await send_rules(message, static_data, user_data, lang)

@router.message(btn_filter('btn_rhythm'))
async def handle_rhythm_button(message: Message, **kwargs):
    """Ритм дня."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    lang = user_data.get("language", "ru")
    static_data = kwargs.get("static_data", {})
    logger.debug(f"Handlers: User {user_id} requested rhythm")
    await send_from_list(message, static_data, user_data, lang, "ritm", "title_rhythm")

@router.message(btn_filter('btn_challenge'))
async def handle_challenge_button(message: Message, state: FSMContext, **kwargs):
    """Челлендж дня."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    lang = user_data.get("language", "ru")
    static_data = kwargs.get("static_data", {})
    logger.info(f"Handlers: User {user_id} requested challenge (force_db=True)")
    await send_new_challenge_message(message, static_data, user_data, lang, state, is_edit=False)

@router.message(btn_filter('btn_profile'))
async def handle_profile_button(message: Message, **kwargs):
    """Профиль пользователя."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    lang = user_data.get("language", "ru")
    logger.info(f"Handlers: User {user_id} viewing profile (force_db=True)")
    await send_profile(message, user_data, lang)

# --- 👑 АДМИН-КНОПКИ ---

@router.message(btn_filter('btn_stats'))
async def handle_stats_button(message: Message, **kwargs):
    """Статистика (✅ КРИТИЧНО для админа → force_db)."""
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")):
        return
    
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    lang = user_data.get("language", "ru")
    logger.info(f"Handlers: Admin {message.from_user.id} viewing statistics (force_db=True)")
    await send_stats_report(message, kwargs.get("users_db", {}), lang)

@router.message(btn_filter('btn_pay_premium'))
async def handle_pay_button(message: Message, **kwargs):
    """Платежные инструкции."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    lang = user_data.get("language", "ru")
    logger.info(f"Handlers: User {user_id} viewing payment instructions (force_db=True)")
    await send_payment_instructions(message, user_data, lang)

@router.message(btn_filter('btn_want_demo'))
async def handle_want_demo_button(message: Message, **kwargs):
    """Активация нового демо периода."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=True)
    lang = user_data.get("language", "ru")
    logger.info(f"Handlers: User {user_id} activating new demo (force_db=True)")
    await activate_new_demo(message, user_data, lang)

@router.message(btn_filter('btn_reload_data'))
async def handle_reload_data(message: Message, bot: Bot, **kwargs):
    """Админская кнопка: переезагрузить контент."""
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")):
        return
    
    logger.warning(f"Admin {message.from_user.id} requesting RELOAD DATA")
    new_static_data = await load_static_data()
    if "static_data" in kwargs:
        kwargs["static_data"].clear()
        kwargs["static_data"].update(new_static_data)
    
    new_users_db = await db.get_all_users()
    if "users_db" in kwargs:
        kwargs["users_db"].clear()
        kwargs["users_db"].update(new_users_db)
    
    await setup_jobs_and_cache(bot, kwargs.get("users_db", {}), new_static_data)
    
    user_data = await _get_user_data(message.from_user.id, kwargs, force_db=True)
    lang = user_data.get("language", "ru")
    logger.info(f"Admin {message.from_user.id} successfully reloaded data")
    await message.answer(t('reload_confirm', lang))

@router.message(btn_filter('btn_show_users'))
async def handle_show_users_button(message: Message, **kwargs):
    """Админская кнопка: показать всех пользователей."""
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")):
        return
    
    logger.info(f"Admin {message.from_user.id} dumping users database")
    await show_users_command(message, kwargs.get("users_db", {}), True)

@router.message(btn_filter('btn_test_broadcast'))
async def handle_test_broadcast_button(message: Message, bot: Bot, **kwargs):
    """Админская кнопка: тестовая рассылка."""
    if not (int(message.from_user.id) == int(settings.ADMIN_CHAT_ID) or kwargs.get("is_admin")):
        return
    
    logger.info(f"Admin {message.from_user.id} starting test broadcast")
    await broadcast_test_command(message, bot, kwargs.get("static_data", {}), True)

# --- ❓ ИЗОЛИРОВАННЫЙ UNKNOWN TEXT ---
@router_unknown.message(F.text)
async def handle_unknown_text(message: Message, **kwargs):
    """Обработка неизвестных команд (фолбек)."""
    user_id = message.from_user.id
    user_data = await _get_user_data(user_id, kwargs, force_db=False)
    lang = user_data.get("language", "ru")
    logger.debug(f"Handlers: Unknown command from {user_id}: {message.text[:50]}")
    
    markup = get_reply_keyboard_for_user(user_id, lang, user_data)
    await message.answer(t('unknown_command', lang), reply_markup=markup)