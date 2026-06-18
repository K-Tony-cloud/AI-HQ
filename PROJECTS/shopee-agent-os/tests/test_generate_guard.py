"""
Tests for fb_generate_daily_schedule() guard logic.

Verifies that failed/cancelled posts do NOT block regeneration.
generate_today_content is imported locally inside fb_generate_daily_schedule,
so we patch it at shopee_engine.editorial_engine.generate_today_content.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(path: str) -> None:
    import duckdb
    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE scheduled_posts (
            id          INTEGER,
            created_at  TEXT,
            message     TEXT,
            image_url   TEXT DEFAULT '',
            link        TEXT DEFAULT '',
            post_type   TEXT DEFAULT 'manual',
            publish_at  TEXT,
            status      TEXT DEFAULT 'pending',
            post_id     TEXT DEFAULT '',
            note        TEXT DEFAULT ''
        )
    """)
    con.close()


def _insert_posts(path: str, date_str: str, status: str, count: int = 3) -> None:
    import duckdb
    con = duckdb.connect(path)
    for i in range(count):
        con.execute(
            "INSERT INTO scheduled_posts "
            "(id, created_at, message, publish_at, status, note, post_type) "
            "VALUES (?,?,?,?,?,?,?)",
            [i + 1, datetime.now().isoformat(), f"test post {i}",
             f"{date_str} 08:00:00", status, f"auto:{date_str}", "comment_bait"],
        )
    con.close()


def _active_count(path: str, date_str: str) -> int:
    import duckdb
    con = duckdb.connect(path, read_only=True)
    n = con.execute(
        "SELECT COUNT(*) FROM scheduled_posts "
        "WHERE DATE(publish_at) = ? AND status NOT IN ('failed','deleted','cancelled')",
        [date_str],
    ).fetchone()[0]
    con.close()
    return n


_FAKE_CONTENT = {
    "posts": [
        {"caption": f"post {i}", "caption_raw": f"post {i}", "type": "comment_bait"}
        for i in range(3)
    ],
    "override_active": False,
}

_DB_PATCHES = lambda db_path: [
    patch("shopee_engine.config.DB_PATH", db_path),
    patch("shopee_engine.config.config.db_path", __import__("pathlib").Path(db_path)),
]


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_guard_skips_when_3_pending_posts_exist():
    """Guard returns skipped=True when 3 pending posts already exist for the date."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.duckdb")
        _make_db(db)
        date_str = "2099-01-01"
        _insert_posts(db, date_str, status="pending", count=3)
        assert _active_count(db, date_str) == 3

        with patch("shopee_engine.config.DB_PATH", db), \
             patch("shopee_engine.config.config.db_path", __import__("pathlib").Path(db)):
            import shopee_engine.insights_engine as ie
            result = ie.fb_generate_daily_schedule(for_date=datetime(2099, 1, 1))

        assert result.get("skipped") is True, f"Expected skipped, got: {result}"
        assert "3" in result.get("reason", "")


def test_guard_does_not_skip_when_3_failed_posts_exist():
    """Failed posts must NOT count — regeneration should proceed past the guard."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.duckdb")
        _make_db(db)
        date_str = "2099-01-02"
        _insert_posts(db, date_str, status="failed", count=3)
        assert _active_count(db, date_str) == 0, "No active posts should exist"

        with patch("shopee_engine.config.DB_PATH", db), \
             patch("shopee_engine.config.config.db_path", __import__("pathlib").Path(db)), \
             patch("shopee_engine.editorial_engine.generate_today_content",
                   return_value=_FAKE_CONTENT):
            import shopee_engine.insights_engine as ie
            result = ie.fb_generate_daily_schedule(for_date=datetime(2099, 1, 2))

        assert result.get("skipped") is not True, f"Should NOT be skipped, got: {result}"


def test_guard_does_not_skip_when_3_cancelled_posts_exist():
    """Cancelled posts must not count toward the quota."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.duckdb")
        _make_db(db)
        date_str = "2099-01-03"
        _insert_posts(db, date_str, status="cancelled", count=3)
        assert _active_count(db, date_str) == 0

        with patch("shopee_engine.config.DB_PATH", db), \
             patch("shopee_engine.config.config.db_path", __import__("pathlib").Path(db)), \
             patch("shopee_engine.editorial_engine.generate_today_content",
                   return_value=_FAKE_CONTENT):
            import shopee_engine.insights_engine as ie
            result = ie.fb_generate_daily_schedule(for_date=datetime(2099, 1, 3))

        assert result.get("skipped") is not True, f"Should NOT be skipped, got: {result}"


def test_guard_counts_posted_as_active():
    """Already published posts count toward quota — prevents double-posting."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.duckdb")
        _make_db(db)
        date_str = "2099-01-04"
        _insert_posts(db, date_str, status="posted", count=3)
        assert _active_count(db, date_str) == 3

        with patch("shopee_engine.config.DB_PATH", db), \
             patch("shopee_engine.config.config.db_path", __import__("pathlib").Path(db)):
            import shopee_engine.insights_engine as ie
            result = ie.fb_generate_daily_schedule(for_date=datetime(2099, 1, 4))

        assert result.get("skipped") is True, f"Already posted — should skip, got: {result}"
