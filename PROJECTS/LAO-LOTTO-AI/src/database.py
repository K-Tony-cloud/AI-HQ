"""
SQLite layer — auto-creates and migrates schema on first use.

draws columns:
  draw_date, draw_date_be, six_digit, last_3, last_2,
  last_4, top_2, top_3   ← added in v2

predictions columns:
  id, predicted_at, digit_type, rank, number, probability,
  actual, correct, checked_at
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "db" / "lao_lotto.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_date    TEXT UNIQUE NOT NULL,
    draw_date_be TEXT,
    six_digit    TEXT NOT NULL,
    last_3       TEXT NOT NULL DEFAULT '',
    last_2       TEXT NOT NULL DEFAULT '',
    last_4       TEXT NOT NULL DEFAULT '',
    top_2        TEXT NOT NULL DEFAULT '',
    top_3        TEXT NOT NULL DEFAULT '',
    scraped_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);
CREATE INDEX IF NOT EXISTS idx_date  ON draws(draw_date);
CREATE INDEX IF NOT EXISTS idx_last2 ON draws(last_2);

CREATE TABLE IF NOT EXISTS predictions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    predicted_at TEXT NOT NULL,
    digit_type   TEXT NOT NULL,
    rank         INTEGER NOT NULL,
    number       TEXT NOT NULL,
    probability  REAL NOT NULL,
    actual       TEXT,
    correct      INTEGER,
    checked_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_at   ON predictions(predicted_at);
CREATE INDEX IF NOT EXISTS idx_pred_type ON predictions(digit_type);
"""

# digit_type → column in draws table
DIGIT_COL = {
    "bottom_2": "last_2",
    "top_2":    "top_2",
    "last_3":   "last_3",
    "top_3":    "top_3",
    "last_4":   "last_4",
}

DIGIT_LABEL = {
    "bottom_2": "2 ตัวล่าง",
    "top_2":    "2 ตัวบน",
    "last_3":   "3 ตัวล่าง",
    "top_3":    "3 ตัวบน",
    "last_4":   "4 ตัวท้าย",
}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)
    _migrate()


def _migrate() -> None:
    """Add new columns if upgrading from an older schema."""
    with _conn() as conn:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(draws)").fetchall()}
        for col in ("last_4", "top_2", "top_3"):
            if col not in existing:
                conn.execute(f"ALTER TABLE draws ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_last4 ON draws(last_4)")
        conn.commit()
    _backfill()


def _backfill() -> None:
    """Compute last_4 / top_2 / top_3 from six_digit for any rows missing them."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, six_digit FROM draws WHERE last_4 = '' OR last_4 IS NULL"
        ).fetchall()
        for row in rows:
            six = str(row["six_digit"]).zfill(6)
            conn.execute(
                "UPDATE draws SET last_4=?, top_2=?, top_3=? WHERE id=?",
                (six[-4:], six[:2], six[:3], row["id"]),
            )


def upsert(df: pd.DataFrame) -> int:
    init()
    inserted = 0
    with _conn() as conn:
        for _, row in df.iterrows():
            six = str(row["six_digit"]).zfill(6)
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO draws
                  (draw_date, draw_date_be, six_digit, last_3, last_2, last_4, top_2, top_3)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    str(row.get("date", row.get("draw_date", "")))[:10],
                    str(row.get("date_be", row.get("draw_date_be", ""))),
                    six,
                    str(row["last_3"]).zfill(3),
                    str(row["last_2"]).zfill(2),
                    six[-4:],
                    six[:2],
                    six[:3],
                ),
            )
            inserted += cur.rowcount
    return inserted


def load() -> pd.DataFrame:
    init()
    with _conn() as conn:
        df = pd.read_sql(
            "SELECT draw_date, draw_date_be, six_digit, "
            "last_3, last_2, last_4, top_2, top_3 "
            "FROM draws ORDER BY draw_date DESC",
            conn,
        )
    if df.empty:
        return df
    df["draw_date"] = pd.to_datetime(df["draw_date"])
    for col, w in [("six_digit", 6), ("last_4", 4), ("top_3", 3), ("last_3", 3),
                   ("top_2", 2), ("last_2", 2)]:
        df[col] = df[col].astype(str).str.zfill(w)
    return df


def meta() -> dict:
    init()
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) total, MAX(draw_date) latest, "
            "MIN(draw_date) earliest, MAX(scraped_at) last_scraped FROM draws"
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
        return conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0]


def clear() -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM draws")


# ── Predictions ───────────────────────────────────────────────────────────────

def save_predictions(preds: list[dict]) -> None:
    """
    preds: list of dicts with keys:
      digit_type, rank, number, probability
    All saved with predicted_at = now (UTC).
    """
    init()
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as conn:
        for p in preds:
            conn.execute(
                "INSERT INTO predictions (predicted_at,digit_type,rank,number,probability) "
                "VALUES (?,?,?,?,?)",
                (now, p["digit_type"], p["rank"], p["number"], p["probability"]),
            )


def check_predictions() -> int:
    """
    For every pending prediction (correct IS NULL), find the first draw
    after predicted_at and mark correct/incorrect.
    Returns count of predictions now resolved.
    """
    init()
    checked = 0
    with _conn() as conn:
        pending = conn.execute(
            "SELECT DISTINCT predicted_at, digit_type FROM predictions WHERE correct IS NULL"
        ).fetchall()

        for row in pending:
            pat  = row["predicted_at"]
            dtype = row["digit_type"]
            col   = DIGIT_COL.get(dtype)
            if not col:
                continue

            draw = conn.execute(
                f"SELECT {col} FROM draws WHERE draw_date > ? ORDER BY draw_date ASC LIMIT 1",
                (pat[:10],),
            ).fetchone()
            if not draw:
                continue

            actual = draw[0]
            res = conn.execute(
                """
                UPDATE predictions
                SET actual=?, correct=CASE WHEN number=? THEN 1 ELSE 0 END,
                    checked_at=datetime('now')
                WHERE predicted_at=? AND digit_type=? AND correct IS NULL
                """,
                (actual, actual, pat, dtype),
            )
            checked += res.rowcount

    return checked


def load_predictions() -> pd.DataFrame:
    init()
    with _conn() as conn:
        df = pd.read_sql(
            "SELECT predicted_at, digit_type, rank, number, probability, "
            "actual, correct, checked_at FROM predictions ORDER BY predicted_at DESC",
            conn,
        )
    if not df.empty:
        df["predicted_at"] = pd.to_datetime(df["predicted_at"])
    return df


def prediction_accuracy() -> pd.DataFrame:
    """Per digit_type accuracy stats."""
    init()
    with _conn() as conn:
        df = pd.read_sql(
            """
            SELECT digit_type,
                   COUNT(*) total,
                   SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) hits,
                   SUM(CASE WHEN correct IS NULL THEN 1 ELSE 0 END) pending
            FROM predictions
            GROUP BY digit_type
            """,
            conn,
        )
    if not df.empty:
        df["accuracy_pct"] = (df["hits"] / (df["total"] - df["pending"]).replace(0, 1) * 100).round(1)
    return df
