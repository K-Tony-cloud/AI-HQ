"""
Hanoi (VietLao) lottery scraper.
Source: https://lotto.thaiorc.com/hanoi/stats/lottery-years20.php

Table columns: date | five_digit | alt_prize | last_3 | last_2
- five_digit = main 5-digit prize (last_3 is last 3 digits of this)
- last_2 = last 2 digits of the alt_prize column
"""

import re
import time
from datetime import datetime

import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://lotto.thaiorc.com/hanoi/stats/lottery-years20.php"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
}


def _get(page: int, delay: float = 0.4) -> str:
    time.sleep(delay)
    params = {} if page == 1 else {"pg": page}
    resp   = requests.get(BASE_URL, params=params, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _parse_date(raw: str) -> datetime | None:
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
        if len(tds) < 5:
            continue
        date_raw = tds[0].get_text(strip=True)
        five_raw = tds[1].get_text(strip=True)   # main 5-digit prize
        alt_raw  = tds[2].get_text(strip=True)   # alt 5-digit prize
        l3_raw   = tds[3].get_text(strip=True)   # last_3
        l2_raw   = tds[4].get_text(strip=True)   # last_2

        # Validate main 5-digit number
        if not re.fullmatch(r"\d{3,5}", five_raw):
            continue
        dt = _parse_date(date_raw)
        if dt is None:
            continue

        five = five_raw.zfill(5)
        rows.append({
            "date":      dt,
            "date_be":   date_raw.strip("[]"),
            "five_digit": five,
            "last_3":    l3_raw.zfill(3),
            "last_2":    l2_raw.zfill(2),
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
        return pd.DataFrame(columns=["date", "date_be", "five_digit", "last_3", "last_2"])
    df = pd.DataFrame(rows).drop_duplicates(subset=["date"])
    df["date"] = pd.to_datetime(df["date"])
    df["five_digit"] = df["five_digit"].astype(str).str.zfill(5)
    df["last_3"]     = df["last_3"].astype(str).str.zfill(3)
    df["last_2"]     = df["last_2"].astype(str).str.zfill(2)
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def scrape_latest(progress_cb=None, delay: float = 0.4) -> int:
    from src import hanoi_db as db
    latest_in_db = db.meta().get("latest")
    html1  = _get(1, delay=delay)
    total  = _total_pages(html1)
    rows   = _parse(html1)
    if progress_cb:
        progress_cb(1, total)
    for pg in range(2, total + 1):
        if latest_in_db and rows:
            if min(r["date"] for r in rows) <= pd.Timestamp(latest_in_db):
                break
        rows.extend(_parse(_get(pg, delay=delay)))
        if progress_cb:
            progress_cb(pg, total)
    return db.upsert(_to_df(rows))


def scrape_all(progress_cb=None, max_pages: int | None = None, delay: float = 0.4) -> int:
    from src import hanoi_db as db
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
