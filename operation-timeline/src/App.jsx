import { AppProvider, useApp } from './context/AppContext'
import { Header } from './components/layout/Header'
import { Sidebar } from './components/layout/Sidebar'
import { Timeline } from './components/timeline/Timeline'
import { useCurrentTime } from './hooks/useCurrentTime'
import { getEventState } from './utils/timeUtils'
import clsx from 'clsx'

/* ── Mobile progress bar (visible below xl) ──────────────────── */
const MobileBar = () => {
  const { events } = useApp()
  const { timeStr } = useCurrentTime(10000)
  const counts = events.reduce((acc, ev) => {
    const s = getEventState(ev, timeStr); acc[s] = (acc[s] || 0) + 1; return acc
  }, {})
  const done     = counts.past || 0
  const active   = counts.active || 0
  const upcoming = (counts.upcoming || 0) + (counts['upcoming-near'] || 0)
  const pct      = Math.round((done / events.length) * 100)

  return (
    <div className="xl:hidden flex-shrink-0 bg-white border-b border-ops-border px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-3 text-[11px] font-semibold flex-shrink-0">
          <span className="text-ops-success">✓ {done}</span>
          {active > 0 && <span className="text-ops-accent">◉ {active}</span>}
          <span className="text-ops-info">○ {upcoming}</span>
        </div>
        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-1000"
            style={{ width: `${pct}%`, background: 'linear-gradient(90deg,#0ea5e9,#38bdf8)' }}
          />
        </div>
        <span className="font-mono text-[11px] text-ops-text-muted flex-shrink-0 tabular-nums">{pct}%</span>
      </div>
    </div>
  )
}

/* ── Root ────────────────────────────────────────────────────── */
const AppContent = () => (
  <div className="flex flex-col h-screen bg-ops-bg overflow-hidden">
    <Header />
    <MobileBar />

    <main className="flex-1 flex min-h-0 overflow-hidden">
      <Sidebar />
      <div className="flex-1 min-w-0 overflow-hidden px-3 md:px-5 py-3">
        <Timeline />
      </div>
    </main>

    <footer className="flex-shrink-0 bg-white border-t border-ops-border px-4 md:px-6 py-2.5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-[11px] text-ops-text-muted hidden sm:block">
          ศูนย์ควบคุมปฏิบัติการ · แดชบอร์ดเรียลไทม์ v1.0
        </span>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-ops-success">
            <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse" />
            ระบบออนไลน์
          </span>
          <span className="text-[11px] text-ops-text-muted">ข้อมูลทดสอบ</span>
        </div>
      </div>
    </footer>
  </div>
)

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  )
}
