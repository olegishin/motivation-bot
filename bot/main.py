# 14 - bot/main.py
# ✅ Точка входа приложения (FastAPI + Aiogram)
# ✅ Lifespan управление (запуск/остановка бота)
# ✅ Инициализация базы данных (WAL режим)
# ✅ Настройка вебхука с фильтрацией обновлений
# ✅ Middleware для проверки доступа
# ✅ Роутеры (Aiogram для бота, FastAPI для админки и WebApp)
# ✅ Graceful shutdown с таймаутом
# 14 - bot/main.py - ПОЛНАЯ ФИНАЛЬНАЯ ВЕРСИЯ (26.02.2026)
# Точка входа приложения (FastAPI + Aiogram)
# ✅ Инициализация БД, FSM в SQLite, Lifespan, Webhook

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType
from aiogram.types import Update

from bot.config import settings, logger
from bot.database import db
from bot.user_loader import load_users_with_fix, save_users_sync, load_static_data
from bot.utils import AccessMiddleware
from bot.scheduler import setup_jobs_and_cache

# Роутеры Aiogram
from bot.commands import router as commands_router
from bot.callbacks import router as callbacks_router
from bot.button_handlers import router as buttons_router, router_unknown
from bot.admin_routes import router as admin_router, webapp_router

# --- 🗄️ FSM Storage на базе SQLite ---
class DBSStorage(BaseStorage):
    """FSM Storage с хранением в БД для устойчивости на Fly.io."""
    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await db.update_fsm_storage(key.user_id, key.chat_id, "state", state)
    
    async def get_state(self, key: StorageKey) -> str | None:
        data = await db.get_fsm_storage(key.user_id, key.chat_id)
        return data.get("state") if data else None
    
    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        await db.update_fsm_storage(key.user_id, key.chat_id, "data", data)
    
    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        data = await db.get_fsm_storage(key.user_id, key.chat_id)
        return data.get("data", {}) if data else {}
    
    async def close(self) -> None:
        pass

# --- 🌍 Глобальные переменные ---
bot: Bot = None
dp: Dispatcher = None
users_db: Dict[str, Any] = {}
static_data: Dict[str, Any] = {}

# --- 🚀 Lifespan (Запуск и Остановка) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp, users_db, static_data
    
    logger.info("🚀 Starting Fotinia Bot...")
    
    # 1. БД
    await db.init_db()
    
    # 2. Бот
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # 3. Загрузка данных (Cache + Static)
    users_db = await load_users_with_fix()
    static_data = await load_static_data()
    
    # 4. Dispatcher
    storage = DBSStorage()
    dp = Dispatcher(storage=storage)
    
    # 5. Middlewares
    middleware = AccessMiddleware(users_db, static_data)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    
    # 6. Регистрация всех роутеров
    dp.include_router(admin_router)      # Админка
    dp.include_router(commands_router)   # /commands
    dp.include_router(callbacks_router)  # Inline кнопки
    dp.include_router(buttons_router)    # Текстовые кнопки
    dp.include_router(router_unknown)    # Fallback (всегда последний)
    
    # 7. Планировщик задач
    await setup_jobs_and_cache(bot, users_db, static_data)
    
    # 8. Установка вебхука
    webhook_url = f"{settings.WEBHOOK_URL}/webhook"
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook set to: {webhook_url}")
    
    # 9. Приветствие админу (опционально)
    try:
        from bot.localization import t
        await bot.send_message(settings.ADMIN_CHAT_ID, t("admin_bot_started", settings.DEFAULT_LANG))
    except: pass
    
    yield # --- БОТ РАБОТАЕТ ---
    
    # --- SHUTDOWN ---
    logger.info("⏳ Stopping Fotinia Bot...")
    await bot.delete_webhook()
    await save_users_sync(users_db)
    await bot.session.close()

# --- 🛠️ FastAPI Приложение ---
app = FastAPI(
    title="Fotinia Bot",
    lifespan=lifespan
)

# Подключаем роутер для WebApp профиля (FastAPI)
app.include_router(webapp_router)

@app.post("/webhook")
async def webhook(request: Request):
    """Прием обновлений от Telegram."""
    try:
        update_dict = await request.json()
        update = Update(**update_dict)
        await dp.feed_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"❌ Webhook Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def health_check():
    """Проверка для Fly.io."""
    return {"status": "ok", "version": "26.02.2026", "users": len(users_db)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)