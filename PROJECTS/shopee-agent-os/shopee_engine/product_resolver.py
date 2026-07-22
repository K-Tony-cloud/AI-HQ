"""Central product resolver — pure functions, no Discord dependency.

Resolves a product reference (itemid, Shopee URL, keyword) to a canonical
structured result. All callers (/seo-preview, /product-lookup, etc.) share
this module so lookup logic is never duplicated.
"""

from __future__ import annotations

import re
from typing import Any

_SHOPEE_PRODUCT_DOMAINS = frozenset(["shopee.co.th", "www.shopee.co.th"])
_SHOPEE_SHORT_DOMAINS   = frozenset(["shope.ee", "s.shopee.co.th"])

# /product/{shopid}/{itemid} path
_PRODUCT_PATH_RE  = re.compile(r"/product/(\d+)/(\d+)")
# name-i.{shopid}.{itemid} slug (Shopee i-dot format)
_I_DOT_RE         = re.compile(r"-i\.(\d+)\.(\d+)(?:[/?]|$)")
# origin_link=https://shopee.co.th/product/SHOPID/ITEMID  (datafeed redirect)
_ORIGIN_LINK_RE   = re.compile(r"shopee\.co\.th/product/(\d+)/(\d+)")

ALLOWED_SHOPEE_HOSTS = _SHOPEE_PRODUCT_DOMAINS | _SHOPEE_SHORT_DOMAINS

_RESOLUTION_FIELDS = (
    "resolution_status", "itemid", "shopid", "title", "shop_name",
    "price", "image_url", "source_product_url", "direct_product_url",
    "affiliate_link", "affiliate_status", "source_table", "reason",
    "confidence_score", "confidence_level", "confidence_factors",
)


def _make_result(**kwargs: Any) -> dict:
    base: dict = {k: None for k in _RESOLUTION_FIELDS}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Pure classification + URL parsing
# ---------------------------------------------------------------------------

def classify_reference(ref: str) -> str:
    """Return 'itemid' | 'shopee_url' | 'short_url' | 'keyword'.

    Numeric-only strings are always treated as itemid, never as keywords.
    """
    ref = ref.strip()
    if not ref:
        return "keyword"
    if ref.isdigit():
        return "itemid"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(ref)
        host   = parsed.netloc.lstrip("www.").lower()
        if host in _SHOPEE_PRODUCT_DOMAINS:
            return "shopee_url"
        if host in _SHOPEE_SHORT_DOMAINS:
            return "short_url"
    except Exception:
        pass
    return "keyword"


def extract_shopee_ids_from_url(url: str) -> tuple[int, int] | None:
    """Parse (shopid, itemid) from a Shopee URL.

    Supports:
      /product/{shopid}/{itemid}
      name-i.{shopid}.{itemid}
      ?origin_link=.../product/{shopid}/{itemid}   (datafeed shope.ee format)
    Returns None if the URL is not parseable.
    """
    if not url:
        return None
    m = _ORIGIN_LINK_RE.search(url)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _PRODUCT_PATH_RE.search(url)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _I_DOT_RE.search(url)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def build_direct_url(
    shopid: int,
    itemid: int,
    product_link: str | None = None,
) -> tuple[str, str]:
    """Return (url, source_label) for a product.

    Priority:
      1. product_link from datafeed if it parses to matching shopid+itemid
      2. Canonical fallback https://shopee.co.th/product/{shopid}/{itemid}
      3. ("", "unavailable") when shopid or itemid is 0/missing
    """
    if not shopid or not itemid:
        return "", "unavailable"
    canonical = f"https://shopee.co.th/product/{shopid}/{itemid}"
    if product_link:
        ids = extract_shopee_ids_from_url(product_link)
        if ids and ids[0] == shopid and ids[1] == itemid:
            return canonical, "datafeed"
    return canonical, "constructed"


def validate_shopee_url(url: str) -> str | None:
    """Return an error description if url is not a valid Shopee product URL, else None."""
    if not url:
        return "URL ว่างเปล่า"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.lstrip("www.").lower()
        if host not in ALLOWED_SHOPEE_HOSTS:
            return f"domain '{host}' ไม่ใช่ Shopee domain ที่อนุญาต"
    except Exception as exc:
        return f"malformed URL: {exc}"
    return None


