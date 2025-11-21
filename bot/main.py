import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State

# --- Импорты ---
from config import settings, logger
from localization import t, Lang
from user_loader import load_static_data, load_users_with_fix # Загрузка JSON
from scheduler import setup_jobs_and_cache, scheduler
from utils import AccessMiddleware
from middlewares import TrackActivityMiddleware 
from database import db

# --- Роутеры ---
from commands import router as commands_router
from button_handlers import router as button_router
from callbacks import router as callback_router
# ✅ ВАЖНО: Переименовал для ясности, что это ВЕБ-админка
from admin_routes import router as web_admin_router 

# --- FSM Хранилище (асинхронное) ---
class DBSStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: str | State | None = None):
        state_str = state.state if isinstance(state, State) else state
        await db.update_fsm_storage(int(key.user_id), state=state_str)

    async def get_state(self, key: StorageKey) -> str:
        data = await db.get_fsm_storage(int(key.user_id))
        return data.get("state")

    async def set_data(self, key: StorageKey, data: dict):
        await db.update_fsm_storage(int(key.user_id), data=data)

    async def get_data(self, key: StorageKey) -> dict:
        data = await db.get_fsm_storage(int(key.user_id))
        return data.get("data", {})
    async def close(self): pass
    async def wait_closed(self): pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Bot starting (FULL Version + Web Admin Fix)...")
    
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = DBSStorage()
    dp = Dispatcher(storage=storage)

    # 1. Инициализация БД
    await db.init() 
    
    # 2. Загрузка статических данных (JSON) - ВОТ ЧТО ЧИНИТ КОНТЕНТ
    try:
        static_data = await load_static_data()
        logger.info(f"✅ Loaded static data keys: {list(static_data.keys())}")
    except Exception as e:
        logger.error(f"❌ Error loading static data: {e}")
        static_data = {}

    # 3. Загрузка кэша пользователей (для совместимости)
    users_db_cache = await load_users_with_fix() 
    
    # Передаем данные в диспетчер, чтобы хендлеры их видели
    dp["users_db"] = users_db_cache 
    dp["static_data"] = static_data
    dp["settings"] = settings
    
    # 4. Подключаем ТОЛЬКО ТЕЛЕГРАМ роутеры
    dp.include_router(commands_router)
    dp.include_router(button_router)
    dp.include_router(callback_router)
    # ❌ УБРАЛИ dp.include_router(admin_router) ОТСЮДА (это вызывало ошибку)
    
    # 5. Middlewares (ВАЖНО для языка и данных юзера)
    dp.update.outer_middleware(AccessMiddleware())
    dp.update.middleware(TrackActivityMiddleware())
    
    # 6. Планировщик
    await setup_jobs_and_cache(bot, users_db_cache, static_data)
    
    webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/{settings.BOT_TOKEN}"
    await bot.set_webhook(url=webhook_url, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=True)
    
    app.state.bot = bot
    app.state.dispatcher = dp
    
    yield
    
    logger.info("👋 Bot stopping...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await bot.delete_webhook()
    await bot.session.close()
    await db.close()

# --- FastAPI Приложение ---
app = FastAPI(lifespan=lifespan)

# ✅ 7. Подключаем админку ТОЛЬКО к сайту
app.include_router(web_admin_router) 

@app.post("/webhook/{token}")
async def webhook_handler(request: Request, token: str):
    if token != settings.BOT_TOKEN:
        return Response(content="Invalid token", status_code=403)
    bot: Bot = request.app.state.bot
    dp: Dispatcher = request.app.state.dispatcher
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=500)