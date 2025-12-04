# 06 - bot/user_loader.py
# Загрузка данных и миграция

import asyncio
import json
import shutil
import tempfile
import os
from typing import Dict, Any, Union, List
from pathlib import Path

# ✅ Импорты
from bot.database import db
from bot.config import logger, settings, FILE_MAPPING, DEFAULT_BROADCAST_KEYS
from bot.localization import DEFAULT_LANG

# --- Адаптер для загрузки пользователей ---
async def load_users_with_fix() -> Dict[str, Any]:
    await db.connect()
    await db.migrate_from_json(settings.USERS_FILE)
    users = await db.get_all_users()
    logger.info(f"📖 Loaded {len(users)} users from SQLite (cache).")
    return users

# --- Адаптер для сохранения ---
def save_users_sync(users_db: Dict[str, Any]) -> None:
    try:
        settings.DATA_DIR.mkdir(exist_ok=True, parents=True)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=settings.DATA_DIR) as tmp:
            clean_users_db = {uid: u for uid, u in users_db.items()}
            json.dump(clean_users_db, tmp, ensure_ascii=False, indent=2)
        shutil.move(tmp.name, settings.USERS_FILE)
        logger.info("💾 Emergency JSON snapshot saved.")
    except Exception as e:
        logger.error(f"❌ Emergency save failed: {e}")

# --- Загрузка статики ---
async def load_static_data() -> dict:
    return await asyncio.to_thread(_load_static_data_sync)

def _load_static_data_sync() -> dict:
    DATA_DIR = settings.DATA_DIR
    
    # 1. Копируем файлы из data_initial (если есть)
    source_data_dir = settings.DATA_INITIAL_DIR
    if not source_data_dir.exists():
        logger.warning(f"⚠️ data_initial not found at {source_data_dir}")
    else:
        DATA_DIR.mkdir(exist_ok=True, parents=True)
        for item in source_data_dir.iterdir(): 
            if item.is_file() and item.suffix == '.json' and item.name != 'users.json':
                shutil.copy2(item, DATA_DIR / item.name)

    static_data: Dict[str, Any] = {}
    
    def load_json(path: Path) -> Union[Dict, List, None]:
        if not path.exists(): 
            logger.warning(f"⚠️ File not found: {path}")
            return None
        try:
            # ✅ ИСПРАВЛЕНО: utf-8-sig читает файлы и с BOM (Windows Notepad) и без него
            with open(path, 'r', encoding='utf-8-sig') as f: 
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Error in {path.name}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error loading {path.name}: {e}")
            return None

    # 2. Загружаем файлы по карте FILE_MAPPING
    # В этой версии мы ожидаем, что каждый ключ рассылки сопоставлен с отдельным файлом.
    for key, filename in FILE_MAPPING.items():
        file_path = DATA_DIR / filename
        raw_data = load_json(file_path)
        
        if raw_data is None: 
            static_data[key] = {}
            continue
            
        # УБРАН НЕНУЖНЫЙ БЛОК ДЛЯ 'phrases', так как в конфигурации все файлы разделены.

        # Специальный DEBUG для челленджей
        if key == "challenges":
             if isinstance(raw_data, list):
                 logger.info(f"✅ Loaded {len(raw_data)} challenges (List format).")
             elif isinstance(raw_data, dict):
                 count = sum(len(v) for v in raw_data.values())
                 logger.info(f"✅ Loaded {count} challenges (Dict format).")
        
        # Авто-исправление структуры (Список -> Словарь)
        if isinstance(raw_data, list):
             static_data[key] = {DEFAULT_LANG: raw_data}
        elif isinstance(raw_data, dict):
             static_data[key] = raw_data
        else:
             static_data[key] = {}

    # --- Финальная проверка, что ключи рассылки присутствуют ---
    for key in DEFAULT_BROADCAST_KEYS:
        if key not in static_data or not static_data.get(key):
             logger.error(f"❌ CRITICAL: Broadcast key '{key}' missing or empty in static_data! Check file: {FILE_MAPPING.get(key, 'N/A')}")
             static_data[key] = {} 

    return static_data