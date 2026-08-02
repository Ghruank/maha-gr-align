import { useEffect, useState } from 'react'
import { fmt } from '../../api'

// Bilingual legal terminology. Two halves with very different confidence, and the page says so:
// numeric parity is precise and serious; the glossary is lead-generation with real noise.
export default function Bilingual() {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [tab, setTab] = useState<'parity' | 'terms'>('parity')

  useEffect(() => {
    fetch('/api/bilingual?limit=120').then(r => r.json()).then(setD).catch(e => setErr(String(e)))
  }, [])

  if (err) return <div className="panel">Backend unreachable: {err}</div>
  if (!d) return <div className="panel muted">Loading…</div>
  if (!d.available) return <div className="panel">Not built yet. {d.hint}</div>

  const p = d.parity, g = d.glossary
  const mags = (p.findings ?? []).filter((f: any) => f.kind === 'MAGNITUDE_ERROR')

  return (
    <>
      <h1>Bilingual Legal Terminology</h1>
      <p className="sub">
        Marathi is the legally operative text; the English is a working view that officials
        actually read. This page finds places where the two disagree — numerically, and in how the
        same legal term is rendered.
      </p>

      <div className="panel">
        <div className="note">
          <b>What this does and does not measure.</b> {p.caveat}
        </div>
      </div>

      <div className="panel">
        <div className="row">
          <button className={tab === 'parity' ? 'on' : ''} onClick={() => setTab('parity')}>
            Numeric parity ({fmt(p.classes?.MAGNITUDE_ERROR ?? 0)} magnitude errors)
          </button>
          <button className={tab === 'terms' ? 'on' : ''} onClick={() => setTab('terms')}>
            Terminology ({fmt(g.inconsistent_terms?.length ?? 0)} inconsistent terms)
          </button>
        </div>
      </div>

      {tab === 'parity' ? (
        <>
          <div className="tiles">
            <div className="tile">
              <div className="k">A naive diff would flag</div>
              <div className="v">{(p.naive_diff_rate * 100).toFixed(0)}%</div>
              <div className="d">
                of {fmt(p.sampled)} pairs — which is why flagging is worthless and classifying
                is the whole job
              </div>
            </div>
            <div className="tile">
              <div className="k">Significant divergence</div>
              <div className="v">{(p.significant_divergence_rate * 100).toFixed(1)}%</div>
              <div className="d">
                after restricting to numbers with ≥4 significant digits — amounts, not list
                ordinals
              </div>
            </div>
            <div className="tile hero">
              <div className="k">Magnitude errors</div>
              <div className="v">{fmt(p.classes?.MAGNITUDE_ERROR ?? 0)}</div>
              <div className="d">same digits, wrong scale — the serious class</div>
            </div>
            <div className="tile">
              <div className="k">OCR artefacts suppressed</div>
              <div className="v">
                {fmt((p.classes?.TABLE_MERGE ?? 0) + (p.classes?.YEAR_ONLY_IN_MR ?? 0))}
              </div>
              <div className="d">
                table-cell merges and dropped years — explained, so not reported as findings
              </div>
            </div>
          </div>

          <h2>How every divergence was explained</h2>
          <div className="panel scroll">
            <table>
              <thead>
                <tr><th>Class</th><th>Severity</th><th className="num">Count</th>
                  <th>What it means</th></tr>
              </thead>
              <tbody>
                {Object.entries(p.classes as Record<string, number>).map(([k, v]) => (
                  <tr key={k}>
                    <td className="mono" style={{ fontSize: 12 }}>{k}</td>
                    <td>
                      <span className={`pill ${p.severity_of[k] === 'ERROR' ? 'SUPERSEDES'
                        : p.severity_of[k] === 'WARN' ? 'AMENDS' : 'REFERENCES'}`}>
                        {p.severity_of[k]}</span>
                    </td>
                    <td className="num">{fmt(v)}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{CLASS_HELP[k]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>Magnitude errors — an amount is wrong by a factor of ten or more</h2>
          <div className="panel scroll">
            <table>
              <thead>
                <tr><th>GR</th><th className="num">Marathi (authoritative)</th>
                  <th className="num">English says</th><th className="num">Factor</th></tr>
              </thead>
              <tbody>
                {mags.slice(0, 40).map((f: any, i: number) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 12 }}>{f.uid}</td>
                    <td className="num mono">{Number(f.marathi_value).toLocaleString('en-IN')}</td>
                    <td className="num mono muted">
                      {f.english_values.map((v: string) =>
                        Number(v).toLocaleString('en-IN')).join(', ')}
                    </td>
                    <td className="num" style={{ color: 'var(--danger)', fontWeight: 650 }}>
                      {f.factor ? `×${f.factor.toLocaleString('en-IN')}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="panel">
            <div className="note">
              <b>Confidence here is lower than on the parity tab, and deliberately stated.</b>{' '}
              These terms are mined by association across {fmt(g.sampled_pairs)} aligned document
              pairs — there is no word-alignment model and no hand-written term list, because a
              hand-written list is the kind of assertion this project refuses. Association is not
              translation, so expect real noise alongside real findings. Treat this as
              lead generation for a human terminologist, not a dictionary.
              <br /><br />
              An earlier version returned {fmt(120)} "inconsistent" terms, most of them document
              topics rather than translations: <span className="mr">तक्रारी</span>,{' '}
              <span className="mr">प्रवेश</span> and <span className="mr">शुल्क</span> all mapped
              to the same cluster (capitation / ragging / usability) because one family of
              education-regulation GRs contains all of those words together. Filtering on the
              insight that <b>a translation is near-bijective while a topic marker is
              many-to-many</b> cut it to {fmt(g.inconsistent_terms.length)}.
            </div>
          </div>

          <h2>The same Marathi legal term, rendered several ways in English</h2>
          {g.inconsistent_terms.map((e: any, i: number) => (
            <div className="panel" key={i}>
              <div className="spread">
                <span className="mr" style={{ fontSize: 19, fontWeight: 650 }}>{e.marathi}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  appears in {fmt(e.documents)} documents
                </span>
              </div>
              <div className="scroll" style={{ marginTop: 8 }}>
                <table>
                  <thead>
                    <tr><th>English rendering</th><th className="num">Coverage</th>
                      <th></th><th className="num">Lift</th>
                      <th className="num">Marathi partners</th></tr>
                  </thead>
                  <tbody>
                    {e.renderings.map((r: any, j: number) => (
                      <tr key={j}>
                        <td>{r.english}</td>
                        <td className="num">{(r.coverage * 100).toFixed(0)}%</td>
                        <td style={{ width: 140 }}>
                          <div className="bar" style={{ width: `${r.coverage * 100}%` }} />
                        </td>
                        <td className="num muted">×{r.lift}</td>
                        <td className="num muted">{r.mr_partners}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}
    </>
  )
}

const CLASS_HELP: Record<string, string> = {
  MAGNITUDE_ERROR: 'Same significant digits at a different scale — ₹1.36 crore rendered as ₹13,600. Serious and checkable.',
  TRUNCATED: 'The English number is a prefix of the Marathi one — digits lost in translation.',
  TABLE_MERGE: 'One Marathi table cell arrived as two English tokens. An OCR column-boundary artefact, not a semantic discrepancy.',
  YEAR_ONLY_IN_MR: 'A bare year present in Marathi and absent in English. Usually harmless.',
  MISSING_FROM_ENGLISH: 'Present in Marathi, absent in English, with no mechanical explanation. The honest residual.',
}
