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

# Opportunity score — no table alias (for single-table subqueries)
_OPP_SQL = (
    "COALESCE(TRY_CAST(item_sold AS DOUBLE),0)*0.40 + "
    'COALESCE(TRY_CAST("like" AS DOUBLE),0)*0.15 + '
    "COALESCE(TRY_CAST(discount_percentage AS DOUBLE),0)*0.15 + "
    "COALESCE(TRY_CAST(shop_rating AS DOUBLE),0)*100*0.15 + "
    "COALESCE(TRY_CAST(item_rating AS DOUBLE),0)*100*0.15"
)

# Opportunity score with p. alias (for joined queries)
_OPP_SQL_P = (
    "COALESCE(TRY_CAST(p.item_sold AS DOUBLE),0)*0.40 + "
    'COALESCE(TRY_CAST(p."like" AS DOUBLE),0)*0.15 + '
    "COALESCE(TRY_CAST(p.discount_percentage AS DOUBLE),0)*0.15 + "
    "COALESCE(TRY_CAST(p.shop_rating AS DOUBLE),0)*100*0.15 + "
    "COALESCE(TRY_CAST(p.item_rating AS DOUBLE),0)*100*0.15"
)


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
            asset_status VARCHAR DEFAULT 'ready',
            last_updated VARCHAR
        )
    """)
    # Upgrade existing tables that pre-date the asset_status column
    try:
        con.execute(
            f"ALTER TABLE {ASSET_TABLE} ADD COLUMN IF NOT EXISTS asset_status VARCHAR DEFAULT 'ready'"
        )
    except Exception:
        pass


def _table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=?",
        [ASSET_TABLE],
    ).fetchone()[0])


# ── Core fetch ────────────────────────────────────────────────────────────────

def fetch_and_save_product_assets(itemid: int, shopid: int) -> dict:
    """Read image links from products table and persist to product_assets.

    Returns {"success": bool, "action": "created"|"updated", "image_1": url}
    No HTTP requests — purely reads from the existing datafeed.
    """
    if not config.db_path.exists():
        return {"success": False, "error": "Database not found"}

    con_ro = _connect(read_only=True)
    try:
        existing_cols = {
            r[0] for r in con_ro.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        img_cols = [c for c in _IMAGE_COLS if c in existing_cols]
        if not img_cols:
            return {"success": False, "error": "No image columns in products table"}

        select_expr = ", ".join(f'"{c}"' for c in img_cols)
        row = con_ro.execute(
            f"""SELECT title, {select_expr}
                FROM products
                WHERE TRY_CAST(itemid AS BIGINT) = ?
                  AND TRY_CAST(shopid AS BIGINT) = ?
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

    title    = str(row[0] or "")
    non_empty = [str(v) for v in row[1:] if v and str(v).strip()]
    image_1  = non_empty[0] if non_empty else ""
    image_2  = non_empty[1] if len(non_empty) > 1 else ""
    thumbnail = image_1
    status   = "ready" if image_1 else "no_image"

    con_rw = _connect()
    try:
        _init_asset_table(con_rw)
        now    = datetime.now().isoformat(timespec="seconds")
        exists = con_rw.execute(
            f"SELECT itemid FROM {ASSET_TABLE} WHERE itemid=? AND shopid=?",
            [itemid, shopid],
        ).fetchone()

        if exists:
            con_rw.execute(
                f"""UPDATE {ASSET_TABLE}
                    SET title=?, image_1=?, image_2=?, thumbnail=?,
                        asset_status=?, last_updated=?
                    WHERE itemid=? AND shopid=?""",
                [title, image_1, image_2, thumbnail, status, now, itemid, shopid],
            )
            action = "updated"
        else:
            con_rw.execute(
                f"INSERT INTO {ASSET_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [itemid, shopid, title, image_1, image_2, thumbnail, status, now],
            )
            action = "created"

        return {
            "success":   True,
            "action":    action,
            "image_1":   image_1,
            "image_2":   image_2,
            "thumbnail": thumbnail,
            "status":    status,
        }
    except Exception as exc:
        return {"success": False, "error": f"Save failed: {exc}"}
    finally:
        con_rw.close()


# ── Coverage report ───────────────────────────────────────────────────────────

