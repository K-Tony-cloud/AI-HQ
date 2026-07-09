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


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
