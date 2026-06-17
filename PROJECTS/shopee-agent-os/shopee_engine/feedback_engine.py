"""
Revenue Feedback Loop Intelligence.

Imports actual click/order/revenue data, compares against predictions,
adapts scoring weights, and surfaces smarter product recommendations.

No external ML frameworks — pure DuckDB + arithmetic scoring.
"""

from __future__ import annotations

import csv as csv_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .config import config, build_column_map

console = Console()

# ---------------------------------------------------------------------------
# Table / column constants
# ---------------------------------------------------------------------------

REVENUE_TABLE    = "revenue_feedback"   # generic / ML learning data
PREDICT_TABLE    = "prediction_log"
WEIGHT_TABLE     = "learning_weights"
COMMISSION_TABLE = "commission_report"  # real Shopee TH affiliate commissions
CLICK_TABLE      = "click_report"       # real Shopee TH affiliate clicks

REVENUE_ALIASES: dict[str, list[str]] = {
    "report_date":   ["date", "order_date", "report_date", "day", "click_date",
                      "วันที่", "เวลาคลิก", "เวลาที่สั่งซื้อ"],
    "product_name":  ["product_name", "item_name", "name", "title", "item name", "product",
                      "ชื่อรายการสินค้า"],
    "product_id":    ["item_id", "itemid", "product_id", "sku_id",
                      "รหัสรายการสินค้า"],
    "clicks":        ["clicks", "click", "total_clicks", "click_count",
                      "คลิก", "จำนวนคลิก"],
    "orders":        ["orders", "order", "total_orders", "conversions",
                      "คำสั่งซื้อ", "จำนวนคำสั่งซื้อ"],
    "revenue":       ["revenue", "gmv", "total_revenue", "order_amount", "sales_amount", "amount",
                      "มูลค่าซื้อ(฿)", "มูลค่าซื้อ"],
    "commission":    ["commission", "total_commission", "affiliate_commission", "my_commission",
                      "ค่าคอมมิชชั่นสุทธิ(฿)", "ค่าคอมมิชชั่นสุทธิ"],
    "category":      ["category", "cat_name", "category_name"],
    "shop_name":     ["shop_name", "shopname", "seller_name",
                      "ชื่อร้านค้า"],
    "sub_id":        ["sub_id", "Sub_id"],
    "sub_id1":       ["sub_id1", "Sub_id1"],
    "sub_id2":       ["sub_id2", "Sub_id2"],
    "sub_id3":       ["sub_id3", "Sub_id3"],
    "sub_id4":       ["sub_id4", "Sub_id4"],
    "sub_id5":       ["sub_id5", "Sub_id5"],
    "channel":       ["channel", "ช่องทาง", "อ้างอิง"],
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "w_sold":        0.40,
    "w_likes":       0.15,
    "w_discount":    0.15,
    "w_shop_rating": 0.15,
    "w_item_rating": 0.15,
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.db_path), read_only=read_only)


def _q(col: str) -> str:
    return f'"{col}"'


def _safe(col: str) -> str:
    return f"COALESCE(TRY_CAST({_q(col)} AS DOUBLE), 0.0)"


def _resolve(lower_map: dict[str, str], *candidates: str) -> str | None:
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return name in [r[0] for r in con.execute("SHOW TABLES").fetchall()]


def _parse_date(s: str) -> str:
    """Normalise Shopee TH date strings to YYYY-MM-DD."""
    s = str(s or "").strip()
    if not s:
        return ""
    date_part = s.split(" ")[0].split("T")[0]
    if "/" in date_part:
        parts = date_part.split("/")
        if len(parts) == 3:
            if len(parts[0]) == 4:          # YYYY/MM/DD
                return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
            if len(parts[2]) == 4:          # DD/MM/YYYY
                return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return date_part


def _detect_revenue_cols(actual_cols: list[str]) -> dict[str, str | None]:
    lower_map = {c.lower(): c for c in actual_cols}
    result: dict[str, str | None] = {}
    for canonical, aliases in REVENUE_ALIASES.items():
        result[canonical] = _resolve(lower_map, *aliases)
    return result


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------

def _init_feedback_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {REVENUE_TABLE} (
            id            INTEGER,
            imported_at   TEXT,
            report_date   TEXT,
            product_name  TEXT,
            product_id    TEXT,
            clicks        DOUBLE,
            orders        DOUBLE,
            revenue       DOUBLE,
            commission    DOUBLE,
            category      TEXT,
            shop_name     TEXT,
            source        TEXT,
            sub_id        TEXT,
            sub_id1       TEXT,
            sub_id2       TEXT,
            sub_id3       TEXT,
            sub_id4       TEXT,
            sub_id5       TEXT,
            channel       TEXT
        )
    """)
    # Migration: add new columns to existing tables that were created before these fields
    for _col in ("sub_id", "sub_id1", "sub_id2", "sub_id3", "sub_id4", "sub_id5", "channel"):
        try:
            con.execute(f"ALTER TABLE {REVENUE_TABLE} ADD COLUMN IF NOT EXISTS {_col} TEXT")
        except Exception:
            pass

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {PREDICT_TABLE} (
            id                   INTEGER,
            logged_at            TEXT,
            snapshot_date        TEXT,
            product_name         TEXT,
            predicted_opp_score  DOUBLE,
            predicted_viral_score DOUBLE,
            predicted_rank       INTEGER
        )
    """)

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {WEIGHT_TABLE} (
            id               INTEGER,
            updated_at       TEXT,
            iteration        INTEGER,
            w_sold           DOUBLE,
            w_likes          DOUBLE,
            w_discount       DOUBLE,
            w_shop_rating    DOUBLE,
            w_item_rating    DOUBLE,
            accuracy_score   DOUBLE,
            correlation_score DOUBLE,
            notes            TEXT
        )
    """)


def _init_commission_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {COMMISSION_TABLE} (
            id           INTEGER,
            imported_at  TEXT,
            report_date  TEXT,
            product_name TEXT,
            product_id   TEXT,
            shop_name    TEXT,
            revenue      DOUBLE,
            commission   DOUBLE,
            sub_id1      TEXT,
            sub_id2      TEXT,
            sub_id3      TEXT,
            sub_id4      TEXT,
            sub_id5      TEXT,
            channel      TEXT
        )
    """)


def _init_click_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {CLICK_TABLE} (
            id          INTEGER,
            imported_at TEXT,
            report_date TEXT,
            clicks      DOUBLE,
            sub_id      TEXT,
            channel     TEXT
        )
    """)


# ---------------------------------------------------------------------------
# Spearman rank correlation (pure Python — no external deps)
# ---------------------------------------------------------------------------

def _spearman(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    # Assign ranks (average ties)
    def _rank(vals: list[float]) -> list[float]:
        sorted_vals = sorted(enumerate(vals), key=lambda t: t[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and sorted_vals[j + 1][1] == sorted_vals[i][1]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[sorted_vals[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = _rank(x)
    ry = _rank(y)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    denom = n * (n * n - 1)
    return 1 - 6 * d2 / denom if denom else 0.0


def _accuracy_pct(r: float) -> float:
    """Map Spearman r ∈ [-1, 1] to accuracy pct ∈ [0, 100]."""
    return round((r + 1) / 2 * 100, 1)


# ---------------------------------------------------------------------------
# 1. import-revenue-report
# ---------------------------------------------------------------------------

def _read_rows(path: Path) -> tuple[list[str], list[dict]]:
    """Read CSV or Excel file. Returns (column_names, rows_as_dicts)."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls", ".xlsm"):
        import pandas as pd
        df = pd.read_excel(path, dtype=str)
        cols = list(df.columns)
        rows = df.fillna("").to_dict("records")
        return cols, rows

    # CSV — sniff delimiter
    with open(path, "r", encoding="utf-8-sig") as fh:
        sample = fh.read(8192)
    try:
        delimiter = csv_mod.Sniffer().sniff(sample).delimiter
    except csv_mod.Error:
        delimiter = ","

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv_mod.DictReader(fh, delimiter=delimiter)
        cols = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return cols, rows


