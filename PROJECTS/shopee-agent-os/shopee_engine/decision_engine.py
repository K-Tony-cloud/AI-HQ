"""
Decision Engine — data-driven decision sections for AI Shopping Decision Engine.

Turns real product data into decision-ready Thai content:
  1. Shopping Advisor  — decision table (persona → product) + best pick sentence
  2. Long-tail Decision FAQ — 3-5 intent-specific questions, fully grounded in data

Design rules (enforced throughout):
  - All claims sourced from actual product fields: sale_price, item_sold,
    item_rating, discount_pct, title.
  - No raw "scores" displayed to users. Only the data they originate from.
  - Never say "ดีที่สุด" / "คุ้มที่สุด" unless the value is provably the max
    in this article's product set.
  - "ขายดีที่สุดในกลุ่ม" is valid only when max(item_sold) is unambiguous.
  - Fallback gracefully when data is insufficient; return "" rather than guess.
  - No AI/API calls — fully deterministic from product fields.
  - No Lazada comparisons (no Lazada data available).
  - No "ของแท้" guarantees (authenticity cannot be verified from product data).
  - Seasonal/campaign context: Phase 2 — not implemented here.

Public API:
    get_section_title(category) → str
    build_shopping_advisor(keyword, category, products) → str
    build_decision_faq(keyword, category, products) → str
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Dynamic Section Titles (per category)
# ---------------------------------------------------------------------------

_SECTION_TITLE: dict[str, str] = {
    "mobile-gadgets": "รุ่นไหนดี",
    "home-living":    "แบบไหนดี",
    "beauty":         "ตัวไหนดี",
    "health":         "สูตรไหนดี",
    "sports":         "ตัวไหนดี",
    "baby-kids":      "ชิ้นไหนดี",
    "food-drinks":    "แบบไหนดี",
}
_SECTION_TITLE_DEFAULT = "ตัวไหนดี"


def get_section_title(category: str) -> str:
    """Return the appropriate decision section heading for a given category."""
    return _SECTION_TITLE.get(category.strip().lower(), _SECTION_TITLE_DEFAULT)


# ---------------------------------------------------------------------------
# Persona Configs (per category)
# strategy values:
#   "cheapest"        → min(sale_price)
#   "sold_leader"     → max(item_sold)     — skipped when all item_sold == 0
#   "rating_leader"   → max(item_rating)
#   "value_score"     → max(item_sold * item_rating / max(price, 1))
#   "feature:{key}"   → title contains any keyword in _FEATURE_KEYWORDS[key]
# ---------------------------------------------------------------------------

_PERSONA_CONFIGS: dict[str, list[dict]] = {
    "mobile-gadgets": [
        {"label": "งบน้อย",             "strategy": "cheapest"},
        {"label": "ใช้งานหนักทุกวัน",  "strategy": "sold_leader"},
        {"label": "พกพาบ่อย",           "strategy": "feature:portable"},
        {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
        {"label": "ซื้อเป็นของขวัญ",   "strategy": "value_score"},
    ],
    "home-living": [
        {"label": "งบน้อย",             "strategy": "cheapest"},
        {"label": "ใช้งานบ่อยทุกวัน",  "strategy": "sold_leader"},
        {"label": "คนอยู่คอนโด",        "strategy": "feature:compact"},
        {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
    ],
    "beauty": [
        {"label": "มือใหม่อยากทดลอง",  "strategy": "cheapest"},
        {"label": "ขายดีที่สุด",        "strategy": "sold_leader"},
        {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
        {"label": "คุ้มค่าที่สุด",      "strategy": "value_score"},
    ],
    "health": [
        {"label": "งบน้อย",             "strategy": "cheapest"},
        {"label": "ผ่านการพิสูจน์",     "strategy": "sold_leader"},
        {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
        {"label": "คุ้มค่าที่สุด",      "strategy": "value_score"},
    ],
    "sports": [
        {"label": "งบน้อย",             "strategy": "cheapest"},
        {"label": "ต้องการทนทาน",       "strategy": "rating_leader"},
        {"label": "ขายดีที่สุด",        "strategy": "sold_leader"},
        {"label": "พกพาบ่อย",           "strategy": "feature:portable"},
    ],
    "baby-kids": [
        {"label": "งบน้อย",             "strategy": "cheapest"},
        {"label": "ผ่านการพิสูจน์",     "strategy": "sold_leader"},
        {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
    ],
    "food-drinks": [
        {"label": "งบน้อยอยากลอง",      "strategy": "cheapest"},
        {"label": "ขายดีที่สุด",        "strategy": "sold_leader"},
        {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
    ],
}

_PERSONA_DEFAULT: list[dict] = [
    {"label": "งบน้อย",             "strategy": "cheapest"},
    {"label": "ขายดีที่สุดในกลุ่ม", "strategy": "sold_leader"},
    {"label": "คะแนนดีที่สุด",      "strategy": "rating_leader"},
]

# Feature keywords used by "feature:{key}" strategy (case-insensitive match on title)
_FEATURE_KEYWORDS: dict[str, list[str]] = {
    "portable": [
        "portable", "พกพา", "มือถือ", "mini", "มินิ", "handheld",
        "pocket", "travel", "เดินทาง",
    ],
    "compact": [
        "ขนาดเล็ก", "compact", "mini", "มินิ", "slim", "สลิม", "พื้นที่น้อย",
    ],
    "wireless": ["ไร้สาย", "wireless", "cordless", "bluetooth"],
    "quiet":    ["เงียบ", "silent", "quiet", "low noise"],
    "powerful": ["แรง", "powerful", "high speed", "ความเร็วสูง"],
}


def _get_persona_configs(category: str) -> list[dict]:
    return _PERSONA_CONFIGS.get(category.strip().lower(), _PERSONA_DEFAULT)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_price(price: int | float) -> str:
    """Format integer price as Thai Baht string: ฿94, ฿1,234"""
    return f"฿{int(price):,}"


def _rank_of(product: dict, products: list[dict]) -> int:
    """Return 1-based rank (position) of product in article product list."""
    try:
        return products.index(product) + 1
    except ValueError:
        return 0


def _has_feature(product: dict, feature_key: str) -> bool:
    """Check whether a product's title contains any keyword for the given feature."""
    keywords = _FEATURE_KEYWORDS.get(feature_key, [])
    if not keywords:
        return False
    title = str(product.get("title", "")).lower()
    return any(kw.lower() in title for kw in keywords)


