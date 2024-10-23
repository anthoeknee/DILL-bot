import math
from typing import List, Dict, Optional
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

class HelpView(View):
    def __init__(self, help_cog: 'Help', interaction: discord.Interaction, pages: List[discord.Embed], timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.help_cog = help_cog
        self.interaction = interaction
        self.pages = pages
        self.current_page = 0
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can use the buttons"""
        return interaction.user.id == self.interaction.user.id
        
    @discord.ui.button(label="◀", custom_id="prev")
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page])
        
    @discord.ui.button(label="▶", custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page])

class Help(commands.GroupCog, group_name="help"):
    """Help commands for the bot"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()
        
    def get_command_signature(self, command: app_commands.Command) -> str:
        """Get the command signature with parameters"""
        # Handle command groups differently
        if isinstance(command, app_commands.Group):
            return f"/{command.name}"
            
        params = []
        for param in command.parameters:
            if param.required:
                params.append(f"<{param.name}>")
            else:
                params.append(f"[{param.name}]")
        
        return f"/{command.name} {' '.join(params)}"
        
    def create_command_embed(self, commands_dict: Dict[str, List[app_commands.Command]], page: int, total_pages: int) -> discord.Embed:
        """Create an embed for a page of commands"""
        embed = discord.Embed(
            title="Bot Commands",
            color=discord.Color.blue(),
            description="Here are all available commands:"
        )
        
        for cog_name, commands_list in commands_dict.items():
            if commands_list:
                value = ""
                for cmd in commands_list:
                    signature = self.get_command_signature(cmd)
                    value += f"`{signature}`\n"
                    if isinstance(cmd, app_commands.Group):
                        # For groups, list their subcommands
                        for subcmd in cmd.commands:
                            sub_signature = self.get_command_signature(subcmd)
                            value += f"↳ `{sub_signature}`\n"
                            if subcmd.description:
                                value += f"  ↳ {subcmd.description}\n"
                    elif cmd.description:
                        value += f"↳ {cmd.description}\n"
                    value += "\n"
                
                embed.add_field(
                    name=f"📑 {cog_name}",
                    value=value,
                    inline=False
                )
        
        embed.set_footer(text=f"Page {page + 1} of {total_pages}")
        return embed
        
    def get_commands_by_cog(self) -> Dict[str, List[app_commands.Command]]:
        """Get all commands organized by cog"""
        commands_dict: Dict[str, List[app_commands.Command]] = {}
        
        for cmd in self.bot.tree.get_commands():
            # Skip help commands to avoid recursion
            if cmd.name == "help":
                continue
                
            # Get the cog name, default to "Miscellaneous" if no cog
            cog_name = "Miscellaneous"
            if isinstance(cmd, app_commands.Command) and hasattr(cmd, 'binding'):
                if cmd.binding and isinstance(cmd.binding, commands.Cog):
                    cog_name = cmd.binding.__class__.__name__
            
            if cog_name not in commands_dict:
                commands_dict[cog_name] = []
            commands_dict[cog_name].append(cmd)
            
        return commands_dict
    
    @app_commands.command(name="all")
    async def help_all(self, interaction: discord.Interaction):
        """Show all available commands"""
        commands_dict = self.get_commands_by_cog()
        
        # Create pages (1 page per 6 command groups)
        commands_per_page = 6
        total_pages = math.ceil(len(commands_dict) / commands_per_page)
        pages = []
        
        for page in range(total_pages):
            start_idx = page * commands_per_page
            end_idx = start_idx + commands_per_page
            page_commands = dict(list(commands_dict.items())[start_idx:end_idx])
            pages.append(self.create_command_embed(page_commands, page, total_pages))
        
        # Send first page with navigation buttons
        view = HelpView(self, interaction, pages)
        await interaction.response.send_message(embed=pages[0], view=view)
    
    @app_commands.command(name="command")
    @app_commands.describe(command_name="The name of the command to get help for")
    async def help_command(self, interaction: discord.Interaction, command_name: str):
        """Get detailed help for a specific command"""
        # Find the command
        command = None
        for cmd in self.bot.tree.get_commands():
            if cmd.name == command_name:
                command = cmd
                break
        
        if not command:
            await interaction.response.send_message(
                f"Command `{command_name}` not found.",
                ephemeral=True
            )
            return
        
        # Create embed for the command
        embed = discord.Embed(
            title=f"Command: /{command.name}",
            color=discord.Color.blue(),
            description=command.description or "No description available."
        )
        
        # Add command signature
        signature = self.get_command_signature(command)
        embed.add_field(
            name="Usage",
            value=f"`{signature}`",
            inline=False
        )
        
        # Add parameters if any
        if command.parameters:
            params_desc = ""
            for param in command.parameters:
                param_desc = f"`{param.name}`"
                if param.description:
                    param_desc += f": {param.description}"
                if not param.required:
                    param_desc += " (Optional)"
                params_desc += f"{param_desc}\n"
            
            embed.add_field(
                name="Parameters",
                value=params_desc,
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
