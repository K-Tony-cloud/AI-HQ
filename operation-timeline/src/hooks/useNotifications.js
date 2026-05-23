import { useRef, useCallback } from 'react'

function playBeep(frequency = 880, duration = 200, volume = 0.3, type = 'sine') {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = frequency
    osc.type = type
    gain.gain.setValueAtTime(volume, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration / 1000)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + duration / 1000)
  } catch (_) {}
}

export const useNotifications = () => {
  const permissionRef = useRef(
    typeof Notification !== 'undefined' ? Notification.permission : 'denied',
  )

  const requestPermission = useCallback(async () => {
    if (typeof Notification === 'undefined') return false
    if (Notification.permission === 'granted') return true
    const result = await Notification.requestPermission()
    permissionRef.current = result
    return result === 'granted'
  }, [])

  const notify = useCallback((title, body, urgent = false) => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      new Notification(title, {
        body,
        icon: '/favicon.ico',
        badge: '/favicon.ico',
        tag: title,
      })
    }
    if (urgent) {
      playBeep(1320, 150, 0.4, 'square')
      setTimeout(() => playBeep(1320, 150, 0.4, 'square'), 200)
    } else {
      playBeep(880, 200, 0.25, 'sine')
    }
  }, [])

  return { requestPermission, notify }
}
