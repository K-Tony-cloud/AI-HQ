"""Settings — fetch live data, DB management, export."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from src import database as db, scraper
from src.ui_components import inject_css, section_label, metric_row

st.set_page_config(page_title="Settings · LAO LOTTO AI", page_icon="⚙️", layout="wide")
inject_css()

st.markdown('<h2 style="margin-bottom:.2rem;">⚙️ Settings & Data</h2>', unsafe_allow_html=True)

# ── DB Status ─────────────────────────────────────────────────────────────────
section_label("Database Status")
m = db.meta()

if m["total"]:
    metric_row([
        ("🗄",  f"{m['total']:,}",                                         "rows in DB"),
        ("📅",  pd.to_datetime(m['latest']).strftime("%d %b %Y")   if m['latest']   else "—", "latest draw"),
        ("📅",  pd.to_datetime(m['earliest']).strftime("%d %b %Y") if m['earliest'] else "—", "earliest draw"),
        ("🕐",  m['last_scraped'][:16].replace("T", " ")            if m['last_scraped'] else "—", "last scraped"),
    ])
    stale_status = "⚠ Stale — update recommended" if db.is_stale() else "✅ Up to date"
    st.markdown(f"**Status:** {stale_status}")
else:
    st.info("Database is empty. Fetch data below to get started.")

st.markdown("<hr style='border-color:#30363D;margin:1.2rem 0;'>", unsafe_allow_html=True)

# ── Fetch latest ──────────────────────────────────────────────────────────────
section_label("Fetch Live Data from lotto.thaiorc.com")

c1, c2 = st.columns(2)
with c1:
    st.markdown(
        "**Fetch Latest** — downloads only new draws since your last update. "
        "Fast, usually 1–2 pages."
    )
    fetch_latest = st.button("⬇ Fetch Latest Results", use_container_width=True, type="primary")

with c2:
    st.markdown(
        "**Full Refresh** — re-downloads all available pages. "
        "Use when starting fresh or to repair gaps."
    )
    with st.expander("Full Refresh options"):
        max_pg = st.number_input("Max pages", min_value=1, max_value=200, value=10,
                                 help="Each page has ~30 draws. 10 pages ≈ 300 draws.")
        full_refresh = st.button("🔄 Full Refresh", type="secondary", use_container_width=True)

# ── Run: fetch latest ─────────────────────────────────────────────────────────
if fetch_latest:
    bar  = st.progress(0.0, text="Connecting to lotto.thaiorc.com...")
    info = st.empty()

    def _cb(cur, total):
        pct = cur / max(total, 1)
        bar.progress(pct, text=f"Fetching page {cur} of {total}...")
        info.caption(f"Parsing draw data from page {cur}...")

    try:
        added = scraper.scrape_latest(progress_cb=_cb)
        bar.progress(1.0, text="Done!")
        info.empty()
        if added > 0:
            st.success(f"✅ Added **{added}** new draws. Total: {db.row_count():,}")
        else:
            st.info("Already up to date — no new draws found.")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        bar.empty()
        st.error(f"Fetch failed: {e}")

# ── Run: full refresh ─────────────────────────────────────────────────────────
if full_refresh:
    bar  = st.progress(0.0, text="Starting full refresh...")
    info = st.empty()

    def _cb_full(cur, total):
        pct = cur / max(total, 1)
        bar.progress(pct, text=f"Page {cur} of {total}...")
        info.caption(f"Parsing page {cur}...")

    try:
        total_rows = scraper.scrape_all(progress_cb=_cb_full, max_pages=int(max_pg))
        bar.progress(1.0, text="Done!")
        info.empty()
        st.success(f"✅ Full refresh complete. **{total_rows:,}** rows in database.")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        bar.empty()
        st.error(f"Refresh failed: {e}")

st.markdown("<hr style='border-color:#30363D;margin:1.2rem 0;'>", unsafe_allow_html=True)

# ── Export ────────────────────────────────────────────────────────────────────
section_label("Export Data")
df = db.load()

if not df.empty:
    c_csv, c_info = st.columns([2, 3])
    with c_csv:
        csv_bytes = df.to_csv(index=False).encode()
        st.download_button(
            "⬇ Download all data as CSV",
            csv_bytes,
            file_name="lao_national_lottery.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c_info:
        st.caption(
            f"Exports all {len(df):,} draws with columns: "
            "`draw_date`, `draw_date_be`, `six_digit`, `last_3`, `last_2`"
        )

    with st.expander("Preview exported data (first 20 rows)"):
        preview = df.head(20).copy()
        preview["draw_date"] = pd.to_datetime(preview["draw_date"]).dt.strftime("%d %b %Y")
        st.dataframe(preview, use_container_width=True, hide_index=True)

st.markdown("<hr style='border-color:#30363D;margin:1.2rem 0;'>", unsafe_allow_html=True)

# ── Danger zone ───────────────────────────────────────────────────────────────
section_label("Danger Zone")
with st.expander("Clear all data from database"):
    st.warning("This will delete all draw history from the local SQLite database. You can re-fetch from the source above.")
    confirm = st.text_input("Type **DELETE** to confirm")
    if st.button("🗑 Clear Database", type="secondary") and confirm == "DELETE":
        db.clear()
        st.cache_data.clear()
        st.success("Database cleared.")
        st.rerun()

# ── About ─────────────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#30363D;margin:1.2rem 0;'>", unsafe_allow_html=True)
section_label("About")
st.markdown("""
| Item | Detail |
|------|--------|
| **Data source** | [lotto.thaiorc.com](https://lotto.thaiorc.com/lao/stats/lottery-years20.php) |
| **Database** | SQLite — stored locally in `db/lao_lotto.db` |
| **Lottery** | Lao National Lottery (ສະຫວັນເດດ) — daily draws |
| **Date system** | Buddhist Era (BE) converted to Gregorian CE automatically |
| **Models** | Random Forest · Logistic Regression · Markov Chain (ensemble) |

> Lottery draws are **random events**. All predictions are statistical patterns only.
""")
