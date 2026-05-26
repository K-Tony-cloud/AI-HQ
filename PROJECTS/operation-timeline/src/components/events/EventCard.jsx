import { useRef, useEffect, memo } from 'react'
import { useApp } from '../../context/AppContext'
import { useModalActions } from '../../context/ModalContext'
import { useAuth } from '../../context/AuthContext'
import { StatusBadge } from '../ui/StatusBadge'
import { TypeIcon } from '../ui/TypeIcon'
import { EventLogs } from './EventLogs'
import { EventAttachments } from './EventAttachments'
import { getTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

const toMin = t => t ? parseInt(t.split(':')[0]) * 60 + parseInt(t.split(':')[1]) : 0

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

export const EventCard = memo(
  function EventCard({ event, state }) {
    const { toggleEventExpand, isEventExpanded, densityMode, isAdminMode, editingEventId, deleteEvent } = useApp()
    const { openModal } = useModalActions()
    const { isOpAdmin, isSuperAdmin } = useAuth()
    const cardRef        = useRef(null)
    const prevExpRef     = useRef(false)

    const isActive    = state === 'active'
    const isNear      = state === 'upcoming-near'
    const isPast      = state === 'past'
    const isExpanded  = isActive || isEventExpanded(event.id)
    const dense       = densityMode === 'compact'
    const typeConfig  = getTypeConfig(event.type)
    const urgent      = state !== 'past' && (event.priority === 'critical' || event.type === 'emergency')
    const isEmergency = event.type === 'emergency'
    const isEditing   = editingEventId === event.id

    // Auto-scroll into view when user manually expands this card
    useEffect(() => {
      const justExpanded = !prevExpRef.current && isExpanded && !isActive
      prevExpRef.current = isExpanded
      if (!justExpanded || !cardRef.current) return
      const id = setTimeout(() => {
        cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }, 120)
      return () => clearTimeout(id)
    }, [isExpanded, isActive])

    const handleToggle = () => { if (!isActive) toggleEventExpand(event.id) }

    const cardBase = clsx(
      'rounded-xl border relative overflow-hidden transition-colors duration-200',
      isNear && !isExpanded && !dense && 'near-pulse',
    )

    const cardColor = isActive
      ? 'bg-sky-50 border-sky-300 shadow-card-active'
      : isExpanded && isEmergency
        ? 'bg-red-50/70 border-red-200 shadow-card'
        : isExpanded
          ? clsx(typeConfig.cardClass, 'border-ops-border shadow-card')
          : isPast
            ? 'opacity-45 border-transparent hover:opacity-75 hover:border-ops-border/30 hover:bg-white/50'
            : urgent
              ? 'border-ops-danger/20 bg-white/40 hover:bg-white hover:border-ops-border hover:shadow-card'
              : 'border-transparent hover:border-ops-border hover:bg-white hover:shadow-card'

    const urgentStyle = urgent && !isActive && !isExpanded
      ? { boxShadow: 'inset 3px 0 0 #dc2626' }
      : undefined

    return (
      <>
        <div
          ref={cardRef}
          className={clsx(cardBase, cardColor)}
          style={urgentStyle}
        >
          {/* Active left accent bar */}
          {isActive && (
            <div
              className="absolute left-0 top-0 bottom-0 w-[3px] bg-ops-accent z-10"
              style={{ boxShadow: '2px 0 10px rgba(14,165,233,0.45)' }}
            />
          )}

          {/* ── Header (always visible) ── */}
          <button
            onClick={handleToggle}
            className={clsx(
              'w-full text-left flex items-center gap-2.5 group',
              isActive && 'cursor-default',
              isExpanded
                ? dense ? 'pt-3 px-3 pb-2' : 'pt-4 px-4 pb-2'
                : dense ? 'py-1 px-2.5'    : 'py-1.5 px-3',
            )}
          >
            {/* Time */}
            <span className={clsx(
              'font-mono font-bold tabular-nums leading-none flex-shrink-0',
              isActive ? 'text-ops-accent text-[13px]' :
              isPast   ? 'text-ops-text-disabled text-xs' :
                         'text-ops-text-secondary text-xs',
            )}>
              {event.actual_time || event.planned_time}
            </span>

            {/* Urgent pulse dot (compact only) */}
            {urgent && !isExpanded && (
              <span className="w-1 h-1 rounded-full bg-ops-danger flex-shrink-0 animate-pulse" />
            )}

            {/* Type emoji */}
            <span className={clsx('flex-shrink-0 leading-none', dense ? 'text-sm' : 'text-base')}>
              {typeConfig.icon}
            </span>

            {/* Title */}
            <span className={clsx(
              'flex-1 min-w-0 font-medium leading-snug transition-colors',
              dense ? 'text-xs' : 'text-[13px]',
              isExpanded
                ? isActive
                  ? 'text-ops-accent font-bold'
                  : 'text-ops-text-primary font-semibold'
                : isPast
                  ? 'text-ops-text-muted truncate'
                  : 'text-ops-text-secondary truncate group-hover:text-ops-text-primary',
            )}>
              {event.title}
            </span>

            {/* Right badges */}
            {isEditing && (
              <span className="text-[9px] font-medium text-ops-warning bg-ops-warning-light border border-ops-warning/30 px-1.5 py-0.5 rounded flex-shrink-0">
                แก้ไขอยู่
              </span>
            )}
            {isActive && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-ops-accent bg-sky-100 border border-ops-accent/30 px-2 py-0.5 rounded-full flex-shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-ops-accent animate-blink" />
                ดำเนินการ
              </span>
            )}
            <StatusBadge status={event.status} size="xs" showIcon={false} />

            {/* Expand / collapse chevron */}
            {!isActive && (
              <span className={clsx(
                'flex-shrink-0 text-ops-text-muted/60 text-[11px] transition-transform duration-300 select-none',
                isExpanded && 'rotate-180',
              )}>
                ▾
              </span>
            )}
          </button>

          {/* ── Animated detail panel ── */}
          <div
            style={{
              display: 'grid',
              gridTemplateRows: isExpanded ? '1fr' : '0fr',
              transition: 'grid-template-rows 280ms cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            <div style={{ overflow: 'hidden' }}>
              <div className={dense ? 'px-3 pb-3' : 'px-4 pb-4'}>

                {/* Type + urgency badges */}
                <div className="flex flex-wrap items-center gap-1.5 mb-2.5">
                  <TypeIcon type={event.type} size="sm" showLabel />
                  <StatusBadge status={event.status} size="xs" />
                  {event.priority === 'critical' && (
                    <span className="text-[9px] font-bold text-ops-danger bg-ops-danger-light border border-ops-danger/25 px-1.5 py-0.5 rounded tracking-wide">
                      วิกฤต
                    </span>
                  )}
                  {urgent && isEmergency && (
                    <span className="text-[9px] font-bold text-ops-danger bg-ops-danger-light border border-ops-danger/30 px-1.5 py-0.5 rounded tracking-widest animate-pulse">
                      ฉุกเฉิน
                    </span>
                  )}
                  {isOpAdmin && event.visibility && event.visibility !== 'public' && (
                    <span className={clsx(
                      'text-[9px] font-bold px-1.5 py-0.5 rounded tracking-wide uppercase',
                      event.visibility === 'restricted' && 'text-ops-danger bg-ops-danger-light border border-ops-danger/20',
                      event.visibility === 'internal'   && 'text-ops-warning bg-ops-warning-light border border-ops-warning/20',
                    )}>
                      {event.visibility === 'restricted' && 'จำกัด'}
                      {event.visibility === 'internal'   && 'ภายใน'}
                    </span>
                  )}
                </div>

                {/* Time strip */}
                <div className={clsx(
                  'flex flex-wrap gap-x-5 gap-y-1 rounded-lg border bg-white/60 border-ops-border/60',
                  dense ? 'p-2 mb-2' : 'p-2.5 mb-3',
                )}>
                  {[
                    { label: 'แผนเวลา', val: event.planned_time, mono: true },
                    event.actual_time && {
                      label: 'เวลาจริง', val: event.actual_time, mono: true,
                      extra: <DelayBadge planned={event.planned_time} actual={event.actual_time} />,
                    },
                    event.end_time && { label: 'สิ้นสุด',  val: event.end_time,           mono: true  },
                    event.duration && { label: 'ระยะเวลา', val: `${event.duration} น.`,   mono: false },
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
                    <span>{event.location}</span>
                  </div>
                )}

                {/* Detail text */}
                {(!dense || isActive) && event.detail && (
                  <p className={clsx('text-ops-text-secondary leading-relaxed', dense ? 'text-xs mb-2' : 'text-sm mb-3')}>
                    {event.detail}
                  </p>
                )}

                {/* Logs */}
                {densityMode !== 'compact' && <EventLogs eventId={event.id} />}

                {/* Attachments */}
                {isExpanded && densityMode !== 'compact' && (
                  <EventAttachments event={event} isAdmin={isAdminMode} />
                )}

                {/* Footer */}
                <div className="flex items-center justify-between pt-2 mt-2 border-t border-ops-border/50">
                  <span className="text-[11px] text-ops-text-muted">
                    <span className="font-semibold text-ops-text-secondary">{event.reporter}</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-ops-text-disabled">{event.id}</span>
                    {isAdminMode && (
                      <button
                        onClick={e => { e.stopPropagation(); openModal('editEvent', { event }) }}
                        className="text-[10px] font-semibold text-ops-warning bg-ops-warning-light border border-ops-warning/25 hover:bg-amber-100 px-2 py-0.5 rounded-md transition-all"
                      >
                        แก้ไข
                      </button>
                    )}
                    {isAdminMode && (
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          openModal('confirmDelete', {
                            eventTitle: event.title,
                            eventId:    event.id,
                            onConfirm:  () => deleteEvent(event.id),
                          })
                        }}
                        className="flex items-center gap-1 text-[10px] font-semibold text-ops-danger bg-ops-danger-light border border-ops-danger/20 hover:bg-ops-danger/15 px-2 py-0.5 rounded-md transition-all"
                        aria-label="ลบเหตุการณ์"
                      >
                        🗑 ลบ
                      </button>
                    )}
                  </div>
                </div>

              </div>
            </div>
          </div>
        </div>
      </>
    )
  },
  (prev, next) =>
    prev.event.id          === next.event.id &&
    prev.event.status      === next.event.status &&
    prev.event.updated_at  === next.event.updated_at &&
    prev.event.actual_time === next.event.actual_time &&
    prev.state             === next.state,
)
