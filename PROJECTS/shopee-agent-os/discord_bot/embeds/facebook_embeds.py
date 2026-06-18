"""Embed builders for Facebook integration commands."""

from __future__ import annotations

import discord

from .base import FOOTER_TEXT, make_embed


def _trunc(s: str, n: int) -> str:
    s = str(s or "")
    return s[:n] + "…" if len(s) > n else s


def build_fb_page_info_embed(data: dict) -> discord.Embed:
    """Embed for /facebook-test — page connection status."""
    if data.get("error"):
        e = make_embed("❌ Facebook Connection Failed", color_key="error")
        e.add_field(name="Error", value=data["error"], inline=False)
        e.add_field(
            name="Fix",
            value="Check `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN` in `.env`",
            inline=False,
        )
        return e

    e = make_embed(
        f"✅ Facebook Page Connected",
        color_key="success",
        description=f"**{data.get('name', '—')}** is live and ready.",
    )
    e.add_field(name="Page Name",   value=data.get("name", "—"),              inline=True)
    e.add_field(name="Page ID",     value=f"`{data.get('page_id', '—')}`",    inline=True)
    e.add_field(name="Followers",   value=f"**{data.get('fan_count', 0):,}**", inline=True)
    e.add_field(name="Category",    value=data.get("category", "—"),          inline=True)
    e.add_field(name="Token",       value=f"`{data.get('token_preview','—')}`", inline=True)
    if data.get("about"):
        e.add_field(name="About",   value=_trunc(data["about"], 200),         inline=False)
    e.set_footer(text=f"{FOOTER_TEXT} • Facebook Graph API v19.0")
    return e


def build_fb_post_result_embed(result: dict, message: str) -> discord.Embed:
    """Embed for /facebook-post-test — shows post result."""
    if not result.get("success"):
        e = make_embed("❌ Post Failed", color_key="error")
        e.add_field(name="Error", value=result.get("error", "Unknown error"), inline=False)
        return e

    post_id = result.get("post_id", "")
    url     = result.get("url", "")

    e = make_embed("✅ Posted to Facebook!", color_key="success",
                   description=f"Your post is now live on **อะไรของมัน**.")
    e.add_field(name="Post ID",  value=f"`{post_id}`",  inline=True)
    if url:
        e.add_field(name="View Post", value=f"[Open on Facebook]({url})", inline=True)
    e.add_field(
        name="Message Preview",
        value=f"```{_trunc(message, 300)}```",
        inline=False,
    )
    e.set_footer(text=f"{FOOTER_TEXT} • Manual post — no auto-posting")
    return e


def build_fb_draft_saved_embed(result: dict, message: str) -> discord.Embed:
    """Embed for /facebook-draft — confirms draft saved."""
    if not result.get("success"):
        e = make_embed("❌ Draft Save Failed", color_key="error")
        e.add_field(name="Error", value=result.get("error", "Unknown error"), inline=False)
        return e

    e = make_embed(
        f"📝 Draft #{result.get('id')} Saved",
        color_key="info",
        description="Draft saved to database. Review before posting.",
    )
    e.add_field(
        name="Message Preview",
        value=f"```{_trunc(message, 400)}```",
        inline=False,
    )
    e.add_field(
        name="Next Step",
        value="Use `/facebook-post-test` to publish when ready.",
        inline=False,
    )
    return e


def build_fb_drafts_list_embed(drafts: list[dict]) -> discord.Embed:
    """Embed for listing saved drafts."""
    if not drafts:
        return make_embed("📝 Facebook Drafts", color_key="info",
                          description="No drafts yet. Use `/facebook-draft` to create one.")
    e = make_embed("📝 Facebook Drafts", color_key="content")
    lines = []
    for d in drafts:
        status_icon = {"draft": "📝", "posted": "✅", "deleted": "🗑"}.get(d["status"], "•")
        lines.append(
            f"`#{d['id']}` {status_icon} **{d['type']}** — {d['created_at'][:10]}\n"
            f"    {_trunc(d['message'], 80)}"
        )
    e.add_field(name="Drafts", value="\n".join(lines)[:1024], inline=False)
    return e
