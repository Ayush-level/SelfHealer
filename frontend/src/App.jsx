import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import Setup from './pages/Setup.jsx'
import Home from './pages/Home.jsx'
import Telemetry from './pages/Telemetry.jsx'
import Tools from './pages/Tools.jsx'
import RCA from './pages/RCA.jsx'
import { getConfig } from './api/client.js'

function Nav() {
  return (
    <nav style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #ddd', display: 'flex', gap: '1.5rem' }}>
      <NavLink to="/">Home</NavLink>
      <NavLink to="/telemetry">Telemetry</NavLink>
      <NavLink to="/tools">Tools</NavLink>
      <NavLink to="/rca">RCA</NavLink>
      <NavLink to="/setup">Setup</NavLink>
    </nav>
  )
}

export default function App() {
  const [hasConfig, setHasConfig] = useState(null)

  useEffect(() => {
    getConfig()
      .then(cfg => setHasConfig(cfg && Object.keys(cfg).length > 0))
      .catch(() => setHasConfig(false))  // proxy unreachable → show setup
  }, [])

  // Wait for config check before rendering to avoid flash
  if (hasConfig === null) return null

  return (
    <BrowserRouter>
      <Nav />
      <main style={{ padding: '1.5rem' }}>
        <Routes>
          <Route path="/setup" element={<Setup onSaved={() => setHasConfig(true)} />} />
          <Route path="/" element={hasConfig ? <Home /> : <Navigate to="/setup" replace />} />
          <Route path="/telemetry" element={<Telemetry />} />
          <Route path="/tools" element={<Tools />} />
          <Route path="/rca" element={<RCA />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
