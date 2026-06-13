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


# ---------------------------------------------------------------------------
# find-winning-products
# ---------------------------------------------------------------------------

@app.command("find-winning-products")
def cmd_find_winning(
    keyword:         Optional[str]   = typer.Option(None,  "--keyword",          "-k",  help="Search keyword in title"),
    category:        Optional[str]   = typer.Option(None,  "--category",         "-c",  help="Filter by category (any level)"),
    min_sold:        Optional[int]   = typer.Option(None,  "--min-sold",                help="Minimum item_sold"),
    min_rating:      Optional[float] = typer.Option(None,  "--min-rating",              help="Minimum item_rating"),
    min_shop_rating: Optional[float] = typer.Option(None,  "--min-shop-rating",         help="Minimum shop_rating"),
    price_min:       Optional[float] = typer.Option(None,  "--price-min",               help="Minimum sale_price"),
    price_max:       Optional[float] = typer.Option(None,  "--price-max",               help="Maximum sale_price"),
    min_discount:    Optional[float] = typer.Option(None,  "--min-discount",            help="Minimum discount_percentage"),
    top:             int             = typer.Option(30,    "--top",              "-n",  help="Max results"),
    table:           str             = typer.Option("products", "--table",       "-t",  help="Table name"),
) -> None:
    """
    Find winning products for affiliate/content creation with multi-filter + opportunity_score.

    Example:
        shopee find-winning-products --category Face --min-sold 500 --min-shop-rating 4.8 --price-min 50 --price-max 1500 --top 30
        shopee find-winning-products --keyword ลิปสติก --min-discount 20 --top 20
    """
    from .discovery import find_winning_products, print_winning_products

    filters = []
    if keyword:         filters.append(f"keyword={keyword}")
    if category:        filters.append(f"cat={category}")
    if min_sold:        filters.append(f"sold≥{min_sold}")
    if min_shop_rating: filters.append(f"shop★≥{min_shop_rating}")
    if price_min:       filters.append(f"฿≥{price_min:.0f}")
    if price_max:       filters.append(f"฿≤{price_max:.0f}")
    if min_discount:    filters.append(f"disc≥{min_discount:.0f}%")

    with console.status("[yellow]Finding winning products...[/]"):
        try:
            df = find_winning_products(
                keyword=keyword, category=category, min_sold=min_sold,
                min_rating=min_rating, min_shop_rating=min_shop_rating,
                price_min=price_min, price_max=price_max,
                min_discount=min_discount, top=top, table_name=table,
            )
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_winning_products(df, filters_desc=", ".join(filters))


# ---------------------------------------------------------------------------
# top-opportunities
# ---------------------------------------------------------------------------

@app.command("top-opportunities")
def cmd_top_opportunities(
    top:      int          = typer.Option(30,        "--top",      "-n", help="Number of results"),
    category: Optional[str] = typer.Option(None,    "--category", "-c", help="Filter by category"),
    table:    str          = typer.Option("products","--table",    "-t", help="Table name"),
) -> None:
    """
    Rank all products by opportunity_score (sales×0.40 + likes×0.15 + discount×0.15 + ratings×0.30).

    Example:
        shopee top-opportunities --top 50
        shopee top-opportunities --category Beauty --top 30
    """
    from .discovery import top_opportunities, print_top_opportunities

    with console.status("[yellow]Computing opportunity scores...[/]"):
        try:
            df = top_opportunities(top=top, category=category, table_name=table)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_top_opportunities(df, top)


# ---------------------------------------------------------------------------
# top-viral
# ---------------------------------------------------------------------------

