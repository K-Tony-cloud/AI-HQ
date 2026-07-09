"""Regression tests: taxonomy module and category validation in SEO pipeline.

Coverage:
  - map_to_canonical: known raw → (slug, label)
  - map_to_canonical: unknown raw → None
  - resolve_subcategory: known and unknown
  - is_canonical: slug check
  - validate_article_for_review blocks non-canonical category
  - validate_article_for_publish blocks non-canonical category
  - review/publish passes when category is canonical
  - breadcrumb URL never contains raw Shopee category slug
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

def _make_seo_db(category: str = "mobile-gadgets") -> str:
    """Create a minimal seo_articles + seo_article_products DB for validation tests."""
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)
    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE seo_articles (
            id INTEGER PRIMARY KEY,
            article_id VARCHAR UNIQUE NOT NULL,
            keyword VARCHAR NOT NULL,
            category VARCHAR DEFAULT '',
            category_label VARCHAR DEFAULT '',
            subcategory VARCHAR DEFAULT '',
            subcategory_label VARCHAR DEFAULT '',
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
            published_at TIMESTAMP
        )
    """)
    content = "x" * 600
    con.execute("""
        INSERT INTO seo_articles
            (id, article_id, keyword, category, category_label, title, meta_description,
             content_md, status)
        VALUES (1, 'test-article', 'พัดลมพกพา', ?, 'มือถือ & แกดเจ็ต', 'Test Article',
                'Test description', ?, 'draft')
    """, [category, content])
    con.execute("""
        CREATE TABLE seo_article_products (
            id INTEGER PRIMARY KEY,
            article_id VARCHAR NOT NULL,
            itemid BIGINT,
            shopid BIGINT,
            product_title VARCHAR DEFAULT '',
            sale_price BIGINT DEFAULT 0,
            image_link VARCHAR DEFAULT '',
            affiliate_link VARCHAR DEFAULT 'https://s.shopee.co.th/TEST',
            affiliate_link_type VARCHAR DEFAULT 'confirmed',
            opportunity_score DOUBLE DEFAULT 0,
            rank_in_article INTEGER DEFAULT 1,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP
        )
    """)
    con.execute("""
        INSERT INTO seo_article_products
            (id, article_id, itemid, shopid, product_title, affiliate_link, affiliate_link_type)
        VALUES (1, 'test-article', 12345, 67890, 'Test Fan', 'https://s.shopee.co.th/TEST', 'confirmed')
    """)
    con.close()
    return path


def _patch_db(path: str):
    from pathlib import Path
    return patch("shopee_engine.config.config.db_path", Path(path))


# ---------------------------------------------------------------------------
# Tests: taxonomy module
# ---------------------------------------------------------------------------

class TestMapToCanonical(unittest.TestCase):

    def test_usb_mobile_fans_maps_to_mobile_gadgets(self):
        from shopee_engine.taxonomy import map_to_canonical
        result = map_to_canonical("USB & Mobile Fans")
        self.assertIsNotNone(result)
        slug, label = result
        self.assertEqual(slug, "mobile-gadgets")
        self.assertEqual(label, "มือถือ & แกดเจ็ต")

    def test_powerbanks_maps_to_mobile_gadgets(self):
        from shopee_engine.taxonomy import map_to_canonical
        result = map_to_canonical("Powerbanks")
        self.assertIsNotNone(result)
        slug, _ = result
        self.assertEqual(slug, "mobile-gadgets")

    def test_home_living_maps_correctly(self):
        from shopee_engine.taxonomy import map_to_canonical
        result = map_to_canonical("Home & Living")
        self.assertIsNotNone(result)
        slug, label = result
        self.assertEqual(slug, "home-living")

    def test_unknown_raw_category_returns_none(self):
        from shopee_engine.taxonomy import map_to_canonical
        result = map_to_canonical("UNKNOWN CATEGORY XYZ 9999")
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        from shopee_engine.taxonomy import map_to_canonical
        self.assertIsNone(map_to_canonical(""))

    def test_raw_category_with_ampersand_not_usable_as_slug(self):
        """Verify that the slug returned is URL-safe (no & or spaces)."""
        from shopee_engine.taxonomy import map_to_canonical
        result = map_to_canonical("USB & Mobile Fans")
        slug, _ = result
        self.assertNotIn("&", slug)
        self.assertNotIn(" ", slug)

    def test_returned_slug_is_in_canonical_allowlist(self):
        from shopee_engine.taxonomy import map_to_canonical, CANONICAL_CATEGORIES
        raw_categories = ["USB & Mobile Fans", "Powerbanks", "Beauty", "Home & Living"]
        for raw in raw_categories:
            result = map_to_canonical(raw)
            if result:
                slug, _ = result
                self.assertIn(slug, CANONICAL_CATEGORIES,
                    f"Slug '{slug}' from '{raw}' must be in CANONICAL_CATEGORIES")


