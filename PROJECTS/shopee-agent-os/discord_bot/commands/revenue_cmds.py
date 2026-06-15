"""Phase 11 — Revenue Intelligence commands."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import PaginatedView, error_embed, make_embed
from discord_bot.embeds.revenue_embeds import (
    build_import_result_embed,
    build_revenue_dashboard_embeds,
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
            if not file.filename.lower().endswith(".csv"):
                await interaction.followup.send(
                    embed=make_embed(
                        "❌ Invalid File",
                        color_key="error",
                        description="Please upload a `.csv` file exported from the Shopee affiliate portal.",
                    )
                )
                return

            content = await file.read()

            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
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
