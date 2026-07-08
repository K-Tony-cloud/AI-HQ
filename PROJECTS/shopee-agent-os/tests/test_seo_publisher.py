"""Tests for Phase G: Review, Export, and Safe Publish Pipeline.

Covers all requirements from the Phase G spec:
  - Status transition validation
  - Review workflow (approve / return_to_draft)
  - Article exporter (frontmatter, prose sections, slug safety, collision, atomic write)
  - Pre-publish validation (placeholder detection, SITE_URL)
  - Git publish service (env check, allowlist, dry-run, full pipeline)
  - npm build failure handling
  - Refresh workflow (including published → reviewed demotion)
  - Unpublish pipeline
  - Concurrency lock

Run with: python -m pytest tests/test_seo_publisher.py -v
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Minimal DuckDB fixture
# ---------------------------------------------------------------------------

def _make_test_db() -> str:
    """Return db_path for a fresh test DB with SEO tables."""
    import duckdb
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)  # DuckDB must create the file fresh; mkstemp leaves an empty file it rejects
    con = duckdb.connect(path)
    # Create tables
    con.execute("""
        CREATE TABLE IF NOT EXISTS seo_articles (
            id INTEGER PRIMARY KEY,
            article_id VARCHAR UNIQUE NOT NULL,
            keyword VARCHAR NOT NULL,
            category VARCHAR DEFAULT '',
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
    con.execute("""
        CREATE TABLE IF NOT EXISTS seo_article_products (
            id INTEGER PRIMARY KEY,
            article_id VARCHAR NOT NULL,
            itemid BIGINT,
            shopid BIGINT,
            product_title VARCHAR DEFAULT '',
            sale_price BIGINT DEFAULT 0,
            image_link VARCHAR DEFAULT '',
            affiliate_link VARCHAR DEFAULT '',
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score DOUBLE DEFAULT 0,
            rank_in_article INTEGER DEFAULT 0,
            product_status VARCHAR DEFAULT 'active',
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS products (
            itemid BIGINT,
            shopid BIGINT,
            title VARCHAR,
            sale_price BIGINT,
            price BIGINT,
            item_sold INTEGER,
            item_rating DOUBLE,
            shop_rating DOUBLE,
            discount_percentage INTEGER,
            product_link VARCHAR,
            "product_short link" VARCHAR,
            image_link VARCHAR,
            stock INTEGER DEFAULT 10
        )
    """)
    con.close()
    return path


def _insert_article(db_path: str, article_id: str, status: str = "draft",
                    content: str = "A" * 600, keyword: str = "test keyword",
                    title: str = "Test Title", category: str = "Beauty") -> None:
    import duckdb
    # Use a hash-based id to avoid PRIMARY KEY conflicts across different article_ids in same DB
    row_id = abs(hash(article_id)) % 1_000_000 + 1
    con = duckdb.connect(db_path)
    con.execute("""
        INSERT INTO seo_articles
            (id, article_id, keyword, category, title, meta_description, content_md, status)
        VALUES (?, ?, ?, ?, ?, 'Meta description', ?, ?)
    """, [row_id, article_id, keyword, category, title, content, status])
    con.close()


def _insert_product(db_path: str, article_id: str, itemid: int = 1001) -> None:
    import duckdb
    con = duckdb.connect(db_path)
    con.execute("""
        INSERT INTO seo_article_products
            (id, article_id, itemid, shopid, product_title, sale_price,
             image_link, affiliate_link, affiliate_link_type, rank_in_article)
        VALUES (?, ?, ?, 999, 'Test Product', 599, 'http://img.test/1.jpg',
                'https://s.shopee.co.th/test', 'confirmed', 1)
    """, [itemid, article_id, itemid])
    con.close()


# ---------------------------------------------------------------------------
# 1. Status Transition Validation
# ---------------------------------------------------------------------------

class TestStatusTransitions(unittest.TestCase):

    def _t(self, from_s: str, to_s: str) -> dict:
        from shopee_engine.seo_engine import validate_status_transition
        return validate_status_transition(from_s, to_s)

    # Valid transitions
    def test_draft_to_reviewed(self):
        self.assertTrue(self._t("draft", "reviewed")["valid"])

    def test_reviewed_to_published(self):
        self.assertTrue(self._t("reviewed", "published")["valid"])

    def test_reviewed_to_draft(self):
        self.assertTrue(self._t("reviewed", "draft")["valid"])

    def test_published_to_reviewed(self):
        self.assertTrue(self._t("published", "reviewed")["valid"])

    def test_published_to_archived(self):
        self.assertTrue(self._t("published", "archived")["valid"])

    # Forbidden transitions
    def test_draft_to_published_blocked(self):
        r = self._t("draft", "published")
        self.assertFalse(r["valid"])
        self.assertIn("draft", r["error"])

    def test_archived_to_published_blocked(self):
        r = self._t("archived", "published")
        self.assertFalse(r["valid"])

    def test_draft_to_archived_blocked(self):
        self.assertFalse(self._t("draft", "archived")["valid"])

    def test_unknown_from_status(self):
        r = self._t("nonexistent", "draft")
        self.assertFalse(r["valid"])
        self.assertIn("nonexistent", r["error"])

    def test_unknown_to_status(self):
        r = self._t("draft", "limbo")
        self.assertFalse(r["valid"])

    def test_all_statuses_have_entry(self):
        from shopee_engine.seo_engine import ARTICLE_STATUSES, _ALLOWED_TRANSITIONS
        for s in ARTICLE_STATUSES:
            self.assertIn(s, _ALLOWED_TRANSITIONS)


# ---------------------------------------------------------------------------
# 2. Review Workflow
# ---------------------------------------------------------------------------

class TestReviewWorkflow(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def _patch(self):
        return patch("shopee_engine.seo_engine.config.db_path", Path(self.db_path))

    def test_approve_success(self):
        _insert_article(self.db_path, "art-1", status="draft")
        _insert_product(self.db_path, "art-1")
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-1", "approve")
        self.assertTrue(result["success"])
        self.assertEqual(result["to_status"], "reviewed")

    def test_approve_blocked_by_short_content(self):
        _insert_article(self.db_path, "art-short", status="draft", content="short")
        _insert_product(self.db_path, "art-short", itemid=2001)
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-short", "approve")
        self.assertFalse(result["success"])
        self.assertTrue(result.get("blocked"))
        self.assertTrue(len(result["errors"]) > 0)

    def test_approve_blocked_no_products(self):
        _insert_article(self.db_path, "art-noprod", status="draft")
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-noprod", "approve")
        self.assertFalse(result["success"])
        self.assertTrue(result.get("blocked"))

    def test_approve_wrong_status(self):
        _insert_article(self.db_path, "art-pub", status="published")
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-pub", "approve")
        self.assertFalse(result["success"])
        self.assertIn("published", result["error"].lower())

    def test_return_to_draft_success(self):
        _insert_article(self.db_path, "art-rev", status="reviewed")
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-rev", "return_to_draft", note="needs work")
        self.assertTrue(result["success"])
        self.assertEqual(result["to_status"], "draft")

    def test_return_to_draft_wrong_status(self):
        _insert_article(self.db_path, "art-draft2", status="draft")
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-draft2", "return_to_draft")
        self.assertFalse(result["success"])

    def test_invalid_action(self):
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("art-x", "publish_now")
        self.assertFalse(result["success"])

    def test_article_not_found(self):
        with self._patch():
            from shopee_engine import seo_engine
            result = seo_engine.review_article("nonexistent", "approve")
        self.assertFalse(result["success"])


# ---------------------------------------------------------------------------
# 3. Article Exporter
# ---------------------------------------------------------------------------

class TestArticleExporter(unittest.TestCase):

    def setUp(self):
        self.db_path  = _make_test_db()
        self.tmp_dir  = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        Path(self.db_path).unlink(missing_ok=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _patch_all(self):
        return (
            patch("shopee_engine.seo_engine.config.db_path", Path(self.db_path)),
            patch("shopee_engine.article_exporter._connect",
                  side_effect=lambda read_only=False: __import__("duckdb").connect(self.db_path, read_only=read_only)),
            patch("shopee_engine.article_exporter.get_articles_dir",
                  return_value=Path(self.tmp_dir)),
            patch("shopee_engine.article_exporter.get_site_url",
                  return_value="https://test.pages.dev"),
        )

    def test_export_success(self):
        _insert_article(self.db_path, "test-slug")
        _insert_product(self.db_path, "test-slug")
        p1, p2, p3, p4 = self._patch_all()
        with p1, p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("test-slug")
        self.assertTrue(result["success"], result.get("error"))
        self.assertIsNotNone(result["file_path"])
        self.assertTrue(Path(result["file_path"]).exists())

    def test_exported_frontmatter_fields(self):
        _insert_article(self.db_path, "test-slug2", keyword="เมาส์เกมมิ่ง", title="My Title")
        _insert_product(self.db_path, "test-slug2", itemid=1002)
        p1, p2, p3, p4 = self._patch_all()
        with p1, p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("test-slug2", as_status="published")
        content = Path(result["file_path"]).read_text(encoding="utf-8")
        self.assertIn('article_id: "test-slug2"', content)
        self.assertIn('article_status: "published"', content)
        self.assertIn('canonical: "https://test.pages.dev/test-slug2"', content)
        self.assertIn("published_at:", content)

    def test_thai_utf8_content(self):
        thai_title = "5 เมาส์เกมมิ่งที่ดีที่สุด"
        _insert_article(self.db_path, "thai-slug", title=thai_title, keyword="เมาส์เกมมิ่ง")
        _insert_product(self.db_path, "thai-slug", itemid=1003)
        p1, p2, p3, p4 = self._patch_all()
        with p1, p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("thai-slug")
        self.assertTrue(result["success"], result.get("error"))
        content = Path(result["file_path"]).read_text(encoding="utf-8")
        self.assertIn("เมาส์เกมมิ่ง", content)

    def test_path_traversal_blocked(self):
        p3 = patch("shopee_engine.article_exporter.get_articles_dir",
                   return_value=Path(self.tmp_dir))
        p4 = patch("shopee_engine.article_exporter.get_site_url",
                   return_value="https://test.pages.dev")
        with p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("../etc/passwd")
        self.assertFalse(result["success"])
        self.assertIn("Unsafe slug", result["error"])

    def test_duplicate_slug_same_article_ok(self):
        _insert_article(self.db_path, "dup-slug")
        _insert_product(self.db_path, "dup-slug", itemid=1004)
        # Write a file that belongs to the same article
        target = Path(self.tmp_dir) / "dup-slug.md"
        target.write_text('---\narticle_id: "dup-slug"\n---\n', encoding="utf-8")

        p1, p2, p3, p4 = self._patch_all()
        with p1, p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("dup-slug")
        self.assertTrue(result["success"])  # same article: overwrite is OK

    def test_duplicate_slug_different_article_blocked(self):
        _insert_article(self.db_path, "collision-slug")
        _insert_product(self.db_path, "collision-slug", itemid=1005)
        # File belongs to a DIFFERENT article
        target = Path(self.tmp_dir) / "collision-slug.md"
        target.write_text('---\narticle_id: "other-article"\n---\n', encoding="utf-8")

        p1, p2, p3, p4 = self._patch_all()
        with p1, p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("collision-slug")
        self.assertFalse(result["success"])
        self.assertIn("other-article", result["error"])

    def test_article_not_found(self):
        p2 = patch("shopee_engine.article_exporter._connect",
                   side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False)))
        p3 = patch("shopee_engine.article_exporter.get_articles_dir",
                   return_value=Path(self.tmp_dir))
        p4 = patch("shopee_engine.article_exporter.get_site_url",
                   return_value="https://test.pages.dev")
        with p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("ghost-article")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())

    def test_missing_site_url_blocked(self):
        _insert_article(self.db_path, "test-url")
        _insert_product(self.db_path, "test-url", itemid=1006)
        p1 = patch("shopee_engine.seo_engine.config.db_path", Path(self.db_path))
        p2 = patch("shopee_engine.article_exporter._connect",
                   side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False)))
        p3 = patch("shopee_engine.article_exporter.get_articles_dir",
                   return_value=Path(self.tmp_dir))
        p4 = patch.dict(os.environ, {"SITE_URL": ""})
        with p1, p2, p3, p4:
            from shopee_engine import article_exporter
            result = article_exporter.export_article("test-url")
        self.assertFalse(result["success"])
        self.assertIn("SITE_URL", result["error"])


