"""
Thai Stock lottery (หวยหุ้นไทย) data fetcher.
Source: SET Composite Index (^SET.BK) via yfinance.

Lottery digits are derived from the SET index OHLC values:
  open  session → เปิดเช้า  → last 2 digits of daily Open price
  close session → ปิดบ่าย  → last 2 digits of daily Close price

Only trading days (Mon-Fri, non-holidays) appear in yfinance data.
"""

from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

TICKER    = "^SET.BK"
SESSIONS  = {"open": "Open", "close": "Close"}


def _fetch_ohlc(period: str = "max") -> pd.DataFrame:
    raw = yf.download(TICKER, period=period, interval="1d", progress=False, auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"yfinance returned no data for {TICKER}")
    # Flatten multi-level columns (yfinance ≥ 0.2 returns MultiIndex)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    return raw[["Open", "Close"]].dropna()


def _to_rows(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Convert OHLC DataFrame to session rows."""
    records = []
    for dt, row in ohlc.iterrows():
        date_str = str(dt)[:10]
        for sess, col in SESSIONS.items():
            records.append({
                "draw_date": date_str,
                "session":   sess,
                "set_value": float(row[col]),
            })
    return pd.DataFrame(records)


def fetch_latest(progress_cb=None) -> int:
    """Fetch only data newer than what's already in the DB."""
    from src import stock_db as db
    latest = db.meta().get("latest")
    period = "1mo" if latest else "max"
    ohlc   = _fetch_ohlc(period=period)
    if latest:
        ohlc = ohlc[ohlc.index > pd.Timestamp(latest)]
    if ohlc.empty:
        return 0
    rows_df = _to_rows(ohlc)
    if progress_cb:
        progress_cb(len(rows_df))
    return db.upsert(rows_df)


def fetch_all(progress_cb=None) -> int:
    """Fetch full history (back to 1996)."""
    from src import stock_db as db
    ohlc    = _fetch_ohlc(period="max")
    rows_df = _to_rows(ohlc)
    if progress_cb:
        progress_cb(len(rows_df))
    db.upsert(rows_df)
    return db.row_count()
