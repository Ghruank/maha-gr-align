import { useEffect, useState } from 'react'
import { fmt } from '../../api'

// GR-Lint. The persuasive part is not the rule list — it is the *free variation* list next to it.
// "Here are 18 orderings we deliberately do not enforce, because the corpus varies" is the proof
// the rules were measured rather than transcribed from a manual.
export default function Lint() {
  const [prof, setProf] = useState<any>(null)
  const [corpus, setCorpus] = useState<any>(null)
  const [dept, setDept] = useState<string>('')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/lint/profile').then(r => r.json()).then(d => {
      setProf(d)
      if (d.available) setDept(Object.keys(d.profile.departments)[0])
    }).catch(e => setErr(String(e)))
    fetch('/api/lint/corpus?limit=40').then(r => r.json()).then(setCorpus).catch(() => { })
  }, [])

  if (err) return <div className="panel">Backend unreachable: {err}</div>
  if (!prof) return <div className="panel muted">Loading…</div>
  if (!prof.available) return <div className="panel">Not mined yet. {prof.hint}</div>

  const p = prof.profile
  const rules = prof.rules_by_department?.[dept] ?? []
  const dp = p.departments[dept]
  const human: Record<string, string> = prof.human ?? {}

  return (
    <>
      <h1>GR-Lint — template rules mined from the corpus</h1>
      <p className="sub">
        Every rule carries an empirical support count, because a rule without one is an opinion.
        We did not transcribe the Manual of Office Procedure: we measured what{' '}
        {fmt(p.sampled_per_department * Object.keys(p.departments).length)} Government Resolutions
        actually do, per department, and emitted a rule only where the corpus justifies it.
      </p>

      <div className="panel">
        <div className="note">
          <b>Why per-department matters.</b> A प्रस्तावना (preamble) appears in{' '}
          {(p.departments['School_Education_and_Sports_Department']?.presence.preamble.rate * 100).toFixed(0)}%
          of School Education resolutions but only{' '}
          {(p.departments['General_Administration_Department']?.presence.preamble.rate * 100).toFixed(0)}%
          of General Administration's. A single hand-written rule requiring one would flag two
          thirds of a department's lawful output as defective — and a linter that cries wolf gets
          switched off in a week.
        </div>
      </div>

      {corpus?.available && (
        <div className="tiles">
          <div className="tile">
            <div className="k">GRs linted</div>
            <div className="v">{fmt(corpus.linted)}</div>
            <div className="d">random sample across four departments</div>
          </div>
          <div className="tile">
            <div className="k">Pass clean</div>
            <div className="v">{((corpus.clean / corpus.linted) * 100).toFixed(1)}%</div>
            <div className="d">
              {fmt(corpus.clean)} of {fmt(corpus.linted)} — a corpus-mined linter should find its
              own corpus mostly compliant
            </div>
          </div>
          <div className="tile">
            <div className="k">Errors</div>
            <div className="v">{fmt(corpus.severity_tally.ERROR ?? 0)}</div>
            <div className="d">reserved for conventions ≥99% of a department follows</div>
          </div>
          <div className="tile">
            <div className="k">Warnings</div>
            <div className="v">{fmt(corpus.severity_tally.WARN ?? 0)}</div>
            <div className="d">conventions between 90% and 99%</div>
          </div>
        </div>
      )}

      <h2>Rules for a department</h2>
      <div className="panel">
        <select value={dept} onChange={e => setDept(e.target.value)} style={{ minWidth: 340 }}>
          {Object.keys(p.departments).map(d =>
            <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
        </select>
        <div className="scroll" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr><th>Code</th><th>Severity</th><th>Rule</th><th>Measured support</th></tr>
            </thead>
            <tbody>
              {rules.map((r: any) => (
                <tr key={r.code}>
                  <td className="mono">{r.code}</td>
                  <td><span className={`pill ${r.severity === 'ERROR' ? 'SUPERSEDES' : 'AMENDS'}`}>
                    {r.severity}</span></td>
                  <td>{r.message}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{r.support}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2>Marker presence in {dept.replace(/_/g, ' ')}</h2>
      <div className="panel scroll">
        <table>
          <thead>
            <tr><th>Structural marker</th><th className="num">Present in</th><th></th>
              <th>Rule emitted?</th></tr>
          </thead>
          <tbody>
            {Object.entries(dp.presence as Record<string, any>)
              .sort((a, b) => b[1].rate - a[1].rate)
              .map(([k, v]) => {
                const emitted = rules.find((r: any) => r.marker === k)
                return (
                  <tr key={k}>
                    <td>{human[k] ?? k}</td>
                    <td className="num">{(v.rate * 100).toFixed(1)}%</td>
                    <td style={{ width: 170 }}>
                      <div className="bar" style={{
                        width: `${v.rate * 100}%`,
                        background: v.rate >= 0.99 ? 'var(--danger)'
                          : v.rate >= 0.90 ? 'var(--warn)' : 'var(--muted)',
                      }} />
                    </td>
                    <td className="muted" style={{ fontSize: 12 }}>
                      {emitted ? `yes — ${emitted.code} (${emitted.severity})`
                        : 'no — below the 90% threshold, so not a convention'}
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </div>

      <h2>Section ordering — enforced vs free variation</h2>
      <div className="split">
        <div className="panel">
          <div className="lbl muted" style={{ fontSize: 10 }}>
            ENFORCED — {p.order_rules.length} orderings holding in ≥95% of documents
          </div>
          <div className="scroll">
            <table>
              <tbody>
                {p.order_rules.map((r: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontSize: 12.5 }}>
                      {human[r.first] ?? r.first} <span className="muted">before</span>{' '}
                      {human[r.second] ?? r.second}
                    </td>
                    <td className="num" style={{ color: 'var(--ok)' }}>
                      {(r.consistency * 100).toFixed(1)}%
                    </td>
                    <td className="num muted">n={fmt(r.documents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="lbl muted" style={{ fontSize: 10 }}>
            NOT ENFORCED — {p.order_free_variation.length} pairs the corpus varies on
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            An earlier version enforced one canonical order and produced 2,910 violations over
            2,000 GRs. These pairs are genuine free variation, not defects.
          </p>
          <div className="scroll">
            <table>
              <tbody>
                {p.order_free_variation.map((r: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontSize: 12.5 }}>
                      {human[r.first] ?? r.first} <span className="muted">/</span>{' '}
                      {human[r.second] ?? r.second}
                    </td>
                    <td className="num muted">{(r.consistency * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {corpus?.available && (
        <>
          <h2>What fired, across {fmt(corpus.linted)} resolutions</h2>
          <div className="panel scroll">
            <table>
              <thead><tr><th>Rule</th><th className="num">GRs</th><th className="num">Rate</th></tr></thead>
              <tbody>
                {Object.entries(corpus.by_code as Record<string, number>).map(([k, v]) => (
                  <tr key={k}>
                    <td className="mono" style={{ fontSize: 12 }}>{k}</td>
                    <td className="num">{fmt(v)}</td>
                    <td className="num muted">{((v / corpus.linted) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>Sample findings</h2>
          {corpus.findings.slice(0, 12).map((f: any, i: number) => (
            <div className="panel" key={i}>
              <div className="spread">
                <span className="mono" style={{ fontSize: 12 }}>{f.uid}</span>
                <span className="muted" style={{ fontSize: 11.5 }}>
                  {f.dept.replace(/_/g, ' ')}
                </span>
              </div>
              {f.violations.map((v: any, j: number) => (
                <div key={j} style={{ marginTop: 8 }}>
                  <div className="row">
                    <span className={`pill ${v.severity === 'ERROR' ? 'SUPERSEDES' : 'AMENDS'}`}>
                      {v.severity}</span>
                    <span className="mono" style={{ fontSize: 12 }}>{v.code}</span>
                    {v.line && <span className="muted" style={{ fontSize: 12 }}>line {v.line}</span>}
                    <span style={{ fontSize: 13 }}>{v.message}</span>
                  </div>
                  <div className="muted mono" style={{ fontSize: 11.5, marginTop: 3 }}>
                    {v.detail}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </>
  )
}
