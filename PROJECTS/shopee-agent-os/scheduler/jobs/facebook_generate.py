"""06:00 daily — generate today's Facebook editorial content and queue 3 posts."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_facebook_generate(bot=None) -> None:
    """
    06:00 Bangkok — call editorial engine, save 3 posts to scheduled_posts
    (publish_at: 08:00 / 13:00 / 20:00 today).
    """
    logger.info("[job:facebook_generate] Starting daily content generation")

    from discord_bot.config import CHANNEL_CONTENT_QUEUE
    from scheduler.notifications.discord_notify import send_to_channel
    from shopee_engine.insights_engine import fb_generate_daily_schedule

    result = fb_generate_daily_schedule()

    if result.get("skipped"):
        logger.info("[job:facebook_generate] %s", result["reason"])
        return

    if not result.get("success"):
        err = result.get("error", "unknown error")
        logger.error("[job:facebook_generate] Failed: %s", err)
        try:
            import discord
            e = discord.Embed(
                title="❌ Facebook Content Generation Failed",
                description=f"`{err}`",
                color=0xFF4444,
            )
            await send_to_channel(bot, CHANNEL_CONTENT_QUEUE, [e])
        except Exception:
            pass
        return

    scheduled = result.get("scheduled", [])
    date      = result.get("date", "")
    override  = result.get("override", False)

    logger.info(
        "[job:facebook_generate] %d posts queued for %s (override=%s)",
        len(scheduled), date, override,
    )

    try:
        import discord
        lines = [f"• ID `{s['id']}` — **{s['post_type']}** @ `{s['publish_at'][11:16]}`" for s in scheduled]
        e = discord.Embed(
            title=f"📅 Facebook Content Queued — {date}",
            description="\n".join(lines) or "No posts queued",
            color=0x00C853,
        )
        e.set_footer(text=f"{'⚡ Override mode active' if override else '🗓 Standard schedule'} | publishes at 08:00 / 13:00 / 20:00")
        await send_to_channel(bot, CHANNEL_CONTENT_QUEUE, [e])
    except Exception as exc:
        logger.error("[job:facebook_generate] Notification error: %s", exc)
