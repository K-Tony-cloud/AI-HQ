"""Product Research Pipeline — structured per-product evidence extraction.

Extracts domain-specific attributes from product DB records (description,
model_names, global_item_attributes) for editorial review before drafting.

Designed for the Editorial Brief Workflow: a human reviews the research
report before any draft is generated.
"""

from __future__ import annotations

import json
import re
from typing import Any

import duckdb

from shopee_engine.config import config
from shopee_engine.seo_engine import (
    SEO_ARTICLES_TABLE,
    SEO_ARTICLE_PRODUCTS_TABLE,
    _connect,
)


# ---------------------------------------------------------------------------
# Seller claim patterns (phrases that require evidence disclosure)
# ---------------------------------------------------------------------------

_SELLER_CLAIM_PATTERNS: list[tuple[str, str]] = [
    (r"ฆ่าเชื้อ(?:โรค)?\s*\d+(?:\.\d+)?%", "ฆ่าเชื้อ/กำจัดเชื้อโรค — อ้างอิงผู้ขาย"),
    (r"กำจัดเชื้อโรค",                       "กำจัดเชื้อโรค — อ้างอิงผู้ขาย"),
    (r"ฆ่าเชื้อแบคทีเรีย",                   "ฆ่าเชื้อแบคทีเรีย — อ้างอิงผู้ขาย"),
    (r"ดับกลิ่น|กำจัดกลิ่น|ลดกลิ่น",        "ดับกลิ่น/ลดกลิ่น — อ้างอิงผู้ขาย"),
    (r"แห้งเร็ว|เป่าแห้งเร็ว",               "แห้งเร็ว — ดูกำลังไฟและเวลาประกอบ"),
    (r"ปลอดภัย\b|safe\b",                    "ปลอดภัย — ตรวจ Auto Shutoff / Overheat Protection"),
    (r"UV\s*(?:steriliz|ฆ่าเชื้อ|light)",   "UV sterilization — อ้างอิงผู้ขาย"),
    (r"ozone|โอโซน",                         "Ozone technology — อ้างอิงผู้ขาย"),
    (r"nano\s*silver|นาโนซิลเวอร์",          "Nano Silver — อ้างอิงผู้ขาย"),
    (r"99\.9\d*%",                            "ประสิทธิภาพ % — ไม่มีผลทดสอบอิสระ"),
    (r"CE\s*certi|UL\s*listed|RoHS",         "Certification — ตรวจสอบจากผู้ขาย"),
]

# ---------------------------------------------------------------------------
# Spec extraction patterns
# ---------------------------------------------------------------------------

_WATT_RE   = re.compile(r"(\d+(?:\.\d+)?)\s*(?:W|วัตต์|watt)\b", re.IGNORECASE)
_VOLT_RE   = re.compile(r"(\d+(?:\.\d+)?)\s*(?:V|โวลต์)\b", re.IGNORECASE)
_TIMER_RE  = re.compile(
    r"(?:ตั้งเวลา|timer|เวลา|set\s*time)[^\d]*(\d+)\s*(?:นาที|min|ชั่วโมง|h(?:our)?s?|ระดับ|level)",
    re.IGNORECASE,
)
_FOLD_RE   = re.compile(r"พับ(?:เก็บ|ได้)?|foldable|fold(?:ing)?|collapsible", re.IGNORECASE)
_SHUTOFF_RE = re.compile(
    r"auto\s*(?:shut\s*off|off|power\s*off)|ปิดอัตโนมัติ|หยุดอัตโนมัติ|auto.*ปิด",
    re.IGNORECASE,
)
_OVERHEAT_RE = re.compile(
    r"overheat|protection|ป้องกันความร้อน|กันร้อน|thermal\s*protect",
    re.IGNORECASE,
)
_CERAMIC_RE = re.compile(r"ceramic|เซรามิก|PTC\b", re.IGNORECASE)
_UV_RE      = re.compile(r"\bUV\b|ultraviolet|อัลตราไวโอเลต", re.IGNORECASE)
_OZONE_RE   = re.compile(r"\bozone\b|โอโซน", re.IGNORECASE)

