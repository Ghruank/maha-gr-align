import { useState } from 'react'
import type { GraphEdge, NodeView } from './draftApi'

/* The dependency neighbourhood of one GR, as SVG.

   ## Why three columns rather than a force layout

   The archived dashboard renders this with cytoscape and a cose layout, which is the right tool
   for exploring a whole component. It is the wrong tool for the question asked here — *what does
   this GR stand on, and what stands on it* — because a force layout places nodes by attraction
   and direction survives only in the arrowheads. Read at a glance, or on a projector, a hairball
   does not answer a directional question.

   So: what this GR cites on the LEFT, the GR itself in the MIDDLE, what cites it on the RIGHT.
   Time and dependency both flow left to right. It is also deterministic — the same GR draws the
   same picture every time, which a force layout does not guarantee and a demo needs.

   It also keeps cytoscape out of the portal bundle; it is currently loaded only by the lazy
   archive chunk, and importing it here would move ~400 kB into the main one.

   ## What is deliberately visible

   Superseded GRs are drawn with a red dashed outline, because a neighbourhood full of orders
   that no longer stand is the finding. Edge colour carries the type, and the AMENDS/SUPERSEDES
   edges are the ones AI typing produced — clicking any edge shows the verbatim Marathi sentence
   behind it, because an edge we cannot justify should not be on screen. */

const ROW = 46
const COL = 300
const PAD = 26
const MAX_PER_SIDE = 12

const EDGE_COLOR: Record<GraphEdge['type'], string> = {
  REFERENCES: '#8fa3b8',
  AMENDS: '#c9a227',
  SUPERSEDES: '#b3261e',
}

const DEPT_COLOR: Record<string, string> = {
  'Finance': '#0d6e6e',
  'General Administration': '#123a6b',
  'Higher and Technical Education': '#1b8a5a',
  'School Education': '#d97706',
}

const deptColor = (d: string | null) => (d && DEPT_COLOR[d]) || '#5b6a7a'

export default function GraphView({ view, mr, onOpen, onFocus }: {
  view: NodeView
  mr: boolean
  onOpen: (uid: string) => void
  onFocus: (uid: string) => void
}) {
  const [sel, setSel] = useState<GraphEdge | null>(null)

  // Most recent first, so a truncated side drops the oldest neighbours rather than an
  // arbitrary slice of them.
  const on = (e: GraphEdge, side: 'cites' | 'by') =>
    (side === 'cites' ? e.dst_date : e.src_date) || ''
  const cites = [...view.cites].sort((a, b) => on(b, 'cites').localeCompare(on(a, 'cites')))
  const by = [...view.cited_by].sort((a, b) => on(b, 'by').localeCompare(on(a, 'by')))
  const L = cites.slice(0, MAX_PER_SIDE)
  const R = by.slice(0, MAX_PER_SIDE)

  const rows = Math.max(L.length, R.length, 1)
  const h = Math.max(rows * ROW + PAD * 2, 220)
  const w = COL * 2 + 260
  const midY = h / 2
  const midX = w / 2

  const yFor = (i: number, n: number) => midY + (i - (n - 1) / 2) * ROW

  return (
    <div className="pk-gv">
      <div className="pk-gv-cols">
        <span>{mr ? 'हा निर्णय ज्यांचा संदर्भ देतो' : 'What this GR cites'} · {view.cites.length}</span>
        <span>{mr ? 'हा निर्णय' : 'This GR'}</span>
        <span>{mr ? 'याचा संदर्भ देणारे' : 'What cites this GR'} · {view.cited_by.length}</span>
      </div>

      <div className="pk-gv-scroll">
        <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img"
          aria-label={mr ? 'अवलंबित्व आलेख' : 'Dependency graph'}>
          <defs>
            {Object.entries(EDGE_COLOR).map(([t, c]) => (
              <marker key={t} id={`ar-${t}`} viewBox="0 0 8 8" refX="7" refY="4"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L8,4 L0,8 z" fill={c} />
              </marker>
            ))}
          </defs>

          {/* Edges first so nodes sit on top of them. */}
          {L.map((e, i) => (
            <Edge key={`l${e.index}`} e={e} sel={sel} onSel={setSel}
              x1={PAD + 210} y1={yFor(i, L.length)} x2={midX - 96} y2={midY} />
          ))}
          {R.map((e, i) => (
            <Edge key={`r${e.index}`} e={e} sel={sel} onSel={setSel}
              x1={w - PAD - 210} y1={yFor(i, R.length)} x2={midX + 96} y2={midY} />
          ))}

          {L.map((e, i) => (
            <Node key={`ln${e.index}`} x={PAD} y={yFor(i, L.length)} anchor="start"
              uid={e.dst} date={e.dst_date} dept={e.dst_dept} subject={e.dst_subject}
              dead={!e.dst_in_force} onOpen={onOpen} onFocus={onFocus} />
          ))}
          {R.map((e, i) => (
            <Node key={`rn${e.index}`} x={w - PAD - 210} y={yFor(i, R.length)} anchor="start"
              uid={e.src} date={e.src_date} dept={e.src_dept} subject={e.src_subject}
              dead={!e.src_in_force} onOpen={onOpen} onFocus={onFocus} />
          ))}

          {/* The centre. Red dashed when this GR has itself been superseded. */}
          <g className="pk-gv-centre">
            <rect x={midX - 94} y={midY - 30} width={188} height={60} rx={8}
              fill="#fff" stroke={view.in_force ? deptColor(view.node.dept) : '#b3261e'}
              strokeWidth={view.in_force ? 2 : 2.5}
              strokeDasharray={view.in_force ? undefined : '6 4'} />
            <text x={midX} y={midY - 10} textAnchor="middle" className="pk-gv-uid">
              {view.node.uid}
            </text>
            <text x={midX} y={midY + 6} textAnchor="middle" className="pk-gv-sub">
              {view.node.date} · {short(view.node.dept)}
            </text>
            <text x={midX} y={midY + 22} textAnchor="middle"
              className={view.in_force ? 'pk-gv-live' : 'pk-gv-dead'}>
              {view.in_force ? (mr ? 'अंमलात' : 'in force') : (mr ? 'अधिक्रमित' : 'superseded')}
            </text>
          </g>
        </svg>
      </div>

      {(cites.length > L.length || by.length > R.length) && (
        <p className="pk-fine">{mr
          ? `जागेअभावी प्रत्येक बाजूस ${MAX_PER_SIDE} पर्यंतच दाखवले आहेत.`
          : `Showing at most ${MAX_PER_SIDE} per side; this GR has ${cites.length} cited and ${by.length} citing.`}</p>
      )}

      {sel
        ? <EdgeDetail e={sel} mr={mr} onClose={() => setSel(null)} />
        : <p className="pk-fine">{mr
          ? 'रेषेवर क्लिक केल्यास ती जोडणी कोणत्या वाक्यामुळे निर्माण झाली ते दिसेल.'
          : 'Click a line to see the sentence that produced that link. Click a box to re-centre on it.'}</p>}
    </div>
  )
}

