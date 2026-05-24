"""Analysis — heatmap, hot/cold, frequency, gap, overdue, pairs."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from src import database as db
from src.analytics import (
    frequency, hot_cold, heatmap_matrix,
    gap_analysis, overdue, consecutive_pairs, summary,
)
from src.ui_components import inject_css, metric_row, lottery_balls, section_label, chart_style

st.set_page_config(page_title="Analysis · LAO LOTTO AI", page_icon="📊", layout="wide")
inject_css()

# ── Load ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _load():
    return db.load()

df = _load()

st.markdown('<h2 style="margin-bottom:.2rem;">📊 Number Analysis</h2>', unsafe_allow_html=True)

if df.empty:
    st.warning("No data — go to ⚙ Settings and fetch results first.")
    st.stop()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙ Controls")
    digit_choice = st.radio("Analyse", ["Last 2 digits", "Last 3 digits", "6-digit jackpot"])
    col_map = {"Last 2 digits": "last_2", "Last 3 digits": "last_3", "6-digit jackpot": "six_digit"}
    num_col = col_map[digit_choice]

    top_n = st.slider("Top N", 5, 30, 10)

    st.markdown("---")
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

series = df[num_col].dropna()
stats  = summary(series, df)

# ── Summary metrics ───────────────────────────────────────────────────────────
metric_row([
    ("📋", f"{stats['total_draws']:,}",  "draws"),
    ("🎯", str(stats["unique_numbers"]), "unique numbers"),
    ("🔥", stats["hottest"],             "hottest"),
    ("🧊", stats["coldest"],             "coldest"),
    ("📅", stats["latest_date"],         "latest draw"),
])

# ── Tabs ──────────────────────────────────────────────────────────────────────
t_heat, t_hotcold, t_freq, t_gap, t_overdue, t_pairs = st.tabs(
    ["🗺 Heatmap", "🔥 Hot / Cold", "📊 Frequency", "📏 Gap", "⏳ Overdue", "🔗 Pairs"]
)

# ── Heatmap ───────────────────────────────────────────────────────────────────
with t_heat:
    section_label("Frequency Heatmap — how often each 2-digit number appears")

    matrix, labels = heatmap_matrix(df["last_2"])
    fig = go.Figure(go.Heatmap(
        z=matrix, text=labels, texttemplate="%{text}",
        colorscale="RdYlGn", showscale=True,
        colorbar=dict(title="Count", tickfont=dict(color="#F0F6FC")),
        hoverongaps=False,
    ))
    fig.update_layout(
        **chart_style(height=480),
        xaxis=dict(
            title="Units digit", tickvals=list(range(10)),
            ticktext=[str(i) for i in range(10)], gridcolor="#30363D",
        ),
        yaxis=dict(
            title="Tens digit", tickvals=list(range(10)),
            ticktext=[str(i * 10) for i in range(10)],
            gridcolor="#30363D", autorange="reversed",
        ),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Green = high frequency · Red = low / never appeared")

# ── Hot / Cold ────────────────────────────────────────────────────────────────
with t_hotcold:
    hot, cold = hot_cold(series, top_n)
    freq_df   = frequency(series)

    section_label(f"🔥 Top {top_n} Hot Numbers")
    lottery_balls(hot)

    section_label(f"🧊 Top {top_n} Cold Numbers")
    lottery_balls(cold)

    c1, c2 = st.columns(2)
    with c1:
        st.caption("Hot — full stats")
        st.dataframe(
            freq_df[freq_df["number"].isin(hot)].reset_index(drop=True),
            use_container_width=True, hide_index=True,
        )
    with c2:
        st.caption("Cold — full stats")
        st.dataframe(
            freq_df[freq_df["number"].isin(cold)].reset_index(drop=True),
            use_container_width=True, hide_index=True,
        )

# ── Frequency ─────────────────────────────────────────────────────────────────
with t_freq:
    freq_df = frequency(series)
    section_label("Number Frequency")

    sort_opt = st.radio("Sort by", ["Frequency (desc)", "Number (asc)"], horizontal=True)
    plot_df = freq_df.sort_values("count" if "Freq" in sort_opt else "number",
                                   ascending="asc" in sort_opt.lower())

    fig_f = px.bar(
        plot_df.head(top_n * 3), x="number", y="count", color="count",
        color_continuous_scale="Reds", labels={"count": "Draws", "number": "Number"},
    )
    fig_f.update_layout(**chart_style(height=380), coloraxis_showscale=False)
    fig_f.update_traces(marker_line_width=0)
    st.plotly_chart(fig_f, use_container_width=True)

    with st.expander("Full table"):
        st.dataframe(freq_df, use_container_width=True, height=280, hide_index=True)

# ── Gap ───────────────────────────────────────────────────────────────────────
with t_gap:
    section_label("Gap Analysis — how many draws between each number's appearances")
    gap_df = gap_analysis(series)

    fig_g = px.scatter(
        gap_df, x="avg_gap", y="last_seen_ago", text="number",
        color="avg_gap", color_continuous_scale="Oranges",
        labels={"avg_gap": "Avg gap (draws)", "last_seen_ago": "Draws since last"},
        size_max=8,
    )
    fig_g.update_traces(textposition="top center", marker_size=7)
    fig_g.update_layout(**chart_style(height=430), coloraxis_showscale=False)
    st.plotly_chart(fig_g, use_container_width=True)
    st.caption("Numbers in the top-right corner are both infrequent AND haven't appeared recently.")

    with st.expander("Gap table"):
        st.dataframe(gap_df, use_container_width=True, height=280, hide_index=True)

# ── Overdue ───────────────────────────────────────────────────────────────────
with t_overdue:
    section_label("Overdue Numbers (2-digit pool 00–99)")
    od_df = overdue(df["last_2"])

    never = od_df[od_df["never_appeared"]]["number"].tolist()
    if never:
        st.warning(f"**{len(never)} numbers never appeared:** {', '.join(sorted(never))}")

    fig_o = px.bar(
        od_df.head(25), x="number", y="draws_since",
        color="draws_since", color_continuous_scale="Reds",
        labels={"draws_since": "Draws since last seen"},
        title="Top 25 most overdue",
    )
    fig_o.update_layout(**chart_style(height=380), coloraxis_showscale=False)
    st.plotly_chart(fig_o, use_container_width=True)

# ── Pairs ─────────────────────────────────────────────────────────────────────
with t_pairs:
    section_label("Consecutive Pairs — which number tends to follow another?")
    pair_df = consecutive_pairs(series)

    if pair_df.empty:
        st.info("Not enough data for pair analysis.")
    else:
        fig_p = px.bar(
            pair_df.head(20), x="pair", y="count",
            color="count", color_continuous_scale="Blues",
            labels={"count": "Times in a row", "pair": "A → B"},
            title="Top 20 most common consecutive pairs",
        )
        fig_p.update_layout(**chart_style(height=380), coloraxis_showscale=False)
        st.plotly_chart(fig_p, use_container_width=True)

        with st.expander("Full pair table"):
            st.dataframe(pair_df, use_container_width=True, height=280, hide_index=True)
