"""Slash commands: /morning-brief, /executive-summary"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, send_and_confirm
from discord_bot.embeds.operator_embeds import (
    build_executive_summary_embeds,
    build_morning_brief_embeds,
)
from discord_bot.services.operator_service import (
    get_executive_summary,
    get_morning_brief,
)


class OperatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /morning-brief
    # ------------------------------------------------------------------

    @app_commands.command(
        name="morning-brief",
        description="Daily morning briefing: Opportunities, Viral, Niches, Profit",
    )
    @app_commands.describe(top="Items per section (default 5)")
    async def cmd_morning_brief(
        self,
        interaction: discord.Interaction,
        top: int = 5,
    ) -> None:
        from discord_bot.config import CHANNEL_MORNING_BRIEF
        await interaction.response.defer()
        result = get_morning_brief(top=top)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        embeds = build_morning_brief_embeds(result["data"])
        await send_and_confirm(interaction, embeds, CHANNEL_MORNING_BRIEF)

    # ------------------------------------------------------------------
    # /executive-summary
    # ------------------------------------------------------------------

    @app_commands.command(
        name="executive-summary",
        description="Full executive summary: Opportunities, Risks, Gaps, Viral, Profit",
    )
    async def cmd_executive_summary(self, interaction: discord.Interaction) -> None:
        from discord_bot.config import CHANNEL_REVENUE
        await interaction.response.defer()
        result = get_executive_summary()
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        embeds = build_executive_summary_embeds(result["data"])
        await send_and_confirm(interaction, embeds, CHANNEL_REVENUE)
