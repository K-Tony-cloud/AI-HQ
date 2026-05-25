"""หน้าหลัก — ผลล่าสุด, สถิติ, บล็อกทำนาย, เมนูนำทาง"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd

from src import database as db
from src.analytics  import frequency, hot_cold, summary
from src.predictor  import predict_all_types
from src.ui_components import (
    inject_css, metric_row, lottery_balls,
    latest_draw_card, stale_banner,
    section_label, nav_cards, prediction_block,
)

st.set_page_config(
    page_title="หวยลาว AI",
    page_icon="🎰",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()


@st.cache_data(ttl=300)
def _load():
    return db.load()


df = _load()

# ── แบนเนอร์ข้อมูลล้าสมัย ─────────────────────────────────────────────────
if db.is_stale(hours=20):
    stale_banner(db.meta().get("last_scraped", "ไม่ทราบ"))

# ── หัวเรื่อง ─────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="font-size:2.2rem;font-weight:900;margin-bottom:.1rem;">'
    '🎰 หวยลาว AI</h1>'
    '<p style="color:#8B949E;font-size:.95rem;margin-top:0;">'
    'วิเคราะห์สถิติและทำนายด้วย AI สำหรับหวยลาว</p>',
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#30363D;margin:.8rem 0 1.2rem;'>", unsafe_allow_html=True)

if df.empty:
    st.warning("ยังไม่มีข้อมูล — ไปที่ **⚙️ ตั้งค่า** แล้วกด **ดึงข้อมูลล่าสุด** เพื่อโหลดผลรางวัล")
    st.stop()

# ── ผลล่าสุด ──────────────────────────────────────────────────────────────────
latest   = df.iloc[0]
date_str = pd.to_datetime(latest["draw_date"]).strftime("%A, %d %B %Y")
latest_draw_card(
    latest["six_digit"], date_str,
    latest["last_4"], latest["top_3"], latest["last_2"],
)

# ── ตัวชี้วัด ─────────────────────────────────────────────────────────────────
series  = df["last_2"]
hot, _  = hot_cold(series, 1)
_, cold = hot_cold(series, 1)
m       = db.meta()

metric_row([
    ("📅", pd.to_datetime(m["latest"]).strftime("%d %b %Y"),   "งวดล่าสุด"),
    ("📋", f"{m['total']:,}",                                   "งวดทั้งหมด"),
    ("📅", pd.to_datetime(m["earliest"]).strftime("%b %Y"),    "ข้อมูลตั้งแต่"),
    ("🔥", hot[0]  if hot  else "—",                           "เลขร้อน 2 ตัวล่าง"),
    ("🧊", cold[0] if cold else "—",                           "เลขเย็น 2 ตัวล่าง"),
])

st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)

# ── บล็อกทำนาย ────────────────────────────────────────────────────────────────
col_pred, col_recent = st.columns([3, 2], gap="large")

with col_pred:
    with st.spinner("กำลังคำนวณการทำนาย..."):
        preds = predict_all_types(df, lookback=5, top_n=5)

    prediction_block(preds)

    # บันทึกการทำนาย
    if st.button("💾 บันทึกการทำนายนี้", use_container_width=True):
        to_save = []
        for dtype, items in preds.items():
            for i, p in enumerate(items):
                to_save.append({
                    "digit_type":  dtype,
                    "rank":        i + 1,
                    "number":      p["number"],
                    "probability": p["probability"],
                })
        db.save_predictions(to_save)
        st.success("บันทึกการทำนายแล้ว — ระบบจะตรวจสอบความแม่นยำหลังงวดถัดไปออก")
        st.cache_data.clear()

    st.caption("ทำนายโดย Ensemble AI (Random Forest + Logistic Regression + Markov Chain) — เพื่อความบันเทิงเท่านั้น")

with col_recent:
    section_label("10 งวดล่าสุด")
    recent = df.head(10)[["draw_date","six_digit","last_4","top_3","last_2"]].copy()
    recent["draw_date"] = pd.to_datetime(recent["draw_date"]).dt.strftime("%d %b")
    recent.columns = ["งวด","6 หลัก","4 ตัวท้าย","3 ตัวบน","2 ตัวล่าง"]
    st.dataframe(recent, use_container_width=True, hide_index=True)

st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)

# ── เมนูนำทาง ────────────────────────────────────────────────────────────────
section_label("เมนู")
nav_cards([
    ("📊", "วิเคราะห์",        "ฮีตแมป, เลขร้อน/เย็น, ความถี่, ช่วงห่าง, เลขค้างนาน"),
    ("🎯", "ทำนาย",            "ผลทำนาย AI พร้อมรายละเอียดแต่ละโมเดล"),
    ("📈", "แนวโน้ม",          "ความถี่สะสม, รายวัน, รายเดือน, แยกหลัก"),
    ("📜", "ประวัติการทำนาย", "ดูการทำนายที่ผ่านมาและอัตราความแม่นยำ"),
    ("⚙️", "ตั้งค่า",         "ดึงข้อมูล, จัดการฐานข้อมูล, ส่งออก CSV"),
])

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎰 หวยลาว AI")
    st.markdown(
        f"**{m['total']} งวด** · "
        f"{pd.to_datetime(m['earliest']).strftime('%b %Y')} – "
        f"{pd.to_datetime(m['latest']).strftime('%b %Y')}"
    )
    st.markdown("---")
    if st.button("🔄 รีเฟรชข้อมูล", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("รีเฟรชอัตโนมัติทุก 5 นาที")
