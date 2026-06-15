"""Embed builders for Phase 11 — Revenue Intelligence."""

from __future__ import annotations

import discord

from .base import FOOTER_TEXT, make_embed


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


def _trunc(s: str, n: int) -> str:
    s = str(s or "")
    return s[:n] + "…" if len(s) > n else s


def build_revenue_dashboard_embeds(data: dict) -> list[discord.Embed]:
    """Return 3 embeds: summary + performance tables + EPC & worst."""
    if data.get("error"):
        e = make_embed("❌ Revenue Dashboard", color_key="error", description=data["error"])
        return [e]

    summary  = data.get("summary", {})
    embeds: list[discord.Embed] = []

    # ── Embed 1: Summary ──────────────────────────────────────────────────────
    total_clicks     = summary.get("total_clicks", 0)
    total_orders     = summary.get("total_orders", 0)
    total_commission = summary.get("total_commission", 0)
    total_revenue    = summary.get("total_revenue", 0)
    epc              = summary.get("epc", 0)
    cr               = round(total_orders / total_clicks * 100, 2) if total_clicks else 0

    e1 = make_embed(
        "💰 Revenue Intelligence Dashboard",
        color_key="profit",
        description=(
            f"Period: **{summary.get('date_from','—')}** → **{summary.get('date_to','—')}**\n"
            f"Products tracked: **{_fi(summary.get('total_products',0))}**"
        ),
    )
    e1.add_field(name="👆 Total Clicks",      value=f"**{_fi(total_clicks)}**",          inline=True)
    e1.add_field(name="📦 Total Orders",      value=f"**{_fi(total_orders)}**",          inline=True)
    e1.add_field(name="💳 Conversion Rate",   value=f"**{cr:.2f}%**",                   inline=True)
    e1.add_field(name="💵 Total Revenue",     value=f"**{_fp(total_revenue)}**",         inline=True)
    e1.add_field(name="🏦 Total Commission",  value=f"**{_fp(total_commission)}**",      inline=True)
    e1.add_field(name="📈 EPC (per 100)",     value=f"**{_fp(epc)}**",                  inline=True)
    embeds.append(e1)

    # ── Embed 2: Top Clicked + Top Orders + Top Commission ────────────────────
    e2 = make_embed("📊 Top Performance", color_key="opportunity")

    def _rank_lines(items: list[dict], val_key: str, val_label: str, extra_key: str = "", extra_label: str = "") -> str:
        if not items:
            return "—"
        lines = []
        for i, p in enumerate(items, 1):
            val_str   = _fp(p[val_key]) if "commission" in val_key or "revenue" in val_key else _fi(p[val_key])
            extra_str = ""
            if extra_key and extra_label:
                ev = p.get(extra_key, 0)
                extra_str = f" | {extra_label}: {_fp(ev) if 'commission' in extra_key or 'revenue' in extra_key else _fi(ev)}"
            lines.append(f"`{i}.` {_trunc(p['name'], 38)}\n    {val_label}: **{val_str}**{extra_str}")
        return "\n".join(lines)

    e2.add_field(
        name="👆 Top Clicked",
        value=_rank_lines(data.get("top_clicked", []), "clicks", "Clicks", "orders", "Orders")[:1024],
        inline=False,
    )
    e2.add_field(
        name="📦 Top Orders",
        value=_rank_lines(data.get("top_orders", []), "orders", "Orders", "revenue", "Revenue")[:1024],
        inline=False,
    )
    e2.add_field(
        name="🏦 Top Commission",
        value=_rank_lines(data.get("top_commission", []), "commission", "Commission", "clicks", "Clicks")[:1024],
        inline=False,
    )
    embeds.append(e2)

    # ── Embed 3: EPC Leaders + Worst Performing ───────────────────────────────
    e3 = make_embed("🔬 EPC Analysis & Worst Performers", color_key="trend")

    epc_items = data.get("top_epc", [])
    if epc_items:
        epc_lines = []
        for i, p in enumerate(epc_items, 1):
            epc_lines.append(
                f"`{i}.` {_trunc(p['name'], 38)}\n"
                f"    EPC: **{_fp(p['epc'])}** | Clicks: {_fi(p['clicks'])} | Commission: {_fp(p['commission'])}"
            )
        e3.add_field(
            name="📈 EPC Leaders (min 5 clicks)",
            value="\n".join(epc_lines)[:1024],
            inline=False,
        )
    else:
        e3.add_field(name="📈 EPC Leaders", value="Not enough click data yet (min 5 clicks)", inline=False)

    worst_items = data.get("worst_performing", [])
    if worst_items:
        worst_lines = []
        for i, p in enumerate(worst_items, 1):
            worst_lines.append(
                f"`{i}.` {_trunc(p['name'], 38)}\n"
                f"    Clicks: {_fi(p['clicks'])} | Orders: **0** | ⚠️ Zero conversions"
            )
        e3.add_field(
            name="🔴 Worst Performing (clicks but 0 orders)",
            value="\n".join(worst_lines)[:1024],
            inline=False,
        )
    else:
        e3.add_field(
            name="🔴 Worst Performing",
            value="✅ All products with clicks have at least 1 order",
            inline=False,
        )

    e3.set_footer(text=f"{FOOTER_TEXT} • EPC = Earnings Per 100 Clicks")
    embeds.append(e3)

    return embeds


def build_import_result_embed(result: dict, report_type: str, filename: str) -> discord.Embed:
    rows = result.get("rows_imported", 0)
    color = "success" if rows > 0 else "info"
    icon  = {"click": "👆", "order": "📦", "revenue": "💰"}.get(report_type, "📄")
    e = make_embed(
        f"{icon} {report_type.title()} Report Imported",
        color_key=color,
    )
    e.add_field(name="File",          value=filename,                inline=False)
    e.add_field(name="Rows Imported", value=f"**{rows:,}**",        inline=True)
    e.add_field(name="Source Tag",    value=f"`{report_type}`",     inline=True)
    if rows > 0:
        e.add_field(
            name="Next Step",
            value="Use `/revenue-dashboard` to view performance analytics",
            inline=False,
        )
    return e


def build_revenue_winners_embed(data: dict) -> discord.Embed:
    """Compact embed for morning brief — top 3 commission earners."""
    if data.get("error"):
        return make_embed("💰 Revenue Winners", color_key="info",
                          description="No revenue data yet.")

    top = data.get("top_commission", [])[:3]
    summary = data.get("summary", {})

    e = make_embed("💰 Revenue Winners Today", color_key="profit")
    e.add_field(
        name="Total Commission",
        value=f"**{_fp(summary.get('total_commission', 0))}**",
        inline=True,
    )
    e.add_field(
        name="Total Orders",
        value=f"**{_fi(summary.get('total_orders', 0))}**",
        inline=True,
    )
    e.add_field(
        name="EPC (per 100)",
        value=f"**{_fp(summary.get('epc', 0))}**",
        inline=True,
    )

    if top:
        lines = []
        for i, p in enumerate(top, 1):
            lines.append(
                f"`{i}.` **{_trunc(p['name'], 45)}**\n"
                f"    Commission: {_fp(p['commission'])} | Clicks: {_fi(p['clicks'])}"
            )
        e.add_field(name="🏆 Top Earners", value="\n".join(lines)[:1024], inline=False)

    return e
