"""Tests for shopee_engine/editorial_batch.py."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shopee_engine.editorial_batch import (
    EDITORIAL_VERSION,
    REWRITABLE_SECTIONS,
    _check_invented_numbers,
    _check_prohibited,
    _extract_buying_context_parts,
    _extract_known_numbers,
    _rebuild_buying_context_block,
    _score_section,
    _validate_article_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PRODUCTS = [
    {
        "product_id": "111",
        "rank":        1,
        "title":       "พัดลม USB Mini ขนาดเล็ก 3 ระดับ",
        "price":       199,
        "rating":      4.7,
        "sold_count":  12000,
        "affiliate_link": "https://s.shopee.co.th/abc",
        "image_link":  "https://example.com/img1.jpg",
        "source_facts": {"price": 199, "rating": 4.7, "sold_count": 12000},
    },
    {
        "product_id": "222",
        "rank":        2,
        "title":       "พัดลม USB ตั้งโต๊ะ พับได้ SPF 50 style",
        "price":       350,
        "rating":      4.5,
        "sold_count":  8500,
        "affiliate_link": "https://s.shopee.co.th/def",
        "image_link":  "https://example.com/img2.jpg",
        "source_facts": {"price": 350, "rating": 4.5, "sold_count": 8500},
    },
]

PROTECTED_FIELDS = {
    "product_order":   ["111", "222"],
    "affiliate_links": {"111": "https://s.shopee.co.th/abc", "222": "https://s.shopee.co.th/def"},
    "image_urls":      {"111": "https://example.com/img1.jpg", "222": "https://example.com/img2.jpg"},
}

SOURCE_ARTICLE = {
    "article_id":     "test-article-001",
    "keyword":        "พัดลม USB",
    "category":       "mobile-gadgets",
    "products":       SAMPLE_PRODUCTS,
    "protected_fields": PROTECTED_FIELDS,
    "current_sections": {
        "บทนำ":                   "บทนำเดิม",
        "buying_scenario":        "",
        "for_whom":               "",
        "not_for_whom":           "",
        "คำแนะนำการเลือกซื้อ":   "คู่มือเดิม",
        "บทสรุป":                 "สรุปเดิม",
        "product_highlights":     {},
    },
}

GOOD_OUTPUT = {
    "article_id": "test-article-001",
    "rewritten_sections": {
        "บทนำ":     "ช่วงหน้าร้อนแบบนี้ ออฟฟิศที่แอร์ไม่เย็นพอ หรือห้องพักที่ไม่มีเครื่องปรับอากาศ พัดลม USB กลายเป็นตัวช่วยที่หลายคนนึกถึง",
        "บทสรุป":   "ถ้างบจำกัด สินค้า #1 ฿199 เป็นจุดเริ่มต้นที่คุ้ม สินค้า #1 ขายแล้ว 12,000 ชิ้น ราคาบน Shopee เปลี่ยนตาม Flash Sale",
        "product_highlights": {
            "111": "เล็กที่สุดในกลุ่ม พกใส่กระเป๋าได้ ปรับ 3 ระดับ",
            "222": "เหมาะกับโต๊ะทำงาน พับเก็บได้สะดวก",
        },
    },
    "validation_notes": "humanized intro, summary references rank#1",
    "confidence": 0.9,
    "factual_claims_added": ["rank#1 sold_count=12,000", "rank#1 price=199"],
}


# ---------------------------------------------------------------------------
# _score_section
# ---------------------------------------------------------------------------

class TestScoreSection:
    def test_empty_returns_zero(self):
        score, tags = _score_section("บทนำ", "")
        assert score == 0.0
        assert "empty" in tags

    def test_very_short_returns_low(self):
        score, tags = _score_section("บทนำ", "สั้นมาก")
        assert score <= 0.3

    def test_generic_all_options_penalised(self):
        score, tags = _score_section("บทนำ", "ทั้ง 5 ตัวเลือกในบทความนี้ล้วนคัดสรรมาแล้ว")
        assert "generic_all_options" in tags
        assert score < 0.7

    def test_good_text_scores_high(self):
        long_good = "ช่วงหน้าร้อน พัดลม USB กลายเป็นสิ่งจำเป็นในออฟฟิศและคอนโด ทั้งขนาด ราคา และกำลังไฟต่างกัน บทความนี้ช่วยเลือกให้ตรงการใช้งาน"
        score, tags = _score_section("บทนำ", long_good)
        assert score >= 0.7

    def test_for_whom_sparse_bullets(self):
        # Must be > 30 chars so the too_short guard doesn't trigger before bullet check
        score, tags = _score_section("for_whom", "- เหมาะกับคนทำงานออฟฟิศที่ต้องการลมเย็นส่วนตัว")
        assert "sparse_bullets" in tags

    def test_for_whom_enough_bullets(self):
        text = "- คนทำงานออฟฟิศ\n- นักเรียน\n- คนนอนในห้องไม่มีแอร์"
        score, tags = _score_section("for_whom", text)
        assert "sparse_bullets" not in tags


# ---------------------------------------------------------------------------
# _check_prohibited
# ---------------------------------------------------------------------------

class TestCheckProhibited:
    def test_guarantee_thai(self):
        assert "guarantee" in _check_prohibited("ดีที่สุดแน่นอน")

    def test_fake_testimonial(self):
        assert "fake_testimonial" in _check_prohibited("ฉันได้ทดลองใช้แล้ว มันดีมาก")

    def test_guarantee_pct(self):
        assert "guarantee_pct" in _check_prohibited("100% มั่นใจว่าดี")

    def test_clean_text_no_hits(self):
        clean = "พัดลม USB ขายดีมากใน Shopee มียอดขายกว่า 12,000 ชิ้น"
        assert _check_prohibited(clean) == []


# ---------------------------------------------------------------------------
# _extract_known_numbers
# ---------------------------------------------------------------------------

class TestExtractKnownNumbers:
    def test_includes_prices(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        assert "199" in nums
        assert "350" in nums

    def test_includes_sold_count_formatted(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        assert "12000" in nums or "12,000" in nums

    def test_includes_rating_decimal(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        assert "4.7" in nums

    def test_includes_numbers_from_title(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        assert "3" in nums   # "3 ระดับ" in title of product 111
        assert "50" in nums  # "SPF 50" in title of product 222


# ---------------------------------------------------------------------------
# _check_invented_numbers
# ---------------------------------------------------------------------------

class TestCheckInventedNumbers:
    def test_known_price_passes(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        result = _check_invented_numbers("ราคา 199 บาท ถูกที่สุด", nums)
        assert result == []

    def test_invented_price_fails(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        result = _check_invented_numbers("ราคาเพียง 99 บาท", nums)
        assert len(result) > 0

    def test_invented_sold_count_fails(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        result = _check_invented_numbers("ขายแล้ว 50,000 ชิ้น", nums)
        assert len(result) > 0

    def test_year_passes(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        result = _check_invented_numbers("อัปเดตปี 2026", nums)
        assert result == []

    def test_known_sold_count_passes(self):
        nums = _extract_known_numbers(SAMPLE_PRODUCTS)
        result = _check_invented_numbers("ขายแล้ว 12,000 ชิ้น", nums)
        assert result == []


# ---------------------------------------------------------------------------
# _extract_buying_context_parts
# ---------------------------------------------------------------------------

class TestExtractBuyingContextParts:
    def test_full_section(self):
        content_md = """---
