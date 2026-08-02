import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import { api, fmt } from '../api'
import './styles.css'
import Finding from './pages/Finding'
import GraphExplorer from './pages/GraphExplorer'
import Audit from './pages/Audit'
import Ledger from './pages/Ledger'
import Lint from './pages/Lint'
import Bilingual from './pages/Bilingual'

const PAGES = [
  { to: '/archive/finding', label: 'The Finding', key: 'dead' },
  { to: '/archive/graph', label: 'Graph Explorer', key: 'edges' },
  { to: '/archive/audit', label: 'Reference Audit', key: 'dead' },
  { to: '/archive/lint', label: 'GR-Lint', key: 'lint' },
  { to: '/archive/bilingual', label: 'Bilingual Terms', key: 'bil' },
  { to: '/archive/ledger', label: 'Trust Ledger', key: 'claims' },
]

export default function LegacyApp() {
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [theme, setTheme] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('theme') as 'light' | 'dark') || 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    api.overview().then(o => setCounts({
      dead: o.findings.dead_references ?? 0,
      edges: o.scale.edges,
      claims: o.ai_typing.calls ?? 0,
    })).catch(() => { })
    fetch('/api/lint/corpus?limit=1').then(r => r.json())
      .then(d => d.available && setCounts(c => ({ ...c, lint: d.linted })))
      .catch(() => { })
    fetch('/api/bilingual?limit=1').then(r => r.json())
      .then(d => d.available && setCounts(c => ({
        ...c, bil: d.parity.classes?.MAGNITUDE_ERROR ?? 0 })))
      .catch(() => { })
  }, [])

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          MAHA-GR-ALIGN
          <small>GR dependency graph · Govt of Maharashtra</small>
        </div>
        <nav className="nav">
          {PAGES.map(p => (
            <NavLink key={p.to} to={p.to} className={({ isActive }) => isActive ? 'on' : ''}>
              <span>{p.label}</span>
              <span className="n">{fmt(counts[p.key])}</span>
            </NavLink>
          ))}
        </nav>
        <div style={{ marginTop: 22 }}>
          <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            style={{ width: '100%' }}>
            {theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </button>
        </div>
        <p className="muted" style={{ fontSize: 11, marginTop: 22, lineHeight: 1.5 }}>
          Marathi is the legally operative text. English is a derived working view and is
          machine translation — never the basis of a conclusion.
        </p>
      </aside>

      <main className="main">
        <Routes>
          <Route index element={<Navigate to="/archive/finding" replace />} />
          <Route path="finding" element={<Finding />} />
          <Route path="graph" element={<GraphExplorer />} />
          <Route path="graph/:uid" element={<GraphExplorer />} />
          <Route path="audit" element={<Audit />} />
          <Route path="lint" element={<Lint />} />
          <Route path="bilingual" element={<Bilingual />} />
          <Route path="ledger" element={<Ledger />} />
          <Route path="*" element={<div className="panel">Page not found.</div>} />
        </Routes>
      </main>
    </div>
  )
}
