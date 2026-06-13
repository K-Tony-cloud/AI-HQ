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
