"""Tests for shopee_engine/editorial_team.py."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from shopee_engine.editorial_team import (
    _build_product_brief,
    _CATEGORY_CONTEXT,
    generate_article_content,
)

# A key that passes the real-key validator (starts with sk-ant-api, len > 40)
_VALID_TEST_KEY = "sk-ant-api03-" + "a" * 50

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PRODUCTS = [
    {
        "title": "พัดลม USB Mini ขนาดเล็ก พกพาได้",
        "sale_price": 199,
        "sale_price_fmt": "199 บาท",
        "item_rating": 4.7,
        "item_sold": 12_000,
        "image_link": "https://example.com/img1.jpg",
        "affiliate_link": "https://s.shopee.co.th/abc",
        "product_link": "https://shopee.co.th/p1",
        "original_price": 299,
        "original_price_fmt": "299 บาท",
        "discount_pct": 33,
        "shop_rating": 4.8,
        "itemid": 111,
        "shopid": 222,
    },
    {
        "title": "พัดลมตั้งโต๊ะ USB แบบพับได้ 3 ระดับ",
        "sale_price": 350,
        "sale_price_fmt": "350 บาท",
        "item_rating": 4.5,
        "item_sold": 8_500,
        "image_link": "https://example.com/img2.jpg",
        "affiliate_link": "https://s.shopee.co.th/def",
        "product_link": "https://shopee.co.th/p2",
        "original_price": 350,
        "original_price_fmt": "350 บาท",
        "discount_pct": 0,
        "shop_rating": 4.6,
        "itemid": 333,
        "shopid": 444,
    },
    {
        "title": "พัดลมพกพา ไร้สาย ชาร์จ USB-C",
        "sale_price": 490,
        "sale_price_fmt": "490 บาท",
        "item_rating": 4.9,
        "item_sold": 5_200,
        "image_link": "https://example.com/img3.jpg",
        "affiliate_link": "",
        "product_link": "https://shopee.co.th/p3",
        "original_price": 490,
        "original_price_fmt": "490 บาท",
        "discount_pct": 0,
        "shop_rating": 4.9,
        "itemid": 555,
        "shopid": 666,
    },
]

GOOD_EDITORIAL_RESPONSE = {
    "intro": "ช่วงหน้าร้อนแบบนี้ พัดลม USB กลายเป็นสิ่งที่ขาดไม่ได้ในออฟฟิศ คอนโด หรือแม้แต่รถยนต์",
    "buying_scenario": "คนที่ค้นหาพัดลม USB ส่วนใหญ่ต้องการพัดลมพกพาสำหรับใช้ที่โต๊ะทำงาน",
    "for_whom": "- คนทำงานออฟฟิศที่ต้องการลมเย็นส่วนตัว\n- นักเรียนที่ใช้ laptop",
    "not_for_whom": "- คนที่ต้องการลมแรงแบบพัดลมตั้งพื้นขนาดใหญ่",
    "buying_guide": "เวลาเลือกพัดลม USB ควรดูกำลังไฟ (Watt) และจำนวนใบพัด",
    "product_highlights": {
        "1": "เหมาะสำหรับพกพา ขนาดกะทัดรัดใส่กระเป๋าได้",
        "2": "ปรับความแรงได้ 3 ระดับ เหมาะกับโต๊ะทำงาน",
        "3": "ชาร์จ USB-C สะดวก ไม่ต้องหาสายพิเศษ",
    },
    "summary": "ก่อนตัดสินใจซื้อ ลองเปรียบเทียบขนาดและ spec ตามการใช้งานจริง",
}


def _make_mock_response(payload: dict) -> MagicMock:
    """Build a mock anthropic Messages response."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(payload, ensure_ascii=False)
    mock_msg = MagicMock()
    mock_msg.content = [mock_content]
    return mock_msg


# ---------------------------------------------------------------------------
# TestBuildProductBrief
# ---------------------------------------------------------------------------

class TestBuildProductBrief:
    def test_includes_all_products(self):
        brief = _build_product_brief(SAMPLE_PRODUCTS)
        for p in SAMPLE_PRODUCTS:
            assert p["title"][:30] in brief

    def test_includes_price_and_rating(self):
        brief = _build_product_brief(SAMPLE_PRODUCTS)
        assert "199" in brief
        assert "4.7" in brief

    def test_empty_products(self):
        brief = _build_product_brief([])
        assert brief == ""

    def test_caps_at_8_products(self):
        many = SAMPLE_PRODUCTS * 5
        brief = _build_product_brief(many)
        lines = [l for l in brief.split("\n") if l.strip().startswith(("1.", "2.", "8.", "9.", "10."))]
        assert not any(l.startswith("9.") or l.startswith("10.") for l in lines)


# ---------------------------------------------------------------------------
# TestCategoryContext
# ---------------------------------------------------------------------------

class TestCategoryContext:
    def test_all_expected_categories_present(self):
        for cat in ("home-living", "mobile-gadgets", "beauty", "health", "sports", "baby-kids", "food-drinks"):
            assert cat in _CATEGORY_CONTEXT

    def test_each_category_has_required_keys(self):
        for cat, data in _CATEGORY_CONTEXT.items():
            assert "contexts" in data, f"Missing 'contexts' for {cat}"
            assert "pain_points" in data, f"Missing 'pain_points' for {cat}"
            assert isinstance(data["contexts"], list)
            assert len(data["contexts"]) > 0


