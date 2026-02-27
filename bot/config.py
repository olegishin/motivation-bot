# 01 - bot/config.py
# 01 - bot/config.py - ФИНАЛЬНАЯ ВЕРСИЯ (22.02.2026)
# Конфигурация бота и логирование
# ✅ ПРОВЕРЕНО: Валидация всех параметров, блокировка старта при ошибках

import os
import logging
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Set, List
from pydantic import field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----------------- КОНФИГУРАЦИЯ ЛОГОВ -----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger("bot")
logger.propagate = False
logger.setLevel(logging.INFO)

# --- Отдельный логгер для критичных ошибок конфига ---
config_logger = logging.getLogger("config")
config_logger.setLevel(logging.CRITICAL)

# --- СПИСОК ОБЯЗАТЕЛЬНЫХ ПАРАМЕТРОВ ---
REQUIRED_SETTINGS = {
    "BOT_TOKEN": "Telegram Bot Token (от BotFather)",
    "ADMIN_CHAT_ID": "Admin user ID (твой ID в Telegram)",
    "WEBHOOK_URL": "Webhook URL (например, https://app.fly.dev)",
    "ADMIN_PASSWORD": "Admin password (для /admin/login)",
    "ADMIN_SECRET": "Admin secret token (для CSRF защиты)",
    "ADMIN_JWT_SECRET": "JWT secret (для админ-сессий)",
    "ADMIN_2FA_SECRET": "Google Authenticator 2FA secret",
}

# --- КРИТИЧНЫЕ ПУТИ ---
CRITICAL_PATHS = [
    "data_initial",  # Исходные данные (челленджи, правила и т.д.)
]

# ----------------- КОНФИГУРАЦИЯ .ENV -----------------
class Settings(BaseSettings):
    # === Основные (ОБЯЗАТЕЛЬНЫЕ) ===
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int
    WEBHOOK_URL: str
    DROP_PENDING_UPDATES: bool = True

    # === Язык и часовой пояс ===
    DEFAULT_LANG: str = "ru"
    DEFAULT_TZ_KEY: str = "Europe/Kiev"

    # === Админка (ОБЯЗАТЕЛЬНЫЕ) ===
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str
    ADMIN_SECRET: str
    ADMIN_JWT_SECRET: str
    ADMIN_2FA_SECRET: str

    # === Платежи ===
    PAYMENT_LINK: str = "https://send.monobank.ua/jar/ao8c487LS?a=245"
    PAYMENT_AMOUNT: int = 245
    PAYMENT_CURRENCY: str = "грн"

    # === Роли и тестеры ===
    TESTER_USER_IDS: Set[int] = {290711961, 6104624108}
    SIMULATOR_USER_IDS: Set[int] = {6112492697}

    # === Логика лимитов и демо (ФОРМУЛА 3+1+3) ===
    REGULAR_DEMO_DAYS: int = 3  # ← ИСПРАВЛЕНО: было 5, теперь 3
    REGULAR_COOLDOWN_DAYS: int = 1
    TESTER_DEMO_DAYS: int = 1
    TESTER_COOLDOWN_DAYS: int = 1
    RULES_PER_DAY_LIMIT: int = 3
    CHALLENGES_PER_DAY_LIMIT: int = 1
    MAX_DEMO_CYCLES: int = 2

    BOT_USERNAME: str = "FotiniaBot"

    # === Пути ===
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data")).resolve()

    @field_validator("DATA_DIR", mode="after")
    @classmethod
    def create_data_dir(cls, v: Path) -> Path:
        """Создает директорию данных, если она отсутствует."""
        try:
            v.mkdir(parents=True, exist_ok=True)
            logger.debug(f"✅ Data directory ensured: {v}")
        except PermissionError:
            logger.critical(f"❌ No permission to create directory: {v}")
            raise
        except Exception as e:
            logger.critical(f"❌ Error creating data directory: {e}")
            raise
        return v

    @property
    def BASE_URL(self) -> str:
        """Базовый URL приложения без слеша в конце."""
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
        """Путь к исходным данным (челленджи, правила и т.д.)."""
        return Path(__file__).resolve().parent.parent / "data_initial"

    @property
    def DEFAULT_TIMEZONE(self) -> str:
        """Алиас для DEFAULT_TZ_KEY (для совместимости)."""
        return self.DEFAULT_TZ_KEY

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# --- ✅ ПРОЦЕДУРА ВАЛИДАЦИИ КОНФИГА ---
def _validate_required_settings(settings_obj: Settings) -> None:
    """Проверяет наличие ВСЕХ обязательных параметров."""
    logger.info("=" * 70)
    logger.info("🔍 VALIDATING REQUIRED SETTINGS")
    logger.info("=" * 70)
    
    missing_settings = []
    
    for setting_name, setting_description in REQUIRED_SETTINGS.items():
        setting_value = getattr(settings_obj, setting_name, None)
        
        if not setting_value:
            missing_settings.append((setting_name, setting_description))
            logger.critical(f"❌ MISSING: {setting_name}")
            logger.critical(f"   Description: {setting_description}")
        else:
            # Скрываем чувствительные данные
            if "SECRET" in setting_name or "TOKEN" in setting_name or "PASSWORD" in setting_name:
                masked_value = setting_value[:10] + "..." if len(str(setting_value)) > 10 else "***"
                logger.info(f"✅ {setting_name}: {masked_value}")
            else:
                logger.info(f"✅ {setting_name}: {setting_value}")
    
    if missing_settings:
        logger.critical("=" * 70)
        logger.critical("🚨 CRITICAL: MISSING REQUIRED SETTINGS!")
        logger.critical("=" * 70)
        logger.critical("")
        logger.critical("The following settings are REQUIRED:")
        logger.critical("")
        
        for setting_name, setting_description in missing_settings:
            logger.critical(f"  • {setting_name}")
            logger.critical(f"    → {setting_description}")
        
        logger.critical("")
        logger.critical("For Fly.io deployment, use:")
        logger.critical("  $ flyctl secrets set KEY=VALUE")
        logger.critical("")
        logger.critical("=" * 70)
        
        sys.exit(1)  # 🔴 БЛОКИРУЕМ СТАРТ
    
    logger.info("✅ All required settings validated successfully!")
    logger.info("=" * 70)

