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
        from .commands.creative_cmds  import CreativeCog
        from .commands.asset_cmds     import AssetCog
        from .commands.revenue_cmds   import RevenueCog
        from .commands.system_cmds    import SystemCog
        from .commands.facebook_cmds  import FacebookCog
        from .commands.insights_cmds  import InsightsCog
        from .commands.editorial_cmds import EditorialCog

        await self.add_cog(DiscoveryCog(self))
        await self.add_cog(PerformanceCog(self))
        await self.add_cog(ContentCog(self))
        await self.add_cog(OperatorCog(self))
        await self.add_cog(SchedulerCog(self))
        await self.add_cog(AffiliateCog(self))
        await self.add_cog(CreativeCog(self))
        await self.add_cog(AssetCog(self))
        await self.add_cog(RevenueCog(self))
        await self.add_cog(SystemCog(self))
        await self.add_cog(FacebookCog(self))
        await self.add_cog(InsightsCog(self))
        await self.add_cog(EditorialCog(self))

        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"[bot] Commands synced to guild {DISCORD_GUILD_ID}: {len(synced)} commands")
            for cmd in sorted(synced, key=lambda c: c.name):
                print(f"  /{cmd.name}")
        else:
            synced = await self.tree.sync()
            print(f"[bot] Commands synced globally: {len(synced)} commands")

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
