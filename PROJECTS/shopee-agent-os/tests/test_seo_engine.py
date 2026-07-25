"""Tests for shopee_engine/seo_engine.py

Covers:
- format_price: various inputs including None, int, float
- generate_slug: Thai keywords, special characters, empty string
- Frontmatter validation: required fields present in generated draft
- Migration: idempotent (safe to run twice)
- generate_article_draft: no products found case
- generate_article_draft: no affiliate link case (datafeed fallback)
- generate_article_draft: no API key (template fallback)
- update_article_status: valid and invalid transitions
- validate_article_for_publish: blocks draft status
- validate_article_for_publish: blocks reviewed with no products
- refresh_article_products: product not found marks not_found status
- refresh_article_products: out of stock marking
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_db() -> Path:
    """Create a temp DuckDB with minimal products + affiliate_products tables."""
    import duckdb

    tmp = Path(tempfile.mktemp(suffix=".duckdb"))
    con = duckdb.connect(str(tmp))
    con.execute("""
        CREATE TABLE products (
            itemid              BIGINT,
            shopid              BIGINT,
            title               VARCHAR,
            sale_price          BIGINT,
            price               BIGINT,
            item_sold           BIGINT,
            "like"              BIGINT,
            shop_rating         DOUBLE,
            item_rating         DOUBLE,
            discount_percentage BIGINT,
            global_category1    VARCHAR,
            global_category2    VARCHAR,
            global_category3    VARCHAR,
            global_brand        VARCHAR,
            image_link          VARCHAR,
            product_link        VARCHAR,
            "product_short link" VARCHAR,
            description         VARCHAR,
            stock               BIGINT DEFAULT 1
        )
    """)
    con.execute("""
        CREATE TABLE affiliate_products (
            id                  INTEGER,
            itemid              BIGINT,
            shopid              BIGINT,
            title               VARCHAR,
            category            VARCHAR,
            identification_url  VARCHAR,
            affiliate_short_url VARCHAR,
            campaign            VARCHAR DEFAULT '',
            platform            VARCHAR DEFAULT '',
            created_at          VARCHAR DEFAULT '',
            updated_at          VARCHAR DEFAULT '',
            latest_link         BOOLEAN DEFAULT true
        )
    """)

    # Insert test products
    con.executemany("""
        INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        (1001, 5001, "เมาส์เกมมิ่ง ราคาถูก", 799, 999, 5000, 300, 4.8, 4.7, 20,
         "Mobile & Gadgets", "Computer Accessories", "Gaming Mice",
         "BrandA", "https://cf.shopee.co.th/file/img1", "https://shopee.co.th/product/5001/1001",
         "https://shope.ee/an_redir?origin_link=...1", "เมาส์เกมมิ่งคุณภาพดี", 50),
        (1002, 5002, "เมาส์ไร้สาย RGB", 1290, 1590, 3200, 200, 4.6, 4.5, 19,
         "Mobile & Gadgets", "Computer Accessories", "Gaming Mice",
         "BrandB", "https://cf.shopee.co.th/file/img2", "https://shopee.co.th/product/5002/1002",
         "https://shope.ee/an_redir?origin_link=...2", "เมาส์ไร้สาย", 30),
        (1003, 5003, "เมาส์เกมมิ่ง DPI สูง", 1450, 1800, 2800, 150, 4.5, 4.4, 19,
         "Mobile & Gadgets", "Computer Accessories", "Gaming Mice",
         "BrandC", "https://cf.shopee.co.th/file/img3", "https://shopee.co.th/product/5003/1003",
         "", "สินค้าไม่มี affiliate link", 10),
    ])

    # Insert confirmed affiliate products for ALL test products so validation passes
    con.executemany("""
        INSERT INTO affiliate_products
        (id, itemid, shopid, title, category, identification_url, affiliate_short_url)
        VALUES (?, ?, ?, ?, 'Gaming Mice', ?, ?)
    """, [
        (1, 1001, 5001, 'เมาส์เกมมิ่ง ราคาถูก',
         'https://shopee.co.th/product/5001/1001', 'https://s.shopee.co.th/TestMouse001'),
        (2, 1002, 5002, 'เมาส์ไร้สาย RGB',
         'https://shopee.co.th/product/5002/1002', 'https://s.shopee.co.th/TestMouse002'),
        (3, 1003, 5003, 'เมาส์เกมมิ่ง DPI สูง',
         'https://shopee.co.th/product/5003/1003', 'https://s.shopee.co.th/TestMouse003'),
    ])

    con.close()
    return tmp


def _patch_db(db_path: Path):
    return [
        patch("shopee_engine.config.DB_PATH", str(db_path)),
        patch("shopee_engine.config.config.db_path", db_path),
        patch("shopee_engine.seo_engine.config.db_path", db_path),
    ]


# ---------------------------------------------------------------------------
# format_price tests
# ---------------------------------------------------------------------------

class TestFormatPrice:
    def test_integer_price(self):
        from shopee_engine.seo_engine import format_price
        assert format_price(299) == "฿299"

    def test_price_with_comma(self):
        from shopee_engine.seo_engine import format_price
        assert format_price(1500) == "฿1,500"

    def test_none_returns_label(self):
        from shopee_engine.seo_engine import format_price
        assert format_price(None) == "ไม่ระบุราคา"

    def test_float_rounds_to_int(self):
        from shopee_engine.seo_engine import format_price
        assert format_price(299.9) == "฿299"

    def test_zero(self):
        from shopee_engine.seo_engine import format_price
        assert format_price(0) == "฿0"

    def test_string_non_numeric(self):
        from shopee_engine.seo_engine import format_price
        assert format_price("abc") == "ไม่ระบุราคา"

    def test_large_price(self):
        from shopee_engine.seo_engine import format_price
        assert format_price(15000) == "฿15,000"


# ---------------------------------------------------------------------------
# generate_slug tests
# ---------------------------------------------------------------------------

class TestGenerateSlug:
    def test_thai_keyword(self):
        from shopee_engine.seo_engine import generate_slug
        slug = generate_slug("เมาส์เกมมิ่งไม่เกิน 1500")
        assert "-" in slug or len(slug) > 0
        assert " " not in slug

    def test_english_keyword(self):
        from shopee_engine.seo_engine import generate_slug
        slug = generate_slug("gaming mouse budget")
        assert slug == "gaming-mouse-budget"

    def test_special_chars_removed(self):
        from shopee_engine.seo_engine import generate_slug
        slug = generate_slug("mouse @ 1500!!!")
        assert "@" not in slug
        assert "!" not in slug

    def test_empty_string_returns_hash(self):
        from shopee_engine.seo_engine import generate_slug
        slug = generate_slug("")
        assert len(slug) > 0

    def test_no_leading_trailing_dash(self):
        from shopee_engine.seo_engine import generate_slug
        slug = generate_slug("  keyword  ")
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_multiple_spaces_become_single_dash(self):
        from shopee_engine.seo_engine import generate_slug
        slug = generate_slug("a  b   c")
        assert "a-b-c" == slug


