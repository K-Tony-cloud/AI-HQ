const CSV_HEADERS = [
  'date', 'planned_time', 'actual_time', 'end_time',
  'title', 'type', 'status', 'priority',
  'reporter', 'location', 'duration', 'detail',
]

export const exportEventsCSV = (events, meta) => {
  const rows = events.map(e => [
    e.date,
    e.planned_time,
    e.actual_time  ?? '',
    e.end_time     ?? '',
    e.title,
    e.type,
    e.status,
    e.priority,
    e.reporter     ?? '',
    e.location     ?? '',
    e.duration     ?? '',
    (e.detail      ?? '').replace(/"/g, '""'),
  ])
  const csv = [CSV_HEADERS, ...rows]
    .map(r => r.map(v => `"${v}"`).join(','))
    .join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `operation-${meta?.date ?? 'export'}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
