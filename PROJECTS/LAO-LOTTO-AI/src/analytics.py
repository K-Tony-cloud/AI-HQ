"""
Analytics engine — all number analysis for the Lao lottery dashboard.
"""

from collections import Counter

import numpy as np
import pandas as pd


# ── Frequency ────────────────────────────────────────────────────────────────

def frequency(series: pd.Series) -> pd.DataFrame:
    """Return DataFrame: number | count | pct — sorted by count desc."""
    counts = Counter(series.astype(str))
    total  = sum(counts.values()) or 1
    df = pd.DataFrame([
        {"number": k, "count": v, "pct": round(v / total * 100, 2)}
        for k, v in counts.items()
    ])
    return df.sort_values("count", ascending=False).reset_index(drop=True)


def hot_cold(series: pd.Series, top_n: int = 10) -> tuple[list[str], list[str]]:
    freq = frequency(series)
    return freq.head(top_n)["number"].tolist(), freq.tail(top_n)["number"].tolist()


# ── Heatmap matrix ────────────────────────────────────────────────────────────

def heatmap_matrix(series: pd.Series, digits: int = 2) -> tuple[np.ndarray, list]:
    """
    Build a 10×10 matrix of counts for 00–99.
    Returns (matrix, text_matrix) for Plotly heatmap.
    """
    pool     = 10 ** digits
    side     = 10 ** (digits // 2)
    freq_map = Counter(series.astype(str))
    matrix   = np.zeros((side, side))
    labels   = [[""] * side for _ in range(side)]
    for r in range(side):
        for c in range(side):
            num            = f"{r * side + c:0{digits}d}"
            val            = freq_map.get(num, 0)
            matrix[r][c]   = val
            labels[r][c]   = f"{num}<br>{val}"
    return matrix, labels


# ── Gap analysis ──────────────────────────────────────────────────────────────

def gap_analysis(series: pd.Series) -> pd.DataFrame:
    seen: dict[str, int] = {}
    gaps: dict[str, list[int]] = {}
    for i, val in enumerate(series.astype(str)):
        if val in seen:
            gaps.setdefault(val, []).append(i - seen[val])
        seen[val] = i
    n = len(series)
    rows = []
    for num, g in gaps.items():
        rows.append({
            "number":        num,
            "avg_gap":       round(float(np.mean(g)), 1),
            "max_gap":       int(max(g)),
            "min_gap":       int(min(g)),
            "last_seen_ago": n - 1 - seen.get(num, n - 1),
        })
    return pd.DataFrame(rows).sort_values("avg_gap").reset_index(drop=True)


# ── Overdue ───────────────────────────────────────────────────────────────────

def overdue(series: pd.Series, digits: int = 2) -> pd.DataFrame:
    pool     = {f"{n:0{digits}d}" for n in range(10 ** digits)}
    appeared = set(series.astype(str))
    last_seen: dict[str, int] = {}
    for i, val in enumerate(series.astype(str)):
        last_seen[val] = i
    n = len(series)
    rows = []
    for num in sorted(pool):
        ago = n - 1 - last_seen[num] if num in last_seen else n
        rows.append({
            "number":        num,
            "draws_since":   ago,
            "never_appeared": num not in appeared,
        })
    return pd.DataFrame(rows).sort_values("draws_since", ascending=False).reset_index(drop=True)


# ── Consecutive pairs ─────────────────────────────────────────────────────────

def consecutive_pairs(series: pd.Series) -> pd.DataFrame:
    pairs  = [f"{a}→{b}" for a, b in zip(series.astype(str), series.astype(str).iloc[1:])]
    counts = Counter(pairs)
    df = pd.DataFrame([{"pair": k, "count": v} for k, v in counts.items()])
    return df.sort_values("count", ascending=False).reset_index(drop=True) if not df.empty else df


# ── Rolling frequency ─────────────────────────────────────────────────────────

def rolling_frequency(series: pd.Series, window: int = 20) -> pd.DataFrame:
    unique  = sorted(series.astype(str).unique())
    records = []
    for i in range(window, len(series) + 1):
        w      = series.iloc[i - window:i].astype(str)
        counts = Counter(w)
        rec    = {"period_end": i}
        for num in unique:
            rec[num] = counts.get(num, 0)
        records.append(rec)
    return pd.DataFrame(records)


# ── Day-of-week breakdown ────────────────────────────────────────────────────

def dow_frequency(df: pd.DataFrame, date_col: str = "draw_date", num_col: str = "last_2") -> pd.DataFrame:
    """Frequency of each number by day of week."""
    if date_col not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["dow"] = pd.to_datetime(tmp[date_col]).dt.day_name()
    counts = tmp.groupby(["dow", num_col]).size().reset_index(name="count")
    return counts


def draws_per_dow(df: pd.DataFrame, date_col: str = "draw_date") -> pd.DataFrame:
    """How many draws fall on each day of the week."""
    if date_col not in df.columns:
        return pd.DataFrame()
    days  = pd.to_datetime(df[date_col]).dt.day_name()
    order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    cnt   = days.value_counts().reindex(order, fill_value=0).reset_index()
    cnt.columns = ["day", "count"]
    return cnt


# ── Monthly breakdown ────────────────────────────────────────────────────────

def draws_per_month(df: pd.DataFrame, date_col: str = "draw_date") -> pd.DataFrame:
    if date_col not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["month"] = pd.to_datetime(tmp[date_col]).dt.to_period("M").astype(str)
    return tmp.groupby("month").size().reset_index(name="count").sort_values("month")


def monthly_num_freq(
    df: pd.DataFrame,
    num_col: str = "last_2",
    date_col: str = "draw_date",
) -> pd.DataFrame:
    """Pivot: month × number frequency."""
    if date_col not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["month"] = pd.to_datetime(tmp[date_col]).dt.month
    return tmp.groupby(["month", num_col]).size().reset_index(name="count")


# ── Digit split ───────────────────────────────────────────────────────────────

def digit_split(series: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split 2-digit numbers into units and tens distributions."""
    padded = series.astype(str).str.zfill(2)
    units  = frequency(padded.str[-1])
    tens   = frequency(padded.str[0])
    return units, tens


# ── Summary stats ─────────────────────────────────────────────────────────────

def summary(series: pd.Series, df: pd.DataFrame | None = None) -> dict:
    freq_df   = frequency(series)
    hot, cold = hot_cold(series, 1)
    return {
        "total_draws":     len(series),
        "unique_numbers":  freq_df["number"].nunique(),
        "hottest":         hot[0] if hot else "—",
        "coldest":         cold[0] if cold else "—",
        "hottest_count":   int(freq_df.iloc[0]["count"]) if not freq_df.empty else 0,
        "latest_date": (
            pd.to_datetime(df["draw_date"]).max().strftime("%d %b %Y")
            if df is not None and "draw_date" in df.columns else "—"
        ),
    }
