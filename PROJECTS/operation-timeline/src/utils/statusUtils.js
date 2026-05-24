// Status badge configs
export const STATUS_CONFIG = {
  completed: {
    label: 'เสร็จสิ้น',     cls: 'status-success',  icon: '✓',
  },
  active: {
    label: 'กำลังดำเนินการ', cls: 'status-active',   icon: '◉',
  },
  upcoming: {
    label: 'กำหนดการ',      cls: 'status-info',     icon: '○',
  },
  'upcoming-near': {
    label: 'ใกล้ถึงเวลา',    cls: 'status-warning',  icon: '◔',
  },
  resolved: {
    label: 'แก้ไขแล้ว',     cls: 'status-success',  icon: '✓',
  },
  delayed: {
    label: 'ล่าช้า',         cls: 'status-warning',  icon: '⚠',
  },
  cancelled: {
    label: 'ยกเลิก',         cls: 'status-danger',   icon: '✕',
  },
}

// Event type configs
export const TYPE_CONFIG = {
  briefing: {
    label: 'การประชุม',            labelShort: 'ประชุม',
    icon: '📋', nodeColor: '#2dd4bf',
    color: 'text-teal-600',  bg: 'bg-teal-50',  border: 'border-teal-200',
    cardClass: 'card-briefing',
  },
  security: {
    label: 'รักษาความปลอดภัย',      labelShort: 'ปลอดภัย',
    icon: '🛡️', nodeColor: '#f87171',
    color: 'text-red-500',   bg: 'bg-red-50',   border: 'border-red-200',
    cardClass: 'card-security',
  },
  movement: {
    label: 'การเคลื่อนย้าย',        labelShort: 'เดินทาง',
    icon: '🚗', nodeColor: '#60a5fa',
    color: 'text-blue-500',  bg: 'bg-blue-50',  border: 'border-blue-200',
    cardClass: 'card-movement',
  },
  ceremony: {
    label: 'พิธีการ',               labelShort: 'พิธีการ',
    icon: '👑', nodeColor: '#fbbf24',
    color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200',
    cardClass: 'card-ceremony',
  },
  logistics: {
    label: 'การสนับสนุน',           labelShort: 'สนับสนุน',
    icon: '⚙️', nodeColor: '#fb923c',
    color: 'text-orange-500',bg: 'bg-orange-50',border: 'border-orange-200',
    cardClass: 'card-logistics',
  },
  emergency: {
    label: 'เหตุฉุกเฉิน',           labelShort: 'ฉุกเฉิน',
    icon: '🚨', nodeColor: '#ef4444',
    color: 'text-red-600',   bg: 'bg-red-50',   border: 'border-red-300',
    cardClass: 'card-emergency',
  },
}

// Log entry configs
export const LOG_TYPE_CONFIG = {
  alert:     { color: 'text-ops-danger',         icon: '⚡', bg: 'bg-red-50' },
  update:    { color: 'text-ops-info',           icon: '↑',  bg: 'bg-blue-50' },
  resolved:  { color: 'text-ops-success',        icon: '✓',  bg: 'bg-emerald-50' },
  info:      { color: 'text-ops-text-secondary', icon: 'i',  bg: 'bg-slate-50' },
  completed: { color: 'text-ops-success',        icon: '✓',  bg: 'bg-emerald-50' },
}

export const getStatusConfig  = (s) => STATUS_CONFIG[s]  || STATUS_CONFIG.upcoming
export const getTypeConfig    = (t) => TYPE_CONFIG[t]    || TYPE_CONFIG.briefing
export const getLogTypeConfig = (t) => LOG_TYPE_CONFIG[t]|| LOG_TYPE_CONFIG.info
