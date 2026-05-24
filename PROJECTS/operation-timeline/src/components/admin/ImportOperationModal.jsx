import { useState, useRef, useCallback } from 'react'
import { useApp } from '../../context/AppContext'
import { useToast } from '../../context/ToastContext'
import { Modal, ModalClose } from '../ui/Modal'
import { parseCSV, validateCSV, buildEventPayloads } from '../../services/importService'
import clsx from 'clsx'

const CLASSIFICATIONS = ['RESTRICTED', 'CONFIDENTIAL', 'SECRET']

const inputCls = 'w-full bg-ops-surface border border-ops-border/50 rounded-lg px-3 py-2 text-sm text-ops-text-primary font-mono focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted'
const Field = ({ label, required, children }) => (
  <div>
    <label className="ops-label block mb-1.5">
      {label}{required && <span className="text-ops-danger ml-0.5">*</span>}
    </label>
    {children}
  </div>
)

/* ── Step indicator ───────────────────────────────────────────── */
const Steps = ({ step }) => (
  <div className="flex items-center gap-2 mt-1">
    {['อัปโหลด CSV', 'ตรวจสอบ & ยืนยัน'].map((label, i) => {
      const n = i + 1
      const active = step === n
      const done   = step > n
      return (
        <div key={n} className="flex items-center gap-1.5">
          {i > 0 && <div className={clsx('w-6 h-px', done ? 'bg-ops-accent' : 'bg-ops-border')} />}
          <div className={clsx(
            'flex items-center gap-1.5 text-[11px] font-semibold',
            active ? 'text-ops-accent' : done ? 'text-ops-success' : 'text-ops-text-muted',
          )}>
            <span className={clsx(
              'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border',
              active ? 'bg-ops-accent text-white border-ops-accent' :
              done   ? 'bg-ops-success text-white border-ops-success' :
                       'bg-transparent border-ops-border text-ops-text-muted',
            )}>
              {done ? '✓' : n}
            </span>
            <span className="hidden sm:inline">{label}</span>
          </div>
        </div>
      )
    })}
  </div>
)

/* ── Step 1: CSV upload ───────────────────────────────────────── */
const UploadStep = ({ onParsed }) => {
  const inputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)
  const [parseError, setParseError] = useState(null)

  const processFile = useCallback((file) => {
    if (!file) return
    if (!file.name.endsWith('.csv')) {
      setParseError('รองรับเฉพาะไฟล์ .csv เท่านั้น')
      return
    }
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const text = e.target.result
        const { headers, rows } = parseCSV(text)
        if (rows.length === 0) { setParseError('ไม่พบข้อมูลในไฟล์ CSV'); return }
        const validation = validateCSV(headers, rows)
        setParseError(null)
        onParsed({ headers, rows, validation, fileName: file.name })
      } catch (ex) {
        setParseError('ไม่สามารถอ่านไฟล์ได้: ' + ex.message)
      }
    }
    reader.readAsText(file, 'UTF-8')
  }, [onParsed])

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setIsDragging(false)
    processFile(e.dataTransfer.files[0])
  }, [processFile])

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 gap-6">
      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={clsx(
          'w-full max-w-md border-2 border-dashed rounded-2xl p-10 flex flex-col items-center gap-3 cursor-pointer transition-all duration-150',
          isDragging
            ? 'border-ops-accent bg-ops-accent-light scale-[1.01]'
            : 'border-ops-border hover:border-ops-accent/50 hover:bg-ops-bg',
        )}
      >
        <span className="text-4xl">📄</span>
        <div className="text-center">
          <p className="text-sm font-semibold text-ops-text-primary">วางไฟล์ CSV ที่นี่</p>
          <p className="text-xs text-ops-text-muted mt-1">หรือคลิกเพื่อเลือกไฟล์</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={e => processFile(e.target.files[0])}
        />
      </div>

      {parseError && (
        <div className="w-full max-w-md bg-ops-danger-light border border-ops-danger/25 rounded-lg px-4 py-3 text-sm text-ops-danger font-medium">
          ⚠ {parseError}
        </div>
      )}

      {/* CSV schema hint */}
      <div className="w-full max-w-md bg-ops-bg border border-ops-border rounded-xl p-4">
        <p className="text-[11px] font-bold text-ops-text-muted uppercase tracking-wider mb-2">รูปแบบ CSV ที่รองรับ</p>
        <code className="text-[10px] text-ops-text-secondary leading-relaxed block">
          date, planned_time, actual_time, end_time,<br/>
          title, type, status, priority,<br/>
          reporter, location, duration, detail
        </code>
        <p className="text-[10px] text-ops-text-muted mt-2">
          คอลัมน์บังคับ: <span className="font-semibold text-ops-text-secondary">planned_time, title</span>
        </p>
      </div>
    </div>
  )
}