def _import_feedback_csv(csv_path: Path, source: str) -> dict:
    """Import CSV or Excel report into revenue_feedback."""
    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")

    actual_cols, raw_rows = _read_rows(csv_path)
    col_map = _detect_revenue_cols(actual_cols)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows: list[dict] = []
    for raw in raw_rows:
        def _g(canonical: str, default="") -> str:
            col = col_map.get(canonical)
            return raw.get(col, default) if col else default

        def _gf(canonical: str) -> float:
            v = _g(canonical, "0")
            try:
                return float(str(v).replace(",", "").strip() or 0)
            except ValueError:
                return 0.0

        rows.append({
            "imported_at":  now_str,
            "report_date":  _parse_date(_g("report_date")),
            "product_name": _g("product_name"),
            "product_id":   _g("product_id"),
            "clicks":       _gf("clicks"),
            "orders":       _gf("orders"),
            "revenue":      _gf("revenue"),
            "commission":   _gf("commission"),
            "category":     _g("category"),
            "shop_name":    _g("shop_name"),
            "source":       source,
            "sub_id":       _g("sub_id"),
            "sub_id1":      _g("sub_id1"),
            "sub_id2":      _g("sub_id2"),
            "sub_id3":      _g("sub_id3"),
            "sub_id4":      _g("sub_id4"),
            "sub_id5":      _g("sub_id5"),
            "channel":      _g("channel"),
        })

    if not rows:
        return {"rows_imported": 0, "source": source, "path": str(csv_path)}

    con = _connect(read_only=False)
    _init_feedback_tables(con)

    # Remove existing rows for same (source, report_date) before re-import
    if rows[0]["report_date"]:
        dates = list({r["report_date"] for r in rows})
        for d in dates:
            con.execute(
                f"DELETE FROM {REVENUE_TABLE} WHERE source=? AND report_date=?",
                [source, d],
            )

    # Insert with sequential IDs
    max_id_row = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {REVENUE_TABLE}").fetchone()
    next_id = (max_id_row[0] or 0) + 1

    for i, r in enumerate(rows):
        con.execute(
            f"""INSERT INTO {REVENUE_TABLE}
                (id, imported_at, report_date, product_name, product_id,
                 clicks, orders, revenue, commission, category, shop_name, source,
                 sub_id, sub_id1, sub_id2, sub_id3, sub_id4, sub_id5, channel)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [next_id + i, r["imported_at"], r["report_date"], r["product_name"],
             r["product_id"], r["clicks"], r["orders"], r["revenue"],
             r["commission"], r["category"], r["shop_name"], r["source"],
             r.get("sub_id",""), r.get("sub_id1",""), r.get("sub_id2",""),
             r.get("sub_id3",""), r.get("sub_id4",""), r.get("sub_id5",""),
             r.get("channel","")],
        )

    con.close()
    return {"rows_imported": len(rows), "source": source, "path": str(csv_path)}


def import_revenue_report(csv_path: str | Path) -> dict:
    """Import actual revenue/commission data CSV."""
    return _import_feedback_csv(Path(csv_path), source="revenue")


def import_click_report(csv_path: str | Path) -> dict:
    """Import click-level report CSV."""
    return _import_feedback_csv(Path(csv_path), source="clicks")


def import_order_report(csv_path: str | Path) -> dict:
    """Import order-level report CSV."""
    return _import_feedback_csv(Path(csv_path), source="orders")


# ---------------------------------------------------------------------------
# Shopee TH dedicated importers
# ---------------------------------------------------------------------------

_TH_COMMISSION_COLS: dict[str, list[str]] = {
    "product_name": ["ชื่อรายการสินค้า"],
    "product_id":   ["รหัสรายการสินค้า"],
    "shop_name":    ["ชื่อร้านค้า"],
    "revenue":      ["มูลค่าซื้อ(฿)", "มูลค่าซื้อ"],
    "commission":   ["ค่าคอมมิชชั่นสุทธิ(฿)", "ค่าคอมมิชชั่นสุทธิ"],
    "report_date":  ["เวลาที่สั่งซื้อ", "เวลาคลิก", "วันที่", "date"],
    "sub_id1":      ["Sub_id1", "sub_id1"],
    "sub_id2":      ["Sub_id2", "sub_id2"],
    "sub_id3":      ["Sub_id3", "sub_id3"],
    "sub_id4":      ["Sub_id4", "sub_id4"],
    "sub_id5":      ["Sub_id5", "sub_id5"],
    "channel":      ["ช่องทาง", "channel"],
}


def import_commission_report_th(path: str | Path) -> dict:
    """Import Shopee TH commission report. Each row = 1 completed order."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    actual_cols, raw_rows = _read_rows(path)
    lower_map = {c.lower(): c for c in actual_cols}

    def _col(canonical: str) -> str | None:
        for alias in _TH_COMMISSION_COLS.get(canonical, []):
            if alias.lower() in lower_map:
                return lower_map[alias.lower()]
        return None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[dict] = []

    for raw in raw_rows:
        def _g(canonical: str, default: str = "") -> str:
            c = _col(canonical)
            return str(raw.get(c, default)).strip() if c else default

        def _gf(canonical: str) -> float:
            v = _g(canonical, "0")
            try:
                return float(str(v).replace(",", "").replace("฿", "").strip() or 0)
            except ValueError:
                return 0.0

        rows.append({
            "imported_at":  now_str,
            "report_date":  _parse_date(_g("report_date")),
            "product_name": _g("product_name"),
            "product_id":   _g("product_id"),
            "shop_name":    _g("shop_name"),
            "revenue":      _gf("revenue"),
            "commission":   _gf("commission"),
            "sub_id1":      _g("sub_id1"),
            "sub_id2":      _g("sub_id2"),
            "sub_id3":      _g("sub_id3"),
            "sub_id4":      _g("sub_id4"),
            "sub_id5":      _g("sub_id5"),
            "channel":      _g("channel"),
        })

    if not rows:
        return {"rows_imported": 0, "source": "commission_th", "path": str(path)}

    con = _connect(read_only=False)
    _init_commission_table(con)

    dates = list({r["report_date"] for r in rows if r["report_date"]})
    for d in dates:
        con.execute(f"DELETE FROM {COMMISSION_TABLE} WHERE report_date=?", [d])

    max_id  = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {COMMISSION_TABLE}").fetchone()[0]
    next_id = (max_id or 0) + 1

    for i, r in enumerate(rows):
        con.execute(f"""
            INSERT INTO {COMMISSION_TABLE}
            (id, imported_at, report_date, product_name, product_id, shop_name,
             revenue, commission, sub_id1, sub_id2, sub_id3, sub_id4, sub_id5, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            next_id + i, r["imported_at"], r["report_date"], r["product_name"],
            r["product_id"], r["shop_name"], r["revenue"], r["commission"],
            r["sub_id1"], r["sub_id2"], r["sub_id3"], r["sub_id4"],
            r["sub_id5"], r["channel"],
        ])

    con.close()
    return {
        "rows_imported":    len(rows),
        "source":           "commission_th",
        "path":             str(path),
        "total_revenue":    sum(r["revenue"]    for r in rows),
        "total_commission": sum(r["commission"] for r in rows),
    }


def import_click_report_th(path: str | Path) -> dict:
    """Import Shopee TH click report. Aggregates by date (each raw row = 1 click)."""
    from collections import defaultdict

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    actual_cols, raw_rows = _read_rows(path)
    lower_map = {c.lower(): c for c in actual_cols}

    date_candidates = ["เวลาคลิก", "วันที่", "date", "click_date"]
    date_col = next(
        (lower_map[c.lower()] for c in date_candidates if c.lower() in lower_map), None
    )
    ref_col  = lower_map.get("อ้างอิง") or lower_map.get("channel")
    sub_col  = lower_map.get("sub_id")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_clicks: dict[str, int]  = defaultdict(int)
    date_channel: dict[str, str] = {}

    for raw in raw_rows:
        raw_date = str(raw.get(date_col, "")).strip() if date_col else ""
        parsed = _parse_date(raw_date) or "unknown"
        date_clicks[parsed] += 1
        if ref_col and parsed not in date_channel:
            date_channel[parsed] = str(raw.get(ref_col, "")).strip()

    if not date_clicks:
        return {"rows_imported": 0, "source": "click_th", "path": str(path), "total_clicks": 0}

    con = _connect(read_only=False)
    _init_click_table(con)

    for d in date_clicks:
        con.execute(f"DELETE FROM {CLICK_TABLE} WHERE report_date=?", [d])

    max_id  = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {CLICK_TABLE}").fetchone()[0]
    next_id = (max_id or 0) + 1

    for i, (date, count) in enumerate(sorted(date_clicks.items())):
        con.execute(f"""
            INSERT INTO {CLICK_TABLE}
            (id, imported_at, report_date, clicks, sub_id, channel)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            next_id + i, now_str, date, float(count), "", date_channel.get(date, ""),
        ])

    con.close()
    return {
        "rows_imported": len(date_clicks),
        "source":        "click_th",
        "path":          str(path),
        "total_clicks":  sum(date_clicks.values()),
        "days_covered":  len(date_clicks),
    }


