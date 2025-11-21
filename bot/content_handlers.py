# bot/content_handlers.py
# Файл содержит функции для отправки основного контента бота:
# Утренние/Вечерние рассылки, контент по запросу, и обработка истекшего демо.

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, ReplyKeyboardMarkup

from config import logger, settings
from database import db
from localization import t, Lang
import utils
# Импортируем все необходимые клавиатуры
from keyboards import (
    get_inline_feedback_keyboard, 
    get_broadcast_keyboard, 
    get_on_demand_keyboard, 
    get_payment_keyboard,
    main_menu_keyboard,
    get_reply_keyboard_for_user,
    # ✅ ДОБАВЛЕНО для реализации send_profile
    get_profile_keyboard 
)

# =====================================================
# 1. ОБЩИЕ ФУНКЦИИ ОТПРАВКИ (ИСПОЛЬЗУЕТСЯ ПЛАНИРОВЩИКОМ)
# =====================================================

def get_random_content_for_user(
    user_id: int,
    lang: Lang,
    category: str,
    static_content: dict
) -> Tuple[Optional[str], Optional[str]]:
    """
    Выбирает случайный контент для рассылки по категории.
    Возвращает (отформатированный_текст, заголовок_категории).
    """
    
    # Получаем имя пользователя для форматирования
    # В планировщике USERS_CACHE уже должен содержать first_name
    
    # 1. Получаем список контента
    content_list = static_content.get(category, [])
    if not content_list:
        logger.warning(f"Content list for category '{category}' is empty in static data.")
        return None, None
        
    # 2. Выбор случайного контента
    content_item = random.choice(content_list)
    
    # 3. Форматирование текста
    if isinstance(content_item, dict):
        text_template = content_item.get("text", "")
    else:
        text_template = str(content_item)
        
    # Форматирование (имя здесь не используется, но оставим для совместимости)
    formatted_text = text_template # В рассылках имя не обязательно
    
    # 4. Заголовок
    if category == "morning":
        title_key = "title_morning"
    elif category == "ritm":
        title_key = "title_rhythm"
    elif category == "motivations":
        title_key = "title_motivation"
    elif category == "evening":
        title_key = "title_evening"
    elif category == "challenges":
        title_key = "title_challenge"
    else:
        title_key = category
        
    category_title = t(title_key, lang)
    
    return formatted_text, category_title


async def get_content_and_send(
    bot: Bot, 
    chat_id: int, 
    user_data: dict, 
    static_data: dict, 
    lang: Lang, 
    category: str, 
    title_key: str, 
    keyboard_func: Optional[callable] = get_broadcast_keyboard
):
    """
    Основная функция для выбора, форматирования и отправки контента.
    Используется планировщиком и командами по запросу.
    """
    
    # 1. Получаем контент
    content, title = get_random_content_for_user(chat_id, lang, category, static_data)
    
    if not content:
        logger.warning(f"Failed to retrieve content for {category} for user {chat_id}.")
        return

    # 2. Форматирование текста
    name = user_data.get("first_name", "друг")
    try:
        formatted_text = content.format(name=name)
    except Exception as e:
        logger.error(f"Error formatting content for {category}: {e}")
        formatted_text = content
    
    full_text = f"✨ {title}\n\n{formatted_text}"
    
    # 3. Клавиатура (передаем formatted_text для совместимости)
    reply_markup = keyboard_func(category=category, lang=lang, current_text=formatted_text) if keyboard_func else None

    # 4. Безопасная отправка
    await utils.safe_send(
        bot,
        chat_id,
        full_text,
        reply_markup=reply_markup
    )
    
    await db.update_user(chat_id, content_sent=user_data.get("content_sent", 0) + 1)
    logger.info(f"Sent {category} content to {chat_id}.")


