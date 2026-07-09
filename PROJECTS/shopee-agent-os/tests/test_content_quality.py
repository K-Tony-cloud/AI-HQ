"""Regression tests for content quality fixes.

Coverage:
  - CTA renders as <a> tag (no Pandoc {.affiliate-btn} literal)
  - No duplicate affiliate disclosure in exported body
  - _clean_disclosure strips embedded disclosure from prose
  - detect_placeholders catches {.affiliate-btn}, Discord/internal paths, numeric hrefs
  - _validate_affiliate_url accepts s.shopee.co.th and shope.ee, rejects others
  - URL validation blocks internal paths, Discord commands, numeric itemid as URL
  - Product fallback to product_link when affiliate_link is empty
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_product(
    affiliate_link: str = "",
    affiliate_link_type: str = "none",
    product_link: str = "https://shopee.co.th/product/100/1001",
    sale_price: int = 500,
) -> dict:
    return {
        "title": "Test Product",
        "sale_price": sale_price,
        "sale_price_fmt": "฿500",
        "original_price": sale_price,
        "original_price_fmt": "฿500",
        "discount_pct": 0,
        "item_rating": 4.5,
        "shop_rating": 4.5,
        "item_sold": 100,
        "affiliate_link": affiliate_link,
        "affiliate_link_type": affiliate_link_type,
        "product_link": product_link,
        "image_link": "",
        "itemid": 1001,
        "shopid": 100,
    }


# ---------------------------------------------------------------------------
# Tests: _build_product_blocks CTA output
# ---------------------------------------------------------------------------

class TestBuildProductBlocksCTA(unittest.TestCase):

    def _blocks(self, products):
        from shopee_engine.seo_engine import _build_product_blocks
        return _build_product_blocks(products)

    def test_cta_is_html_anchor_not_pandoc(self):
        product = _make_product(affiliate_link="https://s.shopee.co.th/TEST123")
        result = self._blocks([product])
        self.assertNotIn("{.affiliate-btn}", result)
        self.assertIn('<a href="https://s.shopee.co.th/TEST123"', result)
        self.assertIn('class="affiliate-btn"', result)

    def test_cta_uses_product_link_fallback_when_no_affiliate(self):
        product = _make_product(
            affiliate_link="",
            product_link="https://shopee.co.th/product/100/1001",
        )
        result = self._blocks([product])
        self.assertNotIn("{.affiliate-btn}", result)
        self.assertIn('href="https://shopee.co.th/product/100/1001"', result)

    def test_no_cta_when_both_links_empty(self):
        product = _make_product(affiliate_link="", product_link="")
        result = self._blocks([product])
        self.assertNotIn("affiliate-btn", result)
        self.assertNotIn("<a href", result)

    def test_cta_has_rel_sponsored_nofollow(self):
        product = _make_product(affiliate_link="https://s.shopee.co.th/TEST123")
        result = self._blocks([product])
        self.assertIn('rel="sponsored nofollow noopener"', result)

    def test_cta_target_blank(self):
        product = _make_product(affiliate_link="https://s.shopee.co.th/TEST123")
        result = self._blocks([product])
        self.assertIn('target="_blank"', result)

    def test_non_affiliate_fallback_shows_note(self):
        product = _make_product(
            affiliate_link="",
            product_link="https://shopee.co.th/product/100/1001",
        )
        result = self._blocks([product])
        self.assertIn('non-affiliate-note', result)
        self.assertIn('ลิงก์ตรง Shopee', result)

    def test_non_affiliate_fallback_no_sponsored_rel(self):
        product = _make_product(
            affiliate_link="",
            product_link="https://shopee.co.th/product/100/1001",
        )
        result = self._blocks([product])
        self.assertNotIn('rel="sponsored', result)
        self.assertIn('rel="nofollow noopener"', result)

    def test_affiliate_cta_no_non_affiliate_note(self):
        product = _make_product(affiliate_link="https://s.shopee.co.th/TEST123")
        result = self._blocks([product])
        self.assertNotIn('non-affiliate-note', result)


# ---------------------------------------------------------------------------
# Tests: no duplicate disclosure in exported body
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: _build_template_summary
# ---------------------------------------------------------------------------

class TestBuildTemplateSummary(unittest.TestCase):

    def _summary(self, products):
        from shopee_engine.article_exporter import _build_template_summary
        return _build_template_summary("พัดลม USB", products)

    def test_never_empty(self):
        result = self._summary([_make_product(sale_price=500)])
        self.assertTrue(len(result) > 0)

    def test_empty_products_returns_fallback(self):
        result = self._summary([])
        self.assertTrue(len(result) > 0)
        self.assertNotIn("บทความนี้มีลิงก์ Affiliate", result)

    def test_references_cheapest_price(self):
        cheap = _make_product(sale_price=100)
        cheap["sale_price_fmt"] = "฿100"
        cheap["title"] = "พัดลมราคาถูก"
        result = self._summary([cheap, _make_product(sale_price=500)])
        self.assertIn("฿100", result)

    def test_references_product_title(self):
        p = _make_product(sale_price=300)
        p["title"] = "พัดลมพกพารุ่นพิเศษ"
        p["item_rating"] = 4.9
        result = self._summary([p])
        self.assertIn("พัดลมพกพา", result)

    def test_different_products_give_different_summaries(self):
        products_a = [_make_product(sale_price=100), _make_product(sale_price=300)]
        products_a[0]["title"] = "รุ่น A ราคาถูก"
        products_a[0]["sale_price_fmt"] = "฿100"
        products_a[1]["title"] = "รุ่น A กลาง"
        products_a[1]["sale_price_fmt"] = "฿300"

        products_b = [_make_product(sale_price=500), _make_product(sale_price=900)]
        products_b[0]["title"] = "รุ่น B เริ่มต้น"
        products_b[0]["sale_price_fmt"] = "฿500"
        products_b[1]["title"] = "รุ่น B พรีเมียม"
        products_b[1]["sale_price_fmt"] = "฿900"

        from shopee_engine.article_exporter import _build_template_summary
        s_a = _build_template_summary("พัดลม", products_a)
        s_b = _build_template_summary("พัดลม", products_b)
        self.assertNotEqual(s_a, s_b)

    def test_no_disclosure_text_in_summary(self):
        result = self._summary([_make_product(sale_price=500)])
        self.assertNotIn("Affiliate", result)
        self.assertNotIn("คอมมิชชัน", result)


# ---------------------------------------------------------------------------
# Tests: _build_export_body always includes ## บทสรุป
# ---------------------------------------------------------------------------

class TestExportBodyAlwaysHasSummary(unittest.TestCase):

    def _body(self, products=None, prose=None):
        from shopee_engine.article_exporter import _build_export_body
        products = products or [_make_product(sale_price=500)]
        return _build_export_body({"keyword": "พัดลม"}, products, prose or {})

    def test_summary_heading_always_present(self):
        body = self._body()
        self.assertIn("## บทสรุป", body)

    def test_summary_heading_appears_exactly_once(self):
        body = self._body()
        self.assertEqual(body.count("## บทสรุป"), 1)

    def test_summary_content_non_empty(self):
        body = self._body()
        idx = body.index("## บทสรุป")
        rest = body[idx + len("## บทสรุป"):].lstrip("\n")
        # Should have at least one non-empty line before next heading
        summary_text = rest.split("\n## ")[0].strip()
        self.assertTrue(len(summary_text) > 10)

    def test_summary_before_faq(self):
        body = self._body()
        idx_summary = body.index("## บทสรุป")
        idx_faq = body.index("## คำถามที่พบบ่อย")
        self.assertLess(idx_summary, idx_faq)

    def test_stored_prose_summary_used_when_non_empty(self):
        body = self._body(prose={"บทสรุป": "สรุปพิเศษที่เขียนไว้แล้ว"})
        self.assertIn("สรุปพิเศษที่เขียนไว้แล้ว", body)

    def test_template_summary_used_when_prose_empty(self):
        body = self._body(prose={"บทสรุป": ""})
        # Should still have summary heading and non-empty content
        self.assertIn("## บทสรุป", body)
        idx = body.index("## บทสรุป")
        rest = body[idx + len("## บทสรุป"):].split("\n## ")[0].strip()
        self.assertTrue(len(rest) > 10)


class TestNoDisclosureInBody(unittest.TestCase):

    def _get_body(self, products, prose=None):
        from shopee_engine.article_exporter import _build_export_body
        article = {"keyword": "test keyword"}
        prose = prose or {}
        return _build_export_body(article, products, prose)

    def test_no_affiliate_disclosure_in_body(self):
        product = _make_product(affiliate_link="https://s.shopee.co.th/TEST123")
        body = self._get_body([product])
        self.assertNotIn("บทความนี้มีลิงก์ Affiliate", body)

    def test_no_dashes_disclosure_footer(self):
        product = _make_product(affiliate_link="https://s.shopee.co.th/TEST123")
        body = self._get_body([product])
        self.assertNotIn("*บทความนี้มีลิงก์", body)


# ---------------------------------------------------------------------------
# Tests: _clean_disclosure strips embedded disclosure from prose
# ---------------------------------------------------------------------------

class TestCleanDisclosure(unittest.TestCase):

    def _clean(self, text):
        from shopee_engine.article_exporter import _clean_disclosure
        return _clean_disclosure(text)

    def test_strips_disclosure_footer(self):
        text = (
            "สรุปผลการทดสอบ\n\n"
            "---\n\n"
            "*บทความนี้มีลิงก์ Affiliate — เมื่อซื้อสินค้าผ่านลิงก์ ผู้เขียนอาจได้รับค่าคอมมิชชัน "
            "โดยไม่มีผลต่อราคาสินค้าสำหรับผู้ซื้อ*\n"
        )
        result = self._clean(text)
        self.assertNotIn("บทความนี้มีลิงก์ Affiliate", result)
        self.assertIn("สรุปผลการทดสอบ", result)

    def test_clean_text_unchanged(self):
        text = "ข้อมูลที่ดีและเป็นประโยชน์"
        result = self._clean(text)
        self.assertEqual(result, text)


# ---------------------------------------------------------------------------
# Tests: detect_placeholders catches content quality issues
# ---------------------------------------------------------------------------

class TestDetectPlaceholders(unittest.TestCase):

    def _check(self, content):
        from shopee_engine.article_exporter import detect_placeholders
        return detect_placeholders(content)

    def test_catches_pandoc_affiliate_btn(self):
        content = "[ดูสินค้าบน Shopee](https://s.shopee.co.th/ABC){.affiliate-btn}"
        issues = self._check(content)
        self.assertTrue(any("{.affiliate-btn}" in i or "Pandoc" in i for i in issues))

    def test_catches_discord_command_in_href(self):
        content = '<a href="/seo-publish">Click</a>'
        issues = self._check(content)
        self.assertTrue(any("Discord" in i or "/seo-" in i for i in issues))

    def test_catches_internal_affiliate_path(self):
        content = '<a href="/affiliate-link-add-product">Link</a>'
        issues = self._check(content)
        self.assertTrue(len(issues) > 0)

    def test_catches_numeric_itemid_as_href(self):
        content = '<a href="25626042159">Link</a>'
        issues = self._check(content)
        self.assertTrue(any("Numeric" in i or "itemid" in i.lower() for i in issues))

    def test_clean_content_passes(self):
        content = '<a href="https://s.shopee.co.th/TEST123" class="affiliate-btn">ดูสินค้า</a>'
        issues = self._check(content)
        self.assertEqual(issues, [])


# ---------------------------------------------------------------------------
# Tests: _validate_affiliate_url
# ---------------------------------------------------------------------------

class TestValidateAffiliateUrl(unittest.TestCase):

    def _validate(self, url):
        from shopee_engine.seo_engine import _validate_affiliate_url
        return _validate_affiliate_url(url)

    def test_s_shopee_co_th_accepted(self):
        self.assertIsNone(self._validate("https://s.shopee.co.th/6pyMS1yPF1"))

    def test_shope_ee_accepted(self):
        self.assertIsNone(self._validate("https://shope.ee/an_redir?origin_link=test"))

    def test_empty_returns_none(self):
        self.assertIsNone(self._validate(""))

    def test_shopee_co_th_rejected(self):
        err = self._validate("https://shopee.co.th/product/100/1001")
        self.assertIsNotNone(err)
        self.assertIn("affiliate host", err)

    def test_discord_command_path_rejected(self):
        err = self._validate("/affiliate-link-add-product")
        self.assertIsNotNone(err)

    def test_numeric_string_rejected(self):
        err = self._validate("25626042159")
        self.assertIsNotNone(err)

    def test_internal_path_rejected(self):
        err = self._validate("/seo-publish")
        self.assertIsNotNone(err)


# ---------------------------------------------------------------------------
# Tests: URL validation blocks in validate_article_for_review
# ---------------------------------------------------------------------------

def _make_test_db_with_bad_links() -> str:
    """Create DB with article that has bad affiliate URLs tagged as 'confirmed'."""
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)

    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE seo_articles (
            id INTEGER PRIMARY KEY, article_id VARCHAR UNIQUE NOT NULL,
            keyword VARCHAR NOT NULL, category VARCHAR DEFAULT 'mobile-gadgets',
            title VARCHAR DEFAULT 'Test Article', meta_description VARCHAR DEFAULT 'Test meta',
            content_md TEXT DEFAULT '## Test\n' || repeat('x', 600),
            status VARCHAR DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_product_sync TIMESTAMP, affiliate_disclosure BOOLEAN DEFAULT true,
            published_path VARCHAR DEFAULT '', git_commit_hash VARCHAR DEFAULT '',
            reviewed_at TIMESTAMP, review_note VARCHAR DEFAULT '',
            published_at TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE seo_article_products (
            id INTEGER PRIMARY KEY, article_id VARCHAR NOT NULL,
            itemid BIGINT, shopid BIGINT,
            product_title VARCHAR DEFAULT '', sale_price BIGINT DEFAULT 0,
            image_link VARCHAR DEFAULT '', affiliate_link VARCHAR DEFAULT '',
            affiliate_link_type VARCHAR DEFAULT 'confirmed',
            opportunity_score DOUBLE DEFAULT 0, rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        INSERT INTO seo_articles (id, article_id, keyword, title, meta_description, content_md, category)
        VALUES (1, 'art-bad', 'test', 'Test', 'Test meta', '## Test\n' || repeat('y', 600), 'mobile-gadgets')
    """)
    # Insert 3 products: 1 good, 1 with Discord path, 1 with numeric itemid
    con.execute("""
        INSERT INTO seo_article_products
            (id, article_id, itemid, shopid, product_title, affiliate_link, affiliate_link_type, rank_in_article)
        VALUES
            (1, 'art-bad', 1001, 100, 'Good Product', 'https://s.shopee.co.th/GOOD123', 'confirmed', 1),
            (2, 'art-bad', 1002, 101, 'Bad Product 1', '/affiliate-link-add-product', 'confirmed', 2),
            (3, 'art-bad', 1003, 102, 'Bad Product 2', '1002', 'confirmed', 3)
    """)
    con.close()
    return path


class TestValidationBlocksBadUrls(unittest.TestCase):

    def test_review_blocks_discord_command_link(self):
        from pathlib import Path
        from unittest.mock import patch
        from shopee_engine.seo_engine import validate_article_for_review

        db = _make_test_db_with_bad_links()
        with patch("shopee_engine.config.config.db_path", Path(db)):
            result = validate_article_for_review("art-bad")

        self.assertFalse(result["valid"])
        errors = " ".join(result["errors"])
        self.assertTrue(
            any("1002" in e or "1003" in e or "affiliate host" in e or "scheme" in e for e in result["errors"]),
            f"Expected URL error in: {errors}",
        )

    def test_publish_blocks_discord_command_link(self):
        from pathlib import Path
        from unittest.mock import patch
        from shopee_engine.seo_engine import validate_article_for_publish

        db = _make_test_db_with_bad_links()
        con = duckdb.connect(db)
        con.execute("UPDATE seo_articles SET status='reviewed' WHERE article_id='art-bad'")
        con.close()

        with patch("shopee_engine.config.config.db_path", Path(db)):
            result = validate_article_for_publish("art-bad")

        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
