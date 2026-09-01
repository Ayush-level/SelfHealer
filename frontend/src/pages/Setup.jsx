import React, { useState } from 'react'
import { saveConfig } from '../api/client.js'

const DEFAULTS = {
  storage_mode: 'prometheus',
  enable_grafana: true,
  grafana_port: 3000,
  enable_prometheus_ui: true,
  prometheus_port: 9090,
  enable_signoz: false,
  signoz_port: 8080,
  llm_provider: 'openai',
  llm_api_key: '',
  rca_trigger_mode: 'manual',
  rca_interval_minutes: 15,
}

export default function Setup({ onSaved }) {
  const [form, setForm] = useState(DEFAULTS)
  const [saved, setSaved] = useState(false)
  const [command, setCommand] = useState('')
  const [error, setError] = useState('')

  function set(key, value) {
    setForm(f => ({ ...f, [key]: value }))
  }

  async function handleSave(e) {
    e.preventDefault()
    setError('')
    try {
      await saveConfig(form)
      const cmd = buildCommand(form)
      setCommand(cmd)
      setSaved(true)
      if (onSaved) onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h1>Setup Wizard</h1>
      <p>Configure the stack, then run the generated command to start it.</p>
      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: 480 }}>
        <label>
          Storage mode
          <select value={form.storage_mode} onChange={e => set('storage_mode', e.target.value)}>
            <option value="prometheus">Mode A — Prometheus + ClickHouse</option>
            <option value="clickhouse_only">Mode B — ClickHouse only</option>
          </select>
        </label>

        <fieldset>
          <legend>Visualization</legend>
          <label><input type="checkbox" checked={form.enable_grafana} onChange={e => set('enable_grafana', e.target.checked)} /> Enable Grafana (port <input type="number" value={form.grafana_port} onChange={e => set('grafana_port', +e.target.value)} style={{ width: 70 }} />)</label>
          <label><input type="checkbox" checked={form.enable_prometheus_ui} onChange={e => set('enable_prometheus_ui', e.target.checked)} /> Enable Prometheus UI (port <input type="number" value={form.prometheus_port} onChange={e => set('prometheus_port', +e.target.value)} style={{ width: 70 }} />)</label>
          <label><input type="checkbox" checked={form.enable_signoz} onChange={e => set('enable_signoz', e.target.checked)} /> Enable SigNoz (port <input type="number" value={form.signoz_port} onChange={e => set('signoz_port', +e.target.value)} style={{ width: 70 }} />)</label>
        </fieldset>

        <fieldset>
          <legend>LLM / RCA</legend>
          <label>
            Provider
            <select value={form.llm_provider} onChange={e => set('llm_provider', e.target.value)}>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Claude (Anthropic)</option>
              <option value="mock">Mock (no key needed)</option>
            </select>
          </label>
          <label>
            API key
            <input type="password" value={form.llm_api_key} onChange={e => set('llm_api_key', e.target.value)} placeholder="sk-…" />
          </label>
          <label>
            RCA trigger
            <select value={form.rca_trigger_mode} onChange={e => set('rca_trigger_mode', e.target.value)}>
              <option value="manual">Manual</option>
              <option value="automatic">Automatic (scheduled polling)</option>
            </select>
          </label>
          {form.rca_trigger_mode === 'automatic' && (
            <label>
              Interval (minutes)
              <input type="number" min="1" value={form.rca_interval_minutes} onChange={e => set('rca_interval_minutes', +e.target.value)} style={{ width: 70 }} />
            </label>
          )}
        </fieldset>

        {error && <p style={{ color: 'red' }}>{error}</p>}
        <button type="submit">Save &amp; generate command</button>
      </form>

      {saved && (
        <div style={{ marginTop: '1.5rem' }}>
          <h2>Run this command to start the stack</h2>
          <pre style={{ background: '#f4f4f4', padding: '1rem', overflowX: 'auto' }}>{command}</pre>
          <p>Copy and run it in your terminal, then navigate to <a href="/">Home</a>.</p>
        </div>
      )}
    </div>
  )
}

function buildCommand(form) {
  const files = ['-f docker-compose.yml']
  if (form.enable_prometheus_ui) files.push('-f docker-compose.prometheus-ui.yml')
  if (form.enable_signoz) files.push('-f docker-compose.signoz.yml')
  files.push('-f docker-compose.otel-demo-override.yml')
  const profiles = form.storage_mode === 'prometheus' ? ['--profile mode-a'] : []
  return ['docker compose', ...files, ...profiles, 'up -d'].join(' \\\n  ')
}
