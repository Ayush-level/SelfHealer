import React, { useEffect, useState } from 'react'
import { getTelemetry } from '../api/client.js'

export default function Telemetry() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getTelemetry()
      .then(setData)
      .catch(err => setError(err.message))
  }, [])

  if (error) return <p style={{ color: 'red' }}>Error: {error}</p>
  if (!data) return <p>Loading…</p>

  return (
    <div>
      <h1>Telemetry Analysis</h1>
      <section>
        <h2>Services seen</h2>
        <ul>
          {(data.services || []).map(s => <li key={s}>{s}</li>)}
        </ul>
      </section>
      <section>
        <h2>Recent volume (last hour)</h2>
        <p>Traces: {data.trace_count ?? '—'}</p>
        <p>Logs: {data.log_count ?? '—'}</p>
      </section>
      <section>
        <h2>Error rate trend</h2>
        <p>{data.error_rate_pct != null ? `${data.error_rate_pct.toFixed(1)} %` : '—'}</p>
      </section>
    </div>
  )
}