# ---------------------------------------------------------------------------
# 4. Placeholder / Secret Detection
# ---------------------------------------------------------------------------

class TestPlaceholderDetection(unittest.TestCase):

    def test_todo_detected(self):
        from shopee_engine.article_exporter import detect_placeholders
        self.assertTrue(detect_placeholders("Some TODO item here"))

    def test_lorem_detected(self):
        from shopee_engine.article_exporter import detect_placeholders
        self.assertTrue(detect_placeholders("Lorem ipsum dolor sit amet"))

    def test_example_com_detected(self):
        from shopee_engine.article_exporter import detect_placeholders
        self.assertTrue(detect_placeholders("see http://example.com for details"))

    def test_article_id_placeholder_detected(self):
        from shopee_engine.article_exporter import detect_placeholders
        self.assertTrue(detect_placeholders('article_id: "{ARTICLE_ID}"'))

    def test_local_path_detected(self):
        from shopee_engine.article_exporter import detect_placeholders
        self.assertTrue(detect_placeholders("/Users/khomsanraksri/AI-HQ/data/test"))

    def test_clean_content_ok(self):
        from shopee_engine.article_exporter import detect_placeholders
        self.assertEqual(detect_placeholders("สินค้าราคาดีจาก Shopee\nไม่มี placeholder"), [])


