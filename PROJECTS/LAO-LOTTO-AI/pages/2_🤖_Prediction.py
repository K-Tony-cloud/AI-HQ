import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd

from src.data_loader import load_uploaded_file, generate_sample_data, LOTTERY_TYPES
from src.predictor import predict_next_rf, predict_next_lr, predict_markov, ensemble_predict

st.set_page_config(page_title="Prediction", page_icon="🤖", layout="wide")
st.title("🤖 Number Prediction")

st.info(
    "**Disclaimer:** Lottery draws are random events. These predictions are based on "
    "historical patterns and statistical models — not guarantees. Use for entertainment only."
)

# --- Sidebar ---
with st.sidebar:
    st.header("Data Source")
    lottery_type = st.selectbox("Lottery type", list(LOTTERY_TYPES.keys()), format_func=lambda k: LOTTERY_TYPES[k])
    use_sample = st.checkbox("Use sample data", value=True)
    uploaded = None
    if not use_sample:
        uploaded = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])

    st.markdown("---")
    st.header("Settings")
    target_col = st.text_input("Column to predict", value="result_2d")
    lookback = st.slider("Lookback window", 3, 20, 5)
    top_n = st.slider("Top N suggestions", 3, 15, 5)

# --- Load data ---
df = None
if use_sample:
    df = generate_sample_data(lottery_type)
elif uploaded:
    try:
        df = load_uploaded_file(uploaded)
    except Exception as e:
        st.error(str(e))

if df is None:
    st.warning("Upload a file or enable sample data.")
    st.stop()

if target_col not in df.columns:
    available = df.columns.tolist()
    target_col = available[0]
    st.warning(f"Column not found — using '{target_col}'.")

series = df[target_col].dropna()

# --- Ensemble ---
st.subheader("Ensemble Prediction (combined models)")
with st.spinner("Running models..."):
    ens_df = ensemble_predict(series, lookback=lookback, top_n=top_n)

fig = px.bar(ens_df, x="number", y="score", color="score",
             color_continuous_scale="Viridis",
             labels={"score": "Ensemble score", "number": "Number"},
             title="Top predicted numbers (ensemble)")
fig.update_layout(height=350)
st.plotly_chart(fig, use_container_width=True)
st.dataframe(ens_df, use_container_width=True)

# --- Individual models ---
st.subheader("Individual Model Predictions")
tab1, tab2, tab3 = st.tabs(["Random Forest", "Logistic Regression", "Markov Chain"])

with tab1:
    rf_preds = predict_next_rf(series, lookback=lookback, top_n=top_n)
    st.dataframe(pd.DataFrame(rf_preds), use_container_width=True)

with tab2:
    lr_preds = predict_next_lr(series, lookback=lookback, top_n=top_n)
    st.dataframe(pd.DataFrame(lr_preds), use_container_width=True)

with tab3:
    mk_preds = predict_markov(series, top_n=top_n)
    st.dataframe(pd.DataFrame(mk_preds), use_container_width=True)

# --- Recent draws ---
st.subheader("Recent Draws")
st.dataframe(df.tail(20)[[target_col] + (["date"] if "date" in df.columns else [])], use_container_width=True)
