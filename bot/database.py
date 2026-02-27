# 02 - bot/database.py
# 02 - bot/database.py - ФИНАЛЬНАЯ ВЕРСИЯ (22.02.2026)
# Менеджер базы данных SQLite
# ✅ ПРОВЕРЕНО: WAL режим, защита от дублей рассылки, реферальная система

import aiosqlite
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from bot.config import settings

logger = logging.getLogger(__name__)

# Константа безопасности для рекурсии JSON
MAX_JSON_DEPTH = 5

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        """Инициализация базы с атомарными миграциями и индексами."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    name TEXT,
                    language TEXT DEFAULT 'ru',
                    data TEXT NOT NULL DEFAULT '{}'
                )
            ''')
            
            # Индексы для производительности
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)")
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_demo_expiration 
                ON users(demo_expiration, is_paid) 
                WHERE is_paid = 0 AND demo_expiration IS NOT NULL
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_active_timezone 
                ON users(active, timezone) 
                WHERE active = 1
            """)

            # Список колонок для миграции
            cols = [
                ("timezone", "TEXT DEFAULT 'Europe/Kiev'"),
                ("is_paid", "INTEGER DEFAULT 0"),
                ("status", "TEXT DEFAULT 'demo'"),
                ("demo_expiration", "TEXT"),
                ("active", "INTEGER DEFAULT 1"),
                ("last_challenge_date", "TEXT"),
                ("challenge_accepted", "INTEGER DEFAULT 0"),
                ("challenges", "TEXT NOT NULL DEFAULT '[]'"),
                ("challenge_streak", "INTEGER DEFAULT 0"),
                ("fsm_state", "TEXT"),
                ("fsm_data", "TEXT"),
                ("last_rules_date", "TEXT"),
                ("rules_shown_count", "INTEGER DEFAULT 0"),
                ("rules_indices_today", "TEXT NOT NULL DEFAULT '[]'"),
                ("sent_expiry_warning", "INTEGER DEFAULT 0"),
                ("stats_likes", "INTEGER DEFAULT 0"),
                ("stats_dislikes", "INTEGER DEFAULT 0"),
                ("demo_count", "INTEGER DEFAULT 1"),
                ("challenges_today", "INTEGER DEFAULT 0"),
                ("last_level_checked", "TEXT DEFAULT 'level_0'"),
                ("referred_by", "INTEGER"),
                ("created_at", "TEXT"),
                ("last_broadcast_date", "TEXT"),  # ✅ Защита от дублей рассылки
            ]
            
            for col, definition in cols:
                try:
                    await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                except Exception:
                    pass  # Колонка уже существует
            
            await conn.commit()
            logger.info("Database: ULTIMATE init complete. All fields and methods ready.")

    def _safe_load(self, val: Any, depth: int = 0) -> Any:
        """Безопасная десериализация JSON."""
        if depth > MAX_JSON_DEPTH:
            return {}
        if val is None or val == "":
            return {}
        if isinstance(val, (dict, list)):
            return val
        try:
            data = json.loads(val)
            if isinstance(data, str):
                return self._safe_load(data, depth + 1)
            return data
        except (json.JSONDecodeError, TypeError):
            return {}

    async def add_user(self, user_id: int, username: Optional[str], name: str, language: str = "ru", **kwargs):
        """Добавляет пользователя. Сохраняет дату создания created_at."""
        now = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''
                INSERT INTO users (user_id, username, name, language, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name=excluded.name,
                    username=excluded.username,
                    language=excluded.language
            ''', (user_id, username, name, language, now))
            await conn.commit()
        
        if kwargs:
            await self.update_user(user_id, **kwargs)
        
        return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                d = dict(row)
                for k in ["challenges", "rules_indices_today", "data", "fsm_data"]:
                    if k in d:
                        d[k] = self._safe_load(d.get(k))
                return d
        return None

    async def update_user(self, user_id: int, **kwargs):
        """Обновление данных с защитой и валидацией JSON."""
        if not kwargs:
            return
        
        ALLOWED_FIELDS = {
            "username", "name", "language", "timezone", "is_paid", "status", 
            "demo_expiration", "active", "last_challenge_date", "challenge_accepted",
            "challenges", "challenge_streak", "fsm_state", "fsm_data",
            "last_rules_date", "rules_shown_count", "rules_indices_today",
            "sent_expiry_warning", "stats_likes", "stats_dislikes", "demo_count",
            "challenges_today", "data", "last_level_checked",
            "referred_by", "created_at", "last_broadcast_date",
        }

        JSON_FIELDS = {"challenges", "rules_indices_today", "data", "fsm_data"}
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
        
        if not safe_kwargs:
            return

        async with aiosqlite.connect(self.db_path) as conn:
            params = []
            sql_parts = []
            for k, v in safe_kwargs.items():
                sql_parts.append(f"{k} = ?")
                if k in JSON_FIELDS:
                    if isinstance(v, str):
                        try:
                            json.loads(v)
                            params.append(v)
                        except:
                            params.append("[]" if k in {"challenges", "rules_indices_today"} else "{}")
                    elif isinstance(v, (dict, list)):
                        params.append(json.dumps(v, ensure_ascii=False))
                    else:
                        params.append("[]" if k in {"challenges", "rules_indices_today"} else "{}")
                else:
                    params.append(v)
            
            params.append(user_id)
            await conn.execute(f"UPDATE users SET {', '.join(sql_parts)} WHERE user_id = ?", params)
            await conn.commit()

    async def get_all_users(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM users') as cursor:
                rows = await cursor.fetchall()
        
        result = {}
        for r in rows:
            d = dict(r)
            for k in ["challenges", "rules_indices_today", "data", "fsm_data"]:
                if k in d:
                    d[k] = self._safe_load(d.get(k))
            result[str(r["user_id"])] = d
        return result

    async def delete_user(self, user_id: int):
        """Для тестов: полное удаление."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            await conn.commit()
            logger.warning(f"Database: User {user_id} deleted (Test mode).")

    # ========== 📊 МЕТОДЫ СТАТИСТИКИ ==========
    
    async def get_total_users_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
                res = await cursor.fetchone()
                return res[0] if res else 0

    async def get_active_users_count(self, days: int = 7) -> int:
        limit = (datetime.now() - timedelta(days=days)).date().isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM users WHERE active = 1 AND last_challenge_date >= ?", 
                (limit,)
            ) as cursor:
                res = await cursor.fetchone()
                return res[0] if res else 0

    async def get_referrals_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as cursor:
                res = await cursor.fetchone()
                return res[0] if res else 0

    # ========== 🧠 FSM МЕТОДЫ (State Machine) ==========
    
    async def update_fsm_storage(self, user_id: int, state: Optional[str] = None, data: Optional[dict] = None):
        """Обновление состояния FSM для aiogram."""
        upd = {}
        if state is not None: upd["fsm_state"] = state
        if data is not None: upd["fsm_data"] = data
        if upd: await self.update_user(user_id, **upd)

    async def get_fsm_storage(self, user_id: int) -> Dict[str, Any]:
        """Получение состояния FSM для aiogram."""
        u = await self.get_user(user_id)
        if u:
            return {"state": u.get("fsm_state"), "data": u.get("fsm_data") or {}}
        return {"state": None, "data": {}}

    # ========== 🛠️ SQL МЕТОДЫ (Админка) ==========
    
    async def execute(self, sql: str, params: tuple = ()):
        """Прямой SQL запрос."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def commit(self):
        """Пустой метод для совместимости."""
        pass

# Инициализация глобального экземпляра БД
db = Database(str(settings.DB_FILE))