import os
from pathlib import Path
from typing import List
from discord.ext import commands
from src.utils.logger import logger

class ModuleLoader:
    @staticmethod
    def get_all_modules() -> List[str]:
        """Automatically discover all loadable modules in the src directory"""
        src_path = Path(__file__).parent.parent
        modules = []

        # Directories to scan for modules
        module_dirs = ['events', 'cogs']

        for dir_name in module_dirs:
            dir_path = src_path / dir_name
            if not dir_path.exists():
                continue

            # Walk through the directory
            for root, _, files in os.walk(dir_path):
                for file in files:
                    # Only process Python files that aren't __init__.py
                    if file.endswith('.py') and file != '__init__.py':
                        # Convert file path to module path
                        # e.g., src/events/on_ready.py -> src.events.on_ready
                        rel_path = Path(root).relative_to(src_path.parent)
                        module_name = str(rel_path / file[:-3]).replace(os.sep, '.')
                        modules.append(module_name)

        return modules

    @staticmethod
    async def load_modules(bot: commands.Bot) -> None:
        """Load all discovered modules into the bot"""
        modules = ModuleLoader.get_all_modules()
        
        for module in modules:
            try:
                await bot.load_extension(module)
                logger.info(f"Loaded module: {module}")
            except Exception as e:
                logger.exception(f"Failed to load module {module}")