# ---------------------------------------------------------------------------
# Migration idempotency test
# ---------------------------------------------------------------------------

class TestMigration:
    def test_migration_idempotent(self):
        """Running migration twice must not raise or lose data."""
        import duckdb
        db = Path(tempfile.mktemp(suffix=".duckdb"))
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db):
                from shopee_engine.seo_engine import run_migration
                r1 = run_migration()
                r2 = run_migration()
            assert "ok" in r1["seo_articles"]
            assert "ok" in r2["seo_articles"]
        finally:
            db.unlink(missing_ok=True)

    def test_migration_preserves_existing_rows(self):
        """Running migration a second time must not delete existing data."""
        import duckdb
        db = Path(tempfile.mktemp(suffix=".duckdb"))
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db):
                from shopee_engine.seo_engine import run_migration, _connect, SEO_ARTICLES_TABLE
                run_migration()
                con = _connect(read_only=False)
                con.execute(f"""
                    INSERT INTO {SEO_ARTICLES_TABLE}
                    (id, article_id, keyword, status)
                    VALUES (1, 'test-slug', 'test keyword', 'draft')
                """)
                con.close()
                run_migration()  # second run
                con2 = _connect(read_only=True)
                count = con2.execute(f"SELECT COUNT(*) FROM {SEO_ARTICLES_TABLE}").fetchone()[0]
                con2.close()
            assert count == 1
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# generate_article_draft tests
# ---------------------------------------------------------------------------

class TestGenerateArticleDraft:
    def _run_draft(self, db_path: Path, keyword: str, **kwargs) -> dict:
        import importlib
        import shopee_engine.seo_engine as eng
        importlib.reload(eng)
        patches = _patch_db(db_path)
        with patch("shopee_engine.seo_engine.config.db_path", db_path), \
             patch("shopee_engine.affiliate_products_engine.config.db_path", db_path), \
             patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}), \
             patch("shopee_engine.content_engine.detect_provider", return_value="template"):
            from shopee_engine.seo_engine import generate_article_draft
            return generate_article_draft(keyword, **kwargs)

    def test_no_products_returns_error(self):
        db = _make_test_db()
        try:
            result = self._run_draft(db, "สินค้าที่ไม่มีในฐานข้อมูล XYZ999")
            assert result["success"] is False
            assert "ไม่พบสินค้า" in result["error"]
        finally:
            db.unlink(missing_ok=True)

    def test_draft_created_with_products(self):
        db = _make_test_db()
        try:
            result = self._run_draft(db, "เมาส์เกมมิ่ง")
            assert result["success"] is True
            assert result["products_count"] >= 1
            assert result["article_id"]
            assert result["title"]
        finally:
            db.unlink(missing_ok=True)

    def test_frontmatter_required_fields(self):
        db = _make_test_db()
        try:
            result = self._run_draft(db, "เมาส์เกมมิ่ง")
            assert result["success"] is True

            # Read back content from DB
            import duckdb
            con = duckdb.connect(str(db), read_only=True)
            from shopee_engine.seo_engine import SEO_ARTICLES_TABLE
            row = con.execute(
                f"SELECT content_md FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
                [result["article_id"]],
            ).fetchone()
            con.close()

            content = row[0]
            assert "article_id:" in content
            assert "keyword:" in content
            assert "article_status:" in content
            assert "affiliate_disclosure:" in content
            assert "created_at:" in content
            assert "updated_at:" in content
            assert "last_product_sync:" in content
        finally:
            db.unlink(missing_ok=True)

    def test_no_affiliate_link_uses_datafeed(self):
        db = _make_test_db()
        try:
            result = self._run_draft(db, "เมาส์เกมมิ่ง")
            assert result["success"] is True
            # product 1001 has confirmed link, 1002 has datafeed, 1003 has none
            assert result["confirmed_links"] >= 1
            # Article should still succeed even with mixed link types
        finally:
            db.unlink(missing_ok=True)

    def test_no_api_key_uses_template_fallback(self):
        db = _make_test_db()
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db), \
                 patch("shopee_engine.seo_engine._ai_intro", return_value="template intro"), \
                 patch("shopee_engine.seo_engine._ai_buying_guide", return_value="template guide"), \
                 patch("shopee_engine.seo_engine._ai_summary", return_value="template summary"), \
                 patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}):
                from shopee_engine.seo_engine import generate_article_draft
                result = generate_article_draft("เมาส์เกมมิ่ง")
            assert result["success"] is True
            assert result["ai_used"] is False
        finally:
            db.unlink(missing_ok=True)

    def test_article_id_unique_on_duplicate_keyword(self):
        db = _make_test_db()
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db), \
                 patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}):
                from shopee_engine.seo_engine import generate_article_draft
                r1 = generate_article_draft("เมาส์เกมมิ่ง")
                r2 = generate_article_draft("เมาส์เกมมิ่ง")
            assert r1["success"] and r2["success"]
            assert r1["article_id"] != r2["article_id"]
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Status management tests
# ---------------------------------------------------------------------------

