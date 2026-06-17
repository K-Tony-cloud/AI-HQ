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
