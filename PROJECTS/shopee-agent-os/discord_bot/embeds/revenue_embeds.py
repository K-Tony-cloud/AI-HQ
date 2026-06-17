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


def build_revenue_summary_embed(data: dict) -> discord.Embed:
    """Single embed for /revenue-summary."""
    if data.get("error"):
        return make_embed("❌ Revenue Summary", color_key="error", description=data["error"])

    cr  = data.get("conversion_rate", 0)
    epc = data.get("epc", 0)
    e = make_embed(
        "💰 Revenue Summary",
        color_key="profit",
        description=(
            f"Period: **{data.get('date_from','—')}** → **{data.get('date_to','—')}**  "
            f"({data.get('total_days', 0)} days)"
        ),
    )
    e.add_field(name="👆 Clicks",        value=f"**{_fi(data.get('total_clicks',0))}**",      inline=True)
    e.add_field(name="📦 Orders",        value=f"**{_fi(data.get('total_orders',0))}**",      inline=True)
    e.add_field(name="💳 Conv Rate",     value=f"**{cr:.2f}%**",                              inline=True)
    e.add_field(name="💵 Revenue",       value=f"**{_fp(data.get('total_revenue',0))}**",     inline=True)
    e.add_field(name="🏦 Commission",    value=f"**{_fp(data.get('total_commission',0))}**",  inline=True)
    e.add_field(name="📈 EPC/100",       value=f"**{_fp(epc)}**",                             inline=True)
    e.add_field(name="🛍 Products",      value=str(data.get("total_products", 0)),            inline=True)
    e.add_field(name="📂 Categories",    value=str(data.get("total_categories", 0)),          inline=True)
    return e


def build_revenue_products_embed(items: list[dict], keyword: str = "") -> discord.Embed:
    """Per-product table for /revenue-products."""
    title = "🛍 Revenue Products" + (f" — '{keyword}'" if keyword else "")
    if not items:
        return make_embed(title, color_key="info",
                          description="No data found. Import a commission report first.")
    e = make_embed(title, color_key="content")
    lines = []
    for i, p in enumerate(items, 1):
        lines.append(
            f"`{i:>2}.` **{_trunc(p['name'], 40)}**\n"
            f"      Orders: {_fi(p['orders'])} | Revenue: {_fp(p['revenue'])} | "
            f"Commission: **{_fp(p['commission'])}** | Last: {p.get('last_date', '—')}"
        )
    chunk: list[str] = []
    field_n = 1
    for line in lines:
        chunk.append(line)
        if len("\n".join(chunk)) > 900:
            e.add_field(name="Products (cont.)" if field_n > 1 else "Products",
                        value="\n".join(chunk[:-1])[:1024], inline=False)
            chunk = [chunk[-1]]
            field_n += 1
    if chunk:
        e.add_field(name="Products" if field_n == 1 else "Products (cont.)",
                    value="\n".join(chunk)[:1024], inline=False)
    return e


def build_revenue_top_embed(items: list[dict], metric: str) -> discord.Embed:
    """Top N products by metric for /revenue-top."""
    icons = {"orders": "📦", "revenue": "💵", "commission": "🏦"}
    icon = icons.get(metric, "📊")
    if not items:
        return make_embed(f"{icon} Top by {metric.title()}", color_key="info",
                          description="No data. Import a commission report first.")
    e = make_embed(f"{icon} Top by {metric.title()}", color_key="opportunity")
    lines = []
    for p in items:
        val = p.get(metric, 0)
        val_str = _fp(val) if metric in ("revenue", "commission") else _fi(val)
        extra = ""
        if metric != "commission":
            extra = f" | Commission: {_fp(p['commission'])}"
        elif metric != "revenue":
            extra = f" | Revenue: {_fp(p['revenue'])}"
        lines.append(
            f"`{p['rank']:>2}.` **{_trunc(p['name'], 42)}**\n"
            f"      {metric.title()}: **{val_str}** | Orders: {_fi(p['orders'])}{extra}"
        )
    e.add_field(name=f"Top {len(items)} by {metric.title()}",
                value="\n".join(lines)[:1024], inline=False)
    return e