@app.command("top-viral")
def cmd_top_viral(
    top:       int            = typer.Option(30,    "--top",       "-n", help="Number of results"),
    price_max: float          = typer.Option(500.0, "--price-max",       help="Max price (default ฿500)"),
    category:  Optional[str]  = typer.Option(None,  "--category",  "-c", help="Filter by category"),
    table:     str            = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Find products best suited for TikTok/Reels content.

    Scores by: item_sold×0.35 + likes×0.35 + discount%×100×0.30
    Filters: price ≤ price_max, sold ≥ 50.

    Example:
        shopee top-viral --price-max 500 --top 30
        shopee top-viral --category Beauty --price-max 300
    """
    from .discovery import top_viral, print_top_viral

    with console.status("[yellow]Finding viral products...[/]"):
        try:
            df = top_viral(top=top, price_max=price_max, category=category, table_name=table)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_top_viral(df, top, price_max)


# ---------------------------------------------------------------------------
# top-niche
# ---------------------------------------------------------------------------

@app.command("top-niche")
def cmd_top_niche(
    top:          int = typer.Option(20,   "--top",          "-n",  help="Number of categories"),
    min_products: int = typer.Option(20,   "--min-products",        help="Min products per category"),
    max_products: int = typer.Option(3000, "--max-products",        help="Max products per category (niche ceiling)"),
    table:        str = typer.Option("products", "--table",  "-t",  help="Table name"),
) -> None:
    """
    Find niche categories: high avg_sales but low product count (market gap signal).

    Example:
        shopee top-niche --top 20
        shopee top-niche --max-products 1000 --top 30
    """
    from .discovery import top_niche, print_top_niche

    with console.status("[yellow]Analyzing niche categories...[/]"):
        try:
            df = top_niche(top=top, min_products=min_products, max_products=max_products, table_name=table)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_top_niche(df, top)


# ---------------------------------------------------------------------------
# daily-picks
# ---------------------------------------------------------------------------

@app.command("daily-picks")
def cmd_daily_picks(
    top:   int = typer.Option(10,        "--top",   "-n", help="Products per category bucket"),
    table: str = typer.Option("products","--table", "-t", help="Table name"),
) -> None:
    """
    Daily product recommendations across 7 content buckets:
    Gadget, Home, Viral TikTok, Mobile Accessories, Mother & Baby, Health, Camping.

    Example:
        shopee daily-picks --top 10
    """
    from .discovery import daily_picks, print_daily_picks

    console.print(
        Panel("[bold green]Daily Picks[/]  — top products per content category", expand=False)
    )
    with console.status("[yellow]Selecting daily picks...[/]"):
        try:
            picks = daily_picks(top=top, table_name=table)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_daily_picks(picks)


# ---------------------------------------------------------------------------
# export-opportunities
# ---------------------------------------------------------------------------

@app.command("export-opportunities")
def cmd_export_opportunities(
    output:   str          = typer.Option("exports/opportunities.csv", "--output", "-o", help="Output CSV path"),
    category: Optional[str] = typer.Option(None,    "--category", "-c", help="Filter by category"),
    keyword:  Optional[str] = typer.Option(None,    "--keyword",  "-k", help="Filter by keyword"),
    top:      int          = typer.Option(100,      "--top",      "-n", help="Max rows to export"),
    table:    str          = typer.Option("products","--table",   "-t", help="Table name"),
) -> None:
    """
    Export top opportunities to CSV (DuckDB COPY TO — no RAM overhead).

    Example:
        shopee export-opportunities --category Face --top 100 --output exports/face_opportunities.csv
        shopee export-opportunities --keyword ลิปสติก --top 200 --output exports/lip.csv
    """
    from .discovery import export_opportunities

    with console.status(f"[yellow]Exporting top {top} opportunities...[/]"):
        try:
            out_path = export_opportunities(
                output=output, category=category, keyword=keyword,
                top=top, table_name=table,
            )
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(f"[bold green]Exported {top} rows →[/] {out_path}")


# ===========================================================================
# Phase 3 — Content Intelligence Engine
# ===========================================================================

def _provider_note(provider: str) -> str:
    if provider == "template":
        return "[dim](template mode — set ANTHROPIC_API_KEY or OPENAI_API_KEY for AI)[/]"
    return f"[dim](AI: {provider})[/]"


# ---------------------------------------------------------------------------
# generate-hook
# ---------------------------------------------------------------------------

@app.command("generate-hook")
def cmd_generate_hook(
    keyword:  str = typer.Argument(..., help="Product keyword to search"),
    provider: str = typer.Option("auto", "--provider", "-p",
                                 help="AI provider: auto | claude | openai | template"),
    table:    str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Generate 10 affiliate hooks (5 types × 2) for a product.

    Types: Viral, Curiosity, Problem/Solution, Review, Before/After

    Example:
        shopee generate-hook "JisuLife"
        shopee generate-hook "ลิปสติก" --provider claude
    """
    from .content_engine import generate_hook, print_hooks, detect_provider

    prov = provider if provider != "auto" else detect_provider()
    with console.status(f"[yellow]Generating hooks via {prov}...[/]"):
        try:
            result = generate_hook(keyword, provider=provider, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_hooks(result)
    console.print(_provider_note(result.get("provider", prov)))


# ---------------------------------------------------------------------------
# generate-caption
# ---------------------------------------------------------------------------

@app.command("generate-caption")
def cmd_generate_caption(
    keyword:  str = typer.Argument(..., help="Product keyword to search"),
    provider: str = typer.Option("auto", "--provider", "-p",
                                 help="AI provider: auto | claude | openai | template"),
    table:    str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Generate 5 TikTok + 3 Facebook + 5 Reels captions.

    Example:
        shopee generate-caption "JisuLife"
        shopee generate-caption "Dr.PONG" --provider openai
    """
    from .content_engine import generate_caption, print_captions, detect_provider

    prov = provider if provider != "auto" else detect_provider()
    with console.status(f"[yellow]Generating captions via {prov}...[/]"):
        try:
            result = generate_caption(keyword, provider=provider, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_captions(result)
    console.print(_provider_note(result.get("provider", prov)))


# ---------------------------------------------------------------------------
# generate-script
# ---------------------------------------------------------------------------

@app.command("generate-script")
def cmd_generate_script(
    keyword:  str = typer.Argument(..., help="Product keyword to search"),
    provider: str = typer.Option("auto", "--provider", "-p",
                                 help="AI provider: auto | claude | openai | template"),
    table:    str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Generate TikTok scripts for 15s, 30s, and 60s.

    Example:
        shopee generate-script "JisuLife"
    """
    from .content_engine import generate_script, print_scripts, detect_provider

    prov = provider if provider != "auto" else detect_provider()
    with console.status(f"[yellow]Generating scripts via {prov}...[/]"):
        try:
            result = generate_script(keyword, provider=provider, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_scripts(result)
    console.print(_provider_note(result.get("provider", prov)))


# ---------------------------------------------------------------------------
# content-pack
# ---------------------------------------------------------------------------

@app.command("content-pack")
def cmd_content_pack(
    keyword:  str = typer.Argument(..., help="Product keyword to search"),
    provider: str = typer.Option("auto", "--provider", "-p",
                                 help="AI provider: auto | claude | openai | template"),
    table:    str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Generate a full content package: hooks + captions + scripts + CTA + hashtags.

    Example:
        shopee content-pack "JisuLife"
        shopee content-pack "Dr.PONG" --provider claude
    """
    from .content_engine import content_pack, print_content_pack, detect_provider

    prov = provider if provider != "auto" else detect_provider()
    with console.status(f"[yellow]Building content pack via {prov}...[/]"):
        try:
            result = content_pack(keyword, provider=provider, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_content_pack(result)
    console.print(_provider_note(result.get("provider", prov)))


# ---------------------------------------------------------------------------
# queue-add
# ---------------------------------------------------------------------------

@app.command("queue-add")
def cmd_queue_add(
    keyword:  str = typer.Argument(..., help="Product keyword — finds best match in DuckDB"),
    provider: str = typer.Option("auto", "--provider", "-p",
                                 help="AI provider: auto | claude | openai | template"),
    table:    str = typer.Option("products", "--table", "-t", help="Table name"),
) -> None:
    """
    Generate a full content pack and save it to the content queue (status: draft).

    Example:
        shopee queue-add "JisuLife"
        shopee queue-add "ลิปสติก" --provider claude
    """
    from .content_engine import queue_add, detect_provider

    prov = provider if provider != "auto" else detect_provider()
    with console.status(f"[yellow]Generating & saving content via {prov}...[/]"):
        try:
            row_id = queue_add(keyword, provider=provider, table_name=table)
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(
        f"[bold green]✓ Saved to queue[/]  ID=[bold]{row_id}[/]  "
        f"keyword=[cyan]{keyword}[/]  status=[yellow]draft[/]  "
        + _provider_note(prov)
    )
    console.print(f"  Approve with: [dim]shopee queue-approve --id {row_id}[/]")


# ---------------------------------------------------------------------------
# queue-list
# ---------------------------------------------------------------------------

@app.command("queue-list")
def cmd_queue_list() -> None:
    """
    Show all items in the content queue.

    Example:
        shopee queue-list
    """
    from .content_engine import queue_list, print_queue

    try:
        df = queue_list()
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    print_queue(df)


# ---------------------------------------------------------------------------
# queue-approve
# ---------------------------------------------------------------------------

@app.command("queue-approve")
def cmd_queue_approve(
    id: int = typer.Option(..., "--id", help="Queue item ID to approve"),
) -> None:
    """
    Change a queue item's status from draft → approved.

    Example:
        shopee queue-approve --id 1
    """
    from .content_engine import queue_approve

    try:
        ok = queue_approve(id)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

    if ok:
        console.print(f"[bold green]✓ Approved[/]  ID={id}  status → [green]approved[/]")
    else:
        console.print(f"[red]ID {id} not found in queue.[/]")
        raise typer.Exit(1)


# ===========================================================================
# Phase 4 — Affiliate Performance Engine
# ===========================================================================

# ---------------------------------------------------------------------------
# import-affiliate-report
# ---------------------------------------------------------------------------

@app.command("import-affiliate-report")
def cmd_import_affiliate_report(
    csv_path: str = typer.Argument(..., help="Path to Shopee Affiliate report CSV"),
) -> None:
    """
    Import a Shopee Affiliate Report CSV (Orders / Click / Commission).
    Auto-detects schema and appends to existing performance data.

    Example:
        shopee import-affiliate-report reports/orders_2024_06.csv
        shopee import-affiliate-report reports/*.csv
    """
    from .performance_engine import import_affiliate_report, print_import_result

    paths = list(Path(".").glob(csv_path)) if "*" in csv_path else [Path(csv_path)]
    if not paths:
        console.print(f"[red]No files matched:[/] {csv_path}")
        raise typer.Exit(1)

    for p in paths:
        with console.status(f"[yellow]Importing {p.name}...[/]"):
            try:
                result = import_affiliate_report(p)
            except FileNotFoundError as e:
                console.print(f"[red]Error:[/] {e}")
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]Import failed:[/] {e}")
                raise typer.Exit(1)
        print_import_result(result)


# ---------------------------------------------------------------------------
# daily-performance
# ---------------------------------------------------------------------------

@app.command("daily-performance")
def cmd_daily_performance(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to show"),
) -> None:
    """
    Show daily affiliate performance: Clicks, Orders, Conv.%, EPC, Revenue, Commission.

    Example:
        shopee daily-performance
        shopee daily-performance --days 14
    """
    from .performance_engine import daily_performance, print_daily_performance

    with console.status("[yellow]Loading daily performance...[/]"):
        try:
            df = daily_performance(days=days)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_daily_performance(df)


# ---------------------------------------------------------------------------
# product-performance
# ---------------------------------------------------------------------------

@app.command("product-performance")
def cmd_product_performance(
    top: int = typer.Option(50, "--top", "-n", help="Number of products to show"),
) -> None:
    """
    Ranked table of Product, Clicks, Orders, Conv.%, EPC, Revenue, Commission.

    Example:
        shopee product-performance --top 50
    """
    from .performance_engine import product_performance, print_product_performance

    with console.status("[yellow]Loading product performance...[/]"):
        try:
            df = product_performance(top=top)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_product_performance(df, top)


# ---------------------------------------------------------------------------
# top-profit-products
# ---------------------------------------------------------------------------

@app.command("top-profit-products")
def cmd_top_profit_products(
    top: int = typer.Option(30, "--top", "-n", help="Number of products to show"),
) -> None:
    """
    Top products ranked by Commission → EPC → Conversion Rate.

    Example:
        shopee top-profit-products
        shopee top-profit-products --top 50
    """
    from .performance_engine import top_profit_products, print_top_profit

    with console.status("[yellow]Ranking profit products...[/]"):
        try:
            df = top_profit_products(top=top)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_top_profit(df, top)


# ---------------------------------------------------------------------------
# merge-product-intelligence
# ---------------------------------------------------------------------------

@app.command("merge-product-intelligence")
def cmd_merge_product_intelligence(
    table: str = typer.Option("products", "--table", "-t", help="Product datafeed table name"),
) -> None:
    """
    Join affiliate performance data with product discovery data.
    Creates 'profit_intelligence' view with profit_score.

    profit_score = commission×0.40 + epc×1000×0.30 + conversion_rate×0.30

    Example:
        shopee merge-product-intelligence
    """
    from .performance_engine import merge_product_intelligence

    with console.status("[yellow]Merging affiliate + discovery data...[/]"):
        try:
            count = merge_product_intelligence(table_name=table)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold green]✓ profit_intelligence view created[/]\n"
            f"  [cyan]{count:,}[/] product records merged\n"
            f"  Use [bold]shopee profit-opportunities[/] to query results",
            title="[bold]Merge Complete[/]",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# profit-opportunities
# ---------------------------------------------------------------------------

@app.command("profit-opportunities")
def cmd_profit_opportunities(
    top:            int           = typer.Option(30,   "--top",            "-n", help="Number of results"),
    min_commission: float         = typer.Option(0.0,  "--min-commission",       help="Minimum total commission (฿)"),
    min_conversion: float         = typer.Option(0.0,  "--min-conversion",       help="Minimum conversion rate (%)"),
    category:       Optional[str] = typer.Option(None, "--category",       "-c", help="Filter by category"),
) -> None:
    """
    Find high commission + good conversion + low competition products.

    Profit Score = commission×0.40 + epc×1000×0.30 + conversion_rate×0.30

    Example:
        shopee profit-opportunities --top 30
        shopee profit-opportunities --min-commission 50 --min-conversion 2
    """
    from .performance_engine import profit_opportunities, print_profit_opportunities

    with console.status("[yellow]Finding profit opportunities...[/]"):
        try:
            df = profit_opportunities(
                top=top,
                min_commission=min_commission,
                min_conversion=min_conversion,
                category=category,
            )
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_profit_opportunities(df, top)


# ===========================================================================
# Phase 5 — Affiliate Operator Command Center
# ===========================================================================

# ---------------------------------------------------------------------------
# morning-brief
# ---------------------------------------------------------------------------

@app.command("morning-brief")
def cmd_morning_brief(
    top:   int = typer.Option(5,         "--top",   "-n", help="Items per section"),
    table: str = typer.Option("products","--table", "-t", help="Product table"),
) -> None:
    """
    Morning briefing: Top Opportunities, Top Viral, Top Niches, Top Profit.

    Example:
        shopee morning-brief
        shopee morning-brief --top 10
    """
    from .operator_center import morning_brief, print_morning_brief

    with console.status("[yellow]Loading morning brief...[/]"):
        try:
            data = morning_brief(table_name=table, top=top)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_morning_brief(data)


# ---------------------------------------------------------------------------
# category-brief
# ---------------------------------------------------------------------------

@app.command("category-brief")
def cmd_category_brief(
    category: str = typer.Option(...,        "--category", "-c", help="Category: Gadget | Health | Baby | Camping | Home | Mobile | Beauty | Fashion"),
    top:      int = typer.Option(20,         "--top",      "-n", help="Number of products"),
    table:    str = typer.Option("products", "--table",    "-t", help="Product table"),
) -> None:
    """
    Top products in a category with opportunity score, profit score, content angle.

    Example:
        shopee category-brief --category Gadget
        shopee category-brief --category Health --top 30
    """
    from .operator_center import category_brief, print_category_brief

    with console.status(f"[yellow]Loading {category} brief...[/]"):
        try:
            data = category_brief(category=category, table_name=table, top=top)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_category_brief(data)


# ---------------------------------------------------------------------------
# trend-watch
# ---------------------------------------------------------------------------

@app.command("trend-watch")
def cmd_trend_watch(
    top:   int = typer.Option(20,         "--top",   "-n", help="Items per signal"),
    table: str = typer.Option("products", "--table", "-t", help="Product table"),
) -> None:
    """
    Find products showing unusual growth signals.

    Signals:
      - Social Momentum — high likes/sold ratio
      - Promo Surge     — high discount + high sales
      - New Viral       — high likes with low sold count

    Example:
        shopee trend-watch
    """
    from .operator_center import trend_watch, print_trend_watch

    with console.status("[yellow]Scanning trends...[/]"):
        try:
            data = trend_watch(table_name=table, top=top)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_trend_watch(data)


# ---------------------------------------------------------------------------
# content-worklist
# ---------------------------------------------------------------------------

@app.command("content-worklist")
def cmd_content_worklist(
    top:   int = typer.Option(20,         "--top",   "-n", help="Number of items"),
    table: str = typer.Option("products", "--table", "-t", help="Product table"),
) -> None:
    """
    Daily content work list: Product, Priority, Suggested Hook, Format, Platform.

    Example:
        shopee content-worklist
        shopee content-worklist --top 30
    """
    from .operator_center import content_worklist, print_content_worklist

    with console.status("[yellow]Building content worklist...[/]"):
        try:
            worklist = content_worklist(table_name=table, top=top)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_content_worklist(worklist)


# ---------------------------------------------------------------------------
# executive-summary
# ---------------------------------------------------------------------------

@app.command("executive-summary")
def cmd_executive_summary(
    table: str = typer.Option("products", "--table", "-t", help="Product table"),
) -> None:
    """
    Full executive summary: Opportunities, Risks, Market Gaps, Viral, Profit.

    Example:
        shopee executive-summary
    """
    from .operator_center import executive_summary, print_executive_summary

    with console.status("[yellow]Generating executive summary...[/]"):
        try:
            data = executive_summary(table_name=table)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    print_executive_summary(data)


# ---------------------------------------------------------------------------
# daily-report
# ---------------------------------------------------------------------------

@app.command("daily-report")
def cmd_daily_report(
    format: str = typer.Option("markdown", "--format", "-f",
                                help="Output format: markdown | html | csv"),
    output: str = typer.Option("exports/reports", "--output", "-o",
                                help="Output directory"),
    table:  str = typer.Option("products", "--table", "-t", help="Product table"),
) -> None:
    """
    Export daily affiliate report to markdown / html / csv.

    Example:
        shopee daily-report --format markdown
        shopee daily-report --format html
        shopee daily-report --format csv --output exports/reports
    """
    from .operator_center import daily_report

    fmt = format.lower()
    if fmt not in ("markdown", "html", "csv"):
        console.print("[red]Invalid format.[/] Use: markdown | html | csv")
        raise typer.Exit(1)

    with console.status(f"[yellow]Generating {fmt} report...[/]"):
        try:
            out_path = daily_report(fmt=fmt, table_name=table, output_dir=output)
        except RuntimeError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(f"[bold green]Report exported →[/] {out_path}")


# ===========================================================================
# Phase 8 — Revenue Feedback Loop Intelligence
# ===========================================================================

@app.command("import-revenue-report")
def cmd_import_revenue_report(
    csv_path: str = typer.Argument(..., help="Path to revenue/commission CSV"),
) -> None:
    """
    Import actual revenue & commission report CSV into DuckDB feedback tables.

    Example:
        shopee import-revenue-report reports/revenue_june.csv
    """
    from .feedback_engine import import_revenue_report, print_import_feedback_result
    paths = list(Path(".").glob(csv_path)) if "*" in csv_path else [Path(csv_path)]
    for p in paths:
        with console.status(f"[yellow]Importing {p.name}...[/]"):
            result = import_revenue_report(p)
        print_import_feedback_result(result)


@app.command("import-click-report")
def cmd_import_click_report(
    csv_path: str = typer.Argument(..., help="Path to click report CSV"),
) -> None:
    """
    Import click-level report CSV.

    Example:
        shopee import-click-report reports/clicks_june.csv
    """
    from .feedback_engine import import_click_report, print_import_feedback_result
    paths = list(Path(".").glob(csv_path)) if "*" in csv_path else [Path(csv_path)]
    for p in paths:
        with console.status(f"[yellow]Importing {p.name}...[/]"):
            result = import_click_report(p)
        print_import_feedback_result(result)


@app.command("import-order-report")
def cmd_import_order_report(
    csv_path: str = typer.Argument(..., help="Path to order report CSV"),
) -> None:
    """
    Import order-level report CSV.

    Example:
        shopee import-order-report reports/orders_june.csv
    """
    from .feedback_engine import import_order_report, print_import_feedback_result
    paths = list(Path(".").glob(csv_path)) if "*" in csv_path else [Path(csv_path)]
    for p in paths:
        with console.status(f"[yellow]Importing {p.name}...[/]"):
            result = import_order_report(p)
        print_import_feedback_result(result)


@app.command("log-predictions")
def cmd_log_predictions(
    top:   int = typer.Option(100,       "--top",   "-n", help="Products to snapshot"),
    table: str = typer.Option("products","--table", "-t", help="Source table"),
) -> None:
    """
    Snapshot current top-N predictions into prediction_log for later comparison.

    Example:
        shopee log-predictions --top 100
    """
    from .feedback_engine import log_predictions
    with console.status("[yellow]Logging predictions...[/]"):
        count = log_predictions(table_name=table, top=top)
    console.print(f"[bold green]Logged[/] {count} predictions → prediction_log")


@app.command("learning-report")
def cmd_learning_report() -> None:
    """
    Compare logged predictions vs actual revenue.
    Shows Product Accuracy, Opportunity Accuracy, Viral Accuracy.

    Example:
        shopee learning-report
    """
    from .feedback_engine import learning_report, print_learning_report
    with console.status("[yellow]Computing learning report...[/]"):
        data = learning_report()
    print_learning_report(data)


@app.command("retrain-rankings")
def cmd_retrain_rankings(
    table:         str   = typer.Option("products", "--table",         "-t", help="Product table"),
    learning_rate: float = typer.Option(0.05,       "--learning-rate", "-l",
                                        help="Weight adjustment rate (default 0.05)"),
) -> None:
    """
    Adapt opportunity score weights based on signal-to-revenue correlations.
    New weights are stored in learning_weights and used by adaptive commands.

    Example:
        shopee retrain-rankings
        shopee retrain-rankings --learning-rate 0.10
    """
    from .feedback_engine import retrain_rankings, print_weight_update
    with console.status("[yellow]Retraining ranking weights...[/]"):
        data = retrain_rankings(table_name=table, learning_rate=learning_rate)
    print_weight_update(data)


@app.command("profit-learning")
def cmd_profit_learning(
    top: int = typer.Option(20, "--top", "-n", help="Top-N predictions to evaluate"),
) -> None:
    """
    Classify prediction quality: True/False Positives and False Negatives.
    Shows Precision, Recall, F1.

    Example:
        shopee profit-learning --top 20
    """
    from .feedback_engine import profit_learning, print_profit_learning
    with console.status("[yellow]Running profit learning analysis...[/]"):
        data = profit_learning(top=top)
    print_profit_learning(data)


@app.command("recommend-next-products")
def cmd_recommend_next_products(
    top:   int = typer.Option(20,        "--top",   "-n", help="Number of recommendations"),
    table: str = typer.Option("products","--table", "-t", help="Source table"),
) -> None:
    """
    Recommend untapped products ranked by learned adaptive weights.
    Excludes products already in revenue_feedback (already promoted).

    Example:
        shopee recommend-next-products --top 20
    """
    from .feedback_engine import recommend_next_products, print_recommendations
    with console.status("[yellow]Computing recommendations...[/]"):
        recs = recommend_next_products(top=top, table_name=table)
    print_recommendations(recs)


@app.command("adaptive-daily-picks")
def cmd_adaptive_daily_picks(
    top:   int = typer.Option(5,         "--top",   "-n", help="Products per bucket"),
    table: str = typer.Option("products","--table", "-t", help="Source table"),
) -> None:
    """
    Daily Picks ranked by LEARNED weights (adapts based on real performance data).
    Falls back to default weights if no retraining has been done yet.

    Example:
        shopee adaptive-daily-picks --top 5
    """
    from .feedback_engine import adaptive_daily_picks, print_adaptive_picks
    with console.status("[yellow]Computing adaptive daily picks...[/]"):
        picks = adaptive_daily_picks(top=top, table_name=table)
    print_adaptive_picks(picks)


if __name__ == "__main__":
    app()