def _select_by_strategy(
    products: list[dict],
    strategy: str,
) -> tuple[dict, str] | None:
    """
    Select the best product for a given strategy.

    Returns (product, reason_string) or None if strategy cannot be applied.

    Reason strings use actual data values only.
    "ดีที่สุด" / "สูงสุด" only when the value is provably the max in this set.
    """
    if not products:
        return None

    # ── cheapest ────────────────────────────────────────────────────────────
    if strategy == "cheapest":
        valid = [p for p in products if (p.get("sale_price") or 0) > 0]
        if not valid:
            return None
        min_price = min(p["sale_price"] for p in valid)
        candidates = [p for p in valid if p["sale_price"] == min_price]
        # Use first occurrence (lowest rank) as tiebreak
        p = min(candidates, key=lambda x: products.index(x))
        return p, f"ราคาต่ำสุดในกลุ่ม {_fmt_price(min_price)}"

    # ── sold_leader ──────────────────────────────────────────────────────────
    if strategy == "sold_leader":
        valid = [p for p in products if (p.get("item_sold") or 0) > 0]
        if not valid:
            return None
        max_sold = max(p["item_sold"] for p in valid)
        candidates = [p for p in valid if p["item_sold"] == max_sold]
        p = min(candidates, key=lambda x: products.index(x))
        return p, f"ขายดีที่สุดในกลุ่ม {max_sold:,} ชิ้น"

    # ── rating_leader ────────────────────────────────────────────────────────
    if strategy == "rating_leader":
        valid = [p for p in products if (p.get("item_rating") or 0) > 0]
        if not valid:
            return None
        max_r = max(p["item_rating"] for p in valid)
        candidates = [p for p in valid if p["item_rating"] == max_r]
        p = min(candidates, key=lambda x: products.index(x))
        return p, f"คะแนนสูงสุดในกลุ่ม {max_r:.1f} ⭐"

    # ── value_score ──────────────────────────────────────────────────────────
    if strategy == "value_score":
        def _vs(p: dict) -> float:
            sold   = p.get("item_sold", 0) or 0
            rating = p.get("item_rating", 0.0) or 0.0
            price  = p.get("sale_price", 0) or 1
            return sold * rating / price

        valid = [p for p in products if _vs(p) > 0]
        if not valid:
            return None
        best = max(valid, key=_vs)
        sold   = best.get("item_sold", 0) or 0
        rating = best.get("item_rating", 0.0) or 0.0
        price  = best.get("sale_price", 0) or 0
        reason = (
            f"ยอดขาย {sold:,} ชิ้น คะแนน {rating:.1f} ⭐ ราคา {_fmt_price(price)}"
            f" — สมดุลระหว่างความนิยม คุณภาพ และราคา"
        )
        return best, reason

    # ── feature:{key} ────────────────────────────────────────────────────────
    if strategy.startswith("feature:"):
        feature_key = strategy.split(":", 1)[1]
        matches = [p for p in products if _has_feature(p, feature_key)]
        if not matches:
            return None  # skip this persona when feature not found in any title
        # Among matches, prefer sold_leader; fallback to first in rank order
        with_sold = [p for p in matches if (p.get("item_sold") or 0) > 0]
        if with_sold:
            p = max(with_sold, key=lambda x: x.get("item_sold", 0))
            sold = p.get("item_sold", 0) or 0
            reason = f"มีฟีเจอร์{_feature_label(feature_key)} ขายแล้ว {sold:,} ชิ้น"
        else:
            p = matches[0]
            reason = f"มีฟีเจอร์{_feature_label(feature_key)}"
        return p, reason

    return None


