import pandas as pd
import numpy as np
from collections import Counter


def frequency_table(series: pd.Series) -> pd.DataFrame:
    counts = Counter(series.astype(str))
    total = sum(counts.values())
    df = pd.DataFrame([
        {"number": k, "count": v, "pct": round(v / total * 100, 2)}
        for k, v in sorted(counts.items())
    ])
    return df.sort_values("count", ascending=False).reset_index(drop=True)


def hot_cold(series: pd.Series, top_n: int = 10) -> tuple[list, list]:
    freq = frequency_table(series)
    hot = freq.head(top_n)["number"].tolist()
    cold = freq.tail(top_n)["number"].tolist()
    return hot, cold


def gap_analysis(series: pd.Series) -> pd.DataFrame:
    seen_last: dict[str, int] = {}
    gaps: dict[str, list[int]] = {}
    for i, val in enumerate(series.astype(str)):
        if val in seen_last:
            gaps.setdefault(val, []).append(i - seen_last[val])
        seen_last[val] = i

    rows = []
    for num, g in gaps.items():
        rows.append({
            "number": num,
            "avg_gap": round(np.mean(g), 1),
            "max_gap": max(g),
            "min_gap": min(g),
            "last_seen_ago": len(series) - 1 - seen_last.get(num, len(series) - 1),
        })
    return pd.DataFrame(rows).sort_values("avg_gap").reset_index(drop=True)


def consecutive_pairs(series: pd.Series) -> pd.DataFrame:
    pairs = [f"{a}-{b}" for a, b in zip(series.astype(str), series.astype(str).iloc[1:])]
    counts = Counter(pairs)
    df = pd.DataFrame([{"pair": k, "count": v} for k, v in counts.items()])
    return df.sort_values("count", ascending=False).reset_index(drop=True)


def rolling_frequency(series: pd.Series, window: int = 20) -> pd.DataFrame:
    unique = sorted(series.astype(str).unique())
    records = []
    for i in range(window, len(series) + 1):
        window_vals = series.iloc[i - window:i].astype(str)
        counts = Counter(window_vals)
        record = {"period_end": i}
        for num in unique:
            record[num] = counts.get(num, 0)
        records.append(record)
    return pd.DataFrame(records)


def overdue_numbers(series: pd.Series, pool: range | None = None) -> pd.DataFrame:
    if pool is None:
        pool = range(100)
    all_nums = {f"{n:02d}" for n in pool}
    appeared = set(series.astype(str))
    never = all_nums - appeared

    last_seen: dict[str, int] = {}
    for i, val in enumerate(series.astype(str)):
        last_seen[val] = i

    rows = []
    n = len(series)
    for num in sorted(all_nums):
        ago = n - 1 - last_seen[num] if num in last_seen else n
        rows.append({"number": num, "draws_since_last": ago, "never_appeared": num in never})
    return pd.DataFrame(rows).sort_values("draws_since_last", ascending=False).reset_index(drop=True)
