"""Regression tests: add_affiliate_product_by_itemid().

Coverage:
  - exact itemid match → success
  - itemid not found → error
  - itemid + shopid mismatch → error
  - keyword fallback (search_products_by_keyword) still works
  - duplicate: saving same itemid twice updates, does not create second row
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

def _make_test_db() -> str:
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
    con.executemany("""INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
        (26633396208, 310024922,
         'JisuLife handheld fan life10S พัดลมมือถือ 5000mAh', 'พัดลมมือถือ',
         805, 999, 500, 150, 4.9, 4.8, 20.0,
         'Electronics', 'Fans', 'USB Fan', 'JisuLife',
         'img1.jpg',
         'https://shopee.co.th/product/310024922/26633396208',
         'https://shope.ee/an_redir?origin=p1', 10),
        (6480267967, 59614772,
         'EZhome Mini Portable Handheld Fan พัดลมพกพา', 'พัดลมพกพา',
         149, 199, 800, 200, 4.7, 4.6, 20.0,
         'Electronics', 'Fans', 'USB Fan', 'EZhome',
         'img2.jpg',
         'https://shopee.co.th/product/59614772/6480267967',
         'https://shope.ee/an_redir?origin=p2', 10),
        (40959376984, 1505570169,
         'GOOJODOQ Gfs006 พัดลมพกพา 4000mah Type C', 'พัดลมไอเย็น',
         449, 599, 300, 80, 4.6, 4.5, 20.0,
         'Electronics', 'Fans', 'USB Fan', 'GOOJODOQ',
         'img3.jpg',
         'https://shopee.co.th/product/1505570169/40959376984',
         'https://shope.ee/an_redir?origin=p3', 10),
    ])
    con.execute("""
        CREATE TABLE affiliate_products (
            id INTEGER PRIMARY KEY, itemid BIGINT NOT NULL, shopid BIGINT NOT NULL,
            title VARCHAR DEFAULT '', category VARCHAR DEFAULT '',
            identification_url VARCHAR NOT NULL,
            affiliate_short_url VARCHAR DEFAULT '',
            campaign VARCHAR DEFAULT '', platform VARCHAR DEFAULT '',
            created_at VARCHAR, updated_at VARCHAR, latest_link BOOLEAN DEFAULT true
        )
    """)
    con.close()
    return path


def _patch_db(path: str):
    from pathlib import Path
    return patch("shopee_engine.config.config.db_path", Path(path))


# ---------------------------------------------------------------------------
# Tests: add_affiliate_product_by_itemid
# ---------------------------------------------------------------------------