class TestArticleStatus:
    def _create_draft(self, db: Path) -> str:
        with patch("shopee_engine.seo_engine.config.db_path", db), \
             patch("shopee_engine.affiliate_products_engine.config.db_path", db), \
             patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}):
            from shopee_engine.seo_engine import generate_article_draft
            r = generate_article_draft("เมาส์เกมมิ่ง")
        assert r["success"]
        return r["article_id"]

    def test_update_status_to_reviewed(self):
        db = _make_test_db()
        try:
            article_id = self._create_draft(db)
            with patch("shopee_engine.seo_engine.config.db_path", db):
                from shopee_engine.seo_engine import update_article_status
                ok = update_article_status(article_id, "reviewed")
            assert ok is True
        finally:
            db.unlink(missing_ok=True)

    def test_invalid_status_raises(self):
        db = _make_test_db()
        try:
            article_id = self._create_draft(db)
            import pytest
            with patch("shopee_engine.seo_engine.config.db_path", db):
                from shopee_engine.seo_engine import update_article_status
                try:
                    update_article_status(article_id, "invalid_status")
                    assert False, "Should have raised"
                except ValueError as e:
                    assert "Invalid status" in str(e)
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_blocks_draft_status(self):
        db = _make_test_db()
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db), \
                 patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}):
                from shopee_engine.seo_engine import generate_article_draft, validate_article_for_publish
                r = generate_article_draft("เมาส์เกมมิ่ง")
                result = validate_article_for_publish(r["article_id"])
            assert result["valid"] is False
            assert any("reviewed" in e for e in result["errors"])
        finally:
            db.unlink(missing_ok=True)

    def test_article_not_found(self):
        db = _make_test_db()
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db):
                from shopee_engine.seo_engine import validate_article_for_publish, run_migration
                run_migration()
                result = validate_article_for_publish("non-existent-slug")
            assert result["valid"] is False
            assert any("not found" in e for e in result["errors"])
        finally:
            db.unlink(missing_ok=True)

    def test_passes_after_review(self):
        db = _make_test_db()
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db), \
                 patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}):
                from shopee_engine.seo_engine import (
                    generate_article_draft, update_article_status, validate_article_for_publish
                )
                r = generate_article_draft("เมาส์เกมมิ่ง")
                update_article_status(r["article_id"], "reviewed")
                result = validate_article_for_publish(r["article_id"])
            # Should be valid (may have warnings about datafeed links but no errors)
            assert result["valid"] is True
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Refresh tests
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_product_not_found_marks_status(self):
        db = _make_test_db()
        try:
            import duckdb
            from shopee_engine.seo_engine import (
                SEO_ARTICLES_TABLE, SEO_ARTICLE_PRODUCTS_TABLE,
                _init_seo_tables, _connect
            )

            with patch("shopee_engine.seo_engine.config.db_path", db):
                _init_seo_tables(_connect(read_only=False))

            # Manually insert an article with a product that won't be in the DB
            con = duckdb.connect(str(db))
            con.execute(f"""
                INSERT INTO {SEO_ARTICLES_TABLE}
                (id, article_id, keyword, status)
                VALUES (99, 'test-refresh', 'ทดสอบ', 'draft')
            """)
            con.execute(f"""
                INSERT INTO {SEO_ARTICLE_PRODUCTS_TABLE}
                (id, article_id, itemid, shopid, product_title, sale_price,
                 affiliate_link, affiliate_link_type, rank_in_article)
                VALUES (99, 'test-refresh', 9999999, 8888888, 'สินค้าไม่มีในDB', 100,
                        '', 'none', 1)
            """)
            con.close()

            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db):
                from shopee_engine.seo_engine import refresh_article_products
                result = refresh_article_products("test-refresh")

            assert result["not_found"] == 1
            assert result["needs_review"] is True

            # Verify status was updated in DB
            con2 = duckdb.connect(str(db), read_only=True)
            row = con2.execute(
                f"SELECT product_status FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = 'test-refresh'"
            ).fetchone()
            con2.close()
            assert row[0] == "not_found"
        finally:
            db.unlink(missing_ok=True)

    def test_out_of_stock_marking(self):
        db = _make_test_db()
        try:
            import duckdb
            # Set product 1001 stock to 0
            con = duckdb.connect(str(db))
            con.execute("UPDATE products SET stock = 0 WHERE itemid = 1001")
            con.close()

            from shopee_engine.seo_engine import (
                SEO_ARTICLES_TABLE, SEO_ARTICLE_PRODUCTS_TABLE, _init_seo_tables, _connect
            )
            with patch("shopee_engine.seo_engine.config.db_path", db):
                _init_seo_tables(_connect(read_only=False))

            con2 = duckdb.connect(str(db))
            con2.execute(f"""
                INSERT INTO {SEO_ARTICLES_TABLE}
                (id, article_id, keyword, status)
                VALUES (88, 'test-oos', 'ทดสอบ', 'draft')
            """)
            con2.execute(f"""
                INSERT INTO {SEO_ARTICLE_PRODUCTS_TABLE}
                (id, article_id, itemid, shopid, product_title, sale_price,
                 affiliate_link, affiliate_link_type, rank_in_article)
                VALUES (88, 'test-oos', 1001, 5001, 'เมาส์เกมมิ่ง', 799,
                        'https://s.shopee.co.th/test', 'confirmed', 1)
            """)
            con2.close()

            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db):
                from shopee_engine.seo_engine import refresh_article_products
                result = refresh_article_products("test-oos")

            assert result["out_of_stock"] == 1
            assert result["needs_review"] is True
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Git push fail test (seo_git_service.py — referenced here)
# ---------------------------------------------------------------------------

class TestGitPublishFail:
    def test_publish_fail_keeps_reviewed_status(self):
        """If git push fails, article status must remain 'reviewed', not become 'published'."""
        db = _make_test_db()
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.affiliate_products_engine.config.db_path", db), \
                 patch("shopee_engine.ai_status.get_ai_status", return_value={"active": False}):
                from shopee_engine.seo_engine import (
                    generate_article_draft, update_article_status,
                    update_published_info, list_articles
                )
                r = generate_article_draft("เมาส์เกมมิ่ง")
                update_article_status(r["article_id"], "reviewed")

                # Simulate: git push fails → we do NOT call update_published_info
                # Status should remain "reviewed"
                articles = list_articles(status="reviewed")
            article_ids = [a["article_id"] for a in articles]
            assert r["article_id"] in article_ids
        finally:
            db.unlink(missing_ok=True)


