"""Phase 9 — Manual Affiliate Link Import Workflow.

No Shopee API. No scraping. Human pastes affiliate links from the portal;
this module exports the task list, imports the results, and tracks coverage.
"""

from __future__ import annotations

import csv as csv_mod
import http.client
import http.cookiejar
import logging
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
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
logger = logging.getLogger(__name__)

AFFILIATE_TABLE   = "affiliate_links"
UNMATCHED_TABLE   = "affiliate_links_unmatched"
PENDING_TABLE = "affiliate_links_pending"
AUDIT_TABLE   = "affiliate_link_audit"

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
            notes           VARCHAR DEFAULT '',
            latest_link     BOOLEAN DEFAULT true,
            status          VARCHAR DEFAULT 'matched'
        )
    """)
    # migrate existing table
    con.execute(f"ALTER TABLE {AFFILIATE_TABLE} ADD COLUMN IF NOT EXISTS latest_link BOOLEAN DEFAULT true")
    con.execute(f"ALTER TABLE {AFFILIATE_TABLE} ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'matched'")


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


def _init_unmatched_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {UNMATCHED_TABLE} (
            id            INTEGER PRIMARY KEY,
            created_at    VARCHAR,
            original_link VARCHAR,
            resolved_url  VARCHAR,
            reason        VARCHAR,
            campaign      VARCHAR DEFAULT '',
            platform      VARCHAR DEFAULT '',
            status        VARCHAR DEFAULT 'needs_manual_match'
        )
    """)
    con.execute(f"ALTER TABLE {UNMATCHED_TABLE} ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'needs_manual_match'")


def _init_pending_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {PENDING_TABLE} (
            id               INTEGER PRIMARY KEY,
            session_id       VARCHAR NOT NULL,
            created_at       VARCHAR,
            affiliate_link   VARCHAR,
            resolved_url     VARCHAR DEFAULT '',
            http_status      INTEGER,
            detected_shopid  BIGINT,
            detected_itemid  BIGINT,
            detected_title   VARCHAR DEFAULT '',
            confidence       INTEGER DEFAULT 0,
            confidence_label VARCHAR DEFAULT 'NOT_FOUND',
            existing_link    VARCHAR DEFAULT '',
            campaign         VARCHAR DEFAULT '',
            platform         VARCHAR DEFAULT '',
            status           VARCHAR DEFAULT 'pending'
        )
    """)

def _init_audit_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id              INTEGER PRIMARY KEY,
            session_id      VARCHAR,
            created_at      VARCHAR,
            affiliate_link  VARCHAR,
            detected_shopid BIGINT,
            detected_itemid BIGINT,
            detected_title  VARCHAR DEFAULT '',
            confidence      INTEGER DEFAULT 0,
            confirmed_by    VARCHAR DEFAULT '',
            confirmed_at    VARCHAR DEFAULT '',
            action          VARCHAR
        )
    """)


def _fetch_page_metadata(url: str, timeout: int = 8) -> dict:
    """Fetch first 16KB of a page and extract og:url and og:title / <title>.

    Returns {"og_url": ..., "title": ...} with keys omitted if not found.
    Catches all exceptions silently and returns {}.
    """
    try:
        _ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout)
        conn.request("GET", path, headers={
            "Host": parsed.netloc,
            "User-Agent": _ua,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
        })
        resp = conn.getresponse()
        body = resp.read(16384).decode("utf-8", errors="replace")
        conn.close()

        result: dict = {}

        # og:url — try both attribute orderings
        m = re.search(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']', body)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']', body)
        if m:
            result["og_url"] = m.group(1).strip()

        # og:title
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', body)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', body)
        if m:
            result["title"] = m.group(1).strip()
        else:
            # fallback to <title>
            m = re.search(r'<title[^>]*>([^<]+)</title>', body, re.IGNORECASE)
            if m:
                result["title"] = m.group(1).strip()

        return result
    except Exception:
        return {}


def _identify_product(final_url: str, chain: list[str]) -> dict:
    """Identify a product from its resolved URL + redirect chain.

    Priority:
    1. extract_product_ids(final_url)
    2. Loop reversed(chain[:-1]) → extract_product_ids
    3. _fetch_page_metadata(final_url) → extract_product_ids(og_url)
    4. Return title (or method='none')
    """
    # 1. Direct IDs from final_url
    ids = extract_product_ids(final_url)
    if ids:
        shopid, itemid = ids
        return {"shopid": shopid, "itemid": itemid, "method": "ids", "og_url": None, "title": None}

    # 2. IDs from redirect chain (skip last element which is final_url)
    for hop in reversed(chain[:-1]):
        ids = extract_product_ids(hop)
        if ids:
            shopid, itemid = ids
            return {"shopid": shopid, "itemid": itemid, "method": "ids_from_chain", "og_url": None, "title": None}

    # 3. Fetch page metadata and try og:url
    meta = _fetch_page_metadata(final_url)
    og_url = meta.get("og_url")
    title = meta.get("title")
    if og_url:
        ids = extract_product_ids(og_url)
        if ids:
            shopid, itemid = ids
            return {"shopid": shopid, "itemid": itemid, "method": "og_url", "og_url": og_url, "title": title}

    # 4. Fall back to title
    return {"title": title, "method": "title" if title else "none", "og_url": og_url}


