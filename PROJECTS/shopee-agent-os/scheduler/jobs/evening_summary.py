"""18:00 daily — Evening Executive Summary job."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_evening_summary(bot=None) -> None:
    """
    18:00 Bangkok — Send executive summary to Discord:
    Performance Summary, Top Profit, New Opportunities, Risks.
    """
    logger.info("[job:evening_summary] Starting")

    from discord_bot.config import CHANNEL_REVENUE
    from discord_bot.embeds.operator_embeds import build_executive_summary_embeds
    from discord_bot.services.operator_service import get_executive_summary
    from scheduler.notifications.discord_notify import send_to_channel

    try:
        result = get_executive_summary()
        if result["success"]:
            embeds = build_executive_summary_embeds(result["data"])
            await send_to_channel(bot, CHANNEL_REVENUE, embeds)
            logger.info("[job:evening_summary] Sent %d embeds", len(embeds))
        else:
            logger.error("[job:evening_summary] executive_summary failed: %s", result["error"])
    except Exception as exc:
        logger.error("[job:evening_summary] Error: %s", exc)

    logger.info("[job:evening_summary] Done")