# Shoe type patterns
_SHOE_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"รองเท้ากีฬา|sport(?:s)?\s*shoe|sneaker",  "รองเท้ากีฬา/Sneaker"),
    (r"รองเท้าหนัง|leather\s*shoe",               "รองเท้าหนัง"),
    (r"รองเท้าบูท|boot",                           "บูท"),
    (r"ถุงเท้า|sock",                              "ถุงเท้า"),
    (r"ถุงมือ|glove",                              "ถุงมือ"),
    (r"รองเท้าสกี|ski",                            "รองเท้าสกี"),
    (r"รองเท้าเด็ก|kid(?:s)?.*shoe|children.*shoe", "รองเท้าเด็ก"),
]

# Unsuitable material patterns
_UNSUITABLE_PATTERNS: list[tuple[str, str]] = [
    (r"ห้าม.*หนัง(?:ละเอียด|บาง)|ห้าม.*suede|suede.*ห้าม", "suede/หนังนิ่ม"),
    (r"ห้าม.*ยาง|ห้าม.*rubber",                              "ยาง"),
    (r"ห้าม.*พลาสติก(?:บาง)?",                               "พลาสติกบาง"),
    (r"อุณหภูมิสูง.*ทำลาย|ทำลาย.*หนัง",                     "หนังที่ไวต่อความร้อน"),
]

# OEM title similarity detection (shared phrase patterns common in OEM listings)
_OEM_TITLE_PHRASES: list[str] = [
    "ฆ่าเชื้อโรค 99.99% ฆ่าเชื้อ อบแห้ง ดับกลิ่น 3in1",
    "ฆ่าเชื้อ อบแห้ง ดับกลิ่น",
    "Shoes Dryer เครื่องเป่ารองเท้า การกำจัดกลิ่น",
]


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _extract_watts(text: str) -> int | None:
    m = _WATT_RE.search(text)
    return int(float(m.group(1))) if m else None


def _extract_timer(text: str) -> str:
    ms = _TIMER_RE.findall(text)
    if ms:
        return ", ".join(f"{v}" for v in ms[:3])
    # Fallback: look for plain numbers near timer keywords
    if re.search(r"ตั้งเวลา|timer", text, re.IGNORECASE):
        nums = re.findall(r"\b(\d+)\s*(?:นาที|min)", text, re.IGNORECASE)
        if nums:
            return f"{nums[0]} นาที"
    return "ไม่ระบุ"


def _extract_seller_claims(text: str) -> list[str]:
    found: list[str] = []
    for pattern, label in _SELLER_CLAIM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if label not in found:
                found.append(label)
    return found


def _extract_shoe_types(text: str) -> list[str]:
    found: list[str] = []
    for pattern, label in _SHOE_TYPE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(label)
    return found or ["ไม่ระบุ"]


def _extract_unsuitable(text: str) -> list[str]:
    found: list[str] = []
    for pattern, label in _UNSUITABLE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(label)
    return found


def _drying_method(text: str) -> str:
    methods: list[str] = []
    if re.search(r"ลมร้อน|hot\s*air|warm\s*air|เซรามิก|PTC\b", text, re.IGNORECASE):
        methods.append("ลมร้อน (Hot Air)")
    if _UV_RE.search(text):
        methods.append("UV")
    if _OZONE_RE.search(text):
        methods.append("โอโซน")
    if re.search(r"ลมเย็น|cool\s*air|cold\s*air", text, re.IGNORECASE):
        methods.append("ลมเย็น")
    if re.search(r"infrared|อินฟราเรด|IR\b", text, re.IGNORECASE):
        methods.append("Infrared")
    # Fallback: rack dry
    if not methods and re.search(r"rack|แขวน|วางบน", text, re.IGNORECASE):
        methods.append("Rack Dry (passive)")
    return ", ".join(methods) if methods else "ไม่ระบุ"


def _oem_similarity_check(title_a: str, title_b: str) -> tuple[bool, list[str]]:
    """Return (is_similar, shared_phrases)."""
    shared: list[str] = []
    for phrase in _OEM_TITLE_PHRASES:
        if phrase.lower() in title_a.lower() and phrase.lower() in title_b.lower():
            shared.append(phrase)
    return bool(shared), shared