# ---------------------------------------------------------------------------
# Resolution confidence scoring
# ---------------------------------------------------------------------------

def _compute_resolution_score(
    *,
    ref_type: str,
    shopid_provided: bool,
    ambiguous_resolved: bool,
    url_source: str,
    has_title: bool,
    has_image: bool,
) -> dict:
    """Return {score, level, factors} for a successfully resolved product.

    Score ranges: high ≥ 0.90 | medium ≥ 0.75 | low ≥ 0.50

    Factors (additive):
      - ref_type=='shopee_url'          → 0.90 base (IDs extracted from URL)
      - ref_type=='itemid' + shopid     → 0.85 base (itemid+shopid exact match)
      - ref_type=='itemid', no shopid   → 0.80 base (itemid unique, no shopid)
      - ambiguous_resolved via shopid   → 0.70 base (one of N candidates)
      - url_source=='datafeed'          → +0.05 (datafeed confirms URL)
      - has_title                       → +0.03
      - has_image                       → +0.02
    """
    if ambiguous_resolved:
        base = 0.70
        factors = ["itemid พบหลายร้าน — resolved ด้วย shopid ที่ระบุ"]
    elif ref_type == "shopee_url":
        base = 0.90
        factors = ["shopid+itemid ดึงจาก URL โดยตรง"]
    elif shopid_provided:
        base = 0.85
        factors = ["itemid+shopid ตรงกันใน DB"]
    else:
        base = 0.80
        factors = ["itemid unique ใน DB (ไม่มี shopid ซ้ำ)"]

    if url_source == "datafeed":
        base += 0.05
        factors.append("datafeed URL ยืนยัน shopid+itemid ตรงกัน")
    elif url_source == "constructed":
        factors.append("URL สร้างจาก shopid+itemid (ไม่ผ่าน datafeed)")

    if has_title:
        base += 0.03
        factors.append("มีชื่อสินค้า")
    if has_image:
        base += 0.02
        factors.append("มีรูปสินค้า")

    score = round(min(base, 1.0), 2)

    if score >= 0.90:
        level = "high"
    elif score >= 0.75:
        level = "medium"
    elif score >= 0.50:
        level = "low"
    else:
        level = "very_low"

    return {"score": score, "level": level, "factors": factors}


# ---------------------------------------------------------------------------
# DB-backed resolution (reads products table)
# ---------------------------------------------------------------------------

