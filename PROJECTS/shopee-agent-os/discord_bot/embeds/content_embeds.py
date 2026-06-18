"""Embed builders for content commands."""

from __future__ import annotations

import json

import discord

from .base import make_embed

PAGE_SIZE = 8


def _safe_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return [str(x) for x in data] if isinstance(data, list) else [raw]
        except Exception:
            return [raw]
    return []


# ---------------------------------------------------------------------------
# Content Pack — split into one embed per section
# ---------------------------------------------------------------------------

def build_content_pack_embeds(result: dict) -> list[discord.Embed]:
    product = result.get("product") or {}
    keyword = result.get("keyword", "")
    name    = str(product.get("title") or product.get("name") or keyword)[:60]
    price   = product.get("sale_price") or product.get("price") or 0
    sold    = product.get("item_sold") or product.get("sold") or 0
    provider = result.get("provider", "template")
    embeds: list[discord.Embed] = []

    # ── Header embed ──────────────────────────────────────────────────────
    header = make_embed(
        title=f"📦 Content Pack — {name}",
        color_key="content",
        description=(
            f"Price: **฿{float(price):,.0f}** | Sold: **{int(float(sold)):,}**\n"
            f"AI Provider: `{provider}`"
        ),
    )
    embeds.append(header)

    # ── Hooks ─────────────────────────────────────────────────────────────
    hooks_raw = result.get("hooks") or {}
    hooks_embed = make_embed("🪝 Hooks (10 types)", color_key="content")
    if isinstance(hooks_raw, dict):
        for label, items in hooks_raw.items():
            texts = _safe_list(items)
            if texts:
                hooks_embed.add_field(
                    name=f"**{label}**",
                    value="\n".join(f"• {t[:180]}" for t in texts[:2]),
                    inline=False,
                )
    embeds.append(hooks_embed)

    # ── Captions ──────────────────────────────────────────────────────────
    caps = result.get("captions") or {}
    caps_embed = make_embed("✍️ Captions", color_key="content")
    for platform, items in (caps.items() if isinstance(caps, dict) else []):
        texts = _safe_list(items)
        if texts:
            caps_embed.add_field(
                name=f"**{platform.upper()}**",
                value="\n\n".join(t[:300] for t in texts[:2]),
                inline=False,
            )
    if not caps_embed.fields:
        cap_list = _safe_list(caps)
        for i, c in enumerate(cap_list[:5], 1):
            caps_embed.add_field(name=f"Caption {i}", value=c[:400], inline=False)
    embeds.append(caps_embed)

    # ── Scripts ───────────────────────────────────────────────────────────
    scripts = result.get("scripts") or {}
    sc_embed = make_embed("🎬 Scripts", color_key="content")
    if isinstance(scripts, dict):
        for dur, text in scripts.items():
            sc_embed.add_field(
                name=f"**{dur}**",
                value=str(text)[:600],
                inline=False,
            )
    else:
        for i, s in enumerate(_safe_list(scripts)[:3], 1):
            sc_embed.add_field(name=f"Script {i}", value=s[:600], inline=False)
    embeds.append(sc_embed)

    # ── CTA + Hashtags ────────────────────────────────────────────────────
    cta_raw  = result.get("cta") or {}
    hashtags = result.get("hashtags") or ""
    cta_embed = make_embed("📣 CTA & Hashtags", color_key="content")
    if isinstance(cta_raw, dict):
        for k, v in cta_raw.items():
            cta_embed.add_field(name=f"**{k}**", value=str(v)[:400], inline=False)
    if hashtags:
        cta_embed.add_field(
            name="#️⃣ Hashtags",
            value=str(hashtags)[:600],
            inline=False,
        )
    embeds.append(cta_embed)

    return embeds


# ---------------------------------------------------------------------------
# Content Queue
# ---------------------------------------------------------------------------

def build_queue_pages(records: list[dict], page_size: int = PAGE_SIZE) -> list[discord.Embed]:
    if not records:
        return [make_embed("📋 Content Queue", "queue", "Queue is empty.\nUse `/content-pack` then `queue-add` to add items.")]

    pages: list[discord.Embed] = []
    for chunk_start in range(0, len(records), page_size):
        chunk = records[chunk_start: chunk_start + page_size]
        e = make_embed(
            title="📋 Content Queue",
            color_key="queue",
            description=f"Total items: {len(records)}",
        )
        for r in chunk:
            id_      = r.get("id", "?")
            keyword  = str(r.get("keyword") or "")[:30]
            status   = str(r.get("status") or "draft")
            provider = str(r.get("ai_provider") or "template")
            status_icon = "✅" if status == "approved" else "📝"
            e.add_field(
                name=f"{status_icon} ID {id_} — {keyword}",
                value=f"Status: `{status}` | Provider: `{provider}`",
                inline=False,
            )
        pages.append(e)

    return pages


def build_approve_embed(item_id: int, success: bool) -> discord.Embed:
    if success:
        return make_embed(
            title="✅ Approved",
            color_key="success",
            description=f"Queue item **ID {item_id}** status → `approved`",
        )
    return make_embed(
        title="❌ Not Found",
        color_key="error",
        description=f"No queue item with ID **{item_id}**.",
    )


# ---------------------------------------------------------------------------
# Content Intelligence — อะไรของมัน Facebook Page embeds
# ---------------------------------------------------------------------------

_TYPE_EMOJIS: dict[str, str] = {
    "comment_bait":     "💬",
    "nostalgia":        "📼",
    "visual_curiosity": "👀",
    "weird_product":    "😂",
    "affiliate":        "🛒",
    "trending":         "🔥",
}


