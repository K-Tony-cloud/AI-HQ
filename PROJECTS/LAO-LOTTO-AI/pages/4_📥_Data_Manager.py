import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from datetime import date

from src.data_loader import DATA_DIR, RAW_DIR, LOTTERY_TYPES, SAMPLE_COLUMNS
from src import scraper
from src.ui_components import inject_css, section_label, metric_row

st.set_page_config(page_title="Data Manager", page_icon="📥", layout="wide")
inject_css()

st.markdown('<h2 style="margin-bottom:.2rem;">📥 Data Manager</h2>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Live scraper (Lao National)
# ═══════════════════════════════════════════════════════════════════════════════
section_label("Live Data — Lao National Lottery (lotto.thaiorc.com)")

cached = scraper.load_cached()

# Status row
if cached is not None and not cached.empty:
    metric_row([
        ("✅", f"{len(cached):,}",                                 "rows cached"),
        ("📅", pd.to_datetime(cached['date']).max().strftime("%d %b %Y"), "latest draw"),
        ("📅", pd.to_datetime(cached['date']).min().strftime("%d %b %Y"), "earliest draw"),
        ("🗂️", scraper.cache_path().name,                          "cache file"),
    ])
else:
    st.info("No data cached yet — fetch below to populate.")

col_a, col_b, col_c = st.columns([2, 2, 3])

with col_a:
    fetch_latest = st.button(
        "⬇ Fetch Latest Results",
        help="Incrementally fetch new draws since last update (fast)",
        use_container_width=True,
    )
with col_b:
    with st.expander("Full Refresh (all years)"):
        max_pg = st.number_input("Max pages to fetch", min_value=1, max_value=500, value=50)
        full_refresh = st.button("🔄 Full Refresh", type="secondary", use_container_width=True)
with col_c:
    if cached is not None and not cached.empty:
        csv_bytes = cached.to_csv(index=False).encode()
        st.download_button(
            "⬇ Download cached CSV",
            csv_bytes,
            file_name="lao_national_real.csv",
            use_container_width=True,
        )

# ── Fetch latest ─────────────────────────────────────────────────────────────
if fetch_latest:
    bar  = st.progress(0.0, text="Connecting…")
    info = st.empty()

    def _cb_latest(cur, total):
        bar.progress(cur / total, text=f"Fetched page {cur} / {total}")
        info.caption(f"Scanning page {cur}…")

    try:
        df, added = scraper.scrape_latest(progress_cb=_cb_latest)
        scraper.save(df)
        bar.progress(1.0, text="Done!")
        if added > 0:
            st.success(f"Added **{added}** new rows. Total: {len(df):,}")
        else:
            st.info("Already up to date — no new rows found.")
        st.rerun()
    except Exception as e:
        st.error(f"Fetch failed: {e}")

# ── Full refresh ──────────────────────────────────────────────────────────────
if full_refresh:
    bar  = st.progress(0.0, text="Starting full refresh…")
    info = st.empty()

    def _cb_full(cur, total):
        bar.progress(cur / total, text=f"Page {cur} / {total}")
        info.caption(f"Parsing page {cur}…")

    try:
        df = scraper.scrape_all(progress_cb=_cb_full, max_pages=int(max_pg))
        scraper.save(df)
        bar.progress(1.0, text="Done!")
        st.success(f"Fetched **{len(df):,}** rows across {int(max_pg)} pages.")
        st.rerun()
    except Exception as e:
        st.error(f"Refresh failed: {e}")

# ── Preview cached data ───────────────────────────────────────────────────────
if cached is not None and not cached.empty:
    with st.expander("Preview cached data (latest 20 rows)"):
        st.dataframe(cached.head(20), use_container_width=True)

st.markdown("<hr style='border-color:#30363D;margin:1.5rem 0;'>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Upload your own file
# ═══════════════════════════════════════════════════════════════════════════════
section_label("Upload Custom Dataset")
col_lt, col_up = st.columns([1, 2])
with col_lt:
    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()),
                                format_func=lambda k: LOTTERY_TYPES[k])
