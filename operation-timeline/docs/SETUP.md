# Phase 4 Setup — Connect to Google Sheets

Complete step-by-step guide to take Operation Timeline from mock mode to a live Google Sheets backend.

---

## Prerequisites

- A Google account
- Node.js + npm installed (already working if you ran the dev server)
- The project running locally (`npm run dev`)

---

## Step 1 — Create the Google Spreadsheet

1. Go to [sheets.google.com](https://sheets.google.com) and click **+** to create a blank spreadsheet
2. Name it: **Operation Timeline**
3. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/  ← THIS PART →  /edit
   ```
   Example: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`

---

## Step 2 — Open Apps Script

1. In the spreadsheet, click **Extensions → Apps Script**
2. A new tab opens with a default `Code.gs` file — delete its contents

---

## Step 3 — Copy the .gs Files

Copy each file from `apps-script/` into Apps Script:

| Click "+" (Add File) | File name | Copy from |
|----------------------|-----------|-----------|
| Script               | Schema    | `apps-script/Schema.gs` |
| Script               | Events    | `apps-script/Events.gs` |
| Script               | EventLogs | `apps-script/EventLogs.gs` |
| Script               | Users     | `apps-script/Users.gs` |
| Script               | SeedData  | `apps-script/SeedData.gs` |
| Script               | Code      | `apps-script/Code.gs` (replace existing) |

> **Tip:** The file name in Apps Script doesn't need the `.gs` extension — just type `Schema`, `Events`, etc.

---

## Step 4 — Set the Spreadsheet ID

1. In Apps Script, click **Project Settings** (gear icon, left sidebar)
2. Scroll to **Script Properties**
3. Click **Add script property**
4. Property: `SPREADSHEET_ID` | Value: *(paste your ID from Step 1)*
5. Click **Save script properties**

---

## Step 5 — Initialize the Schema

1. In the Apps Script editor, select function **`initSchema`** from the dropdown (top toolbar)
2. Click **Run**
3. First run will ask for permissions — click **Review permissions → Allow**
4. Check the Spreadsheet: you should see 4 new sheets: `events`, `event_logs`, `operation_meta`, `users` — each with a bold header row

---

## Step 6 — Seed the Data

1. Select function **`seedAll`** from the dropdown
2. Click **Run**
3. Check the Spreadsheet — `events` sheet should have 22 rows of data, `event_logs` should have 14 rows

---

## Step 7 — Deploy as Web App

1. Click **Deploy → New deployment**
2. Click the gear icon next to "Select type" → choose **Web app**
3. Set:
   - **Description:** Operation Timeline API v1
   - **Execute as:** Me
   - **Who has access:** Anyone
4. Click **Deploy**
5. Copy the **Web app URL** (ends with `/exec`)

> Keep this URL private — anyone with it can read and modify your Sheet.

---

## Step 8 — Configure the Frontend

Create `.env.local` in the project root (next to `package.json`):

```bash
# In your terminal:
cp .env.example .env.local
```

Then edit `.env.local`:

```env
VITE_API_MODE=live
VITE_SHEETS_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
VITE_SHEETS_ID=YOUR_SPREADSHEET_ID
VITE_POLL_INTERVAL=30000
```

---

## Step 9 — Test It

```bash
npm run dev
```

The footer should now show **LIVE** (green) instead of **MOCK** (amber).

Click the **MOCK/LIVE** badge in the top-right to open the Connection Panel, then click **ทดสอบการเชื่อมต่อ** — you should see:
```
✓ เชื่อมต่อสำเร็จ
events: 22
logs: 14
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Still shows MOCK after restart | `.env.local` not saved or wrong variable name | Check `VITE_API_MODE=live` (no spaces) |
| `VITE_SHEETS_URL is not configured` | URL not set in `.env.local` | Paste the `/exec` URL |
| `API error: 302` | Apps Script not deployed publicly | Re-deploy: Who has access → **Anyone** |
| `Sheets GET error` | Wrong action or missing sheet | Run `initSchema()` again in Apps Script |
| Empty events list | seedAll() not run | Run `seedAll()` in Apps Script |
| `Script timeout` | Too many rows, Apps Script 6-min limit | Add pagination (not needed for <500 events) |

---

## Updating Data

After going live, all edits made via the dashboard (Edit Event, Add Event) write directly to Google Sheets. You can also edit the Sheet directly — changes will appear in the dashboard within the polling interval (default: 30 seconds).

---

## Re-seeding

If you want to reset to the original 22 events, run `seedAll()` in Apps Script again. **This clears all existing data in `events` and `event_logs`.**

---

## Deploying a New Version of the API

If you update any `.gs` files:

1. Copy the updated file content into Apps Script
2. Click **Deploy → Manage deployments**
3. Click the pencil icon on your existing deployment
4. Change **Version** to **New version**
5. Click **Deploy**

> The URL stays the same — no need to update `.env.local`.
