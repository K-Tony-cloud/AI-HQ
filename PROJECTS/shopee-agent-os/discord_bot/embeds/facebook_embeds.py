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


def build_fb_debug_embed(data: dict) -> discord.Embed:
    """Embed for /facebook-debug — full token/page diagnostic."""
    diagnosis = data.get("diagnosis", [])
    has_error = any(line.startswith("❌") for line in diagnosis)
    color = "error" if has_error else "success"
    e = make_embed("🔍 Facebook Debug Report", color_key=color)

    # Credentials
    e.add_field(
        name="Credentials",
        value=(
            f"Page ID: `{data.get('page_id') or '—'}`\n"
            f"Token: `{data.get('token_preview') or '—'}`\n"
            f"Token set: {'✅' if data.get('token_set') else '❌'} | "
            f"Page ID set: {'✅' if data.get('page_id_set') else '❌'}"
        ),
        inline=False,
    )

    # Token kind
    kind_map = {
        "page_token":        "✅ Page Token",
        "user_token":        "⚠️ User Token (wrong type)",
        "invalid_or_expired": "❌ Invalid / Expired",
    }
    kind_label = kind_map.get(data.get("token_kind", ""), data.get("token_kind", "unknown"))
    e.add_field(name="Token Kind", value=kind_label, inline=True)

    # /me result
    me = data.get("me")
    me_err = data.get("me_raw_error")
    if me:
        e.add_field(name="/me", value=f"`id={me.get('id')}` {me.get('name','')}", inline=True)
    elif me_err:
        e.add_field(name="/me error", value=_trunc(me_err, 200), inline=False)

    # Permissions
    perms = data.get("permissions", [])
    perms_err = data.get("permissions_raw_error")
    if perms:
        e.add_field(name="Permissions", value=", ".join(f"`{p}`" for p in perms), inline=False)
    elif perms_err:
        e.add_field(name="Permissions error", value=_trunc(perms_err, 200), inline=False)
    else:
        e.add_field(name="Permissions", value="*(none returned)*", inline=False)

    # /me/accounts
    accounts = data.get("accounts", [])
    accts_err = data.get("accounts_raw_error")
    if accounts:
        lines = [
            f"`{a.get('id')}` **{a.get('name','')}** — {a.get('category','')}"
            for a in accounts[:5]
        ]
        e.add_field(name="/me/accounts", value="\n".join(lines), inline=False)
    elif accts_err:
        e.add_field(name="/me/accounts error", value=_trunc(accts_err, 200), inline=False)
    else:
        e.add_field(name="/me/accounts", value="*(empty)*", inline=False)

    # /{page_id}
    page = data.get("page")
    page_err = data.get("page_raw_error")
    if page:
        e.add_field(
            name=f"/{data.get('page_id')}",
            value=f"`{page.get('id')}` **{page.get('name','')}** — {page.get('category','')}",
            inline=False,
        )
    elif page_err:
        e.add_field(name=f"/{data.get('page_id')} error", value=_trunc(page_err, 200), inline=False)

    # Post test — raw body
    post = data.get("post_test", {})
    if post:
        if post.get("success"):
            e.add_field(name="POST test", value=f"✅ Published! `{post.get('raw_body','')}`", inline=False)
        else:
            raw = post.get("raw_body", post.get("error", "no response"))
            e.add_field(
                name=f"POST test HTTP {post.get('http_status', '?')}",
                value=f"```json\n{_trunc(raw, 600)}\n```",
                inline=False,
            )

    # Diagnosis
    if diagnosis:
        e.add_field(name="Diagnosis", value="\n".join(diagnosis)[:1024], inline=False)

    e.set_footer(text=f"{FOOTER_TEXT} • Facebook Graph API v19.0 — debug")
    return e
