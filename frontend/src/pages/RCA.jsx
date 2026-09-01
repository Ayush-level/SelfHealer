import React, { useEffect, useState, useCallback } from 'react'
import { getRCAResults, triggerRCA, approveRCA, rejectRCA } from '../api/client.js'

const STATUS_COLOR = { pending: '#888', approved: 'green', rejected: 'red' }

export default function RCA() {
  const [results, setResults] = useState([])
  const [error, setError] = useState('')
  const [triggering, setTriggering] = useState(false)

  const load = useCallback(() => {
    getRCAResults()
      .then(r => setResults(r.results ?? r))
      .catch(err => setError(err.message))
  }, [])

  useEffect(() => { load() }, [load])

  async function handleTrigger() {
    setTriggering(true)
    setError('')
    try {
      const now = Date.now() / 1000
      await triggerRCA({ start_time: now - 300, end_time: now })
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setTriggering(false)
    }
  }

  async function handleApprove(id) {
    await approveRCA(id).catch(err => setError(err.message))
    load()
  }

  async function handleReject(id) {
    await rejectRCA(id).catch(err => setError(err.message))
    load()
  }

  return (
    <div>
      <h1>Root Cause Analysis</h1>
      <button onClick={handleTrigger} disabled={triggering}>
        {triggering ? 'Analyzing…' : 'Analyze last 5 minutes'}
      </button>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {results.length === 0 && !error && <p style={{ marginTop: '1rem' }}>No results yet.</p>}

      {results.map(r => (
        <div key={r.id} style={{ border: '1px solid #ddd', borderRadius: 4, padding: '1rem', marginTop: '1rem' }}>
          <p><strong>Cause:</strong> {r.cause}</p>
          <p><strong>Confidence:</strong> {(r.confidence * 100).toFixed(0)}%</p>
          <p><strong>Status:</strong> <span style={{ color: STATUS_COLOR[r.status] }}>{r.status}</span></p>
          <details>
            <summary>Evidence</summary>
            <pre style={{ fontSize: '0.85em', background: '#f4f4f4', padding: '0.5rem' }}>
              {JSON.stringify(r.evidence, null, 2)}
            </pre>
          </details>
          {r.playbook && (
            <details>
              <summary>Playbook</summary>
              <pre style={{ fontSize: '0.85em', background: '#f4f4f4', padding: '0.5rem' }}>{r.playbook}</pre>
            </details>
          )}
          {r.status === 'pending' && (
            <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
              <button onClick={() => handleApprove(r.id)}>✓ Approve</button>
              <button onClick={() => handleReject(r.id)}>✗ Reject</button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
