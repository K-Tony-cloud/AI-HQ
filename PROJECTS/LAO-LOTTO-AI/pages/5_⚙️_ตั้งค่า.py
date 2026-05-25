"""หน้าตั้งค่า — ดึงข้อมูล, จัดการฐานข้อมูล, ส่งออก CSV"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import io
import streamlit as st
import pandas as pd

from src import database as db
from src.ui_components import inject_css, section_label

st.set_page_config(page_title="ตั้งค่า — หวยลาว AI", page_icon="⚙️", layout="wide")
inject_css()

st.markdown(
    '<h1 style="font-size:2rem;font-weight:900;margin-bottom:.1rem;">⚙️ ตั้งค่า</h1>'
    '<p style="color:#8B949E;font-size:.9rem;margin-top:0;">จัดการข้อมูล, ดึงข้อมูลใหม่, ส่งออก CSV</p>',
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#30363D;margin:.6rem 0 1rem;'>", unsafe_allow_html=True)

# ── สถานะฐานข้อมูล ────────────────────────────────────────────────────────────
section_label("สถานะฐานข้อมูล")
m = db.meta()

c1, c2, c3, c4 = st.columns(4)
c1.metric("📋 งวดทั้งหมด", f"{m['total']:,}")
c2.metric("📅 งวดล่าสุด",
          pd.to_datetime(m["latest"]).strftime("%d %b %Y") if m.get("latest") else "—")
c3.metric("📅 ข้อมูลตั้งแต่",
          pd.to_datetime(m["earliest"]).strftime("%b %Y") if m.get("earliest") else "—")
c4.metric("🕐 ดึงข้อมูลล่าสุด",
          str(m.get("last_scraped", "—"))[:16])

is_stale = db.is_stale(hours=20)
if is_stale:
    st.warning("⚠️ ข้อมูลอาจล้าสมัย (เกิน 20 ชั่วโมง) — แนะนำให้ดึงข้อมูลใหม่")
else:
    st.success("✅ ข้อมูลเป็นปัจจุบัน")

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── ดึงข้อมูล ─────────────────────────────────────────────────────────────────
section_label("ดึงข้อมูล")

tab_fetch1, tab_fetch2 = st.tabs(["🔄 อัปเดตล่าสุด", "📥 ดึงข้อมูลทั้งหมด"])

with tab_fetch1:
    st.markdown(
        "ดึงเฉพาะงวดที่ยังไม่มีในฐานข้อมูล "
        "— เร็วกว่าและใช้แบนด์วิดท์น้อยกว่า"
    )
    delay1 = st.slider("หน่วงเวลาระหว่างหน้า (วินาที)", 0.2, 2.0, 0.4, 0.1, key="d1")
    if st.button("▶️ ดึงข้อมูลล่าสุด", use_container_width=True):
        from src.scraper import scrape_latest
        prog = st.progress(0, text="กำลังเชื่อมต่อ...")
        status = st.empty()

        def _cb(pg: int, total: int):
            pct = int(pg / total * 100)
            prog.progress(pct, text=f"หน้า {pg}/{total}")

        try:
            added = scrape_latest(progress_cb=_cb, delay=delay1)
            prog.progress(100, text="เสร็จแล้ว!")
            st.success(f"เพิ่ม **{added}** งวดใหม่ เข้าฐานข้อมูล")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            prog.empty()
            st.error(f"เกิดข้อผิดพลาด: {e}")

with tab_fetch2:
    st.markdown(
        "ดึงข้อมูลทุกหน้าตั้งแต่ต้น — ใช้เวลานานกว่า "
        "เหมาะสำหรับการติดตั้งครั้งแรกหรือซ่อมแซมข้อมูล"
    )
    col_a, col_b = st.columns(2)
    with col_a:
        delay2 = st.slider("หน่วงเวลาระหว่างหน้า (วินาที)", 0.2, 2.0, 0.5, 0.1, key="d2")
    with col_b:
        max_pages = st.number_input("จำกัดหน้า (0 = ไม่จำกัด)", min_value=0, max_value=100, value=0)

    if st.button("📥 ดึงข้อมูลทั้งหมด", use_container_width=True, type="secondary"):
        from src.scraper import scrape_all
        prog2   = st.progress(0, text="กำลังเชื่อมต่อ...")

        def _cb2(pg: int, total: int):
            pct = int(pg / total * 100)
            prog2.progress(pct, text=f"หน้า {pg}/{total}")

        try:
            total_rows = scrape_all(
                progress_cb=_cb2,
                max_pages=int(max_pages) if max_pages > 0 else None,
                delay=delay2,
            )
            prog2.progress(100, text="เสร็จแล้ว!")
            st.success(f"ฐานข้อมูลมีทั้งหมด **{total_rows:,}** งวด")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            prog2.empty()
            st.error(f"เกิดข้อผิดพลาด: {e}")

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── ส่งออก CSV ────────────────────────────────────────────────────────────────
section_label("ส่งออก CSV")

df_export = db.load()
if not df_export.empty:
    c_dl1, c_dl2 = st.columns(2)

    with c_dl1:
        buf = io.StringIO()
        df_export.to_csv(buf, index=False)
        st.download_button(
            label="⬇️ ดาวน์โหลดผลรางวัลทั้งหมด",
            data=buf.getvalue().encode("utf-8-sig"),
            file_name="lao_lottery_results.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with c_dl2:
        pred_df = db.load_predictions()
        if not pred_df.empty:
            buf2 = io.StringIO()
            pred_df.to_csv(buf2, index=False)
            st.download_button(
                label="⬇️ ดาวน์โหลดประวัติการทำนาย",
                data=buf2.getvalue().encode("utf-8-sig"),
                file_name="lao_lottery_predictions.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("ยังไม่มีประวัติการทำนาย")
else:
    st.info("ยังไม่มีข้อมูลสำหรับส่งออก")

st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)

# ── Danger Zone ───────────────────────────────────────────────────────────────
section_label("⚠️ Danger Zone")

with st.expander("ลบข้อมูลทั้งหมด (ไม่สามารถกู้คืนได้)"):
    st.error("การดำเนินการนี้จะลบข้อมูลทั้งหมดออกจากฐานข้อมูลอย่างถาวร")
    confirm = st.text_input('พิมพ์ "ยืนยันลบ" เพื่อดำเนินการ')
    if st.button("🗑️ ลบข้อมูลทั้งหมด", type="primary"):
        if confirm == "ยืนยันลบ":
            db.clear()
            st.success("ลบข้อมูลทั้งหมดแล้ว")
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("กรุณาพิมพ์ 'ยืนยันลบ' เพื่อยืนยัน")

# ── รีเฟรชแคช ─────────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#30363D;margin:.8rem 0;'>", unsafe_allow_html=True)
if st.button("🔄 รีเฟรชแคช", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