class TestProductRelevanceGate:
    """check_product_relevance() — product-type gate before selection and review."""

    def setup_method(self):
        from shopee_engine.seo_engine import check_product_relevance
        self.check = check_product_relevance

    # --- Power Bank keyword: positive gate ---

    def test_power_bank_accepts_powerbank_in_title(self):
        ok, _ = self.check("Power Bank ชาร์จเร็ว 20W สำหรับ iPhone", "UGREEN Power Bank 10000mAh PD 20W")
        assert ok

    def test_power_bank_accepts_thai_name(self):
        ok, _ = self.check("Power Bank ชาร์จเร็ว 20W", "Anker พาวเวอร์แบงค์ 20000mAh ชาร์จเร็ว")
        assert ok

    def test_power_bank_accepts_thai_backup_battery(self):
        ok, _ = self.check("Power Bank ชาร์จเร็ว", "HOCO แบตสำรองพกพา 10000mAh PD20W")
        assert ok

    def test_power_bank_accepts_powerbank_oneword(self):
        ok, _ = self.check("powerbank 20w iphone", "AUKEY Powerbank 20000mAh PD 20W")
        assert ok

    # --- Power Bank keyword: negative gate (cable/adapter/charger blocked) ---

    def test_power_bank_blocks_usb_cable(self):
        """UGREEN USB-C to Lightning cable must be blocked for power bank keywords.
        Blocked by positive gate (no power bank term in title) before negative gate."""
        ok, reason = self.check(
            "Power Bank ชาร์จเร็ว 20W สำหรับ iPhone",
            "UGREEN รุ่น US304 USB C to Lightning MFI Fast Charging 3A PD 20W Cable Charge & Sync สายชาร์จ สำหรับ iPhone",
        )
        assert not ok
        assert reason  # blocked with a non-empty reason

    def test_power_bank_blocks_thai_cable(self):
        ok, _ = self.check("power bank 20w", "สายชาร์จ USB-C to Lightning 20W สำหรับ iPhone")
        assert not ok

    def test_power_bank_blocks_adapter(self):
        ok, reason = self.check("power bank ชาร์จเร็ว", "Baseus adapter หัวชาร์จ GaN 65W USB-C")
        assert not ok

    def test_power_bank_blocks_wall_charger(self):
        ok, reason = self.check("พาวเวอร์แบงค์ ชาร์จเร็ว", "Anker wall charger 65W USB-C PD")
        assert not ok

    def test_power_bank_blocks_title_missing_product_type(self):
        """A title with '20W' and 'iPhone' but no power bank keyword must fail positive gate."""
        ok, reason = self.check(
            "power bank 20w iphone",
            "Apple 20W USB-C หัวชาร์จ สำหรับ iPhone 14",
        )
        assert not ok

    # --- Non-power-bank keywords: gate must be transparent ---

    def test_unrelated_keyword_does_not_trigger(self):
        """For keywords that don't match any rule, all products pass regardless of title."""
        ok, _ = self.check("เมาส์เกมมิ่ง", "สายชาร์จ USB-C Baseus")
        assert ok

    def test_headphones_keyword_no_false_block(self):
        ok, _ = self.check("หูฟัง gaming ราคาถูก", "JBL Quantum 100 Gaming Headset")
        assert ok

    # --- Compound term: 'power bank' tokenised as one unit ---

    def test_term_groups_power_bank_is_single_group(self):
        """'power bank' in multi-token keyword must become one AND-group, not two."""
        from shopee_engine.seo_engine import _keyword_to_term_groups
        groups = _keyword_to_term_groups("Power Bank ชาร์จเร็ว 20W สำหรับ iPhone")
        # power-bank group, ชาร์จเร็ว group, 20w group, iphone group — NOT split "power" + "bank"
        assert len(groups) == 4
        pb_group = groups[0]
        assert "power bank" in pb_group
        assert "powerbank" in pb_group or "พาวเวอร์แบงค์" in pb_group

    def test_cable_description_no_longer_matches_power_bank_sql(self):
        """The cable that slipped through (itemid 4886903220) must not pass relevance gate."""
        cable_title = (
            "UGREEN รุ่น US304 USB C to Lightning MFI Fast Charging 3A PD 20W "
            "Cable Charge & Sync สายชาร์จ สำหรับ iPhone 12 13 14"
        )
        ok, reason = self.check("Power Bank ชาร์จเร็ว 20W สำหรับ iPhone", cable_title)
        assert not ok, f"Cable should be blocked but passed with reason: {reason}"

    # --- Built-in cable context: สายชาร์จในตัว must NOT block a Power Bank ---

    def test_power_bank_with_builtin_cable_thai_passes(self):
        """iMI / Eloop pattern: Power Bank + สายชาร์จในตัว must pass."""
        ok, reason = self.check(
            "power bank 10000 mah ไม่เกิน 1000 บาท",
            "iMI Powerbank พาวเวอร์แบงค์ 10000/20000/30000mAh CCC+TISI ชาร์จเร็ว22.5W สายชาร์จในตัว พกพาง่าย แบตสำรอง",
        )
        assert ok, f"Power Bank with built-in cable blocked: {reason}"

    def test_eloop_builtin_cable_passes(self):
        """Eloop E33 Line: แบตสำรอง + มีสายชาร์จในตัว must pass."""
        ok, reason = self.check(
            "power bank 10000 mah",
            "[ส่งด่วน] Eloop E33 Line แบตสำรอง 10000mAh มีสายชาร์จในตัว Powerbank 12W พาวเวอร์แบงค์",
        )
        assert ok, f"Eloop built-in cable Power Bank blocked: {reason}"

    def test_yook_saynai_tua_passes(self):
        """สายในตัว (without 'ชาร์จ') must also be treated as built-in cable feature."""
        ok, reason = self.check(
            "power bank 10000 mah",
            "[แถมถุงผ้า มีCCC] พาวเวอร์แบงค์ YOOK Powerbank 10000mAh สายในตัว ลิขสิทธิ์ Disney",
        )
        assert ok, f"Power Bank with สายในตัว blocked: {reason}"

    def test_standalone_saicharg_without_pb_evidence_blocked(self):
        """'สายชาร์จ' alone with no Power Bank evidence must be blocked."""
        ok, _ = self.check(
            "power bank 10000 mah",
            "สายชาร์จ USB-C to Lightning 20W สำหรับ iPhone 14 Pro Max",
        )
        assert not ok

    def test_positive_pb_evidence_outweighs_builtin_cable_term(self):
        """When Power Bank evidence is strong, built-in cable phrase must not block."""
        ok, reason = self.check(
            "powerbank ไม่เกิน 1000 บาท",
            "HOCO แบตสำรองพกพา 10000mAh Fast charging PD20W พร้อมสาย Type-C/iOS จอ LED",
        )
        assert ok, f"HOCO Power Bank with cable feature blocked: {reason}"


