"""Embed builders for scheduler jobs and slash commands."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import discord

from .base import make_embed, COLORS


def _trunc(s, n: int = 50) -> str:
    s = str(s or "Unknown")
    return s[:n] + "…" if len(s) > n else s


def _fi(v) -> str:
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "—"


def _fp(v) -> str:
    try:
        return f"฿{float(v):,.0f}"
    except Exception:
        return "—"


# ---------------------------------------------------------------------------
# Trend Watch (12:00)
# ---------------------------------------------------------------------------

def build_trend_watch_embeds(data: dict) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []

    momentum = data.get("social_momentum", [])
    momentum_e = make_embed(
        title="📈 Midday Trend Watch — Social Momentum",
        color_key="trend",
        description="Products where likes are growing faster than purchases",
    )
    if momentum:
        for i, row in enumerate(momentum[:8], 1):
            name, likes, sold, price, ratio = row
            momentum_e.add_field(
                name=f"{i}. {_trunc(name)}",
                value=f"Likes: **{_fi(likes)}** | Sold: **{_fi(sold)}** | Ratio: **{float(ratio):.2f}x** | {_fp(price)}",
                inline=False,
            )
    else:
        momentum_e.description = "No social momentum signals found."
    embeds.append(momentum_e)

    promo = data.get("promo_surge", [])
    promo_e = make_embed(
        title="🔥 Midday Trend Watch — Promo Surge",
        color_key="trend",
        description="High discount (≥25%) + high sales (≥500 units)",
    )
    if promo:
        for i, row in enumerate(promo[:8], 1):
            name, discount, sold, price = row
            promo_e.add_field(
                name=f"{i}. {_trunc(name)}",
                value=f"Discount: **{float(discount):.0f}%** | Sold: **{_fi(sold)}** | {_fp(price)}",
                inline=False,
            )
    else:
        promo_e.description = "No promo surge signals found."
    embeds.append(promo_e)

    new_viral = data.get("new_viral", [])
    viral_e = make_embed(
        title="🌱 Midday Trend Watch — Emerging Viral",
        color_key="viral",
        description="High likes (≥1,000) with lower sold count (emerging products)",
    )
    if new_viral:
        for i, row in enumerate(new_viral[:8], 1):
            name, likes, sold, price = row
            viral_e.add_field(
                name=f"{i}. {_trunc(name)}",
                value=f"Likes: **{_fi(likes)}** | Sold: **{_fi(sold)}** | {_fp(price)}",
                inline=False,
            )
    else:
        viral_e.description = "No emerging viral signals found."
    embeds.append(viral_e)

    return embeds


# ---------------------------------------------------------------------------
# Content Worklist (morning brief section)
# ---------------------------------------------------------------------------

def build_content_worklist_embed(worklist: list[dict]) -> discord.Embed:
    e = make_embed(
        title="📋 Today's Content Worklist",
        color_key="content",
        description=f"{len(worklist)} items | Ranked by Priority Score",
    )
    for i, item in enumerate(worklist[:10], 1):
        name     = _trunc(item.get("name", ""), 40)
        priority = item.get("priority", "P4")
        hook     = item.get("hook", "")
        fmt      = item.get("format", "")
        platform = item.get("platform", "")
        e.add_field(
            name=f"{i}. [{priority}] {name}",
            value=f"Hook: _{hook}_\nFormat: **{fmt}** | Platform: {platform}",
            inline=False,
        )
    return e


# ---------------------------------------------------------------------------
# Auto Queue Result
# ---------------------------------------------------------------------------

def build_auto_queue_result_embed(
    results: dict[str, list[str]],
    total_ok: int,
    total_skip: int,
) -> discord.Embed:
    e = make_embed(
        title="🤖 Auto Queue Generator — Complete",
        color_key="queue",
        description=f"**{total_ok}** items queued | **{total_skip}** skipped",
    )
    for category, names in results.items():
        if names:
            value = "\n".join(f"• {_trunc(n, 45)}" for n in names) or "—"
        else:
            value = "No products found"
        e.add_field(name=f"📦 {category}", value=value, inline=False)
    return e


# ---------------------------------------------------------------------------
# Weekly Report Summary
# ---------------------------------------------------------------------------

def build_weekly_report_embed(data: dict, exported: list[Path]) -> discord.Embed:
    total    = data.get("total_products", 0)
    comm     = data.get("total_commission", 0.0)
    gen_at   = data.get("generated_at", datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M"))
    file_names = ", ".join(p.name for p in exported) if exported else "none"

    e = make_embed(
        title="📊 Weekly Report",
        color_key="operator",
        description=(
            f"Products analysed: **{int(total):,}**  |  "
            f"Total Commission: **฿{float(comm):,.2f}**\n"
            f"Exported: `{file_names}`\n"
            f"Generated: {gen_at}"
        ),
    )

    opps = data.get("opportunities", [])[:5]
    if opps:
        opp_lines = "\n".join(
            f"{i}. {_trunc(r[0], 40)} — score **{_fi(r[3])}**"
            for i, r in enumerate(opps, 1)
        )
        e.add_field(name="🎯 Top Opportunities", value=opp_lines, inline=False)

    viral = data.get("viral_candidates", [])[:5]
    if viral:
        v_lines = "\n".join(
            f"{i}. {_trunc(r[0], 40)} — viral **{_fi(r[2])}**"
            for i, r in enumerate(viral, 1)
        )
        e.add_field(name="🔥 Top Viral", value=v_lines, inline=False)

    return e


# ---------------------------------------------------------------------------
# Scheduler Status
# ---------------------------------------------------------------------------

def build_scheduler_status_embed(status: dict) -> discord.Embed:
    running = status.get("running", False)
    state   = "🟢 Running" if running else "🔴 Stopped"
    jobs    = status.get("jobs", [])

    e = make_embed(
        title=f"⏰ Scheduler Status — {state}",
        color_key="operator" if running else "error",
        description=f"{len(jobs)} job(s) registered",
    )
    for job in jobs:
        e.add_field(
            name=f"📌 {job['label']}",
            value=f"{job['description']}\nNext run: **{job['next_run']}**",
            inline=False,
        )
    return e


# ---------------------------------------------------------------------------
# Job Run Result
# ---------------------------------------------------------------------------

def build_job_result_embed(job_id: str, label: str, success: bool, detail: str = "") -> discord.Embed:
    if success:
        e = make_embed(
            title=f"✅ Job Triggered: {label}",
            color_key="success",
            description=f"Job `{job_id}` executed successfully.\n{detail}",
        )
    else:
        e = make_embed(
            title=f"❌ Job Failed: {label}",
            color_key="error",
            description=f"```\n{detail[:1800]}\n```",
        )
    return e
