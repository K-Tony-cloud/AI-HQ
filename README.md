# 🧠 AI-HQ
**KTony Team Operating System** — monorepo for all active projects, AI personas, and shared context.

---

## Active Projects

| Project | Stack | Status |
|---------|-------|--------|
| [LAO-LOTTO-AI](#lao-lotto-ai) | Python · Streamlit · SQLite | ✅ Active |
| [operation-timeline](#operation-timeline) | React · Google Apps Script · Google Sheets | ✅ Active |
| [line-reminder](#line-reminder) | Python · FastAPI · LINE SDK | ✅ Active — production |
| [SheetAppScriptRW01](#police-station-system-rw01) | Google Apps Script · Google Sheets | ✅ Active — production |
| [rw-inv-redirect](#police-station-system-rw01) | HTML / JS (SPA) · GitHub Pages | ✅ Active — production |

---

## Projects

### LAO-LOTTO-AI
Statistical analysis and AI-powered predictions for the Lao National Lottery.

| | |
|---|---|
| **Stack** | Python 3.12, Streamlit, SQLite, scikit-learn, Plotly, BeautifulSoup |
| **Data source** | [lotto.thaiorc.com](https://lotto.thaiorc.com/lao/stats/lottery-years20.php) |
| **Run** | `cd PROJECTS/LAO-LOTTO-AI && streamlit run app.py` |
| **Features** | Live scraper · Frequency heatmap · Hot/cold analysis · Ensemble predictions · Trend charts |

---

### operation-timeline
Event timeline and operations management tool backed by Google Sheets.

| | |
|---|---|
| **Stack** | React (Vite), Google Apps Script, Google Sheets, Google Drive |
| **Run** | `cd PROJECTS/operation-timeline && npm run dev` |
| **Features** | Event cards · File/image attachments · CSV import/export · Drive folder management |

---

### line-reminder
LINE Messaging bot that sends event reminders via natural language commands.

| | |
|---|---|
| **Stack** | Python, FastAPI, APScheduler, LINE Messaging SDK, Google Sheets |
| **Deployment** | Railway |
| **Languages** | Thai + English |

---

### Police Station System (RW01)
Visitor and service record management for a police station. Two repos, one system.

**Backend — SheetAppScriptRW01**

| | |
|---|---|
| **Stack** | Google Apps Script, Google Sheets |
| **Deployment** | GAS Web App (clasp) |

**Frontend — rw-inv-redirect**

| | |
|---|---|
| **Stack** | HTML / CSS / JavaScript (single-file SPA) |
| **Deployment** | GitHub Pages · https://rw6-mpb.github.io/project |

---

## Repo Structure

```
AI-HQ/
├── README.md
├── PROJECTS/
│   ├── README.md                  # Project index
│   ├── LAO-LOTTO-AI/              # Lao lottery analysis & predictions
│   ├── operation-timeline/        # Operations event timeline
│   ├── line-reminder/             # LINE reminder bot
│   ├── SheetAppScriptRW01/        # Police station backend
│   └── rw-inv-redirect/           # Police station frontend
├── PERSONAS/                      # AI team member role definitions
├── CONTEXT/                       # Shared context files
├── PROMPTS/                       # Reusable prompt templates
├── SYSTEM/                        # System-level configuration
└── ARCHIVE/                       # Inactive / retired work
```

---

## AI Team

| Name | Role |
|------|------|
| Roxi | CEO / Project Manager |
| Nova | Developer |
| Kiki | Content Creator |
| Vixi | Video / Visual |
| Cipher | QA / Critic |
| Luna | Analyst |
| Speedy | Growth / Marketing |

---

## Core Rules

- Roxi คือ Team Lead — ทุก AI มี role ชัดเจน
- ทุกโปรเจกต์ต้องมี summary / README
- ใช้เฉพาะ context ที่จำเป็น — ห้าม paste full code ถ้าไม่จำเป็น
- Each project folder contains its own README with full setup details
