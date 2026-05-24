import clsx from 'clsx'

export const LoadingSpinner = ({ message = 'กำลังโหลด...', size = 'md', className }) => {
  const ring = size === 'sm'
    ? 'w-5 h-5 border-[2px]'
    : size === 'lg'
      ? 'w-12 h-12 border-[3px]'
      : 'w-8 h-8 border-2'

  return (
    <div className={clsx('flex flex-col items-center justify-center gap-3', className)}>
      <div className={clsx(
        ring,
        'rounded-full border-ops-accent/20 border-t-ops-accent animate-spin',
      )} />
      {message && (
        <p className={clsx(
          'font-medium text-ops-text-secondary',
          size === 'sm' ? 'text-xs' : 'text-sm',
        )}>
          {message}
        </p>
      )}
    </div>
  )
}
