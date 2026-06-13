"""
Entry point: python -m scheduler

Runs the ShopeeScheduler standalone (without a Discord bot UI).
Connects a minimal Discord client for sending scheduled messages to channels.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("shopee.scheduler")


async def _run() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass

    import discord
    from discord_bot.config import DISCORD_TOKEN, DISCORD_GUILD_ID
    from scheduler.scheduler import ShopeeScheduler

    if not DISCORD_TOKEN:
        logger.warning(
            "DISCORD_TOKEN not set — scheduler will run but cannot send Discord messages."
        )

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    scheduler = ShopeeScheduler(bot=client)

    @client.event
    async def on_ready():
        logger.info("Discord client ready as %s", client.user)
        scheduler.start()
        logger.info("Scheduler running. Press Ctrl+C to stop.")

    loop = asyncio.get_event_loop()

    def _shutdown(*_):
        logger.info("Shutting down…")
        scheduler.stop()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass  # Windows

    if DISCORD_TOKEN:
        await client.start(DISCORD_TOKEN)
    else:
        scheduler.start()
        logger.info("Running in no-Discord mode. Ctrl+C to stop.")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            scheduler.stop()


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
