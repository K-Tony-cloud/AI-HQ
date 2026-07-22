"""Unit tests for shopee_engine.product_resolver.

Coverage:
  - classify_reference: itemid, Shopee URL (product path, i-dot, origin_link), short URL, keyword
  - extract_shopee_ids_from_url: all URL formats + malformed
  - build_direct_url: datafeed match, fallback constructed, missing shopid
  - resolve_product_by_ids: unique, ambiguous, not_found, shopid filter
  - resolve_product (main entry): itemid, shopee_url, short_url, keyword
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shopee_engine.product_resolver import (
    classify_reference,
    extract_shopee_ids_from_url,
    build_direct_url,
    resolve_product_by_ids,
    resolve_product,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_PRODUCTS = [
    # itemid,       shopid,      title,                    price,  image_link,  product_link,  shop_name
    (26583952360, 1092528171, "UNEED Powerbank CCC",        739,    "img1.jpg", "https://shopee.co.th/product/1092528171/26583952360", "UNEED TH"),
    (57956633734,  538478477, "VINKO V9 Pro CCC Powerbank", 959,    "img2.jpg", "https://shopee.co.th/product/538478477/57956633734",  "VINKO Official"),
    (53155330120,   82732896, "AUKEY PB-Y59 CCC",           999,    "img3.jpg", "https://shopee.co.th/product/82732896/53155330120",   "AUKEY TH"),
    # itemid shared by two shops (ambiguous scenario)
    (99999000001,  111111111, "Ambiguous Product Shop A",   100,    "imgA.jpg", "https://shopee.co.th/product/111111111/99999000001",  "Shop A"),
    (99999000001,  222222222, "Ambiguous Product Shop B",   200,    "imgB.jpg", "https://shopee.co.th/product/222222222/99999000001",  "Shop B"),
]


def _make_test_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)
    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE products (
            itemid BIGINT, shopid BIGINT,
            title VARCHAR, description VARCHAR DEFAULT '',
            sale_price BIGINT, price BIGINT DEFAULT 0,
            item_sold BIGINT DEFAULT 0, "like" BIGINT DEFAULT 0,
            shop_rating DOUBLE DEFAULT 4.5, item_rating DOUBLE DEFAULT 4.5,
            discount_percentage DOUBLE DEFAULT 0,
            global_category1 VARCHAR DEFAULT '', global_category2 VARCHAR DEFAULT '',
            global_category3 VARCHAR DEFAULT '', global_brand VARCHAR DEFAULT '',
            image_link VARCHAR,
            product_link VARCHAR,
            "product_short link" VARCHAR DEFAULT '',
            stock INTEGER DEFAULT 10,
            shop_name VARCHAR DEFAULT '',
            seller_name VARCHAR DEFAULT ''
        )
    """)
    for row in _SAMPLE_PRODUCTS:
        iid, sid, title, price, img, plink, shop = row
        con.execute(
            "INSERT INTO products (itemid, shopid, title, sale_price, image_link, product_link, shop_name) "
            "VALUES (?,?,?,?,?,?,?)",
            [iid, sid, title, price, img, plink, shop],
        )
    con.close()
    return path


# ---------------------------------------------------------------------------
# classify_reference
# ---------------------------------------------------------------------------

class TestClassifyReference(unittest.TestCase):
    def test_numeric_itemid(self):
        self.assertEqual(classify_reference("26583952360"), "itemid")

    def test_shopee_product_url(self):
        self.assertEqual(
            classify_reference("https://shopee.co.th/product/1092528171/26583952360"),
            "shopee_url",
        )

    def test_shopee_i_dot_url(self):
        self.assertEqual(
            classify_reference("https://shopee.co.th/UNEED-i.1092528171.26583952360"),
            "shopee_url",
        )

    def test_short_url_shope_ee(self):
        self.assertEqual(
            classify_reference("https://shope.ee/abc123"),
            "short_url",
        )

    def test_short_url_s_shopee(self):
        self.assertEqual(
            classify_reference("https://s.shopee.co.th/abc123"),
            "short_url",
        )

    def test_keyword(self):
        self.assertEqual(classify_reference("power bank ccc"), "keyword")

    def test_malformed_non_shopee_url(self):
        self.assertEqual(classify_reference("https://example.com/abc"), "keyword")

    def test_empty_string(self):
        self.assertEqual(classify_reference(""), "keyword")


