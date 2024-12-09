# logger.py
import logging
import sys
from pathlib import Path

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Configure the logger
logger = logging.getLogger("discord_bot")
logger.setLevel(logging.INFO)

# Format for our log messages
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# File handler that overwrites previous logs
file_handler = logging.FileHandler(
    log_dir / "bot.log",
    mode="w",  # 'w' mode overwrites the file on each run
)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)


# Convenience functions
def info(msg: str) -> None:
    logger.info(msg)


def error(msg: str) -> None:
    logger.error(msg)


def warning(msg: str) -> None:
    logger.warning(msg)


def debug(msg: str) -> None:
    logger.debug(msg)
