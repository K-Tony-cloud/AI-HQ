"""Tests: /seo-preview product card generation and search keyword parser.

Coverage:
  - get_products_for_preview: returns per-product direct URLs + cmd templates
  - Affiliate status mapping: confirmed / datafeed / missing
  - Direct URL built from shopid+itemid in seo_article_products
  - Missing shopid → url_status='incomplete', no direct_url
  - _keyword_to_term_groups: editorial context stripped (รุ่นไหนดี, year tokens)
  - _extract_price_max: year stripping side effect
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub discord so seo_embeds can be imported without the discord package
if "discord" not in sys.modules:
    sys.modules["discord"] = MagicMock()
    sys.modules["discord.ext"] = MagicMock()
    sys.modules["discord.ext.commands"] = MagicMock()
if "discord_bot.embeds.base" not in sys.modules:
    _base_mock = MagicMock()
    _base_mock.make_embed = MagicMock(return_value=MagicMock())
    sys.modules["discord_bot.embeds.base"] = _base_mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _patch_db(db_path: str):
    return patch("shopee_engine.config.config.db_path", Path(db_path))


def _make_seo_db(products: list[dict]) -> str:
    """Create temp DB with seo_articles + seo_article_products + products."""
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)
    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE seo_articles (
            id INTEGER PRIMARY KEY,
            article_id VARCHAR NOT NULL UNIQUE,
            keyword VARCHAR NOT NULL,
            category VARCHAR DEFAULT '',
            title VARCHAR DEFAULT '',
            meta_description VARCHAR DEFAULT '',
            content_md TEXT DEFAULT '',
            status VARCHAR DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_product_sync TIMESTAMP,
            affiliate_disclosure BOOLEAN DEFAULT true,
            published_path VARCHAR DEFAULT '',
            git_commit_hash VARCHAR DEFAULT '',
            reviewed_at TIMESTAMP,
            review_note VARCHAR DEFAULT '',
            published_at TIMESTAMP,
            category_label VARCHAR DEFAULT '',
            subcategory VARCHAR DEFAULT '',
            subcategory_label VARCHAR DEFAULT ''
        )
    """)
    con.execute("""
        CREATE TABLE seo_article_products (
            id INTEGER PRIMARY KEY,
            article_id VARCHAR NOT NULL,
            itemid BIGINT,
            shopid BIGINT,
            product_title VARCHAR DEFAULT '',
            sale_price BIGINT DEFAULT 0,
            image_link VARCHAR DEFAULT '',
            affiliate_link VARCHAR DEFAULT '',
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score DOUBLE DEFAULT 0,
            rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE products (
            itemid BIGINT, shopid BIGINT,
            title VARCHAR DEFAULT '',
            sale_price BIGINT DEFAULT 0,
            image_link VARCHAR DEFAULT '',
            product_link VARCHAR DEFAULT '',
            shop_name VARCHAR DEFAULT '',
            seller_name VARCHAR DEFAULT '',
            description VARCHAR DEFAULT ''
        )
    """)
    con.execute(
        "INSERT INTO seo_articles (id, article_id, keyword, title) "
        "VALUES (1, 'test-article', 'test keyword', 'Test')"
    )
    for i, p in enumerate(products, 1):
        con.execute(
            "INSERT INTO seo_article_products "
            "(id, article_id, itemid, shopid, product_title, sale_price, "
            " image_link, affiliate_link, affiliate_link_type, rank_in_article) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                i, "test-article",
                p["itemid"], p.get("shopid", 0), p.get("title", "Product"),
                p.get("price", 100), p.get("image", ""),
                p.get("affiliate_link", ""), p.get("link_type", "none"), i,
            ],
        )
        if p.get("shopid"):
            con.execute(
                "INSERT INTO products (itemid, shopid, shop_name) VALUES (?,?,?)",
                [p["itemid"], p["shopid"], p.get("shop_name", "TestShop")],
            )
    con.close()
    return path


# ---------------------------------------------------------------------------
# get_products_for_preview
# ---------------------------------------------------------------------------

