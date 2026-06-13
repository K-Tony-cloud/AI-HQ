"""Embed builders for discovery commands."""

from __future__ import annotations

import discord

from .base import make_embed, COLORS

PAGE_SIZE_DEFAULT = 10


def _trunc(s: str | None, n: int = 50) -> str:
    s = str(s or "Unknown")
    return s[:n] + "…" if len(s) > n else s


def _fp(v) -> str:
    try:
        return f"฿{float(v):,.0f}"
    except Exception:
        return "—"


def _fi(v) -> str:
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "—"


# ---------------------------------------------------------------------------
# Top Opportunities
# ---------------------------------------------------------------------------

def build_top_opportunities_pages(
    records: list[dict],
    category: str | None,
    page_size: int = PAGE_SIZE_DEFAULT,
) -> list[discord.Embed]:
    cat_label = f" — {category}" if category else ""
    pages: list[discord.Embed] = []

    for chunk_start in range(0, max(len(records), 1), page_size):
        chunk = records[chunk_start: chunk_start + page_size]
        e = make_embed(
            title=f"🎯 Top Opportunities{cat_label}",
            color_key="opportunity",
            description=f"Ranked by opportunity score | {len(records)} products found",
        )
        for i, r in enumerate(chunk, chunk_start + 1):
            name   = _trunc(r.get("title") or r.get("name"), 48)
            sold   = _fi(r.get("item_sold") or r.get("sold") or 0)
            price  = _fp(r.get("sale_price") or r.get("price") or 0)
            score  = _fi(r.get("opportunity_score") or r.get("score") or 0)
            disc   = r.get("discount_pct") or r.get("discount") or 0
            e.add_field(
                name=f"{i}. {name}",
                value=f"Sold: **{sold}** | Price: **{price}** | Score: **{score}** | Disc: {float(disc):.0f}%",
                inline=False,
            )
        pages.append(e)

    return pages or [make_embed("🎯 Top Opportunities", "opportunity", "No data found.")]


# ---------------------------------------------------------------------------
# Top Viral
# ---------------------------------------------------------------------------

def build_top_viral_pages(
    records: list[dict],
    category: str | None,
    page_size: int = PAGE_SIZE_DEFAULT,
) -> list[discord.Embed]:
    cat_label = f" — {category}" if category else ""
    pages: list[discord.Embed] = []

    for chunk_start in range(0, max(len(records), 1), page_size):
        chunk = records[chunk_start: chunk_start + page_size]
        e = make_embed(
            title=f"🔥 Top Viral{cat_label}",
            color_key="viral",
            description="Score: sold×0.35 + likes×0.35 + discount×0.30",
        )
        for i, r in enumerate(chunk, chunk_start + 1):
            name  = _trunc(r.get("title") or r.get("name"), 48)
            price = _fp(r.get("sale_price") or r.get("price") or 0)
            likes = _fi(r.get("likes") or 0)
            sold  = _fi(r.get("item_sold") or r.get("sold") or 0)
            score = _fi(r.get("viral_score") or r.get("opportunity_score") or 0)
            e.add_field(
                name=f"{i}. {name}",
                value=f"Price: **{price}** | Sold: **{sold}** | Likes: **{likes}** | Score: **{score}**",
                inline=False,
            )
        pages.append(e)

    return pages or [make_embed("🔥 Top Viral", "viral", "No data found.")]


# ---------------------------------------------------------------------------
# Find Product
# ---------------------------------------------------------------------------

def build_find_product_embed(records: list[dict], keyword: str) -> discord.Embed:
    e = make_embed(
        title=f"🔍 Results: {keyword}",
        color_key="opportunity",
        description=f"{len(records)} products found",
    )
    for i, r in enumerate(records[:15], 1):
        name   = _trunc(r.get("title") or r.get("name"), 48)
        sold   = _fi(r.get("item_sold") or r.get("sold") or 0)
        price  = _fp(r.get("sale_price") or r.get("price") or 0)
        score  = _fi(r.get("opportunity_score") or 0)
        link   = str(r.get("product_short_link") or r.get("affiliate_link") or "").strip()
        val    = f"Sold: **{sold}** | Price: **{price}** | Score: **{score}**"
        if link:
            val += f"\n[Affiliate Link]({link})"
        e.add_field(name=f"{i}. {name}", value=val, inline=False)
    return e


# ---------------------------------------------------------------------------
# Daily Picks
# ---------------------------------------------------------------------------

def build_daily_picks_embed(picks: dict[str, list[dict]]) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []

    BUCKET_EMOJIS = {
        "Gadget": "📱", "Home": "🏠", "Viral TikTok": "🎵",
        "Mobile Accessories": "🔌", "Mother & Baby": "👶",
        "Health": "💊", "Camping": "⛺",
    }

    for bucket, records in picks.items():
        if not records:
            continue
        emoji = BUCKET_EMOJIS.get(bucket, "🛒")
        e = make_embed(title=f"{emoji} Daily Picks — {bucket}", color_key="opportunity")
        for i, r in enumerate(records[:5], 1):
            name  = _trunc(r.get("title") or r.get("name"), 45)
            sold  = _fi(r.get("item_sold") or r.get("sold") or 0)
            price = _fp(r.get("sale_price") or r.get("price") or 0)
            score = _fi(r.get("opportunity_score") or 0)
            e.add_field(
                name=f"{i}. {name}",
                value=f"Sold: **{sold}** | Price: **{price}** | Score: **{score}**",
                inline=False,
            )
        embeds.append(e)

    if not embeds:
        embeds = [make_embed("📅 Daily Picks", "opportunity", "No data found.")]
    return embeds
