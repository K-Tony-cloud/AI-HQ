"""Product ranking — top sellers, best commission, highest rated."""

from __future__ import annotations

import duckdb
import pandas as pd
from rich.console import Console
from rich.table import Table

from .config import config, build_column_map

console = Console()

RANK_BY_OPTIONS = ("sales", "commission_rate", "rating", "price")


def top_products(
    n: int = 20,
    rank_by: str = "sales",
    category: str | None = None,
    table_name: str | None = None,
) -> pd.DataFrame:
    """Return top N products ranked by the given metric."""
    table_name = table_name or config.default_table

    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        columns = [
            row[0]
            for row in con.execute(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'"
            ).fetchall()
        ]
        col_map = build_column_map(columns)

        sort_col = col_map.get(rank_by)
        if sort_col is None:
            # Fall back: try sales → rating → first numeric column
            for fallback in ("sales", "rating", "commission_rate"):
                sort_col = col_map.get(fallback)
                if sort_col:
                    rank_by = fallback
                    break
            if sort_col is None:
                raise ValueError(
                    f"Cannot rank by '{rank_by}'. Available canonical columns: "
                    + ", ".join(col_map.keys())
                )

        conditions = []
        cat_col = col_map.get("category")
        if category and cat_col:
            cat = category.replace("'", "''")
            conditions.append(f"LOWER(\"{cat_col}\") LIKE LOWER('%{cat}%')")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT *
            FROM {table_name}
            {where}
            ORDER BY TRY_CAST("{sort_col}" AS DOUBLE) DESC NULLS LAST
            LIMIT {n}
        """
        df = con.execute(sql).df()
    finally:
        con.close()

    return df


def print_top_products(df: pd.DataFrame, rank_by: str, n: int) -> None:
    """Render ranking as a Rich table with rank numbers."""
    if df.empty:
        console.print("[yellow]No products found.[/]")
        return

    col_map = build_column_map(list(df.columns))

    label_map = {
        "sales": "Sales",
        "commission_rate": "Commission %",
        "rating": "Rating",
        "price": "Price",
    }
    metric_label = label_map.get(rank_by, rank_by)

    tbl = Table(
        title=f"[bold green]Top {n} Products[/] — ranked by [bold yellow]{metric_label}[/]",
        show_lines=True,
        expand=True,
    )

    tbl.add_column("#", style="bold dim", width=4, justify="right")

    display_order = [
        ("product_name", "Name", "bold white", 45),
        ("price", "Price", "green", 12),
        ("sales", "Sales", "yellow", 10),
        ("commission_rate", "Comm %", "magenta", 8),
        ("rating", "Rating", "cyan", 7),
        ("rating_count", "Reviews", "dim", 9),
        ("category", "Category", "blue", 20),
        ("shop_name", "Shop", "dim", 20),
    ]

    shown: list[tuple[str, str]] = []  # (canonical, actual)
    for canonical, label, style, width in display_order:
        if canonical in col_map:
            tbl.add_column(label, style=style, max_width=width, no_wrap=(width < 20))
            shown.append((canonical, col_map[canonical]))

    for rank, (_, row) in enumerate(df.iterrows(), 1):
        cells = [str(rank)]
        for canonical, actual in shown:
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
                    stars = float(val)
                    val = f"★ {stars:.1f}"
                except (ValueError, TypeError):
                    pass
            elif canonical == "sales" and val not in ("", None):
                try:
                    val = f"{int(float(val)):,}"
                except (ValueError, TypeError):
                    pass
            cells.append(str(val) if val is not None else "")
        tbl.add_row(*cells)

    console.print(tbl)
