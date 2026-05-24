import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from src.data_loader import load_uploaded_file, generate_sample_data, LOTTERY_TYPES
from src.analyzer import frequency_table, hot_cold, gap_analysis, overdue_numbers

st.set_page_config(page_title="Analysis", page_icon="📊", layout="wide")
st.title("📊 Lottery Number Analysis")

# --- Sidebar: data source ---
with st.sidebar:
    st.header("Data Source")
    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k])
    use_sample = st.checkbox("Use sample data", value=True)
    uploaded = None
    if not use_sample:
        uploaded = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])

    st.markdown("---")
    st.header("Settings")
    target_col = st.text_input("Column to analyse", value="result_2d")
    top_n = st.slider("Top N numbers", 5, 30, 10)

# --- Load data ---
df = None
if use_sample:
    df = generate_sample_data(lottery_type)
    st.info("Showing sample data. Upload your own file for real analysis.")
elif uploaded:
    try:
        df = load_uploaded_file(uploaded)
        st.success(f"Loaded {len(df)} rows from {uploaded.name}")
    except Exception as e:
        st.error(str(e))

if df is None:
    st.warning("Upload a file or enable sample data to start.")
    st.stop()

# pick best default column
if target_col not in df.columns:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()
    available = str_cols + numeric_cols
    target_col = available[0] if available else df.columns[0]
    st.warning(f"Column '{target_col}' not found — using '{target_col}'.")

series = df[target_col].dropna()

# --- Frequency chart ---
st.subheader("Number Frequency")
freq_df = frequency_table(series)
fig = px.bar(freq_df.head(top_n * 2), x="number", y="count", color="count",
             color_continuous_scale="Blues", labels={"count": "Draws"})
fig.update_layout(height=350, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

# --- Hot / Cold ---
col1, col2 = st.columns(2)
hot, cold = hot_cold(series, top_n)
with col1:
    st.subheader("🔥 Hot Numbers")
    st.dataframe(freq_df[freq_df["number"].isin(hot)].reset_index(drop=True), use_container_width=True)
with col2:
    st.subheader("🧊 Cold Numbers")
    st.dataframe(freq_df[freq_df["number"].isin(cold)].reset_index(drop=True), use_container_width=True)

# --- Gap analysis ---
st.subheader("Gap Analysis")
gap_df = gap_analysis(series)
fig2 = px.scatter(gap_df, x="avg_gap", y="last_seen_ago", text="number",
                  labels={"avg_gap": "Avg gap (draws)", "last_seen_ago": "Draws since last"},
                  title="Numbers by average gap vs recency")
fig2.update_traces(textposition="top center")
fig2.update_layout(height=400)
st.plotly_chart(fig2, use_container_width=True)

# --- Overdue ---
st.subheader("Overdue Numbers (2-digit pool 00–99)")
od_df = overdue_numbers(series)
fig3 = px.bar(od_df.head(20), x="number", y="draws_since_last",
              color="draws_since_last", color_continuous_scale="Reds",
              title="Top 20 most overdue numbers")
fig3.update_layout(height=350)
st.plotly_chart(fig3, use_container_width=True)

# --- Raw data ---
with st.expander("Raw data"):
    st.dataframe(df, use_container_width=True)