async def send_from_list(
    message: Optional[Message], 
    static_data: dict, 
    user_data: dict, 
    lang: Lang, 
    category: str, 
    title_key: str,
    bot: Optional[Bot] = None, 
    chat_id: Optional[int] = None
):
    """Обертка для отправки контента: определяет chat_id/bot и вызывает get_content_and_send."""
    
    if message:
        bot = message.bot
        chat_id = message.chat.id
        keyboard_func = get_on_demand_keyboard # По запросу
        # Обновляем user_data именем из Message
        user_data['first_name'] = message.from_user.first_name 
    elif bot and chat_id:
        keyboard_func = get_broadcast_keyboard # Планировщик
    else:
        logger.error("Cannot send content: missing Message or Bot/chat_id.")
        return

    await get_content_and_send(
        bot=bot, 
        chat_id=chat_id, 
        user_data=user_data, 
        static_data=static_data, 
        lang=lang, 
        category=category, 
        title_key=title_key,
        keyboard_func=keyboard_func
    )

# =====================================================
# 2. СПЕЦИАЛЬНЫЕ ФУНКЦИИ (РАССЫЛКА)
# =====================================================

async def send_morning(bot: Bot, chat_id: int, static_data: dict, user_data: dict, lang: Lang):
    """Отправка утреннего контента по расписанию."""
    await get_content_and_send(
        bot=bot, 
        chat_id=chat_id, 
        user_data=user_data, 
        static_data=static_data, 
        lang=lang, 
        category="morning", # Изменено на 'morning'
        title_key="title_morning",
        keyboard_func=get_broadcast_keyboard
    )

async def send_evening(bot: Bot, chat_id: int, static_data: dict, user_data: dict, lang: Lang):
    """Отправка вечернего контента по расписанию."""
    await get_content_and_send(
        bot=bot, 
        chat_id=chat_id, 
        user_data=user_data, 
        static_data=static_data, 
        lang=lang, 
        category="evening", # Изменено на 'evening'
        title_key="title_evening",
        keyboard_func=get_broadcast_keyboard
    )

# =====================================================
# 3. ОБРАБОТЧИКИ КОМАНД (для commands.py)
# =====================================================

async def handle_start_command(message: Message, static_data: dict, user_data: dict, lang: Lang, is_new_user: bool):
    """
    Обрабатывает команду /start.
    В зависимости от состояния пользователя, выдает приветствие или меню.
    """
    chat_id = message.chat.id
    name = user_data.get("first_name", message.from_user.first_name or "друг")
    
    if is_new_user:
        welcome_text = t('welcome_new', lang, name=name)
        # Устанавливаем демо-период (для тестеров/симуляторов)
        demo_days = utils.get_demo_days(chat_id)
        expiry_date = datetime.now(ZoneInfo("UTC")) + timedelta(days=demo_days)
        
        await db.update_user(
            chat_id, 
            demo_expiration=expiry_date.isoformat(),
            demo_cycles=1, 
            is_active=True
        )
        logger.info(f"New user {chat_id}. Demo set for {demo_days} days.")
        
        await message.answer(
            welcome_text,
            reply_markup=get_reply_keyboard_for_user(chat_id, lang, user_data) 
        )
        
        # Отправка первого утреннего сообщения сразу после регистрации
        await get_content_and_send(
            message.bot, 
            chat_id, 
            user_data, 
            static_data, 
            lang, 
            category="morning", # Используем 'morning'
            title_key="title_morning",
            keyboard_func=None
        )
        
    else:
        # Для вернувшегося пользователя просто отправляем меню
        status_text = t('profile_status_premium' if user_data.get('is_paid') else 'profile_status_demo', lang)
        greetings_text = t('greetings_back', lang, name=name, status_text=status_text) # Используем greetings_back
        await message.answer(
            greetings_text,
            reply_markup=get_reply_keyboard_for_user(chat_id, lang, user_data)
        )


