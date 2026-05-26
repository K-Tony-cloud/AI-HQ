import { useState } from 'react'
import { Modal } from '../ui/Modal'
import { useAuth } from '../../context/AuthContext'
import clsx from 'clsx'

export const GoogleLoginModal = ({ onClose }) => {
  const { login } = useAuth()
  const [pin,      setPin]      = useState('')
  const [shaking,  setShaking]  = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [errMsg,   setErrMsg]   = useState('')

  const submit = async (value) => {
    if (loading) return
    setLoading(true)
    setErrMsg('')
    try {
      await login(value)
      onClose()
    } catch (ex) {
      setShaking(true)
      setErrMsg(ex.message || 'PIN ไม่ถูกต้อง')
      setTimeout(() => { setShaking(false); setPin('') }, 400)
    } finally {
      setLoading(false)
    }
  }

  const handleDigit = (d) => {
    if (pin.length >= 4 || loading) return
    const next = pin + d
    setPin(next)
    setErrMsg('')
    if (next.length === 4) submit(next)
  }

  const handleClear = () => { setPin(prev => prev.slice(0, -1)); setErrMsg('') }

  const pad = [
    ['1','2','3'],
    ['4','5','6'],
    ['7','8','9'],
    [null,'0',null],
  ]

  return (
    <Modal onClose={onClose} maxWidth="max-w-xs">
      <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/40 to-transparent flex-shrink-0" />
      <div className="p-6">
        <div className="text-center mb-5">
          <h2 className="font-bold text-ops-text-primary text-base">ยืนยันตัวตนผู้ดูแล</h2>
          <p className="text-[11px] text-ops-text-muted mt-1">กรอก PIN เพื่อเข้าสู่ระบบ</p>
        </div>

        <div className={clsx('flex justify-center gap-3 mb-4', shaking && 'animate-shake')}>
          {[0,1,2,3].map(i => (
            <span
              key={i}
              className={clsx(
                'w-3.5 h-3.5 rounded-full border-2 transition-all duration-150',
                i < pin.length
                  ? 'bg-ops-accent border-ops-accent'
                  : 'bg-transparent border-ops-border',
              )}
            />
          ))}
        </div>

        <div className="h-5 flex items-center justify-center mb-3">
          {errMsg && <p className="text-xs text-ops-danger font-medium">{errMsg}</p>}
        </div>

        {loading ? (
          <div className="flex justify-center py-6">
            <span className="w-6 h-6 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-2">
            {pad.map((row, ri) => (
              <div key={ri} className="grid grid-cols-3 gap-2">
                {row.map((cell, ci) => {
                  if (cell === null) {
                    if (ci === 0) return (
                      <button key="clear" onClick={handleClear} disabled={pin.length === 0}
                        className="h-12 rounded-xl bg-ops-bg border border-ops-border text-ops-danger font-bold text-lg hover:bg-white transition-all disabled:opacity-30"
                        aria-label="ลบ">←</button>
                    )
                    if (ci === 2) return (
                      <button key="confirm" onClick={() => submit(pin)} disabled={pin.length < 4}
                        className="h-12 rounded-xl bg-ops-accent text-white font-bold text-lg hover:bg-sky-500 transition-all disabled:opacity-30"
                        aria-label="ยืนยัน">✓</button>
                    )
                  }
                  return (
                    <button key={cell} onClick={() => handleDigit(cell)} disabled={pin.length >= 4}
                      className="h-12 rounded-xl bg-ops-bg border border-ops-border font-semibold text-ops-text-primary text-base hover:bg-white transition-all disabled:opacity-40">
                      {cell}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        )}

        <button onClick={onClose} className="w-full mt-4 py-2 text-xs text-ops-text-muted hover:text-ops-text-primary transition-colors">
          ยกเลิก
        </button>
      </div>
    </Modal>
  )
}
