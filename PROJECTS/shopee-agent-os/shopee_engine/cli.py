"""Typer CLI — entry point for all shopee-agent-os commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="shopee",
    help="[bold green]Shopee Product Intelligence Engine[/] — analyze Affiliate Datafeed at GB scale.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# import-datafeed
# ---------------------------------------------------------------------------

@app.command("import-datafeed")
def cmd_import_datafeed(
    csv_path: str = typer.Argument(..., help="Path to the Shopee affiliate CSV file (supports 3–10 GB+)"),
    table: str = typer.Option("products", "--table", "-t", help="DuckDB table name"),
    delimiter: str = typer.Option(",", "--delimiter", "-d", help="CSV delimiter (use \\t for TSV)"),
    ignore_errors: bool = typer.Option(True, "--ignore-errors/--strict", help="Skip malformed rows"),
) -> None:
    """
    Import a Shopee Affiliate Datafeed CSV into DuckDB.

    The file is streamed — never fully loaded into RAM.

    Example:
        shopee import-datafeed ./shopee_th_feed.csv
        shopee import-datafeed ./feed.tsv --delimiter \\t
    """
    from .importer import import_datafeed

    try:
        result = import_datafeed(csv_path, table_name=table, delimiter=delimiter, ignore_errors=ignore_errors)
        console.print(f"\n[bold green]Done![/] {result['row_count']:,} rows → table [cyan]{result['table']}[/]")
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Import failed:[/] {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# show-schema
# ---------------------------------------------------------------------------

@app.command("show-schema")
def cmd_show_schema(
    table: str = typer.Option("products", "--table", "-t", help="Table name to inspect"),
) -> None:
    """Show columns, types, and sample rows for the imported table."""
    from .importer import get_table_info
    get_table_info(table_name=table)


# ---------------------------------------------------------------------------
# search-products
# ---------------------------------------------------------------------------

@app.command("search-products")
def cmd_search_products(
    keyword: str = typer.Argument(..., help="Search keyword"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results to show"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum price filter"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum price filter"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category name"),
    min_rating: Optional[float] = typer.Option(None, "--min-rating", help="Minimum star rating (e.g. 4.5)"),
    table: str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Search products by keyword with optional filters.

    Example:
        shopee search-products "running shoes" --category Sports --min-rating 4.5
        shopee search-products "iphone case" --max-price 500 --limit 50
    """
    from .search import search_products, print_search_results

    with console.status(f"[yellow]Searching for '{keyword}'...[/]"):
        try:
            df = search_products(
                keyword,
                table_name=table,
                limit=limit,
                min_price=min_price,
                max_price=max_price,
                category=category,
                min_rating=min_rating,
            )
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_search_results(df, keyword)


# ---------------------------------------------------------------------------
# top-products
# ---------------------------------------------------------------------------

@app.command("top-products")
def cmd_top_products(
    n: int = typer.Option(20, "--top", "-n", help="Number of products to show"),
    rank_by: str = typer.Option(
        "sales",
        "--rank-by", "-r",
        help="Metric to rank by: sales | commission_rate | rating | price",
    ),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    table: str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Show top N products ranked by a chosen metric.

    Example:
        shopee top-products --rank-by commission_rate --top 50
        shopee top-products --rank-by sales --category Electronics
    """
    from .ranking import top_products, print_top_products, RANK_BY_OPTIONS

    if rank_by not in RANK_BY_OPTIONS:
        console.print(
            f"[red]Invalid rank-by '{rank_by}'.[/] Choose from: {', '.join(RANK_BY_OPTIONS)}"
        )
        raise typer.Exit(1)

    with console.status(f"[yellow]Ranking by {rank_by}...[/]"):
        try:
            df = top_products(n=n, rank_by=rank_by, category=category, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_top_products(df, rank_by=rank_by, n=n)


# ---------------------------------------------------------------------------
# category-report
# ---------------------------------------------------------------------------

@app.command("category-report")
def cmd_category_report(
    top_n: int = typer.Option(20, "--top", "-n", help="Number of categories to show"),
    table: str = typer.Option("products", "--table", "-t", help="Table name"),
    with_commission: bool = typer.Option(False, "--commission", is_flag=True, help="Show commission distribution chart"),
) -> None:
    """
    Aggregated stats per category: product count, avg price, total sales, commission.

    Example:
        shopee category-report --top 30
        shopee category-report --commission
    """
    from .analytics import (
        category_report, print_category_report,
        commission_analysis, print_commission_analysis,
        db_summary,
    )

    db_summary(table_name=table)
    console.print()

    with console.status("[yellow]Building category report...[/]"):
        try:
            df = category_report(top_n=top_n, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_category_report(df)

    if with_commission:
        console.print()
        try:
            comm_df = commission_analysis(table_name=table)
            print_commission_analysis(comm_df)
        except ValueError as e:
            console.print(f"[yellow]Commission chart skipped:[/] {e}")


# ---------------------------------------------------------------------------
# summary (bonus convenience command)
# ---------------------------------------------------------------------------

@app.command("summary")
def cmd_summary(
    table: str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """Quick stats snapshot of the imported datafeed."""
    from .analytics import db_summary
    try:
        db_summary(table_name=table)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
