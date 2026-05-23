import { useState, useEffect } from 'react'
import { fetchAllLogs } from '../../services/eventService'
import { getLogTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

const LOG_TYPES = ['all', 'alert', 'update', 'info', 'resolved', 'completed']

const formatTime = (log) => {
  if (log.created_at) {
    // Extract time portion from ISO string
    try {
      return new Date(log.created_at).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
    } catch (_) {}
  }
  return log.time || '—'
}

export const AuditPanel = ({ onClose }) => {
  const [logs,        setLogs]        = useState([])
  const [isLoading,   setIsLoading]   = useState(true)
  const [error,       setError]       = useState(null)
  const [typeFilter,  setTypeFilter]  = useState('all')

  const load = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchAllLogs(100)
      setLogs(data)
    } catch (ex) {
      setError(ex.message || 'โหลดข้อมูลไม่สำเร็จ')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = typeFilter === 'all'
    ? logs
    : logs.filter(l => l.type === typeFilter)

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-96 z-40 bg-white border-l border-ops-border shadow-2xl flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-ops-border">
        <h2 className="font-bold text-sm text-ops-text-primary">บันทึกการดำเนินงาน</h2>
        <button
          onClick={onClose}
          className="w-7 h-7 rounded-lg bg-ops-surface border border-ops-border/40 flex items-center justify-center text-ops-text-muted hover:text-ops-danger transition-colors text-xs"
        >
          ✕
        </button>
      </div>

      {/* Filter row */}
      <div className="flex-shrink-0 px-4 py-2.5 border-b border-ops-border bg-ops-bg">
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="w-full bg-white border border-ops-border/50 rounded-lg px-3 py-1.5 text-xs text-ops-text-primary focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all"
        >
          {LOG_TYPES.map(t => (
            <option key={t} value={t} className="bg-white">
              {t === 'all' ? 'ทุกประเภท' : t}
            </option>
          ))}
        </select>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <span className="w-5 h-5 border-2 border-ops-accent/30 border-t-ops-accent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-32 gap-3 px-4">
            <p className="text-xs text-ops-danger text-center">{error}</p>
            <button
              onClick={load}
              className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-ops-border hover:bg-ops-bg transition-all"
            >
              ลองใหม่
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <p className="text-xs text-ops-text-muted">ไม่มีบันทึก</p>
          </div>
        ) : (
          <ul className="divide-y divide-ops-border/50">
            {filtered.map((log) => {
              const cfg = getLogTypeConfig(log.type)
              return (
                <li key={log.id} className={clsx('px-4 py-3 text-xs', cfg.bg)}>
                  <div className="flex items-start gap-2">
                    <span className={clsx('flex-shrink-0 font-bold mt-0.5', cfg.color)}>
                      {cfg.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        {log.event_id && (
                          <span className="ops-label bg-ops-accent-light text-ops-accent border border-ops-border-focus px-1.5 py-0.5 rounded">
                            {log.event_id}
                          </span>
                        )}
                        <span className="font-mono text-ops-text-muted text-[10px]">
                          {formatTime(log)}
                        </span>
                        {log.user && (
                          <span className="text-ops-text-muted text-[10px]">{log.user}</span>
                        )}
                      </div>
                      <p className="text-ops-text-secondary leading-relaxed">{log.message}</p>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
