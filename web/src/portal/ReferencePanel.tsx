import { useState } from 'react'
import GRModal from './GRModal'
import type {
  ArchiveGR, Citation, Lang, RefFinding, ReferenceReport, ReviewResult, Verdict,
} from './draftApi'

/* SRS FR-1 / FR-2 / FR-3, and the problem statement's cross-department conflict bullet.

   Two presentation rules, both downstream of CLAUDE.md rule 3 (never fabricate a citation):

   1. **The five ways of not finding something are never merged.** A court order that the GR
      archive does not hold, an order cited from before the crawl begins, and an order that
      genuinely is not there are three different facts. Colouring them all red would roughly
      quadruple the error count and make it false, so each carries its own verdict pill and its
      own explanation, and only `not_in_archive` is styled as a defect.

   2. **Every supersession claim shows the sentence behind it.** The evidence quote under a
      "superseded by" line is the verbatim Marathi from the GR that did the cancelling. If we
      cannot show the officer that sentence, the claim does not ship. */

const T = {
  head: { en: 'Reference check', mr: 'संदर्भ तपासणी' },
  scope: { en: 'Resolved against', mr: 'यांच्याशी ताडून पाहिले' },
  grs: { en: 'GRs', mr: 'शासन निर्णय' },
  depts: { en: 'departments', mr: 'विभाग' },
  clean: { en: 'No reference defects', mr: 'संदर्भांमध्ये त्रुटी नाहीत' },
  errors: { en: 'errors', mr: 'त्रुटी' },
  citations: { en: 'Citations found', mr: 'आढळलेले संदर्भ' },
  none: { en: 'No citations were found in this document.', mr: 'या दस्तऐवजात कोणताही संदर्भ आढळला नाही.' },
  line: { en: 'line', mr: 'ओळ' },
  alsoAt: { en: 'also at', mr: 'तसेच' },
  no: { en: 'File no.', mr: 'क्रमांक' },
  dated: { en: 'Dated', mr: 'दिनांक' },
  preamble: { en: 'Preamble', mr: 'प्रस्तावना' },
  body: { en: 'Body', mr: 'मजकूर' },
  inForce: { en: 'In force', mr: 'अंमलात' },
  superseded: { en: 'Superseded', mr: 'अधिक्रमित' },
  supersededBy: { en: 'Superseded by', mr: 'अधिक्रमित —' },
  amendedBy: { en: 'Amended by', mr: 'सुधारित —' },
  citedBy: { en: 'orders cite this', mr: 'आदेश याचा संदर्भ देतात' },
  nearest: { en: 'Nearest orders in the same file series', mr: 'याच नस्तीतील जवळचे आदेश' },
  cancels: { en: 'cancels / amends', mr: 'रद्द / सुधारित' },
  crossDept: { en: 'another department', mr: 'अन्य विभाग' },
  jump: { en: 'Show in the text', mr: 'मजकुरात पाहा' },
  viewGR: { en: 'View this GR', mr: 'हा शासन निर्णय पाहा' },
  notInSet: { en: 'Not in the dataset — nothing to open', mr: 'संचात नाही — उघडण्यासारखे काही नाही' },
  alignHead: { en: 'Alignment with the cited orders', mr: 'संदर्भित आदेशांशी सुसंगती' },
  aiHead: { en: 'Review', mr: 'आढावा' },
  aiRun: { en: 'Write a plain-language review', mr: 'सुलभ भाषेत आढावा लिहा' },
  aiBusy: { en: 'The on-premise model is writing…', mr: 'स्थानिक प्रारूप लिहीत आहे…' },
  aiComputed: { en: 'Computed summary', mr: 'गणित सारांश' },
  stats: {
    citations: { en: 'citations', mr: 'संदर्भ' },
    verified: { en: 'found in archive', mr: 'संग्रहात आढळले' },
    not_in_archive: { en: 'not in archive', mr: 'संग्रहात नाहीत' },
    superseded: { en: 'cite a dead order', mr: 'रद्द आदेशाचा संदर्भ' },
    cross_department: { en: 'cross-department', mr: 'आंतरविभागीय' },
    out_of_scope: { en: 'outside archive scope', mr: 'संग्रहाच्या कक्षेबाहेर' },
  },
} as const