def _build_product_research(product: dict) -> dict:
    """Extract structured research from a single product row."""
    title = product.get("product_title") or product.get("title", "")
    desc  = product.get("description") or product.get("_desc", "") or ""
    attrs_raw = product.get("global_item_attributes") or product.get("_attrs", "") or ""
    models = product.get("model_names") or product.get("_model_names", "") or ""
    full_text = f"{title} {desc} {attrs_raw} {models}"

    watts     = _extract_watts(full_text)
    timer     = _extract_timer(full_text)
    foldable  = bool(_FOLD_RE.search(full_text))
    shutoff   = bool(_SHUTOFF_RE.search(full_text))
    overheat  = bool(_OVERHEAT_RE.search(full_text))
    method    = _drying_method(full_text)
    shoe_types = _extract_shoe_types(full_text)
    unsuitable = _extract_unsuitable(full_text)
    claims    = _extract_seller_claims(full_text)

    # Timer levels (ระดับ)
    level_m = re.search(r"(\d+)\s*ระดับ|(\d+)\s*level", full_text, re.IGNORECASE)
    timer_levels = int(level_m.group(1) or level_m.group(2)) if level_m else None

    # What info is missing
    missing: list[str] = []
    if watts is None:
        missing.append("กำลังไฟ (Watt)")
    if timer == "ไม่ระบุ":
        missing.append("Timer")
    if not shoe_types or shoe_types == ["ไม่ระบุ"]:
        missing.append("ประเภทรองเท้าที่รองรับ")
    if not shutoff:
        missing.append("Auto Shutoff (ไม่พบ / ไม่ระบุ)")
    if not overheat:
        missing.append("Overheat Protection (ไม่พบ / ไม่ระบุ)")

    return {
        "itemid":               product.get("itemid", 0),
        "shopid":               product.get("shopid", 0),
        "rank":                 product.get("rank_in_article", product.get("rank", 0)),
        "title":                title,
        "sale_price":           product.get("sale_price", 0),
        "item_rating":          product.get("item_rating", 0),
        "item_sold":            product.get("item_sold", 0),
        "seller_name":          product.get("seller_name", ""),
        "affiliate_status":     product.get("affiliate_link_type", "none"),
        # Structured domain evidence
        "drying_method":        method,
        "watt":                 watts,
        "timer":                timer,
        "timer_levels":         timer_levels,
        "foldable":             foldable,
        "auto_shutoff":         shutoff,
        "overheat_protection":  overheat,
        "suitable_shoe_types":  shoe_types,
        "unsuitable_materials": unsuitable,
        "seller_claims":        claims,
        "evidence_source":      "product_description + model_names + global_item_attributes",
        "missing_info":         missing,
    }


# ---------------------------------------------------------------------------
# OEM detection across a product list
# ---------------------------------------------------------------------------

def detect_oem_clusters(products: list[dict]) -> list[dict]:
    """Return list of OEM match groups (pairs/groups with shared template phrases)."""
    groups: list[dict] = []
    n = len(products)
    matched: set[int] = set()
    for i in range(n):
        for j in range(i + 1, n):
            ti = products[i].get("title") or products[i].get("product_title", "")
            tj = products[j].get("title") or products[j].get("product_title", "")
            similar, shared = _oem_similarity_check(ti, tj)
            if similar:
                matched.update([i, j])
                groups.append({
                    "product_a_itemid": products[i].get("itemid"),
                    "product_a_title":  ti[:80],
                    "product_b_itemid": products[j].get("itemid"),
                    "product_b_title":  tj[:80],
                    "shared_phrases":   shared,
                    "recommendation": (
                        "⚠️ OEM suspected — ตรวจ seller origin ก่อนใส่ทั้งคู่ใน article เดียวกัน"
                    ),
                })
    return groups


# ---------------------------------------------------------------------------
# Main research function
# ---------------------------------------------------------------------------