def _feature_label(feature_key: str) -> str:
    """Human-readable Thai label for a feature key."""
    _labels = {
        "portable": "พกพา",
        "compact":  "ขนาดกะทัดรัด",
        "wireless": "ไร้สาย",
        "quiet":    "เงียบ",
        "powerful": "ลมแรง",
    }
    return _labels.get(feature_key, feature_key)


def _flash_sale_caveat(products: list[dict]) -> str:
    """Return caveat string if any product has discount ≥ 40%, else ''."""
    has_flash = any((p.get("discount_pct") or 0) >= 40 for p in products)
    return " *(ราคา Flash Sale — อาจเปลี่ยนได้ ตรวจก่อนสั่ง)*" if has_flash else ""


# ---------------------------------------------------------------------------
# Shopping Advisor
# ---------------------------------------------------------------------------

def _build_decision_table(products: list[dict], category: str) -> str:
    """
    Build the decision table: | ถ้าคุณ... | แนะนำ | เหตุผล |

    Rules:
    - Dedup by product rank: if two personas resolve to the same product,
      only the first persona row is shown.
    - Returns "" when fewer than 2 distinct rows can be produced.
    """
    personas = _get_persona_configs(category)
    rows: list[tuple[str, str, str]] = []  # (label, "#N ฿price", reason)
    seen_ranks: set[int] = set()

    for p_cfg in personas:
        result = _select_by_strategy(products, p_cfg["strategy"])
        if result is None:
            continue
        product, reason = result
        rank = _rank_of(product, products)
        if rank in seen_ranks:
            continue  # skip duplicate product
        seen_ranks.add(rank)

        price = product.get("sale_price", 0) or 0
        rec   = f"#{rank} {_fmt_price(price)}" if price else f"#{rank}"
        rows.append((p_cfg["label"], rec, reason))

    if len(rows) < 2:
        return ""

    lines = [
        "| ถ้าคุณ... | แนะนำ | เหตุผล |",
        "|-----------|-------|--------|",
    ]
    for label, rec, reason in rows:
        lines.append(f"| {label} | {rec} | {reason} |")
    return "\n".join(lines)


