"""Regression tests for article editing workflow.

Rules under test:
  - Edits always update the database (source of truth), never the generated Markdown file.
  - Refresh never duplicates article files.
  - Republish keeps the same URL (article_id unchanged).
  - Title edits never change slug (article_id).
  - Rollback restores previous content and demotes to draft.
  - A revision is saved before every edit.
  - add_product validates existence and prevents duplicates.
  - remove_product re-ranks remaining products starting at 1.
  - replace_product preserves the original rank.
  - Editing a field in a published article sets requires_republish=True.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _make_db(
    status: str = "draft",
    content_md: str = "",
    article_id: str = "test-article",
    category: str = "mobile-gadgets",
    add_product: bool = True,
    itemids: list[int] | None = None,
) -> str:
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)

    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE products (
            itemid BIGINT, shopid BIGINT, title VARCHAR, sale_price BIGINT,
            image_link VARCHAR, product_link VARCHAR,
            "product_short link" VARCHAR,
            stock INTEGER DEFAULT 10
        )
    """)
    con.execute("""
        CREATE TABLE affiliate_products (product_link VARCHAR, affiliate_short_url VARCHAR)
    """)
    con.execute("""
        CREATE TABLE seo_articles (
            id INTEGER PRIMARY KEY, article_id VARCHAR UNIQUE NOT NULL,
            keyword VARCHAR NOT NULL, category VARCHAR DEFAULT 'mobile-gadgets',
            category_label VARCHAR DEFAULT '', subcategory VARCHAR DEFAULT '',
            subcategory_label VARCHAR DEFAULT '',
            title VARCHAR DEFAULT 'Test Article', meta_description VARCHAR DEFAULT 'Test meta',
            content_md TEXT DEFAULT '',
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
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score DOUBLE DEFAULT 0, rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE seo_article_revisions (
            id INTEGER PRIMARY KEY, article_id VARCHAR NOT NULL,
            revision_number INTEGER NOT NULL,
            title VARCHAR DEFAULT '', meta_description VARCHAR DEFAULT '',
            content_md TEXT DEFAULT '', category VARCHAR DEFAULT '',
            category_label VARCHAR DEFAULT '', status VARCHAR DEFAULT '',
            saved_by VARCHAR DEFAULT 'system', change_summary VARCHAR DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    if not content_md:
        content_md = "## บทนำ\n\nบทนำเดิม\n\n## บทสรุป\n\nสรุปเดิม\n"

    con.execute("""
        INSERT INTO seo_articles (id, article_id, keyword, category, title, meta_description, content_md, status)
        VALUES (1, ?, 'test keyword', ?, 'Test Title', 'Test meta', ?, ?)
    """, [article_id, category, content_md, status])

    items = itemids or ([1001, 1002] if add_product else [])
    for idx, iid in enumerate(items, 1):
        shopid = 100 + idx
        plink  = f"https://shopee.co.th/product/{shopid}/{iid}"
        con.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?)",
                    [iid, shopid, f"Product {idx}", 500, "", plink, "", 10])
        con.execute("""
            INSERT INTO seo_article_products
                (id, article_id, itemid, shopid, product_title, sale_price,
                 affiliate_link, affiliate_link_type, rank_in_article)
            VALUES (?, ?, ?, ?, ?, 500, '', 'none', ?)
        """, [idx, article_id, iid, shopid, f"Product {idx}", idx])

    con.close()
    return path


def _patch_db(db_path: str):
    return patch("shopee_engine.config.config.db_path", Path(db_path))


def _patch_aff():
    return patch(
        "shopee_engine.affiliate_products_engine.get_all_affiliate_products",
        return_value={},
    )


# ---------------------------------------------------------------------------
# 1. edit_article_field updates database, NOT the Markdown file
# ---------------------------------------------------------------------------

class TestEditUpdatesDatabase(unittest.TestCase):

    def test_title_edit_updates_db_title(self):
        from shopee_engine.seo_engine import edit_article_field, get_article
        db = _make_db()
        with _patch_db(db):
            result = edit_article_field("test-article", "title", "New Title", "test")
        self.assertTrue(result["success"], result)
        with _patch_db(db):
            article = get_article("test-article")
        self.assertEqual(article["title"], "New Title")

    def test_edit_does_not_touch_markdown_file(self):
        """edit_article_field must never write to any .md file."""
        from shopee_engine.seo_engine import edit_article_field
        db = _make_db()
        md_writes: list[str] = []

        original_open = open
        def tracked_open(path, mode="r", *a, **kw):
            if "w" in str(mode) and str(path).endswith(".md"):
                md_writes.append(str(path))
            return original_open(path, mode, *a, **kw)

        with _patch_db(db), patch("builtins.open", side_effect=tracked_open):
            edit_article_field("test-article", "title", "Changed Title", "test")

        self.assertEqual(md_writes, [], f"Unexpected .md write: {md_writes}")

    def test_intro_edit_updates_content_md(self):
        from shopee_engine.seo_engine import edit_article_field, get_article
        db = _make_db()
        with _patch_db(db):
            result = edit_article_field("test-article", "intro", "บทนำใหม่ที่ดีกว่าเดิม", "test")
        self.assertTrue(result["success"], result)
        with _patch_db(db):
            article = get_article("test-article")
        self.assertIn("บทนำใหม่ที่ดีกว่าเดิม", article["content_md"])

    def test_summary_edit_updates_content_md(self):
        from shopee_engine.seo_engine import edit_article_field, get_article
        db = _make_db()
        with _patch_db(db):
            result = edit_article_field("test-article", "summary", "สรุปใหม่ที่ชัดเจน", "test")
        self.assertTrue(result["success"], result)
        with _patch_db(db):
            article = get_article("test-article")
        self.assertIn("สรุปใหม่ที่ชัดเจน", article["content_md"])


# ---------------------------------------------------------------------------
# 2. Title edit does NOT change slug (article_id)
# ---------------------------------------------------------------------------

class TestTitleEditDoesNotChangeSlug(unittest.TestCase):

    def test_article_id_unchanged_after_title_edit(self):
        from shopee_engine.seo_engine import edit_article_field
        db = _make_db(article_id="my-article-slug")
        with _patch_db(db):
            result = edit_article_field("my-article-slug", "title", "Totally Different Title", "test")
        self.assertTrue(result["success"])
        self.assertTrue(result["slug_unchanged"])
        # article_id in result must equal the original slug
        self.assertEqual(result["article_id"], "my-article-slug")

    def test_article_id_still_in_db_after_title_edit(self):
        from shopee_engine.seo_engine import edit_article_field, get_article
        db = _make_db(article_id="stable-slug")
        with _patch_db(db):
            edit_article_field("stable-slug", "title", "Brand New Title", "test")
            article = get_article("stable-slug")
        self.assertIsNotNone(article)
        self.assertEqual(article["article_id"], "stable-slug")
        self.assertEqual(article["title"], "Brand New Title")


# ---------------------------------------------------------------------------
# 3. Edit saves revision first
# ---------------------------------------------------------------------------

class TestEditSavesRevision(unittest.TestCase):

    def test_revision_exists_after_edit(self):
        from shopee_engine.seo_engine import edit_article_field, get_article_history
        db = _make_db()
        with _patch_db(db):
            edit_article_field("test-article", "title", "Edited Title", "test")
            history = get_article_history("test-article")
        self.assertGreater(len(history), 0)

    def test_revision_contains_old_title(self):
        from shopee_engine.seo_engine import edit_article_field, get_article_history
        db = _make_db()
        with _patch_db(db):
            edit_article_field("test-article", "title", "New Title", "test")
            history = get_article_history("test-article")
        old_titles = [r["title"] for r in history]
        self.assertIn("Test Title", old_titles)

    def test_invalid_field_rejected(self):
        from shopee_engine.seo_engine import edit_article_field
        db = _make_db()
        with _patch_db(db):
            result = edit_article_field("test-article", "nonexistent_field", "val", "test")
        self.assertFalse(result["success"])
        self.assertIn("ไม่รองรับ", result["error"])


# ---------------------------------------------------------------------------
# 4. Rollback restores previous content
# ---------------------------------------------------------------------------

class TestRollback(unittest.TestCase):

    def test_rollback_restores_title(self):
        from shopee_engine.seo_engine import edit_article_field, get_article, rollback_article
        db = _make_db()
        with _patch_db(db):
            r = edit_article_field("test-article", "title", "Changed Title", "test")
            rev_num = r["revision_saved"]
            rollback_article("test-article", rev_num)
            article = get_article("test-article")
        self.assertEqual(article["title"], "Test Title")

    def test_rollback_demotes_to_draft(self):
        from shopee_engine.seo_engine import edit_article_field, get_article, rollback_article
        db = _make_db(status="reviewed")
        with _patch_db(db):
            r = edit_article_field("test-article", "title", "Changed", "test")
            rev_num = r["revision_saved"]
            rollback_article("test-article", rev_num)
            article = get_article("test-article")
        self.assertEqual(article["status"], "draft")

    def test_rollback_nonexistent_revision_fails(self):
        from shopee_engine.seo_engine import rollback_article
        db = _make_db()
        with _patch_db(db):
            result = rollback_article("test-article", 999)
        self.assertFalse(result["success"])


# ---------------------------------------------------------------------------
# 5. Revision pruning — max 5 kept
# ---------------------------------------------------------------------------

class TestRevisionPruning(unittest.TestCase):

    def test_max_5_revisions_kept(self):
        from shopee_engine.seo_engine import edit_article_field, get_article_history
        db = _make_db()
        with _patch_db(db):
            for i in range(8):
                edit_article_field("test-article", "meta_description", f"meta {i}", "test")
            history = get_article_history("test-article")
        self.assertLessEqual(len(history), 5)


# ---------------------------------------------------------------------------
# 6. add_product validates existence and prevents duplicates
# ---------------------------------------------------------------------------

class TestAddProduct(unittest.TestCase):

    def test_add_existing_itemid_blocked(self):
        from shopee_engine.seo_engine import add_product_to_article
        db = _make_db(itemids=[1001, 1002])
        with _patch_db(db), _patch_aff():
            result = add_product_to_article("test-article", 1001)
        self.assertFalse(result["success"])
        self.assertIn("มีอยู่", result["error"])

    def test_add_nonexistent_itemid_blocked(self):
        from shopee_engine.seo_engine import add_product_to_article
        db = _make_db(itemids=[1001])
        with _patch_db(db), _patch_aff():
            result = add_product_to_article("test-article", 9999999)
        self.assertFalse(result["success"])
        self.assertIn("ไม่พบ", result["error"])

    def test_add_valid_product_succeeds(self):
        from shopee_engine.seo_engine import add_product_to_article, get_article_product_count
        db = _make_db(itemids=[1001])
        # Add product 1002 to products table
        con = duckdb.connect(db)
        con.execute("INSERT INTO products VALUES (1002, 102, 'New Product', 600, '', "
                    "'https://shopee.co.th/product/102/1002', '', 10)")
        con.close()
        with _patch_db(db), _patch_aff():
            result = add_product_to_article("test-article", 1002)
        self.assertTrue(result["success"], result)
        with _patch_db(db):
            count = get_article_product_count("test-article")
        self.assertEqual(count, 2)

    def test_add_product_appended_at_end_by_default(self):
        from shopee_engine.seo_engine import add_product_to_article
        db = _make_db(itemids=[1001])
        con = duckdb.connect(db)
        con.execute("INSERT INTO products VALUES (1002, 102, 'New', 400, '', "
                    "'https://shopee.co.th/product/102/1002', '', 10)")
        con.close()
        with _patch_db(db), _patch_aff():
            result = add_product_to_article("test-article", 1002)
        self.assertEqual(result["rank_in_article"], 2)


# ---------------------------------------------------------------------------
# 7. remove_product re-ranks remaining products
# ---------------------------------------------------------------------------

class TestRemoveProduct(unittest.TestCase):

    def test_remove_middle_product_reranks(self):
        from shopee_engine.seo_engine import remove_product_from_article
        db = _make_db(itemids=[1001, 1002, 1003])
        # Add 1003 to products table too
        con = duckdb.connect(db)
        con.execute("INSERT INTO products VALUES (1003, 103, 'P3', 400, '', '', '', 10)")
        con.close()
        with _patch_db(db), _patch_aff():
            result = remove_product_from_article("test-article", 1002)
        self.assertTrue(result["success"], result)

        con2 = duckdb.connect(db, read_only=True)
        ranks = con2.execute(
            "SELECT itemid, rank_in_article FROM seo_article_products "
            "WHERE article_id='test-article' ORDER BY rank_in_article"
        ).fetchall()
        con2.close()
        self.assertEqual([r[1] for r in ranks], [1, 2])

    def test_cannot_remove_last_product(self):
        from shopee_engine.seo_engine import remove_product_from_article
        db = _make_db(itemids=[1001])
        with _patch_db(db), _patch_aff():
            result = remove_product_from_article("test-article", 1001)
        self.assertFalse(result["success"])
        self.assertIn("สุดท้าย", result["error"])

    def test_remove_nonexistent_product_fails(self):
        from shopee_engine.seo_engine import remove_product_from_article
        db = _make_db(itemids=[1001])
        with _patch_db(db), _patch_aff():
            result = remove_product_from_article("test-article", 9999)
        self.assertFalse(result["success"])


# ---------------------------------------------------------------------------
# 8. replace_product preserves rank, prevents same-id replace
# ---------------------------------------------------------------------------

class TestReplaceProduct(unittest.TestCase):

    def test_replace_preserves_rank(self):
        from shopee_engine.seo_engine import replace_product_in_article
        db = _make_db(itemids=[1001, 1002])
        con = duckdb.connect(db)
        con.execute("INSERT INTO products VALUES (1003, 103, 'P3', 400, '', "
                    "'https://shopee.co.th/product/103/1003', '', 10)")
        con.close()
        with _patch_db(db), _patch_aff():
            result = replace_product_in_article("test-article", 1001, 1003)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["rank_in_article"], 1)

        con2 = duckdb.connect(db, read_only=True)
        row = con2.execute(
            "SELECT itemid, rank_in_article FROM seo_article_products "
            "WHERE article_id='test-article' AND itemid=1003"
        ).fetchone()
        con2.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 1)

    def test_replace_same_itemid_fails(self):
        from shopee_engine.seo_engine import replace_product_in_article
        db = _make_db(itemids=[1001])
        with _patch_db(db), _patch_aff():
            result = replace_product_in_article("test-article", 1001, 1001)
        self.assertFalse(result["success"])

    def test_replace_with_existing_article_product_fails(self):
        from shopee_engine.seo_engine import replace_product_in_article
        db = _make_db(itemids=[1001, 1002])
        with _patch_db(db), _patch_aff():
            result = replace_product_in_article("test-article", 1001, 1002)
        self.assertFalse(result["success"])
        self.assertIn("มีอยู่", result["error"])


# ---------------------------------------------------------------------------
# 9. requires_republish flag set for published articles
# ---------------------------------------------------------------------------

class TestRequiresRepublish(unittest.TestCase):

    def test_edit_on_published_article_sets_requires_republish(self):
        from shopee_engine.seo_engine import edit_article_field
        db = _make_db(status="published")
        with _patch_db(db):
            result = edit_article_field("test-article", "meta_description", "New meta", "test")
        self.assertTrue(result["success"])
        self.assertTrue(result["requires_republish"])

    def test_edit_on_draft_does_not_require_republish(self):
        from shopee_engine.seo_engine import edit_article_field
        db = _make_db(status="draft")
        with _patch_db(db):
            result = edit_article_field("test-article", "meta_description", "New meta", "test")
        self.assertTrue(result["success"])
        self.assertFalse(result["requires_republish"])


# ---------------------------------------------------------------------------
# 10. Product changes demote article status
# ---------------------------------------------------------------------------

class TestProductChangeDemotes(unittest.TestCase):

    def test_add_product_demotes_reviewed_article(self):
        from shopee_engine.seo_engine import add_product_to_article, get_article
        db = _make_db(status="reviewed", itemids=[1001])
        con = duckdb.connect(db)
        con.execute("INSERT INTO products VALUES (1002, 102, 'P2', 400, '', "
                    "'https://shopee.co.th/product/102/1002', '', 10)")
        con.close()
        with _patch_db(db), _patch_aff():
            result = add_product_to_article("test-article", 1002)
        self.assertTrue(result["success"])
        self.assertTrue(result["demoted_to_draft"])
        with _patch_db(db):
            article = get_article("test-article")
        self.assertEqual(article["status"], "draft")

    def test_remove_product_demotes_published_article(self):
        from shopee_engine.seo_engine import get_article, remove_product_from_article
        db = _make_db(status="published", itemids=[1001, 1002])
        with _patch_db(db), _patch_aff():
            result = remove_product_from_article("test-article", 1001)
        self.assertTrue(result["success"])
        self.assertTrue(result["demoted_to_draft"])
        with _patch_db(db):
            article = get_article("test-article")
        self.assertEqual(article["status"], "draft")


# ---------------------------------------------------------------------------
# 11. get_article_history returns empty list when no revisions
# ---------------------------------------------------------------------------

class TestHistoryEmpty(unittest.TestCase):

    def test_history_empty_for_new_article(self):
        from shopee_engine.seo_engine import get_article_history
        db = _make_db()
        with _patch_db(db):
            history = get_article_history("test-article")
        self.assertEqual(history, [])


if __name__ == "__main__":
    unittest.main()
