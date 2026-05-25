"""หวยหุ้นไทย — ดัชนี SET, ร้อน/เย็น, ความถี่, ทำนาย"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import io
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src import stock_db as db
from src.analytics import frequency, hot_cold, heatmap_matrix, gap_analysis, overdue
from src.predictor import ensemble_predict
from src.ui_components import (
    inject_css, lottery_balls, section_label, chart_style, metric_row,
)

st.set_page_config(page_title="หุ้นไทย — หวยลาว AI", page_icon="💹", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">💹 หวยหุ้นไทย</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">'
    'เลขจากดัชนี SET — เปิดเช้า (Open) & ปิดบ่าย (Close)</p>',
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#30363D;margin:.6rem 0 1rem;'>", unsafe_allow_html=True)
st.info(
    "📌 เลขหวยหุ้นคำนวณจาก 2 ตัวท้ายของดัชนี SET ณ เวลา **เปิดตลาด** (Open) และ **ปิดตลาด** (Close) แต่ละวัน  "
    "ข้อมูลย้อนหลังตั้งแต่ปี 1996 ผ่าน Yahoo Finance"
)


@st.cache_data(ttl=300)
def _load(session=None):
    return db.load(session=session)


# ── ดึงข้อมูล ─────────────────────────────────────────────────────────────────
with st.expander("📥 ดึง / อัปเดตข้อมูล"):
    m0 = db.meta()
    c1, c2, c3 = st.columns(3)
    c1.metric("บันทึกทั้งหมด", f"{m0['total']:,}")
    c2.metric("ล่าสุด", pd.to_datetime(m0["latest"]).strftime("%d %b %Y") if m0.get("latest") else "—")
    c3.metric("ดึงล่าสุด", str(m0.get("last_scraped","—"))[:16])

    if db.is_stale():
        st.warning("⚠️ ข้อมูลอาจล้าสมัย — แนะนำให้อัปเดต")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 อัปเดตล่าสุด", use_container_width=True, key="s_latest"):
            from src.stock_scraper import fetch_latest
            with st.spinner("กำลังดึงข้อมูลจาก Yahoo Finance..."):
                try:
                    added = fetch_latest()
                    st.success(f"เพิ่ม {added} รายการ")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    with col_btn2:
        if st.button("📥 ดึงข้อมูลทั้งหมด (ตั้งแต่ปี 1996)", use_container_width=True,
                     type="secondary", key="s_all"):
            from src.stock_scraper import fetch_all
            with st.spinner("กำลังดึงข้อมูลทั้งหมด (~7,000 วัน)..."):
                try:
                    total_rows = fetch_all()
                    st.success(f"ฐานข้อมูลมีทั้งหมด {total_rows:,} รายการ")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

df_all  = _load()
df_open = _load(session="open")
df_close = _load(session="close")

if df_all.empty:
    st.warning("ยังไม่มีข้อมูล — กด **ดึงข้อมูลทั้งหมด** ด้านบน")
    st.stop()

# ── ผลล่าสุด ─────────────────────────────────────────────────────────────────
latest_open  = df_open.iloc[0]  if not df_open.empty  else None
latest_close = df_close.iloc[0] if not df_close.empty else None

if latest_open is not None or latest_close is not None:
    lat = latest_close if latest_close is not None else latest_open
    date_str = pd.to_datetime(lat["draw_date"]).strftime("%A, %d %B %Y")
    o_val = f"{latest_open['set_value']:.2f} → {latest_open['last_2']}" if latest_open is not None else "—"
    c_val = f"{latest_close['set_value']:.2f} → {latest_close['last_2']}" if latest_close is not None else "—"

    st.markdown(
        f'<div class="latest-card">'
        f'<div class="lc-label">ดัชนี SET ล่าสุด</div>'
        f'<div class="lc-date">{date_str}</div>'
        f'<div class="lc-six">{lat["set_value"]:.2f}</div>'
        f'<div class="lc-sub">'
        f'เปิดเช้า: <strong>{o_val}</strong>'
        f' &nbsp;·&nbsp; ปิดบ่าย: <strong>{c_val}</strong>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── เมตริก ────────────────────────────────────────────────────────────────────
m   = db.meta()
s2o = df_open["last_2"].dropna() if not df_open.empty else pd.Series(dtype=str)
hot_o, cold_o = hot_cold(s2o, 1) if len(s2o) > 5 else (["—"], ["—"])

metric_row([
    ("📅", pd.to_datetime(m["latest"]).strftime("%d %b %Y") if m.get("latest") else "—", "วันล่าสุด"),
    ("📋", f"{m['total']:,}", "บันทึกทั้งหมด"),
    ("📅", pd.to_datetime(m["earliest"]).strftime("%b %Y") if m.get("earliest") else "—", "ข้อมูลตั้งแต่"),
    ("🔥", hot_o[0]  if hot_o  else "—", "เลขร้อน เปิดเช้า"),
    ("🧊", cold_o[0] if cold_o else "—", "เลขเย็น เปิดเช้า"),
])

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── ตัวเลือก ──────────────────────────────────────────────────────────────────
c_sel, c_top = st.columns([2, 1])
with c_sel:
    session_label = st.selectbox("เซสชัน", ["เปิดเช้า (Open)", "ปิดบ่าย (Close)"])
with c_top:
    top_n = st.slider("แสดง Top N", 5, 20, 10, 5, key="sn")

sess_key = "open" if "Open" in session_label else "close"
df_sess  = df_open if sess_key == "open" else df_close
digit_col = "last_2"

if df_sess.empty:
    st.info("ยังไม่มีข้อมูลสำหรับเซสชันนี้")
    st.stop()

series = df_sess[digit_col].dropna().astype(str)

tabs = st.tabs(["🔥 ร้อน/เย็น", "📊 ความถี่", "🗺 ฮีตแมป", "📏 ช่วงห่าง", "⏳ ค้างนาน", "🎯 ทำนาย", "📈 Timeline", "📋 ตาราง"])

# TAB 1 ── ร้อน/เย็น
with tabs[0]:
    hot, cold = hot_cold(series, top_n)
    freq_df = frequency(series)
    c1, c2 = st.columns(2)
    with c1:
        section_label(f"🔥 {top_n} เลขร้อน — {session_label}")
        scores_h = [
            round(freq_df.set_index("number").loc[n,"pct"],1)
            if n in freq_df["number"].values else 0.0
            for n in hot
        ]
        lottery_balls(hot, scores_h)
    with c2:
        section_label(f"🧊 {top_n} เลขเย็น — {session_label}")
        scores_c = [
            round(freq_df.set_index("number").loc[n,"pct"],1)
            if n in freq_df["number"].values else 0.0
            for n in cold
        ]
        lottery_balls(cold, scores_c)

# TAB 2 ── ความถี่
with tabs[1]:
    freq_df = frequency(series)
    top_freq = freq_df.head(top_n)
    fig = go.Figure(go.Bar(
        x=top_freq["number"], y=top_freq["count"],
        text=top_freq["pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside",
        marker=dict(color=top_freq["count"],
                    colorscale=[[0,"#30363D"],[1,"#2ECC71"]], showscale=False),
    ))
    fig.update_layout(title=f"ความถี่ — {session_label}", xaxis_title="เลข",
                      yaxis_title="จำนวนวัน", **chart_style())
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("ตารางความถี่ทั้งหมด"):
        st.dataframe(freq_df, use_container_width=True, hide_index=True)

# TAB 3 ── ฮีตแมป
with tabs[2]:
    matrix, labels = heatmap_matrix(series, digits=2)
    fig = go.Figure(go.Heatmap(
        z=matrix, text=labels, texttemplate="%{text}",
        textfont={"size": 9, "color": "white"},
        colorscale=[[0,"#0D1117"],[0.5,"#2ECC71"],[1,"#FFD700"]], showscale=True,
    ))
    fig.update_layout(
        title=f"ฮีตแมป 2 ตัวล่าง — {session_label}",
        xaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)]),
        yaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)]),
        **chart_style(),
    )
    st.plotly_chart(fig, use_container_width=True)

# TAB 4 ── ช่วงห่าง
with tabs[3]:
    gap_df = gap_analysis(series)
    if gap_df.empty:
        st.info("ข้อมูลไม่เพียงพอ")
    else:
        top_gap = gap_df.head(top_n)
        fig = go.Figure()
        fig.add_trace(go.Bar(name="เฉลี่ย", x=top_gap["number"], y=top_gap["avg_gap"], marker_color="#4A90D9"))
        fig.add_trace(go.Bar(name="สูงสุด", x=top_gap["number"], y=top_gap["max_gap"], marker_color="#E63946"))
        fig.update_layout(barmode="group", title=f"ช่วงห่าง — {session_label}",
                          xaxis_title="เลข", yaxis_title="วัน", **chart_style())
        st.plotly_chart(fig, use_container_width=True)

# TAB 5 ── ค้างนาน
with tabs[4]:
    od_df = overdue(series, digits=2)
    top_od = od_df.head(top_n)
    fig = go.Figure(go.Bar(
        x=top_od["number"], y=top_od["draws_since"],
        text=top_od["draws_since"], textposition="outside",
        marker_color=["#E63946" if r else "#4A90D9" for r in top_od["never_appeared"]],
    ))
    fig.update_layout(title=f"เลขค้างนาน — {session_label}",
                      xaxis_title="เลข", yaxis_title="วันที่ไม่ออก", **chart_style())
    st.plotly_chart(fig, use_container_width=True)

# TAB 6 ── ทำนาย
with tabs[5]:
    section_label(f"ทำนายวันถัดไป — {session_label}")
    with st.spinner("กำลังคำนวณ..."):
        ens_df = ensemble_predict(series, lookback=5, top_n=10)
    top_preds = ens_df.head(5)
    lottery_balls(top_preds["number"].tolist(),
                  top_preds["score"].tolist())
    fig = go.Figure(go.Bar(
        x=ens_df["number"], y=ens_df["score"],
        text=ens_df["score"].apply(lambda x: f"{x:.1f}"),
        textposition="outside",
        marker=dict(color=ens_df["score"],
                    colorscale=[[0,"#30363D"],[1,"#FFD700"]], showscale=False),
    ))
    fig.update_layout(title=f"Ensemble Score — {session_label}",
                      xaxis_title="เลข", yaxis_title="Score", **chart_style())
    st.plotly_chart(fig, use_container_width=True)
    st.caption("เพื่อความบันเทิงเท่านั้น")

# TAB 7 ── Timeline
with tabs[6]:
    recent_n = st.slider("ย้อนหลัง (วัน)", 30, min(500, len(df_sess)), 90, 10, key="tl")
    tl = df_sess.head(recent_n).copy()
    tl["draw_date"] = pd.to_datetime(tl["draw_date"])
    tl["num_int"] = tl["last_2"].astype(int)
    tl["set_val_fmt"] = tl["set_value"].apply(lambda x: f"{x:.2f}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=tl["draw_date"], y=tl["set_value"],
        name="SET ดัชนี", mode="lines",
        line=dict(color="#4A90D9", width=2),
        yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=tl["draw_date"], y=tl["num_int"],
        name="เลข 2 ตัวล่าง", mode="markers",
        marker=dict(color=tl["num_int"],
                    colorscale=[[0,"#4A90D9"],[1,"#E63946"]], size=7, showscale=False),
        hovertemplate="%{x|%d %b %Y}<br>เลข: %{y:02d}<extra></extra>",
        yaxis="y1",
    ))
    fig.update_layout(
        title=f"Timeline — {session_label} ({recent_n} วันล่าสุด)",
        xaxis_title="วันที่",
        yaxis=dict(title="เลข 2 ตัว", range=[0, 99]),
        yaxis2=dict(title="SET Index", overlaying="y", side="right"),
        **chart_style(),
    )
    st.plotly_chart(fig, use_container_width=True)

# TAB 8 ── ตาราง
with tabs[7]:
    section_label("ข้อมูลล่าสุด")
    show = df_sess.head(50).copy()
    show["draw_date"] = pd.to_datetime(show["draw_date"]).dt.strftime("%d %b %Y")
    show["set_value"] = show["set_value"].apply(lambda x: f"{x:.2f}")
    show.columns = ["วันที่", "เซสชัน", "ดัชนี SET", "2 ตัวล่าง", "2 ตัวบน"]
    st.dataframe(show, use_container_width=True, hide_index=True)

    buf = io.StringIO()
    df_all.to_csv(buf, index=False)
    st.download_button("⬇️ ดาวน์โหลด CSV ทั้งหมด",
                       buf.getvalue().encode("utf-8-sig"),
                       "thai_stock_lottery.csv", "text/csv",
                       use_container_width=True)