# ---------------------------------------------------------------------------
# 2. log_predictions  (called by CLI / scheduler)
# ---------------------------------------------------------------------------

def log_predictions(table_name: str = "products", top: int = 100) -> int:
    """
    Snapshot the current top-N opportunity predictions into prediction_log.
    Returns the number of predictions logged.
    """
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = _connect(read_only=False)
    _init_feedback_tables(con)

    prod_cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}'"
    ).fetchall()]
    col_map = build_column_map(prod_cols)
    lower_map = {c.lower(): c for c in prod_cols}

    name_col  = col_map.get("product_name") or (prod_cols[1] if len(prod_cols) > 1 else prod_cols[0])
    sold_col  = col_map.get("sales")
    likes_col = lower_map.get("like") or lower_map.get("likes")
    disc_col  = col_map.get("discount")
    shop_r    = col_map.get("shop_rating")
    item_r    = col_map.get("rating")

    def _s(c: str | None) -> str:
        return f"COALESCE(TRY_CAST({_q(c)} AS DOUBLE), 0.0)" if c else "0.0"

    opp = (
        f"{_s(sold_col)}*0.40 + {_s(likes_col)}*0.15 + {_s(disc_col)}*0.15 + "
        f"{_s(shop_r)}*100*0.15 + {_s(item_r)}*100*0.15"
    )
    viral = f"{_s(sold_col)}*0.35 + {_s(likes_col)}*0.35 + {_s(disc_col)}*100*0.30"

    rows = con.execute(f"""
        SELECT {_q(name_col)} AS name,
               ROUND({opp}, 1) AS opp_score,
               ROUND({viral}, 1) AS viral_score
        FROM {_q(table_name)}
        WHERE {_q(name_col)} IS NOT NULL AND LENGTH({_q(name_col)}) > 5
        ORDER BY opp_score DESC
        LIMIT {top}
    """).fetchall()

    max_id_row = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {PREDICT_TABLE}").fetchone()
    next_id = (max_id_row[0] or 0) + 1

    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.now().strftime("%Y-%m-%d")

    for rank, (name, opp_s, viral_s) in enumerate(rows, 1):
        con.execute(
            f"""INSERT INTO {PREDICT_TABLE}
                (id, logged_at, snapshot_date, product_name,
                 predicted_opp_score, predicted_viral_score, predicted_rank)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [next_id + rank - 1, now_str, date_str,
             str(name)[:120], float(opp_s or 0), float(viral_s or 0), rank],
        )

    con.close()
    return len(rows)


# ---------------------------------------------------------------------------
# 3. learning_report
# ---------------------------------------------------------------------------

def learning_report() -> dict:
    """
    Compare predictions vs actuals and return accuracy metrics:
    - product_accuracy   : % of predicted top-20 that actually earned revenue
    - opportunity_accuracy: Spearman correlation (pred_opp_rank vs actual_revenue_rank)
    - viral_accuracy     : Spearman correlation (pred_viral_rank vs actual_clicks_rank)
    """
    con = _connect(read_only=True)
    if not _has_table(con, PREDICT_TABLE) or not _has_table(con, REVENUE_TABLE):
        con.close()
        return {"error": "No prediction_log or revenue_feedback table found. "
                         "Run `log-predictions` and `import-revenue-report` first."}

    # ── Latest snapshot date ──────────────────────────────────────────────────
    snap = con.execute(
        f"SELECT MAX(snapshot_date) FROM {PREDICT_TABLE}"
    ).fetchone()[0]
    if not snap:
        con.close()
        return {"error": "No predictions logged yet. Run `shopee log-predictions` first."}

    pred_rows = con.execute(f"""
        SELECT product_name, predicted_opp_score, predicted_viral_score, predicted_rank
        FROM {PREDICT_TABLE}
        WHERE snapshot_date = '{snap}'
        ORDER BY predicted_rank
        LIMIT 100
    """).fetchall()

    rev_rows = con.execute(f"""
        SELECT LOWER(product_name) AS pname,
               SUM(revenue) AS total_revenue,
               SUM(clicks)  AS total_clicks
        FROM {REVENUE_TABLE}
        GROUP BY LOWER(product_name)
        HAVING SUM(revenue) > 0 OR SUM(clicks) > 0
    """).fetchall()

    con.close()

    if not rev_rows:
        return {
            "snapshot_date":        snap,
            "predictions_logged":   len(pred_rows),
            "revenue_data_rows":    0,
            "product_accuracy":     None,
            "opportunity_accuracy": None,
            "viral_accuracy":       None,
            "warning":              "No revenue feedback data found. "
                                    "Run `shopee import-revenue-report` first.",
        }

    rev_map = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in rev_rows}

    top_20_names = [r[0].lower() for r in pred_rows[:20]]
    matched = sum(1 for n in top_20_names if n in rev_map and rev_map[n][0] > 0)
    product_accuracy = round(matched / max(len(top_20_names), 1) * 100, 1)

    # Spearman: opportunity rank vs revenue rank
    pairs_opp: list[tuple[float, float]] = []
    pairs_viral: list[tuple[float, float]] = []
    for name, opp_s, viral_s, _ in pred_rows:
        nm = name.lower()
        if nm in rev_map:
            rev, clk = rev_map[nm]
            pairs_opp.append((opp_s, rev))
            pairs_viral.append((viral_s, clk))

    opp_corr   = _spearman([p[0] for p in pairs_opp],   [p[1] for p in pairs_opp])   if len(pairs_opp) >= 2   else 0.0
    viral_corr = _spearman([p[0] for p in pairs_viral], [p[1] for p in pairs_viral]) if len(pairs_viral) >= 2 else 0.0

    return {
        "snapshot_date":        snap,
        "predictions_logged":   len(pred_rows),
        "revenue_data_rows":    len(rev_rows),
        "matched_products":     matched,
        "product_accuracy":     product_accuracy,
        "opportunity_accuracy": _accuracy_pct(opp_corr),
        "viral_accuracy":       _accuracy_pct(viral_corr),
        "opp_spearman_r":       round(opp_corr, 4),
        "viral_spearman_r":     round(viral_corr, 4),
    }


# ---------------------------------------------------------------------------
# 4. retrain_rankings
# ---------------------------------------------------------------------------

def retrain_rankings(
    table_name: str = "products",
    learning_rate: float = 0.05,
) -> dict:
    """
    Adapt opportunity score weights based on signal-to-revenue correlations.

    Algorithm:
    1. Join products with revenue_feedback on product_name
    2. Compute CORR(signal, actual_revenue) for each of the 5 signals
    3. Shift each weight proportionally: w += lr × (signal_corr - mean_corr)
    4. Clip to [0.05, 0.80] and normalise so weights sum to 1.0
    5. Persist in learning_weights table
    """
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = _connect(read_only=False)
    _init_feedback_tables(con)

    if not _has_table(con, REVENUE_TABLE):
        con.close()
        raise RuntimeError("No revenue_feedback table. Run import-revenue-report first.")

    prod_cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}'"
    ).fetchall()]
    col_map   = build_column_map(prod_cols)
    lower_map = {c.lower(): c for c in prod_cols}

    name_col  = col_map.get("product_name") or prod_cols[1]
    sold_col  = col_map.get("sales")
    likes_col = lower_map.get("like") or lower_map.get("likes")
    disc_col  = col_map.get("discount")
    shop_r    = col_map.get("shop_rating")
    item_r    = col_map.get("rating")

    selects = [f"{_q(name_col)} AS product_name"]
    signals: list[str] = []
    for label, col in [
        ("sold", sold_col), ("likes", likes_col), ("discount", disc_col),
        ("shop_rating", shop_r), ("item_rating", item_r),
    ]:
        if col:
            selects.append(f"{_safe(col)} AS {label}")
            signals.append(label)
        else:
            selects.append(f"0.0 AS {label}")

    join_rows = con.execute(f"""
        WITH p AS (
            SELECT {', '.join(selects)}
            FROM {_q(table_name)}
        ),
        r AS (
            SELECT LOWER(product_name) AS pname, SUM(revenue) AS rev
            FROM {REVENUE_TABLE}
            GROUP BY LOWER(product_name)
            HAVING SUM(revenue) > 0
        )
        SELECT p.sold, p.likes, p.discount, p.shop_rating, p.item_rating, r.rev
        FROM p JOIN r ON LOWER(p.product_name) = r.pname
    """).fetchall()

    con.close()

    if len(join_rows) < 3:
        return {
            "weights": DEFAULT_WEIGHTS.copy(),
            "warning": f"Only {len(join_rows)} matched products — need at least 3 for meaningful retraining.",
            "matched_products": len(join_rows),
        }

    sold_v  = [r[0] for r in join_rows]
    likes_v = [r[1] for r in join_rows]
    disc_v  = [r[2] for r in join_rows]
    shop_v  = [r[3] for r in join_rows]
    item_v  = [r[4] for r in join_rows]
    rev_v   = [r[5] for r in join_rows]

    def _pearson(x: list[float], y: list[float]) -> float:
        n = len(x)
        mx, my = sum(x) / n, sum(y) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        dx = (sum((xi - mx) ** 2 for xi in x)) ** 0.5
        dy = (sum((yi - my) ** 2 for yi in y)) ** 0.5
        return num / (dx * dy) if dx * dy > 0 else 0.0

    corrs = {
        "w_sold":        _pearson(sold_v,  rev_v),
        "w_likes":       _pearson(likes_v, rev_v),
        "w_discount":    _pearson(disc_v,  rev_v),
        "w_shop_rating": _pearson(shop_v,  rev_v),
        "w_item_rating": _pearson(item_v,  rev_v),
    }

    # Get current weights (latest from learning_weights or defaults)
    con = _connect(read_only=False)
    last = con.execute(
        f"SELECT w_sold, w_likes, w_discount, w_shop_rating, w_item_rating "
        f"FROM {WEIGHT_TABLE} ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if last:
        current = dict(zip(DEFAULT_WEIGHTS.keys(), last))
    else:
        current = DEFAULT_WEIGHTS.copy()

    # Shift weights
    mean_corr = sum(corrs.values()) / len(corrs)
    updated = {}
    for key, w in current.items():
        delta = learning_rate * (corrs[key] - mean_corr)
        updated[key] = max(0.05, min(0.80, w + delta))

    # Normalise to sum = 1.0
    total = sum(updated.values())
    for key in updated:
        updated[key] = round(updated[key] / total, 4)

    # Compute overall accuracy score (avg |corr|)
    acc = round(sum(abs(v) for v in corrs.values()) / len(corrs) * 100, 1)

    # Persist
    iter_row = con.execute(f"SELECT COALESCE(MAX(iteration), 0) FROM {WEIGHT_TABLE}").fetchone()
    iteration = (iter_row[0] or 0) + 1
    max_id    = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {WEIGHT_TABLE}").fetchone()[0]

    con.execute(f"""
        INSERT INTO {WEIGHT_TABLE}
        (id, updated_at, iteration, w_sold, w_likes, w_discount, w_shop_rating, w_item_rating,
         accuracy_score, correlation_score, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        max_id + 1,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        iteration,
        updated["w_sold"], updated["w_likes"], updated["w_discount"],
        updated["w_shop_rating"], updated["w_item_rating"],
        acc, round(mean_corr, 4),
        f"lr={learning_rate}, n={len(join_rows)} products",
    ])
    con.close()

    return {
        "iteration":        iteration,
        "matched_products": len(join_rows),
        "old_weights":      current,
        "new_weights":      updated,
        "signal_correlations": {k: round(v, 4) for k, v in corrs.items()},
        "accuracy_score":   acc,
    }


