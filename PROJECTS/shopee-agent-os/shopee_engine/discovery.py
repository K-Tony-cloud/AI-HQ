"""Product Discovery Engine — winning products for affiliate/content creation."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import config, build_column_map

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Daily-picks category → global_category1 patterns
# ─────────────────────────────────────────────────────────────────────────────

DAILY_PICKS_CATEGORIES: dict[str, list[str]] = {
    "Gadget":             ["mobile & gadget", "computers & accessories", "cameras & drones",
                           "gaming & consoles", "home appliances", "audio"],
    "Home":               ["home & living"],
    "Viral TikTok":       [],   # special logic — handled separately
    "Mobile Accessories": ["mobile & gadget"],
    "Mother & Baby":      ["mom & baby", "baby & kids"],
    "Health":             ["health"],
    "Camping":            ["sports & outdoors"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")
    return duckdb.connect(str(config.db_path), read_only=read_only)


def _get_schema(con: duckdb.DuckDBPyConnection, table: str) -> tuple[list[str], dict[str, str]]:
    cols = [
        r[0] for r in con.execute(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table}'"
        ).fetchall()
    ]
    return cols, build_column_map(cols)


def _q(name: str) -> str:
    """Double-quote a column name — handles spaces and reserved keywords like 'like'."""
    return f'"{name}"'


def _col(lower_map: dict[str, str], *candidates: str) -> str | None:
    """Return first actual column whose name (lower) matches any candidate."""
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _safe(col: str, default: float = 0.0) -> str:
    return f"COALESCE(TRY_CAST({_q(col)} AS DOUBLE), {default})"


def _opportunity_score_expr(lower_map: dict[str, str]) -> str:
    """
    opportunity_score =
      item_sold          * 0.40
      + like             * 0.15
      + discount_pct     * 0.15
      + shop_rating*100  * 0.15
      + item_rating*100  * 0.15  (falls back to shop_rating if item_rating absent)
    """
    sold   = _col(lower_map, "item_sold", "sales", "sold") or "item_sold"
    likes  = _col(lower_map, "like", "likes") or "like"
    disc   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"
    shop_r = _col(lower_map, "shop_rating", "seller_rating") or "shop_rating"
    item_r = _col(lower_map, "item_rating", "rating_star", "rating") or shop_r

    return (
        f"ROUND("
        f"{_safe(sold)} * 0.40 + "
        f"{_safe(likes)} * 0.15 + "
        f"{_safe(disc)} * 0.15 + "
        f"{_safe(shop_r)} * 100.0 * 0.15 + "
        f"{_safe(item_r)} * 100.0 * 0.15"
        f", 2)"
    )


def _base_select(lower_map: dict[str, str], score_expr: str) -> str:
    """Standard SELECT clause for discovery queries — returns fixed aliased columns."""
    title   = _col(lower_map, "title", "product_name", "name") or "title"
    price   = _col(lower_map, "sale_price", "price") or "sale_price"
    sold    = _col(lower_map, "item_sold", "sales") or "item_sold"
    likes   = _col(lower_map, "like", "likes") or "like"
    shop_r  = _col(lower_map, "shop_rating") or "shop_rating"
    disc    = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"
    cat     = _col(lower_map, "global_category3", "global_category2",
                   "global_category1", "category") or "global_category3"
    brand   = _col(lower_map, "global_brand", "brand") or "global_brand"
    # "product_short link" has a space — must be quoted; fallback to product_link
    short   = _col(lower_map, "product_short link", "affiliate_link", "product_link") or "product_link"

    return ", ".join([
        f'{_q(title)} AS title',
        f'{_safe(price)} AS sale_price',
        f'{_safe(sold)} AS item_sold',
        f'{_safe(likes)} AS likes',
        f'{_safe(shop_r)} AS shop_rating',
        f'{_safe(disc)} AS discount_pct',
        f'COALESCE({_q(cat)}, \'\') AS category',
        f'COALESCE({_q(brand)}, \'NoBrand\') AS brand',
        f'COALESCE({_q(short)}, \'\') AS product_short_link',
        f'{score_expr} AS opportunity_score',
    ])


def _cat1_filter(lower_map: dict[str, str], patterns: list[str]) -> str:
    """Filter on global_category1 using ILIKE patterns."""
    cat1 = _col(lower_map, "global_category1")
    if not cat1 or not patterns:
        return "1=1"
    parts = [f"LOWER({_q(cat1)}) LIKE '%{p.lower()}%'" for p in patterns]
    return "(" + " OR ".join(parts) + ")"


def _any_cat_filter(lower_map: dict[str, str], keyword: str) -> str:
    """Search keyword across all three category levels."""
    cat_cols = [c for k in ("global_category1", "global_category2", "global_category3")
                if (c := _col(lower_map, k))]
    if not cat_cols:
        return "1=1"
    kw = keyword.replace("'", "''").lower()
    parts = [f"LOWER({_q(c)}) LIKE '%{kw}%'" for c in cat_cols]
    return "(" + " OR ".join(parts) + ")"


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fp(v) -> str:   # price
    try: return f"฿{float(v):,.0f}"
    except: return "—"

def _fi(v) -> str:   # integer
    try: return f"{int(float(v)):,}"
    except: return "—"

def _fr(v) -> str:   # rating
    try: return f"★{float(v):.2f}"
    except: return "—"

def _fd(v) -> str:   # discount
    try: return f"{float(v):.0f}%"
    except: return "—"

def _fs(v) -> str:   # score
    try: return f"{float(v):,.1f}"
    except: return "—"

def _ft(v, n=43) -> str:   # title truncate
    s = str(v) if v is not None else "—"
    return (s[:n] + "…") if len(s) > n else s

def _fl(v, n=32) -> str:   # link truncate
    s = str(v) if v is not None else "—"
    return (s[:n] + "…") if len(s) > n else s

def _fc(v, n=22) -> str:   # category truncate
    s = str(v) if v is not None else "—"
    return (s[:n] + "…") if len(s) > n else s

def _fb(v, n=16) -> str:   # brand truncate
    s = str(v) if v is not None else "—"
    return (s[:n] + "…") if len(s) > n else s


# Column spec: (header, df_col, style, max_width, fmt_fn)
_DISC_COLS = [
    ("Title",      "title",              "bold white",  45, _ft),
    ("Price",      "sale_price",         "green",       10, _fp),
    ("Sold",       "item_sold",          "yellow",       9, _fi),
    ("Likes",      "likes",              "cyan",         9, _fi),
    ("Shop★",      "shop_rating",        "magenta",      7, _fr),
    ("Disc%",      "discount_pct",       "red",          6, _fd),
    ("Category",   "category",           "blue",        24, _fc),
    ("Brand",      "brand",              "dim",         17, _fb),
    ("Score",      "opportunity_score",  "bold green",  10, _fs),
    ("Short Link", "product_short_link", "dim",         34, _fl),
]


def _print_table(df: pd.DataFrame, title: str, cols=None) -> None:
    if df.empty:
        console.print(f"[yellow]No results — {title}[/]")
        return
    cols = cols or _DISC_COLS
    tbl = Table(title=title, show_lines=True, expand=True)
    tbl.add_column("#", style="bold dim", width=4, justify="right")
    for header, _, style, max_w, _ in cols:
        tbl.add_column(header, style=style, max_width=max_w)
    for rank, (_, row) in enumerate(df.iterrows(), 1):
        cells = [str(rank)]
        for _, col, _, _, fmt in cols:
            v = row.get(col)
            cells.append("—" if (v is None or (isinstance(v, float) and pd.isna(v))) else fmt(v))
        tbl.add_row(*cells)
    console.print(tbl)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def find_winning_products(
    keyword:         str | None = None,
    category:        str | None = None,
    min_sold:        int | None = None,
    min_rating:      float | None = None,
    min_shop_rating: float | None = None,
    price_min:       float | None = None,
    price_max:       float | None = None,
    min_discount:    float | None = None,
    top:             int = 30,
    table_name:      str | None = None,
) -> pd.DataFrame:
    """Find products with high affiliate/content potential using multi-filter + opportunity_score."""
    table_name = table_name or config.default_table
    con = _connect()
    try:
        cols, _ = _get_schema(con, table_name)
        lower_map = {c.lower(): c for c in cols}
        score_expr = _opportunity_score_expr(lower_map)
        select = _base_select(lower_map, score_expr)

        title_col  = _col(lower_map, "title", "product_name") or "title"
        price_col  = _col(lower_map, "sale_price", "price") or "sale_price"
        sold_col   = _col(lower_map, "item_sold", "sales") or "item_sold"
        shop_r_col = _col(lower_map, "shop_rating") or "shop_rating"
        item_r_col = _col(lower_map, "item_rating", "rating") or shop_r_col
        disc_col   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"

        conds = ["1=1"]
        if keyword:
            kw = keyword.replace("'", "''").lower()
            conds.append(f"LOWER({_q(title_col)}) LIKE '%{kw}%'")
        if category:
            conds.append(_any_cat_filter(lower_map, category))
        if min_sold is not None:
            conds.append(f"{_safe(sold_col)} >= {min_sold}")
        if min_rating is not None:
            conds.append(f"{_safe(item_r_col)} >= {min_rating}")
        if min_shop_rating is not None:
            conds.append(f"{_safe(shop_r_col)} >= {min_shop_rating}")
        if price_min is not None:
            conds.append(f"{_safe(price_col)} >= {price_min}")
        if price_max is not None:
            conds.append(f"{_safe(price_col)} <= {price_max}")
        if min_discount is not None:
            conds.append(f"{_safe(disc_col)} >= {min_discount}")

        sql = (
            f"SELECT {select} FROM {table_name} "
            f"WHERE {' AND '.join(conds)} "
            f"ORDER BY opportunity_score DESC LIMIT {top}"
        )
        df = con.execute(sql).df()
    finally:
        con.close()
    return df


def print_winning_products(df: pd.DataFrame, filters_desc: str = "") -> None:
    title = f"[bold green]Winning Products[/]"
    if filters_desc:
        title += f"  [dim]({filters_desc})[/]"
    title += f"  [dim]— {len(df)} results[/]"
    _print_table(df, title)


# ─────────────────────────────────────────────────────────────────────────────

def top_opportunities(
    top:        int = 30,
    category:   str | None = None,
    table_name: str | None = None,
) -> pd.DataFrame:
    """Top N products by opportunity_score across the full dataset."""
    table_name = table_name or config.default_table
    con = _connect()
    try:
        cols, _ = _get_schema(con, table_name)
        lower_map = {c.lower(): c for c in cols}
        score_expr = _opportunity_score_expr(lower_map)
        select = _base_select(lower_map, score_expr)

        conds = ["1=1"]
        if category:
            conds.append(_any_cat_filter(lower_map, category))

        sql = (
            f"SELECT {select} FROM {table_name} "
            f"WHERE {' AND '.join(conds)} "
            f"ORDER BY opportunity_score DESC LIMIT {top}"
        )
        df = con.execute(sql).df()
    finally:
        con.close()
    return df


def print_top_opportunities(df: pd.DataFrame, top: int) -> None:
    _print_table(df, f"[bold yellow]Top {top} Opportunities[/]  [dim](ranked by opportunity_score)[/]")


# ─────────────────────────────────────────────────────────────────────────────

def top_viral(
    top:        int = 30,
    price_max:  float = 500,
    category:   str | None = None,
    table_name: str | None = None,
) -> pd.DataFrame:
    """
    Products best suited for TikTok/Reels content:
    low price, high sales, high likes, high discount.
    viral_score = item_sold*0.35 + likes*0.35 + discount*100*0.30
    """
    table_name = table_name or config.default_table
    con = _connect()
    try:
        cols, _ = _get_schema(con, table_name)
        lower_map = {c.lower(): c for c in cols}

        title_col  = _col(lower_map, "title", "product_name") or "title"
        price_col  = _col(lower_map, "sale_price", "price") or "sale_price"
        sold_col   = _col(lower_map, "item_sold", "sales") or "item_sold"
        likes_col  = _col(lower_map, "like", "likes") or "like"
        disc_col   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"
        shop_r_col = _col(lower_map, "shop_rating") or "shop_rating"
        cat_col    = _col(lower_map, "global_category3", "global_category2",
                          "global_category1") or "global_category3"
        brand_col  = _col(lower_map, "global_brand", "brand") or "global_brand"
        short_col  = _col(lower_map, "product_short link", "affiliate_link",
                          "product_link") or "product_link"

        viral_score = (
            f"ROUND("
            f"{_safe(sold_col)} * 0.35 + "
            f"{_safe(likes_col)} * 0.35 + "
            f"{_safe(disc_col)} * 100.0 * 0.30"
            f", 2)"
        )

        conds = [
            f"{_safe(price_col)} > 0",
            f"{_safe(price_col)} <= {price_max}",
            f"{_safe(sold_col)} >= 50",
        ]
        if category:
            conds.append(_any_cat_filter(lower_map, category))

        sql = f"""
            SELECT
                {_q(title_col)} AS title,
                {_safe(price_col)} AS sale_price,
                {_safe(sold_col)} AS item_sold,
                {_safe(likes_col)} AS likes,
                {_safe(shop_r_col)} AS shop_rating,
                {_safe(disc_col)} AS discount_pct,
                COALESCE({_q(cat_col)}, '') AS category,
                COALESCE({_q(brand_col)}, 'NoBrand') AS brand,
                COALESCE({_q(short_col)}, '') AS product_short_link,
                {viral_score} AS viral_score
            FROM {table_name}
            WHERE {' AND '.join(conds)}
            ORDER BY viral_score DESC
            LIMIT {top}
        """
        df = con.execute(sql).df()
    finally:
        con.close()
    return df


def print_top_viral(df: pd.DataFrame, top: int, price_max: float) -> None:
    viral_cols = [
        ("Title",      "title",          "bold white",  45, _ft),
        ("Price",      "sale_price",     "green",       10, _fp),
        ("Sold",       "item_sold",      "yellow",       9, _fi),
        ("Likes",      "likes",          "cyan",         9, _fi),
        ("Shop★",      "shop_rating",    "magenta",      7, _fr),
        ("Disc%",      "discount_pct",   "red",          6, _fd),
        ("Category",   "category",       "blue",        24, _fc),
        ("Brand",      "brand",          "dim",         17, _fb),
        ("Viral Score","viral_score",    "bold yellow", 12, _fs),
        ("Short Link", "product_short_link","dim",      34, _fl),
    ]
    _print_table(
        df,
        f"[bold yellow]Top {top} Viral Products[/]  "
        f"[dim](price ≤ ฿{price_max:,.0f}, sold ≥ 50)[/]",
        cols=viral_cols,
    )


# ─────────────────────────────────────────────────────────────────────────────

def top_niche(
    top:          int = 20,
    min_products: int = 20,
    max_products: int = 3000,
    table_name:   str | None = None,
) -> pd.DataFrame:
    """
    Niche categories: high avg_sales but low product count → market gap signal.
    Groups by global_category3, filters by product count range.
    """
    table_name = table_name or config.default_table
    con = _connect()
    try:
        cols, _ = _get_schema(con, table_name)
        lower_map = {c.lower(): c for c in cols}

        cat3   = _col(lower_map, "global_category3", "global_category2") or "global_category3"
        cat1   = _col(lower_map, "global_category1") or "global_category1"
        sold   = _col(lower_map, "item_sold", "sales") or "item_sold"
        price  = _col(lower_map, "sale_price", "price") or "sale_price"
        shop_r = _col(lower_map, "shop_rating") or "shop_rating"
        disc   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"

        sql = f"""
            SELECT
                {_q(cat3)}                               AS sub_category,
                {_q(cat1)}                               AS main_category,
                COUNT(*)                                 AS product_count,
                ROUND(AVG({_safe(sold)}), 1)             AS avg_sales,
                SUM({_safe(sold)})                        AS total_sales,
                ROUND(AVG({_safe(price)}), 0)            AS avg_price,
                ROUND(AVG({_safe(shop_r)}), 2)           AS avg_shop_rating,
                ROUND(AVG({_safe(disc)}), 1)             AS avg_discount,
                ROUND(AVG({_safe(sold)}) / NULLIF(COUNT(*), 0) * 100, 2) AS efficiency_score
            FROM {table_name}
            WHERE {_q(cat3)} IS NOT NULL AND TRIM({_q(cat3)}) != ''
            GROUP BY {_q(cat3)}, {_q(cat1)}
            HAVING COUNT(*) BETWEEN {min_products} AND {max_products}
            ORDER BY avg_sales DESC
            LIMIT {top}
        """
        df = con.execute(sql).df()
    finally:
        con.close()
    return df


def print_top_niche(df: pd.DataFrame, top: int) -> None:
    if df.empty:
        console.print("[yellow]No niche data found.[/]")
        return
    niche_cols = [
        ("Sub-Category",  "sub_category",    "bold cyan",   26, _fc),
        ("Main Category", "main_category",   "blue",        22, _fc),
        ("# Products",    "product_count",   "white",        9, _fi),
        ("Avg Sales",     "avg_sales",       "yellow",      10, _fi),
        ("Total Sales",   "total_sales",     "dim yellow",  12, _fi),
        ("Avg Price",     "avg_price",       "green",       10, _fp),
        ("Shop★",         "avg_shop_rating", "magenta",      7, _fr),
        ("Avg Disc%",     "avg_discount",    "red",          8, _fd),
    ]
    tbl = Table(
        title=f"[bold green]Top {top} Niche Categories[/]  "
              f"[dim](high avg_sales, low product count → market gap)[/]",
        show_lines=True,
        expand=True,
    )
    tbl.add_column("#", style="bold dim", width=4, justify="right")
    for header, _, style, max_w, _ in niche_cols:
        tbl.add_column(header, style=style, max_width=max_w)
    for rank, (_, row) in enumerate(df.iterrows(), 1):
        cells = [str(rank)]
        for _, col, _, _, fmt in niche_cols:
            v = row.get(col)
            cells.append("—" if (v is None or (isinstance(v, float) and pd.isna(v))) else fmt(v))
        tbl.add_row(*cells)
    console.print(tbl)


# ─────────────────────────────────────────────────────────────────────────────

def daily_picks(
    top:        int = 10,
    table_name: str | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Select top products per content category using opportunity_score.
    Special handling for 'Viral TikTok' bucket (low price + high discount + likes).
    """
    table_name = table_name or config.default_table
    con = _connect()
    results: dict[str, pd.DataFrame] = {}
    try:
        cols, _ = _get_schema(con, table_name)
        lower_map = {c.lower(): c for c in cols}
        score_expr = _opportunity_score_expr(lower_map)
        select = _base_select(lower_map, score_expr)

        cat1   = _col(lower_map, "global_category1") or "global_category1"
        price  = _col(lower_map, "sale_price", "price") or "sale_price"
        disc   = _col(lower_map, "discount_percentage", "discount") or "discount_percentage"
        sold   = _col(lower_map, "item_sold", "sales") or "item_sold"
        likes  = _col(lower_map, "like", "likes") or "like"

        for bucket, patterns in DAILY_PICKS_CATEGORIES.items():
            if bucket == "Viral TikTok":
                # Special: price ≤ 500, discount ≥ 15, sold ≥ 100, order by likes+sold
                viral_expr = (
                    f"ROUND({_safe(sold)}*0.35 + {_safe(likes)}*0.35 + "
                    f"{_safe(disc)}*100.0*0.30, 2)"
                )
                title_c  = _col(lower_map, "title") or "title"
                price_c  = _col(lower_map, "sale_price", "price") or "sale_price"
                cat3_c   = _col(lower_map, "global_category3", "global_category2") or "global_category3"
                brand_c  = _col(lower_map, "global_brand", "brand") or "global_brand"
                short_c  = _col(lower_map, "product_short link", "product_link") or "product_link"
                shop_r_c = _col(lower_map, "shop_rating") or "shop_rating"

                sql = f"""
                    SELECT
                        {_q(title_c)} AS title,
                        {_safe(price_c)} AS sale_price,
                        {_safe(sold)} AS item_sold,
                        {_safe(likes)} AS likes,
                        {_safe(shop_r_c)} AS shop_rating,
                        {_safe(disc)} AS discount_pct,
                        COALESCE({_q(cat3_c)}, '') AS category,
                        COALESCE({_q(brand_c)}, 'NoBrand') AS brand,
                        COALESCE({_q(short_c)}, '') AS product_short_link,
                        {viral_expr} AS opportunity_score
                    FROM {table_name}
                    WHERE {_safe(price_c)} > 0
                      AND {_safe(price_c)} <= 500
                      AND {_safe(disc)} >= 15
                      AND {_safe(sold)} >= 100
                    ORDER BY opportunity_score DESC
                    LIMIT {top}
                """
            else:
                where = _cat1_filter(lower_map, patterns)
                sql = (
                    f"SELECT {select} FROM {table_name} "
                    f"WHERE {where} ORDER BY opportunity_score DESC LIMIT {top}"
                )
            results[bucket] = con.execute(sql).df()
    finally:
        con.close()
    return results


