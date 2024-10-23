from typing import Any, Dict, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from asyncio.log import logger
from postgrest import AsyncPostgrestClient

from src.config import Config

@dataclass
class Setting:
    """Represents a bot setting"""
    key: str
    value: Any
    scope: str
    scope_id: Optional[int]
    description: Optional[str] = None
    category: str = "General"

@dataclass
class CachedSetting:
    """Represents a cached setting with timestamp"""
    setting: Setting
    timestamp: datetime

class SettingsService:
    """Service for managing bot settings with caching."""
    
    def __init__(self, config: 'Config') -> None:
        """Initialize the settings service.
        
        Args:
            config: Bot configuration instance
        """
        self._config = config
        self._cache: Dict[str, CachedSetting] = {}
        self._cache_duration = timedelta(minutes=5)  # Cache settings for 5 minutes
        self._pending_requests: Set[str] = set()  # Track in-flight requests
        
        # Initialize async postgrest client
        self._db = AsyncPostgrestClient(
            f"{config.get('supabase_url')}/rest/v1",
            headers={
                'apikey': config.get('supabase_key'),
                'Authorization': f"Bearer {config.get('supabase_key')}"
            }
        )

    def _get_setting_cache_key(self, key: str, scope: str, scope_id: Optional[int]) -> str:
        """Generate a unique cache key for a specific setting.
        
        Args:
            key: Setting key
            scope: Setting scope (e.g., 'guild', 'user')
            scope_id: Scope identifier
            
        Returns:
            Unique cache key string
        """
        return f"{key}:{scope}:{scope_id}"

    def _is_cache_valid(self, cached: CachedSetting) -> bool:
        """Check if cached setting is still valid.
        
        Args:
            cached: Cached setting entry
            
        Returns:
            True if cache is valid, False otherwise
        """
        return (datetime.now() - cached.timestamp) < self._cache_duration

    async def get_setting(
        self,
        key: str,
        scope: str,
        scope_id: Optional[int] = None
    ) -> Optional[Setting]:
        """Get a setting value, using cache when available."""
        cache_key = self._get_setting_cache_key(key, scope, scope_id)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_cache_valid(cached):
                return cached.setting
            
        if cache_key in self._pending_requests:
            return None
            
        try:
            self._pending_requests.add(cache_key)
            
            response = await self._db.from_('settings') \
                .select('*') \
                .eq('key', key) \
                .eq('scope', scope) \
                .eq('scope_id', scope_id) \
                .execute()

            if response.data and len(response.data) > 0:
                data = response.data[0]
                if isinstance(data['value'], str):
                    try:
                        data['value'] = json.loads(data['value'])
                    except json.JSONDecodeError:
                        pass  # Keep as string if not valid JSON
                
                setting = Setting(**data)
                # Update cache
                self._cache[cache_key] = CachedSetting(
                    setting=setting,
                    timestamp=datetime.now()
                )
                return setting
                
            return None
            
        except Exception as e:
            logger.error(f"Error fetching setting: {e}")
            return None
            
        finally:
            self._pending_requests.remove(cache_key)

    def _get_scope_cache_key(self, scope: str, scope_id: Optional[int]) -> str:
        """Generate cache key for a scope.
        
        Args:
            scope: Setting scope (e.g., 'guild', 'user')
            scope_id: Scope identifier
            
        Returns:
            Unique cache key string
        """
        return f"{scope}:{scope_id if scope_id else 'global'}"

    async def get_all_settings(
        self, 
        scope: str, 
        scope_id: Optional[int] = None
    ) -> List[Setting]:
        """Retrieve all settings for a given scope.

        Args:
            scope: Setting scope (e.g., 'guild', 'global')
            scope_id: Optional scope identifier

        Returns:
            List of Setting objects
        """
        try:
            # Load fresh settings from database
            await self._load_settings()
            
            # Filter cached settings by scope and scope_id
            settings = []
            for cache_key, cached_setting in self._cache.items():
                setting = cached_setting.setting
                if setting.scope == scope and setting.scope_id == scope_id:
                    settings.append(setting)
                    
            return settings
            
        except Exception as e:
            logger.error(f"Error getting all settings: {e}")
            return []

    async def set_setting(
        self, 
        key: str, 
        value: Any, 
        scope: str, 
        scope_id: Optional[int] = None,
        description: Optional[str] = None,
        category: str = "General"
    ) -> Setting:
        """Create or update a setting."""
        stored_value = (json.dumps(value) 
                       if not isinstance(value, (str, int, float, bool, type(None)))
                       else value)

        data = {
            'key': key,
            'value': stored_value,
            'scope': scope,
            'scope_id': scope_id,
            'description': description,
            'category': category
        }
        
        response = await self._db.from_('settings').upsert(
            data,
            on_conflict='key,scope,scope_id'
        ).execute()

        if not response.data:
            raise Exception("Failed to save setting to Supabase")

        setting = Setting(
            key=key,
            value=value,
            scope=scope,
            scope_id=scope_id,
            description=description,
            category=category
        )
        
        cache_key = self._get_setting_cache_key(key, scope, scope_id)
        self._cache[cache_key] = CachedSetting(
            setting=setting,
            timestamp=datetime.now()
        )
        return setting

    async def delete_setting(
        self, 
        key: str, 
        scope: str, 
        scope_id: Optional[int] = None
    ) -> bool:
        """Delete a setting."""
        try:
            response = await self._db.from_('settings').delete().match({
                'key': key,
                'scope': scope,
                'scope_id': scope_id
            }).execute()

            if response.data:
                cache_key = self._get_setting_cache_key(key, scope, scope_id)
                self._cache.pop(cache_key, None)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error deleting setting: {e}")
            return False

    async def delete_all_settings(
        self, 
        scope: str, 
        scope_id: Optional[int] = None
    ) -> None:
        """Delete all settings for a given scope.

        Args:
            scope: Setting scope
            scope_id: Optional scope identifier

        Raises:
            Exception: If settings cannot be deleted from database
        """
        try:
            self._db.from_('settings').delete().match({
                'scope': scope,
                'scope_id': scope_id
            }).execute()
            
            cache_key = self._get_cache_key(scope, scope_id)
            self.settings_cache.pop(cache_key, None)
                
        except Exception as e:
            print(f"Error deleting settings from Supabase: {e}")
            raise

    async def _load_settings(self) -> None:
        """Load all settings for the current scope from the database."""
        try:
            response = await self._db.from_('settings').select('*').execute()
            
            if response.data:
                # Process each setting
                for data in response.data:
                    # Parse JSON values if stored as strings
                    if isinstance(data['value'], str):
                        try:
                            data['value'] = json.loads(data['value'])
                        except json.JSONDecodeError:
                            pass  # Keep as string if not valid JSON
                    
                    setting = Setting(**data)
                    cache_key = self._get_setting_cache_key(
                        setting.key,
                        setting.scope,
                        setting.scope_id
                    )
                    self._cache[cache_key] = CachedSetting(
                        setting=setting,
                        timestamp=datetime.now()
                    )
                    
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            raise
