"""Slash commands: /link-coverage, /missing-links, /import-links"""

from __future__ import annotations

import asyncio
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


def _review_summary_embed(session: dict, stage: str = "pending") -> discord.Embed:
    """Summary embed for a staging session."""
    counts = session["counts"]
    total  = counts["total"]
    high   = counts["high"]
    review = counts["review"]
    nf     = counts["not_found"]

    color = (
        discord.Color.green()  if high == total
        else discord.Color.yellow() if high > 0
        else discord.Color.orange()
    )
    embed = discord.Embed(
        title=f"📋 Affiliate Link Review — Session `{session['session_id']}`",
        color=color,
    )
    embed.add_field(name="📥 Total",              value=str(total),  inline=True)
    embed.add_field(name="✅ High confidence",    value=str(high),   inline=True)
    embed.add_field(name="⚠️ Needs review",       value=str(review), inline=True)
    embed.add_field(name="❌ Not found",          value=str(nf),     inline=True)

    if stage == "confirmed":
        embed.description = "✅ **Confirmed items have been saved.**"
    elif stage == "cancelled":
        embed.description = "❌ **Session cancelled. Nothing was saved.**"

    return embed


def _review_items_embed(session: dict, page: int = 0, page_size: int = 10) -> discord.Embed:
    """Detail embed showing pending items for a session page."""
    items = session["items"]
    start = page * page_size
    chunk = items[start:start + page_size]
    total_pages = max(1, (len(items) + page_size - 1) // page_size)

    embed = discord.Embed(
        title=f"🔍 Review Items (page {page+1}/{total_pages})",
        color=discord.Color.blue(),
    )
    lines = []
    for it in chunk:
        label = it["confidence_label"]
        emoji = {"HIGH": "✅", "REVIEW": "⚠️", "NOT_FOUND": "❌"}.get(label, "❓")
        link_short = it["affiliate_link"][-15:]
        score = it["confidence"]
        title = (it["title"] or "—")[:45]
        existing = f"\n    ⚠️ Has existing link" if it["existing_link"] else ""
        if it["shopid"]:
            lines.append(
                f"{emoji} `...{link_short}` → **{title}**\n"
                f"    shopid=`{it['shopid']}` itemid=`{it['itemid']}` score={score}{existing}"
            )
        else:
            lines.append(f"{emoji} `...{link_short}` → *{label}*")
    embed.description = "\n\n".join(lines) or "No items."
    embed.set_footer(text=f"Session {session['session_id']} • IDs {[it['id'] for it in chunk]}")
    return embed


class AffiliateReviewView(discord.ui.View):
    """Buttons for confirm-before-save affiliate link review."""

    def __init__(self, session: dict, invoker_name: str) -> None:
        super().__init__(timeout=600)
        self.session      = session
        self.invoker_name = invoker_name
        self.done         = False
        high_ids = [it["id"] for it in session["items"] if it["confidence_label"] == "HIGH"]
        if not high_ids:
            self.confirm_high.disabled = True

    @discord.ui.button(label="✅ Confirm All High Confidence", style=discord.ButtonStyle.green, row=0)
    async def confirm_high(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.done:
            await interaction.response.defer()
            return
        self.done = True
        for child in self.children:
            child.disabled = True

        from shopee_engine.affiliate_link_engine import confirm_pending_items
        high_ids = [it["id"] for it in self.session["items"] if it["confidence_label"] == "HIGH"]
        result   = await asyncio.to_thread(
            confirm_pending_items, self.session["session_id"], high_ids, self.invoker_name
        )

        summary  = _review_summary_embed(self.session, stage="confirmed")
        saved    = result["saved"]
        updated  = result["updated"]
        summary.add_field(name="✅ Saved (new)",        value=str(saved),   inline=True)
        summary.add_field(name="🔄 Updated (new link)", value=str(updated), inline=True)
        if result["errors"]:
            summary.add_field(name="⚠️ Skipped", value="\n".join(result["errors"][:5]), inline=False)
        if result["saved_items"]:
            lines = "\n".join(f"• {p['title'][:55]}" for p in result["saved_items"][:10])
            summary.add_field(name="Saved products", value=lines, inline=False)

        review_ids = [it["id"] for it in self.session["items"] if it["confidence_label"] in ("REVIEW", "NOT_FOUND")]
        if review_ids:
            lines = []
            for it in self.session["items"]:
                if it["confidence_label"] in ("REVIEW", "NOT_FOUND"):
                    lines.append(
                        f"• `...{it['affiliate_link'][-15:]}` (id={it['id']}) "
                        f"→ `/affiliate-link-match {it['id']} <keyword>`"
                    )
            summary.add_field(
                name="🔍 Needs manual match",
                value="\n".join(lines[:8]),
                inline=False,
            )

        await interaction.response.edit_message(embeds=[summary], view=self)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red, row=0)
    async def cancel_session(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.done:
            await interaction.response.defer()
            return
        self.done = True
        for child in self.children:
            child.disabled = True

        from shopee_engine.affiliate_link_engine import reject_pending_items
        all_ids = [it["id"] for it in self.session["items"]]
        await asyncio.to_thread(
            reject_pending_items, self.session["session_id"], all_ids, self.invoker_name
        )
        summary = _review_summary_embed(self.session, stage="cancelled")
        await interaction.response.edit_message(embeds=[summary], view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True


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
    # /affiliate-link-match  — search products by keyword to match an unmatched link
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-match",
        description="Search products by keyword to match an unmatched affiliate link",
    )
    @app_commands.describe(
        unmatched_id="ID shown in the 'Needs manual match' section",
        product_keyword="Keyword to search products (Thai or English)",
    )
    async def cmd_affiliate_link_match(
        self,
        interaction: discord.Interaction,
        unmatched_id: int,
        product_keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_link_engine import search_products_by_keyword
            candidates = search_products_by_keyword(product_keyword, limit=5)
            if not candidates:
                embed = discord.Embed(
                    title="🔍 No Products Found",
                    description=f"No products matching `{product_keyword[:50]}`.\nTry a different keyword.",
                    color=discord.Color.orange(),
                )
            else:
                embed = discord.Embed(
                    title=f"🔍 Top {len(candidates)} matches for `{product_keyword[:30]}`",
                    description=(
                        f"**Unmatched link ID: `{unmatched_id}`**\n"
                        "Use `/affiliate-link-confirm` with one of these itemids:\n\n"
                        + "\n".join(
                            f"`{i}.` itemid=`{c['itemid']}` shopid=`{c['shopid']}`\n    {c['title'][:60]}"
                            for i, c in enumerate(candidates, 1)
                        )
                    ),
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"/affiliate-link-confirm {unmatched_id} <itemid>")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Affiliate Link Match", str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-confirm  — confirm a manual match by itemid
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-confirm",
        description="Confirm a manual match between an unmatched link and a product by itemid",
    )
    @app_commands.describe(
        unmatched_id="ID from the 'Needs manual match' section",
        itemid="Product itemid from /affiliate-link-match results",
    )
    async def cmd_affiliate_link_confirm(
        self,
        interaction: discord.Interaction,
        unmatched_id: int,
        itemid: int,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            import asyncio
            from shopee_engine.affiliate_link_engine import confirm_affiliate_link
            from discord_bot.config import CHANNEL_AFFILIATE_LINKS
            result = await asyncio.to_thread(confirm_affiliate_link, unmatched_id, itemid)
            if result["success"]:
                product = result["product"]
                embed = discord.Embed(title="✅ Match Confirmed", color=discord.Color.green())
                embed.add_field(name="Unmatched ID", value=str(unmatched_id), inline=True)
                embed.add_field(name="itemid", value=str(itemid), inline=True)
                embed.add_field(name="Product", value=product["title"][:80], inline=False)
                embed.add_field(name="Affiliate Link", value=f"`{result['affiliate_link'][:80]}`", inline=False)
            else:
                embed = discord.Embed(
                    title="❌ Confirm Failed",
                    description=result["error"],
                    color=discord.Color.red(),
                )
            await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Affiliate Link Confirm", str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-add-product  — add one link by searching product keyword
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-add-product",
        description="Add one affiliate link by searching for its product by keyword",
    )
    @app_commands.describe(
        link="Shopee affiliate short link",
        product_keyword="Keyword to identify the product",
    )
    async def cmd_affiliate_link_add_product(
        self,
        interaction: discord.Interaction,
        link: str,
        product_keyword: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            import asyncio
            from shopee_engine.affiliate_link_engine import (
                search_products_by_keyword,
                bulk_add_affiliate_links,
            )
            from discord_bot.config import CHANNEL_AFFILIATE_LINKS

            candidates = search_products_by_keyword(product_keyword, limit=5)

            if not candidates:
                embed = discord.Embed(
                    title="🔍 No Products Found",
                    description=f"No products matching `{product_keyword[:50]}`.",
                    color=discord.Color.orange(),
                )
                await interaction.followup.send(embed=embed)
                return

            if len(candidates) == 1:
                # One strong match — save directly using its product URL as the proxy
                product = candidates[0]
                data = await asyncio.to_thread(
                    bulk_add_affiliate_links, [link],
                )
                # Override: if needs_manual_match, force-match to the found product
                if data["needs_manual_match"] > 0 and data["unmatched_links"]:
                    uid = data["unmatched_links"][0].get("unmatched_id")
                    if uid:
                        from shopee_engine.affiliate_link_engine import confirm_affiliate_link
                        result = await asyncio.to_thread(confirm_affiliate_link, uid, product["itemid"])
                        if result["success"]:
                            embed = discord.Embed(title="✅ Saved", color=discord.Color.green())
                            embed.add_field(name="Product", value=product["title"][:80], inline=False)
                            embed.add_field(name="Link", value=f"`{link[:80]}`", inline=False)
                            await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)
                            return
                embed = _bulk_add_embed(data)
                await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)
            else:
                # Multiple matches — show choices
                embed = discord.Embed(
                    title=f"🔍 {len(candidates)} matches — pick one",
                    description=(
                        f"Link: `{link[:60]}`\n\n"
                        "Run `/affiliate-link-add` first, then use `/affiliate-link-confirm`:\n\n"
                        + "\n".join(
                            f"`{i}.` itemid=`{c['itemid']}`  {c['title'][:55]}"
                            for i, c in enumerate(candidates, 1)
                        )
                    ),
                    color=discord.Color.blue(),
                )
                await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Affiliate Link Add Product", str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-debug  — full redirect trace and extraction diagnostic
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-debug",
        description="Show the full redirect trace and extraction result for an affiliate link",
    )
    @app_commands.describe(link="Shopee affiliate short link to diagnose")
    async def cmd_affiliate_link_debug(
        self,
        interaction: discord.Interaction,
        link: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            import asyncio
            from shopee_engine.affiliate_link_engine import debug_affiliate_link

            info = await asyncio.to_thread(debug_affiliate_link, link)

            status_emoji = {
                "IDS_FOUND":              "✅",
                "VALID_NEEDS_MANUAL_MATCH": "🔍",
                "INVALID_UNREACHABLE":    "❌",
            }.get(info["status"], "⚠️")

            color = {
                "IDS_FOUND":              discord.Color.green(),
                "VALID_NEEDS_MANUAL_MATCH": discord.Color.blue(),
                "INVALID_UNREACHABLE":    discord.Color.red(),
            }.get(info["status"], discord.Color.orange())

            embed = discord.Embed(
                title=f"{status_emoji} Affiliate Link Debug",
                color=color,
            )
            embed.add_field(name="Original",    value=f"`{info['original'][:80]}`",  inline=False)
            embed.add_field(name="HTTP Status", value=str(info["http_status"] or "error"), inline=True)
            embed.add_field(name="Reachable",   value="✅ Yes" if info["reachable"] else "❌ No", inline=True)
            embed.add_field(name="Status",      value=info["status"], inline=True)

            chain = info.get("chain", [])
            if len(chain) > 1:
                embed.add_field(
                    name="Redirect Chain",
                    value="\n".join(f"→ `{u[:70]}`" for u in chain),
                    inline=False,
                )
            else:
                embed.add_field(name="Final URL", value=f"`{(info['final_url'] or 'none')[:80]}`", inline=False)

            if info.get("og_url"):
                embed.add_field(name="og:url", value=f"`{info['og_url'][:80]}`", inline=False)
            if info.get("page_title"):
                embed.add_field(name="Page title", value=info["page_title"][:100], inline=False)
            if info.get("shopid"):
                embed.add_field(name="shopid", value=str(info["shopid"]), inline=True)
                embed.add_field(name="itemid", value=str(info["itemid"]), inline=True)
                embed.add_field(name="Identity method", value=info["identity_method"], inline=True)

            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed("Affiliate Link Debug", str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-product-add  — add product from long URL + short link
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-product-add",
        description="Add a product using its long affiliate URL + short link",
    )
    @app_commands.describe(
        long_url="Long Shopee affiliate URL (contains product IDs in the path)",
        short_url="Short affiliate URL used for posting",
        campaign="Campaign tag e.g. daily-picks (optional)",
        platform="Platform tag e.g. tiktok (optional)",
    )
    async def cmd_affiliate_product_add(
        self,
        interaction: discord.Interaction,
        long_url:  str,
        short_url: str,
        campaign:  str = "daily-picks",
        platform:  str = "tiktok",
    ) -> None:
        from discord_bot.config import CHANNEL_AFFILIATE_LINKS
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import add_affiliate_product
            result = await asyncio.to_thread(
                add_affiliate_product, long_url, short_url, campaign, platform
            )
            if not result["success"]:
                await interaction.followup.send(
                    embed=error_embed("Add Product Failed", result["error"])
                )
                return

            action = result["action"]
            embed  = discord.Embed(
                title="✅ Product Added" if action == "added" else "🔄 Product Updated",
                color=discord.Color.green() if action == "added" else discord.Color.blue(),
            )
            embed.add_field(name="Title",      value=result["title"] or "—",    inline=False)
            embed.add_field(name="ItemID",     value=str(result["itemid"]),      inline=True)
            embed.add_field(name="ShopID",     value=str(result["shopid"]),      inline=True)
            embed.add_field(name="Short Link", value=f"`{short_url[:80]}`",      inline=False)
            embed.add_field(name="Status",     value="Saved" if action == "added" else "Updated", inline=True)

            # Auto-fetch product images into asset library (fire-and-forget)
            try:
                from shopee_engine.asset_engine import fetch_and_save_product_assets
                asset_r = await asyncio.to_thread(
                    fetch_and_save_product_assets,
                    result["itemid"],
                    result["shopid"],
                )
                if asset_r.get("success") and asset_r.get("image_1"):
                    embed.set_thumbnail(url=asset_r["image_1"])
                    embed.add_field(name="🖼️ Assets", value="Images saved to asset library ✅", inline=False)
            except Exception:
                pass  # asset fetch failure must never block product-add

            await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)

        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-update  — replace short URL for existing product
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-update",
        description="Update the short affiliate link for an existing product",
    )
    @app_commands.describe(
        product="Product keyword or itemid",
        new_short_url="New short affiliate URL",
    )
    async def cmd_affiliate_link_update(
        self,
        interaction: discord.Interaction,
        product:      str,
        new_short_url: str,
    ) -> None:
        from discord_bot.config import CHANNEL_AFFILIATE_LINKS
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import update_affiliate_short_url
            result = await asyncio.to_thread(update_affiliate_short_url, product, new_short_url)

            if not result["success"]:
                if result.get("candidates"):
                    lines = "\n".join(
                        f"`{c['itemid']}` — {c['title'][:55]}\n  → `{(c['current_link'] or '—')[:60]}`"
                        for c in result["candidates"]
                    )
                    embed = discord.Embed(
                        title="🔍 Multiple matches — be more specific",
                        description=f"{result['error']}\n\n{lines}",
                        color=discord.Color.orange(),
                    )
                else:
                    embed = error_embed("Update Failed", result["error"])
                await interaction.followup.send(embed=embed)
                return

            p = result["product"]
            embed = discord.Embed(title="🔄 Affiliate Link Updated", color=discord.Color.blue())
            embed.add_field(name="Product",     value=p["title"][:80],                        inline=False)
            embed.add_field(name="Old Link",    value=f"`{result['old_link'][:80] or '—'}`",  inline=False)
            embed.add_field(name="New Link",    value=f"`{result['new_link'][:80]}`",          inline=False)
            embed.add_field(name="Latest Link", value="YES",                                   inline=True)
            await send_and_confirm(interaction, [embed], CHANNEL_AFFILIATE_LINKS)

        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-search  — search products in affiliate_products table
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-search",
        description="Search affiliate products by title, keyword, itemid or shopid",
    )
    @app_commands.describe(query="Title keyword, itemid, or shopid")
    async def cmd_affiliate_search(
        self,
        interaction: discord.Interaction,
        query: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import search_affiliate_products
            results = await asyncio.to_thread(search_affiliate_products, query)

            if not results:
                embed = discord.Embed(
                    title="🔍 No Products Found",
                    description=f"No affiliate products matching `{query[:50]}`.",
                    color=discord.Color.orange(),
                )
            else:
                embed = discord.Embed(
                    title=f"🔍 Affiliate Products — {len(results)} result(s)",
                    color=discord.Color.blue(),
                )
                lines = []
                for p in results:
                    link    = p["affiliate_short_url"] or "—"
                    updated = (p["updated_at"] or "")[:10]
                    cat     = p["category"] or "—"
                    lines.append(
                        f"**{p['title'][:55]}**\n"
                        f"  itemid=`{p['itemid']}` | {cat} | Updated: {updated}\n"
                        f"  Link: `{link[:70]}`"
                    )
                embed.description = "\n\n".join(lines[:8])
            await interaction.followup.send(embed=embed)

        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-link-add  — stage links for review before saving
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-link-add",
        description="Stage affiliate links for review before saving — paste one or many links",
    )
    @app_commands.describe(
        links="Affiliate links separated by newlines, commas, or spaces",
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
            from shopee_engine.affiliate_link_engine import stage_affiliate_links

            link_list = [
                lnk.strip()
                for lnk in links.replace(",", "\n").splitlines()
                if lnk.strip()
            ]
            if not link_list:
                await interaction.followup.send(
                    embed=error_embed("No valid links found in input.")
                )
                return

            session = await asyncio.to_thread(
                stage_affiliate_links, link_list, campaign, platform
            )

            invoker = str(interaction.user)
            view    = AffiliateReviewView(session, invoker_name=invoker)
            summary = _review_summary_embed(session)
            detail  = _review_items_embed(session)

            await interaction.followup.send(embeds=[summary, detail], view=view)

        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-dashboard
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-dashboard",
        description="Summary of all affiliate products: coverage, categories, recently added",
    )
    async def cmd_affiliate_dashboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import (
                get_dashboard_stats, fix_bad_titles,
            )
            # Auto-fix bad titles silently
            await asyncio.to_thread(fix_bad_titles)
            stats = await asyncio.to_thread(get_dashboard_stats)

            total       = stats["total"]
            with_link   = stats["with_link"]
            without_link = stats["without_link"]
            pct         = round(with_link / total * 100, 1) if total else 0.0

            bar_n    = int(pct / 5)
            bar      = "█" * bar_n + "░" * (20 - bar_n)
            color    = (discord.Color.green()  if pct >= 80
                        else discord.Color.yellow() if pct >= 40
                        else discord.Color.orange())

            embed = discord.Embed(title="📊 Affiliate Products Dashboard", color=color)
            embed.add_field(name="Total Products",        value=str(total),       inline=True)
            embed.add_field(name="✅ With Affiliate Link", value=str(with_link),   inline=True)
            embed.add_field(name="⚠️ Missing Link",       value=str(without_link), inline=True)
            embed.add_field(name="Link Coverage",
                            value=f"{pct}%  {bar}", inline=False)

            # Category breakdown
            cat_bd = stats.get("category_breakdown", {})
            if cat_bd:
                cat_lines = "\n".join(
                    f"• {k}: **{v}**" for k, v in sorted(cat_bd.items(), key=lambda x: -x[1])
                )
                embed.add_field(name="Category Breakdown", value=cat_lines, inline=False)

            # Recently added
            recent = stats.get("recently_added", [])
            if recent:
                lines = "\n".join(
                    f"`{r['itemid']}` {r['title'][:45] or '—'} ({r['created_at']})"
                    for r in recent[:5]
                )
                embed.add_field(name="🕐 Recently Added (last 5)", value=lines, inline=False)

            embed.set_footer(text="Use /affiliate-missing for missing details • /affiliate-coverage for top-N breakdown")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-missing
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-missing",
        description="Show products in Daily Picks / Viral / Opportunities that need affiliate links",
    )
    async def cmd_affiliate_missing(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import get_missing_by_section
            data = await asyncio.to_thread(get_missing_by_section)

            embeds = []

            # Opportunities
            opp = data.get("opportunities", [])
            e1  = discord.Embed(title="🎯 Missing — Top Opportunities", color=discord.Color.red())
            if opp:
                lines = "\n".join(
                    f"`{i:>2}.` **{p['title'][:50] or '—'}**\n"
                    f"      itemid=`{p['itemid']}` | {p['category'][:25]}"
                    for i, p in enumerate(opp[:10], 1)
                )
                e1.description = lines
            else:
                e1.description = "✅ All top opportunities have affiliate links!"
                e1.color = discord.Color.green()
            embeds.append(e1)

            # Viral
            viral = data.get("viral", [])
            e2    = discord.Embed(title="🔥 Missing — Top Viral", color=discord.Color.orange())
            if viral:
                lines = "\n".join(
                    f"`{i:>2}.` **{p['title'][:50] or '—'}**\n"
                    f"      itemid=`{p['itemid']}` | {p['category'][:25]}"
                    for i, p in enumerate(viral[:10], 1)
                )
                e2.description = lines
            else:
                e2.description = "✅ All top viral products have affiliate links!"
                e2.color = discord.Color.green()
            embeds.append(e2)

            # Daily Picks by bucket
            dp = data.get("daily_picks", {})
            if dp:
                e3 = discord.Embed(title="📅 Missing — Daily Picks by Category", color=discord.Color.yellow())
                for bucket, items in dp.items():
                    if items:
                        lines = "\n".join(
                            f"• `{p['itemid']}` {p['title'][:45] or '—'}"
                            for p in items[:3]
                        )
                        e3.add_field(name=f"{bucket.title()} ({len(items)} missing)",
                                     value=lines, inline=False)
                if e3.fields:
                    embeds.append(e3)

            embed_footer = "Use /affiliate-product-add to add missing links"
            for e in embeds:
                e.set_footer(text=embed_footer)

            await interaction.followup.send(embeds=embeds[:4])
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-coverage
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-coverage",
        description="Affiliate link coverage for top 10 / 20 / 50 / 100 products",
    )
    async def cmd_affiliate_coverage(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import get_coverage_report
            report = await asyncio.to_thread(get_coverage_report)

            embed = discord.Embed(title="📈 Affiliate Coverage Report", color=discord.Color.blue())

            for tier in report.get("tiers", []):
                n    = tier["n"]
                pct  = tier["pct"]
                cov  = tier["covered"]
                tot  = tier["total"]
                bar_n = int(pct / 5)
                bar  = "█" * bar_n + "░" * (20 - bar_n)
                col  = "🟢" if pct >= 80 else "🟡" if pct >= 40 else "🔴"
                embed.add_field(
                    name=f"{col} Top {n}",
                    value=f"{pct}%  `{bar}`\n{cov}/{tot} products",
                    inline=False,
                )

            # Show a few uncovered top products
            uncovered = [d for d in report.get("top100_details", [])[:20]
                         if not d["has_affiliate"]][:5]
            if uncovered:
                lines = "\n".join(
                    f"`{i:>2}.` {d['title'][:50] or '—'} (`{d['itemid']}`)"
                    for i, d in enumerate(uncovered, 1)
                )
                embed.add_field(name="⚠️ Top products missing link", value=lines, inline=False)

            embed.set_footer(text="/affiliate-missing for full breakdown • /affiliate-product-add to add links")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-list
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-list",
        description="Browse affiliate products with optional category filter",
    )
    @app_commands.describe(
        filter="Filter: recent / beauty / gadget / home / baby / health / fashion / camping / missing",
        page="Page number (starts at 1)",
    )
    @app_commands.choices(filter=[
        app_commands.Choice(name="Recent",   value="recent"),
        app_commands.Choice(name="Missing",  value="missing"),
        app_commands.Choice(name="Beauty",   value="beauty"),
        app_commands.Choice(name="Gadget",   value="gadget"),
        app_commands.Choice(name="Home",     value="home"),
        app_commands.Choice(name="Baby",     value="baby"),
        app_commands.Choice(name="Health",   value="health"),
        app_commands.Choice(name="Fashion",  value="fashion"),
        app_commands.Choice(name="Camping",  value="camping"),
    ])
    async def cmd_affiliate_list(
        self,
        interaction: discord.Interaction,
        filter: str = "recent",
        page: int = 1,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import list_affiliate_products
            page_idx = max(0, page - 1)
            data = await asyncio.to_thread(list_affiliate_products, filter, page_idx)

            items       = data["items"]
            total       = data["total"]
            total_pages = data["total_pages"]
            cur_page    = data["page"] + 1

            color = discord.Color.blue() if items else discord.Color.orange()
            embed = discord.Embed(
                title=f"📋 Affiliate Products — {filter.title()} (Page {cur_page}/{total_pages})",
                color=color,
            )
            embed.set_footer(text=f"Total: {total} products • Use page: param to navigate")

            if not items:
                embed.description = "No products found for this filter."
            else:
                lines = []
                for p in items:
                    link_str = f"`{p['link'][:50]}`" if p["link"] else "⚠️ No link"
                    lines.append(
                        f"**{p['title'][:52] or '—'}**\n"
                        f"  itemid=`{p['itemid']}` | {p['category'][:22] or '—'} | {p['updated_at']}\n"
                        f"  {link_str}"
                    )
                embed.description = "\n\n".join(lines)

            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-health
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-health",
        description="Health check for affiliate products data quality",
    )
    async def cmd_affiliate_health(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import get_health_report, fix_bad_titles
            fixed = await asyncio.to_thread(fix_bad_titles)
            report = await asyncio.to_thread(get_health_report)

            score  = report["health_score"]
            total  = report["total"]
            issues = report.get("issues", [])

            color = (discord.Color.green()  if score >= 80
                     else discord.Color.yellow() if score >= 50
                     else discord.Color.red())
            bar_n = int(score / 5)
            bar   = "█" * bar_n + "░" * (20 - bar_n)

            embed = discord.Embed(title="🩺 Affiliate Health Check", color=color)
            embed.add_field(name="Health Score", value=f"{score}%  `{bar}`", inline=False)
            embed.add_field(name="Total Records", value=str(total), inline=True)
            embed.add_field(name="Issues Found",  value=str(len(issues)), inline=True)
            if fixed:
                embed.add_field(name="🔧 Auto-fixed Titles", value=str(fixed), inline=True)

            for issue in issues:
                examples = ", ".join(issue.get("examples", [])[:2])
                val = f"Count: **{issue['count']}**"
                if examples:
                    val += f"\nExamples: {examples[:80]}"
                embed.add_field(name=f"⚠️ {issue['label']}", value=val, inline=False)

            if not issues:
                embed.description = "✅ No issues found. All records look healthy."

            embed.set_footer(text="Run /affiliate-list filter:missing to see products without links")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /control-center
    # ------------------------------------------------------------------
    @app_commands.command(
        name="control-center",
        description="Operational home screen — products, coverage, missing, health",
    )
    async def cmd_control_center(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import get_control_center_stats
            stats = await asyncio.to_thread(get_control_center_stats)

            if not stats:
                await interaction.followup.send(
                    embed=error_embed("No database found. Run import-datafeed first.")
                )
                return

            total        = stats["total"]
            with_link    = stats["with_link"]
            without_link = stats["without_link"]
            top10_pct    = stats["top10_coverage"]
            health       = stats["health_score"]
            n_issues     = stats["issues"]
            recent       = stats.get("recent", [])
            cat_cov      = stats.get("category_coverage", [])

            health_emoji  = "🟢" if health    >= 80 else "🟡" if health    >= 50 else "🔴"
            top10_emoji   = "🟢" if top10_pct >= 80 else "🟡" if top10_pct >= 40 else "🔴"
            overall_color = (discord.Color.green()  if health >= 80 and top10_pct >= 80
                             else discord.Color.yellow() if health >= 50
                             else discord.Color.orange())

            embed = discord.Embed(
                title="🏠 Shopee Affiliate — Control Center",
                color=overall_color,
            )
            embed.add_field(name="📦 Total Products",         value=str(total),        inline=True)
            embed.add_field(name="✅ With Link",               value=str(with_link),    inline=True)
            embed.add_field(name="⚠️ Missing Link",           value=str(without_link), inline=True)
            embed.add_field(name=f"{top10_emoji} Top-10 Coverage",
                            value=f"{top10_pct}%", inline=True)
            embed.add_field(name=f"{health_emoji} Health Score",
                            value=f"{health}%", inline=True)
            embed.add_field(name="🔍 Issues",
                            value=str(n_issues) if n_issues else "None", inline=True)

            # Category coverage summary
            if cat_cov:
                def _cat_emoji(pct: float) -> str:
                    return "🟢" if pct >= 80 else "🟡" if pct >= 40 else "🔴"

                cat_lines = "\n".join(
                    f"{_cat_emoji(c['pct'])} **{c['name'].title()}** "
                    f"{c['covered']}/{c['total']} ({c['pct']}%)"
                    for c in sorted(cat_cov, key=lambda x: -x["pct"])
                )
                # Top priority: most missing
                priority = sorted(
                    [c for c in cat_cov if c["missing"] > 0],
                    key=lambda x: -x["missing"]
                )[:3]
                priority_lines = "\n".join(
                    f"`{i}.` {c['name'].title()} ({c['missing']} missing)"
                    for i, c in enumerate(priority, 1)
                )
                embed.add_field(name="📊 Category Coverage (Top 10)", value=cat_lines, inline=False)
                if priority_lines:
                    embed.add_field(name="🎯 Top Priority", value=priority_lines, inline=False)

            if recent:
                lines = "\n".join(
                    f"• {r['title'][:48] or '—'} ({r['created_at']})"
                    for r in recent
                )
                embed.add_field(name="🕐 Recent Activity", value=lines, inline=False)

            embed.add_field(
                name="Quick Commands",
                value=(
                    "`/affiliate-category-report` — full category breakdown\n"
                    "`/affiliate-missing-category <cat>` — missing per category\n"
                    "`/affiliate-missing` — top opportunities missing links\n"
                    "`/affiliate-list` — browse all products\n"
                    "`/affiliate-health` — data quality check"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-category-report
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-category-report",
        description="Affiliate link coverage breakdown for every product category",
    )
    @app_commands.describe(top_n="Top N products per category to benchmark (default 20)")
    async def cmd_affiliate_category_report(
        self,
        interaction: discord.Interaction,
        top_n: int = 20,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import get_category_coverage
            data = await asyncio.to_thread(get_category_coverage, top_n)

            categories    = data.get("categories", [])
            total_prod    = data.get("total_products", 0)
            total_covered = data.get("total_covered",  0)
            total_missing = data.get("total_missing",  0)

            overall_pct = round(total_covered / total_prod * 100, 1) if total_prod else 0.0
            color = (discord.Color.green()  if overall_pct >= 80
                     else discord.Color.yellow() if overall_pct >= 40
                     else discord.Color.red())

            embed = discord.Embed(
                title=f"📊 Affiliate Category Coverage (Top {top_n} per category)",
                color=color,
            )

            def _bar(pct: float, width: int = 10) -> str:
                filled = int(pct / 100 * width)
                return "█" * filled + "░" * (width - filled)

            def _emoji(pct: float) -> str:
                return "🟢" if pct >= 80 else "🟡" if pct >= 40 else "🔴"

            for cat in sorted(categories, key=lambda x: -x["pct"]):
                pct  = cat["pct"]
                warn = f"⚠️ Missing {cat['missing']}" if cat["missing"] else "✅ Complete"
                embed.add_field(
                    name=f"{_emoji(pct)} {cat['name'].title()}",
                    value=(
                        f"✅ {cat['covered']}/{cat['total']} ({pct}%) "
                        f"`{_bar(pct)}`\n{warn}"
                    ),
                    inline=True,
                )

            # Totals
            embed.add_field(name="​", value="​", inline=False)  # spacer
            embed.add_field(
                name="━━ Total ━━",
                value=(
                    f"✅ **{total_covered}** products with link\n"
                    f"⚠️ **{total_missing}** products missing\n"
                    f"Overall: **{overall_pct}%**  `{_bar(overall_pct, 20)}`"
                ),
                inline=False,
            )
            embed.set_footer(
                text="Use /affiliate-missing-category <name> to see which products need links"
            )
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /affiliate-missing-category
    # ------------------------------------------------------------------
    @app_commands.command(
        name="affiliate-missing-category",
        description="Show top products in a category that still need affiliate links",
    )
    @app_commands.describe(category="Category: beauty / gadget / home / baby / health / fashion / camping")
    @app_commands.choices(category=[
        app_commands.Choice(name="Beauty",  value="beauty"),
        app_commands.Choice(name="Gadget",  value="gadget"),
        app_commands.Choice(name="Home",    value="home"),
        app_commands.Choice(name="Baby",    value="baby"),
        app_commands.Choice(name="Health",  value="health"),
        app_commands.Choice(name="Fashion", value="fashion"),
        app_commands.Choice(name="Camping", value="camping"),
    ])
    async def cmd_affiliate_missing_category(
        self,
        interaction: discord.Interaction,
        category: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            from shopee_engine.affiliate_products_engine import get_missing_for_category
            items = await asyncio.to_thread(get_missing_for_category, category, 20)

            cat_label = category.title()
            cat_icons = {
                "beauty": "💄", "gadget": "📱", "home": "🏠",
                "baby": "🍼", "health": "💊", "fashion": "👗", "camping": "⛺",
            }
            icon = cat_icons.get(category, "📦")

            embed = discord.Embed(
                title=f"{icon} {cat_label} — Missing Affiliate Links",
                color=discord.Color.orange() if items else discord.Color.green(),
            )

            if not items:
                embed.description = f"✅ All top {cat_label} products have affiliate links!"
            else:
                lines = []
                for i, p in enumerate(items, 1):
                    lines.append(
                        f"`{i:>2}.` **{p['title'][:55] or '—'}**\n"
                        f"      ItemID: `{p['itemid']}` | Score: `{p['opp_score']:,}`"
                    )
                embed.description = "\n\n".join(lines[:15])
                embed.set_footer(
                    text=f"{len(items)} products need links • Use /affiliate-product-add to add them"
                )

            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))
