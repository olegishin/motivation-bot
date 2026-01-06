# 01 - bot/config.py
# Конфигурация бота и логирование.

import os
import logging
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Set, List
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----------------- КОНФИГУРАЦИЯ ЛОГОВ -----------------
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("bot")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
if not logger.hasHandlers():
    logger.addHandler(handler)
logger.propagate = False
logger.setLevel(logging.INFO)

# ----------------- КОНФИГУРАЦИЯ .ENV -----------------
class Settings(BaseSettings):
    # === Основные ===
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int
    WEBHOOK_URL: str

    # === Язык и часовой пояс ===
    DEFAULT_LANG: str = "ru"
    DEFAULT_TZ_KEY: str = "Europe/Kiev"

    # === Админка ===
    ADMIN_USERNAME: str = "admin"
    
    # Секреты (ОБЯЗАТЕЛЬНО должны быть в .env или Secrets)
    ADMIN_PASSWORD: str
    ADMIN_SECRET: str 
    ADMIN_JWT_SECRET: str
    ADMIN_2FA_SECRET: str

    # === Роли и тестеры ===
    TESTER_USER_IDS: Set[int] = {290711961, 6104624108}
    SIMULATOR_USER_IDS: Set[int] = {6112492697}

    # === Логика демо ===
    REGULAR_DEMO_DAYS: int = 5
    REGULAR_COOLDOWN_DAYS: int = 1
    TESTER_DEMO_DAYS: int = 1
    TESTER_COOLDOWN_DAYS: int = 1
    RULES_PER_DAY_LIMIT: int = 3
    MAX_DEMO_CYCLES: int = 2

    BOT_USERNAME: str = "FotiniaBot"

    # === Пути ===
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data"))

    # 🔥 НОВОЕ: Динамический BASE_URL для WebApp
    @property
    def BASE_URL(self) -> str:
        """Базовый URL приложения без слеша в конце (для WebApp ссылок)."""
        return self.WEBHOOK_URL.rstrip("/")

    @property
    def USERS_FILE(self) -> Path:
        """Путь к файлу users.json (для миграции)."""
        return self.DATA_DIR / "users.json"

    @property
    def DB_FILE(self) -> Path:
        """Путь к файлу базы данных SQLite."""
        return self.DATA_DIR / "fotinia.db"

    @property
    def DATA_INITIAL_DIR(self) -> Path:
        """Путь к исходным данным."""
        return Path(__file__).parent.parent / "data_initial"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# ----------------- ЗАГРУЗКА -----------------
try:
    settings = Settings()
except Exception as e:
    logger.critical(f"❌ CONFIG ERROR: {e}")
    sys.exit(f"Критическая ошибка конфига (проверьте .env): {e}")

# --- Сопоставление файлов контента ---
FILE_MAPPING = {
    "rules": "universe_laws.json",
    "motivations": "fotinia_motivations.json",
    "ritm": "fotinia_ritm.json",
    "morning_phrases": "fotinia_morning_phrases.json",
    "goals": "fotinia_goals.json",
    "day_phrases": "fotinia_day_phrases.json",
    "evening_phrases": "fotinia_evening_phrases.json",
    "challenges": "challenges.json"
}

# Ключи рассылки, используемые планировщиком
DEFAULT_BROADCAST_KEYS: List[str] = [
    "morning_phrases", 
    "goals", 
    "day_phrases", 
    "evening_phrases"
]

# --- Производные константы ---
DEFAULT_TZ = ZoneInfo(settings.DEFAULT_TZ_KEY)
SPECIAL_USER_IDS = settings.TESTER_USER_IDS.union(settings.SIMULATOR_USER_IDS).union({settings.ADMIN_CHAT_ID})

# Логирование при старте
logger.info("🤖 Bot config loaded...")
logger.info(f"🔗 BASE_URL: {settings.BASE_URL}")
logger.info(f"🔑 ADMIN_CHAT_ID: {settings.ADMIN_CHAT_ID}")
logger.info(f"📂 DATA_DIR: {settings.DATA_DIR}")