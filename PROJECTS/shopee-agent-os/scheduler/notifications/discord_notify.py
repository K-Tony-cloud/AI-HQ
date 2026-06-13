"""Send Discord embeds from scheduled jobs via the bot client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)


async def send_to_channel(
    bot,
    channel_id: int | None,
    embeds: list,
    content: str | None = None,
    files: list | None = None,
) -> bool:
    """
    Send embeds (and optional file attachments) to a Discord channel.

    Discord allows up to 10 embeds per message; larger lists are split
    into sequential messages. Returns True if delivery succeeded.
    """
    if not channel_id:
        logger.warning("[notify] No channel_id configured — skipping Discord send")
        return False
    if not bot:
        logger.warning("[notify] No bot instance — skipping Discord send")
        return False
    if not embeds and not files:
        logger.warning("[notify] Nothing to send (no embeds, no files)")
        return False

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        EMBED_LIMIT = 10
        if embeds:
            first_batch = embeds[:EMBED_LIMIT]
            await channel.send(
                content=content,
                embeds=first_batch,
                files=files or [],
            )
            for i in range(EMBED_LIMIT, len(embeds), EMBED_LIMIT):
                await channel.send(embeds=embeds[i : i + EMBED_LIMIT])
        elif files:
            await channel.send(content=content, files=files)

        logger.info("[notify] Sent %d embed(s) to channel %s", len(embeds or []), channel_id)
        return True

    except Exception as exc:
        logger.error("[notify] Failed to send to channel %s: %s", channel_id, exc)
        return False
