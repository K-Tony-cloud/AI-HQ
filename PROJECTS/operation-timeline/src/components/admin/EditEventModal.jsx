import { useState, useEffect } from 'react'
import { useApp } from '../../context/AppContext'
import { useToast } from '../../context/ToastContext'
import { createLog } from '../../services/eventService'
import { Modal, ModalClose } from '../ui/Modal'
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
  { value: 'upcoming',  label: 'กำหนดการ' },
  { value: 'active',    label: 'กำลังดำเนินการ' },
  { value: 'completed', label: 'เสร็จสิ้น' },
  { value: 'resolved',  label: 'แก้ไขแล้ว' },
]

const inputCls = 'w-full bg-ops-surface border border-ops-border/50 rounded-lg px-3 py-2 text-sm text-ops-text-primary font-mono focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted'

const Field = ({ label, children, span }) => (
  <div className={span}>
    <label className="ops-label block mb-1.5">{label}</label>
    {children}
  </div>
)

export const EditEventModal = ({ event, onClose }) => {
  const { updateEvent, events, setEditingEventId, deleteEvent } = useApp()
  const { addToast }                               = useToast()
  const [isSubmitting,  setIsSubmitting]  = useState(false)
  const [showConflict,  setShowConflict]  = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [isDeleting,    setIsDeleting]    = useState(false)
  const [openedUpdatedAt] = useState(() => event.updated_at)

  const [form, setForm] = useState({
    planned_time: event.planned_time || '',
    actual_time:  event.actual_time  || '',
    end_time:     event.end_time     || '',
    title:        event.title        || '',
    type:         event.type         || 'briefing',
    status:       event.status       || 'upcoming',
    detail:       event.detail       || '',
    reporter:     event.reporter     || '',
    location:     event.location     || '',
    priority:     event.priority     || 'normal',
    visibility:   event.visibility   || 'public',
  })

  // Mark this event as being edited (shows badge on timeline card)
  useEffect(() => {
    setEditingEventId(event.id)
    return () => setEditingEventId(null)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const doSave = async () => {
    setIsSubmitting(true)
    try {
      const updates = {
        ...form,
        actual_time: form.actual_time || null,
        end_time:    form.end_time    || null,
      }
      await updateEvent(event.id, updates)

      if (form.status !== event.status) {
        try {
          await createLog({
            event_id: event.id,
            time:     new Date().toTimeString().slice(0, 5),
            message:  `อัปเดตสถานะ: ${event.status} → ${form.status}`,
            user:     'ADMIN',
            type:     'update',
          })
        } catch (_) {}
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
    const current = events.find(ev => ev.id === event.id)
    if (current?.updated_at && openedUpdatedAt && current.updated_at !== openedUpdatedAt) {
      setShowConflict(true)
      return
    }
    await doSave()
  }

  return (
    <Modal onClose={onClose}>
      {/* Conflict overlay */}
      {showConflict && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/92 backdrop-blur-sm rounded-2xl">
          <div className="text-center p-8 max-w-xs">
            <p className="text-3xl mb-3">⚠️</p>
            <p className="font-bold text-ops-text-primary text-sm mb-1">ข้อมูลถูกแก้ไขล่าสุด</p>
            <p className="text-xs text-ops-text-muted mb-5 leading-relaxed">
              เหตุการณ์นี้ถูกแก้ไขหลังจากที่คุณเปิดหน้านี้<br />บันทึกทับหรือไม่?
            </p>
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

      {/* Amber accent line */}
      <div className="h-px bg-gradient-to-r from-transparent via-ops-warning/60 to-transparent flex-shrink-0" />

      {/* Header — fixed inside modal */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 pt-5 pb-4 border-b border-ops-border/40">
        <div>
          <h2 className="font-bold text-ops-text-primary text-base">แก้ไขเหตุการณ์</h2>
          <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">{event.id} · ผู้ดูแล</p>
        </div>
        <ModalClose onClose={onClose} />
      </div>

      {/* Scrollable form body */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <form id="edit-event-form" onSubmit={handleSubmit} className="space-y-4">

          {/* Section: ข้อมูลเหตุการณ์ */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="ประเภท">
              <select value={form.type} onChange={e => set('type', e.target.value)} className={inputCls}>
                {TYPES.map(t => <option key={t.value} value={t.value} className="bg-ops-card">{t.label}</option>)}
              </select>
            </Field>
            <Field label="ความสำคัญ">
              <select value={form.priority} onChange={e => set('priority', e.target.value)} className={inputCls}>
                {PRIORITIES.map(p => <option key={p.value} value={p.value} className="bg-ops-card">{p.label}</option>)}
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

          {/* Section: เวลา */}
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
            <Field label="เวลาสิ้นสุด">
              <input
                type="time"
                value={form.end_time}
                onChange={e => set('end_time', e.target.value)}
                className={inputCls}
              />
            </Field>
          </div>

          <Field label="สถานะ">
            <div className="grid grid-cols-4 gap-2">
              {STATUSES.map(s => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => set('status', s.value)}
                  className={clsx(
                    'py-2 px-1 rounded-lg text-[11px] font-semibold border transition-all text-center',
                    form.status === s.value
                      ? 'bg-ops-warning/10 border-ops-warning/50 text-ops-warning'
                      : 'border-ops-border/40 text-ops-text-muted hover:border-ops-border hover:text-ops-text-primary hover:bg-ops-surface',
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
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

          <Field label="รายละเอียด">
            <textarea
              rows={4}
              value={form.detail}
              onChange={e => set('detail', e.target.value)}
              className={clsx(inputCls, 'resize-y min-h-[80px]')}
              placeholder="รายละเอียดการปฏิบัติการ..."
            />
          </Field>
        </form>
      </div>

      {/* Footer actions — fixed inside modal */}
      <div className="flex-shrink-0 border-t border-ops-border/40 bg-ops-bg/50">

        {/* Inline delete confirmation — replaces footer when armed */}
        {confirmingDelete ? (
          <div className="px-6 py-4 flex flex-col gap-3">
            <p className="text-xs text-center text-ops-danger font-semibold">
              ยืนยันการลบ "{event.title}"?
            </p>
            <p className="text-[11px] text-center text-ops-text-muted -mt-1">
              เหตุการณ์จะถูกซ่อน แต่กู้คืนได้โดยผู้ดูแลระบบ
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                disabled={isDeleting}
                className="flex-1 py-2.5 rounded-xl border border-ops-border/50 text-sm text-ops-text-muted hover:text-ops-text-primary hover:bg-ops-surface transition-all font-semibold disabled:opacity-40"
              >
                ยกเลิก
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={async () => {
                  setIsDeleting(true)
                  try {
                    await deleteEvent(event.id)
                    onClose()
                  } catch (_) {
                    setIsDeleting(false)
                    setConfirmingDelete(false)
                  }
                }}
                className="flex-1 py-2.5 rounded-xl bg-ops-danger/10 border border-ops-danger/40 text-sm text-ops-danger hover:bg-ops-danger/18 transition-all font-bold disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isDeleting
                  ? <span className="w-3.5 h-3.5 border-2 border-ops-danger/40 border-t-ops-danger rounded-full animate-spin" />
                  : '🗑'
                }
                {isDeleting ? 'กำลังลบ...' : 'ยืนยันการลบ'}
              </button>
            </div>
          </div>
        ) : (
          <div className="px-6 py-4 flex gap-3">
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 py-2.5 px-4 rounded-xl border border-ops-danger/30 text-sm text-ops-danger hover:bg-ops-danger-light transition-all font-semibold disabled:opacity-40"
            >
              🗑 ลบเหตุการณ์
            </button>
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
              form="edit-event-form"
              disabled={isSubmitting}
              className="flex-1 py-2.5 rounded-xl bg-ops-warning/10 border border-ops-warning/40 text-sm text-ops-warning hover:bg-ops-warning/15 transition-all font-bold disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-ops-warning/40 border-t-ops-warning rounded-full animate-spin" />
                  กำลังบันทึก...
                </>
              ) : 'บันทึกการเปลี่ยนแปลง'}
            </button>
          </div>
        )}
      </div>
    </Modal>
  )
}
