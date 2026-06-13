"""CSV → DuckDB importer.  Never loads the full file into RAM."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import config, build_column_map

console = Console()


def _file_size_mb(path: Path) -> float:
    return path.stat().st_size / 1_048_576


def import_datafeed(
    csv_path: str | Path,
    table_name: str | None = None,
    delimiter: str = ",",
    ignore_errors: bool = True,
) -> dict:
    """
    Stream a CSV file into DuckDB using read_csv_auto — no full-RAM load.

    Returns a summary dict with row_count, columns, and db_path.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")

    table_name = table_name or config.default_table
    config.data_dir.mkdir(parents=True, exist_ok=True)

    size_mb = _file_size_mb(csv_path)
    console.print(
        Panel(
            f"[bold cyan]Source:[/] {csv_path}\n"
            f"[bold cyan]Size:[/]   {size_mb:,.1f} MB\n"
            f"[bold cyan]Table:[/]  {table_name}\n"
            f"[bold cyan]DB:[/]     {config.db_path}",
            title="[bold green]Shopee Datafeed Import",
            expand=False,
        )
    )

    # Use forward-slash paths on Windows so DuckDB's SQL parser is happy
    csv_str = csv_path.as_posix()

    with console.status("[bold yellow]Importing — DuckDB is streaming the CSV..."):
        con = duckdb.connect(str(config.db_path))
        try:
            con.execute(f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT *
                FROM read_csv_auto(
                    '{csv_str}',
                    header       = true,
                    delim        = '{delimiter}',
                    ignore_errors = {str(ignore_errors).lower()},
                    parallel     = true
                )
            """)
            row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            columns = [
                row[0]
                for row in con.execute(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{table_name}'"
                ).fetchall()
            ]
        finally:
            con.close()

    col_map = build_column_map(columns)
    _print_import_summary(table_name, row_count, columns, col_map)

    return {
        "table": table_name,
        "row_count": row_count,
        "columns": columns,
        "column_map": col_map,
        "db_path": str(config.db_path),
    }


def get_table_info(table_name: str | None = None) -> None:
    """Print schema + sample rows for an existing DuckDB table."""
    table_name = table_name or config.default_table

    if not config.db_path.exists():
        console.print("[red]No database found. Run import-datafeed first.[/]")
        return

    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        rows = con.execute(
            f"SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' ORDER BY ordinal_position"
        ).fetchall()
        if not rows:
            console.print(f"[red]Table '{table_name}' not found in database.[/]")
            return

        count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

        tbl = Table(title=f"Schema: {table_name}  ({count:,} rows)", show_lines=False)
        tbl.add_column("#", style="dim", width=4)
        tbl.add_column("Column", style="bold cyan")
        tbl.add_column("Type", style="green")
        for i, (col, dtype) in enumerate(rows, 1):
            tbl.add_row(str(i), col, dtype)
        console.print(tbl)

        sample = con.execute(f"SELECT * FROM {table_name} LIMIT 3").df()
        console.print("\n[bold]Sample rows:[/]")
        console.print(sample.to_string())
    finally:
        con.close()


def _print_import_summary(
    table_name: str,
    row_count: int,
    columns: list[str],
    col_map: dict[str, str],
) -> None:
    tbl = Table(title="Import Complete", show_lines=False, expand=False)
    tbl.add_column("Metric", style="bold cyan")
    tbl.add_column("Value", style="white")

    tbl.add_row("Table", table_name)
    tbl.add_row("Rows imported", f"[bold green]{row_count:,}[/]")
    tbl.add_row("Columns detected", str(len(columns)))

    mapped = ", ".join(col_map.keys()) or "[dim]none matched[/]"
    tbl.add_row("Canonical mappings", mapped)

    console.print(tbl)

    if len(col_map) < 3:
        console.print(
            "[yellow]Tip: Few canonical columns detected. "
            "Run [bold]shopee show-schema[/] to see actual column names "
            "and adjust COLUMN_ALIASES in config.py if needed.[/]"
        )
