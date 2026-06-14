"""Slash commands: /link-coverage, /missing-links, /import-links"""

from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.embeds.base import error_embed


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
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_link_engine import link_coverage_report
            data = link_coverage_report(top=top)
            embed = _coverage_embed(data)
            await interaction.followup.send(embed=embed)
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
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_link_engine import link_coverage_report
            data = link_coverage_report(top=top)
            embeds = _missing_links_embeds(data)
            await interaction.followup.send(embeds=embeds[:10])
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
