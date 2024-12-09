# src/core/config.py
from pathlib import Path
from pydantic_settings import BaseSettings
from src.utils import logger


class DatabaseSettings(BaseSettings):
    """Database-specific settings"""

    database_url: str = "sqlite:///data/bot.db"

    class Config:
        env_file = ".env"
        extra = "allow"


class BotSettings(BaseSettings):
    """Full bot settings including Discord configuration"""

    discord_token: str
    command_prefix: str = "!"
    owner_id: int = 1114624963169747068
    admin_user_ids: list[int] = []
    admin_role_ids: list[int] = []
    credentials_path: Path = Path("data/google-credentials.json")
    database: DatabaseSettings = DatabaseSettings()

    class Config:
        env_file = ".env"
        extra = "allow"


class Settings:
    """Settings singleton with separate database-only mode"""

    _instance = None
    _db_instance = None

    @classmethod
    def get_db(cls):
        """Get database-only settings"""
        if cls._db_instance is None:
            try:
                cls._db_instance = DatabaseSettings()
                logger.info("Database settings loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load database settings: {str(e)}")
                raise
        return cls._db_instance

    @classmethod
    def get(cls):
        """Get full bot settings"""
        if cls._instance is None:
            try:
                cls._instance = BotSettings()
                logger.info("Bot settings loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load bot settings: {str(e)}")
                raise
        return cls._instance


# Export database-only settings for migrations
settings = Settings.get_db()
