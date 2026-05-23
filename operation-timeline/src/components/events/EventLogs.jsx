import { useState, useEffect, useCallback } from 'react'
import { fetchLogs, createLog } from '../../services/eventService'
import { getLogTypeConfig } from '../../utils/statusUtils'
import { useApp } from '../../context/AppContext'
import { useToast } from '../../context/ToastContext'
import clsx from 'clsx'

const LOG_TYPES = [
  { value: 'alert',     label: 'แจ้งเตือน' },
  { value: 'update',    label: 'อัปเดต' },
  { value: 'info',      label: 'ข้อมูล' },
  { value: 'resolved',  label: 'แก้ไขแล้ว' },
  { value: 'completed', label: 'เสร็จสิ้น' },
]

export const EventLogs = ({ eventId }) => {
  const { isAdminMode } = useApp()
  const { addToast }    = useToast()

  const [logs,      setLogs]      = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [newMsg,    setNewMsg]    = useState('')
  const [newType,   setNewType]   = useState('info')
  const [submitting, setSubmitting] = useState(false)

  const loadLogs = useCallback(async () => {
    try {
      setIsLoading(true)
      const data = await fetchLogs(eventId)
      setLogs(data || [])
    } catch (_) {
      setLogs([])
    } finally {
      setIsLoading(false)
    }
  }, [eventId])

  useEffect(() => {
    loadLogs()
  }, [loadLogs])

  const handleAddLog = async (e) => {
    e.preventDefault()
    if (!newMsg.trim()) return
    setSubmitting(true)
    try {
      await createLog({
        event_id: eventId,
        time:     new Date().toTimeString().slice(0, 5),
        message:  newMsg.trim(),
        user:     'ADMIN',
        type:     newType,
      })
      addToast('เพิ่มบันทึกแล้ว', 'success')
      setNewMsg('')
      setNewType('info')
      await loadLogs()
    } catch (ex) {
      addToast(ex.message || 'เพิ่มบันทึกไม่สำเร็จ', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="mt-3 pt-3 border-t border-ops-border/50">
        <p className="ops-label mb-2">บันทึกการอัปเดต</p>
        <p className="text-xs text-ops-text-muted text-center py-2">กำลังโหลด...</p>
      </div>
    )
  }

  return (
    <div className="mt-3 pt-3 border-t border-ops-border/50">
      <p className="ops-label mb-2">บันทึกการอัปเดต</p>

      {logs.length === 0 ? (
        <p className="text-xs text-ops-text-muted text-center py-2">ไม่มีบันทึกเหตุการณ์</p>
      ) : (
        <div className="space-y-1.5">
          {logs.map(log => {
            const cfg = getLogTypeConfig(log.type)
            return (
              <div
                key={log.id}
                className={clsx(
                  'flex gap-2.5 rounded-lg p-2 border border-ops-border/30 animate-fade-in',
                  cfg.bg,
                )}
              >
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
      )}

      {/* Admin add-log form */}
      {isAdminMode && (
        <form onSubmit={handleAddLog} className="mt-3 pt-3 border-t border-ops-border/40 space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              value={newMsg}
              onChange={e => setNewMsg(e.target.value)}
              placeholder="ข้อความบันทึก..."
              className="flex-1 bg-ops-surface border border-ops-border/50 rounded-lg px-2.5 py-1.5 text-xs text-ops-text-primary focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted"
            />
            <select
              value={newType}
              onChange={e => setNewType(e.target.value)}
              className="bg-ops-surface border border-ops-border/50 rounded-lg px-2 py-1.5 text-xs text-ops-text-primary focus:outline-none focus:border-ops-accent/50 transition-all"
            >
              {LOG_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={submitting || !newMsg.trim()}
            className="w-full py-1.5 rounded-lg bg-ops-accent-light border border-ops-border-focus text-ops-accent text-xs font-semibold hover:bg-sky-100 transition-all disabled:opacity-40 flex items-center justify-center gap-1.5"
          >
            {submitting ? (
              <>
                <span className="w-3 h-3 border border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
                กำลังบันทึก...
              </>
            ) : (
              '+ เพิ่มบันทึก'
            )}
          </button>
        </form>
      )}
    </div>
  )
}