type Tone = 'ok' | 'bad' | 'warn' | 'mute'

/* Only `not_in_archive` and a superseded target are defects. Everything else is a limit of the
   archive or of the citation's own wording, and is toned down accordingly. */
const TONE: Record<Verdict, Tone> = {
  verified: 'ok',
  not_in_archive: 'bad',
  ambiguous: 'warn',
  unverifiable: 'warn',
  other_dept: 'mute',
  outside_range: 'mute',
  out_of_scope: 'mute',
}

const ALIGN_TONE: Record<string, Tone> = {
  aligned: 'ok', misaligned: 'bad', partial: 'warn', unverified: 'mute',
}

export default function ReferencePanel({ report, lang, mr, onJump, onReview, review, reviewing }: {
  report: ReferenceReport
  lang: Lang
  mr: boolean
  onJump?: (line: number) => void
  onReview?: () => void
  review?: ReviewResult | null
  reviewing?: boolean
}) {
  const L = (k: { en: string; mr: string }) => (mr ? k.mr : k.en)
  const [open, setOpen] = useState<string | null>(null)

  if (!report.available) {
    return (
      <div className="pk-refs">
        <div className="pk-alert">
          {mr
            ? 'संदर्भ संग्रह उपलब्ध नाही — अवलंबित्व आलेख तयार केलेला नाही.'
            : 'The reference archive is not loaded, so citations cannot be checked.'}
          {report.hint && <><br /><code>{report.hint}</code></>}
        </div>
      </div>
    )
  }

  const { summary: s, archive: a, document: d } = report
  const order: Record<RefFinding['severity'], number> = { error: 0, warning: 1, advisory: 2 }
  const findings = [...report.findings].sort((x, y) => order[x.severity] - order[y.severity])

  return (
    <div className="pk-refs">
      <div className="pk-refs-head">
        <div>
          <b>{L(T.head)}</b>
          <span className="pk-fine">
            {L(T.scope)} {a.grs.toLocaleString()} {L(T.grs)} · {a.departments.length} {L(T.depts)} ·
            {' '}{a.covers[0]} → {a.covers[1]}
            {d.department && <> · {mr ? 'हा दस्तऐवज' : 'this document'}: {d.department}</>}
          </span>
        </div>
        <span className={report.clean ? 'ok' : 'bad'}>
          {report.clean
            ? `✓ ${L(T.clean)}`
            : `${report.counts.error} ${L(T.errors)}`}
        </span>
      </div>

      {/* The headline verdict, and it is COMPUTED. Handing this judgement to the 2B model
          produced "the resolution remains valid because the cited references are either
          unverified or superseded" on a document whose citations had in fact been superseded. */}
      <div className={`pk-align ${ALIGN_TONE[report.alignment.verdict]}`}>
        <div className="pk-align-head">
          <b>{L(T.alignHead)}</b>
          <span>{report.alignment.label[lang] || report.alignment.label.en}</span>
        </div>
        <ul>{report.alignment.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <p className="pk-fine">{report.alignment.basis}</p>
      </div>

      <div className="pk-refstats">
        <Stat n={s.citations} label={L(T.stats.citations)} tone="mute" />
        <Stat n={s.verified} label={L(T.stats.verified)} tone="ok" />
        <Stat n={s.not_in_archive} label={L(T.stats.not_in_archive)} tone="bad" />
        <Stat n={s.superseded} label={L(T.stats.superseded)} tone="bad" />
        <Stat n={s.cross_department} label={L(T.stats.cross_department)} tone="warn" />
        <Stat n={s.out_of_scope} label={L(T.stats.out_of_scope)} tone="mute" />
      </div>

      {onReview && (
        <div className="pk-airev">
          <div className="pk-airev-head">
            <b>{L(T.aiHead)}</b>
            {!review && (
              <button className="pk-btn sm" onClick={onReview} disabled={reviewing}>
                {reviewing ? L(T.aiBusy) : L(T.aiRun)}
              </button>
            )}
          </div>
          {reviewing && <p className="pk-fine">{L(T.aiBusy)}</p>}
          {review && (
            <>
              <p className={`pk-airev-text ${review.degraded ? 'degraded' : ''}`}>
                {review.review}
              </p>
              {/* The computed line is kept visible next to the prose, never replaced by it —
                  the officer must always be able to see the answer that does not depend on
                  a model having behaved. */}
              {review.computed && !review.degraded && (
                <p className="pk-fine"><i>{L(T.aiComputed)}:</i> {review.computed}</p>
              )}
              <p className="pk-fine">{review.note}
                {review.stats?.seconds != null &&
                  ` · ${review.stats.model} · ${review.stats.seconds}s`}</p>
            </>
          )}
        </div>
      )}

      {findings.length > 0 && (
        <ul className="pk-findings pk-reffindings">
          {findings.map((f, i) => (
            <li key={i} className={f.severity}>
              <code>{f.code}</code>
              <div>
                {f.message}
                {f.evidence && <q className={mr ? 'pk-mr' : ''}>{f.evidence}</q>}
                {f.blast && Object.keys(f.blast.departments).length > 0 && (
                  <div className="pk-blastbar">
                    {Object.entries(f.blast.departments).map(([dept, n]) => (
                      <span key={dept}><b>{n}</b> {dept}</span>
                    ))}
                  </div>
                )}
                <small>{f.authority}</small>
              </div>
            </li>
          ))}
        </ul>
      )}

      <h5 className="pk-refs-sub">{L(T.citations)} — {report.citations.length}</h5>
      {report.citations.length === 0
        ? <p className="pk-fine">{L(T.none)}</p>
        : (
          <ol className="pk-citelist">
            {report.citations.map(c => (
              <CitationRow key={c.n} c={c} lang={lang} mr={mr} L={L}
                onJump={onJump} onOpen={setOpen} />
            ))}
          </ol>
        )}

      {open && <GRModal uid={open} lang={lang} mr={mr} onClose={() => setOpen(null)} />}
    </div>
  )
}

function Stat({ n, label, tone }: { n: number; label: string; tone: Tone }) {
  return (
    <div className={`pk-refstat ${tone} ${n === 0 ? 'zero' : ''}`}>
      <b>{n}</b><span>{label}</span>
    </div>
  )
}

function CitationRow({ c, lang, mr, L, onJump, onOpen }: {
  c: Citation
  lang: Lang
  mr: boolean
  L: (k: { en: string; mr: string }) => string
  onJump?: (line: number) => void
  onOpen?: (uid: string) => void
}) {
  const [open, setOpen] = useState(false)
  const tone = TONE[c.verdict]
  // The citation text is quoted from the document, so it is rendered in the document's script,
  // not the interface language. A Marathi citation shown in a Latin face is unreadable.
  const cite = c.side === 'mr' ? 'pk-mr' : ''

  return (
    <li className={`pk-cite ${tone}`}>
      <div className="pk-cite-top">
        <span className="pk-cite-n">{c.n}</span>
        <span className="pk-tag">{c.kind_label[lang] || c.kind_label.en}</span>
        <span className="pk-tag soft">{c.zone === 'preamble' ? L(T.preamble) : L(T.body)}</span>
        <button type="button" className="pk-linkish"
          onClick={() => onJump?.(c.line)} disabled={!onJump}>
          {L(T.line)} {c.line}
          {c.also_at_lines.length > 0 && ` (${L(T.alsoAt)} ${c.also_at_lines.join(', ')})`}
        </button>
        {c.cue && <span className="pk-tag cue">{L(T.cancels)}</span>}
        <span className={`pk-verdict ${tone}`}>{c.verdict_label[lang] || c.verdict_label.en}</span>
      </div>

      <p className={`pk-cite-raw ${cite}`}>{c.raw}</p>

      <div className="pk-cite-keys">
        <span><i>{L(T.no)}</i> <em className={cite}>{c.cited_no || '—'}</em></span>
        <span><i>{L(T.dated)}</i> {c.cited_date}</span>
        {c.cited_dept && <span><i>{mr ? 'विभाग' : 'Dept'}</i> {c.cited_dept}</span>}
      </div>

      {c.match ? (
        <Match c={c} mr={mr} L={L} onOpen={onOpen} />
      ) : (
        <>
          <p className="pk-cite-why">{c.why}</p>
          {/* FR-3 the other way round: say plainly that there is nothing to open, rather than
              offering a dead button. */}
          <p className="pk-fine pk-noopen">{L(T.notInSet)}</p>
          {c.candidates.length > 0 && (
            <div className="pk-cands">
              <button type="button" className="pk-linkish" onClick={() => setOpen(o => !o)}>
                {open ? '▾' : '▸'} {L(T.nearest)} ({c.candidates.length})
              </button>
              {open && (
                <ul>
                  {c.candidates.map(g => (
                    <li key={g.uid}>
                      <code>{g.uid}</code> <span>{g.date}</span>
                      <span className="pk-fine">{g.subject}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </li>
  )
}

function Match({ c, mr, L, onOpen }: {
  c: Citation
  mr: boolean
  L: (k: { en: string; mr: string }) => string
  onOpen?: (uid: string) => void
}) {
  const m = c.match as ArchiveGR
  const st = c.status!
  return (
    <div className={`pk-match ${st.in_force ? '' : 'dead'}`}>
      <div className="pk-match-head">
        <code>{m.uid}</code>
        <span>{m.date}</span>
        <span className={c.cross_dept ? 'xdept' : ''}>{m.dept}</span>
        <span className={`pk-verdict ${st.in_force ? 'ok' : 'bad'}`}>
          {st.in_force ? L(T.inForce) : L(T.superseded)}
        </span>
      </div>
      {onOpen && (
        <button type="button" className="pk-btn sm pk-openbtn" onClick={() => onOpen(m.uid)}>
          {L(T.viewGR)} →
        </button>
      )}
      {m.subject && <p className="pk-match-sub">{m.subject}</p>}

      {st.superseded_by.map(k => (
        <Chain key={k.uid} g={k} tone="bad" label={L(T.supersededBy)} mr={mr} />
      ))}
      {st.in_force && st.amended_by.map(k => (
        <Chain key={k.uid} g={k} tone="warn" label={L(T.amendedBy)} mr={mr} />
      ))}

      <div className="pk-fine pk-match-foot">
        <b>{st.cited_by_count}</b> {L(T.citedBy)}
        {typeof c.date_drift_days === 'number' && c.date_drift_days !== 0 && (
          <> · {mr
            ? `संग्रहातील दिनांक ${c.date_drift_days > 0 ? '+' : ''}${c.date_drift_days} दिवस`
            : `archive date differs by ${c.date_drift_days > 0 ? '+' : ''}${c.date_drift_days} d`}
            {' '}({mr ? 'प्रसिद्धी विलंब — अपेक्षित' : 'publication drift — expected'})</>
        )}
      </div>
    </div>
  )
}

function Chain({ g, tone, label, mr }: {
  g: ArchiveGR; tone: 'bad' | 'warn'; label: string; mr: boolean
}) {
  return (
    <div className={`pk-chain ${tone}`}>
      <div>
        <b>{label}</b> <code>{g.uid}</code> <span>{g.date}</span> <span>{g.dept}</span>
      </div>
      {g.subject && <p>{g.subject}</p>}
      {/* The sentence that produced the edge. Without it this is an assertion, not a finding. */}
      {g.evidence && <q className={mr ? 'pk-mr' : ''}>{g.evidence}</q>}
    </div>
  )
}
