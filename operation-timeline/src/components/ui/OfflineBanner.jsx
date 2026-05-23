import { useNetworkStatus } from '../../hooks/useNetworkStatus'

export const OfflineBanner = () => {
  const isOnline = useNetworkStatus()
  if (isOnline) return null
  return (
    <div className="flex-shrink-0 flex items-center gap-2 bg-amber-50 border-b border-amber-200 px-4 py-2 text-xs font-semibold text-amber-800">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
      ไม่มีการเชื่อมต่ออินเทอร์เน็ต — ข้อมูลแสดงอยู่จากแคชล่าสุด
    </div>
  )
}
