"""Embed builders for Facebook Insights + Content Performance commands."""

from __future__ import annotations

import discord

from .base import FOOTER_TEXT, make_embed


def _trunc(s: str, n: int) -> str:
    s = str(s or "")
    return s[:n] + "…" if len(s) > n else s


def _fmt(n: int | float) -> str:
    return f"{int(n):,}"


# ─────────────────────────────────────────────────────────────────────────────
# /insights-page
# ─────────────────────────────────────────────────────────────────────────────

def build_page_insights_embed(data: dict) -> discord.Embed:
    if data.get("error"):
        e = make_embed("❌ Page Insights Failed", color_key="error")
        e.add_field(name="Error", value=data["error"], inline=False)
        return e

    since = data.get("since", "?")
    until = data.get("until", "?")
    e = make_embed(
        "📊 Page Insights — Last 30 Days",
        color_key="content",
        description=f"**{data.get('page_name','อะไรของมัน')}** · {since} → {until}",
    )
    e.add_field(name="👥 Followers",      value=_fmt(data.get("followers_count", 0)),          inline=True)
    e.add_field(name="❤️ Page Likes",    value=_fmt(data.get("fan_count", 0)),                inline=True)
    e.add_field(name="🔍 Page Views",    value=_fmt(data.get("page_views_total", 0)),          inline=True)
    e.add_field(name="💬 Post Engagements", value=_fmt(data.get("page_post_engagements", 0)), inline=True)
    e.add_field(name="🖱 Total Actions",  value=_fmt(data.get("page_total_actions", 0)),       inline=True)

    if data.get("page_error"):
        e.add_field(name="⚠️ Note", value=data["page_error"][:200], inline=False)

    e.set_footer(text=f"{FOOTER_TEXT} • Facebook Graph API")
    return e


# ─────────────────────────────────────────────────────────────────────────────
# /insights-posts
# ─────────────────────────────────────────────────────────────────────────────

def build_posts_embed(posts: list[dict]) -> discord.Embed:
    if not posts:
        return make_embed("📝 No Posts Found", color_key="info",
                          description="No posts found. Publish something first.")
    if len(posts) == 1 and posts[0].get("error"):
        e = make_embed("❌ Posts Fetch Failed", color_key="error")
        e.add_field(name="Error", value=posts[0]["error"], inline=False)
        return e

    e = make_embed(f"📋 Recent Posts — {len(posts)} posts", color_key="content")
    for p in posts:
        msg     = _trunc(p.get("message", "*(no text)*"), 60)
        reach   = _fmt(p.get("reach", 0))
        rx      = p.get("reactions", 0)
        cm      = p.get("comments", 0)
        sh      = p.get("shares", 0)
        er      = p.get("engagement_rate", 0.0)
        score   = p.get("score", 0.0)
        date    = (p.get("created_at") or "")[:10]
        url     = p.get("url", "")
        title   = f"`{date}` {msg}"
        value   = f"Reach **{reach}** · ❤️{rx} 💬{cm} 🔁{sh} · ER {er:.2f}% · Score **{score:.1f}**"
        if url:
            value += f"\n[View]({url})"
        e.add_field(name=title, value=value, inline=False)
    e.set_footer(text=f"{FOOTER_TEXT} • Facebook Graph API")
    return e


# ─────────────────────────────────────────────────────────────────────────────
# /insights-top
# ─────────────────────────────────────────────────────────────────────────────

_METRIC_LABELS = {
    "score":           "Score",
    "reach":           "Reach",
    "reactions":       "Reactions",
    "comments":        "Comments",
    "shares":          "Shares",
    "engagement_rate": "Engagement Rate",
}


def build_top_posts_embed(posts: list[dict], metric: str = "score") -> discord.Embed:
    label = _METRIC_LABELS.get(metric, metric.title())
    if not posts:
        return make_embed(f"🏆 Top Posts by {label}", color_key="info",
                          description="No performance data yet. Run /insights-posts first.")

    e = make_embed(f"🏆 Top Posts by {label}", color_key="viral")
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, p in enumerate(posts):
        medal   = medals[i] if i < len(medals) else f"{i+1}."
        msg     = _trunc(p.get("message", "*(no text)*"), 70)
        val     = p.get(metric, 0)
        val_str = f"{val:.2f}%" if metric == "engagement_rate" else f"{val:,.1f}" if isinstance(val, float) else _fmt(val)
        reach   = _fmt(p.get("reach", 0))
        rx      = p.get("reactions", 0)
        cm      = p.get("comments", 0)
        sh      = p.get("shares", 0)
        date    = (p.get("created_at") or "")[:10]
        e.add_field(
            name=f"{medal} {label}: **{val_str}**",
            value=f"`{date}` {msg}\nReach {reach} · ❤️{rx} 💬{cm} 🔁{sh}",
            inline=False,
        )
    e.set_footer(text=f"{FOOTER_TEXT} • synced from Facebook")
    return e