class TestGetProductsForPreview(unittest.TestCase):
    def setUp(self):
        self.products_data = [
            {"itemid": 1001, "shopid": 10001, "title": "Product A", "price": 500,
             "link_type": "confirmed", "affiliate_link": "https://s.shopee.co.th/aaa"},
            {"itemid": 1002, "shopid": 10002, "title": "Product B", "price": 800,
             "link_type": "datafeed", "affiliate_link": "https://shope.ee/bbb"},
            {"itemid": 1003, "shopid": 10003, "title": "Product C", "price": 300,
             "link_type": "none", "affiliate_link": ""},
        ]
        self.db_path = _make_seo_db(self.products_data)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def _run(self) -> list[dict]:
        with _patch_db(self.db_path):
            from shopee_engine.seo_engine import get_products_for_preview
            return get_products_for_preview("test-article")

    def test_returns_three_products(self):
        products = self._run()
        self.assertEqual(len(products), 3)

    def test_confirmed_has_correct_status(self):
        products = self._run()
        p1 = next(p for p in products if p["itemid"] == 1001)
        self.assertEqual(p1["affiliate_status"], "confirmed")
        self.assertEqual(p1["aff_icon"], "✅")

    def test_datafeed_has_correct_status(self):
        products = self._run()
        p2 = next(p for p in products if p["itemid"] == 1002)
        self.assertEqual(p2["affiliate_status"], "datafeed")
        self.assertEqual(p2["aff_icon"], "📋")

    def test_missing_has_correct_status(self):
        products = self._run()
        p3 = next(p for p in products if p["itemid"] == 1003)
        self.assertEqual(p3["affiliate_status"], "missing")
        self.assertEqual(p3["aff_icon"], "❌")

    def test_direct_url_built_from_shopid_itemid(self):
        products = self._run()
        for p in products:
            expected = f"https://shopee.co.th/product/{p['shopid']}/{p['itemid']}"
            self.assertEqual(p["direct_url"], expected)
            self.assertEqual(p["url_status"], "resolved")

    def test_missing_shopid_gives_incomplete(self):
        data = [{"itemid": 9001, "shopid": 0, "title": "No Shop", "price": 99, "link_type": "none"}]
        db_path = _make_seo_db(data)
        try:
            with _patch_db(db_path):
                from shopee_engine.seo_engine import get_products_for_preview
                products = get_products_for_preview("test-article")
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0]["url_status"], "incomplete")
            self.assertEqual(products[0]["direct_url"], "")
        finally:
            os.unlink(db_path)

    def test_cmd_template_includes_itemid_and_shopid(self):
        products = self._run()
        p2 = next(p for p in products if p["itemid"] == 1002)
        cmd = p2["cmd_template"]
        self.assertIn("1002", cmd)
        self.assertIn("10002", cmd)
        self.assertIn("/affiliate-link-add-product", cmd)

    def test_confirmed_cmd_template_still_present(self):
        products = self._run()
        p1 = next(p for p in products if p["itemid"] == 1001)
        self.assertIn("/affiliate-link-add-product", p1["cmd_template"])

    def test_rank_order(self):
        products = self._run()
        ranks = [p["rank"] for p in products]
        self.assertEqual(ranks, sorted(ranks))


# ---------------------------------------------------------------------------
# Search keyword parser — editorial context stripping
# ---------------------------------------------------------------------------

