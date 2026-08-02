import { useState } from 'react'
import type { GlossaryReport, Lang } from './draftApi'

/* SRS FR-7 / FR-8 / FR-9 — controlled bilingual terminology.

   Two presentation decisions carry the honesty of this panel:

   1. **A withheld suggestion is shown as a withheld suggestion.** `रद्द` (cancelled),
      `अधिक्रमित` (superseded) and `व्यपगत` (lapsed) do different things to an order, so seeing
      "cancelled" in an English GR is not evidence of a mis-rendering — it may be a perfectly
      correct rendering of `रद्द`. Those findings appear with the ambiguity spelled out and no
      replacement offered. FR-9 declining to guess is the requirement working.

   2. **Unapproved entries say so on their face.** The glossary is part Manual of Office
      Procedure and part one person's judgement, and an officer must be able to tell which is
      which before acting on it. */

const T = {
  head: { en: 'Terminology', mr: 'परिभाषा' },
  clean: { en: 'Terminology consistent with the glossary', mr: 'परिभाषेशी सुसंगत' },
  issues: { en: 'to check', mr: 'तपासण्याजोगे' },
  glossary: { en: 'Controlled glossary', mr: 'नियंत्रित परिभाषा-सूची' },
  approved: { en: 'approved', mr: 'मान्य' },
  proposed: { en: 'proposed, not yet approved', mr: 'प्रस्तावित' },
  found: { en: 'Document uses', mr: 'दस्तऐवजात' },
  should: { en: 'Approved term', mr: 'मान्य संज्ञा' },
  noSuggest: { en: 'No replacement proposed', mr: 'पर्याय सुचवलेला नाही' },
  times: { en: 'occurrences', mr: 'वेळा' },
  line: { en: 'line', mr: 'ओळ' },
  present: { en: 'Glossary terms in this document', mr: 'या दस्तऐवजातील परिभाषा' },
  none: { en: 'No glossary terms were found in this document.', mr: 'परिभाषेतील संज्ञा आढळल्या नाहीत.' },
  mrNote: {
    en: 'This is the Marathi text, which is the legally operative one — there is no rendering here to correct. The list below is the English each term must take when the English version is prepared.',
    mr: 'हा मराठी मजकूर विधिग्राह्य आहे; येथे दुरुस्त करण्यासारखे भाषांतर नाही. खालील यादी इंग्रजी आवृत्तीसाठी वापरावयाच्या संज्ञा दर्शवते.',
  },
} as const

export default function GlossaryPanel({ report, mr, onJump }: {
  report: GlossaryReport
  /** Accepted for symmetry with the other panels; the glossary renders each term in its own
      script rather than in the interface language, so nothing here varies by it. */
  lang?: Lang
  mr: boolean
  onJump?: (line: number) => void
}) {
  const L = (k: { en: string; mr: string }) => (mr ? k.mr : k.en)
  const [showAll, setShowAll] = useState(false)

  if (!report.available) {
    return (
      <div className="pk-refs">
        <div className="pk-alert">
          {mr ? 'परिभाषा-सूची उपलब्ध नाही.' : 'The controlled glossary is not loaded.'}
          {report.hint && <><br /><code>{report.hint}</code></>}
        </div>
      </div>
    )
  }

  const g = report.glossary
  const shown = showAll ? report.terms_present : report.terms_present.slice(0, 8)

  return (
    <div className="pk-refs">
      <div className="pk-refs-head">
        <div>
          <b>{L(T.head)}</b>
          <span className="pk-fine">
            {L(T.glossary)}: {g.terms} {mr ? 'संज्ञा' : 'terms'}, {g.approved} {L(T.approved)} ·
            {' '}{mr ? 'मजकूर' : 'text read as'} {report.script === 'mr' ? 'मराठी' : 'English'}
          </span>
        </div>
        <span className={report.clean ? 'ok' : 'bad'}>
          {report.clean ? `✓ ${L(T.clean)}` : `${report.counts.total} ${L(T.issues)}`}
        </span>
      </div>

      {report.script === 'mr' && <p className="pk-fine pk-gl-note">{L(T.mrNote)}</p>}

      {report.findings.length > 0 && (
        <ul className="pk-gl-findings">
          {report.findings.map((f, i) => (
            <li key={i} className={f.severity}>
              <div className="pk-gl-swap">
                <span className="pk-gl-bad">{f.found}</span>
                {f.suggestion
                  ? <><span className="pk-gl-arrow">→</span>
                    <span className="pk-gl-good">{f.suggestion}</span></>
                  : <span className="pk-gl-hold">{L(T.noSuggest)}</span>}
                <code className="pk-gl-mr pk-mr">{f.mr}</code>
                {f.line != null && (
                  <button type="button" className="pk-linkish"
                    onClick={() => onJump?.(f.line!)} disabled={!onJump}>
                    {L(T.line)} {f.line}
                  </button>
                )}
                <span className="pk-tag soft">×{f.occurrences}</span>
              </div>
              <p>{f.message}</p>
              {f.note && <p className="pk-fine">{f.note}</p>}
              <small>{f.authority}</small>
            </li>
          ))}
        </ul>
      )}

      <h5 className="pk-refs-sub">{L(T.present)} — {report.terms_present.length}</h5>
      {report.terms_present.length === 0
        ? <p className="pk-fine">{L(T.none)}</p>
        : (
          <>
            <ul className="pk-gl-terms">
              {shown.map(t => (
                <li key={t.id} title={t.authority}>
                  <span className="pk-mr">{t.mr}</span>
                  <span className="pk-gl-arrow">→</span>
                  <b>{t.en}</b>
                  {!t.approved && <em>{L(T.proposed)}</em>}
                </li>
              ))}
            </ul>
            {report.terms_present.length > 8 && (
              <button type="button" className="pk-linkish"
                onClick={() => setShowAll(s => !s)}>
                {showAll ? '▾' : '▸'} {showAll
                  ? (mr ? 'कमी दाखवा' : 'show fewer')
                  : `${mr ? 'सर्व' : 'all'} ${report.terms_present.length}`}
              </button>
            )}
          </>
        )}
    </div>
  )
}