async def handle_expired_demo(message: Message, user_data: dict, lang: Lang):
    """
    Обрабатывает попытку доступа при истекшем демо.
    Вызывается из AccessMiddleware.
    """
    
    chat_id = message.chat.id
    user_name = user_data.get("first_name", message.from_user.first_name or "друг")
    
    demo_cycles = user_data.get("demo_cycles", 0)
    max_cycles = utils.get_max_demo_cycles(chat_id)
    cooldown_days = utils.get_cooldown_days(chat_id)
    demo_days = utils.get_demo_days(chat_id)
    
    try:
        demo_exp_date = datetime.fromisoformat(user_data.get("demo_expiration")).replace(tzinfo=ZoneInfo("UTC"))
        next_demo_dt = demo_exp_date + timedelta(days=cooldown_days)
        now_utc = datetime.now(ZoneInfo("UTC"))
        
        if now_utc < next_demo_dt:
            # --- Режим КУЛДАУНА ---
            time_left = next_demo_dt - now_utc
            hours_left, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes_left, _ = divmod(remainder, 60)
            
            markup = get_payment_keyboard(lang, is_test_user=(chat_id in settings.TESTER_USER_IDS), show_new_demo=False)
            text = t('demo_expired_cooldown', lang, name=user_name, hours=hours_left, minutes=minutes_left)
            await message.answer(text, reply_markup=markup)
            
        else:
            if demo_cycles < max_cycles:
                # --- Режим ВЫБОРА (активировать демо/купить) ---
                markup = get_payment_keyboard(lang, is_test_user=(chat_id in settings.TESTER_USER_IDS), show_new_demo=True)
                text = t('demo_expired_choice', lang, name=user_name, demo_days=demo_days)
                await message.answer(text, reply_markup=markup)
            else:
                # --- Режим ОПЛАТА (лимит демо исчерпан) ---
                markup = get_payment_keyboard(lang, is_test_user=(chat_id in settings.TESTER_USER_IDS), show_new_demo=False)
                text = t('demo_expired_final', lang, name=user_name)
                await message.answer(text, reply_markup=markup)
                
    except (ValueError, TypeError):
        # Если demo_expiration некорректно, предлагаем выбор
        markup = get_payment_keyboard(lang, is_test_user=(chat_id in settings.TESTER_USER_IDS), show_new_demo=(demo_cycles < max_cycles))
        await message.answer(t('demo_expired_choice', lang, name=user_name, demo_days=demo_days), reply_markup=markup)

# =====================================================
# 4. ОБРАБОТЧИКИ ПРОФИЛЯ (для button_handlers.py)
# =====================================================

async def send_profile(message: Message, user_data: dict, lang: Lang):
    """
    Форматирует и отправляет пользователю информацию о его профиле.
    """
    chat_id = message.chat.id
    
    is_paid = user_data.get('is_paid', False)
    status_key = 'profile_status_premium' if is_paid else 'profile_status_demo'
    status_text = t(status_key, lang)
    
    expiry_info = ""
    if not is_paid and user_data.get('demo_expiration'):
        try:
            # Получаем часовой пояс пользователя
            user_tz = utils.get_user_tz(user_data)
            
            # Конвертируем дату истечения из UTC в TZ пользователя
            expiry_dt_utc = datetime.fromisoformat(user_data['demo_expiration']).replace(tzinfo=ZoneInfo("UTC"))
            expiry_dt_local = expiry_dt_utc.astimezone(user_tz)
            
            # Форматирование даты
            date_format = "%d.%m.%Y %H:%M %Z"
            expiry_info = t('profile_demo_expires', lang, date=expiry_dt_local.strftime(date_format))
            
            status_text += expiry_info
        except Exception as e:
            logger.error(f"Error processing expiry date for profile: {e}")
            
    # Собираем текст
    profile_text = t(
        'profile_info', 
        lang, 
        user_id=chat_id, 
        status=status_text
    )
    
    # Отправляем сообщение с клавиатурой профиля
    await message.answer(
        profile_text,
        reply_markup=get_profile_keyboard(lang=lang, is_paid=is_paid),
        parse_mode="HTML"
    )