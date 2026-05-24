"""Trends — rolling frequency, day-of-week, monthly, digit split."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from src import database as db
from src.analytics import (
    rolling_frequency, draws_per_dow, draws_per_month,
    monthly_num_freq, digit_split, frequency,
)
from src.ui_components import inject_css, section_label, chart_style, metric_row

st.set_page_config(page_title="Trends · LAO LOTTO AI", page_icon="📈", layout="wide")
inject_css()

@st.cache_data(ttl=300)
def _load():
    return db.load()

df = _load()

st.markdown('<h2 style="margin-bottom:.2rem;">📈 Trends</h2>', unsafe_allow_html=True)

if df.empty:
    st.warning("No data — go to ⚙ Settings and fetch results first.")
    st.stop()

with st.sidebar:
    st.header("⚙ Controls")
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

series = df["last_2"].dropna()

tab_roll, tab_dow, tab_monthly, tab_digit, tab_timeline = st.tabs([
    "📉 Rolling Frequency", "📅 Day of Week", "🗓 Monthly", "🔢 Digit Split", "⏱ Timeline"
])

# ── Rolling frequency ─────────────────────────────────────────────────────────
with tab_roll:
    section_label("Rolling Frequency — how hot numbers evolve over time")
    window = st.slider("Rolling window (draws)", 5, 40, 15, key="roll_w")

    freq_df = frequency(series)
    top5    = freq_df.head(5)["number"].tolist()

    roll_df = rolling_frequency(series, window=window)
    melt    = roll_df.melt(
        id_vars="period_end", value_vars=top5,
        var_name="number", value_name="count",
    )

    fig = px.line(
        melt, x="period_end", y="count", color="number",
        labels={"period_end": "Draw index", "count": f"Hits in last {window} draws"},
        markers=True,
    )
    fig.update_layout(**chart_style(height=420), legend_bgcolor="#0D1117",
                      xaxis=dict(gridcolor="#30363D"), yaxis=dict(gridcolor="#30363D"))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Tracking top-5 hottest numbers over a rolling {window}-draw window.")

# ── Day of week ───────────────────────────────────────────────────────────────
with tab_dow:
    section_label("Draws by Day of Week")
    dow_df = draws_per_dow(df, date_col="draw_date")

    if dow_df.empty:
        st.info("Date column not available.")
    else:
        fig_d = px.bar(
            dow_df, x="day", y="count", color="count",
            color_continuous_scale="Reds",
            labels={"count": "Number of draws", "day": ""},
        )
        fig_d.update_layout(**chart_style(height=360), coloraxis_showscale=False,
                             xaxis=dict(gridcolor="#30363D"),
                             yaxis=dict(gridcolor="#30363D"))
        st.plotly_chart(fig_d, use_container_width=True)

        # Hottest numbers by DOW
        section_label("Hottest 2-Digit Number by Day")
        from src.analytics import dow_frequency
        dof = dow_frequency(df, date_col="draw_date", num_col="last_2")
        if not dof.empty:
            top_per_day = (
                dof.sort_values("count", ascending=False)
                   .drop_duplicates(subset="dow")
                   .sort_values("dow")
                   .rename(columns={"dow": "Day", "last_2": "Top Number", "count": "Count"})
            )
            st.dataframe(top_per_day, use_container_width=True, hide_index=True)

# ── Monthly ───────────────────────────────────────────────────────────────────
with tab_monthly:
    section_label("Draws Per Month")
    monthly_df = draws_per_month(df, date_col="draw_date")

    if monthly_df.empty:
        st.info("Date column not available.")
    else:
        fig_m = px.bar(
            monthly_df, x="month", y="count", color="count",
            color_continuous_scale="Blues",
            labels={"count": "Draws", "month": "Month"},
        )
        fig_m.update_layout(**chart_style(height=350), coloraxis_showscale=False,
                             xaxis=dict(tickangle=-45, gridcolor="#30363D"),
                             yaxis=dict(gridcolor="#30363D"))
        st.plotly_chart(fig_m, use_container_width=True)

        section_label("Number Frequency by Month (heatmap)")
        mn_df = monthly_num_freq(df, num_col="last_2", date_col="draw_date")
        if not mn_df.empty:
            pivot = mn_df.pivot(index="last_2", columns="month", values="count").fillna(0)
            fig_h = px.imshow(
                pivot,
                color_continuous_scale="Reds",
                labels=dict(x="Month", y="Number", color="Count"),
                aspect="auto",
            )
            fig_h.update_layout(**chart_style(height=500))
            st.plotly_chart(fig_h, use_container_width=True)

# ── Digit split ───────────────────────────────────────────────────────────────
with tab_digit:
    section_label("Digit Distribution — units vs tens")
    units_df, tens_df = digit_split(series)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Units digit (0–9)**")
        fig_u = px.bar(
            units_df, x="number", y="count", color="count",
            color_continuous_scale="Reds",
            labels={"number": "Units digit", "count": "Hits"},
        )
        fig_u.update_layout(**chart_style(height=320), coloraxis_showscale=False,
                             yaxis=dict(gridcolor="#30363D"))
        st.plotly_chart(fig_u, use_container_width=True)

    with c2:
        st.markdown("**Tens digit (0–9)**")
        fig_t = px.bar(
            tens_df, x="number", y="count", color="count",
            color_continuous_scale="Blues",
            labels={"number": "Tens digit", "count": "Hits"},
        )
        fig_t.update_layout(**chart_style(height=320), coloraxis_showscale=False,
                             yaxis=dict(gridcolor="#30363D"))
        st.plotly_chart(fig_t, use_container_width=True)

    st.caption(
        "For last-2-digit results: the units digit is the right digit, "
        "tens is the left. E.g. '63' → tens=6, units=3."
    )

# ── Timeline ──────────────────────────────────────────────────────────────────
with tab_timeline:
    section_label("Draw Results Over Time")
    timeline = df[["draw_date", "last_2", "six_digit"]].copy()
    timeline["draw_date"] = pd.to_datetime(timeline["draw_date"])
    timeline["last_2_int"] = timeline["last_2"].astype(int)

    fig_tl = px.scatter(
        timeline, x="draw_date", y="last_2_int",
        hover_data={"six_digit": True, "last_2": True, "draw_date": True, "last_2_int": False},
        labels={"draw_date": "Date", "last_2_int": "Last 2 digits (numeric)"},
        color="last_2_int", color_continuous_scale="Viridis",
    )
    fig_tl.update_traces(marker_size=6)
    fig_tl.update_layout(**chart_style(height=420), showlegend=False,
                          coloraxis_showscale=False,
                          xaxis=dict(gridcolor="#30363D"),
                          yaxis=dict(gridcolor="#30363D"))
    st.plotly_chart(fig_tl, use_container_width=True)

    with st.expander("Browse full history"):
        display = df[["draw_date", "six_digit", "last_3", "last_2"]].copy()
        display["draw_date"] = pd.to_datetime(display["draw_date"]).dt.strftime("%d %b %Y")
        display.columns = ["Date", "6-Digit", "3-Digit", "2-Digit"]
        st.dataframe(display, use_container_width=True, hide_index=True)
