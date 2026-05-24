"""Home dashboard — latest draw, key stats, top picks, navigation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd

from src import database as db
from src.analytics import frequency, hot_cold, summary
from src.predictor import ensemble_predict
from src.ui_components import (
    inject_css, metric_row, lottery_balls,
    latest_draw_card, stale_banner, section_label, nav_cards,
)

st.set_page_config(
    page_title="LAO LOTTO AI",
    page_icon="🎰",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _load():
    return db.load()

df = _load()
empty = df.empty

# ── Stale check ───────────────────────────────────────────────────────────────
if db.is_stale(hours=20):
    stale_banner(db.meta().get("last_scraped", "unknown"))

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="font-size:2.2rem;font-weight:900;margin-bottom:.1rem;">'
    '🎰 LAO LOTTO AI</h1>'
    '<p style="color:#8B949E;font-size:.95rem;margin-top:0;">'
    'Statistical analysis &amp; AI-powered predictions for Lao National Lottery</p>',
    unsafe_allow_html=True,
)

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0 1.2rem;'>", unsafe_allow_html=True)

if empty:
    st.warning(
        "No data yet. Go to **⚙ Settings** and click **Fetch Latest Results** "
        "to download draws from lotto.thaiorc.com."
    )
    st.stop()

# ── Latest draw ───────────────────────────────────────────────────────────────
latest = df.iloc[0]
date_str = pd.to_datetime(latest["draw_date"]).strftime("%A, %d %B %Y")
latest_draw_card(latest["six_digit"], date_str, latest["last_3"], latest["last_2"])

# ── Key metrics ───────────────────────────────────────────────────────────────
series = df["last_2"]
freq_df = frequency(series)
hot, cold = hot_cold(series, 1)
m = db.meta()

metric_row([
    ("📅", pd.to_datetime(m["latest"]).strftime("%d %b %Y"),   "latest draw"),
    ("📋", f"{m['total']:,}",                                   "total draws"),
    ("📅", pd.to_datetime(m["earliest"]).strftime("%d %b %Y"), "since"),
    ("🔥", hot[0]  if hot  else "—",                           "hottest 2-digit"),
    ("🧊", cold[0] if cold else "—",                           "coldest 2-digit"),
])

st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)

# ── Top predictions ───────────────────────────────────────────────────────────
col_pred, col_recent = st.columns([3, 2], gap="large")

with col_pred:
    section_label("Today's Top Picks")
    with st.spinner("Computing predictions..."):
        ens = ensemble_predict(series, top_n=7)
    lottery_balls(ens["number"].tolist(), ens["score"].tolist())
    st.caption("Ensemble model (Random Forest + Logistic Regression + Markov). For entertainment only.")

with col_recent:
    section_label("Last 10 Draws")
    recent = df.head(10)[["draw_date", "six_digit", "last_3", "last_2"]].copy()
    recent["draw_date"] = pd.to_datetime(recent["draw_date"]).dt.strftime("%d %b")
    recent.columns = ["Date", "6-Digit", "3-Digit", "2-Digit"]
    st.dataframe(recent, use_container_width=True, hide_index=True)

st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)

# ── Navigation ────────────────────────────────────────────────────────────────
section_label("Explore")
nav_cards([
    ("📊", "Analysis",    "Heatmap, hot/cold balls, frequency, gap & overdue numbers"),
    ("🎯", "Predictions", "Ensemble AI picks with model-by-model breakdown"),
    ("📈", "Trends",      "Rolling frequency, day-of-week patterns, monthly heatmap"),
    ("⚙️", "Settings",   "Fetch live data, manage database, export CSV"),
])

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎰 LAO LOTTO AI")
    st.markdown(f"**{m['total']} draws** · {pd.to_datetime(m['earliest']).strftime('%b %Y')} – {pd.to_datetime(m['latest']).strftime('%b %Y')}")
    st.markdown("---")
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Auto-refreshes every 5 minutes. Manual refresh fetches latest.")
