import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import { useToast } from '../../context/ToastContext'
import clsx from 'clsx'

const CLASSIFICATIONS = ['RESTRICTED', 'CONFIDENTIAL', 'SECRET']
const STATUSES        = ['ACTIVE', 'STANDBY', 'ARCHIVED']

const inputCls = 'w-full bg-ops-surface border border-ops-border/50 rounded-lg px-3 py-2 text-sm text-ops-text-primary font-mono focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted'

const Field = ({ label, children }) => (
  <div>
    <label className="ops-label block mb-1.5">{label}</label>
    {children}
  </div>
)

export const CreateOperationModal = ({ onClose, cloneSourceId = null }) => {
  const { addOperation, cloneOperation, operations } = useApp()
  const { addToast } = useToast()
  const [isSubmitting, setIsSubmitting] = useState(false)

  const source = cloneSourceId ? operations.find(o => o.id === cloneSourceId) : null

  const [form, setForm] = useState({
    title:          source ? `${source.title} (สำเนา)` : '',
    date:           '',
    classification: source?.classification || 'RESTRICTED',
    commander:      source?.commander      || '',
    start_time:     source?.start_time     || '09:00',
    end_time:       source?.end_time       || '20:00',
    venue:          source?.venue          || '',
    status:         'ACTIVE',
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      if (cloneSourceId) {
        await cloneOperation(cloneSourceId, form)
        addToast('สำเนาปฏิบัติการเรียบร้อย', 'success')
      } else {
        await addOperation(form)
        addToast('สร้างปฏิบัติการใหม่เรียบร้อย', 'success')
      }
      onClose()
    } catch (ex) {
      addToast(ex.message || 'ไม่สำเร็จ', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/65 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-ops-card border border-ops-border rounded-2xl shadow-2xl animate-slide-down overflow-hidden">
        <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/50 to-transparent" />
        <div className="p-6">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-bold text-ops-text-primary text-base">
                {cloneSourceId ? 'สำเนาปฏิบัติการ' : 'สร้างปฏิบัติการใหม่'}
              </h2>
              <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">
                {cloneSourceId ? `จาก: ${source?.id}` : 'กำหนดการปฏิบัติการใหม่'}
              </p>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg bg-ops-surface border border-ops-border/40 flex items-center justify-center text-ops-text-muted hover:text-ops-danger transition-colors"
            >
              ✕
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="ชื่อปฏิบัติการ">
              <input
                type="text"
                required
                placeholder="เช่น Operation Royal Passage"
                value={form.title}
                onChange={e => set('title', e.target.value)}
                className={inputCls}
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="วันที่ปฏิบัติการ">
                <input
                  type="date"
                  required
                  value={form.date}
                  onChange={e => set('date', e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="ชั้นความลับ">
                <select
                  value={form.classification}
                  onChange={e => set('classification', e.target.value)}
                  className={inputCls}
                >
                  {CLASSIFICATIONS.map(c => (
                    <option key={c} value={c} className="bg-ops-card">{c}</option>
                  ))}
                </select>
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="เวลาเริ่ม">
                <input
                  type="time"
                  required
                  value={form.start_time}
                  onChange={e => set('start_time', e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="เวลาสิ้นสุด">
                <input
                  type="time"
                  required
                  value={form.end_time}
                  onChange={e => set('end_time', e.target.value)}
                  className={inputCls}
                />
              </Field>
            </div>

            <Field label="ผู้บัญชาการ">
              <input
                type="text"
                placeholder="เช่น COL. WICHAI SUWAN"
                value={form.commander}
                onChange={e => set('commander', e.target.value)}
                className={inputCls}
              />
            </Field>

            <Field label="พื้นที่ปฏิบัติการ">
              <input
                type="text"
                placeholder="เช่น Bangkok Metropolitan Area"
                value={form.venue}
                onChange={e => set('venue', e.target.value)}
                className={inputCls}
              />
            </Field>

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
                className="flex-1 py-2.5 rounded-xl bg-ops-accent/12 border border-ops-accent/40 text-sm text-ops-accent hover:bg-ops-accent/22 transition-all font-bold disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
                    กำลังบันทึก...
                  </>
                ) : (
                  cloneSourceId ? 'สร้างสำเนา' : 'สร้างปฏิบัติการ'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
