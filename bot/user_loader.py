# 14 - bot/user_loader.py
# Загрузка данных и миграция

import asyncio
import json
import shutil
import tempfile
from typing import Dict, Any
from pathlib import Path

# ✅ Импорты с префиксом bot.
from bot.database import db
from bot.config import logger, settings, FILE_MAPPING

# --- Адаптер для загрузки ---
async def load_users_with_fix() -> Dict[str, Any]:
    """Загружает всех пользователей из БД при старте."""
    await db.connect()
    await db.migrate_from_json(settings.USERS_FILE)
    users = await db.get_all_users()
    logger.info(f"📖 Loaded {len(users)} users from SQLite (cache).")
    return users

# --- Адаптер для сохранения ---
def save_users_sync(users_db: Dict[str, Any]) -> None:
    """Синхронно сохраняет аварийный JSON-дамп."""
    try:
        settings.DATA_DIR.mkdir(exist_ok=True, parents=True)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=settings.DATA_DIR) as tmp:
            clean_users_db = {uid: u for uid, u in users_db.items()}
            json.dump(clean_users_db, tmp, ensure_ascii=False, indent=2)
        shutil.move(tmp.name, settings.USERS_FILE)
        logger.info("💾 Emergency JSON snapshot saved.")
    except Exception as e:
        logger.error(f"❌ Emergency save failed: {e}")

# --- Загрузка статического контента ---
async def load_static_data() -> dict:
    return await asyncio.to_thread(_load_static_data_sync)

def _load_static_data_sync() -> dict:
    """Загружает весь статический контент (JSON-файлы) в кэш."""
    DATA_DIR = settings.DATA_DIR
    
    # 1. Копирование файлов из data_initial
    source_data_dir = settings.DATA_INITIAL_DIR
    if not source_data_dir.exists():
        logger.warning(f"⚠️ data_initial not found at {source_data_dir}, skipping sync.")
    else:
        DATA_DIR.mkdir(exist_ok=True, parents=True)
        # Копируем все json файлы
        for item in source_data_dir.iterdir(): 
            if item.is_file() and item.suffix == '.json' and item.name != 'users.json':
                shutil.copy2(item, DATA_DIR / item.name)

    static_data = {}
    
    def load_json(path):
        if not path.exists(): return []
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load static JSON {path.name}: {e}")
            return []

    # 2. Загрузка всех файлов из FILE_MAPPING (ВКЛЮЧАЯ CHALLENGES)
    for key, filename in FILE_MAPPING.items():
        raw_data = load_json(DATA_DIR / filename)
        
        # ✅ АВТО-ИСПРАВЛЕНИЕ СТРУКТУРЫ
        # Если файл содержит список ["текст", "текст"], а мы ждем словарь {"ru": [...]},
        # то привязываем этот список к дефолтному языку.
        if isinstance(raw_data, list):
             static_data[key] = {settings.DEFAULT_LANG: raw_data}
             # logger.info(f"Fixed list structure for {key} -> assigned to {settings.DEFAULT_LANG}")
        elif isinstance(raw_data, dict):
            static_data[key] = raw_data
        else:
            static_data[key] = {}

    # Логируем количество
    rules_count = len(static_data.get('rules', {}).get(settings.DEFAULT_LANG, []))
    challenges_count = len(static_data.get('challenges', {}).get(settings.DEFAULT_LANG, []))
    
    logger.info(f"📚 Static data loaded. Rules: {rules_count}, Challenges: {challenges_count}")
    return static_data