# ---------------------------------------------------------------------------
# 5. profit_learning
# ---------------------------------------------------------------------------

def profit_learning(top: int = 20) -> dict:
    """
    Classify prediction quality:
    - True Positive:  predicted top AND actually earned revenue
    - False Positive: predicted top BUT no significant revenue
    - False Negative: NOT predicted top BUT earned significant revenue
    - True Negative:  correctly excluded (low predicted AND low actual)
    """
    con = _connect(read_only=True)
    if not _has_table(con, PREDICT_TABLE):
        con.close()
        return {"error": "No predictions logged. Run `shopee log-predictions` first."}
    if not _has_table(con, REVENUE_TABLE):
        con.close()
        return {"error": "No revenue data. Run `shopee import-revenue-report` first."}

    snap = con.execute(f"SELECT MAX(snapshot_date) FROM {PREDICT_TABLE}").fetchone()[0]
    if not snap:
        con.close()
        return {"error": "No prediction snapshots found."}

    pred = con.execute(f"""
        SELECT product_name, predicted_opp_score, predicted_rank
        FROM {PREDICT_TABLE} WHERE snapshot_date = '{snap}'
        ORDER BY predicted_rank
    """).fetchall()

    rev_agg = con.execute(f"""
        SELECT LOWER(product_name), SUM(revenue), SUM(orders)
        FROM {REVENUE_TABLE}
        GROUP BY LOWER(product_name)
    """).fetchall()
    con.close()

    rev_map = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in rev_agg}

    if not rev_map:
        return {
            "snapshot_date": snap,
            "error":         "No revenue data in revenue_feedback table.",
        }

    # Revenue threshold = median of non-zero revenues
    non_zero = sorted(v for v, _ in rev_map.values() if v > 0)
    threshold = non_zero[len(non_zero) // 2] if non_zero else 0.0

    predicted_top_names = {r[0].lower() for r in pred[:top]}

    tp, fp, fn, tn = [], [], [], []

    for name, opp_s, rank in pred:
        nm = name.lower()
        rev, orders = rev_map.get(nm, (0.0, 0.0))
        in_top = nm in predicted_top_names
        is_good = rev >= threshold and orders > 0

        entry = {
            "product": name[:55],
            "predicted_rank": rank,
            "revenue": rev,
            "orders": orders,
            "opp_score": opp_s,
        }
        if in_top and is_good:
            tp.append(entry)
        elif in_top and not is_good:
            fp.append(entry)

    # Find false negatives from revenue data
    pred_name_lower = {r[0].lower() for r in pred}
    for nm, (rev, orders) in rev_map.items():
        if nm not in pred_name_lower and rev >= threshold and orders > 0:
            fn.append({"product": nm[:55], "revenue": rev, "orders": orders})

    precision = round(len(tp) / max(len(tp) + len(fp), 1) * 100, 1)
    recall    = round(len(tp) / max(len(tp) + len(fn), 1) * 100, 1)
    f1        = round(2 * precision * recall / max(precision + recall, 0.01), 1)

    return {
        "snapshot_date":    snap,
        "revenue_threshold": round(threshold, 2),
        "true_positives":   tp,
        "false_positives":  fp,
        "false_negatives":  fn,
        "precision":        precision,
        "recall":           recall,
        "f1_score":         f1,
        "prediction_count": len(pred),
        "revenue_products": len(rev_map),
    }


# ---------------------------------------------------------------------------
# 6. get_revenue_dashboard  (Phase 11)
# ---------------------------------------------------------------------------

def get_revenue_dashboard(top_n: int = 5) -> dict:
    """Aggregate revenue_feedback rows for the Discord revenue dashboard.

    Returns totals, top clicked, top orders, top commission, EPC leaders,
    and worst-performing products (clicks but no conversions).
    """
    if not config.db_path.exists():
        return {"error": "Database not found"}

    con = _connect(read_only=True)
    try:
        if not _has_table(con, REVENUE_TABLE):
            return {
                "error": (
                    "No revenue data yet. Use /affiliate-import-report to import "
                    "a Click / Order / Revenue CSV from the Shopee affiliate portal."
                )
            }

        totals = con.execute(f"""
            SELECT
                COALESCE(SUM(clicks),     0) AS total_clicks,
                COALESCE(SUM(orders),     0) AS total_orders,
                COALESCE(SUM(revenue),    0) AS total_revenue,
                COALESCE(SUM(commission), 0) AS total_commission,
                COUNT(DISTINCT product_name) AS total_products,
                MIN(report_date)             AS date_from,
                MAX(report_date)             AS date_to
            FROM {REVENUE_TABLE}
        """).fetchone()

        total_clicks     = float(totals[0] or 0)
        total_orders     = float(totals[1] or 0)
        total_revenue    = float(totals[2] or 0)
        total_commission = float(totals[3] or 0)
        total_products   = int(totals[4] or 0)
        date_from        = totals[5] or "—"
        date_to          = totals[6] or "—"
        epc              = round(total_commission / total_clicks * 100, 4) if total_clicks > 0 else 0.0

        def _fetch(sql: str) -> list:
            return con.execute(sql).fetchall()

        top_clicked = _fetch(f"""
            SELECT product_name, SUM(clicks) AS c, SUM(orders) AS o
            FROM {REVENUE_TABLE} GROUP BY product_name ORDER BY c DESC LIMIT {top_n}
        """)

        top_orders = _fetch(f"""
            SELECT product_name, SUM(orders) AS o, SUM(revenue) AS r
            FROM {REVENUE_TABLE} GROUP BY product_name ORDER BY o DESC LIMIT {top_n}
        """)

        top_commission = _fetch(f"""
            SELECT product_name, SUM(commission) AS cm, SUM(clicks) AS c
            FROM {REVENUE_TABLE} GROUP BY product_name ORDER BY cm DESC LIMIT {top_n}
        """)

        top_epc = _fetch(f"""
            SELECT product_name,
                   SUM(commission) / NULLIF(SUM(clicks), 0) AS epc,
                   SUM(clicks)     AS c,
                   SUM(commission) AS cm
            FROM {REVENUE_TABLE}
            GROUP BY product_name
            HAVING SUM(clicks) >= 5
            ORDER BY epc DESC LIMIT {top_n}
        """)

        worst = _fetch(f"""
            SELECT product_name, SUM(clicks) AS c, SUM(orders) AS o, SUM(commission) AS cm
            FROM {REVENUE_TABLE}
            GROUP BY product_name
            HAVING SUM(clicks) >= 5 AND SUM(orders) = 0
            ORDER BY c DESC LIMIT {top_n}
        """)

        return {
            "summary": {
                "total_clicks":     total_clicks,
                "total_orders":     total_orders,
                "total_revenue":    total_revenue,
                "total_commission": total_commission,
                "total_products":   total_products,
                "epc":              epc,
                "date_from":        date_from,
                "date_to":          date_to,
            },
            "top_clicked":    [
                {"name": (r[0] or "")[:55], "clicks": float(r[1] or 0), "orders": float(r[2] or 0)}
                for r in top_clicked
            ],
            "top_orders":     [
                {"name": (r[0] or "")[:55], "orders": float(r[1] or 0), "revenue": float(r[2] or 0)}
                for r in top_orders
            ],
            "top_commission": [
                {"name": (r[0] or "")[:55], "commission": float(r[1] or 0), "clicks": float(r[2] or 0)}
                for r in top_commission
            ],
            "top_epc":        [
                {"name": (r[0] or "")[:55], "epc": float(r[1] or 0),
                 "clicks": float(r[2] or 0), "commission": float(r[3] or 0)}
                for r in top_epc
            ],
            "worst_performing": [
                {"name": (r[0] or "")[:55], "clicks": float(r[1] or 0),
                 "orders": float(r[2] or 0), "commission": float(r[3] or 0)}
                for r in worst
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 6b. Revenue summary / products / top / category  (new commands)
# ---------------------------------------------------------------------------

def get_revenue_summary() -> dict:
    """Summary from real Shopee TH imports: commission_report + click_report only."""
    if not config.db_path.exists():
        return {"error": "Database not found"}
    con = _connect(read_only=True)
    try:
        has_commission = _has_table(con, COMMISSION_TABLE)
        has_clicks     = _has_table(con, CLICK_TABLE)

        if not has_commission and not has_clicks:
            return {
                "no_data": True,
                "error": (
                    "No real revenue data imported yet.\n"
                    "Use /import-commission-report and /import-click-report."
                ),
            }

        orders = revenue = commission = 0.0
        products = days = 0
        d_from = d_to = "—"

        if has_commission:
            r = con.execute(f"""
                SELECT COUNT(*), COALESCE(SUM(revenue), 0), COALESCE(SUM(commission), 0),
                       COUNT(DISTINCT product_name), COUNT(DISTINCT report_date),
                       MIN(report_date), MAX(report_date)
                FROM {COMMISSION_TABLE}
            """).fetchone()
            orders, revenue, commission = float(r[0] or 0), float(r[1] or 0), float(r[2] or 0)
            products = int(r[3] or 0)
            days     = int(r[4] or 0)
            d_from, d_to = r[5] or "—", r[6] or "—"

        total_clicks = 0.0
        click_from = click_to = "—"
        if has_clicks:
            r = con.execute(f"""
                SELECT COALESCE(SUM(clicks), 0), MIN(report_date), MAX(report_date)
                FROM {CLICK_TABLE}
            """).fetchone()
            total_clicks = float(r[0] or 0)
            click_from, click_to = r[1] or "—", r[2] or "—"

        cr  = round(orders / total_clicks * 100, 2) if total_clicks else 0.0
        epc = round(commission / total_clicks * 100, 4) if total_clicks else 0.0

        return {
            "total_clicks":     total_clicks,
            "total_orders":     orders,
            "total_revenue":    revenue,
            "total_commission": commission,
            "total_products":   products,
            "total_days":       days,
            "date_from":        d_from,
            "date_to":          d_to,
            "click_date_from":  click_from,
            "click_date_to":    click_to,
            "conversion_rate":  cr,
            "epc":              epc,
            "has_commission":   has_commission,
            "has_clicks":       has_clicks,
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        con.close()


def get_revenue_products(keyword: str = "", limit: int = 20) -> list[dict]:
    """Per-product breakdown from commission_report only (real Shopee affiliate data)."""
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        if not _has_table(con, COMMISSION_TABLE):
            return []
        where = f"WHERE LOWER(product_name) LIKE '%{keyword.lower()}%'" if keyword else ""
        rows = con.execute(f"""
            SELECT
                product_name,
                product_id,
                shop_name,
                COUNT(*)         AS orders,
                SUM(revenue)     AS revenue,
                SUM(commission)  AS commission,
                MAX(report_date) AS last_date
            FROM {COMMISSION_TABLE}
            {where}
            GROUP BY product_name, product_id, shop_name
            ORDER BY commission DESC
            LIMIT {limit}
        """).fetchall()
        return [
            {
                "name":       (r[0] or "")[:55],
                "product_id": r[1] or "",
                "shop_name":  r[2] or "",
                "orders":     float(r[3] or 0),
                "revenue":    float(r[4] or 0),
                "commission": float(r[5] or 0),
                "last_date":  r[6] or "—",
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()


_METRIC_SQL = {
    "orders":     "COUNT(*)",
    "revenue":    "SUM(revenue)",
    "commission": "SUM(commission)",
}


def get_revenue_top(metric: str = "commission", top_n: int = 10) -> list[dict]:
    """Top N products by commission/revenue/orders from real commission_report."""
    if not config.db_path.exists():
        return []
    order_expr = _METRIC_SQL.get(metric, "SUM(commission)")
    con = _connect(read_only=True)
    try:
        if not _has_table(con, COMMISSION_TABLE):
            return []
        rows = con.execute(f"""
            SELECT
                product_name,
                COUNT(*)        AS orders,
                SUM(revenue)    AS revenue,
                SUM(commission) AS commission
            FROM {COMMISSION_TABLE}
            GROUP BY product_name
            ORDER BY {order_expr} DESC
            LIMIT {top_n}
        """).fetchall()
        return [
            {
                "rank":       i,
                "name":       (r[0] or "")[:55],
                "orders":     float(r[1] or 0),
                "revenue":    float(r[2] or 0),
                "commission": float(r[3] or 0),
            }
            for i, r in enumerate(rows, 1)
        ]
    except Exception:
        return []
    finally:
        con.close()


def _category_rows(con, group_expr: str, top_n: int) -> list[dict]:
    """Run the category aggregation SQL and return normalised dicts."""
    sql = f"""
        SELECT
            {group_expr}                        AS category,
            COUNT(DISTINCT product_name)        AS products,
            COUNT(*)                            AS orders,
            COALESCE(SUM(revenue), 0)           AS revenue,
            COALESCE(SUM(commission), 0)        AS commission
        FROM {COMMISSION_TABLE}
        GROUP BY category
        ORDER BY commission DESC
        LIMIT {top_n}
    """
    rows = con.execute(sql).fetchall()
    result = []
    for r in rows:
        orders = float(r[2] or 0)
        commission = float(r[4] or 0)
        result.append({
            "category":                str(r[0] or "Unknown")[:40],
            "products":                int(r[1] or 0),
            "orders":                  orders,
            "revenue":                 float(r[3] or 0),
            "commission":              commission,
            "avg_commission_per_order": round(commission / orders, 2) if orders else 0.0,
        })
    return result


def get_revenue_by_category(top_n: int = 10) -> dict:
    """
    Revenue by category from commission_report.
    Returns dict with three sorted views: by_commission, by_revenue, by_orders.
    Falls back to shop_name grouping when no products table or no matching itemids.
    """
    if not config.db_path.exists():
        return {}
    con = _connect(read_only=True)
    try:
        if not _has_table(con, COMMISSION_TABLE):
            return {}

        # Try to join with products table for real category names
        cat_col = id_col = None
        if _has_table(con, "products"):
            prod_cols = [r[0].lower() for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()]
            for c in ["global_category1", "global_category2", "category_name", "category"]:
                if c in prod_cols:
                    cat_col = c
                    break
            for c in ["itemid", "item_id", "product_id"]:
                if c in prod_cols:
                    id_col = c
                    break

        if cat_col and id_col:
            # Check if join actually produces category data
            matched = con.execute(f"""
                SELECT COUNT(*) FROM {COMMISSION_TABLE} c
                JOIN products p
                  ON TRY_CAST(c.product_id AS BIGINT) = TRY_CAST(p.{id_col} AS BIGINT)
                WHERE TRIM(p.{cat_col}) != ''
            """).fetchone()[0]
        else:
            matched = 0

        if matched and cat_col and id_col:
            group_expr = f"""
                COALESCE(NULLIF(TRIM(p.{cat_col}), ''), 'Uncategorized')
                FROM {COMMISSION_TABLE} c
                LEFT JOIN products p
                  ON TRY_CAST(c.product_id AS BIGINT) = TRY_CAST(p.{id_col} AS BIGINT)
                WHERE 1=1 -- placeholder
                GROUP BY category
                ORDER BY commission DESC LIMIT {top_n}
            """
            # Use dedicated SQL for the join case
            sql_base = f"""
                SELECT
                    COALESCE(NULLIF(TRIM(p.{cat_col}), ''), 'Uncategorized') AS category,
                    COUNT(DISTINCT c.product_name)  AS products,
                    COUNT(*)                        AS orders,
                    COALESCE(SUM(c.revenue), 0)     AS revenue,
                    COALESCE(SUM(c.commission), 0)  AS commission
                FROM {COMMISSION_TABLE} c
                LEFT JOIN products p
                  ON TRY_CAST(c.product_id AS BIGINT) = TRY_CAST(p.{id_col} AS BIGINT)
                GROUP BY category
            """
        else:
            sql_base = f"""
                SELECT
                    COALESCE(NULLIF(TRIM(shop_name), ''), 'Unknown Shop') AS category,
                    COUNT(DISTINCT product_name)    AS products,
                    COUNT(*)                        AS orders,
                    COALESCE(SUM(revenue), 0)       AS revenue,
                    COALESCE(SUM(commission), 0)    AS commission
                FROM {COMMISSION_TABLE}
                GROUP BY category
            """

        def _fetch(order_col: str) -> list[dict]:
            rows = con.execute(
                f"SELECT * FROM ({sql_base}) t ORDER BY {order_col} DESC LIMIT {top_n}"
            ).fetchall()
            result = []
            for r in rows:
                orders = float(r[2] or 0)
                commission = float(r[4] or 0)
                result.append({
                    "category":                str(r[0] or "Unknown")[:40],
                    "products":                int(r[1] or 0),
                    "orders":                  orders,
                    "revenue":                 float(r[3] or 0),
                    "commission":              commission,
                    "avg_commission_per_order": round(commission / orders, 2) if orders else 0.0,
                })
            return result

        return {
            "by_commission": _fetch("commission"),
            "by_revenue":    _fetch("revenue"),
            "by_orders":     _fetch("orders"),
        }

    except Exception:
        return {}
    finally:
        con.close()


def migrate_legacy_revenue_data() -> dict:
    """
    One-time migration: move revenue_feedback rows written by old importers
    (source='commission_th', source='click_th') into the dedicated tables.
    Safe to call multiple times — deletes matching dates before re-inserting.
    """
    if not config.db_path.exists():
        return {"migrated_commission": 0, "migrated_click_days": 0}

    con = _connect(read_only=False)
    migrated_commission = 0
    migrated_click_days = 0
    try:
        if not _has_table(con, REVENUE_TABLE):
            return {"migrated_commission": 0, "migrated_click_days": 0}

        _init_commission_table(con)
        _init_click_table(con)

        # ── commission_th rows → commission_report ────────────────────────────
        legacy_rows = con.execute(f"""
            SELECT report_date, product_name, product_id, shop_name,
                   revenue, commission,
                   COALESCE(sub_id1,''), COALESCE(sub_id2,''),
                   COALESCE(sub_id3,''), COALESCE(sub_id4,''),
                   COALESCE(sub_id5,''), COALESCE(channel,''),
                   imported_at
            FROM {REVENUE_TABLE}
            WHERE source = 'commission_th'
        """).fetchall()

        if legacy_rows:
            dates = list({r[0] for r in legacy_rows if r[0]})
            for d in dates:
                con.execute(f"DELETE FROM {COMMISSION_TABLE} WHERE report_date=?", [d])
            max_id = con.execute(
                f"SELECT COALESCE(MAX(id), 0) FROM {COMMISSION_TABLE}"
            ).fetchone()[0]
            for i, r in enumerate(legacy_rows):
                con.execute(f"""
                    INSERT INTO {COMMISSION_TABLE}
                    (id, imported_at, report_date, product_name, product_id, shop_name,
                     revenue, commission, sub_id1, sub_id2, sub_id3, sub_id4, sub_id5, channel)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [max_id + i + 1, r[12], r[0], r[1], r[2], r[3],
                      float(r[4] or 0), float(r[5] or 0),
                      r[6], r[7], r[8], r[9], r[10], r[11]])
            migrated_commission = len(legacy_rows)

        # ── click_th rows → click_report ──────────────────────────────────────
        legacy_clicks = con.execute(f"""
            SELECT report_date, COALESCE(SUM(clicks), COUNT(*)) AS clicks,
                   COALESCE(MAX(sub_id),''), COALESCE(MAX(channel),''),
                   MAX(imported_at)
            FROM {REVENUE_TABLE}
            WHERE source = 'click_th'
            GROUP BY report_date
        """).fetchall()

        if legacy_clicks:
            dates = [r[0] for r in legacy_clicks if r[0]]
            for d in dates:
                con.execute(f"DELETE FROM {CLICK_TABLE} WHERE report_date=?", [d])
            max_id = con.execute(
                f"SELECT COALESCE(MAX(id), 0) FROM {CLICK_TABLE}"
            ).fetchone()[0]
            for i, r in enumerate(legacy_clicks):
                con.execute(f"""
                    INSERT INTO {CLICK_TABLE}
                    (id, imported_at, report_date, clicks, sub_id, channel)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [max_id + i + 1, r[4], r[0], float(r[1] or 0), r[2], r[3]])
            migrated_click_days = len(legacy_clicks)

    finally:
        con.close()

    return {"migrated_commission": migrated_commission, "migrated_click_days": migrated_click_days}


def get_revenue_debug() -> dict:
    """Diagnostic: DB path, table list, row counts, latest rows, column names."""
    result: dict = {"db_path": str(config.db_path), "db_exists": config.db_path.exists()}
    if not config.db_path.exists():
        return result

    try:
        con = _connect(read_only=False)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        result["all_tables"] = tables

        for tbl, key in [
            (COMMISSION_TABLE, "commission"),
            (CLICK_TABLE,      "click"),
            (REVENUE_TABLE,    "revenue_feedback"),
        ]:
            if tbl in tables:
                cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                cols = [r[0] for r in con.execute(f"DESCRIBE {tbl}").fetchall()]
                latest = con.execute(
                    f"SELECT * FROM {tbl} ORDER BY id DESC LIMIT 1"
                ).fetchone()
                result[f"{key}_rows"]   = cnt
                result[f"{key}_cols"]   = cols
                result[f"{key}_latest"] = latest
            else:
                result[f"{key}_rows"] = -1  # table missing

        # legacy data check
        if REVENUE_TABLE in tables:
            legacy = con.execute(f"""
                SELECT source, COUNT(*) FROM {REVENUE_TABLE}
                WHERE source IN ('commission_th','click_th')
                GROUP BY source
            """).fetchall()
            result["legacy_in_revenue_feedback"] = {r[0]: r[1] for r in legacy}

        con.close()
    except Exception as exc:
        result["error"] = str(exc)

    return result


def get_revenue_data_source() -> dict:
    """Show real import status: table row counts, date ranges, data availability."""
    if not config.db_path.exists():
        return {"error": "Database not found"}
    con = _connect(read_only=True)
    try:
        result: dict = {}

        if _has_table(con, COMMISSION_TABLE):
            r = con.execute(f"""
                SELECT COUNT(*), MIN(report_date), MAX(report_date),
                       COALESCE(SUM(commission), 0), COUNT(DISTINCT product_name)
                FROM {COMMISSION_TABLE}
            """).fetchone()
            result.update({
                "has_commission":      int(r[0] or 0) > 0,
                "commission_rows":     int(r[0] or 0),
                "commission_from":     r[1] or "—",
                "commission_to":       r[2] or "—",
                "commission_total":    float(r[3] or 0),
                "commission_products": int(r[4] or 0),
            })
        else:
            result.update({"has_commission": False, "commission_rows": 0})

        if _has_table(con, CLICK_TABLE):
            r = con.execute(f"""
                SELECT COUNT(*), MIN(report_date), MAX(report_date), COALESCE(SUM(clicks), 0)
                FROM {CLICK_TABLE}
            """).fetchone()
            result.update({
                "has_clicks":   int(r[0] or 0) > 0,
                "click_rows":   int(r[0] or 0),
                "click_from":   r[1] or "—",
                "click_to":     r[2] or "—",
                "total_clicks": float(r[3] or 0),
            })
        else:
            result.update({"has_clicks": False, "click_rows": 0})

        return result
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 7. recommend_next_products
# ---------------------------------------------------------------------------

def _get_learned_weights(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    if _has_table(con, WEIGHT_TABLE):
        row = con.execute(
            f"SELECT w_sold, w_likes, w_discount, w_shop_rating, w_item_rating "
            f"FROM {WEIGHT_TABLE} ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(zip(DEFAULT_WEIGHTS.keys(), row))
    return DEFAULT_WEIGHTS.copy()


def recommend_next_products(
    top: int = 20,
    table_name: str = "products",
) -> list[dict]:
    """
    Use learned weights to surface new products NOT yet promoted.
    Excludes products already seen in revenue_feedback (already tried).
    Returns products ranked by adaptive opportunity score.
    """
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = _connect(read_only=True)
    weights = _get_learned_weights(con)

    prod_cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}'"
    ).fetchall()]
    col_map   = build_column_map(prod_cols)
    lower_map = {c.lower(): c for c in prod_cols}

    name_col  = col_map.get("product_name") or prod_cols[1]
    sold_col  = col_map.get("sales")
    likes_col = lower_map.get("like") or lower_map.get("likes")
    disc_col  = col_map.get("discount")
    shop_r    = col_map.get("shop_rating")
    item_r    = col_map.get("rating")
    price_col = col_map.get("price")
    cat_col   = lower_map.get("global_category1") or col_map.get("category")

    def _sw(col: str | None, w_key: str) -> str:
        w = weights.get(w_key, 0.15)
        return f"{_safe(col)}*{w}" if col else f"0.0"

    adaptive_score = (
        f"ROUND("
        f"{_sw(sold_col, 'w_sold')} + "
        f"{_sw(likes_col, 'w_likes')} + "
        f"{_sw(disc_col, 'w_discount')} + "
        f"{_sw(shop_r, 'w_shop_rating')}*100 + "
        f"{_sw(item_r, 'w_item_rating')}*100"
        f", 1)"
    )

    excluded: set[str] = set()
    if _has_table(con, REVENUE_TABLE):
        ex_rows = con.execute(
            f"SELECT DISTINCT LOWER(product_name) FROM {REVENUE_TABLE}"
        ).fetchall()
        excluded = {r[0] for r in ex_rows}

    selects = [
        f"{_q(name_col)} AS name",
        f"COALESCE(TRY_CAST({_q(price_col)} AS DOUBLE), 0) AS price" if price_col else "0 AS price",
        f"COALESCE(TRY_CAST({_q(sold_col)} AS DOUBLE), 0) AS sold" if sold_col else "0 AS sold",
        f"{adaptive_score} AS adaptive_score",
    ]
    if cat_col:
        selects.append(f"{_q(cat_col)} AS category")
    else:
        selects.append("NULL AS category")

    candidates = con.execute(f"""
        SELECT {', '.join(selects)}
        FROM {_q(table_name)}
        WHERE {_q(name_col)} IS NOT NULL AND LENGTH({_q(name_col)}) > 5
        ORDER BY adaptive_score DESC
        LIMIT {top * 10}
    """).fetchall()
    con.close()

    results: list[dict] = []
    for row in candidates:
        name = str(row[0] or "")
        if name.lower() in excluded:
            continue
        results.append({
            "name":          name[:60],
            "price":         float(row[1] or 0),
            "sold":          int(float(row[2] or 0)),
            "adaptive_score": float(row[3] or 0),
            "category":      str(row[4] or ""),
            "reason":        "New target — not yet promoted, high adaptive score",
        })
        if len(results) >= top:
            break

    return results


# ---------------------------------------------------------------------------
# 7. adaptive_daily_picks
# ---------------------------------------------------------------------------

def adaptive_daily_picks(
    top: int = 5,
    table_name: str = "products",
) -> dict[str, list[dict]]:
    """
    Daily Picks using learned weights instead of static defaults.
    Returns the same bucket structure as discovery.daily_picks.
    """
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    from .discovery import DAILY_PICKS_CATEGORIES

    con = _connect(read_only=True)
    weights = _get_learned_weights(con)

    prod_cols = [r[0] for r in con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}'"
    ).fetchall()]
    col_map   = build_column_map(prod_cols)
    lower_map = {c.lower(): c for c in prod_cols}

    name_col  = col_map.get("product_name") or prod_cols[1]
    sold_col  = col_map.get("sales")
    likes_col = lower_map.get("like") or lower_map.get("likes")
    disc_col  = col_map.get("discount")
    shop_r    = col_map.get("shop_rating")
    item_r    = col_map.get("rating")
    price_col = col_map.get("price")
    cat1_col  = lower_map.get("global_category1")

    def _sw(col: str | None, w_key: str) -> str:
        w = weights.get(w_key, 0.15)
        return f"COALESCE(TRY_CAST({_q(col)} AS DOUBLE), 0)*{w}" if col else "0.0"

    adaptive = (
        f"ROUND("
        f"{_sw(sold_col, 'w_sold')} + {_sw(likes_col, 'w_likes')} + "
        f"{_sw(disc_col, 'w_discount')} + {_sw(shop_r, 'w_shop_rating')}*100 + "
        f"{_sw(item_r, 'w_item_rating')}*100"
        f", 1)"
    )

    picks: dict[str, list[dict]] = {}

    for bucket, patterns in DAILY_PICKS_CATEGORIES.items():
        if not patterns:
            # Viral TikTok — high likes + low price
            where = (
                f"COALESCE(TRY_CAST({_q(likes_col)} AS DOUBLE), 0) >= 1000 "
                f"AND COALESCE(TRY_CAST({_q(price_col)} AS DOUBLE), 9999) <= 500"
            ) if likes_col and price_col else "1=1"
        elif cat1_col:
            parts = [f"LOWER({_q(cat1_col)}) LIKE '%{p.lower()}%'" for p in patterns]
            where = "(" + " OR ".join(parts) + ")"
        else:
            where = "1=1"

        rows = con.execute(f"""
            SELECT {_q(name_col)} AS name,
                   COALESCE(TRY_CAST({_q(sold_col)} AS DOUBLE), 0) AS sold,
                   COALESCE(TRY_CAST({_q(price_col)} AS DOUBLE), 0) AS price,
                   {adaptive} AS adaptive_score
            FROM {_q(table_name)}
            WHERE {_q(name_col)} IS NOT NULL AND ({where})
            ORDER BY adaptive_score DESC
            LIMIT {top}
        """).fetchall() if sold_col and price_col else []

        picks[bucket] = [
            {"name": str(r[0])[:55], "sold": int(r[1]), "price": float(r[2]),
             "adaptive_score": float(r[3])}
            for r in rows
        ]

    con.close()
    return picks


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_learning_report(data: dict) -> None:
    if "error" in data:
        console.print(f"[red]Error:[/] {data['error']}")
        return

    console.print(Rule("[bold cyan]Learning Report[/]"))

    t = Table(show_header=True, header_style="bold cyan", expand=True)
    t.add_column("Metric",    style="bold white", min_width=28)
    t.add_column("Value",     style="bold green",  min_width=12)
    t.add_column("Detail",    min_width=30)

    snap  = data.get("snapshot_date", "—")
    preds = data.get("predictions_logged", 0)
    revs  = data.get("revenue_data_rows", 0)
    pa    = data.get("product_accuracy")
    oa    = data.get("opportunity_accuracy")
    va    = data.get("viral_accuracy")

    t.add_row("Snapshot Date",        snap,                         f"Predictions: {preds}")
    t.add_row("Revenue Products",     str(revs),                    "Products with real revenue data")

    if pa is not None:
        t.add_row("Product Accuracy",     f"{pa:.1f}%",             f"Top-20 predicted actually earned revenue")
    else:
        t.add_row("Product Accuracy",     "—",                      data.get("warning", "No data"))

    if oa is not None:
        r_opp = data.get("opp_spearman_r", 0)
        t.add_row("Opportunity Accuracy", f"{oa:.1f}%",             f"Spearman r = {r_opp:+.4f}")
    else:
        t.add_row("Opportunity Accuracy", "—",                      "Need revenue data")

    if va is not None:
        r_vir = data.get("viral_spearman_r", 0)
        t.add_row("Viral Accuracy",       f"{va:.1f}%",             f"Spearman r = {r_vir:+.4f}")
    else:
        t.add_row("Viral Accuracy",       "—",                      "Need click data")

    console.print(t)


def print_weight_update(data: dict) -> None:
    if "error" in data:
        console.print(f"[red]Error:[/] {data['error']}")
        return

    console.print(Rule("[bold magenta]Weight Retraining[/]"))

    if "warning" in data:
        console.print(f"[yellow]⚠[/]  {data['warning']}")

    t = Table(show_header=True, header_style="bold magenta", expand=True)
    t.add_column("Signal",      style="bold white",  min_width=16)
    t.add_column("Old Weight",  style="dim",         min_width=12)
    t.add_column("Correlation", style="cyan",        min_width=14)
    t.add_column("New Weight",  style="bold green",  min_width=12)

    old_w  = data.get("old_weights", DEFAULT_WEIGHTS)
    new_w  = data.get("new_weights", DEFAULT_WEIGHTS)
    corrs  = data.get("signal_correlations", {})
    labels = {
        "w_sold":        "Sales Volume",
        "w_likes":       "Social Likes",
        "w_discount":    "Discount %",
        "w_shop_rating": "Shop Rating",
        "w_item_rating": "Item Rating",
    }

    for key, label in labels.items():
        old = old_w.get(key, 0)
        new = new_w.get(key, 0)
        cor = corrs.get(key, 0)
        arrow = "▲" if new > old else ("▼" if new < old else "═")
        t.add_row(
            label,
            f"{old:.4f}",
            f"{cor:+.4f}",
            f"{new:.4f}  {arrow}",
        )

    console.print(t)
    console.print(
        f"Iteration [cyan]{data.get('iteration', '?')}[/] | "
        f"Matched products: [cyan]{data.get('matched_products', 0)}[/] | "
        f"Accuracy score: [green]{data.get('accuracy_score', 0):.1f}%[/]"
    )


def print_profit_learning(data: dict) -> None:
    if "error" in data:
        console.print(f"[red]Error:[/] {data['error']}")
        return

    console.print(Rule("[bold yellow]Profit Learning Analysis[/]"))
    console.print(
        f"Snapshot: [cyan]{data.get('snapshot_date')}[/]  |  "
        f"Threshold: [yellow]฿{data.get('revenue_threshold', 0):,.0f}[/]  |  "
        f"Precision: [green]{data.get('precision')}%[/]  "
        f"Recall: [green]{data.get('recall')}%[/]  "
        f"F1: [green]{data.get('f1_score')}[/]"
    )

    tp = data.get("true_positives", [])
    fp = data.get("false_positives", [])
    fn = data.get("false_negatives", [])

    for section, items, color, icon in [
        ("True Positives (predicted ✓ & earned ✓)", tp, "green",  "✅"),
        ("False Positives (predicted ✓ but failed)", fp, "red",    "❌"),
        ("False Negatives (missed but earned)",      fn, "yellow", "⚠"),
    ]:
        if not items:
            console.print(f"\n[dim]{icon} {section}: (none)[/]")
            continue
        t = Table(title=f"{icon} {section}", header_style=f"bold {color}",
                  show_header=True, expand=True)
        t.add_column("Product",  min_width=35)
        t.add_column("Revenue",  style=color, min_width=12)
        t.add_column("Orders",   min_width=10)
        if "predicted_rank" in items[0]:
            t.add_column("Pred Rank", min_width=10)
        for item in items[:10]:
            rev_str = f"฿{item.get('revenue', 0):,.0f}"
            ord_str = str(int(item.get("orders", 0)))
            row = [item.get("product", "?")[:50], rev_str, ord_str]
            if "predicted_rank" in item:
                row.append(str(item.get("predicted_rank", "?")))
            t.add_row(*row)
        console.print(t)


def print_recommendations(recs: list[dict]) -> None:
    console.print(Rule("[bold green]Next Product Recommendations[/]"))
    if not recs:
        console.print("[dim]No untapped products found.[/]")
        return
    t = Table(show_header=True, header_style="bold green", expand=True)
    t.add_column("#",              style="dim",         min_width=4)
    t.add_column("Product",        style="bold white",  min_width=35)
    t.add_column("Price",          style="cyan",        min_width=10)
    t.add_column("Sold",           style="green",       min_width=10)
    t.add_column("Adaptive Score", style="bold yellow", min_width=14)
    t.add_column("Category",       style="dim",         min_width=20)
    for i, r in enumerate(recs, 1):
        t.add_row(
            str(i),
            r.get("name", "")[:50],
            f"฿{r.get('price', 0):,.0f}",
            f"{r.get('sold', 0):,}",
            f"{r.get('adaptive_score', 0):,.0f}",
            str(r.get("category", ""))[:20],
        )
    console.print(t)


def print_adaptive_picks(picks: dict[str, list[dict]]) -> None:
    console.print(Panel("[bold green]Adaptive Daily Picks[/]  — driven by learned weights", expand=False))
    for bucket, items in picks.items():
        if not items:
            continue
        t = Table(title=f"📦 {bucket}", header_style="bold cyan", expand=True)
        t.add_column("#",              min_width=4,  style="dim")
        t.add_column("Product",        min_width=35, style="bold white")
        t.add_column("Price",          min_width=10, style="cyan")
        t.add_column("Sold",           min_width=10, style="green")
        t.add_column("Adaptive Score", min_width=14, style="bold yellow")
        for i, r in enumerate(items, 1):
            t.add_row(
                str(i),
                r.get("name", "")[:45],
                f"฿{r.get('price', 0):,.0f}",
                f"{r.get('sold', 0):,}",
                f"{r.get('adaptive_score', 0):,.0f}",
            )
        console.print(t)


def print_import_feedback_result(result: dict) -> None:
    console.print(
        f"[bold green]Imported[/] {result.get('rows_imported', 0)} rows "
        f"[source: {result.get('source', '?')}] ← {result.get('path', '')}"
    )
