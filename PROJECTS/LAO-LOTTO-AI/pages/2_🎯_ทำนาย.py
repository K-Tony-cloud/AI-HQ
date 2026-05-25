"""หน้าทำนาย — ผลทำนาย AI พร้อมรายละเอียดแต่ละโมเดล"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src import database as db
from src.predictor import (
    predict_next_rf, predict_next_lr, predict_markov,
    ensemble_predict, predict_all_types,
)
from src.ui_components import inject_css, lottery_balls, section_label, chart_style, prediction_block

st.set_page_config(page_title="ทำนาย — หวยลาว AI", page_icon="🎯", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">🎯 ทำนาย AI</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">Ensemble: Random Forest + Logistic Regression + Markov Chain</p>',
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

# ── การตั้งค่า ────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
with c1:
    lookback = st.slider("Lookback (งวด)", min_value=3, max_value=20, value=5)
with c2:
    top_n = st.slider("จำนวนการทำนาย", min_value=3, max_value=10, value=5)
with c3:
    dtype_label = st.selectbox(
        "ประเภทเลข (รายละเอียดโมเดล)",
        ["2 ตัวล่าง", "2 ตัวบน", "3 ตัวล่าง", "3 ตัวบน", "4 ตัวท้าย"],
    )

DIGIT_OPTS = {
    "2 ตัวล่าง": "last_2",
    "2 ตัวบน":   "top_2",
    "3 ตัวล่าง": "last_3",
    "3 ตัวบน":   "top_3",
    "4 ตัวท้าย": "last_4",
}
col_name = DIGIT_OPTS[dtype_label]

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── บล็อกทำนายรวมทุกประเภท ───────────────────────────────────────────────────
section_label("ผลทำนายทุกประเภท (Ensemble)")

with st.spinner("กำลังคำนวณ..."):
    preds_all = predict_all_types(df, lookback=lookback, top_n=top_n)

prediction_block(preds_all)

# ── บันทึกการทำนาย ────────────────────────────────────────────────────────────
if st.button("💾 บันทึกการทำนายนี้", use_container_width=True):
    to_save = []
    for dtype, items in preds_all.items():
        for i, p in enumerate(items):
            to_save.append({
                "digit_type":  dtype,
                "rank":        i + 1,
                "number":      p["number"],
                "probability": p["probability"],
            })
    db.save_predictions(to_save)
    st.success("บันทึกการทำนายแล้ว — ระบบจะตรวจสอบความแม่นยำหลังงวดถัดไปออก")

st.markdown("<hr style='border-color:#30363D;margin:1rem 0;'>", unsafe_allow_html=True)

# ── รายละเอียดแต่ละโมเดล ─────────────────────────────────────────────────────
section_label(f"รายละเอียดแต่ละโมเดล — {dtype_label}")

if col_name not in df.columns:
    st.warning(f"ไม่พบคอลัมน์ {col_name}")
    st.stop()

series = df[col_name].dropna()
if series.empty:
    st.stop()

with st.spinner("กำลังรัน 3 โมเดล..."):
    rf_preds     = predict_next_rf(series, lookback=lookback, top_n=top_n)
    lr_preds     = predict_next_lr(series, lookback=lookback, top_n=top_n)
    mk_preds     = predict_markov(series, top_n=top_n)
    ens_df       = ensemble_predict(series, lookback=lookback, top_n=top_n)

tabs = st.tabs(["🌲 Random Forest", "📐 Logistic Regression", "🔗 Markov Chain", "🏆 Ensemble"])

def _model_chart(preds: list[dict], title: str, color: str):
    if not preds:
        st.info("ข้อมูลไม่เพียงพอ")
        return
    nums  = [p["number"] for p in preds]
    probs = [p["probability"] for p in preds]
    fig = go.Figure(go.Bar(
        x=nums, y=probs,
        text=[f"{p:.1f}%" for p in probs],
        textposition="outside",
        marker_color=color,
    ))
    fig.update_layout(
        title=title,
        xaxis_title="เลข", yaxis_title="ความน่าจะเป็น (%)",
        **chart_style(),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        pd.DataFrame(preds)[["number", "probability"]].rename(
            columns={"number": "เลข", "probability": "ความน่าจะเป็น (%)"}
        ),
        use_container_width=True, hide_index=True,
    )

with tabs[0]:
    lottery_balls([p["number"] for p in rf_preds[:5]], [p["probability"] for p in rf_preds[:5]])
    _model_chart(rf_preds, f"Random Forest — {dtype_label}", "#E63946")

with tabs[1]:
    lottery_balls([p["number"] for p in lr_preds[:5]], [p["probability"] for p in lr_preds[:5]])
    _model_chart(lr_preds, f"Logistic Regression — {dtype_label}", "#4A90D9")

with tabs[2]:
    lottery_balls([p["number"] for p in mk_preds[:5]], [p["probability"] for p in mk_preds[:5]])
    _model_chart(mk_preds, f"Markov Chain — {dtype_label}", "#2ECC71")

with tabs[3]:
    ens_list = [{"number": r["number"], "probability": r["score"]} for _, r in ens_df.iterrows()]
    lottery_balls([p["number"] for p in ens_list[:5]], [p["probability"] for p in ens_list[:5]])

    fig = go.Figure(go.Bar(
        x=ens_df["number"],
        y=ens_df["score"],
        text=ens_df["score"].apply(lambda x: f"{x:.1f}"),
        textposition="outside",
        marker=dict(
            color=ens_df["score"],
            colorscale=[[0, "#30363D"], [1, "#FFD700"]],
            showscale=False,
        ),
    ))
    fig.update_layout(
        title=f"Ensemble Score — {dtype_label} (RF×0.4 + LR×0.3 + MK×0.3)",
        xaxis_title="เลข", yaxis_title="Ensemble Score",
        **chart_style(),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        ens_df.rename(columns={"number": "เลข", "score": "Ensemble Score"}),
        use_container_width=True, hide_index=True,
    )

st.caption("ทำนายโดย Ensemble AI — เพื่อความบันเทิงเท่านั้น ไม่ใช่คำแนะนำการพนัน")
