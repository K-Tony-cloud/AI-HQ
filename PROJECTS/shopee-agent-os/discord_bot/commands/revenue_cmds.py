"""Phase 11 — Revenue Intelligence commands."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, make_embed, send_and_confirm
from discord_bot.embeds.revenue_embeds import (
    build_import_result_embed,
    build_revenue_category_embed,
    build_revenue_dashboard_embeds,
    build_revenue_products_embed,
    build_revenue_summary_embed,
    build_revenue_top_embed,
)

logger = logging.getLogger(__name__)

_REPORT_CHOICES = [
    app_commands.Choice(name="Revenue / Commission",  value="revenue"),
    app_commands.Choice(name="Click Report",          value="click"),
    app_commands.Choice(name="Order Report",          value="order"),
]


class RevenueCog(commands.Cog):
    """Revenue Intelligence — import Shopee reports and view performance."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /affiliate-import-report ──────────────────────────────────────────────

    @app_commands.command(
        name="affiliate-import-report",
        description="Import a Shopee affiliate CSV report (click / order / revenue)",
    )
    @app_commands.describe(
        file="CSV file exported from Shopee affiliate portal",
        report_type="Type of report",
    )
    @app_commands.choices(report_type=_REPORT_CHOICES)
    async def cmd_import_report(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        report_type: str = "revenue",
    ) -> None:
        await interaction.response.defer(thinking=True)
        tmp_path: str | None = None
        try:
            _allowed = (".csv", ".xlsx", ".xls")
            if not any(file.filename.lower().endswith(ext) for ext in _allowed):
                await interaction.followup.send(
                    embed=make_embed(
                        "❌ Invalid File",
                        color_key="error",
                        description="Please upload a `.csv` or `.xlsx` file from the Shopee affiliate portal.",
                    )
                )
                return

            content = await file.read()

            _suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
            with tempfile.NamedTemporaryFile(suffix=_suffix, delete=False) as f:
                f.write(content)
                tmp_path = f.name

            from shopee_engine.feedback_engine import (
                import_click_report,
                import_order_report,
                import_revenue_report,
            )

            fn_map = {
                "revenue": import_revenue_report,
                "click":   import_click_report,
                "order":   import_order_report,
            }
            fn     = fn_map[report_type]
            result = await asyncio.to_thread(fn, tmp_path)

            embed = build_import_result_embed(result, report_type, file.filename)

            from discord_bot.config import CHANNEL_REVENUE
            ch_id = CHANNEL_REVENUE
            if ch_id:
                try:
                    ch = self.bot.get_channel(ch_id) or await self.bot.fetch_channel(ch_id)
                    await ch.send(embed=embed)
                    await interaction.followup.send(
                        f"✅ Imported to <#{ch_id}>", ephemeral=True
                    )
                    return
                except Exception:
                    pass

            await interaction.followup.send(embed=embed)

        except Exception as exc:
            logger.error("cmd_import_report: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── /revenue-dashboard ────────────────────────────────────────────────────

    @app_commands.command(
        name="revenue-dashboard",
        description="Show revenue performance: top clicked, top orders, top commission, EPC, worst",
    )
    @app_commands.describe(top_n="How many products per section (default 5)")
    async def cmd_revenue_dashboard(
        self,
        interaction: discord.Interaction,
        top_n: int = 5,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.feedback_engine import get_revenue_dashboard

            top_n  = max(3, min(top_n, 10))
            data   = await asyncio.to_thread(get_revenue_dashboard, top_n)
            embeds = build_revenue_dashboard_embeds(data)

            from discord_bot.config import CHANNEL_REVENUE
            ch_id = CHANNEL_REVENUE
            if ch_id:
                try:
                    ch = self.bot.get_channel(ch_id) or await self.bot.fetch_channel(ch_id)
                    for embed in embeds:
                        await ch.send(embed=embed)
                    await interaction.followup.send(
                        f"✅ Dashboard posted to <#{ch_id}>", ephemeral=True
                    )
                    return
                except Exception:
                    pass

            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                view = PaginatedView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as exc:
            logger.error("cmd_revenue_dashboard: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /revenue-summary ─────────────────────────────────────────────────────

    @app_commands.command(
        name="revenue-summary",
        description="Overall revenue totals: clicks, orders, commission, EPC, conversion rate",
    )
    async def cmd_revenue_summary(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.feedback_engine import get_revenue_summary
            from discord_bot.config import CHANNEL_REVENUE

            data  = await asyncio.to_thread(get_revenue_summary)
            embed = build_revenue_summary_embed(data)
            await send_and_confirm(interaction, [embed], CHANNEL_REVENUE)
        except Exception as exc:
            logger.error("cmd_revenue_summary: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /revenue-products ────────────────────────────────────────────────────

    @app_commands.command(
        name="revenue-products",
        description="Per-product revenue breakdown with clicks, orders, commission, EPC",
    )
    @app_commands.describe(
        keyword="Filter by product name (optional)",
        limit="Number of products to show (default 15, max 30)",
    )
    async def cmd_revenue_products(
        self,
        interaction: discord.Interaction,
        keyword: str = "",
        limit: int = 15,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.feedback_engine import get_revenue_products
            from discord_bot.config import CHANNEL_REVENUE

            limit = max(5, min(limit, 30))
            items = await asyncio.to_thread(get_revenue_products, keyword, limit)
            embed = build_revenue_products_embed(items, keyword)
            await send_and_confirm(interaction, [embed], CHANNEL_REVENUE)
        except Exception as exc:
            logger.error("cmd_revenue_products: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /revenue-top ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="revenue-top",
        description="Top products ranked by clicks, orders, revenue, or commission",
    )
    @app_commands.describe(
        metric="Ranking metric",
        top_n="How many products to show (default 10)",
    )
    @app_commands.choices(metric=[
        app_commands.Choice(name="Commission (default)", value="commission"),
        app_commands.Choice(name="Revenue",              value="revenue"),
        app_commands.Choice(name="Orders",               value="orders"),
        app_commands.Choice(name="Clicks",               value="clicks"),
    ])
    async def cmd_revenue_top(
        self,
        interaction: discord.Interaction,
        metric: str = "commission",
        top_n: int = 10,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.feedback_engine import get_revenue_top
            from discord_bot.config import CHANNEL_REVENUE

            top_n = max(3, min(top_n, 20))
            items = await asyncio.to_thread(get_revenue_top, metric, top_n)
            embed = build_revenue_top_embed(items, metric)
            await send_and_confirm(interaction, [embed], CHANNEL_REVENUE)
        except Exception as exc:
            logger.error("cmd_revenue_top: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /revenue-category ────────────────────────────────────────────────────

    @app_commands.command(
        name="revenue-category",
        description="Revenue breakdown by product category",
    )
    @app_commands.describe(top_n="Number of categories to show (default 10)")
    async def cmd_revenue_category(
        self,
        interaction: discord.Interaction,
        top_n: int = 10,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.feedback_engine import get_revenue_by_category
            from discord_bot.config import CHANNEL_REVENUE

            top_n = max(3, min(top_n, 20))
            items = await asyncio.to_thread(get_revenue_by_category, top_n)
            embed = build_revenue_category_embed(items)
            await send_and_confirm(interaction, [embed], CHANNEL_REVENUE)
        except Exception as exc:
            logger.error("cmd_revenue_category: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /import-commission-report ─────────────────────────────────────────────

    @app_commands.command(
        name="import-commission-report",
        description="Import Shopee TH commission report (ค่าคอมมิชชั่น) — CSV or Excel",
    )
    @app_commands.describe(file="Commission report file from Shopee affiliate portal")
    async def cmd_import_commission_th(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
    ) -> None:
        await interaction.response.defer(thinking=True)
        tmp_path: str | None = None
        try:
            _allowed = (".csv", ".xlsx", ".xls")
            if not any(file.filename.lower().endswith(ext) for ext in _allowed):
                await interaction.followup.send(
                    embed=make_embed("❌ Invalid File", color_key="error",
                                    description="Upload a `.csv` or `.xlsx` file."),
                    ephemeral=True,
                )
                return

            content = await file.read()
            _suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
            with tempfile.NamedTemporaryFile(suffix=_suffix, delete=False) as f:
                f.write(content)
                tmp_path = f.name

            from shopee_engine.feedback_engine import import_commission_report_th
            from discord_bot.config import CHANNEL_REVENUE

            result = await asyncio.to_thread(import_commission_report_th, tmp_path)
            embed  = build_import_result_embed(result, "commission_th", file.filename)

            # Show extra stats for commission report
            if result.get("rows_imported", 0) > 0:
                rev = result.get("total_revenue", 0)
                com = result.get("total_commission", 0)
                embed.add_field(
                    name="📊 Totals",
                    value=f"Revenue: ฿{rev:,.2f} | Commission: ฿{com:,.2f}",
                    inline=False,
                )

            await send_and_confirm(interaction, [embed], CHANNEL_REVENUE)
        except Exception as exc:
            logger.error("cmd_import_commission_th: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── /import-click-report ──────────────────────────────────────────────────

    @app_commands.command(
        name="import-click-report",
        description="Import Shopee TH click report (รหัสคลิก / เวลาคลิก) — CSV or Excel",
    )
    @app_commands.describe(file="Click report file from Shopee affiliate portal")
    async def cmd_import_click_th(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
    ) -> None:
        await interaction.response.defer(thinking=True)
        tmp_path: str | None = None
        try:
            _allowed = (".csv", ".xlsx", ".xls")
            if not any(file.filename.lower().endswith(ext) for ext in _allowed):
                await interaction.followup.send(
                    embed=make_embed("❌ Invalid File", color_key="error",
                                    description="Upload a `.csv` or `.xlsx` file."),
                    ephemeral=True,
                )
                return

            content = await file.read()
            _suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
            with tempfile.NamedTemporaryFile(suffix=_suffix, delete=False) as f:
                f.write(content)
                tmp_path = f.name

            from shopee_engine.feedback_engine import import_click_report_th
            from discord_bot.config import CHANNEL_REVENUE

            result = await asyncio.to_thread(import_click_report_th, tmp_path)
            embed  = build_import_result_embed(result, "click_th", file.filename)

            if result.get("total_clicks", 0) > 0:
                embed.add_field(
                    name="📊 Totals",
                    value=(
                        f"Total clicks: **{result['total_clicks']:,}** "
                        f"across **{result.get('days_covered', 0)}** days"
                    ),
                    inline=False,
                )

            await send_and_confirm(interaction, [embed], CHANNEL_REVENUE)
        except Exception as exc:
            logger.error("cmd_import_click_th: %s", exc)
            await interaction.followup.send(embed=error_embed(str(exc)))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
