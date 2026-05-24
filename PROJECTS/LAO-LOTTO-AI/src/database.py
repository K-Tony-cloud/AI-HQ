"""
SQLite layer for LAO-LOTTO-AI.
Auto-creates the DB and schema on first use.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "db" / "lao_lotto.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_date    TEXT UNIQUE NOT NULL,   -- ISO-8601 date YYYY-MM-DD
    draw_date_be TEXT,                   -- original Buddhist Era string DD/MM/YYYY
    six_digit    TEXT NOT NULL,
    last_3       TEXT NOT NULL,
    last_2       TEXT NOT NULL,
    scraped_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_date  ON draws(draw_date);
CREATE INDEX IF NOT EXISTS idx_last2 ON draws(last_2);
CREATE INDEX IF NOT EXISTS idx_last3 ON draws(last_3);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def upsert(df: pd.DataFrame) -> int:
    """Insert new rows from df; skip duplicates. Returns newly inserted count."""
    init()
    inserted = 0
    with _conn() as conn:
        for _, row in df.iterrows():
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO draws
                    (draw_date, draw_date_be, six_digit, last_3, last_2)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("date", row.get("draw_date", "")))[:10],
                    str(row.get("date_be", row.get("draw_date_be", ""))),
                    str(row["six_digit"]).zfill(6),
                    str(row["last_3"]).zfill(3),
                    str(row["last_2"]).zfill(2),
                ),
            )
            inserted += cur.rowcount
    return inserted


def load() -> pd.DataFrame:
    """Return all draws sorted newest-first with zero-padded strings."""
    init()
    with _conn() as conn:
        df = pd.read_sql(
            "SELECT draw_date, draw_date_be, six_digit, last_3, last_2 "
            "FROM draws ORDER BY draw_date DESC",
            conn,
        )
    if df.empty:
        return df
    df["draw_date"] = pd.to_datetime(df["draw_date"])
    df["six_digit"] = df["six_digit"].str.zfill(6)
    df["last_3"]    = df["last_3"].str.zfill(3)
    df["last_2"]    = df["last_2"].str.zfill(2)
    return df


def meta() -> dict:
    """Summary: total rows, latest/earliest date, last scrape time."""
    init()
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) total, MAX(draw_date) latest, "
            "MIN(draw_date) earliest, MAX(scraped_at) last_scraped "
            "FROM draws"
        ).fetchone()
    return {
        "total":        row["total"],
        "latest":       row["latest"],
        "earliest":     row["earliest"],
        "last_scraped": row["last_scraped"],
    }


def is_stale(hours: int = 20) -> bool:
    """True if the DB is empty or hasn't been scraped in `hours` hours."""
    m = meta()
    if not m["total"] or not m["last_scraped"]:
        return True
    try:
        last = datetime.fromisoformat(m["last_scraped"]).replace(tzinfo=timezone.utc)
        now  = datetime.now(tz=timezone.utc)
        return (now - last).total_seconds() > hours * 3600
    except ValueError:
        return True


def row_count() -> int:
    init()
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0]


def clear() -> None:
    """Delete all draw rows (keeps schema)."""
    with _conn() as conn:
        conn.execute("DELETE FROM draws")
