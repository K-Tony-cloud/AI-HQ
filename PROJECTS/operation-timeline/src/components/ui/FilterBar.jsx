import { useFilter } from '../../context/FilterContext'
import clsx from 'clsx'

const TYPE_PILLS = [
  { label: 'ทั้งหมด',   value: '' },
  { label: 'การประชุม',  value: 'briefing' },
  { label: 'รักษาฯ',    value: 'security' },
  { label: 'เคลื่อนย้าย', value: 'movement' },
  { label: 'พิธีการ',   value: 'ceremony' },
  { label: 'สนับสนุน',  value: 'logistics' },
  { label: 'ฉุกเฉิน',   value: 'emergency' },
]

const STATUS_PILLS = [
  { label: 'ทั้งหมด',     value: '' },
  { label: 'กำลังดำเนิน', value: 'active' },
  { label: 'กำหนดการ',   value: 'upcoming' },
  { label: 'เสร็จสิ้น',   value: 'completed' },
]

const PRIORITY_PILLS = [
  { label: 'ทั้งหมด', value: '' },
  { label: 'วิกฤต',   value: 'critical' },
  { label: 'สูง',     value: 'high' },
]

const pillBase = 'text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-all cursor-pointer'
const pillActive   = 'bg-ops-accent text-white border-ops-accent'
const pillInactive = 'bg-ops-bg border-ops-border text-ops-text-muted hover:bg-white'

const PillGroup = ({ pills, value, onChange }) => (
  <div className="flex items-center gap-1 flex-wrap">
    {pills.map(p => (
      <button
        key={p.value}
        onClick={() => onChange(p.value)}
        className={clsx(pillBase, value === p.value ? pillActive : pillInactive)}
      >
        {p.label}
      </button>
    ))}
  </div>
)

export const FilterBar = ({ searchRef, totalCount, filteredCount }) => {
  const {
    searchQuery,    setSearchQuery,
    typeFilter,     setTypeFilter,
    statusFilter,   setStatusFilter,
    priorityFilter, setPriorityFilter,
    clearFilters,
    hasActiveFilters,
  } = useFilter()

  return (
    <div className="bg-white border-b border-ops-border px-3 md:px-5 py-2 flex items-center gap-2 flex-wrap flex-shrink-0">
      {/* Search input */}
      <div className="relative flex items-center">
        <input
          ref={searchRef}
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="ค้นหาเหตุการณ์..."
          className="text-xs w-40 sm:w-52 bg-ops-bg border border-ops-border rounded-lg px-2.5 py-1 pr-6 text-ops-text-primary placeholder-ops-text-muted focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-1.5 text-ops-text-muted hover:text-ops-text-primary text-xs leading-none"
          >
            ×
          </button>
        )}
      </div>

      {/* Type pills — hidden on mobile */}
      <div className="hidden sm:flex items-center gap-1">
        <span className="text-[10px] text-ops-text-muted font-medium flex-shrink-0">ประเภท:</span>
        <PillGroup pills={TYPE_PILLS} value={typeFilter} onChange={setTypeFilter} />
      </div>

      {/* Status pills — hidden on mobile */}
      <div className="hidden sm:flex items-center gap-1">
        <span className="text-[10px] text-ops-text-muted font-medium flex-shrink-0">สถานะ:</span>
        <PillGroup pills={STATUS_PILLS} value={statusFilter} onChange={setStatusFilter} />
      </div>

      {/* Priority pills — hidden on mobile */}
      <div className="hidden sm:flex items-center gap-1">
        <span className="text-[10px] text-ops-text-muted font-medium flex-shrink-0">ความสำคัญ:</span>
        <PillGroup pills={PRIORITY_PILLS} value={priorityFilter} onChange={setPriorityFilter} />
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Filtered count */}
      {hasActiveFilters && totalCount != null && (
        <span className="text-[10px] text-ops-text-muted flex-shrink-0">
          แสดง {filteredCount} / {totalCount} เหตุการณ์
        </span>
      )}

      {/* Clear button */}
      {hasActiveFilters && (
        <button
          onClick={clearFilters}
          className="text-[10px] font-semibold text-ops-danger bg-ops-danger-light border border-ops-danger/25 hover:bg-red-100 px-2 py-0.5 rounded-full transition-all flex-shrink-0"
        >
          ล้างตัวกรอง ×
        </button>
      )}
    </div>
  )
}
