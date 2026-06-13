"""Affiliate Performance Engine — import and analyze Shopee Affiliate report CSVs."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .config import config

console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERF_TABLE = "affiliate_performance"

# Shopee Affiliate Report may use these column names across report types
PERF_COLUMN_ALIASES: dict[str, list[str]] = {
    "date":           ["date", "order_date", "click_date", "report_date", "day"],
    "product_id":     ["item_id", "itemid", "product_id", "item id", "sku_id"],
    "product_name":   ["item_name", "product_name", "item name", "name", "title"],
    "clicks":         ["clicks", "click", "total_clicks", "click_count"],
    "orders":         ["orders", "order", "conversions", "total_orders", "confirmed_orders"],
    "revenue":        ["gmv", "revenue", "total_gmv", "total_revenue", "order_amount", "sales_amount"],
    "commission":     ["commission", "total_commission", "affiliate_commission", "my_commission"],
    "commission_rate": ["commission_rate", "commission%", "comm_rate", "rate"],
    "category":       ["category", "cat_name", "category_name", "item_category"],
    "shop_name":      ["shop_name", "shopname", "seller_name", "store_name"],
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.db_path), read_only=read_only)


def _q(name: str) -> str:
    return f'"{name}"'


def _safe(col: str, default: float = 0.0) -> str:
    return f"COALESCE(TRY_CAST({_q(col)} AS DOUBLE), {default})"


def _resolve(actual_cols: list[str], *candidates: str) -> str | None:
    lower_map = {c.lower(): c for c in actual_cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _detect_perf_columns(actual_cols: list[str]) -> dict[str, str | None]:
    """Map canonical performance column names to actual CSV column names."""
    result: dict[str, str | None] = {}
    for canonical, aliases in PERF_COLUMN_ALIASES.items():
        result[canonical] = _resolve(actual_cols, *aliases)
    return result


# ---------------------------------------------------------------------------
# Schema detection & table init
# ---------------------------------------------------------------------------

def _init_perf_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {PERF_TABLE} (
            id           INTEGER,
            date         VARCHAR,
            product_id   VARCHAR,
            product_name VARCHAR,
            category     VARCHAR,
            shop_name    VARCHAR,
            clicks       DOUBLE,
            orders       DOUBLE,
            revenue      DOUBLE,
            commission   DOUBLE,
            commission_rate DOUBLE,
            source_file  VARCHAR,
            imported_at  TIMESTAMP
        )
    """)


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {PERF_TABLE}").fetchone()
    return row[0] if row else 1


# ---------------------------------------------------------------------------
# Public: import_affiliate_report
# ---------------------------------------------------------------------------

