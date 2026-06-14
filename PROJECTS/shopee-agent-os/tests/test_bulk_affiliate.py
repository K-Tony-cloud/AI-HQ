"""Tests for Phase 9.1 — bulk affiliate link ingestion.

Covers:
- valid link that resolves to a known product → imported
- duplicate link (product already has a stored link) → skipped
- link that resolves to an unknown product → unmatched, saved for review
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
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = KNOWN_URL
            result = _run_bulk(self.db, ["https://s.shopee.co.th/Abc123"])

        self.assertEqual(result["total"],    1)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["unmatched"], 0)
        self.assertEqual(result["invalid"],   0)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(len(result["matched_products"]), 1)
        self.assertIn("Dr.PONG", result["matched_products"][0]["title"])

    # ------------------------------------------------------------------
    # 2. Duplicate link
    # ------------------------------------------------------------------
    def test_duplicate_link(self) -> None:
        """A second link for the same product must be skipped as a duplicate."""
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = KNOWN_URL
            # First import succeeds
            _run_bulk(self.db, ["https://s.shopee.co.th/First111"])
            # Second import for the same product → duplicate
            result = _run_bulk(self.db, ["https://s.shopee.co.th/Second222"])

        self.assertEqual(result["total"],      1)
        self.assertEqual(result["imported"],   0)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["unmatched"],  0)
        self.assertIn("Dr.PONG", result["duplicate_products"][0]["title"])

    # ------------------------------------------------------------------
    # 3. Unmatched link
    # ------------------------------------------------------------------
    def test_unmatched_link(self) -> None:
        """A link pointing to an unknown product must land in unmatched, not imported."""
        with patch("shopee_engine.affiliate_link_engine.resolve_shopee_link") as mock_res:
            mock_res.return_value = UNKNOWN_URL
            result = _run_bulk(self.db, ["https://s.shopee.co.th/Unknown999"])

        self.assertEqual(result["total"],     1)
        self.assertEqual(result["imported"],  0)
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual(result["invalid"],   0)
        self.assertEqual(result["unmatched_links"][0]["reason"], "product_not_found")

        # Verify the unmatched entry was persisted to the DB
        import duckdb
        from shopee_engine.affiliate_link_engine import UNMATCHED_TABLE
        con = duckdb.connect(str(self.db), read_only=True)
        rows = con.execute(f"SELECT original_link FROM {UNMATCHED_TABLE}").fetchall()
        con.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "https://s.shopee.co.th/Unknown999")


if __name__ == "__main__":
    unittest.main()
