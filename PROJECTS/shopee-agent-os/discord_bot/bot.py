"""ShopeeBot — Discord Command Center entry point."""

from __future__ import annotations

import discord
from discord.ext import commands

from .config import DISCORD_GUILD_ID, DISCORD_TOKEN


class ShopeeBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        from .commands.discovery      import DiscoveryCog
        from .commands.performance    import PerformanceCog
        from .commands.content        import ContentCog
        from .commands.operator       import OperatorCog
        from .commands.scheduler_cmds import SchedulerCog
        from .commands.affiliate_cmds import AffiliateCog

        await self.add_cog(DiscoveryCog(self))
        await self.add_cog(PerformanceCog(self))
        await self.add_cog(ContentCog(self))
        await self.add_cog(OperatorCog(self))
        await self.add_cog(SchedulerCog(self))
        await self.add_cog(AffiliateCog(self))

        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"[bot] Commands synced to guild {DISCORD_GUILD_ID}")
        else:
            await self.tree.sync()
            print("[bot] Commands synced globally (may take up to 1 hour)")

    async def on_ready(self) -> None:
        print(f"[bot] ✅ Logged in as {self.user}  |  {len(self.guilds)} guild(s)")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Shopee Affiliate Intelligence 🛒",
            )
        )


def run() -> None:
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set. Create a .env file — see .env.example")
    bot = ShopeeBot()
    bot.run(DISCORD_TOKEN, log_handler=None)
