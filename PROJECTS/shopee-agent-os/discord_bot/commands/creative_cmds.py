"""Phase 10 — AI Creative Factory slash commands."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, make_embed
from discord_bot.embeds.creative_embeds import (
    build_approve_embed,
    build_creative_list_embeds,
    build_creative_pack_embeds,
)

logger = logging.getLogger(__name__)

_PLATFORM_CHOICES = [
    app_commands.Choice(name="Universal (Facebook + TikTok)", value="universal"),
    app_commands.Choice(name="Facebook",                       value="facebook"),
    app_commands.Choice(name="TikTok",                         value="tiktok"),
    app_commands.Choice(name="Instagram Reels",                value="reels"),
]

_STATUS_CHOICES = [
    app_commands.Choice(name="All",      value="all"),
    app_commands.Choice(name="Draft",    value="draft"),
    app_commands.Choice(name="Approved", value="approved"),
    app_commands.Choice(name="Rejected", value="rejected"),
]


class CreativeCog(commands.Cog):
    """AI Creative Factory — generate, review, and approve creative packs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /creative-pack ────────────────────────────────────────────────────────

    @app_commands.command(
        name="creative-pack",
        description="Generate a full creative pack (captions, hooks, image/video prompts) for a product",
    )
    @app_commands.describe(
        keyword="Product keyword to search (e.g. garnier, ไม้แขวน, dr.pong)",
        platform="Target platform for the creative",
    )
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    async def cmd_creative_pack(
        self,
        interaction: discord.Interaction,
        keyword: str,
        platform: str = "universal",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.creative_engine import (
                generate_creative_pack,
                search_products_for_creative,
            )

            products = await asyncio.to_thread(search_products_for_creative, keyword)

            if not products:
                await interaction.followup.send(
                    embed=make_embed(
                        "⚠️ No Products Found",
                        color_key="error",
                        description=(
                            f"No affiliate products found matching **{keyword}**.\n\n"
                            "Make sure the product:\n"
                            "• Is in `affiliate_products` table\n"
                            "• Has an `affiliate_short_url` set\n\n"
                            "Use `/affiliate-product-add` to add products first."
                        ),
                    )
                )
                return

            product = products[0]
            multi   = len(products) > 1

            result = await asyncio.to_thread(
                generate_creative_pack,
                product["itemid"],
                product["shopid"],
                platform,
            )

            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            embeds = build_creative_pack_embeds(result)

            # Send to #content-factory channel
            from discord_bot.config import CHANNEL_CONTENT_QUEUE
            channel_id = CHANNEL_CONTENT_QUEUE

            if channel_id:
                try:
                    ch = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                    for embed in embeds:
                        await ch.send(embed=embed)
                    cid = result["creative_id"]
                    note = (
                        f"✅ Creative Pack **#{cid}** sent to <#{channel_id}>\n"
                        f"Product: **{(product.get('title') or '')[:60]}**\n"
                        f"Platform: `{platform}` | AI: {'✅' if result.get('used_ai') else '📋 template'}\n"
                    )
                    if multi:
                        note += f"_({len(products)-1} other matches found — showing top result by sales)_"
                    await interaction.followup.send(note, ephemeral=True)
                    return
                except Exception:
                    pass

            # Fallback: reply in-place
            view = PaginatedView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as exc:
            logger.error("cmd_creative_pack: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /creative-image-prompt ────────────────────────────────────────────────

    @app_commands.command(
        name="creative-image-prompt",
        description="Generate image prompts (1:1, 4:5, 9:16) for a product",
    )
    @app_commands.describe(keyword="Product keyword to search")
    async def cmd_creative_image_prompt(
        self,
        interaction: discord.Interaction,
        keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.creative_engine import (
                generate_creative_pack,
                search_products_for_creative,
            )

            products = await asyncio.to_thread(search_products_for_creative, keyword)
            if not products:
                await interaction.followup.send(
                    embed=error_embed(f"No affiliate products found for keyword: **{keyword}**")
                )
                return

            product = products[0]
            result  = await asyncio.to_thread(
                generate_creative_pack, product["itemid"], product["shopid"], "universal"
            )
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            creative = result["creative"]
            img      = creative.get("image_prompt") or {}
            title    = (product.get("title") or "")[:60]
            cid      = result["creative_id"]

            e = make_embed(
                f"🖼️ Image Prompts — {title}",
                color_key="niche",
                description=(
                    f"Creative **#{cid}** | Platform: Universal\n"
                    f"Affiliate: {product.get('affiliate_short_url','')}\n\n"
                    "Paste prompts into **Midjourney**, **DALL-E**, or **Ideogram**."
                ),
            )
            e.add_field(
                name="1:1 — Facebook Feed",
                value=(img.get("1_1") or "—")[:1024],
                inline=False,
            )
            e.add_field(
                name="4:5 — Facebook Ad",
                value=(img.get("4_5") or "—")[:1024],
                inline=False,
            )
            e.add_field(
                name="9:16 — TikTok / Reels",
                value=(img.get("9_16") or "—")[:1024],
                inline=False,
            )
            e.add_field(
                name="AI Generated",
                value="✅ Claude AI" if result.get("used_ai") else "📋 Template",
                inline=True,
            )
            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_creative_image_prompt: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /creative-video-prompt ────────────────────────────────────────────────

    @app_commands.command(
        name="creative-video-prompt",
        description="Generate video storyboard (5s / 10s / 15s) for a product",
    )
    @app_commands.describe(keyword="Product keyword to search")
    async def cmd_creative_video_prompt(
        self,
        interaction: discord.Interaction,
        keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.creative_engine import (
                generate_creative_pack,
                search_products_for_creative,
            )

            products = await asyncio.to_thread(search_products_for_creative, keyword)
            if not products:
                await interaction.followup.send(
                    embed=error_embed(f"No affiliate products found for keyword: **{keyword}**")
                )
                return

            product = products[0]
            result  = await asyncio.to_thread(
                generate_creative_pack, product["itemid"], product["shopid"], "universal"
            )
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            creative = result["creative"]
            vp       = creative.get("video_prompt") or {}
            vs       = creative.get("voice_script") or {}
            title    = (product.get("title") or "")[:55]
            cid      = result["creative_id"]

            def _scene_lines(data: dict) -> str:
                scenes = data.get("scenes") or []
                lines  = []
                for s in scenes:
                    cta_line = f" → `{s['cta']}`" if s.get("cta") else ""
                    lines.append(
                        f"**[{s.get('sec','')}]** {s.get('scene','')}\n"
                        f"Text: `{s.get('text','')}`{cta_line}"
                    )
                return "\n".join(lines)

            embeds: list[discord.Embed] = []

            # Embed 1: 5s + 10s
            e1 = make_embed(f"🎬 Video Storyboard — {title}", color_key="trend")
            v5 = vp.get("5s") or {}
            e1.add_field(
                name="⚡ 5-Second Cut",
                value=(
                    f"**Scene:** {v5.get('scene','—')[:200]}\n"
                    f"**Text:** `{v5.get('on_screen_text','—')[:80]}`\n"
                    f"**Voice:** {v5.get('voice_over','—')[:200]}\n"
                    f"**Music:** {v5.get('music_sfx','—')[:100]}"
                )[:1024],
                inline=False,
            )
            v10 = vp.get("10s") or {}
            v10_body = (
                _scene_lines(v10)
                + f"\n\n**Voice:** {v10.get('voice_over','—')[:300]}\n"
                f"**Music:** {v10.get('music_sfx','—')[:100]}"
            )
            e1.add_field(name="🎬 10-Second Cut", value=v10_body[:1024] or "—", inline=False)
            embeds.append(e1)

            # Embed 2: 15s + voice scripts
            e2 = make_embed("🎥 15-Second Cut + Voice-Over Scripts", color_key="profit")
            v15 = vp.get("15s") or {}
            v15_body = (
                _scene_lines(v15)
                + f"\n\n**Voice:** {v15.get('voice_over','—')[:300]}\n"
                f"**Music:** {v15.get('music_sfx','—')[:100]}"
            )
            e2.add_field(name="🎥 15-Second Cut", value=v15_body[:1024] or "—", inline=False)
            e2.add_field(name="🎙️ Voice (5s)",   value=(vs.get("5s") or "—")[:512],  inline=False)
            e2.add_field(name="🎙️ Voice (10s)",  value=(vs.get("10s") or "—")[:512], inline=False)
            e2.add_field(name="🎙️ Voice (15s)",  value=(vs.get("15s") or "—")[:512], inline=False)
            e2.add_field(
                name="Creative ID",
                value=f"`#{cid}` | AI: {'✅ Claude' if result.get('used_ai') else '📋 template'}",
                inline=False,
            )
            embeds.append(e2)

            view = PaginatedView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as exc:
            logger.error("cmd_creative_video_prompt: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /creative-approve ─────────────────────────────────────────────────────

    @app_commands.command(
        name="creative-approve",
        description="Approve a creative pack (moves to approved status)",
    )
    @app_commands.describe(creative_id="Creative ID (from /creative-list or the pack header)")
    async def cmd_creative_approve(
        self,
        interaction: discord.Interaction,
        creative_id: int,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.creative_engine import approve_creative, get_creative_by_id

            data   = await asyncio.to_thread(get_creative_by_id, creative_id)
            result = await asyncio.to_thread(approve_creative, creative_id)

            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            title = (data or {}).get("title", "") or ""
            embed = build_approve_embed(creative_id, "approved", title)

            # Echo to approved-content channel
            from discord_bot.config import CHANNEL_APPROVED_CONTENT
            if CHANNEL_APPROVED_CONTENT and data:
                try:
                    ch = (
                        self.bot.get_channel(CHANNEL_APPROVED_CONTENT)
                        or await self.bot.fetch_channel(CHANNEL_APPROVED_CONTENT)
                    )
                    short_url = data.get("affiliate_short_url", "")
                    caps      = data.get("caption_facebook") or data.get("caption_tiktok") or ""
                    announce  = make_embed(
                        f"✅ Approved Creative #{creative_id}",
                        color_key="success",
                        description=f"**{title[:80]}**\n\n{caps[:800]}",
                    )
                    announce.add_field(name="Affiliate Link", value=short_url, inline=False)
                    announce.add_field(name="Platform", value=data.get("platform", "—"), inline=True)
                    await ch.send(embed=announce)
                except Exception:
                    pass

            await interaction.followup.send(embed=embed)

        except Exception as exc:
            logger.error("cmd_creative_approve: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /creative-reject ──────────────────────────────────────────────────────

    @app_commands.command(
        name="creative-reject",
        description="Reject a creative pack",
    )
    @app_commands.describe(creative_id="Creative ID to reject")
    async def cmd_creative_reject(
        self,
        interaction: discord.Interaction,
        creative_id: int,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.creative_engine import get_creative_by_id, reject_creative

            data   = await asyncio.to_thread(get_creative_by_id, creative_id)
            result = await asyncio.to_thread(reject_creative, creative_id)

            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            title = (data or {}).get("title", "") or ""
            await interaction.followup.send(
                embed=build_approve_embed(creative_id, "rejected", title)
            )

        except Exception as exc:
            logger.error("cmd_creative_reject: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /creative-list ────────────────────────────────────────────────────────

    @app_commands.command(
        name="creative-list",
        description="List creative assets by status",
    )
    @app_commands.describe(status="Filter by status")
    @app_commands.choices(status=_STATUS_CHOICES)
    async def cmd_creative_list(
        self,
        interaction: discord.Interaction,
        status: str = "all",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.creative_engine import get_creative_list

            items  = await asyncio.to_thread(get_creative_list, status, 40)
            embeds = build_creative_list_embeds(items)

            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                view = PaginatedView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as exc:
            logger.error("cmd_creative_list: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
