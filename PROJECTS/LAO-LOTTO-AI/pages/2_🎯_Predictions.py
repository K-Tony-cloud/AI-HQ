"""Predictions — ensemble lottery balls + model breakdown."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from src import database as db
from src.predictor import predict_next_rf, predict_next_lr, predict_markov, ensemble_predict
from src.ui_components import inject_css, metric_row, lottery_balls, section_label, chart_style

st.set_page_config(page_title="Predictions · LAO LOTTO AI", page_icon="🎯", layout="wide")
inject_css()

# ── Load ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _load():
    return db.load()

df = _load()

st.markdown('<h2 style="margin-bottom:.1rem;">🎯 AI Predictions</h2>', unsafe_allow_html=True)
st.caption("Statistical pattern analysis — lottery draws are random. For entertainment only.")

if df.empty:
    st.warning("No data — go to ⚙ Settings and fetch results first.")
    st.stop()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙ Controls")
    digit_choice = st.radio("Predict on", ["Last 2 digits", "Last 3 digits"])
    num_col  = "last_2" if "2" in digit_choice else "last_3"
    lookback = st.slider("Lookback window", 3, 20, 5, help="How many past draws each model uses as input")
    top_n    = st.slider("Top N picks", 3, 15, 7)
    st.markdown("---")
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

series = df[num_col].dropna()

# ── Ensemble ──────────────────────────────────────────────────────────────────
section_label("Ensemble Prediction — combined model scores")
with st.spinner("Running models..."):
    ens_df = ensemble_predict(series, lookback=lookback, top_n=top_n)

lottery_balls(ens_df["number"].tolist(), ens_df["score"].tolist())

fig_ens = go.Figure(go.Bar(
    x=ens_df["number"], y=ens_df["score"],
    marker=dict(
        color=ens_df["score"],
        colorscale=[[0, "#30363D"], [0.5, "#C0392B"], [1, "#FFD700"]],
        showscale=False, line_width=0,
    ),
    text=[f"{s:.1f}%" for s in ens_df["score"]],
    textposition="outside",
))
fig_ens.update_layout(
    **chart_style(height=300),
    xaxis_title="Number", yaxis_title="Score",
    yaxis=dict(gridcolor="#30363D"),
)
st.plotly_chart(fig_ens, use_container_width=True)

metric_row([
    ("🥇", ens_df.iloc[0]["number"],         "top pick"),
    ("📈", f"{ens_df.iloc[0]['score']:.1f}%", "confidence score"),
    ("🎯", f"{len(ens_df)}",                  "candidates ranked"),
    ("🔁", str(lookback),                     "lookback draws"),
])

st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)

# ── Individual models ─────────────────────────────────────────────────────────
section_label("Model-by-Model Breakdown")

tab_rf, tab_lr, tab_mk, tab_compare = st.tabs([
    "🌲 Random Forest", "📉 Logistic Regression", "🔗 Markov Chain", "⚖ Compare All"
])


def _model_panel(preds: list[dict], color: str) -> None:
    if not preds:
        st.warning("Not enough data for this model.")
        return
    pdf = pd.DataFrame(preds)
    lottery_balls(pdf["number"].tolist(), pdf["probability"].tolist())
    fig = go.Figure(go.Bar(
        x=pdf["number"], y=pdf["probability"],
        marker=dict(color=pdf["probability"], colorscale=color,
                    showscale=False, line_width=0),
        text=[f"{p:.1f}%" for p in pdf["probability"]],
        textposition="outside",
    ))
    fig.update_layout(**chart_style(height=260), yaxis=dict(gridcolor="#30363D"))
    st.plotly_chart(fig, use_container_width=True)


with tab_rf:
    st.caption("Random Forest — learns patterns from sequences of past results.")
    _model_panel(predict_next_rf(series, lookback=lookback, top_n=top_n), "Reds")

with tab_lr:
    st.caption("Logistic Regression — linear probability model on recent sequence.")
    _model_panel(predict_next_lr(series, lookback=lookback, top_n=top_n), "Blues")

with tab_mk:
    st.caption("Markov Chain — probability based on what followed each number historically.")
    _model_panel(predict_markov(series, top_n=top_n), "Greens")

with tab_compare:
    section_label("Side-by-side comparison")
    rf_df  = pd.DataFrame(predict_next_rf(series, lookback=lookback, top_n=top_n)).rename(columns={"probability": "RF %"})
    lr_df  = pd.DataFrame(predict_next_lr(series, lookback=lookback, top_n=top_n)).rename(columns={"probability": "LR %"})
    mk_df  = pd.DataFrame(predict_markov(series, top_n=top_n)).rename(columns={"probability": "MK %"})
    ens_r  = ens_df.rename(columns={"score": "Ensemble"})

    merged = (
        ens_r[["number", "Ensemble"]]
        .merge(rf_df[["number", "RF %"]],  on="number", how="outer")
        .merge(lr_df[["number", "LR %"]],  on="number", how="outer")
        .merge(mk_df[["number", "MK %"]],  on="number", how="outer")
        .fillna(0)
        .sort_values("Ensemble", ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(
        merged.style.background_gradient(
            subset=["Ensemble", "RF %", "LR %", "MK %"], cmap="Reds"
        ),
        use_container_width=True,
        hide_index=True,
    )

# ── Recent draws ──────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)
section_label("Recent Draws (last 15)")
recent = df.head(15)[["draw_date", num_col]].copy()
recent["draw_date"] = pd.to_datetime(recent["draw_date"]).dt.strftime("%d %b %Y")
recent.columns = ["Date", digit_choice]
st.dataframe(recent, use_container_width=True, hide_index=True)
