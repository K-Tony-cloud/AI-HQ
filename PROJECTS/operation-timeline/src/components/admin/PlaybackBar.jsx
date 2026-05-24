import { useApp } from '../../context/AppContext'
import clsx from 'clsx'

export const PlaybackBar = () => {
  const { isAdminMode, getSnapshots, playbackIndex, setPlaybackIndex, isMockMode } = useApp()
  const snapshots = getSnapshots()

  if (!isAdminMode || isMockMode || snapshots.length < 2) return null

  const isLive       = playbackIndex === -1
  const currentSnap  = isLive ? null : snapshots[playbackIndex]
  const label        = isLive
    ? 'สด'
    : new Date(currentSnap?.ts).toLocaleTimeString('th-TH', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })

  return (
    <div className="flex-shrink-0 bg-white border-t border-ops-border px-4 py-2 flex items-center gap-3">
      <span className="ops-label flex-shrink-0">เล่นซ้ำ</span>
      <button
        onClick={() => setPlaybackIndex(-1)}
        className={clsx(
          'text-[10px] font-bold px-2 py-0.5 rounded border transition-all flex-shrink-0',
          isLive
            ? 'bg-ops-danger text-white border-ops-danger'
            : 'bg-ops-bg border-ops-border text-ops-text-muted hover:bg-white',
        )}
      >
        {isLive ? '● สด' : '● กลับสด'}
      </button>
      <input
        type="range"
        min={0}
        max={snapshots.length - 1}
        value={isLive ? snapshots.length - 1 : playbackIndex}
        onChange={e => setPlaybackIndex(Number(e.target.value))}
        className="flex-1 accent-ops-accent h-1"
      />
      <span className="font-mono text-[10px] text-ops-text-muted flex-shrink-0 w-16 text-right tabular-nums">
        {label}
      </span>
      <span className="text-[10px] text-ops-text-muted flex-shrink-0">
        {snapshots.length} เฟรม
      </span>
    </div>
  )
}
