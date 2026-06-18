"""Slash commands: /start-scheduler, /stop-scheduler, /scheduler-status, /run-job"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import error_embed
from discord_bot.embeds.scheduler_embeds import (
    build_job_result_embed,
    build_scheduler_status_embed,
)

logger = logging.getLogger(__name__)

_VALID_JOBS = [
    "morning_brief", "trend_watch", "evening_summary", "auto_queue", "weekly_report",
    "facebook_generate", "facebook_publish_morning", "facebook_publish_afternoon", "facebook_publish_evening",
]


class SchedulerCog(commands.Cog, name="Scheduler"):
    """Manages the automated operations scheduler."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        from scheduler.scheduler import ShopeeScheduler
        self.scheduler = ShopeeScheduler(bot=bot)

    async def cog_load(self) -> None:
        self.scheduler.start()
        logger.info("[SchedulerCog] Scheduler started on cog_load")

    async def cog_unload(self) -> None:
        self.scheduler.stop()
        logger.info("[SchedulerCog] Scheduler stopped on cog_unload")

    # ------------------------------------------------------------------
    # /start-scheduler
    # ------------------------------------------------------------------

    @app_commands.command(
        name="start-scheduler",
        description="Start the automated operations scheduler",
    )
    async def cmd_start_scheduler(self, interaction: discord.Interaction) -> None:
        if self.scheduler.running:
            await interaction.response.send_message(
                embed=error_embed("Scheduler is already running. Use `/scheduler-status` to see jobs."),
                ephemeral=True,
            )
            return

        self.scheduler.start()
        status = self.scheduler.status()
        embed = build_scheduler_status_embed(status)
        embed.title = "✅ Scheduler Started"
        await interaction.response.send_message(embed=embed)
        logger.info("[SchedulerCog] Scheduler started via slash command by %s", interaction.user)

    # ------------------------------------------------------------------
    # /stop-scheduler
    # ------------------------------------------------------------------

    @app_commands.command(
        name="stop-scheduler",
        description="Stop the automated operations scheduler",
    )
    async def cmd_stop_scheduler(self, interaction: discord.Interaction) -> None:
        if not self.scheduler.running:
            await interaction.response.send_message(
                embed=error_embed("Scheduler is not running."),
                ephemeral=True,
            )
            return

        self.scheduler.stop()
        e = discord.Embed(
            title="⏹ Scheduler Stopped",
            description="All scheduled jobs have been paused. Use `/start-scheduler` to resume.",
            color=0xFF4444,
        )
        await interaction.response.send_message(embed=e)
        logger.info("[SchedulerCog] Scheduler stopped via slash command by %s", interaction.user)

    # ------------------------------------------------------------------
    # /scheduler-status
    # ------------------------------------------------------------------

    @app_commands.command(
        name="scheduler-status",
        description="Show scheduler status and next run times for all jobs",
    )
    async def cmd_scheduler_status(self, interaction: discord.Interaction) -> None:
        status = self.scheduler.status()
        embed = build_scheduler_status_embed(status)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /run-job
    # ------------------------------------------------------------------

    @app_commands.command(
        name="run-job",
        description="Manually trigger a scheduled job right now",
    )
    @app_commands.describe(job_id="Scheduled job to run immediately")
    @app_commands.choices(job_id=[
        app_commands.Choice(name="Morning Brief (08:00)",            value="morning_brief"),
        app_commands.Choice(name="Trend Watch (12:00)",              value="trend_watch"),
        app_commands.Choice(name="Evening Summary (18:00)",          value="evening_summary"),
        app_commands.Choice(name="Auto Queue Generator (06:30)",     value="auto_queue"),
        app_commands.Choice(name="Weekly Report (Sunday)",           value="weekly_report"),
        app_commands.Choice(name="FB Content Generator (06:00)",     value="facebook_generate"),
        app_commands.Choice(name="FB Publisher — Morning (08:00)",   value="facebook_publish_morning"),
        app_commands.Choice(name="FB Publisher — Afternoon (13:00)", value="facebook_publish_afternoon"),
        app_commands.Choice(name="FB Publisher — Evening (20:00)",   value="facebook_publish_evening"),
    ])
    async def cmd_run_job(
        self,
        interaction: discord.Interaction,
        job_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)

        from scheduler.scheduler import JOB_REGISTRY
        meta = JOB_REGISTRY.get(job_id, {})
        label = meta.get("label", job_id)

        try:
            await self.scheduler.run_job_now(job_id)
            embed = build_job_result_embed(
                job_id, label, success=True,
                detail=f"Outputs sent to their configured Discord channels.",
            )
            await interaction.followup.send(embed=embed)
            logger.info("[SchedulerCog] Manual run '%s' by %s — OK", job_id, interaction.user)
        except Exception as exc:
            embed = build_job_result_embed(job_id, label, success=False, detail=str(exc))
            await interaction.followup.send(embed=embed)
            logger.error("[SchedulerCog] Manual run '%s' failed: %s", job_id, exc)
