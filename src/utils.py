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
from discord.ext import commands

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

config = load_config()
engine = create_engine(config["database"]["url"])


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
    def wrapper(func):
        @wraps(func)
        async def wrapped(cog, ctx, *args, **kwargs):
            """Check if the bot is configured for the server and user has permission"""
            if not ctx.guild:
                await ctx.send("This command can only be used in a server.")
                return

            server_id = str(ctx.guild.id)
            author = ctx.author

            # Check if user is bot owner
            is_owner = await ctx.bot.is_owner(author)

            config_manager = ctx.bot.config_manager
            config = config_manager.get_config(server_id)

            if not config or not config.is_configured:
                await ctx.send(
                    "Bot is not configured for this server. Please configure it first."
                )
                return

            if not config.enabled and not is_owner:
                await ctx.send("Bot is currently disabled for this server.")
                return

            return await func(cog, ctx, *args, **kwargs)

        return wrapped

    return wrapper


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