---
## บทนำ

intro text

## บริบทการซื้อ

buying text here

**เหมาะกับ:**

- คนทำงาน
- นักเรียน

**อาจไม่ใช่ตัวเลือกที่ดีถ้า:**

- คนต้องการลมแรงมาก

## บทสรุป

summary
"""
        buying, fw, nfw = _extract_buying_context_parts(content_md)
        assert "buying text" in buying
        assert "คนทำงาน" in fw
        assert "คนต้องการลมแรงมาก" in nfw

    def test_no_buying_context_returns_empty(self):
        content_md = "## บทนำ\n\nintro\n\n## บทสรุป\n\nsummary"
        buying, fw, nfw = _extract_buying_context_parts(content_md)
        assert buying == fw == nfw == ""

    def test_buying_context_no_for_whom(self):
        content_md = "## บริบทการซื้อ\n\nbuying text only\n\n## บทสรุป\n\nfoo"
        buying, fw, nfw = _extract_buying_context_parts(content_md)
        assert "buying text only" in buying
        assert fw == ""
        assert nfw == ""


# ---------------------------------------------------------------------------
# _rebuild_buying_context_block
# ---------------------------------------------------------------------------

class TestRebuildBuyingContextBlock:
    def test_all_parts(self):
        result = _rebuild_buying_context_block("scenario", "- fw1\n- fw2", "- nfw1")
        assert "scenario" in result
        assert "**เหมาะกับ:**" in result
        assert "**อาจไม่ใช่ตัวเลือกที่ดีถ้า:**" in result

    def test_no_for_whom(self):
        result = _rebuild_buying_context_block("scenario only", "", "")
        assert result == "scenario only"
        assert "เหมาะกับ" not in result

    def test_empty_all_returns_empty(self):
        result = _rebuild_buying_context_block("", "", "")
        assert result == ""


# ---------------------------------------------------------------------------
# _validate_article_output
# ---------------------------------------------------------------------------

class TestValidateArticleOutput:
    def test_good_output_no_errors(self):
        errors, warns = _validate_article_output(GOOD_OUTPUT, SOURCE_ARTICLE)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_empty_rewritten_sections(self):
        bad = {"article_id": "test-article-001", "rewritten_sections": {}}
        errors, _ = _validate_article_output(bad, SOURCE_ARTICLE)
        assert any("empty" in e.lower() for e in errors)

    def test_unknown_section_key_fails(self):
        bad = {
            "article_id": "test-article-001",
            "rewritten_sections": {"forbidden_section": "hack"},
        }
        errors, _ = _validate_article_output(bad, SOURCE_ARTICLE)
        assert any("not in REWRITABLE" in e for e in errors)

    def test_unknown_product_id_in_highlights_fails(self):
        bad = {
            "article_id": "test-article-001",
            "rewritten_sections": {
                "product_highlights": {"999999": "fake product"},
            },
        }
        errors, _ = _validate_article_output(bad, SOURCE_ARTICLE)
        assert any("999999" in e for e in errors)

    def test_prohibited_guarantee_fails(self):
        bad = {
            "article_id": "test-article-001",
            "rewritten_sections": {
                "บทนำ": "สินค้านี้ดีที่สุดแน่นอน ไม่มีใครสู้ได้",
            },
        }
        errors, _ = _validate_article_output(bad, SOURCE_ARTICLE)
        assert any("guarantee" in e for e in errors)

    def test_prohibited_fake_testimonial_fails(self):
        bad = {
            "article_id": "test-article-001",
            "rewritten_sections": {
                "บทนำ": "ฉันได้ทดลองใช้แล้วและชอบมาก",
            },
        }
        errors, _ = _validate_article_output(bad, SOURCE_ARTICLE)
        assert any("fake_testimonial" in e for e in errors)

    def test_invented_number_fails(self):
        bad = {
            "article_id": "test-article-001",
            "rewritten_sections": {
                "บทสรุป": "ขายแล้ว 99,999 ชิ้น เยี่ยมมาก",
            },
        }
        errors, _ = _validate_article_output(bad, SOURCE_ARTICLE)
        assert any("Invented" in e or "invented" in e for e in errors)

    def test_known_numbers_pass(self):
        ok = {
            "article_id": "test-article-001",
            "rewritten_sections": {
                "บทสรุป": "สินค้า #1 ขายแล้ว 12,000 ชิ้น ราคา 199 บาท",
            },
        }
        errors, _ = _validate_article_output(ok, SOURCE_ARTICLE)
        assert errors == []


# ---------------------------------------------------------------------------
# REWRITABLE_SECTIONS constant
# ---------------------------------------------------------------------------

class TestRewritableSections:
    def test_expected_sections_present(self):
        for sec in ("บทนำ", "buying_scenario", "for_whom", "not_for_whom",
                    "คำแนะนำการเลือกซื้อ", "บทสรุป", "product_highlights"):
            assert sec in REWRITABLE_SECTIONS