def _fuzzy_match_by_title(
    con: duckdb.DuckDBPyConnection,
    title: str,
    table_name: str,
) -> dict | None:
    """Attempt to match a product by fuzzy title search (ILIKE).

    Strips common Shopee suffix noise, checks title length, then queries.
    Returns product dict or None.
    """
    if not title:
        return None

    # Strip trailing noise
    clean = re.sub(r'\s*[-|]\s*(Shopee Thailand|Shopee)\s*$', '', title, flags=re.IGNORECASE).strip()
    if len(clean) < 5:
        return None

    try:
        cols = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [table_name]
        ).fetchall()]
    except Exception:
        return None

    if not cols:
        return None

    lm = {c.lower(): c for c in cols}
    itemid_col = lm.get("itemid") or lm.get("item_id") or lm.get("product_id")
    shopid_col = lm.get("shopid") or lm.get("shop_id")
    title_col  = lm.get("title") or lm.get("name") or lm.get("product_name")
    pl_col     = lm.get("product_link") or lm.get("product_url") or lm.get("url")

    if not itemid_col or not shopid_col or not title_col:
        return None

    pl_expr = f'COALESCE("{pl_col}", \'\')' if pl_col else "''"

    try:
        row = con.execute(
            f'SELECT CAST("{itemid_col}" AS BIGINT), CAST("{shopid_col}" AS BIGINT), '
            f'"{title_col}", {pl_expr} '
            f'FROM "{table_name}" '
            f'WHERE "{title_col}" ILIKE ? '
            f'LIMIT 1',
            [f"%{clean[:40]}%"]
        ).fetchone()
        if row:
            pl = row[3] or f"https://shopee.co.th/product/{row[1]}/{row[0]}"
            return {"itemid": row[0], "shopid": row[1], "title": row[2], "product_link": pl}
    except Exception:
        pass

    return None


def _confidence_score(identity: dict) -> tuple[int, str]:
    """Return (score 0-100, label) based on how the product was identified."""
    method = identity.get("method", "none")
    if method in ("ids", "ids_from_chain"):
        return 90, "HIGH"
    if method == "og_url":
        return 70, "REVIEW"
    if method == "title":
        return 40, "REVIEW"
    return 0, "NOT_FOUND"


def resolve_shopee_link(url: str, timeout: int = 10) -> tuple[str | None, list[str], int | None]:
    """Resolve a Shopee short link by following HTTP redirects.

    Returns (final_url, chain, http_status).
    final_url is None only on network/connection error.
    HTTP 200 with no redirect means the link serves a SPA — it is VALID
    even if no product IDs can be extracted from it.
    """
    chain: list[str] = [url]
    current = url
    _ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )

    for _ in range(8):
        parsed = urlparse(current)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        try:
            conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout)
            conn.request("GET", path, headers={
                "Host": parsed.netloc,
                "User-Agent": _ua,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
            })
            resp = conn.getresponse()
            status = resp.status
            location = resp.getheader("Location") or ""
            resp.read()  # drain body
            conn.close()
        except Exception as exc:
            logger.debug("[resolve] %s → error: %s", current, exc)
            return None, chain, None

        if status in (301, 302, 303, 307, 308) and location:
            # Resolve relative Location headers
            if location.startswith("/"):
                location = f"{parsed.scheme}://{parsed.netloc}{location}"
            if location not in chain:
                chain.append(location)
            current = location
            continue

        # Non-redirect response — return wherever we landed
        return current, chain, status

    return current, chain, status


