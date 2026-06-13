"""Category and commission analytics over the full DuckDB table."""

from __future__ import annotations

import duckdb
import pandas as pd
from rich.bar import Bar
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import config, build_column_map

console = Console()


def _connect() -> duckdb.DuckDBPyConnection:
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")
    return duckdb.connect(str(config.db_path), read_only=True)


def _get_col_map(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    cols = [
        r[0]
        for r in con.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'"
        ).fetchall()
    ]
    return build_column_map(cols)


# ---------------------------------------------------------------------------
# Category Report
# ---------------------------------------------------------------------------

def category_report(
    top_n: int = 20,
    table_name: str | None = None,
) -> pd.DataFrame:
    """Aggregate stats by category — product count, avg price, total sales, avg commission."""
    table_name = table_name or config.default_table
    con = _connect()
    try:
        col_map = _get_col_map(con, table_name)
        cat_col = col_map.get("category")
        if not cat_col:
            raise ValueError(
                "No category column detected. Check COLUMN_ALIASES in config.py."
            )

        agg_parts = [f'COUNT(*) AS "product_count"']

        price_col = col_map.get("price")
        if price_col:
            agg_parts.append(
                f'AVG(TRY_CAST("{price_col}" AS DOUBLE)) AS "avg_price"'
            )

        sales_col = col_map.get("sales")
        if sales_col:
            agg_parts.append(
                f'SUM(TRY_CAST("{sales_col}" AS DOUBLE)) AS "total_sales"'
            )
            agg_parts.append(
                f'AVG(TRY_CAST("{sales_col}" AS DOUBLE)) AS "avg_sales"'
            )

        comm_col = col_map.get("commission_rate")
        if comm_col:
            agg_parts.append(
                f'AVG(TRY_CAST("{comm_col}" AS DOUBLE)) AS "avg_commission"'
            )
            agg_parts.append(
                f'MAX(TRY_CAST("{comm_col}" AS DOUBLE)) AS "max_commission"'
            )

        rating_col = col_map.get("rating")
        if rating_col:
            agg_parts.append(
                f'AVG(TRY_CAST("{rating_col}" AS DOUBLE)) AS "avg_rating"'
            )

        sort_by = "total_sales" if sales_col else "product_count"

        sql = f"""
            SELECT "{cat_col}" AS category, {", ".join(agg_parts)}
            FROM {table_name}
            WHERE "{cat_col}" IS NOT NULL AND TRIM("{cat_col}") != ''
            GROUP BY "{cat_col}"
            ORDER BY {sort_by} DESC NULLS LAST
            LIMIT {top_n}
        """
        df = con.execute(sql).df()
    finally:
        con.close()

    return df


def print_category_report(df: pd.DataFrame) -> None:
    if df.empty:
        console.print("[yellow]No category data available.[/]")
        return

    tbl = Table(
        title="[bold green]Category Report[/]",
        show_lines=True,
        expand=True,
    )

    col_formats: dict[str, tuple[str, str, str]] = {
        "category":       ("Category",      "bold cyan",   "left"),
        "product_count":  ("Products",      "white",       "right"),
        "avg_price":      ("Avg Price",     "green",       "right"),
        "total_sales":    ("Total Sales",   "yellow",      "right"),
        "avg_sales":      ("Avg Sales",     "dim",         "right"),
        "avg_commission": ("Avg Comm %",    "magenta",     "right"),
        "max_commission": ("Max Comm %",    "dim magenta", "right"),
        "avg_rating":     ("Avg Rating",    "cyan",        "right"),
    }

    for col in df.columns:
        label, style, justify = col_formats.get(col, (col, "white", "left"))
        tbl.add_column(label, style=style, justify=justify)  # type: ignore[arg-type]

    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = row[col]
            if col == "avg_price" and pd.notna(val):
                val = f"฿{val:,.0f}"
            elif col in ("total_sales", "avg_sales") and pd.notna(val):
                val = f"{val:,.0f}"
            elif col in ("avg_commission", "max_commission") and pd.notna(val):
                val = f"{val:.1f}%"
            elif col == "avg_rating" and pd.notna(val):
                val = f"★ {val:.2f}"
            elif col == "product_count" and pd.notna(val):
                val = f"{int(val):,}"
            cells.append(str(val) if pd.notna(val) else "—")
        tbl.add_row(*cells)

    console.print(tbl)


# ---------------------------------------------------------------------------
# Commission Analysis
# ---------------------------------------------------------------------------

def commission_analysis(
    table_name: str | None = None,
) -> pd.DataFrame:
    """Distribution of commission rates in 5% buckets."""
    table_name = table_name or config.default_table
    con = _connect()
    try:
        col_map = _get_col_map(con, table_name)
        comm_col = col_map.get("commission_rate")
        if not comm_col:
            raise ValueError("No commission_rate column detected.")

        sql = f"""
            SELECT
                FLOOR(TRY_CAST("{comm_col}" AS DOUBLE) / 5) * 5  AS bucket_start,
                COUNT(*) AS product_count
            FROM {table_name}
            WHERE TRY_CAST("{comm_col}" AS DOUBLE) IS NOT NULL
            GROUP BY bucket_start
            ORDER BY bucket_start
        """
        df = con.execute(sql).df()
    finally:
        con.close()

    return df


def print_commission_analysis(df: pd.DataFrame) -> None:
    if df.empty:
        console.print("[yellow]No commission data available.[/]")
        return

    max_count = df["product_count"].max()
    console.print(Panel("[bold magenta]Commission Rate Distribution[/]", expand=False))

    for _, row in df.iterrows():
        bucket = row["bucket_start"]
        count = int(row["product_count"])
        bar_len = int(count / max_count * 40)
        label = f"  {int(bucket):>3}–{int(bucket)+4}%"
        bar = "█" * bar_len
        console.print(f"[dim]{label}[/]  [magenta]{bar}[/] [dim]{count:,}[/]")


# ---------------------------------------------------------------------------
# Database Summary
# ---------------------------------------------------------------------------

def db_summary(table_name: str | None = None) -> None:
    """Print high-level stats about the imported datafeed."""
    table_name = table_name or config.default_table
    con = _connect()
    try:
        col_map = _get_col_map(con, table_name)
        total = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

        stats: list[tuple[str, str]] = [
            ("Total products", f"{total:,}"),
            ("Database path", str(config.db_path)),
            ("Canonical columns detected", str(len(col_map))),
        ]

        for canonical, actual in [
            ("price", "price"),
            ("sales", "sales"),
            ("commission_rate", "commission_rate"),
            ("rating", "rating"),
        ]:
            if canonical in col_map:
                col = col_map[canonical]
                row = con.execute(
                    f'SELECT MIN(TRY_CAST("{col}" AS DOUBLE)), '
                    f'       MAX(TRY_CAST("{col}" AS DOUBLE)), '
                    f'       AVG(TRY_CAST("{col}" AS DOUBLE)) '
                    f'FROM {table_name}'
                ).fetchone()
                if row and row[0] is not None:
                    mn, mx, avg = row
                    stats.append((
                        f"  {canonical}",
                        f"min={mn:.2f}  max={mx:.2f}  avg={avg:.2f}",
                    ))
    finally:
        con.close()

    tbl = Table(title="[bold green]Datafeed Summary[/]", show_lines=False, expand=False)
    tbl.add_column("Metric", style="bold cyan")
    tbl.add_column("Value", style="white")
    for k, v in stats:
        tbl.add_row(k, v)
    console.print(tbl)
