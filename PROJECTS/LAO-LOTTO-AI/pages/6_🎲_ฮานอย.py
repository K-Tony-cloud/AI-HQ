"""หวยฮานอย (VietLao) — ผลล่าสุด, วิเคราะห์, ดึงข้อมูล"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import io
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src import hanoi_db as db
from src.analytics import (
    frequency, hot_cold, heatmap_matrix,
    gap_analysis, overdue, consecutive_pairs,
)
from src.predictor import predict_all_types
from src.ui_components import (
    inject_css, lottery_balls, section_label,
    chart_style, accuracy_badge, prediction_block,
)

st.set_page_config(page_title="ฮานอย — หวยลาว AI", page_icon="🎲", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">🎲 หวยฮานอย (VietLao)</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">'
    'ผลและสถิติหวยฮานอย — อัปเดตรายวัน</p>',
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#30363D;margin:.6rem 0 1rem;'>", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def _load():
    return db.load()


# ── ดึงข้อมูล (inline) ───────────────────────────────────────────────────────
with st.expander("📥 ดึง / อัปเดตข้อมูล"):
    m0 = db.meta()
    c1, c2, c3 = st.columns(3)
    c1.metric("งวดทั้งหมด", f"{m0['total']:,}")
    c2.metric("ล่าสุด", pd.to_datetime(m0["latest"]).strftime("%d %b %Y") if m0.get("latest") else "—")
    c3.metric("ดึงล่าสุด", str(m0.get("last_scraped","—"))[:16])

    if db.is_stale():
        st.warning("⚠️ ข้อมูลอาจล้าสมัย — แนะนำให้อัปเดต")

    col_btn1, col_btn2 = st.columns(2)
    delay = st.slider("หน่วงเวลา (วินาที)", 0.2, 2.0, 0.4, 0.1, key="h_delay")

    with col_btn1:
        if st.button("🔄 อัปเดตล่าสุด", use_container_width=True):
            from src.hanoi_scraper import scrape_latest
            prog = st.progress(0, text="กำลังเชื่อมต่อ...")
            def _cb(pg, total): prog.progress(int(pg/total*100), text=f"หน้า {pg}/{total}")
            try:
                added = scrape_latest(progress_cb=_cb, delay=delay)
                prog.progress(100, text="เสร็จ!")
                st.success(f"เพิ่ม {added} งวด")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(str(e))

    with col_btn2:
        if st.button("📥 ดึงข้อมูลทั้งหมด", use_container_width=True, type="secondary"):
            from src.hanoi_scraper import scrape_all
            prog2 = st.progress(0, text="กำลังเชื่อมต่อ...")
            def _cb2(pg, total): prog2.progress(int(pg/total*100), text=f"หน้า {pg}/{total}")
            try:
                total_rows = scrape_all(progress_cb=_cb2, delay=delay)
                prog2.progress(100, text="เสร็จ!")
                st.success(f"ฐานข้อมูลมีทั้งหมด {total_rows:,} งวด")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(str(e))

df = _load()

if df.empty:
    st.warning("ยังไม่มีข้อมูล — กด **ดึงข้อมูลทั้งหมด** ด้านบน")
    st.stop()

# ── ผลล่าสุด ─────────────────────────────────────────────────────────────────
latest   = df.iloc[0]
date_str = pd.to_datetime(latest["draw_date"]).strftime("%A, %d %B %Y")

st.markdown(
    f'<div class="latest-card">'
    f'<div class="lc-label">ผลรางวัลฮานอยล่าสุด</div>'
    f'<div class="lc-date">{date_str}</div>'
    f'<div class="lc-six">{latest["five_digit"]}</div>'
    f'<div class="lc-sub">'
    f'3 ตัวล่าง: <strong>{latest["last_3"]}</strong>'
    f' &nbsp;·&nbsp; 2 ตัวล่าง: <strong>{latest["last_2"]}</strong>'
    f' &nbsp;·&nbsp; 2 ตัวบน: <strong>{latest["top_2"]}</strong>'
    f'</div></div>',
    unsafe_allow_html=True,
)

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── เมตริก ────────────────────────────────────────────────────────────────────
m = db.meta()
series2 = df["last_2"].dropna()
hot, cold = hot_cold(series2, 1)

from src.ui_components import metric_row
metric_row([
    ("📅", pd.to_datetime(m["latest"]).strftime("%d %b %Y") if m.get("latest") else "—", "งวดล่าสุด"),
    ("📋", f"{m['total']:,}", "งวดทั้งหมด"),
    ("📅", pd.to_datetime(m["earliest"]).strftime("%b %Y") if m.get("earliest") else "—", "ข้อมูลตั้งแต่"),
    ("🔥", hot[0]  if hot  else "—", "เลขร้อน 2 ตัวล่าง"),
    ("🧊", cold[0] if cold else "—", "เลขเย็น 2 ตัวล่าง"),
])

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── เลือกประเภท ───────────────────────────────────────────────────────────────
DIGIT_OPTS = {
    "2 ตัวล่าง": ("last_2",  2),
    "3 ตัวล่าง": ("last_3",  3),
    "2 ตัวบน":   ("top_2",   2),
    "3 ตัวบน":   ("top_3",   3),
}

col_sel, col_top = st.columns([2, 1])
with col_sel:
    dtype_label = st.selectbox("ประเภทเลข", list(DIGIT_OPTS.keys()))
with col_top:
    top_n = st.slider("แสดง Top N", 5, 20, 10, 5)

col_name, digits = DIGIT_OPTS[dtype_label]
if col_name not in df.columns:
    st.warning(f"ไม่พบคอลัมน์ {col_name}")
    st.stop()

series = df[col_name].dropna().astype(str)

tabs = st.tabs(["🔥 ร้อน/เย็น", "📊 ความถี่", "🗺 ฮีตแมป", "📏 ช่วงห่าง", "⏳ ค้างนาน", "🎯 ทำนาย", "📋 10 งวดล่าสุด"])

# TAB 1 ── ร้อน/เย็น
with tabs[0]:
    hot, cold = hot_cold(series, top_n)
    freq_df = frequency(series)
    c1, c2 = st.columns(2)
    with c1:
        section_label(f"🔥 {top_n} เลขร้อน — {dtype_label}")
        scores_hot = [
            round(freq_df.set_index("number").loc[n, "pct"], 1)
            if n in freq_df["number"].values else 0.0
            for n in hot
        ]
        lottery_balls(hot, scores_hot)
    with c2:
        section_label(f"🧊 {top_n} เลขเย็น — {dtype_label}")
        scores_cold = [
            round(freq_df.set_index("number").loc[n, "pct"], 1)
            if n in freq_df["number"].values else 0.0
            for n in cold
        ]
        lottery_balls(cold, scores_cold)

# TAB 2 ── ความถี่
with tabs[1]:
    freq_df = frequency(series)
    top_freq = freq_df.head(top_n)
    fig = go.Figure(go.Bar(
        x=top_freq["number"], y=top_freq["count"],
        text=top_freq["pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside",
        marker=dict(color=top_freq["count"],
                    colorscale=[[0,"#30363D"],[1,"#E63946"]], showscale=False),
    ))
    fig.update_layout(title=f"ความถี่ {top_n} อันดับแรก — {dtype_label}",
                      xaxis_title="เลข", yaxis_title="จำนวนครั้ง", **chart_style())
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("ตารางความถี่ทั้งหมด"):
        st.dataframe(freq_df, use_container_width=True, hide_index=True)

# TAB 3 ── ฮีตแมป
with tabs[2]:
    if digits == 2:
        matrix, labels = heatmap_matrix(series, digits=2)
        fig = go.Figure(go.Heatmap(
            z=matrix, text=labels, texttemplate="%{text}",
            textfont={"size": 9, "color": "white"},
            colorscale=[[0,"#0D1117"],[0.5,"#E63946"],[1,"#FFD700"]], showscale=True,
        ))
        fig.update_layout(
            title=f"ฮีตแมป {dtype_label} (00–99)",
            xaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)]),
            yaxis=dict(tickvals=list(range(10)), ticktext=[str(i) for i in range(10)]),
            **chart_style(),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ฮีตแมปรองรับเฉพาะ 2 หลัก")

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
        fig.update_layout(barmode="group", title=f"ช่วงห่าง — {dtype_label}",
                          xaxis_title="เลข", yaxis_title="งวด", **chart_style())
        st.plotly_chart(fig, use_container_width=True)

# TAB 5 ── ค้างนาน
with tabs[4]:
    od_df = overdue(series, digits=digits)
    top_od = od_df.head(top_n)
    fig = go.Figure(go.Bar(
        x=top_od["number"], y=top_od["draws_since"],
        text=top_od["draws_since"], textposition="outside",
        marker_color=["#E63946" if r else "#4A90D9" for r in top_od["never_appeared"]],
    ))
    fig.update_layout(title=f"เลขค้างนาน — {dtype_label}",
                      xaxis_title="เลข", yaxis_title="งวดที่ไม่ออก", **chart_style())
    st.plotly_chart(fig, use_container_width=True)

# TAB 6 ── ทำนาย
with tabs[5]:
    with st.spinner("กำลังคำนวณ..."):
        preds = predict_all_types(df.rename(columns={
            "last_2": "last_2", "last_3": "last_3", "top_2": "top_2", "top_3": "top_3",
        }), lookback=5, top_n=5)
    # Map column names to DIGIT_COL keys
    hanoi_preds = {}
    col_to_type = {"last_2": "bottom_2", "last_3": "last_3", "top_2": "top_2", "top_3": "top_3"}
    for col_key, dtype_key in col_to_type.items():
        col = col_key
        if col in df.columns:
            from src.predictor import ensemble_predict
            s = df[col].dropna()
            if not s.empty:
                ens = ensemble_predict(s, lookback=5, top_n=5)
                hanoi_preds[dtype_key] = [{"number": r["number"], "probability": r["score"]} for _, r in ens.iterrows()]

    if hanoi_preds:
        from src.hanoi_db import DIGIT_LABEL
        # Temporarily override for prediction_block
        import src.hanoi_db as _hdb
        import src.database as _ldb
        _orig = _ldb.DIGIT_LABEL.copy()
        _ldb.DIGIT_LABEL.update(DIGIT_LABEL)
        prediction_block(hanoi_preds)
        _ldb.DIGIT_LABEL.clear()
        _ldb.DIGIT_LABEL.update(_orig)
    else:
        st.info("ข้อมูลไม่เพียงพอสำหรับการทำนาย")

# TAB 7 ── ตาราง + ดาวน์โหลด
with tabs[6]:
    section_label("10 งวดล่าสุด")
    recent = df.head(10)[["draw_date", "five_digit", "top_3", "top_2", "last_3", "last_2"]].copy()
    recent["draw_date"] = pd.to_datetime(recent["draw_date"]).dt.strftime("%d %b")
    recent.columns = ["งวด", "5 หลัก", "3 ตัวบน", "2 ตัวบน", "3 ตัวล่าง", "2 ตัวล่าง"]
    st.dataframe(recent, use_container_width=True, hide_index=True)

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("⬇️ ดาวน์โหลด CSV", buf.getvalue().encode("utf-8-sig"),
                       "hanoi_results.csv", "text/csv", use_container_width=True)
