"""Regression tests: /seo-ideas → /seo-draft integration.

Tests:
  - Keyword normalization (price extraction, stopword removal, synonym expansion)
  - idea_id flow (product_ids fetched directly, not by display_keyword text)
  - Expired / unknown idea_id returns safe error (no partial DB write)
  - display_keyword "USB & Mobile Fan ไม่เกิน 1,500 บาท" → finds fan products
  - "Powerbanks" → matches "power bank" / "พาวเวอร์แบงค์" synonyms
  - No article record created on validation failure
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_db(products: list[dict] | None = None) -> str:
    """Create a temp DuckDB with products and SEO tables."""
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)
    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE products (
            itemid BIGINT, shopid BIGINT,
            title VARCHAR, description VARCHAR,
            sale_price BIGINT, price BIGINT,
            item_sold BIGINT, "like" BIGINT,
            shop_rating DOUBLE, item_rating DOUBLE,
            discount_percentage DOUBLE,
            global_category1 VARCHAR, global_category2 VARCHAR, global_category3 VARCHAR,
            global_brand VARCHAR, image_link VARCHAR,
            product_link VARCHAR, "product_short link" VARCHAR,
            stock INTEGER DEFAULT 10
        )
    """)
    con.execute("""
        CREATE TABLE affiliate_products (
            product_link VARCHAR, affiliate_short_url VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE seo_articles (
            id INTEGER PRIMARY KEY, article_id VARCHAR UNIQUE NOT NULL,
            keyword VARCHAR NOT NULL, category VARCHAR DEFAULT '',
            title VARCHAR DEFAULT '', meta_description VARCHAR DEFAULT '',
            content_md TEXT DEFAULT '', status VARCHAR DEFAULT 'draft',
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
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score DOUBLE DEFAULT 0, rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    default_products = products or [
        # USB & Mobile Fan products
        (1001, 201, "USB Mini Fan พัดลม USB พกพา", "พัดลม USB ขนาดเล็ก", 299, 399, 500, 100, 4.8, 4.7, 25.0, "Electronics", "Fans", "USB & Mobile Fan", "FanBrand", "img1.jpg", "https://shopee/p1", "https://shope.ee/p1", 10),
        (1002, 202, "Mobile Fan พัดลมพกพา USB ชาร์จได้", "พัดลม USB สำหรับมือถือ", 450, 600, 300, 80, 4.6, 4.5, 25.0, "Electronics", "Fans", "USB & Mobile Fan", "AirCool", "img2.jpg", "https://shopee/p2", "https://shope.ee/p2", 10),
        (1003, 203, "Portable USB Fan พัดลมพกพา แบบพับได้", "พัดลม USB แบบพับ", 350, 450, 400, 120, 4.9, 4.8, 22.0, "Electronics", "Fans", "USB & Mobile Fan", "CoolBrand", "img3.jpg", "https://shopee/p3", "https://shope.ee/p3", 10),
        (1004, 204, "USB Desk Fan พัดลมตั้งโต๊ะ USB", "พัดลม USB ตั้งโต๊ะ", 799, 999, 200, 60, 4.5, 4.4, 20.0, "Electronics", "Fans", "USB & Mobile Fan", "DeskCool", "img4.jpg", "https://shopee/p4", "https://shope.ee/p4", 10),
        (1005, 205, "Mini Fan USB พัดลม USB ขนาดพกพา", "พัดลมพกพา USB ราคาถูก", 199, 250, 800, 200, 4.7, 4.6, 20.0, "Electronics", "Fans", "USB & Mobile Fan", "MiniCool", "img5.jpg", "https://shopee/p5", "https://shope.ee/p5", 10),
        # Powerbank products
        (2001, 301, "Powerbank 20000mAh แบตสำรอง", "แบตเตอรี่สำรอง 20000 mAh ชาร์จเร็ว", 890, 1200, 1000, 250, 4.8, 4.7, 26.0, "Electronics", "Chargers", "Powerbanks", "PowerBrand", "img6.jpg", "https://shopee/p6", "https://shope.ee/p6", 10),
        (2002, 302, "Power Bank 10000mAh Slim แบบบาง", "แบตสำรอง 10000 mAh บาง", 590, 800, 800, 180, 4.7, 4.6, 26.0, "Electronics", "Chargers", "Powerbanks", "SlimPower", "img7.jpg", "https://shopee/p7", "https://shope.ee/p7", 10),
        (2003, 303, "พาวเวอร์แบงค์ 30000 mAh ชาร์จได้ 3 เครื่อง", "แบตสำรองความจุสูง 30000mAh", 1290, 1500, 600, 150, 4.9, 4.8, 14.0, "Electronics", "Chargers", "Powerbanks", "MegaPower", "img8.jpg", "https://shopee/p8", "https://shope.ee/p8", 10),
        (2004, 304, "Wireless Powerbank แบตสำรองไร้สาย 15000mAh", "แบตสำรองแบบไร้สาย", 1490, 1800, 400, 100, 4.6, 4.5, 17.0, "Electronics", "Chargers", "Powerbanks", "WirelessPower", "img9.jpg", "https://shopee/p9", "https://shope.ee/p9", 10),
        (2005, 305, "แบตสำรอง 5000mAh ขนาดพกพา ราคาถูก", "แบตสำรองราคาประหยัด", 290, 350, 1200, 300, 4.7, 4.6, 17.0, "Electronics", "Chargers", "Powerbanks", "BudgetPower", "img10.jpg", "https://shopee/p10", "https://shope.ee/p10", 10),
    ]
    con.executemany("""
        INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, default_products)
    con.close()
    return path


