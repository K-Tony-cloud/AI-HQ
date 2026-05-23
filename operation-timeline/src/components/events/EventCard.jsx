import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import { StatusBadge } from '../ui/StatusBadge'
import { TypeIcon } from '../ui/TypeIcon'
import { EventLogs } from './EventLogs'
import { EditEventModal } from '../admin/EditEventModal'
import { getTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

/* ── Helpers ─────────────────────────────────────────────────── */
const toMin = t => parseInt(t.split(':')[0]) * 60 + parseInt(t.split(':')[1])

const DelayBadge = ({ planned, actual }) => {
  if (!actual || planned === actual) return null
  const diff = toMin(actual) - toMin(planned)
  if (diff === 0) return null
  const color = diff > 5 ? 'text-ops-danger bg-ops-danger-light'
              : diff > 0 ? 'text-ops-warning bg-ops-warning-light'
              : 'text-ops-success bg-ops-success-light'
  return (
    <span className={clsx('font-mono text-[9px] font-bold px-1 py-0.5 rounded', color)}>
      {diff > 0 ? '+' : ''}{diff}น.
    </span>
  )
}

const TimeStamp = ({ planned, actual, state }) => (
  <span className={clsx(
    'font-mono font-bold tabular-nums leading-none flex-shrink-0',
    state === 'active'   ? 'text-ops-accent text-[13px]' :
    state === 'past'     ? 'text-ops-text-disabled text-xs' :
    'text-ops-text-secondary text-xs',
  )}>
    {actual || planned}
  </span>
)

/* ── COMPACT — past / future ─────────────────────────────────── */
export const EventCardCompact = ({ event, state, onClick, dense }) => {
  const typeConfig = getTypeConfig(event.type)
  const isPast = state === 'past'

  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left flex items-center gap-2.5 rounded-lg border transition-all duration-150 group',
        dense ? 'py-1 px-2.5' : 'py-1.5 px-3',
        typeConfig.cardClass,
        isPast
          ? 'opacity-45 hover:opacity-80 border-transparent hover:border-ops-border/40 hover:bg-white'
          : 'border-transparent hover:border-ops-border hover:bg-white hover:shadow-card',
      )}
    >
      <TimeStamp planned={event.planned_time} actual={event.actual_time} state={state} />
      <span className={clsx('flex-shrink-0 leading-none', dense ? 'text-sm' : 'text-base')}>
        {typeConfig.icon}
      </span>
      <span className={clsx(
        'flex-1 min-w-0 truncate font-medium transition-colors',
        dense ? 'text-xs' : 'text-[13px]',
        isPast ? 'text-ops-text-muted' : 'text-ops-text-secondary group-hover:text-ops-text-primary',
      )}>
        {event.title}
      </span>
      <StatusBadge status={event.status} size="xs" showIcon={false} />
    </button>
  )
}

/* ── SEMI-EXPANDED — upcoming-near ───────────────────────────── */
export const EventCardSemiExpanded = ({ event, onClick }) => {
  const typeConfig = getTypeConfig(event.type)

  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left rounded-xl border shadow-card transition-all duration-200 group',
        'hover:shadow-card-md hover:border-ops-border-focus',
        typeConfig.cardClass,
        'near-pulse',
        'p-3',
      )}
    >
      <div className="flex items-start gap-2.5">
        <span className="text-lg flex-shrink-0 mt-0.5">{typeConfig.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h3 className="font-semibold text-[13px] text-ops-text-primary truncate leading-tight">
              {event.title}
            </h3>
            <StatusBadge status={event.status} size="xs" showIcon={false} />
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="font-mono text-xs font-bold text-ops-warning tabular-nums">
              {event.planned_time}
            </span>
            <TypeIcon type={event.type} size="sm" showLabel />
            {event.location && (
              <span className="text-[11px] text-ops-text-muted truncate max-w-[180px]">
                📍 {event.location}
              </span>
            )}
          </div>
        </div>
        <span className="text-ops-text-muted/40 text-xs flex-shrink-0 group-hover:text-ops-text-muted transition-colors mt-1">↓</span>
      </div>
    </button>
  )
}

