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


# ===========================================================================
# TestSmartTableTruncation
# ===========================================================================

class TestSmartTableTruncation:
    """_truncate_table_name must never cut inside a model code."""

    def test_rpp_680_preserved_when_bracket_prefix_pushes_it_near_40(self):
        """RPP-680 must appear intact — not truncated to RPP-68."""
        from shopee_engine.seo_engine import _truncate_table_name
        title = "[ แถมถุง มีCCC ] Remax Power Bank RPP-680 20000mAh Fast Charge USB-C หน้าจอ LED"
        result = _truncate_table_name(title)
        assert "RPP-680" in result, f"Model code cut: {result!r}"
        assert "RPP-68" not in result.replace("RPP-680", ""), (
            f"Truncated version RPP-68 must not appear: {result!r}"
        )

    def test_rpp_678_preserved_when_bracket_prefix_pushes_it_near_40(self):
        """RPP-678 must appear intact — not truncated to RPP-67."""
        from shopee_engine.seo_engine import _truncate_table_name
        title = "[ CCC ] Remax Wireless Power Bank RPP-678 (N) มีสายในตัว มีประกันศูนย์ไทย"
        result = _truncate_table_name(title)
        assert "RPP-678" in result, f"Model code cut: {result!r}"

    def test_truncates_at_word_boundary_not_mid_word(self):
        """Long title truncated at word boundary, not mid-word or mid-model-code."""
        from shopee_engine.seo_engine import _truncate_table_name
        # 70-char title — should truncate somewhere but never in the middle of "ANKER-A1234"
        title = "Anker PowerBank ANKER-A1234 20000mAh 65W PD Fast Charge with Display"
        result = _truncate_table_name(title)
        # "ANKER-A1234" is 11 chars, starts at position 17 — well inside 60 char limit
        assert "ANKER-A1234" in result, f"Model code not preserved: {result!r}"
        assert result.endswith("…") or len(result) == len(title.replace("|", "｜")), (
            f"Unexpected truncation result: {result!r}"
        )

    def test_short_title_returned_unchanged(self):
        """Title under 60 chars returned as-is (pipes escaped)."""
        from shopee_engine.seo_engine import _truncate_table_name
        title = "Eloop E33 10000mAh Power Bank"
        assert _truncate_table_name(title) == title

    def test_pipe_in_title_is_escaped(self):
        """Pipe characters are escaped so they don't break the markdown table."""
        from shopee_engine.seo_engine import _truncate_table_name
        title = "Brand X | Y Power Bank"
        result = _truncate_table_name(title)
        assert "|" not in result or result.count("｜") >= 1


# ===========================================================================
# TestStaleModelDetection
# ===========================================================================

