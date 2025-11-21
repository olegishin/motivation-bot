# bot/button_handlers.py

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from datetime import datetime

from config import logger, settings
from database import db
from localization import t, Lang
# ✅ ИСПРАВЛЕНО: Импортируем send_from_list и send_profile из content_handlers
from content_handlers import send_from_list, send_profile 
from states import GeneralStates
from keyboards import get_cancel_keyboard, main_menu_keyboard, get_challenge_keyboard
# Импортируем функцию статистики из commands.py (убедитесь, что она там есть)
from commands import send_stats_report 

router = Router()

# =====================================================
# 1. ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ (Reply Keyboard)
# =====================================================

@router.message(F.text.startswith("💪 Мотивируй меня"))
async def handle_motivation(message: Message, static_data: dict, user_data: dict, lang: Lang):
    """Отправка мотивационного контента по запросу."""
    await send_from_list(
        message, 
        static_data, 
        user_data, 
        lang, 
        category="motivations", 
        title_key="title_motivation"
    )

@router.message(F.text.startswith("🎵 Ритм дня"))
async def handle_rhythm(message: Message, static_data: dict, user_data: dict, lang: Lang):
    """Отправка контента "Ритм дня" по запросу."""
    await send_from_list(
        message, 
        static_data, 
        user_data, 
        lang, 
        category="ritm", 
        title_key="title_rhythm"
    )

@router.message(F.text.startswith("📜 Правила Вселенной"))
async def handle_rules(message: Message, static_data: dict, user_data: dict, lang: Lang):
    """
    Отправка контента "Правила Вселенной".
    Используем категорию "morning" для тестовых целей.
    """
    await send_from_list(
        message, 
        static_data, 
        user_data, 
        lang, 
        category="morning", # Используем утренний контент
        title_key="title_morning" 
    )

@router.message(F.text.startswith("⚔️ Челлендж дня"))
async def handle_challenge(message: Message, static_data: dict, user_data: dict, lang: Lang):
    """
    Отправка Челленджа дня. 
    (В идеале, здесь должна быть сложная логика из challenges.py)
    Пока используем общую отправку для категории "challenges".
    """
    await send_from_list(
        message, 
        static_data, 
        user_data, 
        lang, 
        category="challenges", 
        title_key="title_challenge"
    )

# =====================================================
# 2. ПРОФИЛЬ / НАСТРОЙКИ (Переход)
# =====================================================

@router.message(F.text.startswith("👤 Профиль"))
async def handle_profile_menu(message: Message, user_data: dict, lang: Lang):
    """
    Показывает информацию о пользователе. 
    Использует централизованную функцию send_profile из content_handlers.
    """
    # ✅ ИСПРАВЛЕНО: Вызываем функцию, которая форматирует и отправляет профиль
    await send_profile(message, user_data, lang)


@router.message(F.text.startswith("⚙️ Настройки"))
async def handle_settings_menu(message: Message, user_data: dict, lang: Lang):
    """Показывает меню настроек."""
    from keyboards import get_settings_keyboard
    await message.answer(
        t('settings_menu_text', lang),
        reply_markup=get_settings_keyboard(lang=lang)
    )


@router.message(F.text.startswith("📊 Статистика"))
async def handle_stats_button(message: Message):
    """Перенаправляет на админскую команду /stats (или показывает инфо)."""
    if message.from_user.id == settings.ADMIN_CHAT_ID:
        # send_stats_report требует db и lang. Импортируем из commands.py для переиспользования
        from commands import send_stats_report 
        await send_stats_report(message, db, "ru") 
    else:
        await message.answer(t('stats_info_user', message.text.lower()))

# =====================================================
# 3. ОБРАБОТЧИК ОТМЕНЫ
# =====================================================

@router.message(F.text == "❌ Отмена")
async def handle_cancel(message: Message, state: FSMContext, lang: Lang):
    """Обрабатывает нажатие кнопки "Отмена" и сбрасывает FSM."""
    
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(t('cancel_no_action', lang), reply_markup=main_menu_keyboard())
        return

    await state.clear()
    await message.answer(t('cancel_success', lang), reply_markup=main_menu_keyboard())