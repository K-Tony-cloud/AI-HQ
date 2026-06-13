"""06:30 daily — Auto Queue Generator job."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

AUTO_QUEUE_CATEGORIES = ["Gadget", "Home", "Mobile", "Baby", "Health", "Camping"]
PRODUCTS_PER_CATEGORY = 3


async def run_auto_queue(bot=None) -> None:
    """
    06:30 Bangkok — Auto-generate content queue for 6 categories.
    Pulls top 3 products per category and queues them as draft packs.
    """
    logger.info("[job:auto_queue] Starting — categories: %s", AUTO_QUEUE_CATEGORIES)

    from discord_bot.config import CHANNEL_CONTENT_QUEUE
    from discord_bot.embeds.scheduler_embeds import build_auto_queue_result_embed
    from scheduler.notifications.discord_notify import send_to_channel
    from shopee_engine.operator_center import category_brief
    from shopee_engine.content_engine import queue_add

    results: dict[str, list[str]] = {}
    total_ok = 0
    total_skip = 0

    for category in AUTO_QUEUE_CATEGORIES:
        queued: list[str] = []
        try:
            brief = category_brief(category=category, top=PRODUCTS_PER_CATEGORY * 3)
            products = brief.get("products", [])[:PRODUCTS_PER_CATEGORY]
            for row in products:
                name = str(row[0] if isinstance(row, (tuple, list)) else row.get("name", ""))[:60]
                if not name:
                    continue
                try:
                    queue_add(name, provider="template")
                    queued.append(name)
                    total_ok += 1
                except Exception as exc:
                    logger.warning("[job:auto_queue] skip '%s': %s", name[:40], exc)
                    total_skip += 1
        except Exception as exc:
            logger.error("[job:auto_queue] category '%s' error: %s", category, exc)

        results[category] = queued

    logger.info(
        "[job:auto_queue] Complete — %d queued, %d skipped",
        total_ok, total_skip,
    )

    try:
        embed = build_auto_queue_result_embed(results, total_ok, total_skip)
        await send_to_channel(bot, CHANNEL_CONTENT_QUEUE, [embed])
    except Exception as exc:
        logger.error("[job:auto_queue] Notification error: %s", exc)
