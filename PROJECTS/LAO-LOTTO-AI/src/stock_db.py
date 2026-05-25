"""
SQLite layer for Thai Stock lottery (หวยหุ้นไทย).
Derives last-2-digit lottery numbers from SET index (^SET.BK) OHLC data.
Adds stock_draws table to the shared lao_lotto.db.

Sessions per trading day:
  open  → เปิดเช้า  (derived from daily Open price)
  close → ปิดบ่าย  (derived from daily Close price)

stock_draws columns:
  draw_date, session, set_value, last_2, top_2
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "db" / "lao_lotto.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_date    TEXT NOT NULL,
    session      TEXT NOT NULL,
    set_value    REAL NOT NULL,
    last_2       TEXT NOT NULL DEFAULT '',
    top_2        TEXT NOT NULL DEFAULT '',
    fetched_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(draw_date, session)
);
CREATE INDEX IF NOT EXISTS idx_stock_date    ON stock_draws(draw_date);
CREATE INDEX IF NOT EXISTS idx_stock_session ON stock_draws(session);
"""

SESSION_LABEL = {
    "open":  "เปิดเช้า",
    "close": "ปิดบ่าย",
}

DIGIT_COL = {
    "bottom_2": "last_2",
    "top_2":    "top_2",
}

DIGIT_LABEL = {
    "bottom_2": "2 ตัวล่าง",
    "top_2":    "2 ตัวบน",
}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _derive(value: float) -> tuple[str, str]:
    """Return (last_2, top_2) from a SET index float value."""
    v = int(round(value))
    last_2 = str(v % 100).zfill(2)
    top_2  = str((v // 100) % 100).zfill(2)
    return last_2, top_2


def upsert(df: pd.DataFrame) -> int:
    """
    df must have columns: draw_date (date/str), session (str), set_value (float).
    Returns count of newly inserted rows.
    """
    init()
    inserted = 0
    with _conn() as conn:
        for _, row in df.iterrows():
            last_2, top_2 = _derive(float(row["set_value"]))
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO stock_draws
                  (draw_date, session, set_value, last_2, top_2)
                VALUES (?,?,?,?,?)
                """,
                (
                    str(row["draw_date"])[:10],
                    str(row["session"]),
                    float(row["set_value"]),
                    last_2,
                    top_2,
                ),
            )
            inserted += cur.rowcount
    return inserted


def load(session: str | None = None) -> pd.DataFrame:
    init()
    where = f"WHERE session = '{session}'" if session else ""
    with _conn() as conn:
        df = pd.read_sql(
            f"SELECT draw_date, session, set_value, last_2, top_2 "
            f"FROM stock_draws {where} ORDER BY draw_date DESC, session",
            conn,
        )
    if df.empty:
        return df
    df["draw_date"] = pd.to_datetime(df["draw_date"])
    df["last_2"] = df["last_2"].astype(str).str.zfill(2)
    df["top_2"]  = df["top_2"].astype(str).str.zfill(2)
    return df


def meta() -> dict:
    init()
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) total, MAX(draw_date) latest, "
            "MIN(draw_date) earliest, MAX(fetched_at) last_scraped "
            "FROM stock_draws"
        ).fetchone()
    return {k: row[k] for k in ("total", "latest", "earliest", "last_scraped")}


def is_stale(hours: int = 20) -> bool:
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
        return conn.execute("SELECT COUNT(*) FROM stock_draws").fetchone()[0]


def clear() -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM stock_draws")
