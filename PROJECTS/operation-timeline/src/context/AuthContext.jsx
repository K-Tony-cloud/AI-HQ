import { createContext, useContext, useState, useCallback } from 'react'
import { loginGoogle as apiLoginGoogle, logoutUser as apiLogout } from '../services/sheetsAdapter'

const AUTH_STORAGE_KEY = 'ops_auth_session'
const AuthContext = createContext(null)

function loadSession() {
  try {
    const raw = sessionStorage.getItem(AUTH_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(loadSession)

  const login = useCallback(async (credential) => {
    const result = await apiLoginGoogle(credential)
    if (!result.ok) throw new Error(result.error || 'Login failed')
    const session = { role: result.role, token: result.token, name: result.name, email: result.email }
    sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
    setUser(session)
    return session
  }, [])

  const logout = useCallback(async () => {
    if (user?.token) {
      try { await apiLogout(user.token) } catch (_) {}
    }
    sessionStorage.removeItem(AUTH_STORAGE_KEY)
    setUser(null)
  }, [user])

  const isOpAdmin    = user?.role === 'op_admin' || user?.role === 'super_admin'
  const isSuperAdmin = user?.role === 'super_admin'

  return (
    <AuthContext.Provider value={{ user, login, logout, isOpAdmin, isSuperAdmin }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
