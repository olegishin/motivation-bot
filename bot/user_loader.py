import json
import asyncio
import os
import aiofiles
from typing import Dict, Any, List
from pathlib import Path

from config import logger, settings
from database import db
from localization import t, load_localization 

# --- Константы ---
USERS_FILE = settings.USERS_FILE
STATIC_DATA_PATH = settings.STATIC_DATA_FILE

# =====================================================
# 1. Загрузка статических данных (контент)
# =====================================================

async def load_static_data() -> Dict[str, Any]:
    """
    Загружает статические данные из СТАРЫХ файлов (data_initial).
    """
    load_localization() # Обновляем тексты локализации
    
    data = {}
    
    # Ищем папку data_initial
    base_paths = ["/app/data_initial", "data_initial", "bot/data_initial"]
    folder = None
    
    for p in base_paths:
        if os.path.exists(p):
            folder = p
            break
    
    if not folder:
        logger.warning("⚠️ Папка data_initial не найдена. Используем заглушки.")
        return {
             "content": {
                "morning": [{"text": "Проснись и пой!"}],
                "ritm": [{"text": "Держи ритм!"}],
                "motivations": [{"text": "Мотивация дня!"}],
                "challenges": [{"text": "Челлендж: Сделай 10 приседаний."}]
            }
        }

    # Карта: Ключ в боте -> Имя твоего старого файла
    files_map = {
        "rules": "universe_laws.json",
        "motivations": "fotinia_motivations.json",
        "ritm": "fotinia_ritm.json",
        "challenges": "challenges.json",
        "morning_phrases": "fotinia_morning_phrases.json",
        "day_phrases": "fotinia_day_phrases.json",
        "evening_phrases": "fotinia_evening_phrases.json",
        "goals": "fotinia_goals.json"
    }

    logger.info(f"📂 Читаем старые файлы из: {folder}")

    for key, filename in files_map.items():
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            try:
                async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                    json_data = json.loads(content)
                    data[key] = json_data
                    logger.info(f"✅ Загружен {filename} ({len(json_data)} записей)")
            except Exception as e:
                logger.error(f"❌ Ошибка чтения {filename}: {e}")
                data[key] = []
        else:
            logger.warning(f"⚠️ Файл не найден: {filename}")
            data[key] = []

    return data


# =====================================================
# 2. Загрузка пользователей (с миграцией из старого JSON в SQLite)
# =====================================================

async def load_users_with_fix() -> Dict[str, Dict[str, Any]]:
    """
    Загружает пользователей. Если есть старый JSON-файл, мигрирует данные в SQLite.
    """
    
    # 1. Проверяем наличие старого JSON-бэкапа
    if not USERS_FILE.exists():
        logger.info("No old JSON user backup found. Relying solely on SQLite.")
        return {}

    try:
        # 2. Читаем старый JSON
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            old_users_data = json.load(f)
        
        logger.info(f"Found old JSON backup: {len(old_users_data)} users. Starting migration to SQLite...")

        # 3. Миграция в SQLite
        for user_id_str, old_data in old_users_data.items():
            try:
                user_id = int(user_id_str)
                
                # Добавляем пользователя (если нет)
                await db.add_user(user_id) 
                
                # Обновляем поля
                update_data = {
                    "username": old_data.get("username"),
                    "first_name": old_data.get("full_name"), 
                    "language": old_data.get("language"),
                    "timezone": old_data.get("timezone"),
                    "is_paid": old_data.get("is_paid", 0),
                    "demo_expiration": old_data.get("demo_expiration"),
                    "demo_cycles": old_data.get("demo_cycles", 0),
                    "last_active": old_data.get("last_active"),
                    "is_active": old_data.get("active", 1),
                    "joined_at": old_data.get("joined_at"),
                }
                
                # Чистим None значения
                update_data = {k: v for k, v in update_data.items() if v is not None}
                
                await db.update_user(user_id, **update_data)
            except Exception as mig_err:
                logger.error(f"Error migrating user {user_id_str}: {mig_err}")
        
        # 4. Переименовываем файл, чтобы не мигрировать снова
        try:
            USERS_FILE.rename(USERS_FILE.with_suffix('.old_migrated.json'))
            logger.info(f"✅ Migration complete. {len(old_users_data)} users processed.")
        except OSError:
             logger.warning("Could not rename old users file, but migration finished.")

    except Exception as e:
        logger.error(f"❌ Error during user migration: {e}")
        
    return {} 


# =====================================================
# 3. Синхронное сохранение (для совместимости)
# =====================================================

def save_users_sync(users_db_cache: Dict[str, Any]):
    """
    Синхронное сохранение (заглушка, так как теперь SQLite).
    """
    pass