class TestAddByItemid(unittest.TestCase):

    def test_exact_itemid_success(self):
        from shopee_engine.affiliate_products_engine import add_affiliate_product_by_itemid
        db = _make_test_db()
        with _patch_db(db):
            result = add_affiliate_product_by_itemid(
                itemid=26633396208,
                affiliate_short_url="https://s.shopee.co.th/NEWLINK1",
            )
        self.assertTrue(result["success"], f"Expected success, got: {result}")
        self.assertEqual(result["itemid"], 26633396208)
        self.assertEqual(result["shopid"], 310024922)
        self.assertIn("JisuLife", result["title"])
        self.assertEqual(result["action"], "added")

    def test_exact_itemid_not_found(self):
        from shopee_engine.affiliate_products_engine import add_affiliate_product_by_itemid
        db = _make_test_db()
        with _patch_db(db):
            result = add_affiliate_product_by_itemid(
                itemid=999999999,
                affiliate_short_url="https://s.shopee.co.th/NOTEXIST",
            )
        self.assertFalse(result["success"])
        self.assertIn("999999999", result["error"])

    def test_itemid_with_correct_shopid_success(self):
        from shopee_engine.affiliate_products_engine import add_affiliate_product_by_itemid
        db = _make_test_db()
        with _patch_db(db):
            result = add_affiliate_product_by_itemid(
                itemid=6480267967,
                affiliate_short_url="https://s.shopee.co.th/EZLINK",
                shopid=59614772,
            )
        self.assertTrue(result["success"], f"Expected success: {result}")
        self.assertEqual(result["shopid"], 59614772)

    def test_itemid_with_wrong_shopid_mismatch_error(self):
        from shopee_engine.affiliate_products_engine import add_affiliate_product_by_itemid
        db = _make_test_db()
        with _patch_db(db):
            result = add_affiliate_product_by_itemid(
                itemid=6480267967,
                affiliate_short_url="https://s.shopee.co.th/EZLINK",
                shopid=99999999,  # wrong shopid
            )
        self.assertFalse(result["success"])
        self.assertIn("mismatch", result["error"].lower())

    def test_no_duplicate_row_on_second_save(self):
        from shopee_engine.affiliate_products_engine import add_affiliate_product_by_itemid
        db = _make_test_db()
        with _patch_db(db):
            add_affiliate_product_by_itemid(40959376984, "https://s.shopee.co.th/LINK1")
            add_affiliate_product_by_itemid(40959376984, "https://s.shopee.co.th/LINK2")

        con = duckdb.connect(db, read_only=True)
        count = con.execute(
            "SELECT COUNT(*) FROM affiliate_products WHERE itemid=40959376984"
        ).fetchone()[0]
        con.close()
        self.assertEqual(count, 1, "Should upsert, not create duplicate row")

    def test_second_save_updates_link(self):
        from shopee_engine.affiliate_products_engine import add_affiliate_product_by_itemid
        db = _make_test_db()
        with _patch_db(db):
            add_affiliate_product_by_itemid(40959376984, "https://s.shopee.co.th/OLDLINK")
            result = add_affiliate_product_by_itemid(40959376984, "https://s.shopee.co.th/NEWLINK")

        self.assertTrue(result.get("already_had_link"), "Should report already_had_link=True")
        self.assertEqual(result["action"], "updated")

        con = duckdb.connect(db, read_only=True)
        stored = con.execute(
            "SELECT affiliate_short_url FROM affiliate_products WHERE itemid=40959376984"
        ).fetchone()[0]
        con.close()
        self.assertEqual(stored, "https://s.shopee.co.th/NEWLINK")

    def test_saved_link_is_picked_up_by_seo_refresh(self):
        """After add_affiliate_product_by_itemid, get_all_affiliate_products must return it."""
        from shopee_engine.affiliate_products_engine import (
            add_affiliate_product_by_itemid,
            get_all_affiliate_products,
        )
        db = _make_test_db()
        with _patch_db(db):
            add_affiliate_product_by_itemid(
                26633396208, "https://s.shopee.co.th/REFRESHTEST"
            )
            lookup = get_all_affiliate_products()

        canonical = "https://shopee.co.th/product/310024922/26633396208"
        self.assertIn(canonical, lookup)
        self.assertEqual(lookup[canonical], "https://s.shopee.co.th/REFRESHTEST")


# ---------------------------------------------------------------------------
# Tests: keyword fallback (search_products_by_keyword) still works
# ---------------------------------------------------------------------------

class TestKeywordFallback(unittest.TestCase):

    def test_keyword_search_finds_product(self):
        from shopee_engine.affiliate_link_engine import search_products_by_keyword
        db = _make_test_db()
        with _patch_db(db):
            results = search_products_by_keyword("JisuLife", limit=5)
        self.assertTrue(len(results) >= 1)
        titles = [r["title"] for r in results]
        self.assertTrue(any("JisuLife" in t for t in titles))

    def test_keyword_search_no_match(self):
        from shopee_engine.affiliate_link_engine import search_products_by_keyword
        db = _make_test_db()
        with _patch_db(db):
            results = search_products_by_keyword("XYZNOTEXISTPRODUCT9999", limit=5)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
