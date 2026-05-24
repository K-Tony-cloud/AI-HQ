import { useState, useEffect, useRef } from 'react'
import { useApp } from '../../context/AppContext'
import { useModal } from '../../context/ModalContext'
import { LoginButton } from '../admin/LoginButton'
import { ConnectionPanel } from '../admin/ConnectionPanel'
import { exportEventsCSV } from '../../services/exportService'
import clsx from 'clsx'

/* ── Live clock ──────────────────────────────────────────────── */
const LiveClock = () => {
  const [t, setT] = useState(new Date())
  useEffect(() => { const id = setInterval(() => setT(new Date()), 1000); return () => clearInterval(id) }, [])
  const hh = String(t.getHours()).padStart(2,'0')
  const mm = String(t.getMinutes()).padStart(2,'0')
  const ss = String(t.getSeconds()).padStart(2,'0')
  const dateStr = t.toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' })
  return (
    <div className="flex flex-col items-end leading-none gap-0.5">
      <div className="flex items-baseline gap-0.5">
        <span className="font-mono text-xl font-bold text-ops-accent tabular-nums">{hh}:{mm}</span>
        <span className="font-mono text-sm text-ops-text-muted/70">:{ss}</span>
      </div>
      <span className="text-[10px] text-ops-text-muted">{dateStr}</span>
    </div>
  )
}

/* ── Density toggle ──────────────────────────────────────────── */
const DensityToggle = () => {
  const { densityMode, setDensityMode } = useApp()
  const items = [
    { key: 'compact', label: 'ย่อ',  icon: '⊞' },
    { key: 'normal',  label: 'ปกติ', icon: '☰' },
  ]
  return (
    <div className="hidden sm:flex items-center p-0.5 bg-ops-bg border border-ops-border rounded-lg gap-0.5">
      {items.map(({ key, label, icon }) => (
        <button
          key={key}
          onClick={() => setDensityMode(key)}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all duration-150',
            densityMode === key
              ? 'bg-white text-ops-accent shadow-sm border border-ops-border/60'
              : 'text-ops-text-muted hover:text-ops-text-primary',
          )}
        >
          <span className="text-[10px]">{icon}</span>
          {label}
        </button>
      ))}
    </div>
  )
}

