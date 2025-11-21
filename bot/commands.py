# 9 - bot/commands.py

import logging
from aiogram import Router, F, types
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from config import settings, logger
from database import db
from localization import t, Lang
from content_handlers import handle_start_command
from user_loader import load_static_data
# Импортируем клавиатуру для test_pay
from keyboards import main_menu_keyboard

router = Router()

# =====================================================
# 1. START
# =====================================================
@router.message(CommandStart())
async def cmd_start(message: Message, static_data: dict, user_data: dict, lang: Lang, state: FSMContext):
    # Сбрасываем состояние FSM (если было)
    await state.clear()
    
    # Проверяем, новый ли это пользователь
    is_new = False
    if not user_data.get("demo_expiration") and not user_data.get("is_paid"):
        is_new = True

    # Основная логика старта (приветствие, выдача демо и т.д.)
    await handle_start_command(message, static_data, user_data, lang, is_new_user=is_new)


# =====================================================
# 2. АДМИН: СБРОС ПОЛЬЗОВАТЕЛЯ
# =====================================================
@router.message(Command("reset_user"))
async def cmd_reset_user(message: Message, command: CommandObject):
    """
    Использование: /reset_user 123456789
    """
    # Проверка прав админа
    if message.from_user.id != settings.ADMIN_CHAT_ID:
        return

    target_id_str = command.args
    if not target_id_str:
        await message.answer("⚠️ Укажи ID пользователя.\nПример: <code>/reset_user 123456789</code>", parse_mode="HTML")
        return

    try:
        target_id = int(target_id_str.strip())
    except ValueError:
        await message.answer("⚠️ ID должен быть числом.")
        return

    # Удаляем из базы
    await db.delete_user(target_id)
    
    await message.answer(f"✅ Пользователь <code>{target_id}</code> был полностью удален из базы.\nПри следующем его входе он будет как новый.", parse_mode="HTML")


# =====================================================
# 3. АДМИН: СТАТИСТИКА (НОВАЯ, ПОДРОБНАЯ)
# =====================================================
async def send_stats_report(message: Message, db, lang: str):
    # Получаем расширенную статистику напрямую из SQLite
    stats = await db.get_stats()
    
    text = (
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 <b>Всего в базе:</b> {stats['total']}\n"
        f"✅ <b>Живая аудитория:</b> {stats['alive']}\n"
        f"🚫 <b>Заблокировали (Мертвые):</b> {stats['blocked']}\n\n"
        
        f"🔥 <b>Активны за 24ч:</b> {stats['active_24h']}\n"
        f"🆕 <b>Новых за сегодня:</b> {stats['new_today']}\n\n"
        
        f"👑 <b>Premium:</b> {stats['premium']}\n"
        f"🆓 <b>Demo:</b> {stats['demo_total']}\n"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id == settings.ADMIN_CHAT_ID:
        # Передаем db глобально
        await send_stats_report(message, db, "ru")


# =====================================================
# 4. АДМИН: ФАЙЛ С ПОЛЬЗОВАТЕЛЯМИ (BackUp)
# =====================================================
@router.message(Command("show_users"))
async def cmd_show_users(message: Message):
    if message.from_user.id != settings.ADMIN_CHAT_ID:
        return
        
    if settings.USERS_FILE.exists() and settings.USERS_FILE.stat().st_size > 2:
        await message.answer_document(
            document=FSInputFile(settings.USERS_FILE),
            caption="📂 База пользователей (JSON Backup)"
        )
    else:
        await message.answer("Файл бэкапа пуст или отсутствует.")


# =====================================================
# 5. ТЕСТОВАЯ ОПЛАТА (ДЛЯ АДМИНА/ТЕСТЕРОВ)
# =====================================================
@router.message(Command("test_pay"))
async def cmd_test_pay(message: Message, user_data: dict, lang: Lang):
    # Только для тестеров и админа
    if message.from_user.id not in settings.TESTER_USER_IDS and message.from_user.id != settings.ADMIN_CHAT_ID:
        return

    # Эмуляция успешной оплаты в базе
    await db.update_user(message.from_user.id, is_paid=True)
    # Обновляем локальный объект, чтобы изменения применились сразу в этой сессии
    user_data['is_paid'] = True
    
    await message.answer("Payment Successful (TEST) ✅", reply_markup=main_menu_keyboard())