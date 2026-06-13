"""Full-text product search using DuckDB ILIKE queries."""

from __future__ import annotations

import duckdb
import pandas as pd
from rich.console import Console
from rich.table import Table

from .config import config, build_column_map

console = Console()


def _get_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [
        row[0]
        for row in con.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'"
        ).fetchall()
    ]


def search_products(
    keyword: str,
    table_name: str | None = None,
    limit: int = 20,
    min_price: float | None = None,
    max_price: float | None = None,
    category: str | None = None,
    min_rating: float | None = None,
) -> pd.DataFrame:
    """Search products by keyword with optional filters. Returns a DataFrame."""
    table_name = table_name or config.default_table

    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        columns = _get_columns(con, table_name)
        col_map = build_column_map(columns)

        # Build WHERE clauses
        conditions: list[str] = []

        # Keyword search — try name first, fall back to all text columns
        name_col = col_map.get("product_name")
        if name_col:
            kw = keyword.replace("'", "''")
            conditions.append(f"LOWER(\"{name_col}\") LIKE LOWER('%{kw}%')")
        else:
            # Search all VARCHAR columns
            text_cols = _varchar_columns(con, table_name)
            if text_cols:
                kw = keyword.replace("'", "''")
                parts = [f"LOWER(\"{c}\") LIKE LOWER('%{kw}%')" for c in text_cols[:5]]
                conditions.append(f"({' OR '.join(parts)})")

        price_col = col_map.get("price")
        if price_col:
            if min_price is not None:
                conditions.append(f'TRY_CAST("{price_col}" AS DOUBLE) >= {min_price}')
            if max_price is not None:
                conditions.append(f'TRY_CAST("{price_col}" AS DOUBLE) <= {max_price}')

        cat_col = col_map.get("category")
        if category and cat_col:
            cat = category.replace("'", "''")
            conditions.append(f"LOWER(\"{cat_col}\") LIKE LOWER('%{cat}%')")

        rating_col = col_map.get("rating")
        if min_rating is not None and rating_col:
            conditions.append(f'TRY_CAST("{rating_col}" AS DOUBLE) >= {min_rating}')

        where = " AND ".join(conditions) if conditions else "1=1"

        # Sort by sales if available, else by rating
        order_col = col_map.get("sales") or col_map.get("rating") or columns[0]

        sql = f"""
            SELECT *
            FROM {table_name}
            WHERE {where}
            ORDER BY TRY_CAST("{order_col}" AS DOUBLE) DESC NULLS LAST
            LIMIT {limit}
        """
        df = con.execute(sql).df()
    finally:
        con.close()

    return df


def _varchar_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [
        row[0]
        for row in con.execute(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND data_type IN ('VARCHAR', 'TEXT')"
        ).fetchall()
    ]


def print_search_results(df: pd.DataFrame, keyword: str) -> None:
    """Render search results as a Rich table."""
    if df.empty:
        console.print(f"[yellow]No products found for '[bold]{keyword}[/]'[/]")
        return

    col_map = build_column_map(list(df.columns))
    display_cols = _pick_display_columns(df.columns.tolist(), col_map)

    tbl = Table(
        title=f"Search: [bold cyan]{keyword}[/]  ({len(df)} results)",
        show_lines=True,
        expand=True,
    )

    col_styles = {
        "product_name": ("Name", "bold white", 40),
        "price": ("Price", "green", 12),
        "original_price": ("Orig. Price", "dim", 12),
        "sales": ("Sales", "yellow", 10),
        "commission_rate": ("Comm %", "magenta", 8),
        "rating": ("Rating", "cyan", 7),
        "rating_count": ("Reviews", "dim", 8),
        "category": ("Category", "blue", 20),
        "shop_name": ("Shop", "dim", 20),
    }

    for canonical in display_cols:
        label, style, width = col_styles.get(canonical, (canonical, "white", 15))
        tbl.add_column(label, style=style, max_width=width, no_wrap=(width < 20))

    for _, row in df.iterrows():
        cells = []
        for canonical in display_cols:
            actual = col_map[canonical]
            val = row.get(actual, "")
            if canonical == "price" and val not in ("", None):
                try:
                    val = f"฿{float(val):,.0f}"
                except (ValueError, TypeError):
                    pass
            elif canonical == "commission_rate" and val not in ("", None):
                try:
                    val = f"{float(val):.1f}%"
                except (ValueError, TypeError):
                    pass
            elif canonical == "rating" and val not in ("", None):
                try:
                    val = f"★ {float(val):.1f}"
                except (ValueError, TypeError):
                    pass
            cells.append(str(val) if val is not None else "")
        tbl.add_row(*cells)

    console.print(tbl)


def _pick_display_columns(
    actual_cols: list[str], col_map: dict[str, str]
) -> list[str]:
    """Return ordered list of canonical keys to display, prefer most useful."""
    preferred = [
        "product_name", "price", "original_price",
        "sales", "commission_rate", "rating", "rating_count",
        "category", "shop_name",
    ]
    return [c for c in preferred if c in col_map]
