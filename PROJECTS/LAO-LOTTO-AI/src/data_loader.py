import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

LOTTERY_TYPES = {
    "lao_national": "Lao National Lottery (ສະຫວັນເດດ)",
    "vietlao": "VietLao Lottery",
    "stock": "Stock Lottery (ຫວຍຮຸ້ນ)",
}

SAMPLE_COLUMNS = {
    "lao_national": ["date", "six_digit", "last_3", "last_2"],
    "vietlao":      ["date", "result_2d", "result_3d"],
    "stock":        ["date", "session", "result_2d", "result_3d"],
}

# Default analysis column per lottery type
DEFAULT_COL = {
    "lao_national": "last_2",
    "vietlao":      "result_2d",
    "stock":        "result_2d",
}


def load_csv(filepath: str | Path) -> pd.DataFrame:
    df = pd.read_csv(filepath, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def load_excel(filepath: str | Path, sheet_name: int | str = 0) -> pd.DataFrame:
    df = pd.read_excel(filepath, sheet_name=sheet_name, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def load_uploaded_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError(f"Unsupported file type: {uploaded_file.name}")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.sort_values("date", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def generate_sample_data(lottery_type: str = "lao_national", n: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range(end=datetime.today(), periods=n, freq="W")

    if lottery_type == "lao_national":
        six = [f"{x:06d}" for x in rng.integers(100000, 999999, n)]
        return pd.DataFrame({
            "date":      dates,
            "six_digit": six,
            "last_3":    [s[-3:] for s in six],
            "last_2":    [s[-2:] for s in six],
        })
    elif lottery_type == "vietlao":
        return pd.DataFrame({
            "date": dates,
            "result_2d": [f"{x:02d}" for x in rng.integers(0, 100, n)],
            "result_3d": [f"{x:03d}" for x in rng.integers(0, 1000, n)],
        })
    elif lottery_type == "stock":
        sessions = ["morning", "afternoon", "evening"]
        rows = []
        for date in dates:
            for session in sessions:
                rows.append({
                    "date": date,
                    "session": session,
                    "result_2d": f"{rng.integers(0, 100):02d}",
                    "result_3d": f"{rng.integers(0, 1000):03d}",
                })
        return pd.DataFrame(rows)

    raise ValueError(f"Unknown lottery type: {lottery_type}")


def load_real_data() -> pd.DataFrame | None:
    """Load scraped Lao National results from cache, or None if not yet fetched."""
    from src.scraper import load_cached
    return load_cached()


def extract_digits(series: pd.Series, n_digits: int = 2) -> pd.Series:
    return series.astype(str).str[-n_digits:].str.zfill(n_digits)
