# PROJECTS

Index of all active projects in AI-HQ.

---

## LAO-LOTTO-AI

Statistical analysis and AI-powered predictions for the Lao National Lottery (ສະຫວັນເດດ).

| | |
|---|---|
| **Status** | Active — local |
| **Stack** | Python 3.12, Streamlit, SQLite, scikit-learn, Plotly, BeautifulSoup |
| **Data source** | [lotto.thaiorc.com](https://lotto.thaiorc.com/lao/stats/lottery-years20.php) |
| **Entry point** | `app.py` |
| **Run** | `streamlit run app.py` |
| **Database** | `db/lao_lotto.db` (SQLite, gitignored — fetch via Settings page) |

---

## operation-timeline

Event timeline and operations management tool. React frontend backed by Google Sheets + Google Drive via Apps Script.

| | |
|---|---|
| **Status** | Active — local + GAS deployed |
| **Stack** | React (Vite), Google Apps Script, Google Sheets, Google Drive |
| **Entry point** | `src/main.jsx` |
| **Backend** | `apps-script/Code.gs` (deployed as GAS Web App) |
| **Run** | `npm run dev` |
| **Features** | Event cards, file/image attachments, CSV import/export, Drive subfolders |

---

## line-reminder

LINE Messaging bot that sends event reminders via natural language commands (Thai + English).

| | |
|---|---|
| **Status** | Active — production |
| **Stack** | Python, FastAPI, APScheduler, LINE SDK, Google Sheets |
| **Deployment** | Railway (`railway.json`) |
| **Git** | [K-Tony-cloud/line-reminder](https://github.com/K-Tony-cloud/line-reminder) |
| **Entry point** | `run.py` |
| **Backups** | `backups/` (gitignored, local only) |

---

## Police Station Visitor System (RW01)

Visitor and service record management system for a police station.
Two repos make up one system: GAS handles the backend API, GitHub Pages serves the frontend.

### SheetAppScriptRW01 — backend

| | |
|---|---|
| **Status** | Active — production |
| **Stack** | Google Apps Script, Google Sheets |
| **Deployment** | GAS Web App (clasp) |
| **Git** | [K-Tony-cloud/SheetAppScriptRW01](https://github.com/K-Tony-cloud/SheetAppScriptRW01) |

### rw-inv-redirect — frontend

| | |
|---|---|
| **Status** | Active — production |
| **Stack** | HTML / CSS / JavaScript (single file SPA) |
| **Deployment** | GitHub Pages |
| **Git** | [rw6-mpb/project](https://github.com/rw6-mpb/project) |
| **Live URL** | https://rw6-mpb.github.io/project |

---

## Notes

- Each project folder contains its own README with full setup and run instructions.
- Do not rename `line-reminder/` — Railway deployment depends on the local path.
- `line-reminder/backups/` is local only and not tracked in git.
- `LAO-LOTTO-AI/db/` is gitignored — each environment fetches its own data via the Settings page.
