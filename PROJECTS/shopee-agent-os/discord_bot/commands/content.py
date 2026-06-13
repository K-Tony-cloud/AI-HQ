"""Slash commands: /content-pack, /queue, /approve"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, make_embed
from discord_bot.embeds.content_embeds import (
    build_approve_embed,
    build_content_pack_embeds,
    build_queue_pages,
)
from discord_bot.services.content_service import (
    approve_queue_item,
    generate_content_pack,
    get_queue,
)


class ContentCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /content-pack
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-pack",
        description="Generate full content pack: Hooks, Captions, Scripts, CTA, Hashtags",
    )
    @app_commands.describe(keyword="Product keyword or name to generate content for")
    async def cmd_content_pack(
        self,
        interaction: discord.Interaction,
        keyword: str,
    ) -> None:
        await interaction.response.defer()
        result = generate_content_pack(keyword=keyword)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        embeds = build_content_pack_embeds(result["data"])
        # Send header embed first, then use pagination for the rest
        await interaction.followup.send(embed=embeds[0])
        if len(embeds) > 1:
            view = PaginatedView(embeds[1:])
            await interaction.followup.send(embed=embeds[1], view=view)

    # ------------------------------------------------------------------
    # /queue
    # ------------------------------------------------------------------

    @app_commands.command(
        name="queue",
        description="Show all items in the content queue",
    )
    async def cmd_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = get_queue()
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        pages = build_queue_pages(result["data"])
        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            view = PaginatedView(pages)
            await interaction.followup.send(embed=pages[0], view=view)

    # ------------------------------------------------------------------
    # /approve
    # ------------------------------------------------------------------

    @app_commands.command(
        name="approve",
        description="Approve a content queue item (draft → approved)",
    )
    @app_commands.describe(id="Queue item ID to approve")
    async def cmd_approve(
        self,
        interaction: discord.Interaction,
        id: int,
    ) -> None:
        await interaction.response.defer()
        result = approve_queue_item(id)
        embed = build_approve_embed(id, result.get("success", False))
        await interaction.followup.send(embed=embed)
