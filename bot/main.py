# 14 - bot/main.py — финальная рабочая версия (с защитой от дублей планировщика)
# 14 - bot/main.py — с фиксом аргументов user_data и lang для колбэков
# 14 - bot/main.py — финальная рабочая версия (с разделением роутеров и защитой от дублей)
# FastAPI + Aiogram Lifespan (УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс Shutdown + Единый кэш)
# FastAPI + Aiogram Lifespan (ПРОДАКШЕН-ФИНАЛЬНАЯ ВЕРСИЯ 12.02)
# Чистая сборка: WAL SQLite → бот → кэш → планировщик + безопасный webhook
# UPD: Добавлены метрики времени старта и Graceful Shutdown с таймаутом
# Точка входа: FastAPI + Aiogram Lifespan
# ✅ ИСПРАВЛЕНО (2026-01-16): 
#    - Правильный порядок роутеров (unknown в конце)
#    - Graceful shutdown
#    - Логирование на каждом шаге
# 14 - bot/main.py — ФИНАЛЬНАЯ УЛЬТИМАТИВНАЯ ВЕРСИЯ
# ✅ СОХРАНЕНО: DBSStorage, Graceful Shutdown, Порядок роутеров
# ✅ ИСПРАВЛЕНО (2026-01-26): 
#    - Импорт и shutdown планировщика с таймаутом
#    - Загрузка static_data и передача в setup_jobs_and_cache
#    - Проброс bot в dispatcher (dp["bot"])
#    - Расширенное логирование ошибок (exc_info=True)

import asyncio
from datetime import datetime, timezone
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
from bot.scheduler import setup_jobs_and_cache, scheduler # Импорт планировщика
from bot.utils import AccessMiddleware
from bot.content_handlers import notify_admins

# Роутеры
from bot.commands import router as commands_router
from bot.button_handlers import router as button_router, router_unknown as unknown_router
from bot.callbacks import router as callback_router
from bot.admin_routes import router as admin_router, webapp_router

# --- 🛡️ Хранилище FSM на базе SQLite ---
class DBSStorage(BaseStorage):
    """Хранилище состояний FSM в SQLite."""
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
    """Жизненный цикл приложения FastAPI + Aiogram."""
    start_init = datetime.now(timezone.utc)
    logger.info("=" * 50)
    logger.info("🚀 Bot lifespan starting...")
    logger.info("=" * 50)

    # 1️⃣ ИНИЦИАЛИЗАЦИЯ БД
    logger.info("📦 Step 1: Initializing database...")
    try:
        await db.init()
        logger.info("✅ Database initialized (WAL mode)")
    except Exception as e:
        logger.critical(f"❌ Database initialization failed: {e}", exc_info=True)
        raise

    # 2️⃣ ИНИЦИАЛИЗАЦИЯ БОТА И ДИСПЕТЧЕРА
    logger.info("🤖 Step 2: Initializing bot and dispatcher...")
    try:
        bot = Bot(
            token=settings.BOT_TOKEN, 
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher(storage=DBSStorage())
        dp["bot"] = bot # ✅ Фикс: проброс бота в диспетчер
        logger.info("✅ Bot and dispatcher initialized")
    except Exception as e:
        logger.critical(f"❌ Bot initialization failed: {e}", exc_info=True)
        raise

    # 3️⃣ ЗАГРУЗКА ДАННЫХ (КЭШ + СТАТИКА)
    logger.info("📊 Step 3: Loading cache and static data...")
    try:
        users_db_cache = await load_users_with_fix()
        static_data = await load_static_data() # ✅ Фикс: загрузка реальной статики
        logger.info(f"✅ Loaded {len(users_db_cache)} users, {len(static_data)} static keys")
    except Exception as e:
        logger.critical(f"❌ Data loading failed: {e}", exc_info=True)
        raise

    # 4️⃣ СОХРАНЕНИЕ В STATE
    app.state.bot = bot
    app.state.users_db = users_db_cache
    app.state.dispatcher = dp
    dp["users_db"] = users_db_cache
    dp["static_data"] = static_data
    dp["settings"] = settings

    # 5️⃣ MIDDLEWARE
    middleware = AccessMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)

    # 6️⃣ РОУТЕРЫ (СТРОГИЙ ПОРЯДОК)
    dp.include_router(commands_router)      # /start...
    dp.include_router(callback_router)      # inline
    dp.include_router(button_router)        # buttons
    dp.include_router(unknown_router)       # fallback (LAST)
    logger.info("✅ Routers registered in priority order")

    # 7️⃣ ПЛАНИРОВЩИК
    logger.info("⏰ Step 7: Setting up scheduler...")
    try:
        await setup_jobs_and_cache(bot, users_db_cache, static_data) # ✅ Фикс: передача статики
        logger.info("✅ Scheduler configured")
    except Exception as e:
        logger.error(f"⚠️ Scheduler setup error: {e}", exc_info=True)

    # 8️⃣ ВЕБХУК
    webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/{settings.BOT_TOKEN}"
    try:
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
        logger.info(f"✅ Webhook set: {webhook_url}")
    except Exception as e:
        logger.error(f"⚠️ Webhook setup failed: {e}", exc_info=True)

    # 9️⃣ УВЕДОМЛЕНИЕ
    try:
        await notify_admins(bot, "🚀 <b>Бот запущен. Система стабильна.</b>")
    except: pass

    init_duration = (datetime.now(timezone.utc) - start_init).total_seconds()
    logger.info(f"✨ Bot fully started in {init_duration:.2f} seconds")
    
    yield  # --- РАБОТА ---
    
    # --- SHUTDOWN ---
    logger.info("🛑 Stopping application...")
    
    if scheduler.running:
        logger.info("⏰ Stopping scheduler...")
        try:
            scheduler.shutdown(wait=True, timeout=10) # ✅ Фикс: таймаут 10 сек
            logger.info("✅ Scheduler stopped")
        except Exception as e:
            logger.error(f"⚠️ Scheduler shutdown error: {e}")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.session.close()
        logger.info("✅ Bot session closed")
    except Exception as e:
        logger.error(f"⚠️ Bot session close error: {e}")
    
    try:
        await save_users_sync(users_db_cache)
        logger.info("✅ User cache saved")
    except Exception as e:
        logger.error(f"⚠️ Cache save error: {e}")

# === FASTAPI APP ===
app = FastAPI(title="FotiniaBot", version="12.02", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(webapp_router)

@app.get("/")
async def root():
    return {"status": "FotiniaBot Active", "version": "12.02", "ts": datetime.now(timezone.utc).isoformat()}

@app.post("/webhook/{token}")
async def webhook_handler(request: Request, token: str):
    if token != settings.BOT_TOKEN:
        return Response("Forbidden", status_code=403)
    try:
        bot, dp = request.app.state.bot, request.app.state.dispatcher
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return Response("OK", status_code=200)