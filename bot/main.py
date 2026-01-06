# 14 - bot/main.py — финальная рабочая версия (с защитой от дублей планировщика)

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from bot.config import settings, logger
from bot.database import db
from bot.user_loader import load_users_with_fix, save_users_sync, load_static_data
from bot.scheduler import setup_jobs_and_cache, scheduler
from bot.utils import AccessMiddleware
from bot.content_handlers import notify_admins

# Роутеры
from bot.commands import router as commands_router
from bot.button_handlers import router as button_router
from bot.callbacks import router as callback_router
from bot.admin_routes import router as admin_router, webapp_router

# --- Хранилище FSM на базе SQLite ---
class DBSStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: str | None = None):
        await db.update_fsm_storage(int(key.user_id), state=state)

    async def get_state(self, key: StorageKey) -> str | None:
        fsm_raw = await db.get_fsm_storage(int(key.user_id))
        return fsm_raw.get("state")

    async def set_data(self, key: StorageKey, data: dict):
        await db.update_fsm_storage(int(key.user_id), data=data)

    async def get_data(self, key: StorageKey) -> dict:
        fsm_raw = await db.get_fsm_storage(int(key.user_id))
        return fsm_raw.get("data", {})

    async def close(self): pass
    async def wait_closed(self): pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Bot starting...")

    # Инициализация бота
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=DBSStorage())

    await db.init()

    # Загружаем кэш и статику
    users_db_cache = await load_users_with_fix()
    static_data = await load_static_data()

    # Сохраняем в state приложения
    app.state.bot = bot
    app.state.users_db = users_db_cache
    app.state.dispatcher = dp 

    # Прокидываем данные в роутеры
    dp["users_db"] = users_db_cache
    dp["static_data"] = static_data
    dp["settings"] = settings

    # Middleware
    middleware = AccessMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    
    # Регистрация роутеров
    dp.include_router(commands_router)
    dp.include_router(button_router)
    dp.include_router(callback_router)

    # Настройка задач планировщика (setup_jobs_and_cache теперь имеет защиту replace_existing)
    await setup_jobs_and_cache(bot, users_db_cache, static_data)

    # Установка вебхука
    webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/{settings.BOT_TOKEN}"
    try:
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
        logger.info(f"Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"Не удалось установить вебхук: {e}")

    try:
        await notify_admins(bot, "🚀 <b>Бот запущен. Планировщик активен.</b>")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    logger.info("Бот полностью запущен!")
    
    yield  # Здесь приложение работает
    
    # --- ЗАВЕРШЕНИЕ РАБОТЫ ---
    logger.info("Остановка бота...")
    
    # Корректно выключаем планировщик
    if scheduler.running:
        scheduler.shutdown(wait=False)
    
    # Синхронизируем данные перед выходом
    save_users_sync(users_db_cache)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except:
        pass
        
    await bot.session.close()
    logger.info("Бот остановлен.")


app = FastAPI(lifespan=lifespan)
app.include_router(admin_router)
app.include_router(webapp_router)


@app.get("/")
async def root():
    return {"status": "FotiniaBot Working", "version": "10.60"}


@app.post("/webhook/{token}")
async def webhook_handler(request: Request, token: str):
    if token != settings.BOT_TOKEN:
        return Response("Forbidden", status_code=403)

    bot: Bot = request.app.state.bot
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await request.app.state.dispatcher.feed_update(bot=bot, update=update) 
    except Exception as e:
        logger.error(f"Webhook error handled: {e}")
        return Response("OK (Handled)", status_code=200)

    return Response(status_code=200)