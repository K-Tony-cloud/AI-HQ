"""Phase 10.5 — Product Asset Library.

Stores product image links from the `products` datafeed into a structured
product_assets table. No external HTTP requests — reads directly from the
existing datafeed columns (image_link, image_link_3 … image_link_10).
"""

from __future__ import annotations

import logging
from datetime import datetime

import duckdb

from .config import config
from .affiliate_link_engine import _connect

logger = logging.getLogger(__name__)

ASSET_TABLE = "product_assets"

# Ordered by preference: primary first, then secondary images.
_IMAGE_COLS = [
    "image_link",
    "image_link_3",
    "image_link_4",
    "image_link_5",
    "image_link_6",
    "image_link_7",
    "image_link_8",
    "image_link_9",
    "image_link_10",
    "additional_image_link",
]


# ── Table ─────────────────────────────────────────────────────────────────────

def _init_asset_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {ASSET_TABLE} (
            itemid       BIGINT NOT NULL,
            shopid       BIGINT NOT NULL,
            title        VARCHAR DEFAULT '',
            image_1      VARCHAR DEFAULT '',
            image_2      VARCHAR DEFAULT '',
            thumbnail    VARCHAR DEFAULT '',
            last_updated VARCHAR
        )
    """)


def _table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=?",
        [ASSET_TABLE],
    ).fetchone()[0])


# ── Core fetch ────────────────────────────────────────────────────────────────

def fetch_and_save_product_assets(itemid: int, shopid: int) -> dict:
    """Read image links from products table, persist to product_assets.

    Returns {"success": bool, "action": "created"|"updated", "image_1": url}
    No HTTP requests — purely reads from the existing datafeed.
    """
    if not config.db_path.exists():
        return {"success": False, "error": "Database not found"}

    con_ro = _connect(read_only=True)
    try:
        # Find which image columns actually exist in this datafeed
        existing_cols_rows = con_ro.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
        ).fetchall()
        existing_cols = {r[0] for r in existing_cols_rows}
        img_cols = [c for c in _IMAGE_COLS if c in existing_cols]

        if not img_cols:
            return {"success": False, "error": "No image columns found in products table"}

        select_expr = ", ".join(f'"{c}"' for c in img_cols)
        row = con_ro.execute(
            f"""SELECT title, {select_expr}
                FROM products
                WHERE TRY_CAST(itemid AS BIGINT) = ? AND TRY_CAST(shopid AS BIGINT) = ?
                LIMIT 1""",
            [itemid, shopid],
        ).fetchone()
    except Exception as exc:
        con_ro.close()
        return {"success": False, "error": f"Products lookup failed: {exc}"}
    finally:
        con_ro.close()

    if not row:
        return {"success": False, "error": "Product not found in products table"}

    title     = str(row[0] or "")
    img_vals  = [str(v) for v in row[1:] if v and str(v).strip()]
    image_1   = img_vals[0] if img_vals else ""
    image_2   = img_vals[1] if len(img_vals) > 1 else ""
    thumbnail = image_1

    con_rw = _connect()
    try:
        _init_asset_table(con_rw)
        now     = datetime.now().isoformat(timespec="seconds")
        exists  = con_rw.execute(
            f"SELECT itemid FROM {ASSET_TABLE} WHERE itemid=? AND shopid=?",
            [itemid, shopid],
        ).fetchone()

        if exists:
            con_rw.execute(
                f"""UPDATE {ASSET_TABLE}
                    SET title=?, image_1=?, image_2=?, thumbnail=?, last_updated=?
                    WHERE itemid=? AND shopid=?""",
                [title, image_1, image_2, thumbnail, now, itemid, shopid],
            )
            action = "updated"
        else:
            con_rw.execute(
                f"INSERT INTO {ASSET_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)",
                [itemid, shopid, title, image_1, image_2, thumbnail, now],
            )
            action = "created"

        return {
            "success":  True,
            "action":   action,
            "image_1":  image_1,
            "image_2":  image_2,
            "thumbnail": thumbnail,
        }
    except Exception as exc:
        return {"success": False, "error": f"Save failed: {exc}"}
    finally:
        con_rw.close()


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_product_assets(itemid: int, shopid: int) -> dict | None:
    if not config.db_path.exists():
        return None
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return None
        row = con.execute(
            f"SELECT itemid, shopid, title, image_1, image_2, thumbnail, last_updated "
            f"FROM {ASSET_TABLE} WHERE itemid=? AND shopid=?",
            [itemid, shopid],
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["itemid", "shopid", "title", "image_1", "image_2", "thumbnail", "last_updated"],
            row,
        ))
    except Exception:
        return None
    finally:
        con.close()


def search_assets_by_keyword(keyword: str) -> list[dict]:
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return []
        rows = con.execute(
            f"""SELECT itemid, shopid, title, image_1, image_2, thumbnail, last_updated
                FROM {ASSET_TABLE}
                WHERE title ILIKE ?
                ORDER BY last_updated DESC LIMIT 5""",
            [f"%{keyword}%"],
        ).fetchall()
        cols = ["itemid", "shopid", "title", "image_1", "image_2", "thumbnail", "last_updated"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def get_asset_status() -> dict:
    """Coverage stats: how many affiliate products have assets saved."""
    if not config.db_path.exists():
        return {"error": "Database not found"}
    con = _connect(read_only=True)
    try:
        # Total in affiliate_products
        aff_total = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='affiliate_products'"
        ).fetchone()[0]
        if not aff_total:
            return {"total_affiliate": 0, "with_assets": 0, "coverage_pct": 0.0, "missing": []}

        total_aff = con.execute(
            "SELECT COUNT(*) FROM affiliate_products WHERE affiliate_short_url IS NOT NULL AND affiliate_short_url != ''"
        ).fetchone()[0] or 0

        if not _table_exists(con):
            return {
                "total_affiliate": total_aff,
                "with_assets":     0,
                "coverage_pct":    0.0,
                "last_updated":    None,
                "missing":         [],
            }

        with_assets = con.execute(
            f"SELECT COUNT(*) FROM {ASSET_TABLE}"
        ).fetchone()[0] or 0

        last_updated = con.execute(
            f"SELECT MAX(last_updated) FROM {ASSET_TABLE}"
        ).fetchone()[0]

        pct = round(with_assets / total_aff * 100, 1) if total_aff else 0.0

        # Products missing assets
        missing_rows = con.execute(f"""
            SELECT ap.itemid, ap.shopid, ap.title
            FROM affiliate_products ap
            LEFT JOIN {ASSET_TABLE} pa ON pa.itemid=ap.itemid AND pa.shopid=ap.shopid
            WHERE ap.affiliate_short_url IS NOT NULL
              AND ap.affiliate_short_url != ''
              AND pa.itemid IS NULL
            LIMIT 10
        """).fetchall()
        missing = [
            {"itemid": r[0], "shopid": r[1], "title": r[2]}
            for r in missing_rows
        ]

        return {
            "total_affiliate": total_aff,
            "with_assets":     with_assets,
            "coverage_pct":    pct,
            "last_updated":    last_updated,
            "missing":         missing,
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        con.close()


def backfill_all_assets() -> dict:
    """Fetch assets for all affiliate_products that don't have assets yet."""
    if not config.db_path.exists():
        return {"success": False, "error": "Database not found"}
    con = _connect(read_only=True)
    try:
        has_ap = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='affiliate_products'"
        ).fetchone()[0]
        if not has_ap:
            return {"success": False, "error": "affiliate_products table not found"}

        rows = con.execute("""
            SELECT ap.itemid, ap.shopid
            FROM affiliate_products ap
            WHERE ap.affiliate_short_url IS NOT NULL AND ap.affiliate_short_url != ''
        """).fetchall()
    except Exception as exc:
        con.close()
        return {"success": False, "error": str(exc)}
    finally:
        con.close()

    created = updated = failed = 0
    for (itemid, shopid) in rows:
        r = fetch_and_save_product_assets(itemid, shopid)
        if not r["success"]:
            failed += 1
        elif r["action"] == "created":
            created += 1
        else:
            updated += 1

    return {"success": True, "created": created, "updated": updated, "failed": failed}
