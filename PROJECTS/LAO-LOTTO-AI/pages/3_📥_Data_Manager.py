import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from datetime import date

from src.data_loader import DATA_DIR, RAW_DIR, LOTTERY_TYPES, SAMPLE_COLUMNS

st.set_page_config(page_title="Data Manager", page_icon="📥", layout="wide")
st.title("📥 Data Manager")

st.markdown("Manage your lottery result datasets stored locally.")

# --- Upload & Save ---
st.subheader("Upload New Data")
lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k])
uploaded = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])

if uploaded:
    try:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)
        st.success(f"Preview: {len(df)} rows × {len(df.columns)} columns")
        st.dataframe(df.head(10), use_container_width=True)

        save_name = st.text_input("Save as (filename without extension)", value=f"{lottery_type}_{date.today()}")
        if st.button("Save to data/raw/"):
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            out = RAW_DIR / f"{save_name}.csv"
            df.to_csv(out, index=False)
            st.success(f"Saved to {out}")
    except Exception as e:
        st.error(str(e))

st.markdown("---")

# --- Existing files ---
st.subheader("Existing Datasets")
raw_files = list(RAW_DIR.glob("*.csv")) + list(RAW_DIR.glob("*.xlsx"))
if raw_files:
    selected = st.selectbox("Select file to preview / delete", [f.name for f in raw_files])
    sel_path = RAW_DIR / selected
    try:
        preview_df = pd.read_csv(sel_path) if selected.endswith(".csv") else pd.read_excel(sel_path)
        st.dataframe(preview_df, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            csv = preview_df.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, file_name=selected.replace(".xlsx", ".csv"))
        with col2:
            if st.button("Delete this file", type="secondary"):
                sel_path.unlink()
                st.warning(f"Deleted {selected}")
                st.rerun()
    except Exception as e:
        st.error(str(e))
else:
    st.info("No datasets found in data/raw/. Upload a file above.")

st.markdown("---")

# --- Template download ---
st.subheader("Download Data Template")
tpl_type = st.selectbox("Template for", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k], key="tpl")
cols = SAMPLE_COLUMNS[tpl_type]
tpl_df = pd.DataFrame(columns=cols)
tpl_csv = tpl_df.to_csv(index=False).encode()
st.download_button(f"Download {LOTTERY_TYPES[tpl_type]} template", tpl_csv, file_name=f"template_{tpl_type}.csv")