# ---------------------------------------------------------------------------
# TestGenerateArticleContentSuccess
# ---------------------------------------------------------------------------

class TestGenerateArticleContentSuccess:
    @patch("shopee_engine.editorial_team.anthropic")
    def test_returns_success_true(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(GOOD_EDITORIAL_RESPONSE)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_success"] is True

    @patch("shopee_engine.editorial_team.anthropic")
    def test_all_required_keys_present(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(GOOD_EDITORIAL_RESPONSE)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        for key in ("intro", "buying_scenario", "for_whom", "not_for_whom",
                    "buying_guide", "product_highlights", "summary"):
            assert key in result, f"Missing key: {key}"

    @patch("shopee_engine.editorial_team.anthropic")
    def test_product_highlights_keys_are_strings(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(GOOD_EDITORIAL_RESPONSE)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        highlights = result["product_highlights"]
        assert isinstance(highlights, dict)
        for k in highlights:
            assert isinstance(k, str), f"Key {k!r} should be str"

    @patch("shopee_engine.editorial_team.anthropic")
    def test_product_highlights_covers_all_products(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(GOOD_EDITORIAL_RESPONSE)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        highlights = result["product_highlights"]
        expected_keys = {str(i) for i in range(1, len(SAMPLE_PRODUCTS) + 1)}
        assert expected_keys == set(highlights.keys())

    @patch("shopee_engine.editorial_team.anthropic")
    def test_model_stored_in_result_claude(self, mock_anthropic):
        """When Claude succeeds, _model should be the Claude model name."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(GOOD_EDITORIAL_RESPONSE)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_model"] == "claude-sonnet-4-6"

    def test_model_stored_in_result_deterministic(self):
        """When no AI key, _model should be 'deterministic'."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_model"] == "deterministic"


# ---------------------------------------------------------------------------
# TestGenerateArticleContentMarkdownFences
# ---------------------------------------------------------------------------

class TestMarkdownFenceStripping:
    """Model sometimes wraps JSON in markdown code fences — must be stripped."""

    @patch("shopee_engine.editorial_team.anthropic")
    def test_strips_json_code_fence(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        wrapped = "```json\n" + json.dumps(GOOD_EDITORIAL_RESPONSE) + "\n```"
        mock_content = MagicMock()
        mock_content.text = wrapped
        mock_msg = MagicMock()
        mock_msg.content = [mock_content]
        mock_client.messages.create.return_value = mock_msg

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_success"] is True
        assert result["intro"] == GOOD_EDITORIAL_RESPONSE["intro"]


# ---------------------------------------------------------------------------
# TestGenerateArticleContentFallback
# ---------------------------------------------------------------------------

class TestGenerateArticleContentFallback:
    """
    With the provider router, errors fall through to deterministic mode.
    The only _success=False case is if deterministic itself crashes (very rare).
    """

    def test_no_api_key_uses_deterministic(self):
        """No API key → skip all AI providers → deterministic → success."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_success"] is True
        assert result["_model"] == "deterministic"

    def test_no_api_key_has_all_sections(self):
        """Deterministic mode returns non-empty content for all required sections."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        for key in ("intro", "buying_scenario", "for_whom", "not_for_whom",
                    "buying_guide", "summary"):
            assert result[key], f"Section '{key}' should not be empty in deterministic mode"
        assert result["product_highlights"], "product_highlights should not be empty"

    @patch("shopee_engine.editorial_team.anthropic")
    def test_claude_error_falls_back_to_deterministic(self, mock_anthropic):
        """Claude API error → deterministic fallback → still success."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("API timeout")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_success"] is True
        assert result["_model"] == "deterministic"

    @patch("shopee_engine.editorial_team.anthropic")
    def test_claude_invalid_json_falls_back_to_deterministic(self, mock_anthropic):
        """Claude returns non-JSON → parse fails → deterministic fallback → success."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_content = MagicMock()
        mock_content.text = "This is not JSON at all."
        mock_msg = MagicMock()
        mock_msg.content = [mock_content]
        mock_client.messages.create.return_value = mock_msg

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        assert result["_success"] is True
        assert result["_model"] == "deterministic"


# ---------------------------------------------------------------------------
# TestProductHighlightsIntConversion
# ---------------------------------------------------------------------------

class TestProductHighlightsIntConversion:
    """Some JSON parsers may produce int keys — must be converted to str."""

    @patch("shopee_engine.editorial_team.anthropic")
    def test_int_keys_converted_to_str(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        payload = dict(GOOD_EDITORIAL_RESPONSE)
        payload["product_highlights"] = {1: "text1", 2: "text2", 3: "text3"}

        mock_content = MagicMock()
        mock_content.text = json.dumps(payload)
        mock_msg = MagicMock()
        mock_msg.content = [mock_content]
        mock_client.messages.create.return_value = mock_msg

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("พัดลม USB", "mobile-gadgets", SAMPLE_PRODUCTS)

        for k in result["product_highlights"]:
            assert isinstance(k, str)


# ---------------------------------------------------------------------------
# TestUnknownCategoryGraceful
# ---------------------------------------------------------------------------

class TestUnknownCategoryGraceful:
    @patch("shopee_engine.editorial_team.anthropic")
    def test_unknown_category_does_not_crash(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(GOOD_EDITORIAL_RESPONSE)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _VALID_TEST_KEY}):
            result = generate_article_content("สินค้าทั่วไป", "unknown-category", SAMPLE_PRODUCTS)

        assert result["_success"] is True
