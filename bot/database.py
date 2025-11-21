import aiosqlite
import json
import logging
from config import settings

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = settings.DB_FILE
        self.conn = None

    async def init(self):
        """Инициализация соединения и создание таблиц."""
        # ЭТО СООБЩЕНИЕ ПОКАЖЕТ, ЧТО КОД ОБНОВИЛСЯ:
        logger.info("🚀 ЗАПУСК НОВОЙ ВЕРСИИ БАЗЫ ДАННЫХ...")
        
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info("📦 База данных (aiosqlite) успешно подключена.")

    async def _create_tables(self):
        """
        Создаем таблицы.
        В SQL используем только -- для комментариев.
        """
        
        # Основная таблица пользователей
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'ru',
                timezone TEXT DEFAULT 'Europe/Kiev',
                is_active INTEGER DEFAULT 1,
                last_active TEXT,
                
                -- Поля подписки и демо
                is_paid INTEGER DEFAULT 0,
                demo_expiration TEXT,
                demo_cycles INTEGER DEFAULT 0,
                
                -- Статистика и геймификация
                challenge_streak INTEGER DEFAULT 0,
                content_sent INTEGER DEFAULT 0,
                feedback_likes INTEGER DEFAULT 0,
                feedback_dislikes INTEGER DEFAULT 0,
                
                -- JSON списки (храним как TEXT)
                challenges TEXT DEFAULT '[]',
                reacted_messages TEXT DEFAULT '[]'
            );
        """)
        
        # Таблица для FSM (машина состояний)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fsm_storage (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            );
        """)
        await self.conn.commit()

    async def get_user(self, user_id: int):
        """Получить пользователя по ID как словарь."""
        async with self.conn.execute("SELECT * FROM user WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def update_user(self, user_id: int, **kwargs):
        """Обновляем или создаем пользователя."""
        if not kwargs:
            return
        
        # 1. Убедимся, что пользователь есть
        await self.conn.execute("INSERT OR IGNORE INTO user (user_id) VALUES (?)", (user_id,))
        
        # 2. Подготовка данных
        set_parts = []
        values = []
        
        for key, value in kwargs.items():
            set_parts.append(f"{key} = ?")
            # Если это список или словарь — превращаем в JSON-строку
            if isinstance(value, (list, dict)):
                values.append(json.dumps(value, ensure_ascii=False))
            elif isinstance(value, bool):
                 # Python bool True -> SQLite INTEGER 1
                values.append(1 if value else 0)
            else:
                values.append(value)
        
        values.append(user_id)
        
        sql = f"UPDATE user SET {', '.join(set_parts)} WHERE user_id = ?"
        
        try:
            await self.conn.execute(sql, values)
            await self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка SQL при обновлении user {user_id}: {e}")

    # --- Методы для FSM ---
    async def update_fsm_storage(self, user_id: int, state=None, data=None):
        await self.conn.execute("INSERT OR IGNORE INTO fsm_storage (user_id, data) VALUES (?, ?)", (user_id, "{}"))
        if state is not None:
             await self.conn.execute("UPDATE fsm_storage SET state = ? WHERE user_id = ?", (state, user_id))
        if data is not None:
             json_data = json.dumps(data, ensure_ascii=False)
             await self.conn.execute("UPDATE fsm_storage SET data = ? WHERE user_id = ?", (json_data, user_id))
        await self.conn.commit()

    async def get_fsm_storage(self, user_id: int):
        async with self.conn.execute("SELECT state, data FROM fsm_storage WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "state": row["state"],
                    "data": json.loads(row["data"]) if row["data"] else {}
                }
            return {"state": None, "data": {}}

    async def close(self):
        if self.conn:
            await self.conn.close()

db = Database()