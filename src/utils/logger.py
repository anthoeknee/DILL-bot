import logging
import sys
from pathlib import Path
from typing import Optional, Any

from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install

# Install rich traceback handling
install(show_locals=True)

# Create logs directory if it doesn't exist
LOG_DIR: Path = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure console output
console: Console = Console(force_terminal=True)
error_console: Console = Console(stderr=True, style="bold red")

class BotLogger:
    def __init__(self, name: str = "bot", log_file: Optional[str] = "bot.log") -> None:
        self.log_file: Optional[Path] = LOG_DIR / log_file if log_file else None
        
        # Configure logging format
        logging.basicConfig(
            level="INFO",
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="[%X]",
            handlers=[
                RichHandler(
                    console=console,
                    rich_tracebacks=True,
                    tracebacks_show_locals=True,
                    markup=True
                )
            ]
        )

        # Create logger instance
        self.logger: logging.Logger = logging.getLogger(name)
        
        # Add file handler if log_file is specified
        if self.log_file:
            file_handler: logging.FileHandler = logging.FileHandler(
                filename=self.log_file,
                encoding='utf-8',
                mode='a'
            )
            file_handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
            )
            self.logger.addHandler(file_handler)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message"""
        self.logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message"""
        self.logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message"""
        self.logger.error(message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message"""
        self.logger.debug(message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a critical message"""
        self.logger.critical(message, *args, **kwargs)

    def exception(self, message: str, *args: Any, exc_info: bool = True, **kwargs: Any) -> None:
        """Log an exception with traceback"""
        self.logger.exception(message, *args, exc_info=exc_info, **kwargs)

# Create a global logger instance
logger: BotLogger = BotLogger()

