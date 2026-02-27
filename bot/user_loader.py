# 06 - bot/user_loader.py
# ✅ Загрузка кэша пользователей из SQLite
# ✅ Загрузка статических данных (челленджи, правила, мотивации)
# ✅ Копирование файлов из data_initial/ в data/
# ✅ Резервное сохранение кэша в JSON (на случай аварии)

# 06 - bot/user_loader.py - ФИНАЛЬНАЯ ВЕРСИЯ (22.02.2026)
# Загрузка данных и кэширование
# ✅ ПРОВЕРЕНО: Загрузка из SQLite, копирование data_initial, бэкап в JSON

import asyncio
import json
import shutil
import tempfile
from typing import Dict, Any, Union, List
from pathlib import Path

from bot.database import db
from bot.config import logger, settings, FILE_MAPPING, DEFAULT_BROADCAST_KEYS
from bot.localization import DEFAULT_LANG

# --- Адаптер для загрузки пользователей ---
async def load_users_with_fix() -> Dict[str, Any]:
    """
    Загружает кэш пользователей из SQLite.
    """
    users = await db.get_all_users()
    logger.info(f"📖 Loaded {len(users)} users from SQLite (cache).")
    return users

# --- Адаптер для сохранения ---
async def save_users_sync(users_db: Dict[str, Any]) -> None:
    """
    Делает экстренный снимок кэша в JSON файл (backup).
    Основная работа идет в SQLite.
    """
    try:
        settings.DATA_DIR.mkdir(exist_ok=True, parents=True)
        await asyncio.to_thread(_save_json_snapshot, users_db)
        logger.info("💾 Emergency JSON snapshot saved.")
    except Exception as e:
        logger.error(f"❌ Emergency save failed: {e}")

def _save_json_snapshot(users_db: Dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=settings.DATA_DIR) as tmp:
        clean_users_db = {uid: u for uid, u in users_db.items()}
        json.dump(clean_users_db, tmp, ensure_ascii=False, indent=2)
    shutil.move(tmp.name, settings.USERS_FILE)

# --- Загрузка статики (Челленджи, Правила и т.д.) ---
async def load_static_data() -> dict:
    return await asyncio.to_thread(_load_static_data_sync)

def _load_static_data_sync() -> dict:
    DATA_DIR = settings.DATA_DIR
    
    # 1. Копируем файлы из data_initial (если есть новые)
    source_data_dir = settings.DATA_INITIAL_DIR
    if not source_data_dir.exists():
        logger.warning(f"⚠️ data_initial not found at {source_data_dir}")
    else:
        DATA_DIR.mkdir(exist_ok=True, parents=True)
        for item in source_data_dir.iterdir():
            if item.is_file() and item.suffix == '.json' and item.name != 'users.json':
                try:
                    shutil.copy2(item, DATA_DIR / item.name)
                except Exception as e:
                    logger.error(f"❌ Failed to copy {item.name}: {e}")

    static_data: Dict[str, Any] = {}
    
    def load_json(path: Path) -> Union[Dict, List, {}]:
        if not path.exists():
            logger.warning(f"⚠️ File not found: {path}")
            return {}
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Error in {path.name}: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error loading {path.name}: {e}")
            return {}

    # 2. Загружаем файлы по карте FILE_MAPPING
    for key, filename in FILE_MAPPING.items():
        file_path = DATA_DIR / filename
        raw_data = load_json(file_path)
        
        if not raw_data:
            static_data[key] = {}
            continue
        
        if key == "challenges":
            if isinstance(raw_data, list):
                logger.info(f"✅ Loaded {len(raw_data)} challenges (List format).")
            elif isinstance(raw_data, dict):
                count = sum(len(v) for v in raw_data.values())
                logger.info(f"✅ Loaded {count} challenges (Dict format).")
        
        if isinstance(raw_data, list):
            static_data[key] = {DEFAULT_LANG: raw_data}
        elif isinstance(raw_data, dict):
            static_data[key] = raw_data
        else:
            static_data[key] = {}

    # --- Финальная проверка обязательных ключей ---
    for key in DEFAULT_BROADCAST_KEYS:
        if key not in static_data or not static_data.get(key):
            logger.error(f"❌ CRITICAL: Broadcast key '{key}' missing or empty in static_data!")
            static_data[key] = {}

    return static_data