import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import { useToast } from '../../context/ToastContext'
import { createLog } from '../../services/eventService'
import clsx from 'clsx'

const TYPES = [
  { value: 'briefing',  label: 'การประชุม' },
  { value: 'security',  label: 'รักษาความปลอดภัย' },
  { value: 'movement',  label: 'การเคลื่อนย้าย' },
  { value: 'ceremony',  label: 'พิธีการ' },
  { value: 'logistics', label: 'การสนับสนุน' },
  { value: 'emergency', label: 'เหตุฉุกเฉิน' },
]

const PRIORITIES = [
  { value: 'normal',   label: 'ปกติ' },
  { value: 'high',     label: 'สูง' },
  { value: 'critical', label: 'วิกฤต' },
]

const STATUSES = [
  { value: 'upcoming',   label: 'กำหนดการ' },
  { value: 'active',     label: 'กำลังดำเนินการ' },
  { value: 'completed',  label: 'เสร็จสิ้น' },
  { value: 'resolved',   label: 'แก้ไขแล้ว' },
]

const inputCls = 'w-full bg-ops-surface border border-ops-border/50 rounded-lg px-3 py-2 text-sm text-ops-text-primary font-mono focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted'

const Field = ({ label, children }) => (
  <div>
    <label className="ops-label block mb-1.5">{label}</label>
    {children}
  </div>
)

export const EditEventModal = ({ event, onClose }) => {
  const { updateEvent, events } = useApp()
  const { addToast }            = useToast()
  const [isSubmitting,  setIsSubmitting]  = useState(false)
  const [showConflict,  setShowConflict]  = useState(false)
  const [openedUpdatedAt] = useState(() => event.updated_at)
  const [form, setForm] = useState({
    planned_time: event.planned_time || '',
    actual_time:  event.actual_time  || '',
    title:        event.title        || '',
    type:         event.type         || 'briefing',
    status:       event.status       || 'upcoming',
    detail:       event.detail       || '',
    reporter:     event.reporter     || '',
    location:     event.location     || '',
    priority:     event.priority     || 'normal',
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const doSave = async () => {
    setIsSubmitting(true)
    try {
      const updates = { ...form, actual_time: form.actual_time || null }
      await updateEvent(event.id, updates)

      // Auto-log status change
      if (form.status !== event.status) {
        try {
          await createLog({
            event_id: event.id,
            time:     new Date().toTimeString().slice(0, 5),
            message:  `อัปเดตสถานะ: ${event.status} → ${form.status}`,
            user:     'ADMIN',
            type:     'update',
          })
        } catch (_) {
          // Non-critical
        }
      }

      addToast('บันทึกเรียบร้อย', 'success')
      onClose()
    } catch (ex) {
      addToast(ex.message || 'บันทึกไม่สำเร็จ', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    // Conflict check
    const current = events.find(ev => ev.id === event.id)
    if (current && current.updated_at && openedUpdatedAt && current.updated_at !== openedUpdatedAt) {
      setShowConflict(true)
      return
    }
    await doSave()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/65 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-ops-card border border-ops-border rounded-2xl shadow-2xl animate-slide-down overflow-hidden">
        {showConflict && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90 backdrop-blur-sm rounded-2xl">
            <div className="text-center p-6 max-w-xs">
              <p className="text-2xl mb-3">⚠️</p>
              <p className="font-bold text-ops-text-primary text-sm mb-1">ข้อมูลถูกแก้ไขล่าสุด</p>
              <p className="text-xs text-ops-text-muted mb-4">เหตุการณ์นี้ถูกแก้ไขหลังจากที่คุณเปิดหน้านี้ บันทึกทับหรือไม่?</p>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowConflict(false)}
                  className="flex-1 py-2 rounded-lg border border-ops-border text-xs font-semibold text-ops-text-muted hover:bg-ops-bg transition-all"
                >
                  ยกเลิก
                </button>
                <button
                  onClick={() => { setShowConflict(false); doSave() }}
                  className="flex-1 py-2 rounded-lg bg-ops-warning/10 border border-ops-warning/40 text-xs font-bold text-ops-warning hover:bg-ops-warning/20 transition-all"
                >
                  บันทึกทับ
                </button>
              </div>
            </div>
          </div>
        )}
        <div className="h-px bg-gradient-to-r from-transparent via-ops-warning/60 to-transparent" />
        <div className="p-6">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-bold text-ops-text-primary text-base">แก้ไขเหตุการณ์</h2>
              <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">{event.id} · ผู้ดูแล</p>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg bg-ops-surface border border-ops-border/40 flex items-center justify-center text-ops-text-muted hover:text-ops-danger transition-colors"
            >
              ✕
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Time row */}
            <div className="grid grid-cols-3 gap-3">
              <Field label="เวลาที่วางแผน">
                <input
                  type="time"
                  required
                  value={form.planned_time}
                  onChange={e => set('planned_time', e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="เวลาจริง">
                <input
                  type="time"
                  value={form.actual_time}
                  onChange={e => set('actual_time', e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="สถานะ">
                <select
                  value={form.status}
                  onChange={e => set('status', e.target.value)}
                  className={inputCls}
                >
                  {STATUSES.map(s => (
                    <option key={s.value} value={s.value} className="bg-ops-card">{s.label}</option>
                  ))}
                </select>
              </Field>
            </div>

            {/* Type + Priority */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="ประเภท">
                <select
                  value={form.type}
                  onChange={e => set('type', e.target.value)}
                  className={inputCls}
                >
                  {TYPES.map(t => (
                    <option key={t.value} value={t.value} className="bg-ops-card">{t.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="ความสำคัญ">
                <select
                  value={form.priority}
                  onChange={e => set('priority', e.target.value)}
                  className={inputCls}
                >
                  {PRIORITIES.map(p => (
                    <option key={p.value} value={p.value} className="bg-ops-card">{p.label}</option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="ชื่อเหตุการณ์">
              <input
                type="text"
                required
                value={form.title}
                onChange={e => set('title', e.target.value)}
                className={inputCls}
              />
            </Field>

            <Field label="รายละเอียด">
              <textarea
                rows={3}
                value={form.detail}
                onChange={e => set('detail', e.target.value)}
                className={clsx(inputCls, 'resize-none')}
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="ผู้รายงาน">
                <input
                  type="text"
                  value={form.reporter}
                  onChange={e => set('reporter', e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="สถานที่">
                <input
                  type="text"
                  value={form.location}
                  onChange={e => set('location', e.target.value)}
                  className={inputCls}
                />
              </Field>
            </div>

            <div className="flex gap-3 pt-1">
              <button
                type="button"
                onClick={onClose}
                disabled={isSubmitting}
                className="flex-1 py-2.5 rounded-xl border border-ops-border/50 text-sm text-ops-text-muted hover:text-ops-text-primary hover:bg-ops-surface transition-all font-semibold disabled:opacity-50"
              >
                ยกเลิก
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex-1 py-2.5 rounded-xl bg-ops-warning/10 border border-ops-warning/40 text-sm text-ops-warning hover:bg-ops-warning/18 transition-all font-bold disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-ops-warning/40 border-t-ops-warning rounded-full animate-spin" />
                    กำลังบันทึก...
                  </>
                ) : (
                  'บันทึกการเปลี่ยนแปลง'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
