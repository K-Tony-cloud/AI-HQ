"""Regression tests: affiliate link validation gates for /seo-review and /seo-publish.

Coverage:
  - 0/5 confirmed → block review + block publish
  - 1/5 confirmed → block review + block publish
  - 4/5 confirmed → block review + block publish
  - 5/5 confirmed → review passes, publish passes (with status=reviewed)
  - datafeed URL (shope.ee) must NOT appear as CTA in exported production article content
  - After seo-refresh: newly_confirmed list populated, no new draft created
  - Mixed links: error message includes specific missing itemids
  - get_article_link_status returns per-product breakdown
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

def _make_test_db(
    confirmed: list[int] | None = None,
    total: int = 5,
) -> str:
    """
    Create a temp DB with `total` products in seo_article_products,
    some of which have confirmed affiliate links (from affiliate_products).
    """
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)

    confirmed_itemids = set(confirmed or [])
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
            affiliate_link_type VARCHAR DEFAULT 'datafeed',
            opportunity_score DOUBLE DEFAULT 0, rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert the article
    con.execute("""
        INSERT INTO seo_articles (id, article_id, keyword, category, title, meta_description, content_md, status)
        VALUES (1, 'art-001', 'test keyword', 'mobile-gadgets',
                'Test Article Title',
                'Test meta description for SEO',
                '## Introduction\n' || repeat('y', 700),
                'draft')
    """)

    for i in range(1, total + 1):
        itemid = 1000 + i
        shopid = 200 + i
        product_url = f"https://shopee.co.th/product/{shopid}/{itemid}"
        datafeed_url = f"https://shope.ee/an_redir?origin_link=https%3A%2F%2Fshopee.co.th%2Fproduct%2F{shopid}%2F{itemid}"

        # Insert into products table
        con.execute("""
            INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [itemid, shopid, f"Product {i}", f"Desc {i}", 500, 600, 100, 50,
              4.8, 4.7, 20.0, "Electronics", "Cat2", "Cat3",
              "Brand", f"img{i}.jpg", product_url, datafeed_url, 10])

        # If this itemid should be confirmed, add to affiliate_products
        if itemid in confirmed_itemids:
            aff_link = f"https://s.shopee.co.th/TEST{itemid}"
            con.execute(
                "INSERT INTO affiliate_products VALUES (?, ?)",
                [product_url, aff_link],
            )
            link_type = "confirmed"
            affiliate_link = aff_link
        else:
            link_type = "datafeed"
            affiliate_link = datafeed_url

        con.execute("""
            INSERT INTO seo_article_products
            (id, article_id, itemid, shopid, product_title, sale_price,
             affiliate_link, affiliate_link_type, rank_in_article)
            VALUES (?, 'art-001', ?, ?, ?, 500, ?, ?, ?)
        """, [i, itemid, shopid, f"Product {i}", affiliate_link, link_type, i])

    con.close()
    return path


def _patch_db(db_path: str):
    """Patch config.db_path to point to test DB."""
    from pathlib import Path
    return patch("shopee_engine.config.config.db_path", Path(db_path))


def _patch_affiliate(db_path: str):
    """Patch get_all_affiliate_products to read from test DB."""
    import duckdb as _ddb
    from pathlib import Path

    def _read_aff():
        con = _ddb.connect(db_path, read_only=True)
        rows = con.execute(
            "SELECT product_link, affiliate_short_url FROM affiliate_products"
        ).fetchall()
        con.close()
        return {r[0]: r[1] for r in rows}

    return patch(
        "shopee_engine.affiliate_products_engine.get_all_affiliate_products",
        side_effect=_read_aff,
    )


# ---------------------------------------------------------------------------
# Tests: validate_article_for_review
# ---------------------------------------------------------------------------

