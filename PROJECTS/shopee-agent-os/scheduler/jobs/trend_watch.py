"""12:00 daily — Midday Trend Watch job."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_trend_watch(bot=None) -> None:
    """
    12:00 Bangkok — Send midday trend watch to Discord:
    Social Momentum, Promo Surge, New Viral Candidates.
    """
    logger.info("[job:trend_watch] Starting")

    from discord_bot.config import CHANNEL_ANALYTICS
    from discord_bot.embeds.scheduler_embeds import build_trend_watch_embeds
    from scheduler.notifications.discord_notify import send_to_channel
    from shopee_engine.operator_center import trend_watch

    try:
        data = trend_watch(top=10)
        embeds = build_trend_watch_embeds(data)
        await send_to_channel(bot, CHANNEL_ANALYTICS, embeds)
        logger.info("[job:trend_watch] Sent %d embeds", len(embeds))
    except Exception as exc:
        logger.error("[job:trend_watch] Error: %s", exc)

    logger.info("[job:trend_watch] Done")