def build_content_picks_embed(items: list[dict]) -> discord.Embed:
    """Embed showing top products to feature today from commission or discovery data."""
    if not items:
        return make_embed(
            title="📊 Content Picks — Today",
            color_key="opportunity",
            description="ยังไม่มีข้อมูลสินค้า\nลอง import commission report ก่อนนะ",
        )

    source_label = items[0].get("source", "?")
    source_tag   = "🏆 Real commission data" if source_label == "real" else "🔍 Discovery (by sales)"
    e = make_embed(
        title="📊 Content Picks — Today",
        color_key="opportunity",
        description=f"Source: {source_tag} | Top {len(items)} products",
    )

    for i, item in enumerate(items, 1):
        name       = str(item.get("name", "?"))[:50]
        commission = float(item.get("commission", 0))
        orders     = float(item.get("orders", 0))
        revenue    = float(item.get("revenue", 0))
        src        = item.get("source", "?")
        src_icon   = "🏆" if src == "real" else "🔍"
        val_parts  = [f"{src_icon} `{src}`"]
        if commission > 0:
            val_parts.append(f"฿{commission:,.2f} commission")
        if orders > 0:
            val_parts.append(f"{int(orders)} orders")
        if revenue > 0:
            val_parts.append(f"฿{revenue:,.0f} revenue")
        e.add_field(
            name=f"**#{i}** {name}",
            value=" | ".join(val_parts),
            inline=False,
        )

    return e


def build_engagement_post_embed(data: dict) -> discord.Embed:
    """Embed for a single engagement/viral post."""
    post_type  = data.get("type", "engagement")
    type_emoji = _TYPE_EMOJIS.get(post_type, "📝")
    hook       = str(data.get("hook", ""))[:1000]
    caption    = str(data.get("caption", ""))[:500]
    cta        = str(data.get("cta", ""))[:300]
    provider   = data.get("provider", "template")

    e = make_embed(
        title=f"{type_emoji} Engagement Post — {post_type.replace('_', ' ').title()}",
        color_key="opportunity",
        description=f"`provider: {provider}`",
    )
    if hook:
        e.add_field(name="🎣 Hook", value=hook, inline=False)
    if caption:
        e.add_field(name="📝 Caption", value=caption, inline=False)
    if cta:
        e.add_field(name="📣 CTA", value=cta, inline=False)
    return e


def build_facebook_post_embed(data: dict) -> discord.Embed:
    """Embed showing a product Facebook post in อะไรของมัน voice."""
    hook      = str(data.get("hook", ""))[:500]
    post_text = str(data.get("post", ""))[:1800]
    hashtags  = str(data.get("hashtags", ""))[:300]
    provider  = data.get("provider", "template")

    e = make_embed(
        title="📘 Facebook Product Post — อะไรของมัน",
        color_key="content",
        description=f"`provider: {provider}`",
    )
    if hook:
        e.add_field(name="🎣 Hook", value=hook, inline=False)
    if post_text:
        e.add_field(name="📄 Post", value=post_text, inline=False)
    if hashtags:
        e.add_field(name="#️⃣ Hashtags", value=hashtags, inline=False)
    return e


def build_content_calendar_embed(days: list[dict]) -> discord.Embed:
    """Embed with a 7-day posting calendar."""
    e = make_embed(
        title=f"📅 Content Calendar — {len(days)} Days",
        color_key="content",
        description="70% engagement / 20% weird product / 10% affiliate",
    )
    for day in days:
        day_num  = day.get("day", "?")
        date_str = day.get("date", "")
        typ      = day.get("type", "?")
        emoji    = _TYPE_EMOJIS.get(typ, "📝")
        cat      = day.get("category", "")
        desc     = day.get("description", "")
        time_str = day.get("time", "19:00")
        e.add_field(
            name=f"Day {day_num} — {date_str} {time_str}",
            value=f"{emoji} **{typ.replace('_', ' ')}** `{cat}`\n{desc}",
            inline=False,
        )
    return e


def build_content_mix_embed(data: dict) -> list[discord.Embed]:
    """Returns 3 embeds: engagement post + product post + affiliate note."""
    engagement = data.get("engagement", {})
    product    = data.get("product", {})
    affiliate  = data.get("affiliate", {})
    date_str   = data.get("date", "")

    embeds: list[discord.Embed] = []

    # 1. Engagement post
    eng_embed = build_engagement_post_embed(engagement)
    eng_embed.title = f"💬 Today's Engagement Post — {date_str}"
    embeds.append(eng_embed)

    # 2. Product post
    prod_embed = build_facebook_post_embed(product)
    prod_embed.title = f"😂 Today's Product Post — {date_str}"
    embeds.append(prod_embed)

    # 3. Affiliate note
    aff_hook    = str(affiliate.get("hook", ""))[:400]
    aff_caption = str(affiliate.get("caption", ""))[:400]
    aff_cta     = str(affiliate.get("cta", ""))[:200]
    aff_embed   = make_embed(
        title=f"🛒 Today's Affiliate Soft — {date_str}",
        color_key="profit",
        description="โพสต์นุ่มๆ ไม่ขายตรง",
    )
    if aff_hook:
        aff_embed.add_field(name="🎣 Hook", value=aff_hook, inline=False)
    if aff_caption:
        aff_embed.add_field(name="📝 Caption", value=aff_caption, inline=False)
    if aff_cta:
        aff_embed.add_field(name="📣 CTA", value=aff_cta, inline=False)
    embeds.append(aff_embed)

    return embeds