# ---------------------------------------------------------------------------
# 5. Git Publish Service — Environment Checks
# ---------------------------------------------------------------------------

class TestGitEnvironmentCheck(unittest.TestCase):

    @patch("shopee_engine.git_publish_service._git")
    def test_correct_branch_and_remote_ok(self, mock_git):
        mock_git.side_effect = [
            MagicMock(stdout="main\n"),      # branch
            MagicMock(stdout="https://..."), # remote get-url
            MagicMock(stdout=""),            # diff --cached
        ]
        with patch.dict(os.environ, {"SEO_GIT_BRANCH": "main", "SEO_GIT_REMOTE": "origin"}):
            from shopee_engine import git_publish_service
            result = git_publish_service.check_git_environment()
        self.assertTrue(result["ok"])

    @patch("shopee_engine.git_publish_service._git")
    def test_wrong_branch_fails(self, mock_git):
        mock_git.side_effect = [
            MagicMock(stdout="feature-x\n"),
            MagicMock(stdout="https://..."),
            MagicMock(stdout=""),
        ]
        with patch.dict(os.environ, {"SEO_GIT_BRANCH": "main"}):
            from shopee_engine import git_publish_service
            result = git_publish_service.check_git_environment()
        self.assertFalse(result["ok"])
        self.assertTrue(any("branch" in e.lower() or "Wrong" in e for e in result["errors"]))

    @patch("shopee_engine.git_publish_service._git")
    def test_dirty_staging_area_fails(self, mock_git):
        mock_git.side_effect = [
            MagicMock(stdout="main\n"),
            MagicMock(stdout="https://..."),
            MagicMock(stdout="PROJECTS/some-file.py\n"),
        ]
        with patch.dict(os.environ, {"SEO_GIT_BRANCH": "main"}):
            from shopee_engine import git_publish_service
            result = git_publish_service.check_git_environment()
        self.assertFalse(result["ok"])