class TestKeywordParser(unittest.TestCase):
    def _groups(self, keyword: str) -> list[list[str]]:
        from shopee_engine.seo_engine import _keyword_to_term_groups
        return _keyword_to_term_groups(keyword)

    def _extract(self, keyword: str):
        from shopee_engine.seo_engine import _extract_price_max
        return _extract_price_max(keyword)

    def test_power_bank_ccc_basic(self):
        groups = self._groups("Power Bank CCC")
        terms = [t for g in groups for t in g]
        self.assertTrue(any("bank" in t.lower() or "powerbank" in t.lower() for t in terms))
        self.assertTrue(any("ccc" in t.lower() for t in terms))

    def test_editorial_context_stripped(self):
        groups = self._groups("Power Bank รุ่นไหนดี")
        terms = [t.lower() for g in groups for t in g]
        self.assertNotIn("รุ่นไหนดี", terms)

    def test_ที่มี_stripped(self):
        groups = self._groups("Power Bank ที่มี CCC")
        terms = [t.lower() for g in groups for t in g]
        self.assertNotIn("ที่มี", terms)

    def test_ccc_attribute_preserved(self):
        groups = self._groups("Power Bank ที่มี CCC รุ่นไหนดี")
        terms = [t.lower() for g in groups for t in g]
        self.assertTrue(any("ccc" in t for t in terms))

    def test_year_stripped_by_extract_price_max(self):
        cleaned, price = self._extract("Power Bank CCC ปี 2026")
        self.assertNotIn("2026", cleaned)
        self.assertNotIn("ปี", cleaned)

    def test_price_still_extracted_with_year(self):
        cleaned, price = self._extract("Power Bank ไม่เกิน 1000 บาท ปี 2026")
        self.assertEqual(price, 1000)
        self.assertNotIn("2026", cleaned)

    def test_plain_year_stripped(self):
        cleaned, _ = self._extract("Power Bank 2026")
        self.assertNotIn("2026", cleaned)

    def test_price_without_year_unchanged(self):
        cleaned, price = self._extract("Power Bank ไม่เกิน 500 บาท")
        self.assertEqual(price, 500)
        self.assertNotIn("500", cleaned)


# ---------------------------------------------------------------------------
# Keyword parser — editorial + context regression tests (Phase 3B)
# ---------------------------------------------------------------------------

