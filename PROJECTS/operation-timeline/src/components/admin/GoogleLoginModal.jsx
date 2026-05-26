import { useState, useEffect, useRef } from 'react'
import { Modal } from '../ui/Modal'
import { useAuth } from '../../context/AuthContext'
import clsx from 'clsx'

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

export const GoogleLoginModal = ({ onClose }) => {
  const { login } = useAuth()
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const btnRef = useRef(null)

  useEffect(() => {
    if (!CLIENT_ID || !window.google) return
    window.google.accounts.id.initialize({
      client_id: CLIENT_ID,
      callback: handleCredential,
      use_fedcm_for_prompt: false,
    })
    window.google.accounts.id.renderButton(btnRef.current, {
      theme: 'outline',
      size: 'large',
      width: '100%',
      text: 'signin_with',
      locale: 'th',
    })
  }, [])

  const handleCredential = async ({ credential }) => {
    setLoading(true)
    setError('')
    try {
      await login(credential)
      onClose()
    } catch (ex) {
      setError(ex.message || 'เข้าสู่ระบบไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }

  if (!CLIENT_ID) {
    return (
      <Modal onClose={onClose} maxWidth="max-w-sm">
        <div className="p-6 text-center">
          <p className="text-sm text-ops-danger font-medium">VITE_GOOGLE_CLIENT_ID ยังไม่ได้ตั้งค่า</p>
          <p className="text-xs text-ops-text-muted mt-1">กรุณาตั้งค่าใน .env.local แล้วรีสตาร์ท</p>
        </div>
      </Modal>
    )
  }

  return (
    <Modal onClose={onClose} maxWidth="max-w-xs">
      <div className="h-px bg-gradient-to-r from-transparent via-ops-accent/40 to-transparent flex-shrink-0" />
      <div className="p-6">
        <div className="text-center mb-6">
          <div className="w-10 h-10 rounded-xl bg-ops-accent/10 border border-ops-accent/20 flex items-center justify-center mx-auto mb-3">
            <span className="text-lg">🔐</span>
          </div>
          <h2 className="font-bold text-ops-text-primary text-base">เข้าสู่ระบบผู้ดูแล</h2>
          <p className="text-[11px] text-ops-text-muted mt-1">ใช้บัญชี Google ที่ได้รับสิทธิ์เท่านั้น</p>
        </div>

        {loading ? (
          <div className="flex justify-center py-4">
            <span className="w-6 h-6 border-2 border-ops-accent/40 border-t-ops-accent rounded-full animate-spin" />
          </div>
        ) : (
          <div ref={btnRef} className="flex justify-center" />
        )}

        {error && (
          <p className="mt-3 text-xs text-center text-ops-danger font-medium">{error}</p>
        )}

        <button
          onClick={onClose}
          className="w-full mt-4 py-2 text-xs text-ops-text-muted hover:text-ops-text-primary transition-colors"
        >
          ยกเลิก
        </button>
      </div>
    </Modal>
  )
}