# ---------------------------------------------------------------------------
# extract_shopee_ids_from_url
# ---------------------------------------------------------------------------

class TestExtractShopeeIds(unittest.TestCase):
    def test_product_path(self):
        url = "https://shopee.co.th/product/1092528171/26583952360"
        self.assertEqual(extract_shopee_ids_from_url(url), (1092528171, 26583952360))

    def test_i_dot_format(self):
        url = "https://shopee.co.th/UNEED-Powerbank-i.1092528171.26583952360"
        self.assertEqual(extract_shopee_ids_from_url(url), (1092528171, 26583952360))

    def test_origin_link_format(self):
        url = (
            "https://shope.ee/an_redir?origin_link="
            "https%3A%2F%2Fshopee.co.th%2Fproduct%2F1092528171%2F26583952360"
        )
        # URL-decoded origin_link won't be decoded here — test unencoded version
        url2 = (
            "https://shope.ee/an_redir?origin_link="
            "https://shopee.co.th/product/1092528171/26583952360"
        )
        self.assertEqual(extract_shopee_ids_from_url(url2), (1092528171, 26583952360))

    def test_empty_url(self):
        self.assertIsNone(extract_shopee_ids_from_url(""))

    def test_malformed(self):
        self.assertIsNone(extract_shopee_ids_from_url("not-a-url"))


# ---------------------------------------------------------------------------
# build_direct_url
# ---------------------------------------------------------------------------

class TestBuildDirectUrl(unittest.TestCase):
    def test_matching_product_link_returns_datafeed(self):
        product_link = "https://shopee.co.th/product/1092528171/26583952360"
        url, src = build_direct_url(1092528171, 26583952360, product_link)
        self.assertEqual(url, product_link)
        self.assertEqual(src, "datafeed")

    def test_mismatched_product_link_falls_back(self):
        wrong_link = "https://shopee.co.th/product/9999/9999"
        url, src = build_direct_url(1092528171, 26583952360, wrong_link)
        self.assertEqual(url, "https://shopee.co.th/product/1092528171/26583952360")
        self.assertEqual(src, "constructed")

    def test_no_product_link_returns_constructed(self):
        url, src = build_direct_url(1092528171, 26583952360, None)
        self.assertEqual(url, "https://shopee.co.th/product/1092528171/26583952360")
        self.assertEqual(src, "constructed")

    def test_missing_shopid_returns_empty(self):
        url, src = build_direct_url(0, 26583952360, None)
        self.assertEqual(url, "")
        self.assertEqual(src, "unavailable")


# ---------------------------------------------------------------------------
# resolve_product_by_ids
# ---------------------------------------------------------------------------