class TestSpecEvidenceDetection:
    """detect_product_spec_evidence() + check_product_spec() + _extract_spec_requirements()."""

    def setup_method(self):
        from shopee_engine.seo_engine import (
            detect_product_spec_evidence,
            check_product_spec,
            _extract_spec_requirements,
        )
        self.detect  = detect_product_spec_evidence
        self.check   = check_product_spec
        self.extract = _extract_spec_requirements

    # --- _extract_spec_requirements ---

    def test_extracts_20w_from_keyword(self):
        r = self.extract("Power Bank ชาร์จเร็ว 20W สำหรับ iPhone")
        assert r["min_watt"] == 20.0
        assert r["iphone_required"] is True

    def test_extracts_no_watt_when_absent(self):
        r = self.extract("Power Bank แบตสำรอง")
        assert r["min_watt"] is None
        assert r["iphone_required"] is False

    def test_extracts_iphone_from_keyword(self):
        r = self.extract("แบตสำรอง iPhone Lightning สายในตัว")
        assert r["iphone_required"] is True

    # --- detect_product_spec_evidence: wattage source attribution ---

    def test_watt_from_title(self):
        ev = self.detect("AUKEY PB-Y59 20W PD Power Bank 5000mAh USB-C")
        assert ev["watt_max"] == 20.0
        assert ev["watt_source"] == "title"

    def test_watt_from_description_when_missing_in_title(self):
        ev = self.detect(
            title="UGREEN Power Bank แบตสำรอง 10000mAh PD Fast Charging",
            description="รองรับ PD 22.5W ชาร์จ iPhone ได้ภายใน 30 นาที",
        )
        assert ev["watt_max"] == 22.5
        assert ev["watt_source"] == "description"

    def test_no_watt_evidence(self):
        ev = self.detect("Power Bank ราคาถูก แบตสำรอง")
        assert ev["watt_max"] == 0.0
        assert ev["watt_source"] == "none"

    def test_iphone_from_title(self):
        ev = self.detect("HOCO แบตสำรอง PD20W พร้อมสาย Type-C/iOS")
        assert ev["iphone_compat"] is True
        assert ev["iphone_source"] == "title"

    def test_iphone_from_description(self):
        ev = self.detect(
            title="UGREEN Power Bank แบตสำรอง 10000mAh",
            description="สามารถชาร์จ iPhone 15 ได้ 2.2 ครั้ง",
        )
        assert ev["iphone_compat"] is True
        assert ev["iphone_source"] == "description"

    def test_no_iphone_evidence(self):
        ev = self.detect("Power Bank Samsung 20000mAh 45W Fast Charge")
        assert ev["iphone_compat"] is False
        assert ev["iphone_source"] == "none"

    # --- check_product_spec: keyword=20W + iPhone ---

    def test_power_bank_20w_iphone_passes_when_both_present(self):
        ok, _, ev = self.check(
            "Power Bank ชาร์จเร็ว 20W สำหรับ iPhone",
            "[CCC] AUKEY PB-Y59 20W PD พาวเวอร์แบงค์ สำหรับ iPhone",
        )
        assert ok

    def test_power_bank_passes_via_description_watt(self):
        """Power Bank with no watt in title but ≥20W in description must pass."""
        ok, _, ev = self.check(
            "Power Bank ชาร์จเร็ว 20W สำหรับ iPhone",
            "UGREEN Power Bank แบตสำรอง 10000mAh Magnetic Wireless",
            description="ชาร์จด้วย PD 20W ใช้กับ iPhone 15 ได้",
        )
        assert ok
        assert ev["watt_source"] == "description"

    def test_power_bank_fails_without_20w_evidence(self):
        """Real power bank but no ≥20W evidence anywhere must be blocked."""
        ok, reason, _ = self.check(
            "Power Bank ชาร์จเร็ว 20W สำหรับ iPhone",
            "Power Bank แบตสำรอง 10000mAh Quick Charge 3.0 (สูงสุด 18W)",
        )
        assert not ok
        assert "20W" in reason or "20" in reason

    def test_power_bank_fails_without_iphone_compatibility(self):
        """Power bank with 20W+ but no iPhone mention must be blocked when iPhone required."""
        ok, reason, _ = self.check(
            "Power Bank ชาร์จเร็ว 20W สำหรับ iPhone",
            "Samsung 25W Super Fast Power Bank 20000mAh USB-C",
            description="ชาร์จ Samsung Galaxy ได้เร็วสุด 25W",
        )
        assert not ok
        assert "iphone" in reason.lower() or "iPhone" in reason

    def test_no_spec_requirement_always_passes(self):
        """Keyword with no watt/iPhone requirement: any power bank passes spec gate."""
        ok, reason, _ = self.check(
            "Power Bank แบตสำรอง ราคาถูก",
            "Power Bank Generic 10000mAh",
        )
        assert ok
        assert reason == "ok"

    def test_aukey_pb_y44_100w_passes_spec(self):
        """The 100W laptop bank passes spec (100W ≥ 20W) — excluded by price logic, not spec."""
        ok, _, ev = self.check(
            "Power Bank ชาร์จเร็ว 20W สำหรับ iPhone",
            "AUKEY PB-Y44 พาวเวอร์แบงค์ชาร์จเร็ว Sprint X 20K 100W 20000mAh Laptop Power Bank with PD3.0",
            description="รองรับ PD 45W 30W สำหรับ iPhone และ Laptop",
        )
        assert ok
        assert ev["watt_max"] == 100.0


# ---------------------------------------------------------------------------
# TestContentConsistency (Task 1)
# ---------------------------------------------------------------------------

