import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from src.data_loader import generate_sample_data
from src.analyzer import frequency_table, hot_cold
from src.ui_components import inject_css, metric_row, lottery_balls, nav_cards, section_label

st.set_page_config(
    page_title="LAO LOTTO AI",
    page_icon="🎰",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ── Hero ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <h1 style="font-size:2.4rem; font-weight:800; margin-bottom:.2rem;">
      🎰 LAO LOTTO AI
    </h1>
    <p style="color:#8B949E; font-size:1rem; margin-top:0;">
      Statistical analysis &amp; pattern-based prediction for Lao lottery results
    </p>
    """,
    unsafe_allow_html=True,
)

# ── Live stats (from sample data) ───────────────────────────────────────────
df  = generate_sample_data("vietlao", n=200)
ser = df["result_2d"].dropna()
freq = frequency_table(ser)
hot, cold = hot_cold(ser, top_n=1)
last_date = df["date"].max().strftime("%d %b %Y") if "date" in df.columns else "—"

metric_row([
    ("📅", last_date,          "last draw date"),
    ("📊", str(len(df)),       "total draws"),
    ("🔥", hot[0] if hot else "—", "hottest number"),
    ("🧊", cold[0] if cold else "—", "coldest number"),
    ("🎯", f"{len(freq)}",     "unique numbers seen"),
])

st.markdown("<hr style='border-color:#30363D; margin:1.2rem 0;'>", unsafe_allow_html=True)

# ── Top predicted balls preview ──────────────────────────────────────────────
section_label("Today's Top Picks (sample data — upload yours for real predictions)")

from src.predictor import ensemble_predict
with st.spinner("Computing preview predictions…"):
    ens = ensemble_predict(ser, top_n=7)

lottery_balls(ens["number"].tolist(), ens["score"].tolist())

st.caption("Numbers ranked by ensemble model score. Lottery draws are random — for entertainment only.")

st.markdown("<hr style='border-color:#30363D; margin:1.2rem 0;'>", unsafe_allow_html=True)

# ── Navigation cards ─────────────────────────────────────────────────────────
section_label("Navigate")
nav_cards([
    ("📊", "Analysis",     "Frequency charts, heatmap, hot/cold, gap &amp; overdue analysis"),
    ("🤖", "Prediction",   "Ensemble model (RF + LR + Markov) with lottery-ball display"),
    ("📜", "History",      "Browse and search your full draw history by date or number"),
    ("📥", "Data Manager", "Upload CSV/Excel results, download templates, manage datasets"),
])

st.sidebar.markdown("### LAO LOTTO AI")
st.sidebar.markdown("Use the pages above to explore analysis and predictions.")
st.sidebar.markdown("---")
st.sidebar.info("Upload your own data in **📥 Data Manager** for real results.")
