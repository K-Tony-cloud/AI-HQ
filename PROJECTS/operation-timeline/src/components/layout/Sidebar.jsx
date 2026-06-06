import { useApp } from '../../context/AppContext'
import { useModalActions } from '../../context/ModalContext'
import { useCurrentTime } from '../../hooks/useCurrentTime'
import { getEventState } from '../../utils/timeUtils'
import { getTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

const StatPill = ({ label, value, colorClass, bg }) => (
  <div className={clsx('rounded-xl p-3 border border-ops-border', bg || 'bg-white')}>
    <p className="ops-label mb-1.5">{label}</p>
    <p className={clsx('font-mono text-2xl font-bold leading-none', colorClass)}>{value}</p>
  </div>
)

export const Sidebar = () => {
  const { events, operationMeta } = useApp()
  const { openModal } = useModalActions()
  const { timeStr } = useCurrentTime(10000)

  const counts = events.reduce((acc, ev) => {
    const s = getEventState(ev, timeStr)
    acc[s] = (acc[s] || 0) + 1
    return acc
  }, {})

  const completed = counts.past || 0
  const active    = counts.active || 0
  const upcoming  = (counts.upcoming || 0) + (counts['upcoming-near'] || 0)
  const total     = events.length
  const pct       = Math.round((completed / total) * 100)

  return (
    <aside className="w-52 flex-shrink-0 hidden xl:flex flex-col gap-3 overflow-y-auto py-4 px-3">

      {/* Progress card */}
      <div className="bg-white rounded-xl border border-ops-border shadow-card p-4">
        <p className="ops-label mb-2">ความคืบหน้า</p>
        <div className="flex items-baseline justify-between mb-2.5">
          <span className="font-mono text-3xl font-bold text-ops-accent leading-none">{pct}%</span>
          <span className="text-xs text-ops-text-muted font-mono">{completed} / {total}</span>
        </div>
        {/* Progress bar */}
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-1000"
            style={{
              width: `${pct}%`,
              background: 'linear-gradient(90deg, #0ea5e9, #38bdf8)',
            }}
          />
        </div>
        {active > 0 && (
          <div className="flex items-center gap-1.5 mt-2.5">
            <span className="w-1.5 h-1.5 rounded-full bg-ops-accent animate-blink" />
            <p className="text-[11px] text-ops-accent font-semibold">
              กำลังดำเนินการ {active} กิจกรรม
            </p>
          </div>
        )}
      </div>

      {/* Stats 2×2 */}
      <div className="grid grid-cols-2 gap-2">
        <StatPill label="เสร็จแล้ว"  value={completed} colorClass="text-ops-success" bg="bg-ops-success-light" />
        <StatPill label="ดำเนินการ"  value={active}    colorClass="text-ops-accent" bg="bg-ops-accent-light" />
        <StatPill label="ถัดไป"      value={upcoming}  colorClass="text-ops-info" bg="bg-ops-info-light" />
        <StatPill label="ทั้งหมด"    value={total}     colorClass="text-ops-text-primary" />
      </div>

      {/* Op window */}
      <div className="bg-white rounded-xl border border-ops-border shadow-card p-4">
        <p className="ops-label mb-3">ช่วงปฏิบัติการ</p>
        <div className="space-y-2.5">
          {[
            { l: 'เริ่มต้น',  v: operationMeta?.start_time },
            { l: 'สิ้นสุด',   v: operationMeta?.end_time },
            { l: 'ระยะเวลา',  v: (() => {
              const [sh, sm] = (operationMeta?.start_time || '09:00').split(':').map(Number)
              const [eh, em] = (operationMeta?.end_time   || '20:00').split(':').map(Number)
              const diff = (eh * 60 + em) - (sh * 60 + sm)
              return diff > 0 ? `${Math.floor(diff / 60)} ชั่วโมง ${diff % 60 ? `${diff % 60} นาที` : ''}`.trim() : '-'
            })() },
          ].map(({ l, v }) => (
            <div key={l} className="flex items-center justify-between">
              <span className="ops-label">{l}</span>
              <span className="font-mono text-xs font-semibold text-ops-text-secondary">{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Event types */}
      <div className="bg-white rounded-xl border border-ops-border shadow-card p-4">
        <p className="ops-label mb-3">ประเภทเหตุการณ์</p>
        <div className="space-y-2">
          {[
            { type: 'ceremony',  label: 'พิธีการ' },
            { type: 'security',  label: 'ปลอดภัย' },
            { type: 'movement',  label: 'เดินทาง' },
            { type: 'briefing',  label: 'ประชุม' },
            { type: 'logistics', label: 'สนับสนุน' },
            { type: 'emergency', label: 'ฉุกเฉิน' },
          ].map(({ type, label }) => {
            const cfg   = getTypeConfig(type)
            const count = events.filter(e => e.type === type).length
            return (
              <div key={type} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: cfg.nodeColor }} />
                  <span className={clsx('text-xs font-medium', cfg.color)}>{label}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">{cfg.icon}</span>
                  <span className="font-mono text-xs text-ops-text-muted w-4 text-right">{count}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

    </aside>
  )
}
