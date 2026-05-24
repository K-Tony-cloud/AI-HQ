import clsx from 'clsx'

export const ErrorBanner = ({ message, onRetry, className }) => (
  <div className={clsx(
    'flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3 animate-fade-in',
    className,
  )}>
    <span className="text-ops-danger text-base flex-shrink-0">⚠</span>
    <p className="text-sm text-ops-danger flex-1 leading-snug">{message}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="flex-shrink-0 text-xs font-bold text-ops-danger border border-ops-danger/30 rounded-lg px-3 py-1.5 hover:bg-red-100 transition-colors"
      >
        ลองใหม่
      </button>
    )}
  </div>
)
