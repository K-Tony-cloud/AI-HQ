"""Affiliate Operator Command Center — daily operations hub for affiliate managers."""

from __future__ import annotations

import csv as csv_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .config import config, build_column_map

console = Console()

# ---------------------------------------------------------------------------
# Category → global_category1 ILIKE patterns
# ---------------------------------------------------------------------------

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "Gadget":  ["mobile & gadget", "computers & accessories", "cameras & drones",
                "gaming & consoles", "home appliances", "audio"],
    "Health":  ["health"],
    "Baby":    ["mom & baby", "baby & kids"],
    "Camping": ["sports & outdoors"],
    "Home":    ["home & living"],
    "Mobile":  ["mobile & gadget"],
    "Beauty":  ["beauty", "health beauty"],
    "Fashion": ["fashion", "women fashion", "men fashion"],
    "Food":    ["food & beverages", "grocery"],
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")
    return duckdb.connect(str(config.db_path), read_only=read_only)


def _schema(con: duckdb.DuckDBPyConnection, table: str) -> tuple[list[str], dict[str, str]]:
    cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'"
    ).fetchall()]
    return cols, build_column_map(cols)


def _q(name: str) -> str:
    return f'"{name}"'


def _safe(col: str) -> str:
    return f"COALESCE(TRY_CAST({_q(col)} AS DOUBLE), 0.0)"


def _col(lower_map: dict[str, str], *candidates: str) -> str | None:
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return name in [r[0] for r in con.execute("SHOW TABLES").fetchall()]


def _has_view(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type='VIEW'"
    ).fetchall()
    return name in [r[0] for r in rows]


def _opp_expr(lower_map: dict[str, str]) -> str:
    sold   = _col(lower_map, "item_sold", "sales", "sold") or "item_sold"
    likes  = _col(lower_map, "like", "likes")   or "like"
    disc   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"
    shop_r = _col(lower_map, "shop_rating")     or "shop_rating"
    item_r = _col(lower_map, "item_rating", "rating_star", "rating") or shop_r
    return (
        f"ROUND("
        f"{_safe(sold)}*0.40 + {_safe(likes)}*0.15 + {_safe(disc)}*0.15 + "
        f"{_safe(shop_r)}*100.0*0.15 + {_safe(item_r)}*100.0*0.15"
        f", 1)"
    )


def _viral_expr(lower_map: dict[str, str]) -> str:
    sold   = _col(lower_map, "item_sold", "sales") or "item_sold"
    likes  = _col(lower_map, "like", "likes")      or "like"
    disc   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"
    return (
        f"ROUND("
        f"{_safe(sold)}*0.35 + {_safe(likes)}*0.35 + {_safe(disc)}*100.0*0.30"
        f", 1)"
    )


def _cat1_filter(lower_map: dict[str, str], patterns: list[str]) -> str:
    cat1 = _col(lower_map, "global_category1")
    if not cat1 or not patterns:
        return "1=1"
    parts = [f"LOWER({_q(cat1)}) LIKE '%{p.lower()}%'" for p in patterns]
    return "(" + " OR ".join(parts) + ")"


def _content_angle(sold: float, likes: float, discount: float, price: float, rating: float) -> str:
    if discount >= 30:
        return "Flash Sale / ลดแรง"
    if likes > 5000:
        return "Viral TikTok / Social Proof"
    if sold > 2000:
        return "Bestseller / ยอดขายสูง"
    if rating >= 4.8:
        return "รีวิว 5 ดาว / Premium"
    if price <= 200:
        return "ราคาถูก / Value for Money"
    if price >= 3000:
        return "High-ticket / ROI Content"
    return "Product Review / Unboxing"


# ---------------------------------------------------------------------------
# morning_brief
# ---------------------------------------------------------------------------

