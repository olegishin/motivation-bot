import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Update
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

# --- Импорты ---
from config import logger, settings, DEFAULT_TZ, SPECIAL_USER_IDS
from localization import t, Lang
from database import db
# ❌ Убрали здесь 'from content_handlers import handle_expired_demo'

# =====================================================
# 1. Вспомогательные функции
# ... (остальной код функции get_tz_from_lang и get_max_demo_cycles без изменений)

# =====================================================
# 4. ФУНКЦИИ ВРЕМЕНИ И РАССЫЛКИ (КРИТИЧЕСКОЕ ДОБАВЛЕНИЕ)
# ... (остальной код get_current_user_dt, is_time_for_user и safe_send без изменений)

# =====================================================
# 3. Middleware — Access Control
# =====================================================

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        
        user = None
        message = None
        if event.message:
            user = event.message.from_user
            message = event.message
        elif event.callback_query:
            user = event.callback_query.from_user
            message = event.callback_query.message

        if not user:
            return await handler(event, data)

        chat_id = user.id
        user_data = await db.get_user(chat_id)
        is_new_user = not bool(user_data)

        # --- Регистрация нового пользователя ---
        if is_new_user:
            lang_code = user.language_code if user.language_code in ["ru", "ua", "en"] else "ru"
            
            await db.add_user(user_id=chat_id)
            await db.update_user(
                user_id=chat_id,
                username=user.username,
                first_name=user.first_name, # Используем first_name
                language=lang_code,
                timezone=get_tz_from_lang(lang_code)
            )
            
            user_data = await db.get_user(chat_id)

        lang = get_user_lang(user_data)
        is_admin_flag = is_admin(chat_id)

        # --- Вставляем в data ---
        data.update({
            "user_data": user_data,
            "lang": lang,
            "is_admin": is_admin_flag,
            "is_new_user": is_new_user
        })

        # --- Проверка доступа (только для сообщений) ---
        if message and message.text:
            text = message.text

            # Заблокированный пользователь
            if user_data.get("is_active") is False and not is_admin_flag:
                return

            # Админ / платный / спец — полный доступ
            if is_admin_flag or chat_id in settings.SPECIAL_USER_IDS or user_data.get("is_paid", False):
                return await handler(event, data)

            # Разрешённые команды/кнопки
            # Здесь используются функции t() из localization, которые мы уже импортировали
            allowed_cmds = ("/start", "/language", "/timezone", "/cancel", "/pay")
            allowed_btns = (
                t('btn_pay_premium', lang),
                t('btn_pay_api_test_premium', lang),
                t('btn_want_demo', lang),
                t('cmd_cancel', lang)
            )

            if any(text.startswith(cmd) for cmd in allowed_cmds) or text in allowed_btns:
                return await handler(event, data)

            # Демо активно — пропускаем
            if not is_demo_expired(user_data):
                return await handler(event, data)

            # Демо истёк — показываем сообщение
            logger.info(f"Access denied for {chat_id} — demo expired")
            
            # ✅ ИСПРАВЛЕНИЕ: Импортируем функцию здесь, чтобы разорвать циклическую зависимость
            from content_handlers import handle_expired_demo
            await handle_expired_demo(message, user_data, lang)
            return

        # Для callback_query — просто пропускаем
        return await handler(event, data)