# ─────────────────────────────────────────────────────────────────────────────
# /insights-last30
# ─────────────────────────────────────────────────────────────────────────────

def build_last30_embed(data: dict) -> discord.Embed:
    pi    = data.get("page_insights", {})
    count = data.get("post_count", 0)
    top   = data.get("top_post")

    has_error = bool(pi.get("error"))
    e = make_embed(
        "📅 Last 30 Days Summary",
        color_key="error" if has_error else "profit",
    )

    if has_error:
        e.add_field(name="Insights Error", value=pi["error"], inline=False)
    else:
        e.add_field(name="👥 Followers",       value=_fmt(pi.get("followers_count", 0)),          inline=True)
        e.add_field(name="❤️ Page Likes",     value=_fmt(pi.get("fan_count", 0)),                inline=True)
        e.add_field(name="🔍 Page Views",     value=_fmt(pi.get("page_views_total", 0)),          inline=True)
        e.add_field(name="💬 Engagements",    value=_fmt(pi.get("page_post_engagements", 0)),     inline=True)
        e.add_field(name="🖱 Total Actions",  value=_fmt(pi.get("page_total_actions", 0)),        inline=True)
        e.add_field(name="📝 Posts Tracked",  value=str(count),                                  inline=True)

    if top:
        msg   = _trunc(top.get("message", "*(no text)*"), 80)
        score = top.get("score", 0.0)
        reach = _fmt(top.get("reach", 0))
        rx    = top.get("reactions", 0)
        cm    = top.get("comments", 0)
        sh    = top.get("shares", 0)
        url   = top.get("url", "")
        val   = f"Score **{score:.1f}** · Reach {reach} · ❤️{rx} 💬{cm} 🔁{sh}\n{msg}"
        if url:
            val += f"\n[View Post]({url})"
        e.add_field(name="🏆 Top Post", value=val, inline=False)

    e.set_footer(text=f"{FOOTER_TEXT} • Facebook Graph API")
    return e


# ─────────────────────────────────────────────────────────────────────────────
# /content-next
# ─────────────────────────────────────────────────────────────────────────────

_TYPE_LABELS = {
    "comment_bait":    "💬 Comment Bait",
    "weird_product":   "😳 Weird Product",
    "nostalgia":       "🥹 Nostalgia",
    "visual_curiosity":"👀 Visual Curiosity",
    "trending":        "🔥 Trending",
    "affiliate":       "🛒 Affiliate",
    "manual":          "✍️ Manual",
}


def build_content_recommendation_embed(data: dict) -> discord.Embed:
    rec_type = data.get("recommended_type", "comment_bait")
    e = make_embed(
        f"🎯 Next Post: {_TYPE_LABELS.get(rec_type, rec_type)}",
        color_key="opportunity",
        description="AI recommendation based on your content performance.",
    )
    e.add_field(name="Content Type",    value=_TYPE_LABELS.get(rec_type, rec_type), inline=True)
    e.add_field(name="Best Time",       value=f"🕐 **{data.get('recommended_time','?')}**",   inline=True)
    e.add_field(name="Time Note",       value=data.get("time_note", "—"),                      inline=False)
    e.add_field(
        name="Suggested Hook",
        value=f"```{data.get('hook','—')}```",
        inline=False,
    )
    e.add_field(name="Reason",          value=data.get("reason", "—"),                         inline=False)
    e.add_field(
        name="Next Step",
        value="Use `/facebook-draft` or `/facebook-post` to publish.",
        inline=False,
    )
    e.set_footer(text=f"{FOOTER_TEXT} • Content Intelligence")
    return e


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled posts list
# ─────────────────────────────────────────────────────────────────────────────

def build_scheduled_posts_embed(posts: list[dict]) -> discord.Embed:
    if not posts:
        return make_embed(
            "📅 Scheduled Posts",
            color_key="info",
            description="No pending scheduled posts. Use `/facebook-schedule` to add one.",
        )
    e = make_embed(f"📅 Scheduled Posts — {len(posts)} pending", color_key="queue")
    for p in posts:
        msg  = _trunc(p.get("message", ""), 60)
        ptype = _TYPE_LABELS.get(p.get("post_type", ""), p.get("post_type", "manual"))
        note  = f" · {p['note']}" if p.get("note") else ""
        e.add_field(
            name=f"`#{p['id']}` 🕐 {p.get('publish_at','?')[:16]}",
            value=f"{ptype}{note}\n{msg}",
            inline=False,
        )
    e.set_footer(text=f"{FOOTER_TEXT} • Manual approval mode")
    return e
