import { useAuth } from '../../context/AuthContext'
import { useModalActions } from '../../context/ModalContext'

const ROLE_LABELS = {
  super_admin: 'ผู้ดูแลระบบ',
  op_admin:    'ผู้ดูแล',
}

export const LoginButton = () => {
  const { user, logout, isSuperAdmin } = useAuth()
  const { openModal } = useModalActions()

  if (user) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ops-success bg-ops-success-light border border-ops-success/30 px-2.5 py-1.5 rounded-lg max-w-[140px]">
          <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse flex-shrink-0" />
          <span className="truncate">{ROLE_LABELS[user.role] || user.role}</span>
        </span>
        {isSuperAdmin && (
          <button
            onClick={() => openModal('userManagement', {})}
            className="text-[11px] font-medium text-ops-text-muted hover:text-ops-accent border border-ops-border hover:border-ops-accent/30 hover:bg-ops-accent-light px-2 py-1.5 rounded-lg transition-all"
            title="จัดการผู้ใช้"
          >
            👥
          </button>
        )}
        <button
          onClick={logout}
          className="text-[11px] font-medium text-ops-text-muted hover:text-ops-danger border border-ops-border hover:border-ops-danger/30 hover:bg-ops-danger-light px-2.5 py-1.5 rounded-lg transition-all"
        >
          ออก
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={() => openModal('googleLogin', {})}
      className="flex items-center gap-2 text-[11px] font-medium text-ops-text-secondary hover:text-ops-text-primary border border-ops-border hover:border-ops-border-focus bg-white hover:bg-ops-accent-light px-3 py-1.5 rounded-lg transition-all duration-150 shadow-sm"
    >
      <span>🔐</span>
      <span>เข้าสู่ระบบ</span>
    </button>
  )
}
