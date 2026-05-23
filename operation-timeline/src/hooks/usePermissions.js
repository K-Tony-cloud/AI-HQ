import { useApp } from '../context/AppContext'
import { getPermissions } from '../utils/permissions'

export const usePermissions = () => {
  const { isAdminMode } = useApp()
  return getPermissions(isAdminMode ? 'admin' : 'viewer')
}
