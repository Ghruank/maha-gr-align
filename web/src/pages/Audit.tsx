import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt, type Finding } from '../api'

// Two tabs, deliberately separate: proven dead references, and citations we could not verify.
// Keeping them apart IS the credibility feature — merging them would multiply the headline
// several times over and make it false.
export default function Audit() {
  const [data, setData] = useState<any>(null)
  const [tab, setTab] = useState<'ALL' | 'ROTTED' | 'BORN_DEAD' | 'UNVERIFIABLE'>('ALL')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.audit().then(setData).catch(e => setErr(String(e))) }, [])

  if (err) return <div className="panel">Backend unreachable: {err}</div>
  if (!data) return <div className="panel muted">Loading…</div>
  if (!data.available) return <div className="panel">Audit not built yet. {data.hint}</div>

  const all: Finding[] = data.findings
  const shown = tab === 'ALL' || tab === 'UNVERIFIABLE' ? all : all.filter(f => f.kind === tab)
  const h = data.headline

  return (
    <>
      <h1>Reference Audit</h1>
      <p className="sub">
        Which Government Resolutions still in force cite orders that have been cancelled. Every
        row below is backed by two verbatim Marathi sentences: the citation, and the supersession
        that killed its target.
      </p>

      <div className="panel">
        <div className="row">
          {(['ALL', 'ROTTED', 'BORN_DEAD', 'UNVERIFIABLE'] as const).map(t => (
            <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
              {t === 'ALL' ? `All proven (${fmt(h.dead_references)})`
                : t === 'ROTTED' ? `Rotted (${fmt(h.rotted)})`
                  : t === 'BORN_DEAD' ? `Born dead (${fmt(h.born_dead)})`
                    : `Unverifiable (${fmt(data.unverifiable.total)})`}
            </button>
          ))}
        </div>
      </div>

      {tab === 'UNVERIFIABLE' ? (
        <>
          <div className="panel">
            <div className="note"><b>These are NOT dead references.</b> {data.unverifiable.WARNING}</div>
          </div>
          <div className="panel scroll">
            <table>
              <thead><tr><th>Reason</th><th className="num">Citations</th><th>What it means</th></tr></thead>
              <tbody>
                {Object.entries(data.unverifiable.by_reason as Record<string, number>)
                  .sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <tr key={k}>
                      <td className="mono">{k}</td>
                      <td className="num">{fmt(v)}</td>
                      <td className="muted">{EXPLAIN[k] ?? '—'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Definitions — shown because they are choices, not facts</h2>
            <table>
              <tbody>
                {Object.entries(data.definitions as Record<string, string>).map(([k, v]) => (
                  <tr key={k}>
                    <td className="mono" style={{ whiteSpace: 'nowrap' }}>{k}</td>
                    <td className="muted">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {shown.length === 0 && (
            <div className="panel muted">
              No findings in this category. That is a real result, not a failure — it means no GR
              still in force cites an order we can <i>prove</i> was superseded.
            </div>
          )}

          {shown.map((f, i) => (
            <div className="panel" key={i}>
              <div className="spread">
                <div>
                  <span className={`pill ${f.kind}`}>{f.kind.replace('_', ' ')}</span>{' '}
                  {f.cross_dept_citation &&
                    <span className="pill AMENDS">cross-department</span>}
                </div>
                <div className="muted mono" style={{ fontSize: 11.5 }}>
                  {f.kind === 'BORN_DEAD'
                    ? `already dead ${f.days_dead_when_cited} days when cited`
                    : `died ${f.days_until_death} days after this GR was issued`}
                </div>
              </div>

              <table style={{ marginTop: 10 }}>
                <tbody>
                  <tr>
                    <th style={{ width: 110 }}>Citing GR</th>
                    <td>
                      <Link to={`/graph/${f.citing_uid}`} className="mono">{f.citing_uid}</Link>{' '}
                      <span className="muted">{f.citing_date} · {f.citing_dept}</span>
                      <div>{f.citing_subject}</div>
                    </td>
                  </tr>
                  <tr>
                    <th>Cites</th>
                    <td>
                      <Link to={`/graph/${f.target_uid}`} className="mono">{f.target_uid}</Link>{' '}
                      <span className="muted">{f.target_date} · {f.target_dept}</span>
                      <div>{f.target_subject}</div>
                    </td>
                  </tr>
                  <tr>
                    <th>Killed by</th>
                    <td>
                      <Link to={`/graph/${f.superseded_by}`} className="mono">
                        {f.superseded_by}</Link>{' '}
                      <span className="muted">{f.superseded_on}</span>
                      <div>{f.superseded_by_subject}</div>
                    </td>
                  </tr>
                </tbody>
              </table>

              <div className="ev">
                <div className="lbl">The citation — verbatim Marathi</div>
                <div className="mr">{f.citation_evidence}</div>
              </div>
              {f.supersession_evidence && (
                <div className="ev" style={{ borderLeftColor: 'var(--danger)' }}>
                  <div className="lbl">The supersession — verbatim Marathi</div>
                  <div className="mr">{f.supersession_evidence}</div>
                  {f.supersession_evidence_en &&
                    <div className="gloss">“{f.supersession_evidence_en}” — machine gloss,
                      a reading aid only</div>}
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </>
  )
}

const EXPLAIN: Record<string, string> = {
  date_only_insufficient:
    'The date matched but no file number agreed. A correct refusal — resolving on date alone ' +
    'would link every GR issued that day.',
  no_number: 'The citation carries no file number at all, so there is no second key to confirm with.',
  number_absent: 'The file number matches no GR in the corpus.',
  series_gap:
    'The file number matched a real series, but no member falls in the date window — the cited ' +
    'order is absent from the public crawl. Not dead: unverifiable.',
  other_dept: 'Names a department outside the four indexed here.',
  ambiguous: 'Two or more GRs matched both keys, so we abstained rather than pick one.',
}
