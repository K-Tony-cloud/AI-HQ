"""
Thai Content Intelligence — Self-Learning Loop.

DuckDB-backed system that tracks which patterns get the best engagement.
Automatically promotes high-performing patterns and demotes poor ones.

Tables:
  pattern_performance — per-pattern use + engagement tracking
  content_ab_test     — A/B test records for content variants

Usage:
  record_pattern_use("h_cb_01", "comment_bait", post_id="xxx")
  update_pattern_performance("h_cb_01", reactions=42, comments=15, shares=3)
  weight_overrides = get_weight_overrides("comment_bait")
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        import os
        from pathlib import Path as P
        data_dir = P(os.getenv("DATA_DIR", str(P(__file__).parent.parent.parent / "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        _DB_PATH = data_dir / "shopee.duckdb"
    return _DB_PATH


def _connect():
    import duckdb
    return duckdb.connect(str(_get_db_path()), read_only=False)


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS pattern_performance (
    pattern_id      TEXT NOT NULL,
    post_type       TEXT NOT NULL,
    pattern_text    TEXT DEFAULT '',
    times_used      INTEGER DEFAULT 0,
    total_reactions INTEGER DEFAULT 0,
    total_comments  INTEGER DEFAULT 0,
    total_shares    INTEGER DEFAULT 0,
    total_reach     INTEGER DEFAULT 0,
    avg_engagement  DOUBLE  DEFAULT 0.0,
    weight_override DOUBLE  DEFAULT 1.0,
    last_used_at    TEXT    DEFAULT '',
    last_updated_at TEXT    DEFAULT '',
    PRIMARY KEY (pattern_id)
);

CREATE TABLE IF NOT EXISTS content_ab_test (
    test_id         TEXT NOT NULL,
    post_id         TEXT DEFAULT '',
    variant_a_id    TEXT DEFAULT '',
    variant_b_id    TEXT DEFAULT '',
    variant_a_score DOUBLE DEFAULT 0.0,
    variant_b_score DOUBLE DEFAULT 0.0,
    winner          TEXT DEFAULT '',
    created_at      TEXT DEFAULT '',
    resolved_at     TEXT DEFAULT '',
    PRIMARY KEY (test_id)
);
"""


def init_schema() -> None:
    """Create tables if they don't exist."""
    try:
        con = _connect()
        con.execute(_INIT_SQL)
        con.close()
        logger.debug("[learning_loop] Schema initialized")
    except Exception as exc:
        logger.warning("[learning_loop] Schema init failed: %s", exc)


