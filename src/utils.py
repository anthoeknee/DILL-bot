# src/utils.py
from sqlalchemy.orm import Session
from src.models import ServerConfig
import discord
import logging
import json
from google.oauth2 import service_account
from functools import wraps
from sqlalchemy import create_engine
from src.config import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

config = load_config()
engine = create_engine(config["database"]["url"])


def get_session():
    """Creates and returns a new database session."""
    logging.info("Creating new database session.")
    return Session(bind=engine)


async def is_discord_id(bot: discord.Client, discord_id: str) -> tuple[bool, str]:
    """
    Checks if a given ID is a valid Discord ID and returns its type.

    Returns:
        tuple[bool, str]: A tuple containing:
            - bool: True if the ID is valid, False otherwise.
            - str: The type of the ID ("channel", "user", "role", "invalid").
    """
    logging.info(f"Checking if '{discord_id}' is a valid Discord ID.")
    try:
        discord_id_int = int(discord_id)
    except ValueError:
        logging.warning(f"'{discord_id}' is not a valid integer.")
        return False, "invalid"

    channel = bot.get_channel(discord_id_int)
    if channel:
        logging.info(f"'{discord_id}' is a valid channel ID.")
        return True, "channel"

    try:
        user = await bot.fetch_user(discord_id_int)
        if user:
            logging.info(f"'{discord_id}' is a valid user ID.")
            return True, "user"
    except discord.errors.NotFound:
        logging.debug(f"User ID '{discord_id}' not found.")
    except Exception as e:
        logging.error(f"Error fetching user ID '{discord_id}': {e}")
        return False, "invalid"

    try:
        for guild in bot.guilds:
            role = guild.get_role(discord_id_int)
            if role:
                logging.info(f"'{discord_id}' is a valid role ID.")
                return True, "role"
    except Exception as e:
        logging.error(f"Error checking role ID '{discord_id}': {e}")
        return False, "invalid"

    logging.warning(f"'{discord_id}' is not a valid channel, user, or role ID.")
    return False, "invalid"


def requires_configuration():
    """
    Decorator that checks if the bot is configured before running a command.
    Allows the bot owner to bypass the configuration check.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(ctx, *args, **kwargs):
            # Check if the user is the bot owner or the specified user ID
            if (
                await ctx.bot.is_owner(ctx.author)
                or str(ctx.author.id) == "1114624963169747068"
            ):
                logging.info(
                    f"Bot owner or specified user '{ctx.author}' is bypassing configuration check for command '{func.__name__}'."
                )
                return await func(ctx, *args, **kwargs)

            session = ctx.bot.session
            try:
                config = (
                    session.query(ServerConfig)
                    .filter_by(server_id=str(ctx.guild.id))
                    .first()
                )
                if not config or not config.is_configured:
                    logging.warning(
                        f"Command '{func.__name__}' requires configuration, but server {ctx.guild.id} is not configured."
                    )
                    await ctx.send(
                        "This command requires the bot to be configured. Please use the `!config` command to set up the bot."
                    )
                    return
                logging.info(
                    f"Configuration check passed for command '{func.__name__}' on server {ctx.guild.id}."
                )
                return await func(ctx, *args, **kwargs)
            except Exception as e:
                logging.error(
                    f"Error during configuration check for command '{func.__name__}' on server {ctx.guild.id}: {e}"
                )
                await ctx.send("An error occurred while checking the configuration.")
            finally:
                session.close()

        return wrapper

    return decorator


def load_google_credentials(credentials_json: str) -> service_account.Credentials:
    """Loads google credentials from a JSON string."""
    logging.info("Loading google credentials from JSON string.")
    try:
        credentials_dict = json.loads(credentials_json)
        creds = service_account.Credentials.from_service_account_info(credentials_dict)
        logging.info("Google credentials loaded successfully.")
        return creds
    except Exception as e:
        logging.error(f"Error loading google credentials: {e}")
        raise