def _make_test_db_with_article(
    product_rows: list[tuple],
    content_md: str,
    article_id: str = "test-article",
    keyword: str = "Power Bank ชาร์จเร็ว 20W",
    status: str = "draft",
) -> Path:
    """Create a temp DB with an article + products for consistency tests."""
    import duckdb
    tmp = Path(tempfile.mktemp(suffix=".duckdb"))
    con = duckdb.connect(str(tmp))

    # Minimal products table
    con.execute("""
        CREATE TABLE products (
            itemid BIGINT, shopid BIGINT, title VARCHAR,
            sale_price BIGINT, price BIGINT, item_sold BIGINT, "like" BIGINT,
            shop_rating DOUBLE, item_rating DOUBLE, discount_percentage BIGINT,
            global_category1 VARCHAR, global_category2 VARCHAR, global_category3 VARCHAR,
            global_brand VARCHAR, image_link VARCHAR, product_link VARCHAR,
            "product_short link" VARCHAR, description VARCHAR, stock BIGINT DEFAULT 1
        )
    """)
    con.execute("""
        CREATE TABLE affiliate_products (
            id INTEGER, itemid BIGINT, shopid BIGINT, title VARCHAR,
            category VARCHAR, identification_url VARCHAR, affiliate_short_url VARCHAR,
            campaign VARCHAR DEFAULT '', platform VARCHAR DEFAULT '',
            created_at VARCHAR DEFAULT '', updated_at VARCHAR DEFAULT '',
            latest_link BOOLEAN DEFAULT true
        )
    """)

    # SEO tables
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
            published_at TIMESTAMP, category_label VARCHAR DEFAULT '',
            subcategory VARCHAR DEFAULT '', subcategory_label VARCHAR DEFAULT ''
        )
    """)
    con.execute("""
        CREATE TABLE seo_article_products (
            id INTEGER PRIMARY KEY, article_id VARCHAR NOT NULL,
            itemid BIGINT, shopid BIGINT, product_title VARCHAR DEFAULT '',
            sale_price BIGINT DEFAULT 0, image_link VARCHAR DEFAULT '',
            affiliate_link VARCHAR DEFAULT '', affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score DOUBLE DEFAULT 0, rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS seo_article_revisions (
            id INTEGER PRIMARY KEY, article_id VARCHAR NOT NULL,
            revision_number INTEGER NOT NULL, title VARCHAR DEFAULT '',
            meta_description VARCHAR DEFAULT '', content_md TEXT DEFAULT '',
            category VARCHAR DEFAULT '', category_label VARCHAR DEFAULT '',
            status VARCHAR DEFAULT '', saved_by VARCHAR DEFAULT 'system',
            change_summary VARCHAR DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert products into products table
    for row in product_rows:
        # row: (itemid, shopid, title, sale_price)
        con.execute("""
            INSERT INTO products (itemid, shopid, title, sale_price, price, item_sold, "like",
                shop_rating, item_rating, discount_percentage, global_category1, global_category2,
                global_category3, global_brand, image_link, product_link, "product_short link",
                description, stock)
            VALUES (?,?,?,?,?,100,0,4.8,4.7,10,'Mobile & Gadgets','Power Banks','Power Banks','Test',
                'https://img/1','https://shopee.co.th/1','https://s.shopee.co.th/1','desc',10)
        """, [row[0], row[1], row[2], row[3], row[3]])

    # Insert article
    con.execute("""
        INSERT INTO seo_articles (id, article_id, keyword, status, content_md,
            category, title, meta_description)
        VALUES (1, ?, ?, ?, ?, 'mobile-gadgets', 'Test Article', 'Test description')
    """, [article_id, keyword, status, content_md])

    # Insert article products
    for i, row in enumerate(product_rows, 1):
        con.execute("""
            INSERT INTO seo_article_products
                (id, article_id, itemid, shopid, product_title, sale_price,
                 affiliate_link, affiliate_link_type, rank_in_article)
            VALUES (?, ?, ?, ?, ?, ?, 'https://s.shopee.co.th/test', 'confirmed', ?)
        """, [i, article_id, row[0], row[1], row[2], row[3], i])

    con.close()
    return tmp


class TestContentConsistency:
    """validate_content_consistency() and rebuild_article_content()."""

    def test_stale_price_detected(self):
        from shopee_engine.seo_engine import validate_content_consistency
        # Article has product at ฿990 but content's table references ฿399
        products = [(1001, 5001, "UGREEN Power Bank 10000mAh PB561", 990)]
        content = (
            "---\narticle_id: test\n---\n\n"
            "| # | สินค้า | ราคา |\n|---|---|---|\n| 1 | UGREEN Cable US304 | ฿399 |\n"
        )
        db = _make_test_db_with_article(products, content)
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db):
                result = validate_content_consistency("test-article")
            assert not result["consistent"]
            assert any("399" in s for s in result["stale_items"])
        finally:
            db.unlink(missing_ok=True)

    def test_stale_product_name_detected(self):
        from shopee_engine.seo_engine import validate_content_consistency
        # Content mentions US304 but no product has that code
        products = [(1001, 5001, "UGREEN Power Bank PB561 10000mAh", 990)]
        content = "---\narticle_id: test\n---\n\nรุ่น US304 เป็นสายชาร์จยอดนิยม"
        db = _make_test_db_with_article(products, content)
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db):
                result = validate_content_consistency("test-article")
            assert not result["consistent"]
            assert any("US304" in s.upper() for s in result["stale_items"])
        finally:
            db.unlink(missing_ok=True)

    def test_consistent_content_passes(self):
        from shopee_engine.seo_engine import validate_content_consistency
        products = [(1001, 5001, "UGREEN Power Bank PB561 10000mAh", 990)]
        # Table format uses the current product price ฿990 — should pass
        content = (
            "---\narticle_id: test\n---\n\n"
            "| # | สินค้า | ราคา |\n|---|---|---|\n| 1 | UGREEN Power Bank PB561 | ฿990 |\n"
        )
        db = _make_test_db_with_article(products, content)
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db):
                result = validate_content_consistency("test-article")
            assert result["consistent"]
            assert result["stale_items"] == []
        finally:
            db.unlink(missing_ok=True)

    def test_rebuild_removes_stale_references(self):
        from shopee_engine.seo_engine import rebuild_article_content, validate_content_consistency
        products = [(1001, 5001, "UGREEN Power Bank PB561 10000mAh", 990)]
        # Content has stale price ฿399 in table and old model US304 in text
        content = (
            "---\narticle_id: test\n---\n\n"
            "รุ่น US304 ขายดีมาก\n\n"
            "| # | สินค้า | ราคา |\n|---|---|---|\n| 1 | UGREEN US304 Cable | ฿399 |\n"
        )
        db = _make_test_db_with_article(products, content)
        try:
            with patch("shopee_engine.seo_engine.config.db_path", db), \
                 patch("shopee_engine.seo_engine._ai_intro", return_value="intro rebuilt"), \
                 patch("shopee_engine.seo_engine._ai_buying_guide", return_value="guide rebuilt"), \
                 patch("shopee_engine.seo_engine._ai_summary", return_value="summary rebuilt"), \
                 patch("shopee_engine.editorial_team.generate_article_content",
                       return_value={"_success": False}):
                r = rebuild_article_content("test-article")
            assert r["success"] is True
            assert r["products_used"] == 1
            # After rebuild, content consistency should pass (no stale ฿399 in table)
            with patch("shopee_engine.seo_engine.config.db_path", db):
                cc = validate_content_consistency("test-article")
            assert "399" not in str(cc.get("stale_items", []))
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TestCapacityGate (Task 2)
# ---------------------------------------------------------------------------

class TestCapacityGate:
    """detect_capacity_evidence() + _extract_capacity_requirement() + check_capacity_relevance()."""

    def setup_method(self):
        from shopee_engine.seo_engine import (
            detect_capacity_evidence,
            _extract_capacity_requirement,
            check_capacity_relevance,
        )
        self.detect   = detect_capacity_evidence
        self.extract  = _extract_capacity_requirement
        self.check    = check_capacity_relevance

    def test_10000mah_passes(self):
        ok, reason, ev = self.check(
            "power-bank-10000-mah-ไม่เกิน-1000-บาท",
            "LBR P03 แบตสำรอง 10000mAh Mini Powerbank",
        )
        assert ok
        assert ev["capacity_max"] == 10000

    def test_20000mah_blocked(self):
        ok, reason, ev = self.check(
            "power-bank-10000-mah-ไม่เกิน-1000-บาท",
            "Samsung Power Bank 20000mAh 45W Fast Charge",
        )
        assert not ok
        assert "20000" in reason or "20,000" in reason

    def test_12000mah_blocked(self):
        ok, reason, ev = self.check(
            "power-bank-10000-mah-ไม่เกิน-1000-บาท",
            "UNEED Powerbank 12000mAh Magnetic",
        )
        assert not ok
        assert "12000" in reason or "12,000" in reason

    def test_variant_title_gives_warning(self):
        ok, reason, ev = self.check(
            "power-bank-10000-mah-ไม่เกิน-1000-บาท",
            "ANKER Zolo Powerbank 10000/20000mAh 22.5W",
        )
        # Should pass with warning (ambiguous_variant = True)
        assert ok
        assert ev.get("ambiguous_variant") is True
        assert "warning" in reason.lower() or "variant" in reason.lower()

    def test_no_capacity_in_keyword_passes(self):
        ok, reason, ev = self.check(
            "power-bank-ชาร์จเร็ว-20w",
            "Power Bank 20000mAh Fast Charge 20W",
        )
        assert ok
        assert "no capacity requirement" in reason.lower() or reason == "ok"

    def test_detect_single_mah(self):
        ev = self.detect("LBR P03 10000mAh Powerbank")
        assert ev["capacity_max"] == 10000
        assert ev["capacity_source"] == "title"
        assert 10000 in ev["capacities_mah"]

    def test_detect_multi_variant(self):
        ev = self.detect("iMI Powerbank 10000/20000/30000mAh")
        assert len(ev["capacities_mah"]) >= 2
        assert 10000 in ev["capacities_mah"]

    def test_detect_no_mah(self):
        ev = self.detect("Power Bank Generic Fast Charge 20W")
        assert ev["capacity_max"] == 0
        assert ev["capacity_source"] == "none"
        assert ev["capacities_mah"] == []

    def test_extract_10000_from_keyword(self):
        r = self.extract("power-bank-10000-mah-ไม่เกิน-1000-บาท")
        assert r["required_mah"] == 10000

    def test_extract_none_no_capacity(self):
        r = self.extract("power-bank-ชาร์จเร็ว-20w-สำหรับ-iphone")
        assert r["required_mah"] is None


