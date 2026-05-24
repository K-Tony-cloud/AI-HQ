import numpy as np
import pandas as pd
from collections import Counter
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
import warnings

warnings.filterwarnings("ignore")


def _encode_sequence(series: pd.Series, lookback: int = 5):
    vals = series.astype(str).tolist()
    le = LabelEncoder()
    encoded = le.fit_transform(vals)
    X, y = [], []
    for i in range(lookback, len(encoded)):
        X.append(encoded[i - lookback:i])
        y.append(encoded[i])
    return np.array(X), np.array(y), le


def predict_next_rf(series: pd.Series, lookback: int = 5, top_n: int = 5) -> list[dict]:
    if len(series) < lookback + 10:
        return _fallback_frequency(series, top_n)

    X, y, le = _encode_sequence(series, lookback)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)

    last_window = le.transform(series.astype(str).tail(lookback).tolist())
    proba = clf.predict_proba([last_window])[0]
    top_idx = np.argsort(proba)[::-1][:top_n]

    results = []
    for idx in top_idx:
        num = le.inverse_transform([idx])[0]
        results.append({"number": num, "probability": round(float(proba[idx]) * 100, 2), "method": "Random Forest"})
    return results


def predict_next_lr(series: pd.Series, lookback: int = 5, top_n: int = 5) -> list[dict]:
    if len(series) < lookback + 10:
        return _fallback_frequency(series, top_n)

    X, y, le = _encode_sequence(series, lookback)
    clf = LogisticRegression(max_iter=500, random_state=42)
    clf.fit(X, y)

    last_window = le.transform(series.astype(str).tail(lookback).tolist())
    proba = clf.predict_proba([last_window])[0]
    top_idx = np.argsort(proba)[::-1][:top_n]

    results = []
    for idx in top_idx:
        num = le.inverse_transform([idx])[0]
        results.append({"number": num, "probability": round(float(proba[idx]) * 100, 2), "method": "Logistic Regression"})
    return results


def predict_markov(series: pd.Series, top_n: int = 5) -> list[dict]:
    vals = series.astype(str).tolist()
    transitions: dict[str, Counter] = {}
    for a, b in zip(vals, vals[1:]):
        transitions.setdefault(a, Counter())[b] += 1

    last = vals[-1]
    if last not in transitions:
        return _fallback_frequency(series, top_n)

    counts = transitions[last]
    total = sum(counts.values())
    results = []
    for num, cnt in counts.most_common(top_n):
        results.append({"number": num, "probability": round(cnt / total * 100, 2), "method": "Markov Chain"})
    return results[:top_n]


def _fallback_frequency(series: pd.Series, top_n: int) -> list[dict]:
    counts = Counter(series.astype(str))
    total = sum(counts.values())
    return [
        {"number": num, "probability": round(cnt / total * 100, 2), "method": "Frequency (fallback)"}
        for num, cnt in counts.most_common(top_n)
    ]


def ensemble_predict(series: pd.Series, lookback: int = 5, top_n: int = 10) -> pd.DataFrame:
    results: dict[str, float] = {}
    weight = {"Random Forest": 0.4, "Logistic Regression": 0.3, "Markov Chain": 0.3}

    for pred_fn, method in [
        (predict_next_rf, "Random Forest"),
        (predict_next_lr, "Logistic Regression"),
        (predict_markov, "Markov Chain"),
    ]:
        preds = pred_fn(series, **({} if method == "Markov Chain" else {"lookback": lookback}), top_n=20)
        for p in preds:
            results[p["number"]] = results.get(p["number"], 0) + p["probability"] * weight[method]

    df = pd.DataFrame([{"number": k, "score": round(v, 2)} for k, v in results.items()])
    df.sort_values("score", ascending=False, inplace=True)
    return df.head(top_n).reset_index(drop=True)
