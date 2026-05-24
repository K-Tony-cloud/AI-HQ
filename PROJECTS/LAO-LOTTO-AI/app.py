import streamlit as st

st.set_page_config(
    page_title="LAO LOTTO AI",
    page_icon="🎰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎰 LAO LOTTO AI")
st.markdown(
    """
Welcome to **LAO LOTTO AI** — a statistical analysis and pattern-based prediction tool
for Lao lottery results.

---

### Pages

| Page | What it does |
|------|-------------|
| 📊 **Analysis** | Frequency charts, hot/cold numbers, gap analysis, overdue numbers |
| 🤖 **Prediction** | Random Forest, Logistic Regression, and Markov Chain ensemble predictions |
| 📥 **Data Manager** | Upload, preview, and manage your result datasets |

---

### Getting started

1. Go to **📥 Data Manager** and upload a CSV with your historical results, OR
2. Enable **"Use sample data"** on any page to explore with generated data.

> **Note:** Lottery draws are random. All predictions are statistical patterns only — not guarantees.
"""
)

st.sidebar.success("Select a page above.")
