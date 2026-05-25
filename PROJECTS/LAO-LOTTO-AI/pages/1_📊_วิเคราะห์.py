"""หน้าวิเคราะห์ — ฮีตแมป, เลขร้อน/เย็น, ความถี่, ช่วงห่าง, เลขค้างนาน"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src import database as db
from src.analytics import (
    frequency, hot_cold, heatmap_matrix,
    gap_analysis, overdue, consecutive_pairs,
)
from src.ui_components import inject_css, lottery_balls, section_label, chart_style

st.set_page_config(page_title="วิเคราะห์ — หวยลาว AI", page_icon="📊", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">📊 วิเคราะห์</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">ความถี่, เลขร้อน/เย็น, ฮีตแมป, ช่วงห่าง</p>',
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#30363D;margin:.6rem 0 1rem;'>", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def _load():
    return db.load()


df = _load()

if df.empty:
    st.warning("ยังไม่มีข้อมูล — ไปที่ **⚙️ ตั้งค่า** แล้วดึงข้อมูลก่อน")
    st.stop()

# ── ตัวเลือกประเภทหลัก ────────────────────────────────────────────────────────
DIGIT_OPTS = {
    "2 ตัวล่าง":  ("last_2",   2),
    "2 ตัวบน":    ("top_2",    2),
    "3 ตัวล่าง":  ("last_3",   3),
    "3 ตัวบน":    ("top_3",    3),
    "4 ตัวท้าย":  ("last_4",   4),
}

col_sel, col_top = st.columns([2, 1])
with col_sel:
    dtype_label = st.selectbox("ประเภทเลข", list(DIGIT_OPTS.keys()), index=0)
with col_top:
    top_n = st.slider("แสดง Top N", min_value=5, max_value=20, value=10, step=5)

col_name, digits = DIGIT_OPTS[dtype_label]
if col_name not in df.columns:
    st.warning(f"ไม่พบคอลัมน์ {col_name}")
    st.stop()

series = df[col_name].dropna().astype(str)
if series.empty:
    st.warning("ไม่มีข้อมูลสำหรับประเภทนี้")
    st.stop()

tabs = st.tabs(["🔥 ร้อน/เย็น", "📊 ความถี่", "🗺 ฮีตแมป", "📏 ช่วงห่าง", "⏳ ค้างนาน", "🔗 คู่ติดกัน"])

# ── TAB 1: เลขร้อน/เย็น ──────────────────────────────────────────────────────
with tabs[0]:
    hot, cold = hot_cold(series, top_n)
    c1, c2 = st.columns(2)
    with c1:
        section_label(f"🔥 {top_n} เลขร้อน — {dtype_label}")
        scores_hot = [
            round(frequency(series).set_index("number").loc[n, "pct"], 1)
            if n in frequency(series)["number"].values else 0.0
            for n in hot
        ]
        lottery_balls(hot, scores_hot)

    with c2:
        section_label(f"🧊 {top_n} เลขเย็น — {dtype_label}")
        freq_df = frequency(series)
        scores_cold = [
            round(freq_df.set_index("number").loc[n, "pct"], 1)
            if n in freq_df["number"].values else 0.0
            for n in cold
        ]
        lottery_balls(cold, scores_cold)

# ── TAB 2: ความถี่ ────────────────────────────────────────────────────────────
with tabs[1]:
    freq_df = frequency(series)
    top_freq = freq_df.head(top_n)

    fig = go.Figure(go.Bar(
        x=top_freq["number"],
        y=top_freq["count"],
        text=top_freq["pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside",
        marker=dict(
            color=top_freq["count"],
            colorscale=[[0, "#30363D"], [1, "#E63946"]],
            showscale=False,
        ),
    ))
    fig.update_layout(
        title=f"ความถี่ {top_n} อันดับแรก — {dtype_label}",
        xaxis_title="เลข",
        yaxis_title="จำนวนครั้ง",
        **chart_style(),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("ตารางความถี่ทั้งหมด"):
        st.dataframe(freq_df, use_container_width=True, hide_index=True)

# ── TAB 3: ฮีตแมป ────────────────────────────────────────────────────────────
with tabs[2]:
    if digits == 2:
        matrix, labels = heatmap_matrix(series, digits=2)
        fig = go.Figure(go.Heatmap(
            z=matrix,
            text=labels,
            texttemplate="%{text}",
            textfont={"size": 9, "color": "white"},
            colorscale=[[0, "#0D1117"], [0.5, "#E63946"], [1, "#FFD700"]],
            showscale=True,
        ))
        fig.update_layout(
            title=f"ฮีตแมป {dtype_label} (00–99)",
            xaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)]),
            yaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)]),
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"ฮีตแมปรองรับเฉพาะ 2 หลัก — เลือก '2 ตัวล่าง' หรือ '2 ตัวบน' เพื่อดูฮีตแมป")
        freq_df = frequency(series)
        top20 = freq_df.head(20)
        fig = px.bar(
            top20, x="number", y="count", color="count",
            color_continuous_scale=["#30363D", "#E63946", "#FFD700"],
            labels={"number": "เลข", "count": "จำนวน"},
            title=f"ความถี่ Top 20 — {dtype_label}",
        )
        fig.update_layout(**chart_style())
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 4: ช่วงห่าง ──────────────────────────────────────────────────────────
with tabs[3]:
    gap_df = gap_analysis(series)
    if gap_df.empty:
        st.info("ข้อมูลไม่เพียงพอสำหรับการวิเคราะห์ช่วงห่าง")
    else:
        top_gap = gap_df.head(top_n)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="ช่วงห่างเฉลี่ย",
            x=top_gap["number"], y=top_gap["avg_gap"],
            marker_color="#4A90D9",
        ))
        fig.add_trace(go.Bar(
            name="ช่วงห่างสูงสุด",
            x=top_gap["number"], y=top_gap["max_gap"],
            marker_color="#E63946",
        ))
        fig.update_layout(
            barmode="group",
            title=f"ช่วงห่างระหว่างการออก — {dtype_label} (Top {top_n})",
            xaxis_title="เลข", yaxis_title="จำนวนงวด",
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("ตารางช่วงห่างทั้งหมด"):
            gap_df.columns = ["เลข", "ช่วงห่างเฉลี่ย", "สูงสุด", "ต่ำสุด", "ห่างล่าสุด(งวด)"]
            st.dataframe(gap_df, use_container_width=True, hide_index=True)

# ── TAB 5: เลขค้างนาน ────────────────────────────────────────────────────────
with tabs[4]:
    od_df = overdue(series, digits=digits)
    top_od = od_df.head(top_n)

    fig = go.Figure(go.Bar(
        x=top_od["number"],
        y=top_od["draws_since"],
        text=top_od["draws_since"],
        textposition="outside",
        marker_color=["#E63946" if r else "#4A90D9" for r in top_od["never_appeared"]],
    ))
    fig.update_layout(
        title=f"เลขที่ไม่ออกนานที่สุด — {dtype_label}",
        xaxis_title="เลข", yaxis_title="งวดที่ไม่ออก",
        **chart_style(),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("🔴 = ไม่เคยออกเลย  🔵 = ออกแล้วแต่นานมาก")

    with st.expander("ตารางเลขค้างนานทั้งหมด"):
        od_df.columns = ["เลข", "งวดที่ไม่ออก", "ไม่เคยออก"]
        st.dataframe(od_df, use_container_width=True, hide_index=True)

# ── TAB 6: คู่ติดกัน ─────────────────────────────────────────────────────────
with tabs[5]:
    pairs_df = consecutive_pairs(series)
    if pairs_df.empty:
        st.info("ข้อมูลไม่เพียงพอ")
    else:
        top_pairs = pairs_df.head(top_n)
        fig = go.Figure(go.Bar(
            x=top_pairs["pair"],
            y=top_pairs["count"],
            text=top_pairs["count"],
            textposition="outside",
            marker_color="#A78BFA",
        ))
        fig.update_layout(
            title=f"คู่เลขติดกันที่พบบ่อย — {dtype_label} (Top {top_n})",
            xaxis_title="คู่เลข", yaxis_title="จำนวนครั้ง",
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("ตารางคู่ทั้งหมด"):
            pairs_df.columns = ["คู่เลข", "จำนวนครั้ง"]
            st.dataframe(pairs_df, use_container_width=True, hide_index=True)