class TestValidateForReview(unittest.TestCase):

    def _run(self, confirmed: list[int], total: int = 5) -> dict:
        from shopee_engine.seo_engine import validate_article_for_review
        db = _make_test_db(confirmed, total)
        with _patch_db(db):
            return validate_article_for_review("art-001")

    def test_zero_confirmed_blocks_review(self):
        result = self._run(confirmed=[], total=5)
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("confirmed", errors_joined)

    def test_one_of_five_blocks_review(self):
        result = self._run(confirmed=[1001], total=5)
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("4", errors_joined)  # "ขาด 4/5"

    def test_four_of_five_blocks_review(self):
        result = self._run(confirmed=[1001, 1002, 1003, 1004], total=5)
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("1", errors_joined)  # "ขาด 1/5"

    def test_all_confirmed_passes_review(self):
        result = self._run(confirmed=[1001, 1002, 1003, 1004, 1005], total=5)
        self.assertTrue(result["valid"], f"Expected valid but got errors: {result['errors']}")

    def test_error_message_contains_missing_itemids(self):
        result = self._run(confirmed=[1001], total=5)
        errors_joined = " ".join(result["errors"])
        # Should mention at least one of the missing itemids
        self.assertTrue(
            any(str(i) in errors_joined for i in [1002, 1003, 1004, 1005]),
            f"Expected missing itemid in error: {errors_joined}",
        )


# ---------------------------------------------------------------------------
# Tests: validate_article_for_publish
# ---------------------------------------------------------------------------

class TestValidateForPublish(unittest.TestCase):

    def _run(self, confirmed: list[int], total: int = 5, status: str = "reviewed") -> dict:
        from shopee_engine.seo_engine import validate_article_for_publish
        db = _make_test_db(confirmed, total)
        # Set article status
        con = duckdb.connect(db)
        con.execute("UPDATE seo_articles SET status=? WHERE article_id='art-001'", [status])
        con.close()
        with _patch_db(db):
            return validate_article_for_publish("art-001")

    def test_zero_confirmed_blocks_publish(self):
        result = self._run(confirmed=[], total=5)
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("confirmed", errors_joined)

    def test_one_of_five_blocks_publish(self):
        result = self._run(confirmed=[1001], total=5)
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("4", errors_joined)

    def test_four_of_five_blocks_publish(self):
        result = self._run(confirmed=[1001, 1002, 1003, 1004], total=5)
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("1", errors_joined)

    def test_all_confirmed_passes_publish(self):
        result = self._run(confirmed=[1001, 1002, 1003, 1004, 1005], total=5)
        # status=reviewed is required; if other checks pass → should be valid
        self.assertTrue(result["valid"], f"Expected valid but got errors: {result['errors']}")

    def test_datafeed_url_is_an_error_not_warning(self):
        result = self._run(confirmed=[1001], total=5)  # 1/5 confirmed
        self.assertFalse(result["valid"])
        self.assertTrue(len(result["errors"]) > 0)
        # The datafeed issue must be in errors, not only warnings
        all_warnings = " ".join(result.get("warnings", []))
        # "ขาด" should appear in errors, not just warnings
        self.assertTrue(
            any("ขาด" in e or "confirmed" in e for e in result["errors"])
        )


# ---------------------------------------------------------------------------
# Tests: datafeed URL must not be CTA in production content
# ---------------------------------------------------------------------------

class TestDatafeedUrlNotInProduction(unittest.TestCase):

    def test_shope_ee_not_in_published_content(self):
        """Article with only datafeed links should be blocked before reaching content."""
        from shopee_engine.seo_engine import validate_article_for_publish
        db = _make_test_db(confirmed=[], total=5)
        con = duckdb.connect(db)
        # Simulate content that erroneously contains datafeed URLs
        con.execute(
            "UPDATE seo_articles SET content_md=?, status='reviewed' WHERE article_id='art-001'",
            ["## Test\n" + "https://shope.ee/an_redir?origin_link=https://shopee.co.th/product/201/1001 " * 5 + "y" * 200]
        )
        con.close()
        with _patch_db(db):
            result = validate_article_for_publish("art-001")
        # Must be blocked by validation before publish
        self.assertFalse(result["valid"])
        errors_joined = " ".join(result["errors"])
        self.assertIn("confirmed", errors_joined)


# ---------------------------------------------------------------------------
# Tests: get_article_link_status
# ---------------------------------------------------------------------------

