"""Tests for Phase 9.1 — bulk affiliate link ingestion.

Covers:
- valid link that resolves to a known product → imported
- two different links for same product → first imported, second updated
- exact same link submitted twice → second is duplicate_links
- link resolves OK but no product IDs / no metadata → needs_manual_match
- network error → invalid
- link pointing to an unknown product → needs_manual_match, saved for review
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


KNOWN_SHOPID  = 6583190
KNOWN_ITEMID  = 6690255925
KNOWN_TITLE   = "เซรั่ม Dr.PONG 28D Gen2"
KNOWN_URL     = f"https://shopee.co.th/product/{KNOWN_SHOPID}/{KNOWN_ITEMID}"

UNKNOWN_SHOPID = 9999999
UNKNOWN_ITEMID = 8888888
UNKNOWN_URL    = f"https://shopee.co.th/product/{UNKNOWN_SHOPID}/{UNKNOWN_ITEMID}"


def _make_test_db() -> Path:
    """Create a temp DuckDB file with a minimal products table."""
    import duckdb

    tmp = Path(tempfile.mktemp(suffix=".duckdb"))
    con = duckdb.connect(str(tmp))
    con.execute("""
        CREATE TABLE products (
            itemid       BIGINT,
            shopid       BIGINT,
            title        VARCHAR,
            product_link VARCHAR
        )
    """)
    con.execute(
        "INSERT INTO products VALUES (?, ?, ?, ?)",
        [KNOWN_ITEMID, KNOWN_SHOPID, KNOWN_TITLE, KNOWN_URL],
    )
    con.close()
    return tmp


def _run_bulk(db_path: Path, links: list[str], campaign: str = "test", platform: str = "tiktok") -> dict:
    from shopee_engine.affiliate_link_engine import bulk_add_affiliate_links
    from shopee_engine import affiliate_link_engine as eng

    orig = eng.config.db_path
    eng.config.db_path = db_path
    try:
        return bulk_add_affiliate_links(links, campaign=campaign, platform=platform)
    finally:
        eng.config.db_path = orig


class TestBulkAffiliateLinks(unittest.TestCase):

    def setUp(self) -> None:
        self.db = _make_test_db()

    def tearDown(self) -> None:
        self.db.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 1. Valid matched link
    # ------------------------------------------------------------------
    def test_valid_matched_link(self) -> None:
        """A short link that resolves to a known product must be imported."""
        short = "https://s.shopee.co.th/Abc123"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = (KNOWN_URL, [short, KNOWN_URL])
            result = _run_bulk(self.db, [short])

        self.assertEqual(result["total"],    1)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["needs_manual_match"], 0)
        self.assertEqual(result["invalid"],   0)
        self.assertEqual(result["duplicate_links"], 0)
        self.assertEqual(len(result["imported_products"]), 1)
        self.assertIn("Dr.PONG", result["imported_products"][0]["title"])

    # ------------------------------------------------------------------
    # 2. Two different short links for same product (updated, not duplicate)
    # ------------------------------------------------------------------
    def test_same_product_two_different_links(self) -> None:
        """Two different short links for the same product: first→imported, second→updated."""
        s1, s2 = "https://s.shopee.co.th/Link001", "https://s.shopee.co.th/Link002"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = (KNOWN_URL, [s1, KNOWN_URL])
            r1 = _run_bulk(self.db, [s1])
            mock_res.return_value = (KNOWN_URL, [s2, KNOWN_URL])
            r2 = _run_bulk(self.db, [s2])

        self.assertEqual(r1["imported"], 1)
        self.assertEqual(r1["updated"], 0)
        self.assertEqual(r2["imported"], 0)
        self.assertEqual(r2["updated"], 1)
        self.assertEqual(r2["duplicate_links"], 0)

    # ------------------------------------------------------------------
    # 3. Exact same link submitted twice → second is duplicate_links
    # ------------------------------------------------------------------
    def test_same_link_repeated(self) -> None:
        """Submitting the exact same short link twice → second submission is a duplicate_link."""
        short = "https://s.shopee.co.th/SameLink"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = (KNOWN_URL, [short, KNOWN_URL])
            _run_bulk(self.db, [short])
            result = _run_bulk(self.db, [short])

        self.assertEqual(result["duplicate_links"], 1)
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["updated"], 0)

    # ------------------------------------------------------------------
    # 4. Link resolves OK but no product IDs / no metadata → needs_manual_match
    # ------------------------------------------------------------------
    def test_valid_link_no_product_id(self) -> None:
        """Link resolves to a URL with no product IDs and no page metadata → needs_manual_match."""
        short = "https://s.shopee.co.th/NoIdLink"
        no_id_url = "https://shopee.co.th/search?keyword=something"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res, \
             patch("shopee_engine.affiliate_link_engine._fetch_page_metadata") as mock_meta:
            mock_res.return_value = (no_id_url, [short, no_id_url])
            mock_meta.return_value = {}   # no og:url, no title
            result = _run_bulk(self.db, [short])

        self.assertEqual(result["needs_manual_match"], 1)
        self.assertEqual(result["invalid"], 0)
        self.assertEqual(result["imported"], 0)

    # ------------------------------------------------------------------
    # 5. Network error → invalid (not unmatched)
    # ------------------------------------------------------------------
    def test_broken_link(self) -> None:
        """Network error → invalid (not unmatched)."""
        short = "https://s.shopee.co.th/BrokenLink"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = (None, [short])
            result = _run_bulk(self.db, [short])

        self.assertEqual(result["invalid"], 1)
        self.assertEqual(result["needs_manual_match"], 0)
        self.assertEqual(result["imported"], 0)

    # ------------------------------------------------------------------
    # 6. Link pointing to an unknown product → needs_manual_match
    # ------------------------------------------------------------------
    def test_unmatched_link(self) -> None:
        """A link pointing to an unknown product must land in needs_manual_match, not imported."""
        short = "https://s.shopee.co.th/Unknown999"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = (UNKNOWN_URL, [short, UNKNOWN_URL])
            result = _run_bulk(self.db, [short])

        self.assertEqual(result["total"],     1)
        self.assertEqual(result["imported"],  0)
        self.assertEqual(result["needs_manual_match"], 1)
        self.assertEqual(result["invalid"],   0)
        self.assertEqual(result["unmatched_links"][0]["reason"], "product_not_identified")

        # Verify the unmatched entry was persisted to the DB
        import duckdb
        from shopee_engine.affiliate_link_engine import UNMATCHED_TABLE
        con = duckdb.connect(str(self.db), read_only=True)
        rows = con.execute(f"SELECT original_link FROM {UNMATCHED_TABLE}").fetchall()
        con.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "https://s.shopee.co.th/Unknown999")

    # ------------------------------------------------------------------
    # 7. (Legacy name alias) duplicate_link — different links same product → updated
    # ------------------------------------------------------------------
    def test_duplicate_link(self) -> None:
        """Two DIFFERENT short links for the same product: first→imported, second→updated."""
        s1, s2 = "https://s.shopee.co.th/First111", "https://s.shopee.co.th/Second222"
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = (KNOWN_URL, [s1, KNOWN_URL])
            r1 = _run_bulk(self.db, [s1])
            mock_res.return_value = (KNOWN_URL, [s2, KNOWN_URL])
            r2 = _run_bulk(self.db, [s2])

        self.assertEqual(r1["imported"], 1)
        self.assertEqual(r2["updated"], 1)
        self.assertEqual(r2["duplicate_links"], 0)
        self.assertIn("Dr.PONG", r2["updated_products"][0]["title"])


if __name__ == "__main__":
    unittest.main()
