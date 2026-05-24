export const ROLES = {
  viewer: {
    canEdit:        false,
    canAddEvent:    false,
    canAddLog:      false,
    canViewAudit:   false,
    canDeleteEvent: false,
  },
  admin: {
    canEdit:        true,
    canAddEvent:    true,
    canAddLog:      true,
    canViewAudit:   true,
    canDeleteEvent: false, // reserved
  },
}

export const getPermissions = (role) => ROLES[role] ?? ROLES.viewer
