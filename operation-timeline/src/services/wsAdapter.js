/**
 * wsAdapter.js — WebSocket migration scaffold
 *
 * When a WebSocket server is available, swap createPoller() for createWsPoller()
 * in AppContext. Both implement the same interface: { start, stop, refresh, subscribe }.
 *
 * Migration steps:
 *   1. Set VITE_WS_URL in .env.local
 *   2. Replace createPoller import in AppContext with createWsPoller
 *   3. Update server to emit { action: 'events', data: [...] } messages
 */

import { createPoller } from './realtime'

const WS_URL = import.meta.env.VITE_WS_URL || null

export const createWsPoller = (onFallback, interval = 30000) => {
  // If no WS_URL configured, fall back to HTTP polling
  if (!WS_URL) {
    console.warn('[wsAdapter] VITE_WS_URL not set — using HTTP polling fallback')
    return createPoller(onFallback, interval)
  }

  let socket = null
  let listeners = []
  let reconnectTimer = null
  const notify = (payload) => listeners.forEach(fn => fn(payload))

  const connect = () => {
    socket = new WebSocket(WS_URL)

    socket.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.action === 'events') notify({ data: msg.data, error: null })
      } catch (_) {}
    }

    socket.onerror = () => notify({ data: null, error: 'WebSocket error' })

    socket.onclose = () => {
      // Reconnect after delay
      reconnectTimer = setTimeout(connect, 5000)
    }
  }

  return {
    start()   { connect() },
    stop()    { socket?.close(); clearTimeout(reconnectTimer) },
    refresh() { socket?.send(JSON.stringify({ action: 'refresh' })) },
    subscribe(fn) {
      listeners = [...listeners, fn]
      return () => { listeners = listeners.filter(l => l !== fn) }
    },
  }
}
