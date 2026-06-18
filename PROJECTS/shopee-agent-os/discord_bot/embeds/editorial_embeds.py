"""Embed builders for the Editorial System — /today-content."""

from __future__ import annotations

import discord

from .base import FOOTER_TEXT, make_embed

_TYPE_ICONS = {
    "comment_bait":     "💬",
    "weird_product":    "😳",
    "nostalgia":        "🥹",
    "visual_curiosity": "👀",
    "trending":         "🔥",
    "affiliate":        "🛒",
    "manual":           "✍️",
}

_TYPE_LABELS = {
    "comment_bait":     "Comment Bait",
    "weird_product":    "Weird Product",
    "nostalgia":        "Nostalgia",
    "visual_curiosity": "Visual Curiosity",
    "trending":         "Trending",
    "affiliate":        "Affiliate",
    "manual":           "Manual",
}


def _trunc(s: str, n: int) -> str:
    s = str(s or "")
    return s[:n] + "…" if len(s) > n else s


def build_today_content_embeds(data: dict) -> list[discord.Embed]:
    """
    Returns a list of embeds:
    - Embed 0: Editorial brief (date, trend status, day mood)
    - Embed 1-N: One embed per post slot (full caption, image rec, reasoning)
    """
    embeds: list[discord.Embed] = []

    # ── Brief embed ────────────────────────────────────────────────────────────
    date       = data.get("date", "")
    day_th     = data.get("day_th", "")
    season     = data.get("season", "")
    season_em  = data.get("season_emoji", "")
    mood       = data.get("mood", "")
    override   = data.get("override_active", False)
    ov_label   = data.get("override_label", "")
    slang      = data.get("slang_today", [])
    ai_trends  = data.get("ai_trending", [])
    posts      = data.get("posts", [])

    color = "error" if override else "opportunity"
    brief_title = (
        f"🔥 TREND OVERRIDE: {ov_label}" if override
        else f"📅 Editorial Plan — {day_th} {date}"
    )
    brief_desc = f"{season_em} **{season}** · {mood}"

    brief = make_embed(brief_title, color_key=color, description=brief_desc)
    brief.add_field(
        name="📋 Today's Schedule",
        value="\n".join(
            f"`{p['time']}` {_TYPE_ICONS.get(p['type'], '•')} **{_TYPE_LABELS.get(p['type'], p['type'])}**"
            for p in posts
        ) or "No posts generated",
        inline=False,
    )
    if slang:
        brief.add_field(
            name="💬 Today's Slang",
            value=" · ".join(f"`{s}`" for s in slang),
            inline=False,
        )
    if ai_trends:
        brief.add_field(
            name="🔍 AI Trend Radar",
            value="\n".join(f"• {t}" for t in ai_trends[:3]),
            inline=False,
        )
    brief.set_footer(text=f"{FOOTER_TEXT} • Editorial System • อะไรของมัน")
    embeds.append(brief)

    # ── Per-post embeds ────────────────────────────────────────────────────────
    post_colors = ["content", "viral", "profit", "niche"]
    for i, post in enumerate(posts):
        slot_type = post.get("type", "manual")
        icon      = _TYPE_ICONS.get(slot_type, "📝")
        label     = _TYPE_LABELS.get(slot_type, slot_type.title())
        ai_badge  = " ✨AI" if post.get("ai_enhanced") else ""

        e = make_embed(
            f"{icon} Post {post['slot']} — {post['time']} · {label}{ai_badge}",
            color_key=post_colors[i % len(post_colors)],
        )

        caption = post.get("caption", "")
        if caption:
            # Split long captions into ≤1000 char chunks for Discord field limit
            if len(caption) <= 900:
                e.add_field(
                    name="📝 Caption (copy-paste ready)",
                    value=f"```\n{caption}\n```",
                    inline=False,
                )
            else:
                # Show first 900 chars, rest in continuation field
                e.add_field(
                    name="📝 Caption (Part 1)",
                    value=f"```\n{caption[:900]}\n```",
                    inline=False,
                )
                e.add_field(
                    name="📝 Caption (Part 2)",
                    value=f"```\n{caption[900:1800]}\n```",
                    inline=False,
                )

        if post.get("image_rec"):
            e.add_field(
                name="🖼 Image Recommendation",
                value=post["image_rec"],
                inline=False,
            )

        if post.get("cta"):
            e.add_field(
                name="📣 CTA",
                value=f"`{post['cta']}`",
                inline=True,
            )

        e.add_field(
            name="🧠 Why This Post",
            value=post.get("reasoning", "—"),
            inline=False,
        )

        e.set_footer(text=f"Post {post['slot']}/{len(posts)} · {FOOTER_TEXT}")
        embeds.append(e)

    return embeds
