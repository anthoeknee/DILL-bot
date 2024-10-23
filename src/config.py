import yaml
import os
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    """Manages bot configuration from YAML file and environment variables."""
    
    def __init__(self) -> None:
        """Initialize configuration from environment variables and YAML file."""
        # Load YAML first so we can use it in the initial config
        self._config: Dict[str, Any] = {}
        self.load_config()
        
        # Now update with environment variables and YAML values
        self._config.update({
            'supabase_url': os.getenv('SUPABASE_URL', 'your_supabase_url'),
            'supabase_key': os.getenv('SUPABASE_KEY', 'your_supabase_service_key'),
            'openai_api_key': os.getenv('OPENAI_API_KEY') or self._config.get('openai_api_key')
        })

    def load_config(self) -> None:
        """Load configuration from YAML file."""
        config_path: Path = Path(__file__).parent.parent / 'data' / 'settings.yml'
        
        try:
            with open(config_path, 'r') as file:
                yaml_config = yaml.safe_load(file) or {}
                self._config.update(yaml_config)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found at {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing config.yml: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key: Configuration key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            Configuration value or default
        """
        # Check environment variables first
        env_key = f'DISCORD_{key.upper()}'
        env_value = os.getenv(env_key)
        if env_value is not None:
            return env_value
            
        return self._config.get(key, default)

    def __getattr__(self, key: str) -> Any:
        """
        Access configuration values as properties.
        Prioritizes environment variables over YAML config.
        """
        return self.get(key)

    @property
    def token(self) -> Optional[str]:
        """Get Discord bot token from environment or config."""
        return os.getenv('DISCORD_TOKEN') or self._config.get('token')

# Create a global instance
config: Config = Config()
