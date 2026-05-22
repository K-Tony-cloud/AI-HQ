import { useState, useEffect } from 'react'
import { getCurrentTimeString, getCurrentTimePercent } from '../utils/timeUtils'

export const useCurrentTime = (interval = 10000) => {
  const [timeStr, setTimeStr] = useState(getCurrentTimeString())
  const [percent, setPercent] = useState(getCurrentTimePercent())
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const update = () => {
      setTimeStr(getCurrentTimeString())
      setPercent(getCurrentTimePercent())
      setTick(t => t + 1)
    }

    const id = setInterval(update, interval)
    return () => clearInterval(id)
  }, [interval])

  return { timeStr, percent, tick }
}
