import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# Загружаем ваш токен из файла
load_dotenv("token_id.env") 
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def delete_and_check_webhook():
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден. Проверьте ваш файл token_id.env.")
        return
        
    bot = Bot(token=BOT_TOKEN)
    
    print("--- 1. Попытка удалить старый Webhook ---")
    is_deleted = await bot.delete_webhook()
    
    print("--- 2. Проверка статуса ---")
    webhook_info = await bot.get_webhook_info()
    
    if not webhook_info.url:
        print("✅ УСПЕХ! Webhook удален, адрес чист.")
    else:
        print(f"❌ ОШИБКА: Webhook все еще активен на URL: {webhook_info.url}")

if __name__ == "__main__":
    asyncio.run(delete_and_check_webhook())
    