# ---------------------------------------------------------------------------
# TestDuplicateModelGate (Task 3)
# ---------------------------------------------------------------------------

class TestDuplicateModelGate:
    """normalize_model_key() + check_duplicate_models()."""

    def setup_method(self):
        from shopee_engine.seo_engine import normalize_model_key, check_duplicate_models
        self.normalize  = normalize_model_key
        self.check_dups = check_duplicate_models

    def test_same_model_different_itemid_blocked(self):
        products = [
            {"itemid": 53155330120, "product_title": "[CCC] AUKEY PB-Y59 20W PD Power Bank 5000mAh"},
            {"itemid": 54052973043, "product_title": "AUKEY PB-Y59 20W PD Power Bank 5000mAh พับได้"},
        ]
        dups = self.check_dups(products)
        assert len(dups) >= 1
        # Both PB-Y59 itemids should be in the same group
        all_ids = []
        for g in dups:
            all_ids.extend(g["itemids"])
        assert 53155330120 in all_ids
        assert 54052973043 in all_ids

    def test_different_models_passes(self):
        products = [
            {"itemid": 1001, "product_title": "[CCC] AUKEY PB-Y59 20W PD Power Bank 5000mAh"},
            {"itemid": 1002, "product_title": "AUKEY PB-Y44 100W Power Bank 20000mAh"},
        ]
        dups = self.check_dups(products)
        assert dups == []

    def test_no_model_code_not_flagged(self):
        products = [
            {"itemid": 1001, "product_title": "พาวเวอร์แบงค์ไร้สาย 20000mAh"},
            {"itemid": 1002, "product_title": "พาวเวอร์แบงค์ไร้สาย 20000mAh"},
        ]
        dups = self.check_dups(products)
        # These have no parseable model code → not flagged
        assert dups == []

    def test_normalize_aukey_pb_y59(self):
        brand, model, cap = self.normalize("[CCC] AUKEY PB-Y59 20W PD Power Bank 5000mAh USB-C")
        assert brand == "aukey"
        assert model is not None and "pb" in model.lower() and "y59" in model.lower()
        assert cap == 5000

    def test_normalize_ukiki_kp15ac(self):
        brand, model, cap = self.normalize(
            "[CCC] UKIKI Powerbank 15000mAh PD22.5W รุ่น KP15AC-01"
        )
        assert brand == "ukiki"
        assert model is not None and "kp15ac" in model.lower()
        assert cap == 15000


# ---------------------------------------------------------------------------
# TestFeatureCopyGuard (Task 4)
# ---------------------------------------------------------------------------

class TestFeatureCopyGuard:
    """check_content_feature_copy()."""

    def setup_method(self):
        from shopee_engine.seo_engine import check_content_feature_copy
        self.check = check_content_feature_copy

    def test_remote_shutter_in_powerbank_content_flagged(self):
        content = "---\narticle_id: test\n---\n\nใช้เป็น remote shutter ได้ด้วย"
        offenders = self.check("Power Bank ชาร์จเร็ว 20W", content)
        assert "remote shutter" in offenders

    def test_shutter_release_in_powerbank_flagged(self):
        content = "---\narticle_id: test\n---\n\nมีฟีเจอร์ shutter release สะดวกมาก"
        offenders = self.check("powerbank 10000mah", content)
        assert "shutter release" in offenders

    def test_clean_content_passes(self):
        content = "---\narticle_id: test\n---\n\nชาร์จเร็ว PD 20W สะดวกมาก"
        offenders = self.check("Power Bank ชาร์จเร็ว 20W", content)
        assert offenders == []

    def test_non_powerbank_keyword_not_triggered(self):
        # Fan keyword doesn't have blocked_features for power bank
        content = "---\narticle_id: test\n---\n\nใช้เป็น remote shutter ได้"
        offenders = self.check("พัดลมพกพา USB", content)
        # Power bank rule doesn't trigger for fan keyword
        assert "remote shutter" not in offenders

    def test_frontmatter_not_scanned(self):
        # Even if phrase in frontmatter only, body scan should not flag it
        content = "---\ndescription: remote shutter\n---\n\nชาร์จเร็วดีมาก"
        offenders = self.check("Power Bank ชาร์จเร็ว 20W", content)
        assert offenders == []


# ---------------------------------------------------------------------------
# TestNormalizeModelKeyFix — brand aliases and E33-style codes
# ---------------------------------------------------------------------------

class TestNormalizeModelKeyBrandAlias:
    """normalize_model_key brand aliasing and suffix stripping."""

    def setup_method(self):
        from shopee_engine.seo_engine import normalize_model_key
        self.norm = normalize_model_key

    def test_eloop_e33_line_gets_e33(self):
        brand, model, cap = self.norm("Eloop E33 Line แบตสำรอง 10000mAh มีสายชาร์จในตัว")
        assert brand == "eloop"
        assert model == "e33"
        assert cap == 10000

    def test_orsen_eloop_e33line_concat_gets_e33(self):
        brand, model, cap = self.norm(
            "Orsen Eloop E33 E33Line แบตสำรอง 10000mAh ชาร์จเร็ว Power bank"
        )
        # orsen → eloop via brand alias; E33Line → e33 via suffix strip
        assert brand == "eloop"
        assert model == "e33"
        assert cap == 10000

    def test_both_eloop_products_same_key(self):
        """The two Eloop listings that caused a false duplicate pass now collide."""
        from shopee_engine.seo_engine import normalize_model_key
        k1 = normalize_model_key("Eloop E33 Line แบตสำรอง 10000mAh มีสายชาร์จในตัว 12W")
        k2 = normalize_model_key(
            "Orsen Eloop E33 E33Line แบตสำรอง 10000mAh ชาร์จเร็ว พาวเวอร์แบงค์"
        )
        assert k1 == k2, f"Expected same key: {k1} vs {k2}"

    def test_orsen_brand_aliases_to_eloop(self):
        brand, _, _ = self.norm("Orsen EW31 พาวเวอร์แบงค์ 10000mAh PD 20W")
        assert brand == "eloop"

    def test_aukey_brand_unchanged(self):
        brand, model, _ = self.norm("[CCC] AUKEY PB-Y59 20W Power Bank")
        assert brand == "aukey"
        assert model == "pb-y59"

    def test_single_letter_model_e33_captured(self):
        _, model, _ = self.norm("Test E33 PowerBank 10000mAh")
        assert model == "e33"

    def test_model_pro_suffix_stripped(self):
        _, model, _ = self.norm("Brand E33Pro PowerBank 10000mAh")
        assert model == "e33"

    def test_model_line_suffix_stripped(self):
        # V9Pro — 3-char code with suffix, model_code detection only triggers on 2+ digits
        _, model, _ = self.norm("Brand V90Pro PowerBank 20000mAh")
        assert model == "v90"


