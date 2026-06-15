"""Phase 10.5 — Product Asset Library commands."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import make_embed, error_embed

logger = logging.getLogger(__name__)


class AssetCog(commands.Cog):
    """Product Asset Library — browse and manage product images."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /product-assets ───────────────────────────────────────────────────────

    @app_commands.command(
        name="product-assets",
        description="Show stored image assets for a product",
    )
    @app_commands.describe(keyword="Product name or keyword (e.g. garnier, ไม้แขวน)")
    async def cmd_product_assets(
        self,
        interaction: discord.Interaction,
        keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import search_assets_by_keyword

            items = await asyncio.to_thread(search_assets_by_keyword, keyword)

            if not items:
                # Try to fetch on-demand from products table via affiliate_products
                from shopee_engine.creative_engine import search_products_for_creative
                from shopee_engine.asset_engine import fetch_and_save_product_assets

                products = await asyncio.to_thread(search_products_for_creative, keyword)
                if products:
                    p = products[0]
                    result = await asyncio.to_thread(
                        fetch_and_save_product_assets, p["itemid"], p["shopid"]
                    )
                    if result["success"]:
                        items = await asyncio.to_thread(search_assets_by_keyword, keyword)

            if not items:
                await interaction.followup.send(
                    embed=make_embed(
                        "🖼️ No Assets Found",
                        color_key="info",
                        description=(
                            f"No image assets found for **{keyword}**.\n\n"
                            "Assets are automatically saved when you use `/affiliate-product-add`.\n"
                            "Use `/asset-status` to see coverage."
                        ),
                    )
                )
                return

            # Show first result
            asset = items[0]
            title = (asset.get("title") or keyword)[:80]
            e = make_embed(
                f"🖼️ Product Assets — {title[:55]}",
                color_key="niche",
                description=(
                    f"ItemID: `{asset['itemid']}` | ShopID: `{asset['shopid']}`\n"
                    f"Last updated: {(asset.get('last_updated') or '—')[:16]}"
                ),
            )

            img1 = asset.get("image_1") or ""
            img2 = asset.get("image_2") or ""

            if img1:
                e.add_field(name="Primary Image (1:1 ready)", value=f"[Open]({img1})", inline=True)
                e.set_image(url=img1)
            if img2:
                e.add_field(name="Secondary Image",           value=f"[Open]({img2})", inline=True)

            e.add_field(
                name="Use in Creative",
                value="Run `/creative-pack` to generate AI creative prompts using this product",
                inline=False,
            )

            if len(items) > 1:
                more = [f"`{a['itemid']}` {(a.get('title') or '')[:40]}" for a in items[1:4]]
                e.add_field(
                    name=f"+{len(items)-1} more match(es)",
                    value="\n".join(more),
                    inline=False,
                )

            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_product_assets: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /asset-status ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-status",
        description="Show product asset library coverage stats",
    )
    async def cmd_asset_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import get_asset_status

            status = await asyncio.to_thread(get_asset_status)

            if status.get("error"):
                await interaction.followup.send(embed=error_embed(status["error"]))
                return

            total    = status.get("total_affiliate", 0)
            covered  = status.get("with_assets", 0)
            pct      = status.get("coverage_pct", 0.0)
            missing  = status.get("missing", [])
            last_upd = (status.get("last_updated") or "Never")[:16]

            filled = int(pct / 10)
            bar    = "█" * filled + "░" * (10 - filled)
            color  = "success" if pct >= 80 else "trend" if pct >= 40 else "error"

            e = make_embed("🖼️ Product Asset Library Status", color_key=color)
            e.add_field(name="Coverage",     value=f"**{covered}/{total}** ({pct}%)\n`{bar}`", inline=False)
            e.add_field(name="Last Updated", value=last_upd,                                    inline=True)
            e.add_field(name="Missing",      value=f"**{total - covered}** products",           inline=True)

            if missing:
                lines = [
                    f"`{m['itemid']}` {(m.get('title') or '—')[:45]}"
                    for m in missing[:8]
                ]
                e.add_field(
                    name="⚠️ Missing Assets (sample)",
                    value="\n".join(lines),
                    inline=False,
                )
                e.add_field(
                    name="Tip",
                    value=(
                        "Assets are auto-saved on `/affiliate-product-add`.\n"
                        "Run `/asset-backfill` to fill gaps for existing products."
                    ),
                    inline=False,
                )

            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_status: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /asset-backfill ───────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-backfill",
        description="Fetch images for all affiliate products that are missing assets",
    )
    async def cmd_asset_backfill(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import backfill_all_assets

            result = await asyncio.to_thread(backfill_all_assets)

            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            e = make_embed("✅ Asset Backfill Complete", color_key="success")
            e.add_field(name="Created",  value=f"**{result['created']}**",  inline=True)
            e.add_field(name="Updated",  value=f"**{result['updated']}**",  inline=True)
            e.add_field(name="Failed",   value=f"**{result['failed']}**",   inline=True)
            e.add_field(
                name="Note",
                value="Products not in the datafeed will show 0 images — this is expected.",
                inline=False,
            )
            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_backfill: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
