"""Slash commands: /content-pack, /queue, /approve, content intelligence phase"""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, make_embed, send_and_confirm
from discord_bot.embeds.content_embeds import (
    build_approve_embed,
    build_content_calendar_embed,
    build_content_mix_embed,
    build_content_pack_embeds,
    build_content_picks_embed,
    build_engagement_post_embed,
    build_facebook_post_embed,
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
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        await interaction.response.defer()
        result = generate_content_pack(keyword=keyword)
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        embeds = build_content_pack_embeds(result["data"])
        await send_and_confirm(interaction, embeds, CHANNEL_CONTENT_QUEUE)

    # ------------------------------------------------------------------
    # /queue
    # ------------------------------------------------------------------

    @app_commands.command(
        name="queue",
        description="Show all items in the content queue",
    )
    async def cmd_queue(self, interaction: discord.Interaction) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        await interaction.response.defer()
        result = get_queue()
        if not result["success"]:
            await interaction.followup.send(embed=error_embed(result["error"]))
            return

        pages = build_queue_pages(result["data"])
        await send_and_confirm(interaction, pages, CHANNEL_CONTENT_QUEUE)

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
        from discord_bot.config import CHANNEL_APPROVED_CONTENT
        await interaction.response.defer()
        result = approve_queue_item(id)
        embed = build_approve_embed(id, result.get("success", False))
        await send_and_confirm(interaction, [embed], CHANNEL_APPROVED_CONTENT)

    # ------------------------------------------------------------------
    # /content-picks
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-picks",
        description="Find best products to feature today based on real commission data",
    )
    @app_commands.describe(top_n="Number of products (default 5)")
    async def cmd_content_picks(
        self,
        interaction: discord.Interaction,
        top_n: int = 5,
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import get_content_picks
        await interaction.response.defer(thinking=True)
        try:
            items = await asyncio.to_thread(get_content_picks, top_n)
            embed = build_content_picks_embed(items)
            await send_and_confirm(interaction, [embed], CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /content-post
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-post",
        description="Generate a Facebook post in อะไรของมัน voice for a product",
    )
    @app_commands.describe(keyword="Product keyword")
    async def cmd_content_post(
        self,
        interaction: discord.Interaction,
        keyword: str,
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import (
            generate_facebook_product_post,
            lookup_product,
        )
        await interaction.response.defer(thinking=True)
        try:
            product = await asyncio.to_thread(lookup_product, keyword)
            data    = await asyncio.to_thread(generate_facebook_product_post, product)
            embed   = build_facebook_post_embed(data)
            await send_and_confirm(interaction, [embed], CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /content-reel
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-reel",
        description="Generate Facebook Reel script for a product",
    )
    @app_commands.describe(keyword="Product keyword", length="Script length")
    @app_commands.choices(length=[
        Choice(name="15 seconds", value="15s"),
        Choice(name="30 seconds", value="30s"),
        Choice(name="60 seconds", value="60s"),
    ])
    async def cmd_content_reel(
        self,
        interaction: discord.Interaction,
        keyword: str,
        length: str = "30s",
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import generate_script
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(generate_script, keyword)
            script_text = result.get("scripts", {}).get(length, "")
            product     = result.get("product", {})
            name        = str(product.get("title", keyword))[:60]
            provider    = result.get("provider", "template")
            embed = make_embed(
                title=f"🎬 Reel Script ({length}) — {name}",
                color_key="content",
                description=f"`provider: {provider}`",
            )
            if script_text:
                embed.add_field(name=f"📋 Script ({length})", value=str(script_text)[:1000], inline=False)
            await send_and_confirm(interaction, [embed], CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /content-hook
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-hook",
        description="Generate 5 viral engagement hooks for the page (no product needed)",
    )
    @app_commands.describe(type="Hook type")
    @app_commands.choices(type=[
        Choice(name="Comment Bait",       value="comment_bait"),
        Choice(name="Nostalgia",          value="nostalgia"),
        Choice(name="Visual Curiosity",   value="visual_curiosity"),
        Choice(name="Weird Product",      value="weird_product"),
        Choice(name="Trending Discussion", value="trending"),
    ])
    async def cmd_content_hook(
        self,
        interaction: discord.Interaction,
        type: str = "comment_bait",
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import _ENGAGEMENT_TEMPLATES
        await interaction.response.defer(thinking=True)
        try:
            templates = _ENGAGEMENT_TEMPLATES.get(type, _ENGAGEMENT_TEMPLATES["comment_bait"])
            embed = make_embed(
                title=f"🎣 Engagement Hooks — {type.replace('_', ' ').title()}",
                color_key="opportunity",
                description=f"Template hooks for **{type}** posts",
            )
            for i, t in enumerate(templates, 1):
                hook    = str(t.get("hook", ""))[:300]
                caption = str(t.get("caption", ""))[:200]
                cta     = str(t.get("cta", ""))[:100]
                embed.add_field(
                    name=f"Hook #{i}",
                    value=f"**Hook:** {hook}\n**Caption:** {caption}\n**CTA:** {cta}",
                    inline=False,
                )
            await send_and_confirm(interaction, [embed], CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /content-calendar
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-calendar",
        description="Build 7-day posting calendar with 70/20/10 content mix",
    )
    @app_commands.describe(days="Number of days (default 7, max 14)")
    async def cmd_content_calendar(
        self,
        interaction: discord.Interaction,
        days: int = 7,
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import generate_content_calendar
        await interaction.response.defer(thinking=True)
        try:
            days    = min(days, 14)
            cal     = await asyncio.to_thread(generate_content_calendar, days)
            embed   = build_content_calendar_embed(cal)
            await send_and_confirm(interaction, [embed], CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /content-trending
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-trending",
        description="Generate engagement posts — no selling, just audience building",
    )
    @app_commands.describe(type="Engagement type")
    @app_commands.choices(type=[
        Choice(name="Comment Bait",        value="comment_bait"),
        Choice(name="Nostalgia",           value="nostalgia"),
        Choice(name="Visual Curiosity",    value="visual_curiosity"),
        Choice(name="Weird Product",       value="weird_product"),
        Choice(name="Trending Discussion", value="trending"),
    ])
    async def cmd_content_trending(
        self,
        interaction: discord.Interaction,
        type: str = "trending",
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import generate_engagement_post
        await interaction.response.defer(thinking=True)
        try:
            data  = await asyncio.to_thread(generate_engagement_post, type)
            embed = build_engagement_post_embed(data)
            await send_and_confirm(interaction, [embed], CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /content-mix
    # ------------------------------------------------------------------

    @app_commands.command(
        name="content-mix",
        description="Generate today's full content package: viral + product + soft affiliate",
    )
    async def cmd_content_mix(
        self,
        interaction: discord.Interaction,
    ) -> None:
        from discord_bot.config import CHANNEL_CONTENT_QUEUE
        from shopee_engine.content_engine import generate_content_mix, get_content_picks
        await interaction.response.defer(thinking=True)
        try:
            picks  = await asyncio.to_thread(get_content_picks, 5)
            data   = await asyncio.to_thread(generate_content_mix, picks if picks else None)
            embeds = build_content_mix_embed(data)
            await send_and_confirm(interaction, embeds, CHANNEL_CONTENT_QUEUE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))