def resolve_product_by_ids(
    itemid: int,
    shopid: int | None = None,
    db_path: str | None = None,
    _ref_type: str = "itemid",
) -> dict:
    """Look up a product by itemid (+ optional shopid) in the products table.

    resolution_status:
      'resolved'   — found, direct_product_url built
      'incomplete' — found but shopid=0 so URL cannot be built
      'ambiguous'  — itemid matches multiple rows with different shopids
                     and shopid was not provided; 'candidates' key is populated
      'not_found'  — no row in products table
    """
    try:
        import duckdb
        from shopee_engine.config import config
        path = db_path or str(config.db_path)
        con  = duckdb.connect(path, read_only=True)
        try:
            rows = con.execute(
                """SELECT itemid, shopid, title, sale_price, image_link,
                          product_link, shop_name, seller_name
                   FROM products WHERE itemid = ?""",
                [itemid],
            ).fetchall()
        finally:
            con.close()
    except Exception as exc:
        return _make_result(
            resolution_status="not_found",
            itemid=itemid,
            reason=f"DB error: {exc}",
            source_table="products",
        )

    if not rows:
        return _make_result(
            resolution_status="not_found",
            itemid=itemid,
            reason=f"itemid {itemid} ไม่พบในฐานข้อมูลสินค้า",
            source_table="products",
        )

    # Multiple shops selling the same itemid (rare but possible)
    if len(rows) > 1 and shopid is None:
        candidates = [
            {
                "itemid":           int(r[0]),
                "shopid":           int(r[1]),
                "title":            str(r[2] or "")[:60],
                "price":            int(r[3] or 0),
                "confidence_score": 0.70,
                "confidence_level": "medium",
                "confidence_note":  "ระบุ shopid เพื่อยืนยัน",
            }
            for r in rows
        ]
        result = _make_result(
            resolution_status="ambiguous",
            itemid=itemid,
            reason=f"itemid {itemid} พบ {len(rows)} ร้าน — ต้องระบุ shopid เพื่อ resolve",
            source_table="products",
            confidence_score=0.0,
            confidence_level="none",
            confidence_factors=["ambiguous: พบหลายร้าน ยังไม่ resolve"],
        )
        result["candidates"] = candidates
        return result

    # Exact match with shopid filter
    if shopid is not None:
        matching = [r for r in rows if int(r[1]) == shopid]
        if not matching:
            return _make_result(
                resolution_status="not_found",
                itemid=itemid,
                shopid=shopid,
                reason=f"itemid {itemid} ไม่พบใน shopid {shopid}",
                source_table="products",
            )
        row = matching[0]
    else:
        row = rows[0]

    found_itemid   = int(row[0])
    found_shopid   = int(row[1])
    title          = str(row[2] or "")
    price          = int(row[3] or 0)
    image_link     = str(row[4] or "")
    product_link   = str(row[5] or "")
    shop_name      = str(row[6] or row[7] or "")   # shop_name or seller_name

    direct_url, url_source = build_direct_url(found_shopid, found_itemid, product_link)
    status = "resolved" if direct_url else "incomplete"

    # Confidence score — only meaningful when resolved
    if status == "resolved":
        ambiguous_resolved = len(rows) > 1  # resolved from ambiguous set via shopid
        conf = _compute_resolution_score(
            ref_type=_ref_type,
            shopid_provided=(shopid is not None),
            ambiguous_resolved=ambiguous_resolved,
            url_source=url_source,
            has_title=bool(title),
            has_image=bool(image_link),
        )
    else:
        conf = {"score": 0.0, "level": "none", "factors": ["URL ไม่สามารถสร้างได้"]}

    return _make_result(
        resolution_status=status,
        itemid=found_itemid,
        shopid=found_shopid,
        title=title,
        shop_name=shop_name,
        price=price,
        image_url=image_link,
        source_product_url=product_link,
        direct_product_url=direct_url,
        affiliate_link=None,
        affiliate_status="unknown",
        source_table="products",
        reason=f"direct_url_source={url_source}",
        confidence_score=conf["score"],
        confidence_level=conf["level"],
        confidence_factors=conf["factors"],
    )


def resolve_product(
    reference: str,
    shopid: int | None = None,
    db_path: str | None = None,
) -> dict:
    """Main entry point: resolve any reference to a structured product result.

    Supported reference types:
      A. Shopee product URL  → extract shopid+itemid, then DB lookup
      B. Numeric itemid      → DB lookup (with optional shopid)
      C. Short URL           → returns 'invalid' (cannot resolve offline)
      D. Keyword             → returns 'invalid' (use full-text search instead)

    Numeric-only references are NEVER sent to full-text search.
    """
    ref      = (reference or "").strip()
    ref_type = classify_reference(ref)

    if ref_type == "itemid":
        return resolve_product_by_ids(int(ref), shopid=shopid, db_path=db_path,
                                      _ref_type="itemid")

    if ref_type == "shopee_url":
        ids = extract_shopee_ids_from_url(ref)
        if ids is None:
            return _make_result(
                resolution_status="invalid",
                reason=f"ไม่สามารถ parse shopid/itemid จาก URL: {ref[:80]}",
            )
        url_shopid, url_itemid = ids
        if shopid is not None and url_shopid != shopid:
            return _make_result(
                resolution_status="invalid",
                reason=(
                    f"shopid ใน URL ({url_shopid}) ไม่ตรงกับ shopid ที่ระบุ ({shopid})"
                ),
            )
        return resolve_product_by_ids(url_itemid, shopid=url_shopid, db_path=db_path,
                                      _ref_type="shopee_url")

    if ref_type == "short_url":
        return _make_result(
            resolution_status="invalid",
            reason=(
                "Short link (shope.ee / s.shopee.co.th) ไม่สามารถ resolve ได้ offline — "
                "ใช้ URL สินค้าปกติหรือ itemid แทน"
            ),
        )

    # keyword
    return _make_result(
        resolution_status="invalid",
        reason=(
            "ข้อความนี้ดูเหมือน keyword — ใช้ itemid หรือ Shopee product URL แทน "
            "เพื่อ resolve ตรงตัว (ตัวเลขล้วนจะถูกใช้เป็น itemid อัตโนมัติ)"
        ),
    )
