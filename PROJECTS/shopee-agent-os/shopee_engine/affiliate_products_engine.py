"""Phase 10 — Simple affiliate product registry.

long_url  → identify product (shopid + itemid + title from URL/meta)
short_url → used for posting and earning commission; can be replaced any time
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import duckdb

from .config import config
from .affiliate_link_engine import (
    _connect, _fetch_page_metadata, _match_product_in_db, extract_product_ids,
)

PRODUCTS_TABLE = "affiliate_products"


def _init_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {PRODUCTS_TABLE} (
            id                  INTEGER PRIMARY KEY,
            itemid              BIGINT NOT NULL,
            shopid              BIGINT NOT NULL,
            title               VARCHAR DEFAULT '',
            category            VARCHAR DEFAULT '',
            identification_url  VARCHAR NOT NULL,
            affiliate_short_url VARCHAR DEFAULT '',
            campaign            VARCHAR DEFAULT '',
            platform            VARCHAR DEFAULT '',
            created_at          VARCHAR,
            updated_at          VARCHAR,
            latest_link         BOOLEAN DEFAULT true
        )
    """)


def _title_from_url_slug(url: str) -> str:
    """Extract a human-readable name from the Shopee URL slug.

    https://shopee.co.th/Dr-PONG-28D-i.6583190.6690255925 → "Dr PONG 28D"
    Returns "" if the slug is purely numeric (i.e. /product/SHOPID/ITEMID format).
    """
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    slug = re.sub(r"-i\.\d+\.\d+$", "", slug)
    slug = slug.replace("-", " ").strip()
    return "" if slug.isdigit() else slug


def _lookup_title_from_products(con: duckdb.DuckDBPyConnection, shopid: int, itemid: int) -> str:
    """Look up the real product title from the products table by shopid+itemid."""
    try:
        product = _match_product_in_db(con, shopid, itemid, config.default_table)
        return (product or {}).get("title", "") or ""
    except Exception:
        return ""


def add_affiliate_product(
    long_url:  str,
    short_url: str,
    campaign:  str = "",
    platform:  str = "",
) -> dict:
    """Add or update an affiliate product.

    Returns {success, action, itemid, shopid, title, identification_url,
             affiliate_short_url} or {success=False, error}.
    """
    if not long_url or not short_url:
        return {"success": False, "error": "Both long_url and short_url are required."}

    ids = extract_product_ids(long_url)
    if ids is None:
        return {
            "success": False,
            "error": (
                f"Could not extract shopid/itemid from URL.\n`{long_url[:120]}`\n\n"
                "Expected formats:\n"
                "• `shopee.co.th/name-i.SHOPID.ITEMID`\n"
                "• `shopee.co.th/product/SHOPID/ITEMID`"
            ),
        }
    shopid, itemid = ids

    if not config.db_path.exists():
        return {"success": False, "error": "No database found. Run import-datafeed first."}

    con     = _connect(read_only=False)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        _init_table(con)

        # Title lookup priority:
        # 1. products table (datafeed — most reliable)
        # 2. og:title from page metadata
        # 3. URL slug (only if it's not purely numeric)
        title = _lookup_title_from_products(con, shopid, itemid)
        if not title:
            meta  = _fetch_page_metadata(long_url)
            title = meta.get("title", "") or ""
            title = re.sub(r"\s*[|\-]\s*(Shopee.*)?$", "", title, flags=re.IGNORECASE).strip()
        if not title:
            title = _title_from_url_slug(long_url)

        existing = con.execute(
            f"SELECT id, title FROM {PRODUCTS_TABLE} WHERE itemid=? AND shopid=?",
            [itemid, shopid],
        ).fetchone()

        if existing:
            stored_title = existing[1] or ""
            # Prefer the better title: products table > stored > empty
            final_title = title or stored_title
            con.execute(
                f"UPDATE {PRODUCTS_TABLE} "
                f"SET identification_url=?, affiliate_short_url=?, campaign=?, platform=?, "
                f"    title=?, updated_at=?, latest_link=true "
                f"WHERE itemid=? AND shopid=?",
                [long_url, short_url, campaign, platform, final_title, now_str, itemid, shopid],
            )
            title  = final_title
            action = "updated"
        else:
            max_id = con.execute(f"SELECT COALESCE(MAX(id),0) FROM {PRODUCTS_TABLE}").fetchone()[0]
            con.execute(
                f"INSERT INTO {PRODUCTS_TABLE} "
                f"(id, itemid, shopid, title, category, identification_url, affiliate_short_url, "
                f" campaign, platform, created_at, updated_at, latest_link) "
                f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [max_id + 1, itemid, shopid, title, "", long_url, short_url,
                 campaign, platform, now_str, now_str, True],
            )
            action = "added"

        return {
            "success":            True,
            "action":             action,
            "itemid":             itemid,
            "shopid":             shopid,
            "title":              title,
            "identification_url": long_url,
            "affiliate_short_url": short_url,
        }
    finally:
        con.close()