class TestStaleModelDetection:
    """validate_content_consistency must not flag truncation artifacts as stale."""

    def _make_stale_db(self, article_id: str, content_md: str, product_titles: list[str]) -> Path:
        """DB with given content_md and specified product titles."""
        import duckdb
        db = _make_test_db(article_id=article_id)
        con = duckdb.connect(str(db))
        # Update content_md with our test body
        con.execute(
            "UPDATE seo_articles SET content_md = ? WHERE article_id = ?",
            [content_md, article_id],
        )
        # Update product titles
        con.execute(f"DELETE FROM seo_article_products WHERE article_id = ?", [article_id])
        for rank, t in enumerate(product_titles, 1):
            con.execute("""
                INSERT INTO seo_article_products
                    (id, article_id, itemid, shopid, product_title, sale_price,
                     image_link, affiliate_link, affiliate_link_type, rank_in_article)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [rank + 100, article_id, rank + 3000, rank + 7000, t, 500,
                  "", "https://s.shopee.co.th/test", "confirmed", rank])
        con.close()
        return db

    def test_exact_current_model_not_flagged(self):
        """RPP-680 in prose is not stale when RPP-680 is in current products."""
        from shopee_engine.seo_engine import validate_content_consistency
        body = "## บทนำ\n\nสินค้าที่แนะนำคือ Remax RPP-680 ความจุ 20000mAh\n\n## บทสรุป\n\nดีมาก\n"
        db = self._make_stale_db("a-rpp680", body, ["[ CCC ] Remax Power Bank RPP-680 20000mAh"])
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            result = validate_content_consistency("a-rpp680")
            stale = result["stale_items"]
            assert "RPP-680" not in stale, f"RPP-680 should NOT be stale: {stale}"
            assert result["consistent"] is True, f"Should be consistent: {stale}"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_truncated_prefix_rpp_68_not_flagged_when_rpp_680_is_current(self):
        """RPP-68 in content_md (truncation artifact) must not be flagged as stale."""
        from shopee_engine.seo_engine import validate_content_consistency
        # Simulate content_md that contains a comparison table with truncated model code
        body = (
            "## บทนำ\n\nบทนำ\n\n"
            "## ตารางเปรียบเทียบ\n\n"
            "| # | สินค้า | ราคา |\n"
            "|---|-------|------|\n"
            "| 1 | [ แถมถุง มีCCC ] Remax Power Bank RPP-68 | ฿699 |\n"  # truncated
            "\n## บทสรุป\n\nดีมาก\n"
        )
        db = self._make_stale_db("a-prefix68", body, ["[ CCC ] Remax Power Bank RPP-680 20000mAh"])
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            result = validate_content_consistency("a-prefix68")
            stale = result["stale_items"]
            assert "RPP-68" not in stale, (
                f"RPP-68 is a prefix of current model RPP-680 — must NOT be flagged: {stale}"
            )
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_truncated_prefix_rpp_67_not_flagged_when_rpp_678_is_current(self):
        """RPP-67 in content_md (truncation artifact) must not be flagged as stale."""
        from shopee_engine.seo_engine import validate_content_consistency
        body = (
            "## ตารางเปรียบเทียบ\n\n"
            "| 1 | [ CCC ] Remax Wireless Power Bank RPP-67 | ฿799 |\n"  # truncated
            "\n## บทสรุป\n\nดีมาก\n"
        )
        db = self._make_stale_db("a-prefix67", body, ["[ CCC ] Remax Wireless Power Bank RPP-678 (N)"])
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            result = validate_content_consistency("a-prefix67")
            stale = result["stale_items"]
            assert "RPP-67" not in stale, (
                f"RPP-67 is a prefix of current model RPP-678 — must NOT be flagged: {stale}"
            )
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_genuinely_stale_model_is_still_flagged(self):
        """A truly stale model code (not a prefix of current) must still be flagged."""
        from shopee_engine.seo_engine import validate_content_consistency
        # Old product PB-Y59 in prose, but current product is PB-Y60
        body = "## บทนำ\n\nสินค้าเก่า PB-Y59 ที่เคยแนะนำ\n\n## บทสรุป\n\nดี\n"
        db = self._make_stale_db("a-stale-y59", body, ["AUKEY Power Bank PB-Y60 20000mAh"])
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            result = validate_content_consistency("a-stale-y59")
            stale = result["stale_items"]
            assert "PB-Y59" in stale, f"PB-Y59 SHOULD be stale (current is PB-Y60): {stale}"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)


# ===========================================================================
# TestCrawlArtifactExtended
# ===========================================================================

class TestCrawlArtifactExtended:
    """Extended artifact checks in crawl_staging_html."""

    def _base_html(self, extra_body: str = "") -> str:
        return (
            "<html><head><title>Test</title></head>"
            "<body>"
            "<h1>5 Power Bank ดีที่สุด</h1>"
            "<p>ราคา: ฿399</p><p>ราคา: ฿549</p>"
            "<p>Eloop E33 Power Bank 10000mAh</p>"
            "<p>Anker 521 Power Bank 10000mAh</p>"
            '<a href="https://s.shopee.co.th/TestPB001" class="affiliate-btn">ดูสินค้า</a>'
            '<a href="https://s.shopee.co.th/TestPB002" class="affiliate-btn">ดูสินค้า</a>'
            + extra_body
            + "</body></html>"
        )

    def _run_crawl(self, html: str) -> dict:
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            return crawl_staging_html("test-article", html)
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_markdown_image_syntax_fails_no_artifacts(self):
        """Raw ![alt](url) in HTML body must trigger no_artifacts failure."""
        html = self._base_html('<p>![product image](https://cf.shopee.co.th/img.jpg)</p>')
        result = self._run_crawl(html)
        checks = result["checks"]
        assert "no_artifacts" in checks
        assert checks["no_artifacts"]["passed"] is False, (
            f"Should fail — raw Markdown image found. Detail: {checks['no_artifacts']['detail']}"
        )
        assert "image" in checks["no_artifacts"]["detail"].lower()

    def test_raw_markdown_blockquote_fails_no_artifacts(self):
        """<p>&gt; text</p> (unrendered blockquote) must trigger no_artifacts failure."""
        html = self._base_html("<p>&gt; Editorial highlight context here</p>")
        result = self._run_crawl(html)
        checks = result["checks"]
        assert "no_artifacts" in checks
        assert checks["no_artifacts"]["passed"] is False, (
            f"Should fail — raw blockquote marker. Detail: {checks['no_artifacts']['detail']}"
        )

    def test_markdown_table_separator_fails_no_artifacts(self):
        """<td>---</td> from unprocessed table separator must trigger no_artifacts failure."""
        html = self._base_html(
            "<table><tr><td>---</td><td>---</td></tr></table>"
        )
        result = self._run_crawl(html)
        checks = result["checks"]
        assert "no_artifacts" in checks
        assert checks["no_artifacts"]["passed"] is False, (
            f"Should fail — Markdown separator in <td>. Detail: {checks['no_artifacts']['detail']}"
        )

    def test_orphaned_tr_fails_no_artifacts(self):
        """<tr> without enclosing <table> must trigger no_artifacts failure."""
        html = self._base_html(
            "<tr><td>orphaned row</td></tr>"
        )
        result = self._run_crawl(html)
        checks = result["checks"]
        assert "no_artifacts" in checks
        assert checks["no_artifacts"]["passed"] is False, (
            f"Should fail — orphaned <tr>. Detail: {checks['no_artifacts']['detail']}"
        )

    def test_clean_html_passes_no_artifacts(self):
        """Well-formed HTML with no raw Markdown must pass no_artifacts."""
        html = self._base_html(
            "<table><thead><tr><th>สินค้า</th><th>ราคา</th></tr></thead>"
            "<tbody><tr><td>Eloop E33</td><td>฿399</td></tr></tbody></table>"
        )
        result = self._run_crawl(html)
        checks = result["checks"]
        assert checks.get("no_artifacts", {}).get("passed") is True, (
            f"Should pass no_artifacts. Detail: {checks.get('no_artifacts', {}).get('detail')}"
        )


# ===========================================================================
# TestRelatedArticlesInStaging
# ===========================================================================

class TestRelatedArticlesInStaging:
    """generate_preview_body must include related articles when they exist."""

    def test_preview_body_includes_related_articles_section(self):
        """generate_preview_body output includes บทความที่เกี่ยวข้อง when related articles exist."""
        from unittest.mock import patch as _patch
        from shopee_engine.article_exporter import generate_preview_body

        db = _make_test_db()
        patches = _patch_db(db)
        related_mock = [
            {"article_id": "power-bank-10000-mah", "title": "Power Bank 10000mAh", "keyword": ""},
            {"article_id": "power-bank-ccc", "title": "Power Bank CCC", "keyword": ""},
        ]
        for p in patches:
            p.start()
        try:
            with _patch("shopee_engine.article_exporter.get_related_articles",
                        return_value=related_mock):
                result = generate_preview_body("test-article")
            assert result.get("success") is True, f"Error: {result.get('error')}"
            body = result["body"]
            assert "บทความที่เกี่ยวข้อง" in body, (
                "Related articles section missing from preview body"
            )
            assert "power-bank-10000-mah" in body or "Power Bank 10000mAh" in body, (
                "Related article link/title not found in body"
            )
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_preview_body_no_related_section_when_none_exist(self):
        """generate_preview_body does not include related section when list is empty."""
        from unittest.mock import patch as _patch
        from shopee_engine.article_exporter import generate_preview_body

        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            with _patch("shopee_engine.article_exporter.get_related_articles", return_value=[]):
                result = generate_preview_body("test-article")
            assert result.get("success") is True
            body = result["body"]
            # Section should be absent or empty when no related articles
            assert "- [" not in body or "บทความที่เกี่ยวข้อง" not in body, (
                "Related section should be absent when list is empty"
            )
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)


# ===========================================================================
# TestRendererConsistency
# ===========================================================================

class TestRendererConsistency:
    """preview body must use the same pipeline as export_article."""

    def test_preview_body_contains_comparison_table_header(self):
        """Preview body includes the comparison table with Thai header row."""
        from unittest.mock import patch as _patch
        from shopee_engine.article_exporter import generate_preview_body

        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            with _patch("shopee_engine.article_exporter.get_related_articles", return_value=[]):
                result = generate_preview_body("test-article")
            assert result.get("success") is True
            body = result["body"]
            assert "ตารางเปรียบเทียบ" in body, "Comparison table section missing from preview"
            assert "สินค้า" in body and "ราคา" in body, "Comparison table header missing"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_preview_body_contains_product_section(self):
        """Preview body includes the product detail section (แนะนำสินค้า)."""
        from unittest.mock import patch as _patch
        from shopee_engine.article_exporter import generate_preview_body

        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            with _patch("shopee_engine.article_exporter.get_related_articles", return_value=[]):
                result = generate_preview_body("test-article")
            assert result.get("success") is True
            body = result["body"]
            assert "แนะนำสินค้า" in body, "Product section missing from preview"
            # Both test products should appear
            assert "Eloop E33" in body, "First product missing from preview"
            assert "Anker 521" in body, "Second product missing from preview"
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)


# ===========================================================================
# TestFaqHeadingGeneration
# ===========================================================================

class TestFaqHeadingGeneration:
    """FAQ builder must not produce #N rank references that render as H1."""

    def _build_faq(self, products=None) -> str:
        from shopee_engine.decision_engine import build_decision_faq
        if products is None:
            products = [
                {"sale_price": 184, "item_sold": 5000, "item_rating": 4.7,
                 "shop_rating": 4.8, "discount_pct": 50,
                 "title": "JMAX PowerBank M19 10000mAh"},
                {"sale_price": 399, "item_sold": 3000, "item_rating": 4.6,
                 "shop_rating": 4.7, "discount_pct": 0,
                 "title": "Eloop E33 10000mAh"},
                {"sale_price": 699, "item_sold": 2000, "item_rating": 4.5,
                 "shop_rating": 4.6, "discount_pct": 0,
                 "title": "Remax RPP-680 20000mAh"},
            ]
            for i, p in enumerate(products):
                p["sale_price_fmt"] = f"฿{p['sale_price']:,}"
                p["original_price"] = p["sale_price"]
                p["original_price_fmt"] = f"฿{p['sale_price']:,}"
                p["item_sold"] = p.get("item_sold", 0)
                p["image_link"] = ""
                p["affiliate_link"] = "https://s.shopee.co.th/test"
                p["product_link"] = ""
        return build_decision_faq("Power Bank มีสายในตัว รุ่นไหนดี", "mobile-gadgets", products)

    def test_faq_does_not_start_paragraph_with_hash_number(self):
        """FAQ answer bodies must not start with #N (would render as H1)."""
        faq = self._build_faq()
        # Split into non-empty lines and check none starts with #<digit>
        import re
        problem_lines = [
            line for line in faq.split("\n")
            if re.match(r"^#\d", line.strip())
        ]
        assert problem_lines == [], (
            f"FAQ has lines starting with #<digit> (renders as H1): {problem_lines}"
        )

    def test_faq_uses_andan_rank_format(self):
        """FAQ should use 'อันดับ N' format, not '#N'."""
        faq = self._build_faq()
        assert "อันดับ" in faq, "FAQ should use อันดับ format for rank references"

    def test_faq_content_has_no_h1_heading_markers(self):
        """No line in FAQ output should render as an H1 heading.

        ## headers (H2) are intentional section titles and are allowed.
        Single # (H1) or #N digit patterns are forbidden.
        """
        import re
        faq = self._build_faq()
        for line in faq.split("\n"):
            stripped = line.strip()
            # Reject: single # followed by space (H1) — "# Heading"
            assert not re.match(r"^#\s", stripped), (
                f"H1 heading marker found in FAQ: {stripped!r}"
            )
            # Reject: # followed immediately by digit — "#1", "#4" (renders as H1)
            assert not re.match(r"^#\d", stripped), (
                f"#N pattern (renders as H1) found: {stripped!r}"
            )


# ===========================================================================
# TestH1CountValidation
# ===========================================================================

class TestH1CountValidation:
    """HTML must contain exactly one H1 tag."""

    def _run_crawl(self, html: str) -> dict:
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            return crawl_staging_html("test-article", html)
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_single_h1_passes(self):
        """Exactly one H1 that matches the title must pass h1_exists."""
        html = (
            "<html><body>"
            "<h1>5 Power Bank ดีที่สุด</h1>"
            "<p>ราคา: ฿399</p><p>ราคา: ฿549</p>"
            "<p>Eloop E33 Power Bank 10000mAh</p>"
            "<p>Anker 521 Power Bank 10000mAh</p>"
            '<a href="https://s.shopee.co.th/t" class="affiliate-btn">ดู</a>'
            '<a href="https://s.shopee.co.th/t2" class="affiliate-btn">ดู</a>'
            "</body></html>"
        )
        result = self._run_crawl(html)
        assert result["checks"]["h1_exists"]["passed"] is True, (
            f"Detail: {result['checks']['h1_exists']['detail']}"
        )

    def test_multiple_h1_fails(self):
        """More than one H1 must cause h1_exists to fail."""
        html = (
            "<html><body>"
            "<h1>5 Power Bank ดีที่สุด</h1>"
            "<h1>1 ขายแล้ว 5,000 ชิ้น</h1>"  # FAQ answer rendered as H1
            '<a href="https://s.shopee.co.th/t" class="affiliate-btn">ดู</a>'
            '<a href="https://s.shopee.co.th/t2" class="affiliate-btn">ดู</a>'
            "</body></html>"
        )
        result = self._run_crawl(html)
        assert result["checks"]["h1_exists"]["passed"] is False, (
            "Multiple H1 should fail h1_exists check"
        )
        assert "2" in result["checks"]["h1_exists"]["detail"] or "Multiple" in result["checks"]["h1_exists"]["detail"]

    def test_zero_h1_fails(self):
        """No H1 tag must cause h1_exists to fail."""
        html = (
            "<html><body>"
            "<h2>5 Power Bank ดีที่สุด</h2>"
            '<a href="https://s.shopee.co.th/t" class="affiliate-btn">ดู</a>'
            '<a href="https://s.shopee.co.th/t2" class="affiliate-btn">ดู</a>'
            "</body></html>"
        )
        result = self._run_crawl(html)
        assert result["checks"]["h1_exists"]["passed"] is False


# ===========================================================================
# TestStrikethroughArtifacts
# ===========================================================================

class TestStrikethroughArtifacts:
    """~~text~~ raw Markdown must fail no_artifacts; <del> must not."""

    def _run_crawl(self, html: str) -> dict:
        from shopee_engine.preflight import crawl_staging_html
        db = _make_test_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            return crawl_staging_html("test-article", html)
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def _base(self, extra: str = "") -> str:
        return (
            "<html><body>"
            "<h1>5 Power Bank ดีที่สุด</h1>"
            "<p>ราคา: ฿399</p><p>ราคา: ฿549</p>"
            "<p>Eloop E33 Power Bank 10000mAh</p>"
            "<p>Anker 521 Power Bank 10000mAh</p>"
            '<a href="https://s.shopee.co.th/t" class="affiliate-btn">ดู</a>'
            '<a href="https://s.shopee.co.th/t2" class="affiliate-btn">ดู</a>'
            + extra
            + "</body></html>"
        )

    def test_raw_strikethrough_fails_no_artifacts(self):
        """~~฿1,990~~ in HTML body must trigger no_artifacts failure."""
        html = self._base("<p>ราคาเดิม ~~฿1,990~~</p>")
        result = self._run_crawl(html)
        checks = result["checks"]
        assert "no_artifacts" in checks
        assert checks["no_artifacts"]["passed"] is False, (
            f"~~฿1,990~~ should fail no_artifacts. Detail: {checks['no_artifacts']['detail']}"
        )
        assert "strikethrough" in checks["no_artifacts"]["detail"].lower()

    def test_del_tag_passes_no_artifacts(self):
        """<del>฿1,990</del> rendered HTML must pass no_artifacts."""
        html = self._base("<p>ราคาเดิม <del>฿1,990</del></p>")
        result = self._run_crawl(html)
        checks = result["checks"]
        assert checks.get("no_artifacts", {}).get("passed") is True, (
            f"<del> tag should pass. Detail: {checks.get('no_artifacts', {}).get('detail')}"
        )

    def test_product_block_uses_del_not_tilde(self):
        """_build_product_blocks must use <del> not ~~ for original price."""
        from shopee_engine.seo_engine import _build_product_blocks
        products = [{
            "title": "Eloop E33 10000mAh",
            "sale_price": 399,
            "sale_price_fmt": "฿399",
            "original_price": 599,
            "original_price_fmt": "฿599",
            "item_sold": 1000,
            "item_rating": 4.7,
            "shop_rating": 4.8,
            "discount_pct": 33,
            "image_link": "",
            "affiliate_link": "https://s.shopee.co.th/test",
            "product_link": "",
            "ccc_evidence_source": "no_evidence",
            "ccc_evidence_text": "",
            "ccc_confidence_note": "",
        }]
        result = _build_product_blocks(products)
        assert "<del>฿599</del>" in result, (
            f"Expected <del>฿599</del> but got: {result[:300]!r}"
        )
        assert "~~฿599~~" not in result, "Must not use ~~ for strikethrough"


# ===========================================================================
# TestRelatedArticlesPriority
# ===========================================================================

class TestRelatedArticlesPriority:
    """Power Bank articles must appear before category-fallback articles."""

    def _make_multi_article_db(self) -> "Path":
        """DB with 2 power bank articles + 2 fan articles (same category)."""
        import duckdb
        db = _make_test_db(article_id="pb-main", keyword="Power Bank มีสายในตัว รุ่นไหนดี")
        con = duckdb.connect(str(db))

        # Insert power bank articles
        for i, (aid, kw) in enumerate([
            ("pb-10000-mah", "Power Bank 10000mAh ราคาถูก"),
            ("pb-ccc",       "Power Bank ที่มี CCC รุ่นไหนดี"),
        ], start=2):
            con.execute("""
                INSERT INTO seo_articles
                    (id, article_id, keyword, category, title, content_md, status)
                VALUES (?, ?, ?, 'mobile-gadgets', ?, '', 'published')
            """, [i, aid, kw, f"Title {aid}"])

        # Insert fan articles (same category, different cluster)
        for i, (aid, kw) in enumerate([
            ("fan-usb-mobile", "USB & Mobile Fans รุ่นไหนดี"),
            ("fan-desk",       "พัดลมตั้งโต๊ะ USB ดีไหม"),
        ], start=4):
            con.execute("""
                INSERT INTO seo_articles
                    (id, article_id, keyword, category, title, content_md, status)
                VALUES (?, ?, ?, 'mobile-gadgets', ?, '', 'published')
            """, [i, aid, kw, f"Title {aid}"])

        con.close()
        return db

    def test_power_bank_articles_appear_before_fan_articles(self):
        """get_related_articles for power bank must list PB articles before fans."""
        from shopee_engine.seo_engine import get_related_articles
        db = self._make_multi_article_db()
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            related = get_related_articles("pb-main", limit=4)
            article_ids = [r["article_id"] for r in related]
            # Both power bank articles must appear
            assert "pb-10000-mah" in article_ids, f"Missing pb-10000-mah: {article_ids}"
            assert "pb-ccc" in article_ids, f"Missing pb-ccc: {article_ids}"
            # Power bank articles must appear BEFORE any fan articles
            pb_indices = [i for i, aid in enumerate(article_ids) if aid.startswith("pb-")]
            fan_indices = [i for i, aid in enumerate(article_ids) if aid.startswith("fan-")]
            if pb_indices and fan_indices:
                assert max(pb_indices) < min(fan_indices), (
                    f"Fan article appeared before PB article: {article_ids}"
                )
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)

    def test_power_bank_only_when_sufficient_cluster_articles(self):
        """If >= limit power bank articles exist, fans must not appear."""
        import duckdb
        db = _make_test_db(article_id="pb-main2", keyword="Power Bank ชาร์จเร็ว 20W")
        con = duckdb.connect(str(db))
        # Insert 4 power bank articles (= limit)
        for i, (aid, kw) in enumerate([
            ("pb-a1", "Power Bank 10000mAh ราคาถูก"),
            ("pb-a2", "Power Bank ที่มี CCC"),
            ("pb-a3", "Power Bank ชาร์จเร็ว สำหรับ iPhone"),
            ("pb-a4", "Power Bank มีสายในตัว"),
        ], start=2):
            con.execute("""
                INSERT INTO seo_articles
                    (id, article_id, keyword, category, title, content_md, status)
                VALUES (?, ?, ?, 'mobile-gadgets', ?, '', 'published')
            """, [i, aid, kw, f"Title {aid}"])
        # Insert fan article (same category)
        con.execute("""
            INSERT INTO seo_articles
                (id, article_id, keyword, category, title, content_md, status)
            VALUES (6, 'fan-usb', 'USB & Mobile Fans รุ่นไหนดี', 'mobile-gadgets', 'Fan Title', '', 'published')
        """)
        con.close()

        from shopee_engine.seo_engine import get_related_articles
        patches = _patch_db(db)
        for p in patches:
            p.start()
        try:
            related = get_related_articles("pb-main2", limit=4)
            article_ids = [r["article_id"] for r in related]
            assert "fan-usb" not in article_ids, (
                f"Fan article must not appear when 4 PB articles exist: {article_ids}"
            )
            assert len(article_ids) == 4
        finally:
            for p in patches:
                p.stop()
            db.unlink(missing_ok=True)
