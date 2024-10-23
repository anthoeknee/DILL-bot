from typing import Callable, TypeVar
from discord import app_commands
from discord import Interaction
from src.config import config

T = TypeVar('T')

def is_owner() -> Callable[[T], T]:
    """A check that verifies if the user is the bot owner"""
    async def predicate(interaction: Interaction) -> bool:
        owner_id = config.get('owner_id')
        return interaction.user.id == owner_id
    
    return app_commands.check(predicate)