def seed_patterns() -> int:
    """
    Seed the pattern_performance table with all known patterns at weight 1.0.
    Skips patterns that already exist. Returns count inserted.
    """
    from .pattern_library import list_all_patterns
    patterns = list_all_patterns()
    now = datetime.utcnow().isoformat()
    inserted = 0

    try:
        con = _connect()
        init_schema()
        existing = {row[0] for row in con.execute("SELECT pattern_id FROM pattern_performance").fetchall()}

        for p in patterns:
            if p.id not in existing:
                con.execute(
                    """INSERT INTO pattern_performance
                       (pattern_id, post_type, pattern_text, weight_override, last_updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    [p.id, _infer_post_type(p.id), p.text, p.weight, now],
                )
                inserted += 1

        con.close()
        logger.info("[learning_loop] Seeded %d patterns", inserted)
    except Exception as exc:
        logger.warning("[learning_loop] Seed failed: %s", exc)

    return inserted


def _infer_post_type(pattern_id: str) -> str:
    """Infer post_type from pattern ID prefix."""
    if "_cb_" in pattern_id or "_cbp_" in pattern_id or "_cbg_" in pattern_id:
        return "comment_bait"
    if "_wp_" in pattern_id:
        return "weird_product"
    if "_nos_" in pattern_id:
        return "nostalgia"
    if "_vc_" in pattern_id:
        return "visual_curiosity"
    if "_tr_" in pattern_id:
        return "trending"
    if "_aff_" in pattern_id:
        return "affiliate"
    return "comment_bait"


# ─────────────────────────────────────────────────────────────────────────────
# Record usage
# ─────────────────────────────────────────────────────────────────────────────

def record_pattern_use(pattern_id: str, post_type: str,
                       pattern_text: str = "", post_id: str = "") -> None:
    """Record that a pattern was used in a post."""
    now = datetime.utcnow().isoformat()
    try:
        con = _connect()
        existing = con.execute(
            "SELECT pattern_id FROM pattern_performance WHERE pattern_id = ?",
            [pattern_id]
        ).fetchone()

        if existing:
            con.execute(
                """UPDATE pattern_performance
                   SET times_used = times_used + 1,
                       last_used_at = ?
                   WHERE pattern_id = ?""",
                [now, pattern_id],
            )
        else:
            con.execute(
                """INSERT INTO pattern_performance
                   (pattern_id, post_type, pattern_text, times_used, last_used_at, last_updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)""",
                [pattern_id, post_type, pattern_text, now, now],
            )
        con.close()
    except Exception as exc:
        logger.debug("[learning_loop] record_pattern_use failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Update performance from Facebook metrics
# ─────────────────────────────────────────────────────────────────────────────

def update_pattern_performance(
    pattern_id: str,
    reactions: int = 0,
    comments: int = 0,
    shares: int = 0,
    reach: int = 0,
) -> None:
    """
    Update cumulative engagement metrics for a pattern.
    Called after syncing Facebook post performance data.
    """
    if not any([reactions, comments, shares, reach]):
        return

    engagement_score = (reactions * 1.0) + (comments * 3.0) + (shares * 2.0)
    now = datetime.utcnow().isoformat()

    try:
        con = _connect()
        con.execute(
            """UPDATE pattern_performance
               SET total_reactions = total_reactions + ?,
                   total_comments  = total_comments + ?,
                   total_shares    = total_shares + ?,
                   total_reach     = total_reach + ?,
                   last_updated_at = ?
               WHERE pattern_id = ?""",
            [reactions, comments, shares, reach, now, pattern_id],
        )

        # Recalculate avg_engagement
        row = con.execute(
            "SELECT times_used, total_reactions, total_comments, total_shares FROM pattern_performance WHERE pattern_id = ?",
            [pattern_id]
        ).fetchone()

        if row and row[0] > 0:
            times_used = row[0]
            total_score = (row[1] * 1.0) + (row[2] * 3.0) + (row[3] * 2.0)
            avg = total_score / times_used
            con.execute(
                "UPDATE pattern_performance SET avg_engagement = ? WHERE pattern_id = ?",
                [avg, pattern_id],
            )

        con.close()
        logger.debug("[learning_loop] Updated %s: +%d reactions +%d comments +%d shares",
                     pattern_id, reactions, comments, shares)
    except Exception as exc:
        logger.warning("[learning_loop] update_pattern_performance failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Weight adjustment
# ─────────────────────────────────────────────────────────────────────────────

def promote_winning_patterns(min_uses: int = 3, percentile: float = 0.75) -> list[str]:
    """
    Boost weight for patterns in the top percentile of avg_engagement.
    Only runs on patterns used at least min_uses times.
    Returns list of promoted pattern IDs.
    """
    promoted: list[str] = []
    try:
        con = _connect()
        rows = con.execute(
            """SELECT pattern_id, avg_engagement
               FROM pattern_performance
               WHERE times_used >= ?
               ORDER BY avg_engagement DESC""",
            [min_uses]
        ).fetchall()

        if not rows:
            con.close()
            return []

        cutoff_idx = int(len(rows) * (1 - percentile))
        top_ids = {r[0] for r in rows[:max(1, cutoff_idx)]}

        now = datetime.utcnow().isoformat()
        for pid in top_ids:
            current = con.execute(
                "SELECT weight_override FROM pattern_performance WHERE pattern_id = ?", [pid]
            ).fetchone()
            new_weight = min((current[0] if current else 1.0) * 1.2, 3.0)
            con.execute(
                """UPDATE pattern_performance
                   SET weight_override = ?, last_updated_at = ?
                   WHERE pattern_id = ?""",
                [new_weight, now, pid],
            )
            promoted.append(pid)

        con.close()
        logger.info("[learning_loop] Promoted %d patterns", len(promoted))
    except Exception as exc:
        logger.warning("[learning_loop] promote_winning_patterns failed: %s", exc)

    return promoted


def demote_failing_patterns(min_uses: int = 5, percentile: float = 0.25) -> list[str]:
    """
    Reduce weight for patterns in the bottom percentile of avg_engagement.
    Only runs on patterns used at least min_uses times.
    Returns list of demoted pattern IDs.
    """
    demoted: list[str] = []
    try:
        con = _connect()
        rows = con.execute(
            """SELECT pattern_id, avg_engagement
               FROM pattern_performance
               WHERE times_used >= ?
               ORDER BY avg_engagement ASC""",
            [min_uses]
        ).fetchall()

        if not rows:
            con.close()
            return []

        cutoff_idx = int(len(rows) * percentile)
        bottom_ids = {r[0] for r in rows[:max(1, cutoff_idx)]}

        now = datetime.utcnow().isoformat()
        for pid in bottom_ids:
            current = con.execute(
                "SELECT weight_override FROM pattern_performance WHERE pattern_id = ?", [pid]
            ).fetchone()
            new_weight = max((current[0] if current else 1.0) * 0.8, 0.2)
            con.execute(
                """UPDATE pattern_performance
                   SET weight_override = ?, last_updated_at = ?
                   WHERE pattern_id = ?""",
                [new_weight, now, pid],
            )
            demoted.append(pid)

        con.close()
        logger.info("[learning_loop] Demoted %d patterns", len(demoted))
    except Exception as exc:
        logger.warning("[learning_loop] demote_failing_patterns failed: %s", exc)

    return demoted


# ─────────────────────────────────────────────────────────────────────────────
# Query API
# ─────────────────────────────────────────────────────────────────────────────

def get_weight_overrides(post_type: str | None = None) -> dict[str, float]:
    """
    Return {pattern_id: weight_override} for all learned patterns.
    Used by humanize_engine to apply learned weights.
    """
    try:
        con = _connect()
        if post_type:
            rows = con.execute(
                "SELECT pattern_id, weight_override FROM pattern_performance WHERE post_type = ?",
                [post_type]
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT pattern_id, weight_override FROM pattern_performance"
            ).fetchall()
        con.close()
        return {r[0]: r[1] for r in rows}
    except Exception as exc:
        logger.debug("[learning_loop] get_weight_overrides failed: %s", exc)
        return {}


def get_top_patterns(post_type: str, n: int = 5) -> list[dict]:
    """Return the top N best-performing patterns for a post type."""
    try:
        con = _connect()
        rows = con.execute(
            """SELECT pattern_id, pattern_text, times_used, avg_engagement, weight_override
               FROM pattern_performance
               WHERE post_type = ? AND times_used > 0
               ORDER BY avg_engagement DESC
               LIMIT ?""",
            [post_type, n]
        ).fetchall()
        con.close()
        return [
            {
                "id": r[0], "text": r[1], "uses": r[2],
                "avg_engagement": r[3], "weight": r[4],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("[learning_loop] get_top_patterns failed: %s", exc)
        return []


def get_learning_summary() -> dict:
    """Return a summary of the learning loop state."""
    try:
        con = _connect()
        total = con.execute("SELECT COUNT(*) FROM pattern_performance").fetchone()[0]
        used = con.execute("SELECT COUNT(*) FROM pattern_performance WHERE times_used > 0").fetchone()[0]
        top = con.execute(
            "SELECT pattern_id, avg_engagement FROM pattern_performance ORDER BY avg_engagement DESC LIMIT 3"
        ).fetchall()
        bot = con.execute(
            "SELECT pattern_id, avg_engagement FROM pattern_performance WHERE times_used >= 3 ORDER BY avg_engagement ASC LIMIT 3"
        ).fetchall()
        con.close()
        return {
            "total_patterns": total,
            "patterns_used": used,
            "top_3": [{"id": r[0], "avg_engagement": r[1]} for r in top],
            "bottom_3": [{"id": r[0], "avg_engagement": r[1]} for r in bot],
        }
    except Exception as exc:
        logger.debug("[learning_loop] get_learning_summary failed: %s", exc)
        return {"error": str(exc)}


def run_weekly_adjustment() -> dict:
    """
    Run promote + demote cycle. Call this from the weekly_report scheduler job.
    Returns summary of changes.
    """
    init_schema()
    promoted = promote_winning_patterns()
    demoted = demote_failing_patterns()
    summary = get_learning_summary()
    return {
        "promoted": promoted,
        "demoted": demoted,
        "summary": summary,
    }