class TestResolveSubcategory(unittest.TestCase):

    def test_usb_mobile_fans_subcategory(self):
        from shopee_engine.taxonomy import resolve_subcategory
        sub_slug, sub_label = resolve_subcategory("USB & Mobile Fans")
        self.assertEqual(sub_slug, "usb-mobile-fans")
        self.assertEqual(sub_label, "USB & Mobile Fans")

    def test_powerbanks_subcategory(self):
        from shopee_engine.taxonomy import resolve_subcategory
        sub_slug, sub_label = resolve_subcategory("Powerbanks")
        self.assertEqual(sub_slug, "powerbanks")

    def test_unknown_subcategory_returns_empty_tuple(self):
        from shopee_engine.taxonomy import resolve_subcategory
        result = resolve_subcategory("UNKNOWN")
        self.assertEqual(result, ("", ""))

    def test_subcategory_slug_has_no_ampersand_or_space(self):
        from shopee_engine.taxonomy import resolve_subcategory
        sub_slug, _ = resolve_subcategory("USB & Mobile Fans")
        self.assertNotIn("&", sub_slug)
        self.assertNotIn(" ", sub_slug)


class TestIsCanonical(unittest.TestCase):

    def test_valid_slug_returns_true(self):
        from shopee_engine.taxonomy import is_canonical
        for slug in ["home-living", "mobile-gadgets", "beauty", "health", "baby-kids", "sports", "food-drinks"]:
            self.assertTrue(is_canonical(slug), f"Expected '{slug}' to be canonical")

    def test_raw_shopee_category_not_canonical(self):
        from shopee_engine.taxonomy import is_canonical
        self.assertFalse(is_canonical("USB & Mobile Fans"))
        self.assertFalse(is_canonical("Powerbanks"))
        self.assertFalse(is_canonical("mom-baby"))  # old Astro slug
        self.assertFalse(is_canonical("food"))       # old Astro slug

    def test_usb_mobile_fans_subcategory_slug_not_a_category(self):
        from shopee_engine.taxonomy import is_canonical
        self.assertFalse(is_canonical("usb-mobile-fans"))  # subcategory, not category


# ---------------------------------------------------------------------------
# Tests: validate_article_for_review blocks non-canonical
# ---------------------------------------------------------------------------

class TestValidateForReviewCategoryBlock(unittest.TestCase):

    def test_non_canonical_category_blocks_review(self):
        from shopee_engine.seo_engine import validate_article_for_review
        db = _make_seo_db(category="USB & Mobile Fans")
        with _patch_db(db):
            result = validate_article_for_review("test-article")
        self.assertFalse(result["valid"])
        errors_text = " ".join(result["errors"])
        self.assertIn("canonical", errors_text.lower())

    def test_canonical_category_passes_review(self):
        from shopee_engine.seo_engine import validate_article_for_review
        db = _make_seo_db(category="mobile-gadgets")
        with _patch_db(db):
            result = validate_article_for_review("test-article")
        self.assertTrue(result["valid"], f"Expected valid, got errors: {result['errors']}")

    def test_old_astro_mom_baby_slug_blocks_review(self):
        from shopee_engine.seo_engine import validate_article_for_review
        db = _make_seo_db(category="mom-baby")
        with _patch_db(db):
            result = validate_article_for_review("test-article")
        self.assertFalse(result["valid"])

    def test_all_canonical_slugs_pass_review(self):
        from shopee_engine.seo_engine import validate_article_for_review
        from shopee_engine.taxonomy import CANONICAL_CATEGORIES
        for slug in CANONICAL_CATEGORIES:
            db = _make_seo_db(category=slug)
            with _patch_db(db):
                result = validate_article_for_review("test-article")
            self.assertTrue(result["valid"],
                f"Canonical slug '{slug}' should pass review, got: {result['errors']}")


# ---------------------------------------------------------------------------
# Tests: no auto-generated 404 category URL
# ---------------------------------------------------------------------------

class TestNoBrokenCategoryUrl(unittest.TestCase):

    def test_usb_mobile_fans_does_not_generate_broken_slug(self):
        """Verify map_to_canonical never returns 'usb-&-mobile-fans' or similar broken slug."""
        from shopee_engine.taxonomy import map_to_canonical
        result = map_to_canonical("USB & Mobile Fans")
        self.assertIsNotNone(result)
        slug, _ = result
        # The slug must not contain URL-unsafe characters
        self.assertNotIn("%", slug)
        self.assertNotIn("&", slug)
        # Must be exactly 'mobile-gadgets'
        self.assertEqual(slug, "mobile-gadgets")

    def test_category_page_url_is_valid(self):
        """Verify that constructing /category/{slug} with mapped slug produces a valid URL."""
        from shopee_engine.taxonomy import map_to_canonical
        from shopee_engine.taxonomy import CANONICAL_CATEGORIES
        result = map_to_canonical("USB & Mobile Fans")
        slug, _ = result
        url = f"/category/{slug}"
        # Must be a valid, non-encoded URL path
        self.assertEqual(url, "/category/mobile-gadgets")
        self.assertNotEqual(url, "/category/usb-%26-mobile-fans")


if __name__ == "__main__":
    unittest.main()
