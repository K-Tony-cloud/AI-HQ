"""Slash commands: /top-profit"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed
from discord_bot.embeds.performance_embeds import (
    build_daily_performance_embed,
    build_top_profit_pages,
)
from discord_bot.services.performance_service import (
    get_daily_performance,
    get_top_profit,
)


class PerformanceCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /top-profit
    # ------------------------------------------------------------------

    @app_commands.command(
        name="top-profit",
        description="Top affiliate products ranked by Commission → EPC → Conversion Rate",
    )
    @app_commands.describe(top="Number of results (default 20)")
    async def cmd_top_profit(
        self,
        interaction: discord.Interaction,
        top: int = 20,
    ) -> None:
        await interaction.response.defer()
        result = get_top_profit(top=top)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        pages = build_top_profit_pages(result["data"])
        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            view = PaginatedView(pages)
            await interaction.followup.send(embed=pages[0], view=view)
