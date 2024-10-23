from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class CommandSyncManager:
    """Manages Discord application command synchronization."""

    def __init__(self, bot: commands.Bot):
        """Initialize the sync manager.
        
        Args:
            bot: The Discord bot instance
        """
        self.bot = bot
        self._command_tree_hash = self._get_command_tree_hash()

    def _get_command_tree_hash(self) -> int:
        """Calculate a hash of the command tree for sync detection.
        
        Returns:
            Hash value representing the current command tree state
        """
        commands = self.bot.tree.get_commands()
        return hash(tuple(sorted(cmd.name for cmd in commands)))

    async def sync_commands(self, guild_id: Optional[int] = None) -> List[app_commands.Command]:
        """Sync application commands with Discord.
        
        Args:
            guild_id: Optional guild ID to sync commands for. If None, syncs globally.
            
        Returns:
            List of synced commands
            
        Raises:
            discord.HTTPException: If command sync fails
        """
        try:
            logger.info(f"Starting command sync for {'guild ' + str(guild_id) if guild_id else 'global'}")
            
            if guild_id:
                # Sync to a specific guild
                guild = discord.Object(id=guild_id)
                self.bot.tree.copy_global_to(guild=guild)
                commands = await self.bot.tree.sync(guild=guild)
            else:
                # Global sync
                commands = await self.bot.tree.sync()
                
            logger.info(f"Successfully synced {len(commands)} commands")
            self._command_tree_hash = self._get_command_tree_hash()
            return commands
            
        except discord.HTTPException as e:
            logger.error(f"Failed to sync commands: {e}", exc_info=True)
            raise

    async def check_sync_needed(self) -> bool:
        """Check if command synchronization is needed.
        
        Returns:
            True if sync is needed, False otherwise
        """
        return self._get_command_tree_hash() != self._command_tree_hash

    async def sync_if_needed(self) -> Optional[List[app_commands.Command]]:
        """Sync commands only if changes are detected.
        
        Returns:
            List of synced commands if sync was performed, None if no sync needed
        """
        if await self.check_sync_needed():
            return await self.sync_commands()
        return None

async def setup(bot: commands.Bot) -> None:
    """Set up the command sync module."""
    bot.sync_manager = CommandSyncManager(bot)
