"""
SQLite layer for Hanoi (VietLao) lottery.
Adds hanoi_draws table to the shared lao_lotto.db.

hanoi_draws columns:
  draw_date, draw_date_be, five_digit, top_2, top_3, last_3, last_2
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "db" / "lao_lotto.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hanoi_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_date    TEXT UNIQUE NOT NULL,
    draw_date_be TEXT,
    five_digit   TEXT NOT NULL,
    top_2        TEXT NOT NULL DEFAULT '',
    top_3        TEXT NOT NULL DEFAULT '',
    last_3       TEXT NOT NULL DEFAULT '',
    last_2       TEXT NOT NULL DEFAULT '',
    scraped_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);
CREATE INDEX IF NOT EXISTS idx_hanoi_date  ON hanoi_draws(draw_date);
CREATE INDEX IF NOT EXISTS idx_hanoi_last2 ON hanoi_draws(last_2);
"""

DIGIT_COL = {
    "bottom_2": "last_2",
    "last_3":   "last_3",
    "top_2":    "top_2",
    "top_3":    "top_3",
}

DIGIT_LABEL = {
    "bottom_2": "2 ตัวล่าง",
    "last_3":   "3 ตัวล่าง",
    "top_2":    "2 ตัวบน",
    "top_3":    "3 ตัวบน",
}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def upsert(df: pd.DataFrame) -> int:
    init()
    inserted = 0
    with _conn() as conn:
        for _, row in df.iterrows():
            five = str(row["five_digit"]).zfill(5)
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO hanoi_draws
                  (draw_date, draw_date_be, five_digit, top_2, top_3, last_3, last_2)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    str(row.get("date", row.get("draw_date", "")))[:10],
                    str(row.get("date_be", row.get("draw_date_be", ""))),
                    five,
                    five[:2],
                    five[:3],
                    str(row["last_3"]).zfill(3),
                    str(row["last_2"]).zfill(2),
                ),
            )
            inserted += cur.rowcount
    return inserted


def load() -> pd.DataFrame:
    init()
    with _conn() as conn:
        df = pd.read_sql(
            "SELECT draw_date, draw_date_be, five_digit, top_2, top_3, last_3, last_2 "
            "FROM hanoi_draws ORDER BY draw_date DESC",
            conn,
        )
    if df.empty:
        return df
    df["draw_date"] = pd.to_datetime(df["draw_date"])
    for col, w in [("five_digit", 5), ("top_3", 3), ("last_3", 3), ("top_2", 2), ("last_2", 2)]:
        df[col] = df[col].astype(str).str.zfill(w)
    return df


def meta() -> dict:
    init()
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) total, MAX(draw_date) latest, "
            "MIN(draw_date) earliest, MAX(scraped_at) last_scraped "
            "FROM hanoi_draws"
        ).fetchone()
    return {k: row[k] for k in ("total", "latest", "earliest", "last_scraped")}


def is_stale(hours: int = 30) -> bool:
    m = meta()
    if not m["total"] or not m["last_scraped"]:
        return True
    try:
        last = datetime.fromisoformat(m["last_scraped"]).replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - last).total_seconds() > hours * 3600
    except ValueError:
        return True


def row_count() -> int:
    init()
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM hanoi_draws").fetchone()[0]


def clear() -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM hanoi_draws")