def get_asset_coverage(top_n_list: list[int] | None = None) -> dict:
    """Coverage at top 20 / 50 / 100 by opportunity score.

    Returns {20: {covered, total, pct}, 50: ..., 100: ...}
    """
    if top_n_list is None:
        top_n_list = [20, 50, 100]
    if not config.db_path.exists():
        return {n: {"covered": 0, "total": n, "pct": 0.0} for n in top_n_list}

    con = _connect(read_only=True)
    try:
        has_assets = _table_exists(con)
        results: dict[int, dict] = {}
        for n in top_n_list:
            if not has_assets:
                results[n] = {"covered": 0, "total": n, "pct": 0.0}
                continue
            rows = con.execute(f"""
                SELECT
                    (pa.itemid IS NOT NULL
                     AND pa.image_1 IS NOT NULL
                     AND pa.image_1 != '') AS has_asset
                FROM (
                    SELECT
                        TRY_CAST(itemid AS BIGINT) AS itemid,
                        TRY_CAST(shopid AS BIGINT) AS shopid
                    FROM products
                    WHERE COALESCE(product_link, '') != ''
                    ORDER BY {_OPP_SQL} DESC
                    LIMIT {n}
                ) t
                LEFT JOIN {ASSET_TABLE} pa
                    ON pa.itemid = t.itemid AND pa.shopid = t.shopid
            """).fetchall()
            total   = len(rows)
            covered = sum(1 for r in rows if r[0])
            pct     = round(covered / total * 100, 1) if total else 0.0
            results[n] = {"covered": covered, "total": total, "pct": pct}
        return results
    except Exception as exc:
        logger.error("get_asset_coverage: %s", exc)
        return {n: {"covered": 0, "total": n, "pct": 0.0} for n in top_n_list}
    finally:
        con.close()


# ── Missing assets ────────────────────────────────────────────────────────────

