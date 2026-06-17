"""Slash command: /system-status"""

from __future__ import annotations

import logging
import os
import platform
import sys
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.system_embeds import build_system_status_embed

logger = logging.getLogger(__name__)

_START_TIME: datetime = datetime.now(timezone.utc)


def _format_uptime(start: datetime) -> str:
    delta = datetime.now(timezone.utc) - start
    total_seconds = int(delta.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _detect_host() -> tuple[str, str]:
    """Return (host_label, region)."""
    if os.getenv("RENDER"):
        service = os.getenv("RENDER_SERVICE_NAME", "shopee-agent-os")
        region = os.getenv("RENDER_REGION", "")
        return f"Render ({service})", region
    return "Mac (local)", ""


def _db_product_count() -> int | None:
    try:
        import duckdb
        from shopee_engine.config import DB_PATH
        if not DB_PATH.exists():
            return None
        con = duckdb.connect(str(DB_PATH), read_only=True)
        row = con.execute("SELECT COUNT(*) FROM products").fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


class SystemCog(commands.Cog, name="System"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="system-status",
        description="Show bot health, scheduler, database, and hosting info",
    )
    async def cmd_system_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        host, region = _detect_host()

        # Scheduler info from the SchedulerCog (running in same process)
        sched_running = False
        job_count = 0
        next_brief = "—"
        jobs_info: list[dict] = []

        sched_cog = self.bot.cogs.get("Scheduler")
        if sched_cog and hasattr(sched_cog, "scheduler"):
            s = sched_cog.scheduler.status()
            sched_running = s.get("running", False)
            job_count = s.get("job_count", 0)
            jobs_info = s.get("jobs", [])
            for j in jobs_info:
                if j["id"] == "morning_brief":
                    next_brief = j["next_run"]
                    break

        db_products = _db_product_count()

        from shopee_engine.config import DB_PATH

        status = {
            "host": host,
            "region": region,
            "uptime": _format_uptime(_START_TIME),
            "py_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "bot_name": str(self.bot.user) if self.bot.user else "—",
            "guild_count": len(self.bot.guilds),
            "scheduler_running": sched_running,
            "job_count": job_count,
            "next_morning_brief": next_brief,
            "db_path": str(DB_PATH),
            "db_products": db_products,
            "jobs": jobs_info,
        }

        embed = build_system_status_embed(status)
        await interaction.followup.send(embed=embed)
        logger.info("[SystemCog] /system-status called by %s", interaction.user)

    # ── /force-sync ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="force-sync",
        description="Force re-sync all slash commands to this guild (use after bot updates)",
    )
    async def cmd_force_sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            from discord_bot.config import DISCORD_GUILD_ID

            if DISCORD_GUILD_ID:
                guild = discord.Object(id=int(DISCORD_GUILD_ID))
                self.bot.tree.copy_global_to(guild=guild)
                synced = await self.bot.tree.sync(guild=guild)
            else:
                synced = await self.bot.tree.sync()

            names = sorted(c.name for c in synced)
            e = discord.Embed(
                title=f"✅ Synced {len(synced)} Commands",
                description="\n".join(f"`/{n}`" for n in names),
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=e, ephemeral=True)
            logger.info("[SystemCog] /force-sync by %s — %d commands", interaction.user, len(synced))
        except Exception as exc:
            await interaction.followup.send(f"❌ Sync failed: {exc}", ephemeral=True)
            logger.error("[SystemCog] /force-sync error: %s", exc)

    # ── /list-commands ────────────────────────────────────────────────────────

    @app_commands.command(
        name="list-commands",
        description="Show all registered Shopee Agent OS slash commands grouped by module",
    )
    async def cmd_list_commands(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)

        e = discord.Embed(
            title="📋 Registered Slash Commands",
            color=discord.Color.blurple(),
        )

        _cog_order = [
            ("Discovery",  "Daily picks, opportunities, viral"),
            ("Operator",   "Morning brief, executive summary"),
            ("Affiliate",  "Links, products, coverage, dashboard"),
            ("Revenue",    "Import reports, dashboard, analysis"),
            ("Asset",      "Coverage, missing, health, backfill"),
            ("Creative",   "AI content generation"),
            ("Content",    "Content queue and pack"),
            ("Scheduler",  "Scheduled jobs"),
            ("System",     "Status, sync, commands"),
            ("Performance","Top profit"),
        ]

        for cog_name, cog_desc in _cog_order:
            cog = interaction.client.cogs.get(cog_name)
            if not cog:
                continue
            cmds = sorted(c.name for c in cog.get_app_commands())
            if cmds:
                e.add_field(
                    name=f"{cog_name} — {cog_desc}",
                    value=" ".join(f"`/{c}`" for c in cmds),
                    inline=False,
                )

        total = sum(len(list(c.get_app_commands())) for c in interaction.client.cogs.values())
        e.set_footer(text=f"Total: {total} commands")
        await interaction.followup.send(embed=e, ephemeral=True)
        logger.info("[SystemCog] /list-commands called by %s", interaction.user)