function Edge({ e, x1, y1, x2, y2, sel, onSel }: {
  e: GraphEdge; x1: number; y1: number; x2: number; y2: number
  sel: GraphEdge | null; onSel: (e: GraphEdge) => void
}) {
  const on = sel?.index === e.index
  const mx = (x1 + x2) / 2
  const d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`
  return (
    <g className="pk-gv-edge" onClick={() => onSel(e)}>
      {/* A fat invisible line so the click target is not a 2 px hair. */}
      <path d={d} stroke="transparent" strokeWidth={14} fill="none" />
      <path d={d} stroke={EDGE_COLOR[e.type]} strokeWidth={on ? 3 : 1.6} fill="none"
        strokeDasharray={e.type === 'AMENDS' ? '7 4' : undefined}
        markerEnd={`url(#ar-${e.type})`} opacity={on ? 1 : 0.75} />
    </g>
  )
}

function Node({ x, y, uid, date, dept, subject, dead, onOpen, onFocus }: {
  x: number; y: number; anchor?: string; dead?: boolean
  uid: string; date: string | null; dept: string | null; subject: string | null
  onOpen: (uid: string) => void; onFocus: (uid: string) => void
}) {
  return (
    <g className={`pk-gv-node ${dead ? 'dead' : ''}`}>
      {/* A red dashed box means that order has itself been superseded. A neighbourhood full of
          them is the finding, so it has to be visible without clicking anything. */}
      <rect x={x} y={y - 17} width={210} height={34} rx={6}
        fill={dead ? '#fdf4f3' : '#fff'} stroke={dead ? '#b3261e' : deptColor(dept)}
        strokeWidth={dead ? 1.8 : 1.4} strokeDasharray={dead ? '5 3' : undefined}
        onClick={() => onFocus(uid)}>
        <title>{subject || uid}</title>
      </rect>
      <text x={x + 9} y={y - 3} className="pk-gv-uid sm" onClick={() => onFocus(uid)}>{uid}</text>
      <text x={x + 9} y={y + 10} className="pk-gv-sub" onClick={() => onFocus(uid)}>
        {date} · {short(dept)}{dead ? ' · superseded' : ''}
      </text>
      <text x={x + 199} y={y + 4} textAnchor="end" className="pk-gv-open"
        onClick={() => onOpen(uid)}>↗</text>
    </g>
  )
}

function EdgeDetail({ e, mr, onClose }: { e: GraphEdge; mr: boolean; onClose: () => void }) {
  return (
    <div className={`pk-gv-edgebox t-${e.type}`}>
      <div>
        <span className="pk-tag">{e.type}</span>
        <code>{e.src}</code> → <code>{e.dst}</code>
        {e.cross_dept && <span className="pk-tag cue">{mr ? 'आंतरविभागीय' : 'cross-department'}</span>}
        <button className="pk-modal-x" onClick={onClose} aria-label="Close">×</button>
      </div>
      {/* The verbatim Marathi that justified this edge. Without it the edge is an assertion. */}
      <q className="pk-mr">{e.evidence}</q>
      {e.how && <p className="pk-fine">{e.how}</p>}
      {e.verification?.verdict && (
        <p className="pk-fine">
          {mr ? 'पडताळणी' : 'AI typing'}: {e.verification.verdict}
          {e.verification.gloss_en && ` — ${e.verification.gloss_en}`}
        </p>
      )}
    </div>
  )
}

/** Department names are long and the boxes are 210 px. Initials keep the colour meaningful. */
function short(d: string | null): string {
  if (!d) return '—'
  if (d.length <= 18) return d
  return d.split(/\s+/).filter(w => /^[A-Z]/.test(w)).map(w => w[0]).join('') || d.slice(0, 16)
}
