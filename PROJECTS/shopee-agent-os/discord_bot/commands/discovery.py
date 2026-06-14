"""Slash commands: /daily-picks, /top-opportunities, /top-viral, /find-product"""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, send_and_confirm
from discord_bot.embeds.discovery_embeds import (
    build_daily_picks_embed,
    build_find_product_embed,
    build_top_opportunities_pages,
    build_top_viral_pages,
)
from discord_bot.services.discovery_service import (
    find_products,
    get_daily_picks,
    get_top_opportunities,
    get_top_viral,
)


class DiscoveryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /daily-picks
    # ------------------------------------------------------------------

    @app_commands.command(
        name="daily-picks",
        description="Daily product briefing: Top Opportunities, Viral, Profit & Daily Picks",
    )
    @app_commands.describe(top="Products per bucket (default 5)")
    async def cmd_daily_picks(
        self,
        interaction: discord.Interaction,
        top: int = 5,
    ) -> None:
        from discord_bot.config import CHANNEL_DAILY_PICKS
        await interaction.response.defer()
        result = get_daily_picks(top=top)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        embeds = build_daily_picks_embed(result["data"])
        await send_and_confirm(interaction, embeds, CHANNEL_DAILY_PICKS)

    # ------------------------------------------------------------------
    # /top-opportunities
    # ------------------------------------------------------------------

    @app_commands.command(
        name="top-opportunities",
        description="Top products ranked by opportunity score",
    )
    @app_commands.describe(
        category="Filter by category name (e.g. Beauty, Health)",
        top="Number of results (default 20)",
    )
    async def cmd_top_opportunities(
        self,
        interaction: discord.Interaction,
        category: Optional[str] = None,
        top: int = 20,
    ) -> None:
        from discord_bot.config import CHANNEL_MORNING_BRIEF
        await interaction.response.defer()
        result = get_top_opportunities(category=category, top=top)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        pages = build_top_opportunities_pages(result["data"], category)
        await send_and_confirm(interaction, pages, CHANNEL_MORNING_BRIEF)

    # ------------------------------------------------------------------
    # /top-viral
    # ------------------------------------------------------------------

    @app_commands.command(
        name="top-viral",
        description="Top viral products for TikTok/Reels content",
    )
    @app_commands.describe(
        category="Filter by category name",
        top="Number of results (default 20)",
    )
    async def cmd_top_viral(
        self,
        interaction: discord.Interaction,
        category: Optional[str] = None,
        top: int = 20,
    ) -> None:
        from discord_bot.config import CHANNEL_DAILY_PICKS
        await interaction.response.defer()
        result = get_top_viral(category=category, top=top)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        pages = build_top_viral_pages(result["data"], category)
        await send_and_confirm(interaction, pages, CHANNEL_DAILY_PICKS)

    # ------------------------------------------------------------------
    # /find-product
    # ------------------------------------------------------------------

    @app_commands.command(
        name="find-product",
        description="Search products by keyword with optional category filter",
    )
    @app_commands.describe(
        keyword="Search keyword (Thai or English)",
        category="Optional category filter",
    )
    async def cmd_find_product(
        self,
        interaction: discord.Interaction,
        keyword: str,
        category: Optional[str] = None,
    ) -> None:
        await interaction.response.defer()
        result = find_products(keyword=keyword, category=category)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        embed = build_find_product_embed(result["data"], keyword)
        await interaction.followup.send(embed=embed)
