"""Regression tests for /seo-preview pipeline.

Coverage:
  - generate_preview_body uses live DB data (not stale content_md)
  - shope.ee confirmed link renders as affiliate CTA — no {.affiliate-btn} literal
  - s.shopee.co.th confirmed link renders as affiliate CTA — no {.affiliate-btn} literal
  - shope.ee and s.shopee.co.th treated identically (both affiliate hosts)
  - preview body and _build_export_body produce identical product blocks
  - non-confirmed product still shows non-affiliate note in preview
  - preview_article service includes preview_body key
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_STALE_CONTENT_MD = (
    "## บทนำ\n\nบทนำ\n\n"
    "## แนะนำสินค้า\n\n"
    "[ดูสินค้าบน Shopee](https://s.shopee.co.th/OLD){.affiliate-btn}\n\n"  # stale Pandoc literal
    "## FAQ\n\nคำถาม?\n\nคำตอบ\n"
)


def _make_db(
    products: list[dict],
    article_id: str = "test-preview",
    content_md: str = _STALE_CONTENT_MD,
) -> str:
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)

    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE products (
            itemid BIGINT, shopid BIGINT, title VARCHAR, sale_price BIGINT,
            image_link VARCHAR, product_link VARCHAR,
            "product_short link" VARCHAR,
            stock INTEGER DEFAULT 10,
            price BIGINT DEFAULT 0,
            item_sold INTEGER DEFAULT 0,
            item_rating DOUBLE DEFAULT 4.5,
            shop_rating DOUBLE DEFAULT 4.5,
            discount_percentage INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE seo_articles (
            id INTEGER PRIMARY KEY, article_id VARCHAR UNIQUE NOT NULL,
            keyword VARCHAR NOT NULL, category VARCHAR DEFAULT 'mobile-gadgets',
            category_label VARCHAR DEFAULT '', subcategory VARCHAR DEFAULT '',
            subcategory_label VARCHAR DEFAULT '',
            title VARCHAR DEFAULT 'Test Article', meta_description VARCHAR DEFAULT 'Test meta',
            content_md TEXT DEFAULT '',
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
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score DOUBLE DEFAULT 0, rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE seo_article_revisions (
            id INTEGER PRIMARY KEY, article_id VARCHAR NOT NULL,
            revision_number INTEGER NOT NULL,
            title VARCHAR DEFAULT '', meta_description VARCHAR DEFAULT '',
            content_md TEXT DEFAULT '', category VARCHAR DEFAULT '',
            category_label VARCHAR DEFAULT '', status VARCHAR DEFAULT '',
            saved_by VARCHAR DEFAULT 'system', change_summary VARCHAR DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        INSERT INTO seo_articles (id, article_id, keyword, title, content_md)
        VALUES (1, ?, 'USB Fan', 'USB Fan Article', ?)
    """, [article_id, content_md])

    for idx, p in enumerate(products, 1):
        iid    = p["itemid"]
        shopid = p["shopid"]
        plink  = p.get("product_link", f"https://shopee.co.th/p/{shopid}/{iid}")
        aff    = p.get("affiliate_link", "")
        atype  = p.get("affiliate_link_type", "none")
        price  = p.get("sale_price", 500)
        con.execute(
            "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [iid, shopid, p.get("title", f"Product {idx}"), price,
             "", plink, "", 10, price, 100, 4.5, 4.5, 0],
        )
        con.execute("""
            INSERT INTO seo_article_products
                (id, article_id, itemid, shopid, product_title, sale_price,
                 affiliate_link, affiliate_link_type, rank_in_article)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [idx, article_id, iid, shopid,
              p.get("title", f"Product {idx}"), price, aff, atype, idx])

    con.close()
    return path


def _patch_db(db_path: str):
    return patch("shopee_engine.config.config.db_path", Path(db_path))


# ---------------------------------------------------------------------------
# 1. generate_preview_body — uses live data, not stale content_md
# ---------------------------------------------------------------------------

class TestGeneratePreviewBodyUsesLiveData(unittest.TestCase):

    def setUp(self):
        self.db = _make_db([
            {"itemid": 1001, "shopid": 101,
             "affiliate_link": "https://s.shopee.co.th/LIVE1",
             "affiliate_link_type": "confirmed"},
        ])

    def tearDown(self):
        os.unlink(self.db)

    def test_no_pandoc_literal_in_preview(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertTrue(result.get("success"), result.get("error"))
        self.assertNotIn("{.affiliate-btn}", result["body"])

    def test_live_affiliate_url_appears_in_preview(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertIn("s.shopee.co.th/LIVE1", result["body"])

    def test_stale_url_not_in_preview(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        # The old stale URL from content_md must NOT appear in the product CTA
        self.assertNotIn("s.shopee.co.th/OLD", result["body"])


# ---------------------------------------------------------------------------
# 2. shope.ee confirmed link → affiliate CTA (no non-affiliate note)
# ---------------------------------------------------------------------------

class TestShopeeEeConfirmedAffiliate(unittest.TestCase):

    def setUp(self):
        self.db = _make_db([
            {"itemid": 2001, "shopid": 201,
             "affiliate_link": "https://shope.ee/an_redir?target=xyz",
             "affiliate_link_type": "confirmed"},
        ])

    def tearDown(self):
        os.unlink(self.db)

    def test_shope_ee_renders_as_affiliate_btn(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        body = result["body"]
        self.assertIn('class="affiliate-btn"', body)
        self.assertIn("shope.ee/an_redir", body)

    def test_shope_ee_uses_sponsored_rel(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertIn('rel="sponsored nofollow noopener"', result["body"])

    def test_shope_ee_no_non_affiliate_note(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertNotIn("ลิงก์ตรง Shopee", result["body"])

    def test_no_pandoc_literal(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertNotIn("{.affiliate-btn}", result["body"])


# ---------------------------------------------------------------------------
# 3. s.shopee.co.th confirmed link → same affiliate CTA as shope.ee
# ---------------------------------------------------------------------------

class TestShopeeCoThConfirmedAffiliate(unittest.TestCase):

    def setUp(self):
        self.db = _make_db([
            {"itemid": 3001, "shopid": 301,
             "affiliate_link": "https://s.shopee.co.th/9KmXABCdef",
             "affiliate_link_type": "confirmed"},
        ])

    def tearDown(self):
        os.unlink(self.db)

    def test_s_shopee_co_th_renders_as_affiliate_btn(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        body = result["body"]
        self.assertIn('class="affiliate-btn"', body)
        self.assertIn("s.shopee.co.th/9KmXABCdef", body)

    def test_s_shopee_co_th_uses_sponsored_rel(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertIn('rel="sponsored nofollow noopener"', result["body"])

    def test_no_non_affiliate_note(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertNotIn("ลิงก์ตรง Shopee", result["body"])


# ---------------------------------------------------------------------------
# 4. shope.ee and s.shopee.co.th treated identically
# ---------------------------------------------------------------------------

class TestBothAffiliateHostsTreatedIdentically(unittest.TestCase):
    """Preview for shope.ee and s.shopee.co.th must produce the same CTA structure."""

    def _body_for_url(self, aff_url: str) -> str:
        db = _make_db([
            {"itemid": 4001, "shopid": 401,
             "affiliate_link": aff_url,
             "affiliate_link_type": "confirmed"},
        ])
        try:
            from shopee_engine.article_exporter import generate_preview_body
            with _patch_db(db):
                result = generate_preview_body("test-preview")
            return result.get("body", "")
        finally:
            os.unlink(db)

    def test_both_hosts_get_affiliate_btn_class(self):
        body_shope = self._body_for_url("https://shope.ee/an_redir?x=1")
        body_s     = self._body_for_url("https://s.shopee.co.th/ABC123")
        self.assertIn('class="affiliate-btn"', body_shope)
        self.assertIn('class="affiliate-btn"', body_s)

    def test_both_hosts_get_sponsored_rel(self):
        body_shope = self._body_for_url("https://shope.ee/an_redir?x=1")
        body_s     = self._body_for_url("https://s.shopee.co.th/ABC123")
        self.assertIn('rel="sponsored nofollow noopener"', body_shope)
        self.assertIn('rel="sponsored nofollow noopener"', body_s)

    def test_neither_host_gets_non_affiliate_note(self):
        body_shope = self._body_for_url("https://shope.ee/an_redir?x=1")
        body_s     = self._body_for_url("https://s.shopee.co.th/ABC123")
        self.assertNotIn("ลิงก์ตรง Shopee", body_shope)
        self.assertNotIn("ลิงก์ตรง Shopee", body_s)


# ---------------------------------------------------------------------------
# 5. preview_body matches _build_export_body directly
# ---------------------------------------------------------------------------

class TestPreviewBodyMatchesExportBody(unittest.TestCase):
    """generate_preview_body must produce the same body as calling _build_export_body directly."""

    def setUp(self):
        self.db = _make_db([
            {"itemid": 5001, "shopid": 501,
             "affiliate_link": "https://shope.ee/an_redir?target=abc",
             "affiliate_link_type": "confirmed"},
            {"itemid": 5002, "shopid": 502,
             "affiliate_link": "",
             "affiliate_link_type": "none",
             "product_link": "https://shopee.co.th/product/502/5002"},
        ])

    def tearDown(self):
        os.unlink(self.db)

    def test_preview_body_same_as_export_body(self):
        from shopee_engine.article_exporter import (
            generate_preview_body,
            _extract_prose,
            _build_export_body,
            _load_enriched_products,
        )
        from shopee_engine.seo_engine import _connect, SEO_ARTICLES_TABLE

        with _patch_db(self.db):
            preview = generate_preview_body("test-preview")

            con = _connect(read_only=True)
            art = con.execute(
                f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
                ["test-preview"],
            ).fetchdf().iloc[0].to_dict()
            products = _load_enriched_products("test-preview", con)
            con.close()

            prose    = _extract_prose(str(art.get("content_md", "")))
            expected = _build_export_body(art, products, prose)

        self.assertEqual(preview["body"], expected)


# ---------------------------------------------------------------------------
# 6. Non-confirmed product still shows non-affiliate note in preview
# ---------------------------------------------------------------------------

class TestNonConfirmedProductPreview(unittest.TestCase):

    def setUp(self):
        self.db = _make_db([
            {"itemid": 6001, "shopid": 601,
             "affiliate_link": "",
             "affiliate_link_type": "none",
             "product_link": "https://shopee.co.th/product/601/6001"},
        ])

    def tearDown(self):
        os.unlink(self.db)

    def test_non_confirmed_shows_non_affiliate_note(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        self.assertIn("ลิงก์ตรง Shopee", result["body"])

    def test_non_confirmed_uses_nofollow_not_sponsored(self):
        from shopee_engine.article_exporter import generate_preview_body
        with _patch_db(self.db):
            result = generate_preview_body("test-preview")
        body = result["body"]
        self.assertIn('rel="nofollow noopener"', body)
        self.assertNotIn('"sponsored', body)


# ---------------------------------------------------------------------------
# 7. preview_article service includes preview_body key
# ---------------------------------------------------------------------------

class TestPreviewArticleServiceIncludesPreviewBody(unittest.TestCase):

    def setUp(self):
        self.db = _make_db([
            {"itemid": 7001, "shopid": 701,
             "affiliate_link": "https://shope.ee/an_redir?target=svc",
             "affiliate_link_type": "confirmed"},
        ])

    def tearDown(self):
        os.unlink(self.db)

    def test_service_returns_preview_body_key(self):
        from discord_bot.services.seo_service import preview_article
        with _patch_db(self.db):
            result = preview_article("test-preview")
        self.assertTrue(result.get("success"), result.get("error"))
        self.assertIn("preview_body", result)
        self.assertIsInstance(result["preview_body"], str)
        self.assertGreater(len(result["preview_body"]), 0)

    def test_service_preview_body_has_no_pandoc_literal(self):
        from discord_bot.services.seo_service import preview_article
        with _patch_db(self.db):
            result = preview_article("test-preview")
        self.assertNotIn("{.affiliate-btn}", result.get("preview_body", ""))

    def test_service_preview_body_contains_affiliate_cta(self):
        from discord_bot.services.seo_service import preview_article
        with _patch_db(self.db):
            result = preview_article("test-preview")
        body = result.get("preview_body", "")
        self.assertIn('class="affiliate-btn"', body)
        self.assertIn("shope.ee/an_redir", body)
