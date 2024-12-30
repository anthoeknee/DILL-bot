# start.py
import logging
import os

import discord
import dotenv
from discord.ext import commands
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from alembic.config import Config
from alembic import command
from sqlalchemy.orm import sessionmaker

from src.bot import DiscordBot
from src.models import Base
from src.config import ConfigManager, load_config

dotenv.load_dotenv()


def setup_logging():
    """Configures logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.info("Logging configured.")


def setup_database() -> Engine:
    """Initializes the database and runs Alembic migrations."""
    logging.info("Setting up database.")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.error("DATABASE_URL environment variable not set.")
        exit(1)
    engine = create_engine(db_url)
    logging.info("Database engine created.")

    # Configure Alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", os.path.abspath("migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    logging.info("Alembic configuration set.")

    # Run migrations
    try:
        command.upgrade(alembic_cfg, "head")
        logging.info("Database migrations completed.")
    except Exception as e:
        logging.error(f"Error running database migrations: {e}")
        exit(1)

    Base.metadata.create_all(engine)
    logging.info("Database tables created.")
    return engine


def main():
    """Main function to run the bot."""
    setup_logging()
    engine = setup_database()
    Session = sessionmaker(bind=engine)
    session = Session()
    config_manager = ConfigManager(session)

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # Create a commands.Bot instance with help_command=None
    base_bot = commands.Bot(
        command_prefix=commands.when_mentioned_or(load_config()["bot"]["prefix"]),
        intents=intents,
        help_command=None,  # Disable default help command here
    )

    # Pass the commands.Bot instance to your DiscordBot (no need to assign to a variable)
    DiscordBot(
        base_bot=base_bot,
        config_manager=config_manager,
        session=session,
    )

    # Run the bot using the commands.Bot instance
    base_bot.run(load_config()["bot"]["token"])


if __name__ == "__main__":
    main()
