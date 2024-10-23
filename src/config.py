import yaml
import os
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from YAML file."""
        config_path: Path = Path(__file__).parent.parent / 'data' / 'settings.yml'
        
        try:
            with open(config_path, 'r') as file:
                self._config = yaml.safe_load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found at {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing config.yml: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        Returns default if key doesn't exist.
        """
        return self._config.get(key, default)

    def __getattr__(self, key: str) -> Any:
        """
        Dynamically access configuration values as properties.
        Prioritizes environment variables for keys prefixed with 'DISCORD_'.
        """
        env_key: str = f'DISCORD_{key.upper()}'
        env_value: Optional[str] = os.getenv(env_key)
        
        if env_value is not None:
            return env_value
            
        return self._config.get(key)

# Create a global instance
config: Config = Config()
