# 02 - bot/database.py
# Менеджер базы данных SQLite (Final Version with WAL + Stats Fixes)
# Менеджер базы данных SQLite (Robust Version: Fixes Double JSON Encoding)
# Менеджер базы данных SQLite (FINAL FIX: Лечит FSM и Челленджи)
# Менеджер базы данных SQLite (FINAL FIX: Bulletproof JSON)
# Менеджер базы данных SQLite (ULTIMATE FIX: Recursive JSON Unwrapping)
# Менеджер базы данных SQLite (ULTIMATE FIX: FSM Logic Separation)
# Асинхронный менеджер базы данных SQLite (WAL + миграции + безопасный JSON)
# ИСПРАВЛЕНО: Аргументы add_user синхронизированы с Middleware
# Менеджер базы данных SQLite (Final Version with WAL + Stats Fixes)
# (ФИНАЛЬНАЯ ВЕРСИЯ: Исправлено обновление языка при перезапуске)
# Менеджер базы данных SQLite
# ИСПРАВЛЕНО (2026-01-13): Двойное JSON кодирование + Новые индексы + Улучшенное логирование
# Менеджер базы данных SQLite (ULTIMATE VERSION)
# ИСПРАВЛЕНО (2026-01-16): Белый список полей + защита от неизвестных параметров

import aiosqlite
import json
import logging
from typing import Dict, Any, Optional

from bot.config import settings

logger = logging.getLogger(__name__)

