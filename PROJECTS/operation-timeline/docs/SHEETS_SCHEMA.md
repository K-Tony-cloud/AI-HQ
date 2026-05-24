# Google Sheets Schema

This document defines the Google Sheets structure used as the backend for Operation Timeline.

Run `initSchema()` in Apps Script once to auto-create all sheets with correct headers.

---

## Sheet: `events`

| Column | Header | Type | Notes |
|--------|--------|------|-------|
| A | id | string | EVT-xxx (auto-generated) |
| B | date | string | YYYY-MM-DD |
| C | planned_time | string | HH:MM |
| D | actual_time | string\|null | HH:MM |
| E | end_time | string\|null | HH:MM |
| F | title | string | |
| G | status | enum | upcoming · active · completed · resolved |
| H | type | enum | briefing · security · movement · ceremony · logistics · emergency |
| I | detail | string | Long-form description |
| J | reporter | string | e.g. MAJ. PRASONG |
| K | location | string | Venue name |
| L | duration | number | Minutes |
| M | priority | enum | normal · high · critical |
| N | created_at | ISO string | Auto-set on creation |
| O | updated_at | ISO string | Auto-updated on each write |

---

## Sheet: `event_logs`

| Column | Header | Type | Notes |
|--------|--------|------|-------|
| A | id | string | LOG-xxx (auto-generated) |
| B | event_id | string | FK → events.id |
| C | time | string | HH:MM — time of the log entry |
| D | message | string | Log message body |
| E | user | string | Reporter name |
| F | type | enum | alert · update · resolved · info · completed |
| G | created_at | ISO string | Auto-set on creation |

---

## Sheet: `operation_meta`

Single data row (row 2) with one record per operation.

| Column | Header | Type | Notes |
|--------|--------|------|-------|
| A | id | string | OP-YYYY-MMDD |
| B | name | string | Operation name |
| C | date | string | YYYY-MM-DD |
| D | classification | string | e.g. RESTRICTED |
| E | commander | string | e.g. COL. WICHAI SUWAN |
| F | start_time | string | HH:MM |
| G | end_time | string | HH:MM |
| H | venue | string | City/area name |
| I | status | string | ACTIVE · STANDBY · CLOSED |
| J | updated_at | ISO string | |

---

## Sheet: `users`

Future — for role-based access (admin vs viewer).

| Column | Header | Type | Notes |
|--------|--------|------|-------|
| A | id | string | USR-xxx |
| B | name | string | Display name |
| C | role | enum | admin · viewer |
| D | email | string | |
| E | pin_hash | string | Simple PIN or hashed |
| F | created_at | ISO string | |

---

## Apps Script Deployment

1. Open [script.google.com](https://script.google.com) and create a new project
2. Copy all `.gs` files from `apps-script/` into the project
3. Set script property `SPREADSHEET_ID` → your spreadsheet's ID
4. Run `initSchema()` once to create headers
5. **Deploy → New deployment → Web App**
   - Execute as: **Me**
   - Who has access: **Anyone**
6. Copy the deployment URL → paste into `.env.local` as `VITE_SHEETS_URL`
7. Set `VITE_API_MODE=live` in `.env.local`