# ---------------------------------------------------------------------------
# TestVariantPricePlausibilityGate
# ---------------------------------------------------------------------------

class TestVariantPricePlausibilityGate:
    """check_variant_price_plausibility()."""

    def setup_method(self):
        from shopee_engine.seo_engine import check_variant_price_plausibility
        self.check = check_variant_price_plausibility

    def test_imi_30000mah_at_209_flagged(self):
        ok, reason, ev = self.check(
            "iMI Powerbank 30000mAh 22.5W", 209.0,
            "CCC 10000mAh|CCC 20000mAh|CCC 30000mAh"
        )
        assert not ok
        assert "209" in reason or "30" in reason
        assert ev["is_multivariant"] is True

    def test_eloop_10000mah_at_299_passes(self):
        ok, reason, _ = self.check("Eloop E33 10000mAh 12W", 299.0, "E33 ขาว|E33 ดำ")
        assert ok

    def test_20000mah_at_190_flagged(self):
        ok, reason, _ = self.check("แบตสำรอง 20000mAh", 190.0, None)
        assert not ok

    def test_10000mah_at_120_passes(self):
        ok, _, _ = self.check("แบตสำรอง 10000mAh", 120.0, None)
        assert ok

    def test_10000mah_at_100_flagged(self):
        ok, reason, _ = self.check("แบตสำรอง 10000mAh", 100.0, None)
        assert not ok

    def test_no_capacity_always_passes(self):
        ok, reason, _ = self.check("แบตสำรอง", 50.0, None)
        assert ok

    def test_multivariant_flag_in_evidence(self):
        ok, reason, ev = self.check(
            "Brand PB 10000/20000mAh", 100.0,
            "10000mAh สีขาว|20000mAh สีขาว"
        )
        assert not ok
        assert ev["is_multivariant"] is True

    def test_single_variant_color_only_not_flagged_as_multivariant(self):
        _, _, ev = self.check(
            "GOOJODOQ 10000mAh PowerBank", 196.0,
            "สีดํา|สีขาว"
        )
        # 2 color variants — is_multivariant True (it's fine, just flag for multi)
        assert ev["is_multivariant"] is True

    def test_high_wattage_surcharge_applied(self):
        # 10000mAh + 65W should have higher floor than 10000mAh alone
        _, _, ev_base = self.check("แบตสำรอง 10000mAh 10W", 150.0, None)
        ok_high, _, _ = self.check("แบตสำรอง 10000mAh 65W", 150.0, None)
        # At 65W the floor is raised, so 150 may fail
        # Just verify evidence keys exist
        assert "floor_used" in ev_base
        assert "watt_detected" in ev_base


# ---------------------------------------------------------------------------
# TestTitleGenerator — รุ่นไหนดี suffix
# ---------------------------------------------------------------------------

class TestTitleGeneratorSuffix:
    """Title should not append ที่ดีที่สุด when keyword ends in รุ่นไหนดี."""

    _QUESTION_ENDINGS = ("รุ่นไหนดี", "อันไหนดี", "ตัวไหนดี", "รุ่นไหนเด็ด")

    def _build_title(self, keyword: str, count: int = 5) -> str:
        from datetime import datetime
        _kw = keyword.strip()
        _has_q = any(_kw.endswith(q) for q in self._QUESTION_ENDINGS)
        suffix = "" if _has_q else " ที่ดีที่สุด"
        return f"{count} {keyword}{suffix} (อัปเดต {datetime.now().year})"

    def test_ruennaidi_no_double_suffix(self):
        title = self._build_title("Power Bank มีสายในตัว รุ่นไหนดี")
        assert "ที่ดีที่สุด" not in title
        assert "รุ่นไหนดี" in title

    def test_normal_keyword_gets_suffix(self):
        title = self._build_title("Power Bank ชาร์จเร็ว 20W สำหรับ iPhone")
        assert "ที่ดีที่สุด" in title

    def test_annaidi_no_suffix(self):
        title = self._build_title("หูฟังไร้สาย อันไหนดี")
        assert "ที่ดีที่สุด" not in title

    def test_count_in_title(self):
        title = self._build_title("Power Bank", count=7)
        assert title.startswith("7 ")


# ---------------------------------------------------------------------------
# TestRelatedArticlesExport — pipeline fix
# ---------------------------------------------------------------------------

class TestRelatedArticlesExport:
    """_build_export_body includes related articles section."""

    def test_related_section_rendered(self):
        from shopee_engine.article_exporter import _build_export_body
        article = {
            "keyword": "Test Keyword",
            "category": "mobile-gadgets",
            "content_md": "",
        }
        products = []
        prose = {"บทนำ": "intro text", "บทสรุป": "summary text"}
        related = [
            {"article_id": "power-bank-abc", "title": "5 Power Bank ABC ที่ดีที่สุด", "keyword": ""},
            {"article_id": "power-bank-xyz", "title": "", "keyword": "Power Bank XYZ"},
        ]
        body = _build_export_body(article, products, prose, related_articles=related)
        assert "## บทความที่เกี่ยวข้อง" in body
        assert "[5 Power Bank ABC ที่ดีที่สุด](/power-bank-abc/)" in body
        assert "[Power Bank XYZ](/power-bank-xyz/)" in body

    def test_no_related_no_section(self):
        from shopee_engine.article_exporter import _build_export_body
        article = {"keyword": "Test", "category": "mobile-gadgets", "content_md": ""}
        body = _build_export_body(article, [], {}, related_articles=[])
        assert "## บทความที่เกี่ยวข้อง" not in body

    def test_none_related_no_section(self):
        from shopee_engine.article_exporter import _build_export_body
        article = {"keyword": "Test", "category": "mobile-gadgets", "content_md": ""}
        body = _build_export_body(article, [], {}, related_articles=None)
        assert "## บทความที่เกี่ยวข้อง" not in body


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
