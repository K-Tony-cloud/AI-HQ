import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import pandas as pd

from src.data_loader import load_uploaded_file, generate_sample_data, LOTTERY_TYPES
from src.analyzer import (
    frequency_table, hot_cold, gap_analysis,
    overdue_numbers, consecutive_pairs, rolling_frequency,
)
from src.ui_components import inject_css, metric_row, lottery_balls, section_label

st.set_page_config(page_title="Analysis", page_icon="📊", layout="wide")
inject_css()

st.markdown('<h2 style="margin-bottom:.2rem;">📊 Lottery Number Analysis</h2>', unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Data Source")
    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k])
    use_sample   = st.checkbox("Use sample data", value=True)
    uploaded     = None
    if not use_sample:
        uploaded = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])
    st.markdown("---")
    st.header("Settings")
    target_col = st.text_input("Column to analyse", value="result_2d")
    top_n      = st.slider("Top N numbers", 5, 30, 10)

# ── Load ─────────────────────────────────────────────────────────────────────
df = None
if use_sample:
    df = generate_sample_data(lottery_type, n=300)
    st.info("Showing sample data — upload your own in Data Manager for real analysis.")
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
    st.warning(f"Column not found — falling back to **{target_col}**.")

series = df[target_col].dropna()
freq_df = frequency_table(series)
hot, cold = hot_cold(series, top_n)

# ── Summary metrics ───────────────────────────────────────────────────────────
metric_row([
    ("📋", f"{len(series):,}",          "total draws"),
    ("🎯", f"{freq_df['number'].nunique()}", "unique numbers"),
    ("🔥", hot[0] if hot else "—",      "hottest"),
    ("🧊", cold[0] if cold else "—",    "coldest"),
    ("📅", df["date"].max().strftime("%d %b %Y") if "date" in df.columns else "—", "latest draw"),
])

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_freq, tab_heat, tab_hotcold, tab_gap, tab_overdue, tab_pairs, tab_trend = st.tabs([
    "Frequency", "Heatmap", "Hot / Cold", "Gap Analysis", "Overdue", "Pairs", "Trend",
])

# ── Frequency ────────────────────────────────────────────────────────────────
with tab_freq:
    section_label("Number Frequency")
    sort_by = st.radio("Sort by", ["frequency (desc)", "number (asc)"], horizontal=True)
    plot_df = freq_df.copy()
    if "number (asc)" in sort_by:
        plot_df = plot_df.sort_values("number")
    else:
        plot_df = plot_df.sort_values("count", ascending=False)

    fig = px.bar(
        plot_df.head(top_n * 3), x="number", y="count", color="count",
        color_continuous_scale="Reds",
        labels={"count": "Draws", "number": "Number"},
    )
    fig.update_layout(height=380, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                      font_color="#F0F6FC", coloraxis_showscale=False)
    fig.update_traces(marker_line_width=0)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Full frequency table"):
        st.dataframe(freq_df, use_container_width=True, height=300)

# ── Heatmap ───────────────────────────────────────────────────────────────────
with tab_heat:
    section_label("Frequency Heatmap (00 – 99)")
    freq_map = {r["number"]: r["count"] for _, r in freq_df.iterrows()}
    matrix   = np.zeros((10, 10))
    text_mat = [[""] * 10 for _ in range(10)]
    for r in range(10):
        for c in range(10):
            num = f"{r * 10 + c:02d}"
            val = freq_map.get(num, 0)
            matrix[r][c]   = val
            text_mat[r][c] = f"{num}<br>{val}"

    fig_h = go.Figure(go.Heatmap(
        z=matrix, text=text_mat, texttemplate="%{text}",
        colorscale="RdYlGn", showscale=True,
        hoverongaps=False,
    ))
    fig_h.update_layout(
        height=480, plot_bgcolor="#0D1117", paper_bgcolor="#0D1117",
        font_color="#F0F6FC",
        xaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)],
                   title="Units digit", gridcolor="#30363D"),
        yaxis=dict(tickvals=list(range(10)), ticktext=[str(i * 10) for i in range(10)],
                   title="Tens digit", gridcolor="#30363D", autorange="reversed"),
    )
    st.plotly_chart(fig_h, use_container_width=True)
    st.caption("Each cell = a 2-digit number 00–99. Green = appears most, Red = least / never.")

