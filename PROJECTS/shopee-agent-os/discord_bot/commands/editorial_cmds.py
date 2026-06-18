"""Editorial System commands — /today-content."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed
from discord_bot.embeds.editorial_embeds import build_today_content_embeds

logger = logging.getLogger(__name__)


class EditorialCog(commands.Cog, name="Editorial"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="today-content",
        description="Generate today's complete Facebook editorial plan — ready-to-publish posts, schedule, and reasoning",
    )
    async def cmd_today_content(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.editorial_engine import generate_today_content

            data   = await asyncio.to_thread(generate_today_content)
            embeds = build_today_content_embeds(data)

            if not embeds:
                await interaction.followup.send(embed=error_embed("No content generated"))
                return

            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                view = PaginatedView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)

            override = data.get("override_active", False)
            logger.info(
                "[EditorialCog] /today-content by %s — %d posts, override=%s",
                interaction.user, len(data.get("posts", [])), override,
            )
        except Exception as exc:
            logger.error("[EditorialCog] /today-content error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
