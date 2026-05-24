/**
 * realtime.js — polling-based realtime update mechanism
 *
 * Google Sheets does not support WebSockets or SSE, so we poll
 * at a configurable interval. In mock mode, polling is a no-op.
 *
 * Usage:
 *   const poller = createPoller(fetchEvents, 30000)
 *   const unsub  = poller.subscribe(({ data, error }) => ...)
 *   poller.start()
 *   // later:
 *   poller.stop()
 *   unsub()
 */

/**
 * Creates a polling manager.
 * @param {() => Promise<any>} fetchFn  Async function that returns fresh data
 * @param {number}             interval Polling interval in milliseconds
 */
export const createPoller = (fetchFn, interval = 30000) => {
  let timerId    = null
  let listeners  = []
  let running    = false

  const notify = (payload) => listeners.forEach(fn => fn(payload))

  const poll = async () => {
    try {
      const data = await fetchFn()
      notify({ data, error: null })
    } catch (ex) {
      notify({ data: null, error: ex.message || 'Poll error' })
    }
  }

  return {
    /** Immediately polls once, then starts the interval. */
    start() {
      if (running) return
      running = true
      poll()
      timerId = setInterval(poll, interval)
    },

    /** Stops polling. */
    stop() {
      running = false
      clearInterval(timerId)
      timerId = null
    },

    /** Forces an immediate out-of-band poll. */
    refresh: poll,

    /** Subscribe to poll results. Returns an unsubscribe function. */
    subscribe(fn) {
      listeners = [...listeners, fn]
      return () => { listeners = listeners.filter(l => l !== fn) }
    },
  }
}
