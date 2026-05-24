import { useApp } from '../../context/AppContext'
import { useModal } from '../../context/ModalContext'

export const LoginButton = () => {
  const { isAdminMode, setIsAdminMode } = useApp()
  const { openModal } = useModal()

  if (isAdminMode) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ops-success bg-ops-success-light border border-ops-success/30 px-2.5 py-1.5 rounded-lg">
          <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse" />
          ผู้ดูแล
        </span>
        <button
          onClick={() => setIsAdminMode(false)}
          className="text-[11px] font-medium text-ops-text-muted hover:text-ops-danger border border-ops-border hover:border-ops-danger/30 hover:bg-ops-danger-light px-2.5 py-1.5 rounded-lg transition-all"
        >
          ออก
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={() => openModal('pinLogin', { onSuccess: () => setIsAdminMode(true) })}
      className="flex items-center gap-2 text-[11px] font-medium text-ops-text-secondary hover:text-ops-text-primary border border-ops-border hover:border-ops-border-focus bg-white hover:bg-ops-accent-light px-3 py-1.5 rounded-lg transition-all duration-150 shadow-sm"
    >
      <span>🔐</span>
      <span>เข้าสู่ระบบ</span>
    </button>
  )
}