def extract_product_ids(url: str) -> tuple[int, int] | None:
    """Extract (shopid, itemid) from a Shopee product URL.

    Handles:
      /product/<shopid>/<itemid>          — canonical product page
      <name>-i.<shopid>.<itemid>          — SEO slug format
      shopee.co.th/<shop_slug>/<shopid>/<itemid>  — affiliate redirect target
    """
    if not url:
        return None
    m = re.search(r'/product/(\d+)/(\d+)', url)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'-i\.(\d+)\.(\d+)', url)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Affiliate redirect format: shopee.co.th/<slug>/<shopid(5+d)>/<itemid(8+d)>
    m = re.search(r'shopee\.co\.th/[^/?#]+/(\d{5,})/(\d{8,})', url)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _match_product_in_db(
    con: duckdb.DuckDBPyConnection,
    shopid: int,
    itemid: int,
    table_name: str,
) -> dict | None:
    """Return product info dict if (shopid, itemid) exists in the products table."""
    try:
        cols = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [table_name]
        ).fetchall()]
    except Exception:
        return None
    if not cols:
        return None

    lm = {c.lower(): c for c in cols}
    itemid_col = lm.get("itemid") or lm.get("item_id") or lm.get("product_id")
    shopid_col = lm.get("shopid") or lm.get("shop_id")
    title_col  = lm.get("title") or lm.get("name") or lm.get("product_name")
    pl_col     = lm.get("product_link") or lm.get("product_url") or lm.get("url")

    if not itemid_col or not shopid_col or not title_col:
        return None

    pl_expr = f'COALESCE("{pl_col}", \'\')' if pl_col else "''"

    try:
        row = con.execute(
            f'SELECT CAST("{itemid_col}" AS BIGINT), CAST("{shopid_col}" AS BIGINT), '
            f'"{title_col}", {pl_expr} '
            f'FROM "{table_name}" '
            f'WHERE CAST("{itemid_col}" AS BIGINT) = ? AND CAST("{shopid_col}" AS BIGINT) = ? '
            f'LIMIT 1',
            [itemid, shopid]
        ).fetchone()
        if row:
            pl = row[3] or f"https://shopee.co.th/product/{row[1]}/{row[0]}"
            return {"itemid": row[0], "shopid": row[1], "title": row[2], "product_link": pl}
    except Exception:
        pass

    # Fallback: match by itemid alone
    try:
        row = con.execute(
            f'SELECT CAST("{itemid_col}" AS BIGINT), CAST("{shopid_col}" AS BIGINT), '
            f'"{title_col}", {pl_expr} '
            f'FROM "{table_name}" '
            f'WHERE CAST("{itemid_col}" AS BIGINT) = ? LIMIT 1',
            [itemid]
        ).fetchone()
        if row:
            pl = row[3] or f"https://shopee.co.th/product/{row[1]}/{row[0]}"
            return {"itemid": row[0], "shopid": row[1], "title": row[2], "product_link": pl}
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Phase 9.2 — Confirm-before-save review flow
# ---------------------------------------------------------------------------

