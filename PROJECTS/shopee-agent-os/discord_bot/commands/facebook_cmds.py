"""Facebook integration commands — manual page management for อะไรของมัน."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import error_embed
from discord_bot.embeds.facebook_embeds import (
    build_fb_debug_embed,
    build_fb_draft_saved_embed,
    build_fb_drafts_list_embed,
    build_fb_page_info_embed,
    build_fb_post_result_embed,
    build_fb_schedule_embed,
)

logger = logging.getLogger(__name__)


class FacebookCog(commands.Cog, name="Facebook"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /facebook-test ────────────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-test",
        description="Test Facebook page connection — show page name, ID, and follower count",
    )
    async def cmd_facebook_test(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.facebook_engine import fb_get_page_info

            data  = await asyncio.to_thread(fb_get_page_info)
            embed = build_fb_page_info_embed(data)
            await interaction.followup.send(embed=embed)
            logger.info("[FacebookCog] /facebook-test by %s", interaction.user)
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-test error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-post-test ───────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-post-test",
        description="Publish a simple test post to อะไรของมัน page (manual only)",
    )
    @app_commands.describe(
        message="Message to post (leave blank for default test message)"
    )
    async def cmd_facebook_post_test(
        self,
        interaction: discord.Interaction,
        message: str = "",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.facebook_engine import fb_post_message

            if not message.strip():
                message = (
                    "สวัสดีครับ 👋\n\n"
                    "เพจ อะไรของมัน พร้อมแล้ว! 🎉\n\n"
                    "เร็วๆ นี้จะมีของแปลก ของน่าสนใจ และคำถามสนุกๆ มาให้ comment กัน\n\n"
                    "กด Like เพื่อไม่พลาดนะครับ 🛒"
                )

            result = await asyncio.to_thread(fb_post_message, message)
            embed  = build_fb_post_result_embed(result, message)
            await interaction.followup.send(embed=embed)
            logger.info(
                "[FacebookCog] /facebook-post-test by %s — success=%s post_id=%s",
                interaction.user, result.get("success"), result.get("post_id"),
            )
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-post-test error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-draft ───────────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-draft",
        description="Save a Facebook post draft for review before publishing",
    )
    @app_commands.describe(
        message="Post content to save as draft",
        post_type="Content type tag",
        note="Optional note for yourself",
    )
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Comment Bait",     value="comment_bait"),
        app_commands.Choice(name="Weird Product",    value="weird_product"),
        app_commands.Choice(name="Nostalgia",        value="nostalgia"),
        app_commands.Choice(name="Visual Curiosity", value="visual_curiosity"),
        app_commands.Choice(name="Trending",         value="trending"),
        app_commands.Choice(name="Affiliate",        value="affiliate"),
        app_commands.Choice(name="Manual",           value="manual"),
    ])
    async def cmd_facebook_draft(
        self,
        interaction: discord.Interaction,
        message: str,
        post_type: str = "manual",
        note: str = "",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.facebook_engine import fb_save_draft

            result = await asyncio.to_thread(fb_save_draft, message, post_type, note)
            embed  = build_fb_draft_saved_embed(result, message)
            await interaction.followup.send(embed=embed)
            logger.info(
                "[FacebookCog] /facebook-draft by %s — id=%s type=%s",
                interaction.user, result.get("id"), post_type,
            )
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-draft error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-debug ───────────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-debug",
        description="Full Facebook token/page diagnostic — shows raw API responses and exact errors",
    )
    async def cmd_facebook_debug(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            from shopee_engine.facebook_engine import fb_debug

            data  = await asyncio.to_thread(fb_debug)
            embed = build_fb_debug_embed(data)
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info("[FacebookCog] /facebook-debug by %s", interaction.user)
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-debug error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ── /facebook-post ────────────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-post",
        description="Publish a post to อะไรของมัน Facebook page immediately",
    )
    @app_commands.describe(
        message="Post content",
        link="Optional URL to attach",
    )
    async def cmd_facebook_post(
        self,
        interaction: discord.Interaction,
        message: str,
        link: str = "",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.facebook_engine import fb_post_message

            result = await asyncio.to_thread(fb_post_message, message, link)
            embed  = build_fb_post_result_embed(result, message)
            await interaction.followup.send(embed=embed)
            logger.info(
                "[FacebookCog] /facebook-post by %s — success=%s post_id=%s",
                interaction.user, result.get("success"), result.get("post_id"),
            )
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-post error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-post-image ──────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-post-image",
        description="Publish a photo post with caption to อะไรของมัน page",
    )
    @app_commands.describe(
        message="Caption for the image",
        image_url="Public URL of the image (must be accessible by Facebook)",
    )
    async def cmd_facebook_post_image(
        self,
        interaction: discord.Interaction,
        message: str,
        image_url: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_post_with_image

            result = await asyncio.to_thread(fb_post_with_image, message, image_url)
            embed  = build_fb_post_result_embed(result, message)
            await interaction.followup.send(embed=embed)
            logger.info(
                "[FacebookCog] /facebook-post-image by %s — success=%s post_id=%s",
                interaction.user, result.get("success"), result.get("post_id"),
            )
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-post-image error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /facebook-schedule ────────────────────────────────────────────────────

    @app_commands.command(
        name="facebook-schedule",
        description="Queue a Facebook post for future publishing (manual approval required)",
    )
    @app_commands.describe(
        message="Post content",
        publish_at="Publish date and time (YYYY-MM-DD HH:MM, Bangkok time)",
        post_type="Content type tag",
        note="Optional note for yourself",
    )
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Comment Bait",     value="comment_bait"),
        app_commands.Choice(name="Weird Product",    value="weird_product"),
        app_commands.Choice(name="Nostalgia",        value="nostalgia"),
        app_commands.Choice(name="Visual Curiosity", value="visual_curiosity"),
        app_commands.Choice(name="Trending",         value="trending"),
        app_commands.Choice(name="Affiliate",        value="affiliate"),
        app_commands.Choice(name="Manual",           value="manual"),
    ])
    async def cmd_facebook_schedule(
        self,
        interaction: discord.Interaction,
        message: str,
        publish_at: str,
        post_type: str = "manual",
        note: str = "",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.insights_engine import fb_schedule_post

            result = await asyncio.to_thread(
                fb_schedule_post, message, publish_at, post_type, "", "", note
            )
            embed  = build_fb_schedule_embed(result, message, publish_at)
            await interaction.followup.send(embed=embed)
            logger.info(
                "[FacebookCog] /facebook-schedule by %s — id=%s publish_at=%s",
                interaction.user, result.get("id"), publish_at,
            )
        except Exception as exc:
            logger.error("[FacebookCog] /facebook-schedule error: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
