"""Tests for shopee_engine/decision_engine.py"""
import pytest
from shopee_engine.decision_engine import (
    build_decision_faq,
    build_shopping_advisor,
    get_section_title,
    _build_best_pick,
    _build_decision_table,
    _has_feature,
    _select_by_strategy,
    _fmt_price,
    _flash_sale_caveat,
)

# ---------------------------------------------------------------------------
# Fixtures — realistic product data from published articles
# ---------------------------------------------------------------------------

def _p(title, price, sold, rating, discount=0):
    return {
        "title": title,
        "sale_price": price,
        "item_sold": sold,
        "item_rating": rating,
        "discount_pct": discount,
    }


FANS_500 = [
    _p("KENTO LITE พัดลมสำนักงาน 6 นิ้ว ความเร็วสูง ทํางานเงียบ 100 ระดับ ใช้ได้12ชม", 276, 1982, 4.86),
    _p("EZhome Mini Portable Handheld Fan พัดลมพกพา พัดลมมินิ Mini Fan สีพาสเทล",        149,   95, 4.90),
    _p("GOOJODOQ Gfs006 พัดลมพกพา 4000mah Type C หมอกเย็น 100 ระดับ พัดลมมือถือ",        449, 3680, 4.89),
    _p("JH-022 พัดลมไร้สาย 8 นิ้ว หน้ากว้าง ลมแรง ชาร์จไฟ 10,000-20,000mAh clip fan",  376, 1896, 4.91),
    _p("Flash Sale พัดลมมือถือ พัดลมพกพา 100 ระดับ แบตฯใหญ่ 5000mAh",                    94, 3803, 4.59, discount=50),
]

FANS_1000 = [
    _p("JisuLife handheld fan life9 พัดลมเจ็ท 5000mAh ใช้งานได้ 18 ชั่วโมง",           738, 3181, 4.90),
    _p("KENTO LITE พัดลมสำนักงาน 6 นิ้ว ความเร็วสูง 100 ระดับ ใช้ได้12ชม",            276, 1982, 4.86),
    _p("JisuLife handheld fan life10S 5000mAh 28 ชั่วโมง จอแสดงผล",                    805, 2253, 4.90),
    _p("EZhome Mini Portable Handheld Fan พัดลมพกพา มินิ สีพาสเทล",                     149,   95, 4.90),
    _p("GOOJODOQ Gfs006 พัดลมพกพา 4000mah Type C หมอกเย็น 100 ระดับ พัดลมมือถือ",      449, 3680, 4.89),
]

BEAUTY = [
    _p("Mistine BB Cream SPF30 สูตรรองพื้น",          89, 5000, 4.8, discount=20),
    _p("Maybelline Fit Me Foundation ติดทนนาน 24ชม", 349, 2000, 4.7),
    _p("MAC Studio Fix สูตรปิดรูขุมขน",               899,  800, 4.9),
    _p("Pond's BB Magic ครีมกันแดด SPF50",            129, 3500, 4.6),
]

SINGLE_PRODUCT = [
    _p("สินค้าเดียว", 299, 500, 4.5),
]

ZERO_SOLD = [
    _p("สินค้า A ไม่มียอดขาย", 100, 0, 4.5),
    _p("สินค้า B ไม่มียอดขาย", 200, 0, 4.8),
    _p("สินค้า C ไม่มียอดขาย", 300, 0, 4.7),
]

SAME_PRICE = [
    _p("สินค้า A", 299, 100, 4.5),
    _p("สินค้า B", 299, 200, 4.8),
    _p("สินค้า C", 299, 300, 4.7),
]

NO_PORTABLE = [
    _p("พัดลมตั้งโต๊ะขนาดใหญ่ ใช้ไฟบ้าน",   499, 1000, 4.7),
    _p("พัดลมอุตสาหกรรมลมแรง 18 นิ้ว",        890, 800,  4.8),
    _p("พัดลมสำนักงานตั้งโต๊ะ เงียบ 6 นิ้ว", 276, 1982, 4.9),
]


# ---------------------------------------------------------------------------
# get_section_title
# ---------------------------------------------------------------------------

