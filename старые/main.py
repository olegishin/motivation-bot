# 14 - bot/main.py
# Точка входа

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State
import os

# --- Импорты ---
from config import settings, logger
from localization import t 
from bot.user_loader import load_static_data, load_users_with_fix, save_users_sync
from bot.scheduler import setup_jobs_and_cache, scheduler
from bot.utils import AccessMiddleware 
from database import db

# --- Роутеры ---
from bot.commands import router as commands_router
from bot.button_handlers import router as button_router
from bot.callbacks import router as callback_router
from bot.admin_routes import router as admin_router # ✅ Импортируем админку

# --- FSM Хранилище в БД ---
class DBSStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: str | State | None = None):
        state_str = state.state if isinstance(state, State) else state
        await db.update_fsm_storage(int(key.user_id), state=state_str)

    async def get_state(self, key: StorageKey) -> str:
        data = await db.get_fsm_storage(int(key.user_id))
        # Aiogram ожидает строку или None. Если нет - вернем None
        return data.get("state")

    async def set_data(self, key: StorageKey, data: dict):
        await db.update_fsm_storage(int(key.user_id), data=data)

    async def get_data(self, key: StorageKey) -> dict:
        data = await db.get_fsm_storage(int(key.user_id))
        # Если FSM данных нет, возвращаем пустой словарь
        return data.get("data", {}) 
    async def close(self): pass
    async def wait_closed(self): pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Bot starting (Full Version)...")
    
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = DBSStorage()
    dp = Dispatcher(storage=storage)

    # 1. Инициализация БД и миграция
    users_db_cache = await load_users_with_fix() # Инициализирует БД и загружает кэш
    
    # 2. Загрузка статических данных
    static_data = await load_static_data()
    
    # Передаем данные в диспетчер и состояние приложения
    app.state.users_db = users_db_cache # Кэш для админки/планировщика
    dp["users_db"] = users_db_cache 
    dp["static_data"] = static_data
    dp["settings"] = settings
    
    # 3. Подключаем роутеры
    dp.include_router(commands_router)
    dp.include_router(button_router)
    dp.include_router(callback_router)
    # Админские роуты подключаются только через FastAPI (app.include_router)

    # 4. Middlewares
    dp.update.outer_middleware(AccessMiddleware())
    # dp.update.middleware(TrackActivityMiddleware()) # Убрал, т.к. нет файла middlewares
    
    # 5. Планировщик
    await setup_jobs_and_cache(bot, users_db_cache, static_data)
    
    # 6. Установка вебхука
    webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/{settings.BOT_TOKEN}"
    try:
        await bot.set_webhook(
            url=webhook_url, 
            allowed_updates=dp.resolve_used_update_types(), 
            drop_pending_updates=True
        )
        logger.info(f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ НЕ УДАЛОСЬ установить вебхук: {e}")
    
    app.state.bot = bot
    app.state.dispatcher = dp
    
    logger.info(f"✅ Lifespan: Бот полностью запущен.")
    
    # Уведомление админа о старте (если не Polling)
    if os.getenv("WEBHOOK_URL"):
        try:
            await bot.send_message(settings.ADMIN_CHAT_ID, t('admin_bot_started', lang="ru"))
        except Exception as e:
            logger.error(f"Не удалось отправить админу сообщение о старте: {e}")

    yield # Приложение запущено
    
    # 7. Остановка (shutdown)
    logger.info("👋 Bot stopping...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
        
    save_users_sync(users_db_cache) # Аварийный JSON дамп
    
    try:
        # Удаляем вебхук при остановке
        await bot.delete_webhook(drop_pending_updates=True) 
    except Exception: pass
    await bot.session.close()
    await db.close() # Закрываем соединение с БД (хотя aiosqlite и так управляет)
    logger.info("👋 Бот выключен.")

# --- FastAPI Приложение ---
app = FastAPI(lifespan=lifespan)

# Health Check
@app.get("/")
async def root():
    return {"status": "FotiniaBot v10.25 is alive"}
    
# 1. Подключаем админку
app.include_router(admin_router) 

@app.post("/webhook/{token}")
async def webhook_handler(request: Request, token: str):
    if token != settings.BOT_TOKEN:
        return Response(content="Invalid token", status_code=403)
        
    bot: Bot = request.app.state.bot
    dp: Dispatcher = request.app.state.dispatcher
    
    # Обновляем кэш из состояния приложения (FastAPI)
    # Это важно, т.к. планировщик и админка могут изменить app.state.users_db
    dp["users_db"] = request.app.state.users_db

    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        logger.exception("Полный traceback ошибки webhook:") 
        return Response(status_code=500)

# --- Локальный запуск в режиме Polling ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Запуск в режиме Polling (локальная отладка)...")
    
    async def run_polling():
        logger.info("Starting in POLLING mode...")
        
        bot = Bot(
            token=settings.BOT_TOKEN, 
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        storage = DBSStorage()
        dp = Dispatcher(storage=storage)

        # 1. Инициализация БД и кэша
        users_db_cache = await load_users_with_fix()
        static_data = await load_static_data()

        dp["users_db"] = users_db_cache
        dp["static_data"] = static_data
        dp["settings"] = settings
        
        # 2. Подключение роутеров
        dp.include_router(commands_router)
        dp.include_router(button_router)
        dp.include_router(callback_router)
        dp.include_router(admin_router) 

        # 3. Middlewares
        dp.update.outer_middleware(AccessMiddleware())

        # 4. Планировщик
        await setup_jobs_and_cache(bot, users_db_cache, static_data)
        
        logger.info("Bot started (polling)...")
        await bot.delete_webhook(drop_pending_updates=True)
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            # Очистка при остановке Polling
            if scheduler.running:
                scheduler.shutdown(wait=False)
            await bot.session.close()
            await db.close()

    asyncio.run(run_polling())
