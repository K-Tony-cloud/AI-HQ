"""08:00 / 13:00 / 20:00 daily — publish due Facebook posts from scheduled_posts queue."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_facebook_publisher(bot=None) -> None:
    """
    Publish all pending posts from scheduled_posts where publish_at <= now (today only).
    Called at 08:00, 13:00, and 20:00 Bangkok time.
    """
    logger.info("[job:facebook_publisher] Checking for due posts")

    from discord_bot.config import CHANNEL_CONTENT_QUEUE
    from scheduler.notifications.discord_notify import send_to_channel
    from shopee_engine.insights_engine import fb_publish_due_posts

    result = fb_publish_due_posts()

    published = result.get("published", [])
    errors    = result.get("errors", [])
    total     = result.get("total", 0)

    if not published and not errors:
        logger.info("[job:facebook_publisher] No due posts found")
        return

    logger.info(
        "[job:facebook_publisher] Published %d post(s), %d error(s)",
        total, len(errors),
    )

    try:
        import discord

        if published:
            lines = [
                f"✅ `{p['post_type']}` — [{p['message'][:50]}…]"
                for p in published
            ]
            e = discord.Embed(
                title=f"📢 {total} Post{'s' if total != 1 else ''} Published to Facebook",
                description="\n".join(lines),
                color=0x1877F2,
            )
        else:
            e = discord.Embed(
                title="⚠️ Facebook Publisher — All Posts Failed",
                description="\n".join(f"• DB `{er['db_id']}`: {er['error'][:80]}" for er in errors),
                color=0xFF6B00,
            )

        if errors and published:
            e.add_field(
                name="⚠️ Errors",
                value="\n".join(f"• DB `{er['db_id']}`: {er['error'][:60]}" for er in errors),
                inline=False,
            )

        await send_to_channel(bot, CHANNEL_CONTENT_QUEUE, [e])
    except Exception as exc:
        logger.error("[job:facebook_publisher] Notification error: %s", exc)