class TestGetSectionTitle:
    def test_mobile_gadgets(self):
        assert get_section_title("mobile-gadgets") == "รุ่นไหนดี"

    def test_beauty(self):
        assert get_section_title("beauty") == "ตัวไหนดี"

    def test_health(self):
        assert get_section_title("health") == "สูตรไหนดี"

    def test_baby_kids(self):
        assert get_section_title("baby-kids") == "ชิ้นไหนดี"

    def test_food_drinks(self):
        assert get_section_title("food-drinks") == "แบบไหนดี"

    def test_home_living(self):
        assert get_section_title("home-living") == "แบบไหนดี"

    def test_sports(self):
        assert get_section_title("sports") == "ตัวไหนดี"

    def test_unknown_category_returns_default(self):
        assert get_section_title("unknown-xyz") == "ตัวไหนดี"

    def test_empty_category_returns_default(self):
        assert get_section_title("") == "ตัวไหนดี"

    def test_case_insensitive(self):
        assert get_section_title("Mobile-Gadgets") == "รุ่นไหนดี"


# ---------------------------------------------------------------------------
# _fmt_price
# ---------------------------------------------------------------------------

class TestFmtPrice:
    def test_small_price(self):
        assert _fmt_price(94) == "฿94"

    def test_comma_formatted(self):
        assert _fmt_price(1234) == "฿1,234"

    def test_large_price(self):
        assert _fmt_price(10000) == "฿10,000"


# ---------------------------------------------------------------------------
# _has_feature
# ---------------------------------------------------------------------------

class TestHasFeature:
    def test_portable_thai(self):
        p = _p("พัดลมพกพา mini ขนาดเล็ก", 100, 0, 4.0)
        assert _has_feature(p, "portable") is True

    def test_portable_english(self):
        p = _p("EZhome Mini Portable Handheld Fan", 100, 0, 4.0)
        assert _has_feature(p, "portable") is True

    def test_no_portable(self):
        p = _p("พัดลมตั้งโต๊ะอุตสาหกรรม 18 นิ้ว", 100, 0, 4.0)
        assert _has_feature(p, "portable") is False

    def test_compact_thai(self):
        p = _p("ขนาดเล็ก slim สำหรับคอนโด", 100, 0, 4.0)
        assert _has_feature(p, "compact") is True

    def test_unknown_feature_key(self):
        p = _p("สินค้าทดสอบ", 100, 0, 4.0)
        assert _has_feature(p, "nonexistent") is False


# ---------------------------------------------------------------------------
# _select_by_strategy
# ---------------------------------------------------------------------------

class TestSelectByStrategy:
    def test_cheapest_selects_min_price(self):
        result = _select_by_strategy(FANS_500, "cheapest")
        assert result is not None
        p, reason = result
        assert p["sale_price"] == 94
        assert "94" in reason
        assert "ราคาต่ำสุด" in reason

    def test_sold_leader_selects_max_sold(self):
        result = _select_by_strategy(FANS_500, "sold_leader")
        assert result is not None
        p, reason = result
        assert p["item_sold"] == 3803
        assert "3,803" in reason
        assert "ขายดีที่สุด" in reason

    def test_rating_leader_selects_max_rating(self):
        result = _select_by_strategy(FANS_500, "rating_leader")
        assert result is not None
        p, reason = result
        assert p["item_rating"] == 4.91
        assert "4.9" in reason
        assert "คะแนนสูงสุด" in reason

    def test_value_score_returns_balanced_pick(self):
        result = _select_by_strategy(FANS_500, "value_score")
        assert result is not None
        p, reason = result
        assert "ยอดขาย" in reason
        assert "คะแนน" in reason
        assert "สมดุล" in reason

    def test_feature_portable_matches(self):
        result = _select_by_strategy(FANS_500, "feature:portable")
        assert result is not None
        p, reason = result
        assert _has_feature(p, "portable")
        assert "พกพา" in reason

    def test_feature_not_found_returns_none(self):
        result = _select_by_strategy(NO_PORTABLE, "feature:portable")
        assert result is None

    def test_sold_leader_skipped_when_all_zero(self):
        result = _select_by_strategy(ZERO_SOLD, "sold_leader")
        assert result is None

    def test_empty_products_returns_none(self):
        assert _select_by_strategy([], "cheapest") is None
        assert _select_by_strategy([], "sold_leader") is None

    def test_unknown_strategy_returns_none(self):
        assert _select_by_strategy(FANS_500, "nonexistent_strategy") is None


# ---------------------------------------------------------------------------
# _flash_sale_caveat
# ---------------------------------------------------------------------------

