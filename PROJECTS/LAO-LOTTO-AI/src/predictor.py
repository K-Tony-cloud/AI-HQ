"""
ML prediction models for the Lao lottery dashboard.
All models take a pd.Series of past results and return ranked predictions.
"""

import warnings
import numpy as np
import pandas as pd
from collections import Counter
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")


def _encode(series: pd.Series, lookback: int):
    vals    = series.astype(str).tolist()
    le      = LabelEncoder()
    encoded = le.fit_transform(vals)
    X, y    = [], []
    for i in range(lookback, len(encoded)):
        X.append(encoded[i - lookback:i])
        y.append(encoded[i])
    return np.array(X), np.array(y), le


def predict_next_rf(series: pd.Series, lookback: int = 5, top_n: int = 5) -> list[dict]:
    if len(series) < lookback + 10:
        return _fallback(series, top_n)
    X, y, le = _encode(series, lookback)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)
    last = le.transform(series.astype(str).tail(lookback).tolist())
    proba = clf.predict_proba([last])[0]
    idx = np.argsort(proba)[::-1][:top_n]
    return [{"number": str(le.inverse_transform([i])[0]), "probability": round(float(proba[i]) * 100, 2), "method": "Random Forest"} for i in idx]


def predict_next_lr(series: pd.Series, lookback: int = 5, top_n: int = 5) -> list[dict]:
    if len(series) < lookback + 10:
        return _fallback(series, top_n)
    X, y, le = _encode(series, lookback)
    clf = LogisticRegression(max_iter=500, random_state=42)
    clf.fit(X, y)
    last = le.transform(series.astype(str).tail(lookback).tolist())
    proba = clf.predict_proba([last])[0]
    idx = np.argsort(proba)[::-1][:top_n]
    return [{"number": str(le.inverse_transform([i])[0]), "probability": round(float(proba[i]) * 100, 2), "method": "Logistic Regression"} for i in idx]


def predict_markov(series: pd.Series, top_n: int = 5) -> list[dict]:
    vals = series.astype(str).tolist()
    trans: dict[str, Counter] = {}
    for a, b in zip(vals, vals[1:]):
        trans.setdefault(a, Counter())[b] += 1
    last = vals[-1]
    if last not in trans:
        return _fallback(series, top_n)
    counts = trans[last]
    total  = sum(counts.values())
    return [{"number": n, "probability": round(c / total * 100, 2), "method": "Markov Chain"}
            for n, c in counts.most_common(top_n)]


def ensemble_predict(series: pd.Series, lookback: int = 5, top_n: int = 10) -> pd.DataFrame:
    w    = {"Random Forest": 0.4, "Logistic Regression": 0.3, "Markov Chain": 0.3}
    agg: dict[str, float] = {}
    for fn, method in [(predict_next_rf,"Random Forest"), (predict_next_lr,"Logistic Regression"), (predict_markov,"Markov Chain")]:
        kw = {"top_n": 20} if method == "Markov Chain" else {"lookback": lookback, "top_n": 20}
        for p in fn(series, **kw):
            agg[p["number"]] = agg.get(p["number"], 0) + p["probability"] * w[method]
    df = pd.DataFrame([{"number": k, "score": round(v, 2)} for k, v in agg.items()])
    return df.sort_values("score", ascending=False).head(top_n).reset_index(drop=True)


def _fallback(series: pd.Series, top_n: int) -> list[dict]:
    counts = Counter(series.astype(str))
    total  = sum(counts.values()) or 1
    return [{"number": n, "probability": round(c / total * 100, 2), "method": "Frequency"} for n, c in counts.most_common(top_n)]


def predict_all_types(df: pd.DataFrame, lookback: int = 5, top_n: int = 5) -> dict[str, list[dict]]:
    """
    Run ensemble predictions for all 5 digit types.
    Returns { digit_type: [ {number, probability}, ... ] }
    """
    from src.database import DIGIT_COL
    results = {}
    for dtype, col in DIGIT_COL.items():
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if series.empty:
            continue
        ens = ensemble_predict(series, lookback=lookback, top_n=top_n)
        results[dtype] = [{"number": r["number"], "probability": r["score"]} for _, r in ens.iterrows()]
    return results