def update_affiliate_short_url(
    query:         str,
    new_short_url: str,
) -> dict:
    """Replace the short affiliate URL for a product found by keyword or itemid.

    Returns {success, product, old_link, new_link}
    or {success=False, error, candidates?}.
    """
    if not config.db_path.exists():
        return {"success": False, "error": "No database found."}

    con = _connect(read_only=False)
    try:
        _init_table(con)

        q    = query.strip()
        rows = []

        if q.isdigit():
            rows = con.execute(
                f"SELECT id, itemid, shopid, title, affiliate_short_url "
                f"FROM {PRODUCTS_TABLE} WHERE itemid=?",
                [int(q)],
            ).fetchall()

        if not rows:
            rows = con.execute(
                f"SELECT id, itemid, shopid, title, affiliate_short_url "
                f"FROM {PRODUCTS_TABLE} WHERE title ILIKE ? ORDER BY updated_at DESC LIMIT 10",
                [f"%{q}%"],
            ).fetchall()

        if not rows:
            return {"success": False, "error": f"No product found matching `{q[:60]}`"}

        if len(rows) > 1:
            return {
                "success": False,
                "error":   f"{len(rows)} products match `{q[:30]}`. Use itemid to be specific.",
                "candidates": [
                    {"itemid": r[1], "shopid": r[2], "title": r[3], "current_link": r[4] or ""}
                    for r in rows[:5]
                ],
            }

        row_id, itemid, shopid, title, old_link = rows[0]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            f"UPDATE {PRODUCTS_TABLE} SET affiliate_short_url=?, updated_at=? WHERE id=?",
            [new_short_url, now_str, row_id],
        )
        return {
            "success":  True,
            "product":  {"itemid": itemid, "shopid": shopid, "title": title},
            "old_link": old_link or "",
            "new_link": new_short_url,
        }
    finally:
        con.close()


def _table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=?",
        [PRODUCTS_TABLE],
    ).fetchone()[0])


def search_affiliate_products(query: str, limit: int = 10) -> list[dict]:
    """Search by title keyword, itemid, or shopid.

    Returns list of {itemid, shopid, title, category, affiliate_short_url, updated_at}.
    """
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return []
        q = query.strip()
        if q.isdigit():
            rows = con.execute(
                f"SELECT itemid, shopid, title, category, affiliate_short_url, updated_at "
                f"FROM {PRODUCTS_TABLE} WHERE itemid=? OR shopid=? "
                f"ORDER BY updated_at DESC LIMIT ?",
                [int(q), int(q), limit],
            ).fetchall()
        else:
            rows = con.execute(
                f"SELECT itemid, shopid, title, category, affiliate_short_url, updated_at "
                f"FROM {PRODUCTS_TABLE} WHERE title ILIKE ? "
                f"ORDER BY updated_at DESC LIMIT ?",
                [f"%{q}%", limit],
            ).fetchall()
        return [
            {
                "itemid":              r[0],
                "shopid":              r[1],
                "title":               r[2],
                "category":            r[3],
                "affiliate_short_url": r[4],
                "updated_at":          r[5],
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()


def get_all_affiliate_products() -> dict[str, str]:
    """Return {canonical_product_url: affiliate_short_url} for all products with a short URL.

    Used by get_all_affiliate_links() so scheduler jobs pick up new-style products.
    """
    if not config.db_path.exists():
        return {}
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return {}
        rows = con.execute(
            f"SELECT itemid, shopid, affiliate_short_url FROM {PRODUCTS_TABLE} "
            f"WHERE affiliate_short_url IS NOT NULL AND affiliate_short_url != ''",
        ).fetchall()
        return {
            f"https://shopee.co.th/product/{r[1]}/{r[0]}": r[2]
            for r in rows
        }
    except Exception:
        return {}
    finally:
        con.close()
