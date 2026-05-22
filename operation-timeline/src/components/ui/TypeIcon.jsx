import { getTypeConfig } from '../../utils/statusUtils'
import clsx from 'clsx'

export const TypeIcon = ({ type, size = 'md', showLabel = false }) => {
  const cfg = getTypeConfig(type)
  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 rounded-md border font-medium',
      cfg.color, cfg.bg, cfg.border,
      size === 'sm' && 'text-[10px] px-1.5 py-0.5',
      size === 'md' && 'text-xs px-2 py-0.5',
    )}>
      <span className="leading-none">{cfg.icon}</span>
      {showLabel && <span>{cfg.labelShort}</span>}
    </span>
  )
}