# ── Hot / Cold ────────────────────────────────────────────────────────────────
with tab_hotcold:
    section_label(f"Top {top_n} Hot Numbers")
    lottery_balls(hot)

    section_label(f"Top {top_n} Cold Numbers")
    lottery_balls(cold)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Hot — full stats**")
        st.dataframe(freq_df[freq_df["number"].isin(hot)].reset_index(drop=True), use_container_width=True)
    with col2:
        st.markdown("**Cold — full stats**")
        st.dataframe(freq_df[freq_df["number"].isin(cold)].reset_index(drop=True), use_container_width=True)

# ── Gap Analysis ──────────────────────────────────────────────────────────────
with tab_gap:
    section_label("Gap Analysis — how often does each number repeat?")
    gap_df = gap_analysis(series)

    fig_g = px.scatter(
        gap_df, x="avg_gap", y="last_seen_ago", text="number",
        color="avg_gap", color_continuous_scale="Oranges",
        labels={"avg_gap": "Avg gap (draws)", "last_seen_ago": "Draws since last seen"},
        size_max=10,
    )
    fig_g.update_traces(textposition="top center", marker_size=8)
    fig_g.update_layout(height=430, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                        font_color="#F0F6FC", coloraxis_showscale=False)
    st.plotly_chart(fig_g, use_container_width=True)

    with st.expander("Gap table"):
        st.dataframe(gap_df, use_container_width=True, height=300)

# ── Overdue ───────────────────────────────────────────────────────────────────
with tab_overdue:
    section_label("Overdue Numbers (00–99 pool)")
    od_df  = overdue_numbers(series)
    never  = od_df[od_df["never_appeared"]]["number"].tolist()
    if never:
        st.warning(f"**{len(never)} numbers never appeared:** {', '.join(sorted(never))}")

    fig_o = px.bar(
        od_df.head(25), x="number", y="draws_since_last",
        color="draws_since_last", color_continuous_scale="Reds",
        labels={"draws_since_last": "Draws since last seen"},
        title="Top 25 most overdue",
    )
    fig_o.update_layout(height=380, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                        font_color="#F0F6FC", coloraxis_showscale=False)
    st.plotly_chart(fig_o, use_container_width=True)

# ── Pairs ─────────────────────────────────────────────────────────────────────
with tab_pairs:
    section_label("Consecutive Draw Pairs — which number tends to follow another?")
    pair_df = consecutive_pairs(series)

    fig_p = px.bar(
        pair_df.head(20), x="pair", y="count",
        color="count", color_continuous_scale="Blues",
        labels={"count": "Times in a row"},
        title="Top 20 most common consecutive pairs",
    )
    fig_p.update_layout(height=380, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                        font_color="#F0F6FC", coloraxis_showscale=False)
    st.plotly_chart(fig_p, use_container_width=True)

    with st.expander("Full pair table"):
        st.dataframe(pair_df, use_container_width=True, height=280)

# ── Trend ─────────────────────────────────────────────────────────────────────
with tab_trend:
    section_label("Rolling Frequency Trend")
    window = st.slider("Rolling window (draws)", 10, 50, 20)
    roll_df = rolling_frequency(series, window=window)

    nums_to_show = hot[:5]
    melt = roll_df.melt(id_vars="period_end", value_vars=nums_to_show,
                        var_name="number", value_name="count")
    fig_t = px.line(
        melt, x="period_end", y="count", color="number",
        labels={"period_end": "Draw index", "count": f"Appearances in last {window} draws"},
        title=f"Rolling {window}-draw frequency for top {len(nums_to_show)} hot numbers",
    )
    fig_t.update_layout(height=400, plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
                        font_color="#F0F6FC", legend_bgcolor="#0D1117")
    st.plotly_chart(fig_t, use_container_width=True)
