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
    from shopee_engine.ai_status import get_ai_status
    from shopee_engine.insights_engine import fb_generate_daily_schedule

    ai = get_ai_status()
    provider_label = f"Claude · {ai['model']}" if ai["active"] else "Fallback Templates"
    logger.info("[job:facebook_generate] AI provider: %s", provider_label)

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
    posts     = result.get("posts", [])
    date      = result.get("date", "")
    override  = result.get("override", False)

    logger.info(
        "[job:facebook_generate] %d posts queued for %s (override=%s)",
        len(scheduled), date, override,
    )

    try:
        import discord

        # Main summary embed
        lines = [
            f"• ID `{s['id']}` — **{s['post_type']}** @ `{s['publish_at'][11:16]}`"
            for s in scheduled
        ]
        e = discord.Embed(
            title=f"📅 Facebook Content Queued — {date}",
            description="\n".join(lines) or "No posts queued",
            color=0x00C853 if ai["active"] else 0xFF9800,
        )
        e.add_field(
            name="🤖 AI Provider",
            value=f"`{provider_label}`",
            inline=True,
        )
        e.add_field(
            name="🗣 Humanize",
            value="`ENABLED`" if ai["active"] else "`DISABLED — add real ANTHROPIC_API_KEY`",
            inline=True,
        )
        e.set_footer(
            text=f"{'⚡ Override' if override else '🗓 Standard'} | 08:00 / 13:00 / 20:00"
        )

        embeds = [e]

        # Per-post before/after embed (first post only, as proof)
        if posts:
            p = posts[0]
            raw     = p.get("caption_raw", "")
            human   = p.get("caption", "")
            changed = raw and human and raw != human

            proof = discord.Embed(
                title=f"🔬 Content Proof — Post 1 ({p.get('type', '?')})",
                color=0x1877F2,
            )
            if changed:
                proof.add_field(
                    name="📄 Raw Draft (before humanize)",
                    value=f"```\n{raw[:400]}\n```",
                    inline=False,
                )
                proof.add_field(
                    name="🗣 Humanized (after Claude)",
                    value=f"```\n{human[:400]}\n```",
                    inline=False,
                )
            else:
                proof.add_field(
                    name="📄 Caption (rule-based only)",
                    value=f"```\n{human[:400]}\n```",
                    inline=False,
                )
                proof.add_field(
                    name="⚠️ Note",
                    value="Content was NOT processed by Claude — add a real `ANTHROPIC_API_KEY` to `.env`",
                    inline=False,
                )
            proof.set_footer(text=f"provider={provider_label}")
            embeds.append(proof)

        await send_to_channel(bot, CHANNEL_CONTENT_QUEUE, embeds)

    except Exception as exc:
        logger.error("[job:facebook_generate] Notification error: %s", exc)
