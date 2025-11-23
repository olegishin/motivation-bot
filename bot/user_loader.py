# 4 - S:/fotinia_bot/user_loader.py
# Загрузка данных и миграция

import asyncio
import json
import os 
import shutil
import tempfile
from typing import Dict, Any
from pathlib import Path

from bot.database import db
from config import logger, settings, FILE_MAPPING

# --- Адаптер для загрузки ---
async def load_users_with_fix() -> Dict[str, Any]:
    """
    Загружает всех пользователей из БД при старте.
    Запускает миграцию, если нужно (из users.json).
    Возвращает кэш пользователей.
    """
    # 1. Убеждаемся, что БД инициализирована
    await db.connect()
    
    # 2. Миграция из старого JSON, если БД пуста
    await db.migrate_from_json(settings.USERS_FILE)
    
    # 3. Загружаем всех пользователей из БД в кэш
    users = await db.get_all_users()
    logger.info(f"📖 Loaded {len(users)} users from SQLite (cache).")
    return users

# --- Адаптер для сохранения (JSON Emergency Dump) ---
def save_users_sync(users_db: Dict[str, Any]) -> None:
    """
    Синхронно сохраняет аварийный JSON-дамп (на случай сбоя БД).
    """
    try:
        # Убеждаемся, что папка существует
        settings.DATA_DIR.mkdir(exist_ok=True)
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=settings.DATA_DIR) as tmp:
            # Сохраняем только данные (data), без FSM
            clean_users_db = {uid: u for uid, u in users_db.items()}
            json.dump(clean_users_db, tmp, ensure_ascii=False, indent=2)
        # Атомарно перемещаем
        shutil.move(tmp.name, settings.USERS_FILE)
        logger.info("💾 Emergency JSON snapshot saved.")
    except Exception as e:
        logger.error(f"❌ Emergency save failed: {e}")

# --- Загрузка статического контента ---
async def load_static_data() -> dict:
    """Асинхронная обертка для загрузки статики."""
    return await asyncio.to_thread(_load_static_data_sync)

def _load_static_data_sync() -> dict:
    """
    Загружает весь статический контент (JSON-файлы) в кэш.
    """
    DATA_DIR = settings.DATA_DIR
    
    # 1. Копирование файлов из data_initial
    source_data_dir = settings.DATA_INITIAL_DIR
    if not source_data_dir.exists():
        logger.warning(f"⚠️ data_initial not found at {source_data_dir}, skipping sync.")
    else:
        DATA_DIR.mkdir(exist_ok=True)
        for filename in os.listdir(source_data_dir): 
            if filename.endswith('.json') and filename != 'users.json':
                shutil.copy2(source_data_dir / filename, DATA_DIR / filename)

    static_data = {}
    
    def load_json(path):
        if not path.exists(): return []
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load static JSON {path.name}: {e}")
            return []

    # 2. Загрузка основных файлов
    for key, filename in FILE_MAPPING.items():
        # Ожидаем, что эти файлы содержат словари {lang: [items]}
        raw_data = load_json(DATA_DIR / filename)
        if isinstance(raw_data, dict):
            static_data[key] = raw_data
        else:
            # Если это простой список, оборачиваем его в словарь по умолчанию
            static_data[key] = {settings.DEFAULT_LANG: raw_data}

    # 3. Загрузка челленджей (challenges*.json)
    challenges = {}
    for p in DATA_DIR.glob("challenges*.json"):
        data = load_json(p)
        if isinstance(data, dict):
            # Объединяем челленджи по языкам из разных файлов
            for l, items in data.items():
                challenges.setdefault(l, []).extend(items)
    static_data["challenges"] = challenges
    
    
    rules_count = len(static_data.get('rules', {}).get(settings.DEFAULT_LANG, []))
    motivations_count = len(static_data.get('motivations', {}).get(settings.DEFAULT_LANG, []))
    logger.info(f"📚 Static data loaded. {rules_count} rules, {motivations_count} motivations.")
    return static_data