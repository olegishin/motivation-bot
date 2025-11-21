from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from localization import t, Lang
# Импортируем функции отправки контента (убедись, что content_handlers.py существует!)
from content_handlers import send_from_list, send_profile 
from keyboards import main_menu_keyboard, get_settings_keyboard
from commands import send_stats_report
from database import db
from config import settings

router = Router()

# 1. Мотивация
@router.message(F.text.contains("💪")) # Ловим по эмодзи для всех языков
@router.message(F.text.contains("Motivate"))
@router.message(F.text.contains("Мотивуй"))
async def handle_motivation(message: types.Message, static_data: dict, user_data: dict, lang: str):
    await send_from_list(message, static_data, user_data, lang, category="motivations", title_key="title_motivation")

# 2. Ритм дня
@router.message(F.text.contains("🎵"))
@router.message(F.text.contains("Rhythm"))
@router.message(F.text.contains("Ритм"))
async def handle_rhythm(message: types.Message, static_data: dict, user_data: dict, lang: str):
    await send_from_list(message, static_data, user_data, lang, category="ritm", title_key="title_rhythm")

# 3. Правила Вселенной
@router.message(F.text.contains("📜"))
@router.message(F.text.contains("Rules"))
@router.message(F.text.contains("Правила"))
async def handle_rules(message: types.Message, static_data: dict, user_data: dict, lang: str):
    # ВАЖНО: категория должна совпадать с названием в JSON (universe_laws)
    await send_from_list(message, static_data, user_data, lang, category="universe_laws", title_key="title_morning")

# 4. Челлендж
@router.message(F.text.contains("⚔️"))
@router.message(F.text.contains("Challenge"))
@router.message(F.text.contains("Челлендж"))
@router.message(F.text.contains("Челендж"))
async def handle_challenge(message: types.Message, static_data: dict, user_data: dict, lang: str):
    await send_from_list(message, static_data, user_data, lang, category="challenges", title_key="title_challenge")

# 5. Профиль
@router.message(F.text.contains("👤"))
@router.message(F.text.contains("Profile"))
@router.message(F.text.contains("Профіль"))
async def handle_profile(message: types.Message, user_data: dict, lang: str):
    await send_profile(message, user_data, lang)

# 6. Настройки
@router.message(F.text.contains("⚙️"))
@router.message(F.text.contains("Settings"))
@router.message(F.text.contains("Налаштування"))
async def handle_settings(message: types.Message, user_data: dict, lang: str):
    await message.answer(t('settings_menu_text', lang), reply_markup=get_settings_keyboard(lang))

# 7. Статистика (для всех, перенаправляет админа)
@router.message(F.text.contains("📊"))
async def handle_stats(message: types.Message):
    if message.from_user.id == settings.ADMIN_CHAT_ID:
        await send_stats_report(message, db, "ru")
    else:
        await message.answer(t('stats_info_user', "ru"))

# 8. Отмена
@router.message(F.text.contains("❌"))
async def handle_cancel(message: types.Message, state: FSMContext, lang: str):
    await state.clear()
    await message.answer(t('cancel_success', lang), reply_markup=main_menu_keyboard(lang))