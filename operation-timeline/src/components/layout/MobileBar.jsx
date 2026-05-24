import { useApp } from '../../context/AppContext'
import { useFilter } from '../../context/FilterContext'
import { useModal } from '../../context/ModalContext'
import clsx from 'clsx'

export const MobileBar = () => {
  const { isAdminMode, isMockMode, isSyncing, refetch } = useApp()
  const { hasActiveFilters } = useFilter()
  const { openModal } = useModal()

  return (
    <>
      <div className="sm:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-ops-border h-14 flex items-center px-4 pb-safe">
        {/* Admin mode indicator dot */}
        {isAdminMode && (
          <span className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-ops-success" />
        )}

        <div className="flex items-center justify-around w-full">
          {/* Refresh */}
          <button
            onClick={refetch}
            className="flex flex-col items-center gap-0.5 px-4 py-1 rounded-lg text-ops-text-secondary hover:text-ops-accent transition-colors"
            aria-label="รีเฟรช"
          >
            <span className={clsx('text-base leading-none', isSyncing && 'animate-spin')}>
              ↻
            </span>
            <span className="text-[10px] font-medium">รีเฟรช</span>
          </button>

          {/* Add event */}
          <button
            onClick={() => isAdminMode && openModal('addEvent')}
            disabled={!isAdminMode}
            className={clsx(
              'flex flex-col items-center gap-0.5 px-4 py-1 rounded-lg transition-colors',
              isAdminMode
                ? 'text-ops-accent hover:text-sky-600'
                : 'text-ops-text-disabled cursor-not-allowed',
            )}
            aria-label="เพิ่มเหตุการณ์"
          >
            <span className="text-base leading-none">＋</span>
            <span className="text-[10px] font-medium">เพิ่มเหตุการณ์</span>
          </button>

          {/* Search */}
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('focus-search'))}
            className="relative flex flex-col items-center gap-0.5 px-4 py-1 rounded-lg text-ops-text-secondary hover:text-ops-accent transition-colors"
            aria-label="ค้นหา"
          >
            {hasActiveFilters && (
              <span className="absolute top-0 right-2 w-1.5 h-1.5 rounded-full bg-ops-accent" />
            )}
            <span className="text-base leading-none">🔍</span>
            <span className="text-[10px] font-medium">ค้นหา</span>
          </button>

          {/* Mode badge */}
          <div className="flex flex-col items-center gap-0.5 px-4 py-1">
            <span
              className={clsx(
                'text-[10px] font-bold px-1.5 py-0.5 rounded tracking-wide',
                isMockMode
                  ? 'text-ops-warning bg-ops-warning-light border border-ops-warning/25'
                  : 'text-ops-success bg-ops-success-light border border-ops-success/25',
              )}
            >
              {isMockMode ? 'MOCK' : 'LIVE'}
            </span>
            <span className="text-[10px] font-medium text-ops-text-muted">โหมดปัจจุบัน</span>
          </div>
        </div>
      </div>

    </>
  )
}
