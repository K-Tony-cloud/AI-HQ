"""
Scraper for https://lotto.thaiorc.com/lao/stats/lottery-years20.php

Columns produced:
  date        – Gregorian datetime
  date_be     – original Buddhist Era date string (DD/MM/YYYY)
  six_digit   – 6-digit jackpot number (zero-padded string)
  last_3      – last 3 digits (string)
  last_2      – last 2 digits (string)
"""

import re
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

_BASE_URL  = "https://lotto.thaiorc.com/lao/stats/lottery-years20.php"
_CACHE     = Path(__file__).parent.parent / "data" / "raw" / "lao_national_real.csv"
_HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
}


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> datetime | None:
    """'[DD/MM/YYYY_BE]'  →  CE datetime, or None if unparseable."""
    cleaned = raw.strip().strip("[]")
    try:
        d, m, y_be = [int(x) for x in cleaned.split("/")]
        return datetime(y_be - 543, m, d)
    except Exception:
        return None


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(page: int, delay: float = 0.4) -> str:
    time.sleep(delay)
    params = {} if page == 1 else {"pg": page}
    resp = requests.get(_BASE_URL, params=params, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        six = tds[1].get_text(strip=True)
        if not re.fullmatch(r"\d{3,6}", six):
            continue
        dt = _parse_date(tds[0].get_text(strip=True))
        if dt is None:
            continue
        rows.append({
            "date":      dt,
            "date_be":   tds[0].get_text(strip=True).strip("[]"),
            "six_digit": six.zfill(6),
            "last_3":    tds[2].get_text(strip=True).zfill(3),
            "last_2":    tds[3].get_text(strip=True).zfill(2),
        })
    return rows


def _total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    nums = [int(m.group(1)) for a in soup.find_all("a", href=True)
            if (m := re.search(r"pg=(\d+)", a["href"]))]
    return max(nums) if nums else 1


def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["date", "date_be", "six_digit", "last_3", "last_2"])
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["date"])
    df["date"]      = pd.to_datetime(df["date"])
    # Force string type + zero-padding so CSV round-trips correctly
    df["six_digit"] = df["six_digit"].astype(str).str.zfill(6)
    df["last_3"]    = df["last_3"].astype(str).str.zfill(3)
    df["last_2"]    = df["last_2"].astype(str).str.zfill(2)
    return df.sort_values("date", ascending=False).reset_index(drop=True)


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_all(
    progress_cb=None,
    max_pages: int | None = None,
    delay: float = 0.4,
) -> pd.DataFrame:
    """
    Fetch every page (up to max_pages).
    progress_cb(current_page, total_pages) is called after each page.
    """
    html1 = _get(1, delay=delay)
    total = _total_pages(html1)
    if max_pages:
        total = min(total, max_pages)

    all_rows = _parse(html1)
    if progress_cb:
        progress_cb(1, total)

    for pg in range(2, total + 1):
        all_rows.extend(_parse(_get(pg, delay=delay)))
        if progress_cb:
            progress_cb(pg, total)

    return _to_df(all_rows)


def scrape_latest(progress_cb=None, delay: float = 0.4) -> tuple[pd.DataFrame, int]:
    """
    Incremental fetch: stops once page results are already in the cache.
    Returns (merged_df, new_rows_added).
    """
    cached = load_cached()
    latest_cached = cached["date"].max() if (cached is not None and not cached.empty) else None

    html1 = _get(1, delay=delay)
    total = _total_pages(html1)
    new_rows = _parse(html1)
    if progress_cb:
        progress_cb(1, total)

    for pg in range(2, total + 1):
        if latest_cached is not None and new_rows:
            if min(r["date"] for r in new_rows) <= latest_cached:
                break
        new_rows.extend(_parse(_get(pg, delay=delay)))
        if progress_cb:
            progress_cb(pg, total)

    new_df = _to_df(new_rows)

    if cached is not None and not cached.empty:
        merged = pd.concat([new_df, cached], ignore_index=True)
        merged = (merged
                  .drop_duplicates(subset=["date"])
                  .sort_values("date", ascending=False)
                  .reset_index(drop=True))
        added = max(0, len(merged) - len(cached))
    else:
        merged = new_df
        added  = len(merged)

    return merged, added


def load_cached() -> pd.DataFrame | None:
    if not _CACHE.exists():
        return None
    return pd.read_csv(
        _CACHE,
        parse_dates=["date"],
        dtype={"six_digit": str, "last_3": str, "last_2": str, "date_be": str},
    )


def save(df: pd.DataFrame) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_CACHE, index=False)


def cache_path() -> Path:
    return _CACHE
