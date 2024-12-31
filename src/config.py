# src/config.py
import os
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from src.models import ServerConfig
import logging
import json
from google.oauth2 import service_account

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
        self.google_credentials = self._load_google_credentials()
        logging.info(f"ConfigManager initialized. SYNC_GUILD_ID: {self.sync_guild_id}")

    def _load_google_credentials(self) -> Optional[Dict]:
        """Loads Google credentials from the specified file path."""
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        if not credentials_path:
            logging.warning(
                "GOOGLE_CREDENTIALS_PATH not set, skipping credentials load."
            )
            return None
        try:
            with open(credentials_path, "r") as f:
                credentials = json.load(f)
                logging.info("Google credentials loaded from file.")
                return credentials
        except FileNotFoundError:
            logging.error(f"Google credentials file not found at {credentials_path}.")
            return None
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {credentials_path}.")
            return None
        except Exception as e:
            logging.error(f"Error loading google credentials: {e}")
            return None

    def get_google_credentials(self) -> Optional[Dict]:
        """Returns the loaded Google credentials."""
        return self.google_credentials

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

    def save_config(self, config):
        """Save a new config to the database"""
        self.session.add(config)
        self.session.commit()
        return config

    def update_config(self, guild_id, **kwargs):
        """Update an existing config"""
        config = self.get_config(guild_id)
        if config:
            for key, value in kwargs.items():
                setattr(config, key, value)
            self.session.commit()
        return config
