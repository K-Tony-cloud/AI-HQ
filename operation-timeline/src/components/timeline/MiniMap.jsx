import { useState, useEffect } from 'react'
import { useCurrentTime } from '../../hooks/useCurrentTime'
import { DAY_START_HOUR, DAY_END_HOUR, parseTimeString } from '../../utils/timeUtils'
import { getTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

const DAY_MINS = (DAY_END_HOUR - DAY_START_HOUR) * 60
const toPct = (timeStr) => {
  const t = parseTimeString(timeStr) - DAY_START_HOUR * 60
  return Math.max(0, Math.min(100, (t / DAY_MINS) * 100))
}

export const MiniMap = ({ events, containerRef, ppm }) => {
  const { percent } = useCurrentTime(5000)
  const [viewport, setViewport] = useState({ top: 0, height: 0.3 })

  useEffect(() => {
    const container = containerRef?.current
    if (!container) return

    const update = () => {
      const { scrollTop, clientHeight, scrollHeight } = container
      if (scrollHeight <= 0) return
      setViewport({
        top: scrollTop / scrollHeight,
        height: Math.min(1, clientHeight / scrollHeight),
      })
    }

    update()
    container.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update, { passive: true })
    return () => {
      container.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [containerRef])

  const scrollTo = (eventId) => {
    const el = document.getElementById(`event-${eventId}`)
    if (!el || !containerRef?.current) return
    const c      = containerRef.current
    const offset = el.offsetTop - c.clientHeight / 2 + 60
    c.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' })
  }

  return (
    <div className="flex flex-col h-full">
      <p className="text-[8px] font-mono font-bold tracking-widest uppercase text-ops-text-muted text-center mb-2 flex-shrink-0">
        แผนที่
      </p>

      {/* Mini spine */}
      <div className="flex-1 relative mx-auto w-6 min-h-0">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-ops-border -translate-x-1/2" />

        {/* Viewport indicator */}
        <div
          className="absolute left-0 right-0 rounded pointer-events-none transition-all duration-75"
          style={{
            top: `${viewport.top * 100}%`,
            height: `${viewport.height * 100}%`,
            background: 'rgba(14,165,233,0.07)',
            borderTop: '1px solid rgba(14,165,233,0.25)',
            borderBottom: '1px solid rgba(14,165,233,0.25)',
          }}
        />

        {/* Hour ticks */}
        {Array.from({ length: 12 }, (_, i) => (
          <div key={i} className="absolute left-0 right-0 flex justify-center" style={{ top: `${(i / 11) * 100}%` }}>
            <div className="w-2.5 h-px bg-ops-border/50" />
          </div>
        ))}

        {/* Event dots */}
        {events.map(event => {
          const pos    = toPct(event.planned_time)
          const cfg    = getTypeConfig(event.type)
          const isAct  = event.status === 'active'
          const isDone = event.status === 'completed' || event.status === 'resolved'

          return (
            <button
              key={event.id}
              onClick={() => scrollTo(event.id)}
              title={`${event.planned_time} — ${event.title}`}
              className="absolute left-1/2 -translate-x-1/2 group"
              style={{ top: `${pos}%` }}
            >
              <div
                className={clsx(
                  'rounded-full transition-all duration-200 group-hover:scale-150 -translate-y-1/2',
                  isAct ? 'w-3 h-3' : 'w-2 h-2',
                )}
                style={{
                  backgroundColor: cfg.nodeColor,
                  opacity: isDone ? 0.3 : 1,
                  boxShadow: isAct ? `0 0 6px ${cfg.nodeColor}80` : undefined,
                }}
              />
              {isAct && (
                <div
                  className="absolute inset-0 rounded-full node-ring -translate-y-1/2"
                  style={{ backgroundColor: cfg.nodeColor, opacity: 0.2 }}
                />
              )}
            </button>
          )
        })}

        {/* NOW tick */}
        {percent > 0 && percent < 100 && (
          <div className="absolute left-0 right-0 pointer-events-none" style={{ top: `${percent}%` }}>
            <div className="w-full h-[1.5px] bg-ops-now now-line-animated opacity-80 rounded-full" />
          </div>
        )}
      </div>

      {/* Time labels */}
      <div className="flex justify-between mt-1.5 flex-shrink-0 px-0.5">
        <span className="font-mono text-[8px] text-ops-text-disabled">09</span>
        <span className="font-mono text-[8px] text-ops-text-disabled">20</span>
      </div>

      <div className="my-2.5 h-px bg-ops-border/50 flex-shrink-0" />

      {/* Legend */}
      <div className="space-y-1.5 flex-shrink-0">
        {[
          { c: '#2dd4bf', l: 'ประชุม' },
          { c: '#f87171', l: 'ปลอดภัย' },
          { c: '#60a5fa', l: 'เดินทาง' },
          { c: '#fbbf24', l: 'พิธีการ' },
          { c: '#fb923c', l: 'สนับสนุน' },
          { c: '#ef4444', l: 'ฉุกเฉิน' },
        ].map(({ c, l }) => (
          <div key={l} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: c }} />
            <span className="text-[8px] text-ops-text-muted leading-none">{l}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
