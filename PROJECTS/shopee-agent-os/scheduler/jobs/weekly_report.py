"""Sunday 20:00 — Weekly Report job."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_weekly_report(bot=None) -> None:
    """
    Sunday 20:00 Bangkok — Export weekly report in MD/HTML/CSV
    and post files + summary embed to Discord.
    """
    logger.info("[job:weekly_report] Starting")

    from discord_bot.config import CHANNEL_LEARNING_REPORTS
    from discord_bot.embeds.scheduler_embeds import build_weekly_report_embed
    from scheduler.notifications.discord_notify import send_to_channel
    from shopee_engine.operator_center import daily_report, executive_summary

    output_dir = "exports/reports"
    exported: list[Path] = []

    for fmt in ("markdown", "html", "csv"):
        try:
            path = daily_report(fmt=fmt, output_dir=output_dir)
            exported.append(path)
            logger.info("[job:weekly_report] Exported %s", path)
        except Exception as exc:
            logger.error("[job:weekly_report] Export %s failed: %s", fmt, exc)

    try:
        summary_data = executive_summary()
    except Exception as exc:
        logger.error("[job:weekly_report] executive_summary failed: %s", exc)
        summary_data = {}

    embed = build_weekly_report_embed(summary_data, exported)

    try:
        import discord

        files = []
        for path in exported:
            if path.exists():
                files.append(discord.File(str(path), filename=path.name))

        await send_to_channel(
            bot,
            CHANNEL_LEARNING_REPORTS,
            [embed],
            content="📊 **Weekly Affiliate Report**",
            files=files,
        )
        logger.info("[job:weekly_report] Sent %d files to Discord", len(files))
    except Exception as exc:
        logger.error("[job:weekly_report] Notification error: %s", exc)

    # Run Thai Intelligence learning loop weekly adjustment
    try:
        import asyncio
        from shopee_engine.thai_intelligence.learning_loop import run_weekly_adjustment
        adjustment = await asyncio.to_thread(run_weekly_adjustment)
        promoted = adjustment.get("promoted", [])
        demoted  = adjustment.get("demoted", [])
        logger.info(
            "[job:weekly_report] Learning loop: promoted=%d demoted=%d",
            len(promoted), len(demoted),
        )
        if bot and (promoted or demoted):
            import discord
            from discord_bot.config import CHANNEL_LEARNING_REPORTS
            from scheduler.notifications.discord_notify import send_to_channel
            e = discord.Embed(
                title="🧠 Thai Intelligence — Weekly Adjustment",
                color=0x7C4DFF,
            )
            e.add_field(
                name=f"⬆️ Promoted ({len(promoted)})",
                value="\n".join(f"`{p}`" for p in promoted[:10]) or "none",
                inline=True,
            )
            e.add_field(
                name=f"⬇️ Demoted ({len(demoted)})",
                value="\n".join(f"`{p}`" for p in demoted[:10]) or "none",
                inline=True,
            )
            summary = adjustment.get("summary", {})
            e.set_footer(
                text=f"Total patterns: {summary.get('total_patterns', '?')} | Used: {summary.get('patterns_used', '?')}"
            )
            await send_to_channel(bot, CHANNEL_LEARNING_REPORTS, [e])
    except Exception as exc:
        logger.warning("[job:weekly_report] Learning loop adjustment failed: %s", exc)

    logger.info("[job:weekly_report] Done")