/* ── Step 2: Preview + metadata form ─────────────────────────── */
const ReviewStep = ({ fileName, rows, validation, form, setForm, onBack, onImport, isSubmitting }) => {
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const errorCount  = Object.keys(validation.rowErrors).length
  const schemaErrs  = validation.errors
  const canImport   = !isSubmitting && schemaErrs.length === 0 && errorCount === 0 && form.title && form.date

  const STATUS_LABELS = {
    upcoming: 'upcoming', active: 'active', completed: 'completed',
    delayed: 'delayed', cancelled: 'cancelled',
  }
  const TYPE_COLORS = {
    briefing: 'bg-sky-50 text-sky-700', tactical: 'bg-red-50 text-red-700',
    logistics: 'bg-amber-50 text-amber-700', media: 'bg-purple-50 text-purple-700',
    movement: 'bg-green-50 text-green-700', coordination: 'bg-teal-50 text-teal-700',
    other: 'bg-slate-50 text-slate-600',
  }

  return (
    <div className="flex-1 overflow-y-auto flex flex-col gap-0">
      {/* Schema-level errors */}
      {schemaErrs.length > 0 && (
        <div className="mx-6 mt-5 bg-ops-danger-light border border-ops-danger/25 rounded-lg px-4 py-3">
          {schemaErrs.map((e, i) => (
            <p key={i} className="text-sm text-ops-danger font-medium">⚠ {e.message}</p>
          ))}
        </div>
      )}

      <div className="px-6 pt-5 pb-3 grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Operation metadata form */}
        <div className="space-y-3.5">
          <p className="text-[11px] font-bold text-ops-text-muted uppercase tracking-wider">ข้อมูลปฏิบัติการ</p>

          <Field label="ชื่อปฏิบัติการ" required>
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
            <Field label="วันที่ปฏิบัติการ" required>
              <input
                type="date"
                required
                value={form.date}
                onChange={e => set('date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="ชั้นความลับ">
              <select value={form.classification} onChange={e => set('classification', e.target.value)} className={inputCls}>
                {CLASSIFICATIONS.map(c => <option key={c} value={c} className="bg-ops-card">{c}</option>)}
              </select>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="เวลาเริ่ม">
              <input type="time" value={form.start_time} onChange={e => set('start_time', e.target.value)} className={inputCls} />
            </Field>
            <Field label="เวลาสิ้นสุด">
              <input type="time" value={form.end_time} onChange={e => set('end_time', e.target.value)} className={inputCls} />
            </Field>
          </div>

          <Field label="ผู้บัญชาการ">
            <input type="text" placeholder="เช่น COL. WICHAI SUWAN" value={form.commander} onChange={e => set('commander', e.target.value)} className={inputCls} />
          </Field>

          <Field label="พื้นที่ปฏิบัติการ">
            <input type="text" placeholder="เช่น Bangkok Metropolitan Area" value={form.venue} onChange={e => set('venue', e.target.value)} className={inputCls} />
          </Field>
        </div>

        {/* Event summary */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-bold text-ops-text-muted uppercase tracking-wider">
              เหตุการณ์ที่นำเข้า ({rows.length} รายการ)
            </p>
            {errorCount > 0 && (
              <span className="text-[10px] font-bold text-ops-danger bg-ops-danger-light border border-ops-danger/25 px-2 py-0.5 rounded">
                {errorCount} แถวมีข้อผิดพลาด
              </span>
            )}
            {errorCount === 0 && rows.length > 0 && (
              <span className="text-[10px] font-bold text-ops-success bg-ops-success-light border border-ops-success/25 px-2 py-0.5 rounded">
                ผ่านการตรวจสอบ ✓
              </span>
            )}
          </div>
          <p className="text-[10px] text-ops-text-muted">จาก: <span className="font-mono">{fileName}</span></p>

          <div className="border border-ops-border rounded-xl overflow-hidden flex-1">
            <div className="overflow-auto max-h-64 text-[11px]">
              <table className="w-full min-w-[480px]">
                <thead className="bg-ops-bg sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 font-semibold text-ops-text-muted">#</th>
                    <th className="text-left px-3 py-2 font-semibold text-ops-text-muted">เวลา</th>
                    <th className="text-left px-3 py-2 font-semibold text-ops-text-muted">ชื่อเหตุการณ์</th>
                    <th className="text-left px-3 py-2 font-semibold text-ops-text-muted">ประเภท</th>
                    <th className="text-left px-3 py-2 font-semibold text-ops-text-muted">สถานะ</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const rowErrs = validation.rowErrors[row._rowIndex]
                    return (
                      <tr
                        key={i}
                        className={clsx(
                          'border-t border-ops-border/40 transition-colors',
                          rowErrs ? 'bg-red-50' : i % 2 === 0 ? 'bg-white' : 'bg-ops-bg/30',
                        )}
                      >
                        <td className="px-3 py-1.5 font-mono text-ops-text-muted">{row._rowIndex}</td>
                        <td className="px-3 py-1.5 font-mono text-ops-text-primary font-medium">
                          {row.planned_time || <span className="text-ops-danger">—</span>}
                        </td>
                        <td className="px-3 py-1.5 text-ops-text-primary truncate max-w-[160px]">
                          {row.title || <span className="text-ops-danger italic">ไม่มีชื่อ</span>}
                          {rowErrs && (
                            <div className="text-[9px] text-ops-danger mt-0.5">{rowErrs[0]}</div>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          {row.type ? (
                            <span className={clsx('px-1.5 py-0.5 rounded font-medium', TYPE_COLORS[row.type] || 'bg-slate-50 text-slate-600')}>
                              {row.type}
                            </span>
                          ) : <span className="text-ops-text-muted">—</span>}
                        </td>
                        <td className="px-3 py-1.5 text-ops-text-muted">{row.status || 'upcoming'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 flex gap-3 px-6 py-4 border-t border-ops-border/40 bg-ops-bg/50 mt-auto">
        <button
          type="button"
          onClick={onBack}
          disabled={isSubmitting}
          className="px-5 py-2.5 rounded-xl border border-ops-border/50 text-sm text-ops-text-muted hover:text-ops-text-primary hover:bg-ops-surface transition-all font-semibold disabled:opacity-50"
        >
          ← ย้อนกลับ
        </button>
        <div className="flex-1" />
        {!canImport && (errorCount > 0 || schemaErrs.length > 0) && (
          <p className="text-[11px] text-ops-danger self-center">แก้ไขข้อผิดพลาดในไฟล์ CSV ก่อนนำเข้า</p>
        )}
        <button
          type="button"
          onClick={onImport}
          disabled={!canImport}
          className="px-6 py-2.5 rounded-xl bg-ops-accent/12 border border-ops-accent/40 text-sm text-ops-accent hover:bg-ops-accent/22 transition-all font-bold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isSubmitting ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
              กำลังนำเข้า...
            </>
          ) : (
            <>นำเข้า {rows.length} เหตุการณ์</>
          )}
        </button>
      </div>
    </div>
  )
}

/* ── Main modal ───────────────────────────────────────────────── */
export const ImportOperationModal = ({ onClose }) => {
  const { importOperation } = useApp()
  const { addToast } = useToast()
  const [step, setStep] = useState(1)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const [parsed, setParsed] = useState(null)
  const [form, setForm] = useState({
    title:          '',
    date:           '',
    classification: 'RESTRICTED',
    commander:      '',
    start_time:     '09:00',
    end_time:       '20:00',
    venue:          '',
    status:         'ACTIVE',
  })

  const handleParsed = useCallback((result) => {
    setParsed(result)
    const firstDate = result.rows.find(r => r.date?.trim())?.date?.trim() || ''
    if (firstDate) setForm(f => ({ ...f, date: firstDate }))
    setStep(2)
  }, [])

  const handleImport = useCallback(async () => {
    if (!parsed) return
    setIsSubmitting(true)
    try {
      const events = buildEventPayloads(parsed.rows, form.date)
      const result = await importOperation(form, events)
      addToast(`นำเข้าสำเร็จ: ${result.count} เหตุการณ์`, 'success')
      onClose()
    } catch (ex) {
      addToast(ex.message || 'นำเข้าไม่สำเร็จ', 'error')
      setIsSubmitting(false)
    }
  }, [parsed, form, importOperation, addToast, onClose])

  return (
    <Modal onClose={onClose} maxWidth="max-w-4xl">
      <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/50 to-transparent flex-shrink-0" />

      {/* Header */}
      <div className="flex-shrink-0 flex items-start justify-between px-6 pt-5 pb-4 border-b border-ops-border/40">
        <div>
          <h2 className="font-bold text-ops-text-primary text-base">นำเข้าปฏิบัติการจาก CSV</h2>
          <Steps step={step} />
        </div>
        <ModalClose onClose={onClose} />
      </div>

      {step === 1 && (
        <UploadStep onParsed={handleParsed} />
      )}

      {step === 2 && parsed && (
        <ReviewStep
          fileName={parsed.fileName}
          rows={parsed.rows}
          validation={parsed.validation}
          form={form}
          setForm={setForm}
          onBack={() => setStep(1)}
          onImport={handleImport}
          isSubmitting={isSubmitting}
        />
      )}
    </Modal>
  )
}
