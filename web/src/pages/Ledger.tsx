import { useEffect, useState } from 'react'
import { api, fmt } from '../api'

// The page no competing team will have. It answers "how do you know your AI isn't making things
// up" with a number and a browsable list of the specific times it tried.
export default function Ledger() {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.ledger().then(setD).catch(e => setErr(String(e))) }, [])

  if (err) return <div className="panel">Backend unreachable: {err}</div>
  if (!d) return <div className="panel muted">Loading…</div>
  if (!d.available) return <div className="panel">No AI claims recorded yet.</div>

  const s = d.summary
  return (
    <>
      <h1>Trust Ledger</h1>
      <p className="sub">
        The model proposes; the corpus decides. Every claim an AI made about this corpus, the
        gates it faced, and what happened to it. Verification failures are shown here rather
        than hidden — a system that cannot name its own errors should not be trusted with a
        legal graph.
      </p>

      <div className="tiles">
        <div className="tile">
          <div className="k">Claims proposed</div>
          <div className="v">{fmt(s.claims)}</div>
          <div className="d">one per operative sentence sent to the model</div>
        </div>
        <div className="tile">
          <div className="k">Edges upgraded</div>
          <div className="v">{fmt(s.edges_upgraded)}</div>
          <div className="d">
            typed AMENDS or SUPERSEDES after passing every gate
          </div>
        </div>
        <div className="tile">
          <div className="k">Downgraded by scope gate</div>
          <div className="v">{fmt(s.downgraded_by_G7)}</div>
          <div className="d">
            claimed a supersession that only changed something done <i>under</i> the order
          </div>
        </div>
        <div className="tile">
          <div className="k">Gate failures</div>
          <div className="v">
            {fmt(Object.values(s.gate_failures as Record<string, number>)
              .reduce((a: number, b: number) => a + b, 0))}
          </div>
          <div className="d">caught before anything reached this interface</div>
        </div>
      </div>

      <h2>The gates</h2>
      <div className="panel scroll">
        <table>
          <thead>
            <tr><th>Gate</th><th>What it enforces</th><th className="num">Failures</th></tr>
          </thead>
          <tbody>
            {GATES.map(([k, v]) => (
              <tr key={k}>
                <td className="mono">{k}</td>
                <td className="muted">{v}</td>
                <td className="num">{fmt(s.gate_failures[k] ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="note" style={{ marginTop: 12 }}>
          <b>What these gates do not bound.</b> They stop <i>fabrication</i> — invented quotes,
          invented GRs, impossible dates. They cannot stop <i>bad judgement</i>: a model can quote
          a real sentence from a real GR and still draw the wrong conclusion. We observed exactly
          that, which is why the scope gate below exists and why supersessions are spot-checked
          by a human.
        </div>
      </div>

      <h2>Verdicts</h2>
      <div className="panel">
        <div className="row">
          {Object.entries(s.verdicts as Record<string, number>).map(([k, v]) => (
            <div key={k} style={{ minWidth: 120 }}>
              <span className={`pill ${k}`}>{k}</span>
              <div style={{ fontSize: 20, fontWeight: 650, marginTop: 5 }}>{fmt(v)}</div>
            </div>
          ))}
        </div>
      </div>

      {d.downgrades?.length > 0 && (
        <>
          <h2>Scope-gate downgrades — the model over-claimed, deterministically corrected</h2>
          {d.downgrades.map((t: any, i: number) => (
            <div className="panel" key={i}>
              <div className="row">
                <span className="pill SUPERSEDES">{t.proposed_type}</span>
                <span className="muted">→</span>
                <span className={`pill ${t.type}`}>{t.type}</span>
                <span className="muted mono" style={{ fontSize: 11.5 }}>
                  {t.src} → {t.dst}
                </span>
              </div>
              <p className="muted" style={{ fontSize: 12.5, margin: '8px 0 0' }}>
                {t.notes?.join('; ')}
              </p>
              <div className="ev">
                <div className="lbl">Sentence</div>
                <div className="mr">{t.sentence}</div>
                {t.gloss_en && <div className="gloss">“{t.gloss_en}”</div>}
              </div>
              <div className="muted" style={{ fontSize: 12 }}>
                cancelled object: <span className="mr">{t.cancelled_object ?? '—'}</span>
              </div>
            </div>
          ))}
        </>
      )}

      {d.non_verified?.length > 0 && (
        <>
          <h2>Claims that failed a gate</h2>
          {d.non_verified.map((t: any, i: number) => (
            <div className="panel" key={i}>
              <div className="row">
                <span className={`pill ${t.verdict}`}>{t.verdict}</span>
                <span className="muted mono" style={{ fontSize: 11.5 }}>{t.src} → {t.dst}</span>
              </div>
              <ul style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                {[...(t.failed_hard ?? []), ...(t.failed_soft ?? [])].map((x: string, j: number) =>
                  <li key={j} className="mono">{x}</li>)}
              </ul>
              <div className="ev">
                <div className="lbl">The span the model claimed to be quoting</div>
                <div className="mr">{t.evidence_span ?? '—'}</div>
              </div>
              <div className="ev">
                <div className="lbl">What the document actually says</div>
                <div className="mr">{t.sentence}</div>
              </div>
            </div>
          ))}
        </>
      )}
    </>
  )
}

const GATES: [string, string][] = [
  ['G1_grounding', 'Every quoted span must appear verbatim in the cited source document.'],
  ['G2_referential', 'Every GR id must exist in the corpus. Targets come from the deterministic resolver, never the model.'],
  ['G3_vocabulary', 'Relationship types must come from a closed set.'],
  ['G4_numeric', 'Every number asserted must occur in the source, digits normalised across Devanagari and Latin.'],
  ['G5_temporal', 'Nothing may supersede an order issued after it.'],
  ['G6_determinism', 'Temperature 0 and cached; a disagreeing re-run downgrades the claim.'],
  ['G7_scope', 'Cancelling something done under an order is an amendment, not a supersession. Deliberative "under consideration" language is neither.'],
]