def stage_affiliate_links(
    links:      list[str],
    campaign:   str = "",
    platform:   str = "",
    sub_ids:    tuple[str, str, str, str, str] = ("", "", "", "", ""),
    table_name: str | None = None,
) -> dict:
    """Resolve links and store in pending table for user review. No auto-save.

    Returns session dict:
    {
        session_id: str,
        items: list[dict],  # one per link
        counts: {high, review, not_found, total},
    }
    Each item: {
        id, affiliate_link, resolved_url, http_status,
        shopid, itemid, title, confidence, confidence_label,
        existing_link, status
    }
    """
    import uuid
    table_name  = table_name or config.default_table
    session_id  = str(uuid.uuid4())[:8]
    raw_links   = [lnk.strip() for lnk in links if lnk.strip()]
    if not raw_links:
        return {"session_id": session_id, "items": [], "counts": {"high": 0, "review": 0, "not_found": 0, "total": 0}}

    # Phase 1: resolve concurrently
    resolved: list[tuple[str, str | None, list[str], int | None]] = [("", None, [], None)] * len(raw_links)
    with ThreadPoolExecutor(max_workers=min(10, len(raw_links))) as pool:
        future_map = {pool.submit(resolve_shopee_link, url): i for i, url in enumerate(raw_links)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            final_url, chain, http_status = fut.result()
            resolved[idx] = (raw_links[idx], final_url, chain, http_status)

    # Phase 2: identify and score
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")
    con = _connect(read_only=False)
    _init_affiliate_table(con)
    _init_pending_table(con)
    _init_audit_table(con)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items: list[dict] = []

    try:
        for original, final_url, chain, http_status in resolved:
            logger.info("[stage] 🔗 %s  http=%s", original, http_status)

            # Network error or 4xx/5xx
            if final_url is None or (http_status and http_status >= 400):
                score, label = 0, "NOT_FOUND"
                shopid_val = itemid_val = None
                title_val  = ""
                resolved_url = final_url or ""
            else:
                identity = _identify_product(final_url, chain)
                score, label = _confidence_score(identity)
                shopid_val = identity.get("shopid")
                itemid_val = identity.get("itemid")
                title_val  = ""
                resolved_url = final_url

                if shopid_val and itemid_val:
                    product = _match_product_in_db(con, shopid_val, itemid_val, table_name)
                    if product:
                        title_val = product["title"]
                    else:
                        score, label = 0, "NOT_FOUND"
                        shopid_val = itemid_val = None
                elif identity.get("title"):
                    product = _fuzzy_match_by_title(con, identity["title"], table_name)
                    if product:
                        shopid_val = product["shopid"]
                        itemid_val = product["itemid"]
                        title_val  = product["title"]
                    else:
                        score, label = 0, "NOT_FOUND"

            # Check if product already has an affiliate link
            existing_link = ""
            if shopid_val and itemid_val:
                row = con.execute(
                    f"SELECT affiliate_link FROM {AFFILIATE_TABLE} "
                    f"WHERE itemid = ? AND shopid = ? AND latest_link = true LIMIT 1",
                    [itemid_val, shopid_val],
                ).fetchone()
                if row:
                    existing_link = row[0] or ""

            max_id = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {PENDING_TABLE}").fetchone()[0]
            item_id = max_id + 1
            con.execute(f"""
                INSERT INTO {PENDING_TABLE}
                (id, session_id, created_at, affiliate_link, resolved_url, http_status,
                 detected_shopid, detected_itemid, detected_title,
                 confidence, confidence_label, existing_link, campaign, platform, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                item_id, session_id, now_str,
                original, resolved_url, http_status,
                shopid_val, itemid_val, title_val,
                score, label, existing_link,
                campaign, platform, "pending",
            ])

            items.append({
                "id":               item_id,
                "affiliate_link":   original,
                "resolved_url":     resolved_url,
                "http_status":      http_status,
                "shopid":           shopid_val,
                "itemid":           itemid_val,
                "title":            title_val,
                "confidence":       score,
                "confidence_label": label,
                "existing_link":    existing_link,
                "status":           "pending",
            })
            logger.info("[stage]    %s score=%d title=%s", label, score, title_val[:40] if title_val else "—")

    finally:
        con.close()

    counts = {
        "high":      sum(1 for it in items if it["confidence_label"] == "HIGH"),
        "review":    sum(1 for it in items if it["confidence_label"] == "REVIEW"),
        "not_found": sum(1 for it in items if it["confidence_label"] == "NOT_FOUND"),
        "total":     len(items),
    }
    return {"session_id": session_id, "items": items, "counts": counts}


def confirm_pending_items(
    session_id:   str,
    item_ids:     list[int],
    confirmed_by: str = "discord",
    table_name:   str | None = None,
) -> dict:
    """Save confirmed pending items to affiliate_links and write audit log.

    Returns {saved, updated, errors, saved_items}
    """
    table_name = table_name or config.default_table
    con = _connect(read_only=False)
    _init_affiliate_table(con)
    _init_audit_table(con)

    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved    = 0
    updated  = 0
    errors: list[str] = []
    saved_items: list[dict] = []

    try:
        placeholders = ",".join("?" * len(item_ids))
        rows = con.execute(
            f"SELECT id, affiliate_link, detected_shopid, detected_itemid, "
            f"detected_title, confidence, campaign, platform "
            f"FROM {PENDING_TABLE} "
            f"WHERE session_id = ? AND id IN ({placeholders}) AND status = 'pending'",
            [session_id, *item_ids],
        ).fetchall()

        for row in rows:
            (item_id, affiliate_link, shopid_val, itemid_val,
             title_val, confidence, campaign, platform) = row

            if not shopid_val or not itemid_val:
                errors.append(f"item {item_id}: missing shopid/itemid")
                continue

            canonical = f"https://shopee.co.th/product/{shopid_val}/{itemid_val}"

            # Check if exact affiliate_link already stored
            dup = con.execute(
                f"SELECT id FROM {AFFILIATE_TABLE} WHERE affiliate_link = ?",
                [affiliate_link],
            ).fetchone()
            if dup:
                con.execute(
                    f"UPDATE {PENDING_TABLE} SET status='confirmed' WHERE id=?", [item_id]
                )
                errors.append(f"item {item_id}: exact link already stored")
                continue

            existing_count = con.execute(
                f"SELECT COUNT(*) FROM {AFFILIATE_TABLE} WHERE itemid=? AND shopid=?",
                [itemid_val, shopid_val],
            ).fetchone()[0]

            con.execute(
                f"UPDATE {AFFILIATE_TABLE} SET latest_link=false WHERE itemid=? AND shopid=?",
                [itemid_val, shopid_val],
            )
            max_id = con.execute(f"SELECT COALESCE(MAX(id),0) FROM {AFFILIATE_TABLE}").fetchone()[0]
            con.execute(f"""
                INSERT INTO {AFFILIATE_TABLE}
                (id, created_at, itemid, shopid, product_link, affiliate_link,
                 sub_id1, sub_id2, sub_id3, sub_id4, sub_id5,
                 campaign, platform, notes, latest_link, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                max_id + 1, now_str,
                itemid_val, shopid_val,
                canonical, affiliate_link,
                campaign, platform, "", "", "",
                campaign, platform,
                f"confirmed by {confirmed_by} session={session_id}",
                True, "matched",
            ])

            # Audit
            max_aud = con.execute(f"SELECT COALESCE(MAX(id),0) FROM {AUDIT_TABLE}").fetchone()[0]
            con.execute(f"""
                INSERT INTO {AUDIT_TABLE}
                (id, session_id, created_at, affiliate_link,
                 detected_shopid, detected_itemid, detected_title,
                 confidence, confirmed_by, confirmed_at, action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                max_aud + 1, session_id, now_str, affiliate_link,
                shopid_val, itemid_val, title_val or "",
                confidence, confirmed_by, now_str, "confirmed",
            ])

            con.execute(
                f"UPDATE {PENDING_TABLE} SET status='confirmed' WHERE id=?", [item_id]
            )

            entry = {"title": title_val, "link": affiliate_link, "shopid": shopid_val, "itemid": itemid_val}
            if existing_count > 0:
                updated += 1
            else:
                saved += 1
            saved_items.append(entry)
            logger.info("[confirm] ✅ saved: %s", title_val[:50] if title_val else affiliate_link)

    finally:
        con.close()

    return {"saved": saved, "updated": updated, "errors": errors, "saved_items": saved_items}


def reject_pending_items(
    session_id: str,
    item_ids:   list[int],
    rejected_by: str = "discord",
) -> int:
    """Mark items as rejected in pending table and audit log. Returns count rejected."""
    con = _connect(read_only=False)
    _init_audit_table(con)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    try:
        placeholders = ",".join("?" * len(item_ids))
        rows = con.execute(
            f"SELECT id, affiliate_link, detected_shopid, detected_itemid, detected_title, confidence "
            f"FROM {PENDING_TABLE} "
            f"WHERE session_id=? AND id IN ({placeholders}) AND status='pending'",
            [session_id, *item_ids],
        ).fetchall()
        for row in rows:
            item_id, aff_link, shopid_v, itemid_v, title_v, conf = row
            con.execute(f"UPDATE {PENDING_TABLE} SET status='rejected' WHERE id=?", [item_id])
            max_aud = con.execute(f"SELECT COALESCE(MAX(id),0) FROM {AUDIT_TABLE}").fetchone()[0]
            con.execute(f"""
                INSERT INTO {AUDIT_TABLE}
                (id, session_id, created_at, affiliate_link,
                 detected_shopid, detected_itemid, detected_title,
                 confidence, confirmed_by, confirmed_at, action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [max_aud+1, session_id, now_str, aff_link,
                  shopid_v, itemid_v, title_v or "", conf or 0,
                  rejected_by, now_str, "rejected"])
            count += 1
    finally:
        con.close()
    return count


# ---------------------------------------------------------------------------
# Phase 9.1 — Bulk affiliate link ingestion
# ---------------------------------------------------------------------------

def bulk_add_affiliate_links(
    links:      list[str],
    campaign:   str = "",
    platform:   str = "",
    sub_ids:    tuple[str, str, str, str, str] = ("", "", "", "", ""),
    table_name: str | None = None,
) -> dict:
    """Resolve and bulk-import Shopee affiliate short links.

    The affiliate short link is used as the link-to-store value. Product
    identity is determined by shopid+itemid extracted from the resolved URL
    (or redirect chain / page metadata). Multiple affiliate links per product
    are allowed; a ``latest_link`` flag tracks the newest one.

    Result categories:
    - imported        — first link ever stored for this product
    - updated         — additional link for a product that already has links
    - needs_manual_match — resolved OK but product could not be identified
    - invalid         — network error (final_url is None)
    - duplicate_links — exact same affiliate_link URL already in DB

    Returns a summary dict with counts and per-link details.
    """
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    raw_links = [lnk.strip() for lnk in links if lnk.strip()]
    if not raw_links:
        return {
            "total": 0,
            "imported": 0,
            "updated": 0,
            "needs_manual_match": 0,
            "invalid": 0,
            "duplicate_links": 0,
            "imported_products": [],
            "updated_products": [],
            "unmatched_links": [],
            "invalid_links": [],
            "duplicate_link_urls": [],
        }

    # Phase 1: resolve all links concurrently
    resolved: list[tuple[str, str | None, list[str], int | None]] = [("", None, [], None)] * len(raw_links)
    with ThreadPoolExecutor(max_workers=min(10, len(raw_links))) as pool:
        future_map = {pool.submit(resolve_shopee_link, url): i for i, url in enumerate(raw_links)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            final_url, chain, http_status = fut.result()
            resolved[idx] = (raw_links[idx], final_url, chain, http_status)

    # Phase 2: classify and store
    con = _connect(read_only=False)
    _init_affiliate_table(con)
    _init_unmatched_table(con)

    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s1, s2, s3, s4, s5 = sub_ids

    imported:   list[dict] = []
    updated:    list[dict] = []
    unmatched:  list[dict] = []
    invalid:    list[str]  = []
    dup_links:  list[str]  = []

    try:
        for original, final_url, chain, http_status in resolved:
            logger.info("[affiliate] 🔗 %s", original)

            if final_url is None:
                invalid.append(original)
                logger.info("[affiliate]    ❌ network error (unreachable)")
                continue

            logger.info("[affiliate]    HTTP %s | final: %s", http_status, final_url)
            if len(chain) > 1:
                for hop in chain[1:]:
                    logger.info("[affiliate]    → %s", hop)

            # 4xx/5xx = broken link
            if http_status and http_status >= 400:
                invalid.append(original)
                logger.info("[affiliate]    ❌ HTTP %d — broken", http_status)
                continue

            # Check for exact duplicate affiliate link URL already in DB
            dup_row = con.execute(
                f"SELECT id FROM {AFFILIATE_TABLE} WHERE affiliate_link = ?", [original]
            ).fetchone()
            if dup_row:
                dup_links.append(original)
                logger.info("[affiliate]    ♻️  duplicate link (exact URL already stored)")
                continue

            # Identify the product from the resolved URL / chain / metadata
            identity = _identify_product(final_url, chain)
            shopid = identity.get("shopid")
            itemid = identity.get("itemid")
            product: dict | None = None

            logger.info("[affiliate]    identity: method=%s og_url=%s title=%s",
                        identity.get("method"), identity.get("og_url"), identity.get("title"))

            if shopid is not None and itemid is not None:
                logger.info("[affiliate]    shopid=%d  itemid=%d  (via %s)", shopid, itemid, identity.get("method"))
                product = _match_product_in_db(con, shopid, itemid, table_name)

            if product is None and identity.get("title"):
                product = _fuzzy_match_by_title(con, identity["title"], table_name)

            if product is None:
                status_label = f"HTTP {http_status}" if http_status else "reachable"
                logger.info("[affiliate]    🔍 VALID_NEEDS_MANUAL_MATCH (%s) — product not identified", status_label)
                max_id = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {UNMATCHED_TABLE}").fetchone()[0]
                con.execute(f"""
                    INSERT INTO {UNMATCHED_TABLE}
                    (id, created_at, original_link, resolved_url, reason, campaign, platform, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    max_id + 1, now_str, original, final_url,
                    "product_not_identified", campaign, platform, "needs_manual_match",
                ])
                unmatched.append({
                    "original": original,
                    "resolved": final_url or "",
                    "http_status": http_status,
                    "reason": "product_not_identified",
                    "identity_method": identity.get("method", "none"),
                    "unmatched_id": max_id + 1,
                })
                continue

            logger.info("[affiliate]    ✅ %s", product["title"])

            canonical = f"https://shopee.co.th/product/{product['shopid']}/{product['itemid']}"

            # Count existing links for this product
            existing_count = con.execute(
                f"SELECT COUNT(*) FROM {AFFILIATE_TABLE} WHERE itemid = ? AND shopid = ?",
                [product["itemid"], product["shopid"]],
            ).fetchone()[0]

            # Mark older links as not-latest
            con.execute(
                f"UPDATE {AFFILIATE_TABLE} SET latest_link = false WHERE itemid = ? AND shopid = ?",
                [product["itemid"], product["shopid"]],
            )

            # Insert new row
            max_id = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {AFFILIATE_TABLE}").fetchone()[0]
            con.execute(f"""
                INSERT INTO {AFFILIATE_TABLE}
                (id, created_at, itemid, shopid, product_link, affiliate_link,
                 sub_id1, sub_id2, sub_id3, sub_id4, sub_id5, campaign, platform, notes,
                 latest_link, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                max_id + 1, now_str,
                product["itemid"], product["shopid"],
                canonical, original,
                s1 or campaign, s2 or platform, s3, s4, s5,
                campaign, platform, "",
                True, "matched",
            ])

            entry = {"title": product["title"], "link": original, "product_link": canonical}
            if existing_count > 0:
                updated.append(entry)
                logger.info("[affiliate]    🔄 updated (additional link for product)")
            else:
                imported.append(entry)
                logger.info("[affiliate]    ✅ imported (first link for product)")

    finally:
        con.close()

    return {
        "total":               len(raw_links),
        "imported":            len(imported),
        "updated":             len(updated),
        "needs_manual_match":  len(unmatched),
        "invalid":             len(invalid),
        "duplicate_links":     len(dup_links),
        "imported_products":   imported,
        "updated_products":    updated,
        "unmatched_links":     unmatched,
        "invalid_links":       invalid,
        "duplicate_link_urls": dup_links,
    }


def debug_affiliate_link(url: str) -> dict:
    """Full diagnostic trace for one affiliate link. No DB writes.

    Returns a dict with: original, http_status, reachable, chain, final_url,
    identity_method, shopid, itemid, og_url, page_title, status.
    """
    final_url, chain, http_status = resolve_shopee_link(url)

    reachable = (final_url is not None) and (http_status is None or http_status < 400)
    out = {
        "original":   url,
        "http_status": http_status,
        "reachable":  reachable,
        "chain":      chain,
        "final_url":  final_url,
        "shopid":     None,
        "itemid":     None,
        "og_url":     None,
        "page_title": None,
        "identity_method": "none",
        "status": "INVALID_UNREACHABLE",
    }

    if not reachable:
        if final_url is not None and http_status and http_status >= 400:
            out["status"] = f"INVALID_HTTP_{http_status}"
        return out

    identity = _identify_product(final_url, chain)
    out["identity_method"] = identity.get("method", "none")
    out["shopid"]     = identity.get("shopid")
    out["itemid"]     = identity.get("itemid")
    out["og_url"]     = identity.get("og_url")
    out["page_title"] = identity.get("title")
    out["status"]     = "IDS_FOUND" if identity.get("shopid") else "VALID_NEEDS_MANUAL_MATCH"
    return out


def search_products_by_keyword(
    keyword: str,
    limit: int = 5,
    table_name: str | None = None,
) -> list[dict]:
    """Return up to `limit` products whose title contains `keyword` (ILIKE)."""
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        cols = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [table_name],
        ).fetchall()]
        if not cols:
            return []
        lm = {c.lower(): c for c in cols}
        itemid_col = lm.get("itemid") or lm.get("item_id")
        shopid_col = lm.get("shopid") or lm.get("shop_id")
        title_col  = lm.get("title") or lm.get("name") or lm.get("product_name")
        if not all([itemid_col, shopid_col, title_col]):
            return []
        rows = con.execute(
            f'SELECT CAST("{itemid_col}" AS BIGINT), CAST("{shopid_col}" AS BIGINT), "{title_col}" '
            f'FROM "{table_name}" WHERE "{title_col}" ILIKE ? LIMIT ?',
            [f"%{keyword}%", limit],
        ).fetchall()
        return [
            {
                "itemid": r[0],
                "shopid": r[1],
                "title": r[2],
                "product_link": f"https://shopee.co.th/product/{r[1]}/{r[0]}",
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()


def confirm_affiliate_link(
    unmatched_id: int,
    itemid: int,
    table_name: str | None = None,
) -> dict:
    """Confirm a manual match: associate unmatched link with product by itemid."""
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        return {"success": False, "error": "No database found."}
    con = _connect(read_only=False)
    try:
        row = con.execute(
            f"SELECT original_link, resolved_url, campaign, platform "
            f"FROM {UNMATCHED_TABLE} WHERE id = ?",
            [unmatched_id],
        ).fetchone()
        if not row:
            return {"success": False, "error": f"No unmatched record with id={unmatched_id}"}
        original_link, resolved_url, campaign, platform = row

        product = _match_product_in_db(con, 0, itemid, table_name)  # shopid=0 triggers itemid-only fallback
        if not product:
            return {"success": False, "error": f"No product found with itemid={itemid}"}

        shopid_val = product["shopid"]
        itemid_val = product["itemid"]
        canonical  = f"https://shopee.co.th/product/{shopid_val}/{itemid_val}"
        now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        con.execute(
            f"UPDATE {AFFILIATE_TABLE} SET latest_link = false WHERE itemid = ? AND shopid = ?",
            [itemid_val, shopid_val],
        )
        max_id = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {AFFILIATE_TABLE}").fetchone()[0]
        con.execute(f"""
            INSERT INTO {AFFILIATE_TABLE}
            (id, created_at, itemid, shopid, product_link, affiliate_link,
             sub_id1, sub_id2, sub_id3, sub_id4, sub_id5,
             campaign, platform, notes, latest_link, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            max_id + 1, now_str,
            itemid_val, shopid_val,
            canonical, original_link,
            campaign, platform, "", "", "",
            campaign, platform,
            f"manual confirm: unmatched_id={unmatched_id} itemid={itemid}",
            True, "matched",
        ])
        con.execute(
            f"UPDATE {UNMATCHED_TABLE} SET status = 'matched' WHERE id = ?",
            [unmatched_id],
        )
        return {"success": True, "product": product, "affiliate_link": original_link}
    finally:
        con.close()


def manual_match_affiliate_link(
    unmatched_id: int,
    keyword: str,
    table_name: str | None = None,
) -> dict:
    """Manually match an unmatched affiliate link to a product by keyword or URL.

    Fetches the unmatched record, tries fuzzy title search, and if keyword
    looks like a URL also tries extract_product_ids + _match_product_in_db.
    On success: marks other links for the product as not-latest, inserts the
    new affiliate link row, and marks the unmatched record as 'matched'.
    """
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        return {"success": False, "error": "No database found."}

    con = _connect(read_only=False)
    try:
        row = con.execute(
            f"SELECT id, original_link, resolved_url FROM {UNMATCHED_TABLE} WHERE id = ?",
            [unmatched_id],
        ).fetchone()
        if not row:
            return {"success": False, "error": f"No unmatched record with id={unmatched_id}"}

        _, original_link, resolved_url = row

        product: dict | None = None

        # Try fuzzy title match first
        product = _fuzzy_match_by_title(con, keyword, table_name)

        # If keyword looks like a URL, also try extract_product_ids
        if product is None and ("http://" in keyword or "https://" in keyword):
            ids = extract_product_ids(keyword)
            if ids:
                shopid, itemid = ids
                product = _match_product_in_db(con, shopid, itemid, table_name)

        if product is None:
            return {"success": False, "error": f"No product found matching keyword: {keyword!r}"}

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        canonical = f"https://shopee.co.th/product/{product['shopid']}/{product['itemid']}"

        # Mark existing links for this product as not-latest
        con.execute(
            f"UPDATE {AFFILIATE_TABLE} SET latest_link = false WHERE itemid = ? AND shopid = ?",
            [product["itemid"], product["shopid"]],
        )

        # Insert new affiliate link row
        max_id = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {AFFILIATE_TABLE}").fetchone()[0]
        con.execute(f"""
            INSERT INTO {AFFILIATE_TABLE}
            (id, created_at, itemid, shopid, product_link, affiliate_link,
             sub_id1, sub_id2, sub_id3, sub_id4, sub_id5, campaign, platform, notes,
             latest_link, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            max_id + 1, now_str,
            product["itemid"], product["shopid"],
            canonical, original_link,
            "", "", "", "", "",
            "", "", "",
            True, "matched",
        ])

        # Mark unmatched record as matched
        con.execute(
            f"UPDATE {UNMATCHED_TABLE} SET status = 'matched' WHERE id = ?",
            [unmatched_id],
        )

        return {
            "success": True,
            "product": product,
            "affiliate_link": original_link,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        con.close()


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


def print_bulk_add_result(data: dict) -> None:
    total     = data["total"]
    imported  = data["imported"]
    updated   = data.get("updated", 0)
    unmatched = data.get("needs_manual_match", 0)
    invalid   = data["invalid"]
    dup_links = data.get("duplicate_links", 0)

    color = "green" if imported > 0 else "yellow"
    console.print(Panel(
        f"[bold {color}]✅ Imported  : {imported}[/bold {color}]\n"
        f"Total       : {total}\n"
        f"[cyan]Updated     : {updated}[/cyan]\n"
        f"[yellow]Needs match : {unmatched}[/yellow]\n"
        f"[yellow]Duplicates  : {dup_links}[/yellow]\n"
        f"[red]Invalid     : {invalid}[/red]",
        title="[bold]Bulk Affiliate Link Import[/]",
        expand=False,
    ))

    if data.get("imported_products"):
        tbl = Table(show_lines=False, expand=False)
        tbl.add_column("#",       width=4, style="dim", justify="right")
        tbl.add_column("Product", max_width=55)
        tbl.add_column("Link",    max_width=42)
        for i, p in enumerate(data["imported_products"], 1):
            tbl.add_row(str(i), str(p["title"])[:55], str(p["link"])[:42])
        console.print(tbl)

    if data.get("updated_products"):
        console.print("\n[cyan]🔄 Updated (additional links):[/]")
        for p in data["updated_products"][:5]:
            console.print(f"  [dim]{p['title'][:60]}[/]")

    if data["unmatched_links"]:
        console.print("\n[red]⚠ Needs manual match (saved to affiliate_links_unmatched for review):[/]")
        for u in data["unmatched_links"][:10]:
            console.print(f"  [dim]{u['original'][:60]}[/]  → [red]{u['reason']}[/]")

    if data["invalid_links"]:
        console.print("\n[red]❌ Invalid / unreachable:[/]")
        for lnk in data["invalid_links"][:5]:
            console.print(f"  [dim]{lnk[:60]}[/]")
