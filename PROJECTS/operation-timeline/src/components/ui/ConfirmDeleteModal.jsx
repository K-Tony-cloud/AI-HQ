import { useState } from 'react'
import { Modal } from './Modal'

export const ConfirmDeleteModal = ({ eventTitle, eventId, onConfirm, onClose }) => {
  const [loading, setLoading] = useState(false)

  const handleConfirm = async () => {
    setLoading(true)
    try {
      await onConfirm()
      onClose()
    } catch (_) {
      setLoading(false)
    }
  }

  return (
    <Modal onClose={loading ? undefined : onClose} maxWidth="max-w-sm">
      <div className="h-px bg-gradient-to-r from-transparent via-ops-danger/50 to-transparent flex-shrink-0" />
      <div className="p-6">

        <div className="flex flex-col items-center text-center gap-3 mb-5">
          <div className="w-12 h-12 rounded-full bg-ops-danger-light border border-ops-danger/20 flex items-center justify-center text-xl select-none">
            🗑
          </div>
          <div>
            <h2 className="font-bold text-ops-text-primary text-base">ยืนยันการลบเหตุการณ์</h2>
            <p className="text-[11px] text-ops-text-muted mt-1">
              เหตุการณ์จะถูกซ่อน แต่ยังสามารถกู้คืนได้โดยผู้ดูแลระบบ
            </p>
          </div>
        </div>

        <div className="bg-ops-danger-light border border-ops-danger/20 rounded-lg px-4 py-3 mb-6">
          <p className="text-sm font-semibold text-ops-danger truncate">{eventTitle || eventId}</p>
          {eventTitle && (
            <p className="text-[10px] text-ops-danger/60 font-mono mt-0.5">{eventId}</p>
          )}
        </div>

        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="flex-1 py-2.5 rounded-xl border border-ops-border/50 text-sm text-ops-text-muted hover:text-ops-text-primary hover:bg-ops-surface transition-all font-semibold disabled:opacity-40"
          >
            ยกเลิก
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="flex-1 py-2.5 rounded-xl bg-ops-danger/10 border border-ops-danger/40 text-sm text-ops-danger hover:bg-ops-danger/18 transition-all font-bold disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {loading
              ? <span className="w-3.5 h-3.5 border-2 border-ops-danger/40 border-t-ops-danger rounded-full animate-spin" />
              : <span className="text-base leading-none">🗑</span>
            }
            {loading ? 'กำลังลบ...' : 'ยืนยันการลบ'}
          </button>
        </div>

      </div>
    </Modal>
  )
}