# ---------------------------------------------------------------------------
# 6. Staged-file Allowlist
# ---------------------------------------------------------------------------

class TestStagedAllowlist(unittest.TestCase):

    def test_article_file_allowed(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist(
            ["PROJECTS/seo-website/src/content/articles/test.md"]
        )
        self.assertEqual(bad, [])

    def test_env_file_blocked(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist([".env", "PROJECTS/seo-website/src/content/articles/ok.md"])
        self.assertIn(".env", bad)

    def test_db_file_blocked(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist(["PROJECTS/shopee-agent-os/data/shopee.duckdb"])
        self.assertEqual(len(bad), 1)

    def test_python_source_blocked(self):
        from shopee_engine.git_publish_service import _verify_staged_allowlist
        bad = _verify_staged_allowlist(["PROJECTS/shopee-agent-os/shopee_engine/seo_engine.py"])
        self.assertEqual(len(bad), 1)


# ---------------------------------------------------------------------------
# 7. Dry-Run Publish Pipeline
# ---------------------------------------------------------------------------

class TestDryRunPublish(unittest.TestCase):

    def _good_mocks(self, article_id: str, db_path: str, tmp_dir: str):
        """Return a context manager that sets up all mocks for a successful pipeline."""
        return (
            patch.dict(os.environ, {"SEO_PUBLISH_ENABLED": "false",
                                    "SEO_GIT_BRANCH": "main",
                                    "SEO_GIT_REMOTE": "origin",
                                    "SITE_URL": "https://test.pages.dev"}),
            patch("shopee_engine.git_publish_service._git", return_value=MagicMock(stdout="main\n")),
            patch("shopee_engine.git_publish_service.check_git_environment",
                  return_value={"ok": True, "branch": "main", "remote": "origin", "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.validate_article_for_publish",
                  return_value={"valid": True, "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.export_article",
                  return_value={"success": True, "file_path": f"{tmp_dir}/{article_id}.md", "article_id": article_id, "error": None}),
            patch("shopee_engine.git_publish_service.run_astro_build",
                  return_value={"success": True, "output": "14 pages built", "error": None}),
            patch("shopee_engine.git_publish_service.verify_article_in_build",
                  return_value={"success": True, "page_path": f"{tmp_dir}/dist/{article_id}/index.html", "in_sitemap": True, "error": None}),
            patch("shopee_engine.git_publish_service.delete_article_file", return_value=True),
            patch("shopee_engine.git_publish_service._connect",
                  side_effect=lambda **kw: __import__("duckdb").connect(db_path, read_only=kw.get("read_only", False))),
        )

    def setUp(self):
        self.db_path = _make_test_db()
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        Path(self.db_path).unlink(missing_ok=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dry_run_returns_no_commit_no_push(self):
        _insert_article(self.db_path, "my-article", status="reviewed")
        mocks = self._good_mocks("my-article", self.db_path, self.tmp_dir)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8]:
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_publish("my-article")
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertIsNone(result["commit_hash"])
        self.assertFalse(result["pushed"])

    def test_draft_status_blocked(self):
        _insert_article(self.db_path, "draft-art", status="draft")
        mocks = self._good_mocks("draft-art", self.db_path, self.tmp_dir)
        with mocks[0], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7], mocks[8]:
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_publish("draft-art")
        self.assertFalse(result["success"])
        self.assertIn("draft", result["error"].lower())

    def test_npm_build_failure_cleans_up(self):
        _insert_article(self.db_path, "build-fail", status="reviewed")
        with (
            patch.dict(os.environ, {"SEO_PUBLISH_ENABLED": "false", "SEO_GIT_BRANCH": "main",
                                    "SEO_GIT_REMOTE": "origin", "SITE_URL": "https://x.dev"}),
            patch("shopee_engine.git_publish_service.check_git_environment",
                  return_value={"ok": True, "branch": "main", "remote": "origin", "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.validate_article_for_publish",
                  return_value={"valid": True, "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.export_article",
                  return_value={"success": True, "file_path": "/tmp/fake.md", "article_id": "build-fail", "error": None}),
            patch("shopee_engine.git_publish_service.run_astro_build",
                  return_value={"success": False, "output": "Error: ...", "error": "npm run build failed"}),
            patch("shopee_engine.git_publish_service.delete_article_file") as mock_del,
            patch("shopee_engine.git_publish_service._connect",
                  side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False))),
        ):
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_publish("build-fail")
        self.assertFalse(result["success"])
        mock_del.assert_called_once_with("build-fail")


# ---------------------------------------------------------------------------
# 8. Full Publish Pipeline (mocked git push — success)
# ---------------------------------------------------------------------------

class TestFullPublishPipeline(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        Path(self.db_path).unlink(missing_ok=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_successful_publish_changes_status(self):
        _insert_article(self.db_path, "good-art", status="reviewed")
        git_responses = [
            MagicMock(stdout="main\n"),            # branch
            MagicMock(stdout="https://..."),       # remote get-url
            MagicMock(stdout=""),                  # diff --cached (clean)
            MagicMock(stdout=""),                  # git add
            MagicMock(stdout="PROJECTS/seo-website/src/content/articles/good-art.md\n"),  # staged files
            MagicMock(stdout=""),                  # git commit
            MagicMock(stdout="abc1234567890\n"),   # rev-parse HEAD
            MagicMock(stdout=""),                  # git push
        ]

        with (
            patch.dict(os.environ, {"SEO_PUBLISH_ENABLED": "true", "SEO_GIT_BRANCH": "main",
                                    "SEO_GIT_REMOTE": "origin", "SITE_URL": "https://x.dev"}),
            patch("shopee_engine.git_publish_service._git", side_effect=git_responses),
            patch("shopee_engine.git_publish_service.validate_article_for_publish",
                  return_value={"valid": True, "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.export_article",
                  return_value={"success": True,
                                "file_path": "/fake/root/PROJECTS/seo-website/src/content/articles/good-art.md",
                                "article_id": "good-art", "error": None}),
            patch("shopee_engine.git_publish_service.run_astro_build",
                  return_value={"success": True, "output": "", "error": None}),
            patch("shopee_engine.git_publish_service.verify_article_in_build",
                  return_value={"success": True, "page_path": "/dist/good-art/index.html",
                                "in_sitemap": True, "error": None}),
            patch("shopee_engine.git_publish_service._git_root",
                  return_value=Path("/fake/root")),
            patch("shopee_engine.git_publish_service._mark_published") as mock_mark,
            patch("shopee_engine.git_publish_service._connect",
                  side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False))),
        ):
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_publish("good-art")

        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["pushed"])
        mock_mark.assert_called_once()
        args = mock_mark.call_args[0]
        self.assertEqual(args[0], "good-art")
        self.assertIn("abc12345", args[1])

    def test_git_push_fail_keeps_reviewed(self):
        _insert_article(self.db_path, "push-fail", status="reviewed")

        git_responses = [
            MagicMock(stdout="main\n"),      # branch (check_git_environment)
            MagicMock(stdout="https://..."), # remote get-url
            MagicMock(stdout=""),            # diff --cached (clean, pre-flight)
            MagicMock(stdout=""),            # git add
            MagicMock(stdout="PROJECTS/seo-website/src/content/articles/push-fail.md\n"),  # diff --name-only
            MagicMock(stdout=""),            # git commit
            MagicMock(stdout="deadbeef\n"),  # rev-parse HEAD
            RuntimeError("Connection refused"),  # git push — RAISES
        ]

        with (
            patch.dict(os.environ, {"SEO_PUBLISH_ENABLED": "true", "SEO_GIT_BRANCH": "main",
                                    "SEO_GIT_REMOTE": "origin", "SITE_URL": "https://x.dev"}),
            patch("shopee_engine.git_publish_service._git", side_effect=git_responses),
            patch("shopee_engine.git_publish_service.validate_article_for_publish",
                  return_value={"valid": True, "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.export_article",
                  return_value={"success": True,
                                "file_path": "/fake/root/PROJECTS/seo-website/src/content/articles/push-fail.md",
                                "article_id": "push-fail", "error": None}),
            patch("shopee_engine.git_publish_service.run_astro_build",
                  return_value={"success": True, "output": "", "error": None}),
            patch("shopee_engine.git_publish_service.verify_article_in_build",
                  return_value={"success": True, "page_path": "/d/i.html", "in_sitemap": True, "error": None}),
            patch("shopee_engine.git_publish_service._git_root",
                  return_value=Path("/fake/root")),
            patch("shopee_engine.git_publish_service._mark_published") as mock_mark,
            patch("shopee_engine.git_publish_service._connect",
                  side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False))),
        ):
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_publish("push-fail")

        self.assertFalse(result["success"])
        self.assertIsNotNone(result["commit_hash"])  # commit hash reported
        mock_mark.assert_not_called()       # DB NOT updated to published

    def test_status_is_published_only_after_push(self):
        # Implicit: _mark_published is called only after push succeeds
        # Covered by test_successful_publish_changes_status (mock_mark called)
        # and test_git_push_fail_keeps_reviewed (mock_mark NOT called)
        pass


# ---------------------------------------------------------------------------
# 9. Concurrent Publish Lock
# ---------------------------------------------------------------------------

class TestConcurrentPublishLock(unittest.TestCase):

    def test_second_acquire_raises(self):
        from shopee_engine.git_publish_service import _PublishLock, _LOCK_FILE
        _LOCK_FILE.unlink(missing_ok=True)  # ensure clean state

        lock1 = _PublishLock()
        lock1.__enter__()
        try:
            with self.assertRaises(RuntimeError):
                lock2 = _PublishLock()
                lock2.__enter__()
        finally:
            lock1.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 10. Refresh Workflow
# ---------------------------------------------------------------------------

class TestRefreshWorkflow(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def _patch(self):
        return patch("shopee_engine.seo_engine.config.db_path", Path(self.db_path))

    def test_refresh_reviewed_article_stays_reviewed(self):
        _insert_article(self.db_path, "rev-art", status="reviewed")
        _insert_product(self.db_path, "rev-art")

        with self._patch():
            from discord_bot.services import seo_service
            result = seo_service.refresh_article("rev-art")

        self.assertTrue(result.get("success"), result)
        self.assertFalse(result.get("demoted_to_reviewed"))

    def test_refresh_published_article_demoted_to_reviewed(self):
        _insert_article(self.db_path, "pub-art", status="published")
        _insert_product(self.db_path, "pub-art")

        with self._patch():
            from discord_bot.services import seo_service
            result = seo_service.refresh_article("pub-art")

        self.assertTrue(result.get("success"), result)
        self.assertTrue(result.get("demoted_to_reviewed"))
        self.assertEqual(result.get("previous_status"), "published")

    def test_refresh_no_auto_republish(self):
        _insert_article(self.db_path, "pub-art2", status="published")
        _insert_product(self.db_path, "pub-art2", itemid=2002)

        with self._patch():
            from discord_bot.services import seo_service
            seo_service.refresh_article("pub-art2")

        # After refresh, status must be reviewed (not published)
        import duckdb
        con = duckdb.connect(self.db_path)
        row = con.execute(
            "SELECT status FROM seo_articles WHERE article_id = ?", ["pub-art2"]
        ).fetchone()
        con.close()
        self.assertEqual(row[0], "reviewed")


# ---------------------------------------------------------------------------
# 11. Unpublish Pipeline (dry-run)
# ---------------------------------------------------------------------------

class TestUnpublishPipeline(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_test_db()

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def test_unpublish_wrong_status_blocked(self):
        _insert_article(self.db_path, "draft-up", status="draft")
        with (
            patch.dict(os.environ, {"SEO_PUBLISH_ENABLED": "false", "SITE_URL": "https://x.dev"}),
            patch("shopee_engine.git_publish_service.check_git_environment",
                  return_value={"ok": True, "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service._connect",
                  side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False))),
        ):
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_unpublish("draft-up")
        self.assertFalse(result["success"])

    def test_unpublish_dry_run_does_not_change_db(self):
        _insert_article(self.db_path, "pub-up", status="published")
        with (
            patch.dict(os.environ, {"SEO_PUBLISH_ENABLED": "false", "SITE_URL": "https://x.dev"}),
            patch("shopee_engine.git_publish_service.check_git_environment",
                  return_value={"ok": True, "errors": [], "warnings": []}),
            patch("shopee_engine.git_publish_service.delete_article_file", return_value=True),
            patch("shopee_engine.git_publish_service.run_astro_build",
                  return_value={"success": True, "output": "", "error": None}),
            patch("shopee_engine.git_publish_service.export_article",
                  return_value={"success": True, "file_path": "/tmp/x.md", "article_id": "pub-up", "error": None}),
            patch("shopee_engine.git_publish_service._connect",
                  side_effect=lambda **kw: __import__("duckdb").connect(self.db_path, read_only=kw.get("read_only", False))),
        ):
            from shopee_engine import git_publish_service
            result = git_publish_service.safe_unpublish("pub-up")

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        # DB status must NOT have changed
        import duckdb
        con = duckdb.connect(self.db_path)
        row = con.execute("SELECT status FROM seo_articles WHERE article_id='pub-up'").fetchone()
        con.close()
        self.assertEqual(row[0], "published")  # dry-run: no change


if __name__ == "__main__":
    unittest.main(verbosity=2)
