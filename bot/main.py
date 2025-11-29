# 14 - bot/main.py - Точка входа

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties 
from aiogram.enums import ParseMode 
from aiogram.types import Update
from aiogram.fsm.storage.base import BaseStorage, StorageKey

# ✅ ИСПРАВЛЕНО: Импорты через bot.xxx
from bot.config import settings, logger
from bot.localization import t, Lang
from bot.user_loader import load_static_data, save_users_sync
from bot.scheduler import setup_jobs_and_cache, scheduler
from bot.utils import AccessMiddleware
from bot.database import db

# ✅ ИСПРАВЛЕНО: Роутеры тоже через bot.xxx
from bot.commands import router as commands_router
from bot.button_handlers import router as button_router
from bot.callbacks import router as callback_router
from bot.admin_routes import router as admin_router 

# --- FSM Хранилище в БД ---
class DBSStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: str = None):
        await db.update_fsm_storage(int(key.user_id), state=state)

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
    logger.info("Bot starting...")
    
    bot = Bot(
        token=settings.BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = DBSStorage()
    dp = Dispatcher(storage=storage)

    await db.connect()
    
    # ✅ ИСПРАВЛЕНО: Импорт внутри функции
    from bot.user_loader import load_users_with_fix
    users_db_cache = await load_users_with_fix()
    
    static_data = await load_static_data()
    
    app.state.users_db = users_db_cache 
    
    dp["users_db"] = users_db_cache 
    dp["static_data"] = static_data
    dp["settings"] = settings
    
    # --- 4. Регистрируем роутеры (Aiogram) ---
    dp.include_router(commands_router)
    dp.include_router(button_router)
    dp.include_router(callback_router)
    
    dp.update.outer_middleware(AccessMiddleware())
    
    # Настраиваем задачи (теперь там корректное время 06:00 UTC)
    await setup_jobs_and_cache(bot, users_db_cache, static_data)
    
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
    
    logger.info(f"✅ Lifespan: Бот полностью запущен (v10.28 Stable)")
    
    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, t('admin_bot_started', lang="ru"))
    except Exception as e:
        logger.error(f"Не удалось отправить админу сообщение о старте: {e}")

    try:
        yield
    finally:
        logger.info("Bot stopping...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        
        save_users_sync(users_db_cache) # Аварийный JSON
        
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception: pass
        await bot.session.close()
        logger.info("👋 Бот выключен.")


# --- Инициализация FastAPI ---
app = FastAPI(lifespan=lifespan)

# ✅ Подключаем админку к FastAPI
app.include_router(admin_router) 

@app.get("/")
async def root():
    return {"status": "FotiniaBot v10.28 is alive"}

@app.post("/webhook/{token}")
async def webhook_handler(request: Request, token: str):
    if token != settings.BOT_TOKEN:
        return Response(content="Invalid token", status_code=403)
        
    bot: Bot = request.app.state.bot
    dp: Dispatcher = request.app.state.dispatcher
    
    dp["users_db"] = app.state.users_db

    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        logger.exception("Полный traceback ошибки webhook:")
        return Response(status_code=500)