def morning_brief(table_name: str = "products", top: int = 5) -> dict:
    """
    Aggregate morning briefing:
    Top Opportunities, Top Viral, Top Profit Products, Top Niches.
    """
    con = _connect()
    cols, col_map = _schema(con, table_name)
    lower_map = {c.lower(): c for c in cols}

    name_col  = col_map.get("product_name") or (cols[1] if len(cols) > 1 else None)
    sold_col  = col_map.get("sales")
    price_col = col_map.get("price")
    cat3_col  = _col(lower_map, "global_category3") or col_map.get("category")

    opp  = _opp_expr(lower_map)
    viral = _viral_expr(lower_map)

    name_expr  = _q(name_col) if name_col else "NULL"
    sold_expr  = _safe(sold_col) if sold_col else "0"
    price_expr = _safe(price_col) if price_col else "0"

    top_opp = con.execute(f"""
        SELECT {name_expr} AS name, {sold_expr} AS sold,
               {price_expr} AS price, {opp} AS score
        FROM {_q(table_name)}
        ORDER BY score DESC LIMIT {top}
    """).fetchall()

    top_viral = con.execute(f"""
        SELECT {name_expr} AS name, {price_expr} AS price, {viral} AS vscore
        FROM {_q(table_name)}
        WHERE {sold_expr} >= 50
        ORDER BY vscore DESC LIMIT {top}
    """).fetchall()

    top_niches: list = []
    niche_col = cat3_col
    if niche_col and sold_col:
        top_niches = con.execute(f"""
            SELECT {_q(niche_col)} AS cat, COUNT(*) AS cnt,
                   ROUND(AVG({_safe(sold_col)}), 0) AS avg_sold
            FROM {_q(table_name)}
            WHERE {_q(niche_col)} IS NOT NULL
            GROUP BY {_q(niche_col)}
            HAVING COUNT(*) BETWEEN 20 AND 3000
            ORDER BY avg_sold DESC LIMIT {top}
        """).fetchall()

    top_profit: list = []
    if _has_table(con, "affiliate_performance"):
        top_profit = con.execute("""
            SELECT COALESCE(product_name, product_id, 'Unknown') AS name,
                   SUM(commission) AS comm,
                   CASE WHEN SUM(clicks)>0 THEN ROUND(SUM(commission)/SUM(clicks),4) ELSE 0 END AS epc,
                   CASE WHEN SUM(clicks)>0 THEN ROUND(SUM(orders)/SUM(clicks)*100,2) ELSE 0 END AS conv
            FROM affiliate_performance
            GROUP BY product_name, product_id
            ORDER BY comm DESC LIMIT 5
        """).fetchall()

    con.close()
    return {
        "top_opportunities": top_opp,
        "top_viral":         top_viral,
        "top_niches":        top_niches,
        "top_profit":        top_profit,
        "generated_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ---------------------------------------------------------------------------
# category_brief
# ---------------------------------------------------------------------------

def category_brief(category: str, table_name: str = "products", top: int = 20) -> dict:
    """
    Top 20 products in a category with opportunity score,
    profit score, and suggested content angle.
    """
    patterns = CATEGORY_PATTERNS.get(category, [category.lower()])
    con = _connect()
    cols, col_map = _schema(con, table_name)
    lower_map = {c.lower(): c for c in cols}

    name_col   = col_map.get("product_name") or (cols[1] if len(cols) > 1 else None)
    sold_col   = col_map.get("sales")
    price_col  = col_map.get("price")
    likes_col  = _col(lower_map, "like", "likes")
    disc_col   = col_map.get("discount")
    rating_col = col_map.get("rating")

    opp = _opp_expr(lower_map)
    cat_filter = _cat1_filter(lower_map, patterns)

    name_expr  = _q(name_col) if name_col else "NULL"
    sold_expr  = _safe(sold_col)  if sold_col  else "0"
    price_expr = _safe(price_col) if price_col else "0"
    likes_expr = _safe(likes_col) if likes_col else "0"
    disc_expr  = _safe(disc_col)  if disc_col  else "0"
    rat_expr   = _safe(rating_col) if rating_col else "0"

    rows = con.execute(f"""
        SELECT {name_expr} AS name,
               {sold_expr}  AS sold,
               {price_expr} AS price,
               {likes_expr} AS likes,
               {disc_expr}  AS discount,
               {rat_expr}   AS rating,
               {opp}        AS opp_score
        FROM {_q(table_name)}
        WHERE ({cat_filter})
        ORDER BY opp_score DESC
        LIMIT {top}
    """).fetchall()

    # Profit scores from profit_intelligence view if available
    profit_map: dict[str, float] = {}
    if _has_view(con, "profit_intelligence"):
        pr = con.execute("SELECT product_key, profit_score FROM profit_intelligence").fetchall()
        profit_map = {str(r[0]).lower(): float(r[1] or 0) for r in pr}

    con.close()

    enriched = []
    for r in rows:
        name, sold, price, likes, discount, rating, opp_s = r
        angle = _content_angle(sold, likes, discount, price, rating)
        profit = profit_map.get(str(name).lower(), 0.0)
        enriched.append((name, sold, price, opp_s, profit, angle))

    return {"category": category, "products": enriched, "total": len(enriched)}


# ---------------------------------------------------------------------------
# trend_watch
# ---------------------------------------------------------------------------

def trend_watch(table_name: str = "products", top: int = 20) -> dict:
    """
    Find products showing unusual growth signals:
    - Social momentum: high likes/sold ratio
    - Promo surge: high discount + high sales
    - New viral potential: high likes with lower sold count
    """
    con = _connect()
    cols, col_map = _schema(con, table_name)
    lower_map = {c.lower(): c for c in cols}

    name_col   = col_map.get("product_name") or (cols[1] if len(cols) > 1 else None)
    sold_col   = col_map.get("sales")
    likes_col  = _col(lower_map, "like", "likes")
    disc_col   = col_map.get("discount")
    price_col  = col_map.get("price")

    name_expr  = _q(name_col)  if name_col  else "NULL"
    price_expr = _safe(price_col) if price_col else "0"

    # 1. Social momentum — likes growing faster than purchases
    momentum: list = []
    if likes_col and sold_col:
        momentum = con.execute(f"""
            SELECT {name_expr} AS name,
                   {_safe(likes_col)} AS likes,
                   {_safe(sold_col)}  AS sold,
                   {price_expr}       AS price,
                   CASE WHEN {_safe(sold_col)} > 0
                        THEN ROUND({_safe(likes_col)}/{_safe(sold_col)}, 2)
                        ELSE 0 END AS momentum_ratio
            FROM {_q(table_name)}
            WHERE {_safe(sold_col)} >= 100 AND {_safe(likes_col)} >= 500
            ORDER BY momentum_ratio DESC LIMIT {top}
        """).fetchall()

    # 2. Promo surge — high discount + high sales
    promo_surge: list = []
    if disc_col and sold_col:
        promo_surge = con.execute(f"""
            SELECT {name_expr}        AS name,
                   {_safe(disc_col)}  AS discount,
                   {_safe(sold_col)}  AS sold,
                   {price_expr}       AS price
            FROM {_q(table_name)}
            WHERE {_safe(disc_col)} >= 25 AND {_safe(sold_col)} >= 500
            ORDER BY sold DESC LIMIT {top}
        """).fetchall()

    # 3. New viral potential — high likes, lower sold (new/emerging)
    new_viral: list = []
    if likes_col and sold_col:
        new_viral = con.execute(f"""
            SELECT {name_expr}         AS name,
                   {_safe(likes_col)}  AS likes,
                   {_safe(sold_col)}   AS sold,
                   {price_expr}        AS price
            FROM {_q(table_name)}
            WHERE {_safe(likes_col)} >= 1000 AND {_safe(sold_col)} < 500
            ORDER BY likes DESC LIMIT {top}
        """).fetchall()

    con.close()
    return {"social_momentum": momentum, "promo_surge": promo_surge, "new_viral": new_viral}


# ---------------------------------------------------------------------------
# content_worklist
# ---------------------------------------------------------------------------

def content_worklist(table_name: str = "products", top: int = 20) -> list[dict]:
    """
    Daily content work list: Product, Priority, Suggested Hook, Format, Platform.
    Combines opportunity score + viral score + affiliate profit data.
    """
    con = _connect()
    cols, col_map = _schema(con, table_name)
    lower_map = {c.lower(): c for c in cols}

    name_col  = col_map.get("product_name") or (cols[1] if len(cols) > 1 else None)
    sold_col  = col_map.get("sales")
    likes_col = _col(lower_map, "like", "likes")
    disc_col  = col_map.get("discount")
    price_col = col_map.get("price")

    name_expr  = _q(name_col) if name_col else "NULL"
    sold_expr  = _safe(sold_col)  if sold_col  else "0"
    price_expr = _safe(price_col) if price_col else "0"
    likes_expr = _safe(likes_col) if likes_col else "0"
    disc_expr  = _safe(disc_col)  if disc_col  else "0"

    opp   = _opp_expr(lower_map)
    viral = _viral_expr(lower_map)

    rows = con.execute(f"""
        SELECT {name_expr} AS name,
               {sold_expr}  AS sold,
               {price_expr} AS price,
               {likes_expr} AS likes,
               {disc_expr}  AS discount,
               {opp}        AS opp_score,
               {viral}      AS viral_score
        FROM {_q(table_name)}
        ORDER BY opp_score DESC LIMIT {top * 2}
    """).fetchall()

    profit_map: dict[str, float] = {}
    if _has_table(con, "affiliate_performance"):
        pr = con.execute("""
            SELECT COALESCE(product_name, product_id) AS k, SUM(commission) AS c
            FROM affiliate_performance GROUP BY product_name, product_id
        """).fetchall()
        profit_map = {str(r[0]).lower(): float(r[1] or 0) for r in pr}

    con.close()

    worklist: list[dict] = []
    seen: set[str] = set()

    for name, sold, price, likes, discount, opp_s, vscore in rows:
        if not name or str(name) in seen:
            continue
        seen.add(str(name))

        profit_comm = profit_map.get(str(name).lower(), 0.0)
        priority_score = float(opp_s or 0) * 0.5 + float(vscore or 0) * 0.3 + profit_comm * 0.2

        if priority_score > 5000:
            priority = "P1 — URGENT"
        elif priority_score > 2000:
            priority = "P2 — HIGH"
        elif priority_score > 500:
            priority = "P3 — MEDIUM"
        else:
            priority = "P4 — LOW"

        # Hook
        if float(discount or 0) >= 30:
            hook = f"ลดไป {float(discount):.0f}% อย่าพลาด!"
        elif float(likes or 0) > 3000:
            hook = f"ทำไมถึงมี {int(float(likes)):,} likes?"
        elif float(sold or 0) > 2000:
            hook = f"ขายไปแล้ว {int(float(sold)):,} ชิ้น"
        else:
            hook = "รีวิวสินค้านี้ก่อนใคร"

        # Format & Platform
        p = float(price or 0)
        if p <= 300 and float(likes or 0) > 1000:
            fmt, platform = "TikTok 15s",     "TikTok + Instagram"
        elif p <= 600:
            fmt, platform = "Reels 30s",       "TikTok + Instagram"
        elif p >= 3000:
            fmt, platform = "YouTube Review",  "YouTube + Facebook"
        else:
            fmt, platform = "TikTok 30s",      "TikTok + Facebook"

        worklist.append({
            "name":      str(name)[:35],
            "priority":  priority,
            "hook":      hook,
            "format":    fmt,
            "platform":  platform,
            "opp_score": float(opp_s or 0),
        })
        if len(worklist) >= top:
            break

    return worklist


# ---------------------------------------------------------------------------
# executive_summary
# ---------------------------------------------------------------------------

def executive_summary(table_name: str = "products") -> dict:
    """
    Full executive summary: Opportunities, Risks, Market Gaps,
    Viral Candidates, Profit Candidates.
    """
    con = _connect()
    cols, col_map = _schema(con, table_name)
    lower_map = {c.lower(): c for c in cols}

    name_col  = col_map.get("product_name") or (cols[1] if len(cols) > 1 else None)
    sold_col  = col_map.get("sales")
    price_col = col_map.get("price")
    cat3_col  = _col(lower_map, "global_category3") or _col(lower_map, "global_category1") or col_map.get("category")
    cat1_col  = _col(lower_map, "global_category1") or col_map.get("category")

    name_expr  = _q(name_col)  if name_col  else "NULL"
    sold_expr  = _safe(sold_col)  if sold_col  else "0"
    price_expr = _safe(price_col) if price_col else "0"

    opp   = _opp_expr(lower_map)
    viral = _viral_expr(lower_map)

    # Opportunities
    opportunities = con.execute(f"""
        SELECT {name_expr} AS name, {sold_expr} AS sold, {price_expr} AS price, {opp} AS score
        FROM {_q(table_name)} ORDER BY score DESC LIMIT 10
    """).fetchall()

    # Market gaps: niches with few products but high avg sales
    market_gaps: list = []
    niche_col = cat3_col or cat1_col
    if niche_col and sold_col:
        market_gaps = con.execute(f"""
            SELECT {_q(niche_col)} AS cat, COUNT(*) AS cnt,
                   ROUND(AVG({_safe(sold_col)}), 0) AS avg_sold
            FROM {_q(table_name)}
            WHERE {_q(niche_col)} IS NOT NULL
            GROUP BY {_q(niche_col)}
            HAVING COUNT(*) BETWEEN 10 AND 500
            ORDER BY avg_sold DESC LIMIT 10
        """).fetchall()

    # Viral candidates
    viral_candidates = con.execute(f"""
        SELECT {name_expr} AS name, {price_expr} AS price, {viral} AS vscore
        FROM {_q(table_name)}
        WHERE {sold_expr} >= 50
        ORDER BY vscore DESC LIMIT 10
    """).fetchall()

    # Risks: high price + low sales
    risks: list = []
    if price_col and sold_col:
        risks = con.execute(f"""
            SELECT {name_expr} AS name, {price_expr} AS price, {sold_expr} AS sold
            FROM {_q(table_name)}
            WHERE {price_expr} >= 5000 AND {sold_expr} < 50
            ORDER BY price DESC LIMIT 5
        """).fetchall()

    # Profit candidates from affiliate data
    profit_candidates: list = []
    if _has_table(con, "affiliate_performance"):
        profit_candidates = con.execute("""
            SELECT COALESCE(product_name, product_id, 'Unknown') AS name,
                   SUM(commission) AS comm,
                   CASE WHEN SUM(clicks)>0 THEN ROUND(SUM(commission)/SUM(clicks),4) ELSE 0 END AS epc
            FROM affiliate_performance
            GROUP BY product_name, product_id
            ORDER BY comm DESC LIMIT 10
        """).fetchall()

    total = con.execute(f"SELECT COUNT(*) FROM {_q(table_name)}").fetchone()[0]
    total_comm = 0.0
    if _has_table(con, "affiliate_performance"):
        total_comm = float(con.execute("SELECT COALESCE(SUM(commission),0) FROM affiliate_performance").fetchone()[0])

    con.close()
    return {
        "opportunities":     opportunities,
        "risks":             risks,
        "market_gaps":       market_gaps,
        "viral_candidates":  viral_candidates,
        "profit_candidates": profit_candidates,
        "total_products":    total,
        "total_commission":  total_comm,
        "generated_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ---------------------------------------------------------------------------
# daily_report
# ---------------------------------------------------------------------------

def daily_report(
    fmt: str = "markdown",
    table_name: str = "products",
    output_dir: str = "exports/reports",
) -> Path:
    """Export daily report as markdown / html / csv."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    data = executive_summary(table_name=table_name)

    if fmt == "markdown":
        return _to_markdown(data, out_dir, date_str)
    if fmt == "html":
        return _to_html(data, out_dir, date_str)
    if fmt == "csv":
        return _to_csv(data, out_dir, date_str)
    raise ValueError(f"Unknown format '{fmt}'. Use: markdown | html | csv")


def _to_markdown(data: dict, out_dir: Path, date_str: str) -> Path:
    path = out_dir / f"daily_report_{date_str}.md"
    lines: list[str] = [
        f"# Daily Affiliate Report — {date_str}",
        f"> Generated: {data['generated_at']}  |  "
        f"Products: {data['total_products']:,}  |  "
        f"Commission: ฿{data['total_commission']:,.2f}",
        "",
        "---",
        "## Top Opportunities",
        "",
        "| # | Product | Sold | Price (฿) | Score |",
        "|---|---------|------|----------|-------|",
    ]
    for i, (name, sold, price, score) in enumerate(data["opportunities"], 1):
        lines.append(f"| {i} | {name} | {int(sold):,} | {price:,.0f} | {score:,.0f} |")

    lines += ["", "---", "## Market Gaps", "",
              "| # | Category | Products | Avg Sold |",
              "|---|----------|----------|----------|"]
    for i, (cat, cnt, avg) in enumerate(data["market_gaps"], 1):
        lines.append(f"| {i} | {cat} | {cnt:,} | {int(avg):,} |")

    lines += ["", "---", "## Viral Candidates", "",
              "| # | Product | Price (฿) | Viral Score |",
              "|---|---------|----------|-------------|"]
    for i, (name, price, vscore) in enumerate(data["viral_candidates"], 1):
        lines.append(f"| {i} | {name} | {price:,.0f} | {vscore:,.0f} |")

    if data["profit_candidates"]:
        lines += ["", "---", "## Profit Candidates", "",
                  "| # | Product | Commission (฿) | EPC |",
                  "|---|---------|---------------|-----|"]
        for i, (name, comm, epc) in enumerate(data["profit_candidates"], 1):
            lines.append(f"| {i} | {name} | {comm:,.2f} | {epc:.4f} |")

    if data["risks"]:
        lines += ["", "---", "## Risks (High Price / Low Sales)", "",
                  "| # | Product | Price (฿) | Sold |",
                  "|---|---------|----------|------|"]
        for i, (name, price, sold) in enumerate(data["risks"], 1):
            lines.append(f"| {i} | {name} | {price:,.0f} | {int(sold):,} |")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _to_html(data: dict, out_dir: Path, date_str: str) -> Path:
    path = out_dir / f"daily_report_{date_str}.html"

    def tbl(headers: list[str], rows: list[tuple]) -> str:
        th = "".join(f"<th>{h}</th>" for h in headers)
        body = ""
        for i, row in enumerate(rows, 1):
            cells = "".join(f"<td>{v}</td>" for v in row)
            body += f"<tr><td>{i}</td>{cells}</tr>"
        return f"<table><thead><tr><th>#</th>{th}</tr></thead><tbody>{body}</tbody></table>"

    opp_tbl = tbl(
        ["Product", "Sold", "Price (฿)", "Score"],
        [(n, f"{int(s):,}", f"{p:,.0f}", f"{sc:,.0f}") for n, s, p, sc in data["opportunities"]],
    )
    gap_tbl = tbl(
        ["Category", "Products", "Avg Sold"],
        [(c, f"{cnt:,}", f"{int(a):,}") for c, cnt, a in data["market_gaps"]],
    )
    viral_tbl = tbl(
        ["Product", "Price (฿)", "Viral Score"],
        [(n, f"{p:,.0f}", f"{v:,.0f}") for n, p, v in data["viral_candidates"]],
    )
    profit_tbl = ""
    if data["profit_candidates"]:
        profit_tbl = (
            "<h2>Profit Candidates</h2>"
            + tbl(["Product", "Commission (฿)", "EPC"],
                  [(n, f"{c:,.2f}", f"{e:.4f}") for n, c, e in data["profit_candidates"]])
        )

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<title>Daily Affiliate Report {date_str}</title>
<style>
  body{{font-family:sans-serif;max-width:1100px;margin:auto;padding:20px;background:#f9f9f9}}
  h1{{color:#2c3e50}}h2{{color:#27ae60;border-bottom:2px solid #27ae60;padding-bottom:4px}}
  table{{border-collapse:collapse;width:100%;margin-bottom:24px;background:white}}
  th{{background:#2c3e50;color:white;padding:8px 12px;text-align:left}}
  td{{padding:7px 12px;border-bottom:1px solid #eee}}
  tr:hover{{background:#f0f4f8}}
  .meta{{color:#666;font-size:.9em;margin-bottom:20px}}
</style>
</head>
<body>
<h1>Daily Affiliate Report — {date_str}</h1>
<p class="meta">Generated: {data['generated_at']} &nbsp;|&nbsp;
  Products: {data['total_products']:,} &nbsp;|&nbsp;
  Commission: ฿{data['total_commission']:,.2f}</p>
<h2>Top Opportunities</h2>{opp_tbl}
<h2>Market Gaps</h2>{gap_tbl}
<h2>Viral Candidates</h2>{viral_tbl}
{profit_tbl}
</body></html>"""

    path.write_text(html, encoding="utf-8")
    return path


def _to_csv(data: dict, out_dir: Path, date_str: str) -> Path:
    path = out_dir / f"daily_report_{date_str}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv_mod.writer(f)
        w.writerow(["section", "rank", "name", "metric_a", "val_a", "metric_b", "val_b", "score"])
        for i, (name, sold, price, score) in enumerate(data["opportunities"], 1):
            w.writerow(["opportunity", i, name, "sold", int(sold), "price", f"{price:.0f}", f"{score:.0f}"])
        for i, (cat, cnt, avg) in enumerate(data["market_gaps"], 1):
            w.writerow(["market_gap", i, cat, "products", cnt, "avg_sold", int(avg), ""])
        for i, (name, price, vscore) in enumerate(data["viral_candidates"], 1):
            w.writerow(["viral", i, name, "price", f"{price:.0f}", "", "", f"{vscore:.0f}"])
        for i, (name, comm, epc) in enumerate(data["profit_candidates"], 1):
            w.writerow(["profit", i, name, "commission", f"{comm:.2f}", "epc", f"{epc:.4f}", ""])
    return path


# ---------------------------------------------------------------------------
# Rich print helpers
# ---------------------------------------------------------------------------

def print_morning_brief(data: dict) -> None:
    console.print(Rule(f"[bold green]Morning Brief — {data['generated_at']}[/]"))

    t = Table(title="Top Opportunities", header_style="bold green", expand=True)
    t.add_column("#", width=3, justify="right")
    t.add_column("Product", min_width=22, max_width=35)
    t.add_column("Sold", justify="right", min_width=7)
    t.add_column("Price", justify="right", min_width=8)
    t.add_column("Score", justify="right", style="bold yellow", min_width=8)
    for i, (name, sold, price, score) in enumerate(data["top_opportunities"], 1):
        t.add_row(str(i), str(name)[:35], f"{int(sold):,}", f"฿{price:,.0f}", f"{score:,.0f}")
    console.print(t)

    t2 = Table(title="Top Viral", header_style="bold magenta", expand=True)
    t2.add_column("#", width=3, justify="right")
    t2.add_column("Product", min_width=22, max_width=35)
    t2.add_column("Price", justify="right", min_width=8)
    t2.add_column("Viral Score", justify="right", style="bold magenta", min_width=11)
    for i, (name, price, vscore) in enumerate(data["top_viral"], 1):
        t2.add_row(str(i), str(name)[:35], f"฿{price:,.0f}", f"{vscore:,.0f}")
    console.print(t2)

    if data["top_niches"]:
        t3 = Table(title="Top Niches (Market Gaps)", header_style="bold cyan", expand=True)
        t3.add_column("#", width=3, justify="right")
        t3.add_column("Category", min_width=22, max_width=35)
        t3.add_column("Products", justify="right", min_width=9)
        t3.add_column("Avg Sold", justify="right", style="cyan", min_width=9)
        for i, (cat, cnt, avg_sold) in enumerate(data["top_niches"], 1):
            t3.add_row(str(i), str(cat)[:35], f"{cnt:,}", f"{int(avg_sold):,}")
        console.print(t3)

    if data["top_profit"]:
        t4 = Table(title="Top Profit (Affiliate)", header_style="bold yellow", expand=True)
        t4.add_column("#", width=3, justify="right")
        t4.add_column("Product", min_width=22, max_width=35)
        t4.add_column("Commission", justify="right", style="green", min_width=11)
        t4.add_column("EPC", justify="right", min_width=7)
        t4.add_column("Conv.%", justify="right", min_width=7)
        for i, (name, comm, epc, conv) in enumerate(data["top_profit"], 1):
            t4.add_row(str(i), str(name)[:35], f"฿{comm:,.2f}", f"{epc:.4f}", f"{conv:.2f}%")
        console.print(t4)


def print_category_brief(data: dict) -> None:
    cat = data["category"]
    console.print(Rule(f"[bold cyan]Category Brief — {cat}[/]"))

    t = Table(show_header=True, header_style="bold cyan", expand=True)
    t.add_column("#", width=3, justify="right")
    t.add_column("Product", min_width=20, max_width=26)
    t.add_column("Sold", justify="right", min_width=7)
    t.add_column("Price", justify="right", min_width=8)
    t.add_column("Opp", justify="right", style="yellow", min_width=7)
    t.add_column("Profit", justify="right", style="green", min_width=7)
    t.add_column("Content Angle", min_width=22)

    for i, (name, sold, price, opp, profit, angle) in enumerate(data["products"], 1):
        t.add_row(
            str(i), str(name)[:26],
            f"{int(sold):,}", f"฿{price:,.0f}",
            f"{opp:,.0f}",
            f"[green]{profit:.1f}[/]" if profit > 0 else "[dim]—[/]",
            angle,
        )
    console.print(t)
    console.print(f"[dim]{data['total']} products in '{cat}'[/]")


def print_trend_watch(data: dict) -> None:
    console.print(Rule("[bold yellow]Trend Watch[/]"))

    if data["social_momentum"]:
        t = Table(title="Social Momentum (likes ÷ sold)", header_style="bold yellow", expand=True)
        t.add_column("#", width=3, justify="right")
        t.add_column("Product", min_width=22, max_width=30)
        t.add_column("Likes", justify="right", style="yellow", min_width=7)
        t.add_column("Sold", justify="right", min_width=7)
        t.add_column("Price", justify="right", min_width=8)
        t.add_column("Ratio", justify="right", style="bold yellow", min_width=6)
        for i, (name, likes, sold, price, ratio) in enumerate(data["social_momentum"], 1):
            t.add_row(str(i), str(name)[:30], f"{int(likes):,}", f"{int(sold):,}",
                      f"฿{price:,.0f}", f"{ratio:.2f}x")
        console.print(t)
    else:
        console.print("[dim]No social momentum data found.[/]")

    if data["promo_surge"]:
        t2 = Table(title="Promo Surge (≥25% off, ≥500 sold)", header_style="bold red", expand=True)
        t2.add_column("#", width=3, justify="right")
        t2.add_column("Product", min_width=22, max_width=30)
        t2.add_column("Discount", justify="right", style="red", min_width=9)
        t2.add_column("Sold", justify="right", min_width=7)
        t2.add_column("Price", justify="right", min_width=8)
        for i, (name, disc, sold, price) in enumerate(data["promo_surge"], 1):
            t2.add_row(str(i), str(name)[:30], f"{disc:.1f}%", f"{int(sold):,}", f"฿{price:,.0f}")
        console.print(t2)
    else:
        console.print("[dim]No promo surge data found.[/]")

    if data["new_viral"]:
        t3 = Table(title="New Viral Potential (≥1000 likes, <500 sold)", header_style="bold magenta", expand=True)
        t3.add_column("#", width=3, justify="right")
        t3.add_column("Product", min_width=22, max_width=30)
        t3.add_column("Likes", justify="right", style="magenta", min_width=7)
        t3.add_column("Sold", justify="right", min_width=7)
        t3.add_column("Price", justify="right", min_width=8)
        for i, (name, likes, sold, price) in enumerate(data["new_viral"], 1):
            t3.add_row(str(i), str(name)[:30], f"{int(likes):,}", f"{int(sold):,}", f"฿{price:,.0f}")
        console.print(t3)
    else:
        console.print("[dim]No new viral potential data found.[/]")


def print_content_worklist(worklist: list[dict]) -> None:
    console.print(Rule("[bold green]Content Worklist[/]"))
    if not worklist:
        console.print("[yellow]No data.[/]")
        return

    STYLES = {
        "P1 — URGENT": "bold red",
        "P2 — HIGH":   "bold yellow",
        "P3 — MEDIUM": "cyan",
        "P4 — LOW":    "dim",
    }

    t = Table(show_header=True, header_style="bold green", expand=True)
    t.add_column("#", width=3, justify="right")
    t.add_column("Priority", min_width=12)
    t.add_column("Product", min_width=18, max_width=24)
    t.add_column("Suggested Hook", min_width=24, max_width=35)
    t.add_column("Format", min_width=14)
    t.add_column("Platform", min_width=18)

    for i, item in enumerate(worklist, 1):
        style = STYLES.get(item["priority"], "")
        t.add_row(
            str(i),
            f"[{style}]{item['priority']}[/]",
            item["name"][:24],
            item["hook"][:35],
            item["format"],
            item["platform"],
        )
    console.print(t)


def print_executive_summary(data: dict) -> None:
    console.print(Panel(
        f"[bold white]Products:[/] [cyan]{data['total_products']:,}[/]   "
        f"[bold white]Commission:[/] [green]฿{data['total_commission']:,.2f}[/]   "
        f"[bold white]Generated:[/] {data['generated_at']}",
        title="[bold green]Executive Summary[/]", expand=False,
    ))

    def show(title: str, color: str, rows: list, headers: list, fmt_fn):
        t = Table(title=f"[bold {color}]{title}[/]", header_style=f"bold {color}", expand=True)
        t.add_column("#", width=3, justify="right")
        for h in headers:
            t.add_column(h, min_width=10)
        for i, row in enumerate(rows, 1):
            t.add_row(str(i), *fmt_fn(row))
        console.print(t)

    show("Opportunities", "green", data["opportunities"],
         ["Product", "Sold", "Price", "Score"],
         lambda r: (str(r[0])[:28], f"{int(r[1]):,}", f"฿{r[2]:,.0f}", f"{r[3]:,.0f}"))

    show("Market Gaps", "cyan", data["market_gaps"],
         ["Category", "Products", "Avg Sold"],
         lambda r: (str(r[0])[:28], f"{r[1]:,}", f"{int(r[2]):,}"))

    show("Viral Candidates", "magenta", data["viral_candidates"],
         ["Product", "Price", "Viral Score"],
         lambda r: (str(r[0])[:28], f"฿{r[1]:,.0f}", f"{r[2]:,.0f}"))

    if data["profit_candidates"]:
        show("Profit Candidates", "yellow", data["profit_candidates"],
             ["Product", "Commission", "EPC"],
             lambda r: (str(r[0])[:28], f"฿{r[1]:,.2f}", f"{r[2]:.4f}"))

    if data["risks"]:
        show("Risks (High Price / Low Sales)", "red", data["risks"],
             ["Product", "Price", "Sold"],
             lambda r: (str(r[0])[:28], f"฿{r[1]:,.0f}", f"{int(r[2]):,}"))
