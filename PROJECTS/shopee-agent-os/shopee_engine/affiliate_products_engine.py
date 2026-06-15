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


# ---------------------------------------------------------------------------
# Category patterns (matches global_category1 in products table)
# ---------------------------------------------------------------------------

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "beauty":   ["%beauty%"],
    "gadget":   ["%gadget%", "%electronic%"],
    "home":     ["%home%", "%living%"],
    "baby":     ["%baby%", "%mother%"],
    "health":   ["%health%"],
    "fashion":  ["%fashion%", "%cloth%", "%accessories%"],
    "camping":  ["%camping%", "%outdoor%", "%sport%"],
}

_OPP_SCORE = (
    "COALESCE(TRY_CAST(p.item_sold AS DOUBLE),0)*0.40 + "
    "COALESCE(TRY_CAST(p.\"like\" AS DOUBLE),0)*0.15 + "
    "COALESCE(TRY_CAST(p.discount_percentage AS DOUBLE),0)*0.15 + "
    "COALESCE(TRY_CAST(p.shop_rating AS DOUBLE),0)*100*0.15 + "
    "COALESCE(TRY_CAST(p.item_rating AS DOUBLE),0)*100*0.15"
)

_VIRAL_SCORE = (
    "COALESCE(TRY_CAST(p.item_sold AS DOUBLE),0)*0.35 + "
    "COALESCE(TRY_CAST(p.\"like\" AS DOUBLE),0)*0.35 + "
    "COALESCE(TRY_CAST(p.discount_percentage AS DOUBLE),0)*100*0.30"
)


def _has_affiliate_sql(ap_alias: str = "ap", al_alias: str = "al") -> str:
    """SQL expression: true if this product has any usable affiliate link."""
    return (
        f"({ap_alias}.itemid IS NOT NULL AND "
        f" {ap_alias}.affiliate_short_url IS NOT NULL AND "
        f" {ap_alias}.affiliate_short_url != '') "
        f"OR ({al_alias}.itemid IS NOT NULL AND {al_alias}.latest_link = true)"
    )


def _join_affiliates(products_alias: str = "p") -> str:
    """SQL LEFT JOINs to attach affiliate tables to a products query."""
    return (
        f"LEFT JOIN affiliate_products ap "
        f"  ON ap.itemid = TRY_CAST({products_alias}.itemid AS BIGINT) "
        f"  AND ap.shopid = TRY_CAST({products_alias}.shopid AS BIGINT) "
        f"LEFT JOIN affiliate_links al "
        f"  ON al.itemid = TRY_CAST({products_alias}.itemid AS BIGINT) "
        f"  AND al.shopid = TRY_CAST({products_alias}.shopid AS BIGINT) "
    )


# ---------------------------------------------------------------------------
# Part 1 — Fix bad titles
# ---------------------------------------------------------------------------

def fix_bad_titles() -> int:
    """Backfill affiliate_products rows where title is empty or purely numeric.

    Returns the number of rows updated.
    """
    if not config.db_path.exists():
        return 0
    con = _connect(read_only=False)
    try:
        if not _table_exists(con):
            return 0
        rows = con.execute(
            f"SELECT id, itemid, shopid FROM {PRODUCTS_TABLE} "
            f"WHERE title = '' OR TRY_CAST(title AS BIGINT) IS NOT NULL"
        ).fetchall()
        fixed = 0
        for row_id, itemid, shopid in rows:
            title = _lookup_title_from_products(con, shopid, itemid)
            if title and not title.strip().isdigit():
                con.execute(
                    f"UPDATE {PRODUCTS_TABLE} SET title=? WHERE id=?",
                    [title, row_id]
                )
                fixed += 1
        return fixed
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Part 2 — Dashboard stats
# ---------------------------------------------------------------------------

