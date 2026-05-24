const REQUIRED_COLUMNS = ['planned_time', 'title']

const VALID_STATUSES  = ['upcoming', 'active', 'completed', 'delayed', 'cancelled']
const VALID_TYPES     = ['briefing', 'tactical', 'logistics', 'media', 'movement', 'coordination', 'other']
const VALID_PRIORITIES = ['low', 'normal', 'high', 'critical']

const TIME_RE   = /^\d{2}:\d{2}$/
const DATE_RE   = /^\d{4}-\d{2}-\d{2}$/

/* ── CSV text → array of row objects ──────────────────────────── */
export function parseCSV(text) {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split('\n')
  if (lines.length < 2) return { headers: [], rows: [] }

  const headers = parseLine(lines[0]).map(h => h.trim().toLowerCase())
  const rows = lines.slice(1)
    .filter(l => l.trim().length > 0)
    .map((line, i) => {
      const values = parseLine(line)
      const obj = {}
      headers.forEach((h, j) => { obj[h] = (values[j] ?? '').trim() })
      obj._rowIndex = i + 2
      return obj
    })

  return { headers, rows }
}

function parseLine(line) {
  const fields = []
  let cur = ''
  let inQuotes = false

  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { cur += '"'; i++ }
      else inQuotes = !inQuotes
    } else if (ch === ',' && !inQuotes) {
      fields.push(cur); cur = ''
    } else {
      cur += ch
    }
  }
  fields.push(cur)
  return fields
}

/* ── Validate parsed rows ─────────────────────────────────────── */
export function validateCSV(headers, rows) {
  const errors = []

  // Check required columns exist
  const missingCols = REQUIRED_COLUMNS.filter(c => !headers.includes(c))
  if (missingCols.length > 0) {
    errors.push({ type: 'schema', message: `Missing required columns: ${missingCols.join(', ')}` })
    return { valid: false, errors, rowErrors: {} }
  }

  const rowErrors = {}

  rows.forEach(row => {
    const rowIdx = row._rowIndex
    const errs   = []

    if (!row.title?.trim()) {
      errs.push('title is required')
    }
    if (!row.planned_time?.trim()) {
      errs.push('planned_time is required')
    } else if (!TIME_RE.test(row.planned_time.trim())) {
      errs.push(`planned_time "${row.planned_time}" must be HH:MM (24h)`)
    }
    if (row.actual_time?.trim() && !TIME_RE.test(row.actual_time.trim())) {
      errs.push(`actual_time "${row.actual_time}" must be HH:MM (24h)`)
    }
    if (row.end_time?.trim() && !TIME_RE.test(row.end_time.trim())) {
      errs.push(`end_time "${row.end_time}" must be HH:MM (24h)`)
    }
    if (row.date?.trim() && !DATE_RE.test(row.date.trim())) {
      errs.push(`date "${row.date}" must be YYYY-MM-DD`)
    }
    if (row.status?.trim() && !VALID_STATUSES.includes(row.status.trim())) {
      errs.push(`status "${row.status}" must be one of: ${VALID_STATUSES.join(', ')}`)
    }
    if (row.type?.trim() && !VALID_TYPES.includes(row.type.trim())) {
      errs.push(`type "${row.type}" must be one of: ${VALID_TYPES.join(', ')}`)
    }
    if (row.priority?.trim() && !VALID_PRIORITIES.includes(row.priority.trim())) {
      errs.push(`priority "${row.priority}" must be one of: ${VALID_PRIORITIES.join(', ')}`)
    }
    if (row.duration?.trim() && isNaN(Number(row.duration))) {
      errs.push(`duration "${row.duration}" must be a number`)
    }

    if (errs.length > 0) rowErrors[rowIdx] = errs
  })

  const valid = errors.length === 0 && Object.keys(rowErrors).length === 0
  return { valid, errors, rowErrors }
}

/* ── Build event payloads for import (no IDs — generated server-side) */
export function buildEventPayloads(rows, defaultDate) {
  return rows
    .map(row => ({
      date:         row.date?.trim()         || defaultDate || '',
      planned_time: row.planned_time?.trim() || '',
      actual_time:  row.actual_time?.trim()  || '',
      end_time:     row.end_time?.trim()     || '',
      title:        row.title?.trim()        || '',
      status:       row.status?.trim()       || 'upcoming',
      type:         row.type?.trim()         || 'briefing',
      priority:     row.priority?.trim()     || 'normal',
      reporter:     row.reporter?.trim()     || '',
      location:     row.location?.trim()     || '',
      duration:     row.duration?.trim()     ? Number(row.duration) : 30,
      detail:       row.detail?.trim()       || '',
    }))
    .sort((a, b) => a.planned_time.localeCompare(b.planned_time))
}
