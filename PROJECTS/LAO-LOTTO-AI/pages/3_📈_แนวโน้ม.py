"""หน้าแนวโน้ม — ความถี่สะสม, รายวัน, รายเดือน, แยกหลัก"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src import database as db
from src.analytics import (
    rolling_frequency, draws_per_dow, draws_per_month,
    monthly_num_freq, digit_split, frequency,
)
from src.ui_components import inject_css, section_label, chart_style

st.set_page_config(page_title="แนวโน้ม — หวยลาว AI", page_icon="📈", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">📈 แนวโน้ม</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">ความถี่สะสม, แยกวัน/เดือน, แยกหลัก</p>',
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

DIGIT_OPTS = {
    "2 ตัวล่าง": ("last_2",  2),
    "2 ตัวบน":   ("top_2",   2),
    "3 ตัวล่าง": ("last_3",  3),
    "3 ตัวบน":   ("top_3",   3),
    "4 ตัวท้าย": ("last_4",  4),
}

c1, c2 = st.columns([2, 1])
with c1:
    dtype_label = st.selectbox("ประเภทเลข", list(DIGIT_OPTS.keys()))
with c2:
    window = st.slider("Rolling Window (งวด)", 10, 50, 20, 5)

col_name, digits = DIGIT_OPTS[dtype_label]
if col_name not in df.columns:
    st.warning(f"ไม่พบคอลัมน์ {col_name}")
    st.stop()

series = df[col_name].dropna().astype(str)

tabs = st.tabs(["📉 Rolling Frequency", "📅 แยกวัน", "🗓 แยกเดือน", "🔢 แยกหลัก", "⏱ Timeline"])

# ── TAB 1: Rolling Frequency ─────────────────────────────────────────────────
with tabs[0]:
    if len(series) < window + 5:
        st.info("ข้อมูลไม่เพียงพอสำหรับ rolling frequency")
    else:
        roll_df = rolling_frequency(series, window=window)
        top5 = frequency(series).head(5)["number"].tolist()

        fig = go.Figure()
        colors = ["#E63946", "#FFD700", "#4A90D9", "#2ECC71", "#A78BFA"]
        for i, num in enumerate(top5):
            if num in roll_df.columns:
                fig.add_trace(go.Scatter(
                    x=roll_df["period_end"],
                    y=roll_df[num],
                    name=f"เลข {num}",
                    mode="lines",
                    line=dict(color=colors[i % len(colors)], width=2),
                ))
        fig.update_layout(
            title=f"Rolling Frequency (window={window}) — {dtype_label} Top 5",
            xaxis_title="ลำดับงวด (ใหม่→เก่า)",
            yaxis_title=f"จำนวนครั้งใน {window} งวด",
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("แสดงเฉพาะ 5 เลขที่ออกบ่อยที่สุดโดยรวม")

# ── TAB 2: แยกวัน ────────────────────────────────────────────────────────────
with tabs[1]:
    dow_df = draws_per_dow(df)
    if dow_df.empty:
        st.info("ไม่มีข้อมูลวันที่")
    else:
        DOW_TH = {
            "Monday": "จันทร์", "Tuesday": "อังคาร", "Wednesday": "พุธ",
            "Thursday": "พฤหัส", "Friday": "ศุกร์", "Saturday": "เสาร์", "Sunday": "อาทิตย์",
        }
        dow_df["day_th"] = dow_df["day"].map(DOW_TH).fillna(dow_df["day"])

        fig = go.Figure(go.Bar(
            x=dow_df["day_th"],
            y=dow_df["count"],
            text=dow_df["count"],
            textposition="outside",
            marker_color="#4A90D9",
        ))
        fig.update_layout(
            title="จำนวนงวดแยกตามวัน",
            xaxis_title="วัน", yaxis_title="จำนวนงวด",
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 3: แยกเดือน ──────────────────────────────────────────────────────────
with tabs[2]:
    month_df = draws_per_month(df)
    if month_df.empty:
        st.info("ไม่มีข้อมูลเดือน")
    else:
        fig = go.Figure(go.Bar(
            x=month_df["month"],
            y=month_df["count"],
            marker=dict(
                color=month_df["count"],
                colorscale=[[0, "#161B22"], [1, "#E63946"]],
                showscale=False,
            ),
        ))
        fig.update_layout(
            title="จำนวนงวดต่อเดือน",
            xaxis_title="เดือน", yaxis_title="จำนวนงวด",
            xaxis_tickangle=-45,
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)

    # monthly number frequency heatmap
    if digits == 2:
        section_label(f"ความถี่รายเดือน — {dtype_label}")
        mfreq = monthly_num_freq(df, num_col=col_name)
        if not mfreq.empty:
            pivot = mfreq.pivot(index="month", columns=col_name, values="count").fillna(0)
            top10_nums = frequency(series).head(10)["number"].tolist()
            pivot_top = pivot[[c for c in top10_nums if c in pivot.columns]]
            MONTH_TH = {1:"ม.ค.",2:"ก.พ.",3:"มี.ค.",4:"เม.ย.",5:"พ.ค.",6:"มิ.ย.",
                        7:"ก.ค.",8:"ส.ค.",9:"ก.ย.",10:"ต.ค.",11:"พ.ย.",12:"ธ.ค."}
            pivot_top.index = [MONTH_TH.get(int(m), m) for m in pivot_top.index]
            fig2 = px.imshow(
                pivot_top,
                color_continuous_scale=["#0D1117", "#E63946", "#FFD700"],
                labels={"x": "เลข", "y": "เดือน", "color": "จำนวน"},
                title=f"ความถี่รายเดือน — {dtype_label} Top 10",
            )
            fig2.update_layout(**chart_style())
            st.plotly_chart(fig2, use_container_width=True)

# ── TAB 4: แยกหลัก ──────────────────────────────────────────────────────────
with tabs[3]:
    if digits == 2:
        units_df, tens_df = digit_split(series)
        c1, c2 = st.columns(2)
        with c1:
            section_label("หลักหน่วย (0–9)")
            fig_u = go.Figure(go.Bar(
                x=units_df["number"], y=units_df["count"],
                text=units_df["pct"].apply(lambda x: f"{x:.1f}%"),
                textposition="outside",
                marker_color="#2ECC71",
            ))
            fig_u.update_layout(xaxis_title="หลักหน่วย", yaxis_title="จำนวน", **chart_style(title="หลักหน่วย"))
            st.plotly_chart(fig_u, use_container_width=True)

        with c2:
            section_label("หลักสิบ (0–9)")
            fig_t = go.Figure(go.Bar(
                x=tens_df["number"], y=tens_df["count"],
                text=tens_df["pct"].apply(lambda x: f"{x:.1f}%"),
                textposition="outside",
                marker_color="#A78BFA",
            ))
            fig_t.update_layout(xaxis_title="หลักสิบ", yaxis_title="จำนวน", **chart_style(title="หลักสิบ"))
            st.plotly_chart(fig_t, use_container_width=True)
    else:
        st.info("การแยกหลักรองรับเฉพาะเลข 2 หลัก — เลือก '2 ตัวล่าง' หรือ '2 ตัวบน'")

# ── TAB 5: Timeline ──────────────────────────────────────────────────────────
with tabs[4]:
    if "draw_date" not in df.columns:
        st.info("ไม่มีข้อมูลวันที่")
    else:
        recent_n = st.slider("แสดงย้อนหลัง (งวด)", 20, min(200, len(df)), 50, 10)
        timeline_df = df.head(recent_n)[["draw_date", col_name]].copy()
        timeline_df["draw_date"] = pd.to_datetime(timeline_df["draw_date"])
        timeline_df[col_name] = timeline_df[col_name].astype(str)
        timeline_df["num_int"] = timeline_df[col_name].astype(int)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=timeline_df["draw_date"],
            y=timeline_df["num_int"],
            mode="markers+lines",
            text=timeline_df[col_name],
            hovertemplate="%{x|%d %b %Y}<br>เลข: %{text}<extra></extra>",
            marker=dict(
                color=timeline_df["num_int"],
                colorscale=[[0, "#4A90D9"], [1, "#E63946"]],
                size=8,
                showscale=True,
            ),
            line=dict(color="#30363D", width=1),
        ))
        fig.update_layout(
            title=f"Timeline — {dtype_label} ({recent_n} งวดล่าสุด)",
            xaxis_title="วันที่", yaxis_title="ค่าเลข",
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)