def _build_best_pick(products: list[dict]) -> str:
    """
    Build the 'ถ้าต้องเลือกแค่ตัวเดียว' sentence.

    Picks the product with the best value_score (sold × rating / price).
    If cheapest == sold_leader, uses that product with a stronger rationale.
    Returns "" if data is insufficient for a grounded recommendation.
    """
    if not products:
        return ""

    # Check if cheapest is also sold_leader (clear-cut winner)
    cheapest_result   = _select_by_strategy(products, "cheapest")
    sold_result       = _select_by_strategy(products, "sold_leader")
    value_result      = _select_by_strategy(products, "value_score")

    if cheapest_result and sold_result and (
        cheapest_result[0] is sold_result[0]
    ):
        p = cheapest_result[0]
        rank  = _rank_of(p, products)
        price = p.get("sale_price", 0) or 0
        sold  = p.get("item_sold", 0) or 0
        caveat = _flash_sale_caveat([p])
        return (
            f"**ถ้าต้องเลือกแค่ตัวเดียว:** #{rank} {_fmt_price(price)}"
            f" — ราคาต่ำสุดในกลุ่มและขายดีที่สุด {sold:,} ชิ้น"
            f" ความเสี่ยงต่ำสำหรับคนที่ยังไม่แน่ใจ{caveat}"
        )

    if value_result:
        p, reason = value_result
        rank  = _rank_of(p, products)
        price = p.get("sale_price", 0) or 0
        caveat = _flash_sale_caveat([p])
        return (
            f"**ถ้าต้องเลือกแค่ตัวเดียว:** #{rank} {_fmt_price(price)}"
            f" — {reason}{caveat}"
        )

    # Fallback: sold_leader
    if sold_result:
        p, reason = sold_result
        rank  = _rank_of(p, products)
        price = p.get("sale_price", 0) or 0
        caveat = _flash_sale_caveat([p])
        return (
            f"**ถ้าต้องเลือกแค่ตัวเดียว:** #{rank} {_fmt_price(price)}"
            f" — {reason}{caveat}"
        )

    return ""


def build_shopping_advisor(
    keyword: str,
    category: str,
    products: list[dict],
) -> str:
    """
    Build the complete Shopping Advisor section body (no ## header — caller adds it).

    Returns "" if there are fewer than 2 products or data is too sparse.
    """
    if len(products) < 2:
        return ""

    table    = _build_decision_table(products, category)
    best     = _build_best_pick(products)

    if not table and not best:
        return ""

    parts: list[str] = []
    if table:
        parts.append(table)
    if best:
        parts.append("")
        parts.append(best)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Long-tail Decision FAQ
# ---------------------------------------------------------------------------