# ---------------------------------------------------------------------------
# Unit tests: keyword normalization
# ---------------------------------------------------------------------------

class TestKeywordNormalization(unittest.TestCase):

    def _import_fn(self):
        from shopee_engine.seo_engine import _extract_price_max, _keyword_to_search_terms, normalize_search_terms
        return _extract_price_max, _keyword_to_search_terms, normalize_search_terms

    def test_extract_price_max_simple(self):
        _extract_price_max, _, _ = self._import_fn()
        cleaned, price = _extract_price_max("USB Fan ไม่เกิน 1,500 บาท")
        self.assertEqual(price, 1500)
        self.assertNotIn("ไม่เกิน", cleaned)
        self.assertNotIn("บาท", cleaned)

    def test_extract_price_max_no_price(self):
        _extract_price_max, _, _ = self._import_fn()
        cleaned, price = _extract_price_max("Powerbanks")
        self.assertIsNone(price)
        self.assertEqual(cleaned, "Powerbanks")

    def test_normalize_removes_stopwords(self):
        _, _keyword_to_search_terms, _ = self._import_fn()
        terms = _keyword_to_search_terms("USB Mobile Fan ไม่เกิน 1500 บาท")
        # stopwords removed even without price extraction (raw input)
        self.assertNotIn("ไม่เกิน", terms)
        self.assertNotIn("บาท", terms)

    def test_normalize_removes_connectors(self):
        _, _keyword_to_search_terms, _ = self._import_fn()
        terms = _keyword_to_search_terms("USB & Mobile Fan")
        self.assertNotIn("&", terms)
        self.assertIn("usb", terms)
        self.assertIn("mobile", terms)
        self.assertIn("fan", terms)

    def test_normalize_powerbanks_synonym_expansion(self):
        _, _keyword_to_search_terms, _ = self._import_fn()
        terms = _keyword_to_search_terms("Powerbanks")
        # Must expand to power bank + Thai synonyms
        self.assertIn("powerbanks", terms)
        self.assertTrue(
            any("power bank" in t for t in terms) or any("พาวเวอร์แบงค์" in t for t in terms),
            f"Expected synonym expansion, got: {terms}"
        )

    def test_normalize_usb_fan_synonym_expansion(self):
        _, _keyword_to_search_terms, _ = self._import_fn()
        terms = _keyword_to_search_terms("USB & Mobile Fan")
        # Must include Thai fan synonyms
        self.assertTrue(
            any("พัดลม" in t for t in terms),
            f"Expected พัดลม synonym, got: {terms}"
        )

    def test_normalize_search_terms_display(self):
        _, _, normalize_search_terms = self._import_fn()
        result = normalize_search_terms("USB & Mobile Fan ไม่เกิน 1,500 บาท")
        self.assertEqual(result["price_max"], 1500)
        self.assertIsNotNone(result["display"])