def _validate_critical_paths(settings_obj: Settings) -> None:
    """Проверяет наличие критичных директорий."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("🔍 VALIDATING CRITICAL PATHS")
    logger.info("=" * 70)
    
    critical_issues = []
    
    # Проверяем data_initial
    if not settings_obj.DATA_INITIAL_DIR.exists():
        logger.critical(f"❌ MISSING: data_initial directory")
        logger.critical(f"   Path: {settings_obj.DATA_INITIAL_DIR}")
        critical_issues.append("data_initial")
    else:
        logger.info(f"✅ data_initial directory: {settings_obj.DATA_INITIAL_DIR}")
    
    # Проверяем права на DATA_DIR
    if settings_obj.DATA_DIR.exists():
        if not os.access(settings_obj.DATA_DIR, os.W_OK):
            logger.critical(f"❌ NO WRITE PERMISSION: {settings_obj.DATA_DIR}")
            critical_issues.append("data_dir_permissions")
        else:
            logger.info(f"✅ DATA_DIR is writable: {settings_obj.DATA_DIR}")
    
    if critical_issues:
        logger.critical("=" * 70)
        logger.critical("🚨 CRITICAL: MISSING OR INACCESSIBLE PATHS!")
        logger.critical("=" * 70)
        sys.exit(1)
    
    logger.info("✅ All critical paths validated successfully!")
    logger.info("=" * 70)

def _validate_bot_token_format(settings_obj: Settings) -> None:
    """Проверка формата BOT_TOKEN."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("🔍 VALIDATING BOT TOKEN FORMAT")
    logger.info("=" * 70)
    
    token = settings_obj.BOT_TOKEN
    
    if not token:
        logger.critical("❌ BOT_TOKEN is empty!")
        sys.exit(1)
    
    if ":" not in token:
        logger.critical("❌ BOT_TOKEN has invalid format!")
        sys.exit(1)
    
    parts = token.split(":")
    if len(parts) != 2 or not parts[0].isdigit():
        logger.critical("❌ BOT_TOKEN format error!")
        sys.exit(1)
    
    logger.info(f"✅ BOT_TOKEN format is valid: {parts[0]}:***")
    logger.info("=" * 70)

def _validate_admin_chat_id(settings_obj: Settings) -> None:
    """Проверка ADMIN_CHAT_ID."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("🔍 VALIDATING ADMIN_CHAT_ID")
    logger.info("=" * 70)
    
    admin_id = settings_obj.ADMIN_CHAT_ID
    
    if not isinstance(admin_id, int) or admin_id <= 0:
        logger.critical(f"❌ ADMIN_CHAT_ID must be positive integer")
        sys.exit(1)
    
    logger.info(f"✅ ADMIN_CHAT_ID is valid: {admin_id}")
    logger.info("=" * 70)

# --- ГЛАВНАЯ ПРОЦЕДУРА ЗАГРУЗКИ ---
logger.info("")
logger.info("=" * 70)
logger.info("🚀 INITIALIZING BOT CONFIGURATION")
logger.info("=" * 70)

try:
    settings = Settings()
    logger.info("✅ Settings loaded from .env / environment variables")
except ValidationError as e:
    logger.critical("❌ PYDANTIC VALIDATION ERROR:")
    for error in e.errors():
        logger.critical(f"   • {error['loc'][0]}: {error['msg']}")
    sys.exit(1)
except Exception as e:
    logger.critical(f"❌ CONFIG LOAD ERROR: {e}")
    sys.exit(1)

# Последовательные проверки
_validate_required_settings(settings)
_validate_bot_token_format(settings)
_validate_admin_chat_id(settings)
_validate_critical_paths(settings)

# --- ПРОИЗВОДНЫЕ КОНСТАНТЫ ---
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

DEFAULT_BROADCAST_KEYS: List[str] = [
    "morning_phrases",
    "goals",
    "day_phrases",
    "evening_phrases"
]

DEFAULT_TZ = ZoneInfo(settings.DEFAULT_TZ_KEY)
SPECIAL_USER_IDS = settings.TESTER_USER_IDS.union(settings.SIMULATOR_USER_IDS).union({settings.ADMIN_CHAT_ID})

# --- ФИНАЛЬНОЕ ЛОГИРОВАНИЕ ---
logger.info("")
logger.info("=" * 70)
logger.info("✨ BOT CONFIGURATION SUCCESSFULLY INITIALIZED")
logger.info("=" * 70)
logger.info(f"🤖 Bot username: @{settings.BOT_USERNAME}")
logger.info(f"🔗 Webhook URL: {settings.BASE_URL}")
logger.info(f"🔑 Admin Chat ID: {settings.ADMIN_CHAT_ID}")
logger.info(f"📂 Data directory: {settings.DATA_DIR}")
logger.info(f"📦 Data source: {settings.DATA_INITIAL_DIR}")
logger.info(f"💰 Payment: {settings.PAYMENT_AMOUNT} {settings.PAYMENT_CURRENCY}")
logger.info(f"🌍 Default language: {settings.DEFAULT_LANG}")
logger.info(f"🕐 Default timezone: {settings.DEFAULT_TZ_KEY}")
logger.info("=" * 70)