# Константа безопасности для рекурсии JSON
MAX_JSON_DEPTH = 5


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        """Инициализация базы с атомарными миграциями."""
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
            
            # Создаем индекс для быстрого поиска пользователя
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)")
            
            # 🆕 Индекс для поиска истекающих демо-периодов
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_demo_expiration 
                ON users(demo_expiration, is_paid) 
                WHERE is_paid = 0 AND demo_expiration IS NOT NULL
            """)
            
            # 🆕 Индекс для планировщика (активные юзеры + часовой пояс)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_active_timezone 
                ON users(active, timezone) 
                WHERE active = 1
            """)

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
                ("challenges_today", "INTEGER DEFAULT 0")
            ]
            
            for col, definition in cols:
                try:
                    await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                except Exception:
                    pass  # Колонка уже существует
            
            await conn.commit()
            logger.info("Database initialized and migrated successfully (async).")

    def _safe_load(self, val: Any, depth: int = 0) -> Any:
        """Безопасная десериализация JSON с защитой от двойного кодирования и лимитом рекурсии."""
        if depth > MAX_JSON_DEPTH:
            logger.warning(f"JSON recursion depth exceeded at level {depth}")
            return {}
        if val is None or val == "":
            return {}
        if isinstance(val, (dict, list)):
            return val
        try:
            data = json.loads(val)
            # Рекурсивная проверка на случай, если JSON сохранен как строка внутри строки
            if isinstance(data, str):
                return self._safe_load(data, depth + 1)
            return data
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse JSON value: {str(val)[:100]}... Error: {e}")
            return {}

    async def add_user(self, user_id: int, username: Optional[str], name: str, language: str = "ru", **kwargs):
        """
        Добавляет пользователя или обновляет базовые данные при конфликте.
        
        ✅ ИСПРАВЛЕНО (2026-01-16):
        - Не передаём неизвестные параметры в kwargs
        - Все фильтрации происходят в update_user()
        """
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''
                INSERT INTO users (user_id, username, name, language)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name=excluded.name,
                    username=excluded.username,
                    language=excluded.language
            ''', (user_id, username, name, language))
            await conn.commit()
        
        # Все дополнительные поля передаём в update_user — там уже будет полная фильтрация
        if kwargs:
            await self.update_user(user_id, **kwargs)
        
        return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает и распаковывает данные пользователя."""
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
        """
        Обновление данных пользователя с абсолютной защитой от неизвестных колонок.
        
        ✅ ИСПРАВЛЕНО (2026-01-16):
        - Белый список ВСЕХ допустимых полей
        - Фильтрация неизвестных параметров (защита от Ошибки #1)
        - Логирование попыток обновления неизвестных полей
        - Безопасное преобразование JSON
        """
        
        if not kwargs:
            return
        
        # 🛡️ БЕЛЫЙ СПИСОК: Только реальные колонки из schema
        ALLOWED_FIELDS = {
            "username", "name", "language", "timezone", "is_paid", "status", 
            "demo_expiration", "active", "last_challenge_date", "challenge_accepted",
            "challenges", "challenge_streak", "fsm_state", "fsm_data",
            "last_rules_date", "rules_shown_count", "rules_indices_today",
            "sent_expiry_warning", "stats_likes", "stats_dislikes", "demo_count",
            "challenges_today", "data"
        }

        # JSON-поля, которые должны храниться как строки
        JSON_FIELDS = {"challenges", "rules_indices_today", "data", "fsm_data"}
        
        # 🛡️ ФИЛЬТРУЕМ: оставляем только разрешённые поля
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
        
        # 📝 ЛОГИРУЕМ, если пытались обновить неизвестные поля
        if len(kwargs) != len(safe_kwargs):
            unknown = set(kwargs.keys()) - ALLOWED_FIELDS
            logger.warning(f"update_user: User {user_id} attempted to set unknown fields: {unknown}. Ignored.")
        
        if not safe_kwargs:
            logger.debug(f"update_user: No valid fields to update for user {user_id}")
            return

        async with aiosqlite.connect(self.db_path) as conn:
            params = []
            sql_parts = []
            
            for k, v in safe_kwargs.items():
                sql_parts.append(f"{k} = ?")
                
                if k in JSON_FIELDS:
                    # Обработка JSON полей
                    if isinstance(v, str):
                        try:
                            json.loads(v)
                            # Валидный JSON-строка → сохраняем как есть
                            params.append(v)
                        except (json.JSONDecodeError, TypeError):
                            # Битая строка → исправляем на дефолт
                            default_value = "[]" if k in {"challenges", "rules_indices_today"} else "{}"
                            logger.warning(f"Invalid JSON string for field '{k}', replacing with {default_value}")
                            params.append(default_value)
                    elif isinstance(v, (dict, list)):
                        # Словарь/список → сериализуем в JSON
                        params.append(json.dumps(v, ensure_ascii=False))
                    else:
                        # Неожиданный тип → заменяем на безопасное значение
                        default_value = "[]" if k in {"challenges", "rules_indices_today"} else "{}"
                        logger.warning(f"Unexpected type {type(v)} for JSON field '{k}', replacing with {default_value}")
                        params.append(default_value)
                else:
                    # Обычные поля (не JSON)
                    params.append(v)
            
            params.append(user_id)
            
            try:
                await conn.execute(f"UPDATE users SET {', '.join(sql_parts)} WHERE user_id = ?", params)
                await conn.commit()
            except Exception as e:
                logger.exception(f"Failed to update user {user_id}: {e}")
                raise

    async def get_all_users(self) -> Dict[str, Any]:
        """Возвращает всех пользователей (словарь с ключами по user_id)."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM users') as cursor:
                rows = await cursor.fetchall()
        
        result: Dict[str, Any] = {}
        for r in rows:
            d = dict(r)
            for k in ["challenges", "rules_indices_today", "data", "fsm_data"]:
                if k in d:
                    d[k] = self._safe_load(d.get(k))
            result[str(r["user_id"])] = d
        return result

    async def update_fsm_storage(self, user_id: int, state: Optional[str] = None, data: Optional[dict] = None):
        """Интеграция с FSM через update_user."""
        upd = {}
        if state is not None:
            upd["fsm_state"] = state
        if data is not None:
            upd["fsm_data"] = data
        if upd:
            await self.update_user(user_id, **upd)

    async def get_fsm_storage(self, user_id: int) -> Dict[str, Any]:
        """Получает текущее состояние и данные FSM."""
        u = await self.get_user(user_id)
        if u:
            return {"state": u.get("fsm_state"), "data": u.get("fsm_data") or {}}
        return {"state": None, "data": {}}

    async def execute(self, sql: str, params: tuple = ()):
        """Выполняет произвольный SQL запрос."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def delete_user(self, user_id: int):
        """Удаляет пользователя."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            await conn.commit()

    async def commit(self):
        """Заглушка для совместимости."""
        pass

# Инициализация глобального экземпляра БД
db = Database(str(settings.DB_FILE))