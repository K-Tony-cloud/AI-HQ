"""Phase 10.5B — Asset Coverage & Asset Health commands."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import make_embed, error_embed

logger = logging.getLogger(__name__)


def _bar(pct: float, width: int = 10) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _emoji(pct: float) -> str:
    return "🟢" if pct >= 80 else "🟡" if pct >= 40 else "🔴"


class AssetCog(commands.Cog):
    """Product Asset Library — coverage, health, and image management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /asset-coverage ───────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-coverage",
        description="Asset image coverage at Top 20 / 50 / 100 by opportunity score",
    )
    async def cmd_asset_coverage(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import get_asset_coverage

            data = await asyncio.to_thread(get_asset_coverage, [20, 50, 100])

            # Determine overall colour from Top 20
            pct20 = data.get(20, {}).get("pct", 0.0)
            color = "success" if pct20 >= 80 else "trend" if pct20 >= 40 else "error"

            e = make_embed("🖼️ Asset Coverage Report", color_key=color)

            for n in [20, 50, 100]:
                d       = data.get(n, {})
                covered = d.get("covered", 0)
                total   = d.get("total", n)
                pct     = d.get("pct", 0.0)
                e.add_field(
                    name=f"{_emoji(pct)} Top {n}",
                    value=(
                        f"**{covered}/{total}** assets ({pct}%)\n"
                        f"`{_bar(pct, 12)}`"
                    ),
                    inline=True,
                )

            # Overall verdict
            pct50  = data.get(50, {}).get("pct", 0.0)
            pct100 = data.get(100, {}).get("pct", 0.0)
            target_hit = pct50 >= 80

            e.add_field(
                name="Target: Top 50 ≥ 80%",
                value=(
                    f"{'✅ Target reached!' if target_hit else f'⚠️ {80 - pct50:.1f}% to go'}\n"
                    f"Current: **{pct50}%**"
                ),
                inline=False,
            )
            e.add_field(
                name="Actions",
                value=(
                    "`/asset-backfill` — auto-fetch all missing\n"
                    "`/asset-missing` — see which products need images\n"
                    "`/asset-health` — full health metrics"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_coverage: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /asset-missing ────────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-missing",
        description="Products with affiliate links but no image assets — sorted by opportunity",
    )
    @app_commands.describe(limit="How many products to show (default 20, max 30)")
    async def cmd_asset_missing(
        self,
        interaction: discord.Interaction,
        limit: int = 20,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import get_missing_assets

            limit = max(5, min(limit, 30))
            items = await asyncio.to_thread(get_missing_assets, limit)

            if not items:
                e = make_embed(
                    "✅ No Missing Assets",
                    color_key="success",
                    description="All affiliate products have image assets saved. 🎉",
                )
                await interaction.followup.send(embed=e)
                return

            e = make_embed(
                f"⚠️ Products Missing Assets ({len(items)})",
                color_key="trend",
                description="Sorted by opportunity score. Run `/asset-backfill` to fetch all at once.",
            )

            lines = []
            for i, p in enumerate(items, 1):
                reason = "📭 Never fetched" if p["reason"] == "not_fetched" else "🖼️ No image in datafeed"
                score  = int(p.get("opp_score") or 0)
                title  = (p.get("title") or f"ItemID {p['itemid']}")[:52]
                lines.append(
                    f"`{i:>2}.` **{title}**\n"
                    f"       Score: `{score:,}` | {reason}"
                )

            # Split into up to 3 fields to avoid the 1024-char limit
            chunk = 10
            for start in range(0, min(len(lines), 30), chunk):
                e.add_field(
                    name=f"#{start+1}–#{min(start+chunk, len(lines))}",
                    value="\n".join(lines[start:start+chunk])[:1024],
                    inline=False,
                )

            e.set_footer(text=f"{len(items)} products need images • /asset-backfill to fix all")
            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_missing: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /asset-status ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-status",
        description="Check asset status for a product (keyword) or show overall library stats",
    )
    @app_commands.describe(keyword="Product name to check (e.g. dr pong, garnier) — leave blank for overall stats")
    async def cmd_asset_status(
        self,
        interaction: discord.Interaction,
        keyword: str = "",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            # ── Per-product detail ─────────────────────────────────────────
            if keyword.strip():
                from shopee_engine.asset_engine import (
                    fetch_and_save_product_assets,
                    get_product_asset_detail,
                )

                detail = await asyncio.to_thread(get_product_asset_detail, keyword)

                # Auto-fetch if not in table yet
                if detail and not detail["asset_ready"] and detail["asset_status"] == "not_fetched":
                    await asyncio.to_thread(
                        fetch_and_save_product_assets,
                        detail["itemid"],
                        detail["shopid"],
                    )
                    detail = await asyncio.to_thread(get_product_asset_detail, keyword)

                if not detail:
                    await interaction.followup.send(
                        embed=make_embed(
                            "🔍 Product Not Found",
                            color_key="info",
                            description=(
                                f"No affiliate product found matching **{keyword}**.\n"
                                "Make sure the product is in `affiliate_products` with a short URL."
                            ),
                        )
                    )
                    return

                title  = (detail.get("title") or keyword)[:70]
                ready  = detail["asset_ready"]
                color  = "success" if ready else "error"
                img1   = detail.get("image_1") or ""
                img2   = detail.get("image_2") or ""
                thumb  = detail.get("thumbnail") or ""

                e = make_embed(
                    f"🖼️ Asset Status — {title[:50]}",
                    color_key=color,
                )
                e.add_field(
                    name="Product",
                    value=f"`{title}`\nItemID: `{detail['itemid']}` | ShopID: `{detail['shopid']}`",
                    inline=False,
                )
                e.add_field(name="Image 1",   value="✅" if img1   else "❌", inline=True)
                e.add_field(name="Image 2",   value="✅" if img2   else "❌", inline=True)
                e.add_field(name="Thumbnail", value="✅" if thumb  else "❌", inline=True)
                e.add_field(
                    name="Asset Ready",
                    value="✅ Ready for AI creative generation" if ready
                          else "❌ Run `/asset-backfill` to fetch",
                    inline=False,
                )
                if img1:
                    e.set_image(url=img1)
                if detail.get("last_updated"):
                    e.set_footer(text=f"Last updated: {detail['last_updated'][:16]}")

                await interaction.followup.send(embed=e)
                return

            # ── Overall stats (no keyword) ─────────────────────────────────
            from shopee_engine.asset_engine import get_asset_health, get_asset_coverage

            health   = await asyncio.to_thread(get_asset_health)
            coverage = await asyncio.to_thread(get_asset_coverage, [20, 50, 100])

            if health.get("error"):
                await interaction.followup.send(embed=error_embed(health["error"]))
                return

            total      = health["total_affiliate"]
            ready      = health["ready"]
            no_image   = health["no_image"]
            not_fetched = health["not_fetched"]
            pct        = health["coverage_pct"]
            last_upd   = (health.get("last_updated") or "Never")[:16]

            color = "success" if pct >= 80 else "trend" if pct >= 40 else "error"
            e = make_embed("🖼️ Asset Library Status", color_key=color)

            e.add_field(
                name="Overall Coverage",
                value=f"**{ready}/{total}** ({pct}%)\n`{_bar(pct, 12)}`",
                inline=False,
            )
            e.add_field(name="✅ Ready",          value=str(ready),      inline=True)
            e.add_field(name="🖼️ No image",       value=str(no_image),   inline=True)
            e.add_field(name="📭 Never fetched",  value=str(not_fetched), inline=True)
            e.add_field(name="Last fetch",        value=last_upd,        inline=True)

            # Coverage breakdown
            cov_lines = []
            for n in [20, 50, 100]:
                d   = coverage.get(n, {})
                cv  = d.get("covered", 0)
                tot = d.get("total", n)
                p   = d.get("pct", 0.0)
                cov_lines.append(f"{_emoji(p)} **Top {n}:** {cv}/{tot} ({p}%)  `{_bar(p, 10)}`")
            e.add_field(name="Coverage by Tier", value="\n".join(cov_lines), inline=False)

            # Target status
            pct50 = coverage.get(50, {}).get("pct", 0.0)
            need_more = round(50 * 0.8 - coverage.get(50, {}).get("covered", 0))
            target_val = "✅ Reached!" if pct50 >= 80 else f"Need {need_more} more products"
            e.add_field(
                name="🎯 Target: Top 50 ≥ 80%",
                value=target_val,
                inline=False,
            )

            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_status: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /asset-health ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-health",
        description="Full asset library health report with metrics and recent activity",
    )
    async def cmd_asset_health(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import get_asset_health, get_asset_coverage

            health   = await asyncio.to_thread(get_asset_health)
            coverage = await asyncio.to_thread(get_asset_coverage, [20, 50, 100])

            if health.get("error"):
                await interaction.followup.send(embed=error_embed(health["error"]))
                return

            total       = health["total_affiliate"]
            ready       = health["ready"]
            no_image    = health["no_image"]
            not_fetched = health["not_fetched"]
            pct         = health["coverage_pct"]

            color = "success" if pct >= 80 else "trend" if pct >= 40 else "error"
            e = make_embed("🏥 Asset Library Health Report", color_key=color)

            # Summary row
            e.add_field(name="📦 Total Products",    value=str(total),      inline=True)
            e.add_field(name="✅ With Assets",        value=str(ready),      inline=True)
            e.add_field(name="❌ Missing Assets",     value=str(total - ready), inline=True)
            e.add_field(name="Coverage %",            value=f"**{pct}%**",   inline=True)
            e.add_field(name="🖼️ No image in feed",  value=str(no_image),   inline=True)
            e.add_field(name="📭 Never fetched",      value=str(not_fetched), inline=True)

            # Coverage tiers
            tier_lines = []
            for n in [20, 50, 100]:
                d   = coverage.get(n, {})
                cv  = d.get("covered", 0)
                tot = d.get("total", n)
                p   = d.get("pct", 0.0)
                tier_lines.append(
                    f"{_emoji(p)} **Top {n}:** {cv}/{tot} ({p}%)  `{_bar(p, 10)}`"
                )
            e.add_field(name="Coverage by Tier", value="\n".join(tier_lines), inline=False)

            # Recently fetched
            recent = health.get("recently_fetched", [])
            if recent:
                lines = [
                    f"• {(r.get('title') or '—')[:48]} _(fetched {(r.get('last_updated') or '')[:10]})_"
                    for r in recent[:5]
                ]
                e.add_field(name="🕐 Recently Fetched", value="\n".join(lines), inline=False)

            # Readiness verdict
            pct50 = coverage.get(50, {}).get("pct", 0.0)
            if pct50 >= 80:
                verdict = "✅ **Asset Coverage Target Met** — ready to proceed to Phase 11 (Revenue Intelligence)"
            else:
                gap = round(50 * 0.8 - coverage.get(50, {}).get("covered", 0))
                verdict = (
                    f"⚠️ **{pct50}% / 80% target** — need **{gap} more** top-50 products covered\n"
                    f"Run `/asset-backfill` then check if newly imported datafeed has those products"
                )
            e.add_field(name="Phase Readiness", value=verdict, inline=False)

            e.add_field(
                name="Actions",
                value=(
                    "`/asset-backfill` — fetch all missing images\n"
                    "`/asset-missing` — list which products need images\n"
                    "`/asset-coverage` — visual coverage bars\n"
                    "`/asset-status dr pong` — per-product image check"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_health: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /asset-backfill ───────────────────────────────────────────────────────

    @app_commands.command(
        name="asset-backfill",
        description="Fetch images from datafeed for all affiliate products missing assets",
    )
    async def cmd_asset_backfill(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import backfill_all_assets, get_asset_coverage

            result   = await asyncio.to_thread(backfill_all_assets)
            coverage = await asyncio.to_thread(get_asset_coverage, [20, 50, 100])

            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return

            pct20 = coverage.get(20, {}).get("pct", 0)
            pct50 = coverage.get(50, {}).get("pct", 0)

            e = make_embed("✅ Asset Backfill Complete", color_key="success")
            e.add_field(name="✅ Created", value=f"**{result['created']}**", inline=True)
            e.add_field(name="🔄 Updated", value=f"**{result['updated']}**", inline=True)
            e.add_field(name="❌ Failed",  value=f"**{result['failed']}**",  inline=True)
            e.add_field(
                name="Coverage After Backfill",
                value=(
                    f"{_emoji(pct20)} Top 20: **{pct20}%**  `{_bar(pct20)}`\n"
                    f"{_emoji(pct50)} Top 50: **{pct50}%**  `{_bar(pct50)}`"
                ),
                inline=False,
            )
            if result["failed"] > 0:
                e.add_field(
                    name="Note",
                    value=(
                        f"{result['failed']} products not found in the current datafeed. "
                        "Import a fresh datafeed to fill these gaps."
                    ),
                    inline=False,
                )
            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_asset_backfill: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /product-assets ───────────────────────────────────────────────────────

    @app_commands.command(
        name="product-assets",
        description="Show full image assets for a product with inline preview",
    )
    @app_commands.describe(keyword="Product name or keyword")
    async def cmd_product_assets(
        self,
        interaction: discord.Interaction,
        keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.asset_engine import (
                fetch_and_save_product_assets,
                search_assets_by_keyword,
            )

            items = await asyncio.to_thread(search_assets_by_keyword, keyword)

            if not items:
                from shopee_engine.creative_engine import search_products_for_creative
                products = await asyncio.to_thread(search_products_for_creative, keyword)
                if products:
                    p = products[0]
                    r = await asyncio.to_thread(
                        fetch_and_save_product_assets, p["itemid"], p["shopid"]
                    )
                    if r["success"]:
                        items = await asyncio.to_thread(search_assets_by_keyword, keyword)

            if not items:
                await interaction.followup.send(
                    embed=make_embed(
                        "🖼️ No Assets Found",
                        color_key="info",
                        description=(
                            f"No image assets for **{keyword}**.\n"
                            "• Run `/asset-backfill` to fetch all\n"
                            "• Or `/affiliate-product-add` auto-fetches on save"
                        ),
                    )
                )
                return

            asset = items[0]
            title = (asset.get("title") or keyword)[:70]
            img1  = asset.get("image_1") or ""
            img2  = asset.get("image_2") or ""

            e = make_embed(
                f"🖼️ {title[:55]}",
                color_key="niche",
                description=(
                    f"ItemID: `{asset['itemid']}` | ShopID: `{asset['shopid']}`\n"
                    f"Status: `{asset.get('asset_status','—')}` | "
                    f"Updated: {(asset.get('last_updated') or '—')[:16]}"
                ),
            )
            e.add_field(name="Image 1",   value=f"[View]({img1})" if img1 else "❌", inline=True)
            e.add_field(name="Image 2",   value=f"[View]({img2})" if img2 else "❌", inline=True)
            e.add_field(name="Thumbnail", value="✅" if img1 else "❌",               inline=True)
            if img1:
                e.set_image(url=img1)
            if img2:
                e.set_thumbnail(url=img2)

            await interaction.followup.send(embed=e)

        except Exception as exc:
            logger.error("cmd_product_assets: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