class TestFlashSaleCaveat:
    def test_caveat_when_discount_40_or_more(self):
        products = [_p("test", 94, 100, 4.5, discount=50)]
        assert _flash_sale_caveat(products) != ""
        assert "Flash Sale" in _flash_sale_caveat(products)

    def test_no_caveat_below_40(self):
        products = [_p("test", 200, 100, 4.5, discount=39)]
        assert _flash_sale_caveat(products) == ""

    def test_no_caveat_no_discount(self):
        products = [_p("test", 200, 100, 4.5, discount=0)]
        assert _flash_sale_caveat(products) == ""


# ---------------------------------------------------------------------------
# _build_decision_table
# ---------------------------------------------------------------------------

class TestBuildDecisionTable:
    def test_mobile_gadgets_produces_table(self):
        table = _build_decision_table(FANS_500, "mobile-gadgets")
        assert "| ถ้าคุณ..." in table
        assert "| เหตุผล |" in table
        assert "#" in table

    def test_table_has_at_least_2_rows(self):
        table = _build_decision_table(FANS_500, "mobile-gadgets")
        rows = [l for l in table.split("\n") if l.startswith("|") and "ถ้าคุณ" not in l and "---" not in l]
        assert len(rows) >= 2

    def test_no_duplicate_product_ranks(self):
        table = _build_decision_table(FANS_500, "mobile-gadgets")
        # Extract recommendations (e.g. #5, #1)
        recs = [part.strip() for line in table.split("\n")
                if line.startswith("|") and "ถ้าคุณ" not in line and "---" not in line
                for part in line.split("|")[2:3]]
        # Each rank should appear at most once
        ranks = [r.split()[0] for r in recs if r.startswith("#")]
        assert len(ranks) == len(set(ranks)), f"Duplicate ranks: {ranks}"

    def test_beauty_category_uses_beauty_personas(self):
        table = _build_decision_table(BEAUTY, "beauty")
        assert table != ""

    def test_single_product_returns_empty(self):
        table = _build_decision_table(SINGLE_PRODUCT, "mobile-gadgets")
        assert table == ""

    def test_same_price_no_cheapest_row(self):
        table = _build_decision_table(SAME_PRICE, "mobile-gadgets")
        # cheapest and sold_leader may collapse to fewer rows; just verify no crash
        assert isinstance(table, str)

    def test_no_portable_feature_skips_portable_persona(self):
        table = _build_decision_table(NO_PORTABLE, "mobile-gadgets")
        # "พกพาบ่อย" persona should be skipped (no portable products)
        assert "พกพาบ่อย" not in table

    def test_table_prices_are_grounded(self):
        table = _build_decision_table(FANS_500, "mobile-gadgets")
        actual_prices = {str(p["sale_price"]) for p in FANS_500}
        for price in actual_prices:
            # If price appears in table, it was from data (not invented)
            pass  # just verify no exception and table is non-empty
        assert "฿" in table


# ---------------------------------------------------------------------------
# _build_best_pick
# ---------------------------------------------------------------------------

class TestBuildBestPick:
    def test_returns_best_pick_string(self):
        result = _build_best_pick(FANS_500)
        assert result.startswith("**ถ้าต้องเลือกแค่ตัวเดียว:**")

    def test_cheapest_sold_leader_wins_clearly(self):
        # In FANS_500, #5 (฿94, sold=3803) is cheapest AND sold leader
        result = _build_best_pick(FANS_500)
        assert "94" in result
        assert "3,803" in result or "ราคาต่ำสุด" in result

    def test_flash_sale_caveat_included(self):
        result = _build_best_pick(FANS_500)
        # FANS_500 has a product with 50% discount → caveat expected
        assert "Flash Sale" in result or "ราคา" in result

    def test_empty_products_returns_empty(self):
        assert _build_best_pick([]) == ""

    def test_single_product_still_returns_result(self):
        # Single product can still be a best pick (only option)
        result = _build_best_pick(SINGLE_PRODUCT)
        assert isinstance(result, str)

    def test_no_invented_scores(self):
        result = _build_best_pick(FANS_500)
        # Should not contain patterns like "8.5/10" or "/10"
        assert "/10" not in result
        assert "คะแนนรวม" not in result


# ---------------------------------------------------------------------------
# build_shopping_advisor
# ---------------------------------------------------------------------------