class TestKeywordParserRegressions(unittest.TestCase):
    """Regression suite for complex editorial/contextual keyword stripping."""

    def _terms(self, keyword: str) -> list[str]:
        from shopee_engine.seo_engine import _keyword_to_term_groups
        return [t for g in _keyword_to_term_groups(keyword) for t in g]

    def _cleaned(self, keyword: str) -> str:
        from shopee_engine.seo_engine import _extract_price_max
        return _extract_price_max(keyword)[0]

    # --- Full complex keyword ---

    def test_full_complex_keyword_power_intent_preserved(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertTrue(any(t in ("power", "bank", "powerbank") for t in terms),
                        f"power/bank missing from {terms}")

    def test_full_complex_keyword_ccc_preserved(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertIn("ccc", terms, f"ccc missing from {terms}")

    def test_full_complex_keyword_pi_stripped(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertNotIn("ปี", terms)

    def test_full_complex_keyword_2026_stripped(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertNotIn("2026", terms)

    def test_full_complex_keyword_runnaiydee_stripped(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertNotIn("รุ่นไหนดี", terms)

    def test_full_complex_keyword_mi_stripped(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertNotIn("มี", terms)

    def test_full_complex_keyword_travel_context_stripped(self):
        terms = self._terms("Power Bank มี CCC รุ่นไหนดี สำหรับเดินทางไปจีน ปี 2026")
        self.assertFalse(any("สำหรับ" in t for t in terms),
                         f"สำหรับ... context leaked into {terms}")

    # --- Year token variants ---

    def test_pi_2026_stripped_from_term_groups(self):
        terms = self._terms("Power Bank CCC ปี 2026")
        self.assertNotIn("ปี", terms)
        self.assertNotIn("2026", terms)

    def test_thai_year_2569_stripped(self):
        terms = self._terms("Power Bank CCC ปี2569")
        self.assertNotIn("ปี2569", terms)
        self.assertNotIn("2569", terms)

    def test_bare_2026_stripped_from_term_groups(self):
        terms = self._terms("Power Bank CCC 2026")
        self.assertNotIn("2026", terms)
        self.assertIn("ccc", terms)

    def test_update_year_phrase_stripped(self):
        terms = self._terms("Power Bank CCC อัปเดตปี 2026")
        self.assertNotIn("ปี", terms)
        self.assertNotIn("2026", terms)
        self.assertNotIn("อัปเดตปี", terms)
        self.assertIn("ccc", terms)

    def test_runnaidee_pi_year_both_stripped(self):
        terms = self._terms("Power Bank CCC รุ่นไหนดี ปี 2026")
        self.assertNotIn("รุ่นไหนดี", terms)
        self.assertNotIn("ปี", terms)
        self.assertNotIn("2026", terms)
        self.assertIn("ccc", terms)

    # --- 3C / CCC synonyms not dropped ---

    def test_3c_travel_context_ccc_not_lost(self):
        terms = self._terms("Power Bank มี 3C สำหรับไปจีน ปี 2026")
        self.assertFalse(any("สำหรับ" in t for t in terms))
        self.assertNotIn("ปี", terms)
        self.assertNotIn("2026", terms)
        self.assertNotIn("มี", terms)
        # 3C should survive (it is a product attribute, not a stopword)
        self.assertTrue(any("3c" in t.lower() or "3" in t for t in terms),
                        f"3c/3C missing from {terms}")

    # --- Stopword "มี" ---

    def test_mi_standalone_stripped(self):
        terms = self._terms("Power Bank มี CCC")
        self.assertNotIn("มี", terms)
        self.assertIn("ccc", terms)

    # --- Context prefix สำหรับ stripped even when compound ---

    def test_samrap_compound_token_stripped(self):
        terms = self._terms("Power Bank สำหรับนักเดินทาง CCC")
        self.assertFalse(any("สำหรับ" in t for t in terms))
        self.assertIn("ccc", terms)

    # --- _extract_price_max year stripping ---

    def test_extract_price_max_thai_year(self):
        cleaned, _ = self._cleaned("Power Bank CCC ปี 2026"), None
        # call directly
        from shopee_engine.seo_engine import _extract_price_max
        cleaned, _ = _extract_price_max("Power Bank CCC ปี 2026")
        self.assertNotIn("2026", cleaned)
        self.assertNotIn("ปี", cleaned)

    def test_extract_price_max_bare_year(self):
        from shopee_engine.seo_engine import _extract_price_max
        cleaned, _ = _extract_price_max("Power Bank CCC 2026")
        self.assertNotIn("2026", cleaned)


# ---------------------------------------------------------------------------
# Preview embed product card builder (no Discord dependency)
# ---------------------------------------------------------------------------

class TestPreviewProductCardValue(unittest.TestCase):
    def setUp(self):
        import discord_bot.embeds.seo_embeds as em
        self._build = em._build_product_card_value

    def _product(self, **kwargs):
        base = {
            "rank": 1, "total": 5, "itemid": 26583952360, "shopid": 1092528171,
            "title": "UNEED Powerbank CCC",
            "shop_name": "UNEED TH", "price": 739,
            "image_url": "img.jpg",
            "affiliate_type": "datafeed", "affiliate_status": "datafeed",
            "aff_icon": "📋",
            "direct_url": "https://shopee.co.th/product/1092528171/26583952360",
            "url_status": "resolved",
            "cmd_template": (
                "`/affiliate-link-add-product link:<วาง> "
                "itemid:26583952360 shopid:1092528171`"
            ),
        }
        base.update(kwargs)
        return base

    def test_direct_link_in_output(self):
        val = self._build(self._product(), "test-article")
        self.assertIn("shopee.co.th/product/1092528171/26583952360", val)

    def test_itemid_in_output(self):
        val = self._build(self._product(), "test-article")
        self.assertIn("26583952360", val)

    def test_shopid_in_output(self):
        val = self._build(self._product(), "test-article")
        self.assertIn("1092528171", val)

    def test_missing_affiliate_shows_cmd(self):
        p = self._product(affiliate_status="missing", aff_icon="❌")
        val = self._build(p, "test-article")
        self.assertIn("/affiliate-link-add-product", val)

    def test_confirmed_no_cmd(self):
        p = self._product(affiliate_status="confirmed", aff_icon="✅")
        val = self._build(p, "test-article")
        self.assertNotIn("/affiliate-link-add-product", val)

    def test_missing_direct_url_shows_warning(self):
        p = self._product(direct_url="", url_status="incomplete")
        val = self._build(p, "test-article")
        self.assertIn("ไม่สามารถสร้าง URL", val)

    def test_value_within_discord_limit(self):
        val = self._build(self._product(), "test-article")
        self.assertLessEqual(len(val), 1024)


if __name__ == "__main__":
    unittest.main()