def import_affiliate_report(csv_path: str | Path) -> dict:
    """
    Import a Shopee Affiliate Report CSV into DuckDB.
    Auto-detects schema across Orders / Click / Commission report types.
    Appends to existing data (supports multiple report files).
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Sniff delimiter and header
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(sample)
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    # Read headers only first
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader)

    headers = [h.strip() for h in headers]
    col_map = _detect_perf_columns(headers)

    con = _connect(read_only=False)
    _init_perf_table(con)

    # Read full CSV via DuckDB (streaming)
    posix = path.as_posix()
    temp = f"_tmp_perf_{abs(hash(posix)) % 99999}"
    con.execute(f"""
        CREATE TEMP TABLE {temp} AS
        SELECT * FROM read_csv_auto('{posix}', header=true,
                                    delim='{delimiter}', ignore_errors=true)
    """)

    actual = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{temp}'"
    ).fetchall()]
    col_map = _detect_perf_columns(actual)

    def expr(canonical: str) -> str:
        col = col_map.get(canonical)
        if col:
            if canonical in ("clicks", "orders", "revenue", "commission", "commission_rate"):
                return f"{_safe(col)} AS {canonical}"
            return f"{_q(col)} AS {canonical}"
        # return NULL placeholder
        if canonical in ("clicks", "orders", "revenue", "commission", "commission_rate"):
            return f"0.0 AS {canonical}"
        return f"NULL AS {canonical}"

    start_id = _next_id(con)
    now_str = datetime.now().isoformat(sep=" ", timespec="seconds")

    con.execute(f"""
        INSERT INTO {PERF_TABLE}
        SELECT
            ROW_NUMBER() OVER () + {start_id - 1} AS id,
            {expr('date')},
            {expr('product_id')},
            {expr('product_name')},
            {expr('category')},
            {expr('shop_name')},
            {expr('clicks')},
            {expr('orders')},
            {expr('revenue')},
            {expr('commission')},
            {expr('commission_rate')},
            '{path.name}' AS source_file,
            '{now_str}' AS imported_at
        FROM {temp}
    """)

    row_count = con.execute(f"SELECT COUNT(*) FROM {PERF_TABLE} WHERE source_file='{path.name}'").fetchone()[0]
    total = con.execute(f"SELECT COUNT(*) FROM {PERF_TABLE}").fetchone()[0]
    con.close()

    return {
        "file": path.name,
        "rows_imported": row_count,
        "total_rows": total,
        "columns_detected": {k: v for k, v in col_map.items() if v},
    }


# ---------------------------------------------------------------------------
# Public: daily_performance
# ---------------------------------------------------------------------------

def daily_performance(days: int = 30) -> pd.DataFrame:
    """Clicks, Orders, Conversion Rate, Revenue, Commission aggregated by date."""
    con = _connect(read_only=True)
    try:
        total = con.execute(f"SELECT COUNT(*) FROM {PERF_TABLE}").fetchone()[0]
    except Exception:
        raise RuntimeError("No affiliate performance data. Run import-affiliate-report first.")
    if total == 0:
        raise RuntimeError("No affiliate performance data. Run import-affiliate-report first.")

    df = con.execute(f"""
        SELECT
            date,
            SUM(clicks)     AS clicks,
            SUM(orders)     AS orders,
            SUM(revenue)    AS revenue,
            SUM(commission) AS commission,
            CASE WHEN SUM(clicks) > 0
                 THEN ROUND(SUM(orders) / SUM(clicks) * 100, 2)
                 ELSE 0 END AS conversion_rate,
            CASE WHEN SUM(clicks) > 0
                 THEN ROUND(SUM(commission) / SUM(clicks), 4)
                 ELSE 0 END AS epc
        FROM {PERF_TABLE}
        WHERE date IS NOT NULL
        GROUP BY date
        ORDER BY date DESC
        LIMIT {days}
    """).df()
    con.close()
    return df


# ---------------------------------------------------------------------------
# Public: product_performance
# ---------------------------------------------------------------------------

def product_performance(top: int = 50) -> pd.DataFrame:
    """Ranked table: Product, Clicks, Orders, Conversion Rate, Revenue, Commission."""
    con = _connect(read_only=True)
    try:
        total = con.execute(f"SELECT COUNT(*) FROM {PERF_TABLE}").fetchone()[0]
    except Exception:
        raise RuntimeError("No affiliate performance data. Run import-affiliate-report first.")
    if total == 0:
        raise RuntimeError("No affiliate performance data.")

    df = con.execute(f"""
        SELECT
            COALESCE(product_name, product_id, 'Unknown') AS product,
            category,
            SUM(clicks)     AS clicks,
            SUM(orders)     AS orders,
            SUM(revenue)    AS revenue,
            SUM(commission) AS commission,
            CASE WHEN SUM(clicks) > 0
                 THEN ROUND(SUM(orders) / SUM(clicks) * 100, 2)
                 ELSE 0 END AS conversion_rate,
            CASE WHEN SUM(clicks) > 0
                 THEN ROUND(SUM(commission) / SUM(clicks), 4)
                 ELSE 0 END AS epc
        FROM {PERF_TABLE}
        GROUP BY product_name, product_id, category
        ORDER BY commission DESC
        LIMIT {top}
    """).df()
    con.close()
    return df


# ---------------------------------------------------------------------------
# Public: top_profit_products
# ---------------------------------------------------------------------------

def top_profit_products(top: int = 30) -> pd.DataFrame:
    """Rank by Commission DESC, then EPC, then Conversion Rate."""
    con = _connect(read_only=True)
    try:
        total = con.execute(f"SELECT COUNT(*) FROM {PERF_TABLE}").fetchone()[0]
    except Exception:
        raise RuntimeError("No affiliate performance data. Run import-affiliate-report first.")
    if total == 0:
        raise RuntimeError("No affiliate performance data.")

    df = con.execute(f"""
        SELECT
            COALESCE(product_name, product_id, 'Unknown') AS product,
            category,
            SUM(commission) AS total_commission,
            CASE WHEN SUM(clicks) > 0
                 THEN ROUND(SUM(commission) / SUM(clicks), 4)
                 ELSE 0 END AS epc,
            CASE WHEN SUM(clicks) > 0
                 THEN ROUND(SUM(orders) / SUM(clicks) * 100, 2)
                 ELSE 0 END AS conversion_rate,
            SUM(clicks)  AS clicks,
            SUM(orders)  AS orders,
            SUM(revenue) AS revenue
        FROM {PERF_TABLE}
        GROUP BY product_name, product_id, category
        HAVING SUM(clicks) > 0
        ORDER BY total_commission DESC, epc DESC, conversion_rate DESC
        LIMIT {top}
    """).df()
    con.close()
    return df


# ---------------------------------------------------------------------------
# Public: merge_product_intelligence
# ---------------------------------------------------------------------------

def merge_product_intelligence(table_name: str = "products") -> int:
    """
    Join affiliate performance data with 1M product discovery data.
    Creates/replaces 'profit_intelligence' view in DuckDB.

    profit_score = commission*0.40 + epc*1000*0.30 + conversion_rate*0.30
    """
    con = _connect(read_only=False)

    # Verify both tables exist
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    if PERF_TABLE not in tables:
        con.close()
        raise RuntimeError("No affiliate performance data. Run import-affiliate-report first.")
    if table_name not in tables:
        con.close()
        raise RuntimeError(f"No product table '{table_name}'. Run import-datafeed first.")

    # Get product table columns for safe join
    prod_cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}'"
    ).fetchall()]

    # Find product name column in products table
    lower_map = {c.lower(): c for c in prod_cols}
    name_col = (
        lower_map.get("name") or lower_map.get("product_name") or
        lower_map.get("item_name") or lower_map.get("title") or prod_cols[1] if len(prod_cols) > 1 else None
    )
    sold_col = lower_map.get("item_sold") or lower_map.get("sales") or lower_map.get("sold")
    rating_col = lower_map.get("item_rating") or lower_map.get("rating")

    extra_selects = []
    if sold_col:
        extra_selects.append(f'COALESCE(TRY_CAST("{sold_col}" AS DOUBLE), 0) AS item_sold')
    else:
        extra_selects.append("0 AS item_sold")
    if rating_col:
        extra_selects.append(f'COALESCE(TRY_CAST("{rating_col}" AS DOUBLE), 0) AS item_rating')
    else:
        extra_selects.append("0 AS item_rating")

    extra_str = ", ".join(extra_selects)

    # Build aggregated performance per product
    con.execute(f"""
        CREATE OR REPLACE VIEW profit_intelligence AS
        WITH perf AS (
            SELECT
                COALESCE(product_name, product_id) AS product_key,
                SUM(commission) AS total_commission,
                CASE WHEN SUM(clicks) > 0 THEN SUM(commission)/SUM(clicks) ELSE 0 END AS epc,
                CASE WHEN SUM(clicks) > 0 THEN SUM(orders)/SUM(clicks)*100 ELSE 0 END AS conversion_rate,
                SUM(clicks) AS total_clicks,
                SUM(orders) AS total_orders,
                SUM(revenue) AS total_revenue
            FROM {PERF_TABLE}
            GROUP BY product_name, product_id
        ),
        discovery AS (
            SELECT
                {_q(name_col) if name_col else "NULL"} AS product_key,
                {extra_str}
            FROM "{table_name}"
        )
        SELECT
            p.product_key,
            p.total_commission,
            p.epc,
            p.conversion_rate,
            p.total_clicks,
            p.total_orders,
            p.total_revenue,
            COALESCE(d.item_sold, 0) AS item_sold,
            COALESCE(d.item_rating, 0) AS item_rating,
            -- profit_score = commission*0.40 + epc*1000*0.30 + conversion_rate*0.30
            ROUND(
                p.total_commission * 0.40
                + p.epc * 1000 * 0.30
                + p.conversion_rate * 0.30,
                4
            ) AS profit_score
        FROM perf p
        LEFT JOIN discovery d ON LOWER(p.product_key) = LOWER(d.product_key)
        ORDER BY profit_score DESC
    """)

    count = con.execute("SELECT COUNT(*) FROM profit_intelligence").fetchone()[0]
    con.close()
    return count


# ---------------------------------------------------------------------------
# Public: profit_opportunities
# ---------------------------------------------------------------------------

def profit_opportunities(
    top: int = 30,
    min_commission: float = 0.0,
    min_conversion: float = 0.0,
    category: Optional[str] = None,
) -> pd.DataFrame:
    """
    Find high commission + good conversion + low competition products.
    Requires merge_product_intelligence to have been run first.
    """
    con = _connect(read_only=True)

    # Check view exists
    views = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type='VIEW'"
    ).fetchall()]

    if "profit_intelligence" not in views:
        # Fall back to querying perf table directly
        df = _profit_from_perf(con, top, min_commission, min_conversion)
        con.close()
        return df

    filters = []
    if min_commission > 0:
        filters.append(f"total_commission >= {min_commission}")
    if min_conversion > 0:
        filters.append(f"conversion_rate >= {min_conversion}")

    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    df = con.execute(f"""
        SELECT *
        FROM profit_intelligence
        {where}
        ORDER BY profit_score DESC
        LIMIT {top}
    """).df()
    con.close()
    return df


def _profit_from_perf(
    con: duckdb.DuckDBPyConnection,
    top: int,
    min_commission: float,
    min_conversion: float,
) -> pd.DataFrame:
    filters = ["SUM(clicks) > 0"]
    if min_commission > 0:
        filters.append(f"SUM(commission) >= {min_commission}")

    having = f"HAVING {' AND '.join(filters)}"

    df = con.execute(f"""
        SELECT
            COALESCE(product_name, product_id, 'Unknown') AS product_key,
            SUM(commission) AS total_commission,
            ROUND(SUM(commission)/SUM(clicks), 4) AS epc,
            ROUND(SUM(orders)/SUM(clicks)*100, 2) AS conversion_rate,
            SUM(clicks) AS total_clicks,
            SUM(orders) AS total_orders,
            SUM(revenue) AS total_revenue,
            ROUND(
                SUM(commission)*0.40
                + (SUM(commission)/SUM(clicks))*1000*0.30
                + (SUM(orders)/SUM(clicks)*100)*0.30,
                4
            ) AS profit_score
        FROM {PERF_TABLE}
        GROUP BY product_name, product_id
        {having}
        ORDER BY profit_score DESC
        LIMIT {top}
    """).df()
    return df


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_import_result(result: dict) -> None:
    t = Table(title=f"[bold green]Affiliate Report Imported[/]", show_header=True, header_style="bold cyan")
    t.add_column("Field", style="dim", width=24)
    t.add_column("Value")
    t.add_row("File", result["file"])
    t.add_row("Rows imported", f'{result["rows_imported"]:,}')
    t.add_row("Total rows in DB", f'{result["total_rows"]:,}')
    t.add_row("Detected columns", ", ".join(result["columns_detected"].keys()))
    console.print(t)


def print_daily_performance(df: pd.DataFrame) -> None:
    console.print(Rule("[bold cyan]Daily Affiliate Performance[/]"))
    if df.empty:
        console.print("[yellow]No data.[/]")
        return

    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Date", style="dim", width=12)
    t.add_column("Clicks", justify="right")
    t.add_column("Orders", justify="right")
    t.add_column("Conv.%", justify="right")
    t.add_column("EPC (฿)", justify="right")
    t.add_column("Revenue (฿)", justify="right")
    t.add_column("Commission (฿)", justify="right", style="green")

    for _, r in df.iterrows():
        t.add_row(
            str(r.get("date", "")),
            f'{int(r.get("clicks", 0)):,}',
            f'{int(r.get("orders", 0)):,}',
            f'{r.get("conversion_rate", 0):.2f}%',
            f'{r.get("epc", 0):.4f}',
            f'{r.get("revenue", 0):,.2f}',
            f'[green]{r.get("commission", 0):,.2f}[/]',
        )
    console.print(t)

    # Summary totals
    console.print(
        f"\n[bold]Total:[/]  "
        f"Clicks [cyan]{int(df['clicks'].sum()):,}[/]  |  "
        f"Orders [cyan]{int(df['orders'].sum()):,}[/]  |  "
        f"Revenue [cyan]฿{df['revenue'].sum():,.2f}[/]  |  "
        f"Commission [green]฿{df['commission'].sum():,.2f}[/]"
    )


def print_product_performance(df: pd.DataFrame, top: int) -> None:
    console.print(Rule(f"[bold cyan]Top {top} Products by Performance[/]"))
    if df.empty:
        console.print("[yellow]No data.[/]")
        return

    t = Table(show_header=True, header_style="bold magenta", expand=True)
    t.add_column("#", width=3, justify="right")
    t.add_column("Product", min_width=20, max_width=30, no_wrap=False)
    t.add_column("Clicks", justify="right", min_width=6)
    t.add_column("Orders", justify="right", min_width=6)
    t.add_column("Conv.%", justify="right", min_width=7)
    t.add_column("EPC", justify="right", min_width=7)
    t.add_column("Commission", justify="right", style="green", min_width=10)

    for i, r in enumerate(df.itertuples(), 1):
        prod = str(getattr(r, "product", ""))[:30]
        t.add_row(
            str(i),
            prod,
            f'{int(getattr(r, "clicks", 0)):,}',
            f'{int(getattr(r, "orders", 0)):,}',
            f'{getattr(r, "conversion_rate", 0):.2f}%',
            f'{getattr(r, "epc", 0):.4f}',
            f'[green]฿{getattr(r, "commission", 0):,.2f}[/]',
        )
    console.print(t)


def print_top_profit(df: pd.DataFrame, top: int) -> None:
    console.print(Rule(f"[bold yellow]Top {top} Profit Products[/]"))
    if df.empty:
        console.print("[yellow]No data.[/]")
        return

    t = Table(show_header=True, header_style="bold yellow", expand=True)
    t.add_column("#", width=3, justify="right")
    t.add_column("Product", min_width=22, max_width=32)
    t.add_column("Commission", justify="right", style="green", min_width=11)
    t.add_column("EPC", justify="right", min_width=7)
    t.add_column("Conv.%", justify="right", min_width=7)
    t.add_column("Clicks", justify="right", min_width=6)
    t.add_column("Revenue", justify="right", min_width=10)

    for i, r in enumerate(df.itertuples(), 1):
        prod = str(getattr(r, "product", ""))[:32]
        t.add_row(
            str(i),
            prod,
            f'[green]฿{getattr(r, "total_commission", 0):,.2f}[/]',
            f'{getattr(r, "epc", 0):.4f}',
            f'{getattr(r, "conversion_rate", 0):.2f}%',
            f'{int(getattr(r, "clicks", 0)):,}',
            f'฿{getattr(r, "revenue", 0):,.2f}',
        )
    console.print(t)


def print_profit_opportunities(df: pd.DataFrame, top: int) -> None:
    console.print(Rule(f"[bold magenta]Top {top} Profit Opportunities[/]"))
    if df.empty:
        console.print("[yellow]No data.[/]")
        return

    has_item_sold = "item_sold" in df.columns
    has_profit_score = "profit_score" in df.columns

    t = Table(show_header=True, header_style="bold magenta", expand=True)
    t.add_column("#", width=3, justify="right")
    t.add_column("Product", min_width=22, max_width=30)
    t.add_column("Score", justify="right", style="bold yellow", min_width=7)
    t.add_column("Commission", justify="right", style="green", min_width=11)
    t.add_column("EPC", justify="right", min_width=7)
    t.add_column("Conv.%", justify="right", min_width=7)
    if has_item_sold:
        t.add_column("Sold", justify="right", min_width=7)

    for i, r in enumerate(df.itertuples(), 1):
        prod = str(getattr(r, "product_key", ""))[:35]
        row_data = [
            str(i),
            prod,
            f'{getattr(r, "profit_score", 0):.2f}' if has_profit_score else "—",
            f'[green]฿{getattr(r, "total_commission", 0):,.2f}[/]',
            f'{getattr(r, "epc", 0):.4f}',
            f'{getattr(r, "conversion_rate", 0):.2f}%',
        ]
        if has_item_sold:
            row_data.append(f'{int(getattr(r, "item_sold", 0)):,}')
        t.add_row(*row_data)
    console.print(t)
    console.print(
        "[dim]profit_score = commission×0.40 + epc×1000×0.30 + conversion_rate×0.30[/]"
    )