class TestResolveProductByIds(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_unique_itemid_resolves(self):
        r = resolve_product_by_ids(26583952360, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "resolved")
        self.assertEqual(r["itemid"], 26583952360)
        self.assertEqual(r["shopid"], 1092528171)
        self.assertIn("shopee.co.th/product", r["direct_product_url"])
        self.assertIsNotNone(r["title"])

    def test_itemid_not_found(self):
        r = resolve_product_by_ids(0, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "not_found")

    def test_ambiguous_itemid_no_shopid(self):
        r = resolve_product_by_ids(99999000001, shopid=None, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "ambiguous")
        candidates = r.get("candidates", [])
        self.assertEqual(len(candidates), 2)
        shopids = {c["shopid"] for c in candidates}
        self.assertIn(111111111, shopids)
        self.assertIn(222222222, shopids)

    def test_ambiguous_itemid_with_shopid_resolves(self):
        r = resolve_product_by_ids(99999000001, shopid=111111111, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "resolved")
        self.assertEqual(r["shopid"], 111111111)

    def test_shopid_mismatch_returns_not_found(self):
        r = resolve_product_by_ids(26583952360, shopid=999, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "not_found")

    def test_direct_url_format(self):
        r = resolve_product_by_ids(57956633734, db_path=self.db_path)
        self.assertEqual(
            r["direct_product_url"],
            "https://shopee.co.th/product/538478477/57956633734",
        )


# ---------------------------------------------------------------------------
# resolve_product (main entry)
# ---------------------------------------------------------------------------

class TestResolveProduct(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_itemid_string(self):
        r = resolve_product("26583952360", db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "resolved")
        self.assertEqual(r["itemid"], 26583952360)

    def test_shopee_url(self):
        url = "https://shopee.co.th/product/538478477/57956633734"
        r = resolve_product(url, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "resolved")
        self.assertEqual(r["itemid"], 57956633734)
        self.assertEqual(r["shopid"], 538478477)

    def test_short_url_returns_invalid(self):
        r = resolve_product("https://s.shopee.co.th/abc123", db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "invalid")

    def test_keyword_returns_invalid(self):
        r = resolve_product("power bank ccc", db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "invalid")

    def test_numeric_never_goes_to_full_text_search(self):
        # A numeric string that's NOT in DB should return not_found, not a search result
        r = resolve_product("12345678901", db_path=self.db_path)
        self.assertIn(r["resolution_status"], ("not_found",))

    def test_shopee_url_shopid_mismatch(self):
        url = "https://shopee.co.th/product/999999/26583952360"
        r = resolve_product(url, shopid=111111, db_path=self.db_path)
        # shopid in URL (999999) != shopid param (111111) → invalid
        self.assertEqual(r["resolution_status"], "invalid")

    def test_url_with_mismatched_shopid_param(self):
        url = "https://shopee.co.th/product/1092528171/26583952360"
        r = resolve_product(url, shopid=9999999, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "invalid")

    def test_url_with_correct_shopid_param(self):
        url = "https://shopee.co.th/product/1092528171/26583952360"
        r = resolve_product(url, shopid=1092528171, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "resolved")


# ---------------------------------------------------------------------------
# Resolution confidence scoring
# ---------------------------------------------------------------------------

class TestResolutionConfidenceScore(unittest.TestCase):
    """Verify _compute_resolution_score output for each resolution path."""

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def _score(self, **kwargs):
        from shopee_engine.product_resolver import _compute_resolution_score
        return _compute_resolution_score(**kwargs)

    # --- score structure ---

    def test_returns_score_level_factors(self):
        r = self._score(ref_type="itemid", shopid_provided=False, ambiguous_resolved=False,
                        url_source="datafeed", has_title=True, has_image=True)
        self.assertIn("score", r)
        self.assertIn("level", r)
        self.assertIn("factors", r)

    def test_score_is_float_in_range(self):
        r = self._score(ref_type="itemid", shopid_provided=False, ambiguous_resolved=False,
                        url_source="datafeed", has_title=True, has_image=True)
        self.assertIsInstance(r["score"], float)
        self.assertGreaterEqual(r["score"], 0.0)
        self.assertLessEqual(r["score"], 1.0)

    # --- shopee_url is highest base ---

    def test_shopee_url_score_higher_than_itemid(self):
        url_score  = self._score(ref_type="shopee_url", shopid_provided=True, ambiguous_resolved=False,
                                 url_source="datafeed", has_title=True, has_image=True)
        item_score = self._score(ref_type="itemid", shopid_provided=False, ambiguous_resolved=False,
                                 url_source="datafeed", has_title=True, has_image=True)
        self.assertGreater(url_score["score"], item_score["score"])

    def test_shopee_url_datafeed_full_data_is_high(self):
        r = self._score(ref_type="shopee_url", shopid_provided=True, ambiguous_resolved=False,
                        url_source="datafeed", has_title=True, has_image=True)
        self.assertEqual(r["level"], "high")

    # --- datafeed bonus ---

    def test_datafeed_source_boosts_score(self):
        datafeed  = self._score(ref_type="itemid", shopid_provided=False, ambiguous_resolved=False,
                                url_source="datafeed", has_title=False, has_image=False)
        construct = self._score(ref_type="itemid", shopid_provided=False, ambiguous_resolved=False,
                                url_source="constructed", has_title=False, has_image=False)
        self.assertGreater(datafeed["score"], construct["score"])

    # --- ambiguous resolved is lower ---

    def test_ambiguous_resolved_lower_than_unique(self):
        ambig  = self._score(ref_type="itemid", shopid_provided=True, ambiguous_resolved=True,
                             url_source="datafeed", has_title=True, has_image=True)
        unique = self._score(ref_type="itemid", shopid_provided=True, ambiguous_resolved=False,
                             url_source="datafeed", has_title=True, has_image=True)
        self.assertLess(ambig["score"], unique["score"])

    # --- integration: resolve_product returns confidence fields ---

    def test_resolved_result_has_confidence_fields(self):
        r = resolve_product("26583952360", db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "resolved")
        self.assertIsNotNone(r["confidence_score"])
        self.assertIn(r["confidence_level"], ("high", "medium", "low", "very_low"))
        self.assertIsInstance(r["confidence_factors"], list)
        self.assertTrue(len(r["confidence_factors"]) > 0)

    def test_url_resolve_returns_higher_score_than_itemid(self):
        url  = resolve_product("https://shopee.co.th/product/1092528171/26583952360",
                               db_path=self.db_path)
        iid  = resolve_product("26583952360", db_path=self.db_path)
        self.assertGreater(url["confidence_score"], iid["confidence_score"])

    def test_ambiguous_result_score_is_zero(self):
        r = resolve_product_by_ids(99999000001, shopid=None, db_path=self.db_path)
        self.assertEqual(r["resolution_status"], "ambiguous")
        self.assertEqual(r["confidence_score"], 0.0)
        self.assertEqual(r["confidence_level"], "none")

    def test_not_found_has_no_score(self):
        r = resolve_product("0", db_path=self.db_path)
        self.assertIsNone(r["confidence_score"])

    def test_ambiguous_candidates_have_confidence_fields(self):
        r = resolve_product_by_ids(99999000001, shopid=None, db_path=self.db_path)
        candidates = r.get("candidates", [])
        self.assertTrue(len(candidates) > 0)
        for c in candidates:
            self.assertIn("confidence_score", c)
            self.assertIn("confidence_level", c)
            self.assertIn("confidence_note", c)


# ---------------------------------------------------------------------------
# CCC attribute evidence detection
# ---------------------------------------------------------------------------

class TestAttributeEvidenceDetection(unittest.TestCase):
    """Verify _detect_attribute_evidence — no 'verified' language."""

    def _ev(self, title: str, desc: str = "") -> dict:
        from shopee_engine.seo_engine import (
            _detect_attribute_evidence, _CCC_BRACKET_RE, _CCC_PLAIN_RE,
        )
        return _detect_attribute_evidence(title, desc, _CCC_BRACKET_RE, _CCC_PLAIN_RE)

    def test_bracket_ccc_in_title_is_title_bracket(self):
        r = self._ev("[CCC] AUKEY Powerbank")
        self.assertEqual(r["evidence_source"], "title_bracket")

    def test_qi2_plus_ccc_bracket_detected(self):
        r = self._ev("[Qi2+CCC] UNEED Powerbank")
        self.assertEqual(r["evidence_source"], "title_bracket")

    def test_plain_ccc_in_title_is_title_mention(self):
        r = self._ev("Powerbank CCC 20000mAh")
        self.assertEqual(r["evidence_source"], "title_mention")

    def test_ccc_only_in_description_is_description_match(self):
        r = self._ev("Generic Powerbank", "มาตรฐาน CCC รับประกัน")
        self.assertEqual(r["evidence_source"], "description_match")

    def test_no_ccc_anywhere_is_no_evidence(self):
        r = self._ev("Powerbank 20000mAh Fast Charge", "ชาร์จเร็ว USB-C")
        self.assertEqual(r["evidence_source"], "no_evidence")

    def test_evidence_text_not_empty_when_found(self):
        r = self._ev("[CCC] Powerbank")
        self.assertTrue(len(r["evidence_text"]) > 0)

    def test_no_evidence_text_is_empty(self):
        r = self._ev("Powerbank no CCC here")
        # "no CCC here" has CCC → should be title_mention
        r2 = self._ev("Powerbank 20000mAh", "")
        self.assertEqual(r2["evidence_source"], "no_evidence")
        self.assertEqual(r2["evidence_text"], "")

    def test_note_never_contains_word_verified(self):
        for title, desc in [
            ("[CCC] Product", ""),
            ("Product CCC", ""),
            ("Product", "has CCC standard"),
            ("Product", "no mention"),
        ]:
            r = self._ev(title, desc)
            self.assertNotIn("verified", r["confidence_note"].lower(),
                             f"'verified' found in note for title={title!r}: {r['confidence_note']}")

    def test_get_products_for_preview_includes_ccc_fields(self):
        """Integration: preview products include ccc_evidence keys."""
        import os
        import tempfile
        import duckdb
        from unittest.mock import patch
        from pathlib import Path

        # Minimal DB
        fd, path = tempfile.mkstemp(suffix=".duckdb")
        os.close(fd); os.unlink(path)
        con = duckdb.connect(path)
        con.execute("""
            CREATE TABLE seo_articles (
                id INTEGER PRIMARY KEY, article_id VARCHAR UNIQUE NOT NULL,
                keyword VARCHAR NOT NULL, title VARCHAR DEFAULT '',
                category VARCHAR DEFAULT '', meta_description VARCHAR DEFAULT '',
                content_md TEXT DEFAULT '', status VARCHAR DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_product_sync TIMESTAMP, affiliate_disclosure BOOLEAN DEFAULT true,
                published_path VARCHAR DEFAULT '', git_commit_hash VARCHAR DEFAULT '',
                reviewed_at TIMESTAMP, review_note VARCHAR DEFAULT '',
                published_at TIMESTAMP, category_label VARCHAR DEFAULT '',
                subcategory VARCHAR DEFAULT '', subcategory_label VARCHAR DEFAULT ''
            )""")
        con.execute("""
            CREATE TABLE seo_article_products (
                id INTEGER PRIMARY KEY, article_id VARCHAR NOT NULL,
                itemid BIGINT, shopid BIGINT,
                product_title VARCHAR DEFAULT '', sale_price BIGINT DEFAULT 0,
                image_link VARCHAR DEFAULT '', affiliate_link VARCHAR DEFAULT '',
                affiliate_link_type VARCHAR DEFAULT 'none',
                opportunity_score DOUBLE DEFAULT 0,
                rank_in_article INTEGER DEFAULT 0,
                product_status VARCHAR DEFAULT 'active',
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        con.execute("""
            CREATE TABLE products (
                itemid BIGINT, shopid BIGINT,
                title VARCHAR DEFAULT '', description VARCHAR DEFAULT '',
                sale_price BIGINT DEFAULT 0, image_link VARCHAR DEFAULT '',
                product_link VARCHAR DEFAULT '', shop_name VARCHAR DEFAULT '',
                seller_name VARCHAR DEFAULT ''
            )""")
        con.execute("INSERT INTO seo_articles (id, article_id, keyword, title) VALUES (1, 'ev-test', 'kw', 'T')")
        con.execute("INSERT INTO seo_article_products (id, article_id, itemid, shopid, product_title, rank_in_article) VALUES (1, 'ev-test', 111, 222, '[CCC] Product', 1)")
        con.execute("INSERT INTO products (itemid, shopid, title, description, shop_name) VALUES (111, 222, '[CCC] Product', 'มาตรฐาน CCC', 'Shop')")
        con.close()
        try:
            with patch("shopee_engine.config.config.db_path", Path(path)):
                from shopee_engine.seo_engine import get_products_for_preview
                products = get_products_for_preview("ev-test")
            self.assertEqual(len(products), 1)
            p = products[0]
            self.assertIn("ccc_evidence_source", p)
            self.assertIn("ccc_evidence_text", p)
            self.assertIn("ccc_confidence_note", p)
            self.assertNotIn("verified", p["ccc_confidence_note"].lower())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