def print_daily_picks(picks: dict[str, pd.DataFrame]) -> None:
    from .affiliate_link_engine import get_all_affiliate_links, _normalize_link
    aff_map = get_all_affiliate_links()

    bucket_colors = {
        "Gadget":             "bold cyan",
        "Home":               "bold blue",
        "Viral TikTok":       "bold red",
        "Mobile Accessories": "bold magenta",
        "Mother & Baby":      "bold yellow",
        "Health":             "bold green",
        "Camping":            "bold white",
    }
    for bucket, df in picks.items():
        color = bucket_colors.get(bucket, "bold white")
        console.print(Panel(f"[{color}]{bucket}[/]", expand=False))
        if df.empty:
            console.print(f"  [dim]No products found for this category.[/]\n")
            continue
        _print_table(df, f"[{color}]{bucket}[/]  [dim]({len(df)} picks)[/]")
        # Affiliate link status per product
        for _, row in df.iterrows():
            raw_link = str(row.get("product_short_link", "") or "")
            norm     = _normalize_link(raw_link)
            aff      = aff_map.get(norm) or aff_map.get(raw_link)
            title_s  = str(row.get("title", ""))[:40]
            if aff:
                console.print(f"  [green]🔗 {title_s}[/]  [dim]{aff[:60]}[/]")
            else:
                console.print(f"  [red]⚠  {title_s}[/]  [dim]Needs affiliate link[/]")
        console.print()


