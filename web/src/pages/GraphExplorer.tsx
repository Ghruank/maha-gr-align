import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import cytoscape from 'cytoscape'
import { api, fmt, DEPT_COLOR, EDGE_COLOR, type Edge, type Node } from '../api'

// The thesis, visible. Node = GR, edge = a legal dependency. Clicking an edge shows the verbatim
// Marathi sentence that produced it — if we cannot show that sentence, the edge does not ship.
export default function GraphExplorer() {
  const { uid } = useParams()
  const nav = useNavigate()
  const box = useRef<HTMLDivElement>(null)
  const cy = useRef<cytoscape.Core | null>(null)

  const [center, setCenter] = useState<string | null>(uid ?? null)
  const [depth, setDepth] = useState(1)
  const [sel, setSel] = useState<{ kind: 'node' | 'edge'; data: any } | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [hubs, setHubs] = useState<Node[]>([])
  const [q, setQ] = useState('')
  const [truncated, setTruncated] = useState(false)
  const [busy, setBusy] = useState(false)

  // Entry point: the most-depended-upon GRs. Starting from a hub shows the structure
  // immediately; an arbitrary node usually has one edge and teaches nothing.
  useEffect(() => {
    api.nodes({ sort: 'in_degree', limit: 12 })
      .then(r => {
        setHubs(r.nodes)
        if (!center && r.nodes.length) setCenter(r.nodes[0].uid)
      })
      .catch(() => { })
  }, [])

  useEffect(() => { if (uid && uid !== center) setCenter(uid) }, [uid])

  useEffect(() => {
    if (!center || !box.current) return
    setBusy(true)
    api.subgraph(center, depth, 130).then(g => {
      setTruncated(g.truncated)
      const elements = [
        ...g.nodes.map(n => ({
          data: {
            id: n.uid, label: n.uid.slice(0, 8), dept: n.dept ?? '?',
            subject: n.subject, date: n.date, decision_no: n.decision_no,
            in_degree: n.in_degree, out_degree: n.out_degree,
            in_force: n.in_force !== false, isCenter: n.uid === center,
          },
        })),
        ...g.edges.map(e => ({
          data: { id: `e${e.index}`, source: e.src, target: e.dst, type: e.type, edge: e },
        })),
      ]

      cy.current?.destroy()
      cy.current = cytoscape({
        container: box.current!,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': (n: any) => DEPT_COLOR[n.data('dept')] ?? '#78839a',
              label: 'data(label)', 'font-size': 7, color: '#fff',
              'text-valign': 'center', 'text-outline-width': 1.6,
              'text-outline-color': (n: any) => DEPT_COLOR[n.data('dept')] ?? '#78839a',
              width: (n: any) => 16 + Math.min(30, Math.sqrt(n.data('in_degree')) * 4),
              height: (n: any) => 16 + Math.min(30, Math.sqrt(n.data('in_degree')) * 4),
              'border-width': 0,
            },
          },
          {
            selector: 'node[?isCenter]',
            style: { 'border-width': 3, 'border-color': '#f5b301' },
          },
          {
            // A superseded GR is drawn hollow — a dead node is the pitch in one glance.
            selector: 'node[!in_force]',
            style: {
              'background-opacity': 0.18, 'border-width': 2.5, 'border-style': 'dashed',
              'border-color': '#dc2626', color: '#dc2626', 'text-outline-width': 0,
            },
          },
          {
            selector: 'edge',
            style: {
              width: (e: any) => (e.data('type') === 'REFERENCES' ? 1 : 2.4),
              'line-color': (e: any) => EDGE_COLOR[e.data('type')],
              'target-arrow-color': (e: any) => EDGE_COLOR[e.data('type')],
              'target-arrow-shape': 'triangle', 'arrow-scale': 0.75,
              'curve-style': 'bezier', opacity: 0.72,
              'line-style': (e: any) => (e.data('type') === 'AMENDS' ? 'dashed' : 'solid'),
            },
          },
          { selector: ':selected', style: { 'line-color': '#f5b301', width: 3.5, opacity: 1 } },
        ],
        layout: { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 85,
                  padding: 24 } as any,
        wheelSensitivity: 0.25,
      })

      cy.current.on('tap', 'node', ev => setSel({ kind: 'node', data: ev.target.data() }))
      cy.current.on('tap', 'edge', ev => setSel({ kind: 'edge', data: ev.target.data().edge }))
      cy.current.on('dbltap', 'node', ev => nav(`/graph/${ev.target.id()}`))
      setBusy(false)
    }).catch(() => setBusy(false))
  }, [center, depth])

  useEffect(() => {
    if (sel?.kind === 'node') api.node(sel.data.id).then(setDetail).catch(() => setDetail(null))
    else setDetail(null)
  }, [sel])

  return (
    <>
      <h1>Graph Explorer</h1>
      <p className="sub">
        Each circle is a Government Resolution, sized by how many others depend on it and
        coloured by department. Arrows point from the citing GR to the order it relies on.
        A <span style={{ color: '#dc2626' }}>dashed red outline</span> means that GR has been
        superseded — an arrow into one is a dead reference. Double-click to re-centre.
      </p>

      <div className="panel">
        <div className="row">
          <input placeholder="Search subject, number or uid…" value={q}
                 style={{ flex: 1, minWidth: 220 }}
                 onChange={e => setQ(e.target.value)}
                 onKeyDown={async e => {
                   if (e.key !== 'Enter' || !q.trim()) return
                   const r = await api.nodes({ q: q.trim(), limit: 1 })
                   if (r.nodes[0]) nav(`/graph/${r.nodes[0].uid}`)
                 }} />
          <span className="muted" style={{ fontSize: 12 }}>depth</span>
          {[1, 2].map(d => (
            <button key={d} className={depth === d ? 'on' : ''} onClick={() => setDepth(d)}>{d}</button>
          ))}
          {Object.entries(EDGE_COLOR).map(([t, c]) => (
            <span key={t} className="muted" style={{ fontSize: 11.5 }}>
              <span style={{ display: 'inline-block', width: 14, height: 3,
                             background: c, marginRight: 5, verticalAlign: 'middle' }} />{t}
            </span>
          ))}
        </div>
        <div className="row" style={{ marginTop: 9 }}>
          <span className="muted" style={{ fontSize: 12 }}>Most-depended-upon:</span>
          {hubs.slice(0, 7).map(h => (
            <button key={h.uid} className={center === h.uid ? 'on' : ''}
                    onClick={() => nav(`/graph/${h.uid}`)}
                    title={h.subject} style={{ fontSize: 11.5, padding: '4px 8px' }}>
              {h.in_degree} · {h.subject.slice(0, 26)}
            </button>
          ))}
        </div>
        {truncated && (
          <div className="note" style={{ marginTop: 9 }}>
            Neighbourhood capped at 130 nodes. This GR has more dependents than can be drawn
            legibly — the count in the panel is the true figure.
          </div>
        )}
      </div>

      <div className="split">
        <div>
          <div id="cy" ref={box} />
          {busy && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>rendering…</div>}
        </div>

        <div>
          {!sel && (
            <div className="panel muted" style={{ fontSize: 13 }}>
              Click a node or an edge. Every edge carries the verbatim Marathi sentence that
              justified it.
            </div>
          )}

          {sel?.kind === 'edge' && <EdgePanel e={sel.data as Edge} />}

          {sel?.kind === 'node' && (
            <div className="panel">
              <div className="spread">
                <span className="mono" style={{ fontSize: 12 }}>{sel.data.id}</span>
                {detail && (detail.in_force
                  ? <span className="pill VERIFIED">in force</span>
                  : <span className="pill SUPERSEDES">superseded</span>)}
              </div>
              <p style={{ fontSize: 13.5, margin: '8px 0' }}>{sel.data.subject}</p>
              <table>
                <tbody>
                  <tr><th>Date</th><td>{sel.data.date}</td></tr>
                  <tr><th>Department</th><td>{sel.data.dept}</td></tr>
                  <tr><th>Decision no.</th><td className="mr">{sel.data.decision_no || '—'}</td></tr>
                  <tr><th>Depended on by</th><td>{fmt(sel.data.in_degree)} GRs</td></tr>
                  <tr><th>Depends on</th><td>{fmt(sel.data.out_degree)} GRs</td></tr>
                  {detail && (
                    <tr><th>Unverifiable citations</th>
                      <td>{fmt(detail.unresolved_citations.length)}</td></tr>
                  )}
                </tbody>
              </table>
              {detail?.superseded_by?.length > 0 && (
                <div className="ev" style={{ borderLeftColor: 'var(--danger)' }}>
                  <div className="lbl">Superseded by</div>
                  {detail.superseded_by.map((e: Edge) => (
                    <div key={e.index} style={{ marginBottom: 6 }}>
                      <a className="mono" onClick={() => nav(`/graph/${e.src}`)}
                         style={{ cursor: 'pointer' }}>{e.src}</a>{' '}
                      <span className="muted">{e.src_date}</span>
                      <div className="mr" style={{ fontSize: 12.5 }}>{e.evidence}</div>
                    </div>
                  ))}
                </div>
              )}
              <button style={{ marginTop: 8 }} onClick={() => nav(`/graph/${sel.data.id}`)}>
                Centre on this GR
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function EdgePanel({ e }: { e: Edge }) {
  const v = e.verification
  return (
    <div className="panel">
      <div className="row">
        <span className={`pill ${e.type}`}>{e.type}</span>
        {e.cross_dept && <span className="pill AMENDS">cross-department</span>}
        {v && <span className={`pill ${v.verdict}`}>{v.verdict}</span>}
      </div>

      <table style={{ marginTop: 9 }}>
        <tbody>
          <tr><th style={{ width: 74 }}>From</th>
            <td><span className="mono">{e.src}</span> <span className="muted">{e.src_date}</span>
              <div className="muted" style={{ fontSize: 12 }}>{e.src_dept}</div></td></tr>
          <tr><th>To</th>
            <td><span className="mono">{e.dst}</span> <span className="muted">{e.dst_date}</span>
              <div className="muted" style={{ fontSize: 12 }}>{e.dst_dept}</div></td></tr>
          <tr><th>Confidence</th><td>{e.confidence}</td></tr>
          <tr><th>Matched by</th><td className="muted" style={{ fontSize: 12 }}>{e.how}</td></tr>
        </tbody>
      </table>

      <div className="ev">
        <div className="lbl">Evidence — verbatim Marathi, authoritative</div>
        <div className="mr">{e.evidence}</div>
        {e.evidence_en && <div className="gloss">“{e.evidence_en}” — machine gloss, reading aid only</div>}
      </div>

      {e.cue && (
        <div className="ev" style={{ borderLeftColor: 'var(--warn)' }}>
          <div className="lbl">Operative phrase that set this type</div>
          <div className="mr">{e.cue}</div>
        </div>
      )}

      {v && (
        <>
          <div className="lbl muted" style={{ fontSize: 10, marginTop: 10 }}>VERIFICATION GATES</div>
          <table>
            <tbody>
              {Object.entries(v.gates).map(([g, r]) => (
                <tr key={g}>
                  <td className="mono" style={{ fontSize: 11.5 }}>{g}</td>
                  <td style={{ color: r.pass ? 'var(--ok)' : 'var(--danger)', fontSize: 11.5 }}>
                    {r.pass ? 'pass' : 'FAIL'} {r.why && <span className="muted">{r.why}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {v.notes?.length > 0 && (
            <div className="note" style={{ marginTop: 8 }}>{v.notes.join('; ')}</div>
          )}
        </>
      )}
    </div>
  )
}
