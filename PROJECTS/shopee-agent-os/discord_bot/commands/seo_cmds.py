"""Slash commands: /seo-ideas, /seo-draft, /seo-preview, /seo-list"""

from __future__ import annotations

import asyncio
import io

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from discord_bot.embeds.base import error_embed, send_and_confirm
from discord_bot.embeds.seo_embeds import (
    build_draft_duplicate_embed,
    build_draft_embed,
    build_ideas_embed,
    build_list_embed,
    build_preview_embed,
    build_publish_embed,
    build_publish_failed_embed,
    build_refresh_embed,
    build_review_blocked_embed,
    build_review_embed,
    build_unpublish_embed,
)
from discord_bot.services import seo_service


_CATEGORY_CHOICES = [
    Choice(name="บ้านและครัว",        value="Home & Living"),
    Choice(name="มือถือ & แกดเจ็ต",   value="Mobile & Gadgets"),
    Choice(name="ความงาม",            value="Beauty"),
    Choice(name="สุขภาพ",             value="Health"),
    Choice(name="แม่และเด็ก",         value="Mom & Baby"),
    Choice(name="กีฬา",               value="Sports & Outdoors"),
    Choice(name="อาหาร & เครื่องดื่ม", value="Food & Beverages"),
]


class SeoCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /seo-ideas
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-ideas",
        description="Show keyword opportunities for SEO article writing",
    )
    @app_commands.describe(
        category="กรอง keyword ตามหมวดสินค้า (optional)",
        limit="จำนวน keyword ที่แสดง (1-20, default 10)",
    )
    @app_commands.choices(category=_CATEGORY_CHOICES)
    async def cmd_seo_ideas(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        limit: int = 10,
    ) -> None:
        from discord_bot.config import CHANNEL_SEO_ARTICLES
        await interaction.response.defer(thinking=True)
        limit = max(1, min(20, limit))
        try:
            result = await asyncio.to_thread(
                seo_service.get_keyword_opportunities, category, limit
            )
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return
            embed = build_ideas_embed(result["data"], category, limit)
            await send_and_confirm(interaction, [embed], CHANNEL_SEO_ARTICLES)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-draft
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-draft",
        description="Generate a new SEO article draft from Shopee product data",
    )
    @app_commands.describe(
        keyword="Keyword หลักของบทความ (required)",
        category="หมวดสินค้าสำหรับกรองข้อมูล (optional)",
        product_count="จำนวนสินค้าในบทความ (3-7, default 5)",
    )
    @app_commands.choices(category=_CATEGORY_CHOICES)
    async def cmd_seo_draft(
        self,
        interaction: discord.Interaction,
        keyword: str,
        category: str | None = None,
        product_count: int = 5,
    ) -> None:
        from discord_bot.config import CHANNEL_SEO_ARTICLES
        await interaction.response.defer(thinking=True)
        product_count = max(3, min(7, product_count))
        try:
            result = await asyncio.to_thread(
                seo_service.create_article_draft, keyword, category, product_count
            )
            if not result.get("success"):
                if result.get("duplicate"):
                    embed = build_draft_duplicate_embed(keyword, {
                        "article_id": result["existing_id"],
                        "status":     result["existing_status"],
                        "updated_at": result.get("existing_updated", ""),
                    })
                else:
                    embed = error_embed(result.get("error", "Unknown error"))
                await interaction.followup.send(embed=embed)
                return
            embed = build_draft_embed(result)
            await send_and_confirm(interaction, [embed], CHANNEL_SEO_ARTICLES)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-preview
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-preview",
        description="Preview an SEO article (never changes status)",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการดู")
    async def cmd_seo_preview(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.preview_article, article_id)
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return
            embed = build_preview_embed(result)
            content_md = str(result["article"].get("content_md", ""))
            if len(content_md) > 1800:
                f = discord.File(
                    io.BytesIO(content_md.encode("utf-8")),
                    filename=f"{article_id}.md",
                )
                await interaction.followup.send(embed=embed, file=f)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-list
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # /seo-review
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-review",
        description="Approve or return a draft article for editorial review",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการ review",
        action="approve = draft→reviewed | return_to_draft = reviewed→draft",
        note="หมายเหตุ (optional)",
    )
    @app_commands.choices(action=[
        Choice(name="✅ Approve (draft → reviewed)", value="approve"),
        Choice(name="↩️ Return to Draft",            value="return_to_draft"),
    ])
    async def cmd_seo_review(
        self,
        interaction: discord.Interaction,
        article_id: str,
        action: str,
        note: str = "",
    ) -> None:
        from discord_bot.config import CHANNEL_SEO_ARTICLES
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(
                seo_service.review_article_action, article_id, action, note
            )
            if not result.get("success"):
                if result.get("blocked"):
                    embed = build_review_blocked_embed({**result, "article_id": article_id})
                else:
                    from discord_bot.embeds.base import error_embed as _err
                    embed = _err(result.get("error", "Unknown error"))
                await interaction.followup.send(embed=embed)
                return
            embed = build_review_embed(result)
            await send_and_confirm(interaction, [embed], CHANNEL_SEO_ARTICLES)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-publish
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-publish",
        description="Validate, build, and publish a reviewed SEO article",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการ publish (ต้องมี status reviewed)")
    async def cmd_seo_publish(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.publish_article, article_id)
            if not result.get("success"):
                embed = build_publish_failed_embed(result)
            else:
                embed = build_publish_embed(result)
            # Path/git/env details are ephemeral
            await interaction.followup.send(embed=embed, ephemeral=not result.get("success") is False)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ------------------------------------------------------------------
    # /seo-refresh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-refresh",
        description="Sync article product prices, images, and affiliate links from DB",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการ refresh สินค้า")
    async def cmd_seo_refresh(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.refresh_article, article_id)
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Refresh failed")))
                return
            embed = build_refresh_embed(result)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-unpublish
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-unpublish",
        description="Remove a published article from the site (published → reviewed)",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการ unpublish")
    async def cmd_seo_unpublish(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.unpublish_article, article_id)
            if not result.get("success"):
                embed = build_publish_failed_embed({**result, "article_id": article_id})
            else:
                embed = build_unpublish_embed(result)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ------------------------------------------------------------------
    # /seo-list
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-list",
        description="List SEO articles, newest first",
    )
    @app_commands.describe(
        status="กรองตาม status (default: ทั้งหมด)",
        limit="จำนวนบทความที่แสดง (1-25, default 10)",
    )
    @app_commands.choices(status=[
        Choice(name="ทั้งหมด",  value="all"),
        Choice(name="Draft",    value="draft"),
        Choice(name="Reviewed", value="reviewed"),
        Choice(name="Published", value="published"),
        Choice(name="Archived", value="archived"),
    ])
    async def cmd_seo_list(
        self,
        interaction: discord.Interaction,
        status: str = "all",
        limit: int = 10,
    ) -> None:
        await interaction.response.defer(thinking=True)
        limit = max(1, min(25, limit))
        status_filter = None if status == "all" else status
        try:
            result = await asyncio.to_thread(
                seo_service.list_seo_articles, status_filter, limit
            )
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return
            embed = build_list_embed(result["data"], result["stats"], status_filter, limit)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))