def build_revenue_category_embed(data: dict) -> discord.Embed:
    """Category revenue breakdown for /revenue-category — three ranked sections."""
    if not data:
        return make_embed("📂 Revenue by Category", color_key="info",
                          description="No data. Import a commission report first.")

    e = make_embed("📂 Revenue by Category", color_key="trend")

    def _lines(items: list[dict], rank_key: str) -> str:
        if not items:
            return "—"
        out = []
        for i, c in enumerate(items, 1):
            val = c[rank_key]
            val_str = _fp(val) if rank_key in ("commission", "revenue") else _fi(val)
            avg = c.get("avg_commission_per_order", 0)
            out.append(
                f"`{i:>2}.` **{_trunc(c['category'], 28)}**\n"
                f"      {rank_key.title()}: **{val_str}** | "
                f"Orders: {_fi(c['orders'])} | "
                f"Avg/order: {_fp(avg)} | "
                f"{c['products']} products"
            )
        return "\n".join(out)

    e.add_field(
        name="🏦 By Commission",
        value=_lines(data.get("by_commission", []), "commission")[:1024],
        inline=False,
    )
    e.add_field(
        name="💵 By Revenue",
        value=_lines(data.get("by_revenue", []), "revenue")[:1024],
        inline=False,
    )
    e.add_field(
        name="📦 By Orders",
        value=_lines(data.get("by_orders", []), "orders")[:1024],
        inline=False,
    )
    return e


def build_revenue_data_source_embed(data: dict) -> discord.Embed:
    """Show real import table status for /revenue-data-source."""
    if data.get("error"):
        return make_embed("📊 Revenue Data Source", color_key="error", description=data["error"])

    has_commission = data.get("has_commission", False)
    has_clicks     = data.get("has_clicks", False)

    if not has_commission and not has_clicks:
        return make_embed(
            "📊 Revenue Data Source",
            color_key="info",
            description=(
                "**No real revenue data imported yet.**\n\n"
                "Use `/import-commission-report` to import your Shopee TH commission report.\n"
                "Use `/import-click-report` to import your Shopee TH click report."
            ),
        )

    e = make_embed("📊 Revenue Data Source", color_key="success",
                   description="Showing real Shopee affiliate import tables only.")

    if has_commission:
        e.add_field(
            name="📄 Commission Report",
            value=(
                f"Rows: **{data.get('commission_rows', 0):,}** orders\n"
                f"Products: **{data.get('commission_products', 0)}**\n"
                f"Period: {data.get('commission_from','—')} → {data.get('commission_to','—')}\n"
                f"Total Commission: **{_fp(data.get('commission_total', 0))}**"
            ),
            inline=True,
        )
    else:
        e.add_field(
            name="📄 Commission Report",
            value="Not imported yet.\nUse `/import-commission-report`",
            inline=True,
        )

    if has_clicks:
        e.add_field(
            name="👆 Click Report",
            value=(
                f"Days tracked: **{data.get('click_rows', 0)}**\n"
                f"Total Clicks: **{_fi(data.get('total_clicks', 0))}**\n"
                f"Period: {data.get('click_from','—')} → {data.get('click_to','—')}"
            ),
            inline=True,
        )
    else:
        e.add_field(
            name="👆 Click Report",
            value="Not imported yet.\nUse `/import-click-report`",
            inline=True,
        )

    return e


def build_revenue_debug_embed(data: dict) -> discord.Embed:
    """Full diagnostic embed for /revenue-debug."""
    e = make_embed("🔍 Revenue Debug", color_key="info")
    e.add_field(name="DB Path",   value=f"`{data.get('db_path','?')}`",         inline=False)
    e.add_field(name="DB Exists", value="✅ Yes" if data.get("db_exists") else "❌ No", inline=True)

    if data.get("error"):
        e.add_field(name="Error", value=f"```{data['error'][:900]}```", inline=False)
        return e

    all_tables = data.get("all_tables", [])
    e.add_field(
        name="All Tables",
        value=", ".join(f"`{t}`" for t in all_tables) or "none",
        inline=False,
    )

    for key, label, icon in [
        ("commission", "commission_report", "📄"),
        ("click",      "click_report",      "👆"),
        ("revenue_feedback", "revenue_feedback", "📦"),
    ]:
        rows = data.get(f"{key}_rows", -1)
        if rows == -1:
            e.add_field(name=f"{icon} {label}", value="❌ table missing", inline=True)
        else:
            cols   = data.get(f"{key}_cols", [])
            latest = data.get(f"{key}_latest")
            latest_str = str(latest)[:200] if latest else "—"
            e.add_field(
                name=f"{icon} {label}",
                value=(
                    f"Rows: **{rows:,}**\n"
                    f"Cols: {len(cols)}\n"
                    f"Latest: `{latest_str[:150]}`"
                ),
                inline=False,
            )

    legacy = data.get("legacy_in_revenue_feedback", {})
    if legacy:
        parts = [f"`{src}`: **{cnt}** rows" for src, cnt in legacy.items()]
        e.add_field(
            name="⚠️ Legacy data in revenue_feedback",
            value="\n".join(parts) + "\nUse `/revenue-migrate` to move to correct tables.",
            inline=False,
        )
    else:
        e.add_field(name="Legacy data", value="✅ None (all data in correct tables)", inline=False)

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
