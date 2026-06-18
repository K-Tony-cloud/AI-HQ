"""Facebook Insights + Content Performance commands."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import error_embed
from discord_bot.embeds.insights_embeds import (
    build_content_recommendation_embed,
    build_facebook_queue_embeds,
    build_last30_embed,
    build_page_insights_embed,
    build_posts_embed,
    build_scheduled_posts_embed,
    build_top_posts_embed,
)

logger = logging.getLogger(__name__)


class InsightsCog(commands.Cog, name="Insights"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /insights-page ────────────────────────────────────────────────────────

    @app_commands.command(
        name="insights-page",
        description="Show page-level Facebook insights for the last 30 days",
    )
    async def cmd_insights_page(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_get_page_insights

            data  = await asyncio.to_thread(fb_get_page_insights)
            embed = build_page_insights_embed(data)
            await interaction.followup.send(embed=embed)
            logger.info("[InsightsCog] /insights-page by %s", interaction.user)
        except Exception as exc:
            logger.error("[InsightsCog] /insights-page error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /insights-posts ───────────────────────────────────────────────────────

    @app_commands.command(
        name="insights-posts",
        description="Show recent Facebook posts with reach, reactions, and engagement metrics",
    )
    @app_commands.describe(limit="Number of posts to show (1–15, default 5)")
    async def cmd_insights_posts(
        self,
        interaction: discord.Interaction,
        limit: int = 5,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_get_posts

            limit = max(1, min(limit, 15))
            posts = await asyncio.to_thread(fb_get_posts, limit)
            embed = build_posts_embed(posts)
            await interaction.followup.send(embed=embed)
            logger.info("[InsightsCog] /insights-posts by %s limit=%d", interaction.user, limit)
        except Exception as exc:
            logger.error("[InsightsCog] /insights-posts error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /insights-top ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="insights-top",
        description="Show top-performing Facebook posts ranked by a metric",
    )
    @app_commands.describe(
        metric="Ranking metric",
        limit="Number of posts to return (1–10, default 5)",
    )
    @app_commands.choices(metric=[
        app_commands.Choice(name="Score (combined)",    value="score"),
        app_commands.Choice(name="Reach",               value="reach"),
        app_commands.Choice(name="Reactions",           value="reactions"),
        app_commands.Choice(name="Comments",            value="comments"),
        app_commands.Choice(name="Shares",              value="shares"),
        app_commands.Choice(name="Engagement Rate",     value="engagement_rate"),
    ])
    async def cmd_insights_top(
        self,
        interaction: discord.Interaction,
        metric: str = "score",
        limit: int = 5,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_get_top_posts

            limit = max(1, min(limit, 10))
            posts = await asyncio.to_thread(fb_get_top_posts, metric, limit)
            embed = build_top_posts_embed(posts, metric)
            await interaction.followup.send(embed=embed)
            logger.info(
                "[InsightsCog] /insights-top by %s metric=%s limit=%d",
                interaction.user, metric, limit,
            )
        except Exception as exc:
            logger.error("[InsightsCog] /insights-top error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /insights-last30 ──────────────────────────────────────────────────────

    @app_commands.command(
        name="insights-last30",
        description="30-day summary: page insights, post count, and top performing post",
    )
    async def cmd_insights_last30(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_get_last_30_days

            data  = await asyncio.to_thread(fb_get_last_30_days)
            embed = build_last30_embed(data)
            await interaction.followup.send(embed=embed)
            logger.info("[InsightsCog] /insights-last30 by %s", interaction.user)
        except Exception as exc:
            logger.error("[InsightsCog] /insights-last30 error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /content-next ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="content-next",
        description="Recommend the best content type, posting time, and hook for your next Facebook post",
    )
    async def cmd_content_next(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import get_content_recommendation

            data  = await asyncio.to_thread(get_content_recommendation)
            embed = build_content_recommendation_embed(data)
            await interaction.followup.send(embed=embed)
            logger.info("[InsightsCog] /content-next by %s", interaction.user)
        except Exception as exc:
            logger.error("[InsightsCog] /content-next error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-scheduled ───────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-scheduled",
        description="List all pending scheduled Facebook posts",
    )
    async def cmd_facebook_scheduled(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_get_scheduled_posts

            posts = await asyncio.to_thread(fb_get_scheduled_posts)
            embed = build_scheduled_posts_embed(posts)
            await interaction.followup.send(embed=embed)
            logger.info("[InsightsCog] /facebook-scheduled by %s", interaction.user)
        except Exception as exc:
            logger.error("[InsightsCog] /facebook-scheduled error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-queue ───────────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-queue",
        description="Inspect queued posts — caption, hook, CTA, quality score, humanized",
    )
    async def cmd_facebook_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_get_scheduled_posts

            posts  = await asyncio.to_thread(fb_get_scheduled_posts)
            embeds = build_facebook_queue_embeds(posts)
            # Discord allows max 10 embeds per message — send summary + up to 9 post embeds
            await interaction.followup.send(embeds=embeds[:10])
            logger.info("[InsightsCog] /facebook-queue by %s — %d posts", interaction.user, len(posts))
        except Exception as exc:
            logger.error("[InsightsCog] /facebook-queue error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
