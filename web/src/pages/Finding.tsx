import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt, DEPT_COLOR, type Overview } from '../api'

// The landing page leads with a FINDING, not a feature list (CLAUDE.md pitch framing).
// A judge should understand what this project discovered within fifteen seconds.
export default function Finding() {
  const [o, setO] = useState<Overview | null>(null)
  const [m, setM] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.overview().then(setO).catch(e => setErr(String(e)))
    api.metrics().then(setM).catch(() => { })
  }, [])

  if (err) return <div className="panel">Backend unreachable: {err}</div>
  if (!o) return <div className="panel muted">Loading artefacts…</div>

  const f = o.findings
  const ab = m?.ablation
  const xl = m?.cross_language

  return (
    <>
      <h1>A Government Resolution is not a document. It is a node in a legal dependency graph.</h1>
      <p className="sub">
        Maharashtra has issued lakhs of GRs since 1960. Every one amends, supersedes, references
        or silently contradicts earlier ones — and no machine-readable representation of those
        relationships exists anywhere. We built it for {fmt(o.scale.grs)} GRs across{' '}
        {o.scale.departments} departments, then asked what it reveals.
      </p>

      <div className="tiles">
        <div className="tile hero">
          <div className="k">Dead references</div>
          <div className="v">{fmt(f.dead_references)}</div>
          <div className="d">GRs in force citing orders that no longer exist</div>
        </div>
        <div className="tile">
          <div className="k">Cross-department edges</div>
          <div className="v">{fmt(o.scale.cross_dept_edges)}</div>
          <div className="d">
            {((o.scale.cross_dept_edges / Math.max(o.scale.edges, 1)) * 100).toFixed(1)}% of all
            dependencies cross a departmental boundary
          </div>
        </div>
        <div className="tile">
          <div className="k">Dependencies mapped</div>
          <div className="v">{fmt(o.scale.edges)}</div>
          <div className="d">from {fmt(o.scale.citations)} extracted citations</div>
        </div>
        <div className="tile">
          <div className="k">Supersessions found</div>
          <div className="v">{fmt(o.edge_types.SUPERSEDES)}</div>
          <div className="d">{fmt(o.edge_types.AMENDS)} amendments, each with its evidence</div>
        </div>
      </div>

      <h2>What the dead references look like</h2>
      <div className="panel">
        <div className="row" style={{ gap: 26 }}>
          <div>
            <div className="k muted" style={{ fontSize: 11 }}>ROTTED</div>
            <div style={{ fontSize: 21, fontWeight: 650 }}>{fmt(f.rotted)}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              correct when written — the cited order died later
            </div>
          </div>
          <div>
            <div className="k muted" style={{ fontSize: 11 }}>BORN DEAD</div>
            <div style={{ fontSize: 21, fontWeight: 650 }}>{fmt(f.born_dead)}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              cited an order that was already cancelled
            </div>
          </div>
          <div>
            <div className="k muted" style={{ fontSize: 11 }}>LATENT CROSS-DEPT</div>
            <div style={{ fontSize: 21, fontWeight: 650 }}>
              {fmt(f.latent_cross_department)}
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              a live GR depending on another department's replaced order
            </div>
          </div>
        </div>
        <p style={{ marginTop: 14, marginBottom: 0 }}>
          <Link to="/audit">Every finding, with the Marathi sentence that proves it →</Link>
        </p>
      </div>

      <h2>Finance is the structural chokepoint</h2>
      <div className="panel">
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          Every department's spending decisions hang off Finance appropriation orders. Supersede
          one and hundreds of GRs across the state are affected at once.
        </p>
        <div className="scroll">
          <table>
            <thead><tr><th>Dependency flow</th><th className="num">Edges</th><th></th></tr></thead>
            <tbody>
              {Object.entries(o.cross_dept_flows).map(([k, v]) => {
                const max = Math.max(...Object.values(o.cross_dept_flows))
                return (
                  <tr key={k}>
                    <td>{k}</td>
                    <td className="num">{fmt(v)}</td>
                    <td style={{ width: 180 }}>
                      <div className="bar" style={{ width: `${(v / max) * 100}%` }} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {ab && (
        <>
          <h2>Why this is hard — and why the obvious approach fails</h2>
          <div className="panel">
            <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
              A GR's "Government Decision No." is a <b>departmental file number, not a unique
              identifier</b> — 41% of GRs share theirs with another. And dates collide massively.
              Measured over the {fmt(ab.edges)} dependencies we resolved:
            </p>
            <div className="scroll">
              <table>
                <thead>
                  <tr><th>Matching key</th><th className="num">Ambiguous</th>
                    <th className="num">Uniquely resolved</th><th>Outcome</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Date alone <span className="muted">(the naive approach)</span></td>
                    <td className="num">{ab.date_only.ambiguous_pct}%</td>
                    <td className="num">{ab.date_only.unique_pct}%</td>
                    <td className="muted">
                      mean {ab.date_only.mean_candidates} candidates, worst{' '}
                      {ab.date_only.max_candidates} — resolves nothing
                    </td>
                  </tr>
                  <tr>
                    <td>File number alone</td>
                    <td className="num">{ab.number_only.ambiguous_pct}%</td>
                    <td className="num">{ab.number_only.unique_pct}%</td>
                    <td className="muted">a file accumulates decisions over years</td>
                  </tr>
                  <tr>
                    <td><b>Both, plus a script-independent digit key</b></td>
                    <td className="num">0%</td>
                    <td className="num">100%</td>
                    <td className="muted">ambiguity abstains rather than guessing</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <h2>How far we trust it</h2>
      <div className="tiles">
        {xl && (
          <div className="tile">
            <div className="k">Cross-language agreement</div>
            <div className="v">{xl.agreement_lower_bound_pct}%</div>
            <div className="d">
              over {fmt(xl.comparable_edges)} edges where the English text independently states a
              file number. A <b>lower bound</b> — most residual disagreement is translation damage
            </div>
          </div>
        )}
        {m?.groundedness && (
          <div className="tile">
            <div className="k">Evidence groundedness</div>
            <div className="v">{m.groundedness.groundedness_pct}%</div>
            <div className="d">
              of {fmt(m.groundedness.checked)} sampled edges quote their source document verbatim
            </div>
          </div>
        )}
        {m?.invariants && (
          <div className="tile">
            <div className="k">Structural violations</div>
            <div className="v">{fmt(m.invariants.total_violations)}</div>
            <div className="d">
              over {fmt(m.invariants.edges_checked)} edges — no self-citation, nothing pointing
              forward in time, no lost citations
            </div>
          </div>
        )}
        <div className="tile">
          <div className="k">Accuracy</div>
          <div className="v" style={{ fontSize: 17, fontWeight: 600 }}>Unmeasured</div>
          <div className="d">
            Requires a human-labelled answer key. We will not print a number we did not measure.
          </div>
        </div>
      </div>

      <h2>What we could not verify — stated, not hidden</h2>
      <div className="panel">
        <div className="note">{o.unverifiable.warning}</div>
        <div className="scroll" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th>Reason</th><th className="num">Citations</th></tr></thead>
            <tbody>
              {Object.entries(o.unverifiable.by_reason)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <tr key={k}>
                    <td className="mono">{k}</td>
                    <td className="num">{fmt(v)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2>Corpus</h2>
      <div className="panel">
        <div className="scroll">
          <table>
            <thead><tr><th>Department</th><th className="num">GRs</th><th></th></tr></thead>
            <tbody>
              {Object.entries(o.scale.by_department).map(([k, v]) => (
                <tr key={k}>
                  <td>
                    <span style={{
                      display: 'inline-block', width: 9, height: 9, borderRadius: 2,
                      background: DEPT_COLOR[k] ?? '#888', marginRight: 8,
                    }} />{k}
                  </td>
                  <td className="num">{fmt(v)}</td>
                  <td style={{ width: 200 }}>
                    <div className="bar" style={{
                      width: `${(v / Math.max(...Object.values(o.scale.by_department))) * 100}%`,
                      background: DEPT_COLOR[k] ?? '#888',
                    }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
          {o.scale.index_covers?.[0]} → {o.scale.index_covers?.[1]}. Source corpus:{' '}
          <a href="https://github.com/orgpedia/mahGRs" target="_blank" rel="noreferrer">
            orgpedia/mahGRs</a> (MIT) — OCR, paragraph/table detection and IndicTrans2 translation
          are theirs and we credit them. The graph is ours.
        </p>
      </div>
    </>
  )
}
