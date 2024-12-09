from pathlib import Path
from typing import List

from discord.ext import commands

from src.utils.logger import logger
from src.core.config import Settings


class FeatureManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.features_path = Path("src/features")
        self.loaded_features: List[str] = []
        self.settings = Settings.get()

    async def load_all_features(self) -> None:
        """Load all features from the features directory"""
        logger.info("Starting feature discovery and loading process...")

        if not self.features_path.exists():
            logger.warning(f"Features directory not found at {self.features_path}")
            return

        # Load both individual feature files and folder features
        for path in self.features_path.iterdir():
            if path.is_file() and path.suffix == ".py" and path.name != "__init__.py":
                # Load individual feature file
                await self._load_feature_file(path)
            elif path.is_dir():
                # Load folder-based feature
                await self._load_folder_feature(path)

        logger.info(
            f"Successfully loaded {len(self.loaded_features)} features: {', '.join(self.loaded_features)}"
        )

    async def _load_feature_file(self, file_path: Path) -> None:
        """Load an individual feature file"""
        try:
            feature_name = file_path.stem
            module_path = f"src.features.{feature_name}"

            await self.bot.load_extension(module_path)
            self.loaded_features.append(feature_name)
            logger.info(f"Loaded feature file: {feature_name}")

        except Exception as e:
            logger.error(f"Failed to load feature file {file_path.name}: {str(e)}")

    async def _load_folder_feature(self, folder_path: Path) -> None:
        """Load a folder-based feature"""
        try:
            feature_name = folder_path.name
            cog_file = folder_path / "cog.py"

            if not cog_file.exists():
                logger.warning(f"Feature folder {feature_name} missing cog.py file")
                return

            module_path = f"src.features.{feature_name}.cog"
            await self.bot.load_extension(module_path)
            self.loaded_features.append(feature_name)
            logger.info(f"Loaded folder feature: {feature_name}")

        except Exception as e:
            logger.error(f"Failed to load folder feature {folder_path.name}: {str(e)}")

    async def reload_feature(self, feature_name: str) -> bool:
        """Reload a specific feature by name"""
        try:
            if feature_name not in self.loaded_features:
                logger.error(f"Feature {feature_name} not found")
                return False

            # Determine if it's a folder feature or single file feature
            feature_path = self.features_path / f"{feature_name}.py"
            folder_path = self.features_path / feature_name / "cog.py"

            if folder_path.exists():
                module_path = f"src.features.{feature_name}.cog"
            elif feature_path.exists():
                module_path = f"src.features.{feature_name}"
            else:
                logger.error(f"Feature {feature_name} files not found")
                return False

            await self.bot.reload_extension(module_path)
            return True

        except Exception as e:
            logger.error(f"Failed to reload feature {feature_name}: {str(e)}")
            return False
