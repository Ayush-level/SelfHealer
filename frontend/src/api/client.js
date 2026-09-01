// All API calls go through the Flask proxy at /api/*.
// During development, Vite proxies /api → http://localhost:5000 (see vite.config.js).

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`${options.method || 'GET'} ${path} → ${res.status}`)
  return res.json()
}

export const getConfig    = ()       => request('/config')
export const saveConfig   = (data)   => request('/config', { method: 'POST', body: JSON.stringify(data) })
export const getHealth    = ()       => request('/health')
export const getTelemetry = ()       => request('/telemetry/summary')
export const getTools     = ()       => request('/tools')
export const triggerRCA   = (window) => request('/rca/trigger', { method: 'POST', body: JSON.stringify(window) })
export const getRCAResults = ()      => request('/rca/results')
export const approveRCA   = (id)     => request(`/rca/${id}/approve`, { method: 'POST' })
export const rejectRCA    = (id)     => request(`/rca/${id}/reject`,  { method: 'POST' })
