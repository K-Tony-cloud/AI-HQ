import { useCurrentTime } from '../../hooks/useCurrentTime'

export const NowIndicator = ({ containerRef }) => {
  const { timeStr, percent } = useCurrentTime(5000)

  if (percent <= 0 || percent >= 100) return null

  return (
    <div
      className="absolute left-0 right-0 pointer-events-none z-20"
      style={{ top: `${percent}%` }}
    >
      {/* Glow line */}
      <div className="now-line-animated h-px bg-ops-now w-full relative">
        {/* Time label */}
        <div className="absolute left-8 -top-3.5 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-ops-now animate-blink flex-shrink-0" />
          <span className="font-mono text-[11px] font-bold text-ops-now glow-text-now bg-ops-bg/90 px-1.5 py-0.5 rounded border border-ops-now/30">
            NOW {timeStr}
          </span>
        </div>

        {/* Right arrow indicator */}
        <div className="absolute right-2 -top-2.5">
          <span className="font-mono text-[9px] text-ops-now/60">▶</span>
        </div>
      </div>
    </div>
  )
}
