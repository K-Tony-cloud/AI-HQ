"""
Scraper — https://lotto.thaiorc.com/lao/stats/lottery-years20.php

Writes directly to SQLite via src.database.
Public API:
    scrape_latest(progress_cb)   → (new_rows: int)
    scrape_all(max_pages, progress_cb, delay)  → (total_rows: int)
"""

import re
import time
from datetime import datetime

import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://lotto.thaiorc.com/lao/stats/lottery-years20.php"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
}


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _get(page: int, delay: float = 0.4) -> str:
    time.sleep(delay)
    params = {} if page == 1 else {"pg": page}
    resp   = requests.get(BASE_URL, params=params, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> datetime | None:
    """'[DD/MM/YYYY_BE]' → CE datetime."""
    cleaned = raw.strip().strip("[]")
    try:
        d, m, y_be = [int(x) for x in cleaned.split("/")]
        return datetime(y_be - 543, m, d)
    except Exception:
        return None


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
    nums = [
        int(m.group(1))
        for a in soup.find_all("a", href=True)
        if (m := re.search(r"pg=(\d+)", a["href"]))
    ]
    return max(nums) if nums else 1


def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["date", "date_be", "six_digit", "last_3", "last_2"])
    df = pd.DataFrame(rows).drop_duplicates(subset=["date"])
    df["date"]      = pd.to_datetime(df["date"])
    df["six_digit"] = df["six_digit"].astype(str).str.zfill(6)
    df["last_3"]    = df["last_3"].astype(str).str.zfill(3)
    df["last_2"]    = df["last_2"].astype(str).str.zfill(2)
    return df.sort_values("date", ascending=False).reset_index(drop=True)


# ── Public API ─────────────────────────────────────────────────────────────────

def scrape_latest(progress_cb=None, delay: float = 0.4) -> int:
    """
    Incremental fetch: stops when it reaches draws already in the DB.
    Returns count of newly inserted rows.
    """
    from src import database as db

    latest_in_db = db.meta().get("latest")

    html1  = _get(1, delay=delay)
    total  = _total_pages(html1)
    rows   = _parse(html1)
    if progress_cb:
        progress_cb(1, total)

    for pg in range(2, total + 1):
        if latest_in_db and rows:
            earliest_fetched = min(r["date"] for r in rows)
            if pd.Timestamp(earliest_fetched) <= pd.Timestamp(latest_in_db):
                break
        rows.extend(_parse(_get(pg, delay=delay)))
        if progress_cb:
            progress_cb(pg, total)

    df = _to_df(rows)
    return db.upsert(df)


def scrape_all(progress_cb=None, max_pages: int | None = None, delay: float = 0.4) -> int:
    """
    Full fetch of all pages (up to max_pages).
    Returns total rows now in the DB.
    """
    from src import database as db

    html1 = _get(1, delay=delay)
    total = _total_pages(html1)
    if max_pages:
        total = min(total, max_pages)

    rows = _parse(html1)
    if progress_cb:
        progress_cb(1, total)

    for pg in range(2, total + 1):
        rows.extend(_parse(_get(pg, delay=delay)))
        if progress_cb:
            progress_cb(pg, total)

    db.upsert(_to_df(rows))
    return db.row_count()
