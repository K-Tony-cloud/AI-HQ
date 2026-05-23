// Google Apps Script Web App adapter skeleton
// Set VITE_SHEETS_URL in .env.local to your deployed script URL

const SCRIPT_URL = import.meta.env.VITE_SHEETS_URL || ''

export const sheetsGet = async (action, params = {}) => {
  if (!SCRIPT_URL) throw new Error('VITE_SHEETS_URL not configured')
  const url = new URL(SCRIPT_URL)
  url.searchParams.set('action', action)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
  const res = await fetch(url.toString())
  return res.json()
}

export const sheetsPost = async (action, payload = {}) => {
  if (!SCRIPT_URL) throw new Error('VITE_SHEETS_URL not configured')
  const res = await fetch(SCRIPT_URL, {
    method: 'POST',
    body: JSON.stringify({ action, ...payload }),
  })
  return res.json()
}
