"""หน้าประวัติการทำนาย — ดูการทำนายที่ผ่านมาและอัตราความแม่นยำ"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src import database as db
from src.ui_components import inject_css, section_label, accuracy_badge, chart_style

st.set_page_config(page_title="ประวัติการทำนาย — หวยลาว AI", page_icon="📜", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">📜 ประวัติการทำนาย</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">ติดตามความแม่นยำของ AI ในแต่ละงวด</p>',
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#30363D;margin:.6rem 0 1rem;'>", unsafe_allow_html=True)

DIGIT_LABEL = db.DIGIT_LABEL


def _check_and_reload():
    resolved = db.check_predictions()
    if resolved:
        st.toast(f"ตรวจสอบแล้ว — อัปเดต {resolved} รายการ")
    st.cache_data.clear()


# ── โหลดข้อมูล ────────────────────────────────────────────────────────────────
pred_df   = db.load_predictions()
acc_df    = db.prediction_accuracy()

if pred_df.empty:
    st.info("ยังไม่มีประวัติการทำนาย — ไปที่หน้า **🎯 ทำนาย** แล้วกด **บันทึกการทำนาย**")
    st.stop()

# ── ตรวจสอบการทำนายที่รอผล ────────────────────────────────────────────────────
pending = int(pred_df["correct"].isna().sum())
if pending > 0:
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("🔍 ตรวจสอบผลทำนาย", use_container_width=True):
            _check_and_reload()
            st.rerun()
    with col_info:
        st.info(f"มีการทำนายรอตรวจสอบ **{pending} รายการ** — กดปุ่มเพื่ออัปเดตผล")
else:
    st.success("การทำนายทั้งหมดได้รับการตรวจสอบแล้ว")

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── สรุปความแม่นยำ ────────────────────────────────────────────────────────────
if not acc_df.empty:
    section_label("สรุปความแม่นยำแต่ละประเภท")

    cols = st.columns(min(len(acc_df), 5))
    for i, (_, row) in enumerate(acc_df.iterrows()):
        with cols[i % len(cols)]:
            label  = DIGIT_LABEL.get(row["digit_type"], row["digit_type"])
            pct    = float(row.get("accuracy_pct", 0))
            badge  = accuracy_badge(pct)
            st.markdown(
                f'<div style="background:#161B22;border:1px solid #30363D;border-radius:12px;'
                f'padding:1rem;text-align:center;margin-bottom:.5rem;">'
                f'<div style="font-size:.75rem;color:#8B949E;text-transform:uppercase;'
                f'letter-spacing:.06em;margin-bottom:.4rem;">{label}</div>'
                f'<div style="font-size:1.8rem;font-weight:900;color:#F0F6FC;margin-bottom:.3rem;">'
                f'{badge}</div>'
                f'<div style="font-size:.7rem;color:#8B949E;">'
                f'ถูก {int(row["hits"])} / {int(row["total"] - row["pending"])} งวด'
                f' · รอผล {int(row["pending"])}'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    # แผนภูมิความแม่นยำ
    if acc_df["total"].sum() > 0:
        acc_chart = acc_df[acc_df["total"] - acc_df["pending"] > 0].copy()
        if not acc_chart.empty:
            acc_chart["label"] = acc_chart["digit_type"].map(DIGIT_LABEL).fillna(acc_chart["digit_type"])
            fig = go.Figure(go.Bar(
                x=acc_chart["label"],
                y=acc_chart["accuracy_pct"],
                text=acc_chart["accuracy_pct"].apply(lambda x: f"{x:.1f}%"),
                textposition="outside",
                marker=dict(
                    color=acc_chart["accuracy_pct"],
                    colorscale=[[0, "#E63946"], [0.5, "#F5A623"], [1, "#2ECC71"]],
                    showscale=False,
                ),
            ))
            fig.update_layout(
                title="ความแม่นยำการทำนายแต่ละประเภท (%)",
                xaxis_title="ประเภทเลข", yaxis_title="ความแม่นยำ (%)",
                yaxis_range=[0, 110],
                **chart_style(),
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── ตัวกรอง ───────────────────────────────────────────────────────────────────
section_label("รายละเอียดการทำนาย")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    type_options = ["ทั้งหมด"] + [DIGIT_LABEL.get(t, t) for t in pred_df["digit_type"].unique()]
    dtype_filter = st.selectbox("ประเภทเลข", type_options)
with col_f2:
    status_filter = st.selectbox("สถานะ", ["ทั้งหมด", "✅ ถูก", "❌ ผิด", "⏳ รอผล"])
with col_f3:
    rank_filter = st.slider("อันดับ", 1, int(pred_df["rank"].max()), (1, int(pred_df["rank"].max())))

filtered = pred_df.copy()

if dtype_filter != "ทั้งหมด":
    rev_label = {v: k for k, v in DIGIT_LABEL.items()}
    dtype_key = rev_label.get(dtype_filter, dtype_filter)
    filtered  = filtered[filtered["digit_type"] == dtype_key]

if status_filter == "✅ ถูก":
    filtered = filtered[filtered["correct"] == 1]
elif status_filter == "❌ ผิด":
    filtered = filtered[filtered["correct"] == 0]
elif status_filter == "⏳ รอผล":
    filtered = filtered[filtered["correct"].isna()]

filtered = filtered[(filtered["rank"] >= rank_filter[0]) & (filtered["rank"] <= rank_filter[1])]

# ── ตาราง ─────────────────────────────────────────────────────────────────────
display = filtered.copy()
display["ประเภท"]         = display["digit_type"].map(DIGIT_LABEL).fillna(display["digit_type"])
display["วันที่ทำนาย"]    = pd.to_datetime(display["predicted_at"]).dt.strftime("%d %b %Y %H:%M")
display["อันดับ"]         = display["rank"]
display["เลขทำนาย"]      = display["number"]
display["ความน่าจะเป็น"] = display["probability"].apply(lambda x: f"{x:.2f}%")
display["ผลจริง"]        = display["actual"].fillna("—")
display["ผล"] = display["correct"].apply(
    lambda x: "✅" if x == 1 else ("❌" if x == 0 else "⏳")
)
display["ตรวจเมื่อ"] = display["checked_at"].fillna("—")

cols_show = ["วันที่ทำนาย", "ประเภท", "อันดับ", "เลขทำนาย", "ความน่าจะเป็น", "ผลจริง", "ผล", "ตรวจเมื่อ"]
st.dataframe(
    display[cols_show],
    use_container_width=True,
    hide_index=True,
)

st.caption(f"แสดง {len(display):,} จาก {len(pred_df):,} รายการ")

# ── แผนภูมิ Hit Rate ตามเวลา ──────────────────────────────────────────────────
checked = pred_df[pred_df["correct"].notna()].copy()
if len(checked) >= 5:
    st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)
    section_label("Hit Rate ตามเวลา (อันดับ 1 เท่านั้น)")

    rank1 = checked[checked["rank"] == 1].copy()
    rank1["date"] = pd.to_datetime(rank1["predicted_at"]).dt.date
    rank1 = rank1.sort_values("date")

    if len(rank1) >= 3:
        for dtype, grp in rank1.groupby("digit_type"):
            grp = grp.sort_values("date").reset_index(drop=True)
            grp["cumhits"]   = grp["correct"].cumsum()
            grp["cumtotal"]  = range(1, len(grp) + 1)
            grp["hit_rate"]  = grp["cumhits"] / grp["cumtotal"] * 100
            rank1.loc[grp.index, "hit_rate"] = grp["hit_rate"].values
            rank1.loc[grp.index, "dtype_label"] = DIGIT_LABEL.get(dtype, dtype)

        if "dtype_label" in rank1.columns:
            fig = px.line(
                rank1, x="date", y="hit_rate", color="dtype_label",
                labels={"date": "วันที่", "hit_rate": "Hit Rate สะสม (%)", "dtype_label": "ประเภท"},
                title="Hit Rate สะสม (อันดับ 1) — แยกประเภท",
            )
            fig.update_layout(**chart_style())
            st.plotly_chart(fig, use_container_width=True)
