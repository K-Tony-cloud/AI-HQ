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
