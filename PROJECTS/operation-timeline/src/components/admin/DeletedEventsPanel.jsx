import { useState, useEffect } from 'react'
import { Modal, ModalClose } from '../ui/Modal'
import { useApp } from '../../context/AppContext'
import { fetchDeletedEvents } from '../../services/eventService'

export const DeletedEventsPanel = ({ onClose }) => {
  const { restoreEvent } = useApp()
  const [items,   setItems]   = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDeletedEvents()
      .then(setItems)
      .finally(() => setLoading(false))
  }, [])

  const handleRestore = async (id) => {
    await restoreEvent(id)
    setItems(prev => prev.filter(e => e.id !== id))
  }

  return (
    <Modal onClose={onClose}>
      <div className="h-px bg-gradient-to-r from-transparent via-ops-danger/40 to-transparent flex-shrink-0" />
      <div className="flex-shrink-0 flex items-center justify-between px-6 pt-5 pb-4 border-b border-ops-border/40">
        <div>
          <h2 className="font-bold text-ops-text-primary text-base">เหตุการณ์ที่ถูกลบ</h2>
          <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">เฉพาะผู้ดูแลระบบ</p>
        </div>
        <ModalClose onClose={onClose} />
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex justify-center py-8">
            <span className="w-5 h-5 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-center text-sm text-ops-text-muted py-8">ไม่มีเหตุการณ์ที่ถูกลบ</p>
        ) : (
          <div className="space-y-2">
            {items.map(ev => (
              <div key={ev.id} className="flex items-center justify-between gap-3 p-3 rounded-lg bg-ops-surface border border-ops-border/50">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ops-text-primary truncate">{ev.title}</p>
                  <p className="text-[11px] text-ops-text-muted font-mono">
                    {ev.id} · ลบเมื่อ {ev.deleted_at ? new Date(ev.deleted_at).toLocaleString('th-TH') : '—'}
                  </p>
                  {ev.deleted_by && (
                    <p className="text-[10px] text-ops-text-muted">โดย: {ev.deleted_by}</p>
                  )}
                </div>
                <button
                  onClick={() => handleRestore(ev.id)}
                  className="flex-shrink-0 text-[11px] font-semibold text-ops-success bg-ops-success-light border border-ops-success/30 hover:bg-ops-success/15 px-3 py-1.5 rounded-lg transition-all"
                >
                  กู้คืน
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 px-6 py-4 border-t border-ops-border/40">
        <button onClick={onClose} className="w-full py-2.5 rounded-xl border border-ops-border/50 text-sm text-ops-text-muted hover:text-ops-text-primary hover:bg-ops-surface transition-all font-semibold">
          ปิด
        </button>
      </div>
    </Modal>
  )
}