# ─────────────────────────────────────────────────────────────────────────────

def export_opportunities(
    output:     str = "exports/opportunities.csv",
    category:   str | None = None,
    keyword:    str | None = None,
    top:        int = 100,
    table_name: str | None = None,
) -> str:
    """
    Export top opportunities to CSV.
    Uses DuckDB COPY TO — no Pandas memory pressure for large exports.
    """
    table_name = table_name or config.default_table
    out_path = Path(output)
    if not out_path.is_absolute():
        out_path = config.data_dir.parent / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    con = _connect()
    try:
        cols, _ = _get_schema(con, table_name)
        lower_map = {c.lower(): c for c in cols}
        score_expr = _opportunity_score_expr(lower_map)
        select = _base_select(lower_map, score_expr)

        title_col = _col(lower_map, "title", "product_name") or "title"
        conds = ["1=1"]
        if keyword:
            kw = keyword.replace("'", "''").lower()
            conds.append(f"LOWER({_q(title_col)}) LIKE '%{kw}%'")
        if category:
            conds.append(_any_cat_filter(lower_map, category))

        inner_sql = (
            f"SELECT {select} FROM {table_name} "
            f"WHERE {' AND '.join(conds)} "
            f"ORDER BY opportunity_score DESC LIMIT {top}"
        )
        # DuckDB COPY writes directly to disk
        out_posix = out_path.as_posix()
        con.execute(f"COPY ({inner_sql}) TO '{out_posix}' (HEADER, DELIMITER ',')")
    finally:
        con.close()

    return str(out_path)