def build_decision_faq(
    keyword: str,
    category: str,
    products: list[dict],
) -> str:
    """
    Build the decision FAQ section with 3-5 intent-specific questions.

    All answers grounded in actual product data.
    Returns the complete section string including the ## header.

    Excluded by design (not enough data to answer honestly):
      - Lazada vs Shopee comparisons (no Lazada data)
      - Authenticity guarantees ("ของแท้") — cannot verify
      - Seasonal/campaign tips — Phase 2
    """
    if not products:
        return ""

    prices   = [p.get("sale_price", 0) or 0 for p in products if (p.get("sale_price") or 0) > 0]
    min_p    = min(prices) if prices else 0
    max_p    = max(prices) if prices else 0
    count    = len(products)

    sold_result   = _select_by_strategy(products, "sold_leader")
    cheap_result  = _select_by_strategy(products, "cheapest")

    questions: list[str] = []

    # Q1 — Most popular / best starting point (always)
    if sold_result:
        p, _ = sold_result
        rank  = _rank_of(p, products)
        sold  = p.get("item_sold", 0) or 0
        price = p.get("sale_price", 0) or 0
        r     = p.get("item_rating", 0.0) or 0.0
        questions.append(
            f"**{keyword} ตัวไหนขายดีที่สุด?**\n\n"
            f"#{rank} ขายแล้ว {sold:,} ชิ้น ราคา {_fmt_price(price)}"
            f"{f' คะแนน {r:.1f} ⭐' if r > 0 else ''}"
            f" — ยอดขายสูงสุดในบทความนี้ ณ วันที่อัปเดตข้อมูล"
        )
    else:
        # Fallback Q1: price range
        if min_p and max_p:
            questions.append(
                f"**{keyword} ราคาอยู่ที่เท่าไหร่?**\n\n"
                f"ราคาในบทความนี้เริ่มต้นที่ {_fmt_price(min_p)}"
                f" และสูงสุดที่ {_fmt_price(max_p)}"
            )

    # Q2 — Entry budget (always)
    if cheap_result and min_p > 0:
        p, _ = cheap_result
        rank  = _rank_of(p, products)
        questions.append(
            f"**งบ {_fmt_price(min_p)} บาท ซื้อ {keyword} ได้ไหม?**\n\n"
            f"ได้ — #{rank} ราคา {_fmt_price(min_p)} เป็นตัวเลือกที่ราคาต่ำสุดในบทความนี้"
            f" ราคาอาจเปลี่ยนตามช่วงโปร ตรวจราคาปัจจุบันก่อนสั่ง"
        )

    # Q3 — Where to buy (always) — no Lazada mention, no authenticity guarantee
    questions.append(
        f"**ซื้อ {keyword} ที่ไหนดี?**\n\n"
        f"ลิงก์ทุกรายการในบทความนี้เชื่อมตรงไป Shopee"
        f" ซึ่งมีระบบคุ้มครองผู้ซื้อและรองรับการคืนสินค้า"
        f" ราคาที่แสดงในบทความเป็นราคา ณ วันที่อัปเดต — ควรตรวจราคาก่อนกดสั่ง"
    )

    # Q4 — Price range comparison (only if max ≥ 2.5× min)
    if min_p > 0 and max_p > 0 and max_p >= min_p * 2.5 and cheap_result:
        cheap_p, _ = cheap_result
        cheap_rank = _rank_of(cheap_p, products)
        prem_result = _select_by_strategy(products, "rating_leader")
        if prem_result and prem_result[0] is not cheap_p:
            prem_p, _  = prem_result
            prem_rank  = _rank_of(prem_p, products)
            prem_price = prem_p.get("sale_price", 0) or 0
            prem_r     = prem_p.get("item_rating", 0.0) or 0.0
            questions.append(
                f"**{_fmt_price(min_p)} หรือ {_fmt_price(max_p)} ดีกว่ากัน?**\n\n"
                f"#{cheap_rank} {_fmt_price(min_p)} เหมาะกับคนที่อยากทดลองใช้ก่อนโดยไม่เสี่ยงงบมาก "
                f"#{prem_rank} {_fmt_price(prem_price)} มีคะแนนรีวิว {prem_r:.1f} ⭐"
                f" เหมาะกับคนที่ต้องการความมั่นใจด้านคุณภาพมากกว่า"
                f" — ขึ้นกับว่าคุณเน้นราคาหรือคุณภาพเป็นหลัก"
            )

    # Q5 — Flash Sale (only if any discount ≥ 40%)
    flash_products = [p for p in products if (p.get("discount_pct") or 0) >= 40]
    if flash_products:
        fp = flash_products[0]
        fp_rank  = _rank_of(fp, products)
        fp_price = fp.get("sale_price", 0) or 0
        fp_disc  = fp.get("discount_pct", 0) or 0
        questions.append(
            f"**Flash Sale คุ้มไหม?**\n\n"
            f"#{fp_rank} ลดอยู่ที่ {fp_disc}% เหลือ {_fmt_price(fp_price)}"
            f" ราคา Flash Sale อาจเปลี่ยนได้ทุกวันหรือทุกชั่วโมง"
            f" ควรตรวจราคาปัจจุบันก่อนตัดสินใจ — ไม่ควรรอนานเพราะสต็อกอาจหมด"
        )

    if not questions:
        return ""

    lines = ["## คำถามที่พบบ่อย (FAQ)\n"]
    lines.extend(q + "\n" for q in questions)
    return "\n".join(lines)
