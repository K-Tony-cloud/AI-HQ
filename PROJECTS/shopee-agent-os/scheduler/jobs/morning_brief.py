"""08:00 daily — Morning Brief job."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_morning_brief(bot=None) -> None:
    """
    08:00 Bangkok — Send morning brief to Discord:
    Top Opportunities, Top Viral, Top Profit, Daily Picks, Content Worklist.
    """
    logger.info("[job:morning_brief] Starting")

    from discord_bot.config import (
        CHANNEL_MORNING_BRIEF,
        CHANNEL_DAILY_PICKS,
        CHANNEL_CONTENT_QUEUE,
    )
    from discord_bot.embeds.operator_embeds import build_morning_brief_embeds
    from discord_bot.embeds.discovery_embeds import build_daily_picks_embed
    from discord_bot.embeds.scheduler_embeds import build_content_worklist_embed
    from discord_bot.services.operator_service import get_morning_brief
    from discord_bot.services.discovery_service import get_daily_picks
    from scheduler.notifications.discord_notify import send_to_channel
    from shopee_engine.operator_center import content_worklist

    try:
        result = get_morning_brief(top=5)
        if result["success"]:
            embeds = build_morning_brief_embeds(result["data"])
            await send_to_channel(bot, CHANNEL_MORNING_BRIEF, embeds)
            logger.info("[job:morning_brief] Morning brief sent (%d embeds)", len(embeds))
        else:
            logger.error("[job:morning_brief] morning_brief failed: %s", result["error"])
    except Exception as exc:
        logger.error("[job:morning_brief] Error: %s", exc)

    try:
        picks_result = get_daily_picks(top=5)
        if picks_result["success"]:
            picks_embeds = build_daily_picks_embed(picks_result["data"])

            # Part 7 — validate affiliate coverage before sending
            try:
                from shopee_engine.affiliate_products_engine import validate_daily_picks_coverage
                coverage = validate_daily_picks_coverage(picks_result["data"])
                if coverage["missing"] > 0:
                    import discord as _discord
                    warn_embed = _discord.Embed(
                        title="⚠️ Missing Affiliate Links in Daily Picks",
                        color=_discord.Color.orange(),
                    )
                    warn_embed.add_field(
                        name="Coverage",
                        value=f"{coverage['covered']}/{coverage['total']} products have links",
                        inline=False,
                    )
                    missing_lines = "\n".join(
                        f"• [{m['bucket']}] `{m['itemid']}` {m['title'][:45]}"
                        for m in coverage["missing_items"][:10]
                    )
                    warn_embed.add_field(
                        name="Missing Links",
                        value=missing_lines or "—",
                        inline=False,
                    )
                    warn_embed.set_footer(text="Use /affiliate-product-add to add missing links")
                    picks_embeds = [warn_embed] + list(picks_embeds)
            except Exception as val_exc:
                logger.warning("[job:morning_brief] Affiliate validation error: %s", val_exc)

            await send_to_channel(bot, CHANNEL_DAILY_PICKS, picks_embeds)
            logger.info("[job:morning_brief] Daily picks sent (%d buckets)", len(picks_embeds))
    except Exception as exc:
        logger.error("[job:morning_brief] Daily picks error: %s", exc)

    try:
        worklist = content_worklist(top=10)
        if worklist:
            wl_embed = build_content_worklist_embed(worklist)
            await send_to_channel(bot, CHANNEL_CONTENT_QUEUE, [wl_embed])
            logger.info("[job:morning_brief] Worklist sent (%d items)", len(worklist))
    except Exception as exc:
        logger.error("[job:morning_brief] Content worklist error: %s", exc)

    logger.info("[job:morning_brief] Done")
