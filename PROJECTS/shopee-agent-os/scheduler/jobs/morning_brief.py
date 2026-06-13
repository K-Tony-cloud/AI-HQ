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

    from discord_bot.config import CHANNEL_DAILY_PICKS
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
            await send_to_channel(bot, CHANNEL_DAILY_PICKS, embeds)
            logger.info("[job:morning_brief] Morning brief sent (%d embeds)", len(embeds))
        else:
            logger.error("[job:morning_brief] morning_brief failed: %s", result["error"])
    except Exception as exc:
        logger.error("[job:morning_brief] Error: %s", exc)

    try:
        picks_result = get_daily_picks(top=5)
        if picks_result["success"]:
            picks_embeds = build_daily_picks_embed(picks_result["data"])
            await send_to_channel(bot, CHANNEL_DAILY_PICKS, picks_embeds)
            logger.info("[job:morning_brief] Daily picks sent (%d buckets)", len(picks_embeds))
    except Exception as exc:
        logger.error("[job:morning_brief] Daily picks error: %s", exc)

    try:
        worklist = content_worklist(top=10)
        if worklist:
            wl_embed = build_content_worklist_embed(worklist)
            await send_to_channel(bot, CHANNEL_DAILY_PICKS, [wl_embed])
            logger.info("[job:morning_brief] Worklist sent (%d items)", len(worklist))
    except Exception as exc:
        logger.error("[job:morning_brief] Content worklist error: %s", exc)

    logger.info("[job:morning_brief] Done")