class TestGetArticleLinkStatus(unittest.TestCase):

    def _run(self, confirmed: list[int], total: int = 5) -> dict:
        from shopee_engine.seo_engine import get_article_link_status
        db = _make_test_db(confirmed, total)
        with _patch_db(db):
            return get_article_link_status("art-001")

    def test_returns_per_product_breakdown(self):
        result = self._run(confirmed=[1001, 1002], total=5)
        self.assertTrue(result["success"])
        self.assertEqual(result["total_count"], 5)
        self.assertEqual(result["confirmed_count"], 2)
        self.assertEqual(result["datafeed_count"], 3)
        self.assertEqual(len(result["products"]), 5)

    def test_missing_products_listed(self):
        result = self._run(confirmed=[1001], total=5)
        missing_ids = [p["itemid"] for p in result["missing_products"]]
        self.assertIn(1002, missing_ids)
        self.assertIn(1003, missing_ids)
        self.assertNotIn(1001, missing_ids)

    def test_product_url_correct_format(self):
        result = self._run(confirmed=[], total=3)
        for p in result["products"]:
            self.assertIn("shopee.co.th/product/", p["product_url"])
            self.assertNotIn("an_redir", p["product_url"])

    def test_all_confirmed_flag(self):
        result = self._run(confirmed=[1001, 1002, 1003, 1004, 1005], total=5)
        self.assertTrue(result["all_confirmed"])

    def test_missing_products_reports_all_itemids(self):
        confirmed = [1001, 1003]  # 1002, 1004, 1005 missing
        result = self._run(confirmed=confirmed, total=5)
        missing_ids = {p["itemid"] for p in result["missing_products"]}
        self.assertEqual(missing_ids, {1002, 1004, 1005})


# ---------------------------------------------------------------------------
# Tests: refresh newly_confirmed tracking
# ---------------------------------------------------------------------------

class TestRefreshNewlyConfirmed(unittest.TestCase):

    def test_refresh_tracks_newly_confirmed_without_new_draft(self):
        """After adding affiliate link, refresh should detect newly confirmed without regenerating."""
        from shopee_engine.seo_engine import refresh_article_products

        db = _make_test_db(confirmed=[], total=3)

        # Simulate adding affiliate link for itemid 1001 after draft was created
        con = duckdb.connect(db)
        con.execute(
            "INSERT INTO affiliate_products VALUES (?, ?)",
            ["https://shopee.co.th/product/201/1001", "https://s.shopee.co.th/NEWLINK"],
        )
        con.close()

        def _read_aff():
            _con = duckdb.connect(db, read_only=True)
            rows = _con.execute(
                "SELECT product_link, affiliate_short_url FROM affiliate_products"
            ).fetchall()
            _con.close()
            return {r[0]: r[1] for r in rows}

        with _patch_db(db), patch(
            "shopee_engine.affiliate_products_engine.get_all_affiliate_products",
            side_effect=_read_aff,
        ):
            result = refresh_article_products("art-001")

        self.assertTrue(result["success"])
        # Exactly 1 product should be newly confirmed
        self.assertEqual(len(result["newly_confirmed"]), 1)
        self.assertEqual(result["newly_confirmed"][0]["itemid"], 1001)
        # No new article was created — article_id unchanged
        con2 = duckdb.connect(db, read_only=True)
        count = con2.execute(
            "SELECT COUNT(*) FROM seo_articles WHERE article_id='art-001'"
        ).fetchone()[0]
        con2.close()
        self.assertEqual(count, 1)

    def test_refresh_already_confirmed_not_in_newly_confirmed(self):
        """Products that were already confirmed before refresh are not in newly_confirmed."""
        from shopee_engine.seo_engine import refresh_article_products
        db = _make_test_db(confirmed=[1001], total=3)

        def _read_aff():
            _con = duckdb.connect(db, read_only=True)
            rows = _con.execute(
                "SELECT product_link, affiliate_short_url FROM affiliate_products"
            ).fetchall()
            _con.close()
            return {r[0]: r[1] for r in rows}

        with _patch_db(db), patch(
            "shopee_engine.affiliate_products_engine.get_all_affiliate_products",
            side_effect=_read_aff,
        ):
            result = refresh_article_products("art-001")

        self.assertTrue(result["success"])
        # itemid 1001 was already confirmed — should not appear in newly_confirmed
        newly_ids = [p["itemid"] for p in result["newly_confirmed"]]
        self.assertNotIn(1001, newly_ids)


if __name__ == "__main__":
    unittest.main()