/* ── FULL EXPANDED — active or manually opened ───────────────── */
export const EventCardExpanded = ({ event, state, onCollapse, dense }) => {
  const { isAdminMode, densityMode } = useApp()
  const [showEdit, setShowEdit] = useState(false)
  const typeConfig = getTypeConfig(event.type)
  const isActive = state === 'active'
  const isEmergency = event.type === 'emergency'

  return (
    <>
    <div className={clsx(
      'rounded-xl border overflow-hidden transition-all duration-300 animate-expand relative',
      dense ? 'p-3' : 'p-4',
      isActive
        ? 'bg-sky-50 border-sky-300 shadow-card-active'
        : isEmergency
          ? 'bg-red-50/70 border-red-200 shadow-card'
          : `${typeConfig.cardClass} border-ops-border shadow-card`,
    )}>

      {/* Active left accent bar */}
      {isActive && (
        <div
          className="absolute left-0 top-0 bottom-0 w-[3px] bg-ops-accent rounded-r-full"
          style={{ boxShadow: '2px 0 10px rgba(14,165,233,0.45)' }}
        />
      )}

      {/* Header */}
      <div className={clsx('flex items-start gap-3', dense ? 'mb-2' : 'mb-3')}>
        <span className={clsx('flex-shrink-0', dense ? 'text-lg' : 'text-xl', 'mt-0.5')}>
          {typeConfig.icon}
        </span>
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <h3 className={clsx(
              'font-bold leading-tight',
              dense ? 'text-[13px]' : 'text-sm',
              isActive    ? 'text-ops-accent' :
              isEmergency ? 'text-ops-danger'  : 'text-ops-text-primary',
            )}>
              {event.title}
            </h3>
            {isActive && (
              <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-ops-accent bg-sky-100 border border-ops-accent/30 px-2 py-0.5 rounded-full shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-ops-accent animate-blink" />
                กำลังดำเนินการ
              </span>
            )}
          </div>
          {/* Type + status badges */}
          <div className="flex flex-wrap items-center gap-1.5">
            <TypeIcon type={event.type} size="sm" showLabel />
            <StatusBadge status={event.status} size="xs" />
            {event.priority === 'critical' && (
              <span className="text-[9px] font-bold text-ops-danger bg-ops-danger-light border border-ops-danger/25 px-1.5 py-0.5 rounded tracking-wide">
                วิกฤต
              </span>
            )}
          </div>
        </div>
        {/* Collapse button (non-active cards only) */}
        {!isActive && (
          <button
            onClick={onCollapse}
            className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-ops-text-muted hover:text-ops-text-primary hover:bg-slate-100 transition-all"
          >
            <span className="text-xs">↑</span>
          </button>
        )}
      </div>

      {/* Time strip */}
      <div className={clsx(
        'flex flex-wrap gap-x-5 gap-y-1 rounded-lg border bg-white/60',
        dense ? 'p-2 mb-2' : 'p-2.5 mb-3',
        'border-ops-border/60',
      )}>
        {[
          { label: 'แผนเวลา', val: event.planned_time, mono: true },
          event.actual_time && { label: 'เวลาจริง', val: event.actual_time, mono: true,
            extra: <DelayBadge planned={event.planned_time} actual={event.actual_time} /> },
          event.end_time  && { label: 'สิ้นสุด',  val: event.end_time,    mono: true },
          event.duration  && { label: 'ระยะเวลา',  val: `${event.duration} น.`, mono: false },
        ].filter(Boolean).map((item, i) => (
          <div key={i}>
            <p className="ops-label mb-0.5">{item.label}</p>
            <div className="flex items-baseline gap-1">
              <p className={clsx('font-semibold text-sm tabular-nums text-ops-text-primary', item.mono && 'font-mono')}>
                {item.val}
              </p>
              {item.extra}
            </div>
          </div>
        ))}
      </div>

      {/* Location */}
      {event.location && (
        <div className={clsx('flex items-center gap-1.5 text-xs text-ops-text-secondary', dense ? 'mb-2' : 'mb-3')}>
          <span>📍</span>
          <span className="truncate">{event.location}</span>
        </div>
      )}

      {/* Detail text */}
      {(!dense || isActive) && (
        <p className={clsx('text-ops-text-secondary leading-relaxed', dense ? 'text-xs mb-2' : 'text-sm mb-3')}>
          {event.detail}
        </p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-ops-border/50">
        <span className="text-[11px] text-ops-text-muted">
          <span className="font-semibold text-ops-text-secondary">{event.reporter}</span>
        </span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-ops-text-disabled">{event.id}</span>
          {isAdminMode && (
            <button
              onClick={() => setShowEdit(true)}
              className="text-[10px] font-semibold text-ops-warning bg-ops-warning-light border border-ops-warning/25 hover:bg-amber-100 px-2 py-0.5 rounded-md transition-all"
            >
              แก้ไข
            </button>
          )}
        </div>
      </div>

      {/* Logs */}
      {densityMode !== 'compact' && <EventLogs eventId={event.id} />}
    </div>

    {showEdit && <EditEventModal event={event} onClose={() => setShowEdit(false)} />}
    </>
  )
}

/* ── SMART WRAPPER ───────────────────────────────────────────── */
export const EventCard = ({ event, state }) => {
  const { toggleEventExpand, isEventExpanded, densityMode } = useApp()
  const expanded = isEventExpanded(event.id)
  const isActive = state === 'active'
  const isNear   = state === 'upcoming-near'
  const dense    = densityMode === 'compact'

  if (isActive || expanded) {
    return (
      <EventCardExpanded
        event={event} state={state} dense={dense}
        onCollapse={() => { if (!isActive) toggleEventExpand(event.id) }}
      />
    )
  }
  // Semi-expand upcoming-near events in normal mode
  if (isNear && !dense) {
    return <EventCardSemiExpanded event={event} onClick={() => toggleEventExpand(event.id)} />
  }
  return (
    <EventCardCompact
      event={event} state={state} dense={dense}
      onClick={() => toggleEventExpand(event.id)}
    />
  )
}
