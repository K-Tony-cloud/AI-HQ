import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from datetime import date

from src.data_loader import DATA_DIR, RAW_DIR, LOTTERY_TYPES, SAMPLE_COLUMNS
from src.ui_components import inject_css, section_label, metric_row

st.set_page_config(page_title="Data Manager", page_icon="📥", layout="wide")
inject_css()

st.markdown('<h2 style="margin-bottom:.2rem;">📥 Data Manager</h2>', unsafe_allow_html=True)
st.caption("Upload, preview, validate, and manage your lottery result datasets.")

# ── Upload ────────────────────────────────────────────────────────────────────
section_label("Upload New Dataset")
col_lt, col_up = st.columns([1, 2])
with col_lt:
    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()),
                                format_func=lambda k: LOTTERY_TYPES[k])
with col_up:
    uploaded = st.file_uploader("CSV or Excel file", type=["csv", "xlsx", "xls"],
                                label_visibility="collapsed")

if uploaded:
    try:
        df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

        # ── Validation ──────────────────────────────────────────────────────
        expected_cols = SAMPLE_COLUMNS[lottery_type]
        missing = [c for c in expected_cols if c not in df.columns]
        extra   = [c for c in df.columns if c not in expected_cols]

        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("Rows",    f"{len(df):,}")
        col_v2.metric("Columns", len(df.columns))
        col_v3.metric("Missing expected cols", len(missing))

        if missing:
            st.warning(f"Missing expected columns: **{', '.join(missing)}** — check the template below.")
        if extra:
            st.info(f"Extra columns (will be kept): {', '.join(extra)}")

        # ── Null check ──────────────────────────────────────────────────────
        nulls = df.isnull().sum()
        null_cols = nulls[nulls > 0]
        if not null_cols.empty:
            st.warning(f"Null values found: { {c: int(v) for c, v in null_cols.items()} }")

        st.markdown("**Preview (first 10 rows)**")
        st.dataframe(df.head(10), use_container_width=True)

        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            save_name = st.text_input("Save as", value=f"{lottery_type}_{date.today()}")
        with col_s2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Save to data/raw/", use_container_width=True):
                RAW_DIR.mkdir(parents=True, exist_ok=True)
                out = RAW_DIR / f"{save_name}.csv"
                df.to_csv(out, index=False)
                st.success(f"Saved → `{out}`")
                st.rerun()

    except Exception as e:
        st.error(str(e))

# ── Saved datasets ────────────────────────────────────────────────────────────
section_label("Saved Datasets")
raw_files = sorted(list(RAW_DIR.glob("*.csv")) + list(RAW_DIR.glob("*.xlsx")))

if not raw_files:
    st.info("No datasets saved yet. Upload a file above.")
else:
    metric_row([
        ("🗂️", str(len(raw_files)), "saved files"),
    ])

    selected = st.selectbox("Select a file", [f.name for f in raw_files])
    sel_path = RAW_DIR / selected

    try:
        preview_df = pd.read_csv(sel_path) if selected.endswith(".csv") else pd.read_excel(sel_path)
        st.markdown(f"**{len(preview_df):,} rows × {len(preview_df.columns)} columns**")
        st.dataframe(preview_df, use_container_width=True, height=320)

        col_dl, col_del = st.columns([3, 1])
        with col_dl:
            csv_bytes = preview_df.to_csv(index=False).encode()
            st.download_button("⬇ Download as CSV", csv_bytes,
                               file_name=selected.replace(".xlsx", ".csv"),
                               use_container_width=True)
        with col_del:
            if st.button("🗑 Delete", type="secondary", use_container_width=True):
                sel_path.unlink()
                st.warning(f"Deleted **{selected}**")
                st.rerun()
    except Exception as e:
        st.error(str(e))

# ── Template download ─────────────────────────────────────────────────────────
section_label("Download Data Template")
st.markdown("Use these templates to format your data correctly before uploading.")

cols_tpl = st.columns(len(LOTTERY_TYPES))
for col, (lt_key, lt_name) in zip(cols_tpl, LOTTERY_TYPES.items()):
    with col:
        tpl_df  = pd.DataFrame(columns=SAMPLE_COLUMNS[lt_key])
        tpl_csv = tpl_df.to_csv(index=False).encode()
        st.download_button(
            f"📄 {lt_name.split('(')[0].strip()}",
            tpl_csv,
            file_name=f"template_{lt_key}.csv",
            use_container_width=True,
            help=f"Columns: {', '.join(SAMPLE_COLUMNS[lt_key])}",
        )

# ── Column reference ──────────────────────────────────────────────────────────
with st.expander("Column reference for all lottery types"):
    for lt_key, lt_name in LOTTERY_TYPES.items():
        st.markdown(f"**{lt_name}**")
        st.code(", ".join(SAMPLE_COLUMNS[lt_key]))
