import { AppProvider, useApp } from './context/AppContext'
import { ToastProvider } from './context/ToastContext'
import { FilterProvider } from './context/FilterContext'
import { ToastContainer } from './components/ui/Toast'
import { Header } from './components/layout/Header'
import { OfflineBanner } from './components/ui/OfflineBanner'
import { Sidebar } from './components/layout/Sidebar'
import { MobileBar as MobileBottomBar } from './components/layout/MobileBar'
import { Timeline } from './components/timeline/Timeline'
import { PlaybackBar } from './components/admin/PlaybackBar'
import { LoadingSpinner } from './components/ui/LoadingSpinner'
import { ErrorBanner } from './components/ui/ErrorBanner'
import { useCurrentTime } from './hooks/useCurrentTime'
import { getEventState } from './utils/timeUtils'
import clsx from 'clsx'

/* ── Mobile progress bar (visible below xl) ──────────────────── */
const MobileProgressBar = () => {
  const { events } = useApp()
  const { timeStr } = useCurrentTime(10000)
  if (!events.length) return null
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

/* ── Footer ──────────────────────────────────────────────────── */
const Footer = () => {
  const { isMockMode, isSyncing, lastSyncAt, error } = useApp()
  const syncLabel = isSyncing
    ? 'กำลังซิงก์...'
    : lastSyncAt
      ? `ซิงก์ ${lastSyncAt.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })}`
      : null

  return (
    <footer className="flex-shrink-0 bg-white border-t border-ops-border px-4 md:px-6 py-2.5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-[11px] text-ops-text-muted hidden sm:block">
          ศูนย์ควบคุมปฏิบัติการ · แดชบอร์ดเรียลไทม์ v1.0
        </span>
        <div className="flex items-center gap-4">
          {!error && (
            <span className="flex items-center gap-1.5 text-[11px] font-medium text-ops-success">
              <span className={clsx(
                'w-1.5 h-1.5 rounded-full',
                isSyncing ? 'bg-ops-warning animate-pulse' : 'bg-ops-success animate-pulse',
              )} />
              ระบบออนไลน์
            </span>
          )}
          {syncLabel && (
            <span className="text-[11px] text-ops-text-muted font-mono">{syncLabel}</span>
          )}
          <span className={clsx(
            'text-[10px] font-bold px-1.5 py-0.5 rounded tracking-wide',
            isMockMode
              ? 'text-ops-warning bg-ops-warning-light border border-ops-warning/25'
              : 'text-ops-success bg-ops-success-light border border-ops-success/25',
          )}>
            {isMockMode ? 'MOCK' : 'LIVE'}
          </span>
        </div>
      </div>
    </footer>
  )
}

/* ── Root ────────────────────────────────────────────────────── */
const AppContent = () => {
  const { isLoading, error, refetch } = useApp()

  return (
    <div className="flex flex-col h-screen bg-ops-bg overflow-hidden">
      <Header />
      <OfflineBanner />
      <MobileProgressBar />

      {error && (
        <div className="flex-shrink-0 px-4 py-2">
          <ErrorBanner message={error} onRetry={refetch} />
        </div>
      )}

      <main className="flex-1 flex min-h-0 overflow-hidden">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <LoadingSpinner
              message="กำลังโหลดข้อมูลปฏิบัติการ..."
              size="lg"
            />
          </div>
        ) : (
          <>
            <Sidebar />
            <div className="flex-1 min-w-0 overflow-hidden px-3 md:px-5 py-3">
              <Timeline />
            </div>
          </>
        )}
      </main>

      <PlaybackBar />
      <Footer />
      <MobileBottomBar />
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <FilterProvider>
        <AppProvider>
          <AppContent />
          <ToastContainer />
        </AppProvider>
      </FilterProvider>
    </ToastProvider>
  )
}
