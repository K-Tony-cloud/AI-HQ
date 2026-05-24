import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from src.data_loader import load_uploaded_file, generate_sample_data, LOTTERY_TYPES
from src.predictor import predict_next_rf, predict_next_lr, predict_markov, ensemble_predict
from src.ui_components import inject_css, metric_row, lottery_balls, section_label

st.set_page_config(page_title="Prediction", page_icon="🤖", layout="wide")
inject_css()

st.markdown('<h2 style="margin-bottom:.2rem;">🤖 Number Prediction</h2>', unsafe_allow_html=True)
st.caption("Predictions are statistical patterns only — lottery draws are random. For entertainment.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Data Source")
    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k])
    use_sample   = st.checkbox("Use sample data", value=True)
    uploaded     = None
    if not use_sample:
        uploaded = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])
    st.markdown("---")
    st.header("Settings")
    target_col = st.text_input("Column to predict", value="result_2d")
    lookback   = st.slider("Lookback window", 3, 20, 5)
    top_n      = st.slider("Top N suggestions", 3, 15, 7)

# ── Load ──────────────────────────────────────────────────────────────────────
df = None
if use_sample:
    df = generate_sample_data(lottery_type, n=300)
    st.info("Using sample data — upload yours in Data Manager for real predictions.")
elif uploaded:
    try:
        df = load_uploaded_file(uploaded)
        st.success(f"Loaded {len(df):,} rows from **{uploaded.name}**")
    except Exception as e:
        st.error(str(e))

if df is None:
    st.warning("Upload a file or enable sample data.")
    st.stop()

if target_col not in df.columns:
    candidates = [c for c in df.columns if df[c].dtype == object] or df.columns.tolist()
    target_col = candidates[0]
    st.warning(f"Column not found — using **{target_col}**.")

series = df[target_col].dropna()

# ── Ensemble ──────────────────────────────────────────────────────────────────
section_label("Ensemble Prediction")
with st.spinner("Running models…"):
    ens_df = ensemble_predict(series, lookback=lookback, top_n=top_n)

lottery_balls(ens_df["number"].tolist(), ens_df["score"].tolist())

# Score bar chart
fig = go.Figure(go.Bar(
    x=ens_df["number"], y=ens_df["score"],
    marker=dict(
        color=ens_df["score"],
        colorscale="Reds",
        showscale=False,
        line_width=0,
    ),
))
fig.update_layout(
    height=280, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
    font_color="#F0F6FC",
    xaxis_title="Number", yaxis_title="Ensemble score",
    margin=dict(t=10, b=40),
)
st.plotly_chart(fig, use_container_width=True)

metric_row([
    ("🥇", ens_df.iloc[0]["number"],          "top pick"),
    ("📈", f"{ens_df.iloc[0]['score']:.1f}%",  "top score"),
    ("🎯", f"{len(ens_df)}",                   "candidates"),
    ("🔁", str(lookback),                      "lookback window"),
])

# ── Individual models ─────────────────────────────────────────────────────────
section_label("Individual Model Breakdown")
tab_rf, tab_lr, tab_mk, tab_compare = st.tabs(
    ["Random Forest", "Logistic Regression", "Markov Chain", "Compare All"]
)


def _model_view(preds: list[dict]) -> None:
    if not preds:
        st.warning("Not enough data.")
        return
    pdf = pd.DataFrame(preds)
    lottery_balls(pdf["number"].tolist(), pdf["probability"].tolist())
    fig_m = go.Figure(go.Bar(
        x=pdf["number"], y=pdf["probability"],
        marker=dict(color=pdf["probability"], colorscale="Blues", showscale=False, line_width=0),
    ))
    fig_m.update_layout(height=240, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                        font_color="#F0F6FC", margin=dict(t=10))
    st.plotly_chart(fig_m, use_container_width=True)


with tab_rf:
    rf = predict_next_rf(series, lookback=lookback, top_n=top_n)
    _model_view(rf)

with tab_lr:
    lr = predict_next_lr(series, lookback=lookback, top_n=top_n)
    _model_view(lr)

with tab_mk:
    mk = predict_markov(series, top_n=top_n)
    _model_view(mk)

with tab_compare:
    section_label("Side-by-side comparison")
    rf_s  = pd.DataFrame(predict_next_rf(series, lookback=lookback, top_n=top_n)).rename(columns={"probability": "RF %"})
    lr_s  = pd.DataFrame(predict_next_lr(series, lookback=lookback, top_n=top_n)).rename(columns={"probability": "LR %"})
    mk_s  = pd.DataFrame(predict_markov(series, top_n=top_n)).rename(columns={"probability": "MK %"})
    ens_s = ens_df.rename(columns={"score": "Ensemble"})

    merged = (
        ens_s[["number", "Ensemble"]]
        .merge(rf_s[["number", "RF %"]],  on="number", how="outer")
        .merge(lr_s[["number", "LR %"]],  on="number", how="outer")
        .merge(mk_s[["number", "MK %"]],  on="number", how="outer")
        .fillna(0)
        .sort_values("Ensemble", ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(merged.style.background_gradient(subset=["Ensemble", "RF %", "LR %", "MK %"],
                                                   cmap="Reds"), use_container_width=True)

# ── Recent draws ──────────────────────────────────────────────────────────────
section_label("Recent Draws")
cols = [target_col] + (["date"] if "date" in df.columns else [])
st.dataframe(df[cols].tail(20).reset_index(drop=True), use_container_width=True)
