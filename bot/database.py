# 3 - S:/fotinia_bot/bot/database.py
# Менеджер базы данных SQLite

import json
import aiosqlite
from typing import Dict, Any, List, Optional
from pathlib import Path
from config import settings, logger

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def _get_db(self):
        """Возвращает подключение к БД с row_factory."""
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        return db

    async def connect(self):
        """Создает подключение и таблицы."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fsm_state TEXT,
                    fsm_data TEXT
                )
            """)
            try:
                # Попытка добавить колонки, если их еще нет
                await db.execute("ALTER TABLE users ADD COLUMN fsm_state TEXT")
                await db.execute("ALTER TABLE users ADD COLUMN fsm_data TEXT")
                logger.info("Database migration: Added FSM columns.")
            except aiosqlite.OperationalError:
                pass # Колонки уже существуют
            
            await db.commit()
            logger.info("💾 Database connected and tables checked.")
            
    # Alias для connect
    async def init(self):
        await self.connect()

    async def close(self):
        """Заглушка, чтобы соответствовать интерфейсу Aiogram Storage."""
        pass 

    async def migrate_from_json(self, json_path: Path):
        if not json_path.exists():
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                count = (await cursor.fetchone())[0]
                if count > 0:
                    logger.info("💾 Database is not empty. Skipping migration.")
                    return

            logger.info(f"🔄 Starting migration from {json_path}...")
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                users_to_insert = []
                for user_id_str, user_data in data.items():
                    try:
                        uid = int(user_id_str)
                        users_to_insert.append((uid, json.dumps(user_data, ensure_ascii=False)))
                    except ValueError:
                        continue
                
                if users_to_insert:
                    await db.executemany(
                        "INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)",
                        users_to_insert
                    )
                    await db.commit()
                    logger.info(f"✅ Migrated {len(users_to_insert)} users from JSON to SQLite.")
                    
            except Exception as e:
                logger.error(f"❌ Migration failed: {e}")

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные пользователя (data) как словарь."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT data FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row["data"])
        return None

    async def get_fsm_storage(self, user_id: int) -> Dict[str, Any]:
        """Получает FSM state и data."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT fsm_state, fsm_data FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row["fsm_state"]:
                    return {
                        "state": row["fsm_state"],
                        "data": json.loads(row["fsm_data"] or "{}")
                    }
        return {"state": None, "data": {}}

    async def update_fsm_storage(self, user_id: int, state: Optional[str] = None, data: Optional[Dict] = None):
        """Обновляет FSM state и data."""
        async with aiosqlite.connect(self.db_path) as db:
            # Если state None, то это очистка FSM.
            await db.execute(
                "UPDATE users SET fsm_state = ?, fsm_data = ? WHERE user_id = ?",
                (state, json.dumps(data or {}), user_id)
            )
            await db.commit()

    async def update_user(self, user_id: int, **kwargs):
        """Точечно обновляет поля в user_data (JSON)."""
        if not kwargs:
            return

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT data FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    # Если юзера нет, добавляем заглушку, но в этом случае user_data не обновится
                    logger.warning(f"update_user: User {user_id} not found to update.")
                    return
                try:
                    user_data = json.loads(row["data"])
                except Exception:
                    user_data = {}

            user_data.update(kwargs)
            
            json_data = json.dumps(user_data, ensure_ascii=False)
            await db.execute(
                "UPDATE users SET data = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (json_data, user_id)
            )
            await db.commit()

    async def add_user(self, user_id: int, username: Optional[str], full_name: str, language: str, timezone: str):
        """Добавляет нового пользователя (вызывается из Middleware)."""
        new_user_data = {
            "id": user_id,
            "username": username,
            "name": full_name,
            "language": language,
            "timezone": timezone,
            "active": True,
            "demo_count": 0,
            "demo_expiration": None,
            "challenge_streak": 0,
            "challenges": [],
            "last_challenge_date": None,
            "last_rules_date": None,
            "rules_shown_count": 0,
            "rules_indices_today": [],
            "sent_expiry_warning": False,
            "is_paid": False,
            "stats_likes": 0,
            "stats_dislikes": 0,
            "status": "new"
        }
        json_data = json.dumps(new_user_data, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)",
                (user_id, json_data)
            )
            await db.commit()

    async def get_all_users(self) -> Dict[str, Any]:
        """Загружает ВСЕХ пользователей в память (для админки и кэша рассылок)."""
        users_dict = {}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT user_id, data FROM users") as cursor:
                async for row in cursor:
                    try:
                        user_id = str(row["user_id"])
                        user_data = json.loads(row["data"])
                        users_dict[user_id] = user_data
                    except Exception as e:
                        logger.error(f"Error loading user {row['user_id']}: {e}")
                        continue
        return users_dict

db = Database(settings.DB_FILE)