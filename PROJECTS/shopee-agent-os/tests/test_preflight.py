"""Tests for shopee_engine/preflight.py and shopee_engine/title_cleaner.py"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# DB helpers (reuse pattern from test_seo_engine.py)
# ---------------------------------------------------------------------------

def _make_test_db(
    article_id: str = "test-article",
    keyword: str = "power bank",
    category: str = "mobile-gadgets",
    title: str = "5 Power Bank ดีที่สุด",
    products: list[dict] | None = None,
) -> Path:
    """Create a temp DuckDB with seo tables and minimal products."""
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

    # Default product set: valid power banks
    if products is None:
        products = [
            {
                "itemid": 2001, "shopid": 6001,
                "title": "Eloop E33 Power Bank 10000mAh 22.5W",
                "sale_price": 399, "aff_link": "https://s.shopee.co.th/TestPB001",
            },
            {
                "itemid": 2002, "shopid": 6002,
                "title": "Anker 521 Power Bank 10000mAh 20W",
                "sale_price": 549, "aff_link": "https://s.shopee.co.th/TestPB002",
            },
        ]

    for p in products:
        con.execute("""
            INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            p["itemid"], p["shopid"], p["title"],
            p["sale_price"], p["sale_price"] + 100,
            500, 50, 4.8, 4.7, 10,
            "Mobile & Gadgets", "Batteries & Charging", "Power Bank",
            "TestBrand",
            "https://cf.shopee.co.th/file/img1",
            f"https://shopee.co.th/product/{p['shopid']}/{p['itemid']}",
            f"https://shope.ee/test{p['itemid']}",
            f"Power Bank ดีมาก {p['title']}", 10,
        ])
        con.execute("""
            INSERT INTO affiliate_products
            (id, itemid, shopid, title, category, identification_url, affiliate_short_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            p["itemid"], p["itemid"], p["shopid"], p["title"],
            "Power Bank",
            f"https://shopee.co.th/product/{p['shopid']}/{p['itemid']}",
            p["aff_link"],
        ])

    # Create seo_articles and seo_article_products
    con.execute("""
        CREATE TABLE seo_articles (
            id                  INTEGER PRIMARY KEY,
            article_id          VARCHAR UNIQUE NOT NULL,
            keyword             VARCHAR NOT NULL,
            category            VARCHAR DEFAULT '',
            title               VARCHAR DEFAULT '',
            meta_description    VARCHAR DEFAULT '',
            content_md          TEXT DEFAULT '',
            status              VARCHAR DEFAULT 'draft',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_product_sync   TIMESTAMP,
            affiliate_disclosure BOOLEAN DEFAULT true,
            published_path      VARCHAR DEFAULT '',
            git_commit_hash     VARCHAR DEFAULT '',
            reviewed_at         TIMESTAMP,
            review_note         VARCHAR DEFAULT '',
            published_at        TIMESTAMP,
            category_label      VARCHAR DEFAULT '',
            subcategory         VARCHAR DEFAULT '',
            subcategory_label   VARCHAR DEFAULT '',
            preflight_status    VARCHAR DEFAULT 'pending',
            preflight_passed_at TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE seo_article_products (
            id                  INTEGER PRIMARY KEY,
            article_id          VARCHAR NOT NULL,
            itemid              BIGINT,
            shopid              BIGINT,
            product_title       VARCHAR DEFAULT '',
            sale_price          BIGINT DEFAULT 0,
            image_link          VARCHAR DEFAULT '',
            affiliate_link      VARCHAR DEFAULT '',
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score   DOUBLE DEFAULT 0,
            rank_in_article     INTEGER DEFAULT 0,
            product_status      VARCHAR DEFAULT 'active',
            synced_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert article
    con.execute("""
        INSERT INTO seo_articles
            (id, article_id, keyword, category, title, content_md, status)
        VALUES (1, ?, ?, ?, ?, ?, 'draft')
    """, [article_id, keyword, category, title,
          f"## บทนำ\n\nบทนำของ {keyword}\n\n## บทสรุป\n\nสรุป {keyword}\n"])

    # Insert products
    for rank, p in enumerate(products, 1):
        con.execute("""
            INSERT INTO seo_article_products
                (id, article_id, itemid, shopid, product_title, sale_price,
                 image_link, affiliate_link, affiliate_link_type, rank_in_article)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            rank, article_id, p["itemid"], p["shopid"], p["title"], p["sale_price"],
            "https://cf.shopee.co.th/file/img",
            p["aff_link"], "confirmed", rank,
        ])

    con.close()
    return tmp


def _patch_db(db_path: Path):
    return [
        patch("shopee_engine.config.DB_PATH", str(db_path)),
        patch("shopee_engine.config.config.db_path", db_path),
        patch("shopee_engine.seo_engine.config.db_path", db_path),
    ]


# ===========================================================================
# TestTitleCleaner
# ===========================================================================

class TestTitleCleaner:
    def test_strips_bracket_promo_tags(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("[ส่งด่วน] Eloop E33 Power Bank 10000mAh")
        assert result["display_title"] == "Eloop E33 Power Bank 10000mAh"
        assert result["raw_title"] == "[ส่งด่วน] Eloop E33 Power Bank 10000mAh"

    def test_strips_multiple_bracket_tags(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("[พร้อมส่ง][แถมถุง] สินค้าดี 100W")
        assert not result["display_title"].startswith("[")

    def test_strips_emoji_prefix(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("🔥 Eloop E33 Power Bank 10000mAh มีสายชาร์จในตัว")
        assert result["display_title"].startswith("Eloop")

    def test_strips_combined_bracket_and_emoji(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("[ส่งด่วน] 🔥 Eloop E33 Line แบตสำรอง 10000mAh มีสายชาร์จในตัว")
        assert result["display_title"] == "Eloop E33 Line แบตสำรอง 10000mAh มีสายชาร์จในตัว"
        assert result["flags"] == []

    def test_flags_suspicious_mah_20001(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("Brand PowerBank 20001mAh 120W")
        flags = result["flags"]
        assert any("suspicious_mah" in f and "20001" in f for f in flags), f"Flags: {flags}"

    def test_flags_suspicious_mah_30001(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("Brand PowerBank 30001mAh 120W ราคา ฿209")
        flags = result["flags"]
        assert any("suspicious_mah" in f and "30001" in f for f in flags), f"Flags: {flags}"

    def test_does_not_flag_10000_mah(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("Power Bank 10000mAh")
        flags = result["flags"]
        assert not any("suspicious_mah" in f for f in flags), f"Should not flag: {flags}"

    def test_does_not_alter_spec_values(self):
        """Flagged suspicious mAh value must still appear in display_title unchanged."""
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("PowerBank 20001mAh 120W")
        # The spec value in the title should NOT be modified
        assert "20001mAh" in result["display_title"] or "20001" in result["display_title"], \
            "Spec value was altered"

    def test_removes_price_pattern(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("Brand PowerBank 30001mAh 120W ราคา ฿209")
        assert "฿209" not in result["display_title"]

    def test_truncates_long_title(self):
        from shopee_engine.title_cleaner import clean_display_title
        long_title = "A" * 100 + " Power Bank"
        result = clean_display_title(long_title)
        assert result["truncated"] is True
        assert result["display_title"].endswith("…")
        assert len(result["display_title"]) <= 81  # 80 chars + …

    def test_raw_title_unchanged(self):
        from shopee_engine.title_cleaner import clean_display_title
        raw = "[ส่งด่วน] 🔥 Eloop E33 Power Bank 10000mAh"
        result = clean_display_title(raw)
        assert result["raw_title"] == raw

    def test_flags_title_too_long(self):
        from shopee_engine.title_cleaner import clean_display_title
        long_title = "Power Bank " + "A" * 120
        result = clean_display_title(long_title)
        assert "title_too_long" in result["flags"]

    def test_removes_repeated_punctuation(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("Power Bank ดีมาก!!! ซื้อเลย~~~")
        assert "!!!" not in result["display_title"]
        assert "~~~" not in result["display_title"]

    def test_no_flags_for_clean_title(self):
        from shopee_engine.title_cleaner import clean_display_title
        result = clean_display_title("Eloop E33 Line แบตสำรอง 10000mAh มีสายชาร์จในตัว")
        assert result["flags"] == []
        assert result["truncated"] is False


# ===========================================================================
# TestPreflightGates
# ===========================================================================

class TestPreflightGates:
    def test_canonical_category_passes_for_valid_category(self):
        """run_preflight: canonical_category gate passes for 'mobile-gadgets'."""
        db = _make_test_db(category="mobile-gadgets")
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            from shopee_engine.preflight import run_preflight
            result = run_preflight("test-article")
            gates = result["gates"]
            assert "canonical_category" in gates, f"Gates: {list(gates.keys())}"
            assert gates["canonical_category"]["passed"] is True, \
                f"Errors: {gates['canonical_category']['errors']}"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_canonical_category_fails_for_non_canonical(self):
        """run_preflight: canonical_category gate fails for raw 'USB & Mobile Fans'."""
        db = _make_test_db(category="USB & Mobile Fans")
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            from shopee_engine.preflight import run_preflight
            result = run_preflight("test-article")
            gates = result["gates"]
            assert "canonical_category" in gates
            assert gates["canonical_category"]["passed"] is False, \
                "Expected canonical_category to fail for raw 'USB & Mobile Fans'"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_title_duplication_detects_same_title(self):
        """run_preflight: title_duplication gate fails when same title exists in another article."""
        import duckdb
        db = _make_test_db(article_id="article-1", title="5 Power Bank ดีที่สุด")
        con = duckdb.connect(str(db))
        # Insert second article with same title but different id
        con.execute("""
            INSERT INTO seo_articles
                (id, article_id, keyword, category, title, content_md, status)
            VALUES (99, 'article-2', 'power bank 2', 'mobile-gadgets',
                    '5 Power Bank ดีที่สุด', 'content', 'draft')
        """)
        con.close()

        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            from shopee_engine.preflight import run_preflight
            result = run_preflight("article-1")
            gates = result["gates"]
            assert "title_duplication" in gates
            assert gates["title_duplication"]["passed"] is False, \
                "Expected title_duplication to fail"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_title_duplication_passes_when_title_is_unique(self):
        """run_preflight: title_duplication gate passes when title is unique."""
        db = _make_test_db(article_id="article-only", title="ชื่อที่ไม่ซ้ำกับใครเลย 12345")
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            from shopee_engine.preflight import run_preflight
            result = run_preflight("article-only")
            gates = result["gates"]
            assert "title_duplication" in gates
            assert gates["title_duplication"]["passed"] is True, \
                f"Errors: {gates['title_duplication']['errors']}"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_preflight_returns_article_meta(self):
        """run_preflight: article_meta contains expected fields."""
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            from shopee_engine.preflight import run_preflight
            result = run_preflight("test-article")
            meta = result["article_meta"]
            assert "title" in meta
            assert "keyword" in meta
            assert "category" in meta
            assert "status" in meta
            assert "product_count" in meta
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_preflight_not_found_returns_error(self):
        """run_preflight: returns error dict for non-existent article_id."""
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            from shopee_engine.preflight import run_preflight
            result = run_preflight("non-existent-id")
            assert result["passed"] is False
            assert len(result["summary_errors"]) > 0
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)


# ===========================================================================
# TestCrawlStagingHtml
# ===========================================================================

class TestCrawlStagingHtml:
    def _make_simple_html(
        self,
        article_id: str = "test-article",
        title: str = "5 Power Bank ดีที่สุด",
        products: list[dict] | None = None,
    ) -> str:
        """Build a minimal HTML that should pass crawl checks."""
        if products is None:
            products = [
                {"title": "Eloop E33 Power Bank 10000mAh", "price": 399,
                 "affiliate_link": "https://s.shopee.co.th/TestPB001"},
                {"title": "Anker 521 Power Bank 10000mAh", "price": 549,
                 "affiliate_link": "https://s.shopee.co.th/TestPB002"},
            ]

        product_html = ""
        for p in products:
            product_html += (
                f'<h3>{p["title"]}</h3>'
                f'<p>ราคา: ฿{p["price"]}</p>'
                f'<a href="{p["affiliate_link"]}" class="affiliate-btn">ดูสินค้า</a>'
            )

        return f"""<!DOCTYPE html>
<html><head><title>{title}</title></head>
<body>
<h1>{title}</h1>
{product_html}
</body></html>"""

    def test_detects_missing_h1(self):
        """crawl_staging_html: flags when H1 is missing."""
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            html = "<html><body><p>No heading here</p></body></html>"
            result = crawl_staging_html("test-article", html)
            checks = result["checks"]
            assert "h1_exists" in checks
            assert checks["h1_exists"]["passed"] is False
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_finds_product_price_in_html(self):
        """crawl_staging_html: passes when all product prices are found."""
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            html = self._make_simple_html()
            result = crawl_staging_html("test-article", html)
            checks = result["checks"]
            assert "product_prices" in checks
            assert checks["product_prices"]["passed"] is True, \
                f"Detail: {checks['product_prices']['detail']}"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_flags_broken_placeholder_text(self):
        """crawl_staging_html: detects [object Object] artifact."""
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            html = (
                "<html><body><h1>5 Power Bank ดีที่สุด</h1>"
                "<p>[object Object] broken content</p>"
                "<a href='https://s.shopee.co.th/t' class='affiliate-btn'>ดู</a>"
                "<a href='https://s.shopee.co.th/t2' class='affiliate-btn'>ดู</a>"
                "</body></html>"
            )
            result = crawl_staging_html("test-article", html)
            checks = result["checks"]
            assert "no_artifacts" in checks
            assert checks["no_artifacts"]["passed"] is False, \
                "Expected [object Object] to be flagged"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_detects_missing_affiliate_links(self):
        """crawl_staging_html: fails when affiliate-btn count != product count."""
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            # DB has 2 products but HTML has 0 affiliate-btn links
            html = (
                "<html><body><h1>5 Power Bank ดีที่สุด</h1>"
                "<p>ราคา: ฿399</p><p>ราคา: ฿549</p>"
                "<p>Eloop E33 Power Bank 10000mAh</p>"
                "<p>Anker 521 Power Bank 10000mAh</p>"
                "</body></html>"
            )
            result = crawl_staging_html("test-article", html)
            checks = result["checks"]
            assert "affiliate_btn_count" in checks or "product_count" in checks
            # One of these should fail
            product_count_check = checks.get("product_count") or checks.get("affiliate_btn_count")
            assert product_count_check is not None
            assert product_count_check["passed"] is False
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_passes_valid_html(self):
        """crawl_staging_html: all main checks pass for well-formed HTML."""
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            html = self._make_simple_html()
            result = crawl_staging_html("test-article", html)
            # At minimum, no_artifacts and h1_exists should pass
            checks = result["checks"]
            assert checks.get("no_artifacts", {}).get("passed") is True
            assert checks.get("h1_exists", {}).get("passed") is True
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)
