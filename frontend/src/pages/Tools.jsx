import React, { useEffect, useState } from 'react'
import { getTools } from '../api/client.js'

export default function Tools() {
  const [tools, setTools] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getTools()
      .then(setTools)
      .catch(err => setError(err.message))
  }, [])

  if (error) return <p style={{ color: 'red' }}>Error: {error}</p>
  if (!tools) return <p>Loading…</p>
  if (!tools.length) return <p>No tools enabled. Configure them in <a href="/setup">Setup</a>.</p>

  return (
    <div>
      <h1>Tool Links</h1>
      <ul>
        {tools.map(t => (
          <li key={t.name}>
            <a href={t.url} target="_blank" rel="noopener noreferrer">{t.name}</a>
            {t.description && <span style={{ marginLeft: '0.5rem', color: '#666' }}>— {t.description}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
