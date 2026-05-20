# PROJECTS

Index of all active projects in AI-HQ.

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
| **Live API** | GAS exec endpoint (see `PROJECT_SUMMARY.md`) |

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

- Each project folder contains its own README or PROJECT_SUMMARY.md with full details.
- Do not rename `line-reminder/` — Railway deployment depends on the local path.
- `line-reminder/backups/` is local only and not tracked in git.
