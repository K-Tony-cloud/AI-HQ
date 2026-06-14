"""Phase 9 — Manual Affiliate Link Import Workflow.

No Shopee API. No scraping. Human pastes affiliate links from the portal;
this module exports the task list, imports the results, and tracks coverage.
"""

from __future__ import annotations

import csv as csv_mod
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import duckdb
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .config import config

console = Console()

AFFILIATE_TABLE = "affiliate_links"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    if not config.db_path.exists() and read_only:
        raise RuntimeError("No database found. Run import-datafeed first.")
    return duckdb.connect(str(config.db_path), read_only=read_only)


def _init_affiliate_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {AFFILIATE_TABLE} (
            id              INTEGER PRIMARY KEY,
            created_at      VARCHAR,
            itemid          BIGINT,
            shopid          BIGINT,
            product_link    VARCHAR,
            affiliate_link  VARCHAR,
            sub_id1         VARCHAR DEFAULT '',
            sub_id2         VARCHAR DEFAULT '',
            sub_id3         VARCHAR DEFAULT '',
            sub_id4         VARCHAR DEFAULT '',
            sub_id5         VARCHAR DEFAULT '',
            campaign        VARCHAR DEFAULT '',
            platform        VARCHAR DEFAULT '',
            notes           VARCHAR DEFAULT ''
        )
    """)


def _has_table(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [AFFILIATE_TABLE],
    ).fetchone()[0])


def _normalize_link(url: str) -> str:
    """Reduce any Shopee link form to the canonical product URL."""
    if not url:
        return url
    if "an_redir" in url:
        qs = parse_qs(urlparse(url).query)
        origin = qs.get("origin_link", [""])[0]
        return unquote(origin)
    # Strip query params so plain product URLs also normalize cleanly
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


# ---------------------------------------------------------------------------
# 1. export-link-tasks
# ---------------------------------------------------------------------------

def export_link_tasks(
    top:        int = 50,
    campaign:   str = "daily-picks",
    platform:   str = "tiktok",
    table_name: str | None = None,
) -> dict:
    """Export top products to CSV for manual affiliate link generation in the portal."""
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = _connect(read_only=True)
    try:
        cols = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [table_name]
        ).fetchall()]
        lm = {c.lower(): c for c in cols}

        def g(key: str) -> str:
            return lm.get(key, key)

        title_c    = g("title")
        itemid_c   = g("itemid")
        shopid_c   = g("shopid")
        pl_c       = g("product_link")
        sold_c     = g("item_sold")
        likes_c    = g("like")
        disc_c     = g("discount_percentage")
        shop_r_c   = g("shop_rating")
        item_r_c   = g("item_rating")
        cat_c      = g("global_category1")

        score_expr = (
            f'ROUND(COALESCE(TRY_CAST("{sold_c}" AS DOUBLE),0)*0.40 + '
            f'COALESCE(TRY_CAST("{likes_c}" AS DOUBLE),0)*0.15 + '
            f'COALESCE(TRY_CAST("{disc_c}" AS DOUBLE),0)*100.0*0.15 + '
            f'(COALESCE(TRY_CAST("{shop_r_c}" AS DOUBLE),0) + '
            f'COALESCE(TRY_CAST("{item_r_c}" AS DOUBLE),0))*0.15, 2)'
        )

        rows = con.execute(f"""
            SELECT
                CAST("{itemid_c}" AS VARCHAR)        AS product_id,
                CAST("{itemid_c}" AS BIGINT)         AS itemid,
                CAST("{shopid_c}" AS BIGINT)         AS shopid,
                "{title_c}"                          AS title,
                COALESCE("{pl_c}", '')               AS product_link,
                COALESCE(TRY_CAST("{cat_c}" AS VARCHAR), '') AS category,
                {score_expr}                         AS opportunity_score
            FROM "{table_name}"
            WHERE COALESCE("{pl_c}", '') != ''
            ORDER BY opportunity_score DESC
            LIMIT {top}
        """).fetchall()
    finally:
        con.close()

    if not rows:
        return {"rows_exported": 0, "path": None, "warning": "No products with product_link found."}

    out_dir = config.data_dir.parent / "exports" / "link-tasks"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{campaign}-{platform}.csv"
    out_path = out_dir / filename

    fieldnames = [
        "product_id", "itemid", "shopid", "title", "product_link",
        "category", "opportunity_score",
        "affiliate_link",
        "sub_id1", "sub_id2", "sub_id3", "sub_id4", "sub_id5",
        "campaign", "platform",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv_mod.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "product_id":        r[0],
                "itemid":            r[1],
                "shopid":            r[2],
                "title":             r[3],
                "product_link":      r[4],
                "category":          r[5],
                "opportunity_score": r[6],
                "affiliate_link":    "",
                "sub_id1":           campaign,
                "sub_id2":           platform,
                "sub_id3":           "",
                "sub_id4":           "",
                "sub_id5":           "",
                "campaign":          campaign,
                "platform":          platform,
            })

    return {"rows_exported": len(rows), "path": str(out_path), "campaign": campaign, "platform": platform}


# ---------------------------------------------------------------------------
# 2. import-affiliate-links
# ---------------------------------------------------------------------------

def import_affiliate_links(csv_path: str | Path) -> dict:
    """Import affiliate links from a CSV that the user filled in from the Shopee portal."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8-sig") as fh:
        reader = csv_mod.DictReader(fh)
        rows = list(reader)

    if not rows:
        return {"imported": 0, "skipped": 0, "errors": [], "warning": "CSV is empty."}

    # Required column
    pl_key  = next((k for k in rows[0] if "product_link" in k.lower() and "affiliate" not in k.lower()), None)
    aff_key = next((k for k in rows[0] if "affiliate_link" in k.lower()), None)
    if not pl_key or not aff_key:
        raise ValueError(
            f"CSV must have 'product_link' and 'affiliate_link' columns. "
            f"Found: {list(rows[0].keys())}"
        )

    def _g(row: dict, key: str, default: str = "") -> str:
        return str(row.get(key, default) or default).strip()

    con = _connect(read_only=False)
    _init_affiliate_table(con)

    imported = 0
    skipped  = 0
    errors: list[str] = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, row in enumerate(rows, 1):
        pl  = _g(row, pl_key)
        aff = _g(row, aff_key)
        if not pl or not aff:
            skipped += 1
            continue

        norm_pl = _normalize_link(pl)

        # Try to resolve itemid/shopid from products table
        itemid: int | None = None
        shopid: int | None = None
        try:
            raw_itemid = _g(row, "itemid") or _g(row, "product_id")
            raw_shopid = _g(row, "shopid")
            if raw_itemid:
                itemid = int(raw_itemid)
            if raw_shopid:
                shopid = int(raw_shopid)
        except (ValueError, TypeError):
            pass

        sub1 = _g(row, "sub_id1")
        sub2 = _g(row, "sub_id2")
        sub3 = _g(row, "sub_id3")
        sub4 = _g(row, "sub_id4")
        sub5 = _g(row, "sub_id5")
        campaign = _g(row, "campaign")
        platform = _g(row, "platform")

        try:
            # Remove existing entry for same product_link (upsert by replace)
            con.execute(
                f"DELETE FROM {AFFILIATE_TABLE} WHERE product_link = ?", [norm_pl]
            )
            max_id = con.execute(
                f"SELECT COALESCE(MAX(id), 0) FROM {AFFILIATE_TABLE}"
            ).fetchone()[0]
            con.execute(f"""
                INSERT INTO {AFFILIATE_TABLE}
                (id, created_at, itemid, shopid, product_link, affiliate_link,
                 sub_id1, sub_id2, sub_id3, sub_id4, sub_id5, campaign, platform, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                max_id + 1, now_str, itemid, shopid, norm_pl, aff,
                sub1, sub2, sub3, sub4, sub5, campaign, platform, "",
            ])
            imported += 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    con.close()
    return {"imported": imported, "skipped": skipped, "errors": errors, "path": str(csv_path)}


# ---------------------------------------------------------------------------
# 3. link-coverage-report
# ---------------------------------------------------------------------------

def link_coverage_report(
    top:        int = 50,
    table_name: str | None = None,
) -> dict:
    """Show how many top products have affiliate links vs. missing."""
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = _connect(read_only=True)
    try:
        has_aff = _has_table(con)

        cols = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [table_name]
        ).fetchall()]
        lm = {c.lower(): c for c in cols}

        def g(key: str) -> str:
            return lm.get(key, key)

        title_c  = g("title")
        pl_c     = g("product_link")
        sold_c   = g("item_sold")
        likes_c  = g("like")
        disc_c   = g("discount_percentage")
        shop_r_c = g("shop_rating")
        item_r_c = g("item_rating")
        cat_c    = g("global_category1")

        score_expr = (
            f'ROUND(COALESCE(TRY_CAST("{sold_c}" AS DOUBLE),0)*0.40 + '
            f'COALESCE(TRY_CAST("{likes_c}" AS DOUBLE),0)*0.15 + '
            f'COALESCE(TRY_CAST("{disc_c}" AS DOUBLE),0)*100.0*0.15 + '
            f'(COALESCE(TRY_CAST("{shop_r_c}" AS DOUBLE),0) + '
            f'COALESCE(TRY_CAST("{item_r_c}" AS DOUBLE),0))*0.15, 2)'
        )

        products = con.execute(f"""
            SELECT
                "{title_c}"                           AS title,
                COALESCE("{pl_c}", '')                AS product_link,
                COALESCE(TRY_CAST("{cat_c}" AS VARCHAR), '') AS category,
                {score_expr}                          AS opp_score
            FROM "{table_name}"
            WHERE COALESCE("{pl_c}", '') != ''
            ORDER BY opp_score DESC
            LIMIT {top}
        """).fetchall()

        if not has_aff:
            details = [
                {"title": r[0], "product_link": r[1], "category": r[2],
                 "opp_score": r[3], "affiliate_link": None, "covered": False}
                for r in products
            ]
        else:
            aff_map = {
                row[0]: row[1]
                for row in con.execute(
                    f"SELECT product_link, affiliate_link FROM {AFFILIATE_TABLE}"
                ).fetchall()
            }
            details = []
            for r in products:
                norm = _normalize_link(r[1])
                aff  = aff_map.get(norm) or aff_map.get(r[1])
                details.append({
                    "title":          r[0],
                    "product_link":   r[1],
                    "category":       r[2],
                    "opp_score":      r[3],
                    "affiliate_link": aff,
                    "covered":        bool(aff),
                })
    finally:
        con.close()

    total    = len(details)
    covered  = sum(1 for d in details if d["covered"])
    missing  = total - covered
    pct      = round(covered / total * 100, 1) if total else 0.0

    return {
        "total":    total,
        "covered":  covered,
        "missing":  missing,
        "coverage": pct,
        "details":  details,
    }


# ---------------------------------------------------------------------------
# 4. Lookup helpers (used by discovery and content_engine)
# ---------------------------------------------------------------------------

def get_all_affiliate_links() -> dict[str, str]:
    """Return {normalized_product_link: affiliate_link} for all stored links."""
    if not config.db_path.exists():
        return {}
    try:
        con = _connect(read_only=True)
        if not _has_table(con):
            con.close()
            return {}
        rows = con.execute(
            f"SELECT product_link, affiliate_link FROM {AFFILIATE_TABLE} "
            f"WHERE affiliate_link IS NOT NULL AND affiliate_link != ''"
        ).fetchall()
        con.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def get_affiliate_link(product_link_or_short: str) -> str | None:
    """Return affiliate_link for a product URL, or None if not found."""
    aff_map = get_all_affiliate_links()
    norm = _normalize_link(product_link_or_short)
    return aff_map.get(norm) or aff_map.get(product_link_or_short)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_export_result(data: dict) -> None:
    if not data.get("path"):
        console.print(f"[yellow]⚠ {data.get('warning', 'Nothing exported.')}[/]")
        return
    console.print(Panel(
        f"[bold green]✅ Exported {data['rows_exported']} products[/]\n"
        f"Campaign : [cyan]{data['campaign']}[/]\n"
        f"Platform : [cyan]{data['platform']}[/]\n"
        f"File     : [dim]{data['path']}[/]\n\n"
        f"[bold]Next steps:[/]\n"
        f"  1. Open the CSV in Excel/Sheets\n"
        f"  2. For each row, go to [cyan]affiliate.shopee.co.th[/] → Create Link\n"
        f"  3. Paste [cyan]product_link[/] → generate → copy the short link\n"
        f"  4. Paste into the [cyan]affiliate_link[/] column\n"
        f"  5. Run: [bold]shopee import-affiliate-links <file>[/]",
        title="[bold]Link Task Export[/]",
        expand=False,
    ))


def print_import_result(data: dict) -> None:
    errors = data.get("errors", [])
    console.print(Panel(
        f"[bold green]Imported :[/] {data['imported']}\n"
        f"[yellow]Skipped  :[/] {data['skipped']}  (empty affiliate_link)\n"
        f"[red]Errors   :[/] {len(errors)}\n"
        + (("\n" + "\n".join(f"  [red]{e}[/]" for e in errors[:5])) if errors else ""),
        title=f"[bold]Import — {data.get('path', '')}[/]",
        expand=False,
    ))


def print_link_coverage(data: dict) -> None:
    total   = data["total"]
    covered = data["covered"]
    missing = data["missing"]
    pct     = data["coverage"]

    bar_filled = int(pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    color = "green" if pct >= 80 else "yellow" if pct >= 40 else "red"

    console.print(Panel(
        f"[bold]Coverage: [{color}]{pct}%[/]  [{color}]{bar}[/][/bold]\n"
        f"Total top products : {total}\n"
        f"[green]With affiliate link[/] : {covered}\n"
        f"[red]Missing            [/] : {missing}",
        title="[bold]Affiliate Link Coverage[/]",
        expand=False,
    ))

    if not data["details"]:
        return

    tbl = Table(show_lines=True, expand=True)
    tbl.add_column("#",        width=4, justify="right", style="dim")
    tbl.add_column("Title",    max_width=50)
    tbl.add_column("Category", max_width=22)
    tbl.add_column("Score",    width=10, justify="right")
    tbl.add_column("Link",     max_width=50)

    for i, d in enumerate(data["details"], 1):
        link_cell = (
            f"[green]{d['affiliate_link'][:45]}[/]"
            if d["covered"]
            else "[red]⚠ Needs affiliate link[/]"
        )
        tbl.add_row(
            str(i),
            str(d["title"])[:50],
            str(d["category"])[:22],
            f"{d['opp_score']:,.0f}",
            link_cell,
        )

    console.print(tbl)
