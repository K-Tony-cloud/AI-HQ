# 🎰 LAO LOTTO AI

Statistical analysis and AI-powered predictions for the **Lao National Lottery** (ສະຫວັນເດດ).  
Built with Python + Streamlit. Data sourced from [lotto.thaiorc.com](https://lotto.thaiorc.com/lao/stats/lottery-years20.php).

---

## Features

- **Live data** — scrapes real draw results and stores them in a local SQLite database
- **Frequency heatmap** — 10×10 grid showing how often each 2-digit number (00–99) has appeared
- **Hot / Cold numbers** — displayed as lottery balls with rankings
- **Gap & overdue analysis** — which numbers are long overdue
- **AI predictions** — ensemble of Random Forest, Logistic Regression, and Markov Chain models
- **Trend charts** — rolling frequency, day-of-week patterns, monthly heatmap, digit split
- **Modern dark UI** — mobile-responsive design

> **Disclaimer:** Lottery draws are random events. All predictions are statistical patterns only — not guarantees. For entertainment use only.

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/K-Tony-cloud/AI-HQ.git
cd AI-HQ/PROJECTS/LAO-LOTTO-AI

pip3 install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

### 3. Fetch real data

On first launch, go to **⚙️ Settings → Fetch Latest Results** to download draw history from lotto.thaiorc.com. This takes about 5–10 seconds.

---

## Project Structure

```
LAO-LOTTO-AI/
├── app.py                    # Home dashboard (entry point)
├── requirements.txt
├── .streamlit/
│   └── config.toml           # Dark theme
├── db/
│   └── lao_lotto.db          # SQLite database (auto-created, gitignored)
├── src/
│   ├── database.py           # SQLite layer — init, load, upsert, meta
│   ├── scraper.py            # Fetches data from lotto.thaiorc.com
│   ├── analytics.py          # All analysis functions
│   ├── predictor.py          # ML prediction models
│   └── ui_components.py      # Shared CSS and Streamlit components
└── pages/
    ├── 1_📊_Analysis.py      # Heatmap, hot/cold, frequency, gap, overdue, pairs
    ├── 2_🎯_Predictions.py   # Ensemble predictions with model breakdown
    ├── 3_📈_Trends.py        # Rolling frequency, DOW, monthly, digit split
    └── 4_⚙️_Settings.py     # Scraper controls, DB status, CSV export
```

---

## Pages

| Page | Description |
|------|-------------|
| 🏠 **Home** | Latest draw, key stats, top-7 AI picks, last 10 draws |
| 📊 **Analysis** | Frequency heatmap · Hot/Cold balls · Gap analysis · Overdue · Pairs |
| 🎯 **Predictions** | Ensemble model + Random Forest · Logistic Regression · Markov Chain |
| 📈 **Trends** | Rolling frequency · Day-of-week · Monthly heatmap · Digit split · Timeline |
| ⚙️ **Settings** | Fetch latest / full refresh · DB status · CSV export · Clear database |

---

## Data

- **Source:** [lotto.thaiorc.com](https://lotto.thaiorc.com/lao/stats/lottery-years20.php) — 20 years of Lao National Lottery results
- **Date system:** Buddhist Era (BE) dates are automatically converted to Gregorian (CE)
- **Storage:** Local SQLite database at `db/lao_lotto.db`
- **Columns:** `draw_date`, `draw_date_be`, `six_digit`, `last_3`, `last_2`

### Updating data

| Action | When to use |
|--------|-------------|
| **Fetch Latest** | Daily / whenever you open the app — fast, only fetches new draws |
| **Full Refresh** | First setup or to repair missing gaps — downloads all available pages |

The app automatically shows a warning banner when data hasn't been refreshed in 20+ hours.

---

## Prediction Models

All models operate on the sequence of past 2-digit results and use a configurable **lookback window** (default: 5 draws).

| Model | How it works |
|-------|-------------|
| **Random Forest** | Learns patterns from sequences of past results |
| **Logistic Regression** | Linear probability model on the recent draw sequence |
| **Markov Chain** | Probability based on historical transition frequencies |
| **Ensemble** | Weighted combination (RF 40% · LR 30% · Markov 30%) |

---

## Requirements

- Python 3.12+
- See `requirements.txt` for all dependencies

Key packages: `streamlit` · `pandas` · `numpy` · `plotly` · `scikit-learn` · `beautifulsoup4` · `lxml`

---

## Development

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run locally
streamlit run app.py

# Run on a specific port
streamlit run app.py --server.port 8502
```

The SQLite database and raw data files are gitignored — each environment fetches its own copy via the Settings page.
