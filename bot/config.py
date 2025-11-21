# bot/config.py
import os
import logging
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Set, Optional, List, TypeVar
from pydantic_settings import BaseSettings, SettingsConfigDict

Lang = TypeVar("Lang", bound=str) # Для типизации языка

# --- Настройка логирования ---

def setup_logging():
    logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
    _logger = logging.getLogger("bot")
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    if not _logger.hasHandlers():
        _logger.addHandler(_handler)
    _logger.propagate = False
    _logger.setLevel(logging.DEBUG)
    return _logger

logger = setup_logging()

# --- КОНФИГУРАЦИЯ .ENV ---

class Settings(BaseSettings):
    # Основные настройки (должны быть в .env)
    BOT_TOKEN: str = "YOUR_BOT_TOKEN_HERE" # Замените
    ADMIN_CHAT_ID: int = 123456789 # Замените
    WEBHOOK_URL: str = "https://your-app-name.fly.dev" # Замените
    
    # Константы по умолчанию
    DEFAULT_LANG: str = "ru"
    DEFAULT_TZ_KEY: str = "Europe/Kiev"
    
    # --- Админка ---
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "secret"
    
    # Списки ID (для тестеров и симуляторов)
    TESTER_USER_IDS: List[int] = [290711961, 6104624108]
    SIMULATOR_USER_IDS: List[int] = [6112492697]

    # Настройки логики
    REGULAR_DEMO_DAYS: int = 5
    REGULAR_COOLDOWN_DAYS: int = 14 # 14 дней кулдауна
    TESTER_DEMO_DAYS: int = 1
    TESTER_COOLDOWN_DAYS: int = 1
    RULES_PER_DAY_LIMIT: int = 3
    MAX_DEMO_CYCLES: int = 2 # Максимум 2 демо-цикла
    
    BOT_USERNAME: str = "FotiniaBot"

    # --- 📍 ПУТИ К ФАЙЛАМ ---
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data"))
    
    @property
    def USERS_FILE(self) -> Path:
        """Путь к файлу users_backup.json (для миграции)."""
        return self.DATA_DIR / "users_backup.json"

    @property
    def DB_FILE(self) -> Path:
        """Путь к файлу базы данных SQLite."""
        # ✅ ИСПРАВЛЕНО: используем fotinia_bot.db
        return self.DATA_DIR / "fotinia_bot.db"

    @property
    def DATA_INITIAL_DIR(self) -> Path:
        """Путь к исходным данным."""
        return Path(__file__).parent.parent / "static_data"

    @property
    def STATIC_DATA_FILE(self) -> Path:
        """Путь к файлу контента."""
        return self.DATA_INITIAL_DIR / "content_v1.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore'
    )

try:
    settings = Settings()
    # Создаем директорию для данных, если ее нет
    settings.DATA_DIR.mkdir(exist_ok=True) 
    
except Exception as e:
    logger.critical(f"❌ НЕ УДАЛОСЬ ЗАГРУЗИТЬ .env И КОНФИГ: {e}")
    sys.exit(f"Критическая ошибка: {e}")

# --- Производные константы ---
try:
    DEFAULT_TZ = ZoneInfo(settings.DEFAULT_TZ_KEY)
except Exception:
    logger.warning(f"Invalid default timezone: {settings.DEFAULT_TZ_KEY}. Using UTC.")
    DEFAULT_TZ = ZoneInfo("UTC")

SPECIAL_USER_IDS = set(settings.TESTER_USER_IDS).union(set(settings.SIMULATOR_USER_IDS)).union({settings.ADMIN_CHAT_ID})

# Логирование при старте
logger.info("🤖 Bot config loaded...")
logger.info(f"🔑 ADMIN_CHAT_ID configured as: {settings.ADMIN_CHAT_ID}")
logger.info(f"📂 DB_FILE is: {settings.DB_FILE}")