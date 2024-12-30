# src/config.py
import os
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from src.models import ServerConfig
import logging

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def load_config() -> Dict[str, Any]:
    config = {
        "bot": {
            "token": os.getenv("DISCORD_TOKEN"),
            "prefix": os.getenv("BOT_PREFIX"),
        },
        "google": {
            "credentials_path": os.getenv(
                "GOOGLE_CREDENTIALS_PATH", "data/google-credentials.json"
            ),
            "spreadsheet_id": os.getenv("SPREADSHEET_ID"),
        },
        "database": {"url": os.getenv("DATABASE_URL", "sqlite:///./data/bot.db")},
    }
    return config


class ConfigManager:
    """Manages the configuration for the bot, including server-specific settings."""

    def __init__(self, session: Session):
        self.session = session
        self.sync_guild_id = os.getenv("SYNC_GUILD_ID")
        logging.info(f"ConfigManager initialized. SYNC_GUILD_ID: {self.sync_guild_id}")

    def get_config(self, server_id: Optional[str] = None) -> Optional[ServerConfig]:
        """Retrieves the configuration for a specific server."""
        if not server_id:
            server_id = self.sync_guild_id
        if not server_id:
            logging.warning(
                "No server_id provided and SYNC_GUILD_ID not set. Cannot retrieve config."
            )
            return None
        return self.session.query(ServerConfig).filter_by(server_id=server_id).first()

    def create_or_update_config(self, config_data: Dict[str, Any]) -> ServerConfig:
        """Creates or updates the configuration for a server."""
        server_id = config_data.get("server_id")
        if not server_id:
            logging.error("No server_id provided. Cannot create or update config.")
            return None

        config = self.get_config(server_id)
        if not config:
            config = ServerConfig(server_id=server_id)
            self.session.add(config)

        for key, value in config_data.items():
            if key != "server_id":
                setattr(config, key, value)

        self.session.commit()
        logging.info(f"Configuration for server {server_id} updated.")
        return config

    def set_google_credentials(self, server_id: str, credentials: Dict[str, Any]):
        """Sets the Google credentials for a server."""
        config = self.get_config(server_id)
        if config:
            config.set_google_credentials(credentials)
            self.session.commit()
            logging.info(f"Google credentials set for server {server_id}.")
        else:
            logging.error(f"No config found for server {server_id}.")