def research_article_products(article_id: str) -> dict:
    """Load all products for an article and extract structured research.

    Returns:
        {
          "success": bool,
          "article_id": str,
          "keyword": str,
          "brief": dict | None,
          "products": list[dict],   # per-product research
          "oem_alerts": list[dict], # OEM similarity groups
          "summary": dict,
          "error": str | None,
        }
    """
    con = _connect(read_only=True)
    try:
        art_row = con.execute(
            f"SELECT keyword, category, status, title FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()
        if not art_row:
            con.close()
            return {"success": False, "error": f"Article '{article_id}' not found"}

        keyword, category, status, art_title = art_row

        # Load products with full detail from products table JOIN article_products
        _prod_cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        _has_desc  = "description" in _prod_cols
        _has_attrs = "global_item_attributes" in _prod_cols
        _has_mn    = "model_names" in _prod_cols
        _has_rating = "item_rating" in _prod_cols
        _has_sold   = "item_sold" in _prod_cols
        _has_seller = "seller_name" in _prod_cols

        desc_expr   = "COALESCE(p.description, '')"            if _has_desc   else "''"
        attrs_expr  = "COALESCE(p.global_item_attributes, '')" if _has_attrs  else "''"
        mn_expr     = "COALESCE(p.model_names, '')"            if _has_mn     else "''"
        rating_expr = "COALESCE(p.item_rating, 0)"             if _has_rating else "0"
        sold_expr   = "COALESCE(p.item_sold, 0)"               if _has_sold   else "0"
        seller_expr = "COALESCE(p.seller_name, '')"            if _has_seller else "''"

        rows = con.execute(f"""
            SELECT
                ap.rank_in_article,
                ap.itemid,
                ap.shopid,
                ap.product_title,
                ap.sale_price,
                ap.affiliate_link_type,
                ap.affiliate_link,
                {desc_expr}   AS _desc,
                {attrs_expr}  AS _attrs,
                {mn_expr}     AS _model_names,
                {rating_expr} AS item_rating,
                {sold_expr}   AS item_sold,
                {seller_expr} AS seller_name
            FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
            LEFT JOIN products p ON p.itemid = ap.itemid AND p.shopid = ap.shopid
            WHERE ap.article_id = ?
            ORDER BY ap.rank_in_article
        """, [article_id]).fetchall()

        con.close()
    except Exception as exc:
        con.close()
        return {"success": False, "error": str(exc)}

    if not rows:
        return {"success": False, "error": f"Article '{article_id}' has no products"}

    col_names = [
        "rank_in_article", "itemid", "shopid", "product_title", "sale_price",
        "affiliate_link_type", "affiliate_link",
        "description", "global_item_attributes", "model_names",
        "item_rating", "item_sold", "seller_name",
    ]
    raw_products = [dict(zip(col_names, r)) for r in rows]

    researched: list[dict] = []
    for rp in raw_products:
        ev = _build_product_research(rp)
        researched.append(ev)

    # OEM detection
    oem_alerts = detect_oem_clusters(raw_products)

    # Summary
    aff_confirmed = sum(1 for p in raw_products if p.get("affiliate_link_type") == "confirmed")
    missing_all   = sum(1 for p in researched if p["missing_info"])
    claim_heavy   = sum(1 for p in researched if len(p["seller_claims"]) >= 3)

    # Load brief for alignment check
    brief = None
    try:
        from shopee_engine.editorial_brief import get_brief_for_keyword, get_brief_for_article
        brief = get_brief_for_keyword(keyword) or get_brief_for_article(article_id)
    except Exception:
        pass

    summary: dict[str, Any] = {
        "total_products":     len(researched),
        "affiliate_confirmed": aff_confirmed,
        "affiliate_missing":   len(researched) - aff_confirmed,
        "oem_suspect_pairs":  len(oem_alerts),
        "products_missing_info": missing_all,
        "heavy_claim_products": claim_heavy,
        "brief_status": brief.get("brief_status", "none") if brief else "none",
        "draft_recommendation": (
            "⛔ อย่าสร้าง Draft ก่อน: ตรวจ OEM alerts และ Research Report นี้ให้ครบก่อน"
            if oem_alerts or missing_all > 1
            else "✅ Research เบื้องต้นพร้อม — แต่ผู้ใช้ต้องตรวจ OEM และ claims ก่อน approve draft"
        ),
    }

    return {
        "success":    True,
        "article_id": article_id,
        "keyword":    keyword,
        "article_title": art_title,
        "status":     status,
        "brief":      brief,
        "products":   researched,
        "oem_alerts": oem_alerts,
        "summary":    summary,
    }
