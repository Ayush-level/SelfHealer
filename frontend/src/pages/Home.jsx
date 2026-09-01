import React, { useEffect, useState } from 'react'
import { getHealth } from '../api/client.js'

const STATUS_COLOR = { healthy: 'green', unhealthy: 'red', unreachable: '#aaa' }

export default function Home() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(err => setError(err.message))
  }, [])

  if (error) return <p style={{ color: 'red' }}>Could not reach proxy: {error}</p>
  if (!health) return <p>Loading…</p>

  return (
    <div>
      <h1>Health Overview</h1>
      <table>
        <thead><tr><th>Service</th><th>Status</th></tr></thead>
        <tbody>
          {Object.entries(health.services || {}).map(([svc, info]) => (
            <tr key={svc}>
              <td>{svc}</td>
              <td style={{ color: STATUS_COLOR[info.status] ?? 'inherit' }}>{info.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
