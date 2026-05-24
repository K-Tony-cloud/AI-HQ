import { getStatusConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

export const StatusBadge = ({ status, size = 'sm', showIcon = true }) => {
  const cfg = getStatusConfig(status)
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 font-semibold rounded-full border whitespace-nowrap',
      cfg.cls,
      size === 'xs' && 'text-[9px] px-1.5 py-0.5 leading-none',
      size === 'sm' && 'text-[10px] px-2 py-0.5',
      size === 'md' && 'text-xs px-2.5 py-1',
    )}>
      {showIcon && <span className="font-mono leading-none">{cfg.icon}</span>}
      <span className="tracking-wide">{cfg.label}</span>
    </span>
  )
}
