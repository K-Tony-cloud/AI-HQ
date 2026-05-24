import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from src.data_loader import load_uploaded_file, generate_sample_data, LOTTERY_TYPES, RAW_DIR
from src.ui_components import inject_css, metric_row, section_label

st.set_page_config(page_title="History", page_icon="📜", layout="wide")
inject_css()

st.markdown('<h2 style="margin-bottom:.2rem;">📜 Draw History</h2>', unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Data Source")
    src = st.radio("Source", ["Sample data", "Saved file", "Upload file"])

    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k])
    uploaded = None

    if src == "Upload file":
        uploaded = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])
    elif src == "Saved file":
        raw_files = list(RAW_DIR.glob("*.csv")) + list(RAW_DIR.glob("*.xlsx"))
        if raw_files:
            sel = st.selectbox("Select saved file", [f.name for f in raw_files])
        else:
            st.warning("No saved files. Use Data Manager to upload one.")
            sel = None

    st.markdown("---")
    st.header("Filters")
    target_col = st.text_input("Result column", value="result_2d")

# ── Load ──────────────────────────────────────────────────────────────────────
df = None
if src == "Sample data":
    df = generate_sample_data(lottery_type, n=365)
    st.info("Showing 1 year of sample data.")
elif src == "Upload file" and uploaded:
    try:
        df = load_uploaded_file(uploaded)
        st.success(f"Loaded **{len(df):,}** rows from {uploaded.name}")
    except Exception as e:
        st.error(str(e))
elif src == "Saved file" and sel:
    try:
        path = RAW_DIR / sel
        df = pd.read_csv(path) if sel.endswith(".csv") else pd.read_excel(path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        st.success(f"Loaded **{len(df):,}** rows from {sel}")
    except Exception as e:
        st.error(str(e))

if df is None:
    st.warning("Select a data source to begin.")
    st.stop()

if target_col not in df.columns:
    candidates = [c for c in df.columns if df[c].dtype == object] or df.columns.tolist()
    target_col = candidates[0]
    st.warning(f"Column not found — using **{target_col}**.")

# ── Date filter ───────────────────────────────────────────────────────────────
if "date" in df.columns and df["date"].notna().any():
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    with st.sidebar:
        date_range = st.date_input("Date range", value=(min_date, max_date),
                                   min_value=min_date, max_value=max_date)

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        df = df[(df["date"].dt.date >= date_range[0]) & (df["date"].dt.date <= date_range[1])]

# ── Number search ─────────────────────────────────────────────────────────────
section_label("Search by Number")
search_num = st.text_input("Enter a number to find all draws it appeared in (e.g. 43)", max_chars=6)

if search_num.strip():
    mask   = df[target_col].astype(str).str.contains(search_num.strip(), na=False)
    result = df[mask]
    st.markdown(f"**{len(result)}** draws matched `{search_num}`")
    if not result.empty:
        cols = ["date", target_col] if "date" in df.columns else [target_col]
        st.dataframe(result[cols].reset_index(drop=True), use_container_width=True)
    st.markdown("---")

# ── Summary metrics ───────────────────────────────────────────────────────────
from src.analyzer import frequency_table
freq = frequency_table(df[target_col].dropna())
metric_row([
    ("📋", f"{len(df):,}",   "draws in range"),
    ("🎯", f"{freq['number'].nunique()}", "unique numbers"),
    ("🔥", freq.iloc[0]["number"] if not freq.empty else "—", "most frequent"),
    ("📅", df["date"].max().strftime("%d %b %Y") if "date" in df.columns else "—", "latest draw"),
])

# ── Timeline ─────────────────────────────────────────────────────────────────
if "date" in df.columns:
    section_label("Results Timeline")
    timeline_df = df[["date", target_col]].dropna().copy()
    timeline_df[target_col] = timeline_df[target_col].astype(str)

    fig = px.scatter(
        timeline_df, x="date", y=target_col,
        color=target_col,
        labels={"date": "Draw date", target_col: "Result"},
        height=350,
    )
    fig.update_traces(marker_size=5)
    fig.update_layout(plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                      font_color="#F0F6FC", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# ── Full history table ────────────────────────────────────────────────────────
section_label("Full Draw History")

page_size = st.select_slider("Rows per page", options=[25, 50, 100, 200], value=50)
total_pages = max(1, (len(df) - 1) // page_size + 1)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)

start = (page - 1) * page_size
end   = start + page_size
page_df = df.iloc[start:end].reset_index(drop=True)

display_cols = (["date"] if "date" in page_df.columns else []) + \
               [c for c in page_df.columns if c != "date"]
st.dataframe(page_df[display_cols], use_container_width=True)
st.caption(f"Showing rows {start + 1}–{min(end, len(df))} of {len(df):,} total")

# ── Export ───────────────────────────────────────────────────────────────────
section_label("Export")
csv = df.to_csv(index=False).encode()
st.download_button("Download filtered data as CSV", csv, file_name="lao_lotto_history.csv")
