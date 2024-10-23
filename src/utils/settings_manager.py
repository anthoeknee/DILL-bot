import sqlite3
import json
from typing import Any, Optional, Union, Dict, TypeVar, cast
from pathlib import Path
from enum import Enum

T = TypeVar('T')  # Generic type for return values

class SettingType(Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    JSON = "json"
    FLOAT = "float"

class SettingsManager:
    def __init__(self, db_path: Union[str, Path] = "data/db/settings.db") -> None:
        self.db_path: Path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.setup_database()

    def setup_database(self) -> None:
        """Initialize the database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    type TEXT NOT NULL,
                    PRIMARY KEY (guild_id, key)
                )
            """)

    def _convert_value(self, value: Any, setting_type: SettingType) -> str:
        """Convert a value to string for storage"""
        if setting_type == SettingType.JSON:
            return json.dumps(value)
        return str(value)

    def _parse_value(self, value: str, setting_type: SettingType) -> Any:
        """Parse a stored value back to its proper type"""
        if setting_type == SettingType.INTEGER:
            return int(value)
        elif setting_type == SettingType.BOOLEAN:
            return value.lower() == "true"
        elif setting_type == SettingType.FLOAT:
            return float(value)
        elif setting_type == SettingType.JSON:
            return json.loads(value)
        return value

    def set(self, guild_id: int, key: str, value: Any, setting_type: SettingType) -> None:
        """Set a setting value"""
        with sqlite3.connect(self.db_path) as conn:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (guild_id, key, value, type) VALUES (?, ?, ?, ?)",
                (guild_id, key, self._convert_value(value, setting_type), setting_type.value)
            )

    def get(self, guild_id: int, key: str, default: T = None) -> Union[str, int, bool, float, Dict, T]:
        """Get a setting value"""
        with sqlite3.connect(self.db_path) as conn:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                "SELECT value, type FROM settings WHERE guild_id = ? AND key = ?",
                (guild_id, key)
            )
            result: Optional[tuple[str, str]] = cursor.fetchone()
            
            if result is None:
                return cast(T, default)
                
            value, type_str = result
            return self._parse_value(value, SettingType(type_str))

    def delete(self, guild_id: int, key: str) -> None:
        """Delete a setting"""
        with sqlite3.connect(self.db_path) as conn:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM settings WHERE guild_id = ? AND key = ?",
                (guild_id, key)
            )

    def get_all(self, guild_id: int) -> Dict[str, Any]:
        """Get all settings for a guild"""
        settings: Dict[str, Any] = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                "SELECT key, value, type FROM settings WHERE guild_id = ?",
                (guild_id,)
            )
            for key, value, type_str in cursor.fetchall():
                settings[key] = self._parse_value(value, SettingType(type_str))
        return settings
