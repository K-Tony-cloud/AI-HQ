import { useRef, useEffect, useMemo } from 'react'
import { useApp } from '../../context/AppContext'
import { useCurrentTime } from '../../hooks/useCurrentTime'
import { EventCard } from '../events/EventCard'
import { MiniMap } from './MiniMap'
import { getEventState, getHourMarkers, DAY_START_HOUR, DAY_END_HOUR, parseTimeString } from '../../utils/timeUtils'
import { getTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

// px per minute for each density mode
const PPM = { compact: 2.0, normal: 3.5 }
const DAY_MINS = (DAY_END_HOUR - DAY_START_HOUR) * 60

const toPx  = (timeStr, ppm) => (parseTimeString(timeStr) - DAY_START_HOUR * 60) * ppm
const nowPx = (ppm) => {
  const n = new Date()
  return Math.max(0, (n.getHours() * 60 + n.getMinutes() - DAY_START_HOUR * 60) * ppm)
}

/* ── Hour ruler ──────────────────────────────────────────────── */
const HourMarker = ({ time, label, ppm }) => (
  <div
    className="absolute left-0 right-0 flex items-center pointer-events-none select-none"
    style={{ top: `${toPx(time, ppm)}px` }}
  >
    <span className="font-mono text-[10px] text-ops-text-disabled w-12 text-right pr-2 flex-shrink-0 tabular-nums">
      {label}
    </span>
    <div className="flex-1 h-px bg-ops-border/40" />
  </div>
)

/* ── Timeline dot ────────────────────────────────────────────── */
const TimelineNode = ({ event, state, ppm }) => {
  const cfg    = getTypeConfig(event.type)
  const isActive = state === 'active'
  const isPast   = state === 'past'
  const nodeTop  = ppm <= 2.0 ? 9 : 14

  return (
    <div className="absolute flex items-center z-10" style={{ left: '50px', top: `${nodeTop}px` }}>
      {/* Connector */}
      <div className={clsx('h-px w-4', isActive ? 'bg-sky-300' : 'bg-ops-border')} />
      {/* Dot */}
      <div className="relative">
        <div
          className={clsx(
            'rounded-full border-2 transition-all duration-400',
            isActive ? 'w-3.5 h-3.5' : isPast ? 'w-2 h-2' : 'w-2.5 h-2.5',
          )}
          style={{
            borderColor: isActive ? cfg.nodeColor : isPast ? '#e2e8f0' : `${cfg.nodeColor}80`,
            backgroundColor: isActive ? `${cfg.nodeColor}20` : isPast ? '#f4f7fb' : '#ffffff',
            boxShadow: isActive ? `0 0 6px ${cfg.nodeColor}60` : undefined,
          }}
        />
        {isActive && (
          <div
            className="absolute inset-0 rounded-full node-ring"
            style={{ backgroundColor: cfg.nodeColor, opacity: 0.25 }}
          />
        )}
      </div>
    </div>
  )
}

/* ── NOW indicator line ──────────────────────────────────────── */
const NowLine = ({ ppm }) => {
  const py   = nowPx(ppm)
  const total = DAY_MINS * ppm
  if (py <= 4 || py >= total - 4) return null

  const n  = new Date()
  const hh = String(n.getHours()).padStart(2, '0')
  const mm = String(n.getMinutes()).padStart(2, '0')

  return (
    <div className="absolute left-0 right-0 z-20 pointer-events-none" style={{ top: `${py}px` }}>
      <div className="now-line-animated h-[1.5px] bg-ops-now relative">
        {/* Label pill */}
        <div className="absolute left-12 -top-[14px] flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-ops-now animate-blink shadow-now flex-shrink-0" />
          <span className="font-mono text-[11px] font-bold text-ops-now bg-white/95 px-2 py-0.5 rounded-full border border-ops-now/30 shadow-sm tabular-nums">
            ขณะนี้ {hh}:{mm}
          </span>
        </div>
        {/* Right arrowhead */}
        <div className="absolute right-1 top-[-3px] w-0 h-0
          border-t-[4px] border-b-[4px] border-l-[6px]
          border-t-transparent border-b-transparent border-l-ops-now/70" />
      </div>
    </div>
  )
}

/* ── Main Timeline ───────────────────────────────────────────── */
export const Timeline = () => {
  const { events, densityMode, isEventExpanded } = useApp()
  const { timeStr } = useCurrentTime(10000)
  const containerRef = useRef(null)
  const activeRef    = useRef(null)

  const ppm   = useMemo(() => PPM[densityMode] ?? PPM.normal, [densityMode])
  const hours = useMemo(() => getHourMarkers(), [])

  const sortedEvents = useMemo(
    () => [...events].sort((a, b) => a.planned_time.localeCompare(b.planned_time)),
    [events],
  )

  const eventStates = useMemo(() => {
    const map = new Map()
    sortedEvents.forEach(ev => map.set(ev.id, getEventState(ev, timeStr)))
    return map
  }, [sortedEvents, timeStr])

  // Estimated rendered heights per card state (used to push siblings down)
  const COMPACT_H  = densityMode === 'compact' ? 28 : 33
  const SEMI_H     = 72
  const EXPANDED_H = densityMode === 'compact' ? 195 : 310

  const getCardH = (event, state) => {
    if (state === 'active' || isEventExpanded(event.id)) return EXPANDED_H
    if (state === 'upcoming-near' && densityMode !== 'compact') return SEMI_H
    return COMPACT_H
  }

  // Compute y for each event; accumulate extra pixels when a card overflows its natural gap
  let cumulativeExtra = 0
  const eventsWithY = sortedEvents.map((event, i) => {
    const baseY = toPx(event.planned_time, ppm)
    const y     = baseY + cumulativeExtra
    const state = eventStates.get(event.id)

    if (i < sortedEvents.length - 1) {
      const naturalGap = toPx(sortedEvents[i + 1].planned_time, ppm) - baseY
      cumulativeExtra += Math.max(0, getCardH(event, state) - naturalGap)
    }

    return { event, y, state }
  })

  const totalH = DAY_MINS * ppm + cumulativeExtra

  // Scroll to active event when density changes or on mount
  useEffect(() => {
    if (!activeRef.current || !containerRef.current) return
    const container = containerRef.current
    const offset    = activeRef.current.offsetTop - container.clientHeight / 2 + 60
    container.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' })
  }, [densityMode])

  return (
    <div className="flex gap-3 h-full min-h-0">
      {/* ── Scrollable timeline canvas ── */}
      <div
        ref={containerRef}
        className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden"
        style={{ scrollbarWidth: 'thin' }}
      >
        <div
          className="relative"
          style={{ height: `${totalH + 72}px`, paddingTop: '18px', paddingBottom: '28px' }}
        >
          {/* Spine */}
          <div
            className="absolute top-0 bottom-0 w-px pointer-events-none"
            style={{
              left: '64px',
              background: 'linear-gradient(to bottom, transparent 0%, #e2e8f0 3%, #e2e8f0 97%, transparent 100%)',
            }}
          />

          {/* Spine accent glow near NOW */}
          <div
            className="absolute w-px pointer-events-none transition-top duration-[5s]"
            style={{
              left: '64px',
              top: `${Math.max(0, nowPx(ppm) - 50)}px`,
              height: '100px',
              background: 'linear-gradient(to bottom, transparent, rgba(14,165,233,0.2), transparent)',
            }}
          />

          {/* Hour markers */}
          {hours.map(m => <HourMarker key={m.time} time={m.time} label={m.label} ppm={ppm} />)}

          {/* NOW line */}
          <NowLine ppm={ppm} />

          {/* Event rows */}
          {eventsWithY.map(({ event, y, state }) => {
            const isActive = state === 'active'

            return (
              <div
                key={event.id}
                id={`event-${event.id}`}
                ref={isActive ? activeRef : null}
                className="absolute"
                style={{
                  top: `${y}px`,
                  left: '68px',
                  right: '2px',
                  zIndex: isActive ? 10 : 1,
                }}
              >
                <TimelineNode event={event} state={state} ppm={ppm} />
                <div className="ml-10">
                  <EventCard event={event} state={state} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Mini-map ── */}
      <div className="hidden md:flex flex-col w-14 flex-shrink-0">
        <div
          className="sticky top-0 bg-white border border-ops-border rounded-xl p-2.5 shadow-card"
          style={{ height: 'calc(100vh - 148px)' }}
        >
          <MiniMap events={sortedEvents} containerRef={containerRef} ppm={ppm} />
        </div>
      </div>
    </div>
  )
}