/* ── Operation selector dropdown ─────────────────────────────── */
const OperationSelector = ({ isAdmin }) => {
  const { operations, currentOperationId, operationMeta, switchOperation, archiveOperation } = useApp()
  const { openModal } = useModal()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const statusColor = {
    ACTIVE:   'text-ops-success bg-ops-success-light border-ops-success/25',
    STANDBY:  'text-ops-warning bg-amber-50 border-amber-200/60',
    ARCHIVED: 'text-ops-text-muted bg-slate-50 border-slate-200/60',
  }

  return (
    <div ref={ref} className="relative min-w-0">
      {/* Current operation button */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 min-w-0 group"
      >
        <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-ops-accent-light border border-ops-border-focus flex items-center justify-center shadow-sm">
          <span className="text-lg">⚡</span>
        </div>
        <div className="min-w-0 text-left">
          <div className="flex items-center gap-2">
            <h1 className="font-bold text-sm md:text-[15px] text-ops-text-primary truncate leading-tight">
              {operationMeta?.title}
            </h1>
            <span className="hidden sm:inline text-[9px] font-bold text-ops-danger bg-ops-danger-light border border-ops-danger/25 px-1.5 py-0.5 rounded tracking-widest flex-shrink-0">
              {operationMeta?.classification}
            </span>
            <span className="text-ops-text-muted text-xs group-hover:text-ops-accent transition-colors">▾</span>
          </div>
          <p className="text-[11px] text-ops-text-muted truncate mt-0.5">
            {operationMeta?.venue}
            <span className="hidden md:inline"> · {operationMeta?.date}</span>
          </p>
        </div>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-full left-0 mt-2 w-80 bg-white border border-ops-border rounded-xl shadow-2xl z-50 overflow-hidden animate-slide-down">
          <div className="p-2.5 border-b border-ops-border">
            <p className="text-[11px] font-bold text-ops-text-muted uppercase tracking-wider px-1">ปฏิบัติการทั้งหมด</p>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {operations.map(op => (
              <div
                key={op.id}
                className={clsx(
                  'flex items-center gap-2 px-3 py-2.5 hover:bg-ops-bg transition-colors cursor-pointer group/row',
                  op.id === currentOperationId && 'bg-ops-accent-light',
                )}
                onClick={() => { switchOperation(op.id); setOpen(false) }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {op.id === currentOperationId && (
                      <span className="text-ops-accent text-xs flex-shrink-0">●</span>
                    )}
                    <p className={clsx(
                      'text-sm font-semibold truncate',
                      op.id === currentOperationId ? 'text-ops-accent' : 'text-ops-text-primary',
                    )}>
                      {op.title}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="font-mono text-[10px] text-ops-text-muted">{op.date}</span>
                    <span className={clsx(
                      'text-[9px] font-bold px-1.5 py-0.5 rounded border',
                      statusColor[op.status] || statusColor.STANDBY,
                    )}>
                      {op.status}
                    </span>
                  </div>
                </div>
                {isAdmin && (
                  <div className="hidden group-hover/row:flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={e => { e.stopPropagation(); openModal('createOperation', { cloneSourceId: op.id }); setOpen(false) }}
                      title="สำเนา"
                      className="text-[10px] text-ops-text-muted hover:text-ops-accent px-1.5 py-1 rounded hover:bg-ops-accent-light transition-colors"
                    >
                      ⎘
                    </button>
                    {op.status !== 'ARCHIVED' && (
                      <button
                        onClick={e => { e.stopPropagation(); archiveOperation(op.id) }}
                        title="เก็บถาวร"
                        className="text-[10px] text-ops-text-muted hover:text-amber-600 px-1.5 py-1 rounded hover:bg-amber-50 transition-colors"
                      >
                        ✦
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          {isAdmin && (
            <div className="p-2 border-t border-ops-border">
              <button
                onClick={() => { openModal('createOperation'); setOpen(false) }}
                className="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-ops-accent hover:bg-ops-accent-light transition-colors flex items-center gap-2"
              >
                <span className="text-sm">+</span>
                สร้างปฏิบัติการใหม่
              </button>
            </div>
          )}
        </div>
      )}

    </div>
  )
}

/* ── Main Header ─────────────────────────────────────────────── */
export const Header = () => {
  const { operationMeta, isAdminMode, events } = useApp()
  const { openModal } = useModal()

  return (
    <>
      <header className="flex-shrink-0 bg-white border-b border-ops-border shadow-header px-4 md:px-6 py-3 relative z-30">
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-ops-accent/50 to-transparent" />

        <div className="flex items-center justify-between gap-4">
          {/* Brand / Operation selector */}
          <OperationSelector isAdmin={isAdminMode} />

          {/* Center: status + op ID */}
          <div className="hidden md:flex items-center gap-3 flex-shrink-0">
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-ops-success bg-ops-success-light border border-ops-success/25 px-2.5 py-1 rounded-lg">
              <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse" />
              {operationMeta?.status}
            </span>
            <div className="hidden lg:block border-l border-ops-border pl-3">
              <p className="font-mono text-[10px] text-ops-text-muted">{operationMeta?.id}</p>
              <p className="text-[11px] text-ops-text-secondary font-medium">{operationMeta?.commander}</p>
            </div>
          </div>

          {/* Right controls */}
          <div className="flex items-center gap-2.5 flex-shrink-0">
            <DensityToggle />
            <div className="hidden sm:block w-px h-6 bg-ops-border" />
            <LiveClock />
            <div className="hidden sm:block w-px h-6 bg-ops-border" />
            {isAdminMode && (
              <button
                onClick={() => openModal('addEvent')}
                className="hidden sm:flex items-center gap-1.5 text-xs font-semibold text-ops-accent bg-ops-accent-light border border-ops-border-focus hover:bg-sky-100 px-3 py-1.5 rounded-lg transition-all"
              >
                <span className="text-sm leading-none">+</span>
                <span>เพิ่มเหตุการณ์</span>
              </button>
            )}
            {isAdminMode && (
              <button
                onClick={() => openModal('audit')}
                className="text-[11px] font-semibold text-ops-text-secondary border border-ops-border hover:bg-ops-bg px-2.5 py-1.5 rounded-lg transition-all"
              >
                📋 ประวัติ
              </button>
            )}
            {isAdminMode && (
              <button
                onClick={() => exportEventsCSV(events, operationMeta)}
                className="hidden sm:flex text-[11px] font-semibold text-ops-text-secondary border border-ops-border hover:bg-ops-bg px-2.5 py-1.5 rounded-lg transition-all"
              >
                ↓ CSV
              </button>
            )}
            <ConnectionPanel />
            <LoginButton />
          </div>
        </div>

        {isAdminMode && (
          <div className="mt-2 flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-lg py-1.5 px-3 animate-fade-in">
            <span className="text-xs font-semibold text-amber-700">
              ⚠ โหมดผู้ดูแลระบบ — แก้ไขข้อมูลแบบเรียลไทม์
            </span>
            <button
              onClick={() => openModal('addEvent')}
              className="sm:hidden text-xs font-semibold text-ops-accent bg-white border border-ops-border rounded px-2 py-0.5"
            >
              + เพิ่ม
            </button>
          </div>
        )}
      </header>

    </>
  )
}