def get_dashboard_stats() -> dict:
    """Summary stats for /affiliate-dashboard.

    Returns {total, with_link, without_link, category_breakdown, recently_added}.
    """
    if not config.db_path.exists():
        return {"total": 0, "with_link": 0, "without_link": 0,
                "category_breakdown": {}, "recently_added": []}
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return {"total": 0, "with_link": 0, "without_link": 0,
                    "category_breakdown": {}, "recently_added": []}

        total = con.execute(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}").fetchone()[0]
        with_link = con.execute(
            f"SELECT COUNT(*) FROM {PRODUCTS_TABLE} "
            f"WHERE affiliate_short_url IS NOT NULL AND affiliate_short_url != ''"
        ).fetchone()[0]

        # Category breakdown — join with products table for real category
        cat_rows = con.execute(f"""
            SELECT
                COALESCE(p.global_category1, 'Unknown') AS cat,
                COUNT(*) AS cnt
            FROM {PRODUCTS_TABLE} ap
            LEFT JOIN products p
                ON TRY_CAST(p.itemid AS BIGINT) = ap.itemid
                AND TRY_CAST(p.shopid AS BIGINT) = ap.shopid
            GROUP BY cat
            ORDER BY cnt DESC
            LIMIT 15
        """).fetchall()
        cat_breakdown: dict[str, int] = {}
        for cat, cnt in cat_rows:
            # Map to friendly bucket
            bucket = "Other"
            cat_lower = (cat or "").lower()
            for name, patterns in CATEGORY_PATTERNS.items():
                if any(pat.strip("%").lower() in cat_lower for pat in patterns):
                    bucket = name.title()
                    break
            cat_breakdown[bucket] = cat_breakdown.get(bucket, 0) + cnt

        # Recently added
        recent_rows = con.execute(f"""
            SELECT itemid, shopid, title, affiliate_short_url, created_at
            FROM {PRODUCTS_TABLE}
            ORDER BY created_at DESC
            LIMIT 10
        """).fetchall()
        recently_added = [
            {"itemid": r[0], "shopid": r[1], "title": r[2],
             "link": r[3], "created_at": (r[4] or "")[:10]}
            for r in recent_rows
        ]

        return {
            "total":              total,
            "with_link":          with_link,
            "without_link":       total - with_link,
            "category_breakdown": cat_breakdown,
            "recently_added":     recently_added,
        }
    except Exception:
        return {"total": 0, "with_link": 0, "without_link": 0,
                "category_breakdown": {}, "recently_added": []}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Part 3 — Missing by section
# ---------------------------------------------------------------------------

