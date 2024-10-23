import os
from pathlib import Path
from typing import List
from discord.ext import commands
import importlib
import pkgutil
import logging

logger = logging.getLogger('bot')

class ModuleLoader:
    """Handles loading of bot modules, extensions, and services."""
    
    CORE_SERVICES = [
        'src.services.settings_service',
        'src.services.permission_service'
    ]
    
    EXTENSION_PATHS = [
        'src.events',
        'src.cogs'
    ]

    
    @staticmethod
    async def load_services(bot: commands.Bot) -> None:
        """Initialize core services and attach them to the bot instance.
        
        Args:
            bot: The Discord bot instance
        """
        try:
            # Import and initialize settings service first
            from src.services.settings_service import SettingsService
            bot.settings = SettingsService(bot.config)
            
            # Import and initialize permissions service
            from src.services.permission_service import PermissionService
            bot.permissions = PermissionService(bot)
            
            logger.info("Core services initialized")
            
        except Exception as e:
            logger.error("Failed to initialize core services", exc_info=e)
            raise

    @staticmethod
    def _collect_modules(package_path: str) -> List[str]:
        """Recursively collect all module paths from a package.

        Args:
            package_path: Import path to the package (e.g. 'src.cogs')

        Returns:
            List of full module import paths
        """
        modules: List[str] = []
        package = importlib.import_module(package_path)
        
        # Get the filesystem path
        pkg_path = Path(package.__path__[0])
        
        # Walk through all files and directories
        for item in pkg_path.rglob("*.py"):
            if item.stem.startswith("_"):  # Skip private modules
                continue
                
            # Convert file path to module path
            relative_path = item.relative_to(pkg_path)
            module_parts = list(relative_path.parent.parts)
            module_parts.append(item.stem)
            full_module_path = f"{package_path}.{'.'.join(module_parts)}"
            modules.append(full_module_path)
            
        return modules

    @staticmethod
    async def load_modules(bot: commands.Bot) -> None:
        """Load all extension modules.
        
        Args:
            bot: The Discord bot instance
        """
        modules: List[str] = []
        
        # Collect extension modules (cogs and events)
        for path in ModuleLoader.EXTENSION_PATHS:
            modules.extend(ModuleLoader._collect_modules(path))
        
        # Load each extension
        for module in modules:
            try:
                await bot.load_extension(module)
                logger.info(f"Loaded module: {module}")
            except Exception as e:
                logger.exception(f"Failed to load module {module}")

    @staticmethod
    async def setup(bot: commands.Bot) -> None:
        """Initialize services and load all modules.
        
        Args:
            bot: The Discord bot instance
        """
        await ModuleLoader.load_services(bot)
        await ModuleLoader.load_modules(bot)
