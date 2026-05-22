import { getLogsForEvent } from '../../data/mockLogs'
import { getLogTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

export const EventLogs = ({ eventId }) => {
  const logs = getLogsForEvent(eventId)
  if (logs.length === 0) return null

  return (
    <div className="mt-3 pt-3 border-t border-ops-border/50">
      <p className="ops-label mb-2">บันทึกการอัปเดต</p>
      <div className="space-y-1.5">
        {logs.map(log => {
          const cfg = getLogTypeConfig(log.type)
          return (
            <div key={log.id} className={clsx('flex gap-2.5 rounded-lg p-2', cfg.bg, 'border border-ops-border/30')}>
              <span className={clsx('font-mono text-xs font-bold flex-shrink-0 mt-0.5 w-4 text-center', cfg.color)}>
                {cfg.icon}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-mono text-[11px] text-ops-accent font-bold tabular-nums">{log.time}</span>
                  <span className="text-[10px] text-ops-text-muted font-semibold tracking-wide uppercase">{log.user}</span>
                </div>
                <p className="text-xs text-ops-text-secondary leading-relaxed">{log.message}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
