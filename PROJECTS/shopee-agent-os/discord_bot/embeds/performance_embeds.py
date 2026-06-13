"""Embed builders for performance commands."""

from __future__ import annotations

import discord

from .base import make_embed

PAGE_SIZE = 10


def _fp(v) -> str:
    try:
        return f"฿{float(v):,.2f}"
    except Exception:
        return "—"


def _fi(v) -> str:
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "—"


def build_top_profit_pages(records: list[dict], page_size: int = PAGE_SIZE) -> list[discord.Embed]:
    if not records:
        return [make_embed(
            "💰 Top Profit Products", "profit",
            "No affiliate data found.\nRun `shopee import-affiliate-report` first.",
        )]

    pages: list[discord.Embed] = []
    for chunk_start in range(0, len(records), page_size):
        chunk = records[chunk_start: chunk_start + page_size]
        e = make_embed(
            title="💰 Top Profit Products",
            color_key="profit",
            description=f"Ranked by Commission → EPC → Conversion Rate | {len(records)} products",
        )
        for i, r in enumerate(chunk, chunk_start + 1):
            name = str(r.get("product") or r.get("name") or "Unknown")[:48]
            comm = _fp(r.get("total_commission") or r.get("commission") or 0)
            epc  = f"{float(r.get('epc') or 0):.4f}"
            conv = f"{float(r.get('conversion_rate') or 0):.2f}%"
            rev  = _fp(r.get("revenue") or 0)
            e.add_field(
                name=f"{i}. {name}",
                value=f"Commission: **{comm}** | EPC: **{epc}** | Conv: **{conv}** | Revenue: {rev}",
                inline=False,
            )
        pages.append(e)

    return pages or [make_embed("💰 Top Profit Products", "profit", "No affiliate data found.\nRun `shopee import-affiliate-report` first.")]


def build_daily_performance_embed(records: list[dict]) -> discord.Embed:
    e = make_embed(
        title="📊 Daily Performance (last 7 days)",
        color_key="profit",
        description="Clicks | Orders | Conv.% | EPC | Revenue | Commission",
    )
    totals = {"clicks": 0.0, "orders": 0.0, "revenue": 0.0, "commission": 0.0}
    for r in records:
        date  = str(r.get("date", ""))
        clk   = int(float(r.get("clicks") or 0))
        ord_  = int(float(r.get("orders") or 0))
        conv  = float(r.get("conversion_rate") or 0)
        epc   = float(r.get("epc") or 0)
        rev   = float(r.get("revenue") or 0)
        comm  = float(r.get("commission") or 0)
        totals["clicks"]     += clk
        totals["orders"]     += ord_
        totals["revenue"]    += rev
        totals["commission"] += comm
        e.add_field(
            name=date,
            value=f"Clicks: **{clk:,}** | Orders: **{ord_:,}** | Conv: **{conv:.2f}%** | EPC: **{epc:.4f}** | Rev: **฿{rev:,.0f}** | Comm: **฿{comm:,.0f}**",
            inline=False,
        )
    e.add_field(
        name="─── Totals ───",
        value=f"Clicks: **{int(totals['clicks']):,}** | Orders: **{int(totals['orders']):,}** | Revenue: **฿{totals['revenue']:,.2f}** | Commission: **฿{totals['commission']:,.2f}**",
        inline=False,
    )
    return e
