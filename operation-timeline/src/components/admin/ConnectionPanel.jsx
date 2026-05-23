import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import { testConnection } from '../../services/eventService'
import clsx from 'clsx'

const STATUS = { idle: 'idle', testing: 'testing', ok: 'ok', fail: 'fail' }

export const ConnectionPanel = () => {
  const { isMockMode, lastSyncAt, refetch } = useApp()
  const [status,  setStatus]  = useState(STATUS.idle)
  const [result,  setResult]  = useState(null)
  const [open,    setOpen]    = useState(false)

  const runTest = async () => {
    setStatus(STATUS.testing)
    setResult(null)
    try {
      const data = await testConnection()
      setResult(data)
      setStatus(STATUS.ok)
    } catch (ex) {
      setResult({ error: ex.message })
      setStatus(STATUS.fail)
    }
  }

  const statusColor = {
    [STATUS.idle]:    'text-ops-text-muted',
    [STATUS.testing]: 'text-ops-warning',
    [STATUS.ok]:      'text-ops-success',
    [STATUS.fail]:    'text-ops-danger',
  }[status]

  const statusIcon = {
    [STATUS.idle]:    '○',
    [STATUS.testing]: '◌',
    [STATUS.ok]:      '✓',
    [STATUS.fail]:    '✕',
  }[status]

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className={clsx(
          'flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1.5 rounded-lg border transition-all',
          isMockMode
            ? 'text-ops-warning bg-ops-warning-light border-ops-warning/30 hover:bg-amber-100'
            : 'text-ops-success bg-ops-success-light border-ops-success/30 hover:bg-emerald-100',
        )}
      >
        <span className="font-mono">{isMockMode ? 'MOCK' : 'LIVE'}</span>
        <span className={clsx('text-[10px]', statusColor)}>{statusIcon}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-72 bg-white border border-ops-border rounded-xl shadow-card-md z-50 animate-slide-down overflow-hidden">
          <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/40 to-transparent" />
          <div className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-sm text-ops-text-primary">การเชื่อมต่อ</h3>
              <button
                onClick={() => setOpen(false)}
                className="text-ops-text-muted hover:text-ops-text-primary text-xs w-5 h-5 flex items-center justify-center"
              >
                ✕
              </button>
            </div>

            {/* Current mode */}
            <div className="flex items-center justify-between mb-3 p-2.5 rounded-lg bg-ops-bg border border-ops-border">
              <span className="text-xs text-ops-text-secondary font-medium">โหมดปัจจุบัน</span>
              <span className={clsx(
                'text-[11px] font-bold px-2 py-0.5 rounded',
                isMockMode
                  ? 'text-ops-warning bg-ops-warning-light border border-ops-warning/30'
                  : 'text-ops-success bg-ops-success-light border border-ops-success/30',
              )}>
                {isMockMode ? 'MOCK — ข้อมูลทดสอบ' : 'LIVE — Google Sheets'}
              </span>
            </div>

            {/* Env var hint */}
            {isMockMode && (
              <div className="mb-3 p-2.5 rounded-lg bg-amber-50 border border-amber-200">
                <p className="text-[11px] text-amber-700 font-medium mb-1">เปิดใช้โหมด Live:</p>
                <code className="text-[10px] font-mono text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded block">
                  VITE_API_MODE=live
                </code>
                <p className="text-[10px] text-amber-600 mt-1">เพิ่มใน .env.local แล้ว restart dev server</p>
              </div>
            )}

            {/* Test result */}
            {result && (
              <div className={clsx(
                'mb-3 p-2.5 rounded-lg border text-[11px] font-mono',
                status === STATUS.ok
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                  : 'bg-red-50 border-red-200 text-red-700',
              )}>
                {status === STATUS.ok ? (
                  <>
                    <p className="font-bold mb-1">✓ เชื่อมต่อสำเร็จ</p>
                    <p>events: {result.events ?? '—'}</p>
                    <p>logs: {result.logs ?? '—'}</p>
                    <p className="text-[10px] opacity-70 mt-0.5">{result.timestamp}</p>
                  </>
                ) : (
                  <>
                    <p className="font-bold mb-1">✕ เชื่อมต่อไม่สำเร็จ</p>
                    <p className="break-all">{result.error}</p>
                  </>
                )}
              </div>
            )}

            {/* Sync info */}
            {lastSyncAt && (
              <p className="text-[10px] text-ops-text-muted mb-3">
                ซิงก์ล่าสุด: {lastSyncAt.toLocaleTimeString('th-TH')}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={runTest}
                disabled={status === STATUS.testing}
                className="flex-1 text-xs font-semibold py-2 rounded-lg border border-ops-border hover:bg-ops-bg disabled:opacity-50 transition-all"
              >
                {status === STATUS.testing ? 'กำลังทดสอบ...' : 'ทดสอบการเชื่อมต่อ'}
              </button>
              <button
                onClick={() => { refetch(); setOpen(false) }}
                className="flex-1 text-xs font-semibold py-2 rounded-lg bg-ops-accent-light border border-ops-border-focus text-ops-accent hover:bg-sky-100 transition-all"
              >
                รีเฟรชข้อมูล
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
