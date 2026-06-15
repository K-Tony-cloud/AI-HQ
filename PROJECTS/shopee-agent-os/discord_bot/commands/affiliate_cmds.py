"""Slash commands: /link-coverage, /missing-links, /import-links"""

from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import error_embed, send_and_confirm


DEFAULT_IMPORT_PATH = "exports/link-tasks"


def _coverage_embed(data: dict) -> discord.Embed:
    total   = data["total"]
    covered = data["covered"]
    missing = data["missing"]
    pct     = data["coverage"]

    bar_filled = int(pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    color = discord.Color.green() if pct >= 80 else discord.Color.yellow() if pct >= 40 else discord.Color.red()

    embed = discord.Embed(
        title="🔗 Affiliate Link Coverage",
        color=color,
    )
    embed.add_field(name="Coverage",       value=f"{pct}%  {bar}", inline=False)
    embed.add_field(name="Total products", value=str(total),   inline=True)
    embed.add_field(name="✅ With link",   value=str(covered), inline=True)
    embed.add_field(name="⚠️ Missing",     value=str(missing), inline=True)

    if missing > 0:
        embed.add_field(
            name="Next step",
            value=(
                "```\n"
                "shopee export-link-tasks --top 50\n"
                "# Fill affiliate_link column in the CSV\n"
                "shopee import-affiliate-links <file>\n"
                "```"
            ),
            inline=False,
        )
    return embed


def _missing_links_embeds(data: dict) -> list[discord.Embed]:
    missing = [d for d in data["details"] if not d["covered"]]
    if not missing:
        embed = discord.Embed(
            title="✅ All top products have affiliate links!",
            color=discord.Color.green(),
        )
        return [embed]

    embeds: list[discord.Embed] = []
    chunk_size = 10
    for page_start in range(0, len(missing), chunk_size):
        chunk = missing[page_start:page_start + chunk_size]
        embed = discord.Embed(
            title=f"⚠️ Missing Affiliate Links ({len(missing)} total)",
            color=discord.Color.red(),
        )
        lines = []
        for i, d in enumerate(chunk, page_start + 1):
            title = str(d["title"])[:55]
            lines.append(f"`{i:>2}.` {title}")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Run: shopee export-link-tasks  →  fill CSV  →  shopee import-affiliate-links")
        embeds.append(embed)

    return embeds[:3]  # Discord limit — first 30 missing max


def _bulk_add_embed(data: dict) -> discord.Embed:
    imported   = data["imported"]
    updated    = data.get("updated", 0)
    total      = data["total"]
    unmatched  = data.get("needs_manual_match", 0)
    invalid    = data["invalid"]
    dup_links  = data.get("duplicate_links", 0)

    color = (
        discord.Color.green()  if imported > 0 and unmatched == 0 and invalid == 0
        else discord.Color.yellow() if imported > 0 or updated > 0
        else discord.Color.orange() if unmatched > 0 and invalid == 0
        else discord.Color.red()
    )
    embed = discord.Embed(title="🔗 Bulk Affiliate Links — Import Summary", color=color)
    embed.add_field(name="📥 Received",           value=str(total),     inline=True)
    embed.add_field(name="✅ Saved (new)",         value=str(imported),  inline=True)
    embed.add_field(name="🔄 Updated (new link)",  value=str(updated),   inline=True)
    embed.add_field(name="🔍 Needs manual match",  value=str(unmatched), inline=True)
    embed.add_field(name="♻️ Duplicate link",      value=str(dup_links), inline=True)
    embed.add_field(name="❌ Invalid",             value=str(invalid),   inline=True)

    if data.get("imported_products"):
        lines = "\n".join(
            f"`{i:>2}.` {p['title'][:50]}"
            for i, p in enumerate(data["imported_products"][:10], 1)
        )
        embed.add_field(name="✅ Saved products", value=lines, inline=False)

    if data.get("updated_products"):
        lines = "\n".join(
            f"`{i:>2}.` {p['title'][:50]}"
            for i, p in enumerate(data["updated_products"][:5], 1)
        )
        embed.add_field(name="🔄 Updated products", value=lines, inline=False)

    if data.get("unmatched_links"):
        parts = []
        for u in data["unmatched_links"][:5]:
            resolved = u.get("resolved") or ""
            uid = u.get("unmatched_id", "?")
            parts.append(
                f"• `{u['original'][:35]}`\n"
                f"  → `{resolved[:50] or 'no response'}`\n"
                f"  ↳ Use `/affiliate-link-match {uid} <keyword>`"
            )
        embed.add_field(name="🔍 Needs manual match", value="\n".join(parts), inline=False)

    return embed


def _import_status_embed(import_path: str) -> discord.Embed:
    """Check if a filled CSV exists locally and report its status."""
    base = Path(import_path)
    candidates: list[Path] = []
    if base.exists() and base.is_dir():
        candidates = sorted(base.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    elif base.exists() and base.is_file():
        candidates = [base]

    if not candidates:
        embed = discord.Embed(
            title="📂 Import Status",
            description=(
                f"No CSV files found in `{import_path}`\n\n"
                "**To create one:**\n"
                "```\nshopee export-link-tasks --top 50\n```\n"
                "Fill the `affiliate_link` column, then run:\n"
                "```\nshopee import-affiliate-links <file>\n```"
            ),
            color=discord.Color.orange(),
        )
        return embed

    latest = candidates[0]
    import csv as csv_mod
    try:
        with open(latest, encoding="utf-8-sig") as fh:
            rows = list(csv_mod.DictReader(fh))
        total    = len(rows)
        filled   = sum(1 for r in rows if str(r.get("affiliate_link", "")).strip())
        empty    = total - filled
        embed = discord.Embed(
            title="📂 Import Status",
            color=discord.Color.blue() if filled > 0 else discord.Color.orange(),
        )
        embed.add_field(name="File",          value=f"`{latest.name}`",  inline=False)
        embed.add_field(name="Total rows",    value=str(total),          inline=True)
        embed.add_field(name="✅ Filled",     value=str(filled),         inline=True)
        embed.add_field(name="⬜ Empty",      value=str(empty),          inline=True)
        if filled > 0:
            embed.add_field(
                name="Ready to import",
                value=f"```\nshopee import-affiliate-links exports/link-tasks/{latest.name}\n```",
                inline=False,
            )
        else:
            embed.add_field(
                name="Action needed",
                value="Open the CSV, go to [affiliate.shopee.co.th](https://affiliate.shopee.co.th) → Create Link → fill `affiliate_link` column",
                inline=False,
            )
    except Exception as exc:
        embed = discord.Embed(
            title="📂 Import Status",
            description=f"Error reading `{latest.name}`: {exc}",
            color=discord.Color.red(),
        )
    return embed


class AffiliateCog(commands.Cog, name="Affiliate Links"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /link-coverage
    # ------------------------------------------------------------------
    @app_commands.command(name="link-coverage", description="Show affiliate link coverage for top products")
    @app_commands.describe(top="Number of top products to check (default 50)")
    async def cmd_link_coverage(
        self,
        interaction: discord.Interaction,
        top: int = 50,
    ) -> None:
        from discord_bot.config import CHANNEL_LINK_COVERAGE
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_link_engine import link_coverage_report
            data = link_coverage_report(top=top)
            embed = _coverage_embed(data)
            await send_and_confirm(interaction, [embed], CHANNEL_LINK_COVERAGE)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Link Coverage", str(exc)))

    # ------------------------------------------------------------------
    # /missing-links
    # ------------------------------------------------------------------
    @app_commands.command(name="missing-links", description="List top products without affiliate links")
    @app_commands.describe(top="Number of top products to check (default 50)")
    async def cmd_missing_links(
        self,
        interaction: discord.Interaction,
        top: int = 50,
    ) -> None:
        from discord_bot.config import CHANNEL_MISSING_LINKS
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_link_engine import link_coverage_report
            data = link_coverage_report(top=top)
            embeds = _missing_links_embeds(data)
            await send_and_confirm(interaction, embeds[:10], CHANNEL_MISSING_LINKS)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Missing Links", str(exc)))

    # ------------------------------------------------------------------
    # /import-links  (status check only — no file upload, no scraping)
    # ------------------------------------------------------------------
    @app_commands.command(name="import-links", description="Check status of local affiliate link CSV (read-only)")
    @app_commands.describe(path="Local path to check (default: exports/link-tasks/)")
    async def cmd_import_links(
        self,
        interaction: discord.Interaction,
        path: str = DEFAULT_IMPORT_PATH,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            embed = _import_status_embed(path)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Import Links Status", str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-match  — manually match an unmatched link
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-match",
        description="Manually match an unmatched affiliate link to a product by keyword",
    )
    @app_commands.describe(
        unmatched_id="ID shown in the 'Needs manual match' section",
        product_keyword="Product keyword or title to search for",
    )
    async def cmd_affiliate_link_match(
        self,
        interaction: discord.Interaction,
        unmatched_id: int,
        product_keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            import asyncio
            from shopee_engine.affiliate_link_engine import manual_match_affiliate_link
            from discord_bot.config import CHANNEL_AFFILIATE_LINKS
            result = await asyncio.to_thread(manual_match_affiliate_link, unmatched_id, product_keyword)
            if result["success"]:
                product = result["product"]
                embed = discord.Embed(title="✅ Manual Match Successful", color=discord.Color.green())
                embed.add_field(name="Unmatched ID", value=str(unmatched_id), inline=True)
                embed.add_field(name="Matched Product", value=product["title"][:80], inline=False)
                embed.add_field(name="Affiliate Link", value=f"`{result['affiliate_link'][:80]}`", inline=False)
            else:
                embed = discord.Embed(title="❌ Manual Match Failed", description=result["error"], color=discord.Color.red())
            await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Affiliate Link Match", str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-add  — bulk paste affiliate short links
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-add",
        description="Bulk-add affiliate links — paste multiple Shopee short links (one per line)",
    )
    @app_commands.describe(
        links="Paste affiliate links separated by newlines or spaces",
        campaign="Campaign tag e.g. daily-picks (optional)",
        platform="Platform tag e.g. tiktok (optional)",
    )
    async def cmd_affiliate_link_add(
        self,
        interaction: discord.Interaction,
        links: str,
        campaign: str = "daily-picks",
        platform: str = "tiktok",
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            import asyncio
            from shopee_engine.affiliate_link_engine import bulk_add_affiliate_links

            # Accept newline, comma, or space-separated links
            link_list = [
                lnk.strip()
                for lnk in links.replace(",", "\n").splitlines()
                if lnk.strip()
            ]
            if not link_list:
                await interaction.followup.send(
                    embed=error_embed("Affiliate Link Add", "No valid links found in input.")
                )
                return

            from discord_bot.config import CHANNEL_AFFILIATE_LINKS
            data = await asyncio.to_thread(
                bulk_add_affiliate_links, link_list, campaign, platform
            )
            embed = _bulk_add_embed(data)
            await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Affiliate Link Add", str(exc)))