with col_up:
    uploaded = st.file_uploader("CSV or Excel", type=["csv", "xlsx", "xls"],
                                label_visibility="collapsed")

if uploaded:
    try:
        df_up = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

        expected = SAMPLE_COLUMNS[lottery_type]
        missing  = [c for c in expected if c not in df_up.columns]
        extra    = [c for c in df_up.columns if c not in expected]

        c1, c2, c3 = st.columns(3)
        c1.metric("Rows",    f"{len(df_up):,}")
        c2.metric("Columns", len(df_up.columns))
        c3.metric("Missing cols", len(missing))

        if missing:
            st.warning(f"Missing expected columns: **{', '.join(missing)}**")
        if extra:
            st.info(f"Extra columns (kept): {', '.join(extra)}")

        nulls = df_up.isnull().sum()
        null_cols = nulls[nulls > 0]
        if not null_cols.empty:
            st.warning(f"Null values: { {c: int(v) for c, v in null_cols.items()} }")

        st.dataframe(df_up.head(10), use_container_width=True)

        c_name, c_btn = st.columns([3, 1])
        with c_name:
            save_name = st.text_input("Save as", value=f"{lottery_type}_{date.today()}")
        with c_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Save", use_container_width=True):
                RAW_DIR.mkdir(parents=True, exist_ok=True)
                df_up.to_csv(RAW_DIR / f"{save_name}.csv", index=False)
                st.success(f"Saved → `{save_name}.csv`")
                st.rerun()

    except Exception as e:
        st.error(str(e))

st.markdown("<hr style='border-color:#30363D;margin:1.5rem 0;'>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Saved datasets
# ═══════════════════════════════════════════════════════════════════════════════
section_label("Saved Datasets")
raw_files = sorted(list(RAW_DIR.glob("*.csv")) + list(RAW_DIR.glob("*.xlsx")))

if not raw_files:
    st.info("No datasets saved yet.")
else:
    selected = st.selectbox("Select file", [f.name for f in raw_files])
    sel_path = RAW_DIR / selected
    try:
        pv = pd.read_csv(sel_path) if selected.endswith(".csv") else pd.read_excel(sel_path)
        st.markdown(f"**{len(pv):,} rows × {len(pv.columns)} columns**")
        st.dataframe(pv, use_container_width=True, height=300)
        c_dl, c_del = st.columns([3, 1])
        with c_dl:
            st.download_button("⬇ Download CSV", pv.to_csv(index=False).encode(),
                               file_name=selected.replace(".xlsx", ".csv"), use_container_width=True)
        with c_del:
            if st.button("🗑 Delete", type="secondary", use_container_width=True):
                sel_path.unlink()
                st.warning(f"Deleted **{selected}**")
                st.rerun()
    except Exception as e:
        st.error(str(e))

st.markdown("<hr style='border-color:#30363D;margin:1.5rem 0;'>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Templates
# ═══════════════════════════════════════════════════════════════════════════════
section_label("Download Data Templates")
tpl_cols = st.columns(len(LOTTERY_TYPES))
for col, (k, name) in zip(tpl_cols, LOTTERY_TYPES.items()):
    with col:
        tpl_csv = pd.DataFrame(columns=SAMPLE_COLUMNS[k]).to_csv(index=False).encode()
        st.download_button(
            f"📄 {name.split('(')[0].strip()}",
            tpl_csv, file_name=f"template_{k}.csv",
            use_container_width=True,
            help=f"Columns: {', '.join(SAMPLE_COLUMNS[k])}",
        )

with st.expander("Column reference"):
    for k, name in LOTTERY_TYPES.items():
        st.markdown(f"**{name}**")
        st.code(", ".join(SAMPLE_COLUMNS[k]))
