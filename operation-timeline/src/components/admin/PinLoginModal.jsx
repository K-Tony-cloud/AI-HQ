import { useState } from 'react'
import clsx from 'clsx'

const CORRECT_PIN = import.meta.env.VITE_ADMIN_PIN || '1234'

export const PinLoginModal = ({ onSuccess, onClose }) => {
  const [pin,      setPin]      = useState('')
  const [shaking,  setShaking]  = useState(false)
  const [errMsg,   setErrMsg]   = useState('')

  const handleDigit = (d) => {
    if (pin.length >= 4) return
    const next = pin + d
    setPin(next)
    setErrMsg('')
    if (next.length === 4) {
      // Auto-confirm when 4 digits entered
      if (next === CORRECT_PIN) {
        onSuccess()
      } else {
        setShaking(true)
        setErrMsg('PIN ไม่ถูกต้อง')
        setTimeout(() => {
          setShaking(false)
          setPin('')
        }, 400)
      }
    }
  }

  const handleClear = () => {
    setPin(prev => prev.slice(0, -1))
    setErrMsg('')
  }

  const handleConfirm = () => {
    if (pin.length < 4) return
    if (pin === CORRECT_PIN) {
      onSuccess()
    } else {
      setShaking(true)
      setErrMsg('PIN ไม่ถูกต้อง')
      setTimeout(() => {
        setShaking(false)
        setPin('')
      }, 400)
    }
  }

  const pad = [
    ['1','2','3'],
    ['4','5','6'],
    ['7','8','9'],
    [null,'0',null],
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/65 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-xs bg-ops-card border border-ops-border rounded-2xl shadow-2xl overflow-hidden animate-slide-down">
        <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/40 to-transparent" />
        <div className="p-6">
          {/* Title */}
          <div className="text-center mb-5">
            <h2 className="font-bold text-ops-text-primary text-base">ยืนยันตัวตนผู้ดูแล</h2>
            <p className="text-[11px] text-ops-text-muted mt-1">กรอก PIN เพื่อเข้าสู่โหมดผู้ดูแล</p>
          </div>

          {/* PIN dots */}
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

          {/* Error message */}
          <div className="h-5 flex items-center justify-center mb-3">
            {errMsg && (
              <p className="text-xs text-ops-danger font-medium">{errMsg}</p>
            )}
          </div>

          {/* Number pad */}
          <div className="space-y-2">
            {pad.map((row, ri) => (
              <div key={ri} className="grid grid-cols-3 gap-2">
                {row.map((cell, ci) => {
                  if (cell === null) {
                    // First null = clear (←), last null = confirm (✓)
                    const isClear   = ci === 0
                    const isConfirm = ci === 2
                    if (isClear) {
                      return (
                        <button
                          key="clear"
                          onClick={handleClear}
                          disabled={pin.length === 0}
                          className="h-12 rounded-xl bg-ops-bg border border-ops-border text-ops-danger font-bold text-lg hover:bg-white transition-all disabled:opacity-30"
                          aria-label="ลบ"
                        >
                          ←
                        </button>
                      )
                    }
                    if (isConfirm) {
                      return (
                        <button
                          key="confirm"
                          onClick={handleConfirm}
                          disabled={pin.length < 4}
                          className="h-12 rounded-xl bg-ops-accent text-white font-bold text-lg hover:bg-sky-500 transition-all disabled:opacity-30"
                          aria-label="ยืนยัน"
                        >
                          ✓
                        </button>
                      )
                    }
                  }
                  return (
                    <button
                      key={cell}
                      onClick={() => handleDigit(cell)}
                      disabled={pin.length >= 4}
                      className="h-12 rounded-xl bg-ops-bg border border-ops-border font-semibold text-ops-text-primary text-base hover:bg-white transition-all disabled:opacity-40"
                    >
                      {cell}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>

          {/* Cancel */}
          <button
            onClick={onClose}
            className="w-full mt-4 py-2 text-xs text-ops-text-muted hover:text-ops-text-primary transition-colors"
          >
            ยกเลิก
          </button>
        </div>
      </div>
    </div>
  )
}
