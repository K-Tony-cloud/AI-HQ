"""Embed builders for operator commands."""

from __future__ import annotations

import discord

from .base import make_embed

PAGE_SIZE = 8


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


def _trunc(s, n: int = 52) -> str:
    s = str(s or "Unknown")
    return s[:n] + "…" if len(s) > n else s


# ---------------------------------------------------------------------------
# Morning Brief
# ---------------------------------------------------------------------------

def build_morning_brief_embeds(data: dict) -> list[discord.Embed]:
    gen_at = data.get("generated_at", "")
    embeds: list[discord.Embed] = []

    # Opportunities
    opp_e = make_embed(
        title="🌅 Morning Brief — Top Opportunities",
        color_key="opportunity",
        description=f"Generated: {gen_at}",
    )
    for i, (name, sold, price, score) in enumerate(data.get("top_opportunities", []), 1):
        opp_e.add_field(
            name=f"{i}. {_trunc(name)}",
            value=f"Sold: **{_fi(sold)}** | Price: **{_fp(price)}** | Score: **{_fi(score)}**",
            inline=False,
        )
    embeds.append(opp_e)

    # Viral
    viral_e = make_embed(title="🔥 Morning Brief — Top Viral", color_key="viral")
    for i, (name, price, vscore) in enumerate(data.get("top_viral", []), 1):
        viral_e.add_field(
            name=f"{i}. {_trunc(name)}",
            value=f"Price: **{_fp(price)}** | Viral Score: **{_fi(vscore)}**",
            inline=False,
        )
    embeds.append(viral_e)

    # Niches
    niches = data.get("top_niches", [])
    if niches:
        niche_e = make_embed(title="🔭 Morning Brief — Top Niches", color_key="niche")
        for i, (cat, cnt, avg_sold) in enumerate(niches, 1):
            niche_e.add_field(
                name=f"{i}. {_trunc(cat)}",
                value=f"Products: **{_fi(cnt)}** | Avg Sold: **{_fi(avg_sold)}**",
                inline=False,
            )
        embeds.append(niche_e)

    # Profit
    profit = data.get("top_profit", [])
    if profit:
        profit_e = make_embed(title="💰 Morning Brief — Top Profit", color_key="profit")
        for i, (name, comm, epc, conv) in enumerate(profit, 1):
            profit_e.add_field(
                name=f"{i}. {_trunc(name)}",
                value=f"Commission: **{_fp(comm)}** | EPC: **{float(epc):.4f}** | Conv: **{float(conv):.2f}%**",
                inline=False,
            )
        embeds.append(profit_e)

    return embeds


# ---------------------------------------------------------------------------
# Executive Summary
# ---------------------------------------------------------------------------

def build_executive_summary_embeds(data: dict) -> list[discord.Embed]:
    total   = data.get("total_products", 0)
    comm    = data.get("total_commission", 0.0)
    gen_at  = data.get("generated_at", "")
    embeds: list[discord.Embed] = []

    # Header
    header = make_embed(
        title="📊 Executive Summary",
        color_key="operator",
        description=(
            f"Products: **{int(total):,}**  |  "
            f"Total Commission: **฿{float(comm):,.2f}**\n"
            f"Generated: {gen_at}"
        ),
    )
    embeds.append(header)

    # Opportunities
    opp_e = make_embed(title="🎯 Opportunities (Top 10)", color_key="opportunity")
    for i, (name, sold, price, score) in enumerate(data.get("opportunities", []), 1):
        opp_e.add_field(
            name=f"{i}. {_trunc(name)}",
            value=f"Sold: **{_fi(sold)}** | Price: **{_fp(price)}** | Score: **{_fi(score)}**",
            inline=False,
        )
    embeds.append(opp_e)

    # Market Gaps
    gaps = data.get("market_gaps", [])
    if gaps:
        gap_e = make_embed(title="🔭 Market Gaps", color_key="niche")
        for i, (cat, cnt, avg) in enumerate(gaps, 1):
            gap_e.add_field(
                name=f"{i}. {_trunc(cat)}",
                value=f"Products: **{_fi(cnt)}** | Avg Sold: **{_fi(avg)}**",
                inline=False,
            )
        embeds.append(gap_e)

    # Viral Candidates
    viral_e = make_embed(title="🔥 Viral Candidates", color_key="viral")
    for i, (name, price, vscore) in enumerate(data.get("viral_candidates", []), 1):
        viral_e.add_field(
            name=f"{i}. {_trunc(name)}",
            value=f"Price: **{_fp(price)}** | Score: **{_fi(vscore)}**",
            inline=False,
        )
    embeds.append(viral_e)

    # Profit Candidates
    profit = data.get("profit_candidates", [])
    if profit:
        profit_e = make_embed(title="💰 Profit Candidates", color_key="profit")
        for i, (name, comm_v, epc) in enumerate(profit, 1):
            profit_e.add_field(
                name=f"{i}. {_trunc(name)}",
                value=f"Commission: **{_fp(comm_v)}** | EPC: **{float(epc):.4f}**",
                inline=False,
            )
        embeds.append(profit_e)

    # Risks
    risks = data.get("risks", [])
    if risks:
        risk_e = make_embed(title="⚠️ Risks (High Price / Low Sales)", color_key="error")
        for i, (name, price, sold) in enumerate(risks, 1):
            risk_e.add_field(
                name=f"{i}. {_trunc(name)}",
                value=f"Price: **{_fp(price)}** | Sold: **{_fi(sold)}**",
                inline=False,
            )
        embeds.append(risk_e)

    return embeds
