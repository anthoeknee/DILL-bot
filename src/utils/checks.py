from typing import Callable, TypeVar
from discord import app_commands
from discord import Interaction
from src.config import config

T = TypeVar('T')

def is_owner() -> Callable[[T], T]:
    """A check that verifies if the user is the bot owner"""
    async def predicate(interaction: Interaction) -> bool:
        if not isinstance(interaction.user.id, int):
            return False
        owner_id = int(config.get('owner_id'))
        return interaction.user.id == owner_id
    
    return app_commands.check(predicate)

def is_admin_or_owner() -> Callable[[T], T]:
    """A check that verifies if the user is either an admin or the bot owner"""
    async def predicate(interaction: Interaction) -> bool:
        if not isinstance(interaction.user.id, int):
            return False
        # Check if user is bot owner
        owner_id = int(config.get('owner_id'))
        if interaction.user.id == owner_id:
            return True
        # Check if user has admin permissions
        return interaction.user.guild_permissions.administrator
    
    return app_commands.check(predicate)