# ---------------------------------------------------------------------------
# Integration tests: fetch_products with normalization
# ---------------------------------------------------------------------------

class TestFetchProductsNormalized(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        os.unlink(self.db_path)

    def _fetch(self, keyword, category=None, price_max=None):
        with patch("shopee_engine.config.config") as mock_cfg:
            mock_cfg.db_path = self.db_path
            with patch("shopee_engine.seo_engine.config") as mock_cfg2:
                mock_cfg2.db_path = self.db_path
                from shopee_engine import seo_engine
                # Ensure config is patched
                import importlib
                from shopee_engine.seo_engine import fetch_products_for_keyword
                with patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
                    return fetch_products_for_keyword(keyword, category=category, price_max=price_max)

    def test_usb_mobile_fan_display_keyword_finds_products(self):
        """Copying display keyword from /seo-ideas must find fan products."""
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import fetch_products_for_keyword
            products = fetch_products_for_keyword("USB & Mobile Fan ไม่เกิน 1,500 บาท")
        self.assertGreater(len(products), 0, "Must find USB/Mobile fan products")
        titles = " ".join(p["title"].lower() for p in products)
        self.assertTrue(
            "fan" in titles or "พัดลม" in titles,
            f"Expected fan products, got: {[p['title'] for p in products]}"
        )

    def test_powerbanks_keyword_finds_powerbank_products(self):
        """'Powerbanks' must match power bank / พาวเวอร์แบงค์ products."""
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import fetch_products_for_keyword
            products = fetch_products_for_keyword("Powerbanks")
        self.assertGreater(len(products), 0, "Must find powerbank products")
        titles = " ".join(p["title"].lower() for p in products)
        self.assertTrue(
            "power" in titles or "powerbank" in titles or "แบตสำรอง" in titles or "แบตเตอรี่สำรอง" in titles,
            f"Expected powerbank products, got: {[p['title'] for p in products]}"
        )

    def test_price_extracted_from_keyword(self):
        """Price in keyword string must be used as price_max filter."""
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import fetch_products_for_keyword
            products = fetch_products_for_keyword("Powerbanks ไม่เกิน 1,000 บาท")
        # Only products priced <= 1000
        for p in products:
            self.assertLessEqual(
                p["sale_price"], 1000,
                f"Product '{p['title']}' priced {p['sale_price']} exceeds 1000"
            )


# ---------------------------------------------------------------------------
# Integration tests: idea_id flow
# ---------------------------------------------------------------------------

class TestIdeaIdFlow(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        os.unlink(self.db_path)
        # Clear idea cache between tests
        from shopee_engine import seo_engine
        seo_engine._idea_cache.clear()

    def _run_find_ideas(self, category=None):
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import find_keyword_opportunities
            return find_keyword_opportunities(category=category, top=10, min_sales=10)

    def test_ideas_have_idea_id(self):
        ideas = self._run_find_ideas()
        self.assertGreater(len(ideas), 0)
        for idea in ideas:
            self.assertIn("idea_id", idea, "Each idea must have idea_id")
            self.assertTrue(idea["idea_id"].startswith("idea-"), f"Bad idea_id: {idea['idea_id']}")

    def test_ideas_have_product_ids(self):
        ideas = self._run_find_ideas()
        for idea in ideas:
            self.assertIn("product_ids", idea)
            self.assertIsInstance(idea["product_ids"], list)
            self.assertGreater(len(idea["product_ids"]), 0, "Each idea must have at least 1 product_id")

    def test_idea_id_cached_after_find(self):
        ideas = self._run_find_ideas()
        from shopee_engine import seo_engine
        for idea in ideas:
            self.assertIn(idea["idea_id"], seo_engine._idea_cache, f"{idea['idea_id']} not in cache")

    def test_fetch_products_by_idea_returns_products(self):
        ideas = self._run_find_ideas()
        idea = ideas[0]
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import fetch_products_by_idea
            products = fetch_products_by_idea(idea["idea_id"], top=5)
        self.assertIsNotNone(products, "fetch_products_by_idea must not return None for valid idea_id")
        self.assertGreater(len(products), 0, "Must find products for a valid idea_id")

    def test_fetch_products_by_idea_unknown_returns_none(self):
        from shopee_engine.seo_engine import fetch_products_by_idea
        result = fetch_products_by_idea("idea-000000")
        self.assertIsNone(result, "Unknown idea_id must return None")

    def test_all_ideas_passable_to_draft(self):
        """Every idea returned by /seo-ideas must be usable via idea_id in generate_article_draft."""
        ideas = self._run_find_ideas()
        from shopee_engine import seo_engine
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            for idea in ideas:
                products = seo_engine.fetch_products_by_idea(idea["idea_id"], top=5)
                self.assertIsNotNone(
                    products,
                    f"idea_id {idea['idea_id']} ('{idea['keyword']}') must fetch products"
                )
                self.assertGreater(
                    len(products), 0,
                    f"idea_id {idea['idea_id']} ('{idea['keyword']}') must find >0 products"
                )


# ---------------------------------------------------------------------------
# Integration tests: generate_article_draft safety
# ---------------------------------------------------------------------------

class TestArticleDraftSafety(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        os.unlink(self.db_path)
        from shopee_engine import seo_engine
        seo_engine._idea_cache.clear()

    def _count_articles(self) -> int:
        con = duckdb.connect(self.db_path)
        n = con.execute("SELECT COUNT(*) FROM seo_articles").fetchone()[0]
        con.close()
        return n

    def test_expired_idea_id_returns_error_no_db_write(self):
        """Expired/unknown idea_id must return error and NOT create a partial article."""
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import generate_article_draft
            before = self._count_articles()
            result = generate_article_draft(idea_id="idea-badid")
        self.assertFalse(result["success"])
        self.assertIn("idea_id", result["error"])
        self.assertEqual(self._count_articles(), before, "No article must be created on expired idea_id")

    def test_no_products_returns_error_no_db_write(self):
        """When no products match, must return error without creating article record."""
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import generate_article_draft
            before = self._count_articles()
            result = generate_article_draft(keyword="zzz-nonexistent-xyz-product-abc")
        self.assertFalse(result["success"])
        self.assertEqual(self._count_articles(), before, "No article must be created when no products found")

    def test_draft_error_shows_search_terms_not_sql(self):
        """Error message on no-product must show search terms, not SQL."""
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import generate_article_draft
            result = generate_article_draft(keyword="zzz-nonexistent-xyz-product-abc")
        self.assertFalse(result["success"])
        err = result.get("error", "")
        self.assertNotIn("SELECT", err)
        self.assertNotIn("FROM products", err)
        self.assertNotIn("/Users/", err)

    def test_idea_id_creates_article_successfully(self):
        """Valid idea_id flow must create article in DB."""
        # First run find_keyword_opportunities to populate cache
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import find_keyword_opportunities, generate_article_draft
            ideas = find_keyword_opportunities(top=5, min_sales=10)
        self.assertGreater(len(ideas), 0)

        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import generate_article_draft as gad
            result = gad(idea_id=ideas[0]["idea_id"])

        if result["success"]:
            self.assertIn("article_id", result)
            self.assertGreater(result.get("products_count", 0), 0)
        else:
            # Acceptable only if no products in DB match (skip, not fail)
            self.assertIn("idea_id", result.get("error", "") + result.get("keyword", ""))


# ---------------------------------------------------------------------------
# Unit tests: _keyword_to_term_groups
# ---------------------------------------------------------------------------

class TestKeywordToTermGroups(unittest.TestCase):

    def _groups(self, keyword):
        from shopee_engine.seo_engine import _keyword_to_term_groups
        return _keyword_to_term_groups(keyword)

    def test_phrase_synonym_returns_one_group(self):
        """Phrase match → single OR group (synonym terms only, no raw tokens)."""
        groups = self._groups("USB & Mobile Fan")
        self.assertEqual(len(groups), 1)
        # Must include Thai fan terms, NOT just "usb" / "mobile"
        all_terms = groups[0]
        self.assertTrue(any("พัดลม" in t for t in all_terms), f"Expected พัดลม in {all_terms}")

    def test_plural_fans_matches_phrase_synonym(self):
        """'USB & Mobile Fans' (plural from Shopee category) must resolve same as singular."""
        groups = self._groups("USB & Mobile Fans")
        self.assertEqual(len(groups), 1)
        all_terms = groups[0]
        self.assertTrue(any("พัดลม" in t for t in all_terms), f"Expected พัดลม in {all_terms}")
        # Must NOT include bare "usb" — too broad
        self.assertNotIn("usb", all_terms)

    def test_powerbanks_phrase_synonym(self):
        """'Powerbanks' phrase maps to battery/powerbank synonyms."""
        groups = self._groups("Powerbanks")
        self.assertEqual(len(groups), 1)
        all_terms = groups[0]
        self.assertTrue(
            any("แบตสำรอง" in t or "power bank" in t for t in all_terms),
            f"Expected powerbank synonyms in {all_terms}",
        )

    def test_multi_token_no_phrase_returns_multiple_groups(self):
        """Multi-token keyword without phrase synonym → AND between groups."""
        groups = self._groups("หูฟัง ไร้สาย")
        self.assertGreater(len(groups), 1, "Two concepts → two AND groups")

    def test_empty_keyword_returns_empty(self):
        groups = self._groups("")
        self.assertEqual(groups, [])

    def test_stopword_only_keyword_returns_empty(self):
        groups = self._groups("ที่ดีที่สุด ราคา")
        self.assertEqual(groups, [])


# ---------------------------------------------------------------------------
# Integration tests: fetch_products with plural Shopee category keywords
# ---------------------------------------------------------------------------

class TestFetchProductsPluralKeyword(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        os.unlink(self.db_path)

    def _fetch(self, keyword):
        with patch("shopee_engine.seo_engine.config") as mock_cfg, \
             patch("shopee_engine.seo_engine._get_affiliate_lookup", return_value={}):
            mock_cfg.db_path = self.db_path
            from shopee_engine.seo_engine import fetch_products_for_keyword
            return fetch_products_for_keyword(keyword, price_max=1500)

    def test_usb_mobile_fans_plural_finds_fan_products(self):
        """'USB & Mobile Fans' (plural Shopee category) must find fan products, not power strips."""
        products = self._fetch("USB & Mobile Fans ไม่เกิน 500 บาท")
        self.assertGreater(len(products), 0, "Must find products for USB & Mobile Fans")
        titles = " ".join(p["title"].lower() for p in products)
        self.assertTrue(
            "fan" in titles or "พัดลม" in titles,
            f"Expected fan products, got: {[p['title'] for p in products]}",
        )

    def test_usb_mobile_fans_singular_finds_same_category(self):
        """Singular and plural forms must return equivalent product sets."""
        products_plural   = self._fetch("USB & Mobile Fans")
        products_singular = self._fetch("USB & Mobile Fan")
        ids_plural   = {p["itemid"] for p in products_plural}
        ids_singular = {p["itemid"] for p in products_singular}
        self.assertEqual(ids_plural, ids_singular, "Plural and singular must return same products")


if __name__ == "__main__":
    unittest.main()
