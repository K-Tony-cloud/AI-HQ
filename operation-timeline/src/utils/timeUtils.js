export const DAY_START_HOUR = 9
export const DAY_END_HOUR = 20
export const DAY_TOTAL_MINUTES = (DAY_END_HOUR - DAY_START_HOUR) * 60

export const parseTimeString = (timeStr) => {
  if (!timeStr) return null
  const [hours, minutes] = timeStr.split(':').map(Number)
  return hours * 60 + minutes
}

export const minutesToTimeString = (totalMinutes) => {
  const h = Math.floor(totalMinutes / 60)
  const m = totalMinutes % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export const getMinutesFromDayStart = (timeStr) => {
  const totalMinutes = parseTimeString(timeStr)
  return totalMinutes - DAY_START_HOUR * 60
}

export const getTimelinePercent = (timeStr) => {
  const minutesFromStart = getMinutesFromDayStart(timeStr)
  return Math.max(0, Math.min(100, (minutesFromStart / DAY_TOTAL_MINUTES) * 100))
}

export const getCurrentTimeString = () => {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

export const getCurrentTimePercent = () => {
  const now = new Date()
  const currentMinutes = now.getHours() * 60 + now.getMinutes()
  const minutesFromStart = currentMinutes - DAY_START_HOUR * 60
  return Math.max(0, Math.min(100, (minutesFromStart / DAY_TOTAL_MINUTES) * 100))
}

export const isTimeInRange = (timeStr, start, end) => {
  const t = parseTimeString(timeStr)
  const s = parseTimeString(start)
  const e = parseTimeString(end)
  return t >= s && t <= e
}

export const getEventState = (event, currentTimeStr) => {
  const current = parseTimeString(currentTimeStr)
  const planned = parseTimeString(event.planned_time)
  const endTime = event.end_time ? parseTimeString(event.end_time) : planned + (event.duration || 30)

  if (event.status === 'completed' || event.status === 'resolved') return 'past'
  if (event.status === 'active') return 'active'
  if (current >= endTime) return 'past'
  if (current >= planned) return 'active'

  const minutesUntilStart = planned - current
  if (minutesUntilStart <= 30) return 'upcoming-near'
  return 'upcoming'
}

export const formatTimeDisplay = (timeStr) => {
  if (!timeStr) return '--:--'
  return timeStr
}

export const getHourMarkers = () => {
  const markers = []
  for (let h = DAY_START_HOUR; h <= DAY_END_HOUR; h++) {
    const timeStr = `${String(h).padStart(2, '0')}:00`
    markers.push({
      time: timeStr,
      label: timeStr,
      percent: getTimelinePercent(timeStr),
    })
  }
  return markers
}
