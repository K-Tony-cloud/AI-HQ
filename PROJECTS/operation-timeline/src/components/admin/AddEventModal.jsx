import { useState } from 'react'
import { useApp } from '../../context/AppContext'
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

const inputCls = 'w-full bg-ops-surface border border-ops-border/50 rounded-lg px-3 py-2 text-sm text-ops-text-primary font-mono focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted'

const Field = ({ label, children }) => (
  <div>
    <label className="ops-label block mb-1.5">{label}</label>
    {children}
  </div>
)

export const AddEventModal = ({ onClose }) => {
  const { addEvent, operationMeta, currentOperationId } = useApp()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [form, setForm] = useState({
    planned_time: '',
    title:        '',
    type:         'briefing',
    detail:       '',
    reporter:     '',
    location:     '',
    priority:     'normal',
    visibility:   'public',
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      await addEvent({
        ...form,
        operation_id: currentOperationId,
        date:         operationMeta?.date || '',
        actual_time:  null,
        end_time:     null,
        status:       'upcoming',
        duration:     30,
        visibility:   form.visibility,
      })
      onClose()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal onClose={onClose}>
      {/* Sky accent line */}
      <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/50 to-transparent flex-shrink-0" />

      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 pt-5 pb-4 border-b border-ops-border/40">
        <div>
          <h2 className="font-bold text-ops-text-primary text-base">เพิ่มเหตุการณ์ใหม่</h2>
          <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">
            ผู้ดูแล · {operationMeta?.id || 'อัปเดตแผนปฏิบัติการ'}
          </p>
        </div>
        <ModalClose onClose={onClose} />
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <form id="add-event-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="เวลาที่วางแผน">
              <input
                type="time"
                required
                value={form.planned_time}
                onChange={e => set('planned_time', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="ประเภท">
              <select value={form.type} onChange={e => set('type', e.target.value)} className={inputCls}>
                {TYPES.map(t => <option key={t.value} value={t.value} className="bg-ops-card">{t.label}</option>)}
              </select>
            </Field>
          </div>

          <Field label="ชื่อเหตุการณ์">
            <input
              type="text"
              required
              placeholder="เช่น การตรวจพื้นที่ — โซน ดี"
              value={form.title}
              onChange={e => set('title', e.target.value)}
              className={inputCls}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="ผู้รายงาน">
              <input
                type="text"
                placeholder="เช่น ร.ต. สมชาย"
                value={form.reporter}
                onChange={e => set('reporter', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="ความสำคัญ">
              <select value={form.priority} onChange={e => set('priority', e.target.value)} className={inputCls}>
                {PRIORITIES.map(p => <option key={p.value} value={p.value} className="bg-ops-card">{p.label}</option>)}
              </select>
            </Field>
          </div>

          <Field label="สถานที่">
            <input
              type="text"
              placeholder="เช่น ทำเนียบรัฐบาล — ห้องโถงหลัก"
              value={form.location}
              onChange={e => set('location', e.target.value)}
              className={inputCls}
            />
          </Field>

          <Field label="รายละเอียด">
            <textarea
              rows={3}
              placeholder="รายละเอียดการปฏิบัติการ..."
              value={form.detail}
              onChange={e => set('detail', e.target.value)}
              className={clsx(inputCls, 'resize-y min-h-[72px]')}
            />
          </Field>
        </form>
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 flex gap-3 px-6 py-4 border-t border-ops-border/40 bg-ops-bg/50">
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
          form="add-event-form"
          disabled={isSubmitting}
          className="flex-1 py-2.5 rounded-xl bg-ops-accent/12 border border-ops-accent/40 text-sm text-ops-accent hover:bg-ops-accent/22 transition-all font-bold disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {isSubmitting ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
              กำลังเพิ่ม...
            </>
          ) : 'เพิ่มเหตุการณ์'}
        </button>
      </div>
    </Modal>
  )
}
