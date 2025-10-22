import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv("token_id.env") 
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Используем URL, который вы прописали в fly.toml
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL", "https://fotinia-final.fly.dev") 

# Путь, который ожидает FastAPI: /telegram/ТОКЕН
WEBHOOK_PATH = f"/telegram/{BOT_TOKEN}"
FULL_WEBHOOK_URL = WEBHOOK_URL_BASE + WEBHOOK_PATH

async def set_new_webhook():
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден.")
        return

    bot = Bot(token=BOT_TOKEN)
    
    print("--- 1. Проверяем текущий Webhook ---")
    info = await bot.get_webhook_info()
    print(f"Текущий URL: {info.url or 'Нет'}")
    
    print(f"--- 2. Устанавливаем новый URL: {FULL_WEBHOOK_URL} ---")
    try:
        # Устанавливаем Webhook на правильный адрес /telegram/...
        success = await bot.set_webhook(url=FULL_WEBHOOK_URL)
        if success:
            print("✅ УСПЕХ! Webhook установлен. Бот должен начать отвечать.")
        else:
            print("❌ ОШИБКА: Telegram API вернул False. Проверьте правильность URL.")
    except Exception as e:
        print(f"❌ Критическая ошибка при установке Webhook: {e}")

if __name__ == "__main__":
    asyncio.run(set_new_webhook())