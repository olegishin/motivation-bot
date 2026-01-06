# bot/database.py
import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        
        # Создаем таблицу, если её нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT,
                language TEXT DEFAULT 'ru',
                data TEXT NOT NULL DEFAULT '{}'
            )
        ''')

        # Список всех необходимых колонок для миграции
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
            ("demo_count", "INTEGER DEFAULT 1")
        ]

        # Автоматическое добавление отсутствующих колонок
        for col, definition in cols:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass  # Колонка уже существует

        conn.commit()
        conn.close()
        logger.info("Database initialized and migrated successfully.")

    def _safe_load(self, val: Any) -> Any:
        if isinstance(val, (dict, list)): 
            return val
        try: 
            return json.loads(val) if val else {}
        except: 
            return {}

    async def add_user(self, user_id: int, username: Optional[str], full_name: str, language: str = "ru"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, name, language) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username
        ''', (user_id, username, full_name, language))
        conn.commit()
        conn.close()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            # Распаковываем JSON-поля
            for k in ["challenges", "rules_indices_today", "data", "fsm_data"]:
                d[k] = self._safe_load(d.get(k))
            return d
        return None

    async def update_user(self, user_id: int, **kwargs):
        conn = sqlite3.connect(self.db_path)
        params = []
        sql_parts = []
        for k, v in kwargs.items():
            sql_parts.append(f"{k} = ?")
            if isinstance(v, (dict, list)):
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                params.append(v)
        
        params.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(sql_parts)} WHERE user_id = ?", params)
        conn.commit()
        conn.close()

    async def get_all_users(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT * FROM users').fetchall()
        conn.close()
        
        result = {}
        for r in rows:
            d = dict(r)
            # Распаковываем JSON для корректной работы планировщика
            for k in ["challenges", "rules_indices_today", "data", "fsm_data"]:
                d[k] = self._safe_load(d.get(k))
            result[str(r["user_id"])] = d
        return result

    async def update_fsm_storage(self, user_id: int, state: str = None, data: dict = None):
        upd = {}
        if state is not None: 
            upd["fsm_state"] = state
        if data is not None: 
            upd["fsm_data"] = data
        if upd: 
            await self.update_user(user_id, **upd)

    async def get_fsm_storage(self, user_id: int) -> Dict[str, Any]:
        u = await self.get_user(user_id)
        if u:
            return {"state": u.get("fsm_state"), "data": u.get("fsm_data") or {}}
        return {"state": None, "data": {}}

    async def delete_user(self, user_id: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

from bot.config import settings
db = Database(str(settings.DB_FILE))