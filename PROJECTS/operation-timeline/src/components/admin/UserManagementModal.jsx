import { useState, useEffect, useCallback } from 'react'
import { Modal, ModalClose } from '../ui/Modal'
import { fetchUsers, createUser, deactivateUser } from '../../services/eventService'
import clsx from 'clsx'

const ROLES = [
  { value: 'op_admin',    label: 'ผู้ดูแล' },
  { value: 'super_admin', label: 'ผู้ดูแลระบบ' },
]

const inputCls = 'w-full bg-ops-surface border border-ops-border/50 rounded-lg px-3 py-2 text-sm text-ops-text-primary font-mono focus:outline-none focus:border-ops-accent/50 focus:ring-1 focus:ring-ops-accent/20 transition-all placeholder-ops-text-muted'

export const UserManagementModal = ({ onClose }) => {
  const [users,   setUsers]   = useState([])
  const [loading, setLoading] = useState(true)
  const [form,    setForm]    = useState({ name: '', pin: '', role: 'op_admin', operation_scope: '*' })
  const [adding,  setAdding]  = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetchUsers().then(setUsers).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = async (e) => {
    e.preventDefault()
    if (form.pin.length < 4) return
    setAdding(true)
    try {
      await createUser(form)
      setForm({ name: '', pin: '', role: 'op_admin', operation_scope: '*' })
      load()
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (id, name) => {
    if (!window.confirm(`ปิดการใช้งาน ${name}?`)) return
    await deactivateUser(id)
    load()
  }

  return (
    <Modal onClose={onClose}>
      <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/40 to-transparent flex-shrink-0" />
      <div className="flex-shrink-0 flex items-center justify-between px-6 pt-5 pb-4 border-b border-ops-border/40">
        <div>
          <h2 className="font-bold text-ops-text-primary text-base">จัดการผู้ใช้</h2>
          <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">เฉพาะผู้ดูแลระบบ</p>
        </div>
        <ModalClose onClose={onClose} />
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
        {/* Add user form */}
        <form onSubmit={handleAdd} className="space-y-3 p-4 rounded-xl bg-ops-surface border border-ops-border/50">
          <p className="text-xs font-bold text-ops-text-primary">เพิ่มผู้ใช้ใหม่</p>
          <input
            type="text" required placeholder="ชื่อ"
            value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            className={inputCls}
          />
          <input
            type="password" required placeholder="PIN (4 หลัก)" maxLength={8} minLength={4}
            value={form.pin} onChange={e => setForm(f => ({ ...f, pin: e.target.value.replace(/\D/g,'') }))}
            className={inputCls}
          />
          <input
            type="text" placeholder="ขอบเขตปฏิบัติการ (* = ทั้งหมด, หรือ OP-xxx,OP-yyy)"
            value={form.operation_scope} onChange={e => setForm(f => ({ ...f, operation_scope: e.target.value }))}
            className={inputCls}
          />
          <select
            value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
            className={inputCls}
          >
            {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
          <button
            type="submit" disabled={adding || form.pin.length < 4}
            className="w-full py-2 rounded-lg bg-ops-accent/12 border border-ops-accent/40 text-sm text-ops-accent hover:bg-ops-accent/22 transition-all font-bold disabled:opacity-60"
          >
            {adding ? 'กำลังเพิ่ม...' : 'เพิ่มผู้ใช้'}
          </button>
        </form>

        {/* User list */}
        <div>
          <p className="text-xs font-bold text-ops-text-primary mb-2">ผู้ใช้ปัจจุบัน ({users.length})</p>
          {loading ? (
            <div className="flex justify-center py-4">
              <span className="w-5 h-5 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
            </div>
          ) : users.length === 0 ? (
            <p className="text-xs text-ops-text-muted text-center py-4">ยังไม่มีผู้ใช้</p>
          ) : (
            <div className="space-y-2">
              {users.map(u => (
                <div key={u.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border border-ops-border/50">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ops-text-primary truncate">{u.name}</p>
                    <p className="text-[11px] text-ops-text-muted font-mono">
                      ขอบเขต: {u.operation_scope || '*'}
                    </p>
                    <span className={clsx(
                      'text-[9px] font-bold px-1.5 py-0.5 rounded tracking-wide uppercase mt-0.5 inline-block',
                      u.role === 'super_admin'
                        ? 'text-ops-accent bg-ops-accent-light border border-ops-accent/20'
                        : 'text-ops-success bg-ops-success-light border border-ops-success/20',
                    )}>
                      {u.role === 'super_admin' ? 'ผู้ดูแลระบบ' : 'ผู้ดูแล'}
                    </span>
                  </div>
                  <button
                    onClick={() => handleRemove(u.id, u.name)}
                    className="flex-shrink-0 text-[11px] font-medium text-ops-danger hover:bg-ops-danger-light border border-ops-danger/20 hover:border-ops-danger/40 px-3 py-1.5 rounded-lg transition-all"
                  >
                    ปิดใช้
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-shrink-0 px-6 py-4 border-t border-ops-border/40">
        <button onClick={onClose} className="w-full py-2.5 rounded-xl border border-ops-border/50 text-sm text-ops-text-muted hover:text-ops-text-primary hover:bg-ops-surface transition-all font-semibold">
          ปิด
        </button>
      </div>
    </Modal>
  )
}