def get_missing_by_section(top: int = 20) -> dict:
    """Products in top Opportunities / Viral / Daily Picks without affiliate links.

    Returns {opportunities: [...], viral: [...], daily_picks: {bucket: [...]}}
    Each item: {itemid, shopid, title, category, opp_score}
    """
    if not config.db_path.exists():
        return {"opportunities": [], "viral": [], "daily_picks": {}}
    con = _connect(read_only=True)
    try:
        def _missing_for_score(score_expr: str, extra_where: str = "") -> list[dict]:
            rows = con.execute(f"""
                SELECT
                    TRY_CAST(p.itemid AS BIGINT)       AS itemid,
                    TRY_CAST(p.shopid AS BIGINT)        AS shopid,
                    p.title,
                    COALESCE(p.global_category1, '')    AS category,
                    ROUND({score_expr}, 0)              AS score
                FROM products p
                {_join_affiliates()}
                WHERE COALESCE(p.product_link, '') != ''
                  {extra_where}
                  AND NOT ({_has_affiliate_sql()})
                ORDER BY score DESC
                LIMIT ?
            """, [top]).fetchall()
            return [{"itemid": r[0], "shopid": r[1], "title": r[2],
                     "category": r[3], "score": r[4]} for r in rows]

        opp_missing   = _missing_for_score(_OPP_SCORE)
        viral_missing = _missing_for_score(
            _VIRAL_SCORE,
            "AND COALESCE(TRY_CAST(p.item_sold AS DOUBLE),0) >= 50 "
            "AND COALESCE(TRY_CAST(p.price AS DOUBLE),0) <= 500"
        )

        # Daily Picks by category
        daily_picks: dict[str, list[dict]] = {}
        for bucket, patterns in CATEGORY_PATTERNS.items():
            cat_where = " OR ".join(
                f"p.global_category1 ILIKE '{pat}'" for pat in patterns
            )
            rows = con.execute(f"""
                SELECT
                    TRY_CAST(p.itemid AS BIGINT)       AS itemid,
                    TRY_CAST(p.shopid AS BIGINT)        AS shopid,
                    p.title,
                    COALESCE(p.global_category1, '')    AS category,
                    ROUND({_OPP_SCORE}, 0)              AS score
                FROM products p
                {_join_affiliates()}
                WHERE COALESCE(p.product_link, '') != ''
                  AND ({cat_where})
                  AND NOT ({_has_affiliate_sql()})
                ORDER BY score DESC
                LIMIT 5
            """).fetchall()
            if rows:
                daily_picks[bucket] = [
                    {"itemid": r[0], "shopid": r[1], "title": r[2],
                     "category": r[3], "score": r[4]} for r in rows
                ]

        return {
            "opportunities": opp_missing,
            "viral":         viral_missing,
            "daily_picks":   daily_picks,
        }
    except Exception as exc:
        return {"opportunities": [], "viral": [], "daily_picks": {}, "error": str(exc)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Part 4 — Coverage report
# ---------------------------------------------------------------------------

def get_coverage_report() -> dict:
    """Affiliate link coverage for top 10 / 20 / 50 / 100 products by opp score.

    Returns {tiers: [{n, covered, total, pct}], top100_details: [...]}
    """
    if not config.db_path.exists():
        return {"tiers": [], "top100_details": []}
    con = _connect(read_only=True)
    try:
        rows = con.execute(f"""
            SELECT
                TRY_CAST(p.itemid AS BIGINT)        AS itemid,
                TRY_CAST(p.shopid AS BIGINT)         AS shopid,
                p.title,
                COALESCE(p.global_category1, '')     AS category,
                ROUND({_OPP_SCORE}, 0)               AS score,
                ({_has_affiliate_sql()})              AS has_affiliate,
                COALESCE(ap.affiliate_short_url,
                         al.affiliate_link, '')       AS aff_link
            FROM products p
            {_join_affiliates()}
            WHERE COALESCE(p.product_link, '') != ''
            ORDER BY score DESC
            LIMIT 100
        """).fetchall()

        details = [
            {"itemid": r[0], "shopid": r[1], "title": r[2], "category": r[3],
             "score": r[4], "has_affiliate": bool(r[5]), "aff_link": r[6] or ""}
            for r in rows
        ]

        tiers = []
        for n in (10, 20, 50, 100):
            chunk = details[:n]
            covered = sum(1 for d in chunk if d["has_affiliate"])
            tiers.append({
                "n": n,
                "covered": covered,
                "total": len(chunk),
                "pct": round(covered / len(chunk) * 100, 1) if chunk else 0.0,
            })

        return {"tiers": tiers, "top100_details": details}
    except Exception as exc:
        return {"tiers": [], "top100_details": [], "error": str(exc)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Part 5 — Paginated list
# ---------------------------------------------------------------------------

def list_affiliate_products(
    filter_key: str = "recent",
    page:       int = 0,
    page_size:  int = 8,
) -> dict:
    """Return a paginated slice of affiliate_products.

    filter_key: "recent" | "beauty" | "gadget" | "home" | "baby" |
                "health" | "fashion" | "camping" | "missing" (no short URL)
    Returns {items, page, total_pages, total, filter_key}
    """
    if not config.db_path.exists():
        return {"items": [], "page": 0, "total_pages": 0, "total": 0, "filter_key": filter_key}
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return {"items": [], "page": 0, "total_pages": 0, "total": 0, "filter_key": filter_key}

        base = f"""
            SELECT
                ap.itemid, ap.shopid, ap.title, ap.affiliate_short_url,
                ap.created_at, ap.updated_at,
                COALESCE(p.global_category1, ap.category, '') AS category
            FROM {PRODUCTS_TABLE} ap
            LEFT JOIN products p
                ON TRY_CAST(p.itemid AS BIGINT) = ap.itemid
                AND TRY_CAST(p.shopid AS BIGINT) = ap.shopid
        """

        if filter_key == "missing":
            where = "WHERE (ap.affiliate_short_url IS NULL OR ap.affiliate_short_url = '')"
            order = "ORDER BY ap.created_at DESC"
        elif filter_key in CATEGORY_PATTERNS:
            patterns = CATEGORY_PATTERNS[filter_key]
            cat_cond = " OR ".join(
                f"COALESCE(p.global_category1, '') ILIKE '{pat}'"
                for pat in patterns
            )
            where = f"WHERE ({cat_cond})"
            order = "ORDER BY ap.updated_at DESC"
        else:  # recent
            where = ""
            order = "ORDER BY ap.created_at DESC"

        total = con.execute(
            f"SELECT COUNT(*) FROM ({base} {where}) t"
        ).fetchone()[0]

        offset = page * page_size
        rows = con.execute(
            f"{base} {where} {order} LIMIT ? OFFSET ?",
            [page_size, offset]
        ).fetchall()

        items = [
            {"itemid": r[0], "shopid": r[1], "title": r[2],
             "link": r[3] or "", "created_at": (r[4] or "")[:10],
             "updated_at": (r[5] or "")[:10], "category": r[6]}
            for r in rows
        ]
        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items":       items,
            "page":        page,
            "total_pages": total_pages,
            "total":       total,
            "filter_key":  filter_key,
        }
    except Exception as exc:
        return {"items": [], "page": 0, "total_pages": 0, "total": 0,
                "filter_key": filter_key, "error": str(exc)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Part 6 — Health check
# ---------------------------------------------------------------------------

def get_health_report() -> dict:
    """Check affiliate_products table for data quality issues.

    Returns {health_score, total, issues: [{type, count, examples}]}
    """
    if not config.db_path.exists():
        return {"health_score": 0, "total": 0, "issues": []}
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return {"health_score": 100, "total": 0, "issues": []}

        total = con.execute(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}").fetchone()[0]
        if total == 0:
            return {"health_score": 100, "total": 0, "issues": []}

        issues = []

        # 1. Missing / numeric titles
        bad_title_rows = con.execute(f"""
            SELECT itemid, title FROM {PRODUCTS_TABLE}
            WHERE title = '' OR TRY_CAST(title AS BIGINT) IS NOT NULL
            LIMIT 5
        """).fetchall()
        if bad_title_rows:
            issues.append({
                "type": "missing_title",
                "count": con.execute(
                    f"SELECT COUNT(*) FROM {PRODUCTS_TABLE} "
                    f"WHERE title = '' OR TRY_CAST(title AS BIGINT) IS NOT NULL"
                ).fetchone()[0],
                "label": "Missing or numeric titles",
                "examples": [str(r[0]) for r in bad_title_rows[:3]],
            })

        # 2. Missing short URL
        no_link_count = con.execute(
            f"SELECT COUNT(*) FROM {PRODUCTS_TABLE} "
            f"WHERE affiliate_short_url IS NULL OR affiliate_short_url = ''"
        ).fetchone()[0]
        if no_link_count:
            examples = con.execute(
                f"SELECT title FROM {PRODUCTS_TABLE} "
                f"WHERE affiliate_short_url IS NULL OR affiliate_short_url = '' LIMIT 3"
            ).fetchall()
            issues.append({
                "type": "missing_short_url",
                "count": no_link_count,
                "label": "Missing affiliate short URL",
                "examples": [r[0][:40] for r in examples],
            })

        # 3. Duplicate itemid+shopid
        dup_count = con.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT itemid, shopid FROM {PRODUCTS_TABLE}
                GROUP BY itemid, shopid HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        if dup_count:
            issues.append({
                "type": "duplicate_product",
                "count": dup_count,
                "label": "Duplicate product records (same itemid+shopid)",
                "examples": [],
            })

        # 4. Short URLs that look broken (not starting with http)
        broken_url_count = con.execute(f"""
            SELECT COUNT(*) FROM {PRODUCTS_TABLE}
            WHERE affiliate_short_url IS NOT NULL
              AND affiliate_short_url != ''
              AND affiliate_short_url NOT LIKE 'http%'
        """).fetchone()[0]
        if broken_url_count:
            issues.append({
                "type": "broken_url",
                "count": broken_url_count,
                "label": "Malformed affiliate URLs (missing http)",
                "examples": [],
            })

        bad_count = sum(i["count"] for i in issues)
        health_score = max(0, round((total - bad_count) / total * 100))

        return {
            "health_score": health_score,
            "total":        total,
            "issues":       issues,
        }
    except Exception as exc:
        return {"health_score": 0, "total": 0, "issues": [], "error": str(exc)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Part 7 — Morning brief affiliate validation
# ---------------------------------------------------------------------------

def validate_daily_picks_coverage(picks_data: dict) -> dict:
    """Check how many products in daily_picks data have affiliate links.

    picks_data: the dict returned by daily_picks() service (bucket → list[record])
    Returns {covered, missing, total, missing_items: [{bucket, title, itemid}]}
    """
    if not config.db_path.exists():
        return {"covered": 0, "missing": 0, "total": 0, "missing_items": []}

    all_links = get_all_affiliate_products()
    # Also get old-style links for completeness
    try:
        from .affiliate_link_engine import get_all_affiliate_links
        old_links = get_all_affiliate_links()
    except Exception:
        old_links = {}

    covered = 0
    missing = 0
    missing_items = []

    for bucket, records in picks_data.items():
        for rec in records:
            itemid = rec.get("itemid") or rec.get("item_id")
            shopid = rec.get("shopid") or rec.get("shop_id")
            title  = rec.get("title", "—")
            if not itemid:
                continue
            canonical = f"https://shopee.co.th/product/{shopid}/{itemid}"
            has_link = canonical in all_links or canonical in old_links
            if has_link:
                covered += 1
            else:
                missing += 1
                missing_items.append({
                    "bucket":  bucket,
                    "itemid":  itemid,
                    "shopid":  shopid,
                    "title":   str(title)[:60],
                })

    total = covered + missing
    return {
        "covered":       covered,
        "missing":       missing,
        "total":         total,
        "missing_items": missing_items,
    }


# ---------------------------------------------------------------------------
# Part 8 — Control center quick stats
# ---------------------------------------------------------------------------

def get_control_center_stats() -> dict:
    """Single-call summary for /control-center."""
    if not config.db_path.exists():
        return {}

    dash   = get_dashboard_stats()
    health = get_health_report()

    # Quick coverage (top 10 only — fast)
    con = _connect(read_only=True)
    try:
        top10_rows = con.execute(f"""
            SELECT ({_has_affiliate_sql()}) AS has_aff
            FROM products p
            {_join_affiliates()}
            WHERE COALESCE(p.product_link, '') != ''
            ORDER BY {_OPP_SCORE} DESC
            LIMIT 10
        """).fetchall()
        top10_covered = sum(1 for r in top10_rows if r[0])
        top10_pct = round(top10_covered / len(top10_rows) * 100) if top10_rows else 0
    except Exception:
        top10_pct = 0
    finally:
        con.close()

    # Recent activity (last 3)
    recent = dash.get("recently_added", [])[:3]

    return {
        "total":         dash["total"],
        "with_link":     dash["with_link"],
        "without_link":  dash["without_link"],
        "top10_coverage": top10_pct,
        "health_score":  health["health_score"],
        "recent":        recent,
        "issues":        len(health.get("issues", [])),
    }