def get_missing_assets(limit: int = 20) -> list[dict]:
    """Affiliate products sorted by opp score that have no valid image.

    Includes products with no row in product_assets AND products
    with a row but empty image_1 (no_image status).
    """
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        rows = con.execute(f"""
            SELECT
                ap.itemid,
                ap.shopid,
                ap.title,
                ap.affiliate_short_url,
                ROUND({_OPP_SQL_P}, 0)           AS opp_score,
                COALESCE(p.global_category1, '')  AS category,
                CASE
                    WHEN pa.itemid IS NULL THEN 'not_fetched'
                    ELSE 'no_image'
                END AS reason
            FROM affiliate_products ap
            LEFT JOIN products p
                ON TRY_CAST(p.itemid AS BIGINT) = ap.itemid
            LEFT JOIN {ASSET_TABLE} pa
                ON pa.itemid = ap.itemid AND pa.shopid = ap.shopid
                AND pa.image_1 IS NOT NULL AND pa.image_1 != ''
            WHERE ap.affiliate_short_url IS NOT NULL
              AND ap.affiliate_short_url != ''
              AND pa.itemid IS NULL
            ORDER BY opp_score DESC NULLS LAST
            LIMIT ?
        """, [limit]).fetchall()
        cols = ["itemid", "shopid", "title", "affiliate_short_url",
                "opp_score", "category", "reason"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception as exc:
        logger.error("get_missing_assets: %s", exc)
        return []
    finally:
        con.close()


# ── Health report ─────────────────────────────────────────────────────────────

def get_asset_health() -> dict:
    """Full asset library health metrics."""
    if not config.db_path.exists():
        return {"error": "Database not found"}
    con = _connect(read_only=True)
    try:
        # Total affiliate products with short URL
        has_ap = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='affiliate_products'"
        ).fetchone()[0]
        total_affiliate = 0
        if has_ap:
            total_affiliate = con.execute(
                "SELECT COUNT(*) FROM affiliate_products "
                "WHERE affiliate_short_url IS NOT NULL AND affiliate_short_url != ''"
            ).fetchone()[0] or 0

        if not _table_exists(con):
            return {
                "total_affiliate": total_affiliate,
                "in_table":        0,
                "ready":           0,
                "no_image":        0,
                "not_fetched":     total_affiliate,
                "coverage_pct":    0.0,
                "last_updated":    None,
                "recently_fetched": [],
            }

        in_table = con.execute(
            f"SELECT COUNT(*) FROM {ASSET_TABLE}"
        ).fetchone()[0] or 0

        ready = con.execute(
            f"SELECT COUNT(*) FROM {ASSET_TABLE} "
            f"WHERE image_1 IS NOT NULL AND image_1 != '' AND image_1 LIKE 'http%'"
        ).fetchone()[0] or 0

        no_image = in_table - ready
        not_fetched = max(0, total_affiliate - in_table)
        pct = round(ready / total_affiliate * 100, 1) if total_affiliate else 0.0

        last_updated = con.execute(
            f"SELECT MAX(last_updated) FROM {ASSET_TABLE}"
        ).fetchone()[0]

        recent = con.execute(
            f"SELECT title, image_1, last_updated FROM {ASSET_TABLE} "
            f"WHERE image_1 IS NOT NULL AND image_1 != '' "
            f"ORDER BY last_updated DESC LIMIT 5"
        ).fetchall()

        return {
            "total_affiliate": total_affiliate,
            "in_table":        in_table,
            "ready":           ready,
            "no_image":        no_image,
            "not_fetched":     not_fetched,
            "coverage_pct":    pct,
            "last_updated":    last_updated,
            "recently_fetched": [
                {"title": r[0], "image_1": r[1], "last_updated": r[2]}
                for r in recent
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        con.close()


# ── Per-product detail ────────────────────────────────────────────────────────

def get_product_asset_detail(keyword: str) -> dict | None:
    """Return image status for a single product matched by keyword.

    Searches affiliate_products by title, returns asset detail.
    """
    if not config.db_path.exists():
        return None
    con = _connect(read_only=True)
    try:
        # Search affiliate_products by keyword
        ap_row = con.execute(
            "SELECT itemid, shopid, title, affiliate_short_url "
            "FROM affiliate_products WHERE title ILIKE ? "
            "ORDER BY itemid LIMIT 1",
            [f"%{keyword}%"],
        ).fetchone()
        if not ap_row:
            return None

        itemid, shopid, title, short_url = ap_row

        # Check product_assets
        if _table_exists(con):
            pa_row = con.execute(
                f"SELECT image_1, image_2, thumbnail, asset_status, last_updated "
                f"FROM {ASSET_TABLE} WHERE itemid=? AND shopid=?",
                [itemid, shopid],
            ).fetchone()
        else:
            pa_row = None

        if pa_row:
            image_1, image_2, thumbnail, status, last_updated = pa_row
        else:
            image_1 = image_2 = thumbnail = ""
            status = "not_fetched"
            last_updated = None

        return {
            "itemid":       itemid,
            "shopid":       shopid,
            "title":        title or "",
            "short_url":    short_url or "",
            "image_1":      image_1 or "",
            "image_2":      image_2 or "",
            "thumbnail":    thumbnail or "",
            "asset_status": status or "not_fetched",
            "last_updated": last_updated,
            "asset_ready":  bool(image_1 and str(image_1).startswith("http")),
        }
    except Exception as exc:
        logger.error("get_product_asset_detail: %s", exc)
        return None
    finally:
        con.close()


# ── Convenience ───────────────────────────────────────────────────────────────

def get_product_assets(itemid: int, shopid: int) -> dict | None:
    if not config.db_path.exists():
        return None
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return None
        row = con.execute(
            f"SELECT itemid, shopid, title, image_1, image_2, thumbnail, "
            f"asset_status, last_updated "
            f"FROM {ASSET_TABLE} WHERE itemid=? AND shopid=?",
            [itemid, shopid],
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["itemid", "shopid", "title", "image_1", "image_2",
             "thumbnail", "asset_status", "last_updated"],
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
            f"""SELECT itemid, shopid, title, image_1, image_2, thumbnail,
                       asset_status, last_updated
                FROM {ASSET_TABLE}
                WHERE title ILIKE ?
                ORDER BY last_updated DESC LIMIT 5""",
            [f"%{keyword}%"],
        ).fetchall()
        cols = ["itemid", "shopid", "title", "image_1", "image_2",
                "thumbnail", "asset_status", "last_updated"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def get_asset_status() -> dict:
    """Overall coverage stats used by /asset-status (no keyword)."""
    if not config.db_path.exists():
        return {"error": "Database not found"}
    return get_asset_health()


def backfill_all_assets() -> dict:
    """Fetch assets for all affiliate_products."""
    if not config.db_path.exists():
        return {"success": False, "error": "Database not found"}
    con = _connect(read_only=True)
    try:
        has_ap = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='affiliate_products'"
        ).fetchone()[0]
        if not has_ap:
            return {"success": False, "error": "affiliate_products table not found"}
        rows = con.execute(
            "SELECT itemid, shopid FROM affiliate_products "
            "WHERE affiliate_short_url IS NOT NULL AND affiliate_short_url != ''"
        ).fetchall()
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
