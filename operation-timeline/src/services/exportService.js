export const exportEventsCSV = (events, meta) => {
  const headers = [
    'ID', 'วันที่', 'เวลาที่วางแผน', 'เวลาจริง', 'สิ้นสุด',
    'ชื่อเหตุการณ์', 'สถานะ', 'ประเภท', 'ความสำคัญ',
    'ผู้รายงาน', 'สถานที่', 'ระยะเวลา(นาที)', 'รายละเอียด',
  ]
  const rows = events.map(e => [
    e.id,
    e.date,
    e.planned_time,
    e.actual_time ?? '',
    e.end_time ?? '',
    e.title,
    e.status,
    e.type,
    e.priority,
    e.reporter ?? '',
    e.location ?? '',
    e.duration ?? '',
    (e.detail ?? '').replace(/,/g, '；'),
  ])
  const csv = [headers, ...rows]
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