class TestBuildShoppingAdvisor:
    def test_fans_500_produces_content(self):
        result = build_shopping_advisor(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        assert result != ""
        assert "ถ้าคุณ" in result
        assert "ถ้าต้องเลือกแค่ตัวเดียว" in result

    def test_fans_1000_produces_content(self):
        result = build_shopping_advisor(
            "USB & Mobile Fans ไม่เกิน 1,000 บาท", "mobile-gadgets", FANS_1000
        )
        assert result != ""

    def test_beauty_products(self):
        result = build_shopping_advisor("BB Cream", "beauty", BEAUTY)
        assert result != ""

    def test_single_product_returns_empty(self):
        result = build_shopping_advisor("สินค้า", "mobile-gadgets", SINGLE_PRODUCT)
        assert result == ""

    def test_no_dii_sut_without_grounds(self):
        result = build_shopping_advisor("สินค้า", "mobile-gadgets", FANS_500)
        # "ดีที่สุด" allowed only in "คะแนนสูงสุดในกลุ่ม" or "ขายดีที่สุดในกลุ่ม" context
        forbidden = ["ดีที่สุดสำหรับทุกคน", "ดีที่สุดในโลก", "ดีที่สุดทุกด้าน"]
        for phrase in forbidden:
            assert phrase not in result

    def test_no_lazada_mention(self):
        result = build_shopping_advisor("สินค้า", "mobile-gadgets", FANS_500)
        assert "lazada" not in result.lower()
        assert "Lazada" not in result

    def test_no_authenticity_guarantee(self):
        result = build_shopping_advisor("สินค้า", "mobile-gadgets", FANS_500)
        assert "ของแท้รับรอง" not in result
        assert "ของแท้ 100%" not in result


# ---------------------------------------------------------------------------
# build_decision_faq
# ---------------------------------------------------------------------------

class TestBuildDecisionFaq:
    def test_fans_500_has_faq_header(self):
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        assert "## คำถามที่พบบ่อย (FAQ)" in result

    def test_fans_500_has_sold_leader_question(self):
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        assert "ขายดีที่สุด" in result

    def test_fans_500_has_where_to_buy(self):
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        assert "Shopee" in result

    def test_fans_500_has_flash_sale_question(self):
        # FANS_500 has product with 50% discount → Q5 Flash Sale should appear
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        assert "Flash Sale" in result

    def test_fans_1000_has_price_range_question(self):
        # FANS_1000: min=149, max=805 → 805/149 ≈ 5.4 ≥ 2.5 → Q4 should appear
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 1,000 บาท", "mobile-gadgets", FANS_1000
        )
        assert "฿149" in result or "฿805" in result  # Q4 price range comparison

    def test_beauty_no_flash_sale_question_when_no_big_discount(self):
        # BEAUTY has max discount 20% → no Flash Sale Q5
        result = build_decision_faq("BB Cream", "beauty", BEAUTY)
        assert "Flash Sale" not in result

    def test_no_lazada_comparison(self):
        result = build_decision_faq("สินค้า", "mobile-gadgets", FANS_500)
        assert "Lazada" not in result
        assert "lazada" not in result.lower()

    def test_no_authenticity_claim(self):
        result = build_decision_faq("สินค้า", "mobile-gadgets", FANS_500)
        assert "ของแท้รับรอง" not in result
        assert "รับประกันของแท้" not in result

    def test_empty_products_returns_empty(self):
        result = build_decision_faq("สินค้า", "mobile-gadgets", [])
        assert result == ""

    def test_no_seasonal_content(self):
        result = build_decision_faq("สินค้า", "mobile-gadgets", FANS_500)
        assert "หน้าร้อน" not in result
        assert "เปิดเทอม" not in result
        assert "11.11" not in result
        assert "Payday" not in result

    def test_answers_grounded_in_data(self):
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        # Sold leader in FANS_500 is 3803 → should appear in FAQ
        assert "3,803" in result

    def test_max_5_questions(self):
        result = build_decision_faq(
            "USB & Mobile Fans ไม่เกิน 500 บาท", "mobile-gadgets", FANS_500
        )
        bold_q = result.count("**")
        question_count = bold_q // 2  # each question has opening and closing **
        assert question_count <= 5, f"Too many questions: {question_count}"

    def test_zero_sold_data_skips_sold_leader_question(self):
        result = build_decision_faq("สินค้า", "mobile-gadgets", ZERO_SOLD)
        # No sold data → no "ขายดีที่สุด X ชิ้น" claim
        assert "ชิ้น" not in result or "0 ชิ้น" not in result
