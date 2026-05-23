import { useState, useEffect } from 'react'
import { useApp } from '../../context/AppContext'
import { LoginButton } from '../admin/LoginButton'
import { AddEventModal } from '../admin/AddEventModal'
import { AuditPanel } from '../admin/AuditPanel'
import { ConnectionPanel } from '../admin/ConnectionPanel'
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

/* ── Compact / Normal toggle ─────────────────────────────────── */
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

/* ── Main Header ─────────────────────────────────────────────── */
export const Header = () => {
  const { operationMeta, isAdminMode } = useApp()
  const [showAddModal,  setShowAddModal]  = useState(false)
  const [showAudit,     setShowAudit]     = useState(false)

  return (
    <>
      <header className="flex-shrink-0 bg-white border-b border-ops-border shadow-header px-4 md:px-6 py-3 relative z-30">
        {/* Sky accent top line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-ops-accent/50 to-transparent" />

        <div className="flex items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-ops-accent-light border border-ops-border-focus flex items-center justify-center shadow-sm">
              <span className="text-lg">⚡</span>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="font-bold text-sm md:text-[15px] text-ops-text-primary truncate leading-tight">
                  {operationMeta.name}
                </h1>
                <span className="hidden sm:inline text-[9px] font-bold text-ops-danger bg-ops-danger-light border border-ops-danger/25 px-1.5 py-0.5 rounded tracking-widest">
                  {operationMeta.classification}
                </span>
              </div>
              <p className="text-[11px] text-ops-text-muted truncate mt-0.5">
                {operationMeta.venue}
                <span className="hidden md:inline"> · {operationMeta.date}</span>
              </p>
            </div>
          </div>

          {/* Center: status + op ID */}
          <div className="hidden md:flex items-center gap-3 flex-shrink-0">
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-ops-success bg-ops-success-light border border-ops-success/25 px-2.5 py-1 rounded-lg">
              <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse" />
              {operationMeta.status}
            </span>
            <div className="hidden lg:block border-l border-ops-border pl-3">
              <p className="font-mono text-[10px] text-ops-text-muted">{operationMeta.id}</p>
              <p className="text-[11px] text-ops-text-secondary font-medium">{operationMeta.commander}</p>
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
                onClick={() => setShowAddModal(true)}
                className="hidden sm:flex items-center gap-1.5 text-xs font-semibold text-ops-accent bg-ops-accent-light border border-ops-border-focus hover:bg-sky-100 px-3 py-1.5 rounded-lg transition-all"
              >
                <span className="text-sm leading-none">+</span>
                <span>เพิ่มเหตุการณ์</span>
              </button>
            )}
            {isAdminMode && (
              <button
                onClick={() => setShowAudit(true)}
                className="text-[11px] font-semibold text-ops-text-secondary border border-ops-border hover:bg-ops-bg px-2.5 py-1.5 rounded-lg transition-all"
              >
                📋 ประวัติ
              </button>
            )}
            <ConnectionPanel />
            <LoginButton />
          </div>
        </div>

        {/* Admin warning bar */}
        {isAdminMode && (
          <div className="mt-2 flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-lg py-1.5 px-3 animate-fade-in">
            <span className="text-xs font-semibold text-amber-700">
              ⚠ โหมดผู้ดูแลระบบ — แก้ไขข้อมูลแบบเรียลไทม์
            </span>
            <button
              onClick={() => setShowAddModal(true)}
              className="sm:hidden text-xs font-semibold text-ops-accent bg-white border border-ops-border rounded px-2 py-0.5"
            >
              + เพิ่ม
            </button>
          </div>
        )}
      </header>

      {showAddModal && <AddEventModal onClose={() => setShowAddModal(false)} />}
      {showAudit    && <AuditPanel onClose={() => setShowAudit(false)} />}
    </>
  )
}
